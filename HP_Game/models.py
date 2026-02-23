from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Ship:
    name: str = "Kogge"
    cargo_capacity: int = 120
    hull: int = 100
    rigging: int = 100
    value: int = 3200

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Ship":
        return cls(
            name=str(data.get("name", "Kogge")),
            cargo_capacity=int(data.get("cargo_capacity", 120)),
            hull=int(data.get("hull", 100)),
            rigging=int(data.get("rigging", 100)),
            value=int(data.get("value", 3200)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cargo_capacity": self.cargo_capacity,
            "hull": self.hull,
            "rigging": self.rigging,
            "value": self.value,
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
    ship: Ship = field(default_factory=Ship)
    cargo: Dict[str, int] = field(default_factory=dict)
    alive: bool = True
    married: bool = False
    children: int = 0
    turns_in_debt_tower: int = 0
    chronicle: List[str] = field(default_factory=list)
    investments: List[Investment] = field(default_factory=list)

    @property
    def total_cargo(self) -> int:
        return sum(self.cargo.values())

    @property
    def cargo_space_left(self) -> int:
        return self.ship.cargo_capacity - self.total_cargo

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
            "ship": self.ship.to_dict(),
            "cargo": dict(self.cargo),
            "alive": self.alive,
            "married": self.married,
            "children": self.children,
            "turns_in_debt_tower": self.turns_in_debt_tower,
            "chronicle": list(self.chronicle),
            "investments": [inv.to_dict() for inv in self.investments],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        ship = Ship.from_dict(data.get("ship", {}))
        investments = [Investment.from_dict(entry) for entry in data.get("investments", [])]
        cargo = {str(key): int(value) for key, value in data.get("cargo", {}).items()}
        return cls(
            name=str(data.get("name", "Unbekannt")),
            gender=str(data.get("gender", "m")),
            city=str(data.get("city", "Luebeck")),
            money=int(data.get("money", 0)),
            debt=int(data.get("debt", 0)),
            reputation=int(data.get("reputation", 0)),
            age=int(data.get("age", 20)),
            title_index=int(data.get("title_index", 0)),
            ship=ship,
            cargo=cargo,
            alive=bool(data.get("alive", True)),
            married=bool(data.get("married", False)),
            children=int(data.get("children", 0)),
            turns_in_debt_tower=int(data.get("turns_in_debt_tower", 0)),
            chronicle=[str(item) for item in data.get("chronicle", [])],
            investments=investments,
        )
