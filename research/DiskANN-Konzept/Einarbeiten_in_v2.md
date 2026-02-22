# Offene Punkte und Ergänzungen für vector_db_concept v2.2

**Zweck:** Dieses Dokument listet alle Punkte auf, die in der nächsten Version des Konzeptdokuments `vector_db_concept_2.md` berücksichtigt werden sollten, um es implementierungsbereit zu machen.

**Status:** Einarbeitungsdokument (nicht das finale Konzept selbst)  
**Datum:** 14. Februar 2026  

--- 

## 1.: - erledigt

---

## 2. Globale Datenbank: Vollständiges Schema definieren

### Problem
In Abschnitt 3.3 wird eine "Vermittlungsstelle" zwischen globalem DiskANN-Index und lokalen Daten erwähnt, aber das genaue Schema fehlt.

### Fehlende Tabellendefinition

Die globale DB benötigt eine Tabelle, die globale DiskANN-IDs mit lokalen Quellen verknüpft:

```sql
-- Globale DB: birdnet_global.db
-- NEU: Vermittlungstabelle

CREATE TABLE vector_sources (
    global_vector_id INTEGER PRIMARY KEY,     -- ID in globaler embeddings-Tabelle
    vector_hash TEXT UNIQUE NOT NULL,         -- SHA256 für Deduplizierung
    source_db_path TEXT NOT NULL,             -- z.B. "standort_a/birdnet_analysis.db"
    local_vector_id INTEGER NOT NULL,         -- ID in lokaler embeddings-Tabelle
    first_seen_utc TEXT NOT NULL,             -- Wann erstmals in globale DB importiert
    FOREIGN KEY (global_vector_id) REFERENCES embeddings(vector_id)
);

CREATE INDEX idx_vector_sources_hash ON vector_sources(vector_hash);
CREATE INDEX idx_vector_sources_path ON vector_sources(source_db_path);
```

### Alternative: Vereinfachte Variante (ohne separate Tabelle)

Falls die globale DB vollständig unabhängig sein soll:

```sql
-- Globale DB enthält NUR:
-- 1. embeddings (BLOB + Hash)
-- 2. detections (mit audio_path statt filename)

-- KEINE separate Vermittlung, da:
-- - Vektoren sind KOPIERT (nicht referenziert)
-- - Dereferenzierung über detections.audio_path → findet lokale DB automatisch
```

**Vorteil:** Einfacher, keine zusätzliche Tabelle.  
**Nachteil:** Keine Rückverfolgung, aus welcher lokalen DB ein Vektor ursprünglich kam.

### Zu entscheiden
Welche Variante passt besser zum Use Case?

- **Mit vector_sources:** Debugging, Auditing, "Woher kam dieser Vektor?"
- **Ohne:** Einfachheit, globale DB als reines Archiv

### Ins Konzept aufnehmen
- Abschnitt 3.3.1 erweitern: Vollständiges SQL-Schema
- Abschnitt 5.2 erweitern: Tabellenstruktur vollständig dokumentieren
- Deduplizierungs-Logik beim Import präzisieren (nutzt vector_sources oder nicht?)

---

## 3. Embedding-Extraktion: Workflow detailliert beschreiben

### Problem
Das Konzept sagt "ein Vektor pro Zeitsegment", aber der genaue Ablauf fehlt.

### Klarstellung (wie besprochen)
- BirdNET analysiert Audio in 3-Sekunden-Segmenten (mit 0.75s Overlap)
- **Ein Segment → Ein Embedding-Vektor**
- **Mehrere Species-Detections können auf denselben Vektor verweisen**

### Beispiel-Szenario
```
Zeitsegment 08:32:21.5 - 08:32:24.5:
  - Erkennung 1: Kohlmeise (0.89 confidence)
  - Erkennung 2: Blaumeise (0.45 confidence)
  
→ Ein Embedding-Vektor wird extrahiert
→ Beide Detections bekommen dieselbe vector_id
```

### Workflow in Pseudo-Code

