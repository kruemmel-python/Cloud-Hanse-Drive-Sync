# CodeDump for Project: `HP_Android.zip`

_Generated on 2026-02-25T06:08:45.001Z_

## File: `HP_Android/HP_Game/atheria_economy.py`  
- Path: `HP_Android/HP_Game/atheria_economy.py`  
- Size: 15177 Bytes  
- Modified: 2026-02-25 06:49:06 UTC

```python
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable


def _default_atheria_root() -> Path:
    env_value = os.getenv("HP_GAME_ATHERIA_ROOT", "").strip()
    if env_value:
        env_path = Path(env_value)
        if env_path.exists():
            return env_path

    here = Path(__file__).resolve()
    candidates = [
        here.parent / "ATHERIA",
        here.parent.parent / "ATHERIA",
        Path(r"D:\ATHERIA"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[1]


DEFAULT_ATHERIA_ROOT = _default_atheria_root()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _hash_unit(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    num = int.from_bytes(digest[:8], "big")
    return (num % 10_000_000) / 10_000_000.0


def _extract_first_json_object(text: str) -> Dict[str, Any] | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : idx + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                if isinstance(parsed, dict):
                    return parsed
                return None
    return None


@dataclass
class EconomyState:
    year: float
    global_growth: float
    global_price_level: float
    resource_scarcity: float
    good_factors: Dict[str, float] = field(default_factory=dict)
    city_factors: Dict[str, float] = field(default_factory=dict)
    source: str = "fallback"
    summary: str = ""
    raw_metrics: Dict[str, Any] = field(default_factory=dict)

    def good_factor(self, good_name: str) -> float:
        return self.good_factors.get(good_name, 1.0)

    def city_factor(self, city_name: str) -> float:
        return self.city_factors.get(city_name, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "global_growth": self.global_growth,
            "global_price_level": self.global_price_level,
            "resource_scarcity": self.resource_scarcity,
            "good_factors": dict(self.good_factors),
            "city_factors": dict(self.city_factors),
            "source": self.source,
            "summary": self.summary,
            "raw_metrics": dict(self.raw_metrics),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EconomyState":
        return cls(
            year=float(data.get("year", 0.0)),
            global_growth=float(data.get("global_growth", 1.0)),
            global_price_level=float(data.get("global_price_level", 1.0)),
            resource_scarcity=float(data.get("resource_scarcity", 0.0)),
            good_factors={str(k): float(v) for k, v in data.get("good_factors", {}).items()},
            city_factors={str(k): float(v) for k, v in data.get("city_factors", {}).items()},
            source=str(data.get("source", "fallback")),
            summary=str(data.get("summary", "")),
            raw_metrics={str(k): v for k, v in data.get("raw_metrics", {}).items()},
        )


class AtheriaEconomyEngine:
    def __init__(
        self,
        atheria_root: Path | None = None,
        refresh_interval_years: int = 5,
        demo_duration_seconds: float = 0.4,
        timeout_seconds: float = 25.0,
    ) -> None:
        self.atheria_root = atheria_root or DEFAULT_ATHERIA_ROOT
        self.refresh_interval_years = max(1, int(refresh_interval_years))
        self.demo_duration_seconds = max(0.1, float(demo_duration_seconds))
        self.timeout_seconds = max(5.0, float(timeout_seconds))
        self.is_android = ("ANDROID_ARGUMENT" in os.environ) or (sys.platform == "android")

        self.last_refresh_year: float | None = None
        self.last_error: str | None = None
        self.metrics: Dict[str, Any] = {}
        self.runtime_python = self._detect_runtime_python()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atheria_root": str(self.atheria_root),
            "refresh_interval_years": self.refresh_interval_years,
            "demo_duration_seconds": self.demo_duration_seconds,
            "timeout_seconds": self.timeout_seconds,
            "last_refresh_year": self.last_refresh_year,
            "last_error": self.last_error,
            "metrics": dict(self.metrics),
            "runtime_python": str(self.runtime_python) if self.runtime_python else None,
        }

    def load_dict(self, data: Dict[str, Any]) -> None:
        self.refresh_interval_years = max(1, int(data.get("refresh_interval_years", self.refresh_interval_years)))
        self.demo_duration_seconds = max(0.1, float(data.get("demo_duration_seconds", self.demo_duration_seconds)))
        self.timeout_seconds = max(5.0, float(data.get("timeout_seconds", self.timeout_seconds)))
        self.last_refresh_year = float(data["last_refresh_year"]) if data.get("last_refresh_year") is not None else None
        self.last_error = str(data["last_error"]) if data.get("last_error") else None
        metrics = data.get("metrics", {})
        if isinstance(metrics, dict):
            self.metrics = dict(metrics)

        root_text = data.get("atheria_root")
        if isinstance(root_text, str) and root_text:
            loaded_root = Path(root_text)
            self.atheria_root = loaded_root if loaded_root.exists() else _default_atheria_root()

        runtime_text = data.get("runtime_python")
        if isinstance(runtime_text, str) and runtime_text:
            runtime_path = Path(runtime_text)
            self.runtime_python = runtime_path if runtime_path.exists() else self._detect_runtime_python()
        else:
            self.runtime_python = self._detect_runtime_python()

    def for_year(
        self,
        year: float,
        sea_state: str,
        goods: Iterable[str],
        cities: Iterable[str],
    ) -> EconomyState:
        should_refresh = self.last_refresh_year is None or (year - self.last_refresh_year) >= self.refresh_interval_years
        refreshed = False
        if should_refresh:
            metrics = self._fetch_live_metrics()
            if metrics:
                self.metrics = metrics
                self.last_refresh_year = year
                self.last_error = None
                refreshed = True

        return self._build_state(
            year=year,
            sea_state=sea_state,
            goods=list(goods),
            cities=list(cities),
            refreshed=refreshed,
        )

    def _detect_runtime_python(self) -> Path | None:
        candidates = [
            self.atheria_root / ".venv" / "Scripts" / "python.exe",
            self.atheria_root / ".venv" / "bin" / "python",
            Path(sys.executable),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _fetch_live_metrics(self) -> Dict[str, Any] | None:
        main_py = self.atheria_root / "main.py"
        python_exe = self.runtime_python
        if python_exe is None or not main_py.exists():
            if self.is_android:
                self.last_error = None
                return self._mobile_metrics()
            self.last_error = "ATHERIA runtime nicht gefunden."
            return None

        args = [
            str(python_exe),
            str(main_py),
            "demo",
            "--duration",
            str(self.demo_duration_seconds),
            "--log-level",
            "ERROR",
        ]
        try:
            result = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            if self.is_android:
                self.last_error = None
                return self._mobile_metrics()
            self.last_error = f"ATHERIA Aufruf fehlgeschlagen: {exc}"
            return None

        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        parsed = _extract_first_json_object(combined)
        if result.returncode != 0 or parsed is None:
            if self.is_android:
                self.last_error = None
                return self._mobile_metrics()
            self.last_error = (
                f"ATHERIA Runtime-Fehler (code={result.returncode})."
                if result.returncode != 0
                else "ATHERIA JSON konnte nicht gelesen werden."
            )
            return None
        return parsed

    def _mobile_metrics(self) -> Dict[str, Any]:
        # Android fallback without subprocess/torch runtime: deterministic ATHERIA-style pulse.
        year_ref = self.last_refresh_year if self.last_refresh_year is not None else 1368.0
        phase = year_ref * 0.37 + 1.0
        purpose = _clamp(0.50 + 0.18 * math.sin(phase), 0.12, 0.92)
        morphic = _clamp(0.46 + 0.17 * math.cos(phase * 1.21), 0.08, 0.90)
        scarcity = _clamp(0.34 + 0.20 * math.sin(phase * 0.73 + 0.6), 0.04, 0.88)
        selection = _clamp(0.44 + 0.14 * math.cos(phase * 0.57), 0.05, 0.92)
        guardian = _clamp(0.42 + 0.16 * math.sin(phase * 0.41 + 1.2), 0.05, 0.94)
        market_last_price = max(0.1, 1.15 + 0.55 * math.sin(phase * 0.69))
        fitness_gradient = _clamp(-0.04 + 0.12 * math.cos(phase * 0.83), -0.20, 0.20)
        system_temperature = _clamp(56.0 + 11.0 * math.sin(phase * 0.52), 32.0, 96.0)
        resource_pool = _clamp(17.0 + 6.0 * math.cos(phase * 0.48), 5.0, 40.0)
        return {
            "purpose_alignment": purpose,
            "morphic_resonance_index": morphic,
            "resource_scarcity": scarcity,
            "selection_pressure": selection,
            "market_guardian_score": guardian,
            "market_last_price": market_last_price,
            "fitness_gradient": fitness_gradient,
            "system_temperature": system_temperature,
            "resource_pool": resource_pool,
            "_hp_mobile": True,
        }

    def _build_state(
        self,
        *,
        year: float,
        sea_state: str,
        goods: List[str],
        cities: List[str],
        refreshed: bool,
    ) -> EconomyState:
        metrics = dict(self.metrics)
        mobile_mode = bool(metrics.get("_hp_mobile"))
        purpose = _clamp(float(metrics.get("purpose_alignment", 0.46)), 0.0, 1.0)
        morphic = _clamp(float(metrics.get("morphic_resonance_index", 0.27)), 0.0, 1.0)
        scarcity = _clamp(float(metrics.get("resource_scarcity", 0.18)), 0.0, 1.0)
        selection = _clamp(float(metrics.get("selection_pressure", 0.40)), 0.0, 1.0)
        guardian = _clamp(float(metrics.get("market_guardian_score", 0.36)), 0.0, 1.0)
        market_last_price = max(0.0, float(metrics.get("market_last_price", 0.0)))
        fitness_grad = float(metrics.get("fitness_gradient", 0.0))
        fitness_norm = _clamp((fitness_grad + 0.22) / 0.44, 0.0, 1.0)
        temp = float(metrics.get("system_temperature", 58.0))
        temp_norm = _clamp((temp - 30.0) / 80.0, 0.0, 1.4)
        resource_pool = float(metrics.get("resource_pool", 18.0))
        pool_norm = _clamp(resource_pool / 40.0, 0.0, 1.6)
        market_price_norm = _clamp(market_last_price / 3.0, 0.0, 1.6)

        phase = (year - 1200) * 0.61
        cycle = math.sin(phase + purpose * 2.2 + morphic * 1.8)

        global_growth = _clamp(
            0.78
            + 0.28 * purpose
            + 0.22 * morphic
            + 0.14 * fitness_norm
            - 0.20 * scarcity
            + 0.06 * cycle,
            0.62,
            1.42,
        )
        global_price_level = _clamp(
            0.82
            + 0.36 * temp_norm
            + 0.24 * scarcity
            + 0.10 * selection
            - 0.14 * pool_norm
            + 0.10 * market_price_norm
            + 0.05 * cycle,
            0.70,
            1.85,
        )

        sea_lc = sea_state.lower()
        if "tobende" in sea_lc:
            global_growth *= 0.93
            global_price_level *= 1.12
        elif "stuermische" in sea_lc:
            global_growth *= 0.96
            global_price_level *= 1.08
        elif "stille" in sea_lc:
            global_growth *= 1.03
            global_price_level *= 0.96
        elif "ruhige" in sea_lc:
            global_growth *= 1.01
            global_price_level *= 0.98

        global_growth = _clamp(global_growth, 0.55, 1.55)
        global_price_level = _clamp(global_price_level, 0.65, 2.1)

        good_factors: Dict[str, float] = {}
        for good_name in goods:
            unit = _hash_unit(f"{good_name}-atheria")
            wave = math.sin((year * 0.53) + unit * 6.283 + morphic * 2.4)
            scarcity_bias = (unit - 0.5) * 0.26
            staple_bonus = 0.08 if good_name in {"Salz", "Getreide", "Hering"} else 0.0
            factor = global_price_level * (
                1.0
                + 0.14 * wave
                + scarcity * (0.18 + scarcity_bias)
                + staple_bonus * temp_norm
            )
            good_factors[good_name] = _clamp(factor, 0.55, 2.60)

        city_factors: Dict[str, float] = {}
        for city_name in cities:
            unit = _hash_unit(f"{city_name}-market")
            wave = math.cos((year * 0.47) + unit * 6.283 + guardian * 2.8)
            factor = 0.92 + 0.09 * wave + 0.06 * guardian - 0.05 * scarcity + 0.03 * (unit - 0.5)
            city_factors[city_name] = _clamp(factor, 0.72, 1.28)

        if refreshed:
            source = "ATHERIA mobil" if mobile_mode else "ATHERIA live"
        elif metrics:
            source = "ATHERIA mobil fortgeschrieben" if mobile_mode else "ATHERIA fortgeschrieben"
        else:
            source = "Fallback-Modell"

        summary = (
            f"{source} | Wachstum {global_growth:.2f} | Preisniveau {global_price_level:.2f} | "
            f"Knappheit {scarcity:.2f}"
        )
        if self.last_error and not refreshed and not mobile_mode:
            summary += f" | Hinweis: {self.last_error}"

        return EconomyState(
            year=year,
            global_growth=global_growth,
            global_price_level=global_price_level,
            resource_scarcity=scarcity,
            good_factors=good_factors,
            city_factors=city_factors,
            source=source,
            summary=summary,
            raw_metrics=metrics,
        )

```

