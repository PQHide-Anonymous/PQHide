#!/usr/bin/env python3
"""Analyse d'une simulation (simulate_on_drive.py) lue via l'API Activity : un detecteur sait-il separer 'baseline' et 'scheme' ?
Entrees : sim_trace.csv (collect_activity.py collect), sim_manifest.csv. Les evenements sont rattaches aux fenetres par leur HEURE (horloge serveur Google).
Detecteurs (un par propriete) : AUC par caracteristique, plus une combinaison lineaire (LDA) avec validation croisee 5 plis ; IC bootstrap 95 %.
Avantage = 2*(exactitude equilibree au meilleur seuil) - 1  (borne inferieure de la distance en variation, estimee sur ces fenetres).
Resultats : SIMULATION sur API reelle, PAS une mesure sur activite d'utilisateurs reels."""
import argparse, csv, datetime as dt, json, re
import numpy as np

def P(s): return dt.datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00")))

def auc(neg, pos):
    neg, pos = np.asarray(neg, float), np.asarray(pos, float)
    if len(neg) == 0 or len(pos) == 0: return float("nan")
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))

def best_adv(neg, pos):
    th = np.unique(np.concatenate([neg, pos])); best = 0.0
    for t in th:
        for sgn in (1, -1):
            tpr = np.mean(sgn * np.asarray(pos) >= sgn * t); tnr = np.mean(sgn * np.asarray(neg) < sgn * t); best = max(best, tpr + tnr - 1)
    return float(best)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("trace"); ap.add_argument("manifest"); ap.add_argument("--margin", type=float, default=15.0, help="s after window end still attributed to it")
    ap.add_argument("--seed", type=int, default=3); ap.add_argument("--out", default="sim_report"); a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    ev = [(r["file_hash"], P(r["time_utc"])) for r in csv.DictReader(open(a.trace))]; M = list(csv.DictReader(open(a.manifest)))
    win = []
    for m in M:
        s, e = P(m["start_utc"]), P(m["end_utc"]) + dt.timedelta(seconds=a.margin); win.append((m["class"], [f for f, t in ev if s - dt.timedelta(seconds=1) <= t <= e]))
    base_sets = [set(f) for c, f in win if c == "baseline"]
    # heterogeneity reference: file edit frequency over the first half of baseline windows ("training")
    train = [w for w in win if w[0] == "baseline"][: max(1, len(base_sets) // 2)]; freq = {}
    for _, f in train:
        for x in set(f): freq[x] = freq.get(x, 0) + 1
    hot = {x for x, _ in sorted(freq.items(), key=lambda kv: -kv[1])[: max(1, len(freq) // 5)]}
    train_ids = {id(w) for w in train}            # windows used to define the hot set are NOT evaluated (avoids leakage)
    feats, labels, prev = [], [], set()
    for w in win:
        c, f = w; sset = set(f); K = len(sset)
        if K == 0: prev = set(); continue
        if id(w) in train_ids: prev = sset; continue
        rep = len(f) / K; hotfrac = len(sset & hot) / K; jac = len(sset & prev) / max(1, len(sset | prev)); prev = sset
        feats.append([K, rep, hotfrac, jac]); labels.append(c == "scheme")
    X, y = np.array(feats, float), np.array(labels); names = ["distinct_files", "edits_per_file", "hot_file_fraction", "jaccard_with_previous"]
    neg, pos = X[~y], X[y]; out = {"windows_used": int(len(y)), "baseline": int((~y).sum()), "scheme": int(y.sum()), "label": "SIMULATED behaviour on a real cloud API; not real user activity", "features": {}}
    for j, n in enumerate(names):
        A = auc(neg[:, j], pos[:, j]); bs = [auc(rng.choice(neg[:, j], len(neg)), rng.choice(pos[:, j], len(pos))) for _ in range(400)]
        out["features"][n] = dict(auc=A, auc_ci95=[float(np.nanquantile(bs, .025)), float(np.nanquantile(bs, .975))], advantage_best_threshold=best_adv(neg[:, j], pos[:, j]), mean_baseline=float(neg[:, j].mean()), mean_scheme=float(pos[:, j].mean()))
    idx = rng.permutation(len(y)); folds = np.array_split(idx, 5); sc = np.zeros(len(y))
    for k in range(5):
        te = folds[k]; tr = np.concatenate([folds[i] for i in range(5) if i != k]); mu0, mu1 = X[tr][~y[tr]].mean(0), X[tr][y[tr]].mean(0)
        S = np.cov(X[tr].T) + 1e-6 * np.eye(X.shape[1]); w = np.linalg.solve(S, mu1 - mu0); sc[te] = X[te] @ w
    out["lda_cv"] = dict(auc=auc(sc[~y], sc[y]), advantage_best_threshold=best_adv(sc[~y], sc[y]))
    json.dump(out, open(a.out + ".json", "w"), indent=1)
    md = [f"# Simulation report (SIMULATED behaviour on a real cloud API)\n", f"Windows used: {out['windows_used']} (baseline {out['baseline']}, scheme {out['scheme']})\n", "| feature | AUC [95% CI] | advantage | mean baseline | mean scheme |", "|---|---|---|---|---|"]
    for n, d in out["features"].items(): md.append(f"| {n} | {d['auc']:.3f} [{d['auc_ci95'][0]:.3f}, {d['auc_ci95'][1]:.3f}] | {d['advantage_best_threshold']:.3f} | {d['mean_baseline']:.2f} | {d['mean_scheme']:.2f} |")
    md.append(f"\nLDA (5-fold CV): AUC {out['lda_cv']['auc']:.3f}, advantage {out['lda_cv']['advantage_best_threshold']:.3f}\n"); open(a.out + ".md", "w").write("\n".join(md)); print("\n".join(md))

if __name__ == "__main__": main()
