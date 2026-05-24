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

# --- GLOBAL HELPER & HIGHLIGHTING FUNCTIONS ---
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

def parse_hm(time_str):
    if pd.isna(time_str) or time_str == '-' or time_str == '':
        return 0.0
    try:
        clean_str = str(time_str).strip().rstrip(',').strip('"')
        parts = clean_str.split(':')
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h + m / 60.0
    except:
        return 0.0

def parse_adj_hm(val_str):
    val_str = str(val_str).strip()
    if not val_str or val_str == '-' or val_str == '0' or val_str == '0:00':
        return 0.0
    try:
        sign = -1 if val_str.startswith('-') else 1
        clean_val = val_str.lstrip('+-').rstrip(',').strip('"')
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
        clean_val = str(val).replace('-', '').rstrip(',').strip('"')
        if ':' in clean_val:
            parts = clean_val.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return sign * (h + m / 60.0)
    except:
        pass
    return 0.0

def check_late(row):
    fp = row['First_Punch']
    status = row['First_Status']
    if pd.isna(fp): return False
    if status in ['On The Way', 'Lowes Store']:
        return fp.hour >= 8
    elif status == 'In Progress':
        return fp.hour > 8 or (fp.hour == 8 and fp.minute >= 30)
    return False

def get_assumed_pay(row):
    nl = str(row['Name']).lower()
    clocked = row['Total_Weekly_Clocked_Hrs']
    rev = row['Total_Assigned_Revenue']
    
    if 'sean marble' in nl:
        return 70000.0 / 52.0
    if 'michael owens' in nl:
        return 65000.0 / 52.0
    if 'bryan' in nl or 'erik' in nl:
        return rev * 0.33
        
    rate = 0.0
    if 'nate' in nl or 'nathan' in nl:
        rate = 22.50
    elif any(n in nl for n in ['edward', 'matt', 'tanner']):
        rate = 25.00
        
    if rate > 0:
        if clocked > 40.0:
            return (40.0 * rate) + ((clocked - 40.0) * rate * 1.5)  
        else:
            return clocked * rate
    return 0.0

def highlight_daily(val):
    hrs = parse_diff_to_hours(val)
    if hrs > 1.0: return 'background-color: #ffcccc; color: #990000;'
    return ''

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

def highlight_pay_pct_row(row):
    styles = [''] * len(row)
    if 'Pay % vs Assigned Revenue' in row.index and 'Name' in row.index:
        val = row['Pay % vs Assigned Revenue']
        name = str(row['Name']).lower()
        if val != '-' and pd.notna(val):
            try:
                v = float(str(val).replace('%', ''))
                idx = row.index.get_loc('Pay % vs Assigned Revenue')
                if 'bryan' in name or 'erik' in name:
                    if v < 34.0:
                        styles[idx] = 'background-color: #e6f4ea; color: #137333; font-weight: bold;'
                    else:
                        styles[idx] = 'background-color: #ffcccc; color: #990000;'
                else:
                    if v < 20.0:
                        styles[idx] = 'background-color: #e6f4ea; color: #137333; font-weight: bold;'
                    else:
                        styles[idx] = 'background-color: #ffcccc; color: #990000;'
            except:
                pass
    return styles

def highlight_matrix_overhead(s):
    styles = []
    for val in s:
        if val == '-' or pd.isna(val) or ' (Div: ' not in str(val):
            styles.append('')
            continue
        try:
            tech_part, div_part = str(val).split(' (Div: ')
            t_val = parse_hm(tech_part)
            d_val = parse_hm(div_part.replace(')', ''))
            if t_val > d_val:
                styles.append('background-color: #ffcccc; color: #990000;')
            else:
                styles.append('')
        except:
            styles.append('')
    return styles

