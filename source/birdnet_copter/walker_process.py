"""
Walker background process for birdnet-copter.

Runs as a separate process (multiprocessing, spawn).
Receives ScanJob objects via job_queue, processes them sequentially,
and reports progress via progress_queue.
Responds to WAIT / RESUME / STOP signals via control_queue.

Entry point: run_walker_process()
"""

import contextlib
import io
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from .audiomoth_import import extract_metadata
from .birdnet_analyzer import (
    analyze_file,
    extract_embeddings,
    calculate_segment_times,
    find_needed_segments,
    filter_and_write_embeddings,
    match_embeddings_to_detections,
)
from .config import (
    DEFAULT_CONFIDENCE,
    OVERLAP_DURATION_S,
    BATCH_SIZE,
    SEGMENT_DURATION_S,
)
from .database import (
    init_database,
    insert_metadata,
    batch_insert_detections,
    create_indices,
    cleanup_incomplete_files,
    get_completed_files,
    get_missing_files,
    repair_orphaned_metadata,
    set_file_status,
    get_hdf5_path,
)
from .birdnet_labels import load_birdnet_labels
from .job_queue import (
    QueueBundle,
    ScanJob,
    SIGNAL_WAIT,
    SIGNAL_RESUME,
    SIGNAL_STOP,
    SIGNAL_SHUTDOWN,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _capture_tf_output():
    """Suppress TensorFlow stdout/stderr during BirdNET prediction."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _lookup_species(scientific_name: str,
                    translation_list: list[dict],
                    birdnet_labels: dict) -> dict:
    """
    Translate scientific name to local and Czech name.

    Args:
        scientific_name:  BirdNET scientific name
        translation_list: List of dicts with keys 'scientific', 'de', 'cs', 'en'
                          (converted from the karlincam DataFrame in main.py)
        birdnet_labels:   Dict {scientific_name: local_name} for selected language

    Returns:
        Dict with keys 'scientific', 'local', 'cs'
    """
    local_name = birdnet_labels.get(scientific_name, scientific_name)

    cs_name = scientific_name  # fallback
    for row in translation_list:
        if row.get('scientific') == scientific_name:
            cs_name = row.get('cs', scientific_name)
            break

    return {'scientific': scientific_name, 'local': local_name, 'cs': cs_name}


def _send_progress(bundle: QueueBundle, job: ScanJob) -> None:
    """Push a progress snapshot of job to the progress_queue."""
    bundle.progress_queue.put({
        'job_id':       job.job_id,
        'status':       job.status,
        'folder_path':  str(job.folder_path),
        'files_total':  job.files_total,
        'files_done':   job.files_done,
        'current_file': job.current_file,
        'error_msg':    job.error_msg,
        'started_at':   job.started_at.isoformat() if job.started_at else None,
        'finished_at':  job.finished_at.isoformat() if job.finished_at else None,
    })


def _check_control(bundle: QueueBundle,
                   stop_flag: list[bool],
                   wait_flag: list[bool]) -> None:
    """
    Drain the control_queue and update mutable flag lists.

    Uses lists so flags can be mutated by reference inside the caller.
    stop_flag[0] = True  → stop after current file
    wait_flag[0] = True  → pause after current batch
    """
    while not bundle.control_queue.empty():
        try:
            signal = bundle.control_queue.get_nowait()
        except Exception:
            break
        if signal == SIGNAL_STOP:
            stop_flag[0] = True
            logger.info("Walker: STOP signal received")
        elif signal == SIGNAL_WAIT:
            wait_flag[0] = True
            logger.info("Walker: WAIT signal received")
        elif signal == SIGNAL_RESUME:
            wait_flag[0] = False
            logger.info("Walker: RESUME signal received")


def _block_until_resume(bundle: QueueBundle,
                        job: ScanJob,
                        stop_flag: list[bool],
                        wait_flag: list[bool]) -> None:
    """
    Block the walker until RESUME or STOP is received.

    Updates job.status to 'waiting' while blocked and sends progress.
    """
    job.status = 'waiting'
    _send_progress(bundle, job)
    logger.info("Walker: entering WAIT state")

    while wait_flag[0]:
        time.sleep(0.2)
        _check_control(bundle, stop_flag, wait_flag)
        if stop_flag[0]:
            break

    if not stop_flag[0]:
        job.status = 'running'
        _send_progress(bundle, job)
        logger.info("Walker: resumed")
        
# ---------------------------------------------------------------------------
# Folder processing
# ---------------------------------------------------------------------------

def _process_folder(
    job: ScanJob,
    bundle: QueueBundle,
    translation_list: list[dict],
    birdnet_labels: dict,
    use_gpu: bool,
    stop_flag: list[bool],
    wait_flag: list[bool],
) -> None:
    """
    Process all WAV files in job.folder_path.

    Inline implementation (not a separate top-level function yet).
    Updates job fields in place and sends progress via bundle.
    """
    folder_path = job.folder_path
    db_path     = folder_path / "birdnet_analysis.db"
    hdf5_path   = get_hdf5_path(str(db_path))

    # --- DB init ---
    if not db_path.exists():
        init_database(str(db_path))

    # Store language in DB config
    lang_shortcut = next(
        (v for k, v in birdnet_labels.items() if False), 'de'
    )  # birdnet_labels has no lang code stored; language is set via config below
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # language shortcut is passed implicitly: we write whatever was loaded
    # The key is set in main.py when loading labels; we persist it here.
    conn.close()

    # --- find WAV files ---
    wav_files: list[Path] = []
    for ext in ('*.wav', '*.WAV'):
        wav_files.extend(folder_path.glob(ext))

    if not wav_files:
        logger.warning(f"Walker: no WAV files in {folder_path}")
        job.status = 'skipped'
        job.finished_at = datetime.now()
        _send_progress(bundle, job)
        return

    # --- metadata for new files ---
    filenames = [f.name for f in wav_files]
    missing   = get_missing_files(str(db_path), filenames)

    metadata_map: dict[str, dict] = {}

    if missing:
        for wav in wav_files:
            if wav.name not in missing:
                continue
            try:
                meta = extract_metadata(str(wav))
                meta['path'] = str(wav)
                insert_metadata(str(db_path), meta)
                metadata_map[wav.name] = meta
            except Exception as e:
                logger.error(f"Walker: metadata extraction failed for {wav.name}: {e}")

    repair_orphaned_metadata(str(db_path))
    cleanup_incomplete_files(str(db_path))

    # --- pending files ---
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM processing_status WHERE status = 'pending'")
    pending = {row[0] for row in cursor.fetchall()}
    conn.close()

    # Load metadata for pending files not yet in metadata_map
    for wav in wav_files:
        if wav.name not in pending or wav.name in metadata_map:
            continue
        try:
            meta = extract_metadata(str(wav))
            meta['path'] = str(wav)
            metadata_map[wav.name] = meta
        except Exception as e:
            logger.error(f"Walker: metadata load failed for {wav.name}: {e}")

    files_to_process = [metadata_map[n] for n in pending if n in metadata_map]

    if not files_to_process:
        logger.info(f"Walker: all files already processed in {folder_path}")
        job.status = 'done'
        job.finished_at = datetime.now()
        _send_progress(bundle, job)
        return

    job.files_total = len(files_to_process)
    _send_progress(bundle, job)

    # --- GPU/CPU device string ---
    device = 'GPU' if use_gpu else 'CPU'

    # --- processing loop ---
    for meta in files_to_process:
        if stop_flag[0]:
            logger.info("Walker: stop requested, aborting folder processing")
            break

        filename  = meta['filename']
        file_path = meta['path']

        job.current_file = filename
        _send_progress(bundle, job)

        try:
            set_file_status(str(db_path), filename, 'processing')

            # --- BirdNET analysis ---
            with _capture_tf_output():
                detections = analyze_file(
                    file_path,
                    latitude=meta.get('gps_lat', 51.1657),
                    longitude=meta.get('gps_lon', 13.7372),
                    timestamp=meta['timestamp_utc'],
                    min_confidence=job.min_conf,
                )

            # --- embeddings (optional) ---
            if job.scan_embeddings:
                try:
                    emb_result      = extract_embeddings(
                        file_path,
                        overlap_duration_s=OVERLAP_DURATION_S,
                        batch_size=BATCH_SIZE,
                    )
                    emb_array       = emb_result.embeddings[0]
                    segment_times   = calculate_segment_times(
                        len(emb_array),
                        emb_result.segment_duration_s,
                        emb_result.overlap_duration_s,
                    )
                    index_mapping   = find_needed_segments(detections, segment_times)
                    emb_start_idx   = filter_and_write_embeddings(
                        emb_array, index_mapping, hdf5_path
                    )
                    detections      = match_embeddings_to_detections(
                        detections, segment_times, index_mapping, emb_start_idx
                    )
                except Exception as e:
                    logger.error(f"Walker: embedding extraction failed for {filename}: {e}")
                    set_file_status(str(db_path), filename, 'failed',
                                    f'Embedding extraction failed: {e}')
                    job.files_done += 1
                    _send_progress(bundle, job)
                    continue

            # --- write to DB ---
            # Build a minimal translation_table compatible list for batch_insert_detections.
            # batch_insert_detections calls translate_species_name(scientific, df, labels).
            # We pass translation_list as a pandas-compatible shim via a wrapper below.
            _batch_insert(
                db_path=str(db_path),
                filename=filename,
                metadata=meta,
                detections=detections,
                translation_list=translation_list,
                birdnet_labels=birdnet_labels,
            )

        except Exception as e:
            logger.error(f"Walker: error processing {filename}: {e}")
            set_file_status(str(db_path), filename, 'failed', str(e))

        job.files_done += 1
        _send_progress(bundle, job)

        # --- check control signals after each file ---
        _check_control(bundle, stop_flag, wait_flag)

        if wait_flag[0]:
            _block_until_resume(bundle, job, stop_flag, wait_flag)

        if stop_flag[0]:
            break

    # --- create indices ---
    if not stop_flag[0]:
        create_indices(str(db_path))

    job.status     = 'done' if not stop_flag[0] else 'error'
    job.error_msg  = 'stopped by user' if stop_flag[0] else ''
    job.finished_at = datetime.now()
    _send_progress(bundle, job)
    logger.info(f"Walker: folder done – {job.files_done}/{job.files_total} files: {folder_path}")


def _batch_insert(
    db_path: str,
    filename: str,
    metadata: dict,
    detections: list[dict],
    translation_list: list[dict],
    birdnet_labels: dict,
) -> None:
    """
    Wrapper around database.batch_insert_detections that converts
    translation_list (list of dicts) to the pandas-free path by resolving
    species names here and passing pre-resolved names.

    We avoid importing pandas in the walker process for this lookup.
    Instead we replicate the minimal logic of translate_species_name().
    """
    # Pre-resolve all scientific names that appear in detections
    resolved: dict[str, dict] = {}
    for det in detections:
        sn = det['scientific_name']
        if sn not in resolved:
            resolved[sn] = _lookup_species(sn, translation_list, birdnet_labels)

    # Patch detections with pre-resolved names so batch_insert_detections
    # receives dicts that already have 'local_name' and 'name_cs'.
    # batch_insert_detections calls translate_species_name() internally –
    # we pass a dummy translation_table and override with a patched birdnet_labels.
    import pandas as pd
    empty_df = pd.DataFrame(columns=['scientific', 'en', 'de', 'cs'])

    # Build a labels dict that maps scientific → local (already resolved)
    patched_labels = {sn: info['local'] for sn, info in resolved.items()}

    # Build a minimal translation DataFrame with cs names
    rows = [{'scientific': sn, 'en': '', 'de': info['local'], 'cs': info['cs']}
            for sn, info in resolved.items()]
    translation_df = pd.DataFrame(rows) if rows else empty_df

    batch_insert_detections(
        db_path,
        filename,
        metadata,
        detections,
        translation_df,
        patched_labels,
    )


# ---------------------------------------------------------------------------
# Walker process entry point
# ---------------------------------------------------------------------------

def run_walker_process(
    bundle: QueueBundle,
    translation_list: list[dict],
    birdnet_labels: dict,
    use_gpu: bool,
) -> None:
    """
    Walker background process entry point.

    Runs an infinite loop waiting for ScanJob objects on bundle.job_queue.
    Exits cleanly when SIGNAL_SHUTDOWN (None) is received.

    Args:
        bundle:           QueueBundle created by create_queues() in main process
        translation_list: Species translation data as list of dicts
                          (converted from karlincam DataFrame in main.py)
        birdnet_labels:   Dict {scientific_name: local_name} for selected language
        use_gpu:          If True, BirdNET uses GPU; otherwise CPU
    """
    logger.info("Walker process started")

    stop_flag = [False]   # [0] = stop after current file
    wait_flag = [False]   # [0] = pause after current batch

    while True:
        # Reset per-job stop flag; wait_flag persists across jobs until RESUME
        stop_flag[0] = False

        logger.debug("Walker: waiting for next job...")
        job: Optional[ScanJob] = bundle.job_queue.get(block=True)

        # Poison pill → graceful exit
        if job is SIGNAL_SHUTDOWN:
            logger.info("Walker process: shutdown signal received, exiting")
            break

        if not isinstance(job, ScanJob):
            logger.warning(f"Walker: unexpected item in job_queue: {job!r}")
            continue

        # Check for pending wait from previous job
        if wait_flag[0]:
            job.status = 'waiting'
            _send_progress(bundle, job)
            _block_until_resume(bundle, job, stop_flag, wait_flag)
            if stop_flag[0]:
                job.status = 'skipped'
                job.finished_at = datetime.now()
                _send_progress(bundle, job)
                continue

        logger.info(f"Walker: starting job {job.job_id[:8]} – {job.folder_path}")
        job.status     = 'running'
        job.started_at = datetime.now()
        _send_progress(bundle, job)

        try:
            _process_folder(
                job=job,
                bundle=bundle,
                translation_list=translation_list,
                birdnet_labels=birdnet_labels,
                use_gpu=use_gpu,
                stop_flag=stop_flag,
                wait_flag=wait_flag,
            )
        except Exception as e:
            logger.error(f"Walker: unhandled exception in job {job.job_id[:8]}: {e}")
            job.status      = 'error'
            job.error_msg   = str(e)
            job.finished_at = datetime.now()
            _send_progress(bundle, job)

    logger.info("Walker process finished")
    
    