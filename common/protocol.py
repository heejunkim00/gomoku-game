#!/usr/bin/env python3
"""
통신 프로토콜 정의 (Protocol Definition)
- 클라이언트와 서버 간 메시지 형식을 정의합니다
- JSON 기반의 구조화된 메시지를 사용합니다
"""

import json
from datetime import datetime

class MessageType:
    """메시지 타입 상수"""
    # 연결 관련
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"

    # 룸 관련
    CREATE_ROOM = "CREATE_ROOM"
    JOIN_ROOM = "JOIN_ROOM"
    LEAVE_ROOM = "LEAVE_ROOM"
    LIST_ROOMS = "LIST_ROOMS"
    SPECTATE_ROOM = "SPECTATE_ROOM"

    # 채팅 관련
    CHAT_MESSAGE = "CHAT_MESSAGE"
    SPECTATOR_CHAT = "SPECTATOR_CHAT"

    # 게임 관련
    READY = "READY"
    PLACE_STONE = "PLACE_STONE"
    GAME_START = "GAME_START"
    GAME_END = "GAME_END"
    BOARD_UPDATE = "BOARD_UPDATE"
    TURN_CHANGE = "TURN_CHANGE"

    # 응답
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    ROOM_LIST = "ROOM_LIST"
    ROOM_UPDATE = "ROOM_UPDATE"  # 룸 상태 변경 알림
    USER_JOINED = "USER_JOINED"
    USER_LEFT = "USER_LEFT"
    READY_STATUS = "READY_STATUS"
    TIMER_UPDATE = "TIMER_UPDATE"
    TIME_UP = "TIME_UP"
    
    # 재연결 관련
    RECONNECT = "RECONNECT"
    PLAYER_DISCONNECTED = "PLAYER_DISCONNECTED"
    PLAYER_RECONNECTED = "PLAYER_RECONNECTED"
    GAME_PAUSED = "GAME_PAUSED"
    GAME_RESUMED = "GAME_RESUMED"
    
    # 게임 종료 관련
    SURRENDER = "SURRENDER"  # 항복
    FORFEIT = "FORFEIT"      # 연결 끊김으로 인한 몰수패
    REMATCH = "REMATCH"      # 리게임 요청
    REMATCH_RESPONSE = "REMATCH_RESPONSE"  # 리게임 응답
    REMATCH_DECLINED = "REMATCH_DECLINED"  # 리게임 거절

class Protocol:
    """프로토콜 유틸리티 클래스"""

    @staticmethod
    def create_message(msg_type, data=None):
        """
        메시지를 생성합니다

        Args:
            msg_type: 메시지 타입 (MessageType 클래스의 상수)
            data: 메시지 데이터 (딕셔너리)

        Returns:
            JSON 문자열 (바이트) + 구분자
        """
        message = {
            "type": msg_type,
            "data": data if data else {},
            "timestamp": datetime.now().isoformat()
        }
        return (json.dumps(message) + '\n').encode('utf-8')

    @staticmethod
    def parse_messages(raw_data):
        """
        받은 데이터에서 여러 메시지를 파싱합니다

        Args:
            raw_data: 받은 데이터 (바이트)

        Returns:
            파싱된 딕셔너리 리스트 또는 빈 리스트 (에러 시)
        """
        try:
            text = raw_data.decode('utf-8')
            lines = text.strip().split('\n')
            messages = []
            
            for line in lines:
                if line.strip():  # 빈 줄 건너뛰기
                    try:
                        message = json.loads(line)
                        messages.append(message)
                    except json.JSONDecodeError as e:
                        print(f"[!] Error parsing line: {line[:50]}... - {e}")
                        
            return messages
        except Exception as e:
            print(f"[!] Error parsing messages: {e}")
            return []

    @staticmethod
    def parse_message(raw_data):
        """
        하나의 메시지만 파싱합니다 (하위 호환성)

        Args:
            raw_data: 받은 데이터 (바이트)

        Returns:
            파싱된 딕셔너리 또는 None (에러 시)
        """
        messages = Protocol.parse_messages(raw_data)
        return messages[0] if messages else None

    @staticmethod
    def create_error(error_message):
        """에러 메시지 생성"""
        return Protocol.create_message(
            MessageType.ERROR,
            {"message": error_message}
        )

    @staticmethod
    def create_success(success_message, extra_data=None):
        """성공 메시지 생성"""
        data = {"message": success_message}
        if extra_data:
            data.update(extra_data)
        return Protocol.create_message(MessageType.SUCCESS, data)

# 메시지 생성 헬퍼 함수들

def create_room_message(player_name):
    """룸 생성 요청"""
    return Protocol.create_message(
        MessageType.CREATE_ROOM,
        {"player_name": player_name}
    )

def join_room_message(room_id, player_name):
    """룸 참가 요청"""
    return Protocol.create_message(
        MessageType.JOIN_ROOM,
        {"room_id": room_id, "player_name": player_name}
    )

def spectate_room_message(room_id, spectator_name):
    """룸 관전 요청"""
    return Protocol.create_message(
        MessageType.SPECTATE_ROOM,
        {"room_id": room_id, "spectator_name": spectator_name}
    )

def list_rooms_message():
    """룸 목록 요청"""
    return Protocol.create_message(MessageType.LIST_ROOMS)

def chat_message(room_id, message):
    """채팅 메시지"""
    return Protocol.create_message(
        MessageType.CHAT_MESSAGE,
        {"room_id": room_id, "message": message}
    )

def leave_room_message(room_id):
    """룸 나가기"""
    return Protocol.create_message(
        MessageType.LEAVE_ROOM,
        {"room_id": room_id}
    )

# 사용 예시:
"""
# 서버에서:
from common.protocol import Protocol, MessageType

# 메시지 생성
message = Protocol.create_message(
    MessageType.SUCCESS,
    {"room_id": "room_1"}
)
client_socket.send(message)

# 메시지 파싱
raw_data = client_socket.recv(1024)
parsed = Protocol.parse_message(raw_data)
if parsed:
    msg_type = parsed["type"]
    data = parsed["data"]

    if msg_type == MessageType.CREATE_ROOM:
        player_name = data["player_name"]
        # 룸 생성 처리...
"""
