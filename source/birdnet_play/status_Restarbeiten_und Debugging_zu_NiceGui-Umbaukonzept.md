# Status Protokoll – BirdNET Play NiceGUI-Umbau

Zusatz-Übersicht zur Umbau-Konzeptbeschreibung NiceGui-Umbaukonzept.py

Stand, was dazu gehört und was noch fehlt und inzwischen noch zusätzlich zum NiceGui-Umbaukonzept.py noch vereinbart wurde.

---

## Eintrag 1 – 2026-03-04

### Aufgabe
Umbau des BirdNET-Play-Frontends von Streamlit auf NiceGUI gemäß `NiceGui-Umbaukonzept.md` (im Projektordner).

---

### Kontext-Navigation für neue Chats

**Wichtig:** Folgende Projektdateien müssen zu Beginn eines neuen Chats gezielt gesucht werden, um den Kontext effizient aufzubauen. Nicht alle auf einmal lesen – nach Bedarf suchen.

| Was ich brauche | Wo es steht |
|---|---|
| Gesamtarchitektur, alle Anforderungen | `NiceGui-Umbaukonzept.md` (Projektordner) |
| AppState-Felder (hm_* für Heatmap) | `app_state.py` |
| Seitenstruktur, Routing, Layout-API | `layout.py`, `main.py` |
| Audio-Generierung für Dialog | `player.py` → `prepare_detection_audio_simple()` |
| DB-Queries für Heatmap | `db_queries.py` → `query_detections()`, `get_recording_date_range()` |
| Referenz-Implementierung (Streamlit) | `3_heatmap_alaltair.py` (alte Streamlit-Version, Aggregationslogik) |
| Muster für Page-Aufbau | `audio_player.py` (vollständige NiceGUI-Referenz) |
| Muster für SpeciesSearch-Komponente | `species_search.py` |

**Nicht lesen** (veraltet / nicht relevant für Heatmap-Task):
- `full_project_context.md` – alt, nicht kompatibel
- `birdnet_agent_concept.md` – anderes Thema
- `Konzept: Hierarchisches Vektordatenbank-System.md` – anderes Thema
- `1_database_overview.py`, `2_audio_player.py` – alte Streamlit-Versionen

---

### Aktueller Stand der Implementierung

#### Vollständig fertig (NiceGUI):

| Datei | Pfad |
|---|---|
| `main.py` | `birdnet_play/main.py` |
| `app_state.py` | `birdnet_play/app_state.py` |
| `cli_playback.py` | `birdnet_play/cli_playback.py` |
| `__main__.py` | `birdnet_play/__main__.py` |
| `__init__.py` | `birdnet_play/__init__.py` |
| `layout.py` | `birdnet_play/pages/layout.py` |
| `database_overview.py` | `birdnet_play/pages/database_overview.py` |
| `audio_player.py` | `birdnet_play/pages/audio_player.py` |
| `folder_tree.py` | `birdnet_play/gui_elements/folder_tree.py` |
| `species_search.py` | `birdnet_play/gui_elements/species_search.py` |
| `filters.py` | `birdnet_play/filters.py` (unverändert aus Streamlit) |
| `player.py` | `birdnet_play/player.py` (unverändert aus Streamlit) |
| `tts.py` | `birdnet_play/tts.py` (unverändert aus Streamlit) |
| `db_queries.py` | `shared/db_queries.py` (unverändert) |
| `audio_extract.py` | `shared/audio_extract.py` (unverändert) |
| `streamlit_utils.py` | `shared/streamlit_utils.py` (unverändert, wird weitergenutzt) |

#### Manuell anzulegen (triviale Inhalte, kein Artefakt nötig):

**`birdnet_play/pages/__init__.py`** – aktuell leer, muss befüllt werden mit:
```python
from . import database_overview  # noqa: F401
from . import audio_player        # noqa: F401
from . import heatmap_page        # noqa: F401
```

**`birdnet_play/gui_elements/__init__.py`** – leer lassen.

#### Noch zu implementieren:

- `birdnet_play/pages/heatmap_page.py` – **die einzige noch fehlende Datei**

---

### Aufgabe für den nächsten Chat: heatmap_page.py

#### Dateiname und Route
- Datei: `birdnet_play/pages/heatmap_page.py` (kein Nummernpräfix!)
- Route: `/heatmap` (bereits als Link in `layout.py` eingetragen)

