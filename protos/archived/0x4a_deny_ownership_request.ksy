meta:
  id: deny_ownership_request
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 74. Single-field payload, one 32-bit value.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  partially confirmed. Deserialize (FUN_0038958c, 0x0038958c) / Serialize
  (FUN_00389274, 0x00389274):
    Read32(&target_id);   // offset 0x10, via FUN_00a1af50
  Execute (FUN_0038c740, 0x0038c740) resolves it via FUN_0039f3d8 - the
  same small per-match table lookup used for team_id in spawn_entity/
  coop_team_failed (so this may be a team or ownership-request-target id
  rather than a raw entity id, not disambiguated) - and sets a pending-deny
  flag (+0x401 = 1) on the result.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: target_id
    type: b32
    doc: "32-bit value (object offset 0x10). Confirmed resolved via FUN_0039f3d8 (the same lookup used for team_id elsewhere) on Execute, which then sets a pending-deny flag on the result - likely the ownership-request target, exact identity (team vs. other) not disambiguated."
