# BirdNET Walker & Play - Vollständige Projekt-Dokumentation

# OUTDATED

Now all parts merged into a GUI suported birdnet-copter.


Dieses Dokument dienst insbesondere als Kontext-Initialisierung mit Claude.ai .

## 1. Projekt-Übersicht

### 1.1 Zweck und Zielgruppe

**BirdNET Walker & Play** ist ein Python-basiertes System zur automatisierten Analyse und Auswertung von Vogelstimmen-Aufnahmen. Es richtet sich an:

- **Biologen und Ornithologen** für Feldforschung
- **Professionelle Monitoring-Projekte** für Territorial-Überwachung
- **Ambitionierte Hobby-Vogelbeobachter** mit semi-professionellem Anspruch

### 1.2 Hauptfunktionalität

Das Projekt besteht aus zwei Hauptkomponenten:

1. **BirdNET Walker** - Batch-Analyse-Engine
   - Analysiert große Mengen AudioMoth-Aufnahmen mit BirdNET
   - GPU-beschleunigt (CUDA erforderlich)
   - Erstellt SQLite-Datenbanken pro Ordner
   - Performance: RTX A6000 @ ~20s pro 6h-Aufnahme (vs. CPU @ 12-30h)
   - **Embedding-Extraktion:** Optional 1024-dimensionale Feature-Vektoren
   - Speicherung in separater HDF5-Datei (effizient, komprimiert)
   - Verwendung: Clustering, Ähnlichkeitssuche, False-Positive-Erkennung

2. **BirdNET Play** - Audio-Playback & Web-Interface
   - Streamlit-basierte Web-UI für komfortable Durchsicht
   - Audio-Playback mit TTS-Ansagen
   - Umfangreiche Filter- und Sortierfunktionen
   - Species-Übersicht mit intelligenter Sortierung

### 1.3 Typischer Workflow

```
AudioMoth im Feld
    ↓
Aufnahmen (typisch: 500h+ pro Gerät, ~2GB pro 6h-File)
    ↓
Analyse mit birdnet-walker (GPU/CUDA)
  ├─> Detections (Confidence, Species, Zeit)
  └─> Embeddings (optional, 1024-dim Vektoren)
    ↓
SQLite-Datenbank pro Ordner
  ├─> detections (mit embedding_idx)
  └─> metadata, processing_status, analysis_config
    ↓
HDF5-Datei pro Ordner (falls Embeddings aktiviert)
  └─> birdnet_embeddings.h5 (komprimierte Vektoren)
    ↓
Durchsicht mit birdnet-play (Streamlit)
    ↓
Identifikation von Besonderheiten/seltenen Arten
  + Clustering & Ähnlichkeitsanalyse (Embeddings)
```

### 1.4 Deployment

- **Primär:** Docker-basiert (beste Integration mit VSCode)
- **Walker:** CUDA-abhängig, nur im Docker Image nutzbar
- **Play:** Theoretisch auch ohne Docker nutzbar (Python-Env konfigurieren)
- **Plattform:** Linux/macOS bevorzugt, Windows via Docker

**Hinweis:** Das Projekt ist noch nicht auf optimale User-Experience für Einsteiger ausgelegt. Docker + VSCode ist der empfohlene Weg.

---

## 2. Technologie-Stack

### 2.1 Core Technologies

**Sprache & Version:**
- Python 3.12+ (kompatibel bis 3.13)
- Poetry 2.2.1+ für Dependency-Management

**Audio & AI:**
- BirdNET 0.2.x (TensorFlow + CUDA für GPU-Beschleunigung)
- h5py für HDF5-Speicherung (Embeddings)
- numpy für Array-Operationen
- edge-tts für Text-to-Speech
- pydub für Audio-Manipulation
- sounddevice/soundfile für Audio-I/O
- pedalboard für Audio-Kompression
- pyloudnorm für LUFS-Normalisierung

**Datenbank & Daten:**
- SQLite mit WAL-Mode (Write-Ahead Logging)
- Pandas für Datenverarbeitung

**Web-Interface:**
- Streamlit 1.53.0+
- streamlit-aggrid für interaktive Tabellen
- streamlit-searchbox für Species-Autocomplete
- Altair für interaktive Visualisierungen (Heatmap)

**Utilities:**
- Loguru für strukturiertes Logging
- num2words für Zahlen-zu-Wörter (TTS)
- requests + BeautifulSoup für Web-Scraping (tschechische Artennamen)

### 2.2 Hardware-Anforderungen

**Für birdnet-walker:**
- CUDA-fähige GPU (essentiell!)
- Beispiel-Performance: RTX A6000 @ 60s/6h-File (ohne Embeddings)
- Mit Embeddings: ~40s/6h-File (2x längere Laufzeit)
- CPU-Fallback: 2-5x Realtime (nicht praktikabel für große Datenmengen)

**Für birdnet-play:**
- Keine GPU erforderlich
- Standard-Desktop/Laptop ausreichend

---

## 3. Projektstruktur

### 3.1 Verzeichnis-Layout

```
birdnet-walker/
├── pyproject.toml              # Poetry-Konfiguration, Dependencies
├── README.md                   # Projekt-Übersicht
├── readme_2.md                 # Erweiterte technische Dokumentation
├── full_project_context.md     # Diese Datei - Vollständige Dokumentation
│
└── source/                     # Alle Python-Module
    │
    ├── shared/                 # Gemeinsame Funktionen für alle Tools
    │   ├── __init__.py
    │   ├── db_queries.py       # SQLite-Query-Funktionen (read-only)
    │   ├── audio_extract.py    # Audio-Snippet-Extraktion
    │   └── streamlit_utils.py  # Streamlit-Helper (DB-Suche, Init)
    │
    ├── birdnet_walker/         # Batch-Analyse-Engine
    │   ├── __init__.py
    │   ├── __main__.py         # Entry point "python -m birdnet_walker"
    │   ├── main.py             # Hauptlogik, Orchestrierung
    │   ├── config.py           # Zentrale Konfigurationskonstanten
    │   ├── database.py         # SQLite Schema-Creation & Write-Ops
    │   ├── birdnet_analyzer.py # BirdNET-Wrapper
    │   ├── audiomoth_import.py # Metadaten-Extraktion aus WAV
    │   ├── species_translation.py  # Tschechische Namen (Web-Scraping)
    │   ├── birdnet_labels.py   # Mehrsprachige Namen von BirdNET
    │   └── progress.py         # Fortschrittsanzeige
    │
    └── birdnet_play/           # Audio-Playback & Web-Interface
        ├── __init__.py
        ├── __main__.py         # Entry point "python -m birdnet_play"
        ├── streamlit_app.py    # Streamlit Entry Point (Auto-Redirect)
        ├── cli.py              # CLI-Interface & Argument-Parsing
        ├── player.py           # Audio-Engine (Extraktion, Kombination, Processing)
        ├── tts.py              # TTS-Generierung (edge-tts)
        ├── filters.py          # Filter-Logik & Query-Builder
        ├── keyboard_control.py # Tastatur-Steuerung für CLI
        │
        └── pages/              # Streamlit Multi-Page App
            ├── 1_database_overview.py  # DB-Auswahl, Metadata, Species-Liste
            └── 2_audio_player.py       # Filter, Audio-Player, Export
        └── 3_heatmap_alaltair.py   # Activity Heatmap (Altair-Version)

```

### 3.2 Entry Points (pyproject.toml)

```toml
[tool.poetry.scripts]
birdnet-walker = "birdnet_walker.main:main"  # Batch-Analyse
birdnet-play = "birdnet_play.cli:main"       # Playback (CLI oder --ui)
```

**Neue Dependencies (ab Version 24.1.26):**
```toml
[tool.poetry.dependencies]
# ... existing dependencies ...
streamlit-searchbox = "^0.1.0"  # Species autocomplete
altair = "^5.0.0"                # Heatmap visualization
```

**Verwendung:**
```bash
# Walker: Analyse starten (ohne Embeddings)
poetry run birdnet-walker /path/to/recordings --recursive

# Walker: Analyse mit Embeddings (empfohlen für Clustering)
poetry run birdnet-walker /path/to/recordings --recursive --extract-embeddings

# Play: Streamlit UI
poetry run birdnet-play /path/to/db.db --ui

# Play: CLI-Modus
poetry run birdnet-play /path/to/db.db --species "Parus major"
```

