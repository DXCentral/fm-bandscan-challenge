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
    df['ERP-H'] = pd.to_numeric(df['ERP-H'], errors='coerce').fillna(0)
    df['ERP-V'] = pd.to_numeric(df['ERP-V'], errors='coerce').fillna(0)
    df['Power (kW)'] = df[['ERP-H', 'ERP-V']].max(axis=1) / 1000
    
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
        geolocator = Nominatim(user_agent="dx_central_logger_v35")
        location = geolocator.reverse(f"{lat}, {lon}", language='en')
        if location:
            addr = location.raw.get('address', {})
            city_tags = ['city', 'town', 'village', 'hamlet', 'suburb', 'municipality']
            found_city = next((addr[tag] for tag in city_tags if tag in addr), "")
            st.session_state["dx_city_val"] = found_city
            st.session_state["dx_st_val"] = addr.get('state', addr.get('province', ''))
            st.session_state["dx_ctry_val"] = addr.get('country', 'USA')
    except: pass

def update_from_grid():
    grid = st.session_state.grid_input.strip()
    if len(grid) >= 4:
        try:
            lat, lon = mh.to_location(grid)
            st.session_state["home_lat_val"] = float(lat)
            st.session_state["home_lon_val"] = float(lon)
            reverse_geocode(lat, lon)
        except: pass

def update_from_search():
    query = st.session_state.search_query.strip()
    if query:
        try:
            geolocator = Nominatim(user_agent="dx_central_logger_v35")
            loc = geolocator.geocode(query)
            if loc:
                st.session_state["home_lat_val"] = float(loc.latitude)
                st.session_state["home_lon_val"] = float(loc.longitude)
                reverse_geocode(loc.latitude, loc.longitude)
        except: pass

# --- 3. UI SETUP ---
st.set_page_config(page_title="DX Central FM Logger", layout="wide")
df_stations = load_stations()
df_categories = load_categories()
logged_stations = get_logged_stations_set()

# --- 4. SIDEBAR (STATIONARY SYNC) ---
with st.sidebar:
    # A. FETCH DATA
    js_get = "JSON.parse(localStorage.getItem('dx_central_profile'));"
    saved_data = st_javascript(js_get)
    
    # B. ROBUST INITIALIZATION
    # We only apply saved data IF session hasn't been initialized and data exists
    if saved_data and not st.session_state.get('initialized'):
        st.session_state.dx_name_val = saved_data.get("name", "")
        st.session_state.dx_city_val = saved_data.get("city", "")
        st.session_state.dx_st_val = saved_data.get("st", "")
        st.session_state.dx_ctry_val = saved_data.get("ctry", "USA")
        st.session_state.home_lat_val = float(saved_data.get("lat", 0.0))
        st.session_state.home_lon_val = float(saved_data.get("lon", 0.0))
        st.session_state.initialized = True

    # Fallback for brand new sessions
    if 'dx_name_val' not in st.session_state:
        st.session_state.dx_name_val, st.session_state.dx_city_val, st.session_state.dx_st_val = "", "", ""
        st.session_state.dx_ctry_val, st.session_state.home_lat_val, st.session_state.home_lon_val = "USA", 0.0, 0.0

    st.header("🛰️ 1. Set Your Location")
    loc_method = st.radio("Method", ["Grid Square", "City Search", "Manual Lat/Lon"], horizontal=True)
    if loc_method == "Grid Square":
        st.text_input("Enter Grid (e.g. EM40xi)", key="grid_input", on_change=update_from_grid, placeholder="XX##xx")
    elif loc_method == "City Search":
        st.text_input("Enter City & State", key="search_query", placeholder="e.g. Mandeville, LA")
        st.button("Lookup Location", on_click=update_from_search)
    st.number_input("Latitude", key="home_lat_val", format="%.4f")
    st.number_input("Longitude", key="home_lon_val", format="%.4f")

    st.divider()
    st.header("👤 2. DXer Profile")
    st.text_input("Your Name", key="dx_name_val")
    col_c, col_s = st.columns([2, 1])
    col_c.text_input("City", key="dx_city_val")
    col_s.text_input("ST/Prov", key="dx_st_val")
    st.text_input("Country", key="dx_ctry_val")

    if st.button("💾 Remember Me on this Browser"):
        prof = {
            "name": st.session_state.dx_name_val, "city": st.session_state.dx_city_val, 
            "st": st.session_state.dx_st_val, "ctry": st.session_state.dx_ctry_val, 
            "lat": st.session_state.home_lat_val, "lon": st.session_state.home_lon_val
        }
        js_set = f"localStorage.setItem('dx_central_profile', JSON.stringify({json.dumps(prof)}));"
        st_javascript(js_set)
        st.session_state.initialized = True
        st.success("Profile Saved!")

    st.divider()
    with st.expander("📄 Privacy & Data Info"):
        st.caption("Profile data is stored locally in your browser. Logs are public.")

    if st.button("🔄 Clear Data Cache"):
        st.cache_data.clear()
        st.rerun()

