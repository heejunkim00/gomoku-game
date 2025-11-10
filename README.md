# Gomoku Game - Computer Networking Assignment 3

Real-time multiplayer Gomoku (Five-in-a-Row) game with TCP socket programming, multithreading server architecture, and advanced features including spectator mode, chat system, and reconnection support.

## How to Run

Clear instructions on how to run the application, including dependencies, installation steps, and startup commands.

### Dependencies

**Required External Library:**
- `pygame` (version 2.0.0 or higher) - Used for client GUI interface

**Python Standard Libraries (no installation needed):**
- `socket` - TCP socket communication
- `threading` - Multithreading for concurrent connections
- `json` - Message serialization
- `time` - Timer functionality
- `random` - Room ID generation

**System Requirements:**
- Python 3.7 or higher
- Operating System: Windows, macOS, or Linux

### Installation Steps

1. **Install the only external dependency:**
```bash
pip install pygame
```

Note: No `requirements.txt` file is provided as pygame is the only external dependency. All other modules are part of Python standard library.

### Startup Commands

**Step 1: Start the Server**
```bash
cd examples
python gomoku_server.py
```
The server will start on `localhost:5555` by default.

**Step 2: Launch Client Instances**

Open multiple terminal windows and run:
```bash
cd client
python gomoku_gui_client.py
```

- First two clients become players
- Additional clients automatically become spectators
- All testing can be done on localhost (single machine)

## Features

### Core Features 

**Game Room System**
- Create and join game rooms
- View list of available rooms with their status
- Each room supports exactly 2 players
- Room states: "Waiting for Player" or "In Progress"

**Real-time Two-Player Gameplay**
- Standard 15x15 Gomoku board
- Black and white stones for two players
- Turn-based gameplay with strict turn enforcement
- Move validation (position validity, duplicate placement prevention)

**Spectator Mode**
- Multiple spectators can watch ongoing games simultaneously
- Real-time board synchronization for all spectators
- Spectators can view player chat messages (read-only)
- No limit on spectator count

**Game Mechanics**
- Server-side move validation
- Automatic win detection (horizontal, vertical, diagonal - 5 in a row)
- Turn order enforcement
- Game state management

**Chat System**
- Real-time chat between players
- Spectators can view player conversations
- Separate spectator-only chat channel (advanced feature)
- Chat history maintained during the game

**Server Architecture**
- Multithreaded server using Python threading
- Each client connection handled in a separate thread
- Non-blocking concurrent game rooms
- Thread-safe game state management with RLock

### Advanced Features

**1. Spectator-only Chat Mode**
- Spectators have a dedicated chat channel separate from players
- Spectators can communicate with each other without disturbing players
- Players cannot see spectator chat messages
- Implementation: Shift+Enter for spectators to send messages to spectator chat

**2. Move Timer with Time Limits**
- 60-second time limit per turn
- Real-time countdown display with visual timer bar
- Color-coded warning system:
  - Green: > 10 seconds remaining
  - Orange: 5-10 seconds remaining  
  - Red: < 5 seconds remaining
- Automatic turn change on timeout
- Timer resets to 60 seconds for each new turn

**3. Reconnection Support**
- Players can rejoin after disconnection
- 3-minute reconnection window
- Automatic game pause when player disconnects
- Session recovery using player nickname
- Game state fully restored upon reconnection
- Join button automatically handles reconnection if same nickname is used

### Additional Features (Beyond Requirements)

**Ready System**
- Players must click "READY" before game starts
- Visual ready status indicators for both players
- Prevents accidental game starts

**Surrender Mechanism**
- Players can surrender during the game
- Immediate game end with opponent declared winner
- Clean game termination

**Rematch System**
- Quick rematch after game ends
- Both players must agree to rematch
- Automatic color swap (black becomes white, white becomes black)
- New game starts immediately upon agreement

**Leave Room**
- Clean room exit functionality
- Proper resource cleanup
- Return to lobby after leaving

**Visual Enhancements**
- Gradient backgrounds for better visual appeal
- Hover effects on buttons
- Last move highlighting on board
- Turn indicators and player status display
- Optimized window size for 4-way split screen recording

**Reconnection Timer Display**
- Visual countdown when opponent disconnects
- Shows remaining time before automatic forfeit
- Color-coded urgency indicators

## Protocol Specification

All communication uses JSON messages with the following structure:

```json
{
  "type": "MESSAGE_TYPE",
  "data": {...},
  "timestamp": "2025-11-10T12:00:00"
}
```

### Client to Server Messages

