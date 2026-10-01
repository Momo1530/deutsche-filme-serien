#!/usr/bin/env python3
"""Baut die Serien-Playlist: internationale Serien mit deutscher Synchronisation.

Quelle: ARD Mediathek (api.ardmediathek.de) — frei & legal.
Gesucht werden gezielt Serien ausländischer Produktion, die in der ARD
mit deutscher Synchronfassung laufen (Krimis, Dramen, Historisches).

Ergebnis: ~/Serien/deutsche-serien.m3u
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import subprocess
import sys
import time
from pathlib import Path

API = "https://api.ardmediathek.de"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OUT = Path.home() / "Serien" / "deutsche-serien.m3u"
WORKERS = 4
SERIE_TYPEN = ("SEASON_SERIES", "INFINITE_SERIES")

# Internationale Serien, die in der ARD auf Deutsch laufen.
# Nur Titel ausländischer Produktion — keine deutschen Eigenproduktionen.
QUERIES = [
    "Inspector Barnaby", "Kommissar Wallander", "Mankells Wallander",
    "Agatha Christies Poirot", "Kommissar Beck", "Miss Marple",
    "Sherlock Holmes", "Kommissar Maigret", "Maigret", "Montalbano",
    "Kommissarin Lund", "Borgen", "Die Brücke", "Shetland", "Vera",
    "Lewis", "Endeavour", "Father Brown", "Death in Paradise",
    "Downton Abbey", "Call the Midwife", "Poldark", "Outlander",
    "Vikings", "The Last Kingdom", "The Tudors", "Borgia", "Medici",
    "Versailles", "Poirot", "Midsomer", "Rosamunde Pilcher",
    "Inga Lindström", "Herzkino", "Nord bei Nordwest",
]
# Diese Begriffe liefern deutsche Eigenproduktionen → ausschließen
AUSSCHLIESSEN = re.compile(r"Trailer|Making|Doku|Meister der|Macht der Superreichen|"
                           r"Die Chefin|Familie Heinz Becker|Beckenbauer|Like a Loser|"
                           r"Twist|Trump|H2O|Ostfriesen", re.I)


def sh(a, t=45):
    try:
        r = subprocess.run(a, capture_output=True, timeout=t)
        return (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return ""


def suche(term):
    u = (f"{API}/search-system/search/shows/ard?query={term}"
         f"&pageSize=30&platform=MEDIA_THEK&sortingCriteria=SCORE_DESC")
    o = sh(["curl", "-sL", "-m", "22", "-A", UA, u], 32)
    if not o:
        return []
    import json
    try:
        return (json.loads(o) or {}).get("teasers") or []
    except ValueError:
        return []


def getj(u, t=30):
    o = sh(["curl", "-sL", "-m", str(t), "-A", UA, u], t + 10)
    if not o:
        return None
    import json
    try:
        return json.loads(o)
    except ValueError:
        return None


def titel(t):
    return (t.get("shortTitle") or t.get("longTitle") or t.get("mediumTitle")
            or t.get("title") or "").strip()


def links(t):
    L = t.get("links") or {}
    return ((L.get("target") or {}).get("href"),
            (L.get("target") or {}).get("id") or t.get("id"))


def episoden(href):
    d = getj(href + ("&" if "?" in href else "?") + "embedded=true") or {}
    out = []
    for w in d.get("widgets") or []:
        for t in w.get("teasers") or []:
            gh, i = links(t)
            if i and gh:
                out.append({"name": titel(t), "href": gh})
    return out


def stream(href):
    d = getj(href + ("&" if "?" in href else "?") + "devicetype=pc&embedded=true") or {}
    urls = []

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("streams"), list):
                for st in o["streams"]:
                    for m in (st.get("media") or []):
                        if m.get("url"):
                            urls.append(m["url"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
    hls = [u for u in urls if ".m3u8" in u]
    return (hls or urls)[:1]


def pruefe(url, t=22):
    m = sh(["curl", "-sL", "-m", str(t), "-A", UA, url], t + 8)
    if not m:
        return False
    base = url.rsplit("/", 1)[0] + "/"
    var = None
    if "#EXT-X-STREAM-INF" in m:
        best, bw, pend = None, -1, None
        for l in m.split("\n"):
            s = l.strip()
            mm = re.search(r"BANDWIDTH=(\d+)", s)
            if mm:
                pend = int(mm.group(1))
                continue
            if s and not s.startswith("#") and pend is not None:
                if pend > bw:
                    bw, best = pend, s
                pend = None
        if best:
            var = best if best.startswith("http") else base + best
            m = sh(["curl", "-sL", "-m", str(t), "-A", UA, var], t + 8) or m
    seg = next((l.strip() for l in m.split("\n") if l.strip() and not l.startswith("#")), None)
    if not seg:
        return False
    if not seg.startswith("http"):
        seg = (var or url).rsplit("/", 1)[0] + "/" + seg
    o = sh(["curl", "-s", "-o", "/dev/null", "-L", "-m", str(t), "-A", UA,
            "-r", "0-32767", "-w", "%{http_code}|%{size_download}", seg], t + 8)
    p = (o or "").split("|")
    try:
        n = int(p[1])
    except (ValueError, IndexError):
        n = 0
    return p[0] in ("200", "206") and n > 0


def main():
    print(f"Suche internationale Serien in der ARD ({len(QUERIES)} Begriffe) …", flush=True)
    shows = {}
    for q in QUERIES:
        for t in suche(q):
            typ = (t.get("coreAssetType") or "")
            gh, i = links(t)
            nm = titel(t)
            if not (gh and i):
                continue
            if typ and typ not in SERIE_TYPEN:
                continue
            if AUSSCHLIESSEN.search(nm or ""):
                continue
            shows.setdefault(i, {"name": nm, "href": gh})
        time.sleep(0.35)
    print(f"   Serien gefunden: {len(shows)}", flush=True)

    kand = []
    for s in shows.values():
        for e in episoden(s["href"]):
            kand.append({**e, "show": s["name"]})
        time.sleep(0.25)
    print(f"   Episoden: {len(kand)} — Streams prüfen …", flush=True)

    def work(k):
        for h in stream(k["href"]):
            if pruefe(h):
                return {**k, "url": h}
        return None

    live = []
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for n, r in enumerate(ex.map(work, kand), 1):
            if r:
                live.append(r)
            if n % 25 == 0:
                print(f"   {n}/{len(kand)}  live={len(live)}", flush=True)
    print(f"   live: {len(live)}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen, out = set(), ["#EXTM3U", "# Serien — deutsche Synchronisation"]
    for r in live:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        nm = r["name"] if not r["show"] or r["name"].lower().startswith(r["show"].lower()) \
            else f'{r["show"]}: {r["name"]}'
        out += [f'#EXTINF:-1 group-title="Serien (deutsche Synchro)",{nm}', r["url"]]
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n✓ {len(seen)} Serien → {OUT}")


if __name__ == "__main__":
    main()
