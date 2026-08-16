meta:
  id: signal_respawn_player
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 30. 3-field payload: player id, a bool, and an
  unresolved 32-bit field.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium for player_id/respawn_flag, low for field_18.
  Deserialize (FUN_00409eac, 0x00409eac) / Serialize (FUN_00409d08,
  0x00409d08):
    ReadBits(&player_id, 13);   // offset 0x10
    ReadBool(&respawn_flag);    // offset 0x14
    Read32(&field_18);          // offset 0x18, via FUN_00a1b488 (4th
                                 // confirmed Read32-equivalent call site)
  Execute (FUN_0040ec04, 0x0040ec04) resolves player_id via FUN_0039f3d8,
  checks a capability flag, and branches on respawn_flag: the false path
  sets two per-player fields from a hash-keyed lookup (FUN_009e98cc,
  plausibly a spawn-point id pair); the true path calls FUN_0040eaa4
  instead. field_18 is not referenced in the traced Execute code.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute."
  - id: respawn_flag
    type: b1
    doc: "Bool (object offset 0x14). Confirmed present/width; selects between two Execute code paths (a spawn-point lookup vs. a different call), exact meaning of each path not disambiguated."
  - id: field_18
    type: b32
    doc: "32-bit value (object offset 0x18), read via FUN_00a1b488 - confirmed as a 4th equivalent Read32 call site (see companion doc section 5). Not referenced in the traced portion of Execute; likely a respawn-point id given the opcode name, not confirmed."
