meta:
  id: animation_sync
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 64. Fixed 3-field, bit-packed payload.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  partially confirmed. Deserialize (FUN_0038998c, 0x0038998c) / Serialize
  (FUN_00389888, 0x00389888):
    anim_index = ReadBits(1);   // offset 0x10, 1 bit
    Read32(&field_14);           // offset 0x14, via FUN_00a1af50
    Read32(&field_18);           // offset 0x18, via FUN_00a1ae90
  Execute (FUN_0038e610, 0x0038e610) uses anim_index (offset 0x10) as a
  byte multiplied into a per-entity animation-table stride (*0xf158), then
  combines field_14/field_18 into a packed value stored back into that
  table entry - confirms the 3-field shape; exact semantics of field_14/
  field_18 (likely a frame number and a timestamp/phase value) are not
  disambiguated.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: anim_index
    type: b1
    doc: "1-bit selector (object offset 0x10). Confirmed used as a multiplier index into a per-entity animation table on Execute - effectively a 2-valued animation-slot selector, not a plain bool."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; combined with field_18 into a packed animation-table entry on Execute, exact role not disambiguated."
  - id: field_18
    type: b32
    doc: "32-bit value (object offset 0x18). Confirmed present/width; combined with field_14 into a packed animation-table entry on Execute, exact role not disambiguated."
