from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
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
PANEL_INNER = (26, 42, 58, 70)
PANEL_SOFT = (17, 27, 40, 200)
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


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


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


@lru_cache(maxsize=256)
def measure_text_width(text: str, font_size: int, font_name: tuple[str, ...], bold: bool = False) -> float:
    return arcade.Text(text, 0, 0, font_size=font_size, font_name=font_name, bold=bold).content_width


def fit_text_size(
    text: str,
    *,
    preferred: int,
    minimum: int,
    max_width: float,
    font_name: tuple[str, ...],
    bold: bool = False,
) -> int:
    for size in range(preferred, minimum - 1, -1):
        if measure_text_width(text, size, font_name, bold) <= max_width:
            return size
    return minimum


def inset_rect(rect: arcade.Rect, inset_x: float, inset_y: float) -> arcade.Rect:
    return arcade.LBWH(rect.left + inset_x, rect.bottom + inset_y, rect.width - inset_x * 2, rect.height - inset_y * 2)


def draw_glass_panel(
    rect: arcade.Rect,
    *,
    fill_color: tuple[int, int, int, int] = PANEL_COLOR,
    border_color: tuple[int, int, int, int] = PANEL_BORDER,
    accent_color: tuple[int, int, int, int] = ACCENT,
) -> None:
    arcade.draw_rect_filled(rect, fill_color)
    arcade.draw_rect_filled(inset_rect(rect, 8, 8), PANEL_INNER)
    arcade.draw_rect_outline(rect, border_color, border_width=2)
    arcade.draw_rect_filled(arcade.LBWH(rect.left, rect.top - 4, rect.width, 4), accent_color[:3] + (70,))
    arcade.draw_line(rect.left + 18, rect.top - 18, rect.left + 72, rect.top - 18, accent_color[:3] + (140,), 2)
    arcade.draw_line(rect.right - 72, rect.bottom + 18, rect.right - 18, rect.bottom + 18, border_color[:3] + (110,), 2)


