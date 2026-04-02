import streamlit as st
import pandas as pd
import numpy as np
import math
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from streamlit_javascript import st_javascript

# --- 1. CONFIG & DATA LOADING ---
STATION_DATA = "FM Challenge - Station List and Data - WTFDA Data.csv"
CATEGORY_DATA = "Frequency Categories - Sheet1.csv"

@st.cache_data
def load_stations():
    # AGGRESSIVE FIX: Force PI Code to be read as a string immediately
    df = pd.read_csv(STATION_DATA, dtype={'PI Code': str})
    
    # Clean Callsign: Strip -FM
    df['Station Callsign'] = df['Callsign'].str.replace(r'-FM$', '', regex=True)
    
    # CLEAN PI CODE: Remove 'nan' and ensure no '.0' decimal points appear
    df['PI Code'] = df['PI Code'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True)
    
    df = df.rename(columns={'S/P': 'State/Province'})
    df['State/Province'] = df['State/Province'].fillna("Unknown")
    df['Country'] = df['Country'].fillna("Unknown")
    return df

@st.cache_data
def load_categories():
    df = pd.read_csv(CATEGORY_DATA)
    # Combine Category + Definition for the dropdown
    df['Display'] = df['Category'] + " - " + df['Definitions']
    return df

# --- 2. HELPERS: DISTANCE & LOCAL STORAGE ---
def dms_to_dd(dms_str):
    if pd.isna(dms_str) or not isinstance(dms_str, str): return None
    try:
        parts = dms_str.split('-')
        if len(parts) != 3: return None
        return float(parts[0]) + (float(parts[1]) / 60) + (float(parts[2]) / 3600)
    except: return None

def calculate_distance(lat1, lon1, lat2, lon2):
    if any(v is None for v in [lat1, lon1, lat2, lon2]): return 0
    R = 3958.8 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a)), 1)

def get_gsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1

# --- 3. UI SETUP ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()
df_categories = load_categories()

# --- 4. SIDEBAR WITH LOCAL STORAGE ---
with st.sidebar:
    st.header("📍 DXer Profile")
    js_code = "JSON.parse(localStorage.getItem('dx_central_profile'));"
    saved_data = st_javascript(js_code)
    
    s_name = saved_data.get("name", "") if isinstance(saved_data, dict) else ""
    s_city = saved_data.get("city", "Mandeville") if isinstance(saved_data, dict) else "Mandeville"
    s_st = saved_data.get("st", "LA") if isinstance(saved_data, dict) else "LA"
    s_lat = saved_data.get("lat", 30.3583) if isinstance(saved_data, dict) else 30.3583
    s_lon = saved_data.get("lon", -90.0656) if isinstance(saved_data, dict) else -90.0656

    dxer_name = st.text_input("Your Name", value=s_name)
    col_c, col_s = st.columns([2, 1])
    dxer_city = col_c.text_input("City", value=s_city)
    dxer_st = col_s.text_input("ST", value=s_st)

    st.divider()
    st.write("Coordinates (for Distance Math):")
    home_lat = st.number_input("Latitude", value=float(s_lat), format="%.4f")
    home_lon = st.number_input("Longitude", value=float(s_lon), format="%.4f")

    if st.button("💾 Remember Me on this Browser"):
        profile = {"name": dxer_name, "city": dxer_city, "st": dxer_st, "lat": home_lat, "lon": home_lon}
        st_javascript(f"localStorage.setItem('dx_central_profile', JSON.stringify({json.dumps(profile)}));")
        st.success("Preferences saved to browser!")

# --- 5. SEARCH & FILTERS ---
st.subheader("🔍 Station Search")

if 'filter_key' not in st.session_state:
    st.session_state.filter_key = 0

def reset_all():
    st.session_state.filter_key += 1
    st.rerun()

state_options = sorted(df_stations['State/Province'].unique().tolist())
country_options = sorted(df_stations['Country'].unique().tolist())

