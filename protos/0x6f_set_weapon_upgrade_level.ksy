meta:
  id: set_weapon_upgrade_level
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 111. 3-field payload: an entity id and two 8-bit
  upgrade-level values.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_00410704, 0x00410704) / Serialize (FUN_004106a0,
  0x004106a0):
    Read32(&entity_id);       // offset 0x10, via FUN_00a1af50
    ReadU8(&upgrade_level_a); // offset 0x14, via FUN_00a1ab64
    ReadU8(&upgrade_level_b); // offset 0x15, via FUN_00a1ab64
  Execute (FUN_00410638, 0x00410638) resolves entity_id via FUN_0039f3d8,
  then passes both byte fields straight into FUN_003cd838(resolved_entity,
  upgrade_level_a, upgrade_level_b) - a direct setter call, matching the
  opcode name well (two weapon-part upgrade levels, or current+previous
  level).
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: entity_id
    type: b32
    doc: "32-bit weapon/entity id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute."
  - id: upgrade_level_a
    type: b8
    doc: "8-bit value (object offset 0x14). Confirmed: passed directly to the upgrade-level setter call (FUN_003cd838) on Execute."
  - id: upgrade_level_b
    type: b8
    doc: "8-bit value (object offset 0x15). Confirmed: passed directly to the upgrade-level setter call (FUN_003cd838) on Execute, second argument."
