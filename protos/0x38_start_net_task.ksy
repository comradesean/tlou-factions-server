meta:
  id: start_net_task
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 56. Single-field payload, one 32-bit value.

  STATUS: confirmed structurally, high confidence. Deserialize
  (FUN_0038a950, 0x0038a950) / Serialize (FUN_0038a680, 0x0038a680):
    Read32(&task_id);   // offset 0x10, via FUN_00a1b3c8
  Execute (FUN_0038dbc8, 0x0038dbc8) uses the value as a lookup key into
  what looks like a task/entity registry (FUN_009ef28c, then a fallback
  FUN_0078be94) - consistent with a task identifier.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: task_id
    type: b32
    doc: "32-bit task identifier (object offset 0x10). Confirmed used as a registry lookup key on Execute."
