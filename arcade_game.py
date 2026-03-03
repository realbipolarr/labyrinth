from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import math
import random

import arcade
from arcade.types import Color
from PIL import Image, ImageDraw

from maze import EMPTY, WALL, Maze, Position, generate_maze, solve_maze


WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Labyrinth"
MAZE_WIDTH = 29
MAZE_HEIGHT = 29
CELL_SIZE = 54
PLAYER_RADIUS = CELL_SIZE * 0.24
MOVE_ANIMATION_SPEED = 9.0
AUTO_STEP_DELAY = 0.12
BASE_VISION_RADIUS = 4
SHARD_VISION_BONUS = 1
SHARD_COUNT = 3
TRAP_COUNT = 3
TEXTURE_SIZE = 64
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
EXIT_LOCKED = (255, 145, 99, 255)
EXIT_LOCKED_GLOW = (255, 127, 70, 52)
PATH_COLOR = (255, 207, 111, 110)
SHARD_CORE = (106, 219, 255, 255)
SHARD_GLOW = (72, 190, 255, 60)
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
    shard_positions: tuple[Position, ...]
    key_position: Position | None = None
    door_position: Position | None = None
    trap_positions: tuple[Position, ...] = ()
    collected_shards: set[Position] = field(default_factory=set)
    triggered_traps: set[Position] = field(default_factory=set)
    has_key: bool = False
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


def to_color(value: tuple[int, int, int, int]) -> Color:
    return Color(*value)


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


def progress_hint(shards_remaining: int, *, auto: bool = False) -> str:
    if shards_remaining <= 0:
        return "Все осколки собраны. Ищите выход." if not auto else "Все осколки собраны. ИИ идёт к выходу."
    return "Продвигайтесь к следующему осколку." if not auto else "ИИ собирает осколки и открывает путь."


def open_floor_cells(maze: Maze) -> list[Position]:
    return [
        (x, y)
        for y, row in enumerate(maze.grid)
        for x, cell in enumerate(row)
        if cell == EMPTY
    ]


def pick_shard_positions(maze: Maze, count: int = SHARD_COUNT, seed: int | None = None) -> tuple[Position, ...]:
    rng = random.Random(seed)
    blocked = {maze.start, maze.exit}
    candidates = [
        cell
        for cell in open_floor_cells(maze)
        if cell not in blocked and abs(cell[0] - maze.start[0]) + abs(cell[1] - maze.start[1]) > 5
    ]
    if len(candidates) < count:
        candidates = [cell for cell in open_floor_cells(maze) if cell not in blocked]
    rng.shuffle(candidates)
    return tuple(candidates[:count])


def pick_key_position(
    maze: Maze,
    forbidden: set[Position],
    seed: int | None = None,
) -> Position | None:
    rng = random.Random(seed)
    candidates = [
        cell
        for cell in open_floor_cells(maze)
        if cell not in forbidden and abs(cell[0] - maze.start[0]) + abs(cell[1] - maze.start[1]) > 4
    ]
    if not candidates:
        return None
    rng.shuffle(candidates)
    return candidates[0]


def pick_door_position(maze: Maze, seed: int | None = None) -> Position | None:
    rng = random.Random(seed)
    candidates: list[Position] = []
    for y in range(1, maze.height - 1):
        for x in range(1, maze.width - 1):
            if maze.grid[y][x] != WALL:
                continue
            horizontal = maze.is_open((x - 1, y)) and maze.is_open((x + 1, y))
            vertical = maze.is_open((x, y - 1)) and maze.is_open((x, y + 1))
            if horizontal or vertical:
                candidates.append((x, y))

    if not candidates:
        return None

    candidates.sort(key=lambda pos: abs(pos[0] - maze.start[0]) + abs(pos[1] - maze.start[1]), reverse=True)
    top_slice = candidates[: max(1, min(24, len(candidates)))]
    return rng.choice(top_slice)


