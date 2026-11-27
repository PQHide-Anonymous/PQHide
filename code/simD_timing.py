"""Sim D: local computation costs (repeated measurements, mean/sd/95% CI) for
 - PQHide-v2 (QC-MDPC, BIKE Round-4 sizes L1/L3/L5): keygen, encode, decode, frame embed/extract
 - classical baselines in the *same Python harness*: RSA-2048 OAEP, X25519 ECDH+HKDF (ECIES-style)
Also reports ciphertext/public-key sizes.  Network/cloud costs are NOT measured here.
Output: results/simD.json"""
import sys, json, time, math
import numpy as np
from scipy import stats
sys.path.insert(0, "/home/claude/pqhide_rev/code")
from mdpc import QCMDPC
from protocol import *
from cryptography.hazmat.primitives.asymmetric import rsa, padding, x25519
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def summ(xs):
    xs = np.array(xs) * 1e3
    n = len(xs)
    ci = stats.t.ppf(0.975, n - 1) * xs.std(ddof=1) / math.sqrt(n)
    return dict(mean_ms=float(xs.mean()), sd_ms=float(xs.std(ddof=1)), ci95_ms=float(ci), n=n)


def timeit(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter(); fn(); out.append(time.perf_counter() - t)
    return summ(out)


rng = np.random.default_rng(11)
res = {}
for lvl, reps in [("L1", 200), ("L3", 100), ("L5", 60)]:
    K = QCMDPC(lvl, rng)
    r = K.r
    m = rng.integers(0, 2, r).astype(np.uint8)
    holder = {}
    kg = timeit(lambda: QCMDPC(lvl, rng), 20)
    e = K.sample_error(rng, K.t)
    enc = timeit(lambda: K.encode(m, K.sample_error(rng, K.t)), reps)
    ys = [K.encode(m, K.sample_error(rng, K.t)) for _ in range(reps)]
    it = iter(ys)
    fails = 0
    def d():
        global fails
        ok, _ = K.decode(next(it))
        fails += (not ok)
    dec = timeit(d, reps)
    res[lvl] = dict(r=r, n=2 * r, w=K.w, t=K.t, keygen=kg, encode=enc, decode=dec, decode_fail_in_timing_runs=fails,
                    pk_bytes=math.ceil(r / 8), ct_bits=2 * r, msg_bits_capacity=r)
# frame embed/extract (N=2^17)
N = 1 << 17
for Kmin, K in [(50, 80), (105, 105)]:
    beta, pb = frame_geometry(N, Kmin)
    pay = int.from_bytes(rng.bytes(pb // 8 + 1), "big") & ((1 << pb) - 1)
    kk = b'k' * 32
    emb = timeit(lambda: embed_keyed(rng, N, K, beta, kk, 7, pay, pb), 100)
    S = embed_keyed(rng, N, K, beta, kk, 7, pay, pb)
    ext = timeit(lambda: extract_keyed(S, N, beta, pb, kk), 100)
    res[f"frame_Kmin{Kmin}"] = dict(beta=beta, payload_bits=pb, K=K, embed=emb, extract=ext)
# baselines
msg = b"x" * 190
rk = rsa.generate_private_key(65537, 2048)
pk = rk.public_key()
oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
ct = pk.encrypt(msg, oaep)
res["RSA2048_OAEP"] = dict(encrypt=timeit(lambda: pk.encrypt(msg, oaep), 300),
                           decrypt=timeit(lambda: rk.decrypt(ct, oaep), 300), ct_bytes=len(ct), pk_bytes=270, quantum_safe=False)
sk = x25519.X25519PrivateKey.generate(); spub = sk.public_key()
def ecies():
    eph = x25519.X25519PrivateKey.generate()
    k = HKDF(hashes.SHA256(), 32, None, b"x").derive(eph.exchange(spub))
    return eph.public_key()
def ecies_dec():
    eph = x25519.X25519PrivateKey.generate().public_key()
    HKDF(hashes.SHA256(), 32, None, b"x").derive(sk.exchange(eph))
res["X25519_ECIES"] = dict(encrypt=timeit(ecies, 300), decrypt=timeit(ecies_dec, 300), ct_bytes=32, pk_bytes=32, quantum_safe=False)
json.dump(res, open("/home/claude/pqhide_rev/results/simD.json", "w"), indent=1)
print("done")
