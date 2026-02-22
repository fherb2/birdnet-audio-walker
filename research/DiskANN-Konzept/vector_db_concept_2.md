# Konzept: Hierarchisches Vektordatenbank-System mit DiskANN

**Version:** 2.1 (Final)  
**Datum:** 10. Februar 2026  
**Status:** Implementierungsbereit  

---

## 1. Überblick und Motivation

### 1.1 Die zentrale Idee

Das bestehende BirdNET-Walker-System speichert neben den eigentlichen Artenerkennungen in Audiofiles in einer SQLite-Datenbank derzeit für jeden Aufnahme-Ordner eine separate HDF5-Datei mit Embedding-Vektoren. Diese Embeddings sind 1024-dimensionale Feature-Vektoren, die aus dem BirdNET-Modell extrahiert werden und die akustischen Eigenschaften jeder Detection repräsentieren. Das funktioniert gut für die lokale Speicherung zugehörig zu den Audiofiles und Detektionen des Verzeichnisses auf der gleichen Ebene. Aber es gibt ein fundamentales Problem: Die Embeddings sind über viele einzelne Dateien verstreut, wenn es mehrere derartiger Ordner gibt, in denen man die Audiofiles und Detektionen sortiert. Es gibt dann keine Möglichkeit, schnell nach ähnlichen Detections global über alle Aufnahme-Sessions hinweg zu suchen.

Die neue Architektur führt ein hierarchisches System ein, bei dem Vektordatenbanken auf verschiedenen Ebenen existieren können. Eine lokale Vektordatenbank liegt direkt bei den Audiofiles und speichert alle Embeddings dieser Session. Übergeordnete Ordner können globale Vektordatenbanken enthalten, die automatisch alle Embeddings aus untergeordneten Sessions aggregieren. Auch die Erkennungen werden entsprechend globaler zusammengeführt.

### 1.2 Warum DiskANN als Embedding-Vektor Datenbank?

Der Wechsel von HDF5 zu DiskANN hat einen spezifischen Grund: DiskANN ist eine Vektordatenbank-Technologie von Microsoft Research, die speziell dafür entwickelt wurde, Milliarden von hochdimensionalen Vektoren effizient auf SSDs zu speichern und schnelle Nearest-Neighbor-Suchen zu ermöglichen. Im Gegensatz zu HDF5, das eine reine Speichertechnologie ist, baut DiskANN einen Index auf, der Ähnlichkeitssuchen dramatisch beschleunigt, ohne gezwungen zu sein, die Daten im Ganzen im Arbeitsspeicher zu halten.

Das ist entscheidend für die biologische Fragestellung: Ein Nutzer hat vielleicht in einer Session einen Cluster von Detections gefunden, der wie eine Fehlklassifikation aussieht. Mit DiskANN kann er fragen: "Finde alle ähnlichen Detections in allen meinen anderen Sessions". Diese Query würde über potentiell Millionen von Vektoren laufen und muss trotzdem in wenigen Sekunden Ergebnisse liefern. Weder HDF5, noch Zarr noch eine SQL-Datenbank kann das leisten – man müsste alle Vektoren laden und manuell Distanzen berechnen, was bei großen Datenmengen völlig unpraktikabel ist.

### 1.3 Die biologische Perspektive

Aus biologischer Sicht ist das System so konzipiert, dass die Embeddings modell-intrinsisch sind, nicht standort-spezifisch. Das bedeutet: Ein Kohlmeisen-Reviergesang hat überall ähnliche Embeddings, egal wo er aufgenommen wurde. Sofern das gleiche Modell zur Erkennung (BirdNET der gleichen Version) verwendet wurde. Wenn BirdNET einen Blaumeisen-Ruf fälschlicherweise als Kohlmeise klassifiziert, wird dieser Fehler ebenfalls überall ähnliche Embeddings produzieren.

Das ermöglicht systematische Qualitätskontrolle: Einmal einen Fehler identifiziert, können alle ähnlichen Fälle in allen Sessions gefunden und korrigiert werden. Das ist der Kern des Mehrwerts – nicht nur lokale Analyse, sondern cross-site Pattern Recognition. Es ist auch die Ausgangsbasis dafür, durch die Erweiterung des Modells solche "Schwächen" auszumerzen.

---

## 2. Architektur-Überblick

### 2.1 Das hierarchische Prinzip

Die neue Architektur basiert auf einem einfachen Prinzip: Jede Datenbank (ob lokal oder global) besteht aus genau zwei Komponenten – einer SQLite-Datei und einem DiskANN-Index. Die Benennung dieser Dateien signalisiert automatisch ihren Typ:

Lokale Datenbanken bei den Audiofiles heißen `birdnet_analysis.db` und haben einen zugehörigen DiskANN-Index `birdnet_vectors.diskann/`. Diese lokalen Datenbanken werden vom bestehenden birdnet-walker erstellt und enthalten alle Detections und Embeddings einer Aufnahme-Session, die als Ordner im Dateisystem abgebildet ist.

Globale Datenbanken in übergeordneten Ordnern heißen `birdnet_global.db` und haben einen Index `birdnet_vectors_global.diskann/`. Da der birdnet-walker dafür ausgelegt ist, ganze Ordnerstrukturen rekursiv zu durchsuchen und neue Daten zu sammeln (neue Ordner oder neue Audio-Dateien in Ordnern), wird dieser im Rahmen dieses Konzepts um die globale Methodik erweitert. Freigeschaltet wird diese Option durch die Option -g / --global.

