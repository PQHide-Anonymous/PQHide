#!/usr/bin/env python3
"""Export EDIT events of a Drive folder (Drive Activity API v2) to an anonymised CSV.

Output columns:  file_hash, time_utc, by_me
 - file_hash : first 16 hex chars of SHA-256(salt + fileId); the salt stays in salt.txt on YOUR machine
 - time_utc  : ISO-8601 time of the edit event
 - by_me     : 1 if the actor is you, 0 otherwise
NO file name, NO content, NO e-mail, NO IP address is written.

Usage:  python export_drive_activity.py --folder-id <FOLDER_ID> --out edits.csv [--since 2025-01-01]
Requires: pip install google-api-python-client google-auth-oauthlib
Status: written from the public API documentation; NOT run against the live API by the author of this kit.
"""
import argparse, csv, hashlib, os, secrets, sys, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive.activity.readonly"]


def creds():
    c = None
    if os.path.exists("token.json"):
        c = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not c or not c.valid:
        if c and c.expired and c.refresh_token:
            c.refresh(Request())
        else:
            c = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
        open("token.json", "w").write(c.to_json())
    return c


def salt():
    if not os.path.exists("salt.txt"):
        open("salt.txt", "w").write(secrets.token_hex(16))
    return open("salt.txt").read().strip()


def call(req, tries=6):
    for k in range(tries):
        try:
            return req.execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503, 504) and k < tries - 1:
                time.sleep(2 ** k); continue
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder-id", required=True)
    ap.add_argument("--out", default="edits.csv")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD (optional)")
    ap.add_argument("--no-server-filter", action="store_true", help="read all activity and keep only edits locally (slower, more robust)")
    a = ap.parse_args()
    svc = build("driveactivity", "v2", credentials=creds(), cache_discovery=False)
    S = salt()
    h = lambda fid: hashlib.sha256((S + fid).encode()).hexdigest()[:16]
    flt = "detail.action_detail_case:EDIT"
    if a.since:
        flt += f" AND time >= \"{a.since}T00:00:00Z\""
    body = {"filter": flt, "pageSize": 100, "consolidationStrategy": {"none": {}}}
    if a.folder_id.upper() != "ALL":                 # --folder-id ALL = whole Drive (all activity of the account)
        body["ancestorName"] = f"items/{a.folder_id}"
    client_side = a.no_server_filter
    if client_side:
        body.pop("filter")
    n = 0; files = set(); since = (a.since + "T00:00:00") if a.since else None
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["file_hash", "time_utc", "by_me"])
        pages = 0
        while True:
            try:
                r = call(svc.activity().query(body=body))
            except HttpError as ex:
                if ex.resp.status >= 500 and not client_side and "pageToken" not in body:
                    print("Server error with the server-side filter: retrying WITHOUT it (edits filtered locally).")
                    client_side = True; body.pop("filter", None); continue
                raise
            pages += 1
            for act in r.get("activities", []):
                if client_side and "edit" not in (act.get("primaryActionDetail") or {}):
                    continue
                ts = act.get("timestamp") or act.get("timeRange", {}).get("endTime")
                if not ts or (since and ts[:19] < since):
                    continue
                me = 0
                for ac in act.get("actors", []):
                    if ac.get("user", {}).get("knownUser", {}).get("isCurrentUser"):
                        me = 1
                for t in act.get("targets", []):
                    di = t.get("driveItem")
                    if not di or "driveFile" not in di:
                        continue                      # skip folders and non-files
                    fid = di["name"].split("/")[-1]
                    w.writerow([h(fid), ts, me]); n += 1; files.add(fid)
            if pages % 20 == 0:
                print(f"... {pages} pages read, {n} edit events so far", flush=True)
            tok = r.get("nextPageToken")
            if not tok:
                break
            body["pageToken"] = tok
    print(f"{n} edit events on {len(files)} files written to {a.out}")


if __name__ == "__main__":
    main()
