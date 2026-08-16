meta:
  id: end_round
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 6. Fixed 2-field payload, two back-to-back 32-bit
  values.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  unconfirmed. Deserialize (FUN_003890c0, 0x003890c0) / Serialize
  (FUN_00388f74, 0x00388f74):
    Read32(&field1);   // offset 0x10, via FUN_00a1ae90
    Read32(&field2);   // offset 0x14, via FUN_00a1ae90
  Execute (FUN_0038cc2c, 0x0038cc2c) routes both values into a
  formatting/log helper (FUN_00767434) whose arguments weren't traced
  further this session - fields are confirmed present and 32-bit; likely
  candidates (unverified) are a round number and/or a result/winner code.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: field_10
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed present/width; semantic meaning not confirmed - unverified guess: round number."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; semantic meaning not confirmed - unverified guess: result/winner code."