## File: `HP_Android/HP_Game/game_data.py`  
- Path: `HP_Android/HP_Game/game_data.py`  
- Size: 3423 Bytes  
- Modified: 2026-02-24 09:04:30 UTC

```python
from __future__ import annotations

from typing import Dict

STARTING_YEAR = 1368
STARTING_MONTH = 1
MAX_YEARS = 25
MAX_PLAYERS = 6
MIN_NAME_LEN = 3
SAVE_FILE = "savegame.json"
SAVE_DIR = "saves"
SAVE_SLOT_COUNT = 6

MONTHS = [
    "Januar",
    "Februar",
    "Maerz",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]

STARTING_CASH = 6000
STARTING_DEBT = 1800
STARTING_REPUTATION = 10
STARTING_AGE = 20

HANSE_PRIVILEG_GOOD = "Getreide"
HANSE_PRIVILEG_QTY = 120
HANSE_PRIVILEG_MONTHS = 12
HANSE_PRIVILEG_DISCOUNT = 0.08

FLEET_SYNERGY_REQUIRED = 2
FLEET_SYNERGY_HULL_MIN = 90
FLEET_SYNERGY_HEUER_REDUCTION = 0.10

ATHERIA_RESONANCE_GROWTH_MAX = 0.95
ATHERIA_RESONANCE_TARGET_MULT = 2.0

DYNASTY_CHILDREN_TARGET = 3
DYNASTY_INHERITANCE_PER_CHILD = 50000
DYNASTY_AGE_LIMIT = 60

SEA_STATES = [
    "tobende See",
    "stuermische See",
    "bewegte See",
    "ruhige See",
    "stille See",
]

SEA_FACTORS: Dict[str, float] = {
    "tobende See": 1.30,
    "stuermische See": 1.18,
    "bewegte See": 1.08,
    "ruhige See": 0.96,
    "stille See": 0.88,
}

CITIES = [
    "Luebeck",
    "Bergen",
    "Toensberg",
    "Warberg",
    "Malmoe",
    "Ystad",
    "Visby",
    "Riga",
    "Novgorod",
]

GOODS = {
    "Salz": {"base_price": 40, "volatility": 0.24},
    "Holz": {"base_price": 28, "volatility": 0.16},
    "Pelze": {"base_price": 70, "volatility": 0.30},
    "Getreide": {"base_price": 22, "volatility": 0.20},
    "Tuch": {"base_price": 55, "volatility": 0.24},
    "Hering": {"base_price": 30, "volatility": 0.22},
    "Wein": {"base_price": 78, "volatility": 0.28},
}

SHIPYARD = [
    ("Grosse Kogge", 180, 5200, 7200),
    ("Holk", 230, 7500, 10200),
    ("Kraier", 300, 10800, 14600),
]

CITY_PRICE_BIAS = {
    "Luebeck": {"Salz": 1.00, "Holz": 0.94, "Pelze": 1.16, "Getreide": 0.98, "Tuch": 1.02, "Hering": 1.05, "Wein": 1.10},
    "Bergen": {"Salz": 1.12, "Holz": 0.92, "Pelze": 0.90, "Getreide": 1.10, "Tuch": 1.04, "Hering": 0.84, "Wein": 1.16},
    "Toensberg": {"Salz": 1.06, "Holz": 0.90, "Pelze": 0.94, "Getreide": 1.08, "Tuch": 1.06, "Hering": 0.88, "Wein": 1.14},
    "Warberg": {"Salz": 1.04, "Holz": 0.92, "Pelze": 0.96, "Getreide": 1.04, "Tuch": 1.00, "Hering": 0.94, "Wein": 1.08},
    "Malmoe": {"Salz": 0.96, "Holz": 1.04, "Pelze": 1.10, "Getreide": 0.94, "Tuch": 1.02, "Hering": 0.98, "Wein": 1.06},
    "Ystad": {"Salz": 0.94, "Holz": 1.06, "Pelze": 1.12, "Getreide": 0.92, "Tuch": 1.00, "Hering": 0.96, "Wein": 1.08},
    "Visby": {"Salz": 1.08, "Holz": 1.02, "Pelze": 1.00, "Getreide": 0.96, "Tuch": 0.98, "Hering": 0.90, "Wein": 1.02},
    "Riga": {"Salz": 1.16, "Holz": 0.88, "Pelze": 0.86, "Getreide": 1.14, "Tuch": 1.10, "Hering": 0.96, "Wein": 1.20},
    "Novgorod": {"Salz": 1.20, "Holz": 0.84, "Pelze": 0.78, "Getreide": 1.16, "Tuch": 1.14, "Hering": 1.02, "Wein": 1.24},
}

TITLE_STEPS = [
    (0, "Buerger", "Buergerin"),
    (9000, "Haendler", "Haendlerin"),
    (15000, "Kaufmann", "Kauffrau"),
    (23000, "Grosskaufmann", "Grosskauffrau"),
    (34000, "Patrizier", "Patrizierin"),
    (47000, "Bruder", "Schwester"),
    (62000, "Junker", "Edelfrau"),
    (82000, "Diplomat", "Diplomatin"),
    (105000, "Schaffer", "Schafferin"),
    (135000, "Ratsherr", "Ratsfrau"),
    (170000, "Senator", "Senatorin"),
]

```

