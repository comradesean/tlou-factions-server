meta:
  id: room_search_result
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingRoomSearchResult - server -> client reply to RoomSearchInfo
  (0x137), over the Session Manager connection (port 7314). One of the 11
  opcodes the client's own receive-dispatch (FUN_00ad7604) already has a
  case for (confirmed via sessmgr_vtable_dump.txt) - its handler searches a
  4-slot local array by an 8-byte key at wire offset 8, matching
  RoomSearchInfo's room_id shape.

  STATUS: declared table size (docs/protocol/session_manager_and_
  matchmaking.md) is 16 bytes, matching what this project's stub actually
  sends. Only the room_id-echo field is exercised/confirmed live; the
  4-byte field at offset 4 is sent as zero by the stub and its real
  semantics are unconfirmed. Tried live 2026-08-15 as a reply to
  RoomSearchInfo - had zero effect on the "Searching for Optimal Game"
  hang; see 0x137_room_search_info.ksy and ROOM_LEAVING_OPCODE (0x133) for
  the more likely actual cause.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x138 (312 decimal)."
  - id: unknown
    size: 4
    doc: "Offset 4:8. Sent as zero by tools/session_manager_stub.py's ROOM_SEARCH_INFO_OPCODE handler - real semantics unconfirmed, this value has not been shown to matter."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Echo of the corresponding RoomSearchInfo's own room_id field (see 0x137_room_search_info.ksy) - the client's receive-dispatch handler for this opcode searches its local room-slot array by this exact 8-byte key."
