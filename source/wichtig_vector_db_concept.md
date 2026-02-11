# Konzept: Hierarchisches Vektordatenbank-System mit DiskANN

**Version:** 1.0  
**Datum:** 10. Februar 2026  
**Status:** Konzeptphase  

---

## 1. Überblick und Motivation

### 1.1 Die zentrale Idee

Das bestehende BirdNET-Walker-System speichert derzeit für jeden Aufnahme-Ordner eine separate HDF5-Datei mit Embedding-Vektoren. Diese Embeddings sind 1024-dimensionale Feature-Vektoren, die aus dem BirdNET-Modell extrahiert werden und die akustischen Eigenschaften jeder Detection repräsentieren. Das funktioniert gut für die lokale Speicherung, aber es gibt ein fundamentales Problem: Die Embeddings sind über viele einzelne Dateien verstreut, und es gibt keine Möglichkeit, schnell nach ähnlichen Detections über alle Aufnahme-Sessions hinweg zu suchen.

Die neue Architektur führt ein hierarchisches System ein, bei dem Vektordatenbanken auf verschiedenen Ebenen existieren können. Eine lokale Vektordatenbank liegt direkt bei den Audiofiles und speichert alle Embeddings dieser Session. Übergeordnete Ordner können globale Vektordatenbanken enthalten, die automatisch alle Embeddings aus untergeordneten Sessions aggregieren. Das Besondere: Diese Aggregation erfolgt ohne Duplikate und mit minimaler Redundanz.

### 1.2 Warum DiskANN?

Der Wechsel von HDF5 zu DiskANN hat einen spezifischen Grund: DiskANN ist eine Vektordatenbank-Technologie von Microsoft Research, die speziell dafür entwickelt wurde, Milliarden von hochdimensionalen Vektoren effizient auf SSDs zu speichern und schnelle Nearest-Neighbor-Suchen zu ermöglichen. Im Gegensatz zu HDF5, das eine reine Speichertechnologie ist, baut DiskANN einen Index auf, der Ähnlichkeitssuchen dramatisch beschleunigt.

Das ist entscheidend für die biologische Fragestellung: Ein Biologe hat vielleicht in einer Session einen Cluster von Detections gefunden, der wie eine Fehlklassifikation aussieht. Mit DiskANN kann er fragen: "Finde alle ähnlichen Detections in allen meinen anderen Sessions". Diese Query würde über potentiell Millionen von Vektoren laufen und muss trotzdem in wenigen Sekunden Ergebnisse liefern. HDF5 kann das nicht leisten – man müsste alle Vektoren laden und manuell Distanzen berechnen, was bei großen Datenmengen unpraktikabel ist.

### 1.3 Die biologische Perspektive

Aus biologischer Sicht ist das System so konzipiert, dass die Embeddings modell-intrinsisch sind, nicht standort-spezifisch. Das bedeutet: Ein Kohlmeisen-Reviergesang hat überall ähnliche Embeddings, egal wo er aufgenommen wurde. Wenn BirdNET einen Blaumeisen-Ruf fälschlicherweise als Kohlmeise klassifiziert, wird dieser Fehler ebenfalls überall ähnliche Embeddings produzieren.

Das ermöglicht systematische Qualitätskontrolle: Einmal einen Fehler identifiziert, können alle ähnlichen Fälle in allen Sessions gefunden und korrigiert werden. Das ist der Kern des Mehrwerts – nicht nur lokale Analyse, sondern cross-site Pattern Recognition.

---

## 2. Architektur-Überblick

### 2.1 Das hierarchische Prinzip

Die neue Architektur basiert auf einem einfachen Prinzip: Jede Datenbank (ob lokal oder global) besteht aus genau zwei Komponenten – einer SQLite-Datei und einem DiskANN-Index. Die Benennung dieser Dateien signalisiert automatisch ihren Typ:

Lokale Datenbanken bei den Audiofiles heißen `birdnet_analysis.db` und haben einen zugehörigen DiskANN-Index `birdnet_vectors.diskann/`. Diese lokalen Datenbanken werden vom bestehenden birdnet-walker erstellt und enthalten alle Detections und Embeddings einer Aufnahme-Session.

Globale Datenbanken in übergeordneten Ordnern heißen `birdnet_global.db` und haben einen Index `birdnet_vectors_global.diskann/`. Diese werden von einem neuen Tool erstellt, dem birdnet-global-sync, der alle untergeordneten lokalen Datenbanken findet und deren Inhalte aggregiert.

Der Clou: Globale Datenbanken können beliebig tief verschachtelt werden. Ein Ordner "projekt_2024" kann eine globale Datenbank haben, die alle Standorte dieses Jahres aggregiert. Ein Ordner "alle_projekte" kann eine weitere globale Datenbank haben, die mehrere Jahre aggregiert. Das System erkennt automatisch, welche Datenbanken zu welcher Ebene gehören, und verhindert, dass globale Datenbanken sich gegenseitig importieren.

### 2.2 Datenfluss im neuen System

Der Datenfluss beginnt wie bisher mit dem birdnet-walker. Der Nutzer analysiert einen Ordner mit Audiofiles, und der Walker erstellt eine lokale SQLite-Datenbank mit allen Detections. Wenn Embeddings aktiviert sind, extrahiert der Walker für jede Detection einen 1024-dimensionalen Vektor. Diese Vektoren werden aber nicht mehr in eine HDF5-Datei geschrieben, sondern direkt in einen DiskANN-Index.

