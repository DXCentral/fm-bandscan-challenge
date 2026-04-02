import streamlit as st
import pandas as pd
import numpy as np
import math
import datetime

# --- 1. CONFIG & DATA LOADING ---
STATION_DATA = "FM Challenge - Station List and Data - WTFDA Data.csv"

@st.cache_data
def load_stations():
    df = pd.read_csv(STATION_DATA)
    # Clean Callsign: Strip -FM but keep -LP and -LD
    df['Station Callsign'] = df['Callsign'].str.replace(r'-FM$', '', regex=True)
    # FIX: Force PI Code to string to prevent Scientific Notation (5.36E+03)
    df['PI Code'] = df['PI Code'].astype(str).replace('nan', '')
    # Rename S/P for user friendliness
    df = df.rename(columns={'S/P': 'State/Province'})
    return df

# --- 2. THE DISTANCE ENGINE ---
def dms_to_dd(dms_str):
    try:
        parts = dms_str.split('-')
        return float(parts[0]) + (float(parts[1]) / 60) + (float(parts[2]) / 3600)
    except: return None

def calculate_distance(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]: return 0
    R = 3958.8 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a)), 1)

# --- 3. UI SETUP & SESSION STATE ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()

# Initialize session state for filters
if 'reset_filters' not in st.session_state:
    st.session_state.reset_filters = False

# Sidebar
with st.sidebar:
    st.header("Personal Settings")
    dxer_name = st.text_input("DXer Name", value=st.session_state.get('dxer_name', ""))
    # Mandeville Default Coordinates
    home_lat, home_lon = 30.3583, -90.0656 
    st.session_state['dxer_name'] = dxer_name

# --- 4. SEARCH & FILTERS ---
st.subheader("🔍 Station Search")

c1, c2, c3, c4, c5, c6 = st.columns(6)
f_freq = c1.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None, key='f_freq_val')
f_call = c2.text_input("Callsign", key='f_call_val').upper()
f_city = c3.text_input("City", key='f_city_val')
f_sp = c4.text_input("State/Prov (Fuzzy)", key='f_sp_val')
f_country = c5.text_input("Country", key='f_country_val')
f_slogan = c6.text_input("Slogan", key='f_slogan_val')

# Reset Button
_, center_col, _ = st.columns([2, 1, 2])
if center_col.button("Clear All Filters", use_container_width=True):
    # Manual clear of widget states
    st.session_state.f_freq_val = None
    st.session_state.f_call_val = ""
    st.session_state.f_city_val = ""
    st.session_state.f_sp_val = ""
    st.session_state.f_country_val = ""
    st.session_state.f_slogan_val = ""
    st.rerun()

# --- 5. FILTER LOGIC ---
view_df = df_stations.copy()
if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
if f_call: view_df = view_df[view_df['Station Callsign'].str.contains(f_call, na=False)]
if f_city: view_df = view_df[view_df['City'].str.contains(f_city, case=False, na=False)]
if f_sp: view_df = view_df[view_df['State/Province'].str.contains(f_sp, case=False, na=False)]
if f_country: view_df = view_df[view_df['Country'].str.contains(f_country, case=False, na=False)]
if f_slogan: view_df = view_df[view_df['Slogan'].str.contains(f_slogan, case=False, na=False)]

# Calculate Distance for Table
view_df['Dist'] = view_df.apply(lambda row: calculate_distance(home_lat, home_lon, dms_to_dd(row['Lat-N']), -dms_to_dd(row['Long-W'])), axis=1)

# --- 6. THE INTERACTIVE TABLE ---
st.write(f"Showing {len(view_df)} stations. Check the 'Log?' box to select a station:")
view_df.insert(0, 'Select', False)

edited_df = st.data_editor(
    view_df[['Select', 'Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist']],
    use_container_width=True,
    hide_index=True,
    column_config={"Select": st.column_config.CheckboxColumn("Log?", default=False)},
    disabled=['Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist'],
    key="editor"
)

# --- 7. LOGGING FORM ---
selected_rows = edited_df[edited_df['Select'] == True]
if not selected_rows.empty:
    station = selected_rows.iloc[0]
    st.divider()
    
    with st.form("log_entry", clear_on_submit=True):
        st.subheader(f"📝 Log: {station['Station Callsign']} ({station['Frequency']})")
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        c_date, c_time = st.columns(2)
        log_date = c_date.date_input("Date (UTC)", value=now_utc.date())
        log_time = c_time.text_input("Time (UTC - HHMM)", value=now_utc.strftime("%H%M"))

        col_a, col_b = st.columns(2)
        with col_a:
            rds_ready = st.selectbox("RDS Decoded?", ["No", "Yes"])
            # Keeps the pre-populated PI Code as a string
            pi_code = st.text_input("PI Code", value=station['PI Code'] if rds_ready == "Yes" else "")
            sig = st.text_input("Signal Strength (dBm)")
            
        with col_b:
            cat = st.selectbox("Frequency Category", ["", "Open", "Fringe", "Semi-Local", "Local-HD", "Strong Local"], index=0)
            prop = st.selectbox("Propagation", ["Local", "Tropo", "Es", "Meteor Scatter"])
            fmlist = st.checkbox("Logged on FMList?")
            wlogger = st.checkbox("Logged on WLogger?")

        if st.form_submit_button("Submit Log Entry"):
            if not dxer_name:
                st.error("Please enter your name in the sidebar!")
            else:
                st.success(f"Entry for {station['Station Callsign']} recorded locally! (GSheet Logic Next)")
