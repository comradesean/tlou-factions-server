meta:
  id: increment_score
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 102. 3-field payload: a 13-bit id, and two 32-bit
  fields.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium. Deserialize (FUN_00409764, 0x00409764) / Serialize
  (FUN_0040963c, 0x0040963c):
    ReadBits(&id, 13);       // offset 0x10
    Read32(&field_14);       // offset 0x14, via FUN_00a1ae90
    Read32(&score_delta);    // offset 0x18, via FUN_00a1ae90
  Execute (FUN_0040c8bc, 0x0040c8bc) branches on id (offset 0x10): if
  zero, calls FUN_003e6e0c(score_mgr, field_14, score_delta) directly (a
  team-level increment, no player lookup needed); if nonzero, resolves a
  player via FUN_0039f3d8 and calls FUN_003ea190(score_mgr, player,
  score_delta) - notably NOT passing field_14 in this branch. score_delta
  (offset 0x18) is consistently the score-tracker's amount argument in
  both branches, confirming its role; field_14's role is only used in the
  id==0 (team) branch and not disambiguated.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: id
    type: b13
    doc: "13-bit id (object offset 0x10). Confirmed: 0 selects a team-level score-increment path, nonzero is resolved as a player id via FUN_0039f3d8, on Execute."
  - id: field_14
    type: b32
    doc: "32-bit value (object offset 0x14). Confirmed present/width; only consumed in the id==0 (team) branch of Execute, not the player branch - role not disambiguated."
  - id: score_delta
    type: b32
    doc: "32-bit score delta (object offset 0x18). Confirmed: passed as the score-tracker's amount argument in both Execute branches."
