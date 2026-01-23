# BirdNET Walker - Projekt-Kontext und Dokumentation

## Projekt-Übersicht

BirdNET Walker ist ein Python-basiertes Batch-Analyse-System für AudioMoth-Vogelaufnahmen. Das Projekt nutzt BirdNET (Version 2.4) mit CUDA-GPU-Beschleunigung zur automatischen Vogelerkennung in großen Mengen von WAV-Dateien. Die Hauptfunktion besteht darin, rekursiv Ordner mit AudioMoth-Aufnahmen zu durchsuchen, diese zu analysieren und die Erkennungsergebnisse in SQLite-Datenbanken zu speichern.

Das System ist darauf ausgelegt, mit Unterbrechungen und Fehlern robust umzugehen. Durch ein Status-Tracking-System kann die Verarbeitung jederzeit unterbrochen und später nahtlos fortgesetzt werden, ohne bereits analysierte Dateien erneut zu verarbeiten.

**Technologie-Stack:**
- Python 3.12+ (kompatibel bis 3.13)
- Poetry 2.2.1 für Dependency-Management
- BirdNET 0.2.x mit TensorFlow/CUDA
- SQLite für Datenbanken
- Loguru für Logging
- Pandas für Datenverarbeitung

## Projektstruktur

Das Projekt folgt einer modernen Python-Package-Struktur mit Poetry:

```
project_root/
├── pyproject.toml              # Poetry-Konfiguration, Dependencies
├── README.md
└── source/
    └── birdnet_walker/         # Hauptmodul
        ├── __init__.py
        ├── __main__.py         # Entry point für "python -m birdnet_walker"
        ├── main.py             # Hauptlogik und Orchestrierung
        ├── config.py           # Zentrale Konfigurationskonstanten
        ├── database.py         # SQLite-Verwaltung und Schema
        ├── birdnet_analyzer.py # BirdNET-Wrapper
        ├── audiomoth_import.py # WAV-Metadata-Extraktion
        ├── species_translation.py  # Tschechische Namen von Web
        ├── birdnet_labels.py   # Mehrsprachige Namen von BirdNET
        └── progress.py         # Fortschrittsanzeige
```

**Geplante Erweiterung:**
Ein `shared/` Modul wird parallel zu `birdnet_walker/` angelegt werden, um gemeinsame Funktionen für mehrere Tools bereitzustellen (z.B. Datenbankzugriff, Audio-Snippet-Extraktion).

**Installation und Ausführung:**
```bash
poetry install                    # Dependencies installieren
poetry run birdnet-walker -h      # Hilfe anzeigen
poetry run birdnet-walker INPUT   # Ausführen
```

## Vorhandene Module im Detail

### main.py - Hauptprogramm

Das Hauptprogramm orchestriert den gesamten Analyseprozess. Es implementiert eine zweistufige Architektur:

1. **Folder-Discovery-Phase**: Im recursive Mode werden alle Ordner gefunden, die WAV-Dateien enthalten. Jeder Ordner wird separat verarbeitet und erhält seine eigene Datenbank.

2. **Processing-Phase**: Für jeden Ordner wird ein separater Verarbeitungszyklus durchgeführt. Dabei wird zuerst geprüft, welche Dateien bereits vollständig analysiert wurden, dann werden fehlende Metadaten extrahiert, und schließlich erfolgt die BirdNET-Analyse mit parallelem Datenbankschreiben.

Die Verarbeitung nutzt Multiprocessing: Ein DB-Writer-Prozess empfängt Erkennungsergebnisse über eine Queue und schreibt diese asynchron in die Datenbank, während der Hauptprozess die nächste Datei analysiert.

**Wichtige Funktionen:**
- `find_folders_with_wavs()` - Findet rekursiv alle Ordner mit WAV-Dateien
- `process_folder()` - Verarbeitet einen einzelnen Ordner komplett
- `signal_handler()` - Ermöglicht sauberes Beenden bei Ctrl+C

