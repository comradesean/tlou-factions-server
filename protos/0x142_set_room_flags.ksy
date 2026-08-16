meta:
  id: set_room_flags
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetRoomFlags - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only).

  STATUS: declared size in the Init() size table is a fixed 16 bytes -
  CONFIRMED WRONG. Sender fully identified and disassembled 2026-08-15
  (`FUN_00ad5ffc` at vtable+0x38): this is a variable-length message, a
  16-byte header plus a `num_entries * 2`-byte trailing payload copied
  verbatim from a caller-supplied buffer (`_opd_FUN_00e3e064`, a plain
  memcpy-shaped helper, not decompiled further). Every header field's exact
  store instruction was located.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x142 (322 decimal), stored as a raw big-endian compile-time constant (no runtime byteswap call needed for this one - the literal is already emitted in wire order)."
  - id: num_entries
    type: u2
    doc: "Offset 4:6. The function's 4th argument (`param_4`), truncated to 16 bits and stored raw - no processing call at all, though that would be moot anyway since the calls elsewhere in this family are confirmed no-ops (research/notes/2026-08-15-byteswap-helper-is-a-noop.md)."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Not written by this sender - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field - matches the room_id-echo pattern used throughout this opcode family."
  - id: flags_data
    size: num_entries * 2
    doc: "Offset 16 onward, num_entries*2 bytes. Raw caller-supplied payload, copied verbatim (memcpy-shaped helper, not further decompiled). Per-entry field semantics entirely unconfirmed - not traced back to a caller this pass."