Um es nochmal zusammenzustellen:

* ohne die Optionen -r/--recursive oder/und -g/--global: es wird nur der aktuelle Ordner, der als Pfad übergeben wird, durchsucht und die lokalen Datenbanken (`birdnet_analysis.db` und `birdnet_vectors.diskann/`) werden angelegt oder mit den Ergebnissen noch nicht bearbeiteter Audiofiles erweitert.
* mit Option -r/--recursive: Es werden ab dem angegebenen Pfad alles in diesem Ordner und darunter durchsucht und dort die einzelnen Datenbanken angelegt bzw. erweitert.
* mit Option -g/--global (egal, ob -r/--recursive angegeben ist): Es werden die gleichen Operationen recursiv ausgeführt, wie mit der Option -r/--recursive, zusätzlich wird auf der obersten Ebene (also der, die als Pfad angegeben wurde) eine globale Datenbank `birdnet_global.db` und `birdnet_vectors_global.diskann/` angelegt beziehungsweise erweitert.

Die Embedding-Vektoren werden dabei in allen Fällen nur gesammelt, wenn das mit dem zusätzlichen Argument --extract-embeddings gefordert wird!

Zu bemerken ist, dass im bisherigen Zustand aber auch für die neue Funktion gilt: Es wird nicht doppelt indiziert. Immer nur neue Audios bzw. ganze neue Ordner mit Audios werden als neu erkannt, dann mit BirdNET analysiert und dann die Daten lokal (im Ordner der Audio-Datei) und zusätzlich in der globalen Datenbank (ganz oben liegenden Datenbank) zugefügt.

Der Clou: Globale Datenbanken können damit im Prinzip beliebig tief verschachtelt werden. Ein Ordner "projekt_2024" kann eine globale Datenbank haben, die alle Standorte dieses Jahres aggregiert. Ein Ordner "alle_projekte" kann darüber liegend eine weitere globale Datenbank hat, die mehrere Jahre aggregiert. Für diesen Fall startet man den birdnet-walker beginnend von "unten" in mehreren Ebenen. Lokale Datenbanken werden nur einmal erstellt, da auch bei einer Analyse aus einer "oberen Etage" die Erkennungsdaten weiter unten erkannt werden und nicht nochmal eine Erkennung beginnt. Es wird dann immer geprüft, welche Daten in den jeweiligen Ebenen neu sind und in der Ausgangsebene der recursiven Suche gesammelt.

### 2.2 Datenfluss im neuen System

Der Nutzer analysiert einen Ordner oder ein geschachteltes Ordnersystem mit Audiofiles, und der Walker erstellt eine lokale SQLite-Datenbank mit allen Detections und den Embeddings (wenn embeddings aktiviert sind) in jedem Ordner. Wenn Embeddings aktiviert sind, extrahiert der Walker für jedes Zeitsegment, in denen eine oder mehrere Species detektiert wurden, einen 1024-dimensionalen Vektor. Diese Vektoren werden **in einer SQLite-Tabelle als BLOB gespeichert** (primäre Datensicherung) sowie ein Hash daraus ermittelt der ebenfalls zum Blob zugehörig gespeichert wird (dient als zusätzlicher Schutz gegen mehrfach-Ablage des gleichen Vektors). Parallel wird mit dem Vektor redundant ein DiskANN-Index aufgebaut (für schnelle Ähnlichkeitssuchen).

Der DiskANN-Index ist eine Ordner-Struktur (daher die `.diskann/` Notation), die mehrere Dateien enthält: Den eigentlichen Vektor-Speicher, die Index-Struktur für schnelle Suchen, und Metadaten. Der Walker fügt jeden Vektor hinzu und bekommt eine vector_id zurück – eine fortlaufende Nummer, die in der SQLite-Datenbank a) bei den zum Zeitsegment gehörenden Detections und b) auch in der Vektor-Blob-Tabelle als Reference gespeichert wird.

Über einen Hash-Mechanismus, der in der zugehörigen SQLite-Datenbank referenziert mitgespeichert wird, ist sichergestellt, dass keine Duplikate in der SQL-Datenbank, wie auch in der DiskANN abgelegt werden: Wenn derselbe Audio-Schnipsel tatsächlich mehrfach analysiert wurde, wird sein Embedding nur einmal in der lokalen, wie globalen DiskANN Datenbank gespeichert.

### 2.3 Deduplizierung über Hash-Werte

Abgesehen davon, dass in den SQL-Datenbanken gespeichert ist, welche Audiofiles bereits analysiert wurden, da sie ja auch als Backreferenz für die Audioschnipsel der Erkennungen dienen, soll zur Absicherung, in die DiskANN keine Vektoren doppelt einzutragen, ein Hash über die eingetragenen Vektoren in der SQLite gespeichert werden. Die Deduplizierung funktioniert über einen vector_hash, der für jeden Embedding-Vektor berechnet wird. Dieser Hash ist ein SHA256 über das float32-Array des Vektors. Da Embeddings deterministisch sind (gleiches Audio → gleicher Vektor), haben identische Detections auch identische Hashes.

