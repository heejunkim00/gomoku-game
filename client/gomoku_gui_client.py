#!/usr/bin/env python3
"""
오목 게임 GUI 클라이언트 (Pygame)
- 전통 바둑판 스타일
- 나무 질감 배경
- 돌에 그림자 효과
"""

import pygame
import socket
import threading
import sys
import os
import time

# 상위 디렉토리의 모듈을 import하기 위한 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.protocol import Protocol, MessageType

# 색상 정의
WOOD_COLOR = (220, 179, 92)       # 나무 배경색
GRID_COLOR = (50, 50, 50)         # 격자선 색
BLACK_STONE = (20, 20, 20)        # 흑돌
WHITE_STONE = (240, 240, 240)     # 백돌
SHADOW_COLOR = (100, 100, 100, 128)  # 그림자
TEXT_COLOR = (50, 50, 50)         # 텍스트
HIGHLIGHT_COLOR = (255, 0, 0)     # 하이라이트
BG_COLOR = (245, 222, 179)        # 배경색 (밝은 나무색)

# 화면 설정 (MacBook M3 13인치 4분할 최적화)
# 전체: 2560x1664, 4분할: 1280x832 (실제로는 메뉴바 등 고려 시 약 1280x780)
BOARD_SIZE = 15
CELL_SIZE = 32  # 보드 크기 적절하게 조정
BOARD_OFFSET = 30  # 보드 여백
BOARD_PIXEL_SIZE = CELL_SIZE * (BOARD_SIZE - 1)

# UI 영역 
INFO_HEIGHT = 120  # 정보 영역 높이 늘림
CHAT_WIDTH = 250  # 채팅 영역 너비
WINDOW_WIDTH = BOARD_OFFSET * 2 + BOARD_PIXEL_SIZE + CHAT_WIDTH  # 약 758
WINDOW_HEIGHT = BOARD_OFFSET + BOARD_PIXEL_SIZE + INFO_HEIGHT  # 약 598

