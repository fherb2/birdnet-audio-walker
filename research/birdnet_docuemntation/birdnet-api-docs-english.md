```
birdnet/
├── acoustic-models/
│   └── v2.4/
│       ├── pb/
│       │   ├── model-fp32/
│       │   └── labels/
│       └── tf/
│           ├── model-fp32.tflite
│           ├── model-fp16.tflite
│           └── labels/
└── geo-models/
    └── v2.4/
        └── pb/
            ├── model-fp32/
            └── labels/
```

When a model has already been downloaded, BirdNET checks on loading whether it's available locally and uses the cached version. If not, it's automatically downloaded from Zenodo or another configured server.

You can programmatically retrieve the app data directory:

```python
from birdnet.utils.local_data import get_birdnet_app_data_folder

app_dir = get_birdnet_app_data_folder()
print(f"BirdNET data is located at: {app_dir}")
```

If you want to manually download and store models at a different location for space or security reasons, you can use `load_custom()` and specify the explicit path.

### Logging

BirdNET uses the standard Python logging framework. By default, logging is activated at INFO level, with messages output to the console. You can adjust the log level:

```python
import logging
from birdnet.utils.logging_utils import init_package_logger

# Activate debug messages
init_package_logger(logging.DEBUG)

# Show only warnings and errors
init_package_logger(logging.WARNING)

# Completely disable logging
init_package_logger(logging.CRITICAL + 1)
```

During inference sessions, detailed logs are stored in temporary files, which are helpful for error diagnosis in case of problems. When `show_stats="benchmark"` is set, these logs are also copied to the benchmark directory.

Loggers follow a hierarchical naming structure:

```
birdnet (main logger)
├── birdnet.session_<ID> (session logger)
│   ├── birdnet.session_<ID>.producer
│   ├── birdnet.session_<ID>.worker
│   └── birdnet.session_<ID>.analyzer
```

You can add your own handlers to integrate logs into your application:

```python
import logging

birdnet_logger = logging.getLogger("birdnet")
handler = logging.FileHandler("my_birdnet.log")
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
birdnet_logger.addHandler(handler)
```

### Supported Audio Formats

BirdNET internally uses the SoundFile library (libsndfile) to load audio files. Supported formats include:

WAV, FLAC, OGG, MP3 (via MPEG decoder), AIFF, AU, CAF, and many more. The complete list can be found in `birdnet.utils.helper.SF_FORMATS`. Proprietary formats like AAC, WMA, or M4A are not supported without corresponding system codecs.

If you're unsure whether a file is supported, you can use the check function:

```python
from pathlib import Path
from birdnet.utils.helper import is_supported_audio_file

file_path = Path("/path/to/audio.mp3")
if is_supported_audio_file(file_path):
    print("File is supported")
else:
    print("File is NOT supported")
```

For recursively searching all supported audio files in a directory:

```python
from pathlib import Path
from birdnet.utils.helper import get_supported_audio_files_recursive

audio_dir = Path("/path/to/audio/folder")
all_audio_files = list(get_supported_audio_files_recursive(audio_dir))
print(f"Found: {len(all_audio_files)} audio files")
```

This is useful when you have a folder with mixed file types and only want to process the audio files.

---

## Performance Optimization and Best Practices

Efficient processing of large amounts of audio data requires understanding of internal processes and some best practices. In this section, we'll examine how the inference pipeline works and how you can optimally set parameters.

### The Inference Pipeline in Detail

When you call `predict()` or `encode()`, a complex pipeline with multiple parallel processes starts internally. Understanding this pipeline helps you identify bottlenecks and choose parameters correctly.

**Producer Processes:** Producers read audio files from disk, perform resampling to the model sample rate (48 kHz), apply bandpass filters, and split the audio into overlapping 3-second segments. These segments are written to a shared memory ring buffer from which workers can retrieve them. Producers work asynchronously to hide I/O wait times.

**Ring Buffer:** The ring buffer is a circular buffer in shared memory that decouples producers and workers. It has a fixed number of slots (calculated from `n_workers * batch_size * prefetch_ratio`). Producers fill slots, workers empty them. Semaphores synchronize access and prevent race conditions. The ring buffer enables efficient zero-copy sharing between processes.

**Worker Processes:** Workers each load their own copy of the model and process batches of segments from the ring buffer. Each worker operates independently and writes its results to a shared result queue. Workers are CPU or GPU bound, depending on the backend.

**Analyzer Process:** The analyzer runs in the main process and coordinates the pipeline. It manages the input queue for producers, collects results from workers, and aggregates them into a final result object. The analyzer also monitors progress and can abort the pipeline if needed.

**Data Flow:**

```
Audio Files
    ↓
[Producer 1] [Producer 2] ... [Producer N]
    ↓         ↓                 ↓
    +---------+-----------------+
              ↓
      [Ring Buffer (Shared Memory)]
              ↓
    +---------+-----------------+
    ↓         ↓                 ↓
[Worker 1] [Worker 2] ... [Worker M]
    ↓         ↓                 ↓
    +---------+-----------------+
              ↓
        [Results Queue]
              ↓
          [Analyzer]
              ↓
        Result Object
```

### Parameter Tuning for Different Scenarios

**Scenario 1: Few Large Files (e.g., 10 files of 1 hour each):**

Here I/O is not a bottleneck but model inference. Use:

```python
result = model.predict(
    files,
    n_producers=1,        # One producer is enough
    n_workers=8,          # Many workers for parallelism
    batch_size=64,        # Large batches for GPU utilization
    prefetch_ratio=2,     # Moderate prefetching
    device="GPU:0"
)
```

**Scenario 2: Many Small Files (e.g., 10,000 files of 10 seconds each):**

I/O can become a bottleneck. Use:

```python
result = model.predict(
    files,
    n_producers=4,        # Multiple producers for parallel reading
    n_workers=4,          # Fewer workers since files are short
    batch_size=16,        # Smaller batches for faster throughput
    prefetch_ratio=3,     # Higher prefetching to fill I/O gaps
    device="CPU"
)
```

**Scenario 3: Real-time Processing (Audio Stream):**

Minimal latency is important:

```python
# Process short chunks as arrays
with model.predict_session(
    n_producers=1,
    n_workers=1,
    batch_size=1,         # No batching delay
    overlap_duration_s=0, # No overlap for fastest processing
    device="GPU:0"        # GPU for low latency
) as session:
    while audio_stream_active:
        chunk = get_next_audio_chunk()  # E.g., 3 seconds
        result = session.run_arrays([(chunk, 48000)])
        process_result(result)
```

**Scenario 4: GPU with Multiple Devices:**

Distribute workers across GPUs:

