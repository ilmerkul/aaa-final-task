from copy import deepcopy
from typing import Tuple

FREE_SPACE = '.'
CROSS = 'X'
ZERO = 'O'

DEFAULT_STATE = [[FREE_SPACE for _ in range(3)] for _ in range(3)]


class TicTacToe:
    free_space = FREE_SPACE
    cross = CROSS
    zero = ZERO

    default_state = DEFAULT_STATE

    def __init__(self):
        pass

    @staticmethod
    def get_empty_cells(fields: list[list[str]]) -> list[Tuple[int, int]]:
        return [(i, j) for i in range(len(fields)) for j in
                range(len(fields[0]))
                if fields[i][j] == FREE_SPACE]

    @staticmethod
    def get_default_state():
        """Helper function to get default state of the game"""
        return deepcopy(DEFAULT_STATE)

    @staticmethod
    def check_horizontal_line_won(fields: list[list[str]],
                                  player: str) -> bool:
        for y in range(len(fields)):
            for x in range(len(fields[0])):
                if fields[y][x] != player:
                    break
            else:
                return True

        return False

    @staticmethod
    def check_vertical_line_won(fields: list[list[str]], player: str) -> bool:
        for y in range(len(fields[0])):
            for x in range(len(fields)):
                if fields[x][y] != player:
                    break
            else:
                return True

        return False

    @staticmethod
    def check_right_diag_won(fields: list[list[str]], player: str) -> bool:
        for i in range(len(fields)):
            if fields[i][i] != player:
                return False

        return True

    @staticmethod
    def check_left_diag_won(fields: list[list[str]], player: str) -> bool:
        for i in range(len(fields)):
            if fields[i][len(fields[0]) - i - 1] != player:
                return False

        return True

    @staticmethod
    def check_diag_won(fields: list[list[str]], player: str) -> bool:
        return TicTacToe.check_right_diag_won(fields, player) \
               or TicTacToe.check_left_diag_won(fields, player)

    @staticmethod
    def check_line_won(fields: list[list[str]], player: str) -> bool:
        return (TicTacToe.check_horizontal_line_won(fields, player)
                or TicTacToe.check_vertical_line_won(fields, player)
                or TicTacToe.check_diag_won(fields, player))

    @staticmethod
    def won(fields: list[list[str]], player: str) -> bool:
        """Check if crosses or zeros have won the game"""

        return TicTacToe.check_line_won(fields, player)
