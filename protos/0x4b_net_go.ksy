meta:
  id: net_go
  endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 75. Confirmed EMPTY payload - carries no fields
  beyond the shared per-event wire envelope, same pattern as
  start_connection (opcode 0) and assign_team_done (opcode 20).

  STATUS: confirmed, high confidence. Deserialize (FUN_00388b78,
  0x00388b78) and Serialize (FUN_00388b7c, 0x00388b7c) are both literal
  `{ return; }`. Execute (FUN_003928bc, 0x003928bc) conditionally triggers
  FUN_00392750 - consistent with net_go being a pure "synchronized match
  start" signal, matching the opcode name.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq: []
