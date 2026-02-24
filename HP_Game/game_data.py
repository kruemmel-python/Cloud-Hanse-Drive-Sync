from __future__ import annotations

from typing import Dict

STARTING_YEAR = 1368
MAX_YEARS = 25
MAX_PLAYERS = 6
MIN_NAME_LEN = 3
SAVE_FILE = "savegame.json"
SAVE_DIR = "saves"
SAVE_SLOT_COUNT = 6

STARTING_CASH = 6000
STARTING_DEBT = 1800
STARTING_REPUTATION = 10
STARTING_AGE = 20

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

GOODS = {
    "Salz": {"base_price": 40, "volatility": 0.24},
    "Holz": {"base_price": 28, "volatility": 0.16},
    "Pelze": {"base_price": 70, "volatility": 0.30},
    "Getreide": {"base_price": 22, "volatility": 0.20},
    "Tuch": {"base_price": 55, "volatility": 0.24},
    "Hering": {"base_price": 30, "volatility": 0.22},
    "Wein": {"base_price": 78, "volatility": 0.28},
}

SHIPYARD = [
    ("Grosse Kogge", 180, 5200, 7200),
    ("Holk", 230, 7500, 10200),
    ("Kraier", 300, 10800, 14600),
]

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

TITLE_STEPS = [
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
