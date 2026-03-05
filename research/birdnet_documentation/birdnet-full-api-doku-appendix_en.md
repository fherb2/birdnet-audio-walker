# BirdNET API Documentation - Appendix

## Advanced & Undocumented Features for Advanced Users

**Version:** 2.4  
**Last Updated:** January 2025  
**Target Audience:** Developers building custom tools on BirdNET

---

## Introduction to This Appendix

This appendix is aimed at advanced users and developers who want to delve deeper into BirdNET's internals or develop their own applications based on the library. The features described here are partially not documented as public API or are used internally by the BirdNET Analyzer, but are very valuable for certain use cases.

**Important Note:** The functionalities described here are not part of the stable public API and may change in future versions. Use them at your own risk and be prepared to adapt code during updates.

---

## 1. AcousticProgressStats - Detailed Progress Monitoring

### What It Is

`AcousticProgressStats` is a dataclass object containing detailed information about processing progress during inference. It's passed to progress callbacks when `show_stats="progress"` or `show_stats="benchmark"` is activated.

### Complete Attributes

```python
@dataclass
class AcousticProgressStats:
    # Speed
    worker_speed_xrt: float | None = None  # Real-time factor (e.g., 10.0 = 10x faster than real-time)
    worker_speed_seg_per_s: float | None = None  # Segments per second
    
    # Progress
    progress: float | None = None  # Percentage (0-100)
    progress_current: int = 0  # Number of processed segments
    progress_total: int | None = None  # Total number of segments
    
    # Time estimation
    est_remaining_time_s: float | None = None  # Estimated remaining time in seconds
```

### Usage for Custom Monitoring

**Simple Progress Bar:**

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

**Logging with ETA:**

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

**Integration in Web Dashboard:**

```python
import asyncio
from queue import Queue
from threading import Thread

# Async queue for web updates
progress_queue = asyncio.Queue()

def web_progress_callback(stats: AcousticProgressStats):
    # Thread-safe transfer to async context
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

# In your web application (FastAPI, Flask, etc.)
async def stream_progress():
    while True:
        update = await progress_queue.get()
        yield f"data: {json.dumps(update)}\n\n"
        if update['progress'] >= 100:
            break
```

### Why It's Useful

These detailed metrics enable you to build professional user interfaces that provide precise feedback about long processing operations. The BirdNET Analyzer likely uses this information for its GUI progress displays.

---

## 2. Ring Buffer System - Zero-Copy Data Transfer

### What It Is

The ring buffer system is the core of BirdNET's efficient multi-process architecture. It uses Python's `multiprocessing.shared_memory` for zero-copy data transfer between producer and worker processes.

### Architecture

The ring buffer consists of several synchronized shared memory arrays:

1. **rf_audio_samples**: The audio data itself `(n_slots, batch_size, segment_samples)`
2. **rf_file_indices**: Indices of source files `(n_slots, batch_size)`
3. **rf_segment_indices**: Segment numbers within files `(n_slots, batch_size)`
4. **rf_batch_sizes**: Actual number of samples per slot `(n_slots,)`
5. **rf_flags**: Status flags for each slot `(n_slots,)`

### Status Flags

```python
WRITABLE_FLAG = 0  # Slot is free, producer can write
WRITING_FLAG = 1   # Producer is currently writing
READABLE_FLAG = 2  # Slot is filled, worker can read
READING_FLAG = 3   # Worker is currently reading
```

### Accessing Ring Buffer Data (Experimental)

**Important:** This is highly experimental and intended for debugging purposes!

```python
from birdnet.acoustic.inference.resources import RingBufferResources
from birdnet.acoustic.inference.core.shm import RingField
import numpy as np

# In a custom worker or for debugging
def inspect_ring_buffer(session):
    # Access via session internals (not recommended for production!)
    resources = session._resource_manager._resources
    ring_resources = resources.ring_buffer_resources
    
    # Attach to shared memory
    shm, flags_array = ring_resources.rf_flags.attach_and_get_array()
    
    # Inspect ring status
    print(f"Free slots: {np.sum(flags_array == 0)}")
    print(f"Filled slots: {np.sum(flags_array == 2)}")
    print(f"Busy slots: {np.sum(flags_array == 3)}")
    
    # IMPORTANT: shm.close() after use!
    shm.close()
```

### Custom Producer Implementation

For advanced use cases, you can write your own producers that write directly to the ring buffer:

```python
from birdnet.acoustic.inference.processes.producer import ProducerBase
from birdnet.globals import WRITABLE_FLAG, WRITING_FLAG, READABLE_FLAG
import numpy as np

class NetworkStreamProducer(ProducerBase):
    """
    Custom producer that loads audio from network stream instead of files
    """
    
    def __init__(self, stream_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream_url = stream_url
        self.stream_client = None  # Your network implementation
    
    def get_segments_from_input(self, input_idx, inp_data):
        # Your logic for loading from network stream
        # and segmenting into 3s chunks
        
        for segment_idx, audio_segment in self.stream_segments():
            # audio_segment should be np.float32 with sample_rate 48kHz
            yield segment_idx, audio_segment
    
    def stream_segments(self):
        # Implementation of streaming logic
        pass

# Usage would require custom session setup
# (details are complex and would exceed the scope)
```

