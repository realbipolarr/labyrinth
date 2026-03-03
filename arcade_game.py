from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import math
import random

import arcade
from arcade.types import Color
from PIL import Image, ImageDraw

from level_data import (
    COLOR_LABELS,
    KEY_COLORS,
    Door,
    Key,
    LevelData,
    ValidationResult,
    build_objective_route as _build_objective_route,
    door_map,
    generate_random_level,
    key_map,
    make_maze_from_grid,
    pick_shard_positions as _pick_shard_positions,
    pick_trap_positions as _pick_trap_positions,
    solve_level,
    validate_level,
)
from maze import EMPTY, WALL, Maze, Position, generate_maze, solve_maze


WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Labyrinth"
DEFAULT_MAZE_SIZE = (16, 16)
MAZE_SIZE_OPTIONS = (
    (10, 10, "Быстрый старт"),
    (16, 16, "Компактный квадрат"),
    (24, 24, "Классический квадрат"),
    (32, 24, "Большой лабиринт"),
)
CELL_SIZE = 54
PLAYER_RADIUS = CELL_SIZE * 0.24
MOVE_ANIMATION_SPEED = 9.0
AUTO_STEP_DELAY = 0.12
BASE_VISION_RADIUS = 4
SHARD_VISION_BONUS = 1
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
WARNING = (255, 125, 112, 255)

KEY_COLOR_VALUES = {
    "yellow": (255, 214, 102, 255),
    "cyan": (104, 221, 255, 255),
    "violet": (208, 129, 255, 255),
}

COLOR_SHORT = {
    "yellow": "Y",
    "cyan": "C",
    "violet": "V",
}


class GameMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"


@dataclass
class GameState:
    level: LevelData
    mode: GameMode
    player_cell: Position
    collected_shards: set[Position] = field(default_factory=set)
    triggered_traps: set[Position] = field(default_factory=set)
    owned_keys: set[str] = field(default_factory=set)
    steps: int = 0
    won: bool = False
    show_path_hint: bool = False


@dataclass(frozen=True)
class EditorTool:
    kind: str
    label: str
    hotkeys: tuple[int, ...]
    color: str | None = None


EDITOR_TOOLS = (
    EditorTool("floor", "Пол", (arcade.key.KEY_1,)),
    EditorTool("wall", "Стена", (arcade.key.KEY_2,)),
    EditorTool("start", "Старт", (arcade.key.KEY_3,)),
    EditorTool("exit", "Выход", (arcade.key.KEY_4,)),
    EditorTool("shard", "Осколок", (arcade.key.KEY_5,)),
    EditorTool("trap", "Ловушка", (arcade.key.KEY_6,)),
    EditorTool("key", "Жёлтый ключ", (arcade.key.KEY_7,), "yellow"),
    EditorTool("door", "Жёлтая дверь", (arcade.key.KEY_8,), "yellow"),
    EditorTool("key", "Бирюзовый ключ", (arcade.key.KEY_9,), "cyan"),
    EditorTool("door", "Бирюзовая дверь", (arcade.key.KEY_0,), "cyan"),
    EditorTool("key", "Фиолетовый ключ", (arcade.key.Q,), "violet"),
    EditorTool("door", "Фиолетовая дверь", (arcade.key.E,), "violet"),
)


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
    value_font_size = fit_text_size(
        value,
        preferred=20,
        minimum=13,
        max_width=rect.width - 32,
        font_name=FONT_DISPLAY,
        bold=True,
    )
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


def pick_shard_positions(maze: Maze, count: int = 3, seed: int | None = None) -> tuple[Position, ...]:
    return _pick_shard_positions(maze, count, random.Random(seed))


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
    return rng.choice(candidates[: max(1, min(24, len(candidates)))])


def pick_trap_positions(
    maze: Maze,
    forbidden: set[Position],
    route: list[Position],
    count: int = 3,
    seed: int | None = None,
) -> tuple[Position, ...]:
    return _pick_trap_positions(maze, forbidden, route, count, random.Random(seed))


def build_objective_route(
    maze: Maze,
    start: Position,
    exit_cell: Position,
    shards: tuple[Position, ...],
) -> list[Position]:
    return _build_objective_route(maze, start, exit_cell, shards)


def describe_size(size: tuple[int, int]) -> str:
    return f"{size[0]}x{size[1]}"


def color_name(color: str) -> str:
    return COLOR_LABELS[color].lower()


@lru_cache(maxsize=None)
def _texture_base() -> Image.Image:
    return Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), (255, 255, 255, 255))


