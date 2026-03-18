"""
Hangar page – technical base configuration.

Route: /
Sections:
  1. Host Information  (read-only hardware display)
  2. Root Path         (change via FolderTree dialog)
  3. Inference Configuration  (GPU toggle, embeddings toggle)
  4. Global Index      (toggle + path selector)
"""

import asyncio
from pathlib import Path

from loguru import logger
from nicegui import ui, app as nicegui_app

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.page_header import page_header
from ..gui_elements.section_card import section_card
from ..gui_elements.folder_tree import FolderTree
from ..utils import find_databases_recursive
from ..bird_language import get_available_languages


# ---------------------------------------------------------------------------
# Page registration
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


@ui.page('/')
async def hangar() -> None:
    state = _get_state()
    create_layout(state)

    page_header('🛠', 'Hangar', 'hangar')

    # -----------------------------------------------------------------------
    # Section 1: Host Information
    # -----------------------------------------------------------------------
    with section_card('🚁', 'Copter – Technical data', 'hangar_host'):
        hw = state.hw_info

        if hw is None:
            ui.label('Hardware info not available.').classes('text-caption text-grey-6')
        else:
            with ui.grid(columns=2).classes('gap-x-8 gap-y-1'):

                # GPU
                ui.label('GPU').classes('text-caption text-grey-6 font-bold')
                if hw.has_nvidia_gpu and hw.gpu_name:
                    parts = [hw.gpu_name]
                    if hw.gpu_vram_gb is not None:
                        parts.append(f'{hw.gpu_vram_gb:.0f} GB VRAM')
                    if hw.gpu_shaders is not None:
                        parts.append(f'{hw.gpu_shaders} shaders')
                    ui.label(', '.join(parts)).classes('text-body2')
                else:
                    ui.label('no NVIDIA GPU').classes('text-body2 text-grey-6')

                # CPU
                ui.label('CPU').classes('text-caption text-grey-6 font-bold')
                ui.label(
                    f'{hw.cpu_count_logical} logical cores'
                    f' ({hw.cpu_count_physical} physical)'
                ).classes('text-body2')

                # RAM
                ui.label('RAM').classes('text-caption text-grey-6 font-bold')
                ui.label(f'{hw.ram_total_gb:.0f} GB').classes('text-body2')

                # Cores for inference
                ui.label('Cores for inference').classes('text-caption text-grey-6 font-bold')
                note = ' ⚠ sleep mode active' if hw.sleep_flag else ''
                ui.label(
                    f'{hw.cpu_count_for_inference}{note}'
                ).classes('text-body2' + (' text-orange-7' if hw.sleep_flag else ''))

    # -----------------------------------------------------------------------
    # Section 2: Root Path
    # -----------------------------------------------------------------------
    with section_card('🌍', 'Flying Area: Root Path / Global DB Path', 'hangar_root_path'):
        root_label = ui.label(str(state.root_path)).classes('text-body2 text-grey-10 q-mb-xs')
        root_dialog_btn = ui.button('📁 Change', on_click=lambda: asyncio.create_task(_open_root_dialog())).props('no-caps')

    with ui.dialog() as root_dialog:
        with ui.card().classes('w-96') as root_dialog_card:
            pass

    async def _open_root_dialog() -> None:
        root_dialog_card.clear()
        with root_dialog_card:
            ui.label('Select Root Path').classes('text-h6 q-mb-sm')
            selected_path: dict = {'value': state.root_path}

            def _on_folder_select(p: Path) -> None:
                selected_path['value'] = p

            FolderTree(root_path=state.root_path, on_select=_on_folder_select, show_extras=False)

            with ui.row().classes('q-mt-sm gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=root_dialog.close).props('no-caps flat')

                async def _confirm_root() -> None:
                    new_root = selected_path['value']
                    if new_root == state.root_path:
                        root_dialog.close()
                        return
                    state.root_path = new_root
                    root_label.set_text(str(new_root))
                    loop = asyncio.get_event_loop()
                    dbs = await loop.run_in_executor(None, find_databases_recursive, new_root)
                    state.available_dbs = dbs
                    state.active_db = dbs[0] if dbs else None
                    logger.info(f'Root path changed to: {new_root}')
                    root_dialog.close()

                ui.button('✔ Confirm', on_click=_confirm_root).props('no-caps color=primary')

        root_dialog.open()


    # -----------------------------------------------------------------------
    # Section 3: Inference Configuration
    # -----------------------------------------------------------------------
    with section_card('⚙️', 'GPU Processing', 'hangar_gpu'):

        hw = state.hw_info
        gpu_available = hw is not None and hw.has_nvidia_gpu

        with ui.row().classes('items-center gap-3 q-mb-xs'):
            gpu_toggle = ui.switch(
                'Use GPU',
                value=state.use_gpu and gpu_available,
                on_change=lambda e: _on_gpu_change(e.value),
            )
            if not gpu_available:
                gpu_toggle.disable()
                ui.label('(no NVIDIA GPU detected)').classes('text-caption text-grey-6')

        def _on_gpu_change(val: bool) -> None:
            state.use_gpu = val
            logger.debug(f'use_gpu set to {val}')

    # -----------------------------------------------------------------------
    # Section 4: Global Index
    # -----------------------------------------------------------------------
    with section_card('🌐', 'Global Index', 'hangar_global_index'):

        use_global_toggle = ui.switch(
            'Create / Use Global Index',
            value=state.global_index_path is not None,
            on_change=lambda e: _on_global_toggle(e.value),
        )

        global_path_row = ui.row().classes('items-center gap-3 q-mt-xs')
        with global_path_row:
            global_path_display = ui.label(
                str(state.global_index_path or state.root_path)
            ).classes('text-body2 text-grey-10 flex-grow')
            ui.button('📁 Change', on_click=lambda: asyncio.create_task(_open_global_dialog())).props('no-caps')

        ui.label(
            'A global index combines all local databases into one overarching database.'
        ).classes('text-caption text-grey-6')

        def _on_global_toggle(val: bool) -> None:
            global_path_row.set_visibility(val)
            if not val:
                state.global_index_path = None
                state.active_db_is_global = False
            else:
                if state.global_index_path is None:
                    state.global_index_path = state.root_path
                global_path_display.set_text(str(state.global_index_path))

        global_path_row.set_visibility(state.global_index_path is not None)

    with ui.dialog() as global_dialog:
        with ui.card().classes('w-96') as global_dialog_card:
            pass

    async def _open_global_dialog() -> None:
        global_dialog_card.clear()
        with global_dialog_card:
            ui.label('Select Global Index Path').classes('text-h6 q-mb-sm')
            selected_global: dict = {'value': state.global_index_path or state.root_path}

            def _on_global_select(p: Path) -> None:
                selected_global['value'] = p

            FolderTree(root_path=state.global_index_path or state.root_path, on_select=_on_global_select, show_extras=False)

            with ui.row().classes('q-mt-sm gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=global_dialog.close).props('no-caps flat')

                def _confirm_global() -> None:
                    state.global_index_path = selected_global['value']
                    global_path_display.set_text(str(state.global_index_path))
                    global_dialog.close()

                ui.button('✔ Confirm', on_click=_confirm_global).props('no-caps color=primary')

        global_dialog.open()
        
    # -----------------------------------------------------------------------
    # Section 5: Language Configuration
    # -----------------------------------------------------------------------
    with section_card('🌍', 'Language Configuration', 'hangar_language'):

        with ui.row().classes('gap-8 items-start'):

            # --- Bird name language (fully active) ---
            with ui.column().classes('gap-1'):
                ui.label('Bird Name Language').classes('text-caption text-grey-6 font-bold')
                bird_lang_select = ui.select(
                    options=get_available_languages(),
                    value=state.bird_language_code,
                    label='Bird Name Language',
                    on_change=lambda e: _on_bird_lang_change(e.value),
                ).props('outlined dense').classes('w-40')
                ui.label('Default: de (Deutsch)').classes('text-caption text-grey-6')

            # --- GUI language (not yet active) ---
            with ui.column().classes('gap-1'):
                ui.label('GUI Language').classes('text-caption text-grey-6 font-bold')
                ui.select(
                    options=['de', 'en'],
                    value=state.gui_language_code,
                    label='GUI Language',
                ).props('outlined dense disable').classes('w-40')
                ui.label('Not yet implemented').classes('text-caption text-grey-6')

    def _on_bird_lang_change(lang: str) -> None:
        available = get_available_languages()
        if lang not in available:
            ui.notify(
                f"Language '{lang}' not available, resetting to 'de'",
                type='warning',
            )
            state.bird_language_code = 'de'
            bird_lang_select.set_value('de')
        else:
            state.bird_language_code = lang
            logger.info(f"Bird language changed to: {lang}")