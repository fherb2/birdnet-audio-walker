# BirdNET Play – Konzept NiceGUI-Umbau
## Teil 1: Architektur und Grundprinzipien

---

## 1. Überblick

Dieses Dokument beschreibt den Umbau des BirdNET-Play-Frontends von Streamlit auf NiceGUI. Es ist der erste von drei geplanten Ausbaustufen des Gesamtsystems. Der Umbau ersetzt ausschließlich die Präsentationsschicht – die bestehende Backend-Logik (Datenbankzugriff, Audio-Processing, TTS) bleibt vollständig erhalten und wird unverändert weitergenutzt.

Das Ziel dieses ersten Schritts ist eine funktional vollständige Reimplementierung der drei bestehenden Seiten (Database Overview, Audio Player, Activity Heatmap) unter NiceGUI, mit einer Architektur, die die Anforderungen der nachfolgenden Ausbaustufen (Walker-Integration, Embedding-Analyse, Filebrowser) nicht verbaut.

---

## 2. Ziele des Umbaus

Der Umbau verfolgt zwei gleichrangige Ziele: die kurzfristige Ablösung von Streamlit und die mittelfristige Erweiterbarkeit des Systems.

Streamlit hat sich als ungeeignet erwiesen, sobald die Interaktion über einfache Formular-Widgets hinausgeht. Ein Filebrowser, Drag-and-Drop, kontextsensitive Menüs, oder Hintergrundprozesse mit reaktivem UI-Feedback sind mit Streamlit entweder nicht oder nur mit erheblichem Aufwand und fragiler Stabilität realisierbar. NiceGUI überwindet diese Einschränkungen strukturell.

Gleichzeitig soll die neue Architektur von Anfang an so gestaltet sein, dass ein dauerhaft laufender Server-Prozess, Background-Tasks und ein zustandsbehaftetes System ohne Neustart des Servers sinnvoll betrieben werden können. Das ist keine Vorbereitung auf Zukunftsfeatures, sondern eine Grundvoraussetzung bereits für den ersten Umbauschritt, da der Server dauerhaft laufen soll und der Client jederzeit ein- und aussteigen können muss.

---

## 3. Kernarchitektur-Prinzipien

### 3.1 Ein Server – ein Systemzustand – ein GUI-Client

Dies ist das wichtigste Architekturprinzip des gesamten Systems und muss bei allen Entwurfsentscheidungen konsequent berücksichtigt werden.

Der Server läuft als eigenständiger, dauerhafter Prozess. Er wird einmal gestartet und läuft dann so lange, bis er explizit beendet wird – unabhängig davon, ob gerade ein Client verbunden ist oder nicht. Der Server hält den gesamten Systemzustand im Speicher. Dieser Zustand umfasst die aktuell geöffnete Datenbank, alle gesetzten Filter, die geladene Detektionsliste, den Zustand des Audio-Players und alle Konfigurationsoptionen.

Es gibt genau einen GUI-State. Dieser State gehört nicht dem Client, sondern dem Server. Wenn ein Browser-Client die Oberfläche öffnet, bekommt er den aktuellen Systemzustand des Servers angezeigt – so, als wäre er nie weg gewesen. Es gibt keine Unterscheidung zwischen "erster Verbindung" und "Wiederverbindung". Der Client ist ein Fenster auf den Serverzustand, kein eigenständiger Akteur.

Es wird bewusst kein Multi-Client-Szenario unterstützt. Es gibt keinen Mechanismus, mit dem mehrere Browser-Clients gleichzeitig unabhängige Abläufe starten oder eigene States führen könnten. Ein zweiter Browser, der sich verbindet, sieht denselben Zustand wie der erste. Dieses Prinzip vereinfacht die Architektur erheblich und entspricht dem realen Nutzungsmodell: Ein Nutzer bedient das System, möglicherweise von verschiedenen Geräten oder zu verschiedenen Zeiten, aber immer als derselbe Nutzer mit demselben laufenden Prozess.

### 3.2 Trennung von Server-Prozess und Haupt-Prozess

Der NiceGUI-Server wird als eigenständiger gespawnter Prozess gestartet. Er teilt keinen Speicher mit dem Hauptprozess (dem ehemaligen CLI-Einstiegspunkt). Die Kommunikation zwischen den Prozessen erfolgt über definierte Schnittstellen (zunächst einfache Queues oder Pipes, bei Bedarf erweiterbar).

Diese Trennung hat zwei Gründe: Erstens wird dadurch sichergestellt, dass CPU-intensive Hintergrundoperationen (Audio-Processing, zukünftig: Embedding-Berechnungen) den Web-Server nicht blockieren. Zweitens entspricht die Trennung dem Deployment-Modell: Im Docker-Container kann der Server-Prozess unabhängig überwacht, neugestartet oder auf einem anderen System (Remote, FPGA-Maschine) betrieben werden.

### 3.3 Direkter Zugriff auf die AsyncIO-Event-Loop

Der NiceGUI-Server wird nicht über `ui.run()` gestartet, sondern über eine manuell instanziierte uvicorn-Server-Instanz. Damit ist die AsyncIO-Event-Loop vollständig zugänglich. Hintergrundaufgaben können über `asyncio.create_task()` gestartet werden und laufen in derselben Loop wie der Web-Server und NiceGUI selbst.

Dies ermöglicht es, Audio-Processing-Jobs, Datenbankoperationen oder zukünftige Walker-Analysen als echte asynchrone Tasks zu betreiben, die Fortschrittsevents direkt in die UI schieben können, ohne den Browser-Client zu blockieren oder einen separaten Thread verwalten zu müssen.

Die Grundstruktur des Servers orientiert sich dabei an dem bereits erprobten Muster aus `gui_prc.py`: Eine async Hauptfunktion, die über `asyncio.run()` gestartet wird, darin die uvicorn-Konfiguration, NiceGUI-Routen und `app.on_startup()` für die Registrierung von Hintergrundtasks.

### 3.4 Beibehaltung der bestehenden Backend-Schicht

Die Module `shared/db_queries.py`, `shared/audio_extract.py`, `birdnet_play/player.py`, `birdnet_play/filters.py` und `birdnet_play/tts.py` werden ohne Änderungen übernommen. Der NiceGUI-Server ruft diese Module direkt auf, genau wie Streamlit es bisher getan hat. Es wird keine neue Abstraktionsschicht zwischen Frontend und Backend eingeführt.

---

## 4. Prozessmodell

### 4.1 Startvorgang

Der bisherige Einstiegspunkt `cli.py` mit dem `--ui`-Flag entfällt. An seine Stelle tritt ein dediziertes Server-Startskript, das direkt aufgerufen wird. Der Server nimmt beim Start den Pfad zu einem Datenbankverzeichnis oder einer konkreten Datenbankdatei als Argument entgegen – analog zur bisherigen Konvention.

Der Server-Prozess wird mit dem `spawn`-Kontext von `multiprocessing` gestartet, wenn er als Hintergrunddienst betrieben wird. Für Entwicklung und einfachen Betrieb kann er auch direkt als Hauptprozess laufen. Das Startskript unterscheidet diese beiden Fälle.

### 4.2 Laufzeitverhalten

Nach dem Start initialisiert der Server den Systemzustand: Er scannt das übergebene Verzeichnis nach Datenbanken, lädt die zuletzt verwendete Datenbank (sofern persistiert) oder wartet auf eine Auswahl durch den Client. Der Server läuft dann dauerhaft und wartet auf HTTP-Verbindungen von Browser-Clients.

