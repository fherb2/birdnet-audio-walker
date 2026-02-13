# Konzept: Hierarchisches Vektordatenbank-System mit DiskANN

**Version:** 2.0
**Datum:** 10. Februar 2026
**Status:** Konzeptphase

---

## 1. Überblick und Motivation

### 1.1 Die zentrale Idee

Das bestehende BirdNET-Walker-System speichert derzeit für jeden Aufnahme-Ordner eine separate HDF5-Datei mit Embedding-Vektoren. Diese Embeddings sind 1024-dimensionale Feature-Vektoren, die aus dem BirdNET-Modell extrahiert werden und die akustischen Eigenschaften jeder Detection repräsentieren. Das funktioniert gut für die lokale Speicherung zugehörig zu den Audiofiles und Detektionen des Verzeichnisses auf der gleichen Ebene. Aber es gibt ein fundamentales Problem: Die Embeddings sind über viele einzelne Dateien verstreut, wenn es mehrere derartiger Ordner gibt, in denen man die Audiofiles und Detektionen sortiert. Es gibt dann keine Möglichkeit, schnell nach ähnlichen Detections global über alle Aufnahme-Sessions hinweg zu suchen.

Die neue Architektur führt ein hierarchisches System ein, bei dem Vektordatenbanken auf verschiedenen Ebenen existieren können. Eine lokale Vektordatenbank liegt direkt bei den Audiofiles und speichert alle Embeddings dieser Session. Übergeordnete Ordner können globale Vektordatenbanken enthalten, die automatisch alle Embeddings aus untergeordneten Sessions aggregieren. Auch die Erkennungen werden entsprechend globaler zusammengeführt.

### 1.2 Warum DiskANN als Embedding-Vektor Datenbank?

Der Wechsel von HDF5 zu DiskANN hat einen spezifischen Grund: DiskANN ist eine Vektordatenbank-Technologie von Microsoft Research, die speziell dafür entwickelt wurde, Milliarden von hochdimensionalen Vektoren effizient auf SSDs zu speichern und schnelle Nearest-Neighbor-Suchen zu ermöglichen. Im Gegensatz zu HDF5, das eine reine Speichertechnologie ist, baut DiskANN einen Index auf, der Ähnlichkeitssuchen dramatisch beschleunigt, ohne gezwungen zu sein, die Daten im Ganzen im Arbeitsspeicher zu halten.

Das ist entscheidend für die biologische Fragestellung: Ein Nutzere hat vielleicht in einer Session einen Cluster von Detections gefunden, der wie eine Fehlklassifikation aussieht. Mit DiskANN kann er fragen: "Finde alle ähnlichen Detections in allen meinen anderen Sessions". Diese Query würde über potentiell Millionen von Vektoren laufen und muss trotzdem in wenigen Sekunden Ergebnisse liefern. Weder HDF5, noch Zarr noch eine SQL-Datenbank kann das leisten – man müsste alle Vektoren laden und manuell Distanzen berechnen, was bei großen Datenmengen völlig unpraktikabel ist.

### 1.3 Die biologische Perspektive

Aus biologischer Sicht ist das System so konzipiert, dass die Embeddings modell-intrinsisch sind, nicht standort-spezifisch. Das bedeutet: Ein Kohlmeisen-Reviergesang hat überall ähnliche Embeddings, egal wo er aufgenommen wurde. Sofern das gleiche Modell zur Erkennung (BirdNET der gleichen Version) verwendet wurde. Wenn BirdNET einen Blaumeisen-Ruf fälschlicherweise als Kohlmeise klassifiziert, wird dieser Fehler ebenfalls überall ähnliche Embeddings produzieren.

Das ermöglicht systematische Qualitätskontrolle: Einmal einen Fehler identifiziert, können alle ähnlichen Fälle in allen Sessions gefunden und korrigiert werden. Das ist der Kern des Mehrwerts – nicht nur lokale Analyse, sondern cross-site Pattern Recognition. Es ist auch die Ausgangsbasis dafür, durch die Erweiterung des Modells solche "Schwächen" auszumerzen.

---

## 2. Architektur-Überblick