@lru_cache(maxsize=None)
def get_floor_texture(variant: int = 0) -> arcade.Texture:
    image = _texture_base().copy()
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
    image = _texture_base().copy()
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
            ("Автопрохождение", "Случайный лабиринт, который ИИ проходит сам"),
            ("Ручное исследование", "Случайный лабиринт с туманом войны, дверями и ловушками"),
            ("Редактор уровня", "Постройте свой лабиринт и запустите его только после проверки"),
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
        elif symbol in {arcade.key.KEY_1, arcade.key.KEY_2, arcade.key.KEY_3, arcade.key.ENTER, arcade.key.SPACE}:
            if symbol == arcade.key.KEY_1:
                self.selected_index = 0
            elif symbol == arcade.key.KEY_2:
                self.selected_index = 1
            elif symbol == arcade.key.KEY_3:
                self.selected_index = 2
            self.launch_selected()

    def launch_selected(self) -> None:
        if self.selected_index == 0:
            self.window.show_view(SizeSelectionView(mode=GameMode.AUTO))
        elif self.selected_index == 1:
            self.window.show_view(SizeSelectionView(mode=GameMode.MANUAL))
        else:
            self.window.show_view(SizeSelectionView(editor=True))

    def on_draw(self) -> None:
        self.clear()
        draw_background(self.window, self.time, accent_shift=0.0)
        self.draw_preview_maze()
        self.draw_title()

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
        subtitle = "Случайные и пользовательские лабиринты с гарантированной проверкой проходимости"
        subtitle_size = fit_text_size(
            subtitle,
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
            subtitle,
            left,
            top - 48,
            HUD_MUTED,
            font_size=subtitle_size,
            font_name=FONT_DISPLAY,
        )

        panel = arcade.LBWH(left - 30, 145, 720, 372)
        draw_glass_panel(panel, accent_color=(82, 147, 255, 255))

        for index, (title, subtitle_text) in enumerate(self.options):
            y = 430 - index * 108
            is_selected = index == self.selected_index
            option_rect = arcade.LBWH(left, y - 34, 600, 76)
            fill = (255, 176, 74, 54) if is_selected else (16, 26, 40, 140)
            border = ACCENT if is_selected else (63, 95, 122, 90)
            draw_glass_panel(option_rect, fill_color=fill, border_color=border, accent_color=border if is_selected else (70, 120, 158, 255))
            arcade.draw_text(
                f"{index + 1}. {title}",
                left + 26,
                y + 4,
                HUD_TEXT if is_selected else (207, 219, 233, 255),
                font_size=25,
                font_name=FONT_DISPLAY,
                bold=is_selected,
            )
            arcade.draw_text(
                subtitle_text,
                left + 26,
                y - 20,
                HUD_MUTED,
                font_size=14,
                font_name=FONT_DISPLAY,
            )

        arcade.draw_text(
            "W/S или стрелки: выбор, Enter: дальше",
            left,
            106,
            HUD_MUTED,
            font_size=16,
            font_name=FONT_DISPLAY,
        )


class SizeSelectionView(arcade.View):
    def __init__(self, *, mode: GameMode | None = None, editor: bool = False) -> None:
        super().__init__(background_color=BACKGROUND_BOTTOM)
        self.mode = mode
        self.editor = editor
        self.selected_index = next(
            (index for index, (width, height, _) in enumerate(MAZE_SIZE_OPTIONS) if (width, height) == DEFAULT_MAZE_SIZE),
            0,
        )
        self.time = 0.0

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_BOTTOM)

    def on_update(self, delta_time: float) -> None:
        self.time += delta_time

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(TitleView())
            return

        option_key_map = {
            arcade.key.KEY_1: 0,
            arcade.key.KEY_2: 1,
            arcade.key.KEY_3: 2,
            arcade.key.KEY_4: 3,
        }
        if symbol in option_key_map:
            self.selected_index = option_key_map[symbol]
            return

        if symbol in {arcade.key.W, arcade.key.UP, arcade.key.A, arcade.key.LEFT}:
            self.selected_index = (self.selected_index - 1) % len(MAZE_SIZE_OPTIONS)
            return
        if symbol in {arcade.key.S, arcade.key.DOWN, arcade.key.D, arcade.key.RIGHT}:
            self.selected_index = (self.selected_index + 1) % len(MAZE_SIZE_OPTIONS)
            return
        if symbol in {arcade.key.ENTER, arcade.key.SPACE}:
            self.launch_selected()
            return

    def launch_selected(self) -> None:
        size = MAZE_SIZE_OPTIONS[self.selected_index][:2]
        if self.editor:
            self.window.show_view(EditorView(size))
        else:
            self.window.show_view(LabyrinthView(self.mode or GameMode.MANUAL, maze_size=size))

    def on_draw(self) -> None:
        self.clear()
        draw_background(self.window, self.time, accent_shift=0.35)
        panel = arcade.LBWH(self.window.width / 2 - 390, 140, 780, 520)
        draw_glass_panel(panel, accent_color=(116, 205, 255, 255))

        title = "Размер редактора" if self.editor else "Размер случайного лабиринта"
        subtitle = (
            "Выберите один из готовых форматов. Поле будет создано точно в этом размере."
            if self.editor
            else "Выберите один из готовых форматов. Каждый случайный лабиринт дополнительно проверяется решателем."
        )
        title_top = panel.top - 34
        arcade.draw_text(
            title,
            panel.left + 38,
            title_top,
            HUD_TEXT,
            34,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )
        arcade.draw_text(
            subtitle,
            panel.left + 38,
            title_top - 62,
            HUD_MUTED,
            15,
            width=int(panel.width - 76),
            multiline=True,
            font_name=FONT_DISPLAY,
            anchor_y="top",
        )

        for index, (width, height, description) in enumerate(MAZE_SIZE_OPTIONS):
            top = panel.top - 158 - index * 78
            option = arcade.LBWH(panel.left + 36, top - 58, panel.width - 72, 64)
            selected = index == self.selected_index
            accent = (116, 205, 255, 255) if selected else (80, 116, 144, 130)
            fill = (40, 83, 109, 82) if selected else (16, 26, 40, 120)
            draw_glass_panel(option, fill_color=fill, border_color=accent, accent_color=accent)
            arcade.draw_text(
                f"{index + 1}. {width} x {height}",
                option.left + 22,
                option.top - 18,
                HUD_TEXT,
                24,
                font_name=FONT_DISPLAY,
                bold=selected,
                anchor_y="top",
            )
            arcade.draw_text(
                description,
                option.left + 220,
                option.top - 22,
                HUD_MUTED,
                14,
                font_name=FONT_DISPLAY,
                anchor_y="top",
            )

        arcade.draw_text(
            "W/S или стрелки: выбор, 1-4: быстрый выбор, Enter: старт, Esc: назад",
            panel.left + 38,
            panel.bottom + 30,
            HUD_MUTED,
            14,
            width=int(panel.width - 76),
            multiline=True,
            font_name=FONT_DISPLAY,
            anchor_y="bottom",
        )


