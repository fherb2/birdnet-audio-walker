"""
Temporary aggregation database initialisation for birdnet-copter.

Creates a NamedTemporaryFile SQLite database, applies the temp_db schema,
and populates the local_names table from a labels dict.

The temp_db schema mirrors the source-DB tables (metadata, detections) with
an additional source_db_id column in each, plus three new tables:
  - source_dbs   : registry of currently loaded source databases
  - local_names  : bird name translations for the active language
  - species_list : aggregated species statistics (rebuilt on every add/remove)
"""

import sqlite3
import tempfile
from pathlib import Path

from loguru import logger


def create_temp_db(labels: dict[str, str]) -> Path:
    """
    Create a temporary SQLite database with the temp_db schema.

    Creates a NamedTemporaryFile (not auto-deleted), initialises all tables,
    and populates local_names from the supplied labels dict.

    Args:
        labels: Dict {scientific_name: local_name} for the active language.
                Obtained via bird_language.load_labels(language_code).

    Returns:
        Path to the newly created temp database file.
    """
    # Create temp file; delete=False so the DB persists until explicit cleanup
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    logger.info(f"Creating temp_db at: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _create_schema(conn)
        _populate_local_names(conn, labels)
        conn.commit()
    finally:
        conn.close()

    logger.info(f"temp_db initialised ({len(labels)} local names loaded)")
    return db_path


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _create_schema(conn: sqlite3.Connection) -> None:
    """Create all temp_db tables (empty)."""

    # Registry of currently loaded source databases
    conn.execute("""
        CREATE TABLE source_dbs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            db_path        TEXT    NOT NULL UNIQUE,
            display_name   TEXT    NOT NULL,
            min_confidence REAL,
            added_at       TEXT    NOT NULL
        )
    """)

    # Bird name translations for the active language
    conn.execute("""
        CREATE TABLE local_names (
            scientific_name TEXT PRIMARY KEY,
            local_name      TEXT NOT NULL
        )
    """)

    # Aggregated species statistics; rebuilt after every add/remove
    conn.execute("""
        CREATE TABLE species_list (
            scientific_name TEXT PRIMARY KEY,
            count_high      INTEGER,
            count_low       INTEGER,
            score           REAL
        )
    """)

    # Recording file metadata – mirrors source-DB schema + source_db_id.
    # No UNIQUE on filename alone: the same filename may exist in multiple
    # source DBs.  Uniqueness is enforced on (filename, source_db_id).
    conn.execute("""
        CREATE TABLE metadata (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            filename          TEXT NOT NULL,
            source_db_id      INTEGER NOT NULL REFERENCES source_dbs(id),
            timestamp_utc     TEXT NOT NULL,
            timestamp_local   TEXT NOT NULL,
            timezone          TEXT NOT NULL,
            serial            TEXT,
            gps_lat           REAL,
            gps_lon           REAL,
            sample_rate       INTEGER,
            channels          INTEGER,
            bit_depth         INTEGER,
            duration_seconds  REAL,
            temperature_c     REAL,
            battery_voltage   REAL,
            gain              TEXT,
            firmware          TEXT,
            UNIQUE (filename, source_db_id)
        )
    """)

    # Detections – mirrors source-DB schema + source_db_id.
    # JOIN to metadata must always include source_db_id.
    conn.execute("""
        CREATE TABLE detections (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            filename             TEXT NOT NULL,
            source_db_id         INTEGER NOT NULL REFERENCES source_dbs(id),
            segment_start_utc    TEXT NOT NULL,
            segment_start_local  TEXT NOT NULL,
            segment_end_utc      TEXT NOT NULL,
            segment_end_local    TEXT NOT NULL,
            timezone             TEXT NOT NULL,
            scientific_name      TEXT NOT NULL,
            confidence           REAL NOT NULL
        )
    """)

    # Indices for the most common query patterns
    conn.execute("""
        CREATE INDEX idx_detections_source
        ON detections(source_db_id)
    """)
    conn.execute("""
        CREATE INDEX idx_detections_species
        ON detections(scientific_name)
    """)
    conn.execute("""
        CREATE INDEX idx_detections_segment_start
        ON detections(segment_start_local)
    """)
    conn.execute("""
        CREATE INDEX idx_metadata_source
        ON metadata(source_db_id)
    """)

    logger.debug("temp_db schema created")


# ---------------------------------------------------------------------------
# local_names population
# ---------------------------------------------------------------------------

def _populate_local_names(conn: sqlite3.Connection, labels: dict[str, str]) -> None:
    """
    Insert all entries from labels into the local_names table.

    Args:
        conn:   Open connection to the temp_db.
        labels: Dict {scientific_name: local_name}.
    """
    conn.executemany(
        "INSERT INTO local_names (scientific_name, local_name) VALUES (?, ?)",
        labels.items(),
    )
    logger.debug(f"Inserted {len(labels)} rows into local_names")