Sowohl der Hash als auch der komplette Vektor selbst als Blob und die Back-Referenz-ID aus der Indizierung in der DiskANN werden in der SQLite-Tabelle `embeddings` gespeichert.

---

## 3. Änderungen am bestehenden Code

### 3.1 Migration von HDF5 zu SQLite+DiskANN in birdnet_walker

Der birdnet-walker muss in mehreren Modulen angepasst werden, aber die grundlegende Logik bleibt erhalten. Die Hauptänderung betrifft die Art, wie Embeddings gespeichert werden.

Im aktuellen System gibt es eine Funktion `write_embeddings_to_hdf5()`, die ein numpy-Array von Embeddings nimmt und in eine HDF5-Datei schreibt. Diese Funktion gibt einen Start-Index zurück, der dann verwendet wird, um jede Detection mit ihrer Position in der HDF5-Datei zu verknüpfen.

In der neuen Version wird diese Funktion ersetzt durch **zwei Schritte**:

1. **`write_embeddings_to_sqlite()`** – Speichert Vektoren als BLOB in `embeddings`-Tabelle
2. **`add_to_diskann()`** – Fügt Vektoren redundant zum DiskANN-Index hinzu

SQLite ist die primäre Speicherung (Single Source of Truth), DiskANN ist der sekundäre Suchindex.

Vor dem Einfügen wird geprüft, ob der vector_hash bereits existiert. Falls ja, wird die existierende vector_id wiederverwendet. Dies verhindert Duplikate in beiden Systemen (SQLite und DiskANN).

### 3.2 Lokale Datenbanken: Erweiterung der SQLite-Schema

"Lokale Datenbanken" bezeichnet die SQLite- und DiskANN-Datenbank, die ausschließlich Einträge aus Audiofiles im eigenen Ordner enthält. Insbesondere liegen hier auch die Referenzen von den einzelnen Erkennungen und Embedding-Vektoren zum Zeit-Ausschnitt der Audiofiles. In der SQLite-DB liegt auch die Referenz (ID) zum Eintrag eines Embeddingvektors in der lokalen DiskANN-Datenbank.

Im Gegensatz dazu liegen in der globalen Datenbank diese lokalen Informationen nicht noch einmal, sondern dort wird in die lokale Datenbank referenziert. Das bgedeutet aber auch, dass die Dereferenzierung der Daten in der globalen Datenbank nur über die lokalen Datenbanken funktioniert. Es hat aber auch den Vorteil, dass mehrere globale Datenbanken existieren können. Entweder auf mehreren Ebenen, als auch mit unterschiedlichen Parametern bei der DiskANN-Indizierung.

#### Neue Tabelle: embeddings (primäre Vektorspeicherung)

Eine neue Tabelle `embeddings` wird eingeführt, die die Embedding-Vektoren als primäre Datenquelle speichert. Dies ist die "Single Source of Truth" für alle Vektoren:

```sql
CREATE TABLE embeddings (
    vector_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector_hash TEXT UNIQUE NOT NULL,
    embedding BLOB NOT NULL
);

CREATE UNIQUE INDEX idx_vector_hash ON embeddings(vector_hash);
```

**Felder:**
- `vector_id`: Fortlaufende ID (Primärschlüssel), automatisch vergeben, **beginnt bei 1**
- `vector_hash`: SHA256-Hash über den Vektor (64 Zeichen), berechnet via `hashlib.sha256(embedding.tobytes()).hexdigest()`
- `embedding`: Der komplette Vektor als BLOB (4096 Bytes bei 1024 float32-Werten)

**Zweck des Hash:** Deduplizierung. Bevor ein neuer Vektor eingefügt wird, wird geprüft: Existiert dieser Hash schon? Falls ja, wird die existierende `vector_id` wiederverwendet. Falls nein, wird ein neuer Eintrag angelegt.

**Warum BLOB in SQLite?** Falls der DiskANN-Index korrupt wird (durch Absturz, Disk-Fehler), kann er aus dieser Tabelle in wenigen Minuten neu aufgebaut werden, ohne erneute BirdNET-Analyse. SQLite ist die sichere Datenbasis, DiskANN ist der optimierte Suchindex darüber.

#### Änderung der detections-Tabelle

Die `detections`-Tabelle bekommt ein geändertes Feld:

Das bisherige Feld `embedding_idx` (Index in HDF5) wird umbenannt zu `vector_id INTEGER` und verweist nun auf die neue `embeddings`-Tabelle:

```sql
ALTER TABLE detections ADD COLUMN vector_id INTEGER;
ALTER TABLE detections ADD FOREIGN KEY (vector_id) REFERENCES embeddings(vector_id);
```

**Wichtig:** Mehrere Detections können den gleichen `vector_id` haben. Das passiert, wenn BirdNET denselben 3-Sekunden-Audio-Schnipsel als mehrere verschiedene Arten klassifiziert (z.B. Kohlmeise UND Blaumeise im gleichen Segment). Der Vektor wird nur einmal gespeichert, beide Detections referenzieren ihn.

Wenn `--extract-embeddings` nicht verwendet wurde, ist `vector_id` NULL.

### 3.3 Globale Datenbank

