"""QC-MDPC code (BIKE-like quasi-cyclic structure) with a BGF-style bit-flipping decoder.

Pure numpy; circulant products are done by FFT.  This is a *research harness* used to
measure decoding-failure rates and local computation times, not a constant-time
implementation.  Parameters follow BIKE Round-4 (r, w, t) for the three NIST categories.
"""
import numpy as np

# (r, w, t, threshold slope, threshold intercept, threshold floor)  -- BIKE Round-4 spec
PARAMS = {
    "L1": dict(r=12323, w=142, t=134, a=0.0069722, b=13.530, tmin=36),
    "L3": dict(r=24659, w=206, t=199, a=0.005265, b=15.2588, tmin=52),
    "L5": dict(r=40973, w=274, t=264, a=0.00402312, b=17.8785, tmin=69),
}


def _fft_len(r):
    L = 1
    while L < 2 * r:
        L <<= 1
    return L


class Ring:
    """F2[x]/(x^r - 1) arithmetic on uint8 bit arrays (index i = coefficient of x^i)."""

    def __init__(self, r):
        self.r = r
        self.L = _fft_len(r)

    def fft(self, a):
        return np.fft.rfft(a.astype(np.float64), self.L)

    def conv_from_fft(self, fa, fb):
        lin = np.fft.irfft(fa * fb, self.L)
        lin = np.rint(lin).astype(np.int64)
        r = self.r
        return lin[:r] + lin[r:2 * r]

    def mul(self, a, b):
        return (self.conv_from_fft(self.fft(a), self.fft(b)) & 1).astype(np.uint8)

    def to_int(self, a):
        return int.from_bytes(np.packbits(a, bitorder="little").tobytes(), "little")

    def from_int(self, x):
        nb = (self.r + 7) // 8 + 1
        b = np.unpackbits(np.frombuffer(x.to_bytes(nb, "little"), dtype=np.uint8), bitorder="little")
        out = b[: self.r].copy()
        if b.shape[0] > self.r:  # fold x^r = 1
            ex = b[self.r:]
            out[: ex.shape[0]] ^= ex[: self.r]
        return out

    def inv(self, a):
        """Inverse in F2[x]/(x^r+1) via extended Euclid on Python ints."""
        M = (1 << self.r) | 1
        h = self.to_int(a)
        r0, r1, s0, s1 = M, h, 0, 1
        dg = lambda z: z.bit_length() - 1
        while dg(r1) > 0:
            if dg(r0) < dg(r1):
                r0, r1, s0, s1 = r1, r0, s1, s0
            d = dg(r0) - dg(r1)
            r0 ^= r1 << d
            s0 ^= s1 << d
        if r1 != 1:
            raise ValueError("not invertible")
        # reduce s1 mod x^r + 1
        out = 0
        mask = (1 << self.r) - 1
        while s1:
            out ^= s1 & mask
            s1 >>= self.r
        return self.from_int(out)


def rand_weight_vec(rng, r, wt):
    v = np.zeros(r, dtype=np.uint8)
    v[rng.choice(r, wt, replace=False)] = 1
    return v


