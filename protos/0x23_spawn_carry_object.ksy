meta:
  id: spawn_carry_object
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 35. 2-field payload, both 32-bit.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  low-medium. Deserialize (FUN_003f6a9c, 0x003f6a9c) / Serialize
  (FUN_003f6898, 0x003f6898):
    Read32(&field_10);   // offset 0x10, via FUN_00a1af50
    Read32(&field_14);   // offset 0x14, via FUN_00a1af50
  Execute (FUN_003f7c64, 0x003f7c64) gates on field_10 being nonzero (a
  boolean-ish role), then resolves a global carry-object registry and
  toggles a per-slot flag; branches on field_14 being zero (a plain
  "drop" call, FUN_00782038 with all-default args) vs. nonzero (a second
  registry lookup feeding richer arguments into the same call). Structure
  is clear; individual field semantics (spawn-flag / carry-object-type)
  not confidently disambiguated.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: field_10
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed present/width; gates a branch in Execute in a boolean-like way. Exact role not confirmed."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; selects between two Execute code paths (plain drop vs. richer registry-backed spawn). Likely a carry-object type id, not confirmed."
