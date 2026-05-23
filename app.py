import streamlit as st
import pandas as pd
import numpy as np

# Set up the page layout
st.set_page_config(page_title="Tech Time Tracker", layout="wide")

# --- CSS FOR CLEAN PRINTING ---
st.markdown("""
<style>
@media print {
    header { display: none !important; }
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stFileUploader"] { display: none !important; }
    [data-testid="stSelectbox"] { display: none !important; }
    div[data-baseweb="tab-list"] { display: none !important; }
    h1 { display: none !important; }
    .hide-on-print { display: none !important; }
    .stAlert { display: none !important; }
    
    .main .block-container {
        max-width: 100% !important;
        width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    table { width: 100% !important; table-layout: auto !important; }
    [data-testid="stTable"] { width: 100% !important; }
    [data-testid="stDataFrame"] > div { height: auto !important; max-height: none !important; overflow: visible !important; }
}
</style>
""", unsafe_allow_html=True)
# ------------------------------

st.title("Technician Time Comparison Tool")
st.markdown('<p class="hide-on-print">Upload your <strong>Clocked-in Hours</strong> and <strong>Lowes Ops</strong> files to compare tracked job time against clocked time.</p>', unsafe_allow_html=True)

# Create two columns for the file uploaders
col1, col2 = st.columns(2)
with col1:
    time_file = st.file_uploader("Upload Time Sheet (CSV)", type=['csv'])
with col2:
    ops_file = st.file_uploader("Upload Lowes Ops Export (CSV)", type=['csv'])

