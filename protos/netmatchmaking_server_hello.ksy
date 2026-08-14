meta:
  id: netmatchmaking_server_hello
  endian: be
  license: CC0-1.0
doc: |
  Server's reply to netmatchmaking_client_hello, on the same new TCP
  connection (see that schema's doc for the connection setup). Fixed size,
  0x10 (16) bytes. This is the recv() call that fails live with errno=9
  (EBADF) whenever the connection itself never actually succeeded - see
  doc-ref for the full live-capture evidence trail (the connection object's
  socket fd is -1 by the time this recv() runs, meaning the preceding
  connect() silently failed and its failure was never checked).

  STATUS: opcode field confirmed (hard equality check, connection aborted on
  mismatch); one field (session_seed) confirmed as real key material feeding
  the SAME ARX cipher key-schedule function already solved for ticket-server
  (see docs/known-keys.md - the static key itself is confirmed byte-for-byte
  identical to ticket-server's, at a second rodata address). The remaining
  two fields are unconfirmed placeholders - genuinely never read by anything
  this pass traced, not just "not yet looked at closely".
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "MUST equal 0x12e (302 decimal) = NetMatchmakingServerHello's own numeric ID, or Init() treats this as a fatal handshake failure (closes the connection, Init() returns -1) - confirmed via `if (local_a8[0] == 0x12e) {...} else { close; fail }` in FUN_00ad71a0's decompile. Passed through a byte-order-fixup function (FUN_00ad55d8, not decompiled this pass) before this check - same on-wire-endianness caveat as netmatchmaking_client_hello's opcode field applies here too."
  - id: unknown1
    type: u4
    doc: "Declared/received but not read by any branch this pass traced in Init(). Do not assume a meaning."
  - id: session_seed
    type: u4
    doc: "Passed directly as the counter/seed argument to FUN_00db5ec0 - the EXACT SAME key-schedule function that keys ticket-server's ARX stream cipher (docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section), here combined with a static 16-byte key confirmed byte-for-byte identical to ticket-server's own key (see docs/known-keys.md). Directly analogous to ticket-server message B's session_token field: a server-chosen per-connection counter the client will use to key everything it decrypts/verifies from this point on. A server implementation MUST track whatever value it sends here the same way ticket-server's session_token/client_nonce counters are tracked."
  - id: unknown2
    type: u4
    doc: "Final 4 bytes of the 16-byte response. Not read in the portion of Init() traced this pass. Genuinely unconfirmed."