#### Aufteilung in zwei Artefakte
- **Teil 1:** Imports, Konstanten, Colormap-Daten, Aggregationsfunktion, ECharts-Konfigurationsfunktion, Page-Handler mit Filter-UI und ECharts-Render
- **Teil 2:** Klick-Dialog (inkl. Audio-Generierung + kompakter Inline-Player), CSV-Export

#### Entscheidungen (bereits getroffen, nicht neu diskutieren):
- **PNG-Export:** NICHT implementieren – erst nach erstem Test der Grundfunktion
- **ECharts-Klick-Event:** gemäß Konzept mit `.on('click', handler)` implementieren, noch nicht getestet
- **Dialog-Audio-Player:** kompakte Inline-HTML/JS-Version direkt im Heatmap-File (nicht `_build_player_html()` aus `audio_player.py` importieren)
- **CSV-Export:** implementieren (serverseitig erzeugt, via `ui.download()`)

---

### Anforderungen an heatmap_page.py (Zusammenfassung aus Konzept Teil 4)

#### Filter (Sidebar oder Inline):
- SpeciesSearch-Komponente (wie auf Audio-Player-Seite)
- Datumsbereich: date_from / date_to (Standardwerte: vollständiger DB-Zeitraum)
- Confidence-Dropdown: "All", 5%–95% in 5%-Schritten, Standard: 70%
- "Apply Filters"-Button

#### Heatmap-Optionen:
- Colormap-Dropdown: 16 Optionen (inferno, viridis, plasma, magma, turbo, blues, greens, reds, oranges, purples, greys, blueorange, redyellowblue, redyellowgreen, spectral, rainbow), Standard: turbo
- "Weight by Confidence"-Checkbox, Standard: aktiv

#### ECharts-Heatmap:
- X-Achse: Datum (Kategorie), nur Montage beschriftet ("TT.MM.")
- Y-Achse: 48 Zeitslots (00:00–23:30), nur 00:00/06:00/12:00/18:00 beschriftet, invertiert (00:00 oben)
- Zellgröße: 12×12 px (Konstante `HEATMAP_CELL_SIZE = 12`)
- Zellen mit Wert 0: weiß; Zellen > 0: nach Colormap
- Maximalwert Farbskala: max(größter Zellwert, 4) (Konstante `MIN_COLORSCALE_MAX = 4`)
- Tooltip: Datum (TT.MM.), Uhrzeit (HH:MM), Wert, Anzahl Detektionen, Ø Konfidenz
- Klick-Event: `.on('click', handler)` → öffnet Dialog

#### Colormap-Mapping (ECharts kennt keine Namen wie "turbo"):
Jede Colormap als Liste von Hex-Farbstops definieren (siehe Konzept Abschnitt 6.5).

#### Datenaggregation:
- Slot-Index = Stunde × 2 + (1 wenn Minute ≥ 30, sonst 0)
- Pro Datum+Slot: Konfidenzwerte summieren (Weight-Modus) oder zählen (Count-Modus)
- Auch Tage ohne Detektionen in Matrix (0-Werte), lückenloser Datumsbereich

#### Klick-Dialog (`ui.dialog`):
- Header: Datum (TT.MM.YYYY), Zeitfenster (HH:MM – HH:MM+29min), Spezies-Filter oder "All species", Metriken (Anzahl, Summe/Anzahl, Ø Konfidenz)
- Detektionen: `query_detections()` mit `time_range`, `date_from=date_to=clicked_date`, `limit=25`, `sort_by="confidence"`, `sort_order="desc"`, `min_confidence` aus Heatmap-Filter
- Audio: `prepare_detection_audio_simple()` als Hintergrundtask, Fortschrittsbalken
- Kompakter HTML/JS-Player (ohne "Recently Played"-Liste)
- Schließen via Button oder Klick außerhalb; beim Schließen werden Dialog-Audiodaten verworfen (NICHT in `app_state.audio_cache`)

#### AppState-Felder für Heatmap (bereits in app_state.py vorhanden):
```
hm_filter_species, hm_filter_date_from, hm_filter_date_to,
hm_filter_confidence, hm_filters_applied,
hm_colormap, hm_weight_confidence, hm_aggregated_data
```

#### CSV-Export:
- Zeilen: 48 Zeitslots, Spalten: Tage
- Dateiname: `heatmap_<spezies>_<datum_von>_<datum_bis>.csv`
- Serverseitig erzeugt, via `ui.download()`


# Status Protokoll – Teil 2

---

### Muster-Code-Referenzen für heatmap_page.py