### 2.1 Das hierarchische Prinzip

Die neue Architektur basiert auf einem einfachen Prinzip: Jede Datenbank (ob lokal oder global) besteht aus genau zwei Komponenten – einer SQLite-Datei und einem DiskANN-Index. Die Benennung dieser Dateien signalisiert automatisch ihren Typ:

Lokale Datenbanken bei den Audiofiles heißen `birdnet_analysis.db` und haben einen zugehörigen DiskANN-Index `birdnet_vectors.diskann/`. Diese lokalen Datenbanken werden vom bestehenden birdnet-walker erstellt und enthalten alle Detections und Embeddings einer Aufnahme-Session, die als Ordner im Dateisystem abgebildet ist.

Globale Datenbanken in übergeordneten Ordnern heißen `birdnet_global.db` und haben einen Index `birdnet_vectors_global.diskann/`. Da der birdnet-walker dafür ausgelegt ist, ganze Ordnerstrukturen rekursiv zu durchsuchen und neue Daten zu sammeln (neue Ordner oder neue Audio-Dateien in Ordnern), wird dieser im Rahmen dieses Konzepts um die gloable Methodik erweitert. Freigeschaltet wird diese Option durch die Option -g / --global.

Um es nochmal zusammenzustellen:

* ohne die Optionen -r/--recursive oder/und -g/--global: es wird nur der aktuelle Ordner, der als Pfad übergeben wird, durchsucht und die lokalen Datenbanken (`birdnet_analysis.db` und `birdnet_vectors.diskann/`) werden angelegt oder mit den Ergennissen noch nicht bearbeiteter Audiofiles erweitert.
* mit Option -r/--recursive: Es werden ab dem angegebenen Pfad alles in diesem Ordner und darunter durchsucht und dort die einzelnen Datenbanken angelegt bzw. erweitert.
* mit Option -g/--global (egal, ob -r/--recursive angegeben ist): Es werden die gleichen Operationen recursiv ausgeführt, wie mit der Option -r/--recursive, zusätzlich wird auf der obersten Ebene (also der, die als Pfad angegeben wurde) eine globale Datenbank `birdnet_global.db` und `birdnet_vectors_global.diskann/` angelegt beziehungsweise erweitert.

Die Embedding-Vektoren werden dabei in allen Fällen nur gesammelt, wenn das mit dem zusätzlichen Argument --extract-embeddings gefordert wird!

Zu bemerken ist, dass im bisherigen Zustand aber auch für die neue Funktion gilt: Es wird nicht doppelt indiziert. Immer nur neue Audios bzw. ganze neue Ordner mit Audios werden als neu erkannt, dann mit BirdNET analysiert und dann die Daten lokal (im Ordner der Audio-Datei) und zusätzlich in der globalen Datenbank (ganz oben liegenden Datenbank) zugefügt.

Der Clou: Globale Datenbanken können damit im Prinzip beliebig tief verschachtelt werden. Ein Ordner "projekt_2024" kann eine globale Datenbank haben, die alle Standorte dieses Jahres aggregiert. Ein Ordner "alle_projekte" kann darüber liegend eine weitere globale Datenbank hat, die mehrere Jahre aggregiert. Für diesen Fall startet man den birdnet-walker beginnend von "unten" in mehreren Ebenen. Lokale Datenbanken werden nur einmal erstellt, da auch bei einer Analyse aus einer "oberen Etage" die Erkennungsdaten weiter unten erkannt werden und nicht nochmal eine Erkennung beginnt. Es wird dann immer geprüft, welche Daten in den jeweiligen Ebenen neu sind und in der Ausgangseben der recursiven Suche gesammelt.

### 2.2 Datenfluss im neuen System

Der Nutzer analysiert einen Ordner oder ein geschachteltes Ordnersystem mit Audiofiles, und der Walker erstellt eine lokale SQLite-Datenbank mit allen Detections und den Embeddings (wenn embeddings aktiviert sind) in jedem Ordner. Wenn Embeddings aktiviert sind, extrahiert der Walker für jede Detection einen 1024-dimensionalen Vektor. Diese Vektoren werden aber nicht mehr in eine HDF5-Datei geschrieben, sondern direkt in einen DiskANN-Index.

