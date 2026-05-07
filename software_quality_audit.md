# Code-Analyse: Gefundene Fehler und Probleme

Nach einer systematischen Durchsicht der gesamten Codebasis habe ich folgende Fehler, Inkonsistenzen und potenzielle Probleme identifiziert. Die Liste ist nach Schweregrad geordnet.

---

## 🔴 Kritische Fehler

### 1. Fehlende Funktion `get_db_connection` in `database.py`
**Datei:** `database.py`  
**Betroffene Funktionen:** `get_db_meta_data`, `set_db_meta_data`, `get_utc_methods`, `add_utc_method`

Diese Funktionen rufen `get_db_connection(db_path)` auf, aber eine solche Funktion ist in `database.py` nirgends definiert. Sie existiert nur in `db_queries.py`. Ein Aufruf würde daher einen `NameError` auslösen. Da andere Module (z. B. `db_file_prep.py`, `exploration_area.py`) die korrekt definierte Version aus `db_queries.py` importieren, tritt der Fehler derzeit nicht in Erscheinung – es handelt sich jedoch um eine tickende Zeitbombe.

**Auswirkung:** Jeder direkte Import aus `database` und folgender Aufruf dieser Funktionen lässt das Programm abstürzen.

---

### 2. GPU-Watchdog läuft auch im reinen CPU-Modus und löst Fehlalarm aus
**Datei:** `scout_watchdog.py` in Verbindung mit `scout_process.py`

Der Watchdog überwacht die GPU-Auslastung (via `nvidia-smi`). Die Bedingung für einen Hang ist:
- `birdnet_active == True` UND
- GPU-Auslastung < 20 % für ≥ 30 s

Das Problem: `birdnet_active` wird im `scout_process` **unabhängig vom Gerät** auf `True` gesetzt – also auch dann, wenn BirdNET mit `device='CPU'` läuft. Sobald der Benutzer in den Einstellungen `use_gpu=False` setzt und eine Analyse startet, wird die GPU naturgemäß nicht ausgelastet, der Watchdog interpretiert das als Hang und **terminiert den Scout-Prozess fälschlicherweise**.

**Auswirkung:** Vogelanalyse mit CPU ist nicht möglich, ohne dass der Watchdog nach 30 s eingreift.

---

### 3. Temporäre Datenbank-Indizes werden unter bestimmten Bedingungen nicht wieder aufgebaut
**Datei:** `temp_db_process.py`, Funktion `_handle_add`

Um den Massenimport zu beschleunigen, werden vor dem Einfügen die Detektions-Indizes gelöscht:

```python
temp_conn.execute("DROP INDEX IF EXISTS idx_detections_species")
temp_conn.execute("DROP INDEX IF EXISTS idx_detections_segment_start")
temp_conn.execute("DROP INDEX IF EXISTS idx_detections_source")
```

Die Wiederherstellung erfolgt nur, wenn die Operations-Queue *leer* ist:

```python
if queue is None or queue.empty():
    temp_conn.execute("CREATE INDEX IF NOT EXISTS ...")
    _rebuild_species_list(temp_conn)
```

Wenn nun schnell hintereinander Operationen eintreffen (z. B. `ADD` gefolgt von `REMOVE`), stellt `_handle_add` die Indizes nicht wieder her (weil die Queue beim Aufruf nicht leer war). Das nachfolgende `REMOVE` erstellt die Indizes ebenfalls nicht, da es nur löscht. **Die Indizes bleiben dann dauerhaft verloren**, bis ein weiteres `ADD` bei leerer Queue die Wiederherstellung anstößt.

**Auswirkung:** Langsame Query-Performance in der Exploration Area und im Audio Player, ohne dass der Benutzer den Grund erkennt.

---

## 🟠 Mittelschwere Fehler

### 4. `_rebuild_folder` setzt `min_conf=0.0` statt des aktuellen Cockpit-Wertes
**Datei:** `pages/scouting_flight.py`, Funktion `_rebuild_folder`

```python
job = ScanJob(
    folder_path=folder,
    scan_embeddings=state.use_embeddings,
    rescan_species=True,
    min_conf=0.0,  # set at job start from cockpit
)
```

Der tatsächlich gewünschte Wert (aus `min_conf_input`) wird zuvor korrekt berechnet (`conf = float(min_conf_input.value or 0.4)`), aber nicht an den Job übergeben. Die Tabelle zeigt daher für Rebuild-Jobs `min_conf = 0.00`, bis der Job gestartet und der Wert in `_on_start` überschrieben wird. Das verwirrt den Anwender.

**Auswirkung:** Falsche Anzeige in der Job-Liste bis zum Start.

---

### 5. Num2words-Konvertierung hart auf Deutsch fixiert
**Datei:** `player.py`, Methode `_get_announcement_text`

```python
conf_percent_words = num2words(conf_percent, lang='de')
```

Egal welche Sprache für die Vogelnamen gewählt wurde – die Konfidenz wird immer auf Deutsch angesagt. Bei englischen oder tschechischen Ansagen wirkt das fehl am Platz.

**Auswirkung:** Mischsprachige TTS-Ausgabe, die nicht zur sonstigen Sprachauswahl passt.

