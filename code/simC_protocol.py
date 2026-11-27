"""Sim C (v3 framing): complete PQHide cycle in an in-memory cloud emulator (no network).

Cycle (one fresh encapsulation per cycle):
  phase 1: s' = e0*q+e1 (r bits, uniform under QC-SD) is cut into F1 chunks of beta bits (+ fresh random
           padding) and sent in the clear, one chunk per window with natural count K >= Kmin (colex rank,
           no seed, no CRC, no mask: nothing is checkable without the secret key);
  phase 2: blob = (payload xor stream(K)) || tag, K = H(e), is cut into F2 chunks, fountain-coded, and sent as
           CRC frames masked by M(K, u) (a mask keyed by the secret session key), T2 = F2 + EXTRA windows.
  The sender repeats cycles (fresh e, fresh K) until the mailbox ends; delivery is detected by the receiver only.
Channel: natural counts K ~ NB(mean mu, kappa); external edits ~ Poisson(nuN) per window are unioned in.
Receiver: after each eligible window (observed K' >= Kmin) it tries the last F1 plain chunks as a ciphertext
  (BIKE-style decoding with the secret key); on success it derives K and reads phase-2 frames with K.
Output: results/simC.json"""
import sys, json, math, time, hashlib
import numpy as np
from multiprocessing import Pool
from scipy import stats
sys.path.insert(0, "/home/claude/pqhide_rev/code")
from mdpc import QCMDPC
from protocol import *

N = 1 << 17
MU, KAPPA = 105.0, 8.0
PAYLOAD_BYTES = 1024
TAG_BITS = 128


TAG_BYTES = 16


def dem_encrypt(e_bits, payload):
    """K = SHAKE256(e); c2 = payload xor stream(K); tag = MAC_K(payload). Everything from the RO."""
    K = hashlib.shake_256(b"PQHide-K" + np.packbits(e_bits).tobytes()).digest(32)
    stream = hashlib.shake_256(b"enc" + K).digest(len(payload))
    c2 = bytes(a ^ b for a, b in zip(payload, stream))
    tag = hashlib.shake_256(b"mac" + K + payload).digest(TAG_BYTES)
    return c2 + tag


def dem_decrypt(e_bits, blob):
    K = hashlib.shake_256(b"PQHide-K" + np.packbits(e_bits).tobytes()).digest(32)
    c2, tag = blob[:-TAG_BYTES], blob[-TAG_BYTES:]
    stream = hashlib.shake_256(b"enc" + K).digest(len(c2))
    payload = bytes(a ^ b for a, b in zip(c2, stream))
    ok = hashlib.shake_256(b"mac" + K + payload).digest(TAG_BYTES) == tag
    return payload if ok else None


def bits_to_int(a):
    return int("".join(map(str, a.tolist())), 2)


def int_to_bits(x, n):
    return np.array([int(b) for b in bin(x)[2:].zfill(n)], dtype=np.uint8)


def bytes_to_bits(b):
    return np.unpackbits(np.frombuffer(b, dtype=np.uint8))


def session_key(e_bits):
    return hashlib.shake_256(b"PQHide-K" + np.packbits(e_bits).tobytes()).digest(32)


EXTRA = 8