## File: `HP_Android/HP_Game/game.py`  
- Path: `HP_Android/HP_Game/game.py`  
- Size: 42556 Bytes  
- Modified: 2026-02-24 09:13:42 UTC

```python
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
        self.current_month = STARTING_MONTH
        self.current_sea_state = "bewegte See"
        self._market_cache: Dict[Tuple[int, int, str, str], Dict[str, int]] = {}
        self.economy_engine = AtheriaEconomyEngine()
        economy_year = self.current_year + (self.current_month - 1) / 12.0
        self.economy_state = self.economy_engine.for_year(
            year=economy_year,
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

        while self.players:
            elapsed_months = (self.current_year - STARTING_YEAR) * 12 + (self.current_month - 1)
            if elapsed_months >= MAX_YEARS * 12:
                break
            self.current_sea_state = self.rng.choice(SEA_STATES)
            self._refresh_economy_for_year()
            print()
            print(f"ANNO {self.current_year} {MONTHS[self.current_month - 1]} - {self.current_sea_state}")
            print(f"Atheria-Wirtschaft: {self.economy_state.summary}")
            print("=" * 60)
            for player in self.players:
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
                for ship in player.ships:
                    for good_name in GOODS:
                        ship.cargo.setdefault(good_name, 0)
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
            "month": self.current_month,
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
        discount = self._city_discount(player, player.city)
        if discount > 0:
            price = max(1, int(round(price * (1 - discount))))
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
            parts = [f"{name} {counts.get(name, 0)}/{FLEET_SYNERGY_REQUIRED}" for name, *_ in SHIPYARD]
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
        cache_key = (self.current_year, self.current_month, self.current_sea_state, city)
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
        required = {name: 0 for name, *_ in SHIPYARD}
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

```

## File: `HP_Android/HP_Game/main_pygame.py`  
- Path: `HP_Android/HP_Game/main_pygame.py`  
- Size: 495 Bytes  
- Modified: 2026-02-22 15:46:36 UTC

```python
from __future__ import annotations

import sys


def main() -> int:
    try:
        from pygame_game import run_pygame_game
    except ModuleNotFoundError as exc:
        if exc.name == "pygame":
            print("pygame ist nicht installiert.")
            print("Installation: pip install pygame")
            print("Danach starten mit: python HP_Game/main_pygame.py")
            return 1
        raise
    return run_pygame_game()


if __name__ == "__main__":
    raise SystemExit(main())

```

## File: `HP_Android/HP_Game/main.py`  
- Path: `HP_Android/HP_Game/main.py`  
- Size: 163 Bytes  
- Modified: 2026-02-22 15:38:40 UTC

```python
from __future__ import annotations

from game import HanseGame


def main() -> None:
    game = HanseGame()
    game.run()


if __name__ == "__main__":
    main()

```

## File: `HP_Android/HP_Game/models.py`  
- Path: `HP_Android/HP_Game/models.py`  
- Size: 10440 Bytes  
- Modified: 2026-02-24 09:16:52 UTC

```python
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
    children: int = 0
    turns_in_debt_tower: int = 0
    chronicle: List[str] = field(default_factory=list)
    investments: List[Investment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.ships:
            self.ships = [Ship(city=self.city)]
        self.active_ship_index = max(0, min(self.active_ship_index, len(self.ships) - 1))
        if not isinstance(self.missions, dict):
            self.missions = {}

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
            children=int(data.get("children", 0)),
            turns_in_debt_tower=int(data.get("turns_in_debt_tower", 0)),
            chronicle=[str(item) for item in data.get("chronicle", [])],
            investments=investments,
        )

```

## File: `HP_Android/HP_Game/pygame_game.py`  
- Path: `HP_Android/HP_Game/pygame_game.py`  
- Size: 130972 Bytes  
- Modified: 2026-02-25 06:38:02 UTC

