meta:
  id: packet_header
  endian: be
  license: CC0-1.0
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
doc-ref: ../../docs/protocol/README.md
seq:
  - id: sequence_number
    type: u4
    doc: "Hypothesis only - see meta doc. Reliable-transport sequence number."
  - id: opcode
    type: u1
    doc: "Hypothesis only. Width (u1 vs u2) and whether this maps to NetEventType or something else entirely is unconfirmed."
