#!/usr/bin/env python3
"""Measure the cloud cost of one PQHide window on YOUR Google Drive account.

A window = K individual content edits (each: files.update with a new media body = file content + one more line),
exactly the operation the paper assumes (no batching).  Per window we log THREE separate phases:
  t_local   : local computation (frame embedding = choosing the K files)        [protocol.embed_keyed]
  t_submit  : wall time from first request sent to LAST update call returned OK (includes retries/backoff)
  t_confirm : extra time until every edited file shows a new `version` through files.get
              (what a recipient could observe; polling interval --poll)
plus per-call latencies, number of retries, HTTP 403/429 (throttling) events, and failures.
Concurrency levels c are run in separate series; each (c, K) is repeated --reps times.

It only touches files it creates itself, in ONE new folder 'pqhide_latency_test' (scope drive.file = least privilege).
At the end it can delete that folder (--cleanup).

Usage (real):   python measure_drive_latency.py --files 300 --K 20,60,105 --conc 1,4,16 --reps 5 --cleanup
Usage (dry run, no network, synthetic latencies -> tests the pipeline only):  python measure_drive_latency.py --dry-run
Status: NOT run against the live API by the author of this kit (no network in the authoring sandbox).
"""
import argparse, csv, io, json, os, random, statistics as st, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import os
import protocol as P
SESSION_KEY = os.urandom(32)   # stands for the secret session key K (v3 framing)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
RETRY_CODES = (403, 429, 500, 502, 503, 504)


# ------------------------------------------------------------------ backends
class RealDrive:
    def __init__(self):
        self.tl = threading.local()

    def _svc(self):                       # httplib2 is not thread-safe: one service per thread
        if not hasattr(self.tl, "svc"):
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            c = None
            if os.path.exists("token_lat.json"):
                c = Credentials.from_authorized_user_file("token_lat.json", SCOPES)
            if not c or not c.valid:
                if c and c.expired and c.refresh_token:
                    c.refresh(Request())
                else:
                    c = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
                open("token_lat.json", "w").write(c.to_json())
            self.tl.svc = build("drive", "v3", credentials=c, cache_discovery=False)
        return self.tl.svc

    def create_folder(self, name):
        return self._svc().files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]

    def create_file(self, folder, name, text):
        from googleapiclient.http import MediaIoBaseUpload
        m = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain")
        r = self._svc().files().create(body={"name": name, "parents": [folder]}, media_body=m, fields="id,version").execute()
        return r["id"], int(r["version"])

    def update(self, fid, text):          # one raw attempt; raises HttpError on failure
        from googleapiclient.http import MediaIoBaseUpload
        m = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain")
        return self._svc().files().update(fileId=fid, media_body=m, fields="id,version").execute()

    def version(self, fid):
        return int(self._svc().files().get(fileId=fid, fields="version").execute()["version"])

    def delete(self, fid):
        self._svc().files().delete(fileId=fid).execute()

    @staticmethod
    def status_of(e):
        from googleapiclient.errors import HttpError
        return e.resp.status if isinstance(e, HttpError) else None


class FakeHttpError(Exception):
    def __init__(self, s): self.status = s


class DryDrive:
    """Synthetic backend: lognormal latency, rate limit when more than 10 calls are in flight, version lag."""
    def __init__(self, seed=0):
        self.rng = random.Random(seed); self.v = {}; self.lock = threading.Lock(); self.inflight = 0; self.lag = {}
    def create_folder(self, name): return "folder"
    def create_file(self, folder, name, text):
        i = f"f{len(self.v)}"; self.v[i] = 1; return i, 1
    def update(self, fid, text):
        with self.lock:
            self.inflight += 1; over = self.inflight > 10
        try:
            time.sleep(self.rng.lognormvariate(-1.6, 0.4) * 0.05)          # scaled x0.05 so the dry run is fast
            if over and self.rng.random() < 0.3: raise FakeHttpError(429)
            with self.lock:
                self.v[fid] += 1; self.lag[fid] = time.time() + self.rng.random() * 0.02
            return {"id": fid}
        finally:
            with self.lock: self.inflight -= 1
    def version(self, fid):
        time.sleep(0.002)
        return self.v[fid] if time.time() >= self.lag.get(fid, 0) else self.v[fid] - 1
    def delete(self, fid): pass
    @staticmethod
    def status_of(e): return getattr(e, "status", None)