```python
# Room Management
CREATE_ROOM: {"type": "CREATE_ROOM", "data": {"player_name": "Alice"}}
JOIN_ROOM: {"type": "JOIN_ROOM", "data": {"room_id": "room_1", "player_name": "Bob"}}
LEAVE_ROOM: {"type": "LEAVE_ROOM", "data": {"room_id": "room_1"}}
LIST_ROOMS: {"type": "LIST_ROOMS", "data": {}}
SPECTATE_ROOM: {"type": "SPECTATE_ROOM", "data": {"room_id": "room_1", "spectator_name": "Charlie"}}

# Game Actions
READY: {"type": "READY", "data": {}}
PLACE_STONE: {"type": "PLACE_STONE", "data": {"x": 7, "y": 7}}
SURRENDER: {"type": "SURRENDER", "data": {}}

# Chat
CHAT_MESSAGE: {"type": "CHAT_MESSAGE", "data": {"room_id": "room_1", "message": "Good game!"}}
SPECTATOR_CHAT: {"type": "SPECTATOR_CHAT", "data": {"room_id": "room_1", "message": "Nice move!"}}

# Rematch & Reconnection
REMATCH: {"type": "REMATCH", "data": {}}
REMATCH_RESPONSE: {"type": "REMATCH_RESPONSE", "data": {"accepted": true}}
RECONNECT: {"type": "RECONNECT", "data": {"player_name": "Alice"}}
```

### Server to Client Messages

```python
# Responses
SUCCESS: {"type": "SUCCESS", "data": {"message": "Room created", "room_id": "room_1"}}
ERROR: {"type": "ERROR", "data": {"message": "Invalid move"}}

# Room Updates
ROOM_LIST: {"type": "ROOM_LIST", "data": {"rooms": [...]}}
ROOM_UPDATE: {"type": "ROOM_UPDATE", "data": {"room_id": "room_1", "status": "playing"}}
USER_JOINED: {"type": "USER_JOINED", "data": {"player_name": "Bob", "role": "player"}}
USER_LEFT: {"type": "USER_LEFT", "data": {"player_name": "Bob"}}

# Game State
GAME_START: {"type": "GAME_START", "data": {"current_turn": "black"}}
BOARD_UPDATE: {"type": "BOARD_UPDATE", "data": {"x": 7, "y": 7, "color": "black"}}
TURN_CHANGE: {"type": "TURN_CHANGE", "data": {"current_turn": "white"}}
GAME_END: {"type": "GAME_END", "data": {"winner": "black", "winner_name": "Alice"}}

# Timer
TIMER_UPDATE: {"type": "TIMER_UPDATE", "data": {"remaining_time": 45}}
TIME_UP: {"type": "TIME_UP", "data": {"player": "black"}}

# Connection Status
PLAYER_DISCONNECTED: {"type": "PLAYER_DISCONNECTED", "data": {"player_name": "Alice"}}
PLAYER_RECONNECTED: {"type": "PLAYER_RECONNECTED", "data": {"player_name": "Alice"}}
GAME_PAUSED: {"type": "GAME_PAUSED", "data": {"reason": "Player disconnected"}}
GAME_RESUMED: {"type": "GAME_RESUMED", "data": {}}
FORFEIT: {"type": "FORFEIT", "data": {"winner": "white", "player_name": "Bob"}}

# Rematch
REMATCH_DECLINED: {"type": "REMATCH_DECLINED", "data": {}}
```

## Architecture

### Server Architecture
- **Multithreading Model**: Each client connection is handled in a separate thread
- **Thread Safety**: RLock (Reentrant Lock) used for game state synchronization
- **Room Management**: RoomManager class maintains all active game rooms
- **Timer System**: Separate timer threads for each active game
- **Message Queue**: Thread-safe message broadcasting to all room participants

### Client Architecture
- **GUI Framework**: pygame for game interface
- **Network Thread**: Separate thread for receiving server messages
- **Event-Driven**: Mouse and keyboard event handling for user interactions
- **State Management**: Clean separation between lobby and game states

## Testing Guide

### Basic Gameplay Test
1. Start the server
2. Launch two clients and enter different nicknames
3. First player creates a room
4. Second player joins the room
5. Both players click READY
6. Take turns placing stones
7. Achieve 5 in a row to win

### Spectator Mode Test
1. Start a game with two players
2. Launch a third client
3. Click "Watch" button on the active game room
4. Verify spectator can see all moves and chat
5. Test spectator chat with Shift+Enter

### Timer Test
1. Start a game
2. Wait 60 seconds without making a move
3. Verify automatic turn change
4. Check timer reset for new turn

### Reconnection Test
1. Start a game between two players
2. Close one client (force quit)
3. Relaunch client with same nickname
4. Join the same room (automatic reconnection)
5. Verify game state is restored

### Surrender Test
1. During an active game, click "Surrender"
2. Verify game ends immediately
3. Check winner declaration

### Rematch Test
1. Complete a game
2. Click "Rematch" button
3. Both players must accept
4. Verify colors are swapped
5. New game starts automatically

## Project Structure

```
gomoku-game/
├── README.md                 # This file
├── client/
│   └── gomoku_gui_client.py  # Client GUI implementation
├── server/
│   ├── game_logic.py         # Game rules and win detection
│   └── room_manager.py       # Room and player management
├── common/
│   └── protocol.py           # Protocol definitions
└── examples/
    └── gomoku_server.py      # Main server implementation
```

