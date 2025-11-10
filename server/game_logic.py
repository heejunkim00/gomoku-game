#!/usr/bin/env python3
"""
오목 게임 로직 (Gomoku Game Logic)
- 15x15 보드 관리
- 돌 배치 및 유효성 검증
- 승리 조건 감지 (5개 연속)
"""

class GomokuBoard:
    """오목 게임 보드 클래스"""

    def __init__(self, size=15):
        """
        보드 초기화

        Args:
            size: 보드 크기 (기본 15x15)
        """
        self.size = size
        self.board = [[None for _ in range(size)] for _ in range(size)]
        # None = 빈칸, "black" = 흑돌, "white" = 백돌

    def is_valid_position(self, x, y):
        """
        좌표가 유효한지 확인

        Args:
            x, y: 보드 좌표

        Returns:
            bool: 유효하면 True
        """
        return 0 <= x < self.size and 0 <= y < self.size

    def is_empty(self, x, y):
        """
        해당 위치가 비어있는지 확인

        Args:
            x, y: 보드 좌표

        Returns:
            bool: 비어있으면 True
        """
        if not self.is_valid_position(x, y):
            return False
        return self.board[x][y] is None

    def place_stone(self, x, y, color):
        """
        돌을 놓습니다

        Args:
            x, y: 보드 좌표
            color: 돌 색상 ("black" 또는 "white")

        Returns:
            bool: 성공하면 True

        Raises:
            ValueError: 유효하지 않은 이동인 경우
        """
        if not self.is_valid_position(x, y):
            raise ValueError(f"Invalid position: ({x}, {y})")

        if not self.is_empty(x, y):
            raise ValueError(f"Position already occupied: ({x}, {y})")

        if color not in ["black", "white"]:
            raise ValueError(f"Invalid color: {color}")

        self.board[x][y] = color
        return True

    def check_winner(self, x, y):
        """
        특정 위치에 돌을 놓은 후 승리했는지 확인합니다
        (최근에 놓은 돌 기준으로 5개 연속 체크)

        Args:
            x, y: 최근에 돌을 놓은 위치

        Returns:
            str: 승리한 색상 ("black" 또는 "white") 또는 None
        """
        color = self.board[x][y]
        if color is None:
            return None

        # 4방향 체크: 가로, 세로, 대각선↘, 대각선↙
        directions = [
            [(0, 1), (0, -1)],    # 가로 (→, ←)
            [(1, 0), (-1, 0)],    # 세로 (↓, ↑)
            [(1, 1), (-1, -1)],   # 대각선 (↘, ↖)
            [(1, -1), (-1, 1)]    # 대각선 (↙, ↗)
        ]

        for direction_pair in directions:
            count = 1  # 현재 돌 포함

            # 양방향으로 확인
            for dx, dy in direction_pair:
                # 해당 방향으로 계속 탐색
                nx, ny = x + dx, y + dy
                while self.is_valid_position(nx, ny) and self.board[nx][ny] == color:
                    count += 1
                    nx += dx
                    ny += dy

            # 5개 이상 연속이면 승리!
            if count >= 5:
                return color

        return None

    def get_board_state(self):
        """
        현재 보드 상태를 반환

        Returns:
            list: 2D 리스트로 된 보드 상태
        """
        return [row[:] for row in self.board]  # 복사본 반환

    def reset(self):
        """보드를 초기화합니다"""
        self.board = [[None for _ in range(self.size)] for _ in range(self.size)]

    def get_stone_at(self, x, y):
        """
        특정 위치의 돌 색상을 반환

        Args:
            x, y: 보드 좌표

        Returns:
            str: "black", "white", 또는 None
        """
        if not self.is_valid_position(x, y):
            return None
        return self.board[x][y]

    def count_stones(self):
        """
        보드에 놓인 돌의 개수를 세어 반환

        Returns:
            dict: {"black": count, "white": count, "empty": count}
        """
        black_count = 0
        white_count = 0
        empty_count = 0

        for row in self.board:
            for cell in row:
                if cell == "black":
                    black_count += 1
                elif cell == "white":
                    white_count += 1
                else:
                    empty_count += 1

        return {
            "black": black_count,
            "white": white_count,
            "empty": empty_count
        }

    def is_board_full(self):
        """
        보드가 가득 찼는지 확인 (무승부 판정용)

        Returns:
            bool: 가득 차면 True
        """
        for row in self.board:
            if None in row:
                return False
        return True

    def display(self):
        """
        보드를 터미널에 출력합니다 (디버깅/테스트용)
        """
        print("   ", end="")
        for i in range(self.size):
            print(f"{i:2}", end=" ")
        print()

        for i, row in enumerate(self.board):
            print(f"{i:2} ", end="")
            for cell in row:
                if cell == "black":
                    print(" ●", end=" ")
                elif cell == "white":
                    print(" ○", end=" ")
                else:
                    print(" ·", end=" ")
            print()


# 사용 예시:
"""
# 보드 생성
board = GomokuBoard()

# 돌 놓기
board.place_stone(7, 7, "black")
board.place_stone(7, 8, "white")

# 승리 확인
board.place_stone(8, 7, "black")
board.place_stone(8, 8, "white")
board.place_stone(9, 7, "black")
board.place_stone(9, 8, "white")
board.place_stone(10, 7, "black")
board.place_stone(10, 8, "white")
board.place_stone(11, 7, "black")

winner = board.check_winner(11, 7)
if winner:
    print(f"{winner} wins!")

# 보드 출력
board.display()
"""