Der DiskANN-Index ist eine Ordner-Struktur (daher die `.diskann/` Notation), die mehrere Dateien enthält: Den eigentlichen Vektor-Speicher, die Index-Struktur für schnelle Suchen, und Metadaten. Der Walker fügt jeden Vektor hinzu und bekommt eine vector_id zurück – eine fortlaufende Nummer, die in der SQLite-Datenbank bei der entsprechenden Detection gespeichert wird.

Später, wenn der Nutzer eine globale Datenbank erstellen möchte, ruft er birdnet-global-sync im übergeordneten Ordner auf. Dieses neue Tool scannt rekursiv nach allen lokalen Datenbanken, liest deren Detections und Vektoren, und fügt sie in die globale Datenbank ein. Dabei wird über einen Hash-Mechanismus sichergestellt, dass keine Duplikate entstehen – wenn derselbe Audio-Schnipsel mehrfach analysiert wurde, wird sein Embedding nur einmal in der globalen Datenbank gespeichert.

### 2.3 Deduplizierung über Hash-Werte

Die Deduplizierung funktioniert über einen vector_hash, der für jeden Embedding-Vektor berechnet wird. Dieser Hash ist ein SHA256 über das float32-Array des Vektors. Da Embeddings deterministisch sind (gleiches Audio → gleicher Vektor), haben identische Detections auch identische Hashes.

In der lokalen Datenbank wird dieser Hash für jede Detection gespeichert. Wenn birdnet-global-sync eine Detection importieren will, prüft es zuerst: Existiert dieser Hash schon in der globalen Datenbank? Falls ja, wird die Detection zwar in die globale SQL-Tabelle eingetragen (damit man weiß, dass diese Detection auch in dieser Session vorkam), aber der Vektor wird nicht dupliziert. Die Detection verweist einfach auf die bestehende vector_id.

Das ist speichereffizient: Wenn derselbe Vogel-Ruf in zehn verschiedenen Sessions vorkommt, gibt es zehn Detection-Einträge in der globalen SQL-Datenbank, aber nur einen Vektor im DiskANN-Index.

---

## 3. Änderungen am bestehenden Code

### 3.1 Migration von HDF5 zu DiskANN in birdnet_walker

Der birdnet-walker muss in mehreren Modulen angepasst werden, aber die grundlegende Logik bleibt erhalten. Die Hauptänderung betrifft die Art, wie Embeddings gespeichert werden.

Im aktuellen System gibt es eine Funktion `write_embeddings_to_hdf5()`, die ein numpy-Array von Embeddings nimmt und in eine HDF5-Datei schreibt. Diese Funktion gibt einen Start-Index zurück, der dann verwendet wird, um jede Detection mit ihrer Position in der HDF5-Datei zu verknüpfen.

In der neuen Version wird diese Funktion ersetzt durch `write_embeddings_to_diskann()`, die die Embeddings nicht in eine Datei schreibt, sondern einzeln zum DiskANN-Index hinzufügt. DiskANN arbeitet anders als HDF5: Statt ein großes Array auf einmal zu schreiben, fügt man Vektoren iterativ hinzu. Für jeden Vektor gibt DiskANN eine ID zurück – eine fortlaufende Nummer, beginnend bei 0.

Das bedeutet: Die bestehende Logik mit `start_idx` und kompakter Nummerierung bleibt konzeptionell gleich. Nur statt `hdf5_file[start_idx:end_idx] = embeddings` macht man jetzt eine Schleife: `for embedding in embeddings: vector_id = diskann.add(embedding)`. Die vector_ids sind immer noch 0, 1, 2, 3, ... – nur dass sie jetzt von DiskANN vergeben werden statt von uns berechnet.

### 3.2 Erweiterung der SQLite-Schema

Die `detections`-Tabelle in der lokalen Datenbank muss um ein Feld erweitert werden. Aktuell gibt es ein Feld `embedding_idx INTEGER`, das den Index in der HDF5-Datei speichert. Dieses Feld wird umbenannt zu `vector_id INTEGER` – konzeptionell das Gleiche, nur dass es jetzt auf DiskANN verweist statt auf HDF5.

Zusätzlich kommt ein neues Feld `vector_hash TEXT` hinzu. Dieses speichert den SHA256-Hash des Embedding-Vektors. Der Hash wird einmal beim Einfügen berechnet und ist unveränderlich. Er dient ausschließlich der Deduplizierung beim Import in globale Datenbanken.

Die anderen Tabellen (`metadata`, `processing_status`, `analysis_config`, `species_list`) bleiben komplett unverändert. Das ist wichtig für die Rückwärtskompatibilität: Bestehende Tools wie birdnet-play, die diese Tabellen lesen, funktionieren weiterhin ohne Änderungen.

### 3.3 Versionierung über db_version

Um zu tracken, welche Datenbank welches Schema hat, wird eine neue Tabelle `db_version` eingeführt. Diese ist sehr einfach – nur key-value-Paare:

```
db_type: "session" oder "global"
schema_version: "1.0"
diskann_version: "0.7.0"
created_at: ISO-Timestamp
```