```python
result = model.predict(
    files,
    n_producers=2,
    n_workers=4,
    batch_size=128,
    device=["GPU:0", "GPU:1", "GPU:0", "GPU:1"],  # Alternating on 2 GPUs
)
```

Each worker is assigned to the corresponding device from the list. Ensure the list has length `n_workers`.

### Memory Management

Memory requirements depend mainly on the following factors:

**Ring Buffer Size:** `n_workers * batch_size * prefetch_ratio * segment_size * 4 bytes (Float32)`

For `n_workers=4`, `batch_size=32`, `prefetch_ratio=2`, and `segment_size=144,000` samples (3s at 48 kHz), this gives:

`4 * 32 * 2 * 144,000 * 4 ≈ 147 MB`

**Model Memory:** Each worker loads a model copy. The acoustic FP32 model requires about 50-120 MB per copy (depending on backend). With 4 workers, that's 200-480 MB.

**Result Memory:** Results are aggregated in the main process. Size depends on the number of predictions. For a one-hour recording with 1.5s overlap (`speed=1.0`), you get about 2400 segments. With `top_k=5`, that's 12,000 predictions. Each prediction stores:

- Input index (2-4 bytes)
- Segment index (2-4 bytes)
- Start/end time (8 bytes Float64)
- Species ID (2-4 bytes)
- Confidence (4 bytes Float32)

≈ 20-30 bytes per prediction, so ~360 KB for 12,000 predictions. For 100 hours, that's ~36 MB.

**Total Memory Requirements:** For typical configurations, you should expect 1-3 GB RAM, depending on the number of workers and batch size.

If you hit memory limits, reduce `prefetch_ratio`, `batch_size`, or `n_workers`. Or set `max_audio_duration_min` to process very long files in chunks (though this leads to multiple passes).

### Benchmarking

For detailed performance analysis, use `show_stats="benchmark"`:

```python
result = model.predict(
    files,
    n_workers=4,
    batch_size=32,
    show_stats="benchmark"
)
```

After processing, detailed metrics are output:

- **Wall Clock Time:** Total duration of processing
- **Audio Duration:** Sum of processed audio lengths
- **Real-time Factor:** Audio duration / wall clock time (e.g., 10.0 means 10 hours audio in 1 hour processed)
- **Segment Throughput:** Segments per second
- **Memory Usage:** Size of ring buffer and results

This information is also saved in a benchmark file in the app data directory, so you can compare different configurations.

---

## Advanced Use Cases

### Custom Confidence Thresholds

In some scenarios, you want to use different thresholds for different species. For example, common species like blackbird or great tit could get higher thresholds to reduce false positives, while rare species get lower thresholds to not miss any detections:

```python
custom_thresholds = {
    "Amsel_Turdus merula": 0.5,
    "Kohlmeise_Parus major": 0.5,
    "Rare Species_Species rara": 0.1,
}

result = model.predict(
    files,
    default_confidence_threshold=0.3,
    custom_confidence_thresholds=custom_thresholds,
    top_k=None  # Return all species, filtering via thresholds
)
```

Species without an entry in `custom_thresholds` use `default_confidence_threshold`.

### Custom Species Lists

If you're only interested in a subset of species, you can pass a custom species list. This doesn't reduce computation time (the model always calculates all outputs), but it reduces result size and simplifies post-processing:

```python
target_species = [
    "Amsel_Turdus merula",
    "Nachtigall_Luscinia megarhynchos",
    "Rotkehlchen_Erithacus rubecula",
]

result = model.predict(
    files,
    custom_species_list=target_species,
    top_k=3
)
```

Alternatively, you can also specify a path to a text file containing species names (one name per line):

```python
result = model.predict(
    files,
    custom_species_list=Path("/path/to/target_species.txt"),
    top_k=3
)
```

### Batch Processing Large Datasets

When you want to process thousands of files, it can make sense to split them into chunks and save intermediate results between chunks:

```python
from pathlib import Path
import numpy as np

all_files = list(Path("/audio/dataset").rglob("*.wav"))
chunk_size = 1000

with model.predict_session(
    n_workers=8,
    batch_size=64,
    device="GPU:0",
    show_stats="progress"
) as session:
    for i in range(0, len(all_files), chunk_size):
        chunk = all_files[i:i+chunk_size]
        print(f"Processing chunk {i//chunk_size + 1}/{(len(all_files)-1)//chunk_size + 1}")
        
        result = session.run(chunk)
        result.save(f"results_chunk_{i//chunk_size}.npz")
        
        # Optional: Free memory
        del result
```

Later you can combine or analyze chunk results separately.

### Custom Progress Callbacks

If you're developing a GUI or dashboard, you can register your own progress callbacks:

```python
from birdnet.acoustic.inference.core.perf_tracker import AcousticProgressStats

def my_progress_callback(stats: AcousticProgressStats):
    progress_percent = (stats.segments_processed / stats.segments_total) * 100
    eta_seconds = stats.estimated_time_remaining
    
    # Update GUI elements
    update_progress_bar(progress_percent)
    update_eta_label(f"Remaining: {eta_seconds:.0f}s")
    
    # Optional: Logging
    print(f"Progress: {progress_percent:.1f}% | "
          f"Speed: {stats.segments_per_second:.1f} seg/s")

result = model.predict(
    files,
    show_stats="progress",  # Activates progress tracking
    progress_callback=my_progress_callback
)
```

The `AcousticProgressStats` object contains the following attributes:

- `segments_total`: Total number of segments to process
- `segments_processed`: Number of already processed segments
- `elapsed_time`: Elapsed time in seconds
- `estimated_time_remaining`: Estimated remaining time in seconds
- `segments_per_second`: Current processing speed

The callback is called approximately every 1-2 seconds, so you can update your UI smoothly without creating too much overhead.

---

## Complete Workflow Examples

In this section, we'll walk through three realistic application scenarios from start to finish to show how BirdNET's various components work together.

### Example 1: Acoustic Bird Species Recognition with Geographic Filtering

**Scenario:** You've made audio recordings from a forest area in Germany (coordinates: 51.1657°N, 10.4515°E) and want to know which bird species can be heard in May (week 20). You only want to consider species that plausibly occur in this region and season.