### Why It's Useful

If you want to integrate your own data sources (e.g., live streams, databases, cloud storage), you can use the ring buffer system directly instead of going through files. The BirdNET Analyzer could use this for continuous monitoring scenarios.

---

## 3. Detailed Benchmark Metrics

### What It Is

When `show_stats="benchmark"` is set, BirdNET collects extensive performance metrics that go far beyond standard output.

### Complete Metric Structure

The benchmarking infrastructure captures the following categories:

**Time Metrics:**
- Wall clock time (total duration)
- Worker wall time (cumulative inference time of all workers)
- Producer wall time (cumulative loading time of all producers)

**Throughput Metrics:**
- Segments per second (total and per worker)
- Real-time factor (how much faster than audio real-time)
- Audio minutes per second of processing

**Memory Metrics:**
- Peak memory usage (maximum across all processes)
- Average memory usage
- Shared memory size (ring buffer)
- Result memory size (NumPy arrays)

**Ring Buffer Metrics:**
- Average free slots
- Average filled slots
- Average busy slots

**Worker Metrics:**
- Wait time for batches (how long workers wait for data)
- Inference duration (pure model calculation time)
- Copy-to-device duration (data transfer CPU→GPU)
- Average busy workers

**Producer Metrics:**
- Batch loading duration
- Wait time for free slots
- Flush duration (writing to shared memory)

### Access to Complete Benchmark Data

```python
# After prediction with show_stats="benchmark"
result = model.predict(
    files,
    show_stats="benchmark",
    n_workers=4,
    batch_size=32
)

# Benchmark data is saved as JSON and CSV
# Path: ~/.local/share/birdnet/acoustic-benchmarks/lib-v{version}/{timestamp}/

# Programmatic access to tracking result
# (requires access to session internals - not documented!)
```

**Benchmark Output Structure:**

```
birdnet/acoustic-benchmarks/
└── lib-v{version}/
    └── session_{timestamp}/
        └── run-0/
            ├── {hash}-run-0-stats.json       # Complete metrics
            ├── {hash}-run-0-stats.txt        # Human-readable
            ├── {hash}-run-0-result.npz       # Predictions
            ├── {hash}-run-0-result.csv       # Predictions as CSV
            └── {hash}.log                     # Session log
```

### Custom Benchmark Analysis

```python
import json
from pathlib import Path
import pandas as pd

def analyze_benchmarks(benchmark_dir):
    """
    Analyzes all benchmark runs in a directory
    """
    all_runs = []
    
    for stats_file in Path(benchmark_dir).rglob("*-stats.json"):
        with open(stats_file) as f:
            data = json.load(f)
            all_runs.append(data)
    
    df = pd.DataFrame(all_runs)
    
    # Compare different configurations
    print("Performance by worker count:")
    print(df.groupby('param_workers')['speed_total_xrt'].agg(['mean', 'std']))
    
    print("\nMemory usage by batch size:")
    print(df.groupby('param_batch_size')['mem_memory_usage_maximum_MiB'].agg(['mean', 'max']))
    
    return df

# Usage
benchmark_dir = Path.home() / ".local/share/birdnet/acoustic-benchmarks"
df = analyze_benchmarks(benchmark_dir)
```

### Why It's Useful

These metrics are essential for performance tuning and debugging. They show exactly where bottlenecks are (I/O, inference, memory) and help with optimal configuration for specific hardware.

---

## 4. Session Lifecycle and Resource Management

### What It Is

Sessions have a complex lifecycle with multiple phases: initialization, resource allocation, process start, processing, cleanup.

### Session Internals

```python
class AcousticPredictionSession:
    def __init__(self, ...):
        self._conf = InferenceConfig(...)
        self._resource_manager = None
        self._process_manager = None
        self._shm_context = None
        self._is_initialized = False
    
    def __enter__(self):
        # 1. Resource allocation
        self._resource_manager = ResourceManager(self._conf)
        resources = self._resource_manager.allocate()
        
        # 2. Create shared memory
        self._shm_context = resources.ring_buffer_resources.shared_memory_context(...)
        self._shm_context.__enter__()
        
        # 3. Start processes
        self._process_manager = ProcessManager(...)
        self._process_manager.start_main_processes()
        
        self._is_initialized = True
        return self
    
    def __exit__(self, *args):
        # Cleanup in reverse order
        if self._process_manager:
            self._process_manager.join_main_processes()
        
        if self._shm_context:
            self._shm_context.__exit__(*args)
        
        if self._resource_manager:
            self._resource_manager.cleanup()
        
        self._is_initialized = False
```

### Custom Session Wrapping

For advanced use cases, you can create your own session wrappers:

