# HP_Game

Python-Portierung des vorhandenen HANSE-Programms als spielbare CLI-Neuimplementierung.

## Inhalt

- `main.py`: Einstiegspunkt
- `game.py`: Spiellogik (Markt, Hafen, Reise, Investition, Chronik, Schuldturm, Weltwirtschaft)
- `models.py`: Datenmodelle fuer Spieler, Schiffe, Investitionen, Stadtwirtschaft, NPC-Haendler
- `game_data.py`: Staedte, Waren, Titel, Startwerte, Freischaltungen
- `atheria_economy.py`: ATHERIA-Adapter fuer Wirtschaftswachstum und Rohstoffpreise
- `main_pygame.py` / `pygame_game.py`: grafische Version
- `SPIELHANDBUCH.md`: professionelles Handbuch inkl. eingebetteter Bildassets
- `SPIELHANDBUCH.html`: browserfreundliche Handbuchfassung
- `SPIELANLEITUNG.md` / `SPIELANLEITUNG.html`: aktualisierte Anleitung (alias zum Handbuch)

## Starten

```bash
python HP_Game/main.py
```

Grafische Version (pygame):

```bash
pip install -r HP_Game/requirements-pygame.txt
python HP_Game/main_pygame.py
```

## Spielprinzip

- 1 bis 6 Spieler
- Handel zwischen Hansestaedten
- Kauf und Verkauf von Waren mit dynamischen Preisen und realen Stadtbestaenden
- Stadtlager + schiffsspezifische Ladung (Verladen pro Schiff)
- Schiffsreparaturen, Schiffbau und Kanonenaufruestung im Hafen
- Investitionen mit Risiko
- Zufallsereignisse (Sturm, Kaperangriff, Schuldturm, Familie, Tod)
- Missionen, Dynastie/Nachfolge und Auto-Modus (Atheria-Autopilot)
- Titel-/Waren-/Schiffserweiterung ueber Jahrhunderte (kein hartes Endjahr)

## Dynamische Weltwirtschaft

- Jede Stadt fuehrt ein physisches Markt-Inventory pro Ware.
- Produktionsbetriebe (z. B. Brauerei, Salzmine, Holzfaeller, Fischerei) verarbeiten monatlich Inputs/Outputs.
- NPC-Haendler handeln per Arbitrage zwischen Staedten und bewegen echte Warenmengen.
- Spielerhandel greift auf dieselben Stadtbestaende zu.
- Preisbildung enthaelt einen zusaetzlichen Knappheits-/Ueberflussfaktor aus dem Stadtinventory.
- Monatsreihenfolge: Seezustand -> ATHERIA-Refresh -> Produktion -> NPC-Trades -> Spielerphase.

## ATHERIA-Wirtschaftssystem

Die Oekonomie ist an ATHERIA angebunden. Standard-Pfad:

- integriertes Repo: `../ATHERIA` relativ zu `HP_Game/atheria_economy.py`
- alternativ extern ueber `HP_GAME_ATHERIA_ROOT` (z. B. `D:\ATHERIA`)

- ATHERIA steuert globales Wirtschaftswachstum
- ATHERIA steuert Rohstoffpreisniveau (pro Ware und Stadt)
- Savegames enthalten den ATHERIA-Wirtschaftszustand

Technik:

- Live-Polling ueber `python ATHERIA/main.py demo ...`
- Zwischen den Live-Polls wird die Wirtschaft aus den letzten ATHERIA-Metriken fortgeschrieben
- Falls ATHERIA nicht erreichbar ist, nutzt das Spiel ein internes Fallback-Modell

Voraussetzung fuer Live-Betrieb:

- ATHERIA-Runtime vorhanden (integriert oder extern)
- Abhaengigkeiten installiert (insb. `numpy`, `torch`)

## pygame-Edition

- Datei: `HP_Game/main_pygame.py`
- Fokus auf 1 spielbares Handelshaus mit grafischer Oberflaeche
- Funktionen: Handel, Reisen, Reparatur, Schiffbau, Schiffs-Editor, Missionen, Info-Fenster, Auto-Modus
- Scrollbare Markt- und Flottenlisten (Mausrad, Touch-Drag, Scrollbuttons)
- Heirats-/Kinder-Events inkl. Popup-Flow (auch im Auto-Modus sichtbar)
- Save/Laden auch hier ueber `HP_Game/saves/slot_01.json` bis `slot_06.json`

## Speichern und Laden (Slots)

Das Spiel besitzt ein echtes Savegame-Menue mit mehreren Slots.

- Speicherpfad: `HP_Game/saves/slot_01.json` bis `HP_Game/saves/slot_06.json`
- Beim Start kann ein Slot direkt geladen werden
- Im Spiel kann ueber `Speichern` gezielt ein Slot ueberschrieben werden
- Jeder Slot zeigt eine Kurzvorschau (Jahr, Spieler, Zeitstempel)
- Savepayload enthaelt zusaetzlich `world_economy`, `npcs` und `save_version`.

Legacy-Datei `HP_Game/savegame.json` wird weiterhin als einmaliger Alt-Spielstand erkannt.

## Hinweis

Die Ausgangsbasis liegt als Amiga-Binaerdatei vor. Diese Portierung bildet die zentrale Spielmechanik als moderne Python-CLI nach, ist aber keine bitgenaue Emulation.
