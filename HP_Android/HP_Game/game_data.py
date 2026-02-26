from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Dict, List, Tuple

STARTING_YEAR = 1368
STARTING_MONTH = 1
# Legacy-kompatibel; das eigentliche Spiel nutzt nun kein hartes Zeitlimit mehr.
MAX_YEARS = 10_000
MAX_PLAYERS = 6
MIN_NAME_LEN = 3
SAVE_FILE = "savegame.json"
SAVE_DIR = "saves"
SAVE_SLOT_COUNT = 6

MONTHS = [
    "Januar",
    "Februar",
    "Maerz",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]

STARTING_CASH = 6000
STARTING_DEBT = 1800
STARTING_REPUTATION = 10
STARTING_AGE = 20

HANSE_PRIVILEG_GOOD = "Getreide"
HANSE_PRIVILEG_QTY = 120
HANSE_PRIVILEG_MONTHS = 12
HANSE_PRIVILEG_DISCOUNT = 0.08

FLEET_SYNERGY_REQUIRED = 2
FLEET_SYNERGY_HULL_MIN = 90
FLEET_SYNERGY_HEUER_REDUCTION = 0.10

ATHERIA_RESONANCE_GROWTH_MAX = 0.95
ATHERIA_RESONANCE_TARGET_MULT = 2.0

DYNASTY_CHILDREN_TARGET = 3
DYNASTY_INHERITANCE_PER_CHILD = 50000
DYNASTY_AGE_LIMIT = 60

SEA_STATES = [
    "tobende See",
    "stuermische See",
    "bewegte See",
    "ruhige See",
    "stille See",
]

SEA_FACTORS: Dict[str, float] = {
    "tobende See": 1.30,
    "stuermische See": 1.18,
    "bewegte See": 1.08,
    "ruhige See": 0.96,
    "stille See": 0.88,
}

CITIES = [
    "Luebeck",
    "Bergen",
    "Toensberg",
    "Warberg",
    "Malmoe",
    "Ystad",
    "Visby",
    "Riga",
    "Novgorod",
]


BASE_GOODS: Dict[str, Dict[str, float]] = {
    "Salz": {"base_price": 40, "volatility": 0.24},
    "Holz": {"base_price": 28, "volatility": 0.16},
    "Pelze": {"base_price": 70, "volatility": 0.30},
    "Getreide": {"base_price": 22, "volatility": 0.20},
    "Tuch": {"base_price": 55, "volatility": 0.24},
    "Hering": {"base_price": 30, "volatility": 0.22},
    "Wein": {"base_price": 78, "volatility": 0.28},
    "Bier": {"base_price": 34, "volatility": 0.20},
}
# Legacy Alias
GOODS = dict(BASE_GOODS)


CENTURY_GOOD_UNLOCKS: Dict[int, Dict[str, Dict[str, float]]] = {
    15: {
        "Hopfen": {"base_price": 52, "volatility": 0.22},
        "Teer": {"base_price": 64, "volatility": 0.18},
    },
    16: {
        "Gewuerze": {"base_price": 110, "volatility": 0.30},
        "Kupfer": {"base_price": 92, "volatility": 0.24},
    },
    17: {
        "Tabak": {"base_price": 88, "volatility": 0.27},
        "Zucker": {"base_price": 96, "volatility": 0.26},
    },
    18: {
        "Kaffee": {"base_price": 104, "volatility": 0.28},
        "Baumwolle": {"base_price": 84, "volatility": 0.22},
    },
    19: {
        "Kohle": {"base_price": 72, "volatility": 0.21},
        "Stahl": {"base_price": 122, "volatility": 0.25},
    },
    20: {
        "Elektronik": {"base_price": 168, "volatility": 0.32},
        "Treibstoff": {"base_price": 140, "volatility": 0.29},
    },
    21: {
        "Seltene Erden": {"base_price": 188, "volatility": 0.33},
        "Mikrochips": {"base_price": 214, "volatility": 0.35},
    },
}

FUTURE_GOOD_TEMPLATES: List[Tuple[str, int, float]] = [
    ("Biofasern", 162, 0.30),
    ("Nanobauteile", 226, 0.34),
    ("Photonik", 204, 0.31),
    ("Quantenkerne", 248, 0.36),
    ("Synthtreibstoff", 188, 0.29),
]