```python
from contextlib import contextmanager
import time

@contextmanager
def monitored_session(model, **session_kwargs):
    """
    Session wrapper with custom monitoring and error handling
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
        
        # Custom logging/monitoring
        print(f"Session duration: {duration:.2f}s")
        if errors:
            print(f"Errors encountered: {len(errors)}")
            # Send errors to monitoring system
        
        # Cleanup validation
        # (check if all resources were released)

# Usage
with monitored_session(model, n_workers=4, device="GPU:0") as session:
    for batch in file_batches:
        result = session.run(batch)
        process_result(result)
```

### Resource Pre-Warming

For repeated sessions, you can keep resources "warm":

```python
class SessionPool:
    """
    Pool of reusable sessions (experimental!)
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

# Usage (EXPERIMENTAL - not for production!)
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

### Why It's Useful

Session management is critical for long-running services. Custom wrapping enables error recovery, resource pooling, and integration into larger systems.

---

## 5. Logging Hierarchy and Custom Loggers

### What It Is

BirdNET uses a hierarchical logging structure with session-specific loggers and queue-based multi-process logging.

### Logging Hierarchy

```
root
└── birdnet (package logger, level: INFO)
    └── birdnet.session_{session_id} (session logger, level: inherited)
        ├── birdnet.session_{id}.producer_{pid}
        ├── birdnet.session_{id}.worker_{pid}
        ├── birdnet.session_{id}.analyzer
        ├── birdnet.session_{id}.perf_tracker
        └── birdnet.session_{id}.consumer
```

### Access to Session Logger

```python
from birdnet.acoustic.inference.core.logs import get_logger_from_session

# In custom code within a session
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

BirdNET uses queue handlers for thread-safe logging across process boundaries:

```python
from birdnet.utils.logging_utils import get_package_logger
from logging.handlers import QueueHandler
import multiprocessing as mp

# Setup in main process
logging_queue = mp.Queue()
package_logger = get_package_logger()

# Handler for file output
file_handler = logging.FileHandler("app.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Queue listener in background thread
from logging.handlers import QueueListener
listener = QueueListener(logging_queue, file_handler)
listener.start()

# In worker processes
queue_handler = QueueHandler(logging_queue)
worker_logger = logging.getLogger(f"birdnet.worker_{os.getpid()}")
worker_logger.addHandler(queue_handler)
```

### Custom Logging Integration

```python
import logging
from contextlib import contextmanager

@contextmanager
def custom_logging_context(session, log_file):
    """
    Adds custom handler for session duration
    """
    # Extract session ID (internal access)
    session_id = session._session_id
    logger = get_logger_from_session(session_id, "custom")
    
    # Add custom handler
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

# Usage
with model.predict_session(...) as session:
    with custom_logging_context(session, "my_analysis.log") as logger:
        logger.info("Starting custom analysis")
        result = session.run(files)
        logger.info(f"Analysis complete: {result.n_predictions} predictions")
```

### Why It's Useful

Professional logging is essential for debugging, monitoring, and audit trails in production systems. The queue-based architecture is optimal for multi-process scenarios.

---

## Summary and Recommendations

### What You Should Take Away from This Appendix

**For Advanced Users:**
- `AcousticProgressStats` for professional monitoring
- Benchmark metrics for performance tuning
- Error recovery patterns for robustness

**For Tool Developers:**
- Ring buffer system for custom data sources
- Session lifecycle for resource management
- Logging hierarchy for multi-process debugging

**For Production Deployments:**
- Distributed processing for scaling
- Health monitoring for stability
- Graceful shutdown for reliability

### Compatibility Warning

**Important:** All features described here are:
- Not part of the stable public API
- May change without notice
- Require deep understanding of internals
- Should be used with caution in production

**Recommendation:** Use these features only when:
1. The public API doesn't meet your requirements
2. You're prepared to adapt code during updates
3. You can understand and test the implementation

### BirdNET Analyzer Connection

The **BirdNET Analyzer** likely uses many of these features:

1. **Progress callbacks** for GUI progress bars
2. **Benchmark metrics** for performance displays
3. **Custom post-processing** for result aggregation
4. **Session management** for repeated analyses
5. **Logging integration** for user feedback
6. **Error recovery** for robust file processing

### Further Exploration

If you want to use these features:

1. **Study the source code:** Look at the implementation in `birdnet/acoustic/inference/`
2. **Experiment in isolation:** Test features separately before integrating them
3. **Write tests:** Your own tests help during API changes
4. **Stay informed:** Follow GitHub issues and releases

### Contact and Community

If you have questions about these advanced features:

- **GitHub Issues:** For bug reports and feature requests
- **GitHub Discussions:** For general questions
- **Source Code:** The best documentation for internals

---

## Conclusion

This appendix has given you insight into BirdNET's internals that are normally not documented. These features are powerful but also complex and unstable. Use them wisely and be prepared for changes.

The public API should be sufficient for 95% of use cases. Only for very special requirements (e.g., custom monitoring systems, distributed processing, custom hardware integration) are these advanced features necessary.

Good luck developing on BirdNET!

---

**Appendix Version**: 1.0  
**Last Updated**: January 2025  
**Note**: This appendix is based on code analysis of BirdNET v2.4 and may contain inaccuracies. When in doubt, consult the source code directly.