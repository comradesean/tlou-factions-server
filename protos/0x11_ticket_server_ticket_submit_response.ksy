meta:
  id: ticket_server_ticket_submit_response
  endian: be
  license: CC0-1.0
doc: |
  Server's reply to ticket_server_ticket_submit, on the same connection.
  Uses the SAME encrypt-then-MAC frame format as ticket_server_ticket_submit
  (see that schema's doc for the full frame layout and evidence) - NOT a
  fixed 16 raw bytes, as an earlier pass of this schema wrongly assumed.

  STATUS: CORRECTED (2026-08-14, second follow-up pass this session). The
  receive side was traced via FUN_00acd568 (0x00acd568) -> FUN_00acbb90
  (0x00acbb90, the actual frame decoder - the decompiler had also dropped a
  parameter here, same root cause as the send-side correction; the `0x10`
  literal at the orchestrator's call site, previously read as "confirmed
  16-byte fixed size", is NOT consumed anywhere in FUN_00acbb90's decompiled
  body and its real purpose was not resolved this pass - treat the old
  "confirmed 16 bytes" claim as WITHDRAWN, not just downgraded). FUN_00acbb90
  parses the SAME 20-byte header (frame_magic/pad_count/plaintext_len/
  auth_tag) then decrypts `plaintext_len + pad_count` ciphertext bytes and
  independently recomputes+compares the auth_tag before accepting the frame
  (`_opd_FUN_00e498f0(computed_tag, embedded_tag, 0x10)` - a memcmp; any
  mismatch, or a first byte != 0x33, closes the connection immediately,
  mirroring the send side's magic-byte requirement). This means a server
  MUST build a correctly-keyed, correctly-tagged frame for this message or
  the client will treat it as a fatal desync and drop the connection - an
  all-zero 16-byte reply (what this project's current stub sends) is
  BELIEVED to fail this check, though a connection using it was NOT observed
  to error out mid-handshake in the one live test so far (the client simply
  closed the connection normally afterward - inconclusive on its own,
  since NetInit may have already given up on ticket-server via a different
  code path by that point; needs a real decrypt-side implementation to test
  properly).

  Critically, this message's frame is keyed by a DIFFERENT counter than
  ticket_server_ticket_submit's: FUN_00acbb90 reads/increments
  `*(conn+0x4c)` (the CLIENT's own nonce from ticket_server_hello, NOT
  conn+0x50's session_token) for every frame it decodes. This makes sense
  directionally: conn+0x4c's starting value is CLIENT-chosen and sent to the
  server in cleartext in message A, so the server can derive the correct key
  for ITS OWN replies without needing any secret handshake - symmetric to
  how conn+0x50 (server-chosen, sent in message B) keys the client's sends.

  UPDATE (2026-08-14, fourth pass): the cipher itself is now SOLVED and
  verified against a real message-C capture - see
  protos/0x11_ticket_server_ticket_submit.ksy and the doc's "Encrypted frame
  layer" section. `tools/ticket_cipher.py`'s `encrypt_frame()`, keyed by a
  connection's own client_nonce, now produces a real, self-consistent frame
  (correct magic byte, correct auth_tag - verified by round-tripping it back
  through the module's own decrypt) for this message. The all-zero 16-byte
  reply this project's stub previously sent is essentially confirmed invalid
  now (wrong magic byte at minimum). What remains open is ONLY this
  message's *content* semantics (see plaintext_len/ciphertext fields below) -
  never captured, so still a placeholder/guess even though the wrapper
  around it is now real.
doc-ref: ../docs/protocol/0x11_ticket_server_hello.md
seq:
  - id: frame_magic
    type: u1
    doc: "Fixed literal 0x33 - same check as ticket_server_ticket_submit's frame_magic, this time enforced by the CLIENT's decoder FUN_00acbb90 (`if (*pcVar3 == '3') {...} else { close }`). Confirmed via decompile."
  - id: pad_count
    type: u1
    doc: "Same meaning as ticket_server_ticket_submit's pad_count - padding byte count for the ciphertext region, read back out of the frame header rather than recomputed (the sender is responsible for getting this right; FUN_00acbb90 just uses it to size the ciphertext read)."
  - id: plaintext_len
    type: u2
    doc: "Length of the response's UNENCRYPTED payload, big-endian, self-described by the server (this project's stub, once corrected) rather than dictated by the client. The previously-assumed fixed value of 16 for this message is WITHDRAWN - not confirmed, and the field that looked like a fixed-16-byte recv length at the orchestrator's call site turned out not to be read by the actual frame decoder. True content/expected length: UNKNOWN, not yet observed live (no server has ever sent the client a protocol-legal frame at this point to see how it reacts)."
  - id: auth_tag
    size: 16
    doc: "Keyed tag, independently recomputed by the client via `_opd_FUN_00db5ec0(static_key, *(conn+0x4c), state)` + digest, then compared via memcmp against this field - any mismatch is treated as fatal (FUN_00a0f6b8(conn,2) + FUN_00acbad0(conn), connection closed). Keyed by client_nonce (conn+0x4c), NOT session_token - see doc-level note above."
  - id: ciphertext
    size: plaintext_len + pad_count
    doc: "The response payload, XOR-keystream-decrypted in place by the client via FUN_00db7e08 before the tag is even checked (decrypt-then-verify, not verify-then-decrypt - worth noting for a real implementation, though the end result the client acts on is the same either way since a bad tag closes the connection regardless). Content semantics completely unknown - never captured, never explained by any other code path this or the prior pass could find."