Damit kann jedes Tool, das eine Datenbank öffnet, sofort erkennen: Ist das eine alte HDF5-basierte Datenbank? Dann muss ich anders damit umgehen. Ist das eine neue DiskANN-basierte Session-Datenbank? Dann kann ich direkt arbeiten. Ist das eine globale Datenbank? Dann weiß ich, dass die Struktur anders ist.

Das ermöglicht auch zukünftige Migrationen: Wenn wir später das Schema ändern, können wir die schema_version hochzählen und automatische Migrations-Scripts schreiben.

---

## 4. Das neue Tool: birdnet-global-sync

### 4.1 Zweck und Funktionsweise

Das birdnet-global-sync Tool ist das Herzstück der neuen Architektur. Es wird vom Nutzer manuell aufgerufen, wenn er eine globale Datenbank erstellen oder aktualisieren möchte. Der Aufruf ist einfach: Der Nutzer navigiert in einen Ordner, der mehrere Unterordner mit lokalen Datenbanken enthält, und ruft `birdnet-global-sync .` auf.

Das Tool macht dann folgendes: Es scannt rekursiv alle Unterordner und sucht nach Dateien namens `birdnet_analysis.db`. Wenn es eine findet, prüft es: Liegt im gleichen Ordner auch ein `birdnet_vectors.diskann/` Ordner? Falls ja, ist das eine lokale Session-Datenbank. Diese wird zur Liste der zu importierenden Quellen hinzugefügt.

Wichtig: Wenn das Tool auf eine `birdnet_global.db` stößt, stoppt es die Rekursion in diesem Zweig. Globale Datenbanken werden nicht importiert – das würde zu endlosen Schleifen und Duplikaten führen. Nur lokale Session-Datenbanken sind Importquellen.

### 4.2 Sync-Logik und Inkrementalität

Nach dem Scannen prüft das Tool: Existiert schon eine globale Datenbank im aktuellen Ordner? Falls nein, wird sie erstellt – eine leere `birdnet_global.db` und ein leerer `birdnet_vectors_global.diskann/` Index.

Falls eine globale Datenbank schon existiert, muss das Tool intelligent vorgehen: Es soll nur neue oder geänderte Detections importieren, nicht alles nochmal. Dazu führt die globale Datenbank eine Tabelle `source_dbs`, die für jede importierte Quell-Datenbank einen Eintrag hat:

```
source_db: relativer Pfad zur Quell-DB
last_synced: Timestamp
num_vectors_imported: Anzahl
db_checksum: Hash über die Quell-DB
```

Der db_checksum ist ein Hash über den gesamten Inhalt der Quell-Datenbank (nicht der Vektoren, sondern der SQL-Struktur). Wenn dieser Hash sich nicht geändert hat seit dem letzten Sync, kann diese Quelle übersprungen werden – es gibt nichts Neues zu importieren.

Falls der Hash sich geändert hat, oder die Quelle noch nie importiert wurde, lädt das Tool alle Detections aus dieser Quelle und fügt sie der globalen Datenbank hinzu. Dabei wird für jede Detection geprüft: Existiert ihr vector_hash schon in der globalen Datenbank? Falls ja, wird nur ein neuer Detection-Eintrag mit Verweis auf die bestehende vector_id angelegt. Falls nein, wird auch der Vektor aus dem lokalen DiskANN geladen und dem globalen DiskANN hinzugefügt.

### 4.3 Hierarchie-Bewusstsein

Das System ist so konzipiert, dass mehrere Ebenen von globalen Datenbanken möglich sind. Angenommen, ein Nutzer hat diese Struktur:

```
alle_projekte/
├── projekt_2024/
│   ├── standort_a/
│   └── standort_b/
└── projekt_2025/
    └── standort_c/
```

Er kann erst in `projekt_2024/` eine globale Datenbank erstellen, die standort_a und standort_b aggregiert. Dann kann er in `alle_projekte/` eine weitere globale Datenbank erstellen. Wenn birdnet-global-sync in `alle_projekte/` läuft, findet es rekursiv die Session-Datenbanken in standort_a, standort_b und standort_c – aber es findet auch die globale Datenbank in `projekt_2024/`.

Hier greift die Stopp-Regel: Wenn das Tool auf `projekt_2024/birdnet_global.db` stößt, rekursiert es nicht weiter in die Unterordner von projekt_2024. Es importiert also standort_c (der noch nicht in einer globalen DB ist), aber nicht standort_a und standort_b (die schon in projekt_2024/birdnet_global.db sind).

Das ist wichtig, damit keine Duplikate entstehen: standort_a wird nur einmal importiert – in projekt_2024/global. Wenn der Nutzer später auch in alle_projekte/global importieren will, könnte er entweder die projekt_2024/global importieren (wir könnten das später als Feature hinzufügen), oder er löscht die projekt_2024/global und lässt alle_projekte/global direkt von den Sessions importieren.

---

## 5. Datenbank-Struktur im Detail

### 5.1 Lokale Session-Datenbank

Die lokale Datenbank (`birdnet_analysis.db`) bleibt weitgehend wie sie ist. Die zentrale Änderung ist die `detections`-Tabelle. Statt einem Feld `embedding_idx` gibt es jetzt zwei Felder: `vector_id` (die ID im DiskANN-Index) und `vector_hash` (der SHA256-Hash des Vektors).

