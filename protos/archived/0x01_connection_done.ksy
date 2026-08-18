meta:
  id: connection_done
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 1. Fixed 3-field payload: a 1-bit bool followed by
  two 32-bit values, all bit-packed (no byte alignment/padding between them).

  STATUS: confirmed structurally, high confidence on type/width; medium
  confidence on field semantics. Deserialize (FUN_0038911c, 0x0038911c) /
  Serialize (FUN_00388fd0, 0x00388fd0):
    ReadBool(&success);   // offset 0x10
    Read32(&val1);        // offset 0x14, via FUN_00a1ae90
    Read32(&val2);        // offset 0x18, via FUN_00a1ae90
  Execute (FUN_0038c554, 0x0038c554) calls FUN_0035199c(success, val1, val2),
  which formats val1/1024 and val2/1000 into what looks like a log/debug
  string call (FUN_00e46460) - suggestive of "bytes transferred (shown as
  KB)" and "elapsed time in ms (shown as seconds)" but not proven (no
  format-string text was traced to confirm the labels).
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: success
    type: b1
    doc: "1-bit bool. Confirmed field (ReadBool at object offset 0x10); whether this represents connection success vs. failure is a naming inference from the opcode name, not independently proven."
  - id: value1
    type: b32
    doc: "32-bit value (object offset 0x14). Hypothesis (medium confidence, from Execute dividing it by 1024 for a log call): bytes transferred during connection setup."
  - id: value2
    type: b32
    doc: "32-bit value (object offset 0x18). Hypothesis (medium confidence, from Execute dividing it by 1000 for a log call): elapsed connection time in milliseconds."
