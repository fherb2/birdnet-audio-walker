# Konzept: Vogelname-Übersetzung zur Lesezeit

## Ziel

Die SQLite-Datenbank speichert nur noch `scientific_name`. Lokale Vogelnamen werden
zur Lesezeit aus Language-Files übersetzt. Diese werden von der Quelle des verwendeten BirdNET
Modells mit herunter geladen. Eine konfigurierbare Vogelname-Sprache
(Default: `de`) steuert die Übersetzung. Die GUI-Sprache ist ein separates,
noch nicht aktives Feld.

---

## 1. Neues Modul `bird_language.py`

Ort: `source/birdnet_copter/bird_language.py`

### Aufgabe
- Lädt Label-Files aus :
  -> BirdNET-Systemordner: `BIRDNET_LABELS_PATH` (aus `config.py`)
  Das bisher auch verwendete File aus 
  SPECIES_TABLE_URL = "https://www.karlincam.cz/de_de/und-sonst-noch/artennamen-uebersetzen/vogelnamen-wissenschaftlich-sortiert"
  wird nicht mehr verwendet.
- Cacht geladene Label-Dicts im Modul-Level (kein erneutes Laden solange
  die Sprache gleich bleibt)
- Wenn eine angeforderte Sprache in keiner Quelle existiert: Fallback auf `'de'`,
  Warnung ins Log

### Öffentliche API

```python
def get_available_languages() -> list[str]:
    """
    Gibt sortierte Liste aller verfügbaren Sprachcodes zurück.
    Vereinigung aus BIRDNET_LABELS_PATH/*.txt und BIRD_LANGUAGES_PATH/*.txt.
    """

def load_labels(language: str) -> dict[str, str]:
    """
    Lädt Labels für eine Sprache. Gecacht nach erstem Aufruf.
    Lokaler Ordner hat Vorrang vor BirdNET-Systemordner.

    Args:
        language: Sprachcode z.B. 'de', 'en_uk', 'cs'

    Returns:
        Dict {scientific_name: local_name}.
        Leeres Dict wenn Sprache nicht gefunden.
    """

def translate(scientific_name: str, language: str) -> str:
    """
    Übersetzt einen wissenschaftlichen Namen in die Zielsprache.
    Fallback: scientific_name wenn nicht gefunden.

    Args:
        scientific_name: Wissenschaftlicher Name
        language:        Sprachcode

    Returns:
        Lokaler Name oder scientific_name als Fallback.
    """
```

### Interner Cache
```python
_label_cache: dict[str, dict[str, str]] = {}
# Key: language code, Value: {scientific: local}
```

---

## 2. Liste der verfügbaren Vogelnamen-Sprachen

In `BIRDNET_LABELS_PATH` stehen alle Text-Übersetzungsfiles. Der Dateiname hat den Aufbau sprachcode.txt . Demzufolge kann für die Liste der zur Verfügung stehenenden Codes einfach die Liste der Dateinamen verwendet werden.

---

## 3. Änderungen `app_state.py`

### Umbenennung
- `language_code: str = 'de'` → aufgeteilt in zwei Felder:

```python
# Vogelname-Sprache (vollständig implementiert)
bird_language_code: str = 'de'

# GUI-Sprache (noch nicht aktiv, nur vorbereitet)
gui_language_code: str = 'de'
```

### Konsequenzen der Umbenennung
Alle bisherigen Zugriffe auf `state.language_code` müssen angepasst werden:
- `exploration_area.py`: `state.language_code` → `state.bird_language_code`
- `database_overview.py`: analog
- `audio_player.py`: analog (wird an `player.py` übergeben)
- `main.py`: `app_state.language_code` → `app_state.bird_language_code`
- `scout_process.py`: `language_code`-Parameter bleibt, aber der Wert kommt
  aus `app_state.bird_language_code` (wird nur noch für `analysis_config`
  in der DB geschrieben, nicht mehr für Translation verwendet)

---

## 4. Änderungen `db_queries.py`

### Neues optionales Parameter-Pattern

Alle Query-Funktionen die Detection- oder Species-Daten zurückgeben, erhalten
ein optionales Argument:

```python
labels: Optional[dict[str, str]] = None
```

Wenn `labels` übergeben wird, wird jedem zurückgegebenen Dict ein
`local_name`-Feld hinzugefügt:

```python
row_dict['local_name'] = labels.get(row_dict['scientific_name'],
                                     row_dict['scientific_name'])
```

Wenn `labels=None`: `local_name` fehlt im Dict (kein Fallback, kein Fehler –
Aufrufer muss wissen was er übergibt).

### Betroffene Funktionen

