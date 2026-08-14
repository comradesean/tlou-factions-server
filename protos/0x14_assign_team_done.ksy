meta:
  id: assign_team_done
  endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 20. Confirmed EMPTY payload - carries no fields
  beyond the shared per-event wire envelope, same pattern as
  start_connection (opcode 0) and net_go (opcode 75).

  STATUS: confirmed, high confidence. Deserialize (FUN_00388a34,
  0x00388a34) and Serialize (FUN_00388a38, 0x00388a38) are both literal
  `{ return; }`. Execute (FUN_0038dcf4, 0x0038dcf4) is a substantial
  match-flow-progression function (checks/sets several match-state flags,
  e.g. distinguishing intermission/results states) consistent with "team
  assignment phase complete, proceed" being a pure signal with no payload.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq: []