**Command-Line-Optionen:**
- `--confidence / -c` - Minimum Confidence Threshold (Default: 0.09)
- `--recursive / -r` - Rekursive Ordnerverarbeitung
- `--no-index` - Keine Datenbankindizes erstellen
- `--lang / -l` - Sprachcode für Artennamen (Default: "de")

### config.py - Konfiguration

Zentrale Konstanten für das gesamte Projekt. Hier werden Pfade, BirdNET-Parameter und System-Einstellungen definiert.

**BirdNET-Parameter:**
- `OVERLAP_DURATION_S` - Overlap für BirdNET's Sliding Window (0.0-2.9s)
- `BATCH_SIZE` - Anzahl paralleler Audio-Chunks (32)
- `DEVICE` - Immer 'GPU' (CPU-Mode nicht implementiert)
- Frequenzfilter: `BANDPASS_FMIN` / `BANDPASS_FMAX`

**Pfade:**
- `BIRDNET_MODEL_PATH` - Basis-Pfad zum BirdNET-Modell
- `BIRDNET_LABELS_PATH` - Mehrsprachige Label-Dateien

**System-Parameter:**
- `QUEUE_SIZE` - Maximale Anzahl Result-Packages in Queue (2)
- `SLEEP_INTERVAL` - Wartezeit bei voller Queue (0.1s)

### database.py - Datenbankverwaltung

Dieses Modul verwaltet alle SQLite-Operationen und definiert das Datenbankschema. Es implementiert ein robustes Transaktionsmanagement und einen separaten DB-Writer-Prozess für optimale Performance.

**Kernfunktionen:**

`init_database()` erstellt eine neue Datenbank mit WAL-Mode (Write-Ahead Logging) für bessere Concurrency. Das Schema umfasst drei Haupttabellen.

`insert_metadata()` fügt File-Metadaten ein und setzt den initialen Processing-Status auf 'pending'.

`batch_insert_detections()` schreibt alle Erkennungen einer Datei in einer einzigen Transaktion, was die Performance deutlich verbessert gegenüber Einzel-Inserts.

`db_writer_process()` ist der separate Prozess, der kontinuierlich die Queue abhört und Erkennungsergebnisse in die Datenbank schreibt. Er terminiert sauber, wenn ein "Poison Pill" (None) in der Queue erscheint.

**Processing-Status-Management:**

`cleanup_incomplete_files()` wird beim Programmstart aufgerufen und bereinigt Dateien, die in einem vorherigen Lauf nicht vollständig verarbeitet wurden. Alle Detektionen dieser Dateien werden gelöscht und der Status auf 'pending' zurückgesetzt.

`get_completed_files()` liefert die Menge aller erfolgreich verarbeiteten Dateien, sodass diese übersprungen werden können.

`set_file_status()` aktualisiert den Verarbeitungsstatus einer Datei mit Zeitstempeln.

**Index-Management:**

Die Funktion `create_indices()` erstellt drei Indizes für optimale Query-Performance:
- Zeit-basiert auf `segment_start_local`
- Species-basiert auf `scientific_name`
- Filename-basiert

Mit `--no-index` können alle Indizes gelöscht werden (via `drop_all_indices()`), was sinnvoll ist wenn die Datenbank noch wächst und Indizes die Insert-Performance beeinträchtigen würden.

### birdnet_analyzer.py - BirdNET-Wrapper

Schlanker Wrapper um die BirdNET-Library. Das Modul lädt das Modell lazy beim ersten Aufruf und cached es in einer globalen Variable `_model`, sodass bei der Verarbeitung vieler Dateien das Modell nur einmal geladen werden muss.

`analyze_file()` verarbeitet eine komplette WAV-Datei. BirdNET führt intern die Segmentierung durch (3-Sekunden-Fenster mit konfigurierbarem Overlap). Die Funktion gibt eine Liste von Detektionen zurück, wobei jede Detection den wissenschaftlichen Namen, Common Name (English), Confidence und die exakten Start/End-Zeiten innerhalb der Datei enthält.

