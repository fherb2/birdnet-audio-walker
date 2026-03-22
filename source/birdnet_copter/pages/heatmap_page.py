"""
Activity Heatmap page for BirdNET Play.

Covers:
- Filter section (species, date range, confidence)
- Heatmap options (colormap, weight-by-confidence)
- Apply Filters button → query + aggregate detections
- ECharts heatmap (48 time slots × N days)
- Click-event → modal dialog with detections + audio player
- CSV export
"""

import asyncio
import base64
import csv
import io
import json
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Dict, List, Tuple

from loguru import logger
from nicegui import ui, app as nicegui_app, context

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.page_header import page_header
from ..gui_elements.section_card import section_card
from ..gui_elements.species_search import SpeciesSearch
from ..player import AudioPlayer
from ..db_queries import query_detections, get_recording_date_range
from ..bird_language import load_labels
from ..task_status import run_with_loading, JS_TIMEOUT

import uuid
from nicegui import app as _nicegui_app
from fastapi.responses import JSONResponse

# Temporary store for dialog audio data: session_id -> List[Dict]
# Entries are removed when the dialog is closed.
_dialog_audio_store: Dict[str, List] = {}


@_nicegui_app.get('/api/dialog-audio/{session_id}')
async def _get_dialog_audio(session_id: str):
    data = _dialog_audio_store.get(session_id)
    if data is None:
        return JSONResponse(status_code=404, content={'error': 'not found'})
    return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEATMAP_CELL_SIZE = 12          # px per cell (width and height)
MIN_COLORSCALE_MAX = 4          # minimum upper bound of color scale
DIALOG_PM_SECONDS = 0.5         # PM buffer for dialog audio
DIALOG_MAX_DETECTIONS = 99      # max detections loaded per dialog

# 48 time slot labels (00:00 … 23:30)
TIME_SLOTS: List[str] = [
    f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)
]

# Labels shown on Y-axis: only 00:00 / 06:00 / 12:00 / 18:00
_Y_LABEL_SET = {"00:00", "06:00", "12:00", "18:00"}
Y_AXIS_LABELS: List[str] = [
    t if t in _Y_LABEL_SET else "" for t in TIME_SLOTS
]

# Confidence dropdown options
CONFIDENCE_OPTIONS: List[str] = ["All"] + [f"{v}%" for v in range(5, 100, 5)]
CONFIDENCE_DEFAULT = "70%"


# ---------------------------------------------------------------------------
# Colormap definitions for ECharts visualMap
# Each entry: list of hex color stops (min → max)
# ---------------------------------------------------------------------------

ECHARTS_COLORMAPS: Dict[str, List[str]] = {
    "turbo":          ["#30123b", "#4146ac", "#4575d6", "#27b19f",
                       "#8fd830", "#eded30", "#fb9e19", "#e64516", "#7a0403"],
    "viridis":        ["#440154", "#30688e", "#35b779", "#fde725"],
    "plasma":         ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"],
    "magma":          ["#000004", "#3b0f70", "#8c2981", "#de4968",
                       "#fea16e", "#fcfdbf"],
    "inferno":        ["#000004", "#420a68", "#932667", "#dd513a",
                       "#fca50a", "#fcffa4"],
    "blues":          ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"],
    "greens":         ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"],
    "reds":           ["#fff5f0", "#fcbba1", "#fb6a4a", "#cb181d", "#67000d"],
    "oranges":        ["#fff5eb", "#fdd0a2", "#fd8d3c", "#d94801", "#7f2704"],
    "purples":        ["#fcfbfd", "#dadaeb", "#9e9ac8", "#6a51a3", "#3f007d"],
    "greys":          ["#ffffff", "#d9d9d9", "#969696", "#525252", "#000000"],
    "blueorange":     ["#2166ac", "#92c5de", "#f7f7f7", "#f4a582", "#b2182b"],
    "redyellowblue":  ["#d73027", "#fc8d59", "#fee090", "#e0f3f8",
                       "#91bfdb", "#4575b4"],
    "redyellowgreen": ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b",
                       "#91cf60", "#1a9850"],
    "spectral":       ["#9e0142", "#f46d43", "#fee08b", "#e6f598",
                       "#66c2a5", "#5e4fa2"],
    "rainbow":        ["#6e40aa", "#4c6edb", "#23abd8", "#1ddfa3",
                       "#52f667", "#aff05b", "#e2b72f", "#fb4e17", "#b60a00"],
}