Der DiskANN-Index ist eine Ordner-Struktur (daher die `.diskann/` Notation), die mehrere Dateien enthält: Den eigentlichen Vektor-Speicher, die Index-Struktur für schnelle Suchen, und Metadaten. Der Walker fügt jeden Vektor hinzu und bekommt eine vector_id zurück – eine fortlaufende Nummer, die in der SQLite-Datenbank bei der entsprechenden Detection als Reference gespeichert wird.

Über einen Hash-Mechanismus, der in der zugehörigen SQLite-Datenbank referenziert mitgespeichert wird, ist sichergestellt, dass keine Duplikate in der DiskANN abgelegt werden: Wenn derselbe Audio-Schnipsel tatsächlich mehrfach analysiert wurde, wird sein Embedding nur einmal in der lokalen, wie globalen DiskANN Datenbank gespeichert.

### 2.3 Deduplizierung über Hash-Werte

Abgesehen davon, dass in den SQL-Datenbanken gespeichert ist, welche Audiofiles bereits analaysiert wurden, da sie ja auch als Backreferenz für die Audioschnipsel der Erkennungen dienen, soll zur Absicherung, in die DiskANN keine Vektoren doppelt einzutragen, ein Hash über die eingetragenen Vektoren in der SQLite gespeichert werden. Die Deduplizierung funktioniert über einen vector_hash, der für jeden Embedding-Vektor berechnet wird. Dieser Hash ist ein SHA256 über das float32-Array des Vektors. Da Embeddings deterministisch sind (gleiches Audio → gleicher Vektor), haben identische Detections auch identische Hashes.

Das ist speichereffizient: Wenn derselbe Vogel-Ruf in zehn verschiedenen Sessions vorkommt, gibt es zehn Detection-Einträge in der globalen SQL-Datenbank, aber nur einen Vektor im DiskANN-Index.

---

## 3. Änderungen am bestehenden Code

### 3.1 Migration von HDF5 zu DiskANN in birdnet_walker

Der birdnet-walker muss in mehreren Modulen angepasst werden, aber die grundlegende Logik bleibt erhalten. Die Hauptänderung betrifft die Art, wie Embeddings gespeichert werden.

Im aktuellen System gibt es eine Funktion `write_embeddings_to_hdf5()`, die ein numpy-Array von Embeddings nimmt und in eine HDF5-Datei schreibt. Diese Funktion gibt einen Start-Index zurück, der dann verwendet wird, um jede Detection mit ihrer Position in der HDF5-Datei zu verknüpfen.

In der neuen Version wird diese Funktion ersetzt durch `write_embeddings_to_diskann()`, die die Embeddings nicht in eine Datei schreibt, sondern einzeln zum DiskANN-Index hinzufügt. DiskANN arbeitet anders als HDF5: Statt ein großes Array auf einmal zu schreiben, fügt man Vektoren iterativ hinzu. Für jeden Vektor gibt DiskANN eine ID zurück – eine fortlaufende Nummer, beginnend bei 0.

Diese wird in der SQLite-Datenbank nicht nur bei den betreffenden Erkennungen abgespeicht  (als Vorwärts-Referenz), sondern in einer eigenen Tabelle mit dem zu erstellenden Hash des Vektors gespeichert. Diese Tabelle dient der Prüfung, dass der Vektor nicht schon abgespeichert wurde und ist entsprechend vor `write_embeddings_to_diskann()` zu prüfen.

### 3.2 Erweiterung der SQLite-Schema

Die `detections`-Tabelle in der lokalen Datenbank muss um ein Feld erweitert werden. Aktuell gibt es ein Feld `embedding_idx INTEGER`, das den Index in der HDF5-Datei speichert. Dieses Feld wird umbenannt zu `vector_id INTEGER` – konzeptionell das Gleiche, nur dass es jetzt auf DiskANN verweist statt auf HDF5.

