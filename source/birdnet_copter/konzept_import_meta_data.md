# Konzept: Initialisierung einer Datenbank für den Import neuer Audiodaten in birdnet-copter – Konfiguration und Metadaten

---

## 1. Nutzungs-Grundprinzip von birdnet-copter

1.1 Grundsätze des Design

Birdnet-copter organisiert die Erkennungen in Audiofiles nach dem Prinzip

> **Ein Fileordner = ein Aufnahmegerät = ein Ort (Punkt im GPS-Koordinatensystem) = ein zugehöriges Datenbank-File**

sowie

> **Mehrere Ordner = mehrere Einzeldatenbanken = eine globale Auswertung**

sodass

* Aus der Regel "ein Fileordner = ein Aufnahmegerät" geht hervor, dass die Audiofiles eines Ordners sich zeitlich nicht überschneiden sollten, wenn die Informationen in der Datenbank eindeutig sein sollen.
* Aus der Regel "ein Fileordner = ein Ort (Punkt im GPS-Koordinatensystem)" geht hervor, dass die Audioaufnahmen zumindest für jeden Aufnahmestandort in separate Ordner einsortiert sein sollten, wenn die Möglichkeit der Ortsangabe in der Anwendung genutzt werden soll.
* Die Regel "mehrere Ordner = mehrere Einzeldatenbanken = eine globale Auswertung" beschreibt die typische Nutzungsart, mehrere Ordner und damit Einzeldatenbank für eine gemeinsame Auswertung gleichzeitig zu laden.

*Implementierungsauftrag:* Diese Darstellung der Nutzung ist auf der ersten Seite der Anwendung (im Moment der Hangar) als erster Hilfetext zu implementieren. Ebenso gehört das in das Readme des Git-Projekts. In wie weit wir das dann auf der in diesem Konzept beschriebenen Seite nochmal wiederholen, muss im Zusammenhang mit dem gesamtenm Hilftext dieser Seite noch festgelegt werden.

### 1.1 Vorbereitung einer Datenbank

Um abzusichern, dass die Datenbank eines Audioordners "richtig" aufgebaut wird, ist eine eigene GUI-Seite erforderlich, die zur Initialisierung der Datenbank verwendet wird. Sie folgt in der Reihenfolge der Hangar-Seite. Ganz oben befindet sich die Auswahl eines Ordners. In ihm muss sich mindestens ein Audiofile (unabhängig von der Dateiart) befinden (das ist wichtig für die automatischen Vorschläge, die später beschrieben werden). Es dürfen sich beliebig andere Dateien in dem Ordner befinden.

---



*Implementierung:*

Jedoch:

* Wenn bereits eine Datenbank vorhanden ist, handelt es sich auf dieser Konfigurationsseite um ein "edit" der Datenbank.
* Existiert keine Datenbank, handelt es sich um eine "create".

Diese beiden Zustände sollen als "Mode" für die Arbeit auf dieser Seite bezeichnet werden.

Damit Seitenwechsel möglich sind, soll der State in app_state gespeichert sein.

---



Das Besondere: Der hier ausgewählte Ordner (nur ein Ordner ist möglich) hat nichts mit den Daten auf den Folgeseiten der Aplikation zu tun. Er ist nur für die auf dieser Seite zu tätigenden Dinge da. Das gilt auch für die Datenbank in diesem Ordner, wenn eine solche Datenbank existiert. - Alle Einstellungen auf dieser Seite beziehen sich immer nur auf dem oben auf der Seite gewählten Ordner (s. 2. Kapitel).

*Implementierungsauftrag:* Diese Seite ist als Seite "db-file-prep.py" zu erstellen und nach hangar einzuordnen. Als Seitensymbol ist ein Datenbank-Icon zu wählen. Wenn es gibt: EIn Datenbanksymbol mit einem Bleistift für "editing".

Ziel der Seite

Es soll 2 Pflichtinformationen für den Ordner festgelegt und in die Datenbank eingertagen werden (DB ertstellen, wenn noch nicht existent):

- **lat/lon** – eine einzige geographische Position für alle Files des Ordners (WGS84)
- **UTC-Startzeiten-Methode** – eine Methode gewählt werden, die den Audiofiles beim scouting_flight die UTC-Startzeit des Files entlockt

Erst wenn beide Konfigurationen vom Nutzer bestätigt sind, wird die SQLite-Datenbankdatei angelegt (mit vollständiger Tabellenstruktur, aber zunächst nur mit diesen Kerndaten befüllt). Erst dann ist der Ordner für den Scouting Flight freigegeben.

*Implementierung:* Die Bedingung "Erst dann ist der Ordner für den Scouting Flight freigegeben." ist dort noch zu tätigen.

