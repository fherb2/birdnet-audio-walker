"""
Activity Heatmap Page - Temporal distribution of bird detections (Altair version)
"""

import streamlit as st
from pathlib import Path
from datetime import datetime, time as dt_time, timedelta
from typing import List, Dict
import pandas as pd
import altair as alt
import numpy as np
from loguru import logger

from shared.db_queries import get_analysis_config, query_detections, get_recording_date_range, search_species_in_list
from streamlit_searchbox import st_searchbox


# =============================================================================
# CONSTANTS
# =============================================================================

MIN_COLORSCALE_MAX = 4  # Minimum value for colorscale maximum
HEATMAP_CELL_SIZE = 12    # Cell size in pixels (square)


# =============================================================================
# DIALOG FUNCTION
# =============================================================================

@st.dialog("🎵 Play Detections", width="large")
def show_play_dialog(date, halfhour_idx, cell_value, cell_count, species_filter, db_path):
    """
    Show modal dialog with cell details and audio player.
    
    Args:
        date: Date object of clicked cell
        halfhour_idx: Halfhour index (0-47)
        cell_value: Sum of confidences or count
        cell_count: Number of detections
        species_filter: Current species filter (or None)
        db_path: Path to database
    """
    from datetime import timedelta
    from birdnet_play.player import AudioPlayer
    import base64
    import json
    
    hour = halfhour_idx // 2
    minute = "00" if halfhour_idx % 2 == 0 else "30"
    time_start = dt_time(hour, int(minute), 0)
    
    # Calculate end time
    if minute == "00":
        time_end = dt_time(hour, 29, 59)
    else:
        time_end = dt_time(hour, 59, 59)
    
    st.markdown(f"**📅 Date:** {date.day}.{date.month}.{date.year}")
    st.markdown(f"**🕐 Time:** {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}")
    
    if species_filter:
        st.markdown(f"**🔍 Species:** {species_filter}")
    else:
        st.markdown("**🔍 Species:** All species")
    
    st.divider()
    
    st.subheader("📊 Detections in this cell")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Count", f"{cell_count}")
    with col2:
        if st.session_state.get('heatmap_weight_confidence', True):
            st.metric("Total Conf.", f"{cell_value:.2f}")
        else:
            st.metric("Count", f"{int(cell_value)}")
    with col3:
        if cell_count > 0:
            avg_conf = cell_value / cell_count if st.session_state.get('heatmap_weight_confidence', True) else 1.0
            st.metric("Avg Conf.", f"{avg_conf:.2f}")
        else:
            st.metric("Avg Conf.", "-")
    
    st.divider()
    
    # Load detections for this time window
    with st.spinner("Loading detections..."):
        try:
            # Convert confidence filter (same as main page)
            min_conf_filter = st.session_state.get('page3_filter_confidence', '70%')
            if min_conf_filter == "All":
                min_confidence = None
            else:
                min_confidence = int(min_conf_filter.rstrip('%')) / 100

            # Query detections (max 25, sorted by confidence DESC)
            # Use time_range parameter for half-hour window
            detections = query_detections(
                db_path,
                species=species_filter,
                date_from=date,
                date_to=date,
                time_range=(time_start, time_end),
                min_confidence=min_confidence,
                limit=25,
                offset=0,
                sort_by="confidence",
                sort_order="desc"
            )
            
            if not detections:
                st.warning("⚠️ No detections found in this time window")
                return
            
            st.success(f"✅ Loaded {len(detections)} detection(s) (max 25, highest confidence)")
            
        except Exception as e:
            st.error(f"❌ Error loading detections: {e}")
            logger.exception("Query failed in dialog")
            return
    
    st.divider()
    
    # Generate audio files
    with st.spinner("Preparing audio files..."):
        try:
            player = AudioPlayer(db_path, pm_seconds=0.5)
            audio_files = []
            
            progress_bar = st.progress(0, text="Preparing audio files...")
            
            for i, det in enumerate(detections):
                try:
                    audio_bytes = player.prepare_detection_audio_simple(det, pm_seconds=0.5)
                    audio_b64 = base64.b64encode(audio_bytes.read()).decode()
                    conf_pct = det['confidence'] * 100
                    
                    audio_files.append({
                        'id': det['detection_id'],
                        'name': det.get('local_name', det['scientific_name']),
                        'scientific': det['scientific_name'],
                        'confidence': conf_pct,
                        'time': det['segment_start_local'],
                        'audio_data': audio_b64
                    })
                    
                    progress = (i + 1) / len(detections)
                    progress_bar.progress(progress, text=f"Preparing audio... {i+1}/{len(detections)}")
                    
                except Exception as e:
                    logger.error(f"Failed to prepare detection #{det['detection_id']}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            progress_bar.empty()
            
            if not audio_files:
                st.error("❌ Failed to prepare audio files")
                return
            
        except Exception as e:
            st.error(f"❌ Error preparing audio: {e}")
            logger.exception("Audio preparation failed in dialog")
            return
    
    # Embedded HTML Audio Player
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
                max-width: 100%;
                margin: 0;
                padding: 10px;
            }}
            #now-playing {{
                background: #262730;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
                border-left: 4px solid #ff4b4b;
            }}
            #now-playing h3 {{
                margin-top: 0;
                color: #ff4b4b;
                font-size: 16px;
            }}
            .info-row {{
                margin: 6px 0;
                font-size: 13px;
            }}
            .info-label {{
                color: #888;
                display: inline-block;
                width: 100px;
            }}
            .progress {{
                width: 100%;
                height: 6px;
                background: #444;
                border-radius: 3px;
                margin: 10px 0;
                overflow: hidden;
            }}
            .progress-bar {{
                height: 100%;
                background: linear-gradient(90deg, #ff4b4b, #ff6b6b);
                border-radius: 3px;
                width: 0%;
                transition: width 0.3s ease;
            }}
            #audio-player {{
                width: 100%;
                margin: 10px 0;
                border-radius: 4px;
            }}
            .controls {{
                display: flex;
                gap: 8px;
                margin: 15px 0;
                flex-wrap: wrap;
            }}
            button {{
                padding: 10px 20px;
                font-size: 14px;
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
            .status-text {{
                font-size: 12px;
                color: #888;
                margin: 8px 0;
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
                        <span id="det-confidence">-</span>
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
        </div>
        
        <script>
            const audioFiles = {audio_data_js};
            let currentIndex = 0;
            
            const player = document.getElementById('audio-player');
            const statusEl = document.getElementById('status');
            const detailsEl = document.getElementById('current-details');
            const progressBar = document.getElementById('progress-bar');
            const progressText = document.getElementById('progress-text');
            const btnPlay = document.getElementById('btn-play');
            
            function loadDetection(index) {{
                if (index < 0 || index >= audioFiles.length) return;
                
                currentIndex = index;
                const det = audioFiles[index];
                
                player.src = 'data:audio/mp3;base64,' + det.audio_data;
                
                document.getElementById('det-id').textContent = '#' + det.id;
                document.getElementById('det-species').textContent = det.name + ' (' + det.scientific + ')';
                document.getElementById('det-confidence').textContent = det.confidence.toFixed(1) + '%';
                
                detailsEl.style.display = 'block';
                statusEl.textContent = 'Loaded';
                
                const progress = ((index + 1) / audioFiles.length * 100);
                progressBar.style.width = progress + '%';
                progressText.textContent = (index + 1) + ' / ' + audioFiles.length;
                
                updateButtons();
            }}
            
            player.addEventListener('ended', () => {{
                if (currentIndex < audioFiles.length - 1) {{
                    currentIndex++;
                    loadDetection(currentIndex);
                    player.play();
                }} else {{
                    statusEl.textContent = '✅ Playback finished!';
                    btnPlay.textContent = '▶ Play';
                }}
            }});
            
            player.addEventListener('play', () => {{
                statusEl.textContent = '▶ Playing...';
                btnPlay.textContent = '⏸ Pause';
            }});
            
            player.addEventListener('pause', () => {{
                if (!player.ended) {{
                    statusEl.textContent = '⏸ Paused';
                    btnPlay.textContent = '▶ Resume';
                }}
            }});
            
            function updateButtons() {{
                document.getElementById('btn-prev').disabled = currentIndex === 0;
                document.getElementById('btn-next').disabled = currentIndex >= audioFiles.length - 1;
            }}
            
            function playPause() {{
                if (player.paused) {{
                    if (currentIndex === 0 && detailsEl.style.display === 'none') {{
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
    
    st.components.v1.html(html, height=400, scrolling=True)
    
    st.divider()
    
        
        

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Activity Heatmap - BirdNET",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🦜 BirdNET Activity Heatmap")
st.header("📊 Temporal Distribution (Altair)")

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

language_code = get_analysis_config(db_path, 'local_name_shortcut')
if not language_code:
    language_code = 'de'

st.markdown(f"**🌐 Language:** {language_code}")
st.markdown(f"**📂 Database:** `{db_path.name}`")
st.divider()


# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def init_filter_state():
    """Initialize filter session state with defaults for Page 3 (shared across pages)."""
    if 'filter_species' not in st.session_state:
        st.session_state['filter_species'] = ""
    if 'page3_filter_date_from' not in st.session_state or 'page3_filter_date_to' not in st.session_state:
        min_date, max_date = get_recording_date_range(db_path)
        st.session_state['page3_filter_date_from'] = min_date.date() if min_date else None
        st.session_state['page3_filter_date_to'] = max_date.date() if max_date else None
    if 'page3_filter_confidence' not in st.session_state:
        st.session_state['page3_filter_confidence'] = "70%"


def init_heatmap_state():
    """Initialize heatmap-specific options."""
    if 'heatmap_colormap' not in st.session_state:
        st.session_state['heatmap_colormap'] = "turbo"
    if 'heatmap_weight_confidence' not in st.session_state:
        st.session_state['heatmap_weight_confidence'] = True


init_filter_state()
init_heatmap_state()


# =============================================================================
# SIDEBAR: HEATMAP OPTIONS
# =============================================================================

st.sidebar.title("📊 Heatmap Options")

colormap_options = [
    "inferno",
    "viridis", 
    "plasma",
    "magma",
    "turbo",
    "blues",
    "greens",
    "reds",
    "oranges",
    "purples",
    "greys",
    "blueorange",
    "redyellowblue",
    "redyellowgreen",
    "spectral",
    "rainbow"
]

current_colormap_idx = colormap_options.index(st.session_state['heatmap_colormap']) \
    if st.session_state['heatmap_colormap'] in colormap_options else 0

selected_colormap = st.sidebar.selectbox(
    "Colormap",
    options=colormap_options,
    index=current_colormap_idx,
    key="sidebar_colormap"
)
st.session_state['heatmap_colormap'] = selected_colormap

weight_by_conf = st.sidebar.checkbox(
    "Weight by Confidence",
    value=st.session_state['heatmap_weight_confidence'],
    key="sidebar_weight_conf",
    help="If checked: sum of confidences, otherwise: count of detections"
)
st.session_state['heatmap_weight_confidence'] = weight_by_conf

st.sidebar.divider()
st.sidebar.info(
    "**Heatmap Guide:**\n"
    "- Horizontal: Days in selected range\n"
    "- Vertical: 30-minute intervals (00:00-23:30)\n"
    "- Click on cell to play detections\n"
    "- Hover for details"
)


# =============================================================================
# FILTER SECTION
# =============================================================================

st.subheader("🔍 Search Filters")

def search_species_callback(search_term: str) -> List[str]:
    """Callback for searchbox - searches in species_list."""
    return search_species_in_list(db_path, search_term, limit=10)

col1, col2 = st.columns([3, 1])
with col1:
    current_species = st.session_state.get('filter_species', '')
    
    if current_species:
        col_a, col_b = st.columns([4, 1])
        with col_a:
            st.info(f"🔍 Selected: **{current_species}**")
        with col_b:
            if st.button("✕", key="clear_species", help="Clear species filter"):
                st.session_state['filter_species'] = ''
                st.rerun()
    else:
        selected_species = st_searchbox(
            search_species_callback,
            key="species_searchbox",
            placeholder="Search species... (type to filter)",
            clear_on_submit=False
        )
        
        if selected_species:
            if '(' in selected_species:
                scientific_name = selected_species.split(' (')[0]
            else:
                scientific_name = selected_species
            
            st.session_state['filter_species'] = scientific_name

with col2:
    species_for_xc = st.session_state.get('filter_species', '')
    
    if species_for_xc:
        xc_query = species_for_xc.replace(' ', '+')
        xc_url = f"https://xeno-canto.org/explore?query={xc_query}&view=3"
        
        st.link_button(
            "🔊 Xeno-Canto",
            xc_url,
            help=f"Open {species_for_xc} in Xeno-Canto (new tab)",
            width='stretch'
        )
    else:
        st.button(
            "🔊 Xeno-Canto",
            disabled=True,
            help="Select a species first",
            width='stretch'
        )

col1, col2, col3 = st.columns(3)
with col1:
    date_from = st.date_input(
        "Date From",
        value=st.session_state['page3_filter_date_from'],
        key="input_date_from"
    )
    st.session_state['page3_filter_date_from'] = date_from

with col2:
    date_to = st.date_input(
        "Date To",
        value=st.session_state['page3_filter_date_to'],
        key="input_date_to"
    )
    st.session_state['page3_filter_date_to'] = date_to

with col3:
    conf_options = ["All"] + [f"{i}%" for i in range(5, 100, 5)]
    current_conf_idx = 0
    if st.session_state['page3_filter_confidence'] in conf_options:
        current_conf_idx = conf_options.index(st.session_state['page3_filter_confidence'])
    
    conf_selected = st.selectbox(
        "Min Confidence",
        options=conf_options,
        index=current_conf_idx,
        key="input_confidence"
    )
    st.session_state['page3_filter_confidence'] = conf_selected

if st.button("🔍 **Apply Filters**", type="primary", width='stretch'):
    st.session_state['heatmap_filters_applied'] = True
    st.rerun()

st.divider()


# =============================================================================
# LOAD AND PROCESS DATA
# =============================================================================

if not st.session_state.get('heatmap_filters_applied', False):
    st.info("👆 Configure filters above and click **'Apply Filters'** to generate heatmap")
    st.stop()

min_confidence = None if st.session_state['page3_filter_confidence'] == "All" else \
    int(st.session_state['page3_filter_confidence'].rstrip('%')) / 100

with st.spinner("Loading detections for heatmap..."):
    try:
        detections = query_detections(
            db_path,
            species=st.session_state['filter_species'] if st.session_state['filter_species'] else None,
            date_from=datetime.combine(st.session_state['page3_filter_date_from'], dt_time(0, 0)) if st.session_state['page3_filter_date_from'] else None,
            date_to=datetime.combine(st.session_state['page3_filter_date_to'], dt_time(23, 59)) if st.session_state['page3_filter_date_to'] else None,
            min_confidence=min_confidence,
            limit=999999,
            offset=0,
            sort_by="time",
            sort_order="asc"
        )
        
        if not detections:
            st.warning("⚠️ No detections found matching filters")
            st.stop()
        
        logger.info(f"Loaded {len(detections)} detections for heatmap")
        
    except Exception as e:
        st.error(f"❌ Error loading detections: {e}")
        logger.exception("Query failed")
        st.stop()


# =============================================================================
# DATA AGGREGATION
# =============================================================================

def aggregate_heatmap_data(detections: List[Dict], weight_by_confidence: bool) -> pd.DataFrame:
    """Aggregate detections into DataFrame for heatmap."""
    aggregated = []
    
    for det in detections:
        timestamp_str = det['segment_start_local']
        timestamp = datetime.fromisoformat(timestamp_str)
        
        date = timestamp.date()
        hour = timestamp.hour
        minute = timestamp.minute
        
        halfhour_idx = hour * 2 + (1 if minute >= 30 else 0)
        value = det['confidence'] if weight_by_confidence else 1.0
        
        aggregated.append({
            'date': date,
            'halfhour_idx': halfhour_idx,
            'value': value
        })
    
    df = pd.DataFrame(aggregated)
    df_grouped = df.groupby(['date', 'halfhour_idx'])['value'].sum().reset_index()
    df_counts = df.groupby(['date', 'halfhour_idx']).size().reset_index(name='count')
    df_result = df_grouped.merge(df_counts, on=['date', 'halfhour_idx'])
    
    return df_result

with st.spinner("Aggregating data..."):
    df_agg = aggregate_heatmap_data(detections, st.session_state['heatmap_weight_confidence'])
    
    if df_agg.empty:
        st.warning("⚠️ No data to display")
        st.stop()


# =============================================================================
# CREATE ALTAIR DATA (LONG FORM)
# =============================================================================

def create_altair_data(df_agg: pd.DataFrame, date_from, date_to) -> pd.DataFrame:
    """Create long-form data for Altair with ALL dates in range."""
    from datetime import timedelta
    
    dates = []
    current_date = date_from
    while current_date <= date_to:
        dates.append(current_date)
        current_date += timedelta(days=1)
    
    data = []
    for halfhour_idx in range(48):
        for date in dates:
            mask = (df_agg['date'] == date) & (df_agg['halfhour_idx'] == halfhour_idx)
            
            if mask.any():
                value = df_agg.loc[mask, 'value'].values[0]
                count = df_agg.loc[mask, 'count'].values[0]
            else:
                value = 0.0
                count = 0
            
            hour = halfhour_idx // 2
            minute = "00" if halfhour_idx % 2 == 0 else "30"
            time_label = f"{hour:02d}:{minute}"
            date_label = f"{date.day}.{date.month}."
            
            is_monday = date.weekday() == 0
            date_display = date_label if is_monday else ""
            
            show_time_label = (hour % 3 == 0 and minute == "00")
            time_display = time_label if show_time_label else ""
            
            avg_conf = value / count if count > 0 else 0.0
            
            value_display = value if value > 0 else None
            
            data.append({
                'date': date,
                'date_label': date_label,
                'date_display': date_display,
                'date_idx': dates.index(date),
                'halfhour_idx': halfhour_idx,
                'time_label': time_label,
                'time_display': time_display,
                'value': value_display,
                'value_raw': value,
                'count': count,
                'avg_conf': avg_conf,
                'tooltip': f"{date_label} {time_label} | conf/det: {value:.1f}/{count} = {avg_conf:.2f}" if count > 0 else f"{date_label} {time_label} | No detections"
            })
    
    return pd.DataFrame(data), dates


altair_df, dates = create_altair_data(
    df_agg,
    st.session_state['page3_filter_date_from'],
    st.session_state['page3_filter_date_to']
)

max_value = altair_df['value_raw'].max()
colorscale_max = max(max_value, MIN_COLORSCALE_MAX)


# =============================================================================
# CREATE ALTAIR CHART
# =============================================================================

st.subheader(f"📊 Activity Heatmap ({len(detections)} detections)")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Date Range", f"{dates[0]} to {dates[-1]}")
with col2:
    st.metric("Max Value", f"{max_value:.1f}")
with col3:
    mode_text = "Sum of Confidences" if st.session_state['heatmap_weight_confidence'] else "Count"
    st.metric("Mode", mode_text)

n_cols = len(dates)
n_rows = 48
chart_width = n_cols * HEATMAP_CELL_SIZE
chart_height = n_rows * HEATMAP_CELL_SIZE



# Define selection for click events
selection = alt.selection_point(fields=['date_idx', 'halfhour_idx'])

# Create date labels list (only Mondays)
date_labels_list = []
for i, date in enumerate(dates):
    if date.weekday() == 0:  # Monday
        date_labels_list.append(f"{date.day}.{date.month}.")
    else:
        date_labels_list.append("")

# Create time labels list (every 3 hours)
time_labels_list = []
for i in range(48):
    hour = i // 2
    minute = "00" if i % 2 == 0 else "30"
    if hour % 3 == 0 and minute == "00":
        time_labels_list.append(f"{hour:02d}:00")
    else:
        time_labels_list.append("")

chart = alt.Chart(altair_df).mark_rect(
    stroke=None
).encode(
    x=alt.X(
        'date_idx:O',
        axis=alt.Axis(
            title='Date',
            values=list(range(len(dates))),
            labelExpr=f"['', {','.join([repr(l) for l in date_labels_list])}][datum.value] || ''",
            labelAngle=0
        )
    ),
    y=alt.Y(
        'halfhour_idx:O',
        axis=alt.Axis(
            title='Time of Day',
            values=list(range(48)),
            labelExpr=f"['', {','.join([repr(l) for l in time_labels_list])}][datum.value] || ''"
        ),
        sort=alt.SortOrder('descending')
    ),
    color=alt.condition(
        alt.datum.value_raw == 0,
        alt.value('white'),
        alt.Color(
            'value_raw:Q',
            scale=alt.Scale(
                scheme=st.session_state['heatmap_colormap'],
                domain=[0.01, colorscale_max]
            ),
            legend=alt.Legend(title='Value')
        )
    ),
    tooltip=[
        alt.Tooltip('date_label:N', title='Date'),
        alt.Tooltip('time_label:N', title='Time'),
        alt.Tooltip('value_raw:Q', title='Value', format='.2f'),
        alt.Tooltip('count:Q', title='Count'),
        alt.Tooltip('avg_conf:Q', title='Avg Conf', format='.2f')
    ]
).add_params(
    selection
).properties(
    width=chart_width,
    height=chart_height
).configure_axis(
    grid=False
)

event = st.altair_chart(chart, width='stretch', on_select="rerun", key="heatmap_chart")

if event and 'selection' in event:
    # Altair selection format: event['selection']['param_1']
    selection_data = event['selection']
    
    # Get first selection parameter (usually 'param_1')
    param_key = list(selection_data.keys())[0] if selection_data else None
    
    if param_key and selection_data[param_key]:
        points = selection_data[param_key]
        
        if points and len(points) > 0:
            selected_point = points[0]
            
            clicked_date_idx = selected_point.get('date_idx')
            clicked_halfhour = selected_point.get('halfhour_idx')
            
            if clicked_date_idx is not None and clicked_halfhour is not None:
                clicked_date = dates[clicked_date_idx]
                
                # Find cell values from DataFrame
                mask = (altair_df['date_idx'] == clicked_date_idx) & (altair_df['halfhour_idx'] == clicked_halfhour)
                selected_row = altair_df[mask].iloc[0]
                
                cell_value = selected_row['value_raw']
                cell_count = selected_row['count']
                
                show_play_dialog(
                    clicked_date,
                    clicked_halfhour,
                    cell_value,
                    cell_count,
                    st.session_state.get('filter_species', None),
                    db_path
                )


# =============================================================================
# EXPORT SECTION
# =============================================================================

st.divider()
st.subheader("💾 Export")

col1, col2 = st.columns(2)

with col1:
    if st.button("💾 Export as PNG", width='stretch'):
        try:
            chart_save = chart.properties(
                width=chart_width,
                height=chart_height
            )
            
            species_part = st.session_state['filter_species'].replace(' ', '_') if st.session_state['filter_species'] else 'all_species'
            filename = f"heatmap_{species_part}_{dates[0]}_{dates[-1]}.png"
            
            chart_save.save(filename, format='png', scale_factor=2.0)
            
            with open(filename, 'rb') as f:
                st.download_button(
                    label="⬇️ Download PNG",
                    data=f,
                    file_name=filename,
                    mime="image/png",
                    width='stretch'
                )
            
        except Exception as e:
            st.error(f"❌ PNG export failed: {e}")
            logger.exception("PNG export failed")
            st.info("Note: PNG export requires additional packages. Try: pip install altair_saver pillow")

with col2:
    if st.button("💾 Export as CSV", width='stretch'):
        try:
            df_export = altair_df.pivot(index='halfhour_idx', columns='date_label', values='value_raw')
            df_export.insert(0, 'Time', [f"{i//2:02d}:{('00' if i%2==0 else '30')}" for i in range(48)])
            
            csv = df_export.to_csv(index=False)
            
            species_part = st.session_state['filter_species'].replace(' ', '_') if st.session_state['filter_species'] else 'all_species'
            filename = f"heatmap_{species_part}_{dates[0]}_{dates[-1]}.csv"
            
            st.download_button(
                label="⬇️ Download CSV",
                data=csv,
                file_name=filename,
                mime="text/csv",
                width='stretch'
            )
            
        except Exception as e:
            st.error(f"❌ CSV export failed: {e}")
            logger.exception("CSV export failed")