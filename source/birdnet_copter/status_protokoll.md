# Status Protokoll: birdnet-copter

---

## Eintrag 2 – 2026-03-07

### Erledigte Schritte

#### Kopierliste aus birdnet_walker_alt nach birdnet_copter

| File | Aktion |
|---|---|
| `birdnet_analyzer.py` | Komplett kopiert, unverändert |
| `audiomoth_import.py` | Komplett kopiert, unverändert |
| `species_translation.py` | Komplett kopiert, unverändert |
| `birdnet_labels.py` | Komplett kopiert, unverändert |
| `config.py` | Kopiert, Änderungen noch ausstehend: `DEVICE` entfernen (kommt aus AppState.use_gpu); `QUEUE_SIZE` und `SLEEP_INTERVAL` entfernen |
| `database.py` | Kopiert, Änderungen noch ausstehend: `db_writer_process()` löschen; Import-Bug in `check_indices_exist()` und `drop_all_indices()` fixen (`from config import` → `from .config import`) |
| `progress.py` | Nicht kopiert – entfällt (Fortschritt läuft über progress_queue → GUI) |
| `main.py` (walker) | Nicht kopiert – entfällt |
| `__main__.py` (walker) | Nicht kopiert – entfällt |
| `__init__.py` (walker) | Nicht kopiert – entfällt |

#### walker_process.py  ✅ (neues File, als 2 Artefakte erstellt)

**Struktur:**
- `run_walker_process(bundle, translation_list, birdnet_labels, use_gpu)` — Prozess-Einstiegspunkt, Endlosschleife, wartet auf Jobs via `bundle.job_queue.get(block=True)`
- `_process_folder(job, bundle, translation_list, birdnet_labels, use_gpu, stop_flag, wait_flag)` — inline Folder-Verarbeitung (bewusst nicht als Top-Level-Funktion, kann später refaktoriert werden)
- `_batch_insert(...)` — Wrapper um `database.batch_insert_detections`; löst Species-Namen intern auf ohne pandas-DataFrame zu übergeben
- `_lookup_species(scientific_name, translation_list, birdnet_labels)` — ersetzt `translate_species_name()` aus `species_translation.py`; arbeitet auf Liste von Dicts statt pandas DataFrame
- `_send_progress(bundle, job)` — schreibt Progress-Snapshot in `progress_queue`
- `_check_control(bundle, stop_flag, wait_flag)` — drainiert `control_queue` non-blocking, aktualisiert Flags
- `_block_until_resume(bundle, job, stop_flag, wait_flag)` — blockiert bis RESUME oder STOP
- `_capture_tf_output()` — Context Manager, unterdrückt TensorFlow stdout/stderr

**Wait/Stop-Logik:**
- `stop_flag` und `wait_flag` als einelementige Listen (mutierbar per Referenz)
- `stop_flag` wird pro Job zurückgesetzt; `wait_flag` bleibt über Jobs hinweg aktiv bis RESUME
- Kontrolle wird nach jeder WAV-Datei geprüft (nie mitten in einem BirdNET-Batch)
- Bei WAIT vor Job-Start: Job wartet sofort, bevor er beginnt

**Entscheidungen:**
- `translation_list` wird als `list[dict]` übergeben (nicht pandas DataFrame) — einfachere Serialisierung für multiprocessing spawn
- `_lookup_species` repliziert die Lookup-Logik aus `species_translation.translate_species_name()` ohne pandas
- `_batch_insert` baut intern einen minimalen pandas DataFrame für den Aufruf von `database.batch_insert_detections()` (Übergangs-Lösung; kann später refaktoriert werden)
- `use_gpu` wird als bool übergeben; der device-String ('GPU'/'CPU') wird im Walker intern gebildet
- Folder-Processing ist bewusst inline gelassen (strukturelle Verbesserung für später)
- Indizes werden nur erstellt wenn kein Stop-Signal aktiv war

---

## Eintrag 4 – 2026-03-07

### Erledigte Schritte