def draw_background(window: arcade.Window, time_value: float, *, accent_shift: float) -> None:
    bands = 20
    for index in range(bands):
        height = window.height / bands
        mix = index / max(1, bands - 1)
        color = (
            int(BACKGROUND_TOP[0] * (1 - mix) + BACKGROUND_BOTTOM[0] * mix),
            int(BACKGROUND_TOP[1] * (1 - mix) + BACKGROUND_BOTTOM[1] * mix),
            int(BACKGROUND_TOP[2] * (1 - mix) + BACKGROUND_BOTTOM[2] * mix),
            255,
        )
        rect = arcade.LBWH(0, window.height - (index + 1) * height, window.width, height + 2)
        arcade.draw_rect_filled(rect, color)

    for index in range(8):
        angle = time_value * (0.1 + accent_shift * 0.02) + index * 0.8
        radius = 140 + index * 20
        x = window.width * (0.12 + 0.09 * index) + math.sin(angle) * 40
        y = window.height * (0.16 + 0.07 * index) + math.cos(angle * 1.5) * 24
        arcade.draw_circle_filled(x, y, radius, (20, 58, 74, max(10, 30 - index * 2)))


class EditorView(arcade.View):
    def __init__(self, size: tuple[int, int]) -> None:
        super().__init__(background_color=BACKGROUND_BOTTOM)
        self.grid_size = size
        self.time = 0.0
        self.selected_tool_index = 1
        self.reset_level()

    def reset_level(self) -> None:
        width, height = self.grid_size
        self.grid = [[WALL for _ in range(width)] for _ in range(height)]
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                self.grid[y][x] = EMPTY
        self.start = (1, 1)
        self.exit = (width - 2, height - 2)
        self.shards: set[Position] = set()
        self.traps: set[Position] = set()
        self.keys: dict[str, Position] = {}
        self.doors: dict[Position, str] = {}
        self.validation = ValidationResult(False, "Добавьте старт, выход и путь между ними.")
        self._revalidate()

    @property
    def selected_tool(self) -> EditorTool:
        return EDITOR_TOOLS[self.selected_tool_index]

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_BOTTOM)

    def on_update(self, delta_time: float) -> None:
        self.time += delta_time

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(TitleView())
            return
        if symbol == arcade.key.R:
            self.reset_level()
            return
        if symbol == arcade.key.TAB:
            self.selected_tool_index = (self.selected_tool_index + 1) % len(EDITOR_TOOLS)
            return
        if symbol == arcade.key.ENTER:
            self.launch_level()
            return

        for index, tool in enumerate(EDITOR_TOOLS):
            if symbol in tool.hotkeys:
                self.selected_tool_index = index
                return

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        cell = self.cell_from_screen(x, y)
        if cell is None:
            return
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.apply_tool(cell)
        elif button == arcade.MOUSE_BUTTON_RIGHT:
            self.apply_tool(cell, erase=True)

    def on_mouse_drag(self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int) -> None:
        cell = self.cell_from_screen(x, y)
        if cell is None:
            return
        if buttons & arcade.MOUSE_BUTTON_LEFT:
            self.apply_tool(cell)
        elif buttons & arcade.MOUSE_BUTTON_RIGHT:
            self.apply_tool(cell, erase=True)

    def board_layout(self) -> tuple[arcade.Rect, float]:
        left_panel_width = 330
        right_panel_width = 430
        margin = 28
        available_width = self.window.width - left_panel_width - right_panel_width - margin * 4
        available_height = self.window.height - 110
        cell_size = max(18, min(34, int(min(available_width / self.grid_size[0], available_height / self.grid_size[1]))))
        board_width = self.grid_size[0] * cell_size
        board_height = self.grid_size[1] * cell_size
        board_left = left_panel_width + margin * 2 + max(0, (available_width - board_width) / 2)
        board_bottom = 58 + max(0, (available_height - board_height) / 2)
        return arcade.LBWH(board_left, board_bottom, board_width, board_height), cell_size

    def cell_from_screen(self, x: float, y: float) -> Position | None:
        board, cell_size = self.board_layout()
        if not (board.left <= x < board.right and board.bottom <= y < board.top):
            return None
        local_x = int((x - board.left) // cell_size)
        local_y = int((y - board.bottom) // cell_size)
        grid_y = self.grid_size[1] - 1 - local_y
        cell = (local_x, grid_y)
        if not (0 <= cell[0] < self.grid_size[0] and 0 <= cell[1] < self.grid_size[1]):
            return None
        return cell

    def _clear_special_at(self, cell: Position) -> None:
        self.shards.discard(cell)
        self.traps.discard(cell)
        self.doors.pop(cell, None)
        for color, position in list(self.keys.items()):
            if position == cell:
                self.keys.pop(color)

    def _set_floor(self, cell: Position) -> None:
        x, y = cell
        self.grid[y][x] = EMPTY

    def apply_tool(self, cell: Position, *, erase: bool = False) -> None:
        x, y = cell
        if x in {0, self.grid_size[0] - 1} or y in {0, self.grid_size[1] - 1}:
            return

        if erase:
            if cell in {self.start, self.exit}:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            self._revalidate()
            return

        tool = self.selected_tool
        if tool.kind == "floor":
            if cell in {self.start, self.exit}:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
        elif tool.kind == "wall":
            if cell in {self.start, self.exit}:
                return
            self.grid[y][x] = WALL
            self._clear_special_at(cell)
        elif tool.kind == "start":
            if cell == self.exit:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            self.start = cell
        elif tool.kind == "exit":
            if cell == self.start:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            self.exit = cell
        elif tool.kind == "shard":
            if cell in {self.start, self.exit}:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            self.shards.add(cell)
        elif tool.kind == "trap":
            if cell in {self.start, self.exit}:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            self.traps.add(cell)
        elif tool.kind == "key":
            if cell in {self.start, self.exit}:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            if tool.color is not None:
                self.keys[tool.color] = cell
        elif tool.kind == "door":
            if cell in {self.start, self.exit}:
                return
            self._set_floor(cell)
            self._clear_special_at(cell)
            if tool.color is not None:
                self.doors[cell] = tool.color

        self._revalidate()

    def current_level(self) -> LevelData:
        maze = make_maze_from_grid(self.grid, self.start, self.exit)
        doors = tuple(Door(position=position, color=color) for position, color in sorted(self.doors.items()))
        keys = tuple(Key(position=position, color=color) for color, position in sorted(self.keys.items()))
        return LevelData(
            maze=maze,
            shard_positions=tuple(sorted(self.shards)),
            trap_positions=tuple(sorted(self.traps)),
            doors=doors,
            keys=keys,
        )

    def _revalidate(self) -> None:
        self.validation = validate_level(self.current_level())

    def launch_level(self) -> None:
        if not self.validation.ok:
            return
        self.window.show_view(
            LabyrinthView(
                GameMode.MANUAL,
                level=self.current_level(),
                maze_size=self.grid_size,
                return_view=self,
            )
        )

    def on_draw(self) -> None:
        self.clear()
        draw_background(self.window, self.time, accent_shift=0.6)
        self.draw_board()
        self.draw_panels()

    def draw_board(self) -> None:
        board, cell_size = self.board_layout()
        board_panel = arcade.LBWH(board.left - 18, board.bottom - 18, board.width + 36, board.height + 36)
        draw_glass_panel(board_panel, fill_color=(8, 14, 24, 210), border_color=(70, 106, 132, 90), accent_color=(110, 180, 224, 255))

        for y in range(self.grid_size[1]):
            for x in range(self.grid_size[0]):
                cell = (x, y)
                screen_x = board.left + x * cell_size
                screen_y = board.bottom + (self.grid_size[1] - y - 1) * cell_size
                rect = arcade.LBWH(screen_x, screen_y, cell_size - 1, cell_size - 1)
                cell_value = self.grid[y][x]
                fill_color = (55, 104, 122, 255) if cell_value == EMPTY else (22, 38, 50, 255)
                line_color = (122, 171, 190, 70) if cell_value == EMPTY else (86, 114, 134, 90)
                arcade.draw_rect_filled(rect, fill_color)
                arcade.draw_rect_outline(rect, line_color, border_width=1)

        for door_position, color in self.doors.items():
            rect = inset_rect(self._editor_rect(board, cell_size, door_position), cell_size * 0.08, cell_size * 0.08)
            arcade.draw_texture_rect(get_door_texture(False), rect, color=to_color(KEY_COLOR_VALUES[color]))

        for key_color, key_position in self.keys.items():
            rect = inset_rect(self._editor_rect(board, cell_size, key_position), cell_size * 0.12, cell_size * 0.12)
            arcade.draw_texture_rect(get_key_texture(), rect, color=to_color(KEY_COLOR_VALUES[key_color]))

        for shard in self.shards:
            rect = inset_rect(self._editor_rect(board, cell_size, shard), cell_size * 0.14, cell_size * 0.14)
            arcade.draw_texture_rect(get_shard_texture(), rect, color=to_color(SHARD_CORE))

        for trap in self.traps:
            rect = inset_rect(self._editor_rect(board, cell_size, trap), cell_size * 0.12, cell_size * 0.12)
            arcade.draw_texture_rect(get_trap_texture(), rect, color=to_color((255, 112, 102, 230)))

        self._draw_marker(board, cell_size, self.start, (132, 255, 190, 255), "S")
        self._draw_marker(board, cell_size, self.exit, (255, 189, 102, 255), "E")

    def _editor_rect(self, board: arcade.Rect, cell_size: float, cell: Position) -> arcade.Rect:
        x, y = cell
        return arcade.LBWH(
            board.left + x * cell_size,
            board.bottom + (self.grid_size[1] - y - 1) * cell_size,
            cell_size - 1,
            cell_size - 1,
        )

    def _draw_marker(self, board: arcade.Rect, cell_size: float, cell: Position, color: tuple[int, int, int, int], text: str) -> None:
        rect = self._editor_rect(board, cell_size, cell)
        center_x = rect.center_x
        center_y = rect.center_y
        arcade.draw_circle_filled(center_x, center_y, cell_size * 0.28, color[:3] + (60,))
        arcade.draw_circle_filled(center_x, center_y, cell_size * 0.18, color)
        arcade.draw_text(
            text,
            center_x,
            center_y - cell_size * 0.12,
            (10, 15, 22, 255),
            max(10, int(cell_size * 0.34)),
            anchor_x="center",
            font_name=FONT_DISPLAY,
            bold=True,
        )

    def draw_panels(self) -> None:
        margin = 28
        left_panel = arcade.LBWH(margin, self.window.height - 340 - margin, 320, 340)
        right_panel = arcade.LBWH(self.window.width - 420 - margin, self.window.height - 470 - margin, 420, 470)
        help_panel = arcade.LBWH(self.window.width - 420 - margin, 54, 420, 230)
        draw_glass_panel(left_panel)
        draw_glass_panel(right_panel, fill_color=(8, 14, 24, 205), border_color=(61, 93, 122, 95), accent_color=(100, 162, 214, 255))
        draw_glass_panel(help_panel, fill_color=(8, 14, 24, 205), border_color=(61, 93, 122, 95), accent_color=(100, 162, 214, 255))

        arcade.draw_text(
            "Редактор",
            left_panel.left + 24,
            left_panel.top - 24,
            HUD_TEXT,
            28,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )
        arcade.draw_text(
            f"Размер: {describe_size(self.grid_size)}",
            left_panel.left + 24,
            left_panel.top - 62,
            HUD_MUTED,
            15,
            font_name=FONT_DISPLAY,
            anchor_y="top",
        )

        draw_stat_chip(arcade.LBWH(left_panel.left + 24, left_panel.bottom + 182, 128, 72), "Осколки", str(len(self.shards)), SHARD_CORE)
        draw_stat_chip(arcade.LBWH(left_panel.left + 168, left_panel.bottom + 182, 128, 72), "Двери", str(len(self.doors)), (110, 210, 255, 255))
        draw_stat_chip(arcade.LBWH(left_panel.left + 24, left_panel.bottom + 92, 272, 72), "Ключи", str(len(self.keys)), (200, 144, 255, 255))

        status_color = SUCCESS if self.validation.ok else WARNING
        arcade.draw_rect_filled(arcade.LBWH(left_panel.left + 20, left_panel.bottom + 18, left_panel.width - 40, 46), (18, 29, 42, 180))
        arcade.draw_text(
            self.validation.message,
            left_panel.left + 24,
            left_panel.bottom + 24,
            status_color,
            13,
            width=int(left_panel.width - 48),
            multiline=True,
            font_name=FONT_DISPLAY,
            anchor_y="bottom",
        )

        arcade.draw_text(
            "Инструменты",
            right_panel.left + 24,
            right_panel.top - 24,
            HUD_TEXT,
            24,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )

        grid_left = right_panel.left + 18
        grid_top = right_panel.top - 78
        column_width = (right_panel.width - 52) / 2
        row_height = 58
        for index, tool in enumerate(EDITOR_TOOLS):
            selected = index == self.selected_tool_index
            color = KEY_COLOR_VALUES.get(tool.color or "", HUD_MUTED)
            label_color = HUD_TEXT if selected else (207, 219, 233, 255)
            column = index % 2
            row = index // 2
            item_left = grid_left + column * (column_width + 12)
            item_bottom = grid_top - (row + 1) * row_height
            item_rect = arcade.LBWH(item_left, item_bottom, column_width, row_height - 10)
            if selected:
                arcade.draw_rect_filled(item_rect, (52, 82, 108, 110))
                arcade.draw_rect_outline(item_rect, (110, 190, 230, 120), border_width=1)
            arcade.draw_text(
                f"{self._tool_shortcut(tool)} {tool.label}",
                item_left + 10,
                item_rect.top - 10,
                label_color,
                12,
                width=int(column_width - 28),
                multiline=True,
                font_name=FONT_DISPLAY,
                anchor_y="top",
            )
            if tool.color is not None:
                arcade.draw_circle_filled(item_rect.right - 12, item_rect.center_y, 5, color)

        arcade.draw_text(
            "Подсказки",
            help_panel.left + 24,
            help_panel.top - 24,
            HUD_TEXT,
            22,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )
        arcade.draw_text(
            "ЛКМ: поставить объект\nПКМ: очистить клетку\nTab: следующий инструмент\nEnter: запуск, только если уровень валиден\nR: сбросить поле\nEsc: в меню",
            help_panel.left + 24,
            help_panel.top - 68,
            HUD_MUTED,
            13,
            width=int(help_panel.width - 48),
            multiline=True,
            font_name=FONT_DISPLAY,
            anchor_y="top",
        )

    def _tool_shortcut(self, tool: EditorTool) -> str:
        shortcut = tool.hotkeys[0]
        mapping = {
            arcade.key.Q: "Q",
            arcade.key.E: "E",
            arcade.key.KEY_0: "0",
        }
        if shortcut in mapping:
            return f"[{mapping[shortcut]}]"
        if arcade.key.KEY_1 <= shortcut <= arcade.key.KEY_9:
            return f"[{shortcut - arcade.key.KEY_0}]"
        return "[?]"


class LabyrinthView(arcade.View):
    def __init__(
        self,
        mode: GameMode,
        *,
        maze_size: tuple[int, int] = DEFAULT_MAZE_SIZE,
        level: LevelData | None = None,
        return_view: arcade.View | None = None,
    ) -> None:
        super().__init__(background_color=BACKGROUND_BOTTOM)
        self.game_camera = arcade.Camera2D()
        self.mode = mode
        self.maze_size = maze_size
        self.return_view = return_view
        self.fixed_level = level
        self.time = 0.0
        self.auto_path_index = 0
        self.auto_step_timer = 0.0
        self.visible_cells: set[Position] = set()
        self.explored_cells: set[Position] = set()
        self.status_message = "Соберите все осколки, а затем ищите выход."
        self.state = self._create_state()
        self.player_draw_position = grid_to_world(self.state.level.maze, self.state.player_cell)
        self.solution_path = solve_level(self.state.level)
        self._refresh_visibility()

    def _new_level(self) -> LevelData:
        if self.fixed_level is not None:
            return self.fixed_level
        return generate_random_level(*self.maze_size)

    def _create_state(self) -> GameState:
        level = self._new_level()
        return GameState(level=level, mode=self.mode, player_cell=level.start)

    def regenerate(self) -> None:
        self.state = self._create_state()
        self.solution_path = solve_level(self.state.level)
        self.visible_cells = set()
        self.explored_cells = set()
        self.player_draw_position = grid_to_world(self.state.level.maze, self.state.player_cell)
        self.auto_path_index = 0
        self.auto_step_timer = 0.0
        if self.fixed_level is not None:
            self.status_message = "Пользовательский лабиринт перезапущен."
        else:
            self.status_message = "Новый лабиринт готов. Ищите осколки."
        self._refresh_visibility()

    def on_show_view(self) -> None:
        arcade.set_background_color(BACKGROUND_BOTTOM)

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self.game_camera.match_window()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(self.return_view or TitleView())
            return

        if symbol == arcade.key.R:
            self.regenerate()
            return

        if symbol == arcade.key.H:
            self.state.show_path_hint = not self.state.show_path_hint
            return

        if self.state.mode != GameMode.MANUAL or self.state.won:
            return

        if not is_close(self.player_draw_position, grid_to_world(self.state.level.maze, self.state.player_cell), tolerance=0.6):
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
        target_position = grid_to_world(self.state.level.maze, self.state.player_cell)
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
        if not is_close(self.player_draw_position, grid_to_world(self.state.level.maze, self.state.player_cell), tolerance=0.8):
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

    @property
    def maze(self) -> Maze:
        return self.state.level.maze

    @property
    def doors(self) -> dict[Position, str]:
        return door_map(self.state.level)

    @property
    def keys(self) -> dict[Position, str]:
        return key_map(self.state.level)

    def is_walkable(self, position: Position) -> bool:
        if not self.maze.in_bounds(position):
            return False
        door_color = self.doors.get(position)
        if door_color is not None:
            return door_color in self.state.owned_keys
        return self.maze.is_open(position)

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
                if nxt in seen or not self.maze.in_bounds(nxt):
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
        return len(self.state.level.shard_positions) - len(self.state.collected_shards)

    @property
    def exit_unlocked(self) -> bool:
        return self.shards_remaining == 0

    def _collect_shard_if_needed(self) -> str | None:
        player_cell = self.state.player_cell
        if player_cell not in self.state.level.shard_positions or player_cell in self.state.collected_shards:
            return None
        self.state.collected_shards.add(player_cell)
        if self.exit_unlocked:
            return "Все осколки собраны. Ищите выход."
        return f"Осколок найден. Осталось: {self.shards_remaining}."

    def _collect_key_if_needed(self) -> str | None:
        color = self.keys.get(self.state.player_cell)
        if color is None or color in self.state.owned_keys:
            return None
        self.state.owned_keys.add(color)
        return f"{COLOR_LABELS[color]} ключ найден. Соответствующие двери открыты."

    def _trigger_trap_if_needed(self) -> str | None:
        if self.state.player_cell not in self.state.level.trap_positions or self.state.player_cell in self.state.triggered_traps:
            return None
        self.state.triggered_traps.add(self.state.player_cell)
        self.state.steps += 5
        self.state.player_cell = self.maze.start
        self.player_draw_position = grid_to_world(self.maze, self.state.player_cell)
        return "Ловушка сработала. Вас отбросило к старту."

    def _move_player(self, next_cell: Position, *, auto: bool, count_step: bool = True) -> None:
        if not self.maze.in_bounds(next_cell):
            return

        door_color = self.doors.get(next_cell)
        if door_color is not None and door_color not in self.state.owned_keys:
            self.status_message = f"{COLOR_LABELS[door_color]} дверь заперта. Найдите {color_name(door_color)} ключ."
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
        if self.state.player_cell != self.maze.exit:
            return
        if not self.exit_unlocked:
            self.status_message = f"Выход закрыт. Осталось осколков: {self.shards_remaining}."
            return
        self.state.won = True
        self.status_message = "Выход найден."

    def on_draw(self) -> None:
        self.clear()
        draw_background(self.window, self.time, accent_shift=0.2)
        self.game_camera.use()
        self.draw_maze_backdrop()
        self.draw_maze()
        self.draw_goal()
        self.draw_shards()
        self.draw_keys()
        self.draw_traps()
        self.draw_path()
        self.draw_player_light()
        self.draw_player()
        self.draw_fog()
        self.window.default_camera.use()
        self.draw_hud()

    def draw_maze_backdrop(self) -> None:
        maze_width = self.maze.width * CELL_SIZE
        maze_height = self.maze.height * CELL_SIZE
        backdrop = arcade.LBWH(-CELL_SIZE * 0.85, -CELL_SIZE * 0.85, maze_width + CELL_SIZE * 1.7, maze_height + CELL_SIZE * 1.7)
        arcade.draw_rect_filled(backdrop, (6, 11, 22, 210))
        arcade.draw_rect_outline(backdrop, (50, 77, 102, 100), border_width=3)
        inner = inset_rect(backdrop, CELL_SIZE * 0.28, CELL_SIZE * 0.28)
        arcade.draw_rect_outline(inner, (96, 141, 170, 45), border_width=2)

    def draw_maze(self) -> None:
        for y, row in enumerate(self.maze.grid):
            for x, cell in enumerate(row):
                position = (x, y)
                if position not in self.explored_cells:
                    continue

                rect = cell_rect(self.maze, position)
                door_color = self.doors.get(position)
                if door_color is not None:
                    owned = door_color in self.state.owned_keys
                    tint = KEY_COLOR_VALUES[door_color]
                    if owned:
                        tint = mix_color(tint, 18)
                    arcade.draw_texture_rect(get_door_texture(owned), rect, color=to_color(tint))
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
        if self.maze.exit not in self.explored_cells:
            return
        center_x, center_y = grid_to_world(self.maze, self.maze.exit)
        pulse = 8 * math.sin(self.time * 2.7)
        glow_color = EXIT_GLOW if self.exit_unlocked else EXIT_LOCKED_GLOW
        core_color = EXIT_COLOR if self.exit_unlocked else EXIT_LOCKED
        arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.28 + pulse * 0.08, glow_color)
        arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.17, core_color)

    def draw_shards(self) -> None:
        for shard in self.state.level.shard_positions:
            if shard in self.state.collected_shards or shard not in self.explored_cells:
                continue
            center_x, center_y = grid_to_world(self.maze, shard)
            pulse = 1 + 0.08 * math.sin(self.time * 3.6 + shard[0] * 0.8 + shard[1] * 0.5)
            alpha_scale = 1.0 if shard in self.visible_cells else 0.45
            glow = (SHARD_GLOW[0], SHARD_GLOW[1], SHARD_GLOW[2], int(SHARD_GLOW[3] * alpha_scale))
            arcade.draw_circle_filled(center_x, center_y, CELL_SIZE * 0.18 * pulse, glow)
            shard_rect = inset_rect(cell_rect(self.maze, shard), CELL_SIZE * 0.19, CELL_SIZE * 0.19)
            arcade.draw_texture_rect(
                get_shard_texture(),
                shard_rect,
                color=to_color((SHARD_CORE[0], SHARD_CORE[1], SHARD_CORE[2], int(230 * alpha_scale))),
            )

    def draw_keys(self) -> None:
        for key in self.state.level.keys:
            if key.color in self.state.owned_keys or key.position not in self.explored_cells:
                continue
            rect = inset_rect(cell_rect(self.maze, key.position), CELL_SIZE * 0.18, CELL_SIZE * 0.18)
            arcade.draw_texture_rect(get_key_texture(), rect, color=to_color(KEY_COLOR_VALUES[key.color]))

    def draw_traps(self) -> None:
        for trap in self.state.level.trap_positions:
            if trap not in self.explored_cells:
                continue
            rect = inset_rect(cell_rect(self.maze, trap), CELL_SIZE * 0.16, CELL_SIZE * 0.16)
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
            center_x, center_y = grid_to_world(self.maze, cell)
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
        for y in range(self.maze.height):
            for x in range(self.maze.width):
                position = (x, y)
                rect = cell_rect(self.maze, position)
                if position not in self.explored_cells:
                    arcade.draw_rect_filled(rect, FOG_HIDDEN)
                elif position not in self.visible_cells:
                    arcade.draw_rect_filled(rect, FOG_EXPLORED)

    def draw_hud(self) -> None:
        margin = 28
        panel_width = clamp(self.window.width * 0.44, 500, 680)
        panel_height = 304
        panel = arcade.LBWH(margin, self.window.height - panel_height - margin, panel_width, panel_height)
        draw_glass_panel(panel)

        padding = 28
        title = "Автопрохождение" if self.state.mode == GameMode.AUTO else "Ручное исследование"
        if self.fixed_level is not None:
            title += " | редактор"
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
            panel.top - 22,
            HUD_TEXT,
            title_font,
            font_name=FONT_DISPLAY,
            bold=True,
            anchor_y="top",
        )

        descriptor_top = panel.top - 22 - title_font - 14
        arcade.draw_text(
            f"Размер: {self.maze.width}x{self.maze.height} | Осколки: {len(self.state.level.shard_positions)}",
            panel.left + padding,
            descriptor_top,
            HUD_MUTED,
            13,
            font_name=FONT_DISPLAY,
            anchor_y="top",
        )
        arcade.draw_text(
            f"Двери: {len(self.state.level.doors)} | Ловушки: {len(self.state.level.trap_positions)}",
            panel.left + padding,
            descriptor_top - 28,
            HUD_MUTED,
            13,
            font_name=FONT_DISPLAY,
            anchor_y="top",
        )

        chip_gap = 18
        chip_width = (panel.width - padding * 2 - chip_gap * 2) / 3
        chip_height = 72
        chip_bottom = panel.bottom + 110
        draw_stat_chip(
            arcade.LBWH(panel.left + padding, chip_bottom, chip_width, chip_height),
            "Шаги",
            str(self.state.steps),
            ACCENT,
        )
        draw_stat_chip(
            arcade.LBWH(panel.left + padding + chip_width + chip_gap, chip_bottom, chip_width, chip_height),
            "Осколки",
            f"{len(self.state.collected_shards)} / {len(self.state.level.shard_positions)}",
            SHARD_CORE,
        )
        key_value = "нет" if not self.state.owned_keys else " ".join(COLOR_SHORT[color] for color in KEY_COLORS if color in self.state.owned_keys)
        draw_stat_chip(
            arcade.LBWH(panel.left + padding + (chip_width + chip_gap) * 2, chip_bottom, chip_width, chip_height),
            "Ключи",
            key_value,
            (112, 201, 255, 255),
        )

        helper_text = (
            f"Свет: {self.current_vision_radius} | Выход: {'открыт' if self.exit_unlocked else 'закрыт'} | "
            f"Запертых дверей: {sum(1 for color in self.doors.values() if color not in self.state.owned_keys)}"
        )
        arcade.draw_text(
            helper_text,
            panel.left + padding,
            panel.bottom + 60,
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
            panel.bottom + 18,
            SUCCESS if self.state.won else ACCENT,
            17,
            width=int(panel.width - padding * 2),
            multiline=True,
            anchor_y="bottom",
            font_name=FONT_DISPLAY,
        )

        help_panel_width = clamp(self.window.width * 0.27, 330, 400)
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
            "H: показать найденный маршрут",
            "R: перезапустить уровень" if self.fixed_level is not None else "R: новый лабиринт",
            "Esc: назад в редактор" if self.return_view is not None else "Esc: в меню",
        ]
        if self.state.mode == GameMode.AUTO:
            controls[0] = "Авто-режим: игрок идёт сам"
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
        overlay = arcade.LBWH(self.window.width / 2 - 310, self.window.height / 2 - 126, 620, 252)
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
        exit_text = "R — перезапустить, Esc — назад в редактор" if self.return_view is not None else "R — сыграть ещё раз, Esc — вернуться в меню"
        arcade.draw_text(
            exit_text,
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
