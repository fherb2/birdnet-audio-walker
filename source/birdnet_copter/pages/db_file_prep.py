"""
DB Configuration page – folder selection and database initialisation.

Route: /db-config

Sections:
  2.2  Folder / DB selection  (DbFolderTree, single-select)
  2.3  Metadata table         (scan_folder results, radio-button selection)
  2.4  GPS / Map              (lat/lon input + OpenStreetMap)
  2.6  UTC time method        (dropdown + offset + preview table)
"""

import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger
from nicegui import ui, app as nicegui_app, context

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.page_header import page_header
from ..gui_elements.section_card import section_card
from ..gui_elements.notes_card import NotesCard
from ..folder_metadata_scanner import scan_folder
from ..database import init_database
from ..db_queries import get_db_meta_data, set_db_meta_data
from ..gui_elements.folder_tree import FolderTree


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_FILENAME = 'birdnet_analysis.db'
PAGE_ROUTE  = '/db-config'


# ---------------------------------------------------------------------------
# Page registration
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


@ui.page(PAGE_ROUTE)
async def db_file_prep() -> None:
    state = _get_state()
    state.dbprep_page_active = True

    async def _on_disconnect():
        state.dbprep_page_active = False
    context.client.on_disconnect(_on_disconnect)
    
    create_layout(state)

    page_header('/static/icons/db_icon_32.svg', 'Database Configuration', 'db_file_prep')

    # ------------------------------------------------------------------
    # Header override: second row shows selected folder in dark red
    # when on this page (Konzept 2.1)
    # ------------------------------------------------------------------
    await ui.run_javascript("""
        (function() {
            // Find the second header row label and override its text + style.
            // layout.py renders it with id derived from class 'db-path-label'
            // We patch via a small polling loop until the element appears.
            var attempts = 0;
            var interval = setInterval(function() {
                var el = document.querySelector('[data-db-path-label]');
                if (el || attempts > 20) {
                    clearInterval(interval);
                    if (el) {
                        el.dataset.dbprepOverride = '1';
                    }
                }
                attempts++;
            }, 100);
        })();
    """)

    # Page-local state dict (avoids closure rebinding issues)
    page: dict = {
        'scan_task': None,   # current asyncio scan task
    }

    # ------------------------------------------------------------------
    # Header second-row label – updated reactively
    # ------------------------------------------------------------------
    def _header_label() -> str:
        if state.dbprep_folder is None:
            return 'Select a folder (DB) to configure / edit!'
        return str(state.dbprep_folder)

    # NiceGUI label in dark red shown at top of page content (mirrors header
    # intent; actual header patching requires JS cooperation with layout.py –
    # implemented as a prominent banner here instead)
    with ui.row().classes('w-full items-center bg-red-9 text-white px-4 py-2 rounded q-mb-sm'):
        folder_banner = ui.label(_header_label()).classes('text-body1 font-bold')

    def _refresh_banner() -> None:
        folder_banner.set_text(_header_label())

    # ------------------------------------------------------------------
    # Section 2.2: Folder / DB selection
    # ------------------------------------------------------------------
    with section_card('📂', 'Folder / Database Selection', 'dbprep_folder_selection'):

        ui.label(
            'Select a folder containing audio files. One folder = one recording '
            'location = one database. Only folders with audio files are selectable.'
        ).classes('text-caption text-grey-8 q-mb-sm')

        def _on_folder_selected(folder: Optional[Path]) -> None:
            """Called by DbFolderTree when user selects / deselects a folder."""
            state.dbprep_folder = folder
            state.dbprep_scan_result = None   # invalidate cached scan

            if folder is None:
                state.dbprep_mode = 'create'
                _refresh_banner()
                _refresh_dependent_sections()
                return

            db_path = folder / DB_FILENAME
            state.dbprep_mode = 'edit' if db_path.exists() else 'create'
            logger.info(
                f"DB config: folder selected – {folder.name} "
                f"(mode={state.dbprep_mode})"
            )
            _refresh_banner()
            _refresh_notes_section()
            _refresh_metadata_section()   # zeigt Spinner
            _trigger_scan(folder)         # startet Scan; rendert alles wenn fertig

        FolderTree(
            root_path=state.root_path,
            on_select=_on_folder_selected,
        )

    # ------------------------------------------------------------------
    # Placeholder containers for sections filled after folder selection
    # These are populated by _refresh_dependent_sections()
    # ------------------------------------------------------------------
    notes_container       = ui.column().classes('w-full')
    metadata_container    = ui.column().classes('w-full')
    kv_overview_container = ui.column().classes('w-full')
    gps_map_container     = ui.column().classes('w-full')
    utc_container         = ui.column().classes('w-full')
    confirm_container     = ui.column().classes('w-full')
    gps_map_ref: dict = {'m': None, 'final_marker': None, 'blue_markers': []}

    with gps_map_container:
        with section_card('🗺', 'Location (GPS)', 'dbprep_gps'):
            ui.label(
                'Click on the map or an existing marker to set the recording location. '
                'Blue markers show GPS coordinates found in file metadata. '
                'The red marker is the final position stored in the database.'
            ).classes('text-caption text-grey-8 q-mb-sm')

            gps_warning_label = ui.label('').classes('text-caption text-orange-8 q-mb-sm')
            gps_warning_label.set_visibility(False)
            with ui.row().classes('items-center gap-6 q-mb-sm'):
                ui.label('🔵 GPS from metadata (suggestion)').classes('text-caption text-grey-7')
                ui.label('🔴 Selected position (will be saved)').classes('text-caption text-grey-7')

            with ui.row().classes('items-center gap-4 q-mb-sm'):
                lat_input = ui.number(
                    label='Latitude', value=90.0, format='%.6f',
                    min=-90.0, max=90.0,
                ).classes('w-40').props('outlined dense')
                lon_input = ui.number(
                    label='Longitude', value=0.0, format='%.6f',
                    min=-180.0, max=180.0,
                ).classes('w-40').props('outlined dense')
                ui.label('(90.0 / 0.0 = no location set)').classes('text-caption text-grey-6')

            m = ui.leaflet(center=(51.16, 10.45), zoom=6).classes('w-full').style('height: 400px;')
            gps_map_ref['m'] = m

            ui.button(
                '🔄 Reset to "no location" (Nordpol)',
                on_click=lambda: _update_position(90.0, 0.0, m, lat_input, lon_input, gps_map_ref, state, page),
            ).props('no-caps flat').classes('q-mt-xs')

    await m.initialized()

    async def _on_map_click(e):
        try:
            lat = e.args['latlng']['lat']
            lon = e.args['latlng']['lng']
            _update_position(float(lat), float(lon), m, lat_input, lon_input, gps_map_ref, state, page)
        except (KeyError, TypeError) as ex:
            logger.warning(f"Map click: {e.args} – {ex}")

    m.on('map-click', _on_map_click)

    lat_input.on('blur', lambda _: _try_manual_input(lat_input, lon_input, m, gps_map_ref, state, page))
    lon_input.on('blur', lambda _: _try_manual_input(lat_input, lon_input, m, gps_map_ref, state, page))

    # ------------------------------------------------------------------
    # Async scan helpers
    # ------------------------------------------------------------------

    async def _run_scan(folder: Path) -> None:
        """Run scan_folder in thread pool, store result, refresh table."""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, scan_folder, folder)
            state.dbprep_scan_result = result
            logger.info(
                f"DB config: scan done – {len(result)} keys for {folder.name}"
            )
        except Exception as e:
            logger.error(f"DB config: scan failed for {folder}: {e}")
            state.dbprep_scan_result = {}
        finally:
            _refresh_metadata_section()
            _refresh_kv_overview_section()
            _refresh_utc_section()
            _refresh_confirm_section()
            _update_map_markers(state, page, m, lat_input, lon_input, gps_map_ref, gps_warning_label)

    def _trigger_scan(folder: Path) -> None:
        """Cancel any running scan and start a new one."""
        if page['scan_task'] and not page['scan_task'].done():
            page['scan_task'].cancel()
        page['scan_task'] = asyncio.create_task(_run_scan(folder))

    # ------------------------------------------------------------------
    # Section refresh helpers (called on folder change or scan completion)
    # ------------------------------------------------------------------

    def _refresh_dependent_sections() -> None:
        _refresh_metadata_section()
        if state.dbprep_scan_result is not None:
            _refresh_notes_section()
            _refresh_kv_overview_section()
            _refresh_utc_section()
            _refresh_confirm_section()
            _update_map_markers(state, page, m, lat_input, lon_input, gps_map_ref, gps_warning_label)
            
    def _refresh_notes_section() -> None:
        notes_container.clear()
        with notes_container:
            if state.dbprep_folder is not None:
                db_path = state.dbprep_folder / DB_FILENAME
                if db_path.exists():
                    NotesCard(db_path=db_path, folder_path=state.dbprep_folder)

    def _refresh_metadata_section() -> None:
        metadata_container.clear()
        with metadata_container:
            _render_metadata_section(state, page)

    def _refresh_kv_overview_section() -> None:
        kv_overview_container.clear()
        with kv_overview_container:
            _render_kv_overview_section(state, page)

    def _refresh_utc_section() -> None:
        utc_container.clear()
        with utc_container:
            _render_utc_section(state, page)

    def _refresh_confirm_section() -> None:
        confirm_container.clear()
        with confirm_container:
            _render_confirm_section(state, page)

    page['refresh_confirm'] = _refresh_confirm_section

    # Initial render if folder already selected (page revisit)
    if state.dbprep_folder is not None:
        _refresh_dependent_sections()
        if state.dbprep_scan_result is not None:
            _update_map_markers(state, page, m, lat_input, lon_input, gps_map_ref, gps_warning_label)
        if state.dbprep_scan_result is None:
            _trigger_scan(state.dbprep_folder)


