# BirdNET API-Dokumentation - Anhang

## Advanced & Undokumentierte Features für fortgeschrittene Anwender

**Version:** 2.4  
**Stand:** Januar 2025  
**Zielgruppe:** Entwickler, die eigene Tools auf BirdNET-Basis entwickeln

---

## Einleitung zu diesem Anhang

Dieser Anhang richtet sich an fortgeschrittene Anwender und Entwickler, die tiefer in die Internals von BirdNET eintauchen möchten oder eigene Anwendungen auf Basis der Bibliothek entwickeln. Die hier beschriebenen Features sind teilweise nicht als öffentliche API dokumentiert oder werden intern vom BirdNET Analyzer verwendet, sind aber für bestimmte Anwendungsfälle sehr wertvoll.

**Wichtiger Hinweis:** Die hier beschriebenen Funktionalitäten sind nicht Teil der stabilen öffentlichen API und können sich in zukünftigen Versionen ändern. Verwenden Sie sie auf eigenes Risiko und seien Sie bereit, Code bei Updates anzupassen.

---

## 1. AcousticProgressStats - Detailliertes Progress-Monitoring

### Was es ist

`AcousticProgressStats` ist ein Dataclass-Objekt, das detaillierte Informationen über den Verarbeitungsfortschritt während der Inferenz enthält. Es wird an Progress-Callbacks übergeben, wenn `show_stats="progress"` oder `show_stats="benchmark"` aktiviert ist.

### Vollständige Attribute

```python
@dataclass
class AcousticProgressStats:
    # Geschwindigkeit
    worker_speed_xrt: float | None = None  # Echtzeit-Faktor (z.B. 10.0 = 10x schneller als Echtzeit)
    worker_speed_seg_per_s: float | None = None  # Segmente pro Sekunde
    
    # Fortschritt
    progress: float | None = None  # Prozent (0-100)
    progress_current: int = 0  # Anzahl verarbeiteter Segmente
    progress_total: int | None = None  # Gesamtanzahl Segmente
    
    # Zeitschätzung
    est_remaining_time_s: float | None = None  # Geschätzte Restzeit in Sekunden
```

### Verwendung für Custom Monitoring

**Einfacher Progress-Bar:**

```python
from birdnet.acoustic.inference.core.perf_tracker import AcousticProgressStats

def simple_progress_callback(stats: AcousticProgressStats):
    if stats.progress is not None:
        bar_width = 50
        filled = int(bar_width * stats.progress / 100)
        bar = '█' * filled + '░' * (bar_width - filled)
        print(f"\r[{bar}] {stats.progress:.1f}%", end='', flush=True)

result = model.predict(
    files,
    show_stats="progress",
    progress_callback=simple_progress_callback
)
```

**Logging mit ETA:**

```python
import logging
from datetime import timedelta

logger = logging.getLogger("my_app")

def logging_callback(stats: AcousticProgressStats):
    if stats.progress is not None and stats.est_remaining_time_s is not None:
        eta = timedelta(seconds=int(stats.est_remaining_time_s))
        speed_info = ""
        if stats.worker_speed_xrt is not None:
            speed_info = f" | Speed: {stats.worker_speed_xrt:.1f}x realtime"
        
        logger.info(
            f"Progress: {stats.progress:.1f}% "
            f"({stats.progress_current}/{stats.progress_total} segments) "
            f"| ETA: {eta}{speed_info}"
        )

result = model.predict(
    files,
    show_stats="progress",
    progress_callback=logging_callback
)
```

**Integration in Web-Dashboard:**

```python
import asyncio
from queue import Queue
from threading import Thread

# Async Queue für Web-Updates
progress_queue = asyncio.Queue()

def web_progress_callback(stats: AcousticProgressStats):
    # Thread-safe Übertragung in Async Context
    asyncio.run_coroutine_threadsafe(
        progress_queue.put({
            'progress': stats.progress,
            'current': stats.progress_current,
            'total': stats.progress_total,
            'speed': stats.worker_speed_xrt,
            'eta_seconds': stats.est_remaining_time_s
        }),
        asyncio.get_event_loop()
    )

# In Ihrer Web-Anwendung (FastAPI, Flask, etc.)
async def stream_progress():
    while True:
        update = await progress_queue.get()
        yield f"data: {json.dumps(update)}\n\n"
        if update['progress'] >= 100:
            break
```

### Warum es nützlich ist

Diese detaillierten Metriken ermöglichen es Ihnen, professionelle User Interfaces zu bauen, die präzise Feedback über lange Verarbeitungsprozesse geben. Der BirdNET Analyzer nutzt diese Informationen wahrscheinlich für seine GUI-Progress-Anzeigen.

---

## 2. Ring-Buffer-System - Zero-Copy Data Transfer

### Was es ist

Das Ring-Buffer-System ist der Kern der effizienten Multi-Process-Architektur von BirdNET. Es verwendet Python's `multiprocessing.shared_memory` für Zero-Copy-Datentransfer zwischen Producer- und Worker-Prozessen.

### Architektur

Der Ring-Buffer besteht aus mehreren synchronisierten Shared-Memory-Arrays:

1. **rf_audio_samples**: Die Audio-Daten selbst `(n_slots, batch_size, segment_samples)`
2. **rf_file_indices**: Indizes der Quelldateien `(n_slots, batch_size)`
3. **rf_segment_indices**: Segment-Nummern innerhalb der Dateien `(n_slots, batch_size)`
4. **rf_batch_sizes**: Tatsächliche Anzahl Samples pro Slot `(n_slots,)`
5. **rf_flags**: Status-Flags für jeden Slot `(n_slots,)`

### Status-Flags

```python
WRITABLE_FLAG = 0  # Slot ist frei, Producer kann schreiben
WRITING_FLAG = 1   # Producer schreibt gerade
READABLE_FLAG = 2  # Slot ist gefüllt, Worker kann lesen
READING_FLAG = 3   # Worker liest gerade
```

### Zugriff auf Ring-Buffer-Daten (Experimental)

**Wichtig:** Dies ist hochgradig experimentell und für Debug-Zwecke gedacht!

