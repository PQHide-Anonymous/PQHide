"""Sim B: steganalysis of PQHide embeddings against a *synthetic* model of legitimate cloud activity.

IMPORTANT: no real user-activity dataset is available offline; the legitimate-activity model
below is an explicit, parametric generative model.  All detectors are given an *oracle* view of
the legitimate model (strongest realistic adversary), so reported detection rates are
conservative with respect to that model, but they say nothing about real-world mismatch.

Worlds
  legit : K_w ~ NB(mean mu, dispersion kappa) edits in a pool of N folders; folders drawn with
          rates rho_f = exp(sigma z_f) (heterogeneity) and, with prob gamma, as adjacent bursts.
  v1    : original PQHide - y uniform in F_2^n, a folder is modified iff y_i = 1.
  v2    : rank-coded embedding: K_w from the *same* count law, subset uniform among K-subsets.
  v2x   : v2 but with counts inflated by a factor rho (throughput boost).
Output: results/simB.json
"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import json, sys, time
import numpy as np
from scipy import stats

N = 1 << 17
MU = 105.0
KAPPA = 8.0   # gamma-mixing shape of the daily activity multiplier (overdispersion)
rng = np.random.default_rng(20261122)


def sample_counts(n, mu=MU, kappa=KAPPA, scale=1.0):
    g = rng.gamma(kappa, 1.0 / kappa, size=n)
    return rng.poisson(scale * mu * g)


def make_rates(sigma):
    z = rng.standard_normal(N)
    rho = np.exp(sigma * z)
    return rho / rho.sum()


def legit_windows(K, p_cdf, gamma):
    """returns list of index arrays. bursts: with prob gamma an event expands to an adjacent run."""
    out = []
    tot = int(K.sum())
    u = rng.random(tot)
    idx = np.searchsorted(p_cdf, u).clip(0, N - 1)
    burst = rng.random(tot) < gamma if gamma > 0 else np.zeros(tot, bool)
    pos = 0
    for k in K:
        a = idx[pos:pos + k]
        b = burst[pos:pos + k]
        if b.any():
            a = np.unique(np.concatenate([a, (a[b] + 1) % N]))
        else:
            a = np.unique(a)
        out.append(a)
        pos += k
    return out


def stego_windows(K):
    return [np.unique(rng.integers(0, N, size=k)) if k < N // 8 else rng.choice(N, k, replace=False) for k in K]


def tpr_at_fpr(neg, pos, fprs):
    neg = np.sort(neg)
    res = {}
    for f in fprs:
        thr = np.quantile(neg, 1 - f)
        res[str(f)] = float((pos > thr).mean())
    return res


def boot_ci(neg, pos, f, B=300):
    vals = []
    for _ in range(B):
        n_ = rng.choice(neg, len(neg)); p_ = rng.choice(pos, len(pos))
        thr = np.quantile(n_, 1 - f)
        vals.append((p_ > thr).mean())
    return [float(np.quantile(vals, .025)), float(np.quantile(vals, .975))]


def auc(neg, pos):
    r = stats.rankdata(np.concatenate([neg, pos]))
    n1, n2 = len(neg), len(pos)
    return float((r[n1:].sum() - n2 * (n2 + 1) / 2) / (n1 * n2))


results = {}

# ---------- B1: v1 (dense uniform y) vs legit: the count alone separates them ----------
Kl = sample_counts(20000)
Kv1 = rng.binomial(N, 0.5, size=20000)
results["B1_v1_dense"] = dict(legit_mean=float(Kl.mean()), legit_std=float(Kl.std()),
                              v1_mean=float(Kv1.mean()), v1_std=float(Kv1.std()),
                              auc=auc(Kl.astype(float), Kv1.astype(float)),
                              min_v1=int(Kv1.min()), max_legit=int(Kl.max()))

# ---------- B2: count inflation (throughput boost) -- oracle NB likelihood-ratio detector -------
def nb_llr(K, rho, T):
    # K: (trials, T) counts. Gamma-Poisson (NB) with mean mu vs mean rho*mu, same kappa
    def lp(k, m):
        n = KAPPA; p = n / (n + m)
        return stats.nbinom.logpmf(k, n, p)
    return (lp(K, rho * MU) - lp(K, MU)).sum(axis=1)

B2 = {}
for rho in [1.0, 1.25, 1.5, 2.0, 4.0, 8.0]:
    row = {}
    for T in [1, 7, 30]:
        trials = 20000
        Kneg = sample_counts(trials * T).reshape(trials, T)
        Kpos = sample_counts(trials * T, scale=rho).reshape(trials, T)
        neg, pos = nb_llr(Kneg, rho, T), nb_llr(Kpos, rho, T)
        row[str(T)] = dict(auc=auc(neg, pos),
                           tpr=tpr_at_fpr(neg, pos, [1e-2, 1e-3]),
                           ci_1e2=boot_ci(neg, pos, 1e-2, 100))
    B2[str(rho)] = row
results["B2_count_inflation"] = B2

# ---------- B3: folder-selection leakage, oracle LLR, vs pool heterogeneity sigma -------------
def selection_stat(wins, logrho):
    return np.array([-logrho[w].sum() for w in wins])

B3 = {}
trialsB3 = 6000
Tmax = 30
for sigma in [0.0, 0.1, 0.25, 0.5, 1.0]:
    p = make_rates(sigma)
    cdf = np.cumsum(p); cdf[-1] = 1.0
    logrho = np.log(p * N)  # per-folder relative log-rate
    row = {}
    # per-window statistic for legit and stego (same count sequence law)
    Kn = sample_counts(trialsB3 * Tmax)
    Kp = sample_counts(trialsB3 * Tmax)
    wn = legit_windows(Kn, cdf, 0.0)
    wp = stego_windows(Kp)
    sn = selection_stat(wn, logrho).reshape(trialsB3, Tmax)
    sp = selection_stat(wp, logrho).reshape(trialsB3, Tmax)
    for T in [1, 7, 30]:
        neg, pos = sn[:, :T].sum(1), sp[:, :T].sum(1)
        row[str(T)] = dict(auc=auc(neg, pos), tpr=tpr_at_fpr(neg, pos, [1e-2, 1e-3]),
                           ci_1e2=boot_ci(neg, pos, 1e-2, 100))
    B3[str(sigma)] = row
results["B3_selection_vs_sigma"] = B3

# ---------- B4: spatial clustering (adjacent bursts) + GBM detector on summary features --------
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

def feats(wins, logrho):
    F = []
    for w in wins:
        w = np.sort(w)
        gaps = np.diff(w)
        F.append([len(w), (gaps == 1).sum(), (gaps <= 3).sum(), np.median(gaps) if len(gaps) else 0,
                  logrho[w].mean() if len(w) else 0, logrho[w].std() if len(w) > 1 else 0])
    return np.array(F)

B4 = {}
for gamma in [0.0, 0.02, 0.1, 0.3]:
    p = make_rates(0.25)
    cdf = np.cumsum(p); cdf[-1] = 1.0
    logrho = np.log(p * N)
    ntr, nte = 6000, 6000
    Xl = feats(legit_windows(sample_counts(ntr + nte), cdf, gamma), logrho)
    Xs = feats(stego_windows(sample_counts(ntr + nte)), logrho)
    Xtr = np.vstack([Xl[:ntr], Xs[:ntr]]); ytr = np.r_[np.zeros(ntr), np.ones(ntr)]
    Xte = np.vstack([Xl[ntr:], Xs[ntr:]]); yte = np.r_[np.zeros(nte), np.ones(nte)]
    clf = GradientBoostingClassifier(n_estimators=150, max_depth=3, random_state=0).fit(Xtr, ytr)
    sc = clf.predict_proba(Xte)[:, 1]
    neg, pos = sc[yte == 0], sc[yte == 1]
    B4[str(gamma)] = dict(auc=float(roc_auc_score(yte, sc)), tpr=tpr_at_fpr(neg, pos, [1e-2, 1e-3]),
                          ci_1e2=boot_ci(neg, pos, 1e-2, 100))
results["B4_clustering_gbm"] = B4

# ---------- B5: null check: homogeneous, unclustered pool, count law identical (T=1) -----------
Kn = sample_counts(40000); Kp = sample_counts(40000)
wn = legit_windows(Kn, np.linspace(1 / N, 1, N), 0.0)
wp = stego_windows(Kp)
Fn, Fp = feats(wn, np.zeros(N)), feats(wp, np.zeros(N))
X = np.vstack([Fn, Fp]); y = np.r_[np.zeros(len(Fn)), np.ones(len(Fp))]
idx = rng.permutation(len(y)); tr, te = idx[:40000], idx[40000:]
clf = GradientBoostingClassifier(n_estimators=150, max_depth=3, random_state=0).fit(X[tr], y[tr])
sc = clf.predict_proba(X[te])[:, 1]
results["B5_null_check_auc"] = float(roc_auc_score(y[te], sc))
json.dump(results, open(ROOT + "/results/simB.json", "w"), indent=1)
print("done")