```python
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

from atheria_economy import AtheriaEconomyEngine, EconomyState
from game_data import (
    CITIES,
    CITY_PRICE_BIAS,
    GOODS,
    SHIPYARD,
    MAX_YEARS,
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
    SAVE_SLOT_COUNT,
    SEA_FACTORS,
    SEA_STATES,
    STARTING_AGE,
    STARTING_CASH,
    STARTING_DEBT,
    STARTING_MONTH,
    STARTING_REPUTATION,
    STARTING_YEAR,
    TITLE_STEPS,
)
from models import Player, Ship


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

CANNON_COST = 500
MAX_SHIP_NAME_LEN = 18
AUTO_TURN_INTERVAL_MS = 550
AUTO_MIN_ROUTE_SCORE = 90
AUTO_MIN_RESERVE_MARK = 1400
AUTO_RESERVE_PER_SHIP_MARK = 420
AUTO_SHIP_BUILD_RESERVE = 7000
AUTO_MAX_FLEET_SIZE = 18
AUTO_REPAIR_TARGET = 90
AUTO_MAX_CANNON_BUYS = 2


class PygameHanseApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Hanse - pygame Edition")
        self.is_android = ("ANDROID_ARGUMENT" in os.environ) or (sys.platform == "android")
        if self.is_android:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.screen = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.scale_x = 1.0
        self.scale_y = 1.0
        self._update_display_scale()
        self.clock = pygame.time.Clock()
        self.running = True

        self.font_title = pygame.font.Font(None, 58)
        self.font_h1 = pygame.font.Font(None, 38)
        self.font = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)

        self.image_dir = Path(__file__).with_name("images")
        self.images: Dict[str, pygame.Surface] = {}
        self.scaled_images: Dict[Tuple[str, int, int], pygame.Surface] = {}
        self._load_images()

        self.rng = random.Random()
        self.scene = "menu"

        self.save_dir = Path(__file__).with_name(SAVE_DIR)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.player: Player | None = None
        self.current_year = STARTING_YEAR
        self.current_month = STARTING_MONTH
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self.market_cache: Dict[Tuple[int, int, str, str], Dict[str, int]] = {}
        self.economy_engine = AtheriaEconomyEngine()
        economy_year = self.current_year + (self.current_month - 1) / 12.0
        self.economy_state = self.economy_engine.for_year(
            year=economy_year,
            sea_state=self.current_sea_state,
            goods=GOODS.keys(),
            cities=CITIES,
        )

        self.selected_slot = 1
        self.selected_good = 0
        self.selected_dest = 0
        self.trade_qty = 5
        self.selected_ship_type = 0
        self.selected_fleet_ship = 0
        self.fleet_scroll = 0
        self.shipyard_open = False
        self.ship_cargo_open = False
        self.ship_editor_open = False
        self.ship_name_edit = ""
        self.ship_name_active = False
        self.save_menu_open = False
        self.save_menu_mode: str | None = None
        self.city_market_open = False
        self.missions_open = False
        self.selected_city_market = 0
        self.transfer_drag_good: str | None = None
        self.transfer_drag_value = 0
        self.preview_destination: str | None = None
        self.cheat_open = False
        self.cheat_text = ""
        self.text_input_enabled = False
        self.auto_mode = False
        self.auto_next_tick = 0
        self.time_limit_reached = False
        self.fleet_drag_active = False
        self.fleet_drag_start_y = 0
        self.fleet_drag_start_scroll = 0
        self.fleet_drag_moved = False

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
        self.city_market_rows: List[Tuple[int, pygame.Rect]] = []
        self.transfer_sliders: List[Tuple[str, pygame.Rect, int, int]] = []
        self.ship_name_input_rect: pygame.Rect | None = None
        self.messages: List[str] = [
            "Willkommen in Hanse (pygame).",
            "Neues Spiel anlegen oder Slot laden.",
        ]

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
                scaled = pygame.transform.smoothscale(self.screen, self.window.get_size())
                self.window.blit(scaled, (0, 0))
            pygame.display.flip()
            self.clock.tick(FPS)

        self._set_text_input_enabled(False)
        pygame.quit()
        return 0

    def _handle_key(self, event: pygame.event.Event) -> None:
        back_key = getattr(pygame, "K_AC_BACK", -1)
        is_back = event.key in {pygame.K_ESCAPE, back_key}
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

    def _handle_click(self, pos: Tuple[int, int]) -> None:
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
        if (
            self.scene != "game"
            or self.shipyard_open
            or self.ship_cargo_open
            or self.ship_editor_open
            or self.city_market_open
            or self.missions_open
        ):
            return
        if self.player is None:
            return
        mouse = self._virtual_mouse_pos()
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
        elif key == "game_cargo":
            self._open_ship_cargo()
        elif key == "game_shipyard":
            self._open_shipyard()
        elif key == "game_ship_editor":
            self._open_ship_editor()
        elif key == "game_city_prices":
            self.city_market_open = True
        elif key == "game_missions":
            self.missions_open = True
        elif key == "game_repair_hull":
            self._repair("hull")
        elif key == "game_repair_rig":
            self._repair("rigging")
        elif key == "game_auto":
            self._toggle_auto_mode()
        elif key == "game_next_year":
            self._advance_year()
        elif key == "game_save":
            if not self.save_menu_open or self.save_menu_mode != "save":
                self.save_menu_open = True
                self.save_menu_mode = "save"
            else:
                self._save_slot(self.selected_slot)
                self.save_menu_open = False
                self.save_menu_mode = None
        elif key == "game_load":
            if not self.save_menu_open or self.save_menu_mode != "load":
                self.save_menu_open = True
                self.save_menu_mode = "load"
            else:
                self._load_slot(self.selected_slot)
                self.save_menu_open = False
                self.save_menu_mode = None
        elif key == "game_menu":
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            self.save_menu_open = False
            self.save_menu_mode = None
            self.city_market_open = False
            self.missions_open = False
            self.cheat_open = False
            self.cheat_text = ""
            self.auto_mode = False
            self.scene = "menu"

    def _toggle_auto_mode(self) -> None:
        if self.player is None or not self.player.alive:
            return
        self.auto_mode = not self.auto_mode
        if self.auto_mode:
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            self.city_market_open = False
            self.missions_open = False
            self.save_menu_open = False
            self.save_menu_mode = None
            self.cheat_open = False
            self.cheat_text = ""
            self.transfer_drag_good = None
            self.auto_next_tick = pygame.time.get_ticks() + 120
            self._log("Auto-Modus aktiv: Atheria steuert Handel, Flotte und Reisen.")
        else:
            self._log("Auto-Modus beendet.")

    def _run_auto_mode(self) -> None:
        if not self.auto_mode or self.scene != "game" or self.player is None:
            return
        if self.time_limit_reached:
            self.auto_mode = False
            self._log("Auto-Modus beendet: Zeitlimit erreicht.")
            return
        if not self.player.alive:
            self.auto_mode = False
            self._log("Auto-Modus beendet: Handelshaus erloschen.")
            return
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
        if self.auto_mode and self.time_limit_reached:
            self.auto_mode = False
            self._log("Auto-Modus beendet: Zeitlimit erreicht.")

    def _auto_player_reserve(self) -> int:
        if self.player is None:
            return 0
        return max(AUTO_MIN_RESERVE_MARK, 500 + len(self.player.ships) * AUTO_RESERVE_PER_SHIP_MARK)

    def _auto_travel_cost(self, origin: str, target: str) -> int:
        distance = abs(CITIES.index(origin) - CITIES.index(target)) + 1
        return 60 + distance * 25

    def _auto_play_month(self) -> None:
        if self.player is None or not self.player.alive:
            self.auto_mode = False
            return
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
        self._advance_year()

    def _auto_build_ship_if_possible(self) -> None:
        if self.player is None or self.player.turns_in_debt_tower > 0:
            return
        if len(self.player.ships) >= AUTO_MAX_FLEET_SIZE:
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
        if not SHIPYARD:
            return
        cheapest = min(cost for _, _, _, cost in SHIPYARD)
        if budget < cheapest:
            return

        selected_idx: int | None = None
        mission = self.player.missions.get("fleet_synergy", {})
        if mission.get("state") != "completed":
            counts = {name: 0 for name, *_ in SHIPYARD}
            for ship in self.player.ships:
                if ship.name in counts:
                    counts[ship.name] += 1
            missing: List[Tuple[int, int, int]] = []
            for idx, (name, _cap, _value, cost) in enumerate(SHIPYARD):
                owned = counts.get(name, 0)
                if owned < FLEET_SYNERGY_REQUIRED and cost <= budget:
                    missing.append((owned, cost, idx))
            if missing:
                selected_idx = min(missing)[2]

        if selected_idx is None:
            affordable = [
                (cap, -cost, idx)
                for idx, (_name, cap, _value, cost) in enumerate(SHIPYARD)
                if cost <= budget
            ]
            if affordable:
                selected_idx = max(affordable)[2]

        if selected_idx is None:
            return
        self.selected_ship_type = selected_idx
        self._buy_selected_ship_type()

    def _auto_maintain_ship(self, ship: Ship) -> None:
        if self.player is None or ship.is_at_sea:
            return
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

        cannon_target = 4
        if self.player.money > 14000:
            cannon_target = 7
        if self.player.money > 28000:
            cannon_target = 10
        if self.player.money > 50000:
            cannon_target = 12
        bought = 0
        while ship.cannons < cannon_target and bought < AUTO_MAX_CANNON_BUYS:
            if self.player.money - CANNON_COST < reserve:
                break
            self._buy_cannons(ship, 1)
            bought += 1

    def _auto_unload_ship(self, ship: Ship) -> int:
        if self.player is None:
            return 0
        storage = self._storage_for_city(ship.city)
        locks = self._locks_for_city(ship.city)
        moved = 0
        current_prices = self._market_prices(ship.city)
        for good_name in GOODS:
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
        for good_name in GOODS:
            qty = storage.get(good_name, 0)
            if qty <= 0:
                continue
            locked_revenue, locked_sold = self._consume_locked_lots(city, good_name, qty)
            remaining = qty - locked_sold
            revenue = locked_revenue + remaining * prices[good_name]
            storage[good_name] = max(0, storage.get(good_name, 0) - qty)
            self.player.money += revenue
            self._record_hanse_delivery(city, good_name, qty)
            total_revenue += revenue
            sold_goods += 1
        if sold_goods > 0:
            self.player.reputation = min(200, self.player.reputation + 1)
            self._log(f"Auto-Handel ({city}): {sold_goods} Waren verkauft, +{total_revenue} Mark.")
        return total_revenue

    def _auto_buy_good(self, city: str, good_name: str, qty: int) -> int:
        if self.player is None or qty <= 0:
            return 0
        price = self._market_prices(city)[good_name]
        discount = self._city_discount(city)
        if discount > 0:
            price = max(1, int(round(price * (1 - discount))))
        affordable = self.player.money // price
        bought = min(qty, affordable)
        if bought <= 0:
            return 0
        storage = self._storage_for_city(city)
        storage[good_name] = storage.get(good_name, 0) + bought
        self.player.money -= bought * price
        self.player.reputation = min(200, self.player.reputation + 1)
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
        budget = max(0, self.player.money - reserve - travel_cost)
        capacity = ship.cargo_space_left
        if budget <= 0 or capacity <= 0:
            return travel_cost, 0, [], -travel_cost

        city_prices = self._market_prices(ship.city)
        target_prices = self._market_prices(target)
        discount = self._city_discount(ship.city)
        opportunities: List[Tuple[float, int, int, str]] = []
        for good_name in GOODS:
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
        for city_name in CITIES:
            if city_name == ship.city:
                continue
            _travel_cost, expected_profit, plan, score = self._auto_plan_route(ship, city_name)
            if not plan:
                continue
            if score > best_score:
                best_score = score
                best_target = city_name
                best_plan = plan
                best_profit = expected_profit
        if not best_plan or best_score < AUTO_MIN_ROUTE_SCORE:
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
        destinations = [city_name for city_name in CITIES if city_name != ship.city]
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
        if self.selected_ship_type >= len(SHIPYARD):
            self.selected_ship_type = 0

    def _handle_shipyard_click(self, pos: Tuple[int, int]) -> None:
        for idx, rect in self.ship_rows:
            if rect.collidepoint(pos):
                self.selected_ship_type = idx
                return
        button = self._clicked_button(pos)
        if button == "shipyard_buy":
            self._buy_selected_ship_type()
            return
        if button == "shipyard_close":
            self.shipyard_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            return

    def _buy_selected_ship_type(self) -> None:
        if self.player is None:
            return
        if not SHIPYARD:
            self._log("Keine Schiffe verfuegbar.")
            return
        if self.selected_ship_type >= len(SHIPYARD):
            self.selected_ship_type = 0
        name, cap, value, cost = SHIPYARD[self.selected_ship_type]
        if self.player.money < cost:
            self._log(f"Nicht genug Mark. Benoetigt: {cost}")
            return
        self.player.money -= cost
        new_ship = Ship(
            name=name,
            cargo_capacity=cap,
            value=value,
            city=self.player.city,
            cargo={good: 0 for good in GOODS},
        )
        self.player.ships.append(new_ship)
        self.selected_fleet_ship = len(self.player.ships) - 1
        self.shipyard_open = False
        self._log(f"Neues Schiff gekauft: {name}. Kosten: {cost} Mark.")
        self.player.chronicle.append(f"ANNO {self.current_year}: {name} als neues Schiff erworben.")

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
        for good in GOODS:
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
        required = {name: 0 for name, *_ in SHIPYARD}
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
        self.player.children = 0
        self.player.turns_in_debt_tower = 0
        if self.player.money < inheritance:
            self.player.money = inheritance
        self.player.chronicle.append(f"ANNO {self.current_year}: Erbe angetreten.")
        self._log("Familiendynastie: Ein Erbe tritt das Handelshaus an.")
        return True

    def _locks_for_city(self, city: str) -> Dict[str, List[Dict[str, int]]]:
        if self.player is None:
            return {}
        locks = self.player.warehouse_locks.setdefault(city, {})
        for good in GOODS:
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
        destinations = [city for city in CITIES if city != ship.city]
        if destinations:
            self.selected_dest = min(self.selected_dest, len(destinations) - 1)
            self.preview_destination = destinations[self.selected_dest]
        else:
            self.preview_destination = None

    def _open_ship_editor(self) -> None:
        if self.player is None or not self.player.alive:
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        self.ship_editor_open = True
        self.ship_name_active = False
        self.ship_name_edit = ship.custom_name

    def _handle_ship_cargo_click(self, pos: Tuple[int, int]) -> None:
        ship = self._selected_ship()
        if ship is None:
            self.ship_cargo_open = False
            return
        for idx, rect in self.dest_rows:
            if rect.collidepoint(pos):
                self.selected_dest = idx
                destinations = [city for city in CITIES if city != ship.city]
                if destinations:
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
        if button == "cargo_close":
            self.ship_cargo_open = False
            self.transfer_drag_good = None
            return

    def _handle_ship_editor_click(self, pos: Tuple[int, int]) -> None:
        ship = self._selected_ship()
        if ship is None:
            self.ship_editor_open = False
            return
        if self.ship_name_input_rect and self.ship_name_input_rect.collidepoint(pos):
            self.ship_name_active = True
            if not self.ship_name_edit:
                self.ship_name_edit = ship.custom_name or ship.display_name
            return
        button = self._clicked_button(pos)
        if button == "editor_save":
            self._submit_ship_name()
            return
        if button == "editor_cannon_1":
            self._buy_cannons(ship, 1)
            return
        if button == "editor_cannon_5":
            self._buy_cannons(ship, 5)
            return
        if button == "editor_close":
            self.ship_editor_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
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
        ship = self._selected_ship()
        if ship is None:
            self.ship_name_active = False
            self.ship_name_edit = ""
            return
        name = self.ship_name_edit.strip()
        ship.custom_name = name
        self.ship_name_active = False
        self.ship_name_edit = ""
        self._log(f"Schiffsname gesetzt: {ship.display_name}")

    def _buy_cannons(self, ship: Ship, qty: int) -> None:
        if self.player is None:
            return
        if ship.is_at_sea:
            self._log("Kanonen koennen nur im Hafen montiert werden.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        cost = CANNON_COST * qty
        if self.player.money < cost:
            self._log("Nicht genug Mark fuer Kanonen.")
            return
        self.player.money -= cost
        ship.cannons += qty
        self._log(f"{qty} Kanone(n) gekauft fuer {cost} Mark.")

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

    def _draw_menu(self) -> None:
        title = self.font_title.render("HANSE - pygame Edition", True, TEXT)
        self.screen.blit(title, (50, 35))
        subtitle = self.font.render("Grafische Version mit Save-Slots", True, TEXT_DIM)
        self.screen.blit(subtitle, (54, 86))

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
        self._draw_text(
            "Hinweis: F5/F9 im Spiel speichern/laden den gewaehlten Slot.",
            self.font_small,
            TEXT_DIM,
            (980, 470),
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
            self._draw_text(
                f"Ladung {ship.total_cargo}/{ship.cargo_capacity} | Kanonen {ship.cannons}{eta_text}",
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
        fleet_can_scroll = self._fleet_max_scroll() > 0
        self._draw_button("game_fleet_up", pygame.Rect(fleet_panel.right - 78, 176, 34, 28), "^", fleet_can_scroll)
        self._draw_button("game_fleet_down", pygame.Rect(fleet_panel.right - 40, 176, 34, 28), "v", fleet_can_scroll)
        self._draw_button("game_missions", pygame.Rect(log_panel.right - 150, log_panel.y + 6, 130, 36), "Missionen", True)

        target_prices = None
        if self.preview_destination and self.preview_destination != active_city:
            target_prices = self._market_prices(self.preview_destination)
        self._draw_text(f"Ort: {active_city}", self.font_small, TEXT_DIM, (38, 206))
        if self.preview_destination and self.preview_destination != active_city:
            self._draw_text(f"Ziel: {self.preview_destination}", self.font_small, ACCENT_2, (190, 206))

        self.goods_rows = []
        goods_list = list(GOODS.keys())
        mouse_pos = self._virtual_mouse_pos()
        y = 228
        for idx, good_name in enumerate(goods_list):
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
            if target_prices:
                self._draw_text(f"Ziel {target_prices[good_name]:>4}", self.font_small, TEXT_DIM, (330, y + 12))
                self._draw_text(f"Lager {qty:>4}", self.font_small, TEXT_DIM, (470, y + 12))
            else:
                self._draw_text(f"Lager {qty:>4}", self.font_small, TEXT_DIM, (454, y + 12))
            self.goods_rows.append((idx, row))
            y += 50

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

        max_lines = 7
        lines = self.messages[-max_lines:]
        y = 654
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
        if self.cheat_open:
            self._draw_cheat_prompt()

    def _draw_shipyard(self) -> None:
        if self.player is None:
            return
        player = self.player
        if self.selected_ship_type >= len(SHIPYARD):
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
        y = panel.y + 96
        for idx, (name, cap, value, cost) in enumerate(SHIPYARD):
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

        if SHIPYARD:
            _name, _cap, _value, cost = SHIPYARD[self.selected_ship_type]
            self._draw_text(
                f"Preis: {cost} Mark",
                self.font,
                ACCENT_2,
                (panel.x + 24, panel.y + 320),
            )

        can_buy = player.alive and player.turns_in_debt_tower == 0
        self._draw_button(
            "shipyard_buy",
            pygame.Rect(panel.x + panel.width - 262, panel.y + panel.height - 62, 120, 44),
            "Kaufen",
            can_buy,
            accent=True,
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
        self.transfer_sliders = []
        y = panel.y + 140
        for good_name in GOODS:
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

        self.dest_rows = []
        destinations = [city for city in CITIES if city != ship.city]
        if destinations and self.selected_dest >= len(destinations):
            self.selected_dest = 0
        y = panel.y + 140
        for idx, city_name in enumerate(destinations):
            row = pygame.Rect(dest_x, y, 228, 34)
            selected = idx == self.selected_dest
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            self._draw_text(city_name, self.font_small, TEXT, (row.x + 8, row.y + 8))
            self.dest_rows.append((idx, row))
            y += 40

        travel_cost = None
        if destinations:
            target = destinations[self.selected_dest]
            distance = abs(CITIES.index(ship.city) - CITIES.index(target)) + 1
            travel_cost = 60 + distance * 25
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
        ship = self._selected_ship()
        if ship is None:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 180))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(360, 240, 600, 320)
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
            (panel.x + 24, panel.y + 58),
        )
        self._draw_text(
            f"Rumpf {ship.hull}% / Takelage {ship.rigging}% | Kanonen {ship.cannons}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 82),
        )

        self._draw_text("Name:", self.font_small, TEXT, (panel.x + 24, panel.y + 120))
        input_box = pygame.Rect(panel.x + 24, panel.y + 146, panel.width - 48, 44)
        self.ship_name_input_rect = input_box
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT if self.ship_name_active else (60, 85, 122), input_box, width=2, border_radius=8)
        display_name = self.ship_name_edit if self.ship_name_active else (ship.custom_name or ship.display_name)
        self._draw_text(display_name or "_", self.font, TEXT, (input_box.x + 10, input_box.y + 10))

        cannon_cost_1 = CANNON_COST
        cannon_cost_5 = CANNON_COST * 5
        icon = self._get_scaled("icon_cannon", (28, 28))
        if icon:
            self.screen.blit(icon, (panel.x + 24, panel.y + 200))
            self._draw_text(
                f"Kanonen kosten {CANNON_COST} Mark pro Stueck.",
                self.font_small,
                TEXT_DIM,
                (panel.x + 60, panel.y + 204),
            )
        else:
            self._draw_text(
                f"Kanonen kosten {CANNON_COST} Mark pro Stueck.",
                self.font_small,
                TEXT_DIM,
                (panel.x + 24, panel.y + 204),
            )
        self._draw_button(
            "editor_cannon_1",
            pygame.Rect(panel.x + 24, panel.y + 232, 150, 40),
            f"+1 ({cannon_cost_1})",
            self.player.money >= cannon_cost_1,
        )
        self._draw_button(
            "editor_cannon_5",
            pygame.Rect(panel.x + 184, panel.y + 232, 150, 40),
            f"+5 ({cannon_cost_5})",
            self.player.money >= cannon_cost_5,
        )
        self._draw_button(
            "editor_save",
            pygame.Rect(panel.x + panel.width - 252, panel.y + panel.height - 58, 120, 40),
            "Speichern",
            True,
            accent=True,
        )
        self._draw_button(
            "editor_close",
            pygame.Rect(panel.x + panel.width - 122, panel.y + panel.height - 58, 98, 40),
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

        self.city_market_rows = []
        city_x = panel.x + 24
        city_y = panel.y + 90
        city_w = 220
        if self.selected_city_market >= len(CITIES):
            self.selected_city_market = 0
        for idx, city_name in enumerate(CITIES):
            row = pygame.Rect(city_x, city_y, city_w, 34)
            selected = idx == self.selected_city_market
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            self._draw_text(city_name, self.font_small, TEXT, (row.x + 8, row.y + 8))
            self.city_market_rows.append((idx, row))
            city_y += 40

        prices_x = panel.x + 270
        prices_y = panel.y + 90
        prices_w = panel.width - 300
        selected_city = CITIES[self.selected_city_market]
        prices = self._market_prices(selected_city)
        header = f"Preise in {selected_city}"
        self._draw_text(header, self.font_small, ACCENT_2, (prices_x, prices_y - 24))
        for idx, good_name in enumerate(GOODS.keys()):
            row = pygame.Rect(prices_x, prices_y, prices_w, 36)
            pygame.draw.rect(self.screen, BG_PANEL_ALT, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            self._draw_text(good_name, self.font_small, TEXT, (row.x + 10, row.y + 10))
            self._draw_text(f"{prices[good_name]:>4}", self.font_small, TEXT_DIM, (row.right - 60, row.y + 10))
            prices_y += 42

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
                return
        button = self._clicked_button(pos)
        if button == "city_market_close":
            self.city_market_open = False

    def _draw_missions(self) -> None:
        if self.player is None:
            return
        self._init_missions()
        self._update_fleet_synergy()
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
            parts = [f"{name} {counts.get(name, 0)}/{FLEET_SYNERGY_REQUIRED}" for name, *_ in SHIPYARD]
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
        label_surface = self.font_small.render(label, True, fg)
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
        self.screen.blit(font.render(text, True, color), pos)

    def _shorten_text(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max(0, max_len - 3)].rstrip() + "..."

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
            goods=GOODS.keys(),
            cities=CITIES,
        )
        self.market_cache.clear()

    def _start_new_game(self) -> None:
        name = self.new_name.strip()
        if len(name) < MIN_NAME_LEN:
            self._log(f"Fehler: Name braucht mindestens {MIN_NAME_LEN} Zeichen.")
            return

        city = CITIES[self.new_city]
        ship = Ship(city=city, cargo={good: 0 for good in GOODS})
        self.player = Player(
            name=name,
            gender=self.new_gender,
            city=city,
            money=STARTING_CASH,
            debt=STARTING_DEBT,
            reputation=STARTING_REPUTATION,
            age=STARTING_AGE + self.rng.randint(0, 4),
            ships=[ship],
            warehouses={city: {good: 0 for good in GOODS}},
            warehouse_locks={city: {good: [] for good in GOODS}},
        )
        self.current_year = STARTING_YEAR
        self.current_month = STARTING_MONTH
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._refresh_economy_for_year()
        self.selected_good = 0
        self.selected_dest = 0
        self.selected_ship_type = 0
        self.selected_fleet_ship = 0
        self.fleet_scroll = 0
        self.shipyard_open = False
        self.ship_cargo_open = False
        self.ship_editor_open = False
        self.preview_destination = None
        self.save_menu_open = False
        self.save_menu_mode = None
        self.city_market_open = False
        self.missions_open = False
        self.cheat_open = False
        self.cheat_text = ""
        self.auto_mode = False
        self.auto_next_tick = 0
        self.time_limit_reached = False
        self.messages = []
        self._init_missions()
        self._update_missions_monthly()
        self.player.chronicle.append(f"ANNO {self.current_year}: Kontor in {city} geoeffnet.")
        self._log(f"Neues Handelshaus gegruendet in {city}.")
        self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")
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
        payload = {
            "year": self.current_year,
            "month": self.current_month,
            "sea_state": self.current_sea_state,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "players": [self.player.to_dict()],
            "atheria_economy_engine": self.economy_engine.to_dict(),
            "atheria_economy_state": self.economy_state.to_dict(),
        }
        try:
            path = self._slot_path(slot)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._log(f"Spiel in Slot {slot} gespeichert.")
        except OSError:
            self._log(f"Fehler: Slot {slot} konnte nicht gespeichert werden.")

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
            for ship in self.player.ships:
                for good_name in GOODS:
                    ship.cargo.setdefault(good_name, 0)
            for city in CITIES:
                storage = self.player.warehouses.setdefault(city, {})
                for good_name in GOODS:
                    storage.setdefault(good_name, 0)
                self._locks_for_city(city)
            self.current_year = int(raw.get("year", STARTING_YEAR))
            self.current_month = int(raw.get("month", STARTING_MONTH))
            self.current_month = max(1, min(12, self.current_month))
            self.current_sea_state = str(raw.get("sea_state", "bewegte See"))
            econ_engine_data = raw.get("atheria_economy_engine")
            if isinstance(econ_engine_data, dict):
                self.economy_engine.load_dict(econ_engine_data)
            econ_state_data = raw.get("atheria_economy_state")
            if isinstance(econ_state_data, dict):
                self.economy_state = EconomyState.from_dict(econ_state_data)
            else:
                self._refresh_economy_for_year()
            self.market_cache.clear()
            self.scene = "game"
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.selected_ship_type = 0
            self.selected_fleet_ship = 0
            self.fleet_scroll = 0
            self.preview_destination = None
            self.save_menu_open = False
            self.save_menu_mode = None
            self.city_market_open = False
            self.missions_open = False
            self.cheat_open = False
            self.cheat_text = ""
            self.auto_mode = False
            self.auto_next_tick = 0
            self.time_limit_reached = False
            self._init_missions()
            self._log(f"Slot {slot} geladen.")
            self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")
            if len(players) > 1:
                self._log("Mehrspieler-Save erkannt: erster Spieler geladen.")
        except (OSError, ValueError, TypeError, KeyError):
            self._log(f"Fehler: Slot {slot} konnte nicht geladen werden.")

    def _market_prices(self, city: str) -> Dict[str, int]:
        key = (self.current_year, self.current_month, self.current_sea_state, city)
        if key in self.market_cache:
            return self.market_cache[key]

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
        self.market_cache[key] = prices
        return prices

    def _buy_selected_good(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Kaufen nicht moeglich.")
            return

        good = list(GOODS.keys())[self.selected_good]
        price = self._market_prices(self.player.city)[good]
        discount = self._city_discount(self.player.city)
        if discount > 0:
            price = max(1, int(round(price * (1 - discount))))
        storage = self._storage_for_city(self.player.city)
        max_qty = min(self.player.money // price, self.trade_qty)
        if max_qty <= 0:
            self._log("Nicht genug Mark.")
            return
        self.player.money -= max_qty * price
        storage[good] = storage.get(good, 0) + max_qty
        self.player.reputation = min(200, self.player.reputation + 1)
        self._log(f"Gekauft: {max_qty} {good} fuer {max_qty * price} Mark (Lager {self.player.city}).")

    def _sell_selected_good(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Verkaufen nicht moeglich.")
            return

        good = list(GOODS.keys())[self.selected_good]
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
        self.player.money += revenue
        self.player.reputation = min(200, self.player.reputation + 1)
        self._record_hanse_delivery(self.player.city, good, qty)
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
        destinations = [city for city in CITIES if city != ship.city]
        if not destinations:
            self._log("Keine Reiseziele verfuegbar.")
            return
        self.selected_dest = max(0, min(self.selected_dest, len(destinations) - 1))
        target = destinations[self.selected_dest]
        distance = abs(CITIES.index(ship.city) - CITIES.index(target)) + 1
        travel_cost = 60 + distance * 25
        if self.player.money < travel_cost:
            self._log("Nicht genug Mark fuer die Reise.")
            return

        origin = ship.city
        self.player.money -= travel_cost
        ship.is_at_sea = True
        ship.destination = target
        ship.travel_turns_left = max(1, distance)
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
        pirate_chance = risk / (1 + ship.cannons * 0.5)
        if self.rng.random() < pirate_chance:
            goods = [good for good, qty in ship.cargo.items() if qty > 0]
            if goods:
                lost_good = self.rng.choice(goods)
                lost_qty = self.rng.randint(1, max(1, ship.cargo[lost_good] // 2))
                ship.cargo[lost_good] -= lost_qty
                if lost_good in ship.locked_qty:
                    remaining_locked = max(0, ship.locked_qty[lost_good] - lost_qty)
                    if remaining_locked > 0:
                        ship.locked_qty[lost_good] = remaining_locked
                    else:
                        ship.locked_qty.pop(lost_good, None)
                        ship.locked_prices.pop(lost_good, None)
                rep_loss = max(1, int(round(2 / (1 + ship.cannons * 0.5))))
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
        elapsed_months = (self.current_year - STARTING_YEAR) * 12 + (self.current_month - 1)
        if elapsed_months >= MAX_YEARS * 12:
            if not self.time_limit_reached:
                self._log("Zeitlimit erreicht. Lade einen Slot oder starte neu.")
            self.time_limit_reached = True
            return
        self.time_limit_reached = False

        growth = self.economy_state.global_growth
        price_level = self.economy_state.global_price_level

        if self.player.turns_in_debt_tower > 0:
            self.player.turns_in_debt_tower -= 1
            self._log(f"Schuldturm: noch {self.player.turns_in_debt_tower} Monat(e).")
            self.player.chronicle.append(f"ANNO {self.current_year}: Schuldturm ({MONTHS[self.current_month - 1]}).")

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
            self.player.age += 1
            self._resolve_life_events()
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._refresh_economy_for_year()
        self._update_missions_monthly()
        self._log(f"{MONTHS[self.current_month - 1]} {self.current_year}: {self.current_sea_state}.")
        self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")

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
            if self.auto_mode and SHIPYARD:
                cheapest_idx = min(range(len(SHIPYARD)), key=lambda idx: SHIPYARD[idx][3])
                cheapest_cost = SHIPYARD[cheapest_idx][3]
                if self.player.money < cheapest_cost:
                    deficit = cheapest_cost - self.player.money
                    self.player.debt += deficit
                    self.player.money = cheapest_cost
                    self._log(f"Auto-Modus: Notfinanzierung {deficit} Mark fuer Ersatzschiff.")
                if self.player.city not in CITIES:
                    self.player.city = CITIES[0]
                self.selected_ship_type = cheapest_idx
                self._buy_selected_ship_type()
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

        if (not self.player.married) and self.player.age >= 23 and self._net_worth(self.player, self._market_prices(self.player.city)) > 12000:
            if self.rng.random() < 0.16:
                self.player.married = True
                self.player.chronicle.append(f"ANNO {self.current_year}: den Bund der Ehe eingegangen.")
                self._log("Historie: den Bund der Ehe eingegangen.")

        if self.player.married and self.rng.random() < 0.24:
            self.player.children += 1
            self.player.chronicle.append(f"ANNO {self.current_year}: Kind geboren.")
            self._log("Historie: Kind geboren.")

        if self.player.age > 60:
            death_chance = min(0.42, (self.player.age - 60) * 0.025)
            if self.rng.random() < death_chance:
                if self._apply_dynasty_heir():
                    return
                self.player.alive = False
                self.player.chronicle.append(f"ANNO {self.current_year}: Tod des Vorfahren.")
                self._log("Tod des Vorfahren.")

    def _update_title(self) -> None:
        if self.player is None:
            return
        worth = self._net_worth(self.player, self._market_prices(self.player.city))
        new_index = 0
        for idx, (threshold, _, _) in enumerate(TITLE_STEPS):
            if worth >= threshold:
                new_index = idx
        if new_index > self.player.title_index:
            self.player.title_index = new_index
            title = self._title_for(self.player)
            self.player.chronicle.append(f"ANNO {self.current_year}: In den Stand '{title}' erhoben.")
            self._log(f"Aufstieg: {title}")

    def _title_for(self, player: Player) -> str:
        _, male, female = TITLE_STEPS[min(player.title_index, len(TITLE_STEPS) - 1)]
        return female if player.gender == "w" else male

    def _net_worth(self, player: Player, prices: Dict[str, int]) -> int:
        cargo_value = 0
        for ship in player.ships:
            cargo_value += sum(prices[good] * qty for good, qty in ship.cargo.items())
        for goods in player.warehouses.values():
            cargo_value += sum(prices[good] * qty for good, qty in goods.items())
        fleet_value = sum(ship.value for ship in player.ships)
        return player.money + cargo_value + fleet_value - player.debt + player.reputation * 150

    def _log(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 200:
            self.messages = self.messages[-160:]


def run_pygame_game() -> int:
    app = PygameHanseApp()
    return app.run()

```