```python
from birdnet.acoustic.inference.resources import RingBufferResources
from birdnet.acoustic.inference.core.shm import RingField
import numpy as np

# In einem Custom Worker oder für Debugging
def inspect_ring_buffer(session):
    # Zugriff über Session-Internals (nicht empfohlen für Production!)
    resources = session._resource_manager._resources
    ring_resources = resources.ring_buffer_resources
    
    # Attach zu Shared Memory
    shm, flags_array = ring_resources.rf_flags.attach_and_get_array()
    
    # Ring-Status inspizieren
    print(f"Free slots: {np.sum(flags_array == 0)}")
    print(f"Filled slots: {np.sum(flags_array == 2)}")
    print(f"Busy slots: {np.sum(flags_array == 3)}")
    
    # WICHTIG: shm.close() nach Verwendung!
    shm.close()
```

### Custom Producer Implementation

Für fortgeschrittene Anwendungsfälle können Sie eigene Producer schreiben, die direkt in den Ring-Buffer schreiben:

```python
from birdnet.acoustic.inference.processes.producer import ProducerBase
from birdnet.globals import WRITABLE_FLAG, WRITING_FLAG, READABLE_FLAG
import numpy as np

class NetworkStreamProducer(ProducerBase):
    """
    Custom Producer der Audio von Netzwerk-Stream statt Dateien lädt
    """
    
    def __init__(self, stream_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream_url = stream_url
        self.stream_client = None  # Ihre Netzwerk-Implementierung
    
    def get_segments_from_input(self, input_idx, inp_data):
        # Ihre Logik zum Laden von Netzwerk-Stream
        # und Segmentierung in 3s Chunks
        
        for segment_idx, audio_segment in self.stream_segments():
            # audio_segment sollte np.float32 mit sample_rate 48kHz sein
            yield segment_idx, audio_segment
    
    def stream_segments(self):
        # Implementierung des Streaming-Logik
        pass

# Verwendung würde custom Session-Setup erfordern
# (Details sind komplex und würden den Rahmen sprengen)
```

### Warum es nützlich ist

Wenn Sie eigene Datenquellen integrieren möchten (z.B. Live-Streams, Datenbanken, Cloud-Storage), können Sie das Ring-Buffer-System direkt nutzen statt über Dateien zu gehen. Der BirdNET Analyzer könnte dies für kontinuierliche Monitoring-Szenarien verwenden.

---

## 3. Detaillierte Benchmark-Metriken

### Was es ist

Wenn `show_stats="benchmark"` gesetzt ist, sammelt BirdNET umfangreiche Performance-Metriken, die weit über die Standard-Ausgabe hinausgehen.

### Vollständige Metrik-Struktur

Die Benchmarking-Infrastruktur erfasst folgende Kategorien:

**Zeitmetriken:**
- Wall-Clock-Zeit (Gesamtdauer)
- Worker-Wall-Zeit (kumulative Inferenz-Zeit aller Worker)
- Producer-Wall-Zeit (kumulative Lade-Zeit aller Producer)

**Throughput-Metriken:**
- Segmente pro Sekunde (total und pro Worker)
- Echtzeit-Faktor (wie viel schneller als Audio-Echtzeit)
- Audio-Minuten pro Sekunde Verarbeitung

**Memory-Metriken:**
- Peak Memory Usage (Maximum über alle Prozesse)
- Average Memory Usage
- Shared Memory Größe (Ring-Buffer)
- Result Memory Size (NumPy Arrays)

**Ring-Buffer-Metriken:**
- Average Free Slots
- Average Filled Slots
- Average Busy Slots

**Worker-Metriken:**
- Wait Time für Batches (wie lange Worker auf Daten warten)
- Inference Duration (reine Modell-Berechnungszeit)
- Copy-to-Device Duration (Datentransfer CPU→GPU)
- Average Busy Workers

**Producer-Metriken:**
- Batch Loading Duration
- Wait Time für freie Slots
- Flush Duration (Schreiben in Shared Memory)

### Zugriff auf vollständige Benchmark-Daten

```python
# Nach Prediction mit show_stats="benchmark"
result = model.predict(
    files,
    show_stats="benchmark",
    n_workers=4,
    batch_size=32
)

# Benchmark-Daten werden als JSON und CSV gespeichert
# Pfad: ~/.local/share/birdnet/acoustic-benchmarks/lib-v{version}/{timestamp}/

# Programmatischer Zugriff auf Tracking-Result
# (erfordert Zugriff auf Session-Internals - nicht dokumentiert!)
```

**Benchmark-Output-Struktur:**

```
birdnet/acoustic-benchmarks/
└── lib-v{version}/
    └── session_{timestamp}/
        └── run-0/
            ├── {hash}-run-0-stats.json       # Vollständige Metriken
            ├── {hash}-run-0-stats.txt        # Human-readable
            ├── {hash}-run-0-result.npz       # Predictions
            ├── {hash}-run-0-result.csv       # Predictions als CSV
            └── {hash}.log                     # Session-Log
```

### Custom Benchmark-Analyse

```python
import json
from pathlib import Path
import pandas as pd

def analyze_benchmarks(benchmark_dir):
    """
    Analysiert alle Benchmark-Runs in einem Verzeichnis
    """
    all_runs = []
    
    for stats_file in Path(benchmark_dir).rglob("*-stats.json"):
        with open(stats_file) as f:
            data = json.load(f)
            all_runs.append(data)
    
    df = pd.DataFrame(all_runs)
    
    # Vergleiche verschiedene Konfigurationen
    print("Performance by Worker Count:")
    print(df.groupby('param_workers')['speed_total_xrt'].agg(['mean', 'std']))
    
    print("\nMemory Usage by Batch Size:")
    print(df.groupby('param_batch_size')['mem_memory_usage_maximum_MiB'].agg(['mean', 'max']))
    
    return df

# Verwendung
benchmark_dir = Path.home() / ".local/share/birdnet/acoustic-benchmarks"
df = analyze_benchmarks(benchmark_dir)
```

### Warum es nützlich ist

Diese Metriken sind essenziell für Performance-Tuning und Debugging. Sie zeigen genau, wo Engpässe sind (I/O, Inferenz, Memory) und helfen bei der optimalen Konfiguration für spezifische Hardware.

