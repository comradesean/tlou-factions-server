meta:
  id: simple_snapshot_phys_fx
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 52. Single-field, bit-packed payload.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  unconfirmed. Deserialize (FUN_00389a04, 0x00389a04) / Serialize
  (FUN_003898f8, 0x003898f8):
    field = ReadBits(13);   // offset 0x10
  Execute (FUN_00392a3c, 0x00392a3c) passes the value into
  FUN_00392908(value, 0xd9, 1) and FUN_00ad124c(...) - the fixed magic
  constant 0xd9 (217) and follow-up single-argument lookup are consistent
  with an entity/effect-index style lookup, but not confirmed.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: field_10
    type: b13
    doc: "13-bit unsigned value (object offset 0x10). Confirmed present/width; unverified guess: a physics-effect or entity index, given Execute's lookup-style usage."