```python
def query_detections(..., labels: Optional[dict] = None) -> List[Dict]:
    # Nach dem Aufbau der results-Liste:
    if labels is not None:
        for r in results:
            r['local_name'] = labels.get(r['scientific_name'], r['scientific_name'])

def get_detection_by_id(..., labels: Optional[dict] = None) -> Optional[Dict]:
    # Nach dem dict(row):
    if labels is not None and result:
        result['local_name'] = labels.get(result['scientific_name'],
                                           result['scientific_name'])

def get_species_list_with_counts(..., labels: Optional[dict] = None) -> List[Dict]:
    # Nach dem Aufbau der results-Liste:
    if labels is not None:
        for r in results:
            r['local_name'] = labels.get(r['scientific_name'], r['scientific_name'])

def get_available_species(..., labels: Optional[dict] = None) -> List[...]:
    # Rückgabeformat ändert sich je nach labels:
    # labels=None  → list[str]  (nur scientific_name, wie bisher)
    # labels given → list[tuple[str, str]]  (scientific, local)

def search_species_in_list(..., labels: Optional[dict] = None) -> List[str]:
    # Wenn labels gegeben: Suche zusätzlich in local_name (im Python-Code,
    # nicht in der DB). Anzeige-String: "Scientific Name (Local Name)"
    # Wenn labels=None: nur scientific_name, wie bisher
```

### `create_species_list_table()`
Bleibt unverändert – schreibt nur `scientific_name` (bereits angepasst).

---

## 5. Verwendung in den Pages

### Prinzip
Jede Page, die lokale Vogelnamen anzeigen will, holt sich einmalig beim
Seitenaufruf die Labels:

```python
from ..bird_language import load_labels
labels = load_labels(state.bird_language_code)
```

Und übergibt sie an die DB-Queries:

```python
detections = query_detections(db_path, ..., labels=labels)
species_list = get_species_list_with_counts(db_path, labels=labels)
```

### `audio_player.py`
- `labels = load_labels(state.bird_language_code)` einmalig beim Seitenaufruf
- `query_detections(..., labels=labels)` → Detections haben `local_name`
- `player.py` greift weiterhin auf `det.get('local_name')` zu – keine Änderung

### `heatmap_page.py`
- `labels = load_labels(state.bird_language_code)` einmalig
- `query_detections(..., labels=labels)` in `_apply_filters()` und im Dialog
- `SpeciesSearch` bekommt `labels=labels` übergeben (siehe unten)

### `exploration_area.py` / `database_overview.py`
- `labels = load_labels(state.bird_language_code)` einmalig
- `get_species_list_with_counts(db, labels=labels)` → hat `local_name`
- Spalte `name_cs` in Grid und Downloads entfernen
- Spalte `local_name` bleibt (kommt jetzt aus Übersetzung, nicht aus DB)
- Downloads (CSV/Excel): `name_cs`-Spalte entfernen, `local_name` bleibt

### `exploration_area.py` Besonderheit: DB-Wechsel
Wenn der Nutzer die DB wechselt und `_refresh_db_info()` aufgerufen wird,
muss `labels` neu geladen werden (könnte sich durch DB-Wechsel nicht ändern,
aber `bird_language_code` könnte sich geändert haben). Lösung: `labels` nicht
einmalig am Seitenanfang, sondern in einer Closure die immer
`load_labels(state.bird_language_code)` aufruft (gecacht, also kein
Performance-Problem).

---

## 6. Änderungen `species_search.py`

### Neues optionales Argument
```python
def __init__(
    self,
    db_path: Optional[Path],
    on_select: Optional[Callable[[Optional[str]], None]] = None,
    initial_value: Optional[str] = None,
    placeholder: str = 'Search species… (type to filter)',
    labels: Optional[dict[str, str]] = None,   # NEU
) -> None:
```

### Verhalten mit `labels`
- `search_species_in_list()` wird mit `labels` aufgerufen
- Wenn ein Match im lokalen Namen gefunden wird, wird er in der Dropdown
  angezeigt: `"Scientific Name (Local Name)"`
- Der interne Wert (`self._value`) bleibt immer `scientific_name`
- Die aktive Anzeige (`_show_active`) zeigt: `"🔍 Local Name (Scientific)"`,
  also mit lokalem Namen zuerst wenn vorhanden

### `set_labels()` Methode
```python
def set_labels(self, labels: Optional[dict[str, str]]) -> None:
    """Aktualisiert die Labels (z.B. nach Sprachwechsel)."""
    self._labels = labels
```

---

## 7. Änderungen `hangar.py`

### Neuer Abschnitt: Language Configuration

Neuer Section-Card nach GPU Processing:

```python
with section_card('🌍', 'Language Configuration', 'hangar_language'):

    with ui.row().classes('gap-8 items-start'):

        # --- Vogelname-Sprache (vollständig aktiv) ---
        with ui.column().classes('gap-1'):
            ui.label('Bird Name Language').classes('text-caption text-grey-6 font-bold')
            bird_lang_select = ui.select(
                options=get_available_languages(),
                value=state.bird_language_code,
                label='Bird Name Language',
                on_change=lambda e: _on_bird_lang_change(e.value),
            ).props('outlined dense').classes('w-40')
            ui.label('Default: de (Deutsch)').classes('text-caption text-grey-6')

        # --- GUI-Sprache (noch nicht aktiv) ---
        with ui.column().classes('gap-1'):
            ui.label('GUI Language').classes('text-caption text-grey-6 font-bold')
            gui_lang_select = ui.select(
                options=['de', 'en'],   # Platzhalter
                value=state.gui_language_code,
                label='GUI Language',
            ).props('outlined dense disable').classes('w-40')
            ui.label('Not yet implemented').classes('text-caption text-grey-6')

def _on_bird_lang_change(lang: str) -> None:
    available = get_available_languages()
    if lang not in available:
        ui.notify(
            f"Language '{lang}' not available, resetting to 'de'",
            type='warning'
        )
        state.bird_language_code = 'de'
        bird_lang_select.set_value('de')
    else:
        state.bird_language_code = lang
        logger.info(f"Bird language changed to: {lang}")
```

