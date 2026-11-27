#!/usr/bin/env python3
"""FALLBACK exporter (Drive API v3 revisions) -> same CSV schema as export_drive_activity.py.
Use it only if the Activity API is not available for your account.
CAUTION: Drive keeps old revisions of NON-Google-format files only for a limited time (about 30 days unless pinned),
so prefer Google Docs/Sheets/Slides, or use the Activity API exporter.
Usage: python export_drive_revisions.py --folder-id <ID> --out edits.csv
Status: NOT run against the live API by the author of this kit.
"""
import argparse, csv, hashlib, os, secrets, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]   # if you get HTTP 403, try drive.readonly


def creds():
    c = None
    if os.path.exists("token_rev.json"):
        c = Credentials.from_authorized_user_file("token_rev.json", SCOPES)
    if not c or not c.valid:
        if c and c.expired and c.refresh_token:
            c.refresh(Request())
        else:
            c = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
        open("token_rev.json", "w").write(c.to_json())
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


def walk(svc, root):
    stack = [root]
    while stack:
        fid = stack.pop(); tok = None
        while True:
            r = call(svc.files().list(q=f"'{fid}' in parents and trashed=false", pageToken=tok,
                                      fields="nextPageToken, files(id,mimeType)", pageSize=1000))
            for f in r.get("files", []):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    stack.append(f["id"])
                elif f["mimeType"] != "application/vnd.google-apps.shortcut":
                    yield f["id"]
            tok = r.get("nextPageToken")
            if not tok:
                break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder-id", required=True); ap.add_argument("--out", default="edits.csv")
    a = ap.parse_args()
    svc = build("drive", "v3", credentials=creds(), cache_discovery=False)
    S = salt(); h = lambda x: hashlib.sha256((S + x).encode()).hexdigest()[:16]
    n = nf = 0
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["file_hash", "time_utc", "by_me"])
        for fid in walk(svc, a.folder_id):
            nf += 1; tok = None
            while True:
                r = call(svc.revisions().list(fileId=fid, pageToken=tok, pageSize=200,
                         fields="nextPageToken, revisions(id,modifiedTime,lastModifyingUser(me))"))
                for rv in r.get("revisions", []):
                    w.writerow([h(fid), rv["modifiedTime"], 1 if rv.get("lastModifyingUser", {}).get("me") else 0]); n += 1
                tok = r.get("nextPageToken")
                if not tok:
                    break
    print(f"{n} revisions on {nf} files written to {a.out}")


if __name__ == "__main__":
    main()
