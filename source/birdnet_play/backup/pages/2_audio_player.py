"""
Audio Player Page - Filter detections and play audio
"""

import streamlit as st
from pathlib import Path
from datetime import datetime, time as dt_time, timedelta
from typing import List
import tempfile
import base64
import json
from loguru import logger

from shared.db_queries import get_analysis_config, query_detections
from birdnet_play.filters import DetectionFilter
from birdnet_play.player import AudioPlayer, export_detections, export_detections_mp3


st.set_page_config(
    page_title="Audio Player - BirdNET",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Page title
st.title("🐦 BirdNET Audio Player")
st.header("🎵 Audio Player")

# Check if database is selected
db_path = st.session_state.get('db_path')

if db_path is None:
    st.error("❌ No database selected")
    st.info("Please select a database in the **Database Overview** page first")
    if st.button("📂 Go to Database Overview"):
        st.switch_page("pages/1_database_overview.py")
    st.stop()

if not db_path.exists():
    st.error(f"❌ Database not found: {db_path}")
    st.stop()

# Load language from database
language_code = get_analysis_config(db_path, 'local_name_shortcut')
if not language_code:
    language_code = 'de'
    st.warning("⚠️ Language not found in database, defaulting to 'de'")

st.markdown(f"**🌍 Language:** {language_code}")
st.markdown(f"**📂 Database:** `{db_path.name}`")
st.divider()


# =============================================================================
# SESSION STATE INITIALIZATION (with defaults)
# =============================================================================

def init_filter_state():
    """Initialize filter session state with defaults for Page 2."""
    if 'filter_species' not in st.session_state:
        st.session_state['filter_species'] = ""
    if 'page2_filter_date_from' not in st.session_state or 'page2_filter_date_to' not in st.session_state:
        from shared.db_queries import get_recording_date_range
        min_date, max_date = get_recording_date_range(db_path)
        st.session_state['page2_filter_date_from'] = min_date.date() if min_date else None
        st.session_state['page2_filter_date_to'] = max_date.date() if max_date else None
    if 'page2_filter_use_time' not in st.session_state:
        st.session_state['page2_filter_use_time'] = False
    if 'page2_filter_time_start' not in st.session_state:
        st.session_state['page2_filter_time_start'] = dt_time(0, 0, 0)
    if 'page2_filter_time_end' not in st.session_state:
        st.session_state['page2_filter_time_end'] = dt_time(23, 59, 59)
    if 'page2_filter_confidence' not in st.session_state:
        st.session_state['page2_filter_confidence'] = "70%"
    if 'page2_filter_limit' not in st.session_state:
        st.session_state['page2_filter_limit'] = 25
    if 'page2_filter_offset' not in st.session_state:
        st.session_state['page2_filter_offset'] = 0
    if 'page2_filter_sort' not in st.session_state:
        st.session_state['page2_filter_sort'] = "time"


def init_audio_state():
    """Initialize audio options session state with defaults."""
    if 'audio_say_number' not in st.session_state:
        st.session_state['audio_say_number'] = False
    if 'audio_bird_name' not in st.session_state:
        st.session_state['audio_bird_name'] = "none"
    if 'audio_say_id' not in st.session_state:
        st.session_state['audio_say_id'] = False
    if 'audio_say_confidence' not in st.session_state:
        st.session_state['audio_say_confidence'] = False
    if 'audio_speech_speed' not in st.session_state:
        st.session_state['audio_speech_speed'] = 1.0  # 0.5 - 2.0
    if 'audio_speech_loudness' not in st.session_state:
        st.session_state['audio_speech_loudness'] = -2
    if 'audio_frame_duration' not in st.session_state:
        st.session_state['audio_frame_duration'] = 1.0  # 0.5 - 6.0 seconds
    if 'audio_noise_reduction' not in st.session_state:
        st.session_state['audio_noise_reduction'] = True
    if 'audio_noise_reduce_strength' not in st.session_state:
        st.session_state['audio_noise_reduce_strength'] = 0.8


# Initialize session state
init_filter_state()
init_audio_state()


# =============================================================================
# FILTER SECTION (Main Area - Top)
# =============================================================================

st.subheader("🔍 Search Filters")

# Species filter with auto-complete
from streamlit_searchbox import st_searchbox
from shared.db_queries import search_species_in_list

def search_species_callback(search_term: str) -> List[str]:
    """Callback for searchbox - searches in species_list."""
    return search_species_in_list(db_path, search_term, limit=10)

col1, col2 = st.columns([3, 1])
with col1:
    current_species = st.session_state.get('filter_species', '')
    
    # If species already selected (e.g., from Page 1), show it with clear button
    if current_species:
        col_a, col_b = st.columns([4, 1])
        with col_a:
            st.info(f"🔍 Selected: **{current_species}**")
        with col_b:
            if st.button("✕", key="clear_species", help="Clear species filter"):
                st.session_state['filter_species'] = ''
                # Increment counter to force searchbox reset
                st.session_state['searchbox_reset_counter'] = st.session_state.get('searchbox_reset_counter', 0) + 1
                st.rerun()
    else:
        # Use dynamic key to force component reset when cleared
        searchbox_key = f"species_searchbox_{st.session_state.get('searchbox_reset_counter', 0)}"
        
        selected_species = st_searchbox(
            search_species_callback,
            key=searchbox_key,
            placeholder="Search species... (type to filter)",
            clear_on_submit=False
        )
        
        # Update session state if selection made
        if selected_species:
            # Extract scientific name from "Scientific (Local)" format
            if '(' in selected_species:
                scientific_name = selected_species.split(' (')[0]
            else:
                scientific_name = selected_species
            
            st.session_state['filter_species'] = scientific_name

with col2:
    # Xeno-Canto button (only active if species selected)
    species_for_xc = st.session_state.get('filter_species', '')
    
    if species_for_xc:
        # Build Xeno-Canto URL with scientific name
        # Replace spaces with + for URL
        xc_query = species_for_xc.replace(' ', '+')
        xc_url = f"https://xeno-canto.org/explore?query={xc_query}&view=3"
        
        st.link_button(
            "🔊 Xeno-Canto",
            xc_url,
            help=f"Open {species_for_xc} in Xeno-Canto (new tab)",
            width='stretch'
        )
    else:
        # Disabled placeholder when no species selected
        st.button(
            "🔊 Xeno-Canto",
            disabled=True,
            help="Select a species first",
            width='stretch'
        )

# Date filters
col1, col2, col3 = st.columns(3)
with col1:
    date_from = st.date_input(
        "Date From",
        value=st.session_state['page2_filter_date_from'],
        key="input_date_from"
    )
    st.session_state['page2_filter_date_from'] = date_from

with col2:
    date_to = st.date_input(
        "Date To",
        value=st.session_state['page2_filter_date_to'],
        key="input_date_to"
    )
    st.session_state['page2_filter_date_to'] = date_to

with col3:
    use_time_filter = st.checkbox(
        "Enable Time Filter",
        value=st.session_state['page2_filter_use_time'],
        key="input_use_time"
    )
    st.session_state['page2_filter_use_time'] = use_time_filter
    
    # Reset times to full day range when disabled
    if not use_time_filter:
        st.session_state['page2_filter_time_start'] = dt_time(0, 0, 0)
        st.session_state['page2_filter_time_end'] = dt_time(23, 59, 59)

# Time filters (if enabled)
if use_time_filter:
    col1, col2 = st.columns(2)
    with col1:
        time_start = st.time_input(
            "Time Start",
            value=st.session_state['page2_filter_time_start'],
            key="input_time_start"
        )
        st.session_state['page2_filter_time_start'] = time_start
    
    with col2:
        time_end = st.time_input(
            "Time End",
            value=st.session_state['page2_filter_time_end'],
            key="input_time_end"
        )
        st.session_state['page2_filter_time_end'] = time_end
    

# Confidence, Limit, Offset
col1, col2, col3, col4 = st.columns(4)

with col1:
    conf_options = ["All"] + [f"{i}%" for i in range(5, 100, 5)]
    current_conf_idx = 0
    if st.session_state['page2_filter_confidence'] in conf_options:
        current_conf_idx = conf_options.index(st.session_state['page2_filter_confidence'])
    
    conf_selected = st.selectbox(
        "Min Confidence",
        options=conf_options,
        index=current_conf_idx,
        key="input_confidence"
    )
    st.session_state['page2_filter_confidence'] = conf_selected

with col2:
    limit = st.number_input(
        "Limit",
        min_value=1,
        max_value=1000,
        value=st.session_state['page2_filter_limit'],
        key="input_limit"
    )
    st.session_state['page2_filter_limit'] = limit

with col3:
    offset = st.number_input(
        "Offset",
        min_value=0,
        value=st.session_state['page2_filter_offset'],
        step=10,
        key="input_offset"
    )
    st.session_state['page2_filter_offset'] = offset

with col4:
    sort_options = {
        "Time (oldest→newest)": "time",
        "Confidence (high→low)": "confidence", 
        "ID (upwards)": "id"
    }
    current_sort_label = [k for k, v in sort_options.items() if v == st.session_state['page2_filter_sort']][0]
    
    sort_selected = st.selectbox(
        "Sort By",
        options=list(sort_options.keys()),
        index=list(sort_options.keys()).index(current_sort_label),
        key="input_sort"
    )
    st.session_state['page2_filter_sort'] = sort_options[sort_selected]

# Apply Filters Button
if st.button("🔍 **Apply Filters**", type="primary", width="stretch"):
    st.session_state['filters_applied'] = True
    st.rerun()

st.divider()


# =============================================================================
# SIDEBAR: AUDIO OPTIONS
# =============================================================================

st.sidebar.title("🎵 Audio Options")

# Say Audio Number
say_number = st.sidebar.checkbox(
    "Say Audio Number",
    value=st.session_state['audio_say_number'],
    key="sidebar_say_number"
)
st.session_state['audio_say_number'] = say_number

# Say Bird Name
st.sidebar.subheader("Say Bird Name")
bird_name_option = st.sidebar.radio(
    "Name Type",
    options=["None", "Local Name", "Scientific Name"],
    index=["none", "local", "scientific"].index(st.session_state['audio_bird_name']),
    key="sidebar_bird_name"
)
st.session_state['audio_bird_name'] = {
    "None": "none",
    "Local Name": "local",
    "Scientific Name": "scientific"
}[bird_name_option]

# Say DB ID
say_id = st.sidebar.checkbox(
    "Say Database ID",
    value=st.session_state['audio_say_id'],
    key="sidebar_say_id"
)
st.session_state['audio_say_id'] = say_id

# Say Confidence
say_confidence = st.sidebar.checkbox(
    "Say Confidence",
    value=st.session_state['audio_say_confidence'],
    key="sidebar_say_confidence"
)
st.session_state['audio_say_confidence'] = say_confidence

st.sidebar.divider()

# Speech Speed
speech_speed = st.sidebar.slider(
    "Speech Speed",
    min_value=0.5,
    max_value=2.0,
    value=st.session_state['audio_speech_speed'],
    step=0.1,
    key="sidebar_speech_speed",
    help="1.0 = normal speed"
)
st.session_state['audio_speech_speed'] = speech_speed

# Speech Loudness
speech_loudness = st.sidebar.slider(
    "Speech Loudness",
    min_value=-10,
    max_value=4,
    value=st.session_state['audio_speech_loudness'],
    step=1,
    key="sidebar_speech_loudness",
    help="0 = normal loudness, ±dB adjustment"
)
st.session_state['audio_speech_loudness'] = speech_loudness

st.sidebar.divider()

# Audio Frame Duration (formerly PM Buffer)
frame_duration = st.sidebar.slider(
    "Audio Frame Duration (s)",
    min_value=0.5,
    max_value=6.0,
    value=st.session_state['audio_frame_duration'],
    step=0.5,
    key="sidebar_frame_duration",
    help="Duration of audio frame around detection (0.5-6.0 seconds)"
)
st.session_state['audio_frame_duration'] = frame_duration

st.sidebar.divider()

# Noise Reduction
noise_reduction_on = st.sidebar.checkbox(
    "Noise Reduction",
    value=st.session_state['audio_noise_reduction'],
    key="sidebar_noise_reduction"
)
st.session_state['audio_noise_reduction'] = noise_reduction_on

if noise_reduction_on:
    import numpy as np
    _nr_steps = np.logspace(np.log10(0.5), np.log10(1.0), 20)
    _current_val = st.session_state['audio_noise_reduce_strength']
    _current_idx = int(np.argmin(np.abs(_nr_steps - _current_val)))

    nr_strength_idx = st.sidebar.slider(
        "Noise Reduction Strength",
        min_value=0,
        max_value=19,
        value=_current_idx,
        step=1,
        key="sidebar_nr_strength",
        help="Logarithmic scale: finer steps near 1.0 (stronger reduction)"
    )
    st.session_state['audio_noise_reduce_strength'] = float(_nr_steps[nr_strength_idx])
    st.sidebar.caption(f"prop_decrease = {_nr_steps[nr_strength_idx]:.3f}")

st.sidebar.divider()

# Apply Audio Settings Button
if st.sidebar.button("🎵 **Apply Audio Settings**", type="primary", width="stretch"):
    st.session_state['audio_settings_applied'] = True
    st.rerun()

# Cache Clear Button
if st.sidebar.button("🔄 Clear Audio Cache"):
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith('audio_cache_')]
    for key in keys_to_remove:
        del st.session_state[key]
    st.sidebar.success("Cache cleared!")
    st.rerun()


