meta:
  id: npc_kill
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 39. 2-field payload: a full 32-bit npc id (read via
  the generic ReadBits(32) form rather than one of the dedicated Read32
  call sites) and a second 32-bit field.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  low-medium (Execute logic is unusually convoluted for this pass to fully
  resolve). Deserialize (FUN_0040375c, 0x0040375c) / Serialize
  (FUN_00402c40, 0x00402c40):
    ReadBits(&npc_id, 32);   // offset 0x10
    Read32(&field_14);        // offset 0x14, via FUN_00a1b3c8 (the same
                               // call site confirmed elsewhere for entity
                               // handles, e.g. spawn_entity/kill_entity)
  Execute (FUN_00403ca0, 0x00403ca0) resolves npc_id via FUN_0039e0c8 (an
  npc-registry lookup) and does further virtual-call/validation logic
  including an exception-trap path on mismatch; field_14 is compared
  against a resolved value's +0x24 field rather than being used as a
  direct lookup key. The exact roles are not confidently disambiguated
  this pass. Note: opcode 95 (npc_set_host) also uses the ReadBits(32)
  form for its own npc-id field, suggesting NPCs are consistently
  addressed with a full 32-bit id distinct from the common 13-bit
  player/entity-index scheme used elsewhere.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: npc_id
    type: b32
    doc: "32-bit npc id (object offset 0x10), read via the generic ReadBits(32) form. Confirmed: resolved via FUN_0039e0c8 (npc registry) on Execute. Cross-opcode note: npc_set_host (opcode 95) uses the same ReadBits(32) form for its own npc id."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14), read via FUN_00a1b3c8 (the entity-handle call site seen elsewhere). Confirmed present/width; compared against a resolved object's +0x24 field in Execute rather than used as a lookup key itself - role not confirmed."
