#!/usr/bin/env python3
"""Collecte longue duree de l'activite d'edition de VOTRE Drive (Drive Activity API v2), en 3 commandes.

  python collect_activity.py scan    [--days 60] [--max-folders 100]     -> classe vos dossiers par activite recente (trouve ou il y a assez d'edits)
  python collect_activity.py collect --folder-id <ID|ALL> --out trace.csv [--since 2026-01-01]   -> ajoute les NOUVEAUX edits a trace.csv (sans doublon)
  python collect_activity.py report  --out trace.csv [--kmin 60] [--bulk 150] [--tz UTC]         -> combien de fenetres exploitables, combien de jours encore

Sortie trace.csv : file_hash, time_utc, by_me  (meme format que export_drive_activity.py ; sel dans salt.txt, a garder PRIVE).
Aucun nom de fichier, contenu, e-mail ou IP n'est ecrit dans trace.csv. `scan` affiche les NOMS de dossiers a l'ecran seulement (rien n'est ecrit sur disque).
Scopes : drive.activity.readonly + drive.metadata.readonly (jeton : token_collect.json). Prerequis : API Drive Activity ET API Drive activees.
Lancement quotidien automatique (Linux) : voir README_collect.md."""
import argparse, collections, csv, datetime as dt, hashlib, json, os, secrets, statistics as st, sys, time
from zoneinfo import ZoneInfo

SCOPES = ["https://www.googleapis.com/auth/drive.activity.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly"]


def services():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    c = Credentials.from_authorized_user_file("token_collect.json", SCOPES) if os.path.exists("token_collect.json") else None
    if not c or not c.valid:
        if c and c.expired and c.refresh_token: c.refresh(Request())
        else: c = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
        open("token_collect.json", "w").write(c.to_json())
    return build("driveactivity", "v2", credentials=c, cache_discovery=False), build("drive", "v3", credentials=c, cache_discovery=False)


def salt():
    if not os.path.exists("salt.txt"): open("salt.txt", "w").write(secrets.token_hex(16))
    return open("salt.txt").read().strip()


def call(req, tries=6):
    from googleapiclient.errors import HttpError
    for k in range(tries):
        try: return req.execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503, 504) and k < tries - 1: time.sleep(2 ** k); continue
            raise
        except (OSError, TimeoutError) as e:                 # transport errors (SSL EOF, reset, timeout)
            if k < tries - 1: time.sleep(2 ** k); continue
            raise


def parse_activities(r, client_side=False):
    """-> list of (file_id, timestamp, by_me) for EDIT events on files (folders skipped)."""
    out = []
    for act in r.get("activities", []):
        if client_side and "edit" not in (act.get("primaryActionDetail") or {}): continue
        ts = act.get("timestamp") or act.get("timeRange", {}).get("endTime")
        if not ts: continue
        me = int(any(a.get("user", {}).get("knownUser", {}).get("isCurrentUser") for a in act.get("actors", [])))
        for t in act.get("targets", []):
            di = t.get("driveItem")
            if di and "driveFile" in di: out.append((di["name"].split("/")[-1], ts, me))
    return out


def query(act_svc, folder, since_iso, max_pages=None):
    flt = "detail.action_detail_case:EDIT" + (f' AND time >= "{since_iso}"' if since_iso else "")
    body = {"filter": flt, "pageSize": 100, "consolidationStrategy": {"none": {}}}
    if folder.upper() != "ALL": body["ancestorName"] = f"items/{folder}"
    client_side, pages = False, 0
    while True:
        try: r = call(act_svc.activity().query(body=body))
        except Exception as e:
            if not client_side and "pageToken" not in body and getattr(getattr(e, "resp", None), "status", 0) >= 500:
                print("  erreur serveur avec le filtre : relecture sans filtre serveur", flush=True)
                client_side = True; body.pop("filter", None); continue
            raise
        pages += 1
        for x in parse_activities(r, client_side): yield x
        tok = r.get("nextPageToken")
        if not tok or (max_pages and pages >= max_pages): return
        body["pageToken"] = tok


def iso_parse(s):
    import re
    return dt.datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00")))


def cmd_scan(a):
    act, drv = services(); since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    folders, tok = [], None
    while len(folders) < a.max_folders:
        r = call(drv.files().list(q="mimeType='application/vnd.google-apps.folder' and trashed=false", pageSize=100, orderBy="modifiedTime desc",
                                  fields="nextPageToken,files(id,name,modifiedTime)", pageToken=tok)); folders += r.get("files", []); tok = r.get("nextPageToken")
        if not tok: break
    folders = folders[:a.max_folders]; print(f"{len(folders)} dossiers examines (les plus recemment modifies), activite des {a.days} derniers jours ...", flush=True)
    rows = []
    for i, f in enumerate(folders, 1):
        byday, ev = collections.defaultdict(set), 0
        try:
            for fid, ts, me in query(act, f["id"], since, max_pages=a.max_pages):
                ev += 1; byday[ts[:10]].add(fid)
        except Exception as e: print(f"  ({f['id']}: {type(e).__name__})"); continue
        if ev: rows.append((max((len(v) for v in byday.values()), default=0), len(byday), ev, f["id"], f["name"]))
        if i % 10 == 0: print(f"  ... {i}/{len(folders)}", flush=True)
    rows.sort(reverse=True)
    print(f"\n{'max fichiers/jour':>18} {'jours actifs':>13} {'edits':>7}  id  nom   (sur {a.days} jours ; limite {a.max_pages} pages par dossier)")
    for mx, nd, ev, fid, nm in rows[:25]: print(f"{mx:>18} {nd:>13} {ev:>7}  {fid}  {nm}")
    print("\nPour PQHide il faut des jours avec au moins ~60 fichiers DISTINCTS modifies (colonne 1), et de preference beaucoup de jours actifs (colonne 2).")
    print("Les NOMS ci-dessus ne sont affiches qu'ici : ne les copiez pas dans le papier.")


