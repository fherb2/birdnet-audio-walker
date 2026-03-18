"""
SQLite database management for BirdNET Batch Analyzer.
"""

#
# Hinweis zu birdnet_play (oder anderen Auswertezugriffen):
# ---------------------------------------------------------
#
# 1. HDF5-Datei wird schreibend nur in birdnet_analyzer.py verwaltet
# 2. Zum Auslesen später (in birdnet_play):
#    
#    import h5py
#    
#    # Get embedding_idx from database
#    cursor.execute("SELECT embedding_idx FROM detections WHERE id = ?", (det_id,))
#    idx = cursor.fetchone()[0]
#    
#    # Load embedding from HDF5
#    hdf5_path = get_hdf5_path(db_path)
#    with h5py.File(hdf5_path, 'r') as f:
#        embedding = f['embeddings'][idx]  # Shape: (1024,)

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger


def init_database(db_path: str):
    """
    Initialize SQLite database with schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable WAL mode for better concurrency
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            timestamp_utc TEXT NOT NULL,
            timestamp_local TEXT NOT NULL,
            timezone TEXT NOT NULL,
            serial TEXT,
            gps_lat REAL,
            gps_lon REAL,
            sample_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            duration_seconds REAL,
            temperature_c REAL,
            battery_voltage REAL,
            gain TEXT,
            firmware TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            segment_start_utc TEXT NOT NULL,
            segment_start_local TEXT NOT NULL,
            segment_end_utc TEXT NOT NULL,
            segment_end_local TEXT NOT NULL,
            timezone TEXT NOT NULL,
            scientific_name TEXT NOT NULL,
            confidence REAL NOT NULL,
            FOREIGN KEY (filename) REFERENCES metadata(filename)
        )
    """)

    # Processing status tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_status (
            filename TEXT PRIMARY KEY,
            completed_at TEXT NOT NULL,
            FOREIGN KEY (filename) REFERENCES metadata(filename)
        )
    """)
    
    # Analysis config table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized: {db_path}")


def insert_metadata(db_path: str, metadata: dict):
    """
    Insert file metadata into database.
    
    Args:
        db_path: Path to SQLite database
        metadata: Metadata dictionary from audiomoth_import
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO metadata 
            (filename, timestamp_utc, timestamp_local, timezone, serial, 
             gps_lat, gps_lon, sample_rate, channels, bit_depth, 
             duration_seconds, temperature_c, battery_voltage, gain, firmware)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metadata['filename'],
            metadata['timestamp_utc'].isoformat(),
            metadata['timestamp_local'].isoformat(),
            metadata['timezone'],
            metadata.get('serial'),
            metadata.get('gps_lat'),
            metadata.get('gps_lon'),
            metadata.get('sample_rate'),
            metadata.get('channels'),
            metadata.get('bit_depth'),
            metadata.get('duration_seconds'),
            metadata.get('temperature_c'),
            metadata.get('battery_voltage'),
            metadata.get('gain'),
            metadata.get('firmware')
        ))
        
        conn.commit()
        logger.debug(f"Metadata inserted for {metadata['filename']}")
    except Exception as e:
        logger.error(f"Error inserting metadata for {metadata['filename']}: {e}")
        conn.rollback()
    finally:
        conn.close()



def batch_insert_detections(
    db_path: str,
    filename: str,
    metadata: dict,
    detections: list[dict],
):
    """
    Insert all detections from one file in a single transaction.

    Args:
        db_path:    Path to SQLite database
        filename:   Original WAV filename
        metadata:   File metadata dict
        detections: List of detection dicts from BirdNET.
    """
    if not detections:
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN TRANSACTION")

        for detection in detections:
            start_s = detection['start_time']
            end_s   = detection['end_time']

            seg_start_utc   = metadata['timestamp_utc']   + timedelta(seconds=start_s)
            seg_end_utc     = metadata['timestamp_utc']   + timedelta(seconds=end_s)
            seg_start_local = metadata['timestamp_local'] + timedelta(seconds=start_s)
            seg_end_local   = metadata['timestamp_local'] + timedelta(seconds=end_s)

            cursor.execute("""
                INSERT INTO detections
                (filename, segment_start_utc, segment_start_local,
                 segment_end_utc, segment_end_local, timezone,
                 scientific_name, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename,
                seg_start_utc.isoformat(),
                seg_start_local.isoformat(),
                seg_end_utc.isoformat(),
                seg_end_local.isoformat(),
                metadata['timezone'],
                detection['scientific_name'],
                detection['confidence'],
            ))

        conn.commit()
        logger.debug(f"Batch inserted {len(detections)} detections for {filename}")

    except Exception as e:
        logger.error(f"Error batch inserting detections for {filename}: {e}")
        conn.rollback()
    finally:
        conn.close()



def create_indices(db_path: str):
    """
    Create database indices after all inserts are complete.
    
    This is much faster than maintaining indices during inserts.
    
    Args:
        db_path: Path to SQLite database
    """
    logger.info("Creating database indices...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Index for time-based queries (segment start times)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_segment_start
            ON detections(segment_start_local)
        """)
        
        # Index for species-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_species 
            ON detections(scientific_name)
        """)
        
        # Index for filename-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_filename 
            ON detections(filename)
        """)
        
        conn.commit()
        logger.info("Database indices created ✓")
        
    except Exception as e:
        logger.error(f"Error creating indices: {e}")
    finally:
        conn.close()


