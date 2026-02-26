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
