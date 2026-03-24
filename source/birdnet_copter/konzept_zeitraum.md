# Konzept: Zeit, Raum und Audiodaten-Import in birdnet-copter

## 1. Grundprinzip: UTC und GPS als unveränderliche Wahrheit

Jede Aufnahme ist ein Ereignis in Raum und Zeit. Die einzige physikalisch eindeutige Beschreibung dieses Ereignisses ist die Kombination aus einem absoluten Zeitstempel in UTC und einer geographischen Position in WGS84-Koordinaten (Breitengrad und Längengrad). Diese beiden Informationen bilden das Fundament aller weiteren Verarbeitung. Sie werden beim Import einmal festgelegt, in der Datenbank unveränderlich gespeichert und dienen als Referenz für alle Darstellungen und Analysen.

Politische Zeitzonen, Sommerzeit-Regelungen und biologische Solarzeit sind dagegen Interpretationen dieses Grunddatums. Sie hängen von Konventionen ab, die sich ändern können, und von Fragestellungen, die je nach Nutzer unterschiedlich sind. Deshalb werden sie nicht in der Datenbank gespeichert, sondern zur Laufzeit aus UTC und GPS berechnet.

Konkret bedeutet das: Die `metadata`-Tabelle enthält für jedes Audiofile genau einen Raum-Zeit-Anker – den UTC-Zeitstempel des Aufnahmebeginns und die GPS-Koordinaten des Aufnahmeorts. Jede Erkennung in der `detections`-Tabelle ist über einen Zeitoffset relativ zu diesem Anker präzise in Raum und Zeit verortet. Die genaue technische Ausgestaltung dieser Offsets – ob als Sekundenwert, als Samplezahl oder als vollständig berechneter UTC-Zeitstempel – ist noch abschließend zu entscheiden. Entscheidend ist, dass jedes Schnipsel auf den Bruchteil einer Sekunde genau in Raum und Zeit rekonstruierbar bleibt.

---

## 2. Die Import-Pipeline und das Plugin-Konzept

### 2.1 Warum Plugins?

Audiodaten kommen aus unterschiedlichen Quellen: von AudioMoth-Rekordern mit reichhaltigen GUANO-Metadaten, von einfachen Diktiergeräten ohne jegliche Zeitinformation, von Forschungsgeräten mit proprietären Formaten. Eine starre Import-Logik kann dieser Vielfalt nicht gerecht werden. Deshalb wird der Import-Mechanismus als Plugin-Schnittstelle gestaltet, bei der jedes Plugin genau weiß, wie es mit einem bestimmten Dateityp oder Gerätetyp umgeht.

### 2.2 Die Plugin-Schnittstelle

Jedes Import-Plugin ist ein Python-Modul oder eine Python-Klasse, die eine definierte Schnittstelle implementiert. Diese Schnittstelle verlangt genau zwei Pflichtinformationen: den UTC-Zeitstempel des Aufnahmebeginns und die GPS-Koordinaten des Aufnahmeorts. Alles weitere ist optional.

In Python würde das als abstrakte Basisklasse mit `abc.ABC` und `@abc.abstractmethod` ausgedrückt. Ein Plugin muss eine Methode `extract_metadata(file_path: Path) -> dict` implementieren, die mindestens die Schlüssel `timestamp_utc` (als `datetime`-Objekt mit UTC-Zeitzone) und `gps_lat`/`gps_lon` (als Floats) zurückgibt. Fehlen diese Pflichtfelder, muss das Plugin eine definierte Ausnahme werfen, die dem Scouting Flight signalisiert, dass eine Nutzer-Interaktion erforderlich ist.

Zusätzliche Metadaten – Seriennummer des Geräts, Temperatur, Akkuspannung, Verstärkungseinstellung und alles weitere – werden als optionaler `extra_metadata`-Eintrag übergeben. Dieser wird als binäres Blob in der Datenbank gespeichert, dessen Serialisierung und Deserialisierung das Plugin selbst verantwortet. Das kann ein JSON-Dictionary sein, ein Pickle-Objekt oder jedes andere Format, solange das Plugin beim Lesen weiß, wie es damit umgeht. Die Datenbank selbst muss den Inhalt nicht verstehen.