#### Page-Handler-Grundstruktur (aus audio_player.py übernehmen):
```python
def _get_state() -> AppState:
    return nicegui_app.state.app_state

@ui.page('/heatmap')
async def heatmap_page() -> None:
    state = _get_state()
    create_layout(state)
    # ...
```

#### SpeciesSearch-Einbindung (aus audio_player.py):
```python
species_search = SpeciesSearch(
    db_path=state.active_db,
    on_select=lambda s: setattr(state, 'hm_filter_species', s),
    initial_value=state.hm_filter_species,
)
```

#### ECharts-Klick-Event (gemäß NiceGUI-Doku):
```python
chart = ui.echart(options).on('click', lambda e: handle_click(e))
# e.args enthält ECharts event-Objekt mit e.args['data'] = [x_idx, y_idx, value]
```

#### Hintergrundtask-Muster für Dialog-Audio (aus audio_player.py):
```python
async def _generate_dialog_audio(detections, player_obj):
    loop = asyncio.get_event_loop()
    audio_files = []
    for det in detections:
        mp3 = await loop.run_in_executor(
            None,
            player_obj.prepare_detection_audio_simple,
            det, 0.5
        )
        b64 = base64.b64encode(mp3.read()).decode()
        audio_files.append({...})
    return audio_files
```

#### ui.download-Muster für CSV:
```python
csv_bytes = csv_string.encode('utf-8')
ui.download(csv_bytes, filename='heatmap_....csv')
```

---

### Bekannte Besonderheiten / Fallstricke

1. **ECharts visualMap für Zellen mit Wert 0:** Zellen mit Wert 0 sollen weiß sein, nicht nach Colormap eingefärbt. Das erfordert entweder `pieces` in `visualMap` mit explizitem Eintrag für 0 → weiß, oder das Herausfiltern von 0-Werten aus den ECharts-Datenpunkten (fehlende Datenpunkte werden in Heatmap-Series als leer/weiß dargestellt).

2. **ECharts Heatmap-Series erwartet Daten als `[x_idx, y_idx, value]`:** Nicht als Dict, sondern als Array.

3. **Y-Achse invertiert:** In ECharts über `inverse: true` in der yAxis-Konfiguration.

4. **Klick-Event `e.args`-Struktur:** Noch nicht getestet. Falls `e.args` nicht direkt `data` enthält, ggf. `e.args[0]` oder `e.args['data']` probieren. Robuster Fallback: try/except mit `ui.notify()` bei unerwarteter Struktur.

5. **Dialog-Audio nicht in app_state.audio_cache:** Die im Dialog generierten Audiodateien sind kurzlebig und werden als lokale Variable im Dialog-Scope gehalten, nicht im globalen AppState gespeichert.

6. **`prepare_detection_audio_simple()` Signatur:**
   ```python
   player.prepare_detection_audio_simple(detection, pm_seconds=0.5) -> BytesIO
   ```

7. **Aggregationslogik:** Die Referenz-Implementierung in `3_heatmap_alaltair.py` (Streamlit-Version, im Projektordner) enthält die bewährte Aggregationslogik. Diese 1:1 übernehmen, nur die Ausgabe von Altair-DataFrame auf ECharts-Datenformat umstellen.

---

### Offene Punkte nach erstem Test

Nach dem ersten erfolgreichen Test der Grundfunktion (Heatmap rendert, Klick-Dialog öffnet, Audio spielt):

- [ ] PNG-Export via ECharts `getDataURL()` nachrüsten
- [ ] ECharts-Kontextmenü ausbauen (aktuell: Klick = Linksklick-Aktion)
- [ ] Testen ob `pages/__init__.py` korrekt alle drei Routen registriert
- [ ] Testen ob Navigation zwischen allen drei Seiten funktioniert
- [ ] Read-Only-Banner auf Heatmap-Seite (kein Schreibzugriff dort nötig, aber Banner-Konsistenz)

---

### Sonstige Projektnotizen

- Der Server wird gestartet mit: `python -m birdnet_play /path/to/db_dir`
- Port: 8080, Host: 0.0.0.0
- `birdnet_play/pages/__init__.py` muss die drei Imports enthalten (siehe Teil 1)
- Alte Streamlit-Files (`1_database_overview.py`, `2_audio_player.py`, `3_heatmap_alaltair.py`) können nach erfolgreichem Test gelöscht werden
- `gui_elements/__init__.py` bleibt leer

