"""
Database query functions for BirdNET tools.
Read-only access to analysis databases.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, time
from loguru import logger

# Species list confidence threshold
CONFIDENCE_THRESHOLD_HIGH = 0.7  # Detections above this are "high confidence"


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """
    Open database connection with WAL mode.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        SQLite connection with Row factory for dict-like access
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_analysis_config(db_path: Path, key: str) -> Optional[str]:
    """
    Read value from analysis_config table.
    
    Args:
        db_path: Path to SQLite database
        key: Config key to read
        
    Returns:
        Config value or None if not found
    """
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute(
            "SELECT value FROM analysis_config WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        return row['value'] if row else None
    except sqlite3.OperationalError:
        # Table doesn't exist (old database)
        logger.warning(f"analysis_config table not found in {db_path}")
        return None
    finally:
        conn.close()


def set_analysis_config(db_path: Path, key: str, value: str) -> bool:
    """
    Schreibt/aktualisiert Wert in analysis_config Tabelle.
    
    Args:
        db_path: Pfad zur Datenbank
        key: Config-Key
        value: Wert zum Speichern
        
    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    try:
        conn = get_db_connection(db_path)
        
        # INSERT OR REPLACE (upsert)
        conn.execute(
            "INSERT OR REPLACE INTO analysis_config (key, value) VALUES (?, ?)",
            (key, value)
        )
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to set analysis_config '{key}': {e}")
        return False


def get_all_metadata(db_path: Path) -> List[Dict]:
    """
    Lädt alle File-Metadaten aus der metadata Tabelle.
    
    Returns:
        Liste von Dicts mit allen Metadata-Feldern
    """
    try:
        conn = get_db_connection(db_path)
        
        query = """
            SELECT 
                filename,
                timestamp_utc,
                timestamp_local,
                timezone,
                serial,
                gps_lat,
                gps_lon,
                sample_rate,
                channels,
                bit_depth,
                duration_seconds,
                temperature_c,
                battery_voltage,
                gain,
                firmware
            FROM metadata
            ORDER BY timestamp_local ASC
        """
        
        cursor = conn.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to load metadata: {e}")
        return []


def species_list_exists(db_path: Path) -> bool:
    """
    Check if species_list table exists in database.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        True if table exists, False otherwise
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='species_list'"
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"Failed to check species_list existence: {e}")
        return False


def create_species_list_table(db_path: Path) -> bool:
    """
    Create/recreate species_list table and populate with unique species from detections.
    Includes high/low confidence counts and score for intelligent sorting.
    
    Drops existing table if present, then creates new one with all unique species.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        True if successful, False on error
    """
    try:
        conn = get_db_connection(db_path)
        
        # Drop existing table
        conn.execute("DROP TABLE IF EXISTS species_list")
        
        # Create new table with count_high, count_low, score
        conn.execute("""
            CREATE TABLE species_list (
                scientific_name TEXT PRIMARY KEY,
                local_name TEXT,
                name_cs TEXT,
                count_high INTEGER,
                count_low INTEGER,
                score REAL
            )
        """)
        
        # Populate from detections with counts and score
        # Note: SQLite doesn't have POWER() function, so we use (confidence * confidence * confidence * confidence)
        conn.execute(f"""
            INSERT INTO species_list (scientific_name, local_name, name_cs, count_high, count_low, score)
            SELECT 
                scientific_name, 
                local_name, 
                name_cs,
                SUM(CASE WHEN confidence >= {CONFIDENCE_THRESHOLD_HIGH} THEN 1 ELSE 0 END) as count_high,
                SUM(CASE WHEN confidence < {CONFIDENCE_THRESHOLD_HIGH} THEN 1 ELSE 0 END) as count_low,
                SUM(confidence * confidence * confidence * confidence) as score
            FROM detections
            GROUP BY scientific_name, local_name, name_cs
            ORDER BY score DESC
        """)
        
        conn.commit()
        
        # Get count for logging
        cursor = conn.execute("SELECT COUNT(*) FROM species_list")
        count = cursor.fetchone()[0]
        
        conn.close()
        
        logger.info(f"Created species_list table with {count} unique species")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create species_list table: {e}")
        return False    
    

def get_species_count(db_path: Path) -> int:
    """
    Get number of species in species_list table.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Number of species, or 0 if table doesn't exist
    """
    if not species_list_exists(db_path):
        return 0
    
    try:
        conn = get_db_connection(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM species_list")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Failed to get species count: {e}")
        return 0


