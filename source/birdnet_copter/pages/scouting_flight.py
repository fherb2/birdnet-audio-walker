"""
Scouting Flight page – folder selection, job management, scout control.

Route: /scouting

Sections:
  1. Folder View   (FolderTree with '+' button per row)
  2. Job Controls  (Take off, Hover/Fly on toggle, Terminate flight)
  3. Job List      (table, updated via ui.timer ~1 s)
  4. Status Line   (single-line scout summary)
"""

import asyncio
from pathlib import Path
from typing import List

from loguru import logger
from nicegui import ui, app as nicegui_app, context

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.page_header import page_header
from ..gui_elements.section_card import section_card
from ..gui_elements.page_header import _load_help_text
from ..gui_elements.folder_tree import FolderTree
from ..job_queue import (
    ScanJob,
    add_job,
    send_control,
    shutdown_scouting,
    drain_progress_queue,
    SIGNAL_WAIT,
    SIGNAL_RESUME,
    SIGNAL_STOP,
)
from ..main import start_scout_process
from ..db_queries import get_db_min_confidence


# ---------------------------------------------------------------------------
# Page registration
# ---------------------------------------------------------------------------

def _get_state() -> AppState:
    return nicegui_app.state.app_state  # type: ignore[attr-defined]


@ui.page('/scouting')
async def scouting_flight() -> None:
    state = _get_state()
    bundle = nicegui_app.state.bundle
    create_layout(state)

    page_header('🚁', 'Scouting Flight', 'scouting_flight')

    # Page-local state
    page: dict = {
        'scout_started': False,        # True once ▶ Take off has been pressed
        'added_folders': set(),
    }

    # -----------------------------------------------------------------------
    # Section 1: Folder View
    # -----------------------------------------------------------------------
    with section_card('📂', 'Folder Selection', 'scouting_folder_selection'):
    
        ui.label(
            'You can add folders for the scouting flight by the + symbol in the list. '
            'Go deeper into the list (double click) if your folder structure has multiple levels.'
        ).classes('text-caption text-grey-9 q-mb-xs')
        
        def _on_scout_everything() -> None:
            """Add root_path and all subfolders with WAV files to the job list."""
            root = state.root_path
            candidates = [root] + sorted(
                p for p in root.rglob('*') if p.is_dir()
            )
            folders_to_add = [
                f for f in candidates
                if (any(f.glob('*.wav')) or any(f.glob('*.WAV')))
                and f not in page['added_folders']
            ]
            if not folders_to_add:
                ui.notify('All folders already in scout list.', type='warning')
                return

            from ..job_queue import progress_msg
            jobs: list = list(bundle.shared_state.get('jobs', []))
            pending: list = list(bundle.shared_state.get('pending_jobs', []))

            for f in folders_to_add:
                page['added_folders'].add(f)
                from ..db_queries import get_db_min_confidence
                db_p = f / 'birdnet_analysis.db'
                stored_conf = get_db_min_confidence(db_p) if db_p.exists() else None
                job = ScanJob(
                    folder_path=f,
                    scan_embeddings=state.use_embeddings,
                    rescan_species=False,
                    min_conf=stored_conf if stored_conf is not None else float(min_conf_input.value or 0.4),
                )
                jobs.append(progress_msg(job))
                pending.append(job)

            bundle.shared_state['jobs'] = jobs
            bundle.shared_state['pending_jobs'] = pending
            ui.notify(f'Added {len(folders_to_add)} folder(s) from root', type='positive')
            _refresh_job_table()
            
        ui.button('🌍 Scout everything', on_click=_on_scout_everything).props('no-caps')

        recursive_toggle = ui.checkbox('Include subfolders into your selection', value=False)

        def _add_folder_to_jobs(folder: Path) -> None:
            """Add folder (and subfolders if recursive) as ScanJob(s)."""
            folders_to_add: list[Path] = []

            if recursive_toggle.value:
                # Collect folder itself + all subfolders containing WAV files
                candidates = [folder] + sorted(
                    p for p in folder.rglob('*') if p.is_dir()
                )
                for f in candidates:
                    has_wav = any(f.glob('*.wav')) or any(f.glob('*.WAV'))
                    if has_wav and f not in page['added_folders']:
                        folders_to_add.append(f)
            else:
                if folder not in page['added_folders']:
                    folders_to_add.append(folder)

            if not folders_to_add:
                ui.notify('All matching folders already in scout list.', type='warning')
                return

            from ..job_queue import progress_msg
            jobs: list = list(bundle.shared_state.get('jobs', []))
            pending: list = list(bundle.shared_state.get('pending_jobs', []))

            for f in folders_to_add:
                page['added_folders'].add(f)
                db_p = f / 'birdnet_analysis.db'
                job = ScanJob(
                    folder_path=f,
                    scan_embeddings=state.use_embeddings,
                    rescan_species=False,
                    min_conf=0.0,  # set at job start from DB or cockpit
                )
                jobs.append(progress_msg(job))
                pending.append(job)

            bundle.shared_state['jobs'] = jobs
            bundle.shared_state['pending_jobs'] = pending
            ui.notify(f'Added {len(folders_to_add)} folder(s)', type='positive')
            _refresh_job_table()

        def _rebuild_folder(folder: Path) -> None:
            """Add folder as Rebuild ScanJob (rescan_species=True)."""
            from ..job_queue import progress_msg
            from ..db_queries import get_db_min_confidence
            db_path = folder / 'birdnet_analysis.db'
            min_conf = get_db_min_confidence(db_path) or float(min_conf_input.value or 0.4)
            # Rebuild always uses current cockpit confidence
            conf = float(min_conf_input.value or 0.4)
            job = ScanJob(
                    folder_path=folder,
                    scan_embeddings=state.use_embeddings,
                    rescan_species=True,
                    min_conf=0.0,  # set at job start from cockpit
                )
            jobs: list = list(bundle.shared_state.get('jobs', []))
            pending: list = list(bundle.shared_state.get('pending_jobs', []))
            jobs.append(progress_msg(job))
            pending.append(job)
            bundle.shared_state['jobs'] = jobs
            bundle.shared_state['pending_jobs'] = pending
            page['added_folders'].add(folder)
            ui.notify(f'Rebuild job added: {folder.name}', type='warning')
            _refresh_job_table()

        FolderTree(
            root_path=state.root_path,
            on_select=None,
            show_extras=True,
            min_root=state.root_path,
            on_add_job=_add_folder_to_jobs,
            on_rebuild_job=_rebuild_folder,
        )


    # -----------------------------------------------------------------------
    # Section 2: Job List
    # -----------------------------------------------------------------------
    with section_card('📋', 'Job List', 'scouting_job_list'):

        STATUS_ICONS = {
            'pending': '⏳',
            'flying':  '🚁',
            'done':    '✅',
            'error':   '❌',
            'skipped': '⏭',
            'waiting':      '⏸',
            'wait_pending': '⏳',
        }

        job_table_container = ui.column().classes('w-full gap-1')
        
        def _remove_job(job_id: str) -> None:
            """Remove a pending job from shared_state and pending_jobs list."""
            # Find folder path before removing
            jobs: list = list(bundle.shared_state.get('jobs', []))
            removed = next((j for j in jobs if j.get('job_id') == job_id), None)

            # Remove from shared_state['jobs']
            bundle.shared_state['jobs'] = [j for j in jobs if j.get('job_id') != job_id]

            # Remove from pending_jobs
            pending: list = list(bundle.shared_state.get('pending_jobs', []))
            bundle.shared_state['pending_jobs'] = [
                j for j in pending if j.job_id != job_id
            ]

            # Allow folder to be re-added
            if removed:
                folder = Path(removed.get('folder_path', ''))
                page['added_folders'].discard(folder)

            _refresh_job_table()

        def _refresh_job_table() -> None:
            jobs: list = list(bundle.shared_state.get('jobs', []))
            job_table_container.clear()
            if not jobs:
                with job_table_container:
                    ui.label('No jobs yet.').classes('text-caption text-grey-6')
                return

            with job_table_container:
                with ui.row().classes(
                    'w-full px-2 py-1 bg-grey-2 text-caption font-bold gap-2 items-center'
                ):
                    ui.label('#').classes('w-6')
                    ui.label('Folder').classes('w-48')
                    ui.label('Type').classes('w-16')
                    ui.label('Min. Conf').classes('w-16')
                    ui.label('Status').classes('w-28')
                    ui.label('Progress').classes('w-16')
                    ui.label('Current file').classes('flex-grow')
                    ui.label('').classes('w-8')

                for idx, j in enumerate(jobs):
                    status = j.get('status', 'pending')
                    icon = STATUS_ICONS.get(status, '?')
                    total = j.get('files_total', 0)
                    done = j.get('files_done', 0)
                    progress = f'{done}/{total}' if total > 0 else '–'

                    job_type = '🔄 Rebuild' if j.get('rescan_species') else '➕ Extend'
                    min_conf_val = j.get('min_conf')
                    min_conf_str = f'{min_conf_val:.2f}' if (min_conf_val is not None and min_conf_val > 0.0) else '–'

                    with ui.row().classes(
                        'w-full px-2 py-1 gap-2 items-center '
                        + ('bg-grey-1' if idx % 2 == 0 else '')
                    ):
                        ui.label(str(idx + 1)).classes('w-6 text-caption')
                        ui.label(
                            Path(j.get('folder_path', '')).name
                        ).classes('w-48 text-body2').tooltip(j.get('folder_path', ''))
                        ui.label(job_type).classes('w-16 text-caption')
                        ui.label(min_conf_str).classes('w-16 text-caption')
                        ui.label(f'{icon} {status}').classes('w-28 text-caption')
                        ui.label(progress).classes('w-16 text-caption')
                        ui.label(j.get('current_file', '')).classes(
                            'flex-grow text-caption text-grey-6'
                        )
                        if status == 'pending':
                            job_id = j.get('job_id')
                            ui.button(
                                icon='close',
                                on_click=lambda jid=job_id: _remove_job(jid),
                            ).props('flat dense round size=xs color=negative')
                        else:
                            ui.label('').classes('w-8')

        _refresh_job_table()

    # -----------------------------------------------------------------------
    # Section 3: Cockpit
    # -----------------------------------------------------------------------
    def _build_status_line() -> str:
        ws = bundle.shared_state.get('walker_status', 'idle')
        jobs: list = list(bundle.shared_state.get('jobs', []))

        if ws == 'idle':
            return '🚁 idle'

        if ws == 'wait_pending':
            return '🚁 hover pending'

        if ws == 'waiting':
            pending_count = sum(1 for j in jobs if j.get('status') == 'pending')
            return f'🚁 waiting | {pending_count} job(s) in queue'

        if ws == 'flying':
            running_jobs = [j for j in jobs if j.get('status') == 'flying']
            total_jobs = len(jobs)
            job_idx = next(
                (i + 1 for i, j in enumerate(jobs) if j.get('status') == 'flying'),
                '?'
            )
            if running_jobs:
                rj = running_jobs[0]
                files_done = rj.get('files_done', 0)
                files_total = rj.get('files_total', 0)
                current_file = rj.get('current_file', '')
                file_part = f'File {files_done}/{files_total}'
                if current_file:
                    file_part += f': {current_file}'
                return f'🚁 flying | Job {job_idx}/{total_jobs} | {file_part}'
            return f'🚁 flying | Job ?/{total_jobs}'

        return '🚁 idle'

    with ui.card().classes('w-full q-mb-md'):
        # Header row: title + status line
        with ui.row().classes('w-full items-center q-mb-xs gap-8'):
            ui.label('🎛  Cockpit').classes('text-h6')
            status_line = ui.label('🚁 idle').classes('text-body1 text-grey-7')

        # Optional description (only shown if help file exists)
        help_text = _load_help_text('scouting_cockpit', 'de')
        if help_text is not None:
            with ui.expansion('Description').classes(
                'text-body2 text-grey-8 q-ma-none q-pa-none q-mb-xs'
            ).props('switch-toggle-side dense'):
                ui.label(help_text).classes('text-body2 text-grey-9 q-mt-xs')

        # Controls
        with ui.row().classes('items-center gap-6 q-mb-sm flex-wrap'):
            min_conf_input = ui.number(
                label='Min. Confidence (new DB & Rebuild)',
                value=0.4,
                min=0.01,
                max=1.0,
                step=0.05,
                format='%.2f',
            ).classes('w-36')
            with ui.column().classes('gap-0'):
                embeddings_toggle = ui.switch(
                    'Include Embedding Vectors',
                    value=False,
                )
                ui.label(
                    'Extracts 1024-dim feature vectors. Increases analysis time by approx. 2×.'
                ).classes('text-caption text-grey-6')

        with ui.row().classes('gap-2 items-center q-mb-sm flex-wrap'):

            async def _on_start() -> None:
                """Start scout if not flying; flush pending jobs into job_queue."""
                if not page['scout_started']:
                    start_scout_process(bundle)
                    page['scout_started'] = True
                    bundle.shared_state['walker_status'] = 'flying'

                pending: list = list(bundle.shared_state.get('pending_jobs', []))
                conf = float(min_conf_input.value or 0.4)
                use_emb = embeddings_toggle.value

                for job in pending:
                    job.scan_embeddings = use_emb
                    if job.rescan_species:
                        job.min_conf = conf
                    else:
                        from ..db_queries import get_db_min_confidence
                        db_p = job.folder_path / 'birdnet_analysis.db'
                        stored = get_db_min_confidence(db_p) if db_p.exists() else None
                        job.min_conf = stored if stored is not None else conf
                    bundle.job_queue.put(job)
                    logger.debug(
                        f'Job sent to scout: {job.folder_path} '
                        f'(min_conf={conf}, embeddings={use_emb})'
                    )

                jobs: list = list(bundle.shared_state.get('jobs', []))
                for job in pending:
                    for i, j in enumerate(jobs):
                        if j.get('job_id') == job.job_id:
                            jobs[i] = {**j, 'min_conf': job.min_conf, 'scan_embeddings': use_emb}
                bundle.shared_state['jobs'] = jobs
                bundle.shared_state['pending_jobs'] = []
                _update_control_buttons()

            start_btn = ui.button('▶ Take off', on_click=_on_start).props('no-caps color=positive')

            def _on_hover_toggle() -> None:
                ws = bundle.shared_state.get('walker_status', 'idle')
                if ws == 'flying':
                    send_control(bundle, SIGNAL_WAIT)
                    bundle.shared_state['walker_status'] = 'wait_pending'
                elif ws == 'waiting':
                    send_control(bundle, SIGNAL_RESUME)
                    bundle.shared_state['walker_status'] = 'flying'
                _update_control_buttons()

            hover_btn = ui.button('⏸ Hover', on_click=_on_hover_toggle).props('no-caps color=warning')

            def _on_terminate() -> None:
                send_control(bundle, SIGNAL_STOP)
                bundle.shared_state['walker_status'] = 'idle'
                _update_control_buttons()

            terminate_btn = ui.button(
                '⏹ Terminate flight', on_click=_on_terminate
            ).props('no-caps color=negative')

    def _update_control_buttons() -> None:
        """En-/disable buttons and tooltips based on scout status."""
        ws = bundle.shared_state.get('walker_status', 'idle')

        _WAIT_MSG       = 'Wait until current batch is processed'
        _NOT_FLYING     = 'Not flying'
        _ALREADY_FLYING = 'Already flying'
        _HOVERING       = 'Scout is hovering'

        if ws == 'idle':
            start_btn.enable()
            start_btn.props('no-caps color=positive')
            start_btn.tooltip('')
        elif ws == 'wait_pending':
            start_btn.disable()
            start_btn.tooltip(_WAIT_MSG)
        else:
            start_btn.disable()
            start_btn.tooltip(_ALREADY_FLYING if ws == 'flying' else _HOVERING)

        if ws == 'flying':
            hover_btn.set_text('⏸ Hover')
            hover_btn.enable()
            hover_btn.tooltip('')
        elif ws == 'waiting':
            hover_btn.set_text('▶ Fly on')
            hover_btn.enable()
            hover_btn.tooltip('')
        elif ws == 'wait_pending':
            hover_btn.disable()
            hover_btn.tooltip(_WAIT_MSG)
        else:
            hover_btn.disable()
            hover_btn.tooltip(_NOT_FLYING)

        if ws in ('flying', 'waiting'):
            terminate_btn.enable()
            terminate_btn.tooltip('')
        elif ws == 'wait_pending':
            terminate_btn.disable()
            terminate_btn.tooltip(_WAIT_MSG)
        else:
            terminate_btn.disable()
            terminate_btn.tooltip(_NOT_FLYING)

    _update_control_buttons()


    # -----------------------------------------------------------------------
    # ui.timer: refresh table + status line + buttons
    # -----------------------------------------------------------------------
    def _tick() -> None:
        drain_progress_queue(bundle)
        _refresh_job_table()
        status_line.set_text(_build_status_line())
        _update_control_buttons()

    timer = ui.timer(1.0, _tick)

    async def _stop_timer() -> None:
        timer.cancel()

    context.client.on_disconnect(_stop_timer)