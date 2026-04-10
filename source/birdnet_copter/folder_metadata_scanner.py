"""
folder_metadata_scanner.py

Scans all files in a folder and extracts metadata into a unified
Meta-Data-Dictionary for use in the DB configuration UI.

Architecture:
  - Classifiers (Section 2): determine the FileClass of each file
  - Parsers     (Section 3): extract metadata for each FileClass
  - Builder     (Section 4): merges results into the Meta-Data-Dictionary
  - Public API  (Section 5): scan_folder() – single entry point

The Meta-Data-Dictionary format:
    key   : str  – metadata field name (e.g. 'timestamp_utc', 'gps_lat')
    value : tuple(
        files:  list[str]  – filenames that contain this key/value pair
        values: list[Any]  – values, index-synchronous with files
    )

Run blocking in a thread pool (asyncio.run_in_executor) – never call
scan_folder() directly from an async context.

Extension guide:
  - New classifier: add a _classify_* function, append to CLASSIFIERS.
  - New parser:     add a _parse_* function, add to PARSERS dict.
  - New file class: add entry to FileClass enum, wire up classifier + parser.
"""

import os
import struct
import wave
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Optional dependencies – imported lazily so missing packages give clear errors
# ---------------------------------------------------------------------------
try:
    import mutagen
    import mutagen.wave
    import mutagen.flac
    import mutagen.mp3
    import mutagen.oggvorbis
    _MUTAGEN_AVAILABLE = True
except ImportError:
    _MUTAGEN_AVAILABLE = False
    logger.warning("mutagen not installed – standard audio tag parsing disabled")


# ===========================================================================
# SECTION 1: Data structures
# ===========================================================================

class FileClass(Enum):
    """
    Classification result for a single file.

    Values are ordered roughly by information richness: richer classes
    are attempted first in the classifier registry.
    """
    WAV_GUANO        = auto()  # WAV with GUANO chunk (e.g. AudioMoth ≥ 1.4)
    WAV_ICMT         = auto()  # WAV with ICMT comment only (older AudioMoth)
    WAV_PLAIN        = auto()  # WAV without any known metadata chunks
    AUDIO_GENERIC    = auto()  # Non-WAV audio (FLAC, MP3, OGG, …)
    AUDIOMOTH_CONFIG = auto()  # AudioMoth CONFIG.TXT (text key:value)
    UNKNOWN          = auto()  # No classifier matched


# Type alias for the Meta-Data-Dictionary
MetaDataDict = dict[str, tuple[list[str], list[Any]]]


def _empty_meta() -> MetaDataDict:
    """Return a fresh, empty Meta-Data-Dictionary."""
    return {}


# ===========================================================================
# SECTION 2: Classifier registry
# ===========================================================================
#
# Each classifier is a function with signature:
#   (path: Path) -> FileClass | None
#
# Classifiers are tried in order; the first non-None result wins.
# The final entry MUST always return a non-None value (fallback).
# ---------------------------------------------------------------------------

# ── WAV / GUANO ─────────────────────────────────────────────────────────────

def _classify_wav_guano(path: Path) -> FileClass | None:
    """WAV file that contains a 'guan' RIFF chunk."""
    if path.suffix.lower() != '.wav':
        return None
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'RIFF':
                return None
            f.seek(8)   # skip file-size field
            if f.read(4) != b'WAVE':
                return None
            # Scan chunks for 'guan'
            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = struct.unpack('<I', f.read(4))[0]
                if chunk_id == b'guan':
                    return FileClass.WAV_GUANO
                # skip chunk body + optional padding byte
                f.seek(chunk_size + (chunk_size % 2), os.SEEK_CUR)
    except OSError:
        pass
    return None


