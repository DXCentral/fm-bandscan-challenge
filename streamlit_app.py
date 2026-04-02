import streamlit as st
import pandas as pd
import numpy as np
import math
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIG & DATA LOADING ---
STATION_DATA = "FM Challenge - Station List and Data - WTFDA Data.csv"

@st.cache_data
def load_stations():
    df = pd.read_csv(STATION_DATA)
    # Clean Callsign: Strip -FM, keep -LP/-LD
    df['Callsign_Clean'] = df['Callsign'].str.replace(r'-FM$', '', regex=True)
    return df

# --- 2. THE DISTANCE ENGINE ---
def dms_to_dd(dms_str):
    """Convert 42-57-21 to 42.9558"""
    try:
        parts = dms_str.split('-')
        degrees = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        return degrees + (minutes / 60) + (seconds / 3600)
    except:
        return None

def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula for Great Circle distance"""
    if None in [lat1, lon1, lat2, lon2]: return 0
    R = 3958.8 # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a)), 1)

# --- 3. GOOGLE SHEETS CONNECTION ---
def get_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    # Pulls credentials from your Streamlit Secrets
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1

# --- 4. UI SETUP ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()

# Sidebar for DXer Info
with st.sidebar:
    st.title("Settings")
    dxer_name = st.text_input("DXer Name", value=st.session_state.get('dxer_name', ""))
    dxer_city = st.text_input("Your City", value=st.session_state.get('dxer_city', "Mandeville"))
    dxer_st = st.text_input("Your State", value=st.session_state.get('dxer_st', "LA"))
    # (Optional) Hardcode coordinates for Mandeville for now
    home_lat, home_lon = 30.3583, -90.0656 
    
    st.session_state['dxer_name'] = dxer_name
    st.session_state['dxer_city'] = dxer_city
    st.session_state['dxer_st'] = dxer_st

# --- 5. MAIN INTERFACE ---
tab1, tab2 = st.tabs(["Search & Log", "Manual Entry"])

with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        f_freq = st.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None)
        f_call = st.text_input("Search Callsign").upper()
        
    # Filter Logic
    view_df = df_stations.copy()
    if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
    if f_call: view_df = view_df[view_df['Callsign_Clean'].str.contains(f_call)]
    
    st.dataframe(view_df[['Frequency', 'Callsign_Clean', 'City', 'S/P', 'Format', 'Slogan']], use_container_width=True)

    # Log Selection
    if not view_df.empty:
        selected_idx = st.selectbox("Select station to log:", view_df.index, 
                                    format_func=lambda x: f"{view_df.loc[x, 'Callsign_Clean']} ({view_df.loc[x, 'Frequency']})")
        
        station = view_df.loc[selected_idx]
        
        with st.form("log_entry"):
            st.subheader(f"Logging {station['Callsign_Clean']}")
            
            # RDS Section
            rds_ready = st.selectbox("RDS Decoded?", ["No", "Yes"])
            pi_code = ""
            if rds_ready == "Yes":
                default_pi = str(station['PI Code']) if pd.notnull(station['PI Code']) else ""
                pi_code = st.text_input("PI Code", value=default_pi)
            
            # Additional Fields
            sig = st.text_input("Signal Strength (dBm)")
            cat = st.selectbox("Frequency Category", ["Open", "Fringe", "Semi-Local", "Local-HD", "Strong Local"])
            prop = st.selectbox("Propagation", ["Local", "Tropo", "Es", "Meteor Scatter"])
            
            # Bonus
            fmlist = st.checkbox("Logged on FMList?")
            wlogger = st.checkbox("Logged on WLogger?")
            
            if st.form_submit_button("Submit Log Entry"):
                # Calculate Distance on the Fly
                s_lat = dms_to_dd(station['Lat-N'])
                s_lon = -dms_to_dd(station['Long-W']) # Negative for West
                dist = calculate_distance(home_lat, home_lon, s_lat, s_lon)
                
                # Prep Data for GSheet (Mapping your columns)
                new_row = [
                    dxer_name, dxer_city, dxer_st, "USA", 
                    station['Frequency'], station['Callsign_Clean'], station['Slogan'],
                    station['City'], station['S/P'], station['Country'], "",
                    station['Format'], datetime.date.today().strftime("%m/%d/%Y"),
                    datetime.datetime.utcnow().strftime("%H%M"), dist,
                    "", sig, rds_ready, pi_code, cat, prop,
                    1 if fmlist else 0, 1 if wlogger else 0, "", ""
                ]
                
                try:
                    sheet = get_gsheet()
                    sheet.append_row(new_row)
                    st.success("Log Recorded! Standings will update shortly.")
                except Exception as e:
                    st.error(f"Error: {e}")
