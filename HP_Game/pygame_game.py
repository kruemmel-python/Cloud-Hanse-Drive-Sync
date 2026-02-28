from __future__ import annotations

import csv
import json
import os
import hashlib
import math
import random
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pygame

from atheria_economy import AtheriaEconomyEngine, EconomyState
import game_data as _gd

CITIES = _gd.CITIES
REMOTE_TRADE_REGIONS = _gd.REMOTE_TRADE_REGIONS
city_good_bias = _gd.city_good_bias
goods_for_year = _gd.goods_for_year
goods_unlocked_in_century = _gd.goods_unlocked_in_century
max_cannons_for_ship = _gd.max_cannons_for_ship
remote_regions_for_year = _gd.remote_regions_for_year
MIN_NAME_LEN = _gd.MIN_NAME_LEN
MONTHS = _gd.MONTHS
HANSE_PRIVILEG_GOOD = _gd.HANSE_PRIVILEG_GOOD
HANSE_PRIVILEG_QTY = _gd.HANSE_PRIVILEG_QTY
HANSE_PRIVILEG_MONTHS = _gd.HANSE_PRIVILEG_MONTHS
HANSE_PRIVILEG_DISCOUNT = _gd.HANSE_PRIVILEG_DISCOUNT
FLEET_SYNERGY_REQUIRED = _gd.FLEET_SYNERGY_REQUIRED
FLEET_SYNERGY_HULL_MIN = _gd.FLEET_SYNERGY_HULL_MIN
FLEET_SYNERGY_HEUER_REDUCTION = _gd.FLEET_SYNERGY_HEUER_REDUCTION
ATHERIA_RESONANCE_GROWTH_MAX = _gd.ATHERIA_RESONANCE_GROWTH_MAX
ATHERIA_RESONANCE_TARGET_MULT = _gd.ATHERIA_RESONANCE_TARGET_MULT
DYNASTY_CHILDREN_TARGET = _gd.DYNASTY_CHILDREN_TARGET
DYNASTY_INHERITANCE_PER_CHILD = _gd.DYNASTY_INHERITANCE_PER_CHILD
DYNASTY_AGE_LIMIT = _gd.DYNASTY_AGE_LIMIT
SAVE_DIR = _gd.SAVE_DIR
SAVE_SLOT_COUNT = _gd.SAVE_SLOT_COUNT
SEA_FACTORS = _gd.SEA_FACTORS
SEA_STATES = _gd.SEA_STATES
STARTING_AGE = _gd.STARTING_AGE
STARTING_CASH = _gd.STARTING_CASH
STARTING_DEBT = _gd.STARTING_DEBT
STARTING_MONTH = _gd.STARTING_MONTH
STARTING_REPUTATION = _gd.STARTING_REPUTATION
STARTING_YEAR = _gd.STARTING_YEAR
shipyard_for_year = _gd.shipyard_for_year
modern_shipyard_for_year = getattr(_gd, "modern_shipyard_for_year", shipyard_for_year)
ships_unlocked_in_century = _gd.ships_unlocked_in_century
title_steps_for_year = _gd.title_steps_for_year
titles_unlocked_in_century = _gd.titles_unlocked_in_century
weapon_profile_for_year = _gd.weapon_profile_for_year
year_to_century = _gd.year_to_century
birth_chance_for_year = getattr(_gd, "birth_chance_for_year", lambda _year: 0.24)
child_mortality_for_year = getattr(_gd, "child_mortality_for_year", lambda _year: 0.10)
disease_pressure_for_year = getattr(_gd, "disease_pressure_for_year", lambda _year: 0.20)
max_children_for_year = getattr(
    _gd,
    "max_children_for_year",
    lambda _year: max(3, int(getattr(_gd, "DYNASTY_CHILDREN_TARGET", 3))),
)

if hasattr(_gd, "weapon_profile_for_century"):
    weapon_profile_for_century = _gd.weapon_profile_for_century
else:
    def weapon_profile_for_century(century: int) -> Dict[str, float | int | str]:
        century_i = max(14, int(century))
        year = (century_i - 1) * 100 + 1
        return dict(weapon_profile_for_year(year))
from models import Building, CityEconomy, NPCTrader, Player, ProductionRecipe, Ship, WorldEconomy
try:
    from research_manager import ResearchManager
except Exception:
    class ResearchManager:
        base_cost_social: int = 8_000
        base_cost_research: int = 500_000
        base_cost_infrastructure: int = 350_000
        base_cost_sophia: int = 750_000
        growth: float = 1.85

        def _base_cost(self, track: str) -> int:
            key = str(track).strip().lower()
            if key == "social":
                return self.base_cost_social
            if key == "infrastructure":
                return self.base_cost_infrastructure
            if key == "sophia":
                return self.base_cost_sophia
            return self.base_cost_research

        def cost_for_level(self, track: str, level: int) -> int:
            level_i = max(0, int(level))
            base = float(self._base_cost(track))
            scaled = base * (self.growth ** level_i) * (1.0 + math.log1p(level_i + 1))
            return max(int(base), int(round(scaled)))

        def level_from_spend(self, track: str, spend_total: float) -> int:
            remaining = max(0.0, float(spend_total))
            level = 0
            while level < 200:
                cost = float(self.cost_for_level(track, level))
                if remaining < cost:
                    break
                remaining -= cost
                level += 1
            return level

        def efficiency_reduction(self, level: int) -> float:
            level_i = max(0, int(level))
            if level_i <= 0:
                return 0.0
            return min(0.80, 0.20 + 0.08 * (level_i - 1))

        def social_relief_gain(self, amount: float) -> float:
            amount_f = max(0.0, float(amount))
            return min(0.08, math.log1p(amount_f / 5_000.0) * 0.012)

        def hazard_mitigation_gain(self, amount: float) -> float:
            amount_f = max(0.0, float(amount))
            return min(0.10, math.log1p(amount_f / 6_000.0) * 0.014)

        def travel_time_multiplier(self, infrastructure_level: int, year: int) -> float:
            level_i = max(0, int(infrastructure_level))
            if int(year) < 2000:
                return 1.0
            return max(0.10, 1.0 - 0.12 * level_i)

        def global_loss_value(self, sophia_spend: float) -> float:
            spend = max(0.0, float(sophia_spend))
            return min(0.85, math.log1p(spend / 1_000_000.0) * 0.12)


WIDTH = 1320
HEIGHT = 820
FPS = 60

BG_MAIN = (13, 19, 31)
BG_PANEL = (23, 31, 48)
BG_PANEL_ALT = (29, 39, 58)
TEXT = (236, 242, 255)
TEXT_DIM = (160, 174, 200)
ACCENT = (18, 170, 156)
ACCENT_2 = (232, 178, 69)
GOOD = (70, 190, 120)
BAD = (218, 96, 96)
ROW_HOVER = (39, 54, 78)
ROW_SELECTED = (54, 79, 112)

CANNON_COST = int(weapon_profile_for_year(STARTING_YEAR)["cannon_cost"])
MAX_SHIP_NAME_LEN = 18
MAX_CHILD_NAME_LEN = 20
AUTO_TURN_INTERVAL_MS = 550
AUTO_MIN_ROUTE_SCORE = 90
AUTO_MIN_RESERVE_MARK = 1400
AUTO_RESERVE_PER_SHIP_MARK = 420
AUTO_SHIP_BUILD_RESERVE = 7000
AUTO_MAX_FLEET_SIZE = 18
AUTO_REPAIR_TARGET = 90
AUTO_MAX_CANNON_BUYS = 2
AUTO_TRADE_BUDGET_SHARE = 0.56
AUTO_SHIP_BUILD_COOLDOWN_MONTHS = 3
AUTO_MARRIAGE_POPUP_MS = 1700
AUTO_MAX_SHIP_REPLACEMENTS_PER_MONTH = 2
AUTO_MAX_SHARE_BUYS_PER_MONTH = 2
AUTO_MAX_BUILDING_UPGRADES_PER_MONTH = 1
AUTO_SHARE_INVEST_RESERVE_MARK = 9000
AUTO_BUILDING_INVEST_RESERVE_MARK = 12000
AUTO_BUILDING_LEVEL_CAP = 7
UI_SETTINGS_FILE = "ui_settings.json"
UI_LANGUAGES = ("de", "en")
DEFAULT_MUSIC_VOLUME = 0.65
MUSIC_VOLUME_STEP = 0.1
FROZEN_APP_DIR_NAME = "Hanse_Atheria"


def _runtime_asset_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent


def _default_save_dir() -> Path:
    if ("ANDROID_ARGUMENT" in os.environ) or (sys.platform == "android"):
        return Path(__file__).resolve().parent / SAVE_DIR
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base_dir = Path(os.getenv("APPDATA", "")).expanduser()
            if not str(base_dir):
                base_dir = Path.home() / "AppData" / "Roaming"
        else:
            base_dir = Path(os.getenv("XDG_DATA_HOME", "")).expanduser()
            if not str(base_dir):
                base_dir = Path.home() / ".local" / "share"
        return base_dir / FROZEN_APP_DIR_NAME / SAVE_DIR
    return Path(__file__).resolve().parent / SAVE_DIR

UI_EN_EXACT: Dict[str, str] = {
    "Neues Spiel": "New Game",
    "Slot laden": "Load Slot",
    "Beenden": "Quit",
    "Speicherstaende": "Save Slots",
    "Grafische Version mit Save-Slots": "Graphical version with save slots",
    "Savegame-Menue": "Save Menu",
    "Speichern": "Save",
    "Laden": "Load",
    "Menue": "Menu",
    "Missionen": "Missions",
    "Schliessen": "Close",
    "Info": "Info",
    "CSV Export": "CSV Export",
    "Stadtpreise": "City Prices",
    "Schiff-Editor": "Ship Editor",
    "Schiffbau": "Shipyard",
    "Schiffsladung": "Ship Cargo",
    "Kaufen": "Buy",
    "Verkaufen": "Sell",
    "Naechster Monat": "Next Month",
    "Nachkommen zeugen": "Conceive Heir",
    "Auto-Policy": "Auto Policy",
    "Atheria-Wirtschaft": "Atheria Economy",
    "Weltmarkt": "World Market",
    "Spielerinfo": "Player Info",
    "Stadtgesundheit & Gesellschaft": "City Health & Society",
    "Einstellungen": "Settings",
    "Sprache": "Language",
    "Deutsch": "German",
    "Englisch": "English",
    "UI-Sprache sofort umschalten.": "Switch UI language immediately.",
    "Musik": "Music",
    "Hintergrundmusik im Spiel umschalten.": "Toggle background music in-game.",
    "Lautstaerke": "Volume",
    "An": "On",
    "Aus": "Off",
    "Nicht verfuegbar": "Unavailable",
    "Hinweis: F5 Speichern | F9 Laden | F6 CSV-Export.": "Tip: F5 Save | F9 Load | F6 CSV export.",
    "Spielinformation": "Game Information",
    "Spielname": "Game Name",
    "Webseite": "Website",
    "Entwickler": "Developer",
    "(leer)": "(empty)",
    "(defekt)": "(corrupt)",
    "Fernhandel: keine Stadtanteile oder Rettung.": "Remote trade: no city shares or bailout.",
}

UI_EN_REPLACE: Tuple[Tuple[str, str], ...] = (
    ("ANNO", "YEAR"),
    ("Jahrhundert", "Century"),
    ("September", "September"),
    ("November", "November"),
    ("Dezember", "December"),
    ("Februar", "February"),
    ("Oktober", "October"),
    ("Januar", "January"),
    ("Maerz", "March"),
    ("April", "April"),
    ("Juni", "June"),
    ("Juli", "July"),
    ("August", "August"),
    ("Mai", "May"),
    ("tobende See", "raging sea"),
    ("stuermische See", "stormy sea"),
    ("bewegte See", "rough sea"),
    ("ruhige See", "calm sea"),
    ("stille See", "still sea"),
    ("ATHERIA mobil fortgeschrieben", "ATHERIA mobile carried forward"),
    ("ATHERIA fortgeschrieben", "ATHERIA carried forward"),
    ("ATHERIA mobil", "ATHERIA mobile"),
    ("Fallback-Modell", "Fallback model"),
    ("Atheria-Wirtschaft", "Atheria Economy"),
    ("Weltmarkt", "World Market"),
    ("Preisniveau", "Price level"),
    ("Hanse-Privileg", "Hanse Privilege"),
    ("Atheria-Resonanz", "Atheria Resonance"),
    ("Architekt der Synergie", "Architect of Synergy"),
    ("Familiendynastie", "Family Dynasty"),
    ("Braumeisterbund", "Brewers' Guild"),
    ("Nordholz-Vertrag", "Northwood Pact"),
    ("Routenmeister", "Route Master"),
    ("Arsenal der Hanse", "Arsenal of the Hanse"),
    ("Betriebskampagnen", "Industry Campaigns"),
    ("Neue Titelstufen freigeschaltet.", "New title tiers unlocked."),
    ("Mission gestartet", "Mission started"),
    ("Mission erfuellt", "Mission completed"),
    ("Hall of Fame freigeschaltet", "Hall of Fame unlocked"),
    ("Rezession endet", "recession ends"),
    ("Auto-Modus", "Auto Mode"),
    ("Auto-Modernisierung", "Auto Modernization"),
    ("Auto-Aufruestung", "Auto Upgrade"),
    ("Auto-Verladen", "Auto Loading"),
    ("Auto-Handel", "Auto Trade"),
    ("Auto-Invest", "Auto Invest"),
    ("Auto-Policy", "Auto Policy"),
    ("Handelshaus erloschen", "trading house has perished"),
    ("Handelshaus endet", "trading house ends"),
    ("Handel geht weiter", "trade continues"),
    ("Laufzeitzustand repariert", "runtime state repaired"),
    ("Auto deaktiviert", "auto disabled"),
    ("Monatswechsel-Fehler", "Month rollover error"),
    ("Laufzeitfehler", "Runtime error"),
    ("veraltete Schiffe ersetzt", "obsolete ships replaced"),
    ("auf Kanonenstufe", "to cannon tier"),
    ("vereinheitlicht", "standardized"),
    ("Keine Schiffe verfuegbar.", "No ships available."),
    ("Kein Schiff ausgewaehlt.", "No ship selected."),
    ("Das letzte Schiff kann nicht verkauft werden.", "The last ship cannot be sold."),
    ("Schiff ist auf See und kann nicht verkauft werden.", "Ship is at sea and cannot be sold."),
    ("Schiff ist auf See. Ausbesserung nicht moeglich.", "Ship is at sea. Repairs are not possible."),
    ("Schiff ist auf See. Verladen nicht moeglich.", "Ship is at sea. Loading is not possible."),
    ("Schiff ist bereits auf See.", "Ship is already at sea."),
    ("Schiff liegt nicht im aktuellen Hafen.", "Ship is not in the current harbor."),
    ("Bitte Schiff erst komplett entladen.", "Please fully unload the ship first."),
    ("Kanonen koennen nur im Hafen montiert werden.", "Cannons can only be installed in harbor."),
    ("Nicht genug Mark fuer Anteilskauf.", "Not enough Mark to buy shares."),
    ("Nicht genug Mark fuer Ausbesserung.", "Not enough Mark for repairs."),
    ("Nicht genug Mark fuer Kanonen.", "Not enough Mark for cannons."),
    ("Nicht genug Mark fuer die Reise.", "Not enough Mark for the voyage."),
    ("Nicht genug Mark.", "Not enough Mark."),
    ("Kaufen nicht moeglich.", "Buying is not possible."),
    ("Verkaufen nicht moeglich.", "Selling is not possible."),
    ("Reisen nicht moeglich.", "Travel is not possible."),
    ("Keine Waren verfuegbar.", "No goods available."),
    ("Keine Ware auf Lager.", "No goods in storage."),
    ("Keine Reiseziele verfuegbar.", "No destinations available."),
    ("Keine freien Anteile verfuegbar.", "No free shares available."),
    ("Marktbestand erschoepft.", "Market stock exhausted."),
    ("CSV-Export fehlgeschlagen.", "CSV export failed."),
    ("CSV exportiert", "CSV exported"),
    ("Betrieb nicht gefunden.", "Building not found."),
    ("Unbekannter Code.", "Unknown code."),
    ("Schuldturm", "Debtors' Tower"),
    ("Schuldentilgung", "Debt repayment"),
    ("Kein Nachkomme moeglich", "No heir possible"),
    ("Nachkommen zeugen ist nur in einer Ehe moeglich.", "Conceiving an heir is only possible within a marriage."),
    ("Nachkommen zeugen derzeit nicht verfuegbar", "Conceiving an heir is currently unavailable"),
    ("Nachkommen gezeugt", "Heir conceived"),
    ("Nachfolge gesichert", "Succession secured"),
    ("Ein Kind wurde geboren. Bitte den Namen im Popup vergeben.", "A child was born. Please assign the name in the popup."),
    ("Bitte einen gueltigen Namen eingeben.", "Please enter a valid name."),
    ("Familie waechst", "Family grows"),
    ("Schicksalsschlag", "Tragedy"),
    ("Neugeborenes", "Newborn"),
    ("Trauerfall", "Bereavement"),
    ("verstarb an Krankheit.", "died of illness."),
    ("verstarben an Krankheiten.", "died of illnesses."),
    ("Vermaehlung", "Marriage"),
    ("Werbungsbrief von", "Suitor letter from"),
    ("abgelehnt.", "declined."),
    ("Schiffsname gesetzt", "Ship name set"),
    ("Verladen", "Loaded"),
    ("Entladen", "Unloaded"),
    ("Gekauft", "Bought"),
    ("Verkauft", "Sold"),
    ("sticht in See Richtung", "sets sail toward"),
    ("Reisekosten", "Travel cost"),
    ("ist sicher im Hafen angekommen.", "has arrived safely in harbor."),
    ("ist untergegangen.", "has sunk."),
    ("Kaperangriff", "Pirate attack"),
    ("Verlust", "Loss"),
    ("keine Beute.", "no loot."),
    ("Sturm", "Storm"),
    ("Rumpf", "Hull"),
    ("Takelage", "Rigging"),
    ("Aufstieg", "Promotion"),
    ("Neues Handelshaus gegruendet in", "New trading house founded in"),
    ("Spiel in Slot", "Game in slot"),
    ("Betriebsquest", "Building quest"),
    ("Stufe", "Tier"),
    ("Maximale Bewaffnung erreicht", "Maximum armament reached"),
    (" ist leer.", " is empty."),
    (" gespeichert.", " saved."),
    (" geladen.", " loaded."),
    ("Mehrspieler-Save erkannt: erster Spieler geladen.", "Multiplayer save detected: first player loaded."),
    ("Keine akute Rettung noetig.", "No urgent bailout needed."),
    ("keine akute Rettung noetig.", "no urgent bailout needed."),
    ("keine Rettung noetig.", "no bailout needed."),
    ("Stadtrettung", "City bailout"),
    ("Sozialstiftung", "Social welfare"),
    ("Betriebsforschung", "Industry research"),
    ("Reise-Infrastruktur", "Travel infrastructure"),
    ("Marktstabilisierung", "Market stabilization"),
    ("Passive Rendite", "Passive income"),
    ("Hinweis", "Note"),
    (" benoetigt ", " requires "),
    (" fuer ", " for "),
    ("Waren", "Goods"),
    ("Mausrad", "Mouse wheel"),
    ("Markt", "Market"),
    ("Flotte", "Fleet"),
    ("Aktionen", "Actions"),
    ("Chronik / Meldungen", "Chronicle / Messages"),
    ("Ort:", "Location:"),
    ("Ziel:", "Target:"),
    ("Preis", "Price"),
    ("Lager", "Storage"),
    ("Bestand", "Stock"),
    ("produziert", "producing"),
    ("wartet", "waiting"),
    ("aktiv", "active"),
    ("inaktiv", "inactive"),
    ("Kurs", "Rate"),
    ("Ihr/Frei", "Own/Free"),
    ("Stadtkasse", "City Treasury"),
    ("Status", "Status"),
    ("stabil", "stable"),
    ("Einfluss", "Influence"),
    ("Food", "Food"),
    ("Crowding", "Crowding"),
    ("Disease", "Disease"),
    ("Medical", "Medical"),
    ("Migration", "Migration"),
    ("Bankruptcy", "Bankruptcy"),
    ("Infrastructure", "Infrastructure"),
    ("Steuern", "Taxes"),
    ("Bailout", "Bailout"),
    ("Monumente", "Monuments"),
    ("Kosten", "Costs"),
    ("Forschung", "Research"),
    ("Stiftung", "Welfare"),
    ("Reisezeit", "Travel Time"),
    ("Preisstab.", "Price Stability"),
    ("Stadt retten", "Rescue City"),
    ("Bankrott", "Bankrupt"),
    ("Bankrott-Staedte", "Bankrupt Cities"),
    ("Krankheitsfaelle", "Disease Cases"),
    ("Krankheitstote", "Disease Deaths"),
    ("Geschlecht", "Gender"),
    ("maennlich", "male"),
    ("weiblich", "female"),
    ("Alter", "Age"),
    ("Familienstand", "Marital status"),
    ("verheiratet", "married"),
    ("ledig", "single"),
    ("Ehepartner", "Spouse"),
    ("Kinder", "Children"),
    ("Datum", "Date"),
    ("Seezustand", "Sea state"),
    ("Schulden", "Debt"),
    ("Reputation", "Reputation"),
    ("Gesamtwert", "Net worth"),
    ("Naechster Titel", "Next title"),
    ("Fehlender Wert", "Missing value"),
    ("Schiffe gesamt", "Ships total"),
    ("Im Hafen", "In harbor"),
    ("Auf See", "At sea"),
    ("Ladung", "Cargo"),
    ("Durchschnitt", "Average"),
    ("Kanonen gesamt", "Cannons total"),
    ("Schiffdetails", "Ship details"),
    ("Mission erfuellt", "Mission completed"),
    ("Abgeschlossen", "Completed"),
    ("Gescheitert", "Failed"),
    ("Wachstum", "Growth"),
    ("Preisniveau", "Price level"),
    ("Knappheit", "Scarcity"),
    ("Tod des Vorfahren", "Ancestor died"),
    ("Das Handelshaus ist erloschen.", "The trading house has perished."),
    ("Du kannst laden oder ins Menue wechseln.", "You can load or switch to the menu."),
    ("Auto-Modus aktiv", "Auto mode active"),
    ("Auto-Modus beendet", "Auto mode ended"),
    ("Fehler", "Error"),
    ("In:", "In:"),
    ("Out:", "Out:"),
    ("Salz", "Salt"),
    ("Holz", "Wood"),
    ("Pelze", "Furs"),
    ("Getreide", "Grain"),
    ("Tuch", "Cloth"),
    ("Hering", "Herring"),
    ("Wein", "Wine"),
    ("Bier", "Beer"),
    ("Hopfen", "Hops"),
    ("Teer", "Tar"),
    ("Gewuerze", "Spices"),
    ("Kupfer", "Copper"),
    ("Tabak", "Tobacco"),
    ("Zucker", "Sugar"),
    ("Kaffee", "Coffee"),
    ("Baumwolle", "Cotton"),
    ("Kohle", "Coal"),
    ("Stahl", "Steel"),
    ("Elektronik", "Electronics"),
    ("Treibstoff", "Fuel"),
    ("Seltene Erden", "Rare Earths"),
    ("Mikrochips", "Microchips"),
    ("Grosse Kogge", "Great Cog"),
    ("Kogge", "Cog"),
    ("Holk", "Hulk"),
    ("Kraier", "Crayer"),
    ("Karavelle", "Caravel"),
    ("Karacke", "Carrack"),
    ("Galeone", "Galleon"),
    ("Fregatte", "Frigate"),
    ("Dampfklipper", "Steam Clipper"),
    ("Stahlschiff", "Steel Ship"),
    ("Containerfrachter", "Container Freighter"),
    ("Schwenkbombarden", "Swivel Bombards"),
    ("Bronze-Kartaunen", "Bronze Culverins"),
    ("Kartaunen", "Culverins"),
    ("Langrohr-Kanonen", "Long-Barrel Cannons"),
    ("Granatkanonen", "Grenade Cannons"),
    ("Stahlgeschuetze", "Steel Guns"),
    ("Turmkanonen", "Turret Cannons"),
    ("Railkanonen", "Rail Cannons"),
)

UI_EN_REPLACE_SORTED: Tuple[Tuple[str, str], ...] = tuple(
    sorted(UI_EN_REPLACE, key=lambda item: len(item[0]), reverse=True)
)
UI_EN_REPLACE_MAP: Dict[str, str] = {source: target for source, target in UI_EN_REPLACE_SORTED}
UI_EN_REPLACE_PATTERN = re.compile("|".join(re.escape(source) for source in UI_EN_REPLACE_MAP))

WORLD_INITIAL_STOCK_MIN = 120
WORLD_INITIAL_STOCK_MAX = 180
NPC_MIN_MARKET_STOCK = 20
NPC_SKIP_LOW_STOCK = 30
NPC_MAX_BUY_PER_TRIP = 80
BASE_CITY_CONSUMPTION: Dict[str, int] = {
    "Getreide": 1,
    "Salz": 1,
    "Hering": 1,
}

QUEST_BREWMASTER_TARGET = 220
QUEST_TIMBER_TARGET = 300
QUEST_ROUTE_MASTER_TARGET_CITIES = 6
QUEST_ARMS_RACE_TARGET_CANNONS = 20
QUEST_ARMS_RACE_TARGET_SHIPS = 3
BUILDING_QUEST_TIERS = 8
BUILDING_QUEST_BASE_MULT = 18
CITY_BANKRUPTCY_LIMIT = -550
CITY_RECOVERY_TARGET = -120
CITY_TREASURY_BASE_INCOME_PER_BUILDING = 2
DIVIDEND_POOL_FACTOR = 0.35
MAX_BUILDING_SHARE_PERCENT = 100.0
MIN_BAILOUT_INFLUENCE = 6.0
BAILOUT_MIN_AMOUNT = 500
BAILOUT_INFLUENCE_COST = 4.0
INFLUENCE_PER_SHARE_PURCHASE = 0.30
INFLUENCE_PER_DIVIDEND_1000 = 0.35
SOCIAL_WELFARE_MIN_AMOUNT = 2_000
CITY_BAILOUT_MONUMENT_KEY = "stifter_monument"
MONUMENT_STORAGE_MULTIPLIER = 2.0
MONUMENT_REPUTATION_BONUS = 0.25
CITY_MONUMENT_REPUTATION_BASE = 2

TRACK_SOCIAL = "social"
TRACK_RESEARCH = "research"
TRACK_INFRASTRUCTURE = "infrastructure"
TRACK_SOPHIA = "sophia"
CITY_POP_MIN = 180
CITY_POP_MAX = 5_000_000
CHILD_MORTALITY_VULNERABLE_AGE = 6
CITY_INDUSTRY_LEVEL_MAX = 1_400
CITY_INDUSTRY_SLOTS_MAX = 240

CENTURY_INSTITUTION_UNLOCKS: Dict[int, Dict[str, int]] = {
    14: {"guild": 1, "watch": 1, "warehouse": 1},
    15: {"academy": 1, "hospital": 1},
    16: {"exchange": 1, "court": 1, "doctors": 1},
    17: {"bank": 1, "dockyard": 1},
    18: {"university": 1, "canal": 1},
    19: {"rail_hub": 1, "sanitation": 1},
    20: {"power_grid": 1, "industrial_port": 1},
    21: {"digital_exchange": 1, "aether_lab": 1},
}

# Marktstabilisierung: globale Verlust-/Volatilitaetsdaempfung.
global_loss_value = 0.0

RECIPE_UNLOCK_CENTURY: Dict[str, int] = {
    "brewery": 14,
    "salt_mine": 14,
    "woodcutter": 14,
    "fishery": 14,
    "grain_farm": 14,
    "winery": 14,
    "weavery": 14,
    "tannery": 14,
    "hop_farm": 15,
    "tar_kiln": 15,
    "grand_brewery": 15,
    "spice_trade": 16,
    "copper_mine": 16,
    "spice_refinery": 16,
    "tobacco_farm": 17,
    "sugar_farm": 17,
    "sugar_refinery": 17,
    "coffee_farm": 18,
    "cotton_farm": 18,
    "textile_factory": 18,
    "coal_mine": 19,
    "steel_mill": 19,
    "refinery": 19,
    "electronics_factory": 20,
    "rare_earth_mine": 21,
    "chip_factory": 21,
    "silk_looms": 16,
    "porcelain_house": 16,
    "tea_house": 16,
    "silver_mint": 16,
    "cacao_press": 17,
    "rum_distillery": 17,
    "colonial_depot": 17,
    "whaling_station": 18,
    "rubber_works": 18,
}

CITY_RECIPE_LEVEL_BONUS: Dict[str, Dict[str, int]] = {
    "Luebeck": {"brewery": 2, "grand_brewery": 2, "weavery": 2, "textile_factory": 2, "spice_trade": 2},
    "Bergen": {"woodcutter": 2, "fishery": 2, "tar_kiln": 2, "hop_farm": 2},
    "Toensberg": {"fishery": 2, "tar_kiln": 2, "sugar_farm": 2},
    "Warberg": {"grain_farm": 2, "cotton_farm": 2, "refinery": 2},
    "Malmoe": {"weavery": 2, "textile_factory": 2, "coffee_farm": 2},
    "Ystad": {"fishery": 2, "spice_trade": 2, "sugar_refinery": 2},
    "Visby": {"hop_farm": 2, "spice_refinery": 2, "tobacco_farm": 2},
    "Riga": {"salt_mine": 2, "copper_mine": 2, "steel_mill": 2, "rare_earth_mine": 2},
    "Novgorod": {"salt_mine": 2, "copper_mine": 2, "coal_mine": 2, "chip_factory": 2},
}

REMOTE_REGION_EXPORT_BONUS: Dict[str, Dict[str, float]] = {
    "Afrika": {"Kaffee": 1.18, "Kupfer": 1.12, "Baumwolle": 1.10},
    "China": {"Seide": 1.40, "Porzellan": 1.38, "Tee": 1.28, "Silber": 1.14},
    "Asien": {"Gewuerze": 1.34, "Tee": 1.26, "Seide": 1.12},
    "Amerika": {"Kakao": 1.32, "Rum": 1.28, "Kolonialholz": 1.25, "Zucker": 1.18},
    "Arktis": {"Walfett": 1.42, "Pelze": 1.16, "Kautschuk": 1.08},
}

REMOTE_REGION_BUILDING_IDS: Dict[str, List[str]] = {
    "Afrika": ["coffee_farm", "copper_mine"],
    "China": ["silk_looms", "porcelain_house", "tea_house", "silver_mint"],
    "Asien": ["spice_trade", "tea_house", "silk_looms"],
    "Amerika": ["cacao_press", "rum_distillery", "colonial_depot", "sugar_farm"],
    "Arktis": ["whaling_station", "tannery", "rubber_works"],
}

REMOTE_REGION_MIGRATION_GOODS: Dict[str, Tuple[str, ...]] = {
    "Afrika": ("Kaffee", "Kupfer"),
    "China": ("Seide", "Porzellan", "Tee"),
    "Asien": ("Gewuerze", "Tee"),
    "Amerika": ("Kakao", "Rum", "Kolonialholz"),
    "Arktis": ("Walfett", "Pelze", "Kautschuk"),
}

REMOTE_SPECIAL_GOODS = {
    good_name
    for export_map in REMOTE_REGION_EXPORT_BONUS.values()
    for good_name in export_map.keys()
}

PRODUCTION_RECIPES: Dict[str, ProductionRecipe] = {
    "brewery": ProductionRecipe(
        id="brewery",
        name="Brauerei",
        inputs={"Getreide": 4, "Holz": 1},
        outputs={"Bier": 6},
        upkeep=2,
    ),
    "salt_mine": ProductionRecipe(
        id="salt_mine",
        name="Salzmine",
        inputs={},
        outputs={"Salz": 5},
        upkeep=1,
    ),
    "woodcutter": ProductionRecipe(
        id="woodcutter",
        name="Holzfaeller",
        inputs={},
        outputs={"Holz": 6},
        upkeep=1,
    ),
    "fishery": ProductionRecipe(
        id="fishery",
        name="Fischerei",
        inputs={},
        outputs={"Hering": 4},
        upkeep=1,
    ),
    "grain_farm": ProductionRecipe(
        id="grain_farm",
        name="Getreidehof",
        inputs={},
        outputs={"Getreide": 5},
        upkeep=1,
    ),
    "winery": ProductionRecipe(
        id="winery",
        name="Weinkellerei",
        inputs={"Getreide": 3},
        outputs={"Wein": 3},
        upkeep=2,
    ),
    "weavery": ProductionRecipe(
        id="weavery",
        name="Weberei",
        inputs={"Holz": 2},
        outputs={"Tuch": 3},
        upkeep=2,
    ),
    "tannery": ProductionRecipe(
        id="tannery",
        name="Gerberei",
        inputs={"Salz": 1},
        outputs={"Pelze": 2},
        upkeep=2,
    ),
    "hop_farm": ProductionRecipe(
        id="hop_farm",
        name="Hopfenplantage",
        inputs={},
        outputs={"Hopfen": 5},
        upkeep=1,
    ),
    "tar_kiln": ProductionRecipe(
        id="tar_kiln",
        name="Teerbrennerei",
        inputs={"Holz": 3},
        outputs={"Teer": 4},
        upkeep=2,
    ),
    "grand_brewery": ProductionRecipe(
        id="grand_brewery",
        name="Grossbrauerei",
        inputs={"Getreide": 4, "Hopfen": 2, "Holz": 1},
        outputs={"Bier": 10},
        upkeep=4,
    ),
    "spice_trade": ProductionRecipe(
        id="spice_trade",
        name="Gewuerzhandel",
        inputs={},
        outputs={"Gewuerze": 4},
        upkeep=3,
    ),
    "copper_mine": ProductionRecipe(
        id="copper_mine",
        name="Kupfermine",
        inputs={},
        outputs={"Kupfer": 4},
        upkeep=2,
    ),
    "spice_refinery": ProductionRecipe(
        id="spice_refinery",
        name="Gewuerzraffinerie",
        inputs={"Gewuerze": 4},
        outputs={"Luxuswaren": 6},
        upkeep=5,
    ),
    "tobacco_farm": ProductionRecipe(
        id="tobacco_farm",
        name="Tabakplantage",
        inputs={},
        outputs={"Tabak": 5},
        upkeep=2,
    ),
    "sugar_farm": ProductionRecipe(
        id="sugar_farm",
        name="Zuckerplantage",
        inputs={},
        outputs={"Zucker": 5},
        upkeep=2,
    ),
    "sugar_refinery": ProductionRecipe(
        id="sugar_refinery",
        name="Zuckerraffinerie",
        inputs={"Zucker": 5},
        outputs={"Luxuswaren": 6},
        upkeep=4,
    ),
    "coffee_farm": ProductionRecipe(
        id="coffee_farm",
        name="Kaffeeplantage",
        inputs={},
        outputs={"Kaffee": 5},
        upkeep=2,
    ),
    "cotton_farm": ProductionRecipe(
        id="cotton_farm",
        name="Baumwollfarm",
        inputs={},
        outputs={"Baumwolle": 5},
        upkeep=2,
    ),
    "textile_factory": ProductionRecipe(
        id="textile_factory",
        name="Textilmanufaktur",
        inputs={"Baumwolle": 5},
        outputs={"Tuch": 7},
        upkeep=4,
    ),
    "coal_mine": ProductionRecipe(
        id="coal_mine",
        name="Kohlemine",
        inputs={},
        outputs={"Kohle": 6},
        upkeep=2,
    ),
    "steel_mill": ProductionRecipe(
        id="steel_mill",
        name="Stahlwerk",
        inputs={"Kohle": 4, "Kupfer": 2},
        outputs={"Stahl": 5},
        upkeep=5,
    ),
    "refinery": ProductionRecipe(
        id="refinery",
        name="Raffinerie",
        inputs={"Kohle": 5},
        outputs={"Treibstoff": 6},
        upkeep=6,
    ),
    "electronics_factory": ProductionRecipe(
        id="electronics_factory",
        name="Elektronikfabrik",
        inputs={"Stahl": 3, "Kupfer": 2},
        outputs={"Elektronik": 5},
        upkeep=6,
    ),
    "rare_earth_mine": ProductionRecipe(
        id="rare_earth_mine",
        name="Seltene Erden Mine",
        inputs={},
        outputs={"Seltene Erden": 4},
        upkeep=4,
    ),
    "chip_factory": ProductionRecipe(
        id="chip_factory",
        name="Chipfabrik",
        inputs={"Seltene Erden": 3},
        outputs={"Mikrochips": 5},
        upkeep=8,
    ),
    "silk_looms": ProductionRecipe(
        id="silk_looms",
        name="Seidenweberei",
        inputs={"Seide": 3, "Holz": 1},
        outputs={"Tuch": 5, "Luxuswaren": 2},
        upkeep=5,
    ),
    "porcelain_house": ProductionRecipe(
        id="porcelain_house",
        name="Porzellanhaus",
        inputs={"Porzellan": 2},
        outputs={"Luxuswaren": 4},
        upkeep=5,
    ),
    "tea_house": ProductionRecipe(
        id="tea_house",
        name="Teehaus",
        inputs={"Tee": 3, "Wein": 1},
        outputs={"Luxuswaren": 4},
        upkeep=4,
    ),
    "silver_mint": ProductionRecipe(
        id="silver_mint",
        name="Silberpraege",
        inputs={"Silber": 2, "Kupfer": 1},
        outputs={"Luxuswaren": 4},
        upkeep=5,
    ),
    "cacao_press": ProductionRecipe(
        id="cacao_press",
        name="Kakaopresse",
        inputs={"Kakao": 3, "Zucker": 2},
        outputs={"Luxuswaren": 5},
        upkeep=5,
    ),
    "rum_distillery": ProductionRecipe(
        id="rum_distillery",
        name="Rumdestille",
        inputs={"Zucker": 3, "Kolonialholz": 1},
        outputs={"Rum": 4, "Luxuswaren": 1},
        upkeep=5,
    ),
    "colonial_depot": ProductionRecipe(
        id="colonial_depot",
        name="Kolonialdepot",
        inputs={"Rum": 2, "Kakao": 2},
        outputs={"Luxuswaren": 6},
        upkeep=6,
    ),
    "whaling_station": ProductionRecipe(
        id="whaling_station",
        name="Walfangstation",
        inputs={},
        outputs={"Walfett": 5},
        upkeep=4,
    ),
    "rubber_works": ProductionRecipe(
        id="rubber_works",
        name="Kautschukwerk",
        inputs={"Kautschuk": 3, "Holz": 1},
        outputs={"Luxuswaren": 5},
        upkeep=6,
    ),
}

MARRIAGE_CANDIDATES = [
    "Adelheid von Wismar",
    "Margarete von Reval",
    "Katharina von Stralsund",
    "Elisabeth aus dem Kontor zu Danzig",
    "Hedwig von Riga",
    "Mechthild von Rostock",
]
AUTO_CHILD_NAME_SOURCES = (
    "Johann von Luebeck",
    "Heinrich Kramer",
    "Dietrich Albers",
    "Klaus Wullenwever",
    "Hinrich Bruns",
    "Cord Petersen",
    "Bertram van Bremen",
    "Nikolaus Kroeger",
    "Hermann Tidemann",
    "Ludolf Hagedorn",
    "Gerd Schumacher",
    "Albert Zimmermann",
    "Bernd Kupfermann",
    "Otto Drechsler",
    "Friedrich Segelmacher",
    "Matthias Rademaker",
    "Konrad Schmied",
    "Volker Fischer",
    "Eberhard Bootsbauer",
    "Ruprecht Steinmetz",
    "Jakob Steuermann",
    "Hinrich Seefahrer",
    "Thomas Navigator",
    "Arend Kapitaen",
    "Juergen Lotsen",
    "Berthold Kuestermann",
    "Magnus Wellenschlaeger",
    "Carsten Ankermann",
    "Timo Rudermann",
    "Wulf Meeresfahrer",
    "Friedrich von Hamburg",
    "Albrecht von Rostock",
    "Wilhelm von Greifswald",
    "Gerhard von Stralsund",
    "Ludolf von Wismar",
    "Eckhard von Danzig",
    "Konrad von Riga",
    "Dietmar von Visby",
    "Heinrich von Koeln",
    "Otto von Bremen",
    "Hans Bauer",
    "Peter Mueller",
    "Simon Weber",
    "Andreas Schulze",
    "Martin Krueger",
    "Lorenz Richter",
    "Michael Vogt",
    "Paul Brandt",
    "Stefan Lorenz",
    "Nikolaus Falk",
)
AUTO_CHILD_FIRST_NAMES = tuple(name.split(" ", 1)[0] for name in AUTO_CHILD_NAME_SOURCES)
AUTO_CHILD_SURNAMES = tuple(name.split(" ", 1)[1] for name in AUTO_CHILD_NAME_SOURCES)
AUTO_SHIP_NAME_POOLS: Dict[str, Tuple[str, ...]] = {
    "kogge": (
        "St. Maria",
        "St. Nikolaus",
        "St. Katharina",
        "St. Georg",
        "St. Johannes",
        "St. Michael",
        "St. Anna",
        "St. Jakob",
        "St. Paulus",
        "St. Petrus",
        "Fortuna",
        "Hoffnung",
        "Gnade Gottes",
        "Barmherzigkeit",
        "Treue",
        "Einigkeit",
        "Ehre",
        "Freiheit",
        "Hanse",
        "Seestern",
        "Nordwind",
        "Ostwind",
        "Westwind",
        "Suedwind",
        "Sturmvogel",
        "Moewe",
        "Albatros",
        "Seeloewe",
        "Meerjungfrau",
        "Meereskrone",
        "Goldener Loewe",
        "Silberner Adler",
        "Roter Greif",
        "Schwarzer Rabe",
        "Weisser Schwan",
        "Blaue Welle",
        "Perle der See",
        "Koenigin der Ostsee",
        "Stolz von Luebeck",
        "Stolz von Hamburg",
        "Stolz von Bremen",
        "Stolz von Danzig",
        "Stolz von Riga",
        "Stolz von Visby",
        "Stolz von Rostock",
        "Stolz von Stralsund",
        "Stolz von Wismar",
        "Stolz von Koeln",
        "Stolz von Elbing",
        "Stolz von Koenigsberg",
        "Fortuna II",
        "Fortuna III",
        "Fortuna IV",
        "Fortuna V",
        "Hoffnung II",
        "Hoffnung III",
        "Hoffnung IV",
        "Hoffnung V",
        "Seestern II",
        "Seestern III",
        "Seestern IV",
        "Seestern V",
        "Nordwind II",
        "Nordwind III",
        "Nordwind IV",
        "Nordwind V",
        "Ostwind II",
        "Ostwind III",
        "Ostwind IV",
        "Ostwind V",
        "Westwind II",
        "Westwind III",
        "Westwind IV",
        "Westwind V",
        "Suedwind II",
        "Suedwind III",
        "Suedwind IV",
        "Suedwind V",
        "Goldener Loewe II",
        "Goldener Loewe III",
        "Goldener Loewe IV",
        "Goldener Loewe V",
        "Silberner Adler II",
        "Silberner Adler III",
        "Silberner Adler IV",
        "Silberner Adler V",
        "Roter Greif II",
        "Roter Greif III",
        "Roter Greif IV",
        "Roter Greif V",
        "Schwarzer Rabe II",
        "Schwarzer Rabe III",
        "Schwarzer Rabe IV",
        "Schwarzer Rabe V",
        "Weisser Schwan II",
        "Weisser Schwan III",
        "Weisser Schwan IV",
        "Weisser Schwan V",
        "Perle der See II",
        "Perle der See III",
        "Perle der See IV",
        "Perle der See V",
        "Koenigin der Ostsee II",
        "Koenigin der Ostsee III",
        "Koenigin der Ostsee IV",
        "Koenigin der Ostsee V",
    ),
    "holk": (
        "Holk der Fortuna",
        "Holk der Hoffnung",
        "Holk der Gnade",
        "Holk der Treue",
        "Holk der Hanse",
        "Holk Luebeck",
        "Holk Hamburg",
        "Holk Bremen",
        "Holk Danzig",
        "Holk Riga",
        "Holk Visby",
        "Holk Rostock",
        "Holk Stralsund",
        "Holk Wismar",
        "Holk Koenigsberg",
    ),
    "kraier": (
        "Kraier Fortuna",
        "Kraier Hoffnung",
        "Kraier Hanse",
        "Kraier Seestern",
        "Kraier Nordwind",
        "Kraier Ostwind",
        "Kraier Westwind",
        "Kraier Suedwind",
        "Kraier Greif",
        "Kraier Adler",
    ),
    "karavelle": (
        "Karavelle Fortuna",
        "Karavelle Hoffnung",
        "Karavelle Hanse",
        "Karavelle Luebeck",
        "Karavelle Hamburg",
        "Karavelle Bremen",
        "Karavelle Danzig",
        "Karavelle Riga",
    ),
    "kriegsschiff": (
        "Kriegsschiff Adler",
        "Kriegsschiff Loewe",
        "Kriegsschiff Greif",
        "Kriegsschiff Hanse",
        "Kriegsschiff Luebeck",
    ),
    "pirat": (
        "Piratenkoenig",
        "Schwarze Kralle",
        "Blutiger Wolf",
        "Dunkle Moewe",
        "Roter Schatten",
        "Schwarze Flut",
        "Blutmond",
        "Sturmbringer",
        "Meeresgeist",
        "Schatten der See",
    ),
}
FEMALE_NAME_HINTS = {
    "anna",
    "grete",
    "elske",
    "alheid",
    "clara",
    "adelheid",
    "margarete",
    "katharina",
    "elisabeth",
    "hedwig",
    "mechthild",
}


class PygameHanseApp:
    def __init__(self) -> None:
        self.is_android = ("ANDROID_ARGUMENT" in os.environ) or (sys.platform == "android")
        if self.is_android:
            try:
                pygame.mixer.pre_init(22050, -16, 2, 1024)
            except TypeError:
                pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=1024)
        pygame.init()
        pygame.display.set_caption("Hanse - pygame Edition")
        if self.is_android:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.screen = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.scale_x = 1.0
        self.scale_y = 1.0
        self._update_display_scale()
        self.clock = pygame.time.Clock()
        self.target_fps = 30 if self.is_android else FPS
        self.running = True

        self.font_title = pygame.font.Font(None, 58)
        self.font_h1 = pygame.font.Font(None, 38)
        self.font = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)

        self.image_dir = _runtime_asset_root() / "images"
        self.images: Dict[str, pygame.Surface] = {}
        self.scaled_images: Dict[Tuple[str, int, int], pygame.Surface] = {}
        self._load_images()

        self.rng = random.Random()
        self.scene = "menu"

        self.save_dir = _default_save_dir()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.save_dir / UI_SETTINGS_FILE
        self.music_path = self._resolve_music_path()
        self.ui_language = self._load_ui_language()
        self.music_enabled = self._load_music_enabled()
        self.music_volume = self._load_music_volume()
        self.music_available = False
        self._music_loaded = False
        self._ui_translation_cache: Dict[str, str] = {}
        self.settings_open = False
        self.settings_panel_rect: pygame.Rect | None = None
        self._init_music()

        self.player: Player | None = None
        self.current_year = STARTING_YEAR
        self.current_month = STARTING_MONTH
        self.current_century = year_to_century(self.current_year)
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self.market_cache: Dict[Tuple[int, int, str, str], Dict[str, int]] = {}
        self.economy_engine = AtheriaEconomyEngine()
        economy_year = self.current_year + (self.current_month - 1) / 12.0
        self.economy_state = self.economy_engine.for_year(
            year=economy_year,
            sea_state=self.current_sea_state,
            goods=self._active_goods().keys(),
            cities=CITIES,
        )
        self.world_economy = WorldEconomy()
        self.npcs: List[NPCTrader] = []
        self.last_world_tick: Dict[str, int] = {
            "producing_buildings": 0,
            "npc_trades": 0,
            "cities_bankrupt": 0,
            "total_tax": 0,
            "net_migration": 0,
            "disease_cases": 0,
            "disease_deaths": 0,
        }
        self.last_dividend_pools: Dict[str, Dict[str, int]] = {}
        self.research_manager = ResearchManager()
        self.sophia_spend_total = 0.0
        self.global_loss_value = 0.0
        self._ensure_world_state(reset_world=True, reset_npcs=True)

        self.selected_slot = 1
        self.selected_good = 0
        self.market_goods_offset = 0
        self.transfer_goods_offset = 0
        self.city_goods_offset = 0
        self.shipyard_offset = 0
        self.selected_dest = 0
        self.trade_qty = 5
        self.selected_ship_type = 0
        self.selected_fleet_ship = 0
        self.fleet_scroll = 0
        self.shipyard_open = False
        self.ship_cargo_open = False
        self.ship_editor_open = False
        self.ship_editor_ship: Ship | None = None
        self.ship_name_edit = ""
        self.ship_name_active = False
        self.save_menu_open = False
        self.save_menu_mode: str | None = None
        self.city_market_open = False
        self.missions_open = False
        self.info_open = False
        self.about_open = False
        self.selected_city_market = 0
        self.city_market_node_offset = 0
        self.selected_city_building_recipe = ""
        self.selected_city_good = 0
        self.transfer_drag_good: str | None = None
        self.transfer_drag_value = 0
        self.preview_destination: str | None = None
        self.cheat_open = False
        self.cheat_text = ""
        self.marriage_popup_open = False
        self.marriage_candidate = ""
        self.child_name_popup_open = False
        self.child_name_edit = ""
        self.text_input_enabled = False
        self.auto_mode = False
        self.auto_next_tick = 0
        self.auto_popup_hold_until = 0
        self.auto_last_ship_build_month = -9999
        self.time_limit_reached = False
        self.selected_weapon_century = self.current_century
        self.fleet_drag_active = False
        self.fleet_drag_start_y = 0
        self.fleet_drag_start_scroll = 0
        self.fleet_drag_moved = False
        self.info_scroll = 0
        self.info_max_scroll = 0
        self.city_analysis_scroll = 0

        self.new_name = ""
        self.new_gender = "m"
        self.new_city = 0

        self.button_states: Dict[str, Tuple[pygame.Rect, bool]] = {}
        self.goods_rows: List[Tuple[int, pygame.Rect]] = []
        self.city_rows: List[Tuple[int, pygame.Rect]] = []
        self.fleet_rows: List[Tuple[int, pygame.Rect]] = []
        self.slot_rows: List[Tuple[int, pygame.Rect]] = []
        self.ship_rows: List[Tuple[int, pygame.Rect]] = []
        self.dest_rows: List[Tuple[int, pygame.Rect]] = []
        self.dest_scroll = 0
        self.dest_list_rect: pygame.Rect | None = None
        self.city_market_rows: List[Tuple[int, pygame.Rect]] = []
        self.city_building_rows: List[Tuple[str, pygame.Rect]] = []
        self.city_building_offset = 0
        self.city_building_list_rect: pygame.Rect | None = None
        self.city_price_rows: List[Tuple[int, pygame.Rect]] = []
        self.city_analysis_rect: pygame.Rect | None = None
        self.city_analysis_lines: List[str] = []
        self.transfer_sliders: List[Tuple[str, pygame.Rect, int, int]] = []
        self.ship_name_input_rect: pygame.Rect | None = None
        self.child_name_input_rect: pygame.Rect | None = None
        self.about_panel_rect: pygame.Rect | None = None
        self.editor_weapon_rows: List[Tuple[int, pygame.Rect]] = []
        self.editor_weapon_list_rect: pygame.Rect | None = None
        self.editor_weapon_offset = 0
        self.editor_weapon_visible_cache = 5
        self.city_dashboard_cache: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
        self._market_breakdown_cache: Dict[Tuple[int, int, str, str], Dict[str, Dict[str, float]]] = {}
        self.messages: List[str] = [
            "Willkommen in Hanse (pygame).",
            "Neues Spiel anlegen oder Slot laden.",
        ]

    def _read_ui_settings(self) -> Dict[str, Any]:
        try:
            if self.settings_path.exists():
                raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return dict(raw)
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def _load_ui_language(self) -> str:
        raw = self._read_ui_settings()
        lang = str(raw.get("ui_language", "de")).strip().lower()
        if lang in UI_LANGUAGES:
            return lang
        return "de"

    def _load_music_enabled(self) -> bool:
        raw = self._read_ui_settings()
        return bool(raw.get("music_enabled", True))

    def _load_music_volume(self) -> float:
        raw = self._read_ui_settings()
        try:
            volume = float(raw.get("music_volume", DEFAULT_MUSIC_VOLUME))
        except (TypeError, ValueError):
            volume = DEFAULT_MUSIC_VOLUME
        return self._clamp(volume, 0.0, 1.0)

    def _save_ui_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "ui_language": self.ui_language,
                "music_enabled": bool(self.music_enabled),
                "music_volume": round(float(self.music_volume), 2),
            }
            self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _save_ui_language(self) -> None:
        self._save_ui_settings()

    def _set_ui_language(self, lang: str) -> None:
        normalized = str(lang).strip().lower()
        if normalized not in UI_LANGUAGES:
            return
        if normalized == self.ui_language:
            return
        self.ui_language = normalized
        self._ui_translation_cache = {}
        self._save_ui_language()
        if self.ui_language == "en":
            self._log("Language switched to English.")
        else:
            self._log("Sprache auf Deutsch umgestellt.")

    def _resolve_music_path(self) -> Path:
        asset_root = _runtime_asset_root()
        launcher_dir = Path(sys.argv[0]).resolve().parent
        candidates = [
            asset_root / "Hanse_Atheria.ogg",
            asset_root / "Hanse_Atheria.opus",
            launcher_dir / "Hanse_Atheria.ogg",
            launcher_dir / "Hanse_Atheria.opus",
            launcher_dir / "HP_Game" / "Hanse_Atheria.ogg",
            launcher_dir / "HP_Game" / "Hanse_Atheria.opus",
        ]
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                return candidate
        return asset_root / "Hanse_Atheria.ogg"

    def _can_play_music(self) -> bool:
        if not bool(getattr(self, "music_available", False)):
            return False
        self.music_path = self._resolve_music_path()
        return bool(self.music_path.exists())

    def _init_music(self) -> None:
        self.music_available = False
        self._music_loaded = False
        try:
            if pygame.mixer.get_init() is None:
                if self.is_android:
                    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
                else:
                    pygame.mixer.init()
            self.music_available = pygame.mixer.get_init() is not None
        except Exception:
            self.music_available = False
        self._apply_music_settings(force_restart=True)

    def _apply_music_settings(self, *, force_restart: bool = False) -> None:
        self.music_path = self._resolve_music_path()
        self.music_volume = self._clamp(float(self.music_volume), 0.0, 1.0)
        if not self._can_play_music():
            self._music_loaded = False
            try:
                if pygame.mixer.get_init() is not None:
                    pygame.mixer.music.stop()
            except Exception:
                pass
            return
        try:
            pygame.mixer.music.set_volume(self.music_volume)
            if not self.music_enabled:
                pygame.mixer.music.stop()
                self._music_loaded = False
                return
            if force_restart or not self._music_loaded:
                pygame.mixer.music.load(str(self.music_path))
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play(-1)
                self._music_loaded = True
                return
            if not pygame.mixer.music.get_busy():
                pygame.mixer.music.play(-1)
        except Exception:
            self._music_loaded = False

    def _set_music_enabled(self, enabled: bool) -> None:
        new_value = bool(enabled)
        if new_value == bool(self.music_enabled):
            self._apply_music_settings(force_restart=False)
            return
        self.music_enabled = new_value
        self._save_ui_settings()
        self._apply_music_settings(force_restart=new_value)

    def _set_music_volume(self, volume: float) -> None:
        new_value = self._clamp(float(volume), 0.0, 1.0)
        if abs(new_value - float(self.music_volume)) < 0.001:
            self._apply_music_settings(force_restart=False)
            return
        self.music_volume = new_value
        self._save_ui_settings()
        self._apply_music_settings(force_restart=False)

    def _adjust_music_volume(self, delta: float) -> None:
        self._set_music_volume(float(self.music_volume) + float(delta))

    def _translate_ui_text(self, text: str) -> str:
        source = str(text)
        if self.ui_language != "en":
            return source
        cached = self._ui_translation_cache.get(source)
        if cached is not None:
            return cached
        exact = UI_EN_EXACT.get(source)
        if exact is not None:
            self._ui_translation_cache[source] = exact
            return exact
        result = UI_EN_REPLACE_PATTERN.sub(lambda match: UI_EN_REPLACE_MAP[match.group(0)], source)
        self._ui_translation_cache[source] = result
        return result

    def _active_goods(self) -> Dict[str, Dict[str, float]]:
        return goods_for_year(self.current_year)

    def _active_good_names(self) -> List[str]:
        return list(self._active_goods().keys())

    def _unlocked_remote_regions(self) -> List[str]:
        return list(remote_regions_for_year(self.current_year))

    def _all_trade_nodes(self) -> List[str]:
        return list(CITIES) + self._unlocked_remote_regions()

    def _is_remote_region(self, name: str) -> bool:
        return str(name) in REMOTE_TRADE_REGIONS

    def _trade_region_config(self, name: str) -> Dict[str, int | float | str]:
        return dict(REMOTE_TRADE_REGIONS.get(str(name), {}))

    def _available_trade_destinations(self, origin: str) -> List[str]:
        origin_name = str(origin)
        return [node for node in self._all_trade_nodes() if node != origin_name]

    def _travel_distance_units(self, origin: str, target: str) -> int:
        origin_name = str(origin)
        target_name = str(target)
        origin_remote = self._is_remote_region(origin_name)
        target_remote = self._is_remote_region(target_name)
        if origin_remote and target_remote:
            origin_cfg = self._trade_region_config(origin_name)
            target_cfg = self._trade_region_config(target_name)
            return max(
                4,
                int(
                    round(
                        (
                            int(origin_cfg.get("distance", 6))
                            + int(target_cfg.get("distance", 6))
                        )
                        * 0.75
                    )
                ),
            )
        if not origin_remote and not target_remote:
            return abs(CITIES.index(origin_name) - CITIES.index(target_name)) + 1
        if target_remote:
            return max(2, int(self._trade_region_config(target_name).get("distance", 6)))
        if origin_remote:
            return max(2, int(self._trade_region_config(origin_name).get("distance", 6)))
        return 1

    def _travel_cost_for_route(self, origin: str, target: str) -> int:
        origin_name = str(origin)
        target_name = str(target)
        origin_remote = self._is_remote_region(origin_name)
        target_remote = self._is_remote_region(target_name)
        if origin_remote and target_remote:
            origin_cost = int(self._trade_region_config(origin_name).get("travel_cost", 320))
            target_cost = int(self._trade_region_config(target_name).get("travel_cost", 320))
            return max(180, int(round((origin_cost + target_cost) * 0.72)))
        if not origin_remote and not target_remote:
            distance = self._travel_distance_units(origin_name, target_name)
            return 60 + distance * 25
        if target_remote:
            base_cost = int(self._trade_region_config(target_name).get("travel_cost", 320))
            return max(120, base_cost)
        if origin_remote:
            base_cost = int(self._trade_region_config(origin_name).get("travel_cost", 320))
            return max(120, base_cost)
        return 60

    def _remote_region_default_buildings(self, region_name: str) -> List[Building]:
        buildings: List[Building] = []
        for recipe_id in REMOTE_REGION_BUILDING_IDS.get(region_name, []):
            unlock = RECIPE_UNLOCK_CENTURY.get(recipe_id, 99)
            if unlock > self.current_century:
                continue
            level = max(1, 1 + max(0, self.current_century - unlock) // 2)
            buildings.append(Building(id=recipe_id, level=min(CITY_INDUSTRY_LEVEL_MAX, level), active=True))
        return buildings

    def _remote_goods_presence_bonus(self, city: CityEconomy) -> float:
        bonus = 0.0
        for region_goods in REMOTE_REGION_MIGRATION_GOODS.values():
            for good_name in region_goods:
                stock = max(0, int(city.inventory.get(good_name, 0)))
                if stock <= 0:
                    continue
                bonus += min(0.30, stock / 900.0)
        return min(2.5, bonus)

    def _stable_remote_stock_for(self, region_name: str, good_name: str) -> int:
        unlock_century = int(self._trade_region_config(region_name).get("unlock_century", 14))
        base_stock = max(120, int(self._stable_stock_for(region_name, good_name)))
        century_scale = 1.0 + max(0, self.current_century - unlock_century) * 0.14
        export_scale = float(REMOTE_REGION_EXPORT_BONUS.get(region_name, {}).get(good_name, 0.55))
        return max(160, int(round(base_stock * (1.35 + export_scale) * century_scale)))

    def _active_shipyard(self) -> List[Tuple[str, int, int, int]]:
        return modern_shipyard_for_year(self.current_year)

    def _fleet_synergy_shipyard(self) -> List[Tuple[str, int, int, int]]:
        return shipyard_for_year(STARTING_YEAR)

    def _active_titles(self) -> List[Tuple[int, str, str]]:
        return title_steps_for_year(self.current_year)

    def _active_weapon_profile(self) -> Dict[str, float | int | str]:
        return weapon_profile_for_year(self.current_year)

    def _available_weapon_centuries(self) -> List[int]:
        return list(range(14, max(14, int(self.current_century)) + 1))

    def _normalize_selected_weapon_century(self) -> int:
        centuries = self._available_weapon_centuries()
        current = int(getattr(self, "selected_weapon_century", self.current_century))
        if current not in centuries:
            current = centuries[-1]
        self.selected_weapon_century = current
        return current

    def _selected_weapon_profile(self) -> Dict[str, float | int | str]:
        return weapon_profile_for_century(self._normalize_selected_weapon_century())

    def _shift_selected_weapon_century(self, delta: int) -> None:
        centuries = self._available_weapon_centuries()
        current = self._normalize_selected_weapon_century()
        idx = centuries.index(current)
        idx = max(0, min(len(centuries) - 1, idx + int(delta)))
        self.selected_weapon_century = centuries[idx]

    def _active_cannon_cost(self) -> int:
        profile = self._active_weapon_profile()
        return int(profile.get("cannon_cost", CANNON_COST))

    def _active_cannon_power(self) -> float:
        profile = self._active_weapon_profile()
        return float(profile.get("cannon_power", 1.0))

    def _max_cannons(self, ship: Ship) -> int:
        return max_cannons_for_ship(ship.name, ship.cargo_capacity, self.current_year)

    def _ship_cannon_power(self, ship: Ship) -> float:
        inventory = getattr(ship, "cannon_inventory", {})
        if not isinstance(inventory, dict) or not inventory:
            return self._active_cannon_power()
        weighted = 0.0
        total = 0
        for raw_century, raw_qty in inventory.items():
            try:
                century_i = max(14, int(raw_century))
                qty_i = max(0, int(raw_qty))
            except (TypeError, ValueError):
                continue
            if qty_i <= 0:
                continue
            profile = weapon_profile_for_century(century_i)
            weighted += float(profile.get("cannon_power", 1.0)) * qty_i
            total += qty_i
        if total <= 0:
            return self._active_cannon_power()
        return weighted / total

    def _ship_cannon_avg_cost(self, ship: Ship) -> int:
        inventory = getattr(ship, "cannon_inventory", {})
        if not isinstance(inventory, dict) or not inventory:
            return self._active_cannon_cost()
        weighted = 0.0
        total = 0
        for raw_century, raw_qty in inventory.items():
            try:
                century_i = max(14, int(raw_century))
                qty_i = max(0, int(raw_qty))
            except (TypeError, ValueError):
                continue
            if qty_i <= 0:
                continue
            profile = weapon_profile_for_century(century_i)
            weighted += int(profile.get("cannon_cost", CANNON_COST)) * qty_i
            total += qty_i
        if total <= 0:
            return self._active_cannon_cost()
        return max(1, int(round(weighted / total)))

    def _stable_stock_for(self, city_name: str, good_name: str) -> int:
        seed = f"{city_name}:{good_name}:hanse-world-stock"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        span = WORLD_INITIAL_STOCK_MAX - WORLD_INITIAL_STOCK_MIN + 1
        return WORLD_INITIAL_STOCK_MIN + (int.from_bytes(digest[:8], "big") % span)

    def _unlocked_recipe_ids(self, century: int | None = None) -> List[str]:
        century_i = (
            century
            if century is not None
            else int(getattr(self, "current_century", year_to_century(self.current_year)))
        )
        return [
            recipe_id
            for recipe_id in sorted(
                PRODUCTION_RECIPES.keys(),
                key=lambda rid: (RECIPE_UNLOCK_CENTURY.get(rid, 14), rid),
            )
            if RECIPE_UNLOCK_CENTURY.get(recipe_id, 14) <= century_i
        ]

    def _city_building_level(self, city_name: str, recipe_id: str) -> int:
        city_bonus = CITY_RECIPE_LEVEL_BONUS.get(city_name, {})
        return max(1, int(city_bonus.get(recipe_id, 1)))

    def _default_city_buildings(self, city_name: str) -> List[Building]:
        return [
            Building(id=recipe_id, level=self._city_building_level(city_name, recipe_id))
            for recipe_id in self._unlocked_recipe_ids()
        ]

    def _sync_city_buildings_for_century(self, city_name: str, buildings: List[Building]) -> List[Building]:
        result: List[Building] = []
        seen: set[str] = set()
        for building in buildings:
            if building.id in seen:
                continue
            seen.add(building.id)
            result.append(
                Building(
                    id=building.id,
                    level=max(1, int(building.level)),
                    active=bool(building.active),
                )
            )
        for recipe_id in self._unlocked_recipe_ids():
            if recipe_id in seen:
                continue
            seen.add(recipe_id)
            result.append(
                Building(
                    id=recipe_id,
                    level=self._city_building_level(city_name, recipe_id),
                    active=True,
                )
            )
        return result

    def _default_npcs(self) -> List[NPCTrader]:
        goods = self._active_good_names()

        def _ship_for_city(city_name: str) -> Ship:
            ship = Ship(
                name="Holk",
                cargo_capacity=170,
                value=5600,
                city=city_name,
                cargo={good_name: 0 for good_name in goods},
            )
            self._apply_auto_ship_name(ship)
            return ship

        used_names: set[str] = set()

        def _npc_name() -> str:
            for _ in range(24):
                candidate = self._next_auto_person_name()
                if candidate.lower() not in used_names:
                    used_names.add(candidate.lower())
                    return candidate
            fallback = self._next_auto_person_name()
            used_names.add(fallback.lower())
            return fallback

        return [
            NPCTrader(name=_npc_name(), city="Bergen", money=7600, ship=_ship_for_city("Bergen")),
            NPCTrader(name=_npc_name(), city="Luebeck", money=7800, ship=_ship_for_city("Luebeck")),
            NPCTrader(name=_npc_name(), city="Novgorod", money=7400, ship=_ship_for_city("Novgorod")),
        ]

    def _ensure_world_state(
        self,
        *,
        reset_world: bool = False,
        reset_npcs: bool = False,
    ) -> None:
        active_goods = self._active_good_names()
        if reset_world or not isinstance(self.world_economy, WorldEconomy):
            self.world_economy = WorldEconomy()

        for city_name in CITIES:
            city = self.world_economy.cities.get(city_name)
            if city is None:
                city = CityEconomy(name=city_name)
                self.world_economy.cities[city_name] = city
            else:
                city.name = city_name

            for good_name in active_goods:
                raw_stock = city.inventory.get(good_name)
                if raw_stock is None:
                    city.inventory[good_name] = self._stable_stock_for(city_name, good_name)
                else:
                    try:
                        city.inventory[good_name] = max(0, int(raw_stock))
                    except (TypeError, ValueError):
                        city.inventory[good_name] = self._stable_stock_for(city_name, good_name)

            sanitized_buildings: List[Building] = []
            for building in city.buildings:
                if building.id not in PRODUCTION_RECIPES:
                    continue
                sanitized_buildings.append(
                    Building(
                        id=building.id,
                        level=max(1, int(building.level)),
                        active=bool(building.active),
                    )
                )
            city.buildings = self._sync_city_buildings_for_century(
                city_name,
                sanitized_buildings or self._default_city_buildings(city_name),
            )
            try:
                city.treasury = int(city.treasury)
            except (TypeError, ValueError):
                city.treasury = 0
            try:
                city.population = max(CITY_POP_MIN, min(CITY_POP_MAX, int(city.population)))
            except (TypeError, ValueError):
                city.population = 2400
            try:
                city.infrastructure = max(0.6, float(city.infrastructure))
            except (TypeError, ValueError):
                city.infrastructure = 1.0
            try:
                city.social_stability = self._clamp(float(city.social_stability), 4.0, 100.0)
            except (TypeError, ValueError):
                city.social_stability = 50.0
            try:
                city.quality_of_life = self._clamp(float(city.quality_of_life), 4.0, 100.0)
            except (TypeError, ValueError):
                city.quality_of_life = 50.0
            try:
                city.disease_pressure = self._clamp(float(city.disease_pressure), 0.0, 1.2)
            except (TypeError, ValueError):
                city.disease_pressure = 0.0
            try:
                city.disease_cases = max(0, int(city.disease_cases))
            except (TypeError, ValueError):
                city.disease_cases = 0
            try:
                city.child_survival_rate = self._clamp(float(city.child_survival_rate), 0.15, 0.999)
            except (TypeError, ValueError):
                city.child_survival_rate = 0.75
            try:
                city.doctor_coverage = self._clamp(float(city.doctor_coverage), 0.0, 1.5)
            except (TypeError, ValueError):
                city.doctor_coverage = 0.0
            max_survival_by_services = self._clamp(
                0.32
                + city.doctor_coverage * 0.30
                + self._institution_level(city, "hospital") * 0.012
                + self._institution_level(city, "sanitation") * 0.010
                - city.disease_pressure * 0.20,
                0.12,
                0.995,
            )
            city.child_survival_rate = min(float(city.child_survival_rate), float(max_survival_by_services))
            try:
                city.local_scarcity_relief = self._clamp(float(city.local_scarcity_relief), 0.0, 0.55)
            except (TypeError, ValueError):
                city.local_scarcity_relief = 0.0
            try:
                city.hazard_mitigation = self._clamp(float(city.hazard_mitigation), 0.0, 0.85)
            except (TypeError, ValueError):
                city.hazard_mitigation = 0.0
            try:
                city.storage_multiplier = max(1.0, float(city.storage_multiplier))
            except (TypeError, ValueError):
                city.storage_multiplier = 1.0
            try:
                city.tax_income = max(0, min(2_500_000_000, int(city.tax_income)))
            except (TypeError, ValueError):
                city.tax_income = 0
            try:
                city.migration = max(-1_000_000, min(1_000_000, int(city.migration)))
            except (TypeError, ValueError):
                city.migration = 0
            city.bankrupt = 1 if city.treasury <= CITY_BANKRUPTCY_LIMIT else int(bool(city.bankrupt))
            if not isinstance(city.institutions, dict):
                city.institutions = {}
            if not isinstance(city.monuments, dict):
                city.monuments = {}
            self._normalize_social_classes(city)
            self._apply_century_city_template(city_name, city)
            self._scale_city_industry(city_name, city)

        for region_name in self._unlocked_remote_regions():
            region = self.world_economy.cities.get(region_name)
            if region is None:
                region = CityEconomy(name=region_name)
                self.world_economy.cities[region_name] = region
            else:
                region.name = region_name
            for good_name in active_goods:
                raw_stock = region.inventory.get(good_name)
                preferred_stock = self._stable_remote_stock_for(region_name, good_name)
                if raw_stock is None:
                    region.inventory[good_name] = preferred_stock
                else:
                    try:
                        region.inventory[good_name] = max(preferred_stock // 2, int(raw_stock))
                    except (TypeError, ValueError):
                        region.inventory[good_name] = preferred_stock
            sanitized_buildings = [
                Building(id=building.id, level=max(1, int(building.level)), active=bool(building.active))
                for building in region.buildings
                if building.id in PRODUCTION_RECIPES
            ]
            region.buildings = sanitized_buildings or self._remote_region_default_buildings(region_name)
            region.treasury = max(8_000, int(getattr(region, "treasury", 0)))
            region.population = max(CITY_POP_MIN, min(CITY_POP_MAX, int(getattr(region, "population", 1800))))
            region.infrastructure = self._clamp(float(getattr(region, "infrastructure", 1.2)), 1.0, 5.0)
            region.social_stability = self._clamp(float(getattr(region, "social_stability", 62.0)), 20.0, 100.0)
            region.quality_of_life = self._clamp(float(getattr(region, "quality_of_life", 58.0)), 20.0, 100.0)
            region.disease_pressure = self._clamp(float(getattr(region, "disease_pressure", 0.08)), 0.0, 1.0)
            region.child_survival_rate = self._clamp(float(getattr(region, "child_survival_rate", 0.72)), 0.30, 0.995)
            region.doctor_coverage = self._clamp(float(getattr(region, "doctor_coverage", 0.25)), 0.0, 1.2)
            region.migration = int(getattr(region, "migration", 0))
            region.tax_income = max(0, int(getattr(region, "tax_income", 0)))
            region.bankrupt = 0
            if not isinstance(region.institutions, dict):
                region.institutions = {}
            for inst_key in ("harbor", "exchange", "warehouse"):
                region.institutions[inst_key] = max(1, int(region.institutions.get(inst_key, 1)))
            if not isinstance(region.monuments, dict):
                region.monuments = {}
            self._normalize_social_classes(region)

        if reset_npcs or not isinstance(self.npcs, list):
            self.npcs = self._default_npcs()

        sanitized_npcs: List[NPCTrader] = []
        valid_nodes = set(self._all_trade_nodes())
        for npc in self.npcs:
            if not isinstance(npc, NPCTrader):
                continue
            if npc.city not in valid_nodes:
                npc.city = CITIES[0]
            if not isinstance(npc.ship, Ship):
                npc.ship = Ship(city=npc.city, cargo={good_name: 0 for good_name in active_goods})
            npc.ship.city = npc.city
            for good_name in active_goods:
                npc.ship.cargo.setdefault(good_name, 0)
            for good_name in list(npc.ship.cargo.keys()):
                try:
                    npc.ship.cargo[good_name] = max(0, int(npc.ship.cargo[good_name]))
                except (TypeError, ValueError):
                    npc.ship.cargo[good_name] = 0
            npc.money = max(0, int(npc.money))
            npc.ship.cargo_capacity = max(40, int(npc.ship.cargo_capacity))
            npc.ship.hull = max(1, min(100, int(npc.ship.hull)))
            npc.ship.rigging = max(1, min(100, int(npc.ship.rigging)))
            sanitized_npcs.append(npc)
        self.npcs = sanitized_npcs or self._default_npcs()

    def _city_economy(self, city_name: str) -> CityEconomy:
        self._ensure_world_state()
        city = self.world_economy.get_or_create_city(city_name, self._active_good_names(), default_stock=0)
        for good_name in self._active_good_names():
            if good_name not in city.inventory:
                if self._is_remote_region(city_name):
                    city.inventory[good_name] = self._stable_remote_stock_for(city_name, good_name)
                else:
                    city.inventory[good_name] = self._stable_stock_for(city_name, good_name)
        return city

    def _city_inventory_qty(self, city_name: str, good_name: str) -> int:
        city = self._city_economy(city_name)
        return max(0, int(city.inventory.get(good_name, 0)))

    def _city_storage_capacity_from_city(self, city: CityEconomy) -> int:
        current_century = max(14, int(getattr(self, "current_century", year_to_century(self.current_year))))
        base = 380
        pop_part = int(math.sqrt(max(0, int(city.population))) * 16.0)
        infra_part = int(max(0.0, float(city.infrastructure)) * 46)
        institution_part = int(
            max(0, int(city.institutions.get("warehouse", 0))) * 120
            + max(0, int(city.institutions.get("sanitation", 0))) * 35
        )
        century_part = max(0, current_century - 14) * 58
        multiplier = max(1.0, float(city.storage_multiplier))
        capacity = int(round((base + pop_part + infra_part + institution_part + century_part) * multiplier))
        return max(180, capacity)

    def _city_population_capacity(self, city_name: str, city: CityEconomy | None = None) -> int:
        city_obj = city or self._city_economy(city_name)
        current_century = max(14, int(getattr(self, "current_century", year_to_century(self.current_year))))
        storage_capacity = float(self._city_storage_capacity_from_city(city_obj))
        sanitation_lvl = self._institution_level(city_obj, "sanitation")
        warehouse_lvl = self._institution_level(city_obj, "warehouse")
        hospital_lvl = self._institution_level(city_obj, "hospital")
        doctor_lvl = self._institution_level(city_obj, "doctors")
        infrastructure = max(0.6, float(city_obj.infrastructure))
        buildings_total = max(1, sum(max(1, int(entry.level)) for entry in city_obj.buildings))

        food_stock = (
            int(city_obj.inventory.get("Getreide", 0))
            + int(city_obj.inventory.get("Hering", 0))
            + int(city_obj.inventory.get("Salz", 0))
        )
        food_capacity = int(
            max(320.0, float(food_stock))
            * (5.6 + sanitation_lvl * 0.10 + infrastructure * 0.12)
        )
        housing_capacity = int(
            1800
            + storage_capacity * 2.6
            + infrastructure * 900
            + warehouse_lvl * 450
            + sanitation_lvl * 380
            + hospital_lvl * 220
            + doctor_lvl * 180
            + max(0, current_century - 14) * 620
            + math.sqrt(max(1, buildings_total)) * 320
        )
        capacity = min(food_capacity, housing_capacity)
        return max(CITY_POP_MIN, min(CITY_POP_MAX, int(capacity)))

    def _scale_city_industry(self, city_name: str, city: CityEconomy) -> None:
        current_century = max(14, int(getattr(self, "current_century", year_to_century(self.current_year))))
        unlocked_ids = [
            recipe_id
            for recipe_id in sorted(
                PRODUCTION_RECIPES.keys(),
                key=lambda rid: (RECIPE_UNLOCK_CENTURY.get(rid, 14), rid),
            )
            if RECIPE_UNLOCK_CENTURY.get(recipe_id, 14) <= current_century
        ]
        if not unlocked_ids:
            return

        if not city.buildings:
            city.buildings = [Building(id=recipe_id, level=1, active=True) for recipe_id in unlocked_ids[:4]]

        unlocked_set = set(unlocked_ids)
        city.buildings = [entry for entry in city.buildings if entry.id in unlocked_set]
        if not city.buildings:
            city.buildings = [Building(id=recipe_id, level=1, active=True) for recipe_id in unlocked_ids[:4]]

        target_slots = max(
            len(unlocked_ids),
            min(CITY_INDUSTRY_SLOTS_MAX, int(max(1, city.population) / 80_000) + len(unlocked_ids)),
        )
        if len(city.buildings) < target_slots:
            cycle_idx = 0
            while len(city.buildings) < target_slots:
                city.buildings.append(Building(id=unlocked_ids[cycle_idx % len(unlocked_ids)], level=1, active=True))
                cycle_idx += 1

        scale_denominator = max(40, 105 - (current_century - 14) * 5)
        target_total_levels = max(
            len(city.buildings),
            min(90_000, int(max(1, city.population) / scale_denominator)),
        )
        current_total = sum(max(1, int(entry.level)) for entry in city.buildings)
        if current_total < target_total_levels:
            missing = target_total_levels - current_total
            remaining = len(city.buildings)
            for entry in city.buildings:
                if remaining <= 0:
                    break
                add = max(1, missing // remaining)
                entry.level = min(CITY_INDUSTRY_LEVEL_MAX, max(1, int(entry.level)) + add)
                missing -= add
                remaining -= 1
                if missing <= 0:
                    break
        elif current_total > target_total_levels * 2 and city.bankrupt:
            excess = current_total - target_total_levels
            remaining = len(city.buildings)
            for entry in city.buildings:
                if remaining <= 0:
                    break
                cut = max(1, excess // remaining)
                entry.level = max(1, max(1, int(entry.level)) - cut)
                excess -= cut
                remaining -= 1
                if excess <= 0:
                    break

        for entry in city.buildings:
            entry.active = bool(entry.active)
            entry.level = max(1, min(CITY_INDUSTRY_LEVEL_MAX, int(entry.level)))

    def _city_storage_capacity(self, city_name: str, good_name: str | None = None) -> int:
        city = self._city_economy(city_name)
        return self._city_storage_capacity_from_city(city)

    def _city_add_inventory(self, city_name: str, good_name: str, qty: int) -> int:
        if qty <= 0:
            return 0
        city = self._city_economy(city_name)
        current = max(0, int(city.inventory.get(good_name, 0)))
        capacity = self._city_storage_capacity(city_name, good_name)
        if capacity <= current:
            return 0
        addable = min(int(qty), max(0, capacity - current))
        if addable <= 0:
            return 0
        city.inventory[good_name] = current + addable
        return int(addable)

    def _city_take_inventory(self, city_name: str, good_name: str, qty: int, min_remaining: int = 0) -> int:
        if qty <= 0:
            return 0
        city = self._city_economy(city_name)
        stock = max(0, int(city.inventory.get(good_name, 0)))
        available = max(0, stock - max(0, int(min_remaining)))
        taken = min(int(qty), available)
        if taken > 0:
            city.inventory[good_name] = stock - taken
        return taken

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _invalidate_analysis_caches(self, city_name: str | None = None) -> None:
        if city_name is None:
            self.city_dashboard_cache.clear()
            self._market_breakdown_cache.clear()
            return
        city_key = str(city_name)
        self.city_dashboard_cache = {
            key: value for key, value in self.city_dashboard_cache.items() if key[2] != city_key
        }
        self._market_breakdown_cache = {
            key: value for key, value in self._market_breakdown_cache.items() if key[3] != city_key
        }

    def _default_auto_policy(self) -> Dict[str, Any]:
        return {
            "risk": 50,
            "reserve_mark": 1400,
            "invest_mode": "balanced",
            "focus_cities": {city_name: True for city_name in CITIES},
        }

    def _player_auto_policy(self) -> Dict[str, Any]:
        if self.player is None:
            return self._default_auto_policy()
        policy = dict(self._default_auto_policy())
        raw = self.player.auto_policy if isinstance(self.player.auto_policy, dict) else {}
        try:
            policy["risk"] = max(0, min(100, int(raw.get("risk", policy["risk"]))))
        except (TypeError, ValueError):
            policy["risk"] = 50
        try:
            policy["reserve_mark"] = max(0, int(raw.get("reserve_mark", policy["reserve_mark"])))
        except (TypeError, ValueError):
            policy["reserve_mark"] = 1400
        invest_mode = str(raw.get("invest_mode", policy["invest_mode"])).strip().lower()
        if invest_mode not in {"conservative", "balanced", "aggressive"}:
            invest_mode = "balanced"
        policy["invest_mode"] = invest_mode
        focus_raw = raw.get("focus_cities", {})
        focus_map = {city_name: True for city_name in CITIES}
        if isinstance(focus_raw, dict):
            for city_name in CITIES:
                focus_map[city_name] = bool(focus_raw.get(city_name, True))
        policy["focus_cities"] = focus_map
        self.player.auto_policy = dict(policy)
        return policy

    def _auto_policy_focus_targets(self, origin_city: str) -> List[str]:
        policy = self._player_auto_policy()
        focus_map = policy.get("focus_cities", {})
        targets = [city_name for city_name in CITIES if city_name != origin_city and bool(focus_map.get(city_name, False))]
        risk = int(policy.get("risk", 50))
        if risk >= 35:
            for region_name in self._unlocked_remote_regions():
                if region_name != origin_city:
                    targets.append(region_name)
        if not targets:
            targets = self._available_trade_destinations(origin_city)
        return targets

    def _auto_route_min_score(self) -> int:
        risk = int(self._player_auto_policy().get("risk", 50))
        return max(20, min(260, int(round(220 - (risk * 2.0)))))

    def _auto_trade_budget_share(self) -> float:
        risk = int(self._player_auto_policy().get("risk", 50))
        return self._clamp(0.35 + (risk / 200.0), 0.35, 0.85)

    def _auto_invest_mode_label(self, mode: str) -> str:
        lookup = {
            "conservative": "Konservativ",
            "balanced": "Ausgewogen",
            "aggressive": "Aggressiv",
        }
        return lookup.get(str(mode).strip().lower(), "Ausgewogen")

    def _auto_policy_adjust_risk(self, delta: int) -> None:
        if self.player is None:
            return
        policy = self._player_auto_policy()
        policy["risk"] = max(0, min(100, int(policy.get("risk", 50)) + int(delta)))
        self.player.auto_policy = dict(policy)
        self._log(f"Auto-Policy: Risiko {policy['risk']}.")

    def _auto_policy_adjust_reserve(self, delta_mark: int) -> None:
        if self.player is None:
            return
        policy = self._player_auto_policy()
        policy["reserve_mark"] = max(0, int(policy.get("reserve_mark", 1400)) + int(delta_mark))
        self.player.auto_policy = dict(policy)
        self._log(f"Auto-Policy: Reserve {policy['reserve_mark']} Mark.")

    def _auto_policy_cycle_invest_mode(self) -> None:
        if self.player is None:
            return
        order = ["conservative", "balanced", "aggressive"]
        policy = self._player_auto_policy()
        current = str(policy.get("invest_mode", "balanced")).strip().lower()
        try:
            idx = order.index(current)
        except ValueError:
            idx = 1
        policy["invest_mode"] = order[(idx + 1) % len(order)]
        self.player.auto_policy = dict(policy)
        self._log(f"Auto-Policy: Invest {self._auto_invest_mode_label(policy['invest_mode'])}.")

    def _auto_policy_toggle_focus_city(self, city_name: str) -> None:
        if self.player is None or city_name not in CITIES:
            return
        policy = self._player_auto_policy()
        focus_map = dict(policy.get("focus_cities", {}))
        focus_map[city_name] = not bool(focus_map.get(city_name, True))
        policy["focus_cities"] = focus_map
        if not any(bool(v) for v in focus_map.values()):
            # Immer mindestens eine Fokusstadt aktiv lassen.
            focus_map[city_name] = True
        self.player.auto_policy = dict(policy)
        state = "AN" if bool(self.player.auto_policy["focus_cities"].get(city_name, True)) else "AUS"
        self._log(f"Auto-Policy: Fokus {city_name} {state}.")

    def _city_dashboard_metrics(self, city_name: str) -> Dict[str, Any]:
        city = self._city_economy(city_name)
        cache_key = (self.current_year, self.current_month, city_name)
        cached = self.city_dashboard_cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        food_stock = (
            city.inventory.get("Getreide", 0)
            + city.inventory.get("Hering", 0)
            + city.inventory.get("Salz", 0)
        )
        food_need = max(140, int(city.population * 0.14))
        food_ratio = food_stock / max(1, food_need)
        population_capacity = max(CITY_POP_MIN, self._city_population_capacity(city_name, city))
        crowding = self._clamp((city.population / max(1.0, population_capacity)) - 1.0, 0.0, 4.5)
        remote_trade_bonus = self._remote_goods_presence_bonus(city)
        hospital_lvl = self._institution_level(city, "hospital")
        doctor_lvl = self._institution_level(city, "doctors")
        sanitation_lvl = self._institution_level(city, "sanitation")
        medical_quality = self._clamp(
            0.20
            + (hospital_lvl * 0.10)
            + (doctor_lvl * 0.14)
            + (sanitation_lvl * 0.07)
            + (float(city.hazard_mitigation) * 0.35),
            0.08,
            1.30,
        )
        institutions_compact = " | ".join(
            f"{name}:{max(0, int(level))}"
            for name, level in sorted(city.institutions.items())
            if max(0, int(level)) > 0
        )
        if not institutions_compact:
            institutions_compact = "-"
        metrics: Dict[str, Any] = {
            "food_ratio": float(food_ratio),
            "crowding": float(crowding),
            "disease_pressure": float(city.disease_pressure),
            "medical_quality": float(medical_quality),
            "migration": int(city.migration),
            "bankruptcy": int(self._city_is_bankrupt(city_name)),
            "institutions": institutions_compact,
            "infrastructure": float(city.infrastructure),
            "population": int(city.population),
            "population_capacity": int(population_capacity),
            "social_stability": float(city.social_stability),
            "quality_of_life": float(city.quality_of_life),
            "doctor_coverage": float(city.doctor_coverage),
            "tax_income": int(city.tax_income),
            "remote_trade_bonus": float(remote_trade_bonus),
        }
        self.city_dashboard_cache[cache_key] = metrics
        return metrics

    def _market_price_breakdown(self, city: str, good_name: str) -> Dict[str, float]:
        cache_key = (self.current_year, self.current_month, self.current_sea_state, city)
        if cache_key not in self._market_breakdown_cache:
            self._market_prices(city)
        city_data = self._market_breakdown_cache.get(cache_key, {})
        entry = city_data.get(good_name)
        if isinstance(entry, dict):
            return dict(entry)
        return {}

    def _format_compact_number(self, value: int | float) -> str:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return "0"
        abs_num = abs(num)
        if abs_num >= 1_000_000_000_000:
            return f"{num / 1_000_000_000_000:.2f}T"
        if abs_num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.2f}B"
        if abs_num >= 1_000_000:
            return f"{num / 1_000_000:.2f}M"
        if abs_num >= 1_000:
            return f"{num / 1_000:.1f}K"
        return str(int(round(num)))

    def _investment_spend_total(self, track: str) -> float:
        if self.player is None:
            return 0.0
        key = str(track).strip().lower()
        if key == TRACK_SOPHIA:
            return max(0.0, float(getattr(self, "sophia_spend_total", 0.0)))
        return max(0.0, float(self.player.investments.get(key, 0.0)))

    def _investment_level(self, track: str) -> int:
        spend_total = self._investment_spend_total(track)
        return self.research_manager.level_from_spend(track, spend_total)

    def _next_investment_cost(self, track: str) -> int:
        return self.research_manager.cost_for_level(track, self._investment_level(track))

    def _manual_investment_minimum(self, track: str) -> int:
        key = str(track).strip().lower()
        if key == TRACK_SOCIAL:
            return SOCIAL_WELFARE_MIN_AMOUNT
        if key == TRACK_SOPHIA:
            next_cost = self.research_manager.cost_for_level(TRACK_SOPHIA, self._investment_level(TRACK_SOPHIA))
        else:
            next_cost = self._next_investment_cost(key)
        base_floor = 10_000 if key == TRACK_RESEARCH else 8_000
        return max(base_floor, int(round(max(1, next_cost) * 0.025)))

    def _manual_investment_click_amount(self, track: str) -> int:
        if self.player is None:
            return 0
        key = str(track).strip().lower()
        minimum = self._manual_investment_minimum(key)
        available = max(0, int(self.player.money))
        if available < minimum:
            return 0
        if key == TRACK_SOPHIA:
            next_cost = self.research_manager.cost_for_level(TRACK_SOPHIA, self._investment_level(TRACK_SOPHIA))
        else:
            next_cost = self._next_investment_cost(key)
        target = max(minimum, available // 5)
        return max(minimum, min(available, next_cost, target))

    def _institution_level(self, city: CityEconomy, key: str) -> int:
        try:
            return max(0, int(city.institutions.get(key, 0)))
        except (TypeError, ValueError):
            return 0

    def _normalize_social_classes(self, city: CityEconomy) -> None:
        defaults = {
            "peasants": 0.72,
            "artisans": 0.18,
            "merchants": 0.08,
            "nobility": 0.02,
        }
        merged: Dict[str, float] = {}
        for key, default_value in defaults.items():
            try:
                merged[key] = max(0.0, float(city.social_classes.get(key, default_value)))
            except (TypeError, ValueError):
                merged[key] = default_value
        total = sum(merged.values())
        if total <= 0:
            city.social_classes = dict(defaults)
            return
        city.social_classes = {key: value / total for key, value in merged.items()}

    def _apply_century_city_template(self, city_name: str, city: CityEconomy) -> None:
        century = max(14, int(getattr(self, "current_century", year_to_century(self.current_year))))
        city.century_stage = max(int(city.century_stage), century)
        for unlock_century in sorted(CENTURY_INSTITUTION_UNLOCKS.keys()):
            if unlock_century > century:
                continue
            institution_map = CENTURY_INSTITUTION_UNLOCKS[unlock_century]
            target_level = 1 + max(0, century - unlock_century) // 3
            for institution_key, base_level in institution_map.items():
                current_level = self._institution_level(city, institution_key)
                desired = max(base_level, min(target_level, base_level + 2))
                if current_level < desired and city.treasury > (unlock_century - 13) * 180:
                    city.institutions[institution_key] = desired

        infra_target = 1.0 + (century - 14) * 0.22
        infra_boost = (city.treasury / 45_000.0) + (self._institution_level(city, "canal") * 0.04)
        city.infrastructure = self._clamp(
            max(float(city.infrastructure), infra_target * 0.92) + max(0.0, infra_boost * 0.01),
            0.6,
            6.5,
        )
        base_qol = 48.0 + (century - 14) * 2.2
        base_stability = 50.0 + (century - 14) * 1.8
        city.quality_of_life = self._clamp(max(float(city.quality_of_life), base_qol * 0.90), 6.0, 100.0)
        city.social_stability = self._clamp(max(float(city.social_stability), base_stability * 0.90), 6.0, 100.0)
        self._normalize_social_classes(city)

    def _city_social_attractiveness(self, city: CityEconomy) -> float:
        bankrupt_penalty = 14.0 if int(city.bankrupt) else 0.0
        institution_weight = sum(max(0, int(level)) for level in city.institutions.values()) * 0.55
        disease_penalty = float(city.disease_pressure) * 24.0 + (
            (float(city.disease_cases) / max(1.0, float(city.population))) * 900.0
        )
        remote_bonus = self._remote_goods_presence_bonus(city) * 4.2
        return (
            float(city.quality_of_life) * 0.52
            + float(city.social_stability) * 0.36
            + float(city.infrastructure) * 11.5
            + institution_weight
            + remote_bonus
            - bankrupt_penalty
            - disease_penalty
        )

    def _simulate_city_society(self) -> Dict[str, int]:
        self._ensure_world_state()
        century = max(14, int(self.current_century))
        attractiveness: Dict[str, float] = {}
        natural_change: Dict[str, int] = {}
        total_tax = 0
        total_disease_cases = 0
        total_disease_deaths = 0

        for city_name in CITIES:
            city = self._city_economy(city_name)
            self._apply_century_city_template(city_name, city)
            self._scale_city_industry(city_name, city)

            food_stock = (
                city.inventory.get("Getreide", 0)
                + city.inventory.get("Hering", 0)
                + city.inventory.get("Salz", 0)
            )
            food_need = max(140, int(city.population * 0.14))
            food_ratio = food_stock / max(1, food_need)
            producing = sum(1 for building in city.buildings if self._can_building_run(city, building))
            production_ratio = producing / max(1, len(city.buildings))
            remote_trade_bonus = self._remote_goods_presence_bonus(city)
            hospital_lvl = self._institution_level(city, "hospital")
            doctor_lvl = self._institution_level(city, "doctors")
            academy_lvl = self._institution_level(city, "academy")
            bank_lvl = self._institution_level(city, "bank")
            digital_lvl = self._institution_level(city, "digital_exchange")
            sanitation_lvl = self._institution_level(city, "sanitation")

            storage_capacity = max(900.0, float(self._city_storage_capacity(city_name)))
            carrying_capacity = max(CITY_POP_MIN, self._city_population_capacity(city_name, city))
            crowding = self._clamp((city.population / max(1.0, carrying_capacity)) - 1.0, 0.0, 4.5)
            capacity_stress = self._clamp((city.population / max(1.0, carrying_capacity)) - 1.0, 0.0, 3.0)
            supply_stress = self._clamp(1.0 - food_ratio, 0.0, 1.6)
            base_disease_pressure = disease_pressure_for_year(self.current_year)
            inflation_pressure = self._clamp(
                (float(self.economy_state.global_price_level) - 1.0) * 1.6,
                0.0,
                2.4,
            )
            medical_quality = self._clamp(
                0.18
                + (hospital_lvl * 0.11)
                + (doctor_lvl * 0.16)
                + (sanitation_lvl * 0.08)
                + (academy_lvl * 0.05)
                + (float(city.hazard_mitigation) * 0.45),
                0.08,
                1.25,
            )
            city.doctor_coverage = self._clamp(
                (hospital_lvl * 0.22 + doctor_lvl * 0.30 + sanitation_lvl * 0.16)
                / max(1.0, city.population / 55_000.0),
                0.0,
                1.5,
            )
            disease_pressure = self._clamp(
                base_disease_pressure
                + (supply_stress * 0.22)
                + (crowding * 0.18)
                + (capacity_stress * 0.26)
                + (inflation_pressure * 0.08)
                + (0.10 if city.bankrupt else 0.0)
                - (medical_quality * 0.20)
                - (city.infrastructure * 0.012),
                0.01,
                0.95,
            )
            outbreak_chance = self._clamp(
                disease_pressure * (0.45 + base_disease_pressure * 1.70),
                0.01,
                0.55,
            )
            if self.rng.random() < outbreak_chance:
                outbreak_factor = self.rng.uniform(0.85, 1.25)
            else:
                outbreak_factor = self.rng.uniform(0.20, 0.65)
            disease_cases = int(
                round(
                    city.population
                    * disease_pressure
                    * (0.008 + base_disease_pressure * 0.036)
                    * outbreak_factor
                )
            )
            disease_cases = max(0, min(int(city.population * 0.35), disease_cases))
            disease_death_rate = self._clamp(
                0.020
                + disease_pressure * 0.075
                + max(0.0, crowding - 0.6) * 0.010
                - medical_quality * 0.028
                - city.doctor_coverage * 0.020,
                0.002,
                0.120,
            )
            disease_deaths = int(round(disease_cases * disease_death_rate))
            city.disease_cases = disease_cases
            city.disease_pressure = disease_pressure
            city.child_survival_rate = self._clamp(
                0.28
                + medical_quality * 0.38
                + city.doctor_coverage * 0.24
                + sanitation_lvl * 0.03
                - child_mortality_for_year(self.current_year) * 0.95
                - disease_pressure * 0.30
                - crowding * 0.10
                - supply_stress * 0.20,
                0.10,
                0.995,
            )
            total_disease_cases += disease_cases
            total_disease_deaths += disease_deaths

            bounded_treasury = self._clamp(float(city.treasury), -50_000.0, 250_000.0)
            prosperity = (
                (bounded_treasury / 4500.0)
                + (production_ratio * 9.0)
                + (bank_lvl * 1.2)
                + (digital_lvl * 0.9)
            )
            disease_burden = disease_pressure * 1.6 + (disease_cases / max(1, city.population)) * 22.0
            qol_delta = (
                (food_ratio - 1.0) * 2.4
                + (production_ratio - 0.45) * 1.4
                + (hospital_lvl * 0.22)
                + (doctor_lvl * 0.17)
                + (academy_lvl * 0.16)
                + (remote_trade_bonus * 0.45)
                + (prosperity * 0.08)
                - (inflation_pressure * 1.05)
                - (disease_burden * 0.75)
            )
            if city.bankrupt:
                qol_delta -= 0.9
            stability_delta = (
                (float(city.quality_of_life) - 50.0) / 130.0
                + (food_ratio - 1.0) * 1.1
                + (city.infrastructure - 1.0) * 0.22
                + (academy_lvl * 0.10)
                + (doctor_lvl * 0.07)
                + (remote_trade_bonus * 0.26)
                - (inflation_pressure * 0.85)
                - (disease_burden * 0.55)
            )
            if city.bankrupt:
                stability_delta -= 1.2

            city.quality_of_life = self._clamp(float(city.quality_of_life) + qol_delta, 4.0, 100.0)
            city.social_stability = self._clamp(float(city.social_stability) + stability_delta, 4.0, 100.0)

            base_growth = 0.00015 + (century - 14) * 0.00005
            growth_mod = (
                (city.quality_of_life - 50.0) / 26_000.0
                + (city.social_stability - 50.0) / 28_000.0
                + (production_ratio - 0.45) / 850.0
                + (remote_trade_bonus / 2400.0)
                - (disease_pressure / 440.0)
                - (inflation_pressure / 420.0)
                - (capacity_stress / 40.0)
                - (supply_stress / 95.0)
            )
            growth_rate = self._clamp(base_growth + growth_mod, -0.018, 0.0035)
            over_capacity = max(0, int(city.population) - int(carrying_capacity))
            collapse_loss = int(round(over_capacity * 0.045))
            starvation_loss = 0
            if food_ratio < 0.72:
                starvation_loss = int(round(city.population * self._clamp((0.72 - food_ratio) * 0.006, 0.0, 0.030)))
            natural_change[city_name] = int(round(city.population * growth_rate)) - disease_deaths - collapse_loss - starvation_loss

            tax_rate = 0.065 + (century - 14) * 0.003
            tax_efficiency = self._clamp(0.58 + city.infrastructure * 0.12 + bank_lvl * 0.03, 0.30, 1.95)
            tax_factor = self._clamp(
                (city.social_stability / 100.0)
                * self._clamp(1.0 - disease_pressure * 0.30 - inflation_pressure * 0.12 + remote_trade_bonus * 0.03, 0.30, 1.10),
                0.25,
                1.20,
            )
            city.tax_income = max(0, min(2_500_000_000, int(round(city.population * tax_rate * tax_efficiency * tax_factor))))
            city.treasury += city.tax_income
            base_maintenance = int(
                28
                + city.population / 2200.0
                + city.infrastructure * 18.0
                + len(city.buildings) * 2.4
                + (hospital_lvl + doctor_lvl + sanitation_lvl) * 9.0
                + disease_cases * 0.12
            )
            city.treasury -= max(0, base_maintenance)
            total_tax += max(0, city.tax_income)
            city.bankrupt = 1 if city.treasury <= CITY_BANKRUPTCY_LIMIT else 0
            city.treasury = int(self._clamp(float(city.treasury), -2_000_000_000.0, 2_000_000_000.0))

            city.political_influence = self._clamp(
                (city.population / 740.0)
                + (city.infrastructure * 5.4)
                + (city.social_stability * 0.25)
                + (city.tax_income / 900.0),
                0.0,
                9999.0,
            )
            attractiveness[city_name] = self._city_social_attractiveness(city)

        average_attractiveness = (
            sum(attractiveness.values()) / len(attractiveness)
            if attractiveness
            else 0.0
        )
        total_migration = 0
        for city_name in CITIES:
            city = self._city_economy(city_name)
            drift = attractiveness.get(city_name, average_attractiveness) - average_attractiveness
            migration_rate = self._clamp(drift / 12_000.0, -0.0025, 0.0025)
            migration_flow = int(round(city.population * migration_rate))
            capacity_now = self._city_population_capacity(city_name, city)
            if city.population > capacity_now:
                overflow = city.population - capacity_now
                migration_flow -= max(5, int(overflow * 0.015))
            if city.bankrupt:
                migration_flow -= max(6, int(city.population * 0.0015))
            city.migration = migration_flow
            total_migration += migration_flow

        for city_name in CITIES:
            city = self._city_economy(city_name)
            delta = natural_change.get(city_name, 0) + int(city.migration)
            if city.bankrupt and city.social_stability < 22.0 and city.quality_of_life < 24.0:
                delta -= max(10, int(city.population * 0.003))
            city.population = max(CITY_POP_MIN, min(CITY_POP_MAX, int(city.population) + int(delta)))

            merchants_target = self._clamp(
                0.08 + (century - 14) * 0.012 + (city.infrastructure - 1.0) * 0.02,
                0.06,
                0.46,
            )
            nobility_target = self._clamp(
                0.02 + (century - 14) * 0.003 + (city.political_influence / 8000.0),
                0.01,
                0.12,
            )
            artisans_target = self._clamp(
                0.18 + (city.infrastructure - 1.0) * 0.03 + (city.quality_of_life - 50.0) / 450.0,
                0.14,
                0.38,
            )
            peasants_target = max(0.12, 1.0 - merchants_target - nobility_target - artisans_target)
            targets = {
                "peasants": peasants_target,
                "artisans": artisans_target,
                "merchants": merchants_target,
                "nobility": nobility_target,
            }
            current = dict(city.social_classes)
            for class_key, target in targets.items():
                try:
                    current_value = float(current.get(class_key, target))
                except (TypeError, ValueError):
                    current_value = target
                current[class_key] = current_value + (target - current_value) * 0.12
            city.social_classes = current
            self._normalize_social_classes(city)

        return {
            "total_tax": int(total_tax),
            "net_migration": int(total_migration),
            "disease_cases": int(total_disease_cases),
            "disease_deaths": int(total_disease_deaths),
        }

    def invest_in_social_welfare(self, player: Player, city: str, amount: int) -> bool:
        if player is None:
            return False
        city_name = str(city)
        if city_name not in CITIES:
            return False
        city_economy = self._city_economy(city_name)
        dashboard = self._city_dashboard_metrics(city_name)
        spend = max(int(amount), self._manual_investment_minimum(TRACK_SOCIAL))
        if player.money < spend:
            self._log(f"Sozialstiftung {city_name}: benoetigt {spend} Mark.")
            return False
        player.money -= spend
        player.investments[TRACK_SOCIAL] = self._investment_spend_total(TRACK_SOCIAL) + spend
        social_level = self._investment_level(TRACK_SOCIAL)
        medical_focus = (
            float(dashboard.get("disease_pressure", 0.0)) >= 0.10
            or float(dashboard.get("medical_quality", 0.0)) < 0.60
            or float(dashboard.get("doctor_coverage", 0.0)) < 0.40
        )
        supply_focus = (
            float(dashboard.get("food_ratio", 1.0)) < 1.05
            or float(dashboard.get("crowding", 0.0)) > 0.15
        )
        city_economy.institutions["academy"] = max(
            self._institution_level(city_economy, "academy"),
            1 + social_level // 3,
        )
        city_economy.institutions["hospital"] = max(
            self._institution_level(city_economy, "hospital"),
            1 + social_level // (2 if medical_focus else 3),
        )
        city_economy.institutions["doctors"] = max(
            self._institution_level(city_economy, "doctors"),
            1 + social_level // (2 if medical_focus else 4),
        )
        if medical_focus:
            city_economy.institutions["sanitation"] = max(
                self._institution_level(city_economy, "sanitation"),
                1 + social_level // 4,
            )
        city_economy.local_scarcity_relief = self._clamp(
            float(city_economy.local_scarcity_relief) + self.research_manager.social_relief_gain(spend),
            0.0,
            0.55,
        )
        if supply_focus:
            city_economy.local_scarcity_relief = self._clamp(
                float(city_economy.local_scarcity_relief) + min(0.08, spend / 250_000.0),
                0.0,
                0.55,
            )
        city_economy.hazard_mitigation = self._clamp(
            float(city_economy.hazard_mitigation) + self.research_manager.hazard_mitigation_gain(spend),
            0.0,
            0.85,
        )
        if medical_focus or supply_focus:
            city_economy.infrastructure = self._clamp(
                float(city_economy.infrastructure) + 0.03 + min(0.18, spend / 500_000.0),
                0.6,
                6.5,
            )
        city_economy.quality_of_life = self._clamp(float(city_economy.quality_of_life) + 0.9 + social_level * 0.12, 4.0, 100.0)
        city_economy.social_stability = self._clamp(float(city_economy.social_stability) + 0.7 + social_level * 0.09, 4.0, 100.0)
        self._add_player_city_influence(city_name, 0.45 + (spend / 22_000.0))
        self.market_cache.clear()
        self._invalidate_analysis_caches(city_name)
        impact_notes: List[str] = []
        if medical_focus:
            impact_notes.append("Medizin ausgebaut")
        if supply_focus:
            impact_notes.append("Versorgung entlastet")
        note_text = f" | {' | '.join(impact_notes)}" if impact_notes else ""
        self._log(
            f"Sozialstiftung {city_name}: -{spend} Mark{note_text} | Knappheitsentlastung {city_economy.local_scarcity_relief:.2f} | "
            f"Gefahrenabwehr {city_economy.hazard_mitigation:.2f}."
        )
        return True

    def _city_bailout_cost(self, city_name: str) -> int:
        city = self._city_economy(city_name)
        debt = max(0, -int(city.treasury))
        return max(BAILOUT_MIN_AMOUNT, int(round(debt * 1.18 + 1200)))

    def execute_city_bailout(self, player: Player, city: str) -> bool:
        if player is None:
            return False
        city_name = str(city)
        if city_name not in CITIES:
            return False
        city_economy = self._city_economy(city_name)
        city_economy.bankrupt = 1 if city_economy.treasury <= CITY_BANKRUPTCY_LIMIT else int(city_economy.bankrupt)
        if city_economy.bankrupt != 1:
            self._log(f"{city_name}: keine akute Rettung noetig.")
            return False
        bailout_cost = self._city_bailout_cost(city_name)
        if player.money < bailout_cost:
            self._log(f"Stadtrettung {city_name}: benoetigt {bailout_cost} Mark.")
            return False
        player.money -= bailout_cost
        city_economy.treasury = max(CITY_RECOVERY_TARGET + 420, int(round(bailout_cost * 0.22)))
        city_economy.bankrupt = 0
        city_economy.storage_multiplier = max(float(city_economy.storage_multiplier), MONUMENT_STORAGE_MULTIPLIER)
        city_economy.monuments[CITY_BAILOUT_MONUMENT_KEY] = city_economy.monuments.get(CITY_BAILOUT_MONUMENT_KEY, 0) + 1
        city_economy.social_stability = self._clamp(float(city_economy.social_stability) + 8.0, 4.0, 100.0)
        city_economy.quality_of_life = self._clamp(float(city_economy.quality_of_life) + 6.0, 4.0, 100.0)
        city_economy.political_influence = self._clamp(float(city_economy.political_influence) + 4.0, 0.0, 9999.0)
        self._add_player_city_influence(city_name, 4.5)
        self.market_cache.clear()
        self._invalidate_analysis_caches(city_name)
        self._log(
            f"Stadtrettung {city_name}: -{bailout_cost} Mark | Stifter-Monument errichtet | Lager x{city_economy.storage_multiplier:.1f}."
        )
        return True

    def invest_in_research_resonance(self, player: Player, amount: int = 0) -> bool:
        if player is None:
            return False
        spend = max(int(amount), self._manual_investment_minimum(TRACK_RESEARCH))
        if player.money < spend:
            self._log(f"Betriebsforschung: benoetigt {spend} Mark.")
            return False
        player.money -= spend
        player.investments[TRACK_RESEARCH] = self._investment_spend_total(TRACK_RESEARCH) + spend
        level = self._investment_level(TRACK_RESEARCH)
        reduction = self.research_manager.efficiency_reduction(level)
        self._log(
            f"Betriebsforschung: -{spend} Mark | Level {level} | Inputbedarf -{reduction * 100:.1f}%."
        )
        return True

    def invest_in_infrastructure(self, player: Player, amount: int = 0) -> bool:
        if player is None:
            return False
        spend = max(int(amount), self._manual_investment_minimum(TRACK_INFRASTRUCTURE))
        if player.money < spend:
            self._log(f"Reise-Infrastruktur: benoetigt {spend} Mark.")
            return False
        player.money -= spend
        player.investments[TRACK_INFRASTRUCTURE] = self._investment_spend_total(TRACK_INFRASTRUCTURE) + spend
        level = self._investment_level(TRACK_INFRASTRUCTURE)
        multiplier = self.research_manager.travel_time_multiplier(level, self.current_year)
        if player.city in CITIES:
            city = self._city_economy(player.city)
            city.infrastructure = self._clamp(float(city.infrastructure) + 0.08 + level * 0.01, 0.6, 6.5)
        self._log(
            f"Reise-Infrastruktur: -{spend} Mark | Level {level} | Reisezeitfaktor {multiplier:.2f}."
        )
        return True

    def invest_in_algorithmic_harmony(self, player: Player, amount: int = 0) -> bool:
        if player is None:
            return False
        spend = max(int(amount), self._manual_investment_minimum(TRACK_SOPHIA))
        if player.money < spend:
            self._log(f"Marktstabilisierung: benoetigt {spend} Mark.")
            return False
        player.money -= spend
        self.sophia_spend_total = max(0.0, float(self.sophia_spend_total) + spend)
        self.global_loss_value = self.research_manager.global_loss_value(self.sophia_spend_total)
        global global_loss_value
        global_loss_value = self.global_loss_value
        self.market_cache.clear()
        self._invalidate_analysis_caches()
        self._log(
            f"Marktstabilisierung: -{spend} Mark | Level {self._investment_level(TRACK_SOPHIA)} | "
            f"Preisschwankung-Daempfung {self.global_loss_value:.2f}."
        )
        return True

    def _travel_turns_for_distance(self, distance: int) -> int:
        base_distance = max(1, int(distance))
        infra_level = self._investment_level(TRACK_INFRASTRUCTURE)
        multiplier = self.research_manager.travel_time_multiplier(infra_level, self.current_year)
        turns = int(math.ceil(base_distance * multiplier))
        return max(1, turns)

    def _player_monument_reputation_multiplier(self) -> float:
        if self.player is None:
            return 1.0
        monuments = 0
        for city_name in CITIES:
            city = self._city_economy(city_name)
            monuments += max(0, int(city.monuments.get(CITY_BAILOUT_MONUMENT_KEY, 0)))
        if monuments <= 0:
            return 1.0
        return self._clamp(1.0 + monuments * MONUMENT_REPUTATION_BONUS, 1.0, 3.0)

    def _player_city_influence(self, city_name: str) -> float:
        if self.player is None:
            return 0.0
        return max(0.0, float(self.player.city_influence.get(city_name, 0.0)))

    def _add_player_city_influence(self, city_name: str, amount: float) -> None:
        if self.player is None or amount == 0:
            return
        current = max(0.0, float(self.player.city_influence.get(city_name, 0.0)))
        self.player.city_influence[city_name] = max(0.0, current + float(amount))

    def _player_building_share_percent(self, city_name: str, recipe_id: str) -> float:
        if self.player is None:
            return 0.0
        city_shares = self.player.building_shares.get(city_name, {})
        return max(0.0, min(MAX_BUILDING_SHARE_PERCENT, float(city_shares.get(recipe_id, 0.0))))

    def _set_player_building_share_percent(self, city_name: str, recipe_id: str, pct: float) -> None:
        if self.player is None:
            return
        if city_name not in self.player.building_shares:
            self.player.building_shares[city_name] = {}
        self.player.building_shares[city_name][recipe_id] = max(0.0, min(MAX_BUILDING_SHARE_PERCENT, float(pct)))

    def _total_building_share_percent(self, city_name: str, recipe_id: str) -> float:
        total = 0.0
        if self.player is not None:
            total += self._player_building_share_percent(city_name, recipe_id)
        return max(0.0, total)

    def _share_price_per_percent(self, city_name: str, building: Building) -> int:
        recipe = PRODUCTION_RECIPES.get(building.id)
        if recipe is None:
            return 120
        active_goods = self._active_goods()
        weighted_output = 0
        for good_name, qty in recipe.outputs.items():
            base_price = int(active_goods.get(good_name, {}).get("base_price", 40))
            weighted_output += max(0, int(qty)) * base_price
        weighted_input = 0
        for good_name, qty in recipe.inputs.items():
            base_price = int(active_goods.get(good_name, {}).get("base_price", 30))
            weighted_input += max(0, int(qty)) * base_price
        century_bonus = max(0, RECIPE_UNLOCK_CENTURY.get(building.id, 14) - 14) * 10
        level_bonus = max(1, int(building.level)) * 30
        model_price = 90 + (weighted_output // 4) - (weighted_input // 7) + level_bonus + century_bonus
        return max(60, model_price)

    def _city_is_bankrupt(self, city_name: str) -> bool:
        city = self._city_economy(city_name)
        city.bankrupt = 1 if int(city.treasury) <= CITY_BANKRUPTCY_LIMIT else int(bool(city.bankrupt))
        return bool(city.bankrupt)

    def _building_dividend_pool(self, city_name: str, recipe_id: str) -> int:
        city_pool = self.last_dividend_pools.get(city_name, {})
        return max(0, int(city_pool.get(recipe_id, 0)))

    def _apply_passive_income(self) -> None:
        if self.player is None:
            return
        total_dividend = 0
        for city_name, share_map in self.player.building_shares.items():
            if not isinstance(share_map, dict):
                continue
            city = self._city_economy(city_name)
            for recipe_id, pct_raw in share_map.items():
                share_pct = max(0.0, min(MAX_BUILDING_SHARE_PERCENT, float(pct_raw)))
                if share_pct <= 0:
                    continue
                pool = self._building_dividend_pool(city_name, recipe_id)
                if pool <= 0:
                    continue
                payout = int(round(pool * (share_pct / 100.0)))
                if payout <= 0:
                    continue
                affordable = max(0, int(city.treasury))
                actual = min(payout, affordable)
                if actual <= 0:
                    continue
                city.treasury -= actual
                total_dividend += actual
                self._add_player_city_influence(city_name, (actual / 1000.0) * INFLUENCE_PER_DIVIDEND_1000)
        if total_dividend > 0:
            self.player.money += total_dividend
            self._log(f"Passive Rendite: +{total_dividend} Mark.")

    def _buy_city_building_shares(self, city_name: str, recipe_id: str, pct: int = 5) -> None:
        if self.player is None:
            return
        city = self._city_economy(city_name)
        building = next((entry for entry in city.buildings if entry.id == recipe_id), None)
        if building is None:
            self._log("Betrieb nicht gefunden.")
            return
        if RECIPE_UNLOCK_CENTURY.get(recipe_id, 14) > self.current_century:
            self._log("Betrieb ist in diesem Jahrhundert noch gesperrt.")
            return
        sold_pct = self._total_building_share_percent(city_name, recipe_id)
        free_pct = max(0.0, MAX_BUILDING_SHARE_PERCENT - sold_pct)
        if free_pct < 1.0:
            self._log("Keine freien Anteile verfuegbar.")
            return
        buy_pct = max(1, min(int(pct), int(free_pct)))
        price_per_pct = self._share_price_per_percent(city_name, building)
        cost = int(round(price_per_pct * buy_pct))
        if self.player.money < cost:
            self._log("Nicht genug Mark fuer Anteilskauf.")
            return
        self.player.money -= cost
        city.treasury += int(round(cost * 0.45))
        current_pct = self._player_building_share_percent(city_name, recipe_id)
        self._set_player_building_share_percent(city_name, recipe_id, current_pct + buy_pct)
        self._add_player_city_influence(city_name, buy_pct * INFLUENCE_PER_SHARE_PURCHASE)
        recipe = PRODUCTION_RECIPES.get(recipe_id)
        label = recipe.name if recipe else recipe_id
        self._log(
            f"Anteilskauf {city_name}: +{buy_pct}% {label} fuer {cost} Mark "
            f"(gesamt {self._player_building_share_percent(city_name, recipe_id):.1f}%)."
        )

    def _bailout_city(self, city_name: str, amount: int = 1000) -> None:
        if self.player is None:
            return
        city = self._city_economy(city_name)
        city.bankrupt = 1 if city.treasury <= CITY_BANKRUPTCY_LIMIT else int(city.bankrupt)
        if city.bankrupt != 1:
            self._log(f"{city_name}: keine Rettung noetig.")
            return
        self.execute_city_bailout(self.player, city_name)

    def _tick_world_production(self) -> int:
        self._ensure_world_state()
        active_goods = set(self._active_good_names())
        current_century = self.current_century
        research_level = self._investment_level(TRACK_RESEARCH)
        efficiency_reduction = self.research_manager.efficiency_reduction(research_level)
        active_buildings = 0
        self.last_dividend_pools = {city_name: {} for city_name in CITIES}
        for city_name in CITIES:
            city = self._city_economy(city_name)
            self._scale_city_industry(city_name, city)
            city.treasury += len(city.buildings) * CITY_TREASURY_BASE_INCOME_PER_BUILDING
            for good_name, base_qty in BASE_CITY_CONSUMPTION.items():
                if good_name not in active_goods:
                    continue
                current = max(0, int(city.inventory.get(good_name, 0)))
                city.inventory[good_name] = max(0, current - max(0, int(base_qty)))

            city_bankrupt = city.treasury <= CITY_BANKRUPTCY_LIMIT
            for idx, building in enumerate(city.buildings):
                if not building.active:
                    continue
                recipe = PRODUCTION_RECIPES.get(building.id)
                if recipe is None:
                    continue
                if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > current_century:
                    continue
                if city_bankrupt and (idx % 2 == 1):
                    continue
                level = max(1, int(building.level))
                can_run = True
                input_total = 0
                for good_name, qty in recipe.inputs.items():
                    base_required = max(0, int(qty)) * level
                    if base_required <= 0:
                        required = 0
                    else:
                        required = max(1, int(math.ceil(base_required * (1.0 - efficiency_reduction))))
                    if city.inventory.get(good_name, 0) < required:
                        can_run = False
                        break
                    input_total += required
                if not can_run:
                    continue

                output_total = 0
                for good_name, qty in recipe.inputs.items():
                    base_required = max(0, int(qty)) * level
                    if base_required <= 0:
                        required = 0
                    else:
                        required = max(1, int(math.ceil(base_required * (1.0 - efficiency_reduction))))
                    city.inventory[good_name] = max(0, int(city.inventory.get(good_name, 0)) - required)
                for good_name, qty in recipe.outputs.items():
                    produced = max(0, int(qty)) * level
                    if good_name not in active_goods:
                        continue
                    current_stock = max(0, int(city.inventory.get(good_name, 0)))
                    capacity = self._city_storage_capacity_from_city(city)
                    added = min(produced, max(0, capacity - current_stock))
                    if added > 0:
                        city.inventory[good_name] = current_stock + added
                    output_total += added
                upkeep_scale = 1.0 + (city.population / 450_000.0) + max(0.0, float(city.infrastructure) - 1.0) * 0.15
                upkeep_cost = int(round(max(0, int(recipe.upkeep)) * level * upkeep_scale))
                city.treasury -= upkeep_cost
                operating_value = max(
                    0,
                    (output_total * 6) - (input_total * 3) - max(0, upkeep_cost * 2),
                )
                dividend_pool = int(round(operating_value * DIVIDEND_POOL_FACTOR))
                if dividend_pool > 0:
                    city_pool = self.last_dividend_pools.setdefault(city_name, {})
                    city_pool[building.id] = city_pool.get(building.id, 0) + dividend_pool
                    city.treasury += max(0, dividend_pool // 6)
                active_buildings += max(1, level)
            city.treasury = int(self._clamp(float(city.treasury), -2_000_000_000.0, 2_000_000_000.0))
        for region_name in self._unlocked_remote_regions():
            region = self._city_economy(region_name)
            for good_name in active_goods:
                target_stock = self._stable_remote_stock_for(region_name, good_name)
                current_stock = max(0, int(region.inventory.get(good_name, 0)))
                if current_stock < target_stock:
                    restock = max(4, int(round((target_stock - current_stock) * 0.18)))
                    region.inventory[good_name] = min(target_stock, current_stock + restock)
            for building in region.buildings:
                if not building.active:
                    continue
                recipe = PRODUCTION_RECIPES.get(building.id)
                if recipe is None:
                    continue
                if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > current_century:
                    continue
                level = max(1, int(building.level))
                can_run = True
                for good_name, qty in recipe.inputs.items():
                    base_required = max(0, int(qty)) * level
                    if base_required <= 0:
                        required = 0
                    else:
                        required = max(1, int(math.ceil(base_required * (1.0 - efficiency_reduction))))
                    if region.inventory.get(good_name, 0) < required:
                        can_run = False
                        break
                if not can_run:
                    continue
                for good_name, qty in recipe.inputs.items():
                    base_required = max(0, int(qty)) * level
                    if base_required <= 0:
                        continue
                    required = max(1, int(math.ceil(base_required * (1.0 - efficiency_reduction))))
                    region.inventory[good_name] = max(0, int(region.inventory.get(good_name, 0)) - required)
                for good_name, qty in recipe.outputs.items():
                    if good_name not in active_goods:
                        continue
                    produced = max(0, int(qty)) * level
                    current_stock = max(0, int(region.inventory.get(good_name, 0)))
                    capacity = max(1_200, self._city_storage_capacity_from_city(region))
                    region.inventory[good_name] = min(capacity, current_stock + produced)
                active_buildings += max(1, level)
        return active_buildings

    def _tick_world_npcs(self) -> int:
        self._ensure_world_state()
        goods = self._active_good_names()
        npc_trades = 0
        trade_nodes = self._all_trade_nodes()
        for npc in self.npcs:
            if npc.city not in trade_nodes:
                npc.city = CITIES[0]
            origin = npc.city
            npc.ship.city = origin

            origin_prices = self._market_prices(origin)
            best_trade: tuple[str, str, int, int, int] | None = None
            for good_name in goods:
                origin_stock = self._city_inventory_qty(origin, good_name)
                if origin_stock < NPC_SKIP_LOW_STOCK:
                    continue
                buy_price = origin_prices.get(good_name, 0)
                if buy_price <= 0:
                    continue
                for target in trade_nodes:
                    if target == origin:
                        continue
                    sell_price = self._market_prices(target).get(good_name, 0)
                    margin = sell_price - buy_price
                    if margin <= 0:
                        continue
                    if best_trade is None or margin > best_trade[4]:
                        best_trade = (good_name, target, buy_price, sell_price, margin)

            if best_trade is None:
                continue

            good_name, target, buy_price, sell_price, _margin = best_trade
            stock = self._city_inventory_qty(origin, good_name)
            tradable_stock = max(0, stock - NPC_MIN_MARKET_STOCK)
            if tradable_stock <= 0:
                continue

            max_by_money = npc.money // max(1, buy_price)
            max_by_cargo = npc.ship.cargo_space_left
            qty = min(tradable_stock, max_by_money, max_by_cargo, NPC_MAX_BUY_PER_TRIP)
            if qty <= 0:
                continue

            bought = self._city_take_inventory(origin, good_name, qty, min_remaining=NPC_MIN_MARKET_STOCK)
            if bought <= 0:
                continue

            npc.money -= bought * buy_price
            npc.ship.cargo[good_name] = npc.ship.cargo.get(good_name, 0) + bought

            # v1: Reisen fuer NPCs ohne Risiko in einem Schritt.
            npc.city = target
            npc.ship.city = target
            sold_qty = npc.ship.cargo.get(good_name, 0)
            if sold_qty <= 0:
                continue

            self._city_add_inventory(target, good_name, sold_qty)
            npc.money += sold_qty * sell_price
            npc.ship.cargo[good_name] = 0
            npc_trades += 1
        return npc_trades

    def _run_world_month_tick(self) -> Dict[str, int]:
        production_count = self._tick_world_production()
        npc_trade_count = self._tick_world_npcs()
        social_metrics = self._simulate_city_society()
        bankrupt_count = sum(1 for city_name in CITIES if self._city_is_bankrupt(city_name))
        # NPCs handeln vor dem Spieler. Danach bleiben Preise fuer den Monat gecached stabil.
        self.market_cache.clear()
        self._invalidate_analysis_caches()
        self.last_world_tick = {
            "producing_buildings": production_count,
            "npc_trades": npc_trade_count,
            "cities_bankrupt": bankrupt_count,
            "total_tax": max(0, min(9_999_999_999, int(social_metrics.get("total_tax", 0)))),
            "net_migration": max(-999_999_999, min(999_999_999, int(social_metrics.get("net_migration", 0)))),
            "disease_cases": max(0, min(9_999_999, int(social_metrics.get("disease_cases", 0)))),
            "disease_deaths": max(0, min(9_999_999, int(social_metrics.get("disease_deaths", 0)))),
        }
        return dict(self.last_world_tick)

    def _can_building_run(self, city: CityEconomy, building: Building) -> bool:
        recipe = PRODUCTION_RECIPES.get(building.id)
        if recipe is None or not building.active:
            return False
        if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > self.current_century:
            return False
        level = max(1, int(building.level))
        for good_name, qty in recipe.inputs.items():
            required = max(0, int(qty)) * level
            if city.inventory.get(good_name, 0) < required:
                return False
        return True

    def _complete_mission_reward(
        self,
        mission_key: str,
        *,
        reward_money: int,
        reward_rep: int,
        text: str,
    ) -> None:
        if self.player is None:
            return
        mission = self.player.missions.get(mission_key, {})
        if mission.get("state") == "completed":
            return
        mission["state"] = "completed"
        if reward_money > 0:
            self.player.money += reward_money
        if reward_rep > 0:
            self.player.reputation = min(200, self.player.reputation + reward_rep)
        self._log(text)
        self.player.chronicle.append(f"ANNO {self.current_year}: {text}")

    def _building_recipe_ids_for_good(self, good_name: str) -> List[str]:
        recipe_ids: List[str] = []
        for recipe_id, recipe in PRODUCTION_RECIPES.items():
            if good_name in recipe.outputs:
                recipe_ids.append(recipe_id)
        return sorted(
            recipe_ids,
            key=lambda rid: (RECIPE_UNLOCK_CENTURY.get(rid, 14), PRODUCTION_RECIPES[rid].name),
        )

    def _building_quest_base_target(self, recipe_id: str) -> int:
        recipe = PRODUCTION_RECIPES.get(recipe_id)
        if recipe is None or not recipe.outputs:
            return 40
        first_qty = max(1, int(next(iter(recipe.outputs.values()))))
        return max(40, first_qty * BUILDING_QUEST_BASE_MULT)

    def _building_quest_target(self, recipe_id: str, tier: int) -> int:
        tier_i = max(1, int(tier) + 1)
        return self._building_quest_base_target(recipe_id) * tier_i

    def _init_building_quests(self) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault("building_quests", {})
        for recipe_id in PRODUCTION_RECIPES:
            entry = mission.get(recipe_id)
            if not isinstance(entry, dict):
                entry = {"tier": 0, "progress": 0}
            tier = max(0, int(entry.get("tier", 0)))
            progress = max(0, int(entry.get("progress", 0)))
            unlock_century = RECIPE_UNLOCK_CENTURY.get(recipe_id, 14)
            if tier >= BUILDING_QUEST_TIERS:
                state = "completed"
                tier = BUILDING_QUEST_TIERS
                progress = 0
            elif self.current_century < unlock_century:
                state = "locked"
            else:
                state = "active"
            mission[recipe_id] = {
                "tier": tier,
                "progress": progress,
                "state": state,
            }

    def _record_building_quest_trade(self, good: str, qty: int) -> None:
        if self.player is None or qty <= 0:
            return
        quests = self.player.missions.setdefault("building_quests", {})
        for recipe_id in self._building_recipe_ids_for_good(good):
            if RECIPE_UNLOCK_CENTURY.get(recipe_id, 14) > self.current_century:
                continue
            recipe = PRODUCTION_RECIPES.get(recipe_id)
            if recipe is None:
                continue
            entry = quests.get(recipe_id)
            if not isinstance(entry, dict):
                entry = {"tier": 0, "progress": 0, "state": "active"}
            tier = max(0, int(entry.get("tier", 0)))
            progress = max(0, int(entry.get("progress", 0)))
            if tier >= BUILDING_QUEST_TIERS:
                quests[recipe_id] = {"tier": BUILDING_QUEST_TIERS, "progress": 0, "state": "completed"}
                continue

            progress += qty
            while tier < BUILDING_QUEST_TIERS:
                target = self._building_quest_target(recipe_id, tier)
                if progress < target:
                    break
                progress -= target
                tier += 1
                reward_money = 350 + tier * 180 + self._building_quest_base_target(recipe_id) // 2
                reward_rep = 1 if tier % 2 == 0 else 0
                self.player.money += reward_money
                if reward_rep > 0:
                    self.player.reputation = min(200, self.player.reputation + reward_rep)
                self._log(
                    f"Betriebsquest [{recipe.name}] Stufe {tier}/{BUILDING_QUEST_TIERS} "
                    f"(+{reward_money} Mark{', +1 Ruf' if reward_rep else ''})."
                )
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Betriebsquest {recipe.name} Stufe {tier} abgeschlossen."
                )

            state = "completed" if tier >= BUILDING_QUEST_TIERS else "active"
            quests[recipe_id] = {"tier": tier, "progress": progress, "state": state}

    def _record_trade_for_missions(self, good: str, qty: int) -> None:
        if self.player is None or qty <= 0:
            return

        if good == "Bier":
            mission = self.player.missions.setdefault(
                "brewmaster",
                {"state": "active", "target": QUEST_BREWMASTER_TARGET, "delivered": 0, "next_log": 40},
            )
            if mission.get("state") != "completed":
                delivered = int(mission.get("delivered", 0)) + qty
                target = int(mission.get("target", QUEST_BREWMASTER_TARGET))
                mission["delivered"] = delivered
                next_log = int(mission.get("next_log", 40))
                if delivered >= next_log and delivered < target:
                    self._log(f"Braumeisterbund: {min(delivered, target)}/{target} Bier.")
                    mission["next_log"] = next_log + 40
                if delivered >= target:
                    self._complete_mission_reward(
                        "brewmaster",
                        reward_money=1800,
                        reward_rep=3,
                        text="Mission erfuellt: Braumeisterbund (+1800 Mark, +3 Ruf).",
                    )

        if good == "Holz":
            mission = self.player.missions.setdefault(
                "timber_trade",
                {"state": "active", "target": QUEST_TIMBER_TARGET, "delivered": 0, "next_log": 60},
            )
            if mission.get("state") != "completed":
                delivered = int(mission.get("delivered", 0)) + qty
                target = int(mission.get("target", QUEST_TIMBER_TARGET))
                mission["delivered"] = delivered
                next_log = int(mission.get("next_log", 60))
                if delivered >= next_log and delivered < target:
                    self._log(f"Nordholz-Vertrag: {min(delivered, target)}/{target} Holz.")
                    mission["next_log"] = next_log + 60
                if delivered >= target:
                    self._complete_mission_reward(
                        "timber_trade",
                        reward_money=1600,
                        reward_rep=2,
                        text="Mission erfuellt: Nordholz-Vertrag (+1600 Mark, +2 Ruf).",
                    )

        self._record_building_quest_trade(good, qty)

    def _record_city_visit(self, city: str) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault(
            "route_master",
            {"state": "active", "target": QUEST_ROUTE_MASTER_TARGET_CITIES, "visited": [self.player.city]},
        )
        visited_raw = mission.get("visited", [])
        visited = [str(city_name) for city_name in visited_raw if isinstance(city_name, str)]
        if city not in visited:
            visited.append(city)
            mission["visited"] = visited
        self._update_route_master()

    def _update_route_master(self) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault(
            "route_master",
            {"state": "active", "target": QUEST_ROUTE_MASTER_TARGET_CITIES, "visited": [self.player.city]},
        )
        if mission.get("state") == "completed":
            return
        visited = [str(city_name) for city_name in mission.get("visited", []) if isinstance(city_name, str)]
        if self.player.city not in visited:
            visited.append(self.player.city)
        mission["visited"] = visited
        target = int(mission.get("target", QUEST_ROUTE_MASTER_TARGET_CITIES))
        if len(visited) >= target:
            self._complete_mission_reward(
                "route_master",
                reward_money=1200,
                reward_rep=2,
                text="Mission erfuellt: Routenmeister (+1200 Mark, +2 Ruf).",
            )

    def _update_arms_race(self) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault(
            "arms_race",
            {
                "state": "active",
                "target_cannons": QUEST_ARMS_RACE_TARGET_CANNONS,
                "target_ships": QUEST_ARMS_RACE_TARGET_SHIPS,
            },
        )
        if mission.get("state") == "completed":
            return
        target_cannons = int(mission.get("target_cannons", QUEST_ARMS_RACE_TARGET_CANNONS))
        target_ships = int(mission.get("target_ships", QUEST_ARMS_RACE_TARGET_SHIPS))
        cannons = sum(ship.cannons for ship in self.player.ships)
        ships_count = len(self.player.ships)
        if ships_count >= target_ships and cannons >= target_cannons:
            self._complete_mission_reward(
                "arms_race",
                reward_money=2200,
                reward_rep=4,
                text="Mission erfuellt: Arsenal der Hanse (+2200 Mark, +4 Ruf).",
            )

    def _preferred_export_dir(self) -> Path:
        fallback = self.save_dir / "exports"
        if not self.is_android:
            return fallback

        candidates: List[Path] = []
        env_download = os.getenv("DOWNLOAD_DIR", "").strip()
        if env_download:
            candidates.append(Path(env_download))
        external_storage = os.getenv("EXTERNAL_STORAGE", "").strip()
        if external_storage:
            candidates.append(Path(external_storage) / "Download")
        candidates.extend(
            [
                Path("/storage/emulated/0/Download"),
                Path("/storage/self/primary/Download"),
                Path("/sdcard/Download"),
            ]
        )

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
            except OSError:
                continue
        return Path("/storage/emulated/0/Download")

    def _export_csv_report(self) -> Path | None:
        if self.player is None:
            return None
        self._ensure_world_state()
        export_dir = self._preferred_export_dir()
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = export_dir / f"hanse_report_{self.current_year}_{self.current_month:02d}_{stamp}.csv"
            headers = ["section", "entity", "subentity", "key", "value", "unit", "note"]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(headers)

                def row(
                    section: str,
                    entity: str,
                    subentity: str,
                    key: str,
                    value: object,
                    unit: str = "",
                    note: str = "",
                ) -> None:
                    writer.writerow([section, entity, subentity, key, value, unit, note])

                row("snapshot", "game", "", "year", self.current_year)
                row("snapshot", "game", "", "month", self.current_month)
                row("snapshot", "game", "", "sea_state", self.current_sea_state)
                row("atheria", "macro", "", "global_growth", f"{self.economy_state.global_growth:.4f}")
                row("atheria", "macro", "", "global_price_level", f"{self.economy_state.global_price_level:.4f}")
                row("atheria", "macro", "", "resource_scarcity", f"{self.economy_state.resource_scarcity:.4f}")

                for city_name in self._all_trade_nodes():
                    city = self._city_economy(city_name)
                    city_note = "remote_region" if self._is_remote_region(city_name) else ""
                    row("city", city_name, "", "treasury", city.treasury, "Mark")
                    row("city", city_name, "", "bankrupt", int(self._city_is_bankrupt(city_name)))
                    row("city", city_name, "", "building_count", len(city.buildings), "count", city_note)
                    row("city", city_name, "", "population", city.population, "citizens", city_note)
                    row("city", city_name, "", "social_stability", f"{city.social_stability:.2f}")
                    row("city", city_name, "", "quality_of_life", f"{city.quality_of_life:.2f}")
                    row("city", city_name, "", "migration", city.migration, "citizens")
                    row("city", city_name, "", "tax_income", city.tax_income, "Mark")
                    row("city", city_name, "", "disease_pressure", f"{city.disease_pressure:.4f}")
                    row("city", city_name, "", "disease_cases", city.disease_cases, "citizens")
                    row("city", city_name, "", "child_survival_rate", f"{city.child_survival_rate:.4f}")
                    row("city", city_name, "", "doctor_coverage", f"{city.doctor_coverage:.4f}")
                    row("city", city_name, "", "political_influence", f"{city.political_influence:.2f}")
                    row("city", city_name, "", "local_scarcity_relief", f"{city.local_scarcity_relief:.4f}")
                    row("city", city_name, "", "hazard_mitigation", f"{city.hazard_mitigation:.4f}")
                    row("city", city_name, "", "storage_multiplier", f"{city.storage_multiplier:.2f}")
                    prices = self._market_prices(city_name)
                    for good_name in self._active_good_names():
                        row("city_inventory", city_name, good_name, "stock", city.inventory.get(good_name, 0), "units")
                        row(
                            "city_inventory",
                            city_name,
                            good_name,
                            "scarcity_factor",
                            f"{city.scarcity_factor(good_name):.4f}",
                        )
                        row("city_inventory", city_name, good_name, "market_price", prices.get(good_name, 0), "Mark")
                    for idx, building in enumerate(city.buildings, start=1):
                        recipe = PRODUCTION_RECIPES.get(building.id)
                        recipe_name = recipe.name if recipe else building.id
                        row("building", city_name, f"{idx}", "id", building.id)
                        row("building", city_name, f"{idx}", "name", recipe_name)
                        row("building", city_name, f"{idx}", "level", max(1, int(building.level)))
                        row("building", city_name, f"{idx}", "active", int(bool(building.active)))
                        row("building", city_name, f"{idx}", "can_run_now", int(self._can_building_run(city, building)))
                        if recipe:
                            row("building", city_name, f"{idx}", "inputs", json.dumps(recipe.inputs, ensure_ascii=False))
                            row("building", city_name, f"{idx}", "outputs", json.dumps(recipe.outputs, ensure_ascii=False))

                for npc in self.npcs:
                    row("npc", npc.name, "", "city", npc.city)
                    row("npc", npc.name, "", "money", npc.money, "Mark")
                    row("npc", npc.name, "", "ship", npc.ship.display_name)
                    row("npc", npc.name, "", "cargo_total", npc.ship.total_cargo, "units")
                    for good_name in self._active_good_names():
                        qty = npc.ship.cargo.get(good_name, 0)
                        if qty > 0:
                            row("npc_cargo", npc.name, good_name, "qty", qty, "units")

                prices = self._market_prices(self.player.city)
                row("player", self.player.name, "", "city", self.player.city)
                row("player", self.player.name, "", "money", self.player.money, "Mark")
                row("player", self.player.name, "", "debt", self.player.debt, "Mark")
                row("player", self.player.name, "", "reputation", self.player.reputation)
                row("player", self.player.name, "", "age", self.player.age, "years")
                row("player", self.player.name, "", "children", self.player.children, "count")
                row("player", self.player.name, "", "children_limit", self._current_max_children(), "count")
                row("player", self.player.name, "", "net_worth", self._net_worth(self.player, prices), "Mark")
                row("investment_impact", self.player.name, "", "social_spend", f"{self._investment_spend_total(TRACK_SOCIAL):.2f}", "Mark")
                row("investment_impact", self.player.name, "", "social_level", self._investment_level(TRACK_SOCIAL), "level")
                row("investment_impact", self.player.name, "", "research_spend", f"{self._investment_spend_total(TRACK_RESEARCH):.2f}", "Mark")
                row("investment_impact", self.player.name, "", "research_level", self._investment_level(TRACK_RESEARCH), "level")
                row(
                    "investment_impact",
                    self.player.name,
                    "",
                    "efficiency_reduction",
                    f"{self.research_manager.efficiency_reduction(self._investment_level(TRACK_RESEARCH)):.4f}",
                )
                row("investment_impact", self.player.name, "", "infrastructure_spend", f"{self._investment_spend_total(TRACK_INFRASTRUCTURE):.2f}", "Mark")
                row("investment_impact", self.player.name, "", "infrastructure_level", self._investment_level(TRACK_INFRASTRUCTURE), "level")
                row(
                    "investment_impact",
                    self.player.name,
                    "",
                    "travel_time_multiplier",
                    f"{self.research_manager.travel_time_multiplier(self._investment_level(TRACK_INFRASTRUCTURE), self.current_year):.4f}",
                )
                row("investment_impact", self.player.name, "", "sophia_spend", f"{self.sophia_spend_total:.2f}", "Mark")
                row("investment_impact", self.player.name, "", "sophia_level", self._investment_level(TRACK_SOPHIA), "level")
                row("investment_impact", self.player.name, "", "global_loss_value", f"{self.global_loss_value:.4f}")
                for city_name, score in self.player.city_influence.items():
                    row("player_influence", self.player.name, city_name, "score", f"{float(score):.2f}")
                for mission_key, mission_data in self.player.missions.items():
                    state = mission_data.get("state", "inactive") if isinstance(mission_data, dict) else "inactive"
                    row("player_mission", self.player.name, mission_key, "state", state)
                for city_name, share_map in self.player.building_shares.items():
                    if not isinstance(share_map, dict):
                        continue
                    for recipe_id, share_pct in share_map.items():
                        recipe = PRODUCTION_RECIPES.get(recipe_id)
                        row(
                            "player_share",
                            self.player.name,
                            f"{city_name}:{recipe_id}",
                            "share_pct",
                            f"{float(share_pct):.2f}",
                            "%",
                            recipe.name if recipe else recipe_id,
                        )
                building_quests = self.player.missions.get("building_quests", {})
                if isinstance(building_quests, dict):
                    for recipe_id, quest_data in building_quests.items():
                        if not isinstance(quest_data, dict):
                            continue
                        recipe = PRODUCTION_RECIPES.get(recipe_id)
                        recipe_name = recipe.name if recipe else recipe_id
                        row("player_building_quest", self.player.name, recipe_id, "recipe_name", recipe_name)
                        row(
                            "player_building_quest",
                            self.player.name,
                            recipe_id,
                            "tier",
                            max(0, int(quest_data.get("tier", 0))),
                            "of_8",
                        )
                        row(
                            "player_building_quest",
                            self.player.name,
                            recipe_id,
                            "progress",
                            max(0, int(quest_data.get("progress", 0))),
                            "units",
                        )
                        row(
                            "player_building_quest",
                            self.player.name,
                            recipe_id,
                            "state",
                            str(quest_data.get("state", "inactive")),
                        )
                for idx, ship in enumerate(self.player.ships, start=1):
                    row("player_ship", self.player.name, f"{idx}", "name", ship.display_name)
                    row("player_ship", self.player.name, f"{idx}", "city", ship.city)
                    row("player_ship", self.player.name, f"{idx}", "cargo_capacity", ship.cargo_capacity, "units")
                    row("player_ship", self.player.name, f"{idx}", "cargo_total", ship.total_cargo, "units")
                    row("player_ship", self.player.name, f"{idx}", "hull", ship.hull, "%")
                    row("player_ship", self.player.name, f"{idx}", "rigging", ship.rigging, "%")
                    row("player_ship", self.player.name, f"{idx}", "cannons", ship.cannons, "count")
            return path
        except OSError:
            return None

    def _ensure_runtime_state(self) -> None:
        runtime_defaults = {
            "market_goods_offset": 0,
            "transfer_goods_offset": 0,
            "city_goods_offset": 0,
            "city_market_node_offset": 0,
            "city_building_offset": 0,
            "shipyard_offset": 0,
            "time_limit_reached": False,
            "fleet_scroll": 0,
            "selected_good": 0,
            "selected_ship_type": 0,
            "selected_fleet_ship": 0,
            "selected_dest": 0,
            "dest_scroll": 0,
            "selected_weapon_century": year_to_century(self.current_year),
            "editor_weapon_offset": 0,
            "editor_weapon_visible_cache": 5,
            "info_scroll": 0,
            "info_max_scroll": 0,
            "city_analysis_scroll": 0,
            "info_open": False,
            "selected_city_building_recipe": "",
            "selected_city_good": 0,
            "settings_open": False,
            "about_open": False,
            "ship_editor_ship": None,
            "auto_popup_hold_until": 0,
            "auto_last_ship_build_month": -9999,
            "last_world_tick": {
                "producing_buildings": 0,
                "npc_trades": 0,
                "cities_bankrupt": 0,
                "total_tax": 0,
                "net_migration": 0,
                "disease_cases": 0,
                "disease_deaths": 0,
            },
            "last_dividend_pools": {},
            "sophia_spend_total": 0.0,
            "global_loss_value": 0.0,
            "city_dashboard_cache": {},
            "_market_breakdown_cache": {},
        }
        for key, value in runtime_defaults.items():
            if not hasattr(self, key):
                setattr(self, key, value)
        global global_loss_value
        try:
            global_loss_value = max(0.0, min(0.85, float(getattr(self, "global_loss_value", 0.0))))
        except (TypeError, ValueError):
            global_loss_value = 0.0
        if not hasattr(self, "editor_weapon_rows") or not isinstance(self.editor_weapon_rows, list):
            self.editor_weapon_rows = []
        if not hasattr(self, "editor_weapon_list_rect"):
            self.editor_weapon_list_rect = None
        if not hasattr(self, "dest_list_rect"):
            self.dest_list_rect = None
        if not hasattr(self, "about_panel_rect"):
            self.about_panel_rect = None
        if not hasattr(self, "city_price_rows") or not isinstance(self.city_price_rows, list):
            self.city_price_rows = []
        if not hasattr(self, "city_building_list_rect"):
            self.city_building_list_rect = None
        if not hasattr(self, "city_analysis_rect"):
            self.city_analysis_rect = None
        if not hasattr(self, "city_analysis_lines") or not isinstance(self.city_analysis_lines, list):
            self.city_analysis_lines = []
        if not isinstance(getattr(self, "city_dashboard_cache", None), dict):
            self.city_dashboard_cache = {}
        if not isinstance(getattr(self, "_market_breakdown_cache", None), dict):
            self._market_breakdown_cache = {}
        if not hasattr(self, "settings_path"):
            self.settings_path = self.save_dir / UI_SETTINGS_FILE
        if not hasattr(self, "music_path"):
            self.music_path = self._resolve_music_path()
        if not hasattr(self, "image_dir"):
            self.image_dir = _runtime_asset_root() / "images"
        if not hasattr(self, "ui_language") or str(getattr(self, "ui_language", "")).strip().lower() not in UI_LANGUAGES:
            self.ui_language = self._load_ui_language()
        if not hasattr(self, "music_enabled"):
            self.music_enabled = self._load_music_enabled()
        if not hasattr(self, "music_volume"):
            self.music_volume = self._load_music_volume()
        self.music_volume = self._clamp(float(self.music_volume), 0.0, 1.0)
        if not hasattr(self, "music_available"):
            self.music_available = False
        if not hasattr(self, "_music_loaded"):
            self._music_loaded = False
        if not hasattr(self, "_ui_translation_cache") or not isinstance(self._ui_translation_cache, dict):
            self._ui_translation_cache = {}
        self.info_scroll = max(0, int(getattr(self, "info_scroll", 0)))
        self.info_max_scroll = max(0, int(getattr(self, "info_max_scroll", 0)))
        self.info_scroll = min(self.info_scroll, self.info_max_scroll)
        if not hasattr(self, "world_economy") or not isinstance(self.world_economy, WorldEconomy):
            self.world_economy = WorldEconomy()
        if not hasattr(self, "npcs") or not isinstance(self.npcs, list):
            self.npcs = []
        self._ensure_world_state()
        if not hasattr(self, "current_century"):
            self.current_century = year_to_century(self.current_year)
        self._normalize_selected_weapon_century()
        if self.player is not None:
            if not hasattr(self.player, "missions") or not isinstance(self.player.missions, dict):
                self.player.missions = {}
            if not hasattr(self.player, "building_shares") or not isinstance(self.player.building_shares, dict):
                self.player.building_shares = {}
            if not hasattr(self.player, "city_influence") or not isinstance(self.player.city_influence, dict):
                self.player.city_influence = {}
            if not hasattr(self.player, "investments") or not isinstance(self.player.investments, dict):
                self.player.investments = {"social": 0.0, "research": 0.0, "infrastructure": 0.0}
            for inv_key in ("social", "research", "infrastructure"):
                try:
                    self.player.investments[inv_key] = max(0.0, float(self.player.investments.get(inv_key, 0.0)))
                except (TypeError, ValueError):
                    self.player.investments[inv_key] = 0.0
            if not hasattr(self.player, "married"):
                self.player.married = False
            if not hasattr(self.player, "spouse_name"):
                self.player.spouse_name = ""
            if not hasattr(self.player, "marriage_year"):
                self.player.marriage_year = None
            if not hasattr(self.player, "marriage_month"):
                self.player.marriage_month = None
            if not hasattr(self.player, "children"):
                self.player.children = 0
            if not hasattr(self.player, "child_names") or not isinstance(self.player.child_names, list):
                self.player.child_names = []
            if not hasattr(self.player, "child_ages") or not isinstance(self.player.child_ages, dict):
                self.player.child_ages = {}
            if not hasattr(self.player, "last_marriage_offer_month"):
                self.player.last_marriage_offer_month = -9999
            if not hasattr(self.player, "turns_in_debt_tower"):
                self.player.turns_in_debt_tower = 0
            if not hasattr(self.player, "chronicle") or not isinstance(self.player.chronicle, list):
                self.player.chronicle = []
            if self.player.children < len(self.player.child_names):
                self.player.children = len(self.player.child_names)
            for child_name in self.player.child_names:
                try:
                    self.player.child_ages[child_name] = max(0, int(self.player.child_ages.get(child_name, 6)))
                except (TypeError, ValueError):
                    self.player.child_ages[child_name] = 6
            for stored_name in list(self.player.child_ages.keys()):
                if stored_name not in self.player.child_names:
                    self.player.child_ages.pop(stored_name, None)
            for ship in getattr(self.player, "ships", []):
                if not hasattr(ship, "cargo") or not isinstance(ship.cargo, dict):
                    ship.cargo = {}
                if not hasattr(ship, "cannons"):
                    ship.cannons = 0
                if not hasattr(ship, "cannon_inventory") or not isinstance(ship.cannon_inventory, dict):
                    ship.cannon_inventory = {}
                if not hasattr(ship, "is_at_sea"):
                    ship.is_at_sea = False
                if not hasattr(ship, "destination"):
                    ship.destination = None
                if not hasattr(ship, "travel_turns_left"):
                    ship.travel_turns_left = 0
                if not hasattr(ship, "last_report"):
                    ship.last_report = ""
                if not hasattr(ship, "locked_prices") or not isinstance(ship.locked_prices, dict):
                    ship.locked_prices = {}
                if not hasattr(ship, "locked_qty") or not isinstance(ship.locked_qty, dict):
                    ship.locked_qty = {}

    def _snapshot_game_state(self) -> Dict[str, object] | None:
        if self.player is None:
            return None
        return {
            "player": self.player.to_dict(),
            "year": self.current_year,
            "month": self.current_month,
            "sea_state": self.current_sea_state,
            "economy_state": self.economy_state.to_dict(),
            "world_economy": self.world_economy.to_dict(),
            "npcs": [npc.to_dict() for npc in self.npcs],
            "last_world_tick": dict(self.last_world_tick),
            "last_dividend_pools": {
                city_name: {recipe_id: int(value) for recipe_id, value in pool.items()}
                for city_name, pool in self.last_dividend_pools.items()
            },
            "sophia_spend_total": float(self.sophia_spend_total),
            "global_loss_value": float(self.global_loss_value),
            "market_cache": {key: dict(value) for key, value in self.market_cache.items()},
            "current_century": self.current_century,
            "preview_destination": self.preview_destination,
            "selected_good": self.selected_good,
            "selected_city_good": self.selected_city_good,
            "city_building_offset": self.city_building_offset,
            "selected_dest": self.selected_dest,
            "selected_ship_type": self.selected_ship_type,
            "selected_fleet_ship": self.selected_fleet_ship,
            "fleet_scroll": self.fleet_scroll,
            "selected_weapon_century": self.selected_weapon_century,
            "city_dashboard_cache": {
                key: dict(value) for key, value in self.city_dashboard_cache.items()
            },
            "market_breakdown_cache": {
                key: {good: dict(parts) for good, parts in goods.items()}
                for key, goods in self._market_breakdown_cache.items()
            },
        }

    def _restore_game_state(self, snapshot: Dict[str, object] | None) -> None:
        if not snapshot:
            return
        player_data = snapshot.get("player")
        if isinstance(player_data, dict):
            self.player = Player.from_dict(player_data)
        self.current_year = int(snapshot.get("year", self.current_year))
        self.current_month = int(snapshot.get("month", self.current_month))
        self.current_sea_state = str(snapshot.get("sea_state", self.current_sea_state))
        econ_data = snapshot.get("economy_state")
        if isinstance(econ_data, dict):
            self.economy_state = EconomyState.from_dict(econ_data)
        world_data = snapshot.get("world_economy")
        if isinstance(world_data, dict):
            self.world_economy = WorldEconomy.from_dict(world_data)
        else:
            self.world_economy = WorldEconomy()
        npcs_data = snapshot.get("npcs")
        if isinstance(npcs_data, list):
            self.npcs = [NPCTrader.from_dict(entry) for entry in npcs_data if isinstance(entry, dict)]
        else:
            self.npcs = []
        last_world_tick = snapshot.get("last_world_tick")
        if isinstance(last_world_tick, dict):
            self.last_world_tick = {
                "producing_buildings": int(last_world_tick.get("producing_buildings", 0)),
                "npc_trades": int(last_world_tick.get("npc_trades", 0)),
                "cities_bankrupt": int(last_world_tick.get("cities_bankrupt", 0)),
                "total_tax": max(0, min(9_999_999_999, int(last_world_tick.get("total_tax", 0)))),
                "net_migration": max(-999_999_999, min(999_999_999, int(last_world_tick.get("net_migration", 0)))),
                "disease_cases": max(0, min(9_999_999, int(last_world_tick.get("disease_cases", 0)))),
                "disease_deaths": max(0, min(9_999_999, int(last_world_tick.get("disease_deaths", 0)))),
            }
        else:
            self.last_world_tick = {
                "producing_buildings": 0,
                "npc_trades": 0,
                "cities_bankrupt": 0,
                "total_tax": 0,
                "net_migration": 0,
                "disease_cases": 0,
                "disease_deaths": 0,
            }
        dividend_data = snapshot.get("last_dividend_pools")
        self.last_dividend_pools = {}
        if isinstance(dividend_data, dict):
            for raw_city, raw_pool in dividend_data.items():
                if not isinstance(raw_pool, dict):
                    continue
                city_name = str(raw_city)
                pool: Dict[str, int] = {}
                for raw_recipe, raw_value in raw_pool.items():
                    try:
                        pool[str(raw_recipe)] = max(0, int(raw_value))
                    except (TypeError, ValueError):
                        continue
                self.last_dividend_pools[city_name] = pool
        try:
            self.sophia_spend_total = max(0.0, float(snapshot.get("sophia_spend_total", self.sophia_spend_total)))
        except (TypeError, ValueError):
            self.sophia_spend_total = 0.0
        try:
            self.global_loss_value = max(0.0, min(0.85, float(snapshot.get("global_loss_value", self.global_loss_value))))
        except (TypeError, ValueError):
            self.global_loss_value = 0.0
        market_cache = snapshot.get("market_cache")
        if isinstance(market_cache, dict):
            self.market_cache = {}
            for key, value in market_cache.items():
                if isinstance(key, tuple) and isinstance(value, dict):
                    self.market_cache[key] = dict(value)
        self.current_century = int(snapshot.get("current_century", year_to_century(self.current_year)))
        self.preview_destination = snapshot.get("preview_destination") if isinstance(
            snapshot.get("preview_destination"), (str, type(None))
        ) else None
        self.selected_good = int(snapshot.get("selected_good", 0))
        self.selected_city_good = int(snapshot.get("selected_city_good", 0))
        self.city_building_offset = max(0, int(snapshot.get("city_building_offset", 0)))
        self.selected_dest = int(snapshot.get("selected_dest", 0))
        self.selected_ship_type = int(snapshot.get("selected_ship_type", 0))
        self.selected_fleet_ship = int(snapshot.get("selected_fleet_ship", 0))
        self.fleet_scroll = int(snapshot.get("fleet_scroll", 0))
        self.selected_weapon_century = int(snapshot.get("selected_weapon_century", self.current_century))
        dashboard_cache = snapshot.get("city_dashboard_cache")
        if isinstance(dashboard_cache, dict):
            self.city_dashboard_cache = {}
            for key, value in dashboard_cache.items():
                if isinstance(key, tuple) and isinstance(value, dict):
                    self.city_dashboard_cache[key] = dict(value)
        breakdown_cache = snapshot.get("market_breakdown_cache")
        if isinstance(breakdown_cache, dict):
            self._market_breakdown_cache = {}
            for key, value in breakdown_cache.items():
                if isinstance(key, tuple) and isinstance(value, dict):
                    self._market_breakdown_cache[key] = {
                        str(good): dict(parts) for good, parts in value.items() if isinstance(parts, dict)
                    }
        self._ensure_world_state()
        self._ensure_runtime_state()
        self._sync_century_content(announce=False)

    def _market_visible_count(self) -> int:
        return 7

    def _transfer_visible_count(self) -> int:
        return 8

    def _city_market_visible_count(self) -> int:
        return 10

    def _shipyard_visible_count(self) -> int:
        return 3

    def _ship_destination_visible_count(self) -> int:
        return 7

    def _editor_weapon_visible_count(self) -> int:
        return max(1, int(getattr(self, "editor_weapon_visible_cache", 5)))

    def _max_market_goods_offset(self) -> int:
        return max(0, len(self._active_good_names()) - self._market_visible_count())

    def _max_transfer_goods_offset(self) -> int:
        return max(0, len(self._active_good_names()) - self._transfer_visible_count())

    def _max_city_goods_offset(self) -> int:
        return max(0, len(self._active_good_names()) - self._city_market_visible_count())

    def _max_destination_offset(self, origin: str) -> int:
        return max(0, len(self._available_trade_destinations(origin)) - self._ship_destination_visible_count())

    def _city_market_nodes(self) -> List[str]:
        nodes = list(CITIES)
        for region_name in self._unlocked_remote_regions():
            if region_name not in nodes:
                nodes.append(region_name)
        return nodes

    def _selected_city_market_name(self) -> str:
        nodes = self._city_market_nodes()
        if not nodes:
            return CITIES[0]
        self.selected_city_market = max(0, min(self.selected_city_market, len(nodes) - 1))
        return nodes[self.selected_city_market]

    def _city_market_node_layout(self) -> Tuple[pygame.Rect, int, int]:
        panel = pygame.Rect(160, 110, 1000, 600)
        city_x = panel.x + 24
        list_top = panel.y + 90
        city_w = 220
        list_bottom = panel.bottom - 74
        row_step = 40
        visible_node_count = max(1, (list_bottom - list_top) // row_step)
        list_height = max(34, (visible_node_count - 1) * row_step + 34)
        node_rect = pygame.Rect(city_x, list_top, city_w, list_height)
        max_node_offset = max(0, len(self._city_market_nodes()) - visible_node_count)
        return node_rect, visible_node_count, max_node_offset

    def _city_market_goods_layout(self) -> Tuple[pygame.Rect, int, int]:
        panel = pygame.Rect(160, 110, 1000, 600)
        prices_x = panel.x + 270
        prices_w = 430
        list_top = panel.y + 164
        list_bottom = panel.bottom - 188
        row_step = 42
        visible_goods_count = max(1, min(self._city_market_visible_count(), (list_bottom - list_top) // row_step))
        list_height = max(36, (visible_goods_count - 1) * row_step + 36)
        goods_rect = pygame.Rect(prices_x, list_top, prices_w, list_height)
        max_goods_offset = max(0, len(self._active_good_names()) - visible_goods_count)
        return goods_rect, visible_goods_count, max_goods_offset

    def _city_market_building_layout(self) -> Tuple[pygame.Rect, int]:
        panel = pygame.Rect(160, 110, 1000, 600)
        prices_x = panel.x + 270
        prices_w = 430
        buildings_x = prices_x + prices_w + 16
        buildings_w = panel.right - buildings_x - 24
        list_top = panel.y + 164
        list_bottom = panel.bottom - 188
        row_height = 80
        row_step = 84
        visible_building_count = max(1, (list_bottom - list_top + 4) // row_step)
        list_height = max(row_height, (visible_building_count - 1) * row_step + row_height)
        return pygame.Rect(buildings_x, list_top, buildings_w, list_height), visible_building_count

    def _max_shipyard_offset(self) -> int:
        return max(0, len(self._active_shipyard()) - self._shipyard_visible_count())

    def _sync_century_content(self, *, announce: bool = False) -> None:
        century = year_to_century(self.current_year)
        self._ensure_world_state()
        if self.player is not None:
            goods = self._active_good_names()
            for city in CITIES:
                storage = self.player.warehouses.setdefault(city, {})
                city_locks = self.player.warehouse_locks.setdefault(city, {})
                for good_name in goods:
                    storage.setdefault(good_name, 0)
                    city_locks.setdefault(good_name, [])
            for ship in self.player.ships:
                for good_name in goods:
                    ship.cargo.setdefault(good_name, 0)
                    ship.locked_qty.setdefault(good_name, 0)
                ship.locked_qty = {good: qty for good, qty in ship.locked_qty.items() if qty > 0}
                ship.locked_prices = {good: price for good, price in ship.locked_prices.items() if good in goods}
                raw_inventory = getattr(ship, "cannon_inventory", {})
                cleaned_inventory: Dict[str, int] = {}
                if isinstance(raw_inventory, dict):
                    for raw_century, raw_qty in raw_inventory.items():
                        try:
                            century_key = str(max(14, int(raw_century)))
                            qty_i = max(0, int(raw_qty))
                        except (TypeError, ValueError):
                            continue
                        if qty_i > 0:
                            cleaned_inventory[century_key] = cleaned_inventory.get(century_key, 0) + qty_i
                ship.cannon_inventory = cleaned_inventory
                inventory_total = sum(cleaned_inventory.values())
                if inventory_total > 0:
                    ship.cannons = inventory_total
                max_cannons = self._max_cannons(ship)
                ship.cannons = min(ship.cannons, max_cannons)
                overflow = sum(ship.cannon_inventory.values()) - ship.cannons
                if overflow > 0:
                    # Bei Reduktion zunaechst neuere Tier-Kanonen entfernen.
                    for century_key in sorted(ship.cannon_inventory.keys(), key=int, reverse=True):
                        if overflow <= 0:
                            break
                        take = min(overflow, ship.cannon_inventory[century_key])
                        ship.cannon_inventory[century_key] -= take
                        overflow -= take
                        if ship.cannon_inventory[century_key] <= 0:
                            ship.cannon_inventory.pop(century_key, None)
            self.selected_good = max(0, min(self.selected_good, max(0, len(goods) - 1)))
            shipyard = self._active_shipyard()
            self.selected_ship_type = max(0, min(self.selected_ship_type, max(0, len(shipyard) - 1)))
            self.market_goods_offset = max(0, min(self.market_goods_offset, self._max_market_goods_offset()))
            self.transfer_goods_offset = max(0, min(self.transfer_goods_offset, self._max_transfer_goods_offset()))
            self.city_goods_offset = max(0, min(self.city_goods_offset, self._max_city_goods_offset()))
            self.shipyard_offset = max(0, min(self.shipyard_offset, self._max_shipyard_offset()))
        if announce and century > self.current_century:
            goods_unlock = goods_unlocked_in_century(century)
            ships_unlock = ships_unlocked_in_century(century)
            titles_unlock = titles_unlocked_in_century(century)
            region_unlock = [
                region_name
                for region_name in self._unlocked_remote_regions()
                if int(self._trade_region_config(region_name).get("unlock_century", 99)) == century
            ]
            weapon = self._active_weapon_profile()
            self._log(f"Neues Jahrhundert erreicht: {century}. Jahrhundert.")
            if goods_unlock:
                self._log("Neue Gueter: " + ", ".join(goods_unlock))
            if region_unlock:
                self._log("Neue Fernhandelsziele: " + ", ".join(region_unlock))
            if ships_unlock:
                self._log("Neue Schiffe: " + ", ".join(name for name, *_ in ships_unlock))
            if titles_unlock:
                self._log("Neue Titelstufen freigeschaltet.")
            self._log(
                f"Neue Waffentechnik: {weapon.get('name', 'Kanonen')} "
                f"(Kosten {self._active_cannon_cost()} Mark, Wirkung x{self._active_cannon_power():.2f})."
            )
            if self.player is not None:
                self.player.chronicle.append(f"ANNO {self.current_year}: Jahrhundert {century} erreicht.")
        self.current_century = century
        self._normalize_selected_weapon_century()

    def _update_display_scale(self) -> None:
        win_w = max(1, self.window.get_width())
        win_h = max(1, self.window.get_height())
        self.scale_x = win_w / WIDTH
        self.scale_y = win_h / HEIGHT

    def _to_virtual_pos(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        win_w = max(1, self.window.get_width())
        win_h = max(1, self.window.get_height())
        scale_x = win_w / WIDTH
        scale_y = win_h / HEIGHT
        # Android liefert bei manchen Geräten Touch-Koordinaten relativ zur Displayfläche.
        # Wenn diese außerhalb der Surface liegen, auf Display-Skalierung umschalten.
        if self.is_android and (pos[0] >= win_w or pos[1] >= win_h):
            info = pygame.display.Info()
            disp_w = max(1, int(info.current_w))
            disp_h = max(1, int(info.current_h))
            scale_x = disp_w / WIDTH
            scale_y = disp_h / HEIGHT
        x = int(pos[0] / scale_x) if scale_x > 0 else pos[0]
        y = int(pos[1] / scale_y) if scale_y > 0 else pos[1]
        x = max(0, min(WIDTH - 1, x))
        y = max(0, min(HEIGHT - 1, y))
        return (x, y)

    def _virtual_mouse_pos(self) -> Tuple[int, int]:
        return self._to_virtual_pos(pygame.mouse.get_pos())

    def _set_text_input_enabled(self, enabled: bool) -> None:
        if enabled and not self.text_input_enabled:
            pygame.key.start_text_input()
            self.text_input_enabled = True
        elif not enabled and self.text_input_enabled:
            pygame.key.stop_text_input()
            self.text_input_enabled = False

    def _wants_text_input(self) -> bool:
        if self.scene == "setup":
            return True
        if self.scene == "game" and self.cheat_open:
            return True
        if self.scene == "game" and self.child_name_popup_open:
            return True
        if self.scene == "game" and self.ship_editor_open and self.ship_name_active:
            return True
        return False

    def _sync_text_input_state(self) -> None:
        wants_text = self._wants_text_input()
        self._set_text_input_enabled(wants_text)
        if self.is_android and not wants_text:
            info = pygame.display.Info()
            if self.window.get_width() < info.current_w or self.window.get_height() < info.current_h:
                self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                self._update_display_scale()

    def _force_exit(self) -> None:
        self.running = False
        self._set_text_input_enabled(False)
        pygame.quit()
        raise SystemExit(0)

    def run(self) -> int:
        while self.running:
            try:
                self._update_display_scale()
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.VIDEORESIZE:
                        if not self.is_android:
                            self.window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                        else:
                            self.window = pygame.display.get_surface()
                        self._update_display_scale()
                    elif event.type == pygame.KEYDOWN:
                        self._handle_key(event)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_click(self._to_virtual_pos(event.pos))
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self._handle_release(self._to_virtual_pos(event.pos))
                    elif event.type == pygame.MOUSEMOTION:
                        self._handle_motion(self._to_virtual_pos(event.pos))
                    elif event.type == pygame.MOUSEWHEEL:
                        self._handle_wheel(event)

                self._run_auto_mode()
                self._sync_text_input_state()
                self._draw()
                if self.window.get_size() == (WIDTH, HEIGHT):
                    self.window.blit(self.screen, (0, 0))
                else:
                    if self.is_android:
                        scaled = pygame.transform.scale(self.screen, self.window.get_size())
                    else:
                        scaled = pygame.transform.smoothscale(self.screen, self.window.get_size())
                    self.window.blit(scaled, (0, 0))
                pygame.display.flip()
            except Exception as exc:
                self.auto_mode = False
                self._log(f"Laufzeitfehler: {type(exc).__name__}: {exc}.")
                self._record_runtime_exception(exc, "run_loop")
                self.shipyard_open = False
                self.ship_cargo_open = False
                self.ship_editor_open = False
                self.ship_editor_ship = None
                self.city_market_open = False
                self.missions_open = False
                self.info_open = False
                self.save_menu_open = False
                self.transfer_drag_good = None
                self.ship_name_active = False
                self.child_name_popup_open = False
                self.marriage_popup_open = False
                self._ensure_runtime_state()
            self.clock.tick(self.target_fps)

        self._set_text_input_enabled(False)
        pygame.quit()
        return 0

    def _handle_key(self, event: pygame.event.Event) -> None:
        back_key = getattr(pygame, "K_AC_BACK", -1)
        is_back = event.key in {pygame.K_ESCAPE, back_key}
        if self.settings_open:
            if is_back or event.key == pygame.K_RETURN:
                self.settings_open = False
            return
        if self.scene == "setup":
            if is_back:
                self.scene = "menu"
            elif event.key == pygame.K_BACKSPACE:
                self.new_name = self.new_name[:-1]
            elif event.key == pygame.K_RETURN:
                self._start_new_game()
            else:
                if event.unicode.isprintable() and not event.unicode.isspace():
                    if len(self.new_name) < 18:
                        self.new_name += event.unicode
        elif self.scene == "game":
            if self.child_name_popup_open:
                if event.key == pygame.K_BACKSPACE:
                    self.child_name_edit = self.child_name_edit[:-1]
                    return
                if event.key == pygame.K_RETURN:
                    self._submit_child_name()
                    return
                if event.unicode.isprintable() and not event.unicode.isspace():
                    if len(self.child_name_edit) < MAX_CHILD_NAME_LEN:
                        self.child_name_edit += event.unicode
                return
            if self.marriage_popup_open:
                if event.key in {pygame.K_RETURN, pygame.K_y}:
                    self._resolve_marriage_proposal(True)
                    return
                if is_back or event.key == pygame.K_n:
                    self._resolve_marriage_proposal(False)
                    return
                return
            if self.cheat_open:
                if is_back:
                    self.cheat_open = False
                    self.cheat_text = ""
                    return
                if event.key == pygame.K_BACKSPACE:
                    self.cheat_text = self.cheat_text[:-1]
                    return
                if event.key == pygame.K_RETURN:
                    self._submit_cheat()
                    return
                if event.unicode.isprintable() and len(self.cheat_text) < 16:
                    self.cheat_text += event.unicode
                return
            if self.city_market_open:
                if is_back:
                    self.city_market_open = False
                return
            if self.missions_open:
                if is_back:
                    self.missions_open = False
                return
            if self.info_open:
                if is_back or event.key in {pygame.K_RETURN, pygame.K_i}:
                    self.info_open = False
                    self.info_scroll = 0
                    self.info_max_scroll = 0
                return
            if self.about_open:
                if is_back or event.key == pygame.K_RETURN:
                    self.about_open = False
                    self.about_panel_rect = None
                return
            if self.ship_editor_open and self.ship_name_active:
                if is_back:
                    self.ship_name_active = False
                    self.ship_name_edit = ""
                    self.ship_name_input_rect = None
                    return
                if event.key == pygame.K_BACKSPACE:
                    self.ship_name_edit = self.ship_name_edit[:-1]
                    return
                if event.key == pygame.K_RETURN:
                    self._submit_ship_name()
                    return
                if event.unicode.isprintable() and not event.unicode.isspace():
                    if len(self.ship_name_edit) < MAX_SHIP_NAME_LEN:
                        self.ship_name_edit += event.unicode
                return
            if is_back:
                if self.shipyard_open:
                    self.shipyard_open = False
                    return
                if self.ship_cargo_open:
                    self.ship_cargo_open = False
                    self.transfer_drag_good = None
                    return
                if self.ship_editor_open:
                    self.ship_editor_open = False
                    self.ship_editor_ship = None
                    self.ship_name_active = False
                    self.ship_name_edit = ""
                    self.ship_name_input_rect = None
                    return
                if self.city_market_open:
                    self.city_market_open = False
                    return
                if self.missions_open:
                    self.missions_open = False
                    return
                if self.info_open:
                    self.info_open = False
                    self.info_scroll = 0
                    self.info_max_scroll = 0
                    return
            if event.unicode == "|":
                self.cheat_open = True
                self.cheat_text = ""
                return
            if event.key in {pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS}:
                self.trade_qty = min(99, self.trade_qty + 1)
            elif event.key in {pygame.K_MINUS, pygame.K_KP_MINUS}:
                self.trade_qty = max(1, self.trade_qty - 1)
            elif event.key == pygame.K_F5:
                self._save_slot(self.selected_slot)
            elif event.key == pygame.K_F9:
                self._load_slot(self.selected_slot)
            elif event.key == pygame.K_F6:
                path = self._export_csv_report()
                if path:
                    self._log(f"CSV exportiert: {path}")
                else:
                    self._log("CSV-Export fehlgeschlagen.")

    def _handle_click(self, pos: Tuple[int, int]) -> None:
        if self.settings_open:
            self._handle_settings_click(pos)
            return
        if self.scene == "menu":
            for slot, rect in self.slot_rows:
                if rect.collidepoint(pos):
                    self.selected_slot = slot
                    return
            button = self._clicked_button(pos)
            if button == "menu_new":
                self.scene = "setup"
            elif button == "menu_load":
                self._load_slot(self.selected_slot)
            elif button == "menu_quit":
                self._force_exit()
            elif button == "menu_settings":
                self.settings_open = True
            return

        if self.scene == "setup":
            for idx, rect in self.city_rows:
                if rect.collidepoint(pos):
                    self.new_city = idx
                    return
            button = self._clicked_button(pos)
            if button == "setup_back":
                self.scene = "menu"
            elif button == "setup_start":
                self._start_new_game()
            elif button == "setup_gender_m":
                self.new_gender = "m"
            elif button == "setup_gender_w":
                self.new_gender = "w"
            return

        if self.scene == "game":
            if self.marriage_popup_open:
                self._handle_marriage_popup_click(pos)
                return
            if self.child_name_popup_open:
                self._handle_child_name_popup_click(pos)
                return
            if self.shipyard_open:
                self.fleet_drag_active = False
                self._handle_shipyard_click(pos)
                return
            if self.ship_cargo_open:
                self.fleet_drag_active = False
                self._handle_ship_cargo_click(pos)
                return
            if self.ship_editor_open:
                self.fleet_drag_active = False
                self._handle_ship_editor_click(pos)
                return
            if self.city_market_open:
                self.fleet_drag_active = False
                self._handle_city_market_click(pos)
                return
            if self.missions_open:
                self.fleet_drag_active = False
                self._handle_missions_click(pos)
                return
            if self.info_open:
                self.fleet_drag_active = False
                self._handle_info_click(pos)
                return
            if self.about_open:
                self.fleet_drag_active = False
                self._handle_about_click(pos)
                return
            fleet_panel = self._fleet_panel_rect()
            if fleet_panel.collidepoint(pos):
                self.fleet_drag_active = True
                self.fleet_drag_start_y = pos[1]
                self.fleet_drag_start_scroll = self.fleet_scroll
                self.fleet_drag_moved = False
            else:
                self.fleet_drag_active = False
                self.fleet_drag_moved = False
            for slot, rect in self.slot_rows:
                if self.save_menu_open and rect.collidepoint(pos):
                    self.selected_slot = slot
                    return
            for idx, rect in self.goods_rows:
                if rect.collidepoint(pos):
                    self.selected_good = idx
                    return
            for idx, rect in self.fleet_rows:
                if rect.collidepoint(pos):
                    self.selected_fleet_ship = idx
                    self._sync_city_with_selected_ship()
                    return
            button = self._clicked_button(pos)
            self._handle_game_button(button)

    def _handle_motion(self, pos: Tuple[int, int]) -> None:
        if self.ship_cargo_open and self.transfer_drag_good is not None:
            for good_name, rect, max_unload, max_load in self.transfer_sliders:
                if good_name == self.transfer_drag_good:
                    self._update_transfer_drag(pos[0], rect, max_unload, max_load)
                    return
        if (
            self.scene == "game"
            and self.player is not None
            and self.fleet_drag_active
            and not self.shipyard_open
            and not self.ship_cargo_open
            and not self.ship_editor_open
            and not self.city_market_open
            and not self.missions_open
            and not self.info_open
            and not self.cheat_open
        ):
            dy = pos[1] - self.fleet_drag_start_y
            if abs(dy) >= 4:
                self.fleet_drag_moved = True
            max_scroll = self._fleet_max_scroll()
            new_scroll = self.fleet_drag_start_scroll - dy
            self.fleet_scroll = max(0, min(max_scroll, int(new_scroll)))

    def _handle_release(self, _pos: Tuple[int, int]) -> None:
        if self.transfer_drag_good is not None:
            self._apply_transfer()
            return
        if self.fleet_drag_active:
            self.fleet_drag_active = False
            self.fleet_drag_start_y = 0
            self.fleet_drag_start_scroll = self.fleet_scroll
            self.fleet_drag_moved = False

    def _handle_wheel(self, event: pygame.event.Event) -> None:
        if self.scene != "game" or self.player is None:
            return
        if self.settings_open:
            return
        if self.about_open:
            return
        mouse = self._virtual_mouse_pos()
        if self.shipyard_open:
            shipyard_list = pygame.Rect(264, 266, 792, self._shipyard_visible_count() * 64)
            if shipyard_list.collidepoint(mouse):
                self.shipyard_offset = max(0, min(self._max_shipyard_offset(), self.shipyard_offset - event.y))
            return
        if self.ship_cargo_open:
            transfer_list = pygame.Rect(144, 250, 760, self._transfer_visible_count() * 48)
            if transfer_list.collidepoint(mouse):
                self.transfer_goods_offset = max(
                    0,
                    min(self._max_transfer_goods_offset(), self.transfer_goods_offset - event.y),
                )
            elif self.dest_list_rect and self.dest_list_rect.collidepoint(mouse):
                ship = self._selected_ship()
                if ship is not None:
                    self.dest_scroll = max(0, min(self._max_destination_offset(ship.city), self.dest_scroll - event.y))
            return
        if self.ship_editor_open:
            if self.editor_weapon_list_rect and self.editor_weapon_list_rect.collidepoint(mouse):
                max_offset = max(0, len(self._available_weapon_centuries()) - self._editor_weapon_visible_count())
                self.editor_weapon_offset = max(0, min(max_offset, self.editor_weapon_offset - event.y))
            return
        if self.info_open:
            step = 34
            self.info_scroll = max(0, min(self.info_max_scroll, self.info_scroll - event.y * step))
            return
        if self.missions_open:
            return
        if self.city_market_open:
            if self.city_analysis_rect and self.city_analysis_rect.collidepoint(mouse):
                visible = max(1, (self.city_analysis_rect.height - 10) // (self.font_small.get_height() + 2))
                max_scroll = max(0, len(self.city_analysis_lines) - visible)
                self.city_analysis_scroll = max(0, min(max_scroll, self.city_analysis_scroll - event.y))
                return
            city_list_rect, _visible_node_count, max_node_offset = self._city_market_node_layout()
            if city_list_rect.collidepoint(mouse):
                self.city_market_node_offset = max(0, min(max_node_offset, self.city_market_node_offset - event.y))
                return
            prices_list, _visible_goods_count, max_goods_offset = self._city_market_goods_layout()
            if prices_list.collidepoint(mouse):
                self.city_goods_offset = max(0, min(max_goods_offset, self.city_goods_offset - event.y))
                return
            if self.city_building_list_rect and self.city_building_list_rect.collidepoint(mouse):
                selected_city = self._selected_city_market_name()
                building_entries = [
                    entry for entry in self._city_economy(selected_city).buildings if entry.id in PRODUCTION_RECIPES
                ]
                _rect, visible_building_count = self._city_market_building_layout()
                max_building_offset = max(0, len(building_entries) - visible_building_count)
                self.city_building_offset = max(0, min(max_building_offset, self.city_building_offset - event.y))
            return

        goods_panel = pygame.Rect(36, 228, 590, self._market_visible_count() * 50)
        if goods_panel.collidepoint(mouse):
            self.market_goods_offset = max(0, min(self._max_market_goods_offset(), self.market_goods_offset - event.y))
            return
        fleet_panel = self._fleet_panel_rect()
        if not fleet_panel.collidepoint(mouse):
            return
        self._scroll_fleet(-event.y * 24)

    def _clicked_button(self, pos: Tuple[int, int]) -> str | None:
        for key, (rect, enabled) in reversed(list(self.button_states.items())):
            if enabled and rect.collidepoint(pos):
                return key
        return None

    def _handle_game_button(self, key: str | None) -> None:
        if key is None:
            return
        if key == "game_buy":
            self._buy_selected_good()
        elif key == "game_sell":
            self._sell_selected_good()
        elif key == "game_qty_minus":
            self.trade_qty = max(1, self.trade_qty - 1)
        elif key == "game_qty_plus":
            self.trade_qty = min(99, self.trade_qty + 1)
        elif key == "game_fleet_up":
            self._scroll_fleet(-120)
        elif key == "game_fleet_down":
            self._scroll_fleet(120)
        elif key == "game_market_up":
            self.market_goods_offset = max(0, self.market_goods_offset - 1)
        elif key == "game_market_down":
            self.market_goods_offset = min(self._max_market_goods_offset(), self.market_goods_offset + 1)
        elif key == "game_cargo":
            self._open_ship_cargo()
        elif key == "game_shipyard":
            self._open_shipyard()
        elif key == "game_ship_editor":
            self._open_ship_editor()
        elif key == "game_city_prices":
            self.city_market_open = True
            self.city_goods_offset = 0
            self.city_building_offset = 0
            self.city_analysis_scroll = 0
        elif key == "game_missions":
            self.missions_open = True
        elif key == "game_heir":
            self._conceive_heir()
        elif key == "game_info":
            self.info_open = True
            self.info_scroll = 0
            self.info_max_scroll = 0
        elif key == "game_settings":
            self.settings_open = True
        elif key == "game_export":
            path = self._export_csv_report()
            if path:
                self._log(f"CSV exportiert: {path}")
            else:
                self._log("CSV-Export fehlgeschlagen.")
        elif key == "game_repair_hull":
            self._repair("hull")
        elif key == "game_repair_rig":
            self._repair("rigging")
        elif key == "game_auto":
            self._toggle_auto_mode()
        elif key == "policy_risk_minus":
            self._auto_policy_adjust_risk(-5)
        elif key == "policy_risk_plus":
            self._auto_policy_adjust_risk(5)
        elif key == "policy_reserve_minus":
            self._auto_policy_adjust_reserve(-250)
        elif key == "policy_reserve_plus":
            self._auto_policy_adjust_reserve(250)
        elif key == "policy_invest_cycle":
            self._auto_policy_cycle_invest_mode()
        elif key.startswith("policy_focus_"):
            city_name = key.replace("policy_focus_", "", 1)
            self._auto_policy_toggle_focus_city(city_name)
        elif key == "game_next_year":
            self._safe_advance_month("manuell")
        elif key == "game_save":
            if not self.save_menu_open or self.save_menu_mode != "save":
                self.save_menu_open = True
                self.save_menu_mode = "save"
                self.about_open = False
                self.about_panel_rect = None
            else:
                self._save_slot(self.selected_slot)
                self.save_menu_open = False
                self.save_menu_mode = None
                self.about_open = False
                self.about_panel_rect = None
        elif key == "game_load":
            if not self.save_menu_open or self.save_menu_mode != "load":
                self.save_menu_open = True
                self.save_menu_mode = "load"
                self.about_open = False
                self.about_panel_rect = None
            else:
                self._load_slot(self.selected_slot)
                self.save_menu_open = False
                self.save_menu_mode = None
                self.about_open = False
                self.about_panel_rect = None
        elif key == "save_menu_info":
            if self.save_menu_open:
                self.about_open = True
        elif key == "game_menu":
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.ship_editor_ship = None
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            self.save_menu_open = False
            self.save_menu_mode = None
            self.about_open = False
            self.about_panel_rect = None
            self.city_market_open = False
            self.missions_open = False
            self.info_open = False
            self.info_scroll = 0
            self.info_max_scroll = 0
            self.market_goods_offset = 0
            self.transfer_goods_offset = 0
            self.city_goods_offset = 0
            self.shipyard_offset = 0
            self.cheat_open = False
            self.cheat_text = ""
            self.marriage_popup_open = False
            self.marriage_candidate = ""
            self.child_name_popup_open = False
            self.child_name_edit = ""
            self.child_name_input_rect = None
            self.auto_mode = False
            if self.player is not None:
                self.player.auto_enabled = False
            self.auto_popup_hold_until = 0
            self.settings_open = False
            self.scene = "menu"

    def _toggle_auto_mode(self) -> None:
        if self.player is None or not self.player.alive:
            return
        self.auto_mode = not self.auto_mode
        self.player.auto_enabled = bool(self.auto_mode)
        if self.auto_mode:
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.ship_editor_ship = None
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            self.city_market_open = False
            self.missions_open = False
            self.info_open = False
            self.info_scroll = 0
            self.info_max_scroll = 0
            self.save_menu_open = False
            self.save_menu_mode = None
            self.cheat_open = False
            self.cheat_text = ""
            self.transfer_drag_good = None
            self.auto_next_tick = pygame.time.get_ticks() + 120
            if self.marriage_popup_open:
                self.auto_popup_hold_until = pygame.time.get_ticks() + AUTO_MARRIAGE_POPUP_MS
            if self.child_name_popup_open:
                self._submit_child_name(auto=True)
            self._log("Auto-Modus aktiv: Atheria steuert Handel, Flotte und Reisen.")
        else:
            self.auto_popup_hold_until = 0
            self._log("Auto-Modus beendet.")

    def _run_auto_mode(self) -> None:
        if not self.auto_mode or self.scene != "game" or self.player is None:
            return
        if self.settings_open:
            return
        self._ensure_runtime_state()
        snapshot = self._snapshot_game_state()
        try:
            if not self.player.alive:
                self.auto_mode = False
                self.player.auto_enabled = False
                self._log("Auto-Modus beendet: Handelshaus erloschen.")
                return
            if self.marriage_popup_open:
                hold_until = int(getattr(self, "auto_popup_hold_until", 0))
                if pygame.time.get_ticks() < hold_until:
                    return
                self._resolve_marriage_proposal(True)
            if self.child_name_popup_open:
                self._submit_child_name(auto=True)
            if (
                self.shipyard_open
                or self.ship_cargo_open
                or self.ship_editor_open
                or self.city_market_open
                or self.missions_open
                or self.cheat_open
                or self.save_menu_open
            ):
                return
            now = pygame.time.get_ticks()
            if now < self.auto_next_tick:
                return
            self.auto_next_tick = now + AUTO_TURN_INTERVAL_MS
            self._auto_play_month()
        except AttributeError as exc:
            self._ensure_runtime_state()
            try:
                self._auto_play_month()
                self._log(f"Auto-Modus: Laufzeitzustand repariert ({exc}).")
                return
            except Exception as inner_exc:
                self._restore_game_state(snapshot)
                self.auto_mode = False
                if self.player is not None:
                    self.player.auto_enabled = False
                self._log(f"Auto-Modus Fehler: {type(inner_exc).__name__}: {inner_exc}. Auto deaktiviert.")
                self._record_runtime_exception(inner_exc, "auto_mode")
        except Exception as exc:
            self._restore_game_state(snapshot)
            self.auto_mode = False
            if self.player is not None:
                self.player.auto_enabled = False
            self._log(f"Auto-Modus Fehler: {type(exc).__name__}: {exc}. Auto deaktiviert.")
            self._record_runtime_exception(exc, "auto_mode")

    def _record_runtime_exception(self, exc: Exception, context: str) -> None:
        try:
            auto_path = self.save_dir / "auto_mode_error.log"
            runtime_path = self.save_dir / "runtime_error.log"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            details = traceback.format_exc()
            entry = (
                f"[{timestamp}] {type(exc).__name__}: {exc}\n"
                f"Context={context} | Year={self.current_year} Month={self.current_month} Scene={self.scene}\n"
                f"{details}\n"
            )
            with runtime_path.open("a", encoding="utf-8") as handle:
                handle.write(entry)
            if context == "auto_mode":
                with auto_path.open("a", encoding="utf-8") as handle:
                    handle.write(entry)
        except Exception:
            # Keine Folgefehler aus dem Fehlerlogger.
            return

    def _record_auto_exception(self, exc: Exception) -> None:
        self._record_runtime_exception(exc, "auto_mode")

    def _safe_advance_month(self, source: str) -> None:
        self._ensure_runtime_state()
        snapshot = self._snapshot_game_state()
        try:
            self._advance_year()
        except Exception as exc:
            self._restore_game_state(snapshot)
            self.auto_mode = False
            self._log(f"Monatswechsel-Fehler ({source}): {type(exc).__name__}: {exc}.")
            self._record_runtime_exception(exc, f"advance_{source}")

    def _auto_player_reserve(self) -> int:
        if self.player is None:
            return 0
        policy = self._player_auto_policy()
        policy_reserve = max(0, int(policy.get("reserve_mark", AUTO_MIN_RESERVE_MARK)))
        return max(policy_reserve, 500 + len(self.player.ships) * AUTO_RESERVE_PER_SHIP_MARK)

    def _auto_travel_cost(self, origin: str, target: str) -> int:
        return self._travel_cost_for_route(origin, target)

    def _auto_pick_modern_ship_index(self, budget: int) -> int | None:
        shipyard = self._active_shipyard()
        if not shipyard:
            return None
        budget_i = max(0, int(budget))
        affordable: List[Tuple[int, int, int, int]] = []
        for idx, (_name, cap, value, cost) in enumerate(shipyard):
            if cost <= budget_i:
                affordable.append((cap, value, -cost, idx))
        if not affordable:
            return None
        return max(affordable)[3]

    def _auto_replace_outdated_ship(self, old_ship: Ship) -> bool:
        if self.player is None:
            return False
        if old_ship not in self.player.ships:
            return False
        if old_ship.is_at_sea or old_ship.total_cargo > 0:
            return False

        shipyard = self._active_shipyard()
        if not shipyard:
            return False
        latest_idx = max(
            range(len(shipyard)),
            key=lambda idx: (shipyard[idx][1], shipyard[idx][2], shipyard[idx][3]),
        )
        old_city = old_ship.city
        self.player.city = old_city
        old_idx = self.player.ships.index(old_ship)
        self.selected_fleet_ship = old_idx
        reserve = max(self._auto_player_reserve(), 1400)
        immediate_budget = max(0, self.player.money - reserve)
        immediate_idx = self._auto_pick_modern_ship_index(immediate_budget)
        if immediate_idx is not None:
            before = len(self.player.ships)
            self.selected_ship_type = immediate_idx
            self._buy_selected_ship_type(auto_named=True)
            if len(self.player.ships) > before and old_ship in self.player.ships:
                replacement_ship = self.player.ships[-1]
                if old_ship.custom_name and not replacement_ship.custom_name:
                    replacement_ship.custom_name = old_ship.custom_name
                self.player.city = old_city
                self.selected_fleet_ship = self.player.ships.index(old_ship)
                self._sell_selected_ship()
                return True

        sale_value = self._ship_sale_price(old_ship)
        delayed_budget = max(0, self.player.money + sale_value - reserve)
        delayed_idx = self._auto_pick_modern_ship_index(delayed_budget)
        if delayed_idx is None:
            return False

        # Mit nur einem Schiff keine aggressive Ersetzung, wenn danach zu wenig Handelsreserve bleibt.
        if len(self.player.ships) <= 1 and delayed_idx == latest_idx and delayed_budget < shipyard[delayed_idx][3]:
            return False

        if old_ship in self.player.ships:
            self.player.city = old_city
            self.selected_fleet_ship = self.player.ships.index(old_ship)
            self._sell_selected_ship()
        self.player.city = old_city
        before = len(self.player.ships)
        self.selected_ship_type = delayed_idx
        self._buy_selected_ship_type(auto_named=True)
        if len(self.player.ships) > before and old_ship.custom_name:
            replacement_ship = self.player.ships[-1]
            if not replacement_ship.custom_name:
                replacement_ship.custom_name = old_ship.custom_name
        return len(self.player.ships) > before

    def _auto_modernize_fleet(self) -> None:
        if self.player is None or self.player.turns_in_debt_tower > 0:
            return
        shipyard = self._active_shipyard()
        if not shipyard:
            return
        modern_names = {name for name, *_ in shipyard}
        replaced = 0
        candidates = [
            ship
            for ship in self.player.ships
            if ship.name not in modern_names and not ship.is_at_sea and ship.total_cargo <= 0
        ]
        for ship in candidates:
            if replaced >= AUTO_MAX_SHIP_REPLACEMENTS_PER_MONTH:
                break
            if ship not in self.player.ships:
                continue
            if self._auto_replace_outdated_ship(ship):
                replaced += 1
        if replaced > 0:
            self._log(f"Auto-Modernisierung: {replaced} veraltete Schiffe ersetzt.")

    def _auto_refresh_ship_weaponry(self, ship: Ship) -> None:
        if ship.is_at_sea:
            return
        if not hasattr(ship, "cannon_inventory") or not isinstance(ship.cannon_inventory, dict):
            ship.cannon_inventory = {}
        current_key = str(max(14, int(self.current_century)))
        normalized: Dict[str, int] = {}
        for raw_key, raw_qty in ship.cannon_inventory.items():
            try:
                qty_i = max(0, int(raw_qty))
            except (TypeError, ValueError):
                continue
            if qty_i > 0:
                normalized[str(raw_key)] = qty_i

        if ship.cannons <= 0:
            if normalized:
                ship.cannon_inventory = {}
            return

        old_qty = sum(qty for key, qty in normalized.items() if key != current_key)
        current_qty = max(0, int(normalized.get(current_key, 0)))
        if old_qty > 0 or current_qty != ship.cannons:
            ship.cannon_inventory = {current_key: int(ship.cannons)}
            if old_qty > 0:
                self._log(f"Auto-Aufruestung: {ship.display_name} auf Kanonenstufe C{current_key} vereinheitlicht.")

    def _auto_building_upgrade_cost(self, city_name: str, building: Building) -> int:
        unlock = RECIPE_UNLOCK_CENTURY.get(building.id, 14)
        level = max(1, int(building.level))
        base = self._share_price_per_percent(city_name, building)
        return max(1000, int(round(base * (6 + level * 0.9) + unlock * 40)))

    def _auto_invest_city_economy(self) -> None:
        if self.player is None or self.player.turns_in_debt_tower > 0:
            return
        policy = self._player_auto_policy()
        mode = str(policy.get("invest_mode", "balanced")).strip().lower()
        if mode == "conservative":
            share_cap = 1
            upgrade_cap = 0
            reserve_factor = 1.35
        elif mode == "aggressive":
            share_cap = AUTO_MAX_SHARE_BUYS_PER_MONTH + 1
            upgrade_cap = AUTO_MAX_BUILDING_UPGRADES_PER_MONTH + 1
            reserve_factor = 0.90
        else:
            share_cap = AUTO_MAX_SHARE_BUYS_PER_MONTH
            upgrade_cap = AUTO_MAX_BUILDING_UPGRADES_PER_MONTH
            reserve_factor = 1.0

        share_reserve = max(int(self._auto_player_reserve() * reserve_factor), AUTO_SHARE_INVEST_RESERVE_MARK)
        share_buys = 0
        share_candidates: List[Tuple[float, float, int, str, str]] = []
        for city_name in CITIES:
            city = self._city_economy(city_name)
            influence = self._player_city_influence(city_name)
            for building in city.buildings:
                recipe = PRODUCTION_RECIPES.get(building.id)
                if recipe is None:
                    continue
                if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > self.current_century:
                    continue
                sold_pct = self._total_building_share_percent(city_name, building.id)
                free_pct = max(0.0, MAX_BUILDING_SHARE_PERCENT - sold_pct)
                if free_pct < 1.0:
                    continue
                price_per_pct = self._share_price_per_percent(city_name, building)
                if price_per_pct <= 0:
                    continue
                pool = self._building_dividend_pool(city_name, building.id)
                score = float(pool) + influence * 38.0 + max(1, int(building.level)) * 24.0
                share_candidates.append((score, influence, price_per_pct, city_name, building.id))
        share_candidates.sort(key=lambda item: (item[0], item[1], -item[2]), reverse=True)
        for _score, _influence, price_per_pct, city_name, recipe_id in share_candidates:
            if share_buys >= share_cap:
                break
            buy_pct = 5
            if self.player.money - (price_per_pct * buy_pct) < share_reserve:
                continue
            before = self._player_building_share_percent(city_name, recipe_id)
            self._buy_city_building_shares(city_name, recipe_id, pct=buy_pct)
            after = self._player_building_share_percent(city_name, recipe_id)
            if after > before:
                share_buys += 1

        if upgrade_cap <= 0:
            return

        building_reserve = max(int(self._auto_player_reserve() * reserve_factor), AUTO_BUILDING_INVEST_RESERVE_MARK)
        upgrades = 0
        upgrade_candidates: List[Tuple[float, int, str, str]] = []
        for city_name in CITIES:
            city = self._city_economy(city_name)
            influence = self._player_city_influence(city_name)
            for building in city.buildings:
                if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > self.current_century:
                    continue
                if not building.active:
                    continue
                level = max(1, int(building.level))
                if level >= AUTO_BUILDING_LEVEL_CAP:
                    continue
                owned_share = self._player_building_share_percent(city_name, building.id)
                if owned_share <= 0 and influence < 4.0:
                    continue
                cost = self._auto_building_upgrade_cost(city_name, building)
                score = owned_share * 2.0 + influence * 0.8 + level * 0.35
                upgrade_candidates.append((score, -cost, city_name, building.id))
        upgrade_candidates.sort(reverse=True)
        for _score, neg_cost, city_name, recipe_id in upgrade_candidates:
            if upgrades >= upgrade_cap:
                break
            cost = -neg_cost
            if self.player.money - cost < building_reserve:
                continue
            city = self._city_economy(city_name)
            building = next((entry for entry in city.buildings if entry.id == recipe_id), None)
            if building is None:
                continue
            level_before = max(1, int(building.level))
            if level_before >= AUTO_BUILDING_LEVEL_CAP:
                continue
            self.player.money -= cost
            building.level = level_before + 1
            city.treasury += int(round(cost * 0.38))
            self._add_player_city_influence(city_name, 0.32 + level_before * 0.04)
            recipe = PRODUCTION_RECIPES.get(recipe_id)
            label = recipe.name if recipe else recipe_id
            self._log(
                f"Auto-Betriebsausbau {city_name}: {label} L{level_before}->{building.level} fuer {cost} Mark."
            )
            upgrades += 1

    def _auto_invest_macro_projects(self) -> None:
        if self.player is None or self.player.turns_in_debt_tower > 0:
            return
        policy = self._player_auto_policy()
        mode = str(policy.get("invest_mode", "balanced")).strip().lower()
        if mode == "conservative":
            reserve_factor = 1.35
            social_targets = 1
            research_threshold = 1.35
            infra_threshold = 1.30
            sophia_threshold = 1.50
        elif mode == "aggressive":
            reserve_factor = 0.90
            social_targets = 3
            research_threshold = 1.05
            infra_threshold = 1.00
            sophia_threshold = 1.10
        else:
            reserve_factor = 1.0
            social_targets = 2
            research_threshold = 1.15
            infra_threshold = 1.10
            sophia_threshold = 1.25

        reserve = max(int(self._auto_player_reserve() * reserve_factor), 22_000 + len(self.player.ships) * 700)

        # 1) Stadtrettung priorisieren.
        for city_name in CITIES:
            city = self._city_economy(city_name)
            city.bankrupt = 1 if city.treasury <= CITY_BANKRUPTCY_LIMIT else int(city.bankrupt)
            if city.bankrupt != 1:
                continue
            bailout_cost = self._city_bailout_cost(city_name)
            if self.player.money - bailout_cost < reserve:
                continue
            self.execute_city_bailout(self.player, city_name)

        # 2) Sozialstiftung in schwachen Staedten.
        social_cost = self._next_investment_cost(TRACK_SOCIAL)
        weak_cities = sorted(
            CITIES,
            key=lambda city_name: (
                self._city_economy(city_name).social_stability + self._city_economy(city_name).quality_of_life,
                self._city_economy(city_name).population,
            ),
        )
        for city_name in weak_cities[:social_targets]:
            if self.player.money - social_cost < reserve:
                break
            self.invest_in_social_welfare(self.player, city_name, social_cost)

        # 3) Forschungs- und Infrastrukturspruenge fuer Langzeitdominanz.
        research_cost = self._next_investment_cost(TRACK_RESEARCH)
        if self.player.money - research_cost >= int(reserve * research_threshold):
            self.invest_in_research_resonance(self.player, research_cost)
        infra_cost = self._next_investment_cost(TRACK_INFRASTRUCTURE)
        if self.player.money - infra_cost >= int(reserve * infra_threshold):
            self.invest_in_infrastructure(self.player, infra_cost)

        # 4) Marktstabilisierung als Volatilitaetsdaempfer.
        sophia_cost = self.research_manager.cost_for_level(TRACK_SOPHIA, self._investment_level(TRACK_SOPHIA))
        if self.player.money - sophia_cost >= int(reserve * sophia_threshold):
            self.invest_in_algorithmic_harmony(self.player, sophia_cost)

    def _auto_play_month(self) -> None:
        if self.player is None or not self.player.alive:
            self.auto_mode = False
            if self.player is not None:
                self.player.auto_enabled = False
            return
        self._auto_modernize_fleet()
        self._auto_build_ship_if_possible()
        harbor_indices = [idx for idx, ship in enumerate(self.player.ships) if not ship.is_at_sea]
        for idx in harbor_indices:
            if idx >= len(self.player.ships):
                continue
            self.selected_fleet_ship = idx
            ship = self._selected_ship()
            if ship is None or ship.is_at_sea:
                continue
            self.player.city = ship.city
            self._storage_for_city(ship.city)
            self._auto_unload_ship(ship)
            self._auto_sell_city_storage(ship.city)
            self._auto_maintain_ship(ship)
            route = self._auto_choose_route(ship)
            if route is None:
                continue
            target, plan, expected_profit = route
            self._auto_prepare_and_send_ship(ship, target, plan, expected_profit)
        self._auto_invest_city_economy()
        self._auto_invest_macro_projects()
        self._safe_advance_month("auto")

    def _auto_build_ship_if_possible(self) -> None:
        if self.player is None or self.player.turns_in_debt_tower > 0:
            return
        risk = int(self._player_auto_policy().get("risk", 50))
        max_fleet_size = max(6, min(AUTO_MAX_FLEET_SIZE, 8 + risk // 5))
        if len(self.player.ships) >= max_fleet_size:
            return
        month_index = self._month_index()
        if month_index - int(getattr(self, "auto_last_ship_build_month", -9999)) < AUTO_SHIP_BUILD_COOLDOWN_MONTHS:
            return
        harbor_ship = next((ship for ship in self.player.ships if not ship.is_at_sea), None)
        if harbor_ship is None:
            if self.player.ships:
                return
            build_city = self.player.city if self.player.city in CITIES else CITIES[0]
        else:
            build_city = harbor_ship.city
        self.player.city = build_city
        reserve = max(self._auto_player_reserve(), AUTO_SHIP_BUILD_RESERVE + len(self.player.ships) * 450)
        budget = self.player.money - reserve
        shipyard = self._active_shipyard()
        if not shipyard:
            return
        cheapest = min(cost for _, _, _, cost in shipyard)
        if budget < cheapest:
            return

        selected_idx: int | None = None
        mission = self.player.missions.get("fleet_synergy", {})
        if mission.get("state") != "completed":
            synergy_names = [name for name, *_ in self._fleet_synergy_shipyard()]
            counts = {name: 0 for name in synergy_names}
            for ship in self.player.ships:
                if ship.name in counts:
                    counts[ship.name] += 1
            missing: List[Tuple[int, int, int]] = []
            for idx, (name, _cap, _value, cost) in enumerate(shipyard):
                owned = counts.get(name, 0)
                if owned < FLEET_SYNERGY_REQUIRED and cost <= budget:
                    missing.append((owned, cost, idx))
            if missing:
                selected_idx = min(missing)[2]

        if selected_idx is None:
            affordable = [
                (cap, -cost, idx)
                for idx, (_name, cap, _value, cost) in enumerate(shipyard)
                if cost <= budget
            ]
            if affordable:
                selected_idx = max(affordable)[2]

        if selected_idx is None:
            return
        self.selected_ship_type = selected_idx
        fleet_before = len(self.player.ships)
        self._buy_selected_ship_type(auto_named=True)
        if len(self.player.ships) > fleet_before:
            self.auto_last_ship_build_month = month_index

    def _auto_maintain_ship(self, ship: Ship) -> None:
        if self.player is None or ship.is_at_sea:
            return
        self._auto_refresh_ship_weaponry(ship)
        reserve = self._auto_player_reserve()
        while ship.hull < AUTO_REPAIR_TARGET:
            amount = min(10, 100 - ship.hull)
            cost = amount * 16
            if self.player.money - cost < reserve:
                break
            self._repair("hull")
        while ship.rigging < AUTO_REPAIR_TARGET:
            amount = min(10, 100 - ship.rigging)
            cost = amount * 12
            if self.player.money - cost < reserve:
                break
            self._repair("rigging")

        max_cannons = self._max_cannons(ship)
        cannon_target = max(2, min(max_cannons, 4 + len(self.player.ships) // 2))
        if self.player.money > 14000:
            cannon_target = min(max_cannons, cannon_target + 3)
        if self.player.money > 28000:
            cannon_target = min(max_cannons, cannon_target + 3)
        if self.player.money > 50000:
            cannon_target = min(max_cannons, cannon_target + 4)
        bought = 0
        while ship.cannons < cannon_target and bought < AUTO_MAX_CANNON_BUYS:
            if self.player.money - self._active_cannon_cost() < reserve:
                break
            self._buy_cannons(ship, 1, weapon_century=self.current_century)
            bought += 1

    def _auto_unload_ship(self, ship: Ship) -> int:
        if self.player is None:
            return 0
        storage = self._storage_for_city(ship.city)
        locks = self._locks_for_city(ship.city)
        moved = 0
        current_prices = self._market_prices(ship.city)
        for good_name in self._active_good_names():
            qty = ship.cargo.get(good_name, 0)
            if qty <= 0:
                continue
            moved += qty
            storage[good_name] = storage.get(good_name, 0) + qty
            ship.cargo[good_name] = 0

            locked_qty = ship.locked_qty.get(good_name, 0)
            if locked_qty > 0:
                move_locked = min(qty, locked_qty)
                if move_locked > 0:
                    price = ship.locked_prices.get(good_name, current_prices[good_name])
                    locks.setdefault(good_name, []).append({"qty": move_locked, "price": price})
                remaining_locked = locked_qty - move_locked
                if remaining_locked > 0:
                    ship.locked_qty[good_name] = remaining_locked
                else:
                    ship.locked_qty.pop(good_name, None)
                    ship.locked_prices.pop(good_name, None)
        if moved > 0:
            self._log(f"Auto-Verladen: {ship.display_name} entladen in {ship.city}.")
        return moved

    def _auto_sell_city_storage(self, city: str) -> int:
        if self.player is None:
            return 0
        storage = self._storage_for_city(city)
        prices = self._market_prices(city)
        total_revenue = 0
        sold_goods = 0
        for good_name in self._active_good_names():
            qty = storage.get(good_name, 0)
            if qty <= 0:
                continue
            locked_revenue, locked_sold = self._consume_locked_lots(city, good_name, qty)
            remaining = qty - locked_sold
            revenue = locked_revenue + remaining * prices[good_name]
            storage[good_name] = max(0, storage.get(good_name, 0) - qty)
            self._city_add_inventory(city, good_name, qty)
            self.player.money += revenue
            self._record_hanse_delivery(city, good_name, qty)
            self._record_trade_for_missions(good_name, qty)
            total_revenue += revenue
            sold_goods += 1
        if sold_goods > 0:
            if self.rng.random() < 0.35:
                self.player.reputation = min(200, self.player.reputation + 1)
            self._log(f"Auto-Handel ({city}): {sold_goods} Waren verkauft, +{total_revenue} Mark.")
        return total_revenue

    def _auto_buy_good(self, city: str, good_name: str, qty: int) -> int:
        if self.player is None or qty <= 0:
            return 0
        city_stock = self._city_inventory_qty(city, good_name)
        if city_stock <= 0:
            return 0
        price = self._market_prices(city)[good_name]
        discount = self._city_discount(city)
        if discount > 0:
            price = max(1, int(round(price * (1 - discount))))
        affordable = self.player.money // price
        bought = min(qty, affordable, city_stock)
        if bought <= 0:
            return 0
        bought = self._city_take_inventory(city, good_name, bought)
        if bought <= 0:
            return 0
        storage = self._storage_for_city(city)
        storage[good_name] = storage.get(good_name, 0) + bought
        self.player.money -= bought * price
        return bought

    def _auto_move_storage_to_ship(self, ship: Ship, city: str, good_name: str, qty: int) -> int:
        if self.player is None or qty <= 0:
            return 0
        storage = self._storage_for_city(city)
        available = min(storage.get(good_name, 0), ship.cargo_space_left)
        moved = min(qty, available)
        if moved <= 0:
            return 0
        locks = self._locks_for_city(city)
        storage_total = storage.get(good_name, 0)
        locked_total = self._locked_total(locks, good_name)
        unlocked_available = max(0, storage_total - locked_total)
        remaining = moved - min(unlocked_available, moved)
        if remaining > 0:
            self._remove_locked_qty(locks.get(good_name, []), remaining)
        storage[good_name] = storage_total - moved
        ship.cargo[good_name] = ship.cargo.get(good_name, 0) + moved
        return moved

    def _auto_plan_route(self, ship: Ship, target: str) -> tuple[int, int, List[Tuple[str, int]], int]:
        if self.player is None:
            return 0, 0, [], 0
        travel_cost = self._auto_travel_cost(ship.city, target)
        reserve = self._auto_player_reserve()
        available = max(0, self.player.money - reserve - travel_cost)
        budget = max(0, min(available, int(available * self._auto_trade_budget_share())))
        capacity = ship.cargo_space_left
        if budget <= 0 or capacity <= 0:
            return travel_cost, 0, [], -travel_cost

        city_prices = self._market_prices(ship.city)
        target_prices = self._market_prices(target)
        discount = self._city_discount(ship.city)
        opportunities: List[Tuple[float, int, int, str]] = []
        for good_name in self._active_good_names():
            buy_price = city_prices[good_name]
            if discount > 0:
                buy_price = max(1, int(round(buy_price * (1 - discount))))
            margin = target_prices[good_name] - buy_price
            if margin <= 0:
                continue
            roi = margin / buy_price
            opportunities.append((roi, margin, buy_price, good_name))
        opportunities.sort(reverse=True)

        plan: List[Tuple[str, int]] = []
        expected_profit = 0
        for _roi, margin, buy_price, good_name in opportunities:
            if capacity <= 0 or budget < buy_price:
                continue
            qty = min(capacity, budget // buy_price)
            if qty <= 0:
                continue
            plan.append((good_name, int(qty)))
            expected_profit += int(qty) * margin
            budget -= int(qty) * buy_price
            capacity -= int(qty)
        score = expected_profit - travel_cost
        return travel_cost, expected_profit, plan, score

    def _auto_choose_route(self, ship: Ship) -> Tuple[str, List[Tuple[str, int]], int] | None:
        best_target = ""
        best_plan: List[Tuple[str, int]] = []
        best_profit = 0
        best_score = -10**9
        for city_name in self._auto_policy_focus_targets(ship.city):
            _travel_cost, expected_profit, plan, score = self._auto_plan_route(ship, city_name)
            if not plan:
                continue
            if score > best_score:
                best_score = score
                best_target = city_name
                best_plan = plan
                best_profit = expected_profit
        if not best_plan or best_score < self._auto_route_min_score():
            return None
        return best_target, best_plan, best_profit

    def _auto_prepare_and_send_ship(
        self,
        ship: Ship,
        target: str,
        plan: List[Tuple[str, int]],
        expected_profit: int,
    ) -> bool:
        if self.player is None:
            return False
        origin = ship.city
        loaded_total = 0
        manifest: List[str] = []
        for good_name, desired_qty in plan:
            bought = self._auto_buy_good(origin, good_name, desired_qty)
            if bought <= 0:
                continue
            moved = self._auto_move_storage_to_ship(ship, origin, good_name, bought)
            if moved <= 0:
                continue
            loaded_total += moved
            manifest.append(f"{good_name}:{moved}")

        if loaded_total <= 0:
            return False
        destinations = self._available_trade_destinations(ship.city)
        if target not in destinations:
            return False
        self.selected_dest = destinations.index(target)
        self._travel_selected_ship()
        if ship.is_at_sea and ship.destination == target:
            details = ", ".join(manifest[:3])
            if len(manifest) > 3:
                details += ", ..."
            self._log(
                f"Auto-Route: {ship.display_name} {origin} -> {target} | Ladung {loaded_total} | "
                f"Prognose +{expected_profit} Mark ({details})."
            )
            return True
        return False

    def _open_shipyard(self) -> None:
        if self.player is None or not self.player.alive:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Schiffbau nicht moeglich.")
            return
        self.shipyard_open = True
        shipyard = self._active_shipyard()
        if self.selected_ship_type >= len(shipyard):
            self.selected_ship_type = 0
        max_offset = self._max_shipyard_offset()
        self.shipyard_offset = max(0, min(self.selected_ship_type, max_offset))

    def _handle_shipyard_click(self, pos: Tuple[int, int]) -> None:
        for idx, rect in self.ship_rows:
            if rect.collidepoint(pos):
                self.selected_ship_type = idx
                return
        button = self._clicked_button(pos)
        if button == "shipyard_buy":
            self._buy_selected_ship_type(auto_named=True)
            return
        if button == "shipyard_sell":
            self._sell_selected_ship()
            return
        if button == "shipyard_close":
            self.shipyard_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            return

    def _buy_selected_ship_type(self, auto_named: bool = False) -> None:
        if self.player is None:
            return
        shipyard = self._active_shipyard()
        if not shipyard:
            self._log("Keine Schiffe verfuegbar.")
            return
        if self.selected_ship_type >= len(shipyard):
            self.selected_ship_type = 0
        name, cap, value, cost = shipyard[self.selected_ship_type]
        if self.player.money < cost:
            self._log(f"Nicht genug Mark. Benoetigt: {cost}")
            return
        self.player.money -= cost
        new_ship = Ship(
            name=name,
            cargo_capacity=cap,
            value=value,
            city=self.player.city,
            cargo={good: 0 for good in self._active_good_names()},
        )
        if auto_named:
            self._apply_auto_ship_name(new_ship)
        self.player.ships.append(new_ship)
        self.selected_fleet_ship = len(self.player.ships) - 1
        self.shipyard_open = False
        self._log(f"Neues Schiff gekauft: {new_ship.display_name}. Kosten: {cost} Mark.")
        self.player.chronicle.append(
            f"ANNO {self.current_year}: {new_ship.display_name} als neues Schiff erworben."
        )

    def _ship_sale_price(self, ship: Ship) -> int:
        condition = max(0.20, min(1.0, (ship.hull + ship.rigging) / 200.0))
        hull_value = int(ship.value * (0.32 + 0.38 * condition))
        cannon_value = int(ship.cannons * 0.35 * self._ship_cannon_avg_cost(ship))
        return max(100, hull_value + cannon_value)

    def _sell_selected_ship(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if len(self.player.ships) <= 1:
            self._log("Das letzte Schiff kann nicht verkauft werden.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist auf See und kann nicht verkauft werden.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        if ship.total_cargo > 0:
            self._log("Bitte Schiff erst komplett entladen.")
            return
        sale_value = self._ship_sale_price(ship)
        sold_name = ship.display_name
        if self.ship_editor_ship is ship:
            self.ship_editor_ship = None
            self.ship_editor_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
        del self.player.ships[self.selected_fleet_ship]
        self.selected_fleet_ship = max(0, min(self.selected_fleet_ship, len(self.player.ships) - 1))
        self.player.money += sale_value
        selected_after = self._selected_ship()
        if selected_after is not None and not selected_after.is_at_sea:
            self.player.city = selected_after.city
        self._log(f"Schiff verkauft: {sold_name} fuer {sale_value} Mark.")
        self.player.chronicle.append(f"ANNO {self.current_year}: {sold_name} verkauft ({sale_value} Mark).")

    def _selected_ship(self) -> Ship | None:
        if self.player is None or not self.player.ships:
            return None
        if self.selected_fleet_ship >= len(self.player.ships):
            self.selected_fleet_ship = 0
        return self.player.ships[self.selected_fleet_ship]

    def _sync_city_with_selected_ship(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None:
            return
        if not ship.is_at_sea:
            self.player.city = ship.city
            self._storage_for_city(ship.city)
            self.preview_destination = None
        else:
            self.preview_destination = ship.destination

    def _storage_for_city(self, city: str) -> Dict[str, int]:
        if self.player is None:
            return {}
        storage = self.player.warehouses.setdefault(city, {})
        for good in self._active_good_names():
            storage.setdefault(good, 0)
        self._locks_for_city(city)
        return storage

    def _init_missions(self) -> None:
        if self.player is None:
            return
        missions = self.player.missions
        missions.setdefault("hanse_privileg", {"state": "inactive"})
        missions.setdefault("fleet_synergy", {"state": "inactive"})
        missions.setdefault("atheria_resonance", {"state": "inactive"})
        missions.setdefault("family_dynasty", {"state": "inactive"})
        missions.setdefault(
            "brewmaster",
            {"state": "active", "target": QUEST_BREWMASTER_TARGET, "delivered": 0, "next_log": 40},
        )
        missions.setdefault(
            "timber_trade",
            {"state": "active", "target": QUEST_TIMBER_TARGET, "delivered": 0, "next_log": 60},
        )
        route_mission = missions.setdefault(
            "route_master",
            {"state": "active", "target": QUEST_ROUTE_MASTER_TARGET_CITIES, "visited": [self.player.city]},
        )
        visited_raw = route_mission.get("visited", [])
        visited = [str(city_name) for city_name in visited_raw if isinstance(city_name, str)]
        if self.player.city not in visited:
            visited.append(self.player.city)
        route_mission["visited"] = visited
        missions.setdefault(
            "arms_race",
            {
                "state": "active",
                "target_cannons": QUEST_ARMS_RACE_TARGET_CANNONS,
                "target_ships": QUEST_ARMS_RACE_TARGET_SHIPS,
            },
        )
        self._init_building_quests()

    def _month_index(self) -> int:
        return (self.current_year - STARTING_YEAR) * 12 + (self.current_month - 1)

    def _city_discount(self, city: str) -> float:
        if self.player is None:
            return 0.0
        mission = self.player.missions.get("hanse_privileg", {})
        if mission.get("state") == "completed" and mission.get("city") == city:
            return float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
        return 0.0

    def _update_missions_monthly(self) -> None:
        if self.player is None:
            return
        self._init_missions()
        month_index = self._month_index()
        self._update_hanse_privileg(month_index)
        self._update_fleet_synergy()
        self._update_atheria_resonance()
        self._update_family_dynasty()
        self._update_route_master()
        self._update_arms_race()

    def _update_hanse_privileg(self, month_index: int) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault("hanse_privileg", {})
        state = mission.get("state", "inactive")
        if state == "completed":
            return
        if state == "active":
            deadline = int(mission.get("deadline", month_index))
            delivered = int(mission.get("delivered", 0))
            target = int(mission.get("target", HANSE_PRIVILEG_QTY))
            if month_index > deadline:
                mission["state"] = "failed"
                self._log("Hanse-Privileg gescheitert: Frist abgelaufen.")
                return
            if delivered >= target:
                mission["state"] = "completed"
                mission["discount"] = float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
                self._log(
                    f"Hanse-Privileg erlangt: {mission.get('city')} (-{int(HANSE_PRIVILEG_DISCOUNT * 100)}% Einkauf)."
                )
            return

        if self.economy_state.resource_scarcity < 0.55:
            return

        target_city = max(CITIES, key=lambda city: self._market_prices(city)[HANSE_PRIVILEG_GOOD])
        mission.update(
            {
                "state": "active",
                "city": target_city,
                "good": HANSE_PRIVILEG_GOOD,
                "target": HANSE_PRIVILEG_QTY,
                "delivered": 0,
                "start": month_index,
                "deadline": month_index + HANSE_PRIVILEG_MONTHS,
                "discount": HANSE_PRIVILEG_DISCOUNT,
                "next_log": max(10, HANSE_PRIVILEG_QTY // 4),
            }
        )
        self._log(
            f"Mission gestartet: Hanse-Privileg in {target_city} ({HANSE_PRIVILEG_QTY} {HANSE_PRIVILEG_GOOD} in 12 Monaten)."
        )

    def _record_hanse_delivery(self, city: str, good: str, qty: int) -> None:
        if self.player is None or qty <= 0:
            return
        mission = self.player.missions.get("hanse_privileg", {})
        if mission.get("state") != "active":
            return
        if mission.get("city") != city or mission.get("good") != good:
            return
        delivered = int(mission.get("delivered", 0)) + qty
        target = int(mission.get("target", HANSE_PRIVILEG_QTY))
        mission["delivered"] = delivered
        next_log = int(mission.get("next_log", max(10, target // 4)))
        if delivered >= next_log:
            self._log(f"Hanse-Privileg: {min(delivered, target)}/{target} {good} geliefert.")
            mission["next_log"] = next_log + max(10, target // 4)
        if delivered >= target:
            mission["state"] = "completed"
            mission["discount"] = float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
            self._log(
                f"Hanse-Privileg erlangt: {city} (-{int(HANSE_PRIVILEG_DISCOUNT * 100)}% Einkauf)."
            )

    def _update_fleet_synergy(self) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault("fleet_synergy", {})
        if mission.get("state") == "completed":
            return
        required = {name: 0 for name, *_ in self._fleet_synergy_shipyard()}
        for ship in self.player.ships:
            if ship.name in required and ship.hull > FLEET_SYNERGY_HULL_MIN:
                required[ship.name] += 1
        mission["counts"] = dict(required)
        if all(count >= FLEET_SYNERGY_REQUIRED for count in required.values()) and required:
            mission["state"] = "completed"
            mission["reduction"] = FLEET_SYNERGY_HEUER_REDUCTION
            self._log("Mission erfuellt: Architekt der Synergie (Heuer -10%).")
        else:
            mission.setdefault("state", "active")

    def _update_atheria_resonance(self) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault("atheria_resonance", {})
        state = mission.get("state", "inactive")
        growth = self.economy_state.global_growth
        worth = self._net_worth(self.player, self._market_prices(self.player.city))
        if state == "completed":
            return
        if growth < ATHERIA_RESONANCE_GROWTH_MAX:
            if state != "active":
                mission["state"] = "active"
                mission["baseline"] = worth
                mission["next_log"] = 1.25
                self._log("Mission gestartet: Atheria-Resonanz (Netto-Wert verdoppeln in Rezession).")
            else:
                baseline = max(1, int(mission.get("baseline", worth)))
                ratio = worth / baseline
                next_log = float(mission.get("next_log", 1.25))
                if ratio >= next_log:
                    self._log(f"Atheria-Resonanz: Fortschritt {ratio:.2f}x.")
                    mission["next_log"] = min(2.0, next_log + 0.25)
                if ratio >= ATHERIA_RESONANCE_TARGET_MULT:
                    mission["state"] = "completed"
                    self._log("Mission erfuellt: Atheria-Resonanz (Hall of Fame freigeschaltet).")
            return
        if state == "active":
            mission["state"] = "inactive"
            mission.pop("baseline", None)
            mission.pop("next_log", None)
            self._log("Atheria-Resonanz abgebrochen: Rezession endet.")

    def _update_family_dynasty(self) -> None:
        if self.player is None:
            return
        mission = self.player.missions.setdefault("family_dynasty", {})
        if mission.get("state") == "completed":
            return
        if self.player.age >= DYNASTY_AGE_LIMIT:
            return
        target_fund = DYNASTY_INHERITANCE_PER_CHILD * DYNASTY_CHILDREN_TARGET
        if self.player.children >= DYNASTY_CHILDREN_TARGET and self.player.money >= target_fund:
            mission["state"] = "completed"
            mission["inheritance"] = DYNASTY_INHERITANCE_PER_CHILD
            self._log("Mission erfuellt: Familiendynastie (Erbe gesichert).")

    def _apply_dynasty_heir(self) -> bool:
        if self.player is None:
            return False
        mission = self.player.missions.get("family_dynasty", {})
        if mission.get("state") != "completed" or mission.get("used"):
            return False
        inheritance = int(mission.get("inheritance", DYNASTY_INHERITANCE_PER_CHILD))
        mission["used"] = True
        self.player.age = 18
        self.player.married = False
        self.player.spouse_name = ""
        self.player.marriage_year = None
        self.player.marriage_month = None
        self.player.children = 0
        self.player.child_names = []
        self.player.child_ages = {}
        self.player.turns_in_debt_tower = 0
        self.marriage_popup_open = False
        self.marriage_candidate = ""
        self.child_name_popup_open = False
        self.child_name_edit = ""
        self.child_name_input_rect = None
        if self.player.money < inheritance:
            self.player.money = inheritance
        self.player.chronicle.append(f"ANNO {self.current_year}: Erbe angetreten.")
        self._log("Familiendynastie: Ein Erbe tritt das Handelshaus an.")
        return True

    def _locks_for_city(self, city: str) -> Dict[str, List[Dict[str, int]]]:
        if self.player is None:
            return {}
        locks = self.player.warehouse_locks.setdefault(city, {})
        for good in self._active_good_names():
            lots = locks.get(good, [])
            if not isinstance(lots, list):
                lots = []
            sanitized: List[Dict[str, int]] = []
            for entry in lots:
                if not isinstance(entry, dict):
                    continue
                try:
                    qty = int(entry.get("qty", 0))
                    price = int(entry.get("price", 0))
                except (TypeError, ValueError):
                    continue
                if qty > 0 and price > 0:
                    sanitized.append({"qty": qty, "price": price})
            locks[good] = sanitized
        return locks

    def _locked_total(self, locks: Dict[str, List[Dict[str, int]]], good: str) -> int:
        return sum(int(entry.get("qty", 0)) for entry in locks.get(good, []))

    def _remove_locked_qty(self, lots: List[Dict[str, int]], qty: int) -> None:
        remaining = qty
        while remaining > 0 and lots:
            entry = lots[0]
            entry_qty = int(entry.get("qty", 0))
            if entry_qty <= 0:
                lots.pop(0)
                continue
            take = min(entry_qty, remaining)
            entry["qty"] = entry_qty - take
            remaining -= take
            if entry["qty"] <= 0:
                lots.pop(0)

    def _consume_locked_lots(self, city: str, good: str, qty: int) -> tuple[int, int]:
        locks = self._locks_for_city(city)
        lots = locks.get(good, [])
        remaining = qty
        revenue = 0
        consumed = 0
        while remaining > 0 and lots:
            entry = lots[0]
            entry_qty = int(entry.get("qty", 0))
            entry_price = int(entry.get("price", 0))
            if entry_qty <= 0 or entry_price <= 0:
                lots.pop(0)
                continue
            take = min(entry_qty, remaining)
            revenue += take * entry_price
            consumed += take
            entry["qty"] = entry_qty - take
            remaining -= take
            if entry["qty"] <= 0:
                lots.pop(0)
        return revenue, consumed

    def _open_ship_cargo(self) -> None:
        if self.player is None or not self.player.alive:
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist auf See. Verladen nicht moeglich.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        self.ship_cargo_open = True
        self.transfer_drag_good = None
        self.transfer_drag_value = 0
        max_offset = self._max_transfer_goods_offset()
        self.transfer_goods_offset = max(0, min(self.selected_good, max_offset))
        destinations = self._available_trade_destinations(ship.city)
        if destinations:
            self.selected_dest = min(self.selected_dest, len(destinations) - 1)
            max_dest_offset = self._max_destination_offset(ship.city)
            self.dest_scroll = max(0, min(self.selected_dest, max_dest_offset))
            self.preview_destination = destinations[self.selected_dest]
        else:
            self.dest_scroll = 0
            self.preview_destination = None

    def _open_ship_editor(self) -> None:
        if self.player is None or not self.player.alive:
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        self.ship_editor_open = True
        self.ship_editor_ship = ship
        self.ship_name_active = False
        self.ship_name_edit = ship.custom_name
        self.selected_weapon_century = self.current_century
        self.editor_weapon_offset = 0
        self.editor_weapon_rows = []
        self.editor_weapon_list_rect = None

    def _ship_in_player_fleet(self, ship: Ship | None) -> bool:
        return self.player is not None and ship is not None and ship in self.player.ships

    def _editor_ship(self) -> Ship | None:
        ship = self.ship_editor_ship
        if self._ship_in_player_fleet(ship):
            return ship
        ship = self._selected_ship()
        self.ship_editor_ship = ship
        return ship

    def _handle_ship_cargo_click(self, pos: Tuple[int, int]) -> None:
        ship = self._selected_ship()
        if ship is None:
            self.ship_cargo_open = False
            return
        for idx, rect in self.dest_rows:
            if rect.collidepoint(pos):
                self.selected_dest = idx
                destinations = self._available_trade_destinations(ship.city)
                if destinations:
                    if self.selected_dest < self.dest_scroll:
                        self.dest_scroll = self.selected_dest
                    visible = self._ship_destination_visible_count()
                    if self.selected_dest >= self.dest_scroll + visible:
                        self.dest_scroll = self.selected_dest - visible + 1
                    self.preview_destination = destinations[self.selected_dest]
                return
        for good_name, rect, max_unload, max_load in self.transfer_sliders:
            if rect.collidepoint(pos):
                self.transfer_drag_good = good_name
                self._update_transfer_drag(pos[0], rect, max_unload, max_load)
                return
        button = self._clicked_button(pos)
        if button == "cargo_travel":
            self._travel_selected_ship()
            return
        if button == "cargo_dest_up":
            self.dest_scroll = max(0, self.dest_scroll - 1)
            return
        if button == "cargo_dest_down":
            self.dest_scroll = min(self._max_destination_offset(ship.city), self.dest_scroll + 1)
            return
        if button == "cargo_close":
            self.ship_cargo_open = False
            self.transfer_drag_good = None
            return

    def _handle_ship_editor_click(self, pos: Tuple[int, int]) -> None:
        ship = self._editor_ship()
        if ship is None:
            self.ship_editor_open = False
            self.ship_editor_ship = None
            return
        if self.ship_name_input_rect and self.ship_name_input_rect.collidepoint(pos):
            self.ship_name_active = True
            if not self.ship_name_edit:
                self.ship_name_edit = ship.custom_name or ship.display_name
            return
        for century_i, row in self.editor_weapon_rows:
            if row.collidepoint(pos):
                self.selected_weapon_century = century_i
                return
        button = self._clicked_button(pos)
        if button == "editor_save":
            self._submit_ship_name()
            return
        if button == "editor_weapon_prev":
            self._shift_selected_weapon_century(-1)
            return
        if button == "editor_weapon_next":
            self._shift_selected_weapon_century(1)
            return
        if button == "editor_tier_up":
            self.editor_weapon_offset = max(0, self.editor_weapon_offset - 1)
            return
        if button == "editor_tier_down":
            max_offset = max(0, len(self._available_weapon_centuries()) - self._editor_weapon_visible_count())
            self.editor_weapon_offset = min(max_offset, self.editor_weapon_offset + 1)
            return
        if button == "editor_cannon_1":
            self._buy_cannons(ship, 1, weapon_century=self._normalize_selected_weapon_century())
            return
        if button == "editor_cannon_5":
            self._buy_cannons(ship, 5, weapon_century=self._normalize_selected_weapon_century())
            return
        if button == "editor_close":
            self.ship_editor_open = False
            self.ship_editor_ship = None
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            self.editor_weapon_rows = []
            self.editor_weapon_list_rect = None
            return

    def _update_transfer_drag(self, mouse_x: int, rect: pygame.Rect, max_unload: int, max_load: int) -> None:
        center = rect.centerx
        half = rect.width / 2
        offset = mouse_x - center
        if offset >= 0:
            if max_load <= 0:
                self.transfer_drag_value = 0
                return
            ratio = min(1.0, offset / half)
            self.transfer_drag_value = int(round(ratio * max_load))
        else:
            if max_unload <= 0:
                self.transfer_drag_value = 0
                return
            ratio = min(1.0, abs(offset) / half)
            self.transfer_drag_value = -int(round(ratio * max_unload))

    def _apply_transfer(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None or ship.is_at_sea or ship.city != self.player.city:
            self.transfer_drag_good = None
            self.transfer_drag_value = 0
            return
        if not self.transfer_drag_good:
            return
        good_name = self.transfer_drag_good
        value = self.transfer_drag_value
        storage = self._storage_for_city(self.player.city)
        locks = self._locks_for_city(self.player.city)
        ship.cargo.setdefault(good_name, 0)
        if value > 0:
            storage_total = storage.get(good_name, 0)
            max_load = min(storage_total, ship.cargo_space_left)
            qty = min(value, max_load)
            if qty > 0:
                locked_total = self._locked_total(locks, good_name)
                unlocked_available = max(0, storage_total - locked_total)
                remaining = qty - min(unlocked_available, qty)
                if remaining > 0:
                    self._remove_locked_qty(locks.get(good_name, []), remaining)
                storage[good_name] = storage_total - qty
                ship.cargo[good_name] += qty
                self._log(f"Verladen: {qty} {good_name} auf {ship.display_name}.")
        elif value < 0:
            max_unload = ship.cargo.get(good_name, 0)
            qty = min(-value, max_unload)
            if qty > 0:
                ship.cargo[good_name] -= qty
                storage[good_name] = storage.get(good_name, 0) + qty
                locked_qty = ship.locked_qty.get(good_name, 0)
                if locked_qty > 0:
                    move_locked = min(qty, locked_qty)
                    if move_locked > 0:
                        price = ship.locked_prices.get(good_name)
                        if price is None:
                            price = self._market_prices(self.player.city)[good_name]
                        locks.setdefault(good_name, []).append({"qty": move_locked, "price": price})
                        remaining_locked = locked_qty - move_locked
                        if remaining_locked > 0:
                            ship.locked_qty[good_name] = remaining_locked
                        else:
                            ship.locked_qty.pop(good_name, None)
                            ship.locked_prices.pop(good_name, None)
                self._log(f"Entladen: {qty} {good_name} von {ship.display_name}.")
        self.transfer_drag_good = None
        self.transfer_drag_value = 0

    def _submit_ship_name(self) -> None:
        ship = self._editor_ship()
        if ship is None:
            self.ship_editor_ship = None
            self.ship_name_active = False
            self.ship_name_edit = ""
            return
        name = self.ship_name_edit.strip()
        ship.custom_name = name
        self.ship_name_active = False
        self.ship_name_edit = ""
        self._log(f"Schiffsname gesetzt: {ship.display_name}")

    def _buy_cannons(self, ship: Ship, qty: int, weapon_century: int | None = None) -> None:
        if self.player is None:
            return
        qty = max(0, int(qty))
        if qty <= 0:
            return
        if ship.is_at_sea:
            self._log("Kanonen koennen nur im Hafen montiert werden.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        max_cannons = self._max_cannons(ship)
        possible = max(0, max_cannons - ship.cannons)
        if possible <= 0:
            self._log(f"Maximale Bewaffnung erreicht ({max_cannons}).")
            return
        qty = min(qty, possible)
        if weapon_century is None:
            weapon_century = self.current_century
        weapon_century = max(14, min(self.current_century, int(weapon_century)))
        profile = weapon_profile_for_century(weapon_century)
        cost_per_cannon = int(profile.get("cannon_cost", CANNON_COST))
        cost = cost_per_cannon * qty
        if self.player.money < cost:
            self._log("Nicht genug Mark fuer Kanonen.")
            return
        self.player.money -= cost
        ship.cannons += qty
        if not hasattr(ship, "cannon_inventory") or not isinstance(ship.cannon_inventory, dict):
            ship.cannon_inventory = {}
        key = str(weapon_century)
        ship.cannon_inventory[key] = max(0, int(ship.cannon_inventory.get(key, 0))) + qty
        self._log(
            f"{qty} Kanone(n) ({profile.get('name', 'Standard')}, C{weapon_century}) "
            f"gekauft fuer {cost} Mark."
        )

    def _submit_cheat(self) -> None:
        if self.player is None:
            self.cheat_open = False
            self.cheat_text = ""
            return
        code = self.cheat_text.strip()
        if code.upper() == "HANSE":
            self.player.money += 200000
            self._log("Godmodus aktiviert: +200000 Mark.")
            self.player.chronicle.append(f"ANNO {self.current_year}: Godmodus (HANSE) genutzt.")
        else:
            self._log("Unbekannter Code.")
        self.cheat_open = False
        self.cheat_text = ""

    def _open_marriage_proposal(self) -> None:
        if self.player is None or self.player.married:
            return
        if self.marriage_popup_open or self.child_name_popup_open:
            return
        self.marriage_candidate = self.rng.choice(MARRIAGE_CANDIDATES)
        self.marriage_popup_open = True
        if self.auto_mode:
            self.auto_popup_hold_until = pygame.time.get_ticks() + AUTO_MARRIAGE_POPUP_MS
        self._set_last_marriage_offer_month(self._month_index())

    def _get_last_marriage_offer_month(self) -> int:
        if self.player is None:
            return -9999
        value = getattr(self.player, "last_marriage_offer_month", None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return -9999
        missions = getattr(self.player, "missions", {})
        if isinstance(missions, dict):
            compat = missions.get("_compat_last_marriage_offer_month")
            try:
                return int(compat) if compat is not None else -9999
            except (TypeError, ValueError):
                return -9999
        return -9999

    def _set_last_marriage_offer_month(self, month_index: int) -> None:
        if self.player is None:
            return
        try:
            setattr(self.player, "last_marriage_offer_month", int(month_index))
            return
        except Exception:
            pass
        missions = getattr(self.player, "missions", None)
        if isinstance(missions, dict):
            missions["_compat_last_marriage_offer_month"] = int(month_index)

    def _resolve_marriage_proposal(self, accepted: bool) -> None:
        if self.player is None:
            self.marriage_popup_open = False
            self.marriage_candidate = ""
            return
        candidate = self.marriage_candidate or self.rng.choice(MARRIAGE_CANDIDATES)
        self.marriage_popup_open = False
        self.marriage_candidate = ""
        self.auto_popup_hold_until = 0
        if accepted:
            self.player.married = True
            self.player.spouse_name = candidate
            self.player.marriage_year = self.current_year
            self.player.marriage_month = self.current_month
            self._log(f"Vermaehlung: Du bist mit {candidate} vermählt.")
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Ehe mit {candidate} geschlossen."
            )
        else:
            self._log(f"Werbungsbrief von {candidate} abgelehnt.")

    def _normalize_child_name(self, name: str) -> str:
        clean = "".join(ch for ch in name.strip() if ch.isprintable())
        clean = clean[:MAX_CHILD_NAME_LEN].strip()
        return clean

    def _unique_child_name(self, base: str) -> str:
        if self.player is None:
            return base
        existing = {name.lower() for name in self.player.child_names}
        if base.lower() not in existing:
            return base
        idx = 2
        while f"{base} {idx}".lower() in existing:
            idx += 1
        return f"{base} {idx}"

    def _used_ship_names(self) -> set[str]:
        used: set[str] = set()
        if self.player is not None:
            for ship in self.player.ships:
                used.add(ship.display_name.lower())
        for npc in getattr(self, "npcs", []):
            npc_ship = getattr(npc, "ship", None)
            if npc_ship is not None:
                used.add(npc_ship.display_name.lower())
        return used

    def _auto_ship_name_pool(self, ship_type_name: str) -> Tuple[str, ...]:
        ship_name_lc = str(ship_type_name).lower()
        if "pirat" in ship_name_lc:
            return AUTO_SHIP_NAME_POOLS["pirat"]
        if "kogge" in ship_name_lc:
            return AUTO_SHIP_NAME_POOLS["kogge"]
        if "holk" in ship_name_lc:
            return AUTO_SHIP_NAME_POOLS["holk"]
        if "kraier" in ship_name_lc:
            return AUTO_SHIP_NAME_POOLS["kraier"]
        if "karavelle" in ship_name_lc:
            return AUTO_SHIP_NAME_POOLS["karavelle"]
        return AUTO_SHIP_NAME_POOLS["kriegsschiff"]

    def _next_auto_ship_name(self, ship_type_name: str) -> str:
        pool = self._auto_ship_name_pool(ship_type_name)
        if not pool:
            return str(ship_type_name)
        used = self._used_ship_names()
        available = [name for name in pool if name.lower() not in used]
        base = self.rng.choice(available if available else list(pool))
        if base.lower() not in used:
            return base
        idx = 2
        candidate = f"{base} {idx}"
        while candidate.lower() in used:
            idx += 1
            candidate = f"{base} {idx}"
        return candidate

    def _apply_auto_ship_name(self, ship: Ship) -> None:
        if ship.custom_name:
            return
        ship.custom_name = self._next_auto_ship_name(ship.name)

    def _next_auto_person_name(self) -> str:
        return f"{self.rng.choice(AUTO_CHILD_FIRST_NAMES)} {self.rng.choice(AUTO_CHILD_SURNAMES)}"

    def _next_auto_child_name(self) -> str:
        if self.player is None:
            return "Kind"
        existing = {name.lower() for name in self.player.child_names}
        for _ in range(32):
            candidate = self._normalize_child_name(self._next_auto_person_name())
            if len(candidate) >= 2 and candidate.lower() not in existing:
                return candidate
        return self._unique_child_name(self._normalize_child_name(self._next_auto_person_name()) or "Kind")

    def _current_max_children(self) -> int:
        return max(1, int(max_children_for_year(self.current_year)))

    def _child_survival_probability(self, city_name: str) -> float:
        city = self._city_economy(city_name)
        hospital_lvl = self._institution_level(city, "hospital")
        doctor_lvl = self._institution_level(city, "doctors")
        sanitation_lvl = self._institution_level(city, "sanitation")
        medical_quality = self._clamp(
            0.20
            + (hospital_lvl * 0.09)
            + (doctor_lvl * 0.13)
            + (sanitation_lvl * 0.06)
            + (float(city.hazard_mitigation) * 0.35)
            + (float(city.child_survival_rate) * 0.35),
            0.08,
            1.35,
        )
        mortality = self._clamp(
            child_mortality_for_year(self.current_year)
            * (1.30 - medical_quality)
            * (1.0 + float(city.disease_pressure) * 0.45),
            0.01,
            0.60,
        )
        return self._clamp(1.0 - mortality, 0.10, 0.995)

    def _age_children_and_resolve_mortality(self) -> None:
        if self.player is None or not self.player.child_names:
            return
        city_name = self.player.city if self.player.city in CITIES else CITIES[0]
        survival_probability = self._child_survival_probability(city_name)
        yearly_mortality = self._clamp(1.0 - survival_probability, 0.002, 0.30)
        deceased: List[str] = []

        for child_name in list(self.player.child_names):
            try:
                age = max(0, int(self.player.child_ages.get(child_name, 0))) + 1
            except (TypeError, ValueError):
                age = 1
            self.player.child_ages[child_name] = age
            if age <= CHILD_MORTALITY_VULNERABLE_AGE and self.rng.random() < yearly_mortality:
                deceased.append(child_name)

        if not deceased:
            self.player.children = len(self.player.child_names)
            return

        for child_name in deceased:
            if child_name in self.player.child_names:
                self.player.child_names.remove(child_name)
            self.player.child_ages.pop(child_name, None)
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Kind {child_name} verstarb an Krankheit."
            )
        self.player.children = len(self.player.child_names)
        if len(deceased) == 1:
            self._log(f"Trauerfall: Kind {deceased[0]} verstarb an Krankheit.")
        else:
            self._log(f"Trauerfall: {len(deceased)} Kinder verstarben an Krankheiten.")

    def _register_child(self, name: str) -> bool:
        if self.player is None:
            return False
        clean = self._normalize_child_name(name)
        if len(clean) < 2:
            return False
        if self.player.children >= self._current_max_children():
            self._log(
                f"Familienplanung: Im {self.current_century}. Jahrhundert sind maximal "
                f"{self._current_max_children()} Kinder vorgesehen."
            )
            return False
        final_name = self._unique_child_name(clean)
        survival_probability = self._child_survival_probability(self.player.city)
        self.player.chronicle.append(f"ANNO {self.current_year}: Geburt ({final_name}).")
        if self.rng.random() <= survival_probability:
            self.player.child_names.append(final_name)
            self.player.child_ages[final_name] = 0
            self.player.children = len(self.player.child_names)
            self._log(f"Familie waechst: {final_name} wurde geboren.")
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Kind geboren ({final_name})."
            )
        else:
            self._log(f"Schicksalsschlag: Neugeborenes {final_name} verstarb an Krankheit.")
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Neugeborenes {final_name} verstarb an Krankheit."
            )
        return True

    def _submit_child_name(self, auto: bool = False) -> None:
        if self.player is None:
            self.child_name_popup_open = False
            self.child_name_edit = ""
            return
        proposed = self.child_name_edit.strip()
        if auto or len(proposed) < 2:
            proposed = self._next_auto_child_name()
        if not self._register_child(proposed):
            if len(proposed.strip()) < 2:
                self._log("Bitte einen gueltigen Namen eingeben.")
            return
        self.child_name_popup_open = False
        self.child_name_edit = ""
        self.child_name_input_rect = None

    def _trigger_child_birth_event(self) -> None:
        if self.player is None or not self.player.married:
            return
        if self.player.children >= self._current_max_children():
            return
        if self.auto_mode:
            self._register_child(self._next_auto_child_name())
            return
        if self.child_name_popup_open:
            return
        self.child_name_popup_open = True
        self.child_name_edit = ""
        self._log("Ein Kind wurde geboren. Bitte den Namen im Popup vergeben.")

    def _conceive_heir(self) -> None:
        if self.player is None:
            return
        if not self.player.alive:
            self._log("Kein Nachkomme moeglich: Handelshaus ist erloschen.")
            return
        if not self.player.married:
            self._log("Nachkommen zeugen ist nur in einer Ehe moeglich.")
            return
        if self.player.children >= self._current_max_children():
            self._log(
                f"Familienplanung: Im {self.current_century}. Jahrhundert sind maximal "
                f"{self._current_max_children()} Kinder vorgesehen."
            )
            return
        if self.marriage_popup_open or self.child_name_popup_open:
            self._log("Nachkommen zeugen derzeit nicht verfuegbar (offenes Familienereignis).")
            return
        heir_name = self._next_auto_child_name()
        if self._register_child(heir_name):
            self._log(f"Nachkommen gezeugt: {heir_name}.")

    def _maybe_trigger_marriage_proposal(self) -> None:
        if self.player is None or not self.player.alive:
            return
        if self.player.married or self.player.title_index < 1:
            return
        if self.marriage_popup_open or self.child_name_popup_open:
            return
        month_index = self._month_index()
        if month_index - self._get_last_marriage_offer_month() < 12:
            return
        self._open_marriage_proposal()

    def _apply_firstborn_heir(self) -> bool:
        if self.player is None or not self.player.child_names:
            return False
        heir_name = self.player.child_names[0]
        heir_gender = "w" if heir_name.strip().lower() in FEMALE_NAME_HINTS else "m"
        self.player.name = heir_name
        self.player.gender = heir_gender
        self.player.age = 18
        self.player.married = False
        self.player.spouse_name = ""
        self.player.marriage_year = None
        self.player.marriage_month = None
        self.player.children = 0
        self.player.child_names = []
        self.player.child_ages = {}
        self.player.turns_in_debt_tower = 0
        self.player.alive = True
        self.marriage_popup_open = False
        self.marriage_candidate = ""
        self.child_name_popup_open = False
        self.child_name_edit = ""
        self.child_name_input_rect = None
        self.player.chronicle.append(
            f"ANNO {self.current_year}: Erstgeborenes Kind {heir_name} uebernimmt das Handelshaus."
        )
        self._log(f"Nachfolge gesichert: {heir_name} fuehrt das Handelshaus weiter.")
        return True

    def _handle_marriage_popup_click(self, pos: Tuple[int, int]) -> None:
        button = self._clicked_button(pos)
        if button == "marriage_accept":
            self._resolve_marriage_proposal(True)
        elif button == "marriage_decline":
            self._resolve_marriage_proposal(False)

    def _handle_child_name_popup_click(self, pos: Tuple[int, int]) -> None:
        if self.child_name_input_rect and self.child_name_input_rect.collidepoint(pos):
            return
        button = self._clicked_button(pos)
        if button == "child_name_submit":
            self._submit_child_name()
        elif button == "child_name_suggest":
            self.child_name_edit = self._next_auto_child_name()

    def _handle_info_click(self, pos: Tuple[int, int]) -> None:
        button = self._clicked_button(pos)
        if button == "info_close":
            self.info_open = False
            self.info_scroll = 0
            self.info_max_scroll = 0
        elif button == "info_up":
            self.info_scroll = max(0, self.info_scroll - 40)
        elif button == "info_down":
            self.info_scroll = min(self.info_max_scroll, self.info_scroll + 40)

    def _draw(self) -> None:
        self.button_states.clear()
        if self.scene == "menu":
            self._blit_background_cover("bg_setup")
            self._draw_menu()
        elif self.scene == "setup":
            self._blit_background("bg_setup")
            self._draw_setup()
        else:
            self._blit_background("bg_market")
            self._draw_game()
        if self.settings_open:
            self._draw_settings()

    def _draw_menu(self) -> None:
        self._draw_text("HANSE - pygame Edition", self.font_title, TEXT, (50, 35))
        self._draw_text("Grafische Version mit Save-Slots", self.font, TEXT_DIM, (54, 86))

        header = self._get_scaled("panel_stripe", (WIDTH - 120, 80))
        if header:
            self.screen.blit(header, (50, 10))

        slots_panel = pygame.Rect(50, 135, 890, 590)
        pygame.draw.rect(self.screen, BG_PANEL, slots_panel, border_radius=14)
        pygame.draw.rect(self.screen, (46, 66, 98), slots_panel, width=2, border_radius=14)
        self._draw_panel_header(slots_panel)
        self._draw_text("Speicherstaende", self.font_h1, TEXT, (70, 155))

        self.slot_rows = []
        y = 210
        for slot in range(1, SAVE_SLOT_COUNT + 1):
            row = pygame.Rect(72, y, 845, 68)
            selected = slot == self.selected_slot
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=10)
            border = ACCENT if selected else (54, 74, 108)
            pygame.draw.rect(self.screen, border, row, width=2, border_radius=10)
            summary = self._slot_summary(slot)
            self._draw_text(f"Slot {slot}", self.font, TEXT, (88, y + 10))
            self._draw_text(summary, self.font_small, TEXT_DIM, (220, y + 14))
            self.slot_rows.append((slot, row))
            y += 82

        self._draw_button("menu_new", pygame.Rect(980, 190, 290, 66), "Neues Spiel", True, accent=True)
        self._draw_button("menu_load", pygame.Rect(980, 274, 290, 66), "Slot laden", True)
        self._draw_button("menu_quit", pygame.Rect(980, 358, 290, 66), "Beenden", True)
        self._draw_button("menu_settings", pygame.Rect(980, 442, 290, 66), "Einstellungen", True)
        self._draw_text(
            "Hinweis: F5 Speichern | F9 Laden | F6 CSV-Export.",
            self.font_small,
            TEXT_DIM,
            (980, 530),
        )

        ship_icon = self._get_scaled("ship_kogge", (240, 240))
        if ship_icon:
            self.screen.blit(ship_icon, (990, 520))

    def _draw_setup(self) -> None:
        panel = pygame.Rect(180, 90, 960, 640)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=14)
        pygame.draw.rect(self.screen, (46, 66, 98), panel, width=2, border_radius=14)
        self._draw_panel_header(panel)
        self._draw_text("Neues Handelshaus", self.font_h1, TEXT, (220, 124))

        self._draw_text("Name (min. 3 Zeichen):", self.font, TEXT, (220, 196))
        input_box = pygame.Rect(220, 222, 420, 52)
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, input_box, width=2, border_radius=8)
        self._draw_text(self.new_name or "_", self.font, TEXT, (236, 236))

        self._draw_text("Geschlecht:", self.font, TEXT, (220, 302))
        self._draw_button(
            "setup_gender_m",
            pygame.Rect(220, 330, 140, 46),
            "Maennlich",
            True,
            accent=self.new_gender == "m",
        )
        self._draw_button(
            "setup_gender_w",
            pygame.Rect(380, 330, 140, 46),
            "Weiblich",
            True,
            accent=self.new_gender == "w",
        )

        self._draw_text("Startstadt:", self.font, TEXT, (700, 196))
        self.city_rows = []
        y = 218
        for idx, city_name in enumerate(CITIES):
            row = pygame.Rect(700, y, 360, 36)
            selected = idx == self.new_city
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (58, 82, 118), row, width=1, border_radius=8)
            self._draw_text(city_name, self.font_small, TEXT, (716, y + 8))
            self.city_rows.append((idx, row))
            y += 40

        self._draw_button("setup_back", pygame.Rect(220, 610, 180, 54), "Zurueck", True)
        self._draw_button("setup_start", pygame.Rect(880, 610, 180, 54), "Start", True, accent=True)

        self._draw_text("Enter: Starten | Backspace: Zeichen loeschen", self.font_small, TEXT_DIM, (220, 560))

    def _draw_settings(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 200))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(360, 190, 600, 380)
        self.settings_panel_rect = panel
        self._draw_panel_base(panel, use_paper=True)
        self._draw_text("Einstellungen", self.font_h1, TEXT, (panel.x + 24, panel.y + 20))
        self._draw_text("Sprache", self.font, ACCENT_2, (panel.x + 24, panel.y + 78))
        self._draw_text(
            "UI-Sprache sofort umschalten.",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 110),
        )
        self._draw_button(
            "settings_lang_de",
            pygame.Rect(panel.x + 24, panel.y + 148, 210, 48),
            "Deutsch",
            True,
            accent=self.ui_language == "de",
        )
        self._draw_button(
            "settings_lang_en",
            pygame.Rect(panel.x + 264, panel.y + 148, 210, 48),
            "Englisch",
            True,
            accent=self.ui_language == "en",
        )
        self._draw_text("Musik", self.font, ACCENT_2, (panel.x + 24, panel.y + 220))
        self._draw_text(
            "Hintergrundmusik im Spiel umschalten.",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 252),
        )
        music_ready = self._can_play_music()
        self._draw_button(
            "settings_music_toggle",
            pygame.Rect(panel.x + 24, panel.y + 286, 210, 48),
            "An" if self.music_enabled else "Aus",
            music_ready,
            accent=self.music_enabled and music_ready,
        )
        self._draw_text("Lautstaerke", self.font_small, TEXT_DIM, (panel.x + 264, panel.y + 264))
        self._draw_button(
            "settings_music_minus",
            pygame.Rect(panel.x + 264, panel.y + 286, 56, 48),
            "-",
            music_ready and self.music_volume > 0.0,
        )
        self._draw_button(
            "settings_music_plus",
            pygame.Rect(panel.x + 446, panel.y + 286, 56, 48),
            "+",
            music_ready and self.music_volume < 1.0,
        )
        volume_label = "Nicht verfuegbar" if not music_ready else f"{int(round(self.music_volume * 100))}%"
        self._draw_text(volume_label, self.font, TEXT, (panel.x + 344, panel.y + 296))
        self._draw_button(
            "settings_close",
            pygame.Rect(panel.x + panel.width - 154, panel.y + panel.height - 58, 130, 40),
            "Schliessen",
            True,
        )

    def _handle_settings_click(self, pos: Tuple[int, int]) -> None:
        button = self._clicked_button(pos)
        if button == "settings_lang_de":
            self._set_ui_language("de")
            return
        if button == "settings_lang_en":
            self._set_ui_language("en")
            return
        if button == "settings_music_toggle":
            self._set_music_enabled(not self.music_enabled)
            return
        if button == "settings_music_minus":
            self._adjust_music_volume(-MUSIC_VOLUME_STEP)
            return
        if button == "settings_music_plus":
            self._adjust_music_volume(MUSIC_VOLUME_STEP)
            return
        if button == "settings_close":
            self.settings_open = False
            return
        if self.settings_panel_rect and not self.settings_panel_rect.collidepoint(pos):
            self.settings_open = False

    def _draw_about_panel(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 200))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(340, 230, 640, 320)
        self.about_panel_rect = panel
        self._draw_panel_base(panel, use_paper=True)
        self._draw_text("Spielinformation", self.font_h1, TEXT, (panel.x + 24, panel.y + 20))

        label_x = panel.x + 24
        value_x = panel.x + 190
        y = panel.y + 88
        gap = 44

        self._draw_text("Spielname", self.font, ACCENT_2, (label_x, y))
        self._draw_text("Hanse - pygame Edition", self.font, TEXT, (value_x, y))
        y += gap
        self._draw_text("Webseite", self.font, ACCENT_2, (label_x, y))
        self._draw_text(
            "https://github.com/kruemmel-python/Cloud-Hanse-Drive-Sync",
            self.font_small,
            TEXT,
            (label_x, y + 26),
        )
        y += 70
        self._draw_text("Entwickler", self.font, ACCENT_2, (label_x, y))
        self._draw_text("Ralf Kruemmel", self.font, TEXT, (value_x, y))

        self._draw_button(
            "about_close",
            pygame.Rect(panel.x + panel.width - 154, panel.y + panel.height - 58, 130, 40),
            "Schliessen",
            True,
        )

    def _handle_about_click(self, pos: Tuple[int, int]) -> None:
        button = self._clicked_button(pos)
        if button == "about_close":
            self.about_open = False
            self.about_panel_rect = None
            return
        if self.about_panel_rect and not self.about_panel_rect.collidepoint(pos):
            self.about_open = False
            self.about_panel_rect = None

    def _draw_game(self) -> None:
        if self.player is None:
            self._draw_text("Kein Spiel aktiv.", self.font_h1, TEXT, (50, 50))
            self._draw_button("game_menu", pygame.Rect(50, 110, 180, 48), "Zum Menue", True)
            return

        player = self.player
        self._sync_city_with_selected_ship()
        active_city = player.city
        prices = self._market_prices(active_city)
        storage = self._storage_for_city(active_city)
        ship = self._selected_ship()

        top = pygame.Rect(20, 16, WIDTH - 40, 130)
        sea_key = "bg_sea_wild" if self.current_sea_state in {"tobende See", "stuermische See"} else "bg_sea"
        sea_img = self._get_scaled(sea_key, (top.width, top.height))
        if sea_img:
            self.screen.blit(sea_img, (top.x, top.y))
            overlay = pygame.Surface((top.width, top.height), pygame.SRCALPHA)
            overlay.fill((10, 16, 28, 140))
            self.screen.blit(overlay, (top.x, top.y))
        else:
            pygame.draw.rect(self.screen, BG_PANEL, top, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), top, width=2, border_radius=12)

        self._draw_text(self._date_label(), self.font_h1, TEXT, (38, 30))
        self._draw_text(self.current_sea_state, self.font, ACCENT_2, (40, 76))
        self._draw_text(f"{self.current_century}. Jahrhundert", self.font_small, TEXT_DIM, (40, 108))
        self._draw_text(f"{player.name} ({self._title_for(player)})", self.font, TEXT, (310, 34))
        self._draw_text(f"Stadt: {active_city}", self.font, TEXT_DIM, (310, 70))
        self._draw_text(f"Mark: {player.money}", self.font, GOOD, (540, 34))
        self._draw_text(f"Schulden: {player.debt}", self.font, BAD if player.debt > 15000 else TEXT_DIM, (540, 70))
        if ship:
            ship_loc = f"{ship.city}" if not ship.is_at_sea else f"auf See -> {ship.destination}"
            self._draw_text(f"Aktiv: {ship.display_name}", self.font, TEXT, (760, 34))
            self._draw_text(
                f"Ort: {ship_loc} | Rumpf {ship.hull}% / Takelage {ship.rigging}%",
                self.font_small,
                TEXT_DIM,
                (760, 66),
            )
            eta_text = ""
            if ship.is_at_sea:
                eta = ship.travel_turns_left
                eta_text = f" | Reisezeit {eta} Monat(e)" if eta > 0 else " | Reisezeit ?"
            cannon_limit = self._max_cannons(ship)
            self._draw_text(
                f"Ladung {ship.total_cargo}/{ship.cargo_capacity} | Kanonen {ship.cannons}/{cannon_limit}{eta_text}",
                self.font_small,
                TEXT_DIM,
                (760, 88),
            )
            if ship.last_report:
                status = self._shorten_text(f"Status: {ship.last_report}", 58)
                self._draw_text(status, self.font_small, ACCENT_2, (760, 110))
        self._draw_text(f"Flotte: {len(player.ships)} Schiffe", self.font_small, TEXT_DIM, (540, 102))
        net = self._net_worth(player, prices)
        self._draw_text(f"Gesamtwert {net}", self.font, ACCENT_2, (1070, 34))
        self._draw_text(f"Auto: {'EIN' if self.auto_mode else 'AUS'}", self.font_small, GOOD if self.auto_mode else TEXT_DIM, (1070, 102))
        self._draw_text(
            f"Atheria W:{self.economy_state.global_growth:.2f} P:{self.economy_state.global_price_level:.2f} "
            f"K:{self.economy_state.resource_scarcity:.2f}",
            self.font_small,
            ACCENT_2,
            (310, 102),
        )
        self._draw_text(
            f"Welt: Betriebe {self.last_world_tick.get('producing_buildings', 0)} | "
            f"NPC-Deals {self.last_world_tick.get('npc_trades', 0)}/{len(self.npcs)} | "
            f"Bankrott {self.last_world_tick.get('cities_bankrupt', 0)} | "
            f"Steuern {self._format_compact_number(self.last_world_tick.get('total_tax', 0))} | "
            f"Migration {self._format_compact_number(self.last_world_tick.get('net_migration', 0))} | "
            f"Einfluss {self._player_city_influence(player.city):.1f}",
            self.font_small,
            TEXT_DIM,
            (310, 122),
        )
        if player.turns_in_debt_tower > 0:
            self._draw_text(f"Schuldturm: {player.turns_in_debt_tower} Monat(e)", self.font, BAD, (1060, 72))

        goods_panel = pygame.Rect(20, 162, 620, 420)
        fleet_panel = self._fleet_panel_rect()
        act_panel = pygame.Rect(955, 162, 345, 420)
        log_panel = pygame.Rect(20, 596, WIDTH - 40, 205)

        for panel in (goods_panel, fleet_panel, act_panel, log_panel):
            self._draw_panel_base(panel, use_paper=True)

        self._draw_text("Markt", self.font_h1, TEXT, (38, 178))
        self._draw_text("Flotte", self.font_h1, TEXT, (675, 178))
        self._draw_text("Aktionen", self.font_h1, TEXT, (975, 178))
        self._draw_text("Chronik / Meldungen", self.font_h1, TEXT, (38, 610))
        market_can_scroll = self._max_market_goods_offset() > 0
        self._draw_button("game_market_up", pygame.Rect(goods_panel.right - 78, 176, 34, 28), "^", market_can_scroll)
        self._draw_button("game_market_down", pygame.Rect(goods_panel.right - 40, 176, 34, 28), "v", market_can_scroll)
        fleet_can_scroll = self._fleet_max_scroll() > 0
        self._draw_button("game_fleet_up", pygame.Rect(fleet_panel.right - 78, 176, 34, 28), "^", fleet_can_scroll)
        self._draw_button("game_fleet_down", pygame.Rect(fleet_panel.right - 40, 176, 34, 28), "v", fleet_can_scroll)
        can_conceive_heir = (
            player.alive
            and player.married
            and not self.marriage_popup_open
            and not self.child_name_popup_open
        )
        self._draw_button(
            "game_heir",
            pygame.Rect(log_panel.right - 650, log_panel.y + 6, 170, 36),
            "Nachkommen zeugen",
            can_conceive_heir,
        )
        self._draw_button("game_export", pygame.Rect(log_panel.right - 472, log_panel.y + 6, 102, 36), "CSV Export", True)
        self._draw_button("game_info", pygame.Rect(log_panel.right - 362, log_panel.y + 6, 92, 36), "Info", True)
        self._draw_button("game_settings", pygame.Rect(log_panel.right - 260, log_panel.y + 6, 102, 36), "Einstellungen", True)
        self._draw_button("game_missions", pygame.Rect(log_panel.right - 150, log_panel.y + 6, 130, 36), "Missionen", True)
        policy = self._player_auto_policy()
        policy_box = pygame.Rect(log_panel.x + 18, log_panel.y + 44, log_panel.width - 36, 70)
        pygame.draw.rect(self.screen, BG_PANEL_ALT, policy_box, border_radius=8)
        pygame.draw.rect(self.screen, (60, 85, 122), policy_box, width=1, border_radius=8)
        self._draw_text("Auto-Policy", self.font_small, ACCENT_2, (policy_box.x + 8, policy_box.y + 6))
        self._draw_button("policy_risk_minus", pygame.Rect(policy_box.x + 120, policy_box.y + 4, 28, 26), "-", True)
        self._draw_button("policy_risk_plus", pygame.Rect(policy_box.x + 152, policy_box.y + 4, 28, 26), "+", True)
        self._draw_text(f"Risiko {int(policy.get('risk', 50))}", self.font_small, TEXT_DIM, (policy_box.x + 186, policy_box.y + 9))
        self._draw_button("policy_reserve_minus", pygame.Rect(policy_box.x + 285, policy_box.y + 4, 28, 26), "-", True)
        self._draw_button("policy_reserve_plus", pygame.Rect(policy_box.x + 317, policy_box.y + 4, 28, 26), "+", True)
        self._draw_text(
            f"Reserve {int(policy.get('reserve_mark', 1400))}",
            self.font_small,
            TEXT_DIM,
            (policy_box.x + 351, policy_box.y + 9),
        )
        invest_label = self._auto_invest_mode_label(str(policy.get("invest_mode", "balanced")))
        self._draw_button(
            "policy_invest_cycle",
            pygame.Rect(policy_box.x + 500, policy_box.y + 4, 180, 26),
            f"Invest: {invest_label}",
            True,
        )
        focus_map = policy.get("focus_cities", {})
        fx = policy_box.x + 8
        fy = policy_box.y + 36
        for city_name in CITIES:
            self._draw_button(
                f"policy_focus_{city_name}",
                pygame.Rect(fx, fy, 58, 26),
                city_name[:3],
                True,
                accent=bool(focus_map.get(city_name, True)),
            )
            fx += 64

        target_prices = None
        if self.preview_destination and self.preview_destination != active_city:
            target_prices = self._market_prices(self.preview_destination)
        self._draw_text(f"Ort: {active_city}", self.font_small, TEXT_DIM, (38, 206))
        if self.preview_destination and self.preview_destination != active_city:
            self._draw_text(f"Ziel: {self.preview_destination}", self.font_small, ACCENT_2, (190, 206))

        self.goods_rows = []
        goods_list = self._active_good_names()
        if self.selected_good >= len(goods_list):
            self.selected_good = 0
        self.market_goods_offset = max(0, min(self.market_goods_offset, self._max_market_goods_offset()))
        if self.selected_good < self.market_goods_offset:
            self.market_goods_offset = self.selected_good
        if self.selected_good >= self.market_goods_offset + self._market_visible_count():
            self.market_goods_offset = self.selected_good - self._market_visible_count() + 1
        visible_goods = goods_list[
            self.market_goods_offset : self.market_goods_offset + self._market_visible_count()
        ]
        mouse_pos = self._virtual_mouse_pos()
        y = 228
        for local_idx, good_name in enumerate(visible_goods):
            idx = self.market_goods_offset + local_idx
            row = pygame.Rect(36, y, 590, 44)
            selected = idx == self.selected_good
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            if row.collidepoint(mouse_pos):
                color = ROW_HOVER if not selected else ROW_SELECTED
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            qty = storage.get(good_name, 0)
            self._draw_text(good_name, self.font_small, TEXT, (48, y + 12))
            self._draw_text(f"Preis {prices[good_name]:>4}", self.font_small, TEXT_DIM, (210, y + 12))
            market_qty = self._city_inventory_qty(active_city, good_name)
            if target_prices:
                self._draw_text(f"Ziel {target_prices[good_name]:>4}", self.font_small, TEXT_DIM, (330, y + 12))
                self._draw_text(
                    f"Lager {qty:>3} | Markt {market_qty:>3}",
                    self.font_small,
                    TEXT_DIM,
                    (430, y + 12),
                )
            else:
                self._draw_text(
                    f"Lager {qty:>3} | Markt {market_qty:>3}",
                    self.font_small,
                    TEXT_DIM,
                    (420, y + 12),
                )
            self.goods_rows.append((idx, row))
            y += 50
        if len(goods_list) > self._market_visible_count():
            start = self.market_goods_offset + 1
            end = min(len(goods_list), self.market_goods_offset + self._market_visible_count())
            self._draw_text(
                f"Waren {start}-{end}/{len(goods_list)} (Mausrad / Buttons)",
                self.font_small,
                TEXT_DIM,
                (38, goods_panel.bottom - 20),
            )

        self.fleet_rows = []
        row_height = 86
        visible_top = 228
        visible_bottom = fleet_panel.y + fleet_panel.height - 18
        total_height = len(player.ships) * row_height
        max_scroll = max(0, total_height - (fleet_panel.height - 56))
        self.fleet_scroll = max(0, min(self.fleet_scroll, max_scroll))
        y = visible_top - self.fleet_scroll
        for idx, fleet_ship in enumerate(player.ships):
            row = pygame.Rect(fleet_panel.x + 12, y, fleet_panel.width - 24, 78)
            if row.bottom < visible_top or row.top > visible_bottom:
                y += row_height
                continue
            selected = idx == self.selected_fleet_ship
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            if row.collidepoint(mouse_pos):
                color = ROW_HOVER if not selected else ROW_SELECTED
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            icon = self._get_scaled(self._ship_image_key(fleet_ship), (44, 44))
            text_x = row.x + 10
            if icon:
                self.screen.blit(icon, (row.x + 6, row.y + 12))
                text_x = row.x + 58
            label = fleet_ship.display_name
            location = fleet_ship.city if not fleet_ship.is_at_sea else f"See → {fleet_ship.destination}"
            self._draw_text(label, self.font_small, TEXT, (text_x, row.y + 8))
            self._draw_text(
                f"{location} | Ladung {fleet_ship.total_cargo}/{fleet_ship.cargo_capacity}",
                self.font_small,
                TEXT_DIM,
                (text_x, row.y + 34),
            )
            self._draw_text(
                f"R:{fleet_ship.hull}% T:{fleet_ship.rigging}% K:{fleet_ship.cannons}",
                self.font_small,
                TEXT_DIM,
                (text_x, row.y + 58),
            )
            self.fleet_rows.append((idx, row))
            y += row_height

        locked = (not player.alive) or (player.turns_in_debt_tower > 0)
        self._draw_button("game_buy", pygame.Rect(975, 228, 152, 46), "Kaufen", not locked, accent=True)
        self._draw_button("game_sell", pygame.Rect(1140, 228, 142, 46), "Verkaufen", not locked)
        self._draw_button("game_qty_minus", pygame.Rect(975, 286, 74, 42), "- Menge", not locked)
        self._draw_button("game_qty_plus", pygame.Rect(1056, 286, 71, 42), "+ Menge", not locked)
        self._draw_text(f"Menge: {self.trade_qty}", self.font_small, TEXT_DIM, (1140, 298))
        self._draw_button("game_cargo", pygame.Rect(975, 340, 152, 44), "Schiffsladung", not locked)
        self._draw_button("game_city_prices", pygame.Rect(1140, 340, 142, 44), "Stadtpreise", True)
        self._draw_button("game_ship_editor", pygame.Rect(975, 394, 152, 42), "Schiff-Editor", not locked)
        self._draw_button("game_shipyard", pygame.Rect(1140, 394, 142, 42), "Schiffbau", not locked)
        self._draw_button("game_repair_hull", pygame.Rect(975, 446, 152, 42), "Rumpf +10%", not locked)
        self._draw_button("game_repair_rig", pygame.Rect(1140, 446, 142, 42), "Takelage +10%", not locked)
        self._draw_button("game_next_year", pygame.Rect(975, 498, 214, 44), "Naechster Monat", player.alive, accent=True)
        self._draw_button("game_auto", pygame.Rect(1196, 498, 86, 44), "Auto", player.alive, accent=self.auto_mode)
        self._draw_button("game_save", pygame.Rect(975, 550, 102, 42), "Speichern", player.alive)
        self._draw_button("game_load", pygame.Rect(1088, 550, 90, 42), "Laden", True)
        self._draw_button("game_menu", pygame.Rect(1188, 550, 94, 42), "Menue", True)

        self.slot_rows = []
        if self.save_menu_open:
            y = 600
            label = "Slots (Speichern)" if self.save_menu_mode == "save" else "Slots (Laden)"
            self._draw_text(label, self.font_small, ACCENT_2, (975, y - 22))
            self._draw_button("save_menu_info", pygame.Rect(1186, y - 28, 96, 28), "Info", True)
            for slot in range(1, SAVE_SLOT_COUNT + 1):
                row = pygame.Rect(975, y, 307, 32)
                selected = slot == self.selected_slot
                pygame.draw.rect(self.screen, ROW_SELECTED if selected else BG_PANEL_ALT, row, border_radius=6)
                pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
                summary = self._slot_summary(slot)
                short = summary if len(summary) <= 35 else summary[:32] + "..."
                self._draw_text(f"S{slot}: {short}", self.font_small, TEXT_DIM, (985, y + 8))
                self.slot_rows.append((slot, row))
                y += 36

        max_lines = 4
        lines = self.messages[-max_lines:]
        y = 714
        for line in lines:
            color = BAD if "Fehler" in line else TEXT_DIM
            self._draw_text(line, self.font_small, color, (38, y))
            y += 24

        if not player.alive:
            self._draw_text("Das Handelshaus ist erloschen.", self.font_h1, BAD, (430, 324))
            self._draw_text("Du kannst laden oder ins Menue wechseln.", self.font, TEXT_DIM, (445, 360))

        if self.shipyard_open:
            self._draw_shipyard()
        if self.ship_cargo_open:
            self._draw_ship_cargo()
        if self.ship_editor_open:
            self._draw_ship_editor()
        if self.city_market_open:
            self._draw_city_market()
        if self.missions_open:
            self._draw_missions()
        if self.info_open:
            self._draw_info()
        if self.about_open:
            self._draw_about_panel()
        if self.marriage_popup_open:
            self._draw_marriage_popup()
        if self.child_name_popup_open:
            self._draw_child_name_popup()
        if self.cheat_open:
            self._draw_cheat_prompt()

    def _draw_shipyard(self) -> None:
        if self.player is None:
            return
        player = self.player
        shipyard = self._active_shipyard()
        if self.selected_ship_type >= len(shipyard):
            self.selected_ship_type = 0
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 8, 14, 210))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(240, 170, 840, 440)
        stripe = self._get_scaled("panel_stripe", (panel.width, panel.height))
        if stripe:
            self.screen.blit(stripe, (panel.x, panel.y))
            overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            overlay.fill((14, 18, 26, 170))
            self.screen.blit(overlay, (panel.x, panel.y))
        else:
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)
        self._draw_panel_header(panel)

        self._draw_text("Schiffbau", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            f"Neues Schiff wird in {player.city} stationiert.",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 56),
        )

        self.ship_rows = []
        mouse_pos = self._virtual_mouse_pos()
        self.shipyard_offset = max(0, min(self.shipyard_offset, self._max_shipyard_offset()))
        if self.selected_ship_type < self.shipyard_offset:
            self.shipyard_offset = self.selected_ship_type
        if self.selected_ship_type >= self.shipyard_offset + self._shipyard_visible_count():
            self.shipyard_offset = self.selected_ship_type - self._shipyard_visible_count() + 1
        visible_ships = shipyard[
            self.shipyard_offset : self.shipyard_offset + self._shipyard_visible_count()
        ]
        y = panel.y + 96
        for local_idx, (name, cap, value, cost) in enumerate(visible_ships):
            idx = self.shipyard_offset + local_idx
            row = pygame.Rect(panel.x + 24, y, panel.width - 48, 54)
            selected = idx == self.selected_ship_type
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            if row.collidepoint(mouse_pos):
                color = ROW_HOVER if not selected else ROW_SELECTED
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            key = "ship_kogge"
            if "holk" in name.lower():
                key = "ship_holk"
            elif "kraier" in name.lower():
                key = "ship_kraier"
            icon = self._get_scaled(key, (44, 44))
            text_x = row.x + 12
            if icon:
                self.screen.blit(icon, (row.x + 6, row.y + 4))
                text_x = row.x + 58
            self._draw_text(name, self.font_small, TEXT, (text_x, row.y + 16))
            self._draw_text(f"Ladung {cap}", self.font_small, TEXT_DIM, (row.x + 300, row.y + 16))
            self._draw_text(f"Wert {value}", self.font_small, TEXT_DIM, (row.x + 420, row.y + 16))
            self._draw_text(f"Preis {cost}", self.font_small, ACCENT_2, (row.x + 540, row.y + 16))
            self.ship_rows.append((idx, row))
            y += 64
        if len(shipyard) > self._shipyard_visible_count():
            start = self.shipyard_offset + 1
            end = min(len(shipyard), self.shipyard_offset + self._shipyard_visible_count())
            self._draw_text(
                f"Modelle {start}-{end}/{len(shipyard)} (Mausrad)",
                self.font_small,
                TEXT_DIM,
                (panel.x + 24, panel.y + 292),
            )

        if shipyard:
            _name, _cap, _value, cost = shipyard[self.selected_ship_type]
            self._draw_text(
                f"Preis: {cost} Mark",
                self.font,
                ACCENT_2,
                (panel.x + 24, panel.y + 320),
            )

        selected_ship = self._selected_ship()
        sell_price = self._ship_sale_price(selected_ship) if selected_ship is not None else 0
        can_sell = bool(
            player.alive
            and player.turns_in_debt_tower == 0
            and selected_ship is not None
            and len(player.ships) > 1
            and not selected_ship.is_at_sea
            and selected_ship.city == player.city
            and selected_ship.total_cargo == 0
        )
        if selected_ship is not None:
            self._draw_text(
                f"Aktiv: {selected_ship.display_name} | Verkauf: {sell_price} Mark",
                self.font_small,
                TEXT_DIM,
                (panel.x + 24, panel.y + 350),
            )

        can_buy = player.alive and player.turns_in_debt_tower == 0
        self._draw_button(
            "shipyard_buy",
            pygame.Rect(panel.x + panel.width - 392, panel.y + panel.height - 62, 120, 44),
            "Kaufen",
            can_buy,
            accent=True,
        )
        self._draw_button(
            "shipyard_sell",
            pygame.Rect(panel.x + panel.width - 262, panel.y + panel.height - 62, 120, 44),
            "Verkaufen",
            can_sell,
        )
        self._draw_button(
            "shipyard_close",
            pygame.Rect(panel.x + panel.width - 132, panel.y + panel.height - 62, 110, 44),
            "Schliessen",
            True,
        )

    def _draw_ship_cargo(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None:
            return
        self.dest_list_rect = None
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 10, 18, 210))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(120, 110, 1080, 600)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)
        paper = self._get_scaled("paper_transfer", (panel.width, panel.height))
        if paper:
            self.screen.blit(paper, (panel.x, panel.y))
            overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            overlay.fill((15, 18, 24, 110))
            self.screen.blit(overlay, (panel.x, panel.y))
        self._draw_panel_header(panel)

        can_transfer = (not ship.is_at_sea) and (ship.city == self.player.city)
        location = ship.city if not ship.is_at_sea else f"auf See → {ship.destination}"

        self._draw_text("Schiffsladung", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            f"{ship.display_name} ({ship.name}) | Ort: {location}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 56),
        )
        self._draw_text(
            f"Ladung {ship.total_cargo}/{ship.cargo_capacity} | Kanonen {ship.cannons}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 78),
        )
        ship_icon = self._get_scaled(self._ship_image_key(ship), (70, 70))
        if ship_icon:
            self.screen.blit(ship_icon, (panel.x + panel.width - 110, panel.y + 24))

        table_x = panel.x + 24
        table_w = panel.width - 320
        dest_x = panel.x + panel.width - 260
        self._draw_text(f"Lager ({self.player.city})", self.font_small, TEXT, (table_x, panel.y + 110))
        self._draw_text("Schiff", self.font_small, TEXT, (table_x + table_w - 120, panel.y + 110))
        self._draw_text("Reiseziele", self.font_small, TEXT, (dest_x, panel.y + 110))

        storage = self._storage_for_city(self.player.city)
        goods_names = self._active_good_names()
        self.transfer_goods_offset = max(0, min(self.transfer_goods_offset, self._max_transfer_goods_offset()))
        visible_goods = goods_names[
            self.transfer_goods_offset : self.transfer_goods_offset + self._transfer_visible_count()
        ]
        self.transfer_sliders = []
        y = panel.y + 140
        for good_name in visible_goods:
            row = pygame.Rect(table_x, y, table_w, 40)
            pygame.draw.rect(self.screen, BG_PANEL_ALT, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            storage_qty = storage.get(good_name, 0)
            ship_qty = ship.cargo.get(good_name, 0)
            self._draw_text(good_name, self.font_small, TEXT, (row.x + 8, row.y + 10))
            self._draw_text(f"{storage_qty:>4}", self.font_small, TEXT_DIM, (row.x + 140, row.y + 10))
            self._draw_text(f"{ship_qty:>4}", self.font_small, TEXT_DIM, (row.x + row.width - 60, row.y + 10))

            slider_rect = pygame.Rect(row.x + 200, row.y + 12, 220, 14)
            max_unload = ship_qty
            max_load = min(storage_qty, ship.cargo_space_left)
            if can_transfer:
                pygame.draw.rect(self.screen, (70, 94, 130), slider_rect, border_radius=6)
                center_x = slider_rect.centerx
                pygame.draw.line(self.screen, TEXT_DIM, (center_x, slider_rect.y), (center_x, slider_rect.y + slider_rect.height))
                value = 0
                if self.transfer_drag_good == good_name:
                    value = self.transfer_drag_value
                if value >= 0:
                    ratio = 0 if max_load == 0 else min(1.0, value / max_load)
                    knob_x = int(center_x + ratio * (slider_rect.width / 2))
                else:
                    ratio = 0 if max_unload == 0 else min(1.0, abs(value) / max_unload)
                    knob_x = int(center_x - ratio * (slider_rect.width / 2))
                knob = pygame.Rect(0, 0, 10, 20)
                knob.center = (knob_x, slider_rect.centery)
                pygame.draw.rect(self.screen, ACCENT_2, knob, border_radius=4)
                if value != 0:
                    self._draw_text(f"{value:+d}", self.font_small, ACCENT_2, (slider_rect.right + 10, row.y + 8))
                self.transfer_sliders.append((good_name, slider_rect, max_unload, max_load))
            else:
                pygame.draw.rect(self.screen, (45, 49, 59), slider_rect, border_radius=6)

            y += 48
        if len(goods_names) > self._transfer_visible_count():
            start = self.transfer_goods_offset + 1
            end = min(len(goods_names), self.transfer_goods_offset + self._transfer_visible_count())
            self._draw_text(
                f"Waren {start}-{end}/{len(goods_names)} (Mausrad)",
                self.font_small,
                TEXT_DIM,
                (table_x, panel.y + panel.height - 64),
            )

        self.dest_rows = []
        destinations = self._available_trade_destinations(ship.city)
        if destinations and self.selected_dest >= len(destinations):
            self.selected_dest = 0
        max_dest_offset = self._max_destination_offset(ship.city)
        self.dest_scroll = max(0, min(self.dest_scroll, max_dest_offset))
        if self.selected_dest < self.dest_scroll:
            self.dest_scroll = self.selected_dest
        if self.selected_dest >= self.dest_scroll + self._ship_destination_visible_count():
            self.dest_scroll = self.selected_dest - self._ship_destination_visible_count() + 1
        visible_destinations = destinations[
            self.dest_scroll : self.dest_scroll + self._ship_destination_visible_count()
        ]
        y = panel.y + 140
        self.dest_list_rect = pygame.Rect(dest_x, y, 228, max(34, len(visible_destinations) * 40))
        for local_idx, city_name in enumerate(visible_destinations):
            idx = self.dest_scroll + local_idx
            row = pygame.Rect(dest_x, y, 228, 34)
            selected = idx == self.selected_dest
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            label = f"{city_name} *" if self._is_remote_region(city_name) else city_name
            self._draw_text(label, self.font_small, TEXT, (row.x + 8, row.y + 8))
            self.dest_rows.append((idx, row))
            y += 40
        if len(destinations) > self._ship_destination_visible_count():
            can_scroll_up = self.dest_scroll > 0
            can_scroll_down = self.dest_scroll < max_dest_offset
            self._draw_button("cargo_dest_up", pygame.Rect(dest_x + 192, panel.y + 108, 36, 28), "^", can_scroll_up)
            self._draw_button(
                "cargo_dest_down",
                pygame.Rect(dest_x + 192, panel.y + 404, 36, 28),
                "v",
                can_scroll_down,
            )
            self._draw_text(
                f"Ziele {self.dest_scroll + 1}-{min(len(destinations), self.dest_scroll + self._ship_destination_visible_count())}/{len(destinations)}",
                self.font_small,
                TEXT_DIM,
                (dest_x, panel.y + 440),
            )
        else:
            self.dest_list_rect = pygame.Rect(dest_x, panel.y + 140, 228, 34)

        travel_cost = None
        if destinations:
            target = destinations[self.selected_dest]
            travel_cost = self._travel_cost_for_route(ship.city, target)
        if travel_cost is not None:
            self._draw_text(
                f"Reisekosten: {travel_cost} Mark",
                self.font_small,
                TEXT_DIM,
                (dest_x, panel.y + panel.height - 130),
            )

        travel_enabled = can_transfer and travel_cost is not None and self.player.money >= (travel_cost or 0)
        self._draw_button(
            "cargo_travel",
            pygame.Rect(dest_x, panel.y + panel.height - 98, 228, 40),
            "Reisen",
            travel_enabled,
            accent=True,
        )
        self._draw_button(
            "cargo_close",
            pygame.Rect(dest_x, panel.y + panel.height - 52, 228, 40),
            "Schliessen",
            True,
        )

        if not can_transfer:
            self._draw_text(
                "Schiff muss im aktuellen Hafen liegen.",
                self.font_small,
                BAD,
                (panel.x + 24, panel.y + panel.height - 42),
            )

    def _draw_ship_editor(self) -> None:
        if self.player is None:
            return
        ship = self._editor_ship()
        if ship is None:
            self.ship_editor_open = False
            self.ship_editor_ship = None
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 180))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(170, 70, 980, 660)
        stripe = self._get_scaled("panel_stripe", (panel.width, panel.height))
        if stripe:
            self.screen.blit(stripe, (panel.x, panel.y))
            overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            overlay.fill((14, 18, 26, 170))
            self.screen.blit(overlay, (panel.x, panel.y))
        else:
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)
        self._draw_panel_header(panel)

        self._draw_text("Schiff-Editor", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            f"{ship.display_name} ({ship.name}) | Ort: {ship.city}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 72),
        )
        self._draw_text(
            f"Rumpf {ship.hull}% / Takelage {ship.rigging}% | Kanonen {ship.cannons}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 98),
        )
        selected_weapon_century = self._normalize_selected_weapon_century()
        weapon = self._selected_weapon_profile()
        max_cannons = self._max_cannons(ship)

        self._draw_text("Name:", self.font_small, TEXT, (panel.x + 24, panel.y + 124))
        input_box = pygame.Rect(panel.x + 24, panel.y + 148, panel.width - 48, 44)
        self.ship_name_input_rect = input_box
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(
            self.screen,
            ACCENT if self.ship_name_active else (60, 85, 122),
            input_box,
            width=2,
            border_radius=8,
        )
        display_name = self.ship_name_edit if self.ship_name_active else (ship.custom_name or ship.display_name)
        self._draw_text(display_name or "_", self.font, TEXT, (input_box.x + 10, input_box.y + 10))

        self._draw_text("Kanonenstufe:", self.font_small, TEXT, (panel.x + 24, panel.y + 206))
        selector_left = pygame.Rect(panel.x + 24, panel.y + 230, 34, 28)
        selector_right = pygame.Rect(panel.x + panel.width - 58, panel.y + 230, 34, 28)
        self._draw_button("editor_weapon_prev", selector_left, "<", selected_weapon_century > 14)
        self._draw_button("editor_weapon_next", selector_right, ">", selected_weapon_century < self.current_century)
        self._draw_text(
            f"C{selected_weapon_century}: {weapon.get('name', 'Standard')}",
            self.font,
            ACCENT_2,
            (panel.x + 72, panel.y + 232),
        )
        self._draw_text(
            (
                f"Limit {max_cannons} | Power x{float(weapon.get('cannon_power', 1.0)):.2f} | "
                f"Kosten {int(weapon.get('cannon_cost', CANNON_COST))} Mark"
            ),
            self.font_small,
            TEXT_DIM,
            (panel.x + 72, panel.y + 260),
        )

        available_centuries = self._available_weapon_centuries()
        selected_idx = available_centuries.index(selected_weapon_century)

        buttons_y = panel.bottom - 52
        footer_rect = pygame.Rect(panel.x + 24, buttons_y - 66, panel.width - 48, 56)
        list_top = panel.y + 280
        list_bottom = footer_rect.y - 10
        list_height = max(110, list_bottom - list_top)
        list_rect = pygame.Rect(panel.x + 24, list_top, panel.width - 48, list_height)
        self.editor_weapon_list_rect = list_rect
        pygame.draw.rect(self.screen, BG_PANEL_ALT, list_rect, border_radius=8)
        pygame.draw.rect(self.screen, (60, 85, 122), list_rect, width=1, border_radius=8)

        row_height = 32
        row_step = row_height + 4
        rows_fit = max(1, (list_rect.height - 16) // row_step)
        visible_count = max(1, min(rows_fit, len(available_centuries)))
        self.editor_weapon_visible_cache = visible_count
        max_offset = max(0, len(available_centuries) - visible_count)
        self.editor_weapon_offset = max(0, min(max_offset, int(self.editor_weapon_offset)))
        if selected_idx < self.editor_weapon_offset:
            self.editor_weapon_offset = selected_idx
        if selected_idx >= self.editor_weapon_offset + visible_count:
            self.editor_weapon_offset = selected_idx - visible_count + 1

        self._draw_button(
            "editor_tier_up",
            pygame.Rect(list_rect.right - 34, list_rect.y + 6, 24, 24),
            "^",
            self.editor_weapon_offset > 0,
        )
        self._draw_button(
            "editor_tier_down",
            pygame.Rect(list_rect.right - 34, list_rect.bottom - 30, 24, 24),
            "v",
            self.editor_weapon_offset < max_offset,
        )

        self.editor_weapon_rows = []
        y = list_rect.y + 8
        visible_centuries = available_centuries[self.editor_weapon_offset : self.editor_weapon_offset + visible_count]
        inventory = getattr(ship, "cannon_inventory", {})
        list_content_rect = pygame.Rect(list_rect.x + 8, list_rect.y + 8, list_rect.width - 50, list_rect.height - 16)
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(list_content_rect)
        for century_i in visible_centuries:
            if y + row_height > list_content_rect.bottom:
                break
            row = pygame.Rect(list_rect.x + 8, y, list_rect.width - 50, row_height)
            is_selected = century_i == selected_weapon_century
            pygame.draw.rect(self.screen, ROW_SELECTED if is_selected else BG_PANEL, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            profile = weapon_profile_for_century(century_i)
            qty = 0
            if isinstance(inventory, dict):
                qty = max(0, int(inventory.get(str(century_i), 0)))
            row_text = (
                f"C{century_i} {profile.get('name', 'Kanonen')} | Bestand {qty:>2} | "
                f"{int(profile.get('cannon_cost', CANNON_COST))} Mark | "
                f"x{float(profile.get('cannon_power', 1.0)):.2f}"
            )
            self._draw_text(
                self._shorten_text(row_text, 84),
                self.font_small,
                ACCENT_2 if is_selected else TEXT_DIM,
                (row.x + 8, row.y + 8),
            )
            self.editor_weapon_rows.append((century_i, row))
            y += row_step
        self.screen.set_clip(prev_clip)

        if len(available_centuries) > visible_count:
            start = self.editor_weapon_offset + 1
            end = min(len(available_centuries), self.editor_weapon_offset + visible_count)
            self._draw_text(
                f"Stufen {start}-{end}/{len(available_centuries)} (Mausrad / Buttons)",
                self.font_small,
                TEXT_DIM,
                (list_rect.x + 8, list_rect.bottom - 22),
            )

        cannon_cost = int(weapon.get("cannon_cost", CANNON_COST))
        remaining_slots = max(0, max_cannons - ship.cannons)
        buy_1 = min(1, remaining_slots)
        buy_5 = min(5, remaining_slots)
        cannon_cost_1 = cannon_cost * buy_1
        cannon_cost_5 = cannon_cost * buy_5
        pygame.draw.rect(self.screen, BG_PANEL_ALT, footer_rect, border_radius=8)
        pygame.draw.rect(self.screen, (60, 85, 122), footer_rect, width=1, border_radius=8)
        icon = self._get_scaled("icon_cannon", (24, 24))
        if icon:
            self.screen.blit(icon, (footer_rect.x + 8, footer_rect.y + 6))
            text_x = footer_rect.x + 40
        else:
            text_x = footer_rect.x + 10
        self._draw_text(
            f"C{selected_weapon_century}: {cannon_cost} Mark pro Kanone.",
            self.font_small,
            TEXT_DIM,
            (text_x, footer_rect.y + 8),
        )

        if isinstance(inventory, dict) and inventory:
            tiers: List[str] = []
            sortable: List[Tuple[int, str, int]] = []
            for key, qty in inventory.items():
                try:
                    century_key = max(14, int(key))
                    qty_i = max(0, int(qty))
                except (TypeError, ValueError):
                    continue
                if qty_i > 0:
                    sortable.append((century_key, str(key), qty_i))
            for century_key, _raw_key, qty_i in sorted(sortable, key=lambda item: item[0]):
                tiers.append(f"C{century_key}:{qty_i}")
            if tiers:
                self._draw_text(
                    self._shorten_text("Bestand " + ", ".join(tiers), 84),
                    self.font_small,
                    TEXT_DIM,
                    (footer_rect.x + 10, footer_rect.y + 32),
                )
        self._draw_button(
            "editor_cannon_1",
            pygame.Rect(panel.x + 24, buttons_y, 150, 40),
            f"+1 ({cannon_cost_1})",
            buy_1 > 0 and self.player.money >= cannon_cost_1,
        )
        self._draw_button(
            "editor_cannon_5",
            pygame.Rect(panel.x + 184, buttons_y, 150, 40),
            f"+{buy_5} ({cannon_cost_5})",
            buy_5 > 0 and self.player.money >= cannon_cost_5,
        )
        self._draw_button(
            "editor_save",
            pygame.Rect(panel.x + panel.width - 252, buttons_y, 120, 40),
            "Speichern",
            True,
            accent=True,
        )
        self._draw_button(
            "editor_close",
            pygame.Rect(panel.x + panel.width - 122, buttons_y, 98, 40),
            "Schliessen",
            True,
        )

    def _draw_city_market(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 180))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(160, 110, 1000, 600)
        self._draw_panel_base(panel, use_paper=True)

        self._draw_text("Stadtpreise", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(self._date_label(), self.font_small, TEXT_DIM, (panel.x + 24, panel.y + 52))

        city_nodes = self._city_market_nodes()
        self.city_market_rows = []
        city_list_rect, visible_node_count, max_node_offset = self._city_market_node_layout()
        city_x = city_list_rect.x
        city_y = city_list_rect.y
        city_w = city_list_rect.width
        if self.selected_city_market >= len(city_nodes):
            self.selected_city_market = 0
        self.city_market_node_offset = max(0, min(self.city_market_node_offset, max_node_offset))
        if self.selected_city_market < self.city_market_node_offset:
            self.city_market_node_offset = self.selected_city_market
        if self.selected_city_market >= self.city_market_node_offset + visible_node_count:
            self.city_market_node_offset = self.selected_city_market - visible_node_count + 1
        visible_nodes = city_nodes[
            self.city_market_node_offset : self.city_market_node_offset + visible_node_count
        ]
        self._draw_button(
            "city_nodes_up",
            pygame.Rect(city_list_rect.right - 58, panel.y + 52, 24, 24),
            "^",
            self.city_market_node_offset > 0,
        )
        self._draw_button(
            "city_nodes_down",
            pygame.Rect(city_list_rect.right - 30, panel.y + 52, 24, 24),
            "v",
            self.city_market_node_offset < max_node_offset,
        )
        for local_idx, city_name in enumerate(visible_nodes):
            idx = self.city_market_node_offset + local_idx
            row = pygame.Rect(city_x, city_y, city_w, 34)
            selected = idx == self.selected_city_market
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            label = f"{city_name} *" if self._is_remote_region(city_name) else city_name
            self._draw_text(label, self.font_small, TEXT, (row.x + 8, row.y + 8))
            self.city_market_rows.append((idx, row))
            city_y += 40
        if len(city_nodes) > visible_node_count:
            self._draw_text(
                f"Orte {self.city_market_node_offset + 1}-{min(len(city_nodes), self.city_market_node_offset + visible_node_count)}/{len(city_nodes)}",
                self.font_small,
                TEXT_DIM,
                (city_x, panel.bottom - 90),
            )

        selected_city = self._selected_city_market_name()
        is_remote_city = self._is_remote_region(selected_city)
        prices = self._market_prices(selected_city)
        city_economy = self._city_economy(selected_city)
        dashboard = self._city_dashboard_metrics(selected_city)

        prices_x = panel.x + 270
        prices_w = 430
        buildings_x = prices_x + prices_w + 16
        buildings_w = panel.right - buildings_x - 24
        list_top = panel.y + 164
        list_bottom = panel.bottom - 188
        row_step = 42

        city_status = "BANKROTT" if self._city_is_bankrupt(selected_city) else "stabil"
        influence = self._player_city_influence(selected_city)
        treasury_text = self._format_compact_number(city_economy.treasury)
        tax_text = self._format_compact_number(dashboard["tax_income"])
        self._draw_text(
            self._shorten_text(
                f"Stadtkasse {treasury_text} | Status {city_status} | Einfluss {influence:.1f}",
                68,
            ),
            self.font,
            BAD if city_status == "BANKROTT" else TEXT_DIM,
            (prices_x, panel.y + 48),
        )
        self._draw_text("Stadtgesundheit & Gesellschaft", self.font_small, ACCENT_2, (prices_x, panel.y + 80))
        self._draw_text(
            self._shorten_text(
                (
                    f"Food {dashboard['food_ratio']:.2f} | Crowding {dashboard['crowding']:.2f} | "
                    f"Disease {dashboard['disease_pressure']:.2f} | Medical {dashboard['medical_quality']:.2f}"
                ),
                68,
            ),
            self.font_small,
            TEXT_DIM,
            (prices_x, panel.y + 102),
        )
        self._draw_text(
            self._shorten_text(
                (
                    f"Pop {dashboard['population']} / Cap {dashboard['population_capacity']} | "
                    f"Migration {dashboard['migration']:+d} | Bankr {dashboard['bankruptcy']} | Tax {tax_text}"
                ),
                68,
            ),
            self.font_small,
            TEXT_DIM,
            (prices_x, panel.y + 124),
        )

        self._draw_text(f"Preise in {selected_city}", self.font, ACCENT_2, (prices_x, list_top - 30))
        self._draw_text("Betriebe", self.font, ACCENT_2, (buildings_x, list_top - 30))

        goods_names = self._active_good_names()
        self.city_price_rows = []
        goods_list_rect, visible_goods_count, max_goods_offset = self._city_market_goods_layout()
        self.city_goods_offset = max(0, min(self.city_goods_offset, max_goods_offset))
        if self.selected_city_good >= len(goods_names):
            self.selected_city_good = 0
        if self.selected_city_good < self.city_goods_offset:
            self.city_goods_offset = self.selected_city_good
        if self.selected_city_good >= self.city_goods_offset + visible_goods_count:
            self.city_goods_offset = self.selected_city_good - visible_goods_count + 1
        visible_goods = goods_names[
            self.city_goods_offset : self.city_goods_offset + visible_goods_count
        ]
        self._draw_button(
            "city_prices_up",
            pygame.Rect(goods_list_rect.right - 58, list_top - 34, 24, 24),
            "^",
            self.city_goods_offset > 0,
        )
        self._draw_button(
            "city_prices_down",
            pygame.Rect(goods_list_rect.right - 30, list_top - 34, 24, 24),
            "v",
            self.city_goods_offset < max_goods_offset,
        )
        prices_y = list_top
        for local_idx, good_name in enumerate(visible_goods):
            idx = self.city_goods_offset + local_idx
            row = pygame.Rect(prices_x, prices_y, prices_w, 36)
            selected_good = idx == self.selected_city_good
            row_color = ROW_SELECTED if selected_good else BG_PANEL_ALT
            pygame.draw.rect(self.screen, row_color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            self._draw_text(good_name, self.font_small, TEXT, (row.x + 10, row.y + 10))
            stock = city_economy.inventory.get(good_name, 0)
            self._draw_text(f"Bestand {stock:>4}", self.font_small, TEXT_DIM, (row.x + 180, row.y + 10))
            self._draw_text(f"Preis {prices[good_name]:>4}", self.font_small, TEXT_DIM, (row.right - 120, row.y + 10))
            self.city_price_rows.append((idx, row))
            prices_y += 42
        if len(goods_names) > visible_goods_count:
            start = self.city_goods_offset + 1
            end = min(len(goods_names), self.city_goods_offset + visible_goods_count)
            self._draw_text(
                f"Waren {start}-{end}/{len(goods_names)} (Mausrad)",
                self.font_small,
                TEXT_DIM,
                (prices_x, list_bottom + 4),
            )

        analysis_rect = pygame.Rect(prices_x, panel.bottom - 174, prices_w, 62)
        self.city_analysis_rect = analysis_rect
        pygame.draw.rect(self.screen, BG_PANEL_ALT, analysis_rect, border_radius=6)
        pygame.draw.rect(self.screen, (60, 85, 122), analysis_rect, width=1, border_radius=6)
        self.city_analysis_lines = []
        if goods_names and self.selected_city_good < len(goods_names):
            selected_good_name = goods_names[self.selected_city_good]
            analysis = self._market_price_breakdown(selected_city, selected_good_name)
            if analysis:
                formula = (
                    "Basispreis x CityBias x Sea x Makro x Inventory/Scarcity x "
                    "(local_scarcity_relief) x Drift x Bankruptcy"
                )
                self.city_analysis_lines.extend(
                    self._wrap_text_to_width(
                        f"Preisanalyse {selected_good_name}: {formula}",
                        self.font_small,
                        analysis_rect.width - 52,
                    )
                )
                self.city_analysis_lines.extend(
                    self._wrap_text_to_width(
                        f"B {analysis.get('base_price', 0):.0f} | Bias {analysis.get('city_bias', 0):.2f} | "
                        f"Sea {analysis.get('sea_factor', 0):.2f} | Makro {analysis.get('macro_factor', 0):.2f}",
                        self.font_small,
                        analysis_rect.width - 52,
                    )
                )
                self.city_analysis_lines.extend(
                    self._wrap_text_to_width(
                        f"Inv {analysis.get('scarcity_base', 0):.2f} x Relief({analysis.get('local_scarcity_relief', 0):.2f}) "
                        f"= {analysis.get('scarcity_final', 0):.2f} | Drift {analysis.get('drift_factor', 0):.2f} | "
                        f"Bankr {analysis.get('bankruptcy_factor', 0):.2f} | Final {int(analysis.get('final_price', 0))}",
                        self.font_small,
                        analysis_rect.width - 52,
                    )
                )
        if not self.city_analysis_lines:
            self.city_analysis_lines = ["Preisanalyse: keine Daten verfuegbar."]
        line_height = self.font_small.get_height() + 2
        visible_lines = max(1, (analysis_rect.height - 10) // line_height)
        max_scroll = max(0, len(self.city_analysis_lines) - visible_lines)
        self.city_analysis_scroll = max(0, min(max_scroll, self.city_analysis_scroll))
        start = self.city_analysis_scroll
        end = start + visible_lines
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(analysis_rect.x + 6, analysis_rect.y + 4, analysis_rect.width - 46, analysis_rect.height - 8))
        for idx, line in enumerate(self.city_analysis_lines[start:end]):
            color = ACCENT_2 if (start + idx) == 0 else TEXT_DIM
            self._draw_text(
                line,
                self.font_small,
                color,
                (analysis_rect.x + 8, analysis_rect.y + 6 + idx * line_height),
            )
        self.screen.set_clip(prev_clip)
        can_up = self.city_analysis_scroll > 0
        can_down = self.city_analysis_scroll < max_scroll
        self._draw_button(
            "city_analysis_up",
            pygame.Rect(analysis_rect.right - 32, analysis_rect.y + 4, 24, 24),
            "^",
            can_up,
        )
        self._draw_button(
            "city_analysis_down",
            pygame.Rect(analysis_rect.right - 32, analysis_rect.bottom - 28, 24, 24),
            "v",
            can_down,
        )

        self.city_building_rows = []
        building_entries = [entry for entry in city_economy.buildings if entry.id in PRODUCTION_RECIPES]
        if not self.selected_city_building_recipe and building_entries:
            self.selected_city_building_recipe = building_entries[0].id
        building_list_rect, visible_building_count = self._city_market_building_layout()
        self.city_building_list_rect = building_list_rect
        max_building_offset = max(0, len(building_entries) - visible_building_count)
        self.city_building_offset = max(0, min(self.city_building_offset, max_building_offset))
        if building_entries:
            if self.selected_city_building_recipe not in {entry.id for entry in building_entries}:
                self.selected_city_building_recipe = building_entries[0].id
            selected_building_index = next(
                (
                    idx
                    for idx, entry in enumerate(building_entries)
                    if entry.id == self.selected_city_building_recipe
                ),
                0,
            )
            if selected_building_index < self.city_building_offset:
                self.city_building_offset = selected_building_index
            if selected_building_index >= self.city_building_offset + visible_building_count:
                self.city_building_offset = selected_building_index - visible_building_count + 1
        visible_buildings = building_entries[
            self.city_building_offset : self.city_building_offset + visible_building_count
        ]
        self._draw_button(
            "city_buildings_up",
            pygame.Rect(building_list_rect.right - 58, list_top - 34, 24, 24),
            "^",
            self.city_building_offset > 0,
        )
        self._draw_button(
            "city_buildings_down",
            pygame.Rect(building_list_rect.right - 30, list_top - 34, 24, 24),
            "v",
            self.city_building_offset < max_building_offset,
        )
        by = list_top
        building_row_height = 80
        building_list_bottom = building_list_rect.bottom
        for building in visible_buildings:
            if by + building_row_height > building_list_bottom + 1:
                break
            recipe = PRODUCTION_RECIPES.get(building.id)
            if recipe is None:
                continue
            row = pygame.Rect(buildings_x, by, buildings_w, building_row_height)
            selected_building = building.id == self.selected_city_building_recipe
            row_color = ROW_SELECTED if selected_building else BG_PANEL_ALT
            pygame.draw.rect(self.screen, row_color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            level = max(1, int(building.level))
            state = "aktiv" if building.active else "inaktiv"
            unlock_century = RECIPE_UNLOCK_CENTURY.get(building.id, 14)
            if unlock_century > self.current_century:
                run_state = f"C{unlock_century}"
            else:
                run_state = "produziert" if self._can_building_run(city_economy, building) else "wartet"
            own_pct = self._player_building_share_percent(selected_city, building.id)
            sold_pct = self._total_building_share_percent(selected_city, building.id)
            free_pct = max(0.0, MAX_BUILDING_SHARE_PERCENT - sold_pct)
            price_per_pct = self._share_price_per_percent(selected_city, building)
            inputs = ", ".join(
                f"{good_name}x{max(0, int(qty)) * level}" for good_name, qty in recipe.inputs.items()
            ) or "-"
            outputs = ", ".join(
                f"{good_name}x{max(0, int(qty)) * level}" for good_name, qty in recipe.outputs.items()
            ) or "-"
            meta_w = 120
            meta_x = row.right - meta_w - 8
            left_x = row.x + 8
            left_w = max(120, meta_x - left_x - 8)
            left_title = self._shorten_text(f"{recipe.name} L{level} ({state})", 28)
            left_in = self._shorten_text(f"In: {inputs}", 28)
            left_out = self._shorten_text(f"Out: {outputs}", 28)
            prev_clip = self.screen.get_clip()
            self.screen.set_clip(pygame.Rect(left_x, row.y + 2, left_w, row.height - 4))
            self._draw_text(
                left_title,
                self.font_small,
                TEXT,
                (left_x, row.y + 5),
            )
            self._draw_text(
                left_in,
                self.font_small,
                TEXT_DIM,
                (left_x, row.y + 29),
            )
            self._draw_text(
                left_out,
                self.font_small,
                TEXT_DIM,
                (left_x, row.y + 53),
            )
            self.screen.set_clip(prev_clip)
            right_info_top = f"I/F {own_pct:.0f}%/{free_pct:.0f}%"
            right_info_mid = f"Kurs {price_per_pct}"
            right_clip = pygame.Rect(meta_x, row.y + 2, meta_w, row.height - 4)
            prev_clip = self.screen.get_clip()
            self.screen.set_clip(right_clip)
            self._draw_text(
                self._shorten_text(right_info_top, 16),
                self.font_small,
                ACCENT_2 if selected_building else TEXT_DIM,
                (meta_x, row.y + 8),
            )
            self._draw_text(
                self._shorten_text(right_info_mid, 16),
                self.font_small,
                ACCENT_2 if selected_building else TEXT_DIM,
                (meta_x, row.y + 30),
            )
            self._draw_text(
                self._shorten_text(run_state, 16),
                self.font_small,
                ACCENT_2 if run_state == "produziert" else TEXT_DIM,
                (meta_x, row.y + 52),
            )
            self.screen.set_clip(prev_clip)
            self.city_building_rows.append((building.id, row))
            by += 84
        if len(building_entries) > visible_building_count:
            self._draw_text(
                f"Betriebe {self.city_building_offset + 1}-{min(len(building_entries), self.city_building_offset + visible_building_count)}/{len(building_entries)}",
                self.font_small,
                TEXT_DIM,
                (buildings_x, panel.bottom - 90),
            )

        selected_building = next(
            (entry for entry in city_economy.buildings if entry.id == self.selected_city_building_recipe),
            None,
        )
        can_buy_share = selected_building is not None and not is_remote_city
        social_click = self._manual_investment_click_amount(TRACK_SOCIAL)
        research_click = self._manual_investment_click_amount(TRACK_RESEARCH)
        infra_click = self._manual_investment_click_amount(TRACK_INFRASTRUCTURE)
        sophia_click = self._manual_investment_click_amount(TRACK_SOPHIA)
        social_next = self._next_investment_cost(TRACK_SOCIAL)
        research_next = self._next_investment_cost(TRACK_RESEARCH)
        infra_next = self._next_investment_cost(TRACK_INFRASTRUCTURE)
        sophia_next = self.research_manager.cost_for_level(TRACK_SOPHIA, self._investment_level(TRACK_SOPHIA))
        bailout_cost = self._city_bailout_cost(selected_city)
        row_top_y = panel.y + panel.height - 104
        row_bottom_y = panel.y + panel.height - 58
        self._draw_button(
            "city_market_buy_share",
            pygame.Rect(panel.x + 24, row_bottom_y, 132, 40),
            "+5% Anteil",
            can_buy_share,
        )
        self._draw_button(
            "city_market_social",
            pygame.Rect(panel.x + 166, row_bottom_y, 132, 40),
            "Stiftung",
            self.player is not None and social_click > 0 and not is_remote_city,
        )
        self._draw_button(
            "city_market_research",
            pygame.Rect(panel.x + 308, row_bottom_y, 132, 40),
            "Forschung",
            self.player is not None and research_click > 0,
        )
        self._draw_button(
            "city_market_infra",
            pygame.Rect(panel.x + 450, row_bottom_y, 132, 40),
            "Reisezeit",
            self.player is not None and infra_click > 0,
        )
        self._draw_button(
            "city_market_sophia",
            pygame.Rect(panel.x + 592, row_bottom_y, 132, 40),
            "Preisstab.",
            self.player is not None and sophia_click > 0,
        )
        self._draw_button(
            "city_market_bailout",
            pygame.Rect(panel.x + 734, row_bottom_y, 132, 40),
            "Stadt retten",
            self.player is not None
            and (not is_remote_city)
            and self._city_is_bankrupt(selected_city)
            and self.player.money >= bailout_cost,
            accent=True,
        )
        self._draw_text(
            self._shorten_text(
                f"Klickbetrag: Stiftung {self._format_compact_number(social_click)} / {self._format_compact_number(social_next)} | "
                f"Forschung {self._format_compact_number(research_click)} / {self._format_compact_number(research_next)} | "
                f"Reisezeit {self._format_compact_number(infra_click)} / {self._format_compact_number(infra_next)} | "
                f"Preisstabil. {self._format_compact_number(sophia_click)} / {self._format_compact_number(sophia_next)}",
                118,
            ),
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, row_top_y + 8),
        )
        bailout_line = (
            "Fernhandel: keine Stadtanteile oder Rettung."
            if is_remote_city
            else self._shorten_text(
                f"Bailout {selected_city}: {self._format_compact_number(bailout_cost)} Mark | "
                f"Monumente {city_economy.monuments.get(CITY_BAILOUT_MONUMENT_KEY, 0)}",
                118,
            )
        )
        self._draw_text(
            bailout_line,
            self.font_small,
            ACCENT_2 if (not is_remote_city and self._city_is_bankrupt(selected_city)) else TEXT_DIM,
            (panel.x + 24, row_top_y + 30),
        )
        self._draw_button(
            "city_market_close",
            pygame.Rect(panel.x + panel.width - 140, panel.y + panel.height - 58, 120, 40),
            "Schliessen",
            True,
        )

    def _handle_city_market_click(self, pos: Tuple[int, int]) -> None:
        for idx, rect in self.city_market_rows:
            if rect.collidepoint(pos):
                self.selected_city_market = idx
                self.city_building_offset = 0
                self.selected_city_building_recipe = ""
                self.selected_city_good = 0
                self.city_analysis_scroll = 0
                return
        for idx, rect in self.city_price_rows:
            if rect.collidepoint(pos):
                self.selected_city_good = idx
                self.city_analysis_scroll = 0
                return
        for recipe_id, rect in self.city_building_rows:
            if rect.collidepoint(pos):
                self.selected_city_building_recipe = recipe_id
                return
        button = self._clicked_button(pos)
        if button == "city_market_close":
            self.city_market_open = False
        elif button == "city_nodes_up":
            self.city_market_node_offset = max(0, self.city_market_node_offset - 1)
        elif button == "city_nodes_down":
            _rect, _visible_count, max_node_offset = self._city_market_node_layout()
            self.city_market_node_offset = min(max_node_offset, self.city_market_node_offset + 1)
        elif button == "city_buildings_up":
            self.city_building_offset = max(0, self.city_building_offset - 1)
        elif button == "city_buildings_down":
            selected_city = self._selected_city_market_name()
            building_entries = [
                entry for entry in self._city_economy(selected_city).buildings if entry.id in PRODUCTION_RECIPES
            ]
            _rect, visible_building_count = self._city_market_building_layout()
            max_building_offset = max(0, len(building_entries) - visible_building_count)
            self.city_building_offset = min(max_building_offset, self.city_building_offset + 1)
        elif button == "city_prices_up":
            self.city_goods_offset = max(0, self.city_goods_offset - 1)
        elif button == "city_prices_down":
            _goods_rect, _visible_goods_count, max_goods_offset = self._city_market_goods_layout()
            self.city_goods_offset = min(max_goods_offset, self.city_goods_offset + 1)
        elif button == "city_analysis_up":
            self.city_analysis_scroll = max(0, self.city_analysis_scroll - 1)
        elif button == "city_analysis_down":
            visible = 3
            if self.city_analysis_rect:
                visible = max(1, (self.city_analysis_rect.height - 10) // (self.font_small.get_height() + 2))
            max_scroll = max(0, len(self.city_analysis_lines) - visible)
            self.city_analysis_scroll = min(max_scroll, self.city_analysis_scroll + 1)
        elif button == "city_market_buy_share":
            selected_city = self._selected_city_market_name()
            if self.selected_city_building_recipe:
                self._buy_city_building_shares(selected_city, self.selected_city_building_recipe, pct=5)
        elif button == "city_market_social":
            selected_city = self._selected_city_market_name()
            if self.player is not None:
                spend = self._manual_investment_click_amount(TRACK_SOCIAL)
                if spend > 0:
                    self.invest_in_social_welfare(self.player, selected_city, spend)
        elif button == "city_market_research":
            if self.player is not None:
                spend = self._manual_investment_click_amount(TRACK_RESEARCH)
                if spend > 0:
                    self.invest_in_research_resonance(self.player, spend)
        elif button == "city_market_infra":
            if self.player is not None:
                spend = self._manual_investment_click_amount(TRACK_INFRASTRUCTURE)
                if spend > 0:
                    self.invest_in_infrastructure(self.player, spend)
        elif button == "city_market_sophia":
            if self.player is not None:
                spend = self._manual_investment_click_amount(TRACK_SOPHIA)
                if spend > 0:
                    self.invest_in_algorithmic_harmony(self.player, spend)
        elif button == "city_market_bailout":
            selected_city = self._selected_city_market_name()
            self._bailout_city(selected_city, amount=self._city_bailout_cost(selected_city))

    def _draw_missions(self) -> None:
        if self.player is None:
            return
        self._init_missions()
        self._update_fleet_synergy()
        self._update_route_master()
        self._update_arms_race()
        self.button_states = {}
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 8, 14, 210))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(150, 110, 1020, 600)
        self._draw_panel_base(panel, use_paper=True)
        self._draw_text("Missionen", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))

        month_index = self._month_index()
        y = panel.y + 80
        line_gap = 22

        mission = self.player.missions.get("hanse_privileg", {})
        state = mission.get("state", "inactive")
        self._draw_text("Hanse-Privileg", self.font, ACCENT_2, (panel.x + 24, y))
        y += line_gap
        if state == "active":
            delivered = int(mission.get("delivered", 0))
            target = int(mission.get("target", HANSE_PRIVILEG_QTY))
            city = mission.get("city", "?")
            remaining = max(0, int(mission.get("deadline", month_index)) - month_index)
            self._draw_text(
                f"Liefern: {delivered}/{target} {HANSE_PRIVILEG_GOOD} nach {city} | Frist: {remaining} Monat(e)",
                self.font_small,
                TEXT,
                (panel.x + 24, y),
            )
        elif state == "completed":
            city = mission.get("city", "?")
            self._draw_text(
                f"Abgeschlossen: -{int(HANSE_PRIVILEG_DISCOUNT * 100)}% Einkauf in {city}",
                self.font_small,
                GOOD,
                (panel.x + 24, y),
            )
        elif state == "failed":
            self._draw_text("Gescheitert (Frist abgelaufen)", self.font_small, BAD, (panel.x + 24, y))
        else:
            self._draw_text("Warte auf Knappheit (> 0.55).", self.font_small, TEXT_DIM, (panel.x + 24, y))
        y += line_gap * 2

        mission = self.player.missions.get("fleet_synergy", {})
        state = mission.get("state", "inactive")
        self._draw_text("Architekt der Synergie", self.font, ACCENT_2, (panel.x + 24, y))
        y += line_gap
        counts = mission.get("counts", {})
        if counts:
            parts = [
                f"{name} {counts.get(name, 0)}/{FLEET_SYNERGY_REQUIRED}"
                for name, *_ in self._fleet_synergy_shipyard()
            ]
            self._draw_text(" | ".join(parts), self.font_small, TEXT, (panel.x + 24, y))
            y += line_gap
        if state == "completed":
            self._draw_text("Bonus: Heuer -10%", self.font_small, GOOD, (panel.x + 24, y))
        else:
            self._draw_text("Ziel: 2 je Schiffstyp, Rumpf > 90%.", self.font_small, TEXT_DIM, (panel.x + 24, y))
        y += line_gap * 2

        mission = self.player.missions.get("atheria_resonance", {})
        state = mission.get("state", "inactive")
        self._draw_text("Atheria-Resonanz", self.font, ACCENT_2, (panel.x + 24, y))
        y += line_gap
        if state == "active":
            baseline = max(1, int(mission.get("baseline", 1)))
            worth = self._net_worth(self.player, self._market_prices(self.player.city))
            ratio = worth / baseline
            self._draw_text(
                f"Rezession aktiv: {ratio:.2f}x von Ziel {ATHERIA_RESONANCE_TARGET_MULT:.2f}x",
                self.font_small,
                TEXT,
                (panel.x + 24, y),
            )
        elif state == "completed":
            self._draw_text("Abgeschlossen: Hall of Fame", self.font_small, GOOD, (panel.x + 24, y))
        else:
            self._draw_text(
                "Warte auf Rezession (Wachstum < 0.95).",
                self.font_small,
                TEXT_DIM,
                (panel.x + 24, y),
            )
        y += line_gap * 2

        mission = self.player.missions.get("family_dynasty", {})
        state = mission.get("state", "inactive")
        self._draw_text("Familiendynastie", self.font, ACCENT_2, (panel.x + 24, y))
        y += line_gap
        target_fund = DYNASTY_INHERITANCE_PER_CHILD * DYNASTY_CHILDREN_TARGET
        if state == "completed":
            self._draw_text(
                f"Erbe gesichert: Startkapital {DYNASTY_INHERITANCE_PER_CHILD} Mark",
                self.font_small,
                GOOD,
                (panel.x + 24, y),
            )
        else:
            self._draw_text(
                f"Kinder: {self.player.children}/{DYNASTY_CHILDREN_TARGET} | "
                f"Kapital: {self.player.money}/{target_fund} | Alter < {DYNASTY_AGE_LIMIT}",
                self.font_small,
                TEXT,
                (panel.x + 24, y),
            )

        right_x = panel.x + 530
        y2 = panel.y + 80

        mission = self.player.missions.get("brewmaster", {})
        state = mission.get("state", "active")
        delivered = int(mission.get("delivered", 0))
        target = int(mission.get("target", QUEST_BREWMASTER_TARGET))
        self._draw_text("Braumeisterbund", self.font, ACCENT_2, (right_x, y2))
        y2 += line_gap
        color = GOOD if state == "completed" else TEXT
        self._draw_text(f"Bier verkaufen: {delivered}/{target}", self.font_small, color, (right_x, y2))
        y2 += line_gap * 2

        mission = self.player.missions.get("timber_trade", {})
        state = mission.get("state", "active")
        delivered = int(mission.get("delivered", 0))
        target = int(mission.get("target", QUEST_TIMBER_TARGET))
        self._draw_text("Nordholz-Vertrag", self.font, ACCENT_2, (right_x, y2))
        y2 += line_gap
        color = GOOD if state == "completed" else TEXT
        self._draw_text(f"Holz verkaufen: {delivered}/{target}", self.font_small, color, (right_x, y2))
        y2 += line_gap * 2

        mission = self.player.missions.get("route_master", {})
        state = mission.get("state", "active")
        visited = [str(city_name) for city_name in mission.get("visited", [])]
        target = int(mission.get("target", QUEST_ROUTE_MASTER_TARGET_CITIES))
        self._draw_text("Routenmeister", self.font, ACCENT_2, (right_x, y2))
        y2 += line_gap
        color = GOOD if state == "completed" else TEXT
        self._draw_text(f"Staedte besucht: {len(visited)}/{target}", self.font_small, color, (right_x, y2))
        y2 += line_gap * 2

        mission = self.player.missions.get("arms_race", {})
        state = mission.get("state", "active")
        target_cannons = int(mission.get("target_cannons", QUEST_ARMS_RACE_TARGET_CANNONS))
        target_ships = int(mission.get("target_ships", QUEST_ARMS_RACE_TARGET_SHIPS))
        cannons = sum(ship.cannons for ship in self.player.ships)
        ships_count = len(self.player.ships)
        self._draw_text("Arsenal der Hanse", self.font, ACCENT_2, (right_x, y2))
        y2 += line_gap
        color = GOOD if state == "completed" else TEXT
        self._draw_text(
            f"Schiffe {ships_count}/{target_ships} | Kanonen {cannons}/{target_cannons}",
            self.font_small,
            color,
            (right_x, y2),
        )
        y2 += line_gap * 2

        building_quests = self.player.missions.get("building_quests", {})
        unlocked_recipe_ids = self._unlocked_recipe_ids(self.current_century)
        total_tiers = len(unlocked_recipe_ids) * BUILDING_QUEST_TIERS
        completed_tiers = 0
        for recipe_id in unlocked_recipe_ids:
            entry = building_quests.get(recipe_id, {})
            completed_tiers += min(BUILDING_QUEST_TIERS, max(0, int(entry.get("tier", 0))))
        self._draw_text("Betriebskampagnen", self.font, ACCENT_2, (right_x, y2))
        y2 += line_gap
        self._draw_text(
            f"Queststufen gesamt: {completed_tiers}/{total_tiers}",
            self.font_small,
            TEXT,
            (right_x, y2),
        )
        y2 += line_gap
        preview_count = 5
        for recipe_id in unlocked_recipe_ids[:preview_count]:
            recipe = PRODUCTION_RECIPES.get(recipe_id)
            if recipe is None:
                continue
            entry = building_quests.get(recipe_id, {})
            tier = min(BUILDING_QUEST_TIERS, max(0, int(entry.get("tier", 0))))
            if tier >= BUILDING_QUEST_TIERS:
                line = f"{recipe.name}: 8/8"
            else:
                progress = max(0, int(entry.get("progress", 0)))
                target = self._building_quest_target(recipe_id, tier)
                line = f"{recipe.name}: {tier + 1}/8 {progress}/{target}"
            self._draw_text(self._shorten_text(line, 40), self.font_small, TEXT_DIM, (right_x, y2))
            y2 += 20
        if len(unlocked_recipe_ids) > preview_count:
            self._draw_text(
                f"... +{len(unlocked_recipe_ids) - preview_count} weitere Betriebe",
                self.font_small,
                TEXT_DIM,
                (right_x, y2),
            )

        self._draw_button(
            "missions_close",
            pygame.Rect(panel.right - 160, panel.bottom - 60, 130, 40),
            "Schliessen",
            True,
        )

    def _handle_missions_click(self, pos: Tuple[int, int]) -> None:
        button = self._clicked_button(pos)
        if button == "missions_close":
            self.missions_open = False
            return

    def _draw_info(self) -> None:
        if self.player is None:
            return
        player = self.player
        self.button_states = {}
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 10, 18, 208))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(130, 90, 1060, 640)
        self._draw_panel_base(panel, use_paper=True)
        self._draw_text("Spielerinfo", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))

        net = self._net_worth(player, self._market_prices(player.city))
        current_title = self._title_for(player)
        title_steps = self._active_titles()
        next_title = f"{current_title} (Maximalrang)"
        next_gap = 0
        if player.title_index + 1 < len(title_steps):
            threshold, male, female = title_steps[player.title_index + 1]
            next_title = female if player.gender == "w" else male
            next_gap = max(0, threshold - net)

        content_rect = pygame.Rect(panel.x + 20, panel.y + 68, panel.width - 40, panel.height - 146)
        self.info_scroll = max(0, min(self.info_scroll, self.info_max_scroll))
        scroll_start = content_rect.y + 8
        left_x = panel.x + 28
        right_x = panel.x + 540
        y_left = scroll_start
        y_right = scroll_start
        gap = 26

        prev_clip = self.screen.get_clip()
        self.screen.set_clip(content_rect)

        def draw_line(text: str, font: pygame.font.Font, color: Tuple[int, int, int], x: int, y: int) -> None:
            self._draw_text(text, font, color, (x, y - self.info_scroll))

        family_state = "verheiratet" if player.married else "ledig"
        spouse = player.spouse_name if player.spouse_name else "-"
        children = ", ".join(player.child_names[:4]) if player.child_names else "-"
        if len(player.child_names) > 4:
            children += f", ... (+{len(player.child_names) - 4})"

        draw_line(f"Name: {player.name}", self.font_small, TEXT, left_x, y_left)
        y_left += gap
        draw_line(f"Titel: {current_title}", self.font_small, TEXT, left_x, y_left)
        y_left += gap
        draw_line(f"Alter: {player.age}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(
            f"Geschlecht: {'weiblich' if player.gender == 'w' else 'maennlich'}",
            self.font_small,
            TEXT_DIM,
            left_x,
            y_left,
        )
        y_left += gap
        draw_line(f"Familienstand: {family_state}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(f"Ehepartner: {spouse}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(
            f"Kinder ({player.children}/{self._current_max_children()}): {children}",
            self.font_small,
            TEXT_DIM,
            left_x,
            y_left,
        )
        y_left += gap
        draw_line(f"Aktueller Ort: {player.city}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(f"Datum: {self._date_label()}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(f"Seezustand: {self.current_sea_state}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap + 2

        draw_line(f"Mark: {player.money}", self.font_small, GOOD, left_x, y_left)
        y_left += gap
        draw_line(f"Schulden: {player.debt}", self.font_small, BAD if player.debt > 0 else TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(f"Reputation: {player.reputation}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(f"Gesamtwert: {net}", self.font_small, ACCENT_2, left_x, y_left)
        y_left += gap
        draw_line(f"Naechster Titel: {next_title}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap
        draw_line(f"Fehlender Wert: {next_gap}", self.font_small, TEXT_DIM, left_x, y_left)
        y_left += gap + 2
        social_level = self._investment_level(TRACK_SOCIAL)
        research_level = self._investment_level(TRACK_RESEARCH)
        infra_level = self._investment_level(TRACK_INFRASTRUCTURE)
        sophia_level = self._investment_level(TRACK_SOPHIA)
        draw_line(
            f"Stiftung: L{social_level} ({int(self._investment_spend_total(TRACK_SOCIAL))} Mark)",
            self.font_small,
            TEXT_DIM,
            left_x,
            y_left,
        )
        y_left += gap
        draw_line(
            f"Forschung: L{research_level} | Input-Reduktion {self.research_manager.efficiency_reduction(research_level) * 100:.1f}%",
            self.font_small,
            TEXT_DIM,
            left_x,
            y_left,
        )
        y_left += gap
        draw_line(
            f"Infrastruktur: L{infra_level} | Reisefaktor {self.research_manager.travel_time_multiplier(infra_level, self.current_year):.2f}",
            self.font_small,
            TEXT_DIM,
            left_x,
            y_left,
        )
        y_left += gap
        draw_line(
            f"Marktstabilisierung: L{sophia_level} | Dampfungswert {self.global_loss_value:.2f}",
            self.font_small,
            TEXT_DIM,
            left_x,
            y_left,
        )

        ships_total = len(player.ships)
        ships_at_sea = sum(1 for ship in player.ships if ship.is_at_sea)
        ships_harbor = max(0, ships_total - ships_at_sea)
        total_capacity = sum(ship.cargo_capacity for ship in player.ships)
        total_cargo = sum(ship.total_cargo for ship in player.ships)
        avg_hull = int(round(sum(ship.hull for ship in player.ships) / ships_total)) if ships_total else 0
        avg_rigging = int(round(sum(ship.rigging for ship in player.ships) / ships_total)) if ships_total else 0
        total_cannons = sum(ship.cannons for ship in player.ships)

        draw_line("Flottenstatus", self.font, ACCENT_2, right_x, y_right)
        y_right += gap + 4
        draw_line(f"Schiffe gesamt: {ships_total}", self.font_small, TEXT, right_x, y_right)
        y_right += gap
        draw_line(f"Im Hafen: {ships_harbor} | Auf See: {ships_at_sea}", self.font_small, TEXT_DIM, right_x, y_right)
        y_right += gap
        draw_line(f"Ladung: {total_cargo}/{total_capacity}", self.font_small, TEXT_DIM, right_x, y_right)
        y_right += gap
        draw_line(
            f"Durchschnitt Rumpf/Takelage: {avg_hull}% / {avg_rigging}%",
            self.font_small,
            TEXT_DIM,
            right_x,
            y_right,
        )
        y_right += gap
        draw_line(f"Kanonen gesamt: {total_cannons}", self.font_small, TEXT_DIM, right_x, y_right)
        y_right += gap + 8

        draw_line("Missionen", self.font, ACCENT_2, right_x, y_right)
        y_right += gap + 2
        mission_labels = [
            ("hanse_privileg", "Hanse-Privileg"),
            ("fleet_synergy", "Architekt der Synergie"),
            ("atheria_resonance", "Atheria-Resonanz"),
            ("family_dynasty", "Familiendynastie"),
            ("brewmaster", "Braumeisterbund"),
            ("timber_trade", "Nordholz-Vertrag"),
            ("route_master", "Routenmeister"),
            ("arms_race", "Arsenal der Hanse"),
        ]
        for key, label in mission_labels:
            state = player.missions.get(key, {}).get("state", "inactive")
            state_text = str(state).upper()
            color = GOOD if state == "completed" else (BAD if state == "failed" else TEXT_DIM)
            draw_line(f"{label}: {state_text}", self.font_small, color, right_x, y_right)
            y_right += gap
        building_quests = player.missions.get("building_quests", {})
        unlocked_recipe_ids = self._unlocked_recipe_ids(self.current_century)
        total_tiers = len(unlocked_recipe_ids) * BUILDING_QUEST_TIERS
        completed_tiers = 0
        if isinstance(building_quests, dict):
            for recipe_id in unlocked_recipe_ids:
                quest_data = building_quests.get(recipe_id, {})
                completed_tiers += min(BUILDING_QUEST_TIERS, max(0, int(quest_data.get("tier", 0))))
        draw_line(
            f"Betriebskampagnen: {completed_tiers}/{total_tiers}",
            self.font_small,
            GOOD if total_tiers > 0 and completed_tiers >= total_tiers else TEXT_DIM,
            right_x,
            y_right,
        )
        y_right += gap

        y_right += 4
        draw_line("Schiffdetails", self.font, ACCENT_2, right_x, y_right)
        y_right += gap + 2
        for ship in player.ships:
            if ship.is_at_sea and ship.destination:
                loc = f"See->{ship.destination} ({ship.travel_turns_left}M)"
            else:
                loc = ship.city
            line = f"{ship.display_name}: {loc}, L {ship.total_cargo}/{ship.cargo_capacity}, K {ship.cannons}"
            draw_line(self._shorten_text(line, 64), self.font_small, TEXT_DIM, right_x, y_right)
            y_right += 22

        self.screen.set_clip(prev_clip)
        content_height = max(y_left, y_right) - scroll_start + 10
        self.info_max_scroll = max(0, content_height - content_rect.height)
        self.info_scroll = max(0, min(self.info_scroll, self.info_max_scroll))

        self._draw_button(
            "info_up",
            pygame.Rect(panel.right - 266, panel.bottom - 58, 48, 40),
            "^",
            self.info_scroll > 0,
        )
        self._draw_button(
            "info_down",
            pygame.Rect(panel.right - 212, panel.bottom - 58, 48, 40),
            "v",
            self.info_scroll < self.info_max_scroll,
        )
        self._draw_text(
            f"Scroll {self.info_scroll}/{self.info_max_scroll}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 26, panel.bottom - 48),
        )

        self._draw_button(
            "info_close",
            pygame.Rect(panel.right - 158, panel.bottom - 58, 130, 40),
            "Schliessen",
            True,
        )

    def _draw_cheat_prompt(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 180))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(360, 310, 600, 180)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)

        self._draw_text("Geheimcode", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        input_box = pygame.Rect(panel.x + 24, panel.y + 78, panel.width - 48, 52)
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, input_box, width=2, border_radius=8)
        display = self.cheat_text if self.cheat_text else "_"
        self._draw_text(display, self.font, TEXT, (input_box.x + 12, input_box.y + 12))
        self._draw_text("Enter: OK | Esc: Schliessen", self.font_small, TEXT_DIM, (panel.x + 24, panel.y + 140))

    def _draw_marriage_popup(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 190))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(280, 220, 760, 350)
        self._draw_panel_base(panel, use_paper=True)
        candidate = self.marriage_candidate or "eine Dame aus dem Rat"
        self._draw_text("Werbungsbrief", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        text_lines = [
            f"Ehrbarer {self.player.name if self.player else 'Haendler'},",
            f"die tugendsame {candidate} laesst anfragen,",
            "ob Ihr Euer Haus mit dem ihren in fester Ehe verbinden wollt.",
            "Eine solche Verbindung staerkt Euren Namen im Hanseraum.",
        ]
        y = panel.y + 74
        for line in text_lines:
            self._draw_text(line, self.font_small, TEXT, (panel.x + 24, y))
            y += 30
        self._draw_text("Nehmt Ihr die Hand dieser Dame an?", self.font, ACCENT_2, (panel.x + 24, y + 8))
        self._draw_button(
            "marriage_accept",
            pygame.Rect(panel.x + panel.width - 284, panel.y + panel.height - 62, 130, 42),
            "Annehmen",
            True,
            accent=True,
        )
        self._draw_button(
            "marriage_decline",
            pygame.Rect(panel.x + panel.width - 144, panel.y + panel.height - 62, 120, 42),
            "Ablehnen",
            True,
        )

    def _draw_child_name_popup(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 190))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(300, 250, 720, 300)
        self._draw_panel_base(panel, use_paper=True)
        self._draw_text("Geburt im Handelshaus", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            "Das Neugeborene verlangt nach einem Namen. Wie soll es heissen?",
            self.font_small,
            TEXT,
            (panel.x + 24, panel.y + 70),
        )
        input_box = pygame.Rect(panel.x + 24, panel.y + 112, panel.width - 48, 50)
        self.child_name_input_rect = input_box
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, input_box, width=2, border_radius=8)
        display = self.child_name_edit if self.child_name_edit else "_"
        self._draw_text(display, self.font, TEXT, (input_box.x + 12, input_box.y + 12))
        self._draw_text("Enter: Name bestaetigen", self.font_small, TEXT_DIM, (panel.x + 24, panel.y + 172))
        self._draw_button(
            "child_name_suggest",
            pygame.Rect(panel.x + panel.width - 300, panel.y + panel.height - 62, 138, 42),
            "Vorschlag",
            True,
        )
        self._draw_button(
            "child_name_submit",
            pygame.Rect(panel.x + panel.width - 152, panel.y + panel.height - 62, 128, 42),
            "Bestaetigen",
            True,
            accent=True,
        )

    def _draw_button(
        self,
        key: str,
        rect: pygame.Rect,
        label: str,
        enabled: bool,
        accent: bool = False,
    ) -> None:
        mouse = rect.collidepoint(self._virtual_mouse_pos())
        if not enabled:
            fill = (45, 49, 59)
            border = (65, 70, 82)
            fg = (118, 124, 138)
        else:
            fill = ACCENT if accent else BG_PANEL_ALT
            border = (84, 120, 169) if not accent else (26, 206, 188)
            fg = TEXT
            if mouse:
                fill = tuple(min(255, c + 12) for c in fill)
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
        shown_label = self._translate_ui_text(label)
        label_surface = self.font_small.render(shown_label, True, fg)
        label_rect = label_surface.get_rect(center=rect.center)
        self.screen.blit(label_surface, label_rect)
        self.button_states[key] = (rect, enabled)

    def _load_image(self, filename: str) -> pygame.Surface | None:
        path = self.image_dir / filename
        if not path.exists():
            return None
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None

    def _load_asset(self, stem: str) -> pygame.Surface | None:
        for ext in (".webp", ".png", ".jpg", ".jpeg"):
            image = self._load_image(f"{stem}{ext}")
            if image is not None:
                return image
        return None

    def _load_images(self) -> None:
        self.images["bg_main"] = self._load_asset("bg_main")
        self.images["bg_menu"] = self._load_asset("Menue")
        self.images["bg_setup"] = self._load_asset("bg_setup")
        self.images["bg_market"] = self._load_asset("bg_market")
        self.images["bg_sea"] = self._load_asset("bg_sea")
        self.images["bg_sea_wild"] = self._load_asset("bg_sea_wild")
        self.images["panel_stripe"] = self._load_asset("panel_stripe")
        self.images["paper_chronik"] = self._load_asset("paper_texture_chronik")
        self.images["paper_transfer"] = self._load_asset("paper_texture_transfer")
        ui_border = self._load_asset("ui_border")
        self.images["ui_border"] = ui_border
        if ui_border:
            src_w, src_h = ui_border.get_size()
            corner_src = max(64, min(src_w, src_h) // 8)
            tl = ui_border.subsurface(pygame.Rect(0, 0, corner_src, corner_src)).copy()
            self.images["ui_corner_tl"] = tl
            self.images["ui_corner_tr"] = pygame.transform.flip(tl, True, False)
            self.images["ui_corner_bl"] = pygame.transform.flip(tl, False, True)
            self.images["ui_corner_br"] = pygame.transform.flip(tl, True, True)
        self.images["icon_cannon"] = self._load_asset("icon_cannon")
        self.images["ship_kogge"] = self._load_asset("ship_kogge")
        self.images["ship_holk"] = self._load_asset("ship_holk")
        self.images["ship_kraier"] = self._load_asset("ship_kraier")

    def _get_scaled(self, key: str, size: Tuple[int, int]) -> pygame.Surface | None:
        image = self.images.get(key)
        if image is None:
            return None
        cache_key = (key, size[0], size[1])
        cached = self.scaled_images.get(cache_key)
        if cached is None:
            cached = pygame.transform.smoothscale(image, size)
            self.scaled_images[cache_key] = cached
        return cached

    def _blit_background(self, key: str | None) -> None:
        self.screen.fill(BG_MAIN)
        if key:
            bg = self._get_scaled(key, (WIDTH, HEIGHT))
            if bg:
                self.screen.blit(bg, (0, 0))
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 40))
                self.screen.blit(overlay, (0, 0))

    def _blit_background_cover(self, key: str | None) -> None:
        self.screen.fill(BG_MAIN)
        if not key:
            return
        image = self.images.get(key)
        if image is None:
            return
        img_w, img_h = image.get_size()
        if img_w <= 0 or img_h <= 0:
            return
        scale = max(WIDTH / img_w, HEIGHT / img_h)
        scaled_w = max(1, int(round(img_w * scale)))
        scaled_h = max(1, int(round(img_h * scale)))
        scaled = self._get_scaled(key, (scaled_w, scaled_h))
        if scaled:
            x = (WIDTH - scaled_w) // 2
            y = (HEIGHT - scaled_h) // 2
            self.screen.blit(scaled, (x, y))
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 40))
            self.screen.blit(overlay, (0, 0))

    def _draw_panel_header(self, panel: pygame.Rect) -> None:
        stripe = self._get_scaled("panel_stripe", (panel.width, 36))
        if stripe:
            self.screen.blit(stripe, (panel.x, panel.y))

    def _draw_panel_corners(self, panel: pygame.Rect) -> None:
        corner_size = max(28, min(panel.width, panel.height) // 8)
        for key, pos in (
            ("ui_corner_tl", (panel.x, panel.y)),
            ("ui_corner_tr", (panel.right - corner_size, panel.y)),
            ("ui_corner_bl", (panel.x, panel.bottom - corner_size)),
            ("ui_corner_br", (panel.right - corner_size, panel.bottom - corner_size)),
        ):
            corner = self._get_scaled(key, (corner_size, corner_size))
            if corner:
                self.screen.blit(corner, pos)

    def _draw_panel_base(self, panel: pygame.Rect, use_paper: bool = True) -> None:
        if use_paper:
            paper = self._get_scaled("paper_chronik", (panel.width, panel.height))
            if paper:
                self.screen.blit(paper, (panel.x, panel.y))
                overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
                overlay.fill((18, 22, 30, 110))
                self.screen.blit(overlay, (panel.x, panel.y))
            else:
                pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        else:
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (47, 67, 98), panel, width=2, border_radius=12)
        self._draw_panel_header(panel)
        self._draw_panel_corners(panel)

    def _ship_image_key(self, ship: Ship) -> str:
        name = ship.name.lower()
        if "holk" in name:
            return "ship_holk"
        if "kraier" in name:
            return "ship_kraier"
        return "ship_kogge"

    def _draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Tuple[int, int, int],
        pos: Tuple[int, int],
    ) -> None:
        shown_text = self._translate_ui_text(text)
        self.screen.blit(font.render(shown_text, True, color), pos)

    def _shorten_text(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max(0, max_len - 3)].rstrip() + "..."

    def _wrap_text_to_width(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        source = str(text).strip()
        if not source:
            return [""]
        words = source.split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if font.size(word)[0] <= max_width:
                current = word
                continue
            chunk = ""
            for ch in word:
                probe = f"{chunk}{ch}"
                if chunk and font.size(probe)[0] > max_width:
                    lines.append(chunk)
                    chunk = ch
                else:
                    chunk = probe
            current = chunk
        if current:
            lines.append(current)
        return lines or [source]

    def _date_label(self) -> str:
        month_idx = max(1, min(12, self.current_month)) - 1
        return f"ANNO {self.current_year} | {MONTHS[month_idx]}"

    def _fleet_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(655, 162, 285, 420)

    def _fleet_max_scroll(self) -> int:
        if self.player is None:
            return 0
        row_height = 86
        visible_height = self._fleet_panel_rect().height - 56
        total_height = len(self.player.ships) * row_height
        return max(0, total_height - visible_height)

    def _scroll_fleet(self, delta: int) -> None:
        max_scroll = self._fleet_max_scroll()
        self.fleet_scroll = max(0, min(max_scroll, self.fleet_scroll + int(delta)))

    def _refresh_economy_for_year(self) -> None:
        economy_year = self.current_year + (self.current_month - 1) / 12.0
        self.economy_state = self.economy_engine.for_year(
            year=economy_year,
            sea_state=self.current_sea_state,
            goods=self._active_goods().keys(),
            cities=CITIES,
        )
        if self.global_loss_value > 0:
            damped_price = 1.0 + (self.economy_state.global_price_level - 1.0) * (1.0 - self.global_loss_value * 0.55)
            self.economy_state.global_price_level = self._clamp(damped_price, 0.60, 2.20)
        self._ensure_world_state()
        self.market_cache.clear()
        self._invalidate_analysis_caches()

    def _start_new_game(self) -> None:
        name = self.new_name.strip()
        if len(name) < MIN_NAME_LEN:
            self._log(f"Fehler: Name braucht mindestens {MIN_NAME_LEN} Zeichen.")
            return

        self.current_year = STARTING_YEAR
        self.current_month = STARTING_MONTH
        self.current_century = year_to_century(self.current_year)
        self._ensure_world_state(reset_world=True, reset_npcs=True)
        self.sophia_spend_total = 0.0
        self.global_loss_value = 0.0
        global global_loss_value
        global_loss_value = 0.0
        city = CITIES[self.new_city]
        goods = self._active_good_names()
        ship = Ship(city=city, cargo={good: 0 for good in goods})
        self.player = Player(
            name=name,
            gender=self.new_gender,
            city=city,
            money=STARTING_CASH,
            debt=STARTING_DEBT,
            reputation=STARTING_REPUTATION,
            age=STARTING_AGE + self.rng.randint(0, 4),
            ships=[ship],
            warehouses={city: {good: 0 for good in goods}},
            warehouse_locks={city: {good: [] for good in goods}},
        )
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._sync_century_content(announce=False)
        self._refresh_economy_for_year()
        self._run_world_month_tick()
        self.selected_good = 0
        self.market_goods_offset = 0
        self.transfer_goods_offset = 0
        self.city_goods_offset = 0
        self.shipyard_offset = 0
        self.selected_dest = 0
        self.dest_scroll = 0
        self.selected_weapon_century = self.current_century
        self.selected_ship_type = 0
        self.selected_fleet_ship = 0
        self.fleet_scroll = 0
        self.shipyard_open = False
        self.ship_cargo_open = False
        self.ship_editor_open = False
        self.ship_editor_ship = None
        self.preview_destination = None
        self.save_menu_open = False
        self.save_menu_mode = None
        self.about_open = False
        self.about_panel_rect = None
        self.city_market_open = False
        self.selected_city_market = 0
        self.city_building_offset = 0
        self.city_building_list_rect = None
        self.city_market_node_offset = 0
        self.selected_city_building_recipe = ""
        self.missions_open = False
        self.info_open = False
        self.info_scroll = 0
        self.info_max_scroll = 0
        self.cheat_open = False
        self.cheat_text = ""
        self.marriage_popup_open = False
        self.marriage_candidate = ""
        self.child_name_popup_open = False
        self.child_name_edit = ""
        self.child_name_input_rect = None
        self.settings_open = False
        self.auto_mode = False
        self.auto_next_tick = 0
        self.auto_popup_hold_until = 0
        self.auto_last_ship_build_month = -9999
        self.time_limit_reached = False
        self.messages = []
        self._init_missions()
        self._update_missions_monthly()
        self.player.chronicle.append(f"ANNO {self.current_year}: Kontor in {city} geoeffnet.")
        self._log(f"Neues Handelshaus gegruendet in {city}.")
        self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")
        self._log(
            f"Weltmarkt: Produktion {self.last_world_tick.get('producing_buildings', 0)} Betriebe | "
            f"NPC-Deals {self.last_world_tick.get('npc_trades', 0)} | "
            f"Bankrott-Staedte {self.last_world_tick.get('cities_bankrupt', 0)} | "
            f"Steuern {self._format_compact_number(self.last_world_tick.get('total_tax', 0))} | "
            f"Migration {self._format_compact_number(self.last_world_tick.get('net_migration', 0))} | "
            f"Krankheitsfaelle {self._format_compact_number(self.last_world_tick.get('disease_cases', 0))}."
        )
        self.scene = "game"

    def _slot_path(self, slot: int) -> Path:
        return self.save_dir / f"slot_{slot:02d}.json"

    def _slot_summary(self, slot: int) -> str:
        path = self._slot_path(slot)
        if not path.exists():
            return "(leer)"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            year = raw.get("year", "?")
            month = raw.get("month")
            players = raw.get("players", [])
            names = []
            if isinstance(players, list):
                for entry in players[:3]:
                    if isinstance(entry, dict):
                        names.append(str(entry.get("name", "?")))
            names_text = ", ".join(names) if names else "-"
            if isinstance(players, list) and len(players) > 3:
                names_text += ", ..."
            saved_at = str(raw.get("saved_at", "ohne Zeitstempel"))
            if isinstance(month, int):
                month_name = MONTHS[max(1, min(12, month)) - 1]
                return f"ANNO {year} {month_name} | {names_text} | {saved_at}"
            return f"ANNO {year} | {names_text} | {saved_at}"
        except (OSError, ValueError, TypeError, KeyError):
            return "(defekt)"

    def _save_slot(self, slot: int) -> None:
        if self.player is None:
            self._log("Fehler: Kein aktives Spiel zum Speichern.")
            return
        self._ensure_world_state()
        payload = {
            "save_version": 2,
            "year": self.current_year,
            "month": self.current_month,
            "sea_state": self.current_sea_state,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ui_language": self.ui_language,
            "music_enabled": bool(self.music_enabled),
            "music_volume": round(float(self.music_volume), 2),
            "players": [self.player.to_dict()],
            "atheria_economy_engine": self.economy_engine.to_dict(),
            "atheria_economy_state": self.economy_state.to_dict(),
            "world_economy": self.world_economy.to_dict(),
            "npcs": [npc.to_dict() for npc in self.npcs],
            "last_world_tick": dict(self.last_world_tick),
            "sophia_spend_total": float(self.sophia_spend_total),
            "global_loss_value": float(self.global_loss_value),
        }
        try:
            path = self._slot_path(slot)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._log(f"Spiel in Slot {slot} gespeichert.")
        except OSError:
            self._log(f"Fehler: Slot {slot} konnte nicht gespeichert werden.")

    def _auto_save_selected_slot(self) -> None:
        slot = max(1, min(SAVE_SLOT_COUNT, int(getattr(self, "selected_slot", 1))))
        self._save_slot(slot)

    def _load_slot(self, slot: int) -> None:
        path = self._slot_path(slot)
        if not path.exists():
            self._log(f"Slot {slot} ist leer.")
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            players = raw.get("players", [])
            if not isinstance(players, list) or not players:
                self._log(f"Fehler: Slot {slot} enthaelt keine Spieler.")
                return
            first = players[0]
            if not isinstance(first, dict):
                self._log(f"Fehler: Slot {slot} ist ungueltig.")
                return
            self.player = Player.from_dict(first)
            self.current_year = int(raw.get("year", STARTING_YEAR))
            self.current_month = int(raw.get("month", STARTING_MONTH))
            self.current_month = max(1, min(12, self.current_month))
            self.current_sea_state = str(raw.get("sea_state", "bewegte See"))
            raw_lang = raw.get("ui_language")
            if isinstance(raw_lang, str):
                self._set_ui_language(raw_lang)
            if "music_enabled" in raw:
                self.music_enabled = bool(raw.get("music_enabled"))
            if "music_volume" in raw:
                try:
                    self.music_volume = self._clamp(float(raw.get("music_volume", self.music_volume)), 0.0, 1.0)
                except (TypeError, ValueError):
                    self.music_volume = self._load_music_volume()
            self._save_ui_settings()
            self._apply_music_settings(force_restart=True)
            for ship in self.player.ships:
                for good_name in self._active_good_names():
                    ship.cargo.setdefault(good_name, 0)
            for city in CITIES:
                storage = self.player.warehouses.setdefault(city, {})
                for good_name in self._active_good_names():
                    storage.setdefault(good_name, 0)
                self._locks_for_city(city)
            econ_engine_data = raw.get("atheria_economy_engine")
            if isinstance(econ_engine_data, dict):
                self.economy_engine.load_dict(econ_engine_data)
            econ_state_data = raw.get("atheria_economy_state")
            if isinstance(econ_state_data, dict):
                self.economy_state = EconomyState.from_dict(econ_state_data)
            else:
                self._refresh_economy_for_year()
            world_data = raw.get("world_economy")
            if isinstance(world_data, dict):
                self.world_economy = WorldEconomy.from_dict(world_data)
            else:
                self.world_economy = WorldEconomy()
            npcs_data = raw.get("npcs")
            if isinstance(npcs_data, list):
                self.npcs = [NPCTrader.from_dict(entry) for entry in npcs_data if isinstance(entry, dict)]
            else:
                self.npcs = []
            try:
                self.sophia_spend_total = max(0.0, float(raw.get("sophia_spend_total", 0.0)))
            except (TypeError, ValueError):
                self.sophia_spend_total = 0.0
            try:
                self.global_loss_value = max(0.0, min(0.85, float(raw.get("global_loss_value", 0.0))))
            except (TypeError, ValueError):
                self.global_loss_value = 0.0
            global global_loss_value
            global_loss_value = self.global_loss_value
            tick_data = raw.get("last_world_tick", {})
            if isinstance(tick_data, dict):
                self.last_world_tick = {
                    "producing_buildings": int(tick_data.get("producing_buildings", 0)),
                    "npc_trades": int(tick_data.get("npc_trades", 0)),
                    "cities_bankrupt": int(tick_data.get("cities_bankrupt", 0)),
                    "total_tax": max(0, min(9_999_999_999, int(tick_data.get("total_tax", 0)))),
                    "net_migration": max(-999_999_999, min(999_999_999, int(tick_data.get("net_migration", 0)))),
                    "disease_cases": max(0, min(9_999_999, int(tick_data.get("disease_cases", 0)))),
                    "disease_deaths": max(0, min(9_999_999, int(tick_data.get("disease_deaths", 0)))),
                }
            else:
                self.last_world_tick = {
                    "producing_buildings": 0,
                    "npc_trades": 0,
                    "cities_bankrupt": 0,
                    "total_tax": 0,
                    "net_migration": 0,
                    "disease_cases": 0,
                    "disease_deaths": 0,
                }
            self._ensure_world_state(
                reset_world=not isinstance(world_data, dict),
                reset_npcs=not isinstance(npcs_data, list),
            )
            self.market_cache.clear()
            self._invalidate_analysis_caches()
            self.scene = "game"
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.ship_editor_ship = None
            self.market_goods_offset = 0
            self.transfer_goods_offset = 0
            self.city_goods_offset = 0
            self.shipyard_offset = 0
            self.selected_dest = 0
            self.dest_scroll = 0
            self.selected_ship_type = 0
            self.selected_fleet_ship = 0
            self.fleet_scroll = 0
            self.selected_weapon_century = self.current_century
            self.preview_destination = None
            self.save_menu_open = False
            self.save_menu_mode = None
            self.about_open = False
            self.about_panel_rect = None
            self.city_market_open = False
            self.selected_city_market = 0
            self.city_building_offset = 0
            self.city_building_list_rect = None
            self.city_market_node_offset = 0
            self.selected_city_building_recipe = ""
            self.missions_open = False
            self.info_open = False
            self.info_scroll = 0
            self.info_max_scroll = 0
            self.cheat_open = False
            self.cheat_text = ""
            self.marriage_popup_open = False
            self.marriage_candidate = ""
            self.child_name_popup_open = False
            self.child_name_edit = ""
            self.child_name_input_rect = None
            self.settings_open = False
            self.auto_mode = bool(self.player.auto_enabled)
            self.auto_next_tick = pygame.time.get_ticks() + 120 if self.auto_mode else 0
            self.auto_popup_hold_until = 0
            self.auto_last_ship_build_month = -9999
            self.time_limit_reached = False
            self.last_dividend_pools = {}
            self._sync_century_content(announce=False)
            self._init_missions()
            self._log(f"Slot {slot} geladen.")
            self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")
            if len(players) > 1:
                self._log("Mehrspieler-Save erkannt: erster Spieler geladen.")
        except (OSError, ValueError, TypeError, KeyError):
            self._log(f"Fehler: Slot {slot} konnte nicht geladen werden.")

    def _market_prices(self, city: str) -> Dict[str, int]:
        self._ensure_world_state()
        key = (self.current_year, self.current_month, self.current_sea_state, city)
        if key in self.market_cache:
            return self.market_cache[key]

        sea_factor = SEA_FACTORS[self.current_sea_state]
        city_macro = self.economy_state.city_factor(city)
        city_economy = self._city_economy(city)
        remote_export_bonus = REMOTE_REGION_EXPORT_BONUS.get(city, {})
        is_remote_market = self._is_remote_region(city)
        loss_damping = self._clamp(float(self.global_loss_value), 0.0, 0.85)
        global_price_level = 1.0 + (self.economy_state.global_price_level - 1.0) * (1.0 - loss_damping * 0.75)
        bankruptcy_factor = 1.10 if self._city_is_bankrupt(city) else 1.0
        prices: Dict[str, int] = {}
        breakdown_by_good: Dict[str, Dict[str, float]] = {}
        for good_name, params in self._active_goods().items():
            base = params["base_price"]
            volatility = params["volatility"]
            damped_volatility = max(0.02, volatility * (1.0 - loss_damping * 0.82))
            drift = self.rng.uniform(-damped_volatility, damped_volatility)
            drift_factor = 1.0 + drift
            good_macro = self.economy_state.good_factor(good_name)
            macro_factor = global_price_level * city_macro * good_macro
            scarcity_parts = city_economy.scarcity_components(good_name)
            scarcity_base = float(scarcity_parts.get("scarcity_base", 1.0))
            local_relief = float(scarcity_parts.get("local_scarcity_relief", 0.0))
            stock_factor = float(scarcity_parts.get("scarcity_final", 1.0))
            city_bias = city_good_bias(city, good_name)
            if is_remote_market:
                if good_name in remote_export_bonus:
                    city_bias *= max(0.58, 0.82 - float(remote_export_bonus.get(good_name, 1.0)) * 0.12)
                elif good_name in REMOTE_SPECIAL_GOODS:
                    city_bias *= 1.08
                else:
                    city_bias *= 1.18
            elif good_name in REMOTE_SPECIAL_GOODS:
                city_bias *= 1.16
            price = int(
                base
                * city_bias
                * sea_factor
                * drift_factor
                * macro_factor
                * stock_factor
                * bankruptcy_factor
            )
            final_price = max(6, price)
            prices[good_name] = final_price
            breakdown_by_good[good_name] = {
                "base_price": float(base),
                "city_bias": float(city_bias),
                "sea_factor": float(sea_factor),
                "macro_factor": float(macro_factor),
                "scarcity_base": float(scarcity_base),
                "local_scarcity_relief": float(local_relief),
                "scarcity_final": float(stock_factor),
                "drift_factor": float(drift_factor),
                "bankruptcy_factor": float(bankruptcy_factor),
                "final_price": float(final_price),
            }
        self.market_cache[key] = prices
        self._market_breakdown_cache[key] = breakdown_by_good
        return prices

    def _buy_selected_good(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Kaufen nicht moeglich.")
            return

        goods = self._active_good_names()
        if not goods:
            self._log("Keine Waren verfuegbar.")
            return
        if self.selected_good >= len(goods):
            self.selected_good = 0
        good = goods[self.selected_good]
        city_stock = self._city_inventory_qty(self.player.city, good)
        if city_stock <= 0:
            self._log("Marktbestand erschoepft.")
            return
        price = self._market_prices(self.player.city)[good]
        discount = self._city_discount(self.player.city)
        if discount > 0:
            price = max(1, int(round(price * (1 - discount))))
        storage = self._storage_for_city(self.player.city)
        max_qty = min(self.player.money // price, self.trade_qty, city_stock)
        if max_qty <= 0:
            self._log("Nicht genug Mark.")
            return
        bought = self._city_take_inventory(self.player.city, good, max_qty)
        if bought <= 0:
            self._log("Marktbestand erschoepft.")
            return
        self.player.money -= bought * price
        storage[good] = storage.get(good, 0) + bought
        self.player.reputation = min(200, self.player.reputation + 1)
        self._log(f"Gekauft: {bought} {good} fuer {bought * price} Mark (Lager {self.player.city}).")

    def _sell_selected_good(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Verkaufen nicht moeglich.")
            return

        goods = self._active_good_names()
        if not goods:
            self._log("Keine Waren verfuegbar.")
            return
        if self.selected_good >= len(goods):
            self.selected_good = 0
        good = goods[self.selected_good]
        storage = self._storage_for_city(self.player.city)
        stock = storage.get(good, 0)
        qty = min(stock, self.trade_qty)
        if qty <= 0:
            self._log("Keine Ware auf Lager.")
            return
        locked_revenue, locked_sold = self._consume_locked_lots(self.player.city, good, qty)
        remaining = qty - locked_sold
        price = self._market_prices(self.player.city)[good]
        revenue = locked_revenue + remaining * price
        storage[good] -= qty
        self._city_add_inventory(self.player.city, good, qty)
        self.player.money += revenue
        self.player.reputation = min(200, self.player.reputation + 1)
        self._record_hanse_delivery(self.player.city, good, qty)
        self._record_trade_for_missions(good, qty)
        if locked_sold > 0 and remaining > 0:
            self._log(
                f"Verkauft: {qty} {good} fuer {revenue} Mark ({locked_sold} gebunden)."
            )
        elif locked_sold > 0:
            self._log(f"Verkauft: {qty} {good} fuer {revenue} Mark (gebunden).")
        else:
            self._log(f"Verkauft: {qty} {good} fuer {revenue} Mark.")

    def _travel_selected_ship(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Reisen nicht moeglich.")
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist bereits auf See.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        destinations = self._available_trade_destinations(ship.city)
        if not destinations:
            self._log("Keine Reiseziele verfuegbar.")
            return
        self.selected_dest = max(0, min(self.selected_dest, len(destinations) - 1))
        target = destinations[self.selected_dest]
        distance = self._travel_distance_units(ship.city, target)
        travel_cost = self._travel_cost_for_route(ship.city, target)
        if self.player.money < travel_cost:
            self._log("Nicht genug Mark fuer die Reise.")
            return

        origin = ship.city
        self.player.money -= travel_cost
        ship.is_at_sea = True
        ship.destination = target
        ship.travel_turns_left = self._travel_turns_for_distance(distance)
        ship.last_report = f"Ausgelaufen nach {target}, ETA {ship.travel_turns_left} Monat(e)."
        target_prices = self._market_prices(target)
        ship.locked_prices = {}
        ship.locked_qty = {}
        for good_name, qty in ship.cargo.items():
            if qty > 0:
                ship.locked_prices[good_name] = target_prices[good_name]
                ship.locked_qty[good_name] = qty
        self.preview_destination = target
        self._log(f"{ship.display_name} sticht in See Richtung {target}. Reisekosten {travel_cost} Mark.")
        self.player.chronicle.append(f"ANNO {self.current_year}: {ship.display_name} von {origin} nach {target} entsandt.")
        self.ship_cargo_open = False
        self.transfer_drag_good = None

    def _resolve_travel_risk(self, ship: Ship, origin: str, target: str) -> tuple[bool, str]:
        if self.player is None:
            return True, ""
        risk_map = {
            "tobende See": 0.44,
            "stuermische See": 0.30,
            "bewegte See": 0.20,
            "ruhige See": 0.12,
            "stille See": 0.08,
        }
        risk = risk_map[self.current_sea_state]
        origin_city = self._city_economy(origin)
        target_city = self._city_economy(target)
        mitigation = self._clamp(
            (float(origin_city.hazard_mitigation) + float(target_city.hazard_mitigation)) / 2.0,
            0.0,
            0.85,
        )
        risk = max(0.02, risk * (1.0 - mitigation))
        events: list[str] = []
        if self.rng.random() < risk:
            hull_damage = self.rng.randint(5, 18)
            rig_damage = self.rng.randint(4, 14)
            ship.hull = max(0, ship.hull - hull_damage)
            ship.rigging = max(0, ship.rigging - rig_damage)
            events.append(f"Sturm: R-{hull_damage}% T-{rig_damage}%")
            self._log(f"Sturm ({ship.display_name}): Rumpf -{hull_damage}, Takelage -{rig_damage}.")
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Sturm zwischen {origin} und {target} ({ship.display_name})."
            )
        cannon_power = self._ship_cannon_power(ship)
        effective_cannons = ship.cannons * cannon_power
        pirate_chance = (risk / (1 + effective_cannons * 0.5)) * (1.0 - mitigation * 0.75)
        if self.rng.random() < pirate_chance:
            goods = [good for good, qty in ship.cargo.items() if qty > 0]
            if goods:
                lost_good = self.rng.choice(goods)
                defense_divisor = max(2, int(2 + effective_cannons * 0.12))
                lost_qty = self.rng.randint(1, max(1, ship.cargo[lost_good] // defense_divisor))
                ship.cargo[lost_good] -= lost_qty
                if lost_good in ship.locked_qty:
                    remaining_locked = max(0, ship.locked_qty[lost_good] - lost_qty)
                    if remaining_locked > 0:
                        ship.locked_qty[lost_good] = remaining_locked
                    else:
                        ship.locked_qty.pop(lost_good, None)
                        ship.locked_prices.pop(lost_good, None)
                rep_loss = max(1, int(round(2 / (1 + effective_cannons * 0.5))))
                self.player.reputation = max(0, self.player.reputation - rep_loss)
                events.append(f"Kaper: -{lost_qty} {lost_good}")
                self._log(f"Kaperangriff ({ship.display_name}): Verlust {lost_qty} {lost_good}.")
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Kaperangriff auf {ship.display_name}, {lost_qty} {lost_good} verloren."
                )
            else:
                events.append("Kaper: keine Beute")
                self._log(f"Kaperangriff ({ship.display_name}): keine Beute.")
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Kaperangriff auf {ship.display_name}, keine Beute."
                )
        return ship.hull > 0 and ship.rigging > 0, " | ".join(events)

    def _repair(self, part: str) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Ausbesserung nicht moeglich.")
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist auf See. Ausbesserung nicht moeglich.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return

        if part == "hull":
            current = ship.hull
            label = "Rumpf"
            unit_cost = 16
        else:
            current = ship.rigging
            label = "Takelage"
            unit_cost = 12
        if current >= 100:
            self._log(f"{label} ist bereits bei 100%.")
            return
        amount = min(10, 100 - current)
        cost = amount * unit_cost
        if self.player.money < cost:
            self._log("Nicht genug Mark fuer Ausbesserung.")
            return
        self.player.money -= cost
        if part == "hull":
            ship.hull += amount
        else:
            ship.rigging += amount
        self._log(f"{label} um {amount}% verbessert. Kosten {cost} Mark.")

    def _advance_year(self) -> None:
        if self.player is None or not self.player.alive:
            return

        growth = self.economy_state.global_growth
        price_level = self.economy_state.global_price_level
        year_rolled = False

        if self.player.turns_in_debt_tower > 0:
            self.player.turns_in_debt_tower -= 1
            self._log(f"Schuldturm: noch {self.player.turns_in_debt_tower} Monat(e).")
            self.player.chronicle.append(f"ANNO {self.current_year}: Schuldturm ({MONTHS[self.current_month - 1]}).")

        self._apply_passive_income()
        monument_multiplier = self._player_monument_reputation_multiplier()
        if monument_multiplier > 1.0:
            reputation_gain = max(1, int(round(CITY_MONUMENT_REPUTATION_BASE * monument_multiplier)))
            self.player.reputation = min(200, self.player.reputation + reputation_gain)
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Stifter-Monumente steigern den Ruf (+{reputation_gain}, {MONTHS[self.current_month - 1]})."
            )

        heuer_factor = max(0.75, min(1.45, 0.88 + (price_level - 1.0) * 0.35))
        total_capacity = sum(ship.cargo_capacity for ship in self.player.ships)
        yearly_heuer = int((140 + total_capacity // 4) * heuer_factor)
        monthly_heuer = max(1, yearly_heuer // 12)
        if self.player.missions.get("fleet_synergy", {}).get("state") == "completed":
            monthly_heuer = max(1, int(round(monthly_heuer * (1 - FLEET_SYNERGY_HEUER_REDUCTION))))
        self.player.money -= monthly_heuer
        if self.player.debt > 0:
            debt_interest = max(1.01, min(1.10, 1.02 + (price_level - 1.0) * 0.05 - (growth - 1.0) * 0.02))
            monthly_interest = debt_interest ** (1 / 12)
            self.player.debt = int(self.player.debt * monthly_interest)

        if self.player.money < 0:
            self.player.debt += abs(self.player.money)
            self.player.money = 0

        if growth > 1.0:
            bonus = int(((growth - 1.0) / 12) * (120 + self.player.reputation * 3))
            if bonus > 0:
                self.player.money += bonus
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Wirtschaftsaufschwung (+{bonus} Mark, {MONTHS[self.current_month - 1]})."
                )
        elif growth < 0.95 and self.player.money > 0:
            recession_loss = int(((0.95 - growth) / 12) * max(120, self.player.money * 0.05))
            if recession_loss > 0:
                self.player.money = max(0, self.player.money - recession_loss)
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Konjunkturflaute (-{recession_loss} Mark, {MONTHS[self.current_month - 1]})."
                )

        if self.player.money > 2500 and self.player.debt > 0:
            repayment = min(self.player.debt, max(300, self.player.money // 5))
            self.player.money -= repayment
            self.player.debt -= repayment
            self._log(f"Schuldentilgung: {repayment} Mark.")

        if self.player.debt > 17000 and self.rng.random() < (0.35 / 12):
            turns = self.rng.randint(1, 3)
            self.player.turns_in_debt_tower = turns
            self.player.chronicle.append(f"ANNO {self.current_year}: {turns} Monate im Schuldturm.")
            self._log(f"Schuldturm verhaengt: {turns} Monat(e).")

        self._resolve_fleet_travel()
        self._update_title()

        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
            year_rolled = True
            self.player.age += 1
            self._resolve_life_events()
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._sync_century_content(announce=True)
        self._refresh_economy_for_year()
        self._run_world_month_tick()
        self._update_missions_monthly()
        self._maybe_trigger_marriage_proposal()
        if year_rolled:
            self._auto_save_selected_slot()
        self._log(f"{MONTHS[self.current_month - 1]} {self.current_year}: {self.current_sea_state}.")
        self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")
        self._log(
            f"Weltmarkt: Produktion {self.last_world_tick.get('producing_buildings', 0)} Betriebe | "
            f"NPC-Deals {self.last_world_tick.get('npc_trades', 0)} | "
            f"Bankrott-Staedte {self.last_world_tick.get('cities_bankrupt', 0)} | "
            f"Steuern {self._format_compact_number(self.last_world_tick.get('total_tax', 0))} | "
            f"Migration {self._format_compact_number(self.last_world_tick.get('net_migration', 0))} | "
            f"Krankheitsfaelle {self._format_compact_number(self.last_world_tick.get('disease_cases', 0))}."
        )

    def _resolve_fleet_travel(self) -> None:
        if self.player is None:
            return
        arrived: List[str] = []
        lost: List[str] = []
        for ship in list(self.player.ships):
            if not ship.is_at_sea or not ship.destination:
                continue
            if ship.travel_turns_left > 0:
                ship.travel_turns_left -= 1
            if ship.travel_turns_left > 0:
                ship.last_report = f"Auf See: noch {ship.travel_turns_left} Monat(e) bis {ship.destination}."
                continue

            origin = ship.city
            target = ship.destination
            survived, event_summary = self._resolve_travel_risk(ship, origin, target)
            if not survived:
                lost.append(ship.display_name)
                self.player.ships.remove(ship)
                continue
            ship.city = target
            ship.is_at_sea = False
            ship.destination = None
            ship.travel_turns_left = 0
            self._record_city_visit(target)
            ship.last_report = f"Ankunft in {target}."
            if event_summary:
                ship.last_report = f"{ship.last_report} {event_summary}"
            arrived.append(ship.display_name)
            self._storage_for_city(target)
            self.player.chronicle.append(
                f"ANNO {self.current_year}: {ship.display_name} in {target} angekommen."
            )

        for name in arrived:
            self._log(f"{name} ist sicher im Hafen angekommen.")
        for name in lost:
            self._log(f"{name} ist untergegangen.")
            self.player.chronicle.append(f"ANNO {self.current_year}: {name} ging verloren.")

        if not self.player.ships:
            shipyard = self._active_shipyard()
            if self.auto_mode and shipyard:
                cheapest_idx = min(range(len(shipyard)), key=lambda idx: shipyard[idx][3])
                cheapest_cost = shipyard[cheapest_idx][3]
                if self.player.money < cheapest_cost:
                    deficit = cheapest_cost - self.player.money
                    self.player.debt += deficit
                    self.player.money = cheapest_cost
                    self._log(f"Auto-Modus: Notfinanzierung {deficit} Mark fuer Ersatzschiff.")
                if self.player.city not in CITIES:
                    self.player.city = CITIES[0]
                self.selected_ship_type = cheapest_idx
                self._buy_selected_ship_type(auto_named=True)
                if self.player.ships:
                    self.player.alive = True
                    self._log("Auto-Modus: Ersatzschiff bereit, Handel geht weiter.")
                    return
            self.player.alive = False
            self.player.chronicle.append(f"ANNO {self.current_year}: Keine Schiffe mehr.")
            self._log("Alle Schiffe verloren. Handelshaus endet.")
        if self.selected_fleet_ship >= len(self.player.ships):
            self.selected_fleet_ship = max(0, len(self.player.ships) - 1)

    def _resolve_life_events(self) -> None:
        if self.player is None or not self.player.alive:
            return

        self._age_children_and_resolve_mortality()

        if self.player.age > 60:
            death_chance = min(0.42, (self.player.age - 60) * 0.025)
            if self.rng.random() < death_chance:
                if self._apply_firstborn_heir():
                    return
                if self._apply_dynasty_heir():
                    return
                self.player.alive = False
                self.player.chronicle.append(f"ANNO {self.current_year}: Tod des Vorfahren.")
                self._log("Tod des Vorfahren.")
                return

        if self.player.married:
            marriage_year = self.player.marriage_year if self.player.marriage_year is not None else self.current_year - 1
            marriage_month = self.player.marriage_month if self.player.marriage_month is not None else self.current_month
            months_married = (self.current_year - marriage_year) * 12 + (self.current_month - marriage_month)
            if self.player.children >= self._current_max_children():
                return
            city = self._city_economy(self.player.city if self.player.city in CITIES else CITIES[0])
            base_birth_chance = birth_chance_for_year(self.current_year)
            age_penalty = self._clamp(1.0 - max(0, self.player.age - 35) * 0.02, 0.45, 1.0)
            support_factor = self._clamp(0.72 + float(city.child_survival_rate) * 0.42, 0.55, 1.16)
            birth_chance = self._clamp(base_birth_chance * age_penalty * support_factor, 0.02, 0.56)
            if months_married >= 12 and self.rng.random() < birth_chance:
                self._trigger_child_birth_event()

    def _update_title(self) -> None:
        if self.player is None:
            return
        worth = self._net_worth(self.player, self._market_prices(self.player.city))
        title_steps = self._active_titles()
        new_index = 0
        for idx, (threshold, _, _) in enumerate(title_steps):
            if worth >= threshold:
                new_index = idx
        month_index = max(0, self._month_index())
        max_by_time = 0
        for idx in range(1, len(title_steps)):
            if month_index >= self._title_min_months_for_index(idx):
                max_by_time = idx
        new_index = min(new_index, max_by_time)
        if new_index > self.player.title_index:
            self.player.title_index = new_index
            title = self._title_for(self.player)
            self.player.chronicle.append(f"ANNO {self.current_year}: In den Stand '{title}' erhoben.")
            self._log(f"Aufstieg: {title}")
            self._maybe_trigger_marriage_proposal()

    def _title_min_months_for_index(self, index: int) -> int:
        if index <= 0:
            return 0
        return 2 + (index - 1) * 6

    def _title_for(self, player: Player) -> str:
        title_steps = self._active_titles()
        _, male, female = title_steps[min(player.title_index, len(title_steps) - 1)]
        return female if player.gender == "w" else male

    def _net_worth(self, player: Player, prices: Dict[str, int]) -> int:
        cargo_value = 0
        for ship in player.ships:
            cargo_value += sum(prices.get(good, 0) * qty for good, qty in ship.cargo.items())
        for goods in player.warehouses.values():
            cargo_value += sum(prices.get(good, 0) * qty for good, qty in goods.items())
        fleet_value = sum(ship.value for ship in player.ships)
        return player.money + cargo_value + fleet_value - player.debt + player.reputation * 150

    def _log(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 200:
            self.messages = self.messages[-160:]


def run_pygame_game() -> int:
    try:
        app = PygameHanseApp()
    except Exception as exc:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = traceback.format_exc()
        log_entry = (
            f"[{timestamp}] Boot-Fehler: {type(exc).__name__}: {exc}\n"
            f"{details}\n"
        )
        log_targets: List[Path] = []
        try:
            save_dir = _default_save_dir()
            save_dir.mkdir(parents=True, exist_ok=True)
            log_targets.append(save_dir / "boot_error.log")
        except OSError:
            pass
        if ("ANDROID_ARGUMENT" in os.environ) or (sys.platform == "android"):
            env_download = os.getenv("DOWNLOAD_DIR", "").strip()
            external_storage = os.getenv("EXTERNAL_STORAGE", "").strip()
            candidates = []
            if env_download:
                candidates.append(Path(env_download))
            if external_storage:
                candidates.append(Path(external_storage) / "Download")
            candidates.extend(
                [
                    Path("/storage/emulated/0/Download"),
                    Path("/storage/self/primary/Download"),
                    Path("/sdcard/Download"),
                ]
            )
            for candidate in candidates:
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    log_targets.append(candidate / "hanse_boot_error.log")
                    break
                except OSError:
                    continue
        for target in log_targets:
            try:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(log_entry)
            except OSError:
                continue
        return 1
    return app.run()
