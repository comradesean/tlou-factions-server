meta:
  id: stop_pack_or_deploy
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 34. 2-field payload: a 13-bit player id and an
  unresolved 32-bit field.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium for player_id, low for field_14.
  Deserialize (FUN_003f6af8, 0x003f6af8) / Serialize (FUN_003f68ec,
  0x003f68ec):
    ReadBits(&player_id, 13);   // offset 0x10
    Read32(&field_14);          // offset 0x14, via FUN_00a1af50
  Execute (FUN_003f70fc, 0x003f70fc) passes both fields together into
  FUN_003f6f28(player_id, field_14) as a combined lookup key; if it
  resolves, calls FUN_006c1c48(result) (a stop/cleanup-style call,
  consistent with the opcode name). field_14's individual role (a
  carry-object type or slot index) is not disambiguated since it's only
  used jointly with player_id in the lookup.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed present/width; used jointly with field_14 as a lookup key in Execute (FUN_003f6f28)."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; used jointly with player_id as a lookup key in Execute - likely a carry-object type or slot index given the opcode name, not confirmed individually."
