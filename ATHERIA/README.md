# ATHERIA (Spielanbindung)

ATHERIA ist in diesem Repository **kein eigenstaendiges Spiel-Backend**,
sondern eine lokale Runtime, aus der `HP_Game/atheria_economy.py` Wirtschaftsmetriken liest.

## Was im Spiel wirklich genutzt wird

`HP_Game` ruft regelmaessig folgendes Kommando auf:

```bash
python ATHERIA/main.py demo --duration 0.4 --log-level ERROR
```

Die JSON-Ausgabe wird geparst und fuer Wachstum/Preisniveau verwendet.

## Verwendete Metriken

Das Spiel nutzt diese Felder aus der Demo-JSON (mit Fallback-Werten):

- `purpose_alignment`
- `morphic_resonance_index`
- `resource_scarcity`
- `selection_pressure`
- `market_guardian_score`
- `market_last_price`
- `fitness_gradient`
- `system_temperature`
- `resource_pool`

## Kurztest

```bash
python ATHERIA/main.py demo --duration 0.4 --log-level ERROR
```

Wenn JSON ausgegeben wird, ist die Runtime fuer `HP_Game` einsatzbereit.