---

## 4. Datenbank-Schema

### 4.1 Datenbank-Organisation

**Prinzip:** Eine SQLite-Datenbank pro Ordner mit WAV-Dateien.

**Dateiname:** `birdnet_analysis.db` (liegt im gleichen Ordner wie die WAV-Files)

**Beispiel-Struktur:**
```
recordings/
├── site_A/
│   ├── birdnet_analysis.db
│   ├── birdnet_embeddings.h5 
│   ├── 20250416_060000.WAV
│   └── 20250416_120000.WAV
└── site_B/
    ├── birdnet_analysis.db
    ├── birdnet_embeddings.h5
    └── ...

**Vorteile:**
- Unabhängige Verwaltung pro Standort/Session
- Einfaches Kopieren/Archivieren
- Parallele Verarbeitung möglich

**HDF5-Datei:**
- `birdnet_embeddings.h5` liegt im gleichen Ordner wie die DB
- Enthält nur Embeddings für Detections (nicht alle Segmente)
- Komprimiert mit gzip (Level 4), dtype float32
- Chunk-Size: 1000 Zeilen für optimalen Zugriff

### 4.2 Tabellen-Schema

#### **Tabelle: `metadata`**
Speichert File-Metadaten der AudioMoth-Aufnahmen (ein Eintrag pro Datei).

```sql
CREATE TABLE metadata (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    timestamp_utc TEXT NOT NULL,        -- ISO-Format
    timestamp_local TEXT NOT NULL,      -- MEZ/MESZ konvertiert
    timezone TEXT NOT NULL,             -- 'MEZ' oder 'MESZ'
    serial TEXT,                        -- AudioMoth Seriennummer
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
)
```

#### **Tabelle: `detections`**
Haupttabelle mit allen BirdNET-Erkennungen (ein Eintrag pro 3-Sekunden-Segment).

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    segment_start_utc TEXT NOT NULL,
    segment_start_local TEXT NOT NULL,
    segment_end_utc TEXT NOT NULL,
    segment_end_local TEXT NOT NULL,
    timezone TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    local_name TEXT,                    -- Name in gewählter Sprache (--lang)
    name_cs TEXT,                       -- Tschechischer Name
    confidence REAL NOT NULL,           -- 0.0-1.0
    embedding_idx INTEGER,              -- NEU: Index in HDF5 (oder NULL)
    FOREIGN KEY (filename) REFERENCES metadata(filename)
)

-- Indizes für Performance
CREATE INDEX idx_detections_segment_start ON detections(segment_start_local);
CREATE INDEX idx_detections_species ON detections(scientific_name);
CREATE INDEX idx_detections_filename ON detections(filename);
```

**Zeitstempel-Berechnung:**
```
segment_start_utc = file_timestamp_utc + detection_start_time
```
wobei `detection_start_time` der Offset in Sekunden vom Datei-Anfang ist (von BirdNET geliefert).

**Embedding-Index:**

embedding_idx = kompakter Index in birdnet_embeddings.h5

- NULL wenn --extract-embeddings nicht verwendet
- Kompakte Nummerierung (0, 1, 2, ...) ohne Lücken
- Referenziert Zeile in HDF5: embeddings[embedding_idx]

#### **Tabelle: `processing_status`**
Tracking für Resume-Funktionalität (ermöglicht Neustart nach Absturz).

```sql
CREATE TABLE processing_status (
    filename TEXT PRIMARY KEY,
    status TEXT NOT NULL,              -- 'pending', 'processing', 'completed', 'failed'
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY (filename) REFERENCES metadata(filename)
)
```

**Status-Übergänge:**
1. Bei `insert_metadata()`: Status → 'pending'
2. Vor BirdNET-Analyse: Status → 'processing'
3. Nach erfolgreicher Analyse: Status → 'completed'
4. Bei Fehler: Status → 'failed'

#### **Tabelle: `analysis_config`**
Speichert Analyse-Parameter (neu in birdnet-play).

```sql
CREATE TABLE IF NOT EXISTS analysis_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)

-- Beispiel-Einträge:
-- ('local_name_shortcut', 'de')
-- ('confidence_threshold', '0.09')
-- ('created_at', '2025-01-17T10:30:00Z')
-- ('user_comment', 'Site A - Spring 2025')
```

#### **Tabelle: `species_list`**
Cached Species-Übersicht für schnellen Zugriff (neu in birdnet-play).

```sql
CREATE TABLE IF NOT EXISTS species_list (
    scientific_name TEXT PRIMARY KEY,
    local_name TEXT,
    name_cs TEXT,
    count_high INTEGER,     -- Detections mit confidence >= 0.7
    count_low INTEGER,      -- Detections mit confidence < 0.7
    score REAL              -- SUM(confidence^4) für Sortierung
)
```

**Score-Formel:** `score = SUM(confidence^4)`
- Verstärkt hohe Confidence-Werte exponentiell
- 10x @ 0.9 conf → score ≈ 6.56
- 100x @ 0.3 conf → score ≈ 0.81
- → Qualität schlägt Quantität


### 4.2 HDF5-Struktur (Embeddings)

**Datei:** `birdnet_embeddings.h5` (im gleichen Ordner wie SQLite-DB)

**Dataset:** `embeddings`
- Shape: (n_detections, 1024)
- Dtype: float32
- Compression: gzip level 4
- Chunk size: (1000, 1024)

**Eigenschaften:**
- Nur Embeddings für tatsächliche Detections (nicht alle Segmente!)
- Kompakte Indizierung: Zeile 0-499 für 500 Detections
- Resizable Dataset (maxshape=(None, 1024))

**Zugriff:**
```python
import h5py
import sqlite3

# 1. Embedding-Index aus SQLite laden
conn = sqlite3.connect('birdnet_analysis.db')
cursor = conn.cursor()
cursor.execute("SELECT embedding_idx FROM detections WHERE id = ?", (detection_id,))
embedding_idx = cursor.fetchone()[0]
conn.close()

# 2. Embedding aus HDF5 laden
with h5py.File('birdnet_embeddings.h5', 'r') as f:
    embedding = f['embeddings'][embedding_idx]  # Shape: (1024,)
```

**Konsistenz-Garantien:**
- Gleiche Zeitfenster in analyze_file() und extract_embeddings()
- Detection-Zeit == Segment-Zeit → Exakte Zuordnung
- Keine Lücken in embedding_idx (kompakte Nummerierung)

### 4.3 Datenbank-Zugriff

**Schreib-Zugriff:** Nur `birdnet_walker/database.py`
**Lese-Zugriff:** `shared/db_queries.py` (für alle Tools)

**WAL-Mode:** Alle Verbindungen nutzen `PRAGMA journal_mode=WAL` für bessere Concurrency.

---

## 5. Module-Beschreibungen

### 5.1 shared/ - Gemeinsame Funktionen

#### **db_queries.py**
**Zweck:** Zentrale Read-Only-Zugriffsfunktionen für SQLite-Datenbanken.

**Wichtige Konstanten:**
```python
CONFIDENCE_THRESHOLD_HIGH = 0.7  # Schwelle für "gute" Detections
```

**Hauptfunktionen:**
- `get_db_connection()` - Öffnet DB mit WAL-Mode & Row-Factory
- `get_analysis_config(key)` - Liest Config-Werte
- `set_analysis_config(key, value)` - Schreibt Config-Werte
- `query_detections(...)` - Haupt-Query mit allen Filtern & Sortierung
- `get_detection_by_id()` - Lädt einzelne Detection
- `get_metadata_by_filename()` - Lädt File-Metadaten
- `get_all_metadata()` - Lädt alle Files (für Overview-Page)
- `get_recording_date_range()` - Min/Max Datum der Aufnahmen
- `species_list_exists()` - Prüft ob species_list Tabelle existiert
- `create_species_list_table()` - Erstellt/aktualisiert species_list
- `get_species_count()` - Anzahl Species in Liste
- `get_species_list_with_counts()` - Lädt vollständige Species-Liste
- `format_score_with_two_significant_digits()` - Score-Formatierung
- `format_detections_column()` - Formatiert Detections-Spalte
- `search_species_in_list()` - Autocomplete-Suche für Species (für streamlit_searchbox)