---

## 4. Session-Lifecycle und Resource-Management

### Was es ist

Sessions haben einen komplexen Lifecycle mit mehreren Phasen: Initialisierung, Ressourcen-Allokation, Prozess-Start, Verarbeitung, Cleanup.

### Session-Internals

```python
class AcousticPredictionSession:
    def __init__(self, ...):
        self._conf = InferenceConfig(...)
        self._resource_manager = None
        self._process_manager = None
        self._shm_context = None
        self._is_initialized = False
    
    def __enter__(self):
        # 1. Ressourcen-Allokation
        self._resource_manager = ResourceManager(self._conf)
        resources = self._resource_manager.allocate()
        
        # 2. Shared Memory erstellen
        self._shm_context = resources.ring_buffer_resources.shared_memory_context(...)
        self._shm_context.__enter__()
        
        # 3. Prozesse starten
        self._process_manager = ProcessManager(...)
        self._process_manager.start_main_processes()
        
        self._is_initialized = True
        return self
    
    def __exit__(self, *args):
        # Cleanup in umgekehrter Reihenfolge
        if self._process_manager:
            self._process_manager.join_main_processes()
        
        if self._shm_context:
            self._shm_context.__exit__(*args)
        
        if self._resource_manager:
            self._resource_manager.cleanup()
        
        self._is_initialized = False
```

### Custom Session-Wrapping

Für fortgeschrittene Anwendungsfälle können Sie eigene Session-Wrapper erstellen:

```python
from contextlib import contextmanager
import time

@contextmanager
def monitored_session(model, **session_kwargs):
    """
    Session-Wrapper mit Custom Monitoring und Error-Handling
    """
    session = model.predict_session(**session_kwargs)
    
    start_time = time.time()
    errors = []
    
    try:
        with session:
            yield session
    except Exception as e:
        errors.append(e)
        raise
    finally:
        duration = time.time() - start_time
        
        # Custom Logging/Monitoring
        print(f"Session duration: {duration:.2f}s")
        if errors:
            print(f"Errors encountered: {len(errors)}")
            # Fehler an Monitoring-System senden
        
        # Cleanup-Validierung
        # (prüfen ob alle Ressourcen freigegeben wurden)

# Verwendung
with monitored_session(model, n_workers=4, device="GPU:0") as session:
    for batch in file_batches:
        result = session.run(batch)
        process_result(result)
```

### Resource Pre-Warming

Für wiederholte Sessions können Sie Ressourcen "warm" halten:

```python
class SessionPool:
    """
    Pool von wiederverwendbaren Sessions (experimentell!)
    """
    def __init__(self, model, session_config, pool_size=2):
        self.model = model
        self.session_config = session_config
        self.pool_size = pool_size
        self.sessions = []
        self._init_pool()
    
    def _init_pool(self):
        for _ in range(self.pool_size):
            session = self.model.predict_session(**self.session_config)
            session.__enter__()
            self.sessions.append(session)
    
    def get_session(self):
        if not self.sessions:
            raise RuntimeError("No sessions available")
        return self.sessions.pop()
    
    def return_session(self, session):
        self.sessions.append(session)
    
    def cleanup(self):
        for session in self.sessions:
            session.__exit__(None, None, None)
        self.sessions.clear()

# Verwendung (EXPERIMENTELL - nicht für Production!)
pool = SessionPool(model, {'n_workers': 4, 'device': 'GPU:0'}, pool_size=2)

try:
    session1 = pool.get_session()
    result1 = session1.run(files1)
    pool.return_session(session1)
    
    session2 = pool.get_session()
    result2 = session2.run(files2)
    pool.return_session(session2)
finally:
    pool.cleanup()
```

### Warum es nützlich ist

Session-Management ist kritisch für Long-Running-Services. Custom Wrapping ermöglicht Error-Recovery, Resource-Pooling und Integration in größere Systeme.

---

## 5. Logging-Hierarchie und Custom Loggers

### Was es ist

BirdNET verwendet eine hierarchische Logging-Struktur mit Session-spezifischen Loggern und Queue-basiertem Multi-Process-Logging.

### Logging-Hierarchie

```
root
└── birdnet (Package-Logger, Level: INFO)
    └── birdnet.session_{session_id} (Session-Logger, Level: inherited)
        ├── birdnet.session_{id}.producer_{pid}
        ├── birdnet.session_{id}.worker_{pid}
        ├── birdnet.session_{id}.analyzer
        ├── birdnet.session_{id}.perf_tracker
        └── birdnet.session_{id}.consumer
```

### Zugriff auf Session-Logger

```python
from birdnet.acoustic.inference.core.logs import get_logger_from_session

# In Custom Code innerhalb einer Session
def custom_processing_with_logging(session_id, data):
    logger = get_logger_from_session(session_id, __name__)
    
    logger.debug("Starting custom processing")
    try:
        result = process(data)
        logger.info(f"Processed {len(data)} items successfully")
        return result
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        raise
```

### Multi-Process Logging Setup

BirdNET verwendet Queue-Handler für Thread-sicheres Logging über Prozessgrenzen:

```python
from birdnet.utils.logging_utils import get_package_logger
from logging.handlers import QueueHandler
import multiprocessing as mp

# Setup im Hauptprozess
logging_queue = mp.Queue()
package_logger = get_package_logger()

# Handler für File-Output
file_handler = logging.FileHandler("app.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Queue-Listener im Background-Thread
from logging.handlers import QueueListener
listener = QueueListener(logging_queue, file_handler)
listener.start()

# In Worker-Prozessen
queue_handler = QueueHandler(logging_queue)
worker_logger = logging.getLogger(f"birdnet.worker_{os.getpid()}")
worker_logger.addHandler(queue_handler)
```

### Custom Logging-Integration

```python
import logging
from contextlib import contextmanager

@contextmanager
def custom_logging_context(session, log_file):
    """
    Fügt Custom Handler für Session-Dauer hinzu
    """
    # Session-ID extrahieren (internal access)
    session_id = session._session_id
    logger = get_logger_from_session(session_id, "custom")
    
    # Custom Handler hinzufügen
    handler = logging.FileHandler(log_file)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
    
    try:
        yield logger
    finally:
        logger.removeHandler(handler)
        handler.close()

# Verwendung
with model.predict_session(...) as session:
    with custom_logging_context(session, "my_analysis.log") as logger:
        logger.info("Starting custom analysis")
        result = session.run(files)
        logger.info(f"Analysis complete: {result.n_predictions} predictions")
```

