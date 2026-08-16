meta:
  id: member_updated_data
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingMemberUpdatedData (declared name) - server -> client, over
  the Session Manager connection (port 7314). One of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: declared size in the Init() size table is 80 bytes - CONFIRMED
  WRONG. The dispatch case requires >15 buffered bytes and consumes exactly
  16.

  NAME QUESTIONABLE: the room lookup here matches by ROOM id (comparing
  struct+0x10 against the room_id field, the exact same match used by every
  whole-room-targeted case in this dispatcher), not by a member id via the
  `_opd_FUN_00ad0d4c` member-lookup helper the genuinely per-member cases
  (0x134/RoomLeave, 0x13b) use. The single payload field (offset 4) is
  written into the matched ROOM struct itself at +0x19f0 - four bytes before
  the confirmed "is owner" flag OwnerChanged (0x13f) writes at +0x19f4.
  Despite its declared name, this looks like a room-level attribute update
  adjacent to ownership state, not a per-member data update - flagged as a
  probable declared-name mismatch, no confirmed alternate name yet.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13d (317 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: value
    type: u2
    doc: "Offset 4:6. Written verbatim into the matched room struct at +0x19f0, immediately adjacent to OwnerChanged's (0x13f) +0x19f4 flag byte. Semantic meaning unconfirmed."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Not read by the traced portion of the 0x13d dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against the session's own tracked room id - same room_id-echo pattern used throughout this opcode family."
