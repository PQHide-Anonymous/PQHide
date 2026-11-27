# PQHide — reproducibility package

Code, raw results and table generators for the experiments reported in the paper *"PQHide: A Post-Quantum Steganography
System Exploiting Cloud Computing"* (revised version). The repository contains **only** what is needed to reproduce
the reported numbers; the manuscript is not included.

## What is (and is not) in the experiments
* Everything runs **offline** in an in-memory cloud emulator, except the two optional kits in `real_trace_kit/` and
  `latency_kit/`, which call the Google Drive APIs with the user's own account.
* The steganalysis results (Sims B, B2, I) are obtained on an **explicit synthetic activity model**, not on real traffic.
* ISD costs (Sim H) are **transparent estimates** (Prange/Stern, naive Grover); they are not NIST security levels.
* The decoder is a BGF-style bit-flipping decoder written for this study; its DFR evidence is empirical and is not
  the BIKE reference implementation.
* The real-trace and latency kits report measurements from **one account, one machine, five sessions**
  (see `results/real_trace`, `results/latency`).

## Layout
| Path | Content |
|---|---|
| `code/mdpc.py`, `code/protocol.py` | QC-MDPC (BIKE Round-4 shapes L1/L3/L5), hybrid KEM-DEM, colex rank coding, two-phase framing (plain encapsulation chunks, session-key-masked CRC frames), GF(2) fountain code |
| `code/sim*.py` | simulations (table below); each writes `results/<name>.json` |
| `code/make_tables.py` | builds every LaTeX table fragment in `tables/` from `results/*.json` (no number is typed by hand) |
| `results/` | raw JSON outputs of all simulations, plus `real_trace/`, `latency/` and `sim_drive/` |
| `tables/` | generated LaTeX table fragments |
| `real_trace_kit/` | exporter (Drive Activity API) and analysis of a real edit trace |
| `latency_kit/` | per-window cloud-cost measurement (Drive API v3); `simulate_on_drive.py` + `analyze_sim.py`: simulated behaviour on the real API |
| `tests/test_smoke.py` | fast correctness checks |

## Installation
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python tests/test_smoke.py          # rank coding, plain/keyed frame embedding, QC-MDPC L1 decoding at t=134
```
Tested with Python 3.13, NumPy 2.5, SciPy 1.18, scikit-learn 1.9 (any recent versions should work).

## Reproducing the results
All seeds are fixed in the scripts. Run from the repository root (`python code/<script>.py`).
Results of Sims A, A2 and C use `multiprocessing.Pool(2)`; run times depend on the machine (the reported runs used
a 2-core VM).

| Script | Content | Output |
|---|---|---|
| `simA_dfr.py`, `simA2_dfr_more.py` | decoding-failure rate vs. error weight (L1; L3/L5 around BIKE's t) | `simA_dfr.json`, `simA2_dfr.json` |
| `simB_stegan.py` | steganalysis on the synthetic model: count, oracle selection, clustering, gradient boosting, null control | `simB.json` |
| `simB2_estimated_adversary.py` | history-limited adversary estimating per-file rates | `simB2.json` |
| `simC_protocol.py` | end-to-end protocol (two-phase framing, cycles, stray external edits) | `simC.json` |
| `simD_timing.py` | local computation cost (QC-MDPC L1/L3/L5, RSA-2048 OAEP and X25519 baselines in the same harness) | `simD.json` |
| `simE_memory.py` | peak memory | `simE.json` |
| `simF_message.py` | predictable / chosen message leakage (v1 vs. hybrid design) | `simF.json` |
| `simG_cycle.py` | local cycle for a 1 KiB message | `simG.json` |
| `simH_isd.py` | ISD work-factor estimates (deterministic, runs in seconds) | `simH.json` |
| `simI_timing_order.py` | timing and edit-order steganalysis | `simI.json` |

Then regenerate the tables: `python code/make_tables.py` (writes `tables/*.tex`; with the provided `results/` it
reproduces the provided tables byte for byte). Timing and memory figures (Sims D, E, G) depend on the machine and will differ.

## Real-trace kit (`real_trace_kit/`)
Measures the cover-model gap on an edit trace exported from the user's own Google Drive.
1. Create a Google Cloud project, enable the *Drive Activity API*, create an OAuth *desktop* client and save it as `credentials.json`.
2. `pip install -r real_trace_kit/requirements.txt`
3. `python real_trace_kit/export_drive_activity.py --folder-id <ID or ALL> --out edits.csv`
   writes only `file_hash,time_utc,by_me` (SHA-256 of a private salt + file id, truncated); no names, contents or e-mails.
4. `python real_trace_kit/analyze_real_trace.py edits.csv --tz <IANA zone> --exclude-bulk 150 --min-days 1`
   (`--since YYYY-MM-DD`, `--all-actors`, `--min-days` are optional) produces `real_report.{md,json}` and `tab_real.tex`.
   `real_trace_kit/make_mock_trace.py` generates synthetic data to test the pipeline only.

Reported outcome (`results/real_trace/`): after removing bulk-operation days, the analysed account had a mean of
0.58 edited files per day, so delivery of 1 KiB is not feasible. This is a negative applicability result, not a measurement of the gap.
**Never publish** `credentials.json`, `token*.json`, `salt.txt` or the CSV.

## Latency kit (`latency_kit/`)
`python latency_kit/measure_drive_latency.py --files 300 --K 20,60,105 --conc 1,4,16 --reps 10 --cleanup`
creates test files in a new Drive folder (scope `drive.file`), times local computation, submission and confirmation of
`K` individual `files.update` calls with `c` workers, and deletes the folder. `--dry-run` uses a synthetic backend with no network
(pipeline test only). `make_latency_table_2sessions.py` builds the two-session table from the raw CSVs in `results/latency/`.
Both reported sessions used a harness version that retried only HTTP status codes and did not log the error class;
the current version retries and classifies transport errors but has not been re-run against the live API.

## License
See `LICENSE`.

## Public-adversary check and cover-gap bound
- `latency_kit/public_frame_test.py`: shows that the old public recognition test (unkeyed mask + CRC) accepts 0 of 600 windows of the current framing, and that low-bit statistics of covert windows match natural ones.
- `latency_kit/esel_bound.py`: computable upper bound on the cover-model gap for an independent-edit cover model from per-file rates (Pinsker + KL additivity over windows; validated by exhaustive enumeration).

## Simulated behaviour on a real cloud API (`results/sim_drive/`)
Two runs of 80 windows (120 s) with `latency_kit/simulate_on_drive.py` (uniform baseline `--hetero 0.0`, heterogeneous `--hetero 1.0`),
read back through the Drive Activity API and analysed with `latency_kit/analyze_sim.py`. **This is simulated behaviour, not real user activity.**
Raw traces and test-folder identifiers are not published (manifests show `TESTFOLDER`). See `latency_kit/README_simulation.md`.
