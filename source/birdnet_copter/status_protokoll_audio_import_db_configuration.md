# Status Protokoll: konzept_audio_import_db_configuration + folder_metadata_scanner

Dieses Protokoll ersetzt die beiden vorherigen Einzelprotokolle und fasst den gesamten Implementierungsstand zusammen.

---

## Erledigte Schritte

### 1. `folder_metadata_scanner.py` – vollständig implementiert und getestet

Neues Modul unter `source/birdnet_copter/folder_metadata_scanner.py`.

Erfolgreich getestet gegen 153 AudioMoth-WAV-Files + 1 CONFIG.TXT. Ergebnis: 154 Files korrekt klassifiziert, 52 distinct Metadata-Keys extrahiert.

**Architektur: Registry-Pattern in 5 Sektionen:**
1. Datenstrukturen (`FileClass` Enum, `MetaDataDict` TypeAlias)
2. Klassifikator-Registry (`CLASSIFIERS`) – dateiname-agnostisch, inhaltbasiert
3. Parser-Registry (`PARSERS`) – je ein Parser pro FileClass
4. Dictionary-Builder (`_merge_into_dict`)
5. Public API (`scan_folder`) – synchron/blocking, Aufruf via `run_in_executor`

**Unterstützte FileClasses:** `WAV_GUANO`, `WAV_ICMT`, `WAV_PLAIN`, `AUDIO_GENERIC`, `AUDIOMOTH_CONFIG`, `UNKNOWN`

**Bibliotheken:** `mutagen` für Standard-Audio-Tags; GUANO/ICMT direkt auf Byte-Ebene; stdlib `wave` für WAV-Technicals.

**Bugs behoben:** `_parse_audiomoth_config`: `elif 'gain' in kl` → `elif kl == 'gain'` (verhinderte Überschreiben des Gain-Werts durch `Enable low gain range`).

**Übersprungene Files:** `.db`, `.db-wal`, `.db-shm`, `.hdf5`, `.h5` und versteckte Files (Prefix `.`).

**GUANO-Namespace-Keys** mit Prefix `guano:`, CONFIG.TXT-unbekannte Keys mit Prefix `cfg:`.

---

### 2. DB-Schema erweitert – `database.py` und `db_queries.py`

In `init_database()` in `database.py` nach dem `CREATE TABLE analysis_config`-Block und vor `conn.commit()` eingefügt:

**`db_meta_data`** – eine Zeile pro DB:
- `id` INTEGER PRIMARY KEY CHECK (id = 1)
- `gps_lat` REAL DEFAULT 90.0 (Nordpol = "kein Ort")
- `gps_lon` REAL DEFAULT 0.0
- `utc_time_method` TEXT
- `time_offset` TEXT DEFAULT '+00:00:00'
- `notes` TEXT DEFAULT '' (freies Notizfeld)
- `kv_blob` BLOB (gepickeltes Python-Dictionary)

Sofort mit `INSERT OR IGNORE` initialisiert.

**`utc_methods`** – Registry der UTC-Methoden:
- `name` TEXT PRIMARY KEY, `description` TEXT
- Befüllt mit: `GUANO_TIMESTAMP`, `ICMT_TIMESTAMP`, `FILENAME_PATTERN`, `FILESYSTEM_CTIME`

**Neue Funktionen in `db_queries.py`** (nach `vacuum_database()`):
- `get_db_meta_data(db_path)` – liest db_meta_data-Zeile als Dict
- `set_db_meta_data(db_path, **kwargs)` – aktualisiert Felder, pickelt kv_blob automatisch
- `get_kv_blob(db_path)` – liest und entpickelt kv_blob
- `get_utc_methods(db_path)` – gibt alle Methoden zurück
- `add_utc_method(db_path, name, description)` – registriert neue Methode (INSERT OR IGNORE)

`database.py` benötigte zusätzlich `from typing import Optional, Dict, List`.

---

### 3. `app_state.py` erweitert

Neue Felder für die DB-Config-Seite (nach den Walker-State-Feldern):
```python
dbprep_folder:         Optional[Path] = None
dbprep_scan_result:    Optional[Dict] = None
dbprep_mode:           str = 'create'        # 'create' | 'edit'
dbprep_selected_kv:    Dict = field(default_factory=dict)
dbprep_pending_gps:    Optional[tuple] = None
dbprep_pending_method: Optional[str] = None
dbprep_pending_offset: str = '+00:00:00'
dbprep_page_active:    bool = False
```