Parallel zur Ablage in der lokalen SQLite und DiskANN müssen die Information bei gewählter -g/--global Option in der globalen Datenbank abgelegt werden. Diese globale Datenbank liegt im Einmstiegsordner für das recursiven Abarbeiten der Ordner und Files. Falls in diesem Einstiegsordner ebenfalls Audiofiles liegen, werden die natürlich ebenso indiziert und in einer "lokalen" Datenbank eingetragen. Allerdings werden auch diese Daten in die im glkeichen Ordner liegende globale Datenbank eingetragen.

Die globale Datenbank, ebenfalls aus einer SQLite und einer DiskANN-Datenbank bestehend, ist leicht anders strukturiert.

#### 3.3.1 SQLite-Datenbank

Da die Indices aus der globalen DiskANN nicht in die lokalen SQLite-DBs eingetragen wird, benötigen wir eine "Vermittlungsstelle", um die DiskANN Indices bezüglich Audiofile, Zeitsegment und Species in Verbindung zu bringen. Jeder Index aus der globalen DiskANN, der ja einen Embedding-Vektor repräsentiert, wird hier referenziert auf:

- den Ordner, in dem sich das zugehörige Audiofile und damit auch die lokalen SQLIte-Datenbank befindet, aus 
- der u.a. auch das zugehörige Zeitintervall gespeichert ist und
- sich mit dem Hash der Index des dort ebenso gespeicherten Embedding-Vektors und dessen SQLite-ID bestimmen lässt,
- mit der sich dann dort alle damit identifizierten Species ermitteln lässt.
- Zur Sicherheit und zum schnellen Prüfen beim Zufügen der Embedding-Vektoren wird auch hier eine Hashtabelle geführt. Sie dient nur dem Vorgang der Vektor-Indizierung als letzte Absicherung gegen dopplter Indizierung.

#### 3.3.2 DiskANN

Die globale DB bekommt alle Embeddings-Vektoren und der zurück gegebene Index wird in der in 3.3.1 beschriebenen SQLite-DB zu den Quellinformationen Rückreferenziert.

### 3.4 Versionierung über db_version

Um zu tracken, welche Datenbank welches Schema hat, wird eine neue Tabelle `db_version` eingeführt. Diese ist sehr einfach – nur key-value-Paare:

```sql
CREATE TABLE db_version (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO db_version (key, value) VALUES ('db_type', 'session');
INSERT INTO db_version (key, value) VALUES ('schema_version', '1.0');
INSERT INTO db_version (key, value) VALUES ('diskann_version', '0.7.0');
```

Damit kann jedes Tool, das eine Datenbank öffnet, sofort erkennen: Ist das eine alte Datenbank? Dann muss ich anders damit umgehen. Ist das eine globale Datenbank? Dann weiß ich, dass die Struktur anders ist.

Das ermöglicht zukünftige Migrationen (im Moment noch nicht nötig, da alles noch in Entwicklung der 1. Version): Wenn wir später das Schema ändern, können wir die schema_version hochzählen und automatische Migrations-Scripts schreiben.

---

## 4 - entfällt

---

## 5. Datenbank-Struktur im Detail

### 5.1 Lokale Session-Datenbank

Die lokale Datenbank (`birdnet_analysis.db`) erweitert das bestehende Schema um zwei neue Tabellen: `embeddings` und `db_version`. Alle anderen Tabellen (`metadata`, `processing_status`, `analysis_config`, `species_list`) bleiben unverändert.

#### Vollständiges Schema (nur neue/geänderte Teile)

```sql
-- NEUE Tabelle: Embedding-Vektoren (primäre Speicherung)
CREATE TABLE embeddings (
    vector_id INTEGER PRIMARY KEY,  -- KEIN AUTOINCREMENT!
    vector_hash TEXT UNIQUE NOT NULL,
    embedding BLOB NOT NULL
);

CREATE UNIQUE INDEX idx_vector_hash ON embeddings(vector_hash);

-- GEÄNDERTE Tabelle: detections (neues Feld vector_id)
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    segment_start_utc TEXT NOT NULL,
    segment_start_local TEXT NOT NULL,
    segment_end_utc TEXT NOT NULL,
    segment_end_local TEXT NOT NULL,
    timezone TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    local_name TEXT,
    name_cs TEXT,
    confidence REAL NOT NULL,
    vector_id INTEGER,  -- NEU! Verweis auf embeddings-Tabelle (NULL wenn keine Embeddings)
    FOREIGN KEY (filename) REFERENCES metadata(filename),
    FOREIGN KEY (vector_id) REFERENCES embeddings(vector_id)
);

-- NEUE Tabelle: Datenbank-Versionierung
CREATE TABLE db_version (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

#### Datenfluss beim Einfügen

Wenn birdnet-walker ein Embedding extrahiert:

1. **Hash berechnen:** `vector_hash = sha256(embedding_array.tobytes())`
2. **Deduplizierungs-Check:** Prüfe `SELECT vector_id FROM embeddings WHERE vector_hash = ?`
3. **Falls Hash existiert:** Verwende existierende `vector_id`, füge keinen neuen Vektor ein
4. **Falls Hash neu:** 
   - `INSERT INTO embeddings (vector_hash, embedding) VALUES (?, ?)`
   - Erhalte neue `vector_id` via `lastrowid`
   - Füge Vektor auch zu DiskANN hinzu (mit gleicher ID!)
5. **Detection speichern:** `INSERT INTO detections (..., vector_id) VALUES (..., ?)`

#### Beziehung zu DiskANN

Der DiskANN-Index (`birdnet_vectors.diskann/`) speichert die gleichen Vektoren redundant, aber mit optimierter Graph-Struktur für schnelle Nearest-Neighbor-Suchen. 

**Wichtig:** Die `vector_id` in SQLite und die interne ID in DiskANN müssen identisch sein!

**Mapping:** `embeddings.vector_id` = DiskANN internal ID

Bei korruptem DiskANN kann der Index aus der `embeddings`-Tabelle neu gebaut werden (siehe Abschnitt 9.3).

### 5.2 Globale Aggregations-Datenbank

Die globale Datenbank (`birdnet_global.db`) hat eine ähnliche Struktur wie lokale Session-Datenbanken, mit folgenden Unterschieden:

#### Schema-Unterschiede zur lokalen DB

**1. detections-Tabelle:** Statt `filename` (nur Dateiname) enthält sie einen relativen Pfad zum Audio:

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_path TEXT NOT NULL,  -- z.B. "standort_a/20240516_060000.WAV"
    segment_start_utc TEXT NOT NULL,
    -- ... alle anderen Felder wie in lokaler DB ...
    vector_id INTEGER,
    FOREIGN KEY (vector_id) REFERENCES embeddings(vector_id)
);
```