```python
from pathlib import Path
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4
from birdnet.geo.models.v2_4.model import GeoModelV2_4
from birdnet.geo.models.v2_4.backends.pb import GeoPBBackendV2_4

# Step 1: Geographic prediction
print("Loading geographic model...")
geo_model = GeoModelV2_4.load(
    lang="en_us",
    backend_type=GeoPBBackendV2_4,
    backend_kwargs={}
)

print("Calculating likely species for location...")
geo_prediction = geo_model.predict(
    latitude=51.1657,
    longitude=10.4515,
    week=20,
    min_confidence=0.05,  # Only species with >5% probability
    device="CPU"
)

# Extract list of likely species
likely_species = set(
    geo_prediction.species_list[~geo_prediction.species_masked]
)
print(f"Geographically plausible species: {len(likely_species)}")

# Step 2: Load acoustic model
print("\nLoading acoustic model...")
acoustic_model = AcousticModelV2_4.load(
    lang="en_us",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Step 3: Collect audio files
audio_dir = Path("/path/to/recordings")
audio_files = list(audio_dir.glob("*.wav"))
print(f"Found audio files: {len(audio_files)}")

# Step 4: Acoustic analysis with geographic filtering
print("\nStarting analysis...")
acoustic_result = acoustic_model.predict(
    audio_files,
    custom_species_list=likely_species,  # Only geographically plausible species
    top_k=5,
    overlap_duration_s=1.5,  # High temporal resolution
    apply_sigmoid=True,
    sigmoid_sensitivity=1.2,  # Slightly more conservative predictions
    default_confidence_threshold=0.25,
    n_producers=2,
    n_workers=4,
    batch_size=32,
    device="GPU:0",
    show_stats="progress"
)

# Step 5: Export and analyze results
acoustic_result.to_csv("detections_may.csv")
acoustic_result.save("detections_may.npz", compress=True)

print(f"\nAnalysis complete!")
print(f"Total detections: {len(acoustic_result.species_ids)}")
print(f"Analyzed audio duration: {acoustic_result.input_durations.sum() / 60:.1f} minutes")

# Step 6: Determine top species
import pandas as pd

df = pd.read_csv("detections_may.csv")
top_species = df.groupby("species_name").size().sort_values(ascending=False).head(10)

print("\nTop 10 detected species:")
for species, count in top_species.items():
    print(f"  {species}: {count} detections")
```

**Workflow Explanation:**

First, we load the geographic model and calculate probabilities for all species at the given location and time. We filter for species with at least 5% probability to get a realistic candidate list. We then pass this list as `custom_species_list` to the acoustic model, so only these species can appear in results. This dramatically reduces false-positive detections – a nightingale won't be incorrectly identified as a tropical species that doesn't occur at the location at all.

The acoustic analysis uses moderate overlap for good temporal resolution and slightly increased sigmoid sensitivity to enhance precision. Parallel processing with GPU significantly accelerates the analysis. At the end, we export results as CSV for easy further processing and as NPZ for later Python analyses.

### Example 2: Embedding Extraction for Clustering

**Scenario:** You want to automatically group audio recordings by acoustic similarity without relying on species classification. To do this, you extract embeddings and perform clustering.

```python
from pathlib import Path
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4

# Step 1: Load model
print("Loading acoustic model...")
model = AcousticModelV2_4.load(
    lang="en_us",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Step 2: Collect audio files
audio_dir = Path("/path/to/recordings")
audio_files = list(audio_dir.glob("*.wav"))[:100]  # Only first 100 for demo
print(f"Processing {len(audio_files)} files...")

# Step 3: Extract embeddings
embedding_result = model.encode(
    audio_files,
    overlap_duration_s=0,  # No overlap for clustering
    n_producers=2,
    n_workers=4,
    batch_size=32,
    device="GPU:0",
    show_stats="progress"
)

# Step 4: Prepare embeddings
embeddings = embedding_result.embeddings  # Shape: (n_files, n_segments_max, 1024)
embeddings_masked = embedding_result.embeddings_masked  # Mask for valid embeddings

# Use only valid embeddings
valid_embeddings = embeddings[~embeddings_masked]
print(f"Valid embeddings: {valid_embeddings.shape[0]}")

# Optional: Dimensionality reduction for visualization (PCA to 50 dimensions)
from sklearn.decomposition import PCA
pca = PCA(n_components=50, random_state=42)
embeddings_reduced = pca.fit_transform(valid_embeddings)
print(f"Variance explained by PCA: {pca.explained_variance_ratio_.sum():.2%}")

# Step 5: Clustering with DBSCAN
print("\nPerforming clustering...")
scaler = StandardScaler()
embeddings_scaled = scaler.fit_transform(embeddings_reduced)

clustering = DBSCAN(eps=2.5, min_samples=5, metric='euclidean')
labels = clustering.fit_predict(embeddings_scaled)

n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
n_noise = list(labels).count(-1)

print(f"Found clusters: {n_clusters}")
print(f"Noise points: {n_noise}")

# Step 6: Analyze clusters
cluster_sizes = {}
for label in set(labels):
    if label != -1:
        cluster_sizes[label] = (labels == label).sum()

print("\nCluster sizes:")
for cluster_id, size in sorted(cluster_sizes.items(), key=lambda x: x[1], reverse=True):
    print(f"  Cluster {cluster_id}: {size} segments")

# Step 7: Visualization (optional)
# Here you could use t-SNE or UMAP for 2D projection
# and visualize the clusters

# Step 8: Save embeddings for later use
embedding_result.save("embeddings_cluster.npz", compress=True)
```

**Workflow Explanation:**

This workflow demonstrates how embeddings can be used for unsupervised learning. After extracting embeddings, we apply PCA for dimensionality reduction, which accelerates clustering and reduces noise. DBSCAN clustering automatically groups similar audio segments without us having to specify the number of clusters beforehand. Noise points (label -1) are segments that couldn't be assigned to any cluster, often background noise or very rare sounds.

You could extend this workflow by selecting representative samples for each cluster and manually annotating them to interpret the clusters. Or you could use the clusters as input for a classification model to identify rare species not included in the BirdNET training dataset.

### Example 3: Real-time Monitoring with Stream Processing

**Scenario:** You want to build a live monitoring system that analyzes a continuous audio stream and reports detections in real-time.