# ===========================================================================
# Section renderers (called from refresh helpers above)
# ===========================================================================
          

    
       
def _render_metadata_section(state: AppState, page: dict) -> None:
    """
    Section 2.3 – File Metadata table.

    Shows all metadata extracted by scan_folder() as a scrollable table
    with radio-button selection logic per key.

    Columns:
      1. Checkbox (radio-button within same key group)
      2. Key
      3. Value (editable after table creation)
      4. Files containing this key/value pair

    Selected rows are stored in page['rows_state'] for use by section 2.5.
    """
    if state.dbprep_folder is None:
        return

    with section_card('🔍', 'File Metadata', 'dbprep_metadata'):

        with ui.row().classes('items-center gap-3 q-mb-sm'):
            ui.button(
                '🔄 Recreate Table',
                on_click=lambda: _start_scan(state.dbprep_folder, state, page),
            ).props('no-caps flat')
            ui.button(
                '➕ Add row',
                on_click=lambda: _add_manual_row(page, table_container),
            ).props('no-caps flat')

        if state.dbprep_scan_result is None:
            with ui.row().classes('items-center gap-2'):
                ui.spinner(size='sm')
                ui.label('Scanning files…').classes('text-caption text-grey-7')
            return

        if not state.dbprep_scan_result:
            ui.label('No metadata found in this folder.') \
                .classes('text-caption text-grey-6')
            return

        # Build flat row list and store in page dict so 2.5 can access it
        if 'rows_state' not in page or page.get('rows_folder') != state.dbprep_folder:
            rows: list[dict] = []
            for key, (files, values) in sorted(state.dbprep_scan_result.items()):
                seen: dict = {}
                for fname, val in zip(files, values):
                    vk = repr(val)
                    if vk not in seen:
                        seen[vk] = {'value': val, 'files': []}
                    seen[vk]['files'].append(fname)
                for entry in seen.values():
                    rows.append({
                        'key':      key,
                        'value':    entry['value'],
                        'files':    entry['files'],
                        'selected': False,
                        'edited':   False,
                        'manual':   False,
                    })
            page['rows_state']  = rows
            page['rows_folder'] = state.dbprep_folder

        rows_state = page['rows_state']

        table_container = ui.column().classes('w-full gap-0').style(
            'max-height: 700px; overflow-y: auto;'
            'border: 1px solid #e0e0e0; border-radius: 4px;'
        )
        with table_container:
            _render_table_header(table_container)
            _render_table_rows(rows_state, table_container, page)


