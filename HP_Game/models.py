from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class Ship:
    name: str = "Kogge"
    custom_name: str = ""
    cargo_capacity: int = 120
    hull: int = 100
    rigging: int = 100
    value: int = 3200
    cargo: Dict[str, int] = field(default_factory=dict)
    cannons: int = 0
    cannon_inventory: Dict[str, int] = field(default_factory=dict)
    is_at_sea: bool = False
    city: str = "Luebeck"
    destination: Optional[str] = None
    travel_turns_left: int = 0
    last_report: str = ""
    locked_prices: Dict[str, int] = field(default_factory=dict)
    locked_qty: Dict[str, int] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.custom_name or self.name

    @property
    def total_cargo(self) -> int:
        return sum(self.cargo.values())

    @property
    def cargo_space_left(self) -> int:
        return self.cargo_capacity - self.total_cargo

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Ship":
        cargo_raw = data.get("cargo", {})
        cargo = {str(key): int(value) for key, value in cargo_raw.items()} if isinstance(cargo_raw, dict) else {}
        destination = data.get("destination")
        locked_prices_raw = data.get("locked_prices", {})
        locked_qty_raw = data.get("locked_qty", {})
        cannon_inventory_raw = data.get("cannon_inventory", {})
        locked_prices = (
            {str(k): int(v) for k, v in locked_prices_raw.items()} if isinstance(locked_prices_raw, dict) else {}
        )
        locked_qty = (
            {str(k): int(v) for k, v in locked_qty_raw.items()} if isinstance(locked_qty_raw, dict) else {}
        )
        cannon_inventory: Dict[str, int] = {}
        if isinstance(cannon_inventory_raw, dict):
            for raw_key, raw_value in cannon_inventory_raw.items():
                try:
                    qty = max(0, int(raw_value))
                except (TypeError, ValueError):
                    continue
                if qty > 0:
                    cannon_inventory[str(raw_key)] = qty
        return cls(
            name=str(data.get("name", "Kogge")),
            custom_name=str(data.get("custom_name", "")),
            cargo_capacity=int(data.get("cargo_capacity", 120)),
            hull=int(data.get("hull", 100)),
            rigging=int(data.get("rigging", 100)),
            value=int(data.get("value", 3200)),
            cargo=cargo,
            cannons=int(data.get("cannons", 0)),
            cannon_inventory=cannon_inventory,
            is_at_sea=bool(data.get("is_at_sea", False)),
            city=str(data.get("city", "Luebeck")),
            destination=str(destination) if destination else None,
            travel_turns_left=int(data.get("travel_turns_left", 0)),
            last_report=str(data.get("last_report", "")),
            locked_prices=locked_prices,
            locked_qty=locked_qty,
        )

    def to_dict(self) -> Dict[str, Any]:
        cannon_inventory: Dict[str, int] = {}
        for key, value in self.cannon_inventory.items():
            try:
                qty = max(0, int(value))
            except (TypeError, ValueError):
                continue
            if qty > 0:
                cannon_inventory[str(key)] = qty
        return {
            "name": self.name,
            "custom_name": self.custom_name,
            "cargo_capacity": self.cargo_capacity,
            "hull": self.hull,
            "rigging": self.rigging,
            "value": self.value,
            "cargo": dict(self.cargo),
            "cannons": self.cannons,
            "cannon_inventory": cannon_inventory,
            "is_at_sea": self.is_at_sea,
            "city": self.city,
            "destination": self.destination,
            "travel_turns_left": self.travel_turns_left,
            "last_report": self.last_report,
            "locked_prices": dict(self.locked_prices),
            "locked_qty": dict(self.locked_qty),
        }