Die vector_id wird direkt vom DiskANN-Index zurückgegeben, wenn ein Vektor hinzugefügt wird. Sie ist immer eine nicht-negative Ganzzahl, beginnend bei 0, fortlaufend ohne Lücken. Wenn eine Detection keine Embeddings hat (weil --extract-embeddings nicht verwendet wurde), ist vector_id NULL.

Der vector_hash wird einmal beim Einfügen berechnet. Die Berechnung erfolgt über: `hashlib.sha256(embedding.tobytes()).hexdigest()`. Das gibt einen 64-Zeichen-String zurück. Dieser Hash ist unveränderlich und wird nie neu berechnet – er ist quasi der Fingerabdruck des Vektors.

Die neue `db_version`-Tabelle enthält Metadaten über die Datenbank selbst. Sie hat nur zwei Spalten: `key` und `value`, beide Text. Wichtige Einträge sind:
- `db_type`: "session" (markiert diese als lokale Datenbank)
- `schema_version`: "1.0" (Version des Schema)
- `diskann_version`: Die Version der DiskANN-Library, mit der der Index erstellt wurde
- `created_at`: ISO-Timestamp der Erstellung

### 5.2 Globale Aggregations-Datenbank

Die globale Datenbank (`birdnet_global.db`) hat eine andere Struktur. Ihre `detections`-Tabelle enthält nicht nur die Detection-Daten selbst, sondern auch Informationen über die Herkunft:

Jede Detection hat ein Feld `source_db`, das den relativen Pfad zur Quell-Datenbank speichert (z.B. "standort_a_2024/birdnet_analysis.db"). Dadurch kann man später nachvollziehen: Diese Detection kam ursprünglich aus standort_a.

Zusätzlich gibt es ein Feld `source_detection_id` – die ID, die diese Detection in ihrer Quell-Datenbank hatte. Das ermöglicht eine vollständige Rückverfolgung: Wenn ich in der globalen Datenbank eine interessante Detection finde, kann ich über source_db und source_detection_id zur Original-Detection in der lokalen Datenbank navigieren.

Die Felder `vector_id` und `vector_hash` haben die gleiche Bedeutung wie in der lokalen Datenbank – nur dass vector_id hier auf den globalen DiskANN-Index verweist. Wichtig: Der vector_hash ist identisch zum Hash in der Quell-Datenbank. Das ist der Schlüssel zur Deduplizierung.

Die `source_dbs`-Tabelle ist neu und dient dem Sync-Tracking. Für jede Quell-Datenbank, die jemals importiert wurde, gibt es einen Eintrag. Das `db_checksum`-Feld speichert einen Hash über den gesamten Inhalt der Quell-Datenbank (genauer: über alle Detection-IDs, vector_hashes und Timestamps). Wenn dieser Hash sich nicht ändert, hat sich nichts Relevantes geändert, und diese Quelle kann beim nächsten Sync übersprungen werden.

Die `db_version`-Tabelle ist analog zur lokalen Datenbank, nur dass `db_type` hier "global" ist.

---

## 6. Technische Details zu DiskANN

### 6.1 Warum DiskANN und nicht andere Technologien?

Es gibt viele Vektordatenbank-Technologien: FAISS, Annoy, Milvus, Qdrant, ChromaDB. Die Wahl von DiskANN basiert auf mehreren Überlegungen:

DiskANN ist speziell für disk-basierte Speicherung optimiert. Das ist wichtig, weil biologische Projekte oft auf Servern mit begrenztem RAM, aber viel SSD-Speicher laufen. DiskANN kann Milliarden von Vektoren verwalten, ohne sie alle in den RAM laden zu müssen. Der Index ist so strukturiert, dass nur die relevanten Teile geladen werden, wenn eine Suche durchgeführt wird.

DiskANN ist Open Source und hat Python-Bindings über PyPI. Die Integration ist also straightforward – keine komplizierte Installation oder separate Server-Prozesse. Ein einfaches `pip install diskannpy` reicht.

DiskANN skaliert exzellent: Die Suchgeschwindigkeit degradiert nur logarithmisch mit der Anzahl der Vektoren. Eine Suche über 1 Million Vektoren ist nur unwesentlich langsamer als über 100.000. Das ist wichtig, weil globale Datenbanken schnell sehr groß werden können.

### 6.2 Index-Aufbau und -Verwaltung

Ein DiskANN-Index ist kein einzelnes File, sondern eine Ordner-Struktur mit mehreren Dateien. Daher die Notation `birdnet_vectors.diskann/` (mit Slash am Ende, um zu signalisieren: Das ist ein Ordner).

Beim erstmaligen Erstellen wird der Index mit bestimmten Parametern initialisiert: Dimensionalität (1024), Distanz-Metrik (Cosinus-Ähnlichkeit), maximale Anzahl von Nachbarn im Index-Graph, etc. Diese Parameter werden in einer Metadaten-Datei im Index-Ordner gespeichert.

Vektoren werden dem Index einzeln oder in Batches hinzugefügt. DiskANN baut intern eine Graph-Struktur auf, die für schnelle Navigation während der Suche optimiert ist. Wichtig: Der Index muss periodisch "konsolidiert" werden – ein Prozess, der die Graph-Struktur optimiert. Das geschieht nicht nach jedem eingefügten Vektor, sondern in größeren Intervallen (z.B. nach 10.000 neuen Vektoren).

