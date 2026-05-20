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
        h, m = map(int, str(time_str).split(':'))
        return h + m / 60.0
    except:
        return 0.0

def parse_diff_to_hours(val):
    if val == '-' or pd.isna(val): return 0.0
    try:
        sign = -1 if str(val).startswith('-') else 1
        clean_val = str(val).replace('-', '')
        if ':' in clean_val:
            h, m = map(int, clean_val.split(':'))
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
def show_advanced_reporting(ops_df, final_df, export_df, tab_key):
    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
    # === BOSS TOOLS SECTION ===
    st.header("💼 Boss Tools (Financials & Efficiency)")
    
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    
    with b_col1:
        st.markdown("**Calculate Lost Revenue**")
        rate = st.number_input("Average Tech Hourly Rate ($)", value=25.0, step=1.0, key=f"rate_{tab_key}")
        
    total_clocked = final_df['Total_Weekly_Clocked_Hrs'].sum()
    total_job = final_df['Total_Weekly_Job_Hrs'].sum()
    efficiency = (total_job / total_clocked * 100) if total_clocked > 0 else 0
    lost_hrs = final_df[final_df['Total_Weekly_Diff_Hrs'] > 0]['Total_Weekly_Diff_Hrs'].sum()
    lost_money = lost_hrs * rate
    
    with b_col2:
        st.metric(label="Total Unaccounted Hours", value=f"{lost_hrs:.1f} hrs")
    with b_col3:
        st.metric(label="Financial Leakage (Loss)", value=f"${lost_money:,.2f}")
    with b_col4:
        st.metric(label="Division Efficiency Score", value=f"{efficiency:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)
    
    trend_col, leaderboard_col = st.columns(2)
    
    with trend_col:
        st.subheader("📈 Daily Division Health Trend")
        st.markdown("*(Combined team efficiency analyzed day-by-day)*")
        trend_data = []
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            day_clocked = final_df[f'{d}_Clocked_Hrs'].sum()
            day_job = final_df[f'{d}_Job_Hrs'].sum()
            day_eff = (day_job / day_clocked * 100) if day_clocked > 0 else 0.0
            trend_data.append({
                "Day": d, 
                "Total Clocked": format_hm(day_clocked), 
                "Total Job Time": format_hm(day_job), 
                "Efficiency Score": f"{day_eff:.1f}%"
            })
        trend_df = pd.DataFrame(trend_data)
        st.dataframe(trend_df, use_container_width=True)

    with leaderboard_col:
        st.subheader("🚨 Team Leaderboard")
        st.markdown("*(Whole team sorted by highest unaccounted time)*")
        leaderboard_df = final_df.sort_values(by='Total_Weekly_Diff_Hrs', ascending=False).copy()
        if not leaderboard_df.empty:
            leaderboard_df['Total Clocked'] = leaderboard_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
            leaderboard_df['Total Job Time'] = leaderboard_df['Total_Weekly_Job_Hrs'].apply(format_hm)
            leaderboard_df['Total Diff'] = leaderboard_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
            
            show_leaderboard = leaderboard_df[['Name', 'Total Clocked', 'Total Job Time', 'Total Diff']].copy()
            def highlight_leaderboard(row):
                val = parse_diff_to_hours(row['Total Diff'])
                if val > 0:
                    return ['background-color: #ffcccc; color: #990000;'] * len(row)
                return [''] * len(row)
            try:
                styled_leaderboard = show_leaderboard.style.hide(axis="index").apply(highlight_leaderboard, axis=1)
            except Exception:
                styled_leaderboard = show_leaderboard.style.apply(highlight_leaderboard, axis=1)
            st.dataframe(styled_leaderboard, use_container_width=True)
        else:
            st.info("No tech data available to display.")
            
    st.markdown("<br>", unsafe_allow_html=True)
    csv_data = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="💾 Download Final Weekly Report (CSV for Payroll/HR)",
        data=csv_data,
        file_name="Tech_Time_Weekly_Summary.csv",
        mime="text/csv",
        key=f"download_{tab_key}"
    )

    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
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
        
        # Calculate consistency metrics based on the standard deviation of In Progress times
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
        tech_stats['Avg Store/Job'] = tech_stats['Store_Avg'].apply(lambda x