```python
from pathlib import Path
import numpy as np
import sounddevice as sd
from collections import deque
from threading import Thread, Event
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4

# Configuration
SAMPLE_RATE = 48000
SEGMENT_DURATION_S = 3.0
SEGMENT_SAMPLES = int(SAMPLE_RATE * SEGMENT_DURATION_S)
MIN_CONFIDENCE = 0.3

# Audio buffer for incoming data
audio_buffer = deque(maxlen=SEGMENT_SAMPLES * 2)
stop_event = Event()

# Step 1: Load model
print("Loading acoustic model...")
model = AcousticModelV2_4.load(
    lang="en_us",
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Step 2: Start session for repeated inference
print("Starting prediction session...")
session = model.predict_session(
    top_k=3,
    overlap_duration_s=0,  # No overlap for minimal latency
    apply_sigmoid=True,
    default_confidence_threshold=MIN_CONFIDENCE,
    n_producers=1,
    n_workers=1,
    batch_size=1,
    device="GPU:0"  # Or "CPU" if no GPU available
)
session.__enter__()

# Step 3: Audio callback for real-time recording
def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")
    
    # Add audio data to buffer
    audio_buffer.extend(indata[:, 0])  # Mono channel

# Step 4: Processing thread
def processing_thread():
    segment_count = 0
    
    while not stop_event.is_set():
        # Wait until enough data for a segment is available
        if len(audio_buffer) < SEGMENT_SAMPLES:
            continue
        
        # Extract segment
        segment = np.array(list(audio_buffer)[:SEGMENT_SAMPLES], dtype=np.float32)
        
        # Process
        try:
            result = session.run_arrays([(segment, SAMPLE_RATE)])
            
            # Output detections
            if result.n_predictions > 0:
                predictions = result.to_structured_array()
                for pred in predictions:
                    species = pred['species_name']
                    confidence = pred['confidence']
                    print(f"[Segment {segment_count}] Detected: {species} ({confidence:.2f})")
        
        except Exception as e:
            print(f"Error during processing: {e}")
        
        # Empty buffer (segments don't overlap)
        for _ in range(SEGMENT_SAMPLES):
            if audio_buffer:
                audio_buffer.popleft()
        
        segment_count += 1

# Step 5: Start threads
processor = Thread(target=processing_thread, daemon=True)
processor.start()

# Step 6: Start audio stream
print("\nStarting audio recording... (Ctrl+C to stop)")
with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    callback=audio_callback,
    blocksize=int(SAMPLE_RATE * 0.1)  # 100ms blocks
):
    try:
        while True:
            sd.sleep(1000)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()
        processor.join(timeout=5)
        session.__exit__(None, None, None)
        print("Stopped.")
```

**Workflow Explanation:**

This example shows a complete real-time monitoring system. The `sounddevice` stream continuously captures audio from the microphone and writes it to a thread-safe buffer (deque). A separate processing thread constantly checks whether enough data for a 3-second segment is available and then performs the analysis. Using a session ensures the model is loaded only once and remains in memory between inferences, minimizing latency.

Important is the configuration with `batch_size=1` and `overlap_duration_s=0` to minimize latency. In a production system, you would probably add additional features like database logging, alarm notifications, or web dashboards.

---

## API Reference (Compact)

### AcousticModelV2_4

**Class Methods:**

```python
AcousticModelV2_4.load(
    lang: str,
    backend_type: type[VersionedAcousticBackendProtocol],
    backend_kwargs: dict[str, Any],
    precision: MODEL_PRECISIONS = "fp32"  # (please verify, may be incorrect)
) -> AcousticModelV2_4

AcousticModelV2_4.load_custom(
    model_path: Path,
    species_list: Path,
    backend_type: type[VersionedAcousticBackendProtocol],
    backend_kwargs: dict[str, Any],
    check_validity: bool = True
) -> AcousticModelV2_4

AcousticModelV2_4.get_segment_size_s() -> float  # 3.0
AcousticModelV2_4.get_sample_rate() -> int  # 48000
AcousticModelV2_4.get_sig_fmin() -> int  # 0
AcousticModelV2_4.get_sig_fmax() -> int  # 15000
AcousticModelV2_4.get_embeddings_dim() -> int  # 1024
```

**Instance Methods:**

```python
model.predict(
    inp: Path | str | Iterable[Path | str],
    /,
    *,
    top_k: int | None = 5,
    n_producers: int = 1,
    n_workers: int | None = None,
    batch_size: int = 1,
    prefetch_ratio: int = 1,
    overlap_duration_s: float = 0,
    bandpass_fmin: int = 0,
    bandpass_fmax: int = 15_000,
    speed: float = 1.0,
    apply_sigmoid: bool = True,
    sigmoid_sensitivity: float | None = 1.0,
    default_confidence_threshold: float | None = 0.1,
    custom_confidence_thresholds: dict[str, float] | None = None,
    custom_species_list: str | Path | Collection[str] | None = None,
    half_precision: bool = False,
    max_audio_duration_min: float | None = None,
    device: str | list[str] = "CPU",
    show_stats: Literal["minimal", "progress", "benchmark"] | None = None,
    progress_callback: Callable[[AcousticProgressStats], None] | None = None,
) -> AcousticPredictionResultBase

model.predict_session(...) -> AcousticPredictionSession

model.encode(
    inp: Path | str | Iterable[Path | str],
    /,
    *,
    n_producers: int = 1,
    n_workers: int | None = None,
    batch_size: int = 1,
    prefetch_ratio: int = 1,
    overlap_duration_s: float = 0,
    speed: float = 1.0,
    bandpass_fmin: int = 0,
    bandpass_fmax: int = 15_000,
    half_precision: bool = False,
    max_audio_duration_min: float | None = None,
    device: str | list[str] = "CPU",
    show_stats: Literal["minimal", "progress", "benchmark"] | None = None,
    progress_callback: Callable[[AcousticProgressStats], None] | None = None,
) -> AcousticEncodingResultBase

model.encode_session(...) -> AcousticEncodingSession
```

### GeoModelV2_4

```python
GeoModelV2_4.load(
    lang: str,
    backend_type: type[VersionedGeoBackendProtocol],
    backend_kwargs: dict[str, Any]
) -> GeoModelV2_4

GeoModelV2_4.load_custom(
    model_path: Path,
    species_list: Path,
    backend_type: type[VersionedGeoBackendProtocol],
    backend_kwargs: dict[str, Any],
    check_validity: bool = True
) -> GeoModelV2_4

model.predict(
    latitude: float,
    longitude: float,
    /,
    *,
    week: int | None = None,
    min_confidence: float = 0.03,
    half_precision: bool = False,
    device: str = "CPU",
) -> GeoPredictionResult

model.predict_session(...) -> GeoPredictionSession
```

### Result Objects

**AcousticFilePredictionResult / AcousticDataPredictionResult# BirdNET API Documentation

**Version:** 2.4  
**Last Updated:** January 2025

---

## Introduction

This documentation is aimed at users who already have initial experience with BirdNET and now want to understand and professionally utilize the library's complete functionality. Here you will find not only the technical interfaces, but above all comprehensive explanations about what the individual components accomplish, how they interact, and how you can optimally deploy them for your specific requirements.

BirdNET is a Python library for automated bird recognition from audio recordings using deep learning. The library offers two main functionalities: acoustic analysis of audio files for identifying bird species, as well as geographic models for predicting bird occurrences based on location and season. Additionally, BirdNET enables the extraction of embeddings – high-dimensional feature vectors – that can be used for further analysis, transfer learning, or custom machine learning pipelines.

