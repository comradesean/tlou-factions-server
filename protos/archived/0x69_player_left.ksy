meta:
  id: player_left
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 105. Single-field payload: a 13-bit player id.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_004096b0, 0x004096b0) / Serialize (FUN_00409590,
  0x00409590):
    ReadBits(&player_id, 13);   // offset 0x10
  Execute (FUN_0040c5b4, 0x0040c5b4) resolves player_id via FUN_0039f3d8
  twice - once directly, once at `player_id + 0x1000` (a "primary slot"
  vs. "shadow/spectator slot" addressing scheme) - and for each resolved
  object calls FUN_003d0210 (cleanup) then invalidates a +0x3c0 field
  (sets it to -1). Directly consistent with the opcode name (per-player
  cleanup on disconnect).
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: player_id
    type: b13
    doc: "13-bit player id (object offset 0x10). Confirmed: resolved via FUN_0039f3d8 on Execute (both directly and at player_id+0x1000, a primary/shadow-slot scheme), each triggering a cleanup call and a field invalidation."
