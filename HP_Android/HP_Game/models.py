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
        locked_prices = (
            {str(k): int(v) for k, v in locked_prices_raw.items()} if isinstance(locked_prices_raw, dict) else {}
        )
        locked_qty = (
            {str(k): int(v) for k, v in locked_qty_raw.items()} if isinstance(locked_qty_raw, dict) else {}
        )
        return cls(
            name=str(data.get("name", "Kogge")),
            custom_name=str(data.get("custom_name", "")),
            cargo_capacity=int(data.get("cargo_capacity", 120)),
            hull=int(data.get("hull", 100)),
            rigging=int(data.get("rigging", 100)),
            value=int(data.get("value", 3200)),
            cargo=cargo,
            cannons=int(data.get("cannons", 0)),
            is_at_sea=bool(data.get("is_at_sea", False)),
            city=str(data.get("city", "Luebeck")),
            destination=str(destination) if destination else None,
            travel_turns_left=int(data.get("travel_turns_left", 0)),
            last_report=str(data.get("last_report", "")),
            locked_prices=locked_prices,
            locked_qty=locked_qty,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "custom_name": self.custom_name,
            "cargo_capacity": self.cargo_capacity,
            "hull": self.hull,
            "rigging": self.rigging,
            "value": self.value,
            "cargo": dict(self.cargo),
            "cannons": self.cannons,
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
            return min(1.45, 1.10 + (40 - stock) / 120.0)
        if stock < 120:
            return 1.05 + (120 - stock) / 400.0
        if stock <= 220:
            return 1.0
        if stock <= 260:
            return 1.0 - (stock - 220) / 500.0
        return max(0.78, 0.92 - (stock - 260) / 900.0)

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

        return cls(
            name=str(data.get("name", "")).strip() or "Unbekannt",
            inventory=inventory,
            buildings=buildings,
            treasury=treasury,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "inventory": {good: max(0, int(qty)) for good, qty in self.inventory.items()},
            "buildings": [building.to_dict() for building in self.buildings],
            "treasury": int(self.treasury),
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
    last_marriage_offer_month: int = -9999
    turns_in_debt_tower: int = 0
    chronicle: List[str] = field(default_factory=list)
    investments: List[Investment] = field(default_factory=list)

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
            "last_marriage_offer_month": self.last_marriage_offer_month,
            "turns_in_debt_tower": self.turns_in_debt_tower,
            "chronicle": list(self.chronicle),
            "investments": [inv.to_dict() for inv in self.investments],
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

        investments = [Investment.from_dict(entry) for entry in data.get("investments", [])]
        missions_raw = data.get("missions", {})
        missions: Dict[str, Dict[str, Any]] = {}
        if isinstance(missions_raw, dict):
            for key, value in missions_raw.items():
                if isinstance(value, dict):
                    missions[str(key)] = dict(value)
        child_names_raw = data.get("child_names", [])
        child_names: List[str] = []
        if isinstance(child_names_raw, list):
            child_names = [str(item).strip() for item in child_names_raw if str(item).strip()]
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
            last_marriage_offer_month=int(data.get("last_marriage_offer_month", -9999)),
            turns_in_debt_tower=int(data.get("turns_in_debt_tower", 0)),
            chronicle=[str(item) for item in data.get("chronicle", [])],
            investments=investments,
        )
