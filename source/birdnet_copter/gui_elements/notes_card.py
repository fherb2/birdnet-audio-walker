"""
NotesCard – reusable GUI element for database notes.

Shows a textarea bound to db_meta_data.notes, with:
  - "💾 Save Notes" button
  - Optional backup to _notes.txt in the folder (with versioning overlay)

Usage:
    NotesCard(db_path=Path(...), folder_path=Path(...))
"""

from pathlib import Path
from typing import Optional

from loguru import logger
from nicegui import ui

from ..gui_elements.section_card import section_card
from ..db_queries import get_db_meta_data, set_db_meta_data


_NOTES_FILENAME = '_notes.txt'


class NotesCard:
    """
    Reusable notes card for db_meta_data.notes field.

    Args:
        db_path:     Path to the SQLite database file.
        folder_path: Folder where _notes.txt backup will be written.
        read_only:   If True, textarea and buttons are disabled.
    """

    def __init__(
        self,
        db_path: Path,
        folder_path: Path,
        read_only: bool = False,
    ) -> None:
        self._db_path     = db_path
        self._folder_path = folder_path
        self._read_only   = read_only
        self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        with section_card('📝', 'Database Notes', 'notes_card'):

            ui.label(
                'This note exists only together with the SQLite detection database '
                'created here. Use the backup option to save it as a text file in '
                'the folder in case you want to delete the database later.'
            ).classes('text-caption text-grey-8 q-mb-sm')

            # Read current notes from DB
            current_notes = ''
            if self._db_path.exists():
                meta = get_db_meta_data(self._db_path)
                if meta:
                    current_notes = meta.get('notes', '') or ''

            # Textarea
            self._textarea = ui.textarea(
                label='Notes',
                value=current_notes,
                placeholder='Add notes about this recording session…',
            ).classes('w-full').props('rows=6 outlined')
            if self._read_only:
                self._textarea.props('readonly')

            # Backup checkbox + Save button
            with ui.row().classes('items-center gap-4 q-mt-sm'):
                self._backup_checkbox = ui.checkbox(
                    'Backup as _notes.txt in directory',
                    value=True,
                )
                if self._read_only:
                    self._backup_checkbox.disable()

                ui.button(
                    '💾 Save Notes',
                    on_click=self._on_save,
                ).props('no-caps color=primary')
                if self._read_only:
                    ui.label('(read-only)').classes('text-caption text-grey-6')

    # ------------------------------------------------------------------
    # Save logic
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Save notes to DB, optionally backup to _notes.txt."""
        notes_text = self._textarea.value or ''

        # Write to DB
        if not self._db_path.exists():
            ui.notify('No database found – please create the database first.', type='warning')
            return

        ok = set_db_meta_data(self._db_path, notes=notes_text)
        if not ok:
            ui.notify('Failed to save notes to database.', type='negative')
            return

        logger.info(f"Notes saved to DB: {self._db_path.name}")

        if self._backup_checkbox.value:
            self._backup_to_file(notes_text)
        else:
            ui.notify('Notes saved.', type='positive')

    def _backup_to_file(self, notes_text: str) -> None:
        """
        Backup notes to _notes.txt. If file exists, show overlay with
        old/new content and options to overwrite or keep old (with versioning).
        """
        notes_path = self._folder_path / _NOTES_FILENAME

        if not notes_path.exists():
            # Simple write – no conflict
            self._write_notes_file(notes_path, notes_text)
            ui.notify(f'Notes saved and backed up as {_NOTES_FILENAME}.', type='positive')
            return

        # File exists → read old content and show overlay
        try:
            old_content = notes_path.read_text(encoding='utf-8')
        except OSError as e:
            logger.warning(f"Could not read existing {_NOTES_FILENAME}: {e}")
            old_content = '(could not read existing file)'

        self._show_conflict_dialog(old_content, notes_text, notes_path)

    def _show_conflict_dialog(
        self,
        old_content: str,
        new_content: str,
        notes_path: Path,
    ) -> None:
        """Show overlay comparing old and new notes content."""

        with ui.dialog() as dlg, ui.card().classes('w-2/3'):
            ui.label('📄 _notes.txt already exists').classes('text-h6 q-mb-sm')
            ui.separator()

            ui.label('Existing content:').classes('text-caption text-grey-7 q-mt-sm')
            ui.textarea(value=old_content).classes('w-full').props('rows=5 outlined readonly')

            ui.label('New content (current notes):').classes('text-caption text-grey-7 q-mt-sm')
            ui.textarea(value=new_content).classes('w-full').props('rows=5 outlined readonly')

            # Result label (shown after action)
            result_label = ui.label('').classes('text-caption text-positive q-mt-xs')

            ui.separator().classes('q-my-sm')

            def _keep_old() -> None:
                archived = self._archive_existing(notes_path)
                self._write_notes_file(notes_path, new_content)
                result_label.set_text(f'Previous notes archived as {archived.name}')
                result_label.classes(remove='text-negative', add='text-positive')
                logger.info(f"Notes archived to {archived}")
                btn_row.set_visibility(False)
                ok_btn.set_visibility(True)

            def _overwrite() -> None:
                self._write_notes_file(notes_path, new_content)
                result_label.set_text(f'Overwritten {_NOTES_FILENAME} (old content lost).')
                result_label.classes(remove='text-positive', add='text-negative')
                logger.info(f"Notes overwritten: {notes_path}")
                btn_row.set_visibility(False)
                ok_btn.set_visibility(True)

            with ui.row().classes('gap-3 justify-end w-full') as btn_row:
                ui.button('Cancel', on_click=dlg.close).props('no-caps color=warning')
                ui.button(
                    '📦 Keep old (archive it)',
                    on_click=_keep_old,
                ).props('no-caps color=positive')
                ui.button(
                    '🔄 Overwrite',
                    on_click=_overwrite,
                ).props('no-caps color=warning')

            ok_btn = ui.button(
                '✅ OK – Close',
                on_click=dlg.close,
            ).props('no-caps color=positive')
            ok_btn.set_visibility(False)

        dlg.open()

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _archive_existing(self, notes_path: Path) -> Path:
        """
        Rename notes_path to _notes_001.txt (or _002, _003, … until free).
        Returns the Path it was archived to.
        """
        n = 1
        while True:
            candidate = notes_path.parent / f'_notes_{n:03d}.txt'
            if not candidate.exists():
                notes_path.rename(candidate)
                return candidate
            n += 1

    def _write_notes_file(self, path: Path, content: str) -> None:
        """Write content to path, creating parent dirs if needed."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        except OSError as e:
            logger.error(f"Failed to write {path}: {e}")
            ui.notify(f'Failed to write file: {e}', type='negative')