`dbprep_pending_gps`, `dbprep_pending_method`, `dbprep_pending_offset` überleben Seitenwechsel (im AppState statt im page-Dict). `dbprep_page_active` steuert die Header-Anzeige in `layout.py`.

---

### 4. `db_folder_tree.py` erweitert (Single-Select-Modus)

Neue Parameter:
- `single_select: bool = False`
- `on_select: Optional[Callable[[Optional[Path]], None]]`

Neue Property: `selected_folder` – gibt den einzelnen gewählten Pfad zurück.

`_on_checkbox_change()` erweitert um Single-Select-Logik (alle anderen deselektieren bei Auswahl).

**Hinweis:** Auf der DB-Config-Seite wird letztlich `FolderTree` (nicht `DbFolderTree`) verwendet – siehe Absprachen.

---

### 5. Navigation erweitert

**`layout.py`:** Navigationseintrag `('🗄', 'DB Configuration', '/db-config')` nach Hangar eingefügt.

**`layout.py` `_relative_db_label()`:** Wenn `app_state.dbprep_page_active` True ist, zeigt die zweite Header-Zeile den gewählten Ordner statt des Exploration-Status.

**`pages/__init__.py`:** `from . import db_file_prep` nach `hangar` eingefügt.

---

### 6. Neue Seite `db_file_prep.py` – Route `/db-config`

Vollständig implementiert und erfolgreich getestet.

**Block 2.1 – Header:**
- Dunkelrotes Banner zeigt aktuell gewählten Ordner.
- Header-Zeile 2 zeigt via `dbprep_page_active` den Ordner statt Exploration-Status.
- `dbprep_page_active` wird bei `on_disconnect` auf False zurückgesetzt.

**Block 2.2 – Ordner-Auswahl:**
- `FolderTree` (nicht `DbFolderTree`) – zeigt alle Ordner mit Audiofiles.
- Einzelauswahl. Bei Auswahl: Scan startet, Spinner erscheint, alle Sektionen rendern nach Scan-Ende.
- State überlebt Seitenwechsel: Bei Rückkehr wird der zuletzt gewählte Ordner wiederhergestellt.

**Block 2.3 – Metadaten-Tabelle:**
- Scrollbar (max. 700px). 4 Spalten: Checkbox, Key, Value (editierbar), Files.
- Radio-Button-Logik pro Key: Nur ein Value pro Key selektierbar.
- Rebuild mit `ui.timer(0.05, ...)` nach Selektion (verhindert Doppelklick-Problem).
- Button "Recreate Table" (`_start_scan`) startet Scan neu, löscht `rows_state`.
- Button "Add row" fügt manuelle leere Zeile hinzu (Duplikat-Key-Prüfung).
- Selektion triggert Live-Update von Sektion 2.5 via `page['refresh_kv_overview']`.
- `rows_state` im `page`-Dict gespeichert, überlebt Seitenwechsel.

**Block 2.4 – GPS/Karte:**
- `ui.leaflet()` wird **einmalig** beim Seitenaufruf gebaut (nicht bei jedem Scan-Ende) – NiceGUI-Bug bei `container.clear()` + Leaflet.
- `await m.initialized()` + `m.on('map-click', ...)` direkt in `db_file_prep()` im async Page-Kontext.
- Blaue Marker = distinct GPS-Punkte aus Metadaten. Nach Scan via `_update_map_markers()` aktualisiert.
- Alle GPS-Punkte identisch → roter Marker automatisch gesetzt, `dbprep_pending_gps` vorbelegt.
- GPS-Punkte unterschiedlich → nur blaue Marker, Warnung, kein roter Marker. Nutzer klickt Marker oder Karte.
- Roter Marker = finale Position. Klick auf Karte oder manuell in Eingabefelder setzt roten Marker.
- GPS wird **nicht** sofort in DB geschrieben, sondern in `state.dbprep_pending_gps` zwischengespeichert.
- Reset-Button setzt auf Nordpol (90.0/0.0).
- **Legende:** Direkt oberhalb der Koordinaten-Eingabe, innerhalb der GPS-section_card. Implementiert als zwei `ui.label`-Elemente mit Emoji-Symbolen in einer `ui.row`:
  - 🔵 GPS from metadata (suggestion)
  - 🔴 Selected position (will be saved)
