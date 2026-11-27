#!/usr/bin/env python3
"""Public-adversary checks on the v3 framing (run: python public_frame_test.py).
(1) the OLD public recognition test (unkeyed mask + CRC32 + seed) accepts 0 covert windows now;
(2) low-bit statistics of phase-1 / phase-2 windows vs natural uniform K-subsets are indistinguishable
    (KS test on the Hamming weight of the low beta bits and global bit-bias chi-square)."""
import hashlib, math, zlib
import numpy as np
from scipy import stats
import protocol as P
rng = np.random.default_rng(5)
N, K, T = 1 << 17, 105, 600
beta, pb = P.frame_geometry(N, K)
key = hashlib.shake_256(b"session").digest(32)

def old_public_test(S):
    """what an adversary could do against v2: unkeyed mask M(u), then CRC32 + seed check."""
    return P.extract_keyed(S, N, beta, pb, b"") is not None

def low(S):
    return P.rank_subset(sorted(S)) & ((1 << beta) - 1)

def popcount(x): return bin(x).count("1")
cov1, cov2, nat = [], [], []
acc = [0, 0, 0]
for _ in range(T):
    c = int.from_bytes(rng.bytes((beta + 7) // 8), "big") & ((1 << beta) - 1)
    S1 = P.embed_plain(rng, N, K, beta, c)
    pl = int.from_bytes(rng.bytes((pb + 7) // 8), "big") & ((1 << pb) - 1)
    S2 = P.embed_keyed(rng, N, K, beta, key, int(rng.integers(1 << P.SEED_BITS)), pl, pb)
    S0 = sorted(rng.choice(N, K, replace=False).tolist())
    for i, S in enumerate((S1, S2, S0)):
        acc[i] += old_public_test(S)
    cov1.append(popcount(low(S1))); cov2.append(popcount(low(S2))); nat.append(popcount(low(S0)))
print(f"old public test accepted: phase-1 {acc[0]}/{T}, phase-2 {acc[1]}/{T}, natural {acc[2]}/{T}")
print("KS (Hamming weight of low bits) phase-1 vs natural: p=%.3f ; phase-2 vs natural: p=%.3f"
      % (stats.ks_2samp(cov1, nat).pvalue, stats.ks_2samp(cov2, nat).pvalue))
print("expected weight beta/2 = %.1f ; means: %.1f / %.1f / %.1f" % (beta / 2, np.mean(cov1), np.mean(cov2), np.mean(nat)))
