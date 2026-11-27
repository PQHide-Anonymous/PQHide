# PQHide real-trace report

Top days by distinct files edited (count, date): [(1003, '2025-11-24'), (151, '2026-05-16'), (121, '2026-04-29'), (20, '2026-09-14'), (4, '2026-01-13'), (3, '2026-09-19'), (3, '2026-06-24'), (2, '2026-09-21'), (2, '2026-09-07'), (2, '2026-09-02')]; bulk days excluded: 2

Period 2025-11-25 to 2026-10-13 (322 windows), 184 files, 1914 edit events (only mine: True).

## Pool 'all' (N=184)

- N: 184
- K_mean: 0.5807453416149069
- K_sd: 6.839595327228288
- K_quantiles_50_90_99: [0.0, 1.0, 3.0]
- active_day_fraction: 0.10559006211180125
- overdispersion_kappa: 0.00730021913412732
- rate_gini: 0.01578121367123925
- effective_files: 181.18652849740923
- coedit_lift: 138.31481481481484
- test_windows: 19
- detector_auc: None
- note: fewer than 20 usable test windows: detectability not estimated
- capacity: {"Kmin": 60, "payload_bits_per_frame": 51, "frames_needed": 407, "usable_window_fraction": 0.003105590062111801, "feasible": false, "reason": "the observed span is too short or usable windows too rare"}

## Pool 'band' (N=181)

- N: 181
- K_mean: 0.562111801242236
- K_sd: 6.838879543318649
- K_quantiles_50_90_99: [0.0, 0.0, 3.0]
- active_day_fraction: 0.09316770186335403
- overdispersion_kappa: 0.0068379625180636765
- rate_gini: -3.2736346319950595e-18
- effective_files: 181.00000000000003
- coedit_lift: 147.59815837937387
- test_windows: 16
- detector_auc: None
- note: fewer than 20 usable test windows: detectability not estimated
- capacity: {"Kmin": 60, "payload_bits_per_frame": 49, "frames_needed": 424, "usable_window_fraction": 0.003105590062111801, "feasible": false, "reason": "the observed span is too short or usable windows too rare"}

## Timing
- fraction of gaps < 5 min: 0.9389312977099237
- hour profile (local, 24 values): [0.0034, 0.0743, 0.0, 0.0, 0.0034, 0.0135, 0.0, 0.0068, 0.0034, 0.1622, 0.0574, 0.0236, 0.0068, 0.0135, 0.027, 0.0236, 0.0203, 0.0034, 0.0135, 0.0034, 0.1216, 0.0034, 0.0068, 0.4088]
