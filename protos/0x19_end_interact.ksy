meta:
  id: end_interact
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 25. 3-field payload: player id, an interactable id,
  and an unresolved third field. Part of the interact family (see also
  opcodes 21/23/24/61).

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium confidence for the first two fields, low for the third.
  Deserialize (FUN_00405f80, 0x00405f80) / Serialize (FUN_00405c70,
  0x00405c70):
    ReadBits(&player_id, 13);      // offset 0x10
    Read32(&interactable_id);      // offset 0x14, via FUN_00a1af50
    Read32(&field_18);             // offset 0x18, via FUN_00a1ae90
  Execute (FUN_00406a74, 0x00406a74) resolves player_id via FUN_0039f3d8
  and, if a per-object capability check passes, calls FUN_003a1f50 (an
  interrupt/cancel-style call) - then separately resolves interactable_id
  via FUN_003ac5b8 (an interactable-registry lookup distinct from the
  player registry) and clears a pending-interact flag via FUN_003acde4.
  field_18 is not referenced in the traced Execute code (the remainder is
  telemetry/debug calls with hash constants) - present and 32-bit, role
  unconfirmed.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute, matching the common 13-bit player-id pattern."
  - id: interactable_id
    type: b32
    doc: "32-bit interactable id (object offset 0x14). Confirmed: resolved via FUN_003ac5b8 (the interactable-registry lookup) on Execute, whose result has a pending-interact flag cleared."
  - id: field_18
    type: b32
    doc: "32-bit value (object offset 0x18). Confirmed present/width; not referenced in the traced portion of Execute (0x00406a74) - role unconfirmed."
