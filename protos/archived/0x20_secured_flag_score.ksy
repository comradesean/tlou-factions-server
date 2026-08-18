meta:
  id: secured_flag_score
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 32. 2-field payload: a score value and a 13-bit
  team id.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_003f6b5c, 0x003f6b5c) / Serialize (FUN_003f6948,
  0x003f6948):
    Read32(&score_value);      // offset 0x10, via FUN_00a1af50
    ReadBits(&team_id, 13);    // offset 0x14
  Execute (FUN_003f7020, 0x003f7020) resolves team_id via FUN_0039f3d8
  (the same team-lookup helper confirmed elsewhere in this family), then
  passes score_value straight into FUN_003ea190(score_tracker, team,
  score_value) - directly confirms both fields' roles.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: score_value
    type: b32
    doc: "32-bit score value (object offset 0x10). Confirmed: passed directly to the score-tracker call on Execute."
  - id: team_id
    type: b13
    doc: "13-bit team id (object offset 0x14). Confirmed: resolved via FUN_0039f3d8, matching the established team_id pattern, then used as the score-tracker's team argument."
