"""
Audio Player page for BirdNET Play.

Covers:
- Filter section (species autocomplete, date, time, confidence, limit, offset, sort)
- Apply Filters button → queries detections
- Detection statistics (single audio length, outputs/min, total time)
- Detection list (collapsible)
- Audio options (collapsible expansion panel)
- Export buttons (WAV, MP3)
- HTML/JS audio player with incremental playlist loading
- Background audio generation task (asyncio + run_in_executor)
"""

import asyncio
import base64
import json
import tempfile
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from loguru import logger
from nicegui import ui, app as nicegui_app, context as _ctx
        

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.species_search import SpeciesSearch
from shared.db_queries import (
    get_analysis_config,
    query_detections,
    get_recording_date_range,
)
from ..filters import DetectionFilter
from ..player import AudioPlayer, export_detections, export_detections_mp3


# ---------------------------------------------------------------------------
# Page registration
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


@ui.page('/audio-player')
async def audio_player() -> None:
    state = _get_state()
    create_layout(state)

    if state.active_db is None or not state.active_db.exists():
        ui.label('⚠️ No database selected. Please open a database first.') \
            .classes('text-orange-7 q-ma-md')
        ui.button('📂 Go to Database Overview',
                  on_click=lambda: ui.navigate.to('/')) \
            .props('no-caps')
        return

    # -----------------------------------------------------------------------
    # Page-local state
    # -----------------------------------------------------------------------
    page: Dict = {
        'generation_task': None,   # asyncio.Task or None
    }

    # -----------------------------------------------------------------------
    # Section: Filters
    # -----------------------------------------------------------------------
    ui.label('🔍 Search Filters').classes('text-h6 q-mt-md q-mb-xs')

    # Species + Xeno-Canto row
    with ui.row().classes('w-full items-start gap-3'):
        with ui.column().classes('flex-grow'):
            species_search = SpeciesSearch(
                db_path=state.active_db,
                on_select=lambda s: setattr(state, 'ap_filter_species', s),
                initial_value=state.ap_filter_species,
            )

        def _open_xc():
            if state.ap_filter_species:
                q = state.ap_filter_species.replace(' ', '+')
                ui.navigate.to(
                    f'https://xeno-canto.org/explore?query={q}&view=3',
                    new_tab=True,
                )

        xc_btn = ui.button('🔊 Xeno-Canto', on_click=_open_xc) \
            .props('no-caps flat')
        if not state.ap_filter_species:
            xc_btn.disable()

        # Keep XC button in sync with species selection
        def _on_species(sci: Optional[str]):
            state.ap_filter_species = sci
            xc_btn.enable() if sci else xc_btn.disable()

        species_search._on_select = _on_species

    # Date range
    min_date, max_date = get_recording_date_range(state.active_db)
    if state.ap_filter_date_from is None and min_date:
        state.ap_filter_date_from = min_date.date()
    if state.ap_filter_date_to is None and max_date:
        state.ap_filter_date_to = max_date.date()

    with ui.row().classes('gap-4 items-end'):
        date_from = ui.date(value=str(state.ap_filter_date_from) if state.ap_filter_date_from else None) \
            .props('outlined dense label="Date From"')
        date_to = ui.date(value=str(state.ap_filter_date_to) if state.ap_filter_date_to else None) \
            .props('outlined dense label="Date To"')

    # Time filter (optional)
    use_time = ui.checkbox(
        'Enable Time Filter',
        value=state.ap_filter_use_time,
    )
    with ui.row().classes('gap-4 items-end') as time_row:
        time_start = ui.time(value=state.ap_filter_time_start.strftime('%H:%M')) \
            .props('outlined dense label="Time Start"')
        time_end = ui.time(value=state.ap_filter_time_end.strftime('%H:%M')) \
            .props('outlined dense label="Time End"')
    time_row.bind_visibility_from(use_time, 'value')

    # Confidence / Limit / Offset / Sort
    conf_options = ['All'] + [f'{i}%' for i in range(5, 100, 5)]
    current_conf = (
        f'{int(state.ap_filter_confidence * 100)}%'
        if state.ap_filter_confidence is not None else 'All'
    )

    sort_labels = {
        'time':       'Time (oldest→newest)',
        'confidence': 'Confidence (high→low)',
        'id':         'ID (upwards)',
    }

    with ui.row().classes('gap-4 items-end'):
        conf_select = ui.select(
            options=conf_options,
            value=current_conf,
            label='Min Confidence',
        ).props('outlined dense').classes('w-32')

        limit_input = ui.number(
            label='Limit', value=state.ap_filter_limit,
            min=1, max=1000,
        ).props('outlined dense').classes('w-24')

        offset_input = ui.number(
            label='Offset', value=state.ap_filter_offset,
            min=0, step=10,
        ).props('outlined dense').classes('w-24')

        sort_select = ui.select(
            options=list(sort_labels.values()),
            value=sort_labels.get(state.ap_filter_sort, sort_labels['time']),
            label='Sort By',
        ).props('outlined dense').classes('w-56')

    # Apply Filters button
    apply_btn = ui.button(
        '🔍 Apply Filters',
        on_click=lambda: _apply_filters(),
    ).props('no-caps color=primary').classes('w-full q-mt-sm')

    ui.separator().classes('q-my-md')

    # -----------------------------------------------------------------------
    # Section: Results area (hidden until filters applied)
    # -----------------------------------------------------------------------
    with ui.column().classes('w-full gap-2') as results_col:
        results_col.set_visibility(state.ap_filters_applied)

        # Statistics row
        with ui.row().classes('gap-6') as stats_row:
            stat_length   = ui.column()
            stat_opm      = ui.column()
            stat_total    = ui.column()

        def _render_stat(col: ui.column, label: str, value: str) -> None:
            col.clear()
            with col:
                ui.label(label).classes('text-caption text-grey-6')
                ui.label(value).classes('text-body1 font-bold')

        def _update_stats() -> None:
            single = _calc_single_length(state)
            opm    = round(60.0 / single, 1) if single > 0 else 0
            total  = (len(state.detections) * single) / 60
            _render_stat(stat_length, 'Single Audio Length', f'{single:.1f}s')
            _render_stat(stat_opm,    'Outputs per Minute',  f'{opm:.1f}')
            _render_stat(stat_total,  'Total Playback Time',  f'{total:.1f} min')

        # Detection list (collapsible)
        with ui.expansion('📋 Detection List', value=False).classes('w-full'):
            det_list_col = ui.column().classes('w-full gap-0')

        def _refresh_detection_list() -> None:
            det_list_col.clear()
            with det_list_col:
                for i, det in enumerate(state.detections, 1):
                    conf = det['confidence'] * 100
                    name = det.get('local_name') or det['scientific_name']
                    ui.label(
                        f"{i}. #{det['detection_id']} – {name} "
                        f"({conf:.1f}%) – {det['segment_start_local']}"
                    ).classes('text-caption')

        ui.separator().classes('q-my-sm')

        # -----------------------------------------------------------------------
        # Section: Audio options (collapsible)
        # -----------------------------------------------------------------------
        with ui.expansion('🎵 Audio Options', value=False).classes('w-full'):
            with ui.column().classes('gap-3 q-pa-sm'):

                with ui.row().classes('gap-6 items-start'):
                    # TTS checkboxes
                    with ui.column().classes('gap-1'):
                        ui.label('Announcements').classes('text-caption text-grey-6')
                        say_number = ui.checkbox(
                            'Say Audio Number',
                            value=state.audio_say_number,
                        )
                        say_id = ui.checkbox(
                            'Say Database ID',
                            value=state.audio_say_id,
                        )
                        say_conf = ui.checkbox(
                            'Say Confidence',
                            value=state.audio_say_confidence,
                        )

                    # Bird name radio
                    with ui.column().classes('gap-1'):
                        ui.label('Say Bird Name').classes('text-caption text-grey-6')
                        bird_name_radio = ui.radio(
                            options={
                                'none':       'None',
                                'local':      'Local Name',
                                'scientific': 'Scientific Name',
                            },
                            value=state.audio_bird_name,
                        )

                with ui.row().classes('gap-6 items-start'):
                    # Speech speed
                    with ui.column().classes('gap-1 w-48'):
                        ui.label('Speech Speed').classes('text-caption text-grey-6')
                        speech_speed = ui.slider(
                            min=0.5, max=2.0, step=0.1,
                            value=state.audio_speech_speed,
                        )
                        ui.label().bind_text_from(
                            speech_speed, 'value',
                            backward=lambda v: f'{v:.1f}×'
                        ).classes('text-caption text-right')

                    # Speech loudness
                    with ui.column().classes('gap-1 w-48'):
                        ui.label('Speech Loudness (dB)').classes('text-caption text-grey-6')
                        speech_loud = ui.slider(
                            min=-10, max=4, step=1,
                            value=state.audio_speech_loudness,
                        )
                        ui.label().bind_text_from(
                            speech_loud, 'value',
                            backward=lambda v: f'{v:+d} dB'
                        ).classes('text-caption text-right')

                with ui.row().classes('gap-6 items-start'):
                    # Frame duration
                    with ui.column().classes('gap-1 w-48'):
                        ui.label('Audio Frame Duration (s)').classes('text-caption text-grey-6')
                        frame_dur = ui.slider(
                            min=0.5, max=6.0, step=0.5,
                            value=state.audio_frame_duration,
                        )
                        ui.label().bind_text_from(
                            frame_dur, 'value',
                            backward=lambda v: f'{v:.1f}s'
                        ).classes('text-caption text-right')

                    # Noise reduction
                    with ui.column().classes('gap-1'):
                        nr_check = ui.checkbox(
                            'Noise Reduction',
                            value=state.audio_noise_reduction,
                        )
                        with ui.column().classes('gap-1 w-48') as nr_strength_col:
                            ui.label('Strength').classes('text-caption text-grey-6')
                            _nr_steps = list(
                                np.logspace(np.log10(0.5), np.log10(1.0), 20)
                            )
                            _cur_idx = int(
                                np.argmin(
                                    np.abs(
                                        np.array(_nr_steps)
                                        - state.audio_noise_reduce_strength
                                    )
                                )
                            )
                            nr_slider = ui.slider(
                                min=0, max=19, step=1,
                                value=_cur_idx,
                            )
                            nr_caption = ui.label(
                                f'prop_decrease = {_nr_steps[_cur_idx]:.3f}'
                            ).classes('text-caption')

                            def _update_nr_caption(v):
                                nr_caption.set_text(
                                    f'prop_decrease = {_nr_steps[int(v)]:.3f}'
                                )

                            nr_slider.on('update:modelValue',
                                         lambda e: _update_nr_caption(e.args))

                        nr_strength_col.bind_visibility_from(nr_check, 'value')

                # Apply audio settings button
                # IMPORTANT: This invalidates the audio cache and triggers re-generation
                # if detections are already loaded.
                with ui.row().classes('gap-3 items-center'):
                    apply_audio_btn = ui.button(
                        '🎵 Apply Audio Settings',
                        on_click=lambda: _apply_audio_settings(),
                    ).props('no-caps color=secondary')

                    clear_cache_btn = ui.button(
                        '🔄 Clear Audio Cache',
                        on_click=lambda: _clear_cache(),
                    ).props('no-caps flat')

        ui.separator().classes('q-my-sm')

        # -----------------------------------------------------------------------
        # Section: Export buttons
        # -----------------------------------------------------------------------
        with ui.row().classes('gap-3'):
            ui.button('💾 Export as WAV',
                    on_click=lambda: _export_wav()).props('no-caps flat')
            ui.button('💾 Export as MP3',
                    on_click=lambda: _export_mp3()).props('no-caps flat')

        ui.separator().classes('q-my-sm')

        # -----------------------------------------------------------------------
        # Section: Audio player
        # -----------------------------------------------------------------------
        ui.label('🎵 Audio Player').classes('text-h6')

        # Progress bar shown during generation
        with ui.row().classes('items-center gap-2 w-full') as gen_progress_row:
            gen_progress_bar = ui.linear_progress(value=0).classes('flex-grow')
            gen_progress_label = ui.label('0 / 0').classes('text-caption w-16')
        gen_progress_row.set_visibility(False)

        # The HTML/JS player container
        # KNIFFLIG: Der Player wird als ui.html eingebettet. Er liest initial
        # aus window.audioFiles (JSON). Neue Einträge werden über
        # window.pendingAudioFiles nachgereicht (per ui.run_javascript aus dem
        # Python-Task). Ein setInterval im Player prüft alle 500ms ob neue
        # Einträge vorliegen und fügt sie der internen Playlist hinzu.
        # Damit kann der Nutzer bereits abspielen während noch generiert wird.
        player_container = ui.column().classes('w-full')
        player_container.set_visibility(False)

    # -----------------------------------------------------------------------
    # Helper: calculate single audio length
    # -----------------------------------------------------------------------
    def _calc_single_length(s: AppState) -> float:
        opts = s.get_audio_options()
        has_tts = (
            opts['bird_name_option'] != 'none'
            or opts['say_audio_number']
            or opts['say_id']
            or opts['say_confidence']
        )
        tts_est = (4.0 / opts['speech_speed']) if has_tts else 0.5
        return 1.0 + s.audio_frame_duration + 3.0 + s.audio_frame_duration + tts_est

    # -----------------------------------------------------------------------
    # Helper: build player HTML
    # -----------------------------------------------------------------------
    def _build_player_html(initial_files_json: str) -> str:
        return f"""
        <div id="bp-player" style="font-family: system-ui, sans-serif;
             background:#1a1a2e; color:#eee; padding:16px; border-radius:8px;
             max-width:860px;">
          <div style="background:#16213e; padding:14px; border-radius:6px;
               margin-bottom:12px; border-left:4px solid #e94560;">
            <div style="color:#e94560; font-weight:bold; margin-bottom:8px;">
              🔊 Now Playing
            </div>
            <div id="bp-status">Ready to play…</div>
            <div id="bp-details" style="display:none; margin-top:6px;
                 font-size:13px; line-height:1.6;">
              <span style="color:#aaa; display:inline-block; width:110px;">ID:</span>
              <span id="bp-id">–</span><br>
              <span style="color:#aaa; display:inline-block; width:110px;">Species:</span>
              <span id="bp-species">–</span><br>
              <span style="color:#aaa; display:inline-block; width:110px;">Confidence:</span>
              <span id="bp-conf">–</span><br>
              <span style="color:#aaa; display:inline-block; width:110px;">Time:</span>
              <span id="bp-time">–</span>
            </div>
            <div style="background:#333; height:6px; border-radius:3px;
                 margin:10px 0; overflow:hidden;">
              <div id="bp-prog" style="height:100%;
                   background:linear-gradient(90deg,#e94560,#ff6b81);
                   width:0%; transition:width .3s;"></div>
            </div>
            <div id="bp-prog-text" style="font-size:12px; color:#aaa;">
              0 / 0
            </div>
          </div>
          <audio id="bp-audio" controls style="width:100%; margin:8px 0;
                 border-radius:4px;"></audio>
          <div style="background:#16213e; padding:12px; border-radius:6px;
               max-height:220px; overflow-y:auto; margin-top:8px;">
            <div style="font-weight:bold; margin-bottom:6px;">
              📋 Recently Played
            </div>
            <div id="bp-recent">
              <span style="color:#777; font-size:13px;">No items played yet</span>
            </div>
          </div>
        </div>
        """
        
    def _build_player_js(initial_files_json: str) -> str:
        return f"""
          var audioFiles = {initial_files_json};
          var currentIndex = 0;
          var recentPlayed = [];
          var audio    = document.getElementById('bp-audio');
          var statusEl = document.getElementById('bp-status');
          var detailsEl = document.getElementById('bp-details');
          var progBar  = document.getElementById('bp-prog');
          var progText = document.getElementById('bp-prog-text');
          var recentEl = document.getElementById('bp-recent');

          window.pendingAudioFiles = [];
          setInterval(function() {{
            if (window.pendingAudioFiles && window.pendingAudioFiles.length > 0) {{
              audioFiles = audioFiles.concat(window.pendingAudioFiles);
              window.pendingAudioFiles = [];
              progText.textContent = (currentIndex + 1) + ' / ' + audioFiles.length;
            }}
          }}, 500);

          function loadDetection(idx) {{
            if (idx < 0 || idx >= audioFiles.length) return;
            currentIndex = idx;
            var det = audioFiles[idx];
            audio.src = 'data:audio/mp3;base64,' + det.audio_data;
            document.getElementById('bp-id').textContent = '#' + det.id;
            document.getElementById('bp-species').textContent =
              det.name + ' (' + det.scientific + ')';
            document.getElementById('bp-conf').textContent =
              det.confidence.toFixed(1) + '%';
            var parts = det.time.split('T');
            var d = new Date(parts[0]);
            document.getElementById('bp-time').textContent =
              d.getDate() + '.' + (d.getMonth()+1) + '.' + d.getFullYear()
              + '  ' + (parts[1] || '').split('+')[0].split('-')[0]
              + ' ' + (det.timezone || '');
            detailsEl.style.display = 'block';
            statusEl.textContent = 'Loaded';
            var pct = ((idx + 1) / audioFiles.length * 100);
            progBar.style.width = pct + '%';
            progText.textContent = (idx + 1) + ' / ' + audioFiles.length;
          }}

          audio.addEventListener('ended', function() {{
            var det = audioFiles[currentIndex];
            recentPlayed.unshift('✓ #' + det.id + ' – ' + det.name +
              ' (' + det.confidence.toFixed(1) + '%)');
            if (recentPlayed.length > 10) recentPlayed.pop();
            recentEl.innerHTML = recentPlayed.map(function(r) {{
              return '<div style="padding:6px 8px;margin:3px 0;background:#1a1a2e;'
                + 'border-radius:3px;border-left:3px solid #4caf50;font-size:13px;">'
                + r + '</div>';
            }}).join('');
            if (currentIndex < audioFiles.length - 1) {{
              currentIndex++;
              loadDetection(currentIndex);
              audio.play();
            }} else {{
              statusEl.textContent = '✅ Playback finished!';
            }}
          }});

          audio.addEventListener('play',  function() {{
            statusEl.textContent = '▶ Playing…';
          }});
          audio.addEventListener('pause', function() {{
            if (!audio.ended) statusEl.textContent = '⏸ Paused';
          }});

          window._bpPrev = function() {{
            if (currentIndex > 0) {{ loadDetection(currentIndex - 1); audio.play(); }}
          }};
          window._bpNext = function() {{
            if (currentIndex < audioFiles.length - 1) {{
              loadDetection(currentIndex + 1); audio.play();
            }}
          }};

          if (audioFiles.length > 0) loadDetection(0);
        """


    # -----------------------------------------------------------------------
    # Apply filters
    # -----------------------------------------------------------------------
    async def _apply_filters() -> None:
        """Read UI widgets into AppState, query detections, start generation."""
         
        # Write filter state
        state.ap_filter_use_time = use_time.value

        raw_conf = conf_select.value
        state.ap_filter_confidence = (
            None if raw_conf == 'All'
            else int(raw_conf.rstrip('%')) / 100
        )
        state.ap_filter_limit  = int(limit_input.value or 25)
        state.ap_filter_offset = int(offset_input.value or 0)

        sort_inv = {v: k for k, v in sort_labels.items()}
        state.ap_filter_sort = sort_inv.get(sort_select.value, 'time')

        # Parse dates
        try:
            state.ap_filter_date_from = (
                datetime.fromisoformat(date_from.value).date()
                if date_from.value else None
            )
            state.ap_filter_date_to = (
                datetime.fromisoformat(date_to.value).date()
                if date_to.value else None
            )
        except ValueError:
            ui.notify('Invalid date format', type='negative')
            return

        # Parse times
        if use_time.value:
            try:
                h, m = map(int, time_start.value.split(':'))
                state.ap_filter_time_start = dt_time(h, m)
                h, m = map(int, time_end.value.split(':'))
                state.ap_filter_time_end = dt_time(h, m)
            except Exception:
                ui.notify('Invalid time format', type='negative')
                return

        # Build and validate filter
        sort_order = 'desc' if state.ap_filter_sort == 'confidence' else 'asc'
        det_filter = DetectionFilter(
            species=state.ap_filter_species,
            date_from=(
                datetime.combine(state.ap_filter_date_from, dt_time(0, 0))
                if state.ap_filter_date_from else None
            ),
            date_to=(
                datetime.combine(state.ap_filter_date_to, dt_time(23, 59))
                if state.ap_filter_date_to else None
            ),
            time_start=(
                state.ap_filter_time_start if use_time.value else None
            ),
            time_end=(
                state.ap_filter_time_end if use_time.value else None
            ),
            min_confidence=state.ap_filter_confidence,
            limit=state.ap_filter_limit,
            offset=state.ap_filter_offset,
            sort_by=state.ap_filter_sort,
            sort_order=sort_order,
            pm_seconds=state.audio_frame_duration,
        )
        err = det_filter.validate()
        if err:
            ui.notify(f'Filter error: {err}', type='negative')
            return

        apply_btn.disable()
        try:
            loop = asyncio.get_event_loop()
            detections = await loop.run_in_executor(
                None,
                lambda: query_detections(
                    state.active_db, **det_filter.to_query_params()
                )
            )
        except Exception as e:
            logger.error(f"Query failed: {e}")
            ui.notify(f'Query error: {e}', type='negative')
            apply_btn.enable()
            return
        finally:
            apply_btn.enable()

        if not detections:
            ui.notify('No detections found', type='warning')
            return

        state.detections = detections
        state.ap_filters_applied = True
        state.invalidate_audio_cache()

        # Store filter context for TTS
        page['filter_context'] = det_filter.get_filter_context()

        _refresh_detection_list()
        _update_stats()
        results_col.set_visibility(True)

        # Start audio generation
        await _start_generation()

    # -----------------------------------------------------------------------
    # Apply audio settings
    # -----------------------------------------------------------------------
    async def _apply_audio_settings() -> None:
        """Write audio option widgets into AppState, invalidate cache, regenerate."""
        state.audio_say_number          = say_number.value
        state.audio_say_id              = say_id.value
        state.audio_say_confidence      = say_conf.value
        state.audio_bird_name           = bird_name_radio.value
        state.audio_speech_speed        = speech_speed.value
        state.audio_speech_loudness     = int(speech_loud.value)
        state.audio_frame_duration      = frame_dur.value
        state.audio_noise_reduction     = nr_check.value
        state.audio_noise_reduce_strength = float(
            _nr_steps[int(nr_slider.value)]
        )
        state.invalidate_audio_cache()
        if state.detections:
            _update_stats()
            await _start_generation()

    def _clear_cache() -> None:
        state.invalidate_audio_cache()
        player_container.set_visibility(False)
        ui.notify('Audio cache cleared', type='info')

    # -----------------------------------------------------------------------
    # Audio generation background task
    # -----------------------------------------------------------------------
    async def _start_generation() -> None:
        from nicegui import context as _ctx
        client = _ctx.client
        prev = page.get('generation_task')
        if prev and not prev.done():
            prev.cancel()
            try:
                await prev
            except asyncio.CancelledError:
                pass
        state.invalidate_audio_cache()
        task = asyncio.create_task(_generation_task(client))
        page['generation_task'] = task

    async def _generation_task(client) -> None:
        """
        Generate audio for all detections in the background.

        KNIFFLIG: Each finished MP3 is pushed into the browser via
        ui.run_javascript(). The JS player polls window.pendingAudioFiles
        every 500ms. This means playback can start as soon as the first
        file is ready, without waiting for all files.

        The first file is used to initialise the player HTML (so the
        player is injected into the DOM on first file ready, not before).
        """
        if not state.detections:
            return

        state.audio_generation_running = True
        state.audio_generation_progress = 0.0
        n = len(state.detections)

        gen_progress_row.set_visibility(True)
        gen_progress_bar.set_value(0)
        gen_progress_label.set_text(f'0 / {n}')
        player_container.set_visibility(False)

        player_obj = AudioPlayer(state.active_db, state.audio_frame_duration)
        audio_opts = state.get_audio_options()
        filter_ctx = page.get('filter_context', {})
        lang = state.language_code
        disable_tts = (
            audio_opts['bird_name_option'] == 'none'
            and not audio_opts['say_audio_number']
            and not audio_opts['say_id']
            and not audio_opts['say_confidence']
        )

        loop = asyncio.get_event_loop()
        first_file_rendered = False

        try:
            for i, det in enumerate(state.detections):
                # Run CPU-intensive audio generation in thread pool
                # KNIFFLIG: prepare_detection_audio_web is synchronous and
                # blocks for several seconds per file (TTS + noise reduction).
                # run_in_executor keeps the event loop responsive.
                try:
                    mp3_bytes = await loop.run_in_executor(
                        None,
                        lambda d=det, idx=i: player_obj.prepare_detection_audio_web(
                            d,
                            audio_number=idx + 1,
                            language_code=lang,
                            filter_context=filter_ctx,
                            audio_options=audio_opts,
                            disable_tts=disable_tts,
                        )
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        f"Audio generation failed for "
                        f"#{det['detection_id']}: {e}"
                    )
                    continue

                b64 = base64.b64encode(mp3_bytes.read()).decode()
                det_id = str(det['detection_id'])
                state.audio_cache[det_id] = b64

                conf_pct = det['confidence'] * 100
                file_entry = {
                    'id':         det['detection_id'],
                    'name':       det.get('local_name') or det['scientific_name'],
                    'scientific': det['scientific_name'],
                    'confidence': conf_pct,
                    'time':       det['segment_start_local'],
                    'timezone':   det.get('timezone', ''),
                    'audio_data': b64,
                }

                if not first_file_rendered:
                    player_container.clear()
                    with player_container:
                        ui.html(_build_player_html(json.dumps([file_entry])))
                        with ui.row().classes('gap-2 q-mt-sm'):
                            ui.button('▶ Play/Pause', on_click=lambda: ui.run_javascript(
                                "var a=document.getElementById('bp-audio');"
                                "if(a.paused){if(!a.src){"
                                "var d=document.getElementById('bp-details');"
                                "d.style.display='none';}a.play();}else{a.pause();}"
                            )).props('no-caps').style('background:#e94560;color:white;')
                            ui.button('⏮ Prev', on_click=lambda: ui.run_javascript(
                                "var a=document.getElementById('bp-audio');"
                                "window._bpPrev && window._bpPrev();"
                            )).props('no-caps').style('background:#e94560;color:white;')
                            ui.button('⏭ Next', on_click=lambda: ui.run_javascript(
                                "var a=document.getElementById('bp-audio');"
                                "window._bpNext && window._bpNext();"
                            )).props('no-caps').style('background:#e94560;color:white;')
                            ui.button('⏹ Stop', on_click=lambda: ui.run_javascript(
                                "var a=document.getElementById('bp-audio');"
                                "a.pause();a.currentTime=0;"
                                "document.getElementById('bp-status').textContent='Stopped';"
                            )).props('no-caps').style('background:#555;color:white;')
                    player_container.set_visibility(True)
                    with client:
                        await ui.run_javascript(
                            _build_player_js(json.dumps([file_entry])),
                            timeout=5.0,
                        )
                    first_file_rendered = True
                else:
                    entry_json = json.dumps(file_entry)
                    with client:
                        await ui.run_javascript(
                            f'window.pendingAudioFiles = '
                            f'(window.pendingAudioFiles || []);'
                            f'window.pendingAudioFiles.push({entry_json});',
                            timeout=5.0,
                        )
                # Update progress
                progress = (i + 1) / n
                state.audio_generation_progress = progress
                gen_progress_bar.set_value(progress)
                gen_progress_label.set_text(f'{i + 1} / {n}')

        except asyncio.CancelledError:
            logger.info("Audio generation task cancelled")
            raise
        finally:
            state.audio_generation_running = False
            gen_progress_row.set_visibility(False)

    # -----------------------------------------------------------------------
    # Export helpers
    # -----------------------------------------------------------------------
    async def _export_wav() -> None:
        if not state.detections:
            ui.notify('No detections loaded', type='warning')
            return
        export_dir = Path(tempfile.mkdtemp(prefix='birdnet_export_wav_'))
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: export_detections(
                    state.active_db, export_dir, state.detections,
                    state.language_code,
                    page.get('filter_context', {}),
                    state.get_audio_options(),
                    state.audio_frame_duration,
                    disable_tts=False,
                )
            )
            ui.notify(f'✅ WAV files exported to: {export_dir}', type='positive')
        except Exception as e:
            logger.error(f"WAV export failed: {e}")
            ui.notify(f'WAV export failed: {e}', type='negative')

    async def _export_mp3() -> None:
        if not state.detections:
            ui.notify('No detections loaded', type='warning')
            return
        export_dir = Path(tempfile.mkdtemp(prefix='birdnet_export_mp3_'))
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: export_detections_mp3(
                    state.active_db, export_dir, state.detections,
                    state.language_code,
                    page.get('filter_context', {}),
                    state.get_audio_options(),
                    state.audio_frame_duration,
                    disable_tts=False,
                )
            )
            ui.notify(f'✅ MP3 files exported to: {export_dir}', type='positive')
        except Exception as e:
            logger.error(f"MP3 export failed: {e}")
            ui.notify(f'MP3 export failed: {e}', type='negative')

    # -----------------------------------------------------------------------
    # Initial state: if filters were already applied (e.g. from DB overview)
    # trigger generation immediately
    # -----------------------------------------------------------------------
    if state.ap_filters_applied:
        if not state.detections:
            # Filters set (e.g. from DB overview) but no detections yet → run query
            await _apply_filters()
        else:
            _refresh_detection_list()
            _update_stats()
            results_col.set_visibility(True)
            if not state.audio_cache:
                await _start_generation()
            else:
                # Cache still valid – rebuild player from cache
                files = []
                for i, det in enumerate(state.detections):
                    det_id = str(det['detection_id'])
                    if det_id in state.audio_cache:
                        files.append({
                            'id':         det['detection_id'],
                            'name':       det.get('local_name') or det['scientific_name'],
                            'scientific': det['scientific_name'],
                            'confidence': det['confidence'] * 100,
                            'time':       det['segment_start_local'],
                            'timezone':   det.get('timezone', ''),
                            'audio_data': state.audio_cache[det_id],
                        })
                if files:
                    _raw_html = _build_player_html(json.dumps(files))
                _html_part = _raw_html[:_raw_html.index('<script>')]
                _js_part = _raw_html[_raw_html.index('<script>')+8:_raw_html.rindex('</script>')]
                player_container.clear()
                with player_container:
                    ui.html(_html_part)
                await ui.run_javascript(_js_part, timeout=5.0)