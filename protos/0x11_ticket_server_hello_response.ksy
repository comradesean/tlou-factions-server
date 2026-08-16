meta:
  id: ticket_server_hello_response
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  Server's reply to the 88-byte ticket_server_hello message, on the same TCP
  connection. Fixed size, 8 bytes.

  STATUS: confirmed structurally (which bytes the client reads, and exactly
  what it validates before treating the connection as good) via decompilation
  and raw disassembly of FUN_00acc424 (0x00acc424). Field *semantics* beyond
  the magic-byte check are unconfirmed, because no real ticket-server response
  has ever actually been captured (our stand-in TCP catcher never implemented
  this protocol correctly - see research/notes/ticket-server-first-capture.md
  and docs/protocol/0x11_ticket_server_hello.md). This schema is a projection
  of what the client's own receive/validate code proves it requires, not a
  transcription of an observed example.
doc-ref: ../docs/protocol/0x11_ticket_server_hello.md
seq:
  - id: ack_magic
    type: u1
    doc: "MUST equal 0x22 ('\"', 34 decimal) or the client immediately aborts (closes the socket, fails NetInit with an error) - confirmed by `lbz r0,...; cmpwi r0,34; beq` in FUN_00acc424 right after the 8-byte recv completes. This is the only byte of the response the client actually validates before proceeding."
  - id: unknown1
    size: 3
    doc: "Read into the client's receive buffer but never inspected by the validating function (no compare/branch touches these bytes in FUN_00acc424) - unconfirmed whether truly ignored or consumed by code elsewhere. Best-guess placeholder only; do not assume any particular meaning."
  - id: session_token
    type: u4
    doc: "Stored into the connection object at offset +0x50 (`*(u32*)(conn+0x50) = value`) immediately after the magic-byte check passes - confirmed by an explicit `lwz r0,116(r1); stw r0,80(r18)`. RESOLVED, CONFIRMED HIGH CONFIDENCE (2026-08-14 follow-up pass, corrected after an earlier wrong conclusion in this same pass): this is NOT a dead/write-only field - it is the initial value of a per-connection, per-frame rolling key/counter used by a custom encrypt-then-MAC frame format applied to every message AFTER the hello/hello_response exchange (ticket_server_ticket_submit and its response, and by extension the equivalent post-hello messages on every sibling *-server connection, since they share the same encoder FUN_00acb6fc). Traced via raw disassembly of FUN_00acb6fc (0x00acb6fc, the real frame-builder invoked by the FUN_00acd5f8 send wrapper - the decompiler had silently dropped FUN_00acd5f8's buffer/length parameters, which is what caused the earlier wrong 'dead field' conclusion): each outbound frame reads *(conn+0x50), uses it as a key input (alongside a static 16-byte table embedded in the binary) to a custom ARX mixing construction (FUN_00db5ec0 -> FUN_00db7f88/FUN_00db7c80 -> FUN_00db5e50) that produces a 16-byte authentication tag over the plaintext and a keystream that XOR-encrypts the plaintext in place (FUN_00db7cb0), then increments *(conn+0x50) by 1 (`*(int*)(conn+0x50) += 1`) for the next frame. See the new 'Encrypted frame layer' section in docs/protocol/0x11_ticket_server_hello.md for the full trace and a byte-exact match against a real 272-byte live capture. Practical implication: any server MUST track this per-connection counter (seeded by whatever value it sends here) to produce frames the client will decrypt/verify correctly - it is not an arbitrary/ignorable value."
