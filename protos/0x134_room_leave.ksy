meta:
  id: room_leave
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingRoomLeave - client -> server, over the Session Manager
  connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for (this file documents the
  receive side; the client both sends and can receive this shape - the
  dispatch decompile is what's evidenced here).

  STATUS: declared size in the Init() size table is 16 bytes, but the
  receive-dispatch case for 0x134 requires >23 buffered bytes and advances
  the buffer by exactly 24 (0x18) bytes after processing - CONFIRMED actual
  wire size is 24 bytes, not 16. Looks up a specific member by the id at
  offset 16 via `_opd_FUN_00ad0d4c` (member-id -> member-handle) then removes
  them via `_opd_FUN_00ad3190` - the exact same per-member removal call the
  confirmed room-abandon path (opcode 0x133, protos/0x133_room_leaving.ksy)
  uses for every member in a room. Unlike 0x133 (which tears down the whole
  room), 0x134 targets one member_id - "this specific member is leaving",
  consistent with its declared name.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x134 (308 decimal). Passed through a dedicated per-opcode field-touching helper (_opd_FUN_00ad58c8) - decompiled 2026-08-15 and confirmed to be composed entirely of calls to the no-op FUN_00a0e324/FUN_00a0e320, so this stays plain big-endian; see research/notes/2026-08-15-byteswap-helper-is-a-noop.md."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not read by the traced portion of the 0x134 dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against the session's own tracked room id (*(longlong*)(param_1+0x24060)) to find the matching room slot - same room_id-echo pattern used throughout this opcode family."
  - id: member_id
    type: u2
    doc: "Offset 16:18. Passed directly to the member-lookup helper (_opd_FUN_00ad0d4c) to find the member being removed."
  - id: trailing
    size: 6
    doc: "Offset 18:24. Not read by the traced portion of the 0x134 dispatch case - unconfirmed. Present only because the dispatch loop consumes exactly 24 bytes total."