```python
# Phase 1: BirdNET-Analyse
detections = analyze_file(audio_file)  
# Returns: [
#   (start=0.0, end=3.0, species="Parus major", conf=0.89),
#   (start=0.0, end=3.0, species="Cyanistes caeruleus", conf=0.45),
#   (start=2.25, end=5.25, species="Turdus merula", conf=0.92),
#   ...
# ]

# Phase 2: Unique Zeitsegmente identifizieren
unique_segments = extract_unique_time_segments(detections)
# Returns: [(0.0, 3.0), (2.25, 5.25), ...]

# Phase 3: Embeddings nur für diese Segmente extrahieren
for segment in unique_segments:
    embedding = extract_embedding_for_segment(audio_file, segment)
    vector_hash = sha256(embedding.tobytes()).hexdigest()
    
    # Phase 4: Deduplizierung
    cursor.execute("SELECT vector_id FROM embeddings WHERE vector_hash = ?", (vector_hash,))
    existing = cursor.fetchone()
    
    if existing:
        vector_id = existing[0]  # Wiederverwenden
    else:
        # Neuer Vektor
        cursor.execute(
            "INSERT INTO embeddings (vector_hash, embedding) VALUES (?, ?)",
            (vector_hash, sqlite3.Binary(embedding.tobytes()))
        )
        vector_id = cursor.lastrowid
        
        # Auch in DiskANN einfügen
        diskann.add_vector(embedding, id=vector_id)
    
    # Phase 5: Alle Detections in diesem Segment verknüpfen
    for det in filter_detections_by_segment(detections, segment):
        cursor.execute(
            "INSERT INTO detections (..., vector_id) VALUES (..., ?)",
            (..., vector_id)
        )
```

### Ins Konzept aufnehmen
- **Neuer Abschnitt 3.4:** "Detaillierter Workflow: Von Audio zu Embeddings"
- Abschnitt 2.2 erweitern: Diagramm/Ablaufplan einfügen
- Code-Beispiel in Abschnitt 9.1 Phase 1

---

## 4. DiskANN Append-Modus: Machbarkeit klären

### Problem
Das Konzept setzt voraus, dass DiskANN bestehende Indizes öffnen und erweitern kann. Das ist **nicht bei allen Implementierungen garantiert**!

### Zu testen VOR Implementierung

```python
import diskannpy

# Test 1: Index erstellen und speichern
index = diskannpy.DynamicMemoryIndex(
    distance_metric='cosine',
    dimensions=1024,
    max_points=1000000
)
vectors_batch1 = np.random.randn(100, 1024).astype('float32')
index.batch_insert(vectors_batch1, ids=range(1, 101))
index.save("test_index.diskann")

# Test 2: Index LADEN und ERWEITERN (KRITISCH!)
index2 = diskannpy.DynamicMemoryIndex.load("test_index.diskann")
vectors_batch2 = np.random.randn(50, 1024).astype('float32')
index2.batch_insert(vectors_batch2, ids=range(101, 151))  # Geht das?
index2.save("test_index.diskann")  # Überschreibt korrekt?

# Test 3: Suche über alle Vektoren
results = index2.search(query_vector, k=10)
assert max(results) >= 101  # Vektoren aus Batch 2 gefunden?
```

### Wenn Append NICHT möglich

**Alternative Architektur:** Batch-Updates statt kontinuierlicher Append

```python
# Strategie: Vektoren sammeln, dann periodisch Index neu bauen
pending_vectors = []

for file in files:
    embeddings = extract_embeddings(file)
    pending_vectors.extend(embeddings)
    
    # Nur alle 10.000 Vektoren: DiskANN neu bauen
    if len(pending_vectors) >= 10000:
        rebuild_diskann_from_sqlite(db_path, diskann_path)
        pending_vectors = []

# Am Ende: Finaler Rebuild
if pending_vectors:
    rebuild_diskann_from_sqlite(db_path, diskann_path)
```

**Vorteil:** Funktioniert auch ohne Append-Support.  
**Nachteil:** Langsamer, da häufige Rebuilds.

### Ins Konzept aufnehmen
- Abschnitt 6.2 erweitern: Explizit dokumentieren, ob Append-Modus verfügbar ist
- Falls nein: Alternative Batch-Strategie als Fallback beschreiben
- Abschnitt 8.2 (Performance): Rebuild-Zeiten abschätzen

---

## 5. Consolidate-Timing: Präzise Regeln definieren

### Problem
Im Konzept gibt es widersprüchliche Angaben:
- "nach 10.000 neuen Vektoren" (Abschnitt 6.2)
- "Nach N Files (z.B. 100)" (Abschnitt 9.1)

### Empfohlene Strategie

Kombinierte Regel mit zwei Schwellwerten:

