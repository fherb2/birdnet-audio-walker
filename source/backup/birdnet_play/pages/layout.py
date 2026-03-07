"""
Shared page layout for BirdNET Play.

Call create_layout(app_state) at the top of every @ui.page handler.
Returns a reference to the left drawer so pages can add nav items if needed
(not normally necessary).

Layout structure:
    ui.header  (full width, 3 columns)
        col-left  : hamburger button → opens left_drawer overlay
        col-center: root path (row 1) / active db path (row 2)
        col-right : access mode (row 1) / spinner when busy (row 2)
    ui.left_drawer (overlay, hidden by default)
        navigation menu entries
"""

from nicegui import ui, app as nicegui_app, context

from ..app_state import AppState


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _relative_db_label(app_state: AppState) -> str:
    """
    Build the DB path label for the header center column.

    Rules:
    - No active DB → '–'
    - DB folder is root_path itself → '../<foldername>'
    - DB folder is inside root_path → './<relative path>'
    """
    if app_state.active_db is None:
        return '–'

    db_folder = app_state.active_db.parent
    try:
        rel = db_folder.relative_to(app_state.root_path)
        # rel == '.' means the db sits directly in root_path
        if str(rel) == '.':
            return f'../{app_state.root_path.name}'
        return f'./{rel}'
    except ValueError:
        # active_db is outside root_path (shouldn't happen, but be safe)
        return str(db_folder)


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
    # Navigation drawer (hamburger overlay)
    # ------------------------------------------------------------------
    with ui.left_drawer(value=False).classes('bg-grey-1 p-4') as nav_drawer:
        ui.label('Navigation').classes('text-h6 q-mb-md')
        ui.separator()

        nav_items = [
            ('📂  Database Overview', '/'),
            ('🎵  Audio Player',      '/audio-player'),
            ('📊  Activity Heatmap',  '/heatmap'),
        ]

        for label, path in nav_items:
            ui.item(label, on_click=lambda p=path: ui.navigate.to(p)) \
                .classes('cursor-pointer rounded hover:bg-grey-3 q-py-xs')

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    with ui.header().classes('items-center justify-between bg-primary text-white px-4 py-1'):

        # --- left column: hamburger ---
        ui.button(icon='menu', on_click=nav_drawer.toggle) \
            .props('flat dense round color=white')

        # --- center column: paths ---
        with ui.column().classes('items-center gap-0'):
            root_label = ui.label(str(app_state.root_path)) \
                .classes('text-caption opacity-80')
            db_label = ui.label(_relative_db_label(app_state)) \
                .classes('text-body2 font-bold')

        # --- right column: access mode + spinner ---
        with ui.column().classes('items-end gap-0'):
            access_text = '🔒 read-only' if app_state.read_only else '✏️ read-write'
            ui.label(access_text).classes('text-caption')

            # Spinner row – visible only while generation is running
            with ui.row().classes('items-center gap-1') as spinner_row:
                spinner = ui.spinner(size='sm').classes('text-white')
                ui.label('processing…').classes('text-caption')

            # Timer updates spinner visibility every 500 ms
            def _update_spinner():
                running = app_state.audio_generation_running
                spinner_row.set_visibility(running)

            t_spinner = ui.timer(0.5, _update_spinner)

    # ------------------------------------------------------------------
    # Timer to keep center path labels in sync with state changes
    # (e.g. after a DB switch on the overview page)
    # ------------------------------------------------------------------
    def _update_paths():
        root_label.set_text(str(app_state.root_path))
        db_label.set_text(_relative_db_label(app_state))

    t_paths = ui.timer(1.0, _update_paths)

    async def _stop_timers():
        t_spinner.cancel()
        t_paths.cancel()

    context.client.on_disconnect(_stop_timers)

    return nav_drawer