def get_available_species(db_path: Path) -> List[Tuple[str, str]]:
    """
    Get list of all available species from species_list table.
    Falls back to detections table if species_list doesn't exist.
    
    Returns:
        List of tuples: [(scientific_name, local_name), ...]
        Sorted alphabetically by scientific name
    """
    try:
        conn = get_db_connection(db_path)
        
        # Try species_list first
        if species_list_exists(db_path):
            query = """
                SELECT scientific_name, local_name
                FROM species_list
                ORDER BY scientific_name ASC
            """
        else:
            # Fallback to detections (slower)
            logger.warning("species_list table not found, falling back to detections table")
            query = """
                SELECT DISTINCT scientific_name, local_name
                FROM detections
                ORDER BY scientific_name ASC
            """
        
        cursor = conn.execute(query)
        results = [(row[0], row[1] or row[0]) for row in cursor.fetchall()]
        conn.close()
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to get available species: {e}")
        return []


def get_species_list_with_counts(db_path: Path) -> List[Dict]:
    """
    Get complete species list with detection counts and score.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        List of dicts with keys:
        - scientific_name
        - local_name
        - name_cs
        - count_high (detections >= threshold)
        - count_low (detections < threshold)
        - score (sum of confidence^4)
        
        Returns empty list if species_list table doesn't exist.
    """
    if not species_list_exists(db_path):
        logger.warning("species_list table does not exist")
        return []
    
    try:
        conn = get_db_connection(db_path)
        
        query = """
            SELECT 
                scientific_name,
                local_name,
                name_cs,
                count_high,
                count_low,
                score
            FROM species_list
            ORDER BY score DESC
        """
        
        cursor = conn.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to get species list with counts: {e}")
        return []
    

