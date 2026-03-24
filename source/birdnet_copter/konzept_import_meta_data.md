# Konzept: Import neuer Audiodaten in birdnet-copter

---

## 1. Grundprinzip

**Eine Datenbank = ein Ort.** Der Nutzer ist verantwortlich dafür, seine Audiofiles so in Ordnern vorzusortieren, dass alle Files eines Ordners zu einem einzigen geographischen Ort gehören. Das Programm kommuniziert diese Regel explizit im UI.

Ziel des Import-Konfigurationsdialogs ist es, für einen Ordner genau zwei Pflichtinformationen sicherzustellen:

- **lat/lon** – eine einzige geographische Position für alle Files des Ordners (WGS84)
- **UTC-Startzeit** – ein absoluter UTC-Zeitstempel für jedes einzelne Audiofile

Erst wenn beide vollständig und vom Nutzer bestätigt sind, wird die SQLite-Datenbankdatei angelegt (mit vollständiger Tabellenstruktur, aber zunächst nur mit diesen Kerndaten befüllt). Erst dann ist der Ordner für den Scouting Flight freigegeben.

---

## 2. Import-Konfigurationsdialog

Der Dialog wird pro Ordner aufgerufen. Er besteht aus vier Bereichen: Kartenansicht (GPS), Metadaten-Übersicht, Zeitstempel-Zuordnung und Ergebnis-Vorschau.

### 2.1 Kartenansicht (GPS)

Eine eingebettete Karte (OpenStreetMap, z.B. via `folium` oder einer NiceGUI-kompatiblen Kartenlösung) wird angezeigt. Sie dient gleichzeitig zur Eingabe und zur Kontrolle der GPS-Position.

- Wenn GPS-Koordinaten aus den Metadaten einzelner Files extrahiert wurden (z.B. aus dem GUANO-Chunk von AudioMoth), werden alle gefundenen Positionen als Punkte auf der Karte eingeblendet. Der Nutzer erkennt sofort Ausreißer (z.B. Labor-Initialisierung des Geräts an einem anderen Ort).
- Der Nutzer kann per Klick auf die Karte eine einzige endgültige Position für die gesamte DB festlegen. Vorhandene GUANO-Koordinaten werden als Vorschlag verwendet (z.B. Mittelwert oder häufigster Cluster), können aber überschrieben werden.
- Die final gewählte lat/lon-Position wird prominent angezeigt und ist manuell editierbar (Eingabefelder für lat und lon).

**Offene Frage:** Wie gehen wir mit stark streuenden GUANO-Koordinaten um (z.B. Gerät bewegt sich während der Aufnahme)? Warnung anzeigen? Oder ist das außerhalb des vorgesehenen Anwendungsfalls?

### 2.2 Metadaten-Übersicht

Ein scrollbarer Kasten (max. 700 Pixel Höhe) listet für jedes File im Ordner alle extrahierbaren Rohdaten auf. Ziel ist Transparenz: Der Nutzer sieht, was das Programm aus den Files herauslesen konnte.

Angezeigte Felder pro File (soweit vorhanden):
- Dateiname
- Alle gefundenen Zeitfelder (GUANO-Timestamp, ICMT-Timestamp, Dateiname-Kandidaten, Dateisystem-Erstellzeit, Dateisystem-Änderungszeit)
- GPS-Koordinaten (falls in Metadaten enthalten)
- Geräteinformationen (Seriennummer, Firmware, Gain, Temperatur, Akkuspannung – alles was extrahierbar ist)
- Technische Audiodaten (Samplerate, Kanalzahl, Bittiefe, Dauer)

Die Darstellung ist rein informativ – keine Editierfelder in diesem Kasten.

### 2.3 Zeitstempel-Zuordnung

Dieser Bereich ist das Herzstück des Dialogs. Er besteht aus drei Teilen:

**Teil A: Zeitquellen-Auswahl**

Ein Auswahlfeld (Dropdown) listet alle im Ordner verfügbaren Zeitquellen auf, die grundsätzlich als Startzeit-Kandidat geeignet sind. Die Liste wird automatisch befüllt (siehe Abschnitt 3). Der Nutzer wählt, welche Quelle als Basis verwendet werden soll. Die adaptive Bewertung liefert einen Vorschlag, welche Quelle am wahrscheinlichsten korrekt ist (markiert als "Empfehlung").

Beispieleinträge im Dropdown:
- „GUANO-Timestamp (UTC erkannt) – **Empfehlung**"
- „Dateiname-Muster `YYYYMMDD_HHMMSS` (UTC angenommen)"
- „Dateisystem-Erstellzeit (Lokalzeit des Rechners)"

**Teil B: Globaler Zeitoffset**

Über dem scrollbaren Zeitstempel-Kasten befindet sich ein einzelnes Eingabefeld für einen globalen Zeitoffset (Format: `+HH:MM` oder `-HH:MM`, auch Sekunden möglich). Dieser Offset wird auf alle erkannten Zeitstempel der gewählten Quelle angewendet und aktualisiert die Editierfelder im Kasten sofort. Typischer Anwendungsfall: systematische Uhr-Abweichung des Geräts.

