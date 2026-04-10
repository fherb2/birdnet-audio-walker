# Konzept: Initialisierung einer Datenbank für den Import neuer Audiodaten in birdnet-copter – Konfiguration und Metadaten

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

* Wenn bereits eine Datenbank vorhanden ist, handelt es sich auf dieser Konfigurationsseite automatisch um ein "edit" der Datenbank.
* Existiert keine Datenbank, handelt es sich automatisch um eine "create".

Diese beiden Zustände sollen als "Mode" für die Arbeit auf dieser Seite bezeichnet werden.

Damit Seitenwechsel möglich sind, soll der State in app_state gespeichert sein.

**Das Besondere dabei:** Der hier ausgewählte Ordner (nur ein Ordner ist möglich) hat nichts mit den Daten auf den Folgeseiten der Aplikation zu tun. Er ist nur für die auf dieser Seite zu tätigenden Dinge da. Das gilt auch für die Datenbank in diesem Ordner, wenn eine solche Datenbank existiert. - Alle Einstellungen auf dieser Seite beziehen sich immer nur auf dem oben auf der Seite gewählten Ordner (s. 2. Kapitel). Das heißt, der Zustand der Daten dieser Seite existieren in app_state neben dem Zustand der anderen Seiten.

*Implementierungsauftrag:* Diese Seite ist als Seite "db-file-prep.py" zu erstellen und nach hangar einzuordnen. Als Seitensymbol ist ein Datenbank-Icon zu wählen. Wenn es gibt: EIn Datenbanksymbol mit einem Bleistift für "editing".

### 1.2 Ziel der Seite (Vorgriff auf die Beschreibung in Punkt 2)

#### 1.2.1 Pflichtinformationen

Es soll 2 Pflichtinformationen für den Ordner festgelegt und in die Datenbank eingertagen werden (DB ertstellen, wenn noch nicht existent):

- **lat/lon** – eine einzige geographische Position für alle Files des Ordners (WGS84)
- **UTC-Startzeiten-Methode** – eine Methode gewählt werden, die den Audiofiles beim scouting_flight die UTC-Startzeit des Files entlockt

Erst wenn beide Konfigurationen vom Nutzer bestätigt sind, wird die SQLite-Datenbankdatei angelegt (mit vollständiger Tabellenstruktur, aber zunächst nur mit diesen Kerndaten befüllt). Erst dann ist der Ordner für den Scouting Flight freigegeben.

#### 1.2.2 Wahlfreie Metainformationen

Weiterhin sollen Metadaten der Datenbank hinzugefügt werden, die jederzeit angepasst werden können und wo die Seite anbietet, diese aus geparsten Metadaten der enthaltenden dateien zu übernehmen. Abgesehen vom speziellen Feld der Notizen, dass separat editierbar und speicherbar ist, sind das Key-Value-Paare, die in einem Dictionary als pickled Byste Objekt gespeichert werden und die entweder aus einem File-Parsing stammen oder explizit vom Nutzer zu beliebiger Zeit hinzugefügt und geändert werden können.

#### 1.2.3 Besonderheit der Pflichtinformationen

*Implementierung:* Die Bedingung "Erst dann ist der Ordner für den Scouting Flight freigegeben." ist dort auf den entsprechenden Seiten und ggfs. im Backend noch zu berücksichtigen.

Dabei gilt:

* lat/lon wird hier mit 90°/0° initialisiert. Das bedeutet: Keine Positionsangaben für alle Files initialisiert. Datenbanken ohne eine weitere Konfiguration des Standorts sind so trotzdem auf Kartendarstellungen sichtbar: Exakt am Nordpol.
  Eine Konfiguration für einzelne Files oder unterschiedliche Konfigurationen für unterschiedliche Files eines Ordners sind nicht möglich. Wenn bereits Erkennungen stattgefunden haben, kann lat/lon nachträglich mit einem Wert initialisiert werden, er darf jedoch, ist er initialisiert (also von 90°/0° verschieden), nicht mehr geändert werden, wenn mindestens eine Erkennung in der Datenbank enthalten ist. (Ohne Erkennungen ist eine Korrektur noch möglich.) Wenn bereits Erkennungen stattgefunden haben, darf dieses Parameter-Tupel nicht mehr geändert werden.
