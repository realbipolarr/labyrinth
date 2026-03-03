from __future__ import annotations

import argparse

from arcade_game import run as run_arcade
from console_game import run_console


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Labyrinth game")
    parser.add_argument(
        "--console",
        action="store_true",
        help="run the old console version instead of the Arcade client",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.console:
        run_console()
    else:
        run_arcade()


if __name__ == "__main__":
    main()