def _render_table_header(container) -> None:
    with container:
        with ui.row().classes(
            'w-full px-2 py-1 bg-grey-2 text-caption font-bold gap-2 items-center'
        ):
            ui.label('✓').classes('w-6 text-center')
            ui.label('Key').classes('w-48')
            ui.label('Value').classes('flex-grow')
            ui.label('Files').classes('w-64')


def _render_table_rows(rows_state: list[dict], container, page: dict) -> None:
    for idx, row in enumerate(rows_state):
        _render_single_row(idx, row, rows_state, container, page)


def _render_single_row(
    idx: int,
    row: dict,
    rows_state: list[dict],
    container,
    page: dict,
) -> None:
    bg = 'bg-blue-1' if row['selected'] else (
        'bg-yellow-1' if row['manual'] else ''
    )
    with container:
        with ui.row().classes(
            f'w-full px-2 py-1 gap-2 items-center border-b border-grey-3 {bg}'
        ):
            # Col 1: checkbox
            ui.checkbox(
                value=row['selected'],
                on_change=lambda e, i=idx: _on_row_select(
                    i, e.value, rows_state, container, page
                ),
            ).props('dense').classes('w-6')

            # Col 2: key (editable for manual rows)
            if row['manual']:
                ki = ui.input(value=row['key']).classes('w-48').props('dense outlined')
                ki.on('blur', lambda e, i=idx: _on_key_change(e.sender.value, i, rows_state))
            else:
                ui.label(row['key']).classes('w-48 text-caption text-grey-9')

            # Col 3: value (always editable)
            vi = ui.input(value=str(row['value'])).classes('flex-grow').props('dense outlined')
            vi.on('blur',           lambda e, i=idx: _on_value_change(e.sender.value, i, rows_state, container, page))
            vi.on('keydown.enter',  lambda e, i=idx: _on_value_change(e.sender.value, i, rows_state, container, page))

            # Col 4: files
            files_text = ', '.join(row['files']) if row['files'] else '–'
            ui.label(files_text).classes('w-64 text-caption text-grey-7')


def _on_row_select(
    idx: int,
    value: bool,
    rows_state: list[dict],
    container,
    page: dict,
) -> None:
    key = rows_state[idx]['key']
    if value:
        for i, row in enumerate(rows_state):
            if row['key'] == key and i != idx:
                rows_state[i]['selected'] = False
        rows_state[idx]['selected'] = True
    else:
        rows_state[idx]['selected'] = False

    ui.timer(0.05, lambda: _rebuild_table(rows_state, container, page), once=True)
    # Live-update section 2.5
    if page.get('refresh_kv_overview'):
        page['refresh_kv_overview']()


def _on_value_change(
    val: str,
    idx: int,
    rows_state: list[dict],
    container,
    page: dict,
) -> None:
    rows_state[idx]['value']  = val
    rows_state[idx]['edited'] = True
    rows_state[idx]['files']  = []
    _on_row_select(idx, True, rows_state, container, page)


def _on_key_change(val: str, idx: int, rows_state: list[dict]) -> None:
    existing = [r['key'] for j, r in enumerate(rows_state) if j != idx and not r['manual']]
    if val in existing:
        ui.notify(f"Key '{val}' already exists.", type='warning')
    else:
        rows_state[idx]['key'] = val


