"""
Job queue management for birdnet-copter walker process.

Provides:
- ScanJob dataclass
- Queue initialisation (call once in main process before spawning workers)
- Helper functions for adding jobs and draining the progress queue
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing import Queue
from pathlib import Path
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Control signal constants  (sent via control_queue)
# ---------------------------------------------------------------------------

SIGNAL_WAIT   = "WAIT"
SIGNAL_RESUME = "RESUME"
SIGNAL_STOP   = "STOP"

# Poison pill sent via job_queue to shut down the walker process
SIGNAL_SHUTDOWN = None


# ---------------------------------------------------------------------------
# ScanJob dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScanJob:
    """
    A single folder scan job.

    rescan_species=False (default): only WAV files not yet in the DB are analysed
                                    (Extend). min_conf is read from existing DB.
    rescan_species=True:            DB detections are cleared, all WAV files are
                                    re-analysed (Rebuild). min_conf from job settings.

    scan_embeddings=True:           embedding vectors are extracted / backfilled
                                    for every detection that has no embedding_idx yet.
    """
    folder_path: Path
    rescan_species: bool  = False
    scan_embeddings: bool = True
    min_conf: float       = 0.4

    # --- runtime fields (set by scout process) ---
    job_id:      str               = field(default_factory=lambda: str(uuid.uuid4()))
    status:      str               = 'pending'   # 'pending'|'flying'|'done'|'error'|'skipped'
    added_at:    datetime          = field(default_factory=datetime.now)
    started_at:  Optional[datetime] = None
    finished_at: Optional[datetime] = None

    files_total: int = 0
    files_done:  int = 0
    current_file: str = ''
    error_msg:    str = ''


# ---------------------------------------------------------------------------
# Queue bundle  (created once, passed to all processes)
# ---------------------------------------------------------------------------

@dataclass
class QueueBundle:
    """
    Holds all inter-process queues and the shared_state manager dict.

    Attributes:
        job_queue:      Main → Scout    ScanJob objects (or SIGNAL_SHUTDOWN)
        progress_queue: Scout → Main    progress dicts (see _progress_msg())
        control_queue:  Main → Scout    SIGNAL_WAIT / SIGNAL_RESUME / SIGNAL_STOP
        shared_state:   multiprocessing.Manager().dict()  readable by GUI
    """
    job_queue:      Queue
    progress_queue: Queue
    control_queue:  Queue
    shared_state:   dict   # Manager().dict() – passed in from main.py


def create_queues(shared_state: dict) -> QueueBundle:
    """
    Create all inter-process queues.

    Must be called in the main process *before* any worker is spawned
    (required for 'spawn' start method).

    Args:
        shared_state: A multiprocessing.Manager().dict() created by the caller.

    Returns:
        QueueBundle with all queues attached.
    """
    bundle = QueueBundle(
        job_queue=Queue(),
        progress_queue=Queue(),
        control_queue=Queue(),
        shared_state=shared_state,
    )
    logger.debug("Queue bundle created")
    return bundle


# ---------------------------------------------------------------------------
# Helper: build a progress message dict
# ---------------------------------------------------------------------------

def progress_msg(job: ScanJob) -> dict:
    """Build a serialisable progress snapshot from a ScanJob."""
    return {
        'job_id':         job.job_id,
        'status':         job.status,
        'folder_path':    str(job.folder_path),
        'files_total':    job.files_total,
        'files_done':     job.files_done,
        'current_file':   job.current_file,
        'error_msg':      job.error_msg,
        'started_at':     job.started_at.isoformat() if job.started_at else None,
        'finished_at':    job.finished_at.isoformat() if job.finished_at else None,
        'rescan_species': job.rescan_species,
        'min_conf':       job.min_conf,
    }


# ---------------------------------------------------------------------------
# Job management helpers
# ---------------------------------------------------------------------------

def add_job(bundle: QueueBundle, job: ScanJob) -> None:
    """
    Append a ScanJob to the job_queue and register it in shared_state.

    The job is added to shared_state['jobs'] (list of progress dicts)
    so the GUI can display it immediately before the walker picks it up.

    Args:
        bundle: QueueBundle from create_queues()
        job:    ScanJob to enqueue
    """
    # Register in shared_state so GUI sees it straight away
    jobs: list = list(bundle.shared_state.get('jobs', []))
    jobs.append(progress_msg(job))
    bundle.shared_state['jobs'] = jobs

    # Send to walker
    bundle.job_queue.put(job)
    logger.debug(f"Job enqueued: {job.folder_path} (id={job.job_id[:8]})")


def send_control(bundle: QueueBundle, signal: str) -> None:
    """
    Send a control signal to the walker process.

    Args:
        bundle: QueueBundle from create_queues()
        signal: One of SIGNAL_WAIT, SIGNAL_RESUME, SIGNAL_STOP
    """
    bundle.control_queue.put(signal)
    logger.debug(f"Control signal sent: {signal}")


def shutdown_scouting(bundle: QueueBundle) -> None:
    """
    Send the poison pill to the scout process to request a graceful exit.

    Args:
        bundle: QueueBundle from create_queues()
    """
    bundle.job_queue.put(SIGNAL_SHUTDOWN)
    logger.debug("Shutdown signal sent to scout process")


# ---------------------------------------------------------------------------
# Progress queue drain  (called from GUI timer, runs in main process)
# ---------------------------------------------------------------------------

def drain_progress_queue(bundle: QueueBundle) -> None:
    """
    Read all available messages from progress_queue and update shared_state.

    Designed to be called from a NiceGUI ui.timer callback (≈ 1 s interval).
    Non-blocking: returns immediately when the queue is empty.

    Progress messages update the matching entry in shared_state['jobs']
    (matched by job_id). scout_status in shared_state is also updated.

    Args:
        bundle: QueueBundle from create_queues()
    """
    updated = False

    while not bundle.progress_queue.empty():
        try:
            msg: dict = bundle.progress_queue.get_nowait()
        except Exception:
            break

        job_id = msg.get('job_id')

        # Update matching job in shared_state['jobs']
        jobs: list = list(bundle.shared_state.get('jobs', []))
        for i, entry in enumerate(jobs):
            if entry.get('job_id') == job_id:
                jobs[i] = {**entry, **msg}
                break
        bundle.shared_state['jobs'] = jobs

        # Update top-level walker_status
        status = msg.get('status')
        if status:
            if status == 'flying':
                bundle.shared_state['walker_status'] = 'flying'
            elif status in ('done', 'error', 'skipped'):
                any_active = any(
                    j.get('status') in ('pending', 'flying')
                    for j in jobs
                )
                bundle.shared_state['walker_status'] = 'flying' if any_active else 'idle'

        updated = True

    if updated:
        logger.debug("shared_state updated from progress_queue")
        
        