def pick_trap_positions(
    maze: Maze,
    forbidden: set[Position],
    route: list[Position],
    count: int = TRAP_COUNT,
    seed: int | None = None,
) -> tuple[Position, ...]:
    rng = random.Random(seed)
    route_set = set(route)
    candidates = [
        cell
        for cell in open_floor_cells(maze)
        if cell not in forbidden and cell not in route_set and abs(cell[0] - maze.start[0]) + abs(cell[1] - maze.start[1]) > 3
    ]
    if len(candidates) < count:
        candidates = [cell for cell in open_floor_cells(maze) if cell not in forbidden and cell not in route_set]
    rng.shuffle(candidates)
    return tuple(candidates[:count])


def _append_segment(route: list[Position], segment: list[Position]) -> None:
    if not segment:
        return
    if not route:
        route.extend(segment)
    else:
        route.extend(segment[1:])


def build_objective_route(
    maze: Maze,
    start: Position,
    exit_cell: Position,
    shards: tuple[Position, ...],
) -> list[Position]:
    remaining = list(shards)
    current = start
    route: list[Position] = [start]

    while remaining:
        best_target: Position | None = None
        best_path: list[Position] = []
        best_length: int | None = None

        for target in remaining:
            path = solve_maze(maze, current, target)
            if not path:
                continue
            if best_length is None or len(path) < best_length:
                best_target = target
                best_path = path
                best_length = len(path)

        if best_target is None:
            break

        _append_segment(route, best_path)
        current = best_target
        remaining.remove(best_target)

    _append_segment(route, solve_maze(maze, current, exit_cell))
    return route


def _texture_base() -> Image.Image:
    return Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (255, 255, 255, 255))


@lru_cache(maxsize=None)
def get_floor_texture(variant: int = 0) -> arcade.Texture:
    image = _texture_base()
    draw = ImageDraw.Draw(image)
    tint = 228 - variant * 8
    draw.rectangle((0, 0, TEXTURE_SIZE - 1, TEXTURE_SIZE - 1), fill=(tint, tint, tint, 255))
    for offset in range(8, TEXTURE_SIZE, 14):
        draw.line((offset, 0, offset - 8, TEXTURE_SIZE), fill=(175, 175, 175, 42), width=2)
    for y in (10, 31, 49):
        draw.line((0, y, TEXTURE_SIZE, y + variant), fill=(150, 150, 150, 55), width=2)
    draw.line((12, 44, 25, 34, 36, 42, 50, 28), fill=(120, 120, 120, 80), width=2)
    return arcade.Texture(image, hash=f"floor:{variant}")


@lru_cache(maxsize=None)
def get_wall_texture(variant: int = 0) -> arcade.Texture:
    image = _texture_base()
    draw = ImageDraw.Draw(image)
    base = 188 - variant * 12
    draw.rectangle((0, 0, TEXTURE_SIZE - 1, TEXTURE_SIZE - 1), fill=(base, base, base, 255))
    brick_h = 16
    for row in range(0, TEXTURE_SIZE, brick_h):
        shift = 8 if (row // brick_h) % 2 else 0
        draw.line((0, row, TEXTURE_SIZE, row), fill=(120, 120, 120, 120), width=2)
        for x in range(-shift, TEXTURE_SIZE, 16):
            draw.line((x + shift, row, x + shift, min(TEXTURE_SIZE, row + brick_h)), fill=(110, 110, 110, 100), width=2)
    draw.rectangle((6, 6, TEXTURE_SIZE - 7, TEXTURE_SIZE - 7), outline=(220, 220, 220, 28), width=1)
    return arcade.Texture(image, hash=f"wall:{variant}")


@lru_cache(maxsize=None)
def get_door_texture(opened: bool) -> arcade.Texture:
    image = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if opened:
        draw.rounded_rectangle((8, 6, TEXTURE_SIZE - 8, TEXTURE_SIZE - 8), radius=12, outline=(255, 255, 255, 180), width=4)
        draw.line((TEXTURE_SIZE / 2, 10, TEXTURE_SIZE / 2, TEXTURE_SIZE - 10), fill=(255, 255, 255, 90), width=3)
    else:
        draw.rounded_rectangle((10, 6, TEXTURE_SIZE - 10, TEXTURE_SIZE - 6), radius=10, fill=(220, 220, 220, 255), outline=(90, 90, 90, 255), width=4)
        for x in (20, 32, 44):
            draw.line((x, 10, x, TEXTURE_SIZE - 12), fill=(70, 70, 70, 180), width=3)
        draw.ellipse((45, 29, 51, 35), fill=(40, 40, 40, 255))
    return arcade.Texture(image, hash=f"door:{int(opened)}")


@lru_cache(maxsize=None)
def get_key_texture() -> arcade.Texture:
    image = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 20, 26, 38), outline=(255, 255, 255, 255), width=5)
    draw.line((25, 29, 48, 29), fill=(255, 255, 255, 255), width=5)
    draw.line((40, 29, 40, 22), fill=(255, 255, 255, 255), width=5)
    draw.line((47, 29, 47, 36), fill=(255, 255, 255, 255), width=5)
    return arcade.Texture(image, hash="key")