Wenn kein Client verbunden ist, laufen alle Hintergrundtasks dennoch weiter. Ein Fortschrittsbalken für einen laufenden Audio-Processing-Job wird im Server-State gehalten und steht sofort zur Verfügung, wenn ein Client sich neu verbindet.

### 4.3 Shutdown

Der Server reagiert auf SIGTERM mit einem geordneten Shutdown: Laufende Tasks werden abgeschlossen oder abgebrochen (je nach Task-Typ), offene Datenbankverbindungen werden geschlossen, und der uvicorn-Server wird über `server.should_exit = True` graceful heruntergefahren. SIGINT wird im Subprocess ignoriert (der Elternprozess ist verantwortlich).

---

## 5. State-Management

### 5.1 Grundprinzip

Da es genau einen GUI-State gibt und dieser dem Server gehört, wird er als einfaches Python-Objekt (eine Klasse `AppState`) auf Server-Seite gehalten. Es wird bewusst kein Framework für reaktives State-Management verwendet – NiceGUI's eingebaute Binding-Mechanismen (`bind_value`, `bind_text` etc.) werden genutzt, wo sie sinnvoll sind, aber der State selbst ist eine schlichte Python-Datenstruktur.

### 5.2 Inhalt des AppState

Der AppState gliedert sich in drei Bereiche:

**Systemzustand:** Welches Datenbankverzeichnis ist aktiv, welche Datenbank ist geöffnet, Sprachcode, Read-Only-Flag.

**Filter-State:** Alle aktuell gesetzten Filter für den Audio-Player (Spezies, Datumsbereich, Zeitbereich, Confidence, Limit, Offset, Sortierung) und für die Heatmap (Spezies, Datumsbereich, Confidence). Diese sind dauerhaft im Server-State gehalten und gehen nicht verloren, wenn der Client die Verbindung trennt.

**Audio-Player-State:** Geladene Detektionsliste, generierte Audio-Dateien (als Base64-Cache), aktuelle Audio-Optionen (TTS-Einstellungen, Frame-Duration, Noise-Reduction-Parameter), Playback-Position.

**Heatmap-State:** Aggregierte Heatmap-Daten, ausgewählte Colormap, Confidence-Gewichtungs-Flag, zuletzt angeklickte Zelle.

### 5.3 Persistenz

Der AppState wird nicht automatisch auf Disk persistiert. Eine einfache Ausnahme kann für die zuletzt verwendete Datenbank gemacht werden, sodass der Server nach einem Neustart direkt dieselbe Datenbank öffnet. Das wird als einfache JSON-Datei im Arbeitsverzeichnis realisiert.

### 5.4 UI-Aktualisierung bei State-Änderungen

NiceGUI aktualisiert UI-Elemente entweder über Bindings oder über explizite Aufrufe wie `label.set_text()`. Da der State zentral auf dem Server liegt, werden State-Änderungen aus Hintergrundtasks über `asyncio`-sichere Mechanismen in die UI propagiert: Ein Hintergrundtask, der den State verändert, ruft danach eine Callback-Funktion auf, die das zugehörige UI-Element aktualisiert. NiceGUI's `ui.timer()` kann für periodische UI-Refreshes verwendet werden, wenn ein kontinuierlicher Fortschritt angezeigt werden soll.

---

## 6. Navigation und Seitenstruktur

### 6.1 Seitenaufteilung

Das System behält die drei bestehenden Hauptseiten bei:

- **Database Overview** (entspricht Page 1): Datenbankauswahl, Metadaten, Species-Liste
- **Audio Player** (entspricht Page 2): Filter, Audio-Optionen, Detektionsliste, Player
- **Activity Heatmap** (entspricht Page 3): Heatmap-Visualisierung, Filter, Dialog

Die Navigation zwischen den Seiten erfolgt über eine persistente Navigationsleiste, die auf jeder Seite sichtbar ist. NiceGUI realisiert das über `@ui.page`-Dekoratoren für jede Route und ein gemeinsames Layout-Element, das auf jeder Seite eingebunden wird.

### 6.2 Seitenübergreifender State

Da der State dem Server gehört und nicht dem Client, ist der seitenübergreifende State kein technisches Problem: Der `AppState` ist auf jeder Seite vollständig zugänglich. Wenn auf der Database-Overview-Seite eine Spezies ausgewählt und "Play" geklickt wird, schreibt der Server den gewählten Spezies-Filter in den `AppState` und navigiert den Client zur Audio-Player-Seite. Dort liest der Audio-Player den Filter aus dem `AppState` und lädt die Detektionen.

---

## 7. Hintergrundtasks – Konzept für Schritt 1

Im ersten Umbauschritt gibt es einen relevanten Hintergrundtask: die Audio-Generierung für den Audio-Player. Aktuell blockiert Streamlit den kompletten UI-Thread während der Audio-Generierung und zeigt nur einen statischen Spinner. Im neuen System wird die Audio-Generierung als echter asynchroner Task implementiert.

Der Task iteriert über die geladenen Detektionen, generiert für jede Detektion das Audio (Snippet + TTS), und schreibt das Ergebnis schrittweise in den AppState. Nach jeder generierten Audio-Datei sendet er ein Update-Event an die UI, die den Fortschrittsbalken aktualisiert. Der Audio-Player kann bereits mit den ersten verfügbaren Audio-Dateien starten, während die restlichen noch generiert werden.

Dieses Muster – Task schreibt in State, State-Änderung triggert UI-Update – ist das Grundmuster für alle zukünftigen Hintergrundoperationen im System.

---

## 8. Technologie-Entscheidungen

| Bereich | Bisherig (Streamlit) | Neu (NiceGUI) | Begründung |
|---|---|---|---|
| Web-Framework | Streamlit | NiceGUI + uvicorn | Event-Loop-Zugriff, Flexibilität |
| Heatmap | Altair | ECharts (via `ui.echart`) | Nativ in NiceGUI, Kontextmenü, Klick-Events |
| Tabellen / Grid | st-aggrid | `ui.aggrid` | Direkt verfügbar in NiceGUI |
| Species-Suche | streamlit-searchbox | Custom (ui.input + Dropdown) | Kein Äquivalent in NiceGUI, selbst gebaut |
| Audio-Player | HTML/JS (embedded) | HTML/JS (embedded via `ui.html`) | Bewährte Lösung, direkt übertragbar |
| State | st.session_state | AppState-Klasse (server-side) | Zentraler Server-State statt Client-State |
| Background-Tasks | Nicht möglich | asyncio.create_task() | Kernvorteil des Umbaus |

---

# BirdNET Play – Konzept NiceGUI-Umbau
## Teil 2: Database Overview (Seite 1)

---

## 1. Überblick dieser Seite

Die Database-Overview-Seite ist der Einstiegspunkt des Systems. Sie erfüllt vier Aufgaben: Sie ermöglicht die Auswahl der aktiven Datenbank, zeigt Metadaten zur gewählten Datenbank an, pflegt und zeigt die Species-Liste, und bietet einen Sprungpunkt zum Audio-Player für eine ausgewählte Spezies. Die Seite ist nicht der Ort für Audio-Wiedergabe oder Filteroperationen – sie ist der administrative Startpunkt.

**Elemente im Überblick:**
- Datenbankauswahl (Dropdown aus gescanntem Verzeichnis)
- Datenbankinfo (Sprache, Confidence-Schwelle, Erstellungsdatum, Anzahl Spezies)
- Notizfeld mit Speichern-Button
- Tabelle der Recording-Files
- Species-Liste (AG Grid, sortierbar, filterbar, selektierbar)
- CSV- und Excel-Download der Species-Liste
- "Actualize Species List"-Button
- Sidebar: Ausgewählte Spezies + "Play Species"-Button