def get_detection_by_id(db_path: Path, detection_id: int) -> Optional[Dict]:
    """
    Load single detection with all metadata.
    
    Args:
        db_path: Path to SQLite database
        detection_id: Detection ID
        
    Returns:
        Dict with detection + metadata or None if not found
    """
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute("""
            SELECT 
                d.id as detection_id,
                d.filename,
                d.segment_start_utc,
                d.segment_end_utc,
                d.segment_start_local,
                d.segment_end_local,
                d.timezone,
                d.scientific_name,
                d.local_name,
                d.name_cs,
                d.confidence,
                m.timestamp_utc as file_timestamp_utc,
                m.timestamp_local as file_timestamp_local,
                m.duration_seconds as file_duration_seconds,
                m.gps_lat,
                m.gps_lon,
                m.sample_rate,
                m.channels
            FROM detections d
            JOIN metadata m ON d.filename = m.filename
            WHERE d.id = ?
        """, (detection_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
        
    finally:
        conn.close()


def get_metadata_by_filename(db_path: Path, filename: str) -> Optional[Dict]:
    """
    Load file metadata.
    
    Args:
        db_path: Path to SQLite database
        filename: WAV filename
        
    Returns:
        Dict with metadata or None if not found
    """
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute("""
            SELECT * FROM metadata WHERE filename = ?
        """, (filename,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
        
    finally:
        conn.close()


def query_detections(
    db_path: Path,
    species: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    time_range: Optional[Tuple[time, time]] = None,
    min_confidence: Optional[float] = None,
    limit: int = 25,
    offset: int = 0,
    sort_by: str = "time",
    sort_order: str = "asc"
) -> List[Dict]:
    """
    Query detections with filters and sorting.
    
    Args:
        db_path: Path to SQLite database
        species: Species name (scientific, local, or Czech) - partial match
        date_from: Start date (inclusive)
        date_to: End date (inclusive)
        time_range: Tuple of (start_time, end_time) for time of day filter
        min_confidence: Minimum confidence threshold
        limit: Maximum number of results (default: 25)
        offset: Result offset for pagination
        sort_by: Sort field - "time", "confidence", or "id" (default: "time")
        sort_order: Sort order - "asc" or "desc" (default: "asc")
        
    Returns:
        List of detection dicts with metadata
    """
    conn = get_db_connection(db_path)
    
    try:
        # Build query
        query = """
            SELECT 
                d.id as detection_id,
                d.filename,
                d.segment_start_utc,
                d.segment_end_utc,
                d.segment_start_local,
                d.segment_end_local,
                d.timezone,
                d.scientific_name,
                d.local_name,
                d.name_cs,
                d.confidence,
                m.timestamp_utc as file_timestamp_utc,
                m.timestamp_local as file_timestamp_local,
                m.duration_seconds as file_duration_seconds,
                m.gps_lat,
                m.gps_lon,
                m.sample_rate,
                m.channels
            FROM detections d
            JOIN metadata m ON d.filename = m.filename
            WHERE 1=1
        """
        
        params = []
        
        # Species filter (match scientific OR local OR Czech name)
        if species:
            query += " AND (d.scientific_name LIKE ? OR d.local_name LIKE ? OR d.name_cs LIKE ?)"
            pattern = f"%{species}%"
            params.extend([pattern, pattern, pattern])
        
        # Date filters
        if date_from:
            query += " AND date(d.segment_start_local) >= date(?)"
            params.append(date_from.isoformat())
        
        if date_to:
            query += " AND date(d.segment_start_local) <= date(?)"
            params.append(date_to.isoformat())
        
        # Time of day filter
        if time_range:
            start_time, end_time = time_range
            query += " AND time(d.segment_start_local) BETWEEN time(?) AND time(?)"
            params.append(start_time.isoformat())
            params.append(end_time.isoformat())
        
        # Confidence filter
        if min_confidence is not None:
            query += " AND d.confidence >= ?"
            params.append(min_confidence)
        
        # Sorting - Map sort_by to actual column names
        sort_column_map = {
            "time": "d.segment_start_local",
            "confidence": "d.confidence",
            "id": "d.id"
        }
        
        sort_column = sort_column_map.get(sort_by, "d.segment_start_local")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"
        
        query += f" ORDER BY {sort_column} {sort_direction}"
        
        # Limit and offset
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        # Execute query
        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        logger.debug(
            f"Query returned {len(results)} detections "
            f"(sort={sort_by} {sort_order})"
        )
        return results
        
    finally:
        conn.close()
        
        

def format_score_with_two_significant_digits(score: float, min_score: float) -> str:
    """
    Format score with adaptive precision.
    
    Rules:
    - score >= 10: No decimals (e.g., "123")
    - 10 > score >= 1: 1 decimal (e.g., "9.9")
    - score < 1: 2 significant digits (e.g., "0.000075")
    
    Args:
        score: Score value to format
        min_score: Minimum score (not used in this version)
        
    Returns:
        Formatted string
    """
    import math
    
    if score == 0:
        return "0"
    
    if score >= 10:
        # No decimals
        return f"{score:.0f}"
    
    elif score >= 1:
        # 1 decimal place
        return f"{score:.1f}"
    
    else:
        # score < 1: Show 2 significant digits
        # Calculate how many decimals needed
        magnitude = math.floor(math.log10(abs(score)))
        decimals = -(magnitude - 1)
        return f"{score:.{decimals}f}"


def format_detections_column(
    count_high: int, 
    count_low: int, 
    score: float, 
    min_score: float
) -> str:
    """
    Format detections column for display.
    
    Args:
        count_high: Number of detections >= threshold
        count_low: Number of detections < threshold
        score: Score value
        min_score: Minimum score of all species (for precision)
        
    Returns:
        Formatted string: "123 (45) {score: 67.8}" or "123 (45) {score: 0.0012}"
    """
    score_str = format_score_with_two_significant_digits(score, min_score)
    return f"{count_high} ({count_low}) {{score: {score_str}}}"


def get_recording_date_range(db_path: Path) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Get the date range of recordings in the database.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Tuple of (min_date, max_date) as datetime objects
        Returns (None, None) if no recordings found
    """
    try:
        conn = get_db_connection(db_path)
        
        query = """
            SELECT 
                MIN(timestamp_local) as min_date,
                MAX(timestamp_local) as max_date
            FROM metadata
        """
        
        cursor = conn.execute(query)
        row = cursor.fetchone()
        conn.close()
        
        if row and row['min_date'] and row['max_date']:
            min_date = datetime.fromisoformat(row['min_date'])
            max_date = datetime.fromisoformat(row['max_date'])
            return (min_date, max_date)
        else:
            return (None, None)
            
    except Exception as e:
        logger.error(f"Failed to get recording date range: {e}")
        return (None, None)


def search_species_in_list(db_path: Path, search_term: str, limit: int = 10) -> List[str]:
    """
    Search species in species_list table with auto-complete.
    
    Args:
        db_path: Path to SQLite database
        search_term: Search term (partial match)
        limit: Maximum number of results
        
    Returns:
        List of formatted species strings: "Scientific Name (Local Name)"
        Returns empty list if no matches or table doesn't exist
    """
    if not search_term or not species_list_exists(db_path):
        return []
    
    try:
        conn = get_db_connection(db_path)
        
        # Search in scientific, local, and Czech names
        query = """
            SELECT scientific_name, local_name, name_cs
            FROM species_list
            WHERE scientific_name LIKE ? 
               OR local_name LIKE ? 
               OR name_cs LIKE ?
            ORDER BY score DESC
            LIMIT ?
        """
        
        pattern = f"%{search_term}%"
        cursor = conn.execute(query, (pattern, pattern, pattern, limit))
        
        results = []
        for row in cursor.fetchall():
            scientific = row['scientific_name']
            local = row['local_name'] or ''
            
            # Format: "Scientific Name (Local Name)"
            if local:
                results.append(f"{scientific} ({local})")
            else:
                results.append(scientific)
        
        conn.close()
        return results
        
    except Exception as e:
        logger.error(f"Failed to search species: {e}")
        return []
    
    
    