**Filter-Parameter für `query_detections()`:**
- `species` - Teilstring-Suche in scientific/local/Czech name
- `date_from/date_to` - Datum-Range
- `time_range` - Tuple (start_time, end_time) für Tageszeit-Filter (kombiniert mit date_from/date_to)
- `time_range` - Tuple (start_time, end_time) für Tageszeit
- `min_confidence` - Minimum Confidence
- `limit/offset` - Pagination
- `sort_by` - "time", "confidence", "id"
- `sort_order` - "asc", "desc"

#### **audio_extract.py**
**Zweck:** Audio-Snippet-Extraktion aus WAV-Dateien.

**Hauptfunktionen:**
- `calculate_snippet_offsets(detection, pm_seconds)` - Berechnet Start/End mit PM-Buffer
- `extract_snippet(wav_path, start, end)` - Extrahiert Audio → **Gibt Tuple zurück: (audio_data, sample_rate)**

**PM-Buffer (Plus/Minus):** Erweitert 3s-Segment um X Sekunden vor/nach, automatisch geclippt an File-Grenzen.

#### **streamlit_utils.py**
**Zweck:** Utility-Funktionen für Streamlit-Apps.

**Hauptfunktionen:**
- `find_databases_recursive(root_path)` - Findet alle birdnet_analysis.db Files
- `initialize_session_state_from_args()` - Init Session State aus CLI-Args

### 5.2 birdnet_walker/ - Batch-Analyse-Engine

**Hinweis:** Diese Module sind aus der Dokumentation bekannt, aber Code liegt nicht vor. Sie sind für Änderungen an birdnet-play nicht relevant, werden hier nur der Vollständigkeit halber erwähnt.

**Hauptmodule:**
- `main.py` - Orchestrierung, Multiprocessing
- `config.py` - Zentrale Konstanten (BirdNET-Parameter, HDF5-Config, Pfade)
- `database.py` - Schema-Creation, Write-Operations
- `birdnet_analyzer.py` - BirdNET-Wrapper
- `audiomoth_import.py` - GUANO-Metadata-Parsing
- `species_translation.py` - Tschechische Namen von karlincam.cz
- `birdnet_labels.py` - Mehrsprachige Namen aus BirdNET-Labels
- `progress.py` - Konsolen-Progress-Bar

**Wichtige Config-Konstanten (config.py):**
```python
# Embedding Extraction
EXTRACT_EMBEDDINGS_DEFAULT = True       # Default für --extract-embeddings
EMBEDDING_DIMENSIONS = 1024             # BirdNET v2.4 embedding size
SEGMENT_DURATION_S = 3.0                # Segment-Länge (fix bei BirdNET)
OVERLAP_DURATION_S = 0.75               # Overlap zwischen Segmenten

# HDF5 Storage
HDF5_FILENAME = "birdnet_embeddings.h5"
HDF5_DATASET_NAME = "embeddings"
HDF5_DTYPE = 'float32'
HDF5_COMPRESSION = 'gzip'
HDF5_COMPRESSION_LEVEL = 4
HDF5_CHUNK_SIZE = 1000
```

**Wichtige Funktionen in birdnet_analyzer.py:**
- `extract_embeddings()` - Extrahiert 1024-dim Vektoren für alle Segmente
- `calculate_segment_times()` - Berechnet Zeitfenster mit korrektem Overlap
- `find_needed_segments()` - Findet Segmente mit Detections (Zeit-Match)
- `filter_and_write_embeddings()` - Filtert und schreibt nur benötigte Embeddings
- `match_embeddings_to_detections()` - Ordnet Embeddings zu via exakte Zeit
- `create_or_open_hdf5()` - Erstellt/öffnet HDF5-Datei mit korrektem Schema
- `write_embeddings_to_hdf5()` - Schreibt Embeddings und gibt Start-Index zurück

**Wichtige Funktionen in database.py:**
- `get_hdf5_path()` - Ermittelt HDF5-Pfad aus DB-Pfad




### 5.3 birdnet_play/ - Audio-Playback & Web-Interface

#### **streamlit_app.py**
**Zweck:** Entry Point für Streamlit Multi-Page App.

**Funktionalität:**
- Initialisiert Session State aus CLI-Args
- Auto-Redirect zu `pages/1_database_overview.py`

**Aufruf:** `streamlit run streamlit_app.py -- /path/to/db_or_folder`

#### **cli.py**
**Zweck:** Command-Line-Interface für Playback & Export.

**Modes:**
- **`--ui`:** Startet Streamlit (ruft `streamlit run streamlit_app.py` auf)
- **Standard:** CLI-Playback mit Tastatur-Steuerung

**Wichtige CLI-Optionen:**
- `--detection-id ID` - Einzelne Detection
- `--species NAME` - Filter
- `--date YYYY-MM-DD` - Datum-Filter
- `--time HH:MM-HH:MM` - Zeit-Filter
- `--min-confidence 0.0-1.0` - Confidence-Filter
- `--limit N` - Max Anzahl
- `--pm SECONDS` - PM-Buffer (Audio Frame Duration)
- `--sci` - Wissenschaftliche Namen für TTS
- `--export DIR` - Export statt Playback

**CLI-Playback-Keys:**
- SPACE: Pause/Replay
- ← →: Previous/Next
- q: Quit

#### **player.py**
**Zweck:** Audio-Engine - Extraktion, Kombination, Processing.

**Klasse `AudioPlayer`:**

**Hauptmethoden:**
- `prepare_detection_audio(...)` - Kombiniert Audio für WAV-Export
- `prepare_detection_audio_web(...)` - Kombiniert Audio für Web (MP3)
- `prepare_detection_audio_simple(...)` - Einfaches Audio ohne TTS (für Heatmap-Dialog)
- `_get_announcement_text(...)` - Generiert TTS-Text basierend auf Optionen
- `_process_audio_frame(...)` - Audio-Processing-Pipeline

**Audio-Processing-Pipeline (in `_process_audio_frame()`):**
```
1. Fade-in (0.5s) + Fade-out (0.5s)
   ↓
2. LUFS-Normalisierung (Target: -16 LUFS)
   ↓
3. Kompressor (Threshold: -20dB, Ratio: 4:1)
   ↓
4. Clipping-Schutz
```

**Audio-Kombination:**
```
1s Pause → Audio-Frame → TTS-Ansage
```

**Wichtige Konstanten (oben in player.py):**
```python
TARGET_LUFS = -16.0              # Ziel-Lautstärke
FADE_DURATION_MS = 500           # Fade-Dauer
COMPRESSOR_THRESHOLD_DB = -20.0
COMPRESSOR_RATIO = 4.0
```

**Audio-Options Dict:**
```python
audio_options = {
    'say_audio_number': bool,      # "Audio 1"
    'say_id': bool,                # "ID 12345"
    'say_confidence': bool,        # "87 Prozent"
    'bird_name_option': str,       # 'none', 'local', 'scientific'
    'speech_speed': float,         # 0.5-2.0
    'speech_loudness': int         # -10 bis +4 dB
}
```

**Export-Funktionen:**
- `export_detections()` - WAV-Export
- `export_detections_mp3()` - MP3-Export

#### **tts.py**
**Zweck:** Text-to-Speech-Generierung mit edge-tts.

**Voice-Mapping:**
```python
VOICES = {
    'de': 'de-DE-KatjaNeural',
    'en': 'en-US-JennyNeural',
    'cs': 'cs-CZ-VlastaNeural',
    # ...
}
```

**Hauptfunktion:**
```python
generate_tts(text, language_code, speed=1.0, loudness_db=0) -> np.ndarray
```

**Features:**
- Speed-Control via SSML (`<prosody rate="...">`)
- Loudness-Adjustment via pydub (`audio + loudness_db`)
- Output: 48kHz, mono, int16

**Stimmen-Logik:**
- Wissenschaftliche Namen → IMMER deutsche Stimme
- Lokale Namen → Stimme passend zu `language_code`

#### **filters.py**
**Zweck:** Filter-Logik & Query-Builder.

**Klasse `DetectionFilter`:**

