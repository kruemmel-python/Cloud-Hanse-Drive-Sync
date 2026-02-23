# Service-Account Zugriff auf den Drive-Ordner (Cloud Hanse)

Diese Anleitung gilt fuer `python cloud_hanse/server.py`.

Ziel: `world_state.json` im Zielordner lesen/schreiben.

Zielordner:
`https://drive.google.com/drive/folders/16O5AiugmonSzX1pfZ5a5bjZZ4Y_MoRCO`

## 1. Google Cloud

1. Projekt erstellen/waehlen.
2. `Google Drive API` aktivieren.
3. Service-Account erstellen.
4. JSON-Key erzeugen und lokal sichern (nie ins Repo committen).

## 2. Drive-Freigabe

1. Zielordner in Google Drive oeffnen.
2. Service-Account-E-Mail als **Editor** freigeben.

## 3. Wichtiger Quota-Hinweis

Bei persoenlichem My Drive kann ein Service-Account oft **keine neue Datei erstellen**
(`storageQuotaExceeded`).

Praxis fuer dieses Projekt:

- `world_state.json` im Zielordner einmal manuell anlegen **oder**
- Shared Drive verwenden.

Danach kann der Service-Account die bestehende Datei aktualisieren.

## 4. Umgebungsvariable setzen

PowerShell (aktuelle Session):

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_FILE = "D:\secrets\cloud-hanse-service-account.json"
```

Optional fuer Public-Read:

```powershell
$env:GOOGLE_DRIVE_API_KEY = "<api_key>"
# oder
$env:GOOGLE_DRIVE_WORLD_FILE_ID = "<file_id>"
```

## 5. Server starten

```powershell
python cloud_hanse/server.py --host 127.0.0.1 --port 8088
```

UI:
`http://127.0.0.1:8088`

## 6. Funktion pruefen

1. Spieler erstellen, dann handeln.
2. In Drive pruefen, ob `world_state.json` Versionszaehler steigt.

## 7. Typische Fehler

`Drive write unavailable, local cache active`

- Service-Account-Key fehlt/falsch
- Drive-Rechte fehlen
- Netzwerk/API-Probleme

`Drive create fehlgeschlagen ... storageQuotaExceeded`

- Neue Datei via Service-Account in My Drive nicht moeglich
- `world_state.json` manuell anlegen oder Shared Drive nutzen

`403 insufficientPermissions`

- Service-Account nicht als Editor im Zielordner

`404 notFound`

- falsche Ordner-ID / falscher Zugriffspfad

## 8. Sicherheit

- Key-Datei ausserhalb des Repo ablegen
- keinen Key in Git committen
- bei Leak: Key sofort loeschen und neu erstellen
