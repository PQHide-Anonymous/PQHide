Latency measurements, one Google Drive account, one machine, 23-24 Nov 2026.
Grid sessions 1-5 (latency_raw_sessionN.csv, latency_summary_sessionN.json): 90 windows each (c in {1,4,16} x K_nom in {20,60,105}, 10 reps), 450 in total.
Targeted campaign (latency_raw_targeted1.csv, latency_summary_targeted1.json): 80 windows (c in {4,16} x K_nom in {60,105}, 20 reps); reported separately.
Column K of the raw CSV = realised number of distinct edited files.
Sessions 1-3: first harness (retries on HTTP status only; no error classes; CSV has no error_classes column).
Sessions 4-5 and targeted: fixed harness (transport errors retried in submission and confirmation; error_classes and confirm_error_classes logged).
Clock time/connection: sessions 4 (16:31) and 5 (19:01) only, see notes_session{4,5}.txt (place and provider redacted for review). Sessions 1-3 and targeted: not logged.
ORPHAN_latency_summary_session4_noraw.json: a summary labelled session 4 whose raw CSV was not kept; NOT used in any table or statistic.
Table: python latency_kit/make_latency_table_pooled.py raw1 sum1 ... raw5 sum5 -> tab_latency_real.tex
Recipient-side session R1 (recv_session1_*): 15 windows, c=16, K_nom in {20,60,105}; recipient = sender's own account; harness recipient_latency.py.
