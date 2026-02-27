# HP_Android (Android APK Build)

Dieses Verzeichnis enthaelt ein Buildozer-Projekt, das das aktuelle `HP_Game` 1:1 als Android APK verpackt.

Aktuelle App-Konfiguration:
- Titel: `Hanse: Atheria Edition`
- Paket-ID: `org.atheria.hansegame`
- Version: `1.0.0`
- Icon: `assets/icon_launcher.png`
- Presplash: `HP_Game/images/bg_setup.webp`

## Struktur
- `main.py` startet die pygame-Version.
- `buildozer.spec` konfiguriert das Android-Build.
- `HP_Game/` ist eine Kopie der aktuellen Spielquellen inkl. Bilder.
- `scripts/generate_icon.py` erzeugt das quadratische Launcher-Icon.
- `HP_Game/SPIELHANDBUCH.md` enthaelt das vollstaendige Spielhandbuch.
- `HP_Game/SPIELHANDBUCH.html` ist die browserfreundliche Handbuchfassung.
- `HP_Game/SPIELANLEITUNG.md` / `HP_Game/SPIELANLEITUNG.html` enthalten die aktualisierte Anleitung.

## Aktueller Funktionsstand (APK)

- Vollstaendiger Spielablauf wie in `HP_Game` (Handel, Verladen, Reisen, Schiffbau, Kanonen, Missionen).
- Dynamische Weltoekonomie mit echten Stadtinventaren, Produktionsbetrieben und NPC-Haendlern.
- Preise reagieren zusaetzlich auf lokale Knappheit bzw. Ueberfluss je Stadt/Ware.
- `Info`-Button zeigt den kompletten Spielerstatus (Familie, Finanzen, Flotte, Missionsstatus).
- Marktliste ist scrollbar (Mausrad/Touch + Scrollbuttons `^` `v`), damit neue Jahrhundert-Waren sichtbar bleiben.
- Auto-Modus spielt eigenstaendig weiter (Handel, Reisen, Schiffbau/Upgrades) und zeigt Heiratsanfragen als Popup.
- Auto-Progression ist gebremst (Trade-Budget-Anteil, Schiffbau-Cooldown, zeitliches Titel-Gating), damit der Aufstieg stabil bleibt.
- Auto-Modus bleibt risikobehaftet (kein Unsterblichkeitsmodus): ohne Nachfolge oder bei komplettem Flottenverlust endet das Handelshaus.
- Button `Nachkommen zeugen` ist im Hauptscreen verfuegbar, um die Nachfolge aktiv zu sichern.
- Wenn keine externe ATHERIA-Runtime verfuegbar ist, nutzt Android automatisch das mobile ATHERIA-Profil.
- Save-Slots speichern zusaetzlich den Weltzustand (`world_economy`, `npcs`) bei Legacy-kompatiblem Laden.
- Steuer-/Migrationswerte werden kompakt als `K/M/B/T` angezeigt; extrem grosse Altdaten werden beim Laden begrenzt.
- CSV-Export schreibt auf Android in den Download-Ordner statt ins App-internal-Verzeichnis.

Icon neu erzeugen:
```bash
python scripts/generate_icon.py
```

## WSL Build (Debug + Release)
Buildozer ist unter Linux/WSL2 der stabile Weg.

### 1) WSL vorbereiten (Ubuntu)
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git zip unzip openjdk-17-jdk
sudo apt install -y build-essential libssl-dev libffi-dev
sudo apt install -y autoconf automake libtool pkg-config
sudo apt install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
```

### 2) Projekt in WSL-Verzeichnis kopieren
Nicht direkt auf `/mnt/c` bauen (langsamer/fehleranfaelliger).
```bash
mkdir -p ~/projects
cp -r /mnt/d/HANSE_ATHERIA/GitHub_Repo/HP_Android ~/projects/HP_Android
cd ~/projects/HP_Android
```

### 3) Buildozer installieren
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install buildozer cython==0.29.36
```

### 4) Debug APK bauen
```bash
buildozer -v android debug
```
Ergebnis: `bin/*.apk`

### 5) Release APK bauen (unsigned)
```bash
buildozer -v android release
```
Ergebnis: `bin/*-release-unsigned.apk`

### 6) Keystore erzeugen (einmalig)
```bash
keytool -genkeypair -v \
  -keystore hanse-release.keystore \
  -alias hanse_release \
  -keyalg RSA -keysize 4096 -validity 10000
```

### 7) Release APK signieren
```bash
UNSIGNED_APK=$(ls -1 bin/*-release-unsigned.apk | tail -n 1)
BUILD_TOOLS=$(ls -1d .buildozer/android/platform/android-sdk/build-tools/* | sort -V | tail -n 1)

"$BUILD_TOOLS/zipalign" -v -p 4 "$UNSIGNED_APK" bin/hanse-1.0.0-release-aligned.apk
"$BUILD_TOOLS/apksigner" sign \
  --ks hanse-release.keystore \
  --ks-key-alias hanse_release \
  --out bin/hanse-1.0.0-release-signed.apk \
  bin/hanse-1.0.0-release-aligned.apk

"$BUILD_TOOLS/apksigner" verify --verbose --print-certs bin/hanse-1.0.0-release-signed.apk
```

### 8) APK zurueck nach Windows kopieren
```bash
cp bin/hanse-1.0.0-release-signed.apk /mnt/d/HANSE_ATHERIA/GitHub_Repo/HP_Android/bin/
```

## Wichtige Anpassungen
- Paketname: `buildozer.spec` -> `package.domain`/`package.name`
- App-Titel: `buildozer.spec` -> `title`
- Icon/Presplash: `buildozer.spec` -> `icon.filename`/`presplash.filename`
- Release-Typ: `buildozer.spec` -> `android.release_artifact = apk`

## Hinweis
Auf Android nutzt das Spiel automatisch ein eingebettetes ATHERIA-Mobilprofil, wenn der externe Runtime-Aufruf nicht verfuegbar ist.
