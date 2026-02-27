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
- Erweiterte Questline mit 8 parallelen Missionen (inkl. Braumeisterbund, Nordholz-Vertrag, Routenmeister, Arsenal der Hanse)
- Betriebskampagnen: pro Produktionsbetrieb 8 Queststufen (staffelweise Freischaltung/Belohnung)
- Titel-/Waren-/Schiffserweiterung ueber Jahrhunderte (kein hartes Endjahr)

## Dynamische Weltwirtschaft

- Jede Stadt fuehrt ein physisches Markt-Inventory pro Ware.
- Jede Stadt startet mit mindestens 4 rezeptbasierten Betrieben (u. a. Brauerei, Salzmine, Holzfaeller, Fischerei, Weberei, Gerberei).
- Zusaetzliche Jahrhundert-Betriebe von C15 bis C21 (Hopfenplantage bis Chipfabrik) werden automatisch freigeschaltet.
- NPC-Haendler handeln per Arbitrage zwischen Staedten und bewegen echte Warenmengen.
- Spielerhandel greift auf dieselben Stadtbestaende zu.
- Preisbildung enthaelt einen zusaetzlichen Knappheits-/Ueberflussfaktor aus dem Stadtinventory.
- Beteiligungsmarkt je Stadtbetrieb: Anteilskauf (in %) fuer passive Rendite.
- Politischer Einfluss pro Stadt waechst durch Beteiligungen/Dividenden und ermoeglicht Rettungsfonds gegen Stadtbankrott.
- Werftangebot ist jahrhundertbasiert modernisiert: veraltete Schiffsmodelle sind nicht mehr kaufbar.
- Schiff-Editor erlaubt Kanonenkauf je Waffenstufe (alte und neue Kanonengenerationen).
- Monatsreihenfolge: Seezustand -> ATHERIA-Refresh -> Produktion -> NPC-Trades -> Spielerphase.
- Weltwirtschaft ist im CLI direkt einsehbar (Betriebsliste inkl. Inputs/Outputs, Aktivstatus, Laufbarkeit).
- CSV-Export fuer Excel ist in CLI und pygame verfuegbar (pygame: `F6` / Button).
- Steuer- und Migrationsanzeigen sind im UI kompakt formatiert (`K/M/B/T`) und Save-Werte werden beim Laden sicher begrenzt.
- Auto-Modus priorisiert wieder aktiven Handel (Beladen/Versand) und modernisiert Schiffe nur mit ausreichender Liquiditaetsreserve.
- Auto-Modus bleibt risikobehaftet: Ohne Nachfolge (Tod des Vorfahren) oder bei vollstaendigem Flottenverlust kann das Handelshaus enden.
- Schnellhilfe fuer Nachfolge: Button `Nachkommen zeugen` im Hauptbildschirm (bei verheirateter Figur).
- Verstaendliche Investitionsnamen im UI: `Reise-Infrastruktur` (kuerzere Reisen) und `Marktstabilisierung` (daempft Preisspruenge).

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
