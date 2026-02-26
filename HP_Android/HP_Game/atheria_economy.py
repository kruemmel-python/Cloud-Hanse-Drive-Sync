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
