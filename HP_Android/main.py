import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.join(HERE, "HP_Game")
if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)


def _boot_log(exc: Exception, context: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    details = traceback.format_exc()
    entry = f"[{timestamp}] {context}: {type(exc).__name__}: {exc}\n{details}\n"
    targets = []
    try:
        save_dir = Path(GAME_DIR) / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        targets.append(save_dir / "android_boot_error.log")
    except OSError:
        pass
    download_dir = os.getenv("DOWNLOAD_DIR", "").strip()
    external_storage = os.getenv("EXTERNAL_STORAGE", "").strip()
    candidates = []
    if download_dir:
        candidates.append(Path(download_dir))
    if external_storage:
        candidates.append(Path(external_storage) / "Download")
    candidates.extend(
        [
            Path("/storage/emulated/0/Download"),
            Path("/storage/self/primary/Download"),
            Path("/sdcard/Download"),
        ]
    )
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            targets.append(candidate / "hanse_android_boot_error.log")
            break
        except OSError:
            continue
    for target in targets:
        try:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(entry)
        except OSError:
            continue


def main() -> int:
    try:
        from pygame_game import run_pygame_game
    except Exception as exc:
        _boot_log(exc, "import_pygame_game")
        return 1
    try:
        return int(run_pygame_game())
    except Exception as exc:
        _boot_log(exc, "run_pygame_game")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