### What You'll Find in This Documentation

The documentation is modularly structured and guides you from basic concepts through individual module areas to complete application examples. You'll learn not only which parameters a method accepts, but especially what these parameters mean in context, how they influence processing, and what effects different settings have on your results.

**Overview of Main Functionalities:**

- **Acoustic Bird Species Recognition**: Analyze audio recordings and receive precise predictions about which bird species can be heard at which time points in the recording. The system works with overlapping time windows and can efficiently process large amounts of data.

- **Embedding Extraction**: Extract numerical feature representations from audio recordings that represent the "acoustic fingerprint" of an audio segment. These embeddings can be used for clustering, similarity searches, or as input for custom machine learning models.

- **Geographic Filtering**: Use metadata such as GPS coordinates and time information to determine the probability of certain bird species occurring at a location at a specific time. This helps reduce false-positive detections and contextualize results.

**Secondary Functionalities You Don't Need to Implement Yourself:**

- **Parallel Processing**: BirdNET automatically processes audio files in parallel across multiple CPU cores or GPU devices to achieve maximum performance.

- **Batch Processing**: The system internally organizes processing in optimized batches, so you don't need to worry about the details of batch formation.

- **Memory Management**: The library uses shared memory for efficient data transfer between processes and automatically manages resources.

- **Progress Indicators and Benchmarking**: Integrated mechanisms for monitoring processing progress and measuring performance.

- **Flexible Audio Processing**: Automatic resampling, bandpass filtering, and other preprocessing steps are performed transparently in the background.

---

## Architecture Overview

BirdNET is divided into several module areas, each fulfilling specific tasks. Understanding this structure helps you identify the right components for your use cases.

**Core Modules** form the foundation of the library. Here you'll find abstract base classes, the backend system for executing neural networks on different hardware platforms, and basic data structures for results and sessions. The backend system is particularly important as it provides the abstraction between your application and the underlying execution environment (CPU, GPU, various ML frameworks).

**Acoustic Modules** contain everything related to processing audio data. This includes the model classes for different versions of acoustic models, the complete inference pipeline for prediction and encoding, as well as the result objects that encapsulate your analysis results. The inference pipeline is a highly optimized processing chain that uses producer-consumer patterns to efficiently load, process, and aggregate audio segments.

**Geo Modules** provide geographic models. These models are significantly leaner than the acoustic ones, as they don't perform audio processing but merely calculate species probabilities from geographic and temporal inputs. The structure is analogous to the acoustic modules, with their own model, session, and result classes.

**Utils Modules** offer helper functions for recurring tasks such as file handling, logging configuration, and local data management. For example, paths for downloaded models are managed here, and functions for validating input data are provided.

---

## Core Modules: Foundation and Backend System

The core modules form the technical foundation of BirdNET and define the basic abstractions on which all other components are built. For you as a user, the backend system is particularly important as it determines how and where model calculations are executed.

### The Backend System

The backend system in BirdNET separates model logic from the concrete execution environment. This means you can run the same model on different hardware configurations without changing your application code. The library supports multiple backend types, each offering different trade-offs between performance, compatibility, and flexibility.

**TensorFlow Lite (TFLite) Backend:**

The TFLite backend executes models as TensorFlow Lite files and is primarily designed for CPU execution. TFLite models are compact and optimized for edge devices. If you want to use BirdNET on a laptop, desktop PC, or server without a dedicated GPU, this is often the simplest option. The TFLite backend supports various model precisions (INT8, FP16, FP32), where INT8 models are particularly small and fast but may have minimal accuracy losses. FP32 models offer the highest accuracy but require more memory and computation time.

An important note: The future of the TFLite backend is uncertain as Google has partially shifted development to LiteRT. For new projects, you should consider this.

**Protobuf (PB) Backend:**

The Protobuf backend is designed for professional applications with GPU support. It uses TensorFlow SavedModel formats that enable full GPU acceleration. If you're processing large amounts of data or need real-time performance, this is the recommended choice. The PB backend allows executing calculations on specific GPUs and supports various precision levels. The models are larger than TFLite variants but offer maximum flexibility and performance.

**Backend Selection in Practice:**

Backend selection occurs when loading a model via the `backend_type` parameter. For most use cases, you'll use predefined backend classes:

```python
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4
from birdnet.acoustic.models.v2_4.backends.tf import AcousticTFBackendV2_4

# For GPU with Protobuf:
backend_type = AcousticPBBackendV2_4
backend_kwargs = {}

# For CPU with TFLite FP32:
backend_type = AcousticTFBackendV2_4
backend_kwargs = {"inference_library": "tflite"}  # or "litert"
```

The `backend_kwargs` enable additional backend-specific configurations. For the TFLite backend, for example, you can choose between the original TensorFlow implementation (`"tflite"`) and the newer LiteRT variant (`"litert"`).

### Model Precision and Performance

Model precision determines the numerical accuracy with which calculations are performed. BirdNET supports three precision levels:

**FP32 (Float32)**: This is the standard floating-point precision with 32 bits. It offers the highest accuracy and is the basis on which the models were originally trained. Use FP32 when accuracy is more important than memory or speed optimization.

**FP16 (Float16)**: Half-precision floating-point numbers use only 16 bits. This halves memory requirements and can lead to significant speed gains on modern GPUs. Accuracy losses are typically minimal and negligible for most use cases.

**INT8**: Integer quantization with 8 bits per number reduces memory requirements to a quarter of FP32. This is the most compact variant and enables very fast inference on CPUs. Accuracy losses are somewhat larger than with FP16 but often still acceptable for bird species recognition.

Precision is determined during model download. The Protobuf backend currently only supports FP32, while TFLite models are available in all three variants.

### Base Classes for Models and Results

The core module contains abstract base classes that define the interface for all models and results. This abstraction enables using different model versions and types uniformly.

**ModelBase:**

Every model in BirdNET inherits from `ModelBase` and implements basic properties such as the model path, the list of recognizable species (`species_list`), and a flag indicating whether it's a custom model. Important methods are `load()` for loading pretrained models and `load_custom()` for loading custom trained models.

**ResultBase:**

All result objects inherit from `ResultBase` and can be saved and loaded. This allows you to persist analysis results and process them later without having to repeat the analysis. Results are saved as compressed NumPy archives (`.npz`) containing all relevant data and metadata.

**SessionBase:**

Sessions are context managers that provide a reusable inference environment. If you want to perform multiple analyses with the same parameters, a session is more efficient because the model is loaded only once and resources can be reused.

---

## Acoustic Module: Audio Analysis and Feature Extraction

The acoustic module is the heart of BirdNET for working with audio data. It includes the model classes, the inference pipeline for efficient processing, and the result objects that return your analysis results in a structured manner.