**Attribute:**
```python
@dataclass
class DetectionFilter:
    detection_id: Optional[int]
    species: Optional[str]
    date_from: Optional[datetime]
    date_to: Optional[datetime]
    time_start: Optional[time]
    time_end: Optional[time]
    min_confidence: Optional[float]
    limit: int = 25
    offset: int = 0
    sort_by: str = "time"       # "time", "confidence", "id"
    sort_order: str = "asc"     # "asc", "desc"
    pm_seconds: float = 1.0     # Audio Frame Duration (0.5-6.0)
    use_sci: bool = False
```

**Methoden:**
- `has_species_filter()` - Prüft ob Species-Filter aktiv
- `has_time_filter()` - Prüft ob Zeit-Filter aktiv
- `get_filter_context()` - Für TTS-Text-Generierung
- `to_query_params()` - Konvertiert zu `query_detections()` Parametern
- `validate()` - Validiert Filter

**Helper-Funktionen:**
- `parse_time_range("HH:MM-HH:MM")` - Parst Zeit-Range
- `parse_date("YYYY-MM-DD")` - Parst Datum

#### **keyboard_control.py**
**Zweck:** Non-blocking Tastatur-Input für CLI-Playback.

**Klasse `KeyboardController`:**
- Liest Tastatur non-blocking
- Mapped Arrow-Keys, Space, 'q'

### 5.4 birdnet_play/pages/ - Streamlit Pages

#### **1_database_overview.py**
**Zweck:** Datenbank-Auswahl, Metadata-Anzeige, Species-Liste.

**Sections:**
1. **Database Selector**
   - Dropdown für alle gefundenen DBs
   - Bei Wechsel: Session State clearen

2. **Database Information**
   - Language, Confidence Threshold, Created Date
   - Number of Species (aus species_list)
   - Button "🔄 Actualize Species List"

3. **Notes**
   - Text-Area für User-Kommentare
   - Speichern via `set_analysis_config('user_comment', ...)`

4. **Recording Files**
   - Dataframe mit allen Files aus `metadata`
   - Spalten: Filename, Start/End Time, Duration, Temperature, Battery, GPS

5. **Species List** (AG Grid)
   - Sortierbare Tabelle aller Species
   - Spalten: Scientific, Local, Czech, Detections
   - Detections-Format: `"123 (45) {score: 67.8}"`
     - 123 = count_high (>= 0.7 conf)
     - 45 = count_low (< 0.7 conf)
     - 67.8 = score (formatiert mit 2 signifikanten Stellen)
   - Selection → Button "▶ Play Species"
   - Button setzt alle Filter optimal für Species-Playback

**Auto-Create Logic:**
- Beim Laden: Falls `species_list` fehlt → automatisch erstellen
- Falls `species_list` existiert aber altes Schema → neu erstellen

#### **2_audio_player.py**
**Zweck:** Filter, Audio-Player, Export.

**Neue Features:**
- **Xeno-Canto Integration:** Link-Button öffnet Species-Recordings in neuem Tab
- **Autocomplete Search:** streamlit_searchbox für Species-Suche
- **Clear-Button:** Species-Filter kann zurückgesetzt werden


**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Main Area                                          │
│  ┌───────────────────────────────────────────────┐ │
│  │ 🔍 Search Filters                             │ │
│  │ - Species (mit Autocomplete)                  │ │
│  │   + Xeno-Canto Button (Link zu Recordings)   │ │
│  │ - Date From/To                                │ │
│  │ - Time Range (optional)                       │ │
│  │ - Min Confidence                              │ │
│  │ - Limit, Offset, Sort By                      │ │
│  │ [🔍 Apply Filters]                            │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │ 📊 Statistics                                 │ │
│  │ - Single Audio Length                         │ │
│  │ - Outputs per Minute                          │ │
│  │ - Total Playback Time                         │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │ 📋 Detection List (Expander)                  │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  [💾 Export WAV] [💾 Export MP3]                   │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │ 🎵 Audio Player (Custom HTML/JS)              │ │
│  │ - Sequential Playback                         │ │
│  │ - Play/Pause/Stop/Previous/Next               │ │
│  │ - Recently Played                             │ │
│  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Sidebar: 🎵 Audio Options                         │
│                                                     │
│  ☐ Say Audio Number                                │
│  ○ Say Bird Name: None/Local/Scientific            │
│  ☐ Say Database ID                                 │
│  ☐ Say Confidence                                  │
│                                                     │
│  Speech Speed: ━━━●━━━━ 1.0                        │
│  Speech Loudness: ━━●━━━━ -2 dB                    │
│                                                     │
│  Audio Frame Duration: ━●━━━━ 1.0s                 │
│                                                     │
│  [🎵 Apply Audio Settings]                         │
│  [🔄 Clear Audio Cache]                            │
└─────────────────────────────────────────────────────┘
```

**Session State Management:**

**Filter State (persistent):**
```python
filter_species: str
filter_date_from: date
filter_date_to: date
filter_use_time: bool
filter_time_start: time
filter_time_end: time
filter_confidence: str          # "All" oder "XX%"
filter_limit: int
filter_offset: int
filter_sort: str                # "time", "confidence", "id"
filters_applied: bool           # Trigger für Query
```

**Audio State (persistent):**
```python
audio_say_number: bool          # Default: False
audio_bird_name: str            # 'none', 'local', 'scientific' (Default: 'none')
audio_say_id: bool              # Default: False
audio_say_confidence: bool      # Default: False
audio_speech_speed: float       # 0.5-2.0 (Default: 1.0)
audio_speech_loudness: int      # -10 bis +4 (Default: -2)
audio_frame_duration: float     # 0.5-6.0 (Default: 1.0)
audio_settings_applied: bool    # Trigger für Regeneration
```

**Cached Data:**
```python
detections: List[Dict]          # Query-Results
filter: DetectionFilter         # Aktueller Filter
language_code: str              # Aus DB
audio_cache_{hash}: List[...]   # MP3-Daten (Base64)
```

**Filter-Defaults beim DB-Wechsel:**
- Datum: Min/Max aus DB (NICHT aktuelles Datum!)
- Confidence: "70%"
- Sort: "time"
- Limit: 25

**Play Species Button (von Seite 1):**
- Setzt Species-Filter
- Confidence → "All"
- Sort → "confidence"
- Datum → Min/Max aus DB
- Zeit-Filter deaktiviert
- Offset → 0

**Audio Player (Custom HTML):**
- Lädt alle Detections als Base64-MP3 in HTML
- JavaScript Sequential Playback
- Limit: ~20-30 Detections (sonst HTML zu groß)
- Auto-Play nach Ende eines Tracks

**Statistics Calculation:**
```python
def calculate_single_audio_length(frame_duration, audio_options):
    # 1s pause + frame + 3s detection + frame + TTS
    # TTS duration varies based on options
    pass

def calculate_outputs_per_minute(single_length):
    return 60.0 / single_length
```

#### **3_heatmap_alaltair.py**
**Zweck:** Activity Heatmap - Zeitliche Verteilung von Detections visualisieren.

**Hauptfunktionalität:**
- **Altair-basierte Heatmap:** 2D-Visualisierung mit Datum (X-Achse) und Tageszeit (Y-Achse, 30-Min-Intervalle)
- **Interaktive Zell-Auswahl:** Click-Handler öffnet Dialog mit Detections der gewählten Halbstunde
- **Embedded Audio-Player:** Spielt Detections direkt im Dialog (ohne TTS)
- **Flexible Farbskalen:** 16 verschiedene Colormaps (inferno, viridis, plasma, etc.)
- **Gewichtungs-Modi:** Sum of Confidences oder Count
- **Export-Funktionen:** PNG und CSV

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Sidebar: Heatmap Options                          │
│  - Colormap Selection (16 Optionen)                │
│  - Weight by Confidence (Checkbox)                 │
│  - Guide (Info-Box)                                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Main Area                                          │
│  ┌───────────────────────────────────────────────┐ │
│  │ 🔍 Search Filters                             │ │
│  │ - Species (mit Autocomplete + Xeno-Canto)    │ │
│  │ - Date From/To                                │ │
│  │ - Min Confidence                              │ │
│  │ [🔍 Apply Filters]                            │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │ 📊 Activity Heatmap (Altair Chart)            │ │
│  │ - X-Axis: Dates (Labels nur Montags)         │ │
│  │ - Y-Axis: 48 Half-Hours (Labels alle 3h)     │ │
│  │ - Click → Dialog                              │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  [💾 Export PNG] [💾 Export CSV]                   │
└─────────────────────────────────────────────────────┘
```

