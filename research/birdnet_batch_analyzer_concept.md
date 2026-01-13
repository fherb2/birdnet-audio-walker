# BirdNET Batch Analyzer - Konzept

## 1. Überblick

Dieses Tool analysiert AudioMoth-Aufnahmen in einem Ordner mit BirdNET und speichert die Ergebnisse in einer ODS-Tabelle (LibreOffice Calc).

**Hauptfunktionen:**
- Batch-Verarbeitung aller WAV-Dateien in einem Ordner
- Parallelverarbeitung mit Multiprocessing (1.5x CPU-Cores)
- Segmentierung mit Hann-Window und konfigurierbarem Overlap
- Automatische GPS- und Zeitfilterung für BirdNET
- Mehrsprachige Artennamen (Wissenschaftlich, Deutsch, Tschechisch, Englisch)
- SQLite als Zwischenspeicher, finale Ausgabe als ODS
- Automatische Zeitzonen-Konvertierung (UTC → MEZ/MESZ)

## 2. Systemarchitektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Process                              │
│  - Argument Parsing                                          │
│  - File Discovery & Sorting                                  │
│  - Worker Pool Management (multiprocessing.spawn)           │
│  - Progress Display (alle 2s)                               │
│  - SQLite → ODS Export                                       │
└─────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
      ┌──────────────────┐    ┌──────────────────┐
      │  Worker Process  │    │  Worker Process  │
      │  #1              │    │  #N              │
      │                  │    │                  │
      │ 1. Get Task      │    │ 1. Get Task      │
      │ 2. Load Audio    │    │ 2. Load Audio    │
      │ 3. Apply Window  │    │ 3. Apply Window  │
      │ 4. BirdNET       │    │ 4. BirdNET       │
      │ 5. Write SQLite  │    │ 5. Write SQLite  │
      └──────────────────┘    └──────────────────┘
                │                       │
                └───────────┬───────────┘
                            ▼
                  ┌──────────────────┐
                  │  SQLite Database │
                  │  - detections    │
                  │  - metadata      │
                  └──────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │   ODS Export     │
                  │  - Detektionen   │
                  │  - Metadaten     │
                  └──────────────────┘
```

## 3. Module und Schnittstellen

### 3.1 `main.py` - Hauptprogramm

**Kommandozeile:**
```bash
python main.py <input_folder> --output <output.ods> --confidence <float>
```

**Argumente:**
- `input_folder`: Pfad zum Ordner mit WAV-Dateien (required)
- `--output`, `-o`: Output ODS-Datei (default: `results.ods`)
- `--confidence`, `-c`: Minimum Confidence Threshold (default: `0.25`)

**Ablauf:**
1. Argument Parsing
2. File Discovery (alle `.wav`/`.WAV` Dateien)
3. Metadaten extrahieren (für Sortierung und GPS/Zeit-Filter)
4. Dateien sortieren nach Timestamp (GUANO)
5. Artennamen-Tabelle herunterladen/cachen
6. SQLite-Datenbank initialisieren
7. Worker Pool starten (1.5x CPU-Cores, spawn method)
8. Tasks in Queue einreihen (File + Segmente)
9. Progress-Anzeige (alle 2s aktualisieren)
10. Auf Completion warten
11. SQLite → ODS Export
12. Cleanup

### 3.2 `audiomoth_import.py` - Metadaten-Extraktion

**API:**
```python
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
```

**Implementierung:**
- Nutzt `wave` Modul für Standard-WAV-Parameter
- Parst RIFF-Chunks für GUANO/ICMT Metadaten
- Konvertiert UTC → MEZ/MESZ mit `pytz` oder `zoneinfo`
- Erkennt automatisch Sommer-/Winterzeit

### 3.3 `segmentation.py` - Audio-Segmentierung

**Konfigurierbare Konstanten:**
```python
SEGMENT_LENGTH_SEC = 3.0      # Länge eines Segments
OVERLAP_SEC = 0.7              # Overlap beidseitig
STRIDE_SEC = SEGMENT_LENGTH_SEC - OVERLAP_SEC  # = 2.3s
FADE_LENGTH_SEC = 0.3          # Fade-In/Out Länge (Hann Window)
```

**API:**
```python
def generate_segments(
    total_duration: float,
    segment_length: float = SEGMENT_LENGTH_SEC,
    stride: float = STRIDE_SEC
) -> list[tuple[float, float]]:
    """
    Generate segment boundaries (start, end) in seconds.
    
    Args:
        total_duration: Total audio duration in seconds
        segment_length: Segment length in seconds
        stride: Stride between segments in seconds
        
    Returns:
        List of (start_time, end_time) tuples
    """

