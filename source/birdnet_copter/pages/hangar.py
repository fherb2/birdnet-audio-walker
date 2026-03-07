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
from ..gui_elements.folder_tree import FolderTree
from ..utils import find_databases_recursive


# ---------------------------------------------------------------------------
# Page registration
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


@ui.page('/')
async def hangar() -> None:
    state = _get_state()
    create_layout(state)

    ui.label('🛠 Hangar').classes('text-h5 q-mt-md q-mb-sm')

    # -----------------------------------------------------------------------
    # Section 1: Host Information
    # -----------------------------------------------------------------------
    with ui.card().classes('w-full q-mb-md'):
        ui.label('🖥 Host Information').classes('text-h6 q-mb-xs')
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
    with ui.card().classes('w-full q-mb-md'):
        ui.label('📁 Root Path / Global DB Path').classes('text-h6 q-mb-xs')

        root_label = ui.label(str(state.root_path)).classes('text-body2 text-grey-8 q-mb-xs')

        async def _open_root_dialog() -> None:
            root_dialog.open()

        ui.button('📁 Change', on_click=_open_root_dialog).props('no-caps')

    # --- Root Path Dialog ---
    with ui.dialog() as root_dialog:
        with ui.card().classes('w-96'):
            ui.label('Select Root Path').classes('text-h6 q-mb-sm')

            selected_path: dict = {'value': state.root_path}

            def _on_folder_select(p: Path) -> None:
                selected_path['value'] = p

            FolderTree(
                root_path=state.root_path,
                on_select=_on_folder_select,
                show_extras=False,
            )

            with ui.row().classes('q-mt-sm gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=root_dialog.close).props('no-caps flat')

                async def _confirm_root() -> None:
                    new_root = selected_path['value']
                    if new_root == state.root_path:
                        root_dialog.close()
                        return
                    state.root_path = new_root
                    root_label.set_text(str(new_root))
                    # Re-scan for databases
                    loop = asyncio.get_event_loop()
                    dbs = await loop.run_in_executor(
                        None, find_databases_recursive, new_root
                    )
                    state.available_dbs = dbs
                    if dbs:
                        state.active_db = dbs[0]
                    else:
                        state.active_db = None
                    logger.info(f'Root path changed to: {new_root}')
                    root_dialog.close()

                ui.button('✔ Confirm', on_click=_confirm_root).props('no-caps color=primary')

    # -----------------------------------------------------------------------
    # Section 3: Inference Configuration
    # -----------------------------------------------------------------------
    with ui.card().classes('w-full q-mb-md'):
        ui.label('⚙ Inference Configuration').classes('text-h6 q-mb-xs')

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

        with ui.column().classes('gap-0'):
            ui.switch(
                'Use Embedding Vectors',
                value=state.use_embeddings,
                on_change=lambda e: _on_embeddings_change(e.value),
            )
            ui.label(
                'Extracts 1024-dim feature vectors for clustering and similarity search. '
                'Increases analysis time by approx. 2×.'
            ).classes('text-caption text-grey-6 q-ml-md')

        def _on_embeddings_change(val: bool) -> None:
            state.use_embeddings = val
            logger.debug(f'use_embeddings set to {val}')

    # -----------------------------------------------------------------------
    # Section 4: Global Index
    # -----------------------------------------------------------------------
    with ui.card().classes('w-full q-mb-md'):
        ui.label('🌐 Global Index').classes('text-h6 q-mb-xs')

        global_index_label = ui.label(
            str(state.global_index_path) if state.global_index_path else str(state.root_path)
        ).classes('text-body2 text-grey-8')

        global_path_row = ui.row().classes('items-center gap-3 q-mt-xs')

        with global_path_row:
            global_path_display = ui.label(
                str(state.global_index_path or state.root_path)
            ).classes('text-body2 text-grey-8 flex-grow')

            async def _open_global_dialog() -> None:
                global_dialog.open()

            change_global_btn = ui.button(
                '📁 Change', on_click=_open_global_dialog
            ).props('no-caps')

        # Toggle
        use_global_toggle = ui.switch(
            'Create / Use Global Index',
            value=state.global_index_path is not None,
            on_change=lambda e: _on_global_toggle(e.value),
        )
        # Move toggle before path row visually
        use_global_toggle.move(global_path_row.parent_slot.parent, target_index=0)

        ui.label(
            'A global index combines all local databases into one overarching database.'
        ).classes('text-caption text-grey-6')

        def _on_global_toggle(val: bool) -> None:
            global_path_row.set_visibility(val)
            if not val:
                state.global_index_path = None
                state.active_db_is_global = False
                logger.debug('Global index disabled')
            else:
                if state.global_index_path is None:
                    state.global_index_path = state.root_path
                global_path_display.set_text(str(state.global_index_path))
                logger.debug(f'Global index enabled: {state.global_index_path}')

        # Initial visibility
        global_path_row.set_visibility(state.global_index_path is not None)

    # --- Global Index Path Dialog ---
    with ui.dialog() as global_dialog:
        with ui.card().classes('w-96'):
            ui.label('Select Global Index Path').classes('text-h6 q-mb-sm')

            selected_global: dict = {
                'value': state.global_index_path or state.root_path
            }

            def _on_global_select(p: Path) -> None:
                selected_global['value'] = p

            FolderTree(
                root_path=state.global_index_path or state.root_path,
                on_select=_on_global_select,
                show_extras=False,
            )

            with ui.row().classes('q-mt-sm gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=global_dialog.close).props('no-caps flat')

                def _confirm_global() -> None:
                    state.global_index_path = selected_global['value']
                    global_path_display.set_text(str(state.global_index_path))
                    logger.info(f'Global index path set to: {state.global_index_path}')
                    global_dialog.close()

                ui.button(
                    '✔ Confirm', on_click=_confirm_global
                ).props('no-caps color=primary')