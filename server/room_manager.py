#!/usr/bin/env python3
"""
게임 룸 관리자 (Room Manager)
- 여러 게임 룸을 생성하고 관리합니다
- 각 룸은 2명의 플레이어와 여러 관전자를 가질 수 있습니다
"""

import threading
import time
from server.game_logic import GomokuBoard

class GameRoom:
    """개별 게임 룸 클래스"""

    def __init__(self, room_id):
        """
        게임 룸 초기화

        Args:
            room_id: 룸 고유 ID
        """
        self.room_id = room_id
        self.players = []  # 최대 2명: [{socket, name, color}, ...]
        self.spectators = []  # 무제한: [{socket, name}, ...]
        self.status = "waiting"  # "waiting", "playing", "finished"
        self.board = GomokuBoard()  # 오목 보드
        self.current_turn = "black"  # 현재 턴 ("black" 또는 "white")
        self.lock = threading.RLock()  # RLock으로 변경 - 재진입 가능한 락
        
        # 타이머 관련
        self.turn_start_time = None
        self.turn_time_limit = 60  # 60초 제한
        self.timer_thread = None
        self.timer_stop_event = threading.Event()
        
        # 재연결 관련
        self.disconnected_players = {}  # {player_name: {disconnect_time, player_data, color, reconnect_count}}
        self.reconnect_timeout = 180  # 3분 (180초)
        self.max_reconnect_attempts = 2  # 최대 재연결 시도 횟수
        self.is_paused = False
        self.reconnect_attempts = {}  # {player_name: attempt_count}
        
        # 리게임 관련
        self.rematch_requests = {}  # {player_name: True/False}

    def add_player(self, client_socket, player_name):
        """
        플레이어를 룸에 추가합니다

        Args:
            client_socket: 플레이어 소켓
            player_name: 플레이어 이름

        Returns:
            플레이어 색상 ("black" 또는 "white")

        Raises:
            Exception: 룸이 가득 찬 경우
        """
        with self.lock:
            if len(self.players) >= 2:
                raise Exception("Room is full")

            # 첫 번째 플레이어는 흑돌, 두 번째는 백돌
            color = "black" if len(self.players) == 0 else "white"

            player = {
                "socket": client_socket,
                "name": player_name,
                "color": color,
                "ready": False
            }
            self.players.append(player)

            # 2명이 되면 게임 시작 준비 (서버에서 GAME_START 후 playing으로 변경)

            return color

    def add_spectator(self, client_socket, spectator_name):
        """
        관전자를 룸에 추가합니다

        Args:
            client_socket: 관전자 소켓
            spectator_name: 관전자 이름
        """
        with self.lock:
            spectator = {
                "socket": client_socket,
                "name": spectator_name
            }
            self.spectators.append(spectator)

    def remove_player(self, client_socket, is_disconnect=False):
        """
        플레이어를 룸에서 제거합니다

        Args:
            client_socket: 제거할 플레이어 소켓
            is_disconnect: 연결 끊김인지 여부

        Returns:
            제거된 플레이어 이름 또는 None
        """
        with self.lock:
            for player in self.players:
                if player["socket"] == client_socket:
                    player_name = player["name"]
                    player_color = player["color"]
                    
                    if is_disconnect and self.status == "playing":
                        # 게임 중 연결 끊김: 재연결 대기 상태로 설정
                        current_attempts = self.reconnect_attempts.get(player_name, 0)
                        if current_attempts < self.max_reconnect_attempts:
                            self.disconnected_players[player_name] = {
                                "disconnect_time": time.time(),
                                "player_data": player.copy(),
                                "color": player_color,
                                "reconnect_count": current_attempts
                            }
                        # 소켓만 None으로 설정 (플레이어 정보는 유지)
                        player["socket"] = None
                        self.is_paused = True
                        self.stop_timer()  # 타이머 일시정지
                        return player_name
                    else:
                        # 정상 나가기: 완전 제거
                        self.players.remove(player)
                        # 게임 상태 리셋
                        if len(self.players) == 1:
                            # 한 명만 남았을 때 게임 초기화
                            self.status = "waiting"
                            self.board.reset()
                            self.current_turn = "black"
                            self.stop_timer()
                            # 남은 플레이어의 레디 상태 리셋
                            for p in self.players:
                                p["ready"] = False
                            # 리매치 상태 초기화
                            self.rematch_requests.clear()
                        elif len(self.players) == 0:
                            self.status = "waiting"
                        return player_name
            return None

    def remove_spectator(self, client_socket):
        """
        관전자를 룸에서 제거합니다

        Args:
            client_socket: 제거할 관전자 소켓

        Returns:
            제거된 관전자 이름 또는 None
        """
        with self.lock:
            for spectator in self.spectators:
                if spectator["socket"] == client_socket:
                    self.spectators.remove(spectator)
                    return spectator["name"]
            return None

    def get_player_by_socket(self, client_socket):
        """소켓으로 플레이어 찾기"""
        with self.lock:
            for player in self.players:
                if player["socket"] == client_socket:
                    return player
            return None

    def get_spectator_by_socket(self, client_socket):
        """소켓으로 관전자 찾기"""
        with self.lock:
            for spectator in self.spectators:
                if spectator["socket"] == client_socket:
                    return spectator
            return None

    def is_full(self):
        """룸이 가득 찼는지 확인 (플레이어 2명)"""
        with self.lock:
            return len(self.players) >= 2

    def is_empty(self):
        """룸이 비어있는지 확인 (플레이어와 관전자 모두 없음)"""
        with self.lock:
            return len(self.players) == 0 and len(self.spectators) == 0

    def broadcast_to_all(self, message):
        """
        룸의 모든 사람(플레이어 + 관전자)에게 메시지 전송
        락 분리: 소켓 리스트 복사 후 락 밖에서 전송

        Args:
            message: 전송할 메시지 (바이트)
        """
        # 1. 락을 잡고 소켓 리스트만 빠르게 복사
        with self.lock:
            sockets_to_send = []
            
            # 플레이어 소켓 수집
            for player in self.players:
                if player["socket"] is not None:
                    sockets_to_send.append((player["socket"], player["name"], "player"))
            
            # 관전자 소켓 수집
            for spectator in self.spectators:
                if spectator["socket"] is not None:
                    sockets_to_send.append((spectator["socket"], spectator["name"], "spectator"))
        
        # 2. 락 밖에서 실제 전송 (블로킹 되어도 다른 스레드 영향 없음)
        for socket, name, role in sockets_to_send:
            try:
                socket.send(message)
            except Exception as e:
                print(f"[!] Failed to send message to {name} ({role}): {e}")

    def broadcast_to_players(self, message):
        """
        플레이어에게만 메시지 전송
        락 분리: 소켓 리스트 복사 후 락 밖에서 전송

        Args:
            message: 전송할 메시지 (바이트)
        """
        # 1. 락을 잡고 플레이어 소켓만 빠르게 복사
        with self.lock:
            player_sockets = [(p["socket"], p["name"]) for p in self.players if p["socket"] is not None]
        
        # 2. 락 밖에서 실제 전송
        for socket, name in player_sockets:
            try:
                socket.send(message)
            except Exception as e:
                print(f"[!] Failed to send message to player {name}: {e}")

    def place_stone(self, x, y, color):
        """
        돌을 놓습니다

        Args:
            x, y: 보드 좌표
            color: 돌 색상

        Returns:
            bool: 성공 여부
        """
        with self.lock:
            return self.board.place_stone(x, y, color)

    def check_winner(self, x, y):
        """
        승리 확인

        Args:
            x, y: 최근에 놓은 돌의 위치

        Returns:
            str: 승리한 색상 또는 None
        """
        with self.lock:
            return self.board.check_winner(x, y)

    def switch_turn(self):
        """턴을 바꿉니다"""
        with self.lock:
            self.current_turn = "white" if self.current_turn == "black" else "black"

    def get_board_state(self):
        """현재 보드 상태를 반환"""
        with self.lock:
            return self.board.get_board_state()

    def reset_game(self):
        """게임을 초기화합니다"""
        with self.lock:
            self.board.reset()
            self.current_turn = "black"
            self.status = "waiting" if len(self.players) < 2 else "playing"

    def set_player_ready(self, client_socket, ready_state=True):
        """
        플레이어의 레디 상태를 설정합니다

        Args:
            client_socket: 플레이어 소켓
            ready_state: 레디 상태 (True/False)

        Returns:
            bool: 성공 여부
        """
        with self.lock:
            for player in self.players:
                if player["socket"] == client_socket:
                    player["ready"] = ready_state
                    return True
            return False

    def are_all_players_ready(self):
        """
        모든 플레이어가 레디 상태인지 확인

        Returns:
            bool: 모든 플레이어가 레디면 True
        """
        with self.lock:
            if len(self.players) < 2:
                return False
            return all(player["ready"] for player in self.players)

    def get_ready_status(self):
        """
        플레이어들의 레디 상태를 반환

        Returns:
            dict: 플레이어별 레디 상태
        """
        with self.lock:
            return {
                player["name"]: player["ready"] 
                for player in self.players
            }

    def get_info(self):
        """
        룸 정보를 딕셔너리로 반환

        Returns:
            룸 정보 딕셔너리
        """
        with self.lock:
            # 락 안에서 직접 ready_status 계산 (데드락 방지)
            ready_status = {
                player["name"]: player["ready"] 
                for player in self.players
            }
            
            # 실제 연결된 플레이어만 카운트 (socket이 None이 아닌 플레이어)
            active_players = [p for p in self.players if p["socket"] is not None]
            active_spectators = [s for s in self.spectators if s["socket"] is not None]
            
            return {
                "room_id": self.room_id,
                "status": self.status,
                "player_count": len(active_players),  # 실제 연결된 플레이어 수
                "spectator_count": len(active_spectators),  # 실제 연결된 관전자 수
                "players": [p["name"] for p in active_players],  # 실제 연결된 플레이어 이름
                "current_turn": self.current_turn,
                "ready_status": ready_status,
                "turn_start_time": self.turn_start_time,
                "time_limit": self.turn_time_limit
            }

    def start_timer(self, callback_func):
        """턴 타이머 시작"""
        with self.lock:
            if self.is_paused:  # 게임이 일시정지된 경우 타이머 시작하지 않음
                print(f"[DEBUG] Timer start skipped - game is paused")
                return
                
            print(f"[DEBUG] Starting timer for room {self.room_id}, turn: {self.current_turn}")
            
            # 기존 타이머 정리
            if self.timer_thread and self.timer_thread.is_alive():
                print(f"[DEBUG] Stopping existing timer thread")
                self.timer_stop_event.set()
                # 스레드가 종료될 때까지 짧게 기다림
                self.timer_thread.join(timeout=1.0)
                if self.timer_thread.is_alive():
                    print(f"[DEBUG] Warning: timer thread did not stop cleanly")
            
            # 새 타이머 설정
            self.turn_start_time = time.time()
            self.timer_stop_event = threading.Event()  # 새 이벤트 객체 생성
            self.timer_stop_event.clear()
            self._timer_callback = callback_func  # 콜백 저장 (재연결 시 사용)
            
            # 새 타이머 스레드 시작
            self.timer_thread = threading.Thread(
                target=self._timer_worker, 
                args=(callback_func,),
                name=f"Timer-{self.room_id}-{self.current_turn}"
            )
            self.timer_thread.daemon = True
            self.timer_thread.start()
            print(f"[DEBUG] Timer thread started: {self.timer_thread.name}, is_alive: {self.timer_thread.is_alive()}")

    def stop_timer(self):
        """타이머 정지"""
        print(f"[DEBUG] Stopping timer for room {self.room_id}")
        with self.lock:
            if self.timer_thread and self.timer_thread.is_alive():
                self.timer_stop_event.set()
                # 타이머 스레드가 종료될 때까지 짧게 기다림
                self.timer_thread.join(timeout=0.5)
            self.turn_start_time = None

    def get_remaining_time(self):
        """남은 시간 계산 (초)"""
        with self.lock:
            if self.turn_start_time is None:
                return 0
            elapsed = time.time() - self.turn_start_time
            remaining = max(0, self.turn_time_limit - elapsed)
            return int(remaining)

    def _timer_worker(self, callback_func):
        """타이머 워커 (별도 스레드)"""
        print(f"[DEBUG] Timer worker started for room {self.room_id}")
        
        # 첫 번째 업데이트를 즉시 보냄 (60초)
        callback_func(self.room_id, "update", self.turn_time_limit)
        print(f"[DEBUG] Timer first update: {self.turn_time_limit} seconds")
        
        while not self.timer_stop_event.is_set():
            try:
                # 1초 대기
                for _ in range(10):  # 0.1초씩 10번 = 1초
                    if self.timer_stop_event.is_set():
                        break
                    time.sleep(0.1)
                
                if self.timer_stop_event.is_set():
                    break
                    
                with self.lock:
                    if self.turn_start_time is None:
                        print(f"[DEBUG] Timer worker stopping - turn_start_time is None")
                        break
                    elapsed = time.time() - self.turn_start_time
                    remaining = self.turn_time_limit - elapsed
                
                if remaining <= 0:
                    # 시간 초과
                    print(f"[DEBUG] Timer timeout for room {self.room_id}")
                    # timeout 처리를 별도 스레드로 실행하여 데드락 방지
                    import threading
                    timeout_thread = threading.Thread(
                        target=callback_func,
                        args=(self.room_id, "timeout"),
                        name=f"Timeout-{self.room_id}"
                    )
                    timeout_thread.daemon = True
                    timeout_thread.start()
                    break
                else:
                    # 매 1초마다 업데이트
                    callback_func(self.room_id, "update", int(remaining))
                    print(f"[DEBUG] Timer update: {int(remaining)} seconds remaining")
            except Exception as e:
                print(f"[DEBUG] Timer worker error: {e}")
                break
        print(f"[DEBUG] Timer worker ended for room {self.room_id}")

    def can_reconnect(self, player_name):
        """플레이어가 재연결 가능한지 확인"""
        with self.lock:
            if player_name not in self.disconnected_players:
                return False
            
            # 재연결 시도 횟수 체크
            current_attempts = self.reconnect_attempts.get(player_name, 0)
            if current_attempts >= self.max_reconnect_attempts:
                return False
            
            disconnect_time = self.disconnected_players[player_name]["disconnect_time"]
            elapsed = time.time() - disconnect_time
            return elapsed <= self.reconnect_timeout

    def reconnect_player(self, player_name, new_socket):
        """플레이어 재연결 처리"""
        with self.lock:
            if player_name not in self.disconnected_players:
                return False
            
            # 재연결 타임아웃 체크
            if not self.can_reconnect(player_name):
                # 타임아웃 또는 시도 횟수 초과
                return False
            
            # 재연결 시도 횟수 증가
            current_attempts = self.reconnect_attempts.get(player_name, 0)
            self.reconnect_attempts[player_name] = current_attempts + 1
            
            # 플레이어 소켓 복구
            for player in self.players:
                if player["name"] == player_name:
                    player["socket"] = new_socket
                    break
            
            # 재연결 대기 목록에서 제거
            del self.disconnected_players[player_name]
            
            # 게임 재개
            if not self.disconnected_players:  # 모든 플레이어가 재연결됨
                self.is_paused = False
                if self.status == "playing":
                    # 타이머 재시작 (콜백이 있을 때만)
                    if hasattr(self, '_timer_callback') and self._timer_callback:
                        try:
                            self.start_timer(self._timer_callback)
                        except Exception as e:
                            print(f"Error restarting timer: {e}")
                            # 타이머 재시작 실패해도 게임은 계속 진행
            
            return True

    def check_reconnect_timeout(self):
        """재연결 타임아웃 체크 (3분 후 자동 몰수패 처리)"""
        with self.lock:
            current_time = time.time()
            timed_out_players = []
            
            for player_name, data in self.disconnected_players.items():
                if current_time - data["disconnect_time"] > self.reconnect_timeout:
                    timed_out_players.append((player_name, data["color"]))
            
            return timed_out_players

    def forfeit_player(self, player_name, player_color):
        """플레이어 몰수패 처리"""
        with self.lock:
            if player_name in self.disconnected_players:
                del self.disconnected_players[player_name]
            
            # 상대방이 승리자가 됨
            winner_color = "white" if player_color == "black" else "black"
            winner_name = None
            for player in self.players:
                if player["color"] == winner_color:
                    winner_name = player["name"]
                    break
            
            # 게임 종료
            self.stop_timer()
            self.status = "finished"
            self.is_paused = False
            
            return winner_color, winner_name

    def get_disconnected_status(self):
        """연결 끊긴 플레이어 상태 반환"""
        with self.lock:
            return {
                "disconnected_players": list(self.disconnected_players.keys()),
                "is_paused": self.is_paused
            }

    def request_rematch(self, player_name):
        """리게임 요청"""
        with self.lock:
            if self.status != "finished":
                return False
            self.rematch_requests[player_name] = True
            return True

    def is_rematch_agreed(self):
        """모든 플레이어가 리게임에 동의했는지 확인"""
        with self.lock:
            if len(self.players) != 2:
                return False
            for player in self.players:
                if not self.rematch_requests.get(player["name"], False):
                    return False
            return True

    def start_rematch(self):
        """리게임 시작"""
        with self.lock:
            # 게임 상태 초기화
            self.board.reset()
            self.current_turn = "black"
            self.status = "playing"
            self.rematch_requests.clear()
            
            # 플레이어 색상 교체
            for player in self.players:
                if player["color"] == "black":
                    player["color"] = "white"
                elif player["color"] == "white":
                    player["color"] = "black"
                player["ready"] = True  # 자동으로 레디 상태