Dabei gilt:

* lat/lon darf leer bleiben (wie das markiert wird, ist noch festzulegen). Das bedeutet: Keine Positionsangaben für alle Files vorhanden. Eine Konfiguration für einzelne Files oder unterschiedliche Konfigurationen für unterschiedliche Files eines Ordners sind nicht möglich. Wenn bereits Erkennungen stattgefunden haben, kann lat/lon nachträglich mit einem Wert initialisiert werden, er darf jedoch, ist er initialisiert, nicht mehr geändert werden, wenn mindestens eine Erkennung in der Datenbank enthalten ist.
* UTC-Startzeiten-Methode: Es muss exakt eine Methode gewählt werden. Wenn bereits Erkennungen stattgefunden haben, darf diese Methode nicht mehr geändert werden.

Das heißt für Abänderungen des Initialisierungswertes müssen vorher sämtliche Erkennungen der Datenbank gelöscht werden. Die Erkennung muss danach wiederholt werden.

*Implementierung:* Diese Funktionalität ist in Back- und Frontend zu implementieren. Weiterhin soll ein Button vorhanden sein, die Erkennungen in der Datenbank vollständig zu löschen, um eine Neuaufbau zu gestatten. Zu beachten ist, dass es sich hier um dedizierte Zellen in der Datenbank handelt und nicht um Einträge in den im nächsten Kapitel beschriebenen Key-Value-Paare.

### 1.3 Nutzer-Metadaten einer Datenbank

* Es existiert bereits ein Notiz-Feld für beliebigen Text. Dieses Feld wird auch bei der Exploration-Seite angezeigt, wenn dort nur eine Datenbank ausgewählt ist. Dieses Feld ist zur freien Verwendung durch den Nutzer und kann jederzeit editiert werden. Es wird als leere Zeichenkette angelegt (kein Byte-Blob), wenn die Datenbank erstellt wird.

Neu:

Es können zusätzlich (im Prinzip) beliebig viele Key-Value-Paare als Python Dictionary in Form eines Byte-Blobs in einer Zelle der Datenbank gespeicht werden. Gespeichert wird der gepickelte Bytestream dieses Dictionaries als Byte-Blob. Ein Einzelzugriff auf die Werte auf Datenbankebene ist somit nicht möglich.

*Implementierung:*

* Während das "Notizfeld" eine eigene Zelle in der Datenbank ist, die beliebige Zeichen beliebiger Länge speichern kann (beliebiger Zeichensatz!), ist
* für den Byte-Blob der Key-Value-Paare eine weitere Zelle zu erstellen. Beliebige Größe für Binärdaten.
* der Zugriff auf dieses Feld soll in db_query.py implementiert werden: Beim Schreiben wird das übergebene Dictionary gepickelt dort eingetragen (ggfs. Blob-Größe anpassen). Beim Lesen werden die de-pickled Daten als Python-Dictionary zurück gegeben.

---

## 2. Seite "Database Configuration" (db-file-prep.py)

Die Prinzipien aus Kapitel 1 werden hier in die GUI übernommen. Die konkrete GUI-Konfiguration soll in diesem Kapitel beschrieben werden.

Wie auf allen anderen Seiten sind alle logische Einheiten in eigenen Boxen mit einer eigenen Überschrift und einem eigenen Symbol einzuordnen.

### 2.1 Ausgewählter Ordner

**Wichtige Anpassung zur Vermeidung von Missverständnissen!**

Im Header der gesamten Applikation werden auch schon Datenbank-Auswahl-Informationen angezeigt.

* Die erste Zeile zeigt die Wurzel an, innerhalb der gearbeitet wird. Das ist auch auf der Seite "Database Configuration" exakt.
* In der zweiten Zeile werden die in exploration_area ausgewählten Datenbank(en) angezeigt. -> Das ist auf dieser Seite missverständlich.

Es ist essentiell zu wissen, für welchen Ordner man auf "Database Configuration" gerade Einstellungen oder Daten ändert. Deshalb ist die zweite Zeile im Header zusätzlich in folgender Form zu "animieren":

Immer dann, wenn wir uns auf der Seite "Database Configuration" befinden, wechselt die zweite Headerzeile ihre Anzeigefunktion:

* Die Ausschrift wird in fetter (sehr) dunkel-roter Schrift angezeigt.
* wenn kein Ordner (ob mit oder ohne enthaltene Datenbank) gewählt ist, wird angezeigt "Select a folder (DB) to configure / edit!"
* Sobald ein Ordner, wie unter 2.2 beschrieben, ausgewählt ist, wird er angezeigt. Bei Wechsel des Ordners ist auch die Anzeige anzupassen.