Eine neue Tabell ist erforderlich, um die ID jedes Vektors mit einem Feld `vector_hash TEXT` zu verbinden, in dem der HA256-Hash des Embedding-Vektors abgelegt wird. Der Hash wird einmal beim Einfügen berechnet und ist unveränderlich. Er dient zur Prüfung, dass neue Vektoren nicht doch schon enthalten sind, aber vor allem der Deduplizierung beim Import in globale Datenbanken.

### 3.3 Versionierung über db_version

Um zu tracken, welche Datenbank welches Schema hat, wird eine neue Tabelle `db_version` eingeführt. Diese ist sehr einfach – nur key-value-Paare:

```
db_type: "session" oder "global"
schema_version: "1.0"
diskann_version: "0.7.0"
```

Damit kann jedes Tool, das eine Datenbank öffnet, sofort erkennen: Ist das eine alte Datenbank? Dann muss ich anders damit umgehen. Ist das eine globale Datenbank? Dann weiß ich, dass die Struktur anders ist.

Das ermöglicht zukünftige Migrationen (im Moment noch nicht nötig, da alles noch in Entwicklung): Wenn wir später das Schema ändern, können wir die schema_version hochzählen und automatische Migrations-Scripts schreiben.

---

## 4. Neues Tool oder Erweiterung?

Jedes Tool, jede Option, jede zwingend notwendige Zeile Benutzerdokumentation macht die Anwendung schwieriger. Die Funktionalität sollte einfach da sein.

Für alles an Vereinfachung: Option --do-all -> Das volle Programm ohne weitere Optionen.

---

## 5. Datenbank-Struktur im Detail

### 5.1 Lokale Session-Datenbank

Die lokale Datenbank (`birdnet_analysis.db`) bleibt weitgehend wie sie ist. Die zentrale Änderung ist die `detections`-Tabelle. Statt einem Feld `embedding_idx` gibt es jetzt: `vector_id` (die ID im DiskANN-Index)

Eine weite Tabelle führt dann zusammen:

`vector_id` und `vector_hash` (der SHA256-Hash des Vektors).

Die vector_id wird direkt vom DiskANN-Index zurückgegeben, wenn ein Vektor hinzugefügt wird. Sie ist immer eine nicht-negative Ganzzahl, beginnend bei 0, fortlaufend ohne Lücken. Wenn eine Detection keine Embeddings hat (weil --extract-embeddings nicht verwendet wurde), ist vector_id NULL.

Der vector_hash wird einmal beim Einfügen berechnet. Die Berechnung erfolgt über: `hashlib.sha256(embedding.tobytes()).hexdigest()`. Das gibt einen 64-Zeichen-String zurück. Dieser Hash ist unveränderlich und wird nie neu berechnet – er ist quasi der Fingerabdruck des Vektors.

Die neue `db_version`-Tabelle enthält Metadaten über die Datenbank selbst. Sie hat nur zwei Spalten: `key` und `value`, beide Text. Wichtige Einträge sind:

- `db_type`: "session" (markiert diese als lokale Datenbank)
- `schema_version`: "1.0" (Version des Schema)
- `diskann_version`: Die Version der DiskANN-Library, mit der der Index erstellt wurde

### 5.2 Globale Aggregations-Datenbank

Die globale Datenbank (`birdnet_global.db`) hat eine ähnliche Struktur, wie die lokalen Datenbanken.

Ihre `detections`-Tabelle enthält bei den Detection-Daten den realtiven Pfad zum Audio statt nur den Dateinamen selbst. Und die Verweise zum Vektor in der DiskANN enthalten die zur globalen, auf gleicher Ebene befindlichen DiskANN-Datenhbank. Das heißt, bei der Übernahme der Daten der lokalen DBs wird auch der Vektor von dort in die globale DB übernommen und dessen ID zusammen mit dem Hash in der globalen SQLite abgespeichert. Nicht der Verweis zur lokalen Quelldatenbank. Durch den Wert des Hash wird trotzdem erkannt, ob ein Vektor vielleicht doch doppeklt eingelesen würde.