# ------------------------------------------------------------------ measurement
def update_with_retry(be, fid, text, max_tries=8):
    retries, throttled = 0, 0
    errs = []                                   # error classes seen (status or exception type), also when a retry succeeds
    t0 = time.perf_counter()
    for k in range(max_tries):
        t1 = time.perf_counter()
        try:
            be.update(fid, text)
            t2 = time.perf_counter()
            return dict(ok=1, call_s=t2 - t1, total_s=t2 - t0, retries=retries, throttled=throttled, errs=errs)
        except Exception as e:
            s = be.status_of(e)
            errs.append(f"HTTP{s}" if s else type(e).__name__)
            if s in RETRY_CODES or s is None:             # transport errors (timeout, reset, SSL...) are retried too
                if s in (403, 429): throttled += 1
                retries += 1
                time.sleep(min(32, 2 ** k * 0.25) * (0.5 + random.random()))      # exponential backoff + jitter
                continue
            return dict(ok=0, call_s=time.perf_counter() - t1, total_s=time.perf_counter() - t0, retries=retries, throttled=throttled, errs=errs)
    return dict(ok=0, call_s=0, total_s=time.perf_counter() - t0, retries=retries, throttled=throttled, errs=errs)


def read_version_with_retry(be, fid, tries=6):
    """files.get with retries on HTTP retryable codes and on transport errors (SSL EOF, reset, timeout).
    Returns (version or None, list of error classes seen)."""
    errs = []
    for k in range(tries):
        try:
            return be.version(fid), errs
        except Exception as e:
            st_ = be.status_of(e)
            errs.append(f"HTTP{st_}" if st_ else type(e).__name__)
            if st_ in RETRY_CODES or st_ is None:
                time.sleep(min(16, 2 ** k * 0.25) * (0.5 + random.random())); continue
            break
    return None, errs


