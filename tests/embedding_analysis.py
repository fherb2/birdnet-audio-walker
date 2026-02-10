# %% [markdown]
# # BirdNET Embedding-Analyse: Verschiedene Rufe einer Art
#
# Dieses Notebook analysiert die 1024-dimensionalen BirdNET-Embeddings einer ausgewählten Vogelart.
#
# **Workflow:**
# 1. Embeddings effizient aus HDF5 laden (nur die benötigten via SQLite-Indices)
# 2. Dimensionsreduktion mit UMAP (1024D → 2D)
# 3. Clustering mit DBSCAN (automatische Cluster-Erkennung)
# 4. Interaktive Visualisierung mit Plotly
# 5. Cluster-Analyse und Statistiken

# %% [markdown]
# ## 1. Setup & Dependencies

# %%
# Standard libraries
import sqlite3
from pathlib import Path

# Data processing
import numpy as np
import pandas as pd
import h5py

# Machine Learning
import umap
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

# Visualization
import plotly.express as px
import plotly.graph_objects as go

# Plotly Renderer für JupyterLab explizit setzen
import plotly.io as pio
pio.renderers.default = 'jupyterlab'

print("✓ Alle Dependencies erfolgreich importiert")

# %% [markdown]
# ## 2. Input-Parameter
#
# **Hier die Werte aus der Streamlit-Exploration eintragen:**

# %%
# ============================================================
# INPUT: Von Dir nach Streamlit-Exploration anzupassen
# ============================================================

# Pfad zum Ordner mit den Datenbanken
RECORDING_FOLDER = "/home/hostuser/massdata/audiomothes/243B1F0264881CE0-2025"

# Scientific Name der zu analysierenden Art (aus Streamlit)
SPECIES_NAME = "Parus major"

# Optional: Confidence-Filter (nur Detections >= diesem Wert)
MIN_CONFIDENCE = 0.5  # Oder None für alle Detections

# ============================================================

# Automatische Pfad-Konstruktion
DB_PATH = Path(RECORDING_FOLDER) / "birdnet_analysis.db"
HDF5_PATH = Path(RECORDING_FOLDER) / "birdnet_embeddings.h5"

# Validierung
assert DB_PATH.exists(), f"SQLite-DB nicht gefunden: {DB_PATH}"
assert HDF5_PATH.exists(), f"HDF5-Datei nicht gefunden: {HDF5_PATH}"

print(f"✓ Datenbanken gefunden:")
print(f"  SQLite: {DB_PATH}")
print(f"  HDF5:   {HDF5_PATH}")
print(f"\n✓ Analysiere Species: {SPECIES_NAME}")
if MIN_CONFIDENCE:
    print(f"  Min. Confidence: {MIN_CONFIDENCE}")

# %% [markdown]
# ## 3. Detections aus SQLite laden
#
# Wir laden nur die Metadaten (ID, embedding_idx, confidence) für die gewählte Species.

# %%
# SQLite-Verbindung öffnen
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Query: Detections für gewählte Species mit Embeddings
query = """
    SELECT 
        id,
        embedding_idx,
        confidence,
        segment_start_local,
        filename
    FROM detections
    WHERE scientific_name = ?
    AND embedding_idx IS NOT NULL
"""

params = [SPECIES_NAME]

# Optional: Confidence-Filter
if MIN_CONFIDENCE is not None:
    query += " AND confidence >= ?"
    params.append(MIN_CONFIDENCE)

query += " ORDER BY confidence DESC"

# Als DataFrame laden
detections_df = pd.read_sql_query(query, conn, params=params)
conn.close()

# Info ausgeben
print(f"✓ {len(detections_df)} Detections gefunden")
print(f"\nConfidence-Statistiken:")
print(detections_df['confidence'].describe())

# Erste Zeilen anzeigen
detections_df.head()

# %% [markdown]
# ## 4. Embeddings effizient aus HDF5 laden
#
# **Wichtig:** Wir nutzen HDF5-Slicing und laden nur die benötigten Embeddings (nicht das ganze Array!)

# %%
# Embedding-Indices extrahieren
embedding_indices = detections_df['embedding_idx'].values

print(f"Lade {len(embedding_indices)} Embeddings aus HDF5...")