def _classify_wav_icmt(path: Path) -> FileClass | None:
    """WAV file that contains an ICMT sub-chunk inside a LIST/INFO chunk."""
    if path.suffix.lower() != '.wav':
        return None
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'RIFF':
                return None
            f.seek(8)
            if f.read(4) != b'WAVE':
                return None
            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = struct.unpack('<I', f.read(4))[0]
                if chunk_id == b'LIST':
                    chunk_data = f.read(chunk_size)
                    if chunk_data[:4] == b'INFO' and b'ICMT' in chunk_data:
                        return FileClass.WAV_ICMT
                    continue   # already consumed body
                f.seek(chunk_size + (chunk_size % 2), os.SEEK_CUR)
    except OSError:
        pass
    return None


def _classify_wav_plain(path: Path) -> FileClass | None:
    """Any remaining WAV file (no GUANO, no ICMT)."""
    if path.suffix.lower() == '.wav':
        return FileClass.WAV_PLAIN
    return None


# ── Generic audio (non-WAV) ─────────────────────────────────────────────────

_AUDIO_SUFFIXES = {'.flac', '.mp3', '.ogg', '.opus', '.aac', '.m4a', '.aif', '.aiff'}

def _classify_audio_generic(path: Path) -> FileClass | None:
    """Known non-WAV audio formats, identified by file extension."""
    if path.suffix.lower() in _AUDIO_SUFFIXES:
        return FileClass.AUDIO_GENERIC
    return None


# ── AudioMoth CONFIG.TXT ─────────────────────────────────────────────────────

_AUDIOMOTH_CONFIG_MARKERS = [
    b'Device ID',
    b'Firmware',
    b'Sample rate',
]

def _classify_audiomoth_config(path: Path) -> FileClass | None:
    """
    Text file whose first ~512 bytes contain AudioMoth config markers.
    Deliberately file-name-agnostic so renamed copies are still recognised.
    """
    if path.is_dir():
        return None
    try:
        with open(path, 'rb') as f:
            header = f.read(512)
        matches = sum(1 for m in _AUDIOMOTH_CONFIG_MARKERS if m in header)
        if matches >= 2:
            return FileClass.AUDIOMOTH_CONFIG
    except OSError:
        pass
    return None


# ── Fallback ─────────────────────────────────────────────────────────────────

def _classify_unknown(path: Path) -> FileClass | None:
    """Catch-all – always matches."""
    return FileClass.UNKNOWN


# ── Registry ─────────────────────────────────────────────────────────────────
# Order matters: richer / more specific classifiers first.

CLASSIFIERS: list = [
    _classify_wav_guano,
    _classify_wav_icmt,
    _classify_wav_plain,
    _classify_audio_generic,
    _classify_audiomoth_config,
    _classify_unknown,          # must be last
]


def classify_file(path: Path) -> FileClass:
    """Run the classifier registry and return the first matching FileClass."""
    for classifier in CLASSIFIERS:
        result = classifier(path)
        if result is not None:
            return result
    return FileClass.UNKNOWN   # should never be reached


# ===========================================================================
# SECTION 3: Parser registry
# ===========================================================================
#
# Each parser has signature:
#   (path: Path) -> dict[str, Any]
#
# The returned dict maps metadata key → single value for this file.
# Keys should be consistent across parsers (e.g. always 'timestamp_utc',
# never 'ts_utc' in one parser and 'timestamp' in another).
#
# Every parser also calls _parse_filesystem() to include OS-level metadata.
# ---------------------------------------------------------------------------

# ── Shared: filesystem metadata ──────────────────────────────────────────────

def _parse_filesystem(path: Path) -> dict[str, Any]:
    """
    Extract filesystem-level metadata available for any file.

    Keys produced:
      fs_size_bytes     : int
      fs_created_at     : datetime | None   (platform-dependent reliability)
      fs_modified_at    : datetime | None
    """
    result: dict[str, Any] = {}
    try:
        stat = path.stat()
        result['fs_size_bytes'] = stat.st_size
        result['fs_modified_at'] = datetime.fromtimestamp(stat.st_mtime)
        # st_ctime is creation time on Windows, last metadata-change on POSIX
        result['fs_created_at'] = datetime.fromtimestamp(stat.st_ctime)
    except OSError as e:
        logger.warning(f"Filesystem stat failed for {path.name}: {e}")
    return result