Für unseren Anwendungsfall bedeutet das: Wenn birdnet-walker einen neuen Ordner analysiert und 500 Detections findet, fügt er 500 Vektoren zum Index hinzu. Nach Abschluss der Analyse wird einmal eine Index-Konsolidierung durchgeführt. Das ist ein kurzer Prozess (wenige Sekunden), der sicherstellt, dass der Index optimal für Suchen ist.

### 6.3 Persistenz und Wiederherstellung

Ein großer Vorteil von DiskANN ist die Persistenz: Der Index liegt komplett auf Disk. Wenn das Programm beendet wird und später neu gestartet wird, kann der Index einfach wieder geöffnet werden – alle Daten sind noch da.

Das ist wichtig für die Resume-Logik von birdnet-walker: Wenn der Walker während der Analyse abstürzt, können beim Neustart die bereits geschriebenen Vektoren im DiskANN-Index verbleiben. Der Walker muss nur in der SQLite-Datenbank prüfen, welche Files schon vollständig verarbeitet wurden, und kann dann dort weitermachen.

Es gibt allerdings eine Besonderheit: DiskANN unterstützt kein echtes "Löschen" von Vektoren. Wenn ein Vektor einmal hinzugefügt wurde, kann er nicht mehr entfernt werden. Man kann nur den gesamten Index neu aufbauen. Für unseren Anwendungsfall ist das kein Problem: Wir löschen nie Detections. Wenn eine Detection als fehlerhaft markiert wird, bleibt sie in der Datenbank (mit einer entsprechenden Markierung), aber der Vektor bleibt ebenfalls im Index.

---

## 7. Workflow für den Nutzer

### 7.1 Neue Aufnahmen analysieren (wie bisher)

Der grundlegende Workflow ändert sich für den Nutzer fast gar nicht. Wie bisher ruft er `birdnet-walker /pfad/zu/ordner --extract-embeddings` auf. Das Programm läuft durch, analysiert alle WAV-Files, und erstellt eine Datenbank.

Der einzige sichtbare Unterschied: Statt einer `birdnet_embeddings.h5` Datei gibt es jetzt einen `birdnet_vectors.diskann/` Ordner. Intern passiert natürlich viel mehr, aber für den Nutzer ist das transparent.

Auch die Resume-Funktion funktioniert wie bisher: Wenn der Walker abbricht und neu gestartet wird, analysiert er nur die Files, die noch nicht den Status "completed" in der `processing_status`-Tabelle haben.

### 7.2 Globale Datenbank erstellen (neu)

Wenn der Nutzer mehrere Sessions analysiert hat und diese nun aggregieren möchte, navigiert er in den übergeordneten Ordner und ruft das neue Tool auf:

```bash
cd /pfad/zu/projekt_2024
birdnet-global-sync .
```

Das Tool scannt, findet alle Session-Datenbanken, und erstellt eine `birdnet_global.db` und `birdnet_vectors_global.diskann/` im aktuellen Ordner. Der Nutzer sieht einen Progress-Balken mit der Anzahl importierter Sessions und Detections.

Das Schöne: Dieser Befehl ist idempotent. Wenn der Nutzer ihn später nochmal aufruft (z.B. weil neue Sessions hinzugekommen sind), importiert das Tool nur die neuen Daten. Bereits importierte Sessions werden übersprungen (wenn sich ihr Checksum nicht geändert hat).

### 7.3 Cross-Site-Analysen durchführen (zukünftig)

Die globale Datenbank ist die Grundlage für zukünftige Analyse-Tools. Ein Nutzer könnte beispielsweise ein Python-Script schreiben (oder wir entwickeln später ein Tool dafür), das folgendes macht:

1. Lade alle Detections einer bestimmten Art aus der globalen Datenbank
2. Lade die zugehörigen Vektoren aus dem globalen DiskANN-Index
3. Führe ein Clustering auf diesen Vektoren durch (z.B. DBSCAN)
4. Zeige dem Nutzer: "Ich habe 5 Cluster gefunden. Cluster 3 ist klein und hat niedrige Confidence – möglicherweise Fehlklassifikationen"

Oder ein anderes Szenario: Der Nutzer hat in Session A einen verdächtigen Cluster gefunden. Er kann nun eine Nearest-Neighbor-Suche in der globalen Datenbank durchführen: "Finde alle Detections, deren Vektoren dem Durchschnittsvektor dieses Clusters ähnlich sind". Das System findet dann ähnliche Detections in allen anderen Sessions, die der Nutzer sich dann anhören und validieren kann.

Das ist die Vision: Die globale Datenbank ist nicht das Endziel, sondern die Infrastruktur, die solche übergreifenden Analysen erst ermöglicht.

---

## 8. Migration bestehender Datenbanken

### 8.1 Umgang mit alten HDF5-basierten Datenbanken

Es wird Nutzer geben, die bereits mit dem aktuellen System gearbeitet und HDF5-basierte Datenbanken erstellt haben. Diese sollen natürlich nicht einfach unbrauchbar werden. Es gibt mehrere Strategien:

Die einfachste: Alte Datenbanken bleiben funktional für Read-Only-Zugriff. Tools wie birdnet-play können weiterhin alte Datenbanken öffnen und die Embeddings aus HDF5 lesen. Sie müssen nur in der Lage sein zu erkennen: Hat diese Datenbank eine `db_version`-Tabelle? Falls nein, ist es eine alte Datenbank, und Embeddings liegen in HDF5.