**Wichtig für Audio-Tools:** Die `start_time` und `end_time` sind Offsets in Sekunden vom Anfang der Audiodatei. Um die absolute Zeit zu erhalten, müssen diese zum File-Timestamp addiert werden (siehe Datenbank-Schema).

### audiomoth_import.py - Metadata-Extraktion

Extrahiert Metadaten aus AudioMoth WAV-Dateien durch Parsen der RIFF-Chunks. AudioMoth speichert erweiterte Metadaten im GUANO-Format und im ICMT-Chunk.

Die Funktion `extract_metadata()` liefert ein umfangreiches Dictionary mit:
- Timestamps (UTC und konvertiert zu MEZ/MESZ)
- GPS-Koordinaten (falls vorhanden)
- Hardware-Informationen (Serial, Firmware, Temperatur, Batteriespannung)
- Audio-Parameter (Sample Rate, Channels, Bit Depth, Duration)
- Gain-Einstellungen

**Timezone-Handling:** Die Funktion erkennt automatisch ob MEZ (Winterzeit) oder MESZ (Sommerzeit) anhand der DST-Information gilt und setzt das `timezone` Feld entsprechend.

### species_translation.py - Tschechische Namen

Lädt eine manuell kuratierte Übersetzungstabelle von karlincam.cz mit deutschen und tschechischen Vogelnamen. Die Tabelle wird lokal gecacht (`/tmp/species_names.csv`) und automatisch nach 7 Tagen aktualisiert.

`download_species_table()` parsed die HTML-Tabelle mit BeautifulSoup und erstellt ein Pandas DataFrame mit den Spalten: scientific, en, de, cs.

`translate_species_name()` kombiniert die BirdNET-Labels (für die gewählte Sprache) mit der Web-Tabelle (für Tschechisch). Falls eine Übersetzung fehlt, wird der wissenschaftliche Name als Fallback verwendet, sodass nie ein leeres Feld entsteht.

### birdnet_labels.py - Mehrsprachige Namen

Verwaltet die Mehrsprachigkeit durch Zugriff auf BirdNET's Label-Dateien. Diese liegen unter `~/.local/share/birdnet/acoustic-models/v2.4/pb/labels/` und folgen dem Namensschema `<lang>.txt` (z.B. `de.txt`, `en_uk.txt`).

Das Format der Label-Dateien ist simpel: `Scientific Name_Local Name` - genau ein Unterstrich pro Zeile trennt die beiden Namen. Beide Seiten können Leerzeichen enthalten.

`get_available_languages()` scannt den Labels-Ordner und extrahiert die verfügbaren Sprachcodes aus den Dateinamen. Diese werden in der `--lang` Option dynamisch in die Hilfe eingebunden.

`load_birdnet_labels()` lädt eine spezifische Label-Datei und gibt ein Dictionary zurück, das wissenschaftliche Namen auf lokalisierte Namen mappt.

### progress.py - Fortschrittsanzeige

Einfache Klasse zur Anzeige des Verarbeitungsfortschritts auf der Konsole. Zeigt aktuelle Datei, Prozentsatz, Files/Sekunde und geschätzte Restzeit (ETA).

Die Anzeige wird mit `\r` überschrieben, sodass sie kontinuierlich aktualisiert wird ohne den Bildschirm zu füllen.

## Datenbank-Schema

Jeder Ordner mit WAV-Dateien erhält eine eigene SQLite-Datenbank namens `birdnet_analysis.db`. Diese Struktur ermöglicht es, verschiedene Aufnahme-Sessions oder -Standorte separat zu verwalten.

### Tabelle: metadata

Speichert alle File-Metadaten der AudioMoth-Aufnahmen. Jede Datei hat genau einen Eintrag.

