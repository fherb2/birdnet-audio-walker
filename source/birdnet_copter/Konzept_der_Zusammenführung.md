# Konzept: birdnet-copter

Stand: 2026-03-06
Status: Entwurf

---

## 1. Überblick

`birdnet-copter` ist die Zusammenführung von `birdnet-walker` (Analyse-Engine)
und `birdnet-play` (NiceGUI-Player) in einer einzigen Anwendung.

Der bisherige `birdnet_play/`-Ordner wird 1:1 als Startpunkt übernommen und
umbenannt. Die Walker-Funktionalität wird als neuer Hintergrundprozess
integriert. Die GUI erhält drei neue bzw. umstrukturierte Seiten.

**App-Name:** `birdnet-copter`
**Entry Point:** `birdnet-copter` (ersetzt `birdnet-play` und `birdnet-walker`)

---

## 2. Projektstruktur

### 2.1 Verzeichnis-Layout (Zielzustand)

```
source/
├── shared/                         # unverändert
│   ├── __init__.py
│   ├── db_queries.py
│   ├── audio_extract.py
│   └── streamlit_utils.py          # find_databases_recursive() weiter genutzt; File umbenennen!
│
├── birdnet_walker/                 # Entfällt: Inhalt der Files oder ganze Files werden nach 
│                                   # birdnet_copter übernommen.
│
└── birdnet_copter/                 # umbenennen von birdnet_play/ + Erweiterungen
    ├── __init__.py
    ├── __main__.py                 # Entry point: python -m birdnet_copter bzw. poetry: birdnet-copter
    ├── main.py                     # NEU: Backend-Main + Prozess-Start (s. Abschnitt 3)
    ├── app_state.py                # ERWEITERT (s. Abschnitt 4)
    ├── hardware.py                 # NEU: Hardware-Detection (s. Abschnitt 5)
    ├── job_queue.py                # NEU: Auftragsliste + Wait/Stop-Logik (s. Abschnitt 6)
    ├── walker_process.py           # NEU: Walker als Hintergrundprozess (s. Abschnitt 6)
    ├── filters.py                  # unverändert
    ├── player.py                   # unverändert
    ├── tts.py                      # unverändert
    │
    ├── gui_elements/               # unverändert
    │   ├── __init__.py
    │   ├── folder_tree.py          # ERWEITERT: schlankere Variante für Hangar
    │   └── species_search.py
    │
    └── pages/
        ├── __init__.py             # ANGEPASST: neue Seiten registrieren
        ├── layout.py               # ANGEPASST: App-Name + "(global)"-Anzeige
        ├── hangar.py               # NEU  – Route: /
        ├── scouting_flight.py      # NEU  – Route: /scouting
        ├── exploration_area.py     # UMGEBAUT aus database_overview.py – Route: /exploration
        ├── audio_player.py         # Route: /audio-player  (unverändert)
        └── heatmap_page.py         # Route: /heatmap       (unverändert)
```

### 2.2 Was entfällt


| Alt                                           | Grund                                                                                                                                          |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `birdnet_play/pages/database_overview.py`     | Aufgeteilt in`hangar.py`, `scouting_flight.py`, `exploration_area.py`                                                                          |
| `birdnet_play/main.py`                        | Ersetzt durch neues`birdnet_copter/main.py`                                                                                                    |
| CLI-only-Modus (`--species`, `--export` etc.) | Entfällt; Bedienung erfolgt ausschließlich über GUI; nur der Haupt-Ordner kann noch vorgegeben werden (alternativ wird User-Home verwendet) |

### 2.3 pyproject.toml

```toml
[tool.poetry.scripts]
birdnet-copter = "birdnet_copter.main:main"
# birdnet-walker und birdnet-play bleiben als eigenständige Tools erhalten
```

Bitte prüfen, ob noch andere Einträge geändert werden müssen (z.B. entfernen).

---

## 3. Prozess-Architektur

birdnet-copter läuft in **drei Prozessen**:

```
┌─────────────────────────────────────────────────────┐
│  Prozess 1: Backend-Main                            │
│  - Startet beim App-Launch                          │
│  - Liest CLI-Argumente, initialisiert AppState      │
│  - Führt Hardware-Detection durch                   │
│  - Verwaltet Job Queue (Auftragsliste)              │
│  - Startet Prozess 2 (GUI) und Prozess 3 (Walker)  │
│  - Kommuniziert über multiprocessing.Queue und      │
│    multiprocessing.Manager                          │
└────────────────┬────────────────────────────────────┘
                 │ startet
        ┌────────┴──────────────────────────────┐
        │                                       │
        ▼                                       ▼
┌───────────────────────┐         ┌─────────────────────────┐
│  Prozess 2: GUI-Server│         │  Prozess 3: Walker       │
│  NiceGUI / uvicorn    │         │  birdnet_walker-Logik    │
│  asyncio hier         │         │  sequentiell, blockierend│
│  ui.timer liest       │◄────────│  schreibt Fortschritt   │
│  Status aus Manager   │         │  in progress_queue       │
└───────────────────────┘         └─────────────────────────┘
```

### 3.1 Kommunikationskanäle


| Kanal            | Typ                                | Richtung       | Inhalt                                    |
| ------------------ | ------------------------------------ | ---------------- | ------------------------------------------- |
| `job_queue`      | `multiprocessing.Queue`            | Main → Walker | Job-Objekte                               |
| `progress_queue` | `multiprocessing.Queue`            | Walker → Main | Fortschrittsmeldungen                     |
| `control_queue`  | `multiprocessing.Queue`            | Main → Walker | Steuerkommandos (WAIT, RESUME, STOP)      |
| `shared_state`   | `multiprocessing.Manager().dict()` | Main → GUI    | Lesbarer Status (jobs, progress, hw_info) |

### 3.2 Startup-Sequenz

```
main() in main.py
  │
  ├─ parse_args()              # input_path (CLI oder Home)
  ├─ hardware_detection()      # → HardwareInfo-Objekt
  ├─ init_app_state()          # AppState befüllen
  ├─ Manager starten           # shared_state anlegen
  ├─ Walker-Prozess starten    # wartet zunächst auf Jobs
  └─ GUI-Server starten        # uvicorn + NiceGUI (blockiert bis Shutdown)
       └─ on_startup: shared_state in app.state ablegen
```

---

## 4. AppState-Erweiterungen

`app_state.py` erhält zusätzliche Felder:

```python
@dataclass
class AppState:
    # --- bestehende Felder (unverändert) ---
    root_path: Path
    read_only: bool
    available_dbs: List[Path]
    active_db: Optional[Path]
    language_code: str
    # ...

    # --- NEU: Hardware ---
    hw_info: Optional['HardwareInfo'] = None   # befüllt durch hardware.py

    # --- NEU: Laufzeit-Konfiguration (aus Hangar) ---
    use_gpu: bool = True                        # False → CPU-Modus
    use_embeddings: bool = True                 # Embedding-Vektoren extrahieren
    global_index_path: Optional[Path] = None   # Pfad für globalen Index

    # --- NEU: Job Queue Status (read-only-Sicht für GUI) ---
    # Wird aus shared_state gespiegelt, nicht direkt beschrieben
    jobs: List[dict] = field(default_factory=list)
    walker_status: str = 'idle'                 # 'idle' | 'running' | 'wait_pending' | 'waiting'

    # --- NEU: Globale DB aktiv? ---
    active_db_is_global: bool = False           # steuert "(global)" im Header
```

---

## 5. Hardware-Detection (`hardware.py`)

```python
@dataclass
class HardwareInfo:
    has_nvidia_gpu: bool
    gpu_name: Optional[str]          # z.B. "NVIDIA RTX A6000"
    gpu_shaders: int                 # number of shader units
    gpu_vram_gb: Optional[float]     # size of GPU RAM
    cpu_count_physical: int          # ohne HT
    cpu_count_logical: int           # mit HT
    cpu_count_for_inference: int     # max(1, logical - 2) falls logical >= 3, sonst alle
    sleep_flag: bool                 # True wenn logical < 3
    ram_total_gb: float
```

**Erkennungslogik beim Start:**

```python
def detect_hardware() -> HardwareInfo:
    # GPU: versuche nvidia-smi oder torch.cuda
    # CPU: psutil.cpu_count(logical=True/False)
    # cpu_count_for_inference:
    #   logical >= 3 → logical - 2
    #   logical < 3  → logical, sleep_flag = True
    # RAM: psutil.virtual_memory()
```