```python
# Konstanten (in config.py)
DISKANN_CONSOLIDATE_EVERY_N_VECTORS = 10000
DISKANN_CONSOLIDATE_EVERY_N_FILES = 100
DISKANN_CONSOLIDATE_EVERY_N_SECONDS = 3600  # Max. 1h zwischen Consolidates

# Implementierung
last_consolidate_time = time.time()
vectors_since_consolidate = 0
files_since_consolidate = 0

for file in files:
    embeddings = process_file(file)
    vectors_since_consolidate += len(embeddings)
    files_since_consolidate += 1
    
    should_consolidate = (
        vectors_since_consolidate >= DISKANN_CONSOLIDATE_EVERY_N_VECTORS or
        files_since_consolidate >= DISKANN_CONSOLIDATE_EVERY_N_FILES or
        (time.time() - last_consolidate_time) >= DISKANN_CONSOLIDATE_EVERY_N_SECONDS
    )
    
    if should_consolidate:
        logger.info(f"Consolidating index: {vectors_since_consolidate} vectors, "
                   f"{files_since_consolidate} files")
        diskann.consolidate()
        
        # Reset counters
        vectors_since_consolidate = 0
        files_since_consolidate = 0
        last_consolidate_time = time.time()
```

### Ins Konzept aufnehmen
- Abschnitt 6.2 erweitern: Klare Konsolidierungs-Regeln
- Abschnitt 9.1 Phase 2: Einheitlicher Pseudo-Code
- Config-Parameter in neuer Tabelle listen

---

## 6. Globale DB als unabhängiges Archiv: Explizit dokumentieren

### Problem
Nicht klar, ob globale DB auf lokale DBs angewiesen ist oder vollständig autark.

### Klarstellung (bevorzugte Variante)

**Globale DB ist ein vollständig unabhängiges Archiv:**

- Alle Vektoren werden **KOPIERT** (nicht referenziert)
- Alle Detections werden **KOPIERT** mit relativem `audio_path`
- Nach Import kann lokale DB gelöscht werden → globale DB bleibt funktional

### Beispiel

```
# Vor Import
/recordings/
├── standort_a/
│   ├── birdnet_analysis.db        # 1000 Vektoren
│   └── birdnet_vectors.diskann/
└── standort_b/
    ├── birdnet_analysis.db        # 800 Vektoren
    └── birdnet_vectors.diskann/

# Nach Import in /recordings/birdnet_global.db
/recordings/
├── birdnet_global.db              # 1600 Vektoren (200 dedupliziert)
├── birdnet_vectors_global.diskann/
├── standort_a/ ...                # Kann jetzt gelöscht werden!
└── standort_b/ ...                # Kann jetzt gelöscht werden!
```

### Konsequenzen

**Vorteil:**
- Globale DB ist portabel (gesamter Ordner verschiebbar)
- Lokale DBs sind temporär (nach Import entfernbar)
- Backup-Strategie einfach (nur globale DB sichern)

**Nachteil:**
- Redundanz (Vektoren in lokal + global = ca. 2x Speicher)
- Bei großen Projekten: Viele GB Speicherplatz

### Trade-off-Entscheidung

**Für Archivierung:** Akzeptabel  
**Für laufende Projekte:** Lokale DBs behalten, bis Projekt abgeschlossen

### Ins Konzept aufnehmen
- Abschnitt 5.2 erweitern: "Unabhängigkeit von lokalen DBs" als eigener Unterabschnitt
- Abschnitt 7 (Workflow): Explizite Empfehlung, wann lokale DBs gelöscht werden können
- Abschnitt 8.4: Speicher-Trade-off dokumentieren

---

## 7. Performance-Abschätzungen: Konkrete Zahlen

### Problem
Konzept enthält keine Angaben zu erwarteten Laufzeiten und Ressourcenbedarf.

### Zu ergänzen in Abschnitt 8.2

**Geschätzte Performance (Referenz-Hardware: Standard-Laptop, SSD, 16 GB RAM):**

| Operation | Dauer | Details |
|-----------|-------|---------|
| Embedding-Extraktion | ~5 Min./h Audio | BirdNET-Inference auf CPU |
| DiskANN Initial Insert | ~2 Sek./1000 Vektoren | Erste Indexierung |
| DiskANN Consolidate | ~10 Sek./100k Vektoren | Graph-Optimierung |
| DiskANN Nearest-Neighbor (k=10) | <100 ms | Bei 1 Mio. Vektoren |
| SQLite Insert | ~0.1 ms/Vektor | Mit Transaktion (Batch) |
| SQLite SELECT (Hash-Lookup) | <1 ms | Mit Index |

