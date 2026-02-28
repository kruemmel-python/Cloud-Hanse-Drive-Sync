# HP_Game

Aktueller Stand des Hanse-Spiels im Repository.

## Spielpfade

- `main.py`: CLI-Kernspiel
- `main_pygame.py`: primarer grafischer Spielpfad
- `pygame_game.py`: voll ausgestattete Desktop-Spielversion
- `HP_Android/HP_Game/pygame_game.py`: Android-Spiegel der pygame-Version

## Der aktuelle Fokus

Die vollstaendige Featuretiefe liegt im pygame-/Android-Pfad:

- dynamische Weltwirtschaft mit Stadtinventaren
- Produktionsbetriebe und NPC-Handel
- Stadtgesundheit, Krankheiten und Migration
- Beteiligungen, passive Rendite und Stadtrettung
- Fernhandelszonen mit neuen Warenketten
- Auto-Modus mit Auto-Policy
- GUI-Sprachumschaltung (Deutsch / Englisch)
- Hintergrundmusik mit Schalter und Lautstaerke
- automatischer Jahres-Save in den aktiven Slot
- CSV-Export

Die CLI-Version bleibt fuer den textbasierten Kern und lokale Mehrspielerpartien erhalten, bildet aber nicht jede GUI-Komfortfunktion identisch ab.

## Starten

### pygame

```bash
pip install -r requirements.txt
python HP_Game/main_pygame.py
```

### CLI

```bash
python HP_Game/main.py
```

## Dokumentation

- `SPIELHANDBUCH.md` / `SPIELHANDBUCH.html`: umfassende Dokumentation
- `SPIELANLEITUNG.md` / `SPIELANLEITUNG.html`: Schnellstart und Bedienhilfe

## Build-Ausgaben fuer Desktop

Es gibt jetzt einen eigenen Build-Ordner:

- `HP_Game/build/`

Dort liegen:

- `hanse_pygame.spec`: PyInstaller-Konfiguration
- `build_windows.ps1`: Windows-Build fuer die `.exe`
- `build_ubuntu.sh`: Ubuntu-/Linux-Build fuer die native Binary
- `README.md`: Build-Hinweise

Typische Ziele:

- Windows: `HP_Game/build/dist/windows/Hanse_Atheria/Hanse_Atheria.exe`
- Ubuntu: `HP_Game/build/dist/linux/Hanse_Atheria/Hanse_Atheria`

## Projektinformationen im Spiel

Das Save-Menue der pygame-Version enthaelt einen `Info`-Button mit:

- Spielname
- Webseite: `https://github.com/kruemmel-python/Cloud-Hanse-Drive-Sync`
- Entwickler: `Ralf Kruemmel`
