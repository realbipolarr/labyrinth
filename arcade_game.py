from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

import arcade

from maze import EMPTY, Maze, Position, generate_maze, solve_maze, visible_cells


WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Labyrinth"
MAZE_WIDTH = 29
MAZE_HEIGHT = 29
CELL_SIZE = 54
PLAYER_RADIUS = CELL_SIZE * 0.24
MOVE_ANIMATION_SPEED = 9.0
AUTO_STEP_DELAY = 0.12
VISION_RADIUS = 4
FONT_DISPLAY = ("Avenir Next", "Avenir", "Futura", "Arial")


BACKGROUND_TOP = (12, 22, 36)
BACKGROUND_BOTTOM = (3, 8, 17)
PANEL_COLOR = (12, 18, 30, 220)
PANEL_BORDER = (84, 123, 163, 120)
VISIBLE_FLOOR = (53, 92, 105, 255)
EXPLORED_FLOOR = (24, 42, 54, 255)
VISIBLE_WALL = (120, 167, 181, 255)
EXPLORED_WALL = (41, 58, 74, 255)
PLAYER_CORE = (255, 216, 138, 255)
PLAYER_GLOW = (255, 170, 76, 70)
EXIT_COLOR = (119, 255, 194, 255)
EXIT_GLOW = (83, 227, 190, 50)
PATH_COLOR = (255, 207, 111, 110)
FOG_HIDDEN = (2, 5, 12, 235)
FOG_EXPLORED = (3, 8, 18, 168)
HUD_TEXT = (231, 239, 247, 255)
HUD_MUTED = (146, 169, 190, 255)
ACCENT = (255, 181, 92, 255)
SUCCESS = (130, 255, 187, 255)


class GameMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"


@dataclass
class GameState:
    maze: Maze
    mode: GameMode
    player_cell: Position
    steps: int = 0
    won: bool = False
    show_path_hint: bool = False


def mix_color(base: tuple[int, int, int, int], delta: int) -> tuple[int, int, int, int]:
    r, g, b, a = base
    return (
        min(255, max(0, r + delta)),
        min(255, max(0, g + delta)),
        min(255, max(0, b + delta)),
        a,
    )


def cell_noise(cell: Position) -> int:
    x, y = cell
    return ((x * 17 + y * 31) % 7) - 3


def grid_to_world(maze: Maze, cell: Position) -> tuple[float, float]:
    x, y = cell
    world_x = x * CELL_SIZE + CELL_SIZE / 2
    world_y = (maze.height - y - 1) * CELL_SIZE + CELL_SIZE / 2
    return world_x, world_y


def cell_rect(maze: Maze, cell: Position) -> arcade.Rect:
    world_x, world_y = grid_to_world(maze, cell)
    return arcade.XYWH(world_x, world_y, CELL_SIZE, CELL_SIZE)


def move_towards(current: tuple[float, float], target: tuple[float, float], speed: float, delta_time: float) -> tuple[float, float]:
    lerp = min(1.0, speed * delta_time)
    return (
        current[0] + (target[0] - current[0]) * lerp,
        current[1] + (target[1] - current[1]) * lerp,
    )


def is_close(a: tuple[float, float], b: tuple[float, float], tolerance: float = 1.0) -> bool:
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