# --- 5. SEARCH & FILTERS ---
st.subheader("🔍 Station Search")
st.caption("Station data is sourced from WTFDA [db.wtfda.org](https://db.wtfda.org/)")

if 'filter_key' not in st.session_state: st.session_state.filter_key = 0
def reset_all(): st.session_state.filter_key += 1

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
f_country = c5.selectbox("Country", sorted(df_stations['Country'].unique().tolist()), index=None, key=f"f5_{st.session_state.filter_key}")
state_list = sorted(df_stations[df_stations['Country'] == f_country]['State/Province'].unique().tolist()) if f_country else sorted(df_stations['State/Province'].unique().tolist())
f_sp = c4.selectbox("State/Prov", state_list, index=None, key=f"f4_{st.session_state.filter_key}")
f_freq = c1.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None, key=f"f1_{st.session_state.filter_key}")
f_call = c2.text_input("Callsign", key=f"f2_{st.session_state.filter_key}").upper()
f_city = c3.text_input("City", key=f"f3_{st.session_state.filter_key}")
f_slogan = c6.text_input("Slogan", key=f"f6_{st.session_state.filter_key}")
f_status = c7.selectbox("Status", ["All", "Logged Only", "Not Logged Only"], index=0, key=f"f7_{st.session_state.filter_key}")

st.button("Clear All Filters", on_click=reset_all)

# --- 6. FILTER LOGIC & TABLE ---
view_df = df_stations.copy()
view_df['Dist'] = view_df.apply(lambda r: calculate_distance(st.session_state.home_lat_val, st.session_state.home_lon_val, dms_to_dd(r['Lat-N']), -dms_to_dd(r['Long-W'])), axis=1)
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
col_stats, col_export = st.columns([3, 1])
col_stats.write(f"Showing {len(view_df)} stations:")

