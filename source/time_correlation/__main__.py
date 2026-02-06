#!/usr/bin/env python3
"""
CLI entry point for time correlation analyzer.

Usage:
    python -m time_correlation /path/to/birdnet_analysis.db [-t 300]
"""

import argparse
import sys
from pathlib import Path
from loguru import logger

from .analyzer import run_time_correlation_analysis


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Analyze temporal correlations between bird species detections"
    )
    
    parser.add_argument(
        "database",
        type=Path,
        help="Path to birdnet_analysis.db to analyze"
    )
    
    parser.add_argument(
        "-t", "--time-window",
        type=int,
        default=300,
        help="Time window size in seconds (default: 300)"
    )
    
    args = parser.parse_args()
    
    # Validate database exists
    if not args.database.exists():
        logger.error(f"Database not found: {args.database}")
        sys.exit(1)
    
    if not args.database.is_file():
        logger.error(f"Not a file: {args.database}")
        sys.exit(1)
    
    # Validate time window
    if args.time_window <= 0:
        logger.error(f"Time window must be positive, got: {args.time_window}")
        sys.exit(1)
    
    # Run analysis
    try:
        output_db = run_time_correlation_analysis(
            db_path=args.database,
            time_window_seconds=args.time_window
        )
        logger.info(f"Analysis complete. Results written to: {output_db}")
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()