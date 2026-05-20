import streamlit as st
import pandas as pd
import numpy as np

# Set up the page layout
st.set_page_config(page_title="Tech Time Tracker", layout="wide")

# --- CSS FOR CLEAN PRINTING ---
st.markdown("""
<style>
@media print {
    /* Hide the top Streamlit header */
    header { display: none !important; }
    [data-testid="stHeader"] { display: none !important; }
    /* Hide file uploaders */
    [data-testid="stFileUploader"] { display: none !important; }
    /* Hide drop-down select boxes */
    [data-testid="stSelectbox"] { display: none !important; }
    /* Hide the tab navigation bar */
    div[data-baseweb="tab-list"] { display: none !important; }
    /* Hide the main website title */
    h1 { display: none !important; }
    /* Hide anything with this custom class */
    .hide-on-print { display: none !important; }
    /* Hide the green success alert */
    .stAlert { display: none !important; }
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

# --- Styling Functions ---
def parse_diff_to_hours(val):
    """Converts the H:MM string back to a float so we can check the hours"""
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
    """Highlights daily differences strictly greater than 1 hour"""
    hrs = parse_diff_to_hours(val)
    if hrs > 1.0:  
        return 'background-color: #ffcccc; color: #990000;'
    return ''

def highlight_weekly_row(row):
    """Highlights weekly diff if it exceeds (1 hour * Days Worked)"""
    styles = [''] * len(row)
    if 'Total Diff' in row and 'Days Worked' in row:
        diff_idx = row.index.get_loc('Total Diff')
        diff_hrs = parse_diff_to_hours(row['Total Diff'])
        days_worked = row['Days Worked']
        
        if diff_hrs > (days_worked * 1.0):
            styles[diff_idx] = 'background-color: #ffcccc; color: #990000;'
    return styles

def highlight_individual_report(row, days_worked):
    """Highlights the individual tech report based on daily/weekly rules"""
    styles = [''] * len(row)
    if 'Difference' in row and 'Day' in row:
        diff_idx = row.index.get_loc('Difference')
        diff_hrs = parse_diff_to_hours(row['Difference'])
        
        if row['Day'] == "TOTAL WEEKLY":
            if diff_hrs > (days_worked * 1.0):
                styles[diff_idx] = 'background-color: #ffcccc; color: #990000;'
        else:
            if diff_hrs > 1.0:
                styles[diff_idx] = 'background-color: #ffcccc; color: #990000;'
    return styles
# ------------------------------

# Only run the processing if both files are uploaded
if time_file and ops_file:
    try:
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
        ops_df['Job_Date_Parsed'] = pd.to_datetime(ops_df['Job_Date'].astype(str).str.replace(' GMT-0700', ''), errors='coerce')
        ops_df['Day_of_Week'] = ops_df['Job_Date_Parsed'].dt.day_name().str[:3]
        
        ops_df['Assigned Team Members'] = ops_df['Assigned Team Members'].astype(str).str.split(',')
        ops_df = ops_df.explode('Assigned Team Members')
        ops_df['Assigned Team Members'] = ops_df['Assigned Team Members'].str.strip()
        
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
            
            day_df = pd.DataFrame()
            day_df['Name'] = final_df['Name']
            day_df[f'{day} Clocked'] = final_df[day + '_Clocked_Hrs'].apply(format_hm)
            day_df[f'{day} Job Time'] = final_df[day + '_Job_Hrs'].apply(format_hm)
            day_df[f'{day} Diff'] = final_df[diff_col].apply(format_hm)
            display_dfs[day] = day_df
        
        final_df['Total_Weekly_Diff_Hrs'] = final_df['Total_Weekly_Clocked_Hrs'] - final_df['Total_Weekly_Job_Hrs']
        
        weekly_df = pd.DataFrame()
        weekly_df['Name'] = final_df['Name']
        weekly_df['Days Worked'] = final_df['Days_Worked']
        weekly_df['Total Clocked'] = final_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
        weekly_df['Total Job Time'] = final_df['Total_Weekly_Job_Hrs'].apply(format_hm)
        weekly_df['Total Diff'] = final_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
        display_dfs['Weekly'] = weekly_df
        
        st.success("Files processed successfully!")
        
        # --- 4. Display Results in Tabs ---
        tab_names = ["Weekly Summary", "Individual Tech Report", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        tabs = st.tabs(tab_names)
        
        with tabs[0]:
            st.markdown('<h3 class="hide-on-print">Weekly Summary</h3>', unsafe_allow_html=True)
            styled_weekly = display_dfs['Weekly'].style.apply(highlight_weekly_row, axis=1)
            st.dataframe(styled_weekly, use_container_width=True)
            
        with tabs[1]:
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
                
                styled_report = report_df.style.apply(lambda row: highlight_individual_report(row, tech_days_worked), axis=1)
                st.dataframe(styled_report, use_container_width=True, hide_index=True)
                
                st.markdown(f"**Total Days Clocked In:** {tech_days_worked}")

        day_mapping = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
        for i, full_day in enumerate(tab_names[2:]): 
            with tabs[i+2]:
                short_day = day_mapping[full_day]
                st.markdown(f'<h3 class="hide-on-print">{full_day} Breakdown</h3>', unsafe_allow_html=True)
                try:
                    styled_daily = display_dfs[short_day].style.map(highlight_daily, subset=[f'{short_day} Diff'])
                except AttributeError:
                    styled_daily = display_dfs[short_day].style.applymap(highlight_daily, subset=[f'{short_day} Diff'])
                    
                st.dataframe(styled_daily, use_container_width=True)
                
    except Exception as e:
        st.error(f"An error occurred while processing the files: Please ensure you uploaded the correct CSV formats. Exact error: {e}")
