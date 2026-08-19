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

  So only offset 4:6 (the attr_selector) is read by the client; offset 6:8 is not
  read on the echo either. SETTLED 2026-08-18 (second pass): 6:8 is sender-side
  residue on the 0x140 side too - the low half of a stale pointer in the reused
  send buffer, NOT an attribute value. An intermediate revision claimed otherwise
  from cross-day reproducibility; leaked pointers reproduce exactly on a
  deterministic emulator, so that argument was invalid. See
  protos/0x140_set_room_flags.ksy and
  research/notes/2026-08-18-wire-residue-and-field-corrections.md §1-2.
  Nothing on either side of this round trip reads 6:8.

  DEFINITION / PURPOSE: the server's "room attribute updated" confirmation of a
  0x140 SetAttrFlags. Classic set-X / confirm-X pair. The client uses it only to
  refresh room_obj+0x1f0 with the selector (4:6); that field is never branched
  on, so the echo is effectively an ack.

  SEQUENCING: the room lookup keys on room_obj+0x10, which is set ONLY by
  Member's (0x131) handler from Member wire offset 16. This message is
  silently swallowed if it arrives before a Member has established that id.

  server/session_manager.py echoes SetAttrFlags' `chunk[4:8]` verbatim, which
  round-trips both halves (selector + value) correctly.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x141 (321 decimal)."
  - id: attr_selector
    type: u2
    doc: "Offset 4:6. `lhz r3,4(r29)` @ 0x00ad82ec. Zero-extended and stored into the matched room's +0x1f0 (never branched on afterwards). Echo SetAttrFlags' selector here."
  - id: pad_6
    type: u2
    doc: "Offset 6:8. NOT A FIELD - the 0x140 send side leaves this as leaked stack (see protos/0x140_set_room_flags.ksy pad_6), and the client does not read it on the echo either. Echoing SetAttrFlags' own bytes back is harmless and is what server/session_manager.py does (it echoes chunk[4:8] verbatim); sending 0 is equally correct. (Was `attr_value`.)"
  - id: room_id
    size: 8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` across the connection's 4 room slots. Must match the id established by Member, or the message is silently dropped."
