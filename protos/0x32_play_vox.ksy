meta:
  id: play_vox
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 50. Fixed 4-field, bit-packed payload.

  STATUS: confirmed structurally, high confidence on type/width for all
  four fields; semantics confirmed for speaker_id only. Deserialize
  (FUN_0038903c, 0x0038903c) / Serialize (FUN_00388ef4, 0x00388ef4):
    Read32(&vox_id);      // offset 0x10
    speaking = ReadBool(); // offset 0x14
    Read32(&field_18);    // offset 0x18
    Read32(&speaker_id);  // offset 0x1c
  Execute (FUN_0038d138, 0x0038d138) compares speaker_id (offset 0x1c)
  against a live player object's field +0x77 to select between two
  different sound-event hash constants passed to FUN_003e82cc - consistent
  with speaker_id selecting a 3D-positional vs. non-positional playback
  variant depending on whether the speaker is the local player. vox_id and
  field_18 are confirmed present/32-bit; their specific meaning (vox
  line/bank id, category/priority) is not confirmed.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: vox_id
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed present/width; likely a vox line/bank id, not independently confirmed."
  - id: speaking
    type: b1
    doc: "1-bit bool (object offset 0x14). Confirmed present/width; exact meaning not confirmed - unverified guess: whether this is a start-speaking vs. stop-speaking event."
  - id: field_18
    type: b32
    doc: "32-bit value (object offset 0x18). Confirmed present/width; semantic meaning not confirmed."
  - id: speaker_id
    type: b32
    doc: "32-bit value (object offset 0x1c). Confirmed via Execute comparing it against a live player object's +0x77 field to pick a 3D vs. non-positional sound-event variant - this is the speaking player's id/handle."