# =============================================================================
# LOAD DETECTIONS (only if filters were applied)
# =============================================================================

if not st.session_state.get('filters_applied', False):
    st.info("👆 Configure filters above and click **'Apply Filters'** to load detections")
    st.stop()

# Build filter from session state
min_confidence = None if st.session_state['page2_filter_confidence'] == "All" else \
    int(st.session_state['page2_filter_confidence'].rstrip('%')) / 100

# Determine sort order based on sort_by
sort_order = "desc" if st.session_state['page2_filter_sort'] == "confidence" else "asc"

detection_filter = DetectionFilter(
    species=st.session_state['filter_species'] if st.session_state['filter_species'] else None,
    date_from=datetime.combine(st.session_state['page2_filter_date_from'], dt_time(0, 0)) if st.session_state['page2_filter_date_from'] else None,
    date_to=datetime.combine(st.session_state['page2_filter_date_to'], dt_time(23, 59)) if st.session_state['page2_filter_date_to'] else None,
    time_start=st.session_state['page2_filter_time_start'] if st.session_state['page2_filter_use_time'] else None,
    time_end=st.session_state['page2_filter_time_end'] if st.session_state['page2_filter_use_time'] else None,
    min_confidence=min_confidence,
    limit=st.session_state['page2_filter_limit'],
    offset=st.session_state['page2_filter_offset'],
    sort_by=st.session_state['page2_filter_sort'],
    sort_order=sort_order,
    pm_seconds=st.session_state['audio_frame_duration'],
    use_sci=(st.session_state['audio_bird_name'] == "scientific")
)