Der `audio_path` ist relativ zur globalen Datenbank. Dadurch bleibt die globale DB portabel, wenn der gesamte Ordnerbaum verschoben wird.

**2. embeddings-Tabelle:** Identisch zur lokalen DB, enthält alle Vektoren aus allen untergeordneten Sessions:

```sql
CREATE TABLE embeddings (
    vector_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector_hash TEXT UNIQUE NOT NULL,
    embedding BLOB NOT NULL
);
```

**Wichtig:** Die Vektoren werden aus den lokalen Datenbanken KOPIERT, nicht referenziert. Die globale DB ist vollständig selbstständig.

**3. db_version-Tabelle:** `db_type = "global"` statt "session"

#### Deduplizierungs-Logik beim Import

Wenn birdnet-walker mit `-g` läuft und Detections aus lokalen DBs in die globale DB importiert:

1. **Für jede Detection aus lokaler DB:**
   - Lade zugehörigen Vektor aus lokaler `embeddings`-Tabelle (via `vector_id`)
   - Lies bereits gespeicherten `vector_hash`

2. **Prüfe in globaler DB:**
   - `SELECT vector_id FROM embeddings WHERE vector_hash = ?`

3. **Fall A: Hash existiert bereits in globaler DB**
   - Verwende existierende globale `vector_id`
   - Füge NUR Detection in globale `detections`-Tabelle ein (mit existierender `vector_id`)
   - Vektor wird NICHT dupliziert

4. **Fall B: Hash ist neu in globaler DB**
   - `INSERT INTO embeddings (vector_hash, embedding) VALUES (?, ?)`
   - Erhalte neue globale `vector_id`
   - Füge Vektor auch zu globalem DiskANN hinzu
   - Füge Detection mit neuer globaler `vector_id` ein

**Beispiel:**
- Standort A hat Kohlmeisen-Detection mit Hash "abc123", lokale vector_id = 42
- Standort B hat IDENTISCHE Kohlmeisen-Detection mit Hash "abc123", lokale vector_id = 17
- Beim Import in globale DB:
  - Standort A wird importiert: Vektor bekommt globale vector_id = 1
  - Standort B wird importiert: Hash "abc123" existiert schon! → Detection verweist auf globale vector_id = 1
  - **Ergebnis:** 2 Detections in globaler DB, aber nur 1 Vektor

#### Unabhängigkeit von lokalen DBs

Nach dem Import ist die globale SQLite + DiskANN-Datenbank vollständig autark. Alle Vektoren sind kopiert (nicht referenziert). Für globale Analysen werden die untergeordneten lokalen Datenbanken nicht mehr benötigt.

**Vorteil:** Auch wenn lokale Datenbanken gelöscht oder verschoben werden, bleibt die globale DB funktional.

**Nachteil:** Redundanz – Vektoren existieren in lokaler UND globaler DB (ca. 2x Speicherbedarf).

**Trade-off:** Redundanz gegen Robustheit. Die globale DB ist ein vollständiges, eigenständiges Archiv aller Detections und Embeddings des gesamten Projekts.

---

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

#### Technische Voraussetzungen an DiskANN

**Diese Architektur setzt voraus:**

1. **Explizite IDs:** DiskANN muss das Einfügen von Vektoren mit benutzerdefinierten IDs unterstützen:
   ```python
   diskann.add_vector(embedding, id=42)  # ID=42 wird verwendet
   ```
   Falls die verwendete Library das nicht unterstützt, muss ein Mapping-Feld `diskann_internal_id` in der `embeddings`-Tabelle ergänzt werden.

2. **Append-Modus:** DiskANN muss bestehende Indizes öffnen und erweitern können:
   ```python
   diskann = DiskANN.open(path)  # Bestehenden Index laden
   diskann.add_vector(new_embedding, id=543)  # Neuen Vektor hinzufügen
   diskann.save()  # Änderungen speichern
   ```

