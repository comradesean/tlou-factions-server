meta:
  id: reset_melee_history
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 81. 2-field, bit-packed payload using the same
  "optional compact id" idiom as opcode 47 (revive): a bool selects whether
  the following id is 13 or 32 bits wide.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium confidence. Deserialize (FUN_003ff20c, 0x003ff20c) / Serialize
  (FUN_003ff198, 0x003ff198):
    target_is_compact = ReadBool();                      // offset 0x10
    target_id = ReadBits(target_is_compact ? 13 : 32);    // offset 0x14
  Execute (FUN_00400ad4, 0x00400ad4) resolves target_id via
  FUN_0039f3d8 (nonzero id path) or FUN_0039e0c8 (fallback), matching
  revive's exact same two-lookup-helper split keyed on the same bool, then
  calls a "clear melee history" virtual method (vtable+0x3b4) via
  FUN_005ab5e8 - directly consistent with the opcode name.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: target_is_compact
    type: b1
    doc: "Bool (object offset 0x10). Confirmed: selects target_id's wire width and which lookup helper Execute uses, identical pattern to revive's target_is_compact."
  - id: target_id_compact
    type: b13
    if: target_is_compact == true
    doc: "13-bit target id (object offset 0x14), present when target_is_compact is set. Confirmed: resolved via FUN_0039f3d8, then passed to the melee-history-clear virtual call."
  - id: target_id_full
    type: b32
    if: target_is_compact == false
    doc: "32-bit target id (object offset 0x14), present when target_is_compact is clear. Confirmed: resolved via FUN_0039e0c8 instead, then passed to the same melee-history-clear virtual call."
