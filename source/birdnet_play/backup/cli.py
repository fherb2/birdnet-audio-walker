"""
CLI interface for BirdNET Audio Player.
"""

import argparse
import sys
import time
from pathlib import Path
from loguru import logger
import subprocess

import sounddevice as sd
import soundfile as sf

from shared.db_queries import get_detection_by_id, query_detections, get_analysis_config
from .filters import DetectionFilter, parse_time_range, parse_date
from .player import AudioPlayer, export_detections
from .keyboard_control import KeyboardController


def cli_playback(
    db_path: Path,
    detections: list,
    language_code: str,
    filter_context: dict,
    pm_seconds: float,
    use_sci: bool
):
    """
    CLI playback with keyboard control.
    
    Args:
        db_path: Path to database
        detections: List of detections to play
        language_code: Language code for TTS
        filter_context: Filter context dict
        pm_seconds: PM buffer
        use_sci: Use scientific names
    """
    if not detections:
        logger.error("No detections to play")
        return
    
    player = AudioPlayer(db_path, pm_seconds)
    controller = KeyboardController()
    
    current_index = 0
    is_playing = False
    current_audio_data = None
    current_sample_rate = None
    
    print()
    print("=" * 80)
    print(f"Playing {len(detections)} detection(s)")
    print("=" * 80)
    print("Controls: SPACE=Pause/Replay, ← =Previous, → =Next, q=Quit")
    print("=" * 80)
    print()
    
    try:
        while current_index < len(detections):
            detection = detections[current_index]
            
            # Load audio if not already loaded
            if current_audio_data is None or not is_playing:
                try:
                    conf_pct = detection['confidence'] * 100
                    print(f"\r[{current_index + 1}/{len(detections)}] Loading: #{detection['detection_id']} - {detection.get('local_name', detection['scientific_name'])} ({conf_pct:.1f}%)", end='', flush=True)
                    
                    audio_bytes = player.prepare_detection_audio(
                        detection,
                        language_code,
                        filter_context,
                        use_sci
                    )
                    
                    current_audio_data, current_sample_rate = sf.read(audio_bytes)
                    
                except Exception as e:
                    logger.error(f"\nFailed to prepare detection #{detection['detection_id']}: {e}")
                    current_index += 1
                    current_audio_data = None
                    continue
                
                # Start playback
                conf_pct = detection['confidence'] * 100
                print(f"\r[{current_index + 1}/{len(detections)}] Playing: #{detection['detection_id']} - {detection.get('local_name', detection['scientific_name'])} ({conf_pct:.1f}%)       ", end='', flush=True)
                sd.play(current_audio_data, current_sample_rate)
                is_playing = True
            
            # Check for keyboard input and playback status
            while is_playing:
                key = controller.get_key_nonblocking()
                
                if key == 'space':  # SPACE - Pause/Replay
                    if sd.get_stream().active:
                        sd.stop()
                        is_playing = False
                        print("\r[PAUSED] Press SPACE to replay, ← /→  to navigate, q to quit", end='', flush=True)
                    else:
                        # Replay current
                        sd.play(current_audio_data, current_sample_rate)
                        is_playing = True
                        conf_pct = detection['confidence'] * 100
                        print(f"\r[{current_index + 1}/{len(detections)}] Playing: #{detection['detection_id']} - {detection.get('local_name', detection['scientific_name'])} ({conf_pct:.1f}%)       ", end='', flush=True)
                
                elif key == 'left':  # Previous
                    sd.stop()
                    current_index = max(0, current_index - 1)
                    current_audio_data = None
                    is_playing = False
                    break
                
                elif key == 'right':  # Next
                    sd.stop()
                    current_index += 1
                    current_audio_data = None
                    is_playing = False
                    break
                
                elif key == 'q':  # Quit
                    sd.stop()
                    print("\n\nPlayback stopped by user.")
                    return
                
                # Check if audio finished
                if not sd.get_stream().active:
                    is_playing = False
                    current_index += 1
                    current_audio_data = None
                    break
                
                time.sleep(0.05)
        
        print("\n\nPlayback finished!")
        
    except KeyboardInterrupt:
        sd.stop()
        print("\n\nPlayback interrupted.")
    except Exception as e:
        logger.error(f"Playback error: {e}")
        sd.stop()
    finally:
        # Cleanup: Stop keyboard controller
        controller.stop()


