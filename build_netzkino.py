#!/usr/bin/env python3
"""Baut deutsche Filme- und Serien-Playlists aus Netzkino.

Quelle: netzkino.de — kostenlos, legal, werbefinanziert.
Inhalt: INTERNATIONALE Filme/Serien mit DEUTSCHER SYNCHRONISATION
        (Hollywood, Action, Komödie, Horror — wie im deutschen TV).

Ablauf:
  1. Katalog über häufige Wörter abgrasen (die API sucht nur ganze Wörter
     ab 3 Zeichen; ein Buchstabe liefert nichts)
  2. Stream-URL: custom_fields.Streaming ist ein Pfad wie
     'Great_Movies_NK/Action_Theater' → pmd.netzkino-seite.netzkino.de/<slug>.mp4
  3. Jeden Stream per Range-GET prüfen — Referer ist Pflicht
  4. Filme und Serien getrennt schreiben

Ergebnis:
  ~/Filme/deutsche-filme.m3u
  ~/Serien/deutsche-serien.m3u
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import subprocess
import sys
import time
import urllib.parse
from collections import OrderedDict
from pathlib import Path

API = "https://api.netzkino.de.simplecache.net/capi-2.0a"
CDN = "https://pmd.netzkino-seite.netzkino.de/{slug}.mp4"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
REF = "https://www.netzkino.de/"
HOME = Path.home()
OUT_FILM = HOME / "Filme" / "deutsche-filme.m3u"
OUT_SERIE = HOME / "Serien" / "deutsche-serien.m3u"
CACHE = HOME / "Filme" / ".netzkino.json"

WORKERS = 12
MIN = 262144

# Häufige deutsche Wörter + Filmgenres + englische Filmwörter.
# Nur ganze Wörter ab 3 Zeichen bringen Treffer.
WORTE = [
    # deutsche Artikel/Funktionswörter
    "der", "die", "das", "ein", "eine", "und", "nicht", "mit", "von", "für",
    "auf", "aus", "bei", "nach", "über", "unter", "vor", "zur", "zum", "dem",
    "den", "des", "als", "auch", "aber", "wenn", "wie", "wo", "wer", "was",
    "mann", "frau", "kind", "haus", "stadt", "welt", "zeit", "nacht", "tag",
    "jahr", "leben", "tod", "liebe", "krieg", "geld", "blut", "feuer", "wasser",
    "erde", "himmel", "stern", "meer", "insel", "berg", "wald", "reise", "weg",
    "freund", "familie", "bruder", "schwester", "vater", "mutter", "sohn",
    "tochter", "könig", "königin", "prinz", "prinzessin", "ritter", "held",
    "geist", "hexe", "monster", "drache", "teufel", "engel", "gott",
    "geheimnis", "mord", "polizei", "detektiv", "agent", "spion", "gangster",
    "jagd", "rache", "kampf", "sieg", "sturm", "schatten", "dunkel", "licht",
    "letzte", "erste", "grosse", "kleine", "alte", "neue", "junge", "schöne",
    "wild", "frei", "tot", "lebendig", "verloren", "gefangen", "zurück",
    # englische Filmwörter (Titel sind oft englisch)
    "the", "and", "for", "with", "from", "into", "over", "under", "last",
    "night", "day", "man", "woman", "girl", "boy", "king", "queen", "prince",
    "love", "war", "death", "blood", "fire", "water", "earth", "sky", "star",
    "sea", "island", "mountain", "forest", "journey", "road", "friend",
    "family", "brother", "sister", "father", "mother", "son", "daughter",
    "ghost", "witch", "monster", "dragon", "devil", "angel", "god", "secret",
    "murder", "police", "detective", "agent", "spy", "gangster", "hunt",
    "revenge", "fight", "victory", "storm", "shadow", "dark", "light",
    "action", "horror", "comedy", "thriller", "crime", "drama", "western",
    "science", "fiction", "adventure", "fantasy", "mystery", "romance",
    "family", "children", "kids", "movie", "film", "story", "tale", "legend",
    "hero", "villain", "escape", "return", "revenge", "dead", "alive", "lost",
    "trapped", "wild", "free", "great", "small", "old", "new", "young",
    "beautiful", "dark", "evil", "good", "bad", "mad", "crazy", "final",
]


def sh(a, t=30):
    try:
        r = subprocess.run(a, capture_output=True, timeout=t)
        return (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return ""


def suche(term):
    u = f"{API}/search?q={urllib.parse.quote(term)}&d=www"
    o = sh(["curl", "-sL", "-m", "22", "-A", UA, u], 32)
    if not o:
        return []
    try:
        d = json.loads(o)
    except ValueError:
        return []
    return d.get("posts") or []


def clean_title(p):
    t = p.get("title")
    if isinstance(t, dict):
        t = t.get("rendered", "")
    t = re.sub(r"<[^>]+>", "", str(t))
    for a, b in (("&#8211;", "–"), ("&#8217;", "'"), ("&#8222;", "„"),
                 ("&#8220;", "“"), ("&amp;", "&"), ("&#038;", "&")):
        t = t.replace(a, b)
    return t.strip()


def slugs(p):
    f = p.get("custom_fields") or {}
    out = []
    for s in (f.get("Streaming") or []):
        s = (s or "").strip().strip("/")
        if s:
            out.append(s)
    return out


def pruefe(url, t=25):
    o = sh(["curl", "-s", "-o", "/dev/null", "-L", "-m", str(t), "-A", UA,
            "-H", f"Referer: {REF}",
            "-r", f"0-{MIN}", "-w", "%{http_code}|%{size_download}|%{content_type}",
            "--connect-timeout", "10", url], t + 10)
    p = (o or "").strip().split("|")
    if len(p) < 3:
        return False
    try:
        n = int(p[1])
    except ValueError:
        n = 0
    return p[0] in ("200", "206") and n >= MIN and "html" not in (p[2] or "").lower()


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    gef = OrderedDict()
    if CACHE.exists():
        try:
            for k, v in json.loads(CACHE.read_text(encoding="utf-8")).items():
                gef[k] = v
        except ValueError:
            pass

    print(f"Katalog abgrasen ({len(WORTE)} Begriffe) …", flush=True)
    for i, w in enumerate(WORTE, 1):
        posts = suche(w)
        for p in posts:
            t = clean_title(p)
            if not t:
                continue
            for s in slugs(p):
                gef.setdefault(s, t)
        if i % 20 == 0:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(gef, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"   {i}/{len(WORTE)}  Katalog={len(gef)}", flush=True)
        time.sleep(0.12)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(gef, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"   Katalog gesamt: {len(gef)}", flush=True)

    if limit:
        gef = OrderedDict(list(gef.items())[:limit])

    print("Streams prüfen …", flush=True)
    live = []
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        def work(it):
            slug, name = it
            url = CDN.format(slug=slug)
            return {"name": name, "url": url} if pruefe(url) else None
        for k, r in enumerate(ex.map(work, gef.items()), 1):
            if r:
                live.append(r)
            if k % 100 == 0:
                print(f"   {k}/{len(gef)}  live={len(live)}", flush=True)
    print(f"   live: {len(live)} von {len(gef)}", flush=True)
    if not live:
        print("✗ Keine laufenden Streams")
        sys.exit(1)

    ser_re = re.compile(r"\b(Folge|Staffel|Episode|S\d{1,2}E\d{1,3}|Teil\s*\d|"
                        r"Season|Serie)\b", re.I)
    fil = [r for r in live if not ser_re.search(r["name"])]
    ser = [r for r in live if ser_re.search(r["name"])]

    def write(items, path, group, title):
        path.parent.mkdir(parents=True, exist_ok=True)
        seen, out = set(), ["#EXTM3U", f"# {title}"]
        for it in sorted(items, key=lambda x: x["name"].lower()):
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            out += [f'#EXTINF:-1 group-title="{group}",{it["name"]}', it["url"]]
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return len(seen)

    nf = write(fil, OUT_FILM, "Filme (deutsche Synchro)", "Filme — deutsche Synchronisation")
    ns = write(ser, OUT_SERIE, "Serien (deutsche Synchro)", "Serien — deutsche Synchronisation")
    print(f"\n✓ {nf:4d} Filme   → {OUT_FILM}")
    print(f"✓ {ns:4d} Serien  → {OUT_SERIE}")


if __name__ == "__main__":
    main()