*Implementierung:* Exakt so, wie in diesem Kapitel beschrieben.

### 2.2 Ordner / Datenbank-Wahl

Der erste Block ist ein Tree-Element ausgehend von der im Hangar definierten Wurzel. Der Tree ist aufklappbar zugestalten. Wir sollten das mit dem vorhandenen Tree in ./gui-elements kombinieren (db_folder_tree.py) und die unterschiedliche Funktionsweise mit Optionen in der API gestalten.

Im Tree soll unterhalb der Wurzel die gesamte (!) Dateistruktur durchforstbar sein, jedoch:

* Ordner, die keine Audiofiles enthalten, sind ausgegraut vorhanden und könne nicht gewählt werden, sie können aber für die weitere Suche aufgeklappt werden, wenn sie Unterordner enthalten
* Ordner, die Audiofiles enthalten, dürfen ausgewählt werden
* Bei Ordnern, die schon eine Datenbank enthalten, wird hinter dem Ordner ein Datenbanksymbol eingeblendet. (Im Sinne der Wiederverwendung kann das DB-Symbol auch farbig animiert werden, wie in exploration_area.)
* Im Gegensatz zur Treedarstellung in exploration-area kann nur ein Ordner ausgewählt werden. Bei der Auswahl eines Ordners werden zuvor ausgewählte Ordner wieder deselektiert.

Das Auswählen sollte, wie in exploration_area über ein Kästchen erfolgen. Damit können wir das dort verwendete GUI-Element durch Erweiterung der Optionen wiederverwenden, ohne zu sehr abzuwandeln.

Mit der Auswahl, wird der Ordner sofort übernommen un d die davon abhängigen GUI-Elemente der Sete werden aktualisiert.

*Implementierung:* Exakt so, wie im Kapitel beschrieben.

### 2.3 Metadaten-Ansicht

Das ist der zweite Block. Der Inhalt wird dynamisch zum gewählten Ordner generiert: Er zeigt sämtlich erreichbares Metawissen aus dem Ordner und seinen Files an.

Dieser Block wird sehr umfangreich und möglicherweise auch in Zukunft noch erweitert, um zusätzliches Metawissen aus den Files zu generieren. Der Block besteht aus einer fortlaufenden Tabelle

'SPALTEN' definieren

#### 2.3.1 Erstellung der Tabelle

Bevor wir uns mit der Verwendung der Daten beschäftigen können, müssen wir sie extrahieren. Das wird einer der komplexesten Funktionen in der Applikation.

*Implementierung:* Die Methode/Klasse, diese Daten aus den Files des Ordners zu gewinnen, und diese dann als Referenz für die Datenbank zu verwenden, soll wegen ihrer Komplexität in einem eigenen Python-Modul angelegt werden.

Die Methode soll iterativ über die im Ordner vorhandenen Dateien arbeiten. Die Auswertemethoden können adaptiv auf bereits bekannte Dateiformate angewendet werden, um Daten explizit zuzuordnen.

**Analyse der Audiodaten**

* über sinnvolle Python-Tools werden die Metainformationen sämtlicher Audiodaten gesammelt
* Hierbei wird ein Dictionary mit einem key und einem value-Tuple aus 2 Elementen verwendet, welches auch für andere Dateien in der gleichen Form benutzt werden soll:

Es ergibt sich somit ein

**Meta-Data-Dictionary**

key: bezeichnet das Metadatum

value: (

* "files" – ist eine Liste der Files, die dieses Meta-Datum enthalten
* "values" - ist synchron zu "files" die Liste an values aus diesen Files zu diesem Meta-Datum

)

Implementierung: Wir starten hier erstmal nur mit Audio-Files, für die es solche Tools zum Auslesen der Metainformationen gibt.

**Dateisystem-Metadaten**

Auf die gleiche Weise erstellen wir auch die Metadaten, die das Filesystem zu den Files bietet. Also sowas wie Erstellzeitpunkt, Zeitpunkt letzte Änderung, (...?). Auch diese Daten kommen in das Meta-Data-Dictionary als eigene Keys.

Nachfolgend wir aus den Daten eine Tabelle erstellt, mit deren Hilfe wir später referenzieren können, welche Werte in unsere Datenabnk übernommen werden sollen. Die Tabelle besteht deshalb aus 4 Spalten:

* Spalte 1: Ein Index pro Zeile.
* Spalte 2: Ein Kasten zum anhaken, dass dieses Paar aus key und value in die Metadaten übernommen werden soll. Dabei ist zu berücksichtigen, dass es mehrere key-value-Paare mit dem gleichen key gibt und immer nur ein Value pro key ausgewählt werden kann!
* Spalte 3: key
* Spalte 4: value
* Spalte 5: Liste der Files, die dieses key-Value-Paar enthalten

