"""Sim A2: refine the DFR cliff for L1 and measure L3/L5 around their BIKE t.
Output: results/simA2_dfr.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import sys, json, time, numpy as np
from multiprocessing import Pool
from scipy.stats import beta
sys.path.insert(0, ROOT + "/code")
from mdpc import QCMDPC


def work(args):
    level, wt, seed, ntr = args
    rng = np.random.default_rng(seed)
    fail = wrong = done = 0
    while done < ntr:
        K = QCMDPC(level, rng)
        for _ in range(min(25, ntr - done)):
            m = rng.integers(0, 2, K.r).astype(np.uint8)
            e = K.sample_error(rng, wt)
            ok, eh = K.decode(K.encode(m, e))
            if not ok: fail += 1
            elif not (eh == e).all(): wrong += 1
            done += 1
    return level, wt, ntr, fail, wrong


if __name__ == "__main__":
    t0 = time.time()
    plan = {"L1": ([151, 152, 153, 154, 155], 4000), "L3": ([199, 205, 211, 217], 1200), "L5": ([264, 272, 280, 288], 600)}
    jobs = []
    for lvl, (ws, n) in plan.items():
        for wt in ws:
            for c in range(4):
                jobs.append((lvl, wt, 7919 * wt + c, n // 4))
    out = {}
    with Pool(2) as p:
        for lvl, wt, n, f, w in p.imap_unordered(work, jobs):
            d = out.setdefault(f"{lvl}:{wt}", dict(level=lvl, weight=wt, n=0, fail=0, wrong=0))
            d["n"] += n; d["fail"] += f; d["wrong"] += w
    for d in out.values():
        n, f = d["n"], d["fail"]
        d["dfr"] = f / n
        d["ub95"] = float(beta.ppf(0.95, f + 1, n - f)) if f < n else 1.0
    json.dump(out, open(ROOT + "/results/simA2_dfr.json", "w"), indent=1)
    print("done", time.time() - t0)
