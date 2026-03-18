"""
birdnet-copter – backend main.

Starts three processes:
  1. This process (main): hardware detection, AppState init, queue management
  2. Scouting Flight:      sequential BirdNET analysis
  3. GUI server:           NiceGUI / uvicorn (started last, blocks until shutdown)

Usage:
    python -m birdnet_copter [input_path] [--read-only]

    input_path: root folder for recordings (default: user home directory)
"""

import argparse
import multiprocessing
import signal
import sys
from pathlib import Path

from loguru import logger
from nicegui import app, ui

from .app_state import AppState
from .hardware import detect_hardware
from .job_queue import create_queues, shutdown_scouting, QueueBundle
from .scout_process import run_scout_process
from .utils import find_databases_recursive
from .db_queries import create_species_list_table
from .scout_watchdog import run_watchdog


# ---------------------------------------------------------------------------
# Startup tasks (run once after uvicorn is up)
# ---------------------------------------------------------------------------

async def _startup_tasks(app_state: AppState) -> None:
    """
    Scan root_path for databases and set the first one as active.
    Loads language_code from the active database.
    """
    logger.info(f"Scanning for databases in: {app_state.root_path}")
    app_state.available_dbs = find_databases_recursive(app_state.root_path)

    if not app_state.available_dbs:
        logger.warning("No birdnet_analysis.db files found in root path")
        return

    app_state.active_db = app_state.available_dbs[0]
    logger.info(f"Active database: {app_state.active_db}")
    # Bird language stays at default 'de' – configurable via Hangar
    logger.info(f"Bird language: {app_state.bird_language_code}")


# ---------------------------------------------------------------------------
# Scout process management
# ---------------------------------------------------------------------------

def _start_scouting(
    bundle: QueueBundle,
    use_gpu: bool,
) -> multiprocessing.Process:
    p = multiprocessing.Process(
        target=run_scout_process,
        args=(bundle, use_gpu),
        name="scouting_flight",
        daemon=False,
    )
    p.start()
    logger.info(f"Scout process started (pid={p.pid})")
    return p

def start_scout_process(bundle: QueueBundle) -> None:
    """
    Start the scout background process on demand (called from Scouting Flight).
    Does nothing if the scout is already flying.
    """
    wp = getattr(app.state, 'scout_process', None)
    if wp is not None and wp.is_alive():
        logger.debug("Scout process already flying, skipping start")
        return

    app_state: AppState = app.state.app_state
    p = _start_scouting(
        bundle=bundle,
        use_gpu=app_state.use_gpu,
    )
    app.state.scout_process = p
    logger.info("Scout process started on demand")

# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> int:
    """
    birdnet-copter entry point.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    # Must be first – required for 'spawn' start method on all platforms
    multiprocessing.set_start_method('spawn')

    # --- Logging ---
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # --- CLI arguments ---
    parser = argparse.ArgumentParser(
        description="birdnet-copter – BirdNET analysis and playback",
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=str(Path.home()),
        help="Root folder for recordings (default: user home directory)",
    )
    parser.add_argument(
        "--read-only", "-r",
        action="store_true",
        help="Open databases in read-only mode",
    )
    args = parser.parse_args()

    root_path = Path(args.input_path).expanduser().resolve()
    if not root_path.exists():
        logger.error(f"Input path does not exist: {root_path}")
        return 1

    # --- Hardware detection ---
    logger.info("Detecting hardware...")
    hw_info = detect_hardware()

    # --- AppState ---
    app_state = AppState(
        root_path=root_path,
        read_only=args.read_only,
        hw_info=hw_info,
        use_gpu=hw_info.has_nvidia_gpu,
    )

    # --- Multiprocessing manager + shared_state ---
    manager = multiprocessing.Manager()
    shared_state = manager.dict()
    shared_state['jobs'] = []
    shared_state['walker_status'] = 'idle'

    app_state.shared_state = shared_state

    # --- Queues ---
    bundle = create_queues(shared_state)

    # --- Signal handlers ---
    def _signal_handler(signum, frame):
        logger.warning(f"Signal {signum} received – initiating shutdown")
        shutdown_scouting(bundle)
        wp = getattr(app.state, 'scout_process', None)
        if wp is not None:
            wp.join(timeout=5.0)
            if wp.is_alive():
                logger.warning("Scout process did not exit cleanly, terminating")
                wp.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # --- NiceGUI / uvicorn ---
    app.state.app_state = app_state
    app.state.bundle    = bundle

    import asyncio

    async def _on_startup():
        asyncio.create_task(_startup_tasks(app_state))
        asyncio.create_task(
            run_watchdog(
                app_state=app_state,
                bundle=bundle,
                get_scout_process=lambda: getattr(app.state, 'scout_process', None),
            )
        )

    app.on_startup(_on_startup)

    # Import pages so all @ui.page routes are registered
    from . import pages  # noqa: F401

    logger.info("Starting NiceGUI server on http://0.0.0.0:8090")
    ui.run(port=8090, reload=False, show=False)

    # --- Shutdown ---
    logger.info("GUI server stopped – shutting down scout process")
    shutdown_scouting(bundle)
    wp = getattr(app.state, 'scout_process', None)
    if wp is not None:
        wp.join(timeout=5.0)
        if wp.is_alive():
            logger.warning("Scout process did not exit cleanly, terminating")
            wp.terminate()

    manager.shutdown()
    logger.success("birdnet-copter stopped")
    return 0