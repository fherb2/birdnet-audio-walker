"""
Progress display for batch processing.
"""

import time
from datetime import timedelta
from loguru import logger


class ProgressDisplay:
    """Display progress information during batch processing."""
    
    def __init__(self, total_files: int):
        """
        Initialize progress display.
        
        Args:
            total_files: Total number of files to process
        """
        self.total_files = total_files
        self.completed_files = 0
        self.current_file = ""
        self.start_time = time.time()
        
        logger.info(f"Starting processing: {total_files} files")
    
    def update(self, completed_files: int, current_file: str, elapsed: float = None):
        """
        Update display.
        
        Args:
            completed_files: Number of completed files
            current_file: Currently processing file
            elapsed: Elapsed time in seconds (optional)
        """
        self.completed_files = completed_files
        self.current_file = current_file
        
        # Calculate statistics
        if elapsed is None:
            elapsed = time.time() - self.start_time
        
        progress = (completed_files / self.total_files * 100) if self.total_files > 0 else 0
        
        # Calculate files per second
        files_per_sec = completed_files / elapsed if elapsed > 0 else 0
        
        # Estimate remaining time
        if files_per_sec > 0:
            remaining_files = self.total_files - completed_files
            eta_seconds = remaining_files / files_per_sec
            eta = str(timedelta(seconds=int(eta_seconds)))
        else:
            eta = "calculating..."
        
        # Print progress
        print("\r" + "=" * 80)
        print("BirdNET Batch Analyzer - Progress")
        print("=" * 80)
        print(f"Files:             {completed_files} / {self.total_files} ({progress:.1f}%)")
        print(f"Current File:      {current_file}")
        print(f"Files/sec:         {files_per_sec:.2f}")
        print(f"Elapsed:           {str(timedelta(seconds=int(elapsed)))}")
        print(f"ETA:               {eta}")
        print("=" * 80, end="")
        
    def finish(self, total_files: int, total_detections: int, elapsed: float):
        """
        Display final statistics.
        
        Args:
            total_files: Total number of files processed
            total_detections: Total number of detections
            elapsed: Total elapsed time in seconds
        """
        print("\n" + "=" * 80)
        print("Processing Complete!")
        print("=" * 80)
        print(f"Total files:       {total_files}")
        print(f"Total time:        {str(timedelta(seconds=int(elapsed)))}")
        print(f"Average speed:     {total_files / elapsed:.2f} files/sec")
        print(f"Total detections:  {total_detections}")
        print("=" * 80)
        
        logger.info(f"Processing finished: {total_files} files in {elapsed:.1f}s")