# Konzept: Species Co-Occurrence Cluster Analysis

## Ausgangsüberlegung

Wenn Aufnahmen verschiedener Arten zeitlich immer wieder zusammen fallen, dann besteht die Möglichkeit, dass durch eng beieinander liegende Cluster zwar nicxht die angezeigte Art detektiert wurde, sondern die im Nachbarcluster. Wie kann man solche Cluster finde und wie kann man sie visualisieren?

## 1. Algorithmus-Design

### 1.1 Grundprinzip: Zeitlich gewichtete Proximity-Analyse

**Ziel:** Identifikation von Species-Paaren, die statistisch signifikant häufiger gemeinsam auftreten als zufällig erwartet.

**Methodik:**

- Paarweiser Vergleich aller Detections innerhalb eines Zeitfensters
- Gauß-gewichtete Ko-Okkurrenz basierend auf zeitlichem Abstand
- Aggregation in symmetrischer Species-Pair-Matrix

### 1.2 Gauß-Kernel für zeitliche Wichtung

**Formel:**

```python
weight = exp(-distance² / (2 * σ²))
```

**Parameter:**

- **σ (Sigma):** 5 Minuten (Default, konfigurierbar)
- **max_distance:** 5 × σ = 25 Minuten (Bereichsprüfgrenze)
- **distance:** Zeitdifferenz zwischen zwei Detections in Minuten

**Eigenschaften:**

- Bei distance = 0: weight = 1.0 (maximale Relevanz)
- Bei distance = σ (5 Min): weight ≈ 0.607
- Bei distance = 2σ (10 Min): weight ≈ 0.135
- Bei distance = 3σ (15 Min): weight ≈ 0.011
- Bei distance > 5σ (25 Min): weight = 0 (nicht mehr berechnet)

An dieser Stelle muss geprüft werden, wie Birdnet mit einem Audioschnipsel um geht: Werden da auch mehre Arten mit confidence angegeben? Wenn ja, sollte die Zeitlich vollständige Überlappung (distance = 0) nochmal höher gewichtet werden, als in der Tabelle bzw. der genannten Formel.

### 1.3 Proximity-Matrix-Berechnung

**Input:**

- Alle Detections aus Snapshot (z.B. 1 Tag)
- Sortiert nach `segment_start_local`
- Gefiltert nach `min_confidence` (aus Analyse-Config)

**Algorithmus (Sliding Window):**

```
1. Sortiere alle Detections nach Zeit: D = [d1, d2, ..., dn]
2. Initialisiere leere Pair-Matrix: M[species_a, species_b] = 0
3. Für jede Detection di (i = 1 bis n):
   4. Finde alle Detections dj mit |time(di) - time(dj)| <= max_distance
   5. Für jedes gültige Paar (di, dj):
      6. Berechne weight = gauss_kernel(|time(di) - time(dj)|, sigma)
      7. M[species(di), species(dj)] += weight
      8. (Symmetrie: nur obere Dreiecksmatrix speichern)
8. Return M
```

**Komplexität:**

- Naive: O(n²) - nicht praktikabel bei ~50k Detections/Tag
- Optimiert mit Sliding Window: O(n × w)
  - w = durchschnittliche Detections im 25-Min-Fenster
  - Bei 10 Detections/Min → w ≈ 250
  - → O(50k × 250) = 12.5M Operationen (machbar)
- Mit Hilfe der max_distance (Abbruch nach a * σ) wird die Komplexität begrenzt.

**Optimierung:**

- Binäre Suche für Fenster-Grenzen (bisect)
- Nur obere Dreiecksmatrix berechnen (Symmetrie)
- Optional: Sparse Matrix für seltene Species

---

## 2. GPU-Beschleunigung

Zu prüfen ist noch, ob die Berechnung für eine komplette Datenbank ad-hoc auf der CPU möglich ist oder ob ein eigener pre-Analyse-Walk benötigt wird. Dann wäre die GPU möglichweise sinnvoll zur Beschleunigung.

### 2.1 GPU-taugliche Operationen

**Kandidaten für GPU:**

1. **Distanz-Matrix-Berechnung:**

   - Input: Zeitstempel-Array (n × 1)
   - Output: Distanz-Matrix (n × n)
   - Operation: Pairwise Differenzen → GPU-parallelisierbar
2. **Gauß-Kernel-Anwendung:**

   - Input: Distanz-Matrix
   - Output: Weight-Matrix
   - Operation: Element-wise exp() → GPU-optimal
3. **Species-Aggregation:**

   - Input: Weight-Matrix, Species-Labels
   - Output: Pair-Matrix
   - Operation: GroupBy + Sum → teilweise GPU-tauglich (CuPy/Numba)

**Technologie-Stack:**

- **CuPy:** NumPy-kompatibel, GPU-beschleunigt
- **Numba CUDA:** Custom Kernels für spezielle Operationen
- **PyTorch/TensorFlow:** Falls komplexere Matrix-Ops nötig

### 2.2 CPU-Lösung

**Parallelisierung:**

- Multiprocessing über Tages-Chunks
- Jeder Worker berechnet Teil der Pair-Matrix
- Merge-Step aggregiert Ergebnisse

**Libraries:**

- `multiprocessing.Pool`
- Pandas/NumPy für Matrix-Operationen
- `scipy.sparse` für große sparse Matrices

---

## 3. Statistische Metriken

### 3.1 Lift-Analyse

**Formel:**

```python
Expected(A, B) = count(A) × count(B) / total_windows
Observed(A, B) = weighted_cooccurrence(A, B)
Lift(A, B) = Observed / Expected
```

**Interpretation:**

- **Lift = 1.0:** Unabhängig (wie erwartet)
- **Lift > 1.0:** Positive Korrelation (treten häufiger zusammen auf)
- **Lift < 1.0:** Negative Korrelation (meiden sich)

**Verdachts-Schwellen (Hypothese, zu verifizieren):**

- **Lift > 3.0:** Sehr verdächtig (potenzielle Fehlzuordnung)
- **Lift 2.0-3.0:** Verdächtig (genauer prüfen)
- **Lift 1.5-2.0:** Leichte Korrelation (biologisch plausibel?)
- **Lift < 0.5:** Negative Korrelation (exklusives Verhalten?)

**Problem:** Definition von "total_windows" bei kontinuierlicher Zeit

- **Lösung:** Normierung über gewichtete Gesamt-Vorkommen

### 3.2 Support (Absolute Häufigkeit)

**Formel:**

