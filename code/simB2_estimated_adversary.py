"""Sim B2: adversary that must *estimate* per-folder legitimate rates from H past windows
(empirical-Bayes / Gamma-Poisson posterior mean), then runs the LLR test over T windows.
Output: results/simB2.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import json
import numpy as np
from scipy import stats

N = 1 << 17
MU, KAPPA = 105.0, 8.0
rng = np.random.default_rng(7)


def counts(n):
    return rng.poisson(MU * rng.gamma(KAPPA, 1 / KAPPA, size=n))


def windows(K, cdf):
    tot = int(K.sum())
    idx = np.searchsorted(cdf, rng.random(tot)).clip(0, N - 1)
    out, pos = [], 0
    for k in K:
        out.append(np.unique(idx[pos:pos + k])); pos += k
    return out


def stego(K):
    return [np.unique(rng.integers(0, N, size=k)) for k in K]


def auc(neg, pos):
    r = stats.rankdata(np.concatenate([neg, pos])); n1, n2 = len(neg), len(pos)
    return float((r[n1:].sum() - n2 * (n2 + 1) / 2) / (n1 * n2))


def tpr(neg, pos, f):
    return float((pos > np.quantile(neg, 1 - f)).mean())


res = {}
trials, T = 3000, 30
for sigma in [0.25, 0.5, 1.0]:
    z = rng.standard_normal(N); rho = np.exp(sigma * z); p = rho / rho.sum()
    cdf = np.cumsum(p); cdf[-1] = 1
    alpha = 1.0 / (np.exp(sigma ** 2) - 1.0)         # Gamma prior shape matched to lognormal
    for H in [30, 365, 3650, 36500]:
        c = rng.poisson(H * MU * p)                    # per-folder historical counts
        lam0 = H * MU / N
        rhohat = (c + alpha) / (lam0 + alpha)          # posterior-mean relative rate
        lr = np.log(rhohat)
        neg = np.array([-lr[w].sum() for w in windows(counts(trials * T), cdf)]).reshape(trials, T).sum(1)
        pos = np.array([-lr[w].sum() for w in stego(counts(trials * T))]).reshape(trials, T).sum(1)
        res[f"sigma={sigma},H={H}"] = dict(auc=auc(neg, pos), tpr_1e2=tpr(neg, pos, 1e-2), tpr_1e3=tpr(neg, pos, 1e-3))
        print(sigma, H, res[f"sigma={sigma},H={H}"], flush=True)
json.dump(dict(T_windows=T, trials=trials, results=res), open(ROOT + "/results/simB2.json", "w"), indent=1)