# ---------------------------------------------------------------------------
# Page state helper
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def aggregate_detections(
    detections: List[Dict],
    weight_by_confidence: bool,
    date_from: date,
    date_to: date,
) -> Dict[Tuple[str, int], Dict]:
    """
    Aggregate detections into a (date_str, slot_idx) → cell dict.

    Returns a dict keyed by (date_str "YYYY-MM-DD", slot_idx 0-47):
        {
          "value":        float,   # sum(confidence) or count
          "count":        int,     # number of detections
          "sum_conf":     float,   # sum of confidences (for avg calc)
        }
    All (date, slot) combinations in [date_from, date_to] × [0, 47] exist;
    cells with no detections have value=0, count=0.
    """
    # Pre-fill full matrix with zeros
    cells: Dict[Tuple[str, int], Dict] = {}
    cur = date_from
    while cur <= date_to:
        ds = cur.isoformat()
        for slot in range(48):
            cells[(ds, slot)] = {"value": 0.0, "count": 0, "sum_conf": 0.0}
        cur += timedelta(days=1)

    # Fill from detections
    for det in detections:
        ts_str = det.get("segment_start_local") or det.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue
        ds = ts.date().isoformat()
        slot = ts.hour * 2 + (1 if ts.minute >= 30 else 0)
        key = (ds, slot)
        if key not in cells:
            continue  # outside requested range
        c = cells[key]
        c["count"] += 1
        c["sum_conf"] += det.get("confidence", 0.0)
        c["value"] += det.get("confidence", 0.0) if weight_by_confidence else 1.0

    return cells


# ---------------------------------------------------------------------------
# ECharts option builder
# ---------------------------------------------------------------------------

def build_echart_options(
    cells: Dict[Tuple[str, int], Dict],
    date_from: date,
    date_to: date,
    colormap: str,
) -> Dict:
    """
    Build the ECharts option dict for the heatmap.

    X-axis: dates (YYYY-MM-DD), only Mondays labelled as "DD.MM."
    Y-axis: 48 time slots, only 00:00/06:00/12:00/18:00 labelled, inverted.
    Data points: [x_idx, y_idx, value, count, avg_confidence]
    """
    # Build ordered date list
    dates: List[date] = []
    cur = date_from
    while cur <= date_to:
        dates.append(cur)
        cur += timedelta(days=1)

    date_strs = [d.isoformat() for d in dates]

    # X-axis labels: only Mondays
    x_labels: List[str] = [
        d.strftime("%d.%m.") if d.weekday() == 0 else "" for d in dates
    ]

    # Build data array: [x_idx, y_idx, value, count, avg_conf]
    data_points = []
    max_val = 0.0
    for x_idx, ds in enumerate(date_strs):
        for y_idx in range(48):
            c = cells.get((ds, y_idx), {"value": 0.0, "count": 0, "sum_conf": 0.0})
            val = round(c["value"], 4)
            cnt = c["count"]
            avg_conf = round(c["sum_conf"] / cnt, 3) if cnt > 0 else 0.0
            if val > 0:
                data_points.append([x_idx, y_idx, val, cnt, avg_conf])
                if val > max_val:
                    max_val = val

    colorscale_max = max(max_val, MIN_COLORSCALE_MAX)
    colors = ECHARTS_COLORMAPS.get(colormap, ECHARTS_COLORMAPS["turbo"])

    return {
        "animation": False,
        "grid": {
            "top": 10,
            "bottom": 30,
            "left": 55,
            "right": 10,
            "width": len(dates) * HEATMAP_CELL_SIZE,
            "height": 48 * HEATMAP_CELL_SIZE,
        },
        "xAxis": {
            "type": "category",
            "data": x_labels,
            "splitArea": {"show": False},
            "axisLabel": {
                "interval": 0,
                "fontSize": 10,
                "rotate": 45,
            },
            "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "category",
            "data": Y_AXIS_LABELS,
            "inverse": True,
            "splitArea": {"show": False},
            "axisLabel": {"fontSize": 10},
            "axisTick": {"show": False},
        },
        "visualMap": {
            "type": "continuous",
            "show": False,
            "min": 0.01,
            "max": colorscale_max,
            "dimension": 2,
            "inRange": {"color": colors},
            "outOfRange": {"color": "#ffffff"},
        },
        "tooltip": {
            "trigger": "item",
            ":formatter": (
                # params.data = [x_idx, y_idx, value, count, avg_conf]
                # x_idx used to look up label on xAxis is not directly in params
                # → we embed date strings via custom formatter
                "function(params) {"
                "  if (!params.data) return '';"
                "  var d = params.data;"
                "  return 'Detections: ' + d[3]"
                "       + '<br/>Avg conf: ' + (d[4]*100).toFixed(1) + '%';"
                "}"
            ),
        },
        "series": [{
            "type": "heatmap",
            "data": data_points,
            "itemStyle": {
                "borderWidth": 0,
            },
            "emphasis": {
                "itemStyle": {
                    "shadowBlur": 4,
                    "shadowColor": "rgba(0,0,0,0.4)",
                },
            },
        }],
        # Store metadata for click handler (not rendered by ECharts)
        "_meta": {
            "date_strs": date_strs,
            "x_labels": x_labels,
        },
    }