**Vor Implementierung zu klären:** Unterstützt `diskannpy` (oder eine andere DiskANN-Library) diese Features?

### 6.3 Persistenz und Wiederherstellung

Ein großer Vorteil von DiskANN ist die Persistenz: Der Index liegt komplett auf Disk. Wenn das Programm beendet wird und später neu gestartet wird, kann der Index einfach wieder geöffnet werden – alle Daten sind noch da.

Das ist wichtig für die Resume-Logik von birdnet-walker: Wenn der Walker während der Analyse abstürzt, können beim Neustart die bereits geschriebenen Vektoren im DiskANN-Index verbleiben. Der Walker muss nur in der SQLite-Datenbank prüfen, welche Files schon vollständig verarbeitet wurden, und kann dann dort weitermachen. Im schlimmsten Fall sagt der Hash, dass der Vektor schon indiziert wurde.

Es gibt allerdings eine Besonderheit: DiskANN unterstützt kein echtes "Löschen" von Vektoren. Wenn ein Vektor einmal hinzugefügt wurde, kann er nicht mehr entfernt werden. Man kann nur den gesamten Index neu aufbauen. Für unseren Anwendungsfall ist das kein Problem: Wir löschen nie Detections. Wenn eine Detection als fehlerhaft markiert wird, bleibt sie in der Datenbank (mit einer entsprechenden Markierung), aber der Vektor bleibt ebenfalls im Index.

---

## 7. Workflow für den Nutzer

### 7.1 Neue Aufnahmen analysieren (wie bisher)

Der grundlegende Workflow ändert sich für den Nutzer kaum gegenüber der bisherigen Form. Wie bisher ruft er `birdnet-walker /pfad/zu/ordner (und einige Optionen)` auf. Das Programm läuft durch, analysiert alle WAV-Files, und erstellt/erweitert eine Datenbank lokal und bei recursiver Arbeit wenn gewünscht, auch die globale Datenbank.

Auch die Resume-Funktion funktioniert wie bisher: Wenn der Walker abbricht und neu gestartet wird, analysiert er nur die Files, die noch nicht den Status "completed" in der `processing_status`-Tabelle haben. Zusätzlich sichert der Hash die Indizierung der Embeddings ab.

---

## 8. Offene Fragen und Entscheidungen

### 8.1 DiskANN-Parameter

Es gibt diverse Parameter beim Erstellen eines DiskANN-Index: Anzahl der Nachbarn im Graph, Distanz-Metrik, Konsolidierungs-Intervalle. Wir müssen sinnvolle Defaults wählen, die für typische biologische Projekte (Größenordnung: 10.000 bis 1.000.000 Detections pro Session) gut funktionieren.

Die Distanz-Metrik sollte Cosine-Similarity sein, da wir an der Richtung der Vektoren interessiert sind, nicht an ihrer absoluten Magnitude. Denn das ist bei Embeddings aus neuronalen Netzen üblich.

Die Anzahl der Nachbarn im Index-Graph beeinflusst den Trade-off zwischen Suchgeschwindigkeit und Genauigkeit. Ein höherer Wert bedeutet langsameren Aufbau, aber präzisere Suchen. Für unseren Anwendungsfall (wo Recall wichtiger ist als absolute Geschwindigkeit) sollten wir eher großzügig dimensionieren.

Konkrete Werte müssen experimentell ermittelt werden – idealerweise mit realen Datenbanken aus Testprojekten.

### 8.2 Performance-Überlegungen

Ein DiskANN-Index ist schnell für Suchen, aber langsamer beim Aufbau. Das Schreiben von 500 Embeddings in HDF5 dauert Millisekunden. Das Hinzufügen von 500 Vektoren zu DiskANN plus anschließende Konsolidierung kann mehrere Sekunden dauern.

Für den normalen Workflow (ein Ordner analysieren, dann fertig) ist das unkritisch – ein paar Sekunden zusätzliche Wartezeit am Ende der Analyse fallen nicht ins Gewicht. Aber für sehr große Batch-Jobs (hunderte Ordner) könnte sich das summieren.

Eine mögliche Optimierung: Batch-Inserts in DiskANN. Statt jeden Vektor einzeln hinzuzufügen, sammeln wir alle Vektoren eines Files und fügen sie als Batch hinzu. DiskANN kann dann einmal den Index aktualisieren statt 500 mal. Das müsste in der Implementierung berücksichtigt werden.

### 8.3 Recovery-Strategie bei korruptem DiskANN-Index

DiskANN-Indizes können durch Abstürze, Disk-Fehler oder fehlerhafte Shutdowns korrupt werden. Im Gegensatz zu SQLite, das transaktional und sehr robust ist, ist DiskANN anfälliger für solche Probleme.

#### Die gewählte Strategie: SQLite als Primary Storage

Um Datenverlust zu vermeiden, sind die Embedding-Vektoren PRIMÄR in der SQLite-Tabelle `embeddings` gespeichert (als BLOB). Der DiskANN-Index ist ein redundanter, optimierter Suchindex über diese Daten.

**Bei korruptem DiskANN:**