---

## 2. Datenbankauswahl

Beim Start scannt der Server das übergebene Wurzelverzeichnis rekursiv nach Dateien mit dem Namen `birdnet_analysis.db`. Die gefundenen Pfade werden im AppState als Liste verfügbar gehalten. Diese Liste wird beim Seitenaufruf nicht neu gescannt – sie stammt aus dem AppState. Ein manueller "Rescan"-Button kann optional angeboten werden, ist aber für Schritt 1 nicht zwingend.

Die Auswahl der aktiven Datenbank erfolgt über ein Dropdown-Element (`ui.select`), das alle gefundenen Datenbankpfade auflistet. Der aktuell im AppState gesetzte Datenbankpfad ist vorausgewählt. Wenn der Nutzer eine andere Datenbank auswählt, wird folgendes ausgeführt: Der gesamte filter-bezogene State (Filter-State, Audio-Player-State, Heatmap-State) wird zurückgesetzt, die neue Datenbank wird als aktive Datenbank im AppState gesetzt, und alle angezeigten Metadaten werden neu geladen. Die Datenbankauswahl ist das einzige Element auf dieser Seite, das einen vollständigen State-Reset auslöst.

---

## 3. Datenbankinfo

Unterhalb der Datenbankauswahl werden vier Kennzahlen der aktiven Datenbank als Metrik-Elemente angezeigt. Diese Werte werden aus der Tabelle `analysis_config` der Datenbank gelesen:

Die **Sprache** (`local_name_shortcut`) bestimmt, welche Lokalnamen in der Species-Liste und im Audio-Player verwendet werden. Das **Confidence-Threshold** (`confidence_threshold`) ist der bei der Analyse verwendete Mindestschwellwert – er ist informativ, nicht als Filter nutzbar. Das **Erstellungsdatum** (`created_at`) zeigt an, wann die Datenbank erzeugt wurde. Die **Anzahl Spezies** wird aus der Tabelle `species_list` gezählt.

Wenn die `species_list`-Tabelle in der Datenbank nicht vorhanden ist (z.B. bei älteren Datenbanken), wird an ihrer Stelle ein Hinweis angezeigt und der Nutzer wird aufgefordert, die Species-Liste zu aktualisieren.

---

## 4. Species-Liste aktualisieren

Ein Button "Actualize Species List" löst die Neuerstellung der `species_list`-Tabelle aus. Dieser Vorgang liest alle Detektionen der Datenbank, aggregiert sie nach Spezies, berechnet den Score (`SUM(confidence^4)`) und schreibt die Ergebnisse in die `species_list`-Tabelle. Im Read-Only-Modus ist dieser Button deaktiviert.

Da dieser Vorgang bei großen Datenbanken einige Sekunden dauern kann, wird er im neuen System als Hintergrundtask ausgeführt. Während der Ausführung wird ein Fortschrittsindikator angezeigt. Nach Abschluss wird die Species-Liste auf der Seite automatisch aktualisiert, ohne dass der Nutzer die Seite neu laden muss.

---

## 5. Notizfeld

Ein mehrzeiliges Texteingabefeld (`ui.textarea`) zeigt den aktuell in `analysis_config` gespeicherten Kommentar (`user_comment`) zur Datenbank an. Der Nutzer kann den Text bearbeiten und über einen "Speichern"-Button in die Datenbank schreiben. Im Read-Only-Modus sind sowohl das Textfeld als auch der Speichern-Button deaktiviert. Das Notizfeld wird bei Datenbankwechsel neu geladen.

---

## 6. Recording-Files-Tabelle

Unterhalb des Notizfelds wird eine Tabelle aller Recording-Files der Datenbank angezeigt. Die Daten stammen aus der Tabelle `metadata`. Die Tabelle zeigt folgende Spalten: Dateiname, Startzeit (lokal), Endzeit (berechnet aus Startzeit + Dauer), Dauer in Sekunden, Temperatur in °C, Batteriespannung in Volt, GPS-Koordinaten (Lat/Lon als formatierter String, oder "N/A" wenn nicht vorhanden).

Die Tabelle ist rein informativ – sie ermöglicht keine Selektion oder Interaktion. Sie wird als einfache `ui.table` oder `ui.aggrid` (read-only) realisiert. Bei großen Datenbanken mit vielen Files kann Paginierung sinnvoll sein, ist aber für Schritt 1 optional.

---

## 7. Species-Liste (AG Grid)

Die Species-Liste ist das zentrale interaktive Element dieser Seite. Sie wird als AG Grid (`ui.aggrid`) realisiert und zeigt alle Spezies der Datenbank mit ihren Erkennungsstatistiken.

### 7.1 Spalten

Die Tabelle enthält folgende Spalten:

- **Scientific Name:** Wissenschaftlicher Name der Spezies. Breite ca. 250px.
- **Local Name:** Lokaler Name in der Datenbanksprache. Breite ca. 250px.
- **Czech Name:** Tschechischer Name (historisch bedingt, bleibt erhalten). Breite ca. 250px.
- **Detections:** Ein formatierter String, der die Anzahl hochkonfidenter Detektionen (≥70%), die Gesamtanzahl und den Score kombiniert darstellt. Die genaue Formatierung wird durch die Funktion `format_detections_column()` aus `shared/db_queries.py` bestimmt und bleibt unverändert. Breite ca. 220px.
- **Score:** Numerischer Score (`SUM(confidence^4)`), ausgeblendet, aber als Sortierbasis genutzt.

### 7.2 Standardsortierung und Filterung

Die Tabelle ist initial nach Score absteigend sortiert – die "besten" Spezies (häufigste und konfidenteste Erkennungen) erscheinen oben. Alle Spalten sind sortierbar und filterbar (AG Grid Standardfunktionalität). Die Score-Spalte ist ausgeblendet, wird aber als Sortierkriterium in der Grid-Konfiguration gesetzt.

### 7.3 Selektion

Die Tabelle erlaubt Single-Row-Selektion per Mausklick. Eine Checkbox-Spalte wird nicht verwendet. Wenn eine Zeile selektiert ist, wird der wissenschaftliche Name der Spezies im AppState als "ausgewählte Spezies" gespeichert. Gleichzeitig erscheint in der Sidebar ein Panel mit dem Namen der ausgewählten Spezies und einem "Play Species"-Button (siehe Abschnitt 9).

Die Selektion bleibt erhalten, solange dieselbe Datenbank aktiv ist. Bei Datenbankwechsel wird die Selektion zurückgesetzt.

### 7.4 AG Grid Konfiguration

Die Grid-Konfiguration wird über `GridOptionsBuilder` (analog zur Streamlit-Implementierung) oder direkt als Dictionary definiert. Folgende Eigenschaften werden gesetzt: `sortable=True`, `resizable=True`, `filterable=True` für alle Spalten, `rowSelection='single'`, initiale Sortierung nach Score absteigend.

---

## 8. Download der Species-Liste

Unterhalb des AG Grid befinden sich zwei Download-Buttons: "Download CSV" und "Download Excel". Beide Formate enthalten einen Metadaten-Header mit Datenbankpfad, Auswahlbereich (alle oder nur gefilterte Spezies), Datumsbereich der Aufnahmen und die Nutzernotizen.

