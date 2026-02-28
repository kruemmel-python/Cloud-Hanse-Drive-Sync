# HANSE: ATHERIA EDITION - Spielhandbuch

Dokustand: 2026-02-28  
Primarer Spielfokus: `HP_Game/pygame_game.py` und `HP_Android/HP_Game/pygame_game.py`

---

## 1. Projektstatus

Dieses Repository enthaelt mehrere Projekte. Fuer das Hanse-Spiel sind aktuell diese Teile relevant:

- `HP_Game/`: Desktop-Version (CLI + pygame)
- `HP_Android/`: Android-Port der pygame-Version
- `ATHERIA/`: Makrooekonomie-Zulieferer fuer Live-/Fallback-Metriken

Wichtig:

- Die pygame-Version ist der voll ausgestattete Hauptspielpfad.
- Die CLI-Version deckt die Kernsimulation ab, aber nicht alle Komfort- und UI-Funktionen der pygame-Version.
- Die Android-Version folgt funktional der pygame-Version.

---

## 2. Kernfunktionen des Spiels

### 2.1 Handel und Flotte

- Handel mit dynamischen Preisen zwischen Hanse-Staedten
- Stadtlager plus schiffsspezifische Ladung
- Reparaturen, Schiffbau, Schiffsverkauf und Kanonenaufruestung
- Individuelle Schiffsnamen, inklusive Auto-Benennung fuer KI- und Auto-Kaeufe
- Zielpreisvergleich und Preisbindung bei Reisen

### 2.2 Dynamische Weltwirtschaft

- Physische Marktinventare pro Stadt und Ware
- Rezeptbasierte Produktionsbetriebe mit Input/Output, Level und Aktivstatus
- Monatlicher Welt-Tick fuer Produktion, Grundverbrauch und KI-Handel
- NPC-Haendler mit echter Arbitrage-Logik
- Preisbildung mit echter Knappheits-/Ueberflussreaktion

Die Preisformel im Stadtpreise-Fenster ist sichtbar als:

`Basispreis x CityBias x Sea x Makro x Inventory/Scarcity x (local_scarcity_relief) x Drift x Bankruptcy`

### 2.3 Stadt- und Gesellschaftssimulation

Jede Stadt simuliert heute deutlich mehr als nur einen Markt:

- Bevoelkerung
- Bevoelkerungskapazitaet
- soziale Stabilitaet
- Lebensqualitaet
- Migration
- Steuerkraft
- Infrastruktur
- Institutionen
- Krankheitsdruck
- medizinische Versorgung
- Bankrottstatus

Im Fenster `Stadtpreise` ist dafuer der Block `Stadtgesundheit & Gesellschaft` vorhanden.

### 2.4 Krankheiten und Medizin

- Krankheitsdruck steigt bei Ueberbevoelkerung, schwacher Versorgung und schlechter Stabilitaet.
- Krankenhaeuser, Aerzte und Sanitaerstrukturen wirken direkt auf Stadtgesundheit und Kinderueberleben.
- In spaeteren Jahrhunderten sinkt die Kindersterblichkeit, waehrend die maximale Kinderzahl sinkt.
- Kritische Staedte koennen gezielt ueber `Stiftung` verbessert werden.

### 2.5 Beteiligungen, Einfluss und Stadtrettung

- Pro Betrieb koennen Anteile gekauft werden.
- Daraus entstehen monatliche passive Renditen.
- Der Spieler baut stadtbezogenen politischen Einfluss auf.
- Bankrotte Staedte koennen mit `Stadt retten` stabilisiert werden.
- Sozial-, Forschungs- und Infrastrukturinvestitionen wirken systemisch auf die Welt.

### 2.6 Fernhandel / neue Weltregionen

Die pygame- und Android-Version enthalten zusaetzliche Fernhandelszonen.

Aktuelle Fernziele:

- `Afrika`
- `China`
- `Asien`
- `Amerika`
- `Arktis`

Diese Zonen:

- werden nach Jahrhunderten freigeschaltet
- besitzen eigene Inventare und Produktionsprofile
- liefern neue Fernwaren
- sind in `Schiffsladung` als Reiseziele waehlbar
- sind im Fenster `Stadtpreise` wie normale Handelsknoten einsehbar

Typische neue Waren:

- `Seide`
- `Porzellan`
- `Tee`
- `Silber`
- `Kakao`
- `Rum`
- `Kolonialholz`
- `Kautschuk`
- `Walfett`

Hinweis:

- In Fernhandelszonen koennen keine lokalen Stadtanteile gekauft und keine Bailouts ausgefuehrt werden.
- Diese Knoten sind im Stadtpreise-Fenster sichtbar markiert.

