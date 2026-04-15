"""
Landing Page – application entry point.

Route: /

Sections:
  1. Basic principles   (one folder = one device = one location = one DB)
  2. Navigation guide   (card per page with short description + link)
  3. Application description (placeholder)
"""

from nicegui import ui, app as nicegui_app

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.page_header import page_header
from ..gui_elements.section_card import section_card


# ---------------------------------------------------------------------------
# Page registration
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


@ui.page('/')
async def landing_page() -> None:
    state = _get_state()
    create_layout(state)

    with ui.row().classes('items-center gap-3 q-mb-md'):
        ui.image('/static/icons/helipad.svg').style('width:48px; height:48px;')
        ui.label('Landing Page').classes('text-h4 font-bold')

    # -----------------------------------------------------------------------
    # Section 1: Basic principles
    # -----------------------------------------------------------------------
    with section_card('📐', 'Basic Principles', 'landing_principles'):

        ui.label(
            'birdnet-copter organises audio recordings and detections according '
            'to the following principles:'
        ).classes('text-body2 q-mb-sm')

        principles = [
            (
                'One folder = one device = one location = one database',
                'All audio files in a folder are treated as recordings from a single '
                'device at a single geographic location. One SQLite database file is '
                'created per folder.',
            ),
            (
                'No temporal overlap within a folder',
                'Audio files in a folder should not overlap in time. If recordings '
                'from different time periods are mixed, the database entries may be '
                'ambiguous.',
            ),
            (
                'Multiple folders = multiple databases = one global analysis',
                'The typical workflow uses several folders (locations, sessions) '
                'simultaneously. All selected databases are merged into a temporary '
                'global view for analysis across sites.',
            ),
        ]

        for i, (title, body) in enumerate(principles, 1):
            with ui.row().classes('items-start gap-3 q-mb-sm'):
                ui.label(f'{i}.').classes('text-body1 font-bold text-grey-7 q-mt-xs')
                with ui.column().classes('gap-0'):
                    ui.label(title).classes('text-body1 font-bold')
                    ui.label(body).classes('text-body2 text-grey-8')
                    
    # -----------------------------------------------------------------------
    # Section 2: Navigation guide
    # -----------------------------------------------------------------------
    with section_card('🧭', 'Where do I go?', 'landing_navigation'):

        ui.label(
            'Select the page that matches your current task:'
        ).classes('text-body2 q-mb-md')

        nav_cards = [
            (
                '🛠', 'Hangar',
                '/hangar',
                'Technical configuration: set the server host, root path, GPU '
                'settings and global index.',
            ),
            (
                '/static/icons/db_icon_32.svg', 'DB Configuration',
                '/db-config',
                'Prepare a folder for analysis: set GPS location, UTC time method '
                'and metadata for a recording session.',
            ),
            (
                '🚁', 'Scouting Flight',
                '/scouting',
                'Run BirdNET analysis on one or more prepared folders. Monitor '
                'progress and manage the job queue.',
            ),
            (
                '🗺', 'Exploration Area',
                '/exploration',
                'Select one or more databases and explore the results: species list, '
                'recording files and aggregate statistics.',
            ),
            (
                '🎧', 'Audio Player',
                '/audio-player',
                'Listen to detections, filter by species, date, confidence and more. '
                'Navigate through the audio with full playback controls.',
            ),
            (
                '🕐', 'Date-Time-Map',
                '/heatmap',
                'Visualise detections over time as a calendar heatmap. Explore '
                'temporal patterns across sessions.',
            ),
        ]

        with ui.grid(columns=2).classes('w-full gap-4'):
            for icon, name, path, description in nav_cards:
                with ui.card().classes('w-full q-pa-md'):
                    with ui.row().classes('items-center gap-2 q-mb-xs'):
                        if icon.startswith('/static/'):
                            import re
                            from pathlib import Path as _Path
                            _svg_path = _Path(__file__).parent.parent / 'pages' / icon.lstrip('/')
                            try:
                                _svg = _svg_path.read_text(encoding='utf-8')
                                _svg = _svg.replace('<svg ', '<svg style="display:block;" ', 1)
                                ui.html(_svg)
                            except Exception:
                                ui.label('?').classes('text-h5')
                        else:
                            ui.label(icon).classes('text-h5')
                        ui.label(name).classes('text-h6 font-bold')
                    ui.label(description).classes('text-body2 text-grey-8 q-mb-sm')
                    ui.button(
                        f'Go to {name} →',
                        on_click=lambda p=path: ui.navigate.to(p),
                    ).props('no-caps flat color=primary')

    # -----------------------------------------------------------------------
    # Section 3: Application description (placeholder)
    # -----------------------------------------------------------------------
    with section_card('📖', 'Application Description', 'landing_description'):
        ui.label('Coming soon.').classes('text-body2 text-grey-6')