### Warum es nützlich ist

Professionelles Logging ist essenziell für Debugging, Monitoring und Audit-Trails in Produktiv-Systemen. Die Queue-basierte Architektur ist optimal für Multi-Process-Szenarien.

---

## 6. Tensor-Strukturen und Post-Processing

### Was es ist

Die internen Tensor-Klassen (`AcousticPredictionTensor`, `AcousticEncodingTensor`) kapseln die rohen NumPy-Arrays und bieten Low-Level-Zugriff auf Predictions/Embeddings.

### Tensor-Struktur

**AcousticPredictionTensor:**

```python
class AcousticPredictionTensor:
    def __init__(self, max_n_segments, n_species, n_inputs):
        # Hauptdaten
        self._species_ids: np.ndarray  # (n_predictions,) - Art-IDs
        self._species_probs: np.ndarray  # (n_predictions,) - Konfidenzen
        self._file_indices: np.ndarray  # (n_predictions,) - Datei-Index
        self._segment_indices: np.ndarray  # (n_predictions,) - Segment-Index
        
        # Metadaten
        self._n_predictions: int  # Aktuelle Anzahl
        self._capacity: int  # Maximale Kapazität
```

### Direkter Tensor-Zugriff (Experimental)

```python
# Nach Prediction - Zugriff auf rohes Tensor
result = model.predict(files, top_k=5)

# Result-Objekt hat intern ein Tensor
# (nicht dokumentiert, aber zugänglich für Advanced Users)

# Strukturiertes Array abrufen
structured = result.to_structured_array()

# Direkte NumPy-Operationen
species_ids = structured['species_name']
confidences = structured['confidence']

# Custom Post-Processing
def temporal_smoothing(result, window_size=3):
    """
    Glättet Vorhersagen über Zeit mit Moving Average
    """
    structured = result.to_structured_array()
    df = pd.DataFrame(structured)
    
    # Gruppieren nach Datei und Art
    df['smooth_conf'] = df.groupby(['input', 'species_name'])['confidence'].transform(
        lambda x: x.rolling(window=window_size, min_periods=1, center=True).mean()
    )
    
    return df
```

### Custom Aggregations

```python
def aggregate_detections_by_time_window(result, window_seconds=60):
    """
    Aggregiert Detections in Zeitfenster
    """
    structured = result.to_structured_array()
    df = pd.DataFrame(structured)
    
    # Zeitfenster berechnen
    df['time_window'] = (df['start_time'] // window_seconds).astype(int)
    
    # Aggregation: Höchste Konfidenz pro Fenster und Art
    aggregated = df.groupby(['input', 'time_window', 'species_name']).agg({
        'confidence': 'max',
        'start_time': 'min'
    }).reset_index()
    
    return aggregated

# Verwendung
result = model.predict(files, top_k=5, overlap_duration_s=1.5)
aggregated = aggregate_detections_by_time_window(result, window_seconds=60)
```

### Warum es nützlich ist

Direkter Tensor-Zugriff ermöglicht hochgradig optimierte Post-Processing-Pipelines, die spezifisch für Ihre Anwendungsfälle sind. Der BirdNET Analyzer nutzt wahrscheinlich Custom Aggregations für Zusammenfassungen und Reports.

---

## 7. Backend-Internals und Device-Management

### Was es ist

Das Backend-System abstrahiert TensorFlow/TFLite-Details, aber fortgeschrittene Anwender können direkt mit Backend-Instanzen arbeiten.

### Backend-Loader Deep-Dive

```python
from birdnet.core.backends import BackendLoader

# Backend-Loader erstellen
loader = BackendLoader(
    model_path=model.model_path,
    backend_type=AcousticPBBackendV2_4,
    backend_kwargs={}
)

# Backend laden
backend = loader.load_backend(device="GPU:0", half_precision=False)

# Direkter Zugriff auf Backend-Methoden
backend.load()  # Lädt Modell in Speicher

# Custom Batch-Inferenz
import numpy as np

audio_batch = np.random.randn(16, 144000).astype(np.float32)
tensor = backend.copy_to_device(audio_batch)
predictions = backend.predict(tensor)
result = backend.copy_from_device(predictions)

backend.unload()  # Gibt Ressourcen frei
```

### Multi-GPU Management

```python
def create_multi_gpu_backends(model_path, backend_type, n_gpus=2):
    """
    Erstellt Backend-Instanzen für mehrere GPUs
    """
    backends = []
    
    for gpu_id in range(n_gpus):
        loader = BackendLoader(
            model_path=model_path,
            backend_type=backend_type,
            backend_kwargs={}
        )
        backend = loader.load_backend(
            device=f"GPU:{gpu_id}",
            half_precision=True
        )
        backends.append(backend)
    
    return backends

# Round-Robin Inferenz über GPUs
class MultiGPUInferencePool:
    def __init__(self, backends):
        self.backends = backends
        self.current_idx = 0
    
    def predict(self, batch):
        backend = self.backends[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.backends)
        
        tensor = backend.copy_to_device(batch)
        result = backend.predict(tensor)
        return backend.copy_from_device(result)

# Verwendung
backends = create_multi_gpu_backends(model.model_path, AcousticPBBackendV2_4, n_gpus=2)
pool = MultiGPUInferencePool(backends)

for batch in batches:
    predictions = pool.predict(batch)
```

### Memory Growth Control (TensorFlow)

```python
# Explizite Kontrolle über GPU Memory Growth
import os
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'

# Oder programmatisch
import tensorflow as tf

gpus = tf.config.list_physical_devices('GPU')
if gpus:
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
        
        # Optional: Memory Limit setzen
        tf.config.set_logical_device_configuration(
            gpu,
            [tf.config.LogicalDeviceConfiguration(memory_limit=4096)]  # 4GB
        )
```

### Warum es nützlich ist