Nach dem Einlesevorgang ist die gloable SQLite und DiskANN-Datenbank über alle untergeordneten Audiofiles im Bilde. Für eine globale Analyse werden die untergeordneten Datenbanken gar nicht benötigt. Das schafft einerseits Redundanz und doppelte Daten, wenn man Datenbanken lokal und global erstellt. Aber die globalen Datenbanken sind nicht davon abhängig, ob der NButzer auch alle seine lokalen Datenbanken richtig gepflegt hat: Starte ich den birdnet-walker global so erzeugt oder erweitert er mir auch die lokalen Datenbanken, füllt aber unabhängig davon immer auch die globale Datenbank.

## 6. Technische Details zu DiskANN

### 6.1 Warum DiskANN und nicht andere Technologien?

Es gibt viele Vektordatenbank-Technologien: FAISS, Annoy, Milvus, Qdrant, ChromaDB. Die Wahl von DiskANN basiert auf mehreren Überlegungen:

DiskANN ist speziell für disk-basierte Speicherung optimiert. Das ist wichtig, weil biologische Projekte oft auf Servern mit begrenztem RAM, aber viel SSD/HDD-Speicher laufen. DiskANN kann Milliarden von Vektoren verwalten, ohne sie alle in den RAM laden zu müssen. Der Index ist so strukturiert, dass nur die relevanten Teile geladen werden, wenn eine Suche durchgeführt wird.

DiskANN ist Open Source und hat Python-Bindings über PyPI. Die Integration ist also straightforward – keine komplizierte Installation oder separate Server-Prozesse. Ein einfaches `pip install diskannpy` reicht.

DiskANN skaliert exzellent: Die Suchgeschwindigkeit degradiert nur logarithmisch mit der Anzahl der Vektoren. Eine Suche über 1 Million Vektoren ist nur unwesentlich langsamer als über 100.000. Das ist wichtig, weil globale Datenbanken schnell sehr groß werden können.

### 6.2 Index-Aufbau und -Verwaltung

Ein DiskANN-Index ist kein einzelnes File, sondern eine Ordner-Struktur mit mehreren Dateien. Daher die Notation `birdnet_vectors.diskann/` (mit Slash am Ende, um zu signalisieren: Das ist ein Ordner).

Beim erstmaligen Erstellen wird der Index mit bestimmten Parametern initialisiert: Dimensionalität (1024), Distanz-Metrik (Cosinus-Ähnlichkeit), maximale Anzahl von Nachbarn im Index-Graph, etc. Diese Parameter werden in einer Metadaten-Datei im Index-Ordner gespeichert.

Vektoren werden dem Index einzeln oder in Batches hinzugefügt. DiskANN baut intern eine Graph-Struktur auf, die für schnelle Navigation während der Suche optimiert ist. Wichtig: Der Index muss periodisch "konsolidiert" werden – ein Prozess, der die Graph-Struktur optimiert. Das geschieht nicht nach jedem eingefügten Vektor, sondern in größeren Intervallen (z.B. nach 10.000 neuen Vektoren).

Für unseren Anwendungsfall bedeutet das: Wenn birdnet-walker einen neuen Ordner analysiert und 500 Detections findet, fügt er 500 Vektoren zum Index hinzu. Nach Abschluss der Analyse wird einmal eine Index-Konsolidierung durchgeführt. Das ist ein kurzer Prozess (wenige Sekunden), der sicherstellt, dass der Index optimal für Suchen ist.

### 6.3 Persistenz und Wiederherstellung

Ein großer Vorteil von DiskANN ist die Persistenz: Der Index liegt komplett auf Disk. Wenn das Programm beendet wird und später neu gestartet wird, kann der Index einfach wieder geöffnet werden – alle Daten sind noch da.

Das ist wichtig für die Resume-Logik von birdnet-walker: Wenn der Walker während der Analyse abstürzt, können beim Neustart die bereits geschriebenen Vektoren im DiskANN-Index verbleiben. Der Walker muss nur in der SQLite-Datenbank prüfen, welche Files schon vollständig verarbeitet wurden, und kann dann dort weitermachen. Im schlimmsten Fall sagt der Hash, dass der Vektor schon indiziert wurde.

