#!/usr/bin/env python3
"""Mesure cote DESTINATAIRE : apres qu'une fenetre de K edits a ete envoyee (c workers), combien de temps
faut-il pour que le destinataire VOIE ces K edits, et combien coute un listing ?

Deux vues du destinataire, interrogees en boucle (poll) apres la fin de l'envoi :
  A) Drive Activity API v2 (activity.query, filtre EDIT, ancestorName=dossier)   <- la vue principale (historique d'edits)
  B) Drive API v3 files.list (modifiedTime > debut de fenetre)                   <- vue de reference, moins couteuse
Pour chaque fenetre on enregistre : duree d'envoi, delai de visibilite (fin d'envoi -> les K fichiers vus), nombre de
fichiers jamais vus avant --timeout, duree de chaque appel de listing (pagination incluse), nombre de pages, erreurs.

Scopes : drive.file (creer/modifier ses fichiers de test) + drive.activity.readonly. Token : token_recv.json.
Usage : python recipient_latency.py --files 200 --K 20,60,105 --conc 16 --reps 5 --cleanup --out recv_session1
        python recipient_latency.py --dry-run --files 60 --K 20,40 --reps 2 --poll 0.05 --dry-scale 0.02 --out dry
Sorties : <out>_windows.csv, <out>_polls.csv, <out>_summary.json   (ecrites au fil de l'eau)"""
import argparse, csv, datetime as dt, io, json, os, random, re, statistics as st, threading, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np

SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive.activity.readonly"]
RETRY = (403, 429, 500, 502, 503, 504)


def parse_ts(s):
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
    return dt.datetime.fromisoformat(s)

def iso(t): return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Real:
    def __init__(self): self.tl = threading.local()
    def _svcs(self):
        if not hasattr(self.tl, "d"):
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            c = Credentials.from_authorized_user_file("token_recv.json", SCOPES) if os.path.exists("token_recv.json") else None
            if not c or not c.valid:
                if c and c.expired and c.refresh_token: c.refresh(Request())
                else: c = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
                open("token_recv.json", "w").write(c.to_json())
            self.tl.d = build("drive", "v3", credentials=c, cache_discovery=False)
            self.tl.a = build("driveactivity", "v2", credentials=c, cache_discovery=False)
        return self.tl.d, self.tl.a
    def create_folder(self, name):
        d, _ = self._svcs(); return d.files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
    def create_file(self, folder, name, text):
        from googleapiclient.http import MediaIoBaseUpload
        d, _ = self._svcs(); m = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain")
        return d.files().create(body={"name": name, "parents": [folder]}, media_body=m, fields="id").execute()["id"]
    def update(self, fid, text):                         # returns the SERVER modifiedTime
        from googleapiclient.http import MediaIoBaseUpload
        d, _ = self._svcs(); m = MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain")
        return d.files().update(fileId=fid, media_body=m, fields="id,modifiedTime").execute()["modifiedTime"]
    def activity_list(self, folder, since_iso):          # -> ([(file_id, ts)], pages)
        _, a = self._svcs()
        body = {"ancestorName": f"items/{folder}", "filter": f'detail.action_detail_case:EDIT AND time >= "{since_iso}"',
                "pageSize": 100, "consolidationStrategy": {"none": {}}}
        out, pages = [], 0
        while True:
            r = a.activity().query(body=body).execute(); pages += 1
            for act in r.get("activities", []):
                ts = act.get("timestamp") or act.get("timeRange", {}).get("endTime")
                for t in act.get("targets", []):
                    di = t.get("driveItem")
                    if di and "driveFile" in di and ts: out.append((di["name"].split("/")[-1], ts))
            if not r.get("nextPageToken"): return out, pages
            body["pageToken"] = r["nextPageToken"]
    def files_list(self, folder, since_iso):
        d, _ = self._svcs(); out, pages, tok = [], 0, None
        while True:
            r = d.files().list(q=f"'{folder}' in parents and modifiedTime > '{since_iso}' and trashed=false", pageSize=1000,
                               fields="nextPageToken,files(id,modifiedTime)", pageToken=tok).execute(); pages += 1
            out += [(f["id"], f["modifiedTime"]) for f in r.get("files", [])]
            tok = r.get("nextPageToken")
            if not tok: return out, pages
    def delete(self, fid): self._svcs()[0].files().delete(fileId=fid).execute()
    @staticmethod
    def status_of(e):
        from googleapiclient.errors import HttpError
        return e.resp.status if isinstance(e, HttpError) else None