Der Nutzer kann vor dem Download zwischen "All species" und "Only filtered species" wählen (Radio-Button). "Filtered" bezieht sich auf den aktuellen Filterzustand des AG Grid (z.B. wenn der Nutzer in einer Spalte nach einem Suchbegriff gefiltert hat).

**CSV-Format:** Metadaten-Header als Kommentarzeilen, dann die Tabellendaten als Standard-CSV mit UTF-8-Encoding.

**Excel-Format:** Zwei Sheets. Sheet 1 ("Database") enthält die Metadaten. Sheet 2 ("Species Table") enthält die Tabellendaten mit angepassten Spaltenbreiten, Zeilenumbrüchen und Seitenkopf/-fuß. Die Formatierung entspricht exakt der bisherigen Implementierung.

Der Download wird in NiceGUI über `ui.download()` realisiert, das eine Datei aus einem BytesIO-Buffer zum Browser sendet.

---

## 9. Sidebar: Spezies-Selektion und Navigation

Die Sidebar enthält auf dieser Seite ein kontextuelles Panel, das nur sichtbar ist, wenn eine Spezies im AG Grid ausgewählt ist. Das Panel zeigt den wissenschaftlichen Namen der ausgewählten Spezies in fetter Schrift und darunter einen prominenten Button "▶ Play Species".

Wenn der Nutzer "Play Species" klickt, werden folgende Aktionen im AppState ausgeführt: Der Spezies-Filter wird auf den ausgewählten wissenschaftlichen Namen gesetzt. Der Datumsbereich wird auf den vollständigen Aufnahmezeitraum der Datenbank gesetzt. Alle anderen Filter (Zeit, Confidence, Limit, Offset) werden auf ihre Standardwerte zurückgesetzt. Die Sortierung wird auf "Confidence absteigend" gesetzt (sinnvollste Reihenfolge für Spezies-Ansicht). Das Flag `filters_applied` wird auf `True` gesetzt, sodass der Audio-Player beim Öffnen sofort lädt.

Anschließend navigiert das System den Client zur Audio-Player-Seite. Der Audio-Player liest den vorbereiteten State aus dem AppState und startet die Detektionsabfrage ohne weiteren Nutzereingriff.

---

## 10. Xeno-Canto-Link

Wenn eine Spezies im AG Grid ausgewählt ist, wird in der Sidebar (unterhalb des Play-Buttons) oder direkt neben dem Spezies-Namen ein Link-Button "🔊 Xeno-Canto" angezeigt. Dieser öffnet Xeno-Canto im Browser mit dem wissenschaftlichen Namen der Spezies als Suchanfrage (`https://xeno-canto.org/explore?query=<name>&view=3`). Der Button ist deaktiviert, wenn keine Spezies ausgewählt ist.

---

## 11. Read-Only-Modus

Wenn der Server mit dem Flag `--read-only` gestartet wurde, ist der AppState entsprechend markiert. Auf dieser Seite hat das folgende Auswirkungen: Der "Actualize Species List"-Button ist deaktiviert. Das Notizfeld ist schreibgeschützt. Der "Speichern"-Button ist deaktiviert. Ein sichtbarer Hinweisbanner "🔒 Read-Only Mode" wird am oberen Rand der Seite angezeigt.

---

# BirdNET Play – Konzept NiceGUI-Umbau
## Teil 3: Audio Player (Seite 2)

---

## 1. Überblick dieser Seite

Der Audio Player ist die Kernseite des Systems. Er ermöglicht das gefilterte Abrufen von Vogelerkennungen aus der Datenbank, die Konfiguration von Audio-Optionen, die Generierung der kombinierten Audio-Dateien (Snippet + TTS) und deren Wiedergabe in einem eingebetteten Browser-Player. Zusätzlich können die generierten Dateien als WAV oder MP3 exportiert werden.

**Elemente im Überblick:**
- Filterbereich (Spezies, Datum, Zeit, Confidence, Limit, Offset, Sortierung)
- Xeno-Canto-Link (kontextuell)
- "Apply Filters"-Button
- Detektions-Statistik (Anzahl, geschätzte Gesamtdauer, Outputs/min)
- Detektionsliste (aufklappbar)
- Export-Buttons (WAV, MP3)
- Eingebetteter HTML/JS Audio-Player
- Sidebar: Audio-Optionen (TTS, Frame-Duration, Noise Reduction)

---

## 2. Filterbereich

### 2.1 Spezies-Filter mit Autocomplete

Das Spezies-Suchfeld ist eine eigens gebaute Autocomplete-Komponente, da NiceGUI kein fertiges Äquivalent zu `streamlit_searchbox` bietet. Die Komponente besteht aus einem Texteingabefeld (`ui.input`) und einem darunter erscheinenden Dropdown-Panel (`ui.menu` oder ein dynamisch erzeugtes `ui.list`), das nach jeder Tastatureingabe mit den Treffern aus `search_species_in_list()` befüllt wird.

Das Verhalten entspricht exakt dem bisherigen: Der Nutzer tippt mindestens ein Zeichen, das System sucht in der `species_list` nach übereinstimmenden wissenschaftlichen oder lokalen Namen, und zeigt bis zu 10 Treffer an. Die Treffer werden im Format "Scientific Name (Local Name)" angezeigt. Bei Auswahl eines Treffers wird der wissenschaftliche Name im AppState als aktiver Spezies-Filter gespeichert. Das Eingabefeld zeigt dann den ausgewählten Namen in einem Info-Element an, ergänzt durch einen "✕"-Button zum Löschen des Filters.

Wenn ein Spezies-Filter aktiv ist (z.B. von der Database-Overview-Seite übernommen), wird das Suchfeld nicht leer angezeigt, sondern zeigt den gesetzten Filter direkt als aktive Auswahl mit Lösch-Button.

### 2.2 Datumsbereich

Zwei Datumsfelder ("Date From" und "Date To") begrenzen die Suche auf einen Zeitraum. Die Standardwerte beim ersten Öffnen entsprechen dem vollständigen Aufnahmezeitraum der Datenbank (ermittelt über `get_recording_date_range()`). Die Werte werden im AppState gehalten und bleiben beim Seitenwechsel erhalten.

### 2.3 Zeitbereich (optional)

Ein Checkbox "Enable Time Filter" aktiviert zwei zusätzliche Zeitfelder ("Time Start", "Time End"), die die Suche auf eine Tageszeit einschränken. Wenn die Checkbox deaktiviert ist, werden die Zeitfelder ausgeblendet und der Filter auf den vollen Tagesbereich (00:00:00 bis 23:59:59) gesetzt. Das entspricht dem bisherigen Verhalten exakt.

### 2.4 Confidence, Limit, Offset, Sortierung

Diese vier Steuerelemente befinden sich in einer Zeile nebeneinander.

Das **Confidence**-Dropdown bietet die Optionen "All" sowie Prozentstufen von 5% bis 95% in 5%-Schritten. Der Standardwert ist 70%.

Das **Limit**-Feld ist ein Zahleneingabefeld (Minimum 1, Maximum 1000, Standardwert 25). Es begrenzt die maximale Anzahl zurückgegebener Detektionen.

Das **Offset**-Feld ist ein Zahleneingabefeld (Minimum 0, Schrittweite 10, Standardwert 0). Es ermöglicht Paginierung durch die Ergebnisse.

Die **Sortierung** ist ein Dropdown mit drei Optionen: "Time (oldest→newest)", "Confidence (high→low)" und "ID (upwards)". Der interne Sortierschlüssel (`time`, `confidence`, `id`) und die Sortierrichtung werden daraus abgeleitet: Confidence-Sortierung ist immer absteigend, die anderen aufsteigend.

