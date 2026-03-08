"""
Folder tree navigator for BirdNET Play.

Displays a filesystem tree rooted at a given path.
- Single click  : select folder as active database candidate
- Double click  : drill down (selected folder becomes new root)
- Up button     : navigate one level up (root moves to parent)

Each row shows:
  [folder name]  [audio-file count icon]  [db status icon]

DiskANN folders are hidden (name contains 'diskann', case-insensitive).

Audio file extensions considered:
    AUDIO_EXTENSIONS  (extend as needed)
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Callable, Optional

from nicegui import ui


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Extend this list to support additional audio formats
AUDIO_EXTENSIONS: set[str] = {
    '.wav', '.mp3', '.flac', '.ogg', '.aac',
    '.m4a', '.wma', '.aiff', '.aif',
}

DB_FILENAME = 'birdnet_analysis.db'

# Folders whose names contain this substring (case-insensitive) are hidden
DISKANN_MARKER = 'diskann'


# ---------------------------------------------------------------------------
# SVG icons  (32 × 32 px, inline)
# ---------------------------------------------------------------------------

def _svg(content: str) -> str:
    """Wrap SVG path content in a 32×32 viewBox."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="24" height="24" viewBox="0 0 32 32">'
        f'{content}'
        f'</svg>'
    )


# Audio file count icons
SVG_AUDIO_NONE = _svg(
    '<rect x="4" y="8" width="24" height="18" rx="2" '
    'fill="none" stroke="#aaa" stroke-width="2"/>'
    '<text x="16" y="22" text-anchor="middle" '
    'font-size="11" fill="#aaa">♪ 0</text>'
)

SVG_AUDIO_SOME = _svg(
    '<rect x="4" y="8" width="24" height="18" rx="2" '
    'fill="none" stroke="#555" stroke-width="2"/>'
    '<text x="16" y="22" text-anchor="middle" '
    'font-size="11" fill="#555">♪</text>'
)

# DB status icons
SVG_DB_ABSENT = _svg(
    '<ellipse cx="16" cy="18" rx="12" ry="7" '
    'fill="none" stroke="#aaa" stroke-width="2"/>'
    '<line x1="4" y1="18" x2="28" y2="18" '
    'stroke="#aaa" stroke-width="2"/>'
    '<ellipse cx="16" cy="11" rx="12" ry="5" '
    'fill="none" stroke="#aaa" stroke-width="2"/>'
)

SVG_DB_INCOMPLETE = _svg(
    '<ellipse cx="16" cy="18" rx="12" ry="7" '
    'fill="#fff3cd" stroke="#f0ad4e" stroke-width="2"/>'
    '<line x1="4" y1="18" x2="28" y2="18" '
    'stroke="#f0ad4e" stroke-width="2"/>'
    '<ellipse cx="16" cy="11" rx="12" ry="5" '
    'fill="#fff3cd" stroke="#f0ad4e" stroke-width="2"/>'
    '<text x="16" y="15" text-anchor="middle" '
    'font-size="10" fill="#856404">!</text>'
)

SVG_DB_COMPLETE = _svg(
    '<ellipse cx="16" cy="18" rx="12" ry="7" '
    'fill="#d4edda" stroke="#28a745" stroke-width="2"/>'
    '<line x1="4" y1="18" x2="28" y2="18" '
    'stroke="#28a745" stroke-width="2"/>'
    '<ellipse cx="16" cy="11" rx="12" ry="5" '
    'fill="#d4edda" stroke="#28a745" stroke-width="2"/>'
    '<text x="16" y="15" text-anchor="middle" '
    'font-size="10" fill="#155724">✓</text>'
)


# ---------------------------------------------------------------------------
# Folder analysis helpers
# ---------------------------------------------------------------------------

def _is_diskann(folder: Path) -> bool:
    """Return True if the folder should be hidden (DiskANN marker in name)."""
    return DISKANN_MARKER in folder.name.lower()


