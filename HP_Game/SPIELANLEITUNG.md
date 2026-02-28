# HANSE: ATHERIA EDITION - Spielanleitung

Kurzfassung fuer den schnellen Einstieg.  
Ausfuehrliche Referenz: `SPIELHANDBUCH.md`

---

## 1. So startest du das Spiel

### Desktop pygame (empfohlen)

```bash
pip install -r requirements.txt
python HP_Game/main_pygame.py
```

### CLI

```bash
python HP_Game/main.py
```

### Android

Starte die APK aus `HP_Android/`.

---

## 2. Was ist neu im aktuellen Projektstand?

- Dynamische Weltwirtschaft mit echten Stadtinventaren
- Produktionsbetriebe und NPC-Handel
- Stadtgesundheit, Krankheiten, Migration und Steuerkraft
- Beteiligungen, passive Rendite und Stadtrettung
- Fernhandelszonen: Afrika, China, Asien, Amerika, Arktis
- Neue Fernwaren und neue Rezeptketten
- Auto-Modus mit Auto-Policy
- Deutsch/Englisch-Umschaltung in der GUI
- Hintergrundmusik mit Schalter und Lautstaerke
- Automatischer Jahres-Save in den aktuellen Slot

---

## 3. Die wichtigsten Fenster

### Hauptbildschirm

Hier steuerst du:

- Kaufen / Verkaufen
- Schiffsladung
- Schiff-Editor
- Schiffbau
- Stadtpreise
- Speichern / Laden
- Auto-Modus
- Missionen
- Einstellungen

### Stadtpreise

Hier siehst du:

- alle Hanse-Staedte
- freigeschaltete Fernhandelszonen
- Warenpreise und Marktbestaende
- Stadtgesundheit & Gesellschaft
- Preisanalyse pro Ware
- Betriebe der Stadt

### Schiffsladung

Hier kannst du:

- Waren verladen
- Ziele waehlen
- Schiffe auch in freigeschaltete Fernhandelszonen senden

### Einstellungen

Hier kannst du:

- die Sprache auf Deutsch oder Englisch stellen
- Hintergrundmusik aktivieren/deaktivieren
- die Musiklautstaerke anpassen

---

## 4. Erste sinnvolle Spielschritte

1. Kaufe guenstige Basiswaren.
2. Verlade sie auf dein Schiff.
3. Vergleiche Zielpreise im Markt.
4. Reise in eine profitablere Stadt.
5. Repariere dein Schiff rechtzeitig.
6. Kaufe spaeter bessere Schiffe und modernisiere Kanonen.
7. Nutze `Stadtpreise`, um kranke oder bankrotte Staedte zu erkennen.
8. Investiere bei Bedarf in `Stiftung`, `Forschung`, `Reise-Infrastruktur` oder `Marktstabilisierung`.

---

## 5. Fernhandel verstehen

Fernhandel wird ueber Jahrhunderte freigeschaltet.  
Diese Ziele verhalten sich wie erweiterte Handelsregionen:

- eigene Lagerbestaende
- eigene Preise
- spezielle Fernwaren
- im Stadtpreise-Fenster sichtbar
- in Schiffsladung als Reiseziele verfuegbar

Lokale Stadtpolitik gilt dort nicht:

- keine Stadtanteile
- keine Bailouts

---

## 6. Auto-Modus

Der Auto-Modus handelt selbststaendig fuer dich.

Er kann:

- Routen waehlen
- kaufen/verkaufen
- Schiffe modernisieren
- Kanonen upgraden
- investieren

Die Auto-Policy legt fest:

- Risiko
- Reserve
- Investitionsstil
- Fokus-Staedte

Wichtig:

- Auto kann das Handelshaus nicht garantieren.
- Sichere Nachfolge bleibt wichtig.
- Nutze `Nachkommen zeugen`, wenn dein Haus abgesichert werden soll.

---

## 7. Speichern und Sicherheit

- 6 Slots stehen zur Verfuegung.
- Jeder Jahreswechsel speichert automatisch in den aktuellen Slot.
- Im Save-Menue gibt es einen `Info`-Button mit Projektinformationen.

---

## 8. Schnelle Problemhilfe

- Keine Musik? Einstellungen pruefen oder Mixer/Codec fehlt.
- Investitionsbuttons grau? In Fernhandelszonen sind manche Stadtaktionen gesperrt.
- Nicht alle Werte sichtbar? In `Stadtpreise`, `Info` und anderen Listen scrollen.
- Kein Fernziel sichtbar? Das Jahrhundert muss die Region schon freigeschaltet haben.

---

## 9. Projektlink

`https://github.com/kruemmel-python/Cloud-Hanse-Drive-Sync`