def draw_stat_chip(rect: arcade.Rect, label: str, value: str, accent: tuple[int, int, int, int]) -> None:
    arcade.draw_rect_filled(rect, PANEL_SOFT)
    arcade.draw_rect_outline(rect, accent[:3] + (90,), border_width=1)
    arcade.draw_text(
        label,
        rect.left + 18,
        rect.top - 12,
        HUD_MUTED,
        font_size=10,
        font_name=FONT_DISPLAY,
        anchor_y="top",
    )
    value_font_size = 19 if len(value) <= 4 else 17
    arcade.draw_text(
        value,
        rect.left + 18,
        rect.bottom + 14,
        accent,
        font_size=value_font_size,
        font_name=FONT_DISPLAY,
        bold=True,
        anchor_y="bottom",
    )


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
        title_size = fit_text_size(
            "Аркадная версия с атмосферой, туманом войны и плавным движением",
            preferred=20,
            minimum=15,
            max_width=self.window.width - left - 180,
            font_name=FONT_DISPLAY,
        )
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
            font_size=title_size,
            font_name=FONT_DISPLAY,
        )

        panel = arcade.LBWH(left - 30, 150, 700, 320)
        draw_glass_panel(panel, accent_color=(82, 147, 255, 255))

        for index, (title, subtitle) in enumerate(self.options):
            y = 395 - index * 110
            is_selected = index == self.selected_index
            option_rect = arcade.LBWH(left, y - 36, 585, 78)
            fill = (255, 176, 74, 54) if is_selected else (16, 26, 40, 140)
            border = ACCENT if is_selected else (63, 95, 122, 90)
            draw_glass_panel(option_rect, fill_color=fill, border_color=border, accent_color=border if is_selected else (70, 120, 158, 255))
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
        self.draw_maze_backdrop()
        self.draw_maze()
        self.draw_goal()
        self.draw_path()
        self.draw_player_light()
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

        for index in range(9):
            angle = self.time * 0.1 + index * 0.8
            radius = 140 + index * 18
            x = self.window.width * (0.15 + 0.08 * index) + math.sin(angle) * 34
            y = self.window.height * (0.16 + 0.07 * index) + math.cos(angle * 1.6) * 22
            arcade.draw_circle_filled(x, y, radius, (20, 58, 74, max(10, 32 - index * 2)))

    def draw_maze_backdrop(self) -> None:
        maze_width = self.state.maze.width * CELL_SIZE
        maze_height = self.state.maze.height * CELL_SIZE
        backdrop = arcade.LBWH(-CELL_SIZE * 0.85, -CELL_SIZE * 0.85, maze_width + CELL_SIZE * 1.7, maze_height + CELL_SIZE * 1.7)
        arcade.draw_rect_filled(backdrop, (6, 11, 22, 210))
        arcade.draw_rect_outline(backdrop, (50, 77, 102, 100), border_width=3)
        inner = inset_rect(backdrop, CELL_SIZE * 0.28, CELL_SIZE * 0.28)
        arcade.draw_rect_outline(inner, (96, 141, 170, 45), border_width=2)

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

    def draw_player_light(self) -> None:
        center_x, center_y = self.player_draw_position
        for radius, alpha in (
            (CELL_SIZE * (VISION_RADIUS + 1.4), 12),
            (CELL_SIZE * (VISION_RADIUS + 0.8), 20),
            (CELL_SIZE * (VISION_RADIUS * 0.9), 28),
        ):
            arcade.draw_circle_filled(center_x, center_y, radius, (255, 176, 72, alpha))

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
        margin = 28
        panel_width = clamp(self.window.width * 0.42, 460, 650)
        panel_height = 246
        panel = arcade.LBWH(margin, self.window.height - panel_height - margin, panel_width, panel_height)
        draw_glass_panel(panel)

        padding = 28
        title = "Автопрохождение" if self.state.mode == GameMode.AUTO else "Ручное исследование"
        title_font = fit_text_size(
            title,
            preferred=28,
            minimum=18,
            max_width=panel.width - padding * 2,
            font_name=FONT_DISPLAY,
            bold=True,
        )
        arcade.draw_text(
            title,
            panel.left + padding,
            panel.top - 24,
            HUD_TEXT,
            title_font,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )

        title_y = panel.top - 24
        chips_top = title_y - title_font - 30
        chip_gap = 18
        chip_width = (panel.width - padding * 2 - chip_gap) / 2
        chip_height = 72
        chip_bottom = chips_top - chip_height
        draw_stat_chip(
            arcade.LBWH(panel.left + padding, chip_bottom, chip_width, chip_height),
            "Шаги",
            str(self.state.steps),
            ACCENT,
        )
        draw_stat_chip(
            arcade.LBWH(panel.left + padding + chip_width + chip_gap, chip_bottom, chip_width, chip_height),
            "Обзор",
            f"{len(self.visible_cells)} клеток",
            (112, 201, 255, 255),
        )
        helper_bottom = panel.bottom + 52
        status_bottom = panel.bottom + 16
        arcade.draw_text(
            "Свет вокруг героя показывает текущую зону видимости.",
            panel.left + padding,
            helper_bottom,
            HUD_MUTED,
            13,
            width=int(panel.width - padding * 2),
            multiline=True,
            anchor_y="bottom",
            font_name=FONT_DISPLAY,
        )
        arcade.draw_text(
            self.status_message,
            panel.left + padding,
            status_bottom,
            ACCENT if not self.state.won else SUCCESS,
            17,
            width=int(panel.width - padding * 2),
            multiline=True,
            anchor_y="bottom",
            font_name=FONT_DISPLAY,
        )

        help_panel_width = clamp(self.window.width * 0.26, 320, 390)
        help_panel = arcade.LBWH(self.window.width - help_panel_width - margin, self.window.height - panel_height - margin, help_panel_width, panel_height)
        draw_glass_panel(help_panel, fill_color=(8, 14, 24, 205), border_color=(61, 93, 122, 95), accent_color=(100, 162, 214, 255))
        arcade.draw_text(
            "Управление",
            help_panel.left + 24,
            help_panel.top - 24,
            HUD_TEXT,
            22,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )
        controls = [
            "WASD / стрелки: движение",
            "H: показать путь",
            "R: новый лабиринт",
            "Esc: в меню",
        ]
        for index, line in enumerate(controls):
            arcade.draw_text(
                line,
                help_panel.left + 24,
                help_panel.top - 70 - index * 36,
                HUD_MUTED if index else HUD_TEXT,
                14,
                width=int(help_panel.width - 48),
                font_name=FONT_DISPLAY,
                anchor_y="top",
            )

        if self.state.won:
            self.draw_win_overlay()

    def draw_win_overlay(self) -> None:
        overlay = arcade.LBWH(self.window.width / 2 - 290, self.window.height / 2 - 120, 580, 240)
        draw_glass_panel(overlay, fill_color=(8, 12, 18, 235), border_color=SUCCESS, accent_color=SUCCESS)
        title_font = fit_text_size(
            "Выбрались из лабиринта",
            preferred=34,
            minimum=24,
            max_width=overlay.width - 56,
            font_name=FONT_DISPLAY,
            bold=True,
        )
        arcade.draw_text(
            "Выбрались из лабиринта",
            self.window.width / 2,
            overlay.top - 46,
            HUD_TEXT,
            title_font,
            anchor_x="center",
            anchor_y="top",
            font_name=FONT_DISPLAY,
            bold=True,
        )
        arcade.draw_text(
            f"Шагов сделано: {self.state.steps}",
            self.window.width / 2,
            overlay.bottom + 102,
            SUCCESS,
            22,
            anchor_x="center",
            anchor_y="bottom",
            font_name=FONT_DISPLAY,
        )
        arcade.draw_text(
            "R — сыграть ещё раз, Esc — вернуться в меню",
            self.window.width / 2,
            overlay.bottom + 48,
            HUD_MUTED,
            16,
            anchor_x="center",
            anchor_y="bottom",
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