---

### 6. Code-Duplizierung: `get_db_meta_data` und `set_db_meta_data` in zwei Modulen
**Dateien:** `database.py` und `db_queries.py`

Diese und weitere Datenbankfunktionen sind doppelt vorhanden, teils mit unterschiedlicher Implementierung (z. B. fehlende `get_db_connection` in `database.py`). Es existiert keine klare Trennung in „lesende“ und „schreibende“ Datenbankzugriffe. Module, die auf die falsche Version zugreifen, könnten unerwartete Fehler erhalten.

---

## 🟡 Kleinere Fehler / Code Smells

### 7. Mögliche inkonsistente `_on_species`-Callback-Überschreibung
**Datei:** `pages/audio_player.py`

Nach der Erstellung der `SpeciesSearch`-Komponente wird `species_search._on_select` mit einer neuen Lambda überschrieben, die zusätzlich den Xeno-Canto-Button steuert. Der ursprüngliche Callback (über den Konstruktor) führt hingegen nur `setattr` aus. Die Art wird dadurch zweimal gesetzt (kein Fehler, aber unsauber und schwer wartbar).

---

### 8. `spectrogram`-Wrapper unterdrückt *alle* Ausgaben
**Datei:** `scout_process.py`, `_capture_tf_output`

Der Context Manager setzt `sys.stdout` und `sys.stderr` global um. In einem Multiprocessing-Prozess funktioniert das, könnte aber andere Python-Bibliotheken stören, die auf die Standard-Streams schreiben (z. B. Logging). Besser wäre, nur die TensorFlow-Logger stummzuschalten.

---

### 9. `run_with_loading` verwendet veraltete NiceGUI-Funktion
**Datei:** `task_status.py`

```python
result = await run.io_bound(func, *args, **kwargs)
```

Die Funktion `run.io_bound` ist in aktuellen NiceGUI-Versionen durch `run.cpu_bound` / `run.io_bound` ersetzt? (Abhängig von der eingesetzten Version). Falls die API nicht mehr existiert, führt dies zu einem Importfehler.

---

### 10. `shared_state['birdnet_active']` wird nicht geschützt
**Datei:** `scout_process.py`

Das Flag wird im selben Block gesetzt und gelöscht, aber bei einer Exception könnte es auf `True` hängen bleiben. Zwar wird es im `finally`-Block nie explizit zurückgesetzt, aber im äußeren `try` wird es nach der Analyse auf `False` gesetzt. Wenn jedoch eine Exception *vor* dem Zurücksetzen auftritt (z. B. `analyze_file` selbst), bleibt das Flag `True` und der Watchdog würde weiterhin die GPU überwachen. Ein `try…finally` um das Flag wäre sicherer:

```python
try:
    bundle.shared_state['birdnet_active'] = True
    # ... Analyse ...
finally:
    bundle.shared_state['birdnet_active'] = False
```

---

## 🔧 Verbesserungsvorschläge (nicht zwingend Fehler)

- **Temp-DB-Index-Problem:** Statt die Indizes zu löschen, könnte man `PRAGMA synchronous=OFF` und `PRAGMA journal_mode=MEMORY` verwenden und die Indizes einfach bestehen lassen, oder sie immer nach jeder vollständigen Batch-Operation (z. B. nach Verarbeitung aller gesendeten Nachrichten) neu bauen.
- **GPU-Watchdog:** Sollte nur gestartet werden, wenn `app_state.use_gpu == True`, oder sollte `use_gpu` abfragen und sich bei CPU-Modus deaktivieren.
- **Fehlende `get_db_connection` in `database.py`:** Entweder die Funktion dort definieren oder die doppelten Funktionen entfernen und stattdessen aus `db_queries` importieren.
- **`_rebuild_folder` Korrektur:** `job.min_conf = conf` statt `0.0`.

---

## Zusammenfassung

| # | Schwere | Kurzbeschreibung |
|---|--------|------------------|
| 1 | 🔴 kritisch | `get_db_connection` fehlt in `database.py` |
| 2 | 🔴 kritisch | GPU-Watchdog beendet CPU-Analysen fälschlich |
| 3 | 🔴 kritisch | Temp-DB verliert Indizes bei schnellen Queue-Operationen |
| 4 | 🟠 mittel | `_rebuild_folder` zeigt falsche min_confidence |
| 5 | 🟠 mittel | `num2words` hart auf Deutsch, unabhängig von Sprache |
| 6 | 🟠 mittel | Doppelt definierte DB-Funktionen in `database.py` / `db_queries.py` |
| 7 | 🟡 gering | Überschriebener Callback in `audio_player.py` |
| 8 | 🟡 gering | Globales Unterdrücken von stdout/stderr |
| 9 | 🟡 gering | Möglicherweise veraltete `run.io_bound` API |
| 10 | 🟡 gering | `birdnet_active` ohne try-finally bei Analyse-Ausnahme |

Die Anwendung ist insgesamt stabil und funktionsfähig, jedoch sollten die kritischen Punkte 1–3 vor einem produktiven Einsatz behoben werden.