def main():
    """Main entry point for CLI."""
    
    # Setup logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # Argument parser
    parser = argparse.ArgumentParser(
        description="BirdNET Audio Player - Play detection audio snippets with TTS announcements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Play single detection
  birdnet-play /path/to/db.db --detection-id 12345
  
  # Play with species filter
  birdnet-play /path/to/db.db --species "Parus major"
  
  # Play with time filter
  birdnet-play /path/to/db.db --date 2025-04-16 --time 06:00-10:00
  
  # Export instead of playing
  birdnet-play /path/to/db.db --species "Kohlmeise" --export ./snippets/
  
  # Start Streamlit UI
  birdnet-play /path/to/db.db --ui
        """
    )
    
    parser.add_argument(
        "db_path",
        type=str,
        help="Path to birdnet_analysis.db database"
    )
    
    # Mode selection
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Start Streamlit web interface (default: CLI mode)"
    )
    
    # Detection selection
    parser.add_argument(
        "--detection-id", "-i",
        type=int,
        help="Play specific detection by ID"
    )
    
    # Filters
    parser.add_argument(
        "--species", "-s",
        type=str,
        help="Filter by species name (scientific, local, or Czech)"
    )
    
    parser.add_argument(
        "--date", "-d",
        type=str,
        help="Filter by date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--time", "-t",
        type=str,
        help="Filter by time of day (HH:MM-HH:MM)"
    )
    
    parser.add_argument(
        "--min-confidence", "-c",
        type=float,
        help="Minimum confidence threshold (0.0-1.0)"
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=50,
        help="Maximum number of detections (default: 50)"
    )
    
    parser.add_argument(
        "--offset", "-o",
        type=int,
        default=0,
        help="Start offset for pagination (default: 0)"
    )
    
    # Options
    parser.add_argument(
        "--pm",
        type=float,
        default=1.0,
        help="Plus/Minus buffer around detection in seconds (default: 1.0)"
    )
    
    parser.add_argument(
        "--sci",
        action="store_true",
        help="Use scientific names for TTS instead of local names"
    )
    
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomize playback order"
    )
    
    parser.add_argument(
        "--export",
        type=str,
        metavar="DIR",
        help="Export audio snippets as WAV files to directory instead of playing"
    )
    
    parser.add_argument(
        "--read-only", "-r",
        action="store_true",
        help="Open database in read-only mode (prevents modifications)"
    )
    
    args = parser.parse_args()
    
    # Validate database path
    input_path = Path(args.db_path)
    
    if not input_path.exists():
        logger.error(f"Path not found: {input_path}")
        return 1
    
    # Start Streamlit UI if requested
    if args.ui:
        # UI mode: Accept both directory and database file
        if input_path.is_file() and input_path.name != 'birdnet_analysis.db':
            logger.error(f"File must be named 'birdnet_analysis.db', got: {input_path.name}")
            return 1
        
        if input_path.is_dir():
            logger.info(f"Searching for databases in: {input_path}")
        
        # Streamlit will handle directory vs. file
        logger.info("Starting Streamlit UI...")

        
        # Get path to streamlit_app.py
        app_path = Path(__file__).parent / "streamlit_app.py"
        
        # Start streamlit
        cmd = ["streamlit", "run", str(app_path), "--", str(input_path.absolute())]

        # Add read-only flag if set
        if args.read_only:
            cmd.append("--read-only")
        
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            logger.info("Streamlit stopped")
        
        return 0
    
    # CLI/Export mode: Must be a database file
    if input_path.is_dir():
        logger.error("CLI mode requires a database file, not a directory")
        logger.error("Use --ui flag to work with directories")
        return 1
    
    if not input_path.name == 'birdnet_analysis.db':
        logger.error(f"File must be named 'birdnet_analysis.db', got: {input_path.name}")
        return 1
    
    db_path = input_path
    
    # Load language from database
    language_code = get_analysis_config(db_path, 'local_name_shortcut')
    if not language_code:
        logger.warning("Language not found in database, defaulting to 'de'")
        language_code = 'de'
    
    logger.info(f"Database language: {language_code}")
    
    # Create/update species_list table (always in CLI mode for fresh data)
    from shared.db_queries import create_species_list_table
    logger.info("Updating species list...")
    if create_species_list_table(db_path):
        logger.info("Species list updated successfully")
    else:    # Build filter
        logger.warning("Failed to update species list, continuing anyway...")
    
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
        use_sci=args.sci
    )
    
    # Validate filter
    error = detection_filter.validate()
    if error:
        logger.error(f"Invalid filter: {error}")
        return 1
    
    logger.info(f"Filter: {detection_filter}")
    
    # Query detections
    if args.detection_id:
        # Single detection by ID
        logger.info(f"Loading detection #{args.detection_id}...")
        detection = get_detection_by_id(db_path, args.detection_id)
        
        if not detection:
            logger.error(f"Detection #{args.detection_id} not found")
            return 1
        
        detections = [detection]
        
    else:
        # Query with filters
        logger.info("Querying detections...")
        detections = query_detections(db_path, **detection_filter.to_query_params())
        
        if not detections:
            logger.warning("No detections found matching filters")
            return 0
        
        logger.info(f"Found {len(detections)} detection(s)")
        
        # Shuffle if requested
        if args.shuffle:
            import random
            random.shuffle(detections)
            logger.info("Shuffled playback order")
    
    # Get filter context for TTS
    filter_context = detection_filter.get_filter_context()
    
    # Export or play
    if args.export:
        # Export mode
        export_dir = Path(args.export)
        logger.info(f"Exporting to {export_dir}...")
        
        export_detections(
            db_path,
            export_dir,
            detections,
            language_code,
            filter_context,
            args.pm,
            args.sci
        )
        
        logger.info(f"Export complete: {len(detections)} files")
        
    else:
        # Playback mode
        cli_playback(
            db_path,
            detections,
            language_code,
            filter_context,
            args.pm,
            args.sci
        )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