def apply_hann_window(
    audio_segment: np.ndarray,
    sample_rate: int,
    fade_length: float = FADE_LENGTH_SEC
) -> np.ndarray:
    """
    Apply Hann window (raised cosine) to audio segment.
    
    Fade-In: 0.0s - fade_length
    Constant: fade_length - (segment_length - fade_length)
    Fade-Out: (segment_length - fade_length) - segment_length
    
    Args:
        audio_segment: Audio data (1D numpy array)
        sample_rate: Sample rate in Hz
        fade_length: Length of fade in/out in seconds
        
    Returns:
        Windowed audio segment
    """

def load_audio_segment(
    wav_path: str,
    start_time: float,
    end_time: float,
    apply_window: bool = True
) -> np.ndarray:
    """
    Load and window a segment from WAV file.
    
    Args:
        wav_path: Path to WAV file
        start_time: Start time in seconds
        end_time: End time in seconds
        apply_window: Whether to apply Hann window
        
    Returns:
        Audio segment as numpy array
    """
```

### 3.4 `species_translation.py` - Artennamen-Übersetzung

**API:**
```python
def download_species_table(cache_dir: str = "/tmp") -> pd.DataFrame:
    """
    Download species name translation table from karlincam.cz.
    
    Caches result in cache_dir/species_names.csv
    
    Args:
        cache_dir: Directory for caching
        
    Returns:
        DataFrame with columns: ['scientific', 'en', 'de', 'cs']
    """

def translate_species_name(
    scientific_name: str,
    translation_table: pd.DataFrame
) -> dict:
    """
    Translate scientific name to German and Czech.
    
    Args:
        scientific_name: Scientific species name (e.g., "Parus major")
        translation_table: Translation DataFrame
        
    Returns:
        dict with keys: 'scientific', 'en', 'de', 'cs'
        If not found, 'en', 'de', 'cs' are set to scientific_name
    """
```

**Implementierung:**
- Nutzt `requests` + `BeautifulSoup` zum Scrapen der HTML-Tabelle
- Parst Tabelle mit Spalten: Scientific name, en, de, cs
- Speichert als CSV in `/tmp/species_names.csv`
- Bei erneutem Start: Lädt aus Cache, außer älter als 7 Tage

### 3.5 `birdnet_analyzer.py` - BirdNET Wrapper

**API:**
```python
def analyze_segment(
    audio_segment: np.ndarray,
    sample_rate: int,
    latitude: float,
    longitude: float,
    timestamp: datetime,
    min_confidence: float = 0.25
) -> list[dict]:
    """
    Analyze audio segment with BirdNET.
    
    Args:
        audio_segment: Audio data
        sample_rate: Sample rate in Hz
        latitude: GPS latitude
        longitude: GPS longitude
        timestamp: Recording timestamp (for week calculation)
        min_confidence: Minimum confidence threshold
        
    Returns:
        List of detections, each dict with:
        - 'scientific_name': str
        - 'common_name': str (English)
        - 'confidence': float
        - 'start_time': float (relative to segment, in seconds)
        - 'end_time': float (relative to segment, in seconds)
    """