### 2.5 Apply-Filters-Button

Ein prominenter "🔍 Apply Filters"-Button (volle Breite) löst die Datenbankabfrage aus. Er schreibt alle aktuellen Filterwerte aus den UI-Elementen in den AppState und startet die Abfrage über `query_detections()`. Während der Abfrage ist der Button deaktiviert.

Das Flag `filters_applied` im AppState steuert, ob der Audio-Player-Bereich unterhalb angezeigt wird. Solange keine Abfrage ausgeführt wurde (z.B. bei erstem Seitenaufruf ohne Vorauswahl von der Database-Seite), wird stattdessen ein Hinweis angezeigt.

---

## 3. Xeno-Canto-Link

Neben dem Spezies-Suchfeld befindet sich ein "🔊 Xeno-Canto"-Link-Button. Er ist aktiv, wenn ein Spezies-Filter gesetzt ist, und öffnet Xeno-Canto mit dem wissenschaftlichen Namen als Suchanfrage. Der Button ist deaktiviert, wenn kein Spezies-Filter aktiv ist. Das Verhalten ist identisch mit der Database-Overview-Seite.

---

## 4. Audio-Optionen (Sidebar)

Die Sidebar enthält alle Konfigurationsoptionen für die Audio-Generierung. Diese Optionen sind unabhängig von den Suchfiltern und gelten für alle generierten Audio-Dateien. Änderungen an den Audio-Optionen erfordern eine Neu-Generierung der Audio-Dateien (Cache-Invalidierung).

### 4.1 TTS-Optionen

**Say Audio Number** (Checkbox): Wenn aktiv, wird "Audio N" vor dem Snippet angesagt. Standard: deaktiviert.

**Say Bird Name** (Radio-Button, drei Optionen): "None" (kein Name), "Local Name" (lokaler Name in Datenbanksprache), "Scientific Name" (wissenschaftlicher Lateinname). Bei "Scientific Name" wird immer die deutsche TTS-Stimme verwendet, unabhängig von der Datenbanksprache, da lateinische Namen auf Deutsch besser klingen. Standard: "None".

**Say Database ID** (Checkbox): Wenn aktiv, wird "ID 12345" angesagt. Standard: deaktiviert.

**Say Confidence** (Checkbox): Wenn aktiv, wird der Konfidenzwert als ausgeschriebene Zahl mit "Prozent" angesagt (z.B. "siebenundachtzig Prozent"). Standard: deaktiviert.

### 4.2 Sprach- und Geschwindigkeitsoptionen

**Speech Speed** (Slider, 0.5 bis 2.0, Schrittweite 0.1): Steuert die Sprechgeschwindigkeit der TTS-Stimme. 1.0 ist normale Geschwindigkeit. Standard: 1.0.

**Speech Loudness** (Slider, -10 bis +4 dB, Schrittweite 1): Lautstärkekorrektur der TTS-Ansage relativ zum Vogelruf. Standard: -2 dB.

### 4.3 Audio Frame Duration

**Audio Frame Duration** (Slider, 0.5 bis 6.0 Sekunden, Schrittweite 0.5): Steuert den Plus-/Minus-Puffer um die 3-sekündige BirdNET-Detektion. Ein Wert von 1.0 Sekunde ergibt z.B. ein 5-sekündiges Snippet (1s + 3s + 1s). Standard: 1.0 Sekunde. Im UI wird dieser Parameter als "Audio Frame Duration" bezeichnet, nicht als "PM Buffer".

### 4.4 Noise Reduction

**Noise Reduction** (Checkbox): Aktiviert oder deaktiviert die Rauschreduzierung via `noisereduce`. Standard: aktiviert.

**Noise Reduction Strength** (Slider, nur sichtbar wenn Noise Reduction aktiv): Steuert den `prop_decrease`-Parameter der Rauschreduzierung. Der Slider hat 20 Stufen (Index 0–19), die auf einer logarithmischen Skala auf den Bereich 0.5 bis 1.0 abgebildet werden. Die logarithmische Skalierung sorgt dafür, dass die Stufen nahe 1.0 (stärkere Reduktion) feiner sind. Der aktuelle numerische Wert (`prop_decrease = X.XXX`) wird unterhalb des Sliders als Caption angezeigt. Standard: Index entsprechend 0.8 (prop_decrease).

### 4.5 Apply Audio Settings

Ein "🎵 Apply Audio Settings"-Button in der Sidebar löst die Cache-Invalidierung aus: Alle bisher generierten Audio-Dateien werden verworfen und müssen neu generiert werden. Dieser Button ist nötig, weil Audio-Optionen nicht sofort bei Änderung wirken sollen (der Nutzer soll mehrere Optionen auf einmal ändern können), sondern erst bei expliziter Bestätigung.

Zusätzlich gibt es einen "🔄 Clear Audio Cache"-Button, der den Cache ohne neue Generierung löscht – nützlich zur Fehlerdiagnose oder wenn der Nutzer die generierten Dateien einfach verwerfen möchte.

---

## 5. Detektions-Statistik

Nach erfolgreicher Abfrage werden drei Kennzahlen angezeigt:

**Single Audio Length:** Die geschätzte Dauer eines einzelnen Audio-Outputs in Sekunden. Sie setzt sich zusammen aus: 1.0s initiale Pause, Frame-Duration vor der Detektion, 3.0s Detektions-Snippet, Frame-Duration nach der Detektion, und eine geschätzte TTS-Dauer (abhängig davon, welche TTS-Elemente aktiv sind, korrigiert um die Speech-Speed). Die Berechnung erfolgt durch die Funktion `calculate_single_audio_length()`, die aus dem bestehenden Code übernommen wird.

**Outputs per Minute:** Berechnet als 60 / Single Audio Length. Zeigt an, wie viele Detektionen pro Minute abgespielt werden können.

**Total Playback Time:** Berechnet als (Anzahl Detektionen × Single Audio Length) / 60, angezeigt in Minuten.

Diese drei Metriken sind rein informativ und helfen dem Nutzer, die Wiedergabedauer vor dem Start abzuschätzen.

---

## 6. Detektionsliste

Unterhalb der Statistik befindet sich ein aufklappbares Element ("📋 Detection List"), das standardmäßig zugeklappt ist. Es listet alle geladenen Detektionen in nummerierter Form auf: Nummer, Detektions-ID, lokaler oder wissenschaftlicher Name, Konfidenz in Prozent, Zeitstempel. Diese Liste ist rein informativ und ermöglicht keine direkte Interaktion.

---

## 7. Export

Zwei Export-Buttons ("💾 Export as WAV" und "💾 Export as MP3") starten den Export der geladenen Detektionen als einzelne Audiodateien in ein temporäres Verzeichnis auf dem Server. Nach dem Export wird dem Nutzer der Pfad des Verzeichnisses angezeigt. Im Docker/Remote-Betrieb ist das der Pfad auf dem Server-System – der Nutzer muss das Verzeichnis über andere Wege (z.B. Shared Volume) zugänglich machen.

Der Export nutzt die bestehenden Funktionen `export_detections()` (WAV) und `export_detections_mp3()` (MP3) aus `birdnet_play/player.py` unverändert. Er wird als Hintergrundtask ausgeführt, mit Fortschrittsanzeige in der UI.

---

## 8. Audio-Generierung als Hintergrundtask

Dies ist der wichtigste Unterschied zur Streamlit-Implementierung.

In der bisherigen Implementierung blockiert die Audio-Generierung den gesamten UI-Thread: Der Nutzer sieht einen Spinner und kann nichts tun, bis alle Audio-Dateien fertig sind. Im neuen System wird die Audio-Generierung als AsyncIO-Task gestartet.

