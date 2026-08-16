meta:
  id: swap_booster
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 76. 4-field, bit-packed payload: player id, a
  16-bit value, an 8-bit value, and a 4-bit value.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium. Deserialize (FUN_0040a330, 0x0040a330) / Serialize
  (FUN_0040a2a8, 0x0040a2a8):
    ReadBits(&player_id, 13);   // offset 0x10
    Read16(&old_slot_value);    // offset 0x14, via FUN_00a1b190 (3rd
                                 // confirmed Read16-equivalent call site)
    ReadU8(&flag_byte);         // offset 0x16, via FUN_00a1ab64 (newly
                                 // confirmed - see companion doc section 5)
    ReadBits(&new_booster_id, 4); // offset 0x18
  Execute (FUN_0040ce9c, 0x0040ce9c) resolves player_id via FUN_0039f3d8,
  then either applies the fields directly via FUN_003665c8(mgr, player_id,
  old_slot_value, flag_byte, new_booster_id) (not-found path) or does a
  "snapshot, apply, verify, possibly revert" sequence around the same call
  (found path) - the 4-bit width on the last field is consistent with a
  small enum (booster type index).
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute."
  - id: old_slot_value
    type: b16
    doc: "16-bit value (object offset 0x14), read via FUN_00a1b190 - confirmed as a 3rd equivalent Read16 call site (see companion doc section 5). Passed to the booster-apply call; exact role (previous booster slot/id) not independently confirmed."
  - id: flag_byte
    type: b8
    doc: "8-bit value (object offset 0x16), read via FUN_00a1ab64 - newly confirmed 8-bit read helper (see companion doc section 5). Passed to the booster-apply call; role unconfirmed."
  - id: new_booster_id
    type: b4
    doc: "4-bit value (object offset 0x18). Confirmed present/width; passed as the final argument to the booster-apply call - narrow width is consistent with a small booster-type enum, not independently confirmed."
