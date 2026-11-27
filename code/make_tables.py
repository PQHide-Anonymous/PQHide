"""Generate LaTeX table fragments (tables/*.tex) directly from results/*.json so that no
number in the paper is typed by hand."""
import json, math, os
from scipy import stats

R = "/home/claude/pqhide_rev/results/"
T = "/home/claude/pqhide_rev/tables/"
os.makedirs(T, exist_ok=True)
L = lambda f: json.load(open(R + f))


def w(name, s):
    open(T + name, "w").write(s)


def pct(x, d=1):
    return f"{100 * x:.{d}f}"


# ---------- DFR ----------
A = L("simA_dfr.json")["results"]
rows = {int(k): v for k, v in A.items()}
try:
    A2 = L("simA2_dfr.json")
    for k, v in A2.items():
        if v["level"] == "L1":
            rows[v["weight"]] = v
except Exception:
    A2 = {}
s = "\\begin{tabular}{rrrrl}\n\\toprule\n$|\\mathbf e|$ & Trials & Failures & DFR & 95\\% upper bound\\\\\n\\midrule\n"
for wt in sorted(rows):
    v = rows[wt]
    ub = v["ub95"]
    dfr = v["fail"] / v["n"]
    s += f"{wt} & {v['n']} & {v['fail']} & {dfr:.4f} & {ub:.4f}\\\\\n"
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_dfr_l1.tex", s)
s = "\\begin{tabular}{llrrrl}\n\\toprule\nLevel & BIKE $t$ & $|\\mathbf e|$ & Trials & Failures & 95\\% upper bound\\\\\n\\midrule\n"
for k, v in sorted(A2.items(), key=lambda kv: (kv[1]["level"], kv[1]["weight"])):
    if v["level"] == "L1":
        continue
    t_ = {"L3": 199, "L5": 264}[v["level"]]
    s += f"{v['level']} & {t_} & {v['weight']} & {v['n']} & {v['fail']} & {v['ub95']:.4f}\\\\\n"
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_dfr_l35.tex", s)

# ---------- B2 count inflation ----------
B = L("simB.json")
b2 = B["B2_count_inflation"]
s = "\\begin{tabular}{rcccccc}\n\\toprule\n & \\multicolumn{3}{c}{AUC} & \\multicolumn{3}{c}{TPR at FPR $=10^{-3}$}\\\\\n\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\n$\\rho$ & $T{=}1$ & $T{=}7$ & $T{=}30$ & $T{=}1$ & $T{=}7$ & $T{=}30$\\\\\n\\midrule\n"
for rho, row in b2.items():
    s += f"{float(rho):g} & " + " & ".join(f"{row[t]['auc']:.3f}" for t in ["1", "7", "30"]) + " & " + \
         " & ".join(f"{row[t]['tpr']['0.001']:.3f}" for t in ["1", "7", "30"]) + "\\\\\n"
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_count.tex", s)

# ---------- B3 selection vs sigma (oracle) ----------
b3 = B["B3_selection_vs_sigma"]
s = "\\begin{tabular}{rcccccc}\n\\toprule\n & \\multicolumn{3}{c}{AUC} & \\multicolumn{3}{c}{TPR at FPR $=10^{-3}$}\\\\\n\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\n$\\sigma$ & $T{=}1$ & $T{=}7$ & $T{=}30$ & $T{=}1$ & $T{=}7$ & $T{=}30$\\\\\n\\midrule\n"
for sg, row in b3.items():
    s += f"{float(sg):g} & " + " & ".join(f"{row[t]['auc']:.3f}" for t in ["1", "7", "30"]) + " & " + \
         " & ".join(f"{row[t]['tpr']['0.001']:.3f}" for t in ["1", "7", "30"]) + "\\\\\n"
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_sel_oracle.tex", s)

# ---------- B6 estimated-rate adversary ----------
E = L("simB2.json")["results"]
s = "\\begin{tabular}{rrrcc}\n\\toprule\n$\\sigma$ & History $H$ (windows) & AUC & TPR@FPR$=10^{-2}$ & TPR@FPR$=10^{-3}$\\\\\n\\midrule\n"
for k, v in E.items():
    sg, H = k.split(",")
    s += f"{sg.split('=')[1]} & {int(H.split('=')[1]):,} & {v['auc']:.3f} & {v['tpr_1e2']:.3f} & {v['tpr_1e3']:.3f}\\\\\n".replace(",", "\\,")
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_sel_est.tex", s)

