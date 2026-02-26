from __future__ import annotations

import json
import hashlib
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from atheria_economy import AtheriaEconomyEngine, EconomyState
from game_data import (
    CITIES,
    city_good_bias,
    goods_for_year,
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
    shipyard_for_year,
    title_steps_for_year,
)
from models import Building, CityEconomy, Investment, NPCTrader, Player, ProductionRecipe, Ship, WorldEconomy


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
        self.last_world_tick: Dict[str, int] = {"producing_buildings": 0, "npc_trades": 0}
        self._ensure_world_state(reset_world=True, reset_npcs=True)

    def _active_goods(self) -> Dict[str, Dict[str, float]]:
        return goods_for_year(self.current_year)

    def _active_good_names(self) -> List[str]:
        return list(self._active_goods().keys())

    def _active_shipyard(self) -> List[Tuple[str, int, int, int]]:
        return shipyard_for_year(self.current_year)

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

    def _default_city_buildings(self, city_name: str) -> List[Building]:
        if city_name == "Luebeck":
            return [Building(id="brewery", level=2), Building(id="fishery", level=1)]
        if city_name == "Bergen":
            return [Building(id="woodcutter", level=2), Building(id="fishery", level=1)]
        if city_name in {"Novgorod", "Riga"}:
            return [Building(id="salt_mine", level=1), Building(id="woodcutter", level=1)]
        return [Building(id="woodcutter", level=1)]

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
            city.buildings = sanitized_buildings or self._default_city_buildings(city_name)
            try:
                city.treasury = int(city.treasury)
            except (TypeError, ValueError):
                city.treasury = 0

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

    def _tick_world_production(self) -> int:
        self._ensure_world_state()
        active_goods = set(self._active_good_names())
        active_buildings = 0
        for city_name in CITIES:
            city = self._city_economy(city_name)
            for good_name, base_qty in BASE_CITY_CONSUMPTION.items():
                if good_name not in active_goods:
                    continue
                current = max(0, int(city.inventory.get(good_name, 0)))
                city.inventory[good_name] = max(0, current - max(0, int(base_qty)))

            for building in city.buildings:
                if not building.active:
                    continue
                recipe = PRODUCTION_RECIPES.get(building.id)
                if recipe is None:
                    continue
                level = max(1, int(building.level))
                can_run = True
                for good_name, qty in recipe.inputs.items():
                    required = max(0, int(qty)) * level
                    if city.inventory.get(good_name, 0) < required:
                        can_run = False
                        break
                if not can_run:
                    continue

                for good_name, qty in recipe.inputs.items():
                    required = max(0, int(qty)) * level
                    city.inventory[good_name] = max(0, int(city.inventory.get(good_name, 0)) - required)
                for good_name, qty in recipe.outputs.items():
                    produced = max(0, int(qty)) * level
                    city.inventory[good_name] = int(city.inventory.get(good_name, 0)) + produced
                city.treasury -= max(0, int(recipe.upkeep)) * level
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
        npc_trade_count = self._tick_world_npcs()
        # NPCs handeln vor dem Spieler. Danach bleiben Preise fuer den Monat gecached stabil.
        self._market_cache.clear()
        self.last_world_tick = {
            "producing_buildings": production_count,
            "npc_trades": npc_trade_count,
        }
        return dict(self.last_world_tick)

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
                f"NPC-Deals {world_tick.get('npc_trades', 0)} von {len(self.npcs)}"
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

        while True:
            print()
            print(
                "1) Status  2) Markt  3) Reise  4) Hafen  5) Investition  6) Runde Ende  7) Speichern  8) Missionen"
            )
            choice = self._ask_int("Auswahl: ", 1, 8)
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
        if player.alive:
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
        if player.investments:
            print("Laufende Investitionen:")
            for inv in player.investments:
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
        player.investments.append(Investment(amount=amount, turns_left=turns, risk=risk))
        print(f"{amount} Mark investiert. Auszahlung in {turns} Runde(n).")

    def _missions_menu(self, player: Player) -> None:
        self._init_missions(player)
        self._update_fleet_synergy(player)
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

    def _resolve_investments(self, player: Player) -> None:
        remaining: List[Investment] = []
        for inv in player.investments:
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
        player.investments = remaining

    def _end_of_turn(self, player: Player) -> None:
        if not player.alive:
            return

        self._init_missions(player)
        self._update_fleet_synergy(player)

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

    def _resolve_life_events(self, player: Player) -> None:
        if not player.married and player.age >= 23 and self._net_worth(player, self._market_prices(player.city)) > 12000:
            if self.rng.random() < 0.16:
                player.married = True
                player.chronicle.append(f"ANNO {self.current_year}: {player.name} ist den Bund der Ehe eingegangen.")
                print("Historie: in den Bund der Ehe eingegangen.")

        if player.married and self.rng.random() < 0.24:
            player.children += 1
            player.chronicle.append(f"ANNO {self.current_year}: Kind geboren.")
            print("Historie: geboren.")

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
        prices: Dict[str, int] = {}
        for good_name, params in self._active_goods().items():
            base = params["base_price"]
            volatility = params["volatility"]
            drift = self.rng.uniform(-volatility, volatility)
            good_macro = self.economy_state.good_factor(good_name)
            stock_factor = city_economy.scarcity_factor(good_name)
            price = int(
                base
                * city_good_bias(city, good_name)
                * sea_factor
                * (1.0 + drift)
                * global_price_level
                * city_macro
                * good_macro
                * stock_factor
            )
            prices[good_name] = max(6, price)

        self._market_cache[cache_key] = prices
        return prices

    def _init_missions(self, player: Player) -> None:
        missions = player.missions
        missions.setdefault("hanse_privileg", {"state": "inactive"})
        missions.setdefault("fleet_synergy", {"state": "inactive"})
        missions.setdefault("atheria_resonance", {"state": "inactive"})
        missions.setdefault("family_dynasty", {"state": "inactive"})

    def _month_index(self) -> int:
        return (self.current_year - STARTING_YEAR) * 12 + (self.current_month - 1)

    def _city_discount(self, player: Player, city: str) -> float:
        mission = player.missions.get("hanse_privileg", {})
        if mission.get("state") == "completed" and mission.get("city") == city:
            return float(mission.get("discount", HANSE_PRIVILEG_DISCOUNT))
        return 0.0

    def _update_missions_monthly(self, player: Player) -> None:
        self._init_missions(player)
        self._update_hanse_privileg(player, self._month_index())
        self._update_fleet_synergy(player)
        self._update_atheria_resonance(player)
        self._update_family_dynasty(player)

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
