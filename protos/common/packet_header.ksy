meta:
  id: packet_header
  endian: be
  license: CC0-1.0
  imports:
    - opcodes
doc: |
  Outer packet envelope. STATUS: unconfirmed skeleton, not a real parser yet.

  Evidence for a sequence-number field: the string
  "notify->packetSequenceNumber == m_highestAckedSequence + i + 1"
  (EBOOT.elf offset 0xec7d40, source ndlib/net/net-phase-snapshot.cpp) confirms
  a reliable, sequenced/acked transport layer exists above raw sockets. It does
  NOT confirm this field's wire width, position, or whether it's even part of
  every packet type vs. only phase/reliable snapshot packets specifically.

  Field widths/order below are placeholders pending confirmation from
  decompiled serialization code (docs/ghidra-setup.md) or a live capture.

  Update (session 1, Ghidra): NetEventType numeric IDs are now confirmed
  (see protos/common/opcodes.ksy) and range 0-114, comfortably fitting a
  single byte. Two functions that read a queued network event's type before
  looking up its debug name (FUN_00ace694 @ 0x00ace694, FUN_00acecd0 @
  0x00acecd0) do so via an explicit 1-byte load: `*(undefined1 *)(*node + 4)`.
  This corroborates - but does not prove - a u1 opcode field: it's evidence
  about the in-process queue-node representation, not a confirmed wire
  format. Still `opcode: u1` below, now medium- rather than low-confidence.
doc-ref: ../../docs/protocol/README.md
seq:
  - id: sequence_number
    type: u4
    doc: "Hypothesis only - see meta doc. Reliable-transport sequence number."
  - id: opcode
    type: u1
    enum: opcodes::net_event_type
    doc: "Medium confidence: NetEventType id (see opcodes.ksy), corroborated as 1 byte by in-process queue-node reads. Position/whether every packet type uses this exact header is still unconfirmed."
