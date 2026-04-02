import streamlit as st
import pandas as pd
import numpy as np
import math
import datetime
import json
import gspread
import maidenhead as mh
from google.oauth2.service_account import Credentials
from streamlit_javascript import st_javascript
from geopy.geocoders import Nominatim

# --- 1. CONFIG & DATA LOADING ---
STATION_DATA = "FM Challenge - Station List and Data - WTFDA Data.csv"
CATEGORY_DATA = "Frequency Categories - Sheet1.csv"

@st.cache_data
def load_stations():
    df = pd.csv_read(STATION_DATA, dtype=str)
    def scrub_pi(val):
        if pd.isna(val) or val == 'nan' or val == '': return ""
        try:
            float_val = float(val)
            if float_val > 65535: return "" 
            return '{:.0f}'.format(float_val)
        except: return str(val).strip()
    df['PI Code'] = df['PI Code'].apply(scrub_pi)
    df['Frequency'] = pd.to_numeric(df['Frequency'], errors='coerce')
    df['Station Callsign'] = df['Callsign'].str.replace(r'-FM$', '', regex=True)
    df = df.rename(columns={'S/P': 'State/Province'})
    df['State/Province'] = df['State/Province'].fillna("Unknown")
    df['Country'] = df['Country'].fillna("Unknown")
    return df

@st.cache_data
def load_categories():
    df = pd.read_csv(CATEGORY_DATA)
    df['Display'] = df['Category'] + " - " + df['Definitions']
    return df

def get_logged_stations_set():
    try:
        sheet = get_gsheet()
        vals = sheet.get_all_values()
        if len(vals) < 2: return set()
        return set(str(row[5]).strip() + "-" + str(row[4]).strip() for row in vals[1:])
    except: return set()

# --- 2. HELPERS ---
def dms_to_dd(dms_str):
    if pd.isna(dms_str) or not isinstance(dms_str, str): return None
    try:
        parts = dms_str.split('-')
        if len(parts) != 3: return None
        return float(parts[0]) + (float(parts[1]) / 60) + (float(parts[2]) / 3600)
    except: return None

def calculate_distance(lat1, lon1, lat2, lon2):
    # Safety check for None or 0 values
    if any(v is None for v in [lat1, lon1, lat2, lon2]): return 0
    if lat1 == 0 and lon1 == 0: return 0
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

def reverse_geocode(lat, lon):
    """Updates sidebar text inputs based on coordinates"""
    try:
        geolocator = Nominatim(user_agent="dx_central_logger_v2")
        location = geolocator.reverse(f"{lat}, {lon}", language='en')
        if location:
            address = location.raw.get('address', {})
            # Update session state keys linked to text inputs
            st.session_state.dx_city = address.get('city', address.get('town', address.get('village', '')))
            st.session_state.dx_st = address.get('state', address.get('province', ''))
            st.session_state.dx_ctry = address.get('country', 'USA')
    except:
        pass

# --- 3. UI SETUP ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()
df_categories = load_categories()
logged_stations = get_logged_stations_set()