# ---------------------------------------------------------------------------
# Page handler – Part 1: layout, filters, heatmap render
# (Part 2 appends: _open_click_dialog, _build_dialog_player_html, page wiring)
# ---------------------------------------------------------------------------

@ui.page("/heatmap")
async def heatmap_page() -> None:
    state = _get_state()
    create_layout(state)
    page_header('🌡', 'Date-Time-Map', 'heatmap')

    if state.active_db is None or not state.active_db.exists():
        ui.label("⚠️ No database selected. Please open a database first.") \
            .classes("text-orange-7 q-ma-md")
        ui.button("📂 Go to Database Overview",
                  on_click=lambda: ui.navigate.to("/")) \
            .props("no-caps")
        return

    labels = load_labels(state.bird_language_code)

    # ------------------------------------------------------------------
    # Page-local mutable state (dict avoids closure rebinding issues)
    # ------------------------------------------------------------------
    page: Dict[str, Any] = {
        "chart": None,           # ui.echart instance
        "date_strs": [],         # ordered list of date strings for click lookup
        "cells": {},             # aggregation result
        "dialog_task": None,     # asyncio.Task for dialog audio generation
    }

    # AudioPlayer instance for dialog audio (no TTS, simple mode)
    player = AudioPlayer(
        db_path=state.active_db,
        pm_seconds=DIALOG_PM_SECONDS,
    )

    # ------------------------------------------------------------------
    # Section: Filters
    # ------------------------------------------------------------------
    with section_card('🔍', 'Filters', 'heatmap_filters'):
        with ui.row().classes("w-full gap-6 q-mt-sm"):

            # --- Left column ---
            with ui.column().classes("gap-3").style("min-width:280px;"):
                species_search = SpeciesSearch(
                    db_path=state.active_db,
                    on_select=lambda s: setattr(state, "hm_filter_species", s),
                    initial_value=state.hm_filter_species,
                    labels=labels,
                )

                def _on_conf_change(e):
                    val = e.args if isinstance(e.args, str) else e.args.get('label', 'All')
                    state.hm_filter_confidence = None if val == "All" else int(val.rstrip("%")) / 100

                conf_select = ui.select(
                    options=CONFIDENCE_OPTIONS,
                    value=(
                        f"{int(state.hm_filter_confidence * 100)}%"
                        if state.hm_filter_confidence is not None
                        else CONFIDENCE_DEFAULT
                    ),
                    label="Min Confidence",
                ).props("dense outlined").classes("w-full")
                conf_select.on("update:modelValue", _on_conf_change)

                with ui.row().classes("items-center gap-4"):
                    def _on_colormap_change(e):
                        val = e.args['label'] if isinstance(e.args, dict) else e.args
                        setattr(state, "hm_colormap", val)

                    colormap_select = ui.select(
                        options=list(ECHARTS_COLORMAPS.keys()),
                        value=state.hm_colormap,
                        label="Colormap",
                    ).props("dense outlined").classes("w-44")
                    colormap_select.on("update:modelValue", _on_colormap_change)

                    weight_cb = ui.checkbox(
                        "Weight by Confidence",
                        value=state.hm_weight_confidence,
                    )
                    weight_cb.on(
                        "update:modelValue",
                        lambda e: setattr(state, "hm_weight_confidence", bool(e.args)),
                    )

            # --- Right column ---
            with ui.column().classes("gap-3"):
                if state.hm_filter_date_from is None or state.hm_filter_date_to is None:
                    try:
                        db_min, db_max = get_recording_date_range(state.active_db)
                        if state.hm_filter_date_from is not None and hasattr(state.hm_filter_date_from, 'date'):
                            state.hm_filter_date_from = state.hm_filter_date_from.date()
                        if state.hm_filter_date_to is not None and hasattr(state.hm_filter_date_to, 'date'):
                            state.hm_filter_date_to = state.hm_filter_date_to.date()
                        state.hm_filter_date_from = state.hm_filter_date_from or db_min.date()
                        state.hm_filter_date_to = state.hm_filter_date_to or db_max.date()
                    except Exception:
                        state.hm_filter_date_from = state.hm_filter_date_from or date.today()
                        state.hm_filter_date_to = state.hm_filter_date_to or date.today()

                with ui.row().classes("gap-3"):
                    date_from_input = ui.input(
                        label='Date From',
                        value=state.hm_filter_date_from.isoformat()
                            if state.hm_filter_date_from else '',
                    ).props('type=date outlined dense').classes('w-40')
                    date_from_input.on(
                        'change',
                        lambda e: setattr(
                            state, 'hm_filter_date_from',
                            date.fromisoformat(e.args['value']) if e.args.get('value') else None,
                        ),
                    )

                    date_to_input = ui.input(
                        label='Date To',
                        value=state.hm_filter_date_to.isoformat()
                            if state.hm_filter_date_to else '',
                    ).props('type=date outlined dense').classes('w-40')
                    date_to_input.on(
                        'change',
                        lambda e: setattr(
                            state, 'hm_filter_date_to',
                            date.fromisoformat(e.args['value']) if e.args.get('value') else None,
                        ),
                    )

        # ------------------------------------------------------------------
        # Apply Filters button
        # ------------------------------------------------------------------
        async def _apply_filters() -> None:
            """Query detections, aggregate, and render/update the heatmap."""
            if state.hm_filter_date_from is None or state.hm_filter_date_to is None:
                ui.notify("Please set a date range.", type="warning")
                return
            if state.hm_filter_date_from > state.hm_filter_date_to:
                ui.notify("Date From must be ≤ Date To.", type="warning")
                return

            try:
                detections = await run_with_loading(
                    apply_btn,
                    lambda: query_detections(
                        db_path=state.active_db,
                        species=state.hm_filter_species or None,
                        date_from=datetime.combine(state.hm_filter_date_from, dt_time(0, 0)),
                        date_to=datetime.combine(state.hm_filter_date_to, dt_time(23, 59)),
                        min_confidence=state.hm_filter_confidence,
                        limit=999_999,
                        offset=0,
                        sort_by="time",
                        sort_order="asc",
                        labels=labels,
                    ),
                    shared_state=state.shared_state,
                    label='Querying detections…',
                )
            except Exception as exc:
                logger.exception("Heatmap query failed")
                ui.notify(f"Query error: {exc}", type="negative")
                return

            if not detections:
                ui.notify("No detections found for current filters.", type="warning")
                apply_btn.props(remove="loading")
                return

            cells = aggregate_detections(
                detections,
                state.hm_weight_confidence,
                state.hm_filter_date_from,
                state.hm_filter_date_to,
            )  
            page["cells"] = cells

            options = build_echart_options(
                cells,
                state.hm_filter_date_from,
                state.hm_filter_date_to,
                state.hm_colormap,
            )
            # Store ordered date list for click handler
            page["date_strs"] = options["_meta"]["date_strs"]

            state.hm_aggregated_data = cells      # persist in AppState
            state.hm_filters_applied = True

            if page["chart"] is None:
                # First render: create chart element
                n_days = (state.hm_filter_date_to - state.hm_filter_date_from).days + 1
                chart_w = max(n_days * HEATMAP_CELL_SIZE + 140, 400)
                chart_h = 48 * HEATMAP_CELL_SIZE + 80

                with chart_container:
                    chart_container.clear()
                    chart = (
                        ui.echart(options)
                        .style(f"width:{chart_w}px;height:{chart_h}px;")
                            .on("click", lambda e: _handle_chart_click(e, state, page, player),
                            args=['offsetX', 'offsetY'])
                    )
                    page["chart"] = chart
            else:
                # Update existing chart
                page["chart"].options.update(options)
                page["chart"].update()

            export_btn.enable()
            download_section.set_visibility(True)
            ui.notify(f"Heatmap updated ({len(detections)} detections).", type="positive")

        apply_btn = ui.button("▶ Apply Filters", on_click=_apply_filters) \
            .props("no-caps color=primary").classes("q-mt-sm")

    # ------------------------------------------------------------------
    # Chart container + Download
    # ------------------------------------------------------------------
    with section_card('🗺', 'Heatmap', 'heatmap_chart'):
        chart_container = ui.column().classes("w-full q-mt-md overflow-auto")

        if state.hm_filters_applied and state.hm_aggregated_data:
            # Re-render on page revisit without re-querying
            page["cells"] = state.hm_aggregated_data
            options = build_echart_options(
                state.hm_aggregated_data,
                state.hm_filter_date_from,
                state.hm_filter_date_to,
                state.hm_colormap,
            )
            page["date_strs"] = options["_meta"]["date_strs"]
            n_days = (state.hm_filter_date_to - state.hm_filter_date_from).days + 1
            chart_w = max(n_days * HEATMAP_CELL_SIZE + 140, 400)
            chart_h = 48 * HEATMAP_CELL_SIZE + 80
            with chart_container:
                chart = (
                        ui.echart(options)
                        .style(f"width:{chart_w}px;height:{chart_h}px;")
                        .on("click", lambda e: _handle_chart_click(e, state, page, player),
                            args=['offsetX', 'offsetY'])
                    )
                page["chart"] = chart

        # ------------------------------------------------------------------
        # CSV Export button (wired in Part 2 via _export_csv)
        # ------------------------------------------------------------------
        with ui.column().classes('w-full') as download_section:
            ui.label('📥 Download').classes('text-subtitle1 q-mb-xs')

            with ui.row().classes('gap-3 items-center q-mt-sm'):
                export_btn = ui.button(
                    '📥 Download CSV',
                    on_click=lambda: _export_csv(state, page),
                ).props('no-caps')

                ui.label("Save as PNG: Use the chart's context menu (right-click).") \
                    .classes('text-caption text-grey-6')

        download_section.set_visibility(state.hm_filters_applied)

    # ------------------------------------------------------------------
    # _handle_chart_click and _open_click_dialog defined in Part 2
    # ------------------------------------------------------------------
