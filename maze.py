from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random


WALL = "#"
EMPTY = " "
Position = tuple[int, int]


@dataclass
class Maze:
    width: int
    height: int
    grid: list[list[str]]
    start: Position
    exit: Position

    def is_open(self, position: Position) -> bool:
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[y][x] == EMPTY


def _normalize_size(value: int) -> int:
    value = max(5, value)
    if value % 2 == 0:
        value += 1
    return value


def generate_maze(width: int = 21, height: int = 21, seed: int | None = None) -> Maze:
    width = _normalize_size(width)
    height = _normalize_size(height)

    rng = random.Random(seed)
    grid = [[WALL for _ in range(width)] for _ in range(height)]
    start: Position = (1, 1)
    exit_pos: Position = (width - 2, height - 2)

    grid[start[1]][start[0]] = EMPTY
    stack = [start]
    directions = [(0, -2), (2, 0), (0, 2), (-2, 0)]

    while stack:
        x, y = stack[-1]
        neighbors: list[Position] = []

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 1 <= nx < width - 1 and 1 <= ny < height - 1 and grid[ny][nx] == WALL:
                neighbors.append((nx, ny))

        if not neighbors:
            stack.pop()
            continue

        nx, ny = rng.choice(neighbors)
        wall_x = x + (nx - x) // 2
        wall_y = y + (ny - y) // 2
        grid[wall_y][wall_x] = EMPTY
        grid[ny][nx] = EMPTY
        stack.append((nx, ny))

    grid[exit_pos[1]][exit_pos[0]] = EMPTY
    return Maze(width=width, height=height, grid=grid, start=start, exit=exit_pos)


def solve_maze(maze: Maze, start: Position | None = None, goal: Position | None = None) -> list[Position]:
    start = start or maze.start
    goal = goal or maze.exit

    queue = deque([start])
    parents: dict[Position, Position | None] = {start: None}
    directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]

    while queue:
        current = queue.popleft()
        if current == goal:
            break

        x, y = current
        for dx, dy in directions:
            nxt = (x + dx, y + dy)
            if nxt not in parents and maze.is_open(nxt):
                parents[nxt] = current
                queue.append(nxt)

    if goal not in parents:
        return []

    path: list[Position] = []
    current: Position | None = goal
    while current is not None:
        path.append(current)
        current = parents[current]
    path.reverse()
    return path


def render_maze(maze: Maze, player: Position | None = None, path: list[Position] | None = None) -> str:
    path_points = set(path or [])
    rows: list[str] = []

    for y, row in enumerate(maze.grid):
        chars: list[str] = []
        for x, cell in enumerate(row):
            pos = (x, y)
            if pos == player:
                chars.append("@")
            elif pos == maze.start:
                chars.append("S")
            elif pos == maze.exit:
                chars.append("E")
            elif pos in path_points and cell == EMPTY:
                chars.append(".")
            else:
                chars.append(cell)
        rows.append("".join(chars))

    return "\n".join(rows)
