#!/usr/bin/env python3
"""
Time correlation analyzer - main analysis logic.

Analyzes temporal correlations between bird species using a sliding window approach.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Set, Tuple
from collections import defaultdict

from loguru import logger
from shared.db_queries import get_db_connection


def run_time_correlation_analysis(
    db_path: Path,
    time_window_seconds: int
) -> Path:
    """
    Run time correlation analysis on a BirdNET database.
    
    Args:
        db_path: Path to birdnet_analysis.db
        time_window_seconds: Size of sliding window in seconds
        
    Returns:
        Path to output database (time_correlation.db)
    """
    logger.info(f"Starting time correlation analysis")
    logger.info(f"Input DB: {db_path}")
    logger.info(f"Time window: {time_window_seconds}s")
    
    # Get all species in database
    all_species = _get_all_species(db_path)
    logger.info(f"Found {len(all_species)} species in database")
    
    # Get time range of recordings
    start_time, end_time = _get_time_range(db_path)
    logger.info(f"Time range: {start_time} to {end_time}")
    
    # Initialize matrix for all species pairs
    # matrix[species_a][species_b] = (together_score, alone_count)
    matrix: Dict[str, Dict[str, Tuple[int, int]]] = defaultdict(
        lambda: defaultdict(lambda: (0, 0))
    )
    
    # Run sliding window analysis
    total_windows = _sliding_window_analysis(
        db_path=db_path,
        start_time=start_time,
        end_time=end_time,
        time_window_seconds=time_window_seconds,
        all_species=all_species,
        matrix=matrix
    )
    
    logger.info(f"Processed {total_windows} time windows")
    
    # Write results to output database
    output_db = db_path.parent / "time_correlation.db"
    _write_results(
        output_db=output_db,
        matrix=matrix,
        all_species=all_species,
        source_db=db_path,
        time_window_seconds=time_window_seconds,
        total_windows=total_windows
    )
    
    return output_db


def _get_all_species(db_path: Path) -> Dict[str, str]:
    """
    Get dict of all species with their local names.
    
    Args:
        db_path: Path to database
        
    Returns:
        Dict mapping scientific_name -> local_name (or scientific_name if local_name is NULL)
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT scientific_name, 
               COALESCE(MAX(local_name), scientific_name) as local_name_resolved
        FROM detections
        GROUP BY scientific_name
    """)
    
    species_dict = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return species_dict

def _get_time_range(db_path: Path) -> Tuple[datetime, datetime]:
    """
    Get time range of recordings in database.
    
    Args:
        db_path: Path to database
        
    Returns:
        Tuple of (start_time, end_time) as datetime objects
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            MIN(segment_start_local),
            MAX(segment_end_local)
        FROM detections
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    # Parse ISO format timestamps
    start_time = datetime.fromisoformat(row[0])
    end_time = datetime.fromisoformat(row[1])
    
    return start_time, end_time


def _sliding_window_analysis(
    db_path: Path,
    start_time: datetime,
    end_time: datetime,
    time_window_seconds: int,
    all_species: Dict[str, str],
    matrix: Dict[str, Dict[str, Tuple[int, int]]]
) -> int:
    """
    Perform sliding window analysis with 50% overlap.
    
    Args:
        db_path: Path to database
        start_time: Start of time range
        end_time: End of time range
        time_window_seconds: Window size in seconds
        all_species: Set of all species names
        matrix: Matrix to update (modified in-place)
        
    Returns:
        Total number of windows processed
    """
    window_delta = timedelta(seconds=time_window_seconds)
    step_delta = timedelta(seconds=time_window_seconds / 2)  # 50% overlap
    
    # Estimate total windows for progress tracking
    total_duration = (end_time - start_time).total_seconds()
    estimated_windows = int(total_duration / (time_window_seconds / 2)) + 1
    
    logger.info(f"Estimated windows: {estimated_windows}")
    
    current_start = start_time
    window_count = 0
    
    while current_start < end_time:
        window_count += 1
        current_end = current_start + window_delta
        
        # Process this time window
        _process_time_window(
            db_path=db_path,
            window_start=current_start,
            window_end=current_end,
            all_species=all_species,
            matrix=matrix
        )
        
        # Progress output
        progress_pct = (window_count / estimated_windows) * 100
        print(f"\rProgress: {progress_pct:.1f}% ({window_count}/{estimated_windows} windows)", end="", flush=True)
        
        # Move to next window (50% overlap)
        current_start += step_delta
    
    print()  # New line after progress
    return window_count


