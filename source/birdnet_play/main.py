"""
BirdNET Play – main entry point.

Replaces cli.py and __main__.py. Starts the NiceGUI web server.
CLI playback mode (without GUI) is retained for direct use.

Usage:
    # Start GUI server (default mode):
    python -m birdnet_play /path/to/db_dir
    python -m birdnet_play /path/to/birdnet_analysis.db

    # CLI playback (no GUI):
    python -m birdnet_play /path/to/birdnet_analysis.db --species "Parus major"
    python -m birdnet_play /path/to/birdnet_analysis.db --export ./snippets/

    # Read-only server:
    python -m birdnet_play /path/to/db_dir --read-only
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger
from uvicorn import Config, Server
from nicegui import app, ui

from .app_state import AppState
from shared.streamlit_utils import find_databases_recursive
from shared.db_queries import get_analysis_config, create_species_list_table


# =============================================================================
# Server startup helpers
# =============================================================================

async def _startup_tasks(app_state: AppState) -> None:
    """
    Initialisation tasks that run once after the uvicorn server has started.

    - Scans root_path for databases and populates app_state.available_dbs.
    - Sets app_state.active_db to the first found database.
    - Loads language_code from the active database.
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


def run_server(root_path: Path, read_only: bool = False) -> None:
    app_state = AppState(root_path=root_path, read_only=read_only)
    app.state.app_state = app_state

    server: Server | None = None

    async def _on_startup():
        asyncio.create_task(_startup_tasks(app_state))

    app.on_startup(_on_startup)

    from . import pages  # noqa: F401

    def _on_sigterm(*_):
        logger.info("SIGTERM received – initiating graceful shutdown")
        if server is not None:
            server.should_exit = True

    signal.signal(signal.SIGTERM, _on_sigterm)

    config = Config(app, host='0.0.0.0', port=8090, log_level='warning')
    server = Server(config)

    logger.info("Starting NiceGUI server on http://0.0.0.0:8090")
    ui.run(port=8090, reload=False, show=False)
    logger.success("Server stopped")


# =============================================================================
# main() – argument parser + dispatch
# =============================================================================

def main() -> int:
    """
    Main entry point. Parses arguments and either starts the GUI server
    or runs CLI playback.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    parser = argparse.ArgumentParser(
        description="BirdNET Play – Bird detection audio player",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start GUI server:
  python -m birdnet_play /path/to/recordings/

  # CLI: play by species
  python -m birdnet_play /path/to/birdnet_analysis.db --species "Parus major"

  # CLI: export WAV snippets
  python -m birdnet_play /path/to/birdnet_analysis.db --export ./snippets/
        """
    )

    parser.add_argument(
        "input_path",
        type=str,
        help="Path to birdnet_analysis.db or directory containing databases"
    )
    parser.add_argument(
        "--read-only", "-r",
        action="store_true",
        help="Open database in read-only mode (GUI and CLI)"
    )

    # --- CLI-only arguments (ignored in server mode) ---
    parser.add_argument("--detection-id", "-i", type=int,
                        help="CLI: play specific detection by ID")
    parser.add_argument("--species", "-s", type=str,
                        help="CLI: filter by species name")
    parser.add_argument("--date", "-d", type=str,
                        help="CLI: filter by date (YYYY-MM-DD)")
    parser.add_argument("--time", "-t", type=str,
                        help="CLI: filter by time of day (HH:MM-HH:MM)")
    parser.add_argument("--min-confidence", "-c", type=float,
                        help="CLI: minimum confidence threshold (0.0–1.0)")
    parser.add_argument("--limit", "-l", type=int, default=50,
                        help="CLI: max number of detections (default: 50)")
    parser.add_argument("--offset", "-o", type=int, default=0,
                        help="CLI: pagination offset (default: 0)")
    parser.add_argument("--pm", type=float, default=1.0,
                        help="CLI: PM buffer in seconds (default: 1.0)")
    parser.add_argument("--sci", action="store_true",
                        help="CLI: use scientific names for TTS")
    parser.add_argument("--shuffle", action="store_true",
                        help="CLI: randomise playback order")
    parser.add_argument("--export", type=str, metavar="DIR",
                        help="CLI: export WAV files to directory instead of playing")

    args = parser.parse_args()
    input_path = Path(args.input_path)

    if not input_path.exists():
        logger.error(f"Path not found: {input_path}")
        return 1

    # ------------------------------------------------------------------
    # Decide mode: server (directory or db file without CLI filters)
    # vs. CLI playback (db file with at least one CLI filter or --export)
    # ------------------------------------------------------------------
    cli_mode_requested = any([
        args.detection_id,
        args.species,
        args.date,
        args.time,
        args.min_confidence,
        args.export,
    ])

    if input_path.is_dir() or not cli_mode_requested:
        # --- GUI server mode ---
        if input_path.is_file() and input_path.name != 'birdnet_analysis.db':
            logger.error(
                f"File must be named 'birdnet_analysis.db', got: {input_path.name}"
            )
            return 1

        root_path = input_path if input_path.is_dir() else input_path.parent
        try:
            run_server(root_path, read_only=args.read_only)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        return 0

    # --- CLI playback mode ---
    if input_path.is_dir():
        logger.error("CLI playback mode requires a database file, not a directory")
        return 1
    if input_path.name != 'birdnet_analysis.db':
        logger.error(
            f"File must be named 'birdnet_analysis.db', got: {input_path.name}"
        )
        return 1

    return _run_cli(args, input_path)