class Dry:
    """Simulated backend: update ~ lognormal, Activity visibility lag uniform(0, 40 s)*scale, files.list lag uniform(0, 3 s)*scale."""
    def __init__(self, scale=1.0, seed=0):
        self.r = random.Random(seed); self.s = scale; self.ev = []; self.lk = threading.Lock(); self.n = 0
    def create_folder(self, name): return "folder"
    def create_file(self, folder, name, text): self.n += 1; return f"f{self.n}"
    def update(self, fid, text):
        time.sleep(self.r.lognormvariate(-1.6, 0.4) * 0.05 * self.s / 0.05 * 0.05)
        now = dt.datetime.now(dt.timezone.utc)
        with self.lk: self.ev.append((fid, now, now.timestamp() + self.r.uniform(0, 40) * self.s, now.timestamp() + self.r.uniform(0, 3) * self.s))
        return iso(now)
    def activity_list(self, folder, since_iso):
        time.sleep(0.05 * self.s); now = time.time(); lim = parse_ts(since_iso)
        o = [(f, iso(t)) for f, t, va, vf in self.ev if va <= now and t >= lim]; return o, 1 + len(o) // 100
    def files_list(self, folder, since_iso):
        time.sleep(0.02 * self.s); now = time.time(); lim = parse_ts(since_iso)
        o = [(f, iso(t)) for f, t, va, vf in self.ev if vf <= now and t >= lim]; return o, 1
    def delete(self, fid): pass
    @staticmethod
    def status_of(e): return None


