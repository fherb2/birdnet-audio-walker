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
        language_code: str,
        filter_context: Dict,
        use_sci: bool = False
    ) -> BytesIO:
        """
        Create combined audio: Pause + Snippet + TTS announcement.
        
        Args:
            detection: Detection dict from query_detections()
            language_code: Language code for TTS (e.g., 'de', 'en')
            filter_context: Dict with filter info:
                - 'species_filter': bool
                - 'detection_id_given': bool
                - 'time_filter': bool
            use_sci: Use scientific names instead of local names
            
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
        except Exception as e:
            logger.error(f"Failed to extract snippet for detection #{detection['detection_id']}: {e}")
            raise
        
        # 3. Generate TTS announcement
        tts_text = self._get_announcement_text(detection, filter_context, use_sci)
        
        try:
            tts_audio = generate_tts(tts_text, language_code, use_sci)
        except Exception as e:
            logger.warning(f"TTS generation failed, using silence: {e}")
            tts_audio = self._generate_silence(1.0, 48000)
        
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
    
    def _get_announcement_text(
            self,
            detection: Dict,
            filter_context: Dict,
            use_sci: bool
        ) -> str:
            """
            Generate TTS announcement text based on filter context.
            
            Rules:
            - Species filter active → ID + Confidence
            - Time + Species filter → ID + Confidence
            - Detection ID given OR only time filter → ID + Name + Confidence
            - No filters → ID + Name + Confidence
            
            Args:
                detection: Detection dict
                filter_context: Filter context dict
                use_sci: Use scientific name
                
            Returns:
                Text for TTS announcement
            """
            detection_id = detection['detection_id']
            
            # Format confidence: convert to words for TTS
            confidence = detection['confidence']
            conf_percent = int(round(confidence * 100))
            
            # Convert number to German words (e.g., 87 → "siebenundachtzig")
            # Determine language for num2words
            # For now, we assume German for confidence, can be extended
            conf_percent_words = num2words(conf_percent, lang='de')
            
            # Only ID + Confidence if species filter active
            if filter_context.get('species_filter'):
                return f"{detection_id} {conf_percent_words} Prozent"
            
            # ID + Name + Confidence otherwise
            if use_sci:
                name = detection['scientific_name']
            else:
                name = detection.get('local_name') or detection['scientific_name']
            
            return f"{detection_id} {name} {conf_percent_words} Prozent"


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
        language_code: str,
        filter_context: Dict,
        use_sci: bool = False,
        disable_tts: bool = False
    ) -> BytesIO:
        """
        Create combined audio as MP3 (for web streaming).
        
        Same as prepare_detection_audio() but returns MP3 instead of WAV.
        Much smaller file size for web transfer.
        
        Args:
            detection: Detection dict from query_detections()
            language_code: Language code for TTS
            filter_context: Filter context dict
            use_sci: Use scientific names
            
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
        except Exception as e:
            logger.error(f"Failed to extract snippet for detection #{detection['detection_id']}: {e}")
            raise
        
        # 3. Generate TTS announcement (nur wenn nicht disabled)
        if not disable_tts:
            tts_text = self._get_announcement_text(detection, filter_context, use_sci)
            
            try:
                # WICHTIG: Bei wissenschaftlichen Namen IMMER deutsche Stimme!
                tts_lang = 'de' if use_sci else language_code
                tts_audio = generate_tts(tts_text, tts_lang, use_sci=False)
            except Exception as e:
                logger.warning(f"TTS generation failed, using silence: {e}")
                tts_audio = self._generate_silence(1.0, 48000)
        else:
            # TTS disabled - nur kurze Pause statt Ansage
            tts_audio = self._generate_silence(0.5, 48000)
        
        # 4. Combine: Pause + Audio + TTS
        audio_resampled = self._resample_if_needed(audio_data, sample_rate, 48000)
        
        combined = self._combine_audio_segments(
            [pause, audio_resampled, tts_audio],
            48000
        )
        
        # 5. Convert to MP3 instead of WAV
        mp3_bytes = self._to_mp3_bytes(combined, 48000)
        
        logger.debug(
            f"MP3 prepared: detection #{detection['detection_id']}, "
            f"size ~{len(mp3_bytes.getvalue())/1024:.1f}KB"
        )
        
        return mp3_bytes


def export_detections(
    db_path: Path,
    output_dir: Path,
    detections: List[Dict],
    language_code: str,
    filter_context: Dict,
    pm_seconds: float = 1.0,
    use_sci: bool = False,
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
        pm_seconds: Plus/Minus buffer
        use_sci: Use scientific names
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    player = AudioPlayer(db_path, pm_seconds)
    
    logger.info(f"Exporting {len(detections)} detections to {output_dir}")
    
    for i, detection in enumerate(detections, 1):
        try:
            # Generate audio
            # Note: WAV export uses the non-web version (WAV instead of MP3)
            # We need to add disable_tts support here too
            audio_bytes = player.prepare_detection_audio(
                detection,
                language_code,
                filter_context,
                use_sci
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
    pm_seconds: float = 1.0,
    use_sci: bool = False,
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
        pm_seconds: Plus/Minus buffer
        use_sci: Use scientific names
        disable_tts: Disable TTS announcements
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    player = AudioPlayer(db_path, pm_seconds)
    
    logger.info(f"Exporting {len(detections)} detections as MP3 to {output_dir}")
    
    for i, detection in enumerate(detections, 1):
        try:
            # Generate audio as MP3
            audio_bytes = player.prepare_detection_audio_web(
                detection,
                language_code,
                filter_context,
                use_sci,
                disable_tts
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