Der Task iteriert über die Detektionsliste und ruft für jede Detektion `prepare_detection_audio_web()` auf. Da diese Funktion synchron und CPU-intensiv ist, wird sie in einem Thread-Pool-Executor ausgeführt (`asyncio.get_event_loop().run_in_executor()`), damit die Event-Loop nicht blockiert wird. Nach jeder fertiggestellten Audio-Datei wird sie dem Cache im AppState hinzugefügt und der Fortschrittsbalken in der UI aktualisiert.

Sobald die erste Audio-Datei verfügbar ist, kann der eingebettete HTML/JS-Player bereits gestartet werden – er muss nicht auf die vollständige Generierung aller Dateien warten. Neue Dateien werden dem Player-Playlist-Array im Browser dynamisch hinzugefügt, solange der Task läuft.

Der Generierungs-Task wird nur dann gestartet, wenn der Cache ungültig oder leer ist (nach "Apply Filters", "Apply Audio Settings" oder "Clear Audio Cache"). Ist der Cache gültig, wird er direkt verwendet.

---

## 9. Eingebetteter HTML/JS Audio-Player

Der Audio-Player wird als eingebettetes HTML/JS-Komponente in die Seite eingebettet (`ui.html`). Die Architektur und das Verhalten des Players bleiben gegenüber der Streamlit-Implementierung vollständig erhalten:

Die Audio-Dateien werden als Base64-kodierte MP3-Daten in ein JavaScript-Array übergeben. Der Player zeigt "Now Playing" mit Detektions-ID, Speziesname, Konfidenz und Zeitstempel. Ein Fortschrittsbalken zeigt die Position in der Playlist (N / Gesamt). Steuerelemente sind: Play/Pause, Previous, Next, Stop. Nach Ende einer Datei wird automatisch die nächste geladen und abgespielt. Eine "Recently Played"-Liste zeigt die zuletzt abgespielten Detektionen.

Die HTML/JS-Implementierung wird aus der bisherigen Streamlit-Implementierung direkt übernommen. Die einzige Änderung betrifft die Übergabe der Audio-Daten: Statt eines vollständig vorgenerierten JSON-Arrays kann das Array schrittweise erweitert werden, wenn der Generierungs-Task neue Dateien liefert. Dafür wird ein kleiner JavaScript-Mechanismus ergänzt, der periodisch prüft, ob neue Einträge im Array verfügbar sind.

---

## 10. Cache-Verwaltung

Der Audio-Cache wird als Dictionary im AppState gehalten. Der Cache-Schlüssel ist ein Hash über alle relevanten Parameter: Detektions-IDs, Frame-Duration, Audio-Optionen (TTS-Einstellungen, Noise-Reduction-Parameter). Ändert sich einer dieser Parameter, ist der Cache ungültig.

Der Cache wird in folgenden Situationen geleert: nach "Apply Filters" (neue Detektionsliste), nach "Apply Audio Settings" (geänderte Audio-Parameter), nach manuellem "Clear Audio Cache". Der Cache wächst nicht unbegrenzt – er enthält immer nur die Audio-Dateien der aktuell geladenen Detektionsliste.

Da der Cache im Server-State liegt, überlebt er eine Client-Verbindungstrennung. Ein Client, der sich neu verbindet, findet den Cache vor und kann sofort abspielen, ohne neu zu generieren.

---

# BirdNET Play – Konzept NiceGUI-Umbau
## Teil 4: Activity Heatmap, Querschnittsthemen und Implementierungshinweise

---

## 1. Activity Heatmap (Seite 3)

### 1.1 Überblick

Die Heatmap-Seite visualisiert die zeitliche Verteilung von Vogelerkennungen über einen Datumsbereich. Die X-Achse zeigt Tage, die Y-Achse zeigt Tageszeit in 30-Minuten-Intervallen (48 Slots von 00:00 bis 23:30). Jede Zelle repräsentiert die Aktivität in einem 30-Minuten-Fenster an einem bestimmten Tag – entweder als Summe der Konfidenzwerte oder als Anzahl der Detektionen.

**Elemente im Überblick:**
- Filterbereich (Spezies, Datum, Confidence)
- "Apply Filters"-Button
- Heatmap-Optionen (Colormap, Gewichtungsmodus)
- ECharts-Heatmap (interaktiv, klickbar, mit Tooltip)
- Klick-Dialog (Zellen-Details + Audio-Player)
- Export (PNG, CSV)

### 1.2 Filterbereich

Der Filterbereich der Heatmap-Seite ist schlanker als der des Audio-Players. Er enthält:

Den **Spezies-Filter**: dieselbe Autocomplete-Komponente wie auf der Audio-Player-Seite. Der Filter kann leer sein (alle Spezies) oder eine Spezies selektiert haben. Der aktive Filter wird im AppState unter einem eigenen Schlüssel (`heatmap_filter_species`) gehalten, getrennt vom Audio-Player-Filter, damit beide Seiten unabhängig gefiltert werden können.

Den **Datumsbereich**: zwei Datumsfelder ("Date From", "Date To") mit denselben Standardwerten wie auf der Audio-Player-Seite (vollständiger Aufnahmezeitraum), aber ebenfalls im AppState getrennt gehalten (`heatmap_filter_date_from`, `heatmap_filter_date_to`).

Das **Confidence-Dropdown**: dieselben Optionen wie auf der Audio-Player-Seite ("All", 5% bis 95% in 5%-Schritten). Standard: 70%.

Ein **"Apply Filters"-Button** (volle Breite) löst die Datenbankabfrage und die Aggregation aus.

### 1.3 Heatmap-Optionen

Zwei Optionen steuern die Darstellung der Heatmap und sind in der Sidebar oder als Inline-Controls oberhalb der Heatmap platziert:

**Colormap**: Ein Dropdown mit 16 Colormap-Optionen. Die verfügbaren Optionen entsprechen exakt der bisherigen Implementierung: inferno, viridis, plasma, magma, turbo, blues, greens, reds, oranges, purples, greys, blueorange, redyellowblue, redyellowgreen, spectral, rainbow. Standard: turbo. ECharts unterstützt lineare Farbverläufe über `visualMap`; die Colormap-Namen müssen auf ECharts-kompatible Farbdefinitionen abgebildet werden (Startfarbe → Endfarbe, oder mehrstufige Stops für komplexere Colormaps).

**Weight by Confidence** (Checkbox): Wenn aktiv, zeigt jede Zelle die Summe der Konfidenzwerte aller Detektionen in diesem Zeitfenster. Wenn deaktiviert, zeigt die Zelle die Anzahl der Detektionen. Standard: aktiv.

### 1.4 Datenaggregation

Die Aggregationslogik wird aus der bisherigen Implementierung vollständig übernommen. Sie läuft als serverseitige Python-Funktion und erzeugt eine strukturierte Datenmenge, die direkt an ECharts übergeben werden kann.

Die Aggregation iteriert über alle geladenen Detektionen und bestimmt für jede Detektion das Datum und den 30-Minuten-Slot (Slot-Index = Stunde × 2 + (1 wenn Minute ≥ 30, sonst 0)). Pro Kombination aus Datum und Slot werden die Konfidenzwerte summiert und die Anzahl gezählt. Zellen ohne Detektionen erhalten den Wert 0.

