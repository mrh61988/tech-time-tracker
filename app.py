import streamlit as st
import pandas as pd
import numpy as np
import io

# Set up the page layout
st.set_page_config(page_title="Tech Time Tracker", layout="wide")

# --- CSS FOR CLEAN LANDSCAPE FULL-WIDTH MULTI-PAGE PRINTING ---
st.markdown("""
<style>
@media print {
    /* Enforce landscape orientation to maximize wide printable space layout margins */
    @page {
        size: landscape;
        margin: 0.4in !important;
    }

    /* Hide structural utility blocks, upload buttons, tabs navigation bars, and panels from saved PDFs */
    header { display: none !important; }
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapseButton"] { display: none !important; }
    [data-testid="stFileUploader"] { display: none !important; }
    [data-testid="stSelectbox"] { display: none !important; }
    div[data-baseweb="tab-list"] { display: none !important; }
    h1, .hide-on-print, .stAlert, iframe, button { display: none !important; }
    div[class*="stExpander"] { display: none !important; }
    
    /* Flatten flex and grid containers to standard sequential blocks to block overlapping */
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
        page-break-inside: avoid !important;
    }
    
    h2, h3, h4 {
        page-break-inside: avoid !important;
        page-break-after: avoid !important;
        margin-top: 20px !important;
        margin-bottom: 8px !important;
    }

    /* Unclamp core block layout canvas gutters to run margin-to-margin smoothly */
    div[data-testid="stAppViewBlockContainer"],
    .main .block-container,
    div[class*="block-container"] {
        max-width: 100% !important;
        width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Forces summary KPI card layout objects to look clean side-by-side in Landscape */
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
    
    /* Grants wide tables and dataframes maximum layout canvas real estate */
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
    fp = row['First_Punch']
    status = row['First_Status']
    if pd.isna(fp): return False
    if status in ['On The Way', 'Lowes Store']:
        return fp.hour >= 8
    elif status == 'In Progress':
        return fp.hour > 8 or (fp.hour == 8 and fp.minute >= 30)
    return False

def check_contractor(tech_str):
    CORE_TECHS = ['Bryan Pickett', 'Edward Lopez', 'Erik Tange', 'Matt Schlosser', 'Michael Owens', 'Nathan Smith', 'Sean Marble', 'Tanner LaForge']
    raw_members = [m.strip() for m in str(tech_str).split(',') if m.strip()]
    return not any(m in CORE_TECHS for m in raw_members)

def get_first_core_tech(tech_str):
    CORE_TECHS = ['Bryan Pickett', 'Edward Lopez', 'Erik Tange', 'Matt Schlosser', 'Michael Owens', 'Nathan Smith', 'Sean Marble', 'Tanner LaForge']
    raw_members = [m.strip() for m in str(tech_str).split(',') if m.strip()]
    core_members_on_job = [m for m in raw_members if m in CORE_TECHS]
    if core_members_on_job:
        return core_members_on_job[0]
    return None

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

# AUDITOR ROW MARGIN HIGHLIGHTER ENGINE
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

# NATIVE SYSTEM CLIPBOARD DATA EXPORTER (DEFINED AT GLOBAL SCOPE LEVEL)
def create_copy_button(df, raw_key):
    safe_key = "".join([c if c.isalnum() else "_" for c in raw_key])
    tsv_str = df.to_csv(sep='\t', index=False)
    safe_tsv = tsv_str.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
    
    button_html = f"""
    <div class="hide-on-print" style="text-align: left; margin-top: 5px; margin-bottom: 8px;">
        <textarea id="tsv_{safe_key}" style="position: absolute; left: -9999px;">{safe_tsv}</textarea>
        <button id="btn_{safe_key}" onclick="copyTSV_{safe_key}()" style="background-color: #ffffff; color: #3c4043; padding: 6px 14px; border: 1px solid #dadce0; border-radius: 4px; cursor: pointer; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); transition: background-color 0.2s;">
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

# --- CORE ADVANCED BASELINE REPORT GENERATOR PANEL ---
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
            create_copy_button(wh_matrix_df, "wh_over_baseline")
        else: st.success("✅ Zero individual Water Heater jobs exceeded the division baseline average.")
            
    with split_col2:
        st.markdown("##### 🔧 Simple Installs Over-Baseline Jobs")
        if lsi_over_baseline_rows:
            lsi_matrix_df = pd.DataFrame(lsi_over_baseline_rows).sort_values(by='sort_key', ascending=False).drop(columns=['sort_key']).reset_index(drop=True)
            try: st.dataframe(lsi_matrix_df.style.apply(highlight_over_hour_row, axis=1), use_container_width=True)
            except Exception: st.dataframe(lsi_matrix_df, use_container_width=True)
            create_copy_button(lsi_matrix_df, "lsi_over_baseline")
        else: st.success("✅ Zero individual Simple Install jobs exceeded the division baseline average.")

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
        create_copy_button(trend_df, f"trend_{tab_key}")

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
            try: st.dataframe(show_leaderboard.reset_index(drop=True).style.apply(highlight_leaderboard, axis=1), use_container_width=True)
            except Exception: st.dataframe(show_leaderboard.reset_index(drop=True), use_container_width=True)
            create_copy_button(show_leaderboard.reset_index(drop=True), f"leaderboard_{tab_key}")

    # === OVERTIME HORIZON PREDICTOR ===
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🚨 Fleet Overtime Horizon Predictor")
    st.markdown("*(Monitors pacing thresholds. Salaried under 35 hrs and Piece-Rate over 45 hrs flag red automatically)*")
    ot_rows = []
    for idx, row in final_df.iterrows():
        tech_name = row['Name']
        nl = tech_name.lower()
        hrs = row['Total_Weekly_Clocked_Hrs']
        job_hrs = row['Total_Weekly_Job_Hrs']
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
        ot_rows.append({
            "Name": tech_name,
            "Weekly Clocked": format_hm(hrs),
            "Total Job Time": format_hm(job_hrs),
            "Pace Status": status,
            "Overtime Hours": ot_hrs
        })
    if ot_rows:
        ot_predictor_df = pd.DataFrame(ot_rows)
        def style_ot_predictor(row):
            st_val = row['Pace Status']
            if "🚨" in st_val or "⚠️ Low Volume" in st_val: return ['background-color: #ffcccc; color: #990000;'] * len(row)
            if "⚠️ High Overtime" in st_val: return ['background-color: #fff3cd; color: #856404;'] * len(row)
            return [''] * len(row)
        try: st.dataframe(ot_predictor_df.reset_index(drop=True).style.apply(style_ot_predictor, axis=1), use_container_width=True)
        except Exception: st.dataframe(ot_predictor_df.reset_index(drop=True), use_container_width=True)
        create_copy_button(ot_predictor_df.reset_index(drop=True), f"overtime_{tab_key}")
            
    st.markdown("<br>", unsafe_allow_html=True)

    # === CONSOLIDATED MAIN VIEW BLOCKS ===
    st.header("📊 Ops Manager Tools (Benchmarking & Performance)")
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("⭐ The Gold Star High-Performer List")
        st.markdown("*(Technicians who average under 1:30 of unallocated difference per day worked. Store delays do NOT penalize techs)*")
        gold_star_df = final_df[(final_df['Daily_Avg_Diff_Hrs'] < 1.5) & (final_df['Days_Worked'] > 0)].copy()
        if not gold_star_df.empty:
            gold_star_df = gold_star_df.sort_values(by='Daily_Avg_Diff_Hrs', ascending=True)
            gold_star_df['Total Clocked'] = gold_star_df['Total_Weekly_Clocked_Hrs'].apply(format_hm)
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
            
            # CRITICAL WARNING SORT ENGINE IMPLEMENTATION
            skill_df['sort_action'] = skill_df['Action Required'].apply(lambda x: 0 if '⚠️' in str(x) else (1 if 'ℹ️' in str(x) else 2))
            skill_df = skill_df.sort_values(by='sort_action', ascending=True)
            
            show_skill = skill_df[['Name', 'Simple Installs Eff', 'Water Heaters Eff', 'Action Required']].rename(columns={'Simple Installs Eff': 'LSI Efficiency', 'Water Heaters Eff': 'WH Efficiency'})
            def style_flags(row): return ['background-color: #fff3cd; color: #856404; font-weight: bold;'] * len(row) if '⚠️' in row['Action Required'] else [''] * len(row)
            try: st.dataframe(show_skill.reset_index(drop=True).style.apply(style_flags, axis=1), use_container_width=True)
            except Exception: st.dataframe(show_skill.reset_index(drop=True), use_container_width=True)
            create_copy_button(show_skill.reset_index(drop=True), f"skills_{tab_key}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🗺️ Route Optimization Flags")
    st.markdown("*(Identifies service days where a technician spent over 40% of their billable shift driving to audit route density)*")
    
    # 🗺️ GEOGRAPHIC PLOT UPGRADE: Apply absolute metric sort loop prior to formatting conversion
    poor_routes = daily_route[daily_route['Drive %'] > 40.0].copy()
    if not poor_routes.empty:
        poor_routes = poor_routes.sort_values(by='Drive %', ascending=False)
        poor_routes['Drive %'] = poor_routes['Drive %'].apply(lambda x: f"{x:.1f}%")
        poor_routes['Drive Time'] = poor_routes['Drive_Time_Hrs'].apply(format_hm)
        poor_routes['Work Time'] = poor_routes['In_Progress_Time_Hrs'].apply(format_hm)
        route_df_export = poor_routes[['Assigned Team Members', 'Short_Date', 'Job_Count', 'Drive Time', 'Work Time', 'Drive %']].rename(columns={'Assigned Team Members': 'Name', 'Short_Date': 'Date', 'Job_Count': 'Jobs'}).reset_index(drop=True)
        st.dataframe(route_df_export, use_container_width=True)
        create_copy_button(route_df_export, f"routes_{tab_key}")

    st.markdown("<br>", unsafe_allow_html=True)
    launch_col, launch_empty_col = st.columns(2)
    with launch_col:
        st.subheader("📊 Late Deployment Scorecard")
        st.markdown("*(Aggregates the total number of delayed morning launches per technician across the week)*")
        if not delayed_launches_df.empty:
            launch_counts = delayed_launches_df.groupby('Assigned Team Members').size().reset_index(name='Total Late Days').sort_values(by='Total Late Days', ascending=False)
            try: st.dataframe(launch_counts.reset_index(drop=True).style.set_properties(**{'background-color': '#fff3cd', 'color': '#856404;'}, subset=['Total Late Days']), use_container_width=True)
            except Exception: st.dataframe(launch_counts.reset_index(drop=True), use_container_width=True)
            create_copy_button(launch_counts.reset_index(drop=True).rename(columns={'Assigned Team Members': 'Name'}), f"late_score_{tab_key}")

    with launch_empty_col:
        st.subheader("🚗 Delayed Launch Alert")
        st.markdown("*(Provides a day-by-day chronological log of start-of-day timeline compliance delays)*")
        
        # 🚗 TIMELINE PRESET UPGRADE: Automatically calculate indices tracking who holds highest delay values 
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

# --- CONSOLIDATED SANDBOX TAB VIEWS ENGINE ---
def run_sandbox_tab(unexploded_ops, ops_df, final_df, daily_route, bu_financial_matrix, total_assumed_pay_adjusted, pay_ratio_pct_adjusted, sean_penalty, test_choices):
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
                    if "sean marble" in nl or "michael owens" in nl: pay_type = "Salary"
                    elif "bryan" in nl or "erik" in nl: pay_type = "Piece Rate"
                    for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                        clocked = row[f'{d}_Clocked_Hrs']
                        jobs = row[f'{d}_Job_Count']
                        if clocked > 0 and jobs == 0: ghost_alerts.append({"Technician": tech_name, "Pay Profile": pay_type, "Day": d, "Audit Type": "🕵️ Paid But Idle (Clocked In, 0 Jobs Run)", "Clocked Hours": format_hm(clocked), "Jobs Done": 0})
                        elif clocked == 0 and jobs > 0: ghost_alerts.append({"Technician": tech_name, "Pay Profile": pay_type, "Day": d, "Audit Type": "🚨 Unpaid Field Work (0 Hours Clocked, Jobs Run)", "Clocked Hours": format_hm(clocked), "Jobs Done": int(jobs)})
                if ghost_alerts: st.dataframe(pd.DataFrame(ghost_alerts), use_container_width=True)
                else: st.success("Perfect alignment! No payroll discrepancy errors detected.")

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
                    st.dataframe(show_rev_per_hour.reset_index(drop=True), use_container_width=True)

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
                route_eff = ops_df.groupby('Name').agg(Total_Revenue=('Total Invoice Amount', 'sum'), Total_Drive_Hrs=('Drive_Time_Hrs', 'sum')).reset_index()
                route_eff['Rev per Drive Hour Raw'] = np.where(route_eff['Total_Drive_Hrs'] > 0, route_eff['Total_Revenue'] / route_eff['Total_Drive_Hrs'], 0.0)
                route_eff = route_eff.sort_values(by='Rev per Drive Hour Raw', ascending=False)
                route_eff['Total Assigned Revenue'] = route_eff['Total_Revenue'].apply(lambda x: f"${x:,.2f}")
                route_eff['Total Drive Hours'] = route_eff['Total_Drive_Hrs'].apply(lambda x: f"{x:.1f} hrs")
                route_eff['Revenue per Drive Hour'] = route_eff['Rev per Drive Hour Raw'].apply(lambda x: f"{x:.1f}/hr")
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
                    show_team_jobs = team_jobs[['#ID', 'Assigned Team Members', 'Business Unit', 'Total Revenue', 'Job Duration', 'Man-Hours', 'Helper Cost']].rename(columns={'#ID': 'Job ID'})
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
                    elif any(n in nl for n in ['edward', 'matt', 'tanner']): rate = 25.00
                    
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
                    ot_audit_df = pd.DataFrame(ot_audit_rows)
                    st.dataframe(ot_audit_df, use_container_width=True)
                    create_copy_button(ot_audit_df, "overtime_roi_auditor")
                else:
                    st.success("¼ Hourly technicians worked zero premium overtime thresholds during this session cycle.")

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
                            "Business Unit Sector": r['Business Unit'] if 'Business Unit' in r else "Unknown",
                            "Ticket Invoiced Revenue": f"${r['Total Invoice Amount']:,.2f}"
                        })
                    whale_summary_df = pd.DataFrame(whale_summary)
                    st.dataframe(whale_summary_df, use_container_width=True)
                    create_copy_button(whale_summary_df, "whale_alert_leaderboard")
                else:
                    st.info("No invoice details located inside loaded operations datasets.")

            # FIXED MENUS CONFIGURATION HIERARCHY FOR PROFIT MARGIN SUITE ACTIVATION
            if "💵 Division True Net Profitability Margin Auditor" in test_choices:
                st.markdown("### **💵 Division True Net Profitability Margin Auditor**")
                st.markdown("*(Evaluates net profitability metrics across selected sectors factoring contract structures, costs backouts and non-negative thresholds)*")
                
                sort_pane_col, filter_pane_col = st.columns(2)
                with filter_pane_col:
                    selected_bu_filter = st.selectbox("Filter Performance Register By Line of Business:", ["All Sectors", "Lowes - Water Heaters", "Lowes - Simple Installs"], key="bu_perf_filter_matrix")
                with sort_pane_col:
                    selected_sort_choice = st.selectbox("Sort Itemized Register Results By:", ["Highest Net Profit", "Lowest Net Profit", "Highest Gross Invoice", "Highest Margin %", "Job ID"], key="sorting_perf_matrix")
                    
                df_prof_totals = df_macro_pay.copy()
                if selected_bu_filter != "All Sectors":
                    df_prof_totals = df_prof_totals[df_prof_totals['Business Unit'] == selected_bu_filter]
                    
                if not df_prof_totals.empty:
                    gross_revenue_sum = df_prof_totals['Total Invoice Amount'].sum()
                    combined_cost_sum = df_prof_totals['Combined_Lowe_Costs'].sum()
                    labor_payload_sum = df_prof_totals['Assumed_Labor_Payload'].sum()
                    
                    if selected_bu_filter in ["All Sectors", "Lowes - Simple Installs"]:
                        labor_payload_sum = max(0.0, labor_payload_sum - sean_penalty)
                    
                    net_profit_sum = gross_revenue_sum - combined_cost_sum - labor_payload_sum
                    
                    totals_summary_df = pd.DataFrame([{
                        "Total Dispatches Closed": int(len(df_prof_totals)),
                        "Gross Invoiced Revenue": f"${gross_revenue_sum:,.2f}",
                        "Total Combined Cost": f"${combined_cost_sum:,.2f}",
                        "Tech Wage Burden": f"${labor_payload_sum:,.2f}",
                        "Net Profit ($)": f"${net_profit_sum:,.2f}",
                        "Net Profit (%)": f"{(net_profit_sum / gross_revenue_sum * 100):.1f}%" if gross_revenue_sum > 0 else "0.0%"
                    }])
                    
                    # 🖥️ SCROLLBAR REMOVAL ENGINE: Apply high explicit vertical canvas bounds parameters based on data items layout
                    st.dataframe(totals_summary_df, use_container_width=True, height=(len(totals_summary_df) + 1) * 35 + 45)
                    create_copy_button(totals_summary_df, "profitability_summary_totals")
                    st.markdown("   ")
                    
                    df_prof_filtered = df_macro_pay.copy()
                    if selected_bu_filter != "All Sectors":
                        df_prof_filtered = df_prof_filtered[df_prof_filtered['Business Unit'] == selected_bu_filter]
                    df_prof_filtered = df_prof_filtered[~df_prof_filtered['Is_Contractor']]
                    
                    if not df_prof_filtered.empty:
                        df_prof_filtered['Profit Margin %'] = np.where(df_prof_filtered['Total Invoice Amount'] > 0, (df_prof_filtered['Net_Profit_Raw'] / df_prof_filtered['Total Invoice Amount'] * 100), 0.0)
                        
                        if selected_sort_choice == "Highest Net Profit": df_prof_filtered = df_prof_filtered.sort_values(by='Net_Profit_Raw', ascending=False)
                        elif selected_sort_choice == "Lowest Net Profit": df_prof_filtered = df_prof_filtered.sort_values(by='Net_Profit_Raw', ascending=True)
                        elif selected_sort_choice == "Highest Gross Invoice": df_prof_filtered = df_prof_filtered.sort_values(by='Total Invoice Amount', ascending=False)
                        elif selected_sort_choice == "Highest Margin %": df_prof_filtered = df_prof_filtered.sort_values(by='Profit Margin %', ascending=False)
                        else: df_prof_filtered = df_prof_filtered.sort_values(by='#ID', ascending=True)
                        
                        prof_register_rows = []
                        for _, r in df_prof_filtered.iterrows():
                            prof_register_rows.append({
                                "Job ID": str(int(r['#ID'])),
                                "Line of Business": r['Business Unit'],
                                "Crew Assigned": r['Assigned Team Members'],
                                "Gross Invoice": f"${r['Total Invoice Amount']:,.2f}",
                                "Total Combined Cost": f"${r['Combined_Lowe_Costs']:,.2f}",
                                "Tech Wage Burden": f"${r['Assumed_Labor_Payload']:,.2f}",
                                "Net Profit": f"${r['Net_Profit_Raw']:,.2f}",
                                "Margin %": f"{r['Profit Margin %']:.1f}%"
                            })
                        
                        prof_register_df = pd.DataFrame(prof_register_rows, columns=[
                            "Job ID", "Line of Business", "Crew Assigned", "Gross Invoice", 
                            "Total Combined Cost", "Tech Wage Burden", "Net Profit", "Margin %"
                        ])
                        
                        try:
                            styled_reg = prof_register_df.style.apply(highlight_low_margins, axis=1)
                            st.dataframe(styled_reg, use_container_width=True, height=(len(prof_register_df) + 1) * 35 + 45)
                        except Exception:
                            st.dataframe(prof_register_df, use_container_width=True, height=(len(prof_register_df) + 1) * 35 + 45)
                        create_copy_button(prof_register_df, "sortable_job_margins_register")
                    else: st.info("No core internal crew members jobs found for selected parameters layout block.")

            if "📦 Product vs. Service Cost Component Breakdown Matrix" in test_choices or "📦 Lowe's Combined Cost Performance Matrix" in test_choices:
                st.markdown("### **📦 Lowe's Combined Cost Performance Matrix**")
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
                        cc_matrix.loc[idx, 'Assumed_Labor_Payload_Raw'] = max(0.0, cc_matrix.loc[idx, 'Assumed_Labor_Payload_Raw'] - sean_penalty)
                        cc_matrix.loc[idx, 'Net_Profit_Total_Raw'] = cc_matrix.loc[idx, 'Gross_Invoiced_Raw'] - cc_matrix.loc[idx, 'Combined_Cost_Total_Raw'] - cc_matrix.loc[idx, 'Assumed_Labor_Payload_Raw']
                
                cc_matrix['Cost Ratio % vs Rev'] = np.where(cc_matrix['Gross_Invoiced_Raw'] > 0, (cc_matrix['Combined_Cost_Total_Raw'] / cc_matrix['Gross_Invoiced_Raw'] * 100), 0.0)
                cc_matrix['Cost Ratio % vs Rev'] = cc_matrix['Cost Ratio % vs Rev'].apply(lambda x: f"{x:.1f}%")
                cc_matrix['Net Profit (%)'] = cc_matrix['Net_Profit_Total_Raw'] / cc_matrix['Gross_Invoiced_Raw'] * 100
                cc_matrix['Net Profit (%)'] = cc_matrix['Net_Profit (%)'].apply(lambda x: f"{x:.1f}%")
                cc_matrix['Gross Invoiced Revenue'] = cc_matrix['Gross_Invoiced_Raw'].apply(lambda x: f"${x:,.2f}")
                cc_matrix['Total Combined Cost'] = cc_matrix['Combined_Cost_Total_Raw'].apply(lambda x: f"${x:,.2f}")
                cc_matrix['Tech Wage Burden'] = cc_matrix['Assumed_Labor_Payload_Raw'].apply(lambda x: f"${x:,.2f}")
                cc_matrix['Net Profit ($)'] = cc_matrix['Net_Profit_Total_Raw'].apply(lambda x: f"${x:,.2f}")
                
                show_cc = cc_matrix[['Business Unit', 'Jobs', 'Gross Invoiced Revenue', 'Total Combined Cost', 'Cost Ratio % vs Rev', 'Tech Wage Burden', 'Net Profit ($)', 'Net Profit (%)']].rename(columns={'Jobs': 'Jobs Assigned'})
                st.dataframe(show_cc, use_container_width=True)
                create_copy_button(show_cc, "product_vs_service_cost_breakdown")
            
    except Exception as e:
        st.error(f"An error occurred while processing the files: Please ensure you uploaded the correct CSV formats. Exact error: {e}")
