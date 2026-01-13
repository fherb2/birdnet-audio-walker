# BirdNET Batch Analyzer

Batch-Analyse von AudioMoth-Aufnahmen mit BirdNET. Exportiert Ergebnisse als LibreOffice Calc ODS-Datei.

## Features

- ✅ Parallelverarbeitung mit Multiprocessing (1.5x CPU-Cores)
- ✅ Hann-Window für Audio-Segmentierung
- ✅ Automatische GPS- und Zeitfilterung für BirdNET
- ✅ Mehrsprachige Artennamen (Wissenschaftlich, Deutsch, Tschechisch, Englisch)
- ✅ SQLite als Zwischenspeicher
- ✅ Automatische UTC → MEZ/MESZ Konvertierung
- ✅ Progress-Anzeige
- ✅ Export als ODS-Datei (LibreOffice Calc)

## Installation

### Voraussetzungen

- Python 3.12
- libsndfile (für Audio-File-Support)

**Ubuntu/Debian:**
```bash
sudo apt-get install libsndfile1
```

**macOS (Homebrew):**
```bash
brew install libsndfile
```

### Python-Pakete

```bash
pip install -r requirements.txt
```

## Verwendung

### Einfachste Verwendung

```bash
python main.py /path/to/audiomoth/recordings
```

### Mit Optionen

```bash
python main.py /path/to/audiomoth/recordings \
    --output /path/to/results.ods \
    --confidence 0.35
```

### Argumente

- `input_folder`: Pfad zum Ordner mit WAV-Dateien (required)
- `--output`, `-o`: Output ODS-Datei (default: `results.ods`)
- `--confidence`, `-c`: Minimum Confidence Threshold (default: `0.25`)

## Output

Die ODS-Datei enthält zwei Tabellenblätter:

### Sheet 1: "Detektionen"

Alle Vogel-Detektionen sortiert nach Zeit:

| Spalte | Beschreibung |
|--------|--------------|
| Dateiname | Original WAV-Dateiname |
| Segment Start (UTC) | Segment-Start in UTC (ISO 8601) |
| Segment Start (Lokal) | Segment-Start in MEZ/MESZ |
| Segment Ende (UTC) | Segment-Ende in UTC |
| Segment Ende (Lokal) | Segment-Ende in MEZ/MESZ |
| Zeitzone | "MEZ" oder "MESZ" |
| Wissenschaftlicher Name | Scientific name |
| Englischer Name | English common name |
| Deutscher Name | German name |
| Tschechischer Name | Czech name |
| Konfidenz | Confidence (0.0 - 1.0) |

### Sheet 2: "Metadaten"

Ein Eintrag pro Audio-Datei:

| Spalte | Beschreibung |
|--------|--------------|
| Dateiname | Original WAV-Dateiname |
| Zeitstempel (UTC) | Aufnahme-Start UTC |
| Zeitstempel (Lokal) | Aufnahme-Start MEZ/MESZ |
| Zeitzone | "MEZ" oder "MESZ" |
| Geräte-ID | AudioMoth Serial |
| GPS Latitude | GPS Breitengrad |
| GPS Longitude | GPS Längengrad |
| Sample Rate | Sample Rate (Hz) |
| Kanäle | Anzahl Kanäle |
| Bit-Tiefe | Bit Depth |
| Dauer | Dauer in Sekunden |
| Temperatur | Temperatur (°C) |
| Batteriespannung | Battery Voltage (V) |
| Verstärkung | Gain Setting |
| Firmware | Firmware Version |

## Konfiguration

Alle Parameter können in `config.py` angepasst werden:

```python
# Audio Segmentation
SEGMENT_LENGTH_SEC = 3.0      # Segment length
OVERLAP_SEC = 0.7              # Overlap on each side
STRIDE_SEC = 2.3               # Stride between segments
FADE_LENGTH_SEC = 0.3          # Hann window fade length

# Multiprocessing
WORKER_MULTIPLIER = 1.5        # Workers = CPU cores * 1.5

# BirdNET
DEFAULT_CONFIDENCE = 0.25      # Default confidence threshold
```

## Architektur

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
└── README.md                  # Diese Datei
```

## Logging

Logs werden in `birdnet_analyzer.log` gespeichert (automatische Rotation bei 10 MB).

## Troubleshooting

### "libsndfile not found"

Installiere libsndfile (siehe Installation oben).

### "No module named 'birdnet'"

Installiere requirements: `pip install -r requirements.txt`

### Progress-Anzeige funktioniert nicht richtig

Die Progress-Anzeige aktualisiert sich alle 2 Sekunden oder alle 10 Tasks. Bei sehr schneller Verarbeitung kann es zu Verzögerungen kommen.

## Lizenz

MIT License

## Danksagung

- **BirdNET**: Stefan Kahl et al. (Cornell Lab of Ornithology)
- **Artennamen-Übersetzung**: karlincam.cz
