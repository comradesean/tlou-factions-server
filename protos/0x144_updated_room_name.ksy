meta:
  id: updated_room_name
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  REAL IDENTITY (corrected 2026-08-16): this is
  `NetMatchmakingUpdatedRoomName`, NOT `NetMatchmakingHostRank`. The filename
  is kept opcode-keyed for continuity; the `meta/id` and the analysis below
  use the corrected name. See
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 5 for the full argument (the declared name/size table has two
  phantom entries at indices 22-23, shifting everything from index 24 onward
  down by two wire opcodes; all four affected declared sizes then match the
  real wire sizes exactly).

  One of the 11 opcodes the client's own receive-dispatch (FUN_00ad7604) has
  a case for. 144 bytes (`cmpwi r0,143` gate at 0x00ad83b4, buffer advance of
  0x90 at 0x00ad8440).

  KEY CORRECTION: the payload is a NUL-TERMINATED STRING, not a fixed
  128-byte binary block. The handler at 0x00ad8400 is:

      addi r3,r3,24        ; matched_room + 0x18
      addi r4,r31,16       ; wire + 16
      bl   0xe45b10        ; <- strcpy, TWO arguments, no length

  `_opd_FUN_00e45b10` was decompiled this pass and is unambiguously strcpy
  (word-at-a-time NUL detection via `(x & 0x7f7f7f7f) + 0x7f7f7f7f | x |
  0x7f7f7f7f`, then a byte-wise tail). The previous "copies a 128-byte block"
  reading inferred the length from the packet size; the code has no length
  argument at all.

  PRACTICAL CONSEQUENCE: the string MUST be NUL-terminated within 128 bytes
  or the strcpy overruns `room_obj+0x18` into `room_obj+0x98` and beyond.
  Echoing the client's own 0x143 payload back (what
  tools/session_manager_stub.py does) is safe and is exactly the right
  behaviour for a room-name confirmation - the client only ever puts a
  strcpy'd `<npid>.<unix-timestamp>` there.

  SEQUENCING: the room lookup keys on `*(s64*)(room_obj+0x10) == wire[8..15]`
  across the connection's 4 room slots. room_obj+0x10 is set ONLY by Member's
  (0x131) handler. This message is silently swallowed if it arrives first.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x144 (324 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not read by the 0x144 dispatch case at all."
  - id: room_id
    type: u8
    doc: "Offset 8:16. `ld r10,8(r29)` @ 0x00ad83c0, compared against `*(s64*)(room_obj+0x10)` for each of the 4 room slots."
  - id: room_name
    size: 128
    doc: "Offset 16:144. NUL-terminated room name, strcpy'd into `room_obj+0x18` - the same field the client itself fills before sending 0x143/SetRoomName, and the same string RoomCreate (0x12f) carries at its own wire offset 0x28. MUST contain a NUL within these 128 bytes."