def _rebuild_table(rows_state: list[dict], container, page: dict) -> None:
    container.clear()
    with container:
        _render_table_header(container)
        _render_table_rows(rows_state, container, page)


def _add_manual_row(page: dict, container) -> None:
    rows_state = page.get('rows_state', [])
    rows_state.append({
        'key': '', 'value': '', 'files': [],
        'selected': False, 'edited': False, 'manual': True,
    })
    _rebuild_table(rows_state, container, page)


def _start_scan(folder: Optional[Path], state: AppState, page: dict) -> None:
    if folder is None:
        return
    state.dbprep_scan_result = None
    page.pop('rows_state', None)
    if page.get('scan_task') and not page['scan_task'].done():
        page['scan_task'].cancel()

    async def _run():
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, scan_folder, folder)
            state.dbprep_scan_result = result
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            state.dbprep_scan_result = {}
        finally:
            page.pop('rows_state', None)

    page['scan_task'] = asyncio.create_task(_run())


# ===========================================================================
# Section 2.5 – KV Overview (what gets written to DB)
# ===========================================================================

def _render_kv_overview_section(state: AppState, page: dict) -> None:
    """
    Section 2.5 – Metadata overview and DB sync.

    Shows all key-value pairs that will be written to / are already in
    the database kv_blob. Updates live when selection in 2.3 changes.

    Symbols:
      🟢  new entry to be added, or existing entry explicitly kept
      🟡  already in DB, not in current selection – will be kept unchanged
      🔴  already in DB, explicitly deselected – will be deleted on sync
    """
    if state.dbprep_folder is None:
        return

    with section_card('📋', 'Metadata Overview & DB Sync', 'dbprep_kv_overview'):

        overview_container = ui.column().classes('w-full gap-0')

        def _refresh_overview() -> None:
            overview_container.clear()
            with overview_container:
                _render_kv_table(state, page, overview_container)

        # Register refresh callback so 2.3 can trigger it
        page['refresh_kv_overview'] = _refresh_overview

        # Initial render
        _refresh_overview()

        ui.separator().classes('q-my-sm')

        ui.button(
            '💾 Metadaten mit DB abgleichen',
            on_click=lambda: _sync_kv_to_db(state, page),
        ).props('no-caps color=primary')


def _render_kv_table(state: AppState, page: dict, container) -> None:
    """Render the KV overview table inside container."""
    db_path = state.dbprep_folder / 'birdnet_analysis.db'

    # Read existing kv from DB
    existing_kv: dict = {}
    if db_path.exists():
        from ..db_queries import get_kv_blob
        existing_kv = get_kv_blob(db_path) or {}

    # Selected from 2.3
    rows_state = page.get('rows_state', [])
    selected: dict = {
        r['key']: r['value']
        for r in rows_state
        if r['selected'] and r['key']
    }

    # Union of all keys
    all_keys = sorted(set(list(existing_kv.keys()) + list(selected.keys())))

    if not all_keys:
        ui.label('No metadata selected yet.').classes('text-caption text-grey-6')
        return

    # Header
    with ui.row().classes(
        'w-full px-2 py-1 bg-grey-2 text-caption font-bold gap-2 items-center'
    ):
        ui.label('Key').classes('w-48')
        ui.label('Value').classes('flex-grow')
        ui.label('').classes('w-8 text-center')  # symbol col

    # Per-key rows – track editable value inputs for sync
    page['kv_edit_values'] = {}

    for key in all_keys:
        in_db       = key in existing_kv
        in_selected = key in selected

        if in_selected:
            symbol = '🟢'
            symbol_tip = 'Will be added / kept'
            val = selected[key]
            editable = True
        elif in_db:
            symbol = '🟡'
            symbol_tip = 'Already in DB – kept unchanged (not selected)'
            val = existing_kv[key]
            editable = True   # allow editing even if not in selection
        else:
            continue  # should not happen

        with ui.row().classes(
            'w-full px-2 py-1 gap-2 items-center border-b border-grey-3'
        ):
            ui.label(key).classes('w-48 text-caption text-grey-9')

            if editable:
                vi = ui.input(value=str(val)).classes('flex-grow').props('dense outlined')
                # On edit → symbol turns green (explicit selection)
                def _mark_green(e, k=key):
                    page['kv_edit_values'][k] = e.sender.value
                vi.on('blur', _mark_green)
                vi.on('keydown.enter', _mark_green)
                page['kv_edit_values'][key] = str(val)
            else:
                ui.label(str(val)).classes('flex-grow text-caption')

            ui.label(symbol).classes('w-8 text-center').tooltip(symbol_tip)

    # Keys in DB but not in current selection AND not already shown above → red
    deselected_keys = [k for k in existing_kv if k not in selected and k not in all_keys]
    for key in sorted(deselected_keys):
        with ui.row().classes(
            'w-full px-2 py-1 gap-2 items-center border-b border-grey-3 bg-red-1'
        ):
            ui.label(key).classes('w-48 text-caption text-grey-9')
            ui.label(str(existing_kv[key])).classes('flex-grow text-caption text-grey-6')
            ui.label('🔴').classes('w-8 text-center').tooltip('Will be deleted on sync')


