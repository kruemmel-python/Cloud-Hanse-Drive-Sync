# HP_Game Build

Dieser Ordner enthaelt die Build-Struktur fuer den grafischen Spielpfad (`main_pygame.py`).

## Zielplattformen

- Windows: `.exe`
- Ubuntu / Linux: ELF-Binary im Dist-Ordner

Wichtig:

- PyInstaller erzeugt immer auf dem **aktuellen Betriebssystem** die passende Zielplattform.
- Eine Windows-`.exe` wird auf Windows gebaut.
- Eine Ubuntu-/Linux-Binary wird auf Ubuntu/Linux gebaut.

## Voraussetzungen

```bash
python -m pip install -r HP_Game/requirements-pygame.txt
python -m pip install -r HP_Game/build/requirements-build.txt
```

## Windows-Build

```powershell
pwsh -File HP_Game/build/build_windows.ps1
```

Ergebnis:

- `HP_Game/build/dist/windows/Hanse_Atheria/Hanse_Atheria.exe`

## Ubuntu-Build

```bash
chmod +x HP_Game/build/build_ubuntu.sh
./HP_Game/build/build_ubuntu.sh
```

Ergebnis:

- `HP_Game/build/dist/linux/Hanse_Atheria/Hanse_Atheria`

## Enthaltene Assets

Die Build-Konfiguration packt mit ein:

- `images/`
- `Hanse_Atheria.ogg`
- `Hanse_Atheria.opus`
- `SPIELHANDBUCH.html`
- `SPIELANLEITUNG.html`

Die Laufzeitpfade im Spiel wurden fuer gefrorene Builds angepasst:

- Assets werden auch aus PyInstaller-Bundles geladen.
- Savegames liegen in gefrorenen Builds nicht im Bundle selbst, sondern in einem benutzerbeschreibbaren Datenordner.

## Hinweis zur Musik

Fuer Desktop-Builds ist `Hanse_Atheria.ogg` der robustere Standard.  
`Hanse_Atheria.opus` bleibt zusaetzlich enthalten, falls das Zielsystem es unterstuetzt.
