"""
Temporary aggregation database process for birdnet-copter.

Runs as a permanent background process (multiprocessing, spawn).
Receives add/remove/reload_labels/shutdown operations via temp_db_queue
and processes them sequentially.

Supported operations (dicts on the queue):
    {'op': 'add',            'db_path': str}
    {'op': 'remove',         'db_path': str}
    {'op': 'reload_labels',  'language_code': str, 'labels': dict}
    {'op': 'shutdown'}

Entry point: run_temp_db_process()
"""

import sqlite3
from datetime import datetime, timezone
from multiprocessing import Queue
from pathlib import Path

from loguru import logger

from .task_status import set_task_running, TASK_TEMP_DB

# Confidence threshold for high/low split in species_list (mirrors db_queries.py)
_CONFIDENCE_THRESHOLD_HIGH = 0.7


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_temp_db_process(
    temp_db_path: str,
    queue: Queue,
    shared_state: dict,
) -> None:
    """
    Temp-DB background process entry point.

    Runs an infinite loop waiting for operation dicts on *queue*.
    Exits cleanly when {'op': 'shutdown'} is received.

    Args:
        temp_db_path: Absolute path to the already-created temp DB file.
        queue:        temp_db_queue from QueueBundle.
        shared_state: multiprocessing Manager().dict() shared with main process.
    """
    logger.info(f"TempDbProcess started (db={temp_db_path})")
    set_task_running(shared_state, TASK_TEMP_DB, False, '')

    while True:
        msg: dict = queue.get(block=True)
        op = msg.get('op')

        if op == 'shutdown':
            logger.info("TempDbProcess: shutdown received, exiting")
            break

        if op == 'add':
            _handle_add(temp_db_path, msg['db_path'], shared_state, queue)

        elif op == 'remove':
            _handle_remove(temp_db_path, msg['db_path'], shared_state, queue)

        elif op == 'reload_labels':
            _handle_reload_labels(temp_db_path, msg['labels'], shared_state)

        else:
            logger.warning(f"TempDbProcess: unknown op {op!r}, skipping")

    set_task_running(shared_state, TASK_TEMP_DB, False, '')
    logger.info("TempDbProcess finished")


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------

def _handle_add(temp_db_path: str, src_db_path: str, shared_state: dict, queue=None) -> None:
    """
    Add a source database to the temp_db.

    Steps:
      1. Insert entry into source_dbs, retrieve source_db_id.
      2. Read min_confidence from source DB's analysis_config.
      3. Copy all rows from source metadata table.
      4. Copy all rows from source detections table.
      5. Rebuild species_list.
    """
    display_name = Path(src_db_path).parent.name
    set_task_running(shared_state, TASK_TEMP_DB, True, f'Loading {display_name}…')
    logger.info(f"TempDbProcess: adding {src_db_path}")

    try:
        src_conn  = sqlite3.connect(src_db_path)
        src_conn.row_factory = sqlite3.Row
        temp_conn = sqlite3.connect(temp_db_path)
        temp_conn.execute("PRAGMA journal_mode=WAL")
        temp_conn.execute("PRAGMA synchronous=OFF")
        temp_conn.execute("PRAGMA cache_size=-64000")
        
        try:
            # 1. Register source DB
            added_at = datetime.now(timezone.utc).isoformat()
            cur = temp_conn.execute(
                """
                INSERT INTO source_dbs (db_path, display_name, added_at)
                VALUES (?, ?, ?)
                """,
                (src_db_path, display_name, added_at),
            )
            source_db_id = cur.lastrowid

            # 2. Read min_confidence from source analysis_config
            min_conf = _read_min_confidence(src_conn)
            temp_conn.execute(
                "UPDATE source_dbs SET min_confidence = ? WHERE id = ?",
                (min_conf, source_db_id),
            )

            # Close src_conn before ATTACH to avoid lock conflict
            src_conn.close()
            src_conn = None

            # 3+4. Copy via ATTACH
            temp_conn.execute("ATTACH DATABASE ? AS src", (src_db_path,))
            temp_conn.execute(f"""
                INSERT OR IGNORE INTO metadata
                    (filename, source_db_id, timestamp_utc, timestamp_local,
                     timezone, serial, gps_lat, gps_lon, sample_rate, channels,
                     bit_depth, duration_seconds, temperature_c, battery_voltage,
                     gain, firmware)
                SELECT filename, {source_db_id},
                       timestamp_utc, timestamp_local, timezone, serial,
                       gps_lat, gps_lon, sample_rate, channels, bit_depth,
                       duration_seconds, temperature_c, battery_voltage,
                       gain, firmware
                FROM src.metadata
            """)
            meta_count = temp_conn.execute("SELECT changes()").fetchone()[0]
            logger.debug(f"TempDbProcess: copied {meta_count} metadata rows")

            # Drop indices before bulk insert
            temp_conn.execute("DROP INDEX IF EXISTS idx_detections_species")
            temp_conn.execute("DROP INDEX IF EXISTS idx_detections_segment_start")
            temp_conn.execute("DROP INDEX IF EXISTS idx_detections_source")

            temp_conn.execute(f"""
                INSERT INTO detections
                    (filename, source_db_id, segment_start_utc, segment_start_local,
                     segment_end_utc, segment_end_local, timezone,
                     scientific_name, confidence)
                SELECT filename, {source_db_id},
                       segment_start_utc, segment_start_local,
                       segment_end_utc, segment_end_local, timezone,
                       scientific_name, confidence
                FROM src.detections
            """)
            det_count = temp_conn.execute("SELECT changes()").fetchone()[0]
            logger.debug(f"TempDbProcess: copied {det_count} detection rows")
            temp_conn.commit()
            temp_conn.execute("DETACH DATABASE src")

            # Recreate indices and rebuild species_list only if queue is empty
            if queue is None or queue.empty():
                temp_conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_species ON detections(scientific_name)")
                temp_conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_segment_start ON detections(segment_start_local)")
                temp_conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_source ON detections(source_db_id)")
                temp_conn.commit()
                _rebuild_species_list(temp_conn)
                temp_conn.commit()
                
            logger.info(
                f"TempDbProcess: added {display_name} "
                f"({meta_count} files, {det_count} detections)"
            )

        finally:
            if src_conn is not None:
                src_conn.close()
            temp_conn.close()

    except Exception as e:
        logger.error(f"TempDbProcess: add failed for {src_db_path}: {e}")

    set_task_running(shared_state, TASK_TEMP_DB, False, '')