Das Ergebnis ist eine vollständige Matrix über alle Tage im gewählten Datumsbereich und alle 48 Slots. Auch Tage ohne Detektionen sind in der Matrix enthalten (mit 0-Werten), sodass die Heatmap immer einen lückenlosen Datumsbereich zeigt.

### 1.5 ECharts-Heatmap-Konfiguration

Die Heatmap wird über `ui.echart` mit einer ECharts-Konfiguration realisiert. Die relevanten Konfigurationselemente sind:

**X-Achse (Datum):** Die X-Achse ist eine Kategorie-Achse mit den Datumswerten als Labels. Nur Montage werden mit einem Label versehen (Format: "TT.MM."), alle anderen Tage bleiben unbeschriftet. Dies entspricht dem bisherigen Verhalten und verhindert Überlappungen bei langen Zeiträumen.

**Y-Achse (Tageszeit):** Die Y-Achse ist eine Kategorie-Achse mit 48 Einträgen (00:00 bis 23:30 in 30-Minuten-Schritten). Nur jede 6. Stunde (00:00, 06:00, 12:00, 18:00) erhält ein Label. Die Achse ist invertiert, sodass 00:00 oben und 23:30 unten erscheint – identisch zur bisherigen Darstellung.

**Zellen-Farbe:** Zellen mit dem Wert 0 werden weiß dargestellt (keine Aktivität). Zellen mit Werten größer 0 werden nach der gewählten Colormap eingefärbt. Der Maximalwert der Farbskala (`colorscale_max`) ist der größte vorhandene Zellwert, mindestens aber 4 (Konstante `MIN_COLORSCALE_MAX = 4`, aus der bisherigen Implementierung).

**Tooltip:** Beim Hovern über eine Zelle erscheint ein Tooltip mit: Datum (Format "TT.MM."), Uhrzeit (Format "HH:MM"), Summe der Konfidenzwerte bzw. Anzahl (je nach Gewichtungsmodus), Anzahl der Detektionen, Durchschnittliche Konfidenz. Das Format entspricht exakt der bisherigen Tooltip-Logik.

**Zellgröße:** Jede Zelle ist 12×12 Pixel groß (Konstante `HEATMAP_CELL_SIZE = 12`). Die Gesamtbreite der Heatmap ergibt sich aus Anzahl der Tage × 12, die Gesamthöhe aus 48 × 12 = 576 Pixel.

**Klick-Event:** ECharts löst bei Klick auf eine Zelle ein JavaScript-Event aus, das über NiceGUI's Event-Binding-Mechanismus an den Python-Server weitergeleitet wird. Der Server erhält Datum-Index und Slot-Index der angeklickten Zelle, sucht den entsprechenden Eintrag in der Aggregationsmatrix und öffnet den Klick-Dialog.

**Kontextmenü:** ECharts unterstützt ein rechtsseitiges Kontextmenü via `contextMenu`-Event. Für Schritt 1 wird das Kontextmenü noch nicht vollständig ausgebaut, aber die Event-Infrastruktur wird so angelegt, dass es nachträglich befüllt werden kann. Im ersten Schritt kann das Kontextmenü dieselbe Aktion wie ein Linksklick auslösen (Dialog öffnen).

### 1.6 Klick-Dialog

Wenn der Nutzer auf eine Heatmap-Zelle klickt, öffnet sich ein modaler Dialog (`ui.dialog`). Der Dialog zeigt:

Im **Header-Bereich**: Datum der Zelle (Format "TT.MM.YYYY"), Zeitfenster (z.B. "06:00 – 06:29"), aktiver Spezies-Filter oder "All species", und drei Metriken: Anzahl der Detektionen, Summe der Konfidenzwerte (oder Anzahl im Count-Modus), Durchschnittliche Konfidenz.

Im **Detektions-Bereich**: Nach dem Öffnen des Dialogs werden die bis zu 25 höchstkonfidenten Detektionen aus dem gewählten 30-Minuten-Fenster geladen (`query_detections()` mit `time_range`, `date_from=date_to=clicked_date`, `limit=25`, `sort_by="confidence"`, `sort_order="desc"`, `min_confidence` aus dem aktiven Heatmap-Filter).

Im **Audio-Bereich**: Die geladenen Detektionen werden als Audio aufbereitet (über `prepare_detection_audio_simple()`, ohne TTS, mit 0.5s PM-Buffer). Die Generierung erfolgt als Hintergrundtask mit Fortschrittsbalken im Dialog. Der eingebettete HTML/JS-Audio-Player ist derselbe wie auf der Audio-Player-Seite, in einer kompakteren Version (ohne "Recently Played"-Liste, kleinere Steuerelemente).

Der Dialog kann über einen Schließen-Button oder durch Klicken außerhalb des Dialogs geschlossen werden. Beim Schließen werden die für diesen Dialog generierten Audio-Dateien verworfen (sie werden nicht im globalen AppState-Cache gehalten, da sie kurzlebig sind).

### 1.7 Export

**PNG-Export:** Die ECharts-Instanz bietet eine eingebaute `getDataURL()`-Methode, mit der das aktuelle Chart als PNG exportiert werden kann. NiceGUI kann diesen Export über einen JavaScript-Call auslösen und die Bilddaten zum Browser senden. Der Dateiname folgt dem Schema `heatmap_<spezies>_<datum_von>_<datum_bis>.png`.

**CSV-Export:** Die Aggregationsmatrix wird als CSV exportiert. Die Zeilen sind die 48 Zeitslots, die Spalten sind die Tage. Der Dateiname folgt dem Schema `heatmap_<spezies>_<datum_von>_<datum_bis>.csv`. Der Export entspricht exakt der bisherigen Implementierung und wird serverseitig erzeugt, dann über `ui.download()` zum Browser gesendet.

---

## 2. Querschnittsthemen

### 2.1 Navigationsstruktur

Die drei Seiten sind über eine persistente Navigationsleiste verbunden. In NiceGUI wird diese typischerweise als `ui.left_drawer` oder als Header-Element (`ui.header`) mit Navigations-Buttons realisiert. Die Navigationsleiste ist auf allen drei Seiten identisch und enthält die drei Seitennamen als klickbare Elemente. Die aktive Seite ist hervorgehoben.

Die Navigation erfolgt über `ui.navigate.to('/audio-player')` o.ä. – NiceGUI leitet den Browser zur entsprechenden Route um. Da der AppState serverseitig ist, gehen beim Seitenwechsel keine Daten verloren.

### 2.2 Datenbankinfo im Header

Auf jeder Seite wird unterhalb des Seitentitels die aktive Datenbank und die Datenbanksprache als kompakter Info-Text angezeigt (`db_path.name`, `language_code`). Das entspricht dem bisherigen Verhalten.

### 2.3 Fehlerbehandlung

Fehlerzustände (keine Datenbank gefunden, Datenbankfehler, Audio-Generierungsfehler) werden als sichtbare Fehler-Benachrichtigungen (`ui.notify()` mit `type='negative'`) angezeigt. Bei kritischen Fehlern (keine Datenbank gefunden beim Start) wird eine Fehlerseite angezeigt und die Navigation ist deaktiviert.

### 2.4 Read-Only-Modus

Der Read-Only-Modus wird beim Start des Servers als Flag (`--read-only`) gesetzt und im AppState gespeichert. Er wirkt sich auf alle drei Seiten aus: Schreiboperationen (Notizen speichern, Species-Liste aktualisieren) sind deaktiviert. Ein Banner ist auf jeder Seite sichtbar.

---

## 3. Implementierungshinweise

Dieser Abschnitt löst Interpretationsspielräume auf, die sich aus der textuellen Beschreibung ergeben, und zeigt, wie bestehender Code im neuen System aufgegriffen wird.

