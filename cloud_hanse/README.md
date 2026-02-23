# Cloud Hanse (Drive-Sync)

Webbasierte Hanse/Gilde-Wirtschaftssimulation mit globalem `world_state.json`.

## Aktive Features

- Drive-basierter Weltzustand (`world_state.json`)
- Public-Read + Service-Account-Write
- Neuro-Mechanik (`dopamine`, `oxytocin`, `decoq_resonance`, `immunity_level`)
- DeCoG-Guard / Immunantwort
- Sophia-Protokoll fuer NPC-Verhalten
- 5 autonome KI-Haendler
- Web-UI mit Polling

## Wichtige Klarstellung

`cloud_hanse` nutzt **seine eigene Engine** (`cloud_hanse/simulation.py`).
ATHERIA-Meditation/Population-Layer-Features sind hier kein aktiver Laufzeitpfad.

## Start

```bash
python cloud_hanse/server.py --host 127.0.0.1 --port 8088
```

Optional:

```bash
python cloud_hanse/server.py --disable-ai
python cloud_hanse/server.py --ai-interval 10 --ai-seed 42
```

UI: `http://127.0.0.1:8088`

## API

- `GET /api/world`
- `GET /api/diagnostics`
- `POST /api/action/player`
- `POST /api/action/trade`
- `POST /api/action/guild`
- `POST /api/tick`
- `POST /api/validate/decog`

## Drive Setup (Kurzfassung)

Zielordner:
`https://drive.google.com/drive/folders/16O5AiugmonSzX1pfZ5a5bjZZ4Y_MoRCO`

- Lesen: `GOOGLE_DRIVE_API_KEY` oder `GOOGLE_DRIVE_WORLD_FILE_ID`
- Schreiben: `GOOGLE_SERVICE_ACCOUNT_FILE` (oder `GOOGLE_SERVICE_ACCOUNT_JSON`)
- Service-Account muss im Ordner als **Editor** freigegeben sein.

Hinweis zu Service-Accounts auf persoenlichem My Drive:

- Service Accounts haben kein eigenes Storage-Quota fuer neue Dateien in My Drive.
- Daher `world_state.json` im Zielordner vorab anlegen (oder Shared Drive nutzen).

## Schnelltest

```powershell
$r1 = Invoke-RestMethod http://127.0.0.1:8088/api/world
Start-Sleep -Seconds 15
$r2 = Invoke-RestMethod http://127.0.0.1:8088/api/world
$r1.market_view.global_goods.Pelze
$r2.market_view.global_goods.Pelze
$r2.events | Select-Object -Last 12 | Format-Table id,kind,actor_id,at
Invoke-RestMethod http://127.0.0.1:8088/api/diagnostics | ConvertTo-Json -Depth 6
```