def _handle_remove(temp_db_path: str, src_db_path: str, shared_state: dict, queue=None) -> None:
    """
    Remove a source database from the temp_db.

    Steps:
      1. Look up source_db_id by db_path.
      2. Delete all detections with that source_db_id.
      3. Delete all metadata rows with that source_db_id.
      4. Delete the source_dbs entry.
      5. Rebuild species_list.
    """
    display_name = Path(src_db_path).parent.name
    set_task_running(shared_state, TASK_TEMP_DB, True, f'Removing {display_name}…')
    logger.info(f"TempDbProcess: removing {src_db_path}")

    try:
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-64000")

        try:
            row = conn.execute(
                "SELECT id FROM source_dbs WHERE db_path = ?",
                (src_db_path,),
            ).fetchone()

            if row is None:
                logger.warning(
                    f"TempDbProcess: remove – db_path not found in source_dbs: {src_db_path}"
                )
                return

            source_db_id = row[0]

            conn.execute(
                "DELETE FROM detections WHERE source_db_id = ?", (source_db_id,)
            )
            conn.execute(
                "DELETE FROM metadata WHERE source_db_id = ?", (source_db_id,)
            )
            conn.execute(
                "DELETE FROM source_dbs WHERE id = ?", (source_db_id,)
            )
            conn.commit()

            if queue is None or queue.empty():
                _rebuild_species_list(conn)
                conn.commit()

            logger.info(f"TempDbProcess: removed {display_name}")

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"TempDbProcess: remove failed for {src_db_path}: {e}")

    set_task_running(shared_state, TASK_TEMP_DB, False, '')


def _handle_reload_labels(
    temp_db_path: str,
    labels: dict,
    shared_state: dict,
) -> None:
    """
    Replace the local_names table with a new labels dict.

    Steps:
      1. DELETE all rows from local_names.
      2. INSERT all entries from the new labels dict.
      No species_list rebuild needed (local names are not stored there).
    """
    set_task_running(shared_state, TASK_TEMP_DB, True, 'Reloading bird names…')
    logger.info(f"TempDbProcess: reloading labels ({len(labels)} entries)")

    try:
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.execute("DELETE FROM local_names")
            conn.executemany(
                "INSERT INTO local_names (scientific_name, local_name) VALUES (?, ?)",
                labels.items(),
            )
            conn.commit()
            logger.info("TempDbProcess: local_names reloaded")
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"TempDbProcess: reload_labels failed: {e}")

    set_task_running(shared_state, TASK_TEMP_DB, False, '')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_min_confidence(src_conn: sqlite3.Connection) -> float | None:
    """
    Read min_confidence from analysis_config of a source DB connection.

    Returns:
        Float value or None if not set.
    """
    try:
        row = src_conn.execute(
            "SELECT value FROM analysis_config WHERE key = 'min_confidence'"
        ).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


def _rebuild_species_list(conn: sqlite3.Connection) -> None:
    """
    Rebuild the species_list table in the temp_db from current detections.

    Drops and recreates the table; aggregates count_high, count_low and
    score across all source DBs.

    Args:
        conn: Open connection to the temp_db (caller must commit afterwards).
    """
    conn.execute("DELETE FROM species_list")
    conn.execute(
        f"""
        INSERT INTO species_list (scientific_name, count_high, count_low, score)
        SELECT
            scientific_name,
            SUM(CASE WHEN confidence >= {_CONFIDENCE_THRESHOLD_HIGH} THEN 1 ELSE 0 END),
            SUM(CASE WHEN confidence <  {_CONFIDENCE_THRESHOLD_HIGH} THEN 1 ELSE 0 END),
            SUM(confidence * confidence * confidence * confidence)
        FROM detections
        GROUP BY scientific_name
        ORDER BY SUM(confidence * confidence * confidence * confidence) DESC
        """
    )
    cur = conn.execute("SELECT COUNT(*) FROM species_list")
    count = cur.fetchone()[0]
    logger.debug(f"TempDbProcess: species_list rebuilt ({count} species)")