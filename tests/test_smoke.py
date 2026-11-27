"""Fast correctness checks (about a minute): python tests/test_smoke.py"""
import math, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "code"))
import protocol as P
from mdpc import QCMDPC

rng = np.random.default_rng(0)

# 1. colex rank coding is a bijection between K-subsets and integers
for _ in range(200):
    S = sorted(rng.choice(5000, 12, replace=False).tolist())
    assert P.unrank_subset(P.rank_subset(S), 5000, 12) == S
print("rank/unrank: ok")

# 2. v3 framing: a plain chunk and a keyed frame are recovered; a modified set / wrong key is rejected
import hashlib
N, Kmin = 131072, 50
beta, pbits = P.frame_geometry(N, Kmin)
key32 = hashlib.shake_256(b"test").digest(32)
for _ in range(20):
    chunk = int.from_bytes(rng.bytes(beta // 8 + 1), "big") % (1 << beta)
    assert P.extract_plain(P.embed_plain(rng, N, Kmin, beta, chunk), N, beta) == chunk
    payload = int.from_bytes(rng.bytes(pbits // 8 + 1), "big") % (1 << pbits)
    S = P.embed_keyed(rng, N, Kmin, beta, key32, 1234, payload, pbits)
    out = P.extract_keyed(S, N, beta, pbits, key32)
    assert out is not None and out[1] == payload, "frame not recovered"
    assert P.extract_keyed(S, N, beta, pbits, b"x" * 32) is None, "frame accepted without the key"
    S2 = sorted(set(S[:-1]) | {(S[-1] + 1) % N})
    if len(S2) == len(S):
        assert P.extract_keyed(S2, N, beta, pbits, key32) is None, "modified edit set accepted"
print("plain chunk / keyed frame embed-extract (+ rejection without the key): ok")

# 3. QC-MDPC level 1: decode the syndrome of a weight-t error (BGF, 5 iterations)
key = QCMDPC("L1", rng)
ok = 0
for _ in range(5):
    e = key.sample_error(rng, key.t)
    sp = key.encrypt_syndrome(e)
    success, e_hat = key.decode_ct(sp)
    ok += int(success and np.array_equal(e_hat, e))
assert ok >= 4, f"decoding succeeded only {ok}/5 times"
print(f"QC-MDPC L1 decoding at t={key.t}: {ok}/5 ok")
print("ALL SMOKE TESTS PASSED")