if f_status == "Logged Only":
    csv_data = view_df.drop(columns=['Display Callsign', 'Already Logged']).to_csv(index=False).encode('utf-8')
    col_export.download_button(label="📥 Export My Logged List", data=csv_data, file_name=f"MyLogs_{datetime.datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv', use_container_width=True)

view_df.insert(0, 'Select', False)
st.data_editor(
    view_df[['Select', 'Frequency', 'Display Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Power (kW)', 'Dist']],
    use_container_width=True, hide_index=True,
    column_config={
        "Select": st.column_config.CheckboxColumn("Log?"),
        "Frequency": st.column_config.NumberColumn("Frequency", format="%.1f", alignment="center"),
        "Display Callsign": st.column_config.TextColumn("Station Callsign", alignment="center"),
        "City": st.column_config.TextColumn("City", alignment="center"),
        "State/Province": st.column_config.TextColumn("State/Province", alignment="center"),
        "Country": st.column_config.TextColumn("Country", alignment="center"),
        "Slogan": st.column_config.TextColumn("Slogan", alignment="center"),
        "PI Code": st.column_config.TextColumn("PI Code", alignment="center"),
        "Power (kW)": st.column_config.NumberColumn("Power (kW)", format="%.1f", alignment="center"),
        "Dist": st.column_config.NumberColumn("Dist (mi)", format="%.1f", alignment="center"),
    },
    disabled=['Frequency', 'Display Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code', 'Power (kW)', 'Dist'],
    key=f"ed_{st.session_state.filter_key}"
)

# --- 7. LOGGING FORM ---
st.divider()
manual_mode = st.toggle("🛠️ Manual Entry Mode")
ed_state = st.session_state.get(f"ed_{st.session_state.filter_key}")
selected_idx = next((idx for idx, chg in ed_state["edited_rows"].items() if chg.get("Select")), None) if ed_state and "edited_rows" in ed_state else None

if manual_mode or selected_idx is not None:
    if selected_idx is not None and not manual_mode:
        stn = view_df.iloc[selected_idx]
        def_freq, def_call, def_city, def_sp, def_ctry, def_pi, def_dist, d_check = float(stn['Frequency']), str(stn['Station Callsign']), str(stn['City']), str(stn['State/Province']), str(stn['Country']), str(stn['PI Code']), float(stn['Dist']), stn['Already Logged']
    else:
        def_freq, def_call, def_city, def_sp, def_ctry, def_pi, def_dist, d_check = 88.1, "", "", "", "", "", 0.0, False

    if d_check: st.warning(f"⚠️ Duplicate Alert: {def_call}")
    with st.form("log_entry", clear_on_submit=True):
        st.subheader("📝 Submit Log Entry")
        now = datetime.datetime.now(datetime.timezone.utc)
        r1c1, r1c2, r1c3 = st.columns(3)
        log_freq = r1c1.number_input("Frequency", value=def_freq, format="%.1f", step=0.1)
        log_call, log_city = r1c2.text_input("Callsign / ID", value=def_call), r1c3.text_input("Station City", value=def_city)
        r2c1, r2c2, r2c3 = st.columns(3)
        log_sp, log_ctry, log_dist = r2c1.text_input("Station State/Prov", value=def_sp), r2c2.text_input("Station Country", value=def_ctry), r2c3.number_input("Distance (mi)", value=def_dist)
        r3c1, r3c2, r3c3 = st.columns(3)
        l_date, l_time, sig = r3c1.date_input("Date (UTC)", value=now.date()), r3c2.text_input("Time (UTC - HHMM)", value=now.strftime("%H%M")), r3c3.text_input("Signal Strength (dBm)")
        r4c1, r4c2, r4c3 = st.columns(3)
        with r4c1:
            rds = st.selectbox("RDS Decoded?", ["No", "Yes"])
            pi = st.text_input("PI Code", value=def_pi if rds == "Yes" else "")
        with r4c2:
            cat_d = st.selectbox("Frequency Category", [""] + df_categories['Display'].tolist())
            final_cat, prop = cat_d.split(" - ")[0] if cat_d else "", st.selectbox("Propagation", ["Local", "Tropo", "Es", "Meteor Scatter"])
        with r4c3:
            st.write("**Bonus Points:**")
            fml, wlo = st.checkbox("Logged on FMList?"), st.checkbox("Logged on WLogger?")

        if st.form_submit_button("Submit Log Entry"):
            if not st.session_state.dx_name_val or st.session_state.home_lat_val == 0: st.error("Complete sidebar first!")
            else:
                try:
                    row = [st.session_state.dx_name_val, st.session_state.dx_city_val, st.session_state.dx_st_val, st.session_state.dx_ctry_val, log_freq, log_call, "", log_city, log_sp, log_ctry, "", "", "", l_date.strftime("%m/%d/%Y"), l_time, log_dist, "", sig, rds, pi, final_cat, prop, 1 if fml else 0, 1 if wlo else 0, 0, f"{st.session_state.dx_name_val}{log_freq}{log_call}"]
                    get_gsheet().append_row(row)
                    st.success("Log recorded!"); st.balloons(); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