# ── Shared: standard WAV technical parameters ─────────────────────────────────

def _parse_wav_technical(path: Path) -> dict[str, Any]:
    """
    Read sample rate, channels, bit depth and duration via stdlib wave module.

    Keys produced:
      sample_rate       : int   (Hz)
      channels          : int
      bit_depth         : int
      duration_seconds  : float
    """
    result: dict[str, Any] = {}
    try:
        with wave.open(str(path), 'rb') as wf:
            result['sample_rate']      = wf.getframerate()
            result['channels']         = wf.getnchannels()
            result['bit_depth']        = wf.getsampwidth() * 8
            result['duration_seconds'] = wf.getnframes() / wf.getframerate()
    except Exception as e:
        logger.warning(f"WAV technical parse failed for {path.name}: {e}")
    return result


# ── Shared: RIFF chunk reader ─────────────────────────────────────────────────

def _read_riff_chunks(path: Path) -> dict[str, bytes]:
    """
    Low-level RIFF chunk reader.  Returns dict of chunk_id → raw bytes.
    For LIST/INFO, sub-chunks are also extracted with key 'LIST:XXXX'.
    Skips the 'data' chunk body (audio samples) for speed.
    """
    chunks: dict[str, bytes] = {}
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'RIFF':
                return chunks
            f.seek(8)
            if f.read(4) != b'WAVE':  # re-read after seek
                # Actually we need to re-read the form type
                pass
            f.seek(12)  # skip RIFF + size + WAVE
            while True:
                raw_id = f.read(4)
                if len(raw_id) < 4:
                    break
                chunk_size = struct.unpack('<I', f.read(4))[0]
                chunk_id   = raw_id.decode('ascii', errors='replace').rstrip()

                if chunk_id == 'data':
                    # Skip audio data – only store size
                    chunks['data:size'] = str(chunk_size).encode()
                    f.seek(chunk_size + (chunk_size % 2), os.SEEK_CUR)
                    continue

                body = f.read(chunk_size)
                if chunk_size % 2:
                    f.read(1)   # padding byte

                chunks[chunk_id] = body

                # Unpack LIST/INFO sub-chunks
                if chunk_id == 'LIST' and body[:4] == b'INFO':
                    offset = 4
                    while offset < len(body) - 8:
                        sub_id   = body[offset:offset+4].decode('ascii', errors='replace')
                        sub_size = struct.unpack('<I', body[offset+4:offset+8])[0]
                        sub_body = body[offset+8:offset+8+sub_size]
                        chunks[f'LIST:{sub_id}'] = sub_body
                        offset += 8 + sub_size + (sub_size % 2)

    except OSError as e:
        logger.warning(f"RIFF read failed for {path.name}: {e}")
    return chunks


# ── Parser: WAV_GUANO ─────────────────────────────────────────────────────────