def one_message(args):
    Kmin, nuN, seed, max_windows = args
    rng = np.random.default_rng(seed)
    key = QCMDPC("L1", rng)
    r = key.r
    payload = rng.bytes(PAYLOAD_BYTES)
    beta, pb = frame_geometry(N, Kmin)
    F1 = math.ceil(r / beta)
    F2 = math.ceil(8 * (PAYLOAD_BYTES + TAG_BYTES) / pb)
    T2 = F2 + EXTRA
    L, cands = [], []           # receiver state: plain chunks of eligible windows; active phase-2 candidates
    windows = eligible = cycles = 0
    st = None                   # sender state
    delivered = correct = False
    p1_corrupt_cycles = 0
    while windows < max_windows and not delivered:
        windows += 1
        K = int(rng.poisson(MU * rng.gamma(KAPPA, 1 / KAPPA)))
        if K < Kmin:
            continue                                   # sender silent: genuine traffic only
        if st is None or st["pos"] >= F1 + T2:         # start a new cycle: fresh encapsulation
            cycles += 1
            e = key.sample_error(rng, key.t)
            sp = key.encrypt_syndrome(e)
            Kk = session_key(e)
            blob = dem_encrypt(e, payload)
            bb = bytes_to_bits(blob)
            z1 = np.concatenate([sp, rng.integers(0, 2, F1 * beta - r).astype(np.uint8)])
            c1 = [bits_to_int(z1[i * beta:(i + 1) * beta]) for i in range(F1)]
            z2 = np.concatenate([bb, rng.integers(0, 2, F2 * pb - len(bb)).astype(np.uint8)])
            c2 = [bits_to_int(z2[i * pb:(i + 1) * pb]) for i in range(F2)]
            st = dict(pos=0, c1=c1, c2=c2, key=Kk, fseed=1, clean=True)
        if st["pos"] < F1:
            S = embed_plain(rng, N, K, beta, st["c1"][st["pos"]])
        else:
            pay = fountain_encode(st["c2"], st["fseed"])
            S = embed_keyed(rng, N, K, beta, st["key"], st["fseed"], pay, pb)
            st["fseed"] += 1
        st["pos"] += 1
        obs = set(S)
        E = int(rng.poisson(nuN))
        if E:
            extra = set(rng.integers(0, N, size=E).tolist()) - obs
            if extra and st["pos"] <= F1:
                st["clean"] = False
            obs |= extra
        if len(obs) < Kmin:
            continue
        eligible += 1
        so = sorted(obs)
        # ---- receiver ----
        for c in list(cands):
            out = extract_keyed(so, N, beta, pb, c["key"])
            c["n"] += 1
            if out is not None:
                c["dec"].add(*out)
            if c["dec"].done():
                sol = c["dec"].solve()
                zz = np.concatenate([int_to_bits(x, pb) for x in sol])
                got = dem_decrypt(c["eh"], np.packbits(zz[:8 * (PAYLOAD_BYTES + TAG_BYTES)]).tobytes())
                if got is not None:
                    delivered, correct = True, got == payload
                    break
                cands.remove(c)
            elif c["n"] >= T2:
                cands.remove(c)
        if delivered:
            break
        ch = extract_plain(so, N, beta)
        L.append(ch if ch is not None else 0)
        if len(L) >= F1:
            zz = np.concatenate([int_to_bits(x, beta) for x in L[-F1:]])[:r]
            ok, eh = key.decode_ct(zz)
            if ok and int(eh.sum()) == key.t:
                cands.append(dict(key=session_key(eh), eh=eh, dec=FountainDecoder(F2), n=0))
    return dict(Kmin=Kmin, nuN=nuN, windows=windows, eligible=eligible, cycles=cycles,
                delivered=delivered, correct=bool(correct), F1=F1, F2=F2, T2=T2, beta=beta)


def theory_eligible(F1, F2, T2, nuN):
    """Expected eligible windows (approx.): a cycle survives iff its F1 phase-1 windows have no stray
    edit (prob. P1=exp(-nuN*F1)); phase-2 frames survive with exp(-nuN) each (fountain, +1.6 extra)."""
    P1 = math.exp(-nuN * F1)
    p = math.exp(-nuN)
    need2 = (F2 + 1.6) / p
    return (1 / P1 - 1) * (F1 + T2) + F1 + need2


if __name__ == "__main__":
    t0 = time.time()
    jobs = []
    MSG = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    for Kmin in [50, 70, 105]:
        for nuN in [0.0, 0.01, 0.02, 0.05, 0.1]:
            for i in range(MSG):
                jobs.append((Kmin, nuN, hash((Kmin, nuN, i)) & 0xFFFFFFF, 6000))
    with Pool(2) as p:
        res = p.map(one_message, jobs, chunksize=4)
    agg = {}
    for r_ in res:
        agg.setdefault(f"Kmin={r_['Kmin']},nuN={r_['nuN']}", []).append(r_)
    out = {}
    nb_p = KAPPA / (KAPPA + MU)
    for k, v in agg.items():
        d = [x for x in v if x["delivered"]]
        w = np.array([x["windows"] for x in d])
        el = np.array([x["eligible"] for x in d])
        Kmin = v[0]["Kmin"]; nuN = v[0]["nuN"]
        pk = 1 - stats.nbinom.cdf(Kmin - 1, KAPPA, nb_p)
        out[k] = dict(n_msgs=len(v), delivered=len(d), correct=int(sum(x["correct"] for x in v)),
                      windows_median=float(np.median(w)) if len(w) else None,
                      windows_p95=float(np.quantile(w, .95)) if len(w) else None,
                      eligible_mean=float(el.mean()) if len(el) else None,
                      cycles_mean=float(np.mean([x["cycles"] for x in d])) if d else None,
                      F1=v[0]["F1"], F2=v[0]["F2"], T2=v[0]["T2"], beta=v[0]["beta"], P_K_ge_Kmin=float(pk),
                      eligible_theory=theory_eligible(v[0]["F1"], v[0]["F2"], v[0]["T2"], nuN),
                      windows_theory=theory_eligible(v[0]["F1"], v[0]["F2"], v[0]["T2"], nuN) / pk)
    json.dump(out, open("/home/claude/pqhide_rev/results/simC.json", "w"), indent=1)
    print("done", time.time() - t0)