# Validate filter
error = detection_filter.validate()
if error:
    st.error(f"❌ Invalid filter: {error}")
    st.stop()

# Query detections
with st.spinner("Loading detections..."):
    try:
        detections = query_detections(db_path, **detection_filter.to_query_params())
        
        if not detections:
            st.warning("⚠️ No detections found matching filters")
            st.stop()
        
        # Store in session state
        st.session_state['detections'] = detections
        st.session_state['filter'] = detection_filter
        st.session_state['language_code'] = language_code
        
    except Exception as e:
        st.error(f"❌ Error loading detections: {e}")
        logger.exception("Query failed")
        st.stop()


def calculate_single_audio_length(
    frame_duration: float,
    audio_options: dict,
    avg_tts_duration: float = 4.0
) -> float:
    """
    Calculate the duration of a single audio output in seconds.
    
    Components:
    - 1.0s initial pause
    - frame_duration (before detection)
    - 3.0s detection snippet (BirdNET standard)
    - frame_duration (after detection)
    - TTS announcement (estimated)
    
    Args:
        frame_duration: Audio Frame Duration in seconds (0.5-6.0)
        audio_options: Audio options dict (for TTS estimation)
        avg_tts_duration: Average TTS duration in seconds (default: 4.0s)
        
    Returns:
        Total duration in seconds
    """
    # Base components
    initial_pause = 1.0
    detection_audio = 3.0  # BirdNET standard detection length
    frame_before = frame_duration
    frame_after = frame_duration
    
    # TTS duration estimation based on what's being said
    if audio_options.get('bird_name_option') == 'none' and \
       not audio_options.get('say_audio_number') and \
       not audio_options.get('say_id') and \
       not audio_options.get('say_confidence'):
        # No TTS at all
        tts_duration = 0.5  # Short pause instead
    else:
        # Estimate TTS length based on components
        # Adjust by speech speed
        speed = audio_options.get('speech_speed', 1.0)
        tts_duration = avg_tts_duration / speed
    
    total = initial_pause + frame_before + detection_audio + frame_after + tts_duration
    
    return total


