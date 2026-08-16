meta:
  id: item_received
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 100. 3-field payload: two 32-bit fields and a bool.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  low (Execute is a large item-pickup VFX/audio routine not fully traced
  this pass). Deserialize (FUN_003fdc94, 0x003fdc94) / Serialize
  (FUN_003fdc30, 0x003fdc30):
    Read32(&field_10);   // offset 0x10, via FUN_00a1af50
    Read32(&field_14);   // offset 0x14, via FUN_00a1af50
    ReadBool(&field_18); // offset 0x18
  Execute (FUN_003fe0f0, 0x003fe0f0) resolves field_14 via FUN_0039f3d8
  (a player-registry lookup) and, once resolved, resolves field_10 via
  the same helper - consistent with (player_id, item_id) in some order -
  then runs a substantial VFX/audio-cue pipeline gated on field_18. Left
  at "structure confirmed, exact field roles not disambiguated" per this
  project's confidence discipline rather than guessing which of field_10/
  field_14 is the player vs. the item.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: field_10
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed present/width; resolved via FUN_0039f3d8 on Execute (same registry-lookup helper as field_14) - likely player_id or item_id, not disambiguated."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; resolved via FUN_0039f3d8 on Execute (checked first, gates the rest of the routine) - likely player_id or item_id, not disambiguated."
  - id: field_18
    type: b1
    doc: "Bool (object offset 0x18). Confirmed present/width; gates a large VFX/audio branch in Execute (0x003fe0f0), exact meaning not traced further."