def _process_time_window(
    db_path: Path,
    window_start: datetime,
    window_end: datetime,
    all_species: Dict[str, str],
    matrix: Dict[str, Dict[str, Tuple[int, int]]]
):
    """
    Process a single time window and update the matrix.
    
    Args:
        db_path: Path to database
        window_start: Window start time
        window_end: Window end time
        all_species: Set of all species names
        matrix: Matrix to update (modified in-place)
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Query detections in this time window, grouped by species
    cursor.execute("""
        SELECT scientific_name, COUNT(*) as count
        FROM detections
        WHERE segment_start_local >= ? AND segment_start_local < ?
        GROUP BY scientific_name
    """, (window_start.isoformat(), window_end.isoformat()))
    
    # Build dict of species present in this window
    window_species: Dict[str, int] = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    if not window_species:
        # No detections in this window
        return
    
    present_species = set(window_species.keys())
    absent_species = set(all_species.keys()) - present_species
    
    # Update Value 1: Together score
    # For all pairs of species present in window, add min(count_a, count_b)
    species_list = list(present_species)
    for i, species_a in enumerate(species_list):
        for species_b in species_list[i+1:]:
            # Add to both (A,B) and (B,A)
            min_count = min(window_species[species_a], window_species[species_b])
            
            # Update (A,B)
            old_together, old_alone = matrix[species_a][species_b]
            matrix[species_a][species_b] = (old_together + min_count, old_alone)
            
            # Update (B,A)
            old_together, old_alone = matrix[species_b][species_a]
            matrix[species_b][species_a] = (old_together + min_count, old_alone)
    
    # Update Value 2: Alone count
    # For each present species, increment all pairs with absent species
    for present in present_species:
        for absent in absent_species:
            old_together, old_alone = matrix[present][absent]
            matrix[present][absent] = (old_together, old_alone + 1)


def _write_results(
    output_db: Path,
    matrix: Dict[str, Dict[str, Tuple[int, int]]],
    all_species: Dict[str, str],
    source_db: Path,
    time_window_seconds: int,
    total_windows: int
):
    """
    Write analysis results to output database.
    
    Args:
        output_db: Path to output database
        matrix: Results matrix
        source_db: Path to source database
        time_window_seconds: Window size used
        total_windows: Total windows analyzed
    """
    logger.info(f"Writing results to: {output_db}")
    
    # Remove old database if exists
    if output_db.exists():
        output_db.unlink()
    
    conn = sqlite3.connect(output_db)
    cursor = conn.cursor()
    
    # Create schema
    cursor.execute("""
        CREATE TABLE species_pairs (
            species_a TEXT NOT NULL,
            species_a_local TEXT NOT NULL,
            species_b TEXT NOT NULL,
            species_b_local TEXT NOT NULL,
            together_score INTEGER NOT NULL,
            alone_count INTEGER NOT NULL,
            PRIMARY KEY (species_a, species_b)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE analysis_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # Insert metadata
    cursor.execute(
        "INSERT INTO analysis_metadata (key, value) VALUES (?, ?)",
        ("time_window_seconds", str(time_window_seconds))
    )
    cursor.execute(
        "INSERT INTO analysis_metadata (key, value) VALUES (?, ?)",
        ("source_db", str(source_db))
    )
    cursor.execute(
        "INSERT INTO analysis_metadata (key, value) VALUES (?, ?)",
        ("created_at", datetime.now().isoformat())
    )
    cursor.execute(
        "INSERT INTO analysis_metadata (key, value) VALUES (?, ?)",
        ("total_windows_analyzed", str(total_windows))
    )
    
    # Insert species pairs (only where together_score >= 1)
    # Only write one direction (species_a < species_b) to avoid redundancy
    pairs_written = 0
    for species_a in matrix:
        for species_b in matrix[species_a]:
            together_score, alone_count = matrix[species_a][species_b]
            
            if together_score >= 1 and species_a < species_b:
                cursor.execute("""
                    INSERT INTO species_pairs (species_a, species_a_local, species_b, species_b_local, together_score, alone_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (species_a, all_species[species_a], species_b, all_species[species_b], together_score, alone_count))
                pairs_written += 1
    
    conn.commit()
    conn.close()
    
    logger.info(f"Wrote {pairs_written} species pairs to database")