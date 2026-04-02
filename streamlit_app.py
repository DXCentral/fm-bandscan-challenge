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
    df = pd.read_csv(STATION_DATA, dtype=str)
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
    try:
        geolocator = Nominatim(user_agent="dx_central_logger_v10")
        location = geolocator.reverse(f"{lat}, {lon}", language='en')
        if location:
            addr = location.raw.get('address', {})
            city_tags = ['city', 'town', 'village', 'hamlet', 'suburb', 'municipality']
            found_city = ""
            for tag in city_tags:
                if tag in addr:
                    found_city = addr[tag]
                    break
            
            # Explicitly set session state
            st.session_state.dx_city = found_city
            st.session_state.dx_st = addr.get('state', addr.get('province', ''))
            st.session_state.dx_ctry = addr.get('country', 'USA')
    except: pass

def update_from_grid():
    grid = st.session_state.grid_input.strip()
    if len(grid) >= 4:
        try:
            lat, lon = mh.to_location(grid)
            st.session_state.home_lat, st.session_state.home_lon = lat, lon
            reverse_geocode(lat, lon)
        except: pass

def update_from_search():
    query = st.session_state.search_query.strip()
    if query:
        try:
            geolocator = Nominatim(user_agent="dx_central_logger_v10")
            loc = geolocator.geocode(query)
            if loc:
                st.session_state.home_lat, st.session_state.home_lon = loc.latitude, loc.longitude
                reverse_geocode(loc.latitude, loc.longitude)
        except: pass

# --- 3. UI SETUP ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()
df_categories = load_categories()
logged_stations = get_logged_stations_set()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("📍 DXer Profile")
    js_code = "JSON.parse(localStorage.getItem('dx_central_profile'));"
    saved_data = st_javascript(js_code)
    
    if 'dx_name' not in st.session_state:
        if isinstance(saved_data, dict):
            st.session_state.dx_name = saved_data.get("name", "")
            st.session_state.dx_city = saved_data.get("city", "")
            st.session_state.dx_st = saved_data.get("st", "")
            st.session_state.dx_ctry = saved_data.get("ctry", "USA")
            st.session_state.home_lat = float(saved_data.get("lat", 0.0))
            st.session_state.home_lon = float(saved_data.get("lon", 0.0))
        else:
            st.session_state.dx_name, st.session_state.dx_city, st.session_state.dx_st = "", "", ""
            st.session_state.dx_ctry, st.session_state.home_lat, st.session_state.home_lon = "USA", 0.0, 0.0

    # UI LOCK: We use 'value' parameter to force the display to match session state
    st.text_input("Your Name", value=st.session_state.dx_name, key="dx_name_box", on_change=lambda: st.session_state.update(dx_name=st.session_state.dx_name_box))
    
    col_c, col_s = st.columns([2, 1])
    col_c.text_input("City", value=st.session_state.dx_city, key="dx_city_box", on_change=lambda: st.session_state.update(dx_city=st.session_state.dx_city_box))
    col_s.text_input("ST/Prov", value=st.session_state.dx_st, key="dx_st_box", on_change=lambda: st.session_state.update(dx_st=st.session_state.dx_st_box))
    st.text_input("Country", value=st.session_state.dx_ctry, key="dx_ctry_box", on_change=lambda: st.session_state.update(dx_ctry=st.session_state.dx_ctry_box))

    st.divider()
    st.subheader("🛰️ Set Location")
    loc_method = st.radio("Method", ["Grid Square", "City Search", "Manual Lat/Lon"], horizontal=True)
    
    if loc_method == "Grid Square":
        st.text_input("Enter Grid (e.g. EM40xi)", key="grid_input", on_change=update_from_grid, placeholder="XX##xx")
        if st.session_state.home_lat != 0:
            st.success(f"Coordinates: {st.session_state.home_lat:.4f}, {st.session_state.home_lon:.4f}")

    elif loc_method == "City Search":
        st.text_input("Enter City & State", key="search_query", placeholder="e.g. Mandeville, LA")
        st.button("Lookup Location", on_click=update_from_search)

    st.number_input("Latitude", value=st.session_state.home_lat, key="home_lat_box", format="%.4f", on_change=lambda: st.session_state.update(home_lat=st.session_state.home_lat_box))
    st.number_input("Longitude", value=st.session_state.home_lon, key="home_lon_box", format="%.4f", on_change=lambda: st.session_state.update(home_lon=st.session_state.home_lon_box))

    if st.button("💾 Remember Me on this Browser"):
        prof = {
            "name": st.session_state.dx_name, "city": st.session_state.dx_city, 
            "st": st.session_state.dx_st, "ctry": st.session_state.dx_ctry, 
            "lat": st.session_state.home_lat, "lon": st.session_state.home_lon
        }
        st_javascript(f"localStorage.setItem('dx_central_profile', JSON.stringify({json.dumps(prof)}));")
        st.success("Profile Saved!")

