#!/usr/bin/env python3
"""Multi-session latency table (tab_latency_real.tex) and pooled statistics.
Usage: python make_latency_table_sessions.py raw1.csv sum1.json [raw2.csv sum2.json ...]
Pooled ell = median over all cell medians of the per-call latency (call_s_p50)."""
import json, csv, math, statistics as st, sys
a = sys.argv[1:]; assert len(a) >= 2 and len(a) % 2 == 0
R = [list(csv.DictReader(open(p))) for p in a[0::2]]; S = [json.load(open(p)) for p in a[1::2]]; ns = len(S)
ell = st.median([s["call_s_p50"] for ss in S for s in ss])
slash = lambda xs, f: "/".join(f.format(x) for x in xs)
L = ["\\begin{tabular}{rrrrrrrrr}", "\\toprule",
     "$c$ & $K_{\\rm nom}$ & $K$ & local & submit & s/edit & model & confirm & failed \\\\",
     " & & " + "/".join(f"S{i+1}" for i in range(ns)) + " & (ms) & " + "/".join(f"S{i+1}" for i in range(ns)) + " (s) & " +
     "/".join(f"S{i+1}" for i in range(ns)) + " & " + "/".join(f"S{i+1}" for i in range(ns)) + " (s) & " +
     "/".join(f"S{i+1}" for i in range(ns)) + " (s) & " + "/".join(f"S{i+1}" for i in range(ns)) + " \\\\", "\\midrule"]
errs, pe_c1, pe_c16, eps16 = [], {}, {}, []
for j in range(len(S[0])):
    c, kn = S[0][j]["c"], S[0][j]["K"]
    K = [st.median(int(r["K"]) for r in R[i][j * 10:(j + 1) * 10]) for i in range(ns)]
    sub = [S[i][j]["submit_s_median"] for i in range(ns)]
    mod = [math.ceil(K[i] / c) * ell for i in range(ns)]
    errs += [abs(sub[i] / mod[i] - 1) for i in range(ns)]
    if kn == 105 and c == 1: pe_c1 = [sub[i] / K[i] for i in range(ns)]
    if kn == 105 and c == 16: pe_c16 = [sub[i] / K[i] for i in range(ns)]; eps16 = [K[i] / sub[i] for i in range(ns)]
    L.append(f"{c} & {kn} & {slash(K,'{:g}')} & {S[0][j]['local_ms_median']:.1f} & {slash(sub,'{:.1f}')} & {slash([sub[i]/K[i] for i in range(ns)],'{:.2f}')} & {slash(mod,'{:.1f}')} & {slash([S[i][j]['confirm_s_median'] for i in range(ns)],'{:.1f}')} & {slash([S[i][j]['failures'] for i in range(ns)],'{:d}')} \\\\")
L += ["\\bottomrule", "\\end{tabular}"]
open("tab_latency_real.tex", "w").write("\n".join(L) + "\n"); print("\n".join(L))
print("sessions", ns, "pooled ell", round(ell, 3), "max model err", round(max(errs), 3))
print("per-edit speed-up c16 vs c1 (K~88-90):", [round(pe_c1[i] / pe_c16[i], 1) for i in range(ns)], "edits/s at c=16:", [round(x, 1) for x in eps16])
allp = lambda k: [s[k] for ss in S for s in ss]
print("cell p50 range", round(min(allp('call_s_p50')), 2), round(max(allp('call_s_p50')), 2), "p95", round(min(allp('call_s_p95')), 2), round(max(allp('call_s_p95')), 2))
print("p99 sorted top3", sorted(allp('call_s_p99'))[-3:], "p99 min", round(min(allp('call_s_p99')), 2))
print("confirm range", round(min(allp('confirm_s_median')), 1), round(max(allp('confirm_s_median')), 1))
for j in (0, 1, 2):
    print("c=1 row", j, "submit across sessions", [round(S[i][j]["submit_s_median"], 1) for i in range(ns)])
for j in (3, 4, 5, 6, 7, 8):
    print("row", j, [round(S[i][j]["submit_s_median"], 1) for i in range(ns)], "max", [round(S[i][j]["submit_s_max"], 1) for i in range(ns)])
tot = ns * 90; fw = sum(1 for i in range(ns) for j in range(9) if S[i][j]["failures"]); print("windows", tot, "windows with failures", fw, "failed updates", sum(s["failures"] for ss in S for s in ss), "retries", sum(s["retries"] for ss in S for s in ss), "throttled", sum(s["throttled"] for ss in S for s in ss))
ratios = [S[i][j]["submit_s_median"] / S[0][j]["submit_s_median"] for i in range(1, ns) for j in range(9)]
print("session/S1 submit ratio range", round(min(ratios), 2), round(max(ratios), 2))
