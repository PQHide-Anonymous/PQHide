#!/usr/bin/env python3
"""Measure the cover-model gap of PQHide on a REAL edit trace (anonymised CSV from the exporters).

Input : edits.csv  (file_hash, time_utc, by_me)
Output: real_report.json, real_report.md, tab_real.tex (LaTeX fragment for the paper)

What it measures (window = one local calendar day):
  1. descriptive statistics of the legitimate channel: edits per window K, overdispersion, per-file rate
     heterogeneity (Gini, effective number of files), co-editing (clustering), hour-of-day profile, burstiness;
  2. detectability: an observer who estimates per-file rates on the first part of the trace (train) tries to
     separate REAL held-out windows from COVERT windows (count taken from real windows, files drawn uniformly
     in the pool = the PQHide behaviour).  AUC and TPR at fixed FPR with bootstrap 95% CIs;
  3. capacity: bits the pool can carry per window, and the number of windows (days) needed to deliver a
     1 KiB message (20 643 bits), replaying the REAL sequence of counts.

Pools: 'all' = every file seen; 'band' = files whose edited-days count lies in the central band
(narrow range of rates, the design rule of the paper).  Observation is restricted to the pool.
Honest limits: a single account, a single observer model, windows are days; with few windows the TPR at
FPR 1e-3 cannot be estimated, so FPR 5% and 1% are reported.
"""
import argparse, csv, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import numpy as np


def lc(n, k):
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)) / math.log(2) if 0 <= k <= n else float("-inf")


def load(path, tz, only_me):
    z = ZoneInfo(tz); ev = []
    for r in csv.DictReader(open(path)):
        if only_me and r["by_me"] != "1":
            continue
        t = datetime.fromisoformat(r["time_utc"].replace("Z", "+00:00")).astimezone(z)
        ev.append((r["file_hash"], t))
    return ev


def windows(ev):
    days = defaultdict(lambda: defaultdict(list))
    for f, t in ev:
        days[t.date()][f].append(t)
    d0, d1 = min(days), max(days)
    allday = [d0.fromordinal(o) for o in range(d0.toordinal(), d1.toordinal() + 1)]
    return allday, days


def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum())) if x.sum() > 0 else 0.0


def nb_kappa(K):
    m, v = K.mean(), K.var(ddof=1)
    return float(m * m / (v - m)) if v > m else float("inf")


def make_pool(counts, kind, size):
    files = sorted(counts, key=lambda f: counts[f])
    if kind == "all":
        return set(files)
    lo, hi = np.quantile([counts[f] for f in files], [0.25, 0.75])      # central band
    band = [f for f in files if lo <= counts[f] <= hi]
    return set(band[:size] if size else band)


def kmin_auto(N):
    best, bk = 0.0, 1
    for k in range(1, min(N, 400)):
        b = math.floor(lc(N, k)) - 112
        if b > 0:
            # P(K>=k) is data dependent; return the smallest k with a usable frame, refined later
            return k
    return bk


def capacity_days(Kseq, N, Kmin, nz):
    beta = math.floor(lc(N, Kmin)) - 64
    b = beta - 48
    if b <= 0:
        return None, b
    F = math.ceil(nz / b); need = F + 2
    res = []
    for s in range(len(Kseq)):
        got = 0
        for j in range(s, len(Kseq)):
            if Kseq[j] >= Kmin:
                got += 1
                if got >= need:
                    res.append(j - s + 1); break
    return (res, b), b


def auc_pos_lower(neg, pos):
    # score = detector value, larger => 'covert'.  neg: real windows, pos: covert windows
    from scipy.stats import rankdata
    r = rankdata(np.r_[neg, pos]); n1, n2 = len(neg), len(pos)
    return float((r[n1:].sum() - n2 * (n2 + 1) / 2) / (n1 * n2))


def tpr_at(neg, pos, f):
    return float((pos > np.quantile(neg, 1 - f)).mean())