class TitleView(arcade.View):
    def __init__(self) -> None:
        super().__init__(background_color=BACKGROUND_BOTTOM)
        self.selected_index = 0
        self.time = 0.0
        self.preview_maze = generate_maze(17, 17, seed=7)
        self.preview_path = solve_maze(self.preview_maze)
        self.options = [
            ("Автопрохождение", "Смотреть, как персонаж сам находит выход"),
            ("Ручное исследование", "Играть самому с туманом войны и памятью карты"),
        ]

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_BOTTOM)

    def on_update(self, delta_time: float) -> None:
        self.time += delta_time

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol in {arcade.key.W, arcade.key.UP}:
            self.selected_index = (self.selected_index - 1) % len(self.options)
        elif symbol in {arcade.key.S, arcade.key.DOWN}:
            self.selected_index = (self.selected_index + 1) % len(self.options)
        elif symbol == arcade.key.KEY_1:
            self.start_game(GameMode.AUTO)
        elif symbol == arcade.key.KEY_2:
            self.start_game(GameMode.MANUAL)
        elif symbol in {arcade.key.ENTER, arcade.key.SPACE}:
            mode = GameMode.AUTO if self.selected_index == 0 else GameMode.MANUAL
            self.start_game(mode)

    def start_game(self, mode: GameMode) -> None:
        self.window.show_view(LabyrinthView(mode))

    def on_draw(self) -> None:
        self.clear()
        self.draw_background()
        self.draw_preview_maze()
        self.draw_title()

    def draw_background(self) -> None:
        self.window.default_camera.use()
        width = self.window.width
        height_total = self.window.height
        bands = 18
        for index in range(bands):
            height = height_total / bands
            mix = index / max(1, bands - 1)
            color = (
                int(BACKGROUND_TOP[0] * (1 - mix) + BACKGROUND_BOTTOM[0] * mix),
                int(BACKGROUND_TOP[1] * (1 - mix) + BACKGROUND_BOTTOM[1] * mix),
                int(BACKGROUND_TOP[2] * (1 - mix) + BACKGROUND_BOTTOM[2] * mix),
                255,
            )
            rect = arcade.LBWH(0, height_total - (index + 1) * height, width, height + 2)
            arcade.draw_rect_filled(rect, color)

        glow_count = 6
        for index in range(glow_count):
            angle = self.time * 0.12 + index * 0.7
            x = width * (0.2 + 0.13 * index) + math.sin(angle) * 90
            y = height_total * (0.25 + 0.1 * index) + math.cos(angle * 1.4) * 40
            radius = 110 + index * 26
            color = (32, 78, 98, max(12, 40 - index * 4))
            arcade.draw_circle_filled(x, y, radius, color)

    def draw_preview_maze(self) -> None:
        origin_x = self.window.width - 520
        origin_y = 140
        scale = 16
        for y, row in enumerate(self.preview_maze.grid):
            for x, cell in enumerate(row):
                screen_x = origin_x + x * scale
                screen_y = origin_y + (self.preview_maze.height - y - 1) * scale
                rect = arcade.LBWH(screen_x, screen_y, scale - 1, scale - 1)
                if (x, y) in self.preview_path:
                    arcade.draw_rect_filled(rect, (245, 187, 84, 110))
                elif cell == EMPTY:
                    arcade.draw_rect_filled(rect, (53, 92, 105, 180))
                else:
                    arcade.draw_rect_filled(rect, (24, 38, 58, 190))

    def draw_title(self) -> None:
        left = 130
        top = self.window.height - 150
        arcade.draw_text(
            "LABYRINTH",
            left,
            top,
            (240, 246, 252, 255),
            font_size=56,
            font_name=FONT_DISPLAY,
            bold=True,
        )
        arcade.draw_text(
            "Аркадная версия с атмосферой, туманом войны и плавным движением",
            left,
            top - 48,
            HUD_MUTED,
            font_size=20,
            font_name=FONT_DISPLAY,
        )

        panel = arcade.LBWH(left - 30, 150, 700, 320)
        arcade.draw_rect_filled(panel, PANEL_COLOR)
        arcade.draw_rect_outline(panel, PANEL_BORDER, border_width=2)

        for index, (title, subtitle) in enumerate(self.options):
            y = 395 - index * 110
            is_selected = index == self.selected_index
            option_rect = arcade.LBWH(left, y - 36, 585, 78)
            fill = (255, 176, 74, 54) if is_selected else (16, 26, 40, 140)
            border = ACCENT if is_selected else (63, 95, 122, 90)
            arcade.draw_rect_filled(option_rect, fill)
            arcade.draw_rect_outline(option_rect, border, border_width=2)
            arcade.draw_text(
                f"{index + 1}. {title}",
                left + 26,
                y + 6,
                HUD_TEXT if is_selected else (207, 219, 233, 255),
                font_size=26,
                font_name=FONT_DISPLAY,
                bold=is_selected,
            )
            arcade.draw_text(
                subtitle,
                left + 26,
                y - 22,
                HUD_MUTED,
                font_size=15,
                font_name=FONT_DISPLAY,
            )

        arcade.draw_text(
            "W/S или стрелки для выбора, Enter для старта",
            left,
            110,
            HUD_MUTED,
            font_size=16,
            font_name=FONT_DISPLAY,
        )