- **Blaue Marker-Klicks** funktionieren **nicht** nativ in NiceGUI – bekannte Einschränkung, noch nicht gelöst.
- **Technische Erkenntnis zu statischen Bildern in NiceGUI:** `ui.image` und `ui.html` mit `<img>`-Tags funktionieren nicht innerhalb von `ui.column()`-Containern, die außerhalb des direkten Page-Render-Kontexts befüllt werden (wie `gps_map_container`). Auch Base64-kodierte Bilder und externe URLs sind betroffen. Emoji-Lösung als robuster Workaround gewählt.

**Block 2.5 – KV-Übersicht:**
- Zeigt Union aus DB-vorhandenen und neu selektierten Key-Value-Paaren.
- Symbole: 🟢 neu/selektiert, 🟡 in DB aber nicht selektiert (wird behalten), 🔴 (derzeit nie, da kein explizites Löschen implementiert).
- Live-Update bei Selektion in 2.3.
- Button "Metadaten mit DB abgleichen" (`_sync_kv_to_db`):
  - Startet mit `existing_kv`, überschreibt mit `selected`, übernimmt manuelle Edits aus `kv_edit_values`.
  - **Löscht nichts automatisch** – gelbe Einträge (in DB, nicht selektiert) bleiben erhalten.
  - Prüft ob DB existiert, gibt Warning-Notify wenn nicht.

**Block 2.6 – UTC-Methode:**
- Dropdown mit verfügbaren Methoden, aus Scan-Ergebnis ermittelt, beste Quelle als "Empfehlung" markiert.
- Globaler Zeitoffset (Format `+HH:MM:SS` oder `-HH:MM:SS`).
- UTC-Methode wird in `state.dbprep_pending_method`/`state.dbprep_pending_offset` gespeichert.
- "Save Method & Offset" triggert auch `_refresh_confirm_section()` via `page['refresh_confirm']`.
- Vorschau-Tabelle: UTC / Lokalzeit mit DST / Filename. Zeitzone via `timezonefinder`. DST-Übergänge mit orangefarbener Trennzeile.

**Block 5 – Create/Update Database:**
- Statusanzeige ✅/❌ für GPS und UTC-Methode.
- Button nur aktiv wenn beide gesetzt (`dbprep_pending_gps` oder DB-Wert vorhanden, und `dbprep_pending_method` oder DB-Wert vorhanden).
- Button-Label: "💾 Create Database" / "💾 Update Database" je nach Mode.
- Schreibt `pending_gps` und `pending_method`/`pending_offset` in DB, legt DB an falls nicht vorhanden.
- Nach Confirm: pending-Werte auf None/Default zurückgesetzt.

**Danger Zone:**
- Button "🗑 Delete all detections" mit Bestätigungsdialog.
- Löscht `detections` und `processing_status`.
- Ermöglicht danach Änderung von GPS und UTC-Methode (Konzept 1.2.3).

---

### 7. Landing Page – Route `/`

Neue Seite `source/birdnet_copter/pages/landing_page.py`.

**Drei Sektionen:**
1. **Basic Principles** – drei nummerierte Grundsätze: Ein Ordner = ein Gerät = ein Ort = eine DB; keine zeitliche Überschneidung; mehrere Ordner = globale Auswertung.
2. **Where do I go?** – 2-spaltiges Karten-Grid mit je Icon, Name, Kurzbeschreibung und "Go to X →"-Button für alle 6 Seiten.
3. **Application Description** – Platzhalter mit "Coming soon."

**Route-Änderungen:**
- Landing Page: `/` (neu)
- Hangar: `/` → `/hangar`
- Navigation in `layout.py`: `('🅗', 'Landing Page', '/')` als erster Eintrag, Hangar umbenannt zu `'Hangar (Technical Config)'` mit Route `/hangar`.
- `pages/__init__.py`: `from . import landing_page` als erster Import eingefügt.

**SVG-Datei:** `source/birdnet_copter/pages/static/icons/helipad.svg` – grüner Kreis mit weißem Innenring und weißem H, viewBox 100×100.

**Navigation-Symbol:** `🅗` (U+1F157, "Negative Squared Latin Capital Letter H") – passt ohne Sonderbehandlung in die bestehende Nav-Listen-Struktur.

