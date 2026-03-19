"""
Task status helpers for birdnet-copter.

Provides a unified API for reporting running background tasks (Type A)
and wrapping short-lived GUI operations (Type B) with loading indicators.

Type A – background processes (scout, audio generation, …):
    Call set_task_running() to register / deregister a task in shared_state.

Type B – GUI operations (queries, scans, …):
    Use run_with_loading() as an async wrapper around run_in_executor calls.
"""

from typing import Any, Dict, Optional, Union

from nicegui import ui, run

# ---------------------------------------------------------------------------
# Task key constants
# ---------------------------------------------------------------------------

TASK_SCOUT          = 'scout'
TASK_AUDIO_GEN      = 'audio_gen'
TASK_GUI_OP         = 'gui_op'
TASK_EMBEDDING_SYNC = 'embedding_sync'
TASK_GLOBAL_SYNC    = 'global_sync'

ALL_TASK_KEYS = [
    TASK_SCOUT,
    TASK_AUDIO_GEN,
    TASK_GUI_OP,
    TASK_EMBEDDING_SYNC,
    TASK_GLOBAL_SYNC,
]


# ---------------------------------------------------------------------------
# Type A helper
# ---------------------------------------------------------------------------

def set_task_running(
    shared_state: Any,
    task_key: str,
    running: bool,
    label: str = '',
    progress: Optional[float] = None,
) -> None:
    """
    Register or deregister a background task in shared_state['tasks'].

    Uses a full-dict-replace pattern because multiprocessing.Manager().dict()
    does not propagate in-place mutations of nested objects.

    Args:
        shared_state: The multiprocessing Manager dict (app_state.shared_state
                      or bundle.shared_state).
        task_key:     One of the TASK_* constants defined in this module.
        running:      True while the task is active, False when done.
        label:        Human-readable status text shown in the GUI header.
        progress:     Optional 0.0–1.0 progress value; None if not applicable.
    """
    tasks: Dict = dict(shared_state.get('tasks', {}))
    tasks[task_key] = {
        'running':  running,
        'label':    label,
        'progress': progress,
    }
    shared_state['tasks'] = tasks


# ---------------------------------------------------------------------------
# Type B helper
# ---------------------------------------------------------------------------

async def run_with_loading(
    buttons: Union[ui.button, list],
    func,
    *args,
    shared_state: Optional[Any] = None,
    label: str = 'Processing…',
    **kwargs,
):
    """
    Async wrapper for GUI operations that run in a thread executor.

    While func is executing:
      - Each button in `buttons` gets the Quasar 'loading' prop and is disabled.
      - If shared_state is provided, TASK_GUI_OP is set to running=True so the
        header spinner activates for all connected browser tabs.

    After func returns (or raises):
      - Button state is restored.
      - TASK_GUI_OP is reset to running=False.

    Args:
        buttons:      A single ui.button or a list of ui.button instances.
        func:         A plain (non-async) callable to execute in the thread pool.
        *args:        Positional arguments forwarded to func.
        shared_state: Optional Manager dict; when provided the global spinner
                      is shown on all tabs during the operation.
        label:        Status text for the header while the operation runs.
                      Defaults to 'Processing…'.
        **kwargs:     Keyword arguments forwarded to func.

    Returns:
        The return value of func(*args, **kwargs).
    """
    if isinstance(buttons, ui.button):
        buttons = [buttons]

    # --- enter loading state ---
    for btn in buttons:
        btn.props('loading')
        btn.disable()

    if shared_state is not None:
        set_task_running(shared_state, TASK_GUI_OP, True, label)

    # --- run in executor ---
    result = None
    try:
        result = await run.io_bound(func, *args, **kwargs)
    finally:
        # --- restore button state ---
        for btn in buttons:
            btn.props(remove='loading')
            btn.enable()

        if shared_state is not None:
            set_task_running(shared_state, TASK_GUI_OP, False, '')

    return result
