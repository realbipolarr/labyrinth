from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random

from maze import EMPTY, WALL, Maze, Position, generate_maze, solve_maze


KEY_COLORS = ("yellow", "cyan", "violet")
COLOR_LABELS = {
    "yellow": "Жёлтый",
    "cyan": "Бирюзовый",
    "violet": "Фиолетовый",
}


@dataclass(frozen=True)
class Door:
    position: Position
    color: str


@dataclass(frozen=True)
class Key:
    position: Position
    color: str


@dataclass(frozen=True)
class LevelData:
    maze: Maze
    shard_positions: tuple[Position, ...] = ()
    trap_positions: tuple[Position, ...] = ()
    doors: tuple[Door, ...] = ()
    keys: tuple[Key, ...] = ()

    @property
    def start(self) -> Position:
        return self.maze.start

    @property
    def exit(self) -> Position:
        return self.maze.exit


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str
    route: tuple[Position, ...] = ()


def make_maze_from_grid(grid: list[list[str]], start: Position, exit_pos: Position) -> Maze:
    height = len(grid)
    width = len(grid[0]) if grid else 0
    copied = [row[:] for row in grid]
    copied[start[1]][start[0]] = EMPTY
    copied[exit_pos[1]][exit_pos[0]] = EMPTY
    return Maze(width=width, height=height, grid=copied, start=start, exit=exit_pos)


def open_floor_cells(maze: Maze) -> list[Position]:
    return [
        (x, y)
        for y, row in enumerate(maze.grid)
        for x, cell in enumerate(row)
        if cell == EMPTY
    ]


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

        if route:
            route.extend(best_path[1:])
        else:
            route.extend(best_path)
        current = best_target
        remaining.remove(best_target)

    tail = solve_maze(maze, current, exit_cell)
    if tail:
        route.extend(tail[1:])
    return route


def pick_shard_positions(maze: Maze, count: int, rng: random.Random) -> tuple[Position, ...]:
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