**Speicherbedarf:**

| Komponente | Größe | Berechnung |
|------------|-------|------------|
| 1 Embedding (SQLite BLOB) | 4 KB | 1024 × float32 = 4096 Bytes |
| 100k Embeddings (SQLite) | ~400 MB | 100k × 4 KB |
| 100k Embeddings (DiskANN) | ~500 MB | Mit Index-Overhead (~25%) |
| RAM während Indexierung | ~2 GB | Temporäre Strukturen |

**Beispiel-Szenario:**

```
Projekt: 1 Jahr Monitoring, 10 Standorte, je 6h/Tag
→ 21.900 Stunden Audio
→ ~50.000 Detections/Standort = 500k Detections gesamt
→ ~350k unique Zeitsegmente (nach Deduplizierung)

Speicher:
- SQLite embeddings: ~1.4 GB
- DiskANN Index: ~1.8 GB
- Gesamt: ~3.2 GB

Aufbauzeit:
- Embedding-Extraktion: ~1.825 Stunden (für alle 21.900h Audio)
- DiskANN-Indexierung: ~12 Minuten
```

### Ins Konzept aufnehmen
- Abschnitt 8.2 komplett neu schreiben mit diesen Zahlen
- Tabellen verwenden für bessere Lesbarkeit
- Beispiel-Szenario als konkreten Use Case

---

## 8. Schema-Migration: Bestehende DBs konvertieren

### Problem
Bestehende Nutzer haben DBs mit altem Schema (HDF5-basiert). Es fehlt eine Migrationsstrategie.

### Zu ergänzen: Neuer Abschnitt 9.4

**"9.4 Migration bestehender Datenbanken"**

### Migrations-Szenario

**Alt (v0.3):**
```
/recordings/
├── birdnet_analysis.db
│   └── detections.embedding_idx → Index in HDF5
└── birdnet_embeddings.h5
    └── Dataset [7200 × 1024]
```

**Neu (v2.x):**
```
/recordings/
├── birdnet_analysis.db
│   ├── embeddings (Tabelle mit BLOB)
│   └── detections.vector_id → embeddings.vector_id
└── birdnet_vectors.diskann/
    └── Index mit IDs = vector_id
```

### Migrations-Tool

```python
# birdnet-migrate-embeddings

import h5py
import sqlite3
import numpy as np
import hashlib
from diskannpy import DynamicMemoryIndex

def migrate_database(db_path):
    """
    Migriert alte HDF5-basierte DB zu neuem Schema.
    """
    # 1. Öffne DB und HDF5
    conn = sqlite3.connect(db_path)
    hdf5_path = db_path.replace('birdnet_analysis.db', 'birdnet_embeddings.h5')
    
    if not os.path.exists(hdf5_path):
        print("Keine HDF5-Datei gefunden, nichts zu migrieren.")
        return
    
    # 2. Erstelle neue embeddings-Tabelle
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            vector_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vector_hash TEXT UNIQUE NOT NULL,
            embedding BLOB NOT NULL
        )
    """)
    
    # 3. Lade alle Embeddings aus HDF5
    with h5py.File(hdf5_path, 'r') as h5:
        all_embeddings = h5['embeddings'][:]  # Shape: (N, 1024)
    
    # 4. Erstelle Hash-Map: embedding_idx → vector_id
    idx_to_vid = {}
    
    for old_idx, embedding in enumerate(all_embeddings):
        vector_hash = hashlib.sha256(embedding.tobytes()).hexdigest()
        
        # Deduplizierung
        cursor = conn.execute(
            "SELECT vector_id FROM embeddings WHERE vector_hash = ?",
            (vector_hash,)
        )
        existing = cursor.fetchone()
        
        if existing:
            vector_id = existing[0]
        else:
            conn.execute(
                "INSERT INTO embeddings (vector_hash, embedding) VALUES (?, ?)",
                (vector_hash, sqlite3.Binary(embedding.tobytes()))
            )
            vector_id = conn.lastrowid
        
        idx_to_vid[old_idx] = vector_id
    
    conn.commit()
    
    # 5. Update detections: embedding_idx → vector_id
    conn.execute("ALTER TABLE detections RENAME COLUMN embedding_idx TO vector_id")
    
    for old_idx, new_vid in idx_to_vid.items():
        conn.execute(
            "UPDATE detections SET vector_id = ? WHERE vector_id = ?",
            (new_vid, old_idx)
        )
    
    conn.commit()
    
    # 6. Baue DiskANN-Index
    diskann_path = db_path.replace('birdnet_analysis.db', 'birdnet_vectors.diskann')
    rebuild_diskann_from_sqlite(db_path, diskann_path)
    
    # 7. Lösche alte HDF5 (optional, nach Backup!)
    # os.remove(hdf5_path)
    
    print(f"✓ Migration abgeschlossen: {len(idx_to_vid)} Embeddings migriert")

def rebuild_diskann_from_sqlite(db_path, diskann_path):
    """Baut DiskANN aus SQLite embeddings."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT vector_id, embedding FROM embeddings ORDER BY vector_id")
    
    index = DynamicMemoryIndex(distance_metric='cosine', dimensions=1024)
    
    for vector_id, embedding_blob in cursor:
        embedding = np.frombuffer(embedding_blob, dtype=np.float32)
        index.insert(embedding, id=vector_id)
    
    index.save(diskann_path)
    conn.close()
```

