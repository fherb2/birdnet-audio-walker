"""
AudioMoth WAV file metadata extraction.
"""

import wave
import struct
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from loguru import logger


def extract_metadata(wav_path: str) -> dict:
    """
    Extract metadata from AudioMoth WAV file.
    
    Args:
        wav_path: Path to WAV file
        
    Returns:
        dict with keys:
        - 'filename': str - Original filename
        - 'timestamp_utc': datetime - UTC timestamp from GUANO
        - 'timestamp_local': datetime - Local time (MEZ/MESZ)
        - 'timezone': str - 'MEZ' or 'MESZ'
        - 'serial': str - Device ID
        - 'gps_lat': float - GPS Latitude
        - 'gps_lon': float - GPS Longitude
        - 'sample_rate': int - Sample rate in Hz
        - 'channels': int - Number of channels
        - 'bit_depth': int - Bit depth
        - 'duration_seconds': float - Duration in seconds
        - 'temperature_c': float - Temperature in Celsius
        - 'battery_voltage': float - Battery voltage
        - 'gain': str - Gain setting
        - 'firmware': str - Firmware version
        
    Raises:
        ValueError: If file is not a valid AudioMoth WAV
    """
    wav_path = Path(wav_path)
    filename = wav_path.name
    
    logger.debug(f"Extracting metadata from: {filename}")
    
    # Standard WAV parameters
    try:
        with wave.open(str(wav_path), 'rb') as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            n_frames = wav.getnframes()
            duration = n_frames / sample_rate
    except Exception as e:
        raise ValueError(f"Invalid WAV file: {e}")
    
    # Parse RIFF chunks for GUANO metadata
    guano_data = {}
    
    try:
        with open(wav_path, 'rb') as f:
            # Read RIFF header
            riff_id = f.read(4)
            if riff_id != b'RIFF':
                raise ValueError("Not a RIFF file")
            
            file_size = struct.unpack('<I', f.read(4))[0]
            wave_id = f.read(4)
            
            if wave_id != b'WAVE':
                raise ValueError("Not a WAVE file")
            
            # Iterate through chunks
            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                
                chunk_size = struct.unpack('<I', f.read(4))[0]
                chunk_data = f.read(chunk_size)
                
                # Parse LIST chunk (contains ICMT with AudioMoth info)
                if chunk_id == b'LIST':
                    if len(chunk_data) >= 4 and chunk_data[0:4] == b'INFO':
                        offset = 4
                        while offset < len(chunk_data) - 8:
                            sub_id = chunk_data[offset:offset+4]
                            sub_size = struct.unpack('<I', chunk_data[offset+4:offset+8])[0]
                            sub_data = chunk_data[offset+8:offset+8+sub_size]
                            
                            if sub_id == b'ICMT':
                                icmt_text = sub_data.decode('ascii', errors='replace').rstrip('\x00')
                                guano_data['icmt'] = icmt_text
                            
                            offset += 8 + sub_size
                            if sub_size % 2:  # Word alignment
                                offset += 1
                
                # Parse GUANO chunk
                elif chunk_id == b'guan':
                    guano_text = chunk_data.decode('ascii', errors='replace').rstrip('\x00')
                    guano_data['guano'] = guano_text
                
                # Skip padding byte if chunk size is odd
                if chunk_size % 2:
                    f.read(1)
    
    except Exception as e:
        logger.warning(f"Error parsing RIFF chunks: {e}")
    
    # Parse GUANO metadata
    metadata = {
        'filename': filename,
        'sample_rate': sample_rate,
        'channels': channels,
        'bit_depth': sample_width * 8,
        'duration_seconds': duration
    }
    
    # Parse GUANO text (key:value format)
    if 'guano' in guano_data:
        for line in guano_data['guano'].split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'Serial':
                    metadata['serial'] = value
                elif key == 'Timestamp':
                    # Parse ISO timestamp
                    timestamp_utc = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    metadata['timestamp_utc'] = timestamp_utc
                elif key == 'Loc Position':
                    # Parse GPS coordinates
                    parts = value.split()
                    if len(parts) >= 2:
                        metadata['gps_lat'] = float(parts[0])
                        metadata['gps_lon'] = float(parts[1])
                elif key == 'Firmware Version':
                    metadata['firmware'] = value
                elif key == 'OAD|Recording Settings':
                    # Extract gain from recording settings
                    if 'GAIN' in value:
                        metadata['gain'] = value.split('GAIN')[1].strip().split()[0]
                elif key == 'OAD|Battery Voltage':
                    metadata['battery_voltage'] = float(value)
                elif key == 'Temperature Int':
                    metadata['temperature_c'] = float(value)
    
    # Parse ICMT for additional info (fallback)
    if 'icmt' in guano_data and 'timestamp_utc' not in metadata:
        # Try to extract timestamp from ICMT
        icmt = guano_data['icmt']
        # Example: "Recorded at 16:46:32 16/04/2025 (UTC) by AudioMoth..."
        try:
            if 'Recorded at' in icmt:
                time_part = icmt.split('Recorded at')[1].split('(UTC)')[0].strip()
                # Parse time_part: "16:46:32 16/04/2025"
                timestamp_utc = datetime.strptime(time_part, "%H:%M:%S %d/%m/%Y")
                timestamp_utc = timestamp_utc.replace(tzinfo=ZoneInfo('UTC'))
                metadata['timestamp_utc'] = timestamp_utc
            
            # Extract temperature and battery from ICMT
            if 'temperature was' in icmt and 'temperature_c' not in metadata:
                temp_str = icmt.split('temperature was')[1].split('C')[0].strip()
                metadata['temperature_c'] = float(temp_str)
            
            if 'battery was' in icmt and 'battery_voltage' not in metadata:
                volt_str = icmt.split('battery was')[1].split('V')[0].strip()
                metadata['battery_voltage'] = float(volt_str)
        except Exception as e:
            logger.warning(f"Error parsing ICMT timestamp: {e}")
    
    # Convert UTC to MEZ/MESZ
    if 'timestamp_utc' in metadata:
        berlin_tz = ZoneInfo('Europe/Berlin')
        timestamp_local = metadata['timestamp_utc'].astimezone(berlin_tz)
        metadata['timestamp_local'] = timestamp_local
        
        # Determine timezone (MEZ or MESZ)
        # MESZ = Daylight Saving Time (last Sunday in March to last Sunday in October)
        is_dst = bool(timestamp_local.dst())
        metadata['timezone'] = 'MESZ' if is_dst else 'MEZ'
    else:
        raise ValueError(f"No timestamp found in GUANO metadata for {filename}")
    
    logger.debug(f"Metadata extracted: {filename} @ {metadata.get('timestamp_local')}")
    
    return metadata