# ===========================================================================
# Part 2 – Click handler, dialog, audio player, CSV export
# Append this directly below Part 1 (no blank line between needed).
# ===========================================================================


# ---------------------------------------------------------------------------
# Chart click handler
# ---------------------------------------------------------------------------

def _handle_chart_click(
    e: Any,
    state: AppState,
    page: Dict[str, Any],
    player: AudioPlayer,
) -> None:
    try:
        args = e.args
        offset_x = args.get('offsetX', 0)
        offset_y = args.get('offsetY', 0)

        # Grid offsets from build_echart_options: left=55, top=10
        grid_left = 55
        grid_top = 10

        x_idx = int((offset_x - grid_left) / HEATMAP_CELL_SIZE)
        y_idx = int((offset_y - grid_top) / HEATMAP_CELL_SIZE)

        date_strs: List[str] = page.get("date_strs", [])
        if x_idx < 0 or x_idx >= len(date_strs):
            return
        if y_idx < 0 or y_idx >= 48:
            return

        key = (date_strs[x_idx], y_idx)
        cell = page.get("cells", {}).get(key, {"value": 0.0, "count": 0, "sum_conf": 0.0})

        clicked_date = date.fromisoformat(date_strs[x_idx])
        slot_label = TIME_SLOTS[y_idx]
        slot_h = y_idx // 2
        slot_m = (y_idx % 2) * 30
        slot_end_min = slot_m + 29
        slot_end_label = f"{slot_h:02d}:{slot_end_min:02d}"

        asyncio.create_task(
            _open_click_dialog(
                state=state,
                player=player,
                page=page,
                client=context.client,
                clicked_date=clicked_date,
                slot_label=slot_label,
                slot_end_label=slot_end_label,
                y_idx=y_idx,
                cell_value=cell["value"],
                cell_count=cell["count"],
                cell_avg_conf=round(cell["sum_conf"] / cell["count"], 3) if cell["count"] > 0 else 0.0,
            )
        )
    except Exception as exc:
        logger.exception(f"Heatmap click failed: {exc}")
        ui.notify(f"Click error: {exc}", type="negative")


