"""
Reusable page header element with optional collapsible description.

Renders a row with:
  - Page title (symbol + name) on the left
  - Collapsible 'Description' expansion on the right (only if help text found)

Help texts are looked up in:
  TEXTS / lang / help_file.txt
  TEXTS / 'en' / help_file.txt   (fallback)

If neither file exists, the expansion element is not rendered at all.
"""

from pathlib import Path

from nicegui import ui

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEXTS: Path = Path(__file__).parent.parent / 'pages' / 'texts'


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_help_text(help_file: str, lang: str) -> str | None:
    """
    Load help text for the given file and language.

    Search order:
      1. TEXTS / lang / help_file.txt
      2. TEXTS / 'en' / help_file.txt

    Returns:
        File contents as string, or None if neither file exists.
        No log output on missing files.
    """
    for search_lang in (lang, 'en'):
        p = TEXTS / search_lang / f'{help_file}.txt'
        if p.exists():
            return p.read_text(encoding='utf-8')
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def page_header(symbol: str, name: str, help_file: str, lang: str = 'de') -> None:
    """
    Render a standardised page header row.

    Layout:
        <symbol>  <name>        [▶ Description]

    The Description expansion is only shown if a matching help text file
    is found. If no file exists for lang or 'en', the expansion is omitted
    entirely and no error is logged.

    Args:
        symbol:    Emoji or short symbol string, e.g. '🛠'
        name:      Page name, e.g. 'Hangar'
        help_file: Base filename (without extension) for the help text,
                   e.g. 'hangar' → looks for TEXTS/de/hangar.txt
        lang:      Language code, default 'de'
    """
    help_text = _load_help_text(help_file, lang)

    with ui.row().classes('w-full items-start gap-8 q-mt-md q-mb-sm'):
        ui.label(f'{symbol}  {name}').classes('text-h5')

        if help_text is not None:
            with ui.expansion('Description').classes(
                'text-body2 text-grey-8 q-ma-none q-pa-none'
            ).props('switch-toggle-side dense'):
                ui.label(help_text).classes('text-body2 text-grey-9 q-mt-xs')