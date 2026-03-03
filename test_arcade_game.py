import unittest

from arcade_game import (
    build_objective_route,
    pick_door_position,
    pick_key_position,
    pick_shard_positions,
    pick_trap_positions,
    progress_hint,
)
from maze import generate_maze


class ArcadeLogicTests(unittest.TestCase):
    def test_pick_shard_positions_returns_unique_open_cells(self) -> None:
        maze = generate_maze(21, 21, seed=5)
        shards = pick_shard_positions(maze, count=3, seed=11)

        self.assertEqual(len(shards), 3)
        self.assertEqual(len(set(shards)), 3)
        self.assertNotIn(maze.start, shards)
        self.assertNotIn(maze.exit, shards)
        for shard in shards:
            self.assertTrue(maze.is_open(shard))

    def test_route_collects_all_shards_before_exit(self) -> None:
        maze = generate_maze(21, 21, seed=7)
        shards = pick_shard_positions(maze, count=3, seed=13)
        route = build_objective_route(maze, maze.start, maze.exit, shards)

        self.assertTrue(route)
        self.assertEqual(route[0], maze.start)
        self.assertEqual(route[-1], maze.exit)
        exit_index = route.index(maze.exit)

        for shard in shards:
            self.assertIn(shard, route)
            self.assertLess(route.index(shard), exit_index)

        for current, nxt in zip(route, route[1:]):
            self.assertEqual(abs(current[0] - nxt[0]) + abs(current[1] - nxt[1]), 1)

    def test_progress_hint_switches_to_exit_after_last_shard(self) -> None:
        self.assertEqual(progress_hint(2), "Продвигайтесь к следующему осколку.")
        self.assertEqual(progress_hint(0), "Все осколки собраны. Ищите выход.")

    def test_pick_key_and_traps_avoid_forbidden_cells(self) -> None:
        maze = generate_maze(21, 21, seed=17)
        shards = pick_shard_positions(maze, count=3, seed=19)
        key = pick_key_position(maze, {maze.start, maze.exit, *shards}, seed=23)
        route = build_objective_route(maze, maze.start, maze.exit, shards)
        traps = pick_trap_positions(
            maze,
            {maze.start, maze.exit, *shards} | ({key} if key else set()),
            route,
            count=3,
            seed=29,
        )

        self.assertIsNotNone(key)
        self.assertNotIn(key, shards)
        self.assertNotIn(key, {maze.start, maze.exit})
        for trap in traps:
            self.assertNotIn(trap, shards)
            self.assertNotIn(trap, route)
            self.assertNotEqual(trap, key)

    def test_pick_door_returns_wall_or_none(self) -> None:
        maze = generate_maze(21, 21, seed=31)
        door = pick_door_position(maze, seed=37)

        if door is not None:
            self.assertFalse(maze.is_open(door))
            self.assertTrue(maze.in_bounds(door))


if __name__ == "__main__":
    unittest.main()
