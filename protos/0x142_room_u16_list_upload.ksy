meta:
  id: room_u16_list_upload
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingRoomU16ListUpload - client -> server, over the Session
  Manager connection (port 7314). Not one of the 11 opcodes the client's
  own receive-dispatch has a case for (client-to-server only).

  RENAMED from `host_rank` - that name assumed the trailing u16 list was
  per-member rank data. The disassembly-verified opcode map does not
  confirm any such meaning; renamed to a purely structural, non-inventive
  name. THE PURPOSE OF THE U16 LIST IS UNKNOWN - do not assume it is ranks,
  scores, or any other specific semantic without further evidence.

  STATUS: variable-length message, a 16-byte header plus a `count * 2`-byte
  trailing payload copied verbatim from a caller-supplied buffer
  (`_opd_FUN_00e3e064`, a plain memcpy-shaped helper, not decompiled
  further). Builder confirmed at 0x00ad60c4. Every header field's exact
  store instruction was located.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x142 (322 decimal), stored as a raw big-endian compile-time constant (no runtime byteswap call needed for this one - the literal is already emitted in wire order)."
  - id: count
    type: u2
    doc: "Offset 4:6. The function's 4th argument, truncated to 16 bits and stored raw - no processing call at all, though that would be moot anyway since the calls elsewhere in this family are confirmed no-ops (research/notes/2026-08-15-byteswap-helper-is-a-noop.md). Number of u16 entries in the trailing list."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Not written by this sender - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field - matches the room_id-echo pattern used throughout this opcode family."
  - id: entries
    type: u2
    repeat: expr
    repeat-expr: count
    doc: "Offset 16 onward, count*2 bytes. Raw caller-supplied u16 list, copied verbatim (memcpy-shaped helper, not further decompiled). PURPOSE UNKNOWN - not traced back to a caller or reader this pass; do not assume a specific meaning (e.g. ranks) without further evidence."