**Schema:**
```sql
CREATE TABLE metadata (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    timestamp_utc TEXT NOT NULL,        -- ISO-Format Zeitstempel
    timestamp_local TEXT NOT NULL,      -- MEZ/MESZ konvertiert
    timezone TEXT NOT NULL,             -- 'MEZ' oder 'MESZ'
    serial TEXT,                        -- AudioMoth Seriennummer
    gps_lat REAL,                       -- GPS Breitengrad
    gps_lon REAL,                       -- GPS Längengrad
    sample_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    duration_seconds REAL,
    temperature_c REAL,                 -- Aufnahmetemperatur
    battery_voltage REAL,
    gain TEXT,                          -- Gain-Setting
    firmware TEXT                       -- AudioMoth Firmware-Version
)
```

**Verwendung:** Diese Tabelle dient als Referenz für alle Dateien im Ordner. Sie ermöglicht zeitbasierte Queries und die Zuordnung von GPS-Koordinaten zu Erkennungen.

### Tabelle: detections

Die Haupttabelle mit allen BirdNET-Erkennungen. Jede Erkennung (3-Sekunden-Segment) ist ein separater Eintrag.

**Schema:**
```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    segment_start_utc TEXT NOT NULL,      -- Absolute Startzeit des Segments
    segment_start_local TEXT NOT NULL,    -- In lokaler Zeit (MEZ/MESZ)
    segment_end_utc TEXT NOT NULL,        -- Absolute Endzeit des Segments
    segment_end_local TEXT NOT NULL,
    timezone TEXT NOT NULL,
    scientific_name TEXT NOT NULL,        -- Wissenschaftlicher Artname
    local_name TEXT,                      -- Name in gewählter Sprache (--lang)
    name_cs TEXT,                         -- Tschechischer Name
    confidence REAL NOT NULL,             -- BirdNET Confidence (0.0-1.0)
    FOREIGN KEY (filename) REFERENCES metadata(filename)
)
```

**Zeitstempel-Berechnung:** Die absoluten Segment-Zeiten werden wie folgt berechnet:
```
segment_start_utc = file_timestamp_utc + detection_start_time
segment_end_utc = file_timestamp_utc + detection_end_time
```

Wobei `detection_start_time` und `detection_end_time` die Offsets in Sekunden vom Datei-Anfang sind (von BirdNET geliefert).

**Indizes für Performance:**
- `idx_detections_segment_start` auf `segment_start_local` - für zeitbasierte Queries
- `idx_detections_species` auf `scientific_name` - für Arten-Statistiken
- `idx_detections_filename` auf `filename` - für File-basierte Queries

Diese Indizes werden am Ende der Verarbeitung eines Ordners erstellt (außer bei `--no-index`).

### Tabelle: processing_status

Tracking-Tabelle für den Verarbeitungsstatus jeder Datei. Ermöglicht Resume-Funktionalität.

**Schema:**
```sql
CREATE TABLE processing_status (
    filename TEXT PRIMARY KEY,
    status TEXT NOT NULL,              -- 'pending', 'processing', 'completed', 'failed'
    started_at TEXT,                   -- ISO Timestamp
    completed_at TEXT,                 -- ISO Timestamp
    error_message TEXT,                -- Optional bei 'failed'
    FOREIGN KEY (filename) REFERENCES metadata(filename)
)
```

**Status-Übergänge:**
1. Bei `insert_metadata()`: Status → 'pending'
2. Vor `analyze_file()`: Status → 'processing' mit `started_at`
3. Nach erfolgreicher `batch_insert_detections()`: Status → 'completed' mit `completed_at`
4. Bei Exception: Status → 'failed' mit `error_message`

**Cleanup beim Neustart:** `cleanup_incomplete_files()` findet alle Dateien mit Status ≠ 'completed', löscht deren Detektionen und setzt Status zurück auf 'pending'.

## Audio-Datei-Zusammenhänge

### Dateiorganisation

Audio-Dateien und Datenbank liegen immer zusammen im gleichen Ordner:
```
recording_location/
├── birdnet_analysis.db
├── 243B1F0264881CE0_20250416_171834.WAV
├── 243B1F0264881CE0_20250417_025000.WAV
└── ...
```

Die WAV-Dateien bleiben unverändert erhalten. Die Analyse liest sie nur, schreibt aber nichts zurück.