Direkter Backend-Zugriff ermöglicht fein-granulare Kontrolle über Hardware-Nutzung, besonders wichtig für Multi-GPU-Setups oder Server mit mehreren Clients.

---

## 8. Error-Recovery und Partial Results

### Was es ist

BirdNET sammelt Informationen über fehlgeschlagene Dateien und ermöglicht Partial Results auch bei Fehlern.

### Unprocessed Files Tracking

```python
result = model.predict(files, n_workers=4)

# Prüfen ob Dateien fehlgeschlagen sind
if hasattr(result, 'get_unprocessed_files'):
    unprocessed = result.get_unprocessed_files()
    
    if unprocessed:
        print(f"Warning: {len(unprocessed)} files could not be processed")
        for file_path in unprocessed:
            print(f"  - {file_path}")
        
        # Retry-Logik
        retry_result = model.predict(
            list(unprocessed),
            n_workers=1,  # Single-threaded für Debugging
            show_stats="minimal"
        )
```

### Custom Error-Handling in Sessions

```python
from contextlib import suppress

def robust_batch_processing(model, file_batches, max_retries=2):
    """
    Verarbeitet Batches mit automatischem Retry bei Fehlern
    """
    all_results = []
    failed_files = set()
    
    with model.predict_session(n_workers=4) as session:
        for batch_idx, batch in enumerate(file_batches):
            retry_count = 0
            
            while retry_count <= max_retries:
                try:
                    result = session.run(batch)
                    all_results.append(result)
                    
                    # Unprocessed aus diesem Batch tracken
                    if hasattr(result, 'get_unprocessed_files'):
                        failed_files.update(result.get_unprocessed_files())
                    
                    break  # Erfolg
                
                except Exception as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        print(f"Batch {batch_idx} failed after {max_retries} retries: {e}")
                        failed_files.update(batch)
                        break
                    else:
                        print(f"Batch {batch_idx} failed, retrying ({retry_count}/{max_retries})")
                        time.sleep(2 ** retry_count)  # Exponential backoff
    
    return all_results, failed_files

# Verwendung
results, failed = robust_batch_processing(model, file_batches, max_retries=2)
print(f"Successfully processed: {sum(r.n_inputs for r in results)} files")
print(f"Failed: {len(failed)} files")
```

### Graceful Degradation

```python
def predict_with_fallback(model, files, primary_config, fallback_config):
    """
    Versucht Prediction mit primärer Config, fällt auf Fallback zurück bei Fehlern
    """
    try:
        return model.predict(files, **primary_config)
    except MemoryError:
        print("Out of memory with primary config, trying fallback...")
        return model.predict(files, **fallback_config)
    except Exception as e:
        print(f"Primary config failed with error: {e}")
        print("Trying fallback config...")
        return model.predict(files, **fallback_config)

# Verwendung
primary = {
    'n_workers': 8,
    'batch_size': 64,
    'device': 'GPU:0'
}

fallback = {
    'n_workers': 2,
    'batch_size': 8,
    'device': 'CPU'
}

result = predict_with_fallback(model, large_file_list, primary, fallback)
```

### Warum es nützlich ist

Robuste Error-Handling ist kritisch für Produktiv-Systeme, die große, heterogene Datasets verarbeiten. Partial Results ermöglichen es, mit Fehlern fortzufahren statt alles abzubrechen.

---

## 9. Custom Species-List Management und Taxonomie

### Was es ist

BirdNET unterstützt verschiedene Sprachen für Artennamen, aber fortgeschrittene Anwender möchten oft eigene Taxonomien oder Synonyme verwalten.

### Multi-Language Species Mapping

```python
from pathlib import Path
from collections import defaultdict

class SpeciesTranslator:
    """
    Cross-Language Species-Name-Mapping
    """
    def __init__(self, lang_dir: Path):
        self.lang_dir = lang_dir
        self.translations = defaultdict(dict)
        self._load_translations()
    
    def _load_translations(self):
        # Lade alle verfügbaren Sprachen
        for lang_file in self.lang_dir.glob("*.txt"):
            lang_code = lang_file.stem
            with open(lang_file, 'r', encoding='utf-8') as f:
                species_list = [line.strip() for line in f if line.strip()]
            
            # Index durch Reihenfolge
            for idx, species_name in enumerate(species_list):
                # Speichere nach Index für Cross-Referenz
                if idx not in self.translations:
                    self.translations[idx] = {}
                self.translations[idx][lang_code] = species_name
    
    def translate(self, species_name: str, from_lang: str, to_lang: str) -> str:
        """Übersetze Artennamen zwischen Sprachen"""
        # Finde Index der Art in from_lang
        for idx, names in self.translations.items():
            if names.get(from_lang) == species_name:
                return names.get(to_lang, species_name)
        return species_name  # Fallback
    
    def get_all_languages_for_species(self, species_name: str, lang: str) -> dict:
        """Gibt alle Übersetzungen für eine Art zurück"""
        for idx, names in self.translations.items():
            if names.get(lang) == species_name:
                return names
        return {}

# Verwendung
lang_dir = Path.home() / ".local/share/birdnet/acoustic-models/v2.4/pb/labels"
translator = SpeciesTranslator(lang_dir)

# Übersetze Ergebnisse
result = model.predict(files, top_k=5)
structured = result.to_structured_array()

for row in structured[:10]:
    german_name = row['species_name']
    english_name = translator.translate(german_name, 'de', 'en_us')
    print(f"{german_name} → {english_name}")
```

### Custom Taxonomie Integration

