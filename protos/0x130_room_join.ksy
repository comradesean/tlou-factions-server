meta:
  id: room_join
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingRoomJoin - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only, no reply
  processing implemented client-side).

  STATUS: confirmed 88 bytes (matching the declared size), sender fully
  identified 2026-08-15 via instruction-level disassembly (not just C
  decompile) of vtable+0x18 (`FUN_00ad6718`) and the field-touching helper
  it calls (`_opd_FUN_00ad5580`, disassembled separately to confirm exactly
  which 3 words it touches: offsets 0, 4, 8). That helper - like every
  similar one in this family - is composed entirely of calls to the
  confirmed no-op `FUN_00a0e324` (see
  `research/notes/2026-08-15-byteswap-helper-is-a-noop.md`); it does not
  actually byte-swap anything. Every field below is plain big-endian.

  NOTABLE: offset 8 is NOT this family's usual 8-byte room_id. It's a raw
  4-byte store of the sending client's own in-process room-object pointer
  (register r31/param_2 at the call site) - i.e. an opaque, meaningless-to-
  the-server local value, presumably intended purely as a correlation token
  for whatever reply eventually references it. Offset 4:8 is genuinely
  uninitialized stack (read and passed through the no-op helper along with
  the real fields, but never explicitly written by the caller) - same class
  of finding as the confirmed-garbage second word in 0x133's payload.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x130 (304 decimal), passed through _opd_FUN_00ad5580 (offset 0 of the 3 words it touches) - a confirmed no-op, so this stays plain big-endian."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Confirmed via disassembly to be uninitialized stack content at send time - not meaningful data, despite being passed through the field-touching helper along with the real fields."
  - id: local_room_ptr
    type: u4
    doc: "Offset 8:12. The sending client's own raw in-process room-object pointer at the time of the call (`stw r31,0x78(r1)` in FUN_00ad6718), passed through the same no-op helper as the opcode. An opaque client-local value, not a room_id."
  - id: unknown_flag
    type: u1
    doc: "Offset 12:13. Copied verbatim from the room object's own +0x19f8 byte. Meaning not traced this pass."
  - id: unknown_3
    size: 3
    doc: "Offset 13:16. Not written by the traced disassembly - unconfirmed."
  - id: param3_value
    size: 8
    doc: "Offset 16:24. Raw (unswapped) 8-byte copy of the function's third argument (`std r29,0x80(r1)`). This argument's own source/meaning at RoomJoin's call site was not traced this pass."
  - id: room_snapshot
    size: 64
    doc: "Offset 24:88. Byte-for-byte copy of the room object's own bytes 0x0-0x3f (confirmed via a 64x single-byte lbz/stb copy loop in the disassembly, not a single bulk copy - notable but not semantically informative on its own). Field-level meaning of this 64-byte region not decoded this pass."