class QCMDPC:
    def __init__(self, level="L1", rng=None, params=None):
        p = dict(PARAMS[level]) if params is None else dict(params)
        self.p = p
        self.r, self.w, self.t = p["r"], p["w"], p["t"]
        self.d = self.w // 2
        self.ring = Ring(self.r)
        rng = rng or np.random.default_rng()
        R = self.ring
        while True:  # h1 must be invertible: odd weight is necessary; test by inversion
            self.h0 = rand_weight_vec(rng, self.r, self.d)
            self.h1 = rand_weight_vec(rng, self.r, self.d)
            try:
                hinv = R.inv(self.h1)
                break
            except ValueError:
                continue
        # public key: q = h0 * h1^{-1}; codeword (m, m*q) satisfies m*h0 + (m*q)*h1 = 0
        self.q = R.mul(self.h0, hinv)
        # precompute for decoding: reversed h for correlation
        rev = lambda a: np.roll(a[::-1], 1)  # h_rev[k] = h[(-k) mod r]
        self.F_h0, self.F_h1 = R.fft(self.h0), R.fft(self.h1)
        self.F_h0r, self.F_h1r = R.fft(rev(self.h0)), R.fft(rev(self.h1))
        self.Fq = R.fft(self.q)

    # ---------------- encoding (public-key side) ----------------
    def encode(self, m, e):
        """y = (m, m q) + e ;  m: r-bit message, e: 2r-bit error vector."""
        R = self.ring
        c1 = (R.conv_from_fft(R.fft(m), self.Fq) & 1).astype(np.uint8)
        y = np.concatenate([m, c1]) ^ e
        return y

    def sample_error(self, rng, wt):
        e = np.zeros(2 * self.r, dtype=np.uint8)
        e[rng.choice(2 * self.r, wt, replace=False)] = 1
        return e

    # ---------------- decoding (secret-key side) ----------------
    def syndrome(self, y):
        R = self.ring
        r = self.r
        s = R.conv_from_fft(R.fft(y[:r]), self.F_h0) + R.conv_from_fft(R.fft(y[r:]), self.F_h1)
        return (s & 1).astype(np.uint8)

    def _upc(self, s):
        R = self.ring
        Fs = R.fft(s)
        return R.conv_from_fft(Fs, self.F_h0r), R.conv_from_fft(Fs, self.F_h1r)

    def _apply(self, s, f0, f1):
        R = self.ring
        add = 0
        if f0.any():
            add = add + R.conv_from_fft(R.fft(f0), self.F_h0)
        if f1.any():
            add = add + R.conv_from_fft(R.fft(f1), self.F_h1)
        return s ^ (np.asarray(add) & 1).astype(np.uint8) if not np.isscalar(add) else s

    # ---------------- Niederreiter / BIKE-style (syndrome) interface ----------------
    def encrypt_syndrome(self, e):
        """public side: s' = e0*q + e1  (r bits).  Equals (e0*h0 + e1*h1) * h1^{-1}."""
        R, r = self.ring, self.r
        s = (R.conv_from_fft(R.fft(e[:r]), self.Fq) & 1).astype(np.uint8) ^ e[r:]
        return s

    def decode_ct(self, sp, **kw):
        """secret side: sH = s' * h1 = e0 h0 + e1 h1, then bit-flipping."""
        R = self.ring
        sH = (R.conv_from_fft(R.fft(sp), self.F_h1) & 1).astype(np.uint8)
        return self.decode_syndrome(sH, **kw)

    def decode(self, y, nb_iter=5, tau=3):
        """BGF-style decoder on a word y. Returns (success, e_hat)."""
        return self.decode_syndrome(self.syndrome(y), nb_iter, tau)

    def decode_syndrome(self, s, nb_iter=5, tau=3):
        r, p = self.r, self.p
        e0 = np.zeros(r, dtype=np.uint8)
        e1 = np.zeros(r, dtype=np.uint8)
        thr_masked = (self.d + 1) // 2
        for it in range(nb_iter):
            if not s.any():
                break
            T = max(int(p["a"] * int(s.sum()) + p["b"]), p["tmin"])
            u0, u1 = self._upc(s)
            b0, b1 = (u0 >= T).astype(np.uint8), (u1 >= T).astype(np.uint8)
            g0 = ((u0 >= T - tau) & (u0 < T)).astype(np.uint8)
            g1 = ((u1 >= T - tau) & (u1 < T)).astype(np.uint8)
            e0 ^= b0
            e1 ^= b1
            s = self._apply(s, b0, b1)
            if it == 0:
                for m0, m1 in ((b0, b1), (g0, g1)):
                    u0, u1 = self._upc(s)
                    f0 = ((u0 >= thr_masked) & (m0 == 1)).astype(np.uint8)
                    f1 = ((u1 >= thr_masked) & (m1 == 1)).astype(np.uint8)
                    e0 ^= f0
                    e1 ^= f1
                    s = self._apply(s, f0, f1)
        ok = not s.any()
        return ok, np.concatenate([e0, e1])