**Dialog-Funktion `show_play_dialog()`:**
Öffnet bei Zell-Click ein Modal mit:
- **Metadaten:** Datum, Zeit, Species-Filter, Cell-Stats (Count, Total Conf, Avg Conf)
- **Query:** Lädt max. 25 Detections aus gewählter Halbstunde (mit time_range Parameter!)
- **Audio-Player:** Embedded HTML/JS Player mit `prepare_detection_audio_simple()`
  - Kein TTS (nur Fade + LUFS + Compression)
  - PM-Buffer fest auf 0.5s
  - MP3-Format
  - Sequential Playback

**Session State (page3_* für Isolation von Page 2):**
```python
filter_species: str                  # Geteilt mit anderen Pages
page3_filter_date_from: date        # Isoliert von Page 2
page3_filter_date_to: date          # Isoliert von Page 2
page3_filter_confidence: str        # "All" oder "XX%"
heatmap_colormap: str               # "inferno" (Default), "viridis", etc.
heatmap_weight_confidence: bool     # True = sum(conf), False = count
heatmap_filters_applied: bool       # Trigger für Query
```

**Filter-Defaults:**
- Datum: Min/Max aus DB (wie Page 2)
- Confidence: "70%"
- Species: Leer (All species)
- Colormap: "inferno"
- Weight by Confidence: True

**Daten-Aggregation:**
1. **Detections laden:** Alle Detections im gewählten Datums-/Confidence-Bereich
2. **Aggregation:** GroupBy (date, halfhour_idx) mit sum(confidence) oder count
3. **Long-Form-Data:** Alle Kombinationen (48 halfhours × N dates) mit Nullen für leere Zellen
4. **Altair-Chart:** rect-Mark mit conditional color (weiß für Null, Colormap für Werte)

**Besonderheiten:**
- **Achsen-Labels:** Nur Montags-Daten (X) und 3-Stunden-Intervalle (Y) beschriftet
- **Tooltips:** Hover zeigt Date, Time, Value, Count, Avg Confidence
- **Colorscale:** Domain startet bei 0.01 (nicht 0) für bessere Farbkontraste
- **MIN_COLORSCALE_MAX:** Mindestens 10 als Max-Wert (auch wenn Daten kleiner)
- **HEATMAP_CELL_SIZE:** 12 Pixel (square cells)

**Export:**
- **PNG:** Via Altair's `save()` Methode (benötigt altair_saver + pillow)
- **CSV:** Pivot-Table mit Zeit als Rows, Daten als Columns

**Audio im Dialog:**
- Nutzt `prepare_detection_audio_simple()` → keine TTS-Ansagen
- PM-Buffer: 0.5s (fest)
- Format: MP3 (192k bitrate)
- Base64-encoded für Embedding im HTML
- Sequential Playback mit Auto-Advance


---

## 6. Wichtige Konzepte

### 6.1 PM-Buffer (Audio Frame Duration)

**Was ist das?**
- Plus/Minus Buffer um 3-Sekunden-BirdNET-Detection
- Range: 0.5 - 6.0 Sekunden
- Default: 1.0 Sekunde

**Beispiel:**
```
Detection: 08:32:21.5 - 08:32:24.5 (3s)
PM = 1.0s
→ Extrahiert: 08:32:20.5 - 08:32:25.5 (5s)
```

**Zweck:**
- Kontext vor/nach dem Vogel hören
- Hilft bei Identifikation
- Automatisches Clipping an File-Grenzen

**UI:** "Audio Frame Duration" (nicht "PM Buffer"!)

### 6.2 TTS-Ansagen

**Komponenten:**
- Audio Number: "Audio 1" (Position in Playlist)
- Database ID: "ID 12345" (Detection-ID aus DB)
- Bird Name: Scientific oder Local (abhängig von Option)
- Confidence: "87 Prozent" (num2words, deutsche Stimme)

**Logik:**
```
IF say_audio_number: + "Audio N"
IF say_id: + "ID 12345"
IF bird_name != 'none': + Name
IF say_confidence: + "XX Prozent"
```

**Stimmen-Regel:**
- Scientific Name → IMMER deutsche Stimme (für Latein)
- Local Name → Stimme passend zu `language_code`

**Beispiel-Ansagen:**
```
"Audio 1 ID 12345 Kohlmeise siebenundachtzig Prozent"
"ID 12345 siebenundachtzig Prozent" (nur bei Species-Filter)
```

### 6.3 Audio-Processing-Pipeline

**Reihenfolge (in `_process_audio_frame()`):**
```
1. Fade-in/out (pydub)
   ├─ Fade-in: 0.5s am Anfang
   └─ Fade-out: 0.5s am Ende
   
2. LUFS-Normalisierung (pyloudnorm)
   ├─ Target: -16 LUFS (Streaming-Standard)
   ├─ Misst aktuelle Lautstärke
   └─ Normalisiert auf Ziel-LUFS
   
3. Kompressor (pedalboard)
   ├─ Threshold: -20 dB
   ├─ Ratio: 4:1
   └─ Verhindert Clipping/Verzerrung
   
4. Clipping-Schutz
   └─ np.clip(-1.0, 1.0) + Konvertierung zu int16
```

**Konstanten (anpassbar):**
```python
TARGET_LUFS = -16.0              # -23 = leise, -16 = mittel, -14 = laut
FADE_DURATION_MS = 500           # Fade-Dauer in ms
COMPRESSOR_THRESHOLD_DB = -20.0  # Ab wann komprimieren
COMPRESSOR_RATIO = 4.0           # Wie stark (4:1 = moderat)
```

### 6.4 Einfaches Audio für Heatmap (ohne TTS)

**Funktion:** `prepare_detection_audio_simple()`

**Zweck:** Schnelles Audio-Playback für Heatmap-Dialog ohne TTS-Overhead.

**Pipeline:**
```
1. Extract Snippet (mit PM-Buffer)
   ↓
2. Process Audio Frame (Fade + LUFS + Compression)
   ↓
3. Add 0.5s Silence am Anfang
   ↓
4. Export als MP3 (192k bitrate)
```

**Unterschiede zu prepare_detection_audio_web():**
- ❌ Keine TTS-Ansagen
- ❌ Kein audio_options Dict
- ❌ Kein filter_context
- ✅ Nur Fade + LUFS + Compression
- ✅ Fester PM-Buffer (0.5s)
- ✅ Kürzere Pause (0.5s statt 1.0s)

**Verwendung:**
Nur in Heatmap-Dialog (`3_heatmap_alaltair.py`)

**Vorteile:**
- Schnellere Generierung (kein TTS-API-Call)
- Kleinere Dateien
- Konsistente Länge (ca. 4-5s pro Detection)

### 6.5 Species-Sortierung (Score)

**Formel:** `score = SUM(confidence^4)`

**Warum 4. Potenz?**
- Verstärkt hohe Confidence exponentiell
- Qualität schlägt Quantität

**Beispiel:**
```
Art A: 10x @ 0.9 conf → score = 10 × 0.9^4 ≈ 6.56
Art B: 100x @ 0.3 conf → score = 100 × 0.3^4 ≈ 0.81
→ Art A rankt höher (obwohl nur 10 Detections)
```

**Score-Formatierung:**
- >= 10: Keine Nachkommastellen (`"123"`)
- 1-10: 1 Nachkommastelle (`"9.9"`)
- < 1: 2 signifikante Ziffern (`"0.000075"`)

**Detections-Spalten-Format:**
```
"123 (45) {score: 67.8}"
```
- 123 = count_high (>= 0.7 confidence)
- 45 = count_low (< 0.7 confidence)
- 67.8 = score

**Schwelle 0.7:**
```python
CONFIDENCE_THRESHOLD_HIGH = 0.7  # In db_queries.py (oben)
```

### 6.6 Session State & Caching

**Problem:** Streamlit rerunnt bei jedem Interaction.

**Lösungen:**

