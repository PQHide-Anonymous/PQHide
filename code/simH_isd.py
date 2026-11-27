"""Sim H: transparent information-set-decoding (ISD) work-factor ESTIMATES for the BIKE Round-4 shapes used by PQHide.
Model (all in log2, polynomial/memory/depth overheads of the quantum circuit NOT modelled):
  Prange     : iterations = C(n,k-lowering) / ..., cost/iter = Gaussian elimination (n-k)^2 (n+k)/2 bit-ops
  Stern      : Peters-style cost, optimised over (p, l)
  DOOM       : message recovery divides the work factor by sqrt(r) (decoding one out of many), key recovery by r (BIKE spec B.2.1)
  Quantum    : Bernstein: Grover over the iterations of Prange/Stern -> sqrt(#iterations) x cost per iteration (no MAXDEPTH constraint)
These are *estimates of an attacker's cost in a simplified model*, not a security proof and not a substitute for a
current estimator (e.g. a BJMM/MMT-based one); they upper-bound the best attack cost when the algorithm is weaker than the best known.
Output: results/simH.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import math, json
lg = lambda x: math.log2(x)
def lc(n, k):  # log2 C(n,k)
    if k < 0 or k > n: return float("-inf")
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)) / math.log(2)
def lsum(a, b):
    m = max(a, b); return m + lg(2 ** (a - m) + 2 ** (b - m))

def prange(n, k, t):
    # per iteration success: all t errors outside an information set: C(n-k,t)/C(n,t)
    logp = lc(n - k, t) - lc(n, t)
    cost_iter = lg((n - k) ** 2 * (n + k) / 2)
    return dict(iters=-logp, cost_iter=cost_iter, total=cost_iter - logp)

def stern(n, k, t):
    best = None
    for p in range(1, 9):
        for l in range(1, 80):
            if t - 2 * p < 0 or n - k - l < t - 2 * p: continue
            half = k // 2
            logP = 2 * lc(half, p) + lc(n - k - l, t - 2 * p) - lc(n, t)       # success prob per iteration
            ge = lg((n - k) ** 2 * (n + k) / 2)
            lists = lsum(lg(2 * l) + lc(half, p), lg(2 * p * max(n - k - l, 1)) + 2 * lc(half, p) - l - 1)
            cost_iter = lsum(ge, lists)
            tot = cost_iter - logP
            if best is None or tot < best["total"]:
                best = dict(iters=-logP, cost_iter=cost_iter, total=tot, p=p, l=l)
    return best

PARAMS = {"L1": (12323, 142, 134), "L3": (24659, 206, 199), "L5": (40973, 274, 264)}
out = {}
for lvl, (r, w, t) in PARAMS.items():
    n, k = 2 * r, r
    d = {}
    for name, fn in [("prange", prange), ("stern", stern)]:
        msg = fn(n, k, t); key = fn(n, k, w)
        d[name] = dict(
            msg_classical_log2=msg["total"] - 0.5 * lg(r),                      # DOOM
            msg_quantum_log2=0.5 * msg["iters"] + msg["cost_iter"] - 0.5 * lg(r),  # Grover on iterations (+ DOOM, optimistic)
            key_classical_log2=key["total"] - lg(r),
            key_quantum_log2=0.5 * key["iters"] + key["cost_iter"] - lg(r),
            msg_params={k_: v for k_, v in msg.items() if k_ in ("p", "l")},
        )
    d["bike_spec_asymptotic_msg_log2"] = t - 0.5 * lg(r)       # BIKE spec B.2.1: 2^{t(1+o(1))}/sqrt(r), c = 1
    d["bike_spec_asymptotic_key_log2"] = w - lg(r)
    d["r"], d["w"], d["t"] = r, w, t
    out[lvl] = d
json.dump(out, open(ROOT + "/results/simH.json", "w"), indent=1)
for lvl, d in out.items():
    print(lvl, {k: (round(v, 1) if isinstance(v, float) else v) for k, v in d["prange"].items() if k != "msg_params"}, "|",
          {k: round(v, 1) for k, v in d["stern"].items() if k != "msg_params"}, d["stern"]["msg_params"],
          "| asym msg", round(d["bike_spec_asymptotic_msg_log2"], 1), "key", round(d["bike_spec_asymptotic_key_log2"], 1))