```python
import pandas as pd

class TaxonomyManager:
    """
    Verwaltet taxonomische Hierarchie und Synonyme
    """
    def __init__(self, taxonomy_csv: Path):
        self.taxonomy = pd.read_csv(taxonomy_csv)
        # Erwartet Spalten: species_name, genus, family, order, synonyms
    
    def get_family(self, species_name: str) -> str:
        row = self.taxonomy[self.taxonomy['species_name'] == species_name]
        return row['family'].values[0] if len(row) > 0 else "Unknown"
    
    def get_synonyms(self, species_name: str) -> list[str]:
        row = self.taxonomy[self.taxonomy['species_name'] == species_name]
        if len(row) > 0 and pd.notna(row['synonyms'].values[0]):
            return row['synonyms'].values[0].split(';')
        return []
    
    def resolve_synonym(self, name: str) -> str:
        """Findet kanonischen Namen für Synonym"""
        for _, row in self.taxonomy.iterrows():
            if pd.notna(row['synonyms']) and name in row['synonyms'].split(';'):
                return row['species_name']
        return name
    
    def filter_by_family(self, species_list: list[str], families: list[str]) -> list[str]:
        """Filtert Artenliste nach Familien"""
        mask = self.taxonomy['family'].isin(families)
        filtered = self.taxonomy[mask]['species_name'].tolist()
        return [s for s in species_list if s in filtered]

# Verwendung mit BirdNET
taxonomy = TaxonomyManager(Path("my_taxonomy.csv"))

# Nur Singvögel (Passeriformes) analysieren
passerines = taxonomy.filter_by_family(
    model.species_list, 
    families=['Turdidae', 'Paridae', 'Fringillidae']
)

result = model.predict(
    files,
    custom_species_list=passerines,
    top_k=5
)
```

### Warum es nützlich ist

Wissenschaftliche Anwendungen erfordern oft präzise taxonomische Kontrolle. Multi-Language-Support ist wichtig für internationale Kollaborationen oder mehrsprachige Berichte.

---

## 10. Advanced Audio-Preprocessing und Filterung

### Was es ist

Producer-Prozesse führen Audio-Preprocessing durch (Resampling, Filterung), aber diese Schritte können für spezielle Anwendungsfälle angepasst werden.

### Custom Audio-Filter

```python
import numpy as np
from scipy import signal

class CustomAudioPreprocessor:
    """
    Erweiterte Audio-Vorverarbeitung vor BirdNET-Inferenz
    """
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
    
    def spectral_subtraction(self, audio: np.ndarray, noise_profile: np.ndarray) -> np.ndarray:
        """
        Spektrale Subtraktion zur Rauschreduktion
        """
        # FFT von Signal und Rauschen
        audio_fft = np.fft.rfft(audio)
        noise_fft = np.fft.rfft(noise_profile[:len(audio)])
        
        # Magnitude subtrahieren
        audio_mag = np.abs(audio_fft)
        noise_mag = np.abs(noise_fft)
        
        clean_mag = np.maximum(audio_mag - 1.5 * noise_mag, 0.1 * audio_mag)
        
        # Phase beibehalten
        clean_fft = clean_mag * np.exp(1j * np.angle(audio_fft))
        
        return np.fft.irfft(clean_fft, n=len(audio))
    
    def adaptive_bandpass(self, audio: np.ndarray, fmin=500, fmax=12000) -> np.ndarray:
        """
        Adaptiver Bandpass basierend auf Energie-Verteilung
        """
        # Butterworth-Filter
        nyq = self.sample_rate / 2
        low = fmin / nyq
        high = fmax / nyq
        b, a = signal.butter(4, [low, high], btype='band')
        
        return signal.filtfilt(b, a, audio)
    
    def normalize_loudness(self, audio: np.ndarray, target_db=-20) -> np.ndarray:
        """
        Normalisiert Audio auf Ziel-Lautstärke
        """
        rms = np.sqrt(np.mean(audio**2))
        current_db = 20 * np.log10(rms + 1e-10)
        gain_db = target_db - current_db
        gain = 10 ** (gain_db / 20)
        
        return audio * gain
    
    def process(self, audio: np.ndarray, noise_profile: np.ndarray = None) -> np.ndarray:
        """
        Vollständige Preprocessing-Pipeline
        """
        # Spektrale Subtraktion
        if noise_profile is not None:
            audio = self.spectral_subtraction(audio, noise_profile)
        
        # Bandpass
        audio = self.adaptive_bandpass(audio)
        
        # Normalisierung
        audio = self.normalize_loudness(audio)
        
        return audio

# Verwendung mit BirdNET
preprocessor = CustomAudioPreprocessor()

# Audio laden und vorverarbeiten
import soundfile as sf

def preprocess_and_predict(model, audio_file, noise_file=None):
    # Lade Audio
    audio, sr = sf.read(audio_file)
    
    # Lade Noise-Profile falls vorhanden
    noise = None
    if noise_file:
        noise, _ = sf.read(noise_file)
    
    # Preprocessing
    clean_audio = preprocessor.process(audio, noise)
    
    # An BirdNET übergeben
    result = model.predict([(clean_audio, sr)], top_k=5)
    return result

result = preprocess_and_predict(
    model, 
    "noisy_recording.wav", 
    noise_file="noise_profile.wav"
)
```

### Dynamische Segment-Filterung

```python
def predict_with_energy_filtering(model, audio_file, energy_threshold=0.01):
    """
    Analysiert nur Segmente mit ausreichender Energie
    """
    import soundfile as sf
    
    audio, sr = sf.read(audio_file)
    segment_samples = int(3.0 * sr)  # 3s Segmente
    
    # Berechne Energie pro Segment
    segments = []
    for i in range(0, len(audio) - segment_samples, segment_samples // 2):
        segment = audio[i:i+segment_samples]
        energy = np.sqrt(np.mean(segment**2))
        
        if energy > energy_threshold:
            segments.append((segment, sr))
    
    if not segments:
        print("No segments with sufficient energy found")
        return None
    
    # Nur energiereiche Segmente analysieren
    result = model.predict(segments, top_k=5)
    return result
```

### Warum es nützlich ist

Real-World Audio ist oft verrauscht oder hat variable Qualität. Custom Preprocessing kann Erkennungsraten erheblich verbessern, besonders bei schwierigen Aufnahmebedingungen.

---

## 11. Distributed Processing über Netzwerk

### Was es ist

Für sehr große Datasets kann die Verarbeitung über mehrere Maschinen verteilt werden.

### Redis-basierte Task-Queue