def _run_cli(args: argparse.Namespace, db_path: Path) -> int:
    """
    Execute CLI playback / export mode.
    Extracted from main() to keep it readable.

    Args:
        args: Parsed argument namespace.
        db_path: Validated path to birdnet_analysis.db.

    Returns:
        Exit code.
    """
    import random
    from shared.db_queries import (
        get_detection_by_id, query_detections, get_analysis_config,
        create_species_list_table
    )
    from .filters import DetectionFilter, parse_time_range, parse_date
    from .player import AudioPlayer, export_detections

    # Language
    language_code = get_analysis_config(db_path, 'local_name_shortcut') or 'de'
    logger.info(f"Database language: {language_code}")

    # Always update species list in CLI mode
    logger.info("Updating species list...")
    if not create_species_list_table(db_path):
        logger.warning("Failed to update species list, continuing anyway")

    # Build filter
    detection_filter = DetectionFilter(
        detection_id=args.detection_id,
        species=args.species,
        date_from=parse_date(args.date) if args.date else None,
        date_to=parse_date(args.date) if args.date else None,
        time_start=parse_time_range(args.time)[0] if args.time else None,
        time_end=parse_time_range(args.time)[1] if args.time else None,
        min_confidence=args.min_confidence,
        limit=args.limit,
        offset=args.offset,
        pm_seconds=args.pm,
        use_sci=args.sci,
    )

    error = detection_filter.validate()
    if error:
        logger.error(f"Invalid filter: {error}")
        return 1

    # Query detections
    if args.detection_id:
        detection = get_detection_by_id(db_path, args.detection_id)
        if not detection:
            logger.error(f"Detection #{args.detection_id} not found")
            return 1
        detections = [detection]
    else:
        detections = query_detections(db_path, **detection_filter.to_query_params())
        if not detections:
            logger.warning("No detections found matching filters")
            return 0
        logger.info(f"Found {len(detections)} detection(s)")

    if args.shuffle:
        random.shuffle(detections)
        logger.info("Shuffled playback order")

    filter_context = detection_filter.get_filter_context()

    # Export or play
    if args.export:
        export_dir = Path(args.export)
        logger.info(f"Exporting to {export_dir}...")
        # Minimal audio options for CLI export (no TTS by default)
        audio_options = {
            'say_audio_number': False,
            'say_id': False,
            'say_confidence': False,
            'bird_name_option': 'scientific' if args.sci else 'none',
            'speech_speed': 1.0,
            'speech_loudness': 0,
            'noise_reduce_strength': None,
        }
        export_detections(
            db_path, export_dir, detections,
            language_code, filter_context,
            audio_options, args.pm,
            disable_tts=not args.sci
        )
        logger.info(f"Export complete: {len(detections)} files")
        return 0

    # CLI playback
    from .cli_playback import cli_playback
    cli_playback(db_path, detections, language_code,
                 filter_context, args.pm, args.sci)
    return 0