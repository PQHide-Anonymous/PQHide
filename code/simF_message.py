"""Sim F (review point 2): chosen/predictable-message leakage.
 (a) ORIGINAL design  y = mG + e : candidate-message test  wt(y + m'G) <= t  accepts the true m' and rejects others.
 (b) REVISED design   z = s || (payload xor stream(H(e))) || tag : test whether the transmitted bit string
     depends on the payload (all-zero vs random payloads): bit-bias chi-square, weight distribution KS,
     and the same candidate test (which has nothing to test against).
Output: results/simF.json"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repository root
import sys, json, numpy as np
from scipy import stats
sys.path.insert(0, ROOT + "/code")
from mdpc import QCMDPC
from simC_protocol import dem_encrypt, bytes_to_bits
rng = np.random.default_rng(99)
K = QCMDPC("L1", rng); r = K.r
res = {}
# (a) original design
n = 300; true_w, wrong_w = [], []
for _ in range(n):
    m = np.zeros(r, dtype=np.uint8)                       # predictable (all-zero) message
    e = K.sample_error(rng, K.t); y = K.encode(m, e)
    true_w.append(int((y ^ K.encode(m, np.zeros(2 * r, np.uint8))).sum()))
    m2 = rng.integers(0, 2, r).astype(np.uint8)
    wrong_w.append(int((y ^ K.encode(m2, np.zeros(2 * r, np.uint8))).sum()))
res["original_candidate_test"] = dict(trials=n, weight_true_candidate=[min(true_w), max(true_w)],
                                      weight_wrong_candidate_mean=float(np.mean(wrong_w)), threshold_t=K.t,
                                      accept_true=float(np.mean(np.array(true_w) <= K.t)),
                                      accept_wrong=float(np.mean(np.array(wrong_w) <= K.t)),
                                      allzero_message_weight_of_y=[int(min(true_w)), int(max(true_w))])
# (b) revised design: payload-dependence of the transmitted string
N = 3000; PL = 256
def tx(payload):
    e = K.sample_error(rng, K.t)
    return np.concatenate([K.encrypt_syndrome(e), bytes_to_bits(dem_encrypt(e, payload))])
Z0 = np.array([tx(bytes(PL)) for _ in range(N)])                   # all-zero payload
Z1 = np.array([tx(rng.bytes(PL)) for _ in range(N)])               # random payload
nb = Z0.shape[1]
p0 = stats.chi2.sf(((Z0.sum(0) - N / 2) ** 2 / (N / 4)).sum() , nb)    # global bit-bias test
# per-column two-sample chi-square -> uniformity of p-values
cols = np.arange(0, nb, 7)
pv = [stats.chi2_contingency(np.array([[Z0[:, j].sum(), N - Z0[:, j].sum()], [Z1[:, j].sum(), N - Z1[:, j].sum()]]), correction=False)[1] for j in cols]
ks_p = stats.kstest(pv, "uniform").pvalue
w0, w1 = Z0.sum(1), Z1.sum(1)
res["revised_payload_dependence"] = dict(samples_per_class=N, tx_bits=int(nb),
        mean_weight_zero=float(w0.mean()), mean_weight_random=float(w1.mean()), expected_weight=nb / 2,
        ks_weight_pvalue=float(stats.ks_2samp(w0, w1).pvalue),
        bitbias_global_pvalue_zero_payload=float(p0),
        per_column_pvalues_uniformity_ks=float(ks_p), n_columns_tested=int(len(cols)))
json.dump(res, open(ROOT + "/results/simF.json", "w"), indent=1)
print(json.dumps(res, indent=1))
