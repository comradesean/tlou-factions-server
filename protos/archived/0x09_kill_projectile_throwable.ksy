meta:
  id: kill_projectile_throwable
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 9. Single-field payload: a throwable/projectile
  entity handle.

  STATUS: confirmed structurally and semantically, high confidence.
  Deserialize (FUN_00410b40, 0x00410b40) / Serialize (FUN_00410a78,
  0x00410a78):
    Read32(&throwable_id);   // offset 0x10, via FUN_00a1b3c8
  Execute (FUN_00413514, 0x00413514) resolves throwable_id via
  FUN_009ef28c (a dynamic-object registry lookup, the same helper used by
  opcode 109/sync_proxy_mine for its own entity handle), then - after a
  per-match capability-bit check - calls FUN_006ad9d4(resolved_object), a
  despawn/kill-style call, directly confirming the field.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: throwable_id
    type: b32
    doc: "32-bit throwable/projectile entity handle (object offset 0x10). Confirmed: resolved via FUN_009ef28c then passed to FUN_006ad9d4 (despawn/kill) on Execute."
