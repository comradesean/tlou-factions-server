meta:
  id: room_search_info
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingRoomSearchInfo - sent unprompted by the client after
  Member/RoomJoined, over the Session Manager connection (port 7314).

  STATUS: declared opcode/size table (docs/protocol/session_manager_and_
  matchmaking.md) claims 56 bytes - live capture 2026-08-15 shows the
  actual size is 16 bytes. The payload's tail 8 bytes exactly match the
  room_id this server assigned via Member's header - confirmed by direct
  comparison against a real capture. tools/session_manager_stub.py
  (ROOM_SEARCH_INFO_OPCODE) echoes this room_id straight back as
  RoomSearchResult (0x138) at the same wire offset; this was tried live and
  had zero effect on the "Searching for Optimal Game"/"Starting Game" hang
  the client was showing at the time - ROOM_LEAVING_OPCODE (0x133, the
  client abandoning the room on its own initiative) is considered the more
  likely actual cause of that hang, not a missing/wrong reply here.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x137 (311 decimal). Confirmed live, big-endian."
  - id: unknown
    size: 4
    doc: "Offset 4:8. Not independently traced this pass - content unconfirmed in the one live capture referenced above."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Confirmed by direct comparison against a live capture: exactly matches the room_id this server assigned via Member's header. Echoed back verbatim in the stub's RoomSearchResult reply."
