meta:
  id: set_player_exposed
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 103. 3-field payload: a 13-bit player id, a 32-bit
  value, and a bool.

  STATUS: confirmed structurally and semantically (player_id/is_exposed
  high, field_14 low). Deserialize (FUN_00409d80, 0x00409d80) / Serialize
  (FUN_00409bdc, 0x00409bdc):
    ReadBits(&player_id, 13);   // offset 0x10
    Read32(&field_14);          // offset 0x14, via FUN_00a1b488 (4th
                                 // confirmed Read32-equivalent call site)
    ReadBool(&is_exposed);      // offset 0x18
  Execute (FUN_004094b8, 0x004094b8) resolves player_id via FUN_0039f3d8,
  then writes is_exposed directly into the resolved object's +0x90a byte
  field - directly confirms is_exposed and matches the opcode name
  exactly. field_14 is not referenced in this Execute function.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; not referenced in the traced Execute code - role unconfirmed."
  - id: is_exposed
    type: b1
    doc: "Bool (object offset 0x18). Confirmed: written directly into the resolved player's +0x90a field on Execute, matching the opcode name exactly."