def _sync_kv_to_db(state: AppState, page: dict) -> None:
    """Write selected KV pairs to db_meta_data.kv_blob, delete deselected."""
    db_path = state.dbprep_folder / 'birdnet_analysis.db'
    if not db_path.exists():
        ui.notify(
            'Please create the database first by configuring GPS and UTC method below.',
            type='warning',
        )
        return

    from ..db_queries import get_kv_blob
    existing_kv = get_kv_blob(db_path) or {}

    rows_state  = page.get('rows_state', [])
    edit_values = page.get('kv_edit_values', {})

    selected = {
        r['key']: edit_values.get(r['key'], str(r['value']))
        for r in rows_state
        if r['selected'] and r['key']
    }

    # Start from existing, apply selected (overwrite), remove deselected
    # Start from existing DB values
    new_kv = dict(existing_kv)
    # Apply selected values (overwrite or add)
    new_kv.update(selected)
    # Apply manual edits from kv_edit_values (yellow entries that were edited)
    for k, v in edit_values.items():
        if k in new_kv:
            new_kv[k] = v

    set_db_meta_data(db_path, kv_blob=new_kv)
    ui.notify('Metadata synced to database.', type='positive')

    if page.get('refresh_kv_overview'):
        page['refresh_kv_overview']()


# ===========================================================================
# Section 2.6 – UTC Start Time Method
# ===========================================================================

def _render_utc_section(state: AppState, page: dict) -> None:
    """
    Section 2.6 – UTC start time method selection.

    Part A: Dropdown with available methods (from utc_methods table + scan).
    Part B: Global time offset input.
    Part C: Scrollable preview table (UTC / local time with DST / filename).
    """
    if state.dbprep_folder is None:
        return

    with section_card('🕐', 'UTC Start Time Method', 'dbprep_utc'):

        db_path = state.dbprep_folder / 'birdnet_analysis.db'

        # Read current method from DB if in edit mode
        current_method = None
        current_offset = '+00:00:00'
        if db_path.exists():
            meta = get_db_meta_data(db_path)
            if meta:
                current_method = meta.get('utc_time_method')
                current_offset = meta.get('time_offset', '+00:00:00')

        # ── Part A: Method dropdown ───────────────────────────────────────

        # Build options from scan result (which sources yielded timestamps?)
        available_methods: list[str] = []
        scan = state.dbprep_scan_result or {}

        if 'timestamp_utc' in scan:
            sources = scan['timestamp_utc_source'][1] if 'timestamp_utc_source' in scan else []
            if 'GUANO:Timestamp' in sources:
                available_methods.append('GUANO_TIMESTAMP')
            if 'ICMT' in sources:
                available_methods.append('ICMT_TIMESTAMP')

        # Always offer filename and filesystem as options
        if available_methods == []:
            available_methods = ['GUANO_TIMESTAMP', 'ICMT_TIMESTAMP']
        available_methods += ['FILENAME_PATTERN', 'FILESYSTEM_CTIME']
        # Deduplicate while preserving order
        seen_m: set = set()
        method_options = []
        for m in available_methods:
            if m not in seen_m:
                method_options.append(m)
                seen_m.add(m)

        # Mark best candidate
        best = method_options[0] if method_options else None
        option_labels = {
            m: (f'{m}  ← Empfehlung' if m == best else m)
            for m in method_options
        }

        ui.label('Select the method used to extract the UTC start time from audio files.') \
            .classes('text-caption text-grey-8 q-mb-xs')

        method_select = ui.select(
            options={m: option_labels[m] for m in method_options},
            value=current_method or best,
            label='UTC Time Method',
        ).classes('w-80').props('outlined dense')

        # ── Part B: Global time offset ────────────────────────────────────

        ui.label('Global time offset (applied to all extracted timestamps):') \
            .classes('text-caption text-grey-8 q-mt-sm q-mb-xs')

        offset_input = ui.input(
            label='Offset',
            value=current_offset,
            placeholder='+00:00:00  or  -01:30:00',
        ).classes('w-48').props('outlined dense')

        ui.label('Format: +HH:MM:SS or -HH:MM:SS').classes('text-caption text-grey-6')

        # ── Save method + offset button ───────────────────────────────────

        def _save_method() -> None:
            method = method_select.value
            offset = offset_input.value.strip() or '+00:00:00'
            state.dbprep_pending_method = method
            state.dbprep_pending_offset = offset
            ui.notify(f'Method "{method}" staged – click Confirm to save.', type='info')
            preview_container.clear()
            with preview_container:
                _render_utc_preview(state, method, offset)
            if page.get('refresh_confirm'):
                page['refresh_confirm']()
                
        ui.button('💾 Save Method & Offset', on_click=_save_method) \
            .props('no-caps color=primary').classes('q-mt-sm')

        ui.separator().classes('q-my-sm')

        # ── Part C: Preview table ─────────────────────────────────────────

        preview_container = ui.column().classes('w-full')
        with preview_container:
            _render_utc_preview(
                state,
                current_method or best,
                current_offset,
            )

        # Live update preview on method/offset change
        method_select.on(
            'update:model-value',
            lambda e: _refresh_preview(state, e.args, offset_input.value, preview_container),
        )
        offset_input.on(
            'blur',
            lambda e: _refresh_preview(state, method_select.value, e.sender.value, preview_container),
        )


