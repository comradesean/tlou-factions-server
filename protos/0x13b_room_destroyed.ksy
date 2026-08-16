meta:
  id: room_destroyed
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingRoomDestroyed (declared name) - server -> client, over the
  Session Manager connection (port 7314). One of the 11 opcodes the client's
  own receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: declared size in the Init() size table is 16 bytes - CONFIRMED
  WRONG. The dispatch case requires >79 buffered bytes and consumes exactly
  80 (0x50) bytes.

  NAME QUESTIONABLE: unlike a whole-room teardown, the observed behavior
  looks up ONE member by id (member_id at offset 4, via the same
  `_opd_FUN_00ad0d4c` lookup helper 0x134/RoomLeave uses) and, if found,
  copies a length-prefixed blob (length byte at offset 6, payload starting
  at offset 16) into that member's own struct at +0xfc, plus stashes the
  length itself at that member's +0xf8. This is per-member data delivery,
  not room-wide destruction - flagged as a probable declared-name mismatch
  (same class of error already confirmed twice for this table: 0x133 and
  ClientHello2/Ping), but no confirmed alternate name/purpose exists yet.
  Do not treat "RoomDestroyed" as settled.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13b (315 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: member_id
    type: u2
    doc: "Offset 4:6. Passed to the member-lookup helper (_opd_FUN_00ad0d4c) - same helper 0x134/RoomLeave uses."
  - id: blob_length
    type: u1
    doc: "Offset 6:7. Used both as the byte count copied from the trailing blob and stored verbatim into the matched member's own struct at +0xf8."
  - id: unknown_1
    size: 1
    doc: "Offset 7:8. Not read by the traced portion of the 0x13b dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` for each of the connection's 4 room slots (slot i's room-object pointer is at `this + i*0x9000 + 0x50`; verified by raw disasm this pass, the `addis r11,r11,1 / addi r11,r11,-28672` idiom is a 0x9000 stride). Silently dropped if no slot matches - and room_obj+0x10 is set ONLY by Member's (0x131) handler, so this message must follow a Member. Same room_id-echo pattern used throughout this opcode family."
  - id: blob
    size: 64
    doc: "Offset 16:80. Copied (blob_length bytes of it) into the matched member's struct at +0xfc. Semantics unconfirmed - the packet is always 80 bytes regardless of blob_length, so bytes past blob_length within this region go unused by the traced code path."