Für Nutzer, die ihre alten Datenbanken in das neue Format konvertieren wollen, könnte ein Migrations-Script entwickelt werden: `birdnet-migrate-to-diskann /pfad/zu/alter/db`. Dieses Script würde:
1. Die HDF5-Datei öffnen und alle Embeddings laden
2. Einen neuen DiskANN-Index erstellen
3. Alle Embeddings in DiskANN schreiben (dabei die IDs notieren)
4. Die `detections`-Tabelle updaten: `embedding_idx` umbennen zu `vector_id`, `vector_hash` berechnen und hinzufügen
5. Die `db_version`-Tabelle erstellen
6. Optional: Die alte HDF5-Datei in ein Backup umbenennen

Das wäre ein einmaliger Prozess pro Datenbank. Danach ist die Datenbank vollständig kompatibel mit dem neuen System.

### 8.2 Abwärtskompatibilität in birdnet-play

Das birdnet-play Tool (und andere Lese-Tools) sollten so erweitert werden, dass sie beide Formate verstehen. Die Erkennungs-Logik könnte so aussehen:

Beim Öffnen einer Datenbank: Prüfe, ob es eine `db_version`-Tabelle gibt. Falls ja, lies den `db_type` und `schema_version`. Falls `db_type == "session"` und `schema_version >= "1.0"`, nutze DiskANN. Falls die Tabelle nicht existiert, nutze HDF5.

In der Praxis würde das bedeuten: In allen Funktionen, die Embeddings laden, gibt es zwei Code-Pfade:

```python
if db_has_diskann(db_path):
    embedding = load_from_diskann(db_path, vector_id)
else:
    embedding = load_from_hdf5(db_path, embedding_idx)
```

Das ist etwas redundant, aber es ermöglicht einen sanften Übergang ohne Breaking Changes.

---

## 9. Offene Fragen und Entscheidungen

### 9.1 DiskANN-Parameter

Es gibt diverse Parameter beim Erstellen eines DiskANN-Index: Anzahl der Nachbarn im Graph, Distanz-Metrik, Konsolidierungs-Intervalle. Wir müssen sinnvolle Defaults wählen, die für typische biologische Projekte (Größenordnung: 10.000 bis 1.000.000 Detections pro Session) gut funktionieren.

Die Distanz-Metrik sollte Cosine-Similarity sein, da wir an der Richtung der Vektoren interessiert sind, nicht an ihrer absoluten Magnitude. Das ist bei Embeddings aus neuronalen Netzen üblich.

Die Anzahl der Nachbarn im Index-Graph beeinflusst den Trade-off zwischen Suchgeschwindigkeit und Genauigkeit. Ein höherer Wert bedeutet langsameren Aufbau, aber präzisere Suchen. Für unseren Anwendungsfall (wo Recall wichtiger ist als absolute Geschwindigkeit) sollten wir eher großzügig dimensionieren.

Konkrete Werte müssen experimentell ermittelt werden – idealerweise mit realen Datenbanken aus Testprojekten.

### 9.2 Performance-Überlegungen

Ein DiskANN-Index ist schnell für Suchen, aber langsamer beim Aufbau als HDF5. Das Schreiben von 500 Embeddings in HDF5 dauert Millisekunden. Das Hinzufügen von 500 Vektoren zu DiskANN plus anschließende Konsolidierung kann mehrere Sekunden dauern.

Für den normalen Workflow (ein Ordner analysieren, dann fertig) ist das unkritisch – ein paar Sekunden zusätzliche Wartezeit am Ende der Analyse fallen nicht ins Gewicht. Aber für sehr große Batch-Jobs (hunderte Ordner) könnte sich das summieren.

Eine mögliche Optimierung: Batch-Inserts in DiskANN. Statt jeden Vektor einzeln hinzuzufügen, sammeln wir alle Vektoren eines Files und fügen sie als Batch hinzu. DiskANN kann dann einmal den Index aktualisieren statt 500 mal. Das müsste in der Implementierung berücksichtigt werden.

### 9.3 Fehlerbehandlung bei korrupten Indices

Was passiert, wenn ein DiskANN-Index korrupt wird (z.B. durch Absturz während des Schreibens)? Im Gegensatz zu HDF5, wo man einfach die letzte gültige Version wiederherstellen kann, ist DiskANN weniger fehlertolerant.

Ein möglicher Ansatz: Backup des Index vor jeder größeren Operation. Wenn birdnet-walker 100 neue Files analysiert, wird vor dem ersten Insert ein Snapshot des aktuellen Index-Zustands gemacht. Falls während der Verarbeitung etwas schiefgeht, kann der Index auf den Snapshot zurückgesetzt werden.

Alternativ: Der Index ist als "expendable" zu betrachten – er kann jederzeit aus den Daten in der SQLite-Datenbank neu aufgebaut werden. Die SQLite-Datenbank ist die "Single Source of Truth", und der DiskANN-Index ist nur ein beschleunigender Cache. Wenn der Index korrupt ist, löschen wir ihn und bauen ihn neu aus der SQLite-Datenbank.

Das würde bedeuten: In der SQLite-Datenbank müssen die Embeddings selbst auch gespeichert werden, nicht nur die vector_ids. Oder wir speichern die Embeddings in einem separaten, robusten Format (z.B. als BLOB in einer weiteren SQLite-Tabelle), und der DiskANN-Index ist rein sekundär.