### 2.3 Mitgelieferte Plugins

Zum Start werden zwei Plugins mitgeliefert. Das **AudioMoth-Plugin** liest GUANO-Chunks und ICMT-Chunks aus WAV-Dateien, wie es der aktuelle Code in `audiomoth_import.py` bereits tut – allerdings vereinfacht um die Zeitzonenkonvertierung, da diese künftig außerhalb des Plugins stattfindet. Das **Fallback-Plugin** kann keine Metadaten automatisch extrahieren und löst stattdessen einen Nutzer-Dialog aus, in dem alle Pflichtinformationen manuell eingegeben werden.

### 2.4 Plugin-Erkennung und -Auswahl

Ein Scouting Flight hat genau eine Import-Strategie, also genau ein aktives Plugin. Dieses wird im Scouting Flight konfiguriert, bevor der erste Job gestartet wird. Zusätzlich kann ein Plugin eine `can_handle(file_path: Path) -> bool`-Methode anbieten, die automatisch prüft ob es für eine gegebene Datei zuständig ist – etwa durch Prüfung des GUANO-Chunks. Auf Basis dieser Methode kann das System dem Nutzer einen Vorschlag machen, welches Plugin zu verwenden ist.

### 2.5 Fehlende oder fehlerhafte Daten

Da keine Audiofile-Datensätze ohne vollständige Pflichtinformationen in die Datenbank gelangen dürfen, muss der Import-Prozess mit fehlenden Daten umgehen können. Der Scouting Flight zeigt vor dem Start – oder beim ersten Auftreten eines Problems – einen Dialog an, in dem der Nutzer die fehlenden Informationen ergänzen oder fehlerhafte Werte korrigieren kann. Typische Korrekturfälle sind ein systematischer Zeitversatz (alle Aufnahmen einer Session sind um einen festen Betrag verschoben), ungenaue GPS-Koordinaten (Laborinitialisierung) oder vollständig fehlende Ortsdaten.

---

## 3. GPS-Koordinaten und Zeitzonen

### 3.1 Vom GPS zur Zeitzone

Wenn GPS-Koordinaten vorliegen, kann die zugehörige politische Zeitzone automatisch und ohne Netzwerkzugang ermittelt werden. Das Python-Paket `timezonefinder` enthält eine vollständige Weltkarte der Zeitzonengrenzen und liefert zu einem Koordinatenpaar den IANA-Zeitzonennamen. Ein Aufruf sieht so aus:

```python
from timezonefinder import TimezoneFinder
tf = TimezoneFinder()
tz_name = tf.timezone_at(lat=51.1657, lng=13.7372)
# Ergebnis: 'Europe/Berlin'
```

Dieser IANA-Name kann dann mit Pythons `zoneinfo.ZoneInfo` verwendet werden, um UTC-Zeitstempel korrekt in Lokalzeit umzurechnen – inklusive automatischer Sommerzeit-Berücksichtigung, da `zoneinfo` die vollständigen historischen Zeitzonenregeln kennt.

### 3.2 Biologische Solarzeit

Die biologische Solarzeit orientiert sich am tatsächlichen Sonnenstand und ist damit unabhängig von politischen Zeitzonengrenzen. Sie ist für biologische Fragestellungen oft relevanter als die Uhrzeitzeit: Tagesrhythmen von Vögeln richten sich nach Sonnenauf- und -untergang, nicht nach Zeitzonen.

Das Python-Paket `astral` berechnet für beliebige GPS-Koordinaten und Datumswerte die exakten Zeiten von Sonnenaufgang, Sonnenmittagsstand und Sonnenuntergang. Darauf aufbauend lassen sich Zeitstempel in relative Solarzeit umrechnen – etwa als Anzahl Sekunden nach Sonnenaufgang oder als prozentualer Fortschritt des Tagbogens.

### 3.3 Aufnahmen über Zeitzonengrenzen