**Session State (persistent über Reruns):**
- Filter-Einstellungen
- Audio-Optionen
- Query-Results
- Cache-Keys

**Audio-Cache:**
```python
cache_key = f"audio_cache_{hash(cache_params)}"
st.session_state[cache_key] = audio_files
```

**Cache-Parameter:**
- Detection-IDs (Tuple)
- Audio Frame Duration
- Audio-Optionen (TTS-Settings)

**Cache invalidieren:**
- Bei Filter-Änderung (`filters_applied = True`)
- Bei Audio-Settings-Änderung (`audio_settings_applied = True`)
- Manuell via Button "Clear Audio Cache"

### 6.7 Multi-Language Support

**Ebenen:**

1. **BirdNET Labels** (`local_name`)
   - Kommen direkt von BirdNET
   - Sehr vollständig
   - Sprache via `--lang` Parameter

2. **Tschechische Namen** (`name_cs`)
   - Von karlincam.cz Web-Scraping
   - Manuell kuratiert
   - Weniger vollständig

3. **Scientific Names** (Fallback)
   - Immer vorhanden
   - International verständlich

**Language Code aus DB:**
```python
language_code = get_analysis_config(db_path, 'local_name_shortcut')
# Default: 'de'
```

### 6.8 Embedding-Extraktion und -Speicherung

**Was sind Embeddings?**
- 1024-dimensionale Feature-Vektoren aus BirdNET's internem Netzwerk
- Repräsentieren Audio-Charakteristiken (Frequenzen, Muster, etc.)
- Verwendung: Clustering, Ähnlichkeitssuche, False-Positive-Erkennung

**Workflow in main.py:**
```python
# Phase 1: Detections ermitteln
detections = analyze_file(
    file_path,
    overlap_duration_s=OVERLAP_DURATION_S  # z.B. 0.75s
)

# Phase 2: Embeddings extrahieren (falls --extract-embeddings)
if extract_embeddings_flag:
    # 2a. Alle Embeddings extrahieren
    result = extract_embeddings(
        file_path,
        overlap_duration_s=OVERLAP_DURATION_S  # MUSS identisch sein!
    )
    embeddings_array = result.embeddings[0]  # Shape: (7200, 1024)
    
    # 2b. Segment-Zeiten berechnen (mit Overlap!)
    segment_times = calculate_segment_times(
        n_segments=len(embeddings_array),
        segment_duration_s=result.segment_duration_s,  # 3.0s
        overlap_duration_s=result.overlap_duration_s   # 0.75s
    )
    # Returns: [(0.0, 3.0), (2.25, 5.25), (4.5, 7.5), ...]
    
    # 2c. Nur benötigte Segmente finden (exakte Zeit-Matches)
    index_mapping = find_needed_segments(detections, segment_times)
    # Returns: {5: 0, 12: 1, 13: 2, ...}  # old_idx -> compact_idx
    
    # 2d. Nur benötigte Embeddings speichern
    start_idx = filter_and_write_embeddings(
        embeddings_array,    # Alle 7200 Embeddings
        index_mapping,       # Nur 500 behalten
        hdf5_path
    )
    # Schreibt nur 500 Embeddings in HDF5!
    
    # 2e. Detections mit Indices verknüpfen
    detections = match_embeddings_to_detections(
        detections,
        segment_times,
        index_mapping,
        start_idx
    )
    # Jede Detection bekommt embedding_idx
```

**Kritische Konsistenz-Regel:**
```python
# BEIDE müssen EXAKT gleiche Parameter haben:
analyze_file(..., overlap_duration_s=X)
extract_embeddings(..., overlap_duration_s=X)

# Sonst passen die Zeitfenster NICHT zusammen!
```

**Zeit-basiertes Matching:**
Detection: 2:03:22.721 - 2:03:25.721
Segment:   2:03:22.721 - 2:03:25.721  ← EXAKTE Übereinstimmung!

BirdNET nutzt identische Segmentierung für beide Phasen
→ Exakte Zeit bedeutet exaktes Segment

**Speicher-Effizienz:**
6h-Datei = 7200 Segmente (alle 2.25s ein neues bei 0.75s Overlap)
500 Detections = nur 500 Embeddings gespeichert
→ 93% Speicherersparnis!

**Kompakte Indizierung:**
Original-Segmente: [5, 12, 13, 20, ...]
HDF5-Indices:      [0,  1,  2,  3, ...]  # Keine Lücken!
SQLite speichert: embedding_idx = 0, 1, 2, 3, ...
HDF5 Zeile 0 = Original-Segment 5
HDF5 Zeile 1 = Original-Segment 12

---

## 7. Typische Entwicklungs-Szenarien

### 7.1 "Neue Filter-Option hinzufügen"

**Betroffene Files:**
1. `birdnet_play/filters.py` - Filter-Klasse erweitern
2. `shared/db_queries.py` - Query-Funktion anpassen
3. `pages/2_audio_player.py` - UI-Element hinzufügen
4. `pages/2_audio_player.py` - Session State Init

**Beispiel: GPS-Filter**
```python
# 1. filters.py
@dataclass
class DetectionFilter:
    # ...
    gps_radius_km: Optional[float] = None
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None

# 2. db_queries.py
def query_detections(..., gps_radius_km=None, center_lat=None, center_lon=None):
    # Add Haversine distance calculation

# 3. 2_audio_player.py (UI)
if st.checkbox("Enable GPS Filter"):
    center_lat = st.number_input("Center Latitude")
    # ...

# 4. 2_audio_player.py (Session State)
if 'filter_gps_radius' not in st.session_state:
    st.session_state['filter_gps_radius'] = None
```

### 7.2 "Neue Audio-Processing-Option"

**Betroffene Files:**
1. `birdnet_play/player.py` - Processing-Code in `_process_audio_frame()`
2. `pages/2_audio_player.py` - UI-Control in Sidebar
3. `pages/2_audio_player.py` - Session State Init
4. `birdnet_play/player.py` - Konstante (falls nötig)

**Beispiel: Noise Reduction**
```python
# 1. player.py (oben)
ENABLE_NOISE_REDUCTION = True

# 2. player.py (_process_audio_frame)
if ENABLE_NOISE_REDUCTION:
    samples = apply_noise_reduction(samples, sample_rate)

# 3. 2_audio_player.py (Sidebar)
enable_nr = st.sidebar.checkbox("Noise Reduction", value=True)
st.session_state['audio_noise_reduction'] = enable_nr

# 4. audio_options dict erweitern
audio_options = {
    # ...
    'noise_reduction': st.session_state['audio_noise_reduction']
}
```

### 7.3 "Neue Streamlit Page hinzufügen"

**Steps:**
1. Erstelle `pages/3_new_page.py`
2. Page-Config setzen
3. Import nötiger Funktionen aus `shared/`
4. Zugriff auf `st.session_state['db_path']`
5. Navigation: `st.switch_page("pages/X_xyz.py")`

**Template:**
```python
# pages/3_statistics.py
import streamlit as st
from pathlib import Path
from shared.db_queries import get_db_connection

st.set_page_config(
    page_title="Statistics - BirdNET",
    page_icon="📊",
    layout="wide"
)

# Check DB
db_path = st.session_state.get('db_path')
if not db_path:
    st.error("No database selected")
    st.stop()

st.title("📊 Statistics")
# ... your code ...
```

### 7.4 "Datenbank-Schema erweitern"

**ACHTUNG:** Schema-Änderungen sind heikel!

**Betroffene Files:**
1. `birdnet_walker/database.py` - Schema-Definition
2. `shared/db_queries.py` - Query-Funktionen
3. Evtl. Migration-Code für alte DBs

**Vorgehen:**
1. Neue Tabelle/Spalte in `database.py` definieren
2. Migration-Logik schreiben (prüfe alte DBs)
3. Query-Funktionen anpassen
4. Dokumentation aktualisieren

**Beispiel: Neue Spalte in detections**
```python
# database.py
def init_database():
    # ...
    ALTER TABLE detections ADD COLUMN recording_quality REAL;
    # ...

# db_queries.py
def get_detection_by_id():
    query = """
        SELECT ..., d.recording_quality
        FROM detections d
        ...
    """
```

### 7.5 "TTS-Ansage anpassen"

