from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _deepcopy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class WorldSimulator:
    """Core-Engine fuer Hanse/Gilde-Hybrid mit Neuro- und Integritaetslogik."""

    IMMUNITY_COOLDOWN_SECONDS = 28.0
    IMMUNITY_SEVERE_THRESHOLD = 1.9
    IMMUNITY_SUSTAINED_THRESHOLD = 1.1

    SOPHIA_POSITIVE_TERMS = [
        "kooperation",
        "resonanz",
        "ausgleich",
        "vertrauensnetz",
        "signal",
        "gewinngemeinschaft",
        "frachtfluss",
        "stabilitaet",
    ]
    SOPHIA_DEFENSIVE_TERMS = [
        "misstrauen",
        "preissturz",
        "abwertung",
        "engpass",
        "sperre",
        "sanktion",
        "druck",
        "bruechigkeit",
    ]

    NPC_ARCHETYPE_GOODS = {
        "broker": ["Tuch", "Wein", "Salz"],
        "captain": ["Holz", "Hering", "Salz"],
        "quartermaster": ["Getreide", "Holz", "Hering"],
        "scribe": ["Tuch", "Salz", "Wein"],
        "fur_baron": ["Pelze", "Wein", "Salz"],
    }

    SOPHIA_DOPAMINE_TERMS = ["spekulation", "risikopraemie", "dominanz", "sprungmarge"]
    SOPHIA_OXYTOCIN_TERMS = ["pakt", "beistand", "gildenrat", "verbund"]
    SOPHIA_RESONANCE_TERMS = ["decoq", "signalnetz", "kohaerenz", "resonanzkern"]
    SOPHIA_IMMUNITY_TERMS = ["immunantwort", "marktkorrektur", "ausschluss", "sanktionswelle"]

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    # ---------- Public action entry points ----------
    def apply_trade_action(self, state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        world = _deepcopy_dict(state)

        player_id = self._required_text(payload, "player_id")
        city_name = self._required_text(payload, "city")
        good_name = self._required_text(payload, "good")
        side = str(payload.get("side", "buy")).lower()
        quantity = int(payload.get("quantity", 1))
        display_name = str(payload.get("display_name") or player_id)
        guild_id = str(payload.get("guild_id") or "merchant_guild")
        route_id = payload.get("route_id")

        if quantity < 1:
            raise ValueError("quantity muss >= 1 sein.")
        if side not in {"buy", "sell"}:
            raise ValueError("side muss 'buy' oder 'sell' sein.")

        economy = self._get_required_dict(world, "economy")
        cities = self._get_required_dict(economy, "cities")
        goods = self._get_required_dict(economy, "goods")
        if city_name not in cities:
            raise ValueError(f"Unbekannte Stadt: {city_name}")
        if good_name not in goods:
            raise ValueError(f"Unbekannte Ware: {good_name}")

        player = self._ensure_player(world, player_id, display_name, city_name, guild_id)
        city = self._get_required_dict(cities, city_name)
        city_inventory = self._get_required_dict(city, "inventory")
        player_inventory = self._get_required_dict(player, "inventory")

        for candidate_good in goods.keys():
            player_inventory.setdefault(candidate_good, 0.0)
            city_inventory.setdefault(candidate_good, 0.0)

        unit_price = self.city_good_price(world, city_name, good_name)
        notional = unit_price * quantity

        if side == "buy":
            available = float(city_inventory.get(good_name, 0.0))
            if available < quantity:
                raise ValueError(
                    f"Stadtlager reicht nicht aus ({available:.0f} verfuegbar)."
                )
            if float(player.get("cash", 0.0)) < notional:
                raise ValueError("Nicht genug Bargeld fuer den Kauf.")
            city_inventory[good_name] = available - quantity
            player_inventory[good_name] = float(player_inventory.get(good_name, 0.0)) + quantity
            player["cash"] = round(float(player.get("cash", 0.0)) - notional, 2)
            player["reputation"] = clamp(float(player.get("reputation", 0.5)) + 0.004, 0.0, 1.0)
            self._shift_good_supply_demand(goods[good_name], demand_delta=quantity * 1.2, supply_delta=-quantity * 0.55)
            self._adjust_neuro_after_trade(world, quantity=quantity, side="buy")
        else:
            held = float(player_inventory.get(good_name, 0.0))
            if held < quantity:
                raise ValueError(
                    f"Spieler besitzt nicht genug Ware ({held:.0f} verfuegbar)."
                )
            player_inventory[good_name] = held - quantity
            city_inventory[good_name] = float(city_inventory.get(good_name, 0.0)) + quantity
            player["cash"] = round(float(player.get("cash", 0.0)) + notional, 2)
            player["reputation"] = clamp(float(player.get("reputation", 0.5)) + 0.003, 0.0, 1.0)
            self._shift_good_supply_demand(goods[good_name], demand_delta=-quantity * 0.65, supply_delta=quantity * 1.1)
            self._adjust_neuro_after_trade(world, quantity=quantity, side="sell")

        player["home_city"] = city_name
        player["last_action_at"] = utc_now()

        if isinstance(route_id, str):
            self._route_traffic_bump(world, route_id, quantity)

        self._append_event(
            world,
            kind="trade",
            actor_id=player_id,
            payload={
                "city": city_name,
                "good": good_name,
                "side": side,
                "quantity": quantity,
                "unit_price": round(unit_price, 2),
                "notional": round(notional, 2),
                "route_id": route_id,
            },
        )

        self.step_world(world, actor_id=player_id, reason="trade")
        return world

    def apply_guild_action(self, state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        world = _deepcopy_dict(state)

        player_id = self._required_text(payload, "player_id")
        guild_id = str(payload.get("guild_id") or "merchant_guild")
        action_type = str(payload.get("action_type", "cohesion_drive")).lower()
        intensity = clamp(float(payload.get("intensity", 0.25)), 0.01, 1.0)

        guilds = self._get_required_dict(world, "guilds")
        if guild_id not in guilds:
            raise ValueError(f"Unbekannte Gilde: {guild_id}")

        guild = self._get_required_dict(guilds, guild_id)
        neuro = self._get_required_dict(world, "neuro_state")
        politics = self._get_required_dict(world, "politics")

        if action_type == "cohesion_drive":
            guild["cohesion"] = clamp(float(guild.get("cohesion", 0.5)) + 0.1 * intensity, 0.0, 1.0)
            guild["trust"] = clamp(float(guild.get("trust", 0.5)) + 0.12 * intensity, 0.0, 1.0)
            guild["rank_points"] = int(guild.get("rank_points", 0)) + int(220 * intensity)
            guild["treasury"] = round(float(guild.get("treasury", 0.0)) - 200 * intensity, 2)
            neuro["oxytocin"] = clamp(float(neuro.get("oxytocin", 0.5)) + 0.08 * intensity, 0.0, 1.0)
            neuro["dopamine"] = clamp(float(neuro.get("dopamine", 0.5)) - 0.02 * intensity, 0.0, 1.0)
        elif action_type == "market_raid":
            guild["cohesion"] = clamp(float(guild.get("cohesion", 0.5)) - 0.03 * intensity, 0.0, 1.0)
            guild["trust"] = clamp(float(guild.get("trust", 0.5)) - 0.06 * intensity, 0.0, 1.0)
            guild["rank_points"] = int(guild.get("rank_points", 0)) + int(320 * intensity)
            guild["treasury"] = round(float(guild.get("treasury", 0.0)) + 450 * intensity, 2)
            neuro["dopamine"] = clamp(float(neuro.get("dopamine", 0.5)) + 0.12 * intensity, 0.0, 1.0)
            neuro["oxytocin"] = clamp(float(neuro.get("oxytocin", 0.5)) - 0.08 * intensity, 0.0, 1.0)
            politics["corruption"] = clamp(float(politics.get("corruption", 0.2)) + 0.03 * intensity, 0.0, 1.0)
        elif action_type == "trust_pact":
            guild["cohesion"] = clamp(float(guild.get("cohesion", 0.5)) + 0.06 * intensity, 0.0, 1.0)
            guild["trust"] = clamp(float(guild.get("trust", 0.5)) + 0.16 * intensity, 0.0, 1.0)
            guild["treasury"] = round(float(guild.get("treasury", 0.0)) - 120 * intensity, 2)
            neuro["oxytocin"] = clamp(float(neuro.get("oxytocin", 0.5)) + 0.11 * intensity, 0.0, 1.0)
            politics["legitimacy"] = clamp(float(politics.get("legitimacy", 0.6)) + 0.04 * intensity, 0.0, 1.0)
        else:
            raise ValueError(
                "action_type muss einer von cohesion_drive | market_raid | trust_pact sein."
            )

        self._append_event(
            world,
            kind="guild_action",
            actor_id=player_id,
            payload={
                "guild_id": guild_id,
                "action_type": action_type,
                "intensity": intensity,
            },
        )

        self.step_world(world, actor_id=player_id, reason="guild")
        return world

    def apply_player_action(self, state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        world = _deepcopy_dict(state)

        action_type = str(payload.get("action_type", "create")).strip().lower()
        player_id = self._required_text(payload, "player_id")

        if action_type == "create":
            display_name = str(payload.get("display_name") or player_id).strip()
            home_city = str(payload.get("home_city") or payload.get("city") or "Luebeck").strip()
            guild_id = str(payload.get("guild_id") or "free_merchants").strip()
            starting_cash = float(payload.get("starting_cash", 6000.0))
            starting_debt = float(payload.get("starting_debt", 1800.0))

            players = self._get_required_dict(world, "players")
            if player_id in players:
                raise ValueError(f"Spieler '{player_id}' existiert bereits.")

            self._create_player_record(
                world,
                player_id=player_id,
                display_name=display_name,
                city_name=home_city,
                guild_id=guild_id,
                starting_cash=starting_cash,
                starting_debt=starting_debt,
            )
            self._append_event(
                world,
                kind="player_create",
                actor_id=player_id,
                payload={
                    "player_id": player_id,
                    "display_name": display_name,
                    "home_city": home_city,
                    "guild_id": guild_id,
                },
            )
            self.step_world(world, actor_id=player_id, reason="player_create")
            return world

        if action_type == "join_guild":
            guild_id = self._required_text(payload, "guild_id")
            player = self._require_player(world, player_id)
            old_guild = str(player.get("guild_id", "free_merchants"))
            if old_guild == guild_id:
                raise ValueError(f"Spieler '{player_id}' ist bereits in '{guild_id}'.")
            self._ensure_guild_exists(world, guild_id, auto_create=False)
            self._transfer_guild_membership(world, player, from_guild=old_guild, to_guild=guild_id)
            player["last_action_at"] = utc_now()
            self._append_event(
                world,
                kind="guild_join",
                actor_id=player_id,
                payload={"from_guild": old_guild, "to_guild": guild_id},
            )
            self.step_world(world, actor_id=player_id, reason="guild_join")
            return world

        if action_type == "leave_guild":
            fallback_guild = str(payload.get("fallback_guild") or "free_merchants").strip()
            player = self._require_player(world, player_id)
            old_guild = str(player.get("guild_id", "free_merchants"))
            if old_guild == fallback_guild:
                raise ValueError(f"Spieler '{player_id}' ist bereits in '{fallback_guild}'.")
            self._ensure_guild_exists(world, fallback_guild, auto_create=True)
            self._transfer_guild_membership(world, player, from_guild=old_guild, to_guild=fallback_guild)
            player["last_action_at"] = utc_now()
            self._append_event(
                world,
                kind="guild_leave",
                actor_id=player_id,
                payload={"from_guild": old_guild, "to_guild": fallback_guild},
            )
            self.step_world(world, actor_id=player_id, reason="guild_leave")
            return world

        raise ValueError("action_type muss create | join_guild | leave_guild sein.")

    def validate_decog_immunity(self, state: Dict[str, Any], actor_id: str = "validator") -> Dict[str, Any]:
        baseline = _deepcopy_dict(state)
        neuro_baseline = self._get_required_dict(baseline, "neuro_state")

        def scenario_price_spike(world: Dict[str, Any]) -> None:
            goods = self._get_required_dict(self._get_required_dict(world, "economy"), "goods")
            for raw_good in goods.values():
                if isinstance(raw_good, dict):
                    base = float(raw_good.get("base_price", 1.0))
                    raw_good["price"] = round(base * 9.5, 4)
                    break

        def scenario_negative_inventory(world: Dict[str, Any]) -> None:
            goods = self._get_required_dict(self._get_required_dict(world, "economy"), "goods")
            for raw_good in goods.values():
                if isinstance(raw_good, dict):
                    raw_good["supply"] = -80.0
                    raw_good["demand"] = max(1.0, float(raw_good.get("demand", 1.0)))
                    break

        def scenario_event_spam(world: Dict[str, Any]) -> None:
            events = world.get("events")
            if not isinstance(events, list):
                events = []
                world["events"] = events
            meta = self._get_required_dict(world, "meta")
            start_id = int(meta.get("last_event_id", 0))
            now = datetime.now(timezone.utc)
            for idx in range(10):
                event_id = start_id + idx + 1
                at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                events.append(
                    {
                        "id": event_id,
                        "kind": "trade",
                        "actor_id": actor_id,
                        "at": at,
                        "payload": {
                            "city": "Luebeck",
                            "good": "Salz",
                            "side": "buy" if idx % 2 == 0 else "sell",
                            "quantity": 180,
                            "notional": 19000 + idx * 2000,
                        },
                    }
                )
            meta["last_event_id"] = start_id + 10

        def scenario_cashflow(world: Dict[str, Any]) -> None:
            players = self._get_required_dict(world, "players")
            economy = self._get_required_dict(world, "economy")
            cities = self._get_required_dict(economy, "cities")
            home_city = next(iter(cities.keys()), "Luebeck")
            player = self._ensure_player(world, actor_id, "Validator", home_city, "merchant_guild")
            player["cash"] = 6_500_000.0
            player["debt"] = 4_900_000.0

        scenarios: list[tuple[str, str, Any]] = [
            ("price_spike", "Extreme Preismanipulation", scenario_price_spike),
            ("negative_inventory", "Negative Lagerwerte", scenario_negative_inventory),
            ("event_spam", "Wash-Trade/Event-Spam", scenario_event_spam),
            ("impossible_cashflow", "Unplausible Bilanzspruenge", scenario_cashflow),
        ]

        reports = []
        for scenario_id, title, mutate in scenarios:
            probe = _deepcopy_dict(baseline)
            pre_neuro = self._get_required_dict(probe, "neuro_state")
            pre_immunity = float(pre_neuro.get("immunity_level", 0.0))
            pre_events = len(self._get_required_dict(probe, "integrity").get("immunity_events", []))

            mutate(probe)
            self._run_decog_resonance_guard(probe, actor_id=actor_id)

            post_neuro = self._get_required_dict(probe, "neuro_state")
            integrity = self._get_required_dict(probe, "integrity")
            flags = integrity.get("manipulation_flags", {})
            immunity_events = integrity.get("immunity_events", [])
            post_immunity = float(post_neuro.get("immunity_level", 0.0))
            triggered = post_immunity > pre_immunity or (
                isinstance(immunity_events, list) and len(immunity_events) > pre_events
            )
            reports.append(
                {
                    "scenario_id": scenario_id,
                    "title": title,
                    "triggered": triggered,
                    "anomaly_score": float(post_neuro.get("anomaly_score", 0.0)),
                    "immunity_before": pre_immunity,
                    "immunity_after": post_immunity,
                    "flags": flags if isinstance(flags, dict) else {},
                }
            )

        passed = all(bool(item["triggered"]) for item in reports)
        return {
            "validated_at": utc_now(),
            "actor_id": actor_id,
            "passed": passed,
            "baseline": {
                "dopamine": float(neuro_baseline.get("dopamine", 0.0)),
                "oxytocin": float(neuro_baseline.get("oxytocin", 0.0)),
                "resonance": float(neuro_baseline.get("decoq_resonance", 0.0)),
                "immunity_level": float(neuro_baseline.get("immunity_level", 0.0)),
            },
            "scenarios": reports,
        }

    def step_world(self, state: Dict[str, Any], *, actor_id: str | None, reason: str) -> None:
        self._run_sophia_protocol(state, reason=reason)
        self._reprice_goods(state)
        self._refresh_macro_indexes(state)
        self._run_decog_resonance_guard(state, actor_id=actor_id)
        self._touch_meta(state)

    def build_market_view(self, state: Dict[str, Any]) -> Dict[str, Any]:
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        cities = self._get_required_dict(economy, "cities")
        routes = economy.get("trade_routes", [])

        global_goods = {
            good: {
                "price": round(float(values.get("price", 0.0)), 2),
                "momentum": round(float(values.get("momentum", 0.0)), 4),
                "supply": round(float(values.get("supply", 0.0)), 2),
                "demand": round(float(values.get("demand", 0.0)), 2),
            }
            for good, values in goods.items()
            if isinstance(values, dict)
        }

        city_prices: Dict[str, Dict[str, float]] = {}
        for city_name in cities:
            city_prices[city_name] = {}
            for good_name in goods:
                city_prices[city_name][good_name] = round(
                    self.city_good_price(state, city_name, good_name), 2
                )

        return {
            "global_goods": global_goods,
            "city_prices": city_prices,
            "routes": routes,
        }

    # ---------- Pricing ----------
    def city_good_price(self, state: Dict[str, Any], city_name: str, good_name: str) -> float:
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        cities = self._get_required_dict(economy, "cities")
        neuro = self._get_required_dict(state, "neuro_state")
        if city_name not in cities or good_name not in goods:
            return 0.0

        good = self._get_required_dict(goods, good_name)
        city = self._get_required_dict(cities, city_name)
        demand_bias = float(self._get_required_dict(city, "demand_bias").get(good_name, 1.0))
        supply_bias = float(self._get_required_dict(city, "supply_bias").get(good_name, 1.0))
        route_pressure = float(city.get("route_pressure", 0.3))
        inventory_level = float(self._get_required_dict(city, "inventory").get(good_name, 0.0))

        global_price = float(good.get("price", good.get("base_price", 1.0)))
        local_pressure = clamp(demand_bias / max(0.1, supply_bias), 0.35, 2.4)
        inventory_pressure = clamp(1.0 + ((120.0 - min(120.0, inventory_level)) / 120.0) * 0.35, 0.7, 1.5)
        neural = 1.0 + (float(neuro.get("dopamine", 0.5)) - 0.5) * 0.6 - (
            float(neuro.get("oxytocin", 0.5)) - 0.5
        ) * 0.25
        logistics = 1.0 + route_pressure * 0.18
        return max(2.0, global_price * local_pressure * inventory_pressure * neural * logistics)

    def _reprice_goods(self, state: Dict[str, Any]) -> None:
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        neuro = self._get_required_dict(state, "neuro_state")

        dopamine = float(neuro.get("dopamine", 0.5))
        oxytocin = float(neuro.get("oxytocin", 0.5))
        resonance = float(neuro.get("decoq_resonance", 0.2))
        immunity = float(neuro.get("immunity_level", 0.0))
        market_shock = float(economy.get("market_shock", 0.0))
        global_demand = float(economy.get("global_demand_index", 1.0))
        global_supply = float(economy.get("global_supply_index", 1.0))

        for raw_good in goods.values():
            if not isinstance(raw_good, dict):
                continue
            good = raw_good
            base = float(good.get("base_price", 1.0))
            current = float(good.get("price", base))
            raw_supply = max(1.0, float(good.get("supply", 1.0)))
            raw_demand = max(1.0, float(good.get("demand", 1.0)))
            bounded_supply = clamp(raw_supply, 140.0, 3200.0)
            bounded_demand = clamp(raw_demand, 140.0, 3200.0)
            # Entschaerft runaway-Zustaende, damit Handel wieder spuerbar wirkt.
            supply = raw_supply * 0.55 + bounded_supply * 0.45
            demand = raw_demand * 0.55 + bounded_demand * 0.45
            volatility = clamp(float(good.get("volatility", 0.2)), 0.0, 1.0)

            scarcity_ratio = (demand * global_demand) / (supply * global_supply)
            scarcity_factor = clamp(math.pow(max(0.05, scarcity_ratio), 0.36), 0.45, 2.2)
            aggression_factor = 1.0 + (dopamine - 0.5) * 1.25
            trust_factor = 1.0 - (oxytocin - 0.5) * 0.56
            resonance_factor = 1.0 + resonance * math.tanh((dopamine - oxytocin) * 2.6) * 0.42
            immunity_factor = 1.0 - immunity * 0.48
            shock_factor = 1.0 + market_shock * 0.35
            noise_band = volatility * (0.06 + dopamine * 0.2 + immunity * 0.12)
            noise = self.rng.uniform(-noise_band, noise_band)

            raw_target = (
                base
                * scarcity_factor
                * aggression_factor
                * trust_factor
                * resonance_factor
                * immunity_factor
                * shock_factor
                * (1.0 + noise)
            )
            target = clamp(raw_target, base * 0.35, base * 4.8)
            smoothed = current * 0.66 + target * 0.34
            momentum = clamp((smoothed - current) / max(1.0, current), -1.0, 1.0)

            good["price"] = round(smoothed, 4)
            good["momentum"] = round(momentum, 4)
            good["supply"] = round(max(0.0, supply), 4)
            good["demand"] = round(max(0.0, demand), 4)

        economy["last_tick_at"] = utc_now()

    # ---------- Sophia protocol ----------
    def _run_sophia_protocol(self, state: Dict[str, Any], *, reason: str) -> None:
        economy = self._get_required_dict(state, "economy")
        cities = self._get_required_dict(economy, "cities")
        goods = self._get_required_dict(economy, "goods")
        npcs = self._get_required_dict(state, "npcs")
        neuro = self._get_required_dict(state, "neuro_state")
        dopamine = float(neuro.get("dopamine", 0.5))
        oxytocin = float(neuro.get("oxytocin", 0.5))

        for raw_npc in npcs.values():
            if not isinstance(raw_npc, dict):
                continue
            npc = raw_npc
            city_name = str(npc.get("city", ""))
            city = cities.get(city_name)
            if not isinstance(city, dict):
                continue

            old_capital = float(npc.get("capital", 0.0))
            city_signal = (
                float(city.get("wealth", 1.0)) * 0.35
                + float(city.get("stability", 0.5)) * 0.45
                + float(city.get("guild_influence", 0.5)) * 0.20
            )
            success = clamp(
                0.48 + (city_signal - 0.6) * 0.5 + (oxytocin - dopamine) * 0.25 + self.rng.uniform(-0.12, 0.12),
                0.0,
                1.0,
            )
            delta_capital = (success - 0.45) * (200.0 + old_capital * 0.05)
            npc["capital"] = round(max(0.0, old_capital + delta_capital), 2)
            npc["trust"] = round(
                clamp(float(npc.get("trust", 0.5)) + (success - 0.5) * 0.06 + (oxytocin - 0.5) * 0.08, 0.0, 1.0),
                4,
            )
            npc["aggression"] = round(
                clamp(
                    float(npc.get("aggression", 0.5)) + (dopamine - 0.5) * 0.08 - (success - 0.5) * 0.06,
                    0.0,
                    1.0,
                ),
                4,
            )

            self._inject_sophia_goal_variants(npc, neuro, city_signal)
            goals = npc.get("goals", [])
            if isinstance(goals, list) and goals:
                self._evolve_npc_goals(goals, success)
                chosen_goal = self._choose_npc_goal(goals)
            else:
                chosen_goal = {"kind": "profit"}

            focus_goods = self.NPC_ARCHETYPE_GOODS.get(
                str(npc.get("archetype", "")),
                list(goods.keys()),
            )
            if not focus_goods:
                focus_goods = list(goods.keys())
            focus_good = self._select_focus_good(goods, focus_goods, chosen_goal)
            if focus_good in goods and isinstance(goods[focus_good], dict):
                good = goods[focus_good]
                pressure = (float(npc.get("aggression", 0.5)) - 0.45) * 36.0
                if chosen_goal.get("kind") in {"stability", "cohesion"}:
                    pressure *= -0.7
                if pressure > 0:
                    good["demand"] = max(0.0, float(good.get("demand", 0.0)) + pressure)
                else:
                    good["supply"] = max(0.0, float(good.get("supply", 0.0)) + abs(pressure))

            self._evolve_npc_vocabulary(
                npc,
                success,
                neuro=neuro,
                focus_good=focus_good,
                chosen_goal=chosen_goal,
            )
            npc["last_utterance"] = self._npc_utterance(
                npc,
                focus_good,
                city_name,
                reason,
                neuro=neuro,
                chosen_goal=chosen_goal,
            )
            self._append_npc_memory(npc, state, success, focus_good, chosen_goal=chosen_goal)

    def _inject_sophia_goal_variants(self, npc: Dict[str, Any], neuro: Dict[str, Any], city_signal: float) -> None:
        goals = npc.get("goals")
        if not isinstance(goals, list):
            goals = []
            npc["goals"] = goals

        existing_ids = {
            str(goal.get("id"))
            for goal in goals
            if isinstance(goal, dict) and goal.get("id") is not None
        }

        dopamine = float(neuro.get("dopamine", 0.5))
        oxytocin = float(neuro.get("oxytocin", 0.5))
        resonance = float(neuro.get("decoq_resonance", 0.2))
        immunity = float(neuro.get("immunity_level", 0.0))

        candidates = [
            (
                "momentum_harvest",
                "profit",
                dopamine > 0.62,
                0.14 + (dopamine - 0.62) * 0.4,
            ),
            (
                "coalition_weaving",
                "cohesion",
                oxytocin > 0.66,
                0.13 + (oxytocin - 0.66) * 0.35,
            ),
            (
                "resonance_arbitrage",
                "logistics",
                resonance > 0.52,
                0.12 + (resonance - 0.52) * 0.38,
            ),
            (
                "compliance_shell",
                "politics",
                immunity > 0.14,
                0.11 + immunity * 0.28,
            ),
            (
                "city_stabilizer",
                "stability",
                city_signal < 0.56,
                0.12 + (0.56 - city_signal) * 0.3,
            ),
        ]

        for goal_id, kind, condition, weight in candidates:
            if not condition or goal_id in existing_ids:
                continue
            goals.append(
                {
                    "id": goal_id,
                    "kind": kind,
                    "weight": round(clamp(weight, 0.06, 0.4), 4),
                    "progress": round(clamp(0.15 + self.rng.uniform(0.0, 0.25), 0.0, 1.0), 4),
                }
            )
            existing_ids.add(goal_id)

        # Begrenze die Zielmenge und entferne die schwaechsten Ziele.
        if len(goals) > 8:
            scored = [goal for goal in goals if isinstance(goal, dict)]
            scored.sort(key=lambda g: float(g.get("weight", 0.0)), reverse=True)
            npc["goals"] = scored[:8]

    def _select_focus_good(
        self,
        goods: Dict[str, Any],
        focus_goods: list[str],
        chosen_goal: Dict[str, Any],
    ) -> str:
        candidates = [good for good in focus_goods if good in goods and isinstance(goods.get(good), dict)]
        if not candidates:
            candidates = [good for good in goods.keys() if isinstance(goods.get(good), dict)]
        if not candidates:
            return "Salz"

        goal_kind = str(chosen_goal.get("kind", "profit"))
        if goal_kind in {"stability", "cohesion", "politics"}:
            # Defensive Ziele bevorzugen geringes Momentum.
            return min(candidates, key=lambda g: abs(float(goods[g].get("momentum", 0.0))))
        if goal_kind in {"logistics"}:
            # Logistik schaut auf Nachfrage-Ungleichgewichte.
            return max(
                candidates,
                key=lambda g: float(goods[g].get("demand", 0.0)) - float(goods[g].get("supply", 0.0)),
            )
        # Profit fokussiert trendstarke Gueter.
        return max(candidates, key=lambda g: abs(float(goods[g].get("momentum", 0.0))))

    def _evolve_npc_goals(self, goals: list[Any], success: float) -> None:
        for goal in goals:
            if not isinstance(goal, dict):
                continue
            weight = float(goal.get("weight", 0.5))
            progress = float(goal.get("progress", 0.3))
            delta_progress = (success - 0.45) * 0.12 + self.rng.uniform(-0.02, 0.02)
            goal["progress"] = round(clamp(progress + delta_progress, 0.0, 1.0), 4)

            if goal.get("kind") in {"profit", "logistics"}:
                weight += (success - 0.5) * 0.06
            elif goal.get("kind") in {"cohesion", "stability", "politics"}:
                weight += (0.52 - success) * 0.04
            goal["weight"] = round(clamp(weight, 0.05, 0.95), 4)

        total = sum(float(goal.get("weight", 0.1)) for goal in goals if isinstance(goal, dict))
        if total <= 0:
            return
        for goal in goals:
            if not isinstance(goal, dict):
                continue
            goal["weight"] = round(float(goal.get("weight", 0.0)) / total, 4)

    def _choose_npc_goal(self, goals: list[Any]) -> Dict[str, Any]:
        weighted = []
        for goal in goals:
            if isinstance(goal, dict):
                weighted.append((goal, max(0.001, float(goal.get("weight", 0.1)))))
        if not weighted:
            return {"kind": "profit"}
        total = sum(weight for _, weight in weighted)
        roll = self.rng.uniform(0.0, total)
        cursor = 0.0
        for goal, weight in weighted:
            cursor += weight
            if roll <= cursor:
                return goal
        return weighted[-1][0]

    def _evolve_npc_vocabulary(
        self,
        npc: Dict[str, Any],
        success: float,
        *,
        neuro: Dict[str, Any],
        focus_good: str,
        chosen_goal: Dict[str, Any],
    ) -> None:
        vocabulary = npc.get("vocabulary")
        if not isinstance(vocabulary, list):
            vocabulary = []
            npc["vocabulary"] = vocabulary

        term_pool = list(self.SOPHIA_POSITIVE_TERMS if success >= 0.55 else self.SOPHIA_DEFENSIVE_TERMS)
        dopamine = float(neuro.get("dopamine", 0.5))
        oxytocin = float(neuro.get("oxytocin", 0.5))
        resonance = float(neuro.get("decoq_resonance", 0.2))
        immunity = float(neuro.get("immunity_level", 0.0))
        if dopamine > 0.6:
            term_pool.extend(self.SOPHIA_DOPAMINE_TERMS)
        if oxytocin > 0.62:
            term_pool.extend(self.SOPHIA_OXYTOCIN_TERMS)
        if resonance > 0.5:
            term_pool.extend(self.SOPHIA_RESONANCE_TERMS)
        if immunity > 0.1:
            term_pool.extend(self.SOPHIA_IMMUNITY_TERMS)
        goal_kind = str(chosen_goal.get("kind", "")).strip().lower()
        if goal_kind:
            term_pool.append(goal_kind)
        if focus_good:
            term_pool.append(str(focus_good).lower())

        draws = 2 if self.rng.random() < 0.42 else 1
        for _ in range(draws):
            candidate = self.rng.choice(term_pool)
            if candidate not in vocabulary:
                vocabulary.append(candidate)
        while len(vocabulary) > 24:
            vocabulary.pop(0)

    def _npc_utterance(
        self,
        npc: Dict[str, Any],
        good_name: str,
        city_name: str,
        reason: str,
        *,
        neuro: Dict[str, Any],
        chosen_goal: Dict[str, Any],
    ) -> str:
        vocab = npc.get("vocabulary", [])
        if not isinstance(vocab, list) or not vocab:
            return f"Der Markt in {city_name} bleibt unruhig."
        w1 = str(self.rng.choice(vocab))
        w2 = str(self.rng.choice(vocab))
        prefix = "Sophia-Protokoll"
        tone = self._npc_tone_phrase(neuro)
        goal_kind = str(chosen_goal.get("kind", "profit"))
        return f"{prefix}: {w1} und {w2} steuern {good_name} in {city_name} ({reason}, Ziel={goal_kind}, {tone})."

    def _npc_tone_phrase(self, neuro: Dict[str, Any]) -> str:
        dopamine = float(neuro.get("dopamine", 0.5))
        oxytocin = float(neuro.get("oxytocin", 0.5))
        resonance = float(neuro.get("decoq_resonance", 0.2))
        immunity = float(neuro.get("immunity_level", 0.0))
        if immunity > 0.2:
            return "Immunlage angespannt"
        if dopamine - oxytocin > 0.14:
            return "Giervektor dominant"
        if oxytocin - dopamine > 0.14:
            return "Vertrauensnetz dominant"
        if resonance > 0.55:
            return "DeCoG-Signal hoch"
        return "Marktgleichgewicht instabil"

    def _append_npc_memory(
        self,
        npc: Dict[str, Any],
        state: Dict[str, Any],
        success: float,
        good_name: str,
        *,
        chosen_goal: Dict[str, Any],
    ) -> None:
        memory = npc.get("memory")
        if not isinstance(memory, list):
            memory = []
            npc["memory"] = memory
        event_id = int(self._get_required_dict(state, "meta").get("last_event_id", 0))
        goal_kind = str(chosen_goal.get("kind", "profit"))
        memory.append(
            {
                "event_id": event_id,
                "valence": round((success - 0.5) * 2.0, 4),
                "note": f"Marktimpuls {good_name} ({goal_kind})",
                "at": utc_now(),
            }
        )
        while len(memory) > 20:
            memory.pop(0)

    # ---------- DeCoG guard ----------
    def _run_decog_resonance_guard(self, state: Dict[str, Any], *, actor_id: str | None) -> None:
        integrity = self._get_required_dict(state, "integrity")
        neuro = self._get_required_dict(state, "neuro_state")
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        players = self._get_required_dict(state, "players")

        flags = integrity.get("manipulation_flags")
        if not isinstance(flags, dict):
            flags = {}
            integrity["manipulation_flags"] = flags
        for key in ("rapid_price_spike", "negative_inventory", "event_spam", "impossible_cash_flow", "wash_trade_pattern"):
            flags.setdefault(key, False)
            flags[key] = False

        previous_anomaly = float(neuro.get("anomaly_score", 0.0))
        carryover_score = previous_anomaly * 0.22
        fresh_anomaly_score = 0.0
        reasons: list[str] = []
        market_shock = float(economy.get("market_shock", 0.0))

        for good_name, raw_good in goods.items():
            if not isinstance(raw_good, dict):
                continue
            base = float(raw_good.get("base_price", 1.0))
            price = float(raw_good.get("price", base))
            supply = float(raw_good.get("supply", 0.0))
            demand = float(raw_good.get("demand", 0.0))
            momentum = float(raw_good.get("momentum", 0.0))
            if price > base * 4.2:
                fresh_anomaly_score += 1.16
                flags["rapid_price_spike"] = True
                reasons.append(f"Preisspitze {good_name}")
            elif price < base * 0.2 and momentum < -0.42 and market_shock > -0.55:
                # Tiefe Preise sind in Crash-Phasen moeglich; nur abrupte Abstuerze zaehlen.
                fresh_anomaly_score += 0.84
                flags["rapid_price_spike"] = True
                reasons.append(f"Preissturz {good_name}")
            if supply < 0 or demand < 0:
                fresh_anomaly_score += 1.12
                flags["negative_inventory"] = True
                reasons.append(f"Negativbestand {good_name}")

        for player_id, raw_player in players.items():
            if not isinstance(raw_player, dict):
                continue
            cash = float(raw_player.get("cash", 0.0))
            debt = float(raw_player.get("debt", 0.0))
            inventory = raw_player.get("inventory", {})
            if cash > 2500000 or debt > 4500000:
                fresh_anomaly_score += 1.08
                flags["impossible_cash_flow"] = True
                reasons.append(f"Unplausible Bilanz {player_id}")
            if isinstance(inventory, dict):
                if any(float(v) < 0 for v in inventory.values()):
                    fresh_anomaly_score += 1.05
                    flags["negative_inventory"] = True
                    reasons.append(f"Negatives Lager {player_id}")

        events = state.get("events", [])
        if isinstance(events, list) and events:
            sample = events[-24:]
            actor_histogram: Dict[str, int] = {}
            relevant_kinds = {"trade", "guild_action", "player_create", "guild_join", "guild_leave"}
            for event in sample:
                if not isinstance(event, dict):
                    continue
                kind = str(event.get("kind", "")).lower()
                actor = str(event.get("actor_id", ""))
                if actor == "system" or kind not in relevant_kinds:
                    continue
                actor_histogram[actor] = actor_histogram.get(actor, 0) + 1
            for actor, count in actor_histogram.items():
                if actor and count >= 8:
                    fresh_anomaly_score += 0.52
                    flags["event_spam"] = True
                    reasons.append(f"Event-Spam {actor}")
                    break

            wash_trade_score, wash_trade_reason = self._detect_wash_trade_pattern(events)
            if wash_trade_score > 0:
                fresh_anomaly_score += wash_trade_score
                flags["wash_trade_pattern"] = True
                reasons.append(wash_trade_reason)

        anomaly_score = clamp(carryover_score + fresh_anomaly_score, 0.0, 5.0)
        neuro["anomaly_score"] = round(anomaly_score, 4)
        integrity["last_guard_scan_at"] = utc_now()

        severe = fresh_anomaly_score >= self.IMMUNITY_SEVERE_THRESHOLD
        sustained = (
            fresh_anomaly_score >= self.IMMUNITY_SUSTAINED_THRESHOLD
            and anomaly_score >= 2.4
        )
        cooldown_active = self._is_immunity_cooldown_active(neuro)
        allow_during_cooldown = fresh_anomaly_score >= 2.8
        should_trigger = (severe or sustained) and (not cooldown_active or allow_during_cooldown)

        if should_trigger:
            self._trigger_immunity_response(state, anomaly_score=anomaly_score, actor_id=actor_id, reasons=reasons)
        else:
            neuro["immunity_level"] = round(
                clamp(float(neuro.get("immunity_level", 0.0)) * 0.9, 0.0, 1.0),
                4,
            )

        reason_text = ", ".join(reasons) if reasons else "keine"
        self._append_anomaly_record(state, anomaly_score, reason_text, actor_id)

    def _is_immunity_cooldown_active(self, neuro: Dict[str, Any]) -> bool:
        last_trigger = _parse_iso_datetime(neuro.get("last_immunity_trigger"))
        if last_trigger is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last_trigger).total_seconds()
        return elapsed < self.IMMUNITY_COOLDOWN_SECONDS

    def _trigger_immunity_response(
        self,
        state: Dict[str, Any],
        *,
        anomaly_score: float,
        actor_id: str | None,
        reasons: list[str],
    ) -> None:
        neuro = self._get_required_dict(state, "neuro_state")
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        politics = self._get_required_dict(state, "politics")
        council = self._get_required_dict(politics, "hansa_council")
        sanctions = politics.get("sanctions")
        if not isinstance(sanctions, list):
            sanctions = []
            politics["sanctions"] = sanctions
        integrity = self._get_required_dict(state, "integrity")
        immunity_events = integrity.get("immunity_events")
        if not isinstance(immunity_events, list):
            immunity_events = []
            integrity["immunity_events"] = immunity_events

        neuro["immunity_level"] = round(clamp(float(neuro.get("immunity_level", 0.0)) + 0.22, 0.0, 1.0), 4)
        neuro["dopamine"] = round(clamp(float(neuro.get("dopamine", 0.5)) - 0.08, 0.0, 1.0), 4)
        neuro["oxytocin"] = round(clamp(float(neuro.get("oxytocin", 0.5)) + 0.06, 0.0, 1.0), 4)
        neuro["decoq_resonance"] = round(clamp(float(neuro.get("decoq_resonance", 0.2)) + 0.04, 0.0, 1.0), 4)
        neuro["last_immunity_trigger"] = utc_now()

        for raw_good in goods.values():
            if not isinstance(raw_good, dict):
                continue
            raw_good["price"] = round(max(1.0, float(raw_good.get("price", 1.0)) * 0.86), 4)
            raw_good["demand"] = round(max(0.0, float(raw_good.get("demand", 0.0)) * 0.95), 4)
            raw_good["supply"] = round(max(0.0, float(raw_good.get("supply", 0.0)) * 1.04), 4)
            raw_good["momentum"] = round(clamp(float(raw_good.get("momentum", 0.0)) - 0.09, -1.0, 1.0), 4)

        economy["market_shock"] = round(clamp(float(economy.get("market_shock", 0.0)) - 0.2, -1.0, 1.0), 4)
        politics["legitimacy"] = round(clamp(float(politics.get("legitimacy", 0.7)) - 0.02, 0.0, 1.0), 4)
        politics["corruption"] = round(clamp(float(politics.get("corruption", 0.2)) + 0.025, 0.0, 1.0), 4)
        council["public_order"] = round(clamp(float(council.get("public_order", 0.7)) - 0.03, 0.0, 1.0), 4)
        council["stability"] = round(clamp(float(council.get("stability", 0.7)) - 0.025, 0.0, 1.0), 4)

        sanction_id = f"sanction_{int(datetime.now(timezone.utc).timestamp())}"
        sanctions.append(
            {
                "id": sanction_id,
                "target_type": "player" if actor_id else "market",
                "target_id": actor_id or "global_market",
                "reason": "DeCoG-Resonanz: " + "; ".join(reasons[:3] or ["strukturelle Manipulation"]),
                "severity": round(clamp(anomaly_score / 2.5, 0.0, 1.0), 4),
                "issued_at": utc_now(),
                "expires_at": None,
            }
        )
        while len(sanctions) > 60:
            sanctions.pop(0)

        immunity_events.append(
            {
                "at": utc_now(),
                "trigger_score": round(anomaly_score, 4),
                "response": "market_crash_and_ostracism",
                "target_id": actor_id,
            }
        )
        while len(immunity_events) > 80:
            immunity_events.pop(0)

        self._append_event(
            state,
            kind="immunity_response",
            actor_id="system",
            payload={
                "anomaly_score": round(anomaly_score, 4),
                "target_id": actor_id,
                "reasons": reasons,
                "response": "Markteinbruch und politische Aechtung",
            },
        )

    def _append_anomaly_record(
        self,
        state: Dict[str, Any],
        score: float,
        reason: str,
        actor_id: str | None,
    ) -> None:
        integrity = self._get_required_dict(state, "integrity")
        history = integrity.get("anomaly_history")
        if not isinstance(history, list):
            history = []
            integrity["anomaly_history"] = history
        history.append(
            {
                "at": utc_now(),
                "score": round(score, 4),
                "reason": reason,
                "actor_id": actor_id,
            }
        )
        while len(history) > 160:
            history.pop(0)

    # ---------- Macro helpers ----------
    def _refresh_macro_indexes(self, state: Dict[str, Any]) -> None:
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        cities = self._get_required_dict(economy, "cities")
        neuro = self._get_required_dict(state, "neuro_state")

        demand_values = []
        supply_values = []
        momentum_values = []
        for raw_good in goods.values():
            if isinstance(raw_good, dict):
                demand_values.append(float(raw_good.get("demand", 1.0)))
                supply_values.append(float(raw_good.get("supply", 1.0)))
                momentum_values.append(float(raw_good.get("momentum", 0.0)))

        if demand_values and supply_values:
            demand_avg = sum(demand_values) / len(demand_values)
            supply_avg = sum(supply_values) / len(supply_values)
            economy["global_demand_index"] = round(clamp(demand_avg / 1000.0, 0.2, 3.0), 4)
            economy["global_supply_index"] = round(clamp(supply_avg / 1000.0, 0.2, 3.0), 4)

        if momentum_values:
            mean_momentum = sum(momentum_values) / len(momentum_values)
            economy["market_shock"] = round(clamp(float(economy.get("market_shock", 0.0)) * 0.8 + mean_momentum * 0.45, -1.0, 1.0), 4)

        if cities:
            wealth_avg = sum(float(city.get("wealth", 1.0)) for city in cities.values() if isinstance(city, dict)) / len(cities)
            inflation = 0.01 + (wealth_avg - 1.0) * 0.03 + (float(neuro.get("dopamine", 0.5)) - 0.5) * 0.02
            economy["inflation"] = round(clamp(inflation, -0.2, 0.4), 4)

            for raw_city in cities.values():
                if not isinstance(raw_city, dict):
                    continue
                pressure = float(raw_city.get("route_pressure", 0.3))
                stability = float(raw_city.get("stability", 0.6))
                guild_influence = float(raw_city.get("guild_influence", 0.6))
                wealth = float(raw_city.get("wealth", 1.0))
                wealth += (float(neuro.get("oxytocin", 0.5)) - 0.5) * 0.02
                wealth -= max(0.0, pressure - 0.45) * 0.01
                wealth += (guild_influence - 0.5) * 0.012
                wealth *= 1.0 + float(economy.get("inflation", 0.01)) * 0.1
                raw_city["wealth"] = round(clamp(wealth, 0.4, 2.5), 4)

                stability += (float(neuro.get("oxytocin", 0.5)) - 0.5) * 0.03
                stability -= (float(neuro.get("dopamine", 0.5)) - 0.5) * 0.02
                raw_city["stability"] = round(clamp(stability, 0.1, 1.0), 4)
                raw_city["route_pressure"] = round(clamp(pressure * 0.93, 0.0, 1.0), 4)

    def _detect_wash_trade_pattern(self, events: list[Any]) -> tuple[float, str]:
        trade_events = [
            event
            for event in events[-30:]
            if isinstance(event, dict) and str(event.get("kind", "")).lower() == "trade"
        ]
        if len(trade_events) < 4:
            return 0.0, ""

        by_actor: Dict[str, list[Dict[str, Any]]] = {}
        for event in trade_events:
            actor = str(event.get("actor_id", "")).strip()
            if not actor:
                continue
            by_actor.setdefault(actor, []).append(event)

        highest_score = 0.0
        highest_reason = ""
        for actor, actor_events in by_actor.items():
            parsed_events: list[tuple[datetime, Dict[str, Any]]] = []
            for event in actor_events:
                at = _parse_iso_datetime(event.get("at"))
                if at is None:
                    continue
                parsed_events.append((at, event))
            if len(parsed_events) < 4:
                continue
            parsed_events.sort(key=lambda pair: pair[0])

            alternations = 0
            extreme_volume = 0
            for idx in range(1, len(parsed_events)):
                prev_at, prev_event = parsed_events[idx - 1]
                curr_at, curr_event = parsed_events[idx]
                prev_payload = prev_event.get("payload", {})
                curr_payload = curr_event.get("payload", {})
                if not isinstance(prev_payload, dict) or not isinstance(curr_payload, dict):
                    continue
                prev_side = str(prev_payload.get("side", ""))
                curr_side = str(curr_payload.get("side", ""))
                prev_good = str(prev_payload.get("good", ""))
                curr_good = str(curr_payload.get("good", ""))
                prev_city = str(prev_payload.get("city", ""))
                curr_city = str(curr_payload.get("city", ""))
                delta_seconds = (curr_at - prev_at).total_seconds()
                if (
                    delta_seconds <= 180
                    and prev_side
                    and curr_side
                    and prev_side != curr_side
                    and prev_good
                    and prev_good == curr_good
                    and prev_city
                    and prev_city == curr_city
                ):
                    alternations += 1

                quantity = max(float(curr_payload.get("quantity", 0.0)), float(prev_payload.get("quantity", 0.0)))
                notional = max(float(curr_payload.get("notional", 0.0)), float(prev_payload.get("notional", 0.0)))
                if quantity >= 140 or notional >= 12_000:
                    extreme_volume += 1

            score = 0.0
            reason = ""
            if alternations >= 2 and extreme_volume >= 2:
                score = 0.88
                reason = f"Wash-Trade Muster {actor}"
            elif alternations >= 3:
                score = 0.71
                reason = f"Schnelle Buy/Sell-Oszillation {actor}"
            elif extreme_volume >= 3 and len(parsed_events) >= 5:
                score = 0.44
                reason = f"Auffaelliges Extremvolumen {actor}"

            if score > highest_score:
                highest_score = score
                highest_reason = reason

        return highest_score, highest_reason

    # ---------- Utilities ----------
    def _adjust_neuro_after_trade(self, state: Dict[str, Any], *, quantity: int, side: str) -> None:
        neuro = self._get_required_dict(state, "neuro_state")
        unit = clamp(quantity / 140.0, 0.01, 0.3)
        dopamine = float(neuro.get("dopamine", 0.5))
        oxytocin = float(neuro.get("oxytocin", 0.5))
        resonance = float(neuro.get("decoq_resonance", 0.2))

        if side == "buy":
            dopamine += 0.08 * unit
            oxytocin -= 0.02 * unit
        else:
            dopamine -= 0.03 * unit
            oxytocin += 0.05 * unit

        resonance += abs(dopamine - oxytocin) * 0.02 * unit
        neuro["dopamine"] = round(clamp(dopamine, 0.0, 1.0), 4)
        neuro["oxytocin"] = round(clamp(oxytocin, 0.0, 1.0), 4)
        neuro["decoq_resonance"] = round(clamp(resonance, 0.0, 1.0), 4)

    def _shift_good_supply_demand(self, good: Dict[str, Any], *, demand_delta: float, supply_delta: float) -> None:
        demand = max(0.0, float(good.get("demand", 0.0)) + demand_delta)
        supply = max(0.0, float(good.get("supply", 0.0)) + supply_delta)
        good["demand"] = round(demand, 4)
        good["supply"] = round(supply, 4)

    def _route_traffic_bump(self, state: Dict[str, Any], route_id: str, quantity: int) -> None:
        routes = self._get_required_dict(state, "economy").get("trade_routes", [])
        if not isinstance(routes, list):
            return
        for route in routes:
            if not isinstance(route, dict):
                continue
            if str(route.get("id")) == route_id:
                route["traffic"] = round(float(route.get("traffic", 0.0)) + quantity, 4)
                break

    def _ensure_player(
        self,
        state: Dict[str, Any],
        player_id: str,
        display_name: str,
        city_name: str,
        guild_id: str,
    ) -> Dict[str, Any]:
        players = self._get_required_dict(state, "players")
        if player_id in players and isinstance(players[player_id], dict):
            return players[player_id]
        return self._create_player_record(
            state,
            player_id=player_id,
            display_name=display_name,
            city_name=city_name,
            guild_id=guild_id,
            starting_cash=6000.0,
            starting_debt=1800.0,
        )

    def _require_player(self, state: Dict[str, Any], player_id: str) -> Dict[str, Any]:
        players = self._get_required_dict(state, "players")
        raw_player = players.get(player_id)
        if not isinstance(raw_player, dict):
            raise ValueError(
                f"Spieler '{player_id}' existiert nicht. Bitte zuerst Spieler erstellen."
            )
        return raw_player

    def _create_player_record(
        self,
        state: Dict[str, Any],
        *,
        player_id: str,
        display_name: str,
        city_name: str,
        guild_id: str,
        starting_cash: float,
        starting_debt: float,
    ) -> Dict[str, Any]:
        players = self._get_required_dict(state, "players")
        economy = self._get_required_dict(state, "economy")
        goods = self._get_required_dict(economy, "goods")
        cities = self._get_required_dict(economy, "cities")
        if city_name not in cities:
            raise ValueError(f"Unbekannte Stadt: {city_name}")

        self._ensure_guild_exists(state, guild_id, auto_create=(guild_id == "free_merchants"))
        inventory = {good_name: 0.0 for good_name in goods.keys()}
        player = {
            "id": player_id,
            "display_name": display_name,
            "home_city": city_name,
            "guild_id": guild_id,
            "cash": round(max(0.0, float(starting_cash)), 2),
            "debt": round(max(0.0, float(starting_debt)), 2),
            "reputation": 0.45,
            "inventory": inventory,
            "ships": [
                {
                    "name": "Kogge",
                    "cargo_capacity": 120,
                    "hull": 100,
                    "rigging": 100,
                }
            ],
            "last_action_at": utc_now(),
        }
        players[player_id] = player
        self._transfer_guild_membership(state, player, from_guild=None, to_guild=guild_id)
        return player

    def _ensure_guild_exists(self, state: Dict[str, Any], guild_id: str, *, auto_create: bool) -> Dict[str, Any]:
        guilds = self._get_required_dict(state, "guilds")
        raw_guild = guilds.get(guild_id)
        if isinstance(raw_guild, dict):
            return raw_guild
        if not auto_create:
            raise ValueError(f"Unbekannte Gilde: {guild_id}")
        guilds[guild_id] = {
            "name": guild_id.replace("_", " ").title(),
            "cohesion": 0.42,
            "trust": 0.45,
            "treasury": 6000.0,
            "rank_points": 240,
            "member_count": 0,
            "doctrine": "Freier Handel ohne festen Gildenpakt.",
        }
        return guilds[guild_id]

    def _transfer_guild_membership(
        self,
        state: Dict[str, Any],
        player: Dict[str, Any],
        *,
        from_guild: str | None,
        to_guild: str,
    ) -> None:
        guilds = self._get_required_dict(state, "guilds")
        if from_guild:
            from_ref = guilds.get(from_guild)
            if isinstance(from_ref, dict):
                old_count = int(from_ref.get("member_count", 0))
                from_ref["member_count"] = max(0, old_count - 1)
                from_ref["cohesion"] = round(clamp(float(from_ref.get("cohesion", 0.5)) - 0.004, 0.0, 1.0), 4)

        to_ref = self._ensure_guild_exists(state, to_guild, auto_create=True)
        to_count = int(to_ref.get("member_count", 0))
        to_ref["member_count"] = max(0, to_count + 1)
        to_ref["cohesion"] = round(clamp(float(to_ref.get("cohesion", 0.5)) + 0.006, 0.0, 1.0), 4)
        to_ref["trust"] = round(clamp(float(to_ref.get("trust", 0.5)) + 0.004, 0.0, 1.0), 4)
        player["guild_id"] = to_guild

    def _append_event(self, state: Dict[str, Any], *, kind: str, actor_id: str, payload: Dict[str, Any]) -> None:
        meta = self._get_required_dict(state, "meta")
        events = state.get("events")
        if not isinstance(events, list):
            events = []
            state["events"] = events
        event_id = int(meta.get("last_event_id", 0)) + 1
        meta["last_event_id"] = event_id
        events.append(
            {
                "id": event_id,
                "kind": kind,
                "actor_id": actor_id,
                "at": utc_now(),
                "payload": payload,
            }
        )
        while len(events) > 600:
            events.pop(0)

    def _touch_meta(self, state: Dict[str, Any]) -> None:
        meta = self._get_required_dict(state, "meta")
        meta["updated_at"] = utc_now()

    def _required_text(self, payload: Dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} ist erforderlich.")
        return value.strip()

    def _get_required_dict(self, payload: Dict[str, Any], key: str) -> Dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"world_state ist unvollstaendig. Feld '{key}' fehlt.")
        return value