---

### 8. Freigabe-Prüfung in `scouting_flight.py`

Neue Funktion `_is_folder_ready(folder)` (nach den Imports, vor `_get_state()`):
- Prüft: `birdnet_analysis.db` existiert UND `utc_time_method` in `db_meta_data` gesetzt.
- lat/lon wird **nicht** geprüft (Nordpol ist gültiger Wert für "kein Ort").

Einzelner `+`-Button: Prüft Ordner, zeigt Warning-Notify wenn nicht freigegeben, fügt nicht hinzu.

"Scout everything": Filtert nicht-freigegebene Ordner stillschweigend heraus (List Comprehension mit `_is_folder_ready(f)`).

---

### 8. `NotesCard` – GUI-Element für Datenbanknotizen

Neues wiederverwendbares GUI-Element `source/birdnet_copter/gui_elements/notes_card.py`.

**Funktionsumfang:**
- Textarea gebunden an `db_meta_data.notes`, 6 Zeilen, editierbar.
- Checkbox "Backup as _notes.txt in directory" (default: True).
- Button "💾 Save Notes" schreibt in DB und optional als Textdatei.
- Bei Konflikt (Datei existiert bereits): Dialog mit Vergleich alter/neuer Inhalt.
  - Button "📦 Keep old (archive it)": archiviert alte Datei als `_notes_001.txt` etc., schreibt neue.
  - Button "🔄 Overwrite" (`color=warning`): überschreibt ohne Archivierung.
  - Button "Cancel" (`color=warning`): bricht ab, keine Dateiänderung.
  - Nach Aktion: `btn_row` verschwindet, nur "✅ OK – Close" bleibt sichtbar.
- `read_only=True`-Modus: Textarea und Buttons deaktiviert.

**Verwendung:**
- In `db_file_prep.py`: wird in `_refresh_notes_section()` eingebunden, wenn DB existiert.
- In `exploration_area.py`: wird angezeigt, wenn genau eine DB ausgewählt ist (über `page['update_single_db']`-Callback).

---

## Offene Punkte / Noch nicht implementiert

### Aus dem Konzept noch fehlend:

1. **Landing Page – Section 3 (Application Description)** – Platzhalter, noch kein Inhalt. Soll ausführliche Beschreibung aller Seiten und Funktionen enthalten, aufgeteilt in Unterkapitel die sich auf den jeweiligen Seiten in den section_card-Descriptions wiederholen.

3. **Adaptive Dateiname-Erkennung (Konzept 3.2)** – Die Scoring-Logik für Dateinamen-Zeitstempel ist noch nicht implementiert. Aktuell werden nur GUANO, ICMT und Dateisystem-Zeiten als Quellen angeboten; `FILENAME_PATTERN` ist als Methode registriert aber die eigentliche Parsing-Logik fehlt.

4. **Adaptiver UTC-Konvertierungsalgorithmus (Konzept 4)** – Die DST-Sprung-Erkennung und Konfidenz-basierte Auswahl der Konvertierungsmethode ist noch nicht als eigenständiges Modul implementiert. Die Vorschau-Tabelle nutzt direkt `timezonefinder` + `zoneinfo`.

### Bekannte Bugs / technische Schulden:

5. **SVG-Icon in page_header und Landing Page nav_cards – inkonsistente Darstellung**

   Das DB-Icon (`/static/icons/db_icon.svg`) wird per Inline-SVG via `ui.html()` eingebettet. Die SVG-Datei hat `viewBox="0 0 100 100"`, `width="100"`, `height="100"`. Beim Einbetten werden `width` und `height` per Regex auf 32/36px gesetzt.

   **Problem:** Darstellung ist inkonsistent – mal wird `?` angezeigt (Exception im try/except), mal wird das Icon korrekt dargestellt, mal abgeschnitten. Ursache noch nicht eindeutig geklärt: möglicherweise Pfad-Berechnung falsch in einem der beiden Kontexte (page_header vs. landing_page), möglicherweise Python-Cache-Problem, möglicherweise SVG-Struktur ungünstig für kleine Darstellung.

   **Stand:** In der Landing Page nav_card funktioniert es korrekt. In `page_header` auf der DB-Config-Seite erscheint `?`. SVG-Pfad-Logik in `page_header.py`: `Path(__file__).parent.parent / 'pages' / symbol.lstrip('/')`. Muss morgen weiter debuggt werden – am besten mit explizitem Logging des Pfads und der Exception-Meldung statt stummem `except`.