# ---------------------------------------------------------------------------
# Click dialog
# ---------------------------------------------------------------------------

async def _open_click_dialog(
    state: AppState,
    player: AudioPlayer,
    page: Dict[str, Any],
    client,
    clicked_date: date,
    slot_label: str,
    slot_end_label: str,
    y_idx: int,
    cell_value: float,
    cell_count: int,
    cell_avg_conf: float,
) -> None:
    """Build and open the modal dialog for a clicked heatmap cell."""
    try:
        with client:
            # time_range for query: slot start/end within the 30-min window
            slot_h = y_idx // 2
            slot_m = (y_idx % 2) * 30
            t_start = dt_time(slot_h, slot_m, 0)
            t_end = dt_time(slot_h, slot_m + 29 if slot_m == 0 else 59, 59)

            date_label = clicked_date.strftime("%d.%m.%Y")
            species_label = state.hm_filter_species or "All species"

            dialog = ui.dialog().props("maximized=false persistent=false")
            
            cleanup_ref = {'session_id': None}
            def _cleanup():
                sid = cleanup_ref.get('session_id')
                if sid:
                    _dialog_audio_store.pop(sid, None)
            dialog.on('hide', lambda: _cleanup())

            with dialog, ui.card().classes("q-pa-md").style("min-width:500px;max-width:700px;"):

                # --- Header ---
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(f"📅 {date_label}  🕐 {slot_label} – {slot_end_label}") \
                        .classes("text-h6")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense")

                ui.label(f"Species: {species_label}").classes("text-caption text-grey-7")

                with ui.row().classes("gap-6 q-mt-xs"):
                    ui.label(f"Detections: {cell_count}").classes("text-body2")
                    ui.label(f"Value: {cell_value:.2f}").classes("text-body2")
                    ui.label(f"Avg conf: {cell_avg_conf * 100:.1f}%").classes("text-body2")

                ui.separator()

                # --- Detections load ---
                status_label = ui.label("Loading detections…").classes("text-caption text-grey-6")
                progress = ui.linear_progress(value=0).classes("w-full")
                player_container = ui.column().classes("w-full")

                dialog.open()

                # Load detections in background
                try:
                    loop = asyncio.get_event_loop()
                    detections = await loop.run_in_executor(
                        None,
                        lambda: query_detections(
                            db_path=state.active_db,
                            species=state.hm_filter_species or None,
                            date_from=datetime.combine(clicked_date, dt_time(0, 0)),
                            date_to=datetime.combine(clicked_date, dt_time(23, 59)),
                            min_confidence=state.hm_filter_confidence,
                            time_range=(t_start, t_end),
                            limit=DIALOG_MAX_DETECTIONS,
                            sort_by="confidence",
                            sort_order="desc",
                            labels=load_labels(state.bird_language_code),
                        ),
                    )
                    
                except Exception as exc:
                    logger.exception("Dialog detection query failed")
                    status_label.set_text(f"Error loading detections: {exc}")
                    progress.set_visibility(False)
                    return

                if not detections:
                    status_label.set_text("No detections found for this time slot.")
                    progress.set_visibility(False)
                    return

                status_label.set_text(
                    f"Generating audio for {len(detections)} detection(s)…"
                )

                # --- Generate audio as background task ---
                audio_files: List[Dict] = []

                for i, det in enumerate(detections):
                    try:
                        mp3_bytes_io = await loop.run_in_executor(
                            None,
                            lambda d=det: player.prepare_detection_audio_simple(
                                d, DIALOG_PM_SECONDS
                            ),
                        )
                        b64 = base64.b64encode(mp3_bytes_io.read()).decode()
                        ts_str = det.get("segment_start_local", "")
                        try:
                            ts_label = datetime.fromisoformat(ts_str).strftime("%H:%M:%S")
                        except ValueError:
                            ts_label = ts_str
                        audio_files.append({
                            "id":         str(det.get("detection_id", i)),
                            "label":      f"{ts_label}  –  conf {det.get('confidence', 0)*100:.1f}%",
                            "data":       b64,
                            "species":    det.get("species_name", ""),
                        })
                    except Exception as exc:
                        logger.warning(
                            f"Audio generation failed for detection "
                            f"#{det.get('detection_id')}: {exc}"
                        )

                    progress.set_value((i + 1) / len(detections))

                status_label.set_text(
                    f"{len(audio_files)} audio clip(s) ready."
                    if audio_files else "Audio generation failed for all detections."
                )
                progress.set_visibility(False)
                
                if audio_files:
                    session_id = str(uuid.uuid4())
                    _dialog_audio_store[session_id] = audio_files
                    cleanup_ref['session_id'] = session_id
                    container_id = player_container.id

                    with player_container:
                        wait_label = ui.label("⏳ Wait until audio is downloaded...") \
                            .classes("text-caption text-grey-6 q-mt-sm")

                    await ui.run_javascript(
                        _build_dialog_player_js(session_id, container_id),
                        timeout=JS_TIMEOUT,
                    )
                        
    except Exception as exc:
        logger.exception(f"_open_click_dialog failed: {exc}")
        with client:
            ui.notify(f"Dialog error: {exc}", type="negative")