def call(be, fn, *a, tries=6):
    """Retry HTTP 403/429/5xx and transport errors with back-off; returns (result, duration_s of the successful attempt, [error classes])."""
    errs = []
    for k in range(tries):
        t = time.perf_counter()
        try:
            r = fn(*a); return r, time.perf_counter() - t, errs
        except Exception as e:
            s = be.status_of(e); errs.append(f"HTTP{s}" if s else type(e).__name__)
            if s in RETRY or s is None: time.sleep(min(16, 2 ** k * 0.25) * (0.5 + random.random())); continue
            raise
    raise RuntimeError("retries exhausted: " + ",".join(errs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=200); ap.add_argument("--K", default="20,60,105"); ap.add_argument("--conc", type=int, default=16)
    ap.add_argument("--reps", type=int, default=5); ap.add_argument("--poll", type=float, default=2.0); ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--gap", type=float, default=5.0, help="pause between windows (s)"); ap.add_argument("--listings", type=int, default=5, help="steady-state listings after each window")
    ap.add_argument("--cleanup", action="store_true"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--dry-scale", type=float, default=1.0)
    ap.add_argument("--out", default="recv"); a = ap.parse_args()
    be = Dry(a.dry_scale) if a.dry_run else Real(); rng = np.random.default_rng(7); Ks = [int(x) for x in a.K.split(",")]
    folder = be.create_folder("pqhide_recipient_test"); print("folder created; creating files ...", flush=True)
    files = [be.create_file(folder, f"r{i:04d}.txt", "line 0") for i in range(a.files)]; state = [0] * a.files
    time.sleep(2 if not a.dry_run else 0)
    fw = open(a.out + "_windows.csv", "w", newline=""); ww = csv.writer(fw)
    ww.writerow(["K", "rep", "start_utc", "t_submit_s", "send_errors", "vis_first_s", "vis_all_s", "seen_all", "n_not_seen", "n_polls",
                 "act_call_s_median", "act_pages_last", "fl_vis_all_s", "fl_seen_all", "fl_call_s_median", "errors"])
    fp = open(a.out + "_polls.csv", "w", newline=""); wp = csv.writer(fp); wp.writerow(["K", "rep", "poll", "t_rel_s", "act_call_s", "act_pages", "act_seen", "fl_call_s", "fl_seen"])
    fl = open(a.out + "_listings.csv", "w", newline=""); wl = csv.writer(fl); wl.writerow(["K", "rep", "i", "act_call_s", "act_pages", "act_events", "fl_call_s", "fl_files"])
    W = []; aborted = None

    def summarize():
        S = []
        for K in Ks:
            B = [w for w in W if w["K"] == K]
            if not B: continue
            va = [w["vis_all_s"] for w in B if w["seen_all"]]; vf = [w["fl_vis_all_s"] for w in B if w["fl_seen_all"]]
            q = lambda x, p: float(np.quantile(x, p)) if x else None
            S.append(dict(K=K, windows=len(B), act_all_seen=len(va), act_vis_all_median_s=q(va, .5), act_vis_all_p95_s=q(va, .95), act_vis_all_max_s=max(va) if va else None,
                          act_not_seen_files=sum(w["n_not_seen"] for w in B), act_call_median_s=st.median(w["act_call_s_median"] for w in B),
                          fl_all_seen=len(vf), fl_vis_all_median_s=q(vf, .5), fl_call_median_s=st.median(w["fl_call_s_median"] for w in B), send_median_s=st.median(w["t_submit_s"] for w in B)))
        json.dump(S, open(a.out + "_summary.json", "w"), indent=1); return S

    try:
        for K in Ks:
            for r in range(a.reps):
                idx = [int(i) for i in rng.choice(a.files, size=K, replace=False)]; fid_set = {files[i] for i in idx}
                for i in idx: state[i] += 1
                texts = {i: "\n".join(f"line {j}" for j in range(state[i] + 1)) for i in idx}
                t_start = dt.datetime.now(dt.timezone.utc); t0 = time.perf_counter(); sub_errs = []
                with ThreadPoolExecutor(max_workers=a.conc) as ex:
                    res = list(ex.map(lambda i: call(be, be.update, files[i], texts[i]), idx))
                t_sub = time.perf_counter() - t0; t_end = time.perf_counter()
                for _, _, e in res: sub_errs += e
                mts = [parse_ts(m) for m, _, _ in res]; ref = iso(min(mts) - dt.timedelta(seconds=1))       # server clock, no local-clock skew
                min_ts = min(mts) - dt.timedelta(seconds=1)
                seen_a, seen_f, first_a, all_a, all_f, calls_a, calls_f, errs, k = {}, {}, None, None, None, [], [], [], 0
                pg_last = 0
                while time.perf_counter() - t_end < a.timeout:
                    k += 1; tr = time.perf_counter() - t_end
                    try:
                        (ev, pg), da, ea = call(be, be.activity_list, folder, ref); (fv, pf), df, ef = call(be, be.files_list, folder, ref)
                    except Exception as e:
                        errs.append(type(e).__name__); time.sleep(a.poll); continue
                    errs += ea + ef; calls_a.append(da); calls_f.append(df); pg_last = pg
                    for f, ts in ev:
                        if f in fid_set and parse_ts(ts) >= min_ts: seen_a.setdefault(f, tr)
                    for f, ts in fv:
                        if f in fid_set: seen_f.setdefault(f, tr)
                    wp.writerow([K, r, k, round(tr, 3), round(da, 3), pg, len(seen_a), round(df, 3), len(seen_f)]); fp.flush()
                    if seen_a and first_a is None: first_a = tr
                    if len(seen_a) == K and all_a is None: all_a = tr
                    if len(seen_f) == K and all_f is None: all_f = tr
                    if all_a is not None and all_f is not None: break
                    time.sleep(a.poll)
                for i in range(a.listings):                                    # steady-state listing cost, window fully visible (or timed out)
                    try:
                        (ev, pg), da, _ = call(be, be.activity_list, folder, ref); (fv, _), df, _ = call(be, be.files_list, folder, ref)
                        wl.writerow([K, r, i, round(da, 3), pg, len(ev), round(df, 3), len(fv)]); fl.flush()
                    except Exception as e: errs.append("listing:" + type(e).__name__)
                w = dict(K=K, rep=r, start_utc=iso(t_start), t_submit_s=t_sub, send_errors=json.dumps(dict(__import__("collections").Counter(sub_errs))),
                         vis_first_s=first_a, vis_all_s=all_a, seen_all=int(all_a is not None), n_not_seen=K - len(seen_a), n_polls=k,
                         act_call_s_median=st.median(calls_a) if calls_a else float("nan"), act_pages_last=pg_last, fl_vis_all_s=all_f, fl_seen_all=int(all_f is not None),
                         fl_call_s_median=st.median(calls_f) if calls_f else float("nan"), errors=json.dumps(dict(__import__("collections").Counter(errs))))
                W.append(w); ww.writerow([w[x] for x in ["K", "rep", "start_utc", "t_submit_s", "send_errors", "vis_first_s", "vis_all_s", "seen_all", "n_not_seen", "n_polls", "act_call_s_median", "act_pages_last", "fl_vis_all_s", "fl_seen_all", "fl_call_s_median", "errors"]]); fw.flush()
                f_ = lambda x: "n/a" if x is None else f"{x:.1f}"
                print(f"K={K:3d} rep={r}: send {t_sub:.1f}s | Activity: first {f_(first_a)} s, all {f_(all_a)} s, not seen {K-len(seen_a)} | files.list: all {f_(all_f)} s | "
                      f"call act {w['act_call_s_median']:.2f}s ({pg_last} p) fl {w['fl_call_s_median']:.2f}s | errors {w['errors']}", flush=True)
                summarize(); time.sleep(a.gap)
    except BaseException as e:
        aborted = f"{type(e).__name__}: {e}"; print("\nINTERRUPTED:", aborted, flush=True)
    finally:
        for f in (fw, fp, fl): f.close()
        S = summarize(); print("\nSUMMARY\n" + "\n".join(json.dumps(s) for s in S)); print(f"files: {a.out}_windows.csv, {a.out}_polls.csv, {a.out}_listings.csv, {a.out}_summary.json")
        if a.cleanup:
            try: be.delete(folder); print("test folder deleted")
            except Exception as e: print("cleanup failed, delete the folder pqhide_recipient_test by hand:", e)
        if aborted: print("RUN INCOMPLETE:", aborted)

if __name__ == "__main__": main()