* UTC-Startzeiten-Methode: Es muss exakt eine Methode gewählt werden. Wenn bereits Erkennungen stattgefunden haben, darf diese Methode nicht mehr geändert werden.

Das heißt für Abänderungen des Initialisierungswertes des Standortes unbd der UTC-Startzeit-Methode müssen vorher sämtliche Erkennungen der Datenbank gelöscht werden. Die Erkennung muss danach wiederholt werden. Das ist für spätere Erweiterung der Erkennung wichtig, bei der nur lokale Arten zurückgegeben werden und der Standort sozusagen als zusätzlicher Filter dient.

*Implementierung:* Diese Funktionalität ist in Back- und Frontend zu implementieren. Weiterhin soll ein Button vorhanden sein, die Erkennungen in der Datenbank vollständig zu löschen, um eine Neuaufbau aus den Audiofiles des Ordner zu gestatten. Zu beachten ist, dass es sich hier um dedizierte Zellen in der Datenbank handelt und nicht um Einträge in den im nächsten Kapitel beschriebenen Key-Value-Paaren.

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

Die Prinzipien aus Kapitel 1 werden hier in die GUI übernommen. Das heißt, die im ersten Kapitel bereits genannten Bedienvorgänge und Ansichten werden auf dieser Seite implementiert. Die konkrete GUI-Konfiguration soll in diesem Kapitel beschrieben werden.

Wie auf allen anderen Seiten sind alle logische Einheiten in eigenen Boxen mit einer eigenen Überschrift und einem eigenen Symbol einzuordnen.

### 2.1 Ausgewählter Ordner

**Wichtige Anpassung zur Vermeidung von Missverständnissen!**

Im Header der gesamten Applikation werden auch schon Datenbank-Auswahl-Informationen angezeigt.

* Die erste Zeile zeigt die Wurzel an, innerhalb der gearbeitet wird. Das ist auch auf der Seite "Database Configuration" exakt.
* In der zweiten Zeile werden die in exploration_area ausgewählten Datenbank(en) angezeigt. -> Das ist auf dieser Seite hier missverständlich.

Es ist essentiell zu wissen, für welchen Ordner man auf "Database Configuration" gerade Einstellungen oder Daten ändert. **Deshalb** ist die zweite Zeile im Header zusätzlich in folgender Form zu "animieren":

Immer dann, wenn wir uns auf der Seite "Database Configuration" befinden, wechselt die zweite Headerzeile ihre Anzeigefunktion:

* Die Ausschrift wird in fetter (sehr) dunkel-roter Schrift angezeigt.
* wenn kein Ordner (ob mit oder ohne enthaltene Datenbank) gewählt ist, wird angezeigt "Select a folder (DB) to configure / edit!"
* Sobald ein Ordner, wie unter 2.2 beschrieben, ausgewählt ist, wird er angezeigt. Bei Wechsel des Ordners ist auch die Anzeige anzupassen.
* Da diese Seite eigene Einträge in app_state bekommt, können die Einstellungen und Anzeigewerte also sofrt wieder hergestellt werden, wenn auf diese Seite gewechselt wird.

*Implementierung:* Exakt so, wie in diesem Kapitel beschrieben.

### 2.2 Ordner / Datenbank-Wahl

Der erste Block ist ein Tree-Element ausgehend von der im Hangar definierten Wurzel. Der Tree ist aufklappbar zu gestalten. Wir sollten das mit dem vorhandenen Tree in ./gui-elements kombinieren (db_folder_tree.py) und die unterschiedliche Funktionsweise mit Optionen in der API gestalten.

Im Tree soll unterhalb der Wurzel die gesamte (!) Dateistruktur durchforstbar sein, jedoch:

* Ordner, die keine Audiofiles enthalten, sind ausgegraut vorhanden und könne nicht gewählt werden, sie können aber für die weitere Suche aufgeklappt werden, wenn sie Unterordner enthalten
* Ordner, die Audiofiles enthalten, dürfen ausgewählt werden
* Bei Ordnern, die schon eine Datenbank enthalten, wird hinter dem Ordner ein Datenbanksymbol eingeblendet. (Im Sinne der Wiederverwendung kann das DB-Symbol auch farbig animiert werden, wie in exploration_area.)
* Im Gegensatz zur Treedarstellung in exploration-area kann nur ein Ordner ausgewählt werden. Bei der Auswahl eines Ordners werden zuvor ausgewählte Ordner wieder deselektiert.

Das Auswählen sollte, wie in exploration_area über ein Kästchen erfolgen. Damit können wir das dort verwendete GUI-Element durch Erweiterung der Optionen wiederverwenden, ohne zu sehr abzuwandeln.

Mit der Auswahl, wird der Ordner sofort übernommen und die davon abhängigen GUI-Elemente der Seite werden aktualisiert.

*Implementierung:* Exakt so, wie im Kapitel beschrieben.

### 2.3 Metadaten-Ansicht

Das ist der zweite Block. Der Inhalt wird dynamisch zum gewählten Ordner generiert: Er zeigt sämtlich erreichbares Metawissen aus dem Ordner und seinen Files an.

Dieser Block wird sehr umfangreich und möglicherweise auch in Zukunft noch erweitert, um zusätzliches Metawissen aus den Files zu generieren. Der Block besteht aus einer fortlaufenden Tabelle. Sie wird im einzelnen in den nachfolgenden Abschnitten beschrieben.

#### 2.3.1 Erstellung der Tabelle

Bevor wir uns mit der Verwendung der Daten beschäftigen können, müssen wir die Daten extrahieren, die wir in der Tabelle darstellen wollen. Das wird einer der komplexesten Funktionen in der Applikation, denn die Aufgabe ist, alle Files des Ordners zu durchsuchen (außer der eventuell schon vorhandenen Datenbank) und Metainformation daraus zu sammeln, die man nachfolgend zur Übernahme in das Metawissen der Datenbank selektieren kann.

*Implementierung:* Die Methode/Klasse, diese Daten aus den Files des Ordners zu gewinnen, und diese dann als Referenz für die Datenbank zu verwenden, soll wegen ihrer Komplexität in einem eigenen Python-Modul angelegt werden.

Die Methode soll iterativ über die im Ordner vorhandenen Dateien arbeiten. Die Auswertemethoden können adaptiv auf bereits bekannte Dateiformate angewendet werden, um Daten explizit zuzuordnen.

Zuerst implementieren wir nur die erfassung von Metadaten aus den Audiodaten im Ordner und aus einer eventuell vorhandenen AudioMoth-Konfigurationsdatei, die mit von der SD-Karte des Gerätes herunter kopiert wurde.

Erforderlich ist in diesem Modul, die vorhandenen Files mit Erkennungsmechanismen ausreiochend gut zu klassifizieren, sodass wir dann geeignete Parser darauf ansetzen können.

Dateien, aus denen bisher keine Daten gewonnen werden können (keine Klassifizierung angteschlagen; kein Parser vorhanden oder Parsing wegen Fehler abgebrochen), werden im Logging als Info aufgelistet.

**Analyse der Audiodaten (und aller anderen Quellfiles für Metainformationen)**

* über sinnvolle Python-Tools werden die Metainformationen sämtlicher (Audio)dateien gesammelt
* Hierbei wird mittels Parser ein Dictionary mit einem key und einem value-Tuple aus 2 Elementen gefüllt, welches auch für andere Dateien in der gleichen Form benutzt werden soll:

Es ergibt sich somit ein

**Meta-Data-Dictionary**

key: bezeichnet das Metadatum