### Workflow für Nutzer

```bash
# 1. Backup erstellen
cp -r /recordings /recordings_backup

# 2. Migration ausführen
birdnet-migrate-embeddings /recordings

# 3. Test: Alte und neue DB vergleichen
birdnet-verify-migration /recordings

# 4. Falls OK: Alte HDF5 löschen
find /recordings -name "birdnet_embeddings.h5" -delete
```

### Ins Konzept aufnehmen
- **Neuer Abschnitt 9.4:** Vollständiger Migrations-Guide
- Warnung: Backup vor Migration!
- Verify-Skript erwähnen

---

## 9. Zusammenfassung: Checkliste für v2.2

### Struktur-Erweiterungen

- [ ] **Abschnitt 3.2** erweitern: DiskANN vector_id (0 vs 1) klären
- [ ] **Abschnitt 3.3.1** erweitern: Vollständiges Schema der globalen DB
- [ ] **Neuer Abschnitt 3.4:** Detaillierter Workflow Audio → Embeddings
- [ ] **Abschnitt 5.2** erweitern: Unabhängigkeit globaler DB dokumentieren
- [ ] **Abschnitt 6.2** präzisieren: DiskANN Append-Modus (Machbarkeit)
- [ ] **Abschnitt 6.2** erweitern: Consolidate-Timing (klare Regeln)
- [ ] **Abschnitt 8.2** neu schreiben: Performance-Tabellen
- [ ] **Neuer Abschnitt 9.4:** Schema-Migration

### Zu klärende Fragen (vor Implementierung)

1. **DiskANN-Library testen:**
   - Append-Modus verfügbar?
   - Benutzerdefinierte IDs möglich?
   - Welche Library verwenden? (diskannpy, pydiskann, ...)

2. **Globale DB-Struktur:**
   - Mit oder ohne `vector_sources`-Tabelle?
   - Komplett autark oder mit Referenzen?

3. **Consolidate-Strategie:**
   - Nach Vektoren, Dateien oder Zeit?
   - Kombinierte Regel sinnvoll?

### Code-Beispiele hinzufügen

- [ ] Workflow-Pseudo-Code in Abschnitt 3.4
- [ ] DiskANN-Test-Code in Abschnitt 6.2
- [ ] Migrations-Tool in Abschnitt 9.4
- [ ] Performance-Benchmark-Skript in Abschnitt 8.2

### Diagramme/Visualisierungen

- [ ] Datenfluss-Diagramm: Audio → Detections → Embeddings → DiskANN
- [ ] Schema-Diagramm: Tabellen-Beziehungen (lokal + global)
- [ ] Zeitstrahl: Wann wird konsolidiert?

---

## 10. Nächste Schritte

1. **DiskANN-Library evaluieren** (2-3h)
   - Tests mit diskannpy schreiben
   - Append-Modus testen
   - Performance messen

2. **Konzept v2.2 schreiben** (4-6h)
   - Alle oben genannten Punkte einarbeiten
   - Code-Beispiele ergänzen
   - Review durch Zweitleser

3. **Prototyp entwickeln** (1-2 Wochen)
   - Phase 1: SQLite embeddings (ohne DiskANN)
   - Phase 2: DiskANN parallel
   - Phase 3: Globale DB

4. **Migrations-Tool** (3-5 Tage)
   - HDF5 → SQLite konvertieren
   - Verify-Skript
   - Dokumentation

---

**Ende des Einarbeitungsdokuments**
