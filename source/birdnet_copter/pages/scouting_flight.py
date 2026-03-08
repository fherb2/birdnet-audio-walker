"""
Scouting Flight page – folder selection, job management, walker control.

Route: /scouting

Sections:
  1. Folder View   (FolderTree with '+' button per row)
  2. Job Controls  (Start, Wait, Resume, Stop, Scout everything)
  3. Job List      (table, updated via ui.timer ~1 s)
  4. Status Line   (single-line walker summary)
"""

import asyncio
from pathlib import Path
from typing import List

from loguru import logger
from nicegui import ui, app as nicegui_app, context

from ..app_state import AppState
from ..pages.layout import create_layout
from ..gui_elements.folder_tree import FolderTree
from ..job_queue import (
    ScanJob,
    add_job,
    send_control,
    shutdown_walker,
    drain_progress_queue,
    SIGNAL_WAIT,
    SIGNAL_RESUME,
    SIGNAL_STOP,
)
from ..main import start_walker_process


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

    ui.label('🚁 Scouting Flight').classes('text-h5 q-mt-md q-mb-sm')

    # Page-local state
    page: dict = {
        'walker_started': False,       # True once ▶ Start has been pressed
        'added_folders': set(),        # folders already added this session
    }

    # -----------------------------------------------------------------------
    # Section 1: Folder View
    # -----------------------------------------------------------------------
    ui.label('📂 Folder Selection').classes('text-h6 q-mb-xs')
    
    ui.label(
        'You can add folders for the scouting flight by the + symbol in the list. '
        'Go deeper into the list (double click) if your folder structure has multiple levels.'
    ).classes('text-caption text-grey-6 q-mb-xs')
    
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
            job = ScanJob(
                folder_path=f,
                scan_embeddings=state.use_embeddings,
                rescan_species=False,
                min_conf=0.4,
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
            job = ScanJob(
                folder_path=f,
                scan_embeddings=state.use_embeddings,
                rescan_species=False,
                min_conf=0.4,
            )
            jobs.append(progress_msg(job))
            pending.append(job)

        bundle.shared_state['jobs'] = jobs
        bundle.shared_state['pending_jobs'] = pending
        ui.notify(f'Added {len(folders_to_add)} folder(s)', type='positive')
        _refresh_job_table()

    FolderTree(
        root_path=state.root_path,
        on_select=None,
        show_extras=True,
        min_root=state.root_path,
        on_add_job=_add_folder_to_jobs,
    )

    ui.separator().classes('q-my-md')


    # -----------------------------------------------------------------------
    # Section 2: Job List
    # -----------------------------------------------------------------------
    ui.label('📋 Job List').classes('text-h6 q-mb-xs')

    STATUS_ICONS = {
        'pending': '⏳',
        'running':  '🚁',
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

                with ui.row().classes(
                    'w-full px-2 py-1 gap-2 items-center '
                    + ('bg-grey-1' if idx % 2 == 0 else '')
                ):
                    ui.label(str(idx + 1)).classes('w-6 text-caption')
                    ui.label(
                        Path(j.get('folder_path', '')).name
                    ).classes('w-48 text-body2').tooltip(j.get('folder_path', ''))
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

    ui.separator().classes('q-my-md')

    # -----------------------------------------------------------------------
    # Section 3: Job Controls
    # -----------------------------------------------------------------------
    ui.label('🎛 Cockpit Controls').classes('text-h6 q-mb-xs')

    with ui.row().classes('gap-2 items-center q-mb-sm flex-wrap'):

        async def _on_start() -> None:
            """Start walker if not running; flush pending jobs into job_queue."""
            if not page['walker_started']:
                start_walker_process(bundle)
                page['walker_started'] = True
                bundle.shared_state['walker_status'] = 'flying'

            # Send all pending (not-yet-queued) jobs to the walker
            pending: list = list(bundle.shared_state.get('pending_jobs', []))
            for job in pending:
                bundle.job_queue.put(job)
                logger.debug(f'Job sent to walker: {job.folder_path}')
            bundle.shared_state['pending_jobs'] = []
            _update_control_buttons()

        start_btn = ui.button('▶ Take off', on_click=_on_start).props('no-caps color=positive')

        def _on_wait() -> None:
            send_control(bundle, SIGNAL_WAIT)
            bundle.shared_state['walker_status'] = 'wait_pending'
            _update_control_buttons()

        wait_btn = ui.button('⏸ Wait', on_click=_on_wait).props('no-caps color=warning')

        def _on_resume() -> None:
            send_control(bundle, SIGNAL_RESUME)
            bundle.shared_state['walker_status'] = 'running'
            _update_control_buttons()

        resume_btn = ui.button('▶ Resume', on_click=_on_resume).props('no-caps color=primary')

        def _on_stop() -> None:
            send_control(bundle, SIGNAL_STOP)
            bundle.shared_state['walker_status'] = 'idle'
            _update_control_buttons()

        stop_btn = ui.button(
            '⏹ Stop after current', on_click=_on_stop
        ).props('no-caps color=negative')

    def _update_control_buttons() -> None:
        """En-/disable buttons based on walker_status."""
        ws = bundle.shared_state.get('walker_status', 'idle')
        # Start: always available (re-flushes pending jobs)
        start_btn.enable()
        # Wait: only when running
        if ws == 'flying':
            wait_btn.enable()
        else:
            wait_btn.disable()
        # Resume: only when waiting
        if ws == 'waiting':
            resume_btn.enable()
        else:
            resume_btn.disable()
        # Stop: when running or wait_pending or waiting
        if ws in ('flying', 'wait_pending', 'waiting'):
            stop_btn.enable()
        else:
            stop_btn.disable()

    _update_control_buttons()

    ui.separator().classes('q-my-md')



    # -----------------------------------------------------------------------
    # Section 4: Status Line
    # -----------------------------------------------------------------------
    status_line = ui.label('Scout flight: 💤 idle').classes('text-body2 text-grey-7')

    def _build_status_line() -> str:
        ws = bundle.shared_state.get('walker_status', 'idle')
        jobs: list = list(bundle.shared_state.get('jobs', []))

        if ws == 'idle':
            return 'Scout flight: 💤 idle'

        if ws == 'wait_pending':
            return 'Scout flight: ⏳ Wait pending (after current batch)'

        if ws == 'waiting':
            pending_count = sum(
                1 for j in jobs if j.get('status') == 'pending'
            )
            return f'Scout flight: ⏸ Waiting  |  {pending_count} job(s) in queue'

        if ws in ('running', 'flying'):
            running_jobs = [j for j in jobs if j.get('status') == 'running']
            total_jobs = len(jobs)
            done_jobs = sum(1 for j in jobs if j.get('status') == 'done')
            job_idx = done_jobs + 1

            if running_jobs:
                rj = running_jobs[0]
                total_f = rj.get('files_total', 0)
                done_f = rj.get('files_done', 0)
                cur = rj.get('current_file', '')
                return (
                    f'Scout flight: 🚁 flying  |  '
                    f'Job {job_idx}/{total_jobs}  |  '
                    f'File {done_f}/{total_f}: {cur}'
                )
            return f'Scout flight: 🚁 flying  |  Job {job_idx}/{total_jobs}'

        return f'Scout flight: {ws}'

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