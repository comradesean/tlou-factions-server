meta:
  id: promote
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingPromote - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only).

  STATUS: confirmed 16 bytes (matching the declared size). Two distinct
  sender call sites found and fully disassembled 2026-08-15
  (`FUN_00ad6a34` at vtable+0x20, `FUN_00ad7024` at vtable+0x34) - both
  build and send an identical 16-byte shape, differing only in the fixed
  constant at offset 5 (3 vs. 4) and how the flag byte at offset 4 is
  derived. `FUN_00ad6a34`'s variant is gated on the room's own +0x19f4
  "is owner" flag (toggles it locally either way, mirroring the confirmed
  0x13f/OwnerChanged flag) and computes offset 4 from a boolean parameter
  via one of two branches (either the raw value or its logical negation,
  each forced to strict 0/1); `FUN_00ad7024`'s variant computes offset 4
  via a small bitwise negate-and-shift sequence from a different boolean
  input, without touching +0x19f4. Both are plausible "request to promote/
  demote a member to room owner" call sites; which UI/game-logic path
  triggers each was not traced this pass.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13e (318 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: flag
    type: u1
    doc: "Offset 4:5. A single boolean-shaped byte (0 or 1), derived differently by each of the two confirmed sender call sites - see doc for both. Likely \"promote\" vs \"demote\", not confirmed which value means which."
  - id: variant_tag
    type: u1
    doc: "Offset 5:6. A fixed compile-time constant differing per sender call site: 3 for FUN_00ad6a34 (vtable+0x20), 4 for FUN_00ad7024 (vtable+0x34). Purpose unconfirmed - plausibly a request-reason/source tag."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Not written by either confirmed sender - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field, matching the room_id-echo pattern used throughout this opcode family."