```

**Implementierung:**
- Lädt BirdNET Model einmal beim Prozess-Start
- Berechnet Kalenderwoche aus Timestamp
- Nutzt GPS + Kalenderwoche für Species-Filter
- Gibt alle Detektionen mit Confidence >= min_confidence zurück

### 3.6 `worker.py` - Worker-Prozess

**API:**
```python
def worker_main(
    task_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    db_path: str,
    translation_table: pd.DataFrame,
    min_confidence: float
):
    """
    Worker process main function.
    
    Args:
        task_queue: Queue with tasks (file_path, segment_start, segment_end, metadata)
        result_queue: Queue for progress updates
        db_path: Path to SQLite database
        translation_table: Species translation table
        min_confidence: Minimum confidence threshold
    """
```

**Ablauf:**
1. Initialisiere BirdNET Model (einmal pro Worker)
2. Loop:
   - Hole Task aus Queue
   - Lade Audio-Segment mit Window
   - Analysiere mit BirdNET
   - Übersetze Artennamen
   - Schreibe Detektionen in SQLite (mit Lock)
   - Sende Progress-Update an Main
3. Exit bei Poison-Pill

### 3.7 `database.py` - SQLite-Verwaltung

**Schema:**
```sql
CREATE TABLE metadata (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    timestamp_local TEXT NOT NULL,
    timezone TEXT NOT NULL,
    serial TEXT,
    gps_lat REAL,
    gps_lon REAL,
    sample_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    duration_seconds REAL,
    temperature_c REAL,
    battery_voltage REAL,
    gain TEXT,
    firmware TEXT
);

CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    segment_start_utc TEXT NOT NULL,
    segment_start_local TEXT NOT NULL,
    segment_end_utc TEXT NOT NULL,
    segment_end_local TEXT NOT NULL,
    timezone TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    name_en TEXT,
    name_de TEXT,
    name_cs TEXT,
    confidence REAL NOT NULL,
    FOREIGN KEY (filename) REFERENCES metadata(filename)
);

CREATE INDEX idx_detections_time ON detections(segment_start_local);
CREATE INDEX idx_detections_species ON detections(scientific_name);
```

**API:**
```python
def init_database(db_path: str):
    """Initialize SQLite database with schema."""

def insert_metadata(db_path: str, metadata: dict):
    """Insert file metadata."""

def insert_detection(
    db_path: str,
    filename: str,
    segment_start_utc: datetime,
    segment_start_local: datetime,
    segment_end_utc: datetime,
    segment_end_local: datetime,
    timezone: str,
    scientific_name: str,
    name_en: str,
    name_de: str,
    name_cs: str,
    confidence: float
):
    """Insert detection with file locking."""

def export_to_ods(db_path: str, output_path: str):
    """Export SQLite data to ODS file with two sheets."""
```

### 3.8 `progress.py` - Progress-Anzeige

**API:**
```python
class ProgressDisplay:
    def __init__(self, total_segments: int, num_workers: int):
        """Initialize progress display."""
    
    def update(self, completed_segments: int, current_file: str):
        """Update display (called every 2s)."""
    
    def finish(self):
        """Display final statistics."""
```

**Anzeige (Beispiel):**
```
================================================================================
BirdNET Batch Analyzer - Progress
================================================================================
Workers:           12 / 12 active
Segments:          1547 / 8342 (18.5%)
Current File:      249C600363FA5E80_20250416_164632.WAV
Segments/sec:      5.2
ETA:               23m 15s
================================================================================
```

## 4. Datenfluss

```
1. Main Process
   ├─> Entdecke alle WAV-Dateien
   ├─> Extrahiere Metadaten (audiomoth_import)
   ├─> Sortiere nach Timestamp
   ├─> Berechne alle Segmente (segmentation)
   └─> Erstelle Task-Queue: (file, segment_start, segment_end, metadata)

2. Worker Processes (parallel)
   ├─> Hole Task aus Queue
   ├─> Lade Audio-Segment mit Hann-Window
   ├─> Analysiere mit BirdNET (GPS + Kalenderwoche)
   ├─> Übersetze Artennamen
   ├─> Schreibe in SQLite (atomic, mit Lock)
   └─> Zurück zu Schritt 1

