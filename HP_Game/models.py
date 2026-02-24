from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    alive: bool = True
    married: bool = False
    children: int = 0
    turns_in_debt_tower: int = 0
    chronicle: List[str] = field(default_factory=list)
    investments: List[Investment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.ships:
            self.ships = [Ship(city=self.city)]
        self.active_ship_index = max(0, min(self.active_ship_index, len(self.ships) - 1))

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
            "alive": self.alive,
            "married": self.married,
            "children": self.children,
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

        investments = [Investment.from_dict(entry) for entry in data.get("investments", [])]
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
            alive=bool(data.get("alive", True)),
            married=bool(data.get("married", False)),
            children=int(data.get("children", 0)),
            turns_in_debt_tower=int(data.get("turns_in_debt_tower", 0)),
            chronicle=[str(item) for item in data.get("chronicle", [])],
            investments=investments,
        )