def _count_audio_files(folder: Path) -> int:
    try:
        return sum(
            1 for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
        )
    except PermissionError:
        return -1  # sentinel: no access


def _check_db_status(folder: Path) -> str:
    """
    Check database completeness for the folder.

    Returns:
        'absent'     – no birdnet_analysis.db present
        'incomplete' – db exists but not all audio files are registered
        'complete'   – db exists and all audio files are registered
    """
    try:
        db_path = folder / DB_FILENAME
        if not db_path.exists():
            return 'absent'

        audio_files = {
            f.name for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
        }
        if not audio_files:
            # No audio files → db exists, nothing to index → treat as complete
            return 'complete'

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT filename FROM metadata")
        db_files = {row['filename'] for row in cursor.fetchall()}
        conn.close()

        return 'complete' if audio_files <= db_files else 'incomplete'

    except PermissionError:
        return 'no_access'

    except Exception:
        return 'incomplete'


async def _analyse_folder(folder: Path, loop: asyncio.AbstractEventLoop) -> dict:
    """
    Run folder analysis in a thread-pool executor.

    Returns a dict with keys: path, audio_count, db_status.
    """
    audio_count, db_status = await asyncio.gather(
        loop.run_in_executor(None, _count_audio_files, folder),
        loop.run_in_executor(None, _check_db_status, folder),
    )
    return {'path': folder, 'audio_count': audio_count, 'db_status': db_status}


# ---------------------------------------------------------------------------
# FolderTree component
# ---------------------------------------------------------------------------