3. Main Process (nach Completion)
   ├─> Lese SQLite
   ├─> Erstelle ODS mit zwei Sheets
   │   ├─> Sheet 1: Detektionen (sortiert nach Zeit)
   │   └─> Sheet 2: Metadaten (ein Eintrag pro File)
   └─> Cleanup
```

## 5. Parallelisierungsstrategie

### Worker-Pool
- **Anzahl Workers**: `int(multiprocessing.cpu_count() * 1.5)`
- **Spawn-Methode**: `multiprocessing.set_start_method('spawn')`
- **Grund für Spawn**: Saubere Prozess-Isolation, keine Fork-Probleme mit TensorFlow

### Task-Verteilung
- **Task-Granularität**: Ein Task = Ein 3s-Segment
- **Queue-Reihenfolge**: Sortiert nach Dateiname und dann Segment-Start (chronologisch)
- **Vorteil**: Tabelle füllt sich in chronologischer Reihenfolge

### SQLite-Locking
- **Write-Lock**: `fcntl.flock()` auf Unix-Systemen
- **Prozedur**:
  1. Worker öffnet DB-Connection
  2. Nimmt Lock
  3. INSERT INTO detections
  4. COMMIT
  5. Gibt Lock frei
- **Timeout**: 10 Sekunden, dann Retry

## 6. ODS-Tabellenstruktur

### Sheet 1: "Detektionen"

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| Dateiname | Text | Original WAV-Dateiname |
| Segment Start (UTC) | DateTime | Segment-Start in UTC |
| Segment Start (Lokal) | DateTime | Segment-Start in MEZ/MESZ |
| Segment Ende (UTC) | DateTime | Segment-Ende in UTC |
| Segment Ende (Lokal) | DateTime | Segment-Ende in MEZ/MESZ |
| Zeitzone | Text | "MEZ" oder "MESZ" |
| Wissenschaftlicher Name | Text | Scientific name |
| Englischer Name | Text | English common name |
| Deutscher Name | Text | German name |
| Tschechischer Name | Text | Czech name |
| Konfidenz | Zahl | Confidence (0.0 - 1.0) |

**Format DateTime**: ISO 8601, z.B. `2025-04-16 18:46:35` (gut lesbar und maschinell parsbar)

### Sheet 2: "Metadaten"

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| Dateiname | Text | Original WAV-Dateiname |
| Zeitstempel (UTC) | DateTime | Aufnahme-Start UTC |
| Zeitstempel (Lokal) | DateTime | Aufnahme-Start MEZ/MESZ |
| Zeitzone | Text | "MEZ" oder "MESZ" |
| Geräte-ID | Text | AudioMoth Serial |
| GPS Latitude | Zahl | GPS Breitengrad |
| GPS Longitude | Zahl | GPS Längengrad |
| Sample Rate | Zahl | Sample Rate (Hz) |
| Kanäle | Zahl | Anzahl Kanäle |
| Bit-Tiefe | Zahl | Bit Depth |
| Dauer | Zahl | Dauer in Sekunden |
| Temperatur | Zahl | Temperatur (°C) |
| Batteriespannung | Zahl | Battery Voltage (V) |
| Verstärkung | Text | Gain Setting |
| Firmware | Text | Firmware Version |

## 7. Konfiguration

### Konstanten in `config.py`
```python
# Segmentation
SEGMENT_LENGTH_SEC = 3.0
OVERLAP_SEC = 0.7
STRIDE_SEC = SEGMENT_LENGTH_SEC - OVERLAP_SEC  # 2.3s
FADE_LENGTH_SEC = 0.3

# Multiprocessing
WORKER_MULTIPLIER = 1.5  # CPU cores * 1.5

# BirdNET
DEFAULT_CONFIDENCE = 0.25

# Species Translation
SPECIES_CACHE_DIR = "/tmp"
SPECIES_CACHE_MAX_AGE_DAYS = 7
SPECIES_TABLE_URL = "https://www.karlincam.cz/de_de/und-sonst-noch/artennamen-uebersetzen/vogelnamen-wissenschaftlich-sortiert"