---

## 3. Spielversionen im Projekt

### 3.1 Desktop pygame (empfohlen)

Dateien:

- `HP_Game/main_pygame.py`
- `HP_Game/pygame_game.py`

Diese Version enthaelt die vollstaendige Haupt-UI:

- Markt
- Flotte
- Schiffsladung
- Schiff-Editor
- Stadtpreise
- Missionen
- Spielerinfo
- Save-/Load-Menue
- Einstellungen
- Auto-Policy
- CSV-Export

### 3.2 Android

Dateien:

- `HP_Android/main.py`
- `HP_Android/HP_Game/pygame_game.py`

Die Android-Version spiegelt die pygame-Spielmechanik und verwendet dieselben Datenmodelle.

Zusaetzlich wichtig:

- Bei fehlender externer ATHERIA-Runtime greift automatisch `ATHERIA mobil`.
- Die Musikdatei `Hanse_Atheria.opus` ist auch im Android-Spielpfad vorhanden.

### 3.3 CLI

Dateien:

- `HP_Game/main.py`
- `HP_Game/game.py`

Die CLI-Version bleibt der textbasierte Kernpfad fuer:

- Mehrspieler-Runden (1 bis 6 lokal)
- Grundhandel
- Reisen
- Flottenmanagement
- Missionen
- Save/Load

Nicht alle modernen Komfortfenster der pygame-Version existieren dort in identischer Form.

---

## 4. Start und Installation

### 4.1 Desktop

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
python HP_Game/main_pygame.py
```

### 4.2 CLI direkt starten

```bash
python HP_Game/main.py
```

### 4.3 Android Build

Siehe `HP_Android/README.md`.

---

## 5. Steuerung und wichtige Bedienung

### 5.1 Hotkeys

- `F5`: aktuellen Slot speichern
- `F9`: ausgewaehlten Slot laden
- `F6`: CSV-Export
- `ESC`: Fenster schliessen / zurueck
- `Enter`: Texteingaben bestaetigen
- `Backspace`: Texteingaben loeschen

### 5.2 Scrollbare Bereiche in pygame / Android

Folgende Bereiche sind aktuell scrollbar:

- Marktliste
- Flottenliste
- Schiffsladung: Zielorte
- Schiff-Editor: Kanonenliste
- Stadtpreise: Ortsliste
- Stadtpreise: Warenliste
- Stadtpreise: Betriebsliste
- Stadtpreise: Preisanalyse
- Spielerinfo

Das funktioniert je nach Bereich ueber:

- Mausrad
- Touch-Scroll
- `^` / `v` Buttons

### 5.3 Schiffsladung

Im Fenster `Schiffsladung` kann der Spieler:

- Waren zwischen Stadtlager und Schiff verschieben
- Ziele fuer Reisen waehlen
- sowohl Hanse-Staedte als auch freigeschaltete Fernhandelszonen ansteuern

---

## 6. Wichtige Fenster in der pygame-/Android-Version

### 6.1 Hauptbildschirm

Der Hauptbildschirm zeigt:

- Datum und Seezustand
- Spielername, Geld, Schulden, Gesamtwert
- aktives Schiff inkl. ETA
- ATHERIA-Werte
- Weltzeile mit Produktion, NPC-Deals, Bankrott, Steuern, Migration, Einfluss
- Marktpanel
- Flottenpanel
- Aktionspanel
- Auto-Policy-Leiste
- Chronik / Meldungen

### 6.2 Stadtpreise

Das Fenster `Stadtpreise` ist heute das wichtigste Analysefenster fuer Oekonomie:

- Auswahl aller sichtbaren Staedte und Fernhandelszonen
- Preise und Bestandswerte pro Ware
- vollstaendige Preisanalyse pro ausgewaehlter Ware
- Betriebsliste der gewaehlten Stadt
- Anzeige von Stadtgesundheit, Migration, Steuerkraft und Bankrott
- Schnellaktionen fuer Anteilskauf, Stiftung, Forschung, Reise-Infrastruktur, Marktstabilisierung und Stadtrettung

### 6.3 Einstellungen

Im Einstellungsfenster kann der Spieler aktuell steuern:

- Sprache: `Deutsch` / `Englisch`
- Hintergrundmusik: `An` / `Aus`
- Musiklautstaerke

Die Sprache betrifft die sichtbare UI der pygame-/Android-Version.  
Die Einstellungen werden in `ui_settings.json` gespeichert.

### 6.4 Save-Menue

Das Save-Menue bietet:

- 6 Save-Slots
- Slot-Ueberschreiben
- Laden aus dem aktiven Slot
- `Info`-Button mit Spielinformationen

Angezeigte Spielinformationen:

- Spielname
- Webseite: `https://github.com/kruemmel-python/Cloud-Hanse-Drive-Sync`
- Entwickler: `Ralf Kruemmel`

