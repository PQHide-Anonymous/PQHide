#!/usr/bin/env python3
"""SIMULATION sur votre Drive : genere dans un dossier de test des fenetres d'edits de deux classes, avec etiquette connue :
   - baseline : edits "naturels" simules (K tire dans une loi a surdispersion ; fichiers choisis selon des poids heterogenes, exposant --hetero ; 0 = uniforme)
   - scheme   : la sortie PQHide (protocol.embed_keyed sur le pool de N fichiers), meme loi de K (comptage fidele)
Chaque fenetre dure --window-s secondes ; les edits sont repartis dans la fenetre. Les VRAIES horloges et l'API Activity enregistrent les evenements.
IMPORTANT : ceci est un comportement SIMULE sur une API reelle (test du pipeline de bout en bout), PAS de l'activite d'utilisateur reel :
            ne jamais le presenter comme tel. Le fichier SIMULATED_DATA_NOTICE.txt est ecrit a cote du manifeste.
Usage : python simulate_on_drive.py --files 300 --windows-per-class 40 --window-s 120 --hetero 1.0 --out sim            (dry : --dry-run)
Sorties : sim_manifest.csv (fenetre, classe, debut/fin UTC, K, n distincts, echecs) ; le dossier de test N'EST PAS supprime (sauf --cleanup) : il faut ensuite l'exporter."""
import argparse, csv, datetime as dt, io, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import os
import protocol as P
SESSION_KEY = os.urandom(32)   # stands for the secret session key K (v3 framing)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def sample_K(rng, kmean, kmin, disp=8):
    lam = rng.gamma(disp, kmean / disp); return max(kmin, int(rng.poisson(lam)))                # negative binomial (mean kmean), floored at kmin

def baseline_weights(N, hetero, rng):
    w = np.arange(1, N + 1, dtype=float) ** (-hetero); rng.shuffle(w); return w / w.sum()

def sample_baseline(rng, N, K, weights): return sorted(int(i) for i in rng.choice(N, size=K, replace=False, p=weights))

def sample_scheme(rng, N, K, beta, pbits):
    return P.embed_keyed(rng, N, K, beta, SESSION_KEY, int(rng.integers(1 << P.SEED_BITS)), int.from_bytes(os.urandom(max(1, pbits // 8)), "big") % (1 << pbits), pbits)


class Real:
    def __init__(self): self.tl = threading.local()
    def _svc(self):
        if not hasattr(self.tl, "s"):
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            c = Credentials.from_authorized_user_file("token_sim.json", SCOPES) if os.path.exists("token_sim.json") else None
            if not c or not c.valid:
                if c and c.expired and c.refresh_token: c.refresh(Request())
                else: c = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
                open("token_sim.json", "w").write(c.to_json())
            self.tl.s = build("drive", "v3", credentials=c, cache_discovery=False)
        return self.tl.s
    def create_folder(self, name): return self._svc().files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
    def create_file(self, folder, name, text):
        from googleapiclient.http import MediaIoBaseUpload
        return self._svc().files().create(body={"name": name, "parents": [folder]}, media_body=MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain"), fields="id").execute()["id"]
    def update(self, fid, text):
        from googleapiclient.http import MediaIoBaseUpload
        self._svc().files().update(fileId=fid, media_body=MediaIoBaseUpload(io.BytesIO(text.encode()), mimetype="text/plain"), fields="id").execute()
    def delete(self, fid): self._svc().files().delete(fileId=fid).execute()

class Dry:
    n = 0
    def create_folder(self, name): return "dryfolder"
    def create_file(self, folder, name, text): Dry.n += 1; return f"f{Dry.n}"
    def update(self, fid, text): time.sleep(0.001)
    def delete(self, fid): pass


def edit(be, fid, text, tries=6):
    for k in range(tries):
        try: be.update(fid, text); return True
        except Exception: time.sleep(min(16, 2 ** k * 0.25) * (0.5 + random.random()))
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=300); ap.add_argument("--windows-per-class", type=int, default=40); ap.add_argument("--window-s", type=float, default=120)
    ap.add_argument("--kmean", type=float, default=70); ap.add_argument("--kmin", type=int, default=50); ap.add_argument("--hetero", type=float, default=1.0)
    ap.add_argument("--spread", type=float, default=0.6, help="fraction of the window over which edits are spread"); ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=11); ap.add_argument("--out", default="sim"); ap.add_argument("--cleanup", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(); rng = np.random.default_rng(a.seed); be = Dry() if a.dry_run else Real()
    beta, pbits = P.frame_geometry(a.files, a.kmin); wts = baseline_weights(a.files, a.hetero, rng)
    open(a.out + "_SIMULATED_DATA_NOTICE.txt", "w").write("These edits were generated by simulate_on_drive.py (simulated behaviour on a real cloud API). They are NOT real user activity.\n")
    folder = be.create_folder("pqhide_sim_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")); print("DOSSIER DE TEST (id a garder pour l'export) :", folder, flush=True)
    files = [be.create_file(folder, f"s{i:04d}.txt", "line 0") for i in range(a.files)]; state = [0] * a.files
    order = ["baseline"] * a.windows_per_class + ["scheme"] * a.windows_per_class; random.Random(a.seed).shuffle(order)
    fm = open(a.out + "_manifest.csv", "w", newline=""); wm = csv.writer(fm); wm.writerow(["window", "class", "start_utc", "end_utc", "K_drawn", "n_distinct", "failed", "folder"])
    try:
        for wi, cls in enumerate(order):
            K = sample_K(rng, a.kmean, a.kmin); K = min(K, a.files - 1)
            S = sample_baseline(rng, a.files, K, wts) if cls == "baseline" else sample_scheme(rng, a.files, K, beta, pbits)
            offs = sorted(rng.uniform(0, a.spread * a.window_s, size=len(S))); t0 = time.perf_counter(); start = dt.datetime.now(dt.timezone.utc); fails = 0
            def job(x):
                i, off = x; time.sleep(max(0, off - (time.perf_counter() - t0))); state[i] += 1
                return edit(be, files[i], "\n".join(f"line {j}" for j in range(state[i] + 1)))
            with ThreadPoolExecutor(max_workers=a.workers) as ex: res = list(ex.map(job, zip(S, offs)))
            fails = res.count(False); time.sleep(max(0, a.window_s - (time.perf_counter() - t0))); end = dt.datetime.now(dt.timezone.utc)
            wm.writerow([wi, cls, start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), end.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), K, len(set(S)), fails, folder]); fm.flush()
            print(f"window {wi+1}/{len(order)} {cls:8s} K={K} distinct={len(set(S))} failed={fails}", flush=True)
    except BaseException as e: print("INTERRUPTED:", type(e).__name__, e, flush=True)
    finally:
        fm.close()
        if a.cleanup:
            try: be.delete(folder); print("dossier de test supprime")
            except Exception as e: print("suppression impossible :", e)
        else: print("Dossier de test conserve. Exportez-le :  python ../real_trace_kit/collect_activity.py collect --folder-id", folder, "--out sim_trace.csv")

if __name__ == "__main__": main()