def _pick_lock_pairs(
    maze: Maze,
    route: list[Position],
    blocked: set[Position],
    rng: random.Random,
) -> tuple[tuple[Door, ...], tuple[Key, ...]]:
    if len(route) < 14:
        return (), ()

    pair_target = 2 if maze.width * maze.height >= 420 and len(route) >= 30 else 1
    available_colors = list(KEY_COLORS)
    rng.shuffle(available_colors)
    used_positions = set(blocked)
    used_indices: list[int] = []
    doors: list[Door] = []
    keys: list[Key] = []

    for color in available_colors[:pair_target]:
        door_options = [
            (index, cell)
            for index, cell in enumerate(route)
            if index >= max(7, len(route) // 3)
            and index <= len(route) - 4
            and cell not in used_positions
            and all(abs(index - taken) >= 6 for taken in used_indices)
        ]
        if not door_options:
            continue

        door_index, door_cell = rng.choice(door_options[-min(12, len(door_options)) :])
        key_options = [
            (index, cell)
            for index, cell in enumerate(route[: door_index - 2])
            if index >= 2
            and cell not in used_positions
            and all(abs(index - taken) >= 3 for taken in used_indices)
        ]
        if not key_options:
            continue

        key_index, key_cell = rng.choice(key_options[: max(3, len(key_options) // 2)])
        used_positions.add(door_cell)
        used_positions.add(key_cell)
        used_indices.extend((door_index, key_index))
        doors.append(Door(position=door_cell, color=color))
        keys.append(Key(position=key_cell, color=color))

    return tuple(doors), tuple(keys)


def pick_trap_positions(
    maze: Maze,
    forbidden: set[Position],
    route: list[Position],
    count: int,
    rng: random.Random,
) -> tuple[Position, ...]:
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


def _key_by_color(level: LevelData) -> dict[str, Key]:
    return {key.color: key for key in level.keys}


def door_map(level: LevelData) -> dict[Position, str]:
    return {door.position: door.color for door in level.doors}


def key_map(level: LevelData) -> dict[Position, str]:
    return {key.position: key.color for key in level.keys}


def _is_open_for_state(level: LevelData, position: Position, owned_keys: frozenset[str]) -> bool:
    if position in set(level.trap_positions):
        return False
    if not level.maze.in_bounds(position):
        return False
    door_color = door_map(level).get(position)
    if door_color is not None:
        return door_color in owned_keys
    return level.maze.is_open(position)


def solve_level(level: LevelData) -> list[Position]:
    shards = {position: index for index, position in enumerate(level.shard_positions)}
    doors = door_map(level)
    keys = key_map(level)
    trap_set = set(level.trap_positions)
    all_shards_mask = (1 << len(level.shard_positions)) - 1
    directions = ((0, -1), (1, 0), (0, 1), (-1, 0))

    def can_enter(position: Position, owned_keys: frozenset[str]) -> bool:
        if position in trap_set or not level.maze.in_bounds(position):
            return False
        door_color = doors.get(position)
        if door_color is not None:
            return door_color in owned_keys
        return level.maze.is_open(position)

    start_state = (level.start, frozenset(), 0)
    queue = deque([start_state])
    parents: dict[tuple[Position, frozenset[str], int], tuple[Position, frozenset[str], int] | None] = {start_state: None}
    goal_state: tuple[Position, frozenset[str], int] | None = None

    while queue:
        position, owned_keys, shard_mask = queue.popleft()
        if position == level.exit and shard_mask == all_shards_mask:
            goal_state = (position, owned_keys, shard_mask)
            break

        x, y = position
        for dx, dy in directions:
            nxt = (x + dx, y + dy)
            if not can_enter(nxt, owned_keys):
                continue

            next_keys = owned_keys
            key_color = keys.get(nxt)
            if key_color is not None:
                next_keys = frozenset(set(owned_keys) | {key_color})

            next_mask = shard_mask
            shard_index = shards.get(nxt)
            if shard_index is not None:
                next_mask |= 1 << shard_index

            state = (nxt, next_keys, next_mask)
            if state in parents:
                continue
            parents[state] = (position, owned_keys, shard_mask)
            queue.append(state)

    if goal_state is None:
        return []

    route: list[Position] = []
    current: tuple[Position, frozenset[str], int] | None = goal_state
    while current is not None:
        route.append(current[0])
        current = parents[current]
    route.reverse()
    return route


def validate_level(level: LevelData) -> ValidationResult:
    maze = level.maze
    if not maze.in_bounds(level.start) or not maze.in_bounds(level.exit):
        return ValidationResult(False, "Старт и выход должны находиться внутри поля.")
    if level.start == level.exit:
        return ValidationResult(False, "Старт и выход должны быть в разных клетках.")
    if not maze.is_open(level.start) or not maze.is_open(level.exit):
        return ValidationResult(False, "Старт и выход должны стоять на свободных клетках.")

    seen_positions: set[Position] = {level.start, level.exit}
    for shard in level.shard_positions:
        if not maze.in_bounds(shard) or not maze.is_open(shard):
            return ValidationResult(False, "Осколки нужно ставить на свободные клетки.")
        if shard in seen_positions:
            return ValidationResult(False, "Осколки не должны пересекаться с другими объектами.")
        seen_positions.add(shard)

    for trap in level.trap_positions:
        if not maze.in_bounds(trap) or not maze.is_open(trap):
            return ValidationResult(False, "Ловушки нужно ставить на свободные клетки.")
        if trap in seen_positions:
            return ValidationResult(False, "Ловушки не должны пересекаться с другими объектами.")
        seen_positions.add(trap)

    seen_key_colors: set[str] = set()
    for key in level.keys:
        if key.color not in KEY_COLORS:
            return ValidationResult(False, "Обнаружен неизвестный цвет ключа.")
        if key.color in seen_key_colors:
            return ValidationResult(False, "Для каждого цвета должен быть только один ключ.")
        if not maze.in_bounds(key.position) or not maze.is_open(key.position):
            return ValidationResult(False, "Ключи нужно ставить на свободные клетки.")
        if key.position in seen_positions:
            return ValidationResult(False, "Ключи не должны пересекаться с другими объектами.")
        seen_key_colors.add(key.color)
        seen_positions.add(key.position)

    seen_doors: set[Position] = set()
    key_colors = set(_key_by_color(level))
    for door in level.doors:
        if door.color not in KEY_COLORS:
            return ValidationResult(False, "Обнаружен неизвестный цвет двери.")
        if door.position in {level.start, level.exit}:
            return ValidationResult(False, "Дверь нельзя ставить на старт или выход.")
        if not maze.in_bounds(door.position):
            return ValidationResult(False, "Двери должны находиться внутри поля.")
        if door.position in seen_doors:
            return ValidationResult(False, "В одной клетке не может быть несколько дверей.")
        if door.position in seen_positions:
            return ValidationResult(False, "Двери не должны пересекаться с ключами, ловушками и осколками.")
        seen_doors.add(door.position)
        if door.color not in key_colors:
            return ValidationResult(False, f"Для двери цвета «{COLOR_LABELS[door.color]}» нужен ключ.")

    route = solve_level(level)
    if not route:
        return ValidationResult(False, "Уровень не проходится: не найден маршрут до выхода с учётом ключей и осколков.")

    return ValidationResult(True, "Уровень готов к запуску.", tuple(route))


def _random_shard_count(width: int, height: int) -> int:
    return max(2, min(5, (width * height) // 180 + 2))


def _random_trap_count(width: int, height: int) -> int:
    return max(1, min(5, (width * height) // 220 + 1))


def generate_random_level(width: int, height: int, seed: int | None = None) -> LevelData:
    rng = random.Random(seed)

    for _ in range(160):
        maze = generate_maze(width, height, seed=rng.randrange(10**9))
        shards = pick_shard_positions(maze, _random_shard_count(width, height), rng)
        base_route = build_objective_route(maze, maze.start, maze.exit, shards)
        if not base_route:
            continue

        blocked = {maze.start, maze.exit, *shards}
        doors, keys = _pick_lock_pairs(maze, base_route, blocked, rng)
        route_with_locks = solve_level(LevelData(maze=maze, shard_positions=shards, doors=doors, keys=keys))
        if not route_with_locks:
            continue

        forbidden = blocked | {door.position for door in doors} | {key.position for key in keys}
        traps = pick_trap_positions(maze, forbidden, route_with_locks, _random_trap_count(width, height), rng)
        level = LevelData(
            maze=maze,
            shard_positions=shards,
            trap_positions=traps,
            doors=doors,
            keys=keys,
        )
        if validate_level(level).ok:
            return level

    raise RuntimeError(f"Unable to generate a solvable labyrinth for size {width}x{height}.")
