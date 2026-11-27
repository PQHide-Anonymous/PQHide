# Simulation report (SIMULATED behaviour on a real cloud API)

Windows used: 60 (baseline 20, scheme 40)

| feature | AUC [95% CI] | advantage | mean baseline | mean scheme |
|---|---|---|---|---|
| distinct_files | 0.546 [0.396, 0.697] | 0.125 | 75.40 | 78.72 |
| edits_per_file | 0.510 [0.349, 0.664] | 0.150 | 1.04 | 1.04 |
| hot_file_fraction | 0.493 [0.321, 0.661] | 0.200 | 0.24 | 0.24 |
| jaccard_with_previous | 0.554 [0.384, 0.705] | 0.200 | 0.20 | 0.22 |

LDA (5-fold CV): AUC 0.414, advantage 0.250
