"""
Hardware detection for birdnet-copter.

Detects GPU (NVIDIA) and CPU/RAM capabilities at startup.
Results are stored in HardwareInfo and attached to AppState.
"""

import ctypes
import ctypes.util
from dataclasses import dataclass
from typing import Optional

import psutil
from loguru import logger


# ---------------------------------------------------------------------------
# CUDA device properties struct (subset of cudaDeviceProp)
# Only the fields we actually read are listed; the struct must be large enough
# to hold the full cudaDeviceProp layout (>= 256 bytes covers all CUDA versions).
# ---------------------------------------------------------------------------

class _CudaDeviceProp(ctypes.Structure):
    _fields_ = [
        ("name",                       ctypes.c_char * 256),
        ("uuid",                       ctypes.c_byte  * 16),
        ("luid",                       ctypes.c_byte  * 8),
        ("luidDeviceNodeMask",         ctypes.c_uint),
        ("totalGlobalMem",             ctypes.c_size_t),
        ("sharedMemPerBlock",          ctypes.c_size_t),
        ("regsPerBlock",               ctypes.c_int),
        ("warpSize",                   ctypes.c_int),
        ("memPitch",                   ctypes.c_size_t),
        ("maxThreadsPerBlock",         ctypes.c_int),
        ("maxThreadsDim",              ctypes.c_int   * 3),
        ("maxGridSize",                ctypes.c_int   * 3),
        ("clockRate",                  ctypes.c_int),
        ("totalConstMem",              ctypes.c_size_t),
        ("major",                      ctypes.c_int),   # compute capability major
        ("minor",                      ctypes.c_int),   # compute capability minor
        ("textureAlignment",           ctypes.c_size_t),
        ("texturePitchAlignment",      ctypes.c_size_t),
        ("deviceOverlap",              ctypes.c_int),
        ("multiProcessorCount",        ctypes.c_int),   # SM count  ← we need this
        ("kernelExecTimeoutEnabled",   ctypes.c_int),
        ("integrated",                 ctypes.c_int),
        ("canMapHostMemory",           ctypes.c_int),
        ("computeMode",                ctypes.c_int),
        # Pad to 1024 bytes so the struct is large enough for all CUDA versions
        ("_pad",                       ctypes.c_byte  * 600),
    ]


# ---------------------------------------------------------------------------
# CUDA cores per SM lookup  (compute capability major.minor → cores per SM)
# Source: NVIDIA CUDA Programming Guide, Appendix H
# ---------------------------------------------------------------------------

