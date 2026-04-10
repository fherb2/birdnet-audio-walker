# Status Protokoll: DB-Konfigurationsseite und Import-Pipeline

## Erledigte Schritte

### 1. `folder_metadata_scanner.py` – vollständig implementiert und getestet

Neues Modul unter `source/birdnet_copter/folder_metadata_scanner.py`.

Erfolgreich getestet gegen 153 AudioMoth-WAV-Files + 1 CONFIG.TXT in `tests/test_data_working/`. Ergebnis: 154 Files korrekt klassifiziert, 51 distinct Metadata-Keys extrahiert.

Bug behoben: In `_parse_audiomoth_config`: `elif 'gain' in kl` wurde zu `elif kl == 'gain'` korrigiert. Sonst griff die Bedingung auf `Enable low gain range : No` und überschrieb den echten Gain-Wert mit `'No'`.

### 2. DB-Schema erweitert – `database.py` und `db_queries.py`

In `init_database()` in `database.py` wurden zwei neue Tabellen ergänzt, direkt nach dem `CREATE TABLE analysis_config`-Block und vor `conn.commit()`:

**`db_meta_data`** – eine Zeile pro Datenbank, Session-weite Konfiguration:
- `id` INTEGER PRIMARY KEY CHECK (id = 1) – erzwingt genau eine Zeile
- `gps_lat` REAL DEFAULT 90.0 – Nordpol als "kein Ort"-Default
- `gps_lon` REAL DEFAULT 0.0
- `utc_time_method` TEXT – Name der gewählten Methode (FK-Referenz auf `utc_methods.name`)
- `time_offset` TEXT DEFAULT '+00:00:00' – globaler Zeitkorrekturoffset
- `notes` TEXT DEFAULT '' – freies Notizfeld
- `kv_blob` BLOB – gepickeltes Python-Dictionary für beliebige Key-Value-Metadaten

Die Zeile wird beim Anlegen der DB sofort mit `INSERT OR IGNORE` initialisiert (Nordpol-Koordinaten, leere/NULL-Werte für den Rest).

**`utc_methods`** – Registry aller bekannten UTC-Zeitextraktionsmethoden:
- `name` TEXT PRIMARY KEY
- `description` TEXT

Beim Anlegen der DB mit folgenden Methoden befüllt (`INSERT OR IGNORE`):
- `GUANO_TIMESTAMP` – UTC-Timestamp aus GUANO-Chunk, höchste Zuverlässigkeit, AudioMoth >= 1.4
- `ICMT_TIMESTAMP` – UTC-Timestamp aus ICMT-Freitextkommentar, AudioMoth >= 1.2
- `FILENAME_PATTERN` – Datetime aus Dateiname via adaptivem Scoring
- `FILESYSTEM_CTIME` – Dateisystem-Erstellzeit, letzter Fallback, unzuverlässig

In `db_queries.py` wurden folgende neue Funktionen ans Ende der Datei (nach `vacuum_database()`) ergänzt:
- `get_db_meta_data(db_path)` – liest die einzelne db_meta_data-Zeile als Dict
- `set_db_meta_data(db_path, **kwargs)` – aktualisiert beliebige Felder; pickelt kv_blob automatisch wenn dict übergeben
- `get_kv_blob(db_path)` – liest und entpickelt kv_blob, gibt Python-Dict zurück
- `get_utc_methods(db_path)` – gibt alle registrierten Methoden als Liste zurück
- `add_utc_method(db_path, name, description)` – registriert neue Methode (INSERT OR IGNORE)

---

## Zusatzabsprachen, die nicht im Konzept stehen

### Zu `folder_metadata_scanner.py`

- **Registry-Pattern** als Architekturprinzip: Zwei getrennte Listen/Dicts – `CLASSIFIERS` und `PARSERS` – in dedizierten Sektionen. Neue Dateiformate werden ausschließlich dort ergänzt.