### AudioMoth-Dateinamens-Konvention

AudioMoth-Dateien folgen diesem Schema:
```
<SERIAL>_<YYYYMMDD>_<HHMMSS>.WAV
```

Beispiel: `243B1F0264881CE0_20250416_171834.WAV`
- Serial: `243B1F0264881CE0`
- Datum: 16. April 2025
- Zeit: 17:18:34 UTC

**Wichtig:** Die Zeit im Dateinamen ist UTC, aber oft nicht präzise genug. Die korrekte Zeit steht in den GUANO-Metadaten im WAV-Header.

### Audio-Snippet-Extraktion (für zukünftige Tools)

Um ein erkanntes Segment als Audio-Snippet zu extrahieren:

1. **Datei finden:** Verwende `filename` aus der `detections` Tabelle
2. **Zeitoffsets berechnen:** 
   - Hole `timestamp_utc` aus `metadata` für diese Datei
   - Berechne: `offset_seconds = segment_start_utc - timestamp_utc`
3. **Audio extrahieren:** Lese WAV ab Offset für 3 Sekunden (oder `segment_end - segment_start`)

Beispiel-Code-Konzept:
```python
import wave

def extract_snippet(db_path, detection_id, output_file):
    # Get detection + metadata
    detection = get_detection_by_id(db_path, detection_id)
    metadata = get_metadata_by_filename(db_path, detection['filename'])
    
    # Calculate offset
    wav_path = Path(db_path).parent / detection['filename']
    offset_seconds = (detection['segment_start_utc'] - metadata['timestamp_utc']).total_seconds()
    duration_seconds = (detection['segment_end_utc'] - detection['segment_start_utc']).total_seconds()
    
    # Extract audio
    with wave.open(wav_path, 'rb') as wav:
        sample_rate = wav.getframerate()
        start_frame = int(offset_seconds * sample_rate)
        n_frames = int(duration_seconds * sample_rate)
        
        wav.setpos(start_frame)
        audio_data = wav.readframes(n_frames)
        
        # Write snippet...
```

## Wichtige Konzepte und Patterns

### Processing Status Tracking

Das Status-Tracking ermöglicht robuste Verarbeitung mit folgenden Garantien:

1. **Idempotenz:** Bereits vollständig verarbeitete Dateien werden übersprungen
2. **Crash-Recovery:** Bei Programmabsturz werden unvollständige Dateien beim nächsten Start erkannt und neu verarbeitet
3. **Fehler-Tracking:** Fehlgeschlagene Dateien werden markiert und dokumentiert

Der Status-Übergang ist atomar: Erst nach erfolgreichem Schreiben aller Detektionen wird der Status auf 'completed' gesetzt. Schlägt ein Schritt fehl, bleibt der Status bei 'processing' oder wird auf 'failed' gesetzt.

### Multi-Language Support

Die Mehrsprachigkeit ist zweigeteilt:

**BirdNET-Labels (`local_name`):** Decken die meisten Arten ab und kommen direkt von BirdNET. Diese sind sehr vollständig, da sie von der BirdNET-Community gepflegt werden. Die verfügbaren Sprachen können dynamisch erweitert werden durch neue `.txt` Dateien im Labels-Ordner.

**Tschechische Namen (`name_cs`):** Kommen von einer kuratierten Web-Tabelle. Diese ist weniger vollständig, aber manuell geprüft. Die Tabelle wird gecacht und wöchentlich aktualisiert.

**Fallback-Strategie:** Bei fehlenden Übersetzungen wird immer der wissenschaftliche Name eingetragen. Dadurch gibt es nie leere Felder, was bei Abfragen und Darstellungen Fehler verhindert.

### Recursive Mode und Datenbank-Organisation

Im Recursive Mode (`--recursive`) werden alle Unterordner durchsucht. Jeder Ordner mit WAV-Dateien erhält seine eigene Datenbank. Dies hat mehrere Vorteile:

