"""
Filter logic and context for detection queries.
"""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, Tuple, Dict


@dataclass
class DetectionFilter:
    """
    Container for detection filter parameters.
    """
    # Detection selection
    detection_id: Optional[int] = None
    
    # Species filter
    species: Optional[str] = None
    
    # Date filters
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    
    # Time of day filter
    time_start: Optional[time] = None
    time_end: Optional[time] = None
    
    # Confidence filter
    min_confidence: Optional[float] = None
    
    # Pagination
    limit: int = 25  # Changed default from 50 to 25
    offset: int = 0
    
    # Sort options
    sort_by: str = "time"  # "time", "confidence", or "id"
    sort_order: str = "asc"  # "asc" or "desc"
    
    # Options
    pm_seconds: float = 1.0  # Will be "Audio Frame Duration" in UI (0.5-6.0)
    use_sci: bool = False
    
    def has_species_filter(self) -> bool:
        """Check if species filter is active."""
        return self.species is not None
    
    def has_time_filter(self) -> bool:
        """Check if any time-related filter is active."""
        return (
            self.date_from is not None or
            self.date_to is not None or
            self.time_start is not None or
            self.time_end is not None
        )
    
    def has_detection_id_filter(self) -> bool:
        """Check if detection ID is explicitly given."""
        return self.detection_id is not None
    
    def get_filter_context(self) -> Dict:
        """
        Generate filter context dict for TTS text generation.
        
        Returns:
            Dict with keys:
            - 'detection_id_given': bool
            - 'species_filter': bool
            - 'time_filter': bool
        """
        return {
            'detection_id_given': self.has_detection_id_filter(),
            'species_filter': self.has_species_filter(),
            'time_filter': self.has_time_filter()
        }
    
    def to_query_params(self) -> Dict:
        """
        Convert filter to query_detections() parameters.
        
        Returns:
            Dict with query parameters
        """
        # Build time range tuple if both times are set
        time_range = None
        if self.time_start is not None and self.time_end is not None:
            time_range = (self.time_start, self.time_end)
        
        return {
            'species': self.species,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'time_range': time_range,
            'min_confidence': self.min_confidence,
            'limit': self.limit,
            'offset': self.offset,
            'sort_by': self.sort_by,
            'sort_order': self.sort_order
        }
    
    def validate(self) -> Optional[str]:
        """
        Validate filter parameters using datetime combination.
        
        Returns:
            Error message if invalid, None if valid
        """
        # DateTime validation (combines date + time)
        if self.date_from and self.date_to:
            # Combine date + time to datetime objects
            time_start = self.time_start if self.time_start else time(0, 0, 0)
            time_end = self.time_end if self.time_end else time(23, 59, 59)
            
            # date_from/date_to are already datetime objects, extract date part
            datetime_start = datetime.combine(self.date_from.date(), time_start)
            datetime_end = datetime.combine(self.date_to.date(), time_end)
            
            if datetime_end <= datetime_start:
                return "End date/time must be after start date/time"
        
        # Confidence validation
        if self.min_confidence is not None:
            if not (0.0 <= self.min_confidence <= 1.0):
                return "min_confidence must be between 0.0 and 1.0"
        
        # Limit validation
        if self.limit < 1:
            return "limit must be >= 1"
        
        # Offset validation
        if self.offset < 0:
            return "offset must be >= 0"
        
        # PM validation (Audio Frame Duration range: 0.5-6.0)
        if self.pm_seconds < 0.5 or self.pm_seconds > 6.0:
            return "Audio Frame Duration must be between 0.5 and 6.0 seconds"
        
        # Sort validation
        if self.sort_by not in ["time", "confidence", "id"]:
            return "sort_by must be 'time', 'confidence', or 'id'"
        
        if self.sort_order not in ["asc", "desc"]:
            return "sort_order must be 'asc' or 'desc'"
        
        return None
    
    def __str__(self) -> str:
        """String representation for logging."""
        parts = []
        
        if self.detection_id:
            parts.append(f"id={self.detection_id}")
        
        if self.species:
            parts.append(f"species={self.species}")
        
        if self.date_from:
            parts.append(f"date_from={self.date_from.date()}")
        
        if self.date_to:
            parts.append(f"date_to={self.date_to.date()}")
        
        if self.time_start and self.time_end:
            parts.append(f"time={self.time_start}-{self.time_end}")
        
        if self.min_confidence is not None:
            parts.append(f"confidence>={self.min_confidence}")
        
        parts.append(f"limit={self.limit}")
        
        if self.offset > 0:
            parts.append(f"offset={self.offset}")
        
        parts.append(f"frame_duration={self.pm_seconds}s")
        parts.append(f"sort={self.sort_by}_{self.sort_order}")
        
        if self.use_sci:
            parts.append("use_sci=True")
        
        return f"DetectionFilter({', '.join(parts)})"


def parse_time_range(time_str: str) -> Tuple[time, time]:
    """
    Parse time range string to (start_time, end_time) tuple.
    
    Args:
        time_str: Time range in format "HH:MM-HH:MM" or "HH:MM:SS-HH:MM:SS"
        
    Returns:
        Tuple of (start_time, end_time)
        
    Raises:
        ValueError: If format is invalid
        
    Examples:
        >>> parse_time_range("06:00-10:00")
        (time(6, 0), time(10, 0))
        
        >>> parse_time_range("06:30:15-10:45:30")
        (time(6, 30, 15), time(10, 45, 30))
    """
    if '-' not in time_str:
        raise ValueError("Time range must contain '-' separator")
    
    start_str, end_str = time_str.split('-', 1)
    
    # Parse start time
    start_parts = start_str.strip().split(':')
    if len(start_parts) == 2:
        start_time = time(int(start_parts[0]), int(start_parts[1]))
    elif len(start_parts) == 3:
        start_time = time(int(start_parts[0]), int(start_parts[1]), int(start_parts[2]))
    else:
        raise ValueError(f"Invalid start time format: {start_str}")
    
    # Parse end time
    end_parts = end_str.strip().split(':')
    if len(end_parts) == 2:
        end_time = time(int(end_parts[0]), int(end_parts[1]))
    elif len(end_parts) == 3:
        end_time = time(int(end_parts[0]), int(end_parts[1]), int(end_parts[2]))
    else:
        raise ValueError(f"Invalid end time format: {end_str}")
    
    return start_time, end_time


def parse_date(date_str: str) -> datetime:
    """
    Parse date string to datetime.
    
    Args:
        date_str: Date in ISO format "YYYY-MM-DD"
        
    Returns:
        datetime object (time set to 00:00:00)
        
    Raises:
        ValueError: If format is invalid
        
    Examples:
        >>> parse_date("2025-04-16")
        datetime.datetime(2025, 4, 16, 0, 0)
    """
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        # Try to parse as date only
        parts = date_str.split('-')
        if len(parts) != 3:
            raise ValueError(f"Invalid date format: {date_str}")
        
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        
        return datetime(year, month, day)
    