**Teil C: Scrollbarer Zeitstempel-Kasten**

Für jedes File zwei nebeneinanderliegende Felder:

- **Linkes Feld (read-only):** Die aus der gewählten Quelle extrahierte Startzeit, nach Anwendung des globalen Offsets. Beschriftet mit dem Zeitzonenhinweis der Quelle (z.B. „UTC", „MEZ", „unbekannt").
- **Rechtes Feld (editierbar, explizit als UTC gekennzeichnet):** Initialisiert mit dem UTC-Wert aus dem linken Feld (nach Konvertierung durch den adaptiven UTC-Algorithmus, siehe Abschnitt 4). Der Nutzer kann pro File manuell überschreiben.

### 2.4 Ergebnis-Vorschau

Ein weiterer scrollbarer Kasten zeigt die finalen Werte, so wie sie in die Datenbank übernommen werden. Vier Zeitspalten nebeneinander:

1. **UTC** – der UTC-Zeitstempel, der in die DB eingetragen wird (aus den rechten Feldern in 2.3)
2. **Politische Lokalzeit** – UTC umgerechnet in die Zeitzone, die `timezonefinder` für die gewählte lat/lon-Position liefert, ohne Sommerzeitkorrektur (Standardzeit)
3. **Politische Lokalzeit mit DST** – wie Spalte 2, aber mit Sommerzeit-Korrektur gemäß `zoneinfo`
4. **Solare Ortszeit** – UTC + längengrad-basierter fester Offset (Längengrad / 15 * 3600 Sekunden), keine politische Zeitzone

Zusätzlich: An der Stelle in der Liste, wo ein Sommerzeitwechsel stattfindet (erkennbar am Sprung in Spalte 3), wird eine visuelle Trennlinie mit Beschriftung eingeblendet (z.B. „⬆ Beginn Sommerzeit" oder „⬇ Ende Sommerzeit"). Der Nutzer kann so prüfen, ob die Umschaltung zum erwarteten Zeitpunkt erfolgt.

---

## 3. Adaptive Zeitquellen-Erkennung

Dieses Modul analysiert alle Files eines Ordners und liefert eine priorisierte Liste verfügbarer Zeitquellen. Es ist unabhängig vom UTC-Konvertierungsalgorithmus (Abschnitt 4).

### 3.1 Extraktionsquellen (in Prioritätsreihenfolge als Vorschlag)

1. **GUANO-Chunk** – expliziter Timestamp-Eintrag im GUANO-Metadatenblock
2. **ICMT-Chunk** – Freitextfeld im WAV-LIST-Chunk, wie von AudioMoth befüllt
3. **Dateiname** – adaptive Erkennung von Datum/Uhrzeit-Mustern im Dateinamen (siehe 3.2)
4. **Dateisystem-Erstellzeit** – als letzter Fallback, explizit als unzuverlässig gekennzeichnet
5. **Dateisystem-Änderungszeit** – nur als Notfalloption, noch unzuverlässiger

Jede Quelle, die für mindestens einen Großteil der Files im Ordner einen auswertbaren Wert liefert, erscheint im Dropdown.

### 3.2 Adaptive Dateiname-Erkennung

Der Dateiname wird auf Datum/Uhrzeit-Muster untersucht. Da verschiedene Geräte und Software unterschiedliche Formate verwenden, prüft der Algorithmus mehrere Interpretationsvarianten und bewertet sie per Score.

**Scoring-Kriterien:**
- Ergibt das erkannte Datum ein plausibles Kalenderdatum? (z.B. Monat 1–12, Tag 1–31)
- Ergibt die erkannte Uhrzeit eine plausible Zeit? (Stunden 0–23, Minuten/Sekunden 0–59)
- Sind die erkannten Zeitstempel über alle Files des Ordners monoton steigend? (Aufnahmen sollten chronologisch sein)
- Ist der Abstand zwischen aufeinanderfolgenden Files konsistent mit der Dateidauer? (z.B. File A endet um T, File B beginnt bei T + kleiner Puffer)
- Stimmt die Größenordnung des erkannten Jahres? (plausibles Jahr, z.B. 2015–2035)

Die Variante mit dem höchsten Score wird als Empfehlung markiert. Bei Gleichstand oder niedrigem Score wird keine Empfehlung ausgesprochen und der Nutzer zur manuellen Auswahl aufgefordert.

**Offene Frage:** Sollen wir eine feste Bibliothek von bekannten Geräte-Dateinamenformaten pflegen (z.B. AudioMoth: `YYYYMMDD_HHMMSS.WAV`), oder rein adaptiv ohne Geräte-Whitelisting arbeiten?

---

## 4. Adaptiver UTC-Konvertierungsalgorithmus

Dieses Modul wird als eigenständiges Python-Modul implementiert, das unabhängig vom Rest des Imports erweiterbar ist. Es nimmt eine erkannte Zeitstempel-Sequenz (alle Files eines Ordners) sowie verfügbare Kontextinformationen entgegen und liefert für jeden Zeitstempel eine UTC-Entsprechung mit Konfidenzangabe.

### 4.1 Erkennungslogik (in Reihenfolge)

**Schritt 1: Explizite UTC-Kennzeichnung**

Wenn die Zeitquelle eine explizite UTC-Angabe enthält (z.B. GUANO-Feld `Timestamp` mit Suffix `Z` oder explizitem UTC-Vermerk), wird dieser Wert direkt übernommen. Keine weitere Konvertierung nötig. Konfidenz: hoch.

**Schritt 2: Zeitzone aus lat/lon**

Wenn lat/lon bekannt ist (aus Kartenauswahl oder GUANO), ermittelt `timezonefinder` den IANA-Zeitzonennamen. Dieser dient als Ausgangshypothese: Die erkannten Zeitstempel werden als Lokalzeit dieser Zeitzone interpretiert und in UTC umgerechnet. Als Startwert wird die Standardzeit (ohne Sommerzeit) verwendet.

**Schritt 3: DST-Sprung-Erkennung**

Der Algorithmus prüft, ob in der Zeitstempel-Sequenz ein Sprung vorkommt, der dem erwarteten Sommerzeitwechsel an diesem Ort entspricht:
- Sprung von +1h an dem für diese Zeitzone bekannten DST-Beginn-Datum → Quelle ist in Lokalzeit mit Sommerzeit
- Sprung von -1h an dem bekannten DST-End-Datum → konsistent mit Lokalzeit inklusive Sommerzeitumschaltung

Wenn ein solcher Sprung erkannt wird, wird die Konvertierung entsprechend angepasst: Zeitstempel vor dem Sprung werden als Standardzeit, nach dem Sprung als Sommerzeit behandelt.

Wenn kein Sprung erkannt wird (z.B. weil die Aufnahmen nicht über den Umschaltzeitpunkt hinausgehen), wird als Annahme die Standardzeit der Zeitzone verwendet (kein Sommerzeit-Offset).

**Schritt 4: Fallback**

Wenn weder explizite UTC-Kennzeichnung noch lat/lon verfügbar sind, wird der Zeitstempel als UTC interpretiert (mit niedriger Konfidenz) und der Nutzer im UI explizit darauf hingewiesen, dass eine manuelle Prüfung erforderlich ist.

### 4.2 Erweiterbarkeit

Das Modul ist so strukturiert, dass neue Erkennungsregeln als zusätzliche Schritte eingefügt werden können, ohne bestehende Logik zu verändern. Jede Regel gibt einen Konfidenzwert zurück. Die Regel mit der höchsten Konfidenz gewinnt. Bei Gleichstand wird die Regel mit der höheren Priorität (früherer Schritt) bevorzugt.

---

## 5. Datenbankvorab-Erstellung

Sobald der Nutzer den Konfigurationsdialog abschließt und bestätigt, wird die SQLite-Datenbankdatei für diesen Ordner angelegt. Die vollständige Tabellenstruktur (alle Tabellen, alle Spalten) wird dabei erzeugt. Befüllt werden in diesem Schritt ausschließlich:

- **`metadata`-Tabelle:** Dateiname, UTC-Startzeit und lat/lon pro File
- **Session-Konfigurationstabelle** (o.ä.): die gewählte Zeitquelle, der verwendete Offset, die lat/lon-Position

Alle anderen Tabellen (Erkennungen, Vektoren etc.) bleiben leer und werden durch den Scouting Flight befüllt.

---

## 6. Freigabe für den Scouting Flight

Ein Ordner ist für den Scouting Job nur dann auswählbar, wenn:
- lat/lon gesetzt ist
- für jedes File im Ordner eine UTC-Startzeit in der DB hinterlegt ist
- die DB-Datei existiert

Im UI ist der Auswahl-Button für nicht-freigegebene Ordner deaktiviert (mit erklärendem Tooltip).

Bei **rekursiver Übernahme** in die Jobliste (ein Elternordner mit mehreren Unterordnern) werden nur die Unterordner berücksichtigt, die die obigen Bedingungen vollständig erfüllen. Unvollständige Ordner werden übersprungen und in einer Zusammenfassung aufgelistet.

---

## Offene Fragen (Sammlung)

1. Wie gehen wir mit stark streuenden GUANO-GPS-Koordinaten um (Gerät bewegt sich)? Warnung? Außerhalb des Anwendungsfalls?
2. Sollen bekannte Geräte-Dateinamenformate (AudioMoth etc.) als feste Bibliothek gepflegt werden, oder rein adaptives Scoring ohne Whitelist?
3. Was passiert, wenn ein File keinerlei auswertbaren Zeitstempel hat – auch keinen Dateisystem-Zeitstempel? Überspringen mit Warnung? Import blockieren?
4. Gibt es eine Möglichkeit, die Konfiguration eines bereits konfigurierten Ordners nachträglich zu editieren (z.B. Zeitoffset korrigieren), ohne die gesamte DB neu anlegen zu müssen?