Es gibt allerdings eine Besonderheit: DiskANN unterstützt kein echtes "Löschen" von Vektoren. Wenn ein Vektor einmal hinzugefügt wurde, kann er nicht mehr entfernt werden. Man kann nur den gesamten Index neu aufbauen. Für unseren Anwendungsfall ist das kein Problem: Wir löschen nie Detections. Wenn eine Detection als fehlerhaft markiert wird, bleibt sie in der Datenbank (mit einer entsprechenden Markierung), aber der Vektor bleibt ebenfalls im Index. (Diese Negativ-Markierung ist noch nicht implementiert!)

## 7. Workflow für den Nutzer

### 7.1 Neue Aufnahmen analysieren (wie bisher)

Der grundlegende Workflow ändert sich für den Nutzer katisch nicht gegenüber der bisherigen Form. Wie bisher ruft er `birdnet-walker /pfad/zu/ordner (und einige Optionen)` auf. Das Programm läuft durch, analysiert alle WAV-Files, und erstellt/erweitert eine Datenbank lokal und bei recursiver Arbeit wenn gewünscht, auch die globale Datenbank.

Auch die Resume-Funktion funktioniert wie bisher: Wenn der Walker abbricht und neu gestartet wird, analysiert er nur die Files, die noch nicht den Status "completed" in der `processing_status`-Tabelle haben. Zusätzlich sichert der Hash die Indizierung der Embeddings ab.

## 9. Offene Fragen und Entscheidungen

### 9.1 DiskANN-Parameter

Es gibt diverse Parameter beim Erstellen eines DiskANN-Index: Anzahl der Nachbarn im Graph, Distanz-Metrik, Konsolidierungs-Intervalle. Wir müssen sinnvolle Defaults wählen, die für typische biologische Projekte (Größenordnung: 10.000 bis 1.000.000 Detections pro Session) gut funktionieren.

Die Distanz-Metrik sollte Cosine-Similarity sein, da wir an der Richtung der Vektoren interessiert sind, nicht an ihrer absoluten Magnitude. Denn das ist bei Embeddings aus neuronalen Netzen üblich.

Die Anzahl der Nachbarn im Index-Graph beeinflusst den Trade-off zwischen Suchgeschwindigkeit und Genauigkeit. Ein höherer Wert bedeutet langsameren Aufbau, aber präzisere Suchen. Für unseren Anwendungsfall (wo Recall wichtiger ist als absolute Geschwindigkeit) sollten wir eher großzügig dimensionieren.

Konkrete Werte müssen experimentell ermittelt werden – idealerweise mit realen Datenbanken aus Testprojekten.

### 9.2 Performance-Überlegungen

Ein DiskANN-Index ist schnell für Suchen, aber langsamer beim Aufbau. Das Schreiben von 500 Embeddings in HDF5 dauert Millisekunden. Das Hinzufügen von 500 Vektoren zu DiskANN plus anschließende Konsolidierung kann mehrere Sekunden dauern.

Für den normalen Workflow (ein Ordner analysieren, dann fertig) ist das unkritisch – ein paar Sekunden zusätzliche Wartezeit am Ende der Analyse fallen nicht ins Gewicht. Aber für sehr große Batch-Jobs (hunderte Ordner) könnte sich das summieren.

Eine mögliche Optimierung: Batch-Inserts in DiskANN. Statt jeden Vektor einzeln hinzuzufügen, sammeln wir alle Vektoren eines Files und fügen sie als Batch hinzu. DiskANN kann dann einmal den Index aktualisieren statt 500 mal. Das müsste in der Implementierung berücksichtigt werden.

### 9.3 Fehlerbehandlung bei korrupten Indices

Was passiert, wenn ein DiskANN-Index korrupt wird (z.B. durch Absturz während des Schreibens)? Im Gegensatz zu HDF5, wo man einfach die letzte gültige Version wiederherstellen kann, ist DiskANN weniger fehlertolerant.

Ein möglicher Ansatz: Backup des Index vor jeder größeren Operation. Wenn birdnet-walker 100 neue Files analysiert, wird vor dem ersten Insert ein Snapshot des aktuellen Index-Zustands gemacht. Falls während der Verarbeitung etwas schiefgeht, kann der Index auf den Snapshot zurückgesetzt werden.

