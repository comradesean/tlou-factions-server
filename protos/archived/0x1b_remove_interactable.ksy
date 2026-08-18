meta:
  id: remove_interactable
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 27. Single-field payload: an interactable id.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_0040586c, 0x0040586c) / Serialize (FUN_0040583c,
  0x0040583c):
    Read32(&interactable_id);   // offset 0x10, via FUN_00a1b3c8
  Execute (FUN_0040664c, 0x0040664c) passes interactable_id straight into
  FUN_003ac8a8(interact_ctx, interactable_id, 1) - a single-call removal
  function, directly confirming the field and matching the opcode name.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: interactable_id
    type: b32
    doc: "32-bit interactable id (object offset 0x10). Confirmed: passed directly to FUN_003ac8a8's removal call on Execute."