Wenn Aufnahmen aus verschiedenen Zeitzonen gemeinsam betrachtet werden, wird die Darstellung komplexer. Da die Session-Konfiguration im Hangar genau eine Interpretationsstrategie festlegt, gibt es hierfür zwei sinnvolle Lösungen: Entweder der Nutzer wählt eine feste politische Zeitzone für die gesamte Session (dann weichen Darstellungszeit und tatsächliche Lokalzeit für manche Aufnahmen ab), oder er wählt die GPS-basierte automatische Ermittlung (dann hat jedes File potenziell eine andere Lokalzeit). Beide Varianten sind korrekt – sie beantworten nur unterschiedliche Fragen.

---

## 4. Das DateTime-Modul zur Laufzeit

### 4.1 Zweck und Position im System

Das DateTime-Modul ist ein zentraler Konverter, der zwischen der in der Datenbank gespeicherten UTC-Zeit und der vom Nutzer gewünschten Darstellungszeit vermittelt. Es wird an jeder Stelle im Programm eingesetzt, wo Zeitstempel angezeigt oder gefiltert werden – im Audio Player, in der Diel Activity Map, in der Species List und in allen zukünftigen Ansichten.

### 4.2 Session-Konfiguration im Hangar

Im Hangar wählt der Nutzer seine Interpretationsstrategie. Diese Konfiguration besteht aus zwei Elementen: dem Zeitmodus und gegebenenfalls einer expliziten Zeitzone. Der Zeitmodus ist entweder "Politische Zeitzone" oder "Biologische Solarzeit". Bei politischer Zeitzone kann der Nutzer entweder eine IANA-Zeitzone manuell eingeben oder die automatische GPS-basierte Ermittlung aktivieren. Diese Konfiguration wird nicht gespeichert – sie gilt nur für die aktuelle Session und kann jederzeit geändert werden, woraufhin alle Anzeigen sofort neu berechnet werden.

### 4.3 Technische Umsetzung

Das Modul stellt eine einzige zentrale Funktion bereit, die einen UTC-Zeitstempel und GPS-Koordinaten entgegennimmt und die daraus resultierende Darstellungszeit zurückgibt. Bei politischer Zeitzone nutzt sie `zoneinfo.ZoneInfo` mit dem konfigurierten oder GPS-ermittelten IANA-Namen. Bei Solarzeit nutzt sie `astral` um Sonnenauf- und -untergang zu berechnen und gibt einen relativen Zeitwert zurück.

Für Filter-Operationen – etwa "zeige alle Erkennungen zwischen 06:00 und 08:00 Uhr" – muss die Umkehrfunktion existieren: eine Darstellungszeit in einen UTC-Bereich umrechnen. Das ist bei politischen Zeitzonen trivial, bei Solarzeit etwas aufwändiger aber prinzipiell lösbar.

---

## 5. Offene Punkte

Einige Entscheidungen müssen noch getroffen werden, bevor mit der Implementierung begonnen werden kann.

Die genaue Struktur der Zeitstempel in der `detections`-Tabelle ist noch offen. Entweder werden vollständige UTC-Zeitstempel pro Erkennung gespeichert (wie heute), oder nur Offsets relativ zum File-Startpunkt. Beide Ansätze haben Vor- und Nachteile bezüglich Speicherbedarf, Abfrageeffizienz und Lesbarkeit.

Die Plugin-Entdeckung – also wie das System weiß welche Plugins verfügbar sind – ist noch nicht definiert. Optionen sind ein festes `plugins/`-Verzeichnis, ein Eintrag in der Konfigurationsdatei oder der `entry_points`-Mechanismus von Python-Paketen.

Die genaue Darstellung der biologischen Solarzeit in der Benutzeroberfläche ist noch offen. Möglichkeiten sind eine absolute Uhrzeit der lokalen Solarzeit, ein Offset zu Sonnenaufgang oder -untergang in Stunden und Minuten, oder eine normalisierte Darstellung (0% = Sonnenaufgang, 100% = Sonnenuntergang).
