meta:
  id: add_net_marker
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 104. 3-field payload: a 13-bit player/entity id, a
  marker-type value, and a third 32-bit field.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium for owner_id/marker_type, low for field_18.
  Deserialize (FUN_00409ad8, 0x00409ad8) / Serialize (FUN_004099cc,
  0x004099cc):
    ReadBits(&owner_id, 13);   // offset 0x10
    Read32(&marker_type);      // offset 0x14, via FUN_00a1b3c8 (the
                                // entity-handle call site seen elsewhere)
    Read32(&field_18);         // offset 0x18, via FUN_00a1b488 (4th
                                // confirmed Read32-equivalent call site)
  Execute (FUN_00410188, 0x00410188) resolves owner_id via FUN_0039f3d8,
  then uses marker_type to fill a local struct (FUN_003d2ce0) and look up
  a per-marker-type dictionary entry (FUN_007a3878), conditionally applying
  a status effect keyed off that lookup. field_18 is not referenced in the
  traced Execute code.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: owner_id
    type: b13
    doc: "13-bit owner/player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute."
  - id: marker_type
    type: b32
    doc: "32-bit value (object offset 0x14), read via FUN_00a1b3c8 (the entity-handle call site). Confirmed: used as a key into a per-marker-type dictionary lookup on Execute (FUN_007a3878)."
  - id: field_18
    type: b32
    doc: "32-bit value (object offset 0x18). Confirmed present/width; not referenced in the traced portion of Execute - role unconfirmed (possibly a marker position or duration)."