# --- 5. SEARCH & FILTERS ---
st.subheader("🔍 Station Search")
if 'filter_key' not in st.session_state: st.session_state.filter_key = 0
def reset_all(): st.session_state.filter_key += 1

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
f_freq = c1.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None, key=f"f1_{st.session_state.filter_key}")
f_call = c2.text_input("Callsign", key=f"f2_{st.session_state.filter_key}").upper()
f_city = c3.text_input("City", key=f"f3_{st.session_state.filter_key}")
f_sp = c4.selectbox("State/Prov", sorted(df_stations['State/Province'].unique().tolist()), index=None, key=f"f4_{st.session_state.filter_key}")
f_country = c5.selectbox("Country", sorted(df_stations['Country'].unique().tolist()), index=None, key=f"f5_{st.session_state.filter_key}")
f_slogan = c6.text_input("Slogan", key=f"f6_{st.session_state.filter_key}")
f_status = c7.selectbox("Status", ["All", "Logged Only", "Not Logged Only"], index=0, key=f"f7_{st.session_state.filter_key}")

st.button("Clear All Filters", on_click=reset_all)

# --- 6. FILTER LOGIC & TABLE ---
view_df = df_stations.copy()
def safe_dist(r):
    lat_d, lon_d = dms_to_dd(r['Lat-N']), dms_to_dd(r['Long-W'])
    return calculate_distance(st.session_state.home_lat, st.session_state.home_lon, lat_d, -lon_d) if lat_d else 0

view_df['Dist'] = view_df.apply(safe_dist, axis=1)
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
view_df.insert(0, 'Select', False)

edited_df = st.data_editor(
    view_df[['Select', 'Frequency', 'Display Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist']],
    use_container_width=True, hide_index=True,
    column_config={"Select": st.column_config.CheckboxColumn("Log?"), "Frequency": st.column_config.NumberColumn(format="%.1f")},
    disabled=['Frequency', 'Display Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Dist'],
    key=f"ed_{st.session_state.filter_key}"
)

# --- 7. LOGGING FORM ---
ed_state = st.session_state.get(f"ed_{st.session_state.filter_key}")
if ed_state and "edited_rows" in ed_state:
    selected_idx = next((idx for idx, chg in ed_state["edited_rows"].items() if chg.get("Select")), None)
    if selected_idx is not None:
        station = view_df.iloc[selected_idx]
        st.divider()
        if station['Already Logged']: st.error(f"⚠️ **Duplicate Alert:** Already logged {station['Station Callsign']}")
        with st.form("log_entry", clear_on_submit=True):
            st.subheader(f"📝 Log: {station['Station Callsign']}")
            now = datetime.datetime.now(datetime.timezone.utc)
            c1, c2 = st.columns(2)
            l_date = c1.date_input("Date (UTC)", value=now.date())
            l_time = c2.text_input("Time (UTC)", value=now.strftime("%H%M"))
            ca, cb = st.columns(2)
            with ca:
                rds = st.selectbox("RDS?", ["No", "Yes"])
                pi = st.text_input("PI Code", value=str(station['PI Code']) if rds == "Yes" else "")
                sig = st.text_input("Signal (dBm)")
            with cb:
                cats = [""] + df_categories['Display'].tolist()
                cat_d = st.selectbox("Category", cats)
                final_cat = cat_d.split(" - ")[0] if cat_d else ""
                prop = st.selectbox("Prop", ["Local", "Tropo", "Es", "MS"])
                fml, wlo = st.checkbox("FMList?"), st.checkbox("WLogger?")
            if st.form_submit_button("Submit"):
                if not st.session_state.dx_name or st.session_state.home_lat == 0: st.error("Complete sidebar profile first!")
                else:
                    try:
                        row = [st.session_state.dx_name, st.session_state.dx_city, st.session_state.dx_st, st.session_state.dx_ctry, station['Frequency'], station['Station Callsign'], station['Slogan'], station['City'], station['State/Province'], station['Country'], "", station['Format'], l_date.strftime("%m/%d/%Y"), l_time, station['Dist'], "", sig, rds, pi, final_cat, prop, 1 if fml else 0, 1 if wlo else 0, 0, f"{st.session_state.dx_name}{station['Frequency']}{station['Station Callsign']}"]
                        get_gsheet().append_row(row)
                        st.success("Log recorded!"); st.balloons(); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")
