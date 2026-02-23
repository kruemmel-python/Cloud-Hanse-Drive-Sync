# HP_Game

Python-Portierung des vorhandenen HANSE-Programms als spielbare CLI-Neuimplementierung.

## Inhalt

- `main.py`: Einstiegspunkt
- `game.py`: Spiellogik (Markt, Hafen, Reise, Investition, Chronik, Schuldturm)
- `models.py`: Datenmodelle fuer Spieler, Schiff und Investitionen
- `game_data.py`: Staedte, Waren, Titel, Startwerte
- `atheria_economy.py`: ATHERIA-Adapter fuer Wirtschaftswachstum und Rohstoffpreise
- `main_pygame.py` / `pygame_game.py`: grafische Version

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
- Kauf und Verkauf von Waren mit dynamischen Preisen
- Schiffsreparaturen und Schiffsaufstieg im Hafen
- Investitionen mit Risiko
- Zufallsereignisse (Sturm, Kaperangriff, Schuldturm, Familie, Tod)
- Titelaufstieg bis `Senator/Senatorin`

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
- Funktionen: Handel, Reisen, Reparatur, Jahreswechsel, Save-Slots
- Save/Laden auch hier ueber `HP_Game/saves/slot_01.json` bis `slot_06.json`

## Speichern und Laden (Slots)

Das Spiel besitzt ein echtes Savegame-Menue mit mehreren Slots.

- Speicherpfad: `HP_Game/saves/slot_01.json` bis `HP_Game/saves/slot_06.json`
- Beim Start kann ein Slot direkt geladen werden
- Im Spiel kann ueber `Speichern` gezielt ein Slot ueberschrieben werden
- Jeder Slot zeigt eine Kurzvorschau (Jahr, Spieler, Zeitstempel)

Legacy-Datei `HP_Game/savegame.json` wird weiterhin als einmaliger Alt-Spielstand erkannt.

## Hinweis

Die Ausgangsbasis liegt als Amiga-Binaerdatei vor. Diese Portierung bildet die zentrale Spielmechanik als moderne Python-CLI nach, ist aber keine bitgenaue Emulation.
