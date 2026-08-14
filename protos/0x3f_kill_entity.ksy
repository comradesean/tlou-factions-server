meta:
  id: kill_entity
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 63. Single-field payload, one 32-bit entity handle.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_0038a854, 0x0038a854) / Serialize (FUN_0038a58c,
  0x0038a58c):
    Read32(&entity_id);   // offset 0x10, via FUN_00a1b3c8
  Execute (FUN_0038b6c4, 0x0038b6c4) resolves it via FUN_007b49dc (the same
  entity-handle-to-object lookup used by spawn_entity/coop_team_failed) then
  calls a virtual method at the resolved object's vtable+0x210 - the
  "kill this entity" call.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: entity_id
    type: b32
    doc: "32-bit entity handle (object offset 0x10). Confirmed: resolved via FUN_007b49dc then a kill-style virtual call is made on the resolved object."
