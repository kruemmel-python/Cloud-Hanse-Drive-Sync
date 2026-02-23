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