def _refresh_preview(
    state: AppState,
    method: str,
    offset: str,
    container,
) -> None:
    container.clear()
    with container:
        _render_utc_preview(state, method, offset)


def _render_utc_preview(
    state: AppState,
    method: Optional[str],
    offset_str: str,
) -> None:
    """
    Render the 3-column UTC preview table.

    Columns: UTC start time | Local time with DST (from GPS+timezonefinder) | Filename
    Marks DST transitions with a visual separator.
    """
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfo

    if not state.dbprep_scan_result or not method:
        ui.label('No preview available.').classes('text-caption text-grey-6')
        return

    # Parse offset string → timedelta
    try:
        sign = -1 if offset_str.startswith('-') else 1
        parts = offset_str.lstrip('+-').split(':')
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
        offset_td = sign * timedelta(hours=h, minutes=m, seconds=s)
    except Exception:
        offset_td = timedelta(0)

    # Gather (filename, timestamp_utc) pairs from scan
    scan = state.dbprep_scan_result
    ts_entry = scan.get('timestamp_utc')
    if not ts_entry:
        ui.label('No timestamps found in metadata.').classes('text-caption text-grey-6')
        return

    files_list, values_list = ts_entry
    rows: list[tuple[str, object]] = []
    for fname, ts in zip(files_list, values_list):
        if ts is not None:
            rows.append((fname, ts))
    rows.sort(key=lambda x: x[1])

    if not rows:
        ui.label('No timestamps available.').classes('text-caption text-grey-6')
        return

    # Determine timezone from GPS
    tz: Optional[ZoneInfo] = None
    db_path = state.dbprep_folder / 'birdnet_analysis.db'
    gps_lat, gps_lon = 90.0, 0.0
    if db_path.exists():
        meta = get_db_meta_data(db_path)
        if meta:
            gps_lat = meta.get('gps_lat', 90.0)
            gps_lon = meta.get('gps_lon', 0.0)

    if gps_lat != 90.0:
        try:
            from timezonefinder import TimezoneFinder
            tf = TimezoneFinder()
            tz_name = tf.timezone_at(lat=gps_lat, lng=gps_lon)
            if tz_name:
                tz = ZoneInfo(tz_name)
        except Exception as e:
            logger.warning(f"timezonefinder failed: {e}")

    # Table header
    with ui.row().classes(
        'w-full px-2 py-1 bg-grey-2 text-caption font-bold gap-2 items-center'
    ):
        ui.label('UTC').classes('w-44')
        ui.label('Local time (with DST)').classes('w-44')
        ui.label('Filename').classes('flex-grow')

    prev_is_dst: Optional[bool] = None

    with ui.column().classes('w-full gap-0').style(
        'max-height: 600px; overflow-y: auto;'
        'border: 1px solid #e0e0e0; border-radius: 4px;'
    ):
        for fname, ts in rows:
            # Apply offset
            utc_ts = ts + offset_td

            # Local time
            if tz:
                local_ts = utc_ts.astimezone(tz)
                is_dst   = bool(local_ts.dst())
                tz_label = local_ts.strftime('%Z')
                local_str = local_ts.strftime(f'%Y-%m-%d %H:%M:%S {tz_label}')
            else:
                local_ts  = utc_ts
                is_dst    = False
                local_str = utc_ts.strftime('%Y-%m-%d %H:%M:%S UTC')

            # DST transition marker
            if prev_is_dst is not None and is_dst != prev_is_dst:
                label = '⬆ Sommerzeit beginnt' if is_dst else '⬇ Winterzeit beginnt'
                with ui.row().classes(
                    'w-full px-2 py-1 bg-orange-2 text-caption font-bold'
                ):
                    ui.label(label).classes('text-orange-9')
            prev_is_dst = is_dst

            with ui.row().classes(
                'w-full px-2 py-1 gap-2 items-center border-b border-grey-3'
            ):
                ui.label(utc_ts.strftime('%Y-%m-%d %H:%M:%S')).classes('w-44 text-caption')
                ui.label(local_str).classes('w-44 text-caption')
                ui.label(fname).classes('flex-grow text-caption text-grey-8')
         
# ===========================================================================
# Section 5 – Confirm configuration / create DB
# ===========================================================================