def _parse_wav_guano(path: Path) -> dict[str, Any]:
    """
    Parse a WAV file with a GUANO chunk.

    GUANO format: UTF-8 text, one 'Key: Value' pair per line.
    Well-known keys extracted:
      timestamp_utc, gps_lat, gps_lon, serial, firmware,
      temperature_c, battery_voltage, gain, sample_rate (cross-check)

    Namespace keys (e.g. 'OAD|Battery Voltage') are stored with their
    full name so they appear in the meta table for user inspection.

    Also runs _parse_wav_technical and _parse_filesystem.
    """
    result = _parse_filesystem(path)
    result.update(_parse_wav_technical(path))

    chunks = _read_riff_chunks(path)
    guano_raw = chunks.get('guan', b'')
    guano_text = guano_raw.decode('utf-8', errors='replace')

    for line in guano_text.splitlines():
        if ':' not in line:
            continue
        key, _, raw_val = line.partition(':')
        key     = key.strip()
        raw_val = raw_val.strip()

        if not key or not raw_val:
            continue

        # ── Well-known standard fields ──
        if key == 'Timestamp':
            try:
                result['timestamp_utc'] = datetime.fromisoformat(
                    raw_val.replace('Z', '+00:00')
                )
                result['timestamp_utc_source'] = 'GUANO:Timestamp'
            except ValueError:
                logger.warning(f"GUANO Timestamp parse failed: {raw_val!r}")

        elif key == 'Loc Position':
            parts = raw_val.split()
            if len(parts) >= 2:
                try:
                    result['gps_lat'] = float(parts[0])
                    result['gps_lon'] = float(parts[1])
                except ValueError:
                    pass

        elif key == 'Serial':
            result['serial'] = raw_val

        elif key == 'Firmware Version':
            result['firmware'] = raw_val

        elif key == 'Temperature Int':
            try:
                result['temperature_c'] = float(raw_val)
            except ValueError:
                pass

        elif key == 'Make':
            result['device_make'] = raw_val

        elif key == 'Model':
            result['device_model'] = raw_val

        elif key == 'Samplerate':
            try:
                result['sample_rate_guano'] = int(raw_val)
            except ValueError:
                pass

        # ── AudioMoth OAD namespace fields ──
        elif key == 'OAD|Battery Voltage':
            try:
                result['battery_voltage'] = float(raw_val)
            except ValueError:
                pass

        elif key == 'OAD|Recording Settings' and 'gain' not in result:
            # Store raw string; UI can display for user inspection
            result['oad_recording_settings'] = raw_val

        # ── All other keys: store as-is for UI display ──
        else:
            result[f'guano:{key}'] = raw_val

    # Gain may also live in ICMT as fallback
    if 'gain' not in result:
        icmt_raw = chunks.get('LIST:ICMT', b'')
        if icmt_raw:
            result.update(_extract_icmt_fields(
                icmt_raw.decode('ascii', errors='replace').rstrip('\x00'),
                skip_timestamp=('timestamp_utc' in result),
            ))

    return result


# ── Parser: WAV_ICMT ──────────────────────────────────────────────────────────

def _extract_icmt_fields(
    icmt_text: str,
    skip_timestamp: bool = False,
) -> dict[str, Any]:
    """
    Parse the free-text ICMT comment written by AudioMoth firmware.

    Example (firmware ≥ 1.2):
      "Recorded at 16:46:32 16/04/2025 (UTC) by AudioMoth 249C600363FA5E80
       at Medium gain setting while battery was 4.8V and temperature was 21.3C."

    Keys produced (when present):
      timestamp_utc, timestamp_utc_source,
      serial, gain, battery_voltage, temperature_c
    """
    from zoneinfo import ZoneInfo
    result: dict[str, Any] = {}

    if not skip_timestamp and 'Recorded at' in icmt_text:
        try:
            time_part = icmt_text.split('Recorded at')[1].split('(UTC)')[0].strip()
            ts = datetime.strptime(time_part, '%H:%M:%S %d/%m/%Y')
            result['timestamp_utc'] = ts.replace(tzinfo=ZoneInfo('UTC'))
            result['timestamp_utc_source'] = 'ICMT'
        except (ValueError, IndexError) as e:
            logger.warning(f"ICMT timestamp parse failed: {e}")

    # Serial / device ID
    if 'AudioMoth' in icmt_text:
        try:
            result['serial'] = icmt_text.split('AudioMoth')[1].strip().split()[0]
        except IndexError:
            pass

    # Gain
    if 'gain setting' in icmt_text:
        try:
            result['gain'] = icmt_text.split('at ')[1].split(' gain')[0].strip()
        except IndexError:
            pass

    # Battery voltage
    if 'battery was' in icmt_text:
        try:
            result['battery_voltage'] = float(
                icmt_text.split('battery was')[1].split('V')[0].strip()
            )
        except (ValueError, IndexError):
            pass

    # Temperature
    if 'temperature was' in icmt_text:
        try:
            result['temperature_c'] = float(
                icmt_text.split('temperature was')[1].split('C')[0].strip()
            )
        except (ValueError, IndexError):
            pass

    return result


