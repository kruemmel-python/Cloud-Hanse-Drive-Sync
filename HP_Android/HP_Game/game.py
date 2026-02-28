from __future__ import annotations

import csv
import json
import hashlib
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from atheria_economy import AtheriaEconomyEngine, EconomyState
from game_data import (
    CITIES,
    birth_chance_for_year,
    child_mortality_for_year,
    city_good_bias,
    disease_pressure_for_year,
    goods_for_year,
    max_children_for_year,
    MAX_PLAYERS,
    MIN_NAME_LEN,
    MONTHS,
    HANSE_PRIVILEG_GOOD,
    HANSE_PRIVILEG_QTY,
    HANSE_PRIVILEG_MONTHS,
    HANSE_PRIVILEG_DISCOUNT,
    FLEET_SYNERGY_REQUIRED,
    FLEET_SYNERGY_HULL_MIN,
    FLEET_SYNERGY_HEUER_REDUCTION,
    ATHERIA_RESONANCE_GROWTH_MAX,
    ATHERIA_RESONANCE_TARGET_MULT,
    DYNASTY_CHILDREN_TARGET,
    DYNASTY_INHERITANCE_PER_CHILD,
    DYNASTY_AGE_LIMIT,
    SAVE_DIR,
    SAVE_FILE,
    SAVE_SLOT_COUNT,
    SEA_FACTORS,
    SEA_STATES,
    STARTING_AGE,
    STARTING_CASH,
    STARTING_DEBT,
    STARTING_MONTH,
    STARTING_REPUTATION,
    STARTING_YEAR,
    modern_shipyard_for_year,
    shipyard_for_year,
    title_steps_for_year,
    year_to_century,
)
from models import Building, CityEconomy, Investment, NPCTrader, Player, ProductionRecipe, Ship, WorldEconomy


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
CHILD_MORTALITY_VULNERABLE_AGE = 6
CLI_AUTO_RESERVE_PER_SHIP_MARK = 420
CLI_AUTO_POLICY_RESERVE_STEP = 250
CLI_AUTO_POLICY_MIN_ROUTE_SCORE = 20

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
}