```python
Support(A, B) = weighted_cooccurrence(A, B)
```

**Interpretation:**

- Absolute "Stärke" der Korrelation
- Filtert seltene Zufallskorrelationen
- Kombiniert mit Lift: Nur Paare mit Support > Threshold

### 3.3 Confidence (Conditional Probability)

**Formel:**

```python
Confidence(A → B) = weighted_cooccurrence(A, B) / total_weighted_occurrences(A)
Confidence(B → A) = weighted_cooccurrence(A, B) / total_weighted_occurrences(B)
```

**Interpretation:**

- "Wie oft tritt B auf, wenn A vorhanden ist?"
- Asymmetrisch: Conf(A→B) ≠ Conf(B→A)
- Nützlich für Fehlzuordnungs-Hypothesen

**Beispiel:**

```
Kohlmeise: 1000 gewichtete Vorkommen
Exot. Vogel: 50 gewichtete Vorkommen
Co-Occurrence: 45

Conf(Kohlmeise → Exot): 45/1000 = 4.5%
Conf(Exot → Kohlmeise): 45/50 = 90%

→ Exot. Vogel tritt fast NUR mit Kohlmeise auf → verdächtig!
```

### 3.4 Jaccard-Koeffizient (Optional)

**Formel:**

```python
Jaccard(A, B) = |Zeitpunkte mit A ∩ B| / |Zeitpunkte mit A ∪ B|
```

**Interpretation:**

- Ähnlichkeit der zeitlichen Verteilung
- Wert: 0 (disjunkt) bis 1 (identisch)
- Weniger gewichtet als Lift, aber komplementär

---

## 4. Datenbank-Schema

### 4.1 Datenbank-Datei

**Pfad:** `cluster_analysis.db` (neben Source-DB oder konfigurierbar)

**Vorteile:**

- Unabhängig von Analyse-DB (keine Schema-Änderungen)
- Mehrere Analyse-Runs vergleichbar
- Export/Archivierung einfach

### 4.2 Tabelle: `analysis_runs`

**Zweck:** Tracking aller durchgeführten Analysen mit Parametern

```sql
CREATE TABLE cooccurences_run (

    -- Source
    source_db_path TEXT NOT NULL,       -- Pfad zur birdnet_analysis.db
  
    -- Snapshot-Definition
    snapshot_date_from TEXT,            -- NULL = gesamte DB
    snapshot_date_to TEXT,
  
    -- Algorithmus-Parameter
    min_confidence REAL NOT NULL,       -- Aus Analyse-Config oder Override
    sigma_seconds REAL NOT NULL,        -- Default: 5.0 x 60
    max_distance_seconds REAL NOT NULL, -- Default: 5 × sigma_seconds = 25.0
    weight_function TEXT NOT NULL,      -- 'gaussian' (später: 'exponential', 'linear')
    min_lift_level REAL NOT NULL,       -- Default: 1.5 (a mean lift value to add a coocrurences result in DB)
  
    -- Optional
    comment TEXT
);
```

### 4.3 Tabelle: `species_pairs`

**Zweck:** Speicherung aller Species-Paare mit Metriken

TODO: Das ist noch zu klären!!!

```sql
CREATE TABLE species_pairs (
    pair_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
  
    -- Species
    species_a TEXT NOT NULL,            -- Scientific name (alphabetisch sortiert)
    species_b TEXT NOT NULL,            -- species_a < species_b (Symmetrie)
  
    -- Ko-Okkurrenz
    weighted_cooccurrence REAL NOT NULL,    -- Gauß-gewichtete Summe
  
    -- Statistische Maße
    lift REAL,
    support REAL,                       -- = weighted_cooccurrence (redundant, aber explizit)
    confidence_a_to_b REAL,             -- P(B|A)
    confidence_b_to_a REAL,             -- P(A|B)
    jaccard REAL,                       -- Optional
  
    -- Basis-Statistik
    count_a INTEGER NOT NULL,           -- Gesamt-Detections von A im Snapshot
    count_b INTEGER NOT NULL,           -- Gesamt-Detections von B im Snapshot
    weighted_count_a REAL,              -- Gewichtete Summe (für Confidence-Berechnung)
    weighted_count_b REAL,
  
    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id),
    UNIQUE(run_id, species_a, species_b)
);

CREATE INDEX idx_pairs_run ON species_pairs(run_id);
CREATE INDEX idx_pairs_lift ON species_pairs(run_id, lift DESC);
CREATE INDEX idx_pairs_species_a ON species_pairs(run_id, species_a);
CREATE INDEX idx_pairs_species_b ON species_pairs(run_id, species_b);
```

**Wichtig:** `species_a < species_b` (alphabetisch) um Duplikate zu vermeiden

### 4.4 Tabelle: `clusters` (Placeholder für Phase 3)

TODO: Das ist noch zu klären.

**Zweck:** Spätere Clustering-Ergebnisse (Community Detection, Hierarchical)

```sql
CREATE TABLE clusters (
    cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
  
    algorithm TEXT NOT NULL,            -- 'louvain', 'hierarchical', etc.
    cluster_number INTEGER NOT NULL,    -- Cluster-Index (0, 1, 2, ...)
    species TEXT NOT NULL,              -- Member
  
    -- Optional: Cluster-Metriken
    cluster_size INTEGER,               -- Anzahl Species im Cluster
    intra_cluster_density REAL,         -- Durchschnittlicher Lift innerhalb
  
    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id),
    UNIQUE(run_id, algorithm, cluster_number, species)
);
```

**Status:** Noch nicht implementiert, Platzhalter für später

---

## 5. Implementierungs-Architektur

### 5.1 Modul-Struktur

BEACHTE: Das ist eine Idee, die im Umfang übers Ziel hinaus schießen kann:

```
source/
└── birdnet_analysis/
    ├── __init__.py
    ├── __main__.py                 # Entry point: python -m birdnet_analysis
    ├── cluster_analysis.py         # Main orchestration
    ├── proximity_calculator.py     # Phase 1: Proximity-Matrix
    ├── statistics.py               # Phase 2: Lift, Support, Confidence
    ├── clustering.py               # Phase 3: (Placeholder)
    ├── cluster_db.py               # DB-Schema & Write-Ops
    └── progress.py                 # Progress-Tracking (wie in birdnet_walker)
```

### 5.2 Haupt-Module

#### **cluster_analysis.py**

