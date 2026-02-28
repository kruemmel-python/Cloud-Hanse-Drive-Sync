# Hanse Monorepo

Dieses Repository enthaelt mehrere Projekte. Der aktuelle spielerische Schwerpunkt liegt auf `HP_Game` und dem Android-Spiegel in `HP_Android`.

## Enthaltene Teilprojekte

- `HP_Game/`: Hanse: Atheria Edition (CLI + pygame)
- `HP_Android/`: Android-Port der pygame-Version
- `ATHERIA/`: Makrooekonomie-Zulieferer fuer das Hanse-Spiel
- `cloud_hanse/`: separates Webprojekt

## Hanse: Atheria Edition - aktueller Stand

Die pygame-/Android-Version enthaelt derzeit unter anderem:

- dynamische Weltwirtschaft mit echten Stadtinventaren
- Produktionsbetriebe und NPC-Handel
- Stadtgesundheit, Krankheiten, Migration und Steuerkraft
- Beteiligungen, passive Rendite und Stadtrettung
- Fernhandelszonen (Afrika, China, Asien, Amerika, Arktis)
- neue Fernwaren und neue Produktionsketten
- Auto-Modus mit konfigurierbarer Auto-Policy
- GUI-Sprache Deutsch/Englisch
- Hintergrundmusik mit Schalter und Lautstaerke
- automatischen Jahres-Save im aktiven Slot
- CSV-Export

## Start

### Desktop pygame

```bash
python HP_Game/main_pygame.py
```

### CLI

```bash
python HP_Game/main.py
```

## Wichtige Doku

- `HP_Game/SPIELHANDBUCH.md`
- `HP_Game/SPIELANLEITUNG.md`
- `HP_Game/SPIELHANDBUCH.html`
- `HP_Game/SPIELANLEITUNG.html`

## Desktop-Builds

Fuer den pygame-Spielpfad gibt es jetzt einen eigenen Build-Ordner:

- `HP_Game/build/`

Dort enthalten:

- Windows-Build fuer `.exe`
- Ubuntu-/Linux-Build fuer native Binary
- PyInstaller-Spec und Build-README

## Projektlink

`https://github.com/kruemmel-python/Cloud-Hanse-Drive-Sync`
