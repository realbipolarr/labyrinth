import unittest

from arcade_game import build_objective_route, pick_shard_positions
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


if __name__ == "__main__":
    unittest.main()
