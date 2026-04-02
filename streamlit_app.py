# --- 3. FILTER LOGIC (Fuzzy Search) ---
view_df = df_stations.copy()
if f_freq: view_df = view_df[view_df['Frequency'] == f_freq]
if f_call: view_df = view_df[view_df['Station Callsign'].str.contains(f_call, na=False)]
if f_city: view_df = view_df[view_df['City'].str.contains(f_city, case=False, na=False)]

# FUZZY SEARCH FOR STATE: This allows "LA" or "Louisiana" to work 
if f_sp:
    view_df = view_df[view_df['State/Province'].str.contains(f_sp, case=False, na=False)]

if f_country: view_df = view_df[view_df['Country'].str.contains(f_country, case=False, na=False)]
if f_slogan: view_df = view_df[view_df['Slogan'].str.contains(f_slogan, case=False, na=False)]

# --- 4. THE INTERACTIVE TABLE ---
st.write(f"Showing {len(view_df)} stations. Click the checkbox next to a station to log it:")

# We use data_editor with "num_rows='fixed'" to make it act like a selector
# We add a 'Log' column that is a checkbox
view_df.insert(0, 'Select', False)

edited_df = st.data_editor(
    view_df[['Select', 'Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code']],
    use_container_width=True,
    hide_index=True,
    column_config={"Select": st.column_config.CheckboxColumn("Log?", default=False)},
    disabled=['Frequency', 'Station Callsign', 'City', 'State/Province', 'Country', 'Slogan', 'PI Code']
)

# Check which row was checked
selected_rows = edited_df[edited_df['Select'] == True]
selected_station = None

if not selected_rows.empty:
    # Grab the first one they checked
    selected_station = selected_rows.iloc[0]
    st.info(f"✅ Selected: {selected_station['Station Callsign']}. Fill out the form below.")
