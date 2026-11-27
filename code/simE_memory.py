"""Sim E: peak Python-heap memory (tracemalloc) of keygen / encode / decode per level, and
peak RSS of the process.  Output: results/simE.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import sys, json, resource, tracemalloc, numpy as np
sys.path.insert(0, ROOT + "/code")
from mdpc import QCMDPC
rng = np.random.default_rng(5)
out = {}
for lvl in ["L1", "L3", "L5"]:
    tracemalloc.start(); tracemalloc.reset_peak()
    K = QCMDPC(lvl, rng); kg = tracemalloc.get_traced_memory()[1]
    m = rng.integers(0, 2, K.r).astype(np.uint8)
    tracemalloc.reset_peak(); y = K.encode(m, K.sample_error(rng, K.t)); en = tracemalloc.get_traced_memory()[1]
    tracemalloc.reset_peak(); K.decode(y); de = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    out[lvl] = dict(keygen_peak_MiB=kg / 2**20, encode_peak_MiB=en / 2**20, decode_peak_MiB=de / 2**20)
out["process_peak_rss_MiB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
json.dump(out, open(ROOT + "/results/simE.json", "w"), indent=1); print(out)