# --- MAIN BLOCK REPORT ENGINE ---
def show_advanced_reporting(unexploded_ops, ops_df, final_df, bounds_df, delayed_launches_df, daily_route, tab_key):
    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
    # === BOSS TOOLS SECTION ===
    st.header("💼 Boss Tools (Financials & Efficiency)")
    
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
    
    b_col1, b_col2, b_col3, b_col4, b_col5, b_col6 = st.columns([1.3, 1, 1, 1, 1, 1])
    with b_col1:
        rate = st.number_input("Fallback Rate for Unmapped Techs ($)", value=25.0, step=1.0, key=f"rate_{tab_key}")
        
    def get_custom_loss(row, fallback):
        nl = str(row['Name']).lower()
        diff = row['Total_Weekly_Diff_Hrs']
        if diff <= 0: return 0.0
        if 'sean marble' in nl: return diff * 33.65
        if 'michael owens' in nl: return diff * 31.25
        if 'bryan' in nl or 'erik' in nl: return 0.0
        if 'nate' in nl or 'nathan' in nl: return diff * 22.50
        if any(n in nl for n in ['edward', 'matt', 'tanner']): return diff * 25.00
        return diff * fallback

    lost_money = final_df.apply(lambda r: get_custom_loss(r, rate), axis=1).sum()
    
    with b_col2: st.metric(label="Total Unaccounted", value=f"{lost_hrs:.1f} hrs")
    with b_col3: st.metric(label="Financial Leakage", value=f"${lost_money:,.2f}")
    with b_col4: st.metric(label="Overall Efficiency", value=f"{efficiency:.1f}%")
    with b_col5: st.metric(label="LSI Efficiency", value=f"{lsi_eff:.1f}%", delta=f"{total_lsi:.1f} Job Hrs", delta_color="off")
    with b_col6: st.metric(label="Water Heaters Eff", value=f"{wh_eff:.1f}%", delta=f"{total_wh:.1f} Job Hrs", delta_color="off")

    st.markdown("<br>", unsafe_allow_html=True)
    trend_col, leaderboard_col = st.columns(2)
    
    with trend_col:
        st.subheader("📈 Daily Division Health Trend")
        st.markdown("*(Combined team efficiency analyzed day-by-day across all business units)*")
        trend_data = []
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            day_clocked = final_df[f'{d}_Clocked_Hrs'].sum()
            day_job = final_df[f'{d}_Job_Hrs'].sum()
            day_eff = (day_job / day_clocked * 100) if day_clocked > 0 else 0.0
            trend_data.append({"Day": d, "Total Clocked": format_hm(day_clocked), "Job Status Time": format_hm(day_job), "Efficiency Score": f"{day_eff:.1f}%"})
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
                return ['background-color: #ffcccc; color: #990000;'] * len(row) if val > 0 else [''] * len(row)
            try: st.dataframe(show_leaderboard.reset_index(drop=True).style.hide(axis="index").apply(highlight_leaderboard, axis=1), use_container_width=True)
            except Exception: st.dataframe(show_leaderboard.reset_index(drop=True).style.apply(highlight_leaderboard, axis=1), use_container_width=True)

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
            if "🚨" in st_val or "⚠️ Low Volume" in st_val: return ['background-color: #ffcccc; color: #990000;'] * len(row)
            if "⚠️ High Overtime" in st_val: return ['background-color: #fff3cd; color: #856404;'] * len(row)
            return [''] * len(row)
        try: st.dataframe(ot_predictor_df.reset_index(drop=True).style.hide(axis="index").apply(style_ot_predictor, axis=1), use_container_width=True)
        except Exception: st.dataframe(ot_predictor_df.reset_index(drop=True).style.apply(style_ot_predictor, axis=1), use_container_width=True)
            
    st.markdown("<br>", unsafe_allow_html=True)

    # === OPS MANAGER TOOLS ===
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
        
        tech_stats = valid_jobs.groupby('Assigned Team Members').agg(Drive_Avg=('Drive_Time_Hrs', 'mean'), Store_Avg=('Store_Time_Hrs', 'mean'), IP_Avg=('In_Progress_Time_Hrs', 'mean'), Total_Avg=('Total_Job_Time_Hours', 'mean'), IP_Std=('In_Progress_Time_Hrs', 'std'), Job_Count=('Total_Job_Time_Hours', 'size')).reset_index()
        def format_bench_local(val, div_val): return f"{format_hm(val)} (Div: {format_hm(div_val)})" if pd.notna(val) else "-"
        def assign_predictability(row):
            if row['Job_Count'] < 2 or pd.isna(row['IP_Std']): return "Establishing Baseline"
            return "⚠️ Low Consistency" if row['IP_Std'] > 0.75 else "⭐ High Consistency"
            
        tech_stats['Avg Drive/Job'] = tech_stats['Drive_Avg'].apply(lambda x: format_bench_local(x, div_avg_drive))
        tech_stats['Avg Store/Job'] = tech_stats['Store_Avg'].apply(lambda x: format_bench_local(x, div_avg_store))
        tech_stats['Avg In-Progress/Job'] = tech_stats['IP_Avg'].apply(lambda x: format_bench_local(x, div_avg_ip))
        tech_stats['Avg Total Job Length'] = tech_stats['Total_Avg'].apply(lambda x: format_bench_local(x, div_avg_total))
        tech_stats['Predictability Index'] = tech_stats.apply(assign_predictability, axis=1)
        show_bench = tech_stats[['Assigned Team Members', 'Avg Drive/Job', 'Avg Store/Job', 'Avg In-Progress/Job', 'Avg Total Job Length', 'Predictability Index']].rename(columns={'Assigned Team Members': 'Name'})
        try: st.dataframe(show_bench.reset_index(drop=True).style.hide(axis="index").apply(highlight_bench_col, subset=['Avg Drive/Job', 'Avg Store/Job', 'Avg In-Progress/Job', 'Avg Total Job Length']).apply(highlight_consistency, subset=['Predictability Index']), use_container_width=True)
        except Exception: st.dataframe(show_bench.reset_index(drop=True).style.apply(highlight_bench_col, subset=['Avg Drive/Job', 'Avg Store/Job', 'Avg In-Progress/Job', 'Avg Total Job Length']).apply(highlight_consistency, subset=['Predictability Index']), use_container_width=True)

    with gold_star_col:
        st.subheader("⭐ The Gold Star High-Performer List")
        st.markdown("*(Technicians who average under 1:30 of unallocated difference per day worked)*")
        gold_star_df = final_df[(final_df['Daily_Avg_Diff_Hrs'] < 1.5) & (final_df['Days_Worked'] > 0)].copy()
        if not gold_star_df.empty:
            gold_star_df = gold_star_df.sort_values(by='Daily_Avg_Diff_Hrs', ascending=True)
            gold_star_df['Total Clocked'] = gold_star_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
            gold_star_df['Total Job Time'] = gold_star_df['Total_Weekly_Job_Hrs'].apply(format_hm)
            gold_star_df['Daily Avg Diff'] = gold_star_df['Daily_Avg_Diff_Hrs'].apply(format_hm)
            gold_star_df['Total Diff'] = gold_star_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
            show_gold = gold_star_df[['Name', 'Total Clocked', 'Total Job Time', 'Daily Avg Diff', 'Total Diff']].copy()
            try: st.dataframe(show_gold.reset_index(drop=True).style.hide(axis="index").set_properties(**{'background-color': '#e6f4ea', 'color': '#137333'}), use_container_width=True)
            except Exception: st.dataframe(show_gold.reset_index(drop=True).style.set_properties(**{'background-color': '#e6f4ea', 'color': '#137333'}), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🎯 The Technician Skill Matrix & Training Flag")
    st.markdown("*(Compares a technician's LSI performance against their WH performance. Flags techs where the gap exceeds 15%)*")
    skill_df = final_df.copy()
    if not skill_df.empty:
        skill_df['Eff Gap'] = np.where((skill_df['Simple_Installs_Count'] > 0) & (skill_df['Water_Heaters_Count'] > 0), abs(skill_df['LSI_Eff_Raw'] - skill_df['WH_Eff_Raw']), 0.0)
        def assign_skill_flag(row):
            lsi_cnt, wh_cnt = row['Simple_Installs_Count'], row['Water_Heaters_Count']
            if lsi_cnt > 0 and wh_cnt > 0:
                if row['Eff Gap'] > 15.0: return "⚠️ WH Ride-Along Required" if row['LSI_Eff_Raw'] > row['WH_Eff_Raw'] else "⚠️ LSI Ride-Along Required"
                return "✅ Balanced Execution"
            if lsi_cnt > 0: return "ℹ️ Only LSI Jobs Assigned"
            if wh_cnt > 0: return "ℹ️ Only WH Jobs Assigned"
            return "ℹ️ No BU Jobs Assigned"
        skill_df['Action Required'] = skill_df.apply(assign_skill_flag, axis=1)
        show_skill = skill_df[['Name', 'Simple Installs Eff', 'Water Heaters Eff', 'Action Required']].rename(columns={'Simple Installs Eff': 'LSI Efficiency', 'Water Heaters Eff': 'WH Efficiency'})
        def style_flags(row): return ['background-color: #fff3cd; color: #856404; font-weight: bold;'] * len(row) if '⚠️' in row['Action Required'] else [''] * len(row)
        try: st.dataframe(show_skill.reset_index(drop=True).style.hide(axis="index").apply(style_flags, axis=1), use_container_width=True)
        except Exception: st.dataframe(show_skill.reset_index(drop=True).style.apply(style_flags, axis=1), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🗺️ Route Optimization Flags")
    poor_routes = daily_route[daily_route['Drive %'] > 40.0].copy()
    if not poor_routes.empty:
        poor_routes['Drive %'] = poor_routes['Drive %'].apply(lambda x: f"{x:.1f}%")
        poor_routes['Drive Time'] = poor_routes['Drive_Time_Hrs'].apply(format_hm)
        poor_routes['Work Time'] = poor_routes['In_Progress_Time_Hrs'].apply(format_hm)
        st.dataframe(poor_routes[['Assigned Team Members', 'Short_Date', 'Job_Count', 'Drive Time', 'Work Time', 'Drive %']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date', 'Job_Count': 'Jobs'}), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    launch_col, launch_empty_col = st.columns(2)
    with launch_col:
        st.subheader("📊 Late Deployment Scorecard")
        if not delayed_launches_df.empty:
            launch_counts = delayed_launches_df.groupby('Assigned Team Members').size().reset_index(name='Total Late Days').sort_values(by='Total Late Days', ascending=False)
            try: st.dataframe(launch_counts.reset_index(drop=True).style.hide(axis="index").set_properties(**{'background-color': '#fff3cd', 'color': '#856404;'}, subset=['Total Late Days']), use_container_width=True)
            except Exception: st.dataframe(launch_counts.reset_index(drop=True).style.set_properties(**{'background-color': '#fff3cd', 'color': '#856404;'}, subset=['Total Late Days']), use_container_width=True)

    with launch_empty_col:
        st.subheader("🚗 Delayed Launch Alert")
        if not delayed_launches_df.empty:
            tech_late_list = sorted(delayed_launches_df['Assigned Team Members'].unique())
            selected_late_tech = st.selectbox("Select Tech to view launch times:", tech_late_list, key=f"late_launch_{tab_key}")
            if selected_late_tech:
                tech_launches_df = delayed_launches_df[delayed_launches_df['Assigned Team Members'] == selected_late_tech].copy()
                tech_launches_df['First Launch'] = tech_launches_df['First_Punch'].dt.strftime('%I:%M %p') + " (" + tech_launches_df['First_Status'] + ")"
                try: st.dataframe(tech_launches_df.sort_values(by='First_Punch', ascending=False)[['Short_Date', 'First Launch']].rename(columns={'Short_Date': 'Date'}).reset_index(drop=True).style.hide(axis="index").set_properties(**{'background-color': '#ffcccc', 'color': '#990000;'}), use_container_width=True)
                except Exception: st.dataframe(tech_launches_df.sort_values(by='First_Punch', ascending=False)[['Short_Date', 'First Launch']].rename(columns={'Short_Date': 'Date'}).reset_index(drop=True).style.set_properties(**{'background-color': '#ffcccc', 'color': '#990000;'}), use_container_width=True)

# --- CONSOLIDATED SANDBOX TAB VIEWS ---
def run_sandbox_tab(unexploded_ops, ops_df, final_df, daily_route, test_choices):
    if "🏆 The Golden Ratio Margin Predictor" in test_choices:
        st.markdown("### **🏆 The Golden Ratio Margin Predictor**")
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
                golden_data.append({"Day": d, "LSI Jobs": day_lsi, "WH Jobs": day_wh, "LSI Mix %": f"{lsi_ratio:.1f}%", "Daily Efficiency": day_eff, "Profile": profile})
        if golden_data:
            golden_df = pd.DataFrame(golden_data)
            golden_summary = golden_df.groupby('Profile').agg(Days=('Day', 'count'), Avg_Efficiency=('Daily Efficiency', 'mean')).reset_index()
            golden_summary['Avg Efficiency'] = golden_summary['Avg_Efficiency'].apply(lambda x: f"{x:.1f}%")
            golden_df['Daily Efficiency'] = golden_df['Daily Efficiency'].apply(lambda x: f"{x:.1f}%")
            g_col1, g_col2 = st.columns(2)
            with g_col1: st.dataframe(golden_summary[['Profile', 'Days', 'Avg Efficiency']], use_container_width=True)
            with g_col2: st.dataframe(golden_df[['Day', 'LSI Mix %', 'Profile', 'Daily Efficiency']], use_container_width=True)

    if "🔄 The Context-Switching Penalty Alert" in test_choices:
        st.markdown("### **🔄 Context-Switching Penalty Alert**")
        if 'Business Unit' in ops_df.columns:
            daily_bu = ops_df.groupby(['Assigned Team Members', 'Short_Date', 'Business Unit']).size().unstack(fill_value=0).reset_index()
            if 'Lowes - Simple Installs' not in daily_bu.columns: daily_bu['Lowes - Simple Installs'] = 0
            if 'Lowes - Water Heaters' not in daily_bu.columns: daily_bu['Lowes - Water Heaters'] = 0
            daily_bu['Day Type'] = np.where((daily_bu['Lowes - Simple Installs'] > 0) & (daily_bu['Lowes - Water Heaters'] > 0), 'Mixed Route (Both)', 'Uniform Route (One Type)')
            daily_merged = pd.merge(daily_route, daily_bu, on=['Assigned Team Members', 'Short_Date'])
            daily_merged['Avg Job Time'] = daily_merged['Total_Job_Time_Hours'] / daily_merged['Job_Count']
            context_agg = daily_merged.groupby('Day Type').agg(Total_Days=('Short_Date', 'count'), Avg_Job_Turnaround=('Avg Job Time', 'mean')).reset_index()
            if not context_agg.empty:
                context_agg['Average Fleet Job Turnaround'] = context_agg['Avg_Job_Turnaround'].apply(format_hm)
                st.dataframe(context_agg[['Day Type', 'Total_Days', 'Average Fleet Job Turnaround']].rename(columns={'Total_Days': 'Days Analyzed'}), use_container_width=True)

    if "🕵️ The \"Ghost Punch\" & Payroll Discrepancy Auditor" in test_choices:
        st.markdown("### **🕵️ The \"Ghost Punch\" & Payroll Discrepancy Auditor**")
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
        if ghost_alerts: st.dataframe(pd.DataFrame(ghost_alerts), use_container_width=True)
        else: st.success("Perfect alignment! No payroll discrepancy errors detected on current sheets.")

    if "¼ The Lowe's Store Staging Efficiency Scorecard" in test_choices:
        st.markdown("### **¼ The Lowe's Store Staging Efficiency Scorecard**")
        store_cols = [c for c in ops_df.columns if 'store' in c.lower() and 'time' not in c.lower() and 'timestamp' not in c.lower()]
        if store_cols:
            store_stats = ops_df.groupby(store_cols[0])['Store_Time_Hrs'].mean().reset_index()
            store_stats.columns = ['Store Identifier', 'Avg Delay Length (Hrs)']
            store_stats['Avg Delay Length'] = store_stats['Avg Delay Length (Hrs)'].apply(format_hm)
            st.dataframe(store_stats.sort_values(by='Avg Delay Length (Hrs)', ascending=False)[['Store Identifier', 'Avg Delay Length']], use_container_width=True)

    if "📊 Macro Financial Performance Dashboard" in test_choices:
        st.markdown("### **📊 Macro Financial Performance Dashboard**")
        m_col1, m_col2 = st.columns([1, 2])
        with m_col1:
            total_rev = unexploded_ops['Total Invoice Amount'].sum()
            st.metric(label="Division Gross Invoiced Volume", value=f"${total_rev:,.2f}")
            bu_avg_ticket = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].mean().reset_index()
            bu_avg_ticket.columns = ['Business Unit', 'Average Ticket Size Raw']
            bu_avg_ticket['Average Ticket Size'] = bu_avg_ticket['Average Ticket Size Raw'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(bu_avg_ticket[['Business Unit', 'Average Ticket Size']].reset_index(drop=True), use_container_width=True)
        with m_col2:
            st.markdown("**📈 Pay Ratio per Clocked Hour**")
            rev_per_hour_df = final_df.copy()
            rev_per_hour_df['Total Clocked'] = rev_per_hour_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
            rev_per_hour_df['Total Assigned Value'] = rev_per_hour_df['Total_Assigned_Revenue'].apply(lambda x: f"${x:,.2f}")
            rev_per_hour_df['Assumed Pay Amount'] = rev_per_hour_df.apply(get_assumed_pay, axis=1)
            rev_per_hour_df['Assumed Pay'] = rev_per_hour_df['Assumed Pay Amount'].apply(lambda x: f"${x:,.2f}" if x > 0 else "-")
            rev_per_hour_df['Pay Pct'] = np.where(rev_per_hour_df['Total_Assigned_Revenue'] > 0, (rev_per_hour_df['Assumed Pay Amount'] / rev_per_hour_df['Total_Assigned_Revenue']) * 100, 0.0)
            rev_per_hour_df['Pay % vs Assigned Revenue'] = rev_per_hour_df['Pay Pct'].apply(lambda x: f"{x:.1f}%" if x > 0 else "-")
            show_rev_per_hour = rev_per_hour_df.sort_values(by='Pay Pct', ascending=False)[['Name', 'Total Clocked', 'Total Assigned Value', 'Assumed Pay', 'Pay % vs Assigned Revenue']]
            st.dataframe(show_rev_per_hour.reset_index(drop=True).style.apply(highlight_pay_pct_row, axis=1), use_container_width=True)

    if "📊 Business Unit Revenue Velocity" in test_choices:
        st.markdown("### **📊 Business Unit Revenue Velocity**")
        bu_rev = unexploded_ops['Total Invoice Amount'].sum()
        bu_rev_df = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].sum().reset_index()
        bu_rev_df['Revenue Share %'] = (bu_rev_df['Total Invoice Amount'] / unexploded_ops['Total Invoice Amount'].sum()) * 100
        bu_rev_df['Total Revenue'] = bu_rev_df['Total Invoice Amount'].apply(lambda x: f"${x:,.2f}")
        bu_rev_df['Revenue Share %'] = bu_rev_df['Revenue Share %'].apply(lambda x: f"{x:.1f}%")
        st.dataframe(bu_rev_df[['Business Unit', 'Total Revenue', 'Revenue Share %']].reset_index(drop=True), use_container_width=True)

    if "🗺️ Revenue Yield per Drive Hour (Geo-Routing Efficiency)" in test_choices:
        st.markdown("### **🗺️ Revenue Yield per Drive Hour (Geo-Routing Efficiency)**")
        route_eff = ops_df.groupby('Assigned Team Members').agg(Total_Revenue=('Total Invoice Amount', 'sum'), Total_Drive_Hrs=('Drive_Time_Hrs', 'sum')).reset_index().rename(columns={'Assigned Team Members': 'Name'})
        route_eff['Rev per Drive Hour Raw'] = np.where(route_eff['Total_Drive_Hrs'] > 0, route_eff['Total_Revenue'] / route_eff['Total_Drive_Hrs'], 0.0)
        route_eff = route_eff.sort_values(by='Rev per Drive Hour Raw', ascending=False)
        route_eff['Total Assigned Revenue'] = route_eff['Total_Revenue'].apply(lambda x: f"${x:,.2f}")
        route_eff['Total Drive Hours'] = route_eff['Total_Drive_Hrs'].apply(lambda x: f"{x:.1f} hrs")
        route_eff['Revenue per Drive Hour'] = route_eff['Rev per Drive Hour Raw'].apply(lambda x: f"${x:,.2f}/hr")
        st.dataframe(route_eff[['Name', 'Total Assigned Revenue', 'Total Drive Hours', 'Revenue per Drive Hour']].reset_index(drop=True), use_container_width=True)

    if "📉 True Gross Margin per Clocked Hour" in test_choices:
        st.markdown("### **📉 True Gross Margin per Clocked Hour**")
        margin_df = final_df.copy()
        margin_df['Assumed Pay Amount'] = margin_df.apply(get_assumed_pay, axis=1)
        margin_df['Net Margin Raw'] = margin_df['Total_Assigned_Revenue'] - margin_df['Assumed Pay Amount']
        margin_df['Margin per Clocked Hour Raw'] = np.where(margin_df['Total_Weekly_Clocked_Hrs'] > 0, margin_df['Net Margin Raw'] / margin_df['Total_Weekly_Clocked_Hrs'], 0.0)
        margin_df = margin_df.sort_values(by='Margin per Clocked Hour Raw', ascending=False)
        margin_df['Total Assigned Revenue'] = margin_df['Total_Assigned_Revenue'].apply(lambda x: f"${x:,.2f}")
        margin_df['Assumed Pay'] = margin_df['Assumed Pay Amount'].apply(lambda x: f"${x:,.2f}")
        margin_df['Total Net Margin'] = margin_df['Net Margin Raw'].apply(lambda x: f"${x:,.2f}")
        margin_df['Total Clocked'] = margin_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
        margin_df['Margin per Clocked Hour'] = margin_df['Margin per Clocked Hour Raw'].apply(lambda x: f"${x:,.2f}/hr")
        st.dataframe(margin_df[['Name', 'Total Clocked', 'Total Assigned Revenue', 'Assumed Pay', 'Total Net Margin', 'Margin per Clocked Hour']].reset_index(drop=True), use_container_width=True)

    # === ADVANCED BASELINES MATRIX CONTEXT LAYOUTS ===
    if "📋 Advanced Team Processing Baselines Matrix" in test_choices:
        st.markdown("### **📋 Advanced Team Processing Baselines Matrix**")
        
        wh_jobs = ops_df[ops_df['Business Unit'] == 'Lowes - Water Heaters']
        lsi_jobs = ops_df[ops_df['Business Unit'] == 'Lowes - Simple Installs']
        
        div_avg_total = ops_df['Total_Job_Time_Hours'].mean() if not ops_df.empty else 0.0
        div_wh_baseline = wh_jobs['Total_Job_Time_Hours'].mean() if not wh_jobs.empty else 3.5
        div_lsi_baseline = lsi_jobs['Total_Job_Time_Hours'].mean() if not lsi_jobs.empty else 2.0
        
        # Filter division baseline store parameters to strictly ignore direct-to-site jobs
        wh_jobs_with_store = wh_jobs[wh_jobs['Store_Time_Hrs'] > 0]
        lsi_jobs_with_store = lsi_jobs[lsi_jobs['Store_Time_Hrs'] > 0]
        div_wh_store_baseline = wh_jobs_with_store['Store_Time_Hrs'].mean() if not wh_jobs_with_store.empty else 0.5
        div_lsi_store_baseline = lsi_jobs_with_store['Store_Time_Hrs'].mean() if not lsi_jobs_with_store.empty else 0.3
        
        st.markdown(f"""
        📊 **Current Division Baseline Averages (Store Averages Ignore Direct-To-Site Jobs):** &nbsp;&nbsp;•&nbsp;&nbsp;**Blended Total Avg:** `{format_hm(div_avg_total)}` &nbsp;&nbsp;|&nbsp;&nbsp; **WH Job Length:** `{format_hm(div_wh_baseline)}` &nbsp;&nbsp;|&nbsp;&nbsp; **LSI Job Length:** `{format_hm(div_lsi_baseline)}` 
        &nbsp;&nbsp;•&nbsp;&nbsp;**WH Store Delay:** `{format_hm(div_wh_store_baseline)}` &nbsp;&nbsp;|&nbsp;&nbsp; **LSI Store Delay:** `{format_hm(div_lsi_store_baseline)}`
        """)
        
        matrix_rows = []
        wh_over_baseline_rows = []
        lsi_over_baseline_rows = []
        
        for tech_name in sorted(ops_df['Assigned Team Members'].unique()):
            tech_jobs = ops_df[ops_df['Assigned Team Members'] == tech_name]
            
            t_wh = tech_jobs[tech_jobs['Business Unit'] == 'Lowes - Water Heaters']
            t_lsi = tech_jobs[tech_jobs['Business Unit'] == 'Lowes - Simple Installs']
            
            avg_total_val = tech_jobs['Total_Job_Time_Hours'].mean() if not tech_jobs.empty else np.nan
            avg_wh_val = t_wh['Total_Job_Time_Hours'].mean() if not t_wh.empty else np.nan
            avg_lsi_val = t_lsi['Total_Job_Time_Hours'].mean() if not t_lsi.empty else np.nan
            
            t_wh_store = t_wh[t_wh['Store_Time_Hrs'] > 0]
            t_lsi_store = t_lsi[t_lsi['Store_Time_Hrs'] > 0]
            avg_wh_store_val = t_wh_store['Store_Time_Hrs'].mean() if not t_wh_store.empty else np.nan
            avg_lsi_store_val = t_lsi_store['Store_Time_Hrs'].mean() if not t_lsi_store.empty else np.nan
            
            if not tech_jobs.empty:
                max_idx = tech_jobs['Total_Job_Time_Hours'].idxmax()
                max_job_val = tech_jobs['Total_Job_Time_Hours'].max()
                max_job_id = tech_jobs.loc[max_idx, '#ID']
                if isinstance(max_job_id, float) and max_job_id.is_integer():
                    max_job_id = int(max_job_id)
                max_job_str = f"{format_hm(max_job_val)} (ID: {max_job_id})"
            else:
                max_job_str = "-"
                
            # Compile Water Heaters outliers with precise float delta calculations
            if pd.notna(div_wh_baseline):
                for _, j in t_wh[t_wh['Total_Job_Time_Hours'] > div_wh_baseline].iterrows():
                    jid = int(j['#ID']) if isinstance(j['#ID'], float) and j['#ID'].is_integer() else j['#ID']
                    diff_val = j['Total_Job_Time_Hours'] - div_wh_baseline
                    wh_over_baseline_rows.append({
                        "Technician": tech_name,
                        "Job ID": str(jid),
                        "Job Duration": format_hm(j['Total_Job_Time_Hours']),
                        "Over Division Average By": f"+{format_hm(diff_val)}",
                        "sort_key": diff_val
                    })
            
            # Compile Simple Installs outliers with precise float delta calculations
            if pd.notna(div_lsi_baseline):
                for _, j in t_lsi[t_lsi['Total_Job_Time_Hours'] > div_lsi_baseline].iterrows():
                    jid = int(j['#ID']) if isinstance(j['#ID'], float) and j['#ID'].is_integer() else j['#ID']
                    diff_val = j['Total_Job_Time_Hours'] - div_lsi_baseline
                    lsi_over_baseline_rows.append({
                        "Technician": tech_name,
                        "Job ID": str(jid),
                        "Job Duration": format_hm(j['Total_Job_Time_Hours']),
                        "Over Division Average By": f"+{format_hm(diff_val)}",
                        "sort_key": diff_val
                    })
            
            matrix_rows.append({
                "Name": tech_name,
                "Total Avg Job Time": f"{format_hm(avg_total_val)} (Div: {format_hm(div_avg_total)})" if pd.notna(avg_total_val) else "-",
                "Avg WH Time": f"{format_hm(avg_wh_val)} (Div: {format_hm(div_wh_baseline)})" if pd.notna(avg_wh_val) else "-",
                "Avg LSI Time": f"{format_hm(avg_lsi_val)} (Div: {format_hm(div_lsi_baseline)})" if pd.notna(avg_lsi_val) else "-",
                "Avg WH Store Time": f"{format_hm(avg_wh_store_val)} (Div: {format_hm(div_wh_store_baseline)})" if pd.notna(avg_wh_store_val) else "-",
                "Avg LSI Store Time": f"{format_hm(avg_lsi_store_val)} (Div: {format_hm(div_lsi_store_baseline)})" if pd.notna(avg_lsi_store_val) else "-",
                "Max Single Job Length": max_job_str,
                "sort_key": avg_total_val if pd.notna(avg_total_val) else -1.0
            })
            
        matrix_df = pd.DataFrame(matrix_rows)
        if not matrix_df.empty:
            matrix_df = matrix_df.sort_values(by='sort_key', ascending=False).drop(columns=['sort_key'])
            
        try:
            styled_matrix = matrix_df.reset_index(drop=True).style.apply(highlight_matrix_overhead, subset=['Total Avg Job Time', 'Avg WH Time', 'Avg LSI Time', 'Avg WH Store Time', 'Avg LSI Store Time'])
            st.dataframe(styled_matrix, use_container_width=True)
        except Exception:
            st.dataframe(matrix_df.reset_index(drop=True), use_container_width=True)
            
        # FIXED: Created side-by-side wide layout tables split cleanly by active Business Unit profiles
        st.markdown("<br>#### 🚨 Individual Over-Baseline Job Reference Breakdown", unsafe_allow_html=True)
        st.markdown("*(Granular tracking sheets isolating individual work orders exceeding the division run baselines, sorted largest variation to lowest)*")
        
        split_col1, split_col2 = st.columns(2)
        
        with split_col1:
            st.markdown("##### 🛢️ Water Heaters Over-Baseline Jobs")
            if wh_over_baseline_rows:
                wh_matrix_df = pd.DataFrame(wh_over_baseline_rows).sort_values(by='sort_key', ascending=False).drop(columns=['sort_key'])
                st.dataframe(wh_matrix_df.reset_index(drop=True), use_container_width=True)
            else:
                st.success("✅ Zero individual Water Heater jobs exceeded the division baseline average.")
                
        with split_col2:
            st.markdown("##### 🔧 Simple Installs Over-Baseline Jobs")
            if lsi_over_baseline_rows:
                lsi_matrix_df = pd.DataFrame(lsi_over_baseline_rows).sort_values(by='sort_key', ascending=False).drop(columns=['sort_key'])
                st.dataframe(lsi_matrix_df.reset_index(drop=True), use_container_width=True)
            else:
                st.success("✅ Zero individual Simple Install jobs exceeded the division baseline average.")
            
    except Exception as e:
        st.error(f"An error occurred while processing the files: Please ensure you uploaded the correct CSV formats. Exact error: {e}")