**Wichtig:** `sleep_flag` wird als Flag in `AppState` geführt.
Die eigentliche Sleep-Logik an den kritischen Stellen im Code
wird in einem späteren Schritt implementiert.

---

## 6. Job Queue (`job_queue.py` + `walker_process.py`)

### 6.1 Job-Objekt

```python
@dataclass
class ScanJob:
    job_id: str                     # uuid
    folder_path: Path
    rescan_species: bool = False    # Inferenz erneut durchführen
    scan_embeddings: bool = True    # Embedding-Vektoren ermitteln/nachholen
    min_conf: float = 0.4           # minimum confidence
    status: str = 'pending'         # 'pending'|'running'|'done'|'error'|'skipped'
    added_at: datetime = ...
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    files_total: int = 0
    files_done: int = 0
    current_file: str = ''
    error_msg: str = ''
```

`scan_embeddings=True` bedeutet: Embedding-Vektoren werden für alle
Detections ermittelt, für die noch kein `embedding_idx` in der DB steht —
also auch für bereits erkannte Species nachgeholt.
`rescan_species: bool = False` ist der Normalfall: Es werden alle Audio-Files immer gescannt, die noch nicht gescannt wurden. Bei True werden die Scanns neu gemacht. Mit vorgegebenem Mindest-Confidence-Wert.

### 6.2 Walker-Prozess (`walker_process.py`)

Der Walker-Prozess läuft in einer Endlosschleife und wartet auf Jobs:

```
loop:
  job = job_queue.get(block=True)      # wartet auf nächsten Job

  falls job == STOP-Signal:
    graceful exit

  status = 'running' → shared_state aktualisieren

  für jede WAV-Datei im Ordner:
    prüfe control_queue auf WAIT/RESUME/STOP
      WAIT:   wait_pending = True
      RESUME: wait_pending = False
      STOP:   stop_after_batch = True

    rufe birdnet_analyzer auf (blockierend bis Batch zurück kehrt)
    ← birdnet kehrt zurück

    falls wait_pending:
      Walker → Zustand 'waiting'
      blockiert hier (wartet auf RESUME oder STOP aus control_queue)

    falls stop_after_batch:
      graceful exit nach dieser Datei

    schreibe Fortschritt → progress_queue

  status = 'done' → shared_state aktualisieren
```

### 6.3 Wait-Logik im Detail

```
Benutzer drückt "Wait" in der GUI
  → Main sendet WAIT in control_queue
  → Walker setzt wait_pending = True
  → GUI zeigt sofort: "⏳ Wait pending (nach aktuellem Batch)"

BirdNET-Batch kehrt zurück
  → Walker prüft wait_pending
  → Walker wechselt in Zustand 'waiting'
  → GUI zeigt: "⏸ Waiting"

Benutzer drückt "Resume"
  → Main sendet RESUME in control_queue
  → Walker setzt wait_pending = False, läuft weiter
```

**Wichtig:** "Wait" betrifft den aktuellen und alle folgenden Jobs in der
Queue, bis "Resume" gedrückt wird. Laufende BirdNET-Batches werden
**niemals** abgebrochen. Das heißt, der Prozess wird nie abgewürgt. Es wird gewartet bis birdnet mit seinem zuletzt bearbeiteten Batch zurück kehrt.

## 7. Header / Layout (`layout.py`)

Der Header ist auf allen Seiten identisch (unveränderte Logik, nur
visuell erweitert):

```
┌──────────────────────────────────────────────────────────────────┐
│ [☰]  birdnet-copter │  <root_path>          │  RO / RW          │
│                      │  <active_db> (global) │  [spinner]        │
└──────────────────────────────────────────────────────────────────┘
  col-left             col-center               col-right
```

- **col-left:** Hamburger-Button + **"birdnet-copter"** (fett, direkt daneben, Größe: 1,5 Zeilenhöhe) Breite: so schmal, wie möglich
- **col-center:** Root-Path (Zeile 1) / aktive DB-Pfad (Zeile 2) —
  falls `active_db_is_global=True`: hinter dem Pfad angeben: `"<pfad> (global)"` in Zeile 2
- **col-right:** Access-Mode + Spinner (unverändert; Breite: so schmal, wie möglich)

**Navigation Drawer** (Reihenfolge):

