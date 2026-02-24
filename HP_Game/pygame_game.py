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
    SHIPYARD,
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
from models import Player, Ship


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

CANNON_COST = 500
MAX_SHIP_NAME_LEN = 18


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

        self.image_dir = Path(__file__).with_name("images")
        self.images: Dict[str, pygame.Surface] = {}
        self.scaled_images: Dict[Tuple[str, int, int], pygame.Surface] = {}
        self._load_images()

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
        self.selected_ship_type = 0
        self.selected_fleet_ship = 0
        self.fleet_scroll = 0
        self.shipyard_open = False
        self.ship_cargo_open = False
        self.ship_editor_open = False
        self.ship_name_edit = ""
        self.ship_name_active = False
        self.save_menu_open = False
        self.save_menu_mode: str | None = None
        self.transfer_drag_good: str | None = None
        self.transfer_drag_value = 0
        self.preview_destination: str | None = None
        self.cheat_open = False
        self.cheat_text = ""

        self.new_name = ""
        self.new_gender = "m"
        self.new_city = 0

        self.button_states: Dict[str, Tuple[pygame.Rect, bool]] = {}
        self.goods_rows: List[Tuple[int, pygame.Rect]] = []
        self.city_rows: List[Tuple[int, pygame.Rect]] = []
        self.fleet_rows: List[Tuple[int, pygame.Rect]] = []
        self.slot_rows: List[Tuple[int, pygame.Rect]] = []
        self.ship_rows: List[Tuple[int, pygame.Rect]] = []
        self.dest_rows: List[Tuple[int, pygame.Rect]] = []
        self.transfer_sliders: List[Tuple[str, pygame.Rect, int, int]] = []
        self.ship_name_input_rect: pygame.Rect | None = None
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
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self._handle_release(event.pos)
                elif event.type == pygame.MOUSEMOTION:
                    self._handle_motion(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    self._handle_wheel(event)

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
            if self.cheat_open:
                if event.key == pygame.K_ESCAPE:
                    self.cheat_open = False
                    self.cheat_text = ""
                    return
                if event.key == pygame.K_BACKSPACE:
                    self.cheat_text = self.cheat_text[:-1]
                    return
                if event.key == pygame.K_RETURN:
                    self._submit_cheat()
                    return
                if event.unicode.isprintable() and len(self.cheat_text) < 16:
                    self.cheat_text += event.unicode
                return
            if self.ship_editor_open and self.ship_name_active:
                if event.key == pygame.K_ESCAPE:
                    self.ship_name_active = False
                    self.ship_name_edit = ""
                    self.ship_name_input_rect = None
                    return
                if event.key == pygame.K_BACKSPACE:
                    self.ship_name_edit = self.ship_name_edit[:-1]
                    return
                if event.key == pygame.K_RETURN:
                    self._submit_ship_name()
                    return
                if event.unicode.isprintable() and not event.unicode.isspace():
                    if len(self.ship_name_edit) < MAX_SHIP_NAME_LEN:
                        self.ship_name_edit += event.unicode
                return
            if event.key == pygame.K_ESCAPE:
                if self.shipyard_open:
                    self.shipyard_open = False
                    return
                if self.ship_cargo_open:
                    self.ship_cargo_open = False
                    self.transfer_drag_good = None
                    return
                if self.ship_editor_open:
                    self.ship_editor_open = False
                    self.ship_name_active = False
                    self.ship_name_edit = ""
                    self.ship_name_input_rect = None
                    return
            if event.unicode == "|":
                self.cheat_open = True
                self.cheat_text = ""
                return
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
            if self.shipyard_open:
                self._handle_shipyard_click(pos)
                return
            if self.ship_cargo_open:
                self._handle_ship_cargo_click(pos)
                return
            if self.ship_editor_open:
                self._handle_ship_editor_click(pos)
                return
            for slot, rect in self.slot_rows:
                if self.save_menu_open and rect.collidepoint(pos):
                    self.selected_slot = slot
                    return
            for idx, rect in self.goods_rows:
                if rect.collidepoint(pos):
                    self.selected_good = idx
                    return
            for idx, rect in self.fleet_rows:
                if rect.collidepoint(pos):
                    self.selected_fleet_ship = idx
                    self._sync_city_with_selected_ship()
                    return
            button = self._clicked_button(pos)
            self._handle_game_button(button)

    def _handle_motion(self, pos: Tuple[int, int]) -> None:
        if not self.ship_cargo_open:
            return
        if self.transfer_drag_good is None:
            return
        for good_name, rect, max_unload, max_load in self.transfer_sliders:
            if good_name == self.transfer_drag_good:
                self._update_transfer_drag(pos[0], rect, max_unload, max_load)
                return

    def _handle_release(self, _pos: Tuple[int, int]) -> None:
        if self.transfer_drag_good is None:
            return
        self._apply_transfer()

    def _handle_wheel(self, event: pygame.event.Event) -> None:
        if self.scene != "game" or self.shipyard_open or self.ship_cargo_open or self.ship_editor_open:
            return
        if self.player is None:
            return
        mouse = pygame.mouse.get_pos()
        fleet_panel = self._fleet_panel_rect()
        if not fleet_panel.collidepoint(mouse):
            return
        row_height = 86
        visible_height = fleet_panel.height - 56
        total_height = len(self.player.ships) * row_height
        max_scroll = max(0, total_height - visible_height)
        self.fleet_scroll = max(0, min(max_scroll, self.fleet_scroll - event.y * 24))

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
        elif key == "game_cargo":
            self._open_ship_cargo()
        elif key == "game_shipyard":
            self._open_shipyard()
        elif key == "game_ship_editor":
            self._open_ship_editor()
        elif key == "game_repair_hull":
            self._repair("hull")
        elif key == "game_repair_rig":
            self._repair("rigging")
        elif key == "game_next_year":
            self._advance_year()
        elif key == "game_save":
            if not self.save_menu_open or self.save_menu_mode != "save":
                self.save_menu_open = True
                self.save_menu_mode = "save"
            else:
                self._save_slot(self.selected_slot)
                self.save_menu_open = False
                self.save_menu_mode = None
        elif key == "game_load":
            if not self.save_menu_open or self.save_menu_mode != "load":
                self.save_menu_open = True
                self.save_menu_mode = "load"
            else:
                self._load_slot(self.selected_slot)
                self.save_menu_open = False
                self.save_menu_mode = None
        elif key == "game_menu":
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            self.save_menu_open = False
            self.save_menu_mode = None
            self.cheat_open = False
            self.cheat_text = ""
            self.scene = "menu"

    def _open_shipyard(self) -> None:
        if self.player is None or not self.player.alive:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Schiffbau nicht moeglich.")
            return
        self.shipyard_open = True
        if self.selected_ship_type >= len(SHIPYARD):
            self.selected_ship_type = 0

    def _handle_shipyard_click(self, pos: Tuple[int, int]) -> None:
        for idx, rect in self.ship_rows:
            if rect.collidepoint(pos):
                self.selected_ship_type = idx
                return
        button = self._clicked_button(pos)
        if button == "shipyard_buy":
            self._buy_selected_ship_type()
            return
        if button == "shipyard_close":
            self.shipyard_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            return

    def _buy_selected_ship_type(self) -> None:
        if self.player is None:
            return
        if not SHIPYARD:
            self._log("Keine Schiffe verfuegbar.")
            return
        if self.selected_ship_type >= len(SHIPYARD):
            self.selected_ship_type = 0
        name, cap, value, cost = SHIPYARD[self.selected_ship_type]
        if self.player.money < cost:
            self._log(f"Nicht genug Mark. Benoetigt: {cost}")
            return
        self.player.money -= cost
        new_ship = Ship(
            name=name,
            cargo_capacity=cap,
            value=value,
            city=self.player.city,
            cargo={good: 0 for good in GOODS},
        )
        self.player.ships.append(new_ship)
        self.selected_fleet_ship = len(self.player.ships) - 1
        self.shipyard_open = False
        self._log(f"Neues Schiff gekauft: {name}. Kosten: {cost} Mark.")
        self.player.chronicle.append(f"ANNO {self.current_year}: {name} als neues Schiff erworben.")

    def _selected_ship(self) -> Ship | None:
        if self.player is None or not self.player.ships:
            return None
        if self.selected_fleet_ship >= len(self.player.ships):
            self.selected_fleet_ship = 0
        return self.player.ships[self.selected_fleet_ship]

    def _sync_city_with_selected_ship(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None:
            return
        if not ship.is_at_sea:
            self.player.city = ship.city
            self._storage_for_city(ship.city)
            self.preview_destination = None
        else:
            self.preview_destination = ship.destination

    def _storage_for_city(self, city: str) -> Dict[str, int]:
        if self.player is None:
            return {}
        storage = self.player.warehouses.setdefault(city, {})
        for good in GOODS:
            storage.setdefault(good, 0)
        return storage

    def _open_ship_cargo(self) -> None:
        if self.player is None or not self.player.alive:
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist auf See. Verladen nicht moeglich.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        self.ship_cargo_open = True
        self.transfer_drag_good = None
        self.transfer_drag_value = 0
        destinations = [city for city in CITIES if city != ship.city]
        if destinations:
            self.selected_dest = min(self.selected_dest, len(destinations) - 1)
            self.preview_destination = destinations[self.selected_dest]
        else:
            self.preview_destination = None

    def _open_ship_editor(self) -> None:
        if self.player is None or not self.player.alive:
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        self.ship_editor_open = True
        self.ship_name_active = False
        self.ship_name_edit = ship.custom_name

    def _handle_ship_cargo_click(self, pos: Tuple[int, int]) -> None:
        ship = self._selected_ship()
        if ship is None:
            self.ship_cargo_open = False
            return
        for idx, rect in self.dest_rows:
            if rect.collidepoint(pos):
                self.selected_dest = idx
                destinations = [city for city in CITIES if city != ship.city]
                if destinations:
                    self.preview_destination = destinations[self.selected_dest]
                return
        for good_name, rect, max_unload, max_load in self.transfer_sliders:
            if rect.collidepoint(pos):
                self.transfer_drag_good = good_name
                self._update_transfer_drag(pos[0], rect, max_unload, max_load)
                return
        button = self._clicked_button(pos)
        if button == "cargo_travel":
            self._travel_selected_ship()
            return
        if button == "cargo_close":
            self.ship_cargo_open = False
            self.transfer_drag_good = None
            return

    def _handle_ship_editor_click(self, pos: Tuple[int, int]) -> None:
        ship = self._selected_ship()
        if ship is None:
            self.ship_editor_open = False
            return
        if self.ship_name_input_rect and self.ship_name_input_rect.collidepoint(pos):
            self.ship_name_active = True
            if not self.ship_name_edit:
                self.ship_name_edit = ship.custom_name or ship.display_name
            return
        button = self._clicked_button(pos)
        if button == "editor_save":
            self._submit_ship_name()
            return
        if button == "editor_cannon_1":
            self._buy_cannons(ship, 1)
            return
        if button == "editor_cannon_5":
            self._buy_cannons(ship, 5)
            return
        if button == "editor_close":
            self.ship_editor_open = False
            self.ship_name_active = False
            self.ship_name_edit = ""
            self.ship_name_input_rect = None
            return

    def _update_transfer_drag(self, mouse_x: int, rect: pygame.Rect, max_unload: int, max_load: int) -> None:
        center = rect.centerx
        half = rect.width / 2
        offset = mouse_x - center
        if offset >= 0:
            if max_load <= 0:
                self.transfer_drag_value = 0
                return
            ratio = min(1.0, offset / half)
            self.transfer_drag_value = int(round(ratio * max_load))
        else:
            if max_unload <= 0:
                self.transfer_drag_value = 0
                return
            ratio = min(1.0, abs(offset) / half)
            self.transfer_drag_value = -int(round(ratio * max_unload))

    def _apply_transfer(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None or ship.is_at_sea or ship.city != self.player.city:
            self.transfer_drag_good = None
            self.transfer_drag_value = 0
            return
        if not self.transfer_drag_good:
            return
        good_name = self.transfer_drag_good
        value = self.transfer_drag_value
        storage = self._storage_for_city(self.player.city)
        ship.cargo.setdefault(good_name, 0)
        if value > 0:
            max_load = min(storage.get(good_name, 0), ship.cargo_space_left)
            qty = min(value, max_load)
            if qty > 0:
                storage[good_name] -= qty
                ship.cargo[good_name] += qty
                self._log(f"Verladen: {qty} {good_name} auf {ship.display_name}.")
        elif value < 0:
            max_unload = ship.cargo.get(good_name, 0)
            qty = min(-value, max_unload)
            if qty > 0:
                ship.cargo[good_name] -= qty
                storage[good_name] = storage.get(good_name, 0) + qty
                self._log(f"Entladen: {qty} {good_name} von {ship.display_name}.")
        self.transfer_drag_good = None
        self.transfer_drag_value = 0

    def _submit_ship_name(self) -> None:
        ship = self._selected_ship()
        if ship is None:
            self.ship_name_active = False
            self.ship_name_edit = ""
            return
        name = self.ship_name_edit.strip()
        ship.custom_name = name
        self.ship_name_active = False
        self.ship_name_edit = ""
        self._log(f"Schiffsname gesetzt: {ship.display_name}")

    def _buy_cannons(self, ship: Ship, qty: int) -> None:
        if self.player is None:
            return
        if ship.is_at_sea:
            self._log("Kanonen koennen nur im Hafen montiert werden.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        cost = CANNON_COST * qty
        if self.player.money < cost:
            self._log("Nicht genug Mark fuer Kanonen.")
            return
        self.player.money -= cost
        ship.cannons += qty
        self._log(f"{qty} Kanone(n) gekauft fuer {cost} Mark.")

    def _submit_cheat(self) -> None:
        if self.player is None:
            self.cheat_open = False
            self.cheat_text = ""
            return
        code = self.cheat_text.strip()
        if code.upper() == "HANSE":
            self.player.money += 200000
            self._log("Godmodus aktiviert: +200000 Mark.")
            self.player.chronicle.append(f"ANNO {self.current_year}: Godmodus (HANSE) genutzt.")
        else:
            self._log("Unbekannter Code.")
        self.cheat_open = False
        self.cheat_text = ""

    def _draw(self) -> None:
        self.button_states.clear()
        if self.scene == "menu":
            self._blit_background_cover("bg_setup")
            self._draw_menu()
        elif self.scene == "setup":
            self._blit_background("bg_setup")
            self._draw_setup()
        else:
            self._blit_background("bg_market")
            self._draw_game()

    def _draw_menu(self) -> None:
        title = self.font_title.render("HANSE - pygame Edition", True, TEXT)
        self.screen.blit(title, (50, 35))
        subtitle = self.font.render("Grafische Version mit Save-Slots", True, TEXT_DIM)
        self.screen.blit(subtitle, (54, 86))

        header = self._get_scaled("panel_stripe", (WIDTH - 120, 80))
        if header:
            self.screen.blit(header, (50, 10))

        slots_panel = pygame.Rect(50, 135, 890, 590)
        pygame.draw.rect(self.screen, BG_PANEL, slots_panel, border_radius=14)
        pygame.draw.rect(self.screen, (46, 66, 98), slots_panel, width=2, border_radius=14)
        self._draw_panel_header(slots_panel)
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

        ship_icon = self._get_scaled("ship_kogge", (240, 240))
        if ship_icon:
            self.screen.blit(ship_icon, (990, 520))

    def _draw_setup(self) -> None:
        panel = pygame.Rect(180, 90, 960, 640)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=14)
        pygame.draw.rect(self.screen, (46, 66, 98), panel, width=2, border_radius=14)
        self._draw_panel_header(panel)
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
        self._sync_city_with_selected_ship()
        active_city = player.city
        prices = self._market_prices(active_city)
        storage = self._storage_for_city(active_city)
        ship = self._selected_ship()

        top = pygame.Rect(20, 16, WIDTH - 40, 130)
        sea_key = "bg_sea_wild" if self.current_sea_state in {"tobende See", "stuermische See"} else "bg_sea"
        sea_img = self._get_scaled(sea_key, (top.width, top.height))
        if sea_img:
            self.screen.blit(sea_img, (top.x, top.y))
            overlay = pygame.Surface((top.width, top.height), pygame.SRCALPHA)
            overlay.fill((10, 16, 28, 140))
            self.screen.blit(overlay, (top.x, top.y))
        else:
            pygame.draw.rect(self.screen, BG_PANEL, top, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), top, width=2, border_radius=12)

        self._draw_text(f"ANNO {self.current_year}", self.font_h1, TEXT, (38, 30))
        self._draw_text(self.current_sea_state, self.font, ACCENT_2, (40, 76))
        self._draw_text(f"{player.name} ({self._title_for(player)})", self.font, TEXT, (310, 34))
        self._draw_text(f"Stadt: {active_city}", self.font, TEXT_DIM, (310, 70))
        self._draw_text(f"Mark: {player.money}", self.font, GOOD, (540, 34))
        self._draw_text(f"Schulden: {player.debt}", self.font, BAD if player.debt > 15000 else TEXT_DIM, (540, 70))
        if ship:
            ship_loc = f"{ship.city}" if not ship.is_at_sea else f"auf See -> {ship.destination}"
            self._draw_text(f"Aktiv: {ship.display_name}", self.font, TEXT, (760, 34))
            self._draw_text(
                f"Ort: {ship_loc} | Rumpf {ship.hull}% / Takelage {ship.rigging}%",
                self.font_small,
                TEXT_DIM,
                (760, 66),
            )
            eta_text = ""
            if ship.is_at_sea:
                eta = ship.travel_turns_left
                eta_text = f" | Reisezeit {eta} Jahr(e)" if eta > 0 else " | Reisezeit ?"
            self._draw_text(
                f"Ladung {ship.total_cargo}/{ship.cargo_capacity} | Kanonen {ship.cannons}{eta_text}",
                self.font_small,
                TEXT_DIM,
                (760, 88),
            )
            if ship.last_report:
                status = self._shorten_text(f"Status: {ship.last_report}", 58)
                self._draw_text(status, self.font_small, ACCENT_2, (760, 110))
        self._draw_text(f"Flotte: {len(player.ships)} Schiffe", self.font_small, TEXT_DIM, (540, 102))
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
        fleet_panel = self._fleet_panel_rect()
        act_panel = pygame.Rect(955, 162, 345, 420)
        log_panel = pygame.Rect(20, 596, WIDTH - 40, 205)

        for panel in (goods_panel, fleet_panel, act_panel, log_panel):
            self._draw_panel_base(panel, use_paper=True)

        self._draw_text("Markt", self.font_h1, TEXT, (38, 178))
        self._draw_text("Flotte", self.font_h1, TEXT, (675, 178))
        self._draw_text("Aktionen", self.font_h1, TEXT, (975, 178))
        self._draw_text("Chronik / Meldungen", self.font_h1, TEXT, (38, 610))

        target_prices = None
        if self.preview_destination and self.preview_destination != active_city:
            target_prices = self._market_prices(self.preview_destination)
        self._draw_text(f"Ort: {active_city}", self.font_small, TEXT_DIM, (38, 206))
        if self.preview_destination and self.preview_destination != active_city:
            self._draw_text(f"Ziel: {self.preview_destination}", self.font_small, ACCENT_2, (190, 206))

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
            qty = storage.get(good_name, 0)
            self._draw_text(good_name, self.font_small, TEXT, (48, y + 12))
            self._draw_text(f"Preis {prices[good_name]:>4}", self.font_small, TEXT_DIM, (210, y + 12))
            if target_prices:
                self._draw_text(f"Ziel {target_prices[good_name]:>4}", self.font_small, TEXT_DIM, (330, y + 12))
                self._draw_text(f"Lager {qty:>4}", self.font_small, TEXT_DIM, (470, y + 12))
            else:
                self._draw_text(f"Lager {qty:>4}", self.font_small, TEXT_DIM, (454, y + 12))
            self.goods_rows.append((idx, row))
            y += 50

        self.fleet_rows = []
        row_height = 86
        visible_top = 228
        visible_bottom = fleet_panel.y + fleet_panel.height - 18
        total_height = len(player.ships) * row_height
        max_scroll = max(0, total_height - (fleet_panel.height - 56))
        self.fleet_scroll = max(0, min(self.fleet_scroll, max_scroll))
        y = visible_top - self.fleet_scroll
        for idx, fleet_ship in enumerate(player.ships):
            row = pygame.Rect(fleet_panel.x + 12, y, fleet_panel.width - 24, 78)
            if row.bottom < visible_top or row.top > visible_bottom:
                y += row_height
                continue
            selected = idx == self.selected_fleet_ship
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            if row.collidepoint(pygame.mouse.get_pos()):
                color = ROW_HOVER if not selected else ROW_SELECTED
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            icon = self._get_scaled(self._ship_image_key(fleet_ship), (44, 44))
            text_x = row.x + 10
            if icon:
                self.screen.blit(icon, (row.x + 6, row.y + 12))
                text_x = row.x + 58
            label = fleet_ship.display_name
            location = fleet_ship.city if not fleet_ship.is_at_sea else f"See → {fleet_ship.destination}"
            self._draw_text(label, self.font_small, TEXT, (text_x, row.y + 8))
            self._draw_text(
                f"{location} | Ladung {fleet_ship.total_cargo}/{fleet_ship.cargo_capacity}",
                self.font_small,
                TEXT_DIM,
                (text_x, row.y + 34),
            )
            self._draw_text(
                f"R:{fleet_ship.hull}% T:{fleet_ship.rigging}% K:{fleet_ship.cannons}",
                self.font_small,
                TEXT_DIM,
                (text_x, row.y + 58),
            )
            self.fleet_rows.append((idx, row))
            y += row_height

        locked = (not player.alive) or (player.turns_in_debt_tower > 0)
        self._draw_button("game_buy", pygame.Rect(975, 228, 152, 46), "Kaufen", not locked, accent=True)
        self._draw_button("game_sell", pygame.Rect(1140, 228, 142, 46), "Verkaufen", not locked)
        self._draw_button("game_qty_minus", pygame.Rect(975, 286, 74, 42), "- Menge", not locked)
        self._draw_button("game_qty_plus", pygame.Rect(1056, 286, 71, 42), "+ Menge", not locked)
        self._draw_text(f"Menge: {self.trade_qty}", self.font_small, TEXT_DIM, (1140, 298))
        self._draw_button("game_cargo", pygame.Rect(975, 340, 307, 44), "Schiffsladung", not locked)
        self._draw_button("game_ship_editor", pygame.Rect(975, 394, 152, 42), "Schiff-Editor", not locked)
        self._draw_button("game_shipyard", pygame.Rect(1140, 394, 142, 42), "Schiffbau", not locked)
        self._draw_button("game_repair_hull", pygame.Rect(975, 446, 152, 42), "Rumpf +10%", not locked)
        self._draw_button("game_repair_rig", pygame.Rect(1140, 446, 142, 42), "Takelage +10%", not locked)
        self._draw_button("game_next_year", pygame.Rect(975, 498, 307, 44), "Naechstes Jahr", player.alive, accent=True)
        self._draw_button("game_save", pygame.Rect(975, 550, 102, 42), "Speichern", player.alive)
        self._draw_button("game_load", pygame.Rect(1088, 550, 90, 42), "Laden", True)
        self._draw_button("game_menu", pygame.Rect(1188, 550, 94, 42), "Menue", True)

        self.slot_rows = []
        if self.save_menu_open:
            y = 600
            label = "Slots (Speichern)" if self.save_menu_mode == "save" else "Slots (Laden)"
            self._draw_text(label, self.font_small, ACCENT_2, (975, y - 22))
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

        if self.shipyard_open:
            self._draw_shipyard()
        if self.ship_cargo_open:
            self._draw_ship_cargo()
        if self.ship_editor_open:
            self._draw_ship_editor()
        if self.cheat_open:
            self._draw_cheat_prompt()

    def _draw_shipyard(self) -> None:
        if self.player is None:
            return
        player = self.player
        if self.selected_ship_type >= len(SHIPYARD):
            self.selected_ship_type = 0
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 8, 14, 210))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(240, 170, 840, 440)
        stripe = self._get_scaled("panel_stripe", (panel.width, panel.height))
        if stripe:
            self.screen.blit(stripe, (panel.x, panel.y))
            overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            overlay.fill((14, 18, 26, 170))
            self.screen.blit(overlay, (panel.x, panel.y))
        else:
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)
        self._draw_panel_header(panel)

        self._draw_text("Schiffbau", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            f"Neues Schiff wird in {player.city} stationiert.",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 56),
        )

        self.ship_rows = []
        y = panel.y + 96
        for idx, (name, cap, value, cost) in enumerate(SHIPYARD):
            row = pygame.Rect(panel.x + 24, y, panel.width - 48, 54)
            selected = idx == self.selected_ship_type
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            if row.collidepoint(pygame.mouse.get_pos()):
                color = ROW_HOVER if not selected else ROW_SELECTED
            pygame.draw.rect(self.screen, color, row, border_radius=8)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=8)
            key = "ship_kogge"
            if "holk" in name.lower():
                key = "ship_holk"
            elif "kraier" in name.lower():
                key = "ship_kraier"
            icon = self._get_scaled(key, (44, 44))
            text_x = row.x + 12
            if icon:
                self.screen.blit(icon, (row.x + 6, row.y + 4))
                text_x = row.x + 58
            self._draw_text(name, self.font_small, TEXT, (text_x, row.y + 16))
            self._draw_text(f"Ladung {cap}", self.font_small, TEXT_DIM, (row.x + 300, row.y + 16))
            self._draw_text(f"Wert {value}", self.font_small, TEXT_DIM, (row.x + 420, row.y + 16))
            self._draw_text(f"Preis {cost}", self.font_small, ACCENT_2, (row.x + 540, row.y + 16))
            self.ship_rows.append((idx, row))
            y += 64

        if SHIPYARD:
            _name, _cap, _value, cost = SHIPYARD[self.selected_ship_type]
            self._draw_text(
                f"Preis: {cost} Mark",
                self.font,
                ACCENT_2,
                (panel.x + 24, panel.y + 320),
            )

        can_buy = player.alive and player.turns_in_debt_tower == 0
        self._draw_button(
            "shipyard_buy",
            pygame.Rect(panel.x + panel.width - 262, panel.y + panel.height - 62, 120, 44),
            "Kaufen",
            can_buy,
            accent=True,
        )
        self._draw_button(
            "shipyard_close",
            pygame.Rect(panel.x + panel.width - 132, panel.y + panel.height - 62, 110, 44),
            "Schliessen",
            True,
        )

    def _draw_ship_cargo(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 10, 18, 210))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(120, 110, 1080, 600)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)
        paper = self._get_scaled("paper_transfer", (panel.width, panel.height))
        if paper:
            self.screen.blit(paper, (panel.x, panel.y))
            overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            overlay.fill((15, 18, 24, 110))
            self.screen.blit(overlay, (panel.x, panel.y))
        self._draw_panel_header(panel)

        can_transfer = (not ship.is_at_sea) and (ship.city == self.player.city)
        location = ship.city if not ship.is_at_sea else f"auf See → {ship.destination}"

        self._draw_text("Schiffsladung", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            f"{ship.display_name} ({ship.name}) | Ort: {location}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 56),
        )
        self._draw_text(
            f"Ladung {ship.total_cargo}/{ship.cargo_capacity} | Kanonen {ship.cannons}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 78),
        )
        ship_icon = self._get_scaled(self._ship_image_key(ship), (70, 70))
        if ship_icon:
            self.screen.blit(ship_icon, (panel.x + panel.width - 110, panel.y + 24))

        table_x = panel.x + 24
        table_w = panel.width - 320
        dest_x = panel.x + panel.width - 260
        self._draw_text(f"Lager ({self.player.city})", self.font_small, TEXT, (table_x, panel.y + 110))
        self._draw_text("Schiff", self.font_small, TEXT, (table_x + table_w - 120, panel.y + 110))
        self._draw_text("Reiseziele", self.font_small, TEXT, (dest_x, panel.y + 110))

        storage = self._storage_for_city(self.player.city)
        self.transfer_sliders = []
        y = panel.y + 140
        for good_name in GOODS:
            row = pygame.Rect(table_x, y, table_w, 40)
            pygame.draw.rect(self.screen, BG_PANEL_ALT, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            storage_qty = storage.get(good_name, 0)
            ship_qty = ship.cargo.get(good_name, 0)
            self._draw_text(good_name, self.font_small, TEXT, (row.x + 8, row.y + 10))
            self._draw_text(f"{storage_qty:>4}", self.font_small, TEXT_DIM, (row.x + 140, row.y + 10))
            self._draw_text(f"{ship_qty:>4}", self.font_small, TEXT_DIM, (row.x + row.width - 60, row.y + 10))

            slider_rect = pygame.Rect(row.x + 200, row.y + 12, 220, 14)
            max_unload = ship_qty
            max_load = min(storage_qty, ship.cargo_space_left)
            if can_transfer:
                pygame.draw.rect(self.screen, (70, 94, 130), slider_rect, border_radius=6)
                center_x = slider_rect.centerx
                pygame.draw.line(self.screen, TEXT_DIM, (center_x, slider_rect.y), (center_x, slider_rect.y + slider_rect.height))
                value = 0
                if self.transfer_drag_good == good_name:
                    value = self.transfer_drag_value
                if value >= 0:
                    ratio = 0 if max_load == 0 else min(1.0, value / max_load)
                    knob_x = int(center_x + ratio * (slider_rect.width / 2))
                else:
                    ratio = 0 if max_unload == 0 else min(1.0, abs(value) / max_unload)
                    knob_x = int(center_x - ratio * (slider_rect.width / 2))
                knob = pygame.Rect(0, 0, 10, 20)
                knob.center = (knob_x, slider_rect.centery)
                pygame.draw.rect(self.screen, ACCENT_2, knob, border_radius=4)
                if value != 0:
                    self._draw_text(f"{value:+d}", self.font_small, ACCENT_2, (slider_rect.right + 10, row.y + 8))
                self.transfer_sliders.append((good_name, slider_rect, max_unload, max_load))
            else:
                pygame.draw.rect(self.screen, (45, 49, 59), slider_rect, border_radius=6)

            y += 48

        self.dest_rows = []
        destinations = [city for city in CITIES if city != ship.city]
        if destinations and self.selected_dest >= len(destinations):
            self.selected_dest = 0
        y = panel.y + 140
        for idx, city_name in enumerate(destinations):
            row = pygame.Rect(dest_x, y, 228, 34)
            selected = idx == self.selected_dest
            color = ROW_SELECTED if selected else BG_PANEL_ALT
            pygame.draw.rect(self.screen, color, row, border_radius=6)
            pygame.draw.rect(self.screen, (60, 85, 122), row, width=1, border_radius=6)
            self._draw_text(city_name, self.font_small, TEXT, (row.x + 8, row.y + 8))
            self.dest_rows.append((idx, row))
            y += 40

        travel_cost = None
        if destinations:
            target = destinations[self.selected_dest]
            distance = abs(CITIES.index(ship.city) - CITIES.index(target)) + 1
            travel_cost = 60 + distance * 25
        if travel_cost is not None:
            self._draw_text(
                f"Reisekosten: {travel_cost} Mark",
                self.font_small,
                TEXT_DIM,
                (dest_x, panel.y + panel.height - 130),
            )

        travel_enabled = can_transfer and travel_cost is not None and self.player.money >= (travel_cost or 0)
        self._draw_button(
            "cargo_travel",
            pygame.Rect(dest_x, panel.y + panel.height - 98, 228, 40),
            "Reisen",
            travel_enabled,
            accent=True,
        )
        self._draw_button(
            "cargo_close",
            pygame.Rect(dest_x, panel.y + panel.height - 52, 228, 40),
            "Schliessen",
            True,
        )

        if not can_transfer:
            self._draw_text(
                "Schiff muss im aktuellen Hafen liegen.",
                self.font_small,
                BAD,
                (panel.x + 24, panel.y + panel.height - 42),
            )

    def _draw_ship_editor(self) -> None:
        if self.player is None:
            return
        ship = self._selected_ship()
        if ship is None:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 180))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(360, 240, 600, 320)
        stripe = self._get_scaled("panel_stripe", (panel.width, panel.height))
        if stripe:
            self.screen.blit(stripe, (panel.x, panel.y))
            overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            overlay.fill((14, 18, 26, 170))
            self.screen.blit(overlay, (panel.x, panel.y))
        else:
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)
        self._draw_panel_header(panel)

        self._draw_text("Schiff-Editor", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        self._draw_text(
            f"{ship.display_name} ({ship.name}) | Ort: {ship.city}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 58),
        )
        self._draw_text(
            f"Rumpf {ship.hull}% / Takelage {ship.rigging}% | Kanonen {ship.cannons}",
            self.font_small,
            TEXT_DIM,
            (panel.x + 24, panel.y + 82),
        )

        self._draw_text("Name:", self.font_small, TEXT, (panel.x + 24, panel.y + 120))
        input_box = pygame.Rect(panel.x + 24, panel.y + 146, panel.width - 48, 44)
        self.ship_name_input_rect = input_box
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT if self.ship_name_active else (60, 85, 122), input_box, width=2, border_radius=8)
        display_name = self.ship_name_edit if self.ship_name_active else (ship.custom_name or ship.display_name)
        self._draw_text(display_name or "_", self.font, TEXT, (input_box.x + 10, input_box.y + 10))

        cannon_cost_1 = CANNON_COST
        cannon_cost_5 = CANNON_COST * 5
        icon = self._get_scaled("icon_cannon", (28, 28))
        if icon:
            self.screen.blit(icon, (panel.x + 24, panel.y + 200))
            self._draw_text(
                f"Kanonen kosten {CANNON_COST} Mark pro Stueck.",
                self.font_small,
                TEXT_DIM,
                (panel.x + 60, panel.y + 204),
            )
        else:
            self._draw_text(
                f"Kanonen kosten {CANNON_COST} Mark pro Stueck.",
                self.font_small,
                TEXT_DIM,
                (panel.x + 24, panel.y + 204),
            )
        self._draw_button(
            "editor_cannon_1",
            pygame.Rect(panel.x + 24, panel.y + 232, 150, 40),
            f"+1 ({cannon_cost_1})",
            self.player.money >= cannon_cost_1,
        )
        self._draw_button(
            "editor_cannon_5",
            pygame.Rect(panel.x + 184, panel.y + 232, 150, 40),
            f"+5 ({cannon_cost_5})",
            self.player.money >= cannon_cost_5,
        )
        self._draw_button(
            "editor_save",
            pygame.Rect(panel.x + panel.width - 252, panel.y + panel.height - 58, 120, 40),
            "Speichern",
            True,
            accent=True,
        )
        self._draw_button(
            "editor_close",
            pygame.Rect(panel.x + panel.width - 122, panel.y + panel.height - 58, 98, 40),
            "Schliessen",
            True,
        )

    def _draw_cheat_prompt(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 20, 180))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(360, 310, 600, 180)
        pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (49, 71, 102), panel, width=2, border_radius=12)

        self._draw_text("Geheimcode", self.font_h1, TEXT, (panel.x + 24, panel.y + 18))
        input_box = pygame.Rect(panel.x + 24, panel.y + 78, panel.width - 48, 52)
        pygame.draw.rect(self.screen, BG_PANEL_ALT, input_box, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, input_box, width=2, border_radius=8)
        display = self.cheat_text if self.cheat_text else "_"
        self._draw_text(display, self.font, TEXT, (input_box.x + 12, input_box.y + 12))
        self._draw_text("Enter: OK | Esc: Schliessen", self.font_small, TEXT_DIM, (panel.x + 24, panel.y + 140))

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

    def _load_image(self, filename: str) -> pygame.Surface | None:
        path = self.image_dir / filename
        if not path.exists():
            return None
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None

    def _load_images(self) -> None:
        self.images["bg_main"] = self._load_image("bg_main.png")
        self.images["bg_menu"] = self._load_image("Menue.png")
        self.images["bg_setup"] = self._load_image("bg_setup.png")
        self.images["bg_market"] = self._load_image("bg_market.png")
        self.images["bg_sea"] = self._load_image("bg_sea.png")
        self.images["bg_sea_wild"] = self._load_image("bg_sea_wild.png")
        self.images["panel_stripe"] = self._load_image("panel_stripe.png")
        self.images["paper_chronik"] = self._load_image("paper_texture_chronik.png")
        self.images["paper_transfer"] = self._load_image("paper_texture_transfer.png")
        ui_border = self._load_image("ui_border.png")
        self.images["ui_border"] = ui_border
        if ui_border:
            src_w, src_h = ui_border.get_size()
            corner_src = max(64, min(src_w, src_h) // 8)
            tl = ui_border.subsurface(pygame.Rect(0, 0, corner_src, corner_src)).copy()
            self.images["ui_corner_tl"] = tl
            self.images["ui_corner_tr"] = pygame.transform.flip(tl, True, False)
            self.images["ui_corner_bl"] = pygame.transform.flip(tl, False, True)
            self.images["ui_corner_br"] = pygame.transform.flip(tl, True, True)
        self.images["icon_cannon"] = self._load_image("icon_cannon.png")
        self.images["ship_kogge"] = self._load_image("ship_kogge.png")
        self.images["ship_holk"] = self._load_image("ship_holk.png")
        self.images["ship_kraier"] = self._load_image("ship_kraier.png")

    def _get_scaled(self, key: str, size: Tuple[int, int]) -> pygame.Surface | None:
        image = self.images.get(key)
        if image is None:
            return None
        cache_key = (key, size[0], size[1])
        cached = self.scaled_images.get(cache_key)
        if cached is None:
            cached = pygame.transform.smoothscale(image, size)
            self.scaled_images[cache_key] = cached
        return cached

    def _blit_background(self, key: str | None) -> None:
        self.screen.fill(BG_MAIN)
        if key:
            bg = self._get_scaled(key, (WIDTH, HEIGHT))
            if bg:
                self.screen.blit(bg, (0, 0))
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 40))
                self.screen.blit(overlay, (0, 0))

    def _blit_background_cover(self, key: str | None) -> None:
        self.screen.fill(BG_MAIN)
        if not key:
            return
        image = self.images.get(key)
        if image is None:
            return
        img_w, img_h = image.get_size()
        if img_w <= 0 or img_h <= 0:
            return
        scale = max(WIDTH / img_w, HEIGHT / img_h)
        scaled_w = max(1, int(round(img_w * scale)))
        scaled_h = max(1, int(round(img_h * scale)))
        scaled = self._get_scaled(key, (scaled_w, scaled_h))
        if scaled:
            x = (WIDTH - scaled_w) // 2
            y = (HEIGHT - scaled_h) // 2
            self.screen.blit(scaled, (x, y))
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 40))
            self.screen.blit(overlay, (0, 0))

    def _draw_panel_header(self, panel: pygame.Rect) -> None:
        stripe = self._get_scaled("panel_stripe", (panel.width, 36))
        if stripe:
            self.screen.blit(stripe, (panel.x, panel.y))

    def _draw_panel_corners(self, panel: pygame.Rect) -> None:
        corner_size = max(28, min(panel.width, panel.height) // 8)
        for key, pos in (
            ("ui_corner_tl", (panel.x, panel.y)),
            ("ui_corner_tr", (panel.right - corner_size, panel.y)),
            ("ui_corner_bl", (panel.x, panel.bottom - corner_size)),
            ("ui_corner_br", (panel.right - corner_size, panel.bottom - corner_size)),
        ):
            corner = self._get_scaled(key, (corner_size, corner_size))
            if corner:
                self.screen.blit(corner, pos)

    def _draw_panel_base(self, panel: pygame.Rect, use_paper: bool = True) -> None:
        if use_paper:
            paper = self._get_scaled("paper_chronik", (panel.width, panel.height))
            if paper:
                self.screen.blit(paper, (panel.x, panel.y))
                overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
                overlay.fill((18, 22, 30, 110))
                self.screen.blit(overlay, (panel.x, panel.y))
            else:
                pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        else:
            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, (47, 67, 98), panel, width=2, border_radius=12)
        self._draw_panel_header(panel)
        self._draw_panel_corners(panel)

    def _ship_image_key(self, ship: Ship) -> str:
        name = ship.name.lower()
        if "holk" in name:
            return "ship_holk"
        if "kraier" in name:
            return "ship_kraier"
        return "ship_kogge"

    def _draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Tuple[int, int, int],
        pos: Tuple[int, int],
    ) -> None:
        self.screen.blit(font.render(text, True, color), pos)

    def _shorten_text(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max(0, max_len - 3)].rstrip() + "..."

    def _fleet_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(655, 162, 285, 420)

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
        ship = Ship(city=city, cargo={good: 0 for good in GOODS})
        self.player = Player(
            name=name,
            gender=self.new_gender,
            city=city,
            money=STARTING_CASH,
            debt=STARTING_DEBT,
            reputation=STARTING_REPUTATION,
            age=STARTING_AGE + self.rng.randint(0, 4),
            ships=[ship],
            warehouses={city: {good: 0 for good in GOODS}},
        )
        self.current_year = STARTING_YEAR
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._refresh_economy_for_year()
        self.selected_good = 0
        self.selected_dest = 0
        self.selected_ship_type = 0
        self.selected_fleet_ship = 0
        self.fleet_scroll = 0
        self.shipyard_open = False
        self.ship_cargo_open = False
        self.ship_editor_open = False
        self.preview_destination = None
        self.save_menu_open = False
        self.save_menu_mode = None
        self.cheat_open = False
        self.cheat_text = ""
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
            for ship in self.player.ships:
                for good_name in GOODS:
                    ship.cargo.setdefault(good_name, 0)
            for city in CITIES:
                storage = self.player.warehouses.setdefault(city, {})
                for good_name in GOODS:
                    storage.setdefault(good_name, 0)
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
            self.shipyard_open = False
            self.ship_cargo_open = False
            self.ship_editor_open = False
            self.selected_ship_type = 0
            self.selected_fleet_ship = 0
            self.fleet_scroll = 0
            self.preview_destination = None
            self.save_menu_open = False
            self.save_menu_mode = None
            self.cheat_open = False
            self.cheat_text = ""
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
        storage = self._storage_for_city(self.player.city)
        max_qty = min(self.player.money // price, self.trade_qty)
        if max_qty <= 0:
            self._log("Nicht genug Mark.")
            return
        self.player.money -= max_qty * price
        storage[good] = storage.get(good, 0) + max_qty
        self.player.reputation = min(200, self.player.reputation + 1)
        self._log(f"Gekauft: {max_qty} {good} fuer {max_qty * price} Mark (Lager {self.player.city}).")

    def _sell_selected_good(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Verkaufen nicht moeglich.")
            return

        good = list(GOODS.keys())[self.selected_good]
        storage = self._storage_for_city(self.player.city)
        stock = storage.get(good, 0)
        qty = min(stock, self.trade_qty)
        if qty <= 0:
            self._log("Keine Ware auf Lager.")
            return
        price = self._market_prices(self.player.city)[good]
        storage[good] -= qty
        self.player.money += qty * price
        self.player.reputation = min(200, self.player.reputation + 1)
        self._log(f"Verkauft: {qty} {good} fuer {qty * price} Mark.")

    def _travel_selected_ship(self) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Reisen nicht moeglich.")
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist bereits auf See.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return
        destinations = [city for city in CITIES if city != ship.city]
        if not destinations:
            self._log("Keine Reiseziele verfuegbar.")
            return
        self.selected_dest = max(0, min(self.selected_dest, len(destinations) - 1))
        target = destinations[self.selected_dest]
        distance = abs(CITIES.index(ship.city) - CITIES.index(target)) + 1
        travel_cost = 60 + distance * 25
        if self.player.money < travel_cost:
            self._log("Nicht genug Mark fuer die Reise.")
            return

        origin = ship.city
        self.player.money -= travel_cost
        ship.is_at_sea = True
        ship.destination = target
        ship.travel_turns_left = max(1, distance)
        ship.last_report = f"Ausgelaufen nach {target}, ETA {ship.travel_turns_left} Jahr(e)."
        self.preview_destination = target
        self._log(f"{ship.display_name} sticht in See Richtung {target}. Reisekosten {travel_cost} Mark.")
        self.player.chronicle.append(f"ANNO {self.current_year}: {ship.display_name} von {origin} nach {target} entsandt.")
        self.ship_cargo_open = False
        self.transfer_drag_good = None

    def _resolve_travel_risk(self, ship: Ship, origin: str, target: str) -> tuple[bool, str]:
        if self.player is None:
            return True, ""
        risk_map = {
            "tobende See": 0.44,
            "stuermische See": 0.30,
            "bewegte See": 0.20,
            "ruhige See": 0.12,
            "stille See": 0.08,
        }
        risk = risk_map[self.current_sea_state]
        events: list[str] = []
        if self.rng.random() < risk:
            hull_damage = self.rng.randint(5, 18)
            rig_damage = self.rng.randint(4, 14)
            ship.hull = max(0, ship.hull - hull_damage)
            ship.rigging = max(0, ship.rigging - rig_damage)
            events.append(f"Sturm: R-{hull_damage}% T-{rig_damage}%")
            self._log(f"Sturm ({ship.display_name}): Rumpf -{hull_damage}, Takelage -{rig_damage}.")
            self.player.chronicle.append(
                f"ANNO {self.current_year}: Sturm zwischen {origin} und {target} ({ship.display_name})."
            )
        pirate_chance = risk / (1 + ship.cannons * 0.5)
        if self.rng.random() < pirate_chance:
            goods = [good for good, qty in ship.cargo.items() if qty > 0]
            if goods:
                lost_good = self.rng.choice(goods)
                lost_qty = self.rng.randint(1, max(1, ship.cargo[lost_good] // 2))
                ship.cargo[lost_good] -= lost_qty
                rep_loss = max(1, int(round(2 / (1 + ship.cannons * 0.5))))
                self.player.reputation = max(0, self.player.reputation - rep_loss)
                events.append(f"Kaper: -{lost_qty} {lost_good}")
                self._log(f"Kaperangriff ({ship.display_name}): Verlust {lost_qty} {lost_good}.")
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Kaperangriff auf {ship.display_name}, {lost_qty} {lost_good} verloren."
                )
            else:
                events.append("Kaper: keine Beute")
                self._log(f"Kaperangriff ({ship.display_name}): keine Beute.")
                self.player.chronicle.append(
                    f"ANNO {self.current_year}: Kaperangriff auf {ship.display_name}, keine Beute."
                )
        return ship.hull > 0 and ship.rigging > 0, " | ".join(events)

    def _repair(self, part: str) -> None:
        if self.player is None:
            return
        if self.player.turns_in_debt_tower > 0:
            self._log("Schuldturm: Ausbesserung nicht moeglich.")
            return
        ship = self._selected_ship()
        if ship is None:
            self._log("Kein Schiff ausgewaehlt.")
            return
        if ship.is_at_sea:
            self._log("Schiff ist auf See. Ausbesserung nicht moeglich.")
            return
        if ship.city != self.player.city:
            self._log("Schiff liegt nicht im aktuellen Hafen.")
            return

        if part == "hull":
            current = ship.hull
            label = "Rumpf"
            unit_cost = 16
        else:
            current = ship.rigging
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
            ship.hull += amount
        else:
            ship.rigging += amount
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
        total_capacity = sum(ship.cargo_capacity for ship in self.player.ships)
        heuer = int((140 + total_capacity // 4) * heuer_factor)
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

        self._resolve_fleet_travel()
        self.player.age += 1
        self._resolve_life_events()
        self._update_title()

        self.current_year += 1
        self.current_sea_state = self.rng.choice(SEA_STATES)
        self._refresh_economy_for_year()
        self._log(f"ANNO {self.current_year} beginnt: {self.current_sea_state}.")
        self._log(f"Atheria-Wirtschaft: {self.economy_state.summary}")

    def _resolve_fleet_travel(self) -> None:
        if self.player is None:
            return
        arrived: List[str] = []
        lost: List[str] = []
        for ship in list(self.player.ships):
            if not ship.is_at_sea or not ship.destination:
                continue
            if ship.travel_turns_left > 0:
                ship.travel_turns_left -= 1
            if ship.travel_turns_left > 0:
                ship.last_report = f"Auf See: noch {ship.travel_turns_left} Jahr(e) bis {ship.destination}."
                continue

            origin = ship.city
            target = ship.destination
            survived, event_summary = self._resolve_travel_risk(ship, origin, target)
            if not survived:
                lost.append(ship.display_name)
                self.player.ships.remove(ship)
                continue
            ship.city = target
            ship.is_at_sea = False
            ship.destination = None
            ship.travel_turns_left = 0
            ship.last_report = f"Ankunft in {target}."
            if event_summary:
                ship.last_report = f"{ship.last_report} {event_summary}"
            arrived.append(ship.display_name)
            self._storage_for_city(target)
            self.player.chronicle.append(
                f"ANNO {self.current_year}: {ship.display_name} in {target} angekommen."
            )

        for name in arrived:
            self._log(f"{name} ist sicher im Hafen angekommen.")
        for name in lost:
            self._log(f"{name} ist untergegangen.")
            self.player.chronicle.append(f"ANNO {self.current_year}: {name} ging verloren.")

        if not self.player.ships:
            self.player.alive = False
            self.player.chronicle.append(f"ANNO {self.current_year}: Keine Schiffe mehr.")
            self._log("Alle Schiffe verloren. Handelshaus endet.")
        if self.selected_fleet_ship >= len(self.player.ships):
            self.selected_fleet_ship = max(0, len(self.player.ships) - 1)

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
        cargo_value = 0
        for ship in player.ships:
            cargo_value += sum(prices[good] * qty for good, qty in ship.cargo.items())
        for goods in player.warehouses.values():
            cargo_value += sum(prices[good] * qty for good, qty in goods.items())
        fleet_value = sum(ship.value for ship in player.ships)
        return player.money + cargo_value + fleet_value - player.debt + player.reputation * 150

    def _log(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 200:
            self.messages = self.messages[-160:]


def run_pygame_game() -> int:
    app = PygameHanseApp()
    return app.run()