### The AcousticModelV2_4

The `AcousticModelV2_4` class is your main entry point for all acoustic analyses. An object of this class represents a loaded BirdNET model of version 2.4 that can either predict bird species or extract embeddings.

**Loading a Pretrained Model:**

BirdNET comes with pretrained models that are automatically downloaded if not yet available locally. The download process is typically transparent and occurs on the first call to `load()`. You only need to specify the desired language for species names:

```python
from birdnet.acoustic.models.v2_4.model import AcousticModelV2_4
from birdnet.acoustic.models.v2_4.backends.pb import AcousticPBBackendV2_4

model = AcousticModelV2_4.load(
    lang="de",  # German species names
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)
```

The `lang` argument determines not only the language of species names in results but can also influence the list of recognizable species, as different language versions may be trained on different geographic regions. Available languages include: German (`"de"`), English UK (`"en_uk"`), English US (`"en_us"`), Spanish (`"es"`), French (`"fr"`), Japanese (`"ja"`), and many more.

The `backend_type` and `backend_kwargs` were already explained in the section on backends. For CPU usage, you would write, for example:

```python
from birdnet.acoustic.models.v2_4.backends.tf import AcousticTFBackendV2_4

model = AcousticModelV2_4.load(
    lang="de",
    backend_type=AcousticTFBackendV2_4,
    backend_kwargs={"inference_library": "tflite"}
)
```

**Loading a Custom Model:**

If you've trained your own model or want to use a specialized model, use `load_custom()`. Here you must explicitly specify the path to the model and the species list:

```python
from pathlib import Path

model = AcousticModelV2_4.load_custom(
    model_path=Path("/path/to/model"),
    species_list=Path("/path/to/species_list.txt"),
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={},
    check_validity=True  # Checks consistency between model and species list
)
```

The `check_validity` parameter is important: when set to `True`, BirdNET checks whether the number of model outputs matches the number of species in the list. This prevents runtime errors due to inconsistent data.

**Model Properties:**

A loaded model offers several useful class methods to query technical details:

- `get_segment_size_s()`: Returns segment length in seconds (for v2.4: 3.0 seconds). This information is important for understanding the temporal resolution the model works with.
  
- `get_sample_rate()`: The sample rate for which the model was trained (48 kHz for v2.4). Audio files are internally resampled to this rate.

- `get_sig_fmin()` and `get_sig_fmax()`: The frequency range the model processes (0 Hz to 15 kHz). Frequencies outside this range are filtered out during preprocessing.

- `get_embeddings_dim()`: The dimensionality of embeddings (1024 for v2.4). This is relevant when you want to continue working with extracted feature vectors.

These properties are implemented as class methods, so you can query them even without a loaded model object if you only need metadata.

### Prediction: Bird Species Recognition

The `predict()` method is the central function for bird species recognition. It analyzes one or more audio files and returns structured results indicating which bird species were detected at which time points with which confidence.

**Basic Usage:**

```python
from pathlib import Path

result = model.predict(
    Path("/path/to/audio_file.wav"),
    top_k=5,
    overlap_duration_s=1.5,
    device="CPU"
)
```

This simple call analyzes a single audio file and returns the top-5 predictions for each time window. The 1.5-second overlap ensures that consecutive 3-second segments are offset by 1.5 seconds each, resulting in higher temporal resolution and reducing edge effects at segment boundaries.

**Processing Multiple Files Simultaneously:**

A major advantage of BirdNET is its ability to efficiently process large amounts of data. You can simply pass a list of paths or a directory:

```python
from pathlib import Path

input_dir = Path("/path/to/audio/folder")
audio_files = list(input_dir.glob("*.wav"))

result = model.predict(
    audio_files,
    top_k=5,
    overlap_duration_s=1.5,
    n_producers=2,
    n_workers=4,
    batch_size=16,
    device="CPU"
)
```

Here files are internally processed in parallel. The parameters `n_producers`, `n_workers`, and `batch_size` control parallelization, which we'll discuss in more detail shortly.

**Important Parameters in Detail:**

**`top_k`:** Determines how many of the most likely bird species are returned per time window. If you set `top_k=5`, you'll get the five species with the highest confidence values for each 3-second segment. `top_k=None` returns all species, which can lead to very large result sets. For most use cases, values between 3 and 10 are sensible.

**`overlap_duration_s`:** The overlap between consecutive segments in seconds. With a segment length of 3.0 seconds, `overlap_duration_s=0` leads to adjacent segments without overlap (0-3s, 3-6s, 6-9s, ...). With `overlap_duration_s=1.5`, segments overlap by half (0-3s, 1.5-4.5s, 3-6s, ...), doubling the temporal resolution. Higher overlaps increase computation time proportionally but improve capturing of sounds at segment boundaries.

**`speed`:** An acceleration factor for audio processing. `speed=1.0` means real-time speed. `speed=2.0` processes audio data at double speed, halving the number of analyzed segments and reducing computation time but potentially losing details. Values below 1.0 are also possible and lead to more detailed analyses with more overlap.

**`apply_sigmoid` and `sigmoid_sensitivity`:** The model internally outputs logits (unnormalized scores). When `apply_sigmoid=True`, these scores are transformed through a sigmoid function into probabilities between 0 and 1. The `sigmoid_sensitivity` parameter (default: 1.0) shifts the sigmoid curve and thus influences detection sensitivity. Higher values lead to more conservative predictions (fewer false positives but also more missed detections), lower values to more liberal predictions.

**`default_confidence_threshold`:** Predictions with confidence below this threshold are filtered out. The default value of 0.1 is relatively low and only excludes very uncertain predictions. If you want more precise results, you can increase this value (e.g., to 0.3 or 0.5), though at the cost of sensitivity.

**`custom_confidence_thresholds`:** If you need species-specific thresholds, you can pass a dictionary mapping species names to thresholds. This is useful when certain species are harder to detect or when you want to apply stricter criteria for common species.

**`custom_species_list`:** Limits output to a subset of species the model can recognize. You can pass either a list of species names, a file path to a species list, or a `Collection` object. This is useful for filtering results to locally occurring species.

**`bandpass_fmin` and `bandpass_fmax`:** These parameters define a bandpass filter applied before analysis. Frequencies outside the range [fmin, fmax] are filtered out. The default range (0 Hz to 15 kHz) corresponds to the model's training range. If you know your target species sing mainly in a specific frequency range, you can set the filter more narrowly to reduce noise.

**`half_precision`:** When `True`, calculations are internally performed with half precision (FP16). This saves memory and can increase speed on GPUs but leads to minimally lower numerical accuracy. For CPU execution, this parameter usually has no effect.

