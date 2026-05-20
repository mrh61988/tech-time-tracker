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

# --- Advanced Reporting Block Function ---
def show_advanced_reporting(ops_df, final_df, export_df, tab_key):
    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
    # === BOSS TOOLS SECTION ===
    st.header("💼 Boss Tools (Financials & Efficiency)")
    
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    
    with b_col1:
        st.markdown("**Calculate Lost Revenue**")
        # Added a unique key here to prevent Streamlit duplicate ID error
        rate = st.number_input("Average Tech Hourly Rate ($)", value=25.0, step=1.0, key=f"rate_{tab_key}")
        
    # Calculate Metrics
    total_clocked = final_df['Total_Weekly_Clocked_Hrs'].sum()
    total_job = final_df['Total_Weekly_Job_Hrs'].sum()
    efficiency = (total_job / total_clocked * 100) if total_clocked > 0 else 0
    
    # Only calculate lost hours for techs who have a POSITIVE difference (unaccounted time)
    lost_hrs = final_df[final_df['Total_Weekly_Diff_Hrs'] > 0]['Total_Weekly_Diff_Hrs'].sum()
    lost_money = lost_hrs * rate
    
    with b_col2:
        st.metric(label="Total Unaccounted Hours", value=f"{lost_hrs:.1f} hrs")
    with b_col3:
        st.metric(label="Financial Leakage (Loss)", value=f"${lost_money:,.2f}")
    with b_col4:
        st.metric(label="Division Efficiency Score", value=f"{efficiency:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)
    
    colA, colB = st.columns(2)
    with colA:
        st.subheader("🚨 Top 5 Offenders Leaderboard")
        st.markdown("*(Highest unaccounted time for the week)*")
        leaderboard_df = final_df[final_df['Total_Weekly_Diff_Hrs'] > 0].sort_values(by='Total_Weekly_Diff_Hrs', ascending=False).head(5).copy()
        if not leaderboard_df.empty:
            leaderboard_df['Total Clocked'] = leaderboard_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
            leaderboard_df['Total Job Time'] = leaderboard_df['Total_Weekly_Job_Hrs'].apply(format_hm)
            leaderboard_df['Total Diff'] = leaderboard_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
            show_leaderboard = leaderboard_df[['Name', 'Total Clocked', 'Total Job Time', 'Total Diff']].copy()
            try:
                styled_leaderboard = show_leaderboard.style.hide(axis="index").set_properties(**{'background-color': '#ffcccc', 'color': '#990000'})
            except Exception:
                styled_leaderboard = show_leaderboard.style.set_properties(**{'background-color': '#ffcccc', 'color': '#990000'})
            st.dataframe(styled_leaderboard, use_container_width=True)
        else:
            st.success("No techs with unaccounted time!")
            
    with colB:
        st.subheader("💾 1-Click Payroll Export")
        st.markdown("*(Download the clean, finalized weekly calculations)*")
        csv_data = export_df.to_csv(index=False).encode('utf-8')
        # Added a unique key here as well to prevent download button duplicate error
        st.download_button(
            label="Download Final Weekly Report (CSV)",
            data=csv_data,
            file_name="Tech_Time_Weekly_Summary.csv",
            mime="text/csv",
            key=f"download_{tab_key}"
        )

    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    
    # === DISPATCHER TOOLS SECTION ===
    st.header("🛠️ Dispatcher Tools (Daily Accountability)")
    
    d_col1, d_col2 = st.columns(2)
    
    with d_col1:
        st.subheader("🕳️ 'Black Hole' Gap Finder")
        st.markdown("*(Gaps between jobs larger than 45 minutes)*")
        
        # Calculate gaps
        ops_sorted = ops_df.dropna(subset=['Earliest_Start']).sort_values(['Assigned Team Members', 'Earliest_Start'])
        # Shift the start time of the NEXT job up one row (grouped by tech and day)
        ops_sorted['Next_Job_Start'] = ops_sorted.groupby(['Assigned Team Members', 'Short_Date'])['Earliest_Start'].shift(-1)
        ops_sorted['Gap_Hrs'] = (ops_sorted['Next_Job_Start'] - ops_sorted['Estimated_End']).dt.total_seconds() / 3600.0
        
        gaps_df = ops_sorted[ops_sorted['Gap_Hrs'] > 0.75].copy() # > 45 mins
        
        if not gaps_df.empty:
            gaps_df['Gap Length'] = gaps_df['Gap_Hrs'].apply(format_hm)
            gaps_df['End of Job 1'] = gaps_df['Estimated_End'].dt.strftime('%I:%M %p')
            gaps_df['Start of Job 2'] = gaps_df['Next_Job_Start'].dt.strftime('%I:%M %p')
            show_gaps = gaps_df[['Assigned Team Members', 'Short_Date', 'End of Job 1', 'Start of Job 2', 'Gap Length']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
            st.dataframe(show_gaps, use_container_width=True)
        else:
            st.success("No major routing gaps detected!")

    with d_col2:
        st.subheader("🌅 First Job vs. Last Job")
        st.markdown("*(First punch of the morning, last punch of the afternoon)*")
        
        bounds_df = ops_sorted.groupby(['Assigned Team Members', 'Short_Date']).agg(
            First_Punch=('Earliest_Start', 'min'),
            Last_Punch=('Estimated_End', 'max')
        ).reset_index()
        
        bounds_df['First Status Update'] = bounds_df['First_Punch'].dt.strftime('%I:%M %p')
        bounds_df['Last Status Update'] = bounds_df['Last_Punch'].dt.strftime('%I:%M %p')
        show_bounds = bounds_df[['Assigned Team Members', 'Short_Date', 'First Status Update', 'Last Status Update']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
        st.dataframe(show_bounds, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    colC, colD = st.columns(2)
    with colC:
        st.subheader("🛑 Excessive Store Time")
        st.markdown("*(Jobs where tech spent > 60 minutes in Lowe's Status)*")
        excessive_df = ops_df[ops_df['Store_Time_Hrs'] > 1.0].copy()
        if not excessive_df.empty:
            excessive_df['Store Time'] = excessive_df['Store_Time_Hrs'].apply(format_hm)
            show_excessive = excessive_df[['Assigned Team Members', 'Short_Date', 'Store Time']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
            st.dataframe(show_excessive, use_container_width=True)
        else:
            st.success("No excessive store times detected.")
            
    with colD:
        st.subheader("⏱️ Weekly Status Breakdown")
        st.markdown("*(Drive vs. Store vs. In Progress Time)*")
        breakdown_agg = ops_df.groupby('Assigned Team Members')[['Drive_Time_Hrs', 'Store_Time_Hrs', 'In_Progress_Time_Hrs']].sum().reset_index()
        breakdown_agg['Drive Time'] = breakdown_agg['Drive_Time_Hrs'].apply(format_hm)
        breakdown_agg['Store Time'] = breakdown_agg['Store_Time_Hrs'].apply(format_hm)
        breakdown_agg['In Progress Time'] = breakdown_agg['In_Progress_Time_Hrs'].apply(format_hm)
        show_breakdown = breakdown_agg[['Assigned Team Members', 'Drive Time', 'Store Time', 'In Progress Time']].rename(columns={'Assigned Team Members': 'Name'})
        st.dataframe(show_breakdown, use_container_width=True)
# ------------------------------

# Only run the processing if both files are uploaded
if time_file and ops_file:
    try:
        EXCLUDE_NAMES = [
            'Luis Ortiz', 
            'Roman Twardoz',
            'Dave Barber Show Low (Contactor)',
            'Oak Wrench AZ Jarrod Scully (Contractor)',
            'Presidio Plumbing Eric (Contractor)'
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
        
        ts_cols = [
            'Lowes Store - Start Timestamp',
            'On The Way - Start Timestamp',
            'In Progress - Start Timestamp',
            'On The Way - Start Timestamp.1',
            'In Progress - Start Timestamp.1'
        ]
        
        available_ts_cols = [c for c in ts_cols if c in ops_df.columns]
        
        ops_df['Job_Date'] = ops_df[available_ts_cols].bfill(axis=1).iloc[:, 0]
        
        # safely parse timestamps by chopping off the timezone string
        for c in available_ts_cols:
            ops_df[c + '_dt'] = pd.to_datetime(ops_df[c].astype(str).str.split(' GMT').str[0], errors='coerce')
        
        # Calculate start and end times for gap analysis
        ops_df['Earliest_Start'] = ops_df[[c + '_dt' for c in available_ts_cols]].min(axis=1)
        ops_df['Estimated_End'] = ops_df['Earliest_Start'] + pd.to_timedelta(ops_df['Total_Job_Time_Hours'] * 3600, unit='s')
        
        ops_df['Job_Date_Parsed'] = pd.to_datetime(ops_df['Job_Date'].astype(str).str.split(' GMT').str[0], errors='coerce')
        ops_df['Day_of_Week'] = ops_df['Job_Date_Parsed'].dt.day_name().str[:3]
        ops_df['Short_Date'] = ops_df['Job_Date_Parsed'].dt.strftime('%m-%d-%Y')
        
        ops_df['Assigned Team Members'] = ops_df['Assigned Team Members'].astype(str).str.split(',')
        ops_df = ops_df.explode('Assigned Team Members')
        ops_df['Assigned Team Members'] = ops_df['Assigned Team Members'].str.strip()
        ops_df = ops_df[~ops_df['Assigned Team Members'].isin(EXCLUDE_NAMES)]
        
        job_time_agg = ops_df.groupby(['Assigned Team Members', 'Day_of_Week'])['Total_Job_Time_Hours'].sum().reset_index()
        job_time_pivot = job_time_agg.pivot(index='Assigned Team Members', columns='Day_of_Week', values='Total_Job_Time_Hours').reset_index()
        job_time_pivot = job_time_pivot.rename(columns={'Assigned Team Members': 'Name'}).fillna(0)
        
        for day in days:
            if day not in job_time_pivot.columns:
                job_time_pivot[day] = 0.0
        
        rename_dict = {day: day + '_Job_Hrs' for day in days}
        job_time_pivot = job_time_pivot.rename(columns=rename_dict)
        job_time_pivot['Total_Weekly_Job_Hrs'] = job_time_pivot[[d + '_Job_Hrs' for d in days]].sum(axis=1)
        
        # --- 3. Merge and Calculate Differences ---
        final_df = pd.merge(time_df, job_time_pivot, on='Name', how='left').fillna(0)
        
        display_dfs = {}
        for day in days:
            diff_col = day + '_Diff_Hrs'
            final_df[diff_col] = final_df[day + '_Clocked_Hrs'] - final_df[day + '_Job_Hrs']
            final_df[f'{day} Clocked'] = final_df[day + '_Clocked_Hrs'].apply(format_hm)
            final_df[f'{day} Job Time'] = final_df[day + '_Job_Hrs'].apply(format_hm)
            final_df[f'{day} Diff'] = final_df[diff_col].apply(format_hm)
            
            day_df = pd.DataFrame()
            day_df['Name'] = final_df['Name']
            day_df[f'{day} Clocked'] = final_df[f'{day} Clocked']
            day_df[f'{day} Job Time'] = final_df[f'{day} Job Time']
            day_df[f'{day} Diff'] = final_df[f'{day} Diff']
            display_dfs[day] = day_df
            
        manager_cols = ['Name']
        diff_cols_for_style = []
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            manager_cols.extend([f'{d} Clocked', f'{d} Job Time', f'{d} Diff'])
            diff_cols_for_style.append(f'{d} Diff')
            
        manager_df = final_df[manager_cols]
        display_dfs['Manager'] = manager_df
        
        final_df['Total_Weekly_Diff_Hrs'] = final_df['Total_Weekly_Clocked_Hrs'] - final_df['Total_Weekly_Job_Hrs']
        
        weekly_df = pd.DataFrame()
        weekly_df['Name'] = final_df['Name']
        weekly_df['Days Worked'] = final_df['Days_Worked']
        weekly_df['Total Clocked'] = final_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
        weekly_df['Total Job Time'] = final_df['Total_Weekly_Job_Hrs'].apply(format_hm)
        weekly_df['Total Diff'] = final_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
        display_dfs['Weekly'] = weekly_df
        
        # Build Export DF for the boss
        export_df = weekly_df.copy()
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            export_df[f'{d} Diff'] = final_df[f'{d} Diff']
        
        st.success("Files processed successfully!")
        
        # --- 4. Display Results in Tabs ---
        tab_names = ["Weekly Summary", "Manager Overview", "Individual Tech Report", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        tabs = st.tabs(tab_names)
        
        with tabs[0]:
            st.markdown('<h3 class="hide-on-print">Weekly Summary</h3>', unsafe_allow_html=True)
            styled_weekly = display_dfs['Weekly'].style.apply(highlight_weekly_row, axis=1)
            st.dataframe(styled_weekly, use_container_width=True)
            
            # Pass a unique key for the widgets on this tab
            show_advanced_reporting(ops_df, final_df, export_df, tab_key="summary_tab")
            
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
                        "Clocked Time": format_hm(tech_data[short_day + '_Clocked_Hrs']),
                        "Job Time": format_hm(tech_data[short_day + '_Job_Hrs']),
                        "Difference": format_hm(tech_data[short_day + '_Diff_Hrs'])
                    })
                
                report_data.append({
                    "Day": "TOTAL WEEKLY",
                    "Clocked Time": format_hm(tech_data['Total_Weekly_Clocked_Hrs']),
                    "Job Time": format_hm(tech_data['Total_Weekly_Job_Hrs']),
                    "Difference": format_hm(tech_data['Total_Weekly_Diff_Hrs'])
                })
                
                report_df = pd.DataFrame(report_data)
                try:
                    styled_report = report_df.style.hide(axis="index").apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                except Exception:
                    try:
                        styled_report = report_df.style.hide_index().apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                    except:
                        styled_report = report_df.style.apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                st.table(styled_report)
                st.markdown("---")
                
            # Pass a different unique key for the widgets on this tab
            show_advanced_reporting(ops_df, final_df, export_df, tab_key="manager_tab")
            
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
                        "Clocked Time": format_hm(tech_data[short_day + '_Clocked_Hrs']),
                        "Job Time": format_hm(tech_data[short_day + '_Job_Hrs']),
                        "Difference": format_hm(tech_data[short_day + '_Diff_Hrs'])
                    })
                
                report_data.append({
                    "Day": "TOTAL WEEKLY",
                    "Clocked Time": format_hm(tech_data['Total_Weekly_Clocked_Hrs']),
                    "Job Time": format_hm(tech_data['Total_Weekly_Job_Hrs']),
                    "Difference": format_hm(tech_data['Total_Weekly_Diff_Hrs'])
                })
                
                report_df = pd.DataFrame(report_data)
                try:
                    styled_report = report_df.style.hide(axis="index").apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                except Exception:
                    try:
                        styled_report = report_df.style.hide_index().apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                    except:
                        styled_report = report_df.style.apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                st.table(styled_report)
                st.markdown(f"**Total Days Clocked In:** {tech_days_worked}")

        day_mapping = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
        for i, full_day in enumerate(tab_names[3:]): 
            with tabs[i+3]:
                short_day = day_mapping[full_day]
                st.markdown(f'<h3 class="hide-on-print">{full_day} Breakdown</h3>', unsafe_allow_html=True)
                try:
                    styled_daily = display_dfs[short_day].style.map(highlight_daily, subset=[f'{short_day} Diff'])
                except AttributeError:
                    styled_daily = display_dfs[short_day].style.applymap(highlight_daily, subset=[f'{short_day} Diff'])
                st.dataframe(styled_daily, use_container_width=True)
            
    except Exception as e:
        st.error(f"An error occurred while processing the files: Please ensure you uploaded the correct CSV formats. Exact error: {e}")