### 3.1 Server-Einstiegspunkt

Der neue Server-Einstiegspunkt ersetzt `cli.py` für den UI-Modus. Die Grundstruktur orientiert sich an `gui_prc.py`, ist aber erheblich schlanker, da kein Shared Memory und kein Subprocess-Kontext benötigt wird:

```python
async def run_server(root_path: Path, read_only: bool = False):
    app_state = AppState(root_path=root_path, read_only=read_only)

    app.on_startup(lambda: asyncio.create_task(startup_tasks(app_state)))

    config = Config(app, host='0.0.0.0', port=8080, log_level='warning')
    server = Server(config)
    await server.serve()
```

`app.on_startup()` registriert den initialen Task (Datenbank-Scan, Laden des letzten States). Die uvicorn-`Server`-Instanz ist im Scope von `run_server` verfügbar, sodass `server.should_exit` von einem Shutdown-Monitor-Task gesetzt werden kann.

### 3.2 AppState-Klasse

```python
@dataclass
class AppState:
    # System
    root_path: Path
    read_only: bool
    available_dbs: List[Path] = field(default_factory=list)
    active_db: Optional[Path] = None
    language_code: str = 'de'

    # Audio Player Filter
    ap_filter_species: Optional[str] = None
    ap_filter_date_from: Optional[date] = None
    ap_filter_date_to: Optional[date] = None
    ap_filter_use_time: bool = False
    ap_filter_time_start: time = time(0, 0, 0)
    ap_filter_time_end: time = time(23, 59, 59)
    ap_filter_confidence: Optional[float] = 0.70
    ap_filter_limit: int = 25
    ap_filter_offset: int = 0
    ap_filter_sort: str = 'time'
    ap_filters_applied: bool = False

    # Audio Options
    audio_say_number: bool = False
    audio_bird_name: str = 'none'   # 'none', 'local', 'scientific'
    audio_say_id: bool = False
    audio_say_confidence: bool = False
    audio_speech_speed: float = 1.0
    audio_speech_loudness: int = -2
    audio_frame_duration: float = 1.0
    audio_noise_reduction: bool = True
    audio_noise_reduce_strength: float = 0.8

    # Audio Player Runtime
    detections: List[Dict] = field(default_factory=list)
    audio_cache: Dict[str, str] = field(default_factory=dict)  # det_id -> base64
    audio_generation_progress: float = 0.0  # 0.0 - 1.0

    # Heatmap Filter
    hm_filter_species: Optional[str] = None
    hm_filter_date_from: Optional[date] = None
    hm_filter_date_to: Optional[date] = None
    hm_filter_confidence: Optional[float] = 0.70
    hm_filters_applied: bool = False

    # Heatmap Options
    hm_colormap: str = 'turbo'
    hm_weight_confidence: bool = True
    hm_aggregated_data: Optional[pd.DataFrame] = None
```

### 3.3 Autocomplete-Spezies-Suche

Das Autocomplete-Pattern in NiceGUI:

```python
async def update_species_suggestions(input_el, menu_el, search_term: str):
    results = search_species_in_list(app_state.active_db, search_term, limit=10)
    menu_el.clear()
    for r in results:
        menu_el.add_item(r, on_click=lambda r=r: select_species(r))
    if results:
        menu_el.open()
    else:
        menu_el.close()

species_input = ui.input(placeholder='Search species...') \
    .on('keyup', lambda e: update_species_suggestions(
        species_input, species_menu, species_input.value
    ))
species_menu = ui.menu()
```

### 3.4 Audio-Generierungs-Task

```python
async def generate_audio_task(app_state: AppState, player: AudioPlayer):
    app_state.audio_cache.clear()
    app_state.audio_generation_progress = 0.0

    loop = asyncio.get_event_loop()
    for i, det in enumerate(app_state.detections):
        # CPU-intensive Arbeit in Thread-Pool auslagern
        audio_bytes = await loop.run_in_executor(
            None,
            player.prepare_detection_audio_web,
            det, i + 1, app_state.language_code,
            filter_context, audio_options
        )
        b64 = base64.b64encode(audio_bytes.read()).decode()
        app_state.audio_cache[str(det['detection_id'])] = b64
        app_state.audio_generation_progress = (i + 1) / len(app_state.detections)
        # UI-Update auslösen (z.B. über ui.update oder direkte Label-Aktualisierung)
```

### 3.5 ECharts-Heatmap – Colormap-Abbildung

ECharts kennt keine Colormap-Namen wie "turbo" oder "viridis". Jede Colormap muss als Farbverlauf definiert werden. Für den ersten Schritt ist eine Mapping-Tabelle ausreichend, die für jede der 16 Colormaps Anfangs- und Endfarbe (oder mehrere Stützstellen) als Hex-Werte definiert. Beispiel für zwei Colormaps:

```python
ECHARTS_COLORMAPS = {
    'turbo':   ['#30123b', '#1ac7c2', '#eded30', '#fb4e16', '#7a0403'],
    'viridis': ['#440154', '#31688e', '#35b779', '#fde725'],
    'inferno': ['#000004', '#721f81', '#f16745', '#fcffa4'],
    # ... (alle 16 Colormaps)
}
```

Die `visualMap`-Komponente von ECharts nimmt diese Farbstops entgegen und interpoliert dazwischen.

### 3.6 HTML/JS-Player – Übergabe schrittweise generierter Daten

Der bestehende HTML/JS-Player erwartet ein vollständiges `audioFiles`-Array beim Initialisieren. Um schrittweise generierte Daten zu unterstützen, wird der Player leicht erweitert: Er prüft periodisch (über `setInterval`) ob eine globale Variable `pendingAudioFiles` neue Einträge enthält und fügt diese dem internen Array hinzu. NiceGUI kann diese Variable über `ui.run_javascript()` befüllen, wenn neue Audio-Dateien verfügbar sind.

```javascript
// Im Player-HTML ergänzen:
setInterval(() => {
    if (window.pendingAudioFiles && window.pendingAudioFiles.length > 0) {
        audioFiles.push(...window.pendingAudioFiles);
        window.pendingAudioFiles = [];
        updateButtons();
    }
}, 500);
```

---

## 4. Abgrenzung zu späteren Ausbaustufen

Das in diesem Konzept beschriebene System ist vollständig in sich geschlossen für den Funktionsumfang des bisherigen Streamlit-Systems. Die Architektur-Entscheidungen – dauerhafter Server-Prozess, zentraler AppState, AsyncIO-Tasks, gespawnter Prozess, direkter Event-Loop-Zugriff – sind dabei bewusst so gewählt, dass sie für spätere Ausbaustufen keine Umbauten erfordern:

Der Walker (Ausbaustufe 2) wird als weiterer Hintergrundtask in denselben Server eingehängt. Er bekommt eigene State-Felder im AppState und eigene Seiten in der Navigation.

Die Embedding-Vektor-Analyse (Ausbaustufe 3) bringt potenziell lang laufende Berechnungen mit. Diese werden als Tasks mit detailliertem Progress-Feedback realisiert – das Grundmuster ist in Ausbaustufe 1 bereits etabliert.

Der Filebrowser wird als eine weitere Seite implementiert. NiceGUI ermöglicht rekursives Verzeichnis-Rendering und Interaktion ohne Einschränkungen.

Remote- und Docker-Betrieb sind von Beginn an unterstützt, da der Server auf `0.0.0.0` lauscht und keine lokalen GUI-Bibliotheken benötigt.

---




