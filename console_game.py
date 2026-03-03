from __future__ import annotations

import os
import sys
import time

from maze import Maze, generate_maze, render_maze, solve_maze


DEFAULT_WIDTH = 21
DEFAULT_HEIGHT = 21
AUTO_DELAY_SECONDS = 0.08
MOVE_KEYS = {
    "w": (0, -1),
    "a": (-1, 0),
    "s": (0, 1),
    "d": (1, 0),
}


def clear_screen() -> None:
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def read_key() -> str:
    if not sys.stdin.isatty():
        return input("Ваш ход (W/A/S/D, q - выход): ").strip().lower()[:1]

    if os.name == "nt":
        import msvcrt

        key = msvcrt.getwch()
        return key.lower()

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def print_header(maze: Maze, mode_name: str) -> None:
    print(f"Лабиринт {maze.width}x{maze.height} | Режим: {mode_name}")
    print("S - старт, E - выход, @ - игрок, q - выйти")
    print()


def animate_solution(maze: Maze) -> None:
    path = solve_maze(maze)
    if not path:
        print("Не удалось найти путь в сгенерированном лабиринте.")
        return

    for position in path:
        clear_screen()
        print_header(maze, "автопрохождение")
        print(render_maze(maze, player=position, path=path))
        time.sleep(AUTO_DELAY_SECONDS)

    print()
    print(f"Маршрут найден. Длина пути: {len(path) - 1} шагов.")


def run_manual_mode(maze: Maze) -> None:
    player = maze.start
    steps = 0

    while True:
        clear_screen()
        print_header(maze, "ручное прохождение")
        print(render_maze(maze, player=player))
        print()
        print(f"Шаги: {steps}")
        print("Управление: W/A/S/D")

        if player == maze.exit:
            print("Вы дошли до выхода.")
            return

        key = read_key()
        if key == "q":
            print()
            print("Игра завершена пользователем.")
            return

        if key not in MOVE_KEYS:
            continue

        dx, dy = MOVE_KEYS[key]
        next_position = (player[0] + dx, player[1] + dy)
        if maze.is_open(next_position):
            player = next_position
            steps += 1


def choose_mode() -> str:
    while True:
        clear_screen()
        print("Игра Лабиринт")
        print("1. Сгенерировать лабиринт и показать автопрохождение")
        print("2. Сгенерировать лабиринт и пройти вручную через WASD")
        print("q. Выход")
        print()

        choice = input("Выберите режим: ").strip().lower()
        if choice in {"1", "2", "q"}:
            return choice


def ask_restart() -> bool:
    answer = input("Сыграть ещё раз? (y/n): ").strip().lower()
    return answer in {"y", "yes", "д", "да"}


def run_console() -> None:
    while True:
        choice = choose_mode()
        if choice == "q":
            return

        maze = generate_maze(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        if choice == "1":
            animate_solution(maze)
        else:
            run_manual_mode(maze)

        print()
        if not ask_restart():
            return