**Betroffene Files:**
1. `birdnet_play/player.py` - `_get_announcement_text()`
2. `birdnet_play/tts.py` - Evtl. neue Stimmen
3. `pages/2_audio_player.py` - UI für neue Optionen

**Beispiel: Zeitansage hinzufügen**
```python
# player.py
def _get_announcement_text(...):
    parts = []
    # ... existing parts ...
    
    if audio_options.get('say_time'):
        time_str = detection['segment_start_local']
        parts.append(f"um {time_str}")
    
    return " ".join(parts)

# 2_audio_player.py (Sidebar)
say_time = st.sidebar.checkbox("Say Time", value=False)
st.session_state['audio_say_time'] = say_time

# audio_options erweitern
audio_options = {
    # ...
    'say_time': st.session_state['audio_say_time']
}
```

### 7.6 "Embeddings für Clustering nutzen"

**Anwendungsfall:** Ähnliche Detections gruppieren, False-Positives finden.

**Betroffene Files:**
1. Neue Analyse-Scripts außerhalb des Hauptprojekts
2. `shared/db_queries.py` - Evtl. neue Query-Funktionen
3. Dokumentation

**Beispiel-Workflow:**
```python
import h5py
import sqlite3
import numpy as np
from sklearn.cluster import DBSCAN

# 1. Lade alle Embeddings für eine Species
conn = sqlite3.connect('birdnet_analysis.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT id, embedding_idx, confidence
    FROM detections
    WHERE scientific_name = 'Parus major'
    AND embedding_idx IS NOT NULL
""")
detections = cursor.fetchall()
conn.close()

# 2. Lade Embeddings aus HDF5
with h5py.File('birdnet_embeddings.h5', 'r') as f:
    embeddings = f['embeddings']
    vectors = np.array([embeddings[idx] for _, idx, _ in detections])

# 3. Clustering (z.B. DBSCAN)
clustering = DBSCAN(eps=0.3, min_samples=5, metric='cosine')
labels = clustering.fit_predict(vectors)

# 4. Analyse: Welche Cluster haben niedrige Confidence?
for cluster_id in set(labels):
    if cluster_id == -1:
        continue  # Noise
    
    cluster_detections = [d for d, l in zip(detections, labels) if l == cluster_id]
    avg_confidence = np.mean([conf for _, _, conf in cluster_detections])
    
    print(f"Cluster {cluster_id}: {len(cluster_detections)} detections, "
          f"avg confidence: {avg_confidence:.2f}")
```

---

## 8. Debugging & Logging

### 8.1 Logging-Setup

**Library:** Loguru

**Default Level:** INFO

**Config-Beispiel (in Entry Points):**
```python
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, level="INFO")
# Für Debug:
# logger.add(sys.stderr, level="DEBUG")
```

### 8.2 Wichtige Log-Punkte

**Datenbank-Operationen:**
- `db_queries.py` - Query-Results, Fehler
- `database.py` - Schema-Creation, Inserts

**Audio-Processing:**
- `player.py` - Processing-Steps (Fade, LUFS, Compression)
- `tts.py` - TTS-Generation, Fehler

**Streamlit:**
- `st.write()` für Quick-Debug (sichtbar in UI)
- `logger.debug()` für Terminal-Output

### 8.3 Häufige Fehler

**"No such table: species_list"**
- Ursache: Alte DB ohne species_list
- Fix: Button "Actualize Species List" klicken
- Prevention: Auto-create beim Laden implementiert

**"Audio cache keeps growing"**
- Ursache: Cache-Key nicht invalidiert
- Fix: Cache-Clearing-Logik prüfen
- Prevention: Hash über relevante Parameter

**"TTS doesn't work"**
- Ursache: Kein Internet (edge-tts braucht Cloud)
- Fix: Fallback zu Stille (bereits implementiert)
- Alternative: Lokale TTS (nicht implementiert)

**"GPU out of memory" (Walker)**
- Ursache: Batch-Size zu groß
- Fix: `BATCH_SIZE` in `config.py` reduzieren

### 8.4 Embedding-Konsistenz testen

**Test-Script:** `test_embedding_consistency.py`

**Verwendung:**
```bash
python test_embedding_consistency.py /path/to/recordings/folder
```

**Was getestet wird:**
- HDF5 Data Integrity (Shape, dtype, keine NaN/Inf)
- SQLite Embedding Indices (>95% sollten Embeddings haben)
- Index Range Validation (alle Indices im gültigen Bereich)
- **Time-based Consistency** (gleiche Zeit → gleicher Index)
- No Orphaned Embeddings (<5% ungenutzt)
- Segmentation Consistency (~3.0s Segmente)

**Erwartete Ausgabe bei erfolgreicher Validierung:**
```
================================================================================
ALL TESTS PASSED ✓
```

**Häufige Fehlerquellen:**
- Unterschiedliche `overlap_duration_s` Parameter → Zeit-Inkonsistenz
- Corrupt HDF5-Datei → Data Integrity Test schlägt fehl
- DB-Schema-Mismatch → Index Range Test schlägt fehl

---

## 9. Projekt-Konventionen

### 9.1 Code-Style

**Sprache:**
- Code: Englisch
- Kommentare: Englisch
- Docstrings: Englisch
- Logs: Englisch
- UI-Texte: Deutsch (Zielgruppe)
- Dokumentation: Deutsch

**Naming:**
```python
# Functions: snake_case
def extract_audio_snippet():

# Classes: PascalCase
class AudioPlayer:

# Constants: UPPER_SNAKE_CASE
TARGET_LUFS = -16.0

# Private methods: _leading_underscore
def _process_audio_frame():
```

**Docstrings:**
```python
def function(arg: Type) -> ReturnType:
    """
    Short description.
    
    Longer explanation if needed.
    
    Args:
        arg: Description
        
    Returns:
        Description
        
    Raises:
        ErrorType: When this happens
    """
```

### 9.2 File-Organisation

**Imports-Reihenfolge:**
```python
# 1. Standard Library
import sys
from pathlib import Path

# 2. Third-Party
import streamlit as st
import pandas as pd
from loguru import logger

# 3. Local
from shared.db_queries import query_detections
from .player import AudioPlayer
```

**Strukturierung:**
```python
# Imports
# ...

# Constants
CONSTANT = value

# Helper Functions
def helper():
    pass

# Main Classes
class MyClass:
    pass

# Main Function
def main():
    pass

# Entry Point
if __name__ == "__main__":
    main()
```

### 9.3 Git-Workflow (falls relevant)

**Branches:**
- `main` - Stabile Version
- `develop` - Entwicklung
- `feature/xyz` - Features

**Commits:**
- Atomic commits (eine logische Änderung)
- Commit-Messages: Englisch, beschreibend

---

## 10. Wie man mit neuen Aufgaben umgeht

### 10.1 Aufgaben-Analyse

**Fragen, die du stellen solltest:**

1. **Welche Komponente ist betroffen?**
   - Walker (Analyse)? → Meist nicht relevant für Play-Änderungen
   - Play (UI/Playback)? → Welche Page/Module?
   - Shared (DB/Audio)? → Breaking Changes?

2. **Welche Files brauche ich?**
   - Checke Import-Statements
   - Prüfe Funktionsaufrufe
   - Schaue in Doku nach Modul-Beschreibung

3. **Gibt es Session State?**
   - Neue UI-Optionen? → Session State Init
   - Filter-Änderung? → Session State Update
   - Cache-Invalidierung nötig?

4. **Gibt es DB-Schema-Änderungen?**
   - Neue Tabelle/Spalte? → Migration-Code
   - Query-Änderung? → `db_queries.py` anpassen

5. **Betrifft es Audio-Processing?**
   - Neue Processing-Stage? → `_process_audio_frame()`
   - Neue Konstante? → Oben in `player.py`

### 10.2 Files-Anforderung

**Template für File-Anfrage:**
```
Ich brauche folgende Files, um die Aufgabe zu verstehen:

Pflicht:
- birdnet_play/player.py (Audio-Processing ändern)
- pages/2_audio_player.py (UI für neue Option)

Optional (zum Kontext):
- filters.py (wenn Filter-Logik betroffen)
- db_queries.py (wenn Query geändert wird)
```

### 10.3 Implementierungs-Workflow