Die Daten aus dem oben beschriebenen Meta-Data-Dictionary werden hier also aufbereitet präsentiert: Zum jedem Key wird pro unterschiedlichem value eine Zeile erstellt, in der dann alle filenamen eingetragen werden, die diesen Wert zum zugehörigen key besitzen.

Die Spalte 1 wird uns dazu dienen, die lat/lon-Information sowie das Metadatum, dass für die Audio-Startzeit verantwortlich ist, zu übernehmen.

Die Spalte 2 wird uns dazu dienen, die Metadaten in Form der key-Value-Paare in die Datenbank zu übernehmen.

*Implementierung:* Diese Aufgabe unterteilt sich in zwei Aufgaben grundsätzlich anderen Typus:

* Die erste Aufgabe ist, die Daten zusammenzutragen. Das kann für unterschiedlichste Dateitypen sehr vielfältige Möfglichkeiten geben und beliebig komplex werden. Dieser Teil ist in ein eigenes Modul auszugliedern.
* Der zweite Teil ist dann (nur) die Darstellung der gesammelten Informatione in einer Tabelle und der Funktionalität der Selektion. Bei der Selektion gibt es die Besonderheit, dass zwar alle Selektionsfelder in der ersten Spalte quasi auf einer Ebene stehe, jedoch immer die Selektionsfelder, die in den Zeilen mit gleichem key liegen, unter sich quasi als "radio-buttons" wirken und innerrhalb der Gruppe gleicher keys nur eine Zeile auswählbar ist bzw. bei Auswahl in einer anderen Zeile die bisherige Selektion deselektiert wird. Diese Funktion ist funktional abzubilden, nicht visuell in der Anordnung/Art der Eingabeelemente.


### 2.4 Lat/Lon-Datum und Kartenansicht (GPS)

Grundsätzlich werden für die Übernahme der Ortskoordinaten lat/lon 4 Möglichkeiten angeboten:

* "leer lassen" – Durch eine besondere Markierung (die noch fetgelegt werden muss) werden beide Werte ungültig gemacht und symbolisieren: "Kein Ortskoordinaten bekannt." (das ist der default hier auf dieser Seite)
* Übernahme aus den in Kapitel 2.3 beschriebenen Metainformationen ohne Karte. Es werden die Indices (Zeilennummern) aus der Tabelle angegeben. Wird nur eine Zeilennummer durch den Nutzer ausgewählt, startet ein adaptiver Algorithmus, der aus einem Eintrag beide Koordinaten extrahiert. Das ist für den Fall, dass es nur eine Metainformation für beide Werte gibt.

  –> Gleichzeitig werden alle als lat/lon interpretierbare Daten in der Tabelle in die Karte übernommen, um sie statt dessen dort auszuwählen. Auch hier müssen wir adaptiv arbeiten und probieren, ob wir die Daten entschlüsseln können oder nicht. Ebenfalls adaptiv entscheiden wir, diese Daten nicht einzutragen, wenn sie zu stark streuen und nicht eng in einer Region liegen. Denn sonst benötigen wir Weltkartenauflösung, um sie anzuzeigen, was nicht im Sinne des Nutzers sein kann.
* Vorgabe der Koordinaten über eine Karte
* Vorgabe per Handeingabe der beiden Werte

#### 2.4.1 Kartenansicht

Eine eingebettete Karte (OpenStreetMap, z.B. via `folium` oder einer NiceGUI-kompatiblen Kartenlösung) wird angezeigt. Sie dient gleichzeitig zur Eingabe und zur Kontrolle der GPS-Position.

- Wenn GPS-Koordinaten aus den Metadaten einzelner Files extrahiert wurden (z.B. aus dem GUANO-Chunk von AudioMoth), werden alle gefundenen Positionen als Punkte auf der Karte eingeblendet. Der Nutzer erkennt sofort Ausreißer (z.B. Labor-Initialisierung des Geräts an einem anderen Ort) und kann "seinen" Ort vorgeben, der dann übernommen wird.
- Der Nutzer kann somit per Klick auf die Karte eine einzige endgültige Position für die gesamte DB festlegen. Vorhandene GUANO-Koordinaten werden als Vorschlag verwendet (z.B. Mittelwert oder häufigster Cluster), können aber überschrieben werden.
- Die final gewählte lat/lon-Position wird prominent angezeigt. Also wenn die Datenbank bereits einen lat/lon-Wert hat, ist das dieser.

---

nachfolgend weitere Bearbeitung erforderlich

---



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
