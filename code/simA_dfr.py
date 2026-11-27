"""Sim A: decoding-failure rate (DFR) of the QC-MDPC/BGF harness as a function of the total
error weight (intentional t_s + environmental noise), over fresh random keys.
Output: results/simA_dfr.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import sys, json, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, ROOT + "/code")
from mdpc import QCMDPC

LEVEL = "L1"
WEIGHTS = [100, 110, 120, 128, 134, 138, 142, 146, 150, 156, 162]
TRIALS = 6000        # per weight
TRIALS_PER_KEY = 50


def work(args):
    wt, seed, ntr = args
    rng = np.random.default_rng(seed)
    fail = wrong = 0
    done = 0
    while done < ntr:
        K = QCMDPC(LEVEL, rng)
        for _ in range(min(TRIALS_PER_KEY, ntr - done)):
            m = rng.integers(0, 2, K.r).astype(np.uint8)
            e = K.sample_error(rng, wt)
            y = K.encode(m, e)
            ok, eh = K.decode(y)
            if not ok:
                fail += 1
            elif not (eh == e).all():
                wrong += 1
            done += 1
    return wt, ntr, fail, wrong


if __name__ == "__main__":
    t0 = time.time()
    jobs = []
    for wt in WEIGHTS:
        for c in range(4):
            jobs.append((wt, 1000 * wt + c, TRIALS // 4))
    out = {}
    with Pool(2) as p:
        for wt, n, f, w in p.imap_unordered(work, jobs):
            d = out.setdefault(wt, dict(n=0, fail=0, wrong=0))
            d["n"] += n; d["fail"] += f; d["wrong"] += w
    for wt, d in out.items():
        n, f = d["n"], d["fail"]
        # one-sided 95% upper bound (rule of three for f=0, Clopper-Pearson otherwise)
        from scipy.stats import beta
        d["dfr"] = f / n
        d["ub95"] = float(beta.ppf(0.95, f + 1, n - f)) if f < n else 1.0
    json.dump(dict(level=LEVEL, results={str(k): v for k, v in sorted(out.items())},
                   elapsed_s=time.time() - t0), open(ROOT + "/results/simA_dfr.json", "w"), indent=1)
    print("done", time.time() - t0)
