import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.join(HERE, "HP_Game")
if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)

from pygame_game import run_pygame_game


if __name__ == "__main__":
    raise SystemExit(run_pygame_game())
