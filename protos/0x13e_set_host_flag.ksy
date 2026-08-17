meta:
  id: set_host_flag
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetHostFlag - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only). Pairs with
  0x13f/HostFlagUpdated, the server's confirmation of the same flag change.

  RENAMED from `set_attr_flags` to match the disassembly-verified opcode
  map's confirmed field shape: a single flag byte plus a fixed-constant
  "kind" byte, not a generic attribute-flags word.

  STATUS: confirmed 16 bytes. Two distinct sender call sites build and send
  this shape (builders at 0x00ad6b58 and 0x00ad7120), differing in how the
  flag byte at offset 4 is derived from their respective boolean inputs -
  one is gated on the room's own +0x19f4 "is host" flag (toggling it
  locally either way), the other computes it via a small bitwise
  negate-and-shift sequence. Both are plausible "request to become/cease
  being room host" call sites; which UI/game-logic path triggers each was
  not traced this pass.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13e (318 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: flag
    type: u1
    doc: "Offset 4:5. A single boolean-shaped byte (0 or 1), derived differently by each of the two confirmed sender call sites - see doc for both. Written into the matched room's +0x19f4 'is host' flag by 0x13f's handler on the round trip."
  - id: kind
    type: u1
    doc: "Offset 5:6. Fixed constant, 3 for both confirmed builders (0x00ad6b58 / 0x00ad7120). Purpose unconfirmed - plausibly a request-reason/source tag."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Not written by either confirmed sender - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field, matching the room_id-echo pattern used throughout this opcode family."