# HDF5 öffnen und nur benötigte Embeddings laden
with h5py.File(HDF5_PATH, 'r') as f:
    dataset = f['embeddings']
    
    # Info über Dataset
    print(f"\nHDF5-Dataset Info:")
    print(f"  Shape: {dataset.shape}")
    print(f"  Dtype: {dataset.dtype}")
    print(f"  Compression: {dataset.compression}")
    
    # EFFIZIENTES LADEN: Nur benötigte Zeilen
    # HDF5 braucht sortierte Indices!
    
    # 1. Original-Reihenfolge merken
    original_order = np.argsort(np.argsort(embedding_indices))
    
    # 2. Indices sortieren
    sorted_indices = np.sort(embedding_indices)
    
    # 3. Embeddings in sortierter Reihenfolge laden
    embeddings_sorted = dataset[sorted_indices]
    
    # 4. Zurück in ursprüngliche Reihenfolge bringen
    embeddings = embeddings_sorted[original_order]

# %% [markdown]
# ## 5. UMAP: Dimensionsreduktion (1024D → 2D)
#
# UMAP (Uniform Manifold Approximation and Projection) reduziert die 1024 Dimensionen auf 2D für Visualisierung.
#
# **Parameter:**
# - `n_neighbors`: Größere Werte → mehr globale Struktur (15-50 typisch)
# - `min_dist`: Kleinere Werte → engere Cluster (0.0-0.3 typisch)
# - `metric`: cosine ist gut für BirdNET-Embeddings

# %%
# ============================================================
# UMAP-Parameter (zum Experimentieren)
# ============================================================
UMAP_N_NEIGHBORS = 15      # 5-50: größer = mehr globale Struktur
UMAP_MIN_DIST = 0.1        # 0.0-0.5: kleiner = engere Cluster
UMAP_METRIC = 'cosine'     # 'cosine' oder 'euclidean'
UMAP_RANDOM_STATE = 42     # Für Reproduzierbarkeit
# ============================================================

print(f"Starte UMAP mit {len(embeddings)} Embeddings...")
print(f"Parameter: n_neighbors={UMAP_N_NEIGHBORS}, min_dist={UMAP_MIN_DIST}, metric={UMAP_METRIC}")

# UMAP ausführen
reducer = umap.UMAP(
    n_neighbors=UMAP_N_NEIGHBORS,
    min_dist=UMAP_MIN_DIST,
    n_components=2,
    metric=UMAP_METRIC,
    random_state=UMAP_RANDOM_STATE
)

embedding_2d = reducer.fit_transform(embeddings)

print(f"\n✓ UMAP abgeschlossen: {embedding_2d.shape}")
print(f"  X-Range: [{embedding_2d[:, 0].min():.2f}, {embedding_2d[:, 0].max():.2f}]")
print(f"  Y-Range: [{embedding_2d[:, 1].min():.2f}, {embedding_2d[:, 1].max():.2f}]")

# %% [markdown]
# ## 6. DBSCAN: Clustering
#
# DBSCAN findet automatisch Cluster beliebiger Form und markiert Outlier als "Noise" (Label -1).
#
# **Parameter:**
# - `eps`: Maximale Distanz zwischen Punkten im gleichen Cluster (0.3-2.0 typisch für UMAP)
# - `min_samples`: Minimale Anzahl Punkte für ein Cluster (5-20 typisch)
# - `metric`: euclidean für UMAP-2D-Space

# %%
# ============================================================
# DBSCAN-Parameter (zum Experimentieren)
# ============================================================
DBSCAN_EPS = 0.5           # 0.3-2.0: größer = weniger, größere Cluster
DBSCAN_MIN_SAMPLES = 10    # 5-20: größer = strenger (mehr Noise)
# ============================================================

print(f"Starte DBSCAN Clustering...")
print(f"Parameter: eps={DBSCAN_EPS}, min_samples={DBSCAN_MIN_SAMPLES}")

# DBSCAN auf UMAP-2D-Space
clusterer = DBSCAN(
    eps=DBSCAN_EPS,
    min_samples=DBSCAN_MIN_SAMPLES,
    metric='euclidean'
)

cluster_labels = clusterer.fit_predict(embedding_2d)

# Statistiken
n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
n_noise = list(cluster_labels).count(-1)

print(f"\n✓ Clustering abgeschlossen:")
print(f"  Anzahl Cluster: {n_clusters}")
print(f"  Noise-Punkte: {n_noise} ({n_noise/len(cluster_labels)*100:.1f}%)")
print(f"  Cluster-Sizes:")
for label in sorted(set(cluster_labels)):
    if label == -1:
        continue
    count = list(cluster_labels).count(label)
    print(f"    Cluster {label}: {count} Detections")

# %% [markdown]
# ## 7. Daten für Visualisierung vorbereiten

