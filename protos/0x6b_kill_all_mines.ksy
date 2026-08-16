meta:
  id: kill_all_mines
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 107. Confirmed empty payload - same pattern as
  start_connection/net_go/assign_team_done.

  STATUS: confirmed, high confidence. Deserialize (FUN_00410564,
  0x00410564) and Serialize (FUN_00410568, 0x00410568) are both literal
  `{ return; }` - zero bits written beyond the shared envelope. Execute
  (FUN_00410c00, 0x00410c00) calls FUN_009ef134(mine_registry,
  mine_registry_field, ..., 0) - a "clear all" call on the mine registry
  itself, needing no per-object field, consistent with a broadcast
  "no payload" signal matching the opcode name exactly.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq: []
