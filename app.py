import streamlit as st
import pandas as pd
import numpy as np
import io
import re

# Set up the page layout
st.set_page_config(page_title="Tech Time Tracker", layout="wide")

# --- PERFORMANCE CACHING PIPELINE FUNCTIONS ---
def clean_duration_value(val):
    """Helper function to translate string durations like '9 hours 22 mins' or '9:22' into decimal hours."""
    if pd.isna(val) or str(val).strip() in ['-', '', '0', '0:00']:
        return 0.0
    s = str(val).lower().strip()
    try:
        # Handle HH:MM formats
        if ':' in s:
            parts = s.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return h + (m / 60.0)
        
        # Handle text formats like "9 hours 22 mins" or "9h 22m"
        h_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hour|hr|h)', s)
        m_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:min|m)', s)
        
        hours = float(h_match.group(1)) if h_match else 0.0
        minutes = float(m_match.group(1)) if m_match else 0.0
        
        if not h_match and not m_match:
            return float(s)
            
        return hours + (minutes / 60.0)
    except:
        return 0.0

@st.cache_data
def load_and_parse_timesheet(time_bytes):
    """Caches and parses raw timesheet CSV data safely handling manual entries and dynamic schemas without greedy overrides."""
    try:
        sample_df = pd.read_csv(io.BytesIO(time_bytes))
        columns_lower = [str(c).lower().strip() for c in sample_df.columns]
        
        # --- NON-GREEDY SCHEMA SELECTION ---
        # 1. Identify User Column Precisely
        user_col = None
        for target in ['user', 'employee', 'technician', 'employee name', 'tech name', 'username', 'name']:
            if target in columns_lower:
                user_col = sample_df.columns[columns_lower.index(target)]
                break
        if not user_col:
            for c in sample_df.columns:
                if 'user' in str(c).lower() or 'employee' in str(c).lower() or 'tech' in str(c).lower():
                    user_col = c
                    break
                    
        # 2. Identify Clock In Column Precisely
        in_col = None
        for target in ['clock in date/time', 'clock in', 'punch in', 'start time', 'clock-in']:
            if target in columns_lower:
                in_col = sample_df.columns[columns_lower.index(target)]
                break
        if not in_col:
            for c in sample_df.columns:
                if 'clock in' in str(c).lower() or 'punch in' in str(c).lower():
                    in_col = c
                    break

        # 3. Identify Clock Out Column Precisely
        out_col = None
        for target in ['clock out date/time', 'clock out', 'punch out', 'end time', 'clock-out']:
            if target in columns_lower:
                out_col = sample_df.columns[columns_lower.index(target)]
                break
        if not out_col:
            for c in sample_df.columns:
                if 'clock out' in str(c).lower() or 'punch out' in str(c).lower():
                    out_col = c
                    break

        # 4. Identify Duration Column Precisely
        duration_col = None
        for target in ['hours', 'duration', 'total hours', 'logged hours', 'pay hours', 'calculated hours', 'duration hrs', 'duration_hrs']:
            if target in columns_lower:
                duration_col = sample_df.columns[columns_lower.index(target)]
                break
        if not duration_col:
            for c in sample_df.columns:
                cl = str(c).lower()
                if 'hour' in cl or 'hrs' in cl or 'duration' in cl:
                    duration_col = c
                    break
                    
        # Apply strict renames
        rename_map = {}
        if user_col: rename_map[user_col] = 'User'
        if in_col: rename_map[in_col] = 'Clock In Date/Time'
        if out_col: rename_map[out_col] = 'Clock Out Date/Time'
        if duration_col: rename_map[duration_col] = 'Native_Duration'
        
        sample_df = sample_df.rename(columns=rename_map)
        
        if 'User' in sample_df.columns:
            # Extract standard dates and days of the week
            if 'Clock In Date/Time' in sample_df.columns and sample_df['Clock In Date/Time'].notna().any():
                sample_df['Clock_In_dt'] = pd.to_datetime(sample_df['Clock In Date/Time'], errors='coerce')
                sample_df['Day_of_Week'] = sample_df['Clock_In_dt'].dt.day_name().str[:3]
                sample_df['Date_Group'] = sample_df['Clock_In_dt'].dt.date
            else:
                sample_df['Day_of_Week'] = None
                sample_df['Date_Group'] = None
                
            # Fallback date scanning for manual entries missing punch-in timestamps
            if 'Date_Group' not in sample_df.columns or sample_df['Date_Group'].isna().all():
                sample_df['Date_Group'] = np.nan
            if 'Day_of_Week' not in sample_df.columns or sample_df['Day_of_Week'].isna().all():
                sample_df['Day_of_Week'] = np.nan
                
            for c in sample_df.columns:
                if 'date' in str(c).lower() and c not in ['Date_Group', 'Clock In Date/Time', 'Clock Out Date/Time']:
                    parsed_dates = pd.to_datetime(sample_df[c], errors='coerce')
                    sample_df['Date_Group'] = sample_df['Date_Group'].fillna(parsed_dates.dt.date)
                    sample_df['Day_of_Week'] = sample_df['Day_of_Week'].fillna(parsed_dates.dt.day_name().str[:3])
            
            # --- STEP 1: CALCULATE DURATION ---
            if 'Native_Duration' in sample_df.columns:
                sample_df['Duration_Hrs'] = sample_df['Native_Duration'].apply(clean_duration_value)
            else:
                sample_df['Clock_In_dt'] = pd.to_datetime(sample_df['Clock In Date/Time'], errors='coerce')
                sample_df['Clock_Out_dt'] = pd.to_datetime(sample_df['Clock Out Date/Time'], errors='coerce') 
                sample_df['Duration_Hrs'] = (sample_df['Clock_Out_dt'] - sample_df['Clock_In_dt']).dt.total_seconds() / 3600.0
            
            sample_df['Duration_Hrs'] = sample_df['Duration_Hrs'].fillna(0.0)
            sample_df['Day_of_Week'] = sample_df['Day_of_Week'].fillna('Thu')
            
            # --- STEP 2: AUTOMATIC OVERRIDE DEDUREPLICATION ---
            if 'Clock In Date/Time' in sample_df.columns and 'Native_Duration' in sample_df.columns:
                sample_df['Is_Manual_Edit'] = (
                    sample_df['Clock In Date/Time'].isna() | 
                    sample_df['Clock Out Date/Time'].isna() | 
                    sample_df['Native_Duration'].astype(str).str.contains('hour|min|h|m', case=False, na=False)
                )
                
                manual_edits = sample_df[sample_df['Is_Manual_Edit'] & sample_df['Date_Group'].notna()]
                days_with_manuals = set(zip(manual_edits['User'], manual_edits['Date_Group']))
                
                if days_with_manuals:
                    def drop_ghost_punches(row):
                        if pd.isna(row['Date_Group']):
                            return True
                        if (row['User'], row['Date_Group']) in days_with_manuals and not row['Is_Manual_Edit']:
                            return False 
                        return True
                        
                    sample_df = sample_df[sample_df.apply(drop_ghost_punches, axis=1)]

            # --- STEP 3: CONSTRUCT DOWNSTREAM MATRIX ---
            pivot_df = sample_df.groupby(['User', 'Day_of_Week'])['Duration_Hrs'].sum().unstack(fill_value=0.0).reset_index()
            days_order = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
            for d in days_order:
                if d not in pivot_df.columns:
                    pivot_df[d] = 0.0
            pivot_df = pivot_df[['User'] + days_order]
            pivot_df.columns = ['Name'] + [d + '_Clocked_Hrs' for d in days_order]
            pivot_df['Total_Weekly_Clocked_Hrs'] = pivot_df[[d + '_Clocked_Hrs' for d in days_order]].sum(axis=1)
            return pivot_df, sample_df
            
    except Exception as e:
        st.sidebar.error(f"Timesheet structural parse alert: {e}")
    
    # Fallback to manual line parser for custom CSV output text streams
    time_content = time_bytes.decode("utf-8").splitlines()
    time_lines = time_content[1:] 
    data = []
    for i in range(0, len(time_lines), 9):
        if i + 8 < len(time_lines):
            name = time_lines[i].strip().rstrip(',').strip('"')
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
    days_order = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    for col in days_order + ['Total_Weekly']: 
        time_df[col + '_Clocked_Hrs'] = time_df[col].apply(parse_hm)
    return time_df, pd.DataFrame()

@st.cache_data
def load_and_parse_ops(ops_bytes):
    """Caches and executes precision timedelta parsing utilizing dynamic schema mapping to prevent header changes from breaking the app."""
    try:
        ops_df = pd.read_csv(io.BytesIO(ops_bytes), header=0)
        if not any('assigned' in str(c).lower() and 'team' in str(c).lower() for c in ops_df.columns):
            ops_df = pd.read_csv(io.BytesIO(ops_bytes), header=1)
    except:
        ops_df = pd.read_csv(io.BytesIO(ops_bytes), header=1)
        
    # --- DYNAMIC SCHEMA NORMALIZATION (SCHEMA PROTECTION) ---
    cols = ops_df.columns.astype(str).tolist()
    
    rename_map = {}
    for c in cols:
        cl = c.lower()
        if 'assigned' in cl and 'team' in cl and 'members' in cl: rename_map[c] = 'Assigned Team Members'
        elif 'invoice' in cl and 'amount' in cl: rename_map[c] = 'Total Invoice Amount'
        elif 'business' in cl and 'unit' in cl: rename_map[c] = 'Business Unit'
        elif 'location' in cl and 'address' in cl: rename_map[c] = 'Location Address'
        elif 'product' in cl and 'cost' in cl: rename_map[c] = 'Total Product Cost [tax inc]'
        elif 'service' in cl and 'cost' in cl and 'invoice' in cl: rename_map[c] = 'Invoice - Total Service Cost'
        
    ops_df = ops_df.rename(columns=rename_map)
    
    if 'Assigned Team Members' not in ops_df.columns:
        ops_df['Assigned Team Members'] = None
        
    ops_df = ops_df.dropna(subset=['Assigned Team Members'])
    
    cols = ops_df.columns.astype(str).tolist()
    store_time_cols = [c for c in cols if 'store' in c.lower() and 'time' in c.lower() and 'timestamp' not in c.lower()]
    drive_time_cols = [c for c in cols if 'way' in c.lower() and 'time' in c.lower() and 'timestamp' not in c.lower()]
    prog_time_cols = [c for c in cols if 'progress' in c.lower() and 'time' in c.lower() and 'timestamp' not in c.lower()]
    
    time_cols = store_time_cols + drive_time_cols + prog_time_cols
    
    for col in time_cols:
        clean_times = ops_df[col].astype(str).replace('-', '00:00:00')
        ops_df[col] = pd.to_timedelta(clean_times, errors='coerce').dt.total_seconds().fillna(0)
        
    store_ts_cols = [c for c in cols if 'store' in c.lower() and 'timestamp' in c.lower()]
    drive_ts_cols = [c for c in cols if 'way' in c.lower() and 'timestamp' in c.lower()]
    prog_ts_cols = [c for c in cols if 'progress' in c.lower() and 'timestamp' in c.lower()]
    ts_cols = store_ts_cols + drive_ts_cols + prog_ts_cols
    
    return ops_df, store_time_cols, drive_time_cols, prog_time_cols, time_cols, ts_cols