# ---------- B4 clustering ----------
b4 = B["B4_clustering_gbm"]
s = "\\begin{tabular}{rccc}\n\\toprule\n$\\gamma$ & AUC & TPR@FPR$=10^{-2}$ & TPR@FPR$=10^{-3}$\\\\\n\\midrule\n"
for g, v in b4.items():
    s += f"{float(g):g} & {v['auc']:.3f} & {v['tpr']['0.01']:.3f} & {v['tpr']['0.001']:.3f}\\\\\n"
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_cluster.tex", s)

# ---------- protocol ----------
try:
    C = L("simC.json")
    s = "\\begin{tabular}{rrrrrrrrr}\n\\toprule\n$K_{\\min}$ & $F_1$ & $F_2$ & Bits/window & $P[K{\\ge}K_{\\min}]$ & $\\nu N$ & Recovered & Median & P95\\\\\n & & & ($\\beta$) & & & & windows & windows\\\\\n\\midrule\n"
    last = None
    for k, v in C.items():
        Km = int(k.split(",")[0].split("=")[1]); nu = float(k.split(",")[1].split("=")[1])
        if last is not None and Km != last:
            s += "\\midrule\n"
        last = Km
        rec = f"{v['correct']}/{v['n_msgs']}"
        med = f"{v['windows_median']:.0f}" if v["windows_median"] is not None else "--"
        p95 = f"{v['windows_p95']:.0f}" if v["windows_p95"] is not None else "--"
        s += f"{Km} & {v['F1']} & {v['F2']} & {v['beta']} & {v['P_K_ge_Kmin']:.3f} & {nu:g} & {rec} & {med} & {p95}\\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n"
    w("tab_protocol.tex", s)
    s = "\\begin{tabular}{rrrrrr}\n\\toprule\n$K_{\\min}$ & $\\nu N$ & Cycles & Eligible windows & Theory & Ratio\\\\\n & & (mean) & (mean) & (approx.) & \\\\\n\\midrule\n"
    last = None
    for k, v in C.items():
        Km = int(k.split(",")[0].split("=")[1]); nu = float(k.split(",")[1].split("=")[1])
        if last is not None and Km != last:
            s += "\\midrule\n"
        last = Km
        s += f"{Km} & {nu:g} & {v['cycles_mean']:.2f} & {v['eligible_mean']:.1f} & {v['eligible_theory']:.1f} & {v['eligible_mean'] / v['eligible_theory']:.2f}\\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n"
    w("tab_survival.tex", s)
except FileNotFoundError:
    pass

# ---------- timing ----------
try:
    D = L("simD.json")
    f = lambda d: f"{d['mean_ms']:.2f} $\\pm$ {d['ci95_ms']:.2f}"
    s = "\\begin{tabular}{lrrrrr}\n\\toprule\nLevel & $n=2r$ & Key generation & Encode & Decode & $n$ runs (decode)\\\\\n & (bits) & (ms) & (ms) & (ms) & \\\\\n\\midrule\n"
    for lvl in ["L1", "L3", "L5"]:
        v = D[lvl]
        s += f"{lvl} & {v['n']} & {f(v['keygen'])} & {f(v['encode'])} & {f(v['decode'])} & {v['decode']['n']}\\\\\n"
    s += "\\midrule\n"
    for nm in ["RSA2048_OAEP", "X25519_ECIES"]:
        v = D[nm]
        lab = "RSA-2048 OAEP" if nm.startswith("RSA") else "X25519 ECIES"
        s += f"{lab} & -- & -- & {f(v['encrypt'])} & {f(v['decrypt'])} & {v['encrypt']['n']}\\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n"
    w("tab_timing.tex", s)
    s = "\\begin{tabular}{rrrrr}\n\\toprule\n$K_{\\min}$ & $K$ & Payload/frame (bits) & Embed (ms) & Extract (ms)\\\\\n\\midrule\n"
    for k in ["frame_Kmin50", "frame_Kmin105"]:
        v = D[k]
        s += f"{k.split('Kmin')[1]} & {v['K']} & {v['payload_bits']} & {f(v['embed'])} & {f(v['extract'])}\\\\\n"
    s += "\\bottomrule\n\\end{tabular}\n"
    w("tab_frame_timing.tex", s)