1. **Keine Panik:** Alle Vektoren sind in SQLite sicher gespeichert
2. **Rebuild ausführen:** Ein Tool `birdnet-rebuild-diskann` kann den Index neu aufbauen
3. **Dauer:** Ca. 1-2 Minuten pro 100.000 Vektoren (auf Standard-SSD)
4. **Kein Datenverlust:** Keine erneute BirdNET-Analyse nötig

#### Rebuild-Prozess (Pseudo-Code)

```python
def rebuild_diskann_from_sqlite(db_path, diskann_path):
    """
    Baut DiskANN-Index aus SQLite embeddings-Tabelle neu auf.
    """
    import shutil
    import sqlite3
    import numpy as np
    
    # 1. Alten (korrupten) Index löschen
    if os.path.exists(diskann_path):
        shutil.rmtree(diskann_path)
    
    # 2. Vektoren aus SQLite laden
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT vector_id, embedding FROM embeddings ORDER BY vector_id"
    )
    
    # 3. Neuen DiskANN-Index erstellen
    diskann = DiskANN.create(diskann_path, dimensions=1024, metric='cosine')
    
    # 4. Alle Vektoren einfügen
    count = 0
    for vector_id, embedding_blob in cursor:
        embedding = np.frombuffer(embedding_blob, dtype=np.float32)
        diskann.add_vector(embedding, id=vector_id)
        count += 1
        
        # Progress-Ausgabe alle 10.000 Vektoren
        if count % 10000 == 0:
            print(f"Rebuilt {count} vectors...")
    
    # 5. Index konsolidieren und speichern
    print("Consolidating index...")
    diskann.consolidate()
    diskann.save()
    
    conn.close()
    print(f"✓ Rebuild complete: {count} vectors")
```

#### Warum nicht: Nur DiskANN, kein BLOB in SQLite?

**Alternative (nicht gewählt):** Vektoren NUR in DiskANN speichern, SQLite hat nur `vector_id` + `vector_hash`.

**Problem bei Korruption:**
- Vektoren sind verloren
- Komplette Neuanalyse mit BirdNET nötig
- Bei 10.000 Audiostunden: Tage bis Wochen Rechenzeit
- Falls Audiofiles gelöscht: **UNMÖGLICH!**

**Warum das inakzeptabel ist:**
Biologische Projekte erstrecken sich über Jahre. Audiofiles werden oft nach der Analyse gelöscht (Speicherplatz!). Ein korrupter Index darf nicht bedeuten, dass Jahre an Arbeit verloren sind.

#### Kosten der gewählten Strategie

**Speicher-Overhead:**
- 1 Million Vektoren @ 1024 dims @ 4 Bytes = ~4 GB
- SQLite: ~4 GB (BLOB)
- DiskANN: ~5 GB (mit Index-Overhead)
- **Total: ~9 GB** (statt ~5 GB bei "nur DiskANN")

**Urteil:** Für ein mehrjähriges Projekt mit hunderten Gigabyte oder Terabytes an Audiodaten sind 4 GB Redundanz ein akzeptabler Preis für Datensicherheit.

#### Präventive Maßnahmen

Zusätzlich zum Recovery-Mechanismus:

1. **Atomic Writes:** DiskANN-Updates nur nach erfolgreicher SQLite-Transaktion
2. **Checkpoints:** Vor großen Batch-Operationen DiskANN-Backup erstellen
3. **Validierung:** Nach jedem birdnet-walker-Lauf kurzer Integritäts-Check des DiskANN-Index
4. **Logging:** Bei DiskANN-Fehlern detaillierte Logs, sodass Rebuild gezielt erfolgen kann

Diese Strategie macht das System robust gegen die häufigsten Fehlerquellen in der Praxis.

#### Synchronisation SQLite ↔ DiskANN

**Problem:** Was wenn das Programm zwischen SQLite-Insert und DiskANN-Insert abstürzt?

**Gewählte Strategie:** DiskANN ist "expendable" (kann jederzeit neu gebaut werden).

**Beim Start von birdnet-walker:**
1. Zähle Vektoren in SQLite: `SELECT COUNT(*) FROM embeddings`
2. Zähle Vektoren in DiskANN (falls Index existiert)
3. **Falls ungleich:** Warnung ausgeben, optional automatischer Rebuild

**Bei kleinen Differenzen (< 1%):** Weiterarbeiten, DiskANN wird bei Bedarf gefixt.

**Bei großen Differenzen (> 5%):** Automatischer Rebuild empfohlen.

Dies vermeidet aufwändiges Tracking in SQLite (`in_diskann` Boolean-Feld).

### 8.4 Umgang mit sehr großen Datenmengen

Was passiert, wenn eine globale Datenbank 10 Millionen Detections hat? DiskANN kann das theoretisch handhaben, aber praktische Aspekte müssen bedacht werden:

Die SQLite-Datenbank mit 10 Millionen Zeilen in der `detections`-Tabelle ist mehrere Gigabyte groß. Queries können langsam werden, wenn nicht richtig indiziert. Wir müssen sicherstellen, dass alle relevanten Spalten (insbesondere `vector_hash` für die Deduplizierungs-Lookups) gut indiziert sind.

Der DiskANN-Index mit 10 Millionen Vektoren (je 1024 * 4 Bytes = 4 KB) ist etwa 40 GB groß (plus Index-Overhead). Das passt problemlos auf moderne SSDs, aber das Laden und Konsolidieren kann Minuten dauern. Wir sollten dem Nutzer klare Fortschrittsanzeigen geben.

