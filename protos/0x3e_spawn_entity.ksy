meta:
  id: spawn_entity
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 62. Fixed 2-field payload: an entity handle and a
  team id.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_0038a884, 0x0038a884) / Serialize (FUN_0038a5bc,
  0x0038a5bc):
    Read32(&entity_id);   // offset 0x10, via FUN_00a1b3c8
    Read32(&team_id);     // offset 0x14, via FUN_00a1af50
  Execute (FUN_0038b71c, 0x0038b71c) resolves entity_id via FUN_007b49dc
  (entity-handle-to-object lookup) and team_id via FUN_0039f3d8 (small
  per-match table lookup), then calls FUN_007b589c(entity, team) - directly
  confirms both fields' roles.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: entity_id
    type: b32
    doc: "32-bit entity handle (object offset 0x10). Confirmed: resolved via FUN_007b49dc then passed to FUN_007b589c(entity, team) on Execute."
  - id: team_id
    type: b32
    doc: "32-bit team identifier (object offset 0x14). Confirmed: resolved via FUN_0039f3d8 then passed to FUN_007b589c(entity, team) on Execute."
