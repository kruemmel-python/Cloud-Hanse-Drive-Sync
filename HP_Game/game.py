from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from atheria_economy import AtheriaEconomyEngine, EconomyState
from game_data import (
    CITIES,
    CITY_PRICE_BIAS,
    GOODS,
    SHIPYARD,
    MAX_PLAYERS,
    MAX_YEARS,
    MIN_NAME_LEN,
    SAVE_DIR,
    SAVE_FILE,
    SAVE_SLOT_COUNT,
    SEA_FACTORS,
    SEA_STATES,
    STARTING_AGE,
    STARTING_CASH,
    STARTING_DEBT,
    STARTING_REPUTATION,
    STARTING_YEAR,
    TITLE_STEPS,
)
from models import Investment, Player, Ship


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
        self.current_sea_state = "bewegte See"
        self._market_cache: Dict[Tuple[int, str, str], Dict[str, int]] = {}
        self.economy_engine = AtheriaEconomyEngine()
        self.economy_state = self.economy_engine.for_year(
            year=self.current_year,
            sea_state=self.current_sea_state,
            goods=GOODS.keys(),
            cities=CITIES,
        )

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

        while self.players and self.current_year < STARTING_YEAR + MAX_YEARS:
            self.current_sea_state = self.rng.choice(SEA_STATES)
            self._refresh_economy_for_year()
            print()
            print(f"ANNO {self.current_year} - {self.current_sea_state}")
            print(f"Atheria-Wirtschaft: {self.economy_state.summary}")
            print("=" * 60)
            for player in self.players:
                if player.alive:
                    self._play_turn(player)
            self.current_year += 1
            self.players = [p for p in self.players if p.alive]
            if not self.players:
                break
            if not self._ask_yes_no("Naechstes Jahr beginnen? (j/n): "):
                break

        self._show_final_ranking()

    def _print_banner(self) -> None:
        print("=" * 60)
        print("H A N S E  -  Python Portierung")
        print("Markt | Hafen | Kaper-Risiko | Schuldturm | Chronik")
        print("=" * 60)

    def _refresh_economy_for_year(self) -> None:
        self.economy_state = self.economy_engine.for_year(
            year=self.current_year,
            sea_state=self.current_sea_state,
            goods=GOODS.keys(),
            cities=CITIES,
        )
        self._market_cache.clear()

    def _start_new_game(self) -> None:
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
            ship = Ship(city=city, cargo={good: 0 for good in GOODS})
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
            players = raw.get("players", [])
            names = [str(entry.get("name", "?")) for entry in players[:3] if isinstance(entry, dict)]
            names_text = ", ".join(names) if names else "-"
            if isinstance(players, list) and len(players) > 3:
                names_text += ", ..."
            saved_at = str(raw.get("saved_at", "ohne Zeitstempel"))
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
            self.current_sea_state = str(raw.get("sea_state", "bewegte See"))
            self.players = [Player.from_dict(entry) for entry in raw["players"]]
            for player in self.players:
                for ship in player.ships:
                    for good_name in GOODS:
                        ship.cargo.setdefault(good_name, 0)
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
                    goods=GOODS.keys(),
                    cities=CITIES,
                )
            self._market_cache.clear()
            self.active_slot = slot
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _save_game(self, path: Path, slot: int | None = None) -> bool:
        payload = {
            "year": self.current_year,
            "sea_state": self.current_sea_state,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "players": [player.to_dict() for player in self.players],
            "atheria_economy_engine": self.economy_engine.to_dict(),
            "atheria_economy_state": self.economy_state.to_dict(),
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
            print(f"{player.name} sitzt im Schuldturm... ({player.turns_in_debt_tower} Runden verbleibend)")
            player.chronicle.append(f"ANNO {self.current_year}: {player.name} sitzt im Schuldturm.")
            self._end_of_turn(player)
            return

        while True:
            print()
            print("1) Status  2) Markt  3) Reise  4) Hafen  5) Investition  6) Runde Ende  7) Speichern")
            choice = self._ask_int("Auswahl: ", 1, 7)
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
        if player.alive:
            self._end_of_turn(player)

    def _show_status(self, player: Player) -> None:
        prices = self._market_prices(player.city)
        cargo_value = sum(prices[g] * q for g, q in player.cargo.items())
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
        print("Waren an Bord:")
        for good_name in GOODS:
            qty = player.cargo.get(good_name, 0)
            print(f"  {good_name:10} {qty:>4}  Preis {prices[good_name]:>4}")
        if player.investments:
            print("Laufende Investitionen:")
            for inv in player.investments:
                print(f"  {inv.amount} Mark | Rest {inv.turns_left} Runde(n) | Risiko {inv.risk}")
        print("-" * 60)

    def _market_menu(self, player: Player) -> None:
        while True:
            prices = self._market_prices(player.city)
            print()
            print("           MARKT")
            for idx, good_name in enumerate(GOODS, start=1):
                print(f"{idx}) {good_name:10} Preis {prices[good_name]:>4} | Lager {player.cargo[good_name]:>3}")
            print("8) Zurueck")
            action = self._ask_int("1-7 Kaufen/Verkaufen, 8 Zurueck: ", 1, 8)
            if action == 8:
                return
            good_name = list(GOODS.keys())[action - 1]
            if self._ask_yes_no(f"{good_name} kaufen? (j/n fuer verkaufen): "):
                self._buy_goods(player, good_name, prices[good_name])
            else:
                self._sell_goods(player, good_name, prices[good_name])

    def _buy_goods(self, player: Player, good_name: str, price: int) -> None:
        max_by_money = player.money // price
        max_qty = min(max_by_money, player.cargo_space_left)
        if max_qty <= 0:
            print("Nicht genug Mark oder kein Frachtraum frei.")
            return
        qty = self._ask_int(f"Anzahl kaufen (1-{max_qty}): ", 1, max_qty)
        cost = qty * price
        player.money -= cost
        player.cargo[good_name] += qty
        player.reputation = min(200, player.reputation + 1)
        print(f"Gekauft: {qty} {good_name} fuer {cost} Mark.")

    def _sell_goods(self, player: Player, good_name: str, price: int) -> None:
        stock = player.cargo.get(good_name, 0)
        if stock <= 0:
            print("Keine Ware auf Lager.")
            return
        qty = self._ask_int(f"Anzahl verkaufen (1-{stock}): ", 1, stock)
        revenue = qty * price
        player.cargo[good_name] -= qty
        player.money += revenue
        player.reputation = min(200, player.reputation + 1)
        print(f"Verkauft: {qty} {good_name} fuer {revenue} Mark.")

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
            print("4) Zurueck")
            choice = self._ask_int("Auswahl: ", 1, 4)
            if choice == 4:
                return
            if choice == 1:
                self._repair_ship(player, part="hull")
            elif choice == 2:
                self._repair_ship(player, part="rigging")
            elif choice == 3:
                self._buy_ship(player)

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
        shipyard = SHIPYARD
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

        growth = self.economy_state.global_growth
        price_level = self.economy_state.global_price_level

        heuer_factor = max(0.75, min(1.45, 0.88 + (price_level - 1.0) * 0.35))
        total_capacity = sum(ship.cargo_capacity for ship in player.ships)
        heuer = int((140 + total_capacity // 4) * heuer_factor)
        player.money -= heuer
        if player.debt > 0:
            debt_interest = max(1.01, min(1.10, 1.02 + (price_level - 1.0) * 0.05 - (growth - 1.0) * 0.02))
            player.debt = int(player.debt * debt_interest)

        if player.money < 0:
            player.debt += abs(player.money)
            player.money = 0

        if growth > 1.0:
            bonus = int((growth - 1.0) * (120 + player.reputation * 3))
            if bonus > 0:
                player.money += bonus
                player.chronicle.append(f"ANNO {self.current_year}: Wirtschaftsaufschwung (+{bonus} Mark).")
        elif growth < 0.95 and player.money > 0:
            recession_loss = int((0.95 - growth) * max(120, player.money * 0.05))
            if recession_loss > 0:
                player.money = max(0, player.money - recession_loss)
                player.chronicle.append(f"ANNO {self.current_year}: Konjunkturflaute (-{recession_loss} Mark).")

        if player.money > 2500 and player.debt > 0:
            repayment = min(player.debt, max(300, player.money // 5))
            player.money -= repayment
            player.debt -= repayment

        if player.debt > 17000 and self.rng.random() < 0.35:
            turns = self.rng.randint(1, 3)
            player.turns_in_debt_tower = turns
            player.chronicle.append(
                f"ANNO {self.current_year}: {player.name} fuer {turns} Jahre im Schuldturm."
            )
            print(f"Schuldturm: {turns} Runde(n) Haft.")

        player.age += 1
        self._resolve_life_events(player)
        self._update_title(player)

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
                player.alive = False
                player.chronicle.append(f"ANNO {self.current_year}: Tod des Vorfahren.")
                print("Tod des Vorfahren.")

    def _update_title(self, player: Player) -> None:
        worth = self._net_worth(player, self._market_prices(player.city))
        new_index = 0
        for idx, (threshold, _, _) in enumerate(TITLE_STEPS):
            if worth >= threshold:
                new_index = idx
        if new_index > player.title_index:
            player.title_index = new_index
            title = self._title_for(player)
            player.chronicle.append(f"ANNO {self.current_year}: In den Stand '{title}' erhoben.")
            print(f"Aufstieg: {title}")

    def _market_prices(self, city: str) -> Dict[str, int]:
        cache_key = (self.current_year, self.current_sea_state, city)
        if cache_key in self._market_cache:
            return self._market_cache[cache_key]

        sea_factor = SEA_FACTORS[self.current_sea_state]
        city_bias = CITY_PRICE_BIAS[city]
        city_macro = self.economy_state.city_factor(city)
        global_price_level = self.economy_state.global_price_level
        prices: Dict[str, int] = {}
        for good_name, params in GOODS.items():
            base = params["base_price"]
            volatility = params["volatility"]
            drift = self.rng.uniform(-volatility, volatility)
            good_macro = self.economy_state.good_factor(good_name)
            price = int(
                base
                * city_bias[good_name]
                * sea_factor
                * (1.0 + drift)
                * global_price_level
                * city_macro
                * good_macro
            )
            prices[good_name] = max(6, price)

        self._market_cache[cache_key] = prices
        return prices

    def _net_worth(self, player: Player, prices: Dict[str, int]) -> int:
        cargo_value = 0
        for ship in player.ships:
            cargo_value += sum(prices[good_name] * qty for good_name, qty in ship.cargo.items())
        for goods in player.warehouses.values():
            cargo_value += sum(prices[good_name] * qty for good_name, qty in goods.items())
        fleet_value = sum(ship.value for ship in player.ships)
        return player.money + cargo_value + fleet_value - player.debt + player.reputation * 150

    def _title_for(self, player: Player) -> str:
        _, male, female = TITLE_STEPS[min(player.title_index, len(TITLE_STEPS) - 1)]
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