except FileNotFoundError:
    pass

# ---------- channel-use comparison (sizes) ----------
N = 1 << 17
mu, kappa = 105.0, 8.0
import sys
sys.path.insert(0, "/home/claude/pqhide_rev/code")
from protocol import frame_geometry
Kmin = 105
beta, pb = frame_geometry(N, Kmin)
pk = 1 - stats.nbinom.cdf(Kmin - 1, kappa, kappa / (kappa + mu))
pay = 1024
def windows(bits):
    return (math.ceil(bits / pb) + 1.6) / pk
rows = [
    ("RSA-2048-OAEP + AEAD", 256, False, 8 * (256 + pay + 16)),
    ("X25519 ECIES + AEAD", 32, False, 8 * (32 + pay + 16)),
    ("ML-KEM-768 + AEAD", 1088, True, 8 * (1088 + pay + 16)),
    ("PQHide (QC-MDPC L1 syndrome + stream)", math.ceil(12323 / 8), True, 12323 + 8 * (pay + 16)),
]
s = "\\begin{tabular}{lrcrr}\n\\toprule\nEncryption layer & KEM ct (B) & Quantum-safe & Bits to convey for 1\\,KiB & Windows ($K_{\\min}{=}105$)\\\\\n\\midrule\n"
for n_, ct, qs, bits in rows:
    s += f"{n_} & {ct} & {'yes' if qs else 'no'} & {bits} & {windows(bits):.0f}\\\\\n"
s += "\\bottomrule\n\\end{tabular}\n"
w("tab_channel_cost.tex", s)
print("tables written:", sorted(os.listdir(T)))

# ---------- DFR figure (pgfplots) ----------
pts = []
for wt in sorted(rows_dfr := {int(k): v for k, v in A.items()}):
    pass
allrows = {int(k): v for k, v in A.items()}
for k, v in A2.items():
    if v["level"] == "L1":
        allrows[v["weight"]] = v
nz, z = [], []
for wt in sorted(allrows):
    v = allrows[wt]
    if v["fail"] > 0:
        nz.append((wt, v["fail"] / v["n"]))
    else:
        z.append((wt, v["ub95"]))
fig = "\\begin{tikzpicture}\n\\begin{semilogyaxis}[pqaxis, xlabel={total error weight $|\\mathbf e|$}, ylabel={failure rate / 95\\% upper bound}, ymin=2e-4, ymax=1.2]\n"
fig += "\\addplot[only marks, mark=*] coordinates {" + " ".join(f"({a},{b:.5f})" for a, b in nz) + "};\n"
fig += "\\addplot[only marks, mark=o] coordinates {" + " ".join(f"({a},{b:.5f})" for a, b in z) + "};\n"
fig += "\\draw[dashed] (axis cs:134,2e-4) -- (axis cs:134,1.2);\n\\legend{observed failures, 95\\% bound (0 failures)}\n\\end{semilogyaxis}\n\\end{tikzpicture}\n"
w("fig_dfr.tex", fig)

# ---------- memory ----------
try:
    Ee = L("simE.json")
    s2 = "\\begin{tabular}{lrrr}\n\\toprule\nLevel & Key generation & Encapsulation & Decoding\\\\\n & (MiB) & (MiB) & (MiB)\\\\\n\\midrule\n"
    for lv in ["L1", "L3", "L5"]:
        v = Ee[lv]
        s2 += f"{lv} & {v['keygen_peak_MiB']:.1f} & {v['encode_peak_MiB']:.1f} & {v['decode_peak_MiB']:.1f}\\\\\n"
    s2 += "\\bottomrule\n\\end{tabular}\n"
    w("tab_memory.tex", s2)
except FileNotFoundError:
    pass
print("extra tables written")