c1, c2, c3, c4, c5, c6 = st.columns(6)
f_freq = c1.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None, key=f"freq_{st.session_state.filter_key}")
f_call = c2.text_input("Callsign", key=f"call_{st.session_state.filter_key}").upper()
f_city = c3.text_input("City", key=f"city_{st.session_state.filter_key}")
f_sp = c4.selectbox("State/Province", state_options, index=None, key=f"sp_{st.session_state.filter_key}")
f_country = c5.selectbox("Country", country_options, index=None, key=f"ctry_{st.session_state.filter_key}")
f_slogan = c6.text_input("Slogan", key=f"slogan_{st.session_state.filter_key}")

_, center_col, _ = st.columns([2, 1, 2])
center_col.button("Clear All Filters", on_click=reset_all, use_container_width=True)

# --- 6. FILTER LOGIC & TABLE ---
view_df = df_stations.copy()
if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
if f_call: view_df = view_df[view_df['Station Callsign'].str.contains(f_call, na=False)]
if f_city: view_df = view_df[view_df['City'].str.contains(f_city, case=False, na=False)]
if f_sp: view_df = view_df[view_df['State/Province'] == f_sp]
if f_country: view_df = view_df[view_df['Country'] == f_country]
if f_slogan: view_df = view_df[view_df['Slogan'].str.contains(f_slogan, case=False, na=False)]

def get_row_dist(row):
    lat_val, lon_val = dms_to_dd(row['Lat-N']), dms_to_dd(row['Long-W'])
    return calculate_distance(home_lat, home_lon, lat_val, -lon_val) if lat_val and lon_val else 0

view_df['Dist'] = view_df.apply(get_row_dist, axis=1)

st.write(f"Showing {len(view_df)} stations:")
view_df.insert(0, 'Select', False)

# Aggressive formatting in the table itself
edited_df = st.data_editor(
    view_df[['Select', 'Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist']],
    use_container_width=True, hide_index=True,
    column_config={
        "Select": st.column_config.CheckboxColumn("Log?", default=False),
        "PI Code": st.column_config.TextColumn("PI Code"), # Explicitly set as Text
        "Frequency": st.column_config.NumberColumn(format="%.1f")
    },
    disabled=['Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist'],
    key=f"editor_{st.session_state.filter_key}"
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
            # Force the form to show PI Code as plain text
            pi_code = st.text_input("PI Code", value=str(station['PI Code']) if rds_ready == "Yes" else "")
            sig = st.text_input("Signal Strength (dBm)")
        with col_b:
            cat_list = [""] + df_categories['Display'].tolist()
            cat_display = st.selectbox("Frequency Category & Definition", cat_list, index=0)
            final_cat = cat_display.split(" - ")[0] if cat_display else ""

            prop = st.selectbox("Propagation", ["Local", "Tropo", "Es", "Meteor Scatter"])
            fmlist = st.checkbox("Logged on FMList?")
            wlogger = st.checkbox("Logged on WLogger?")

        if st.form_submit_button("Submit Log Entry"):
            if not dxer_name:
                st.error("Please enter your name in the sidebar!")
            else:
                try:
                    new_row = [
                        dxer_name, dxer_city, dxer_st, "USA", 
                        station['Frequency'], station['Station Callsign'], station['Slogan'],
                        station['City'], station['State/Province'], station['Country'], "",
                        station['Format'], log_date.strftime("%m/%d/%Y"), log_time, 
                        station['Dist'], "", sig, rds_ready, pi_code, final_cat, prop,
                        1 if fmlist else 0, 1 if wlogger else 0, 0, f"{dxer_name}{station['Frequency']}{station['Station Callsign']}"
                    ]
                    sheet = get_gsheet()
                    sheet.append_row(new_row)
                    st.success(f"Log recorded for {station['Station Callsign']}!")
                    st.balloons()
                except Exception as e:
                    st.error(f"GSheet Error: {e}")