# Database
SQLITE_LOCK_TIMEOUT = 10.0  # seconds

# Progress
PROGRESS_UPDATE_INTERVAL = 2.0  # seconds
```

## 8. Error-Handling

### Fehlerbehandlung auf Worker-Ebene

**Wenn ein Segment fehlschlägt:**
1. Logge Error mit `loguru` (Dateiname, Segment-Start/Ende, Exception)
2. **Keine** Detektionen für dieses Segment in SQLite eintragen
3. Worker macht mit nächstem Task weiter

**Fehler-Kategorien:**
- Audio-Lade-Fehler (korrupte Datei, falsches Format)
- BirdNET-Analyse-Fehler (Model-Fehler, Out-of-Memory)
- SQLite-Write-Fehler (Lock-Timeout, Disk-Full)

### Fehlerbehandlung auf Main-Ebene

**Wenn Metadaten-Extraktion fehlschlägt:**
1. Logge Warning mit Dateiname
2. Überspringe diese Datei komplett
3. Fahre mit nächster Datei fort

**Wenn Artennamen-Download fehlschlägt:**
1. Versuche Cache zu laden
2. Wenn kein Cache: Nur wissenschaftliche Namen verwenden (kein Abbruch)

## 9. Dependencies

```
# requirements.txt
birdnet>=0.2.11         # Offizielles BirdNET-Paket
numpy>=1.24.0
scipy>=1.10.0           # Für Audio-Processing
soundfile>=0.12.0       # Audio-File-Loading (libsndfile wrapper)
loguru>=0.7.0           # Logging
pyexcel-ods3>=0.6.0     # ODS Export
requests>=2.31.0        # HTTP für Species-Download
beautifulsoup4>=4.12.0  # HTML Parsing
pytz                    # oder: zoneinfo (Python 3.9+) für Zeitzonen
pandas>=2.0.0           # Optional, für einfacheres Daten-Handling
tqdm>=4.66.0            # Optional, falls komplexere Progress-Bar gewünscht
```

## 10. Ordnerstruktur

```
birdnet_batch_analyzer/
├── main.py                    # Hauptprogramm
├── config.py                  # Konfigurationskonstanten
├── audiomoth_import.py        # Metadaten-Extraktion
├── segmentation.py            # Audio-Segmentierung & Windowing
├── species_translation.py     # Artennamen-Download & Übersetzung
├── birdnet_analyzer.py        # BirdNET Wrapper
├── worker.py                  # Worker-Prozess
├── database.py                # SQLite-Verwaltung
├── progress.py                # Progress-Anzeige
├── requirements.txt           # Python Dependencies
└── README.md                  # Dokumentation
```

## 11. Verwendungsbeispiel

```bash
# Installation
pip install -r requirements.txt

# Einfachste Verwendung
python main.py /path/to/audiomoth/recordings

# Mit Optionen
python main.py /path/to/audiomoth/recordings \
    --output /path/to/results.ods \
    --confidence 0.35
```

## 12. Zeitschätzung

**Für die Beispieldatei** (268 Minuten Audio):
- Segmente: ~7000 (bei 2.3s Stride)
- Mit 12 Workern @ 5 Segmente/Sekunde: ~10-15 Minuten Verarbeitungszeit

## 13. Offene Punkte / Erweiterungen (für später)

- [ ] Support für andere Recorder-Typen (nicht nur AudioMoth)
- [ ] GPU-Unterstützung für BirdNET (falls verfügbar)
- [ ] Merge-Strategie für überlappende Detektionen
- [ ] Export in andere Formate (CSV, Parquet, etc.)
- [ ] Visualisierung der Ergebnisse
- [ ] Integration mit eBird / Observation Databases

---

**Version:** 1.0  
**Datum:** 2025-01-11  
**Status:** Konzeptphase abgeschlossen, bereit für Implementierung