value: tuple(

* "files" – ist eine Liste der Files, die dieses Meta-Datum enthalten
* "values" - ist synchron zu "files" die Liste an values aus diesen Files zu diesem Meta-Datum

)

Implementierung: Wir starten hier erstmal nur mit Audio-Files, für die es solche Tools zum Auslesen der Metainformationen gibt. Den Parserteil, der die Daten in das Dictionary füllt müssen wir natürlich für jede File-Klasse selbst schreiben.

**Dateisystem-Metadaten**

Auf die gleiche Weise erstellen wir auch die Metadaten, die das Filesystem zu den Files bietet. Also sowas wie Erstellzeitpunkt, Zeitpunkt letzte Änderung, (...?). Auch diese Daten kommen in das Meta-Data-Dictionary als eigene Keys.

Nachfolgend wird aus den Daten die oben schon genannte Tabelle erstellt, mit deren Hilfe wir später referenzieren können, welche Werte in unsere Datenabnk übernommen werden sollen. Die Tabelle besteht deshalb aus 4 Spalten:

* Spalte 1: Ein Kasten zum anhaken, dass dieses Paar aus key und value in die Metadaten übernommen werden soll. Dabei ist zu berücksichtigen, dass es mehrere key-value-Paare mit dem gleichen key gibt und hier aber immer nur ein Value von allen Values pro key ausgewählt werden kann!
* Spalte 2: key (wie gesagt: kann in mehreren fortlaufenden Zeilen identisch sein)
* Spalte 3: value (kann mit der Hand editiert werden, nachdem die Tabelle durch die Parser gefüllt wurde)
* Spalte 4: Liste der Files, die konkret dieses key-Value-Paar enthalten

Die Daten aus dem oben beschriebenen Meta-Data-Dictionary werden hier also aufbereitet präsentiert: Zum jedem Key wird pro unterschiedlichem value eine Zeile erstellt, in der dann auch alle filenamen eingetragen werden, die diesen Wert zum zugehörigen key besitzen.

Die Spalte 1 wird uns dazu dienen, die Metadaten in Form der key-Value-Paare in die Datenbank zu übernehmen.

Weiterhin:

1. Wenn die Tabelle erzeugt wurde, sind die Einträge in Spalte 3 (value) mit Maus und Tastatur editierbar. Sobald sie editiert wurden, wird der Eintrag in Spalte 4 gelöscht, denn diese Wert steht so ja nicht mehr exakt in den genannten Files. Der letztlich dort eingetragene Wert wird später übernommen, wenn die Metadaten der DB über/geschrieben werden. Der geparste Wert geht mit dem editieren verloren. Auf diese Weise kann man den Inhalt eines Wertes z.B. in der Formatierung u.ä. anpassen, bevor er in die DB übernommen wird.
2. Über einen Button können weitere "leere" key-value-Paare am Ende der Tabelle erzeugt werden, die mit der Hand ausgefüllt und zur Übernahme in die Datenbank auswählbar sind (Kästchen in Spalte 1). Die Spalte 4 bleibt dabei leer. Die Besonderheit hier: Es wird sofort geprüft, ob ein key doppelt vergeben ist. Das ist bei Handeingaben unzulässig (kein Verhalten wie bei den geparsten Daten, wo dann der Haken als Radio-Button, interpretiert wird).
3. Die Tabelle wird nur einmal erzeugt. Dazu gibt es ganz oben einen Button "Read Metadata and create table new". In dem Fall wird die Tabelle komplett neu erzeugt. Handeinträge sind weg. Das bedeutet aber auch:
4. Die Tabelle ist Teilo des app_state: Dort bleibt sie erhalten, auch wenn man zwischendurch die Seiten wechselt. Dann wird sie aus dem State neu erzeugt, nicht durch parsing der Files.

*Implementierung:* Diese Aufgabe unterteilt sich in zwei Aufgaben grundsätzlich anderen Typus:

* Die erste Aufgabe ist, die Daten zusammenzutragen. Es kann für unterschiedlichste Dateitypen sehr vielfältige Möglichkeiten geben und beliebig komplex werden. Dieser File-Classification- und File-Parsing-Teil ist in ein eigenes Modul auszugliedern.
* Der zweite Teil ist dann die Darstellung der gesammelten Informatione in einer Tabelle und der Funktionalität der Selektion zur Übernahme in die DB. Bei der Selektion gibt es die Besonderheit, dass zwar alle Selektionsfelder in der ersten Spalte quasi auf einer Ebene stehen, jedoch immer die Selektionsfelder, die in den Zeilen mit gleichem key liegen, unter sich quasi als "radio-buttons" wirken müssen und innerhalb der Gruppe gleicher keys nur eine Zeile auswählbar ist bzw. bei Auswahl in einer anderen Zeile die bisherige Selektion deselektiert wird. Diese Funktion ist funktional abzubilden, nicht visuell in der Anordnung/Art der Eingabeelemente.

### 2.4 Lat/Lon-Datum und Kartenansicht (GPS)

Grundsätzlich werden für die Übernahme der Ortskoordinaten lat/lon 4 Möglichkeiten angeboten:

* "unverändert lassen" – Für den Fall, dass die Ortsposition unwichtig ist, bleibt der Doppelwert auf der Standardeinstellung: Nordpol (das ist der default hier auf dieser Seite)
* Übernahme aus den in Kapitel 2.3 beschriebenen Metainformationen ohne Karte. Es werden die Indices (Zeilennummern) aus der Tabelle angegeben. Wird nur eine Zeilennummer durch den Nutzer ausgewählt, startet ein adaptiver Algorithmus, der aus einem Eintrag beide Koordinaten extrahiert. Das ist für den Fall, dass es nur eine Metainformation für beide Werte gibt.
* Gleichzeitig werden alle als lat/lon interpretierbare Daten in der Tabelle in die Karte übernommen, um sie statt dessen dort auszuwählen. Auch hier müssen wir adaptiv arbeiten und probieren, ob wir die Daten entschlüsseln können oder nicht. Damit ergibt sich dann die Möglichkeit der Vorgabe der Koordinaten über die Karte aus diesen Markierungen.
* Auswahl eines beliebigen Punktes auf der Karte
* Vorgabe per Handeingabe der beiden Werte

#### 2.4.1 Kartenansicht

Eine eingebettete Karte (OpenStreetMap, z.B. via `folium` oder einer NiceGUI-kompatiblen Kartenlösung) wird angezeigt. Sie dient gleichzeitig zur Eingabe (s. vorheriger Abschnitt) und zur Kontrolle der GPS-Position.

- Wenn GPS-Koordinaten aus den Metadaten einzelner Files extrahiert wurden (z.B. aus dem GUANO-Chunk von AudioMoth), werden alle gefundenen Positionen als Punkte auf der Karte eingeblendet. Der Nutzer erkennt sofort Ausreißer (z.B. Labor-Initialisierung des Geräts an einem anderen Ort) und kann "seinen" Ort vorgeben, der dann übernommen wird.
- Der Nutzer kann somit per Klick auf die Karte eine einzige endgültige Position für die gesamte DB festlegen. Vorhandene GUANO-Koordinaten werden als Vorschlag verwendet (z.B. Mittelwert oder häufigster Cluster), können aber überschrieben werden.
- Die final gewählte lat/lon-Position wird prominent angezeigt. Also wenn die Datenbank bereits einen lat/lon-Wert hat, ist das dieser.

### 2.5 Metadaten-Übersicht und -Übernahme

#### 2.5.1 Tabelle

Dieser Kasten enthält nun eine Übersicht aller in die Datenbank zu übernehmenden Metadaten. Hier wird angezeigt was übernommen wird. Die Tabelle wird aus den oben selektierten key-Value-Paaren gebildet. Jedoch auch aus bereits in der datenbank vorhandenen key-value-Paaren. Das wird als Tabelle mit 3 Spalten gestaltet:

1. Spalte: Key
2. Spalte: Value (Wenn es sich um key-value-Paar handelt, dass bereits in der Datenbank vorhanden ist, dann kann der value hier editiert werden. Der neue Wert wird übernommen, wenn "selektiert" wird (grünes Symbol). Wenn weder selektiert noch deselektiert (gelbes Symbol) belibt bei der Übernahme der alte Wert bestehen. Aus diesem Grund: Beim Editieren ist der Druck der Enter-Taste auch als "selektieren" zu verarbeiten. Was der Nutzer dann auch am Farbwechsel des Symbols erkennt.)
3. Spalte: ein gründes Symbol, wenn bereits in der Datenbank vorhanden oder als neu hinzuzufügen ausgewählt (siehe gleich); ein gelbes Symbol, wenn in der Datenbank vorhanden, nicht aber in den oben in der ersten Tabelle ausgewählten key-value-Paaren, es aber erhalten bleiben soll, also nicht gelöscht werden soll. Ein rotes Symbol, wenn in der Datenbank vorhanden, jetzt aber zum Löschen markiert wurde

Es gibt hier nun eine Bedienmöglichkeit folgender Art:

* selektieren: Eintrag wird als "neu übernehmen" bzw. ein in der DB vorhandener Eintrag explizit als "erhalten" ausgewählt. Symbol wird grün.
* deselektieren: Eintrag wird nicht ausgewählt und wenn bereits in der Datenbank vorhanden, wird er dann bei Übernahme der Daten dort gelöscht. Wenn in der DB vorhanden: wird das Symbol nun rot. Wenn nicht vorhanden: kein Symbol (Ausgangszustand für nicht vorhandene key-value-Paare)
* Bei dieser Bedienmöglichkeit "unbehandelte" Zeilen bedeuten, dass sie entweder keine Farbmarkierung haben (also auich noch nicht in der DB vorhanden) und nicht neu übernommen werden oder dass sie bereits in der DB vorhanden sind und dort bleiben sollen, wobei sie dann schon beim Eintrag in die Tabelle mit einem gelben Symbol markiert wurden.

Das Symbol in gelb und rot gibt es also nur für key-value-Paare, die schon in der DB stehen. Grün für neu hinzuzufügene oder "explizit" als zu erhalten ausgewählt wurden.

#### 2.5.2 Übernahme-Button

Die entgültige Übernahme der Änderungen in der Datenbank passiert über einen separaten Button "Metadaten mit DB abgleichen" unmittelbar unterhalb der Tabelle.

Wird ein in der Datenbank vorhandener Eintrag nicht "selektiert", bleibt er gelb markiert und er bleibt bei der Übernahme in der DB auch erhalten, wird aber auch nicht überschrieben. Ist er explizit deselektiert worden und in der DB vorhanden (rotes Symbol), wird er nun dort entfernt.

#### 2.5.3 Zeitpunkte der Übernahme in die DB

Diese Metadaten, die in key-value-Paaren vorliegen können in einer vorhandenen DB jederzeit geändert oder ergänzt werden. Die einzigen Werte, bei denen das nur geht, wenn noch keine Erkennungen in der DB enthalten sind, ist der Staqndort (lat/lon) und die Interpretation der Zeit in den Audio-Quelldaten.

#### 2.5.4. Create Funktion für die Tabelle

Die Tabelle bekommt unmittelbar davor einen Button "Recreate Table". Durch diesen Button, aber auch mit jeder Selektion eines anderen Ordners und damit einer anderen potentiellen Datenbank, wird die Tabelle mit allem Parsing für den (neuen) Ordner ausgeführt und neu erstellt.

---

### 2.6 UTC-Startzeiten-Methode

Dieses Kapitel behandelt den User-Dialog, um die UTC-Startzeiten-Methode vorzugeben.

**Teil A: Zeitquellen-Auswahl**

