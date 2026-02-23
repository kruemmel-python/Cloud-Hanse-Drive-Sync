# ATHERIA Dokumentation (Spielrelevante Schnittstelle)

Diese Datei dokumentiert den **tatsaechlichen Vertrag** zwischen `HP_Game` und `ATHERIA`.

## 1. Aufrufer

- Datei: `HP_Game/atheria_economy.py`
- Klasse: `AtheriaEconomyEngine`

## 2. Externer Prozessaufruf

`AtheriaEconomyEngine._fetch_live_metrics()` startet:

```bash
python ATHERIA/main.py demo --duration <sekunden> --log-level ERROR
```

Wichtige Parameter aus dem Engine-Code:

- `demo_duration_seconds` (Default `0.4`)
- `timeout_seconds` (Default `25.0`)

## 3. Erwartete Ausgabe

- Ein JSON-Objekt in `stdout`
- Das erste gueltige JSON-Objekt wird geparst (`_extract_first_json_object`)

## 4. Im Spiel verwendete Felder

Die Oekonomie zieht u. a. folgende Metriken:

- `purpose_alignment`
- `morphic_resonance_index`
- `resource_scarcity`
- `selection_pressure`
- `market_guardian_score`
- `market_last_price`
- `fitness_gradient`
- `system_temperature`
- `resource_pool`

Fehlende Felder werden mit Fallback-Werten verarbeitet.

## 5. Wie diese Werte im Spiel wirken

`HP_Game/atheria_economy.py` berechnet daraus:

- `global_growth`
- `global_price_level`
- `resource_scarcity`
- warenspezifische Faktoren (`good_factors`)
- stadtbezogene Faktoren (`city_factors`)

Diese Faktoren fliessen in die Marktpreise pro Jahr ein.

## 6. Minimaler Integrationstest

```bash
python ATHERIA/main.py demo --duration 0.4 --log-level ERROR
python HP_Game/main.py
```

Wenn der Demo-Aufruf JSON liefert und `HP_Game` laeuft, ist die Schnittstelle intakt.
