#!/usr/bin/env python3
"""Two-session latency table (tab_latency_real.tex) from per-session raw CSV + summary JSON.
Usage: python make_latency_table_2sessions.py raw1.csv sum1.json raw2.csv sum2.json   (pooled ell = median of all cell p50 call latencies)"""
import json, csv, math, statistics as st, sys
R = [list(csv.DictReader(open(p))) for p in (sys.argv[1], sys.argv[3])]
S = [json.load(open(p)) for p in (sys.argv[2], sys.argv[4])]
ell = st.median([s["call_s_p50"] for s in S[0] + S[1]])
L = ["\\begin{tabular}{rrrrrrrrr}", "\\toprule",
     "$c$ & $K_{\\rm nom}$ & $K$ & local & submit & s/edit & model & confirm & failed \\\\",
     " & & S1/S2 & (ms) & S1/S2 (s) & S1/S2 & S1/S2 (s) & S1/S2 (s) & S1/S2 \\\\", "\\midrule"]
for j, (a, b) in enumerate(zip(*S)):
    K = [st.median(int(r["K"]) for r in R[i][j * 10:(j + 1) * 10]) for i in (0, 1)]
    sub = [a["submit_s_median"], b["submit_s_median"]]; c = a["c"]
    mod = [math.ceil(K[i] / c) * ell for i in (0, 1)]
    L.append(f"{c} & {a['K']} & {K[0]:g}/{K[1]:g} & {a['local_ms_median']:.1f} & {sub[0]:.1f}/{sub[1]:.1f} & {sub[0]/K[0]:.2f}/{sub[1]/K[1]:.2f} & {mod[0]:.1f}/{mod[1]:.1f} & {a['confirm_s_median']:.1f}/{b['confirm_s_median']:.1f} & {a['failures']}/{b['failures']} \\\\")
L += ["\\bottomrule", "\\end{tabular}"]
open("tab_latency_real.tex", "w").write("\n".join(L) + "\n"); print("\n".join(L)); print("ell =", round(ell, 3))
