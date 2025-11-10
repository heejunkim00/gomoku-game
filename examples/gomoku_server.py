#!/usr/bin/env python3
"""
오목 게임 서버 (Gomoku Game Server)
- room_server.py를 기반으로 게임 로직 추가
- 돌 놓기, 턴 관리, 승리 조건 감지
"""

import socket
import threading
import sys
import os
import time

# 상위 디렉토리의 모듈을 import하기 위한 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.protocol import Protocol, MessageType
from server.room_manager import RoomManager

class GomokuServer:
    """오목 게임 서버 클래스"""

    def __init__(self, host='localhost', port=10000):
        """
        서버 초기화

        Args:
            host: 서버 주소
            port: 서버 포트
        """
        self.host = host
        self.port = port
        self.server_socket = None
        self.room_manager = RoomManager()

    def handle_client(self, client_socket, client_address):
        """
        개별 클라이언트 처리

        Args:
            client_socket: 클라이언트 소켓
            client_address: 클라이언트 주소
        """
        print(f"[+] New connection from: {client_address}")
        current_room = None
        role = None

        try:
            while True:
                # 메시지 받기
                raw_data = client_socket.recv(4096)

                if not raw_data:
                    print(f"[-] Connection closed: {client_address}")
                    break

                # JSON 메시지 파싱
                messages = Protocol.parse_messages(raw_data)
                
                for message in messages:
                    msg_type = message["type"]
                    data = message.get("data", {})

                    print(f"[{client_address}] {msg_type}: {data}")

                    # 메시지 타입별 처리
                    if msg_type == MessageType.CREATE_ROOM:
                        self.handle_create_room(client_socket, data)
                        current_room, role = self.room_manager.find_room_by_socket(client_socket)

                    elif msg_type == MessageType.JOIN_ROOM:
                        self.handle_join_room(client_socket, data)
                        current_room, role = self.room_manager.find_room_by_socket(client_socket)

                    elif msg_type == MessageType.SPECTATE_ROOM:
                        self.handle_spectate_room(client_socket, data)
                        current_room, role = self.room_manager.find_room_by_socket(client_socket)

                    elif msg_type == MessageType.LIST_ROOMS:
                        self.handle_list_rooms(client_socket)

                    elif msg_type == MessageType.CHAT_MESSAGE:
                        self.handle_chat_message(client_socket, data, current_room)

                    elif msg_type == MessageType.SPECTATOR_CHAT:
                        self.handle_spectator_chat(client_socket, data, current_room)

                    elif msg_type == MessageType.READY:
                        self.handle_ready(client_socket, data, current_room)

                    elif msg_type == MessageType.RECONNECT:
                        self.handle_reconnect(client_socket, data)
                        current_room, role = self.room_manager.find_room_by_socket(client_socket)

                    elif msg_type == MessageType.PLACE_STONE:
                        self.handle_place_stone(client_socket, data, current_room)

                    elif msg_type == MessageType.LEAVE_ROOM:
                        self.handle_leave_room(client_socket, current_room, role)
                        current_room = None
                        role = None
                    
                    elif msg_type == MessageType.SURRENDER:
                        self.handle_surrender(client_socket, current_room)
                    
                    elif msg_type == MessageType.REMATCH:
                        self.handle_rematch(client_socket, current_room)
                    
                    elif msg_type == MessageType.REMATCH_RESPONSE:
                        self.handle_rematch_response(client_socket, current_room, data)

        except Exception as e:
            print(f"[!] Error handling {client_address}: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # 연결 종료 시 룸에서 제거 (연결 끊김으로 처리)
            if current_room:
                self.remove_from_room(client_socket, current_room, role, is_disconnect=True)

            client_socket.close()

    def handle_create_room(self, client_socket, data):
        """룸 생성 처리"""
        print(f"[DEBUG] handle_create_room called with data: {data}")
        player_name = data.get("player_name", "Unknown")
        
        # 이미 다른 방에 있는지 확인하고 제거
        existing_room, existing_role = self.room_manager.find_room_by_socket(client_socket)
        if existing_room:
            print(f"[DEBUG] Player already in room {existing_room.room_id}, removing first")
            self.remove_from_room(client_socket, existing_room, existing_role, is_disconnect=False)

        # 새 룸 생성
        print(f"[DEBUG] Creating room for player: {player_name}")
        room_id = self.room_manager.create_room()
        print(f"[DEBUG] Room created with ID: {room_id}")
        room = self.room_manager.get_room(room_id)

        # 플레이어 추가
        print(f"[DEBUG] Adding player to room...")
        color = room.add_player(client_socket, player_name)
        print(f"[DEBUG] Player added with color: {color}")

        # 성공 응답
        response = Protocol.create_success(
            "Room created successfully",
            {
                "room_id": room_id,
                "your_color": color,
                "role": "player"
            }
        )
        print(f"[DEBUG] Sending response: {len(response)} bytes")
        try:
            client_socket.send(response)
            print(f"[DEBUG] Response sent successfully")
        except Exception as e:
            print(f"[ERROR] Failed to send response: {e}")

        print(f"[*] {player_name} created room: {room_id}")

    def handle_join_room(self, client_socket, data):
        """룸 참가 처리"""
        room_id = data.get("room_id")
        player_name = data.get("player_name", "Unknown")
        
        # 이미 다른 방에 있는지 확인하고 제거
        existing_room, existing_role = self.room_manager.find_room_by_socket(client_socket)
        if existing_room:
            print(f"[DEBUG] Player already in room {existing_room.room_id}, removing first")
            self.remove_from_room(client_socket, existing_room, existing_role, is_disconnect=False)

        room = self.room_manager.get_room(room_id)

        if not room:
            error = Protocol.create_error("Room not found")
            client_socket.send(error)
            return

        # 재연결 가능한 플레이어인지 확인
        if room.can_reconnect(player_name):
            print(f"[*] {player_name} is reconnecting to room {room_id} via JOIN")
            # 재연결 처리
            reconnect_data = {"player_name": player_name}
            self.handle_reconnect(client_socket, reconnect_data)
            return

        if room.is_full():
            error = Protocol.create_error("Room is full")
            client_socket.send(error)
            return

        # 플레이어 추가
        color = room.add_player(client_socket, player_name)

        # 성공 응답
        response = Protocol.create_success(
            "Joined room successfully",
            {
                "room_id": room_id,
                "your_color": color,
                "role": "player",
                "board": room.get_board_state(),
                "current_turn": room.current_turn
            }
        )
        client_socket.send(response)

        # 다른 사람들에게 알림
        join_msg = Protocol.create_message(
            MessageType.USER_JOINED,
            {
                "user_name": player_name,
                "role": "player",
                "color": color
            }
        )
        room.broadcast_to_all(join_msg)

        # 레디 상태 브로드캐스트
        if room.is_full():
            ready_msg = Protocol.create_message(
                MessageType.READY_STATUS,
                {"ready_status": room.get_ready_status()}
            )
            room.broadcast_to_all(ready_msg)

        print(f"[*] {player_name} joined room: {room_id} as {color}")

    def handle_spectate_room(self, client_socket, data):
        """룸 관전 처리"""
        room_id = data.get("room_id")
        spectator_name = data.get("spectator_name", "Spectator")
        
        # 이미 다른 방에 있는지 확인하고 제거
        existing_room, existing_role = self.room_manager.find_room_by_socket(client_socket)
        if existing_room:
            print(f"[DEBUG] Client already in room {existing_room.room_id}, removing first")
            self.remove_from_room(client_socket, existing_room, existing_role, is_disconnect=False)

        room = self.room_manager.get_room(room_id)

        if not room:
            error = Protocol.create_error("Room not found")
            client_socket.send(error)
            return

        # 관전자 추가
        room.add_spectator(client_socket, spectator_name)

        # 성공 응답 (현재 게임 상태 포함)
        response = Protocol.create_success(
            "Spectating room",
            {
                "room_id": room_id,
                "role": "spectator",
                "board": room.get_board_state(),
                "current_turn": room.current_turn,
                "status": room.status
            }
        )
        client_socket.send(response)

        # 다른 사람들에게 알림
        join_msg = Protocol.create_message(
            MessageType.USER_JOINED,
            {
                "user_name": spectator_name,
                "role": "spectator"
            }
        )
        room.broadcast_to_all(join_msg)

        print(f"[*] {spectator_name} spectating room: {room_id}")

    def handle_list_rooms(self, client_socket):
        """룸 목록 조회 처리"""
        rooms_info = self.room_manager.get_all_rooms_info()
        
        # 디버그: 실제 방 상태 출력
        print(f"[DEBUG] Current rooms: {len(rooms_info)} total")
        for room_info in rooms_info:
            print(f"  - {room_info['room_id']}: {room_info['player_count']} players, status={room_info['status']}, players={room_info['players']}")

        response = Protocol.create_message(
            MessageType.ROOM_LIST,
            {"rooms": rooms_info}
        )
        client_socket.send(response)

    def handle_chat_message(self, client_socket, data, current_room):
        """채팅 메시지 처리"""
        if not current_room:
            error = Protocol.create_error("You are not in a room")
            client_socket.send(error)
            return

        message_text = data.get("message", "")

        # 발신자 정보 찾기
        player = current_room.get_player_by_socket(client_socket)
        spectator = current_room.get_spectator_by_socket(client_socket)

        sender_name = player["name"] if player else spectator["name"]
        sender_role = "player" if player else "spectator"

        # 채팅 메시지 브로드캐스트
        chat_msg = Protocol.create_message(
            MessageType.CHAT_MESSAGE,
            {
                "sender": sender_name,
                "role": sender_role,
                "message": message_text
            }
        )
        current_room.broadcast_to_all(chat_msg)

        print(f"[{current_room.room_id}] {sender_name}: {message_text}")

    def handle_spectator_chat(self, client_socket, data, current_room):
        """관전자 채팅 메시지 처리"""
        if not current_room:
            error = Protocol.create_error("You are not in a room")
            client_socket.send(error)
            return

        # 관전자인지 확인
        spectator = current_room.get_spectator_by_socket(client_socket)
        if not spectator:
            error = Protocol.create_error("Only spectators can use spectator chat")
            client_socket.send(error)
            return

        message_text = data.get("message", "")
        
        # 관전자들에게만 채팅 메시지 전송
        spectator_chat_msg = Protocol.create_message(
            MessageType.SPECTATOR_CHAT,
            {
                "sender": spectator["name"],
                "message": message_text
            }
        )
        
        # 모든 관전자에게 전송
        with current_room.lock:
            for spec in current_room.spectators:
                try:
                    spec["socket"].send(spectator_chat_msg)
                except:
                    pass

        print(f"[{current_room.room_id}] [SPECTATOR] {spectator['name']}: {message_text}")

    def handle_ready(self, client_socket, data, current_room):
        """레디 상태 변경 처리"""
        if not current_room:
            error = Protocol.create_error("You are not in a room")
            client_socket.send(error)
            return

        # 플레이어 확인
        player = current_room.get_player_by_socket(client_socket)
        if not player:
            error = Protocol.create_error("Only players can ready up")
            client_socket.send(error)
            return

        # 레디 상태 토글
        current_ready = player.get("ready", False)
        new_ready = not current_ready
        current_room.set_player_ready(client_socket, new_ready)

        print(f"[{current_room.room_id}] {player['name']} ready: {new_ready}")

        # 레디 상태 브로드캐스트
        ready_msg = Protocol.create_message(
            MessageType.READY_STATUS,
            {"ready_status": current_room.get_ready_status()}
        )
        current_room.broadcast_to_all(ready_msg)

        # 모든 플레이어가 레디이면 게임 시작
        if current_room.are_all_players_ready():
            current_room.status = "playing"
            game_start_msg = Protocol.create_message(
                MessageType.GAME_START,
                {
                    "current_turn": current_room.current_turn,
                    "players": [{"name": p["name"], "color": p["color"]} for p in current_room.players]
                }
            )
            current_room.broadcast_to_all(game_start_msg)
            
            # 타이머 시작
            print(f"[DEBUG] Starting initial timer for {current_room.current_turn} turn")
            current_room.start_timer(self.handle_timer_event)
            # 타이머 워커가 첫 번째 업데이트로 60초를 보냄
            print(f"[*] Game started in room: {current_room.room_id}")

    def handle_place_stone(self, client_socket, data, current_room):
        """돌 놓기 처리"""
        if not current_room:
            error = Protocol.create_error("You are not in a room")
            client_socket.send(error)
            return

        # 플레이어 확인
        player = current_room.get_player_by_socket(client_socket)
        if not player:
            error = Protocol.create_error("Only players can place stones")
            client_socket.send(error)
            return

        # 게임 상태 확인
        if current_room.status != "playing":
            error = Protocol.create_error("Game is not in progress")
            client_socket.send(error)
            return

        # 차례 확인
        if player["color"] != current_room.current_turn:
            error = Protocol.create_error("Not your turn")
            client_socket.send(error)
            return

        # 좌표 가져오기
        x = data.get("x")
        y = data.get("y")

        if x is None or y is None:
            error = Protocol.create_error("Invalid coordinates")
            client_socket.send(error)
            return

        # 돌 놓기 시도
        try:
            current_room.place_stone(x, y, player["color"])
        except ValueError as e:
            error = Protocol.create_error(str(e))
            client_socket.send(error)
            return

        # 모두에게 보드 업데이트 전송
        board_update_msg = Protocol.create_message(
            MessageType.BOARD_UPDATE,
            {
                "x": x,
                "y": y,
                "color": player["color"],
                "board": current_room.get_board_state()
            }
        )
        current_room.broadcast_to_all(board_update_msg)

        print(f"[{current_room.room_id}] {player['name']} placed {player['color']} stone at ({x}, {y})")

        # 승리 확인
        winner = current_room.check_winner(x, y)
        if winner:
            # 게임 종료 시 타이머 정지
            current_room.stop_timer()
            current_room.status = "finished"
            game_end_msg = Protocol.create_message(
                MessageType.GAME_END,
                {
                    "winner": winner,
                    "winner_name": player["name"]
                }
            )
            current_room.broadcast_to_all(game_end_msg)
            print(f"[{current_room.room_id}] Game ended! Winner: {player['name']} ({winner})")
        else:
            # 현재 타이머 정지
            current_room.stop_timer()
            
            # 턴 변경
            current_room.switch_turn()
            turn_change_msg = Protocol.create_message(
                MessageType.TURN_CHANGE,
                {
                    "current_turn": current_room.current_turn
                }
            )
            current_room.broadcast_to_all(turn_change_msg)
            
            # 다음 턴 타이머 시작
            print(f"[DEBUG] Starting timer for {current_room.current_turn} turn after stone placement")
            current_room.start_timer(self.handle_timer_event)
            # 타이머 워커가 첫 번째 업데이트로 60초를 보냄

    def handle_leave_room(self, client_socket, current_room, role):
        """룸 나가기 처리"""
        print(f"[DEBUG] handle_leave_room called - Room: {current_room.room_id if current_room else 'None'}, Role: {role}")
        if current_room:
            print(f"[DEBUG] Removing from room...")
            self.remove_from_room(client_socket, current_room, role, is_disconnect=False)

            # 성공 응답 - 로비 상태를 알려줌
            print(f"[DEBUG] Sending leave success response...")
            response = Protocol.create_success("Left room and returned to lobby")
            try:
                client_socket.send(response)
                print(f"[DEBUG] Leave response sent successfully")
            except Exception as e:
                print(f"[ERROR] Failed to send leave response: {e}")
        else:
            # 이미 로비에 있는 경우
            response = Protocol.create_success("Already in lobby")
            try:
                client_socket.send(response)
            except Exception as e:
                print(f"[ERROR] Failed to send leave response: {e}")
        print(f"[DEBUG] handle_leave_room completed")

    def handle_timer_event(self, room_id, event_type, remaining_time=None):
        """타이머 이벤트 처리"""
        room = self.room_manager.get_room(room_id)
        if not room:
            return

        if event_type == "update":
            # 타이머 업데이트
            timer_msg = Protocol.create_message(
                MessageType.TIMER_UPDATE,
                {"remaining_time": remaining_time}
            )
            room.broadcast_to_all(timer_msg)
            
        elif event_type == "timeout":
            # 시간 초과 - 턴 자동 넘기기
            print(f"[{room_id}] Turn timeout for {room.current_turn}")
            
            # 게임이 진행 중인지 확인
            if room.status != "playing":
                print(f"[{room_id}] Timer timeout ignored - game not in playing state")
                return
            
            # 시간 초과 메시지
            print(f"[DEBUG] Sending TIME_UP for {room.current_turn}")
            timeout_msg = Protocol.create_message(
                MessageType.TIME_UP,
                {"player": room.current_turn}
            )
            room.broadcast_to_all(timeout_msg)
            
            # 턴 변경
            room.switch_turn()
            print(f"[DEBUG] Switched turn to {room.current_turn}")
            turn_change_msg = Protocol.create_message(
                MessageType.TURN_CHANGE,
                {"current_turn": room.current_turn}
            )
            room.broadcast_to_all(turn_change_msg)
            
            # 다음 플레이어 타이머 시작
            print(f"[DEBUG] Starting timer for {room.current_turn} turn after timeout")
            room.start_timer(self.handle_timer_event)
            # 타이머 워커가 첫 번째 업데이트로 60초를 보냄

    def handle_reconnect(self, client_socket, data):
        """재연결 처리"""
        player_name = data.get("player_name")
        
        if not player_name:
            error = Protocol.create_error("Player name is required for reconnection")
            client_socket.send(error)
            return
        
        print(f"[*] Reconnect attempt for player: {player_name}")
        
        # 재연결 가능한 룸 찾기
        found_room = None
        for room in self.room_manager.rooms.values():
            print(f"[DEBUG] Checking room {room.room_id}: disconnected_players = {list(room.disconnected_players.keys())}")
            if room.can_reconnect(player_name):
                print(f"[DEBUG] Player {player_name} can reconnect to room {room.room_id}")
                # 재연결될 플레이어 정보 가져오기 (삭제되기 전에)
                player_color = None
                for player in room.players:
                    if player["name"] == player_name:
                        player_color = player["color"]
                        break
                
                # 재연결 성공
                if room.reconnect_player(player_name, client_socket):
                    # 성공 응답 (타이머 정보 포함)
                    response_data = {
                        "room_id": room.room_id,
                        "your_color": player_color,
                        "role": "player",
                        "board": room.get_board_state(),
                        "current_turn": room.current_turn,
                        "game_status": room.status
                    }
                    
                    # 타이머 정보 추가
                    if room.status == "playing" and not room.is_paused:
                        remaining_time = room.get_remaining_time()
                        response_data["remaining_time"] = remaining_time
                    
                    response = Protocol.create_success(
                        "Reconnected successfully",
                        response_data
                    )
                    client_socket.send(response)
                    
                    # 다른 사람들에게 재연결 알림
                    reconnect_msg = Protocol.create_message(
                        MessageType.PLAYER_RECONNECTED,
                        {"player_name": player_name}
                    )
                    room.broadcast_to_all(reconnect_msg)
                    
                    # 게임 재개 메시지
                    if not room.is_paused:
                        resume_msg = Protocol.create_message(
                            MessageType.GAME_RESUMED,
                            {}
                        )
                        room.broadcast_to_all(resume_msg)
                    
                    print(f"[*] {player_name} reconnected to room: {room.room_id}")
                    return
        
        # 재연결 실패 - 구체적인 이유 확인
        for room in self.room_manager.rooms.values():
            if player_name in room.reconnect_attempts:
                attempts = room.reconnect_attempts.get(player_name, 0)
                if attempts >= room.max_reconnect_attempts:
                    error = Protocol.create_error(f"Maximum reconnection attempts ({room.max_reconnect_attempts}) exceeded")
                    client_socket.send(error)
                    return
        
        # 일반적인 재연결 실패
        error = Protocol.create_error("No reconnectable session found or timeout expired")
        client_socket.send(error)

    def remove_from_room(self, client_socket, room, role, is_disconnect=False):
        """룸에서 클라이언트 제거"""
        print(f"[DEBUG] remove_from_room called - Room: {room.room_id}, Role: {role}, Disconnect: {is_disconnect}")
        if not room:
            return

        user_name = None

        if role == "player":
            print(f"[DEBUG] Removing player from room...")
            user_name = room.remove_player(client_socket, is_disconnect)
            print(f"[DEBUG] Player {user_name} removed")
            
            if user_name and is_disconnect and room.status == "playing":
                # 연결 끊김 알림
                disconnect_msg = Protocol.create_message(
                    MessageType.PLAYER_DISCONNECTED,
                    {"player_name": user_name}
                )
                room.broadcast_to_all(disconnect_msg)
                
                # 게임 일시정지 알림
                pause_msg = Protocol.create_message(
                    MessageType.GAME_PAUSED,
                    {"reason": f"Player {user_name} disconnected. Waiting for reconnection..."}
                )
                room.broadcast_to_all(pause_msg)
                
            elif user_name and not is_disconnect:
                # 정상 나가기 - 게임 리셋 확인
                if len(room.players) == 1 and room.status == "waiting":
                    # 한 명만 남고 게임이 리셋됨
                    reset_msg = Protocol.create_message(
                        MessageType.ROOM_UPDATE,
                        {
                            "status": "waiting",
                            "message": "Waiting for another player to join",
                            "board": room.get_board_state()
                        }
                    )
                    room.broadcast_to_all(reset_msg)
                
        elif role == "spectator":
            user_name = room.remove_spectator(client_socket)

        if user_name and not is_disconnect:
            # 정상 나가기만 알림 (연결 끊김은 이미 위에서 처리)
            leave_msg = Protocol.create_message(
                MessageType.USER_LEFT,
                {
                    "user_name": user_name,
                    "role": role
                }
            )
            print(f"[DEBUG] Broadcasting USER_LEFT message...")
            room.broadcast_to_all(leave_msg)
            print(f"[DEBUG] USER_LEFT broadcast completed")

            print(f"[*] {user_name} ({role}) left room: {room.room_id}")

        # 빈 룸 정리
        print(f"[DEBUG] Cleaning up empty rooms...")
        self.room_manager.cleanup_empty_rooms()
        print(f"[DEBUG] Cleanup completed")

    def handle_surrender(self, client_socket, current_room):
        """항복 처리"""
        if not current_room or current_room.status != "playing":
            error = Protocol.create_error("Cannot surrender: not in an active game")
            client_socket.send(error)
            return

        # 항복한 플레이어 찾기
        surrendering_player = current_room.get_player_by_socket(client_socket)
        if not surrendering_player:
            error = Protocol.create_error("You are not a player in this game")
            client_socket.send(error)
            return

        # 상대방이 승리자가 됨
        winner_color = "white" if surrendering_player["color"] == "black" else "black"
        winner_name = None
        for player in current_room.players:
            if player["color"] == winner_color:
                winner_name = player["name"]
                break

        # 타이머 정지
        current_room.stop_timer()
        current_room.status = "finished"

        # 게임 종료 메시지
        game_end_msg = Protocol.create_message(
            MessageType.GAME_END,
            {
                "winner": winner_color,
                "winner_name": winner_name,
                "reason": f"{surrendering_player['name']} surrendered"
            }
        )
        current_room.broadcast_to_all(game_end_msg)

        print(f"[*] {surrendering_player['name']} surrendered. {winner_name} wins!")

    def handle_rematch(self, client_socket, current_room):
        """리게임 요청 처리"""
        if not current_room or current_room.status != "finished":
            error = Protocol.create_error("Cannot request rematch: game not finished")
            client_socket.send(error)
            return

        # 리게임 요청한 플레이어 찾기
        requesting_player = current_room.get_player_by_socket(client_socket)
        if not requesting_player:
            error = Protocol.create_error("You are not a player in this game")
            client_socket.send(error)
            return

        # 리게임 요청 등록
        if current_room.request_rematch(requesting_player["name"]):
            # 상대방에게 리게임 요청 알림 (30초 타임아웃)
            rematch_msg = Protocol.create_message(
                MessageType.REMATCH,
                {
                    "requesting_player": requesting_player["name"],
                    "message": f"{requesting_player['name']} wants a rematch",
                    "timeout": 30  # 30초 타임아웃
                }
            )
            current_room.broadcast_to_all(rematch_msg)

            # 모든 플레이어가 동의했는지 확인
            if current_room.is_rematch_agreed():
                # 리게임 시작
                current_room.start_rematch()
                
                # 보드 상태 먼저 전송 (빈 보드로 리셋됨)
                board_reset_msg = Protocol.create_message(
                    MessageType.BOARD_UPDATE,
                    {
                        "board": current_room.get_board_state(),
                        "x": -1,  # 리셋 표시
                        "y": -1,
                        "color": None
                    }
                )
                current_room.broadcast_to_all(board_reset_msg)
                
                # 리게임 시작 알림
                game_start_msg = Protocol.create_message(
                    MessageType.GAME_START,
                    {
                        "current_turn": current_room.current_turn,
                        "players": [
                            {"name": p["name"], "color": p["color"]} 
                            for p in current_room.players
                        ],
                        "board": current_room.get_board_state()  # 보드 상태 포함
                    }
                )
                current_room.broadcast_to_all(game_start_msg)
                
                # 타이머 시작
                current_room.start_timer(self.handle_timer_event)
                # 타이머 워커가 첫 번째 업데이트로 60초를 보냄
                
                print(f"[*] Rematch started in room: {current_room.room_id}")
            else:
                print(f"[*] {requesting_player['name']} requested rematch in room: {current_room.room_id}")

    def handle_rematch_response(self, client_socket, current_room, data):
        """리게임 응답 처리 (승낙/거절)"""
        print(f"[DEBUG] handle_rematch_response called with data: {data}")
        
        if not current_room:
            error = Protocol.create_error("Not in a room")
            client_socket.send(error)
            return
        
        responding_player = current_room.get_player_by_socket(client_socket)
        if not responding_player:
            error = Protocol.create_error("You are not a player in this game")
            client_socket.send(error)
            return
        
        accepted = data.get("accepted", False)
        print(f"[DEBUG] Rematch response from {responding_player['name']}: accepted={accepted}")
        
        if accepted:
            # 리게임 동의
            current_room.request_rematch(responding_player["name"])
            
            if current_room.is_rematch_agreed():
                print(f"[DEBUG] Both players agreed - starting rematch")
                # 모든 플레이어가 동의 - 리게임 시작
                current_room.start_rematch()
                
                # 보드 상태 먼저 전송
                board_reset_msg = Protocol.create_message(
                    MessageType.BOARD_UPDATE,
                    {
                        "board": current_room.get_board_state(),
                        "x": -1,
                        "y": -1,
                        "color": None
                    }
                )
                current_room.broadcast_to_all(board_reset_msg)
                
                # 리게임 시작 알림
                game_start_msg = Protocol.create_message(
                    MessageType.GAME_START,
                    {
                        "current_turn": current_room.current_turn,
                        "players": [
                            {"name": p["name"], "color": p["color"]} 
                            for p in current_room.players
                        ],
                        "board": current_room.get_board_state()
                    }
                )
                current_room.broadcast_to_all(game_start_msg)
                
                # 타이머 시작
                current_room.start_timer(self.handle_timer_event)
                # 타이머 워커가 첫 번째 업데이트로 60초를 보냄
                
                print(f"[*] Rematch started in room: {current_room.room_id} - Colors swapped")
            else:
                print(f"[DEBUG] Waiting for other player's response")
                # 첫 번째 플레이어의 동의 - 대기 메시지
                waiting_msg = Protocol.create_message(
                    MessageType.SUCCESS,
                    {
                        "message": "Waiting for other player's response...",
                        "rematch_accepted": True
                    }
                )
                client_socket.send(waiting_msg)
        else:
            # 리게임 거절
            print(f"[DEBUG] Rematch declined by {responding_player['name']}")
            current_room.rematch_requests.clear()  # 리게임 요청 취소
            
            # 모든 플레이어에게 거절 알림
            decline_msg = Protocol.create_message(
                MessageType.REMATCH_DECLINED,
                {
                    "message": f"{responding_player['name']} declined the rematch request",
                    "declined_by": responding_player['name']
                }
            )
            current_room.broadcast_to_all(decline_msg)
            
            print(f"[*] {responding_player['name']} declined rematch in room: {current_room.room_id}")

    def monitor_reconnection_timeouts(self):
        """재연결 타임아웃 모니터링 (별도 스레드)"""
        while True:
            try:
                time.sleep(30)  # 30초마다 체크
                for room in list(self.room_manager.rooms.values()):
                    timed_out_players = room.check_reconnect_timeout()
                    for player_name, player_color in timed_out_players:
                        print(f"[*] {player_name} forfeit due to reconnection timeout")
                        winner_color, winner_name = room.forfeit_player(player_name, player_color)
                        
                        # 몰수패 알림
                        forfeit_msg = Protocol.create_message(
                            MessageType.FORFEIT,
                            {
                                "winner": winner_color,
                                "winner_name": winner_name,
                                "player_name": player_name,
                                "reason": "Disconnection timeout (3 minutes)"
                            }
                        )
                        room.broadcast_to_all(forfeit_msg)
                        
                        # 게임 종료 메시지도 전송
                        game_end_msg = Protocol.create_message(
                            MessageType.GAME_END,
                            {
                                "winner": winner_color,
                                "winner_name": winner_name,
                                "reason": f"{player_name} forfeited"
                            }
                        )
                        room.broadcast_to_all(game_end_msg)
                        
            except Exception as e:
                print(f"[!] Error in timeout monitor: {e}")

    def start(self):
        """서버 시작"""
        print("=" * 50)
        print("Gomoku Game Server Started")
        print("=" * 50)

        # 소켓 생성
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 바인딩
        self.server_socket.bind((self.host, self.port))
        print(f"Server bound to {self.host}:{self.port}")

        # 연결 대기
        self.server_socket.listen(10)
        print("Waiting for client connections...")
        print("(Press Ctrl+C to stop the server)")
        print()

        # 재연결 타임아웃 모니터링 스레드 시작
        timeout_monitor = threading.Thread(target=self.monitor_reconnection_timeouts)
        timeout_monitor.daemon = True
        timeout_monitor.start()

        try:
            while True:
                # 클라이언트 연결 수락
                client_socket, client_address = self.server_socket.accept()

                # 새 스레드에서 처리
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()

        except KeyboardInterrupt:
            print("\n\nShutting down server...")

        finally:
            # 서버 소켓 닫기
            self.server_socket.close()
            print("Server socket closed.")

if __name__ == "__main__":
    server = GomokuServer(host='localhost', port=10000)
    server.start()
