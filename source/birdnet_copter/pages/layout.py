"""
Shared page layout for BirdNET Copter.

Call create_layout(app_state) at the top of every @ui.page handler.
Returns a reference to the left drawer so pages can add nav items if needed
(not normally necessary).

Layout structure:
    ui.header  (full width, 3 columns)
        col-left  : hamburger button → opens left_drawer overlay
        col-center: root path (row 1) / active db path (row 2)
        col-right : access mode (row 1) / spinner when busy (row 2)
                    + GPU error button when app_state.gpu_error is set
    ui.left_drawer (overlay, hidden by default)
        navigation menu entries
"""

from nicegui import ui, app as nicegui_app, context

from ..app_state import AppState


# ---------------------------------------------------------------------------
# Header size configuration  ('sm' | 'md' | 'lg')
# ---------------------------------------------------------------------------
HEADER_SIZE = 'md'

# Spinner-Icon static and animated
ICON_STATIC   = 'static/icons/birdnet_copter_spinner_static.svg'
ICON_ANIMATED = 'static/icons/birdnet_copter_spinner_animated.svg'

_HEADER_SIZES = {
    'sm': {'py': 'py-1', 'icon': 'w-5 h-5',  'title': 'text-h6', 'body': 'text-body2', 'caption': 'text-caption', 'spinner': 'sm'},
    'md': {'py': 'py-3', 'icon': 'w-8 h-8',  'title': 'text-h5', 'body': 'text-body1', 'caption': 'text-body2',   'spinner': 'md'},
    'lg': {'py': 'py-5', 'icon': 'w-10 h-10', 'title': 'text-h4', 'body': 'text-h6',   'caption': 'text-body1',   'spinner': 'lg'},
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _relative_db_label(app_state: AppState) -> str:
    if app_state.active_db_is_global:
        if app_state.global_index_path is not None:
            return f"{app_state.global_index_path} (global)"
        return "– (global)"

    db = app_state.active_db
    if db is None or not db.exists():
        return '⚠️ No DB selected'

    # If temp_db_process is currently running, don't read yet
    try:
        tasks = app_state.shared_state.get('tasks', {}) if app_state.shared_state else {}
        if tasks.get('temp_db', {}).get('running', False):
            return '⏳ Loading…'
    except Exception:
        pass

    try:
        import sqlite3
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM source_dbs").fetchone()[0]
        if count == 1:
            row = conn.execute("SELECT display_name FROM source_dbs LIMIT 1").fetchone()
            name = row[0] if row else '?'
            conn.close()
            return f'Single DB {name} loaded'
        conn.close()
        if count == 0:
            return '⚠️ No DB selected'
        return f'{count} DBs loaded'
    except Exception:
        return '⚠️ No DB selected'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_layout(app_state: AppState) -> ui.left_drawer:
    """
    Render the shared header and navigation drawer.

    Must be called inside a @ui.page handler, before any page content.

    Args:
        app_state: The global AppState instance.

    Returns:
        The ui.left_drawer instance (overlay nav menu).
        Pages normally don't need this reference.
    """

    # ------------------------------------------------------------------
    # Page title (for Browser-Tabs)
    # ------------------------------------------------------------------
    ui.page_title('birdnet-copter')

    # ------------------------------------------------------------------
    # Navigation drawer (hamburger overlay)
    # ------------------------------------------------------------------
    with ui.left_drawer(value=False).classes('bg-grey-1 p-4') as nav_drawer:
        ui.label('Navigation').classes('text-h6 q-mb-md')
        ui.separator()

        nav_items = [
            ('🛠',  'Hangar',            '/'),
            ('🚁',  'Scouting Flight',   '/scouting'),
            ('🗺',  'Exploration Area',  '/exploration'),
            ('🎧',  'Audio Player',      '/audio-player'),
            ('🕐',  'Date-Time-Map',     '/heatmap'),
        ]

        for icon, label, path in nav_items:
            ui.item(
                f'{icon}  {label}',
                on_click=lambda p=path: ui.navigate.to(p),
            ).classes('cursor-pointer rounded hover:bg-grey-3 q-py-xs')

    # ------------------------------------------------------------------
    # GPU error dialog (created before header so the button can ref it)
    # ------------------------------------------------------------------
    with ui.dialog() as gpu_error_dialog, ui.card().classes('w-2/3'):
        ui.label('⚠️ CUDA GPU-Fehler erkannt').classes('text-h6 text-red-8')
        ui.separator()

        err = app_state.gpu_error  # snapshot – None or dict at page-load time
        msg_text  = err['message']  if err else ''
        kill_text = err['kill_cmd'] if err else ''

        ui.label(msg_text).classes('q-mt-sm')
        ui.label('Auszuführender Befehl auf dem HOST:').classes('q-mt-md font-bold')
        ui.code(kill_text).classes('w-full')
        ui.separator().classes('q-my-sm')
        ui.label('⚠️ Dieser Fehler bleibt bis zum Programm-Neustart aktiv.') \
            .classes('text-caption text-red-6')

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    initial_color = 'bg-red-8' if app_state.gpu_error else 'bg-primary'
    
    hs = _HEADER_SIZES[HEADER_SIZE]

    with ui.header().classes(
        f'items-center justify-between {initial_color} text-white px-4 {hs["py"]}'
    ) as header:

        # Grid with 3 equal columns, all vertically centered
        with ui.element('div').classes('w-full grid grid-cols-3 items-center'):

            # --- left column: hamburger + title ---
            with ui.row().classes('items-center gap-2'):
                ui.button(icon='menu', on_click=nav_drawer.toggle) \
                    .props('flat dense round color=white')
                header_icon = ui.image(ICON_STATIC).classes(hs['icon'])
                ui.label('birdnet-copter').classes(f'{hs["title"]} font-bold')

            # --- center column: paths ---
            with ui.column().classes('items-center gap-0'):
                root_label = ui.label(str(app_state.root_path)) \
                    .classes(f'{hs["caption"]} opacity-80')
                db_label = ui.label(_relative_db_label(app_state)) \
                    .classes(f'{hs["body"]} font-bold')

            # --- right column: access mode + spinner ---
            with ui.row().classes('items-center justify-end gap-3'):
                access_text = '🔒 read-only' if app_state.read_only else '✏️ read-write'
                ui.label(access_text).classes(hs['caption'])

        # GPU error button – outside the grid so it doesn't affect row height
        gpu_err_btn = ui.button(
            '⚠️ GPU-FEHLER – Details',
            on_click=gpu_error_dialog.open,
        ).props('flat color=white').classes('animate-pulse')
        gpu_err_btn.set_visibility(bool(app_state.gpu_error))

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _update_spinner():
        try:
            running = app_state.is_busy()
            header_icon.set_source(ICON_ANIMATED if running else ICON_STATIC)
        except Exception:
            pass

    def _update_paths():
        try:
            root_label.set_text(str(app_state.root_path))
            db_label.set_text(_relative_db_label(app_state))
        except Exception:
            pass

    def _update_gpu_error_state():
        """
        Dynamically update header color and error button visibility.

        Runs every 2 s so the user sees the red header without a page reload
        when a GPU hang is detected during an active session.
        """
        try:
            has_error = bool(app_state.gpu_error)
            # Switch header color
            if has_error:
                header.classes(replace=f'items-center justify-between bg-red-8 text-white px-4 {hs["py"]}')
            else:
                header.classes(replace=f'items-center justify-between bg-primary text-white px-4 {hs["py"]}')
            # Show / hide error button
            gpu_err_btn.set_visibility(has_error)
        except Exception:
            pass

    t_spinner   = ui.timer(0.5, _update_spinner)
    t_paths     = ui.timer(1.0, _update_paths)
    t_gpu_error = ui.timer(2.0, _update_gpu_error_state)

    # ------------------------------------------------------------------
    # Auto-open dialog if gpu_error is already set at page load
    # ------------------------------------------------------------------
    if app_state.gpu_error:
        ui.timer(0.5, gpu_error_dialog.open, once=True)

    # ------------------------------------------------------------------
    # Cleanup timers on client disconnect
    # ------------------------------------------------------------------
    async def _stop_timers():
        t_spinner.cancel()
        t_paths.cancel()
        t_gpu_error.cancel()

    context.client.on_disconnect(_stop_timers)

    return nav_drawer