def _render_confirm_section(state: AppState, page: dict) -> None:
    """
    Section 5 – Confirm configuration and create / update database.

    In 'create' mode: DB is only created when the user clicks Confirm.
    In 'edit' mode:   Confirm writes any pending changes to the existing DB.

    GPS and UTC method are staged in page['pending_gps'] and
    page['pending_method'] / page['pending_offset'] until confirmed.

    Also contains the Danger Zone button to delete all detections,
    which re-enables editing of lat/lon and utc_time_method.
    """
    if state.dbprep_folder is None:
        return

    db_path = state.dbprep_folder / DB_FILENAME

    mode_label = 'Create Database' if state.dbprep_mode == 'create' else 'Update Database'
    with section_card('💾', mode_label, 'dbprep_confirm'):

        # ── Status display ────────────────────────────────────────────────
        has_gps    = state.dbprep_pending_gps is not None or (
            db_path.exists() and _db_has_gps(db_path)
        )
        has_method = state.dbprep_pending_method is not None or (
            db_path.exists() and _db_has_method(db_path)
        )

        with ui.row().classes('gap-6 q-mb-sm'):
            _status_chip('GPS / Location', has_gps)
            _status_chip('UTC Time Method', has_method)

        if not has_gps or not has_method:
            ui.label(
                '⚠️ Both GPS location and UTC time method must be configured '
                'before the database can be created.'
            ).classes('text-caption text-orange-8 q-mb-sm')

        # ── Confirm button ────────────────────────────────────────────────
        btn_label = '💾 Create Database' if state.dbprep_mode == 'create' else '💾 Update Database'
        confirm_btn = ui.button(
            btn_label,
            on_click=lambda: _confirm_configuration(state, page, status_label),
        ).props('no-caps color=positive')
        confirm_btn.set_enabled(has_gps and has_method)

        status_label = ui.label('').classes('text-caption text-grey-7 q-mt-xs')

    # ── Danger Zone ───────────────────────────────────────────────────────
    with section_card('⚠️', 'Danger Zone', 'dbprep_danger'):

        ui.label(
            'Delete all detections from this database. This allows you to change '
            'the GPS location and UTC time method. The audio files and their '
            'metadata are not affected. The scouting flight must be re-run afterwards.'
        ).classes('text-caption text-orange-9 q-mb-sm')

        if not db_path.exists():
            ui.label('No database exists yet for this folder.') \
                .classes('text-caption text-grey-6')
            return

        # Show detection count
        det_count = _count_detections(db_path)
        ui.label(f'Current detections in database: {det_count}') \
            .classes('text-caption text-grey-8 q-mb-sm')

        with ui.row().classes('items-center gap-3'):
            ui.button(
                '🗑 Delete all detections',
                on_click=lambda: _confirm_delete_detections(state, page, det_count_label),
            ).props('no-caps color=negative')
            det_count_label = ui.label(f'{det_count} detections').classes('text-caption text-grey-7')


def _status_chip(label: str, ok: bool) -> None:
    """Small status indicator chip."""
    icon  = '✅' if ok else '❌'
    color = 'text-positive' if ok else 'text-negative'
    ui.label(f'{icon} {label}').classes(f'text-caption font-bold {color}')


def _db_has_gps(db_path: Path) -> bool:
    """Return True if db_meta_data has a non-Nordpol GPS position."""
    meta = get_db_meta_data(db_path)
    if not meta:
        return False
    return meta.get('gps_lat', 90.0) != 90.0 or meta.get('gps_lon', 0.0) != 0.0


def _db_has_method(db_path: Path) -> bool:
    """Return True if db_meta_data has a utc_time_method set."""
    meta = get_db_meta_data(db_path)
    if not meta:
        return False
    return bool(meta.get('utc_time_method'))


def _count_detections(db_path: Path) -> int:
    """Return number of detections in the database."""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute('SELECT COUNT(*) FROM detections').fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _confirm_configuration(
    state: AppState,
    page: dict,
    status_label,
) -> None:
    """
    Write all pending configuration to the database, creating it if needed.
    Called when the user clicks Confirm.
    """
    db_path = state.dbprep_folder / DB_FILENAME

    # Create DB if not yet existing
    if not db_path.exists():
        init_database(str(db_path))

    # Write pending GPS
    if state.dbprep_pending_gps is not None:
        lat, lon = state.dbprep_pending_gps
        state.dbprep_pending_gps = None
        set_db_meta_data(db_path, gps_lat=lat, gps_lon=lon)

    if state.dbprep_pending_method is not None:
        method = state.dbprep_pending_method
        offset = state.dbprep_pending_offset
        state.dbprep_pending_method = None
        state.dbprep_pending_offset = '+00:00:00'
        set_db_meta_data(db_path, utc_time_method=method, time_offset=offset)

    logger.info(f"DB configuration confirmed for {state.dbprep_folder.name}")
    ui.notify('Configuration saved – folder is now ready for Scouting Flight.', type='positive')
    status_label.set_text(f'Last saved: {_now_str()}')


