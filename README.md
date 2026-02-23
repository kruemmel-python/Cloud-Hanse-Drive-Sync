# Hanse Monorepo (Spielrelevante Uebersicht)

Dieses Repository enthaelt zwei spielbare Systeme:

- `cloud_hanse/`: Webspiel mit Drive-Sync (`python cloud_hanse/server.py`)
- `HP_Game/`: CLI/pygame Einzelspiel mit ATHERIA-Metrikadapter

Der Ordner `ATHERIA/` dient als Runtime-Zulieferer fuer `HP_Game` (Demo-Metriken).

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## Start

Cloud Hanse (Web):

```bash
python cloud_hanse/server.py --host 127.0.0.1 --port 8088
```

HP_Game CLI:

```bash
python HP_Game/main.py
```

HP_Game pygame:

```bash
python HP_Game/main_pygame.py
```

## ATHERIA-Anbindung in HP_Game

- Adapter: `HP_Game/atheria_economy.py`
- Genutzter Runtime-Aufruf: `python ATHERIA/main.py demo --duration ...`
- Optional externer Pfad:

```powershell
$env:HP_GAME_ATHERIA_ROOT = "D:\ATHERIA"
```

## Doku-Hinweis

Diese Repository-Dokumentation ist auf **tatsaechlich genutzte Spielpfade** reduziert.
Nicht genutzte experimentelle Features sind nicht als aktive Spielfunktionen dokumentiert.
