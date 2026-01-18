"""
Streamlit Web Interface for BirdNET Audio Player.
"""

import sys
import streamlit as st
from pathlib import Path
from datetime import datetime, time as dt_time
from loguru import logger

from shared.db_queries import get_analysis_config, query_detections
from .filters import DetectionFilter, parse_date
from .player import AudioPlayer


def render_header(db_path: Path, language_code: str):
    """Render page header with database info."""
    st.title("🐦 BirdNET Audio Player")
    st.markdown(f"**📂 Database:** `{db_path}`")
    st.markdown(f"**🌍 Language:** {language_code}")
    st.divider()


def render_filter_sidebar(db_path: Path) -> DetectionFilter:
    """
    Render filter controls in sidebar.
    
    Returns:
        DetectionFilter object with current filter settings
    """
    st.sidebar.title("🔍 Filter")
    
    # Species filter
    species = st.sidebar.text_input(
        "Species",
        help="Search by scientific, local, or Czech name (partial match)"
    )
    
    # Date filters
    st.sidebar.subheader("Date Range")
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        date_from = st.date_input("From", value=None)
    with col2:
        date_to = st.date_input("To", value=None)
    
    # Time of day filter
    st.sidebar.subheader("Time of Day")
    use_time_filter = st.sidebar.checkbox("Enable time filter")
    
    time_start = None
    time_end = None
    
    if use_time_filter:
        col1, col2 = st.sidebar.columns(2)
        with col1:
            time_start = st.time_input("Start", value=dt_time(0, 0))
        with col2:
            time_end = st.time_input("End", value=dt_time(23, 59))
    
    # Confidence filter
    min_confidence = st.sidebar.slider(
        "Min Confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        help="Minimum confidence threshold (0.0 = all detections)"
    )
    
    # Limit and offset
    limit = st.sidebar.slider(
        "Limit",
        min_value=1,
        max_value=100,
        value=20,
        help="Maximum number of detections to load"
    )
    
    offset = st.sidebar.number_input(
        "Offset",
        min_value=0,
        value=0,
        step=10,
        help="Start position (for pagination)"
    )
    
    # PM buffer
    pm_seconds = st.sidebar.slider(
        "PM Buffer (seconds)",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.5,
        help="Plus/Minus buffer around detection"
    )
    
    # Options
    st.sidebar.subheader("Options")
    use_sci = st.sidebar.checkbox(
        "Scientific Names",
        help="Use scientific names for TTS instead of local names"
    )
    
    shuffle = st.sidebar.checkbox(
        "Shuffle",
        help="Randomize playback order"
    )
    
    # Convert to DetectionFilter
    return DetectionFilter(
        species=species if species else None,
        date_from=datetime.combine(date_from, dt_time(0, 0)) if date_from else None,
        date_to=datetime.combine(date_to, dt_time(23, 59)) if date_to else None,
        time_start=time_start,
        time_end=time_end,
        min_confidence=min_confidence if min_confidence > 0 else None,
        limit=limit,
        offset=offset,
        shuffle=shuffle,
        pm_seconds=pm_seconds,
        use_sci=use_sci
    )


def main():
    """Main Streamlit application."""
    
    # Page config
    st.set_page_config(
        page_title="BirdNET Audio Player",
        page_icon="🐦",
        layout="wide"
    )
    
    # Setup logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # Get database path from command line args
    if len(sys.argv) < 2:
        st.error("❌ No database path provided")
        st.info("Usage: streamlit run streamlit_app.py -- /path/to/db.db")
        st.stop()
    
    db_path = Path(sys.argv[1])
    
    if not db_path.exists():
        st.error(f"❌ Database not found: {db_path}")
        st.stop()
    
    # Load language from database
    language_code = get_analysis_config(db_path, 'local_name_shortcut')
    if not language_code:
        language_code = 'de'
        st.warning("⚠️ Language not found in database, defaulting to 'de'")
    
    # Render header
    render_header(db_path, language_code)
    
    # Render filter sidebar
    detection_filter = render_filter_sidebar(db_path)
    
    # Validate filter
    error = detection_filter.validate()
    if error:
        st.sidebar.error(f"❌ Invalid filter: {error}")
        st.stop()
    
    # Query detections button
    if st.sidebar.button("🔍 Load Detections", type="primary"):
        with st.spinner("Loading detections..."):
            try:
                detections = query_detections(db_path, **detection_filter.to_query_params())
                
                if not detections:
                    st.warning("⚠️ No detections found matching filters")
                    st.stop()
                
                # Shuffle if requested
                if detection_filter.shuffle:
                    import random
                    random.shuffle(detections)
                
                # Store in session state
                st.session_state['detections'] = detections
                st.session_state['filter'] = detection_filter
                st.session_state['language_code'] = language_code
                st.session_state['db_path'] = db_path
                
                st.success(f"✅ Loaded {len(detections)} detection(s)")
                
            except Exception as e:
                st.error(f"❌ Error loading detections: {e}")
                logger.exception("Query failed")
    
    # Show detections if loaded
    if 'detections' in st.session_state and st.session_state['detections']:
        detections = st.session_state['detections']
        filter_context = st.session_state['filter'].get_filter_context()
        language_code = st.session_state['language_code']
        db_path = st.session_state['db_path']
        pm_seconds = st.session_state['filter'].pm_seconds
        use_sci = st.session_state['filter'].use_sci
        
        st.divider()
        st.subheader(f"📊 {len(detections)} Detection(s) Loaded")
        
        # Show detection list
        with st.expander("📋 Detection List", expanded=False):
            for i, det in enumerate(detections, 1):
                conf_pct = det['confidence'] * 100
                st.write(
                    f"{i}. **#{det['detection_id']}** - "
                    f"{det.get('local_name', det['scientific_name'])} "
                    f"({conf_pct:.1f}%) - "
                    f"{det['segment_start_local']}"
                )
        
        # Export button
        st.divider()
        col1, col2 = st.columns([3, 1])
        
        with col2:
            if st.button("💾 Export All as WAV"):
                from .player import export_detections
                import tempfile
                
                with st.spinner("Exporting..."):
                    try:
                        # Create temp directory
                        export_dir = Path(tempfile.mkdtemp(prefix="birdnet_export_"))
                        
                        export_detections(
                            db_path,
                            export_dir,
                            detections,
                            language_code,
                            filter_context,
                            pm_seconds,
                            use_sci
                        )
                        
                        st.success(f"✅ Exported {len(detections)} files to: {export_dir}")
                        
                    except Exception as e:
                        st.error(f"❌ Export failed: {e}")
        
        # NOTE: Custom HTML Player würde hier eingefügt werden
        # Das kommt in Teil 2 (separates Artefakt)
        st.info("🎵 Sequential audio player coming in next update...")


if __name__ == "__main__":
    main()