def run_window(be, files, state, K, c, rng, poll, beta, pbits, N_geo):
    # ---- local computation: choose the edit set with the real PQHide embedder (pool = N_geo files)
    t0 = time.perf_counter()
    try:
        S = P.embed_keyed(rng, N_geo, K, beta, SESSION_KEY, 1234, int.from_bytes(os.urandom(max(1, pbits // 8)), "big") % (1 << pbits), pbits)
    except AssertionError:
        raise SystemExit('embed_frame capacity assertion failed: lower --geo-N or raise min K')
    t_local = time.perf_counter() - t0
    idx = [s % len(files) for s in S][:K]
    idx = list(dict.fromkeys(idx))                                   # distinct physical files
    # ---- submission
    before = {}
    for i in idx:
        state[i] += 1; before[i] = state[i] - 1
    texts = {i: "\n".join(f"line {j}" for j in range(state[i] + 1)) for i in idx}
    t1 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=c) as ex:
        res = list(ex.map(lambda i: update_with_retry(be, files[i][0], texts[i]), idx))
    t_submit = time.perf_counter() - t1
    # ---- confirmation (version visible through a separate read)
    t2 = time.perf_counter()
    pend = {i: files[i][1] + state[i] for i in idx}                  # expected minimum version
    conf_errs = []
    with ThreadPoolExecutor(max_workers=c) as ex:
        while pend and time.perf_counter() - t2 < 120:
            items = list(pend)
            got = list(ex.map(lambda i: read_version_with_retry(be, files[i][0]), items))
            for i, (g, e_) in zip(items, got):
                conf_errs += e_
                if g is not None and g >= pend[i]: del pend[i]
            if pend: time.sleep(poll)
    t_conf = time.perf_counter() - t2
    return dict(K=len(idx), c=c, t_local=t_local, t_submit=t_submit, t_confirm=t_conf,
                n_ok=sum(r["ok"] for r in res), n_fail=sum(1 - r["ok"] for r in res),
                retries=sum(r["retries"] for r in res), throttled=sum(r["throttled"] for r in res),
                unconfirmed=len(pend), confirm_errors=dict(__import__('collections').Counter(conf_errs)), call_s=[r["call_s"] for r in res if r["ok"]],
                errors=dict(__import__("collections").Counter(e for r in res for e in r["errs"]))), res


def q(x, p): return float(np.quantile(x, p)) if len(x) else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=300, help="number of test files created (physical pool)")
    ap.add_argument("--K", default="20,60,105"); ap.add_argument("--conc", default="1,4,16")
    ap.add_argument("--reps", type=int, default=5); ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--geo-N", type=int, default=131072, help="pool size used for the LOCAL embedding timing")
    ap.add_argument("--cleanup", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="latency_raw.csv")
    a = ap.parse_args()
    be = DryDrive() if a.dry_run else RealDrive()
    rng = np.random.default_rng(1)
    Ks = [int(x) for x in a.K.split(",")]; Cs = [int(x) for x in a.conc.split(",")]
    folder = be.create_folder("pqhide_latency_test")
    print(f"folder created; creating {a.files} files ...", flush=True)
    files = [be.create_file(folder, f"t{i:04d}.txt", "line 0") for i in range(a.files)]
    state = [0] * a.files
    Kmin_geo = min(Ks)
    beta, pbits_full = P.frame_geometry(a.geo_N, Kmin_geo)
    pbits = pbits_full
    rows, summ = [], []
    HDR = ["c", "K", "rep", "t_local_s", "t_submit_s", "t_confirm_s", "retries", "throttled", "fail", "unconfirmed", "error_classes", "confirm_error_classes"]
    fcsv = open(a.out, "w", newline=""); wcsv = csv.writer(fcsv); wcsv.writerow(HDR); fcsv.flush()
    base = a.out[:-4] if a.out.endswith(".csv") else a.out
    aborted = None

    def write_outputs():
        json.dump(summ, open(base + "_summary.json", "w"), indent=1)
        L = ["\\begin{tabular}{rrrrrrrr}", "\\toprule",
             "$c$ & $K$ & local (ms) & submit (s) & confirm (s) & call p95 (s) & throttled & failures\\\\", "\\midrule"]
        for s_ in summ:
            L.append(f"{s_['c']} & {s_['K']} & {s_['local_ms_median']:.1f} & {s_['submit_s_median']:.2f} & {s_['confirm_s_median']:.2f} & {s_['call_s_p95']:.2f} & {s_['throttled']} & {s_['failures']}\\\\")
        L += ["\\bottomrule", "\\end{tabular}"]
        open(base + "_table.tex", "w").write("\n".join(L) + "\n")

    try:
        for c in Cs:
            for K in Ks:
                W = []
                for r in range(a.reps):
                    w, _ = run_window(be, files, state, K, c, rng, a.poll, beta, pbits, a.geo_N)
                    w["rep"] = r; W.append(w); rows.append(w)
                    wcsv.writerow([w["c"], w["K"], w["rep"], w["t_local"], w["t_submit"], w["t_confirm"], w["retries"], w["throttled"], w["n_fail"], w["unconfirmed"], json.dumps(w["errors"]), json.dumps(w["confirm_errors"])]); fcsv.flush()
                    print(f"c={c:2d} K={K:3d} rep={r}: local {w['t_local']*1e3:.1f} ms  submit {w['t_submit']:.2f} s  confirm {w['t_confirm']:.2f} s  "
                          f"retries {w['retries']} throttled {w['throttled']} fail {w['n_fail']} errors {w['errors']} confirm_errors {w['confirm_errors']}", flush=True)
                allc = [x for w in W for x in w["call_s"]]
                summ.append(dict(c=c, K=K, reps=len(W),
                                 local_ms_median=1e3 * st.median(w["t_local"] for w in W),
                                 submit_s_median=st.median(w["t_submit"] for w in W), submit_s_max=max(w["t_submit"] for w in W),
                                 confirm_s_median=st.median(w["t_confirm"] for w in W),
                                 call_s_p50=q(allc, .5), call_s_p95=q(allc, .95), call_s_p99=q(allc, .99),
                                 retries=sum(w["retries"] for w in W), throttled=sum(w["throttled"] for w in W),
                                 failures=sum(w["n_fail"] for w in W), unconfirmed=sum(w["unconfirmed"] for w in W)))
                write_outputs()
    except BaseException as e:                       # keep what was measured; never lose completed windows
        aborted = f"{type(e).__name__}: {e}"
        print("\nINTERRUPTED:", aborted, flush=True)
    finally:
        fcsv.close()
        if summ: write_outputs()
        print("\nSUMMARY (medians over reps)\n" + "\n".join(json.dumps(s_) for s_ in summ))
        print(f"files: {a.out}, {base}_summary.json, {base}_table.tex")
        if a.cleanup:
            try: be.delete(folder); print("test folder deleted")
            except Exception as e: print("cleanup failed, delete the folder pqhide_latency_test by hand:", e)
        if aborted: print("RUN INCOMPLETE:", aborted)

if __name__ == "__main__":
    main()