def _confirm_delete_detections(
    state: AppState,
    page: dict,
    det_count_label,
) -> None:
    """Show confirmation dialog before deleting all detections."""

    async def _do_delete() -> None:
        db_path = state.dbprep_folder / DB_FILENAME
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute('DELETE FROM detections')
            conn.execute('DELETE FROM processing_status')
            conn.commit()
            conn.close()
            ui.notify('All detections deleted. You can now change GPS and UTC method.', type='positive')
            det_count_label.set_text('0 detections')
            logger.info(f"All detections deleted for {state.dbprep_folder.name}")
        except Exception as e:
            ui.notify(f'Error deleting detections: {e}', type='negative')
            logger.error(f"Delete detections failed: {e}")

    with ui.dialog() as dlg, ui.card():
        ui.label('⚠️ Delete all detections?').classes('text-h6 text-negative')
        ui.label(
            'This cannot be undone. The scouting flight must be re-run '
            'to rebuild the detections.'
        ).classes('text-body2 q-my-sm')
        with ui.row().classes('gap-3 justify-end w-full'):
            ui.button('Cancel', on_click=dlg.close).props('no-caps flat')
            ui.button(
                'Delete',
                on_click=lambda: [dlg.close(), asyncio.create_task(_do_delete())],
            ).props('no-caps color=negative')
    dlg.open()


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _update_position(
    lat: float, lon: float,
    m, lat_input, lon_input,
    gps_map_ref: dict,
    state: AppState,
    page: dict,
) -> None:
    """Move/create red marker, update inputs, stage as pending."""
    final_marker = gps_map_ref.get('final_marker')
    if final_marker is None:
        final_marker = m.marker(latlng=(lat, lon))
        final_marker.run_method(
            ':setIcon',
            "L.icon({iconUrl: 'https://raw.githubusercontent.com/pointhi/"
            "leaflet-color-markers/master/img/marker-icon-red.png',"
            "iconSize:[25,41],iconAnchor:[12,41]})"
        )
        gps_map_ref['final_marker'] = final_marker
    else:
        final_marker.move(lat, lon)
    lat_input.set_value(round(lat, 6))
    lon_input.set_value(round(lon, 6))
    state.dbprep_pending_gps = (lat, lon)
    logger.debug(f"GPS staged: {lat:.6f}, {lon:.6f}")


def _try_manual_input(lat_input, lon_input, m, gps_map_ref, state, page) -> None:
    try:
        lat = float(lat_input.value)
        lon = float(lon_input.value)
        _update_position(lat, lon, m, lat_input, lon_input, gps_map_ref, state, page)
    except (TypeError, ValueError):
        pass


def _update_map_markers(
    state: AppState,
    page: dict,
    m,
    lat_input,
    lon_input,
    gps_map_ref: dict,
    gps_warning_label,
) -> None:
    """
    Called after scan completes. Removes old markers, adds new blue markers
    from metadata, sets red marker if GPS is unambiguous.
    """
    # Remove old blue markers
    for marker in gps_map_ref.get('blue_markers', []):
        try:
            m.remove_layer(marker)
        except Exception:
            pass
    gps_map_ref['blue_markers'] = []

    # Remove old red marker
    if gps_map_ref.get('final_marker') is not None:
        try:
            m.remove_layer(gps_map_ref['final_marker'])
        except Exception:
            pass
        gps_map_ref['final_marker'] = None

    # Read current DB position
    current_lat, current_lon = 90.0, 0.0
    db_path = state.dbprep_folder / 'birdnet_analysis.db' if state.dbprep_folder else None
    if db_path and db_path.exists():
        meta = get_db_meta_data(db_path)
        if meta:
            current_lat = meta.get('gps_lat', 90.0)
            current_lon = meta.get('gps_lon', 0.0)

    # Collect distinct GPS points from scan
    meta_points: list[tuple[float, float]] = []
    if state.dbprep_scan_result:
        lat_entry = state.dbprep_scan_result.get('gps_lat')
        lon_entry = state.dbprep_scan_result.get('gps_lon')
        if lat_entry and lon_entry:
            seen: set = set()
            for lat, lon in zip(lat_entry[1], lon_entry[1]):
                try:
                    pt = (float(lat), float(lon))
                    if pt not in seen:
                        seen.add(pt)
                        meta_points.append(pt)
                except (TypeError, ValueError):
                    pass

    # Add blue markers
    for lat, lon in meta_points:
        bm = m.marker(latlng=(lat, lon))
        bm.run_method(
            ':setIcon',
            "L.icon({iconUrl: 'https://raw.githubusercontent.com/pointhi/"
            "leaflet-color-markers/master/img/marker-icon-blue.png',"
            "iconSize:[25,41],iconAnchor:[12,41]})"
        )
        gps_map_ref['blue_markers'].append(bm)

    # Determine red marker position and map center
    all_identical = len(meta_points) > 0 and all(p == meta_points[0] for p in meta_points)

    if current_lat != 90.0:
        # DB has confirmed position
        _update_position(current_lat, current_lon, m, lat_input, lon_input, gps_map_ref, state, page)
        m.set_center((current_lat, current_lon))
        m.set_zoom(13)
        gps_warning_label.set_visibility(False)
    elif meta_points and all_identical:
        # All identical → use as suggestion
        lat, lon = meta_points[0]
        _update_position(lat, lon, m, lat_input, lon_input, gps_map_ref, state, page)
        m.set_center((lat, lon))
        m.set_zoom(13)
        gps_warning_label.set_visibility(False)
    elif meta_points:
        # Points differ → center on average, no red marker
        clat = sum(p[0] for p in meta_points) / len(meta_points)
        clon = sum(p[1] for p in meta_points) / len(meta_points)
        m.set_center((clat, clon))
        m.set_zoom(13)
        lat_input.set_value(90.0)
        lon_input.set_value(0.0)
        gps_warning_label.set_text(
            '⚠️ GPS coordinates differ between files – '
            'please select a position by clicking a marker or the map.'
        )
        gps_warning_label.set_visibility(True)
    else:
        gps_warning_label.set_visibility(False)