### 9.4 Umgang mit sehr großen Datenmengen

Was passiert, wenn eine globale Datenbank 10 Millionen Detections hat? DiskANN kann das theoretisch handhaben, aber praktische Aspekte müssen bedacht werden:

Die SQLite-Datenbank mit 10 Millionen Zeilen in der `detections`-Tabelle ist mehrere Gigabyte groß. Queries können langsam werden, wenn nicht richtig indiziert. Wir müssen sicherstellen, dass alle relevanten Spalten (insbesondere `vector_hash` für die Deduplizierungs-Lookups) gut indiziert sind.

Der DiskANN-Index mit 10 Millionen Vektoren (je 1024 * 4 Bytes = 4 KB) ist etwa 40 GB groß (plus Index-Overhead). Das passt problemlos auf moderne SSDs, aber das Laden und Konsolidieren kann Minuten dauern. Wir sollten dem Nutzer klare Fortschrittsanzeigen geben.

Eine mögliche Optimierung für Experten-Nutzer: Sharding. Die globale Datenbank könnte aufgeteilt werden in mehrere Shards (z.B. nach Jahr oder Standort). Jeder Shard ist eine separate globale Datenbank. Bei Suchen werden dann parallel mehrere Shards durchsucht. Das ist aber ein fortgeschrittenes Feature für später.

---

## 10. Implementierungsstrategie

### 10.1 Schrittweise Einführung

Die Umstellung sollte nicht in einem großen Bang passieren, sondern schrittweise. Ein möglicher Fahrplan:

**Phase 1: Lokale DiskANN-Unterstützung in birdnet-walker**

Zunächst wird nur der birdnet-walker angepasst. Er schreibt Embeddings in DiskANN statt HDF5, und die `detections`-Tabelle bekommt `vector_id` und `vector_hash`. Die `db_version`-Tabelle wird eingeführt. Alte HDF5-Unterstützung bleibt parallel erhalten (als Fallback).

Nutzer können das neue System ausprobieren. Es gibt noch keine globalen Datenbanken, aber die Grundlage ist gelegt.

**Phase 2: birdnet-play Kompatibilität**

Das birdnet-play Tool wird erweitert, um beide Formate zu lesen. Nutzer können sowohl alte HDF5- als auch neue DiskANN-basierte Datenbanken öffnen und durchsuchen. Die Funktionalität bleibt identisch – es ändert sich nur das Backend.

**Phase 3: birdnet-global-sync entwickeln**

Das neue Tool wird entwickelt und getestet. Zunächst in einer Alpha-Version für experimentierfreudige Nutzer. Feedback wird gesammelt: Ist die Sync-Logik intuitiv? Sind die Performance-Charakteristiken akzeptabel?

**Phase 4: Analyse-Tools für globale Datenbanken**

Sobald globale Datenbanken stabil sind, können erste Analyse-Tools entwickelt werden. Das könnte ein neues birdnet-play Page sein: "Cross-Site Clustering". Oder ein separates Command-Line-Tool für Power-User.

**Phase 5: HDF5 deprecaten**

Wenn die DiskANN-Implementierung ausgereift ist und keine kritischen Bugs mehr auftreten, kann HDF5 offiziell als "legacy" markiert werden. Neue Nutzer werden nur noch DiskANN verwenden. Alte Nutzer werden ermutigt zu migrieren, aber es bleibt funktional.

### 10.2 Testing-Strategie

Jede Phase braucht umfassende Tests:

**Unit-Tests** für alle neuen Funktionen: DiskANN-Schreiben, Vector-Hash-Berechnung, Deduplizierungs-Logik, Hierarchie-Scanning. Diese Tests sollten mit kleinen, synthetischen Datenbanken arbeiten.

**Integration-Tests** mit realen Daten: Ein Testdatensatz mit echten AudioMoth-Aufnahmen (z.B. 100 Files à 6 Stunden) wird durch den kompletten Workflow geschickt: birdnet-walker Analyse, globale Datenbank erstellen, Suchen durchführen. Die Ergebnisse werden gegen bekannte Ground-Truth validiert.

**Performance-Tests**: Wie lange dauert die Analyse von 1000 Files? Wie lange das Erstellen einer globalen Datenbank mit 500.000 Detections? Wie schnell sind Nearest-Neighbor-Suchen über 1 Million Vektoren? Diese Metriken müssen dokumentiert werden, damit Nutzer realistische Erwartungen haben.

**Stress-Tests**: Was passiert bei extremen Szenarien? 10 Millionen Detections? 1000 Session-Datenbanken gleichzeitig importieren? Ein Ordner mit 100 GB an Audiodaten? Das System sollte nicht abstürzen, sondern entweder erfolgreich durchlaufen oder mit klaren Fehlermeldungen abbrechen.

### 10.3 Dokumentation und Nutzer-Kommunikation

Die Änderungen müssen klar dokumentiert werden:

Ein **Migration Guide** erklärt Nutzern, die bereits HDF5-Datenbanken haben, wie sie migrieren können. Schritt-für-Schritt-Anleitung mit Screenshots.

Ein **Tutorial für birdnet-global-sync**: Wie erstellt man seine erste globale Datenbank? Welche Ordnerstruktur macht Sinn? Wie interpretiert man die Ausgabe?

