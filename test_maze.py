import unittest

from maze import generate_maze, solve_maze


class MazeTests(unittest.TestCase):
    def test_generator_creates_open_start_and_exit(self) -> None:
        maze = generate_maze(21, 21, seed=7)

        self.assertTrue(maze.is_open(maze.start))
        self.assertTrue(maze.is_open(maze.exit))

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


if __name__ == "__main__":
    unittest.main()