def calculate_outputs_per_minute(single_audio_length: float) -> float:
    """
    Calculate how many audio outputs can be played per minute.
    
    Args:
        single_audio_length: Duration of single audio in seconds
        
    Returns:
        Number of outputs per minute (rounded to 1 decimal)
    """
    if single_audio_length <= 0:
        return 0.0
    
    outputs_per_minute = 60.0 / single_audio_length
    
    return round(outputs_per_minute, 1)


# =============================================================================
# DISPLAY DETECTIONS
# =============================================================================

detections = st.session_state['detections']
filter_context = detection_filter.get_filter_context()

st.subheader(f"📊 {len(detections)} Detection(s) Loaded")

# Build audio_options dict from session state FIRST
audio_options = {
    'say_audio_number': st.session_state['audio_say_number'],
    'say_id': st.session_state['audio_say_id'],
    'say_confidence': st.session_state['audio_say_confidence'],
    'bird_name_option': st.session_state['audio_bird_name'],
    'speech_speed': st.session_state['audio_speech_speed'],
    'speech_loudness': st.session_state['audio_speech_loudness'],
    'noise_reduce_strength': (
        st.session_state['audio_noise_reduce_strength'] if st.session_state['audio_noise_reduction'] else None
    )
}

# Calculate and display audio statistics
single_length = calculate_single_audio_length(
    st.session_state['audio_frame_duration'],
    audio_options
)
outputs_per_min = calculate_outputs_per_minute(single_length)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        "Single Audio Length",
        f"{single_length:.1f}s",
        help="Duration of one complete audio output (pause + frame + detection + frame + TTS)"
    )
