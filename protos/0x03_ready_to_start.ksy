meta:
  id: ready_to_start
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 3. Fixed 2-field, bit-packed payload: a 12-bit player
  index followed immediately by a 1-bit ready flag (no padding).

  STATUS: confirmed, high confidence on both type and semantics. Deserialize
  (FUN_00389a40, 0x00389a40) / Serialize (FUN_00389930, 0x00389930):
    player_id = ReadBits(12);   // offset 0x10
    ready = ReadBool();          // offset 0x14
  Execute (FUN_0038c5b0, 0x0038c5b0) loops over 8 player slots, matches
  player_id against each slot's stored id at slot+0x1a8, then on match sets
  one of two adjacent flag bytes (slot+0x3fc / slot+0x3fd) depending on
  whether ready is true or false - textbook "this player toggled their
  ready-up state" handling, matching the opcode name exactly. This is likely
  one of the very first gameplay-layer events a minimal server
  implementation needs to handle correctly.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b12
    doc: "12-bit unsigned player/client index. Confirmed via Execute's 8-slot lookup loop matching this value against each connected player's stored id."
  - id: ready
    type: b1
    doc: "1-bit ready flag. Confirmed via Execute setting one of two distinct 'ready'/'not ready' state bytes depending on this value."
