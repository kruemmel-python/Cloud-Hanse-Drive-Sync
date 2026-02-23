from __future__ import annotations

import argparse
import json
import random
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.parse import urlparse

try:
    from .drive_sync import (
        DEFAULT_FOLDER_URL,
        DriveConflictError,
        DriveSyncError,
        DriveWriteUnavailable,
        GoogleDriveWorldStateStore,
        calculate_state_hash,
    )
    from .simulation import WorldSimulator
except ImportError:
    if __package__:
        raise
    from drive_sync import (  # type: ignore[no-redef]
        DEFAULT_FOLDER_URL,
        DriveConflictError,
        DriveSyncError,
        DriveWriteUnavailable,
        GoogleDriveWorldStateStore,
        calculate_state_hash,
    )
    from simulation import WorldSimulator  # type: ignore[no-redef]


def _deepcopy(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


AI_BOT_PROFILES = [
    {
        "id": "ai_elsa_broker",
        "display_name": "Elsa van Brugge",
        "home_city": "Luebeck",
        "guild_id": "merchant_guild",
    },
    {
        "id": "ai_torsten_captain",
        "display_name": "Torsten Ravn",
        "home_city": "Bergen",
        "guild_id": "navigators_guild",
    },
    {
        "id": "ai_agneta_qm",
        "display_name": "Agneta Soder",
        "home_city": "Malmoe",
        "guild_id": "artisans_guild",
    },
    {
        "id": "ai_ivo_scribe",
        "display_name": "Ivo der Schreiber",
        "home_city": "Riga",
        "guild_id": "merchant_guild",
    },
    {
        "id": "ai_yaromir_fur",
        "display_name": "Yaromir Volkov",
        "home_city": "Novgorod",
        "guild_id": "navigators_guild",
    },
]


class WorldService:
    def __init__(
        self,
        *,
        store: GoogleDriveWorldStateStore,
        simulator: WorldSimulator,
        default_state_path: Path,
        pull_interval_seconds: float = 8.0,
        max_write_retries: int = 4,
        ai_enabled: bool = True,
        ai_interval_seconds: float = 12.0,
        ai_seed: int | None = None,
    ) -> None:
        self.store = store
        self.simulator = simulator
        self.default_state_path = default_state_path
        self.pull_interval_seconds = max(1.0, float(pull_interval_seconds))
        self.max_write_retries = max(1, int(max_write_retries))
        self.ai_enabled = bool(ai_enabled)
        self.ai_interval_seconds = max(2.0, float(ai_interval_seconds))
        self._ai_rng = random.Random(ai_seed)

        self._lock = threading.RLock()
        self._last_pull_ts = 0.0
        self._last_sync_error: str | None = None
        self._ai_stop_event = threading.Event()
        self._ai_thread: threading.Thread | None = None
        self._ai_cycle_count = 0
        self._ai_trade_events_total = 0
        self._ai_last_cycle_at: str | None = None
        self._ai_last_cycle_trade_count = 0
        self._ai_last_cycle_price_delta: Dict[str, float] = {}
        self._ai_last_cycle_error: str | None = None

        self._state = self._load_default_state()
        self._bootstrap_state()
        self._start_ai_worker()

    def get_world(self, *, force_pull: bool = False) -> Dict[str, Any]:
        with self._lock:
            state = self._pull_latest(force=force_pull)
            return self._augment_for_client(state)

    def apply_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def mutator(base_state: Dict[str, Any], action_payload: Dict[str, Any]) -> Dict[str, Any]:
            return self.simulator.apply_trade_action(base_state, action_payload)

        return self._apply_with_retry(mutator, payload)

    def apply_guild(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def mutator(base_state: Dict[str, Any], action_payload: Dict[str, Any]) -> Dict[str, Any]:
            return self.simulator.apply_guild_action(base_state, action_payload)

        return self._apply_with_retry(mutator, payload)

    def apply_player(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def mutator(base_state: Dict[str, Any], action_payload: Dict[str, Any]) -> Dict[str, Any]:
            return self.simulator.apply_player_action(base_state, action_payload)

        return self._apply_with_retry(mutator, payload)

    def tick_world(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor = str(payload.get("actor_id") or "system")
        reason = str(payload.get("reason") or "manual_tick")

        def mutator(base_state: Dict[str, Any], _: Dict[str, Any]) -> Dict[str, Any]:
            candidate = _deepcopy(base_state)
            self.simulator.step_world(candidate, actor_id=actor, reason=reason)
            return candidate

        return self._apply_with_retry(mutator, payload)

    def run_ai_cycle(self) -> Dict[str, Any] | None:
        if not self.ai_enabled:
            return None

        cycle_stats: Dict[str, Any] = {}

        def mutator(base_state: Dict[str, Any], _: Dict[str, Any]) -> Dict[str, Any]:
            world = _deepcopy(base_state)
            before_prices = self._snapshot_global_prices(world)
            before_event_count = len(world.get("events", [])) if isinstance(world.get("events"), list) else 0
            world = self._ensure_ai_players(world)
            world = self._execute_ai_trading(world)
            after_prices = self._snapshot_global_prices(world)
            all_events = world.get("events", [])
            new_events = all_events[before_event_count:] if isinstance(all_events, list) else []
            trade_count = 0
            for event in new_events:
                if not isinstance(event, dict):
                    continue
                if str(event.get("kind", "")).lower() != "trade":
                    continue
                actor = str(event.get("actor_id", ""))
                if actor.startswith("ai_"):
                    trade_count += 1
            cycle_stats["trade_count"] = trade_count
            cycle_stats["price_delta"] = {
                good: round(float(after_prices.get(good, 0.0)) - float(before_prices.get(good, 0.0)), 4)
                for good in sorted(after_prices.keys())
            }
            return world

        try:
            result = self._apply_with_retry(mutator, {})
        except Exception as exc:
            self._ai_last_cycle_error = str(exc)
            raise

        self._ai_cycle_count += 1
        self._ai_last_cycle_at = _utc_now()
        self._ai_last_cycle_trade_count = int(cycle_stats.get("trade_count", 0))
        self._ai_trade_events_total += self._ai_last_cycle_trade_count
        self._ai_last_cycle_price_delta = cycle_stats.get("price_delta", {})
        self._ai_last_cycle_error = None
        return result

    def validate_decog(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        actor = str(payload.get("actor_id") or "validator")
        with self._lock:
            base = self._pull_latest(force=True)
            report = self.simulator.validate_decog_immunity(base, actor_id=actor)
            return {
                "validation": report,
                "world_meta": {
                    "version": int(base.get("meta", {}).get("version", 0)),
                    "updated_at": base.get("meta", {}).get("updated_at"),
                },
                "sync": {
                    "last_error": self._last_sync_error,
                    "pull_interval_seconds": self.pull_interval_seconds,
                },
            }

    def get_diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            base = self._pull_latest(force=False)
            events = base.get("events", [])
            events_tail = events[-40:] if isinstance(events, list) else []
            trade_tail = [
                event
                for event in events_tail
                if isinstance(event, dict) and str(event.get("kind", "")).lower() == "trade"
            ]
            ai_trade_tail = [
                event
                for event in trade_tail
                if str(event.get("actor_id", "")).startswith("ai_")
            ]
            human_trade_tail = [
                event
                for event in trade_tail
                if not str(event.get("actor_id", "")).startswith("ai_")
            ]

            market_phase = self._compute_market_phase(base)
            meta = base.get("meta", {})
            sync_meta = meta.get("drive", {}) if isinstance(meta, dict) else {}
            return {
                "timestamp": _utc_now(),
                "world": {
                    "version": int(meta.get("version", 0)) if isinstance(meta, dict) else 0,
                    "updated_at": meta.get("updated_at") if isinstance(meta, dict) else None,
                    "market_phase": market_phase,
                },
                "sync": {
                    "last_error": self._last_sync_error,
                    "pull_interval_seconds": self.pull_interval_seconds,
                    "sync_source": sync_meta.get("sync_source") if isinstance(sync_meta, dict) else None,
                },
                "ai": {
                    "enabled": self.ai_enabled,
                    "interval_seconds": self.ai_interval_seconds,
                    "bots": [profile["id"] for profile in AI_BOT_PROFILES],
                    "cycle_count": self._ai_cycle_count,
                    "last_cycle_at": self._ai_last_cycle_at,
                    "last_cycle_trade_count": self._ai_last_cycle_trade_count,
                    "trade_events_total": self._ai_trade_events_total,
                    "last_cycle_price_delta": self._ai_last_cycle_price_delta,
                    "last_cycle_error": self._ai_last_cycle_error,
                },
                "events": {
                    "tail_size": len(events_tail),
                    "tail_trade_count": len(trade_tail),
                    "tail_ai_trade_count": len(ai_trade_tail),
                    "tail_human_trade_count": len(human_trade_tail),
                    "last_event_ids": [event.get("id") for event in events_tail[-8:] if isinstance(event, dict)],
                },
            }

    def _apply_with_retry(
        self,
        mutator: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._lock:
            last_error: Exception | None = None
            for _attempt in range(1, self.max_write_retries + 1):
                base = self._pull_latest(force=True)
                base_version = int(base.get("meta", {}).get("version", 1))
                expected_version = base_version
                drive_meta = base.get("meta", {}).get("drive", {})
                sync_source = drive_meta.get("sync_source") if isinstance(drive_meta, dict) else None

                # Falls die Welt nur aus dem lokalen Cache kommt, kann die Remote-Datei
                # noch fehlen (remote version=0). Dann darf der erste Push nicht an
                # expected=1 scheitern.
                if sync_source == "local_cache" and expected_version > 0:
                    expected_version = 0

                candidate = mutator(base, payload)
                candidate.setdefault("integrity", {})
                if isinstance(candidate["integrity"], dict):
                    candidate["integrity"]["state_hash"] = calculate_state_hash(candidate)

                try:
                    persisted = self.store.write_world_state(candidate, expected_version=expected_version)
                    self._state = persisted
                    self._last_pull_ts = time.time()
                    self._last_sync_error = None
                    return self._augment_for_client(persisted)
                except DriveConflictError as exc:
                    last_error = exc
                    continue
                except DriveWriteUnavailable:
                    persisted = self.store.write_world_state_local_fallback(candidate)
                    self._state = persisted
                    self._last_pull_ts = time.time()
                    self._last_sync_error = "Drive write unavailable, local cache active."
                    return self._augment_for_client(persisted)
                except DriveSyncError as exc:
                    # Wenn nur der Push fehlschlaegt, bleibt die Welt lokal konsistent.
                    self._state = candidate
                    self._last_sync_error = str(exc)
                    persisted = self.store.write_world_state_local_fallback(candidate)
                    return self._augment_for_client(persisted)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    break

            raise RuntimeError(f"Konnte Aktion nicht persistieren: {last_error}")

    def _augment_for_client(self, state: Dict[str, Any]) -> Dict[str, Any]:
        payload = _deepcopy(state)
        payload["market_view"] = self.simulator.build_market_view(payload)
        payload["system"] = {
            "market_phase": self._compute_market_phase(payload),
            "ai_cycle_count": self._ai_cycle_count,
            "ai_last_cycle_at": self._ai_last_cycle_at,
            "ai_last_cycle_trade_count": self._ai_last_cycle_trade_count,
            "ai_last_cycle_error": self._ai_last_cycle_error,
            "ai_last_cycle_price_delta": self._ai_last_cycle_price_delta,
        }
        payload["sync"] = {
            "last_error": self._last_sync_error,
            "pull_interval_seconds": self.pull_interval_seconds,
            "ai_enabled": self.ai_enabled,
            "ai_interval_seconds": self.ai_interval_seconds,
            "ai_bots": [profile["id"] for profile in AI_BOT_PROFILES],
            "ai_cycle_count": self._ai_cycle_count,
            "ai_last_cycle_at": self._ai_last_cycle_at,
            "ai_last_cycle_trade_count": self._ai_last_cycle_trade_count,
            "ai_last_cycle_error": self._ai_last_cycle_error,
        }
        return payload

    def _snapshot_global_prices(self, state: Dict[str, Any]) -> Dict[str, float]:
        economy = state.get("economy", {})
        goods = economy.get("goods", {}) if isinstance(economy, dict) else {}
        if not isinstance(goods, dict):
            return {}
        out: Dict[str, float] = {}
        for good_name, raw in goods.items():
            if not isinstance(raw, dict):
                continue
            out[str(good_name)] = float(raw.get("price", 0.0))
        return out

    def _compute_market_phase(self, state: Dict[str, Any]) -> str:
        neuro = state.get("neuro_state", {})
        economy = state.get("economy", {})
        goods = economy.get("goods", {}) if isinstance(economy, dict) else {}

        anomaly = float(neuro.get("anomaly_score", 0.0)) if isinstance(neuro, dict) else 0.0
        immunity = float(neuro.get("immunity_level", 0.0)) if isinstance(neuro, dict) else 0.0
        shock = abs(float(economy.get("market_shock", 0.0))) if isinstance(economy, dict) else 0.0

        momentum_values: list[float] = []
        if isinstance(goods, dict):
            for raw in goods.values():
                if isinstance(raw, dict):
                    momentum_values.append(abs(float(raw.get("momentum", 0.0))))
        mean_abs_momentum = sum(momentum_values) / len(momentum_values) if momentum_values else 0.0

        if anomaly >= 2.2 or immunity >= 0.72 or shock >= 0.75:
            return "plasma"
        if anomaly >= 0.9 or immunity >= 0.34 or shock >= 0.35 or mean_abs_momentum >= 0.11:
            return "liquid"
        return "solid"

    def _bootstrap_state(self) -> None:
        try:
            state = self.store.read_world_state()
            self._state = state
            self._last_pull_ts = time.time()
            self._last_sync_error = None
            return
        except Exception as exc:  # noqa: BLE001
            self._last_sync_error = str(exc)

        # Wenn Drive leer/unerreichbar ist, initialisiere mit Default und versuche einmalig zu schreiben.
        try:
            self._state.setdefault("integrity", {})
            if isinstance(self._state["integrity"], dict):
                self._state["integrity"]["state_hash"] = calculate_state_hash(self._state)
            self._state = self.store.write_world_state(self._state, expected_version=0)
            self._last_sync_error = None
            self._last_pull_ts = time.time()
        except Exception:  # noqa: BLE001
            self._state = self.store.write_world_state_local_fallback(self._state)
            self._last_pull_ts = time.time()

    def _pull_latest(self, *, force: bool) -> Dict[str, Any]:
        now = time.time()
        if not force and (now - self._last_pull_ts) < self.pull_interval_seconds:
            return _deepcopy(self._state)
        try:
            latest = self.store.read_world_state()
            self._state = latest
            self._last_pull_ts = now
            self._last_sync_error = None
            return _deepcopy(latest)
        except Exception as exc:  # noqa: BLE001
            self._last_sync_error = str(exc)
            return _deepcopy(self._state)

    def _load_default_state(self) -> Dict[str, Any]:
        raw = self.default_state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("default_world_state.json muss ein JSON-Objekt sein.")
        return data

    def _start_ai_worker(self) -> None:
        if not self.ai_enabled:
            return
        if self._ai_thread and self._ai_thread.is_alive():
            return
        self._ai_thread = threading.Thread(target=self._ai_worker_loop, name="cloud_hanse_ai", daemon=True)
        self._ai_thread.start()

    def _ai_worker_loop(self) -> None:
        # Kurze Startverzoegerung, damit der Server hochfaehrt.
        if self._ai_stop_event.wait(2.0):
            return
        while not self._ai_stop_event.is_set():
            try:
                self.run_ai_cycle()
            except Exception as exc:  # noqa: BLE001
                self._last_sync_error = f"AI cycle fehlgeschlagen: {exc}"
                self._ai_last_cycle_error = str(exc)
            jitter = self.ai_interval_seconds * 0.25
            sleep_for = self.ai_interval_seconds + self._ai_rng.uniform(-jitter, jitter)
            sleep_for = max(2.0, sleep_for)
            if self._ai_stop_event.wait(sleep_for):
                return

    def shutdown(self) -> None:
        self._ai_stop_event.set()
        if self._ai_thread and self._ai_thread.is_alive():
            self._ai_thread.join(timeout=2.0)

    def _ensure_ai_players(self, world: Dict[str, Any]) -> Dict[str, Any]:
        players = world.get("players")
        if not isinstance(players, dict):
            players = {}
            world["players"] = players

        for profile in AI_BOT_PROFILES:
            if profile["id"] in players and isinstance(players[profile["id"]], dict):
                continue
            create_payload = {
                "action_type": "create",
                "player_id": profile["id"],
                "display_name": profile["display_name"],
                "home_city": profile["home_city"],
                "guild_id": profile["guild_id"],
                "starting_cash": 8200.0,
                "starting_debt": 900.0,
            }
            try:
                world = self.simulator.apply_player_action(world, create_payload)
            except Exception:
                # Bot-Erzeugung darf den Zyklus nicht abbrechen.
                continue
        return world

    def _execute_ai_trading(self, world: Dict[str, Any]) -> Dict[str, Any]:
        for profile in AI_BOT_PROFILES:
            try:
                world = self._run_single_bot_trade(world, profile)
            except Exception:
                continue
        return world

    def _run_single_bot_trade(self, world: Dict[str, Any], profile: Dict[str, str]) -> Dict[str, Any]:
        players = world.get("players", {})
        if not isinstance(players, dict):
            return world
        player = players.get(profile["id"])
        if not isinstance(player, dict):
            return world

        economy = world.get("economy", {})
        if not isinstance(economy, dict):
            return world
        goods = economy.get("goods", {})
        cities = economy.get("cities", {})
        if not isinstance(goods, dict) or not isinstance(cities, dict) or not goods or not cities:
            return world

        goods_list = [str(name) for name, entry in goods.items() if isinstance(entry, dict)]
        city_list = [str(name) for name, entry in cities.items() if isinstance(entry, dict)]
        if not goods_list or not city_list:
            return world

        player_city = str(player.get("home_city") or profile.get("home_city") or city_list[0])
        if player_city not in city_list:
            player_city = city_list[0]
        inventory = player.get("inventory", {})
        if not isinstance(inventory, dict):
            inventory = {}
            player["inventory"] = inventory
        cash = float(player.get("cash", 0.0))
        guild_id = str(player.get("guild_id") or profile.get("guild_id") or "merchant_guild")

        # 1) Wenn Ware vorhanden ist, versuche in der besten Stadt zu verkaufen.
        best_sell: tuple[float, str, str, int] | None = None
        for good_name in goods_list:
            qty = int(float(inventory.get(good_name, 0.0)))
            if qty <= 0:
                continue
            local_price = self.simulator.city_good_price(world, player_city, good_name)
            target_city = max(city_list, key=lambda city: self.simulator.city_good_price(world, city, good_name))
            target_price = self.simulator.city_good_price(world, target_city, good_name)
            gain = target_price - local_price
            if target_price > local_price * 1.04 and qty > 0:
                score = gain * min(qty, 40)
                if best_sell is None or score > best_sell[0]:
                    best_sell = (score, good_name, target_city, min(qty, 40))

        if best_sell is not None and self._ai_rng.random() < 0.72:
            _, good_name, target_city, qty = best_sell
            payload = {
                "player_id": profile["id"],
                "display_name": profile["display_name"],
                "guild_id": guild_id,
                "city": target_city,
                "good": good_name,
                "side": "sell",
                "quantity": max(1, qty),
                "route_id": self._pick_route_id(world, target_city),
            }
            try:
                return self.simulator.apply_trade_action(world, payload)
            except Exception:
                pass

        # 2) Sonst bestes Arbitrage-Gut guenstig einkaufen.
        best_buy: tuple[float, str, str, float, int] | None = None
        for good_name in goods_list:
            all_priced: list[tuple[str, float]] = []
            stocked: list[tuple[str, float, int]] = []
            for city in city_list:
                city_price = self.simulator.city_good_price(world, city, good_name)
                if city_price <= 0:
                    continue
                all_priced.append((city, city_price))
                city_state = cities.get(city, {})
                if not isinstance(city_state, dict):
                    continue
                city_inventory = city_state.get("inventory", {})
                if not isinstance(city_inventory, dict):
                    continue
                available_qty = int(float(city_inventory.get(good_name, 0.0)))
                if available_qty > 0:
                    stocked.append((city, city_price, available_qty))

            if len(all_priced) < 2 or not stocked:
                continue
            min_city, min_price, min_available = min(stocked, key=lambda item: item[1])
            _max_city, max_price = max(all_priced, key=lambda item: item[1])
            if min_price <= 0:
                continue
            edge_ratio = (max_price - min_price) / min_price
            score = edge_ratio * max_price
            if best_buy is None or score > best_buy[0]:
                best_buy = (score, good_name, min_city, min_price, min_available)

        if best_buy is None:
            return world

        _, good_name, buy_city, unit_price, available_qty = best_buy
        if cash < unit_price:
            return world
        qty_by_cash = int(cash // max(1.0, unit_price))
        qty = max(1, min(40, qty_by_cash // 3 if qty_by_cash > 3 else qty_by_cash))
        qty = min(qty, max(0, int(available_qty)))
        if qty < 1:
            return world
        payload = {
            "player_id": profile["id"],
            "display_name": profile["display_name"],
            "guild_id": guild_id,
            "city": buy_city,
            "good": good_name,
            "side": "buy",
            "quantity": qty,
            "route_id": self._pick_route_id(world, buy_city),
        }
        try:
            return self.simulator.apply_trade_action(world, payload)
        except Exception:
            return world

    def _pick_route_id(self, world: Dict[str, Any], city_name: str) -> str | None:
        economy = world.get("economy", {})
        if not isinstance(economy, dict):
            return None
        routes = economy.get("trade_routes", [])
        if not isinstance(routes, list):
            return None
        candidates = []
        for route in routes:
            if not isinstance(route, dict):
                continue
            from_city = str(route.get("from_city", ""))
            to_city = str(route.get("to_city", ""))
            route_id = route.get("id")
            if not isinstance(route_id, str):
                continue
            if city_name in {from_city, to_city}:
                candidates.append(route_id)
        if not candidates:
            return None
        return self._ai_rng.choice(candidates)


class HanseRequestHandler(SimpleHTTPRequestHandler):
    server_version = "CloudHanseHTTP/1.0"

    def __init__(self, *args: Any, service: WorldService, web_root: Path, **kwargs: Any) -> None:
        self._service = service
        self._web_root = web_root
        super().__init__(*args, directory=str(web_root), **kwargs)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib callback name
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        route = urlparse(self.path).path
        if route == "/api/world":
            try:
                payload = self._service.get_world(force_pull=False)
                self._send_json(HTTPStatus.OK, payload)
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        if route == "/api/diagnostics":
            try:
                payload = self._service.get_diagnostics()
                self._send_json(HTTPStatus.OK, payload)
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        route = urlparse(self.path).path
        body = self._read_json_body()

        try:
            if route == "/api/action/trade":
                payload = self._service.apply_trade(body)
                self._send_json(HTTPStatus.OK, payload)
                return
            if route == "/api/action/guild":
                payload = self._service.apply_guild(body)
                self._send_json(HTTPStatus.OK, payload)
                return
            if route == "/api/action/player":
                payload = self._service.apply_player(body)
                self._send_json(HTTPStatus.OK, payload)
                return
            if route == "/api/tick":
                payload = self._service.tick_world(body)
                self._send_json(HTTPStatus.OK, payload)
                return
            if route == "/api/validate/decog":
                payload = self._service.validate_decog(body)
                self._send_json(HTTPStatus.OK, payload)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {route}"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def end_headers(self) -> None:
        self._send_common_headers()
        super().end_headers()

    def _read_json_body(self) -> Dict[str, Any]:
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ungueltiges JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request-Body muss ein JSON-Objekt sein.")
        return payload

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if urlparse(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cloud Hanse - Drive synchronisierte Wirtschaftssimulation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--folder-url", default=DEFAULT_FOLDER_URL)
    parser.add_argument("--file-name", default="world_state.json")
    parser.add_argument("--local-cache", default="cloud_hanse/world_state.local.json")
    parser.add_argument("--default-world", default="cloud_hanse/default_world_state.json")
    parser.add_argument("--web-root", default="cloud_hanse/web")
    parser.add_argument("--pull-interval", type=float, default=8.0)
    parser.add_argument("--disable-ai", action="store_true", help="Deaktiviert autonome KI-Haendler.")
    parser.add_argument("--ai-interval", type=float, default=12.0, help="Sekunden zwischen KI-Handelszyklen.")
    parser.add_argument("--ai-seed", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = GoogleDriveWorldStateStore(
        folder_url=args.folder_url,
        file_name=args.file_name,
        local_cache_path=Path(args.local_cache),
    )
    simulator = WorldSimulator(seed=args.seed)
    service = WorldService(
        store=store,
        simulator=simulator,
        default_state_path=Path(args.default_world),
        pull_interval_seconds=args.pull_interval,
        ai_enabled=not args.disable_ai,
        ai_interval_seconds=args.ai_interval,
        ai_seed=args.ai_seed,
    )

    web_root = Path(args.web_root).resolve()
    web_root.mkdir(parents=True, exist_ok=True)

    def handler(*handler_args: Any, **handler_kwargs: Any) -> HanseRequestHandler:
        return HanseRequestHandler(*handler_args, service=service, web_root=web_root, **handler_kwargs)

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Cloud Hanse Server laeuft auf http://{args.host}:{args.port}")
    print(f"Web UI: http://{args.host}:{args.port}/")
    print("Stop mit CTRL+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
