import argparse
import json
import logging
import sys
from typing import Any, Dict, Optional, Sequence

from atheria_core import (
    run_aion_meditation_sync,
    run_ceremonial_aion_activation_sync,
    run_osmotic_demo_sync,
)


logger = logging.getLogger("atheria.main")


def _add_log_level_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level for this launcher.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="ATHERIA entrypoint: osmotic demo, Aion meditation, ceremonial activation.",
    )
    _add_log_level_arg(parser)

    sub = parser.add_subparsers(dest="mode")

    demo = sub.add_parser("demo", help="Run the standard osmotic ATHERIA demo.")
    _add_log_level_arg(demo)
    demo.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Demo runtime in seconds.",
    )

    meditation = sub.add_parser("meditation", help="Run autonomous Aion meditation.")
    _add_log_level_arg(meditation)
    meditation.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Meditation runtime in seconds.",
    )
    meditation.add_argument(
        "--snapshot",
        default="morphic_snapshot.json",
        help="Path for the morphic snapshot output.",
    )

    ceremonial = sub.add_parser("ceremonial", help="Run ceremonial preheat + meditation sequence.")
    _add_log_level_arg(ceremonial)
    ceremonial.add_argument(
        "--preheat",
        type=float,
        default=10.0,
        help="Preheat runtime in seconds.",
    )
    ceremonial.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Meditation runtime in seconds after preheat.",
    )
    ceremonial.add_argument(
        "--snapshot",
        default="morphic_snapshot.json",
        help="Path for the morphic snapshot output.",
    )

    return parser


def _run(parsed: argparse.Namespace) -> Dict[str, Any]:
    mode = parsed.mode or "demo"

    if mode == "demo":
        return run_osmotic_demo_sync(duration_seconds=float(parsed.duration))
    if mode == "meditation":
        return run_aion_meditation_sync(
            duration_seconds=float(parsed.duration),
            snapshot_path=str(parsed.snapshot),
        )
    if mode == "ceremonial":
        return run_ceremonial_aion_activation_sync(
            preheat_seconds=float(parsed.preheat),
            meditation_seconds=float(parsed.duration),
            snapshot_path=str(parsed.snapshot),
        )

    raise ValueError(f"Unknown mode: {mode}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    parsed = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(parsed.log_level)),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    try:
        result = _run(parsed)
    except Exception as exc:
        logger.exception("ATHERIA launch failed: %s", exc)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
