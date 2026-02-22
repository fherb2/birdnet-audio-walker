"""
Audio playback engine for BirdNET detections.
Combines audio snippets with TTS announcements.
"""

import numpy as np
from pathlib import Path
from typing import Dict, List
from io import BytesIO
from pydub import AudioSegment
from loguru import logger
from num2words import num2words

from shared.audio_extract import extract_snippet, calculate_snippet_offsets
from .tts import generate_tts

# Additional imports for audio processing
try:
    import pyloudnorm as pyln
    PYLOUDNORM_AVAILABLE = True
except ImportError:
    PYLOUDNORM_AVAILABLE = False
    logger.warning("pyloudnorm not installed, LUFS normalization will be disabled")

try:
    from pedalboard import Pedalboard, Compressor
    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False
    logger.warning("pedalboard not installed, audio compression will be disabled")


# Audio processing constants
TARGET_LUFS = -16.0  # Target loudness in LUFS (-23 = broadcast, -16 = streaming, -14 = loud)
FADE_DURATION_MS = 500  # Fade-in/out duration in milliseconds (0.5s)
COMPRESSOR_THRESHOLD_DB = -20.0  # Compressor threshold
COMPRESSOR_RATIO = 4.0 # 4.0  # Compression ratio (4:1)

class AudioPlayer:
    """Audio player for BirdNET detections."""
    
    def __init__(self, db_path: Path, pm_seconds: float = 1.0):
        """
        Initialize audio player.
        
        Args:
            db_path: Path to BirdNET analysis database
            pm_seconds: Plus/Minus buffer around detections (default: 1.0s)
        """
        self.db_path = db_path
        self.pm_seconds = pm_seconds
        self.db_dir = db_path.parent
        
        logger.debug(f"AudioPlayer initialized: db={db_path}, pm={pm_seconds}s")
    
    def prepare_detection_audio(
        self,
        detection: Dict,
        audio_number: int,
        language_code: str,
        filter_context: Dict,
        audio_options: Dict,
        disable_tts: bool = False
    ) -> BytesIO:
        """
        Create combined audio: Pause + Snippet + TTS announcement (as WAV).
        
        Args:
            detection: Detection dict from query_detections()
            audio_number: Sequential number in playlist (1, 2, 3, ...)
            language_code: Language code for TTS
            filter_context: Filter context dict
            audio_options: Audio options dict with:
                - say_audio_number: bool
                - say_id: bool
                - say_confidence: bool
                - bird_name_option: 'none', 'local', 'scientific'
                - speech_speed: float (0.5-2.0)
                - speech_loudness: int (-20 to +20 dB)
            disable_tts: Disable TTS announcements completely
            
        Returns:
            BytesIO with WAV data ready for playback or export
        """
        logger.debug(f"Preparing audio for detection #{detection['detection_id']}")
        
        # 1. Generate 1s pause (silence)
        pause = self._generate_silence(1.0, 48000)
        
        # 2. Extract audio snippet with PM buffer
        wav_path = self.db_dir / detection['filename']
        
        try:
            start_offset, end_offset = calculate_snippet_offsets(detection, self.pm_seconds)
            audio_data, sample_rate = extract_snippet(wav_path, start_offset, end_offset)
            
            # Process audio frame: fade-in/out, LUFS normalization, compression
            audio_data = self._process_audio_frame(audio_data, sample_rate)
            
        except Exception as e:
            logger.error(f"Failed to extract/process snippet for detection #{detection['detection_id']}: {e}")
            raise
        
        # 3. Generate TTS announcement (only if not disabled)
        if not disable_tts:
            tts_text = self._get_announcement_text(detection, audio_number, filter_context, audio_options)
            
            try:
                # Determine voice language:
                # - Scientific name -> always German
                # - Local name -> language_code
                bird_name_option = audio_options.get('bird_name_option', 'local')
                if bird_name_option == 'scientific':
                    tts_lang = 'de'
                else:
                    tts_lang = language_code
                
                tts_audio = generate_tts(
                    tts_text,
                    tts_lang,
                    speed=audio_options.get('speech_speed', 1.0),
                    loudness_db=audio_options.get('speech_loudness', 0)
                )
            except Exception as e:
                logger.warning(f"TTS generation failed, using silence: {e}")
                tts_audio = self._generate_silence(1.0, 48000)
        else:
            # TTS disabled - short pause instead
            tts_audio = self._generate_silence(0.5, 48000)
        
        # 4. Combine: Pause + Audio + TTS
        # All segments need same sample rate
        audio_resampled = self._resample_if_needed(audio_data, sample_rate, 48000)
        
        combined = self._combine_audio_segments(
            [pause, audio_resampled, tts_audio],
            48000
        )
        
        # 5. Convert to WAV in BytesIO
        wav_bytes = self._to_wav_bytes(combined, 48000)
        
        logger.debug(
            f"Audio prepared: detection #{detection['detection_id']}, "
            f"total duration ~{len(combined)/48000:.1f}s"
        )
        
        return wav_bytes


    def _process_audio_frame(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> np.ndarray:
        """
        Process audio frame with fade-in/out, LUFS normalization, and compression.
        
        Processing pipeline:
        1. Fade-in (0.5s) and Fade-out (0.5s)
        2. LUFS normalization to target loudness
        3. Compressor to prevent clipping
        
        Args:
            audio_data: Audio samples (int16, mono or stereo)
            sample_rate: Sample rate in Hz
            
        Returns:
            Processed audio samples (int16, mono)
        """
        # Convert to pydub AudioSegment for fade processing
        audio_segment = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=audio_data.dtype.itemsize,
            channels=1 if audio_data.ndim == 1 else audio_data.shape[1]
        )
        
        # 1. Apply fade-in and fade-out
        audio_segment = audio_segment.fade_in(FADE_DURATION_MS).fade_out(FADE_DURATION_MS)
        logger.debug(f"Applied fade-in/out: {FADE_DURATION_MS}ms")
        
        # Convert to numpy for further processing
        samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
        
        # Convert to mono if stereo
        if audio_segment.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1)
        
        # Normalize to [-1.0, 1.0] range for processing
        samples = samples / 32768.0
        
        # 2. LUFS normalization (if available)
        if PYLOUDNORM_AVAILABLE:
            try:
                # Measure current loudness
                meter = pyln.Meter(sample_rate)
                current_loudness = meter.integrated_loudness(samples)
                
                # Normalize to target LUFS
                samples = pyln.normalize.loudness(samples, current_loudness, TARGET_LUFS)
                
                logger.debug(f"LUFS normalization: {current_loudness:.1f} → {TARGET_LUFS:.1f} LUFS")
                
            except Exception as e:
                logger.warning(f"LUFS normalization failed: {e}")
        else:
            logger.debug("LUFS normalization skipped (pyloudnorm not available)")
        
        # 3. Apply compressor to prevent clipping (if available)
        if PEDALBOARD_AVAILABLE:
            try:
                # Create compressor effect
                compressor = Compressor(
                    threshold_db=COMPRESSOR_THRESHOLD_DB,
                    ratio=COMPRESSOR_RATIO
                )
                
                # Apply compressor
                board = Pedalboard([compressor])
                samples = board(samples, sample_rate)
                
                logger.debug(f"Compressor applied: threshold={COMPRESSOR_THRESHOLD_DB}dB, ratio={COMPRESSOR_RATIO}:1")
                
            except Exception as e:
                logger.warning(f"Compression failed: {e}")
        else:
            logger.debug("Compression skipped (pedalboard not available)")
        
        # Clip to safe range and convert back to int16
        samples = np.clip(samples, -1.0, 1.0)
        samples = (samples * 32767.0).astype(np.int16)
        
        return samples

    
    def _get_announcement_text(
            self,
            detection: Dict,
            audio_number: int,
            filter_context: Dict,
            audio_options: Dict
        ) -> str:
            """
            Generate TTS announcement text based on audio options.
            
            Rules based on audio_options:
            - say_audio_number: Include "Audio N"
            - say_id: Include "ID 12345"
            - audio_bird_name: 'none', 'local', or 'scientific'
            - say_confidence: Include "XX Prozent"
            
            Args:
                detection: Detection dict
                audio_number: Sequential number in playlist (1, 2, 3, ...)
                filter_context: Filter context dict
                audio_options: Audio options dict with:
                    - say_audio_number: bool
                    - say_id: bool
                    - say_confidence: bool
                    - bird_name_option: 'none', 'local', 'scientific'
                
            Returns:
                Text for TTS announcement
            """
            parts = []
            
            # Audio Number
            if audio_options.get('say_audio_number', True):
                parts.append(f"Audio {audio_number}")
            
            # Database ID
            if audio_options.get('say_id', True):
                detection_id = detection['detection_id']
                parts.append(f"ID {detection_id}")
            
            # Bird Name
            bird_name_option = audio_options.get('bird_name_option', 'local')
            if bird_name_option == 'scientific':
                name = detection['scientific_name']
                parts.append(name)
            elif bird_name_option == 'local':
                name = detection.get('local_name') or detection['scientific_name']
                parts.append(name)
            # 'none' -> no name
            
            # Confidence
            if audio_options.get('say_confidence', True):
                confidence = detection['confidence']
                conf_percent = int(round(confidence * 100))
                conf_percent_words = num2words(conf_percent, lang='de')
                parts.append(f"{conf_percent_words} Prozent")
            
            # Combine parts
            return " ".join(parts) if parts else "Audio"

    def _generate_silence(self, duration_seconds: float, sample_rate: int) -> np.ndarray:
        """
        Generate silence as numpy array.
        
        Args:
            duration_seconds: Duration in seconds
            sample_rate: Sample rate in Hz
            
        Returns:
            Numpy array with zeros (int16, mono)
        """
        n_samples = int(duration_seconds * sample_rate)
        return np.zeros(n_samples, dtype=np.int16)
    
    def _resample_if_needed(
        self,
        audio_data: np.ndarray,
        source_rate: int,
        target_rate: int
    ) -> np.ndarray:
        """
        Resample audio if sample rates differ.
        
        Args:
            audio_data: Audio samples
            source_rate: Source sample rate
            target_rate: Target sample rate
            
        Returns:
            Resampled audio data (or original if rates match)
        """
        if source_rate == target_rate:
            return audio_data
        
        logger.debug(f"Resampling audio: {source_rate}Hz → {target_rate}Hz")
        
        # Convert to pydub AudioSegment for resampling
        audio_segment = AudioSegment(
            audio_data.tobytes(),
            frame_rate=source_rate,
            sample_width=audio_data.dtype.itemsize,
            channels=1 if audio_data.ndim == 1 else audio_data.shape[1]
        )
        
        # Resample
        resampled = audio_segment.set_frame_rate(target_rate)
        
        # Convert back to numpy
        samples = np.array(resampled.get_array_of_samples(), dtype=np.int16)
        
        return samples
    
    def _combine_audio_segments(
        self,
        segments: List[np.ndarray],
        sample_rate: int
    ) -> np.ndarray:
        """
        Concatenate multiple audio segments.
        
        Args:
            segments: List of audio numpy arrays (all same sample rate)
            sample_rate: Sample rate (for validation)
            
        Returns:
            Combined audio array
        """
        # Ensure all segments are mono int16
        mono_segments = []
        for seg in segments:
            if seg.ndim > 1:
                # Convert stereo to mono by averaging channels
                seg = seg.mean(axis=1).astype(np.int16)
            mono_segments.append(seg)
        
        # Concatenate
        combined = np.concatenate(mono_segments)
        
        logger.debug(f"Combined {len(segments)} segments → {len(combined)} samples")
        
        return combined
    
    def _to_wav_bytes(self, audio_data: np.ndarray, sample_rate: int) -> BytesIO:
        """
        Convert numpy array to WAV in BytesIO.
        
        Args:
            audio_data: Audio samples (int16, mono)
            sample_rate: Sample rate in Hz
            
        Returns:
            BytesIO with WAV data
        """
        # Convert to pydub AudioSegment
        audio_segment = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=audio_data.dtype.itemsize,
            channels=1
        )
        
        # Export to WAV in memory
        buf = BytesIO()
        audio_segment.export(buf, format='wav')
        buf.seek(0)
        
        return buf
    
    def _to_mp3_bytes(self, audio_data: np.ndarray, sample_rate: int) -> BytesIO:
        """
        Convert numpy array to MP3 in BytesIO (for web streaming).
        
        Args:
            audio_data: Audio samples (int16, mono)
            sample_rate: Sample rate in Hz
            
        Returns:
            BytesIO with MP3 data
        """
        # Convert to pydub AudioSegment
        audio_segment = AudioSegment(
            audio_data.tobytes(),
            frame_rate=sample_rate,
            sample_width=audio_data.dtype.itemsize,
            channels=1
        )
        
        # Export to MP3 in memory (128kbps quality)
        buf = BytesIO()
        audio_segment.export(buf, format='mp3', bitrate='128k')
        buf.seek(0)
        
        return buf
    
    def prepare_detection_audio_web(
        self,
        detection: Dict,
        audio_number: int,
        language_code: str,
        filter_context: Dict,
        audio_options: Dict,
        disable_tts: bool = False
    ) -> BytesIO:
        """
        Create combined audio as MP3 (for web streaming).
        
        Args:
            detection: Detection dict from query_detections()
            audio_number: Sequential number in playlist (1, 2, 3, ...)
            language_code: Language code for TTS
            filter_context: Filter context dict
            audio_options: Audio options dict with:
                - say_audio_number: bool
                - say_id: bool
                - say_confidence: bool
                - bird_name_option: 'none', 'local', 'scientific'
                - speech_speed: float (0.5-2.0)
                - speech_loudness: int (-20 to +20 dB)
            disable_tts: Disable TTS announcements completely
            
        Returns:
            BytesIO with MP3 data
        """
        logger.debug(f"Preparing MP3 audio for detection #{detection['detection_id']}")
        
        # 1. Generate 1s pause (silence)
        pause = self._generate_silence(1.0, 48000)
        
        # 2. Extract audio snippet with PM buffer
        wav_path = self.db_dir / detection['filename']
        
        try:
            start_offset, end_offset = calculate_snippet_offsets(detection, self.pm_seconds)
            audio_data, sample_rate = extract_snippet(wav_path, start_offset, end_offset)
            
            # Process audio frame: fade-in/out, LUFS normalization, compression
            audio_data = self._process_audio_frame(audio_data, sample_rate)
            
        except Exception as e:
            logger.error(f"Failed to extract/process snippet for detection #{detection['detection_id']}: {e}")
            raise
        
        # 3. Generate TTS announcement (only if not disabled)
        if not disable_tts:
            tts_text = self._get_announcement_text(detection, audio_number, filter_context, audio_options)
            
            try:
                # Determine voice language:
                # - Scientific name -> always German
                # - Local name -> language_code
                bird_name_option = audio_options.get('bird_name_option', 'local')
                if bird_name_option == 'scientific':
                    tts_lang = 'de'
                else:
                    tts_lang = language_code
                
                tts_audio = generate_tts(
                    tts_text, 
                    tts_lang,
                    speed=audio_options.get('speech_speed', 1.0),
                    loudness_db=audio_options.get('speech_loudness', 0)
                )
            except Exception as e:
                logger.warning(f"TTS generation failed, using silence: {e}")
                tts_audio = self._generate_silence(1.0, 48000)
        else:
            # TTS disabled - short pause instead
            tts_audio = self._generate_silence(0.5, 48000)
        
        # 4. Combine: Pause + Audio + TTS
        audio_resampled = self._resample_if_needed(audio_data, sample_rate, 48000)
        
        combined = self._combine_audio_segments(
            [pause, audio_resampled, tts_audio],
            48000
        )
        
        # 5. Convert to MP3
        mp3_bytes = self._to_mp3_bytes(combined, 48000)
        
        logger.debug(
            f"MP3 prepared: detection #{detection['detection_id']}, "
            f"size ~{len(mp3_bytes.getvalue())/1024:.1f}KB"
        )
        
        return mp3_bytes
    


    def prepare_detection_audio_simple(
        self,
        detection: Dict,
        pm_seconds: float = 0.5
    ) -> BytesIO:
        """
        Prepare simple audio for heatmap dialog - no TTS, just fade.
        
        Combines:
        - 0.5s initial pause
        - PM buffer before detection
        - 3s detection audio
        - PM buffer after detection
        
        Args:
            detection: Detection dict with metadata
            pm_seconds: Plus/minus seconds around detection (default: 0.5)
            
        Returns:
            BytesIO containing MP3 audio data
        """
        from pydub import AudioSegment
        import numpy as np
        
        # Calculate offsets
        start_offset, end_offset = calculate_snippet_offsets(detection, pm_seconds)
        
        # Get WAV path
        wav_path = self.db_path.parent / detection['filename']
        
        if not wav_path.exists():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")
        
        # Extract audio snippet (returns tuple: audio_data, sample_rate)
        audio_samples, sample_rate = extract_snippet(wav_path, start_offset, end_offset)
        
        # Process audio (fade + LUFS + compressor)
        # Returns int16 array
        processed_samples = self._process_audio_frame(audio_samples, sample_rate)
        
        # Convert to pydub AudioSegment (processed_samples is already int16)
        audio_segment = AudioSegment(
            processed_samples.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=1
        )
        
        # Add 0.5s silence at start
        silence = AudioSegment.silent(duration=500, frame_rate=sample_rate)
        final_audio = silence + audio_segment
        
        # Export as MP3
        mp3_buffer = BytesIO()
        final_audio.export(
            mp3_buffer,
            format='mp3',
            bitrate='192k',
            parameters=['-q:a', '2']
        )
        mp3_buffer.seek(0)
        
        return mp3_buffer