@dataclass
class Investment:
    amount: int
    turns_left: int
    risk: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Investment":
        return cls(
            amount=int(data.get("amount", 0)),
            turns_left=int(data.get("turns_left", 0)),
            risk=int(data.get("risk", 2)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "turns_left": self.turns_left,
            "risk": self.risk,
        }


@dataclass
class ProductionRecipe:
    id: str
    name: str
    inputs: Dict[str, int] = field(default_factory=dict)
    outputs: Dict[str, int] = field(default_factory=dict)
    upkeep: int = 0


@dataclass
class Building:
    id: str
    level: int = 1
    active: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Building":
        level_raw = data.get("level", 1)
        try:
            level = max(1, int(level_raw))
        except (TypeError, ValueError):
            level = 1
        return cls(
            id=str(data.get("id", "")).strip(),
            level=level,
            active=bool(data.get("active", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "level": max(1, int(self.level)),
            "active": bool(self.active),
        }


@dataclass
class CityEconomy:
    name: str
    inventory: Dict[str, int] = field(default_factory=dict)
    buildings: List[Building] = field(default_factory=list)
    treasury: int = 0
    population: int = 2400
    social_classes: Dict[str, float] = field(
        default_factory=lambda: {
            "peasants": 0.72,
            "artisans": 0.18,
            "merchants": 0.08,
            "nobility": 0.02,
        }
    )
    institutions: Dict[str, int] = field(default_factory=dict)
    infrastructure: float = 1.0
    social_stability: float = 50.0
    quality_of_life: float = 50.0
    disease_pressure: float = 0.0
    disease_cases: int = 0
    child_survival_rate: float = 0.75
    doctor_coverage: float = 0.0
    migration: int = 0
    tax_income: int = 0
    political_influence: float = 0.0
    local_scarcity_relief: float = 0.0
    hazard_mitigation: float = 0.0
    storage_multiplier: float = 1.0
    bankrupt: int = 0
    monuments: Dict[str, int] = field(default_factory=dict)
    century_stage: int = 14

    def ensure_goods(self, goods: Iterable[str], default_stock: int = 150) -> None:
        base = max(0, int(default_stock))
        for good_name in goods:
            key = str(good_name)
            if key not in self.inventory:
                self.inventory[key] = base
            else:
                try:
                    self.inventory[key] = max(0, int(self.inventory[key]))
                except (TypeError, ValueError):
                    self.inventory[key] = base

    def scarcity_factor(self, good_name: str) -> float:
        stock = max(0, int(self.inventory.get(good_name, 0)))
        if stock <= 40:
            # Knappheit wird teuer, aber bleibt im kontrollierten Bereich.
            base = min(1.45, 1.10 + (40 - stock) / 120.0)
        elif stock < 120:
            base = 1.05 + (120 - stock) / 400.0
        elif stock <= 220:
            base = 1.0
        elif stock <= 260:
            base = 1.0 - (stock - 220) / 500.0
        else:
            base = max(0.78, 0.92 - (stock - 260) / 900.0)
        # Dauerhafte Sozialinvestitionen entlasten lokal den Knappheitsdruck.
        relief = max(0.0, min(0.55, float(self.local_scarcity_relief)))
        return max(0.62, min(1.60, base * (1.0 - relief)))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CityEconomy":
        inventory_raw = data.get("inventory", {})
        inventory: Dict[str, int] = {}
        if isinstance(inventory_raw, dict):
            for key, value in inventory_raw.items():
                try:
                    inventory[str(key)] = max(0, int(value))
                except (TypeError, ValueError):
                    inventory[str(key)] = 0

        buildings_raw = data.get("buildings", [])
        buildings: List[Building] = []
        if isinstance(buildings_raw, list):
            for entry in buildings_raw:
                if isinstance(entry, dict):
                    building = Building.from_dict(entry)
                    if building.id:
                        buildings.append(building)

        treasury_raw = data.get("treasury", 0)
        try:
            treasury = int(treasury_raw)
        except (TypeError, ValueError):
            treasury = 0

        population_raw = data.get("population", 2400)
        try:
            population = max(200, int(population_raw))
        except (TypeError, ValueError):
            population = 2400

        social_classes_raw = data.get("social_classes", {})
        social_classes: Dict[str, float] = {}
        if isinstance(social_classes_raw, dict):
            for key, value in social_classes_raw.items():
                try:
                    social_classes[str(key)] = max(0.0, float(value))
                except (TypeError, ValueError):
                    continue
        if not social_classes:
            social_classes = {
                "peasants": 0.72,
                "artisans": 0.18,
                "merchants": 0.08,
                "nobility": 0.02,
            }

        institutions_raw = data.get("institutions", {})
        institutions: Dict[str, int] = {}
        if isinstance(institutions_raw, dict):
            for key, value in institutions_raw.items():
                try:
                    institutions[str(key)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue

        def _float_field(key: str, default: float) -> float:
            try:
                return float(data.get(key, default))
            except (TypeError, ValueError):
                return float(default)

        migration_raw = data.get("migration", 0)
        try:
            migration = int(migration_raw)
        except (TypeError, ValueError):
            migration = 0
        disease_cases_raw = data.get("disease_cases", 0)
        try:
            disease_cases = max(0, int(disease_cases_raw))
        except (TypeError, ValueError):
            disease_cases = 0
        tax_income_raw = data.get("tax_income", 0)
        try:
            tax_income = int(tax_income_raw)
        except (TypeError, ValueError):
            tax_income = 0
        bankrupt_raw = data.get("bankrupt", 0)
        try:
            bankrupt = 1 if int(bankrupt_raw) else 0
        except (TypeError, ValueError):
            bankrupt = 0

        monuments_raw = data.get("monuments", {})
        monuments: Dict[str, int] = {}
        if isinstance(monuments_raw, dict):
            for key, value in monuments_raw.items():
                try:
                    monuments[str(key)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue
        century_raw = data.get("century_stage", 14)
        try:
            century_stage = max(1, int(century_raw))
        except (TypeError, ValueError):
            century_stage = 14

        return cls(
            name=str(data.get("name", "")).strip() or "Unbekannt",
            inventory=inventory,
            buildings=buildings,
            treasury=treasury,
            population=population,
            social_classes=social_classes,
            institutions=institutions,
            infrastructure=max(0.0, _float_field("infrastructure", 1.0)),
            social_stability=max(0.0, min(100.0, _float_field("social_stability", 50.0))),
            quality_of_life=max(0.0, min(100.0, _float_field("quality_of_life", 50.0))),
            disease_pressure=max(0.0, min(1.2, _float_field("disease_pressure", 0.0))),
            disease_cases=disease_cases,
            child_survival_rate=max(0.15, min(0.999, _float_field("child_survival_rate", 0.75))),
            doctor_coverage=max(0.0, min(1.5, _float_field("doctor_coverage", 0.0))),
            migration=migration,
            tax_income=tax_income,
            political_influence=max(0.0, _float_field("political_influence", 0.0)),
            local_scarcity_relief=max(0.0, min(0.55, _float_field("local_scarcity_relief", 0.0))),
            hazard_mitigation=max(0.0, min(0.85, _float_field("hazard_mitigation", 0.0))),
            storage_multiplier=max(1.0, _float_field("storage_multiplier", 1.0)),
            bankrupt=bankrupt,
            monuments=monuments,
            century_stage=century_stage,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "inventory": {good: max(0, int(qty)) for good, qty in self.inventory.items()},
            "buildings": [building.to_dict() for building in self.buildings],
            "treasury": int(self.treasury),
            "population": max(200, int(self.population)),
            "social_classes": {str(key): float(value) for key, value in self.social_classes.items()},
            "institutions": {str(key): max(0, int(value)) for key, value in self.institutions.items()},
            "infrastructure": float(self.infrastructure),
            "social_stability": float(self.social_stability),
            "quality_of_life": float(self.quality_of_life),
            "disease_pressure": float(self.disease_pressure),
            "disease_cases": max(0, int(self.disease_cases)),
            "child_survival_rate": float(self.child_survival_rate),
            "doctor_coverage": float(self.doctor_coverage),
            "migration": int(self.migration),
            "tax_income": int(self.tax_income),
            "political_influence": float(self.political_influence),
            "local_scarcity_relief": float(self.local_scarcity_relief),
            "hazard_mitigation": float(self.hazard_mitigation),
            "storage_multiplier": float(self.storage_multiplier),
            "bankrupt": int(self.bankrupt),
            "monuments": {str(key): max(0, int(value)) for key, value in self.monuments.items()},
            "century_stage": int(self.century_stage),
        }


@dataclass
class WorldEconomy:
    cities: Dict[str, CityEconomy] = field(default_factory=dict)

    def get_or_create_city(
        self,
        name: str,
        active_goods: Iterable[str],
        default_stock: int = 150,
    ) -> CityEconomy:
        city_name = str(name)
        city = self.cities.get(city_name)
        if city is None:
            city = CityEconomy(name=city_name)
            self.cities[city_name] = city
        city.ensure_goods(active_goods, default_stock=default_stock)
        return city

    def ensure_cities(
        self,
        city_names: Iterable[str],
        active_goods: Iterable[str],
        default_stock: int = 150,
    ) -> None:
        goods = list(active_goods)
        for city_name in city_names:
            self.get_or_create_city(city_name, goods, default_stock=default_stock)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldEconomy":
        cities_raw = data.get("cities", {})
        cities: Dict[str, CityEconomy] = {}
        if isinstance(cities_raw, dict):
            for city_name, city_data in cities_raw.items():
                if isinstance(city_data, dict):
                    city = CityEconomy.from_dict(city_data)
                    city.name = str(city_name)
                    cities[str(city_name)] = city
        return cls(cities=cities)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cities": {name: city.to_dict() for name, city in self.cities.items()}
        }


@dataclass
class NPCTrader:
    name: str
    city: str
    money: int = 6000
    ship: Ship = field(default_factory=Ship)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NPCTrader":
        city = str(data.get("city", "Luebeck"))
        ship_data = data.get("ship", {})
        ship = Ship.from_dict(ship_data) if isinstance(ship_data, dict) else Ship(city=city)
        if not ship.city:
            ship.city = city
        money_raw = data.get("money", 6000)
        try:
            money = max(0, int(money_raw))
        except (TypeError, ValueError):
            money = 6000
        return cls(
            name=str(data.get("name", "NPC-Haendler")).strip() or "NPC-Haendler",
            city=city,
            money=money,
            ship=ship,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "city": self.city,
            "money": max(0, int(self.money)),
            "ship": self.ship.to_dict(),
        }


@dataclass
class Player:
    name: str
    gender: str
    city: str
    money: int
    debt: int
    reputation: int
    age: int
    title_index: int = 0
    ships: List[Ship] = field(default_factory=list)
    active_ship_index: int = 0
    warehouses: Dict[str, Dict[str, int]] = field(default_factory=dict)
    warehouse_locks: Dict[str, Dict[str, List[Dict[str, int]]]] = field(default_factory=dict)
    missions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    alive: bool = True
    married: bool = False
    spouse_name: str = ""
    marriage_year: Optional[int] = None
    marriage_month: Optional[int] = None
    children: int = 0
    child_names: List[str] = field(default_factory=list)
    child_ages: Dict[str, int] = field(default_factory=dict)
    last_marriage_offer_month: int = -9999
    turns_in_debt_tower: int = 0
    chronicle: List[str] = field(default_factory=list)
    market_investments: List[Investment] = field(default_factory=list)
    investments: Dict[str, float] = field(
        default_factory=lambda: {
            "social": 0.0,
            "research": 0.0,
            "infrastructure": 0.0,
        }
    )
    building_shares: Dict[str, Dict[str, float]] = field(default_factory=dict)
    city_influence: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ships:
            self.ships = [Ship(city=self.city)]
        self.active_ship_index = max(0, min(self.active_ship_index, len(self.ships) - 1))
        if not isinstance(self.missions, dict):
            self.missions = {}
        if not isinstance(self.child_names, list):
            self.child_names = []
        self.child_names = [str(name).strip() for name in self.child_names if str(name).strip()]
        if self.children < len(self.child_names):
            self.children = len(self.child_names)
        elif self.children > len(self.child_names):
            for idx in range(len(self.child_names) + 1, self.children + 1):
                self.child_names.append(f"Kind {idx}")
        if not isinstance(self.child_ages, dict):
            self.child_ages = {}
        normalized_child_ages: Dict[str, int] = {}
        for child_name in self.child_names:
            raw_age = self.child_ages.get(child_name, 6)
            try:
                age = max(0, int(raw_age))
            except (TypeError, ValueError):
                age = 6
            normalized_child_ages[child_name] = age
        self.child_ages = normalized_child_ages
        if not isinstance(self.building_shares, dict):
            self.building_shares = {}
        cleaned_shares: Dict[str, Dict[str, float]] = {}
        for city_name, share_map in self.building_shares.items():
            if not isinstance(share_map, dict):
                continue
            city_key = str(city_name)
            cleaned_city: Dict[str, float] = {}
            for recipe_id, value in share_map.items():
                try:
                    pct = max(0.0, float(value))
                except (TypeError, ValueError):
                    continue
                if pct > 0:
                    cleaned_city[str(recipe_id)] = pct
            if cleaned_city:
                cleaned_shares[city_key] = cleaned_city
        self.building_shares = cleaned_shares
        if not isinstance(self.city_influence, dict):
            self.city_influence = {}
        cleaned_influence: Dict[str, float] = {}
        for city_name, value in self.city_influence.items():
            try:
                score = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
            if score > 0:
                cleaned_influence[str(city_name)] = score
        self.city_influence = cleaned_influence
        if not isinstance(self.market_investments, list):
            self.market_investments = []
        normalized_market: List[Investment] = []
        for entry in self.market_investments:
            if isinstance(entry, Investment):
                normalized_market.append(entry)
            elif isinstance(entry, dict):
                normalized_market.append(Investment.from_dict(entry))
        self.market_investments = normalized_market
        if not isinstance(self.investments, dict):
            self.investments = {}
        normalized_investments = {
            "social": 0.0,
            "research": 0.0,
            "infrastructure": 0.0,
        }
        for key in list(normalized_investments.keys()):
            try:
                normalized_investments[key] = max(0.0, float(self.investments.get(key, 0.0)))
            except (TypeError, ValueError):
                normalized_investments[key] = 0.0
        self.investments = normalized_investments

    @property
    def total_cargo(self) -> int:
        return self.ship.total_cargo

    @property
    def cargo_space_left(self) -> int:
        return self.ship.cargo_space_left

    @property
    def ship(self) -> Ship:
        return self.ships[self.active_ship_index]

    @ship.setter
    def ship(self, value: Ship) -> None:
        if not self.ships:
            self.ships = [value]
            self.active_ship_index = 0
        else:
            self.ships[self.active_ship_index] = value

    @property
    def cargo(self) -> Dict[str, int]:
        return self.ship.cargo

    @cargo.setter
    def cargo(self, value: Dict[str, int]) -> None:
        self.ship.cargo = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "gender": self.gender,
            "city": self.city,
            "money": self.money,
            "debt": self.debt,
            "reputation": self.reputation,
            "age": self.age,
            "title_index": self.title_index,
            "ships": [ship.to_dict() for ship in self.ships],
            "active_ship_index": self.active_ship_index,
            "warehouses": {city: dict(goods) for city, goods in self.warehouses.items()},
            "warehouse_locks": {
                city: {good: [dict(entry) for entry in lots] for good, lots in goods.items()}
                for city, goods in self.warehouse_locks.items()
            },
            "missions": {key: dict(value) for key, value in self.missions.items()},
            "alive": self.alive,
            "married": self.married,
            "spouse_name": self.spouse_name,
            "marriage_year": self.marriage_year,
            "marriage_month": self.marriage_month,
            "children": self.children,
            "child_names": list(self.child_names),
            "child_ages": {name: max(0, int(age)) for name, age in self.child_ages.items()},
            "last_marriage_offer_month": self.last_marriage_offer_month,
            "turns_in_debt_tower": self.turns_in_debt_tower,
            "chronicle": list(self.chronicle),
            "market_investments": [inv.to_dict() for inv in self.market_investments],
            "investments": {key: float(value) for key, value in self.investments.items()},
            "building_shares": {
                city: {recipe_id: float(pct) for recipe_id, pct in shares.items()}
                for city, shares in self.building_shares.items()
            },
            "city_influence": {city: float(score) for city, score in self.city_influence.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        city = str(data.get("city", "Luebeck"))
        ships: List[Ship] = []
        ships_raw = data.get("ships")
        if isinstance(ships_raw, list) and ships_raw:
            for entry in ships_raw:
                if isinstance(entry, dict):
                    ship = Ship.from_dict(entry)
                    if not ship.city:
                        ship.city = city
                    ships.append(ship)
        else:
            ship = Ship.from_dict(data.get("ship", {}))
            cargo = data.get("cargo", {})
            if isinstance(cargo, dict):
                ship.cargo = {str(key): int(value) for key, value in cargo.items()}
            if not ship.city:
                ship.city = city
            ships = [ship]

        if not ships:
            ships = [Ship(city=city)]

        active_ship_index = int(data.get("active_ship_index", 0))
        active_ship_index = max(0, min(active_ship_index, len(ships) - 1))

        warehouses_raw = data.get("warehouses", {})
        warehouses: Dict[str, Dict[str, int]] = {}
        if isinstance(warehouses_raw, dict):
            for raw_city, goods in warehouses_raw.items():
                if isinstance(goods, dict):
                    warehouses[str(raw_city)] = {str(k): int(v) for k, v in goods.items()}

        locks_raw = data.get("warehouse_locks", {})
        warehouse_locks: Dict[str, Dict[str, List[Dict[str, int]]]] = {}
        if isinstance(locks_raw, dict):
            for raw_city, goods in locks_raw.items():
                if not isinstance(goods, dict):
                    continue
                city_locks: Dict[str, List[Dict[str, int]]] = {}
                for raw_good, lots in goods.items():
                    entries: List[Dict[str, int]] = []
                    if isinstance(lots, list):
                        for entry in lots:
                            if not isinstance(entry, dict):
                                continue
                            try:
                                qty = int(entry.get("qty", 0))
                                price = int(entry.get("price", 0))
                            except (TypeError, ValueError):
                                continue
                            if qty > 0 and price > 0:
                                entries.append({"qty": qty, "price": price})
                    city_locks[str(raw_good)] = entries
                warehouse_locks[str(raw_city)] = city_locks

        market_investments_raw = data.get("market_investments")
        legacy_investments_raw = data.get("investments")
        if isinstance(market_investments_raw, list):
            market_investments = [Investment.from_dict(entry) for entry in market_investments_raw]
        elif isinstance(legacy_investments_raw, list):
            market_investments = [Investment.from_dict(entry) for entry in legacy_investments_raw]
        else:
            market_investments = []
        investments_raw = data.get("investments", {})
        investments_dict = {
            "social": 0.0,
            "research": 0.0,
            "infrastructure": 0.0,
        }
        if isinstance(investments_raw, dict):
            for key in list(investments_dict.keys()):
                try:
                    investments_dict[key] = max(0.0, float(investments_raw.get(key, 0.0)))
                except (TypeError, ValueError):
                    investments_dict[key] = 0.0
        missions_raw = data.get("missions", {})
        missions: Dict[str, Dict[str, Any]] = {}
        if isinstance(missions_raw, dict):
            for key, value in missions_raw.items():
                if isinstance(value, dict):
                    missions[str(key)] = dict(value)
        shares_raw = data.get("building_shares", {})
        building_shares: Dict[str, Dict[str, float]] = {}
        if isinstance(shares_raw, dict):
            for raw_city, raw_values in shares_raw.items():
                if not isinstance(raw_values, dict):
                    continue
                city_key = str(raw_city)
                city_shares: Dict[str, float] = {}
                for raw_recipe, raw_pct in raw_values.items():
                    try:
                        pct = max(0.0, float(raw_pct))
                    except (TypeError, ValueError):
                        continue
                    if pct > 0:
                        city_shares[str(raw_recipe)] = pct
                if city_shares:
                    building_shares[city_key] = city_shares
        influence_raw = data.get("city_influence", {})
        city_influence: Dict[str, float] = {}
        if isinstance(influence_raw, dict):
            for raw_city, raw_score in influence_raw.items():
                try:
                    score = max(0.0, float(raw_score))
                except (TypeError, ValueError):
                    continue
                if score > 0:
                    city_influence[str(raw_city)] = score
        child_names_raw = data.get("child_names", [])
        child_names: List[str] = []
        if isinstance(child_names_raw, list):
            child_names = [str(item).strip() for item in child_names_raw if str(item).strip()]
        child_ages_raw = data.get("child_ages", {})
        child_ages: Dict[str, int] = {}
        if isinstance(child_ages_raw, dict):
            for raw_name, raw_age in child_ages_raw.items():
                try:
                    age = max(0, int(raw_age))
                except (TypeError, ValueError):
                    continue
                child_ages[str(raw_name)] = age
        spouse_name = str(data.get("spouse_name", ""))
        marriage_year_raw = data.get("marriage_year")
        marriage_month_raw = data.get("marriage_month")
        try:
            marriage_year = int(marriage_year_raw) if marriage_year_raw is not None else None
        except (TypeError, ValueError):
            marriage_year = None
        try:
            marriage_month = int(marriage_month_raw) if marriage_month_raw is not None else None
        except (TypeError, ValueError):
            marriage_month = None
        return cls(
            name=str(data.get("name", "Unbekannt")),
            gender=str(data.get("gender", "m")),
            city=city,
            money=int(data.get("money", 0)),
            debt=int(data.get("debt", 0)),
            reputation=int(data.get("reputation", 0)),
            age=int(data.get("age", 20)),
            title_index=int(data.get("title_index", 0)),
            ships=ships,
            active_ship_index=active_ship_index,
            warehouses=warehouses,
            warehouse_locks=warehouse_locks,
            missions=missions,
            alive=bool(data.get("alive", True)),
            married=bool(data.get("married", False)),
            spouse_name=spouse_name,
            marriage_year=marriage_year,
            marriage_month=marriage_month,
            children=int(data.get("children", 0)),
            child_names=child_names,
            child_ages=child_ages,
            last_marriage_offer_month=int(data.get("last_marriage_offer_month", -9999)),
            turns_in_debt_tower=int(data.get("turns_in_debt_tower", 0)),
            chronicle=[str(item) for item in data.get("chronicle", [])],
            market_investments=market_investments,
            investments=investments_dict,
            building_shares=building_shares,
            city_influence=city_influence,
        )