**`max_audio_duration_min`:** Limits the maximum length of a single audio file in minutes. This is a protective mechanism against accidentally loading extremely long files that could overload memory. The default value allows files up to several hours long.

**Parallelization and Performance Tuning:**

The parameters `n_producers`, `n_workers`, and `batch_size` control internal parallel processing and are crucial for optimal performance.

**`n_producers`:** Number of producer processes that load audio files and split them into segments. Producers read files from disk, perform resampling and filtering, and place segments in a buffer for workers. If you have many small files, multiple producers can increase I/O throughput. For few large files, one producer is usually sufficient.

**`n_workers`:** Number of worker processes that perform actual model inference. Each worker loads its own copy of the model and processes batches of audio segments. The optimal number depends on your hardware: for CPU execution, the number of physical CPU cores is a good starting point. For GPU execution, often one worker per GPU is optimal unless you have a very powerful GPU that can efficiently serve multiple workers.

**`batch_size`:** Number of audio segments a worker processes simultaneously. Larger batches increase throughput as modern hardware (especially GPUs) can perform parallel calculations more efficiently. However, memory requirements also increase. For CPU, values between 4 and 32 are common, for GPU between 32 and 256, depending on available memory.

**`prefetch_ratio`:** Determines how many batches are loaded in advance. A value of 2 means two batches per worker are always ready in the buffer while the worker processes the current batch. This prevents workers from having to wait for data (I/O blocking) but increases memory requirements.

**`device`:** Specifies the execution device. For CPU execution, use `"CPU"`. For GPU execution, you can specify `"GPU:0"` for the first GPU, `"GPU:1"` for the second, etc. You can also pass a list of devices, e.g., `["GPU:0", "GPU:1"]`, to distribute workers across multiple GPUs.

**Progress Display and Monitoring:**

The `show_stats` parameter controls what information is output during processing:

- `None` (default): No output, silent processing.
- `"minimal"`: Minimal information such as start and end time.
- `"progress"`: Detailed progress display with estimated remaining time and processing speed.
- `"benchmark"`: In addition to progress information, detailed performance metrics are captured and output at the end.

You can also pass your own `progress_callback`, a function called periodically with an `AcousticProgressStats` object. This object contains information such as the number of processed segments, elapsed time, and estimated remaining time. This is useful for integrating progress into a GUI or logging system.

### Sessions for Repeated Analysis

If you want to perform multiple analyses with the same parameters (e.g., process a list of files sequentially but need detailed intermediate results for each), using a session is more efficient:

```python
with model.predict_session(
    top_k=5,
    overlap_duration_s=1.5,
    n_producers=2,
    n_workers=4,
    batch_size=16,
    device="CPU"
) as session:
    result1 = session.run(Path("/path/to/file1.wav"))
    result2 = session.run(Path("/path/to/file2.wav"))
    # ... more files
```

The session loads the model and resources once when entering the context manager (`with` block) and releases them when exiting. During the session, you can call `session.run()` as many times as you like. This is faster than repeated `model.predict()` calls because initialization costs are avoided.

### Encoding: Feature Vector Extraction

The `encode()` method extracts embeddings instead of species predictions. Embeddings are high-dimensional numerical vectors (1024 dimensions for v2.4) that represent the acoustic properties of an audio segment in compressed form.

**Why Use Embeddings?**

Embeddings are useful when you want to:

- **Perform similarity searches**: Find audio segments that are acoustically similar without relying on species classification.
- **Conduct clustering**: Automatically group recordings by acoustic features.
- **Apply transfer learning**: Use pretrained features as input for your own machine learning models, e.g., for recognizing non-bird sounds or rare species.
- **Perform dimensionality reduction**: Project embeddings onto 2D/3D for visualization and exploratory data analysis.

**Basic Usage:**

```python
embedding_result = model.encode(
    Path("/path/to/audio_file.wav"),
    overlap_duration_s=1.5,
    device="CPU"
)

# Access embeddings
embeddings = embedding_result.embeddings  # NumPy array with shape (n_files, n_segments, 1024)
```

Parameters are largely identical to `predict()`, with some exceptions: there are no prediction-specific parameters like `top_k`, `apply_sigmoid`, or `confidence_threshold` since no classification takes place.

**Working with Extracted Embeddings:**

The returned `AcousticEncodingResultBase` object encapsulates embeddings and metadata. The embeddings themselves are accessible as a 3D NumPy array:

- **Dimension 0**: Index of input file (if multiple files were processed)
- **Dimension 1**: Segment index within the file
- **Dimension 2**: Embedding dimension (1024)

If you've analyzed only the first 10 seconds of a 60-second recording with 1.5s overlap, you'll get about 13 segments (at 3s segment length and 1.5s step). The embeddings array would then have shape `(1, 13, 1024)` for a single file.

The result object also provides masks to distinguish valid from invalid segments (if files were shorter than a segment or processing errors occurred):

```python
valid_embeddings = embedding_result.embeddings[~embedding_result.embeddings_masked]
```

**Encoding Sessions:**

Analogous to prediction sessions, there's `encode_session()`:

```python
with model.encode_session(
    overlap_duration_s=1.5,
    n_workers=4,
    batch_size=16,
    device="CPU"
) as session:
    emb1 = session.run(Path("/path/to/file1.wav"))
    emb2 = session.run(Path("/path/to/file2.wav"))
```

**Note on Backend Support:**

Not all backends support encoding. The Protobuf backend for v2.4 offers this functionality, but some TFLite models might only have prediction outputs. You can check support via `backend_type.supports_encoding()`. *(Note: Please check backend documentation for exact details on encoding support.)*

### Working with Results

Result objects are not just data containers but offer extensive methods for further processing and persistence.

**AcousticFilePredictionResult:**

This object is returned when you analyze audio files with `predict()`. It contains all predictions structured by file, time window, and species.

```python
result = model.predict(audio_files, top_k=5)

# Basic properties
print(f"Analyzed files: {result.n_inputs}")
print(f"Detected species: {result.n_species}")
print(f"Total predictions: {len(result.species_ids)}")

# Access raw data
predictions = result.to_structured_array()
# Returns a structured NumPy array with fields:
# - input (file path)
# - start_time (seconds)
# - end_time (seconds)
# - species_name
# - confidence
```

**Export and Persistence:**

You can export results in various formats:

```python
# As CSV for Excel/Pandas
result.to_csv("results.csv")

# As Parquet for efficient storage and analysis
result.to_parquet("results.parquet")

# As NPZ for compact storage of all NumPy arrays
result.save("results.npz", compress=True)

# Later reload
from birdnet.acoustic.inference.core.prediction.prediction_result import AcousticFilePredictionResult
loaded_result = AcousticFilePredictionResult.load("results.npz")
```