@lru_cache(maxsize=None)
def get_trap_texture() -> arcade.Texture:
    image = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(((32, 6), (38, 24), (58, 24), (42, 36), (48, 56), (32, 44), (16, 56), (22, 36), (6, 24), (26, 24)), fill=(255, 255, 255, 220))
    draw.ellipse((24, 24, 40, 40), fill=(50, 50, 50, 200))
    return arcade.Texture(image, hash="trap")


@lru_cache(maxsize=None)
def get_shard_texture() -> arcade.Texture:
    image = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(((32, 6), (50, 26), (40, 54), (24, 54), (14, 26)), fill=(255, 255, 255, 240), outline=(210, 210, 210, 255))
    draw.polygon(((32, 14), (42, 28), (36, 46), (28, 46), (22, 28)), fill=(205, 205, 205, 160))
    return arcade.Texture(image, hash="shard")


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
        self.solution_path = build_objective_route(
            self.state.maze,
            self.state.player_cell,
            self.state.maze.exit,
            self.state.shard_positions,
        )
        self.visible_cells: set[Position] = set()
        self.explored_cells: set[Position] = set()
        self.player_draw_position = grid_to_world(self.state.maze, self.state.player_cell)
        self.auto_path_index = 0
        self.auto_step_timer = 0.0
        self.time = 0.0
        self.status_message = "Соберите осколки и откройте выход."
        self._refresh_visibility()

    def _create_state(self, mode: GameMode) -> GameState:
        maze = generate_maze(MAZE_WIDTH, MAZE_HEIGHT)
        shard_positions = pick_shard_positions(maze)
        key_position = pick_key_position(maze, {maze.start, maze.exit, *shard_positions})
        route = build_objective_route(maze, maze.start, maze.exit, shard_positions)
        trap_positions = pick_trap_positions(
            maze,
            {maze.start, maze.exit, *shard_positions} | ({key_position} if key_position else set()),
            route,
        )
        return GameState(
            maze=maze,
            mode=mode,
            player_cell=maze.start,
            shard_positions=shard_positions,
            key_position=key_position,
            door_position=pick_door_position(maze),
            trap_positions=trap_positions,
        )

    def regenerate(self) -> None:
        self.state = self._create_state(self.mode)
        self.solution_path = build_objective_route(
            self.state.maze,
            self.state.player_cell,
            self.state.maze.exit,
            self.state.shard_positions,
        )
        self.visible_cells = set()
        self.explored_cells = set()
        self.player_draw_position = grid_to_world(self.state.maze, self.state.player_cell)
        self.auto_path_index = 0
        self.auto_step_timer = 0.0
        self.status_message = "Новый лабиринт готов. Ищите осколки."
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
        self._move_player(next_cell, auto=False)

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
        self._move_player(self.solution_path[self.auto_path_index], auto=True, count_step=False)

    def _update_camera(self, delta_time: float) -> None:
        current = self.game_camera.position
        target = self.player_draw_position
        self.game_camera.position = move_towards(current, target, 4.0, delta_time)

    def is_walkable(self, position: Position) -> bool:
        if self.state.maze.is_open(position):
            return True
        return self.state.has_key and self.state.door_position == position

    def _refresh_visibility(self) -> None:
        visible = self._visible_cells(self.state.player_cell, self.current_vision_radius)
        self.visible_cells = visible
        self.explored_cells.update(visible)

    def _visible_cells(self, origin: Position, radius: int) -> set[Position]:
        queue: list[tuple[Position, int]] = [(origin, 0)]
        seen = {origin}
        visible = {origin}
        directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]

        while queue:
            current, distance = queue.pop(0)
            if distance >= radius:
                continue

            x, y = current
            for dx, dy in directions:
                nxt = (x + dx, y + dy)
                if nxt in seen or not self.state.maze.in_bounds(nxt):
                    continue
                seen.add(nxt)
                visible.add(nxt)
                if self.is_walkable(nxt):
                    queue.append((nxt, distance + 1))

        return visible

    @property
    def current_vision_radius(self) -> int:
        return BASE_VISION_RADIUS + len(self.state.collected_shards) * SHARD_VISION_BONUS

    @property
    def shards_remaining(self) -> int:
        return len(self.state.shard_positions) - len(self.state.collected_shards)

    @property
    def exit_unlocked(self) -> bool:
        return self.shards_remaining == 0

    def _collect_shard_if_needed(self) -> str | None:
        player_cell = self.state.player_cell
        if player_cell not in self.state.shard_positions or player_cell in self.state.collected_shards:
            return None

        self.state.collected_shards.add(player_cell)
        if self.exit_unlocked:
            return "Все осколки собраны. Ищите выход."
        return f"Осколок найден. Осталось: {self.shards_remaining}."

    def _collect_key_if_needed(self) -> str | None:
        if self.state.key_position is None or self.state.has_key or self.state.player_cell != self.state.key_position:
            return None
        self.state.has_key = True
        return "Ключ найден. Древняя дверь открыта."

    def _trigger_trap_if_needed(self) -> str | None:
        if self.state.player_cell not in self.state.trap_positions or self.state.player_cell in self.state.triggered_traps:
            return None

        self.state.triggered_traps.add(self.state.player_cell)
        self.state.steps += 5
        self.state.player_cell = self.state.maze.start
        self.player_draw_position = grid_to_world(self.state.maze, self.state.player_cell)
        return "Ловушка сработала. Вас отбросило к старту."

    def _move_player(self, next_cell: Position, *, auto: bool, count_step: bool = True) -> None:
        if not self.state.maze.in_bounds(next_cell):
            return

        if self.state.door_position == next_cell and not self.state.has_key:
            self.status_message = "Древняя дверь заперта. Найдите ключ."
            return

        if not self.is_walkable(next_cell):
            return

        self.state.player_cell = next_cell
        if count_step:
            self.state.steps += 1
        else:
            self.state.steps = self.auto_path_index

        message = self._collect_key_if_needed()
        trap_message = self._trigger_trap_if_needed()
        if trap_message is not None:
            message = trap_message
        elif message is None:
            message = self._collect_shard_if_needed()
        if message is None:
            message = progress_hint(self.shards_remaining, auto=auto)

        self.status_message = message
        self._refresh_visibility()
        self._check_win()

    def _check_win(self) -> None:
        if self.state.player_cell != self.state.maze.exit:
            return

        if not self.exit_unlocked:
            self.status_message = f"Выход закрыт. Осталось осколков: {self.shards_remaining}."
            return

        self.state.won = True
        self.status_message = "Выход найден."

    def on_draw(self) -> None:
        self.clear()
        self.draw_background()
        self.game_camera.use()
        self.draw_maze_backdrop()
        self.draw_maze()
        self.draw_goal()
        self.draw_shards()
        self.draw_key()
        self.draw_traps()
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

                rect = cell_rect(self.state.maze, position)
                if position == self.state.door_position:
                    door_color = (110, 210, 255, 255) if self.state.has_key else (214, 162, 110, 255)
                    arcade.draw_texture_rect(get_door_texture(self.state.has_key), rect, color=to_color(door_color))
                    continue

                base_color = self.pick_tile_color(position, cell)
                texture = get_floor_texture(abs(cell_noise(position)) % 2) if cell == EMPTY else get_wall_texture(abs(cell_noise(position)) % 2)
                arcade.draw_texture_rect(texture, rect, color=to_color(base_color))

                if position in self.visible_cells and cell != EMPTY:
                    left, bottom, width, height = rect.lbwh
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
        glow_color = EXIT_GLOW if self.exit_unlocked else EXIT_LOCKED_GLOW
        core_color = EXIT_COLOR if self.exit_unlocked else EXIT_LOCKED
        arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.28 + pulse * 0.08, glow_color)
        arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.17, core_color)

    def draw_shards(self) -> None:
        for shard in self.state.shard_positions:
            if shard in self.state.collected_shards or shard not in self.explored_cells:
                continue

            center_x, center_y = grid_to_world(self.state.maze, shard)
            pulse = 1 + 0.08 * math.sin(self.time * 3.6 + shard[0] * 0.8 + shard[1] * 0.5)
            alpha_scale = 1.0 if shard in self.visible_cells else 0.45
            glow = (SHARD_GLOW[0], SHARD_GLOW[1], SHARD_GLOW[2], int(SHARD_GLOW[3] * alpha_scale))
            arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.18 * pulse, glow)
            shard_rect = inset_rect(cell_rect(self.state.maze, shard), CELL_SIZE * 0.19, CELL_SIZE * 0.19)
            arcade.draw_texture_rect(
                get_shard_texture(),
                shard_rect,
                color=to_color((SHARD_CORE[0], SHARD_CORE[1], SHARD_CORE[2], int(230 * alpha_scale))),
            )

    def draw_key(self) -> None:
        if self.state.has_key or self.state.key_position is None or self.state.key_position not in self.explored_cells:
            return
        rect = inset_rect(cell_rect(self.state.maze, self.state.key_position), CELL_SIZE * 0.18, CELL_SIZE * 0.18)
        arcade.draw_texture_rect(get_key_texture(), rect, color=to_color((255, 214, 102, 255)))

    def draw_traps(self) -> None:
        for trap in self.state.trap_positions:
            if trap not in self.explored_cells:
                continue
            rect = inset_rect(cell_rect(self.state.maze, trap), CELL_SIZE * 0.16, CELL_SIZE * 0.16)
            color = (255, 116, 106, 220) if trap not in self.state.triggered_traps else (128, 144, 160, 140)
            arcade.draw_texture_rect(get_trap_texture(), rect, color=to_color(color))

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
            (CELL_SIZE * (self.current_vision_radius + 1.4), 12),
            (CELL_SIZE * (self.current_vision_radius + 0.8), 20),
            (CELL_SIZE * (self.current_vision_radius * 0.9), 28),
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
            "Осколки / ключ",
            f"{len(self.state.collected_shards)} / {len(self.state.shard_positions)}{' K' if self.state.has_key else ''}",
            (112, 201, 255, 255),
        )
        helper_bottom = panel.bottom + 52
        status_bottom = panel.bottom + 16
        arcade.draw_text(
            f"Свет: {self.current_vision_radius} | Выход: {'открыт' if self.exit_unlocked else 'закрыт'} | Дверь: {'открыта' if self.state.has_key else 'заперта'}",
            panel.left + padding,
            helper_bottom,
            HUD_MUTED,
            12,
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
