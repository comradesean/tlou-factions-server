meta:
  id: complete_task
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 55. Fixed 2-field payload, two back-to-back 32-bit
  values.

  STATUS: confirmed structurally, high confidence. Deserialize
  (FUN_0038a980, 0x0038a980) / Serialize (FUN_0038a6b0, 0x0038a6b0):
    Read32(&field1);   // offset 0x10, via FUN_00a1b3c8
    Read32(&field2);   // offset 0x14, via FUN_00a1b3c8
  Execute (FUN_00388b4c, 0x00388b4c) stores both directly into a global
  task-tracking struct (+0x4b50, +0x4b54) and sets a completion flag
  (+0x4af8 = 1) - confirms these are a task identifier pair (likely
  task-type + task-instance-id), though which field is which is not
  disambiguated.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: field_10
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed stored into a global task-tracking struct on Execute; likely task-type or task-id, not disambiguated from field_14."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed stored into a global task-tracking struct on Execute alongside field_10; likely task-id or a result value, not disambiguated."
