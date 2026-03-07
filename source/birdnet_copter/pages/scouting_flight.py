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

    ui.label('🔭 Scouting Flight').classes('text-h5 q-mt-md q-mb-sm')

    # Page-local state
    page: dict = {
        'walker_started': False,       # True once ▶ Start has been pressed
        'added_folders': set(),        # folders already added this session
    }

    # -----------------------------------------------------------------------
    # Section 1: Folder View
    # -----------------------------------------------------------------------
    ui.label('📂 Folder Selection').classes('text-h6 q-mb-xs')

    def _add_folder_to_jobs(folder: Path) -> None:
        """Add a folder as a new ScanJob (once per session)."""
        if folder in page['added_folders']:
            ui.notify(f'Already in scout list: {folder.name}', type='warning')
            return
        page['added_folders'].add(folder)
        job = ScanJob(
            folder_path=folder,
            scan_embeddings=state.use_embeddings,
            rescan_species=False,
            min_conf=0.4,
        )
        # Register in shared_state so GUI sees it immediately;
        # actual queue send happens when ▶ Start is clicked.
        jobs: list = list(bundle.shared_state.get('jobs', []))
        from ..job_queue import progress_msg
        jobs.append(progress_msg(job))
        bundle.shared_state['jobs'] = jobs
        # Keep the ScanJob object for later sending
        pending: list = list(bundle.shared_state.get('pending_jobs', []))
        pending.append(job)
        bundle.shared_state['pending_jobs'] = pending
        logger.debug(f'Folder staged for scouting: {folder}')
        ui.notify(f'Added: {folder.name}', type='positive')
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
    # Section 2: Job Controls
    # -----------------------------------------------------------------------
    ui.label('🎛 Controls').classes('text-h6 q-mb-xs')

    with ui.row().classes('gap-2 items-center q-mb-sm flex-wrap'):

        async def _on_start() -> None:
            """Start walker if not running; flush pending jobs into job_queue."""
            if not page['walker_started']:
                start_walker_process(bundle)
                page['walker_started'] = True
                bundle.shared_state['walker_status'] = 'running'

            # Send all pending (not-yet-queued) jobs to the walker
            pending: list = list(bundle.shared_state.get('pending_jobs', []))
            for job in pending:
                bundle.job_queue.put(job)
                logger.debug(f'Job sent to walker: {job.folder_path}')
            bundle.shared_state['pending_jobs'] = []
            _update_control_buttons()

        start_btn = ui.button('▶ Start', on_click=_on_start).props('no-caps color=positive')

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

        async def _on_scout_everything() -> None:
            """Add single job for entire tree under root_path."""
            root = state.root_path
            if root in page['added_folders']:
                ui.notify('Root folder already in scout list.', type='warning')
                return
            page['added_folders'].add(root)
            job = ScanJob(
                folder_path=root,
                scan_embeddings=state.use_embeddings,
                rescan_species=False,
                min_conf=0.4,
            )
            from ..job_queue import progress_msg
            jobs: list = list(bundle.shared_state.get('jobs', []))
            jobs.append(progress_msg(job))
            bundle.shared_state['jobs'] = jobs
            pending: list = list(bundle.shared_state.get('pending_jobs', []))
            pending.append(job)
            bundle.shared_state['pending_jobs'] = pending
            logger.debug(f'Scout everything job staged: {root}')
            ui.notify(f'Added root folder: {root.name}', type='positive')
            _refresh_job_table()

        ui.button(
            '🔭 Scout everything', on_click=_on_scout_everything
        ).props('no-caps')

    def _update_control_buttons() -> None:
        """En-/disable buttons based on walker_status."""
        ws = bundle.shared_state.get('walker_status', 'idle')
        # Start: always available (re-flushes pending jobs)
        start_btn.enable()
        # Wait: only when running
        if ws == 'running':
            wait_btn.enable()
        else:
            wait_btn.disable()
        # Resume: only when waiting
        if ws == 'waiting':
            resume_btn.enable()
        else:
            resume_btn.disable()
        # Stop: when running or wait_pending or waiting
        if ws in ('running', 'wait_pending', 'waiting'):
            stop_btn.enable()
        else:
            stop_btn.disable()

    _update_control_buttons()

    ui.separator().classes('q-my-md')

    # -----------------------------------------------------------------------
    # Section 3: Job List
    # -----------------------------------------------------------------------
    ui.label('📋 Job List').classes('text-h6 q-mb-xs')

    STATUS_ICONS = {
        'pending': '⏳',
        'running': '🔄',
        'done':    '✅',
        'error':   '❌',
        'skipped': '⏭',
    }

    job_table_container = ui.column().classes('w-full gap-1')

    def _refresh_job_table() -> None:
        jobs: list = list(bundle.shared_state.get('jobs', []))
        job_table_container.clear()
        if not jobs:
            with job_table_container:
                ui.label('No jobs yet.').classes('text-caption text-grey-6')
            return

        rows = []
        for j in jobs:
            status = j.get('status', 'pending')
            icon = STATUS_ICONS.get(status, '?')
            total = j.get('files_total', 0)
            done = j.get('files_done', 0)
            progress = f'{done}/{total}' if total > 0 else '–'
            rows.append({
                '#':           str(len(rows) + 1),
                'Folder':      Path(j.get('folder_path', '')).name,
                'Status':      f'{icon} {status}',
                'Progress':    progress,
                'Current file': j.get('current_file', ''),
                'Error':       j.get('error_msg', ''),
            })

        cols = [
            {'name': k, 'label': k, 'field': k, 'align': 'left'}
            for k in rows[0]
        ]
        with job_table_container:
            ui.table(
                columns=cols,
                rows=rows,
                pagination=0,
            ).classes('w-full').props('flat bordered dense')

    _refresh_job_table()

    ui.separator().classes('q-my-md')

    # -----------------------------------------------------------------------
    # Section 4: Status Line
    # -----------------------------------------------------------------------
    status_line = ui.label('Walker: 💤 idle').classes('text-body2 text-grey-7')

    def _build_status_line() -> str:
        ws = bundle.shared_state.get('walker_status', 'idle')
        jobs: list = list(bundle.shared_state.get('jobs', []))

        if ws == 'idle':
            return 'Walker: 💤 idle'

        if ws == 'wait_pending':
            return 'Walker: ⏳ Wait pending (after current batch)'

        if ws == 'waiting':
            pending_count = sum(
                1 for j in jobs if j.get('status') == 'pending'
            )
            return f'Walker: ⏸ Waiting  |  {pending_count} job(s) in queue'

        if ws == 'running':
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
                    f'Walker: 🔄 running  |  '
                    f'Job {job_idx}/{total_jobs}  |  '
                    f'File {done_f}/{total_f}: {cur}'
                )
            return f'Walker: 🔄 running  |  Job {job_idx}/{total_jobs}'

        return f'Walker: {ws}'

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