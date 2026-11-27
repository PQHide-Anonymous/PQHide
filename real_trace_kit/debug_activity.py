#!/usr/bin/env python3
"""Diagnostic: query the Drive Activity API WITHOUT any filter and report what comes back.
Usage: python debug_activity.py --folder-id <ID> [--max-pages 5]
Prints only counts by action type and the date range. No names, no content."""
import argparse, collections
from export_drive_activity import creds
from googleapiclient.discovery import build

ap = argparse.ArgumentParser()
ap.add_argument("--folder-id", default="x"); ap.add_argument("--max-pages", type=int, default=5)
ap.add_argument("--no-ancestor", action="store_true", help="query the whole Drive instead of a folder")
a = ap.parse_args()
svc = build("driveactivity", "v2", credentials=creds(), cache_discovery=False)
body = {"pageSize": 100, "consolidationStrategy": {"none": {}}}
if not a.no_ancestor:
    body["ancestorName"] = f"items/{a.folder_id}"
kinds, times, n = collections.Counter(), [], 0
for _ in range(a.max_pages):
    r = svc.activity().query(body=body).execute()
    for act in r.get("activities", []):
        n += 1
        kinds[next(iter(act.get("primaryActionDetail", {}) or {"none": 0}))] += 1
        ts = act.get("timestamp") or act.get("timeRange", {}).get("endTime")
        if ts: times.append(ts)
    if not r.get("nextPageToken"): break
    body["pageToken"] = r["nextPageToken"]
print("activities seen:", n)
print("by primary action:", dict(kinds))
if times: print("from", min(times), "to", max(times))