def boot(neg, pos, rng, B=400):
    a, t5, t1 = [], [], []
    for _ in range(B):
        n_ = rng.choice(neg, len(neg)); p_ = rng.choice(pos, len(pos))
        a.append(auc_pos_lower(n_, p_)); t5.append(tpr_at(n_, p_, .05)); t1.append(tpr_at(n_, p_, .01))
    q = lambda x: [float(np.quantile(x, .025)), float(np.quantile(x, .975))]
    return q(a), q(t5), q(t1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--tz", default="UTC")
    ap.add_argument("--all-actors", action="store_true", help="include edits by other users (default: only mine)")
    ap.add_argument("--train-frac", type=float, default=0.6)
    ap.add_argument("--band-size", type=int, default=0, help="max pool size for the band pool (0 = whole band)")
    ap.add_argument("--nbits", type=int, default=20643, help="bits to convey (1 KiB hybrid ciphertext at Level 1)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--since", default=None, help="YYYY-MM-DD: ignore earlier days")
    ap.add_argument("--exclude-bulk", type=int, default=0, help="drop days on which more than M distinct files were edited (bulk/automated operations)")
    ap.add_argument("--min-days", type=int, default=1, help="pool files must be edited on at least this many distinct days")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    ev = load(a.csv, a.tz, not a.all_actors)
    if not ev:
        sys.exit("no events after filtering")
    if a.since:
        from datetime import date
        d_ = date.fromisoformat(a.since); ev = [(f, t) for f, t in ev if t.date() >= d_]
        if not ev:
            sys.exit("no events after --since")
    days, byday = windows(ev)
    daily = sorted(((len(byday[d]), str(d)) for d in byday), reverse=True)
    top_days = daily[:10]
    n_bulk = 0
    if a.exclude_bulk:
        keep = [d for d in days if len(byday.get(d, {})) <= a.exclude_bulk]
        n_bulk = len(days) - len(keep); days = keep
        if len(days) < 30:
            sys.exit("fewer than 30 windows after bulk exclusion")
    T = len(days)
    per_file_days = defaultdict(int)
    for d in days:
        for f in byday.get(d, {}):
            per_file_days[f] += 1
    out = dict(top_days_files_edited=top_days, bulk_days_excluded=n_bulk, exclude_bulk_threshold=a.exclude_bulk, min_days=a.min_days, tz=a.tz, windows_total=T, first_day=str(days[0]), last_day=str(days[-1]),
               files_seen=len(per_file_days), events=len(ev), only_my_edits=not a.all_actors)
    ntr = int(T * a.train_frac)
    train_days, test_days = days[:ntr], days[ntr:]
    train_counts = defaultdict(int)
    for d in train_days:
        for f in byday.get(d, {}):
            train_counts[f] += 1
    out["pools"] = {}
    for kind in ["all", "band"]:
        pool = make_pool({f: c for f, c in per_file_days.items() if c >= a.min_days}, kind, a.band_size)
        N = len(pool)
        if N < 10:
            out["pools"][kind] = dict(N=N, note="pool too small after --min-days"); continue
        res = dict(N=N)
        # --- windows restricted to the pool
        Kseq = np.array([len([f for f in byday.get(d, {}) if f in pool]) for d in days])
        Ktr, Kte = Kseq[:ntr], Kseq[ntr:]
        res["K_mean"], res["K_sd"] = float(Kseq.mean()), float(Kseq.std(ddof=1))
        res["K_quantiles_50_90_99"] = [float(np.quantile(Kseq, q)) for q in (.5, .9, .99)]
        res["active_day_fraction"] = float((Kseq > 0).mean())
        res["overdispersion_kappa"] = nb_kappa(Kseq.astype(float))
        rates = np.array([per_file_days[f] / T for f in pool])
        res["rate_gini"] = gini(rates); res["effective_files"] = float(1.0 / np.sum((rates / rates.sum()) ** 2))
        # --- co-editing lift: same-day pairs vs independence
        pair, exp, nd = 0, 0.0, 0
        pf = {f: per_file_days[f] / T for f in pool}
        for d in days:
            S = [f for f in byday.get(d, {}) if f in pool]
            k = len(S); pair += k * (k - 1) / 2
        tot = sum(Kseq[i] * (Kseq[i] - 1) / 2 for i in range(T))
        # expected pairs under independence given per-file rates
        s1 = sum(pf.values()); s2 = sum(v * v for v in pf.values())
        exp = T * (s1 * s1 - s2) / 2
        res["coedit_lift"] = float(pair / exp) if exp > 0 else None
        # --- detector (rates estimated on train windows, restricted to the pool)
        p0 = np.mean([train_counts[f] / max(ntr, 1) for f in pool]) if ntr else 0.0
        s = 2.0
        logp = {f: math.log((train_counts[f] + s * max(p0, 1e-9)) / (ntr + s)) for f in pool}
        poolist = sorted(pool)
        lp = np.array([logp[f] for f in poolist])
        real_scores, cov_scores = [], []
        for d, K in zip(test_days, Kte):
            if K < 1:
                continue
            S = [f for f in byday.get(d, {}) if f in pool]
            real_scores.append(-sum(logp[f] for f in S))                       # larger => 'covert'
            idx = rng.choice(N, int(K), replace=False)
            cov_scores.append(-lp[idx].sum())
        # several covert draws per real window for a smoother estimate
        extra = []
        for K in Kte[Kte >= 1]:
            for _ in range(20):
                extra.append(-lp[rng.choice(N, int(K), replace=False)].sum())
        real_scores, extra = np.array(real_scores), np.array(extra)
        res["test_windows"] = int(len(real_scores))
        if len(real_scores) >= 20:
            res["detector_auc"] = auc_pos_lower(real_scores, extra)
            ci_a, ci5, ci1 = boot(real_scores, extra, rng)
            res["detector_auc_ci95"] = ci_a
            res["tpr_at_fpr5pct"], res["tpr_at_fpr5pct_ci95"] = tpr_at(real_scores, extra, .05), ci5
            res["tpr_at_fpr1pct"], res["tpr_at_fpr1pct_ci95"] = tpr_at(real_scores, extra, .01), ci1
        else:
            res["detector_auc"] = None
            res["note"] = "fewer than 20 usable test windows: detectability not estimated"
        # --- capacity / delivery time on the REAL count sequence (pool-restricted)
        cap = {}
        best = None
        for Kmin in range(1, min(N, 60) + 1):
            beta = math.floor(lc(N, Kmin)) - 64
            if beta - 48 <= 0:
                continue
            thr = (Kseq >= Kmin).mean() * (beta - 48)
            if best is None or thr > best[1]:
                best = (Kmin, thr)
        if best is None:
            cap["feasible"] = False
            cap["reason"] = "log2 C(N,K) too small for any K<=60: no capacity after the 64-bit margin and 48 bits of framing"
        else:
            Kmin = best[0]
            r_, b = capacity_days(list(Kseq), N, Kmin, a.nbits)
            cap.update(Kmin=Kmin, payload_bits_per_frame=int(b), frames_needed=int(math.ceil(a.nbits / b)) + 2,
                       usable_window_fraction=float((Kseq >= Kmin).mean()))
            if r_ and r_[0]:
                days_needed = np.array(r_[0])
                cap.update(feasible=True, delivery_days_median=float(np.median(days_needed)),
                           delivery_days_p90=float(np.quantile(days_needed, .9)),
                           start_days_that_complete=int(len(days_needed)), start_days_total=int(T))
            else:
                cap["feasible"] = False; cap["reason"] = "the observed span is too short or usable windows too rare"
        res["capacity"] = cap
        out["pools"][kind] = res
    # --- hour-of-day profile and burstiness (all my edits)
    hours = np.zeros(24)
    gaps_short = gaps_all = 0
    for d in days:
        ts = sorted(t for f, L in byday.get(d, {}).items() for t in L)
        for t in ts:
            hours[t.hour] += 1
        for t0, t1 in zip(ts, ts[1:]):
            gaps_all += 1
            if (t1 - t0).total_seconds() < 300:
                gaps_short += 1
    out["hour_profile"] = (hours / hours.sum()).round(4).tolist()
    out["fraction_gaps_under_5min"] = gaps_short / gaps_all if gaps_all else None
    json.dump(out, open("real_report.json", "w"), indent=1)

    # ---------- markdown + LaTeX ----------
    md = [f"# PQHide real-trace report\n", f"Top days by distinct files edited (count, date): {top_days}; bulk days excluded: {n_bulk}\n", f"Period {out['first_day']} to {out['last_day']} ({T} windows), {out['files_seen']} files, {out['events']} edit events (only mine: {out['only_my_edits']}).\n"]
    tex = ["\\begin{tabular}{lrr}", "\\toprule", "Quantity & Pool: all files & Pool: central band\\\\", "\\midrule"]
    P = out["pools"]
    def g(k, f="{:.2f}"):
        return [f.format(P[p][k]) if P[p].get(k) is not None else "--" for p in ("all", "band")]
    rows = [("Pool size $N$", g("N", "{:d}")), ("Mean edits per window $K$", g("K_mean")), ("Std.\\ dev.\\ of $K$", g("K_sd")),
            ("Active-window fraction", g("active_day_fraction")), ("Rate Gini", g("rate_gini")), ("Effective files", g("effective_files", "{:.0f}")),
            ("Co-editing lift", g("coedit_lift")), ("Detector AUC (held-out)", g("detector_auc")),
            ("TPR at FPR 5\\%", g("tpr_at_fpr5pct")), ("TPR at FPR 1\\%", g("tpr_at_fpr1pct"))]
    for name, v in rows:
        tex.append(f"{name} & {v[0]} & {v[1]}\\\\")
    dd = [P[p].get("capacity", {}).get("delivery_days_median") for p in ("all", "band")]
    tex.append("Median windows to deliver 1\\,KiB & " + " & ".join(f"{x:.0f}" if x else "not feasible" for x in dd) + "\\\\")
    tex += ["\\bottomrule", "\\end{tabular}"]
    open("tab_real.tex", "w").write("\n".join(tex) + "\n")
    for p in ("all", "band"):
        r = P[p]
        md.append(f"## Pool '{p}' (N={r['N']})\n")
        for k, v in r.items():
            if k != "capacity":
                md.append(f"- {k}: {v}")
        md.append("- capacity: " + json.dumps(r.get("capacity", {})) + "\n")
    md.append(f"## Timing\n- fraction of gaps < 5 min: {out['fraction_gaps_under_5min']}\n- hour profile (local, 24 values): {out['hour_profile']}\n")
    open("real_report.md", "w").write("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
