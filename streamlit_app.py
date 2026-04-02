import streamlit as st
import pandas as pd
import datetime

# --- 1. CONFIG & DATA LOADING ---
STATION_DATA = "FM Challenge - Station List and Data - WTFDA Data.csv"

@st.cache_data
def load_stations():
    df = pd.read_csv(STATION_DATA)
    # Clean Callsigns: Strip -FM
    df['Station Callsign'] = df['Callsign'].str.replace(r'-FM$', '', regex=True)
    # Ensure PI Code is treated as a String to prevent "5.36E+03" error
    df['PI Code'] = df['PI Code'].astype(str).replace('nan', '')
    # Rename for UI
    df = df.rename(columns={'S/P': 'State/Province'})
    return df

df_stations = load_stations()

# --- 2. SEARCH & FILTER SECTION ---
st.subheader("🔍 Station Search")

# Reset Filter Logic
if 'reset_filters' in st.session_state and st.session_state.reset_filters:
    for key in ['f_freq', 'f_call', 'f_city', 'f_sp', 'f_country', 'f_slogan']:
        st.session_state[key] = None if "freq" in key else ""
    st.session_state.reset_filters = False

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1: f_freq = st.selectbox("Frequency", sorted(df_stations['Frequency'].unique()), index=None, key='f_freq')
with c2: f_call = st.text_input("Callsign", key='f_call').upper()
with c3: f_city = st.text_input("City", key='f_city')
with c4: f_sp = st.text_input("State/Prov (Abbr or Name)", key='f_sp')
with c5: f_country = st.text_input("Country", key='f_country')
with c6: f_slogan = st.text_input("Slogan", key='f_slogan')

# Center the Reset Button
_, center_col, _ = st.columns([2, 1, 2])
if center_col.button("Clear All Filters", use_container_width=True):
    st.session_state.reset_filters = True
    st.rerun()

# --- 3. FILTER LOGIC (Fuzzy Search) ---
view_df = df_stations.copy()
if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
if f_call: view_df = view_df[view_df['Station Callsign'].str.contains(f_call, na=False)]
if f_city: view_df = view_df[view_df['City'].str.contains(f_city, case=False, na=False)]
if f_sp:
    # Allows for "LA" or "Louisiana" if we added a mapping, 
    # but for now it does a standard "Contains" search on the Sp/Prov column
    view_df = view_df[view_df['State/Province'].str.contains(f_sp, case=False, na=False)]
if f_country: view_df = view_df[view_df['Country'].str.contains(f_country, case=False, na=False)]
if f_slogan: view_df = view_df[view_df['Slogan'].str.contains(f_slogan, case=False, na=False)]

# --- 4. THE INTERACTIVE TABLE ---
st.write(f"Showing {len(view_df)} stations:")

# We use st.data_editor to get the "Button" functionality
event = st.dataframe(
    view_df[['Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code']],
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single_row"
)

# Check if a row was selected
selected_station = None
if len(event.selection.rows) > 0:
    selected_row_index = event.selection.rows[0]
    selected_station = view_df.iloc[selected_row_index]
    st.success(f"Selected: {selected_station['Station Callsign']}. Scroll down to complete log.")

# --- 5. THE LOGGING FORM ---
if selected_station is not None:
    with st.form("log_entry"):
        st.subheader(f"📝 Logging Entry: {selected_station['Station Callsign']}")
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        c_date, c_time = st.columns(2)
        log_date = c_date.date_input("Date (UTC)", value=now_utc.date())
        log_time = c_time.text_input("Time (UTC - HHMM)", value=now_utc.strftime("%H%M"))

        # RDS Logic
        rds_ready = st.selectbox("RDS Decoded?", ["No", "Yes"])
        # PI Code stays as a string to prevent formatting issues
        pi_val = selected_station['PI Code']
        pi_code = st.text_input("PI Code", value=pi_val if rds_ready == "Yes" else "")

        # Submit
        if st.form_submit_button("Submit Log Entry"):
            # Gspread Logic here
            st.balloons()
            st.success("Entry Submitted!")