with col2:
    st.metric(
        "Outputs per Minute",
        f"{outputs_per_min:.1f}",
        help="How many detections can be played per minute at current settings"
    )
with col3:
    total_duration_min = (len(detections) * single_length) / 60
    st.metric(
        "Total Playback Time",
        f"{total_duration_min:.1f} min",
        help="Estimated total time to play all loaded detections"
    )

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

st.divider()
col1, col2, col3 = st.columns([2, 1, 1])

# Note: Export uses current audio settings but disable_tts depends on bird_name option
disable_tts = (st.session_state['audio_bird_name'] == "none" and 
               not st.session_state['audio_say_number'] and
               not st.session_state['audio_say_id'] and
               not st.session_state['audio_say_confidence'])

with col2:
    if st.button("💾 Export as WAV"):
        with st.spinner("Exporting WAV files..."):
            try:
                export_dir = Path(tempfile.mkdtemp(prefix="birdnet_export_wav_"))
                
                export_detections(
                        db_path,
                        export_dir,
                        detections,
                        language_code,
                        filter_context,
                        audio_options,
                        st.session_state['audio_frame_duration'],
                        disable_tts
                    )
                
                st.success(f"✅ Exported {len(detections)} WAV files to: {export_dir}")
                
            except Exception as e:
                st.error(f"❌ WAV export failed: {e}")
                logger.exception("WAV export failed")