def _parse_wav_icmt(path: Path) -> dict[str, Any]:
    """
    Parse a WAV file that has ICMT but no GUANO chunk.
    Falls back to _extract_icmt_fields.
    """
    result = _parse_filesystem(path)
    result.update(_parse_wav_technical(path))

    chunks = _read_riff_chunks(path)
    icmt_raw = chunks.get('LIST:ICMT', b'')
    if icmt_raw:
        icmt_text = icmt_raw.decode('ascii', errors='replace').rstrip('\x00')
        result.update(_extract_icmt_fields(icmt_text))

    return result


# ── Parser: WAV_PLAIN ─────────────────────────────────────────────────────────

def _parse_wav_plain(path: Path) -> dict[str, Any]:
    """
    WAV file with no known metadata chunks.
    Extracts technical parameters and filesystem metadata only.
    Also attempts mutagen for any tags that might be present.
    """
    result = _parse_filesystem(path)
    result.update(_parse_wav_technical(path))
    if _MUTAGEN_AVAILABLE:
        result.update(_parse_mutagen_tags(path))
    return result


# ── Parser: AUDIO_GENERIC ─────────────────────────────────────────────────────

def _parse_audio_generic(path: Path) -> dict[str, Any]:
    """
    Generic audio parser via mutagen.
    Extracts whatever tags mutagen can find (title, artist, date, etc.)
    plus duration/sample-rate where available.
    """
    result = _parse_filesystem(path)
    if _MUTAGEN_AVAILABLE:
        result.update(_parse_mutagen_tags(path))
    return result


def _parse_mutagen_tags(path: Path) -> dict[str, Any]:
    """
    Use mutagen.File() to read any tags present in the file.
    Tag key names are prefixed with 'tag:' to avoid collisions.
    Duration and sample rate are extracted if available.
    """
    result: dict[str, Any] = {}
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return result

        # Duration / bitrate from audio info
        info = getattr(audio, 'info', None)
        if info:
            if hasattr(info, 'length'):
                result['duration_seconds'] = float(info.length)
            if hasattr(info, 'sample_rate'):
                result['sample_rate'] = int(info.sample_rate)
            if hasattr(info, 'channels'):
                result['channels'] = int(info.channels)

        # All tags
        for k, v in audio.items():
            val = v[0] if isinstance(v, list) and v else v
            result[f'tag:{k}'] = str(val)

    except Exception as e:
        logger.debug(f"mutagen parse failed for {path.name}: {e}")
    return result


# ── Parser: AUDIOMOTH_CONFIG ──────────────────────────────────────────────────

