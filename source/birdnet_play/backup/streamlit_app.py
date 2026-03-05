"""
BirdNET Audio Player - Streamlit Multi-Page App Entry Point
"""

import sys
import streamlit as st
from loguru import logger

# Setup logging
logger.remove()
logger.add(sys.stderr, level="INFO")

# Page config
st.set_page_config(
    page_title="BirdNET Audio Player",
    page_icon="🐦",
    layout="wide",
    initial_sidebar_state="collapsed"  # Start without sidebar
)

# Initialize session state from command line arguments
from shared.streamlit_utils import initialize_session_state_from_args

if not initialize_session_state_from_args():
    st.error("❌ No database path provided or no databases found")
    st.info("**Usage:** `streamlit run streamlit_app.py -- /path/to/database_or_folder`")
    st.stop()

# Auto-redirect to Database Overview page
st.switch_page("pages/1_database_overview.py")
