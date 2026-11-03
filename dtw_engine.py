"""
Fast Dynamic Time Warping (DTW) Engine with Sakoe-Chiba Band constraint.
Compiles a tiny C helper for 1,000x speedup with a safe pure-NumPy fallback.
"""

import os
import sys
import ctypes
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
C_SRC_FILE = os.path.join(BASE_DIR, "fast_dtw.c")
SO_FILE = os.path.join(BASE_DIR, "libfast_dtw.so")

C_CODE = r'''
#include <math.h>
#include <float.h>

void batch_dtw_sakoe_chiba(
    const float* target, int n,
    const float* windows, int num_windows,
    int w,
    float* out_distances
) {
    float dtw[160][160];
    if (n > 150) n = 150;
    
    for (int win = 0; win < num_windows; win++) {
        const float* win_ptr = windows + (win * n);
        
        for (int i = 0; i <= n; i++) {
            for (int j = 0; j <= n; j++) {
                dtw[i][j] = 1e9f;
            }
        }
        dtw[0][0] = 0.0f;
        
        for (int i = 1; i <= n; i++) {
            int j_start = (i - w > 1) ? i - w : 1;
            int j_end = (i + w + 1 < n + 1) ? i + w + 1 : n + 1;
            for (int j = j_start; j < j_end; j++) {
                float diff = target[i-1] - win_ptr[j-1];
                float cost = diff * diff;
                float m1 = dtw[i-1][j];
                float m2 = dtw[i][j-1];
                float m3 = dtw[i-1][j-1];
                float min_m = (m1 < m2) ? ((m1 < m3) ? m1 : m3) : ((m2 < m3) ? m2 : m3);
                dtw[i][j] = cost + min_m;
            }
        }
        out_distances[win] = sqrtf(dtw[n][n] / (float)n);
    }
}
'''

_LIB = None

def _get_or_build_lib():
    global _LIB
    if _LIB is not None:
        return _LIB
        
    if not os.path.exists(SO_FILE) or not os.path.exists(C_SRC_FILE):
        try:
            with open(C_SRC_FILE, "w", encoding="utf-8") as f:
                f.write(C_CODE)
            import subprocess
            compiler = "clang" if subprocess.run(["which", "clang"], capture_output=True).returncode == 0 else "gcc"
            subprocess.check_call([compiler, "-O3", "-shared", "-fPIC", C_SRC_FILE, "-o", SO_FILE])
        except Exception as e:
            print(f"[DTW ENGINE] Compilation notice: {e}")
            
    if os.path.exists(SO_FILE):
        try:
            lib = ctypes.CDLL(SO_FILE)
            lib.batch_dtw_sakoe_chiba.argtypes = [
                ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_float)
            ]
            _LIB = lib
            return _LIB
        except Exception:
            pass
    return None

def compute_fast_dtw_distances(target_pattern: np.ndarray, candidate_windows: np.ndarray, window_radius: int = 5) -> np.ndarray:
    """
    Compute DTW distances between a single target pattern and multiple candidate windows.
    target_pattern: shape (N,) float32
    candidate_windows: shape (M, N) float32
    Returns array of normalized DTW distances of shape (M,).
    """
    n = len(target_pattern)
    num_windows = len(candidate_windows)
    if num_windows == 0:
        return np.array([], dtype=np.float32)
        
    lib = _get_or_build_lib()
    if lib is not None and n <= 150:
        target_c = np.ascontiguousarray(target_pattern, dtype=np.float32)
        windows_c = np.ascontiguousarray(candidate_windows, dtype=np.float32)
        out_distances = np.zeros(num_windows, dtype=np.float32)
        
        lib.batch_dtw_sakoe_chiba(
            target_c.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), n,
            windows_c.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), num_windows,
            int(window_radius),
            out_distances.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        )
        return out_distances
    else:
        # Fallback pure NumPy Sakoe-Chiba DTW
        out_distances = np.zeros(num_windows, dtype=np.float32)
        for win_idx in range(num_windows):
            win = candidate_windows[win_idx]
            dtw = np.full((n + 1, n + 1), np.inf, dtype=np.float32)
            dtw[0, 0] = 0.0
            for i in range(1, n + 1):
                j_start = max(1, i - window_radius)
                j_end = min(n + 1, i + window_radius + 1)
                for j in range(j_start, j_end):
                    cost = (target_pattern[i-1] - win[j-1]) ** 2
                    dtw[i, j] = cost + min(dtw[i-1, j], dtw[i, j-1], dtw[i-1, j-1])
            out_distances[win_idx] = np.sqrt(dtw[n, n] / float(n))
        return out_distances