BASE_SHIPYARD: List[Tuple[str, int, int, int]] = [
    ("Grosse Kogge", 180, 5200, 7200),
    ("Holk", 230, 7500, 10200),
    ("Kraier", 300, 10800, 14600),
]
# Legacy Alias
SHIPYARD = list(BASE_SHIPYARD)

CENTURY_SHIP_UNLOCKS: Dict[int, List[Tuple[str, int, int, int]]] = {
    15: [("Karavelle", 340, 13200, 17600)],
    16: [("Karacke", 400, 17800, 22800)],
    17: [("Galeone", 470, 23400, 29400)],
    18: [("Fregatte", 540, 29200, 36200)],
    19: [("Dampfklipper", 620, 35800, 43600)],
    20: [("Stahlschiff", 740, 45200, 54800)],
    21: [("Containerfrachter", 900, 62000, 76000)],
}


CITY_PRICE_BIAS = {
    "Luebeck": {"Salz": 1.00, "Holz": 0.94, "Pelze": 1.16, "Getreide": 0.98, "Tuch": 1.02, "Hering": 1.05, "Wein": 1.10},
    "Bergen": {"Salz": 1.12, "Holz": 0.92, "Pelze": 0.90, "Getreide": 1.10, "Tuch": 1.04, "Hering": 0.84, "Wein": 1.16},
    "Toensberg": {"Salz": 1.06, "Holz": 0.90, "Pelze": 0.94, "Getreide": 1.08, "Tuch": 1.06, "Hering": 0.88, "Wein": 1.14},
    "Warberg": {"Salz": 1.04, "Holz": 0.92, "Pelze": 0.96, "Getreide": 1.04, "Tuch": 1.00, "Hering": 0.94, "Wein": 1.08},
    "Malmoe": {"Salz": 0.96, "Holz": 1.04, "Pelze": 1.10, "Getreide": 0.94, "Tuch": 1.02, "Hering": 0.98, "Wein": 1.06},
    "Ystad": {"Salz": 0.94, "Holz": 1.06, "Pelze": 1.12, "Getreide": 0.92, "Tuch": 1.00, "Hering": 0.96, "Wein": 1.08},
    "Visby": {"Salz": 1.08, "Holz": 1.02, "Pelze": 1.00, "Getreide": 0.96, "Tuch": 0.98, "Hering": 0.90, "Wein": 1.02},
    "Riga": {"Salz": 1.16, "Holz": 0.88, "Pelze": 0.86, "Getreide": 1.14, "Tuch": 1.10, "Hering": 0.96, "Wein": 1.20},
    "Novgorod": {"Salz": 1.20, "Holz": 0.84, "Pelze": 0.78, "Getreide": 1.16, "Tuch": 1.14, "Hering": 1.02, "Wein": 1.24},
}


BASE_TITLE_STEPS: List[Tuple[int, str, str]] = [
    (0, "Buerger", "Buergerin"),
    (9000, "Haendler", "Haendlerin"),
    (15000, "Kaufmann", "Kauffrau"),
    (23000, "Grosskaufmann", "Grosskauffrau"),
    (34000, "Patrizier", "Patrizierin"),
    (47000, "Bruder", "Schwester"),
    (62000, "Junker", "Edelfrau"),
    (82000, "Diplomat", "Diplomatin"),
    (105000, "Schaffer", "Schafferin"),
    (135000, "Ratsherr", "Ratsfrau"),
    (170000, "Senator", "Senatorin"),
]
# Legacy Alias
TITLE_STEPS = list(BASE_TITLE_STEPS)

CENTURY_TITLE_UNLOCKS: Dict[int, List[Tuple[int, str, str]]] = {
    15: [(220000, "Buergermeister", "Buergermeisterin"), (280000, "Landvogt", "Landvoegtin")],
    16: [(350000, "Freiherr", "Freifrau"), (430000, "Magnat", "Magnatin")],
    17: [(520000, "Reichskaufmann", "Reichskauffrau"), (620000, "Oberrat", "Oberraetin")],
    18: [(730000, "Kommodore", "Kommodorin"), (850000, "Handelsfuerst", "Handelsfuerstin")],
    19: [(980000, "Industriebaron", "Industriebaronin"), (1120000, "Stadthalter", "Stadthalterin")],
    20: [(1270000, "Wirtschaftsrat", "Wirtschaftsraetin"), (1450000, "Globalhaendler", "Globalhaendlerin")],
    21: [(1640000, "Aether-Konsul", "Aether-Konsulin"), (1860000, "Sternenkaufmann", "Sternenkauffrau")],
}