def export_detections(
    db_path: Path,
    output_dir: Path,
    detections: List[Dict],
    language_code: str,
    filter_context: Dict,
    audio_options: Dict,
    pm_seconds: float = 1.0,
    disable_tts: bool = False
):
    """
    Export detections as individual WAV files.
    
    Args:
        db_path: Path to BirdNET database
        output_dir: Output directory for WAV files
        detections: List of detections from query_detections()
        language_code: Language code for TTS
        filter_context: Filter context dict
        audio_options: Audio options dict (see prepare_detection_audio)
        pm_seconds: Plus/Minus buffer
        disable_tts: Disable TTS announcements
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    player = AudioPlayer(db_path, pm_seconds)
    
    logger.info(f"Exporting {len(detections)} detections to {output_dir}")
    
    for i, detection in enumerate(detections, 1):
        try:
            # Generate audio with sequential audio number
            audio_bytes = player.prepare_detection_audio(
                detection,
                audio_number=i,
                language_code=language_code,
                filter_context=filter_context,
                audio_options=audio_options,
                disable_tts=disable_tts
            )
            
            # Create filename
            detection_id = detection['detection_id']
            scientific_safe = detection['scientific_name'].replace(' ', '_')
            timestamp = detection['segment_start_local'].replace(':', '').replace('-', '').replace(' ', '_')
            filename = f"{detection_id:06d}_{scientific_safe}_{timestamp}.wav"
            
            # Write file
            output_path = output_dir / filename
            with open(output_path, 'wb') as f:
                f.write(audio_bytes.read())
            
            logger.debug(f"[{i}/{len(detections)}] Exported: {filename}")
            
        except Exception as e:
            logger.error(f"Failed to export detection #{detection['detection_id']}: {e}")
    
    logger.info(f"Export complete: {len(detections)} files in {output_dir}")    
    


def export_detections_mp3(
    db_path: Path,
    output_dir: Path,
    detections: List[Dict],
    language_code: str,
    filter_context: Dict,
    audio_options: Dict,
    pm_seconds: float = 1.0,
    disable_tts: bool = False
):
    """
    Export detections as individual MP3 files.
    
    Args:
        db_path: Path to BirdNET database
        output_dir: Output directory for MP3 files
        detections: List of detections from query_detections()
        language_code: Language code for TTS
        filter_context: Filter context dict
        audio_options: Audio options dict (see prepare_detection_audio_web)
        pm_seconds: Plus/Minus buffer
        disable_tts: Disable TTS announcements
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    player = AudioPlayer(db_path, pm_seconds)
    
    logger.info(f"Exporting {len(detections)} detections as MP3 to {output_dir}")
    
    for i, detection in enumerate(detections, 1):
        try:
            # Generate audio as MP3 with sequential audio number
            audio_bytes = player.prepare_detection_audio_web(
                detection,
                audio_number=i,
                language_code=language_code,
                filter_context=filter_context,
                audio_options=audio_options,
                disable_tts=disable_tts
            )
            
            # Create filename
            detection_id = detection['detection_id']
            scientific_safe = detection['scientific_name'].replace(' ', '_')
            timestamp = detection['segment_start_local'].replace(':', '').replace('-', '').replace(' ', '_')
            filename = f"{detection_id:06d}_{scientific_safe}_{timestamp}.mp3"
            
            # Write file
            output_path = output_dir / filename
            with open(output_path, 'wb') as f:
                f.write(audio_bytes.read())
            
            logger.debug(f"[{i}/{len(detections)}] Exported: {filename}")
            
        except Exception as e:
            logger.error(f"Failed to export detection #{detection['detection_id']}: {e}")
    
    logger.info(f"MP3 export complete: {len(detections)} files in {output_dir}")
    
    
    