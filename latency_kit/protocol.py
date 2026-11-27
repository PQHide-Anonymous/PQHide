"""PQHide-v2 protocol pieces: constant-weight (colex) rank coding, masked CRC frames,
random-linear fountain code over GF(2).  All real code, used by simC and the unit tests."""
import hashlib, math, zlib
import numpy as np


# ------------------------- combinatorial number system -------------------------
def rank_subset(S):
    """S sorted ascending, 0-based folder indices -> integer in [0, C(N,K))."""
    return sum(math.comb(s, i + 1) for i, s in enumerate(S))


def unrank_subset(rank, N, K):
    S = []
    hi = N - 1
    for i in range(K, 0, -1):
        lo = i - 1
        # largest s in [lo, hi] with C(s, i) <= rank
        a, b = lo, hi
        while a < b:
            mid = (a + b + 1) // 2
            if math.comb(mid, i) <= rank:
                a = mid
            else:
                b = mid - 1
        S.append(a)
        rank -= math.comb(a, i)
        hi = a - 1
    return sorted(S)


def log2_comb(N, K):
    return (math.lgamma(N + 1) - math.lgamma(K + 1) - math.lgamma(N - K + 1)) / math.log(2)


# ------------------------------ frames ------------------------------
SEED_BITS, CRC_BITS, MARGIN_BITS = 16, 32, 64


def frame_geometry(N, Kmin):
    beta = int(log2_comb(N, Kmin)) - MARGIN_BITS      # bits hidden in the low part of the rank
    return beta, beta - SEED_BITS - CRC_BITS          # (chunk bits, payload bits per frame)


def _mask(key, high, nbits):
    """Mask M(K, u): SHAKE-256 keyed by the session key K (secret).  An observer without K cannot
    evaluate it, so seeds, CRCs and the linear structure of phase-2 frames stay hidden."""
    nbytes = (nbits + 7) // 8
    d = hashlib.shake_256(b"PQHide-mask" + key + high.to_bytes((high.bit_length() + 7) // 8 or 1, "big")).digest(nbytes)
    return int.from_bytes(d, "big") & ((1 << nbits) - 1)


def build_chunk(seed, payload_int, pbits):
    body = (seed << pbits) | payload_int
    crc = zlib.crc32(body.to_bytes((SEED_BITS + pbits + 7) // 8, "big")) & 0xFFFFFFFF
    return (body << CRC_BITS) | crc


def parse_chunk(chunk, pbits):
    crc = chunk & 0xFFFFFFFF
    body = chunk >> CRC_BITS
    if body.bit_length() > SEED_BITS + pbits:
        return None
    if zlib.crc32(body.to_bytes((SEED_BITS + pbits + 7) // 8, "big")) & 0xFFFFFFFF != crc:
        return None
    return body >> pbits, body & ((1 << pbits) - 1)


def _high(rng, total, beta):
    nhigh = total >> beta
    assert nhigh >= (1 << MARGIN_BITS), "not enough capacity for K"
    return int.from_bytes(rng.bytes(((nhigh.bit_length() + 7) // 8) + 8), "big") % nhigh


# ---- phase 1: the KEM ciphertext chunk, sent in the clear (it is uniform under QC-SD) ----
def embed_plain(rng, N, K, beta, chunk):
    """K-subset whose colex rank is  u*2^beta + chunk  (u uniform, chunk = beta uniform bits).
    No seed, no CRC, no mask: nothing here is checkable without the secret key."""
    r = (_high(rng, math.comb(N, K), beta) << beta) | chunk
    return unrank_subset(r, N, K)


def extract_plain(S, N, beta):
    K = len(S)
    if K == 0 or math.comb(N, K) >> beta < (1 << MARGIN_BITS):
        return None
    return rank_subset(sorted(S)) & ((1 << beta) - 1)


# ---- phase 2: DEM frames (CRC + seed), masked with a mask keyed by the session key K ----
def embed_keyed(rng, N, K, beta, key, seed, payload_int, pbits):
    high = _high(rng, math.comb(N, K), beta)
    chunk = build_chunk(seed, payload_int, pbits)
    r = (high << beta) | (chunk ^ _mask(key, high, beta))
    return unrank_subset(r, N, K)


def extract_keyed(S, N, beta, pbits, key):
    K = len(S)
    if K == 0 or math.comb(N, K) >> beta < (1 << MARGIN_BITS):
        return None
    r = rank_subset(sorted(S))
    high, low = r >> beta, r & ((1 << beta) - 1)
    return parse_chunk(low ^ _mask(key, high, beta), pbits)


# --------------------------- GF(2) fountain code ---------------------------
def coeffs(seed, F):
    g = np.random.default_rng(seed)
    c = g.integers(0, 2, F)
    if not c.any():
        c[seed % F] = 1
    return int("".join(map(str, c.tolist())), 2)   # bit i (from MSB) <-> source chunk i


def fountain_encode(chunks, seed):
    F = len(chunks)
    cm = coeffs(seed, F)
    out = 0
    for i in range(F):
        if (cm >> (F - 1 - i)) & 1:
            out ^= chunks[i]
    return out


class FountainDecoder:
    def __init__(self, F):
        self.F = F
        self.rows = {}      # pivot bit position -> (coeff mask, payload)

    def add(self, seed, payload):
        cm = coeffs(seed, self.F)
        while cm:
            piv = cm.bit_length() - 1
            if piv in self.rows:
                c2, p2 = self.rows[piv]
                cm ^= c2
                payload ^= p2
            else:
                self.rows[piv] = (cm, payload)
                return
        # linearly dependent -> ignored

    def done(self):
        return len(self.rows) == self.F

    def solve(self):
        F = self.F
        sol = [None] * F
        for piv in range(F):   # back-substitute from lowest pivot
            cm, p = self.rows[piv]
            for j in range(piv):
                if (cm >> j) & 1:
                    p ^= sol_by_bit[j]
            if piv == 0:
                sol_by_bit = {}
            sol_by_bit[piv] = p
        # bit position b corresponds to chunk index F-1-b
        return [sol_by_bit[F - 1 - i] for i in range(F)]