Alternativ: Der Index ist als "expendable" zu betrachten – er kann jederzeit aus den Daten in der SQLite-Datenbank neu aufgebaut werden. Die SQLite-Datenbank ist die "Single Source of Truth", und der DiskANN-Index ist nur ein beschleunigender Cache. Wenn der Index korrupt ist, löschen wir ihn und bauen ihn neu aus der SQLite-Datenbank.

Das würde jedoch bedeuten: In der SQLite-Datenbank müssen die Embeddings selbst auch gespeichert werden, nicht nur die vector_ids. Oder wir speichern die Embeddings in einem separaten, robusten Format (z.B. als BLOB in einer weiteren SQLite-Tabelle), und der DiskANN-Index ist rein sekundär. Das bedeutet: Das was wir jetzt in HDF5 schreiben, müsste als eigene Tabelle in SQLite abgelegt werden. DiskANN wäre dann top-of zur SQLite-DB.

### 9.4 Umgang mit sehr großen Datenmengen

Was passiert, wenn eine globale Datenbank 10 Millionen Detections hat? DiskANN kann das theoretisch handhaben, aber praktische Aspekte müssen bedacht werden:

Die SQLite-Datenbank mit 10 Millionen Zeilen in der `detections`-Tabelle ist mehrere Gigabyte groß. Queries können langsam werden, wenn nicht richtig indiziert. Wir müssen sicherstellen, dass alle relevanten Spalten (insbesondere `vector_hash` für die Deduplizierungs-Lookups) gut indiziert sind.

Der DiskANN-Index mit 10 Millionen Vektoren (je 1024 * 4 Bytes = 4 KB) ist etwa 40 GB groß (plus Index-Overhead). Das passt problemlos auf moderne SSDs, aber das Laden und Konsolidieren kann Minuten dauern. Wir sollten dem Nutzer klare Fortschrittsanzeigen geben.

Eine mögliche Optimierung für Experten-Nutzer: Sharding. Die globale Datenbank könnte aufgeteilt werden in mehrere Shards (z.B. nach Jahr oder Standort). Jeder Shard ist eine separate globale Datenbank. Bei Suchen werden dann parallel mehrere Shards durchsucht. Das ist aber ein fortgeschrittenes Feature für später.

---

## 10. Implementierungsstrategie

### 10.1 Schrittweise Einführung

Die Umstellung sollte nicht in einem großen Bang passieren, sondern schrittweise. Ein möglicher Fahrplan:

**Phase 1: Lokale Aufnahme der Embedding-Vektoren zur SQLite-DB in birdnet-walker zusammen mit den Erkennungen und der Mitschrift, welche Audio-Files verarbeitet wurden**

Statt in HDF abzulegen, wird für4 die Embedding-Vektoren eine Datenbanktabelle in SQLite angelegt. Sie nimmt den Vektor und den sofort dazu erstellten Hash auf. Eine eindeutige ID wird dann den Erkennungen zugefügt, die für den gleichen Zeitabschnitt (BirdNET: 3s-Stück) erkannt wurden.

**Phase 2: Lokale DiskANN-Unterstützung in birdnet-walker**

Jetzt werden die Embeddings zusätzlich gleich noch in DiskANN importiert und back-referenziert in die SQLite-DB. Die `db_version`-Tabelle wird in SQLite eingeführt, um die Metainformationen zur DiskANN zu speichern.

**Phase 3: Globalität**

Jetzt bauen wir das Globale ein: Zuerst wird geprüft, ob in der rekursiven Bearbeitung die Ordnerlokale Datenbankerstellung funktioniert. Dann wird die Funktionalität der globalen Datenbanken integriert. Die Position ist dafür immer der Startpunkt der recursiven Arbeit. Das muss der Nutzer gewähren. Wichtig ist, dass jetzt zweigleisig analysiert wird:

* auf Ordner-Niveau, ob neue Audiodateien zu erkennen und indizieren sind
* auf Global-Niveau, dass diese Analysen global zugefügt werden und: ob weitere, bisher nur auf Ordnerebene erstellte Analyseergebnisse und Vektoren in die globale Datenbanken zuzufügen sind.
