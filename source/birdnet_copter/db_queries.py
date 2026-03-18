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

        conn.execute("DROP TABLE IF EXISTS species_list")

        conn.execute("""
            CREATE TABLE species_list (
                scientific_name TEXT PRIMARY KEY,
                count_high INTEGER,
                count_low INTEGER,
                score REAL
            )
        """)

        conn.execute(f"""
            INSERT INTO species_list (scientific_name, count_high, count_low, score)
            SELECT
                scientific_name,
                SUM(CASE WHEN confidence >= {CONFIDENCE_THRESHOLD_HIGH} THEN 1 ELSE 0 END),
                SUM(CASE WHEN confidence < {CONFIDENCE_THRESHOLD_HIGH} THEN 1 ELSE 0 END),
                SUM(confidence * confidence * confidence * confidence) AS score
            FROM detections
            GROUP BY scientific_name
            ORDER BY score DESC
        """)

        conn.commit()

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


def get_available_species(db_path: Path) -> List[str]:
    """
    Get list of all available species from species_list table.
    Falls back to detections table if species_list doesn't exist.

    Returns:
        List of scientific_name strings, sorted alphabetically.
        Translation to local names is done by the caller via labels dict.
    """
    try:
        conn = get_db_connection(db_path)

        if species_list_exists(db_path):
            query = """
                SELECT scientific_name
                FROM species_list
                ORDER BY scientific_name ASC
            """
        else:
            query = """
                SELECT DISTINCT scientific_name
                FROM detections
                ORDER BY scientific_name ASC
            """

        cursor = conn.execute(query)
        results = [row[0] for row in cursor.fetchall()]
        conn.close()
        return results

    except Exception as e:
        logger.error(f"Failed to get available species: {e}")
        return []


def get_species_list_with_counts(
    db_path: Path,
    labels: Optional[dict] = None,
) -> List[Dict]:
    """
    Get complete species list with detection counts and score.

    Args:
        db_path: Path to SQLite database
        labels:  Optional dict {scientific_name: local_name} from bird_language.
                 When provided, each result dict gets a 'local_name' key.
                 When None, 'local_name' is absent from the result dicts.

    Returns:
        List of dicts with keys:
          - scientific_name
          - count_high  (detections >= threshold)
          - count_low   (detections < threshold)
          - score       (sum of confidence^4)
          - local_name  (only present when labels is not None)

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
                count_high,
                count_low,
                score
            FROM species_list
            ORDER BY score DESC
        """
        cursor = conn.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if labels is not None:
            for r in results:
                r['local_name'] = labels.get(r['scientific_name'], r['scientific_name'])

        return results

    except Exception as e:
        logger.error(f"Failed to get species list with counts: {e}")
        return []
    
def get_detection_by_id(
    db_path: Path,
    detection_id: int,
    labels: Optional[dict] = None,
) -> Optional[Dict]:
    """
    Load single detection with all metadata.

    Args:
        db_path:      Path to SQLite database
        detection_id: Detection ID
        labels:       Optional dict {scientific_name: local_name}.
                      When provided, result gets a 'local_name' key.

    Returns:
        Dict with detection + metadata, or None if not found.
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
        if row is None:
            return None
        result = dict(row)
        if labels is not None:
            result['local_name'] = labels.get(result['scientific_name'],
                                               result['scientific_name'])
        return result
    finally:
        conn.close()


def get_metadata_by_filename(db_path: Path, filename: str) -> Optional[Dict]:
    """
    Load file metadata.

    Args:
        db_path:  Path to SQLite database
        filename: WAV filename

    Returns:
        Dict with metadata or None if not found
    """
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM metadata WHERE filename = ?", (filename,)
        )
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
    sort_order: str = "asc",
    labels: Optional[dict] = None,
) -> List[Dict]:
    """
    Query detections with filters and sorting.

    Args:
        db_path:        Path to SQLite database
        species:        Scientific name filter (partial match)
        date_from:      Start date (inclusive)
        date_to:        End date (inclusive)
        time_range:     Tuple of (start_time, end_time) for time-of-day filter
        min_confidence: Minimum confidence threshold
        limit:          Maximum number of results (default: 25)
        offset:         Result offset for pagination
        sort_by:        Sort field – "time", "confidence", or "id"
        sort_order:     Sort order – "asc" or "desc"
        labels:         Optional dict {scientific_name: local_name}.
                        When provided, each result dict gets a 'local_name' key.

    Returns:
        List of detection dicts with metadata.
    """
    conn = get_db_connection(db_path)
    try:
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

        if species:
            query += " AND d.scientific_name LIKE ?"
            params.append(f"%{species}%")

        if date_from:
            start_time = time_range[0] if time_range else time(0, 0, 0)
            datetime_start = datetime.combine(
                date_from.date() if isinstance(date_from, datetime) else date_from,
                start_time,
            )
            query += " AND d.segment_start_local >= ?"
            params.append(datetime_start.isoformat())

        if date_to:
            end_time = time_range[1] if time_range else time(23, 59, 59)
            datetime_end = datetime.combine(
                date_to.date() if isinstance(date_to, datetime) else date_to,
                end_time,
            )
            query += " AND d.segment_start_local <= ?"
            params.append(datetime_end.isoformat())

        if min_confidence is not None:
            query += " AND d.confidence >= ?"
            params.append(min_confidence)

        sort_column_map = {
            "time":       "d.segment_start_local",
            "confidence": "d.confidence",
            "id":         "d.id",
        }
        sort_column    = sort_column_map.get(sort_by, "d.segment_start_local")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"
        query += f" ORDER BY {sort_column} {sort_direction}"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]

        if labels is not None:
            for r in results:
                r['local_name'] = labels.get(r['scientific_name'], r['scientific_name'])

        logger.debug(f"Query returned {len(results)} detections (sort={sort_by} {sort_order})")
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
    """
    import math

    if score == 0:
        return "0"
    if score >= 10:
        return f"{score:.0f}"
    elif score >= 1:
        return f"{score:.1f}"
    else:
        magnitude = math.floor(math.log10(abs(score)))
        decimals  = -(magnitude - 1)
        return f"{score:.{decimals}f}"


