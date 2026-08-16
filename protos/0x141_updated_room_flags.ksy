meta:
  id: updated_room_flags
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingUpdatedAttrFlags - server -> client reply to SetAttrFlags
  (0x140), over the Session Manager connection (port 7314). IS one of the
  11 opcodes the client's own receive-dispatch (FUN_00ad7604) already has a
  case for (unlike 0x140, 0x142, 0x143) - a classic "client sets X, server
  confirms updated X" pair.

  STATUS: 16 bytes, matching SetAttrFlags' own size. The handler is now
  disassembled at the instruction level (0x00ad82d4-0x00ad8358, 2026-08-16):

      ad82ec:  lhz  r3,4(r29)        ; u16 at offset 4 - NOT a 4-byte field
      ad830c:  ld   r3,8(r29)        ; room_id, 8 bytes at offset 8
      (search all 4 room slots for *(s64*)(room_obj+0x10) == room_id)
      ad8350:  clrlwi r0,r10,16      ; zero-extend the u16
      ad8354:  stw  r0,496(r9)       ; room_obj+0x1f0 = value

  So only offset 4:6 is read; offset 6:8 is ignored entirely. This matches
  the 0x140 sender, which also writes only a u16 there (see
  protos/0x140_set_room_flags.ksy for the correction).

  SEQUENCING: the room lookup keys on room_obj+0x10, which is set ONLY by
  Member's (0x131) handler from Member wire offset 16. This message is
  silently swallowed if it arrives before a Member has established that id.

  tools/session_manager_stub.py echoes SetAttrFlags' `chunk[4:8]` verbatim,
  which preserves the meaningful u16 correctly (and echoes 2 bytes of the
  client's own stack garbage, which the client ignores) - accidentally
  correct behaviour.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x141 (321 decimal)."
  - id: value
    type: u2
    doc: "Offset 4:6. `lhz r3,4(r29)` @ 0x00ad82ec. Zero-extended and stored into the matched room's +0x1f0. Echo SetAttrFlags' own u16 here."
  - id: unread_2
    size: 2
    doc: "Offset 6:8. Not read by the handler at all. Send zero (or echo the client's own bytes; either works)."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` across the connection's 4 room slots. Must match the id established by Member, or the message is silently dropped."