```python
def run_analysis(
    source_db_path: Path,
    output_db_path: Path,
    snapshot_date_from: Optional[date] = None,
    snapshot_date_to: Optional[date] = None,
    sigma_minutes: float = 5.0,
    min_confidence: Optional[float] = None,  # None = aus DB-Config
    use_gpu: bool = True,
    comment: Optional[str] = None
) -> int:
    """
    Führt komplette Cluster-Analyse durch.
  
    Returns:
        run_id der erstellten Analyse
    """
```

#### **proximity_calculator.py**

```python
def calculate_proximity_matrix(
    detections: pd.DataFrame,
    sigma_minutes: float,
    max_distance_minutes: float,
    use_gpu: bool = True
) -> Tuple[np.ndarray, List[str]]:
    """
    Berechnet Gauß-gewichtete Proximity-Matrix.
  
    Args:
        detections: DataFrame mit ['segment_start_local', 'scientific_name']
        sigma_minutes: Gauß-Kernel Parameter
        max_distance_minutes: Bereichsprüfgrenze
        use_gpu: Versuche GPU-Beschleunigung
  
    Returns:
        (proximity_matrix, species_list)
        proximity_matrix: Symmetrische Matrix (N×N) mit N = unique species
        species_list: Sortierte Liste der Species-Namen
    """
```

#### **statistics.py**

```python
def calculate_statistics(
    proximity_matrix: np.ndarray,
    species_list: List[str],
    detection_counts: Dict[str, int]
) -> pd.DataFrame:
    """
    Berechnet statistische Metriken für alle Paare.
  
    Returns:
        DataFrame mit Spalten:
        ['species_a', 'species_b', 'weighted_cooccurrence', 
         'lift', 'support', 'confidence_a_to_b', 'confidence_b_to_a', 
         'count_a', 'count_b']
    """
```

#### **cluster_db.py**

```python
def init_cluster_database(db_path: Path) -> None:
    """Erstellt Schema falls nicht vorhanden."""

def create_analysis_run(
    db_path: Path,
    source_db_path: Path,
    params: Dict[str, Any]
) -> int:
    """Erstellt neuen Run-Eintrag, returned run_id."""

def insert_species_pairs(
    db_path: Path,
    run_id: int,
    pairs_df: pd.DataFrame
) -> None:
    """Speichert alle Pair-Statistiken."""
```

### 5.3 CLI-Interface

**Entry Point:** `birdnet-analysis` (via pyproject.toml)

```bash
poetry run birdnet-analysis \
  /path/to/birdnet_analysis.db \
  --output cluster_results.db \
  --date-from 2025-05-01 \
  --date-to 2025-05-01 \
  --sigma 5 \
  --gpu \
  --comment "Test run - May 1st"
```

**Argumente:**

- `source_db`: Pfad zur birdnet_analysis.db (Positional)
- `--output`: Pfad zur cluster_analysis.db (Default: neben source_db)
- `--date-from`, `--date-to`: Snapshot-Zeitraum (Optional, Default: gesamte DB)
- `--sigma`: Gauß-Sigma in Minuten (Default: 5.0)
- `--min-confidence`: Override für DB-Config (Optional)
- `--gpu` / `--no-gpu`: GPU-Nutzung (Default: Auto-Detect)
- `--comment`: User-Kommentar für Run

### 5.4 Progress-Tracking

**Analog zu birdnet_walker:**

- Konsolen-Output mit Fortschrittsbalken
- Phasen:
  1. "Loading detections from DB..."
  2. "Calculating proximity matrix... [GPU/CPU]"
  3. "Computing statistics..."
  4. "Writing results to DB..."
- Geschätzte Restzeit

---

## 6. Workflow & Phasen

BEACHTE: Das ist nur eine Idee. Kann sein, man kann die Lösung deutlich sparsamer kodieren.

### Phase 1: Proximity-Matrix-Berechnung

**Input:**

```python
detections = [
    {'segment_start_local': datetime(...), 'scientific_name': 'Parus major'},
    {'segment_start_local': datetime(...), 'scientific_name': 'Cyanistes caeruleus'},
    # ...
]
```

**Prozess:**

1. Sortiere nach Zeit
2. Erstelle Species-Index (alphabetisch sortiert)
3. Initialisiere Matrix M (N×N, sparse)
4. Sliding Window über Detections:
   - Für jede Detection: Finde Nachbarn im [t-25min, t+25min]
   - Berechne Gauß-Gewichte
   - Akkumuliere in M
5. Output: Symmetrische Matrix M

**GPU-Variante:**

1. Konvertiere Timestamps zu NumPy-Array
2. Berechne Distanz-Matrix (CuPy: pairwise_distances)
3. Wende Gauß-Kernel an (element-wise)
4. Maskiere > max_distance
5. Aggregiere nach Species (GroupBy-GPU-Kernel)

**CPU-Variante:**

- Wie oben, aber mit NumPy/Pandas
- Optional: Multiprocessing über Tages-Chunks

### Phase 2: Statistische Metriken

**Input:** Proximity-Matrix M, Species-Liste, Detection-Counts

**Berechnung:**

```python
for i in range(N):
    for j in range(i+1, N):  # Nur obere Dreiecksmatrix
        species_a = species_list[i]
        species_b = species_list[j]
  
        observed = M[i, j]
        expected = count[i] * count[j] / total_effective_windows
        lift = observed / expected
  
        conf_a_to_b = observed / weighted_count[i]
        conf_b_to_a = observed / weighted_count[j]
  
        # Store to results
```

**Output:** DataFrame mit allen Metriken

### Phase 3: Clustering (Später)

**Placeholder für:**

- Graph-Konstruktion (Knoten = Species, Kanten = Lift > Threshold)
- Community Detection (Louvain, Label Propagation)
- Hierarchical Clustering (scipy.cluster.hierarchy)

**Status:** Noch nicht spezifiziert

## 10. Offene Punkte & Nächste Schritte

### Offen:

1. **Lift-Threshold:** Empirisch ermitteln (nach ersten Runs)
2. **GPU-Implementierung:** CuPy vs. Numba vs. PyTorch?
3. **Sparse Matrix:** Sinnvoll bei vielen Species (>500)?
4. **Clustering-Algorithmus:** Welcher für Phase 3?

### Nächste Schritte:

1. **Implementierung Phase 1 (Proximity Calculator)**
   - CPU-Variante zuerst
   - GPU-Variante danach
2. **Implementierung Phase 2 (Statistics)**
3. **DB-Schema erstellen & Writer**
4. **CLI-Interface**
5. **Testing mit echten Daten**

# 11. Literaturrecherche und verwandte Ansätze

