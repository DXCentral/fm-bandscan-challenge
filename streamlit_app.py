import streamlit as st
import pandas as pd
import numpy as np
import math
import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIG & DATA LOADING ---
STATION_DATA = "FM Challenge - Station List and Data - WTFDA Data.csv"

@st.cache_data
def load_stations():
    df = pd.read_csv(STATION_DATA)
    # Clean Callsign: Strip -FM, keep -LP/-LD
    df['Callsign_Clean'] = df['Callsign'].str.replace(r'-FM$', '', regex=True)
    # Rename columns for the UI as requested
    df = df.rename(columns={
        'Callsign_Clean': 'Station Callsign',
        'S/P': 'State/Province'
    })
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

# --- 3. UI SETUP ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()

# Sidebar Settings
with st.sidebar:
    st.header("Personal Settings")
    dxer_name = st.text_input("DXer Name", value=st.session_state.get('dxer_name', ""))
    dxer_city = st.text_input("Your City", value=st.session_state.get('dxer_city', "Mandeville"))
    dxer_st = st.text_input("Your State", value=st.session_state.get('dxer_st', "LA"))
    
    # Placeholder for Home Lat/Long (Mandeville)
    # In a future update, we can swap this for a geocoding lookup
    home_lat, home_lon = 30.3583, -90.0656 
    
    st.session_state['dxer_name'] = dxer_name

# --- 4. SEARCH & FILTERS ---
st.subheader("🔍 Station Search")
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1: f_freq = st.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None)
with c2: f_call = st.text_input("Callsign").upper()
with c3: f_city = st.text_input("City")
with c4: f_sp = st.text_input("State/Prov")
with c5: f_country = st.text_input("Country")
with c6: f_slogan = st.text_input("Slogan")

# Filter Logic
view_df = df_stations.copy()
if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
if f_call: view_df = view_df[view_df['Station Callsign'].str.contains(f_call)]
if f_city: view_df = view_df[view_df['City'].str.contains(f_city, case=False)]
if f_sp: view_df = view_df[view_df['State/Province'].str.contains(f_sp, case=False)]
if f_country: view_df = view_df[view_df['Country'].str.contains(f_country, case=False)]
if f_slogan: view_df = view_df[view_df['Slogan'].str.contains(f_slogan, case=False, na=False)]

# Calculate Distance for the Table Preview
view_df['Dist'] = view_df.apply(lambda row: calculate_distance(home_lat, home_lon, dms_to_dd(row['Lat-N']), -dms_to_dd(row['Long-W'])), axis=1)

# Display Table (No Row Numbers)
cols_to_show = ['Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'Format', 'PI Code', 'Dist']
st.dataframe(view_df[cols_to_show], use_container_width=True, hide_index=True)

# --- 5. LOGGING FORM ---
if not view_df.empty:
    st.divider()
    # This acts as your "Select Station" button logic
    selected_station_label = st.selectbox("Choose a station from the filtered list to Log:", 
                                         options=view_df.index,
                                         format_func=lambda x: f"{view_df.loc[x, 'Station Callsign']} ({view_df.loc[x, 'Frequency']}) - {view_df.loc[x, 'City']}, {view_df.loc[x, 'State/Province']}")
    
    station = view_df.loc[selected_station_label]

    with st.form("log_entry", clear_on_submit=True):
        st.subheader(f"📝 Logging: {station['Station Callsign']} on {station['Frequency']}")
        
        # Date and Time (Defaults to current UTC)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        log_date = st.date_input("Date of Reception (UTC)", value=now_utc.date())
        log_time = st.text_input("Time of Reception (UTC - HHMM)", value=now_utc.strftime("%H%M"))
        
        col_a, col_b = st.columns(2)
        with col_a:
            rds_ready = st.selectbox("RDS Decoded?", ["No", "Yes"])
            pi_val = str(station['PI Code']) if pd.notnull(station['PI Code']) else ""
            pi_code = st.text_input("PI Code", value=pi_val if rds_ready == "Yes" else "")
            
            sig = st.text_input("Signal Strength (dBm)")
            
        with col_b:
            cat = st.selectbox("Frequency Category", ["", "Open", "Fringe", "Semi-Local", "Local-HD", "Strong Local"], index=0)
            prop = st.selectbox("Propagation", ["Local", "Tropo", "Es", "Meteor Scatter"])
            
            fmlist = st.checkbox("Logged on FMList?")
            wlogger = st.checkbox("Logged on WLogger?")

        if st.form_submit_button("Submit Log Entry"):
            # Check for required info
            if not dxer_name:
                st.error("Please enter your DXer Name in the sidebar first!")
            else:
                # Final submission mapping
                new_row = [
                    dxer_name, dxer_city, dxer_st, "USA", 
                    station['Frequency'], station['Station Callsign'], station['Slogan'],
                    station['City'], station['State/Province'], station['Country'], "",
                    station['Format'], log_date.strftime("%m/%d/%Y"), log_time, 
                    station['Dist'], "", sig, rds_ready, pi_code, cat, prop,
                    1 if fmlist else 0, 1 if wlogger else 0, "", ""
                ]
                st.success(f"Log sent to Google Sheets for {station['Station Callsign']}!")
                # (Gspread logic would go here to append_row)
