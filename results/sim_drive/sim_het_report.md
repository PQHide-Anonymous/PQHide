# Simulation report (SIMULATED behaviour on a real cloud API)

Windows used: 60 (baseline 20, scheme 40)

| feature | AUC [95% CI] | advantage | mean baseline | mean scheme |
|---|---|---|---|---|
| distinct_files | 0.299 [0.154, 0.429] | 0.425 | 94.55 | 81.22 |
| edits_per_file | 0.353 [0.209, 0.507] | 0.325 | 1.07 | 1.05 |
| hot_file_fraction | 0.003 [0.000, 0.011] | 0.950 | 0.42 | 0.24 |
| jaccard_with_previous | 0.290 [0.147, 0.448] | 0.375 | 0.29 | 0.23 |

LDA (5-fold CV): AUC 0.963, advantage 0.825