# %%
# DataFrame für Plotly erstellen
plot_df = detections_df.copy()
plot_df['umap_x'] = embedding_2d[:, 0]
plot_df['umap_y'] = embedding_2d[:, 1]
plot_df['cluster'] = cluster_labels

# Cluster-Label als String (für bessere Plotly-Legende)
plot_df['cluster_label'] = plot_df['cluster'].apply(
    lambda x: 'Noise' if x == -1 else f'Cluster {x}'
)

print(f"✓ Plot-DataFrame vorbereitet: {len(plot_df)} Zeilen")
plot_df.head()

# %% [markdown]
# ## 8. Interaktive Visualisierung mit Plotly
#
# **Hover-Infos:** Detection-ID, Confidence, Cluster, Filename, Zeit

# %%
# Plotly Scatter Plot
fig = px.scatter(
    plot_df,
    x='umap_x',
    y='umap_y',
    color='cluster_label',
    size='confidence',
    hover_data={
        'id': True,
        'confidence': ':.3f',
        'filename': True,
        'segment_start_local': True,
        'umap_x': False,  # Aus Hover entfernen
        'umap_y': False,
        'cluster_label': False  # Steht schon in Legende
    },
    title=f"UMAP Projektion: {SPECIES_NAME} ({len(plot_df)} Detections, {n_clusters} Cluster)",
    labels={'umap_x': 'UMAP Dimension 1', 'umap_y': 'UMAP Dimension 2'},
    width=1200,
    height=800
)

# Noise-Punkte kleiner und grau
fig.for_each_trace(
    lambda trace: trace.update(marker={'color': 'lightgray', 'size': 3}) 
    if trace.name == 'Noise' else ()
)

fig.update_layout(
    legend=dict(title='Cluster'),
    hovermode='closest'
)

fig.show()

print("\n✓ Interaktiver Plot erstellt")
print("  Tipp: Zoom, Pan, Hover über Punkte für Details")

# %% [markdown]
# ## 9. Cluster-Statistiken
#
# Detaillierte Analyse der gefundenen Cluster

# %%
# Statistiken pro Cluster berechnen
cluster_stats = plot_df.groupby('cluster_label').agg({
    'id': 'count',
    'confidence': ['mean', 'std', 'min', 'max']
}).round(3)

cluster_stats.columns = ['Count', 'Avg_Conf', 'Std_Conf', 'Min_Conf', 'Max_Conf']
cluster_stats = cluster_stats.sort_values('Count', ascending=False)

print("Cluster-Statistiken:")
print(cluster_stats)

# Als DataFrame für bessere Darstellung
cluster_stats

# %%
# HTML-Export für Browser
fig.write_html("/workspace/embedding_plot.html")
print("✓ Gespeichert: /workspace/embedding_plot.html")

# %%




# %% [markdown]
# ## 10. Sample-Detections pro Cluster
#
# Zeigt repräsentative Detections aus jedem Cluster (höchste Confidence)

# %%
# Für jeden Cluster: Top 3 Detections nach Confidence
print("Top-3 Detections pro Cluster (nach Confidence):\n")

for label in sorted(set(cluster_labels)):
    cluster_name = 'Noise' if label == -1 else f'Cluster {label}'
    cluster_data = plot_df[plot_df['cluster'] == label].nlargest(3, 'confidence')
    
    print(f"\n{cluster_name}:")
    print("-" * 80)
    for idx, row in cluster_data.iterrows():
        print(f"  ID: {row['id']:6d} | Conf: {row['confidence']:.3f} | "
              f"File: {row['filename'][:30]:30s} | Time: {row['segment_start_local']}")

# %% [markdown]
# ## 11. Export für weitere Analyse
#
# Optional: Cluster-Zuordnungen speichern

# %%
# Cluster-Zuordnungen als CSV exportieren
output_file = Path(RECORDING_FOLDER) / f"{SPECIES_NAME.replace(' ', '_')}_clusters.csv"

export_df = plot_df[['id', 'filename', 'segment_start_local', 'confidence', 'cluster', 'cluster_label']]
export_df.to_csv(output_file, index=False)

print(f"✓ Cluster-Zuordnungen exportiert nach:")
print(f"  {output_file}")

# %% [markdown]
# ## Fertig! 🎉
#
# **Nächste Schritte:**
# - Parameter anpassen (UMAP, DBSCAN) und neu ausführen
# - Andere Species analysieren
# - Audio-Snippets aus verschiedenen Clustern anhören (via birdnet-play)
# - False-Positives identifizieren (meist in eigenen Clustern oder Noise)


# %%