1. **Unabhängigkeit:** Ordner können einzeln verarbeitet, kopiert oder archiviert werden
2. **Parallelisierung:** Verschiedene Ordner könnten theoretisch parallel verarbeitet werden
3. **Übersichtlichkeit:** Ergebnisse bleiben bei den zugehörigen Aufnahmen
4. **Inkrementelle Verarbeitung:** Neue Dateien in einem Ordner werden automatisch erkannt und nur diese werden analysiert

Der Algorithmus:
1. Scanne rekursiv nach Ordnern mit WAV-Dateien
2. Für jeden Ordner: Prüfe ob Datenbank existiert
3. Ermittle fehlende Dateien (nicht in `metadata` oder Status ≠ 'completed')
4. Verarbeite nur fehlende Dateien
5. Erstelle/aktualisiere Indizes

### GPU-Fehlerbehandlung und Logging

BirdNET nutzt TensorFlow mit CUDA. GPU-Fehler (wie "illegal memory access") können auftreten und sind kritisch. Das System fängt diese teilweise ab:

**Python-Level:** `capture_tf_output()` fängt stdout/stderr während der Prediction ab. Warnings und normale Errors werden geloggt.

**C++-Level (Fatal Errors):** TensorFlow's fatale Fehler (aus C++-Code) können nicht komplett abgefangen werden. Sie erscheinen auf stderr und crashen den Prozess. Das Log zeigt aber die Warnungen davor, was bei der Fehlersuche hilft.

Alle stderr-Ausgaben werden im Debug-Level vollständig geloggt, sodass bei Problemen die TensorFlow-Meldungen nachvollzogen werden können.

### Index-Management-Strategie

Datenbankindizes beschleunigen Queries, verlangsamen aber Inserts. Die Strategie:

**Standard-Modus:** Indizes werden am Ende der Verarbeitung erstellt, wenn alle Daten eingefügt sind. Das ist optimal für initiale Batch-Verarbeitung.

**Bei inkrementellen Updates:** Wenn neue Dateien zu einem Ordner hinzugefügt werden, werden die Indizes automatisch neu erstellt um die neuen Daten einzubeziehen.

**Mit `--no-index`:** Keine Indizes. Sinnvoll wenn:
- Die Datenbank noch stark wächst
- Nur sequenzielle Verarbeitung geplant ist
- Maximale Insert-Performance gewünscht

Bestehende Indizes werden bei `--no-index` gelöscht, selbst wenn neue Daten hinzugefügt wurden.

## BirdNET Model und Setup

### Model-Location

Das BirdNET-Modell liegt unter:
```
~/.local/share/birdnet/acoustic-models/v2.4/
```

Definiert in `config.py` als `BIRDNET_MODEL_PATH`.

**Labels:** `{BIRDNET_MODEL_PATH}/pb/labels/*.txt`
**Model:** `{BIRDNET_MODEL_PATH}/pb/model-fp32/saved_model.pb`

Das Modell wird **nicht** vom Programm heruntergeladen, sondern muss vorher via Setup-Script installiert werden. Bei fehlendem Modell terminiert das Programm mit entsprechender Fehlermeldung.

### Model-Loading

Das Modell wird lazy beim ersten `analyze_file()` Aufruf geladen und in der globalen Variable `_model` gecached. Das verhindert wiederholtes Laden bei der Verarbeitung vieler Dateien, was mehrere Minuten Ladezeit sparen würde.

## Hinweise für zukünftige Tools

### Gemeinsame Funktionen (geplantes shared-Modul)

Folgende Funktionen sollten in ein `shared` Modul ausgelagert werden:

**Datenbankzugriff:**
- Verbindung mit WAL-Mode öffnen
- Standard-Queries (get_detection_by_id, get_detections_by_species, etc.)
- Metadata-Lookup

**Audio-Verarbeitung:**
- Snippet-Extraktion aus WAV-Datei
- Audio-Format-Konvertierung (falls nötig)
- Metadata-Parsing (könnte `audiomoth_import` referenzieren)

**Visualisierung:**
- Spektrogramm-Generierung
- Statistik-Helpers

### Typische Use Cases für neue Tools

