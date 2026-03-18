"""
GPU watchdog for the scout process.

Detects CUDA hangs by monitoring GPU utilization while BirdNET is active.
If utilization stays below GPU_HANG_THRESHOLD_PCT for GPU_HANG_TIMEOUT_S
seconds while the scout process is alive and birdnet_active is set,
a hang is assumed: the scout process is killed and gpu_error is set on
app_state so the GUI can inform the user.
"""

import asyncio
import subprocess
import time
from typing import Callable, Optional

import multiprocessing

import psutil
from loguru import logger

from .app_state import AppState
from .job_queue import QueueBundle


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

GPU_POLL_INTERVAL_S    = 5   # seconds between nvidia-smi polls
GPU_HANG_THRESHOLD_PCT = 20  # GPU utilization below this = suspicious
GPU_HANG_TIMEOUT_S     = 30  # seconds below threshold before triggering


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_gpu_utilization() -> Optional[int]:
    """
    Query GPU utilization via nvidia-smi.

    Blocking – must be called via run_in_executor.

    Returns:
        GPU utilization in percent (0–100), or None if nvidia-smi is
        unavailable or returns an unexpected result.
    """
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.strip().split('\n')[0])
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError):
        return None

def _trigger_gpu_error(
    app_state: AppState,
    bundle: QueueBundle,
    scout_process: multiprocessing.Process,
) -> None:
    """
    React to a detected GPU hang:

    1. Terminate the scout process (SIGTERM, then SIGKILL after 3 s).
    2. Set walker_status to 'error' in shared_state.
    3. Set app_state.gpu_error with message and kill command.
    4. Log a prominent error message to the CLI.

    Args:
        app_state:     Global AppState instance.
        bundle:        QueueBundle (for shared_state).
        scout_process: The hanging scout multiprocessing.Process.
        kill_cmd:      Pre-built "sudo kill -9 ..." string (may be empty).
    """
    # --- terminate scout process ---
    try:
        scout_process.terminate()
        scout_process.join(timeout=3.0)
        if scout_process.is_alive():
            scout_process.kill()
            logger.warning("Watchdog: scout did not exit after SIGTERM, sent SIGKILL")
    except Exception as e:
        logger.warning(f"Watchdog: error while terminating scout process: {e}")

    # --- update shared_state ---
    try:
        bundle.shared_state['walker_status'] = 'error'
        bundle.shared_state['birdnet_active'] = False
    except Exception as e:
        logger.warning(f"Watchdog: could not update shared_state: {e}")

    # --- build gpu_error dict ---
    kill_section = (
        'nvidia-smi --query-compute-apps=pid,used_memory --format=csv\n'
        'sudo kill -9 <PIDs from the command above>'
    )

    message = (
        'The Scout process has hung due to a CUDA error'
        'and has been terminated. The GPU may have left behind zombie contexts,'
        'which must be cleaned up manually.\n\n'
        'Please run the following commands ON THE HOST (not inside the container),'
        'then restart birdnet-copter.'
    )

    app_state.gpu_error = {'message': message, 'kill_cmd': kill_section}

    # --- CLI output ---
    logger.error(
        '\n'
        '╔══════════════════════════════════════════════════════════════════╗\n'
        '║  CUDA ERROR: GPU hung – Scout process stopped; restart required  ║\n'
        '╠══════════════════════════════════════════════════════════════════╣\n'
        '║  Sometimes the GPU leaves behind zombie contexts that            ║\n'
        '║  must be cleaned up manually.                                    ║\n'
        '║                                                                  ║\n'
        '║  Command to check for such processes:                            ║\n'
        "║  'nvidia-smi --query-compute-apps=pid,used_memory --format=csv'  ║\n"
        "║  'sudo kill -9 <PIDs from the command above>'                    ║\n"
        '║                                                                  ║\n'
        '║  Afterward: Restart birdnet-copter.                              ║\n'
        '╚══════════════════════════════════════════════════════════════════╝'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_watchdog(
    app_state: AppState,
    bundle: QueueBundle,
    get_scout_process: Callable[[], Optional[multiprocessing.Process]],
) -> None:
    """
    Asyncio task: monitor the scout process for GPU hangs.

    Runs as an infinite loop until a GPU error is triggered or the
    application shuts down (asyncio.CancelledError is silently swallowed).

    The watchdog is active whenever:
      - A scout process exists and is alive
      - walker_status is NOT 'idle'
      - bundle.shared_state['birdnet_active'] is True

    A hang is detected when GPU utilization stays below
    GPU_HANG_THRESHOLD_PCT for at least GPU_HANG_TIMEOUT_S seconds
    under the conditions above.

    Args:
        app_state:         Global AppState instance (for gpu_error flag).
        bundle:            QueueBundle (for shared_state).
        get_scout_process: Callable returning the current scout Process or None.
                           Pass as: lambda: getattr(app.state, 'scout_process', None)
    """
    logger.info("GPU watchdog started")
    loop = asyncio.get_event_loop()

    low_since: Optional[float] = None  # monotonic time when util first dropped low

    try:
        while True:
            await asyncio.sleep(GPU_POLL_INTERVAL_S)

            # --- guard: scout must be alive ---
            scout = get_scout_process()
            if scout is None or not scout.is_alive():
                low_since = None
                continue

            # --- guard: scout must not be idle ---
            walker_status = bundle.shared_state.get('walker_status', 'idle')
            if walker_status == 'idle':
                low_since = None
                continue

            # --- guard: BirdNET must currently be running ---
            if not bundle.shared_state.get('birdnet_active', False):
                low_since = None
                continue

            # --- query GPU utilization (blocking call in thread pool) ---
            util = await loop.run_in_executor(None, _get_gpu_utilization)

            if util is None:
                # nvidia-smi not available – watchdog cannot function
                continue

            # --- hang detection ---
            if util < GPU_HANG_THRESHOLD_PCT:
                if low_since is None:
                    low_since = time.monotonic()
                    logger.debug(
                        f"Watchdog: GPU util dropped to {util}% – starting hang timer"
                    )
                elif time.monotonic() - low_since >= GPU_HANG_TIMEOUT_S:
                    logger.warning(
                        f"Watchdog: GPU util below {GPU_HANG_THRESHOLD_PCT}% "
                        f"for {GPU_HANG_TIMEOUT_S}s – hang detected!"
                    )
                    _trigger_gpu_error(app_state, bundle, scout)
                    return  # watchdog exits after triggering
            else:
                if low_since is not None:
                    logger.debug(
                        f"Watchdog: GPU util recovered to {util}% – resetting hang timer"
                    )
                low_since = None

    except asyncio.CancelledError:
        logger.info("GPU watchdog cancelled")