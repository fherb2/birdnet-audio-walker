# Konzept: Temporäre Aggregations-Datenbank

## 1. Ziel

Alle Seiten der Anwendung arbeiten ausschließlich gegen eine einzige temporäre
SQLite-Datenbank (`temp_db`). Diese wird beim Server-Start als leere Tempfile
angelegt. Der Nutzer wählt über `DbFolderTree` eine oder mehrere
Quell-Datenbanken aus; deren Inhalte werden im Hintergrund in die `temp_db`
kopiert. De-Selektion entfernt die Daten wieder. Alle bestehenden
Query-Funktionen (`db_queries.py`) laufen unverändert gegen `temp_db`.

---

## 2. Schema der temporären Datenbank

Die `temp_db` enthält alle Tabellen der bisherigen Quell-DBs, ergänzt um drei
neue Tabellen.

### 2.1 Übernommene Tabellen (mit Erweiterung)

```sql
-- Bestehende Tabellen, jeweils um source_db_id erweitert:
ALTER TABLE detections ADD COLUMN source_db_id INTEGER REFERENCES source_dbs(id);
ALTER TABLE metadata   ADD COLUMN source_db_id INTEGER REFERENCES source_dbs(id);
```

`processing_status` und `analysis_config` werden **nicht** in die `temp_db`
übernommen – sie verbleiben in den Quell-DBs.

### 2.2 Neue Tabelle: `source_dbs`

Verzeichnet alle aktuell in der `temp_db` enthaltenen Quell-Datenbanken.

```sql
CREATE TABLE source_dbs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    db_path       TEXT NOT NULL UNIQUE,   -- absoluter Pfad zur Quell-DB
    display_name  TEXT NOT NULL,          -- Ordnername (für UI)
    min_confidence REAL,                  -- aus analysis_config der Quell-DB
    added_at      TEXT NOT NULL           -- ISO-Timestamp
    -- Erweiterbar: gps_lat REAL, gps_lon REAL, ...
);
```

### 2.3 Neue Tabelle: `local_names`

Lokale Vogelnamen der aktuell eingestellten Sprache. Ersetzt das bisherige
`labels`-Dict, das durch den ganzen Call-Stack durchgereicht wurde.

```sql
CREATE TABLE local_names (
    scientific_name TEXT PRIMARY KEY,
    local_name      TEXT NOT NULL
);
```

### 2.4 Neue Tabelle: `species_list`

Wird nach jedem Add/Remove vollständig neu aufgebaut (analog zur bisherigen
`create_species_list_table`, aber dediziert für `temp_db`).

```sql
CREATE TABLE species_list (
    scientific_name TEXT PRIMARY KEY,
    count_high      INTEGER,
    count_low       INTEGER,
    score           REAL
);
```

---

## 3. Lebenszyklus der temp_db

### 3.1 Server-Start

1. `tempfile.NamedTemporaryFile(suffix='.db', delete=False)` anlegen
2. Schema initialisieren (alle Tabellen anlegen, leer)
3. `local_names` mit der konfigurierten Sprache befüllen
4. Pfad in `AppState.active_db` speichern
5. **Keine** Quell-DB vorauswählen – `source_dbs` bleibt leer

`AppState.available_dbs` entfällt (nicht mehr benötigt).

### 3.2 DB hinzufügen (ADD)

Auftrag: `{'op': 'add', 'db_path': Path(...)}`

Schritte im `temp_db_process`:
1. Eintrag in `source_dbs` anlegen, `source_db_id` merken
2. `min_confidence` aus `analysis_config` der Quell-DB lesen, in `source_dbs` speichern
3. Alle Zeilen aus `metadata` der Quell-DB kopieren, `source_db_id` setzen
4. Alle Zeilen aus `detections` der Quell-DB kopieren, `source_db_id` setzen
5. `species_list` neu aufbauen (`_rebuild_species_list`)

### 3.3 DB entfernen (REMOVE)

Auftrag: `{'op': 'remove', 'db_path': Path(...)}`

Schritte:
1. `source_db_id` aus `source_dbs` nachschlagen
2. `DELETE FROM detections WHERE source_db_id = ?`
3. `DELETE FROM metadata WHERE source_db_id = ?`
4. `DELETE FROM source_dbs WHERE id = ?`
5. `species_list` neu aufbauen

### 3.4 Sprache neu laden (RELOAD_LABELS)

Auftrag: `{'op': 'reload_labels', 'language_code': str, 'labels': dict}`

Schritte:
1. `DELETE FROM local_names`
2. `INSERT INTO local_names` für alle Einträge des neuen `labels`-Dict
3. Kein Rebuild von `species_list` nötig (Lokalnamen sind dort nicht enthalten)

### 3.5 Server-Stop

Tempfile wird gelöscht (via `atexit` oder explizitem Shutdown-Hook).

---

## 4. temp_db_process

### 4.1 Eigenschaften

- Permanenter `multiprocessing.Process` (Spawn), analog zum Scout-Prozess
- Wird beim Server-Start gestartet, läuft die gesamte Sitzung
- Verarbeitet Aufträge **sequenziell** aus der Queue
- Kommuniziert Status über `shared_state` (für Spinner in der GUI)

