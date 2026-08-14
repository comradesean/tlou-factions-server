meta:
  id: debug
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 85. Single-field payload, one 32-bit value.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  unconfirmed. Deserialize (FUN_0038955c, 0x0038955c) / Serialize
  (FUN_00389244, 0x00389244):
    Read32(&value);   // offset 0x10, via FUN_00a1af50
  Execute (FUN_0038b79c, 0x0038b79c) passes it straight to
  FUN_0064b8dc(value, 0), a debug-output helper - exact meaning of the
  value (a debug code, category id, or free-form number) not traced
  further.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: value
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed passed to a debug-output helper (FUN_0064b8dc) on Execute; specific meaning not confirmed."