# ---------- full local cycle ----------
try:
    G = L("simG.json")
    f = lambda d: f"{d['mean_ms']:.1f} $\\pm$ {d['ci95_ms']:.1f}"
    s3 = ("\\begin{tabular}{lrr}\n\\toprule\nStage & Time (ms) & $F_1{+}F_2$ / bits\\\\\n\\midrule\n"
          f"Sender & {f(G['sender'])} & {G['F1']}+{G['F']} / {G['n_bits']}\\\\\n"
          "Receiver & " + f(G['receiver']) + " & \\\\\n\\bottomrule\n\\end{tabular}\n")
    w("tab_cycle.tex", s3)
except FileNotFoundError:
    pass

# ---------- ISD estimates ----------
H = L("simH.json")
s4 = ("\\begin{tabular}{lrrrrr}\n\\toprule\n & \\multicolumn{3}{c}{Message recovery ($\\log_2$)} & \\multicolumn{2}{c}{Quantum, naive}\\\\\n"
      "\\cmidrule(lr){2-4}\\cmidrule(lr){5-6}\nLevel & BIKE formula & Prange & Stern & Stern & Prange\\\\\n\\midrule\n")
for lv in ["L1", "L3", "L5"]:
    d = H[lv]
    s4 += (f"{lv} & {d['bike_spec_asymptotic_msg_log2']:.0f} & {d['prange']['msg_classical_log2']:.0f} & {d['stern']['msg_classical_log2']:.0f} & "
           f"{d['stern']['msg_quantum_log2']:.0f} & {d['prange']['msg_quantum_log2']:.0f}\\\\\n")
s4 += "\\bottomrule\n\\end{tabular}\n"
w("tab_isd.tex", s4)

# ---------- timing / order ----------
I = L("simI.json")
nm = {"T1": "rate-limited stream", "T2": "diurnal marginal only", "T3": "session-copy (natural timing)"}
s5 = ("\\begin{tabular}{llcccc}\n\\toprule\nTiming & Order & AUC ($T{=}1$) & TPR@$10^{-3}$ ($T{=}1$) & AUC ($T{=}7$) & TPR@$10^{-3}$ ($T{=}7$)\\\\\n\\midrule\n")
for tk in ["T1", "T2", "T3"]:
    for ok in ["sorted", "shuffled"]:
        v = I[f"{tk}/{ok}"]
        s5 += f"{nm[tk]} & {ok} & {v['auc_T1']:.3f} & {v['tpr1e3_T1']:.3f} & {v['auc_T7']:.3f} & {v['tpr1e3_T7']:.3f}\\\\\n"
    if tk != "T3": s5 += "\\midrule\n"
s5 += "\\bottomrule\n\\end{tabular}\n"
w("tab_timing_order.tex", s5)
print("isd/timing tables ok")


# ---------- simulated behaviour on the real Drive API ----------
try:
    H, O = L("sim_drive/sim_het_report.json"), L("sim_drive/sim_hom_report.json")
    nm = [("distinct_files", "Distinct files"), ("edits_per_file", "Edits per file"), ("hot_file_fraction", "Hot-file fraction"), ("jaccard_with_previous", "Overlap with previous")]
    f = lambda d: f"{d['auc']:.2f} [{d['auc_ci95'][0]:.2f}, {d['auc_ci95'][1]:.2f}]"
    s = "\\begin{tabular}{l@{\\hspace{4pt}}c@{\\hspace{4pt}}c}\n\\toprule\nAUC [95\\% CI] & Heterog. baseline & Uniform baseline\\\\\n\\midrule\n"
    for k, n in nm:
        s += f"{n} & {f(H['features'][k])} & {f(O['features'][k])}\\\\\n"
    s += f"Combined (5-fold CV) & {H['lda_cv']['auc']:.2f} & {O['lda_cv']['auc']:.2f}\\\\\n"
    s += f"Windows (base./scheme) & {H['baseline']} / {H['scheme']} & {O['baseline']} / {O['scheme']}\\\\\n\\bottomrule\n\\end{{tabular}}\n"
    w("tab_sim_drive.tex", s)
except FileNotFoundError:
    pass