1. Hangar
2. Scouting Flight
3. Exploration Area
4. 🎵 Audio Player
5. 🌡️ Heatmap

---

## 8. Seite 1: Hangar (`hangar.py`, Route: `/`)

### Zweck

Technische Basis-Konfiguration der App. Einmalig beim Start relevant,
aber jederzeit änderbar.

### Abschnitte

#### 8.1 Host Information (read-only Anzeige)

Zeigt die Ergebnisse von `hardware.py`:


| Feld                    | Beispiel                                       |
| ------------------------- | ------------------------------------------------ |
| GPU                     | NVIDIA RTX A6000 (48 GB VRAM, 4000 Prozessors) |
| CPU                     | 16 logical cores (14 physical)                 |
| RAM                     | 128 GB                                         |
| CPU cores for inference | 14 (logical - 2)                               |
|                         |                                                |

Falls keine NVIDIA-GPU gefunden: Zeile GPU = "no NVIDIA-GPU".

#### 8.2 Root Path

- Label: "Root Path, Global DB Path"
- Anzeige des aktuellen Pfads (aus CLI-Argument oder Home-Verzeichnis)
- Button "📁 Ändern" → öffnet `FolderTree`-Dialog (schlank, ohne
  Zusatzspalten, längere Liste als der bisherige FolderTree)
- Nach Auswahl: Root-Path in AppState aktualisieren,
  `available_dbs` neu scannen

**Hinweis:** Die schlankere FolderTree-Variante für den Hangar wird als
optionaler Parameter im bestehenden `folder_tree.py` umgesetzt
(`show_extras=False`, `row_height` anpassbar), kein zweites File.

#### 8.3 Inference Configuration

- **Use GPU:** Toggle (default: `True` falls GPU erkannt, sonst ausgegraut)
- **Use Embedding Vectors:** Toggle (default: `False`)
  - Erklärungstext: "Extrahiert 1024-dim Feature-Vektoren für Clustering
    und Ähnlichkeitssuche. Erhöht Analysezeit um ca. 2×."

#### 8.4 Global Index

- **Create/Use Global Index:** Toggle (default: `False`)
- **Global Index Path:** Pfad-Anzeige + Button "📁 Ändern"
  (default: Root-Path-Ordner)
  - Nur aktiv wenn Toggle = `True`
- Erklärungstext: "Ein globaler Index fasst alle lokalen Datenbanken
  in einer übergreifenden Datenbank zusammen."

#### 8.5 Verhalten bei Änderungen

- Alle Einstellungen wirken sofort auf `AppState`
- GPU/Embeddings-Änderungen wirken auf den nächsten gestarteten Job
  (laufende Jobs sind nicht betroffen)
- Root-Path-Änderung: löst neuen DB-Scan aus

---

## 9. Seite 2: Scouting Flight (`scouting_flight.py`, Route: `/scouting`)

### Zweck

Ordner für Analyse auswählen, Jobs starten, Fortschritt beobachten.

### Abschnitte

#### 9.1 Folder View

- Bestehender `FolderTree` (mit Zusatzspalten: Audio-File-Count, DB-Status)
- Geclickte Ordner → werden direkt zur Job-Liste hinzugefügt,
  mit den aktuellen Hangar-Einstellungen (`use_embeddings`) als Job-Flags.
  Kein Bestätigungs-Dialog.
- Rooted an `AppState.root_path`; man kann nicht über diesen Ordner
  hinaus navigieren

#### 9.2 Job Controls

```
[▶ Start]  [⏸ Wait]  [▶ Resume]  [⏹ Stop after current]
[🔭 Scout everything]
```

- **Start:** Startet Abarbeitung der Job-Liste (sendet Jobs in `job_queue`)
- **Wait:** Sendet WAIT in `control_queue`; Button wechselt zu ausgegraut,
  Status-Zeile zeigt "⏳ Wait pending (nach aktuellem Batch)"
- **Resume:** Sendet RESUME; nur aktiv wenn Status = 'waiting'
- **Stop after current:** Sendet STOP; Walker beendet sich nach der
  aktuellen WAV-Datei sauber
- **Scout everything:** Fügt einen einzigen Job für den gesamten
  Ordnerbaum ab `root_path` zur Liste hinzu

#### 9.3 Job-Liste

