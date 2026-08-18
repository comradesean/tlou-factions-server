meta:
  id: netmatchmaking_server_hello
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

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
  identical to ticket-server's, at a second rodata address). The remaining two
  fields (reserved_4, reserved_c) are PROVEN never-read (2026-08-18): the reply
  lands at r1+120 (16-byte recv, `bl 0xacbd98` @ 0xad74fc), and Init loads only
  `lwz r0,120(r1)` (opcode, @0xad7510) and `lwz r0,128(r1)` (session_seed,
  @0xad7534); 124(r1) and 132(r1) are never loaded.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "MUST equal 0x12e (302 decimal) = NetMatchmakingServerHello's own numeric ID, or Init() treats this as a fatal handshake failure (closes the connection, Init() returns -1) - confirmed via `if (local_a8[0] == 0x12e) {...} else { close; fail }` in FUN_00ad71a0's decompile. Passed through FUN_00ad55d8 before this check, which this project previously described as a byte-order-fixup - now decompiled and confirmed to be composed entirely of calls to the no-op FUN_00a0e324, so this and every other field in this message is plain big-endian, no runtime swap involved. See research/notes/2026-08-15-byteswap-helper-is-a-noop.md."
  - id: reserved_4
    type: u4
    doc: "Offset 4:8. Server-authored u32 the client NEVER reads (124(r1) never loaded; proven 2026-08-18). Sits on a u32 boundary between opcode and session_seed, so likely a reserved/expansion slot rather than alignment padding, though that intent isn't determinable client-side. Send 0. (Was `unknown1`.)"
  - id: session_seed
    type: u4
    doc: "Passed directly as the counter/seed argument to FUN_00db5ec0 - the EXACT SAME key-schedule function that keys ticket-server's ARX stream cipher (docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section), here combined with a static 16-byte key confirmed byte-for-byte identical to ticket-server's own key (see docs/known-keys.md). Directly analogous to ticket-server message B's session_token field: a server-chosen per-connection counter the client will use to key everything it decrypts/verifies from this point on. A server implementation MUST track whatever value it sends here the same way ticket-server's session_token/client_nonce counters are tracked."
  - id: reserved_c
    type: u4
    doc: "Offset 12:16. Final u32 of the 16-byte reply. Server-authored, the client NEVER reads it (132(r1) never loaded; proven 2026-08-18). Likely a reserved/expansion slot (u32-aligned). Send 0. (Was `unknown2`.)"
