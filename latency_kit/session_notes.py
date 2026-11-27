#!/usr/bin/env python3
"""Ecrit notes_sessionN.txt avant une campagne de latence.
Auto : date/heure+fuseau, Python, OS, version du script, presence de error_classes, type d'interface reseau,
       RTT vers www.googleapis.com. Questions : lieu, connexion, fournisseur, compte.
Usage : python session_notes.py N            (questions interactives)
        python session_notes.py N --lieu "City" --connexion Wi-Fi --fai "Provider" --compte gratuit --yes
        python session_notes.py N --isp-lookup   (interroge ipinfo.io : ne note QUE le nom de l'operateur, jamais l'IP)
Aucune adresse IP, aucun identifiant, aucun jeton n'est ecrit."""
import argparse, datetime as dt, os, platform, re, socket, ssl, statistics as st, subprocess, sys, time, json, urllib.request

def iface_type():
    out = []
    try:
        for n in sorted(os.listdir("/sys/class/net")):
            if n == "lo": continue
            try: up = open(f"/sys/class/net/{n}/operstate").read().strip()
            except Exception: up = "?"
            kind = "Wi-Fi" if os.path.isdir(f"/sys/class/net/{n}/wireless") else ("mobile/USB?" if n.startswith(("wwan", "usb", "rmnet")) else "filaire/autre")
            out.append(f"{n}:{kind}:{up}")
    except Exception: pass
    return ", ".join(out) or "non detecte (Windows/macOS : indiquez-le avec --connexion)"

def rtt(host="www.googleapis.com", n=8):
    ts = []
    ctx = ssl.create_default_context()
    for _ in range(n):
        try:
            t = time.perf_counter()
            with socket.create_connection((host, 443), timeout=5) as s:
                ts.append((time.perf_counter() - t) * 1000)
        except Exception: pass
    if not ts: return "injoignable"
    return f"median {st.median(ts):.0f} ms, min {min(ts):.0f}, max {max(ts):.0f} (connexion TCP, {len(ts)}/{n} essais)"

def isp():
    try:
        d = json.load(urllib.request.urlopen("https://ipinfo.io/json", timeout=8))
        return d.get("org", "inconnu")
    except Exception as e: return f"lookup impossible ({type(e).__name__})"

def ask(prompt, default=""):
    v = input(f"{prompt}" + (f" [{default}]" if default else "") + " : ").strip()
    return v or default

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("n"); ap.add_argument("--lieu"); ap.add_argument("--connexion")
    ap.add_argument("--fai"); ap.add_argument("--compte"); ap.add_argument("--isp-lookup", action="store_true")
    ap.add_argument("--script", default="measure_drive_latency.py"); ap.add_argument("--yes", action="store_true", help="ne pose aucune question")
    a = ap.parse_args()
    now = dt.datetime.now().astimezone()
    lieu = a.lieu or (None if a.yes else ask("Lieu (ville/pays)"))
    conn = a.connexion or (None if a.yes else ask("Connexion (Wi-Fi / 4G / cable / autre)"))
    fai = a.fai or (isp() if a.isp_lookup else (None if a.yes else ask("Fournisseur d'acces (nom)")))
    compte = a.compte or (None if a.yes else ask("Type de compte Google (gratuit / Workspace)", "gratuit"))
    has_err = "error_classes" in open(a.script).read() if os.path.exists(a.script) else None
    L = [f"session: {a.n}",
         f"debut: {now.isoformat(timespec='seconds')} (fuseau {now.tzname()}, UTC{now.strftime('%z')})",
         f"lieu: {lieu or 'non renseigne'}", f"connexion declaree: {conn or 'non renseigne'}", f"fournisseur: {fai or 'non renseigne'}",
         f"compte: {compte or 'non renseigne'}", f"interfaces reseau detectees: {iface_type()}",
         f"RTT vers www.googleapis.com: {rtt()}", f"python: {platform.python_version()} ({platform.python_implementation()})",
         f"systeme: {platform.system()} {platform.release()} {platform.machine()}", f"cpu: {os.cpu_count()} coeurs",
         f"script de mesure present: {os.path.exists(a.script)}; colonne error_classes dans le script: {has_err}"]
    try: L.append("charge machine (1 min): %.2f" % os.getloadavg()[0])
    except Exception: pass
    L.append("fin: (a completer a la main ou avec: python session_notes.py %s --fin)" % a.n)
    p = f"notes_session{a.n}.txt"
    open(p, "w").write("\n".join(L) + "\n"); print("\n".join(L)); print("-> ecrit dans", p)

if __name__ == "__main__":
    if "--fin" in sys.argv:
        n = sys.argv[1]; p = f"notes_session{n}.txt"
        s = open(p).read().replace("fin: (a completer", "fin_PLACEHOLDER")
        s = re.sub(r"fin_PLACEHOLDER.*", "fin: " + dt.datetime.now().astimezone().isoformat(timespec="seconds"), s)
        open(p, "w").write(s); print(s)
    else: main()
