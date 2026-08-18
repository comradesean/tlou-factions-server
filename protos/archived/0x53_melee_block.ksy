meta:
  id: melee_block
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 83. 2-field payload: a 13-bit player id and a
  32-bit value.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_003fed68, 0x003fed68) / Serialize (FUN_003fec84,
  0x003fec84):
    ReadBits(&player_id, 13);   // offset 0x10
    Read32(&block_value);       // offset 0x14, via FUN_00a1b488 (4th
                                 // confirmed Read32-equivalent call site)
  Execute (FUN_004002b0, 0x004002b0) resolves player_id via FUN_0039f3d8,
  then writes block_value directly into the resolved object's +0x58c
  field - a direct field-store, confirming both fields.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute."
  - id: block_value
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed: written directly into the resolved player object's +0x58c field on Execute. Exact semantic label (block state/target) not further disambiguated."