FUTURE_TITLE_NAMES: List[Tuple[str, str]] = [
    ("Welthandelsmeister", "Welthandelsmeisterin"),
    ("Hochkonsul", "Hochkonsulin"),
    ("Aether-Magnat", "Aether-Magnatin"),
    ("Grosspatron", "Grosspatronin"),
    ("Reichsverwalter", "Reichsverwalterin"),
]


WEAPON_TIERS_BY_CENTURY: Dict[int, Dict[str, float | int | str]] = {
    14: {"name": "Schwenkbombarden", "cannon_cost": 500, "cannon_power": 1.00, "max_bonus": 0},
    15: {"name": "Bronze-Kartaunen", "cannon_cost": 620, "cannon_power": 1.14, "max_bonus": 2},
    16: {"name": "Kartaunen", "cannon_cost": 780, "cannon_power": 1.30, "max_bonus": 4},
    17: {"name": "Langrohr-Kanonen", "cannon_cost": 980, "cannon_power": 1.48, "max_bonus": 6},
    18: {"name": "Granatkanonen", "cannon_cost": 1210, "cannon_power": 1.67, "max_bonus": 8},
    19: {"name": "Stahlgeschuetze", "cannon_cost": 1490, "cannon_power": 1.90, "max_bonus": 11},
    20: {"name": "Turmkanonen", "cannon_cost": 1820, "cannon_power": 2.15, "max_bonus": 14},
    21: {"name": "Railkanonen", "cannon_cost": 2200, "cannon_power": 2.45, "max_bonus": 18},
}


def year_to_century(year: int) -> int:
    year_i = max(1, int(year))
    return ((year_i - 1) // 100) + 1


def _stable_unit(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], byteorder="big")
    return (value % 10_000_000) / 10_000_000.0


def city_good_bias(city: str, good_name: str) -> float:
    city_bias = CITY_PRICE_BIAS.get(city, {})
    if good_name in city_bias:
        return float(city_bias[good_name])
    # Fuer neue Gueter pro Stadt stabilen, aber leicht unterschiedlichen Marktcharakter erzeugen.
    unit = _stable_unit(f"{city}:{good_name}")
    return round(0.84 + unit * 0.40, 2)


def _generated_good_for_century(century: int) -> Dict[str, Dict[str, float]]:
    idx = max(0, century - 22)
    base_name, base_price, base_volatility = FUTURE_GOOD_TEMPLATES[idx % len(FUTURE_GOOD_TEMPLATES)]
    tier = idx // len(FUTURE_GOOD_TEMPLATES)
    price_scale = 1.0 + idx * 0.08 + tier * 0.03
    name = f"{base_name} C{century}"
    return {
        name: {
            "base_price": int(round(base_price * price_scale)),
            "volatility": min(0.60, base_volatility + idx * 0.005),
        }
    }


@lru_cache(maxsize=None)
def goods_for_century(century: int) -> Dict[str, Dict[str, float]]:
    century_i = max(14, int(century))
    goods: Dict[str, Dict[str, float]] = {name: dict(values) for name, values in BASE_GOODS.items()}
    for current_century in range(15, century_i + 1):
        unlocks = CENTURY_GOOD_UNLOCKS.get(current_century)
        if unlocks:
            for name, values in unlocks.items():
                goods[name] = dict(values)
        elif current_century > max(CENTURY_GOOD_UNLOCKS):
            goods.update(_generated_good_for_century(current_century))
    return goods


def goods_for_year(year: int) -> Dict[str, Dict[str, float]]:
    return goods_for_century(year_to_century(year))


def goods_unlocked_in_century(century: int) -> List[str]:
    if century in CENTURY_GOOD_UNLOCKS:
        return list(CENTURY_GOOD_UNLOCKS[century].keys())
    if century > max(CENTURY_GOOD_UNLOCKS):
        return list(_generated_good_for_century(century).keys())
    return []