#### layout.py – angepasst (bestehendes File)
- `_relative_db_label()` erweitert: gibt bei `active_db_is_global=True` den `global_index_path` mit Suffix `(global)` zurück
- App-Name `"birdnet-copter"` als `text-h6 font-bold` Label direkt neben Hamburger-Button eingefügt
- Navigation Drawer: alte Einträge (Database Overview, Audio Player, Heatmap) ersetzt durch neue Reihenfolge: Hangar (`/`), Scouting Flight (`/scouting`), Exploration Area (`/exploration`), 🎵 Audio Player (`/audio-player`), 🌡️ Heatmap (`/heatmap`)

#### config.py – angepasst (bestehendes File)
- `DEVICE = 'GPU'` entfernt (device-String wird in walker_process.py aus `use_gpu` gebildet)
- `QUEUE_SIZE` und `SLEEP_INTERVAL` entfernt (alte DB-Writer-Queue-Logik entfällt)

#### database.py – angepasst (bestehendes File)
- `db_writer_process()` komplett gelöscht
- Import-Bug gefixt in `check_indices_exist()` und `drop_all_indices()`: `from config import INDEX_NAMES` → `from .config import INDEX_NAMES`

#### pages/__init__.py – angepasst (bestehendes File)
Inhalt ersetzt durch:
```python
from . import hangar            # noqa: F401
from . import scouting_flight   # noqa: F401
from . import exploration_area  # noqa: F401
from . import audio_player      # noqa: F401
from . import heatmap_page      # noqa: F401
```

### Noch ausstehend (für nächsten Chat)
- `hangar.py` – neue Page (Route `/`)
- `scouting_flight.py` – neue Page (Route `/scouting`)
- `exploration_area.py` – neue Page (Umbau aus `database_overview.py`, Route `/exploration`)

---

## Eintrag 3 – 2026-03-07

### Erledigte Schritte

#### app_state.py – weitere Ergänzungen
Zusätzlich zu Eintrag 1: Nach `active_db_is_global: bool = False` eingefügt:
```python
    # Inter-process shared state (multiprocessing.Manager().dict())
    shared_state: Optional[Any] = None
```

#### config.py – ausstehende Änderungen (noch offen)
- `DEVICE = 'GPU'` entfernen (device-String wird in walker_process.py aus `use_gpu` gebildet)
- `QUEUE_SIZE` und `SLEEP_INTERVAL` entfernen (alte Multiprocessing-Queue-Logik entfällt)

#### database.py – ausstehende Änderungen (noch offen)
- `db_writer_process()` löschen
- Import-Bug fixen: `from config import INDEX_NAMES` → `from .config import INDEX_NAMES` in `check_indices_exist()` und `drop_all_indices()`

#### main.py  ✅ (neues File, ersetzt birdnet_play/main.py, als Artefakt erstellt)

**Aufgaben:**
- CLI-Argumente: nur noch `input_path` (default: Home-Verzeichnis) und `--read-only`; CLI-Playback-Modus entfällt komplett
- `multiprocessing.set_start_method('spawn')` als erstes in `main()`
- `detect_hardware()` → `hw_info` → in `AppState`
- `AppState` initialisiert mit `root_path`, `read_only`, `hw_info`, `use_gpu=hw_info.has_nvidia_gpu`
- `multiprocessing.Manager()` gestartet → `shared_state` (Manager-Dict) angelegt mit `jobs=[]` und `walker_status='idle'`
- `shared_state` wird als `app_state.shared_state` abgelegt (nicht als `app.state`)
- `create_queues(shared_state)` → `bundle`
- Species-Translation: `download_species_table()` → DataFrame → `to_dict(orient='records')` → `translation_list`
- BirdNET-Labels: `load_birdnet_labels(DEFAULT_LANGUAGE)`
- Walker-Prozess gestartet als `daemon=True` via `_start_walker()`
- SIGTERM/SIGINT-Handler: sendet `shutdown_walker()`, joined Walker, dann `sys.exit(0)`
- `app.state.app_state` und `app.state.bundle` gesetzt
- `_on_startup` als async Task: scannt DBs, setzt `active_db`, liest `language_code`
- `from . import pages` registriert alle Routen
- Nach `ui.run()` (Shutdown): `shutdown_walker()`, Walker joinen, `manager.shutdown()`