# --- CSS FOR CLEAN LANDSCAPE FULL-WIDTH MULTI-PAGE PRINTING ---
st.markdown("""
<style>
@media print {
    @page {
        size: landscape;
        margin: 0.4in !important;
    }
    header { display: none !important; }
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; section[data-testid="stSidebar"] { display: none !important; } [data-testid="stSidebarCollapseButton"] { display: none !important; } }
    [data-testid="stFileUploader"] { display: none !important; }
    [data-testid="stSelectbox"] { display: none !important; }
    div[data-baseweb="tab-list"] { display: none !important; }
    h1, .hide-on-print, .stAlert, iframe, button { display: none !important; }
    div[class*="stExpander"] { display: none !important; }
    
    div[class*="stVerticalBlock"], 
    div[data-testid="element-container"],
    div[data-testid="stHorizontalBlock"],
    div[data-testid="column"] {
        display: block !important;
        position: static !important;
        float: none !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 100% !important;
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
        margin: 0 0 15px 0 !important;
        padding: 0 !important;
        box-shadow: none !important;
    }
    
    h2, h3, h4 {
        page-break-inside: avoid !important;
        page-break-after: avoid !important;
        margin-top: 20px !important;
        margin-bottom: 8px !important;
    }

    div[data-testid="stAppViewBlockContainer"],
    .main .block-container,
    div[class*="block-container"] {
        max-width: 100% !important;
        width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: wrap !important;
        width: 100% !important;
        gap: 12px !important;
    }
    div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) div[data-testid="column"] {
        display: inline-block !important;
        flex: 1 1 0% !important;
        min-width: 100px !important;
        width: auto !important;
        max-width: none !important;
        margin: 0 !important;
    }
    
    div[data-testid="stTable"], 
    div[data-testid="stTable"] > div,
    div[data-testid="stDataFrame"],
    div[data-testid="stDataFrame"] > div,
    table {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 100% !important;
        display: block !important;
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
    }
    
    table {
        border-collapse: collapse !important;
        margin: 0 0 15px 0 !important;
    }
    tr {
        page-break-inside: avoid !important;
    }
    th, td {
        white-space: normal !important;
        word-break: break-word !important;
        overflow-wrap: break-word !important;
        padding: 4px 5px !important;
        font-size: 9.5px !important;
        text-align: left !important;
        line-height: 1.25 !important;
    }
    thead {
        display: table-header-group !important;
    }
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
    if 'First_Punch' not in row or 'First_Status' not in row: return False
    fp = row['First_Punch']
    status = row['First_Status']
    if pd.isna(fp): return False
    if status in ['On The Way', 'Lowes Store']:
        return fp.hour >= 8
    elif status == 'In Progress':
        return fp.hour > 8 or (fp.hour == 8 and fp.minute >= 30)
    return False

def check_contractor(tech_str):
    CORE_TECHS = ['Bryan Pickett', 'Erik Tange', 'Mathew Hodges', 'Matt Schlosser', 'Michael Owens', 'Nathan Smith', 'Sean Marble', 'Tanner LaForge']
    raw_members = [m.strip() for m in str(tech_str).split(',') if m.strip()]
    return not any(m in CORE_TECHS for m in raw_members)

def parse_az_city(addr):
    s = str(addr).lower()
    for c in ["prescott", "chandler", "scottsdale", "phoenix", "goodyear", "mesa", "glendale", "gilbert", "tempe", "peoria", "surprise", "buckeye", "avondale", "tucson", "marana", "maricopa", "sierra vista", "green valley"]:
        if c in s:
            return c.title()
    return "Phoenix Region"

def highlight_matrix_overhead(s):
    styles = []
    for val in s:
        try:
            if ' (Div: ' in str(val):
                tech_str, div_str = val.split(' (Div: ')
                t_h = parse_hm(tech_str)
                d_h = parse_hm(div_str.replace(')', ''))
                if hasattr(s, 'name') and s.name == 'Avg WH Time':
                    if t_h > d_h and t_h > 0:
                        styles.append('background-color: #ffcccc; color: #990000;')
                        continue
                else:
                    if t_h > d_h * 1.25 and t_h > 0:
                        styles.append('background-color: #ffcccc; color: #990000;')
                        continue
            styles.append('')
        except:
            styles.append('')
    return styles

def highlight_over_hour_row(row):
    styles = [''] * len(row)
    if 'Over Division Average By' in row.index:
        val = row['Over Division Average By']
        if '+' in str(val):
            hrs = parse_hm(str(val).replace('+', ''))
            if hrs > 1.0:
                return ['background-color: #ffcccc; color: #990000; font-weight: bold;'] * len(row)
    return styles

def get_assumed_pay(row):
    if 'Name' not in row or isinstance(row, bool): return 0.0
    nl = str(row['Name']).lower()
    clocked = row.get('Total_Weekly_Clocked_Hrs', 0.0)
    rev = row.get('Total_Assigned_Revenue', 0.0)
    
    if 'sean marble' in nl:
        base_salary = 70000.0 / 52.0
        penalty_burden = st.session_state.get('sean_absence_penalty_global', 0.0)
        return max(0.0, base_salary - penalty_burden)
    if 'michael owens' in nl or 'mathew hodges' in nl:
        return 65000.0 / 52.0
    if 'bryan' in nl or 'erik' in nl:
        return rev * 0.34
        
    rate = 0.0
    if 'nate' in nl or 'nathan' in nl:
        rate = 22.50
    elif 'tanner' in nl or 'matt schlosser' in nl:
        rate = 25.00
        
    if rate > 0:
        if clocked > 40.0:
            return (40.0 * rate) + ((clocked - 40.0) * rate * 1.5)  
        else:
            return clocked * rate
    return 0.0

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

def highlight_low_margins(row):
    styles = [''] * len(row)
    if 'Line of Business' in row and 'Margin %' in row:
        try:
            bu = row['Line of Business']
            m_val = float(str(row['Margin %']).replace('%', '').strip())
            if 'Water Heaters' in bu and m_val < 35.0:
                return ['background-color: #ffcccc; color: #990000; font-weight: bold;'] * len(row)
            elif 'Simple Installs' in bu and m_val < 45.0:
                return ['background-color: #ffcccc; color: #990000; font-weight: bold;'] * len(row)
        except:
            pass
    return styles

def get_adjusted_table_pay(row):
    if isinstance(row, bool) or 'Name' not in row: return 0.0
    nl = str(row['Name']).lower()
    base_pay = get_assumed_pay(row)
    if 'sean marble' in nl:
        return max(0.0, base_pay)
    return base_pay

def create_copy_button(df, raw_key):
    safe_key = "".join([c if c.isalnum() else "_" for c in raw_key])
    tsv_str = df.to_csv(sep='\t', index=False)
    safe_tsv = tsv_str.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
    
    button_html = f"""
    <div class="hide-on-print" style="text-align: left; margin-top: 5px; margin-bottom: 8px;">
        <textarea id="tsv_{safe_key}" style="position: absolute; left: -9999px;">{safe_tsv}</textarea>
        <button id="btn_{safe_key}" onclick="copyTSV_{safe_key}()" style="background-color: #ffffff; color: #3c4043; padding: 6px 14px; border: 1px solid #dadce0; border-radius: 4px; cursor: pointer; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: background-color 0.2s;">
            📋 Copy Table Data (For Email/Sheets/Docs)
        </button>
    </div>
    <script>
    function copyTSV_{safe_key}() {{
        var copyText = document.getElementById("tsv_{safe_key}");
        copyText.select();
        copyText.setSelectionRange(0, 999999);
        try {{
            var successful = document.execCommand('copy');
            var btn = document.getElementById("btn_{safe_key}");
            if (successful) {{
                btn.innerHTML = "✅ Copied table to clipboard!";
                btn.style.backgroundColor = "#e6f4ea";
                btn.style.color = "#137333";
                btn.style.borderColor = "#137333";
                setTimeout(function() {{
                    btn.innerHTML = "📋 Copy Table Data (For Email/Sheets/Docs)";
                    btn.style.backgroundColor = "#ffffff";
                    btn.style.color = "#3c4043";
                    btn.style.borderColor = "#dadce0";
                }}, 2000);
                }} else {{
                btn.innerHTML = "❌ Copy failed";
            }}
        }} catch (err) {{
            console.error('Execution fallback error:', err);
        }}
    }}
    </script>
    """
    st.components.v1.html(button_html, height=38)

def run_baselines_matrix(ops_df):
    st.markdown("<h4>Advanced Team Processing Baselines Matrix</h4>", unsafe_allow_html=True)
    st.markdown("*(Technician tracking averages sorted by highest un-blended weekly duration totals. Store times ignore direct-to-site jobs)*")
    
    wh_jobs = ops_df[ops_df['Business Unit'] == 'Lowes - Water Heaters']
    lsi_jobs = ops_df[ops_df['Business Unit'] == 'Lowes - Simple Installs']
    
    div_avg_total = ops_df['Total_Job_Time_Hours'].mean() if not ops_df.empty else 0.0
    div_wh_baseline = wh_jobs['Total_Job_Time_Hours'].mean() if not wh_jobs.empty else 3.5
    div_lsi_baseline = lsi_jobs['Total_Job_Time_Hours'].mean() if not lsi_jobs.empty else 2.0
    
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
            max_job_id = tech_jobs.loc[max_idx, '#ID'] if '#ID' in tech_jobs.columns else 'Unknown'
            if isinstance(max_job_id, float) and max_job_id.is_integer():
                max_job_id = int(max_job_id)
            max_job_str = f"{format_hm(max_job_val)} (ID: {max_job_id})"
        else:
            max_job_str = "-"
            
        if pd.notna(div_wh_baseline):
            for _, j in t_wh[t_wh['Total_Job_Time_Hours'] > div_wh_baseline].iterrows():
                jid = int(j['#ID']) if ('#ID' in j and isinstance(j['#ID'], float) and j['#ID'].is_integer()) else (j['#ID'] if '#ID' in j else 'Unknown')
                diff_val = j['Total_Job_Time_Hours'] - div_wh_baseline
                wh_over_baseline_rows.append({
                    "Technician": tech_name,
                    "Job ID": str(jid),
                    "Job Duration": format_hm(j['Total_Job_Time_Hours']),
                    "Over Division Average By": f"+{format_hm(diff_val)}",
                    "sort_key": diff_val
                })
        
        if pd.notna(div_lsi_baseline):
            for _, j in t_lsi[t_lsi['Total_Job_Time_Hours'] > div_lsi_baseline].iterrows():
                jid = int(j['#ID']) if ('#ID' in j and isinstance(j['#ID'], float) and j['#ID'].is_integer()) else (j['#ID'] if '#ID' in j else 'Unknown')
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
        
    create_copy_button(matrix_df, "baselines_matrix")
        
    st.markdown("<br><h4>🚨 Individual Over-Baseline Job Reference Breakdown</h4>", unsafe_allow_html=True)
    st.markdown("*(Granular tracking sheets isolating individual work orders exceeding the division run baselines, sorted largest variation to lowest. Rows >1 hour over are highlighted)*")
    
    split_col1, split_col2 = st.columns(2)
    with split_col1:
        st.markdown("##### 🛢️ Water Heaters Over-Baseline Jobs")
        if wh_over_baseline_rows:
            wh_matrix_df = pd.DataFrame(wh_over_baseline_rows).sort_values(by='sort_key', ascending=False).drop(columns=['sort_key']).reset_index(drop=True)
            try: st.dataframe(wh_matrix_df.style.apply(highlight_over_hour_row, axis=1), use_container_width=True)
            except Exception: st.dataframe(wh_matrix_df, use_container_width=True)
            copy_key = f"wh_over_baseline_{int(pd.Timestamp.now().timestamp())}"
            create_copy_button(wh_matrix_df, copy_key)
        else: st.success("✅ Zero individual Water Heater jobs exceeded the division baseline average.")
            
    with split_col2:
        st.markdown("##### 🔧 Simple Installs Over-Baseline Jobs")
        if lsi_over_baseline_rows:
            lsi_matrix_df = pd.DataFrame(lsi_over_baseline_rows).sort_values(by='sort_key', ascending=False).drop(columns=['sort_key']).reset_index(drop=True)
            try: st.dataframe(lsi_matrix_df.style.apply(highlight_over_hour_row, axis=1), use_container_width=True)
            except Exception: st.dataframe(lsi_matrix_df, use_container_width=True)
            copy_key = f"lsi_over_baseline_{int(pd.Timestamp.now().timestamp())}"
            create_copy_button(lsi_matrix_df, copy_key)
        else: st.success("✅ Zero individual Simple Install jobs exceeded the division baseline average.")

def run_job_type_breakdown_matrix(ops_df):
    st.markdown("<h4>📋 Advanced Job Type Length Breakdown</h4>", unsafe_allow_html=True)
    st.markdown("*(Comprehensive breakdown of average, minimum, and maximum job duration lengths across all business units)*")
    
    if 'Business Unit' not in ops_df.columns:
        st.warning("Business Unit data is not available to create this breakdown.")
        return
        
    job_type_stats = ops_df.groupby('Business Unit').agg(
        Total_Jobs=('#ID', 'count'),
        Avg_Job_Time=('Total_Job_Time_Hours', 'mean'),
        Min_Job_Time=('Total_Job_Time_Hours', 'min'),
        Max_Job_Time=('Total_Job_Time_Hours', 'max'),
        Avg_Store_Time=('Store_Time_Hrs', lambda x: x[x > 0].mean() if len(x[x > 0]) > 0 else 0.0)
    ).reset_index()
    
    job_type_stats['Avg Job Length'] = job_type_stats['Avg_Job_Time'].apply(format_hm)
    job_type_stats['Min Job Length'] = job_type_stats['Min_Job_Time'].apply(format_hm)
    job_type_stats['Max Job Length'] = job_type_stats['Max_Job_Time'].apply(format_hm)
    job_type_stats['Avg Store Delay'] = job_type_stats['Avg_Store_Time'].apply(format_hm)
    
    job_type_stats = job_type_stats.sort_values('Total_Jobs', ascending=False)
    display_df = job_type_stats[['Business Unit', 'Total_Jobs', 'Avg Job Length', 'Min Job Length', 'Max Job Length', 'Avg Store Delay']]
    display_df = display_df.rename(columns={'Business Unit': 'Job Type', 'Total_Jobs': 'Total Dispatches Closed'})
    
    st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
    create_copy_button(display_df, "job_type_breakdown_matrix")

def show_advanced_reporting(unexploded_ops, ops_df, final_df, bounds_df, delayed_launches_df, daily_route, tab_key):
    st.markdown('<div class="hide-on-print"><br><hr><br></div>', unsafe_allow_html=True)
    st.header("📊 Ops Manager Tools (Benchmarking & Performance)")
    
    run_baselines_matrix(ops_df)
    st.markdown("<br><hr><br>", unsafe_allow_html=True)
    
    run_job_type_breakdown_matrix(ops_df)
    st.markdown("<br><hr><br>", unsafe_allow_html=True)
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("⭐ The Gold Star High-Performer List")
        st.markdown("*(Technicians who average under 1:30 of unallocated difference per day worked. Store delays do NOT penalize techs)*")
        gold_star_df = final_df[(final_df['Daily_Avg_Diff_Hrs'] < 1.5) & (final_df['Days_Worked'] > 0)].copy()
        if not gold_star_df.empty:
            gold_star_df = gold_star_df.sort_values(by='Daily_Avg_Diff_Hrs', ascending=True)
            gold_star_df['Total Clocked'] = gold_star_df['Total_Weekly_Clocked_Hrs'].copy().apply(format_hm)
            gold_star_df['Total Job Time'] = gold_star_df['Total_Weekly_Job_Hrs'].apply(format_hm)
            gold_star_df['Daily Avg Diff'] = gold_star_df['Daily_Avg_Diff_Hrs'].apply(format_hm)
            gold_star_df['Total Diff'] = gold_star_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
            show_gold = gold_star_df[['Name', 'Total Clocked', 'Total Job Time', 'Daily Avg Diff', 'Total Diff']].copy()
            
            try: st.dataframe(show_gold.reset_index(drop=True).style.set_properties(**{'background-color': '#e6f4ea', 'color': '#137333'}), use_container_width=True)
            except Exception: st.dataframe(show_gold.reset_index(drop=True), use_container_width=True)
            create_copy_button(show_gold.reset_index(drop=True), f"gold_star_{tab_key}")

    with col_right:
        st.subheader("🎯 The Technician Skill Matrix & Training Flag")
        st.markdown("*(Compares a technician's LSI performance against their WH performance. Flags techs where the gap exceeds 15% sorted by priority warnings)*")
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
            
            skill_df['sort_action'] = skill_df['Action Required'].apply(lambda x: 0 if '⚠️' in str(x) else (1 if 'ℹ️' in str(x) else 2))
            skill_df = skill_df.sort_values(by='sort_action', ascending=True)
            
            show_skill = skill_df[['Name', 'Simple Installs Eff', 'Water Heaters Eff', 'Action Required']].rename(columns={'Simple Installs Eff': 'LSI Efficiency', 'Water Heaters Eff': 'WH Efficiency'})
            def style_flags(row): return ['background-color: #fff3cd; color: #856404; font-weight: bold;'] * len(row) if '⚠️' in row['Action Required'] else [''] * len(row)
            try: st.dataframe(show_skill.reset_index(drop=True).style.apply(style_flags, axis=1), use_container_width=True)
            except Exception: st.dataframe(show_skill.reset_index(drop=True), use_container_width=True)
            create_copy_button(show_skill.reset_index(drop=True), f"skills_{tab_key}")

    st.markdown("<br><h4>🗺️ Route Optimization Flags</h4>", unsafe_allow_html=True)
    st.markdown("*(Identifies service days where a technician spent over 40% of their billable shift driving to audit route density)*")
    poor_routes = daily_route[daily_route['Drive %'] > 40.0].copy()
    if not poor_routes.empty:
        poor_routes = poor_routes.sort_values(by='Drive %', ascending=False)
        poor_routes['Drive %'] = poor_routes['Drive %'].apply(lambda x: f"{x:.1f}%")
        poor_routes['Drive Time'] = poor_routes['Drive_Time_Hrs'].apply(format_hm)
        poor_routes['Work Time'] = poor_routes['In_Progress_Time_Hrs'].apply(format_hm)
        route_df_export = poor_routes[['Assigned Team Members', 'Short_Date', 'Job_Count', 'Drive Time', 'Work Time', 'Drive %']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date', 'Job_Count': 'Jobs'}).reset_index(drop=True)
        st.dataframe(route_df_export, use_container_width=True)
        create_copy_button(route_df_export, f"routes_{tab_key}")
    else: st.success("✅ Great density alignment! No single transport lane routing fell below benchmark efficiency requirements.")

    st.markdown("<br>", unsafe_allow_html=True)
    launch_col, launch_empty_col = st.columns(2)
    with launch_col:
        st.markdown("<h4>📊 Late Deployment Scorecard</h4>", unsafe_allow_html=True)
        st.markdown("*(Aggregates the total number of delayed morning launches per technician across the week)*")
        if not delayed_launches_df.empty:
            launch_counts = delayed_launches_df.groupby('Assigned Team Members').size().reset_index(name='Total Late Days').sort_values(by='Total Late Days', ascending=False)
            try: st.dataframe(launch_counts.reset_index(drop=True).style.set_properties(**{'background-color': '#fff3cd', 'color': '#856404;'}, subset=['Total Late Days']), use_container_width=True)
            except Exception: st.dataframe(launch_counts.reset_index(drop=True), use_container_width=True)
            create_copy_button(launch_counts.reset_index(drop=True).rename(columns={'Assigned Team Members': 'Name'}), f"late_score_{tab_key}")
        else: st.success("✅ Zero morning momentum delays recorded for core internal dispatches.")

    with launch_empty_col:
        st.markdown("<h4>🚗 Delayed Launch Alert</h4>", unsafe_allow_html=True)
        st.markdown("*(Provides a day-by-day chronological log of start-of-day timeline compliance delays)*")
        if not delayed_launches_df.empty:
            tech_late_list = sorted(delayed_launches_df['Assigned Team Members'].unique())
            most_late_tech = delayed_launches_df['Assigned Team Members'].value_counts().idxmax()
            default_late_idx = tech_late_list.index(most_late_tech) if most_late_tech in tech_late_list else 0
            
            selected_late_tech = st.selectbox("Select Tech to view launch times:", tech_late_list, index=default_late_idx, key=f"late_launch_{tab_key}")
            if selected_late_tech:
                tech_launches_df = delayed_launches_df[delayed_launches_df['Assigned Team Members'] == selected_late_tech].copy()
                tech_launches_df['First Punch log'] = tech_launches_df['First_Punch'].dt.strftime('%I:%M %p') + " (" + tech_launches_df['First_Status'] + ")"
                show_launches = tech_launches_df.sort_values(by='First_Punch', ascending=False)[['Short_Date', 'First Punch log']].rename(columns={'Short_Date': 'Date'}).reset_index(drop=True)
                try: st.dataframe(show_launches.style.set_properties(**{'background-color': '#ffcccc', 'color': '#990000;'}), use_container_width=True)
                except Exception: st.dataframe(show_launches, use_container_width=True)
                create_copy_button(show_launches, f"late_alert_{tab_key}")
        else: st.info("No timeline momentum compliance delays located inside current operational data streams.")

# --- THE MAIN TOP-LEVEL BASE EXECELINE PIPELINE LAYER BLOCK ---
st.sidebar.header("📂 Data Loading Pipeline")
time_file = st.sidebar.file_uploader("Upload Time Sheet (CSV)", type=['csv'])
ops_file = st.sidebar.file_uploader("Upload Lowes Ops Export (CSV)", type=['csv'])

if time_file and ops_file:
    try:
        CORE_TECHS = ['Bryan Pickett', 'Erik Tange', 'Mathew Hodges', 'Matt Schlosser', 'Michael Owens', 'Nathan Smith', 'Sean Marble', 'Tanner LaForge']
        
        st.sidebar.header("⏱️ Manual Time Adjustments")
        st.sidebar.markdown("*(Adjust weekly clocked hours. Use formats like `+1:30`, `-0:45`, or `1.5`)*")
        time_adjustments = {}
        
        with st.sidebar.expander("Expand to Adjust Timecards"):
            for tech in CORE_TECHS:
                adj_val = st.text_input(tech, key=f"adj_input_{tech}", placeholder="e.g. +1:30 or -0.5")
                if adj_val:
                    time_adjustments[tech] = parse_adj_hm(adj_val)
        
        # --- 1. Parser Engine for Time Sheets ---
        time_bytes = time_file.getvalue()
        time_df, sample_df = load_and_parse_timesheet(time_bytes)
        
        time_df = time_df[time_df['Name'].isin(CORE_TECHS)]
        
        for tech, adj in time_adjustments.items():
            if tech in time_df['Name'].values:
                time_df.loc[time_df['Name'] == tech, 'Total_Weekly_Clocked_Hrs'] += adj
        
        days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        time_df['Days_Worked'] = (time_df[[f'{d}_Clocked_Hrs' for d in days]] > 0).sum(axis=1)
        
        # --- 2. Parse Ops Sheet Resiliently ---
        ops_bytes = ops_file.getvalue()
        ops_df, store_time_cols, drive_time_cols, prog_time_cols, time_cols, available_ts_cols = load_and_parse_ops(ops_bytes)
            
        ops_df['Total Invoice Amount'] = pd.to_numeric(ops_df.get('Total Invoice Amount', pd.Series([0]*len(ops_df))), errors='coerce').fillna(0.0)
        
        ops_df['Store_Time_Hrs'] = ops_df[store_time_cols].sum(axis=1) / 3600.0 if store_time_cols else 0.0
        ops_df['Drive_Time_Hrs'] = ops_df[drive_time_cols].sum(axis=1) / 3600.0 if drive_time_cols else 0.0
        ops_df['In_Progress_Time_Hrs'] = ops_df[prog_time_cols].sum(axis=1) / 3600.0 if prog_time_cols else 0.0
        ops_df['Total_Job_Time_Hours'] = ops_df[time_cols].sum(axis=1) / 3600.0 if time_cols else 0.0

        if available_ts_cols:
            ops_df['Job_Date'] = ops_df[available_ts_cols].replace('-', np.nan).bfill(axis=1).iloc[:, 0]
        else:
            ops_df['Job_Date'] = np.nan
        
        for c in available_ts_cols: ops_df[c + '_dt'] = pd.to_datetime(ops_df[c].astype(str).str.split(' GMT').str[0], errors='coerce')
        available_ts_dt_cols = [c + '_dt' for c in available_ts_cols]
        
        if available_ts_dt_cols:
            ops_df['Earliest_Start'] = ops_df[available_ts_dt_cols].min(axis=1)
        else:
            ops_df['Earliest_Start'] = pd.NaT
            
        ops_df['Estimated_End'] = ops_df['Earliest_Start'] + pd.to_timedelta(ops_df['Total_Job_Time_Hours'] * 3600, unit='s')
        ops_df['Job_Date_Parsed'] = pd.to_datetime(ops_df['Job_Date'].astype(str).str.split(' GMT').str[0], errors='coerce')
        ops_df['Day_of_Week'] = ops_df['Job_Date_Parsed'].dt.day_name().str[:3]
        ops_df['Short_Date'] = ops_df['Job_Date_Parsed'].dt.strftime('%m-%d-%Y')
        
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
            cl = str(col).lower()
            if 'store' in cl: return 'Lowes Store'
            if 'way' in cl: return 'On The Way'
            return 'In Progress'
            
        ops_df['Earliest_Status'] = ops_df['Earliest_Status_Col'].apply(map_status)

        unexploded_ops = ops_df.copy()
        raw_unsplit_volume = unexploded_ops['Total Invoice Amount'].sum()
        
        validation_warnings = []
        for _, r in unexploded_ops.iterrows():
            raw_members = [m.strip() for m in str(r['Assigned Team Members']).split(',') if m.strip()]
            core_members_on_job = [m for m in raw_members if m in CORE_TECHS]
            for member in core_members_on_job:
                if member in ['Bryan Pickett', 'Sean Marble', 'Erik Tange'] and r.get('Business Unit') == 'Lowes - Water Heaters':
                    jid = int(r['#ID']) if ('#ID' in r and pd.notna(r['#ID'])) else "Unknown"
                    validation_warnings.append(f"⚠️ **Upstream Discrepancy Warning:** {member} is listed on Water Heater job ID **#{jid}** (${r['Total Invoice Amount']:,.2f}) which impacts individual lines of business metric splits.")
        
        # --- FIX 1: REVENUE SPLIT & ROW EXPLOSION ---
        exploded_rows = []
        for idx, row in ops_df.iterrows():
            raw_members = [m.strip() for m in str(row['Assigned Team Members']).split(',') if m.strip()]
            core_members_on_job = [m for m in raw_members if m in CORE_TECHS]
            
            if not core_members_on_job:
                continue
                
            split_revenue = row['Total Invoice Amount'] / len(core_members_on_job)
            
            for member in core_members_on_job:
                new_row = row.copy()
                new_row['Assigned Team Members'] = member
                new_row['Total Invoice Amount'] = split_revenue
                exploded_rows.append(new_row)
                
        if exploded_rows:
            ops_df = pd.DataFrame(exploded_rows).reset_index(drop=True)
        else:
            ops_df = pd.DataFrame(columns=ops_df.columns)

        ops_df['Name'] = ops_df['Assigned Team Members']

        # --- FIX 2: MORNING LAUNCH BIAS (Calculated Post-Explosion) ---
        ops_for_bounds = ops_df.dropna(subset=['Name', 'Earliest_Start']).copy()
        ops_sorted = ops_for_bounds.sort_values(['Name', 'Earliest_Start'])
        
        bounds_df = ops_sorted.groupby(['Name', 'Short_Date']).agg(
            First_Punch=('Earliest_Start', 'min'),
            Last_Punch=('Estimated_End', 'max'),
            First_Status=('Earliest_Status', 'first')
        ).reset_index()
        
        bounds_df = bounds_df.rename(columns={'Name': 'Assigned Team Members'})
        bounds_df['First Status Update'] = bounds_df['First_Punch'].dt.strftime('%I:%M %p')
        bounds_df['Last Status Update'] = bounds_df['Last_Punch'].dt.strftime('%I:%M %p')
        bounds_df['Total_Span_Hrs'] = (bounds_df['Last_Punch'] - bounds_df['First_Punch']).dt.total_seconds() / 3600.0
        bounds_df['Total Time'] = bounds_df['Total_Span_Hrs'].apply(format_hm)
        
        delayed_launches_df = bounds_df[bounds_df.apply(check_late, axis=1)].copy()

        ops_df['Store_Time_Hrs'] = ops_df[store_time_cols].sum(axis=1) / 3600.0 if store_time_cols else 0.0
        ops_df['Drive_Time_Hrs'] = ops_df[drive_time_cols].sum(axis=1) / 3600.0 if drive_time_cols else 0.0
        ops_df['In_Progress_Time_Hrs'] = ops_df[prog_time_cols].sum(axis=1) / 3600.0 if prog_time_cols else 0.0
        ops_df['Total_Job_Time_Hours'] = ops_df[time_cols].sum(axis=1) / 3600.0 if time_cols else 0.0

        if 'Business Unit' in ops_df.columns:
            bu_agg = ops_df.groupby(['Name', 'Business Unit']).agg(Total_Job_Time_Hours=('Total_Job_Time_Hours', 'sum'), BU_Job_Count=('Total_Job_Time_Hours', 'size')).reset_index()
            bu_pivot_hrs = bu_agg.pivot(index='Name', columns='Business Unit', values='Total_Job_Time_Hours').reset_index().fillna(0)
            bu_pivot_cnt = bu_agg.pivot(index='Name', columns='Business Unit', values='BU_Job_Count').reset_index().fillna(0)
            bu_pivot = pd.merge(bu_pivot_hrs, bu_pivot_cnt, on='Name', suffixes=('_hrs', '_cnt'))
            for col in ['Lowes - Simple Installs_hrs', 'Lowes - Water Heaters_hrs', 'Lowes - Simple Installs_cnt', 'Lowes - Water Heaters_cnt']:
                if col not in bu_pivot.columns: bu_pivot[col] = 0.0
            bu_pivot = bu_pivot.rename(columns={'Lowes - Simple Installs_hrs': 'Simple_Installs_Hrs', 'Lowes - Water Heaters_hrs': 'Water_Heaters_Hrs', 'Lowes - Simple Installs_cnt': 'Simple_Installs_Count', 'Lowes - Water Heaters_cnt': 'Water_Heaters_Count'})
        else: bu_pivot = pd.DataFrame(columns=['Name', 'Simple_Installs_Hrs', 'Water_Heaters_Hrs', 'Simple_Installs_Count', 'Water_Heaters_Count'])

        job_time_agg = ops_df.groupby(['Name', 'Day_of_Week'])['Total_Job_Time_Hours'].sum().reset_index()
        job_time_pivot = job_time_agg.pivot(index='Name', columns='Day_of_Week', values='Total_Job_Time_Hours').reset_index().fillna(0)
        for day in days:
            if day not in job_time_pivot.columns: job_time_pivot[day] = 0.0
        job_time_pivot = job_time_pivot.rename(columns={d: d + '_Job_Hrs' for d in days})
        job_time_pivot['Total_Weekly_Job_Hrs'] = job_time_pivot[[d + '_Job_Hrs' for d in days]].sum(axis=1)
        
        job_count_agg = ops_df.groupby(['Name', 'Day_of_Week']).size().reset_index(name='Job_Count')
        job_count_pivot = job_count_agg.pivot(index='Name', columns='Day_of_Week', values='Job_Count').reset_index().fillna(0)
        for day in days:
            if day not in job_count_pivot.columns: job_count_pivot[day] = 0
        job_count_pivot = job_count_pivot.rename(columns={d: d + '_Job_Count' for d in days})
        job_count_pivot['Total_Weekly_Job_Count'] = job_count_pivot[[d + '_Job_Count' for d in days]].sum(axis=1)
        
        daily_route = ops_df.groupby(['Assigned Team Members', 'Short_Date']).agg(Drive_Time_Hrs=('Drive_Time_Hrs', 'sum'), In_Progress_Time_Hrs=('In_Progress_Time_Hrs', 'sum'), Total_Job_Time_Hours=('Total_Job_Time_Hours', 'sum'), Job_Count=('Total_Job_Time_Hours', 'size')).reset_index()
        daily_route = daily_route[daily_route['Total_Job_Time_Hours'] > 0].copy()
        daily_route['Drive %'] = (daily_route['Drive_Time_Hrs'] / daily_route['Total_Job_Time_Hours']) * 100
        daily_route['Name'] = daily_route['Assigned Team Members']
        
        final_df = pd.merge(time_df, job_time_pivot, on='Name', how='left').fillna(0)
        final_df = pd.merge(final_df, job_count_pivot, on='Name', how='left').fillna(0)
        if not bu_pivot.empty: final_df = pd.merge(final_df, bu_pivot[['Name', 'Simple_Installs_Hrs', 'Water_Heaters_Hrs', 'Simple_Installs_Count', 'Water_Heaters_Count']], on='Name', how='left').fillna(0)
        else:
            final_df['Simple_Installs_Hrs'] = final_df['Water_Heaters_Hrs'] = 0.0
            final_df['Simple_Installs_Count'] = final_df['Water_Heaters_Count'] = 0
            
        final_df['Total_Weekly_Job_Count'] = final_df['Simple_Installs_Count'] + final_df['Water_Heaters_Count']
        
        tech_rev_agg = ops_df.groupby('Name')['Total Invoice Amount'].sum().reset_index()
        tech_rev_agg.columns = ['Name', 'Total_Assigned_Revenue']
        final_df = pd.merge(final_df, tech_rev_agg, on='Name', how='left').fillna(0.0)
        final_df['Rev_Per_Clocked_Hr'] = np.where(final_df['Total_Weekly_Clocked_Hrs'] > 0, final_df['Total_Assigned_Revenue'] / final_df['Total_Weekly_Clocked_Hrs'], 0.0)

        sean_timecard = final_df[final_df['Name'] == 'Sean Marble']
        if not sean_timecard.empty:
            sean_row = sean_timecard.iloc[0]
            unworked_clocked_days = 0
            for d in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']:
                if sean_row[f'{d}_Clocked_Hrs'] <= 0:
                    unworked_clocked_days += 1
            sean_penalty_value = unworked_clocked_days * 269.23
        else:
            sean_penalty_value = 0.0

        st.session_state['sean_absence_penalty_global'] = sean_penalty_value

        final_df['LSI_Goal_Hrs'] = final_df['Simple_Installs_Count'] * 2.0
        final_df['WH_Goal_Hrs'] = final_df['Water_Heaters_Count'] * 3.5
        final_df['Total_Goal_Hrs'] = final_df['LSI_Goal_Hrs'] + final_df['WH_Goal_Hrs']
        final_df['Assumed_LSI_Clocked'] = np.where(final_df['Total_Goal_Hrs'] > 0, final_df['Total_Weekly_Clocked_Hrs'] * (final_df['LSI_Goal_Hrs'] / final_df['Total_Goal_Hrs']), 0.0)
        final_df['Assumed_WH_Clocked'] = np.where(final_df['Total_Goal_Hrs'] > 0, final_df['Total_Weekly_Clocked_Hrs'] * (final_df['WH_Goal_Hrs'] / final_df['Total_Goal_Hrs']), 0.0)

        final_df['LSI_Eff_Raw'] = np.where(final_df['Assumed_LSI_Clocked'] > 0, (final_df['Simple_Installs_Hrs'] / final_df['Assumed_LSI_Clocked']) * 100, 0.0)
        final_df['WH_Eff_Raw'] = np.where(final_df['Assumed_WH_Clocked'] > 0, (final_df['Water_Heaters_Hrs'] / final_df['Assumed_WH_Clocked']) * 100, 0.0)

        rev_per_hour_df_calc = final_df.copy()
        rev_per_hour_df_calc['Assumed Pay Amount'] = rev_per_hour_df_calc.apply(get_adjusted_table_pay, axis=1)

        pay_mapping_dict = dict(zip(rev_per_hour_df_calc['Name'], rev_per_hour_df_calc['Assumed Pay Amount']))
        ops_df['Computed_Row_Pay'] = ops_df['Name'].map(pay_mapping_dict).fillna(0.0)
        tech_total_field_hrs = ops_df.groupby('Name')['Total_Job_Time_Hours'].sum().reset_index().rename(columns={'Total_Job_Time_Hours': 'Tech_Total_Work_Hrs'})
        
        if 'Tech_Total_Work_Hrs' in ops_df.columns: 
            ops_df = ops_df.drop(columns=['Tech_Total_Work_Hrs'])
        ops_df = pd.merge(ops_df, tech_total_field_hrs, on='Name', how='left')
        
        ops_df['Job_Time_Weight'] = np.where(ops_df['Tech_Total_Work_Hrs'] > 0, ops_df['Total_Job_Time_Hours'] / ops_df['Tech_Total_Work_Hrs'], 0.0)
        ops_df['Allocated_Job_Pay'] = ops_df['Computed_Row_Pay'] * ops_df['Job_Time_Weight']
        ops_df['Allocated_Job_Pay'] = np.where(
            ops_df['Name'].str.lower().str.contains('bryan') | ops_df['Name'].str.lower().str.contains('erik'),
            ops_df['Total Invoice Amount'] * 0.34,
            ops_df['Allocated_Job_Pay']
        )

        df_macro_pay = unexploded_ops.copy()
        df_macro_pay['Tech_Count'] = df_macro_pay['Assigned Team Members'].apply(lambda x: len([m.strip() for m in str(x).split(',') if m.strip()]))
        df_macro_pay['Is_Contractor'] = df_macro_pay['Assigned Team Members'].apply(check_contractor)
        
        # --- FIX 3: STANDARDIZE HELPER COST BURDENS ---
        bu_conditions = [
            df_macro_pay.get('Business Unit') == 'Lowes - Water Heaters',
            df_macro_pay.get('Business Unit') == 'Lowes - Simple Installs'
        ]
        
        solo_labor_rates = [100.0, 0.0] 
        multi_labor_rates = [175.0, 0.0] 
        
        base_labor = np.select(bu_conditions, solo_labor_rates, default=0.0)
        multi_labor = np.select(bu_conditions, multi_labor_rates, default=0.0)
        
        df_macro_pay['Cost_Burden_Sub'] = np.where(
            df_macro_pay['Tech_Count'] > 1, 
            multi_labor, 
            base_labor
        )
        
        df_macro_pay['Prod_Cost'] = pd.to_numeric(df_macro_pay.get('Total Product Cost [tax inc]', pd.Series([0]*len(df_macro_pay))), errors='coerce').fillna(0.0)
        df_macro_pay['Serv_Cost'] = pd.to_numeric(df_macro_pay.get('Invoice - Total Service Cost', pd.Series([0]*len(df_macro_pay))), errors='coerce').fillna(0.0)
        df_macro_pay['Combined_Lowe_Costs'] = np.maximum(0.0, (df_macro_pay['Prod_Cost'] + df_macro_pay['Serv_Cost']) - df_macro_pay['Cost_Burden_Sub'])
        
        df_macro_pay['Flat_Rate_Labor'] = df_macro_pay['Cost_Burden_Sub']
        df_macro_pay['Logged_Time_Pay'] = df_macro_pay['#ID'].map(ops_df.groupby('#ID')['Allocated_Job_Pay'].sum().to_dict()).fillna(0.0)
        
        df_macro_pay['Assumed_Labor_Payload'] = np.where(
            (df_macro_pay.get('Business Unit') == 'Lowes - Simple Installs') & df_macro_pay['Is_Contractor'],
            df_macro_pay['Total Invoice Amount'],
            np.maximum(df_macro_pay['Flat_Rate_Labor'], df_macro_pay['Logged_Time_Pay'])
        )
        
        df_macro_pay['Has_Bryan_Erik'] = df_macro_pay['Assigned Team Members'].str.lower().str.contains('bryan|erik', na=False)
        df_macro_pay['BE_Simple_Install_Pay'] = (df_macro_pay['Total Invoice Amount'] * 0.34) + (np.maximum(0, df_macro_pay['Tech_Count'] - 1) * 44.0)
        
        df_macro_pay['Assumed_Labor_Payload'] = np.where(
            (df_macro_pay.get('Business Unit') == 'Lowes - Simple Installs') & df_macro_pay['Has_Bryan_Erik'],
            df_macro_pay['BE_Simple_Install_Pay'],
            df_macro_pay['Assumed_Labor_Payload']
        )
        
        df_macro_pay['Net_Profit_Raw'] = df_macro_pay['Total Invoice Amount'] - df_macro_pay['Combined_Lowe_Costs'] - df_macro_pay['Assumed_Labor_Payload']
            
        display_dfs = {}
        for day in days:
            final_df[day + '_Diff_Hrs'] = final_df[day + '_Clocked_Hrs'] - final_df[day + '_Job_Hrs']
            final_df[f'{day} Jobs'] = final_df[day + '_Job_Count'].astype(int)
            final_df[f'{day} Clocked'] = final_df[day + '_Clocked_Hrs'].apply(format_hm)
            final_df[f'{day} Job Time'] = final_df[day + '_Job_Hrs'].apply(format_hm)
            final_df[f'{day} Diff'] = final_df[day + '_Diff_Hrs'].apply(format_hm)
            
            day_df = pd.DataFrame()
            day_df['Name'] = final_df['Name']
            day_df[f'{day} Jobs'] = final_df[f'{day} Jobs']
            day_df[f'{day} Clocked'] = final_df[f'{day} Clocked']
            day_df[f'{day} Job Time'] = final_df[f'{day} Job Time']
            day_df[f'{day} Diff'] = final_df[f'{day} Diff']
            display_dfs[day] = day_df
            
        manager_cols = ['Name']
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]: manager_cols.extend([f'{d} Jobs', f'{d} Clocked', f'{d} Job Time', f'{d} Diff'])
        display_dfs['Manager'] = final_df[manager_cols]
        
        final_df['Total_Weekly_Diff_Hrs'] = final_df['Total_Weekly_Clocked_Hrs'] - final_df['Total_Weekly_Job_Hrs']
        final_df['Daily_Avg_Diff_Hrs'] = np.where(final_df['Days_Worked'] > 0, final_df['Total_Weekly_Diff_Hrs'] / final_df['Days_Worked'], 0.0)
        
        final_df['Simple Installs'] = final_df['Simple_Installs_Hrs'].apply(format_hm)
        final_df['Water Heaters'] = final_df['Water_Heaters_Hrs'].apply(format_hm)
        
        final_df['Simple Installs Eff'] = np.where(final_df['Simple_Installs_Count'] > 0, final_df['LSI_Eff_Raw'].map(lambda x: f"{x:.1f}%"), "-")
        final_df['Water Heaters Eff'] = np.where(final_df['Water_Heaters_Count'] > 0, final_df['WH_Eff_Raw'].map(lambda x: f"{x:.1f}%"), "-")
        
        bu_summary_df = pd.DataFrame()
        bu_summary_df['Name'] = final_df['Name']
        bu_summary_df['Total Clocked'] = final_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
        bu_summary_df['Total Jobs'] = final_df['Total_Weekly_Job_Count'].astype(int)
        bu_summary_df['LSI Jobs'] = final_df['Simple_Installs_Count'].astype(int)
        bu_summary_df['LSI Tracked Hours'] = final_df['Simple Installs']
        bu_summary_df['LSI Efficiency'] = final_df['Simple Installs Eff']
        bu_summary_df['WH Jobs'] = final_df['Water_Heaters_Count'].astype(int)
        bu_summary_df['WH Tracked Hours'] = final_df['Water Heaters']
        bu_summary_df['WH Efficiency'] = final_df['Water Heaters Eff']
        bu_summary_df['Total Efficiency'] = np.where(final_df['Total_Weekly_Clocked_Hrs'] > 0, (final_df['Total_Weekly_Job_Hrs'] / final_df['Total_Weekly_Clocked_Hrs']) * 100, 0.0)
        bu_summary_df['Total Efficiency'] = bu_summary_df['Total Efficiency'].apply(lambda x: f"{x:.1f}%")
        bu_summary_df['Total Unallocated Hours'] = final_df['Total_Weekly_Diff_Hrs'].apply(format_hm)
        
        total_clocked_sum = final_df['Total_Weekly_Clocked_Hrs'].sum()
        total_lsi_jobs_sum = final_df['Simple_Installs_Count'].sum()
        total_lsi_hrs_sum = final_df['Simple_Installs_Hrs'].sum()
        total_wh_jobs_sum = final_df['Water_Heaters_Count'].sum()
        total_wh_hrs_sum = final_df['Water_Heaters_Hrs'].sum()
        total_job_hrs_sum = final_df['Total_Weekly_Job_Hrs'].sum()
        total_diff_hrs_sum = final_df['Total_Weekly_Diff_Hrs'].sum()
        
        total_jobs_sum = total_lsi_jobs_sum + total_wh_jobs_sum
        
        total_lsi_goal_hrs = final_df['Assumed_LSI_Clocked'].sum()
        total_wh_goal_hrs = final_df['Assumed_WH_Clocked'].sum()
        
        blended_lsi_eff = (total_lsi_hrs_sum / total_lsi_goal_hrs * 100) if total_lsi_goal_hrs > 0 else 0.0
        blended_wh_eff = (total_wh_hrs_sum / total_wh_goal_hrs * 100) if total_wh_goal_hrs > 0 else 0.0
        blended_total_eff = (total_job_hrs_sum / total_clocked_sum * 100) if total_clocked_sum > 0 else 0.0
        
        total_row = pd.DataFrame([{
            'Name': 'TOTAL DIVISION',
            'Total Clocked': format_hm(total_clocked_sum),
            'Total Jobs': int(total_jobs_sum),
            'LSI Jobs': int(total_lsi_jobs_sum),
            'LSI Tracked Hours': format_hm(total_lsi_hrs_sum),
            'LSI Efficiency': f"{blended_lsi_eff:.1f}%",
            'WH Jobs': int(total_wh_jobs_sum),
            'WH Tracked Hours': format_hm(total_wh_hrs_sum),
            'WH Efficiency': f"{blended_wh_eff:.1f}%",
            'Total Efficiency': f"{blended_total_eff:.1f}%",
            'Total Unallocated Hours': format_hm(total_diff_hrs_sum)
        }])
        
        bu_summary_df = pd.concat([total_row, bu_summary_df], ignore_index=True)
        display_dfs['Weekly'] = bu_summary_df

        total_assumed_pay_adjusted = max(0.0, df_macro_pay['Assumed_Labor_Payload'].sum() - sean_penalty_value)
        pay_ratio_pct_adjusted = (total_assumed_pay_adjusted / raw_unsplit_volume * 100) if raw_unsplit_volume > 0 else 0.0

        if 'Business Unit' in unexploded_ops.columns:
            bu_gross_rev = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].sum().reset_index()
            bu_gross_rev.columns = ['Business Unit', 'Gross Invoiced Revenue Raw']
            total_macro_sum = bu_gross_rev['Gross Invoiced Revenue Raw'].sum() if bu_gross_rev['Gross Invoiced Revenue Raw'].sum() > 0 else 1.0
            bu_gross_rev['Rev Share %'] = (bu_gross_rev['Gross Invoiced Revenue Raw'] / total_macro_sum * 100).apply(lambda x: f"{x:.1f}%")
            
            bu_pay_split = df_macro_pay.groupby('Business Unit')['Assumed_Labor_Payload'].sum().reset_index().rename(columns={'Assumed_Labor_Payload': 'Assumed Pay Raw'})
            for idx, r in bu_pay_split.iterrows():
                if r['Business Unit'] == 'Lowes - Simple Installs':
                    bu_pay_split.loc[idx, 'Assumed Pay Raw'] = max(0.0, bu_pay_split.loc[idx, 'Assumed Pay Raw'] - sean_penalty_value)
                    
            bu_financial_matrix = pd.merge(bu_gross_rev, bu_pay_split, on='Business Unit', how='left').fillna(0.0)
            bu_financial_matrix['Assumed Pay'] = bu_financial_matrix['Assumed Pay Raw'].apply(lambda x: f"${x:,.2f}")
            bu_financial_matrix['Pay % of Revenue'] = np.where(
                bu_financial_matrix['Gross Invoiced Revenue Raw'] > 0,
                (bu_financial_matrix['Assumed Pay Raw'] / bu_financial_matrix['Gross Invoiced Revenue Raw']) * 100,
                0.0
            )
            bu_financial_matrix['Pay % of Revenue'] = bu_financial_matrix['Pay % of Revenue'].apply(lambda x: f"{x:.1f}%")
            bu_financial_matrix['Gross Invoiced Revenue'] = bu_financial_matrix['Gross Invoiced Revenue Raw'].apply(lambda x: f"${x:,.2f}")
        else:
            bu_financial_matrix = pd.DataFrame()

        tab_names = ["Weekly Summary", "Manager Overview", "Individual Tech Report", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "🧪 Test Section"]
        tabs = st.tabs(tab_names)
        
        with tabs[0]:
            st.markdown('<h3>Weekly Efficiency Summary</h3>', unsafe_allow_html=True)
            
            if validation_warnings:
                with st.expander("⚠️ Upstream Data Integrity Notices", expanded=True):
                    for warning in validation_warnings:
                        st.markdown(warning)
                        
            st.components.v1.html("""
            <div style="text-align: right;">
                <button onclick="window.parent.print()" style="background-color: #1a73e8; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-family: sans-serif; font-size: 14px; font-weight: bold; box-shadow: 0 1px 3px rgba(60,64,67,0.3);">
                    🖨️ Save Report as PDF / Print Dashboard
                </button>
            </div>
            """, height=45)

            st.markdown("### 🏢 Division Operational Health & Productivity Scorecard")
            
            div_health_col1, div_health_col2, div_health_col3, div_health_col4 = st.columns(4)
            with div_health_col1:
                st.metric(label="Total Division Unallocated Hours", value=format_hm(total_diff_hrs_sum))
            with div_health_col2:
                st.metric(label="Division LSI Efficiency", value=f"{blended_lsi_eff:.1f}%")
            with div_health_col3:
                st.metric(label="Division Water Heater Efficiency", value=f"{blended_wh_eff:.1f}%")
            with div_health_col4:
                st.metric(label="Blended Division Efficiency", value=f"{blended_total_eff:.1f}%")
            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown("💡 **Operational Baselines Tasks / Goals per Business Unit:** `Water Heaters Goal = 3:30 hrs` &nbsp;&nbsp;|&nbsp;&nbsp; `Simple Installs Goal = 2:00 hrs` *(Table automatically sorted by highest WH Efficiency)*")
            
            try:
                def highlight_weekly_rows(row):
                    if row['Name'] == 'TOTAL DIVISION':
                        return ['background-color: #e2e3e5; font-weight: bold; color: #383d41;'] * len(row)
                    styles = [''] * len(row)
                    idx = row.index.get_loc('WH Efficiency')
                    if row[idx] != '-':
                        styles[idx] = 'background-color: #fff3cd; font-weight: bold; color: #856404;'
                    return styles
                
                styled_weekly = display_dfs['Weekly'].reset_index(drop=True).style.apply(highlight_weekly_rows, axis=1)
                st.dataframe(styled_weekly, use_container_width=True) 
            except Exception:
                st.dataframe(display_dfs['Weekly'].reset_index(drop=True), use_container_width=True)
                
            create_copy_button(display_dfs['Weekly'], "weekly_summary")
            
            st.markdown("<br><hr><h3>📊 Macro Financial Performance Dashboard</h3>", unsafe_allow_html=True)
            
            dash_metric_col1, dash_metric_col2, dash_metric_col3 = st.columns(3)
            with dash_metric_col1:
                st.metric(label="Division Gross Invoiced Volume", value=f"${raw_unsplit_volume:,.2f}")
            with dash_metric_col2:
                st.metric(label="Assumed Total Pay (Division)", value=f"${total_assumed_pay_adjusted:,.2f}")
            with dash_metric_col3:
                st.metric(label="Division Labor Pay Ratio", value=f"{pay_ratio_pct_adjusted:.1f}%")
                
            m_col1, m_col2 = st.columns([1.2, 1.8])
            with m_col1:
                if not bu_financial_matrix.empty:
                    st.markdown("<br>**📈 Gross Invoiced Revenue & Payroll by Business Unit**", unsafe_allow_html=True)
                    st.dataframe(bu_financial_matrix[['Business Unit', 'Gross Invoiced Revenue', 'Rev Share %', 'Assumed Pay', 'Pay % of Revenue']].reset_index(drop=True), use_container_width=True)
                    create_copy_button(bu_financial_matrix[['Business Unit', 'Gross Invoiced Revenue', 'Rev Share %', 'Assumed Pay', 'Pay % of Revenue']], "bu_rev_and_pay")
                    
                    st.markdown("<br>**🎯 Average Ticket Size per BU**", unsafe_allow_html=True)
                    bu_avg_ticket = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].mean().reset_index()
                    bu_avg_ticket.columns = ['Business Unit', 'Average Ticket Size Raw']
                    bu_avg_ticket['Average Ticket Size'] = bu_avg_ticket['Average Ticket Size Raw'].apply(lambda x: f"${x:,.2f}")
                    st.dataframe(bu_avg_ticket[['Business Unit', 'Average Ticket Size']].reset_index(drop=True), use_container_width=True)
                    create_copy_button(bu_avg_ticket[['Business Unit', 'Average Ticket Size']], "bu_avg_ticket")
            with m_col2:
                st.markdown("**📈 Pay Ratio per Clocked Hour**", unsafe_allow_html=True)
                rev_per_hour_df = final_df.copy()
                rev_per_hour_df['Total Clocked'] = rev_per_hour_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
                rev_per_hour_df['Total Jobs'] = rev_per_hour_df['Total_Weekly_Job_Count'].astype(int)
                rev_per_hour_df['Total Assigned Value'] = rev_per_hour_df['Total_Assigned_Revenue'].apply(lambda x: f"${x:,.2f}")
                
                rev_per_hour_df['Assumed Pay Amount'] = rev_per_hour_df.apply(get_adjusted_table_pay, axis=1)
                rev_per_hour_df['Assumed Pay'] = rev_per_hour_df['Assumed Pay Amount'].apply(lambda x: f"${x:,.2f}" if x > 0 else "-")
                rev_per_hour_df['Pay Pct'] = np.where(rev_per_hour_df['Total_Assigned_Revenue'] > 0, (rev_per_hour_df['Assumed Pay Amount'] / rev_per_hour_df['Total_Assigned_Revenue']) * 100, 0.0)
                rev_per_hour_df['Pay % vs Assigned Revenue'] = rev_per_hour_df['Pay Pct'].apply(lambda x: f"{x:.1f}%" if x > 0 else "-")
                
                rev_per_hour_df['Net Margin Raw'] = rev_per_hour_df['Total_Assigned_Revenue'] - rev_per_hour_df['Assumed Pay Amount']
                rev_per_hour_df['Total Net Margin'] = rev_per_hour_df['Net Margin Raw'].apply(lambda x: f"${x:,.2f}")
                rev_per_hour_df['Margin per Clocked Hour Raw'] = np.where(rev_per_hour_df['Total_Weekly_Clocked_Hrs'] > 0, rev_per_hour_df['Net Margin Raw'] / rev_per_hour_df['Total_Weekly_Clocked_Hrs'], 0.0)
                rev_per_hour_df['Margin per Clocked Hour'] = rev_per_hour_df['Margin per Clocked Hour Raw'].apply(lambda x: f"${x:,.2f}/hr")
                
                show_rev_per_hour_sorted = rev_per_hour_df.sort_values(by='Pay Pct', ascending=False)[['Name', 'Total Jobs', 'Total Clocked', 'Total Assigned Value', 'Assumed Pay', 'Pay % vs Assigned Revenue', 'Total Net Margin', 'Margin per Clocked Hour']]
                st.dataframe(show_rev_per_hour_sorted.reset_index(drop=True), use_container_width=True)
                create_copy_button(show_rev_per_hour_sorted.reset_index(drop=True), "pay_ratio_per_clocked")
                
            st.markdown("<br><hr><h3>💵 Division True Net Profitability Margin Auditor</h3>", unsafe_allow_html=True)
            st.markdown("*(Evaluates net profitability metrics across selected sectors factoring contract structures, costs backouts and non-negative thresholds)*")
            
            sort_pane_col, filter_pane_col = st.columns(2)
            with filter_pane_col:
                selected_bu_filter = st.selectbox("Filter Performance Register By Line of Business:", ["All Sectors", "Lowes - Water Heaters", "Lowes - Simple Installs"], index=1, key="bu_perf_filter_matrix")
            with sort_pane_col:
                selected_sort_choice = st.selectbox("Sort Itemized Register Results By:", ["Highest Net Profit", "Lowest Net Profit", "Highest Gross Invoice", "Highest Profit Margin %", "Job ID"], index=3, key="sorting_perf_matrix")
                
            df_prof_totals = df_macro_pay.copy()
            if selected_bu_filter != "All Sectors":
                df_prof_totals = df_prof_totals[df_prof_totals.get('Business Unit') == selected_bu_filter]
                
            if not df_prof_totals.empty:
                gross_revenue_sum = df_prof_totals['Total Invoice Amount'].sum()
                combined_cost_sum = df_prof_totals['Combined_Lowe_Costs'].sum()
                labor_payload_sum = df_prof_totals['Assumed_Labor_Payload'].sum()
                
                if selected_bu_filter in ["All Sectors", "Lowes - Water Heaters", "Lowes - Simple Installs"]:
                    if 'sean marble' in [tech.lower() for tech in ops_df['Name'].unique()]:
                        labor_payload_sum = max(0.0, labor_payload_sum - sean_penalty_value)
                
                net_profit_sum = gross_revenue_sum - combined_cost_sum - labor_payload_sum
                
                totals_summary_df = pd.DataFrame([{
                    "Total Dispatches Closed": int(len(df_prof_totals)),
                    "Gross Invoiced Revenue": f"${gross_revenue_sum:,.2f}",
                    "Total Combined Cost": f"${combined_cost_sum:,.2f}",
                    "Tech Wage Burden": f"${labor_payload_sum:,.2f}",
                    "Net Profit ($)": f"${net_profit_sum:,.2f}",
                    "Net Profit (%)": f"{(net_profit_sum / gross_revenue_sum * 100):.1f}%" if gross_revenue_sum > 0 else "0.0%"
                }])
                
                st.table(totals_summary_df)
                create_copy_button(totals_summary_df, "profitability_summary_totals")
                
                df_prof_filtered = df_macro_pay.copy()
                if selected_bu_filter != "All Sectors":
                    df_prof_filtered = df_prof_filtered[df_prof_filtered.get('Business Unit') == selected_bu_filter]
                df_prof_filtered = df_prof_filtered[~df_prof_filtered['Is_Contractor']]
                
                if not df_prof_filtered.empty:
                    df_prof_filtered['Profit Margin %'] = np.where(df_prof_filtered['Total Invoice Amount'] > 0, (df_prof_filtered['Net_Profit_Raw'] / df_prof_filtered['Total Invoice Amount'] * 100), 0.0)
                    
                    if selected_sort_choice == "Highest Net Profit": df_prof_filtered = df_prof_filtered.sort_values(by='Net_Profit_Raw', ascending=False)
                    elif selected_sort_choice == "Lowest Net Profit": df_prof_filtered = df_prof_filtered.sort_values(by='Net_Profit_Raw', ascending=True)
                    elif selected_sort_choice == "Highest Gross Invoice": df_prof_filtered = df_prof_filtered.sort_values(by='Total Invoice Amount', ascending=False)
                    elif selected_sort_choice == "Highest Profit Margin %": df_prof_filtered = df_prof_filtered.sort_values(by='Profit Margin %', ascending=False)
                    else: df_prof_filtered = df_prof_filtered.sort_values(by='#ID', ascending=True)
                    
                    prof_register_rows = []
                    for _, r in df_prof_filtered.iterrows():
                        prof_register_rows.append({
                            "Job ID": str(int(r['#ID'])),
                            "Line of Business": r.get('Business Unit', 'Unknown'),
                            "Crew Assigned": r['Assigned Team Members'],
                            "Gross Invoice": f"${r['Total Invoice Amount']:,.2f}",
                            "Total Combined Cost": f"${r['Combined_Lowe_Costs']:,.2f}",
                            "Tech Wage Burden": f"${r['Assumed_Labor_Payload']:,.2f}",
                            "Net Profit ($)": f"${r['Net_Profit_Raw']:,.2f}",
                            "Margin %": f"{r['Profit Margin %']:.1f}%"
                        })
                    
                    prof_register_df = pd.DataFrame(prof_register_rows, columns=[
                        "Job ID", "Line of Business", "Crew Assigned", "Gross Invoice", 
                        "Total Combined Cost", "Tech Wage Burden", "Net Profit ($)", "Margin %"
                    ])
                    
                    try:
                        styled_reg = prof_register_df.style.apply(highlight_low_margins, axis=1)
                        st.table(styled_reg)
                    except Exception:
                        st.table(prof_register_df)
                    create_copy_button(prof_register_df, "sortable_job_margins_register")

            if 'Business Unit' in df_macro_pay.columns:
                st.markdown("<br><hr><h3>📦 Lowe's Combined Cost Performance Matrix</h3>", unsafe_allow_html=True)
                st.markdown("*(Isolates combined material and service expenses metrics and maps accurate Net Profit thresholds by sector inclusive of contractor fields)*")
                cc_matrix = df_macro_pay.groupby('Business Unit').agg(
                    Jobs=('#ID', 'count'),
                    Gross_Invoiced_Raw=('Total Invoice Amount', 'sum'),
                    Combined_Cost_Total_Raw=('Combined_Lowe_Costs', 'sum'),
                    Assumed_Labor_Payload_Raw=('Assumed_Labor_Payload', 'sum'),
                    Net_Profit_Total_Raw=('Net_Profit_Raw', 'sum')
                ).reset_index()
                
                for idx, r in cc_matrix.iterrows():
                    if r['Business Unit'] == 'Lowes - Simple Installs':
                        cc_matrix.loc[idx, 'Assumed_Labor_Payload_Raw'] = max(0.0, cc_matrix.loc[idx, 'Assumed_Labor_Payload_Raw'] - sean_penalty_value)
                        cc_matrix.loc[idx, 'Net_Profit_Total_Raw'] = cc_matrix.loc[idx, 'Gross_Invoiced_Raw'] - cc_matrix.loc[idx, 'Combined_Cost_Total_Raw'] - cc_matrix.loc[idx, 'Assumed_Labor_Payload_Raw']
                
                cc_matrix['Cost Ratio % vs Rev'] = np.where(cc_matrix['Gross_Invoiced_Raw'] > 0, (cc_matrix['Combined_Cost_Total_Raw'] / cc_matrix['Gross_Invoiced_Raw'] * 100), 0.0)
                cc_matrix['Cost Ratio % vs Rev'] = cc_matrix['Cost Ratio % vs Rev'].apply(lambda x: f"{x:.1f}%")
                cc_matrix['Net Profit (%)'] = np.where(cc_matrix['Gross_Invoiced_Raw'] > 0, (cc_matrix['Net_Profit_Total_Raw'] / cc_matrix['Gross_Invoiced_Raw'] * 100), 0.0)
                cc_matrix['Net Profit (%)'] = cc_matrix['Net Profit (%)'].apply(lambda x: f"{x:.1f}%")
                cc_matrix['Gross Invoiced Revenue'] = cc_matrix['Gross_Invoiced_Raw'].apply(lambda x: f"${x:,.2f}")
                cc_matrix['Total Combined Cost'] = cc_matrix['Combined_Cost_Total_Raw'].apply(lambda x: f"${x:,.2f}")
                cc_matrix['Tech Wage Burden'] = cc_matrix['Assumed_Labor_Payload_Raw'].apply(lambda x: f"${x:,.2f}")
                cc_matrix['Net Profit ($)'] = cc_matrix['Net_Profit_Total_Raw'].apply(lambda x: f"${x:,.2f}")
                
                show_cc = cc_matrix[['Business Unit', 'Jobs', 'Gross Invoiced Revenue', 'Total Combined Cost', 'Cost Ratio % vs Rev', 'Tech Wage Burden', 'Net Profit ($)', 'Net Profit (%)']].rename(columns={'Jobs': 'Jobs Assigned'})
                st.dataframe(show_cc, use_container_width=True)
                create_copy_button(show_cc, "product_vs_service_cost_breakdown")
            
            st.markdown("<br><hr>", unsafe_allow_html=True)
            show_advanced_reporting(unexploded_ops, ops_df, final_df, bounds_df, delayed_launches_df, daily_route, tab_key="summary_tab")
            
        with tabs[1]:
            st.markdown('<h3>Manager Overview - All Techs</h3>', unsafe_allow_html=True)
            for tech in final_df['Name'].unique():
                st.markdown(f"#### **{tech}**")
                tech_data = final_df[final_df['Name'] == tech].iloc[0]
                report_data = []
                for full_day, short_day in {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}.items():
                    report_data.append({"Day": full_day, "Jobs": int(tech_data[short_day + '_Job_Count']), "Clocked Time": format_hm(tech_data[short_day + '_Clocked_Hrs']), "Job Time": format_hm(final_df[final_df['Name'] == tech].iloc[0][short_day + '_Job_Hrs']), "Difference": format_hm(tech_data[short_day + '_Diff_Hrs'])})
                report_data.append({"Day": "TOTAL WEEKLY", "Jobs": int(tech_data['Total_Weekly_Job_Count']), "Clocked Time": format_hm(tech_data['Total_Weekly_Clocked_Hrs']), "Job Time": format_hm(tech_data['Total_Weekly_Job_Hrs']), "Difference": format_hm(tech_data['Total_Weekly_Diff_Hrs'])})
                manager_day_df = pd.DataFrame(report_data)
                st.dataframe(manager_day_df, use_container_width=True)
                create_copy_button(manager_day_df, f"manager_overview_{tech}")
                
            st.markdown("<br><hr>", unsafe_allow_html=True)
            show_advanced_reporting(unexploded_ops, ops_df, final_df, bounds_df, delayed_launches_df, daily_route, tab_key="manager_tab")
            
        with tabs[2]:
            st.markdown('<h3>Printable Individual Report</h3>', unsafe_allow_html=True)
            selected_tech = st.selectbox("Select a Technician:", final_df['Name'].unique(), key="printable_tech_selector")
            if selected_tech:
                tech_data = final_df[final_df['Name'] == selected_tech].iloc[0]
                report_data = []
                for full_day, short_day in {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}.items():
                    report_data.append({"Day": full_day, "Jobs": int(tech_data[short_day + '_Job_Count']), "Clocked Time": format_hm(tech_data[short_day + '_Clocked_Hrs']), "Job Time": format_hm(final_df[final_df['Name'] == selected_tech].iloc[0][short_day + '_Job_Hrs']), "Difference": format_hm(tech_data[short_day + '_Diff_Hrs'])})
                report_data.append({"Day": "TOTAL WEEKLY", "Jobs": int(tech_data['Total_Weekly_Job_Count']), "Clocked Time": format_hm(tech_data['Total_Weekly_Clocked_Hrs']), "Job Time": format_hm(tech_data['Total_Weekly_Job_Hrs']), "Difference": format_hm(tech_data['Total_Weekly_Diff_Hrs'])})
                indiv_day_df = pd.DataFrame(report_data)
                st.dataframe(indiv_day_df, use_container_width=True)
                create_copy_button(indiv_day_df, f"printable_indiv_{selected_tech}")

        day_mapping = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
        for i, full_day in enumerate(list(day_mapping.keys())): 
            with tabs[i+3]:
                short_day = day_mapping[full_day]
                st.dataframe(display_dfs[short_day].reset_index(drop=True), use_container_width=True)
                create_copy_button(display_dfs[short_day].reset_index(drop=True), f"day_tab_{short_day}")

        with tabs[10]:
            test_choices = st.multiselect(
                "Select active data views to mount inside Test Section:", 
                [
                    "🏆 The Golden Ratio Margin Predictor", 
                    "🔄 The Context-Switching Penalty Alert", 
                    "🕵️ The Ghost Punch & Payroll Discrepancy Auditor", 
                    "¼ The Lowe's Store Staging Efficiency Scorecard", 
                    "📊 Macro Financial Performance Dashboard", 
                    "📊 Business Unit Revenue Velocity", 
                    "🗺️ Revenue Yield per Drive Hour (Geo-Routing Efficiency)", 
                    "🗺️ Route Optimization Flags", 
                    "🦺 Multi-Tech Labor Yield vs. Solo Runs", 
                    "📅 Lowe's Store Staging Delays by Day of the Week", 
                    "📊 Overtime ROI Cost-Benefit Auditor", 
                    "🏆 Single-Job \"Whale Alert\" Revenue Leaderboard", 
                    "🗺️ Interactive Territory Density and Hotspot Mapping", 
                    "🗺️ Geographic Revenue Yield per Drive Hour", 
                    "🚛 End-of-Day (EOD) Payroll Slippage Auditor",
                    "🤖 AI Outlier & Anomalous Duration Detector",
                    "🚙 Dynamic Machine Learning Drive Time Forecast",
                    "🎖️ Gamification Leaderboards & Digital Badges",
                    "⏱️ Technician Task Speed Leaderboard (Sub-Type)"
                ], 
                default=["🏆 The Golden Ratio Margin Predictor"], 
                key="sandbox_view_choices"
            )
            
            if "🤖 AI Outlier & Anomalous Duration Detector" in test_choices:
                st.markdown("### **🤖 AI Outlier & Anomalous Duration Detector**")
                st.markdown("*(Isolates completion windows that are statistically impossible or indicate severe operational delay using Isolation Forests or Z-Score fallbacks)*")
                df_outlier = ops_df.copy()
                df_outlier['Is_Duration_Anomaly'] = False
                df_outlier['Anomaly_Reason'] = ""
                
                if 'Business Unit' in df_outlier.columns:
                    for bu in df_outlier['Business Unit'].unique():
                        bu_mask = df_outlier['Business Unit'] == bu
                        bu_slice = df_outlier[bu_mask]
                        
                        if len(bu_slice) >= 4:
                            try:
                                from sklearn.ensemble import IsolationForest
                                clf = IsolationForest(contamination=0.08, random_state=42)
                                preds = clf.fit_predict(bu_slice[['Total_Job_Time_Hours']])
                                df_outlier.loc[bu_mask & (preds == -1), 'Is_Duration_Anomaly'] = True
                            except ImportError:
                                mean_t = bu_slice['Total_Job_Time_Hours'].mean()
                                std_t = bu_slice['Total_Job_Time_Hours'].std()
                                if std_t > 0:
                                    z_scores = (bu_slice['Total_Job_Time_Hours'] - mean_t) / std_t
                                    df_outlier.loc[bu_mask & (z_scores.abs() > 2.0), 'Is_Duration_Anomaly'] = True
                            
                            mean_val = bu_slice['Total_Job_Time_Hours'].mean()
                            df_outlier.loc[bu_mask & df_outlier['Is_Duration_Anomaly'] & (df_outlier['Total_Job_Time_Hours'] > mean_val), 'Anomaly_Reason'] = "⚠️ Suspiciously High Window"
                            df_outlier.loc[bu_mask & df_outlier['Is_Duration_Anomaly'] & (df_outlier['Total_Job_Time_Hours'] < mean_val), 'Anomaly_Reason'] = "🚨 Fast-Punch / App Abuse Suspect"
                    
                    anomalies = df_outlier[df_outlier['Is_Duration_Anomaly']].copy()
                    if not anomalies.empty:
                        anomalies['Job Time'] = anomalies['Total_Job_Time_Hours'].apply(format_hm)
                        st.dataframe(anomalies[['#ID', 'Name', 'Business Unit', 'Job Time', 'Anomaly_Reason']].rename(columns={'#ID': 'Job ID'}), use_container_width=True)
                        create_copy_button(anomalies[['#ID', 'Name', 'Business Unit', 'Job Time', 'Anomaly_Reason']], "duration_anomalies_export")
                    else:
                        st.success("✅ No statistical outliers detected in the current dataset.")
                else:
                    st.info("Requires Business Unit data to calculate statistical cohorts.")

            if "🚙 Dynamic Machine Learning Drive Time Forecast" in test_choices:
                st.markdown("### **🚙 Dynamic Machine Learning Drive Time Forecast**")
                st.markdown("*(Predicts expected drive times dynamically by building a spatial-temporal profile per AZ city/hub, flagging anomalous travel routing)*")
                df_drive = ops_df.copy()
                
                if 'Location Address' in df_drive.columns:
                    df_drive['Destination_Hub'] = df_drive['Location Address'].apply(parse_az_city)
                    df_drive['Hour_of_Day'] = pd.to_datetime(df_drive['Earliest_Start']).dt.hour.fillna(8).astype(int)
                    df_drive['Predicted_Drive_Hrs'] = 0.0
                    
                    try:
                        from sklearn.linear_model import LinearRegression
                        from sklearn.preprocessing import OneHotEncoder
                        
                        X_raw = df_drive[['Destination_Hub', 'Hour_of_Day']].copy()
                        y = df_drive['Drive_Time_Hrs'].values
                        
                        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
                        X_encoded = encoder.fit_transform(X_raw[['Destination_Hub']])
                        X_features = np.column_stack((X_encoded, X_raw['Hour_of_Day'].values))
                        
                        model = LinearRegression()
                        model.fit(X_features, y)
                        df_drive['Predicted_Drive_Hrs'] = model.predict(X_features)
                    except ImportError:
                        profile_map = df_drive.groupby(['Destination_Hub', 'Hour_of_Day'])['Drive_Time_Hrs'].mean().to_dict()
                        global_avg = df_drive['Drive_Time_Hrs'].mean() if not df_drive.empty else 0.5
                        df_drive['Predicted_Drive_Hrs'] = df_drive.apply(
                            lambda r: profile_map.get((r['Destination_Hub'], r['Hour_of_Day']), global_avg), axis=1
                        )
                    
                    df_drive['Is_Drive_Anomaly'] = df_drive['Drive_Time_Hrs'] > (df_drive['Predicted_Drive_Hrs'] + 0.75)
                    drive_anomalies = df_drive[df_drive['Is_Drive_Anomaly']].copy()
                    
                    if not drive_anomalies.empty:
                        drive_anomalies['Actual Drive'] = drive_anomalies['Drive_Time_Hrs'].apply(format_hm)
                        drive_anomalies['Predicted Drive'] = drive_anomalies['Predicted_Drive_Hrs'].apply(format_hm)
                        drive_anomalies['Variance'] = (drive_anomalies['Drive_Time_Hrs'] - drive_anomalies['Predicted_Drive_Hrs']).apply(lambda x: f"+{format_hm(x)}")
                        
                        st.dataframe(drive_anomalies[['#ID', 'Name', 'Destination_Hub', 'Actual Drive', 'Predicted Drive', 'Variance']].rename(columns={'#ID': 'Job ID'}), use_container_width=True)
                        create_copy_button(drive_anomalies[['#ID', 'Name', 'Destination_Hub', 'Actual Drive', 'Predicted Drive', 'Variance']], "drive_anomalies_export")
                    else:
                        st.success("✅ Travel routes align closely with expected geographic spatial-temporal forecasts.")
                else:
                    st.info("Requires Location Address column to map and route destinations.")

            if "🎖️ Gamification Leaderboards & Digital Badges" in test_choices:
                st.markdown("### **🎖️ Gamification Leaderboards & Digital Badges**")
                st.markdown("*(Awards digital achievements based on division-leading metrics in efficiency, punctuality, and volume)*")
                
                if 'display_dfs' in locals() and 'Weekly' in display_dfs:
                    badge_rows = []
                    weekly_df = display_dfs['Weekly']
                    
                    for _, r in weekly_df.iterrows():
                        tech_name = r['Name']
                        if tech_name == 'TOTAL DIVISION': 
                            continue
                        
                        badges = []
                        
                        # 1. Master Installer
                        try:
                            eff_val = float(str(r.get('Total Efficiency', '0%')).replace('%', ''))
                            if eff_val >= 75.0:
                                badges.append("🏆 **Master Installer**")
                        except: pass
                        
                        # 2. Punctuality Star
                        if not delayed_launches_df.empty:
                            if len(delayed_launches_df[delayed_launches_df['Assigned Team Members'] == tech_name]) == 0:
                                badges.append("⭐ **Punctuality Star**")
                        else: 
                            badges.append("⭐ **Punctuality Star**")
                            
                        # 3. Road Warrior
                        if int(r.get('Total Jobs', 0)) >= 8:
                            badges.append("🚛 **Road Warrior**")
                            
                        if not badges: 
                            badges.append("🎖️ *Baseline Competency*")
                            
                        badge_rows.append({
                            "Technician": tech_name,
                            "Jobs Completed": int(r.get('Total Jobs', 0)),
                            "Total Efficiency": r.get('Total Efficiency', '-'),
                            "Earned Badges": " &nbsp;•&nbsp; ".join(badges)
                        })
                    
                    badge_df = pd.DataFrame(badge_rows).sort_values(by="Jobs Completed", ascending=False)
                    st.markdown(badge_df.style.hide(axis="index").to_html(), unsafe_allow_html=True)
                else:
                    st.info("Weekly Summary data is missing to calculate gamification badges.")

            if "🏆 The Golden Ratio Margin Predictor" in test_choices:
                st.markdown("### **🏆 The Golden Ratio Margin Predictor**")
                golden_data = []
                for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                    final_df_d_clocked = final_df[f'{d}_Clocked_Hrs'].sum() if f'{d}_Clocked_Hrs' in final_df.columns else 0.0
                    final_df_d_job = final_df[f'{d}_Job_Hrs'].sum() if f'{d}_Job_Hrs' in final_df.columns else 0.0
                    day_clocked = final_df_d_clocked
                    day_job = final_df_d_job
                    day_eff = (day_job / day_clocked * 100) if day_clocked > 0 else 0.0
                    
                    if 'Business Unit' in ops_df.columns:
                        day_lsi = ops_df[(ops_df['Day_of_Week'] == d) & (ops_df['Business Unit'] == 'Lowes - Simple Installs')].shape[0]
                        day_wh = ops_df[(ops_df['Day_of_Week'] == d) & (ops_df['Business Unit'] == 'Lowes - Water Heaters')].shape[0]
                    else: day_lsi, day_wh = 0, 0
                    
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
                    daily_bu = ops_df.groupby(['Name', 'Short_Date', 'Business Unit']).size().unstack(fill_value=0).reset_index()
                    if 'Lowes - Simple Installs' not in daily_bu.columns: daily_bu['Lowes - Simple Installs'] = 0
                    if 'Lowes - Water Heaters' not in daily_bu.columns: daily_bu['Lowes - Water Heaters'] = 0
                    daily_bu['Day Type'] = np.where((daily_bu['Lowes - Simple Installs'] > 0) & (daily_bu['Lowes - Water Heaters'] > 0), 'Mixed Route (Both)', 'Uniform Route (One Type)')
                            
                    daily_merged = pd.merge(daily_route, daily_bu, on=['Name', 'Short_Date'])
                    daily_merged['Avg Job Time'] = daily_merged['Total_Job_Time_Hours'] / daily_merged['Job_Count']
                    context_agg = daily_merged.groupby('Day Type').agg(Total_Days=('Short_Date', 'count'), Avg_Job_Turnaround=('Avg Job Time', 'mean')).reset_index()
                    if not context_agg.empty:
                        context_agg['Average Fleet Job Turnaround'] = context_agg['Avg_Job_Turnaround'].apply(format_hm)
                        st.dataframe(context_agg[['Day Type', 'Total_Days', 'Average Fleet Job Turnaround']].rename(columns={'Total_Days': 'Days Analyzed'}), use_container_width=True)

            if "🕵️ The Ghost Punch & Payroll Discrepancy Auditor" in test_choices:
                st.markdown("### **🕵️ The Ghost Punch & Payroll Discrepancy Auditor**")
                ghost_alerts = []
                for idx, row in final_df.iterrows():
                    tech_name = row['Name']
                    nl = tech_name.lower()
                    pay_type = "Hourly"
                    if "sean marble" in nl or "michael owens" in nl or "mathew hodges" in nl:
                        pay_type = "Salary"
                    elif "bryan" in nl or "erik" in nl:
                        pay_type = "Piece Rate"
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

            if "¼ The Lowe's Store Staging Efficiency Scorecard" in test_choices:
                st.markdown("### **¼ The Lowe's Store Staging Efficiency Scorecard**")
                store_cols = [c for c in ops_df.columns if 'store' in c.lower() and 'time' in c.lower() and 'timestamp' not in c.lower()]
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
                    if 'Business Unit' in unexploded_ops.columns:
                        bu_avg_ticket = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].mean().reset_index()
                        bu_avg_ticket.columns = ['Business Unit', 'Average Ticket Size Raw']
                        bu_avg_ticket['Average Ticket Size'] = bu_avg_ticket['Average Ticket Size Raw'].apply(lambda x: f"${x:,.2f}")
                        st.dataframe(bu_avg_ticket[['Business Unit', 'Average Ticket Size']].reset_index(drop=True), use_container_width=True)
                with m_col2:
                    st.markdown("**📈 Pay Ratio per Clocked Hour**")
                    rev_per_hour_df = final_df.copy()
                    rev_per_hour_df['Total Clocked'] = rev_per_hour_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
                    rev_per_hour_df['Total Assigned Value'] = rev_per_hour_df['Total_Assigned_Revenue'].apply(lambda x: f"${x:,.2f}")
                    
                    rev_per_hour_df['Assumed Pay Amount'] = rev_per_hour_df.apply(get_adjusted_table_pay, axis=1)
                    rev_per_hour_df['Assumed Pay'] = rev_per_hour_df['Assumed Pay Amount'].apply(lambda x: f"${x:,.2f}" if x > 0 else "-")
                    rev_per_hour_df['Pay Pct'] = np.where(rev_per_hour_df['Total_Assigned_Revenue'] > 0, (rev_per_hour_df['Assumed Pay Amount'] / rev_per_hour_df['Total_Assigned_Revenue']) * 100, 0.0)
                    rev_per_hour_df['Pay % vs Assigned Revenue'] = rev_per_hour_df['Pay Pct'].apply(lambda x: f"{x:.1f}%" if x > 0 else "-")
                    show_rev_per_hour = rev_per_hour_df.sort_values(by='Pay Pct', ascending=False)[['Name', 'Total Clocked', 'Total Assigned Value', 'Assumed Pay', 'Pay % vs Assigned Revenue']]
                    st.dataframe(show_rev_per_hour.reset_index(drop=True).style.apply(highlight_pay_pct_row, axis=1), use_container_width=True)

            if "📊 Business Unit Revenue Velocity" in test_choices:
                st.markdown("### **📊 Business Unit Revenue Velocity**")
                bu_rev = unexploded_ops['Total Invoice Amount'].sum()
                if 'Business Unit' in unexploded_ops.columns:
                    bu_rev_df = unexploded_ops.groupby('Business Unit')['Total Invoice Amount'].sum().reset_index()
                    bu_rev_df['Revenue Share %'] = (bu_rev_df['Total Invoice Amount'] / unexploded_ops['Total Invoice Amount'].sum()) * 100
                    bu_rev_df['Total Revenue'] = bu_rev_df['Total Invoice Amount'].apply(lambda x: f"${x:,.2f}")
                    bu_rev_df['Revenue Share %'] = bu_rev_df['Revenue Share %'].apply(lambda x: f"{x:.1f}%")
                    st.dataframe(bu_rev_df[['Business Unit', 'Total Revenue', 'Revenue Share %']].reset_index(drop=True), use_container_width=True)

            if "🗺️ Revenue Yield per Drive Hour (Geo-Routing Efficiency)" in test_choices:
                st.markdown("### **🗺️ Revenue Yield per Drive Hour (Geo-Routing Efficiency)**")
                route_eff = ops_df.groupby('Name').agg(Total_Revenue=('Total Invoice Amount', 'sum'), Total_Drive_Hrs=('Drive_Time_Hrs', 'sum')).reset_index()
                route_eff['Rev per Drive Hour Raw'] = np.where(route_eff['Total_Drive_Hrs'] > 0, route_eff['Total_Revenue'] / route_eff['Total_Drive_Hrs'], 0.0)
                route_eff = route_eff.sort_values(by='Rev per Drive Hour Raw', ascending=False)
                route_eff['Total Assigned Revenue'] = route_eff['Total_Revenue'].apply(lambda x: f"${x:,.2f}")
                route_eff['Total Drive Hours'] = route_eff['Total_Drive_Hrs'].apply(lambda x: f"{x:.1f} hrs")
                route_eff['Revenue per Drive Hour'] = route_eff['Rev per Drive Hour Raw'].apply(lambda x: f"${x:.1f}/hr")
                
                st.dataframe(route_eff[['Name', 'Total Assigned Revenue', 'Total Drive Hours', 'Revenue per Drive Hour']].reset_index(drop=True), use_container_width=True)

            if "🦺 Multi-Tech Labor Yield vs. Solo Runs" in test_choices:
                st.markdown("### **🦺 Multi-Tech Labor Yield vs. Solo Runs (Co-Efficiency Analysis)**")
                st.markdown("*(Assesses crew execution values factoring an applied $22.00/hr secondary helper cost burden override)*")
                df_m = unexploded_ops.copy()
                df_m['Tech_Count'] = df_m['Assigned Team Members'].apply(lambda x: len([m.strip() for m in str(x).split(',') if m.strip()]))
                df_m['Type'] = np.where(df_m['Tech_Count'] > 1, 'Multi-Tech Team Crew', 'Solo Dispatch Run')
                df_m['Total_Man_Hours'] = df_m['Tech_Count'] * df_m['Total_Job_Time_Hours']
                df_m['Helper_Labor_Cost'] = (df_m['Tech_Count'] - 1) * df_m['Total_Job_Time_Hours'] * 22.0
                
                summary_yield = df_m.groupby('Type').agg(
                    Job_Count=('#ID', 'count'),
                    Total_Revenue=('Total Invoice Amount', 'sum'),
                    Total_Field_Hours=('Total_Job_Time_Hours', 'sum'),
                    Total_Man_Hours=('Total_Man_Hours', 'sum'),
                    Total_Helper_Cost=('Helper_Labor_Cost', 'sum')
                ).reset_index()
                summary_yield['Avg Revenue per Job'] = summary_yield['Total_Revenue'] / summary_yield['Job_Count']
                summary_yield['Revenue per Man-Hour'] = summary_yield['Total_Revenue'] / summary_yield['Total_Man_Hours']
                
                show_yield = summary_yield.copy()
                show_yield['Total Revenue'] = show_yield['Total_Revenue'].apply(lambda x: f"${x:,.2f}")
                show_yield['Total Field Hours'] = show_yield['Total_Field_Hours'].apply(format_hm)
                show_yield['Total Man-Hours'] = show_yield['Total_Man_Hours'].apply(format_hm)
                show_yield['Added Helper Cost'] = show_yield['Total_Helper_Cost'].apply(lambda x: f"${x:,.2f}" if x > 0 else "-")
                show_yield['Avg Revenue per Job'] = show_yield['Avg Revenue per Job'].apply(lambda x: f"${x:,.2f}")
                show_yield['Revenue per Man-Hour'] = show_yield['Revenue per Man-Hour'].apply(lambda x: f"${x:.1f}/hr")
                st.dataframe(show_yield[['Type', 'Job_Count', 'Total Revenue', 'Total Field Hours', 'Total Man-Hours', 'Added Helper Cost', 'Avg Revenue per Job', 'Revenue per Man-Hour']].rename(columns={'Job_Count': 'Jobs Assigned'}), use_container_width=True)
                create_copy_button(show_yield, "multi_tech_yield")
                
                st.markdown("#### 🦺 Granular Team Dispatch Review Log")
                team_jobs = df_m[df_m['Tech_Count'] > 1].copy()
                if not team_jobs.empty:
                    team_jobs['Total Revenue'] = team_jobs['Total Invoice Amount'].apply(lambda x: f"${x:,.2f}")
                    team_jobs['Job Duration'] = team_jobs['Total_Job_Time_Hours'].apply(format_hm)
                    team_jobs['Helper Cost'] = team_jobs['Helper_Labor_Cost'].apply(lambda x: f"${x:,.2f}")
                    team_jobs['Man-Hours'] = team_jobs['Total_Man_Hours'].apply(format_hm)
                    show_team_jobs = team_jobs[['#ID', 'Assigned Team Members', 'Business Unit', 'Total Revenue', 'Job Duration', 'Man-Hours', 'Helper Cost']].rename(columns={'#ID': 'Job ID'}) if 'Business Unit' in team_jobs.columns else team_jobs[['#ID', 'Assigned Team Members', 'Total Revenue', 'Job Duration', 'Man-Hours', 'Helper Cost']].rename(columns={'#ID': 'Job ID'})
                    st.dataframe(show_team_jobs, use_container_width=True)
                    create_copy_button(show_team_jobs, "granular_team_log")
                else:
                    st.info("No paired team dispatches detected in current operational datasets.")

            if "📅 Lowe's Store Staging Delays by Day of the Week" in test_choices:
                st.markdown("### **📅 Lowe's Store Staging Delays by Day of the Week**")
                st.markdown("*(Tracks supply chain delay velocities day-by-day to optimize loading schedules)*")
                store_delay_df = unexploded_ops[unexploded_ops['Store_Time_Hrs'] > 0].copy()
                if not store_delay_df.empty:
                    day_order_map = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}
                    staging_agg = store_delay_df.groupby('Day_of_Week').agg(Total_Visits=('Store_Time_Hrs', 'count'), Total_Hours=('Store_Time_Hrs', 'sum')).reset_index()
                    staging_agg['Avg Delay per Visit Raw'] = staging_agg['Total_Hours'] / staging_agg['Total_Visits']
                    staging_agg['sort_day'] = staging_agg['Day_of_Week'].map(day_order_map)
                    staging_agg = staging_agg.sort_values(by='sort_day').drop(columns=['sort_day'])
                    
                    show_staging = staging_agg.copy()
                    show_staging['Total Hours Delayed'] = show_staging['Total_Hours'].apply(format_hm)
                    show_staging['Avg Delay per Visit'] = show_staging['Avg Delay per Visit Raw'].apply(format_hm)
                    st.dataframe(show_staging[['Day_of_Week', 'Total_Visits', 'Total Hours Delayed', 'Avg Delay per Visit']].rename(columns={'Day_of_Week': 'Day', 'Total_Visits': 'Store Pickups'}), use_container_width=True)
                    create_copy_button(show_staging[['Day_of_Week', 'Total_Visits', 'Total Hours Delayed', 'Avg Delay per Visit']], "store_staging_by_day")
                else:
                    st.info("No material store staging records discovered inside logged field parameters.")

            if "📊 Overtime ROI Cost-Benefit Auditor" in test_choices:
                st.markdown("### **📊 Overtime ROI Cost-Benefit Auditor**")
                st.markdown("*(Measures generated invoice revenue returns against the premium wage burden expenses of overtime dispatches)*")
                ot_audit_rows = []
                for idx, row in final_df.iterrows():
                    name = row['Name']
                    clocked = row['Total_Weekly_Clocked_Hrs']
                    revenue = row['Total_Assigned_Revenue']
                    nl = name.lower()
                    
                    rate = 0.0
                    if 'nate' in nl or 'nathan' in nl: rate = 22.50
                    elif 'tanner' in nl or 'matt schlosser' in nl: rate = 25.00
                    
                    if clocked > 40.0 and rate > 0:
                        ot_hours = clocked - 40.0
                        ot_premium_burden = ot_hours * rate * 0.5
                        ot_total_pay = ot_hours * rate * 1.5
                        roi_ratio = revenue / ot_total_pay if ot_total_pay > 0 else 0.0
                        ot_audit_rows.append({
                            "Name": name,
                            "Total Clocked Time": f"{clocked:.2f} hrs",
                            "Overtime Time": f"{ot_hours:.2f} hrs",
                            "Premium Burden Overhead (0.5x)": f"${ot_premium_burden:,.2f}",
                            "Total OT Wage Cost (1.5x)": f"${ot_total_pay:,.2f}",
                            "Total Weekly Revenue": f"${revenue:,.2f}",
                            "Revenue Yield per OT Pay Dollar": f"${roi_ratio:,.2f}/$"
                        })
                if ot_audit_rows:
                    st.dataframe(pd.DataFrame(ot_audit_rows), use_container_width=True)
                    create_copy_button(pd.DataFrame(ot_audit_rows), "overtime_roi_auditor")
                else:
                    st.success("✅ Zero hourly technicians incurred premium overtime thresholds during this invoice cycle.")

            if "🏆 Single-Job \"Whale Alert\" Revenue Leaderboard" in test_choices:
                st.markdown("### **🏆 Single-Job \"Whale Alert\" Revenue Leaderboard**")
                st.markdown("*(Highlights the top 5 highest-grossing individual unexploded invoices completed this cycle across the division)*")
                if not unexploded_ops.empty and 'Total Invoice Amount' in unexploded_ops.columns:
                    whale_df = unexploded_ops.sort_values(by='Total Invoice Amount', ascending=False).head(5).copy()
                    whale_summary = []
                    for _, r in whale_df.iterrows():
                        jid = int(r['#ID']) if ('#ID' in r and pd.notna(r['#ID'])) else "Unknown"
                        whale_summary.append({
                            "Job ID": str(jid),
                            "Assigned Crew Members": r['Assigned Team Members'],
                            "Business Unit Sector": r.get('Business Unit', 'Unknown'),
                            "Ticket Invoiced Revenue": f"${r['Total Invoice Amount']:,.2f}"
                        })
                    whale_summary_df = pd.DataFrame(whale_summary)
                    st.dataframe(whale_summary_df, use_container_width=True)
                    create_copy_button(whale_summary_df, "whale_alert_leaderboard")
                else:
                    st.info("No invoice details located inside loaded operations datasets.")

            if "🗺️ Interactive Territory Density and Hotspot Mapping" in test_choices:
                st.markdown("### **🗺️ Interactive Territory Density and Hotspot Mapping**")
                st.markdown("*(Translates exact street addresses into precise coordinates using Python's built-in tools—no installation required)*")
                
                df_map = ops_df.copy()
                if 'Location Address' in df_map.columns:
                    import urllib.request
                    import urllib.parse
                    import json
                    import time

                    unique_addresses = df_map['Location Address'].dropna().unique()
                    st.info(f"📍 Found {len(unique_addresses)} unique work addresses in your operational data.")
                    
                    # Manual user-triggered execution gate to avoid greedy execution hang-ups
                    if st.button("🚀 Render Exact Job Dispatch Map"):
                        progress_bar = st.progress(0.0)
                        status_text = st.empty()
                        
                        lats, lons = [], []
                        for idx, addr in enumerate(unique_addresses):
                            status_text.text(f"Processing address {idx + 1} of {len(unique_addresses)}...")
                            progress_bar.progress((idx + 1) / len(unique_addresses))
                            try:
                                search_addr = str(addr)
                                if " AZ" not in search_addr.upper() and "ARIZONA" not in search_addr.upper():
                                    search_addr += ", AZ"
                                
                                encoded_addr = urllib.parse.quote(search_addr)
                                url = f"https://nominatim.openstreetmap.org/search?q={encoded_addr}&format=json&limit=1"
                                req = urllib.request.Request(url, headers={'User-Agent': 'tech_time_tracker_built_in_v2'})
                                
                                with urllib.request.urlopen(req) as response:
                                    data = json.loads(response.read().decode())
                                    if data:
                                        lats.append(float(data[0]['lat']))
                                        lons.append(float(data[0]['lon']))
                                    else:
                                        lats.append(np.nan)
                                        lons.append(np.nan)
                                        
                                time.sleep(1) # Strict compliance with free tier geocoding API rate limits
                            except Exception:
                                lats.append(np.nan)
                                lons.append(np.nan)
                        
                        status_text.empty()
                        progress_bar.empty()
                        
                        coord_map = dict(zip(unique_addresses, zip(lats, lons)))
                        df_map['latitude'] = df_map['Location Address'].map(lambda x: coord_map.get(x, (np.nan, np.nan))[0])
                        df_map['longitude'] = df_map['Location Address'].map(lambda x: coord_map.get(x, (np.nan, np.nan))[1])
                        
                        map_points = df_map.dropna(subset=['latitude', 'longitude']).copy()
                        
                        if not map_points.empty:
                            st.map(map_points[['latitude', 'longitude']], use_container_width=True)
                            st.success(f"✅ Successfully mapped {len(map_points)} distinct field coordinates.")
                        else:
                            st.error("No valid matching points found. Please make sure the addresses are full street names.")
                else:
                    st.info("Location Address column header field parameter missing from raw ops data sheets.")

            if "🗺️ Geographic Revenue Yield per Drive Hour" in test_choices:
                st.markdown("### **🗺️ Geographic Revenue Yield per Drive Hour**")
                st.markdown("*(Measures the true invoice revenue generated per drive hour across different destination regions to isolate high-leakage transport lanes)*")
                
                df_yield = ops_df.copy()
                if 'Location Address' in df_yield.columns:
                    df_yield['City Location Sector'] = df_yield['Location Address'].apply(parse_az_city)
                    
                    geo_yield = df_yield.groupby('City Location Sector').agg(
                        Jobs_Assigned=('#ID', 'count'),
                        Gross_Invoiced_Volume=('Total Invoice Amount', 'sum'),
                        Total_Travel_Time=('Drive_Time_Hrs', 'sum')
                    ).reset_index()
                    
                    geo_yield['Yield per Travel Hour Raw'] = np.where(geo_yield['Total_Travel_Time'] > 0, geo_yield['Gross_Invoiced_Volume'] / geo_yield['Total_Travel_Time'], 0.0)
                    geo_yield = geo_yield.sort_values(by='Yield per Travel Hour Raw', ascending=False)
                    
                    show_geo_yield = geo_yield.copy()
                    show_geo_yield['Gross Invoiced Volume'] = show_geo_yield['Gross_Invoiced_Volume'].apply(lambda x: f"${x:,.2f}")
                    show_geo_yield['Total Travel Time'] = show_geo_yield['Total_Travel_Time'].apply(lambda x: f"{x:.2f} hrs")
                    show_geo_yield['Revenue per Travel Hour'] = show_geo_yield['Yield per Travel Hour Raw'].apply(lambda x: f"${x:,.2f}/hr" if x > 0 else "-")
                    
                    final_yield_df = show_geo_yield[['City Location Sector', 'Jobs_Assigned', 'Gross Invoiced Volume', 'Total Travel Time', 'Revenue per Travel Hour']].rename(columns={'City Location Sector': 'Territory City', 'Jobs_Assigned': 'Jobs Closed'})
                    st.dataframe(final_yield_df, use_container_width=True)
                    create_copy_button(final_yield_df, "geographic_revenue_yield_drive_hour")
                else: st.info("Location Address column missing from raw ops datasets.")

            if "🚛 End-of-Day (EOD) Payroll Slippage Auditor" in test_choices:
                st.markdown("### **🚛 End-of-Day (EOD) Payroll Slippage Auditor**")
                st.markdown("*(Flags instances where a technician remained clocked in for more than 90 minutes after completing their final job order)*")
                
                if 'sample_df' in locals() and not bounds_df.empty:
                    sample_df['Short_Date'] = pd.to_datetime(sample_df['Clock In Date/Time'], errors='coerce').dt.strftime('%m-%d-%Y')
                    ts_eod = sample_df.groupby(['User', 'Short_Date'])['Clock_Out_dt'].max().reset_index()
                    ts_eod.columns = ['Assigned Team Members', 'Short_Date', 'Actual_Clock_Out']
                    
                    eod_merged = pd.merge(bounds_df, ts_eod, on=['Assigned Team Members', 'Short_Date'], how='inner')
                    eod_merged['Slippage_Hrs'] = (eod_merged['Actual_Clock_Out'] - eod_merged['Last_Punch']).dt.total_seconds() / 3600.0
                    
                    slippage_alerts = eod_merged[eod_merged['Slippage_Hrs'] > 1.5].copy()
                    if not slippage_alerts.empty:
                        slippage_alerts = slippage_alerts.sort_values(by='Slippage_Hrs', ascending=False)
                        slippage_alerts['Job Close Time'] = slippage_alerts['Last_Punch'].dt.strftime('%I:%M %p')
                        slippage_alerts['Timecard Clockout'] = slippage_alerts['Actual_Clock_Out'].dt.strftime('%I:%M %p')
                        slippage_alerts['Unaccounted Overtime'] = slippage_alerts['Slippage_Hrs'].apply(format_hm)
                        
                        show_slippage = slippage_alerts[['Assigned Team Members', 'Short_Date', 'Job Close Time', 'Timecard Clockout', 'Unaccounted Overtime']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date'})
                        st.dataframe(show_slippage.reset_index(drop=True), use_container_width=True)
                        create_copy_button(show_slippage, "eod_slippage_auditor")
                    else:
                        st.success("✅ Excellent shift close alignment. All technician timecards match close-of-work operational profiles.")

            if "⏱️ Technician Task Speed Leaderboard (Sub-Type)" in test_choices:
                st.markdown("### **⏱️ Technician Task Speed Leaderboard (Sub-Type)**")
                st.markdown("*(Breaks down specific job titles and compares average completion times across technicians to pinpoint the fastest executor)*")
                
                cols_lower = [str(c).lower().strip() for c in ops_df.columns]
                subtype_col = None
                for target in ['job title', 'task', 'service type', 'description', 'work order type', 'item description', 'job type']:
                    if target in cols_lower:
                        subtype_col = ops_df.columns[cols_lower.index(target)]
                        break
                        
                if subtype_col:
                    task_df = ops_df[ops_df['Total_Job_Time_Hours'] > 0].copy()
                    if not task_df.empty:
                        unique_tasks = sorted([str(x) for x in task_df[subtype_col].dropna().unique()])
                        selected_task = st.selectbox("Select a Job Sub-Type to Analyze:", unique_tasks, key="test_task_speed_selector")
                        
                        if selected_task:
                            task_subset = task_df[task_df[subtype_col] == selected_task]
                            
                            tech_task_stats = task_subset.groupby('Name').agg(
                                Jobs_Completed=('#ID', 'count') if '#ID' in task_df.columns else (subtype_col, 'count'),
                                Avg_Time=('Total_Job_Time_Hours', 'mean'),
                                Min_Time=('Total_Job_Time_Hours', 'min'),
                                Max_Time=('Total_Job_Time_Hours', 'max')
                            ).reset_index()
                            
                            tech_task_stats = tech_task_stats.sort_values(by='Avg_Time', ascending=True)
                            
                            show_task_stats = tech_task_stats.copy()
                            show_task_stats['Avg Time'] = show_task_stats['Avg_Time'].apply(format_hm)
                            show_task_stats['Min Time'] = show_task_stats['Min_Time'].apply(format_hm)
                            show_task_stats['Max Time'] = show_task_stats['Max_Time'].apply(format_hm)
                            
                            final_show = show_task_stats[['Name', 'Jobs_Completed', 'Avg Time', 'Min Time', 'Max Time']].rename(columns={'Jobs_Completed': 'Times Performed'})
                            
                            def highlight_fastest(row):
                                if row.name == final_show.index[0]:
                                    return ['background-color: #e6f4ea; color: #137333; font-weight: bold;'] * len(row)
                                return [''] * len(row)

                            try:
                                st.dataframe(final_show.style.apply(highlight_fastest, axis=1), use_container_width=True)
                            except Exception:
                                st.dataframe(final_show, use_container_width=True)
                                
                            create_copy_button(final_show, "tech_task_speed")
                    else:
                        st.info("No job duration data available for sub-types to calculate speeds.")
                else:
                    st.info("⚠️ Could not identify a 'Job Title' or 'Task' column in the uploaded ops data to generate the sub-type breakdown. Please verify your export columns.")


    except Exception as e:
        st.error(f"An error occurred while processing the files: Please ensure you uploaded the correct CSV formats. Exact error: {e}")