```python
import redis
import pickle
from pathlib import Path

class DistributedBirdNETWorker:
    """
    Worker-Node für verteilte BirdNET-Verarbeitung
    """
    def __init__(self, model, redis_host='localhost', redis_port=6379):
        self.model = model
        self.redis_client = redis.Redis(host=redis_host, port=redis_port)
        self.task_queue = 'birdnet:tasks'
        self.result_queue = 'birdnet:results'
    
    def run_worker(self):
        """
        Endlosschleife: hole Tasks und verarbeite sie
        """
        print(f"Worker started, waiting for tasks...")
        
        while True:
            # Blockierendes Pop von Task-Queue
            task_data = self.redis_client.blpop(self.task_queue, timeout=10)
            
            if task_data is None:
                continue
            
            _, task_bytes = task_data
            task = pickle.loads(task_bytes)
            
            task_id = task['id']
            files = task['files']
            config = task['config']
            
            print(f"Processing task {task_id} with {len(files)} files")
            
            try:
                # Verarbeitung
                result = self.model.predict(files, **config)
                
                # Ergebnis serialisieren und in Result-Queue
                result_data = {
                    'task_id': task_id,
                    'success': True,
                    'n_predictions': result.n_predictions,
                    'result_path': f'/shared/results/task_{task_id}.npz'
                }
                
                # Result speichern
                result.save(result_data['result_path'])
                
            except Exception as e:
                result_data = {
                    'task_id': task_id,
                    'success': False,
                    'error': str(e)
                }
            
            # Ergebnis zurück
            self.redis_client.rpush(
                self.result_queue,
                pickle.dumps(result_data)
            )
            
            print(f"Task {task_id} completed")

class DistributedBirdNETCoordinator:
    """
    Koordinator der Tasks über Worker verteilt
    """
    def __init__(self, redis_host='localhost', redis_port=6379):
        self.redis_client = redis.Redis(host=redis_host, port=redis_port)
        self.task_queue = 'birdnet:tasks'
        self.result_queue = 'birdnet:results'
    
    def submit_batch(self, files: list[Path], config: dict, batch_size=100):
        """
        Teilt Files in Batches und submitted als Tasks
        """
        tasks = []
        
        for i in range(0, len(files), batch_size):
            batch = files[i:i+batch_size]
            task = {
                'id': f'batch_{i//batch_size}',
                'files': [str(f) for f in batch],
                'config': config
            }
            tasks.append(task)
            
            # Push zu Queue
            self.redis_client.rpush(
                self.task_queue,
                pickle.dumps(task)
            )
        
        print(f"Submitted {len(tasks)} tasks to queue")
        return tasks
    
    def collect_results(self, n_tasks: int, timeout=3600):
        """
        Sammelt Results von Workern
        """
        results = []
        start_time = time.time()
        
        while len(results) < n_tasks:
            if time.time() - start_time > timeout:
                print(f"Timeout: only {len(results)}/{n_tasks} results collected")
                break
            
            result_data = self.redis_client.blpop(
                self.result_queue,
                timeout=10
            )
            
            if result_data:
                _, result_bytes = result_data
                result = pickle.loads(result_bytes)
                results.append(result)
                print(f"Collected result {len(results)}/{n_tasks}")
        
        return results

# Verwendung auf Worker-Maschinen:
# worker = DistributedBirdNETWorker(model, redis_host='coordinator.local')
# worker.run_worker()

# Verwendung auf Koordinator-Maschine:
# coordinator = DistributedBirdNETCoordinator(redis_host='localhost')
# tasks = coordinator.submit_batch(all_files, {'top_k': 5, 'n_workers': 4})
# results = coordinator.collect_results(len(tasks))
```

### Docker-Container Setup

```dockerfile
# Dockerfile für BirdNET Worker
FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install birdnet[and-cuda] redis

COPY worker_script.py /app/worker.py

CMD ["python", "/app/worker.py"]
```

```yaml
# docker-compose.yml für Multi-Worker Setup
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  coordinator:
    build: .
    command: python coordinator.py
    depends_on:
      - redis
    volumes:
      - ./data:/data
      - ./results:/shared/results
    environment:
      - REDIS_HOST=redis
  
  worker-gpu-1:
    build: .
    runtime: nvidia
    environment:
      - REDIS_HOST=redis
      - NVIDIA_VISIBLE_DEVICES=0
    depends_on:
      - redis
    volumes:
      - ./data:/data
      - ./results:/shared/results
  
  worker-gpu-2:
    build: .
    runtime: nvidia
    environment:
      - REDIS_HOST=redis
      - NVIDIA_VISIBLE_DEVICES=1
    depends_on:
      - redis
    volumes:
      - ./data:/data
      - ./results:/shared/results
```

### Warum es nützlich ist

Für Organisationen mit großen Audio-Archiven (Tausende Stunden) ist verteilte Verarbeitung essentiell. Dies ermöglicht horizontale Skalierung über beliebig viele Maschinen.

---

## 12. Produktions-Deployment Best Practices

### Gesundheits-Checks und Monitoring

