#!/usr/bin/env python3
"""Compact N-session latency table + pooled statistics.
Usage: python make_latency_table_pooled.py raw1.csv sum1.json [raw2.csv sum2.json ...]   (grid sessions: same 9 cells, 10 reps)
Writes tab_latency_real.tex (cwd). Cells: pooled median of per-session medians, with [min-max] over sessions.
slow window := submit or confirm time > 2x the median of its cell (all sessions pooled)."""
import json, csv, math, statistics as st, sys, collections
a = sys.argv[1:]; assert len(a) >= 2 and len(a) % 2 == 0
R = [list(csv.DictReader(open(p))) for p in a[0::2]]; S = [json.load(open(p)) for p in a[1::2]]; ns = len(S); nc = len(S[0])
ell = st.median([s["call_s_p50"] for ss in S for s in ss])
rows, errs = [], []
L = ["\\begin{tabular}{rrrrrrrrr}", "\\toprule",
     "$c$ & $K_{\\rm nom}$ & $K$ & local & submit & s/edit & model & confirm & failed \\\\",
     " & & (median) & (ms) & median [range] (s) & (s) & (s) & median [range] (s) & (updates) \\\\", "\\midrule"]
slow = []
for j in range(nc):
    c, kn = S[0][j]["c"], S[0][j]["K"]
    blocks = [R[i][j*10:(j+1)*10] for i in range(ns)]
    K = st.median(int(r["K"]) for b in blocks for r in b)
    sub = [S[i][j]["submit_s_median"] for i in range(ns)]; conf = [S[i][j]["confirm_s_median"] for i in range(ns)]
    mod = math.ceil(K / c) * ell; errs += [abs(x / (math.ceil(int(np_) / c) * ell) - 1) for x, np_ in [(sub[i], st.median(int(r["K"]) for r in blocks[i])) for i in range(ns)]]
    ms, mc = st.median(sub), st.median(conf)
    for i, b in enumerate(blocks):
        for r in b:
            for k, ref in (("t_submit_s", ms), ("t_confirm_s", mc)):
                if float(r[k]) > 1.5 * ref: slow.append((i + 1, c, kn, k[2:-2], round(float(r[k]), 1), r.get("error_classes", "n/a"), r.get("confirm_error_classes", "n/a")))
    L.append(f"{c} & {kn} & {K:g} & {S[0][j]['local_ms_median']:.1f} & {ms:.1f} [{min(sub):.1f}--{max(sub):.1f}] & {ms/K:.2f} & {mod:.1f} & {mc:.1f} [{min(conf):.1f}--{max(conf):.1f}] & {sum(S[i][j]['failures'] for i in range(ns))} \\\\")
L += ["\\bottomrule", "\\end{tabular}"]
open("tab_latency_real.tex", "w").write("\n".join(L) + "\n"); print("\n".join(L))
print("sessions", ns, "windows", ns * nc * 10, "pooled ell", round(ell, 3), "max model err (session-cells)", round(max(errs), 3), "n session-cells", len(errs))
allp = lambda k: [s[k] for ss in S for s in ss]
print("cell p50", round(min(allp('call_s_p50')), 2), round(max(allp('call_s_p50')), 2), "p95", round(min(allp('call_s_p95')), 2), round(max(allp('call_s_p95')), 2), "p99", round(min(allp('call_s_p99')), 2), sorted(round(x, 2) for x in allp('call_s_p99'))[-4:])
print("confirm range", round(min(allp('confirm_s_median')), 1), round(max(allp('confirm_s_median')), 1))
for lab, (c0, c1) in (("seq K~88", (2, 2)), ("4w K~88", (5, 5)), ("16w K~88", (8, 8))):
    v = [S[i][c0]["submit_s_median"] for i in range(ns)]; print(lab, "submit sessions", [round(x, 1) for x in v], "range", round(min(v), 1), round(max(v), 1))
pe1 = [S[i][2]["submit_s_median"] / st.median(int(r["K"]) for r in R[i][20:30]) for i in range(ns)]
pe16 = [S[i][8]["submit_s_median"] / st.median(int(r["K"]) for r in R[i][80:90]) for i in range(ns)]
print("speed-up 16w", [round(x / y, 1) for x, y in zip(pe1, pe16)], "edits/s at 16w", [round(1 / y, 1) for y in pe16])
print("failed updates", sum(s["failures"] for ss in S for s in ss), "windows with failures", sum(1 for ss in S for s in ss if s["failures"]), "retries", sum(s["retries"] for ss in S for s in ss), "throttled", sum(s["throttled"] for ss in S for s in ss))
ratios = [S[i][j]["submit_s_median"] / S[0][j]["submit_s_median"] for i in range(1, ns) for j in range(nc)]; print("session/S1 submit ratio", round(min(ratios), 2), round(max(ratios), 2))
print("slow windows (session,c,Knom,phase,seconds,submit_err,confirm_err):"); [print("  ", x) for x in slow]
