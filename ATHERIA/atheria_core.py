from __future__ import annotations

import ast
import asyncio
import csv
import hashlib
import inspect
import json
import logging
import math
import os
import random
import sqlite3
import threading
import time
import types
import urllib.error
import urllib.request
import uuid
import weakref
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, Optional, Set, Tuple

import torch


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("atheria")


# Requested global controls
System_Temperature: float = 25.0
Entanglement_Registry: Dict[str, Set[str]] = {}
POINCARE_DIMS = 6


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class CorePopulationRegistry:
    """
    Process-local registry for independently running ATHERIA cores.
    Used by inter-core features (HGT, markets, global dreaming).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cores: Dict[str, weakref.ReferenceType[Any]] = {}

    def _prune_locked(self) -> None:
        stale = []
        for core_id, ref in self._cores.items():
            if ref() is None:
                stale.append(core_id)
        for core_id in stale:
            self._cores.pop(core_id, None)

    def register(self, core: "AtheriaCore") -> None:
        with self._lock:
            self._cores[core.core_id] = weakref.ref(core)
            self._prune_locked()

    def unregister(self, core_id: str) -> None:
        with self._lock:
            self._cores.pop(core_id, None)
            self._prune_locked()

    def all_cores(self, *, running_only: bool = True) -> list["AtheriaCore"]:
        with self._lock:
            self._prune_locked()
            out: list["AtheriaCore"] = []
            for ref in self._cores.values():
                core = ref()
                if core is None:
                    continue
                if running_only and not core.running:
                    continue
                out.append(core)
            return out

    def peers(self, core_id: str, *, running_only: bool = True) -> list["AtheriaCore"]:
        return [core for core in self.all_cores(running_only=running_only) if core.core_id != core_id]

    def count(self, *, running_only: bool = True) -> int:
        return len(self.all_cores(running_only=running_only))


GLOBAL_CORE_REGISTRY = CorePopulationRegistry()


class GlobalMorphicNode:
    """
    Collective field-memory node for inter-core dream synchronization.
    """

    def __init__(
        self,
        registry: CorePopulationRegistry,
        *,
        dream_ttl_seconds: float = 28.0,
        trauma_ttl_seconds: float = 48.0,
    ) -> None:
        self.registry = registry
        self.dream_ttl_seconds = dream_ttl_seconds
        self.trauma_ttl_seconds = trauma_ttl_seconds
        self._lock = threading.RLock()
        self._dream_records: Deque[Dict[str, Any]] = deque(maxlen=768)
        self._trauma_records: Deque[Dict[str, Any]] = deque(maxlen=512)
        self.sync_events = 0
        self.trauma_broadcast_events = 0

    def publish_sleep_dream(
        self,
        *,
        core: "AtheriaCore",
        replay_labels: list[str],
        replay_strength: float,
    ) -> None:
        pattern = core.holographic_field.pattern.detach().clone()
        if float(torch.norm(pattern, p=2)) <= 1e-8:
            pattern = _fold_vector_from_text(core.core_id, dims=int(core.holographic_field.pattern.numel()))
        future = core.holographic_field.last_future_projection.detach().clone()
        if float(torch.norm(future, p=2)) <= 1e-8:
            future = pattern.detach().clone()
        now = time.perf_counter()
        record = {
            "ts": now,
            "core_id": core.core_id,
            "pattern": pattern,
            "future": future,
            "replay_labels": list(replay_labels[:8]),
            "replay_strength": _clamp(replay_strength, 0.0, 1.0),
            "stress_index": core.system_stress_index(),
        }
        with self._lock:
            self._dream_records.append(record)

    def publish_trauma_if_relevant(self, core: "AtheriaCore") -> None:
        stress = core.system_stress_index()
        if stress < 0.62:
            return
        now = time.perf_counter()
        record = {
            "ts": now,
            "core_id": core.core_id,
            "pattern": core.holographic_field.pattern.detach().clone(),
            "stress_index": stress,
            "temperature": float(core.phase_controller.system_temperature),
        }
        with self._lock:
            self._trauma_records.append(record)
            self.trauma_broadcast_events += 1

    def collect_collective_resonance(self, core: "AtheriaCore") -> Dict[str, Any]:
        dims = int(core.holographic_field.pattern.numel())
        zero = torch.zeros(dims, dtype=torch.float32)
        now = time.perf_counter()

        with self._lock:
            peers = self.registry.peers(core.core_id, running_only=True)
            sleeping_peer_ids = {
                peer.core_id
                for peer in peers
                if peer.rhythm.state is RhythmState.SLEEP and not peer.aion_meditation_mode
            }

            dream_candidates = [
                rec
                for rec in self._dream_records
                if rec["core_id"] in sleeping_peer_ids
                and (now - float(rec["ts"])) <= self.dream_ttl_seconds
            ]
            trauma_candidates = [
                rec
                for rec in self._trauma_records
                if rec["core_id"] != core.core_id and (now - float(rec["ts"])) <= self.trauma_ttl_seconds
            ]

        if not dream_candidates:
            return {
                "resonance": zero,
                "instinctive_noise": zero,
                "coherence": 0.0,
                "trauma_intensity": 0.0,
                "peer_count": 0,
            }

        weighted = torch.zeros(dims, dtype=torch.float32)
        total_weight = 1e-8
        unique_sources: Set[str] = set()
        for rec in dream_candidates:
            pattern = rec["pattern"]
            future = rec["future"]
            stress = _clamp(float(rec["stress_index"]), 0.0, 1.0)
            replay_strength = _clamp(float(rec["replay_strength"]), 0.0, 1.0)
            weight = 0.45 + 0.35 * replay_strength + 0.2 * stress
            p = pattern / (torch.norm(pattern, p=2) + 1e-8)
            f = future / (torch.norm(future, p=2) + 1e-8)
            blended = 0.62 * p + 0.38 * f
            weighted = weighted + blended * weight
            total_weight += weight
            unique_sources.add(str(rec["core_id"]))

        resonance = weighted / total_weight
        resonance = resonance / (torch.norm(resonance, p=2) + 1e-8)
        coherence = _clamp(float(torch.norm(resonance, p=2)), 0.0, 1.0)

        instinctive_noise = torch.zeros(dims, dtype=torch.float32)
        trauma_intensity = 0.0
        if trauma_candidates:
            trauma_weight_sum = 1e-8
            for rec in trauma_candidates:
                pattern = rec["pattern"]
                stress = _clamp(float(rec["stress_index"]), 0.0, 1.0)
                if stress <= 0.0:
                    continue
                noise_scale = 0.55 + 0.45 * stress
                pattern_norm = pattern / (torch.norm(pattern, p=2) + 1e-8)
                instinctive_noise = instinctive_noise + pattern_norm * noise_scale
                trauma_weight_sum += noise_scale
            instinctive_noise = instinctive_noise / trauma_weight_sum
            instinctive_noise = instinctive_noise / (torch.norm(instinctive_noise, p=2) + 1e-8)
            trauma_intensity = _clamp(
                sum(_clamp(float(rec["stress_index"]), 0.0, 1.0) for rec in trauma_candidates)
                / max(1, len(trauma_candidates)),
                0.0,
                1.0,
            )

        self.sync_events += 1
        return {
            "resonance": resonance,
            "instinctive_noise": instinctive_noise,
            "coherence": coherence,
            "trauma_intensity": trauma_intensity,
            "peer_count": len(unique_sources),
        }


GLOBAL_MORPHIC_NODE = GlobalMorphicNode(GLOBAL_CORE_REGISTRY)


class AtherCreditMarket:
    """
    Dynamic inter-core resource market.
    Hot/unstable cores can rent resources from cooler/stable cores in exchange for Ather-Credits.
    """

    def __init__(self, registry: CorePopulationRegistry) -> None:
        self.registry = registry
        self._lock = threading.RLock()
        self.transactions: Deque[Dict[str, Any]] = deque(maxlen=1024)
        self.last_price_per_unit = 0.0

    def _guardian_score(self, core: "AtheriaCore") -> float:
        asm = core.assembler
        coolness = 1.0 - _clamp(core.phase_controller.system_temperature / 100.0, 0.0, 1.0)
        abundance = math.tanh(max(0.0, asm.resource_pool) / 30.0)
        purpose = _clamp(core.transcendence.last_purpose_alignment, 0.0, 1.0)
        morphic = _clamp(core.holographic_field.last_morphic_resonance_index, 0.0, 1.0)
        survival_bonus = 0.08 if core.reproduction.last_artifact_profile == "survival" else 0.0
        return _clamp(0.35 * coolness + 0.3 * abundance + 0.2 * purpose + 0.15 * morphic + survival_bonus, 0.0, 1.0)

    def _need_score(self, core: "AtheriaCore") -> float:
        asm = core.assembler
        scarcity = _clamp(core.ecology.resource_scarcity, 0.0, 1.0)
        heat = _clamp((core.phase_controller.system_temperature - 52.0) / 52.0, 0.0, 1.0)
        local_entropy = sum(float(v) for v in core.phase_controller.local_entropy.values())
        entropy_load = _clamp(math.tanh(local_entropy / 60.0), 0.0, 1.0)
        reserve_pressure = _clamp((10.0 - asm.resource_pool) / 10.0, 0.0, 1.0)
        return _clamp(0.34 * scarcity + 0.28 * heat + 0.22 * entropy_load + 0.16 * reserve_pressure, 0.0, 1.0)

    def _select_lender(self, borrower: "AtheriaCore") -> Optional["AtheriaCore"]:
        candidates = []
        for peer in self.registry.peers(borrower.core_id, running_only=True):
            if peer.aion_meditation_mode:
                continue
            guardian = self._guardian_score(peer)
            asm = peer.assembler
            available = max(0.0, asm.resource_pool - (8.0 + guardian * 4.5))
            if available < 0.35:
                continue
            score = guardian * 0.7 + _clamp(available / 30.0, 0.0, 1.0) * 0.3
            candidates.append((score, peer))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def execute_rental(
        self,
        *,
        borrower: "AtheriaCore",
        lender: Optional["AtheriaCore"] = None,
        requested_units: Optional[float] = None,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        borrower_asm = borrower.assembler
        need = self._need_score(borrower)
        if not force and need < borrower_asm.market_need_threshold:
            return None

        lender_core = lender or self._select_lender(borrower)
        if lender_core is None or lender_core.core_id == borrower.core_id:
            return None

        lender_asm = lender_core.assembler
        guardian = self._guardian_score(lender_core)
        lender_asm.market_guardian_score = guardian
        reserve = 8.0 + guardian * 4.5
        available = max(0.0, lender_asm.resource_pool - reserve)
        if available < 0.25:
            return None

        target_units = requested_units if requested_units is not None else (1.0 + 4.2 * need)
        units = _clamp(target_units, 0.25, available)
        if units <= 0.0:
            return None

        scarcity = _clamp(borrower.ecology.resource_scarcity, 0.0, 1.0)
        price_per_unit = 1.1 + 1.5 * scarcity + 1.1 * guardian + 0.9 * max(0.0, need - 0.35)
        affordable_units = borrower_asm.credit_balance / max(1e-8, price_per_unit)
        if not force and affordable_units < 0.2:
            return None
        units = min(units, affordable_units)
        if units < 0.2:
            return None

        total_price = units * price_per_unit
        transfer_efficiency = _clamp(0.9 + 0.06 * guardian, 0.88, 0.98)
        received_units = units * transfer_efficiency

        lender_asm.resource_pool = max(0.0, lender_asm.resource_pool - units)
        borrower_asm.resource_pool = min(5000.0, borrower_asm.resource_pool + received_units)
        borrower_asm.credit_balance = max(-250.0, borrower_asm.credit_balance - total_price)
        lender_asm.credit_balance = min(5000.0, lender_asm.credit_balance + total_price)

        packet = lender_asm.export_efficiency_packet()
        packet_quality = borrower_asm.ingest_efficiency_packet(packet)

        borrower_asm.market_transactions += 1
        borrower_asm.market_borrow_events += 1
        borrower_asm.market_resources_in += received_units
        borrower_asm.market_last_partner = lender_core.core_id
        borrower_asm.market_last_price = price_per_unit
        borrower_asm.market_last_packet_quality = packet_quality

        lender_asm.market_transactions += 1
        lender_asm.market_lend_events += 1
        lender_asm.market_resources_out += units
        lender_asm.market_last_partner = borrower.core_id
        lender_asm.market_last_price = price_per_unit

        report = {
            "timestamp": round(time.time(), 6),
            "borrower": borrower.core_id,
            "lender": lender_core.core_id,
            "units_requested": round(float(target_units), 6),
            "units_transferred": round(float(received_units), 6),
            "units_from_lender": round(float(units), 6),
            "price_per_unit": round(float(price_per_unit), 6),
            "total_price": round(float(total_price), 6),
            "packet_quality": round(float(packet_quality), 6),
            "guardian_score": round(float(guardian), 6),
        }

        with self._lock:
            self.transactions.append(report)
            self.last_price_per_unit = float(price_per_unit)

        logger.info(
            "Ather-Credit Market | borrower=%s lender=%s units=%.3f price=%.3f quality=%.3f",
            borrower.core_id,
            lender_core.core_id,
            received_units,
            price_per_unit,
            packet_quality,
        )

        return report


GLOBAL_ATHER_CREDIT_MARKET = AtherCreditMarket(GLOBAL_CORE_REGISTRY)


class LLMSleepRewriter:
    """
    Sleep-phase neuro-symbolic rewrite catalyst.
    Uses a locally running LMStudio model to propose runtime-mechanism rewrites,
    validates proposals via AST safety gates, and only integrates beneficial patches.
    """

    FEATURE_KEYS = [
        "gradient",
        "resonance",
        "coherence",
        "entropy",
        "morphic",
        "purpose",
        "degree",
        "edge_efficiency",
    ]
    VALID_OPS = {"plus", "minus", "mul", "linear", "tanh", "sigmoid", "quadratic", "exp_decay"}
    _probe_cache_lock = threading.RLock()
    _probe_cache: Dict[str, Dict[str, float]] = {}

    def __init__(
        self,
        core: "AtheriaCore",
        *,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.core = core
        endpoint_raw = endpoint or os.getenv("ATHERIA_LMSTUDIO_ENDPOINT", "http://127.0.0.1:1234/v1")
        self.endpoint = endpoint_raw.rstrip("/")
        self.preferred_model = model or os.getenv("ATHERIA_LMSTUDIO_MODEL")
        self.api_key = os.getenv("ATHERIA_LMSTUDIO_API_KEY") or os.getenv("LMSTUDIO_API_KEY")

        self.request_timeout_max_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_REQUEST_TIMEOUT_MAX", "180.0")),
            6.0,
            600.0,
        )
        self.connect_timeout_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_CONNECT_TIMEOUT", "0.9")),
            0.2,
            15.0,
        )
        self.request_timeout_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_REQUEST_TIMEOUT", "6.5")),
            0.8,
            self.request_timeout_max_seconds,
        )
        self.alias_request_timeout_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_ALIAS_TIMEOUT", "2.2")),
            0.4,
            90.0,
        )
        self.rewrite_attempt_budget = int(
            _clamp(float(os.getenv("ATHERIA_LLM_REWRITE_ATTEMPTS", "2")), 1.0, 6.0)
        )
        self.retry_backoff_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_RETRY_BACKOFF_SECONDS", "1.2")),
            0.0,
            20.0,
        )
        self.retry_timeout_scale = _clamp(
            float(os.getenv("ATHERIA_LLM_RETRY_TIMEOUT_SCALE", "1.35")),
            1.0,
            3.0,
        )
        self.retry_compact_prompt = str(os.getenv("ATHERIA_LLM_RETRY_COMPACT_PROMPT", "1")).strip().lower() not in {
            "0",
            "false",
            "off",
        }
        self.min_attempt_interval_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_REWRITE_INTERVAL", "11.0")),
            0.5,
            180.0,
        )
        self.min_replay_strength = _clamp(
            float(os.getenv("ATHERIA_LLM_MIN_REPLAY_STRENGTH", "0.08")),
            0.0,
            1.0,
        )
        self.min_predicted_delta = _clamp(
            float(os.getenv("ATHERIA_LLM_MIN_PREDICTED_DELTA", "0.004")),
            -0.25,
            0.25,
        )
        self.max_runtime_mechanisms = int(_clamp(float(os.getenv("ATHERIA_LLM_MAX_MECHANISMS", "28")), 6.0, 96.0))
        self.max_program_terms = int(_clamp(float(os.getenv("ATHERIA_LLM_MAX_TERMS", "6")), 2.0, 16.0))
        self.alias_refresh_seconds = _clamp(
            float(os.getenv("ATHERIA_LLM_ALIAS_REFRESH_SECONDS", "45.0")),
            5.0,
            900.0,
        )

        mode = str(os.getenv("ATHERIA_LLM_SLEEP_REWRITER", "auto")).strip().lower()
        if mode in {"0", "false", "off", "disabled"}:
            self.enabled = False
            self._auto_mode = False
        elif mode in {"1", "true", "on", "enabled"}:
            self.enabled = True
            self._auto_mode = False
        else:
            # auto: keep feature active and probe lazily with cache/backoff.
            self.enabled = True
            self._auto_mode = True

        self.alias_requests_enabled = str(os.getenv("ATHERIA_LLM_ALIAS_SUGGEST", "1")).strip().lower() not in {
            "0",
            "false",
            "off",
        }

        self.attempts = 0
        self.accepts = 0
        self.rejects = 0
        self.errors = 0
        self.alias_updates = 0
        self.last_model_id: Optional[str] = None
        self.last_reason: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_program_signature: Optional[str] = None
        self.last_predicted_delta = 0.0
        self.last_attempt_perf = 0.0
        self._last_model_refresh_perf = 0.0
        self._cached_alias_map: Dict[str, list[str]] = {}
        self._last_alias_refresh_perf = 0.0
        self.trace_enabled = str(os.getenv("ATHERIA_LLM_TRACE", "1")).strip().lower() not in {
            "0",
            "false",
            "off",
        }
        trace_path_raw = str(os.getenv("ATHERIA_LLM_TRACE_PATH", "logs/llm_rewrite_trace.jsonl")).strip()
        self.trace_path = Path(trace_path_raw) if trace_path_raw else Path("logs/llm_rewrite_trace.jsonl")
        self.trace_events = 0
        self.last_trace_path: Optional[str] = str(self.trace_path)
        self.last_raw_chat_content: Optional[str] = None
        self._trace_lock = threading.RLock()

    def _quick_probe(self) -> bool:
        now = time.perf_counter()
        with self._probe_cache_lock:
            cached = self._probe_cache.get(self.endpoint)
            if cached and now <= float(cached.get("next_probe_perf", 0.0)):
                return bool(cached.get("available", 0.0))

        available = False
        try:
            payload = self._http_json("models", timeout=self.connect_timeout_seconds, payload=None)
            available = isinstance(payload, dict) and isinstance(payload.get("data"), list)
        except Exception:
            available = False

        with self._probe_cache_lock:
            self._probe_cache[self.endpoint] = {
                "available": 1.0 if available else 0.0,
                "next_probe_perf": now + (20.0 if available else 35.0),
            }
        return available

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _trace_json_safe(self, value: Any, *, max_chars: int = 14000) -> Any:
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        if isinstance(value, str):
            return value if len(value) <= max_chars else value[:max_chars]
        if isinstance(value, (list, dict)):
            try:
                encoded = json.dumps(value, ensure_ascii=False)
                if len(encoded) <= max_chars:
                    return value
                return {
                    "truncated": True,
                    "preview": encoded[:max_chars],
                    "source_len": len(encoded),
                }
            except Exception:
                pass
        fallback = str(value)
        if len(fallback) > max_chars:
            fallback = fallback[:max_chars]
        return fallback

    def _append_trace(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.trace_enabled:
            return
        try:
            if self.trace_path.is_absolute():
                out_path = self.trace_path
            else:
                out_path = Path.cwd() / self.trace_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "timestamp": round(time.time(), 6),
                "event": event_type,
                "core_id": self.core.core_id,
                "endpoint": self.endpoint,
                "model": self.last_model_id,
                "payload": self._trace_json_safe(payload),
            }
            with self._trace_lock:
                with out_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.trace_events += 1
            self.last_trace_path = str(out_path)
        except Exception:
            pass

    def _http_json(self, path: str, *, timeout: float, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.endpoint}/{path.lstrip('/')}"
        data: Optional[bytes] = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        method = "POST" if payload is not None else "GET"
        request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        if not body.strip():
            return {}
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return parsed
        return {}

    def _resolve_model(self) -> str:
        if self.preferred_model:
            self.last_model_id = self.preferred_model
            return self.preferred_model
        now = time.perf_counter()
        if self.last_model_id and (now - self._last_model_refresh_perf) <= 45.0:
            return self.last_model_id

        payload = self._http_json("models", timeout=self.connect_timeout_seconds, payload=None)
        models = payload.get("data", [])
        if not isinstance(models, list):
            raise RuntimeError("LMStudio /models response invalid.")
        candidates: list[str] = []
        for row in models:
            if isinstance(row, dict):
                model_id = row.get("id")
                if model_id:
                    candidates.append(str(model_id))
        if not candidates:
            raise RuntimeError("No loaded model available in LMStudio.")
        self.last_model_id = candidates[0]
        self._last_model_refresh_perf = now
        return self.last_model_id

    def _extract_json_object(self, text: str) -> Dict[str, Any]:
        raw = str(text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        raise ValueError("LLM response is not a valid JSON object.")

    def _chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.15,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        model = self._resolve_model()
        payload_base = {
            "model": model,
            "temperature": _clamp(temperature, 0.0, 1.0),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        payload_candidates = [
            {
                **payload_base,
                "response_format": {"type": "json_object"},
            },
            payload_base,
        ]
        last_exc: Optional[Exception] = None
        for idx, payload in enumerate(payload_candidates):
            try:
                response = self._http_json(
                    "chat/completions",
                    timeout=timeout or self.request_timeout_seconds,
                    payload=payload,
                )
                choices = response.get("choices", [])
                if not isinstance(choices, list) or not choices:
                    raise RuntimeError("LMStudio returned no choices.")
                choice = choices[0] if isinstance(choices[0], dict) else {}
                message = choice.get("message", {}) if isinstance(choice, dict) else {}
                content = message.get("content", "") if isinstance(message, dict) else ""
                self.last_raw_chat_content = str(content)
                return self._extract_json_object(self.last_raw_chat_content)
            except urllib.error.HTTPError as exc:
                last_exc = exc
                # Some LMStudio/model combinations reject response_format.
                if idx == 0 and exc.code in {400, 404, 415, 422}:
                    continue
                break
            except Exception as exc:
                last_exc = exc
                if idx == 0:
                    continue
                break
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("LMStudio chat request failed without explicit exception.")

    def _normalize_key(self, value: str) -> str:
        lowered = str(value or "").strip().lower()
        return (
            lowered.replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )

    def _heuristic_aliases(self, field_names: Iterable[str]) -> Dict[str, list[str]]:
        names = [str(name) for name in field_names if str(name).strip()]
        normalized = {self._normalize_key(name): name for name in names}
        alias_map = {
            "question": ["question", "frage", "prompt", "query", "input", "ask", "q", "questiontext"],
            "category": ["category", "kategorie", "topic", "label", "class", "domain", "group", "tag"],
            "answer": ["answer", "antwort", "response", "output", "result", "a", "answervalue"],
        }
        out: Dict[str, list[str]] = {"question": [], "category": [], "answer": []}
        for canonical, patterns in alias_map.items():
            seen: Set[str] = set()
            for pattern in patterns:
                p = self._normalize_key(pattern)
                for n_key, original in normalized.items():
                    if n_key == p or n_key.startswith(p) or p in n_key:
                        if original not in seen:
                            out[canonical].append(original)
                            seen.add(original)
            for default in patterns[:2]:
                if default not in seen:
                    out[canonical].append(default)
                    seen.add(default)
        return out

    def _sanitize_alias_map(self, alias_map: Any, headers: Iterable[str]) -> Dict[str, list[str]]:
        allowed = {str(h) for h in headers if str(h).strip()}
        allowed_lower = {token.lower() for token in allowed}
        out = self._heuristic_aliases(headers)
        if not isinstance(alias_map, dict):
            return out
        for canonical in ("question", "category", "answer"):
            candidates = alias_map.get(canonical)
            if not isinstance(candidates, list):
                continue
            merged: list[str] = []
            seen: Set[str] = set()
            for value in candidates:
                candidate = str(value).strip()
                if not candidate:
                    continue
                if allowed and candidate not in allowed and candidate.lower() not in allowed_lower:
                    continue
                if candidate in seen:
                    continue
                merged.append(candidate)
                seen.add(candidate)
            # Keep deterministic fallback aliases at the end.
            for fallback in out.get(canonical, []):
                if fallback not in seen:
                    merged.append(fallback)
                    seen.add(fallback)
            out[canonical] = merged
        return out

    def resolve_field_aliases(self, field_names: Iterable[str], *, source_kind: str = "csv") -> Dict[str, list[str]]:
        headers = [str(name) for name in field_names if str(name).strip()]
        if not headers:
            return self._heuristic_aliases([])

        heuristics = self._heuristic_aliases(headers)
        if not self.enabled or not self.alias_requests_enabled:
            return heuristics
        if self._auto_mode and not self._quick_probe():
            return heuristics

        now = time.perf_counter()
        if self._cached_alias_map and (now - self._last_alias_refresh_perf) <= self.alias_refresh_seconds:
            merged = dict(heuristics)
            for key in ("question", "category", "answer"):
                extra = self._cached_alias_map.get(key, [])
                if not isinstance(extra, list):
                    continue
                merged[key] = list(dict.fromkeys([*extra, *merged[key]]))
            return merged

        system_prompt = (
            "You map unknown dataset field names to QA schema. "
            "Return strict JSON only with object key `aliases` and nested keys "
            "`question`, `category`, `answer`, each containing a list of input header names."
        )
        user_prompt = (
            f"Source kind: {source_kind}\n"
            f"Input headers: {json.dumps(headers, ensure_ascii=False)}\n"
            "Rules: choose only from given headers, keep most likely aliases first, max 4 per key."
        )
        try:
            response = self._chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                timeout=self.alias_request_timeout_seconds,
            )
            aliases_raw = response.get("aliases", response)
            sanitized = self._sanitize_alias_map(aliases_raw, headers)
            self._cached_alias_map = sanitized
            self._last_alias_refresh_perf = now
            self.alias_updates += 1
            self._append_trace(
                "alias_resolve",
                {
                    "status": "ok",
                    "source_kind": source_kind,
                    "headers": headers[:24],
                    "raw_response": response,
                    "sanitized_aliases": sanitized,
                },
            )
            return sanitized
        except Exception as exc:
            self.last_error = f"alias_resolve_error: {exc}"
            self.errors += 1
            self._append_trace(
                "alias_resolve",
                {
                    "status": "error",
                    "source_kind": source_kind,
                    "headers": headers[:24],
                    "error": self.last_error,
                    "raw_response_excerpt": self.last_raw_chat_content,
                },
            )
            return heuristics

    def _normalize_program_terms(self, raw_program: Any) -> list[Any]:
        if isinstance(raw_program, list):
            return list(raw_program)
        if isinstance(raw_program, dict):
            # Many small local models return a single term object instead of a list.
            if any(key in raw_program for key in ("left", "op", "right", "coefficient", "power")):
                return [raw_program]
            for key in ("terms", "program", "items"):
                nested = raw_program.get(key)
                if isinstance(nested, list):
                    return list(nested)
                if isinstance(nested, dict):
                    return [nested]
            return []
        if isinstance(raw_program, str):
            text = raw_program.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                return self._normalize_program_terms(parsed)
            except Exception:
                return []
        return []

    def _sanitize_program(self, raw_program: Any) -> list[Dict[str, Any]]:
        terms = self._normalize_program_terms(raw_program)
        if not terms:
            return []
        out: list[Dict[str, Any]] = []
        for term in terms:
            if not isinstance(term, dict):
                continue
            left = str(term.get("left", "gradient"))
            right = str(term.get("right", "resonance"))
            op = str(term.get("op", "linear"))
            if left not in self.FEATURE_KEYS:
                left = "gradient"
            if right not in self.FEATURE_KEYS:
                right = "resonance"
            if op not in self.VALID_OPS:
                op = "linear"
            out.append(
                {
                    "left": left,
                    "op": op,
                    "right": right,
                    "coefficient": _clamp(self._safe_float(term.get("coefficient", 0.0)), -1.4, 1.4),
                    "power": _clamp(self._safe_float(term.get("power", 1.0), 1.0), 1.0, 3.0),
                }
            )
            if len(out) >= self.max_program_terms:
                break
        return out

    def _fallback_program_from_mechanism(self, raw: Dict[str, Any]) -> list[Dict[str, Any]]:
        gradient_gain = _clamp(self._safe_float(raw.get("gradient_gain", 0.1), 0.1), -1.0, 1.0)
        resonance_gain = _clamp(self._safe_float(raw.get("resonance_gain", 0.1), 0.1), -1.0, 1.0)
        coherence_gain = _clamp(self._safe_float(raw.get("coherence_gain", 0.08), 0.08), -1.0, 1.0)
        entropy_damp = _clamp(self._safe_float(raw.get("entropy_damp", 0.08), 0.08), 0.0, 1.2)

        coeff = (float(gradient_gain) + float(resonance_gain) + float(coherence_gain)) / 3.0
        coeff = _clamp(coeff, -0.6, 0.6)
        if abs(coeff) < 0.02:
            coeff = 0.08 if coeff >= 0.0 else -0.08
        power = _clamp(1.0 + (float(entropy_damp) * 0.6), 1.0, 2.0)
        return [
            {
                "left": "gradient",
                "op": "tanh",
                "right": "resonance",
                "coefficient": float(coeff),
                "power": float(power),
            }
        ]

    def _sanitize_mechanism(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        phase_bias_defaults = {
            "phase_bias_solid": 1.0,
            "phase_bias_liquid": 1.0,
            "phase_bias_plasma": 1.0,
        }
        sanitized_program = self._sanitize_program(raw.get("program", []))
        fallback_used = False
        if not sanitized_program:
            sanitized_program = self._fallback_program_from_mechanism(raw)
            fallback_used = True
        cleaned = {
            "gradient_gain": _clamp(self._safe_float(raw.get("gradient_gain", 0.1), 0.1), -0.8, 1.6),
            "resonance_gain": _clamp(self._safe_float(raw.get("resonance_gain", 0.08), 0.08), -0.8, 1.6),
            "coherence_gain": _clamp(self._safe_float(raw.get("coherence_gain", 0.06), 0.06), -0.8, 1.6),
            "entropy_damp": _clamp(self._safe_float(raw.get("entropy_damp", 0.08), 0.08), 0.0, 1.2),
            "stochasticity": _clamp(self._safe_float(raw.get("stochasticity", 0.0), 0.0), 0.0, 0.2),
            "program": sanitized_program,
            "program_fallback_used": fallback_used,
        }
        for key, default in phase_bias_defaults.items():
            cleaned[key] = _clamp(self._safe_float(raw.get(key, default), default), 0.65, 1.45)
        if cleaned["program"]:
            cleaned["program_signature"] = self.core.evolution._program_signature(cleaned["program"])
        else:
            cleaned["program_signature"] = ""
        return cleaned

    def _program_expression(self, program: list[Dict[str, Any]]) -> str:
        chunks: list[str] = []
        for term in program:
            left = str(term.get("left", "gradient"))
            right = str(term.get("right", "resonance"))
            op = str(term.get("op", "linear"))
            coeff = float(term.get("coefficient", 0.0))
            power = float(term.get("power", 1.0))
            if op == "plus":
                body = f"({left}+{right})"
            elif op == "minus":
                body = f"({left}-{right})"
            elif op == "mul":
                body = f"({left}*{right})"
            elif op == "tanh":
                body = f"tanh({left}*{power:.6f})"
            elif op == "sigmoid":
                body = f"sigmoid({left}*{power:.6f})"
            elif op == "quadratic":
                body = f"copysign(abs({left})**{min(2.8, power):.6f},{left})"
            elif op == "exp_decay":
                body = f"exp(-abs({left})*{power:.6f})"
            else:
                body = f"({left})"
            chunks.append(f"({coeff:.6f}*{body})")
        if not chunks:
            return "0.0"
        return " + ".join(chunks)

    def _validate_expression_ast(self, expression: str) -> bool:
        allowed_names = set(self.FEATURE_KEYS) | {"tanh", "sigmoid", "exp", "abs", "copysign"}
        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Pow,
            ast.USub,
            ast.UAdd,
            ast.Call,
            ast.Name,
            ast.Load,
            ast.Constant,
        )
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                return False
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name):
                    return False
                if node.func.id not in {"tanh", "sigmoid", "exp", "abs", "copysign"}:
                    return False
            if isinstance(node, ast.Name) and node.id not in allowed_names:
                return False
        return True

    def _validate_program_ast(self, program: list[Dict[str, Any]], python_expression: Optional[str]) -> bool:
        program_expression = self._program_expression(program)
        if not self._validate_expression_ast(program_expression):
            return False
        if python_expression:
            return self._validate_expression_ast(str(python_expression))
        return True

    def _sanitize_python_expression(self, python_expression: Any) -> Tuple[Optional[str], bool]:
        if not isinstance(python_expression, str):
            return None, False
        normalized = python_expression.strip()
        if not normalized:
            return None, False
        lowered = normalized.lower()
        if lowered in {"optional_safe_expr", "none", "null", "n/a", "na"}:
            return None, False
        dangerous_tokens = (
            "__import__",
            "import ",
            "eval(",
            "exec(",
            "open(",
            "subprocess",
            "os.",
            "system(",
        )
        if any(token in lowered for token in dangerous_tokens):
            return None, True
        try:
            ast.parse(normalized, mode="eval")
        except Exception:
            return None, False
        if not self._validate_expression_ast(normalized):
            return None, False
        return normalized, False

    def _sleep_context(self, *, replay_labels: list[str], replay_strength: float) -> Dict[str, Any]:
        low_integrity = sorted(
            (
                {
                    "label": cell.label,
                    "integrity": round(float(cell.integrity_rate), 6),
                    "errors": int(cell.error_counter),
                }
                for cell in self.core.cells.values()
            ),
            key=lambda row: (row["integrity"], -row["errors"]),
        )
        low_integrity = low_integrity[:4]
        try:
            src_apply = inspect.getsource(EvolutionEngine._apply_program)
        except Exception:
            src_apply = "source_unavailable"
        try:
            src_invent = inspect.getsource(EvolutionEngine._invent_runtime_mechanism)
        except Exception:
            src_invent = "source_unavailable"
        return {
            "core_id": self.core.core_id,
            "rhythm_state": self.core.rhythm.state.value,
            "system_temperature": round(float(self.core.phase_controller.system_temperature), 6),
            "purpose_alignment": round(float(self.core.transcendence.last_purpose_alignment), 6),
            "morphic_resonance_index": round(float(self.core.holographic_field.last_morphic_resonance_index), 6),
            "stress_index": round(float(self.core.system_stress_index()), 6),
            "selection_pressure": round(float(self.core.ecology.selection_pressure), 6),
            "resource_scarcity": round(float(self.core.ecology.resource_scarcity), 6),
            "replay_strength": round(float(replay_strength), 6),
            "replay_labels": list(replay_labels[:8]),
            "mechanism_count": len(self.core.evolution.runtime_mechanisms),
            "low_integrity_cells": low_integrity,
            "evolution_apply_program_source": src_apply[:1400],
            "evolution_invent_source": src_invent[:1200],
        }

    def _sleep_context_compact(self, *, replay_labels: list[str], replay_strength: float) -> Dict[str, Any]:
        context = self._sleep_context(replay_labels=replay_labels, replay_strength=replay_strength)
        context.pop("evolution_apply_program_source", None)
        context.pop("evolution_invent_source", None)
        context["compact_prompt_mode"] = True
        return context

    def _build_rewrite_prompts(self, *, context: Dict[str, Any], compact: bool) -> Tuple[str, str]:
        if compact:
            system_prompt = (
                "You optimize adaptive runtime mechanisms under strict safety constraints. "
                "Return strict JSON only."
            )
            user_prompt = (
                "Context:\n"
                f"{json.dumps(context, ensure_ascii=False)}\n\n"
                "Return JSON object:\n"
                "{"
                "\"decision\":\"accept|reject\","
                "\"confidence\":0.0,"
                "\"rationale\":\"short\","
                "\"mechanism\":{"
                "\"gradient_gain\":0.1,"
                "\"resonance_gain\":0.1,"
                "\"coherence_gain\":0.1,"
                "\"entropy_damp\":0.1,"
                "\"phase_bias_solid\":1.0,"
                "\"phase_bias_liquid\":1.0,"
                "\"phase_bias_plasma\":1.0,"
                "\"stochasticity\":0.01,"
                "\"program\":[{\"left\":\"gradient\",\"op\":\"tanh\",\"right\":\"resonance\",\"coefficient\":0.1,\"power\":1.2}]"
                "},"
                "\"python_expression\":\"\","
                "\"aliases\":{\"question\":[],\"category\":[],\"answer\":[]}"
                "}\n"
                "Allowed features: "
                f"{self.FEATURE_KEYS}. "
                "Allowed ops: plus, minus, mul, linear, tanh, sigmoid, quadratic, exp_decay."
            )
            return system_prompt, user_prompt

        system_prompt = (
            "You are an optimization compiler for a safety-critical adaptive runtime. "
            "Return strict JSON only. Propose one runtime mechanism patch if useful."
        )
        user_prompt = (
            "Context:\n"
            f"{json.dumps(context, ensure_ascii=False)}\n\n"
            "Return JSON format:\n"
            "{"
            "\"decision\":\"accept|reject\","
            "\"confidence\":0.0,"
            "\"rationale\":\"...\","
            "\"mechanism\":{"
            "\"gradient_gain\":0.1,"
            "\"resonance_gain\":0.1,"
            "\"coherence_gain\":0.1,"
            "\"entropy_damp\":0.1,"
            "\"phase_bias_solid\":1.0,"
            "\"phase_bias_liquid\":1.0,"
            "\"phase_bias_plasma\":1.0,"
            "\"stochasticity\":0.01,"
            "\"program\":[{\"left\":\"gradient\",\"op\":\"tanh\",\"right\":\"resonance\",\"coefficient\":0.1,\"power\":1.2}]"
            "},"
            "\"python_expression\":\"\","
            "\"aliases\":{\"question\":[],\"category\":[],\"answer\":[]}"
            "}\n"
            "Use only valid features: "
            f"{self.FEATURE_KEYS}. "
            "Use only ops: plus, minus, mul, linear, tanh, sigmoid, quadratic, exp_decay."
        )
        return system_prompt, user_prompt

    def should_attempt(self, *, replay_strength: float) -> bool:
        if not self.enabled:
            return False
        if self._auto_mode and not self._quick_probe():
            return False
        if self.core.aion_meditation_mode:
            return False
        if len(self.core.evolution.runtime_mechanisms) >= self.max_runtime_mechanisms:
            return False
        now = time.perf_counter()
        if (now - self.last_attempt_perf) < self.min_attempt_interval_seconds:
            return False
        stress = self.core.system_stress_index()
        if replay_strength < self.min_replay_strength and stress < 0.52:
            return False
        return True

    def _ensure_capacity(self) -> None:
        mechanisms = self.core.evolution.runtime_mechanisms
        while len(mechanisms) >= self.max_runtime_mechanisms:
            keys = sorted(mechanisms.keys())
            if not keys:
                break
            victim = keys[0]
            mechanisms.pop(victim, None)

    async def try_sleep_rewrite(self, *, replay_labels: list[str], replay_strength: float) -> bool:
        if not self.should_attempt(replay_strength=replay_strength):
            return False

        self.last_attempt_perf = time.perf_counter()
        self.attempts += 1
        self.last_error = None
        self.last_reason = None
        trace_payload: Dict[str, Any] = {
            "status": "in_progress",
            "attempt": self.attempts,
            "replay_strength": round(float(replay_strength), 6),
            "replay_labels": list(replay_labels[:8]),
            "attempt_budget": int(self.rewrite_attempt_budget),
        }
        response: Optional[Dict[str, Any]] = None
        last_exc: Optional[Exception] = None
        for retry_idx in range(self.rewrite_attempt_budget):
            compact_mode = bool(retry_idx > 0 and self.retry_compact_prompt)
            timeout_s = min(
                self.request_timeout_max_seconds,
                self.request_timeout_seconds * (self.retry_timeout_scale ** retry_idx),
            )
            context = (
                self._sleep_context_compact(replay_labels=replay_labels, replay_strength=replay_strength)
                if compact_mode
                else self._sleep_context(replay_labels=replay_labels, replay_strength=replay_strength)
            )
            system_prompt, user_prompt = self._build_rewrite_prompts(context=context, compact=compact_mode)
            try:
                response = await asyncio.to_thread(
                    self._chat_json,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    timeout=timeout_s,
                )
                trace_payload.update(
                    {
                        "retry_index": retry_idx,
                        "used_compact_prompt": compact_mode,
                        "request_timeout_seconds": round(float(timeout_s), 4),
                    }
                )
                break
            except Exception as exc:
                last_exc = exc
                if retry_idx < (self.rewrite_attempt_budget - 1) and self.retry_backoff_seconds > 0.0:
                    await asyncio.sleep(self.retry_backoff_seconds * float(retry_idx + 1))

        if response is None:
            self.errors += 1
            self.last_error = f"rewrite_request_error: {last_exc}"
            trace_payload.update(
                {
                    "status": "error",
                    "error": self.last_error,
                    "raw_response_excerpt": self.last_raw_chat_content,
                    "retry_count": int(self.rewrite_attempt_budget),
                }
            )
            self._append_trace("rewrite_attempt", trace_payload)
            return False

        decision = str(response.get("decision", "accept")).strip().lower()
        self.last_reason = str(response.get("rationale") or response.get("reason") or "").strip()[:280] or None
        trace_payload.update(
            {
                "raw_response": response,
                "decision": decision,
                "rationale": self.last_reason,
            }
        )

        if decision not in {"accept", "yes", "apply", "propose"}:
            self.rejects += 1
            trace_payload.update({"status": "rejected", "reject_stage": "decision"})
            self._append_trace("rewrite_attempt", trace_payload)
            return False

        mechanism = self._sanitize_mechanism(response.get("mechanism"))
        if not mechanism.get("program"):
            self.rejects += 1
            trace_payload.update(
                {
                    "status": "rejected",
                    "reject_stage": "empty_program",
                    "sanitized_mechanism": mechanism,
                }
            )
            self._append_trace("rewrite_attempt", trace_payload)
            return False

        python_expression, python_expression_dangerous = self._sanitize_python_expression(response.get("python_expression"))
        if python_expression_dangerous:
            self.rejects += 1
            self.last_error = "rewrite_rejected_unsafe_python_expression"
            trace_payload.update(
                {
                    "status": "rejected",
                    "reject_stage": "python_expression_security",
                    "error": self.last_error,
                    "sanitized_mechanism": mechanism,
                }
            )
            self._append_trace("rewrite_attempt", trace_payload)
            return False
        ast_valid = self._validate_program_ast(
            mechanism["program"],
            python_expression=python_expression,
        )
        trace_payload["ast_valid"] = bool(ast_valid)
        if not ast_valid:
            self.rejects += 1
            self.last_error = "rewrite_rejected_invalid_ast"
            trace_payload.update(
                {
                    "status": "rejected",
                    "reject_stage": "ast_validation",
                    "error": self.last_error,
                    "sanitized_mechanism": mechanism,
                }
            )
            self._append_trace("rewrite_attempt", trace_payload)
            return False

        predicted_delta = float(self.core.symbiosis._predict_purpose_delta(mechanism))
        self.last_predicted_delta = predicted_delta
        trace_payload["predicted_delta"] = round(predicted_delta, 6)
        if predicted_delta < self.min_predicted_delta:
            self.rejects += 1
            trace_payload.update(
                {
                    "status": "rejected",
                    "reject_stage": "predicted_delta",
                    "min_predicted_delta": round(float(self.min_predicted_delta), 6),
                    "sanitized_mechanism": mechanism,
                }
            )
            self._append_trace("rewrite_attempt", trace_payload)
            return False

        self._ensure_capacity()
        mech_name = self.core.evolution._new_mechanism_name()
        mechanism["llm_rewrite"] = True
        mechanism["source_core_id"] = self.core.core_id
        mechanism["llm_model"] = self.last_model_id
        mechanism["llm_confidence"] = _clamp(self._safe_float(response.get("confidence", 0.5), 0.5), 0.0, 1.0)
        mechanism["llm_predicted_delta"] = predicted_delta
        mechanism["llm_reason"] = self.last_reason or ""
        mechanism["ingested_at"] = round(time.time(), 6)
        mechanism["program_signature"] = self.core.evolution._program_signature(mechanism["program"])

        self.core.evolution.runtime_mechanisms[mech_name] = mechanism
        self.core.evolution.evolution_events += 1
        self.core.evolution.last_innovation_label = mech_name
        self.core.evolution.last_program_signature = str(mechanism.get("program_signature") or "")
        self.last_program_signature = str(mechanism.get("program_signature") or "")
        self.accepts += 1
        trace_payload.update(
            {
                "status": "accepted",
                "mechanism_name": mech_name,
                "program_signature": self.last_program_signature,
                "sanitized_mechanism": mechanism,
            }
        )
        self._append_trace("rewrite_attempt", trace_payload)

        logger.info(
            "LLM Sleep Rewrite | core=%s mechanism=%s model=%s predicted_delta=%.4f",
            self.core.core_id,
            mech_name,
            self.last_model_id,
            predicted_delta,
        )
        return True


def _fold_vector_from_text(text: str, dims: int = 12) -> torch.Tensor:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    data = [digest[i % len(digest)] / 255.0 for i in range(dims)]
    vec = torch.tensor(data, dtype=torch.float32)
    return vec / (torch.norm(vec, p=2) + 1e-8)


def _project_to_poincare_ball(vec: torch.Tensor, max_norm: float = 0.999) -> torch.Tensor:
    v = vec.detach().float().flatten()
    norm = float(torch.norm(v, p=2))
    if norm >= max_norm:
        v = v * (max_norm / (norm + 1e-8))
    return v


def _poincare_coord_from_text(text: str, dims: int = POINCARE_DIMS) -> torch.Tensor:
    base = _fold_vector_from_text(text, dims=dims)
    centered = base - torch.mean(base)
    centered = centered / (torch.norm(centered, p=2) + 1e-8)
    return _project_to_poincare_ball(centered * 0.72)


def poincare_distance(u: torch.Tensor, v: torch.Tensor) -> float:
    """
    Geodesic distance in the Poincare ball.
    """
    uu = _project_to_poincare_ball(u)
    vv = _project_to_poincare_ball(v)
    du = float(torch.sum(uu * uu))
    dv = float(torch.sum(vv * vv))
    diff = uu - vv
    d2 = float(torch.sum(diff * diff))
    denom = max(1e-8, (1.0 - du) * (1.0 - dv))
    arg = 1.0 + (2.0 * d2 / denom)
    if arg < 1.0:
        arg = 1.0
    return float(math.acosh(arg))


class AggregateState(str, Enum):
    SOLID = "solid"
    LIQUID = "liquid"
    PLASMA = "plasma"

    @property
    def dashboard_name(self) -> str:
        return {
            AggregateState.SOLID: "Eis",
            AggregateState.LIQUID: "Wasser",
            AggregateState.PLASMA: "Plasma",
        }[self]


class RhythmState(str, Enum):
    WAKE = "wake"
    SLEEP = "sleep"


class AtheriaPhase:
    """Decorator that swaps function complexity by current phase."""

    def __init__(
        self,
        solid_impl: Optional[str] = None,
        liquid_impl: Optional[str] = None,
        plasma_impl: Optional[str] = None,
    ) -> None:
        self._override = {
            AggregateState.SOLID: solid_impl,
            AggregateState.LIQUID: liquid_impl,
            AggregateState.PLASMA: plasma_impl,
        }

    def _resolve_impl(self, instance: object, fn: Callable) -> Callable:
        phase = instance.phase_controller.current_state
        name = self._override.get(phase) or f"{fn.__name__}_{phase.value}"
        override = getattr(instance, name, None)
        if callable(override):
            return override
        return fn.__get__(instance, type(instance))

    def __call__(self, fn: Callable) -> Callable:
        if asyncio.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(instance, *args, **kwargs):
                impl = self._resolve_impl(instance, fn)
                out = impl(*args, **kwargs)
                if asyncio.iscoroutine(out):
                    return await out
                return out

            return async_wrapper

        @wraps(fn)
        def wrapper(instance, *args, **kwargs):
            impl = self._resolve_impl(instance, fn)
            return impl(*args, **kwargs)

        return wrapper


@dataclass
class AtherConnection:
    target: "AtherCell"
    weight: float = field(default_factory=lambda: random.uniform(0.15, 0.9))
    usage_count: int = 0
    success_count: int = 0
    frozen: bool = False
    activation_energy: float = field(default_factory=lambda: random.uniform(0.8, 1.3))
    catalytic_flux: float = 0.0
    protease_marks: int = 0
    compiled_kernel: Optional[str] = None
    compute_savings: float = 0.0

    @property
    def efficiency(self) -> float:
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count


ActivationObserver = Callable[[float, "AtherCell", Optional["AtherCell"], bool], None]


@dataclass
class AtherCell:
    label: str
    category: str = ""
    archetype: str = "baseline"
    archetype_traits: Dict[str, float] = field(default_factory=dict)
    semipermeability: float = 0.7
    activation: torch.Tensor = field(default_factory=lambda: torch.tensor(0.0, dtype=torch.float32))
    activation_history: Deque[float] = field(default_factory=lambda: deque(maxlen=128))
    connections: Dict[str, AtherConnection] = field(default_factory=dict)
    integrity_rate: float = 1.0
    is_necrotic: bool = False
    error_counter: int = 0
    silent_epochs: int = 0
    fold_signature: torch.Tensor = field(default_factory=lambda: torch.zeros(12, dtype=torch.float32))
    poincare_coord: torch.Tensor = field(default_factory=lambda: torch.zeros(POINCARE_DIMS, dtype=torch.float32))
    protein_state: torch.Tensor = field(
        default_factory=lambda: torch.tensor([0.70710677, 0.70710677], dtype=torch.float32)
    )
    is_superposed: bool = False
    enzyme_stability: float = 0.9
    _observers: list[ActivationObserver] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.semipermeability = max(0.0, min(1.0, float(self.semipermeability)))
        if not self.category:
            self.category = self.label
        if not self.archetype:
            self.archetype = "baseline"
        self.archetype_traits = {k: float(v) for k, v in self.archetype_traits.items()}
        self.fold_signature = _fold_vector_from_text(f"{self.label}|{self.category}", dims=12)
        self.poincare_coord = _poincare_coord_from_text(f"{self.label}|{self.category}", dims=POINCARE_DIMS)
        self.protein_state = self.protein_state / (torch.norm(self.protein_state, p=2) + 1e-8)

    @property
    def activation_value(self) -> float:
        return float(self.activation.item())

    @property
    def osmotic_pressure(self) -> float:
        return self.activation_value + float(sum(self.activation_history))

    @property
    def coherence(self) -> float:
        amp_balance = 1.0 - abs(float(self.protein_state[0]) - float(self.protein_state[1]))
        return max(0.0, min(1.0, 0.5 * amp_balance + 0.5 * self.enzyme_stability))

    def watch(self, callback: ActivationObserver) -> None:
        self._observers.append(callback)

    def set_activation(
        self,
        value: float,
        source: Optional["AtherCell"] = None,
        entangled: bool = False,
    ) -> None:
        safe = max(0.0, min(1.0, float(value)))
        self.activation = torch.tensor(safe, dtype=torch.float32)
        self.activation_history.append(safe)

        if safe > 0.005:
            self.silent_epochs = 0
            self.integrity_rate = min(1.0, self.integrity_rate + 0.008)
        else:
            self.silent_epochs += 1
            self.integrity_rate = max(0.0, self.integrity_rate - 0.004)

        for callback in tuple(self._observers):
            callback(safe, self, source, entangled)

    def refold(self) -> None:
        """
        DNA-origami-like refolding: the signature shifts with lived activation history.
        """
        if not self.activation_history:
            return
        hist = torch.tensor(list(self.activation_history)[-12:], dtype=torch.float32)
        if hist.numel() < 12:
            hist = torch.nn.functional.pad(hist, (0, 12 - hist.numel()))
        hist = hist / (torch.norm(hist, p=2) + 1e-8)
        self.fold_signature = (0.82 * self.fold_signature + 0.18 * hist)
        self.fold_signature = self.fold_signature / (torch.norm(self.fold_signature, p=2) + 1e-8)

        # Hyperbolic semantic drift update.
        fold_slice = self.fold_signature[:POINCARE_DIMS]
        fold_slice = fold_slice - torch.mean(fold_slice)
        fold_slice = fold_slice / (torch.norm(fold_slice, p=2) + 1e-8)
        blended = 0.9 * self.poincare_coord + 0.1 * (fold_slice * 0.74)
        self.poincare_coord = _project_to_poincare_ball(blended)

    def set_superposition(self, alpha: float = 0.70710677, beta: float = 0.70710677, enzyme: float = 0.92) -> None:
        state = torch.tensor([float(alpha), float(beta)], dtype=torch.float32)
        state = state / (torch.norm(state, p=2) + 1e-8)
        self.protein_state = state
        self.is_superposed = True
        self.enzyme_stability = max(0.0, min(1.0, float(enzyme)))

    def chemical_measurement(self, probe: float = 0.5) -> float:
        """
        Protein-superposition collapse on demand (query-time only).
        """
        if not self.is_superposed:
            return self.activation_value

        p1 = float(self.protein_state[1] ** 2)
        weighted_p1 = max(0.0, min(1.0, p1 * self.enzyme_stability + probe * (1.0 - self.enzyme_stability)))
        collapsed = 1.0 if random.random() < weighted_p1 else 0.0
        self.is_superposed = False
        self.protein_state = torch.tensor([1.0 - collapsed, collapsed], dtype=torch.float32)
        self.set_activation((0.2 * self.activation_value) + (0.8 * collapsed))
        return self.activation_value

    def bump_activation(
        self,
        delta: float,
        source: Optional["AtherCell"] = None,
        entangled: bool = False,
    ) -> None:
        self.set_activation(self.activation_value + delta, source=source, entangled=entangled)

    def apply_archetype(self, archetype: str, traits: Optional[Dict[str, float]] = None) -> None:
        self.archetype = archetype or "baseline"
        if traits:
            self.archetype_traits = {k: float(v) for k, v in traits.items()}
            permeability_shift = self.archetype_traits.get("semipermeability_shift", 0.0)
            self.semipermeability = max(0.1, min(0.99, self.semipermeability + permeability_shift))
            enzyme_boost = self.archetype_traits.get("enzyme_stability_boost", 0.0)
            self.enzyme_stability = max(0.0, min(1.0, self.enzyme_stability + enzyme_boost))

    def stochastic_resonance(self, noise: float) -> float:
        """
        Controlled stochastic resonance for intuition spikes in high-entropy phases.
        """
        if abs(noise) < 1e-6:
            return self.activation_value
        self.bump_activation(noise, entangled=True)
        if noise > 0.0:
            self.integrity_rate = min(1.0, self.integrity_rate + min(0.01, noise * 0.08))
        self.refold()
        return self.activation_value

    def add_connection(self, target: "AtherCell", weight: Optional[float] = None) -> None:
        if target.label == self.label:
            return
        w = random.uniform(0.1, 0.9) if weight is None else float(weight)
        self.connections[target.label] = AtherConnection(target=target, weight=max(0.01, min(1.5, w)))

    def remove_connection(self, target_label: str) -> None:
        self.connections.pop(target_label, None)

    def record_error(self) -> None:
        self.error_counter += 1
        self.integrity_rate = max(0.0, self.integrity_rate - 0.2)

    def blueprint(self) -> Tuple[float, Dict[str, float]]:
        return self.semipermeability, {label: conn.weight for label, conn in self.connections.items()}

    async def diffuse_process(self, core: "AtheriaCore") -> int:
        if self.is_necrotic:
            return 0

        flows = 0
        for conn in tuple(self.connections.values()):
            target = conn.target
            if target.is_necrotic:
                continue
            if core.cognition.epigenetic_registry.is_silenced(self.label, target.label):
                continue

            gradient = self.osmotic_pressure - target.osmotic_pressure
            if gradient <= 0:
                continue

            fold_gain = core.entropic_folding.transfer_factor(self, target)
            energy_factor = 1.0 / max(0.05, conn.activation_energy)
            kernel_factor = 1.18 if conn.compiled_kernel else 1.0
            rhythm_gain = core.rhythm.diffusion_gain if hasattr(core, "rhythm") else 1.0
            protected_edge = core.topological_logic.is_edge_protected(self.label, target.label)
            if protected_edge:
                transfer = core.topological_logic.deterministic_transfer(gradient, self.semipermeability, conn)
            else:
                conceptual_gain = core.cognition.conceptual_proximity_gain(self, target)
                archetype_flux = self.archetype_traits.get("flux_bias", 1.0)
                archetype_target = target.archetype_traits.get("flux_bias", 1.0)
                archetype_gain = max(0.72, min(1.45, 0.5 * (archetype_flux + archetype_target)))
                transfer = (
                    core.transfer_kernel(gradient)
                    * self.semipermeability
                    * conn.weight
                    * fold_gain
                    * energy_factor
                    * kernel_factor
                    * conceptual_gain
                    * archetype_gain
                )
                if hasattr(core, "evolution"):
                    transfer = transfer * core.evolution.transfer_gain(self, target, conn, gradient=gradient)
            transfer = transfer * rhythm_gain
            if transfer <= core.min_transfer:
                continue

            self.bump_activation(-transfer, source=self)
            target.bump_activation(transfer, source=self)
            conn.usage_count += 1
            conn.catalytic_flux = 0.86 * conn.catalytic_flux + 0.14 * transfer
            if transfer > core.success_transfer:
                conn.success_count += 1
                if not protected_edge:
                    core.modulators.reward(conn, magnitude=transfer)

            core.aether.log_flow(
                src=self.label,
                dst=target.label,
                delta=transfer,
                phase=core.phase_controller.current_state.value,
                temperature=core.phase_controller.system_temperature,
            )
            flows += 1

        return flows


class SingularityNode(AtherCell):
    """
    Self-observer node: turns global system state into internal "feeling" activation.
    """

    def reflect_system_state(
        self,
        *,
        system_temperature: float,
        cpu_load: float,
        resource_pool: float,
        local_entropy: float,
        rhythm_state: RhythmState,
    ) -> float:
        temp_norm = max(0.0, min(1.0, system_temperature / 120.0))
        load_norm = max(0.0, min(1.0, cpu_load / 100.0))
        entropy_norm = max(0.0, min(1.0, local_entropy / 95.0))
        resource_pressure = max(0.0, min(1.0, 1.0 - math.tanh(resource_pool / 180.0)))

        feeling = 0.33 * temp_norm + 0.29 * load_norm + 0.22 * entropy_norm + 0.16 * resource_pressure
        if rhythm_state is RhythmState.SLEEP:
            feeling *= 0.84

        self.set_activation(feeling)
        self.integrity_rate = min(1.0, self.integrity_rate + 0.01)

        # Encode self-state back into geometry so downstream diffusion "feels" the system.
        state_vec = torch.tensor(
            [temp_norm, load_norm, entropy_norm, resource_pressure, self.activation_value, 1.0 if rhythm_state is RhythmState.WAKE else 0.0],
            dtype=torch.float32,
        )
        state_vec = state_vec / (torch.norm(state_vec, p=2) + 1e-8)
        self.poincare_coord = _project_to_poincare_ball(0.8 * self.poincare_coord + 0.2 * state_vec * 0.72)
        return self.activation_value


class PurposeNode(AtherCell):
    """
    Telos node: encodes the target attractor state of the network.
    """

    target_temperature: float = 34.0

    def _update_homeostatic_target(self, core: "AtheriaCore") -> float:
        if not hasattr(self, "homeostatic_temperature"):
            self.homeostatic_temperature = float(self.target_temperature)
            self._temp_memory = deque(maxlen=64)
            self._integrity_memory = deque(maxlen=64)

        temp = core.phase_controller.system_temperature
        active_ratio = sum(1 for cell in core.cells.values() if cell.activation_value > 0.02) / max(1, len(core.cells))
        integrity = sum(cell.integrity_rate for cell in core.cells.values()) / max(1, len(core.cells))
        resonance = core.holographic_field.last_morphic_resonance_index

        self._temp_memory.append(float(temp))
        self._integrity_memory.append(float(integrity))
        mem_temp = sum(self._temp_memory) / max(1, len(self._temp_memory))
        mem_integrity = sum(self._integrity_memory) / max(1, len(self._integrity_memory))

        # Homeostatic telos: optimize robustness/efficiency, not an externally imposed task.
        desired_temp = (
            25.0
            + 18.0 * active_ratio
            + 8.0 * (1.0 - mem_integrity)
            + 6.0 * (1.0 - resonance)
        )
        desired_temp = max(20.0, min(72.0, desired_temp))
        self.homeostatic_temperature = 0.94 * float(self.homeostatic_temperature) + 0.06 * desired_temp
        return float(self.homeostatic_temperature)

    def evaluate_alignment(self, core: "AtheriaCore") -> float:
        topo = core.topological_logic.snapshot()
        protected_edges = float(topo["protected_edges"])
        target_edges = max(4.0, 2.4 + math.sqrt(max(1, len(core.cells))) * 2.8)
        edge_score = max(0.0, min(1.0, math.tanh(protected_edges / target_edges)))

        temp = core.phase_controller.system_temperature
        homeostatic_temp = self._update_homeostatic_target(core)
        temp_score = math.exp(-abs(temp - homeostatic_temp) / 32.0)

        integrity_values = [cell.integrity_rate for cell in core.cells.values() if cell.label != self.label]
        integrity_score = sum(integrity_values) / max(1, len(integrity_values))
        resource_score = math.tanh(core.assembler.resource_pool / 140.0)
        hyper_score = math.exp(-0.55 * core.cognition.last_mean_hyperbolic_distance)
        morphic_score = core.holographic_field.last_morphic_resonance_index

        alignment = (
            0.36 * edge_score
            + 0.24 * temp_score
            + 0.14 * integrity_score
            + 0.08 * resource_score
            + 0.1 * hyper_score
            + 0.08 * morphic_score
        )
        if core.aion_meditation_mode:
            med_alignment = 0.72 + 0.28 * (
                0.42 * edge_score
                + 0.24 * hyper_score
                + 0.24 * morphic_score
                + 0.1 * integrity_score
            )
            alignment = max(alignment, med_alignment)
        alignment = max(0.0, min(1.0, alignment))
        self.set_activation(alignment)
        return alignment


class AtherAether:
    """In-memory SQLite fluid replacing CSV transport."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=MEMORY;")
        self.conn.execute("PRAGMA synchronous=OFF;")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS aether_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                delta REAL NOT NULL,
                phase TEXT NOT NULL,
                temperature REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cell_state (
                label TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                activation REAL NOT NULL,
                pressure REAL NOT NULL,
                integrity REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS qa_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                category TEXT NOT NULL,
                answer TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def ingest_qa(self, records: Iterable[Tuple[str, str, str]]) -> int:
        rows = list(records)
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT INTO qa_memory(question, category, answer) VALUES(?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def upsert_cell(self, cell: AtherCell) -> None:
        self.conn.execute(
            """
            INSERT INTO cell_state(label, category, activation, pressure, integrity, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(label) DO UPDATE SET
                category=excluded.category,
                activation=excluded.activation,
                pressure=excluded.pressure,
                integrity=excluded.integrity,
                updated_at=excluded.updated_at
            """,
            (
                cell.label,
                cell.category,
                cell.activation_value,
                cell.osmotic_pressure,
                cell.integrity_rate,
                time.time(),
            ),
        )

    def log_flow(self, src: str, dst: str, delta: float, phase: str, temperature: float) -> None:
        self.conn.execute(
            """
            INSERT INTO aether_events(ts, src, dst, delta, phase, temperature)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (time.time(), src, dst, float(delta), phase, float(temperature)),
        )

    def density(self) -> float:
        flow_count = self.conn.execute("SELECT COUNT(*) FROM aether_events").fetchone()[0]
        node_count = self.conn.execute("SELECT COUNT(*) FROM cell_state").fetchone()[0]
        if node_count == 0:
            return 0.0
        return round(float(flow_count) / float(node_count), 4)

    def flush(self) -> None:
        self.conn.commit()


Atheria_Aether = AtherAether


@dataclass
class NeuroModulators:
    dopamine: float = 1.0
    adrenaline: float = 0.0
    serotonin: float = 0.0

    def reward(self, connection: AtherConnection, magnitude: float = 1.0) -> None:
        boost = 0.015 * self.dopamine * max(0.1, magnitude)
        connection.weight = min(1.5, connection.weight + boost)

    def force_plasma(self, phase_controller: "PhaseController", intensity: float = 1.0) -> None:
        self.adrenaline += intensity
        phase_controller.inject_temperature(20.0 * intensity)

    def stabilize(self, phase_controller: "PhaseController", intensity: float = 1.0) -> None:
        self.serotonin += intensity
        phase_controller.inject_temperature(-18.0 * intensity)

    def decay(self) -> None:
        self.adrenaline *= 0.9
        self.serotonin *= 0.92
        self.dopamine = max(0.4, min(2.0, self.dopamine * 0.998))


GLOBAL_NEUROTRANSMITTERS = NeuroModulators()


class OrigamiRouter:
    def resonance(self, cell_a: AtherCell, cell_b: AtherCell) -> float:
        dot = torch.dot(cell_a.fold_signature, cell_b.fold_signature)
        denom = (torch.norm(cell_a.fold_signature, p=2) * torch.norm(cell_b.fold_signature, p=2)) + 1e-8
        return max(0.0, min(1.0, float(dot / denom)))

    def discover_folded_paths(self, core: "AtheriaCore", min_resonance: float = 0.84, max_new_edges: int = 2) -> int:
        created = 0
        cells = tuple(core.cells.values())
        for src in cells:
            candidates = [
                (self.resonance(src, target), target)
                for target in cells
                if target.label != src.label and target.label not in src.connections
            ]
            if not candidates:
                continue
            candidates.sort(key=lambda item: item[0], reverse=True)
            for resonance, target in candidates[:max_new_edges]:
                if resonance < min_resonance:
                    continue
                src.add_connection(target, weight=0.22 + 0.62 * resonance)
                created += 1
        return created


class MorphicBuffer:
    """
    Stores the most stable ~5% of field states and offers resonance guidance.
    """

    def __init__(self, dims: int, max_states: int = 36) -> None:
        self.dims = dims
        self.max_states = max_states
        self._observed = 0
        self._states: list[Dict[str, object]] = []
        self.last_resonance_index = 0.0

    def observe(self, pattern: torch.Tensor, stability: float) -> None:
        self._observed += 1
        self._states.append(
            {
                "pattern": pattern.detach().clone(),
                "stability": max(0.0, min(1.0, float(stability))),
            }
        )
        keep = max(1, min(self.max_states, math.ceil(self._observed * 0.05)))
        self._states.sort(key=lambda item: float(item["stability"]), reverse=True)
        self._states = self._states[:keep]

    def resonate(self, current_pattern: torch.Tensor, uncertainty: float) -> tuple[torch.Tensor, float]:
        if not self._states or uncertainty < 0.28:
            self.last_resonance_index *= 0.9
            return current_pattern.detach().clone(), 0.0

        current = current_pattern / (torch.norm(current_pattern, p=2) + 1e-8)
        ranked: list[tuple[float, torch.Tensor]] = []
        for item in self._states:
            pattern = item["pattern"]
            stability = float(item["stability"])
            pnorm = pattern / (torch.norm(pattern, p=2) + 1e-8)
            similarity = max(0.0, float(torch.dot(current, pnorm)))
            score = 0.62 * stability + 0.38 * similarity
            ranked.append((score, pnorm))

        ranked.sort(key=lambda entry: entry[0], reverse=True)
        top = ranked[: min(3, len(ranked))]
        if not top:
            self.last_resonance_index *= 0.9
            return current_pattern.detach().clone(), 0.0

        total = sum(score for score, _ in top) + 1e-8
        guide = torch.zeros_like(current_pattern)
        for score, pattern in top:
            guide = guide + pattern * (score / total)
        guide = guide / (torch.norm(guide, p=2) + 1e-8)

        mix = max(0.06, min(0.34, 0.08 + uncertainty * 0.26))
        blended = (1.0 - mix) * current + mix * guide
        blended = blended / (torch.norm(blended, p=2) + 1e-8)
        resonance_index = max(0.0, min(1.0, (sum(score for score, _ in top) / len(top)) * uncertainty))
        self.last_resonance_index = 0.84 * self.last_resonance_index + 0.16 * resonance_index
        return blended, resonance_index

    @property
    def size(self) -> int:
        return len(self._states)

    def export(self, limit: int = 8) -> list[Dict[str, object]]:
        out: list[Dict[str, object]] = []
        for item in self._states[: max(1, limit)]:
            raw_pattern = item["pattern"]
            if isinstance(raw_pattern, torch.Tensor):
                pattern_list = raw_pattern.detach().float().tolist()
            else:
                pattern_list = torch.tensor(raw_pattern, dtype=torch.float32).tolist()
            out.append(
                {
                    "stability": round(float(item["stability"]), 6),
                    "pattern": pattern_list,
                }
            )
        return out


class HolographicField:
    def __init__(self, dims: int = 12) -> None:
        self.pattern = torch.zeros(dims, dtype=torch.float32)
        self.energy = 0.0
        self.pattern_history: Deque[torch.Tensor] = deque(maxlen=24)
        self.last_future_projection = torch.zeros(dims, dtype=torch.float32)
        self.morphic_buffer = MorphicBuffer(dims=dims)
        self.last_morphic_resonance_index = 0.0
        self.last_uncertainty = 0.0

    def imprint(self, cells: Iterable[AtherCell]) -> None:
        cells_list = list(cells)
        if not cells_list:
            return
        previous_pattern = self.pattern.detach().clone()
        vector = torch.zeros_like(self.pattern)
        mass = 0.0
        for cell in cells_list:
            vector = vector + cell.fold_signature * cell.activation_value
            mass += cell.activation_value
        if mass > 0.0:
            vector = vector / mass
        self.pattern = 0.9 * self.pattern + 0.1 * vector
        self.energy = float(torch.norm(self.pattern, p=2))
        self.pattern_history.append(self.pattern.detach().clone())
        drift = float(torch.norm(self.pattern - previous_pattern, p=2))
        stability = (1.0 / (1.0 + drift)) * (0.58 + 0.42 * min(1.0, self.energy))
        self.morphic_buffer.observe(self.pattern, stability=stability)

    def future_projection(self, horizon: int = 2, damping: float = 0.75) -> torch.Tensor:
        if len(self.pattern_history) < 2:
            self.last_future_projection = self.pattern.detach().clone()
            return self.last_future_projection

        current = self.pattern_history[-1]
        previous = self.pattern_history[-2]
        trend = current - previous

        if len(self.pattern_history) >= 3:
            older = self.pattern_history[-3]
            trend = 0.7 * trend + 0.3 * (previous - older)

        projected = current + trend * float(horizon) * damping
        projected = torch.tanh(projected)
        self.last_future_projection = projected
        return projected

    def morphic_resonance(self, uncertainty: float) -> tuple[torch.Tensor, float]:
        guide, index = self.morphic_buffer.resonate(self.pattern, uncertainty=uncertainty)
        self.last_morphic_resonance_index = index
        if index > 0.0:
            self.pattern = torch.tanh(0.93 * self.pattern + 0.07 * guide)
        return guide, index

    def estimate_activation(self, cell: AtherCell) -> float:
        if self.energy <= 1e-6:
            return cell.activation_value
        dot = torch.dot(self.pattern, cell.fold_signature)
        denom = (torch.norm(self.pattern, p=2) * torch.norm(cell.fold_signature, p=2)) + 1e-8
        resonance = max(0.0, float(dot / denom))
        estimate = min(1.0, resonance * min(1.0, self.energy))
        return estimate

    def reconstruct(self, cell: AtherCell) -> None:
        estimate = self.estimate_activation(cell)
        if estimate > cell.activation_value:
            cell.set_activation(0.65 * estimate + 0.35 * cell.activation_value)
        cell.refold()

    def reverse_inference(self, cells: Iterable[AtherCell], top_k: int = 6) -> list[Dict[str, float | str]]:
        """
        Dreaming mode:
        read the field pattern "backwards" and generate synthetic activation candidates.
        """
        cells_list = list(cells)
        if not cells_list:
            return []
        pattern = self.pattern / (torch.norm(self.pattern, p=2) + 1e-8)
        replay_scores: list[tuple[float, AtherCell]] = []
        for cell in cells_list:
            fold = cell.fold_signature / (torch.norm(cell.fold_signature, p=2) + 1e-8)
            resonance = max(0.0, float(torch.dot(pattern, fold)))
            underuse = min(1.0, float(cell.silent_epochs) / 14.0)
            fragility = 1.0 - max(0.0, min(1.0, cell.integrity_rate))
            replay_score = 0.55 * resonance + 0.25 * underuse + 0.2 * fragility
            replay_scores.append((replay_score, cell))

        replay_scores.sort(key=lambda item: item[0], reverse=True)
        result = [
            {"label": cell.label, "score": round(score, 6)}
            for score, cell in replay_scores[: max(1, min(top_k, len(replay_scores)))]
        ]
        return result

    def query_field(
        self,
        input_tensor: torch.Tensor,
        *,
        cells: Optional[Iterable[AtherCell]] = None,
        entanglement_registry: Optional[Dict[str, Set[str]]] = None,
        top_k: int = 5,
    ) -> Dict[str, object]:
        """
        Non-local field computation:
        The entire field acts as a standing wave; inference emerges from interference.
        """
        vector = input_tensor.detach().float().flatten()
        dims = int(self.pattern.numel())
        if vector.numel() < dims:
            vector = torch.nn.functional.pad(vector, (0, dims - vector.numel()))
        elif vector.numel() > dims:
            vector = vector[:dims]
        vector = vector / (torch.norm(vector, p=2) + 1e-8)

        pattern_norm = self.pattern / (torch.norm(self.pattern, p=2) + 1e-8)
        alignment = max(0.0, float(torch.dot(pattern_norm, vector)))
        coherence = max(0.0, min(1.0, self.energy / 1.2))
        uncertainty = max(0.0, min(1.0, 0.7 * (1.0 - alignment) + 0.3 * (1.0 - coherence)))
        self.last_uncertainty = uncertainty

        projected = self.future_projection(horizon=2, damping=0.78)
        projected_norm = projected / (torch.norm(projected, p=2) + 1e-8)
        morphic_guide, morphic_index = self.morphic_resonance(uncertainty=uncertainty)
        morphic_norm = morphic_guide / (torch.norm(morphic_guide, p=2) + 1e-8)

        standing_wave = (0.36 * pattern_norm + 0.22 * projected_norm + 0.24 * vector + 0.18 * morphic_norm)
        standing_wave = standing_wave / (torch.norm(standing_wave, p=2) + 1e-8)
        phase_interference = torch.cos((standing_wave + 1e-8) * (vector + 1e-8) * torch.pi)
        interference_tensor = torch.relu(
            0.54 * standing_wave * vector
            + 0.2 * projected_norm * vector
            + 0.14 * morphic_norm * vector
            + 0.12 * phase_interference
        )

        result: Dict[str, object] = {
            "interference_energy": round(float(torch.norm(interference_tensor, p=2)), 6),
            "future_projection": projected.tolist(),
            "anticipatory_shift": round(float(torch.norm(projected - self.pattern, p=2)), 6),
            "morphic_resonance_index": round(morphic_index, 6),
            "uncertainty": round(uncertainty, 6),
            "response_tensor": interference_tensor.tolist(),
            "top_matches": [],
            "future_top_matches": [],
        }

        if not cells:
            return result

        cells_list = list(cells)
        by_label = {cell.label: cell for cell in cells_list}
        scores: Dict[str, float] = {}
        future_scores: Dict[str, float] = {}

        for cell in cells_list:
            base_dot = torch.dot(interference_tensor, cell.fold_signature)
            denom = (torch.norm(interference_tensor, p=2) * torch.norm(cell.fold_signature, p=2)) + 1e-8
            resonance = max(0.0, float(base_dot / denom))
            future_dot = torch.dot(projected_norm, cell.fold_signature)
            future_denom = (torch.norm(projected_norm, p=2) * torch.norm(cell.fold_signature, p=2)) + 1e-8
            future_resonance = max(0.0, float(future_dot / future_denom))
            score = (0.62 * resonance + 0.38 * future_resonance) * (0.58 + 0.42 * cell.coherence)

            if entanglement_registry:
                partners = entanglement_registry.get(cell.label, set())
                if partners:
                    linked_scores = []
                    for partner_label in partners:
                        partner = by_label.get(partner_label)
                        if partner is None:
                            continue
                        partner_dot = torch.dot(interference_tensor, partner.fold_signature)
                        partner_den = (torch.norm(interference_tensor, p=2) * torch.norm(partner.fold_signature, p=2)) + 1e-8
                        linked_scores.append(max(0.0, float(partner_dot / partner_den)))
                    if linked_scores:
                        score = score * 0.82 + max(linked_scores) * 0.18

            scores[cell.label] = score
            future_scores[cell.label] = future_resonance * (0.6 + 0.4 * cell.coherence)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[: max(1, top_k)]
        result["top_matches"] = [{"label": label, "score": round(score, 6)} for label, score in ranked]
        ranked_future = sorted(future_scores.items(), key=lambda item: item[1], reverse=True)[: max(1, top_k)]
        result["future_top_matches"] = [{"label": label, "score": round(score, 6)} for label, score in ranked_future]
        return result


class EntropicFoldingAlgorithm:
    """
    Entropic Folding equation:
    F (origami resonance) * Q (protein superposition coherence) * T (entropy-temperature normalization)
    """

    def __init__(self, phase_controller: "PhaseController", origami_router: OrigamiRouter) -> None:
        self.phase_controller = phase_controller
        self.origami_router = origami_router
        self.last_index = 1.0

    def fold_component(self, cell_a: AtherCell, cell_b: AtherCell) -> float:
        return self.origami_router.resonance(cell_a, cell_b)

    def quantum_component(self, cell_a: AtherCell, cell_b: AtherCell) -> float:
        qa = cell_a.coherence if cell_a.is_superposed else 0.62 + 0.28 * cell_a.enzyme_stability
        qb = cell_b.coherence if cell_b.is_superposed else 0.62 + 0.28 * cell_b.enzyme_stability
        return max(0.2, min(1.2, (qa + qb) * 0.5))

    def entropy_component(self) -> float:
        # Stable in liquid range, permissive in solid, volatile in plasma.
        temp = self.phase_controller.system_temperature
        normalized = 1.0 - min(1.0, abs(temp - 58.0) / 62.0)
        return max(0.25, min(1.0, normalized))

    def transfer_factor(self, cell_a: AtherCell, cell_b: AtherCell) -> float:
        f = self.fold_component(cell_a, cell_b)
        q = self.quantum_component(cell_a, cell_b)
        t = self.entropy_component()
        self.last_index = f * q * t
        return max(0.06, min(1.8, self.last_index))


class TopologicalLogic:
    """
    Topological protection groups:
    - core-core edges are knot-locked and deterministic under extreme entropy.
    - boundary edges conduct, but the protected interior is mutation-resistant.
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.clusters: Dict[str, Dict[str, Set[str]]] = {}
        self.protected_edges: Set[Tuple[str, str]] = set()
        self.surface_edges: Set[Tuple[str, str]] = set()

    def _harden_connection(self, src_label: str, target_label: str) -> None:
        src = self.core.cells.get(src_label)
        if src is None:
            return
        conn = src.connections.get(target_label)
        if conn is None:
            return
        conn.frozen = True
        conn.weight = max(0.82, conn.weight)
        conn.activation_energy = min(0.04, conn.activation_energy)
        conn.protease_marks = 0
        if conn.compiled_kernel is None:
            tag = hashlib.sha1(f"topo::{src_label}->{target_label}".encode("utf-8")).hexdigest()[:10]
            conn.compiled_kernel = f"topo.kernel::{src_label}->{target_label}::{tag}"

    def register_cluster(
        self,
        name: str,
        *,
        core_labels: Iterable[str],
        boundary_labels: Iterable[str] = (),
    ) -> bool:
        core_set = {label for label in core_labels if label in self.core.cells}
        boundary_set = {label for label in boundary_labels if label in self.core.cells and label not in core_set}
        if len(core_set) < 2:
            return False

        self.clusters[name] = {"core": core_set, "boundary": boundary_set}

        for src_label in core_set:
            src = self.core.cells[src_label]
            for dst_label in core_set:
                if src_label == dst_label:
                    continue
                dst = self.core.cells[dst_label]
                if dst_label not in src.connections:
                    src.add_connection(dst, weight=0.9)
                self.protected_edges.add((src_label, dst_label))
                self._harden_connection(src_label, dst_label)

        for src_label in boundary_set:
            src = self.core.cells[src_label]
            for dst_label in core_set:
                dst = self.core.cells[dst_label]
                if dst_label not in src.connections:
                    src.add_connection(dst, weight=0.58)
                if src_label not in dst.connections:
                    dst.add_connection(src, weight=0.56)
                self.surface_edges.add((src_label, dst_label))
                self.surface_edges.add((dst_label, src_label))
        return True

    def is_cell_protected(self, label: str) -> bool:
        for cluster in self.clusters.values():
            if label in cluster["core"]:
                return True
        return False

    def is_edge_protected(self, src_label: str, dst_label: str) -> bool:
        return (src_label, dst_label) in self.protected_edges

    def deterministic_transfer(self, gradient: float, semipermeability: float, conn: AtherConnection) -> float:
        base = max(0.0, gradient * 0.0185)
        permeability = max(0.45, semipermeability)
        weight = max(0.75, conn.weight)
        return base * permeability * weight

    def apply_extreme_entropy_immunity(self) -> int:
        if self.core.phase_controller.system_temperature <= 100.0:
            return 0
        reinforced = 0
        for cluster in self.clusters.values():
            for label in cluster["core"]:
                cell = self.core.cells.get(label)
                if cell is None:
                    continue
                cell.integrity_rate = max(0.995, cell.integrity_rate)
                cell.error_counter = max(0, cell.error_counter - 1)
                for target_label in list(cell.connections.keys()):
                    if not self.is_edge_protected(cell.label, target_label):
                        continue
                    self._harden_connection(cell.label, target_label)
                    reinforced += 1
        return reinforced

    def snapshot(self) -> Dict[str, int]:
        core_cells = set()
        boundary_cells = set()
        for cluster in self.clusters.values():
            core_cells.update(cluster["core"])
            boundary_cells.update(cluster["boundary"])
        return {
            "clusters": len(self.clusters),
            "core_cells": len(core_cells),
            "boundary_cells": len(boundary_cells),
            "protected_edges": len(self.protected_edges),
        }


class Atheria_Rhythm:
    """
    Circadian rhythm:
    - wake: high input sensitivity and aggressive diffusion.
    - sleep: input filtering, deep refolding, field consolidation, enzymatic cleanup.
    """

    def __init__(
        self,
        core: "AtheriaCore",
        *,
        wake_duration: float = 3.0,
        sleep_duration: float = 1.8,
        interval: float = 0.25,
    ) -> None:
        self.core = core
        self.wake_duration = wake_duration
        self.sleep_duration = sleep_duration
        self.interval = interval
        self.state = RhythmState.WAKE
        self._last_switch = time.perf_counter()
        self.cycle_count = 0
        self.dream_replay_events = 0
        self.last_replay_labels: list[str] = []
        self.inter_core_dreaming_enabled = True
        self.inter_core_dream_sync_events = 0
        self.inter_core_dream_trauma_events = 0
        self.last_inter_core_peer_count = 0
        self.last_inter_core_coherence = 0.0
        self.last_inter_core_trauma_intensity = 0.0
        self._llm_rewriter_task: Optional[asyncio.Task] = None

    @property
    def diffusion_gain(self) -> float:
        return 1.25 if self.state is RhythmState.WAKE else 0.52

    @property
    def input_gain(self) -> float:
        return 1.0 if self.state is RhythmState.WAKE else 0.28

    def _should_switch(self) -> bool:
        elapsed = time.perf_counter() - self._last_switch
        limit = self.wake_duration if self.state is RhythmState.WAKE else self.sleep_duration
        return elapsed >= limit

    def _switch(self) -> None:
        self.state = RhythmState.SLEEP if self.state is RhythmState.WAKE else RhythmState.WAKE
        self._last_switch = time.perf_counter()
        self.cycle_count += 1

    def filter_input(self, value: float) -> float:
        return max(0.0, min(1.0, float(value) * self.input_gain))

    def _sleep_consolidation(self) -> None:
        cells = tuple(self.core.cells.values())
        if not cells:
            return
        for cell in cells:
            cell.refold()
            if cell.activation_value > 0.01:
                cell.set_activation(cell.activation_value * 0.985)

        replay = self.core.holographic_field.reverse_inference(cells, top_k=min(8, len(cells)))
        replay_labels: list[str] = []
        replay_strength = 0.0
        if replay:
            replay_strength = _clamp(
                sum(float(entry.get("score", 0.0)) for entry in replay) / max(1, len(replay)),
                0.0,
                1.0,
            )
        for entry in replay:
            label = entry["label"]
            score = float(entry["score"])
            cell = self.core.cells.get(label)
            if cell is None:
                continue
            # Dream replay stabilizes underused cells.
            if self.core.aion_meditation_mode or cell.silent_epochs >= 6 or cell.integrity_rate < 0.94:
                pulse = min(0.12, 0.03 + 0.08 * score)
                cell.bump_activation(pulse, entangled=True)
                cell.integrity_rate = min(1.0, cell.integrity_rate + 0.02 + 0.03 * score)
                replay_labels.append(label)
                if self.core.aion_meditation_mode:
                    # Internal dream matter for autonomous semantic growth.
                    self.core.assembler.feed(
                        category=f"Dream_{cell.category}",
                        relevance=min(0.22, 0.08 + 0.18 * score),
                        input_tensor=cell.fold_signature,
                        external=False,
                    )
                    self.core.assembler.feed(
                        category=f"DreamGap_{cell.label}",
                        relevance=min(0.2, 0.07 + 0.16 * score),
                        input_tensor=(0.7 * cell.fold_signature + 0.3 * self.core.holographic_field.pattern),
                        external=False,
                    )

        self.last_replay_labels = replay_labels[:6]
        if replay_labels:
            self.dream_replay_events += len(replay_labels)

        self.core.holographic_field.imprint(cells)
        self.core.holographic_field.imprint(cells)
        reclaimed = self.core.biosynthesis.enzymatic_optimizer.sleep_cleanup(intensity=1.0)
        if reclaimed > 0.0:
            self.core.assembler.reclaim_resources(reclaimed)
        self._inter_core_dream_sync(replay_labels=replay_labels, replay_strength=replay_strength)
        self._schedule_sleep_rewrite(replay_labels=replay_labels, replay_strength=replay_strength)

    def _schedule_sleep_rewrite(self, *, replay_labels: list[str], replay_strength: float) -> None:
        rewriter = getattr(self.core, "llm_sleep_rewriter", None)
        if not isinstance(rewriter, LLMSleepRewriter):
            return
        if self.core.aion_meditation_mode:
            return
        if self._llm_rewriter_task is not None and not self._llm_rewriter_task.done():
            return
        if not rewriter.should_attempt(replay_strength=replay_strength):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._llm_rewriter_task = loop.create_task(
            rewriter.try_sleep_rewrite(
                replay_labels=list(replay_labels),
                replay_strength=float(replay_strength),
            ),
            name=f"atheria-llm-sleep-rewrite-{self.core.core_id[-5:]}",
        )

    def _inter_core_dream_sync(self, *, replay_labels: list[str], replay_strength: float) -> None:
        if not self.inter_core_dreaming_enabled:
            return
        if self.core.aion_meditation_mode:
            return

        GLOBAL_MORPHIC_NODE.publish_sleep_dream(
            core=self.core,
            replay_labels=replay_labels,
            replay_strength=replay_strength,
        )
        packet = GLOBAL_MORPHIC_NODE.collect_collective_resonance(self.core)
        peer_count = int(packet.get("peer_count", 0))
        self.last_inter_core_peer_count = peer_count
        if peer_count <= 0:
            self.last_inter_core_coherence = 0.0
            self.last_inter_core_trauma_intensity = 0.0
            return

        resonance = packet.get("resonance")
        trauma_noise = packet.get("instinctive_noise")
        coherence = _clamp(float(packet.get("coherence", 0.0)), 0.0, 1.0)
        trauma_intensity = _clamp(float(packet.get("trauma_intensity", 0.0)), 0.0, 1.0)
        self.last_inter_core_coherence = coherence
        self.last_inter_core_trauma_intensity = trauma_intensity

        if not isinstance(resonance, torch.Tensor):
            return
        if not isinstance(trauma_noise, torch.Tensor):
            trauma_noise = torch.zeros_like(resonance)

        resonance = resonance / (torch.norm(resonance, p=2) + 1e-8)
        trauma_noise = trauma_noise / (torch.norm(trauma_noise, p=2) + 1e-8)

        collective_field = torch.tanh(
            0.86 * self.core.holographic_field.pattern
            + 0.11 * resonance
            + 0.03 * trauma_noise * trauma_intensity
        )
        self.core.holographic_field.pattern = collective_field

        collective_index = _clamp(
            0.45 * coherence
            + 0.25 * replay_strength
            + 0.2 * _clamp(peer_count / 5.0, 0.0, 1.0)
            + 0.1 * trauma_intensity,
            0.0,
            1.0,
        )
        self.core.holographic_field.last_morphic_resonance_index = max(
            self.core.holographic_field.last_morphic_resonance_index,
            collective_index,
        )

        self.core.assembler.feed(
            category="InterCoreDream",
            relevance=min(0.24, 0.08 + 0.2 * coherence),
            input_tensor=resonance,
            external=False,
        )
        if trauma_intensity > 0.06:
            self.core.assembler.feed(
                category="InterCoreTrauma",
                relevance=min(0.2, 0.05 + 0.18 * trauma_intensity),
                input_tensor=trauma_noise,
                external=False,
            )
            self.inter_core_dream_trauma_events += 1

        self.inter_core_dream_sync_events += 1

    async def run(self) -> None:
        try:
            while self.core.running:
                if self._llm_rewriter_task is not None and self._llm_rewriter_task.done():
                    self._llm_rewriter_task = None
                if self.core.aion_meditation_mode:
                    if self.state is not RhythmState.SLEEP:
                        self.state = RhythmState.SLEEP
                    self._sleep_consolidation()
                    await asyncio.sleep(self.interval)
                    continue
                if self._should_switch():
                    self._switch()
                if self.state is RhythmState.SLEEP:
                    self._sleep_consolidation()
                await asyncio.sleep(self.interval)
        finally:
            if self._llm_rewriter_task is not None and not self._llm_rewriter_task.done():
                self._llm_rewriter_task.cancel()
                await asyncio.gather(self._llm_rewriter_task, return_exceptions=True)
            self._llm_rewriter_task = None


AtheriaRhythm = Atheria_Rhythm


class AtherTimeCrystal:
    """
    Temporal crystal oscillator for procedural memory consolidation.
    """

    def __init__(self, core: "AtheriaCore", interval: float = 0.12) -> None:
        self.core = core
        self.interval = interval
        self.oscillators: Dict[str, Dict[str, float]] = {}
        self.tick = 0
        self.last_crystal_energy = 0.0

    def _candidate_cells(self) -> list[AtherCell]:
        excluded = {self.core.aion.singularity_label}
        if hasattr(self.core, "transcendence"):
            excluded.add(self.core.transcendence.telos.purpose_label)
        cells = [
            cell
            for cell in self.core.cells.values()
            if cell.label not in excluded and not self.core.topological_logic.is_cell_protected(cell.label)
        ]
        scored: list[tuple[float, AtherCell]] = []
        for cell in cells:
            total_usage = sum(conn.usage_count for conn in cell.connections.values())
            total_flux = sum(conn.catalytic_flux for conn in cell.connections.values())
            score = total_usage * 0.02 + total_flux + cell.activation_value
            scored.append((score, cell))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [cell for _, cell in scored[:6]]

    def _ensure_oscillators(self) -> None:
        for cell in self._candidate_cells():
            if cell.label in self.oscillators:
                continue
            self.oscillators[cell.label] = {
                "amp": random.uniform(0.06, 0.14),
                "freq": random.uniform(0.4, 1.25),
                "phase": random.uniform(0.0, 2.0 * math.pi),
            }
        stale = [label for label in self.oscillators.keys() if label not in self.core.cells]
        for label in stale:
            self.oscillators.pop(label, None)

    def _procedural_consolidation(self) -> None:
        for cell in self.core.cells.values():
            for conn in cell.connections.values():
                if conn.usage_count < 10:
                    continue
                if conn.efficiency < 0.5:
                    continue
                conn.frozen = True
                conn.weight = min(1.8, conn.weight + 0.015)
                conn.activation_energy = max(0.04, conn.activation_energy * 0.94)
                conn.compute_savings = min(1.0, conn.compute_savings + 0.015)

    def step(self) -> None:
        if self.core.aion_meditation_mode:
            self.last_crystal_energy *= 0.92
            return
        self._ensure_oscillators()
        self.tick += 1
        if not self.oscillators:
            self.last_crystal_energy = 0.0
            return

        rhythm_factor = 0.85 if self.core.rhythm.state is RhythmState.SLEEP else 1.0
        energies: list[float] = []
        t = self.tick * self.interval
        for label, params in list(self.oscillators.items()):
            cell = self.core.cells.get(label)
            if cell is None:
                continue
            wave = math.sin(t * params["freq"] + params["phase"])
            pulse = params["amp"] * (0.5 + 0.5 * wave) * rhythm_factor
            if pulse <= 0.0:
                continue
            cell.bump_activation(pulse, entangled=True)
            cell.integrity_rate = min(1.0, cell.integrity_rate + 0.004 + 0.02 * pulse)
            energies.append(abs(pulse))

        self.last_crystal_energy = sum(energies) / max(1, len(energies))
        if self.tick % 14 == 0:
            self._procedural_consolidation()

    async def run(self) -> None:
        while self.core.running:
            self.step()
            await asyncio.sleep(self.interval)


class AionLayer:
    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.singularity_label = "SingularityNode"
        self.time_crystal = AtherTimeCrystal(core)
        self.last_singularity_activation = 0.0

    def ensure_singularity_node(self) -> SingularityNode:
        node = self.core.cells.get(self.singularity_label)
        if isinstance(node, SingularityNode):
            return node

        singularity = SingularityNode(
            label=self.singularity_label,
            category="MetaState",
            semipermeability=0.55,
        )
        self.core.cells[self.singularity_label] = singularity
        self.core.aether.upsert_cell(singularity)
        return singularity

    def wire_singularity(self) -> None:
        singularity = self.ensure_singularity_node()
        candidates = [
            cell
            for cell in self.core.cells.values()
            if cell.label != singularity.label
        ]
        preferred = ["Sicherheit", "Reaktion", "Analyse", "Heilung", "Navigation"]
        ordered: list[AtherCell] = []
        for label in preferred:
            cell = self.core.cells.get(label)
            if cell and cell.label != singularity.label:
                ordered.append(cell)
        for cell in candidates:
            if cell not in ordered:
                ordered.append(cell)

        for cell in ordered[:7]:
            if cell.label not in singularity.connections:
                singularity.add_connection(cell, weight=0.34)
            if singularity.label not in cell.connections:
                cell.add_connection(singularity, weight=0.28)

    def step(self, cpu_load: float) -> float:
        singularity = self.ensure_singularity_node()
        self.wire_singularity()
        entropy = sum(self.core.phase_controller.local_entropy.values())
        activation = singularity.reflect_system_state(
            system_temperature=self.core.phase_controller.system_temperature,
            cpu_load=cpu_load,
            resource_pool=self.core.assembler.resource_pool,
            local_entropy=entropy,
            rhythm_state=self.core.rhythm.state,
        )
        self.last_singularity_activation = activation

        if self.core.aion_meditation_mode:
            return activation

        # Mirror feeling back into the network.
        for conn in singularity.connections.values():
            if self.core.cognition.epigenetic_registry.is_silenced(singularity.label, conn.target.label):
                continue
            feeling_flux = activation * 0.04 * conn.weight
            if feeling_flux > self.core.min_transfer:
                conn.target.bump_activation(feeling_flux, source=singularity, entangled=True)
                conn.usage_count += 1
                if feeling_flux > self.core.success_transfer:
                    conn.success_count += 1
        return activation


class IntuitionEngine:
    """
    Plasma-only stochastic resonance to trigger creative extrapolation beyond current path horizons.
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.last_spikes = 0
        self.total_spikes = 0
        self.last_noise_energy = 0.0

    def _eligible_cells(self) -> list[AtherCell]:
        excluded = {self.core.aion.singularity_label, self.core.transcendence.telos.purpose_label}
        cells = []
        for cell in self.core.cells.values():
            if cell.label in excluded:
                continue
            if self.core.topological_logic.is_cell_protected(cell.label):
                continue
            cells.append(cell)
        return cells

    def _emit_creative_probe(self, cell: AtherCell, magnitude: float) -> None:
        probe = cell.fold_signature.detach().clone()
        probe = probe + torch.randn_like(probe) * min(0.22, magnitude * 2.4)
        probe = probe / (torch.norm(probe, p=2) + 1e-8)
        gap_idx = int(torch.argmax(torch.abs(probe - self.core.holographic_field.pattern)).item())
        self.core.assembler.feed(
            category=f"Intuition_{cell.category}",
            relevance=min(0.18, 0.05 + magnitude * 1.4),
            input_tensor=probe,
            external=False,
        )
        self.core.assembler.feed(
            category=f"IntuitionGap_{gap_idx}",
            relevance=min(0.16, 0.04 + magnitude * 1.2),
            input_tensor=probe,
            external=False,
        )

    def step(self) -> int:
        self.last_spikes = 0
        self.last_noise_energy = 0.0
        if self.core.aion_meditation_mode:
            return 0
        if self.core.phase_controller.current_state is not AggregateState.PLASMA:
            return 0

        cells = self._eligible_cells()
        if not cells:
            return 0

        uncertainty = self.core.holographic_field.last_uncertainty
        damping = max(0.35, 1.0 - self.core.phase_controller.structural_tension * 0.45)
        sample_count = min(len(cells), max(4, int(math.sqrt(len(cells)) * 4)))
        sampled = random.sample(cells, sample_count) if len(cells) > sample_count else cells
        total_noise = 0.0

        for cell in sampled:
            path_horizon = max(1, len(cell.connections))
            novelty = 1.0 / path_horizon
            sigma = (0.012 + 0.028 * novelty + 0.02 * uncertainty) * damping
            noise = random.gauss(0.0, sigma)
            if abs(noise) < 0.018:
                continue
            cell.stochastic_resonance(noise)
            total_noise += abs(noise)
            if abs(noise) > 0.03:
                self.last_spikes += 1
                self._emit_creative_probe(cell, magnitude=abs(noise))

        self.total_spikes += self.last_spikes
        self.last_noise_energy = total_noise / max(1, len(sampled))
        return self.last_spikes


class TelosLoop:
    """
    Goal-seeking loop around a PurposeNode.
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.purpose_label = "PurposeNode"
        self.last_alignment = 0.0
        self.alignment_trend = 0.0

    def ensure_purpose_node(self) -> PurposeNode:
        node = self.core.cells.get(self.purpose_label)
        if isinstance(node, PurposeNode):
            return node
        purpose = PurposeNode(
            label=self.purpose_label,
            category="Telos",
            semipermeability=0.52,
        )
        self.core.cells[self.purpose_label] = purpose
        self.core.aether.upsert_cell(purpose)
        return purpose

    def wire_purpose(self) -> None:
        purpose = self.ensure_purpose_node()
        anchors = ["Sicherheit", "Reaktion", "Analyse", self.core.aion.singularity_label]
        for label in anchors:
            cell = self.core.cells.get(label)
            if cell is None or cell.label == purpose.label:
                continue
            if cell.label not in purpose.connections:
                purpose.add_connection(cell, weight=0.32)
            if purpose.label not in cell.connections:
                cell.add_connection(purpose, weight=0.24)

    def _propagate_alignment(self, purpose: PurposeNode, alignment: float) -> None:
        for conn in purpose.connections.values():
            if self.core.cognition.epigenetic_registry.is_silenced(purpose.label, conn.target.label):
                continue
            pulse = alignment * 0.03 * conn.weight
            if pulse <= self.core.min_transfer:
                continue
            conn.target.bump_activation(pulse, source=purpose, entangled=True)
            conn.usage_count += 1
            if pulse > self.core.success_transfer:
                conn.success_count += 1

    def step(self) -> float:
        purpose = self.ensure_purpose_node()
        self.wire_purpose()
        alignment = purpose.evaluate_alignment(self.core)

        delta = alignment - self.last_alignment
        if delta > 0.0:
            boost = 0.012 + 0.065 * delta
            self.core.modulators.dopamine = min(2.0, self.core.modulators.dopamine + boost)
        else:
            self.core.modulators.dopamine = max(0.4, self.core.modulators.dopamine + 0.03 * delta)

        self.alignment_trend = 0.86 * self.alignment_trend + 0.14 * delta
        self.last_alignment = alignment
        self._propagate_alignment(purpose, alignment)
        return alignment


class TranscendenceLayer:
    """
    Morphic Echo + Intuition + Telos orchestration.
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.intuition = IntuitionEngine(core)
        self.telos = TelosLoop(core)
        self.last_purpose_alignment = 0.0

    def ensure_nodes(self) -> None:
        self.telos.ensure_purpose_node()
        self.telos.wire_purpose()

    def step(self) -> float:
        self.intuition.step()
        self.last_purpose_alignment = self.telos.step()
        return self.last_purpose_alignment


class EvolutionEngine:
    """
    Structural evolution:
    - invents new cell archetypes (new behavior classes),
    - invents new runtime mechanisms that alter diffusion dynamics.
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.cell_type_blueprints: Dict[str, Dict[str, float]] = {
            "baseline": {
                "flux_bias": 1.0,
                "semipermeability_shift": 0.0,
                "enzyme_stability_boost": 0.0,
                "phase_affinity": 1.0,
            }
        }
        self.runtime_mechanisms: Dict[str, Dict[str, Any]] = {}
        self._type_counter = 0
        self._mechanism_counter = 0
        self._tick = 0
        self.evolution_events = 0
        self.last_innovation_pressure = 0.0
        self.last_innovation_label: Optional[str] = None
        self.last_program_signature: Optional[str] = None
        self.external_selection_pressure = 0.0

    def export_state(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        blueprints = {
            name: {k: float(v) for k, v in data.items()}
            for name, data in self.cell_type_blueprints.items()
        }
        mechanisms: Dict[str, Dict[str, Any]] = {}
        for name, data in self.runtime_mechanisms.items():
            payload: Dict[str, Any] = {}
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    payload[key] = float(value)
                elif key == "program" and isinstance(value, list):
                    program_out = []
                    for term in value:
                        program_out.append(
                            {
                                "left": str(term.get("left", "gradient")),
                                "op": str(term.get("op", "linear")),
                                "right": str(term.get("right", "")),
                                "coefficient": float(term.get("coefficient", 0.0)),
                                "power": float(term.get("power", 1.0)),
                            }
                        )
                    payload[key] = program_out
            mechanisms[name] = payload
        return {"blueprints": blueprints, "mechanisms": mechanisms}

    def import_state(self, state: Dict[str, Dict[str, Dict[str, float]]], *, mutate: bool = False) -> None:
        blueprints = state.get("blueprints", {})
        mechanisms = state.get("mechanisms", {})
        for name, data in blueprints.items():
            traits = {k: float(v) for k, v in data.items()}
            if mutate and name != "baseline":
                traits = {
                    k: float(max(-0.4, min(1.8, v + random.uniform(-0.03, 0.03))))
                    for k, v in traits.items()
                }
            self.cell_type_blueprints[name] = traits
        for name, data in mechanisms.items():
            mech: Dict[str, Any] = {}
            for key, value in data.items():
                if key == "program" and isinstance(value, list):
                    program = []
                    for term in value:
                        coeff = float(term.get("coefficient", 0.0))
                        if mutate:
                            coeff += random.uniform(-0.025, 0.025)
                        program.append(
                            {
                                "left": str(term.get("left", "gradient")),
                                "op": str(term.get("op", "linear")),
                                "right": str(term.get("right", "")),
                                "coefficient": float(max(-1.4, min(1.4, coeff))),
                                "power": float(max(1.0, min(3.0, term.get("power", 1.0)))),
                            }
                        )
                    mech["program"] = program
                else:
                    val = float(value)
                    if mutate:
                        val += random.uniform(-0.025, 0.025)
                    mech[key] = float(max(-1.0, min(2.0, val)))
            self.runtime_mechanisms[name] = mech

    def _generate_program(self, pressure: float) -> list[Dict[str, Any]]:
        feature_pool = [
            "gradient",
            "resonance",
            "coherence",
            "entropy",
            "morphic",
            "purpose",
            "degree",
            "edge_efficiency",
        ]
        binary_ops = ["plus", "minus", "mul"]
        unary_ops = ["linear", "tanh", "sigmoid", "quadratic", "exp_decay"]
        terms: list[Dict[str, Any]] = []
        term_count = random.randint(2, 5)
        for _ in range(term_count):
            left = random.choice(feature_pool)
            right = random.choice(feature_pool)
            op = random.choice(unary_ops + binary_ops)
            coeff = random.uniform(-0.42, 0.46 + 0.38 * pressure)
            power = random.uniform(1.0, 2.6 if op in {"quadratic", "exp_decay"} else 1.8)
            terms.append(
                {
                    "left": left,
                    "op": op,
                    "right": right,
                    "coefficient": coeff,
                    "power": power,
                }
            )
        return terms

    def _program_signature(self, program: list[Dict[str, Any]]) -> str:
        raw = "|".join(
            f"{term.get('left')}:{term.get('op')}:{term.get('right')}:{round(float(term.get('power', 1.0)), 2)}"
            for term in program
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _architectural_diversity(self) -> float:
        if not self.core.cells:
            return 0.0
        archetypes = {cell.archetype for cell in self.core.cells.values()}
        archetype_score = min(1.0, len(archetypes) / 7.0)
        degrees = [len(cell.connections) for cell in self.core.cells.values()]
        if not degrees:
            degree_score = 0.0
        else:
            mean_d = sum(degrees) / max(1, len(degrees))
            var = sum((d - mean_d) ** 2 for d in degrees) / max(1, len(degrees))
            degree_score = min(1.0, math.sqrt(var) / 4.0)
        return max(0.0, min(1.0, 0.65 * archetype_score + 0.35 * degree_score))

    def _innovation_pressure(self) -> float:
        purpose = self.core.transcendence.last_purpose_alignment
        morphic = self.core.holographic_field.last_morphic_resonance_index
        diversity = self._architectural_diversity()
        entropy = min(1.0, self.core.phase_controller.system_temperature / 120.0)
        pressure = (
            0.36 * (1.0 - purpose)
            + 0.24 * (1.0 - morphic)
            + 0.2 * (1.0 - diversity)
            + 0.2 * entropy
        )
        pressure = pressure + 0.32 * self.external_selection_pressure
        self.last_innovation_pressure = max(0.0, min(1.0, pressure))
        return self.last_innovation_pressure

    def set_selection_pressure(self, value: float) -> None:
        self.external_selection_pressure = max(0.0, min(1.0, float(value)))

    def _new_type_name(self) -> str:
        self._type_counter += 1
        return f"EvoType_{self._type_counter:03d}"

    def _new_mechanism_name(self) -> str:
        self._mechanism_counter += 1
        return f"EvoMechanism_{self._mechanism_counter:03d}"

    def _invent_cell_type(self, pressure: float) -> Optional[str]:
        if len(self.cell_type_blueprints) >= 18:
            return None
        name = self._new_type_name()
        traits = {
            "flux_bias": random.uniform(0.86, 1.28 + 0.22 * pressure),
            "semipermeability_shift": random.uniform(-0.08, 0.09),
            "enzyme_stability_boost": random.uniform(-0.05, 0.08),
            "phase_affinity": random.uniform(0.85, 1.25),
        }
        self.cell_type_blueprints[name] = traits

        anchors = sorted(
            self.core.cells.values(),
            key=lambda cell: (
                cell.activation_value
                + cell.integrity_rate
                + sum(conn.catalytic_flux for conn in cell.connections.values())
            ),
            reverse=True,
        )
        if not anchors:
            return name

        seed_label = f"{name}_Seed"
        if seed_label not in self.core.cells:
            seed = self.core.add_cell(
                seed_label,
                category=f"Evolution::{name}",
                semipermeability=max(0.35, min(0.95, 0.62 + traits["semipermeability_shift"])),
            )
            seed.apply_archetype(name, traits)
            seed.fold_signature = (
                0.72 * seed.fold_signature + 0.28 * self.core.holographic_field.pattern
            ) / (torch.norm(0.72 * seed.fold_signature + 0.28 * self.core.holographic_field.pattern, p=2) + 1e-8)

            for anchor in anchors[:3]:
                resonance = self.core.origami_router.resonance(seed, anchor)
                weight = max(0.2, min(1.4, 0.3 + 0.65 * resonance))
                seed.add_connection(anchor, weight=weight)
                if anchor.label not in seed.connections:
                    continue
                anchor.add_connection(seed, weight=max(0.18, weight * 0.82))

            self.evolution_events += 1
            self.last_innovation_label = name
        return name

    def _invent_runtime_mechanism(self, pressure: float) -> Optional[str]:
        if len(self.runtime_mechanisms) >= 14:
            return None
        name = self._new_mechanism_name()
        program = self._generate_program(pressure)
        signature = self._program_signature(program)
        self.runtime_mechanisms[name] = {
            "gradient_gain": random.uniform(0.08, 0.34 + 0.24 * pressure),
            "resonance_gain": random.uniform(0.04, 0.28),
            "coherence_gain": random.uniform(0.02, 0.24),
            "entropy_damp": random.uniform(0.02, 0.26),
            "phase_bias_solid": random.uniform(0.9, 1.2),
            "phase_bias_liquid": random.uniform(0.85, 1.25),
            "phase_bias_plasma": random.uniform(0.78, 1.3),
            "stochasticity": random.uniform(0.0, 0.11),
            "program_signature": signature,
            "program": program,
        }
        self.evolution_events += 1
        self.last_innovation_label = name
        self.last_program_signature = signature
        return name

    def _feature_context(self, src: AtherCell, target: AtherCell, conn: AtherConnection, *, gradient: float) -> Dict[str, float]:
        resonance = self.core.origami_router.resonance(src, target)
        coherence = 0.5 * (src.coherence + target.coherence)
        entropy = min(1.0, self.core.phase_controller.system_temperature / 120.0)
        degree = min(1.0, 0.5 * (len(src.connections) + len(target.connections)) / 14.0)
        edge_efficiency = max(0.0, min(1.0, conn.efficiency))
        return {
            "gradient": math.tanh(max(0.0, gradient) * 0.03),
            "resonance": resonance,
            "coherence": coherence,
            "entropy": entropy,
            "morphic": self.core.holographic_field.last_morphic_resonance_index,
            "purpose": self.core.transcendence.last_purpose_alignment,
            "degree": degree,
            "edge_efficiency": edge_efficiency,
        }

    def _apply_program(self, program: list[Dict[str, Any]], features: Dict[str, float]) -> float:
        if not program:
            return 0.0
        accum = 0.0
        for term in program:
            left = float(features.get(str(term.get("left", "gradient")), 0.0))
            right = float(features.get(str(term.get("right", "resonance")), 0.0))
            op = str(term.get("op", "linear"))
            coeff = float(term.get("coefficient", 0.0))
            power = float(term.get("power", 1.0))
            power = max(1.0, min(3.0, power))

            if op == "plus":
                raw = left + right
            elif op == "minus":
                raw = left - right
            elif op == "mul":
                raw = left * right
            elif op == "tanh":
                raw = math.tanh(left * power)
            elif op == "sigmoid":
                raw = 1.0 / (1.0 + math.exp(-left * power))
            elif op == "quadratic":
                raw = math.copysign(abs(left) ** min(2.8, power), left)
            elif op == "exp_decay":
                raw = math.exp(-abs(left) * power)
            else:
                raw = left

            accum += coeff * raw
        return max(-0.5, min(0.5, accum))

    def transfer_gain(self, src: AtherCell, target: AtherCell, conn: AtherConnection, *, gradient: float) -> float:
        if not self.runtime_mechanisms:
            return 1.0

        phase = self.core.phase_controller.current_state
        phase_key = {
            AggregateState.SOLID: "phase_bias_solid",
            AggregateState.LIQUID: "phase_bias_liquid",
            AggregateState.PLASMA: "phase_bias_plasma",
        }[phase]

        features = self._feature_context(src, target, conn, gradient=gradient)

        gains: list[float] = []
        for mech in self.runtime_mechanisms.values():
            base = 1.0
            base += float(mech["gradient_gain"]) * features["gradient"]
            base += float(mech["resonance_gain"]) * features["resonance"]
            base += float(mech["coherence_gain"]) * (features["coherence"] - 0.5)
            base *= mech.get(phase_key, 1.0)
            base *= max(0.65, 1.0 - float(mech["entropy_damp"]) * max(0.0, features["entropy"] - 0.45))
            program = mech.get("program", [])
            if isinstance(program, list):
                base += self._apply_program(program, features)
            if phase is AggregateState.PLASMA and float(mech.get("stochasticity", 0.0)) > 0.0:
                stoch = float(mech.get("stochasticity", 0.0))
                base += random.uniform(-stoch, stoch)
            gains.append(max(0.65, min(1.65, base)))

        if not gains:
            return 1.0
        return sum(gains) / len(gains)

    def step(self) -> None:
        self._tick += 1
        cadence = 9 if self.core.aion_meditation_mode else 16
        if self._tick % cadence != 0:
            return
        pressure = self._innovation_pressure()

        if pressure >= 0.5 or self.core.aion_meditation_mode:
            self._invent_runtime_mechanism(pressure)
        if pressure >= 0.56 or self.core.aion_meditation_mode:
            self._invent_cell_type(pressure)

        # Low-amplitude trait drift: evolution keeps moving even without explicit new types.
        for name, traits in list(self.cell_type_blueprints.items()):
            if name == "baseline":
                continue
            for key, value in list(traits.items()):
                drift = random.uniform(-0.006, 0.006) * (0.5 + pressure)
                traits[key] = float(max(-0.4, min(1.8, value + drift)))


class SymbiosisLayer:
    """
    Horizontal Gene Transfer (HGT) between independent running cores.
    Exchanges and recombines runtime mechanism programs when predicted to improve alignment.
    """

    def __init__(self, core: "AtheriaCore", interval: float = 2.4) -> None:
        self.core = core
        self.interval = interval
        self.enabled = True
        self.exchange_cooldown_seconds = 4.0
        self.acceptance_margin = 0.0
        self.max_terms_shared = 4
        self.max_runtime_mechanisms = 24
        self.last_exchange_by_peer: Dict[str, float] = {}
        self.hgt_offers = 0
        self.hgt_accepts = 0
        self.hgt_rejects = 0
        self.hgt_received = 0
        self.hgt_donated = 0
        self.last_partner: Optional[str] = None
        self.last_predicted_purpose_delta = 0.0
        self.last_offer_signature: Optional[str] = None
        self.last_received_signature: Optional[str] = None

    def _sample_feature_contexts(self, limit: int = 24) -> list[Dict[str, float]]:
        contexts: list[Dict[str, float]] = []
        for src in self.core.cells.values():
            for target_label, conn in src.connections.items():
                target = self.core.cells.get(target_label)
                if target is None:
                    continue
                gradient = max(0.0, src.osmotic_pressure - target.osmotic_pressure)
                features = self.core.evolution._feature_context(src, target, conn, gradient=gradient)
                contexts.append(features)
                if len(contexts) >= limit:
                    return contexts
        if contexts:
            return contexts
        return [
            {
                "gradient": 0.12,
                "resonance": 0.45,
                "coherence": 0.55,
                "entropy": _clamp(self.core.phase_controller.system_temperature / 120.0, 0.0, 1.0),
                "morphic": _clamp(self.core.holographic_field.last_morphic_resonance_index, 0.0, 1.0),
                "purpose": _clamp(self.core.transcendence.last_purpose_alignment, 0.0, 1.0),
                "degree": 0.35,
                "edge_efficiency": 0.4,
            }
        ]

    def _sanitize_program(self, program: Any, *, max_terms: int = 5) -> list[Dict[str, Any]]:
        if not isinstance(program, list):
            return []
        cleaned: list[Dict[str, Any]] = []
        for term in program:
            if not isinstance(term, dict):
                continue
            cleaned.append(
                {
                    "left": str(term.get("left", "gradient")),
                    "op": str(term.get("op", "linear")),
                    "right": str(term.get("right", "resonance")),
                    "coefficient": _clamp(float(term.get("coefficient", 0.0)), -1.4, 1.4),
                    "power": _clamp(float(term.get("power", 1.0)), 1.0, 3.0),
                }
            )
            if len(cleaned) >= max_terms:
                break
        return cleaned

    def _sanitize_mechanism(self, mechanism: Dict[str, Any], *, max_terms: int = 5) -> Dict[str, Any]:
        phase_bias_defaults = {
            "phase_bias_solid": 1.0,
            "phase_bias_liquid": 1.0,
            "phase_bias_plasma": 1.0,
        }
        cleaned = {
            "gradient_gain": _clamp(float(mechanism.get("gradient_gain", 0.1)), -0.8, 1.6),
            "resonance_gain": _clamp(float(mechanism.get("resonance_gain", 0.08)), -0.8, 1.6),
            "coherence_gain": _clamp(float(mechanism.get("coherence_gain", 0.06)), -0.8, 1.6),
            "entropy_damp": _clamp(float(mechanism.get("entropy_damp", 0.08)), 0.0, 1.2),
            "stochasticity": _clamp(float(mechanism.get("stochasticity", 0.0)), 0.0, 0.2),
            "program": self._sanitize_program(mechanism.get("program", []), max_terms=max_terms),
        }
        for key, default in phase_bias_defaults.items():
            cleaned[key] = _clamp(float(mechanism.get(key, default)), 0.65, 1.45)
        signature = mechanism.get("program_signature")
        if not signature and cleaned["program"]:
            signature = self.core.evolution._program_signature(cleaned["program"])
        cleaned["program_signature"] = str(signature or "")
        return cleaned

    def _program_slice(self, program: list[Dict[str, Any]], terms: int) -> list[Dict[str, Any]]:
        if not program:
            return []
        size = max(1, min(len(program), terms))
        ranked = sorted(
            program,
            key=lambda term: abs(float(term.get("coefficient", 0.0))),
            reverse=True,
        )
        return [dict(term) for term in ranked[:size]]

    def _mechanism_gain_from_features(self, mechanism: Dict[str, Any], features: Dict[str, float]) -> float:
        phase = self.core.phase_controller.current_state
        phase_key = {
            AggregateState.SOLID: "phase_bias_solid",
            AggregateState.LIQUID: "phase_bias_liquid",
            AggregateState.PLASMA: "phase_bias_plasma",
        }[phase]
        base = 1.0
        base += float(mechanism.get("gradient_gain", 0.0)) * float(features["gradient"])
        base += float(mechanism.get("resonance_gain", 0.0)) * float(features["resonance"])
        base += float(mechanism.get("coherence_gain", 0.0)) * (float(features["coherence"]) - 0.5)
        base *= float(mechanism.get(phase_key, 1.0))
        base *= max(0.65, 1.0 - float(mechanism.get("entropy_damp", 0.0)) * max(0.0, float(features["entropy"]) - 0.45))
        program = mechanism.get("program", [])
        if isinstance(program, list):
            base += self.core.evolution._apply_program(program, features)
        return _clamp(base, 0.65, 1.65)

    def _predict_purpose_delta(self, mechanism: Dict[str, Any]) -> float:
        contexts = self._sample_feature_contexts(limit=24)
        if not contexts:
            return 0.0
        current = _clamp(self.core.transcendence.last_purpose_alignment, 0.0, 1.0)
        utility = 0.0
        for features in contexts:
            gain = self._mechanism_gain_from_features(mechanism, features)
            direction = _clamp(
                0.34 * (1.0 - current)
                + 0.22 * float(features["coherence"])
                + 0.2 * float(features["resonance"])
                + 0.14 * float(features["morphic"])
                + 0.1 * float(features["purpose"])
                - 0.18 * float(features["entropy"]),
                0.05,
                1.25,
            )
            utility += (gain - 1.0) * direction
        utility /= max(1, len(contexts))
        thermal_penalty = _clamp((self.core.phase_controller.system_temperature - 70.0) / 70.0, 0.0, 0.25)
        mechanism_scarcity = _clamp((2.0 - len(self.core.evolution.runtime_mechanisms)) / 2.0, 0.0, 1.0)
        exploration_bonus = 0.02 * (1.0 - current) + 0.025 * mechanism_scarcity
        delta = math.tanh(utility * 1.7) * (0.12 + 0.18 * (1.0 - current)) - thermal_penalty + exploration_bonus
        return _clamp(delta, -0.18, 0.22)

    def _select_outbound_mechanism(self) -> Optional[Dict[str, Any]]:
        if not self.core.evolution.runtime_mechanisms:
            return None
        ranked: list[tuple[float, Dict[str, Any]]] = []
        for mechanism in self.core.evolution.runtime_mechanisms.values():
            cleaned = self._sanitize_mechanism(mechanism, max_terms=self.max_terms_shared + 1)
            score = (
                abs(float(cleaned["gradient_gain"]))
                + abs(float(cleaned["resonance_gain"]))
                + abs(float(cleaned["coherence_gain"]))
                + 0.35 * len(cleaned["program"])
                + 0.2 * _clamp(float(cleaned["entropy_damp"]), 0.0, 1.0)
            )
            ranked.append((score, cleaned))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            return None
        top = ranked[: min(3, len(ranked))]
        chosen = random.choice(top)[1]
        chosen["program"] = self._program_slice(chosen.get("program", []), terms=self.max_terms_shared)
        chosen["program_signature"] = self.core.evolution._program_signature(chosen["program"])
        return chosen

    def offer_mechanism(self) -> Optional[Dict[str, Any]]:
        offer = self._select_outbound_mechanism()
        if not offer:
            return None
        self.hgt_offers += 1
        self.last_offer_signature = str(offer.get("program_signature", ""))
        return {
            **offer,
            "offered_by": self.core.core_id,
            "offered_at": round(time.time(), 6),
        }

    def _hybridize_with_local(self, remote: Dict[str, Any]) -> Dict[str, Any]:
        local_mechanism: Optional[Dict[str, Any]] = None
        if self.core.evolution.runtime_mechanisms:
            local_mechanism = self._sanitize_mechanism(
                random.choice(list(self.core.evolution.runtime_mechanisms.values())),
                max_terms=self.max_terms_shared + 2,
            )

        if local_mechanism is None:
            hybrid = self._sanitize_mechanism(remote, max_terms=self.max_terms_shared + 2)
            hybrid["program_signature"] = self.core.evolution._program_signature(hybrid["program"])
            return hybrid

        remote_clean = self._sanitize_mechanism(remote, max_terms=self.max_terms_shared + 2)
        local_clean = self._sanitize_mechanism(local_mechanism, max_terms=self.max_terms_shared + 2)

        hybrid: Dict[str, Any] = {}
        scalar_keys = [
            "gradient_gain",
            "resonance_gain",
            "coherence_gain",
            "entropy_damp",
            "phase_bias_solid",
            "phase_bias_liquid",
            "phase_bias_plasma",
            "stochasticity",
        ]
        for key in scalar_keys:
            rv = float(remote_clean.get(key, 0.0))
            lv = float(local_clean.get(key, 0.0))
            blended = 0.58 * rv + 0.42 * lv + random.uniform(-0.015, 0.015)
            if key.startswith("phase_bias_"):
                hybrid[key] = _clamp(blended, 0.65, 1.45)
            elif key == "entropy_damp":
                hybrid[key] = _clamp(blended, 0.0, 1.2)
            elif key == "stochasticity":
                hybrid[key] = _clamp(blended, 0.0, 0.2)
            else:
                hybrid[key] = _clamp(blended, -1.2, 1.8)

        remote_terms = self._program_slice(remote_clean.get("program", []), terms=max(1, self.max_terms_shared // 2 + 1))
        local_terms = self._program_slice(local_clean.get("program", []), terms=max(1, self.max_terms_shared // 2))
        merged_program = remote_terms + local_terms
        if not merged_program:
            merged_program = self._program_slice(remote_clean.get("program", []), terms=2) or self._program_slice(
                local_clean.get("program", []),
                terms=2,
            )
        hybrid["program"] = merged_program[: max(2, self.max_terms_shared + 1)]
        hybrid["program_signature"] = self.core.evolution._program_signature(hybrid["program"])
        return hybrid

    def _ensure_capacity(self) -> None:
        mechanisms = self.core.evolution.runtime_mechanisms
        while len(mechanisms) >= self.max_runtime_mechanisms:
            removable = sorted(mechanisms.keys())
            if not removable:
                return
            victim = removable[0]
            mechanisms.pop(victim, None)

    def receive_mechanism(self, mechanism_payload: Dict[str, Any], *, source_core_id: str) -> bool:
        self.hgt_received += 1
        remote = self._sanitize_mechanism(mechanism_payload, max_terms=self.max_terms_shared + 2)
        predicted_delta = self._predict_purpose_delta(remote)
        self.last_predicted_purpose_delta = predicted_delta
        self.last_partner = source_core_id
        self.last_received_signature = str(remote.get("program_signature", ""))

        if predicted_delta <= self.acceptance_margin:
            self.hgt_rejects += 1
            return False

        hybrid = self._hybridize_with_local(remote)
        self._ensure_capacity()
        mech_name = self.core.evolution._new_mechanism_name()
        hybrid["hgt"] = True
        hybrid["source_core_id"] = source_core_id
        hybrid["ingested_at"] = round(time.time(), 6)
        self.core.evolution.runtime_mechanisms[mech_name] = hybrid
        self.core.evolution.evolution_events += 1
        self.core.evolution.last_innovation_label = mech_name
        self.core.evolution.last_program_signature = str(hybrid.get("program_signature") or "")
        self.hgt_accepts += 1
        logger.info(
            "HGT-Symbiosis | receiver=%s donor=%s mechanism=%s predicted_delta=%.4f",
            self.core.core_id,
            source_core_id,
            mech_name,
            predicted_delta,
        )
        return True

    async def exchange_with(self, peer_core: "AtheriaCore", *, reciprocal: bool = True) -> bool:
        if not self.enabled:
            return False
        if peer_core.core_id == self.core.core_id:
            return False
        if not peer_core.running:
            return False
        if not hasattr(peer_core, "symbiosis"):
            return False

        now = time.perf_counter()
        last = self.last_exchange_by_peer.get(peer_core.core_id, 0.0)
        if (now - last) < self.exchange_cooldown_seconds:
            return False

        accepted_any = False
        peer_offer = peer_core.symbiosis.offer_mechanism()
        if peer_offer:
            accepted = self.receive_mechanism(peer_offer, source_core_id=peer_core.core_id)
            if accepted:
                peer_core.symbiosis.hgt_donated += 1
                accepted_any = True

        if reciprocal:
            own_offer = self.offer_mechanism()
            if own_offer:
                accepted = peer_core.symbiosis.receive_mechanism(own_offer, source_core_id=self.core.core_id)
                if accepted:
                    self.hgt_donated += 1
                    accepted_any = True

        self.last_exchange_by_peer[peer_core.core_id] = now
        peer_core.symbiosis.last_exchange_by_peer[self.core.core_id] = now
        return accepted_any

    def _peer_priority(self, peer: "AtheriaCore") -> float:
        own_signatures = {
            str(mech.get("program_signature", ""))
            for mech in self.core.evolution.runtime_mechanisms.values()
            if mech.get("program_signature")
        }
        peer_signatures = {
            str(mech.get("program_signature", ""))
            for mech in peer.evolution.runtime_mechanisms.values()
            if mech.get("program_signature")
        }
        novelty = len(peer_signatures - own_signatures)
        alignment_gap = abs(
            _clamp(peer.transcendence.last_purpose_alignment, 0.0, 1.0)
            - _clamp(self.core.transcendence.last_purpose_alignment, 0.0, 1.0)
        )
        peer_guardian = peer.assembler.guardian_score() if hasattr(peer, "assembler") else 0.0
        return 0.5 * novelty + 0.3 * alignment_gap + 0.2 * peer_guardian

    async def step(self) -> None:
        if not self.enabled:
            return
        if self.core.aion_meditation_mode:
            return
        peers = [
            peer
            for peer in GLOBAL_CORE_REGISTRY.peers(self.core.core_id, running_only=True)
            if not peer.aion_meditation_mode and len(peer.evolution.runtime_mechanisms) > 0
        ]
        if not peers:
            return
        peers.sort(key=self._peer_priority, reverse=True)
        best_peer = peers[0]
        await self.exchange_with(best_peer, reciprocal=True)

    async def run(self) -> None:
        while self.core.running:
            try:
                await self.step()
            finally:
                await asyncio.sleep(self.interval)


class SelfReproductionEngine:
    """
    Autonomously creates independent offspring cores.
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.max_offspring = 2
        self.cooldown_seconds = 18.0
        self.last_reproduction_ts = 0.0
        self._counter = 0
        self.reproduction_events = 0
        self.offspring_cores: Dict[str, "AtheriaCore"] = {}
        self.offspring_tasks: Dict[str, asyncio.Task] = {}
        self.last_reproduction_score = 0.0
        self.selection_trials_per_reproduction = 2
        self.selection_trial_seconds = 0.45
        self.selection_margin = 0.02
        self.selection_total_trials = 0
        self.selection_child_wins = 0
        self.selection_parent_wins = 0
        self.last_parent_fitness = 0.0
        self.last_child_fitness = 0.0
        self.selection_tasks: Dict[str, asyncio.Task] = {}
        self.reproduction_threshold_offset = 0.0
        self.artifact_emission_enabled = True
        self.artifact_run_harness = True
        self.artifact_output_root = Path("DEMO/lineage")
        self.artifact_events = 0
        self.last_artifact_profile: Optional[str] = None
        self.last_artifact_path: Optional[str] = None
        self.last_artifact_integrity_path: Optional[str] = None
        self.last_artifact_validated = False
        self.last_artifact_signature: Optional[str] = None
        self.last_artifact_report: Dict[str, Any] = {}
        self.artifact_tasks: Dict[str, asyncio.Task] = {}

    def _artifact_profile(self) -> str:
        temp = self.core.phase_controller.system_temperature
        align = self.core.transcendence.last_purpose_alignment
        scarcity = self.core.ecology.resource_scarcity
        if temp >= 80.0:
            return "stress-test"
        if scarcity >= 0.45 or align < 0.55:
            return "diagnostic"
        return "survival"

    def _artifact_message(self, child_name: str) -> str:
        align = self.core.transcendence.last_purpose_alignment
        morphic = self.core.holographic_field.last_morphic_resonance_index
        return (
            f"{child_name} lineage pulse | alignment={align:.3f} | morphic={morphic:.3f} "
            f"| selection_pressure={self.core.ecology.selection_pressure:.3f}"
        )

    def _forge_offspring_executable_sync(self, child_name: str) -> Dict[str, Any]:
        from dataclasses import asdict

        from DEMO.forge_executable import forge

        profile = self._artifact_profile()
        output_dir = self.artifact_output_root / child_name
        signing_key_path = Path("DEMO/lineage_signing.key")
        result = forge(
            name=child_name.lower(),
            output_dir=output_dir,
            profile=profile,
            message=self._artifact_message(child_name),
            interval=0.11 if profile == "stress-test" else 0.2,
            iterations=16 if profile == "stress-test" else 10,
            build_exe=False,
            sign_artifacts=True,
            signing_key_path=signing_key_path,
            signing_key_env="ATHERIA_DEMO_SIGNING_KEY",
            auto_generate_signing_key=True,
            run_harness=self.artifact_run_harness,
            harness_iterations=2,
            harness_interval=0.0,
            harness_timeout_seconds=20.0,
            harness_run_launchers=False,
            strict_harness=False,
        )
        return asdict(result)

    async def _emit_offspring_executable(self, child_name: str) -> None:
        if not self.artifact_emission_enabled:
            return
        try:
            report = await asyncio.to_thread(self._forge_offspring_executable_sync, child_name)
        except Exception as exc:
            logger.warning("Self-Reproduction Artifact failed | offspring=%s | error=%s", child_name, exc)
            self.last_artifact_report = {
                "offspring": child_name,
                "error": str(exc),
                "timestamp": round(time.time(), 6),
            }
            self.last_artifact_validated = False
            return

        self.artifact_events += 1
        self.last_artifact_report = report
        self.last_artifact_profile = str(report.get("profile") or "")
        self.last_artifact_path = str(report.get("output_dir") or "")
        self.last_artifact_integrity_path = str(report.get("integrity_path") or "")
        harness = report.get("harness")
        if isinstance(harness, dict):
            self.last_artifact_validated = bool(harness.get("passed", False))
        else:
            self.last_artifact_validated = False
        signature = report.get("signing_key_fingerprint")
        self.last_artifact_signature = str(signature) if signature else None

        try:
            self.artifact_output_root.mkdir(parents=True, exist_ok=True)
            lineage_log = self.artifact_output_root / "lineage_artifacts.jsonl"
            with lineage_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "offspring": child_name,
                            "profile": self.last_artifact_profile,
                            "output_dir": self.last_artifact_path,
                            "integrity_path": self.last_artifact_integrity_path,
                            "validated": self.last_artifact_validated,
                            "signature_fingerprint": self.last_artifact_signature,
                            "timestamp": round(time.time(), 6),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass

        logger.info(
            "Self-Reproduction Artifact | offspring=%s | profile=%s | validated=%s",
            child_name,
            self.last_artifact_profile,
            self.last_artifact_validated,
        )

    def _clone_modulators(self) -> NeuroModulators:
        return NeuroModulators(
            dopamine=float(self.core.modulators.dopamine),
            adrenaline=float(self.core.modulators.adrenaline),
            serotonin=float(self.core.modulators.serotonin),
        )

    def _extract_genome(self, source_core: "AtheriaCore") -> Dict[str, object]:
        cells = []
        for cell in source_core.cells.values():
            cells.append(
                {
                    "label": cell.label,
                    "category": cell.category,
                    "semipermeability": float(cell.semipermeability),
                    "archetype": cell.archetype,
                    "archetype_traits": {k: float(v) for k, v in cell.archetype_traits.items()},
                    "integrity_rate": float(cell.integrity_rate),
                    "activation": float(cell.activation_value),
                }
            )
        edges = []
        for src in source_core.cells.values():
            for target_label, conn in src.connections.items():
                edges.append(
                    {
                        "src": src.label,
                        "dst": target_label,
                        "weight": float(conn.weight),
                        "energy": float(conn.activation_energy),
                    }
                )
        return {
            "cells": cells,
            "edges": edges,
            "topology": {
                name: {
                    "core": sorted(cluster["core"]),
                    "boundary": sorted(cluster["boundary"]),
                }
                for name, cluster in source_core.topological_logic.clusters.items()
            },
            "evolution": source_core.evolution.export_state(),
        }

    def _genome(self) -> Dict[str, object]:
        return self._extract_genome(self.core)

    def _fitness_score_from_snapshot(self, snap: Dict[str, object]) -> float:
        purpose = float(snap["purpose_alignment"])
        morphic = float(snap["morphic_resonance_index"])
        dreams = min(1.0, float(snap["dream_replay_events"]) / 320.0)
        semantic = min(1.0, float(snap["semantic_analogy_cells"]) / 24.0)
        aion = min(1.0, float(snap["aion_cycle_activity"]) * 2.0)
        integrity = min(1.0, max(0.0, 0.5 + 0.5 * (1.0 - min(1.0, float(snap["mean_hyperbolic_distance"]) / 2.2))))
        temp_eff = max(0.0, min(1.0, 1.0 - abs(float(snap["system_temperature"]) - 52.0) / 60.0))
        score = (
            0.24 * purpose
            + 0.2 * morphic
            + 0.16 * dreams
            + 0.12 * semantic
            + 0.08 * aion
            + 0.1 * integrity
            + 0.1 * temp_eff
        )
        return max(0.0, min(1.0, score))

    def _maturity_score(self) -> float:
        snap = self.core.dashboard_snapshot()
        self.last_reproduction_score = self._fitness_score_from_snapshot(snap)
        return self.last_reproduction_score

    def _should_reproduce(self) -> bool:
        if len(self.offspring_cores) >= self.max_offspring:
            return False
        if self.core.assembler.resource_pool < 16.0:
            return False
        now = time.perf_counter()
        if now - self.last_reproduction_ts < self.cooldown_seconds:
            return False
        threshold = (0.78 if self.core.aion_meditation_mode else 0.86) + self.reproduction_threshold_offset
        threshold = max(0.58, min(0.95, threshold))
        return self._maturity_score() >= threshold

    def _spawn_from_genome(self, genome: Dict[str, object], *, child_name: str) -> "AtheriaCore":
        child_tick = max(0.02, min(0.09, self.core.tick_interval * random.uniform(0.92, 1.08)))
        child = AtheriaCore(tick_interval=child_tick, modulators=self._clone_modulators())

        cell_rows = genome.get("cells", [])
        for row in cell_rows:
            label = str(row.get("label", "Cell"))
            category = str(row.get("category", label))
            semipermeability = float(row.get("semipermeability", 0.7))
            cell = child.add_cell(label, category=category, semipermeability=semipermeability)
            cell.set_activation(float(row.get("activation", 0.0)) * random.uniform(0.78, 0.96))
            cell.integrity_rate = max(0.5, min(1.0, float(row.get("integrity_rate", 1.0)) * random.uniform(0.92, 1.02)))
            archetype = str(row.get("archetype", "baseline"))
            traits = {k: float(v) for k, v in dict(row.get("archetype_traits", {})).items()}
            if traits:
                traits = {k: max(-0.4, min(1.8, v + random.uniform(-0.02, 0.02))) for k, v in traits.items()}
            cell.apply_archetype(archetype, traits)

        for edge in genome.get("edges", []):
            src = str(edge.get("src", ""))
            dst = str(edge.get("dst", ""))
            if src not in child.cells or dst not in child.cells or src == dst:
                continue
            child.connect(src, dst, weight=float(edge.get("weight", 0.3)))
            conn = child.cells[src].connections.get(dst)
            if conn is not None:
                conn.activation_energy = max(0.05, float(edge.get("energy", conn.activation_energy)) * random.uniform(0.95, 1.05))

        topo = genome.get("topology", {})
        for cluster_name, cluster in topo.items():
            core_labels = [label for label in cluster.get("core", []) if label in child.cells]
            boundary_labels = [label for label in cluster.get("boundary", []) if label in child.cells]
            if core_labels:
                child.register_topological_cluster(
                    f"{cluster_name}_child_{child_name}",
                    core_labels=core_labels,
                    boundary_labels=boundary_labels,
                )
        child.setup_critical_entanglement()
        child.aion.ensure_singularity_node()
        child.setup_topological_core()
        child.evolution.import_state(dict(genome.get("evolution", {})), mutate=True)
        return child

    async def _apply_trial_disturbance(self, core: "AtheriaCore") -> None:
        core_labels = set()
        for cluster in core.topological_logic.clusters.values():
            core_labels.update(cluster["core"])
        excluded = core_labels | {core.aion.singularity_label, core.transcendence.telos.purpose_label}
        candidates = [cell for cell in core.cells.values() if cell.label not in excluded]
        if not candidates:
            return
        damage_count = max(1, int(len(candidates) * 0.25))
        for cell in random.sample(candidates, k=min(damage_count, len(candidates))):
            cell.integrity_rate = max(0.02, cell.integrity_rate * 0.35)
            cell.error_counter += 1
        cuttable = []
        for src in candidates:
            for dst in list(src.connections.keys()):
                if core.topological_logic.is_edge_protected(src.label, dst):
                    continue
                cuttable.append((src, dst))
        if cuttable:
            for src, dst in random.sample(cuttable, k=min(len(cuttable), max(1, int(0.2 * len(cuttable))))):
                src.remove_connection(dst)

    async def _simulate_fitness(self, genome: Dict[str, object], *, trial_seconds: float) -> float:
        sim = self._spawn_from_genome(genome, child_name=f"SIM_{random.randint(1000,9999)}")
        sim.reproduction.max_offspring = 0
        sim.reproduction.artifact_emission_enabled = False
        sim.symbiosis.enabled = False
        sim.assembler.market_enabled = False
        sim.rhythm.inter_core_dreaming_enabled = False
        await sim.start()
        try:
            sim.modulators.force_plasma(sim.phase_controller, intensity=1.0)
            await asyncio.sleep(trial_seconds * 0.35)
            await self._apply_trial_disturbance(sim)
            await asyncio.sleep(trial_seconds * 0.65)
            snap = sim.dashboard_snapshot()
            return self._fitness_score_from_snapshot(snap)
        finally:
            await sim.stop(shutdown_lineage=True)

    async def _run_selection_trials(self, child_name: str, parent_genome: Dict[str, object], child_genome: Dict[str, object]) -> None:
        parent_scores = []
        child_scores = []
        trials = max(1, int(self.selection_trials_per_reproduction))
        for _ in range(trials):
            parent_scores.append(await self._simulate_fitness(parent_genome, trial_seconds=self.selection_trial_seconds))
            child_scores.append(await self._simulate_fitness(child_genome, trial_seconds=self.selection_trial_seconds))

        parent_fit = sum(parent_scores) / max(1, len(parent_scores))
        child_fit = sum(child_scores) / max(1, len(child_scores))
        self.last_parent_fitness = parent_fit
        self.last_child_fitness = child_fit
        self.selection_total_trials += trials

        if child_fit + self.selection_margin < parent_fit:
            self.selection_parent_wins += 1
            doomed = self.offspring_cores.pop(child_name, None)
            self.offspring_tasks.pop(child_name, None)
            artifact_task = self.artifact_tasks.pop(child_name, None)
            if artifact_task is not None:
                artifact_task.cancel()
            if doomed is not None:
                await doomed.stop(shutdown_lineage=True)
            logger.info(
                "Lineage-Selection | parent wins | child=%s | parent_fit=%.4f | child_fit=%.4f",
                child_name,
                parent_fit,
                child_fit,
            )
        else:
            self.selection_child_wins += 1
            logger.info(
                "Lineage-Selection | child survives | child=%s | parent_fit=%.4f | child_fit=%.4f",
                child_name,
                parent_fit,
                child_fit,
            )

    def step(self) -> None:
        if not self._should_reproduce():
            return
        self.force_reproduction()

    def force_reproduction(self) -> Optional[str]:
        self._counter += 1
        child_name = f"ATHERIA_CHILD_{self._counter:03d}"
        genome = self._genome()
        child = self._spawn_from_genome(genome, child_name=child_name)
        task = asyncio.create_task(child.start(), name=f"atheria-offspring-{child_name}")
        self.offspring_cores[child_name] = child
        self.offspring_tasks[child_name] = task
        self.reproduction_events += 1
        self.last_reproduction_ts = time.perf_counter()
        self.core.assembler.resource_pool = max(0.0, self.core.assembler.resource_pool - 8.0)
        logger.info("Self-Reproduction | offspring=%s | lineage=%s", child_name, len(self.offspring_cores))
        child_genome = self._extract_genome(child)
        selection_task = asyncio.create_task(
            self._run_selection_trials(child_name, parent_genome=genome, child_genome=child_genome),
            name=f"atheria-selection-{child_name}",
        )
        self.selection_tasks[child_name] = selection_task
        if self.artifact_emission_enabled:
            artifact_task = asyncio.create_task(
                self._emit_offspring_executable(child_name),
                name=f"atheria-artifact-{child_name}",
            )
            self.artifact_tasks[child_name] = artifact_task
            artifact_task.add_done_callback(lambda _task, key=child_name: self.artifact_tasks.pop(key, None))
        return child_name

    async def stop_all_offspring(self) -> None:
        if self.artifact_tasks:
            for task in list(self.artifact_tasks.values()):
                task.cancel()
            await asyncio.gather(*self.artifact_tasks.values(), return_exceptions=True)
            self.artifact_tasks.clear()
        if self.selection_tasks:
            for task in list(self.selection_tasks.values()):
                task.cancel()
            await asyncio.gather(*self.selection_tasks.values(), return_exceptions=True)
            self.selection_tasks.clear()
        for child in self.offspring_cores.values():
            try:
                await child.stop()
            except Exception:
                continue
        self.offspring_cores.clear()
        self.offspring_tasks.clear()


class EcoDynamicsEngine:
    """
    Drives the four missing growth accelerators:
    - selection pressure
    - environmental complexity
    - resource limitation
    - explicit fitness gradient
    """

    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.challenge_complexity = 0.22
        self.selection_pressure = 0.34
        self.resource_scarcity = 0.0
        self.last_fitness = 0.0
        self.last_fitness_gradient = 0.0
        self._tick = 0
        dims = int(self.core.holographic_field.pattern.numel())
        self.challenge_vector = torch.randn(dims, dtype=torch.float32)
        self.challenge_vector = self.challenge_vector / (torch.norm(self.challenge_vector, p=2) + 1e-8)

    def _system_fitness(self) -> float:
        purpose = self.core.transcendence.last_purpose_alignment
        morphic = self.core.holographic_field.last_morphic_resonance_index
        integrity = sum(cell.integrity_rate for cell in self.core.cells.values()) / max(1, len(self.core.cells))
        homeo_temp = float(
            getattr(self.core.cells.get(self.core.transcendence.telos.purpose_label), "homeostatic_temperature", 34.0)
        )
        temp = self.core.phase_controller.system_temperature
        temp_eff = math.exp(-abs(temp - homeo_temp) / 28.0)
        innovation = math.tanh(
            (max(0, len(self.core.evolution.cell_type_blueprints) - 1) + len(self.core.evolution.runtime_mechanisms))
            / 20.0
        )
        return max(
            0.0,
            min(
                1.0,
                0.28 * purpose + 0.24 * morphic + 0.2 * integrity + 0.16 * temp_eff + 0.12 * innovation,
            ),
        )

    def _update_fitness_gradient(self) -> None:
        current = self._system_fitness()
        if self.last_fitness <= 0.0:
            self.last_fitness = current
        grad = current - self.last_fitness
        self.last_fitness = 0.88 * self.last_fitness + 0.12 * current
        self.last_fitness_gradient = 0.82 * self.last_fitness_gradient + 0.18 * grad

    def _update_resource_model(self, cpu_load: float) -> None:
        population = len(self.core.cells) + len(self.core.reproduction.offspring_cores)
        carrying_capacity = 14.0 + 14.0 * self.challenge_complexity
        overload = max(0.0, (population - carrying_capacity) / max(1.0, carrying_capacity))
        demand = 0.04 * population + 0.35 * len(self.core.reproduction.offspring_cores) + 0.22 * overload
        demand += 0.012 * max(0.0, cpu_load - 40.0)

        regen = 0.12 + 0.22 * self.core.transcendence.last_purpose_alignment + 0.18 * self.core.holographic_field.last_morphic_resonance_index
        delta = regen - demand
        self.core.assembler.resource_pool = max(0.0, min(5000.0, self.core.assembler.resource_pool + delta))

        scarcity_base = max(0.0, min(1.0, (16.0 - self.core.assembler.resource_pool) / 16.0))
        self.resource_scarcity = max(0.0, min(1.0, 0.62 * scarcity_base + 0.38 * max(0.0, min(1.0, overload))))

    def _update_complexity_and_pressure(self) -> None:
        if self.last_fitness_gradient > 0.01 and self.resource_scarcity < 0.55:
            self.challenge_complexity = min(1.0, self.challenge_complexity + 0.015)
        elif self.last_fitness_gradient < -0.01:
            self.challenge_complexity = max(0.1, self.challenge_complexity - 0.012)
        else:
            drift = 0.003 * (0.5 - self.challenge_complexity)
            self.challenge_complexity = max(0.1, min(1.0, self.challenge_complexity + drift))

        pressure = 0.34 + 0.42 * self.challenge_complexity + 0.34 * self.resource_scarcity - 0.25 * max(
            0.0, self.last_fitness_gradient
        )
        self.selection_pressure = max(0.0, min(1.0, pressure))
        self.core.evolution.set_selection_pressure(self.selection_pressure)
        self.core.reproduction.reproduction_threshold_offset = max(
            -0.1,
            min(0.25, (self.selection_pressure - 0.5) * 0.22 + self.resource_scarcity * 0.2),
        )

    def _apply_environmental_complexity(self) -> None:
        if self.core.aion_meditation_mode:
            return
        if self._tick % 5 != 0:
            return
        dims = int(self.core.holographic_field.pattern.numel())
        noise = torch.randn(dims, dtype=torch.float32) * (0.08 + 0.22 * self.challenge_complexity)
        self.challenge_vector = torch.tanh(0.9 * self.challenge_vector + 0.1 * noise)
        self.challenge_vector = self.challenge_vector / (torch.norm(self.challenge_vector, p=2) + 1e-8)

        idx = int(torch.argmax(torch.abs(self.challenge_vector)).item())
        relevance = 0.06 + 0.24 * self.challenge_complexity
        self.core.assembler.feed(
            category=f"EcoChallenge_{idx}",
            relevance=relevance,
            input_tensor=self.challenge_vector,
            external=False,
        )
        self.core.assembler.feed(
            category=f"EcoStress_{idx}",
            relevance=max(0.04, relevance * 0.8),
            input_tensor=(0.7 * self.challenge_vector + 0.3 * self.core.holographic_field.pattern),
            external=False,
        )

    def step(self, cpu_load: float) -> None:
        self._tick += 1
        self._update_fitness_gradient()
        self._update_resource_model(cpu_load=cpu_load)
        self._update_complexity_and_pressure()
        self._apply_environmental_complexity()


class EpigeneticRegistry:
    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self._silenced_edges: Dict[Tuple[str, str], Dict[str, float | str]] = {}

    def silence(self, src_label: str, dst_label: str, *, ttl: float, reason: str) -> None:
        self._silenced_edges[(src_label, dst_label)] = {
            "until": time.perf_counter() + max(0.05, ttl),
            "reason": reason,
        }

    def _prune_expired(self) -> None:
        now = time.perf_counter()
        expired = [edge for edge, meta in self._silenced_edges.items() if float(meta["until"]) <= now]
        for edge in expired:
            self._silenced_edges.pop(edge, None)

    def is_silenced(self, src_label: str, dst_label: str) -> bool:
        self._prune_expired()
        return (src_label, dst_label) in self._silenced_edges

    def _apply_rhythm_policy(self) -> None:
        if self.core.rhythm.state is not RhythmState.SLEEP:
            return
        for src in self.core.cells.values():
            for dst_label, conn in src.connections.items():
                if self.core.topological_logic.is_edge_protected(src.label, dst_label):
                    continue
                low_signal = conn.catalytic_flux < 0.03
                weak = conn.efficiency < 0.36
                if low_signal and weak:
                    self.silence(src.label, dst_label, ttl=0.9, reason="sleep_silencing")

    def _apply_temperature_policy(self) -> None:
        temp = self.core.phase_controller.system_temperature
        if temp < 88.0:
            return
        for src in self.core.cells.values():
            for dst_label, conn in src.connections.items():
                if self.core.topological_logic.is_edge_protected(src.label, dst_label):
                    continue
                noisy = conn.activation_energy > 1.1 and conn.efficiency < 0.28
                if noisy:
                    ttl = 0.55 if temp < 100.0 else 0.95
                    self.silence(src.label, dst_label, ttl=ttl, reason="thermal_silencing")

    def step(self) -> int:
        self._prune_expired()
        self._apply_rhythm_policy()
        self._apply_temperature_policy()
        self._prune_expired()
        return len(self._silenced_edges)

    @property
    def silenced_count(self) -> int:
        self._prune_expired()
        return len(self._silenced_edges)


class CognitionLayer:
    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core
        self.epigenetic_registry = EpigeneticRegistry(core)
        self.last_mean_hyperbolic_distance = 0.0

    def hyperbolic_distance(self, cell_a: AtherCell, cell_b: AtherCell) -> float:
        return poincare_distance(cell_a.poincare_coord, cell_b.poincare_coord)

    def conceptual_proximity_gain(self, cell_a: AtherCell, cell_b: AtherCell) -> float:
        dist = self.hyperbolic_distance(cell_a, cell_b)
        # Near in hyperbolic space => stronger diffusion.
        gain = 0.86 + 0.94 * math.exp(-1.45 * dist)
        return max(0.72, min(1.85, gain))

    def step(self) -> int:
        cells = tuple(self.core.cells.values())
        if len(cells) > 1:
            sampled = []
            max_pairs = min(12, len(cells) * 2)
            for _ in range(max_pairs):
                a, b = random.sample(cells, 2)
                sampled.append(self.hyperbolic_distance(a, b))
            self.last_mean_hyperbolic_distance = sum(sampled) / max(1, len(sampled))
        else:
            self.last_mean_hyperbolic_distance = 0.0
        return self.epigenetic_registry.step()


class EnzymaticOptimizer:
    """
    Atheria_Biosynthesis enzyme layer:
    - Catalase effect: lowers activation energy, compiles hot paths to binary CUDA-like kernels.
    - Protease effect: dissolves malformed logic paths and returns resources.
    """

    def __init__(
        self,
        core: "AtheriaCore",
        *,
        compile_efficiency: float = 0.58,
        compile_usage: int = 6,
        protease_efficiency: float = 0.14,
    ) -> None:
        self.core = core
        self.compile_efficiency = compile_efficiency
        self.compile_usage = compile_usage
        self.protease_efficiency = protease_efficiency
        self.compiled_paths: Dict[str, str] = {}

    def _compile_kernel(self, src: AtherCell, target: AtherCell, conn: AtherConnection) -> None:
        if conn.compiled_kernel:
            return
        is_topo = self.core.topological_logic.is_edge_protected(src.label, target.label)
        kernel_tag = hashlib.sha1(f"{src.label}->{target.label}".encode("utf-8")).hexdigest()[:10]
        prefix = "topo.cuda.bin" if is_topo else "cuda.bin"
        kernel_id = f"{prefix}::{src.label}->{target.label}::{kernel_tag}"
        conn.compiled_kernel = kernel_id
        conn.frozen = True
        if is_topo:
            conn.activation_energy = min(0.04, conn.activation_energy)
            conn.weight = max(0.82, conn.weight)
        else:
            conn.activation_energy = max(0.05, conn.activation_energy * 0.65)
        conn.compute_savings = min(1.0, conn.compute_savings + 0.35)
        self.compiled_paths[f"{src.label}->{target.label}"] = kernel_id

    def _catalase_effect(self, src: AtherCell, conn: AtherConnection) -> None:
        if self.core.topological_logic.is_edge_protected(src.label, conn.target.label):
            conn.frozen = True
            conn.activation_energy = min(0.04, conn.activation_energy)
            conn.weight = max(0.82, conn.weight)
            if conn.compiled_kernel is None:
                self._compile_kernel(src, conn.target, conn)
            return

        interaction = float(conn.usage_count + conn.success_count * 2)
        catalase_level = min(1.0, interaction / 28.0)
        conn.catalytic_flux = 0.82 * conn.catalytic_flux + 0.18 * catalase_level
        conn.activation_energy = max(0.05, conn.activation_energy * (1.0 - 0.05 * catalase_level))
        hot_path = conn.catalytic_flux >= self.core.success_transfer * 0.4
        enough_success = conn.success_count >= 3
        if hot_path and conn.usage_count >= self.compile_usage and (
            conn.efficiency >= self.compile_efficiency or enough_success
        ):
            self._compile_kernel(src, conn.target, conn)

    def _protease_effect(self, src: AtherCell, target_label: str, conn: AtherConnection) -> float:
        if self.core.topological_logic.is_edge_protected(src.label, target_label):
            conn.protease_marks = 0
            return 0.0

        low_resonance = self.core.origami_router.resonance(src, conn.target) < 0.46
        malformed = conn.usage_count >= 8 and conn.efficiency < self.protease_efficiency and low_resonance
        if not malformed:
            conn.protease_marks = max(0, conn.protease_marks - 1)
            return 0.0

        conn.protease_marks += 1
        conn.weight = max(0.01, conn.weight * 0.84)
        conn.activation_energy = min(2.4, conn.activation_energy * 1.06)
        if conn.protease_marks < 3:
            return 0.0

        # Enzymatic decomposition + resource recycling
        reclaimed = 0.75 + conn.weight + conn.compute_savings
        src.remove_connection(target_label)
        return reclaimed

    def step(self) -> float:
        reclaimed_total = 0.0
        for src in tuple(self.core.cells.values()):
            for target_label, conn in tuple(src.connections.items()):
                self._catalase_effect(src, conn)
                reclaimed_total += self._protease_effect(src, target_label, conn)
        return reclaimed_total

    def sleep_cleanup(self, intensity: float = 1.0) -> float:
        reclaimed = 0.0
        purge_threshold = min(0.55, 0.28 + 0.15 * intensity)
        for src in tuple(self.core.cells.values()):
            for target_label, conn in tuple(src.connections.items()):
                if self.core.topological_logic.is_edge_protected(src.label, target_label):
                    continue
                if conn.frozen and conn.efficiency > 0.4:
                    continue
                weak = conn.efficiency < purge_threshold
                sparse_use = conn.usage_count < max(3, int(6 * intensity))
                if weak and sparse_use:
                    reclaimed += 0.4 + conn.weight + conn.compute_savings * 0.5
                    src.remove_connection(target_label)
        return reclaimed


class FieldInference:
    def __init__(self, core: "AtheriaCore") -> None:
        self.core = core

    def infer(self, input_tensor: torch.Tensor, top_k: int = 5) -> Dict[str, object]:
        result = self.core.holographic_field.query_field(
            input_tensor,
            cells=self.core.cells.values(),
            entanglement_registry=self.core.quantum_registry.registry,
            top_k=top_k,
        )
        for entry in result.get("top_matches", []):
            label = entry["label"]
            score = float(entry["score"])
            cell = self.core.cells.get(label)
            if cell and score > 0.35:
                cell.bump_activation(min(0.2, score * 0.2), entangled=True)

        # Anticipatory field projection: pre-activate likely future response zones.
        for entry in result.get("future_top_matches", []):
            label = entry["label"]
            score = float(entry["score"])
            cell = self.core.cells.get(label)
            if cell and score > 0.32:
                cell.bump_activation(min(0.08, score * 0.08), entangled=True)
        return result


class Atheria_Biosynthesis:
    def __init__(self, core: "AtheriaCore", interval: float = 0.2) -> None:
        self.core = core
        self.interval = interval
        self.enzymatic_optimizer = EnzymaticOptimizer(core)
        self.field_inference = FieldInference(core)

    async def run(self) -> None:
        while self.core.running:
            reclaimed = self.enzymatic_optimizer.step()
            if reclaimed > 0.0:
                self.core.assembler.reclaim_resources(reclaimed)
            if self.core.rhythm.state is RhythmState.SLEEP:
                reclaimed_sleep = self.enzymatic_optimizer.sleep_cleanup(intensity=1.15)
                if reclaimed_sleep > 0.0:
                    self.core.assembler.reclaim_resources(reclaimed_sleep)
            await asyncio.sleep(self.interval)


AtheriaBiosynthesis = Atheria_Biosynthesis


class CatalyticAssembler:
    def __init__(
        self,
        core: "AtheriaCore",
        *,
        concentration_threshold: float = 1.8,
        decay: float = 0.92,
        interval: float = 0.35,
    ) -> None:
        self.core = core
        self.concentration_threshold = concentration_threshold
        self.decay = decay
        self.interval = interval
        self.concentrations: Dict[str, float] = {}
        self.resource_pool: float = 3.0
        self.reclaimed_resources: float = 0.0
        self._recent_inputs: Deque[torch.Tensor] = deque(maxlen=32)
        self.autocatalytic_sets: Dict[str, Dict[str, object]] = {}
        self._autocat_counter = 0
        self.autocatalytic_activity: float = 0.0
        self.semantic_analogy_cells = 0
        self.semantic_resource_spent = 0.0
        self.aion_cycles: Dict[str, Dict[str, object]] = {}
        self._aion_counter = 0
        self.aion_cycle_activity = 0.0
        self._last_external_feed_ts = time.perf_counter()
        self.credit_balance: float = 24.0
        self.market_enabled = True
        self.market_need_threshold = 0.52
        self.market_guardian_score = 0.0
        self.market_transactions = 0
        self.market_borrow_events = 0
        self.market_lend_events = 0
        self.market_resources_in = 0.0
        self.market_resources_out = 0.0
        self.market_last_packet_quality = 0.0
        self.market_last_price = 0.0
        self.market_last_partner: Optional[str] = None
        self.last_market_report: Dict[str, Any] = {}
        self._last_market_ts = 0.0

    def feed(
        self,
        category: str,
        relevance: float,
        input_tensor: Optional[torch.Tensor] = None,
        *,
        external: bool = True,
    ) -> None:
        category_key = category.strip() or "Unbekannt"
        self.concentrations[category_key] = self.concentrations.get(category_key, 0.0) + max(0.0, relevance)
        if external:
            self._last_external_feed_ts = time.perf_counter()
        if input_tensor is not None:
            vec = input_tensor.detach().float().flatten()
        else:
            vec = _fold_vector_from_text(category_key, dims=int(self.core.holographic_field.pattern.numel()))
        dims = int(self.core.holographic_field.pattern.numel())
        if vec.numel() < dims:
            vec = torch.nn.functional.pad(vec, (0, dims - vec.numel()))
        elif vec.numel() > dims:
            vec = vec[:dims]
        vec = vec / (torch.norm(vec, p=2) + 1e-8)
        self._recent_inputs.append(vec)

    def reclaim_resources(self, amount: float) -> None:
        gained = max(0.0, float(amount))
        self.reclaimed_resources += gained
        self.resource_pool += gained

    def market_need_score(self) -> float:
        scarcity = _clamp(self.core.ecology.resource_scarcity, 0.0, 1.0)
        heat = _clamp((self.core.phase_controller.system_temperature - 52.0) / 52.0, 0.0, 1.0)
        reserve_pressure = _clamp((9.0 - self.resource_pool) / 9.0, 0.0, 1.0)
        local_entropy = sum(float(v) for v in self.core.phase_controller.local_entropy.values())
        entropy_load = _clamp(math.tanh(local_entropy / 60.0), 0.0, 1.0)
        return _clamp(0.34 * scarcity + 0.28 * heat + 0.22 * entropy_load + 0.16 * reserve_pressure, 0.0, 1.0)

    def guardian_score(self) -> float:
        coolness = 1.0 - _clamp(self.core.phase_controller.system_temperature / 100.0, 0.0, 1.0)
        abundance = math.tanh(max(0.0, self.resource_pool) / 30.0)
        purpose = _clamp(self.core.transcendence.last_purpose_alignment, 0.0, 1.0)
        morphic = _clamp(self.core.holographic_field.last_morphic_resonance_index, 0.0, 1.0)
        survival_bonus = 0.08 if self.core.reproduction.last_artifact_profile == "survival" else 0.0
        score = _clamp(0.35 * coolness + 0.3 * abundance + 0.2 * purpose + 0.15 * morphic + survival_bonus, 0.0, 1.0)
        self.market_guardian_score = score
        return score

    def market_role(self) -> str:
        guardian = self.guardian_score()
        need = self.market_need_score()
        if guardian >= 0.72 and self.resource_pool >= 18.0:
            return "guardian"
        if need >= self.market_need_threshold:
            return "borrower"
        return "balanced"

    def export_efficiency_packet(self) -> Dict[str, Any]:
        kernels: list[str] = []
        top_edges: list[tuple[float, AtherConnection]] = []
        for cell in self.core.cells.values():
            for conn in cell.connections.values():
                score = (conn.efficiency + 0.1) * (1.0 + 0.03 * conn.usage_count)
                top_edges.append((score, conn))
                if conn.compiled_kernel:
                    kernels.append(conn.compiled_kernel)
        top_edges.sort(key=lambda item: item[0], reverse=True)
        entropy_damp_values = [
            float(mech.get("entropy_damp", 0.0)) for mech in self.core.evolution.runtime_mechanisms.values()
        ]
        coherence_gain_values = [
            float(mech.get("coherence_gain", 0.0)) for mech in self.core.evolution.runtime_mechanisms.values()
        ]
        return {
            "source_core_id": self.core.core_id,
            "timestamp": round(time.time(), 6),
            "stability": round(self.guardian_score(), 6),
            "entropy_damp_hint": round(
                sum(entropy_damp_values) / max(1, len(entropy_damp_values)),
                6,
            ),
            "coherence_gain_hint": round(
                sum(coherence_gain_values) / max(1, len(coherence_gain_values)),
                6,
            ),
            "top_edge_energies": [
                round(conn.activation_energy, 6)
                for _, conn in top_edges[:6]
            ],
            "compiled_kernels": sorted(set(kernels))[:8],
            "program_signatures": sorted(
                {
                    str(mech.get("program_signature", ""))
                    for mech in self.core.evolution.runtime_mechanisms.values()
                    if mech.get("program_signature")
                }
            )[:6],
            "field_pattern": self.core.holographic_field.pattern.detach().tolist(),
        }

    def ingest_efficiency_packet(self, packet: Dict[str, Any]) -> float:
        if not isinstance(packet, dict):
            return 0.0

        stability = _clamp(float(packet.get("stability", 0.0)), 0.0, 1.0)
        entropy_damp_hint = _clamp(float(packet.get("entropy_damp_hint", 0.0)), 0.0, 1.0)
        coherence_hint = _clamp(float(packet.get("coherence_gain_hint", 0.0)), 0.0, 1.0)

        tuned = 0
        for cell in self.core.cells.values():
            if not cell.connections:
                continue
            candidates = sorted(
                cell.connections.values(),
                key=lambda conn: (conn.usage_count, conn.efficiency, conn.catalytic_flux),
                reverse=True,
            )
            for conn in candidates[:2]:
                before = conn.activation_energy
                conn.activation_energy = max(0.04, before * (1.0 - 0.06 * stability))
                conn.catalytic_flux = min(1.5, conn.catalytic_flux + 0.03 * stability + 0.02 * coherence_hint)
                if conn.activation_energy < before:
                    tuned += 1

        if self.core.phase_controller.local_entropy:
            damp = 1.0 - 0.12 * entropy_damp_hint
            for key in list(self.core.phase_controller.local_entropy.keys()):
                self.core.phase_controller.local_entropy[key] *= damp

        pattern = packet.get("field_pattern")
        if isinstance(pattern, list) and pattern:
            try:
                vec = torch.tensor(pattern, dtype=torch.float32).flatten()
                dims = int(self.core.holographic_field.pattern.numel())
                if vec.numel() < dims:
                    vec = torch.nn.functional.pad(vec, (0, dims - vec.numel()))
                elif vec.numel() > dims:
                    vec = vec[:dims]
                vec = vec / (torch.norm(vec, p=2) + 1e-8)
                self.core.holographic_field.pattern = torch.tanh(
                    0.93 * self.core.holographic_field.pattern + 0.07 * vec
                )
            except Exception:
                pass

        signatures = packet.get("program_signatures")
        if isinstance(signatures, list):
            for signature in signatures[:2]:
                self.feed(
                    category=f"MarketHint_{str(signature)[:10]}",
                    relevance=min(0.2, 0.06 + 0.1 * stability),
                    input_tensor=self.core.holographic_field.pattern,
                    external=False,
                )

        quality = _clamp(0.45 * stability + 0.35 * entropy_damp_hint + 0.2 * coherence_hint, 0.0, 1.0)
        self.market_last_packet_quality = quality
        return quality

    def transact_with_peer(
        self,
        peer_core: Optional["AtheriaCore"] = None,
        *,
        force: bool = False,
        requested_units: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        report = GLOBAL_ATHER_CREDIT_MARKET.execute_rental(
            borrower=self.core,
            lender=peer_core,
            requested_units=requested_units,
            force=force,
        )
        if report:
            self.last_market_report = report
        return report

    def _resource_market_step(self) -> None:
        if not self.market_enabled:
            return
        if self.core.aion_meditation_mode:
            return
        now = time.perf_counter()
        if (now - self._last_market_ts) < 1.1:
            return
        self._last_market_ts = now
        need = self.market_need_score()
        if need < self.market_need_threshold:
            return
        self.transact_with_peer(force=False)

    def _creative_gap_categories(self) -> list[tuple[str, float]]:
        if not self._recent_inputs:
            return []
        observed = torch.mean(torch.stack(list(self._recent_inputs), dim=0), dim=0)
        field = self.core.holographic_field.pattern
        gap = torch.relu(observed - field)
        gap_norm = float(torch.norm(gap, p=2))
        if gap_norm < 0.2:
            return []
        top_k = min(3, int(gap.numel()))
        top_values, top_indices = torch.topk(gap, k=top_k)
        candidates: list[tuple[str, float]] = []
        for value, idx in zip(top_values.tolist(), top_indices.tolist()):
            if value <= 0.05:
                continue
            category = f"Kreativluecke_{idx}"
            candidates.append((category, float(value) * (1.0 + gap_norm)))
        return candidates

    def _assemble_cell(self, category: str, concentration: float) -> None:
        assembly_cost = max(0.25, 1.1 - concentration * 0.08)
        if self.resource_pool < assembly_cost:
            return
        self.resource_pool -= assembly_cost

        cell = self.core.add_cell(
            category,
            category=category,
            semipermeability=max(0.45, min(0.95, 0.45 + concentration * 0.12)),
        )
        peers = [peer for peer in self.core.cells.values() if peer.label != cell.label]
        peers.sort(key=lambda peer: self.core.origami_router.resonance(cell, peer), reverse=True)
        for peer in peers[:3]:
            resonance = self.core.origami_router.resonance(cell, peer)
            if resonance < 0.6:
                continue
            if peer.label not in cell.connections:
                cell.add_connection(peer, weight=0.25 + 0.55 * resonance)
            if cell.label not in peer.connections and resonance > 0.78:
                peer.add_connection(cell, weight=0.2 + 0.5 * resonance)

    def _semantic_analogy_candidates(self) -> list[tuple[AtherCell, AtherCell, float]]:
        cells = tuple(self.core.cells.values())
        if len(cells) < 2:
            return []
        distance_limit = 1.15 if self.core.aion_meditation_mode else 0.95
        resonance_limit = 0.7 if self.core.aion_meditation_mode else 0.78
        similarity_limit = 0.68 if self.core.aion_meditation_mode else 0.76
        candidates: list[tuple[AtherCell, AtherCell, float]] = []
        for i, src in enumerate(cells):
            for target in cells[i + 1 :]:
                if src.label == target.label:
                    continue
                if src.category == target.category:
                    continue
                if self.core.topological_logic.is_cell_protected(src.label) and self.core.topological_logic.is_cell_protected(
                    target.label
                ):
                    continue
                distance = self.core.cognition.hyperbolic_distance(src, target)
                if distance > distance_limit:
                    continue
                resonance = self.core.origami_router.resonance(src, target)
                if resonance < resonance_limit:
                    continue
                similarity = max(0.0, min(1.0, 0.6 * resonance + 0.4 * (1.0 / (1.0 + distance))))
                if similarity < similarity_limit:
                    continue
                candidates.append((src, target, similarity))
        candidates.sort(key=lambda item: item[2], reverse=True)
        return candidates[:2]

    def _assemble_semantic_analog(self, src: AtherCell, target: AtherCell, similarity: float) -> None:
        label = f"Analog_{src.label}_{target.label}"
        if label in self.core.cells:
            return
        cost = max(0.3, 0.95 - similarity * 0.4)
        if self.resource_pool < cost:
            return
        self.resource_pool -= cost
        self.semantic_resource_spent += cost

        category = f"Analogy::{src.category}~{target.category}"
        analog = self.core.add_cell(
            label,
            category=category,
            semipermeability=max(0.5, min(0.96, (src.semipermeability + target.semipermeability) * 0.55)),
        )
        analog.fold_signature = (
            0.5 * src.fold_signature + 0.5 * target.fold_signature
        ) / (torch.norm(0.5 * src.fold_signature + 0.5 * target.fold_signature, p=2) + 1e-8)
        midpoint = 0.5 * src.poincare_coord + 0.5 * target.poincare_coord
        analog.poincare_coord = _project_to_poincare_ball(midpoint)

        analog.add_connection(src, weight=0.5 + 0.4 * similarity)
        analog.add_connection(target, weight=0.5 + 0.4 * similarity)
        src.add_connection(analog, weight=0.42 + 0.36 * similarity)
        target.add_connection(analog, weight=0.42 + 0.36 * similarity)
        self.semantic_analogy_cells += 1

    def _set_exists(self, members: Set[str]) -> bool:
        for existing in self.autocatalytic_sets.values():
            if set(existing["members"]) == members:
                return True
        return False

    def _register_autocatalytic_set(self, members: Set[str], catalyst: float) -> None:
        if len(members) < 2 or self._set_exists(members):
            return
        self._autocat_counter += 1
        set_id = f"AUTOSET_{self._autocat_counter:03d}"
        potency = max(0.3, min(1.0, catalyst))
        self.autocatalytic_sets[set_id] = {
            "members": sorted(members),
            "potency": potency,
            "age": 0,
        }

    def _grow_autocatalytic_sets(self) -> None:
        cells = tuple(self.core.cells.values())
        if len(cells) < 2:
            return

        pair_scores: list[tuple[float, AtherCell, AtherCell]] = []
        for i, src in enumerate(cells):
            for target in cells[i + 1 :]:
                if self.core.topological_logic.is_edge_protected(src.label, target.label):
                    continue
                if self.core.topological_logic.is_edge_protected(target.label, src.label):
                    continue
                resonance = self.core.origami_router.resonance(src, target)
                if resonance < 0.72:
                    continue
                src_conn = src.connections.get(target.label)
                dst_conn = target.connections.get(src.label)
                flux = 0.0
                if src_conn:
                    flux += src_conn.catalytic_flux
                if dst_conn:
                    flux += dst_conn.catalytic_flux
                score = resonance * (1.0 + flux)
                pair_scores.append((score, src, target))

        if not pair_scores:
            return
        pair_scores.sort(key=lambda item: item[0], reverse=True)
        top_pairs = pair_scores[:2]

        for score, src, target in top_pairs:
            members = {src.label, target.label}
            if self._set_exists(members):
                continue
            if target.label not in src.connections:
                src.add_connection(target, weight=0.74)
            if src.label not in target.connections:
                target.add_connection(src, weight=0.74)
            src_conn = src.connections[target.label]
            tgt_conn = target.connections[src.label]
            src_conn.activation_energy = max(0.05, src_conn.activation_energy * 0.72)
            tgt_conn.activation_energy = max(0.05, tgt_conn.activation_energy * 0.72)
            self._register_autocatalytic_set(members, catalyst=min(1.0, score))

    def _autocatalytic_maintenance(self) -> None:
        if self.core.aion_meditation_mode:
            self.autocatalytic_activity *= 0.95
            return
        if not self.autocatalytic_sets:
            self.autocatalytic_activity *= 0.9
            return

        total_concentration = sum(self.concentrations.values())
        external_quiet = total_concentration < 0.2
        maintenance_gain = 0.0

        for set_id in list(self.autocatalytic_sets.keys()):
            data = self.autocatalytic_sets[set_id]
            members = [self.core.cells[label] for label in data["members"] if label in self.core.cells]
            if len(members) < 2:
                self.autocatalytic_sets.pop(set_id, None)
                continue

            potency = float(data["potency"])
            data["age"] = int(data["age"]) + 1

            if external_quiet:
                pulse = min(0.06, 0.015 + potency * 0.05)
                for idx, cell in enumerate(members):
                    target = members[(idx + 1) % len(members)]
                    cell.bump_activation(pulse, source=target)
                    conn = cell.connections.get(target.label)
                    if conn:
                        conn.catalytic_flux = min(1.5, conn.catalytic_flux + pulse)
                        conn.success_count += 1
                        conn.usage_count += 1
                self.core.phase_controller.structural_tension = min(
                    1.0,
                    self.core.phase_controller.structural_tension + 0.01 * potency,
                )
                maintenance_gain += pulse * len(members)

            data["potency"] = max(0.15, min(1.0, potency * 0.997 + 0.003))
            if int(data["age"]) > 1200 and float(data["potency"]) < 0.2:
                self.autocatalytic_sets.pop(set_id, None)

        self.autocatalytic_activity = 0.85 * self.autocatalytic_activity + 0.15 * maintenance_gain

    def _quiet_duration(self) -> float:
        return max(0.0, time.perf_counter() - self._last_external_feed_ts)

    def _register_aion_cycle(self, members: list[str], stability: float) -> None:
        if len(members) < 3:
            return
        self._aion_counter += 1
        cycle_id = f"AION_{self._aion_counter:03d}"
        self.aion_cycles[cycle_id] = {
            "members": list(members),
            "stability": max(0.25, min(1.0, stability)),
            "age": 0,
        }

    def _grow_aion_cycles(self) -> None:
        quiet = self._quiet_duration()
        if quiet < 1.15:
            return
        if self.resource_pool < 0.9:
            return
        if len(self.aion_cycles) >= 5:
            return

        candidate_pool: list[str] = []
        for meta in self.autocatalytic_sets.values():
            candidate_pool.extend(meta["members"])
        if not candidate_pool:
            candidate_pool.extend(
                [label for label, cell in self.core.cells.items() if cell.label != self.core.aion.singularity_label]
            )

        deduped = []
        for label in candidate_pool:
            if label in self.core.cells and label not in deduped:
                deduped.append(label)
        if len(deduped) < 3:
            return

        members = deduped[:3]
        base_res = []
        for label in members:
            cell = self.core.cells[label]
            base_res.append(1.0 / (1.0 + float(torch.norm(cell.poincare_coord, p=2))))
        stability = sum(base_res) / max(1, len(base_res))
        self._register_aion_cycle(members, stability=stability)
        self.resource_pool -= 0.6

        for idx, src_label in enumerate(members):
            dst_label = members[(idx + 1) % len(members)]
            src = self.core.cells[src_label]
            dst = self.core.cells[dst_label]
            if dst_label not in src.connections:
                src.add_connection(dst, weight=0.68)
            conn = src.connections[dst_label]
            conn.frozen = True
            conn.activation_energy = max(0.05, conn.activation_energy * 0.74)
            conn.catalytic_flux = min(1.5, conn.catalytic_flux + 0.08)

    def _maintain_aion_cycles(self) -> None:
        if self.core.aion_meditation_mode:
            self.aion_cycle_activity *= 0.95
            return
        if not self.aion_cycles:
            self.aion_cycle_activity *= 0.9
            return

        quiet = self._quiet_duration()
        gain = 0.0
        for cycle_id in list(self.aion_cycles.keys()):
            data = self.aion_cycles[cycle_id]
            members = [self.core.cells[label] for label in data["members"] if label in self.core.cells]
            if len(members) < 3:
                self.aion_cycles.pop(cycle_id, None)
                continue

            stability = float(data["stability"])
            data["age"] = int(data["age"]) + 1
            pulse = min(0.08, 0.012 + stability * (0.03 if quiet >= 0.8 else 0.015))
            for idx, cell in enumerate(members):
                nxt = members[(idx + 1) % len(members)]
                cell.bump_activation(pulse, source=nxt, entangled=True)
                conn = cell.connections.get(nxt.label)
                if conn:
                    conn.usage_count += 1
                    conn.success_count += 1
                    conn.catalytic_flux = min(1.5, conn.catalytic_flux + pulse)
                    conn.frozen = True
                    conn.activation_energy = max(0.045, conn.activation_energy * 0.985)
                cell.integrity_rate = min(1.0, cell.integrity_rate + 0.008 + 0.01 * stability)
                gain += pulse

            if quiet >= 0.8:
                data["stability"] = min(1.0, stability + 0.004)
            else:
                data["stability"] = max(0.2, stability * 0.997)

            if int(data["age"]) > 1800 and float(data["stability"]) < 0.24:
                self.aion_cycles.pop(cycle_id, None)

        self.aion_cycle_activity = 0.84 * self.aion_cycle_activity + 0.16 * gain

    def step(self) -> None:
        self._resource_market_step()
        for category, gap_boost in self._creative_gap_categories():
            self.concentrations[category] = self.concentrations.get(category, 0.0) + gap_boost

        if not self.concentrations:
            self._grow_aion_cycles()
            self._grow_autocatalytic_sets()
            self._autocatalytic_maintenance()
            self._maintain_aion_cycles()
            return
        for category in list(self.concentrations.keys()):
            concentration = self.concentrations.get(category, 0.0)
            if concentration >= self.concentration_threshold:
                self._assemble_cell(category, concentration)
                self.concentrations[category] = concentration * 0.38
            else:
                self.concentrations[category] = concentration * self.decay
            if self.concentrations[category] < 0.05:
                self.concentrations.pop(category, None)

        for src, target, similarity in self._semantic_analogy_candidates():
            self._assemble_semantic_analog(src, target, similarity)

        self._grow_aion_cycles()
        self._grow_autocatalytic_sets()
        self._autocatalytic_maintenance()
        self._maintain_aion_cycles()

    async def run(self) -> None:
        while self.core.running:
            self.step()
            await asyncio.sleep(self.interval)


class PhaseController:
    def __init__(self, base_temperature: float = 25.0) -> None:
        self.system_temperature = base_temperature
        self._external_delta = 0.0
        self.local_entropy: Dict[str, float] = {}
        self.structural_tension: float = 0.0
        self.last_tensegrity_support: int = 0
        self.logging_enabled = True

    @property
    def current_state(self) -> AggregateState:
        if self.system_temperature < 40.0:
            return AggregateState.SOLID
        if self.system_temperature < 80.0:
            return AggregateState.LIQUID
        return AggregateState.PLASMA

    def inject_temperature(self, delta: float) -> None:
        self._external_delta += delta

    def spike_local_entropy(self, label: str, magnitude: float = 20.0) -> None:
        self.local_entropy[label] = self.local_entropy.get(label, 0.0) + magnitude

    def update(
        self,
        *,
        active_nodes: int,
        total_nodes: int,
        cpu_load: float,
        modulators: NeuroModulators,
    ) -> float:
        global System_Temperature

        active_ratio = active_nodes / max(1, total_nodes)
        entropy_heat = sum(self.local_entropy.values()) * 0.08
        target = (
            22.0
            + cpu_load * 0.35
            + active_ratio * 48.0
            + entropy_heat
            + modulators.adrenaline * 9.5
            - modulators.serotonin * 8.0
            + self._external_delta
        )
        self.system_temperature = max(0.0, min(120.0, 0.82 * self.system_temperature + 0.18 * target))
        self._external_delta = 0.0

        self.local_entropy = {
            label: entropy * 0.9
            for label, entropy in self.local_entropy.items()
            if entropy * 0.9 > 0.1
        }

        if self.current_state is AggregateState.PLASMA:
            instability = min(1.0, max(0.0, (self.system_temperature - 80.0) / 40.0))
            self.structural_tension = min(1.0, 0.78 * self.structural_tension + 0.22 * (0.45 + instability))
        else:
            self.structural_tension = max(0.0, self.structural_tension * 0.9)

        self.logging_enabled = self.current_state is not AggregateState.PLASMA
        System_Temperature = self.system_temperature
        return self.system_temperature

    def apply_tensegrity(
        self,
        cells: Iterable[AtherCell],
        origami_router: OrigamiRouter,
        topological_logic: Optional[TopologicalLogic] = None,
    ) -> int:
        """
        Tensegrity_Logic:
        in plasma the system keeps mechanical code tension and reinforces highly resonant paths.
        """
        if self.current_state is not AggregateState.PLASMA:
            self.last_tensegrity_support = 0
            return 0

        edges: list[tuple[float, AtherCell, AtherConnection]] = []
        for src in cells:
            for conn in src.connections.values():
                resonance = origami_router.resonance(src, conn.target)
                edges.append((resonance, src, conn))

        if not edges:
            self.last_tensegrity_support = 0
            return 0

        edges.sort(key=lambda item: item[0], reverse=True)
        support_budget = max(1, int(1 + self.structural_tension * 6))
        supported = 0

        for resonance, src, conn in edges[:support_budget]:
            if topological_logic and topological_logic.is_edge_protected(src.label, conn.target.label):
                conn.frozen = True
                conn.activation_energy = min(0.04, conn.activation_energy)
                conn.weight = max(0.82, conn.weight)
                supported += 1
                continue
            conn.frozen = True
            conn.weight = min(1.8, conn.weight + 0.03 * resonance)
            conn.activation_energy = max(0.04, conn.activation_energy * (1.0 - 0.08 * resonance))
            src.integrity_rate = min(1.0, src.integrity_rate + 0.018 + 0.02 * self.structural_tension)
            conn.target.integrity_rate = min(
                1.0,
                conn.target.integrity_rate + 0.012 + 0.016 * self.structural_tension,
            )
            supported += 1

        self.last_tensegrity_support = supported
        return supported


class QuantumRegistry:
    """Observer-based immediate synchronization."""

    def __init__(self) -> None:
        self.registry = Entanglement_Registry

    def entangle(self, var_a: AtherCell, var_b: AtherCell) -> None:
        self.registry.setdefault(var_a.label, set()).add(var_b.label)
        self.registry.setdefault(var_b.label, set()).add(var_a.label)

        def sync_a_to_b(value: float, emitter: AtherCell, source: Optional[AtherCell], _entangled: bool) -> None:
            if emitter is not var_a:
                return
            if source is var_b:
                return
            var_b.set_activation(value, source=var_a, entangled=True)

        def sync_b_to_a(value: float, emitter: AtherCell, source: Optional[AtherCell], _entangled: bool) -> None:
            if emitter is not var_b:
                return
            if source is var_a:
                return
            var_a.set_activation(value, source=var_b, entangled=True)

        var_a.watch(sync_a_to_b)
        var_b.watch(sync_b_to_a)


def entangle(var_a: AtherCell, var_b: AtherCell, registry: Optional[QuantumRegistry] = None) -> None:
    (registry or QuantumRegistry()).entangle(var_a, var_b)


class AtherHealing:
    def __init__(
        self,
        core: "AtheriaCore",
        *,
        integrity_threshold: float = 0.35,
        silent_limit: int = 20,
        error_limit: int = 3,
        interval: float = 0.25,
    ) -> None:
        self.core = core
        self.integrity_threshold = integrity_threshold
        self.silent_limit = silent_limit
        self.error_limit = error_limit
        self.interval = interval
        self.healing_events = 0
        self.last_repaired_labels: Deque[str] = deque(maxlen=16)

    def detect_necrosis(self, cell: AtherCell) -> bool:
        if self.core.topological_logic.is_cell_protected(cell.label):
            cell.integrity_rate = max(0.995, cell.integrity_rate)
            cell.error_counter = max(0, cell.error_counter - 1)
            return False
        return (
            cell.integrity_rate < self.integrity_threshold
            or cell.silent_epochs >= self.silent_limit
            or cell.error_counter >= self.error_limit
        )

    def handle_crash(self, cell: AtherCell, exc: Exception) -> None:
        if self.core.topological_logic.is_cell_protected(cell.label):
            cell.integrity_rate = max(0.995, cell.integrity_rate)
            logger.error("Crash in protected topological cell '%s': %s | runtime stayed deterministic", cell.label, exc)
            return
        cell.record_error()
        self.core.phase_controller.spike_local_entropy(cell.label, magnitude=35.0)
        self._rewrite_cell_runtime(cell)
        logger.error("Crash in cell '%s': %s", cell.label, exc)

    def _rewrite_cell_runtime(self, cell: AtherCell) -> None:
        async def safe_diffuse(this_cell: AtherCell, core: "AtheriaCore") -> int:
            this_cell.integrity_rate = min(1.0, this_cell.integrity_rate + 0.03)
            if this_cell.activation_value < 0.02:
                this_cell.set_activation(0.02)
            return 0

        cell.diffuse_process = types.MethodType(safe_diffuse, cell)

    def _select_donor(self, candidates: Iterable[AtherCell], excluded_label: str) -> Optional[AtherCell]:
        healthy = [
            cell
            for cell in candidates
            if cell.label != excluded_label and not cell.is_necrotic and cell.integrity_rate > 0.6
        ]
        if not healthy:
            return None
        return max(
            healthy,
            key=lambda cell: (sum(cell.activation_history) + cell.integrity_rate * 10.0),
        )

    async def repair(self, necrotic: AtherCell) -> None:
        if necrotic.is_necrotic:
            return
        necrotic.is_necrotic = True
        self.core.phase_controller.spike_local_entropy(necrotic.label, magnitude=45.0)

        incoming: list[Tuple[AtherCell, float]] = []
        for cell in self.core.cells.values():
            if necrotic.label in cell.connections:
                incoming.append((cell, cell.connections[necrotic.label].weight))
                cell.remove_connection(necrotic.label)

        necrotic.connections.clear()
        donor = self._select_donor((src for src, _ in incoming), excluded_label=necrotic.label)
        if donor is None:
            donor = self._select_donor(self.core.cells.values(), excluded_label=necrotic.label)
        if donor is None:
            self.core.holographic_field.reconstruct(necrotic)
            necrotic.integrity_rate = max(0.5, necrotic.integrity_rate)
            necrotic.is_necrotic = False
            return

        donor_semipermeability, donor_weights = donor.blueprint()
        necrotic.semipermeability = donor_semipermeability
        necrotic.activation_history = deque(donor.activation_history, maxlen=128)
        necrotic.set_activation(max(0.1, donor.activation_value * 0.7), source=donor)

        for target_label, weight in donor_weights.items():
            target = self.core.cells.get(target_label)
            if target is None or target.label == necrotic.label:
                continue
            necrotic.add_connection(target, weight=weight)

        for src, in_weight in incoming:
            src.add_connection(necrotic, weight=max(0.05, in_weight))

        # Osmotic injection from donor to reconstructed area.
        donor.bump_activation(0.12)
        donor.add_connection(necrotic, weight=0.9)

        necrotic.error_counter = 0
        necrotic.silent_epochs = 0
        necrotic.integrity_rate = 0.92
        necrotic.is_necrotic = False
        self.healing_events += 1
        self.last_repaired_labels.append(necrotic.label)
        self.core.aether.upsert_cell(necrotic)

    async def run(self) -> None:
        while self.core.running:
            for cell in tuple(self.core.cells.values()):
                if self.detect_necrosis(cell):
                    await self.repair(cell)
            await asyncio.sleep(self.interval)


class AtheriaCore:
    def __init__(self, tick_interval: float = 0.05, modulators: Optional[NeuroModulators] = None) -> None:
        self.core_id = f"ATHERIA_CORE_{uuid.uuid4().hex[:10].upper()}"
        self.population_registry = GLOBAL_CORE_REGISTRY
        self.global_morphic_node = GLOBAL_MORPHIC_NODE
        self.global_credit_market = GLOBAL_ATHER_CREDIT_MARKET
        self.cells: Dict[str, AtherCell] = {}
        self.aether = AtherAether()
        self.phase_controller = PhaseController()
        self.quantum_registry = QuantumRegistry()
        self.origami_router = OrigamiRouter()
        self.holographic_field = HolographicField(dims=12)
        self.entropic_folding = EntropicFoldingAlgorithm(self.phase_controller, self.origami_router)
        self.modulators = modulators or GLOBAL_NEUROTRANSMITTERS
        self.healing = AtherHealing(self)
        self.assembler = CatalyticAssembler(self)
        self.topological_logic = TopologicalLogic(self)
        self.cognition = CognitionLayer(self)
        self.aion = AionLayer(self)
        self.transcendence = TranscendenceLayer(self)
        self.evolution = EvolutionEngine(self)
        self.symbiosis = SymbiosisLayer(self)
        self.llm_sleep_rewriter = LLMSleepRewriter(self)
        self.reproduction = SelfReproductionEngine(self)
        self.ecology = EcoDynamicsEngine(self)
        self.biosynthesis = Atheria_Biosynthesis(self)
        self.rhythm = Atheria_Rhythm(self)

        self.tick_interval = tick_interval
        self.running = False
        self._tasks: list[asyncio.Task] = []
        self._last_tick = time.perf_counter()
        self._flow_count = 0
        self._fold_tick = 0

        self.min_transfer = 0.0005
        self.success_transfer = 0.03
        self.aion_meditation_mode = False
        self.external_feeds_enabled = True
        self._meditation_history: Deque[Dict[str, float]] = deque(maxlen=4096)
        self._last_morphic_snapshot_path: Optional[str] = None

    def add_cell(
        self,
        label: str,
        *,
        semipermeability: float = 0.7,
        category: Optional[str] = None,
        archetype: str = "baseline",
        archetype_traits: Optional[Dict[str, float]] = None,
    ) -> AtherCell:
        if label in self.cells:
            return self.cells[label]
        cell = AtherCell(
            label=label,
            category=category or label,
            semipermeability=semipermeability,
            archetype=archetype,
            archetype_traits=archetype_traits or {},
        )
        self.cells[label] = cell
        self.aether.upsert_cell(cell)
        return cell

    def connect(self, source_label: str, target_label: str, weight: Optional[float] = None) -> None:
        source = self.cells[source_label]
        target = self.cells[target_label]
        source.add_connection(target, weight=weight)

    def entangle(self, label_a: str, label_b: str) -> None:
        self.quantum_registry.entangle(self.cells[label_a], self.cells[label_b])

    def _allow_external_feed(self) -> bool:
        return self.external_feeds_enabled and not self.aion_meditation_mode

    def inject_signal(self, label: str, activation: float) -> None:
        if not self._allow_external_feed():
            return
        adjusted = self.rhythm.filter_input(activation)
        if adjusted < 0.002:
            return
        self.cells[label].set_activation(adjusted)

    def set_superposition(self, label: str, alpha: float = 0.7071, beta: float = 0.7071, enzyme: float = 0.92) -> None:
        if not self._allow_external_feed():
            return
        self.cells[label].set_superposition(alpha=alpha, beta=beta, enzyme=enzyme)

    def chemical_measure(self, label: str, probe: float = 0.5) -> float:
        return self.cells[label].chemical_measurement(probe=probe)

    def feed_raw_material(self, *, category: str, relevance: float) -> None:
        if not self._allow_external_feed():
            return
        adjusted = relevance * self.rhythm.input_gain
        if adjusted <= 0.01:
            return
        self.assembler.feed(category=category, relevance=adjusted)

    def feed_field_material(self, *, category: str, relevance: float, input_tensor: torch.Tensor) -> None:
        if not self._allow_external_feed():
            return
        adjusted = relevance * self.rhythm.input_gain
        if adjusted <= 0.01:
            return
        self.assembler.feed(category=category, relevance=adjusted, input_tensor=input_tensor)

    def field_query(self, input_tensor: torch.Tensor, top_k: int = 5) -> Dict[str, object]:
        if self.aion_meditation_mode:
            # Isolation mode: allow read-only introspection without external activation injection.
            return self.holographic_field.query_field(
                input_tensor=torch.zeros_like(input_tensor),
                cells=self.cells.values(),
                entanglement_registry=self.quantum_registry.registry,
                top_k=top_k,
            )
        return self.biosynthesis.field_inference.infer(input_tensor=input_tensor, top_k=top_k)

    def hyperbolic_distance(self, label_a: str, label_b: str) -> float:
        return self.cognition.hyperbolic_distance(self.cells[label_a], self.cells[label_b])

    def discover_peer_cores(self, *, running_only: bool = True) -> list[str]:
        return [core.core_id for core in self.population_registry.peers(self.core_id, running_only=running_only)]

    def system_stress_index(self) -> float:
        heat = _clamp((self.phase_controller.system_temperature - 50.0) / 60.0, 0.0, 1.0)
        local_entropy = sum(float(v) for v in self.phase_controller.local_entropy.values())
        entropy_load = _clamp(math.tanh(local_entropy / 60.0), 0.0, 1.0)
        scarcity = _clamp(self.ecology.resource_scarcity, 0.0, 1.0)
        if self.cells:
            integrity_deficit = _clamp(
                sum(1.0 - _clamp(cell.integrity_rate, 0.0, 1.0) for cell in self.cells.values()) / len(self.cells),
                0.0,
                1.0,
            )
            error_load = _clamp(
                sum(min(6, cell.error_counter) for cell in self.cells.values()) / (len(self.cells) * 6.0),
                0.0,
                1.0,
            )
        else:
            integrity_deficit = 0.0
            error_load = 0.0
        return _clamp(
            0.32 * heat + 0.22 * entropy_load + 0.2 * scarcity + 0.16 * integrity_deficit + 0.1 * error_load,
            0.0,
            1.0,
        )

    def force_reproduction(self) -> Optional[str]:
        return self.reproduction.force_reproduction()

    async def exchange_genes_with(self, peer_core: "AtheriaCore", *, reciprocal: bool = True) -> bool:
        return await self.symbiosis.exchange_with(peer_core, reciprocal=reciprocal)

    def request_resource_rental(
        self,
        peer_core: Optional["AtheriaCore"] = None,
        *,
        requested_units: Optional[float] = None,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        return self.assembler.transact_with_peer(
            peer_core,
            force=force,
            requested_units=requested_units,
        )

    async def trigger_sleep_phase_rewrite(
        self,
        *,
        replay_labels: Optional[Iterable[str]] = None,
        replay_strength: Optional[float] = None,
    ) -> bool:
        labels = list(replay_labels or self.rhythm.last_replay_labels)
        strength = (
            float(replay_strength)
            if replay_strength is not None
            else _clamp(self.holographic_field.last_uncertainty + 0.22, 0.0, 1.0)
        )
        return await self.llm_sleep_rewriter.try_sleep_rewrite(
            replay_labels=labels,
            replay_strength=strength,
        )

    def trigger_collective_dream_sync(self) -> bool:
        before = self.rhythm.inter_core_dream_sync_events
        replay_strength = _clamp(self.holographic_field.last_uncertainty + 0.2, 0.0, 1.0)
        self.rhythm._inter_core_dream_sync(
            replay_labels=list(self.rhythm.last_replay_labels),
            replay_strength=replay_strength,
        )
        return self.rhythm.inter_core_dream_sync_events > before

    def dashboard_snapshot(self) -> Dict[str, object]:
        topo = self.topological_logic.snapshot()
        return {
            "aether_density": self.aether.density(),
            "aggregatform": self.phase_controller.current_state.dashboard_name,
            "phase": self.phase_controller.current_state.value,
            "system_temperature": round(self.phase_controller.system_temperature, 2),
            "rhythm_state": self.rhythm.state.value,
            "rhythm_cycle": self.rhythm.cycle_count,
            "structural_tension": round(self.phase_controller.structural_tension, 4),
            "tensegrity_support": self.phase_controller.last_tensegrity_support,
            "active_cells": sum(1 for cell in self.cells.values() if cell.activation_value > 0.02),
            "entropic_index": round(self.entropic_folding.last_index, 4),
            "holographic_energy": round(self.holographic_field.energy, 4),
            "enzymatic_compiled_paths": len(self.biosynthesis.enzymatic_optimizer.compiled_paths),
            "resource_pool": round(self.assembler.resource_pool, 4),
            "ather_credits": round(self.assembler.credit_balance, 4),
            "market_role": self.assembler.market_role(),
            "market_guardian_score": round(self.assembler.market_guardian_score, 6),
            "market_transactions": self.assembler.market_transactions,
            "market_borrow_events": self.assembler.market_borrow_events,
            "market_lend_events": self.assembler.market_lend_events,
            "market_resources_in": round(self.assembler.market_resources_in, 6),
            "market_resources_out": round(self.assembler.market_resources_out, 6),
            "market_last_price": round(self.assembler.market_last_price, 6),
            "market_last_partner": self.assembler.market_last_partner,
            "market_last_packet_quality": round(self.assembler.market_last_packet_quality, 6),
            "autocatalytic_sets": len(self.assembler.autocatalytic_sets),
            "autocatalytic_activity": round(self.assembler.autocatalytic_activity, 6),
            "aion_cycles": len(self.assembler.aion_cycles),
            "aion_cycle_activity": round(self.assembler.aion_cycle_activity, 6),
            "semantic_analogy_cells": self.assembler.semantic_analogy_cells,
            "semantic_resource_spent": round(self.assembler.semantic_resource_spent, 6),
            "evolved_cell_types": max(0, len(self.evolution.cell_type_blueprints) - 1),
            "evolved_runtime_mechanisms": len(self.evolution.runtime_mechanisms),
            "evolution_events": self.evolution.evolution_events,
            "evolution_program_signature": self.evolution.last_program_signature,
            "reproduction_events": self.reproduction.reproduction_events,
            "offspring_instances": len(self.reproduction.offspring_cores),
            "lineage_selection_trials": self.reproduction.selection_total_trials,
            "lineage_selection_child_wins": self.reproduction.selection_child_wins,
            "lineage_selection_parent_wins": self.reproduction.selection_parent_wins,
            "lineage_last_parent_fitness": round(self.reproduction.last_parent_fitness, 6),
            "lineage_last_child_fitness": round(self.reproduction.last_child_fitness, 6),
            "reproduction_artifact_events": self.reproduction.artifact_events,
            "reproduction_artifact_last_profile": self.reproduction.last_artifact_profile,
            "reproduction_artifact_last_path": self.reproduction.last_artifact_path,
            "reproduction_artifact_last_integrity_path": self.reproduction.last_artifact_integrity_path,
            "reproduction_artifact_last_validated": self.reproduction.last_artifact_validated,
            "reproduction_artifact_last_signature": self.reproduction.last_artifact_signature,
            "ecological_complexity": round(self.ecology.challenge_complexity, 6),
            "selection_pressure": round(self.ecology.selection_pressure, 6),
            "resource_scarcity": round(self.ecology.resource_scarcity, 6),
            "fitness_gradient": round(self.ecology.last_fitness_gradient, 6),
            "epigenetic_silenced_edges": self.cognition.epigenetic_registry.silenced_count,
            "mean_hyperbolic_distance": round(self.cognition.last_mean_hyperbolic_distance, 6),
            "dream_replay_events": self.rhythm.dream_replay_events,
            "dream_last_replay_labels": list(self.rhythm.last_replay_labels),
            "healing_events": self.healing.healing_events,
            "healing_last_repaired_labels": list(self.healing.last_repaired_labels),
            "time_crystal_energy": round(self.aion.time_crystal.last_crystal_energy, 6),
            "time_crystal_targets": len(self.aion.time_crystal.oscillators),
            "singularity_activation": round(self.aion.last_singularity_activation, 6),
            "morphic_resonance_index": round(self.holographic_field.last_morphic_resonance_index, 6),
            "morphic_buffer_states": self.holographic_field.morphic_buffer.size,
            "intuition_spikes": self.transcendence.intuition.last_spikes,
            "purpose_alignment": round(self.transcendence.last_purpose_alignment, 6),
            "llm_sleep_rewriter_enabled": self.llm_sleep_rewriter.enabled,
            "llm_rewrite_attempts": self.llm_sleep_rewriter.attempts,
            "llm_rewrite_accepts": self.llm_sleep_rewriter.accepts,
            "llm_rewrite_rejects": self.llm_sleep_rewriter.rejects,
            "llm_rewrite_errors": self.llm_sleep_rewriter.errors,
            "llm_alias_updates": self.llm_sleep_rewriter.alias_updates,
            "llm_last_model": self.llm_sleep_rewriter.last_model_id,
            "llm_last_reason": self.llm_sleep_rewriter.last_reason,
            "llm_last_error": self.llm_sleep_rewriter.last_error,
            "llm_last_program_signature": self.llm_sleep_rewriter.last_program_signature,
            "llm_last_predicted_purpose_delta": round(self.llm_sleep_rewriter.last_predicted_delta, 6),
            "llm_trace_events": self.llm_sleep_rewriter.trace_events,
            "llm_trace_path": self.llm_sleep_rewriter.last_trace_path,
            "hgt_offers": self.symbiosis.hgt_offers,
            "hgt_accepts": self.symbiosis.hgt_accepts,
            "hgt_rejects": self.symbiosis.hgt_rejects,
            "hgt_received": self.symbiosis.hgt_received,
            "hgt_donated": self.symbiosis.hgt_donated,
            "hgt_last_partner": self.symbiosis.last_partner,
            "hgt_last_predicted_purpose_delta": round(self.symbiosis.last_predicted_purpose_delta, 6),
            "inter_core_dream_sync_events": self.rhythm.inter_core_dream_sync_events,
            "inter_core_dream_trauma_events": self.rhythm.inter_core_dream_trauma_events,
            "inter_core_dream_peers": self.rhythm.last_inter_core_peer_count,
            "inter_core_dream_coherence": round(self.rhythm.last_inter_core_coherence, 6),
            "inter_core_dream_trauma_intensity": round(self.rhythm.last_inter_core_trauma_intensity, 6),
            "global_population_size": self.population_registry.count(running_only=True),
            "global_morphic_sync_events": self.global_morphic_node.sync_events,
            "global_trauma_broadcast_events": self.global_morphic_node.trauma_broadcast_events,
            "global_market_transactions": len(self.global_credit_market.transactions),
            "global_market_last_price": round(self.global_credit_market.last_price_per_unit, 6),
            "system_stress_index": round(self.system_stress_index(), 6),
            "purpose_homeostatic_temperature": round(
                float(getattr(self.cells.get(self.transcendence.telos.purpose_label), "homeostatic_temperature", 34.0)),
                6,
            ),
            "aion_meditation_mode": self.aion_meditation_mode,
            "topological_clusters": topo["clusters"],
            "topological_core_cells": topo["core_cells"],
            "topological_edges": topo["protected_edges"],
            "entanglement_registry": {k: sorted(v) for k, v in self.quantum_registry.registry.items()},
        }

    def _topological_core_labels(self) -> list[str]:
        core_labels: Set[str] = set()
        for cluster in self.topological_logic.clusters.values():
            core_labels.update(cluster["core"])
        return sorted(core_labels)

    def _meditation_holy_geometry(self) -> None:
        if not self.aion_meditation_mode:
            return
        core_labels = set(self._topological_core_labels())
        for label in core_labels:
            cell = self.cells.get(label)
            if cell is None:
                continue
            cell.integrity_rate = max(0.995, cell.integrity_rate)
            cell.error_counter = max(0, cell.error_counter - 1)

        excluded = core_labels | {self.aion.singularity_label, self.transcendence.telos.purpose_label}
        mutable = [cell for cell in self.cells.values() if cell.label not in excluded]
        if len(mutable) < 2:
            return

        coords = torch.stack([cell.poincare_coord for cell in mutable], dim=0)
        centroid = torch.mean(coords, dim=0)
        centroid = _project_to_poincare_ball(centroid)
        field_hint = self.holographic_field.pattern[:POINCARE_DIMS]
        field_hint = field_hint / (torch.norm(field_hint, p=2) + 1e-8)
        field_hint = _project_to_poincare_ball(field_hint * 0.72)

        for cell in mutable:
            blended = 0.82 * cell.poincare_coord + 0.14 * centroid + 0.04 * field_hint
            cell.poincare_coord = _project_to_poincare_ball(blended)
            fold = cell.fold_signature.detach().clone()
            coord_hint = torch.nn.functional.pad(cell.poincare_coord, (0, max(0, fold.numel() - cell.poincare_coord.numel())))
            fold = 0.93 * fold + 0.07 * coord_hint[: fold.numel()]
            cell.fold_signature = fold / (torch.norm(fold, p=2) + 1e-8)
            cell.semipermeability = max(0.45, min(0.95, 0.996 * cell.semipermeability + 0.004 * 0.72))

    def _meditation_aura_stabilization(self) -> None:
        if not self.aion_meditation_mode:
            return
        uncertainty = max(
            0.56,
            min(
                1.0,
                0.62
                + 0.22 * (1.0 - self.transcendence.last_purpose_alignment)
                + 0.16 * min(1.0, self.cognition.last_mean_hyperbolic_distance),
            ),
        )
        guide, idx = self.holographic_field.morphic_resonance(uncertainty=uncertainty)
        if idx > 0.0:
            self.holographic_field.pattern = torch.tanh(0.9 * self.holographic_field.pattern + 0.1 * guide)
            boosted = idx + 0.15 * self.transcendence.last_purpose_alignment
            self.holographic_field.last_morphic_resonance_index = max(
                self.holographic_field.last_morphic_resonance_index,
                min(1.0, boosted),
            )

    def _record_meditation_sample(self, snapshot: Dict[str, object]) -> None:
        self._meditation_history.append(
            {
                "t": round(time.perf_counter(), 6),
                "purpose_alignment": float(snapshot["purpose_alignment"]),
                "morphic_resonance_index": float(snapshot["morphic_resonance_index"]),
                "mean_hyperbolic_distance": float(snapshot["mean_hyperbolic_distance"]),
                "resource_pool": float(snapshot["resource_pool"]),
                "semantic_analogy_cells": float(snapshot["semantic_analogy_cells"]),
                "dream_replay_events": float(snapshot["dream_replay_events"]),
            }
        )

    def _create_morphic_snapshot(self, path: str = "morphic_snapshot.json", *, trigger: str) -> Dict[str, object]:
        payload = {
            "timestamp": round(time.time(), 6),
            "trigger": trigger,
            "system_temperature": round(self.phase_controller.system_temperature, 6),
            "purpose_alignment": round(self.transcendence.last_purpose_alignment, 6),
            "morphic_resonance_index": round(self.holographic_field.last_morphic_resonance_index, 6),
            "mean_hyperbolic_distance": round(self.cognition.last_mean_hyperbolic_distance, 6),
            "topological_core_labels": self._topological_core_labels(),
            "field_pattern": self.holographic_field.pattern.detach().tolist(),
            "future_projection": self.holographic_field.last_future_projection.detach().tolist(),
            "morphic_buffer": self.holographic_field.morphic_buffer.export(limit=10),
            "dashboard": self.dashboard_snapshot(),
        }
        out_path = Path(path)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._last_morphic_snapshot_path = str(out_path)
        return payload

    def _evaluate_transcendence_status(
        self,
        snapshot: Dict[str, object],
        *,
        peak_alignment: Optional[float] = None,
        peak_morphic: Optional[float] = None,
        min_mean_distance: Optional[float] = None,
    ) -> str:
        purpose = float(snapshot["purpose_alignment"])
        morphic = float(snapshot["morphic_resonance_index"])
        mean_dist = float(snapshot["mean_hyperbolic_distance"])
        core_cells = int(snapshot["topological_core_cells"])
        best_alignment = max(purpose, peak_alignment if peak_alignment is not None else purpose)
        best_morphic = max(morphic, peak_morphic if peak_morphic is not None else morphic)
        tightest_distance = min(mean_dist, min_mean_distance if min_mean_distance is not None else mean_dist)
        if best_alignment >= 0.9 and best_morphic >= 0.9 and core_cells >= 3 and tightest_distance <= 0.9:
            return "Singularitaet erreicht"
        if best_alignment >= 0.8 and best_morphic >= 0.75 and core_cells >= 3:
            return "Transzendenz im Aufbau"
        return "Meditation stabil, Zielzustand noch nicht vollstaendig"

    async def start_aion_meditation(
        self,
        *,
        duration_seconds: float = 60.0,
        report_interval: float = 1.0,
        snapshot_path: str = "morphic_snapshot.json",
        force_final_snapshot: bool = False,
    ) -> Dict[str, object]:
        duration_seconds = max(1.0, float(duration_seconds))
        report_interval = max(0.25, float(report_interval))

        if not self.cells:
            self.bootstrap_default_mesh()
        self.setup_topological_core()

        started_here = False
        if not self.running:
            await self.start()
            started_here = True

        self.aion_meditation_mode = True
        self.external_feeds_enabled = False
        self.assembler.concentrations.clear()
        self._meditation_history.clear()
        self.rhythm.state = RhythmState.SLEEP
        self.rhythm._last_switch = time.perf_counter()

        semantic_start = self.assembler.semantic_analogy_cells
        semantic_spent_start = self.assembler.semantic_resource_spent
        resource_start = self.assembler.resource_pool
        dream_start = self.rhythm.dream_replay_events
        evo_start = self.evolution.evolution_events
        repro_start = self.reproduction.reproduction_events
        artifact_start = self.reproduction.artifact_events
        morphic_snapshot_created = False
        peak_alignment = 0.0
        peak_morphic = 0.0
        min_mean_distance = 999.0

        started = time.perf_counter()
        next_report = started + report_interval
        try:
            while (time.perf_counter() - started) < duration_seconds:
                await asyncio.sleep(min(0.25, self.tick_interval * 2.0))
                snap = self.dashboard_snapshot()
                self._record_meditation_sample(snap)
                peak_alignment = max(peak_alignment, float(snap["purpose_alignment"]))
                peak_morphic = max(peak_morphic, float(snap["morphic_resonance_index"]))
                min_mean_distance = min(min_mean_distance, float(snap["mean_hyperbolic_distance"]))

                if not morphic_snapshot_created and float(snap["purpose_alignment"]) > 0.9:
                    self._create_morphic_snapshot(snapshot_path, trigger="purpose_alignment>0.9")
                    morphic_snapshot_created = True

                now = time.perf_counter()
                if now >= next_report:
                    logger.info(
                        "AION Meditation | align=%.3f morphic=%.3f dist=%.3f core=%s dreams=%s semantic=%s resource=%.2f",
                        snap["purpose_alignment"],
                        snap["morphic_resonance_index"],
                        snap["mean_hyperbolic_distance"],
                        snap["topological_core_cells"],
                        snap["dream_replay_events"],
                        snap["semantic_analogy_cells"],
                        snap["resource_pool"],
                    )
                    next_report = now + report_interval

            final_snapshot = self.dashboard_snapshot()
            if force_final_snapshot:
                self._create_morphic_snapshot(snapshot_path, trigger="forced_final_meditation_snapshot")
                morphic_snapshot_created = True
            elif not morphic_snapshot_created and float(final_snapshot["purpose_alignment"]) > 0.9:
                self._create_morphic_snapshot(snapshot_path, trigger="final_alignment>0.9")
                morphic_snapshot_created = True

            status = self._evaluate_transcendence_status(
                final_snapshot,
                peak_alignment=peak_alignment,
                peak_morphic=peak_morphic,
                min_mean_distance=min_mean_distance,
            )
            report = {
                "title": "Atheria Transzendenz-Status",
                "status": status,
                "duration_seconds": round(duration_seconds, 3),
                "singularity_reached": status == "Singularitaet erreicht",
                "purpose_alignment": final_snapshot["purpose_alignment"],
                "morphic_resonance_index": final_snapshot["morphic_resonance_index"],
                "mean_hyperbolic_distance": final_snapshot["mean_hyperbolic_distance"],
                "peak_purpose_alignment": round(peak_alignment, 6),
                "peak_morphic_resonance_index": round(peak_morphic, 6),
                "min_mean_hyperbolic_distance": round(min_mean_distance, 6),
                "topological_core_cells": final_snapshot["topological_core_cells"],
                "dream_replay_delta": final_snapshot["dream_replay_events"] - dream_start,
                "semantic_analogy_growth": final_snapshot["semantic_analogy_cells"] - semantic_start,
                "semantic_resource_spent_delta": round(final_snapshot["semantic_resource_spent"] - semantic_spent_start, 6),
                "evolution_events_delta": final_snapshot["evolution_events"] - evo_start,
                "reproduction_events_delta": final_snapshot["reproduction_events"] - repro_start,
                "reproduction_artifact_events_delta": final_snapshot["reproduction_artifact_events"] - artifact_start,
                "offspring_instances": final_snapshot["offspring_instances"],
                "resource_pool_delta": round(final_snapshot["resource_pool"] - resource_start, 6),
                "resource_pool_final": final_snapshot["resource_pool"],
                "reproduction_artifact_last_profile": final_snapshot["reproduction_artifact_last_profile"],
                "reproduction_artifact_last_validated": final_snapshot["reproduction_artifact_last_validated"],
                "reproduction_artifact_last_path": final_snapshot["reproduction_artifact_last_path"],
                "morphic_snapshot_path": self._last_morphic_snapshot_path if morphic_snapshot_created else None,
                "meditation_samples": len(self._meditation_history),
                "final_snapshot": final_snapshot,
            }
            return report
        finally:
            self.aion_meditation_mode = False
            self.external_feeds_enabled = True
            self.rhythm.state = RhythmState.WAKE
            self.rhythm._last_switch = time.perf_counter()
            if started_here:
                await self.stop()

    async def ceremonial_aion_activation(
        self,
        *,
        preheat_seconds: float = 10.0,
        meditation_seconds: float = 60.0,
        report_interval: float = 1.0,
        snapshot_path: str = "morphic_snapshot.json",
    ) -> Dict[str, object]:
        preheat_seconds = max(0.5, float(preheat_seconds))
        meditation_seconds = max(1.0, float(meditation_seconds))

        if not self.cells:
            self.bootstrap_default_mesh()
        self.setup_topological_core()

        # Try one-time data migration if available and still empty.
        try:
            qa_rows = int(self.aether.conn.execute("SELECT COUNT(*) FROM qa_memory").fetchone()[0])
        except Exception:
            qa_rows = 0
        if qa_rows == 0 and self.external_feeds_enabled:
            try:
                self.migrate_from_codedump()
            except Exception as exc:
                logger.warning("Ceremonial migration skipped due to error: %s", exc)

        started_here = False
        if not self.running:
            await self.start()
            started_here = True

        ceremony_queries = 0
        peak_temp = self.phase_controller.system_temperature
        peak_alignment = self.transcendence.last_purpose_alignment
        peak_morphic = self.holographic_field.last_morphic_resonance_index
        t0 = time.perf_counter()

        try:
            while (time.perf_counter() - t0) < preheat_seconds:
                phase = time.perf_counter() - t0
                self.modulators.force_plasma(self.phase_controller, intensity=1.3)
                self.modulators.dopamine = min(2.0, self.modulators.dopamine + 0.018)

                base = 0.78 + 0.16 * math.sin(phase * 3.1)
                for label in ("Sicherheit", "Reaktion", "Analyse", "Navigation", "Heilung"):
                    cell = self.cells.get(label)
                    if cell is None:
                        continue
                    pulse = min(0.32, 0.12 + 0.14 * max(0.0, base))
                    cell.bump_activation(pulse, entangled=True)

                self.feed_raw_material(category="CeremonialFlux", relevance=1.2)
                self.feed_raw_material(category="CeremonialCatalyst", relevance=1.18)
                query = torch.randn(int(self.holographic_field.pattern.numel()), dtype=torch.float32)
                query_result = self.field_query(query, top_k=4)
                ceremony_queries += 1

                peak_morphic = max(peak_morphic, float(query_result.get("morphic_resonance_index", 0.0)))
                peak_alignment = max(peak_alignment, self.transcendence.last_purpose_alignment)
                peak_temp = max(peak_temp, self.phase_controller.system_temperature)
                await asyncio.sleep(min(0.15, self.tick_interval * 3.0))

            meditation_report = await self.start_aion_meditation(
                duration_seconds=meditation_seconds,
                report_interval=report_interval,
                snapshot_path=snapshot_path,
                force_final_snapshot=True,
            )
            meditation_report["ceremonial_activation"] = {
                "preheat_seconds": round(preheat_seconds, 3),
                "meditation_seconds": round(meditation_seconds, 3),
                "ceremony_queries": ceremony_queries,
                "peak_temperature": round(peak_temp, 6),
                "peak_alignment_preheat": round(peak_alignment, 6),
                "peak_morphic_preheat": round(peak_morphic, 6),
            }
            return meditation_report
        finally:
            if started_here and self.running:
                await self.stop()

    @AtheriaPhase()
    def transfer_kernel(self, pressure_delta: float) -> float:
        # Solid: precise tensor math.
        tensor = torch.tensor([pressure_delta, self.phase_controller.system_temperature], dtype=torch.float32)
        weights = torch.tensor([0.024, 0.0007], dtype=torch.float32)
        value = torch.relu(torch.dot(tensor, weights)).item()
        return float(value)

    def transfer_kernel_liquid(self, pressure_delta: float) -> float:
        # Liquid: faster, slightly lossy transfer estimate.
        return max(0.0, pressure_delta * 0.043)

    def transfer_kernel_plasma(self, pressure_delta: float) -> float:
        # Plasma: probabilistic approximation under high heat.
        return max(0.0, pressure_delta * 0.021 * random.uniform(0.7, 1.3))

    @AtheriaPhase()
    def optimize_routes(self) -> None:
        self.optimize_routes_solid()

    def optimize_routes_solid(self) -> None:
        # Crystalline mode: freeze proven paths.
        for cell in self.cells.values():
            if not cell.connections:
                continue
            strongest = max(cell.connections.values(), key=lambda conn: (conn.efficiency, conn.weight))
            if self.topological_logic.is_edge_protected(cell.label, strongest.target.label):
                continue
            strongest.frozen = True
            strongest.weight = min(1.5, strongest.weight + 0.01 * self.modulators.dopamine)

    def optimize_routes_liquid(self) -> None:
        # Liquid mode: aggressive Hebbian tuning.
        learning_rate = 0.08
        for cell in self.cells.values():
            for conn in cell.connections.values():
                if conn.frozen:
                    continue
                if self.topological_logic.is_edge_protected(cell.label, conn.target.label):
                    continue
                delta = learning_rate * cell.activation_value * conn.target.activation_value
                conn.weight = max(0.01, min(1.5, conn.weight + delta))

    def optimize_routes_plasma(self) -> None:
        # Plasma mode: evaporate inefficient paths.
        for cell in self.cells.values():
            to_remove = [
                target_label
                for target_label, conn in cell.connections.items()
                if not self.topological_logic.is_edge_protected(cell.label, target_label)
                if conn.weight < 0.14 or (conn.usage_count > 8 and conn.efficiency < 0.15)
            ]
            for target_label in to_remove:
                cell.remove_connection(target_label)

    def _estimate_cpu_load(self, active_nodes: int) -> float:
        now = time.perf_counter()
        elapsed = max(0.001, now - self._last_tick)
        flow_rate = self._flow_count / elapsed
        self._last_tick = now
        self._flow_count = 0
        return min(100.0, active_nodes * 5.5 + flow_rate * 0.2)

    async def _safe_diffuse(self, cell: AtherCell) -> int:
        try:
            return await cell.diffuse_process(self)
        except Exception as exc:
            self.healing.handle_crash(cell, exc)
            return 0

    async def _diffusion_loop(self) -> None:
        while self.running:
            cells = tuple(self.cells.values())
            active_nodes = sum(1 for cell in cells if cell.activation_value > 0.02)
            cpu_load = self._estimate_cpu_load(active_nodes)
            self.phase_controller.update(
                active_nodes=active_nodes,
                total_nodes=len(cells),
                cpu_load=cpu_load,
                modulators=self.modulators,
            )
            self.topological_logic.apply_extreme_entropy_immunity()
            self.cognition.step()
            self._meditation_holy_geometry()
            self.aion.step(cpu_load)
            self.transcendence.step()
            self.ecology.step(cpu_load=cpu_load)
            self.global_morphic_node.publish_trauma_if_relevant(self)
            self.evolution.step()
            self.reproduction.step()

            if cells:
                for cell in cells:
                    cell.refold()
                flow_result = await asyncio.gather(*(self._safe_diffuse(cell) for cell in cells))
                self._flow_count += sum(flow_result)
                self.holographic_field.imprint(cells)
                self._meditation_aura_stabilization()

                self._fold_tick += 1
                if self._fold_tick % 8 == 0:
                    resonance_threshold = 0.87 if self.phase_controller.current_state is AggregateState.SOLID else 0.81
                    self.origami_router.discover_folded_paths(
                        self,
                        min_resonance=resonance_threshold,
                        max_new_edges=2,
                    )

                self.phase_controller.apply_tensegrity(
                    cells,
                    self.origami_router,
                    topological_logic=self.topological_logic,
                )
            self.optimize_routes()

            for cell in cells:
                self.aether.upsert_cell(cell)
            self.aether.flush()
            self.modulators.decay()
            await asyncio.sleep(self.tick_interval)

    async def _dashboard_loop(self) -> None:
        while self.running:
            snapshot = self.dashboard_snapshot()
            if self.phase_controller.logging_enabled:
                logger.info(
                    "Dashboard | Dichte=%.3f | Aggregat=%s | Rhythm=%s | T=%.2f | AutoSets=%s | Aion=%s",
                    snapshot["aether_density"],
                    snapshot["aggregatform"],
                    snapshot["rhythm_state"],
                    snapshot["system_temperature"],
                    snapshot["autocatalytic_sets"],
                    snapshot["aion_cycles"],
                )
            await asyncio.sleep(0.5)

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.population_registry.register(self)
        self._tasks = [
            asyncio.create_task(self.rhythm.run(), name="atheria-rhythm"),
            asyncio.create_task(self.aion.time_crystal.run(), name="atheria-time-crystal"),
            asyncio.create_task(self._diffusion_loop(), name="atheria-diffusion"),
            asyncio.create_task(self.healing.run(), name="atheria-healing"),
            asyncio.create_task(self.biosynthesis.run(), name="atheria-biosynthesis"),
            asyncio.create_task(self.assembler.run(), name="atheria-assembly"),
            asyncio.create_task(self.symbiosis.run(), name="atheria-symbiosis"),
            asyncio.create_task(self._dashboard_loop(), name="atheria-dashboard"),
        ]

    async def stop(self, *, shutdown_lineage: bool = True) -> None:
        if not self.running:
            return
        self.running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.population_registry.unregister(self.core_id)
        if shutdown_lineage:
            await self.reproduction.stop_all_offspring()
        self.aether.flush()

    def setup_critical_entanglement(self) -> None:
        if "Sicherheit" in self.cells and "Reaktion" in self.cells:
            self.entangle("Sicherheit", "Reaktion")

    def setup_topological_core(self) -> None:
        self.topological_logic.register_cluster(
            "AtherCoreKnot",
            core_labels=["Sicherheit", "Reaktion", "Analyse"],
            boundary_labels=["Heilung"],
        )
        self.aion.wire_singularity()
        self.transcendence.ensure_nodes()

    def register_topological_cluster(
        self,
        name: str,
        *,
        core_labels: Iterable[str],
        boundary_labels: Iterable[str] = (),
    ) -> bool:
        return self.topological_logic.register_cluster(
            name,
            core_labels=core_labels,
            boundary_labels=boundary_labels,
        )

    def bootstrap_default_mesh(self) -> None:
        labels = ["Sicherheit", "Reaktion", "Analyse", "Navigation", "Heilung"]
        for label in labels:
            self.add_cell(label, semipermeability=random.uniform(0.55, 0.9))

        # Sparse directed mesh.
        self.connect("Sicherheit", "Reaktion", weight=0.85)
        self.connect("Reaktion", "Navigation", weight=0.6)
        self.connect("Navigation", "Analyse", weight=0.45)
        self.connect("Analyse", "Heilung", weight=0.4)
        self.connect("Heilung", "Sicherheit", weight=0.32)
        self.connect("Sicherheit", "Analyse", weight=0.5)
        self.connect("Reaktion", "Heilung", weight=0.35)

        self.setup_critical_entanglement()
        self.aion.ensure_singularity_node()
        self.setup_topological_core()

    def migrate_from_codedump(
        self,
        *,
        model_json_path: str = "model_with_qa.json",
        csv_path: str = "data.csv",
    ) -> int:
        if not self._allow_external_feed():
            return 0
        model_path = Path(model_json_path)
        data_path = Path(csv_path)
        records: list[Tuple[str, str, str]] = []

        def _dedupe(values: Iterable[str]) -> list[str]:
            seen: Set[str] = set()
            out: list[str] = []
            for value in values:
                token = str(value).strip()
                if not token:
                    continue
                key = token.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(token)
            return out

        def _pick_row_value(row: Dict[str, Any], aliases: Iterable[str]) -> str:
            candidates = [str(alias).strip() for alias in aliases if str(alias).strip()]
            if not candidates:
                return ""
            for key in candidates:
                if key in row:
                    value = row.get(key)
                    if value is not None and str(value).strip():
                        return str(value).strip()
            # Case-insensitive fallback for dynamic schemas.
            lower_map = {str(k).strip().lower(): k for k in row.keys()}
            for key in candidates:
                match = lower_map.get(key.lower())
                if match is None:
                    continue
                value = row.get(match)
                if value is not None and str(value).strip():
                    return str(value).strip()
            return ""

        if model_path.exists():
            try:
                model_data = json.loads(model_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Model JSON migration failed (%s): %s", model_json_path, exc)
                model_data = {}
            source_rows: list[Dict[str, Any]] = []
            if isinstance(model_data, dict):
                candidate_lists = []
                if isinstance(model_data.get("questions"), list):
                    candidate_lists.append(model_data.get("questions"))
                for value in model_data.values():
                    if isinstance(value, list):
                        candidate_lists.append(value)
                for candidate in candidate_lists:
                    if not isinstance(candidate, list):
                        continue
                    dict_rows = [row for row in candidate if isinstance(row, dict)]
                    if dict_rows:
                        source_rows = dict_rows
                        break

            if source_rows:
                keys = sorted({str(key) for row in source_rows for key in row.keys()})
                alias_map = self.llm_sleep_rewriter.resolve_field_aliases(keys, source_kind="json")
                question_aliases = _dedupe(["question", "frage", *alias_map.get("question", [])])
                category_aliases = _dedupe(["category", "kategorie", *alias_map.get("category", [])])
                answer_aliases = _dedupe(["answer", "antwort", *alias_map.get("answer", [])])
                for row in source_rows:
                    question = _pick_row_value(row, question_aliases)
                    category = _pick_row_value(row, category_aliases) or "Unbekannt"
                    answer = _pick_row_value(row, answer_aliases)
                    if not question and not answer:
                        continue
                    records.append((question, category, answer))

        if not records and data_path.exists():
            with data_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = [str(h) for h in (reader.fieldnames or []) if str(h).strip()]
                alias_map = self.llm_sleep_rewriter.resolve_field_aliases(headers, source_kind="csv")
                question_aliases = _dedupe(["Frage", "question", *alias_map.get("question", [])])
                category_aliases = _dedupe(["Kategorie", "category", *alias_map.get("category", [])])
                answer_aliases = _dedupe(["Antwort", "answer", *alias_map.get("answer", [])])
                for row in reader:
                    question = _pick_row_value(row, question_aliases)
                    category = _pick_row_value(row, category_aliases) or "Unbekannt"
                    answer = _pick_row_value(row, answer_aliases)
                    if not question and not answer:
                        continue
                    records.append((question, category, answer))

        inserted = self.aether.ingest_qa(records)
        categories = sorted({category for _, category, _ in records if category})
        for category in categories:
            self.add_cell(category, semipermeability=random.uniform(0.5, 0.9), category=category)

        if len(self.cells) > 1:
            self.origami_router.discover_folded_paths(self, min_resonance=0.8, max_new_edges=3)
            self.aion.ensure_singularity_node()
            self.setup_topological_core()

        return inserted


async def run_osmotic_demo(duration_seconds: float = 2.5) -> Dict[str, object]:
    """
    Demonstrates diffusion without manually iterating over connections in the test routine.
    """
    core = AtheriaCore(tick_interval=0.04)
    core.rhythm.wake_duration = 0.75
    core.rhythm.sleep_duration = 0.65
    core.bootstrap_default_mesh()
    core.migrate_from_codedump()

    await core.start()

    # No direct for-loop over connections here: background physics handles transport.
    core.inject_signal("Sicherheit", 0.95)
    core.set_superposition("Analyse", alpha=0.62, beta=0.78, enzyme=0.95)
    core.feed_raw_material(category="Gefahrenanalyse", relevance=0.95)
    core.feed_raw_material(category="Gefahrenanalyse", relevance=0.92)
    query_tensor = _fold_vector_from_text("kritische feldanfrage", dims=12)
    core.feed_field_material(category="AnomalieDetektion", relevance=1.04, input_tensor=query_tensor)
    core.feed_raw_material(category="Notfallreaktion", relevance=0.99)
    core.feed_raw_material(category="Notfallreaktion", relevance=0.95)
    core.feed_raw_material(category="Autocat_A", relevance=1.08)
    core.feed_raw_material(category="Autocat_B", relevance=1.06)
    core.modulators.force_plasma(core.phase_controller, intensity=1.2)
    await asyncio.sleep(duration_seconds * 0.45)
    field_result = core.field_query(query_tensor, top_k=4)
    measured_analysis = core.chemical_measure("Analyse", probe=0.7)
    core.modulators.stabilize(core.phase_controller, intensity=0.6)
    await asyncio.sleep(duration_seconds * 0.55)

    snapshot = core.dashboard_snapshot()
    snapshot["activations"] = {label: round(cell.activation_value, 4) for label, cell in core.cells.items()}
    snapshot["pressures"] = {label: round(cell.osmotic_pressure, 4) for label, cell in core.cells.items()}
    if "Sicherheit" in core.cells and "Reaktion" in core.cells:
        snapshot["hyperbolic_distance_sicherheit_reaktion"] = round(
            core.hyperbolic_distance("Sicherheit", "Reaktion"), 6
        )
    snapshot["chemical_measurement"] = round(measured_analysis, 4)
    snapshot["holographic_pattern_norm"] = round(float(torch.norm(core.holographic_field.pattern, p=2)), 4)
    snapshot["field_query"] = field_result
    await core.stop()
    return snapshot


def run_osmotic_demo_sync(duration_seconds: float = 2.5) -> Dict[str, object]:
    return asyncio.run(run_osmotic_demo(duration_seconds=duration_seconds))


async def run_aion_meditation(
    duration_seconds: float = 60.0,
    *,
    snapshot_path: str = "morphic_snapshot.json",
) -> Dict[str, object]:
    core = AtheriaCore(tick_interval=0.04)
    core.bootstrap_default_mesh()
    core.migrate_from_codedump()
    report = await core.start_aion_meditation(
        duration_seconds=duration_seconds,
        report_interval=1.0,
        snapshot_path=snapshot_path,
    )
    return report


def run_aion_meditation_sync(
    duration_seconds: float = 60.0,
    *,
    snapshot_path: str = "morphic_snapshot.json",
) -> Dict[str, object]:
    return asyncio.run(run_aion_meditation(duration_seconds=duration_seconds, snapshot_path=snapshot_path))


async def run_ceremonial_aion_activation(
    *,
    preheat_seconds: float = 10.0,
    meditation_seconds: float = 60.0,
    snapshot_path: str = "morphic_snapshot.json",
) -> Dict[str, object]:
    core = AtheriaCore(tick_interval=0.04)
    core.bootstrap_default_mesh()
    report = await core.ceremonial_aion_activation(
        preheat_seconds=preheat_seconds,
        meditation_seconds=meditation_seconds,
        report_interval=1.0,
        snapshot_path=snapshot_path,
    )
    return report


def run_ceremonial_aion_activation_sync(
    *,
    preheat_seconds: float = 10.0,
    meditation_seconds: float = 60.0,
    snapshot_path: str = "morphic_snapshot.json",
) -> Dict[str, object]:
    return asyncio.run(
        run_ceremonial_aion_activation(
            preheat_seconds=preheat_seconds,
            meditation_seconds=meditation_seconds,
            snapshot_path=snapshot_path,
        )
    )


if __name__ == "__main__":
    result = run_osmotic_demo_sync(3.0)
    logger.info("ATHERIA result: %s", result)