**Entscheidungen:**
- `shared_state` als Feld in `AppState` (nicht als separates `app.state`-Attribut)
- Walker-Prozess ist `daemon=True` – wird bei Hauptprozess-Exit automatisch beendet
- Language beim Start fix auf `DEFAULT_LANGUAGE` aus `config.py`; Hangar-seitige Language-Auswahl ist späterer Schritt

---

## Eintrag 1 – 2026-03-07

### Aufgabe
Zusammenführung von `birdnet-walker` und `birdnet-play` zu `birdnet-copter`.
Startpunkt: bestehender `birdnet_play/`-Code (NiceGUI) wird zu `birdnet_copter/` umgebaut
und um Walker-Funktionalität als Hintergrundprozess erweitert.

Das finalisierte Konzept liegt vor als `Konzept_der_Zusammenführung.md`.
Der bestehende Code liegt vor in `projectcontent.txt` (birdnet_play) und
`walkerContent.txt` (birdnet_walker) sowie `sharedContent.txt` (shared/).

### Rahmenbedingungen
- `birdnet_play/` wurde bereits in `birdnet_copter/` umbenannt.
- Die `shared/`-Module wurden bereits nach `birdnet_copter/` kopiert.
- `pynvml` wurde bereits installiert (als Dependency in pyproject.toml eingetragen).

---

### Erledigte Schritte

#### pyproject.toml
Folgende Änderungen wurden beschrieben (zur manuellen Übernahme):
- `name` geändert von `"birdnet-walker"` auf `"birdnet-copter"`
- Paket `birdnet_play` ersetzt durch `birdnet_copter` in der packages-Liste
- Eintrag `{ include = "shared", from = "source" }` entfernt (shared ist jetzt Teil von birdnet_copter)
- Dependency `psutil = "^6.0.0"` hinzugefügt (nach `nicegui`-Zeile)
- `pynvml` als Dependency hinzugefügt und installiert
- Entry Point `birdnet-copter = "birdnet_copter.main:main"` hinzugefügt
- Entry Point `birdnet-play` bleibt erhalten

#### app_state.py
Folgende Ergänzungen wurden beschrieben (zur manuellen Übernahme):

Import-Ergänzung:
```python
from typing import Any, Dict, List, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from .hardware import HardwareInfo
```

Neuer Block nach `language_code: str = 'de'`:
```python
    # Hardware & inference configuration
    hw_info: Optional['HardwareInfo'] = None
    use_gpu: bool = True
    use_embeddings: bool = False
    global_index_path: Optional[Path] = None

    # Walker / job queue state (read-only view for GUI)
    jobs: List[Dict] = field(default_factory=list)
    walker_status: str = 'idle'   # 'idle'|'running'|'wait_pending'|'waiting'

    # Global DB
    active_db_is_global: bool = False
```

#### hardware.py  ✅ (neues File, als Artefakt erstellt)
- Dataclass `HardwareInfo` mit Feldern:
  `has_nvidia_gpu`, `gpu_name`, `gpu_vram_gb`,
  `gpu_sm_count`, `gpu_cores_per_sm`, `gpu_shaders`,
  `cpu_count_physical`, `cpu_count_logical`, `cpu_count_for_inference`,
  `sleep_flag`, `ram_total_gb`
- Funktion `detect_hardware() -> HardwareInfo`
- GPU-Detection via `pynvml` (Name, VRAM)
- SM-Count und Cores-per-SM via `ctypes`/`libcuda.so` (`cudaGetDeviceProperties`)
- `gpu_shaders = gpu_sm_count * gpu_cores_per_sm`
- Lookup-Tabelle `_CORES_PER_SM` für Compute Capability → Cores per SM
  (Fermi bis Hopper abgedeckt; unbekannte CC → `cores_per_sm = None`)
