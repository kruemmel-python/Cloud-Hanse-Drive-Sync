# ATHERIA Anleitung fuer das Spiel

Diese Anleitung beschreibt **nur** die Funktionen, die vom Spiel genutzt werden.

## Ziel

`HP_Game` soll ATHERIA-Demo-Metriken laden koennen.

Genutzter Aufruf:

```bash
python ATHERIA/main.py demo --duration 0.4 --log-level ERROR
```

## 1. Voraussetzungen

- Python 3.10+
- installierte Abhaengigkeiten (`requirements.txt` im Repo-Root)

## 2. Runtime pruefen

Im Repo-Root:

```bash
python ATHERIA/main.py demo --duration 0.4 --log-level ERROR
```

Erwartung:

- Rueckgabecode `0`
- JSON-Objekt in `stdout`

## 3. Pfadbindung fuer HP_Game

Standardmaessig sucht `HP_Game/atheria_economy.py` an folgenden Orten:

- `../ATHERIA` relativ zu `HP_Game/atheria_economy.py`
- optional `HP_GAME_ATHERIA_ROOT`

Windows PowerShell (optional explizit setzen):

```powershell
$env:HP_GAME_ATHERIA_ROOT = "D:\Amiga_Hanse\HP_Game\GitHub_Repo\ATHERIA"
```

## 4. Spielstart

CLI:

```bash
python HP_Game/main.py
```

pygame:

```bash
python HP_Game/main_pygame.py
```

## 5. Fehlerbilder

`ATHERIA runtime nicht gefunden.`

- Pfad falsch oder `main.py` fehlt im ATHERIA-Ordner.

`ATHERIA Runtime-Fehler (code=...)`

- Demo-Aufruf ist fehlgeschlagen; Demo-Befehl direkt ausfuehren und Fehlertext pruefen.

`ATHERIA JSON konnte nicht gelesen werden.`

- Demo liefert kein valides JSON in `stdout`.

## 6. Hinweis zum Umfang

Diese Anleitung fuehrt bewusst nur die aktive Spielintegration.