def _generated_ship_for_century(century: int) -> List[Tuple[str, int, int, int]]:
    extra = max(0, century - 21)
    capacity = 900 + extra * 70
    value = 62000 + extra * 9800
    cost = int(round(value * 1.22))
    return [(f"Expeditionsklasse C{century}", capacity, value, cost)]


@lru_cache(maxsize=None)
def shipyard_for_century(century: int) -> List[Tuple[str, int, int, int]]:
    century_i = max(14, int(century))
    ships: List[Tuple[str, int, int, int]] = list(BASE_SHIPYARD)
    for current_century in range(15, century_i + 1):
        unlocks = CENTURY_SHIP_UNLOCKS.get(current_century)
        if unlocks:
            ships.extend(unlocks)
        elif current_century > max(CENTURY_SHIP_UNLOCKS):
            ships.extend(_generated_ship_for_century(current_century))
    return ships


def shipyard_for_year(year: int) -> List[Tuple[str, int, int, int]]:
    return shipyard_for_century(year_to_century(year))


def ships_unlocked_in_century(century: int) -> List[Tuple[str, int, int, int]]:
    if century in CENTURY_SHIP_UNLOCKS:
        return list(CENTURY_SHIP_UNLOCKS[century])
    if century > max(CENTURY_SHIP_UNLOCKS):
        return _generated_ship_for_century(century)
    return []


def _generated_titles_for_century(century: int, prev_threshold: int) -> List[Tuple[int, str, str]]:
    idx = max(0, century - 22)
    step = 220000 + idx * 32000
    male, female = FUTURE_TITLE_NAMES[idx % len(FUTURE_TITLE_NAMES)]
    return [(prev_threshold + step, f"{male} C{century}", f"{female} C{century}")]


@lru_cache(maxsize=None)
def title_steps_for_century(century: int) -> List[Tuple[int, str, str]]:
    century_i = max(14, int(century))
    titles: List[Tuple[int, str, str]] = list(BASE_TITLE_STEPS)
    for current_century in range(15, century_i + 1):
        unlocks = CENTURY_TITLE_UNLOCKS.get(current_century)
        if unlocks:
            titles.extend(unlocks)
        elif current_century > max(CENTURY_TITLE_UNLOCKS):
            titles.extend(_generated_titles_for_century(current_century, titles[-1][0]))
    return titles


def title_steps_for_year(year: int) -> List[Tuple[int, str, str]]:
    return title_steps_for_century(year_to_century(year))


def titles_unlocked_in_century(century: int) -> List[Tuple[int, str, str]]:
    if century in CENTURY_TITLE_UNLOCKS:
        return list(CENTURY_TITLE_UNLOCKS[century])
    if century > max(CENTURY_TITLE_UNLOCKS):
        prev = title_steps_for_century(century - 1)
        return _generated_titles_for_century(century, prev[-1][0])
    return []


def weapon_profile_for_century(century: int) -> Dict[str, float | int | str]:
    century_i = max(14, int(century))
    profile = WEAPON_TIERS_BY_CENTURY.get(century_i)
    if profile:
        return dict(profile)
    if century_i > max(WEAPON_TIERS_BY_CENTURY):
        idx = century_i - max(WEAPON_TIERS_BY_CENTURY)
        base = WEAPON_TIERS_BY_CENTURY[max(WEAPON_TIERS_BY_CENTURY)]
        return {
            "name": f"Aether-Lanzen C{century_i}",
            "cannon_cost": int(base["cannon_cost"]) + idx * 420,
            "cannon_power": float(base["cannon_power"]) + idx * 0.22,
            "max_bonus": int(base["max_bonus"]) + idx * 3,
        }
    return dict(WEAPON_TIERS_BY_CENTURY[14])


def weapon_profile_for_year(year: int) -> Dict[str, float | int | str]:
    return weapon_profile_for_century(year_to_century(year))


def max_cannons_for_ship(ship_name: str, cargo_capacity: int, year: int) -> int:
    profile = weapon_profile_for_year(year)
    base = max(4, min(24, int(cargo_capacity) // 34))
    name = ship_name.lower()
    if "freg" in name or "galeon" in name:
        base += 2
    elif "frachter" in name or "kogge" in name:
        base -= 1
    max_bonus = int(profile.get("max_bonus", 0))
    return max(2, min(120, base + max_bonus))
