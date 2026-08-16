meta:
  id: npc_set_host
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 95. 3-field payload: a 13-bit requester id, a full
  32-bit npc id, and a bool.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium-high. Deserialize (FUN_00402dcc, 0x00402dcc) / Serialize
  (FUN_00402bcc, 0x00402bcc):
    ReadBits(&requester_id, 13);   // offset 0x10
    ReadBits(&npc_id, 32);          // offset 0x14 (same generic
                                     // ReadBits(32) form as npc_kill's
                                     // own npc id field)
    ReadBool(&is_host);             // offset 0x18
  Execute (FUN_00403df4, 0x00403df4) loops the local player table looking
  for a slot whose resolved id matches requester_id (offset 0x10) to
  determine whether the local machine is the requester - i.e. requester_id
  is compared against local connection slots, not looked up in a generic
  object registry. Separately resolves npc_id (offset 0x14) via
  FUN_0039e0c8 (the npc registry, matching npc_kill's usage), then calls
  FUN_00090058(npc, is_local_match) and FUN_00090074(npc, is_host) -
  directly confirms is_host's role and reinforces the "npc ids are a full
  32-bit ReadBits(32) field" cross-opcode pattern from npc_kill.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: requester_id
    type: b13
    doc: "13-bit id (object offset 0x10). Confirmed: compared against local player-table slots on Execute (not a generic registry lookup) to determine whether the local machine issued the request."
  - id: npc_id
    type: b32
    doc: "32-bit npc id (object offset 0x14), read via the generic ReadBits(32) form. Confirmed: resolved via FUN_0039e0c8 (npc registry) on Execute, matching npc_kill's own npc-id field encoding."
  - id: is_host
    type: b1
    doc: "Bool (object offset 0x18). Confirmed: passed directly to FUN_00090074(npc, is_host) on Execute, directly matching the opcode name."
