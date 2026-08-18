meta:
  id: sync_proxy_mine
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 109. 3-field payload: a mine entity handle and two
  bools.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium for entity_id, low for the two bools.
  Deserialize (FUN_004108b0, 0x004108b0) / Serialize (FUN_0041084c,
  0x0041084c):
    Read32(&entity_id);   // offset 0x10, via FUN_00a1af50
    ReadBool(&flag_a);     // offset 0x14
    ReadBool(&flag_b);     // offset 0x15
  Execute (FUN_0041374c, 0x0041374c) resolves entity_id via FUN_009ef28c -
  the same dynamic-object registry lookup confirmed for opcode 9
  (kill_projectile_throwable) - then, after a hash-keyed capability check,
  makes a telemetry/log call (FUN_009e6a20) that isn't traced further.
  flag_a/flag_b are not visibly consumed in the traced Execute code
  (likely passed to the untraced log call, or an armed/visible state pair
  given the opcode name "sync" - not confirmed).
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: entity_id
    type: b32
    doc: "32-bit mine entity handle (object offset 0x10). Confirmed: resolved via FUN_009ef28c on Execute, same registry-lookup helper as opcode 9's throwable_id."
  - id: flag_a
    type: b1
    doc: "Bool (object offset 0x14). Confirmed present/width; not clearly consumed in the traced Execute code - role unconfirmed."
  - id: flag_b
    type: b1
    doc: "Bool (object offset 0x15). Confirmed present/width; not clearly consumed in the traced Execute code - role unconfirmed."