def _parse_audiomoth_config(path: Path) -> dict[str, Any]:
    """
    Parse an AudioMoth configuration text file (CONFIG.TXT or equivalent).

    Format: lines of the form 'Key  :  Value' or 'Key : Value'.
    Multi-line values (like 'Beschreibung:') are captured until next key.

    Keys produced (when present):
      serial, firmware, device_time_utc, sample_rate, gain,
      location_lat, location_lon, location_description,
      sun_recording_mode, dawn_before_mins, dawn_after_mins,
      dusk_before_mins, dusk_after_mins,
      plus raw 'cfg:<OriginalKey>' for all other lines.
    """
    result = _parse_filesystem(path)
    result['cfg_file'] = path.name

    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError as e:
        logger.warning(f"Cannot read config file {path.name}: {e}")
        return result

    # ── Key:value parsing ──
    raw: dict[str, str] = {}
    current_key: str | None = None

    for line in text.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            k = k.strip()
            v = v.strip()
            if k:
                current_key = k
                raw[k] = v
        elif current_key and line.strip():
            # continuation line for multi-line values
            raw[current_key] = (raw[current_key] + ' ' + line.strip()).strip()

    # ── Map to normalised keys ──
    for k, v in raw.items():
        kl = k.lower()

        if 'device id' in kl:
            result['serial'] = v

        elif 'firmware' in kl:
            result['firmware'] = v

        elif 'device time' in kl:
            # "2025-05-01 13:36:06 (UTC)"
            try:
                ts_str = v.split('(UTC)')[0].strip()
                from zoneinfo import ZoneInfo
                result['device_time_utc'] = datetime.strptime(
                    ts_str, '%Y-%m-%d %H:%M:%S'
                ).replace(tzinfo=ZoneInfo('UTC'))
            except (ValueError, IndexError):
                result['cfg:Device time'] = v

        elif 'sample rate' in kl:
            try:
                result['sample_rate'] = int(v.split()[0])
            except (ValueError, IndexError):
                pass

        elif kl == 'gain':
            result['gain'] = v

        elif 'location' in kl:
            # "51.033469°N 14.341964°E (Acoustic chime)"
            # May also be a free-text description on a continuation line
            _parse_location_field(v, result)

        elif 'sun recording mode' in kl:
            result['sun_recording_mode'] = v

        elif 'dawn' in kl and 'before' in kl:
            # "Dawn - before, after (mins) : 0, 360"
            try:
                parts = v.split(',')
                result['dawn_before_mins'] = int(parts[0].strip())
                result['dawn_after_mins']  = int(parts[1].strip())
            except (ValueError, IndexError):
                pass

        elif 'dusk' in kl and 'before' in kl:
            try:
                parts = v.split(',')
                result['dusk_before_mins'] = int(parts[0].strip())
                result['dusk_after_mins']  = int(parts[1].strip())
            except (ValueError, IndexError):
                pass

        else:
            # Store unrecognised fields with cfg: prefix
            result[f'cfg:{k}'] = v

    return result


def _parse_location_field(value: str, result: dict[str, Any]) -> None:
    """
    Try to extract lat/lon from a Location field value.

    Handles formats like:
      "51.033469°N 14.341964°E (Acoustic chime)"
      "51.033469 14.341964"
      "51.033469N 14.341964E"
    Remaining text after coordinates is stored as location_description.
    """
    import re
    # Pattern: optional sign, digits, optional degree symbol, optional N/S/E/W
    coord_pat = re.compile(
        r'([+-]?\d+\.?\d*)\s*°?\s*([NSns]?)\s+'
        r'([+-]?\d+\.?\d*)\s*°?\s*([EWew]?)'
    )
    m = coord_pat.search(value)
    if m:
        lat = float(m.group(1))
        if m.group(2).upper() == 'S':
            lat = -lat
        lon = float(m.group(3))
        if m.group(4).upper() == 'W':
            lon = -lon
        result['gps_lat'] = lat
        result['gps_lon'] = lon

        # Text after the coordinate match → description
        rest = value[m.end():].strip(' ()')
        if rest:
            result['location_description'] = rest
    else:
        # Not parseable as coordinates – store as description
        result['location_description'] = value


# ── Parser: UNKNOWN ───────────────────────────────────────────────────────────

def _parse_unknown(path: Path) -> dict[str, Any]:
    """Fallback parser: filesystem metadata only."""
    return _parse_filesystem(path)


# ── Registry ──────────────────────────────────────────────────────────────────
# Maps FileClass → parser function.

PARSERS: dict[FileClass, callable] = {
    FileClass.WAV_GUANO:        _parse_wav_guano,
    FileClass.WAV_ICMT:         _parse_wav_icmt,
    FileClass.WAV_PLAIN:        _parse_wav_plain,
    FileClass.AUDIO_GENERIC:    _parse_audio_generic,
    FileClass.AUDIOMOTH_CONFIG: _parse_audiomoth_config,
    FileClass.UNKNOWN:          _parse_unknown,
}