Ein Auswahlfeld (Dropdown) listet alle im Ordner verfügbaren Zeitquellen auf, die grundsätzlich als Startzeit-Kandidat geeignet sind. Die Liste wird automatisch befüllt (parallel zum Parsing aus Kapitel 2.3 bzw. 2.5.4). Der Nutzer wählt nun, welche Quelle als Basis verwendet werden soll. Die adaptive Bewertung liefert einen Vorschlag, welche Quelle am wahrscheinlichsten korrekt ist (markiert als "Empfehlung").

Beispieleinträge im Dropdown:

- „GUANO-Timestamp (UTC erkannt) – **Empfehlung**"
- „Dateiname-Muster `YYYYMMDD_HHMMSS` (UTC angenommen)"
- „Dateisystem-Erstellzeit (Lokalzeit des Rechners)"

**Teil B: Globaler Zeitoffset**

Zusätzlich wird ein Eingabefeld für einen globalen Zeitoffset (Format: `+HH:MM` oder `-HH:MM`, auch Sekunden möglich). Dieser Offset wird bei der Zeitinterpretation der Erkennungen dazu addiert. Typischer Anwendungsfall: systematische bekannte Uhr-Abweichung des Ausnahmegeräts, z.B. durch einen Konfigurationsfehler bei der Initialisierung des Aufnahmegerätes.

**Teil C: Scrollbarer Zeitstempel-Ansichts-Kasten als Ergebnisvorschau**

Hier kann man in Abhängigkeit der Einstelklung der Methode und des Offsets sofort einsehen, wie die Zeiten in den Audiofiles ermitelt werden und ob prüfen, ob das korrekt ist. Verwendet wird eine Tabelle.

Für jedes File drei Spalten in der Tabelle:

- **Links:** Die aus der gewählten Quelle extrahierte Startzeit und Endzeit der Aufnahme, nach Anwendung der Erkennungsmethode und des globalen Offsets. Beschriftet in UTC.
- **Mitte:** Die zugehörige Zeit der Zeitzone laut GPS-Koordinaten. Bei "Nordpol" auch hier UTC. Sonst die übliche Ortszeit, wobei die "politische" Zeit genommen wird, also inklusive Sommerzeit-Umschaltung. Es wird also, wenn Sommerzeit ist, diese Zeit angezeigt. Zwingend wird hinter jeder Zeitangabe deshalb geschrieben, was verwendet wurde. Also im Winter in Mitteleuropa immer MEZ und sobald da Sommerzeit ist, wird diese genommen und MESZ geschrieben.
- **Rechts:** Das File, zu dem die Angaben gehören.

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

## 5. Datenbankvorab-Erstellung

Sobald der Nutzer die Konfigurationsseite abschließt und bestätigt und noich kein DB-File vorhanden ist, wird die SQLite-Datenbankdatei für diesen Ordner angelegt. Die vollständige Tabellenstruktur (alle Tabellen, alle Spalten) wird dabei erzeugt. Befüllt werden in diesem Schritt ausschließlich:

* **`metadata`-Tabelle:** Dateiname, UTC-Startzeit-Methode, Zeitoffset und lat/lon, Notizfeld, aber leer initialisieren, Byte-Blob für key-Value-Paare füllen

Alle anderen Tabellen (Erkennungen, Vektoren etc.) bleiben leer und werden durch den Scouting Flight befüllt.

---

## 6. Freigabe für den Scouting Flight

Ein Ordner ist für den Scouting Job nur dann auswählbar, wenn:

- lat/lon gesetzt ist
- die Startzeit-Methode definiert ist
- die DB-Datei existiert

Im UI ist der Auswahl-Button für nicht-freigegebene Ordner deaktiviert (mit erklärendem Tooltip).

Bei **rekursiver Übernahme** in die Jobliste (ein Elternordner mit mehreren Unterordnern) werden nur die Unterordner berücksichtigt, die die obigen Bedingungen vollständig erfüllen. Unvollständige Ordner werden übersprungen und in einer Zusammenfassung aufgelistet.
