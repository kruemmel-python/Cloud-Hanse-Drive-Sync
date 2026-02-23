from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from .simulation import WorldSimulator
except ImportError:
    from simulation import WorldSimulator  # type: ignore[no-redef]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run Validierung fuer DeCoG-Immunantwort mit mehreren Manipulationsszenarien."
    )
    parser.add_argument("--state", default="", help="Pfad zu world_state.json. Fallback: local cache oder default.")
    parser.add_argument("--actor-id", default="validator_cli")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def load_state(path_arg: str) -> Dict[str, Any]:
    candidates = []
    if path_arg:
        candidates.append(Path(path_arg))
    candidates.extend(
        [
            Path("cloud_hanse/world_state.local.json"),
            Path("cloud_hanse/default_world_state.json"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            raw = candidate.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            raise RuntimeError(f"Datei enthaelt kein JSON-Objekt: {candidate}")
    raise RuntimeError("Kein world_state gefunden. Nutze --state <pfad>.")


def main() -> int:
    args = parse_args()
    state = load_state(args.state)
    simulator = WorldSimulator(seed=args.seed)
    report = simulator.validate_decog_immunity(state, actor_id=args.actor_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.fail_on_error and not report.get("passed", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