## 11.1 Bioacoustic Monitoring & False Positive Analysis

### 11.1.1 Problemstellung in der Bioakustik

Die automatisierte Analyse von akustischen Monitoring-Daten steht vor ähnlichen Herausforderungen wie unser BirdNET-basiertes System. Eine umfassende Review-Studie von Kershenbaum et al. (2024, https://onlinelibrary.wiley.com/doi/10.1111/brv.13155) zeigt, dass passive akustische Monitoring-Systeme (PAM) zwar enorme Datenmengen verarbeiten können, aber systematisch mit hohen False-Positive-Raten kämpfen. Die Autoren betonen, dass selbst bei sorgfältiger Wahl der Confidence-Schwellenwerte niemals alle False Positives eliminiert werden können - es handelt sich um einen fundamentalen Trade-off zwischen Precision und Recall.

Besonders relevant für unser Projekt ist die Erkenntnis, dass False-Positive-Raten von 50% oder mehr bei automatischen Detektionssystemen durchaus akzeptabel sein können, solange diese Fehlerraten korrekt in nachfolgenden Analysen berücksichtigt werden. Marques et al. (2009) demonstrierten, dass Dichte-Schätzungen selbst bei 50% False Positives zuverlässig bleiben, wenn die Fehlerrate quantifiziert und kompensiert wird. Dies unterstützt unseren Ansatz, BirdNET mit niedriger Confidence-Schwelle laufen zu lassen (0.1 in unserem Fall) und die Filterung nachträglich durchzuführen.

Ein Beispiel ist unser Nachweis des Auerhuhns, bei dem sich Confidence nicht unbedingt als ein guter Schwellparameter dargestellt hat.

### 11.1.2 Validation Prediction - Ein statistischer Ansatz

Eine besonders interessante Methode wurde von Balantic & Donovan (2020, https://pubmed.ncbi.nlm.nih.gov/32335994/) entwickelt. Ihr "Validation Prediction"-Ansatz nutzt die prädiktive Beziehung zwischen dem Recognizer-Score (in unserem Fall: BirdNET Confidence) und der Signal-Energie eines akustischen Signals. Die Grundidee ist, dass echte Vogelrufe typischerweise eine charakteristische Beziehung zwischen Lautstärke und Erkennungswahrscheinlichkeit aufweisen, während False Positives oft von dieser Beziehung abweichen.

Die Methode funktioniert wie folgt:

1. **Feature-Extraktion**: Für jede Detection werden zusätzliche Features extrahiert:

   - Signal-Energie (amplitude)
   - Dominante Frequenz
   - Ökologische Prädiktoren (Tageszeit, Jahreszeit)
2. **Statistische Modellierung**: Ein Modell (z.B. logistische Regression) lernt die Beziehung zwischen diesen Features und der Wahrscheinlichkeit, dass eine Detection ein True Positive ist.
3. **Priorisierung**: Basierend auf diesem Modell werden Detections priorisiert für manuelle Validation. Detections mit hoher Wahrscheinlichkeit für True Positive werden bevorzugt.

In ihrer Studie mit Common Nighthawk und Ovenbird konnten Balantic & Donovan die Anzahl der manuell zu validierenden Detections um 75.7% bzw. 42.9% reduzieren, während 98% der echten Detections erhalten blieben.

**Relevanz für unser Projekt**: Wir könnten einen ähnlichen Ansatz verfolgen, wobei **temporal co-occurrence patterns** als zusätzlicher Prädiktor dienen. Wenn eine exotische Art fast ausschließlich zusammen mit einer häufigen einheimischen Art auftritt, deutet dies auf systematische Verwechslung hin.

### 11.1.3 Unsupervised Clustering zur False-Positive-Reduktion

Ein sehr aktueller Ansatz wurde von Researchers im Mai 2025 publiziert (https://www.sciencedirect.com/science/article/pii/S1574954125002316). Sie entwickelten eine Pipeline, die nach initialer CNN-basierter Detection ein zweistufiges Clustering durchführt:

1. **Segmentation**: Extrahiere akustische Features aus jedem Detection-Segment
2. **UMAP + HDBSCAN**: Iteratives Clustering der Features im niedrig-dimensionalen Raum
3. **Outlier-Detection**: Cluster mit abnormalen Charakteristiken werden als False Positives klassifiziert

Diese Methode erreichte eine 88%ige Reduktion der False Positives bei gleichzeitiger Retention von 95% der True Positives (F1-Score: 0.94). Der Clou: Das Clustering ist vollständig unsupervised und erfordert keine manuelle Annotation.

**Übertragung auf unser Problem**: Statt akustischer Features könnten wir **temporal co-occurrence patterns** als Feature-Space nutzen. Species, die in einem ungewöhnlichen zeitlichen Muster mit anderen auftreten, bilden vermutlich separate Cluster im Feature-Space und können als verdächtig markiert werden.

---

## 11.2 Species Co-occurrence Analysis in der Ökologie

### 11.2.1 Grundlagen der Ko-Okkurrenz-Analyse

In der ökologischen Forschung ist die Analyse von Artkoexistenz ein zentrales Thema. Eine fundamentale Studie von Blonder (2015, https://pmc.ncbi.nlm.nih.gov/articles/PMC4632615/) untersuchte, wie Nischen-Überlappung (niche overlap) und Umwelt-Heterogenität Ko-Okkurrenz-Muster beeinflussen.

**Wichtige Erkenntnis**: Nicht-zufällige Ko-Okkurrenz-Muster können auch **ohne direkte Interaktionen zwischen Arten** entstehen. Zwei Mechanismen sind dabei zentral:

1. **Environmental Filtering**: Arten mit ähnlichen Habitatpräferenzen treten gemeinsam auf, weil sie ähnliche Umweltbedingungen bevorzugen - nicht weil sie interagieren.
2. **Limiting Similarity**: Arten mit sehr ähnlichen ökologischen Anforderungen tendieren dazu, sich räumlich oder zeitlich zu segregieren, um Konkurrenz zu vermeiden.

Für unser Projekt bedeutet dies: **Eine hohe Ko-Okkurrenz zweier Vogelarten könnte biologisch legitim sein** (gleicher Lebensraum, gleiche Aktivitätszeiten). Die Unterscheidung zwischen echter ökologischer Ko-Okkurrenz und systematischer Modell-Verwechslung ist daher nicht trivial.

### 11.2.2 Temporal Niche Partitioning

Eine Schlüsselstudie zur zeitlichen Nischen-Partitionierung wurde von Papastamatiou et al. (2021, https://royalsocietypublishing.org/doi/10.1098/rspb.2021.0816) an marinen Räubern durchgeführt. Die Autoren zeigten, dass zeitliche Segregation - also die Aufteilung von Aktivitätszeiten - ein wichtiger Mechanismus für Koexistenz konkurrierender Arten ist.

**Methodik**: Die Autoren nutzten Kernel Density Estimation (KDE) auf Aktivitätsdaten, um zeitliche Überlappungen zu quantifizieren. Arten mit hoher zeitlicher Überlappung wurden als potenzielle Konkurrenten identifiziert, während Arten mit komplementären Aktivitätsmustern (z.B. tagaktiv vs. nachtaktiv) als koexistierend durch Nischen-Partitionierung klassifiziert wurden.

**Übertragung auf Vogelstimmen**: Wenn zwei Vogelarten tatsächlich koexistieren, erwarten wir:

- **Ähnliche Tageszeiten-Präferenzen** (beide singen morgens)
- **Unabhängige Detections** (Art A singt, Art B singt, manchmal zeitgleich)
- **Ähnliche saisonale Muster**

Bei systematischer Verwechslung erwarten wir dagegen:

- **Asymmetrische Abhängigkeit** (Art B tritt fast nur auf, wenn Art A erkannt wurde)
- **Verdächtige zeitliche Muster** (Art B erscheint im gleichen 3 Sekunden Abschnitt oder immer genau im Abschnitt davor oder nach Art A - typisch für überlappende 3s-Segmente)

### 11.2.3 Network-basierte Ansätze für Ko-Okkurrenz

Eine moderne Studie von Gauzens et al. (2019, https://www.nature.com/articles/s41598-019-56515-7) entwickelte einen Network-theoretischen Ansatz zur Analyse von Community Assembly Rules. Die Autoren konstruieren zwei Netzwerke:

1. **Co-occurrence Network**: Knoten = Arten, Kanten = gemeinsames Auftreten
2. **Functional Network**: Knoten = Arten, Kanten = funktionale Ähnlichkeit (trait similarity)

Durch Vergleich der Modularität beider Netzwerke können sie unterscheiden zwischen:

- **Environmental Filtering**: Hohe Kongruenz zwischen beiden Netzwerken (ähnliche Traits → gemeinsames Auftreten)
- **Limiting Similarity**: Niedrige Kongruenz (ähnliche Traits → räumliche/zeitliche Segregation)

**Anwendung für uns**: Wir könnten ein analoges Konzept entwickeln:

- **Co-occurrence Network**: Basierend auf unserem Lift/Support
- **Acoustic Similarity Network**: Basierend auf spektralen Features der Rufe (falls verfügbar)

Hohe Kongruenz würde auf **akustische Verwechslung** hindeuten (ähnliche Rufe → hohe Ko-Okkurrenz). Niedrige Kongruenz auf **ökologische Ko-Okkurrenz** (verschiedene Rufe, aber gemeinsam präsent).

---

## 11.3 Association Rule Mining

### 11.3.1 Grundkonzepte und Metriken

Association Rule Mining (ARM) ist eine etablierte Technik aus dem Data Mining, ursprünglich entwickelt für Market Basket Analysis. Die mathematischen Grundlagen sind gut dokumentiert (siehe Wikipedia: https://en.wikipedia.org/wiki/Association_rule_learning).

**Formale Definitionen**:

Eine Association Rule hat die Form `X → Y`, wobei X (Antecedent) und Y (Consequent) Item-Sets sind. Für Vogelstimmen wäre:

- X = {Species A wurde detektiert}
- Y = {Species B wurde detektiert}

Drei Metriken bewerten solche Regeln:

1. **Support**:

   ```
   Support(X → Y) = P(X ∪ Y) = |Transactions mit X und Y| / |Alle Transactions|
   ```

   Support misst die absolute Häufigkeit des gemeinsamen Auftretens. Hoher Support bedeutet: Die Regel ist statistisch relevant (keine zufällige Einzelbeobachtung).
2. **Confidence**:

   ```
   Confidence(X → Y) = P(Y|X) = Support(X ∪ Y) / Support(X)
   ```

   Confidence misst die bedingte Wahrscheinlichkeit. Hohe Confidence bedeutet: Wenn X auftritt, ist Y sehr wahrscheinlich.
3. **Lift**:

   ```
   Lift(X → Y) = Confidence(X → Y) / Support(Y) 
                = P(X ∪ Y) / (P(X) × P(Y))
   ```

   Lift normalisiert Confidence gegen die erwartete Wahrscheinlichkeit unter Unabhängigkeit.

   - Lift = 1: X und Y sind unabhängig
   - Lift > 1: Positive Korrelation (X und Y treten häufiger zusammen auf als erwartet)
   - Lift < 1: Negative Korrelation (X und Y meiden sich)

**Beispiel aus unserem Kontext**:

```
Kohlmeise: 1000 Detections (10% aller Zeitfenster)
Exotischer Vogel: 50 Detections (0.5% aller Zeitfenster)
Gemeinsame Detections: 45 (0.45% aller Zeitfenster)

Support(Exot → Kohlmeise) = 0.45%
Confidence(Exot → Kohlmeise) = 45/50 = 90%
Expected = 10% (Support Kohlmeise alleine)
Lift = 90% / 10% = 9.0
```

Ein Lift von 9.0 ist extrem verdächtig! Der exotische Vogel tritt 9-mal häufiger mit der Kohlmeise auf als bei Unabhängigkeit erwartet.

### 11.3.2 Temporal Association Rules

Eine Erweiterung für zeitliche Daten wurde von Chen et al. (2021, https://www.sciencedirect.com/science/article/abs/pii/S095741742101681X) für Graph-Sequenzen entwickelt. Die Autoren definieren **Temporal Association Rules**, die explizit zeitliche Offsets berücksichtigen:

```
Pattern: (Event_i, Event_j)Δt
```

wobei Δt der zeitliche Abstand zwischen den Events ist.

**Significance Measures**:

- **Temporal Support**: Wie oft tritt das Muster (Ei, Ej) mit Offset Δt auf?
- **Temporal Confidence**: Gegeben Ei, wie wahrscheinlich folgt Ej nach Δt?

**Anti-Monotonicity Property**: Die Autoren beweisen, dass Support monoton abnimmt mit zunehmender Komplexität der Regel. Dies ermöglicht effiziente Pruning-Strategien beim Mining (Apriori-Prinzip).

**Übertragung auf unser Problem**: Statt diskreter Offsets nutzen wir eine **kontinuierliche Gewichtungsfunktion** (Gauß-Kernel), was eine natürlichere Modellierung zeitlicher Nähe ermöglicht. Der Gauß-Kernel kann als "soft" temporale Assoziation verstanden werden - nahe Events haben hohe Gewichte, entfernte Events niedrige.

### 11.3.3 Null-Invariance und robuste Metriken

Eine wichtige methodische Warnung kommt aus der ARM-Community: Nicht alle Metriken sind "null-invariant". Tan et al. (2004) zeigen, dass viele populäre Metriken durch "null transactions" (Transaktionen, die weder X noch Y enthalten) beeinflusst werden.

**Null-invariante Metriken**:

- Kulczynski
- Cosine
- All-Confidence
- Max-Confidence

**NICHT null-invariant**:

- Support
- Confidence
- Lift (teilweise problematisch bei sehr seltenen Items)

Für unseren Anwendungsfall ist dies relevant, weil die meisten Zeitfenster **keine** Vogelstimmen enthalten (stille Perioden, nur Hintergrundrauschen). Diese "null transactions" sollten idealerweise keinen Einfluss auf unsere Metriken haben.

**Praktische Lösung**: Wir verwenden Lift als Hauptmetrik, aber ergänzen mit:

- Selektion der Erkennungsabschnitte: Aus der Basis-Analyse, die alle Erkennungen oberhalb eines bestimmten Confidence-Level enthält, übernehmen wir nur die Abschnitte, an denen tatsächlich Erkennungen stattgefunden haben. Ausgelassene Zeitfenster sind entsprechend der Gleichungen zu berücksichtigen: Entweder verwenden um die Normalisierung zu gewährleisten oder nicht verwenden, um Fehlzusammenhänge zu vermeiden.
- **Jaccard-Koeffizient**: `|A ∩ B| / |A ∪ B|` (inhärent null-invariant)
- **Conditional Probabilities**: `P(B|A)` und `P(A|B)` zur Asymmetrie-Detektion

---

## 11.4 Confusion Matrix Analysis für Multi-Class Classification

### 11.4.1 Standard Confusion Matrix

Die Confusion Matrix ist das Standardwerkzeug zur Evaluation von Klassifikatoren. Für Multi-Class-Probleme ist sie eine N×N-Matrix, wobei N die Anzahl der Klassen ist. Jede Zelle (i,j) enthält die Anzahl der Samples, die tatsächlich zu Klasse i gehören, aber als Klasse j prädiziert wurden.

**Diagonale**: True Positives (korrekte Klassifikation)
**Off-Diagonal**: Verwechslungen zwischen Klassen

### 11.4.2 Multiclass Confusion Matrix für Object Detection

Ein innovativer Ansatz wurde von Tenyks (2023, https://medium.com/@tenyks_blogger/multiclass-confusion-matrix-for-object-detection-6fc4b0135de6) für Object Detection entwickelt. Sie erweitern die klassische Confusion Matrix um zwei zusätzliche Kategorien:

1. **Undetected**: Annotationen ohne korrespondierende Prediction (klassische False Negatives)
2. **Ghost Predictions**: Predictions ohne korrespondierende Annotation (eine Subklasse von False Positives)
3. **Mispredicted**: Predictions mit falscher Klasse (andere Subklasse von False Positives)

**Übertragung auf Vogelstimmen**:

In unserem Fall könnten wir eine **Temporal Confusion Matrix** konstruieren:

- **Zeilen**: Tatsächlich vorhandene Arten (Ground Truth)
- **Spalten**: Detektierte Arten (BirdNET Output)
- **Zusätzliche Spalte**: "Ghost" für Detections ohne tatsächlichen Vogel
- **Zusätzliche Zeile**: "Missed" für nicht-detektierte tatsächliche Rufe

Diese Matrix würde zeigen:

- Welche Arten systematisch mit welchen verwechselt werden
- Welche Arten häufig "Ghost Predictions" verursachen
- Welche Arten häufig übersehen werden

**Problem**: Wir haben **keine Ground Truth**! Genau deshalb entwickeln wir ja die Ko-Okkurrenz-Analyse als Proxy. Die Confusion Matrix könnte nach manueller Validation einer Stichprobe erstellt werden.

### 11.4.3 Systematische Fehleranalyse

Mehrere Studien betonen die Wichtigkeit, systematische Fehler zu identifizieren statt nur aggregierte Metriken (Accuracy, F1-Score) zu berechten.

Eine Studie zu neuropsychiatrischer Diagnostik (https://www.researchgate.net/figure/Confusion-matrix-summarizing-the-errors-made-by-the-classifier-on-the-test-set_fig1_230830197) zeigt, dass **Class Imbalance** besonders problematisch ist:

- Accuracy kann irreführend hoch sein, wenn eine Klasse dominiert
- Balanced Accuracy (Mittel aus Sensitivity und Specificity) ist robuster
- Bei unbalancierten Daten sind ROC-AUC und Precision-Recall-Curves besser

**Für unser Projekt**: Häufige Arten (Kohlmeise, Amsel) dominieren die Statistik. Seltene Arten könnten systematisch falsch klassifiziert werden, ohne dass dies in der Overall-Accuracy sichtbar wird. Deshalb ist eine **species-spezifische Analyse** (unser Lift-Ansatz) wichtig.

---

## 11.5 Temporal Point Processes

### 11.5.1 Grundlagen

Temporal Point Processes (TPPs) sind ein mathematisches Framework zur Modellierung diskreter Events entlang einer kontinuierlichen Zeitachse. Eine umfassende Review (https://www.ijcai.org/proceedings/2021/0623.pdf) gibt einen Überblick über Neural TPPs.

**Kernkonzepte**:

1. **Conditional Intensity Function λ*(t)**:

   ```
   λ*(t|Ht) = lim(dt→0) P(Event in [t, t+dt) | History bis t) / dt
   ```

   Die Intensity-Funktion beschreibt die momentane Rate, mit der Events auftreten, gegeben die bisherige Historie.
2. **History Dependence**:
   Events beeinflussen die Wahrscheinlichkeit zukünftiger Events. Dies ermöglicht Modellierung von:

   - **Self-Excitation**: Ein Event erhöht die Wahrscheinlichkeit weiterer Events
   - **Mutual Excitation**: Event-Typ A triggert Event-Typ B

### 11.5.2 Hawkes Processes

Der klassische Hawkes Process (Hawkes, 1971) ist ein self-exciting TPP mit der Intensity-Funktion:

```
λ(t) = μ + Σ α·exp(-β·(t - ti))
       alle Events ti vor t
```

wobei:

- μ = Baseline-Rate (spontane Events)
- α = Excitation-Stärke (wie stark triggert ein Event weitere?)
- β = Decay-Rate (wie schnell klingt der Effekt ab?)

**Multivariate Hawkes Processes** erweitern dies auf mehrere Event-Typen mit Cross-Excitation-Matrix:

```
λk(t) = μk + Σ Σ αkj·exp(-βkj·(t - ti))
            j  ti vom Typ j
```

αkj beschreibt, wie stark Event-Typ j die Rate von Event-Typ k beeinflusst.

### 11.5.3 Neural Temporal Point Processes

Moderne Ansätze (Du et al., 2016, https://www.kdd.org/kdd2016/papers/files/rpp1081-duA.pdf) nutzen Recurrent Neural Networks (RNNs) zur Parametrisierung der Intensity-Funktion:

**RMTPP (Recurrent Marked TPP)**:

1. Encode Event-Historie mit LSTM: `ht = LSTM(ht-1, [tj, yj])`
2. Leite Intensity ab: `λ*(t) = f(ht, t)`

**Vorteile**:

- Keine parametrische Form vorgegeben
- Kann komplexe, nichtlineare Abhängigkeiten lernen
- Skaliert auf große Event-Sequenzen

### 11.5.4 Covariates in TPPs

Eine aktuelle Studie (TransFeat-TPP, 2024, https://arxiv.org/html/2407.16161v1) integriert Covariates (Kontext-Variablen) in TPPs. Für Verkehrsunfälle nutzen sie meteorologische Daten (Temperatur, Niederschlag, etc.) als Covariates.

**Feature Importance**: Das Modell kann die Wichtigkeit einzelner Covariates quantifizieren - welche Faktoren beeinflussen Event-Raten am stärksten?

**Übertragung auf Vogelstimmen**:

- **Covariates**: Tageszeit, Temperatur, Wetter, Jahreszeit
- **Event-Typen**: Species-Detections
- **Ziel**: Modelliere λSpecies_A(t | Covariates, Historie)

Wenn Species B systematisch als Co-Variate für Species A auftaucht (hohe αAB in Hawkes-Matrix), könnte dies auf Verwechslung hindeuten.

### 11.5.5 Kritische Bewertung für unser Projekt

**Vorteile von TPPs**:

- Mathematisch rigoros
- Explizite Modellierung zeitlicher Dynamik
- Kann kausale Beziehungen ("A triggert B") von Korrelationen unterscheiden

**Nachteile**:

- Hohe Komplexität (schwierig zu implementieren und zu interpretieren)
- Benötigt viele Daten für robuste Schätzung
- Computationally expensive (besonders Neural TPPs)

**Einschätzung**: Für unseren Anwendungsfall (Fehlererkennung in BirdNET) ist der **Association-Rule-Ansatz praktikabler**:

- Einfacher zu implementieren
- Leichter zu interpretieren (Lift, Support, Confidence sind intuitiv)
- Skaliert besser auf große Datenmengen (Matrix-Operationen, GPU-beschleunigbar)

TPPs könnten in einer **späteren Phase** interessant werden, wenn wir **kausale Modelle** der Vogel-Aktivität erstellen wollen (z.B. "Gesang von Art A stimuliert Antworten von Art B").

---

## 11.6 Event Co-occurrence Detection Frameworks

### 11.6.1 Formale Definition

Eine interessante Arbeit von Subramanian et al. (2016, https://arxiv.org/pdf/1603.09012) definiert ein formales Framework für Event Co-occurrence in Streams:

**Auto Co-occurrence**:
Für Events Ei, Ej aus demselben Stream:

```
AutoCoOcc(Ei, Ej, Δt) = Freq(Ei, Ej mit Offset Δt) / Freq(Ei)
```

**Cross Co-occurrence**:
Für Events aus verschiedenen Streams:

```
CrossCoOcc(Ei, Ej, Δt) = Freq(Ei, Ej mit Offset Δt) / Freq(Ei)
```

**Finite State Automaton (FSA)**:
Die Autoren entwickeln einen FSA-basierten Algorithmus, der effizient Patterns mit temporalen Constraints erkennt.

**Relevanz**: In unserem Fall sind alle Species-Detections Teil eines einzigen Event-Streams (das Mikrofon), aber wir können Species als verschiedene "Marker" betrachten. Der temporale Offset Δt wird bei uns durch den Gauß-Kernel gewichtet.

### 11.6.2 Co-occurrence Matrices mit temporalen Offsets

Die Autoren visualisieren Co-occurrence durch Heatmaps mit verschiedenen Δt-Werten:

- Δt = 0: Exakt gleichzeitige Events
- Δt = 1s, 5s, 10s, ...: Verschiedene zeitliche Abstände

**Anregung für Visualisierung**: Wir könnten eine ähnliche Darstellung entwickeln:

```
Species A × Species B × Temporal Offset
```

Dies würde zeigen, ob Verwechslungen primär bei Δt ≈ 0 auftreten (überlappende Segmente) oder auch bei größeren Offsets.

---

## 11.7 Synthese und Anwendung auf unser Projekt

### 11.7.1 Hybrid-Ansatz: Best of All Worlds

Aus der Literaturrecherche ergibt sich ein optimaler Hybrid-Ansatz für unser Projekt:

**Foundation: Association Rule Mining**

- **Basis-Algorithmus**: Gauß-gewichtete Proximity-Matrix (wie in Konzept Kapitel 2)
- **Metriken**: Lift, Support, Confidence (A→B und B→A)
- **Grund**: Etabliert, interpretierbar, skalierbar

**Enrichment 1: Ökologisches Wissen**

- **Temporal Niche Analysis**: Tageszeit-Überlappung zwischen Arten
- **Seasonal Patterns**: Monatliche Präsenz-Muster
- **Grund**: Unterscheidung ökologische Ko-Okkurrenz vs. Verwechslung

**Enrichment 2: Asymmetrie-Detektion**

- **Conditional Probability Ratio**: `max(P(B|A), P(A|B)) / min(P(B|A), P(A|B))`
- **Verdachts-Score**: `Lift × Asymmetry_Ratio`
- **Grund**: Verwechslungen zeigen oft starke Asymmetrie

**Enrichment 3: Multi-Scale Temporal Analysis**

- **Verschiedene σ-Werte**: σ ∈ {2, 5, 10, 20} Minuten
- **Scale-Dependent Patterns**: Kurzzeit- vs. Langzeit-Korrelationen
- **Grund**: Verwechslungen dominieren bei kurzen Zeitskalen

### 11.7.2 Konkrete Implementierungs-Roadmap

**Phase 1: Basis-Implementierung** (wie in Konzept Kapitel 4-6)

- Proximity-Calculator mit Gauß-Kernel (σ=5 Min)
- Lift/Support/Confidence Berechnung
- SQLite Output-Schema

**Phase 2: Erweiterte Metriken**

```python
# In statistics.py
def calculate_extended_metrics(proximity_matrix, species_list, detection_counts):
    metrics = calculate_basic_metrics()  # Lift, Support, Confidence
  
    # Asymmetrie
    metrics['asymmetry_ratio'] = metrics['conf_a_to_b'] / metrics['conf_b_to_a']
  
    # Verdachts-Score
    metrics['suspicion_score'] = metrics['lift'] * metrics['asymmetry_ratio']
  
    # Jaccard (null-invariant)
    metrics['jaccard'] = ...
  
    return metrics
```

**Phase 3: Multi-Scale Analysis**

```python
# In cluster_analysis.py
def run_multiscale_analysis(detections, sigma_values=[2, 5, 10, 20]):
    results = {}
    for sigma in sigma_values:
        proximity = calculate_proximity_matrix(detections, sigma)
        stats = calculate_statistics(proximity)
        results[f'sigma_{sigma}'] = stats
  
    # Cross-Scale Consistency Check
    consistency = analyze_scale_consistency(results)
  
    return results, consistency
```

**Phase 4: Ökologischer Context**

```python
# Neue Tabelle in cluster_analysis.db
CREATE TABLE ecological_context (
    run_id INTEGER,
    species_a TEXT,
    species_b TEXT,
    temporal_niche_overlap REAL,  -- Tageszeit-Überlappung
    seasonal_overlap REAL,         -- Monats-Überlappung
    geographic_proximity REAL,     -- Falls GPS verfügbar
    FOREIGN KEY (run_id, species_a, species_b) 
        REFERENCES species_pairs(run_id, species_a, species_b)
);
```

### 11.7.3 Validierungs-Strategie

Inspiriert von der bioacoustic Literatur, sollten wir einen iterativen Validierungs-Workflow etablieren:

**Stufe 1: Automatische Priorisierung**

```
Top-N Verdächtige Paare (höchster Suspicion Score)
```

**Stufe 2: Manuelle Stichproben-Validation**

```
Für Top-20 Paare:
  - Höre 5-10 zufällige Detections beider Arten
  - Prüfe Spectrogramme
  - Dokumentiere: Echt / Verwechslung / Unklar
```

**Stufe 3: Pattern-Extraktion**

```
Aus validierten Paaren:
  - Welche Merkmale haben echte Verwechslungen?
  - Können wir Regeln ableiten?
  - Feedback in Modell-Retraining (langfristig)
```

**Stufe 4: Ground-Truth-Erweiterung**

```
Validierte Paare als Ground Truth für:
  - Confusion Matrix Erstellung
  - Benchmark für zukünftige Algorithmen
```

### 11.7.4 Offene Forschungsfragen

Die Literaturrecherche hat auch Fragen aufgeworfen, die wir im Projekt adressieren könnten:

1. **Optimal σ-Wahl**: Gibt es eine "optimale" Zeitskala für Verwechslungs-Detektion?

   - Hypothese: Verwechslungen dominieren bei σ < 5 Min (überlappende Segmente)
   - Test: Multi-Scale-Analyse mit systematischer Evaluation
2. **Lift vs. Conditional Probability**: Welche Metrik ist robuster für seltene Arten?

   - Hypothese: Lift ist anfällig bei sehr seltenen Arten (kleine Nenner)
   - Alternative: Bayesian posterior mit Prior auf typische Ko-Okkurrenz-Raten
3. **Transfer Learning**: Können wir Verwechslungs-Pattern von einem Standort auf andere übertragen?

   - Hypothese: Akustische Verwechslungen (ähnliche Rufe) sind standort-unabhängig
   - Test: Cross-Validation über verschiedene Datenbanken
4. **Temporal Dynamics**: Ändern sich Verwechslungs-Pattern über die Saison?

   - Hypothese: Verwechslungen mit Zugvögeln treten nur während Migrationsperioden auf
   - Test: Monatliche Analyse-Runs, Vergleich der Lift-Werte

---

## 11.8 Zusammenfassung und Ausblick

Die Literaturrecherche hat gezeigt, dass unser geplanter Ansatz gut fundiert ist in mehreren etablierten Forschungsbereichen:

**Validierung unseres Ansatzes**:

- ✅ Lift/Support/Confidence sind etablierte Metriken (Association Rule Mining)
- ✅ Zeitliche Gewichtung ist biologisch plausibel (Temporal Niche Theory)
- ✅ Ko-Okkurrenz-Analyse wird in der Ökologie intensiv genutzt
- ✅ Ähnliche Probleme in Bioacoustic Community (False Positive Detection)

**Neue Erkenntnisse**:

- 🆕 Asymmetrie-Detektion via P(B|A) / P(A|B) als starker Indikator
- 🆕 Multi-Scale-Analyse könnte Verwechslungen von ökologischer Ko-Okkurrenz trennen
- 🆕 Null-Invarianz wichtig - Jaccard als robuste Ergänzung zu Lift
- 🆕 Network-Visualisierung könnte Verwechslungs-Cluster sichtbar machen

**Nächste Schritte**:

1. **Implementierung Basis-Algorithmus** (Kapitel 4-6 des Konzepts)
2. **Test mit 1-Tages-Snapshot** (realistische Datenmenge)
3. **Manuelle Validation** (Top-20 verdächtige Paare)
4. **Iteration** basierend auf Feedback

**Langfristige Vision**:

- Aufbau einer **Verwechslungs-Datenbank** als Community-Ressource
- Integration in BirdNET-Workflow als **Post-Processing-Step**
- Entwicklung von **Model-Agnostic Correction-Faktoren** für häufige Verwechslungen

Die Literatur zeigt: Wir bewegen uns auf solidem wissenschaftlichen Fundament, kombinieren aber Ansätze aus verschiedenen Disziplinen auf innovative Weise. Dies könnte sowohl für die Bioakustik-Community als auch für die ökologische Forschung wertvolle Erkenntnisse liefern.