def cmd_collect(a):
    act, _ = services(); S = salt(); h = lambda fid: hashlib.sha256((S + fid).encode()).hexdigest()[:16]
    state_p = a.out + ".state.json"; seen, last = set(), None
    if os.path.exists(a.out):
        for r in csv.DictReader(open(a.out)): seen.add((r["file_hash"], r["time_utc"]))
    if os.path.exists(state_p): last = json.load(open(state_p)).get("last_time")
    since = a.since and f"{a.since}T00:00:00Z"
    if last: since = (iso_parse(last) - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")      # 1 jour de recouvrement ; les doublons sont ignores
    print("depuis:", since or "(tout l'historique)", flush=True)
    new, mx = 0, last; new_file = not os.path.exists(a.out)
    with open(a.out, "a", newline="") as f:
        w = csv.writer(f)
        if new_file: w.writerow(["file_hash", "time_utc", "by_me"])
        for fid, ts, me in query(act, a.folder_id, since):
            k = (h(fid), ts)
            if k in seen: continue
            seen.add(k); w.writerow([h(fid), ts, me]); new += 1
            if mx is None or ts > mx: mx = ts
            if new % 500 == 0: f.flush(); print(f"  ... {new} nouveaux edits", flush=True)
    if mx: json.dump({"last_time": mx, "folder": "ALL" if a.folder_id.upper() == "ALL" else "<folder>", "updated": dt.datetime.now(dt.timezone.utc).isoformat()}, open(state_p, "w"))
    print(f"{new} nouveaux edits ajoutes a {a.out} (total {len(seen)})")


def cmd_report(a):
    z = ZoneInfo(a.tz); byday = collections.defaultdict(set); ev = 0
    for r in csv.DictReader(open(a.out)):
        if a.only_me and r["by_me"] != "1": continue
        d = iso_parse(r["time_utc"]).astimezone(z).date(); byday[d].add(r["file_hash"]); ev += 1
    if not byday: sys.exit("trace vide")
    d0, d1 = min(byday), max(byday); span = (d1 - d0).days + 1
    cnt = [len(byday.get(d0 + dt.timedelta(days=i), ())) for i in range(span)]
    bulk = [c for c in cnt if c > a.bulk]; kept = [c for c in cnt if c <= a.bulk]
    good = [c for c in kept if c >= a.kmin]
    print(f"periode {d0} -> {d1} ({span} jours), {ev} edits, {len(byday)} jours avec au moins un edit")
    print(f"jours 'en masse' (> {a.bulk} fichiers distincts), exclus : {len(bulk)}")
    print(f"fichiers distincts par jour (hors masse) : moyenne {st.mean(kept):.2f}, mediane {st.median(kept):.0f}, max {max(kept)}")
    print(f"jours exploitables (>= {a.kmin} fichiers distincts) : {len(good)} sur {len(kept)}")
    target = a.target
    if len(good) >= target: print(f"==> OBJECTIF ATTEINT : {len(good)} fenetres exploitables (cible {target}). Vous pouvez lancer analyze_real_trace.py.")
    elif good:
        rate = len(good) / max(1, len(kept)); need = int((target - len(good)) / rate) + 1
        print(f"==> au rythme actuel ({rate:.2f} jour exploitable par jour), il faut encore environ {need} jours pour {target} fenetres.")
    else: print(f"==> aucune fenetre exploitable : ce dossier est trop peu actif pour PQHide (essayez `scan`, un dossier partage, ou des fenetres plus longues).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scan"); s.add_argument("--days", type=int, default=60); s.add_argument("--max-folders", type=int, default=100); s.add_argument("--max-pages", type=int, default=10)
    c = sp.add_parser("collect"); c.add_argument("--folder-id", required=True); c.add_argument("--out", default="trace.csv"); c.add_argument("--since", default=None, help="YYYY-MM-DD, premiere collecte seulement")
    r = sp.add_parser("report"); r.add_argument("--out", default="trace.csv"); r.add_argument("--kmin", type=int, default=60); r.add_argument("--bulk", type=int, default=150)
    r.add_argument("--tz", default="UTC"); r.add_argument("--target", type=int, default=200); r.add_argument("--only-me", action="store_true")
    a = ap.parse_args(); {"scan": cmd_scan, "collect": cmd_collect, "report": cmd_report}[a.cmd](a)