Eine mögliche Optimierung für Experten-Nutzer: Sharding. Die globale Datenbank könnte aufgeteilt werden in mehrere Shards (z.B. nach Jahr oder Standort). Jeder Shard ist eine separate globale Datenbank. Bei Suchen werden dann parallel mehrere Shards durchsucht. Das ist aber ein fortgeschrittenes Feature für später.

---

## 9. Implementierungsstrategie

### 9.1 Schrittweise Einführung

Die Umstellung sollte nicht in einem großen Bang passieren, sondern schrittweise. Ein möglicher Fahrplan:

**Phase 1: Lokale Speicherung der Embedding-Vektoren in SQLite (Ersatz für HDF5)**

Die HDF5-basierte Speicherung wird vollständig durch SQLite ersetzt:

1. **Neue Tabelle `embeddings` erstellen** mit Feldern:
   - `vector_id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `vector_hash` (TEXT UNIQUE) – SHA256 über Vektor-Bytes
   - `embedding` (BLOB) – Der komplette 1024-float32-Vektor (4096 Bytes)

2. **Deduplizierungs-Logik** in `birdnet_analyzer.py`:
   - Vor jedem Insert: Prüfe ob `vector_hash` bereits existiert
   - Falls ja: Verwende existierende `vector_id`
   - Falls nein: INSERT neuer Vektor, erhalte neue `vector_id`

3. **`detections`-Tabelle erweitern:**
   - Feld `embedding_idx` umbenennen zu `vector_id`
   - Foreign Key zu `embeddings(vector_id)` hinzufügen

4. **`db_version`-Tabelle anlegen:**
   - Speichere `db_type = "session"`, `schema_version = "1.0"`

**Ergebnis Phase 1:** Alle Vektoren liegen sicher in SQLite. HDF5-Code kann entfernt werden. DiskANN noch nicht implementiert.

**Test:** Bestehende birdnet-play-Funktionen müssen mit neuem Schema funktionieren (Embeddings aus SQLite-BLOB statt HDF5 laden).

**Phase 2: DiskANN-Index parallel zu SQLite aufbauen**

SQLite bleibt primär, DiskANN wird als redundanter Suchindex hinzugefügt:

1. **DiskANN-Wrapper-Modul** erstellen:
   - Funktionen: `create_diskann()`, `open_diskann()`, `add_vector_with_id()`, `consolidate()`
   - Wichtig: Vektoren mit expliziter ID einfügen (muss mit SQLite `vector_id` übereinstimmen!)

2. **Integration in birdnet_analyzer.py:**
   - Nach `INSERT INTO embeddings`: Füge Vektor auch zu DiskANN hinzu
   - Verwende die gleiche `vector_id` für beide
   - Bei Deduplizierung (Hash existiert): NICHT in DiskANN einfügen

2.5. **Index-Management:**
     ```python
     # Pseudo-Code für Append-Logik
     diskann_path = "birdnet_vectors.diskann/"
     
     if os.path.exists(diskann_path):
         diskann = DiskANN.open(diskann_path)  # Bestehenden laden
     else:
         diskann = DiskANN.create(diskann_path, dims=1024, metric='cosine')
     
     # Vektor hinzufügen
     diskann.add_vector(embedding, id=vector_id)
     
     # Nach jedem File: Save (leichtgewichtig)
     diskann.save()
     
     # Nach N Files (z.B. 100): Consolidate (teuer)
     if file_count % 100 == 0:
         diskann.consolidate()
     ```

3. **Konsolidierung nach Datei-Analyse:**
   - Nach Abschluss aller Embeddings eines Files: `diskann.consolidate()`
   - Optimiert den Index für Suchen

4. **`db_version` erweitern:**
   - Füge `diskann_version` hinzu (z.B. "0.7.0")

5. **Recovery-Tool** `birdnet-rebuild-diskann` erstellen:
   - Liest alle Vektoren aus SQLite `embeddings`-Tabelle
   - Baut DiskANN-Index neu auf
   - Nützlich bei korruptem Index

**Ergebnis Phase 2:** Vektoren liegen in SQLite UND DiskANN. Schnelle Nearest-Neighbor-Suchen möglich. Bei Korruption: Rebuild aus SQLite.

**Test:** DiskANN-basierte Suchen durchführen, Ergebnisse mit Brute-Force-Suche in SQLite vergleichen (müssen identisch sein).

**Phase 3: Globalität**

Jetzt bauen wir das Globale ein: Zuerst wird geprüft, ob in der rekursiven Bearbeitung die Ordnerlokale Datenbankerstellung funktioniert. Dann wird die Funktionalität der globalen Datenbanken integriert. Die Position ist dafür immer der Startpunkt der recursiven Arbeit. Das muss der Nutzer gewähren. Wichtig ist, dass jetzt zweigleisig analysiert wird:

* auf Ordner-Niveau, ob neue Audiodateien zu erkennen und indizieren sind
* auf Global-Niveau, dass diese Analysen global zugefügt werden und: ob weitere, bisher nur auf Ordnerebene erstellte Analyseergebnisse und Vektoren in die globale Datenbanken zuzufügen sind.

---

**Ende des Konzeptdokuments**