# --- 4. SIDEBAR WITH REVERSE GEOCODING ---
with st.sidebar:
    st.header("📍 DXer Profile")
    js_code = "JSON.parse(localStorage.getItem('dx_central_profile'));"
    saved_data = st_javascript(js_code)
    
    # Initialize session state for all profile fields
    if 'dx_name' not in st.session_state:
        if isinstance(saved_data, dict):
            st.session_state.dx_name = saved_data.get("name", "")
            st.session_state.dx_city = saved_data.get("city", "")
            st.session_state.dx_st = saved_data.get("st", "")
            st.session_state.dx_ctry = saved_data.get("ctry", "USA")
            st.session_state.home_lat = float(saved_data.get("lat", 0.0))
            st.session_state.home_lon = float(saved_data.get("lon", 0.0))
        else:
            st.session_state.dx_name = ""
            st.session_state.dx_city = ""
            st.session_state.dx_st = ""
            st.session_state.dx_ctry = "USA"
            st.session_state.home_lat = 0.0
            st.session_state.home_lon = 0.0

    dxer_name = st.text_input("Your Name", key="dx_name")
    col_c, col_s = st.columns([2, 1])
    dxer_city = col_c.text_input("City", key="dx_city")
    dxer_st = col_s.text_input("ST/Prov", key="dx_st")
    dxer_ctry = st.text_input("Country", key="dx_ctry")

    st.divider()
    st.subheader("🛰️ Set Location")
    loc_method = st.radio("Method", ["Grid Square", "City Search", "Manual Lat/Lon"], horizontal=True)
    
    if loc_method == "Grid Square":
        grid = st.text_input("Enter Grid Square (e.g. EM40xi)", placeholder="XX##xx")
        if grid:
            try:
                lat, lon = mh.toLoc(grid)
                st.session_state.home_lat, st.session_state.home_lon = lat, lon
                reverse_geocode(lat, lon) # AUTO-POPULATE CITY/ST
                st.success(f"Grid Set: {lat:.4f}, {lon:.4f}")
            except: st.error("Invalid Grid Square")

    elif loc_method == "City Search":
        search_query = st.text_input("Enter City & State/Country", placeholder="e.g. Mandeville, LA")
        if st.button("Lookup Location"):
            geolocator = Nominatim(user_agent="dx_central_logger_v2")
            location = geolocator.geocode(search_query)
            if location:
                st.session_state.home_lat, st.session_state.home_lon = location.latitude, location.longitude
                reverse_geocode(location.latitude, location.longitude) # AUTO-POPULATE CITY/ST
                st.success(f"Found: {location.latitude:.4f}, {location.longitude:.4f}")
            else: st.error("Location not found.")

    # Always show/allow manual override
    st.session_state.home_lat = st.number_input("Latitude", value=st.session_state.home_lat, format="%.4f")
    st.session_state.home_lon = st.number_input("Longitude", value=st.session_state.home_lon, format="%.4f")

    if st.button("💾 Remember Me on this Browser"):
        profile = {
            "name": st.session_state.dx_name, "city": st.session_state.dx_city, 
            "st": st.session_state.dx_st, "ctry": st.session_state.dx_ctry, 
            "lat": st.session_state.home_lat, "lon": st.session_state.home_lon
        }
        st_javascript(f"localStorage.setItem('dx_central_profile', JSON.stringify({json.dumps(profile)}));")
        st.success("Profile & Location Saved!")

    st.divider()
    if st.button("🔄 Clear Data Cache"):
        st.cache_data.clear()
        st.rerun()

# --- 5. SEARCH & FILTERS ---
st.subheader("🔍 Station Search")
if 'filter_key' not in st.session_state: st.session_state.filter_key = 0
def reset_all(): st.session_state.filter_key += 1

state_options = sorted(df_stations['State/Province'].unique().tolist())
country_options = sorted(df_stations['Country'].unique().tolist())

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
f_freq = c1.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None, key=f"freq_{st.session_state.filter_key}")
f_call = c2.text_input("Callsign", key=f"call_{st.session_state.filter_key}").upper()
f_city = c3.text_input("City", key=f"city_{st.session_state.filter_key}")
f_sp = c4.selectbox("State/Province", state_options, index=None, key=f"sp_{st.session_state.filter_key}")
f_country = c5.selectbox("Country", country_options, index=None, key=f"ctry_{st.session_state.filter_key}")
f_slogan = c6.text_input("Slogan", key=f"slogan_{st.session_state.filter_key}")
f_status = c7.selectbox("Logging Status", ["All", "Logged Only", "Not Logged Only"], index=0, key=f"status_{st.session_state.filter_key}")

_, center_col, _ = st.columns([2, 1, 2])
center_col.button("Clear All Filters", on_click=reset_all, use_container_width=True)

# --- 6. FILTER LOGIC & TABLE ---
view_df = df_stations.copy()

def row_dist_safe(row):
    lat_dest = dms_to_dd(row['Lat-N'])
    lon_dest = dms_to_dd(row['Long-W'])
    if lat_dest is None or lon_dest is None: return 0
    return calculate_distance(st.session_state.home_lat, st.session_state.home_lon, lat_dest, -lon_dest)

view_df['Dist'] = view_df.apply(row_dist_safe, axis=1)
view_df['Already Logged'] = view_df.apply(lambda r: f"{str(r['Station Callsign']).strip()}-{str(r['Frequency']).strip()}" in logged_stations, axis=1)