with col3:
    if st.button("💾 Export as MP3"):
        with st.spinner("Exporting MP3 files..."):
            try:
                export_dir = Path(tempfile.mkdtemp(prefix="birdnet_export_mp3_"))
                
                export_detections_mp3(
                        db_path,
                        export_dir,
                        detections,
                        language_code,
                        filter_context,
                        audio_options,
                        st.session_state['audio_frame_duration'],
                        disable_tts
                    )
                
                st.success(f"✅ Exported {len(detections)} MP3 files to: {export_dir}")
                
            except Exception as e:
                st.error(f"❌ MP3 export failed: {e}")
                logger.exception("MP3 export failed")


# =============================================================================
# AUDIO PLAYER
# =============================================================================

st.divider()
st.subheader("🎵 Audio Player")

# Clear audio cache if filters or audio settings changed
if st.session_state.get('filters_applied', False) or st.session_state.get('audio_settings_applied', False):
    # Clear cache to force regeneration
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith('audio_cache_')]
    for key in keys_to_remove:
        del st.session_state[key]
    
    # Reset flags
    if 'filters_applied' in st.session_state:
        st.session_state['filters_applied'] = False
    if 'audio_settings_applied' in st.session_state:
        st.session_state['audio_settings_applied'] = False
    
    logger.info("Audio cache cleared due to filter/settings change")

