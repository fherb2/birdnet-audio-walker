"""
Reusable section card context manager with optional collapsible description.

Usage:
    with section_card('📂', 'Folder Selection', 'scouting_folder_selection'):
        ui.label('Content here...')

Renders a ui.card() containing:
  - A header row with symbol + name (text-h6) on the left and an optional
    collapsible 'Description' expansion on the right
  - The with-block content below the header

Help texts are looked up via the same mechanism as page_header:
  TEXTS / lang / help_file.txt
  TEXTS / 'en' / help_file.txt  (fallback)
If neither file exists, the expansion element is omitted silently.
"""

from nicegui import ui

from .page_header import TEXTS, _load_help_text


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class SectionCard:
    """
    Context manager that wraps content in a ui.card() with a header row.

    Args:
        symbol:    Emoji or short symbol string, e.g. '📂'
        name:      Section name, e.g. 'Folder Selection'
        help_file: Base filename (without extension) for the help text,
                   e.g. 'scouting_folder_selection'
        lang:      Language code, default 'de'
    """

    def __init__(self, symbol: str, name: str, help_file: str, lang: str = 'de') -> None:
        self._symbol    = symbol
        self._name      = name
        self._help_file = help_file
        self._lang      = lang
        self._card      = None

    def __enter__(self) -> 'SectionCard':
        help_text = _load_help_text(self._help_file, self._lang)

        self._card = ui.card().classes('w-full q-mb-md')
        self._card.__enter__()

        # Header row: title left, optional description right
        with ui.row().classes('w-full items-start gap-8 q-mb-xs'):
            ui.label(f'{self._symbol}  {self._name}').classes('text-h6')
            if help_text is not None:
                with ui.expansion('Description').classes(
                    'text-body2 text-grey-8 q-ma-none q-pa-none'
                ).props('switch-toggle-side dense'):
                    ui.label(help_text).classes('text-body2 text-grey-9 q-mt-xs')

        return self
    
    def set_visibility(self, visible: bool) -> None:
        if self._card is not None:
            self._card.set_visibility(visible)

    def __exit__(self, *args) -> None:
        self._card.__exit__(*args)


# ---------------------------------------------------------------------------
# Public factory function
# ---------------------------------------------------------------------------

def section_card(symbol: str, name: str, help_file: str, lang: str = 'de') -> SectionCard:
    """
    Create a SectionCard context manager.

    Args:
        symbol:    Emoji or short symbol string, e.g. '📂'
        name:      Section name, e.g. 'Folder Selection'
        help_file: Base filename (without extension) for the help text
        lang:      Language code, default 'de'

    Returns:
        SectionCard instance for use as a context manager.
    """
    return SectionCard(symbol, name, help_file, lang)