---

## 8. Änderungen `main.py`

- Import von `birdnet_labels` und `species_translation` entfernen (bereits
  beschlossen in vorherigem Schritt)
- `app_state.language_code` → `app_state.bird_language_code` im
  `_startup_tasks()`-Aufruf:

```python
# Alt:
lang = get_analysis_config(app_state.active_db, 'local_name_shortcut')
app_state.language_code = lang if lang else 'de'

# Neu: language_code aus DB wird nicht mehr für Übersetzung verwendet.
# bird_language_code bleibt beim Default 'de' (kein DB-Lookup mehr nötig).
# gui_language_code analog.
```

Hinweis: `local_name_shortcut` in `analysis_config` der DB wird nicht mehr
gelesen (war der frühere Mechanismus). Der Wert bleibt in der DB für
historische Kompatibilität, wird aber ignoriert.

---

## 9. Änderungen `scout_process.py`

- ()`language_code`-Parameter in `run_scout_process()` und `_process_folder()`
  -> Entscheidung notwendig)

**Entscheidung gefallen:** `local_name_shortcut` soll nicht mehr in `analysis_config`
geschrieben werden, sondern komplett entfernt werden. 
Daraus folgt: `language_code`-Parameter aus `run_scout_process()` und
`_process_folder()` ebenfalls entfernen.

---

## 10. Was entfällt komplett (nach diesem Umbau)

- `species_translation.py` – wird nicht mehr benötigt (kein Tschechisch mehr
  zur Schreibzeit, kein karlincam-Download)
- `birdnet_labels.py` – Funktionalität geht in `bird_language.py` auf
- `config.py`: `SPECIES_CACHE_DIR`, `SPECIES_CACHE_MAX_AGE_DAYS`,
  `SPECIES_TABLE_URL`, `DEFAULT_LANGUAGE`, `BIRDNET_LABELS_PATH`
  (letzteres wandert in `bird_language.py`)

---

## 11. Betroffene Dateien (Zusammenfassung)

### Neue Dateien  
- `source/birdnet_copter/bird_language.py`
- `source/birdnet_copter/bird_languages/.gitkeep`

### Geänderte Dateien
- `config.py` – neue Konstante `BIRD_LANGUAGES_PATH`, alte entfernen
- `app_state.py` – `language_code` → `bird_language_code` + `gui_language_code`
- `db_queries.py` – `labels`-Parameter in Query-Funktionen
- `species_search.py` – `labels`-Parameter, lokale Namenssuche
- `hangar.py` – Language-Configuration-Section
- `main.py` – Imports, `language_code`-Referenzen
- `audio_player.py` – `load_labels`, `labels` an Queries
- `heatmap_page.py` – `load_labels`, `labels` an Queries und SpeciesSearch
- `exploration_area.py` – `load_labels`, `name_cs` entfernen
- `database_overview.py` – analog

### Entfernte Dateien (nach Bestätigung)
- `species_translation.py`
- `birdnet_labels.py`

### Nicht geändert
- `scout_process.py` – nur wenn `language_code`-Parameter entfällt
- `database.py` – bereits angepasst
- `player.py` – greift auf `det.get('local_name')` zu, das bleibt gültig
- `filters.py` – keine Änderung


## Nachtrag: Klärungen vor Implementierungsstart

### get_available_species()
Gibt immer `list[str]` zurück (nur `scientific_name`).
Übersetzung zu `local_name` erfolgt im Aufrufer via `labels.get(scientific_name, scientific_name)`.

### search_species_in_list()
Mit `labels`-Parameter: Suche in `scientific_name` UND `local_name` (Python-seitig).
Anzeigestring im Dropdown: `"Scientific Name (Local Name)"`.
Interner Wert (`self._value` in SpeciesSearch) bleibt immer `scientific_name`.

### Keine Sprachinformation mehr in der DB
`local_name_shortcut` wird nicht mehr in `analysis_config` geschrieben.
Konsequenz für `scout_process.py`:
- `language_code`-Parameter entfällt aus `_process_folder()` und `run_scout_process()`
- `set_analysis_config`-Import prüfen – falls nur für `local_name_shortcut` verwendet, entfernen
- `get_analysis_config`-Import bleibt (wird noch für `min_confidence` gebraucht)

### Abschnitt 9 (offene Fragen) – geklärt
Beide Punkte sind entschieden, keine offenen Fragen mehr vor der Implementierung.