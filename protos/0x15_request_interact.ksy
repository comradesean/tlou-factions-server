meta:
  id: request_interact
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 21. 3-field payload: player id, an interact-slot
  value, and a target id. Part of the interact family alongside opcodes
  23/24/25/61 (denied_interact/on_interact/end_interact/abort_interact).

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium confidence (high for player_id/target_id, low-medium for the
  middle field). Deserialize (FUN_00406070, 0x00406070) / Serialize
  (FUN_00405d4c, 0x00405d4c):
    ReadBits(&player_id, 13);   // offset 0x10
    Read32(&interact_slot);     // offset 0x14, via FUN_00a1af50
    Read32(&target_id);         // offset 0x18, via FUN_00a1af50
  Execute (FUN_00407c68, 0x00407c68) calls
  FUN_003acc74(interact_ctx, target_id, player_id, 0) to validate the
  request; on success calls FUN_003aceb8(interact_ctx, target_id,
  player_id) then FUN_00407a9c(player_id, interact_slot, target_id) -
  confirms player_id/target_id's roles via consistent argument position
  across all three calls. interact_slot (offset 0x14) is passed through
  without being used as a lookup key itself in the traced code, so its
  exact role (slot index vs. interact type) is not disambiguated.
  Opcode 61 (abort_interact) uses the identical FUN_003acc74/FUN_003ace50
  call shape and argument order, reinforcing this field mapping.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit requesting-player id (object offset 0x10). Confirmed: passed as the 'requester' argument to the interact validate/approve calls on Execute."
  - id: interact_slot
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; passed through to the post-approval handler without being used as a lookup key in the traced Execute code - likely an interact type or slot index, not confirmed."
  - id: target_id
    type: b32
    doc: "32-bit target/interactable id (object offset 0x18). Confirmed: passed as the 'target' argument to the interact validate/approve calls, same argument position as abort_interact's own target field."
