meta:
  id: start_connection
  endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 0. Confirmed EMPTY payload - carries no fields beyond
  the shared per-event wire envelope (continuation bit + opcode byte, see
  docs/protocol/net_event_dispatch_and_simple_opcodes.md section 2).

  STATUS: confirmed, high confidence. The allocator trampoline for this
  opcode (0x0038ee0c) constructs a 0x10-byte object inline (just the common
  NetEvent header, no extra fields). Its Deserialize (FUN_00388a2c,
  0x00388a2c) and Serialize (FUN_00388a30, 0x00388a30) vtable methods are
  both literal `{ return; }` - zero bits read/written. Execute
  (FUN_0038c58c, 0x0038c58c) calls FUN_0034b208, a connection-init hook
  unrelated to wire content.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq: []
