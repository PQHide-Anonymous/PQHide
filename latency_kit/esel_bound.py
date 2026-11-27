#!/usr/bin/env python3
"""Computable upper bound on the cover-model gap eps_sel (Section "Security").

Model (the ONLY case covered): in a window, file i is edited independently with
probability p_i (per-file rates estimated from a trace), and the window set S is
observed conditioned on its size K.  Then P(S | K) = prod_{i in S} w_i / e_K(w),
w_i = p_i/(1-p_i), e_K = K-th elementary symmetric polynomial (conditional Bernoulli).
Clustering of edits (files edited together) is NOT covered: the bound says nothing
about it and a deployment must exclude such files from the pool (pool rule ii).

Quantities (all exact up to floating point):
  KL_K = KL(Unif || P(.|K)) = log e_K(w) - (K/N) sum_i log w_i - log C(N,K)
  TV_K <= sqrt(KL_K / 2)                       (Pinsker)
  over W independent windows with count law K ~ pK:
  TV_W <= sqrt(W * D / 2),   D = E_K[KL_K]     (KL adds over independent windows)
and also TV_W <= W * max_K TV_K (union bound, used in the theorem).  We report both.
"""
import argparse, json, math
import numpy as np

def log_esym(logw, K):
    """log e_k(w) for k=0..K by the standard DP in log-space (stable)."""
    N = len(logw)
    le = np.full(K + 1, -np.inf); le[0] = 0.0
    for i in range(N):
        lw = logw[i]
        # e_k <- e_k + w_i * e_{k-1}
        prev = le.copy()
        le[1:] = np.logaddexp(prev[1:], prev[:-1] + lw)
    return le

def kl_unif_to_condbern(p, K):
    p = np.asarray(p, float)
    N = len(p)
    logw = np.log(p) - np.log1p(-p)
    le = log_esym(logw, K)[K]
    logC = math.lgamma(N + 1) - math.lgamma(K + 1) - math.lgamma(N - K + 1)
    return le - (K / N) * logw.sum() - logC

def bound(p, countlaw, W):
    """countlaw: dict K -> prob."""
    kl = {K: max(0.0, kl_unif_to_condbern(p, K)) for K in countlaw}
    D = sum(countlaw[K] * kl[K] for K in countlaw)
    tv1 = max(math.sqrt(v / 2) for v in kl.values())
    return {"D_mean_nats": D, "eps_sel_pinsker_max": min(1.0, tv1),
            "W": W, "tv_W_union": min(1.0, W * tv1),
            "tv_W_kl_additive": min(1.0, math.sqrt(W * D / 2))}

def lognormal_rates(N, sigma, mean_rate, rng):
    r = np.exp(rng.normal(0, sigma, N)); r *= mean_rate / r.mean()
    return np.clip(r, 1e-9, 0.9)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rates", help="CSV/one-per-line per-file edit probabilities per window")
    ap.add_argument("--K", type=int, nargs="+", default=[20, 60, 105])
    ap.add_argument("--W", type=int, default=100)
    a = ap.parse_args()
    p = np.loadtxt(a.rates)
    law = {K: 1 / len(a.K) for K in a.K}
    print(json.dumps(bound(p, law, a.W), indent=1))