def format_detections_column(
    count_high: int,
    count_low: int,
    score: float,
    min_score: float,
) -> str:
    """
    Format detections column for display.

    Returns:
        Formatted string: "123 (45) {score: 67.8}"
    """
    score_str = format_score_with_two_significant_digits(score, min_score)
    return f"{count_high} ({count_low}) {{score: {score_str}}}"


def get_recording_date_range(
    db_path: Path,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Get the date range of recordings in the database.

    Returns:
        Tuple of (min_date, max_date) as datetime objects.
        Returns (None, None) if no recordings found.
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
        row    = cursor.fetchone()
        conn.close()

        if row and row['min_date'] and row['max_date']:
            return (
                datetime.fromisoformat(row['min_date']),
                datetime.fromisoformat(row['max_date']),
            )
        return (None, None)

    except Exception as e:
        logger.error(f"Failed to get recording date range: {e}")
        return (None, None)


def search_species_in_list(
    db_path: Path,
    search_term: str,
    limit: int = 10,
    labels: Optional[dict] = None,
) -> List[str]:
    """
    Search species with auto-complete.

    Searches scientific_name in the DB. When labels are provided, also
    searches local names (Python-side) and includes them in the display string.

    Args:
        db_path:     Path to SQLite database
        search_term: Partial match string
        limit:       Maximum number of results
        labels:      Optional dict {scientific_name: local_name}.
                     When provided, search also matches local names and the
                     display format becomes "Scientific Name (Local Name)".

    Returns:
        List of display strings. Internal value (scientific name) can be
        extracted by splitting on ' (' when labels are present.
        Returns empty list if no matches or table doesn't exist.
    """
    if not search_term or not species_list_exists(db_path):
        return []

    term_lower = search_term.lower()

    try:
        conn = get_db_connection(db_path)

        if labels is not None:
            # Fetch more candidates so local-name matches aren't cut off
            # before the Python-side filter runs
            fetch_limit = limit * 10
        else:
            fetch_limit = limit

        query = """
            SELECT scientific_name
            FROM species_list
            WHERE scientific_name LIKE ?
            ORDER BY score DESC
            LIMIT ?
        """
        cursor = conn.execute(query, (f"%{search_term}%", fetch_limit))
        sci_matches = [row['scientific_name'] for row in cursor.fetchall()]
        conn.close()

        if labels is None:
            return sci_matches[:limit]

        # With labels: merge scientific matches with local-name matches
        # and format as "Scientific Name (Local Name)"
        seen: set[str] = set(sci_matches)
        results: List[str] = []

        # Build display strings for scientific matches first
        for sci in sci_matches:
            local = labels.get(sci, '')
            results.append(f"{sci} ({local})" if local else sci)

        # Add local-name matches not already captured by scientific search
        for sci, local in labels.items():
            if sci in seen:
                continue
            if term_lower in local.lower():
                seen.add(sci)
                results.append(f"{sci} ({local})")

        return results[:limit]

    except Exception as e:
        logger.error(f"Failed to search species: {e}")
        return []


def get_db_completeness(db_path: Path) -> tuple[int, int]:
    """
    Return (completed_count, total_wav_count) for a folder's database.

    completed_count: files with status 'completed' in processing_status
    total_wav_count: files in metadata table (= all WAVs ever seen by scout)

    Returns:
        Tuple (completed, total). Returns (0, 0) if DB not readable.
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM processing_status")
        completed = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM metadata")
        total = cursor.fetchone()[0]
        conn.close()
        return (completed, total)
    except Exception as e:
        logger.error(f"get_db_completeness failed for {db_path}: {e}")
        return (0, 0)


def get_db_min_confidence(db_path: Path) -> Optional[float]:
    """
    Read min_confidence from analysis_config table.

    Returns:
        Float value or None if not set yet.
    """
    val = get_analysis_config(db_path, 'min_confidence')
    try:
        return float(val) if val is not None else None
    except ValueError:
        return None
    
    