The NPZ format is particularly useful when you want to save results for later Python processing, as it preserves all metadata and arrays losslessly. CSV and Parquet are better for exchange with other tools or for data analysis in Pandas.

**Filtering and Aggregation:**

Result objects offer methods for filtering and aggregation that go beyond private implementation details. You can further process structured arrays or Parquet exports with Pandas or other tools:

```python
import pandas as pd

# Export as Parquet and load in Pandas
result.to_parquet("temp.parquet")
df = pd.read_parquet("temp.parquet")

# Filter on specific species
blackbird_detections = df[df["species_name"] == "Amsel_Turdus merula"]

# Aggregation: How often was each species detected?
species_counts = df.groupby("species_name").size().sort_values(ascending=False)
```

**Handling Unprocessed Files:**

If some audio files couldn't be processed (e.g., due to corrupted files or unsupported formats), you can identify them:

```python
if hasattr(result, 'get_unprocessed_files'):
    unprocessed = result.get_unprocessed_files()
    if unprocessed:
        print(f"The following files could not be processed: {unprocessed}")
```

This is important for robust production pipelines to ensure no data is lost.

### Processing Audio Arrays Directly

Besides audio files, you can also process NumPy arrays directly. This is useful when you already have audio data in memory or perform your own preprocessing:

```python
import numpy as np

# Audio array with 48 kHz sample rate
audio_data = np.random.randn(48000 * 30)  # 30 seconds
sample_rate = 48000

result = model.predict(
    [(audio_data, sample_rate)],  # List of tuples (array, sr)
    top_k=5
)
```

Note that the sample rate must be specified even if it matches the model sample rate, as BirdNET otherwise doesn't know how to interpret the time axis. The array should be 1-dimensional (mono) and values should be in the range [-1, 1] (standard float normalization for audio).

For sessions, use the corresponding method:

```python
with model.predict_session(...) as session:
    result = session.run_arrays([(audio_data, sample_rate)])
```

The return values are then `AcousticDataPredictionResult` or `AcousticDataEncodingResult`, which are similarly structured but use array indices instead of file paths.

---

## Geo Module: Geographic Filtering

The geo module complements acoustic analysis through geographic and temporal contextualization. Geographic models predict which bird species are likely to occur at a specific location at a specific time of year.

### GeoModelV2_4

The `GeoModelV2_4` class functions conceptually similar to `AcousticModelV2_4` but is significantly leaner as no audio processing is required.

**Loading a Geographic Model:**

```python
from birdnet.geo.models.v2_4.model import GeoModelV2_4
from birdnet.geo.models.v2_4.backends.pb import GeoPBBackendV2_4

geo_model = GeoModelV2_4.load(
    lang="de",
    backend_type=GeoPBBackendV2_4,
    backend_kwargs={}
)
```

The loading process is analogous to the acoustic model. Language determines species names, and backend defines the execution environment.

**Prediction for a Location:**

```python
prediction = geo_model.predict(
    latitude=51.5074,   # Latitude (London)
    longitude=-0.1278,  # Longitude
    week=20,            # Calendar week (May)
    min_confidence=0.03,
    device="CPU"
)
```

**Parameter Interpretation:**

**`latitude` and `longitude`:** GPS coordinates of the location in decimal degrees. Latitudes range from -90 (South Pole) to +90 (North Pole), longitudes from -180 to +180 (with 0 as Greenwich Meridian). The model is trained globally but works best in regions with extensive training data (North America, Europe).

**`week`:** Calendar week (1 to 48) representing the season. Week 1 is early January, week 48 is end of November. This parameter enables the model to account for seasonal bird migration. You can also pass `week=None`, which leads to a season-independent prediction (or the model uses a default value – please check).

**`min_confidence`:** Species with probability below this threshold are filtered from results. The default value of 0.03 (3%) is relatively low and only excludes very unlikely species.

**`device`:** As with acoustic models, you can specify `"CPU"` or `"GPU:0"` etc.

**Result Object:**

The returned `GeoPredictionResult` object contains the probability of occurrence for each species:

```python
# Access probabilities
species_names = prediction.species_list  # NumPy array with species names
probabilities = prediction.species_probs  # NumPy array with probabilities (0-1)

# Filtered species (above min_confidence)
valid_mask = ~prediction.species_masked
likely_species = species_names[valid_mask]
likely_probs = probabilities[valid_mask]

# Sort by probability
sorted_indices = np.argsort(likely_probs)[::-1]  # Descending
top_species = likely_species[sorted_indices][:10]
top_probs = likely_probs[sorted_indices][:10]

for species, prob in zip(top_species, top_probs):
    print(f"{species}: {prob:.3f}")
```

**Use in Combination with Acoustic Analysis:**

A typical workflow combines both models to filter false-positive acoustic detections:

```python
# 1. Geographic prediction
geo_pred = geo_model.predict(
    latitude=51.5074,
    longitude=-0.1278,
    week=20,
    min_confidence=0.1  # Only species with >10% probability
)

likely_species_set = set(geo_pred.species_list[~geo_pred.species_masked])

# 2. Acoustic analysis with geographic filtering
acoustic_result = acoustic_model.predict(
    audio_files,
    custom_species_list=likely_species_set,
    top_k=5
)
```

This approach significantly reduces false-positive detections as only species that plausibly occur at that location and time are considered.

**Sessions for Repeated Predictions:**

If you want to make predictions for multiple locations with the same parameters:

```python
with geo_model.predict_session(
    min_confidence=0.03,
    device="CPU"
) as session:
    pred1 = session.run(latitude=51.5074, longitude=-0.1278, week=20)
    pred2 = session.run(latitude=48.8566, longitude=2.3522, week=20)  # Paris
    # ... more locations
```

**Custom Geographic Models:**

If you've trained a specialized geographic model for a specific region:

```python
geo_model = GeoModelV2_4.load_custom(
    model_path=Path("/path/to/geo/model"),
    species_list=Path("/path/to/species_list.txt"),
    backend_type=GeoPBBackendV2_4,
    backend_kwargs={},
    check_validity=True
)
```

Validation ensures that the number of model outputs matches the length of the species list.

---

## Utils Module: Helper Functions

The utils module contains various helper functions and classes that handle infrastructure tasks. As a user, you'll rarely interact directly with these components, but it's helpful to understand what happens in the background.

### Local Data Management

BirdNET stores downloaded models and configuration data locally on your system. Exact paths depend on the operating system:

- **Windows**: `%APPDATA%\birdnet\`
- **macOS**: `~/Library/Application Support/birdnet/`
- **Linux**: `~/.local/share/birdnet/`

Within this directory, models are organized by type, version, backend, and precision:

```
bird