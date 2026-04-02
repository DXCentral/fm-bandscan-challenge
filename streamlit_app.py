import streamlit as st
import pandas as pd
import numpy as np
import math
import datetime

# --- 1. CONFIG & URL PERSISTENCE ---
# This looks at the URL to see if Name, Lat, or Lon are already there
query_params = st.query_params

def update_url():
    # This updates the browser URL whenever a value changes
    st.query_params["name"] = st.session_state.dx_name
    st.query_params["lat"] = str(st.session_state.dx_lat)
    st.query_params["lon"] = str(st.session_state.dx_lon)
    st.query_params["city"] = st.session_state.dx_city
    st.query_params["st"] = st.session_state.dx_st

# --- 2. SIDEBAR WITH "REMEMBER ME" LOGIC ---
with st.sidebar:
    st.header("📍 DXer Profile")
    st.info("Fill this out once, then bookmark the page to 'Remember Me'!")
    
    # Pull values from URL if they exist, otherwise use defaults
    default_name = query_params.get("name", "")
    default_lat = float(query_params.get("lat", 30.3583))
    default_lon = float(query_params.get("lon", -90.0656))
    default_city = query_params.get("city", "Mandeville")
    default_st = query_params.get("st", "LA")

    dxer_name = st.text_input("Your Name", value=default_name, key="dx_name", on_change=update_url)
    
    col_c, col_s = st.columns([2, 1])
    dxer_city = col_c.text_input("City", value=default_city, key="dx_city", on_change=update_url)
    dxer_st = col_s.text_input("ST", value=default_st, key="dx_st", on_change=update_url)

    st.divider()
    st.write("Coordinates (for Distance Math):")
    home_lat = st.number_input("Latitude", value=default_lat, format="%.4f", key="dx_lat", on_change=update_url)
    home_lon = st.number_input("Longitude", value=default_lon, format="%.4f", key="dx_lon", on_change=update_url)

    if st.button("Generate Bookmark Link"):
        st.success("Check your browser address bar! Bookmark that URL to save your settings.")

# --- 3. DISTANCE CALCULATION ---
# Now using the dynamic home_lat and home_lon from the sidebar
def get_row_dist(row):
    lat_val = dms_to_dd(row['Lat-N'])
    lon_val = dms_to_dd(row['Long-W'])
    if lat_val is not None and lon_val is not None:
        # We use the live variables from the sidebar here
        return calculate_distance(home_lat, home_lon, lat_val, -lon_val)
    return 0

# Apply the distance to the dataframe
# This will now trigger an instant refresh of the 'Dist' column 
# whenever the user changes the Latitude or Longitude boxes
view_df['Dist'] = view_df.apply(get_row_dist, axis=1)