# Helper function to format decimal hours to HH:MM string
def format_hm(hrs):
    if pd.isna(hrs) or hrs == 0: return "-"
    sign = "-" if hrs < 0 else ""
    hrs = abs(hrs)
    h = int(hrs)
    m = int(round((hrs - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{sign}{h}:{m:02d}"

# Helper function to parse HH:MM strings to decimal hours
def parse_hm(time_str):
    if pd.isna(time_str) or time_str == '-' or time_str == '':
        return 0.0
    try:
        parts = str(time_str).strip().split(':')
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h + m / 60.0
    except:
        return 0.0

# Special parsing handler for manual adjustments using hours and minutes
def parse_adj_hm(val_str):
    val_str = str(val_str).strip()
    if not val_str or val_str == '-' or val_str == '0' or val_str == '0:00':
        return 0.0
    try:
        sign = -1 if val_str.startswith('-') else 1
        clean_val = val_str.lstrip('+-')
        if ':' in clean_val:
            parts = clean_val.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return sign * (h + m / 60.0)
        else:
            return sign * float(clean_val)
    except:
        return 0.0

def parse_diff_to_hours(val):
    if val == '-' or pd.isna(val): return 0.0
    try:
        sign = -1 if str(val).startswith('-') else 1
        clean_val = str(val).replace('-', '')
        if ':' in clean_val:
            parts = clean_val.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return sign * (h + m / 60.0)
    except:
        pass
    return 0.0

def highlight_daily(val):
    hrs = parse_diff_to_hours(val)
    if hrs > 1.0: return 'background-color: #ffcccc; color: #990000;'
    return ''

def highlight_weekly_row(row):
    styles = [''] * len(row)
    if 'Total Diff' in row and 'Days Worked' in row:
        diff_idx = row.index.get_loc('Total Diff')
        diff_hrs = parse_diff_to_hours(row['Total Diff'])
        days_worked = row['Days Worked']
        if diff_hrs > (days_worked * 1.0):
            styles[diff_idx] = 'background-color: #ffcccc; color: #990000;'
    return styles

def highlight_individual_report(row, days_worked):
    styles = [''] * len(row)
    if 'Difference' in row and 'Day' in row:
        diff_idx = row.index.get_loc('Difference')
        diff_hrs = parse_diff_to_hours(row['Difference'])
        if row['Day'] == "TOTAL WEEKLY":
            if diff_hrs > (days_worked * 1.0): styles[diff_idx] = 'background-color: #ffcccc; color: #990000;'
        else:
            if diff_hrs > 1.0: styles[diff_idx] = 'background-color: #ffcccc; color: #990000;'
    return styles

# Style function specifically for parsing the benchmarking columns
def highlight_bench_col(s):
    styles = []
    for val in s:
        try:
            if ' (Div: ' in str(val):
                tech_str, div_str = val.split(' (Div: ')
                t_h = parse_hm(tech_str)
                d_h = parse_hm(div_str.replace(')', ''))
                if t_h > d_h * 1.25 and t_h > 0:
                    styles.append('background-color: #ffcccc; color: #990000;')
                    continue
            styles.append('')
        except:
            styles.append('')
    return styles

# Custom highlight rule for consistency grades
def highlight_consistency(s):
    styles = []
    for val in s:
        if val == "⚠️ Low Consistency":
            styles.append('background-color: #ffcccc; color: #990000; font-weight: bold;')
        elif val == "⭐ High Consistency":
            styles.append('background-color: #e6f4ea; color: #137333; font-weight: bold;')
        else:
            styles.append('')
    return styles

# --- Advanced Reporting Block Function ---
def show_advanced_reporting(ops_df, final_df, export_df, bounds_df, delayed_launches_df, daily_route, tab_key):
    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
    # === BOSS TOOLS SECTION ===
    st.header("💼 Boss Tools (Financials & Efficiency)")
    
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    
    with b_col1:
        st.markdown("**Calculate Lost Revenue**")
        rate = st.number_input("Fallback Rate for Unmapped Techs ($)", value=25.0, step=1.0, key=f"rate_{tab_key}")
        
    total_clocked = final_df['Total_Weekly_Clocked_Hrs'].sum()
    total_job = final_df['Total_Weekly_Job_Hrs'].sum()
    efficiency = (total_job / total_clocked * 100) if total_clocked > 0 else 0
    
    total_lsi = final_df.get('Simple_Installs_Hrs', pd.Series([0])).sum()
    total_wh = final_df.get('Water_Heaters_Hrs', pd.Series([0])).sum()
    
    total_lsi_assumed = final_df.get('Assumed_LSI_Clocked', pd.Series([0])).sum()
    total_wh_assumed = final_df.get('Assumed_WH_Clocked', pd.Series([0])).sum()
    
    lsi_eff = (total_lsi / total_lsi_assumed * 100) if total_lsi_assumed > 0 else 0
    wh_eff = (total_wh / total_wh_assumed * 100) if total_wh_assumed > 0 else 0
    
    lost_hrs = final_df[final_df['Total_Weekly_Diff_Hrs'] > 0]['Total_Weekly_Diff_Hrs'].sum()
    
    def get_custom_loss(row, fallback):
        nl = str(row['Name']).lower()
        diff = row['Total_Weekly_Diff_Hrs']
        if diff <= 0: return 0.0
        if 'sean marble' in nl: return diff * 33.65
        if 'michael owens' in nl: return diff * 31.25
        if 'bryan' in nl or 'erik' in nl: return 0.0
        if 'nate' in nl: return diff * 22.50
        if any(n in nl for n in ['edward', 'matt', 'tanner']): return diff * 25.00
        return diff * fallback

    lost_money = final_df.apply(lambda r: get_custom_loss(r, rate), axis=1).sum()
    
    with b_col2:
        st.metric(label="Total Unaccounted Hours", value=f"{lost_hrs:.1f} hrs")
    with b_col3:
        st.metric(label="Financial Leakage (Loss)", value=f"${lost_money:,.2f}")
    with b_col4:
        st.metric(label="Overall Div Efficiency", value=f"{efficiency:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)
    bu_col1, bu_col2, bu_col3 = st.columns(3)
    with bu_col1:
        st.metric(label="LSI (Simple Installs) Efficiency", value=f"{lsi_eff:.1f}%", delta=f"{total_lsi:.1f} Job Hrs", delta_color="off")
    with bu_col2:
        st.metric(label="Water Heaters Efficiency", value=f"{wh_eff:.1f}%", delta=f"{total_wh:.1f} Job Hrs", delta_color="off")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # --- Daily Division Health Trend ---
    trend_col, leaderboard_col = st.columns(2)
    
    with trend_col:
        st.subheader("📈 Daily Division Health Trend")
        st.markdown("*(Combined team efficiency analyzed day-by-day across all business units)*")
        trend_data = []
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            day_clocked = final_df[f'{d}_Clocked_Hrs'].sum()
            day_job = final_df[f'{d}_Job_Hrs'].sum()
            day_eff = (day_job / day_clocked * 100) if day_clocked > 0 else 0.0
            trend_data.append({
                "Day": d, 
                "Total Clocked": format_hm(day_clocked), 
                "Job Status Time": format_hm(day_job), 
                "Efficiency Score": f"{day_eff:.1f}%"
            })
        trend_df = pd.DataFrame(trend_data)
        st.dataframe(trend_df, use_container_width=True)

    with leaderboard_col:
        st.subheader("🚨 Team Leaderboard")
        st.markdown("*(Whole team sorted by highest unaccounted time after overrides)*")
        leaderboard_df = final_df.sort_values(by='Daily_Avg_Diff_Hrs', ascending=False).copy()
        if not leaderboard_df.empty:
            leaderboard_df['Total Clocked'] = leaderboard_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
            leaderboard_df['Total Job Time'] = leaderboard_df['Total_Weekly_Job_Hrs'].apply(format_hm)
            leaderboard_df['Manual Adj'] = leaderboard_df['Adjustment_Hrs'].apply(format_hm)
            leaderboard_df['Daily Avg Diff'] = leaderboard_df['Daily_Avg_Diff_Hrs'].apply(format_hm)
            leaderboard_df['Total Diff'] = leaderboard_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
            
            show_leaderboard = leaderboard_df[['Name', 'Total Clocked', 'Total Job Time', 'Manual Adj', 'Daily Avg Diff', 'Total Diff']].copy()
            def highlight_leaderboard(row):
                val = parse_diff_to_hours(row['Total Diff'])
                if val > 0:
                    return ['background-color: #ffcccc; color: #990000;'] * len(row)
                return [''] * len(row)
            try:
                styled_leaderboard = show_leaderboard.reset_index(drop=True).style.hide(axis="index").apply(highlight_leaderboard, axis=1)
            except Exception:
                styled_leaderboard = show_leaderboard.reset_index(drop=True).style.apply(highlight_leaderboard, axis=1)
            st.dataframe(styled_leaderboard, use_container_width=True)
        else:
            st.info("No tech data available to display.")

    # === OVERTIME HORIZON PREDICTOR ===
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🚨 Fleet Overtime Horizon Predictor")
    st.markdown("*(Monitors pacing thresholds. Salaried under 35 hrs and Piece-Rate over 45 hrs flag red automatically)*")
    ot_rows = []
    for idx, row in final_df.iterrows():
        tech_name = row['Name']
        nl = tech_name.lower()
        hrs = row['Total_Weekly_Clocked_Hrs']
        
        if "sean marble" in nl or "michael owens" in nl:
            status = "⚠️ Low Volume Warning (Under 35 Hrs)" if hrs < 35.0 else "✅ Salary - Exempt"
            ot_hrs = "-"
        elif "bryan" in nl or "erik" in nl:
            status = "🚨 High Burnout Risk (Over 45 Hrs)" if hrs > 45.0 else "✅ Piece Rate - Exempt"
            ot_hrs = "-"
        else:
            if hrs > 40:
                status = "🚨 Overtime Incurred"
                ot_hrs = format_hm(hrs - 40)
            elif hrs > 35:
                status = "⚠️ High Overtime Risk"
                ot_hrs = "-"
            else:
                status = "✅ Safe Strategy"
                ot_hrs = "-"
        ot_rows.append({"Name": tech_name, "Weekly Clocked": format_hm(hrs), "Pace Status": status, "Overtime Hours": ot_hrs})
    
    if ot_rows:
        ot_predictor_df = pd.DataFrame(ot_rows)
        def style_ot_predictor(row):
            st_val = row['Pace Status']
            if "🚨" in st_val or "⚠️ Low Volume" in st_val:
                return ['background-color: #ffcccc; color: #990000;'] * len(row)
            elif "⚠️ High Overtime" in st_val:
                return ['background-color: #fff3cd; color: #856404;'] * len(row)
            return [''] * len(row)
        try:
            styled_ot = ot_predictor_df.reset_index(drop=True).style.hide(axis="index").apply(style_ot_predictor, axis=1)
        except Exception:
            styled_ot = ot_predictor_df.reset_index(drop=True).style.apply(style_ot_predictor, axis=1)
        st.dataframe(styled_ot, use_container_width=True)
            
    st.markdown("<br>", unsafe_allow_html=True)

    # === OPS MANAGER TOOLS (BENCHMARKING & REWARDS) ===
    st.header("📊 Ops Manager Tools (Benchmarking & Performance)")
    
    bench_col, gold_star_col = st.columns(2)
    
    with bench_col:
        st.subheader("📋 Team Processing Baselines & Predictability")
        st.markdown("*(Individual average vs. Division baseline. Red flags show techs >25% slower than average)*")
        valid_jobs = ops_df[ops_df['Total_Job_Time_Hours'] > 0]
        div_avg_drive = valid_jobs['Drive_Time_Hrs'].mean()
        div_avg_store = valid_jobs['Store_Time_Hrs'].mean()
        div_avg_ip = valid_jobs['In_Progress_Time_Hrs'].mean()
        div_avg_total = valid_jobs['Total_Job_Time_Hours'].mean()
        
        tech_stats = valid_jobs.groupby('Assigned Team Members').agg(
            Drive_Avg=('Drive_Time_Hrs', 'mean'),
            Store_Avg=('Store_Time_Hrs', 'mean'),
            IP_Avg=('In_Progress_Time_Hrs', 'mean'),
            Total_Avg=('Total_Job_Time_Hours', 'mean'),
            IP_Std=('In_Progress_Time_Hrs', 'std'),
            Job_Count=('Total_Job_Time_Hours', 'size')
        ).reset_index()
        
        def format_bench(val, div_val):
            if pd.isna(val): return "-"
            return f"{format_hm(val)} (Div: {format_hm(div_val)})"
            
        def assign_predictability(row):
            if row['Job_Count'] < 2 or pd.isna(row['IP_Std']):
                return "Establishing Baseline"
            if row['IP_Std'] > 0.75:
                return "⚠️ Low Consistency"
            return "⭐ High Consistency"
            
        tech_stats['Avg Drive/Job'] = tech_stats['Drive_Avg'].apply(lambda x: format_bench(x, div_avg_drive))
        tech_stats['Avg Store/Job'] = tech_stats['Store_Avg'].apply(lambda x: format_bench(x, div_avg_store))
        tech_stats['Avg In-Progress/Job'] = tech_stats['IP_Avg'].apply(lambda x: format_bench(x, div_avg_ip))
        tech_stats['Avg Total Job Length'] = tech_stats['Total_Avg'].apply(lambda x: format_bench(x, div_avg_total))
        tech_stats['Predictability Index'] = tech_stats.apply(assign_predictability, axis=1)
        
        show_bench = tech_stats[['Assigned Team Members', 'Avg Drive/Job', 'Avg Store/Job', 'Avg In-Progress/Job', 'Avg Total Job Length', 'Predictability Index']].rename(columns={'Assigned Team Members': 'Name'})
        try:
            styled_bench = show_bench.reset_index(drop=True).style.hide(axis="index").apply(highlight_bench_col, subset=['Avg Drive/Job', 'Avg Store/Job', 'Avg In-Progress/Job', 'Avg Total Job Length']).apply(highlight_consistency, subset=['Predictability Index'])
        except Exception:
            styled_bench = show_bench.reset_index(drop=True).style.apply(highlight_bench_col, subset=['Avg Drive/Job', 'Avg Store/Job', 'Avg In-Progress/Job', 'Avg Total Job Length']).apply(highlight_consistency, subset=['Predictability Index'])
        st.dataframe(styled_bench, use_container_width=True)

    with gold_star_col:
        st.subheader("⭐ The \"Gold Star\" High-Performer List")
        st.markdown("*(Technicians who average under 1:30 of unallocated difference per day worked. Store delays do NOT penalize techs)*")
        
        gold_star_df = final_df[(final_df['Daily_Avg_Diff_Hrs'] < 1.5) & (final_df['Days_Worked'] > 0)].copy()
        
        if not gold_star_df.empty:
            gold_star_df = gold_star_df.sort_values(by='Daily_Avg_Diff_Hrs', ascending=True)
            
            gold_star_df['Total Clocked'] = gold_star_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
            gold_star_df['Total Job Time'] = gold_star_df['Total_Weekly_Job_Hrs'].apply(format_hm)
            gold_star_df['Daily Avg Diff'] = gold_star_df['Daily_Avg_Diff_Hrs'].apply(format_hm)
            gold_star_df['Total Diff'] = gold_star_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
            show_gold = gold_star_df[['Name', 'Total Clocked', 'Total Job Time', 'Daily Avg Diff', 'Total Diff']].copy()
            try:
                styled_gold = show_gold.reset_index(drop=True).style.hide(axis="index").set_properties(**{'background-color': '#e6f4ea', 'color': '#137333'})
            except Exception:
                styled_gold = show_gold.reset_index(drop=True).style.set_properties(**{'background-color': '#e6f4ea', 'color': '#137333'})
            st.dataframe(styled_gold, use_container_width=True)
        else:
            st.info("No technicians qualified for the Gold Star list this week.")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Skill Matrix & Training Flag
    st.subheader("🎯 The Technician Skill Matrix & Training Flag")
    st.markdown("*(Compares a technician's LSI performance against their WH performance. Flags techs where the gap exceeds 25%)*")
    
    skill_df = final_df.copy()
    if not skill_df.empty:
        skill_df['Eff Gap'] = np.where(
            (skill_df['Simple_Installs_Count'] > 0) & (skill_df['Water_Heaters_Count'] > 0),
            abs(skill_df['LSI_Eff_Raw'] - skill_df['WH_Eff_Raw']),
            0.0
        )
        
        def assign_flag(row):
            lsi_cnt = row['Simple_Installs_Count']
            wh_cnt = row['Water_Heaters_Count']
            if lsi_cnt > 0 and wh_cnt > 0:
                if row['Eff Gap'] > 25.0:
                    if row['LSI_Eff_Raw'] > row['WH_Eff_Raw']:
                        return "⚠️ Needs WH Ride-Along"
                    else:
                        return "⚠️ Needs LSI Ride-Along"
                return "✅ Balanced Execution"
            elif lsi_cnt > 0 and wh_cnt == 0:
                return "ℹ️ Only LSI Jobs Assigned"
            elif lsi_cnt == 0 and wh_cnt > 0:
                return "ℹ️ Only WH Jobs Assigned"
            return "ℹ️ No BU Jobs Assigned"
            
        skill_df['Action Required'] = skill_df.apply(assign_flag, axis=1)
        skill_df = skill_df.sort_values(by='Eff Gap', ascending=False)
        show_skill = skill_df[['Name', 'Simple Installs Eff', 'Water Heaters Eff', 'Action Required']].rename(columns={
            'Simple Installs Eff': 'LSI Efficiency',
            'Water Heaters Eff': 'WH Efficiency'
        })
        
        def style_flags(row):
            if '⚠️' in row['Action Required']:
                return ['background-color: #fff3cd; color: #856404; font-weight: bold;'] * len(row)
            return [''] * len(row)
            
        try:
            st.dataframe(show_skill.reset_index(drop=True).style.hide(axis="index").apply(style_flags, axis=1), use_container_width=True)
        except:
            st.dataframe(show_skill.reset_index(drop=True).style.apply(style_flags, axis=1), use_container_width=True)
    else:
        st.info("No technicians found to generate a skills matrix table.")

    st.markdown("<br>", unsafe_allow_html=True)

    # === COACHING CORNER ===
    st.subheader("🏁 The Peer-to-Peer \"Coaching Corner\" Overlay")
    st.markdown("*(Anonymized mentor baseline layout stack comparing tech efficiency targets with Top 25% performers)*")
    lsi_top25 = final_df[final_df['LSI_Eff_Raw'] > 0]['LSI_Eff_Raw'].quantile(0.75) if not final_df[final_df['LSI_Eff_Raw'] > 0].empty else 100.0
    wh_top25 = final_df[final_df['WH_Eff_Raw'] > 0]['WH_Eff_Raw'].quantile(0.75) if not final_df[final_df['WH_Eff_Raw'] > 0].empty else 100.0
    coaching_data = pd.DataFrame()
    coaching_data['Name'] = final_df['Name']
    coaching_data['Your LSI Eff'] = final_df['Simple Installs Eff']
    coaching_data['Fleet Top 25% LSI'] = f"{lsi_top25:.1f}%"
    coaching_data['Your WH Eff'] = final_df['Water Heaters Eff']
    coaching_data['Fleet Top 25% WH'] = f"{wh_top25:.1f}%"
    st.dataframe(coaching_data, use_container_width=True)

    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
    # === DISPATCHER TOOLS SECTION ===
    st.header("🛠️ Dispatcher Tools (Daily Accountability & Planning)")
    
    # Best Fit Dispatch Recommender
    st.subheader("🧠 Best Fit Dispatch Recommender")
    st.markdown("*(Provides a sorted priority list for the dispatcher to assign last-minute emergency jobs based purely on isolated historical unit efficiencies)*")
    
    bf_col1, bf_col2 = st.columns(2)
    with bf_col1:
        st.markdown("**🥇 Top Ranked for LSI Jobs**")
        lsi_top = final_df[final_df['Simple_Installs_Count'] > 0].sort_values(by='LSI_Eff_Raw', ascending=False)
        if not lsi_top.empty:
            lsi_top['Jobs Run'] = lsi_top['Simple_Installs_Count'].astype(int)
            st.dataframe(lsi_top[['Name', 'Simple Installs Eff', 'Jobs Run']].reset_index(drop=True).rename(columns={'Simple Installs Eff': 'LSI Efficiency'}), use_container_width=True)
            
    with bf_col2:
        st.markdown("**🥇 Top Ranked for Water Heaters**")
        wh_top = final_df[final_df['Water_Heaters_Count'] > 0].sort_values(by='WH_Eff_Raw', ascending=False)
        if not wh_top.empty:
            wh_top['Jobs Run'] = wh_top['Water_Heaters_Count'].astype(int)
            st.dataframe(wh_top[['Name', 'Water Heaters Eff', 'Jobs Run']].reset_index(drop=True).rename(columns={'Water Heaters Eff': 'WH Efficiency'}), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    d_col1, d_col2 = st.columns(2)
    
    with d_col1:
        st.subheader("🕳️ 'Black Hole' Gap Finder")
        st.markdown("*(Gaps between jobs larger than 45 minutes)*")
        ops_sorted = ops_df.dropna(subset=['Earliest_Start']).sort_values(['Assigned Team Members', 'Earliest_Start'])
        ops_sorted['Next_Job_Start'] = ops_sorted.groupby(['Assigned Team Members', 'Short_Date'])['Earliest_Start'].shift(-1)
        ops_sorted['Gap_Hrs'] = (ops_sorted['Next_Job_Start'] - ops_sorted['Estimated_End']).dt.total_seconds() / 3600.0
        
        gaps_df = ops_sorted[ops_sorted['Gap_Hrs'] > 0.75].copy()
        if not gaps_df.empty:
            gaps_df = gaps_df.sort_values(by='Gap_Hrs', ascending=False)
            gaps_df['Gap Length'] = gaps_df['Gap_Hrs'].apply(format_hm)
            gaps_df['End of Job 1'] = gaps_df['Estimated_End'].dt.strftime('%I:%M %p')
            gaps_df['Start of Job 2'] = gaps_df['Next_Job_Start'].dt.strftime('%I:%M %p')
            show_gaps = gaps_df[['Assigned Team Members', 'Short_Date', 'End of Job 1', 'Start of Job 2', 'Gap Length']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
            st.dataframe(show_gaps, use_container_width=True)
        else:
            st.success("No major routing gaps detected!")

    with d_col2:
        st.subheader("🌅 First Job vs. Last Job")
        st.markdown("*(First punch of the morning, last punch of the afternoon. Spans over 9 hours are highlighted in red)*")
        bounds_sorted_df = bounds_df.sort_values(by='Total_Span_Hrs', ascending=False).copy()
        show_bounds = bounds_sorted_df[['Assigned Team Members', 'Short_Date', 'First Status Update', 'Last Status Update', 'Total Time']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
        
        def highlight_long_days(row):
            hrs = parse_hm(row['Total Time'])
            if hrs > 9.0:
                return ['background-color: #ffcccc; color: #990000;'] * len(row)
            return [''] * len(row)
            
        try:
            styled_bounds = show_bounds.reset_index(drop=True).style.hide(axis="index").apply(highlight_long_days, axis=1)
        except Exception:
            styled_bounds = show_bounds.reset_index(drop=True).style.apply(highlight_long_days, axis=1)
            
        st.dataframe(styled_bounds, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    colC, colD = st.columns(2)
    
    with colC:
        st.subheader("🛒 Lowe's Operational Delays")
        st.markdown("*(All logged store visits. Rows highlighted in red show specific jobs that took greater than 45 minutes)*")
        
        excessive_df = ops_df[ops_df['Store_Time_Hrs'] > 0.75].copy()
        total_delayed_store_hrs = excessive_df['Store_Time_Hrs'].sum()
        store_loss_cost = total_delayed_store_hrs * rate
        st.markdown(f"⏱️ **Total Field Hours Lost at Lowe's:** `{total_delayed_store_hrs:.1f} hrs` | 💸 **Cost of Store Inefficiencies:** `${store_loss_cost:,.2f}`")
        
        all_store_df = ops_df[ops_df['Store_Time_Hrs'] > 0].sort_values(by='Store_Time_Hrs', ascending=False).copy()
        
        if not all_store_df.empty:
            all_store_df['Store Time'] = all_store_df['Store_Time_Hrs'].apply(format_hm)
            show_store = all_store_df[['Assigned Team Members', 'Short_Date', 'Store Time']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
            
            def highlight_store_jobs(row):
                hrs = parse_hm(row['Store Time'])
                if hrs > 0.75:
                    return ['background-color: #ffcccc; color: #990000;'] * len(row)
                return [''] * len(row)
                
            try:
                styled_store = show_store.reset_index(drop=True).style.hide(axis="index").apply(highlight_store_jobs, axis=1)
            except Exception:
                styled_store = show_store.reset_index(drop=True).style.apply(highlight_store_jobs, axis=1)
            st.dataframe(styled_store, use_container_width=True)
        else:
            st.success("Great job! No store operational visits logged this week.")
            
    with colD:
        st.subheader("⏱️ Weekly Status Breakdown")
        st.markdown("*(Drive vs. Store vs. In Progress Time)*")
        breakdown_agg = ops_df.groupby('Assigned Team Members')[['Drive_Time_Hrs', 'Store_Time_Hrs', 'In_Progress_Time_Hrs']].sum().reset_index()
        breakdown_agg['Drive Time'] = breakdown_agg['Drive_Time_Hrs'].apply(format_hm)
        breakdown_agg['Store Time'] = breakdown_agg['Store_Time_Hrs'].apply(format_hm)
        breakdown_agg['In Progress Time'] = breakdown_agg['In_Progress_Time_Hrs'].apply(format_hm)
        show_breakdown = breakdown_agg[['Assigned Team Members', 'Drive Time', 'Store Time', 'In Progress Time']].rename(columns={'Assigned Team Members': 'Name'})
        st.dataframe(show_breakdown, use_container_width=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    colE, colF = st.columns(2)
    with colE:
        st.subheader("🔮 Predictive Planning")
        st.markdown("*(Average total turnaround time per job to help block future calendar schedules)*")
        avg_job_len = ops_df[ops_df['Total_Job_Time_Hours'] > 0].groupby('Assigned Team Members')['Total_Job_Time_Hours'].mean().reset_index()
        if not avg_job_len.empty:
            avg_job_len['Avg Total Job Length'] = avg_job_len['Total_Job_Time_Hours'].apply(format_hm)
            show_avg_len = avg_job_len[['Assigned Team Members', 'Avg Total Job Length']].rename(columns={'Assigned Team Members': 'Name'})
            st.dataframe(show_avg_len, use_container_width=True)
        else:
            st.info("No average job lengths to display.")

    with colF:
        st.subheader("🗺️ Route Optimization Flags")
        st.markdown("*(Days where greater than 40% of job time was driving. Shows Job Count, Drive Time, and Work Time for context)*")
        poor_routes = daily_route[daily_route['Drive %'] > 40.0].copy()
        
        if not poor_routes.empty:
            poor_routes['Drive %'] = poor_routes['Drive %'].apply(lambda x: f"{x:.1f}%")
            poor_routes['Drive Time'] = poor_routes['Drive_Time_Hrs'].apply(format_hm)
            poor_routes['Work Time'] = poor_routes['In_Progress_Time_Hrs'].apply(format_hm)
            
            show_poor_routes = poor_routes[['Assigned Team Members', 'Short_Date', 'Job_Count', 'Drive Time', 'Work Time', 'Drive %']].rename(columns={
                'Assigned Team Members': 'Name', 
                'Short_Date': 'Date',
                'Job_Count': 'Jobs'
            })
            st.dataframe(show_poor_routes, use_container_width=True)
        else:
            st.success("Great routing! No days hit greater than 40% drive time.")

    # === MORNING MOMENTUM DELAYED LAUNCH AUDIT ===
    st.markdown("<br>", unsafe_allow_html=True)
    launch_col, launch_empty_col = st.columns(2)
    
    with launch_col:
        st.subheader("📊 Late Deployment Scorecard")
        st.markdown("*(Total number of delayed launches tracked for each technician)*")
        if not delayed_launches_df.empty:
            launch_counts = delayed_launches_df.groupby('Assigned Team Members').size().reset_index(name='Total Late Days')
            launch_counts = launch_counts.sort_values(by='Total Late Days', ascending=False).rename(columns={'Assigned Team Members': 'Name'})
            try:
                styled_counts = launch_counts.reset_index(drop=True).style.hide(axis="index").set_properties(**{'background-color': '#fff3cd', 'color': '#856404;', 'font-weight': 'bold'})
            except Exception:
                styled_counts = launch_counts.reset_index(drop=True).style.set_properties(**{'background-color': '#fff3cd', 'color': '#856404;', 'font-weight': 'bold'})
            st.dataframe(styled_counts, use_container_width=True)
        else:
            st.info("No late deployment metrics to aggregate this week.")

    with launch_empty_col:
        st.subheader("🚗 Delayed Launch Alert (Morning Momentum Audit)")
        st.markdown("*(Select a tech from the dropdown to review late launch logs. Goals: **On The Way/Store by 8:00 AM**, **In Progress by 8:30 AM**)*")
        
        if not delayed_launches_df.empty:
            tech_late_list = sorted(delayed_launches_df['Assigned Team Members'].unique())
            selected_late_tech = st.selectbox("Select Tech to view launch times:", tech_late_list, key=f"late_launch_tech_select_{tab_key}")
            
            if selected_late_tech:
                tech_launches_df = delayed_launches_df[delayed_launches_df['Assigned Team Members'] == selected_late_tech].copy()
                tech_launches_df['First Launch'] = tech_launches_df['First_Punch'].dt.strftime('%I:%M %p') + " (" + tech_launches_df['First_Status'] + ")"
                show_launches = tech_launches_df.sort_values(by='First_Punch', ascending=False)[['Short_Date', 'First Launch']].rename(columns={
                    'Short_Date': 'Date'
                })
                try:
                    styled_launches = show_launches.reset_index(drop=True).style.hide(axis="index").set_properties(**{'background-color': '#ffcccc', 'color': '#990000;'})
                except Exception:
                    styled_launches = show_launches.reset_index(drop=True).style.set_properties(**{'background-color': '#ffcccc', 'color': '#990000;'})
                st.dataframe(styled_launches, use_container_width=True)
        else:
            st.success("Perfect deployment momentum! All technicians launched successfully on time.")
# ------------------------------

if time_file and ops_file:
    try:
        EXCLUDE_NAMES = [
            'Luis Ortiz', 
            'Roman Twardoz',
            'Dave Barber Show Low (Contactor)',
            'Oak Wrench AZ Jarrod Scully (Contractor)',
            'Presidio Plumbing Eric (Contractor)',
            'AtoZ Remodel LLC Ken (Contractor)',
            'Steve Walpole'
        ]
        
        # --- 1. Parse Time Sheet ---
        time_content = time_file.getvalue().decode("utf-8").splitlines()
        time_lines = time_content[1:] 
        
        data = []
        for i in range(0, len(time_lines), 9):
            if i + 8 < len(time_lines):
                name = time_lines[i].strip()
                sun = time_lines[i+1].strip()
                mon = time_lines[i+2].strip()
                tue = time_lines[i+3].strip()
                wed = time_lines[i+4].strip()
                thu = time_lines[i+5].strip()
                fri = time_lines[i+6].strip()
                sat = time_lines[i+7].strip()
                total = time_lines[i+8].strip()
                data.append([name, sun, mon, tue, wed, thu, fri, sat, total])
        
        time_df = pd.DataFrame(data, columns=['Name', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Total_Weekly'])
        time_df = time_df[~time_df['Name'].isin(EXCLUDE_NAMES)]
        
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        for col in days + ['Total_Weekly']:
            time_df[col + '_Clocked_Hrs'] = time_df[col].apply(parse_hm)
            
        time_df['Days_Worked'] = (time_df[[f'{d}_Clocked_Hrs' for d in days]] > 0).sum(axis=1)
        
        # --- 2. Parse Ops Sheet ---
        ops_df = pd.read_csv(ops_file, header=1)
        ops_df = ops_df.dropna(subset=['Assigned Team Members'])
        
        time_cols = [
            'Lowes Store - Completed Total Time in Status',
            'On The Way - Completed Total Time in Status',
            'In Progress - Completed Total Time in Status',
            'On The Way - Completed Total Time in Status.1',
            'In Progress - Completed Total Time in Status.1'
        ]
        
        for col in time_cols:
            if col in ops_df.columns:
                ops_df[col] = pd.to_numeric(ops_df[col], errors='coerce').fillna(0)
            else:
                ops_df[col] = 0
        
        ops_df['Store_Time_Hrs'] = ops_df['Lowes Store - Completed Total Time in Status'] / 3600.0
        ops_df['Drive_Time_Hrs'] = (ops_df['On The Way - Completed Total Time in Status'] + ops_df.get('On The Way - Completed Total Time in Status.1', 0)) / 3600.0
        ops_df['In_Progress_Time_Hrs'] = (ops_df['In Progress - Completed Total Time in Status'] + ops_df.get('In Progress - Completed Total Time in Status.1', 0)) / 3600.0
        ops_df['Total_Job_Time_Hours'] = ops_df[time_cols].sum(axis=1) / 3600.0
        
        if 'Total Invoice Amount' in ops_df.columns:
            ops_df['Total Invoice Amount'] = pd.to_numeric(ops_df['Total Invoice Amount'], errors='coerce').fillna(0.0)
        else:
            ops_df['Total Invoice Amount'] = 0.0
            
        unexploded_ops = ops_df.copy()
        
        ts_cols = [
            'Lowes Store - Start Timestamp',
            'On The Way - Start Timestamp',
            'In Progress - Start Timestamp',
            'On The Way - Start Timestamp.1',
            'In Progress - Start Timestamp.1'
        ]
        
        available_ts_cols = [c for c in ts_cols if c in ops_df.columns]
        ops_df['Job_Date'] = ops_df[available_ts_cols].bfill(axis=1).iloc[:, 0]
        
        for c in available_ts_cols:
            ops_df[c + '_dt'] = pd.to_datetime(ops_df[c].astype(str).str.split(' GMT').str[0], errors='coerce')
        
        available_ts_dt_cols = [c + '_dt' for c in available_ts_cols]
        ops_df['Earliest_Start'] = ops_df[available_ts_dt_cols].min(axis=1)
        
        def get_first_status_col(row):
            min_t = pd.NaT
            best_c = 'Unknown'
            for c in available_ts_dt_cols:
                t = row[c]
                if pd.notna(t):
                    if pd.isna(min_t) or t < min_t:
                        min_t = t
                        best_c = c
            return best_c

        ops_df['Earliest_Status_Col'] = ops_df.apply(get_first_status_col, axis=1)
        
        def map_status(col):
            if pd.isna(col): return 'Unknown'
            col = str(col)
            if 'Lowes Store' in col: return 'Lowes Store'
            if 'On The Way' in col: return 'On The Way'
            if 'In Progress' in col: return 'In Progress'
            return 'Unknown'
            
        ops_df['Earliest_Status'] = ops_df['Earliest_Status_Col'].apply(map_status)
        
        ops_df['Estimated_End'] = ops_df['Earliest_Start'] + pd.to_timedelta(ops_df['Total_Job_Time_Hours'] * 3600, unit='s')
        ops_df['Job_Date_Parsed'] = pd.to_datetime(ops_df['Job_Date'].astype(str).str.split(' GMT').str[0], errors='coerce')
        ops_df['Day_of_Week'] = ops_df['Job_Date_Parsed'].dt.day_name().str[:3]
        ops_df['Short_Date'] = ops_df['Job_Date_Parsed'].dt.strftime('%m-%d-%Y')
        
        ops_df['Assigned Team Members'] = ops_df['Assigned Team Members'].astype(str).str.split(',')
        ops_df = ops_df.explode('Assigned Team Members')
        ops_df['Assigned Team Members'] = ops_df['Assigned Team Members'].str.strip()
        ops_df = ops_df[~ops_df['Assigned Team Members'].isin(EXCLUDE_NAMES)]
        
        # --- NEW PIPELINE LOGIC: Parse Business Units & Job Counts per Unit ---
        if 'Business Unit' in ops_df.columns:
            bu_agg = ops_df.groupby(['Assigned Team Members', 'Business Unit']).agg(
                Total_Job_Time_Hours=('Total_Job_Time_Hours', 'sum'),
                BU_Job_Count=('Total_Job_Time_Hours', 'size')
            ).reset_index()
            
            bu_pivot_hrs = bu_agg.pivot(index='Assigned Team Members', columns='Business Unit', values='Total_Job_Time_Hours').reset_index().fillna(0)
            bu_pivot_cnt = bu_agg.pivot(index='Assigned Team Members', columns='Business Unit', values='BU_Job_Count').reset_index().fillna(0)
            
            bu_pivot = pd.merge(bu_pivot_hrs, bu_pivot_cnt, on='Assigned Team Members', suffixes=('_hrs', '_cnt'))
            bu_pivot = bu_pivot.rename(columns={'Assigned Team Members': 'Name'})
            
            for col in ['Lowes - Simple Installs_hrs', 'Lowes - Water Heaters_hrs', 'Lowes - Simple Installs_cnt', 'Lowes - Water Heaters_cnt']:
                if col not in bu_pivot.columns:
                    bu_pivot[col] = 0.0
                    
            bu_pivot = bu_pivot.rename(columns={
                'Lowes - Simple Installs_hrs': 'Simple_Installs_Hrs',
                'Lowes - Water Heaters_hrs': 'Water_Heaters_Hrs',
                'Lowes - Simple Installs_cnt': 'Simple_Installs_Count',
                'Lowes - Water Heaters_cnt': 'Water_Heaters_Count'
            })
        else:
            bu_pivot = pd.DataFrame(columns=['Name', 'Simple_Installs_Hrs', 'Water_Heaters_Hrs', 'Simple_Installs_Count', 'Water_Heaters_Count'])

        job_time_agg = ops_df.groupby(['Assigned Team Members', 'Day_of_Week'])['Total_Job_Time_Hours'].sum().reset_index()
        job_time_pivot = job_time_agg.pivot(index='Assigned Team Members', columns='Day_of_Week', values='Total_Job_Time_Hours').reset_index()
        job_time_pivot = job_time_pivot.rename(columns={'Assigned Team Members': 'Name'}).fillna(0)
        
        for day in days:
            if day not in job_time_pivot.columns:
                job_time_pivot[day] = 0.0
        
        rename_dict = {day: day + '_Job_Hrs' for day in days}
        job_time_pivot = job_time_pivot.rename(columns=rename_dict)
        job_time_pivot['Total_Weekly_Job_Hrs'] = job_time_pivot[[d + '_Job_Hrs' for d in days]].sum(axis=1)
        
        job_count_agg = ops_df.groupby(['Assigned Team Members', 'Day_of_Week']).size().reset_index(name='Job_Count')
        job_count_pivot = job_count_agg.pivot(index='Assigned Team Members', columns='Day_of_Week', values='Job_Count').reset_index()
        job_count_pivot = job_count_pivot.rename(columns={'Assigned Team Members': 'Name'}).fillna(0)
        
        for day in days:
            if day not in job_count_pivot.columns:
                job_count_pivot[day] = 0
                
        rename_dict_counts = {day: day + '_Job_Count' for day in days}
        job_count_pivot = job_count_pivot.rename(columns=rename_dict_counts)
        job_count_pivot['Total_Weekly_Job_Count'] = job_count_pivot[[d + '_Job_Count' for d in days]].sum(axis=1)
        
        daily_route = ops_df.groupby(['Assigned Team Members', 'Short_Date']).agg(
            Drive_Time_Hrs=('Drive_Time_Hrs', 'sum'),
            In_Progress_Time_Hrs=('In_Progress_Time_Hrs', 'sum'),
            Total_Job_Time_Hours=('Total_Job_Time_Hours', 'sum'),
            Job_Count=('Total_Job_Time_Hours', 'size')
        ).reset_index()
        
        daily_route = daily_route[daily_route['Total_Job_Time_Hours'] > 0].copy()
        daily_route['Drive %'] = (daily_route['Drive_Time_Hrs'] / daily_route['Total_Job_Time_Hours']) * 100
        
        final_df = pd.merge(time_df, job_time_pivot, on='Name', how='left').fillna(0)
        final_df = pd.merge(final_df, job_count_pivot, on='Name', how='left').fillna(0)
        
        if not bu_pivot.empty:
            final_df = pd.merge(final_df, bu_pivot[['Name', 'Simple_Installs_Hrs', 'Water_Heaters_Hrs', 'Simple_Installs_Count', 'Water_Heaters_Count']], on='Name', how='left').fillna(0)
        else:
            final_df['Simple_Installs_Hrs'] = 0.0
            final_df['Water_Heaters_Hrs'] = 0.0
            final_df['Simple_Installs_Count'] = 0.0
            final_df['Water_Heaters_Count'] = 0.0
            
        tech_rev_agg = ops_df.groupby('Assigned Team Members')['Total Invoice Amount'].sum().reset_index()
        tech_rev_agg.columns = ['Name', 'Total_Assigned_Revenue']
        final_df = pd.merge(final_df, tech_rev_agg, on='Name', how='left').fillna(0.0)
        
        final_df['Rev_Per_Clocked_Hr'] = np.where(
            final_df['Total_Weekly_Clocked_Hrs'] > 0,
            final_df['Total_Assigned_Revenue'] / final_df['Total_Weekly_Clocked_Hrs'],
            0.0
        )
            
        st.sidebar.header("🔧 Job Status Time Adjustments")
        st.sidebar.markdown("*(Correct tech hours if they hit a job status too early or late)*")
        st.sidebar.markdown("**Rules:** Use positive numbers like `1:30` or `0:45` to add time. Use a minus sign like `-1:15` or `-0:30` to subtract time.")
        
        global_adj_str = st.sidebar.text_input("🌍 Global Adj for ALL Techs (HH:MM)", value="0:00", key="global_adj")
        global_adj_hrs = parse_adj_hm(global_adj_str)
        
        adjustments = {}
        for tech in sorted(final_df['Name'].unique()):
            adj_str = st.sidebar.text_input(f"{tech} Adj (HH:MM)", value="0:00", key=f"adj_{tech}")
            adjustments[tech] = parse_adj_hm(adj_str) + global_adj_hrs
            
        final_df['Adjustment_Hrs'] = final_df['Name'].map(adjustments).fillna(0.0)
        final_df['Total_Weekly_Job_Hrs'] = final_df['Total_Weekly_Job_Hrs'] + final_df['Adjustment_Hrs']
        
        display_dfs = {}
        for day in days:
            diff_col = day + '_Diff_Hrs'
            final_df[diff_col] = final_df[day + '_Clocked_Hrs'] - final_df[day + '_Job_Hrs']
            
            final_df[f'{day} Jobs'] = final_df[day + '_Job_Count'].astype(int)
            final_df[f'{day} Clocked'] = final_df[day + '_Clocked_Hrs'].apply(format_hm)
            final_df[f'{day} Job Time'] = final_df[day + '_Job_Hrs'].apply(format_hm)
            final_df[f'{day} Diff'] = final_df[diff_col].apply(format_hm)
            
            day_df = pd.DataFrame()
            day_df['Name'] = final_df['Name']
            day_df[f'{day} Jobs'] = final_df[f'{day} Jobs']
            day_df[f'{day} Clocked'] = final_df[f'{day} Clocked']
            day_df[f'{day} Job Time'] = final_df[f'{day} Job Time']
            day_df[f'{day} Diff'] = final_df[f'{day} Diff']
            display_dfs[day] = day_df
            
        manager_cols = ['Name']
        diff_cols_for_style = []
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            manager_cols.extend([f'{d} Jobs', f'{d} Clocked', f'{d} Job Time', f'{d} Diff'])
            diff_cols_for_style.append(f'{d} Diff')
            
        manager_df = final_df[manager_cols]
        display_dfs['Manager'] = manager_df
        
        final_df['Total_Weekly_Diff_Hrs'] = final_df['Total_Weekly_Clocked_Hrs'] - final_df['Total_Weekly_Job_Hrs']
        
        final_df['Daily_Avg_Diff_Hrs'] = np.where(final_df['Days_Worked'] > 0, final_df['Total_Weekly_Diff_Hrs'] / final_df['Days_Worked'], 0.0)
        
        # --- BU ISOLATED EFFICIENCY CALCULATION ENGINE (WEIGHTED GOALS) ---
        final_df['LSI_Goal_Hrs'] = final_df['Simple_Installs_Count'] * 2.0
        final_df['WH_Goal_Hrs'] = final_df['Water_Heaters_Count'] * (3 + (25 / 60.0))
        final_df['Total_Goal_Hrs'] = final_df['LSI_Goal_Hrs'] + final_df['WH_Goal_Hrs']
        
        final_df['Assumed_LSI_Clocked'] = np.where(final_df['Total_Goal_Hrs'] > 0, final_df['Total_Weekly_Clocked_Hrs'] * (final_df['LSI_Goal_Hrs'] / final_df['Total_Goal_Hrs']), 0.0)
        final_df['Assumed_WH_Clocked'] = np.where(final_df['Total_Goal_Hrs'] > 0, final_df['Total_Weekly_Clocked_Hrs'] * (final_df['WH_Goal_Hrs'] / final_df['Total_Goal_Hrs']), 0.0)
        
        final_df['LSI_Eff_Raw'] = np.where(final_df['Assumed_LSI_Clocked'] > 0, (final_df['Simple_Installs_Hrs'] / final_df['Assumed_LSI_Clocked']) * 100, 0.0)
        final_df['WH_Eff_Raw'] = np.where(final_df['Assumed_WH_Clocked'] > 0, (final_df['Water_Heaters_Hrs'] / final_df['Assumed_WH_Clocked']) * 100, 0.0)
        
        final_df['Total_Eff'] = np.where(final_df['Total_Weekly_Clocked_Hrs'] > 0, (final_df['Total_Weekly_Job_Hrs'] / final_df['Total_Weekly_Clocked_Hrs']) * 100, 0.0)
        
        final_df['Simple Installs'] = final_df['Simple_Installs_Hrs'].apply(format_hm)
        final_df['Water Heaters'] = final_df['Water_Heaters_Hrs'].apply(format_hm)
        final_df['Simple Installs Eff'] = final_df['LSI_Eff_Raw'].apply(lambda x: f"{x:.1f}%")
        final_df['Water Heaters Eff'] = final_df['WH_Eff_Raw'].apply(lambda x: f"{x:.1f}%")
        final_df['Total Eff'] = final_df['Total_Eff'].apply(lambda x: f"{x:.1f}%")
        
        final_df = final_df.sort_values(by='WH_Eff_Raw', ascending=False)
        
        bu_summary_df = pd.DataFrame()
        bu_summary_df['Name'] = final_df['Name']
        bu_summary_df['Total Clocked'] = final_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
        bu_summary_df['Total Jobs'] = final_df['Total_Weekly_Job_Count'].astype(int)
        
        bu_summary_df['LSI Jobs'] = final_df['Simple_Installs_Count'].astype(int)
        bu_summary_df['LSI Job Status Time'] = final_df['Simple_Installs_Hrs'].apply(format_hm)
        bu_summary_df['LSI Assumed Clocked'] = final_df['Assumed_LSI_Clocked'].apply(format_hm)
        bu_summary_df['LSI Efficiency'] = final_df['Simple Installs Eff']
        
        bu_summary_df['WH Jobs'] = final_df['Water_Heaters_Count'].astype(int)
        bu_summary_df['WH Job Status Time'] = final_df['Water_Heaters_Hrs'].apply(format_hm)
        bu_summary_df['WH Assumed Clocked'] = final_df['Assumed_WH_Clocked'].apply(format_hm)
        bu_summary_df['WH Efficiency'] = final_df['Water Heaters Eff']

        bu_summary_df['Total Efficiency'] = final_df['Total Eff']
        
        display_dfs['Weekly'] = bu_summary_df
        
        export_df = pd.DataFrame()
        export_df['Name'] = final_df['Name']
        export_df['Days Worked'] = final_df['Days_Worked']
        export_df['Total Clocked'] = final_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
        export_df['Total Job Time'] = final_df['Total_Weekly_Job_Hrs'].apply(format_hm)
        export_df['Manual Adj'] = final_df['Adjustment_Hrs'].apply(format_hm)
        export_df['Daily Avg Diff'] = final_df['Daily_Avg_Diff_Hrs'].apply(format_hm) 
        export_df['Total Diff'] = final_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            export_df[f'{d} Diff'] = final_df[f'{d} Diff']
        
        export_df['LSI Job Hours'] = final_df['Simple Installs']
        export_df['LSI Efficiency %'] = final_df['Simple Installs Eff']
        export_df['WH Job Hours'] = final_df['Water Heaters']
        export_df['WH Efficiency %'] = final_df['Water Heaters Eff']
        
        ops_sorted = ops_df.dropna(subset=['Earliest_Start']).sort_values(['Assigned Team Members', 'Earliest_Start'])
        ops_sorted['Next_Job_Start'] = ops_sorted.groupby(['Assigned Team Members', 'Short_Date'])['Earliest_Start'].shift(-1)
        ops_sorted['Gap_Hrs'] = (ops_sorted['Next_Job_Start'] - ops_sorted['Estimated_End']).dt.total_seconds() / 3600.0
        
        bounds_df = ops_sorted.groupby(['Assigned Team Members', 'Short_Date']).agg(
            First_Punch=('Earliest_Start', 'min'),
            Last_Punch=('Estimated_End', 'max'),
            First_Status=('Earliest_Status', 'first')
        ).reset_index()
        bounds_df['First Status Update'] = bounds_df['First_Punch'].dt.strftime('%I:%M %p')
        bounds_df['Last Status Update'] = bounds_df['Last_Punch'].dt.strftime('%I:%M %p')
        bounds_df['Total_Span_Hrs'] = (bounds_df['Last_Punch'] - bounds_df['First_Punch']).dt.total_seconds() / 3600.0
        bounds_df['Total Time'] = bounds_df['Total_Span_Hrs'].apply(format_hm)
        
        def check_late(row):
            fp = row['First_Punch']
            status = row['First_Status']
            if pd.isna(fp): return False
            if status in ['On The Way', 'Lowes Store']:
                return fp.hour >= 8
            elif status == 'In Progress':
                return fp.hour > 8 or (fp.hour == 8 and fp.minute >= 30)
            return False
            
        delayed_launches_df = bounds_df[bounds_df.apply(check_late, axis=1)].copy()
        
        st.success("Files processed successfully!")
        
        # --- 4. Display Results in Tabs ---
        tab_names = ["Weekly Summary", "Manager Overview", "Individual Tech Report", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "🧪 Test Section"]
        tabs = st.tabs(tab_names)
        
        with tabs[0]:
            st.markdown('<h3 class="hide-on-print">Weekly Efficiency Summary</h3>', unsafe_allow_html=True)
            st.markdown("*(Efficiency is calculated by weighting total clocked hours against specific task goals: **Water Heaters = 3:25 hrs**, **LSI = 2:00 hrs**)*")
            
            styled_weekly = display_dfs['Weekly'].reset_index(drop=True).style.set_properties(
                **{'background-color': '#fff3cd', 'font-weight': 'bold', 'color': '#856404'}, subset=['WH Efficiency']
            )
            st.dataframe(styled_weekly, use_container_width=True)
            show_advanced_reporting(ops_df, final_df, export_df, bounds_df, delayed_launches_df, daily_route, tab_key="summary_tab")
            
        with tabs[1]:
            st.markdown('<h3 class="hide-on-print">Manager Overview - All Techs</h3>', unsafe_allow_html=True)
            st.markdown('<p class="hide-on-print"><em>Scroll down to see the breakdown for every technician.</em></p>', unsafe_allow_html=True)
            
            tech_list = final_df['Name'].unique()
            for tech in tech_list:
                st.markdown(f"#### **{tech}**")
                tech_data = final_df[final_df['Name'] == tech].iloc[0]
                tech_days_worked = tech_data['Days_Worked']
                
                report_data = []
                day_mapping_long = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
                for full_day, short_day in day_mapping_long.items():
                    report_data.append({
                        "Day": full_day,
                        "Jobs": int(tech_data[short_day + '_Job_Count']),
                        "Clocked Time": format_hm(tech_data[short_day + '_Clocked_Hrs']),
                        "Job Time": format_hm(tech_data[short_day + '_Job_Hrs']),
                        "Difference": format_hm(tech_data[short_day + '_Diff_Hrs'])
                    })
                
                report_data.append({
                    "Day": "TOTAL WEEKLY",
                    "Jobs": int(tech_data['Total_Weekly_Job_Count']),
                    "Clocked Time": format_hm(tech_data['Total_Weekly_Clocked_Hrs']),
                    "Job Time": format_hm(tech_data['Total_Weekly_Job_Hrs']),
                    "Difference": format_hm(tech_data['Total_Weekly_Diff_Hrs'])
                })
                
                report_df = pd.DataFrame(report_data)
                try:
                    styled_report = report_df.reset_index(drop=True).style.hide(axis="index").apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                except Exception:
                    try:
                        styled_report = report_df.reset_index(drop=True).style.hide_index().apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                    except:
                        styled_report = report_df.reset_index(drop=True).style.apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                st.table(styled_report)
                st.markdown(f"**Business Unit Efficiency Breakdown:** LSI: `{tech_data['Simple Installs']}` hrs ({tech_data['Simple Installs Eff']}) &nbsp;&nbsp;|&nbsp;&nbsp; Water Heaters: `{tech_data['Water Heaters']}` hrs ({tech_data['Water Heaters Eff']})")
                st.markdown("---")
            
            show_advanced_reporting(ops_df, final_df, export_df, bounds_df, delayed_launches_df, daily_route, tab_key="manager_tab")
            
        with tabs[2]:
            st.markdown('<h3 class="hide-on-print">Printable Individual Report</h3>', unsafe_allow_html=True)
            tech_list = final_df['Name'].unique()
            selected_tech = st.selectbox("Select a Technician:", tech_list)
            
            if selected_tech:
                st.markdown(f"### Time Report for: **{selected_tech}**")
                st.markdown('<p class="hide-on-print"><em>(Tip: To print this report for the technician, press <strong>Ctrl + P</strong> or <strong>Cmd + P</strong>)</em></p>', unsafe_allow_html=True)
                tech_data = final_df[final_df['Name'] == selected_tech].iloc[0]
                tech_days_worked = tech_data['Days_Worked']
                
                report_data = []
                day_mapping_long = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
                for full_day, short_day in day_mapping_long.items():
                    report_data.append({
                        "Day": full_day,
                        "Jobs": int(tech_data[short_day + '_Job_Count']),
                        "Clocked Time": format_hm(tech_data[short_day + '_Clocked_Hrs']),
                        "Job Time": format_hm(tech_data[short_day + '_Job_Hrs']),
                        "Difference": format_hm(tech_data[short_day + '_Diff_Hrs'])
                    })
                
                report_data.append({
                    "Day": "TOTAL WEEKLY",
                    "Jobs": int(tech_data['Total_Weekly_Job_Count']),
                    "Clocked Time": format_hm(tech_data['Total_Weekly_Clocked_Hrs']),
                    "Job Time": format_hm(tech_data['Total_Weekly_Job_Hrs']),
                    "Difference": format_hm(tech_data['Total_Weekly_Diff_Hrs'])
                })
                
                report_df = pd.DataFrame(report_data)
                try:
                    styled_report = report_df.reset_index(drop=True).style.hide(axis="index").apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                except Exception:
                    try:
                        styled_report = report_df.reset_index(drop=True).style.hide_index().apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                    except:
                        styled_report = report_df.reset_index(drop=True).style.apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                st.table(styled_report)
                
                a_col, b_col = st.columns(2)
                with a_col:
                    st.markdown(f"**Total Days Clocked In:** {tech_days_worked}")
                with b_col:
                    st.markdown(f"**LSI (Simple Installs):** `{tech_data['Simple Installs']}` hrs ({tech_data['Simple Installs Eff']})  \n**Water Heaters:** `{tech_data['Water Heaters']}` hrs ({tech_data['Water Heaters Eff']})")

        day_mapping = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
        for i, full_day in enumerate(tab_names[3:10]): 
            with tabs[i+3]:
                short_day = day_mapping[full_day]
                st.markdown(f'<h3 class="hide-on-print">{full_day} Breakdown</h3>', unsafe_allow_html=True)
                try:
                    styled_daily = display_dfs[short_day].reset_index(drop=True).style.map(highlight_daily, subset=[f'{short_day} Diff'])
                except AttributeError:
                    styled_daily = display_dfs[short_day].reset_index(drop=True).style.applymap(highlight_daily, subset=[f'{short_day} Diff'])
                st.dataframe(styled_daily, use_container_width=True)

        with tabs[10]:
            st.header("🧪 Isolated Leaderboard Sandbox")
            st.markdown("Use the selections below to add, remove, or evaluate components without changing the data models in other sections.")
            
            # UPDATED: Replaced three individual selections with the unified compound "📊 Macro Financial Performance Dashboard" option
            test_choices = st.multiselect(
                "Select active data views to mount inside Test Section:",
                [
                    "🏆 The \"Golden Ratio\" Margin Predictor",
                    "🔄 The \"Context-Switching\" Penalty Alert",
                    "🕵️ The \"Ghost Punch\" & Payroll Discrepancy Auditor",
                    "🏬 The Lowe's Store Staging Efficiency Scorecard",
                    "📊 Macro Financial Performance Dashboard",
                    "📊 Business Unit Revenue Velocity",
                    "🏆 Top Revenue Producer Leaderboard"
                ],
                default=["🏆 The \"Golden Ratio\" Margin Predictor"],
                key="sandbox_view_choices"
            )

            if "🏆 The \"Golden Ratio\" Margin Predictor" in test_choices:
                st.markdown("### **🏆 The Golden Ratio Margin Predictor**")
                st.markdown("*(Simulates the division's average efficiency based on the ratio of Water Heaters to Simple Installs scheduled that day)*")
                
                golden_data = []
                for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                    day_clocked = final_df[f'{d}_Clocked_Hrs'].sum()
                    day_job = final_df[f'{d}_Job_Hrs'].sum()
                    day_eff = (day_job / day_clocked * 100) if day_clocked > 0 else 0.0
                    
                    day_lsi = ops_df[(ops_df['Day_of_Week'] == d) & (ops_df['Business Unit'] == 'Lowes - Simple Installs')].shape[0]
                    day_wh = ops_df[(ops_df['Day_of_Week'] == d) & (ops_df['Business Unit'] == 'Lowes - Water Heaters')].shape[0]
                    total_bu = day_lsi + day_wh
                    lsi_ratio = (day_lsi / total_bu * 100) if total_bu > 0 else 0
                    
                    if total_bu > 0:
                        profile = "Heavy LSI (>60% LSI)" if lsi_ratio > 60 else ("Heavy WH (<40% LSI)" if lsi_ratio < 40 else "Balanced (40-60%)")
                        golden_data.append({
                            "Day": d,
                            "LSI Jobs": day_lsi,
                            "WH Jobs": day_wh,
                            "LSI Mix %": f"{lsi_ratio:.1f}%",
                            "Daily Efficiency": day_eff,
                            "Profile": profile
                        })
                
                if golden_data:
                    golden_df = pd.DataFrame(golden_data)
                    golden_summary = golden_df.groupby('Profile').agg(
                        Days=('Day', 'count'),
                        Avg_Efficiency=('Daily Efficiency', 'mean')
                    ).reset_index()
                    golden_summary['Avg Efficiency'] = golden_summary['Avg_Efficiency'].apply(lambda x: f"{x:.1f}%")
                    
                    golden_df['Daily Efficiency'] = golden_df['Daily Efficiency'].apply(lambda x: f"{x:.1f}%")
                    
                    g_col1, g_col2 = st.columns(2)
                    with g_col1:
                        st.markdown("**Performance by Daily Mix Strategy**")
                        st.dataframe(golden_summary[['Profile', 'Days', 'Avg Efficiency']], use_container_width=True)
                    with g_col2:
                        st.markdown("**Raw Daily Breakdown**")
                        st.dataframe(golden_df[['Day', 'LSI Mix %', 'Profile', 'Daily Efficiency']], use_container_width=True)
                else:
                    st.info("No business unit ratios calculated for this week.")

            if "🔄 The \"Context-Switching\" Penalty Alert" in test_choices:
                st.markdown("### **🔄 Context-Switching Penalty Alert**")
                st.markdown("*(Compares route durations on days where a tech did ONLY one job type (Uniform Route) vs days where they had to switch back and forth between LSI and WH (Mixed Route))*")
                
                if 'Business Unit' in ops_df.columns:
                    daily_bu = ops_df.groupby(['Assigned Team Members', 'Short_Date', 'Business Unit']).size().unstack(fill_value=0).reset_index()
                    if 'Lowes - Simple Installs' not in daily_bu.columns: daily_bu['Lowes - Simple Installs'] = 0
                    if 'Lowes - Water Heaters' not in daily_bu.columns: daily_bu['Lowes - Water Heaters'] = 0
                    
                    daily_bu['Day Type'] = np.where((daily_bu['Lowes - Simple Installs'] > 0) & (daily_bu['Lowes - Water Heaters'] > 0), 'Mixed Route (Both)', 'Uniform Route (One Type)')
                    
                    daily_merged = pd.merge(daily_route, daily_bu, on=['Assigned Team Members', 'Short_Date'])
                    daily_merged['Avg Job Time'] = daily_merged['Total_Job_Time_Hours'] / daily_merged['Job_Count']
                    
                    context_agg = daily_merged.groupby('Day Type').agg(
                        Total_Days=('Short_Date', 'count'),
                        Avg_Job_Turnaround=('Avg Job Time', 'mean')
                    ).reset_index()
                    
                    if not context_agg.empty:
                        context_agg['Average Fleet Job Turnaround'] = context_agg['Avg_Job_Turnaround'].apply(format_hm)
                        st.dataframe(context_agg[['Day Type', 'Total_Days', 'Average Fleet Job Turnaround']].rename(columns={'Total_Days': 'Days Analyzed'}), use_container_width=True)
                    else:
                        st.info("Could not calculate context-switching averages for this set.")

            if "🕵️ The \"Ghost Punch\" & Payroll Discrepancy Auditor" in test_choices:
                st.markdown("### **🕵️ The \"Ghost Punch\" & Payroll Discrepancy Auditor**")
                st.markdown("*(Scans files day-by-day to cross-verify paid hours against active field activity timestamps)*")
                ghost_alerts = []
                for idx, row in final_df.iterrows():
                    tech_name = row['Name']
                    nl = tech_name.lower()
                    pay_type = "Hourly"
                    if "sean marble" in nl or "michael owens" in nl: pay_type = "Salary"
                    elif "bryan" in nl or "erik" in nl: pay_type = "Piece Rate"
                    
                    for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                        clocked = row[f'{d}_Clocked_Hrs']
                        jobs = row[f'{d}_Job_Count']
                        if clocked > 0 and jobs == 0:
                            ghost_alerts.append({"Technician": tech_name, "Pay Profile": pay_type, "Day": d, "Audit Type": "🕵️ Paid But Idle (Clocked In, 0 Jobs Run)", "Clocked Hours": format_hm(clocked), "Jobs Done": 0})
                        elif clocked == 0 and jobs > 0:
                            ghost_alerts.append({"Technician": tech_name, "Pay Profile": pay_type, "Day": d, "Audit Type": "🚨 Unpaid Field Work (0 Hours Clocked, Jobs Run)", "Clocked Hours": format_hm(clocked), "Jobs Done": int(jobs)})
                if ghost_alerts:
                    st.dataframe(pd.DataFrame(ghost_alerts), use_container_width=True)
                else:
                    st.success("Perfect alignment! No payroll discrepancy errors detected on current sheets.")

            if "🏬 The Lowe's Store Staging Efficiency Scorecard" in test_choices:
                st.markdown("### **🏬 The Lowe\'s Store Staging Efficiency Scorecard**")
                st.markdown("*(Aggregates total field loading bottlenecks across individual store numbers to isolate supplier staging friction)*")
                store_cols = [c for c in ops_df.columns if 'store' in c.lower() and 'time' not in c.lower() and 'timestamp' not in c.lower() and 'start' not in c.lower()]
                if store_cols:
                    s_col = store_cols[0]
                    store_stats = ops_df.groupby(s_col)['Store_Time_Hrs'].mean().reset_index()
                    store_stats.columns = ['Store Identifier', 'Avg Delay Length (Hrs)']
                    store_stats['Avg Delay Length'] = store_stats['Avg Delay Length (Hrs)'].apply(format_hm)
                    st.dataframe(store_stats.sort_values(by='Avg Delay Length (Hrs)', ascending=False)[['Store Identifier', 'Avg Delay Length']], use_container_width=True)
                else:
                    store_stats = pd.DataFrame([
                        {"Store Identifier": "Lowe's Store #1042 (Sample Baseline Row)", "Avg Delay Length": "0:55"},
                        {"Store Identifier": "Lowe's Store #0844 (Sample Baseline Row)", "Avg Delay Length": "0:15"}
                    ])
                    st.dataframe(store_stats, use_container_width=True)

            # UPDATED: NEW CONSOLIDATED INTERFACE SECTION (Combines Total Gross Volume, Average Ticket Size, and Yield Per Hour)
            if "📊 Macro Financial Performance Dashboard" in test_choices:
                st.markdown("### **📊 Macro Financial Performance Dashboard**")
                st.markdown("*(Unified executive layout tracking top-line volume, individual task velocity, and asset allocation yield)*")
                
                m_col1, m_col2 = st.columns([1, 2])
                with m_col1:
                    total_rev = unexploded_ops['Total Invoice Amount'].sum()
                    st.metric(label="Division Gross Invoiced Volume", value=f"${total_rev:,.2f}")
                    
                    st.markdown("<br>**🎯 Average Ticket Size per BU**", unsafe_allow_html=True)
                    bu_avg_ticket = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].mean().reset_index()
                    bu_avg_ticket.columns = ['Business Unit', 'Average Ticket Size Raw']
                    bu_avg_ticket['Average Ticket Size'] = bu_avg_ticket['Average Ticket Size Raw'].apply(lambda x: f"${x:,.2f}")
                    st.dataframe(bu_avg_ticket[['Business Unit', 'Average Ticket Size']].reset_index(drop=True), use_container_width=True)
                    
                with m_col2:
                    st.markdown("**📈 Gross Revenue per Clocked Hour**")
                    rev_per_hour_df = final_df.copy()
                    rev_per_hour_df['Total Clocked'] = rev_per_hour_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
                    rev_per_hour_df['Gross Revenue / Clocked Hour'] = rev_per_hour_df.apply(
                        lambda r: f"${r['Rev_Per_Clocked_Hr']:.2f}/hr" if r['Total_Weekly_Clocked_Hrs'] > 0 else "-", axis=1
                    )
                    rev_per_hour_df['Total Assigned Value'] = rev_per_hour_df['Total_Assigned_Revenue'].apply(lambda x: f"${x:,.2f}")
                    show_rev_per_hour = rev_per_hour_df.sort_values(by='Rev_Per_Clocked_Hr', ascending=False)[
                        ['Name', 'Total Clocked', 'Total Assigned Value', 'Gross Revenue / Clocked Hour']
                    ]
                    st.dataframe(show_rev_per_hour.reset_index(drop=True), use_container_width=True)

            if "📊 Business Unit Revenue Velocity" in test_choices:
                st.markdown("### **📊 Business Unit Revenue Velocity**")
                st.markdown("*(Measures core revenue velocity distributions across plumbing vs appliance business channels)*")
                total_rev = unexploded_ops['Total Invoice Amount'].sum()
                bu_rev = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].sum().reset_index()
                bu_rev['Revenue Share %'] = np.where(total_rev > 0, (bu_rev['Total Invoice Amount'] / total_rev) * 100, 0.0)
                bu_rev['Total Revenue'] = bu_rev['Total Invoice Amount'].apply(lambda x: f"${x:,.2f}")
                bu_rev['Revenue Share %'] = bu_rev['Revenue Share %'].apply(lambda x: f"{x:.1f}%")
                st.dataframe(bu_rev[['Business Unit', 'Total Revenue', 'Revenue Share %']].reset_index(drop=True), use_container_width=True)

            if "🏆 Top Revenue Producer Leaderboard" in test_choices:
                st.markdown("### **🏆 Top Revenue Producer Leaderboard**")
                st.markdown("*(Ranks all active technicians cleanly by raw dollar value injected into division gross accounts)*")
                leaderboard_rev = final_df.sort_values(by='Total_Assigned_Revenue', ascending=False).copy()
                leaderboard_rev['Total Clocked'] = leaderboard_rev['Total_Weekly_Clocked_Hrs'].apply(format_hm)
                leaderboard_rev['Total Assigned Revenue'] = leaderboard_rev['Total_Assigned_Revenue'].apply(lambda x: f"${x:,.2f}")
                leaderboard_rev['Total Jobs'] = leaderboard_rev['Total_Weekly_Job_Count'].astype(int)
                show_leaderboard_rev = leaderboard_rev[['Name', 'Total Jobs', 'Total Clocked', 'Total Assigned Revenue']]
                st.dataframe(show_leaderboard_rev.reset_index(drop=True), use_container_width=True)
            
    except Exception as e:
        st.error(f"An error occurred while processing the files: Please ensure you uploaded the correct CSV formats. Exact error: {e}")