- **Modulstruktur in 5 Sektionen:**
  1. Datenstrukturen (`FileClass` Enum, `MetaDataDict` TypeAlias)
  2. Klassifikator-Registry (`CLASSIFIERS`)
  3. Parser-Registry (`PARSERS`)
  4. Dictionary-Builder (`_merge_into_dict`)
  5. Public API (`scan_folder`)

- **`mutagen`** als primäres Tool für alle Audio-Formate (WAV, FLAC, MP3, OGG etc.) für Standard-Tags und technische Parameter. Ausnahme: GUANO/ICMT werden direkt auf Byte-Ebene geparst. WAV-technische Parameter zusätzlich via stdlib `wave`.

- **Klassifikation ist dateiname-agnostisch**: AudioMoth CONFIG.TXT wird an inhaltlichen Markern in den ersten 512 Bytes erkannt (`Device ID`, `Firmware`, `Sample rate`), nicht am Dateinamen.

- **Nicht-Audio-Files** laufen ebenfalls durch die Klassifikator-Registry. `FileClass.UNKNOWN` liefert nur Filesystem-Metadaten. Nicht parsbare Files werden als WARNING geloggt, der Scan läuft weiter.

- **`_merge_into_dict`-Verhalten**: Gleicher Key + gleicher Value → ein Eintrag, Filename wird zur Liste hinzugefügt. Gleicher Key + unterschiedlicher Value → separate Zeile. Bewusst so, da die UI Radio-Button-Semantik pro Key verwendet.

- **`scan_folder` ist synchron/blocking**, Aufruf via `asyncio.run_in_executor(None, scan_folder, path)` aus dem NiceGUI-Kontext – analog zu `DbFolderTree._scan_and_render()`.

- **Übersprungene Files**: `.db`, `.db-wal`, `.db-shm`, `.hdf5`, `.h5` und versteckte Files (Prefix `.`) werden vor der Klassifikation herausgefiltert.

- **GUANO-Namespace-Keys** mit Prefix `guano:` gespeichert, CONFIG.TXT-unbekannte Keys mit Prefix `cfg:`.

### Zum DB-Schema

- **Keine Abwärtskompatibilität** erforderlich – Schema-Entscheidungen sind unabhängig von der bisherigen Version.

- **`utc_time_method`** als TEXT (Methodenname) statt Enum, damit neue Methoden ohne Schema-Migration ergänzt werden können. Die `utc_methods`-Tabelle dient als selbst-dokumentierende Registry: Neue Methoden bekommen neue Namen, alte DBs bleiben lesbar.

- **`gps_lat`/`gps_lon`** als REAL in Dezimalgrad – natives Format für alle Kartenbibliotheken (Leaflet, folium, OpenStreetMap).

- **`kv_blob`** als gepickeltes Python-Dictionary in einer BLOB-Zelle. Zugriff nur über `get_kv_blob()`/`set_db_meta_data()`, kein Einzelzugriff auf DB-Ebene.

### Zur Gesamtarchitektur / Konzept-Korrekturen

- **Plugin-Konzept verworfen**: Ersetzt durch Import-Konfigurationsdialog. `konzept_zeitraum.md` gelöscht.

- **lat/lon Default ist Nordpol (90.0° / 0.0°)**: Bewusste, gültige Konfiguration für "kein Ort bekannt". Gilt als freigebende Konfiguration für den Scouting Flight.

- **Freigabebedingung für den Scouting Flight**: DB-Datei existiert (Konfiguration wurde einmal abgeschlossen und gespeichert) UND `utc_time_method` ist gesetzt. lat/lon muss konfiguriert sein – Nordpol ist dabei gültig.

- **Ergebnis-Vorschau (Abschnitt 2.6/C)** auf 3 Spalten vereinfacht: UTC / Lokalzeit mit DST / Filename. Solare Ortszeit und reine Standardzeit ohne DST weggelassen.