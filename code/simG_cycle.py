"""Sim G: complete LOCAL computation cycle for one 1 KiB message (no network, no cloud):
sender  = syndrome encapsulation + DEM + F x frame embedding
receiver = F x frame extraction + F2 fountain solve + decode + DEM decrypt/verify
Repeated measurements; Output: results/simG.json"""
import sys, json, math, time, hashlib, numpy as np
from scipy import stats
sys.path.insert(0, "/home/claude/pqhide_rev/code")
from mdpc import QCMDPC
from protocol import *
from simC_protocol import dem_encrypt, dem_decrypt, bytes_to_bits, bits_to_int, int_to_bits
N = 1 << 17
rng = np.random.default_rng(321)
Kmin = 105
beta, pb = frame_geometry(N, Kmin)
key = QCMDPC("L1", rng); r = key.r
send, recv = [], []
for rep in range(40):
    payload = rng.bytes(1024)
    t0 = time.perf_counter()
    e = key.sample_error(rng, key.t); sp = key.encrypt_syndrome(e); blob = dem_encrypt(e, payload)
    Kk = hashlib.shake_256(b"PQHide-K" + np.packbits(e).tobytes()).digest(32)
    F1 = math.ceil(r / beta)
    z1 = np.concatenate([sp, rng.integers(0, 2, F1 * beta - r).astype(np.uint8)])
    c1 = [bits_to_int(z1[i * beta:(i + 1) * beta]) for i in range(F1)]
    bb = bytes_to_bits(blob); nz = len(bb)
    F = math.ceil(nz / pb)
    z2 = np.concatenate([bb, rng.integers(0, 2, F * pb - nz).astype(np.uint8)])
    c2 = [bits_to_int(z2[i * pb:(i + 1) * pb]) for i in range(F)]
    frames = [embed_plain(rng, N, 105 + int(rng.integers(0, 20)), beta, c) for c in c1]
    for j in range(1, F + 3):
        pay = fountain_encode(c2, j)
        frames.append((j, pay, embed_keyed(rng, N, 105 + int(rng.integers(0, 20)), beta, Kk, j, pay, pb)))
    send.append(time.perf_counter() - t0)
    t0 = time.perf_counter()
    plain = [extract_plain(S, N, beta) for S in frames[:F1]]
    zz1 = np.concatenate([int_to_bits(x, beta) for x in plain])[:r]
    ok, eh = key.decode_ct(zz1)
    Kr = hashlib.shake_256(b"PQHide-K" + np.packbits(eh).tobytes()).digest(32)
    dec = FountainDecoder(F)
    for j, pay, S in frames[F1:]:
        out = extract_keyed(S, N, beta, pb, Kr)
        if out: dec.add(*out)
        if dec.done(): break
    sol = dec.solve()
    zz = np.concatenate([int_to_bits(c, pb) for c in sol])[:nz]
    got = dem_decrypt(eh, np.packbits(zz).tobytes()) if ok else None
    recv.append(time.perf_counter() - t0)
    assert got == payload
def summ(x):
    x = np.array(x) * 1e3; n = len(x)
    return dict(mean_ms=float(x.mean()), sd_ms=float(x.std(ddof=1)), ci95_ms=float(stats.t.ppf(.975, n - 1) * x.std(ddof=1) / math.sqrt(n)), n=n)
json.dump(dict(F=F, F1=F1, n_bits=nz, sender=summ(send), receiver=summ(recv)), open("/home/claude/pqhide_rev/results/simG.json", "w"), indent=1)
print(summ(send), summ(recv), F)
