"""
Application state for BirdNET Play NiceGUI server.
Single server-side state object shared across all pages and client connections.
"""

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .hardware import HardwareInfo


@dataclass
class AppState:
    """
    Central server-side application state.

    One instance exists for the lifetime of the server process.
    All GUI pages read from and write to this single object.
    No multi-client isolation: a second browser sees the same state.
    """

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------
    root_path: Path
    read_only: bool = False
    available_dbs: List[Path] = field(default_factory=list)
    active_db: Optional[Path] = None
    # Bird name language (fully implemented)
    bird_language_code: str = 'de'
    # GUI language (prepared, not yet active)
    gui_language_code: str = 'de'
    
    # ------------------------------------------------------------------
    # Hardware & inference configuration  (filled by hardware.py / Hangar)
    # ------------------------------------------------------------------
    hw_info: Optional['HardwareInfo'] = None

    use_gpu: bool = True
    use_embeddings: bool = False
    global_index_path: Optional[Path] = None
    
    # ------------------------------------------------------------------
    # GPU Watchdog
    # ------------------------------------------------------------------
    birdnet_active: bool = False          # dokumentiert nur; Wert kommt aus shared_state
    gpu_error: Optional[dict] = None      # {'message': str, 'kill_cmd': str} wenn Crash

    # ------------------------------------------------------------------
    # Walker / job queue state  (read-only view for GUI)
    # ------------------------------------------------------------------
    jobs: List[Dict] = field(default_factory=list)
    walker_status: str = 'idle'   # 'idle'|'running'|'wait_pending'|'waiting'

    # ------------------------------------------------------------------
    # Global DB
    # ------------------------------------------------------------------
    active_db_is_global: bool = False
    
    # Shared state for inter-process communication (Manager().dict())
    shared_state: Optional[Any] = None

    # ------------------------------------------------------------------
    # Audio Player filter state  (prefix: ap_)
    # ------------------------------------------------------------------
    ap_filter_species: Optional[str] = None
    ap_filter_date_from: Optional[date] = None
    ap_filter_date_to: Optional[date] = None
    ap_filter_use_time: bool = False
    ap_filter_time_start: time = field(default_factory=lambda: time(0, 0, 0))
    ap_filter_time_end: time = field(default_factory=lambda: time(23, 59, 59))
    ap_filter_confidence: Optional[float] = 0.70
    ap_filter_limit: int = 25
    ap_filter_offset: int = 0
    ap_filter_sort: str = 'time'       # 'time' | 'confidence' | 'id'
    ap_filters_applied: bool = False

    # ------------------------------------------------------------------
    # Audio options
    # ------------------------------------------------------------------
    audio_say_number: bool = False
    audio_bird_name: str = 'none'      # 'none' | 'local' | 'scientific'
    audio_say_id: bool = False
    audio_say_confidence: bool = False
    audio_speech_speed: float = 1.0
    audio_speech_loudness: int = -2
    audio_frame_duration: float = 1.0
    audio_noise_reduction: bool = True
    audio_noise_reduce_strength: float = 0.8

    # ------------------------------------------------------------------
    # Audio player runtime state
    # ------------------------------------------------------------------
    detections: List[Dict] = field(default_factory=list)
    # det_id (str) -> base64-encoded MP3
    audio_cache: Dict[str, str] = field(default_factory=dict)
    audio_generation_progress: float = 0.0   # 0.0 – 1.0
    audio_generation_running: bool = False

    # ------------------------------------------------------------------
    # Heatmap filter state  (prefix: hm_)
    # ------------------------------------------------------------------
    hm_filter_species: Optional[str] = None
    hm_filter_date_from: Optional[date] = None
    hm_filter_date_to: Optional[date] = None
    hm_filter_confidence: Optional[float] = 0.70
    hm_filters_applied: bool = False

    # ------------------------------------------------------------------
    # Heatmap options and runtime state
    # ------------------------------------------------------------------
    hm_colormap: str = 'turbo'
    hm_weight_confidence: bool = True
    hm_aggregated_data: Optional[Any] = None   # holds a dict or DataFrame

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def reset_filter_state(self) -> None:
        """
        Reset all filter and runtime state after a database switch.
        Audio options and heatmap display options are preserved.
        """
        # Audio Player filter
        self.ap_filter_species = None
        self.ap_filter_date_from = None
        self.ap_filter_date_to = None
        self.ap_filter_use_time = False
        self.ap_filter_time_start = time(0, 0, 0)
        self.ap_filter_time_end = time(23, 59, 59)
        self.ap_filter_confidence = 0.70
        self.ap_filter_limit = 25
        self.ap_filter_offset = 0
        self.ap_filter_sort = 'time'
        self.ap_filters_applied = False

        # Audio player runtime
        self.detections = []
        self.audio_cache = {}
        self.audio_generation_progress = 0.0
        self.audio_generation_running = False

        # Heatmap filter
        self.hm_filter_species = None
        self.hm_filter_date_from = None
        self.hm_filter_date_to = None
        self.hm_filter_confidence = 0.70
        self.hm_filters_applied = False
        self.hm_aggregated_data = None

    def get_audio_options(self) -> Dict:
        """
        Return current audio options as a dict suitable for player.py calls.
        Matches the audio_options dict shape expected by prepare_detection_audio_web().
        """
        return {
            'say_audio_number': self.audio_say_number,
            'say_id': self.audio_say_id,
            'say_confidence': self.audio_say_confidence,
            'bird_name_option': self.audio_bird_name,
            'speech_speed': self.audio_speech_speed,
            'speech_loudness': self.audio_speech_loudness,
            'noise_reduce_strength': (
                self.audio_noise_reduce_strength
                if self.audio_noise_reduction else None
            ),
        }

    def invalidate_audio_cache(self) -> None:
        """Clear generated audio and reset progress. Call after filter or option changes."""
        self.audio_cache = {}
        self.audio_generation_progress = 0.0
        self.audio_generation_running = False

        