_CORES_PER_SM: dict[tuple[int, int], int] = {
    (2, 0): 32,   # Fermi
    (2, 1): 48,   # Fermi
    (3, 0): 192,  # Kepler
    (3, 2): 192,
    (3, 5): 192,
    (3, 7): 192,
    (5, 0): 128,  # Maxwell
    (5, 2): 128,
    (5, 3): 128,
    (6, 0): 64,   # Pascal
    (6, 1): 128,
    (6, 2): 128,
    (7, 0): 64,   # Volta
    (7, 2): 64,
    (7, 5): 64,   # Turing
    (8, 0): 64,   # Ampere
    (8, 6): 128,
    (8, 7): 128,
    (8, 9): 128,  # Ada Lovelace
    (9, 0): 128,  # Hopper
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class HardwareInfo:
    """
    Hardware capabilities detected at startup.

    GPU fields are None when no NVIDIA GPU is available or detection failed.
    sm_count / cores_per_sm are None when libcuda is not accessible.
    """
    # GPU
    has_nvidia_gpu: bool
    gpu_name: Optional[str]
    gpu_vram_gb: Optional[float]
    gpu_sm_count: Optional[int]
    gpu_cores_per_sm: Optional[int]
    gpu_shaders: Optional[int]          # gpu_sm_count * gpu_cores_per_sm

    # CPU
    cpu_count_physical: int
    cpu_count_logical: int
    cpu_count_for_inference: int        # max(1, logical - 2) if logical >= 3 else logical
    sleep_flag: bool                    # True when logical < 3

    # RAM
    ram_total_gb: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_libcuda() -> Optional[ctypes.CDLL]:
    """Try to load libcuda.so (Linux) or nvcuda.dll (Windows)."""
    for name in ("cuda", "nvcuda"):
        path = ctypes.util.find_library(name)
        if path:
            try:
                return ctypes.CDLL(path)
            except OSError:
                pass
    return None


def _get_sm_info(lib: ctypes.CDLL, device_index: int = 0) -> tuple[Optional[int], Optional[int]]:
    """
    Query SM count and cores-per-SM via cudaGetDeviceProperties.

    Returns:
        (sm_count, cores_per_sm) – both None on failure
    """
    try:
        prop = _CudaDeviceProp()
        ret = lib.cudaGetDeviceProperties(ctypes.byref(prop), ctypes.c_int(device_index))
        if ret != 0:
            logger.warning(f"cudaGetDeviceProperties returned error code {ret}")
            return None, None

        sm_count = prop.multiProcessorCount
        cc = (prop.major, prop.minor)

        # Exact match first, then major-only fallback
        cores_per_sm = _CORES_PER_SM.get(cc)
        if cores_per_sm is None:
            cores_per_sm = _CORES_PER_SM.get((prop.major, 0))

        if cores_per_sm is None:
            logger.warning(
                f"Unknown compute capability {prop.major}.{prop.minor}, "
                "cores_per_sm set to None"
            )

        return sm_count, cores_per_sm

    except Exception as e:
        logger.warning(f"Failed to query cudaGetDeviceProperties: {e}")
        return None, None


def _get_gpu_info() -> tuple[bool, Optional[str], Optional[float], Optional[int], Optional[int], Optional[int]]:
    """
    Detect NVIDIA GPU via pynvml.

    Returns:
        (has_gpu, name, vram_gb, sm_count, cores_per_sm, shaders)
    """
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()

        if count == 0:
            pynvml.nvmlShutdown()
            return False, None, None, None, None, None

        # Use first GPU
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        vram_gb = round(mem_info.total / (1024 ** 3), 1)

        pynvml.nvmlShutdown()

        # SM info via libcuda
        sm_count: Optional[int] = None
        cores_per_sm: Optional[int] = None
        shaders: Optional[int] = None

        lib = _load_libcuda()
        if lib is not None:
            sm_count, cores_per_sm = _get_sm_info(lib)
            if sm_count is not None and cores_per_sm is not None:
                shaders = sm_count * cores_per_sm
        else:
            logger.warning("libcuda not found – sm_count and cores_per_sm unavailable")

        return True, name, vram_gb, sm_count, cores_per_sm, shaders

    except ImportError:
        logger.warning("pynvml not installed – GPU detection unavailable")
        return False, None, None, None, None, None
    except Exception as e:
        logger.warning(f"GPU detection failed: {e}")
        return False, None, None, None, None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_hardware() -> HardwareInfo:
    """
    Detect hardware capabilities of the current host.

    Reads GPU info via pynvml + libcuda, CPU counts via psutil,
    and RAM via psutil.virtual_memory().

    Returns:
        HardwareInfo dataclass instance.
    """
    # --- GPU ---
    has_gpu, gpu_name, vram_gb, sm_count, cores_per_sm, shaders = _get_gpu_info()

    # --- CPU ---
    logical = psutil.cpu_count(logical=True) or 1
    physical = psutil.cpu_count(logical=False) or logical

    if logical >= 3:
        inference_cores = logical - 2
        sleep_flag = False
    else:
        inference_cores = logical
        sleep_flag = True

    # --- RAM ---
    ram_bytes = psutil.virtual_memory().total
    ram_gb = round(ram_bytes / (1024 ** 3), 1)

    info = HardwareInfo(
        has_nvidia_gpu=has_gpu,
        gpu_name=gpu_name,
        gpu_vram_gb=vram_gb,
        gpu_sm_count=sm_count,
        gpu_cores_per_sm=cores_per_sm,
        gpu_shaders=shaders,
        cpu_count_physical=physical,
        cpu_count_logical=logical,
        cpu_count_for_inference=inference_cores,
        sleep_flag=sleep_flag,
        ram_total_gb=ram_gb,
    )

    logger.info(
        f"Hardware detected: GPU={'%s (%.1f GB, %s SMs, %s cores/SM)' % (gpu_name, vram_gb, sm_count, cores_per_sm) if has_gpu else 'none'} | "
        f"CPU={logical} logical / {physical} physical | "
        f"RAM={ram_gb} GB"
    )

    return info