class HanseGame:
    def __init__(
        self,
        rng: random.Random | None = None,
        save_dir: Path | None = None,
        legacy_save_path: Path | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.save_dir = save_dir or Path(__file__).with_name(SAVE_DIR)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_save_path = legacy_save_path or Path(__file__).with_name(SAVE_FILE)
        self.active_slot: int | None = None
        self.players: List[Player] = []
        self.current_year = STARTING_YEAR
        self.current_month = STARTING_MONTH
        self.current_sea_state = "bewegte See"
        self._market_cache: Dict[Tuple[int, int, str, str], Dict[str, int]] = {}
        self._market_breakdown_cache: Dict[Tuple[int, int, str, str], Dict[str, Dict[str, float]]] = {}
        self.city_dashboard_cache: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
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
            "disease_cases": 0,
            "disease_deaths": 0,
        }
        self.last_dividend_pools: Dict[str, Dict[str, int]] = {}
        self._ensure_world_state(reset_world=True, reset_npcs=True)

    def _active_goods(self) -> Dict[str, Dict[str, float]]:
        return goods_for_year(self.current_year)

    def _active_good_names(self) -> List[str]:
        return list(self._active_goods().keys())

    def _active_shipyard(self) -> List[Tuple[str, int, int, int]]:
        return modern_shipyard_for_year(self.current_year)

    def _fleet_synergy_shipyard(self) -> List[Tuple[str, int, int, int]]:
        return shipyard_for_year(STARTING_YEAR)

    def _active_titles(self) -> List[Tuple[int, str, str]]:
        return title_steps_for_year(self.current_year)

    def _sync_player_goods(self, player: Player) -> None:
        goods = self._active_good_names()
        for ship in player.ships:
            for good_name in goods:
                ship.cargo.setdefault(good_name, 0)
        for city in CITIES:
            storage = player.warehouses.setdefault(city, {})
            for good_name in goods:
                storage.setdefault(good_name, 0)

    def _stable_stock_for(self, city_name: str, good_name: str) -> int:
        seed = f"{city_name}:{good_name}:hanse-world-stock"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        span = WORLD_INITIAL_STOCK_MAX - WORLD_INITIAL_STOCK_MIN + 1
        return WORLD_INITIAL_STOCK_MIN + (int.from_bytes(digest[:8], "big") % span)

    def _current_century(self) -> int:
        return year_to_century(self.current_year)

    def _unlocked_recipe_ids(self, century: int | None = None) -> List[str]:
        century_i = century if century is not None else self._current_century()
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
            return Ship(
                name="Holk",
                cargo_capacity=170,
                value=5600,
                city=city_name,
                cargo={good_name: 0 for good_name in goods},
            )

        return [
            NPCTrader(name="Hakon", city="Bergen", money=7600, ship=_ship_for_city("Bergen")),
            NPCTrader(name="Marta", city="Luebeck", money=7800, ship=_ship_for_city("Luebeck")),
            NPCTrader(name="Ilya", city="Novgorod", money=7400, ship=_ship_for_city("Novgorod")),
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
                city.population = max(180, int(city.population))
            except (TypeError, ValueError):
                city.population = 2400
            if not isinstance(city.institutions, dict):
                city.institutions = {}
            city.institutions.setdefault("hospital", 0)
            city.institutions.setdefault("doctors", 0)
            city.institutions.setdefault("sanitation", 0)
            try:
                city.disease_pressure = _clamp(float(city.disease_pressure), 0.0, 1.2)
            except (TypeError, ValueError):
                city.disease_pressure = 0.0
            try:
                city.disease_cases = max(0, int(city.disease_cases))
            except (TypeError, ValueError):
                city.disease_cases = 0
            try:
                city.child_survival_rate = _clamp(float(city.child_survival_rate), 0.15, 0.999)
            except (TypeError, ValueError):
                city.child_survival_rate = 0.75
            try:
                city.doctor_coverage = _clamp(float(city.doctor_coverage), 0.0, 1.5)
            except (TypeError, ValueError):
                city.doctor_coverage = 0.0

        if reset_npcs or not isinstance(self.npcs, list):
            self.npcs = self._default_npcs()

        sanitized_npcs: List[NPCTrader] = []
        for npc in self.npcs:
            if not isinstance(npc, NPCTrader):
                continue
            if npc.city not in CITIES:
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
                city.inventory[good_name] = self._stable_stock_for(city_name, good_name)
        return city

    def _city_inventory_qty(self, city_name: str, good_name: str) -> int:
        city = self._city_economy(city_name)
        return max(0, int(city.inventory.get(good_name, 0)))

    def _city_add_inventory(self, city_name: str, good_name: str, qty: int) -> int:
        if qty <= 0:
            return 0
        city = self._city_economy(city_name)
        city.inventory[good_name] = city.inventory.get(good_name, 0) + int(qty)
        return int(qty)

    def _institution_level(self, city: CityEconomy, key: str) -> int:
        try:
            return max(0, int(city.institutions.get(key, 0)))
        except (TypeError, ValueError):
            return 0

    def _city_health_profile(self, city_name: str) -> Dict[str, float]:
        city = self._city_economy(city_name)
        century = self._current_century()
        if century >= 15:
            city.institutions["hospital"] = max(
                self._institution_level(city, "hospital"),
                1 + max(0, century - 15) // 4,
            )
        if century >= 16:
            city.institutions["doctors"] = max(
                self._institution_level(city, "doctors"),
                1 + max(0, century - 16) // 4,
            )
        if century >= 19:
            city.institutions["sanitation"] = max(
                self._institution_level(city, "sanitation"),
                1 + max(0, century - 19) // 3,
            )
        hospital_lvl = self._institution_level(city, "hospital")
        doctors_lvl = self._institution_level(city, "doctors")
        sanitation_lvl = self._institution_level(city, "sanitation")
        food_stock = (
            city.inventory.get("Getreide", 0)
            + city.inventory.get("Hering", 0)
            + city.inventory.get("Salz", 0)
        )
        food_need = max(140, int(city.population * 0.14))
        food_ratio = food_stock / max(1, food_need)
        base_disease = disease_pressure_for_year(self.current_year)
        supply_stress = max(0.0, min(1.6, 1.0 - food_ratio))
        medical_quality = _clamp(
            0.20
            + (hospital_lvl * 0.10)
            + (doctors_lvl * 0.14)
            + (sanitation_lvl * 0.07)
            + (float(city.hazard_mitigation) * 0.35),
            0.08,
            1.30,
        )
        disease_pressure = _clamp(
            base_disease
            + (supply_stress * 0.22)
            + (0.10 if self._city_is_bankrupt(city_name) else 0.0)
            - (medical_quality * 0.20),
            0.01,
            0.95,
        )
        outbreak_factor = self.rng.uniform(0.20, 1.20)
        disease_cases = int(
            round(
                city.population
                * disease_pressure
                * (0.003 + base_disease * 0.022)
                * outbreak_factor
            )
        )
        disease_cases = max(0, min(int(city.population * 0.30), disease_cases))
        child_survival = _clamp(
            1.0
            - child_mortality_for_year(self.current_year) * (1.25 - medical_quality)
            - disease_pressure * 0.08,
            0.25,
            0.995,
        )
        city.disease_pressure = disease_pressure
        city.disease_cases = disease_cases
        city.child_survival_rate = child_survival
        city.doctor_coverage = _clamp(
            (hospital_lvl * 0.16 + doctors_lvl * 0.24 + sanitation_lvl * 0.10)
            / max(1.0, city.population / 12_000.0),
            0.0,
            1.5,
        )
        return {
            "disease_pressure": float(disease_pressure),
            "disease_cases": int(disease_cases),
            "child_survival_rate": float(child_survival),
            "medical_quality": float(medical_quality),
        }

    def _tick_city_health(self) -> Dict[str, int]:
        total_cases = 0
        total_deaths = 0
        for city_name in CITIES:
            profile = self._city_health_profile(city_name)
            cases = int(profile.get("disease_cases", 0))
            pressure = float(profile.get("disease_pressure", 0.0))
            city = self._city_economy(city_name)
            death_rate = _clamp(0.010 + pressure * 0.040 - city.doctor_coverage * 0.008, 0.002, 0.070)
            deaths = int(round(cases * death_rate))
            if deaths > 0:
                city.population = max(180, int(city.population) - deaths)
            total_cases += cases
            total_deaths += max(0, deaths)
        return {"disease_cases": total_cases, "disease_deaths": total_deaths}

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

    def _player_city_influence(self, player: Player, city_name: str) -> float:
        return max(0.0, float(player.city_influence.get(city_name, 0.0)))

    def _add_player_city_influence(self, player: Player, city_name: str, amount: float) -> None:
        if amount == 0:
            return
        current = max(0.0, float(player.city_influence.get(city_name, 0.0)))
        player.city_influence[city_name] = max(0.0, current + float(amount))

    def _player_building_share_percent(self, player: Player, city_name: str, recipe_id: str) -> float:
        city_shares = player.building_shares.get(city_name, {})
        return max(0.0, min(MAX_BUILDING_SHARE_PERCENT, float(city_shares.get(recipe_id, 0.0))))

    def _set_player_building_share_percent(self, player: Player, city_name: str, recipe_id: str, pct: float) -> None:
        if city_name not in player.building_shares:
            player.building_shares[city_name] = {}
        player.building_shares[city_name][recipe_id] = max(0.0, min(MAX_BUILDING_SHARE_PERCENT, float(pct)))

    def _total_building_share_percent(
        self,
        city_name: str,
        recipe_id: str,
        *,
        exclude_player: Player | None = None,
    ) -> float:
        total = 0.0
        for player in self.players:
            if exclude_player is not None and player is exclude_player:
                continue
            total += self._player_building_share_percent(player, city_name, recipe_id)
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
        return self._city_economy(city_name).treasury <= CITY_BANKRUPTCY_LIMIT

    def _building_dividend_pool(self, city_name: str, recipe_id: str) -> int:
        city_pool = self.last_dividend_pools.get(city_name, {})
        return max(0, int(city_pool.get(recipe_id, 0)))

    def _apply_passive_income(self, player: Player) -> None:
        self._ensure_world_state()
        total_dividend = 0
        detail: List[str] = []
        for city_name, share_map in player.building_shares.items():
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
                self._add_player_city_influence(
                    player,
                    city_name,
                    (actual / 1000.0) * INFLUENCE_PER_DIVIDEND_1000,
                )
                recipe = PRODUCTION_RECIPES.get(recipe_id)
                recipe_name = recipe.name if recipe else recipe_id
                detail.append(f"{city_name}:{recipe_name} +{actual}")
        if total_dividend > 0:
            player.money += total_dividend
            summary = ", ".join(detail[:3])
            if len(detail) > 3:
                summary += ", ..."
            print(f"Passive Rendite: +{total_dividend} Mark ({summary})")

    def _tick_world_production(self) -> int:
        self._ensure_world_state()
        active_goods = set(self._active_good_names())
        current_century = self._current_century()
        active_buildings = 0
        self.last_dividend_pools = {city_name: {} for city_name in CITIES}
        for city_name in CITIES:
            city = self._city_economy(city_name)
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
                    required = max(0, int(qty)) * level
                    if city.inventory.get(good_name, 0) < required:
                        can_run = False
                        break
                    input_total += required
                if not can_run:
                    continue

                output_total = 0
                for good_name, qty in recipe.inputs.items():
                    required = max(0, int(qty)) * level
                    city.inventory[good_name] = max(0, int(city.inventory.get(good_name, 0)) - required)
                for good_name, qty in recipe.outputs.items():
                    produced = max(0, int(qty)) * level
                    city.inventory[good_name] = int(city.inventory.get(good_name, 0)) + produced
                    output_total += produced
                city.treasury -= max(0, int(recipe.upkeep)) * level
                operating_value = max(
                    0,
                    (output_total * 6) - (input_total * 3) - (max(0, int(recipe.upkeep)) * level * 2),
                )
                dividend_pool = int(round(operating_value * DIVIDEND_POOL_FACTOR))
                if dividend_pool > 0:
                    city_pool = self.last_dividend_pools.setdefault(city_name, {})
                    city_pool[building.id] = city_pool.get(building.id, 0) + dividend_pool
                    city.treasury += max(0, dividend_pool // 6)
                active_buildings += 1
        return active_buildings

    def _tick_world_npcs(self) -> int:
        self._ensure_world_state()
        goods = self._active_good_names()
        npc_trades = 0
        for npc in self.npcs:
            if npc.city not in CITIES:
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
                for target in CITIES:
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
        health_metrics = self._tick_city_health()
        npc_trade_count = self._tick_world_npcs()
        bankrupt_count = sum(1 for city_name in CITIES if self._city_is_bankrupt(city_name))
        # NPCs handeln vor dem Spieler. Danach bleiben Preise fuer den Monat gecached stabil.
        self._market_cache.clear()
        self._market_breakdown_cache.clear()
        self.city_dashboard_cache.clear()
        self.last_world_tick = {
            "producing_buildings": production_count,
            "npc_trades": npc_trade_count,
            "cities_bankrupt": bankrupt_count,
            "disease_cases": int(health_metrics.get("disease_cases", 0)),
            "disease_deaths": int(health_metrics.get("disease_deaths", 0)),
        }
        return dict(self.last_world_tick)

    def _can_building_run(self, city: CityEconomy, building: Building) -> bool:
        recipe = PRODUCTION_RECIPES.get(building.id)
        if recipe is None or not building.active:
            return False
        if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > self._current_century():
            return False
        level = max(1, int(building.level))
        for good_name, qty in recipe.inputs.items():
            required = max(0, int(qty)) * level
            if city.inventory.get(good_name, 0) < required:
                return False
        return True

    def _city_dashboard_metrics(self, city_name: str) -> Dict[str, Any]:
        city = self._city_economy(city_name)
        cache_key = (self.current_year, self.current_month, city_name)
        cached = self.city_dashboard_cache.get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)

        food_stock = (
            city.inventory.get("Getreide", 0)
            + city.inventory.get("Hering", 0)
            + city.inventory.get("Salz", 0)
        )
        food_need = max(140, int(city.population * 0.14))
        food_ratio = food_stock / max(1, food_need)
        crowding = _clamp((city.population / max(300.0, city.population * 0.52 + 1200.0)) - 1.0, 0.0, 2.5)

        hospital_lvl = self._institution_level(city, "hospital")
        doctors_lvl = self._institution_level(city, "doctors")
        sanitation_lvl = self._institution_level(city, "sanitation")
        medical_quality = _clamp(
            0.20
            + (hospital_lvl * 0.10)
            + (doctors_lvl * 0.14)
            + (sanitation_lvl * 0.07)
            + (float(city.hazard_mitigation) * 0.35),
            0.08,
            1.30,
        )
        institutions = " | ".join(
            f"{name}:{max(0, int(level))}"
            for name, level in sorted(city.institutions.items())
            if max(0, int(level)) > 0
        )
        if not institutions:
            institutions = "-"

        metrics: Dict[str, Any] = {
            "food_ratio": float(food_ratio),
            "crowding": float(crowding),
            "disease_pressure": float(city.disease_pressure),
            "medical_quality": float(medical_quality),
            "migration": int(city.migration),
            "bankruptcy": int(self._city_is_bankrupt(city_name)),
            "institutions": institutions,
            "infrastructure": float(city.infrastructure),
            "population": int(city.population),
            "social_stability": float(city.social_stability),
            "quality_of_life": float(city.quality_of_life),
            "doctor_coverage": float(city.doctor_coverage),
            "tax_income": int(city.tax_income),
        }
        self.city_dashboard_cache[cache_key] = dict(metrics)
        return metrics

    def _market_price_breakdown(self, city: str, good_name: str) -> Dict[str, float]:
        cache_key = (self.current_year, self.current_month, self.current_sea_state, city)
        if cache_key not in self._market_breakdown_cache:
            self._market_prices(city)
        city_data = self._market_breakdown_cache.get(cache_key, {})
        entry = city_data.get(good_name)
        return dict(entry) if isinstance(entry, dict) else {}

    def _show_price_breakdown(self, city_name: str) -> None:
        goods = self._active_good_names()
        if not goods:
            print("Keine Waren verfuegbar.")
            return
        print()
        print("Preisanalyse")
        for idx, good_name in enumerate(goods, start=1):
            print(f"{idx}) {good_name}")
        print("0) Zurueck")
        choice = self._ask_int(f"Ware (0-{len(goods)}): ", 0, len(goods))
        if choice == 0:
            return
        good_name = goods[choice - 1]
        data = self._market_price_breakdown(city_name, good_name)
        if not data:
            print("Keine Analyse verfuegbar.")
            return
        print("-" * 70)
        print(f"Preisanalyse {good_name} in {city_name}")
        print(
            "Formel: Basispreis x CityBias x Sea x Makro x Inventory/Scarcity x "
            "(local_scarcity_relief) x Drift x Bankruptcy"
        )
        print(f"Basispreis:             {data.get('base_price', 0):.4f}")
        print(f"CityBias:               {data.get('city_bias', 0):.4f}")
        print(f"Sea:                    {data.get('sea_factor', 0):.4f}")
        print(f"Makro:                  {data.get('macro_factor', 0):.4f}")
        print(f"Inventory/Scarcity:     {data.get('scarcity_base', 0):.4f}")
        print(f"local_scarcity_relief:  {data.get('local_scarcity_relief', 0):.4f}")
        print(f"Scarcity final:         {data.get('scarcity_final', 0):.4f}")
        print(f"Drift:                  {data.get('drift_factor', 0):.4f}")
        print(f"Bankruptcy:             {data.get('bankruptcy_factor', 0):.4f}")
        print(f"Finalpreis:             {int(data.get('final_price', 0))}")
        print("-" * 70)

    def _show_city_economy(self, city_name: str, player: Player | None = None) -> None:
        city = self._city_economy(city_name)
        prices = self._market_prices(city_name)
        dashboard = self._city_dashboard_metrics(city_name)
        city_status = "BANKROTTGEFAEHRDET" if self._city_is_bankrupt(city_name) else "stabil"
        print()
        print("=" * 70)
        print(f"WELTWIRTSCHAFT: {city_name}")
        print(
            f"Stadtkasse: {city.treasury} | Status: {city_status} | Betriebe: {len(city.buildings)} | "
            f"Krankheitsdruck: {city.disease_pressure:.2f} | Faelle: {city.disease_cases}"
        )
        if player is not None:
            influence = self._player_city_influence(player, city_name)
            share_sum = sum(self._player_building_share_percent(player, city_name, b.id) for b in city.buildings)
            print(f"Ihr Einfluss: {influence:.1f} | Ihr Anteilsportfolio: {share_sum:.1f}%")
        print("--- Stadtgesundheit & Gesellschaft ---")
        print(
            f"Food Ratio {dashboard['food_ratio']:.2f} | Crowding {dashboard['crowding']:.2f} | "
            f"Disease Pressure {dashboard['disease_pressure']:.2f} | Medical Quality {dashboard['medical_quality']:.2f}"
        )
        print(
            f"Migration {dashboard['migration']:+d} | Bankruptcy {dashboard['bankruptcy']} | "
            f"Infrastructure {dashboard['infrastructure']:.2f}"
        )
        print(
            f"Population {dashboard['population']} | Social Stability {dashboard['social_stability']:.1f} | "
            f"Quality of Life {dashboard['quality_of_life']:.1f} | Doctor Coverage {dashboard['doctor_coverage']:.2f}"
        )
        print(f"Steuern/Monat {dashboard['tax_income']} | Institutions {dashboard['institutions']}")
        print("-" * 70)
        print("Betriebe:")
        for idx, building in enumerate(city.buildings, start=1):
            recipe = PRODUCTION_RECIPES.get(building.id)
            if recipe is None:
                continue
            level = max(1, int(building.level))
            status = "aktiv" if building.active else "inaktiv"
            unlock_century = RECIPE_UNLOCK_CENTURY.get(building.id, 14)
            if unlock_century > self._current_century():
                run_state = f"gesperrt bis C{unlock_century}"
            else:
                run_state = "produziert" if self._can_building_run(city, building) else "wartet auf Inputs"
            inputs = ", ".join(
                f"{good_name} x{max(0, int(qty)) * level}" for good_name, qty in recipe.inputs.items()
            ) or "-"
            outputs = ", ".join(
                f"{good_name} x{max(0, int(qty)) * level}" for good_name, qty in recipe.outputs.items()
            ) or "-"
            upkeep = max(0, int(recipe.upkeep)) * level
            own_pct = self._player_building_share_percent(player, city_name, building.id) if player else 0.0
            sold_pct = self._total_building_share_percent(city_name, building.id)
            price_per_pct = self._share_price_per_percent(city_name, building)
            dividend_pool = self._building_dividend_pool(city_name, building.id)
            print(
                f" {idx:>2}) {recipe.name:14} | Level {level} | {status:7} | {run_state:17} | "
                f"Input [{inputs}] -> Output [{outputs}] | Unterhalt {upkeep} | "
                f"Anteile Ihr {own_pct:.1f}% / Markt {sold_pct:.1f}% | Kurs {price_per_pct}/1% | DivPool {dividend_pool}"
            )
        print("-" * 70)
        print("Marktbestaende:")
        for good_name in self._active_good_names():
            stock = city.inventory.get(good_name, 0)
            scarcity = city.scarcity_factor(good_name)
            price = prices.get(good_name, 0)
            print(f"  {good_name:14} Bestand {stock:>4} | Faktor x{scarcity:.2f} | Preis {price:>4}")
        print("=" * 70)

    def _buy_city_shares_menu(self, player: Player, city_name: str) -> None:
        city = self._city_economy(city_name)
        current_century = self._current_century()
        available_buildings = [
            building
            for building in city.buildings
            if RECIPE_UNLOCK_CENTURY.get(building.id, 14) <= current_century
        ]
        if not available_buildings:
            print("Keine freigeschalteten Betriebe in dieser Stadt.")
            return
        print("Betrieb fuer Anteilskauf waehlen:")
        for idx, building in enumerate(available_buildings, start=1):
            recipe = PRODUCTION_RECIPES.get(building.id)
            if recipe is None:
                continue
            price_per_pct = self._share_price_per_percent(city_name, building)
            sold_pct = self._total_building_share_percent(city_name, building.id)
            own_pct = self._player_building_share_percent(player, city_name, building.id)
            print(
                f"{idx}) {recipe.name:16} Kurs {price_per_pct:>4}/1% | "
                f"frei {max(0.0, MAX_BUILDING_SHARE_PERCENT - sold_pct):>5.1f}% | Ihr {own_pct:>5.1f}%"
            )
        print("0) Zurueck")
        choice = self._ask_int(f"Betrieb (0-{len(available_buildings)}): ", 0, len(available_buildings))
        if choice == 0:
            return
        building = available_buildings[choice - 1]
        recipe = PRODUCTION_RECIPES.get(building.id)
        if recipe is None:
            return
        sold_pct = self._total_building_share_percent(city_name, building.id)
        free_pct = max(0.0, MAX_BUILDING_SHARE_PERCENT - sold_pct)
        if free_pct < 1.0:
            print("Keine freien Anteile mehr.")
            return
        price_per_pct = self._share_price_per_percent(city_name, building)
        max_by_money = int(player.money // max(1, price_per_pct))
        max_pct = int(min(free_pct, max_by_money, 40))
        if max_pct <= 0:
            print("Nicht genug Mark fuer Anteilskauf.")
            return
        pct = self._ask_int(f"Anteil kaufen in % (1-{max_pct}): ", 1, max_pct)
        cost = int(round(pct * price_per_pct))
        if cost > player.money:
            print("Nicht genug Mark.")
            return
        player.money -= cost
        city.treasury += int(round(cost * 0.45))
        new_pct = self._player_building_share_percent(player, city_name, building.id) + pct
        self._set_player_building_share_percent(player, city_name, building.id, new_pct)
        self._add_player_city_influence(player, city_name, pct * INFLUENCE_PER_SHARE_PURCHASE)
        print(
            f"Anteile gekauft: {pct}% an {recipe.name} fuer {cost} Mark. "
            f"Ihr Anteil: {self._player_building_share_percent(player, city_name, building.id):.1f}%"
        )

    def _bailout_city(self, player: Player, city_name: str) -> None:
        city = self._city_economy(city_name)
        influence = self._player_city_influence(player, city_name)
        if influence < MIN_BAILOUT_INFLUENCE:
            print(
                f"Zu wenig Einfluss in {city_name}. Benoetigt: {MIN_BAILOUT_INFLUENCE:.1f}, "
                f"vorhanden: {influence:.1f}."
            )
            return
        if player.money < BAILOUT_MIN_AMOUNT:
            print(f"Mindestens {BAILOUT_MIN_AMOUNT} Mark fuer Rettungsfonds noetig.")
            return
        amount = self._ask_int(f"Rettungsfonds einzahlen ({BAILOUT_MIN_AMOUNT}-{player.money}): ", BAILOUT_MIN_AMOUNT, player.money)
        rescue_bonus = min(0.60, influence / 200.0)
        treasury_gain = int(round(amount * (1.0 + rescue_bonus)))
        player.money -= amount
        city.treasury += treasury_gain
        self._add_player_city_influence(player, city_name, -BAILOUT_INFLUENCE_COST)
        post_status = "stabilisiert" if city.treasury >= CITY_RECOVERY_TARGET else "weiter kritisch"
        print(
            f"Rettungsfonds: {amount} Mark investiert, Stadtkasse +{treasury_gain}. "
            f"Status: {post_status} ({city.treasury})."
        )
        player.chronicle.append(
            f"ANNO {self.current_year}: Rettungsfonds fuer {city_name} ({amount} Mark, Effekt {treasury_gain})."
        )

    def _world_economy_menu(self, player: Player) -> None:
        while True:
            print()
            print("=== Weltwirtschaft ===")
            for idx, city_name in enumerate(CITIES, start=1):
                city = self._city_economy(city_name)
                influence = self._player_city_influence(player, city_name)
                status = "BANKROTT" if self._city_is_bankrupt(city_name) else "stabil"
                print(
                    f"{idx}) {city_name:10} | Betriebe {len(city.buildings):>2} | "
                    f"Stadtkasse {city.treasury:>6} | {status:8} | Einfluss {influence:>5.1f}"
                )
            print("0) Zurueck")
            choice = self._ask_int(f"Stadt waehlen (0-{len(CITIES)}): ", 0, len(CITIES))
            if choice == 0:
                return
            city_name = CITIES[choice - 1]
            while True:
                self._show_city_economy(city_name, player)
                print("1) Anteile kaufen  2) Rettungsfonds  3) Preisanalyse  4) Zurueck")
                action = self._ask_int("Auswahl: ", 1, 4)
                if action == 1:
                    self._buy_city_shares_menu(player, city_name)
                elif action == 2:
                    self._bailout_city(player, city_name)
                elif action == 3:
                    self._show_price_breakdown(city_name)
                else:
                    break

    def _preferred_export_dir(self) -> Path:
        fallback = self.save_dir / "exports"
        is_android = ("ANDROID_ARGUMENT" in os.environ) or (sys.platform == "android")
        if not is_android:
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

    def _export_csv_report(self, player: Player) -> Path | None:
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
                    value: Any,
                    unit: str = "",
                    note: str = "",
                ) -> None:
                    writer.writerow([section, entity, subentity, key, value, unit, note])

                row("snapshot", "game", "", "year", self.current_year)
                row("snapshot", "game", "", "month", self.current_month)
                row("snapshot", "game", "", "sea_state", self.current_sea_state)
                row("snapshot", "game", "", "source_player", player.name)
                row("atheria", "macro", "", "global_growth", f"{self.economy_state.global_growth:.4f}")
                row("atheria", "macro", "", "global_price_level", f"{self.economy_state.global_price_level:.4f}")
                row("atheria", "macro", "", "resource_scarcity", f"{self.economy_state.resource_scarcity:.4f}")

                for city_name in CITIES:
                    city = self._city_economy(city_name)
                    self._city_health_profile(city_name)
                    row("city", city_name, "", "treasury", city.treasury, "Mark")
                    row("city", city_name, "", "bankrupt", int(self._city_is_bankrupt(city_name)))
                    row("city", city_name, "", "building_count", len(city.buildings), "count")
                    row("city", city_name, "", "disease_pressure", f"{city.disease_pressure:.4f}")
                    row("city", city_name, "", "disease_cases", city.disease_cases, "citizens")
                    row("city", city_name, "", "child_survival_rate", f"{city.child_survival_rate:.4f}")
                    row("city", city_name, "", "doctor_coverage", f"{city.doctor_coverage:.4f}")
                    prices = self._market_prices(city_name)
                    for good_name in self._active_good_names():
                        stock = city.inventory.get(good_name, 0)
                        row("city_inventory", city_name, good_name, "stock", stock, "units")
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
                            row("building", city_name, f"{idx}", "upkeep", max(0, int(recipe.upkeep)), "Mark")

                for npc in self.npcs:
                    row("npc", npc.name, "", "city", npc.city)
                    row("npc", npc.name, "", "money", npc.money, "Mark")
                    row("npc", npc.name, "", "ship", npc.ship.display_name)
                    row("npc", npc.name, "", "cargo_total", npc.ship.total_cargo, "units")
                    for good_name in self._active_good_names():
                        qty = npc.ship.cargo.get(good_name, 0)
                        if qty > 0:
                            row("npc_cargo", npc.name, good_name, "qty", qty, "units")

                for p in self.players:
                    city_prices = self._market_prices(p.city)
                    row("player", p.name, "", "city", p.city)
                    row("player", p.name, "", "money", p.money, "Mark")
                    row("player", p.name, "", "debt", p.debt, "Mark")
                    row("player", p.name, "", "reputation", p.reputation)
                    row("player", p.name, "", "age", p.age, "years")
                    row("player", p.name, "", "children", p.children, "count")
                    row("player", p.name, "", "children_limit", max_children_for_year(self.current_year), "count")
                    row("player", p.name, "", "net_worth", self._net_worth(p, city_prices), "Mark")
                    for city_name, score in p.city_influence.items():
                        row("player_influence", p.name, city_name, "score", f"{float(score):.2f}")
                    for mission_key, mission_data in p.missions.items():
                        state = mission_data.get("state", "inactive") if isinstance(mission_data, dict) else "inactive"
                        row("player_mission", p.name, mission_key, "state", state)
                    for city_name, share_map in p.building_shares.items():
                        if not isinstance(share_map, dict):
                            continue
                        for recipe_id, share_pct in share_map.items():
                            recipe = PRODUCTION_RECIPES.get(recipe_id)
                            row(
                                "player_share",
                                p.name,
                                f"{city_name}:{recipe_id}",
                                "share_pct",
                                f"{float(share_pct):.2f}",
                                "%",
                                recipe.name if recipe else recipe_id,
                            )
                    building_quests = p.missions.get("building_quests", {})
                    if isinstance(building_quests, dict):
                        for recipe_id, quest_data in building_quests.items():
                            if not isinstance(quest_data, dict):
                                continue
                            recipe = PRODUCTION_RECIPES.get(recipe_id)
                            recipe_name = recipe.name if recipe else recipe_id
                            row(
                                "player_building_quest",
                                p.name,
                                recipe_id,
                                "recipe_name",
                                recipe_name,
                            )
                            row(
                                "player_building_quest",
                                p.name,
                                recipe_id,
                                "tier",
                                max(0, int(quest_data.get("tier", 0))),
                                "of_8",
                            )
                            row(
                                "player_building_quest",
                                p.name,
                                recipe_id,
                                "progress",
                                max(0, int(quest_data.get("progress", 0))),
                                "units",
                            )
                            row(
                                "player_building_quest",
                                p.name,
                                recipe_id,
                                "state",
                                str(quest_data.get("state", "inactive")),
                            )
                    for idx, ship in enumerate(p.ships, start=1):
                        row("player_ship", p.name, f"{idx}", "name", ship.display_name)
                        row("player_ship", p.name, f"{idx}", "city", ship.city)
                        row("player_ship", p.name, f"{idx}", "cargo_capacity", ship.cargo_capacity, "units")
                        row("player_ship", p.name, f"{idx}", "cargo_total", ship.total_cargo, "units")
                        row("player_ship", p.name, f"{idx}", "hull", ship.hull, "%")
                        row("player_ship", p.name, f"{idx}", "rigging", ship.rigging, "%")
                        row("player_ship", p.name, f"{idx}", "cannons", ship.cannons, "count")
            return path
        except OSError:
            return None

    def run(self) -> None:
        self._print_banner()
        loaded = False
        if self._has_any_slot_save() and self._ask_yes_no("Begonnenes Spiel fortsetzen? (j/n): "):
            loaded = self._load_game_menu()
        elif self.legacy_save_path.exists() and self._ask_yes_no("Legacy-Spielstand laden? (j/n): "):
            loaded = self._load_game(self.legacy_save_path)
            if loaded:
                print(f"Legacy-Spielstand geladen: {self.legacy_save_path.name}")
            else:
                print("Legacy-Spielstand ungueltig.")

        if not loaded:
            self._start_new_game()

        while self.players:
            self.current_sea_state = self.rng.choice(SEA_STATES)
            self._refresh_economy_for_year()
            world_tick = self._run_world_month_tick()
            print()
            print(f"ANNO {self.current_year} {MONTHS[self.current_month - 1]} - {self.current_sea_state}")
            print(f"Atheria-Wirtschaft: {self.economy_state.summary}")
            print(
                f"Weltmarkt: Produktion aktiv {world_tick.get('producing_buildings', 0)} Betriebe | "
                f"NPC-Deals {world_tick.get('npc_trades', 0)} von {len(self.npcs)} | "
                f"Bankrott-Staedte {world_tick.get('cities_bankrupt', 0)} | "
                f"Krankheitsfaelle {world_tick.get('disease_cases', 0)}"
            )
            print("=" * 60)
            for player in self.players:
                self._sync_player_goods(player)
                if player.alive:
                    self._play_turn(player)
            self.current_month += 1
            if self.current_month > 12:
                self.current_month = 1
                self.current_year += 1
            self.players = [p for p in self.players if p.alive]
            if not self.players:
                break
            if not self._ask_yes_no("Naechster Monat beginnen? (j/n): "):
                break

        self._show_final_ranking()

    def _print_banner(self) -> None:
        print("=" * 60)
        print("H A N S E  -  Python Portierung")
        print("Markt | Hafen | Kaper-Risiko | Schuldturm | Chronik")
        print("=" * 60)

    def _refresh_economy_for_year(self) -> None:
        economy_year = self.current_year + (self.current_month - 1) / 12.0
        self.economy_state = self.economy_engine.for_year(
            year=economy_year,
            sea_state=self.current_sea_state,
            goods=self._active_goods().keys(),
            cities=CITIES,
        )
        self._ensure_world_state()
        self._market_cache.clear()
        self._market_breakdown_cache.clear()
        self.city_dashboard_cache.clear()

    def _start_new_game(self) -> None:
        self._ensure_world_state(reset_world=True, reset_npcs=True)
        count = self._ask_int(
            f"Spielerzahl 1-{MAX_PLAYERS} moeglich. Anzahl: ",
            1,
            MAX_PLAYERS,
        )
        self.players = []
        for idx in range(1, count + 1):
            print()
            print(f"Spieler {idx}")
            name = self._ask_name("Ihren Namen bitte: ")
            gender = self._ask_gender("Maennlich oder Weiblich? (m/w): ")
            city = self._choose_city()
            ship = Ship(city=city, cargo={good: 0 for good in self._active_good_names()})
            player = Player(
                name=name,
                gender=gender,
                city=city,
                money=STARTING_CASH,
                debt=STARTING_DEBT,
                reputation=STARTING_REPUTATION,
                age=STARTING_AGE + self.rng.randint(0, 4),
                ships=[ship],
            )
            self._init_missions(player)
            self._update_missions_monthly(player)
            player.chronicle.append(f"ANNO {self.current_year}: Kontor in {city} geoeffnet.")
            self.players.append(player)

    def _slot_path(self, slot: int) -> Path:
        return self.save_dir / f"slot_{slot:02d}.json"

    def _has_any_slot_save(self) -> bool:
        return any(self._slot_path(slot).exists() for slot in range(1, SAVE_SLOT_COUNT + 1))

    def _slot_summary(self, slot: int) -> str:
        path = self._slot_path(slot)
        if not path.exists():
            return "(leer)"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            year = raw.get("year", "?")
            month_value = raw.get("month")
            month_name = None
            if isinstance(month_value, (int, float, str)):
                try:
                    month_index = int(month_value)
                except ValueError:
                    month_index = 0
                if 1 <= month_index <= 12:
                    month_name = MONTHS[month_index - 1]
            players = raw.get("players", [])
            names = [str(entry.get("name", "?")) for entry in players[:3] if isinstance(entry, dict)]
            names_text = ", ".join(names) if names else "-"
            if isinstance(players, list) and len(players) > 3:
                names_text += ", ..."
            saved_at = str(raw.get("saved_at", "ohne Zeitstempel"))
            if month_name:
                return f"ANNO {year} {month_name} | Spieler {len(players)} ({names_text}) | {saved_at}"
            return f"ANNO {year} | Spieler {len(players)} ({names_text}) | {saved_at}"
        except (OSError, ValueError, TypeError, KeyError):
            return "(defekt)"

    def _load_game_menu(self) -> bool:
        while True:
            print()
            print("Speicherstaende:")
            for slot in range(1, SAVE_SLOT_COUNT + 1):
                marker = "*" if slot == self.active_slot else " "
                print(f"{marker} {slot}) {self._slot_summary(slot)}")
            print("0) Abbrechen")

            slot_choice = self._ask_int(f"Slot laden (0-{SAVE_SLOT_COUNT}): ", 0, SAVE_SLOT_COUNT)
            if slot_choice == 0:
                return False

            path = self._slot_path(slot_choice)
            if not path.exists():
                print("Dieser Slot ist leer.")
                continue
            if self._load_game(path, slot_choice):
                print(f"Spiel geladen aus Slot {slot_choice}.")
                return True
            print("Spielstand ungueltig oder nicht lesbar.")

    def _save_game_menu(self) -> None:
        while True:
            print()
            print("Savegame-Menue:")
            for slot in range(1, SAVE_SLOT_COUNT + 1):
                marker = "*" if slot == self.active_slot else " "
                print(f"{marker} {slot}) {self._slot_summary(slot)}")
            print("0) Abbrechen")

            slot_choice = self._ask_int(f"Slot speichern (0-{SAVE_SLOT_COUNT}): ", 0, SAVE_SLOT_COUNT)
            if slot_choice == 0:
                return
            if self._save_game(self._slot_path(slot_choice), slot_choice):
                print(f"Spiel in Slot {slot_choice} gespeichert.")
                return
            print("Speichern fehlgeschlagen.")

    def _load_game(self, path: Path, slot: int | None = None) -> bool:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.current_year = int(raw["year"])
            self.current_month = int(raw.get("month", STARTING_MONTH))
            self.current_month = max(1, min(12, self.current_month))
            self.current_sea_state = str(raw.get("sea_state", "bewegte See"))
            self.players = [Player.from_dict(entry) for entry in raw["players"]]
            for player in self.players:
                self._sync_player_goods(player)
                self._init_missions(player)
                self._ensure_player_child_ages(player)
            econ_engine_data = raw.get("atheria_economy_engine")
            if isinstance(econ_engine_data, dict):
                self.economy_engine.load_dict(econ_engine_data)
            econ_state_data = raw.get("atheria_economy_state")
            if isinstance(econ_state_data, dict):
                self.economy_state = EconomyState.from_dict(econ_state_data)
            else:
                self.economy_state = self.economy_engine.for_year(
                    year=self.current_year,
                    sea_state=self.current_sea_state,
                    goods=self._active_goods().keys(),
                    cities=CITIES,
                )
            world_data = raw.get("world_economy")
            if isinstance(world_data, dict):
                self.world_economy = WorldEconomy.from_dict(world_data)
            else:
                self.world_economy = WorldEconomy()

            npcs_data = raw.get("npcs")
            if isinstance(npcs_data, list):
                loaded_npcs = [NPCTrader.from_dict(entry) for entry in npcs_data if isinstance(entry, dict)]
                self.npcs = loaded_npcs
            else:
                self.npcs = []

            self._ensure_world_state(
                reset_world=not isinstance(world_data, dict),
                reset_npcs=not isinstance(npcs_data, list),
            )
            self._market_cache.clear()
            self._market_breakdown_cache.clear()
            self.city_dashboard_cache.clear()
            self.active_slot = slot
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _save_game(self, path: Path, slot: int | None = None) -> bool:
        self._ensure_world_state()
        payload = {
            "save_version": 2,
            "year": self.current_year,
            "month": self.current_month,
            "sea_state": self.current_sea_state,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "players": [player.to_dict() for player in self.players],
            "atheria_economy_engine": self.economy_engine.to_dict(),
            "atheria_economy_state": self.economy_state.to_dict(),
            "world_economy": self.world_economy.to_dict(),
            "npcs": [npc.to_dict() for npc in self.npcs],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.active_slot = slot
            return True
        except OSError:
            return False

    def _play_turn(self, player: Player) -> None:
        print()
        print(f"--- {player.name} ({self._title_for(player)}) in {player.city} ---")
        self._resolve_investments(player)
        if not player.alive:
            return

        if player.turns_in_debt_tower > 0:
            player.turns_in_debt_tower -= 1
            print(f"{player.name} sitzt im Schuldturm... ({player.turns_in_debt_tower} Monat(e) verbleibend)")
            player.chronicle.append(
                f"ANNO {self.current_year}: {player.name} sitzt im Schuldturm ({MONTHS[self.current_month - 1]})."
            )
            self._end_of_turn(player)
            return

        if player.auto_enabled:
            self._auto_take_turn(player)
            return

        while True:
            print()
            print(
                "1) Status  2) Markt  3) Reise  4) Hafen  5) Investition  6) Runde Ende  "
                "7) Speichern  8) Missionen  9) Weltwirtschaft  10) CSV-Export  "
                "11) Auto ein/aus  12) Auto-Policy  13) Auto jetzt (1 Monat)"
            )
            choice = self._ask_int("Auswahl: ", 1, 13)
            if choice == 1:
                self._show_status(player)
            elif choice == 2:
                self._market_menu(player)
            elif choice == 3:
                self._travel_menu(player)
                if not player.alive:
                    break
            elif choice == 4:
                self._harbor_menu(player)
            elif choice == 5:
                self._investment_menu(player)
            elif choice == 6:
                break
            elif choice == 7:
                self._save_game_menu()
            elif choice == 8:
                self._missions_menu(player)
            elif choice == 9:
                self._world_economy_menu(player)
            elif choice == 10:
                csv_path = self._export_csv_report(player)
                if csv_path:
                    print(f"CSV exportiert: {csv_path}")
                else:
                    print("CSV-Export fehlgeschlagen.")
            elif choice == 11:
                player.auto_enabled = not bool(player.auto_enabled)
                print(f"Auto-Modus {'aktiviert' if player.auto_enabled else 'deaktiviert'}.")
            elif choice == 12:
                self._auto_config_menu(player)
            elif choice == 13:
                self._auto_take_turn(player)
                return
        if player.alive:
            self._end_of_turn(player)

    def _default_auto_policy(self) -> Dict[str, Any]:
        return {
            "risk": 50,
            "reserve_mark": 1400,
            "invest_mode": "balanced",
            "focus_cities": {city_name: True for city_name in CITIES},
        }

    def _player_auto_policy(self, player: Player) -> Dict[str, Any]:
        policy = dict(self._default_auto_policy())
        raw = player.auto_policy if isinstance(player.auto_policy, dict) else {}
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
        if not any(bool(v) for v in focus_map.values()):
            focus_map[CITIES[0]] = True
        policy["focus_cities"] = focus_map
        player.auto_policy = dict(policy)
        return policy

    def _auto_route_min_score(self, policy: Dict[str, Any]) -> int:
        risk = max(0, min(100, int(policy.get("risk", 50))))
        return max(CLI_AUTO_POLICY_MIN_ROUTE_SCORE, min(260, int(round(220 - (risk * 2.0)))))

    def _auto_trade_budget_share(self, policy: Dict[str, Any]) -> float:
        risk = max(0, min(100, int(policy.get("risk", 50))))
        return _clamp(0.35 + (risk / 200.0), 0.35, 0.85)

    def _auto_player_reserve(self, player: Player, policy: Dict[str, Any]) -> int:
        base = max(0, int(policy.get("reserve_mark", 1400)))
        fleet_part = len(player.ships) * CLI_AUTO_RESERVE_PER_SHIP_MARK
        return max(base, 500 + fleet_part)

    def _auto_focus_targets(self, origin_city: str, policy: Dict[str, Any]) -> List[str]:
        focus_map = policy.get("focus_cities", {})
        targets = [
            city_name
            for city_name in CITIES
            if city_name != origin_city and bool(focus_map.get(city_name, False))
        ]
        if not targets:
            targets = [city_name for city_name in CITIES if city_name != origin_city]
        return targets

    def _auto_config_menu(self, player: Player) -> None:
        policy = self._player_auto_policy(player)
        while True:
            print()
            print("=== Auto-Policy ===")
            print(f"Auto aktiv: {'ja' if player.auto_enabled else 'nein'}")
            print(f"1) Risiko: {policy['risk']}")
            print(f"2) Reserve: {policy['reserve_mark']} Mark")
            print(f"3) Investitionsstil: {policy['invest_mode']}")
            print("4) Fokus-Staedte")
            print("0) Zurueck")
            choice = self._ask_int("Auswahl: ", 0, 4)
            if choice == 0:
                player.auto_policy = dict(policy)
                return
            if choice == 1:
                policy["risk"] = self._ask_int("Risiko (0-100): ", 0, 100)
            elif choice == 2:
                max_reserve = max(50_000, max(0, int(player.money)) + 50_000)
                policy["reserve_mark"] = self._ask_int(
                    f"Reserve (0-{max_reserve}): ",
                    0,
                    max_reserve,
                )
            elif choice == 3:
                options = ["conservative", "balanced", "aggressive"]
                current = options.index(policy["invest_mode"]) if policy["invest_mode"] in options else 1
                print(f"Aktuell: {policy['invest_mode']}")
                print("1) conservative  2) balanced  3) aggressive")
                mode_idx = self._ask_int("Stil: ", 1, 3) - 1
                policy["invest_mode"] = options[mode_idx] if mode_idx >= 0 else options[current]
            elif choice == 4:
                while True:
                    print()
                    print("Fokus-Staedte (1=aktiv, 0=inaktiv):")
                    for idx, city_name in enumerate(CITIES, start=1):
                        state = 1 if bool(policy["focus_cities"].get(city_name, True)) else 0
                        print(f"{idx}) {city_name:10} [{state}]")
                    print("0) Zurueck")
                    city_choice = self._ask_int(f"Stadt toggeln (0-{len(CITIES)}): ", 0, len(CITIES))
                    if city_choice == 0:
                        break
                    city_name = CITIES[city_choice - 1]
                    policy["focus_cities"][city_name] = not bool(policy["focus_cities"].get(city_name, True))
                    if not any(bool(v) for v in policy["focus_cities"].values()):
                        policy["focus_cities"][city_name] = True
                        print("Mindestens eine Fokus-Stadt muss aktiv bleiben.")
            player.auto_policy = dict(policy)

    def _auto_choose_route_with_policy(
        self,
        player: Player,
        ship: Ship,
        policy: Dict[str, Any],
    ) -> Tuple[str, List[Tuple[str, int, int]], int] | None:
        if ship.is_at_sea:
            return None
        origin = ship.city
        origin_prices = self._market_prices(origin)
        discount = self._city_discount(player, origin)
        min_score = self._auto_route_min_score(policy)
        budget_share = self._auto_trade_budget_share(policy)
        reserve = self._auto_player_reserve(player, policy)
        best_target = ""
        best_plan: List[Tuple[str, int, int]] = []
        best_profit = 0
        best_score = -10**9
        for target in self._auto_focus_targets(origin, policy):
            distance = abs(CITIES.index(origin) - CITIES.index(target)) + 1
            travel_cost = 60 + distance * 25
            available = max(0, player.money - reserve - travel_cost)
            budget = max(0, int(available * budget_share))
            capacity = ship.cargo_space_left
            if budget <= 0 or capacity <= 0:
                continue
            target_prices = self._market_prices(target)
            opportunities: List[Tuple[float, int, int, int, str]] = []
            for good_name in self._active_good_names():
                buy_price = origin_prices.get(good_name, 0)
                if buy_price <= 0:
                    continue
                if discount > 0:
                    buy_price = max(1, int(round(buy_price * (1 - discount))))
                sell_price = target_prices.get(good_name, 0)
                margin = sell_price - buy_price
                if margin <= 0:
                    continue
                stock = self._city_inventory_qty(origin, good_name)
                available_stock = max(0, stock - 10)
                if available_stock <= 0:
                    continue
                roi = margin / max(1, buy_price)
                opportunities.append((roi, margin, buy_price, available_stock, good_name))
            opportunities.sort(reverse=True)
            plan: List[Tuple[str, int, int]] = []
            expected_profit = 0
            for _roi, margin, buy_price, available_stock, good_name in opportunities:
                if capacity <= 0 or budget < buy_price:
                    break
                qty = min(capacity, budget // buy_price, available_stock)
                if qty <= 0:
                    continue
                plan.append((good_name, int(qty), int(buy_price)))
                budget -= int(qty) * int(buy_price)
                capacity -= int(qty)
                expected_profit += int(qty) * int(margin)
            if not plan:
                continue
            score = expected_profit - travel_cost
            if score > best_score:
                best_target = target
                best_plan = plan
                best_profit = expected_profit
                best_score = score
        if not best_plan or best_score < min_score:
            return None
        return best_target, best_plan, best_profit

    def _auto_execute_trade_with_policy(
        self,
        player: Player,
        ship: Ship,
        target: str,
        plan: List[Tuple[str, int, int]],
    ) -> bool:
        origin = ship.city
        loaded = 0
        spent = 0
        for good_name, desired_qty, buy_price in plan:
            if ship.cargo_space_left <= 0:
                break
            affordable = player.money // max(1, buy_price)
            want_qty = min(int(desired_qty), ship.cargo_space_left, affordable)
            if want_qty <= 0:
                continue
            bought = self._city_take_inventory(origin, good_name, want_qty)
            if bought <= 0:
                continue
            cost = bought * max(1, buy_price)
            player.money -= cost
            player.cargo[good_name] = player.cargo.get(good_name, 0) + bought
            loaded += bought
            spent += cost

        if loaded <= 0:
            return False

        distance = abs(CITIES.index(origin) - CITIES.index(target)) + 1
        travel_cost = 60 + distance * 25
        if player.money < travel_cost:
            return False
        player.money -= travel_cost
        player.city = target
        self._record_city_visit(player, target)
        player.chronicle.append(f"ANNO {self.current_year}: Auto-Route {origin}->{target}.")
        self._resolve_travel_risk(player, origin, target)
        if not player.alive:
            return True

        prices = self._market_prices(target)
        revenue = 0
        sold_units = 0
        for good_name in self._active_good_names():
            qty = player.cargo.get(good_name, 0)
            if qty <= 0:
                continue
            unit_price = prices.get(good_name, 0)
            if unit_price <= 0:
                continue
            revenue += qty * unit_price
            sold_units += qty
            player.cargo[good_name] = 0
            self._city_add_inventory(target, good_name, qty)
            self._record_hanse_delivery(player, target, good_name, qty)
            self._record_trade_for_missions(player, good_name, qty)
        player.money += revenue
        if sold_units > 0:
            player.reputation = min(200, player.reputation + 1)
            print(f"Auto-Handel: Route {origin}->{target}, Ladung {sold_units}, Gewinn {revenue - spent - travel_cost} Mark.")
        return True

    def _auto_invest_with_policy(self, player: Player, policy: Dict[str, Any]) -> None:
        mode = str(policy.get("invest_mode", "balanced")).strip().lower()
        reserve = self._auto_player_reserve(player, policy)
        if mode == "conservative":
            return

        city = self._city_economy(player.city)
        building_candidates: List[Tuple[int, int, Building]] = []
        for building in city.buildings:
            if RECIPE_UNLOCK_CENTURY.get(building.id, 14) > self._current_century():
                continue
            free_pct = max(0.0, MAX_BUILDING_SHARE_PERCENT - self._total_building_share_percent(player.city, building.id))
            if free_pct < 5.0:
                continue
            pool = self._building_dividend_pool(player.city, building.id)
            price_per_pct = self._share_price_per_percent(player.city, building)
            if price_per_pct <= 0:
                continue
            building_candidates.append((pool, -price_per_pct, building))
        building_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        max_share_buys = 1 if mode == "balanced" else 2
        for _pool, _neg_price, building in building_candidates[:max_share_buys]:
            price_per_pct = self._share_price_per_percent(player.city, building)
            pct = 5
            cost = pct * price_per_pct
            if player.money - cost < reserve:
                continue
            player.money -= cost
            city.treasury += int(round(cost * 0.45))
            new_pct = self._player_building_share_percent(player, player.city, building.id) + pct
            self._set_player_building_share_percent(player, player.city, building.id, new_pct)
            self._add_player_city_influence(player, player.city, pct * INFLUENCE_PER_SHARE_PURCHASE)
            recipe = PRODUCTION_RECIPES.get(building.id)
            label = recipe.name if recipe else building.id
            print(f"Auto-Invest: +{pct}% Anteil an {label} in {player.city}.")

        if mode == "aggressive":
            surplus = player.money - reserve
            if surplus >= 4000:
                amount = max(1500, min(int(surplus * 0.25), surplus))
                player.money -= amount
                player.market_investments.append(Investment(amount=amount, turns_left=1, risk=2))
                print(f"Auto-Invest: Markteinsatz {amount} Mark (balanced risk).")

    def _auto_take_turn(self, player: Player) -> None:
        if not player.alive:
            return
        policy = self._player_auto_policy(player)
        ship = player.ship

        reserve = self._auto_player_reserve(player, policy)
        while ship.hull < 90:
            amount = min(10, 100 - ship.hull)
            cost = amount * 16
            if player.money - cost < reserve:
                break
            ship.hull += amount
            player.money -= cost
        while ship.rigging < 90:
            amount = min(10, 100 - ship.rigging)
            cost = amount * 12
            if player.money - cost < reserve:
                break
            ship.rigging += amount
            player.money -= cost

        current_prices = self._market_prices(player.city)
        sold_revenue = 0
        for good_name in self._active_good_names():
            qty = player.cargo.get(good_name, 0)
            if qty <= 0:
                continue
            unit_price = current_prices.get(good_name, 0)
            sold_revenue += qty * unit_price
            player.cargo[good_name] = 0
            self._city_add_inventory(player.city, good_name, qty)
            self._record_hanse_delivery(player, player.city, good_name, qty)
            self._record_trade_for_missions(player, good_name, qty)
        if sold_revenue > 0:
            player.money += sold_revenue
            player.reputation = min(200, player.reputation + 1)
            print(f"Auto-Handel: Lager aufgeloest in {player.city}, Erlos {sold_revenue} Mark.")

        route = self._auto_choose_route_with_policy(player, ship, policy)
        if route:
            target, plan, _profit = route
            self._auto_execute_trade_with_policy(player, ship, target, plan)
        else:
            print("Auto-Handel: Keine rentable Route fuer die aktuelle Policy.")

        if player.alive:
            self._auto_invest_with_policy(player, policy)
            self._end_of_turn(player)

    def _show_status(self, player: Player) -> None:
        prices = self._market_prices(player.city)
        cargo_value = sum(prices.get(g, 0) * q for g, q in player.cargo.items())
        net = self._net_worth(player, prices)
        print("-" * 60)
        print(f"{player.name} | Titel: {self._title_for(player)} | Alter: {player.age}")
        print(f"Stadt: {player.city} | Zustand: Rumpf {player.ship.hull}% / Takelage {player.ship.rigging}%")
        print(f"Mark: {player.money} | Schulden: {player.debt} | Ruf: {player.reputation}")
        print(f"Ladungen: {player.total_cargo}/{player.ship.cargo_capacity} | Warenwert: {cargo_value}")
        print(f"Gesamtwert: {net}")
        influence = self._player_city_influence(player, player.city)
        print(f"Politischer Einfluss in {player.city}: {influence:.1f}")
        print(
            f"Atheria: Wachstum {self.economy_state.global_growth:.2f} | "
            f"Preisniveau {self.economy_state.global_price_level:.2f} | "
            f"Knappheit {self.economy_state.resource_scarcity:.2f}"
        )
        city_market = self._city_economy(player.city)
        debug_goods = [good_name for good_name in ("Getreide", "Bier") if good_name in self._active_goods()]
        if debug_goods:
            parts = [
                f"{good_name}: {city_market.inventory.get(good_name, 0)} (x{city_market.scarcity_factor(good_name):.2f})"
                for good_name in debug_goods
            ]
            print("Stadtbestand: " + " | ".join(parts))
        print("Waren an Bord:")
        for good_name in self._active_good_names():
            qty = player.cargo.get(good_name, 0)
            print(f"  {good_name:14} {qty:>4}  Preis {prices.get(good_name, 0):>4}")
        if player.market_investments:
            print("Laufende Investitionen:")
            for inv in player.market_investments:
                print(f"  {inv.amount} Mark | Rest {inv.turns_left} Runde(n) | Risiko {inv.risk}")
        print("-" * 60)

    def _market_menu(self, player: Player) -> None:
        while True:
            prices = self._market_prices(player.city)
            goods = self._active_good_names()
            print()
            print("           MARKT")
            for idx, good_name in enumerate(goods, start=1):
                city_stock = self._city_inventory_qty(player.city, good_name)
                print(
                    f"{idx}) {good_name:14} Preis {prices.get(good_name, 0):>4} | "
                    f"Bord {player.cargo.get(good_name, 0):>3} | Markt {city_stock:>3}"
                )
            back_idx = len(goods) + 1
            print(f"{back_idx}) Zurueck")
            action = self._ask_int(f"1-{back_idx} Kaufen/Verkaufen, {back_idx} Zurueck: ", 1, back_idx)
            if action == back_idx:
                return
            good_name = goods[action - 1]
            if self._ask_yes_no(f"{good_name} kaufen? (j/n fuer verkaufen): "):
                self._buy_goods(player, good_name, prices.get(good_name, 0))
            else:
                self._sell_goods(player, good_name, prices.get(good_name, 0))

    def _buy_goods(self, player: Player, good_name: str, price: int) -> None:
        if price <= 0:
            print("Diese Ware ist aktuell nicht handelbar.")
            return
        city_stock = self._city_inventory_qty(player.city, good_name)
        if city_stock <= 0:
            print("Der Markt ist leer.")
            return
        discount = self._city_discount(player, player.city)
        if discount > 0:
            price = max(1, int(round(price * (1 - discount))))
        max_by_money = player.money // price
        max_qty = min(max_by_money, player.cargo_space_left, city_stock)
        if max_qty <= 0:
            print("Nicht genug Mark oder kein Frachtraum frei.")
            return
        qty = self._ask_int(f"Anzahl kaufen (1-{max_qty}): ", 1, max_qty)
        bought = self._city_take_inventory(player.city, good_name, qty)
        if bought <= 0:
            print("Der Markt ist in diesem Monat erschoepft.")
            return
        cost = bought * price
        player.money -= cost
        player.cargo[good_name] = player.cargo.get(good_name, 0) + bought
        player.reputation = min(200, player.reputation + 1)
        print(f"Gekauft: {bought} {good_name} fuer {cost} Mark.")

    def _sell_goods(self, player: Player, good_name: str, price: int) -> None:
        if price <= 0:
            print("Diese Ware ist aktuell nicht handelbar.")
            return
        stock = player.cargo.get(good_name, 0)
        if stock <= 0:
            print("Keine Ware auf Lager.")
            return
        qty = self._ask_int(f"Anzahl verkaufen (1-{stock}): ", 1, stock)
        revenue = qty * price
        player.cargo[good_name] = max(0, player.cargo.get(good_name, 0) - qty)
        self._city_add_inventory(player.city, good_name, qty)
        player.money += revenue
        player.reputation = min(200, player.reputation + 1)
        print(f"Verkauft: {qty} {good_name} fuer {revenue} Mark.")
        self._record_hanse_delivery(player, player.city, good_name, qty)
        self._record_trade_for_missions(player, good_name, qty)

    def _travel_menu(self, player: Player) -> None:
        destinations = [city for city in CITIES if city != player.city]
        print()
        print("          HAFEN")
        for idx, city_name in enumerate(destinations, start=1):
            print(f"{idx}) {city_name}")
        choice = self._ask_int(f"Kontor in (1-{len(destinations)}): ", 1, len(destinations))
        target = destinations[choice - 1]

        distance = abs(CITIES.index(player.city) - CITIES.index(target)) + 1
        travel_cost = 60 + distance * 25
        if player.money < travel_cost:
            print("Nicht genug Mark fuer die Reise.")
            return
        player.money -= travel_cost
        old_city = player.city
        player.city = target
        self._record_city_visit(player, target)
        player.chronicle.append(f"ANNO {self.current_year}: Von {old_city} nach {target} gesegelt.")
        print(f"Eingetroffen: {target}. Reisekosten: {travel_cost} Mark.")
        self._resolve_travel_risk(player, old_city, target)

    def _resolve_travel_risk(self, player: Player, origin: str, target: str) -> None:
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
        mitigation = _clamp(
            (float(origin_city.hazard_mitigation) + float(target_city.hazard_mitigation)) / 2.0
            + (
                self._institution_level(origin_city, "hospital")
                + self._institution_level(target_city, "hospital")
                + self._institution_level(origin_city, "doctors")
                + self._institution_level(target_city, "doctors")
            )
            * 0.015,
            0.0,
            0.80,
        )
        risk = max(0.02, risk * (1.0 - mitigation * 0.70))
        if self.rng.random() < risk:
            hull_damage = self.rng.randint(5, 18)
            rig_damage = self.rng.randint(4, 14)
            player.ship.hull = max(0, player.ship.hull - hull_damage)
            player.ship.rigging = max(0, player.ship.rigging - rig_damage)
            print(f"Es war {self.current_sea_state}. Schaden: Rumpf -{hull_damage} / Takelage -{rig_damage}.")
            player.chronicle.append(
                f"ANNO {self.current_year}: Sturm auf See zwischen {origin} und {target}."
            )
        if self.rng.random() < risk / 1.8 and player.total_cargo > 0:
            lost_good = self.rng.choice([good for good, qty in player.cargo.items() if qty > 0])
            lost_qty = self.rng.randint(1, max(1, player.cargo[lost_good] // 2))
            player.cargo[lost_good] -= lost_qty
            player.reputation = max(0, player.reputation - 2)
            print(f"Kaperangriff! Verlust: {lost_qty} {lost_good}.")
            player.chronicle.append(
                f"ANNO {self.current_year}: Von Kaperflotte angegriffen, {lost_qty} {lost_good} verloren."
            )
        if player.ship.hull <= 0 or player.ship.rigging <= 0:
            player.alive = False
            player.chronicle.append(f"ANNO {self.current_year}: Schiffbruch auf See.")
            print("Das Schiff ist nicht mehr seetauglich. Das Handelshaus endet in den Fluten.")

    def _harbor_menu(self, player: Player) -> None:
        while True:
            print()
            print("Bauauftrag / Ausbesserung")
            print("1) Rumpf ausbessern")
            print("2) Takelage ausbessern")
            print("3) Neues Schiff kaufen")
            print("4) Aktives Schiff verkaufen")
            print("5) Zurueck")
            choice = self._ask_int("Auswahl: ", 1, 5)
            if choice == 5:
                return
            if choice == 1:
                self._repair_ship(player, part="hull")
            elif choice == 2:
                self._repair_ship(player, part="rigging")
            elif choice == 3:
                self._buy_ship(player)
            elif choice == 4:
                self._sell_ship(player)

    def _repair_ship(self, player: Player, part: str) -> None:
        if part == "hull":
            current = player.ship.hull
            label = "Rumpf"
            unit_cost = 16
        else:
            current = player.ship.rigging
            label = "Takelage"
            unit_cost = 12

        if current >= 100:
            print(f"{label} ist bereits bei 100%.")
            return

        missing = 100 - current
        affordable = player.money // unit_cost
        max_repair = min(missing, affordable)
        if max_repair <= 0:
            print("Nicht genug Mark fuer Ausbesserung.")
            return

        amount = self._ask_int(f"{label} verbessern um wieviel Prozent? (1-{max_repair}): ", 1, max_repair)
        cost = amount * unit_cost
        player.money -= cost
        if part == "hull":
            player.ship.hull += amount
        else:
            player.ship.rigging += amount
        print(f"{label} um {amount}% verbessert. Kosten: {cost} Mark.")

    def _buy_ship(self, player: Player) -> None:
        shipyard = self._active_shipyard()
        if not shipyard:
            print("Keine Schiffe verfuegbar.")
            return
        print("Schiffe:")
        for idx, (name, cap, val, cost) in enumerate(shipyard, start=1):
            print(f"{idx}) {name:12} Ladungen {cap:>3}  Kosten {cost:>5}")
        choice = self._ask_int(f"Schiff waehlen (1-{len(shipyard)}): ", 1, len(shipyard))
        name, cap, value, cost = shipyard[choice - 1]
        trade_in = int(player.ship.value * 0.35)
        final_cost = max(0, cost - trade_in)
        if player.money < final_cost:
            print(f"Nicht genug Mark. Benoetigt: {final_cost}")
            return
        if player.total_cargo > cap:
            print("Zu viel Ladung fuer das neue Schiff. Erst Ware verkaufen.")
            return
        player.money -= final_cost
        player.ship.name = name
        player.ship.cargo_capacity = cap
        player.ship.value = value
        player.ship.hull = max(player.ship.hull, 75)
        player.ship.rigging = max(player.ship.rigging, 75)
        print(f"Neues Schiff gekauft: {name}. Kosten nach Inzahlungnahme: {final_cost} Mark.")
        player.chronicle.append(f"ANNO {self.current_year}: {name} als neues Schiff erworben.")

    def _ship_sale_price(self, ship: Ship) -> int:
        condition = max(0.20, min(1.0, (ship.hull + ship.rigging) / 200.0))
        hull_value = int(ship.value * (0.32 + 0.38 * condition))
        cannon_value = int(ship.cannons * 0.35 * 500)
        return max(100, hull_value + cannon_value)

    def _sell_ship(self, player: Player) -> None:
        if len(player.ships) <= 1:
            print("Das letzte Schiff kann nicht verkauft werden.")
            return
        ship = player.ship
        if ship.is_at_sea:
            print("Schiff ist auf See und kann nicht verkauft werden.")
            return
        if ship.total_cargo > 0:
            print("Bitte erst die gesamte Ladung entladen/verkaufen.")
            return
        sale_value = self._ship_sale_price(ship)
        sold_name = ship.display_name
        del player.ships[player.active_ship_index]
        player.active_ship_index = max(0, min(player.active_ship_index, len(player.ships) - 1))
        player.money += sale_value
        player.city = player.ship.city
        print(f"Schiff verkauft: {sold_name} fuer {sale_value} Mark.")
        player.chronicle.append(f"ANNO {self.current_year}: {sold_name} verkauft ({sale_value} Mark).")

    def _investment_menu(self, player: Player) -> None:
        if player.money < 500:
            print("Mindestens 500 Mark fuer Investitionen noetig.")
            return
        amount = self._ask_int(f"Investition (500-{player.money}): ", 500, player.money)
        risk = self._ask_int("Risiko 1 (niedrig) bis 3 (hoch): ", 1, 3)
        turns = {1: 2, 2: 2, 3: 1}[risk]
        player.money -= amount
        player.market_investments.append(Investment(amount=amount, turns_left=turns, risk=risk))
        print(f"{amount} Mark investiert. Auszahlung in {turns} Runde(n).")

    def _missions_menu(self, player: Player) -> None:
        self._init_missions(player)
        self._update_fleet_synergy(player)
        self._update_route_master(player)
        self._update_arms_race(player)
        print()
        print("=== Missionen ===")
        month_index = self._month_index()

        mission = player.missions.get("hanse_privileg", {})
        state = mission.get("state", "inactive")
        print("1) Hanse-Privileg")
        if state == "active":
            delivered = int(mission.get("delivered", 0))
            target = int(mission.get("target", HANSE_PRIVILEG_QTY))
            city = mission.get("city", "?")
            remaining = max(0, int(mission.get("deadline", month_index)) - month_index)
            print(f"   Lieferziel: {delivered}/{target} {HANSE_PRIVILEG_GOOD} nach {city}")
            print(f"   Frist: {remaining} Monat(e)")
        elif state == "completed":
            city = mission.get("city", "?")
            print(f"   Abgeschlossen: -{int(HANSE_PRIVILEG_DISCOUNT * 100)}% Einkauf in {city}")
        elif state == "failed":
            print("   Gescheitert (Frist abgelaufen)")
        else:
            print("   Warte auf Knappheit (> 0.55).")

        mission = player.missions.get("fleet_synergy", {})
        state = mission.get("state", "inactive")
        print("2) Architekt der Synergie")
        counts = mission.get("counts", {})
        if counts:
            parts = [
                f"{name} {counts.get(name, 0)}/{FLEET_SYNERGY_REQUIRED}"
                for name, *_ in self._fleet_synergy_shipyard()
            ]
            print(f"   {', '.join(parts)}")
        print("   Ziel: 2 je Schiffstyp, Rumpf > 90%.")
        if state == "completed":
            print("   Bonus: Heuer -10%")

        mission = player.missions.get("atheria_resonance", {})
        state = mission.get("state", "inactive")
        print("3) Atheria-Resonanz")
        if state == "active":
            baseline = max(1, int(mission.get("baseline", 1)))
            worth = self._net_worth(player, self._market_prices(player.city))
            ratio = worth / baseline
            print(f"   Rezession aktiv: {ratio:.2f}x von Ziel {ATHERIA_RESONANCE_TARGET_MULT:.2f}x")
        elif state == "completed":
            print("   Abgeschlossen: Hall of Fame")
        else:
            print("   Warte auf Rezession (Wachstum < 0.95).")

        mission = player.missions.get("family_dynasty", {})
        state = mission.get("state", "inactive")
        print("4) Familiendynastie")
        target_fund = DYNASTY_INHERITANCE_PER_CHILD * DYNASTY_CHILDREN_TARGET
        if state == "completed":
            print(f"   Erbe gesichert: Startkapital {DYNASTY_INHERITANCE_PER_CHILD} Mark")
        else:
            print(
                f"   Kinder {player.children}/{DYNASTY_CHILDREN_TARGET} | Kapital {player.money}/{target_fund} | Alter < {DYNASTY_AGE_LIMIT}"
            )

        mission = player.missions.get("brewmaster", {})
        state = mission.get("state", "active")
        print("5) Braumeisterbund")
        delivered = int(mission.get("delivered", 0))
        target = int(mission.get("target", QUEST_BREWMASTER_TARGET))
        if state == "completed":
            print(f"   Abgeschlossen: {delivered}/{target} Bier gehandelt.")
        else:
            print(f"   Fortschritt: {delivered}/{target} Bier verkaufen.")

        mission = player.missions.get("timber_trade", {})
        state = mission.get("state", "active")
        print("6) Nordholz-Vertrag")
        delivered = int(mission.get("delivered", 0))
        target = int(mission.get("target", QUEST_TIMBER_TARGET))
        if state == "completed":
            print(f"   Abgeschlossen: {delivered}/{target} Holz gehandelt.")
        else:
            print(f"   Fortschritt: {delivered}/{target} Holz verkaufen.")

        mission = player.missions.get("route_master", {})
        state = mission.get("state", "active")
        print("7) Routenmeister")
        visited = [str(city_name) for city_name in mission.get("visited", [])]
        target = int(mission.get("target", QUEST_ROUTE_MASTER_TARGET_CITIES))
        if state == "completed":
            print(f"   Abgeschlossen: {len(visited)}/{target} Staedte besucht.")
        else:
            print(f"   Fortschritt: {len(visited)}/{target} Staedte besucht.")

        mission = player.missions.get("arms_race", {})
        state = mission.get("state", "active")
        print("8) Arsenal der Hanse")
        cannons = sum(ship.cannons for ship in player.ships)
        ships_count = len(player.ships)
        target_cannons = int(mission.get("target_cannons", QUEST_ARMS_RACE_TARGET_CANNONS))
        target_ships = int(mission.get("target_ships", QUEST_ARMS_RACE_TARGET_SHIPS))
        if state == "completed":
            print(f"   Abgeschlossen: {ships_count}/{target_ships} Schiffe, {cannons}/{target_cannons} Kanonen.")
        else:
            print(f"   Fortschritt: {ships_count}/{target_ships} Schiffe, {cannons}/{target_cannons} Kanonen.")

        print("9) Betriebskampagnen (8 Stufen je Betrieb)")
        building_quests = player.missions.get("building_quests", {})
        unlocked_recipe_ids = self._unlocked_recipe_ids()
        total_tiers = len(unlocked_recipe_ids) * BUILDING_QUEST_TIERS
        completed_tiers = 0
        for recipe_id in unlocked_recipe_ids:
            entry = building_quests.get(recipe_id, {})
            completed_tiers += min(BUILDING_QUEST_TIERS, max(0, int(entry.get("tier", 0))))
        print(f"   Gesamtfortschritt: {completed_tiers}/{total_tiers} Queststufen")
        for recipe_id in unlocked_recipe_ids:
            recipe = PRODUCTION_RECIPES.get(recipe_id)
            if recipe is None:
                continue
            entry = building_quests.get(recipe_id, {})
            tier = min(BUILDING_QUEST_TIERS, max(0, int(entry.get("tier", 0))))
            if tier >= BUILDING_QUEST_TIERS:
                print(f"   {recipe.name:18} 8/8 abgeschlossen")
                continue
            progress = max(0, int(entry.get("progress", 0)))
            target = self._building_quest_target(recipe_id, tier)
            print(f"   {recipe.name:18} Stufe {tier + 1}/8: {progress}/{target}")

    def _resolve_investments(self, player: Player) -> None:
        remaining: List[Investment] = []
        for inv in player.market_investments:
            inv.turns_left -= 1
            if inv.turns_left > 0:
                remaining.append(inv)
                continue

            if inv.risk == 1:
                factor = self.rng.uniform(0.90, 1.35)
            elif inv.risk == 2:
                factor = self.rng.uniform(0.70, 1.80)
            else:
                factor = self.rng.uniform(0.20, 2.80)

            payout = int(inv.amount * factor)
            player.money += payout
            diff = payout - inv.amount
            if diff >= 0:
                player.reputation = min(200, player.reputation + 3)
                print(f"Investition erfolgreich: +{diff} Mark Gewinn.")
                player.chronicle.append(
                    f"ANNO {self.current_year}: Investition brachte {diff} Mark Gewinn."
                )
            else:
                player.reputation = max(0, player.reputation - 2)
                print(f"Investition fehlgeschlagen: {-diff} Mark Verlust.")
                player.chronicle.append(
                    f"ANNO {self.current_year}: Investition brachte {-diff} Mark Verlust."
                )
        player.market_investments = remaining

    def _end_of_turn(self, player: Player) -> None:
        if not player.alive:
            return

        self._init_missions(player)
        self._update_fleet_synergy(player)
        self._apply_passive_income(player)

        growth = self.economy_state.global_growth
        price_level = self.economy_state.global_price_level

        heuer_factor = max(0.75, min(1.45, 0.88 + (price_level - 1.0) * 0.35))
        total_capacity = sum(ship.cargo_capacity for ship in player.ships)
        yearly_heuer = int((140 + total_capacity // 4) * heuer_factor)
        monthly_heuer = max(1, yearly_heuer // 12)
        if player.missions.get("fleet_synergy", {}).get("state") == "completed":
            monthly_heuer = max(1, int(round(monthly_heuer * (1 - FLEET_SYNERGY_HEUER_REDUCTION))))
        player.money -= monthly_heuer
        if player.debt > 0:
            debt_interest = max(1.01, min(1.10, 1.02 + (price_level - 1.0) * 0.05 - (growth - 1.0) * 0.02))
            monthly_interest = debt_interest ** (1 / 12)
            player.debt = int(player.debt * monthly_interest)

        if player.money < 0:
            player.debt += abs(player.money)
            player.money = 0

        if growth > 1.0:
            bonus = int(((growth - 1.0) / 12) * (120 + player.reputation * 3))
            if bonus > 0:
                player.money += bonus
                player.chronicle.append(
                    f"ANNO {self.current_year}: Wirtschaftsaufschwung (+{bonus} Mark, {MONTHS[self.current_month - 1]})."
                )
        elif growth < 0.95 and player.money > 0:
            recession_loss = int(((0.95 - growth) / 12) * max(120, player.money * 0.05))
            if recession_loss > 0:
                player.money = max(0, player.money - recession_loss)
                player.chronicle.append(
                    f"ANNO {self.current_year}: Konjunkturflaute (-{recession_loss} Mark, {MONTHS[self.current_month - 1]})."
                )

        if player.money > 2500 and player.debt > 0:
            repayment = min(player.debt, max(300, player.money // 5))
            player.money -= repayment
            player.debt -= repayment

        if player.debt > 17000 and self.rng.random() < (0.35 / 12):
            turns = self.rng.randint(1, 3)
            player.turns_in_debt_tower = turns
            player.chronicle.append(
                f"ANNO {self.current_year}: {player.name} fuer {turns} Monate im Schuldturm."
            )
            print(f"Schuldturm: {turns} Monat(e) Haft.")

        if self.current_month == 12:
            player.age += 1
            self._resolve_life_events(player)
        self._update_title(player)
        self._update_missions_monthly(player)

    def _ensure_player_child_ages(self, player: Player) -> None:
        if not isinstance(player.child_names, list):
            player.child_names = []
        if not isinstance(player.child_ages, dict):
            player.child_ages = {}
        if player.children < len(player.child_names):
            player.children = len(player.child_names)
        elif player.children > len(player.child_names):
            for idx in range(len(player.child_names) + 1, player.children + 1):
                player.child_names.append(f"Kind {idx}")
        for child_name in player.child_names:
            try:
                player.child_ages[child_name] = max(0, int(player.child_ages.get(child_name, 6)))
            except (TypeError, ValueError):
                player.child_ages[child_name] = 6
        for raw_name in list(player.child_ages.keys()):
            if raw_name not in player.child_names:
                player.child_ages.pop(raw_name, None)

    def _resolve_life_events(self, player: Player) -> None:
        self._ensure_player_child_ages(player)
        city_name = player.city if player.city in CITIES else CITIES[0]
        health = self._city_health_profile(city_name)
        survival_probability = _clamp(float(health.get("child_survival_rate", 0.75)), 0.20, 0.995)
        yearly_child_mortality = _clamp(1.0 - survival_probability, 0.002, 0.30)

        deceased_children: List[str] = []
        for child_name in list(player.child_names):
            age = max(0, int(player.child_ages.get(child_name, 0))) + 1
            player.child_ages[child_name] = age
            if age <= CHILD_MORTALITY_VULNERABLE_AGE and self.rng.random() < yearly_child_mortality:
                deceased_children.append(child_name)
        if deceased_children:
            for child_name in deceased_children:
                if child_name in player.child_names:
                    player.child_names.remove(child_name)
                player.child_ages.pop(child_name, None)
                player.chronicle.append(
                    f"ANNO {self.current_year}: Kind {child_name} verstarb an Krankheit."
                )
            player.children = len(player.child_names)
            if len(deceased_children) == 1:
                print(f"Historie: Kind {deceased_children[0]} verstarb an Krankheit.")
            else:
                print(f"Historie: {len(deceased_children)} Kinder verstarben an Krankheiten.")

        if not player.married and player.age >= 23 and self._net_worth(player, self._market_prices(player.city)) > 12000:
            if self.rng.random() < 0.16:
                player.married = True
                player.chronicle.append(f"ANNO {self.current_year}: {player.name} ist den Bund der Ehe eingegangen.")
                print("Historie: in den Bund der Ehe eingegangen.")

        max_children = max_children_for_year(self.current_year)
        if player.married and player.children < max_children:
            age_penalty = _clamp(1.0 - max(0, player.age - 35) * 0.02, 0.45, 1.0)
            support_factor = _clamp(0.72 + float(health.get("child_survival_rate", 0.75)) * 0.42, 0.55, 1.16)
            birth_chance = _clamp(birth_chance_for_year(self.current_year) * age_penalty * support_factor, 0.02, 0.56)
            if self.rng.random() < birth_chance:
                child_name = f"Kind {len(player.child_names) + 1}"
                if self.rng.random() <= survival_probability:
                    player.child_names.append(child_name)
                    player.child_ages[child_name] = 0
                    player.children = len(player.child_names)
                    player.chronicle.append(f"ANNO {self.current_year}: Kind geboren ({child_name}).")
                    print("Historie: geboren.")
                else:
                    player.chronicle.append(
                        f"ANNO {self.current_year}: Neugeborenes {child_name} verstarb an Krankheit."
                    )
                    print("Historie: Neugeborenes verstarb an Krankheit.")
        player.children = len(player.child_names)

        if player.age > 60:
            death_chance = min(0.42, (player.age - 60) * 0.025)
            if self.rng.random() < death_chance:
                if self._apply_dynasty_heir(player):
                    return
                player.alive = False
                player.chronicle.append(f"ANNO {self.current_year}: Tod des Vorfahren.")
                print("Tod des Vorfahren.")

    def _update_title(self, player: Player) -> None:
        worth = self._net_worth(player, self._market_prices(player.city))
        title_steps = self._active_titles()
        new_index = 0
        for idx, (threshold, _, _) in enumerate(title_steps):
            if worth >= threshold:
                new_index = idx
        if new_index > player.title_index:
            player.title_index = new_index
            title = self._title_for(player)
            player.chronicle.append(f"ANNO {self.current_year}: In den Stand '{title}' erhoben.")
            print(f"Aufstieg: {title}")

    def _market_prices(self, city: str) -> Dict[str, int]:
        self._ensure_world_state()
        cache_key = (self.current_year, self.current_month, self.current_sea_state, city)
        if cache_key in self._market_cache:
            return self._market_cache[cache_key]

        sea_factor = SEA_FACTORS[self.current_sea_state]
        city_macro = self.economy_state.city_factor(city)
        city_economy = self._city_economy(city)
        global_price_level = self.economy_state.global_price_level
        bankruptcy_factor = 1.10 if self._city_is_bankrupt(city) else 1.0
        prices: Dict[str, int] = {}
        breakdown_by_good: Dict[str, Dict[str, float]] = {}
        for good_name, params in self._active_goods().items():
            base = params["base_price"]
            volatility = params["volatility"]
            drift = self.rng.uniform(-volatility, volatility)
            drift_factor = 1.0 + drift
            good_macro = self.economy_state.good_factor(good_name)
            macro_factor = global_price_level * city_macro * good_macro
            scarcity_parts = city_economy.scarcity_components(good_name)
            scarcity_base = float(scarcity_parts.get("scarcity_base", 1.0))
            local_relief = float(scarcity_parts.get("local_scarcity_relief", 0.0))
            stock_factor = float(scarcity_parts.get("scarcity_final", 1.0))
            city_bias = city_good_bias(city, good_name)
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

        self._market_cache[cache_key] = prices
        self._market_breakdown_cache[cache_key] = breakdown_by_good
        return prices

    def _init_missions(self, player: Player) -> None:
        missions = player.missions
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
            {"state": "active", "target": QUEST_ROUTE_MASTER_TARGET_CITIES, "visited": [player.city]},
        )
        visited_raw = route_mission.get("visited", [])
        visited = [str(city_name) for city_name in visited_raw if isinstance(city_name, str)]
        if player.city not in visited:
            visited.append(player.city)
        route_mission["visited"] = visited
        missions.setdefault(
            "arms_race",
            {
                "state": "active",
                "target_cannons": QUEST_ARMS_RACE_TARGET_CANNONS,
                "target_ships": QUEST_ARMS_RACE_TARGET_SHIPS,
            },
        )
        self._init_building_quests(player)

    def _month_index(self) -> int:
        return (self.current_year - STARTING_YEAR) * 12 + (self.current_month - 1)

    def _city_discount(self, player: Player, city: str) -> float:
        mission = player.missions.get("hanse_privileg", {})
        if mission.get("state") == "completed" and mission.get("city") == city:
            return float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
        return 0.0

    def _complete_mission_reward(
        self,
        player: Player,
        mission_key: str,
        *,
        reward_money: int,
        reward_rep: int,
        text: str,
    ) -> None:
        mission = player.missions.get(mission_key, {})
        if mission.get("state") == "completed":
            return
        mission["state"] = "completed"
        if reward_money > 0:
            player.money += reward_money
        if reward_rep > 0:
            player.reputation = min(200, player.reputation + reward_rep)
        print(text)
        player.chronicle.append(f"ANNO {self.current_year}: {text}")

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

    def _init_building_quests(self, player: Player) -> None:
        mission = player.missions.setdefault("building_quests", {})
        current_century = self._current_century()
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
            elif current_century < unlock_century:
                state = "locked"
            else:
                state = "active"
            mission[recipe_id] = {
                "tier": tier,
                "progress": progress,
                "state": state,
            }

    def _record_building_quest_trade(self, player: Player, good: str, qty: int) -> None:
        if qty <= 0:
            return
        quests = player.missions.setdefault("building_quests", {})
        current_century = self._current_century()
        for recipe_id in self._building_recipe_ids_for_good(good):
            if RECIPE_UNLOCK_CENTURY.get(recipe_id, 14) > current_century:
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
                player.money += reward_money
                if reward_rep > 0:
                    player.reputation = min(200, player.reputation + reward_rep)
                print(
                    f"Betriebsquest [{recipe.name}] Stufe {tier}/{BUILDING_QUEST_TIERS} abgeschlossen "
                    f"(+{reward_money} Mark{', +1 Ruf' if reward_rep else ''})."
                )
                player.chronicle.append(
                    f"ANNO {self.current_year}: Betriebsquest {recipe.name} Stufe {tier} abgeschlossen."
                )

            state = "completed" if tier >= BUILDING_QUEST_TIERS else "active"
            quests[recipe_id] = {"tier": tier, "progress": progress, "state": state}

    def _record_trade_for_missions(self, player: Player, good: str, qty: int) -> None:
        if qty <= 0:
            return

        if good == "Bier":
            mission = player.missions.setdefault(
                "brewmaster",
                {"state": "active", "target": QUEST_BREWMASTER_TARGET, "delivered": 0, "next_log": 40},
            )
            if mission.get("state") != "completed":
                delivered = int(mission.get("delivered", 0)) + qty
                target = int(mission.get("target", QUEST_BREWMASTER_TARGET))
                mission["delivered"] = delivered
                next_log = int(mission.get("next_log", 40))
                if delivered >= next_log and delivered < target:
                    print(f"Braumeisterbund: {min(delivered, target)}/{target} Bier.")
                    mission["next_log"] = next_log + 40
                if delivered >= target:
                    self._complete_mission_reward(
                        player,
                        "brewmaster",
                        reward_money=1800,
                        reward_rep=3,
                        text="Mission erfuellt: Braumeisterbund (+1800 Mark, +3 Ruf).",
                    )

        if good == "Holz":
            mission = player.missions.setdefault(
                "timber_trade",
                {"state": "active", "target": QUEST_TIMBER_TARGET, "delivered": 0, "next_log": 60},
            )
            if mission.get("state") != "completed":
                delivered = int(mission.get("delivered", 0)) + qty
                target = int(mission.get("target", QUEST_TIMBER_TARGET))
                mission["delivered"] = delivered
                next_log = int(mission.get("next_log", 60))
                if delivered >= next_log and delivered < target:
                    print(f"Nordholz-Vertrag: {min(delivered, target)}/{target} Holz.")
                    mission["next_log"] = next_log + 60
                if delivered >= target:
                    self._complete_mission_reward(
                        player,
                        "timber_trade",
                        reward_money=1600,
                        reward_rep=2,
                        text="Mission erfuellt: Nordholz-Vertrag (+1600 Mark, +2 Ruf).",
                    )

        self._record_building_quest_trade(player, good, qty)

    def _record_city_visit(self, player: Player, city: str) -> None:
        mission = player.missions.setdefault(
            "route_master",
            {"state": "active", "target": QUEST_ROUTE_MASTER_TARGET_CITIES, "visited": [player.city]},
        )
        visited_raw = mission.get("visited", [])
        visited = [str(city_name) for city_name in visited_raw if isinstance(city_name, str)]
        if city not in visited:
            visited.append(city)
            mission["visited"] = visited
        self._update_route_master(player)

    def _update_route_master(self, player: Player) -> None:
        mission = player.missions.setdefault(
            "route_master",
            {"state": "active", "target": QUEST_ROUTE_MASTER_TARGET_CITIES, "visited": [player.city]},
        )
        if mission.get("state") == "completed":
            return
        visited = [str(city_name) for city_name in mission.get("visited", []) if isinstance(city_name, str)]
        if player.city not in visited:
            visited.append(player.city)
        mission["visited"] = visited
        target = int(mission.get("target", QUEST_ROUTE_MASTER_TARGET_CITIES))
        if len(visited) >= target:
            self._complete_mission_reward(
                player,
                "route_master",
                reward_money=1200,
                reward_rep=2,
                text="Mission erfuellt: Routenmeister (+1200 Mark, +2 Ruf).",
            )

    def _update_arms_race(self, player: Player) -> None:
        mission = player.missions.setdefault(
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
        cannons = sum(ship.cannons for ship in player.ships)
        ships_count = len(player.ships)
        if ships_count >= target_ships and cannons >= target_cannons:
            self._complete_mission_reward(
                player,
                "arms_race",
                reward_money=2200,
                reward_rep=4,
                text="Mission erfuellt: Arsenal der Hanse (+2200 Mark, +4 Ruf).",
            )

    def _update_missions_monthly(self, player: Player) -> None:
        self._init_missions(player)
        self._update_hanse_privileg(player, self._month_index())
        self._update_fleet_synergy(player)
        self._update_atheria_resonance(player)
        self._update_family_dynasty(player)
        self._update_route_master(player)
        self._update_arms_race(player)

    def _update_hanse_privileg(self, player: Player, month_index: int) -> None:
        mission = player.missions.setdefault("hanse_privileg", {})
        state = mission.get("state", "inactive")
        if state == "completed":
            return
        if state == "active":
            deadline = int(mission.get("deadline", month_index))
            delivered = int(mission.get("delivered", 0))
            target = int(mission.get("target", HANSE_PRIVILEG_QTY))
            if month_index > deadline:
                mission["state"] = "failed"
                print("Hanse-Privileg gescheitert: Frist abgelaufen.")
                return
            if delivered >= target:
                mission["state"] = "completed"
                mission["discount"] = float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
                print(
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
        print(
            f"Mission gestartet: Hanse-Privileg in {target_city} ({HANSE_PRIVILEG_QTY} {HANSE_PRIVILEG_GOOD} in 12 Monaten)."
        )

    def _record_hanse_delivery(self, player: Player, city: str, good: str, qty: int) -> None:
        if qty <= 0:
            return
        mission = player.missions.get("hanse_privileg", {})
        if mission.get("state") != "active":
            return
        if mission.get("city") != city or mission.get("good") != good:
            return
        delivered = int(mission.get("delivered", 0)) + qty
        target = int(mission.get("target", HANSE_PRIVILEG_QTY))
        mission["delivered"] = delivered
        next_log = int(mission.get("next_log", max(10, target // 4)))
        if delivered >= next_log:
            print(f"Hanse-Privileg: {min(delivered, target)}/{target} {good} geliefert.")
            mission["next_log"] = next_log + max(10, target // 4)
        if delivered >= target:
            mission["state"] = "completed"
            mission["discount"] = float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
            print(f"Hanse-Privileg erlangt: {city} (-{int(HANSE_PRIVILEG_DISCOUNT * 100)}% Einkauf).")

    def _update_fleet_synergy(self, player: Player) -> None:
        mission = player.missions.setdefault("fleet_synergy", {})
        if mission.get("state") == "completed":
            return
        required = {name: 0 for name, *_ in self._fleet_synergy_shipyard()}
        for ship in player.ships:
            if ship.name in required and ship.hull > FLEET_SYNERGY_HULL_MIN:
                required[ship.name] += 1
        mission["counts"] = dict(required)
        if all(count >= FLEET_SYNERGY_REQUIRED for count in required.values()) and required:
            mission["state"] = "completed"
            mission["reduction"] = FLEET_SYNERGY_HEUER_REDUCTION
            print("Mission erfuellt: Architekt der Synergie (Heuer -10%).")
        else:
            mission.setdefault("state", "active")

    def _update_atheria_resonance(self, player: Player) -> None:
        mission = player.missions.setdefault("atheria_resonance", {})
        state = mission.get("state", "inactive")
        growth = self.economy_state.global_growth
        worth = self._net_worth(player, self._market_prices(player.city))
        if state == "completed":
            return
        if growth < ATHERIA_RESONANCE_GROWTH_MAX:
            if state != "active":
                mission["state"] = "active"
                mission["baseline"] = worth
                mission["next_log"] = 1.25
                print("Mission gestartet: Atheria-Resonanz (Netto-Wert verdoppeln in Rezession).")
            else:
                baseline = max(1, int(mission.get("baseline", worth)))
                ratio = worth / baseline
                next_log = float(mission.get("next_log", 1.25))
                if ratio >= next_log:
                    print(f"Atheria-Resonanz: Fortschritt {ratio:.2f}x.")
                    mission["next_log"] = min(2.0, next_log + 0.25)
                if ratio >= ATHERIA_RESONANCE_TARGET_MULT:
                    mission["state"] = "completed"
                    print("Mission erfuellt: Atheria-Resonanz (Hall of Fame freigeschaltet).")
            return
        if state == "active":
            mission["state"] = "inactive"
            mission.pop("baseline", None)
            mission.pop("next_log", None)
            print("Atheria-Resonanz abgebrochen: Rezession endet.")

    def _update_family_dynasty(self, player: Player) -> None:
        mission = player.missions.setdefault("family_dynasty", {})
        if mission.get("state") == "completed":
            return
        if player.age >= DYNASTY_AGE_LIMIT:
            return
        target_fund = DYNASTY_INHERITANCE_PER_CHILD * DYNASTY_CHILDREN_TARGET
        if player.children >= DYNASTY_CHILDREN_TARGET and player.money >= target_fund:
            mission["state"] = "completed"
            mission["inheritance"] = DYNASTY_INHERITANCE_PER_CHILD
            print("Mission erfuellt: Familiendynastie (Erbe gesichert).")

    def _apply_dynasty_heir(self, player: Player) -> bool:
        mission = player.missions.get("family_dynasty", {})
        if mission.get("state") != "completed" or mission.get("used"):
            return False
        inheritance = int(mission.get("inheritance", DYNASTY_INHERITANCE_PER_CHILD))
        mission["used"] = True
        player.age = 18
        player.married = False
        player.children = 0
        player.child_names = []
        player.child_ages = {}
        player.turns_in_debt_tower = 0
        if player.money < inheritance:
            player.money = inheritance
        player.chronicle.append(f"ANNO {self.current_year}: Erbe angetreten.")
        print("Familiendynastie: Ein Erbe tritt das Handelshaus an.")
        return True

    def _net_worth(self, player: Player, prices: Dict[str, int]) -> int:
        cargo_value = 0
        for ship in player.ships:
            cargo_value += sum(prices.get(good_name, 0) * qty for good_name, qty in ship.cargo.items())
        for goods in player.warehouses.values():
            cargo_value += sum(prices.get(good_name, 0) * qty for good_name, qty in goods.items())
        fleet_value = sum(ship.value for ship in player.ships)
        return player.money + cargo_value + fleet_value - player.debt + player.reputation * 150

    def _title_for(self, player: Player) -> str:
        title_steps = self._active_titles()
        _, male, female = title_steps[min(player.title_index, len(title_steps) - 1)]
        return female if player.gender == "w" else male

    def _show_final_ranking(self) -> None:
        print()
        print("=" * 60)
        print("Spielende - Historie")
        print("=" * 60)
        if not self.players:
            print("Keine ueberlebenden Handelshaeuser.")
            return

        ranked = sorted(
            self.players,
            key=lambda p: self._net_worth(p, self._market_prices(p.city)),
            reverse=True,
        )
        for idx, player in enumerate(ranked, start=1):
            value = self._net_worth(player, self._market_prices(player.city))
            print(f"{idx}. {player.name:12} {self._title_for(player):12} Gesamtwert {value}")
            for entry in player.chronicle[-5:]:
                print(f"   - {entry}")

    def _choose_city(self) -> str:
        print("Startstadt:")
        for idx, city_name in enumerate(CITIES, start=1):
            print(f"{idx}) {city_name}")
        choice = self._ask_int(f"Auswahl (1-{len(CITIES)}): ", 1, len(CITIES))
        return CITIES[choice - 1]

    def _ask_name(self, prompt: str) -> str:
        while True:
            value = input(prompt).strip()
            if len(value) >= MIN_NAME_LEN:
                return value
            print(f"{MIN_NAME_LEN} Buchstaben Minimum.")

    def _ask_gender(self, prompt: str) -> str:
        while True:
            value = input(prompt).strip().lower()
            if value in {"m", "w"}:
                return value
            print("Bitte m oder w eingeben.")

    def _ask_yes_no(self, prompt: str) -> bool:
        while True:
            value = input(prompt).strip().lower()
            if value in {"j", "ja", "y", "yes"}:
                return True
            if value in {"n", "nein", "no"}:
                return False
            print("Bitte mit j oder n antworten.")

    def _ask_int(self, prompt: str, min_value: int, max_value: int) -> int:
        while True:
            raw = input(prompt).strip()
            try:
                value = int(raw)
            except ValueError:
                print("Bitte eine Zahl eingeben.")
                continue
            if min_value <= value <= max_value:
                return value
            print(f"Bitte einen Wert zwischen {min_value} und {max_value} eingeben.")
