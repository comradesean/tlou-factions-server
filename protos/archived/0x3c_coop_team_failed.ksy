meta:
  id: coop_team_failed
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 60. Fixed 2-field payload: an entity handle and a
  team id.

  STATUS: confirmed structurally and semantically, medium-high confidence
  (by direct analogy with spawn_entity, opcode 62, which uses the identical
  shape and the identical two lookup functions). Deserialize (FUN_0038a7f8,
  0x0038a7f8) / Serialize (FUN_0038a538, 0x0038a538):
    Read32(&entity_id);   // offset 0x10, via FUN_00a1b3c8
    Read32(&team_id);     // offset 0x14, via FUN_00a1af50
  Execute (FUN_00393c34, 0x00393c34) resolves offset 0x10 via
  FUN_007b49dc (an entity-handle-to-object lookup, confirmed identical
  usage in kill_entity opcode 63) and offset 0x14 via FUN_0039f3d8 (a
  lookup keyed off a small per-match table, consistent with a team index).
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: entity_id
    type: b32
    doc: "32-bit entity handle (object offset 0x10). Confirmed resolved via FUN_007b49dc, the same entity-handle lookup used by kill_entity/spawn_entity."
  - id: team_id
    type: b32
    doc: "32-bit team identifier (object offset 0x14). Confirmed resolved via FUN_0039f3d8, the same small-table lookup used by spawn_entity's second field."
