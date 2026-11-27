"""Sim I (review point 5, timing and operation order): extends the synthetic activity model with
 - edit TIMESTAMPS inside a 24 h window: sessions starting at diurnal times, short intra-session gaps (bursty);
 - operation ORDER: legitimate edits visit files in an order unrelated to the file index.
Covert sender variants:
   timing  T1 'rate-limited'  : memoryless stream (mean gap 30 s) starting at a uniform time  (what v1 implicitly did)
           T2 'marginal'      : each edit time drawn i.i.d. from the legitimate diurnal marginal, no session structure
           T3 'session-copy'  : same session process as legitimate activity (the construction's requirement)
   order   O1 'sorted'        : files edited in increasing index (the natural output of rank unranking)
           O2 'shuffled'      : uniformly random order (required)
Detector: gradient boosting on per-window features (gap statistics, night fraction, Spearman(time rank, file index)),
          evidence accumulated over T=1 and T=7 windows (sum of log-odds). TPR at FPR 1e-2 and 1e-3, held-out data.
Output: results/simI.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import json, numpy as np
from scipy import stats
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
rng = np.random.default_rng(424242)
DAY = 86400.0; N = 1 << 17; MU, KAPPA = 105.0, 8.0

def counts(n): return np.maximum(rng.poisson(MU * rng.gamma(KAPPA, 1 / KAPPA, size=n)), 20)
def diurnal(n):
    comp = rng.choice(3, size=n, p=[0.45, 0.40, 0.15])
    t = np.where(comp == 0, rng.normal(10 * 3600, 1.5 * 3600, n), np.where(comp == 1, rng.normal(15 * 3600, 2 * 3600, n), rng.uniform(0, DAY, n)))
    return np.mod(t, DAY)

def times_legit(K):                       # sessions
    m = max(1, int(round(K / 8)))
    starts = diurnal(m); sess = rng.integers(0, m, K)
    return np.mod(starts[sess] + rng.exponential(180.0, K), DAY)
def times_T1(K): return np.mod(rng.uniform(0, DAY) + np.cumsum(rng.exponential(30.0, K)), DAY)
def times_T2(K): return diurnal(K)
TIMES = {"legit": times_legit, "T1": times_T1, "T2": times_T2, "T3": times_legit}

def window(kind, order):
    K = int(counts(1)[0])
    t = TIMES[kind](K)
    ids = rng.choice(N, K, replace=False)
    idx = np.argsort(t, kind="stable")           # chronological order of edits
    t = t[idx]
    if order == "sorted": ids = np.sort(ids)     # i-th chronological edit has i-th smallest index
    return t, ids

def feats(t, ids):
    g = np.diff(t) + 1e-3
    night = np.mean((t < 6 * 3600))
    rho = stats.spearmanr(np.arange(len(ids)), ids)[0]
    return [len(t), np.mean(np.log(g)), np.std(np.log(g)), np.max(g), np.mean(g < 300), night, np.mean(np.abs(t - 12.5 * 3600)) , abs(rho)]

def make(kind, order, n):
    return np.array([feats(*window(kind, order)) for _ in range(n)])

def tpr(neg, pos, f): return float((pos > np.quantile(neg, 1 - f)).mean())
res = {}
NTR = 4000
Xl = make("legit", "shuffled", 2 * NTR + 7 * 2000)
for tk in ["T1", "T2", "T3"]:
    for ok in ["sorted", "shuffled"]:
        Xs = make(tk, ok, 2 * NTR + 7 * 2000)
        Xtr = np.vstack([Xl[:NTR], Xs[:NTR]]); ytr = np.r_[np.zeros(NTR), np.ones(NTR)]
        clf = GradientBoostingClassifier(n_estimators=120, max_depth=3, random_state=0).fit(Xtr, ytr)
        # held-out: next NTR windows for T=1, and 7*2000 for T=7 (log-odds summed)
        def logit(X):
            p = np.clip(clf.predict_proba(X)[:, 1], 1e-6, 1 - 1e-6); return np.log(p / (1 - p))
        nl, ps = logit(Xl[NTR:2 * NTR]), logit(Xs[NTR:2 * NTR])
        nl7 = logit(Xl[2 * NTR:]).reshape(2000, 7).sum(1); ps7 = logit(Xs[2 * NTR:]).reshape(2000, 7).sum(1)
        yy = np.r_[np.zeros(NTR), np.ones(NTR)]
        res[f"{tk}/{ok}"] = dict(auc_T1=float(roc_auc_score(yy, np.r_[nl, ps])), tpr1e2_T1=tpr(nl, ps, 1e-2), tpr1e3_T1=tpr(nl, ps, 1e-3),
                                 auc_T7=float(roc_auc_score(np.r_[np.zeros(2000), np.ones(2000)], np.r_[nl7, ps7])),
                                 tpr1e2_T7=tpr(nl7, ps7, 1e-2), tpr1e3_T7=tpr(nl7, ps7, 1e-3))
        print(tk, ok, {k: round(v, 3) for k, v in res[f"{tk}/{ok}"].items()}, flush=True)
json.dump(res, open(ROOT + "/results/simI.json", "w"), indent=1)