# ---------------------------------------------------------------------------
# Compact inline HTML/JS audio player for dialog
# ---------------------------------------------------------------------------


def _build_dialog_player_js(session_id: str, container_id: int) -> str:
    return f"""
fetch('/api/dialog-audio/{session_id}')
  .then(function(r) {{ return r.json(); }})
  .then(function(files) {{
    var container = document.getElementById('c{container_id}');
    if (!container) {{
      console.error('container c{container_id} not found');
      return;
    }}
    container.innerHTML = `
      <audio id="hm_audio_{session_id}" style="width:100%;height:36px;" controls></audio>
      <div id="hm_playlist_{session_id}"
           style="max-height:180px;overflow-y:auto;margin-top:6px;
                  border:1px solid #ddd;border-radius:4px;"></div>
    `;
    var audio = document.getElementById('hm_audio_{session_id}');
    var list  = document.getElementById('hm_playlist_{session_id}');
    var cur = 0;

    function play(idx) {{
      cur = idx;
      audio.src = 'data:audio/mpeg;base64,' + files[idx].data;
      audio.play();
      renderList();
    }}

    function renderList() {{
      list.innerHTML = '';
      files.forEach(function(f, i) {{
        var row = document.createElement('div');
        row.style.cssText =
          'padding:4px 8px;cursor:pointer;display:flex;align-items:center;gap:8px;' +
          (i === cur ? 'background:#e3f2fd;font-weight:bold;' : '');
        row.innerHTML =
          '<span style="color:#1976d2;">' + (i===cur?'▶':'○') + '</span>' +
          '<span>' + f.label + '</span>';
        row.onclick = function() {{ play(i); }};
        list.appendChild(row);
      }});
    }}

    audio.addEventListener('ended', function() {{
      if (cur + 1 < files.length) play(cur + 1);
    }});

    if (files.length > 0) play(0);
  }})
  .catch(function(e) {{ console.error('fetch error:', e); }});
"""

# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

def _export_csv(state: AppState, page: Dict[str, Any]) -> None:
    """
    Export the current aggregation matrix as CSV and trigger browser download.

    Rows = 48 time slots, columns = dates.
    Values are the aggregated cell values (confidence sum or count).
    """
    cells: Dict[Tuple[str, int], Dict] = page.get("cells", {})
    if not cells:
        ui.notify("No heatmap data to export. Apply filters first.", type="warning")
        return

    # Reconstruct ordered date list from cells keys
    date_set = sorted({ds for ds, _ in cells.keys()})

    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header row: "time" + dates
    writer.writerow(["time"] + date_set)

    # One row per slot
    for slot in range(48):
        row = [TIME_SLOTS[slot]]
        for ds in date_set:
            c = cells.get((ds, slot), {"value": 0.0})
            row.append(round(c["value"], 4))
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8")

    # Build filename
    species_part = (
        state.hm_filter_species.replace(" ", "_") if state.hm_filter_species
        else "all_species"
    )
    date_from_part = (
        state.hm_filter_date_from.isoformat() if state.hm_filter_date_from else "unknown"
    )
    date_to_part = (
        state.hm_filter_date_to.isoformat() if state.hm_filter_date_to else "unknown"
    )
    filename = f"heatmap_{species_part}_{date_from_part}_{date_to_part}.csv"

    ui.download(csv_bytes, filename=filename)