**Audio-Playback-Tool:**
```bash
birdnet-play DB_PATH --detection-id 12345
birdnet-play DB_PATH --species "Parus major" --date 2025-04-16
```
Benötigt: DB-Query, Snippet-Extraktion, Audio-Player-Integration

**Statistik-Tool:**
```bash
birdnet-stats DB_PATH --output report.html
birdnet-stats DB_PATH --species-list --min-confidence 0.5
```
Benötigt: DB-Aggregation, Visualisierung (matplotlib/plotly), Export

**Export-Tool:**
```bash
birdnet-export DB_PATH --format csv --output detections.csv
birdnet-export DB_PATH --format json --species "Turdus merula"
```
Benötigt: DB-Query, Format-Serialisierung

## Offene Punkte und bekannte Einschränkungen

### GPS-Filterung (TODO)

Aktuell werden GPS-Koordinaten aus den AudioMoth-Metadaten extrahiert und in der Datenbank gespeichert, aber **nicht** zur Filterung der BirdNET-Ergebnisse verwendet. BirdNET kann die erwartete Artenliste basierend auf Location und Datum einschränken, was False Positives reduzieren würde.

**Geplante Implementierung:** Die Koordinaten sollten an `model.predict()` übergeben werden, sodass nur lokal vorkommende Arten erkannt werden. Aktuell werden alle Arten weltweit berücksichtigt (nur durch Confidence-Threshold begrenzt).

**Workaround:** Die GPS-Daten sind in der Datenbank vorhanden und können für Post-Processing-Filterung verwendet werden.

### TensorFlow Fatal Errors

GPU-Fehler auf C++-Level (z.B. "illegal memory access") können nicht vollständig abgefangen werden und führen zum Programmabbruch. Das Processing-Status-System stellt sicher, dass bei einem Neustart die betroffene Datei erneut verarbeitet wird.

**Debugging:** Alle TensorFlow stderr-Ausgaben werden im Debug-Level geloggt. Bei GPU-Problemen das Log nach Warnings vor dem Crash durchsuchen.

### Performance-Überlegungen

**GPU-Auslastung:** Die aktuelle Architektur nutzt eine einzige BirdNET-Instanz sequenziell. Parallele Verarbeitung mehrerer Dateien ist möglich, würde aber mehr GPU-Memory benötigen und die Queue-Verwaltung komplizierter machen.

**Batch-Size:** Aktuell auf 32 gesetzt. Höhere Werte können die GPU-Auslastung verbessern, benötigen aber mehr VRAM.

**DB-Inserts:** Der separate DB-Writer-Prozess mit Batch-Inserts ist bereits optimiert. Indizes werden erst am Ende erstellt für maximale Insert-Performance.

## Zusammenfassung für neue Entwickler

Dieses Projekt analysiert AudioMoth-Vogelaufnahmen mit BirdNET und speichert Erkennungen in SQLite-Datenbanken. Die Architektur ist auf Robustheit und Wiederaufnahme-Fähigkeit ausgelegt.

**Wichtigste Files für neue Tools:**
- `database.py` - Schema und DB-Funktionen verstehen
- `config.py` - Pfade und Konstanten
- `audiomoth_import.py` - File-Metadaten verstehen

**Datenbank-Struktur verstehen:**
- Eine DB pro Ordner mit WAV-Dateien
- Drei Haupttabellen: metadata, detections, processing_status
- Zeitstempel immer in UTC und Local (MEZ/MESZ)
- Segment-Zeiten = File-Timestamp + Offset

**Für Audio-Tools:** Die Kombination aus `filename`, `segment_start_utc`, `segment_end_utc` in der detections-Tabelle ermöglicht das präzise Extrahieren von 3-Sekunden-Snippets aus den Original-WAV-Dateien.

**Für Statistik-Tools:** Die Indizes auf `segment_start_local` und `scientific_name` ermöglichen schnelle zeitbasierte und artbasierte Aggregationen. GPS-Koordinaten sind über `metadata` verfügbar.
