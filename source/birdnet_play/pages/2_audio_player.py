"""
Audio Player Page - Filter detections and play audio
"""

import streamlit as st
from pathlib import Path
from datetime import datetime, time as dt_time, timedelta
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
    initial_sidebar_state="expanded"  # Show sidebar on this page
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
# FILTER SIDEBAR
# =============================================================================

st.sidebar.title("🔍 Filter")

# Species filter
species = st.sidebar.text_input(
    "Species",
    key=f"species_{hash(str(db_path))}",
    help="Search by scientific, local, or Czech name (partial match). Press ENTER to apply."
)

# Date filters
st.sidebar.subheader("Date Range")
col1, col2 = st.sidebar.columns(2)

with col1:
    date_from = st.date_input("From", value=None, key=f"date_from_{hash(str(db_path))}")
with col2:
    date_to = st.date_input("To", value=None, key=f"date_to_{hash(str(db_path))}")

# Time of day filter
st.sidebar.subheader("Time of Day")
use_time_filter = st.sidebar.checkbox("Enable time filter", key=f"use_time_filter_{hash(str(db_path))}")

time_start = None
time_end = None

if use_time_filter:
    col1, col2 = st.sidebar.columns(2)
    with col1:
        time_start = st.time_input("Start", value=dt_time(0, 0), key=f"time_start_{hash(str(db_path))}")
    with col2:
        time_end = st.time_input("End", value=dt_time(23, 59), key=f"time_end_{hash(str(db_path))}")
    
    # Auto-correct: time_end must be >= time_start + 1 minute
    if time_start and time_end:
        dt_start = datetime.combine(datetime.today(), time_start)
        dt_end = datetime.combine(datetime.today(), time_end)
        if dt_end < dt_start + timedelta(minutes=1):
            time_end = (dt_start + timedelta(minutes=1)).time()

# Confidence filter
conf_options = [f"{i}%" for i in range(5, 100, 5)]
conf_selected = st.sidebar.selectbox(
    "Min Confidence",
    options=["All"] + conf_options,
    index=14,  # 70%
    key=f"confidence_{hash(str(db_path))}",
    help="Minimum confidence threshold"
)
min_confidence = None if conf_selected == "All" else int(conf_selected.rstrip('%')) / 100

# Limit and offset
limit = st.sidebar.number_input(
    "Limit",
    min_value=1,
    max_value=1000,
    value=10,
    key=f"limit_{hash(str(db_path))}",
    help="Maximum number of detections to load"
)

offset = st.sidebar.number_input(
    "Offset",
    min_value=0,
    value=0,
    step=10,
    key=f"offset_{hash(str(db_path))}",
    help="Start position (for pagination)"
)

# PM buffer
pm_seconds = st.sidebar.slider(
    "PM Buffer (seconds)",
    min_value=0.0,
    max_value=5.0,
    value=1.0,
    step=0.5,
    key=f"pm_seconds_{hash(str(db_path))}",
    help="Plus/Minus buffer around detection"
)

# Options
st.sidebar.subheader("Options")
use_sci = st.sidebar.checkbox(
    "Scientific Names",
    key=f"use_sci_{hash(str(db_path))}",
    help="Use scientific names for TTS instead of local names"
)

disable_tts = st.sidebar.checkbox(
    "Disable Voice Announcements",
    key=f"disable_tts_{hash(str(db_path))}",
    help="Disable TTS announcements (only play bird sounds)"
)

shuffle = st.sidebar.checkbox(
    "Shuffle",
    key=f"shuffle_{hash(str(db_path))}",
    help="Randomize playback order"
)

# Cache-Clear Button
if st.sidebar.button("🔄 Clear Audio Cache"):
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith('audio_cache_')]
    for key in keys_to_remove:
        del st.session_state[key]
    st.sidebar.success("Cache cleared!")
    st.rerun()


# =============================================================================
# CREATE DETECTION FILTER
# =============================================================================

detection_filter = DetectionFilter(
    species=species if species else None,
    date_from=datetime.combine(date_from, dt_time(0, 0)) if date_from else None,
    date_to=datetime.combine(date_to, dt_time(23, 59)) if date_to else None,
    time_start=time_start,
    time_end=time_end,
    min_confidence=min_confidence,
    limit=limit,
    offset=offset,
    shuffle=shuffle,
    pm_seconds=pm_seconds,
    use_sci=use_sci
)

# Validate filter
error = detection_filter.validate()
if error:
    st.sidebar.error(f"❌ Invalid filter: {error}")
    st.stop()


# =============================================================================
# LOAD DETECTIONS
# =============================================================================

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
        st.session_state['disable_tts'] = disable_tts
        
    except Exception as e:
        st.error(f"❌ Error loading detections: {e}")
        logger.exception("Query failed")
        st.stop()


# =============================================================================
# DISPLAY DETECTIONS
# =============================================================================

detections = st.session_state['detections']
filter_context = detection_filter.get_filter_context()

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


# =============================================================================
# EXPORT BUTTONS
# =============================================================================

st.divider()
col1, col2, col3 = st.columns([2, 1, 1])

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
                    pm_seconds,
                    use_sci,
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
                    pm_seconds,
                    use_sci,
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

with st.spinner("Preparing audio files..."):
    try:
        player = AudioPlayer(db_path, pm_seconds)
        
        # Generate cache key
        cache_key = f"audio_cache_{hash(tuple(d['detection_id'] for d in detections))}"
        
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
                        language_code,
                        filter_context,
                        use_sci,
                        disable_tts
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
        
        # Create HTML player
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
