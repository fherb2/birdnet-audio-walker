"""
Database Overview Page - Database selection, metadata, and file list
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import pandas as pd
from loguru import logger

from shared.streamlit_utils import find_databases_recursive
from shared.db_queries import get_analysis_config, get_all_metadata, set_analysis_config


st.set_page_config(
    page_title="Database Overview - BirdNET",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Page title
st.title("🐦 BirdNET Audio Player")
st.header("📂 Database Overview")
st.divider()

# Database selector
st.subheader("Select Database")

# Find all databases if root_path is set
if 'root_path' in st.session_state and st.session_state['root_path']:
    available_dbs = find_databases_recursive(st.session_state['root_path'])
    
    if not available_dbs:
        st.error(f"❌ No databases found in: {st.session_state['root_path']}")
        st.stop()
    
    st.info(f"Found {len(available_dbs)} database(s)")
    
    # Selectbox for database selection (FULL WIDTH, no sidebar)
    db_options = [str(db) for db in available_dbs]
    
    # Determine current selection index
    current_index = 0
    if 'db_path' in st.session_state and st.session_state['db_path'] in available_dbs:
        current_index = available_dbs.index(st.session_state['db_path'])
    
    selected_db_str = st.selectbox(
        "Database",
        options=db_options,
        index=current_index,
        help="Choose database to analyze",
        key="db_selector_overview"
    )
    
    selected_db = Path(selected_db_str)
    
    # Check if selection changed
    if selected_db != st.session_state.get('db_path'):
        # Clear all cached data
        for key in list(st.session_state.keys()):
            if key not in ['db_path', 'root_path']:
                del st.session_state[key]
        
        # Set new database
        st.session_state['db_path'] = selected_db
        st.success(f"✅ Switched to: {selected_db.name}")
        st.rerun()
    
    db_path = selected_db
else:
    db_path = st.session_state.get('db_path')

# Check if database is valid
if db_path is None:
    st.error("❌ No database path provided")
    st.info("Start with: streamlit run streamlit_app.py -- /path/to/db.db")
    st.stop()

if not db_path.exists():
    st.error(f"❌ Database not found: {db_path}")
    st.stop()

st.divider()

# Load database info
language_code = get_analysis_config(db_path, 'local_name_shortcut')
confidence_threshold = get_analysis_config(db_path, 'confidence_threshold')
created_at = get_analysis_config(db_path, 'created_at')

# Database Information
st.subheader("📊 Database Information")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Language", language_code or "Unknown")

with col2:
    st.metric("Confidence Threshold", f"{float(confidence_threshold or 0)*100:.0f}%" if confidence_threshold else "Unknown")

with col3:
    st.metric("Created", created_at or "Unknown")

st.divider()

# User Comment Section
st.subheader("📝 Notes")

# Load existing comment
existing_comment = get_analysis_config(db_path, 'user_comment') or ""

# Text area for comment
user_comment = st.text_area(
    "Database Notes/Comments",
    value=existing_comment,
    height=200,
    help="Add notes or comments about this recording session",
    key=f"user_comment_{hash(str(db_path))}"
)

# Save button
if st.button("💾 Save Notes"):
    success = set_analysis_config(db_path, 'user_comment', user_comment)
    if success:
        st.success("✅ Notes saved successfully!")
    else:
        st.error("❌ Failed to save notes")

st.divider()

# File List
st.subheader("📁 Recording Files")

metadata_list = get_all_metadata(db_path)

if not metadata_list:
    st.warning("⚠️ No files found in database")
    st.stop()

st.info(f"Total files: {len(metadata_list)}")

# Prepare table data
table_data = []
for meta in metadata_list:
    # Parse timestamps
    start_time = meta['timestamp_local']
    duration = meta['duration_seconds']
    
    # Calculate end time
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = start_dt + pd.Timedelta(seconds=duration)
        end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        end_time = "N/A"
    
    table_data.append({
        'Filename': meta['filename'],
        'Start Time': start_time,
        'End Time': end_time,
        'Duration (s)': f"{duration:.1f}",
        'Temperature (°C)': f"{meta['temperature_c']:.1f}" if meta['temperature_c'] else "N/A",
        'Battery (V)': f"{meta['battery_voltage']:.2f}" if meta['battery_voltage'] else "N/A",
        'GPS': f"{meta['gps_lat']:.4f}, {meta['gps_lon']:.4f}" if meta['gps_lat'] and meta['gps_lon'] else "N/A"
    })

df = pd.DataFrame(table_data)

# Display table
st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# Navigation hint
st.info("➡️ Go to **Audio Player** page to filter and play detections")
