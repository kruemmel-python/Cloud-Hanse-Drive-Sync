from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchManager:
    """Balances high-end spending sinks with exponential + logarithmic scaling."""

    base_cost_social: int = 8_000
    base_cost_research: int = 500_000
    base_cost_infrastructure: int = 350_000
    base_cost_sophia: int = 750_000
    growth: float = 1.85

    def _base_cost(self, track: str) -> int:
        key = str(track).strip().lower()
        if key == "social":
            return self.base_cost_social
        if key == "research":
            return self.base_cost_research
        if key == "infrastructure":
            return self.base_cost_infrastructure
        if key == "sophia":
            return self.base_cost_sophia
        return self.base_cost_research

    def cost_for_level(self, track: str, level: int) -> int:
        level_i = max(0, int(level))
        base = float(self._base_cost(track))
        # Exponential growth with logarithmic steepening keeps billion-scale meaningful.
        scaled = base * (self.growth ** level_i) * (1.0 + math.log1p(level_i + 1))
        return max(int(base), int(round(scaled)))

    def level_from_spend(self, track: str, spend_total: float) -> int:
        remaining = max(0.0, float(spend_total))
        level = 0
        # Hard guard for corrupt data.
        while level < 200:
            cost = float(self.cost_for_level(track, level))
            if remaining < cost:
                break
            remaining -= cost
            level += 1
        return level

    def efficiency_reduction(self, level: int) -> float:
        # 20% on level 1 and asymptotically capped to avoid zero-input production.
        level_i = max(0, int(level))
        if level_i <= 0:
            return 0.0
        return min(0.80, 0.20 + 0.08 * (level_i - 1))

    def social_relief_gain(self, amount: float) -> float:
        # Diminishing returns via logarithm.
        amount_f = max(0.0, float(amount))
        return min(0.08, math.log1p(amount_f / 5_000.0) * 0.012)

    def hazard_mitigation_gain(self, amount: float) -> float:
        amount_f = max(0.0, float(amount))
        return min(0.10, math.log1p(amount_f / 6_000.0) * 0.014)

    def travel_time_multiplier(self, infrastructure_level: int, year: int) -> float:
        level_i = max(0, int(infrastructure_level))
        year_i = int(year)
        if year_i < 2000:
            return 1.0
        # Strong late-game acceleration for "Sub-QG-Antriebe".
        return max(0.10, 1.0 - 0.12 * level_i)

    def global_loss_value(self, sophia_spend: float) -> float:
        spend = max(0.0, float(sophia_spend))
        # Smooth 0..0.85 dampening range.
        return min(0.85, math.log1p(spend / 1_000_000.0) * 0.12)