```python
from dataclasses import dataclass
from datetime import datetime
import psutil

@dataclass
class SystemHealth:
    timestamp: datetime
    cpu_percent: float
    memory_used_gb: float
    memory_available_gb: float
    gpu_memory_used_mb: float
    gpu_memory_total_mb: float
    disk_usage_percent: float

class HealthMonitor:
    """
    Überwacht System-Gesundheit während BirdNET-Verarbeitung
    """
    def __init__(self):
        self.history = []
    
    def check_health(self) -> SystemHealth:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # GPU-Metriken (falls nvidia-smi verfügbar)
        gpu_mem_used, gpu_mem_total = self._get_gpu_memory()
        
        health = SystemHealth(
            timestamp=datetime.now(),
            cpu_percent=cpu,
            memory_used_gb=mem.used / 1024**3,
            memory_available_gb=mem.available / 1024**3,
            gpu_memory_used_mb=gpu_mem_used,
            gpu_memory_total_mb=gpu_mem_total,
            disk_usage_percent=disk.percent
        )
        
        self.history.append(health)
        return health
    
    def _get_gpu_memory(self) -> tuple[float, float]:
        try:
            import subprocess
            result = subprocess.check_output([
                'nvidia-smi',
                '--query-gpu=memory.used,memory.total',
                '--format=csv,noheader,nounits'
            ], encoding='utf-8')
            
            used, total = map(float, result.strip().split(','))
            return used, total
        except:
            return 0.0, 0.0
    
    def is_healthy(self, health: SystemHealth) -> tuple[bool, list[str]]:
        """
        Prüft ob System gesund ist, gibt Warnungen zurück
        """
        warnings = []
        
        if health.cpu_percent > 90:
            warnings.append(f"High CPU usage: {health.cpu_percent}%")
        
        if health.memory_available_gb < 2.0:
            warnings.append(f"Low memory: {health.memory_available_gb:.1f}GB available")
        
        if health.gpu_memory_used_mb > 0:
            usage_percent = (health.gpu_memory_used_mb / health.gpu_memory_total_mb) * 100
            if usage_percent > 90:
                warnings.append(f"High GPU memory: {usage_percent:.1f}%")
        
        if health.disk_usage_percent > 90:
            warnings.append(f"High disk usage: {health.disk_usage_percent}%")
        
        return len(warnings) == 0, warnings

# Verwendung
monitor = HealthMonitor()

def monitored_processing(model, files):
    """
    Verarbeitung mit kontinuierlichem Health-Monitoring
    """
    import threading
    
    stop_monitoring = threading.Event()
    
    def monitor_loop():
        while not stop_monitoring.is_set():
            health = monitor.check_health()
            is_healthy, warnings = monitor.is_healthy(health)
            
            if not is_healthy:
                for warning in warnings:
                    print(f"WARNING: {warning}")
            
            time.sleep(10)
    
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    try:
        result = model.predict(files, n_workers=4, show_stats="progress")
        return result
    finally:
        stop_monitoring.set()
        monitor_thread.join()
```

### Graceful Shutdown

```python
import signal
import sys

class GracefulKiller:
    """
    Fängt Shutdown-Signale ab für sauberes Cleanup
    """
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
    
    def exit_gracefully(self, signum, frame):
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.kill_now = True

def production_processing_loop(model, file_queue):
    """
    Produktions-Loop mit Graceful Shutdown
    """
    killer = GracefulKiller()
    
    with model.predict_session(n_workers=4, device="GPU:0") as session:
        while not killer.kill_now:
            try:
                # Hole nächsten Batch (mit Timeout)
                batch = file_queue.get(timeout=5)
                
                if batch is None:  # Poison pill
                    break
                
                result = session.run(batch)
                
                # Speichere Result
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                result.save(f"results/batch_{timestamp}.npz")
                
                file_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error processing batch: {e}")
                # Logging, Alerting, etc.
    
    print("Shutdown complete")

# Verwendung als Service
# python production_service.py
```

### Warum es nützlich ist

Produktiv-Deployments erfordern Robustheit, Monitoring und sauberes Shutdown-Verhalten. Diese Patterns sind Standard in Production-ML-Services.

---

## Zusammenfassung und Empfehlungen

### Was Sie aus diesem Anhang mitnehmen sollten

**Für fortgeschrittene Anwender:**
- `AcousticProgressStats` für professionelles Monitoring
- Benchmark-Metriken für Performance-Tuning
- Error-Recovery-Patterns für Robustheit

**Für Tool-Entwickler:**
- Ring-Buffer-System für Custom Data-Sources
- Session-Lifecycle für Resource-Management
- Logging-Hierarchie für Multi-Process-Debugging

**Für Produktions-Deployments:**
- Distributed Processing für Skalierung
- Health-Monitoring für Stabilität
- Graceful Shutdown für Zuverlässigkeit

### Kompatibilitätswarnung

**Wichtig:** Alle hier beschriebenen Features sind:
- Nicht Teil der stabilen öffentlichen API
- Können sich ohne Vorankündigung ändern
- Erfordern tiefes Verständnis der Internals
- Sollten mit Vorsicht in Production verwendet werden

**Empfehlung:** Verwenden Sie diese Features nur wenn:
1. Die öffentliche API Ihre Anforderungen nicht erfüllt
2. Sie bereit sind, Code bei Updates anzupassen
3. Sie die Implementierung verstehen und testen können

### BirdNET Analyzer Connection

Der **BirdNET Analyzer** nutzt wahrscheinlich viele dieser Features:

1. **Progress-Callbacks** für GUI-Progress-Bars
2. **Benchmark-Metriken** für Performance-Anzeigen
3. **Custom Post-Processing** für Ergebnis-Aggregation
4. **Session-Management** für wiederholte Analysen
5. **Logging-Integration** für User-Feedback
6. **Error-Recovery** für robuste File-Verarbeitung

### Weiterführende Exploration

Wenn Sie diese Features verwenden möchten:

1. **Studieren Sie den Quellcode:** Schauen Sie sich die Implementierung in `birdnet/acoustic/inference/` an
2. **Experimentieren Sie in Isolation:** Testen Sie Features erst separat bevor Sie sie integrieren
3. **Schreiben Sie Tests:** Eigene Tests helfen bei API-Änderungen
4. **Bleiben Sie informiert:** Verfolgen Sie GitHub-Issues und Releases

### Kontakt und Community

Falls Sie Fragen zu diesen Advanced Features haben:

- **GitHub Issues:** Für Bug-Reports und Feature-Requests
- **GitHub Discussions:** Für allgemeine Fragen
- **Source Code:** Die beste Dokumentation für Internals

---

## Schlusswort

Dieser Anhang hat Ihnen Einblick in die Internals von BirdNET gegeben, die normalerweise nicht dokumentiert sind. Diese Features sind mächtig, aber auch komplex und instabil. Verwenden Sie sie weise und seien Sie bereit für Änderungen.

Die öffentliche API sollte für 95% der Anwendungsfälle ausreichen. Nur für sehr spezielle Anforderungen (z.B. eigene Monitoring-Systeme, verteilte Verarbeitung, Custom Hardware-Integration) sind diese Advanced Features notwendig.

Viel Erfolg beim Entwickeln auf BirdNET-Basis!

---

**Anhang-Version**: 1.0  
**Stand**: Januar 2025  
**Hinweis**: Dieser Anhang basiert auf Code-Analyse von BirdNET v2.4 und kann Ungenauigkeiten enthalten. Bei Unsicherheiten konsultieren Sie den Quellcode direkt.