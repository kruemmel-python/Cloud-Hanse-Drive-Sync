# Hanse Monorepo (Spielrelevante Uebersicht)

Dieses Repository enthaelt zwei spielbare Systeme:

- `cloud_hanse/`: Webspiel mit Drive-Sync (`python cloud_hanse/server.py`)
- <img width="1024" height="768" alt="web3" src="https://github.com/user-attachments/assets/f4ed9b37-5150-4396-9699-c280f6dc002e" />
<img width="1024" height="768" alt="web2" src="https://github.com/user-attachments/assets/4e8be9e7-8072-4748-b7c2-14f52fccc1f4" />
<img width="1024" height="768" alt="web" src="https://github.com/user-attachments/assets/44d5880e-dc27-46a6-b2ba-8c4a51172370" />


- `HP_Game/`: CLI/pygame Einzelspiel mit ATHERIA-Metrikadapter
<img width="1652" height="1054" alt="desktop3" src="https://github.com/user-attachments/assets/5c907725-7b85-43f5-a02b-27bd158e5716" />
<img width="1652" height="1054" alt="desktop2" src="https://github.com/user-attachments/assets/971fae68-8e85-4e05-b412-174592a1f09b" />
<img width="1652" height="1054" alt="desktop1" src="https://github.com/user-attachments/assets/7aaee5ff-6c26-42ba-8268-fa9f35ad208b" />

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
