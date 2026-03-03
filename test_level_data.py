import unittest

from level_data import Door, Key, LevelData, generate_random_level, make_maze_from_grid, solve_level, validate_level


class LevelDataTests(unittest.TestCase):
    def test_generate_random_level_preserves_requested_size(self) -> None:
        for width, height in ((10, 10), (16, 16), (24, 24), (32, 24)):
            level = generate_random_level(width, height, seed=width * 100 + height)
            self.assertEqual(level.maze.width, width)
            self.assertEqual(level.maze.height, height)
            self.assertTrue(validate_level(level).ok)
            self.assertTrue(solve_level(level))

    def test_solver_handles_colored_key_door_and_shards(self) -> None:
        grid = [
            list("#######"),
            list("#     #"),
            list("##### #"),
            list("##### #"),
            list("#######"),
        ]
        maze = make_maze_from_grid(grid, (1, 1), (5, 3))
        level = LevelData(
            maze=maze,
            shard_positions=((3, 1),),
            doors=(Door(position=(5, 2), color="yellow"),),
            keys=(Key(position=(2, 1), color="yellow"),),
        )

        route = solve_level(level)
        self.assertTrue(route)
        self.assertEqual(route[0], (1, 1))
        self.assertEqual(route[-1], (5, 3))
        self.assertIn((2, 1), route)
        self.assertIn((3, 1), route)
        self.assertIn((5, 2), route)

    def test_validate_level_rejects_door_without_matching_key(self) -> None:
        grid = [
            list("#####"),
            list("#   #"),
            list("#   #"),
            list("#   #"),
            list("#####"),
        ]
        maze = make_maze_from_grid(grid, (1, 1), (3, 3))
        level = LevelData(
            maze=maze,
            doors=(Door(position=(2, 2), color="cyan"),),
        )

        result = validate_level(level)
        self.assertFalse(result.ok)
        self.assertIn("нужен ключ", result.message.lower())

    def test_validate_level_rejects_solution_that_steps_on_trap(self) -> None:
        grid = [
            list("#####"),
            list("#   #"),
            list("#####"),
        ]
        maze = make_maze_from_grid(grid, (1, 1), (3, 1))
        level = LevelData(
            maze=maze,
            trap_positions=((2, 1),),
        )

        result = validate_level(level)
        self.assertFalse(result.ok)
        self.assertIn("не проходится", result.message.lower())


if __name__ == "__main__":
    unittest.main()