class LabyrinthView(arcade.View):
    def __init__(self, mode: GameMode) -> None:
        super().__init__(background_color=BACKGROUND_BOTTOM)
        self.game_camera = arcade.Camera2D()
        self.mode = mode
        self.state = self._create_state(mode)
        self.solution_path = solve_maze(self.state.maze)
        self.visible_cells: set[Position] = set()
        self.explored_cells: set[Position] = set()
        self.player_draw_position = grid_to_world(self.state.maze, self.state.player_cell)
        self.auto_path_index = 0
        self.auto_step_timer = 0.0
        self.time = 0.0
        self.status_message = "Найдите выход из лабиринта."
        self._refresh_visibility()

    def _create_state(self, mode: GameMode) -> GameState:
        maze = generate_maze(MAZE_WIDTH, MAZE_HEIGHT)
        return GameState(maze=maze, mode=mode, player_cell=maze.start)

    def regenerate(self) -> None:
        self.state = self._create_state(self.mode)
        self.solution_path = solve_maze(self.state.maze)
        self.visible_cells = set()
        self.explored_cells = set()
        self.player_draw_position = grid_to_world(self.state.maze, self.state.player_cell)
        self.auto_path_index = 0
        self.auto_step_timer = 0.0
        self.status_message = "Новый лабиринт готов."
        self._refresh_visibility()

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_BOTTOM)

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self.game_camera.match_window()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(TitleView())
            return

        if symbol == arcade.key.R:
            self.regenerate()
            return

        if symbol == arcade.key.H:
            self.state.show_path_hint = not self.state.show_path_hint
            return

        if self.state.mode != GameMode.MANUAL or self.state.won:
            return

        if not is_close(self.player_draw_position, grid_to_world(self.state.maze, self.state.player_cell), tolerance=0.6):
            return

        movement = {
            arcade.key.W: (0, -1),
            arcade.key.UP: (0, -1),
            arcade.key.S: (0, 1),
            arcade.key.DOWN: (0, 1),
            arcade.key.A: (-1, 0),
            arcade.key.LEFT: (-1, 0),
            arcade.key.D: (1, 0),
            arcade.key.RIGHT: (1, 0),
        }.get(symbol)

        if movement is None:
            return

        next_cell = (self.state.player_cell[0] + movement[0], self.state.player_cell[1] + movement[1])
        if self.state.maze.is_open(next_cell):
            self.state.player_cell = next_cell
            self.state.steps += 1
            self.status_message = "Продвигайтесь к выходу."
            self._refresh_visibility()
            self._check_win()

    def on_update(self, delta_time: float) -> None:
        self.time += delta_time
        self._update_auto_mode(delta_time)
        target_position = grid_to_world(self.state.maze, self.state.player_cell)
        self.player_draw_position = move_towards(
            self.player_draw_position,
            target_position,
            MOVE_ANIMATION_SPEED,
            delta_time,
        )
        self._update_camera(delta_time)

    def _update_auto_mode(self, delta_time: float) -> None:
        if self.state.mode != GameMode.AUTO or self.state.won or not self.solution_path:
            return

        if not is_close(self.player_draw_position, grid_to_world(self.state.maze, self.state.player_cell), tolerance=0.8):
            return

        self.auto_step_timer += delta_time
        if self.auto_step_timer < AUTO_STEP_DELAY:
            return

        self.auto_step_timer = 0.0
        if self.auto_path_index + 1 >= len(self.solution_path):
            return

        self.auto_path_index += 1
        self.state.player_cell = self.solution_path[self.auto_path_index]
        self.state.steps = self.auto_path_index
        self.status_message = "ИИ уверенно ищет кратчайший путь."
        self._refresh_visibility()
        self._check_win()

    def _update_camera(self, delta_time: float) -> None:
        current = self.game_camera.position
        target = self.player_draw_position
        self.game_camera.position = move_towards(current, target, 4.0, delta_time)

    def _refresh_visibility(self) -> None:
        visible = visible_cells(self.state.maze, self.state.player_cell, radius=VISION_RADIUS)
        self.visible_cells = visible
        self.explored_cells.update(visible)

    def _check_win(self) -> None:
        if self.state.player_cell == self.state.maze.exit:
            self.state.won = True
            self.status_message = "Выход найден."

    def on_draw(self) -> None:
        self.clear()
        self.draw_background()
        self.game_camera.use()
        self.draw_maze()
        self.draw_goal()
        self.draw_path()
        self.draw_player()
        self.draw_fog()
        self.window.default_camera.use()
        self.draw_hud()

    def draw_background(self) -> None:
        self.window.default_camera.use()
        bands = 20
        for index in range(bands):
            height = self.window.height / bands
            mix = index / max(1, bands - 1)
            color = (
                int(BACKGROUND_TOP[0] * (1 - mix) + BACKGROUND_BOTTOM[0] * mix),
                int(BACKGROUND_TOP[1] * (1 - mix) + BACKGROUND_BOTTOM[1] * mix),
                int(BACKGROUND_TOP[2] * (1 - mix) + BACKGROUND_BOTTOM[2] * mix),
                255,
            )
            rect = arcade.LBWH(0, self.window.height - (index + 1) * height, self.window.width, height + 2)
            arcade.draw_rect_filled(rect, color)

    def draw_maze(self) -> None:
        for y, row in enumerate(self.state.maze.grid):
            for x, cell in enumerate(row):
                position = (x, y)
                if position not in self.explored_cells:
                    continue

                base_color = self.pick_tile_color(position, cell)
                arcade.draw_rect_filled(cell_rect(self.state.maze, position), base_color)

                if position in self.visible_cells and cell != EMPTY:
                    left, bottom, width, height = cell_rect(self.state.maze, position).lbwh
                    arcade.draw_line(left, bottom + height, left + width, bottom + height, (212, 242, 255, 55), 2)
                    arcade.draw_line(left, bottom, left, bottom + height, (212, 242, 255, 40), 2)

    def pick_tile_color(self, position: Position, cell: str) -> tuple[int, int, int, int]:
        visible = position in self.visible_cells
        noise = cell_noise(position) * 3
        if cell == EMPTY:
            base = VISIBLE_FLOOR if visible else EXPLORED_FLOOR
        else:
            base = VISIBLE_WALL if visible else EXPLORED_WALL
        return mix_color(base, noise)

    def draw_goal(self) -> None:
        if self.state.maze.exit not in self.explored_cells:
            return

        center_x, center_y = grid_to_world(self.state.maze, self.state.maze.exit)
        pulse = 8 * math.sin(self.time * 2.7)
        arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.28 + pulse * 0.08, EXIT_GLOW)
        arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.17, EXIT_COLOR)

    def draw_path(self) -> None:
        if self.state.mode == GameMode.AUTO:
            path = self.solution_path[max(0, self.auto_path_index - 1) :]
        elif self.state.show_path_hint:
            path = self.solution_path
        else:
            return

        for cell in path:
            if cell not in self.explored_cells:
                continue
            center_x, center_y = grid_to_world(self.state.maze, cell)
            arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.09, PATH_COLOR)

    def draw_player(self) -> None:
        center_x, center_y = self.player_draw_position
        for multiplier, alpha in ((2.8, 26), (2.1, 48), (1.5, 68)):
            arcade.draw_circle_filled(center_x, center_y, PLAYER_RADIUS * multiplier, (PLAYER_GLOW[0], PLAYER_GLOW[1], PLAYER_GLOW[2], alpha))
        arcade.draw_circle_filled(center_x, center_y, PLAYER_RADIUS, PLAYER_CORE)
        arcade.draw_circle_filled(center_x - 4, center_y + 4, PLAYER_RADIUS * 0.23, (255, 245, 220, 220))

    def draw_fog(self) -> None:
        for y in range(self.state.maze.height):
            for x in range(self.state.maze.width):
                position = (x, y)
                rect = cell_rect(self.state.maze, position)
                if position not in self.explored_cells:
                    arcade.draw_rect_filled(rect, FOG_HIDDEN)
                elif position not in self.visible_cells:
                    arcade.draw_rect_filled(rect, FOG_EXPLORED)

    def draw_hud(self) -> None:
        panel = arcade.LBWH(28, self.window.height - 166, 420, 132)
        arcade.draw_rect_filled(panel, PANEL_COLOR)
        arcade.draw_rect_outline(panel, PANEL_BORDER, border_width=2)

        title = "Автопрохождение" if self.state.mode == GameMode.AUTO else "Ручное исследование"
        arcade.draw_text(title, 50, self.window.height - 78, HUD_TEXT, 28, font_name=FONT_DISPLAY, bold=True)
        arcade.draw_text(
            f"Шаги: {self.state.steps}   Туман: {len(self.visible_cells)} клеток в обзоре",
            50,
            self.window.height - 112,
            HUD_MUTED,
            16,
            font_name=FONT_DISPLAY,
        )
        arcade.draw_text(self.status_message, 50, self.window.height - 138, ACCENT if not self.state.won else SUCCESS, 16, font_name=FONT_DISPLAY)

        help_panel = arcade.LBWH(self.window.width - 360, self.window.height - 166, 332, 132)
        arcade.draw_rect_filled(help_panel, (8, 14, 24, 205))
        arcade.draw_rect_outline(help_panel, (61, 93, 122, 95), border_width=2)
        controls = [
            "WASD / стрелки: движение",
            "H: показать путь",
            "R: новый лабиринт",
            "Esc: в меню",
        ]
        for index, line in enumerate(controls):
            arcade.draw_text(
                line,
                self.window.width - 336,
                self.window.height - 82 - index * 24,
                HUD_MUTED if index else HUD_TEXT,
                15,
                font_name=FONT_DISPLAY,
            )

        if self.state.won:
            self.draw_win_overlay()

    def draw_win_overlay(self) -> None:
        overlay = arcade.LBWH(self.window.width / 2 - 250, self.window.height / 2 - 110, 500, 220)
        arcade.draw_rect_filled(overlay, (8, 12, 18, 235))
        arcade.draw_rect_outline(overlay, SUCCESS, border_width=2)
        arcade.draw_text(
            "Выбрались из лабиринта",
            self.window.width / 2,
            self.window.height / 2 + 42,
            HUD_TEXT,
            34,
            anchor_x="center",
            font_name=FONT_DISPLAY,
            bold=True,
        )
        arcade.draw_text(
            f"Шагов сделано: {self.state.steps}",
            self.window.width / 2,
            self.window.height / 2,
            SUCCESS,
            22,
            anchor_x="center",
            font_name=FONT_DISPLAY,
        )
        arcade.draw_text(
            "R — сыграть ещё раз, Esc — вернуться в меню",
            self.window.width / 2,
            self.window.height / 2 - 42,
            HUD_MUTED,
            16,
            anchor_x="center",
            font_name=FONT_DISPLAY,
        )


def create_window(*, visible: bool = True) -> arcade.Window:
    return arcade.Window(
        WINDOW_WIDTH,
        WINDOW_HEIGHT,
        WINDOW_TITLE,
        antialiasing=True,
        visible=visible,
        resizable=True,
    )


def run() -> None:
    window = create_window()
    window.show_view(TitleView())
    arcade.run()
