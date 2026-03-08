"""
Species autocomplete search component for BirdNET Play.

Displays a text input with a dropdown that shows matching species
from the species_list table as the user types.

Usage:
    search = SpeciesSearch(
        db_path=state.active_db,
        on_select=lambda sci_name: ...,
        initial_value=state.ap_filter_species,
    )
    # To clear programmatically:
    search.clear()
    # To get current value:
    search.value  # scientific name or None
"""

from pathlib import Path
from typing import Callable, Optional

from nicegui import ui

from ..db_queries import search_species_in_list


class SpeciesSearch:
    """
    Autocomplete species search field.

    Args:
        db_path:       Path to birdnet_analysis.db for species lookup.
        on_select:     Called with scientific name (str) when user selects
                       a species. Called with None when filter is cleared.
        initial_value: Pre-selected scientific name (e.g. from AppState).
        placeholder:   Input placeholder text.
    """

    def __init__(
        self,
        db_path: Optional[Path],
        on_select: Optional[Callable[[Optional[str]], None]] = None,
        initial_value: Optional[str] = None,
        placeholder: str = 'Search species… (type to filter)',
    ) -> None:
        self._db_path = db_path
        self._on_select = on_select
        self._value: Optional[str] = initial_value   # scientific name
        self._menu: Optional[ui.menu] = None
        self._input: Optional[ui.input] = None
        self._active_label: Optional[ui.label] = None
        self._container: Optional[ui.element] = None

        self._render(placeholder)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def value(self) -> Optional[str]:
        """Currently selected scientific name, or None."""
        return self._value

    def clear(self) -> None:
        """Programmatically clear the selection and show the input field."""
        self._value = None
        self._show_input()
        if self._on_select:
            self._on_select(None)

    def set_db(self, db_path: Optional[Path]) -> None:
        """Update the database path (e.g. after DB switch)."""
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, placeholder: str) -> None:
        with ui.column().classes('w-full gap-1') as self._container:

            # --- Active selection display (shown when a species is selected) ---
            with ui.row().classes('items-center gap-2') as self._active_row:
                self._active_label = ui.label('').classes(
                    'text-body2 bg-blue-1 px-3 py-1 rounded'
                )
                ui.button(
                    icon='close',
                    on_click=self.clear,
                ).props('flat dense round size=sm').tooltip('Clear species filter')

            # --- Input + dropdown (shown when no species selected) ---
            with ui.column().classes('w-full gap-0') as self._input_col:
                self._input = ui.input(placeholder=placeholder) \
                    .classes('w-full') \
                    .props('outlined dense clearable')

                # Dropdown menu anchored below the input
                self._menu = ui.menu().props('no-parent-event no-focus').classes('w-64')

            self._input.on(
                'keyup',
                lambda: self._on_keyup(),
            )
            # Also trigger on input event to catch paste / clear
            self._input.on(
                'input',
                lambda: self._on_keyup(),
            )

        # Set initial state
        if self._value:
            self._show_active(self._value)
        else:
            self._show_input()

    # ------------------------------------------------------------------
    # State switching
    # ------------------------------------------------------------------

    def _show_active(self, scientific_name: str) -> None:
        """Switch to 'species selected' display."""
        self._active_label.set_text(f'🔍 {scientific_name}')
        self._active_row.set_visibility(True)
        self._input_col.set_visibility(False)
        if self._menu:
            self._menu.close()

    def _show_input(self) -> None:
        """Switch to 'search input' display."""
        self._active_row.set_visibility(False)
        self._input_col.set_visibility(True)
        if self._input:
            self._input.set_value('')

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------

    def _on_keyup(self) -> None:
        """Triggered on every keystroke – fetch suggestions and update menu."""
        term = (self._input.value or '').strip()
        if len(term) < 1 or self._db_path is None:
            if self._menu:
                self._menu.close()
            return

        results = search_species_in_list(self._db_path, term, limit=10)
        self._menu.clear()

        if not results:
            self._menu.close()
            return

        with self._menu:
            for entry in results:
                # entry format: "Scientific Name (Local Name)"
                # extract scientific name (part before the first ' (')
                sci = entry.split(' (')[0] if ' (' in entry else entry
                ui.item(
                    entry,
                    on_click=lambda s=sci, e=entry: self._select(s, e),
                ).classes('text-body2 cursor-pointer')

        self._menu.open()


    def _select(self, scientific_name: str, display_text: str) -> None:
        """Called when user clicks a suggestion."""
        self._value = scientific_name
        self._show_active(scientific_name)
        if self._on_select:
            self._on_select(scientific_name)