6. **"Event listeners changed after initial definition"** – NiceGUI-Warnung beim Start, kommt von der Leaflet-Karte. Nicht kritisch, aber unschön.

6. **Favicon-Fehler** – Vorbestehendes Problem (`/static/icons/favicon.svg` nicht gefunden). Nicht durch diese Implementierung verursacht.

7. **Keine Abwärtskompatibilität** – Bestehende DBs ohne `db_meta_data`-Tabelle funktionieren auf der DB-Config-Seite nicht. Neue DBs müssen angelegt werden. Bewusste Entscheidung (keine Migration implementiert).

---

## Absprachen und Festlegungen außerhalb des Konzepts

### Ordner-Tree auf DB-Config-Seite
`FolderTree` statt `DbFolderTree`: `DbFolderTree` zeigt nur Ordner mit vorhandener DB – auf der Konfigurationsseite müssen aber auch neue Ordner (ohne DB) auswählbar sein.

### GPS und UTC-Methode: Staging (Option B)
GPS und UTC-Methode werden nicht sofort in DB geschrieben, sondern in `state.dbprep_pending_gps` / `state.dbprep_pending_method` / `state.dbprep_pending_offset` zwischengespeichert. DB wird erst bei "Create/Update Database" angelegt.

### Nordpol als "kein Ort"
lat/lon Default 90.0/0.0. Gültige Konfiguration. Freigabe-Prüfung prüft lat/lon nicht.

### Karte einmalig bauen
`ui.leaflet()` wird einmalig beim Seitenaufruf gebaut, nie via `container.clear()` neu erstellt. NiceGUI-Bug verhindert korrektes Neu-Rendern der Karte. Marker werden nach jedem Scan via `_update_map_markers()` dynamisch aktualisiert.

### `_trigger_scan` vs `_start_scan`
Interne Scan-Funktion in `db_file_prep()` heißt `_trigger_scan` (Modul-Level-Funktion heißt `_start_scan(folder, state, page)`), um Namenskollision zu vermeiden.

### KV-Blob: Kein automatisches Löschen
`_sync_kv_to_db` löscht keine bestehenden DB-Einträge automatisch. Gelbe Einträge (in DB, nicht selektiert) bleiben erhalten. Nur explizit selektierte und manuell editierte Werte werden geschrieben/überschrieben.

### `page['refresh_confirm']` als Callback
`_refresh_confirm_section` ist eine innere Funktion von `db_file_prep()` und nicht direkt aus Modul-Level-Funktionen erreichbar. Wird über `page['refresh_confirm']` als Callback übergeben – analog zu `page['refresh_kv_overview']`.

### Karten-Legende: Emoji statt Bilder
`ui.image` und `ui.html` mit `<img>`-Tags funktionieren nicht innerhalb von NiceGUI-Containern (`ui.column()`), die außerhalb des direkten Page-Render-Kontexts befüllt werden. Statische Dateien unter `/static/icons/` sind per Browser-URL erreichbar, werden aber im NiceGUI-Rendering-Kontext des Containers nicht dargestellt. Emoji-Lösung (🔵/🔴) als robuster, wartungsfreier Workaround gewählt. Leaflet-Marker-PNG-Dateien (`marker-icon-blue.png`, `marker-icon-red.png`) wurden **nicht** ins Projekt übernommen.

### Blaue Marker-Klicks entfallen
Klick auf blauen Marker zur Koordinatenübernahme wird nicht implementiert. NiceGUI unterstützt Marker-Click-Events nicht nativ. Der Nutzer kann stattdessen auf die Karte klicken oder Koordinaten manuell eingeben.

### Hangar-Route geändert
Hangar war `/`, ist jetzt `/hangar`. Landing Page übernimmt `/` als Einstiegspunkt.

### DEBUG-Markierung von Testcode
Temporärer Debugging- und Testcode ist immer mit `# DEBUG`-Kommentar zu markieren, damit er leicht auffindbar und entfernbar ist. Diese Konvention wurde im Verlauf dieser Implementierung nicht immer eingehalten – künftig konsequent anwenden.