if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
if f_call: view_df = view_df[view_df['Station Callsign'].str.contains(f_call, na=False)]
if f_city: view_df = view_df[view_df['City'].str.contains(f_city, case=False, na=False)]
if f_sp: view_df = view_df[view_df['State/Province'] == f_sp]
if f_country: view_df = view_df[view_df['Country'] == f_country]
if f_slogan: view_df = view_df[view_df['Slogan'].str.contains(f_slogan, case=False, na=False)]
if f_status == "Logged Only": view_df = view_df[view_df['Already Logged'] == True]
elif f_status == "Not Logged Only": view_df = view_df[view_df['Already Logged'] == False]

view_df['Display Callsign'] = view_df.apply(lambda r: f"🟢 {r['Station Callsign']}" if r['Already Logged'] else r['Station Callsign'], axis=1)
st.write(f"Showing {len(view_df)} stations:")
view_df.insert(0, 'Select', False)

edited_df = st.data_editor(
    view_df[['Select', 'Frequency', 'Display Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist']],
    use_container_width=True, hide_index=True,
    column_config={
        "Select": st.column_config.CheckboxColumn("Log?", default=False),
        "Display Callsign": st.column_config.TextColumn("Station Callsign"),
        "Frequency": st.column_config.NumberColumn(format="%.1f")
    },
    disabled=['Frequency', 'Display Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist'],
    key=f"editor_{st.session_state.filter_key}"
)

# --- 7. LOGGING FORM ---
editor_state = st.session_state.get(f"editor_{st.session_state.filter_key}")
selected_indices = []
if editor_state and "edited_rows" in editor_state:
    for idx, changes in editor_state["edited_rows"].items():
        if changes.get("Select"): selected_indices.append(idx)

if selected_indices:
    selected_idx = view_df.index[selected_indices[0]]
    station = view_df.loc[selected_idx]
    st.divider()
    if station['Already Logged']: st.error(f"⚠️ **Duplicate Alert:** {station['Station Callsign']} on {station['Frequency']} has already been logged.")
    with st.form("log_entry", clear_on_submit=True):
        st.subheader(f"📝 Log: {station['Station Callsign']} ({station['Frequency']})")
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        c_date, c_time = st.columns(2)
        log_date = c_date.date_input("Date (UTC)", value=now_utc.date())
        log_time = c_time.text_input("Time (UTC - HHMM)", value=now_utc.strftime("%H%M"))
        col_a, col_b = st.columns(2)
        with col_a:
            rds_ready = st.selectbox("RDS Decoded?", ["No", "Yes"])
            pi_code = st.text_input("PI Code", value=str(station['PI Code']) if rds_ready == "Yes" else "")
            sig = st.text_input("Signal Strength (dBm)")
        with col_b:
            cat_list = [""] + df_categories['Display'].tolist()
            cat_display = st.selectbox("Frequency Category & Definition", cat_list, index=0)
            final_cat = cat_display.split(" - ")[0] if cat_display else ""
            prop = st.selectbox("Propagation", ["Local", "Tropo", "Es", "Meteor Scatter"])
            fmlist, wlogger = st.checkbox("Logged on FMList?"), st.checkbox("Logged on WLogger?")
        if st.form_submit_button("Submit Log Entry"):
            if not st.session_state.dx_name: st.error("Please enter your name in the sidebar!")
            elif st.session_state.home_lat == 0: st.error("Please set your location in the sidebar to calculate distance!")
            else:
                try:
                    new_row = [
                        st.session_state.dx_name, st.session_state.dx_city, st.session_state.dx_st, st.session_state.dx_ctry, 
                        station['Frequency'], station['Station Callsign'], station['Slogan'],
                        station['City'], station['State/Province'], station['Country'], "",
                        station['Format'], log_date.strftime("%m/%d/%Y"), log_time, 
                        station['Dist'], "", sig, rds_ready, pi_code, final_cat, prop,
                        1 if fmlist else 0, 1 if wlogger else 0, 0, f"{st.session_state.dx_name}{station['Frequency']}{station['Station Callsign']}"
                    ]
                    sheet = get_gsheet()
                    sheet.append_row(new_row)
                    st.success(f"Log recorded!")
                    st.balloons()
                    st.rerun()
                except Exception as e: st.error(f"GSheet Error: {e}")