Tabelle im RAM, aktualisiert per `ui.timer` (ca. 1s):


| # | Ordner              | Species | Embeddings | Status     | Fortschritt |
| --- | --------------------- | --------- | ------------ | ------------ | ------------- |
| 1 | /recordings/2024-05 | ✓      | ✓         | ✅ done    | 12/12       |
| 2 | /recordings/2024-06 | ✓      | –         | 🔄 running | 7/15        |
| 3 | /recordings/2024-07 | ✓      | ✓         | ⏳ pending | –          |

- Laufender Job zeigt zusätzlich: aktuellen Dateinamen + Fortschrittsbalken
- Abgeschlossene Jobs bleiben sichtbar (Protokoll der Session)
- Kein Löschen einzelner Jobs (nur gesamte Liste implizit beim Neustart)

#### 9.4 Status-Zeile

Einzeilige Zusammenfassung unterhalb der Job-Liste:

```
Walker: 🔄 running  |  Job 2/3  |  Datei 7/15: 20240601_053000.WAV
```

oder bei Wait:

```
Walker: ⏳ Wait pending (nach aktuellem Batch)
```

oder:

```
Walker: ⏸ Waiting  |  3 Jobs in Queue
```

---

## 10. Seite 3: Exploration Area (`exploration_area.py`, Route: `/exploration`)

### Zweck

Auswahl der aktiven Datenbank (lokal oder global) für alle nachfolgenden
Auswertungsseiten (Audio Player, Heatmap).

### Abschnitte

#### 10.1 Folder View (read-only)

- Gleicher `FolderTree` wie in Scouting Flight, aber **read-only**
  (kein Hinzufügen zur Job-Liste)
- Klick auf Ordner → setzt `AppState.active_db` auf die `birdnet_analysis.db`
  in diesem Ordner (falls vorhanden), sonst keine Aktion
- Visuelle Hervorhebung des aktuell aktiven Ordners

#### 10.2 DB-Typ Auswahl

Radio-Buttons oder Toggle oberhalb des Folder-Views:

- **🗂 Lokale Datenbank** (default)
- **🌐 Globale Datenbank**

Bei Auswahl "Global":

- Zeigt Pfad aus `AppState.global_index_path`
- Setzt `AppState.active_db_is_global = True`
- Header aller Seiten zeigt ab jetzt `"<pfad> (global)"`
- Folder-View wird ausgeblendet (nicht relevant bei globaler DB)

#### 10.3 Datenbank-Information

Unverändert aus bisheriger `database_overview.py`:

- Language, Confidence Threshold, Created Date
- Number of Species
- Button "🔄 Actualize Species List"

#### 10.4 Notes

Unverändert: Text-Area für User-Kommentare.

#### 10.5 Recording Files

Unverändert: Tabelle aller WAV-Files aus `metadata`-Tabelle.

#### 10.6 Species List (AG Grid)

Unverändert aus bisheriger `database_overview.py`:

- Sortierbare Tabelle mit Scientific / Local / Czech / Detections
- Selection → Button "▶ Play Species" (wechselt zu Audio Player
  mit vorgesetztem Filter)

---

## 11. Seiten 4 & 5: Audio Player / Heatmap

Beide Seiten bleiben **vollständig unverändert**.

Sie lesen `AppState.active_db` (wie bisher) — ob das eine lokale oder
globale DB ist, ist für diese Seiten transparent.

---

## 12. Offene Punkte / spätere Schritte


| Thema                        | Beschreibung                                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Sleep-Flag                   | Flag ist im AppState vorhanden; Sleep-Aufrufe an kritischen Stellen im Walker-Code werden in einem späteren Schritt implementiert |
| Embeddings in Folder-Tabelle | Spalte "Embeddings vorhanden" in FolderTree ist noch nicht implementiert                                                           |
| Globaler Index               | Struktur und Sync-Logik (`birdnet-global-sync`) noch nicht konzipiert                                                              |
| GPU-Konfiguration            | Übergabe des GPU/CPU-Flags an birdnet_analyzer noch nicht implementiert                                                           |
| Auftragsliste Persistenz     | Bewusst nicht persistent (RAM only); Wiederaufnahme über DB-Stand                                                                 |
| Walker CLI                   | `birdnet-walker` bleibt als eigenständiges Tool erhalten                                                                          |
