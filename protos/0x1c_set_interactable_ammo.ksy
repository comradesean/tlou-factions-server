meta:
  id: set_interactable_ammo
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 28. 2-field payload: an interactable id and an
  ammo count.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_004057e0, 0x004057e0) / Serialize (FUN_00405788,
  0x00405788):
    Read32(&interactable_id);   // offset 0x10, via FUN_00a1af50
    Read32(&ammo_count);        // offset 0x14, via FUN_00a1ae90
  Execute (FUN_00406c80, 0x00406c80) resolves interactable_id via
  FUN_003ac5b8, then either writes ammo_count directly into the resolved
  object's +0x390 field, or - if a related weapon-rack object exists -
  calls its vtable+0x30c setter with ammo_count as the value argument.
  Directly confirms both fields.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: interactable_id
    type: b32
    doc: "32-bit interactable id (object offset 0x10). Confirmed: resolved via FUN_003ac5b8 on Execute."
  - id: ammo_count
    type: b32
    doc: "32-bit ammo count (object offset 0x14). Confirmed: written into the resolved interactable's +0x390 field, or passed to a weapon-rack setter, on Execute."
