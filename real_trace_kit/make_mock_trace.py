#!/usr/bin/env python3
"""MOCK data generator, ONLY to test the pipeline (clearly not real data). Writes mock_edits.csv."""
import csv, sys, numpy as np
from datetime import datetime, timedelta, timezone
rng = np.random.default_rng(3)
N, T = 400, 300
rate = np.exp(0.9 * rng.standard_normal(N)); rate = 0.04 * rate / rate.mean()    # heterogeneous per-file daily prob
with open("mock_edits.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["file_hash", "time_utc", "by_me"])
    d0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for d in range(T):
        mult = rng.gamma(3, 1 / 3)                      # day-level activity
        for i in range(N):
            if rng.random() < min(1, rate[i] * mult):
                t = d0 + timedelta(days=d, hours=float(rng.choice([9, 10, 14, 15, 20], p=[.2, .3, .2, .2, .1]) + rng.random()))
                w.writerow([f"f{i:04d}", t.isoformat().replace("+00:00", "Z"), 1])
print("mock_edits.csv written")