class RoomManager:
    """모든 게임 룸을 관리하는 클래스"""

    def __init__(self):
        """룸 매니저 초기화"""
        self.rooms = {}  # room_id -> GameRoom
        self.next_room_id = 1
        self.lock = threading.RLock()  # RLock으로 변경 - 재진입 가능한 락

    def create_room(self):
        """
        새 게임 룸을 생성합니다

        Returns:
            생성된 룸 ID
        """
        with self.lock:
            room_id = f"room_{self.next_room_id}"
            self.next_room_id += 1

            new_room = GameRoom(room_id)
            self.rooms[room_id] = new_room

            return room_id

    def get_room(self, room_id):
        """
        룸 ID로 게임 룸을 가져옵니다

        Args:
            room_id: 룸 ID

        Returns:
            GameRoom 객체 또는 None
        """
        with self.lock:
            return self.rooms.get(room_id)

    def remove_room(self, room_id):
        """
        게임 룸을 제거합니다

        Args:
            room_id: 제거할 룸 ID
        """
        with self.lock:
            if room_id in self.rooms:
                del self.rooms[room_id]

    def get_all_rooms_info(self):
        """
        모든 룸의 정보를 리스트로 반환

        Returns:
            룸 정보 딕셔너리 리스트
        """
        with self.lock:
            return [room.get_info() for room in self.rooms.values()]

    def cleanup_empty_rooms(self):
        """
        비어있는 룸들을 정리합니다
        락 분리: 빈 룸 확인과 삭제를 분리
        """
        # 1. 락을 잡고 빈 룸 목록만 빠르게 확인
        empty_rooms = []
        with self.lock:
            for room_id, room in self.rooms.items():
                # 실제로 연결된 플레이어가 있는지 확인 (socket이 None이 아닌 플레이어)
                active_players = [p for p in room.players if p["socket"] is not None]
                active_spectators = [s for s in room.spectators if s["socket"] is not None]
                
                # 활성 플레이어와 관전자가 모두 없으면 빈 방
                if len(active_players) == 0 and len(active_spectators) == 0:
                    empty_rooms.append(room_id)
        
        # 2. 락을 다시 잡고 룸 삭제
        if empty_rooms:
            with self.lock:
                for room_id in empty_rooms:
                    if room_id in self.rooms:  # 다시 확인 (경쟁 조건 방지)
                        del self.rooms[room_id]
                        print(f"[*] Removed empty room: {room_id}")

    def find_room_by_socket(self, client_socket):
        """
        소켓으로 해당 클라이언트가 속한 룸을 찾습니다

        Args:
            client_socket: 클라이언트 소켓

        Returns:
            (GameRoom, role) 튜플 또는 (None, None)
            role은 "player" 또는 "spectator"
        """
        with self.lock:
            for room in self.rooms.values():
                # 플레이어로 있는지 확인
                if room.get_player_by_socket(client_socket):
                    return room, "player"

                # 관전자로 있는지 확인
                if room.get_spectator_by_socket(client_socket):
                    return room, "spectator"

            return None, None
