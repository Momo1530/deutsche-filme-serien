#!/usr/bin/env python3
"""Sprachprüfung + Filter: behält nur Streams mit deutschem Ton.

Liest die erzeugten M3U-Dateien, prüft per ffprobe die Audiosprache
und schreibt nur die deutschen Einträge zurück.

Akzeptiert: deu/ger/german  (deutsche Synchronisation)
Verworfen:  eng, und, andere oder kein deutscher Ton
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
DATEIEN = [HOME / "Filme" / "deutsche-filme.m3u",
           HOME / "Serien" / "deutsche-serien.m3u"]
REPORT = HOME / "Filme" / ".sprachen.json"
WORKERS = 10


def sh(a, t=45):
    try:
        r = subprocess.run(a, capture_output=True, timeout=t)
        return (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return ""


def sprachen(url):
    """Alle Audio-Sprachtags einer Datei."""
    o = sh(["ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type:stream_tags=language",
            "-of", "csv=p=0",
            "-timeout", "15000000", "-rw_timeout", "15000000", url], 50)
    tags = set()
    for l in (o or "").split("\n"):
        if "audio" in l:
            v = l.split(",")[-1].strip().lower()
            tags.add(v or "und")
    return tags


def ist_deutsch(tags):
    return bool(tags & {"deu", "ger", "german", "deutsch"})


def lese(pfad):
    t = pfad.read_text(encoding="utf-8").split("\n")
    out = []
    for i, l in enumerate(t):
        if l.startswith("#EXTINF"):
            u = next((x.strip() for x in t[i + 1:i + 3] if x.strip().startswith("http")), "")
            if u:
                out.append({"extra": l, "url": u})
    return out


def main():
    ziel = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    dateien = [ziel] if ziel else DATEIEN

    cache = {}
    if REPORT.exists():
        try:
            cache = json.loads(REPORT.read_text(encoding="utf-8"))
        except ValueError:
            pass

    for pfad in dateien:
        if not pfad.exists():
            continue
        eintraege = lese(pfad)
        print(f"\n=== {pfad.name}: {len(eintraege)} Einträge ===", flush=True)

        todo = [e for e in eintraege if e["url"] not in cache]
        print(f"   Sprachprüfung: {len(todo)} offen, {len(eintraege)-len(todo)} aus Cache", flush=True)

        def work(e):
            return e["url"], sorted(sprachen(e["url"]))

        if todo:
            with cf.ThreadPoolExecutor(WORKERS) as ex:
                for k, (u, tags) in enumerate(ex.map(work, todo), 1):
                    cache[u] = tags
                    if k % 50 == 0:
                        REPORT.parent.mkdir(parents=True, exist_ok=True)
                        REPORT.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                        print(f"   {k}/{len(todo)}", flush=True)
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

        # Filtern
        de, nicht_de = [], []
        for e in eintraege:
            tags = set(cache.get(e["url"], []))
            (de if ist_deutsch(tags) else nicht_de).append(e)

        # Neu schreiben (Header behalten)
        raw = pfad.read_text(encoding="utf-8").split("\n")
        header = [l for l in raw if l.startswith("#") and l.startswith("#EXTM3U")] or ["#EXTM3U"]
        titel_zeile = [l for l in raw if l.startswith("# ")][:1]
        out = header + titel_zeile
        seen = set()
        for e in de:
            if e["url"] in seen:
                continue
            seen.add(e["url"])
            out += [e["extra"], e["url"]]
        pfad.write_text("\n".join(out) + "\n", encoding="utf-8")

        print(f"   ✓ deutsch: {len(de)} | verworfen: {len(nicht_de)}", flush=True)
        for e in nicht_de[:5]:
            print(f"      ✗ {','.join(cache.get(e['url'],['?'])):12s} {e['extra'].split(',')[-1][:44]}")

    print("\n=== Gesamt ===")
    for pfad in dateien:
        if pfad.exists():
            n = sum(1 for l in pfad.read_text(encoding="utf-8").split("\n") if l.startswith("#EXTINF"))
            print(f"   {pfad.name}: {n} Einträge (nur deutscher Ton)")


if __name__ == "__main__":
    main()