Ein **Technisches Deep-Dive-Dokument** (dieses hier) für fortgeschrittene Nutzer und zukünftige Entwickler, die das System verstehen und erweitern wollen.

**Changelog-Einträge** in der Haupt-Dokumentation: Version 0.4.0 bringt hierarchische Vektordatenbanken. Was ist neu? Was ändert sich? Was bleibt gleich?

---

## 11. Zusammenfassung und Ausblick

### 11.1 Kernpunkte der neuen Architektur

Das neue System führt ein hierarchisches Modell ein: Lokale Session-Datenbanken bleiben das Fundament – erstellt vom birdnet-walker wie bisher. Aber jetzt können diese Sessions in übergeordneten Ordnern zu globalen Datenbanken aggregiert werden. Diese Aggregation ist dedupliziert, effizient, und inkrementell.

Der Wechsel von HDF5 zu DiskANN bringt Nearest-Neighbor-Suche auf Milliarden von Vektoren in den Sekundenbereich. Das ermöglicht vollkommen neue Analysen: Cross-Site Pattern Recognition, False-Positive-Detection über alle Sessions, Ruftyp-Klassifikation über verschiedene Standorte hinweg.

Die Architektur ist so entworfen, dass sie sich natürlich an die Arbeitsweise von Biologen anpasst: Ordner entsprechen logischen Einheiten (Standort, Jahr, Projekt). Das System nutzt diese Struktur, ohne sie zu erzwingen. Ein Nutzer kann weiterhin mit einzelnen Ordnern arbeiten, wenn er will. Globale Datenbanken sind opt-in, nicht obligatorisch.

### 11.2 Was das für den wissenschaftlichen Workflow bedeutet

Für einen Biologen ändert sich der grundlegende Workflow kaum: Aufnahmen machen, mit birdnet-walker analysieren, mit birdnet-play durchsehen. Alles wie bisher.

Aber es kommen neue Möglichkeiten hinzu: Nach der Analyse mehrerer Sessions kann er mit einem einzigen Befehl eine globale Datenbank erstellen. Diese ist nicht nur eine Zusammenfassung der Daten, sondern eine durchsuchbare Wissensbasis über alle seine Aufnahmen.

Ein konkretes Szenario: Ein Biologe untersucht Kohlmeisen-Populationen an 20 Standorten über 3 Jahre. Das sind 60 Session-Datenbanken. Mit dem neuen System kann er:

1. Eine globale Datenbank erstellen, die alle 60 Sessions aggregiert
2. Alle Kohlmeisen-Detections aus dieser Datenbank laden (möglicherweise 100.000 Detections)
3. Die zugehörigen Embeddings clustern und visualisieren
4. Entdecken: Es gibt einen Cluster mit 500 Detections, die BirdNET als Kohlmeise klassifiziert, aber akustisch sehr unterschiedlich sind
5. Diese 500 Detections anhören und feststellen: Das sind tatsächlich Blaumeisen, die BirdNET falsch zugeordnet hat
6. Alle 500 Detections in der globalen Datenbank korrigieren
7. Die Korrektur propagiert in die lokalen Datenbanken (via einem noch zu entwickelnden Tool)

Das ist systematische Qualitätssicherung auf einer Ebene, die mit dem alten System praktisch unmöglich war.

### 11.3 Zukünftige Erweiterungen

Die hierarchischen Vektordatenbanken sind eine Plattform für viele weitere Features:

**Automatische Anomalie-Detection**: Ein Tool, das automatisch alle Detections mit ungewöhnlichen Embeddings identifiziert. "Diese 50 Detections passen nicht zu ihren Art-Clustern – bitte manuell prüfen."

**Ruftyp-Bibliothek**: Nutzer können annotierte Cluster teilen. "Dieser Cluster sind Kohlmeisen-Bettelrufe von Jungvögeln." Diese Annotationen werden in einer Community-Datenbank gesammelt. Neue Nutzer können dann ihre Daten gegen diese Bibliothek matchen: "Du hast einen Cluster, der bekannten Bettelrufen ähnelt."

**Multi-Taxa-Erweiterung**: Das Konzept funktioniert nicht nur für Vögel. Fledermäuse (mit BatDetect), Amphibien, Heuschrecken – jedes akustisch erfassbare Taxon könnte das gleiche System nutzen. Die Vektordatenbanken sind unabhängig vom Modell, das die Embeddings erzeugt.

**Echtzeit-Monitoring**: Mit entsprechender Hardware könnte das System im Feld laufen. Neue Aufnahmen werden sofort analysiert, Embeddings werden in die lokale Datenbank geschrieben. Wenn eine Detection einer bekannten Anomalie-Signatur ähnelt, wird eine Warnung gesendet: "Mögliche seltene Art entdeckt, Position X."

### 11.4 Schlussbemerkung

Diese Architektur ist ambitioniert, aber pragmatisch. Sie baut auf dem auf, was bereits funktioniert (birdnet-walker, SQLite, BirdNET), und erweitert es um eine Dimension, die in der biologischen Praxis oft fehlt: die Fähigkeit, systematisch über viele Datensätze hinweg zu denken.

Die Implementierung wird Zeit brauchen. Aber das Ergebnis – ein System, das Biologen hilft, aus ihren Daten nicht nur Listen von Detections, sondern echtes Wissen zu extrahieren – ist den Aufwand wert.

---

**Ende des Konzeptdokuments**