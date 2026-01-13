"""
Progress display for batch processing.
"""

import time
from datetime import timedelta
from loguru import logger


class ProgressDisplay:
    """Display progress information during batch processing."""
    
    def __init__(self, total_segments: int, num_workers: int):
        """
        Initialize progress display.
        
        Args:
            total_segments: Total number of segments to process
            num_workers: Number of worker processes
        """
        self.total_segments = total_segments
        self.num_workers = num_workers
        self.completed_segments = 0
        self.current_file = ""
        self.start_time = time.time()
        self.active_workers = set()
        
        logger.info(f"Starting processing: {total_segments} segments with {num_workers} workers")
    
    def update(self, completed_segments: int, current_file: str, worker_id: str = None):
        """
        Update display.
        
        Args:
            completed_segments: Number of completed segments
            current_file: Currently processing file
            worker_id: ID of worker that sent update (optional)
        """
        self.completed_segments = completed_segments
        self.current_file = current_file
        
        if worker_id:
            self.active_workers.add(worker_id)
        
        # Calculate statistics
        elapsed = time.time() - self.start_time
        progress = (completed_segments / self.total_segments * 100) if self.total_segments > 0 else 0
        
        # Calculate segments per second
        segments_per_sec = completed_segments / elapsed if elapsed > 0 else 0
        
        # Estimate remaining time
        if segments_per_sec > 0:
            remaining_segments = self.total_segments - completed_segments
            eta_seconds = remaining_segments / segments_per_sec
            eta = str(timedelta(seconds=int(eta_seconds)))
        else:
            eta = "calculating..."
        
        # Print progress
        print("\r" + "=" * 80)
        print("BirdNET Batch Analyzer - Progress")
        print("=" * 80)
        print(f"Workers:           {len(self.active_workers)} / {self.num_workers} active")
        print(f"Segments:          {completed_segments} / {self.total_segments} ({progress:.1f}%)")
        print(f"Current File:      {current_file}")
        print(f"Segments/sec:      {segments_per_sec:.2f}")
        print(f"ETA:               {eta}")
        print("=" * 80, end="")
        
    def finish(self, total_detections: int = None):
        """
        Display final statistics.
        
        Args:
            total_detections: Total number of detections (optional)
        """
        elapsed = time.time() - self.start_time
        
        print("\n" + "=" * 80)
        print("Processing Complete!")
        print("=" * 80)
        print(f"Total segments:    {self.completed_segments}")
        print(f"Total time:        {str(timedelta(seconds=int(elapsed)))}")
        print(f"Average speed:     {self.completed_segments / elapsed:.2f} segments/sec")
        if total_detections is not None:
            print(f"Total detections:  {total_detections}")
        print("=" * 80)
        
        logger.info(f"Processing finished: {self.completed_segments} segments in {elapsed:.1f}s")