- Bei nicht verfügbarer GPU oder libcuda: alle GPU-Felder `None`
- CPU via `psutil.cpu_count(logical=True/False)`
- `cpu_count_for_inference = logical - 2` wenn `logical >= 3`, sonst `logical`
- `sleep_flag = True` wenn `logical < 3`
- RAM via `psutil.virtual_memory().total`

**Entscheidungen:**
- Kein Fallback auf Lookup-Tabelle für SM-Count: bei fehlendem libcuda → `None`
- Alle drei GPU-Shader-Felder werden gespeichert (sm_count, cores_per_sm, shaders)

#### job_queue.py  ✅ (neues File, als Artefakt erstellt)
- Dataclass `ScanJob` mit Feldern:
  `folder_path`, `rescan_species`, `scan_embeddings`, `min_conf`,
  `job_id` (uuid), `status`, `added_at`, `started_at`, `finished_at`,
  `files_total`, `files_done`, `current_file`, `error_msg`
- Dataclass `QueueBundle` hält alle 3 Queues + shared_state:
  `job_queue` (Main→Walker), `progress_queue` (Walker→Main),
  `control_queue` (Main→Walker), `shared_state` (Manager().dict())
- Funktion `create_queues(shared_state) -> QueueBundle`
  — erzeugt alle Queues; muss im Main-Prozess vor spawn aufgerufen werden
- Funktion `add_job(bundle, job)` — trägt Job in shared_state['jobs'] ein und sendet ihn an Walker
- Funktion `send_control(bundle, signal)` — sendet WAIT/RESUME/STOP
- Funktion `shutdown_walker(bundle)` — sendet Poison Pill (None)
- Funktion `drain_progress_queue(bundle)` — liest alle verfügbaren Meldungen
  aus progress_queue, aktualisiert shared_state['jobs'] und shared_state['walker_status'];
  non-blocking, für ui.timer-Aufruf (~1s) ausgelegt

**Entscheidungen:**
- Queues werden nicht als Modul-Level-Instanzen angelegt, sondern per Init-Funktion
  erzeugt (sauber für multiprocessing 'spawn')
- `drain_progress_queue` aktualisiert direkt shared_state (nicht nur Rückgabeliste)
- Steuersignale als Modul-Konstanten: `SIGNAL_WAIT`, `SIGNAL_RESUME`, `SIGNAL_STOP`, `SIGNAL_SHUTDOWN`



---

## Eintrag 6 – 2026-03-07

### Erledigte Schritte

#### job_queue.py – `_progress_msg` umbenannt

`_progress_msg()` von privatem zu öffentlichem Namen umbenannt: `progress_msg()`.
Interner Aufruf in `add_job()` entsprechend angepasst.

#### scouting_flight.py – Import angepasst

Import von `_progress_msg` auf `progress_msg` umgestellt (zwei Aufrufstellen im File).

#### streamlit_utils.py → utils.py

Datei umbenannt von `streamlit_utils.py` zu `utils.py`.
Streamlit-spezifische Funktion `initialize_session_state_from_args()` entfernt
(inkl. `import streamlit as st`). Verbleibende Funktion: `find_databases_recursive()`.

#### hangar.py – Import korrigiert

Import korrigiert von `from ..db_queries import scan_for_databases`
auf `from ..utils import find_databases_recursive`.
Aufruf im `_confirm_root`-Handler entsprechend angepasst.

#### pyproject.toml – bereits erledigt (vom Nutzer)

Entry Point `birdnet-copter`, Paketname, Dependencies (`psutil`, `pynvml`),
Entfernen des `shared`-Eintrags — alle Anpassungen laut Eintrag 1 manuell übernommen.

### Stand

Die Implementierung von `birdnet-copter` ist vollständig. Alle im Konzept
`Konzept_der_Zusammenführung.md` für diesen Schritt vorgesehenen Files sind
erstellt oder angepasst. Die bewusst offen gelassenen Punkte (Sleep-Flag,
Embeddings-Spalte im FolderTree, Globaler Index, GPU-Flag-Übergabe,
Language-Auswahl im Hangar) sind als spätere Schritte im Konzept dokumentiert.
Nächster Schritt: Testen und Debuggen.