class GomokuGUIClient:
    """Pygame GUI 오목 클라이언트"""

    def __init__(self, host='localhost', port=10000):
        """초기화"""
        self.host = host
        self.port = port
        self.socket = None
        self.running = False

        # 게임 상태
        self.current_room = None
        self.my_role = None
        self.my_color = None
        self.my_name = None
        self.board = [[None for _ in range(15)] for _ in range(15)]
        self.current_turn = "black"
        self.game_status = "waiting"
        self.last_move = None  # 마지막 수 하이라이트용

        # 채팅
        self.chat_messages = []  # 플레이어 채팅 (모든 사람이 보는 채팅)
        self.spectator_chat_messages = []  # 관전자 전용 채팅
        self.chat_input = ""
        self.spectator_chat_input = ""
        
        # 레디 상태
        self.ready_status = {}  # {"player_name": ready_bool}
        self.my_ready = False
        
        # 타이머 상태
        self.remaining_time = 0
        
        # 리매치 상태
        self.rematch_requested = False  # 내가 리매치 요청했는지
        self.opponent_rematch_requested = False  # 상대가 리매치 요청했는지
        self.rematch_requester = None  # 리매치 요청자 이름
        
        # 재연결 상태
        self.last_room_id = None  # 마지막으로 있던 방 ID
        self.was_playing = False  # 게임 중 연결이 끊겼었는지
        self.reconnect_available = False  # 재연결 가능 여부
        
        # 상대방 연결 끊김 상태
        self.opponent_disconnected = False  # 상대방이 연결 끊겼는지
        self.opponent_disconnect_time = None  # 상대방 연결 끊긴 시간
        self.reconnect_timeout = 180  # 3분 타임아웃

        # Pygame 초기화
        pygame.init()
        # macOS에서 창 크기 조정 가능하게 설정 (제한적으로 작동)
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Gomoku Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 20)
        self.small_font = pygame.font.Font(None, 16)

        # 로비 UI 상태
        self.in_lobby = True
        self.rooms_list = []
        self.name_input = ""
        self.selected_room = None
        self.last_room_update = 0  # 마지막 룸 리스트 업데이트 시간
        self.system_message = ""  # 시스템 메시지
        self.system_message_time = 0  # 시스템 메시지 표시 시작 시간

    def connect(self):
        """서버에 연결"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((self.host, self.port))
            self.running = True
            print(f"[+] Connected to server {self.host}:{self.port}")
            
            # 재연결 가능한 경우 자동으로 재연결 시도
            if self.reconnect_available and self.my_name:
                print(f"[*] Attempting to reconnect as {self.my_name}")
                time.sleep(0.5)  # 서버가 준비될 시간
                self.send_reconnect()
            
            return True
        except Exception as e:
            print(f"[!] Connection failed: {e}")
            return False

    def receive_messages(self):
        """서버로부터 메시지 받기 (별도 스레드)"""
        print("[DEBUG] Message receiver thread started")
        while self.running:
            try:
                raw_data = self.socket.recv(4096)
                if not raw_data:
                    print("[DEBUG] No data received, closing connection")
                    # 게임 중이었다면 재연결 가능 상태로 설정
                    if self.game_status == "playing" and self.current_room:
                        self.was_playing = True
                        self.last_room_id = self.current_room
                        self.reconnect_available = True
                        print(f"[*] Disconnected during game. Reconnection available for room {self.last_room_id}")
                        self.add_chat_message("SYSTEM", "Connection lost! You can reconnect within 60 seconds.", "error")
                    self.running = False
                    break

                print(f"[DEBUG] Received raw data: {len(raw_data)} bytes")
                messages = Protocol.parse_messages(raw_data)
                print(f"[DEBUG] Parsed {len(messages)} messages")
                for message in messages:
                    self.handle_server_message(message)

            except Exception as e:
                if self.running:
                    print(f"[!] Error: {e}")
                    # 게임 중 오류 시에도 재연결 가능하게
                    if self.game_status == "playing" and self.current_room:
                        self.was_playing = True
                        self.last_room_id = self.current_room
                        self.reconnect_available = True
                break

    def handle_server_message(self, message):
        """서버 메시지 처리"""
        msg_type = message["type"]
        data = message.get("data", {})
        print(f"[DEBUG] Received message type: {msg_type}, data: {data}")

        if msg_type == MessageType.ERROR:
            error_msg = data.get('message', 'Unknown error')
            print(f"[ERROR] {error_msg}")
            self.add_chat_message("SYSTEM", error_msg, "error")
            
            # 재연결 실패 처리
            if "reconnect" in error_msg.lower() or "not found" in error_msg.lower():
                self.reconnect_available = False
                self.was_playing = False
                
        elif msg_type == MessageType.SUCCESS:
            # 재연결 성공 처리
            if "Reconnected successfully" in data.get("message", ""):
                print(f"[DEBUG] Reconnection successful!")
                self.current_room = data["room_id"]
                self.my_role = data.get("role", "player")
                self.my_color = data.get("your_color")
                self.board = data.get("board", [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)])
                self.current_turn = data.get("current_turn", "black")
                self.game_status = data.get("game_status", "playing")
                self.remaining_time = data.get("remaining_time", 0)
                self.in_lobby = False
                self.reconnect_available = False
                self.was_playing = False
                self.add_chat_message("SYSTEM", "Reconnected successfully!", "success")
                print(f"[*] Reconnected to room {self.current_room}")
            elif "room_id" in data:
                print(f"[DEBUG] Entering room: {data['room_id']}")
                self.current_room = data["room_id"]
                self.my_role = data.get("role")
                self.my_color = data.get("your_color")
                if "board" in data:
                    self.board = data["board"]
                else:
                    # 보드가 없으면 초기화
                    self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
                if "current_turn" in data:
                    self.current_turn = data["current_turn"]
                else:
                    self.current_turn = "black"
                if "game_status" in data:
                    self.game_status = data["game_status"]
                else:
                    self.game_status = "waiting"  # 기본값
                if "remaining_time" in data:
                    self.remaining_time = data["remaining_time"]
                self.in_lobby = False
                # 새 방에 들어갈 때 채팅 메시지 리셋
                self.chat_messages = []
                self.spectator_chat_messages = []
                self.chat_input = ""
                self.spectator_chat_input = ""
                print(f"[DEBUG] Room entered. Status: {self.game_status}, Role: {self.my_role}")
            elif "Left room" in data.get("message", "") or "lobby" in data.get("message", "").lower():
                # 룸에서 나갔을 때 로비로 돌아가기
                self.in_lobby = True
                self.current_room = None
                self.my_role = None
                self.my_color = None
                self.game_status = "waiting"
                self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
                self.last_move = None
                # 채팅 메시지 리셋
                self.chat_messages = []
                self.spectator_chat_messages = []
                self.chat_input = ""
                self.spectator_chat_input = ""
                print("[*] Returned to lobby")

        elif msg_type == MessageType.ROOM_LIST:
            self.rooms_list = data.get("rooms", [])

        elif msg_type == MessageType.GAME_START:
            self.game_status = "playing"
            self.current_turn = data.get("current_turn", "black")
            # 서버에서 보드 상태가 제공되면 사용 (리매치 시)
            if "board" in data:
                self.board = data["board"]
                self.last_move = None
            # 리매치 상태 초기화
            self.rematch_requested = False
            self.opponent_rematch_requested = False
            self.rematch_requester = None
            # 플레이어 색상 업데이트 (리매치 시 색상 교체)
            if "players" in data:
                players = data.get("players", [])
                for player in players:
                    if player["name"] == self.my_name:
                        old_color = self.my_color
                        self.my_color = player["color"]
                        if old_color and old_color != self.my_color:
                            # 리매치로 색상이 바뀌었음
                            self.add_chat_message("SYSTEM", f"Rematch started! Your color: {self.my_color}", "system")
                        break

        elif msg_type == MessageType.BOARD_UPDATE:
            x = data.get("x")
            y = data.get("y")
            self.board = data.get("board", self.board)
            self.last_move = (x, y)

        elif msg_type == MessageType.TURN_CHANGE:
            self.current_turn = data.get("current_turn")

        elif msg_type == MessageType.GAME_END:
            winner = data.get("winner")
            winner_name = data.get("winner_name")
            self.game_status = "finished"
            self.show_game_over(winner_name, winner)

        elif msg_type == MessageType.READY_STATUS:
            self.ready_status = data.get("ready_status", {})
            # 내 레디 상태 업데이트
            if self.my_name and self.my_name in self.ready_status:
                self.my_ready = self.ready_status[self.my_name]
            
        elif msg_type == MessageType.CHAT_MESSAGE:
            sender = data.get("sender")
            role = data.get("role")
            msg_text = data.get("message")
            self.add_chat_message(sender, msg_text, role)
            
        elif msg_type == MessageType.SPECTATOR_CHAT:
            sender = data.get("sender")
            msg_text = data.get("message")
            self.add_spectator_chat_message(sender, msg_text)
            
        elif msg_type == MessageType.TIMER_UPDATE:
            new_time = data.get("remaining_time", 0)
            print(f"[DEBUG] Received TIMER_UPDATE: {new_time} seconds")
            self.remaining_time = new_time
            
        elif msg_type == MessageType.TIME_UP:
            timeout_player = data.get("player")
            self.add_chat_message("SYSTEM", f"{timeout_player} player time's up!", "system")
            print(f"[DEBUG] Received TIME_UP for {timeout_player}")
            # TIME_UP 메시지는 타이머 리셋을 하지 않음 (서버에서 TIMER_UPDATE로 처리)
            
        elif msg_type == MessageType.PLAYER_DISCONNECTED:
            player_name = data.get("player_name")
            self.add_chat_message("SYSTEM", f"{player_name} disconnected (3 minutes to reconnect)", "system")
            self.opponent_disconnected = True
            self.opponent_disconnect_time = time.time()
            
        elif msg_type == MessageType.PLAYER_RECONNECTED:
            player_name = data.get("player_name")
            self.add_chat_message("SYSTEM", f"{player_name} reconnected", "system")
            self.opponent_disconnected = False
            self.opponent_disconnect_time = None
            
        elif msg_type == MessageType.GAME_PAUSED:
            reason = data.get("reason")
            self.add_chat_message("SYSTEM", f"Game paused: {reason}", "system")
            
        elif msg_type == MessageType.GAME_RESUMED:
            self.add_chat_message("SYSTEM", "Game resumed!", "system")
            
        elif msg_type == MessageType.FORFEIT:
            # 몰수패 처리
            winner = data.get("winner")
            player_name = data.get("player_name")
            self.add_chat_message("SYSTEM", f"{player_name} forfeited due to disconnection. {winner} wins!", "system")
            self.game_status = "finished"
            self.opponent_disconnected = False
            self.opponent_disconnect_time = None
            
        elif msg_type == MessageType.REMATCH:
            # 리매치 요청 받음
            requesting_player = data.get("requesting_player")
            if requesting_player != self.my_name:
                self.opponent_rematch_requested = True
                self.rematch_requester = requesting_player
                self.rematch_timeout = time.time() + data.get("timeout", 30)  # 타임아웃 설정
                self.add_chat_message("SYSTEM", f"{requesting_player} wants a rematch!", "system")
        
        elif msg_type == MessageType.REMATCH_DECLINED:
            # 리매치 거절 처리
            self.opponent_rematch_requested = False
            self.rematch_requester = None
            self.rematch_requested = False
            self.add_chat_message("SYSTEM", data.get("message", "Rematch declined"), "system")
        
        elif msg_type == MessageType.SUCCESS:
            # Rematch 수락 대기 메시지 처리
            if data.get("rematch_accepted"):
                self.add_chat_message("SYSTEM", data.get("message", "Waiting for other player..."), "system")
            # Leave room 성공 처리
            elif "Left room" in data.get("message", ""):
                self.in_lobby = True
                self.current_room = None
                self.game_status = "waiting"
                self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
                # 채팅 메시지 리셋
                self.chat_messages = []
                self.spectator_chat_messages = []
                self.chat_input = ""
                self.spectator_chat_input = ""
        
        elif msg_type == MessageType.ROOM_UPDATE:
            # 룸 상태 업데이트 (플레이어 나갔을 때 등)
            if "status" in data:
                self.game_status = data["status"]
            if "board" in data:
                self.board = data["board"]
                self.last_move = None
            if "message" in data:
                self.add_chat_message("SYSTEM", data["message"], "system")
            # 리매치 상태 초기화
            self.rematch_requested = False
            self.opponent_rematch_requested = False
            self.rematch_requester = None

    def add_chat_message(self, sender, message, role):
        """플레이어 채팅 메시지 추가"""
        prefix = "[P]" if role == "player" else "[S]"
        self.chat_messages.append(f"{prefix} {sender}: {message}")
        if len(self.chat_messages) > 15:
            self.chat_messages.pop(0)

    def add_spectator_chat_message(self, sender, message):
        """관전자 채팅 메시지 추가"""
        self.spectator_chat_messages.append(f"[SPEC] {sender}: {message}")
        if len(self.spectator_chat_messages) > 15:
            self.spectator_chat_messages.pop(0)
    
    def set_system_message(self, message):
        """시스템 메시지 설정 (3초간 표시)"""
        self.system_message = message
        self.system_message_time = time.time()

    def show_game_over(self, winner_name, winner_color):
        """게임 종료 팝업"""
        # 간단한 텍스트 표시 (나중에 팝업으로 개선 가능)
        if self.my_color == winner_color:
            self.add_chat_message("SYSTEM", "YOU WIN!", "system")
        elif self.my_role == "player":
            self.add_chat_message("SYSTEM", f"{winner_name} wins!", "system")
        else:
            self.add_chat_message("SYSTEM", f"{winner_name} wins!", "system")

    def draw_board(self):
        """바둑판 그리기"""
        # 배경 (나무 질감)
        self.screen.fill(BG_COLOR)

        # 보드 영역 (약간 어두운 나무색)
        board_rect = pygame.Rect(
            BOARD_OFFSET - 20,
            BOARD_OFFSET - 20,
            BOARD_PIXEL_SIZE + 40,
            BOARD_PIXEL_SIZE + 40
        )
        pygame.draw.rect(self.screen, WOOD_COLOR, board_rect)
        pygame.draw.rect(self.screen, GRID_COLOR, board_rect, 2)

        # 격자선 그리기
        for i in range(BOARD_SIZE):
            # 세로선
            x = BOARD_OFFSET + i * CELL_SIZE
            pygame.draw.line(
                self.screen, GRID_COLOR,
                (x, BOARD_OFFSET),
                (x, BOARD_OFFSET + BOARD_PIXEL_SIZE),
                2
            )
            # 가로선
            y = BOARD_OFFSET + i * CELL_SIZE
            pygame.draw.line(
                self.screen, GRID_COLOR,
                (BOARD_OFFSET, y),
                (BOARD_OFFSET + BOARD_PIXEL_SIZE, y),
                2
            )

        # 화점 그리기 (3-3, 3-11, 7-7, 11-3, 11-11)
        star_points = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]
        for px, py in star_points:
            x = BOARD_OFFSET + px * CELL_SIZE
            y = BOARD_OFFSET + py * CELL_SIZE
            pygame.draw.circle(self.screen, GRID_COLOR, (x, y), 5)

        # 돌 그리기
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if self.board[row][col]:
                    self.draw_stone(row, col, self.board[row][col])

        # 마지막 수 하이라이트
        if self.last_move:
            x = BOARD_OFFSET + self.last_move[1] * CELL_SIZE
            y = BOARD_OFFSET + self.last_move[0] * CELL_SIZE
            pygame.draw.circle(self.screen, HIGHLIGHT_COLOR, (x, y), 5)

    def draw_stone(self, row, col, color):
        """돌 그리기 (그림자 효과 포함)"""
        x = BOARD_OFFSET + col * CELL_SIZE
        y = BOARD_OFFSET + row * CELL_SIZE
        radius = int(CELL_SIZE * 0.42)  # 비율에 맞게 조정

        # 그림자 (약간 오른쪽 아래)
        shadow_surface = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        pygame.draw.circle(shadow_surface, SHADOW_COLOR, (radius + 3, radius + 3), radius)
        self.screen.blit(shadow_surface, (x - radius - 2, y - radius - 2))

        # 돌
        stone_color = BLACK_STONE if color == "black" else WHITE_STONE
        pygame.draw.circle(self.screen, stone_color, (x, y), radius)

        # 하이라이트 (입체감)
        if color == "white":
            highlight_pos = (x - radius // 3, y - radius // 3)
            pygame.draw.circle(self.screen, (255, 255, 255), highlight_pos, radius // 4)
        else:
            highlight_pos = (x - radius // 3, y - radius // 3)
            pygame.draw.circle(self.screen, (80, 80, 80), highlight_pos, radius // 4)

    def draw_info(self):
        """게임 정보 표시"""
        y_offset = BOARD_OFFSET + BOARD_PIXEL_SIZE + 30

        # 룸 정보
        if self.current_room:
            info_text = f"Room: {self.current_room}  |  "
            if self.my_role == "player":
                color_name = "Black" if self.my_color == "black" else "White"
                info_text += f"You: {color_name}  |  "
            else:
                info_text += "Spectator  |  "

            turn_name = "Black" if self.current_turn == "black" else "White"
            info_text += f"Turn: {turn_name}  |  Status: {self.game_status}"

            text_surface = self.font.render(info_text, True, TEXT_COLOR)
            self.screen.blit(text_surface, (10, y_offset))  # 20 -> 10 (더 왼쪽으로)

            # 내 차례 표시 (삭제 - draw_timer에서 처리)
                
        # 타이머 표시 (게임 중일 때만)
        if self.game_status == "playing":
            self.draw_timer(y_offset + 25)  # 위로 올림
                
        # 레디 버튼과 상태 표시
        if self.my_role == "player" and self.game_status == "waiting":
            self.draw_ready_section(y_offset + 30)  # 위로 올림
        
        # 게임 중 액션 버튼들 (Surrender)
        if self.my_role == "player" and self.game_status == "playing":
            self.draw_game_actions(y_offset + 25)  # 타이머와 같은 높이
        
        # 게임 종료 후 액션 버튼들
        if self.my_role == "player" and self.game_status == "finished":
            self.draw_post_game_actions(y_offset + 40)  # 위로 올림
        
        # 대기 중일 때도 Leave 버튼 표시 (레디 버튼 옆)
        elif self.my_role == "player" and self.game_status == "waiting":
            self.draw_leave_button_only(y_offset + 30)  # 위로 올림
        
        # 관전자용 Leave 버튼 표시
        if self.my_role == "spectator":
            self.draw_spectator_leave_button(y_offset + 30)  # 위로 올림

    def draw_chat(self):
        """채팅 표시 (두 개 채널)"""
        chat_x = BOARD_OFFSET + BOARD_PIXEL_SIZE + 15  # 채팅창 위치 오른쪽으로 이동
        chat_y = BOARD_OFFSET
        
        # 관전자인지 확인
        is_spectator = (self.my_role == "spectator")
        
        if is_spectator:
            # 관전자: 두 개의 채팅 창을 나누어서 표시
            self.draw_dual_chat(chat_x, chat_y)
        else:
            # 플레이어: 기존 채팅 창만 표시
            self.draw_single_chat(chat_x, chat_y)

    def draw_single_chat(self, chat_x, chat_y):
        """플레이어용 단일 채팅 창"""
        # 채팅 배경
        chat_rect = pygame.Rect(chat_x, chat_y, CHAT_WIDTH - 20, BOARD_PIXEL_SIZE)
        pygame.draw.rect(self.screen, (255, 255, 255), chat_rect)
        pygame.draw.rect(self.screen, GRID_COLOR, chat_rect, 2)

        # 채팅 제목
        title = self.small_font.render("Game Chat", True, TEXT_COLOR)
        self.screen.blit(title, (chat_x + 10, chat_y + 5))

        # 채팅 메시지 (클리핑 영역 설정)
        chat_clip_rect = pygame.Rect(chat_x, chat_y + 30, CHAT_WIDTH - 20, BOARD_PIXEL_SIZE - 65)
        self.screen.set_clip(chat_clip_rect)
        
        msg_y = chat_y + 35
        for msg in self.chat_messages[-12:]:  # 최근 12개
            # 긴 메시지는 줄임
            if len(msg) > 35:
                msg = msg[:32] + "..."
            msg_surface = self.small_font.render(msg, True, TEXT_COLOR)
            self.screen.blit(msg_surface, (chat_x + 10, msg_y))
            msg_y += 25
            # 영역을 벗어나면 중단
            if msg_y > chat_y + BOARD_PIXEL_SIZE - 35:
                break
        
        # 클리핑 영역 해제
        self.screen.set_clip(None)

        # 입력창
        input_y = chat_y + BOARD_PIXEL_SIZE - 30
        input_rect = pygame.Rect(chat_x + 10, input_y, CHAT_WIDTH - 30, 25)
        pygame.draw.rect(self.screen, (240, 240, 240), input_rect)
        pygame.draw.rect(self.screen, GRID_COLOR, input_rect, 1)

        if self.chat_input:
            input_surface = self.small_font.render(self.chat_input, True, TEXT_COLOR)
            self.screen.blit(input_surface, (chat_x + 15, input_y + 3))

    def draw_dual_chat(self, chat_x, chat_y):
        """관전자용 이중 채팅 창 (게임 채팅 + 관전자 채팅)"""
        chat_height = BOARD_PIXEL_SIZE // 2 - 20
        
        # === 게임 채팅 (상단) ===
        game_chat_rect = pygame.Rect(chat_x, chat_y, CHAT_WIDTH - 20, chat_height)
        pygame.draw.rect(self.screen, (255, 255, 255), game_chat_rect)
        pygame.draw.rect(self.screen, GRID_COLOR, game_chat_rect, 2)

        # 게임 채팅 제목
        game_title = self.small_font.render("Game Chat (View Only)", True, TEXT_COLOR)
        self.screen.blit(game_title, (chat_x + 10, chat_y + 5))

        # 게임 채팅 메시지 (클리핑 영역 설정)
        game_clip_rect = pygame.Rect(chat_x, chat_y + 20, CHAT_WIDTH - 20, chat_height - 25)
        self.screen.set_clip(game_clip_rect)
        
        msg_y = chat_y + 25
        for msg in self.chat_messages[-6:]:  # 최근 6개
            if len(msg) > 35:
                msg = msg[:32] + "..."
            msg_surface = self.small_font.render(msg, True, TEXT_COLOR)
            self.screen.blit(msg_surface, (chat_x + 10, msg_y))
            msg_y += 20
            if msg_y > chat_y + chat_height - 5:
                break
        
        self.screen.set_clip(None)

        # === 관전자 채팅 (하단) ===
        spec_chat_y = chat_y + chat_height + 25
        spec_chat_rect = pygame.Rect(chat_x, spec_chat_y, CHAT_WIDTH - 20, chat_height)
        pygame.draw.rect(self.screen, (240, 250, 255), spec_chat_rect)  # 약간 다른 색상
        pygame.draw.rect(self.screen, GRID_COLOR, spec_chat_rect, 2)

        # 관전자 채팅 제목
        spec_title = self.small_font.render("Spectator Chat", True, TEXT_COLOR)
        self.screen.blit(spec_title, (chat_x + 10, spec_chat_y + 5))

        # 관전자 채팅 메시지 (클리핑 영역 설정)
        spec_clip_rect = pygame.Rect(chat_x, spec_chat_y + 20, CHAT_WIDTH - 20, chat_height - 55)
        self.screen.set_clip(spec_clip_rect)
        
        msg_y = spec_chat_y + 25
        for msg in self.spectator_chat_messages[-5:]:  # 최근 5개
            if len(msg) > 35:
                msg = msg[:32] + "..."
            msg_surface = self.small_font.render(msg, True, (0, 0, 150))  # 파란색
            self.screen.blit(msg_surface, (chat_x + 10, msg_y))
            msg_y += 20
            if msg_y > spec_chat_y + chat_height - 35:
                break
        
        self.screen.set_clip(None)

        # 관전자 채팅 입력창
        input_y = spec_chat_y + chat_height - 30
        input_rect = pygame.Rect(chat_x + 10, input_y, CHAT_WIDTH - 30, 25)
        pygame.draw.rect(self.screen, (240, 240, 240), input_rect)
        pygame.draw.rect(self.screen, GRID_COLOR, input_rect, 1)

        if self.spectator_chat_input:
            input_surface = self.small_font.render(self.spectator_chat_input, True, TEXT_COLOR)
            self.screen.blit(input_surface, (chat_x + 15, input_y + 3))

    def draw_ready_section(self, y_start):
        """레디 버튼과 상태 표시"""
        # 레디 버튼
        button_color = (100, 200, 100) if not self.my_ready else (200, 100, 100)
        button_text = "READY" if not self.my_ready else "CANCEL"
        
        ready_btn = pygame.Rect(20, y_start, 100, 40)
        pygame.draw.rect(self.screen, button_color, ready_btn)
        pygame.draw.rect(self.screen, GRID_COLOR, ready_btn, 2)
        
        btn_text_surface = self.font.render(button_text, True, TEXT_COLOR)
        text_rect = btn_text_surface.get_rect(center=ready_btn.center)
        self.screen.blit(btn_text_surface, text_rect)
        
        # 플레이어 레디 상태 표시
        status_y = y_start + 50
        status_text = "Player Status:"
        status_surface = self.small_font.render(status_text, True, TEXT_COLOR)
        self.screen.blit(status_surface, (20, status_y))
        
        status_y += 25
        for player_name, ready in self.ready_status.items():
            ready_indicator = "✓" if ready else "✗"
            color = (0, 150, 0) if ready else (150, 0, 0)
            status_line = f"{ready_indicator} {player_name}"
            
            player_surface = self.small_font.render(status_line, True, color)
            self.screen.blit(player_surface, (30, status_y))
            status_y += 20

    def draw_reconnection_timer(self, x_pos, y_pos):
        """상대방 재연결 대기 타이머 표시"""
        if self.opponent_disconnected and self.opponent_disconnect_time:
            elapsed = time.time() - self.opponent_disconnect_time
            remaining = max(0, self.reconnect_timeout - elapsed)
            
            # 남은 시간 계산 (분:초)
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            
            # 색상 결정
            if remaining > 60:
                timer_color = (0, 150, 0)  # 녹색
            elif remaining > 30:
                timer_color = (255, 165, 0)  # 주황색
            else:
                timer_color = (255, 0, 0)  # 빨간색
            
            # 배경 박스
            box_width = 250
            box_height = 60
            box_rect = pygame.Rect(x_pos - box_width - 10, y_pos - box_height - 10, box_width, box_height)
            pygame.draw.rect(self.screen, (240, 240, 240), box_rect)
            pygame.draw.rect(self.screen, timer_color, box_rect, 3)
            
            # 제목
            title_text = "Opponent Disconnected"
            title_surface = self.font.render(title_text, True, (255, 0, 0))
            title_x = x_pos - box_width//2 - 10 - title_surface.get_width()//2
            self.screen.blit(title_surface, (title_x, y_pos - box_height + 5))
            
            # 타이머
            timer_text = f"Reconnect Time: {minutes:02d}:{seconds:02d}"
            timer_surface = self.font.render(timer_text, True, timer_color)
            timer_x = x_pos - box_width//2 - 10 - timer_surface.get_width()//2
            self.screen.blit(timer_surface, (timer_x, y_pos - box_height + 25))
            
            # 자동 승리 메시지
            if remaining <= 0:
                win_text = "Auto-win in progress..."
                win_surface = self.small_font.render(win_text, True, (0, 100, 0))
                win_x = x_pos - box_width//2 - 10 - win_surface.get_width()//2
                self.screen.blit(win_surface, (win_x, y_pos - box_height + 45))
    
    def draw_timer(self, y_start):
        """타이머 표시"""
        # 현재 턴 플레이어 확인
        current_player = "Black" if self.current_turn == "black" else "White"
        
        # 타이머 색상 결정 (남은 시간에 따라)
        if self.remaining_time > 10:
            timer_color = (0, 150, 0)  # 녹색
        elif self.remaining_time > 5:
            timer_color = (255, 165, 0)  # 주황색
        else:
            timer_color = (255, 0, 0)  # 빨간색
        
        # YOUR TURN 표시 (왼쪽)
        if self.my_role == "player" and self.my_color == self.current_turn:
            your_turn_text = "YOUR TURN!"
            turn_surface = self.font.render(your_turn_text, True, (255, 0, 0))
            self.screen.blit(turn_surface, (20, y_start))
            
            # 타이머 텍스트 (YOUR TURN 오른쪽에 위치)
            timer_text = f"{current_player} Turn: {self.remaining_time}s"
            timer_surface = self.font.render(timer_text, True, timer_color)
            timer_x = 150  # YOUR TURN 충분히 오른쪽
            self.screen.blit(timer_surface, (timer_x, y_start))
        else:
            # YOUR TURN이 아닐 때는 중앙에 표시
            timer_text = f"{current_player} Turn: {self.remaining_time}s"
            timer_surface = self.font.render(timer_text, True, timer_color)
            text_width = timer_surface.get_width()
            timer_x = (220 - text_width) // 2 + 10  # 중앙 정렬
            self.screen.blit(timer_surface, (timer_x, y_start))
        
        # 타이머 바 그리기
        bar_width = 200
        bar_height = 15
        bar_x = 20
        bar_y = y_start + 25
        
        # 배경 바
        bg_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (200, 200, 200), bg_rect)
        pygame.draw.rect(self.screen, GRID_COLOR, bg_rect, 2)
        
        # 남은 시간 바
        if self.remaining_time > 0:
            remaining_width = int((self.remaining_time / 60) * bar_width)
            remaining_rect = pygame.Rect(bar_x, bar_y, remaining_width, bar_height)
            pygame.draw.rect(self.screen, timer_color, remaining_rect)

    def draw_lobby(self):
        """로비 UI 그리기 - 프로페셔널 디자인"""
        # 배경 그라데이션 효과
        for i in range(WINDOW_HEIGHT):
            color_value = int(220 + (i / WINDOW_HEIGHT) * 35)
            pygame.draw.line(self.screen, (color_value, color_value - 10, color_value - 20), (0, i), (WINDOW_WIDTH, i))
        
        # 타이틀 배경 (반투명 효과)
        title_panel = pygame.Rect(0, 0, WINDOW_WIDTH, 70)
        title_surface = pygame.Surface((WINDOW_WIDTH, 70))
        title_surface.set_alpha(230)
        title_surface.fill((50, 50, 60))
        self.screen.blit(title_surface, (0, 0))
        
        # 타이틀
        title_font = pygame.font.Font(None, 32)
        title = title_font.render("GOMOKU ONLINE", True, (255, 255, 255))
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, 35))
        self.screen.blit(title, title_rect)
        
        # 온라인 상태 표시
        status_dot = pygame.Rect(WINDOW_WIDTH - 100, 25, 10, 10)
        pygame.draw.circle(self.screen, (50, 255, 50), (WINDOW_WIDTH - 95, 30), 5)
        online_text = self.small_font.render("Online", True, (200, 255, 200))
        self.screen.blit(online_text, (WINDOW_WIDTH - 85, 23))
        
        # 왼쪽 상단 패널 (플레이어 정보 - 가로로 배치)
        panel_x = 30
        panel_y = 100
        
        # 배경 패널 (Create Room 버튼까지 포함하도록 크기 조정)
        left_panel = pygame.Rect(panel_x, panel_y, 400, 80)
        pygame.draw.rect(self.screen, (255, 255, 255), left_panel)
        pygame.draw.rect(self.screen, (200, 200, 210), left_panel, 2)
        
        # 플레이어 이름 레이블
        name_label = self.font.render("Player Name", True, (80, 80, 90))
        self.screen.blit(name_label, (panel_x + 20, panel_y + 15))

        # 이름 입력창
        name_input_bg = pygame.Rect(panel_x + 20, panel_y + 40, 180, 30)
        pygame.draw.rect(self.screen, (245, 245, 250), name_input_bg)
        pygame.draw.rect(self.screen, (180, 180, 190), name_input_bg, 1)
        if self.name_input:
            name_surface = self.font.render(self.name_input, True, (50, 50, 60))
            self.screen.blit(name_surface, (panel_x + 30, panel_y + 47))
        else:
            hint_text = self.small_font.render("Enter your name...", True, (150, 150, 160))
            self.screen.blit(hint_text, (panel_x + 30, panel_y + 48))
        
        # Create Room 버튼 (입력창 오른쪽에)
        create_btn = pygame.Rect(panel_x + 210, panel_y + 40, 170, 30)
        if self.name_input:
            # 활성화 상태 - 그라데이션 효과
            pygame.draw.rect(self.screen, (80, 180, 250), create_btn)
            pygame.draw.rect(self.screen, (60, 140, 200), create_btn, 2)
            btn_text_color = (255, 255, 255)
        else:
            # 비활성화 상태
            pygame.draw.rect(self.screen, (200, 200, 210), create_btn)
            pygame.draw.rect(self.screen, (180, 180, 190), create_btn, 1)
            btn_text_color = (150, 150, 160)
        
        create_text = self.font.render("CREATE ROOM", True, btn_text_color)
        text_rect = create_text.get_rect(center=create_btn.center)
        self.screen.blit(create_text, text_rect)
        
        # 시스템 메시지 표시 (왼쪽 상단)
        if self.system_message and time.time() - self.system_message_time < 3:
            msg_width = 350
            msg_panel = pygame.Rect(20, 80, msg_width, 35)
            # 반투명 빨간 배경
            msg_surface = pygame.Surface((msg_width, 40))
            msg_surface.set_alpha(200)
            msg_surface.fill((220, 50, 50))
            self.screen.blit(msg_surface, msg_panel)
            pygame.draw.rect(self.screen, (180, 30, 30), msg_panel, 2)
            
            msg_text = self.font.render(self.system_message, True, (255, 255, 255))
            msg_rect = msg_text.get_rect(center=msg_panel.center)
            self.screen.blit(msg_text, msg_rect)
        
        # 재연결 버튼 (재연결 가능한 경우만)
        if self.reconnect_available:
            reconnect_panel = pygame.Rect(20, 130, 350, 60)
            pygame.draw.rect(self.screen, (255, 240, 240), reconnect_panel)
            pygame.draw.rect(self.screen, (200, 100, 100), reconnect_panel, 2)
            
            reconnect_title = self.font.render("RECONNECTION AVAILABLE", True, (200, 50, 50))
            self.screen.blit(reconnect_title, (30, 140))
            
            if self.was_playing:
                info_text = self.small_font.render(f"You were disconnected from room {self.last_room_id}", True, (150, 50, 50))
                self.screen.blit(info_text, (30, 160))
            
            reconnect_btn = pygame.Rect(250, 145, 100, 30)
            pygame.draw.rect(self.screen, (200, 100, 100), reconnect_btn)
            pygame.draw.rect(self.screen, GRID_COLOR, reconnect_btn, 2)
            btn_text = self.font.render("RECONNECT", True, (255, 255, 255))
            btn_rect = btn_text.get_rect(center=reconnect_btn.center)
            self.screen.blit(btn_text, btn_rect)

        # 룸 목록 패널 (메인 영역 - 세로 확장)
        panel_y = 200
        panel_height = WINDOW_HEIGHT - panel_y - 20
        rooms_panel = pygame.Rect(20, panel_y, WINDOW_WIDTH - 40, panel_height)
        pygame.draw.rect(self.screen, (255, 255, 255), rooms_panel)
        pygame.draw.rect(self.screen, (200, 200, 210), rooms_panel, 2)
        
        # 룸 목록 헤더
        header_rect = pygame.Rect(20, panel_y, WINDOW_WIDTH - 40, 40)
        pygame.draw.rect(self.screen, (50, 50, 60), header_rect)
        header_text = self.font.render("ACTIVE GAME ROOMS", True, (255, 255, 255))
        header_text_rect = header_text.get_rect(center=(WINDOW_WIDTH // 2, panel_y + 20))
        self.screen.blit(header_text, header_text_rect)
        
        # Auto-refresh 인디케이터
        refresh_text = self.small_font.render("● Auto-refreshing", True, (100, 255, 100))
        self.screen.blit(refresh_text, (WINDOW_WIDTH - 150, panel_y + 12))

        # 룸 목록 표시
        y = panel_y + 55
        if not self.rooms_list:
            no_rooms = self.font.render("No active rooms", True, (150, 150, 160))
            no_rooms_rect = no_rooms.get_rect(center=(WINDOW_WIDTH // 2, panel_y + 150))
            self.screen.blit(no_rooms, no_rooms_rect)
            hint = self.small_font.render("Create a new room to start playing!", True, (150, 150, 160))
            hint_rect = hint.get_rect(center=(WINDOW_WIDTH // 2, panel_y + 180))
            self.screen.blit(hint, hint_rect)
        else:
            for idx, room in enumerate(self.rooms_list[:6]):  # 최대 6개
                # 룸 카드 (전체 너비 사용)
                room_card = pygame.Rect(35, y, WINDOW_WIDTH - 70, 60)
                
                # 마우스 호버 효과 시뮬레이션 (선택된 경우)
                if self.selected_room == room['room_id']:
                    pygame.draw.rect(self.screen, (240, 245, 255), room_card)
                    pygame.draw.rect(self.screen, (100, 140, 220), room_card, 2)
                else:
                    pygame.draw.rect(self.screen, (250, 250, 252), room_card)
                    pygame.draw.rect(self.screen, (220, 220, 230), room_card, 1)
                
                # 룸 ID (왼쪽)
                room_id_font = pygame.font.Font(None, 28)
                room_name = room_id_font.render(room['room_id'].upper(), True, (50, 50, 60))
                self.screen.blit(room_name, (70, y + 12))
                
                # 플레이어 정보 (중앙)
                player_info = f"{room['player_count']}/2 Players"
                if room['players']:
                    player_names = ", ".join(room['players'][:2])
                    player_text = f"{player_info} - {player_names}"
                else:
                    player_text = player_info
                player_surface = self.font.render(player_text, True, (80, 80, 90))
                self.screen.blit(player_surface, (250, y + 12))
                
                # 상태 뱃지
                status_text = room['status'].upper()
                if room['status'] == 'waiting':
                    status_color = (50, 200, 50)
                    status_bg = (230, 255, 230)
                elif room['status'] == 'playing':
                    status_color = (200, 100, 50)
                    status_bg = (255, 240, 230)
                else:
                    status_color = (150, 150, 150)
                    status_bg = (240, 240, 240)
                    
                status_rect = pygame.Rect(250, y + 35, 80, 22)
                pygame.draw.rect(self.screen, status_bg, status_rect)
                pygame.draw.rect(self.screen, status_color, status_rect, 1)
                status_surface = self.small_font.render(status_text, True, status_color)
                status_rect = status_surface.get_rect(center=(290, y + 46))
                self.screen.blit(status_surface, status_rect)
                
                # JOIN & WATCH 버튼 (가로 배치, 왼쪽으로 이동)
                button_x_base = WINDOW_WIDTH - 350
                
                if room['player_count'] < 2:
                    # JOIN 버튼 (활성화)
                    join_btn = pygame.Rect(button_x_base, y + 14, 70, 32)
                    pygame.draw.rect(self.screen, (80, 180, 250), join_btn)
                    pygame.draw.rect(self.screen, (60, 140, 200), join_btn, 2)
                    join_text = self.font.render("JOIN", True, (255, 255, 255))
                    join_rect = join_text.get_rect(center=join_btn.center)
                    self.screen.blit(join_text, join_rect)
                else:
                    # FULL 표시
                    full_btn = pygame.Rect(button_x_base, y + 14, 70, 32)
                    pygame.draw.rect(self.screen, (220, 220, 230), full_btn)
                    pygame.draw.rect(self.screen, (200, 200, 210), full_btn, 1)
                    full_text = self.font.render("FULL", True, (150, 150, 160))
                    full_rect = full_text.get_rect(center=full_btn.center)
                    self.screen.blit(full_text, full_rect)
                
                # WATCH 버튼 (항상 활성화)
                watch_btn = pygame.Rect(button_x_base + 80, y + 14, 70, 32)
                pygame.draw.rect(self.screen, (250, 200, 100), watch_btn)
                pygame.draw.rect(self.screen, (200, 160, 80), watch_btn, 2)
                watch_text = self.font.render("WATCH", True, (255, 255, 255))
                watch_rect = watch_text.get_rect(center=watch_btn.center)
                self.screen.blit(watch_text, watch_rect)
                
                y += 65

    def handle_game_click(self, pos):
        """게임 화면에서의 클릭 처리 (보드 + 액션 버튼들)"""
        base_y = BOARD_OFFSET + BOARD_PIXEL_SIZE + 30
        
        # 관전자용 Leave 버튼 클릭 처리
        if self.my_role == "spectator":
            leave_y = base_y + 30  # draw_spectator_leave_button과 일치
            button_width = 100
            button_height = 40
            leave_x = 20
            if leave_x <= pos[0] <= leave_x + button_width and leave_y <= pos[1] <= leave_y + button_height:
                self.send_leave()
                return
        
        # 레디 버튼 클릭 확인 (waiting 상태)
        elif self.my_role == "player" and self.game_status == "waiting":
            # 레디 버튼 영역 - draw_ready_section이 y_offset + 30에 그려짐
            ready_y = base_y + 30
            if 20 <= pos[0] <= 120 and ready_y <= pos[1] <= ready_y + 40:
                print(f"[DEBUG] Ready button clicked at ({pos[0]}, {pos[1]})")
                self.send_ready()
                return
            
            # Leave 버튼 영역 (Ready 버튼과 같은 높이)
            leave_y = base_y + 30
            button_width = 100
            button_height = 40
            leave_x = 130  # Ready 버튼 옆
            if leave_x <= pos[0] <= leave_x + button_width and leave_y <= pos[1] <= leave_y + button_height:
                print(f"[DEBUG] Leave button clicked at ({pos[0]}, {pos[1]})")
                self.send_leave()
                return
        
        # 게임 중 액션 버튼들 (playing 상태)
        elif self.my_role == "player" and self.game_status == "playing":
            # 타이머와 Surrender 모두 base_y + 25에 위치
            action_y = base_y + 25
            button_width = 100
            button_height = 35
            surrender_x = 250  # 타이머 오른쪽
            # 항복 버튼 클릭 영역
            if surrender_x <= pos[0] <= surrender_x + button_width and action_y <= pos[1] <= action_y + button_height:
                print(f"[DEBUG] Surrender clicked at ({pos[0]}, {pos[1]})")
                self.send_surrender()
                return
        
        # 게임 종료 후 액션 버튼들 (finished 상태)
        elif self.my_role == "player" and self.game_status == "finished":
            action_y = base_y + 40  # draw_post_game_actions가 y_offset + 40에 그려짐
            
            # 상대가 리매치 요청했고 내가 아직 요청하지 않았을 때
            if self.opponent_rematch_requested and not self.rematch_requested:
                print(f"[DEBUG] Rematch request received, checking click at pos={pos}")
                # 타임아웃 확인
                if hasattr(self, 'rematch_timeout') and time.time() < self.rematch_timeout:
                    print(f"[DEBUG] Within timeout, checking button areas. action_y={action_y}")
                    # 수락 버튼 (20, y_offset, 100, 30)
                    if 20 <= pos[0] <= 120 and action_y <= pos[1] <= action_y + 30:
                        print("[DEBUG] Accept button clicked!")
                        self.send_rematch_response(True)  # 수락
                        return
                    # 거절 버튼 (130, y_offset, 100, 30)
                    elif 130 <= pos[0] <= 230 and action_y <= pos[1] <= action_y + 30:
                        print("[DEBUG] Decline button clicked!")
                        self.send_rematch_response(False)  # 거절
                        return
                else:
                    print(f"[DEBUG] Timeout expired or not set")
            else:
                # 리매치 버튼 (20, y_offset, 100, 30)
                if 20 <= pos[0] <= 120 and action_y <= pos[1] <= action_y + 30:
                    if not self.rematch_requested:
                        self.send_rematch()
                        self.rematch_requested = True
                    return
            
            # 나가기 버튼 (130, y_offset, 100, 30)
            if 130 <= pos[0] <= 230 and action_y <= pos[1] <= action_y + 30:
                self.send_leave()
                return
        
        # 보드 클릭 처리
        self.handle_board_click(pos)

    def handle_board_click(self, pos):
        """보드 클릭 처리"""
        if self.my_role != "player" or self.game_status != "playing":
            return

        if self.my_color != self.current_turn:
            return

        # 클릭 위치를 보드 좌표로 변환
        x = pos[0] - BOARD_OFFSET
        y = pos[1] - BOARD_OFFSET

        # 가장 가까운 교차점 찾기
        col = round(x / CELL_SIZE)
        row = round(y / CELL_SIZE)

        # 범위 체크
        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            # 빈칸 체크
            if self.board[row][col] is None:
                # 서버로 전송
                msg = Protocol.create_message(
                    MessageType.PLACE_STONE,
                    {"x": row, "y": col}
                )
                self.socket.send(msg)

    def handle_lobby_click(self, pos):
        """로비 클릭 처리"""
        panel_x = 30
        panel_y = 100
        
        # Create Room 버튼 (panel_x + 210, panel_y + 40, 170, 30)
        if panel_x + 210 <= pos[0] <= panel_x + 380 and panel_y + 40 <= pos[1] <= panel_y + 70:
            if self.name_input:
                self.my_name = self.name_input
                msg = Protocol.create_message(
                    MessageType.CREATE_ROOM,
                    {"player_name": self.name_input}
                )
                print(f"[DEBUG] Sending CREATE_ROOM request for {self.name_input}")
                try:
                    self.socket.send(msg)
                    print("[DEBUG] CREATE_ROOM request sent")
                except Exception as e:
                    print(f"[ERROR] Failed to send CREATE_ROOM: {e}")
                    self.set_system_message("Failed to create room!")
            else:
                self.set_system_message("Please enter your name first!")

        # Reconnect 버튼 (250, 145, 100, 30) - 재연결 가능한 경우만
        elif 250 <= pos[0] <= 350 and 145 <= pos[1] <= 175 and self.reconnect_available:
            if self.my_name or self.name_input:
                if self.name_input:
                    self.my_name = self.name_input
                self.send_reconnect()
                print(f"[*] Attempting manual reconnect for {self.my_name}")

        # 룸 카드 및 버튼 클릭 처리
        else:
            panel_y = 200
            y = panel_y + 55
            for room in self.rooms_list[:6]:
                # 룸 카드 클릭 (선택) - 35, y, WINDOW_WIDTH - 70, 60
                if 35 <= pos[0] <= WINDOW_WIDTH - 35 and y <= pos[1] <= y + 60:
                    self.selected_room = room['room_id']
                    print(f"[DEBUG] Selected room: {self.selected_room}")
                    
                # Join & Watch 버튼 위치 계산
                button_x_base = WINDOW_WIDTH - 350
                
                # Join 버튼
                if room['player_count'] < 2:
                    join_btn_x = button_x_base
                    if join_btn_x <= pos[0] <= join_btn_x + 70 and y + 14 <= pos[1] <= y + 46:
                        if self.name_input:
                            self.my_name = self.name_input
                            msg = Protocol.create_message(
                                MessageType.JOIN_ROOM,
                                {"room_id": room['room_id'], "player_name": self.name_input}
                            )
                            self.socket.send(msg)
                            print(f"[*] Joining room {room['room_id']} as {self.name_input}")
                        else:
                            self.set_system_message("Please enter your name first!")
                        return

                # Watch 버튼
                watch_btn_x = button_x_base + 80
                if watch_btn_x <= pos[0] <= watch_btn_x + 70 and y + 14 <= pos[1] <= y + 46:
                    if self.name_input:
                        self.my_name = self.name_input
                        msg = Protocol.create_message(
                            MessageType.SPECTATE_ROOM,
                            {"room_id": room['room_id'], "spectator_name": self.name_input}
                        )
                        self.socket.send(msg)
                    else:
                        self.set_system_message("Please enter your name first!")
                    return

                y += 65

    def send_ready(self):
        """레디 상태 전송"""
        if self.current_room and self.my_role == "player":
            msg = Protocol.create_message(MessageType.READY)
            self.socket.send(msg)

    def send_chat(self):
        """플레이어 채팅 전송"""
        if self.chat_input and self.current_room:
            msg = Protocol.create_message(
                MessageType.CHAT_MESSAGE,
                {"room_id": self.current_room, "message": self.chat_input}
            )
            self.socket.send(msg)
            self.chat_input = ""

    def send_spectator_chat(self):
        """관전자 채팅 전송"""
        if self.spectator_chat_input and self.current_room and self.my_role == "spectator":
            msg = Protocol.create_message(
                MessageType.SPECTATOR_CHAT,
                {"room_id": self.current_room, "message": self.spectator_chat_input}
            )
            self.socket.send(msg)
            self.spectator_chat_input = ""

    def run(self):
        """메인 루프"""
        if not self.connect():
            return

        # 메시지 수신 스레드 시작
        receive_thread = threading.Thread(target=self.receive_messages)
        receive_thread.daemon = True
        receive_thread.start()

        # 메인 게임 루프
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.in_lobby:
                        self.handle_lobby_click(event.pos)
                    else:
                        self.handle_game_click(event.pos)

                elif event.type == pygame.KEYDOWN:
                    if self.in_lobby:
                        # 이름 입력
                        if event.key == pygame.K_BACKSPACE:
                            self.name_input = self.name_input[:-1]
                        elif event.key == pygame.K_RETURN:
                            pass
                        elif len(self.name_input) < 20:
                            self.name_input += event.unicode
                    else:
                        # 채팅 입력
                        if self.my_role == "spectator":
                            # 관전자는 Shift+Enter로 일반 채팅, Enter로 관전자 채팅
                            if event.key == pygame.K_BACKSPACE:
                                self.spectator_chat_input = self.spectator_chat_input[:-1]
                            elif event.key == pygame.K_RETURN:
                                if pygame.key.get_pressed()[pygame.K_LSHIFT] or pygame.key.get_pressed()[pygame.K_RSHIFT]:
                                    self.send_chat()  # Shift+Enter: 플레이어 채팅 (볼 수만 있음)
                                else:
                                    self.send_spectator_chat()  # Enter: 관전자 채팅
                            elif len(self.spectator_chat_input) < 50:
                                self.spectator_chat_input += event.unicode
                        else:
                            # 플레이어는 기존 방식
                            if event.key == pygame.K_BACKSPACE:
                                self.chat_input = self.chat_input[:-1]
                            elif event.key == pygame.K_RETURN:
                                self.send_chat()
                            elif len(self.chat_input) < 50:
                                self.chat_input += event.unicode

            # 로비에서 1초마다 룸 리스트 자동 갱신
            if self.in_lobby:
                current_time = time.time()
                if current_time - self.last_room_update > 1.0:  # 1초마다
                    msg = Protocol.create_message(MessageType.LIST_ROOMS)
                    try:
                        self.socket.send(msg)
                        self.last_room_update = current_time
                    except:
                        pass  # 연결 끊김 무시
            
            # 화면 그리기
            if self.in_lobby:
                self.draw_lobby()
            else:
                self.draw_board()
                self.draw_info()
                self.draw_chat()
                # 상대방 재연결 타이머 (오른쪽 하단에 표시)
                self.draw_reconnection_timer(WINDOW_WIDTH - 20, WINDOW_HEIGHT - 20)

            pygame.display.flip()
            self.clock.tick(60)  # 60 FPS

        # 종료
        pygame.quit()
        if self.socket:
            self.socket.close()

    def draw_game_actions(self, y_offset):
        """게임 중 액션 버튼들 (항복만)"""
        # 항복 버튼 - 타이머 오른쪽에 배치
        button_width = 100
        button_height = 35
        # 타이머가 왼쪽(x=20)에 그려지므로, 버튼은 오른쪽에
        surrender_x = 250  # 타이머 오른쪽
        surrender_y = y_offset
        
        surrender_btn = pygame.Rect(surrender_x, surrender_y, button_width, button_height)
        
        # 빨간색 배경만 (테두리 제거)
        pygame.draw.rect(self.screen, (200, 50, 50), surrender_btn)
        
        # 글씨 표시
        surrender_text = self.font.render("Surrender", True, (255, 255, 255))
        text_rect = surrender_text.get_rect(center=surrender_btn.center)
        self.screen.blit(surrender_text, text_rect)

    def draw_leave_button_only(self, y_offset):
        """Leave 버튼만 표시 (대기 중일 때)"""
        # 나가기 버튼 - Ready 버튼 옆에 배치
        button_width = 100
        button_height = 40
        leave_x = 130  # Ready 버튼(x=20) 옆에 배치
        
        leave_btn = pygame.Rect(leave_x, y_offset, button_width, button_height)
        pygame.draw.rect(self.screen, (180, 180, 180), leave_btn)
        pygame.draw.rect(self.screen, GRID_COLOR, leave_btn, 2)
        leave_text = self.font.render("Leave", True, TEXT_COLOR)
        text_rect = leave_text.get_rect(center=leave_btn.center)
        self.screen.blit(leave_text, text_rect)
    
    def draw_spectator_leave_button(self, y_offset):
        """관전자용 Leave 버튼 표시"""
        button_width = 100
        button_height = 40
        leave_x = 20  # 왼쪽에 배치
        
        leave_btn = pygame.Rect(leave_x, y_offset, button_width, button_height)
        pygame.draw.rect(self.screen, (180, 180, 180), leave_btn)
        pygame.draw.rect(self.screen, GRID_COLOR, leave_btn, 2)
        leave_text = self.font.render("Leave", True, TEXT_COLOR)
        text_rect = leave_text.get_rect(center=leave_btn.center)
        self.screen.blit(leave_text, text_rect)
    
    def draw_post_game_actions(self, y_offset):
        """게임 종료 후 액션 버튼들 (리게임, 나가기)"""
        # 상대가 리매치를 요청했을 때
        if self.opponent_rematch_requested and not self.rematch_requested:
            # 수락 버튼
            accept_btn = pygame.Rect(20, y_offset, 100, 30)
            pygame.draw.rect(self.screen, (100, 220, 100), accept_btn)
            pygame.draw.rect(self.screen, GRID_COLOR, accept_btn, 2)
            accept_text = self.font.render("Accept", True, TEXT_COLOR)
            text_rect = accept_text.get_rect(center=accept_btn.center)
            self.screen.blit(accept_text, text_rect)
            
            # 거절 버튼
            decline_btn = pygame.Rect(130, y_offset, 100, 30)
            pygame.draw.rect(self.screen, (220, 100, 100), decline_btn)
            pygame.draw.rect(self.screen, GRID_COLOR, decline_btn, 2)
            decline_text = self.font.render("Decline", True, TEXT_COLOR)
            text_rect = decline_text.get_rect(center=decline_btn.center)
            self.screen.blit(decline_text, text_rect)
            
            # 상대 요청 표시
            request_text = self.small_font.render(f"{self.rematch_requester} wants a rematch!", True, (255, 100, 0))
            self.screen.blit(request_text, (20, y_offset - 25))
        else:
            # 리매치 버튼 (내가 요청했으면 대기 표시)
            rematch_btn = pygame.Rect(20, y_offset, 100, 30)
            if self.rematch_requested:
                # 대기 중 표시
                pygame.draw.rect(self.screen, (200, 200, 100), rematch_btn)
                pygame.draw.rect(self.screen, GRID_COLOR, rematch_btn, 2)
                rematch_text = self.font.render("Waiting...", True, TEXT_COLOR)
            else:
                pygame.draw.rect(self.screen, (100, 220, 100), rematch_btn)
                pygame.draw.rect(self.screen, GRID_COLOR, rematch_btn, 2)
                rematch_text = self.font.render("Rematch", True, TEXT_COLOR)
            text_rect = rematch_text.get_rect(center=rematch_btn.center)
            self.screen.blit(rematch_text, text_rect)
            
        # 나가기 버튼 (항상 표시, Rematch 버튼과 같은 줄)
        leave_btn = pygame.Rect(130, y_offset, 100, 30)
        pygame.draw.rect(self.screen, (180, 180, 180), leave_btn)
        pygame.draw.rect(self.screen, GRID_COLOR, leave_btn, 2)
        leave_text = self.font.render("Leave", True, TEXT_COLOR)
        text_rect = leave_text.get_rect(center=leave_btn.center)
        self.screen.blit(leave_text, text_rect)
    
    def send_surrender(self):
        """항복 메시지 전송"""
        try:
            msg = Protocol.create_message(MessageType.SURRENDER, {})
            self.socket.send(msg)
            print("[*] Surrender request sent")
        except Exception as e:
            print(f"[!] Error sending surrender: {e}")
    
    def send_rematch(self):
        """리게임 요청 메시지 전송"""
        try:
            msg = Protocol.create_message(MessageType.REMATCH, {})
            self.socket.send(msg)
            self.rematch_requested = True
            print("[*] Rematch request sent")
            self.add_chat_message("SYSTEM", "Rematch request sent", "system")
        except Exception as e:
            print(f"[!] Error sending rematch: {e}")
    
    def send_rematch_response(self, accepted):
        """리게임 요청에 대한 응답"""
        print(f"[DEBUG] send_rematch_response called with accepted={accepted}")
        try:
            msg = Protocol.create_message(
                MessageType.REMATCH_RESPONSE,
                {"accepted": accepted}
            )
            self.socket.send(msg)
            print(f"[DEBUG] Rematch response sent: {accepted}")
            self.opponent_rematch_requested = False
            self.rematch_requester = None
            
            if accepted:
                self.add_chat_message("SYSTEM", "Rematch accepted!", "system")
            else:
                self.add_chat_message("SYSTEM", "Rematch declined", "system")
        except Exception as e:
            print(f"[!] Error sending rematch response: {e}")
    
    def send_leave(self):
        """방 나가기 메시지 전송"""
        try:
            msg = Protocol.create_message(MessageType.LEAVE_ROOM, {})
            self.socket.send(msg)
            print("[*] Leave room request sent")
            # 서버 응답을 기다림 - receive_messages에서 처리
        except Exception as e:
            print(f"[!] Error sending leave: {e}")
    
    def send_reconnect(self):
        """재연결 메시지 전송"""
        try:
            msg = Protocol.create_message(MessageType.RECONNECT, {"player_name": self.my_name})
            self.socket.send(msg)
            print(f"[*] Reconnect request sent for {self.my_name}")
        except Exception as e:
            print(f"[!] Error sending reconnect: {e}")

if __name__ == "__main__":
    client = GomokuGUIClient(host='localhost', port=10000)
    client.run()