# ===========================================================================
# SECTION 4: Dictionary-Builder
# ===========================================================================
#
# Merges per-file parse results into the shared MetaDataDict.
#
# MetaDataDict structure:
#   key  → ( files: list[str],  values: list[Any] )
#
# Where files[i] is the filename and values[i] is the corresponding value.
# If two files share the same key AND the same value, they are grouped into
# one row.  If they share the key but have different values, they appear as
# separate rows (since the UI uses radio-button semantics per key).
# ---------------------------------------------------------------------------

def _merge_into_dict(
    meta_dict: MetaDataDict,
    filename: str,
    parsed: dict[str, Any],
) -> None:
    """
    Merge one file's parsed metadata into meta_dict.

    For each (key, value) pair in parsed:
      - If a row with this key AND this exact value already exists,
        append the filename to its files list.
      - Otherwise, create a new row for this key with a new value entry.
    """
    for key, value in parsed.items():
        if key not in meta_dict:
            meta_dict[key] = ([filename], [value])
        else:
            files, values = meta_dict[key]
            # Check if this exact value already exists in the list
            try:
                idx = values.index(value)
                # Same value → just add filename to that group
                if filename not in files:
                    files.append(filename)
                    # Note: values list stays parallel; we append a sentinel
                    # to keep lengths equal. The UI groups by distinct value.
                    values.append(value)
            except ValueError:
                # New value for this key
                files.append(filename)
                values.append(value)


# ===========================================================================
# SECTION 5: Public API
# ===========================================================================

# Files to skip during scanning (the DB file itself, hidden files)
_SKIP_SUFFIXES  = {'.db', '.db-wal', '.db-shm', '.hdf5', '.h5'}
_SKIP_PREFIXES  = {'.'}   # hidden files / macOS resource forks


def scan_folder(folder_path: Path) -> MetaDataDict:
    """
    Scan all files in folder_path and return a MetaDataDict.

    This function is blocking (file I/O).  Call it via::

        loop = asyncio.get_event_loop()
        meta = await loop.run_in_executor(None, scan_folder, folder_path)

    Processing steps per file:
      1. Skip DB / hidden files.
      2. Classify the file (Section 2).
      3. Parse it with the matching parser (Section 3).
      4. Merge results into the shared MetaDataDict (Section 4).

    Files that cannot be parsed are logged at WARNING level and skipped;
    they do not abort the scan.

    Args:
        folder_path: Absolute path to the folder to scan.

    Returns:
        MetaDataDict – may be empty if folder is empty or all files fail.
    """
    meta_dict: MetaDataDict = _empty_meta()

    try:
        all_files = sorted(
            p for p in folder_path.iterdir()
            if p.is_file()
            and p.suffix.lower() not in _SKIP_SUFFIXES
            and not p.name.startswith(tuple(_SKIP_PREFIXES))
        )
    except OSError as e:
        logger.error(f"scan_folder: cannot list {folder_path}: {e}")
        return meta_dict

    logger.info(f"scan_folder: scanning {len(all_files)} files in {folder_path}")

    for file_path in all_files:
        file_class = classify_file(file_path)
        logger.debug(f"  {file_path.name} → {file_class.name}")

        parser = PARSERS.get(file_class, _parse_unknown)
        try:
            parsed = parser(file_path)
        except Exception as e:
            logger.warning(
                f"scan_folder: parser {parser.__name__} failed for "
                f"{file_path.name}: {e}"
            )
            # Fall back to filesystem-only metadata
            try:
                parsed = _parse_filesystem(file_path)
                parsed['parse_error'] = str(e)
            except Exception:
                continue

        _merge_into_dict(meta_dict, file_path.name, parsed)

    logger.info(
        f"scan_folder: done – {len(all_files)} files, "
        f"{len(meta_dict)} distinct metadata keys"
    )
    return meta_dict

