# Filme & Serien mit deutscher Synchronisation

Internationale Filme und Serien **auf Deutsch synchronisiert** --
also Hollywood- und Auslandsproduktionen, die deutsche Synchronsprecher haben.

## Links

| Liste | Inhalt | Link |
|---|---|---|
| **Filme** | 258 internationale Filme, dt. Synchro | `https://raw.githubusercontent.com/Momo1530/deutsche-filme-serien/main/Filme/deutsche-filme.m3u` |
| **Serien** | Serien, dt. Synchro | `https://raw.githubusercontent.com/Momo1530/deutsche-filme-serien/main/Serien/deutsche-serien.m3u` |

## Quelle

- **Netzkino.de** (Filme) -- kostenlos, legal, werbefinanziert
- **ARD Mediathek** (Serien) -- öffentlich-rechtlich, frei

## Prüfung

Jeder Stream wird getestet:
1. **Erreichbarkeit**: Range-GET ueber 256 KB -- nur echte Bytes zaehlen
2. **Sprache**: ffprobe prueft die Audiospur -- **nur deutscher Ton** (`deu`/`ger`)
   kommt in die Liste, englische Originalfassungen fliegen raus

## Neu bauen

```bash
cd Filme && python3 build_netzkino.py   # Filme holen
python3 filter_deutsch.py               # nur deutschen Ton behalten
python3 build_serien.py                 # Serien
```