---

## 7. Auto-Modus und Automatisierung

Der Auto-Modus ist kein reiner Demo-Schalter. Er spielt aktiv fuer den Spieler.

Er uebernimmt:

- Einkauf und Verkauf
- Verladen
- Routenwahl
- Schiffskauf
- Schiffsersatz / Modernisierung
- Kanonenaufruestung
- Investitionen
- Beteiligungskauf (je nach Policy)

### 7.1 Auto-Policy

Die aktuelle Auto-Policy ist im Hauptbildschirm einstellbar:

- Risiko
- Reserve in Mark
- Investitionsstil
- Fokus-Staedte

### 7.2 Wichtige Grenze des Auto-Modus

Der Auto-Modus ist bewusst nicht unsterblich.

Das Handelshaus kann enden durch:

- Tod des Vorfahren ohne gesicherte Nachfolge
- kompletten Flottenverlust
- fehlende Liquiditaet im kritischen Moment

Dafuer gibt es den Button `Nachkommen zeugen`, um Nachfolge aktiv abzusichern.

---

## 8. Speichern, Laden und Jahres-Autosave

- Das Spiel nutzt 6 Slots in `HP_Game/saves/slot_01.json` bis `slot_06.json`.
- Legacy-Saves bleiben ladefaehig.
- Das Spiel speichert zusaetzlich automatisch bei jedem Jahreswechsel in den aktuell aktiven Slot.
- Der aktive Slot wird dabei ueberschrieben.

Enthalten im Save:

- Spielerstatus
- Weltwirtschaft
- NPCs
- ATHERIA-Zustand
- Investitionswerte
- UI-Sprache
- Musikstatus und Lautstaerke

---

## 9. CSV-Export

Der CSV-Export ist fuer externe Auswertung gedacht.

Enthalten sind je nach Spielstand unter anderem:

- Staedte und Fernhandelszonen
- Preise und Inventare
- Betriebe und Status
- Spielerwerte
- Schiffe
- Missionen
- Investitionswirkung

Auf Desktop liegt der Export im Save-Bereich.  
Auf Android wird der Export in den Download-Ordner geschrieben.

---

## 10. ATHERIA-Anbindung

Die Wirtschaft wird durch `HP_Game/atheria_economy.py` erweitert.

Zwei Modi sind moeglich:

- Live-Anbindung an `ATHERIA/main.py`
- robuster Fallback / mobiler ATHERIA-Modus

Dadurch beeinflusst ATHERIA unter anderem:

- Wachstum
- Preisniveau
- Knappheit
- Waren- und Stadtfaktoren

---

## 11. Unterschiede zwischen Dokumentation und Codepfaden

Dieses Handbuch beschreibt den aktuellen Gesamtstand des Hanse-Spiels im Repository.  
Wenn sich Funktionen zwischen CLI und pygame unterscheiden, ist die pygame-/Android-Version massgeblich fuer die volle Featuretiefe.

Kurz gesagt:

- Vollstaendige Komfortfunktionen: pygame / Android
- Textbasierter Kernpfad: CLI

---

## 12. Schnellhilfe bei Problemen

- Schwarzer Bildschirm beim Start: `runtime_error.log` oder Android-Boot-Log pruefen.
- Keine Musik: Mixer/Codec auf dem Zielsystem nicht verfuegbar oder Musik in den Einstellungen deaktiviert.
- Englisch unvollstaendig: Die UI-Sprache betrifft den grafischen Spielpfad; die CLI bleibt ein eigener Textpfad.
- Keine Investitionsbuttons: In Fernhandelszonen sind lokale Stadtaktionen absichtlich deaktiviert.
- Kein Fernziel sichtbar: Die Region muss bereits durch das aktuelle Jahrhundert freigeschaltet sein.

---

## 13. Referenzen

- Hauptspiel: `HP_Game/pygame_game.py`
- Android-Spiegel: `HP_Android/HP_Game/pygame_game.py`
- Datenbasis: `HP_Game/game_data.py`
- Modelle: `HP_Game/models.py`
- ATHERIA-Adapter: `HP_Game/atheria_economy.py`
- Webseite / Projektlink: `https://github.com/kruemmel-python/Cloud-Hanse-Drive-Sync`
