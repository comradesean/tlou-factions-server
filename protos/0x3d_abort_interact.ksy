meta:
  id: abort_interact
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 61. 3-field payload, structurally identical to
  opcode 21 (request_interact) and confirming its field-role hypothesis:
  player id, an interact-slot value, and a target id.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium-high for player_id/target_id (cross-confirmed against
  request_interact), low-medium for interact_slot.
  Deserialize (FUN_00405ff8, 0x00405ff8) / Serialize (FUN_00405ce0,
  0x00405ce0):
    ReadBits(&player_id, 13);   // offset 0x10
    Read32(&interact_slot);     // offset 0x14, via FUN_00a1af50
    Read32(&target_id);         // offset 0x18, via FUN_00a1af50
  Execute (FUN_00406688, 0x00406688) calls
  FUN_003acc74(interact_ctx, target_id, player_id, interact_slot) - the
  exact same function and argument order (target=0x18, player=0x10,
  extra=0x14) as request_interact's Execute - then on success calls
  FUN_003ace50 with the same three arguments, confirming the field
  mapping by direct cross-opcode structural match.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed via the same call shape as request_interact's player_id field."
  - id: interact_slot
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; matches request_interact's interact_slot field position exactly, same unresolved exact role."
  - id: target_id
    type: b32
    doc: "32-bit target/interactable id (object offset 0x18). Confirmed via the same call shape as request_interact's target_id field."
