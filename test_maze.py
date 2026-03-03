import unittest

from maze import EMPTY, Maze, generate_maze, solve_maze, visible_cells


class MazeTests(unittest.TestCase):
    def test_generator_creates_open_start_and_exit(self) -> None:
        maze = generate_maze(21, 21, seed=7)

        self.assertTrue(maze.is_open(maze.start))
        self.assertTrue(maze.is_open(maze.exit))

    def test_generator_supports_exact_even_sizes(self) -> None:
        maze = generate_maze(32, 10, seed=13)

        self.assertEqual(maze.width, 32)
        self.assertEqual(maze.height, 10)
        self.assertTrue(maze.is_open(maze.start))
        self.assertTrue(maze.is_open(maze.exit))
        self.assertTrue(solve_maze(maze))

    def test_solver_finds_path_between_start_and_exit(self) -> None:
        maze = generate_maze(21, 21, seed=11)
        path = solve_maze(maze)

        self.assertTrue(path)
        self.assertEqual(path[0], maze.start)
        self.assertEqual(path[-1], maze.exit)

    def test_solver_path_moves_only_to_neighbor_cells(self) -> None:
        maze = generate_maze(25, 25, seed=19)
        path = solve_maze(maze)

        for current, nxt in zip(path, path[1:]):
            distance = abs(current[0] - nxt[0]) + abs(current[1] - nxt[1])
            self.assertEqual(distance, 1)

    def test_visible_cells_stay_within_maze(self) -> None:
        maze = generate_maze(21, 21, seed=3)
        cells = visible_cells(maze, maze.start, radius=4)

        self.assertTrue(cells)
        for cell in cells:
            self.assertTrue(maze.in_bounds(cell))

    def test_visible_cells_do_not_leak_through_blocked_corridor(self) -> None:
        maze = Maze(
            width=5,
            height=5,
            grid=[
                list("#####"),
                list("#   #"),
                list("#####"),
                list("#   #"),
                list("#####"),
            ],
            start=(1, 1),
            exit=(3, 3),
        )

        cells = visible_cells(maze, (1, 1), radius=4)

        self.assertIn((1, 1), cells)
        self.assertIn((2, 1), cells)
        self.assertNotIn((3, 3), cells)


if __name__ == "__main__":
    unittest.main()