**Steps:**
1. **Konzept schreiben** (bei komplexen Aufgaben)
2. **Artefakte erstellen** (Code-Snippets)
3. **Einfügestellen exakt beschreiben** (nicht per Zeilennummer!)
4. **Testing-Checkliste** (was muss getestet werden?)
5. **Dokumentation aktualisieren** (falls nötig)

**Einfügestellen-Beschreibung:**
```
✅ RICHTIG:
"Suche die Funktion `def init_filter_state():`
Darin suche die Zeile: `if 'filter_species' not in st.session_state:`
Füge NACH dieser Zeile ein: ..."

❌ FALSCH:
"In Zeile 123 einfügen: ..."
```

### 10.4 Testing-Strategie

**Manuelles Testing:**
- **Smoke-Test:** Grundfunktion läuft?
- **Feature-Test:** Neue Funktion funktioniert?
- **Regression-Test:** Alte Funktionen noch ok?
- **Edge-Cases:** Grenzfälle (leere Daten, große Datenmengen)

**Testing-Checkliste-Beispiel:**
```
- [ ] Filter-UI zeigt neue Option
- [ ] Session State wird korrekt initialisiert
- [ ] Query liefert erwartete Results
- [ ] Audio-Playback funktioniert
- [ ] Export funktioniert (WAV + MP3)
- [ ] Cache wird korrekt invalidiert
```

---

## 11. Projekt-Limitationen & Bekannte Issues

### 11.1 Technische Limitationen

**Walker:**
- CUDA-abhängig (kein CPU-Modus praktikabel)
- Keine echte Parallelverarbeitung mehrerer Files (sequentiell)
- TensorFlow-Fatal-Errors nicht komplett abfangbar

**Play:**
- TTS erfordert Internet (edge-tts ist Cloud-basiert)
- Streamlit AG Grid hat limitierte State-Management-Möglichkeiten
- Audio-Cache kann bei vielen Detections groß werden (>20-30 problematisch)

### 11.2 UI-Limitationen (Streamlit)

**AG Grid:**
- Scroll-Position nicht speicherbar
- Sort-State nicht zuverlässig exportierbar
- Double-Click nicht nativ verfügbar (Selection-Workaround)

**Audio-Player:**
- Custom HTML/JS nötig für Sequential Playback
- Alle Audios müssen als Base64 embedded werden (Größenlimit)

### 11.3 Bekannte Bugs (falls vorhanden)

**Hier dokumentieren, wenn bekannte Bugs existieren:**
- Bug-Beschreibung
- Workaround
- Geplanter Fix

---

## 12. Ressourcen & Referenzen

### 12.1 Externe Dependencies

**BirdNET:**
- GitHub: https://github.com/kahst/BirdNET-Analyzer
- Paper: Kahl et al., Cornell Lab of Ornithology

**edge-tts:**
- GitHub: https://github.com/rany2/edge-tts
- Microsoft Azure TTS (kostenlos via Edge)

**Streamlit:**
- Docs: https://docs.streamlit.io
- AG Grid: https://pypi.org/project/streamlit-aggrid/

### 12.2 Daten-Quellen

**Tschechische Artennamen:**
- URL: https://www.karlincam.cz (manuell kuratiert)
- Caching: `/tmp/species_names.csv` (7 Tage)

**BirdNET Labels:**
- Location: `~/.local/share/birdnet/acoustic-models/v2.4/pb/labels/`
- Format: `{lang}.txt` (z.B. `de.txt`, `en_uk.txt`)

### 12.3 Verwandte Projekte

**AudioMoth:**
- Hardware: Open-source Audio-Recorder
- Website: https://www.openacousticdevices.info/audiomoth

---

## 13. Changelog & Version-Historie

**Wichtig für zukünftige Entwicklung:**

Wenn größere Änderungen gemacht werden, hier dokumentieren:

### Version 0.3.0 (aktuell - 8. Februar 2026)
- **Embedding-Extraktion:** 1024-dim Feature-Vektoren optional extrahierbar
  - `--extract-embeddings` Flag für birdnet-walker
  - Speicherung in separater HDF5-Datei (birdnet_embeddings.h5)
  - Kompakte Indizierung (nur Detections, keine Lücken)
  - Zeit-basiertes Matching (exakte Übereinstimmung)
- **Neue Funktionen in birdnet_analyzer.py:**
  - `extract_embeddings()` - 1024-dim Vektoren für alle Segmente
  - `calculate_segment_times()` - Korrekte Zeitberechnung mit Overlap
  - `find_needed_segments()` - Zeit-basiertes Filtering
  - `filter_and_write_embeddings()` - Kompakte Speicherung
  - `match_embeddings_to_detections()` - Exakte Zeit-Zuordnung
  - `create_or_open_hdf5()` / `write_embeddings_to_hdf5()` - HDF5-Management
- **Datenbank-Schema:** `embedding_idx INTEGER` in detections-Tabelle
- **Config-Updates:** EXTRACT_EMBEDDINGS_DEFAULT, HDF5_* Parameter
- **Test-Suite:** test_embedding_consistency.py für Validierung
- **Breaking Change:** OVERLAP_DURATION_S default 0.75s (war 0.0s)
- **Dokumentation:** Vollständiger Embedding-Workflow dokumentiert

### Version 0.2.0 (24. Januar 2026)
- **Neue Page:** Activity Heatmap (Altair-basiert)
  - 2D-Visualisierung: Datum × Tageszeit (30-Min-Intervalle)
  - Interaktive Zell-Auswahl mit Audio-Dialog
  - 16 Colormap-Optionen
  - Export als PNG/CSV
- **Audio-Processing-Pipeline:** Fade, LUFS-Normalisierung, Compression
- **Species-List:** Intelligente Sortierung mit Score (confidence^4)
- **AG Grid Integration** für Species-Übersicht
- **TTS-Optionen erweitert:** Speech Speed, Loudness
- **Session State Management** verbessert
- **Auto-create species_list** beim DB-Öffnen
- **Neue Audio-Funktion:** `prepare_detection_audio_simple()` (ohne TTS)
- **Species Autocomplete:** streamlit_searchbox Integration
- **Xeno-Canto Integration:** Link-Button zu Recordings
- **time_range Filter:** Präzise Tageszeit-Filterung in Queries
- **Breaking Change:** `extract_snippet()` gibt jetzt Tuple zurück: `(audio_data, sample_rate)`

### Version 0.1.0 (Initial)
- BirdNET Walker: Batch-Analyse mit CUDA
- BirdNET Play: CLI + Streamlit UI
- Grundfunktionalität: Filter, Playback, Export

---

## 14. Zusammenfassung für schnellen Einstieg

**Wenn du nur 5 Minuten hast:**

1. **Projekt:** Vogelstimmen-Analyse mit BirdNET + Playback-UI
2. **Struktur:** 3 Module - `birdnet_walker/` (Analyse), `birdnet_play/` (Playback + Heatmap), `shared/` (Common)
3. **Datenbank:** Eine SQLite-DB + eine HDF5-Datei pro Ordner
   - SQLite: 5 Tabellen (metadata, detections mit embedding_idx, processing_status, analysis_config, species_list)
   - HDF5: Komprimierte Embedding-Vektoren (1024-dim, float32, nur für Detections)
4. **UI:** Streamlit mit 3 Pages - (1) DB Overview + Species List, (2) Audio Player + Filter, (3) Activity Heatmap
5. **Audio & Embeddings:** 
   - Extraktion + Processing (Fade, LUFS, Compression) + TTS + Sequential Playback
   - Optional: 1024-dim Feature-Vektoren für Clustering & Ähnlichkeitssuche


**Wichtigste Files für Änderungen:**
- `shared/db_queries.py` - Alle DB-Queries
- `birdnet_play/player.py` - Audio-Engine
- `pages/2_audio_player.py` - Main UI
- `birdnet_play/filters.py` - Filter-Logik

**Bei Fragen:**
- Checke diese Doku
- Schaue in File-Imports
- Frage nach spezifischen Files

---

**Ende der Dokumentation**

Stand: 2026-01-22
Letzte Aktualisierung: Nach Session mit User (Phase 1-3 Implementation)
Status: Produktiv, aktive Entwicklung