## File: `HP_Android/main.py`  
- Path: `HP_Android/main.py`  
- Size: 286 Bytes  
- Modified: 2026-02-24 09:19:34 UTC

```python
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.join(HERE, "HP_Game")
if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)

from pygame_game import run_pygame_game


if __name__ == "__main__":
    raise SystemExit(run_pygame_game())

```

## File: `HP_Android/scripts/generate_icon.py`  
- Path: `HP_Android/scripts/generate_icon.py`  
- Size: 1355 Bytes  
- Modified: 2026-02-25 06:00:08 UTC

```python
"""Generate a square Android launcher icon from ship_kogge.webp."""

from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "HP_Game" / "images" / "ship_kogge.webp"
OUT = ROOT / "assets" / "icon_launcher.png"
SIZE = 512
PADDING_RATIO = 0.74


def main() -> int:
    pygame.init()
    try:
        image = pygame.image.load(str(SRC))
        canvas = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
        canvas.fill((18, 28, 42, 255))

        max_dim = int(SIZE * PADDING_RATIO)
        scale = min(max_dim / image.get_width(), max_dim / image.get_height())
        new_size = (
            max(1, int(image.get_width() * scale)),
            max(1, int(image.get_height() * scale)),
        )
        ship = pygame.transform.smoothscale(image, new_size)

        x = (SIZE - new_size[0]) // 2
        y = (SIZE - new_size[1]) // 2
        canvas.blit(ship, (x, y))
        pygame.draw.rect(
            canvas,
            (210, 178, 108, 255),
            pygame.Rect(10, 10, SIZE - 20, SIZE - 20),
            width=6,
            border_radius=24,
        )

        OUT.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(canvas, str(OUT))
        print(f"Icon generated: {OUT}")
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())

```