class FolderTree:
    """
    Filesystem folder tree navigator.

    Args:
        root_path:          Initial root directory to display.
        on_select:          Called with the selected Path when user clicks a row.
        on_root_change:     Called with the new root Path when root changes
                            (drill-down or up-navigation).
    """

    def __init__(
        self,
        root_path: Path,
        on_select: Optional[Callable[[Path], None]] = None,
        on_root_change: Optional[Callable[[Path], None]] = None,
        show_extras: bool = True,
        min_root: Optional[Path] = None,
        on_add_job: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self._root = root_path
        self._selected: Optional[Path] = None
        self._on_select = on_select
        self._on_root_change = on_root_change
        self._show_extras = show_extras
        self._min_root = min_root
        self._on_add_job = on_add_job
        self._rows: dict[Path, ui.row] = {}
        self._container: Optional[ui.element] = None
        self._render()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-render the tree (e.g. after external root change)."""
        self._render()

    def set_root(self, new_root: Path) -> None:
        """Programmatically change the root and re-render."""
        self._root = new_root
        self._selected = None
        self._render()
        if self._on_root_change:
            self._on_root_change(new_root)

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        """Build or rebuild the tree UI inside self._container."""
        self._rows = {}
        
        if self._container is not None:
            self._container.clear()
        else:
            self._container = ui.column().classes('w-full gap-0')

        with self._container:
            # Up-navigation row
            with ui.row().classes('items-center gap-1 px-2 py-1'):
                at_min = (self._min_root is not None and self._root == self._min_root)
                up_btn = ui.button(
                    icon='arrow_upward',
                    on_click=self._navigate_up,
                ).props('flat dense round size=sm').tooltip('Go up one level')
                if at_min:
                    up_btn.disable()
                ui.label(str(self._root)).classes('text-caption text-grey-9')

            ui.separator()

            # Spinner while loading
            spinner = ui.spinner(size='sm')
            placeholder = ui.label('Scanning…').classes('text-caption text-grey-7 px-4')

        # Load folder data asynchronously
        asyncio.create_task(self._load_and_render(spinner, placeholder))

    async def _load_and_render(
        self,
        spinner: ui.spinner,
        placeholder: ui.label,
    ) -> None:
        """Fetch folder info concurrently, then render rows."""
        loop = asyncio.get_event_loop()

        # Collect immediate child folders (skip hidden + diskann)
        try:
            children = sorted(
                [
                    p for p in self._root.iterdir()
                    if p.is_dir()
                    and not p.name.startswith('.')
                    and not _is_diskann(p)
                ],
                key=lambda p: p.name.lower(),
            )
        except PermissionError:
            spinner.set_visibility(False)
            placeholder.set_text('Permission denied')
            return

        # Analyse all folders in parallel
        tasks = [_analyse_folder(child, loop) for child in children]
        results = await asyncio.gather(*tasks)

        # Remove spinner / placeholder
        spinner.set_visibility(False)
        placeholder.set_visibility(False)

        if not results:
            with self._container:
                ui.label('(empty)').classes('text-caption text-grey-7 px-4 py-2')
            return

        # Render one row per folder
        with self._container:
            for info in results:
                self._render_row(info)

    def _render_row(self, info: dict) -> None:
        """Render a single folder row."""
        folder: Path = info['path']
        audio_count: int = info['audio_count']
        db_status: str = info['db_status']

        no_access = (audio_count == -1 or db_status == 'no_access')
        is_selected = (folder == self._selected)

        row_classes = (
            'items-center gap-2 px-3 py-1 rounded w-full '
            + ('bg-blue-1' if is_selected
               else 'hover:bg-grey-2 cursor-pointer' if not no_access
               else 'cursor-not-allowed')
        )

        with ui.row().classes(row_classes) as row:
            ui.icon('folder').classes(
                'text-grey-4' if no_access
                else ('text-blue-7' if is_selected else 'text-yellow-7')
            )
            ui.label(folder.name).classes(
                'flex-grow text-body2 '
                + ('text-grey-4' if no_access else 'text-grey-9')
            )

            if no_access:
                ui.icon('lock').classes('text-grey-4 shrink-0').tooltip(
                    'Permission denied'
                )
            elif self._show_extras:
                audio_icon_html = SVG_AUDIO_SOME if audio_count > 0 else SVG_AUDIO_NONE
                ui.html(audio_icon_html).classes('shrink-0').tooltip(
                    f'{audio_count} audio file(s)'
                )
                ui.label(str(audio_count)).classes('text-caption w-6 text-right text-grey-9')

                db_svg = {
                    'absent':     SVG_DB_ABSENT,
                    'incomplete': SVG_DB_INCOMPLETE,
                    'complete':   SVG_DB_COMPLETE,
                }[db_status]
                db_tooltip = {
                    'absent':     'No database',
                    'incomplete': 'Database incomplete',
                    'complete':   'Database complete',
                }[db_status]
                ui.html(db_svg).classes('shrink-0').tooltip(db_tooltip)

            if self._on_add_job is not None and not no_access:
                ui.button(
                    icon='add',
                    on_click=lambda f=folder: self._on_add_job(f),
                ).props('flat dense round size=sm color=positive').tooltip(
                    'Add folder to scout list'
                )

        # Click/dblclick only for accessible folders
        if not no_access:
            row.on('click', lambda f=folder, r=row: self._on_click(f, r))
            row.on('dblclick', lambda f=folder: self._drill_down(f))
        self._rows[folder] = row
                
        
    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_click(self, folder: Path, row: ui.row) -> None:
        # Deselect previously selected row
        if self._selected and self._selected in self._rows:
            old_row = self._rows[self._selected]
            old_row.classes(remove='bg-blue-1', add='hover:bg-grey-2')
        # Select new row
        self._selected = folder
        row.classes(remove='hover:bg-grey-2', add='bg-blue-1')
        if self._on_select:
            self._on_select(folder)

    def _drill_down(self, folder: Path) -> None:
        self._root = folder
        self._selected = None
        self._render()
        if self._on_root_change:
            self._on_root_change(folder)

    def _navigate_up(self) -> None:
        parent = self._root.parent
        if parent == self._root:
            return  # filesystem root
        if self._min_root is not None and self._root == self._min_root:
            return  # hard boundary
        self._root = parent
        self._selected = None
        self._render()
        if self._on_root_change:
            self._on_root_change(parent)

            