with st.spinner("Preparing audio files..."):
    try:
        player = AudioPlayer(db_path, st.session_state['audio_frame_duration'])
        
        # Generate cache key (include audio settings to force regeneration on changes)
        cache_params = (
            tuple(d['detection_id'] for d in detections),
            st.session_state['audio_frame_duration'],
            st.session_state['audio_bird_name'],
            st.session_state['audio_say_number'],
            st.session_state['audio_say_id'],
            st.session_state['audio_say_confidence']
        )
        cache_key = f"audio_cache_{hash(cache_params)}"
        
        # Check if already cached
        if cache_key in st.session_state:
            logger.info("Using cached audio files")
            audio_files = st.session_state[cache_key]
        else:
            # Generate audio files with progress indicator
            audio_files = []
            progress_bar = st.progress(0, text="Preparing audio files...")
            
            for i, det in enumerate(detections):
                try:
                    audio_bytes = player.prepare_detection_audio_web(
                            det,
                            audio_number=i+1,  # Sequential number (1, 2, 3, ...)
                            language_code=language_code,
                            filter_context=filter_context,
                            audio_options=audio_options,
                            disable_tts=disable_tts
                        )
                    
                    audio_b64 = base64.b64encode(audio_bytes.read()).decode()
                    conf_pct = det['confidence'] * 100
                    
                    audio_files.append({
                        'id': det['detection_id'],
                        'name': det.get('local_name', det['scientific_name']),
                        'scientific': det['scientific_name'],
                        'confidence': conf_pct,
                        'time': det['segment_start_local'],
                        'timezone': det.get('timezone', 'MEZ'),
                        'audio_data': audio_b64
                    })
                    
                    progress = (i + 1) / len(detections)
                    progress_bar.progress(progress, text=f"Preparing audio files... {i+1}/{len(detections)}")
                    
                except Exception as e:
                    logger.error(f"Failed to prepare detection #{det['detection_id']}: {e}")
            
            progress_bar.empty()
            st.session_state[cache_key] = audio_files
            logger.info(f"Cached {len(audio_files)} audio files")
        
        # Create HTML player (same as before)
        audio_data_js = json.dumps(audio_files)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    padding: 0;
                    margin: 0;
                    background-color: #0e1117;
                    color: #fafafa;
                }}
                #player-container {{
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                #now-playing {{
                    background: #262730;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    border-left: 4px solid #ff4b4b;
                }}
                #now-playing h3 {{
                    margin-top: 0;
                    color: #ff4b4b;
                }}
                .info-row {{
                    margin: 8px 0;
                    font-size: 14px;
                }}
                .info-label {{
                    color: #888;
                    display: inline-block;
                    width: 120px;
                }}
                .progress {{
                    width: 100%;
                    height: 8px;
                    background: #444;
                    border-radius: 4px;
                    margin: 15px 0;
                    overflow: hidden;
                }}
                .progress-bar {{
                    height: 100%;
                    background: linear-gradient(90deg, #ff4b4b, #ff6b6b);
                    border-radius: 4px;
                    width: 0%;
                    transition: width 0.3s ease;
                }}
                #audio-player {{
                    width: 100%;
                    margin: 15px 0;
                    border-radius: 4px;
                }}
                .controls {{
                    display: flex;
                    gap: 10px;
                    margin: 20px 0;
                    flex-wrap: wrap;
                }}
                button {{
                    padding: 12px 24px;
                    font-size: 16px;
                    cursor: pointer;
                    background: #ff4b4b;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    transition: background 0.2s;
                    font-weight: 500;
                }}
                button:hover {{
                    background: #ff6b6b;
                }}
                button:disabled {{
                    background: #444;
                    cursor: not-allowed;
                }}
                #recent-list {{
                    background: #262730;
                    padding: 15px;
                    border-radius: 8px;
                    max-height: 250px;
                    overflow-y: auto;
                }}
                #recent-list h4 {{
                    margin-top: 0;
                    color: #fafafa;
                }}
                .recent-item {{
                    padding: 10px;
                    margin: 5px 0;
                    background: #1e1e1e;
                    border-radius: 4px;
                    border-left: 3px solid #4CAF50;
                    font-size: 13px;
                }}
                .status-text {{
                    font-size: 14px;
                    color: #888;
                    margin: 10px 0;
                }}
            </style>
        </head>
        <body>
            <div id="player-container">
                <div id="now-playing">
                    <h3>🔊 Now Playing</h3>
                    <div id="current-info">
                        <div class="info-row">
                            <span class="info-label">Status:</span>
                            <span id="status">Ready to play...</span>
                        </div>
                        <div class="info-row" id="current-details" style="display:none;">
                            <span class="info-label">ID:</span>
                            <span id="det-id">-</span><br>
                            <span class="info-label">Species:</span>
                            <span id="det-species">-</span><br>
                            <span class="info-label">Confidence:</span>
                            <span id="det-confidence">-</span><br>
                            <span class="info-label">Time:</span>
                            <span id="det-time">-</span>
                        </div>
                    </div>
                    <div class="progress">
                        <div class="progress-bar" id="progress-bar"></div>
                    </div>
                    <div class="status-text" id="progress-text">0 / {len(audio_files)}</div>
                </div>
                
                <audio id="audio-player" controls></audio>
                
                <div class="controls">
                    <button id="btn-play" onclick="playPause()">▶ Play</button>
                    <button id="btn-prev" onclick="previous()">⏮ Previous</button>
                    <button id="btn-next" onclick="next()">⏭ Next</button>
                    <button id="btn-stop" onclick="stop()">⏹ Stop</button>
                </div>
                
                <div id="recent-list">
                    <h4>📋 Recently Played</h4>
                    <div id="recent-items">
                        <div class="status-text">No items played yet</div>
                    </div>
                </div>
            </div>
            
            <script>
                const audioFiles = {audio_data_js};
                let currentIndex = 0;
                let isPlaying = false;
                const recentPlayed = [];
                
                const player = document.getElementById('audio-player');
                const statusEl = document.getElementById('status');
                const detailsEl = document.getElementById('current-details');
                const progressBar = document.getElementById('progress-bar');
                const progressText = document.getElementById('progress-text');
                const recentItems = document.getElementById('recent-items');
                const btnPlay = document.getElementById('btn-play');
                
                function loadDetection(index) {{
                    if (index < 0 || index >= audioFiles.length) return;
                    
                    currentIndex = index;
                    const det = audioFiles[index];
                    
                    player.src = 'data:audio/mp3;base64,' + det.audio_data;
                    
                    document.getElementById('det-id').textContent = '#' + det.id;
                    document.getElementById('det-species').textContent = det.name + ' (' + det.scientific + ')';
                    document.getElementById('det-confidence').textContent = det.confidence.toFixed(1) + '%';
                    
                    const datetime = det.time;
                    const dateTimeParts = datetime.split('T');
                    const datePart = dateTimeParts[0];
                    const timePart = dateTimeParts[1].split('+')[0].split('-')[0];
                    
                    const dateObj = new Date(datePart);
                    const day = String(dateObj.getDate()).padStart(2, '0');
                    const month = String(dateObj.getMonth() + 1).padStart(2, '0');
                    const year = dateObj.getFullYear();
                    const formattedDate = `${{day}}.${{month}}.${{year}}`;
                    
                    document.getElementById('det-time').innerHTML = `
                        <strong>Date:</strong> ${{formattedDate}}<br>
                        <strong>Time:</strong> ${{timePart}} ${{det.timezone}}
                    `;
                    
                    detailsEl.style.display = 'block';
                    statusEl.textContent = 'Loaded';
                    
                    const progress = ((index + 1) / audioFiles.length * 100);
                    progressBar.style.width = progress + '%';
                    progressText.textContent = (index + 1) + ' / ' + audioFiles.length;
                    
                    updateButtons();
                }}
                
                player.addEventListener('ended', () => {{
                    const det = audioFiles[currentIndex];
                    const recentItem = `✓ #${{det.id}} - ${{det.name}} (${{det.confidence.toFixed(1)}}%)`;
                    recentPlayed.unshift(recentItem);
                    if (recentPlayed.length > 10) recentPlayed.pop();
                    updateRecentList();
                    
                    if (currentIndex < audioFiles.length - 1) {{
                        currentIndex++;
                        loadDetection(currentIndex);
                        player.play();
                    }} else {{
                        isPlaying = false;
                        statusEl.textContent = '✅ Playback finished!';
                        btnPlay.textContent = '▶ Play';
                    }}
                }});
                
                player.addEventListener('play', () => {{
                    isPlaying = true;
                    statusEl.textContent = '▶ Playing...';
                    btnPlay.textContent = '⏸ Pause';
                }});
                
                player.addEventListener('pause', () => {{
                    if (!player.ended) {{
                        statusEl.textContent = '⏸ Paused';
                        btnPlay.textContent = '▶ Resume';
                    }}
                }});
                
                function updateRecentList() {{
                    if (recentPlayed.length === 0) {{
                        recentItems.innerHTML = '<div class="status-text">No items played yet</div>';
                    }} else {{
                        recentItems.innerHTML = recentPlayed.map(item => 
                            `<div class="recent-item">${{item}}</div>`
                        ).join('');
                    }}
                }}
                
                function updateButtons() {{
                    document.getElementById('btn-prev').disabled = currentIndex === 0;
                    document.getElementById('btn-next').disabled = currentIndex >= audioFiles.length - 1;
                }}
                
                function playPause() {{
                    if (player.paused) {{
                        if (currentIndex === 0 && !detailsEl.style.display) {{
                            loadDetection(0);
                        }}
                        player.play();
                    }} else {{
                        player.pause();
                    }}
                }}
                
                function previous() {{
                    if (currentIndex > 0) {{
                        loadDetection(currentIndex - 1);
                        player.play();
                    }}
                }}
                
                function next() {{
                    if (currentIndex < audioFiles.length - 1) {{
                        loadDetection(currentIndex + 1);
                        player.play();
                    }}
                }}
                
                function stop() {{
                    player.pause();
                    player.currentTime = 0;
                    isPlaying = false;
                    statusEl.textContent = 'Stopped';
                    btnPlay.textContent = '▶ Play';
                }}
                
                if (audioFiles.length > 0) {{
                    loadDetection(0);
                    updateButtons();
                }} else {{
                    statusEl.textContent = 'No detections to play';
                }}
            </script>
        </body>
        </html>
        """
        
        st.components.v1.html(html, height=700, scrolling=True)
        
    except Exception as e:
        st.error(f"❌ Failed to create player: {e}")
        logger.exception("Player creation failed")
        
        
        
