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
from .birdnet_labels import get_available_languages, load_birdnet_labels
from .species_translation import download_species_table
from .config import DEFAULT_LANGUAGE
from .utils import find_databases_recursive
from .db_queries import get_analysis_config, create_species_list_table


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

    lang = get_analysis_config(app_state.active_db, 'local_name_shortcut')
    app_state.language_code = lang if lang else 'de'
    logger.info(f"Language: {app_state.language_code}")


# ---------------------------------------------------------------------------
# Scout process management
# ---------------------------------------------------------------------------

def _start_scouting(
    bundle: QueueBundle,
    translation_list: list[dict],
    birdnet_labels: dict,
    use_gpu: bool,
    language_code: str,
) -> multiprocessing.Process:
    """
    Spawn the scout background process.

    Args:
        bundle:           QueueBundle from create_queues()
        translation_list: Species translation as list of dicts
        birdnet_labels:   Dict {scientific_name: local_name}
        use_gpu:          If True, BirdNET uses GPU

    Returns:
        Started Process object.
    """
    p = multiprocessing.Process(
        target=run_scout_process,
        args=(bundle, translation_list, birdnet_labels, use_gpu, language_code),
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
        translation_list=app.state.translation_list,
        birdnet_labels=app.state.birdnet_labels,
        use_gpu=app_state.use_gpu,
        language_code=app_state.language_code,
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

    # --- Species translation + BirdNET labels ---
    logger.info("Loading species translation table...")
    translation_df = download_species_table()
    translation_list: list[dict] = translation_df.to_dict(orient='records')

    logger.info(f"Loading BirdNET labels (language: {DEFAULT_LANGUAGE})...")
    available_langs = get_available_languages()
    if not available_langs:
        logger.error("No BirdNET label files found. Is the BirdNET model installed?")
        return 1
    birdnet_labels = load_birdnet_labels(DEFAULT_LANGUAGE)
    if not birdnet_labels:
        logger.error(f"Failed to load BirdNET labels for language '{DEFAULT_LANGUAGE}'")
        return 1

    # Scout process is started on demand from Scouting Flight (▶ Take off button)
    app.state.translation_list = translation_list
    app.state.birdnet_labels   = birdnet_labels

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