def set_file_status(db_path: str, filename: str, status: str):
    """
    Mark a file as completed in processing_status.

    Args:
        db_path: Path to SQLite database
        filename: Filename to mark as completed
        status: Only 'completed' is valid
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO processing_status (filename, completed_at) "
            "VALUES (?, ?)",
            (filename, datetime.now().isoformat())
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error setting status for {filename}: {e}")
        conn.rollback()
    finally:
        conn.close()

        
        
def rebuild_detections(db_path: str, filenames: list[str] | None = None) -> None:
    """
    Prepare database for a full rescan (Rebuild job).

    Keeps all metadata intact. Deletes all detections, resets all
    processing_status entries, and deletes the corresponding HDF5 groups.

    Args:
        db_path:   Path to SQLite database
        filenames: If given, only rebuild these files. If None, rebuild all.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        if filenames is None:
            cursor.execute("DELETE FROM detections")
            cursor.execute("DELETE FROM processing_status")
        else:
            for fn in filenames:
                cursor.execute("DELETE FROM detections WHERE filename = ?", (fn,))
                cursor.execute("DELETE FROM processing_status WHERE filename = ?", (fn,))
        conn.commit()
        logger.info(f"Rebuild: detections cleared for "
                    f"{'all files' if filenames is None else len(filenames)} file(s): {db_path}")
    except Exception as e:
        logger.error(f"Error during rebuild_detections: {e}")
        conn.rollback()
    finally:
        conn.close()

    # Delete HDF5 groups for affected files
    hdf5_path = Path(get_hdf5_path(db_path))
    if not hdf5_path.exists():
        return

    try:
        import h5py
        with h5py.File(str(hdf5_path), 'a') as f:
            targets = filenames if filenames is not None else list(f.keys())
            for fn in targets:
                if fn in f:
                    del f[fn]
                    logger.debug(f"Rebuild: HDF5 group deleted: {fn}")
        logger.info(f"Rebuild: HDF5 groups cleared")
    except Exception as e:
        logger.error(f"Rebuild: failed to delete HDF5 groups: {e}")


def check_indices_exist(db_path: str) -> bool:
    """
    Check if any of the indices exist.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        True if any index exists, False otherwise
    """
    from .config import INDEX_NAMES
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        for index_name in INDEX_NAMES:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name=?
            """, (index_name,))
            
            if cursor.fetchone() is not None:
                return True
        
        return False
        
    finally:
        conn.close()


def drop_all_indices(db_path: str):
    """
    Drop all custom indices.
    
    Args:
        db_path: Path to SQLite database
    """
    from .config import INDEX_NAMES
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        for index_name in INDEX_NAMES:
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
            logger.debug(f"Dropped index: {index_name}")
        
        conn.commit()
        logger.info("All indices dropped")
        
        # Vacuum to reclaim space after dropping indices
        conn.close()  # Close connection before vacuum
        vacuum_database(db_path)
        return  # Return early to skip the finally close
        
    except Exception as e:
        logger.error(f"Error dropping indices: {e}")
    finally:
        conn.close()




def get_missing_files(db_path: str, wav_files: list[str]) -> list[str]:
    """
    Get list of WAV files that are not yet in the database.
    
    Args:
        db_path: Path to SQLite database
        wav_files: List of WAV filenames in the folder
        
    Returns:
        List of filenames not yet in database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all filenames in metadata table
        cursor.execute("SELECT filename FROM metadata")
        existing_files = {row[0] for row in cursor.fetchall()}
        
        # Find missing files
        missing = [f for f in wav_files if f not in existing_files]
        
        if missing:
            logger.info(f"Found {len(missing)} new files not yet in database")
        
        return missing
        
    finally:
        conn.close()
        
        

def get_hdf5_path(db_path: str) -> str:
    """
    Get HDF5 file path for given database path.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Path to HDF5 file (same folder as DB)
    """
    from pathlib import Path
    from .config import HDF5_FILENAME
    
    db_path = Path(db_path)
    hdf5_path = db_path.parent / HDF5_FILENAME
    
    return str(hdf5_path)

        

def vacuum_database(db_path: str):
    """
    Vacuum database to reclaim space after deletions.
    
    Args:
        db_path: Path to SQLite database
    """
    logger.info("Vacuuming database to reclaim space...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("VACUUM")
        conn.commit()
        logger.info("Database vacuumed ✓")
        
    except Exception as e:
        logger.error(f"Error vacuuming database: {e}")
    finally:
        conn.close()