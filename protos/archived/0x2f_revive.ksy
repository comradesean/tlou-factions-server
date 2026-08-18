meta:
  id: revive
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 47. 4-field, bit-packed payload with a variable-width
  target-id field (13 or 32 bits, selected by a preceding bool) - the same
  "optional compact id" idiom also seen in opcode 81 (reset_melee_history);
  see docs/protocol/net_event_dispatch_and_simple_opcodes.md section 5 for
  the cross-opcode discussion.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium confidence. Deserialize (FUN_003d8730, 0x003d8730) / Serialize
  (FUN_003d8608, 0x003d8608):
    target_is_compact = ReadBool();                          // offset 0x18
    target_id = ReadBits(target_is_compact ? 13 : 32);        // offset 0x10
    reviver_id = ReadBits(13);                                // offset 0x14
    extra_flag = ReadBool();                                  // offset 0x19
  Execute (FUN_003d9ee4, 0x003d9ee4) branches on target_is_compact (offset
  0x18) between two different object-lookup helpers for the target_id field
  (FUN_0039e0c8 vs FUN_0039f3d8 - consistent with "compact index" vs "full/
  explicit id" resolution), resolves reviver_id similarly, and updates a
  small "recent revivers" list plus a stat-increment call
  (FUN_008aee5c(..., 6 or 7)) whose code selector is extra_flag (offset
  0x19) - suggestive of a solo-revive vs revive-assist distinction, not
  independently confirmed.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: target_is_compact
    type: b1
    doc: "Bool (object offset 0x18). Confirmed: selects target_id's wire width (13 vs 32 bits) and which of two lookup helpers Execute uses to resolve it. Read first on the wire despite being object offset 0x18 (after target_id/reviver_id in memory)."
  - id: target_id_compact
    type: b13
    if: target_is_compact == true
    doc: "13-bit target id (object offset 0x10), present when target_is_compact is set. Confirmed: resolved via FUN_0039f3d8 in Execute, matching the common 13-bit player/entity-index scheme used elsewhere in this opcode family."
  - id: target_id_full
    type: b32
    if: target_is_compact == false
    doc: "32-bit target id (object offset 0x10), present when target_is_compact is clear. Confirmed: resolved via FUN_0039e0c8 (a different lookup helper than the compact case) in Execute; exact reason a full-width id is needed here (vs. the 13-bit common case) not disambiguated."
  - id: reviver_id
    type: b13
    doc: "13-bit reviver id (object offset 0x14). Confirmed present/width (fixed ReadBits(13), no conditional); Execute resolves it the same way as other 13-bit ids in this family. Semantics (the reviving player) inferred from opcode name, not independently traced."
  - id: extra_flag
    type: b1
    doc: "Bool (object offset 0x19). Confirmed present/width; Execute uses it to pick between two code paths that both end in a stat-increment call with different codes (6 vs 7) - hypothesis: solo-revive vs revive-with-assist, not confirmed."