### 4.2 Erweiterung QueueBundle

```python
@dataclass
class QueueBundle:
    job_queue:      Queue   # Main → Scout
    progress_queue: Queue   # Scout → Main
    control_queue:  Queue   # Main → Scout (WAIT/RESUME/STOP)
    temp_db_queue:  Queue   # Main → TempDbProcess  ← NEU
    shared_state:   dict
```

### 4.3 Auftragsformat

```python
# Add
{'op': 'add',    'db_path': '/abs/path/to/birdnet_analysis.db'}

# Remove
{'op': 'remove', 'db_path': '/abs/path/to/birdnet_analysis.db'}

# Reload labels
{'op': 'reload_labels', 'language_code': 'de', 'labels': {sci: local, ...}}

# Shutdown
{'op': 'shutdown'}
```

### 4.4 Status in shared_state

```python
shared_state['temp_db'] = {
    'running': bool,    # True während ein Auftrag läuft → Spinner
    'label':   str,     # z.B. 'Loading Mai_Wald…' / 'Removing Juni_Wiese…'
    'db_path': str,     # Pfad zur Tempfile (für GUI-Zugriff)
}
```

### 4.5 Prozess-Einstiegspunkt

```python
def run_temp_db_process(
    temp_db_path: str,        # Pfad zur bereits angelegten Tempfile
    queue: Queue,             # temp_db_queue aus QueueBundle
    shared_state: dict,       # Manager().dict()
) -> None: ...
```

---

## 5. Integration in AppState

```python
@dataclass
class AppState:
    root_path:        Path
    active_db:        Optional[Path]   # zeigt immer auf temp_db (nach Init)
    read_only:        bool = False
    # available_dbs entfällt
    shared_state:     dict = ...
    # ... rest unverändert
```

`active_db` wird nach Anlegen der Tempfile gesetzt und danach nie mehr geändert.

---

## 6. DbFolderTree-Integration

`DbFolderTree.on_change` wird mit der neuen Menge selektierter Pfade aufgerufen.
Der aufrufende Code (Hangar oder eine neue DB-Auswahl-Seite) vergleicht die
neue Menge mit dem aktuellen Inhalt von `source_dbs` und schickt die Differenz
als ADD/REMOVE-Aufträge in die `temp_db_queue`.

```python
def _on_db_selection_change(selected: set[Path]) -> None:
    current = _get_loaded_db_paths()          # SELECT db_path FROM source_dbs
    to_add    = selected - current
    to_remove = current - selected
    for p in to_remove:
        bundle.temp_db_queue.put({'op': 'remove', 'db_path': str(p)})
    for p in to_add:
        bundle.temp_db_queue.put({'op': 'add',    'db_path': str(p)})
```

---

## 7. Änderungen an bestehenden Komponenten

### 7.1 db_queries.py

- `search_species_in_list`: JOIN auf `local_names` statt `labels`-Parameter
- `query_detections`: JOIN auf `local_names` statt `labels`-Parameter
- `get_species_list_with_counts`: analog
- `create_species_list_table`: neue dedizierte Funktion
  `rebuild_species_list_in_temp_db(temp_db_path)` – schreibt **nur** in
  `temp_db`, nie in Quell-DBs
- `labels`-Parameter aus allen Funktionen **langfristig** entfernen
  (Übergangsphase: Parameter bleibt als deprecated optional erhalten)

### 7.2 main.py / _startup_tasks

- `active_db` wird nicht mehr auf erste gefundene DB gesetzt
- Tempfile anlegen, Schema initialisieren, `local_names` befüllen
- `temp_db_process` starten (analog zu Scout-Prozess)
- `available_dbs`-Scan entfällt

### 7.3 layout.py (Statusleiste)

Neuer prominenter Hinweis wenn `source_dbs` leer ist:

> ⚠️ No database selected – please select a folder in the DB Overview.

### 7.4 Schreiboperationen

Außerhalb des Scouting Flight gibt es keine schreibenden Zugriffe auf
Quell-DBs mehr, bis auf:
- **Notizen**: werden deaktiviert (ausgegraut) bis eine dedizierte
  Einzeldatenbank-Verwaltungsseite implementiert ist

### 7.5 Exploration Area

Zeigt Aggregat-Statistiken aus der `temp_db`:

| Kennzahl | SQL |
|---|---|
| Erkennungen gesamt | `SELECT COUNT(*) FROM detections` |
| Unterschiedliche Species | `SELECT COUNT(*) FROM species_list` |
| Ausgewählte DBs | `SELECT COUNT(*) FROM source_dbs` |
| Gesamt-Soundzeit | `SELECT SUM(duration_seconds) FROM metadata` |
| Ø Erkennungen / Stunde | `COUNT(*) / (SUM(duration_seconds) / 3600.0)` |

---

## 8. Offene Punkte (spätere Phasen)

- GPS-Metadaten in `source_dbs` (Spalten vorbereitet)
- Dedizierte Einzeldatenbank-Verwaltungsseite (Notizen, Metadaten-Editierung)
- Embeddings in `temp_db` (DiskANN-Integration, separates Konzept)
- Langfristiges Entfernen des `labels`-Parameters aus allen API-Funktionen