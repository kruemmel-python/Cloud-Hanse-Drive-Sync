from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

from atheria_economy import AtheriaEconomyEngine, EconomyState
from game_data import (
    CITIES,
    CITY_PRICE_BIAS,
    GOODS,
    MAX_YEARS,
    MIN_NAME_LEN,
    SAVE_DIR,
    SAVE_SLOT_COUNT,
    SEA_FACTORS,
    SEA_STATES,
    STARTING_AGE,
    STARTING_CASH,
    STARTING_DEBT,
    STARTING_REPUTATION,
    STARTING_YEAR,
    TITLE_STEPS,
)
from models import Player


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


class PygameHanseApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Hanse - pygame Edition")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True

        self.font_title = pygame.font.Font(None, 58)
        self.font_h1 = pygame.font.Font(None, 38)
        self.font = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)

        self.rng = random.Random()
        self.scene = "menu"

        self.save_dir = Path(__file__).with_name(SAVE_DIR)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.player: Player | None = None
        self.current_year = STARTING_YEAR
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self.market_cache: Dict[Tuple[int, str, str], Dict[str, int]] = {}
        self.economy_engine = AtheriaEconomyEngine()
        self.economy_state = self.economy_engine.for_year(
            year=self.current_year,
            sea_state=self.current_sea_state,
            goods=GOODS.keys(),
            cities=CITIES,
        )

        self.selected_slot = 1
        self.selected_good = 0
        self.selected_dest = 0
        self.trade_qty = 5

        self.new_name = ""
        self.new_gender = "m"
        self.new_city = 0

        self.button_states: Dict[str, Tuple[pygame.Rect, bool]] = {}
        self.goods_rows: List[Tuple[int, pygame.Rect]] = []
        self.city_rows: List[Tuple[int, pygame.Rect]] = []
        self.slot_rows: List[Tuple[int, pygame.Rect]] = []
        self.messages: List[str] = [
            "Willkommen in Hanse (pygame).",
            "Neues Spiel anlegen oder Slot laden.",
        ]

    def run(self) -> int:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)

            self._draw()
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        return 0

    def _handle_key(self, event: pygame.event.Event) -> None:
        if self.scene == "setup":
            if event.key == pygame.K_BACKSPACE:
                self.new_name = self.new_name[:-1]
            elif event.key == pygame.K_RETURN:
                self._start_new_game()
            else:
                if event.unicode.isprintable() and not event.unicode.isspace():
                    if len(self.new_name) < 18:
                        self.new_name += event.unicode
        elif self.scene == "game":
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
                self.running = False
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
            for slot, rect in self.slot_rows:
                if rect.collidepoint(pos):
                    self.selected_slot = slot
                    return
            for idx, rect in self.goods_rows:
                if rect.collidepoint(pos):
                    self.selected_good = idx
                    return
            for idx, rect in self.city_rows:
                if rect.collidepoint(pos):
                    self.selected_dest = idx
                    return
            button = self._clicked_button(pos)
            self._handle_game_button(button)

    def _clicked_button(self, pos: Tuple[int, int]) -> str | None:
        for key, (rect, enabled) in self.button_states.items():
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
        elif key == "game_travel":
            self._travel_to_selected_city()
        elif key == "game_repair_hull":
            self._repair("hull")
        elif key == "game_repair_rig":
            self._repair("rigging")
        elif key == "game_next_year":
            self._advance_year()
        elif key == "game_save":
            self._save_slot(self.selected_slot)
        elif key == "game_load":
            self._load_slot(self.selected_slot)
        elif key == "game_menu":
            self.scene = "menu"

    def _draw(self) -> None:
        self.button_states.clear()
        self.screen.fill(BG_MAIN)
        if self.scene == "menu":
            self._draw_menu()
        elif self.scene == "setup":
            self._draw_setup()
        else:
            self._draw_game()

    def _draw_menu(self) -> None:
        title = self.font_title.render("HANSE - pygame Edition", True, TEXT)
        self.screen.blit(title, (50, 35))
        subtitle = self.font.render("Grafische Version mit Save-Slots", True, TEXT_DIM)
        self.screen.blit(subtitle, (54, 86))

        slots_panel = pygame.Rect(50, 135, 890, 590)
        pygame.draw.rect(self.screen, BG_PANEL, slots_panel, border_radius=14)
        pygame.draw.rect(self.screen, (46, 66, 98), slots_panel, width=2, border_radius=14)
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

    def _draw_setup(self) -> None:
        panel = pygame.Rect(180, 90, 960, 640)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=14)
        pygame.draw.rect(self.screen, (46, 66, 98), panel, width=2, border_radius=14)
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
        y = 224
        for idx, city_name in enumerate(CITIES):
            row = pygame.Rect(700, y, 360, 42)
            selected = idx == self.new_city
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (58, 82, 118), row, width=1, border_radius=8)
            self._draw_text(city_name, self.font_small, TEXT, (716, y + 10))
            self.city_rows.append((idx, row))
            y += 48

        self._draw_button("setup_back", pygame.Rect(220, 610, 180, 54), "Zurueck", True)
        self._draw_button("setup_start", pygame.Rect(880, 610, 180, 54), "Start", True, accent=True)

        self._draw_text("Enter: Starten | Backspace: Zeichen loeschen", self.font_small, TEXT_DIM, (220, 560))

    def _draw_game(self) -> None:
        if self.player is None:
            self._draw_text("Kein Spiel aktiv.", self.font_h1, TEXT, (50, 50))
            self._draw_button("game_menu", pygame.Rect(50, 110, 180, 48), "Zum Menue", True)
            return

        player = self.player
        prices = self._market_prices(player.city)

        top = pygame.Rect(20, 16, WIDTH - 40, 130)
        pygame.draw.rect(self.screen, BG_PANEL, top, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), top, width=2, border_radius=12)

        self._draw_text(f"ANNO {self.current_year}", self.font_h1, TEXT, (38, 30))
        self._draw_text(self.current_sea_state, self.font, ACCENT_2, (40, 76))
        self._draw_text(f"{player.name} ({self._title_for(player)})", self.font, TEXT, (310, 34))
        self._draw_text(f"Stadt: {player.city}", self.font, TEXT_DIM, (310, 70))
        self._draw_text(f"Mark: {player.money}", self.font, GOOD, (540, 34))
        self._draw_text(f"Schulden: {player.debt}", self.font, BAD if player.debt > 15000 else TEXT_DIM, (540, 70))
        self._draw_text(f"Rumpf {player.ship.hull}% / Takelage {player.ship.rigging}%", self.font, TEXT, (760, 34))
        self._draw_text(f"Ladung {player.total_cargo}/{player.ship.cargo_capacity}", self.font, TEXT_DIM, (760, 70))
        net = self._net_worth(player, prices)
        self._draw_text(f"Gesamtwert {net}", self.font, ACCENT_2, (1070, 34))
        self._draw_text(
            f"Atheria W:{self.economy_state.global_growth:.2f} P:{self.economy_state.global_price_level:.2f} "
            f"K:{self.economy_state.resource_scarcity:.2f}",
            self.font_small,
            ACCENT_2,
            (310, 102),
        )
        if player.turns_in_debt_tower > 0:
            self._draw_text(f"Schuldturm: {player.turns_in_debt_tower} Runde(n)", self.font, BAD, (1060, 72))

        goods_panel = pygame.Rect(20, 162, 620, 420)
        cities_panel = pygame.Rect(655, 162, 285, 420)
        act_panel = pygame.Rect(955, 162, 345, 420)
        log_panel = pygame.Rect(20, 596, WIDTH - 40, 205)

        for panel in (goods_panel, cities_panel, act_panel, log_panel):
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
            pygame.draw.rect(self.screen, (47, 67, 98), panel, width=2, border_radius=12)

        self._draw_text("Markt", self.font_h1, TEXT, (38, 178))
        self._draw_text("Reiseziele", self.font_h1, TEXT, (675, 178))
        self._draw_text("Aktionen", self.font_h1, TEXT, (975, 178))
        self._draw_text("Chronik / Meldungen", self.font_h1, TEXT, (38, 610))

        self.goods_rows = []
        goods_list = list(GOODS.keys())
        y = 228
        for idx, good_name in enumerate(goods_list):
            row = pygame.Rect(36, y, 590, 44)
            selected = idx == self.selected_good
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            if row.collidepoint(pygame.mouse.get_pos()):
                color = ROW_HOVER if not selected else ROW_SELECTED
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            qty = player.cargo.get(good_name, 0)
            self._draw_text(good_name, self.font_small, TEXT, (48, y + 12))
            self._draw_text(f"Preis {prices[good_name]:>4}", self.font_small, TEXT_DIM, (248, y + 12))
            self._draw_text(f"Lager {qty:>4}", self.font_small, TEXT_DIM, (454, y + 12))
            self.goods_rows.append((idx, row))
            y += 50

        destinations = [city for city in CITIES if city != player.city]
        if self.selected_dest >= len(destinations):
            self.selected_dest = 0
        self.city_rows = []
        y = 228
        for idx, city_name in enumerate(destinations):
            row = pygame.Rect(670, y, 255, 40)
            selected = idx == self.selected_dest
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            self._draw_text(city_name, self.font_small, TEXT, (684, y + 10))
            self.city_rows.append((idx, row))
            y += 46

        locked = (not player.alive) or (player.turns_in_debt_tower > 0)
        self._draw_button("game_buy", pygame.Rect(975, 228, 152, 46), "Kaufen", not locked, accent=True)
        self._draw_button("game_sell", pygame.Rect(1140, 228, 142, 46), "Verkaufen", not locked)
        self._draw_button("game_qty_minus", pygame.Rect(975, 286, 74, 42), "- Menge", not locked)
        self._draw_button("game_qty_plus", pygame.Rect(1056, 286, 71, 42), "+ Menge", not locked)
        self._draw_text(f"Menge: {self.trade_qty}", self.font_small, TEXT_DIM, (1140, 298))
        self._draw_button("game_travel", pygame.Rect(975, 340, 307, 44), "Reisen", not locked)
        self._draw_button("game_repair_hull", pygame.Rect(975, 394, 152, 42), "Rumpf +10%", not locked)
        self._draw_button("game_repair_rig", pygame.Rect(1140, 394, 142, 42), "Takelage +10%", not locked)
        self._draw_button("game_next_year", pygame.Rect(975, 446, 307, 44), "Naechstes Jahr", player.alive, accent=True)
        self._draw_button("game_save", pygame.Rect(975, 500, 102, 42), "Speichern", player.alive)
        self._draw_button("game_load", pygame.Rect(1088, 500, 90, 42), "Laden", True)
        self._draw_button("game_menu", pygame.Rect(1188, 500, 94, 42), "Menue", True)

        self.slot_rows = []
        y = 550
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

    def _draw_button(
        self,
        key: str,
        rect: pygame.Rect,
        label: str,
        enabled: bool,
        accent: bool = False,
    ) -> None:
        mouse = rect.collidepoint(pygame.mouse.get_pos())
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

    def _draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Tuple[int, int, int],
        pos: Tuple[int, int],
    ) -> None:
        self.screen.blit(font.render(text, True, color), pos)

    def _refresh_economy_for_year(self) -> None:
        self.economy_state = self.economy_engine.for_year(
            year=self.current_year,
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
        self.player = Player(
            name=name,
            gender=self.new_gender,
            city=city,
            money=STARTING_CASH,
            debt=STARTING_DEBT,
            reputation=STARTING_REPUTATION,
            age=STARTING_AGE + self.rng.randint(0, 4),
            cargo={good: 0 for good in GOODS},
        )
        self.current_year = STARTING_YEAR
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._refresh_economy_for_year()
        self.selected_good = 0
        self.selected_dest = 0
        self.messages = []
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
            return f"ANNO {year} | {names_text} | {saved_at}"
        except (OSError, ValueError, TypeError, KeyError):
            return "(defekt)"

    def _save_slot(self, slot: int) -> None:
        if self.player is None:
            self._log("Fehler: Kein aktives Spiel zum Speichern.")
            return
        payload = {
            "year": self.current_year,
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
            for good_name in GOODS:
                self.player.cargo.setdefault(good_name, 0)
            self.current_year = int(raw.get("year", STARTING_YEAR))
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
            self._log(f"Slot {slot} geladen.")
            self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")
            if len(players) > 1:
                self._log("Mehrspieler-Save erkannt: erster Spieler geladen.")
        except (OSError, ValueError, TypeError, KeyError):
            self._log(f"Fehler: Slot {slot} konnte nicht geladen werden.")

    def _market_prices(self, city: str) -> Dict[str, int]:
        key = (self.current_year, self.current_sea_state, city)
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
        max_qty = min(self.player.money // price, self.player.cargo_space_left, self.trade_qty)
        if max_qty <= 0:
            self._log("Nicht genug Mark oder kein Frachtraum frei.")
            return
        self.player.money -= max_qty * price
        self.player.cargo[good] += max_qty
        self.player.reputation = min(200, self.player.reputation + 1)
        self._log(f"Gekauft: {max_qty} {good} fuer {max_qty * price} Mark.")

    def _sell_selected_good(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Verkaufen nicht moeglich.")
            return

        good = list(GOODS.keys())[self.selected_good]
        stock = self.player.cargo.get(good, 0)
        qty = min(stock, self.trade_qty)
        if qty <= 0:
            self._log("Keine Ware auf Lager.")
            return
        price = self._market_prices(self.player.city)[good]
        self.player.cargo[good] -= qty
        self.player.money += qty * price
        self.player.reputation = min(200, self.player.reputation + 1)
        self._log(f"Verkauft: {qty} {good} fuer {qty * price} Mark.")

    def _travel_to_selected_city(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Reisen nicht moeglich.")
            return

        destinations = [city for city in CITIES if city != self.player.city]
        if not destinations:
            self._log("Keine Reiseziele verfuegbar.")
            return
        self.selected_dest = max(0, min(self.selected_dest, len(destinations) - 1))
        target = destinations[self.selected_dest]
        distance = abs(CITIES.index(self.player.city) - CITIES.index(target)) + 1
        travel_cost = 60 + distance * 25
        if self.player.money < travel_cost:
            self._log("Nicht genug Mark fuer die Reise.")
            return

        origin = self.player.city
        self.player.money -= travel_cost
        self.player.city = target
        self._log(f"Eingetroffen: {target}. Reisekosten {travel_cost} Mark.")
        self.player.chronicle.append(f"ANNO {self.current_year}: Von {origin} nach {target} gesegelt.")
        self._resolve_travel_risk(origin, target)

    def _resolve_travel_risk(self, origin: str, target: str) -> None:
        if self.player is None:
            return
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
            self.player.ship.hull = max(0, self.player.ship.hull - hull_damage)
            self.player.ship.rigging = max(0, self.player.ship.rigging - rig_damage)
            self._log(f"Sturm: Rumpf -{hull_damage}, Takelage -{rig_damage}.")
            self.player.chronicle.append(f"ANNO {self.current_year}: Sturm zwischen {origin} und {target}.")
        if self.rng.random() < risk / 1.8 and self.player.total_cargo > 0:
            goods = [good for good, qty in self.player.cargo.items() if qty > 0]
            if goods:
                lost_good = self.rng.choice(goods)
                lost_qty = self.rng.randint(1, max(1, self.player.cargo[lost_good] // 2))
                self.player.cargo[lost_good] -= lost_qty
                self.player.reputation = max(0, self.player.reputation - 2)
                self._log(f"Kaperangriff: Verlust {lost_qty} {lost_good}.")
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Kaperangriff, {lost_qty} {lost_good} verloren."
                )
        if self.player.ship.hull <= 0 or self.player.ship.rigging <= 0:
            self.player.alive = False
            self.player.chronicle.append(f"ANNO {self.current_year}: Schiffbruch.")
            self._log("Das Schiff war nicht seetauglich. Handelshaus endet.")

    def _repair(self, part: str) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Ausbesserung nicht moeglich.")
            return

        if part == "hull":
            current = self.player.ship.hull
            label = "Rumpf"
            unit_cost = 16
        else:
            current = self.player.ship.rigging
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
            self.player.ship.hull += amount
        else:
            self.player.ship.rigging += amount
        self._log(f"{label} um {amount}% verbessert. Kosten {cost} Mark.")

    def _advance_year(self) -> None:
        if self.player is None or not self.player.alive:
            return
        if self.current_year >= STARTING_YEAR + MAX_YEARS:
            self._log("Zeitlimit erreicht. Lade einen Slot oder starte neu.")
            return

        growth = self.economy_state.global_growth
        price_level = self.economy_state.global_price_level

        if self.player.turns_in_debt_tower > 0:
            self.player.turns_in_debt_tower -= 1
            self._log(f"Schuldturm: noch {self.player.turns_in_debt_tower} Runde(n).")
            self.player.chronicle.append(f"ANNO {self.current_year}: Schuldturm.")

        heuer_factor = max(0.75, min(1.45, 0.88 + (price_level - 1.0) * 0.35))
        heuer = int((140 + self.player.ship.cargo_capacity // 4) * heuer_factor)
        self.player.money -= heuer
        if self.player.debt > 0:
            debt_interest = max(1.01, min(1.10, 1.02 + (price_level - 1.0) * 0.05 - (growth - 1.0) * 0.02))
            self.player.debt = int(self.player.debt * debt_interest)

        if self.player.money < 0:
            self.player.debt += abs(self.player.money)
            self.player.money = 0

        if growth > 1.0:
            bonus = int((growth - 1.0) * (120 + self.player.reputation * 3))
            if bonus > 0:
                self.player.money += bonus
                self.player.chronicle.append(f"ANNO {self.current_year}: Wirtschaftsaufschwung (+{bonus} Mark).")
        elif growth < 0.95 and self.player.money > 0:
            recession_loss = int((0.95 - growth) * max(120, self.player.money * 0.05))
            if recession_loss > 0:
                self.player.money = max(0, self.player.money - recession_loss)
                self.player.chronicle.append(f"ANNO {self.current_year}: Konjunkturflaute (-{recession_loss} Mark).")

        if self.player.money > 2500 and self.player.debt > 0:
            repayment = min(self.player.debt, max(300, self.player.money // 5))
            self.player.money -= repayment
            self.player.debt -= repayment
            self._log(f"Schuldentilgung: {repayment} Mark.")

        if self.player.debt > 17000 and self.rng.random() < 0.35:
            turns = self.rng.randint(1, 3)
            self.player.turns_in_debt_tower = turns
            self.player.chronicle.append(f"ANNO {self.current_year}: {turns} Jahre im Schuldturm.")
            self._log(f"Schuldturm verhaengt: {turns} Runde(n).")

        self.player.age += 1
        self._resolve_life_events()
        self._update_title()

        self.current_year += 1
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._refresh_economy_for_year()
        self._log(f"ANNO {self.current_year} beginnt: {self.current_sea_state}.")
        self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")

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
        cargo_value = sum(prices[good] * qty for good, qty in player.cargo.items())
        return player.money + cargo_value + player.ship.value - player.debt + player.reputation * 150

    def _log(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 200:
            self.messages = self.messages[-160:]


def run_pygame_game() -> int:
    app = PygameHanseApp()
    return app.run()
