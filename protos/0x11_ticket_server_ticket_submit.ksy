meta:
  id: ticket_server_ticket_submit
  endian: be
  license: CC0-1.0
doc: |
  Second client->server message on the SAME ticket-server TCP connection,
  sent immediately after a valid ticket_server_hello_response is received (no
  reconnect). Carries the raw NP ticket RPCN already issued via
  sceNpManagerRequestTicket2 / sceNpManagerGetTicket, wrapped in a shared
  encrypt-then-MAC frame format (NOT a plain 2-byte-length-prefix + raw bytes
  as an earlier pass of this schema wrongly assumed - see below).

  STATUS: CORRECTED AND CONFIRMED HIGH CONFIDENCE (2026-08-14, second
  follow-up pass this session). The original version of this schema
  ("2-byte BE ticket_length, then that many raw ticket bytes, no further
  wrapping") was DISPROVEN by the first-ever live capture of this message: a
  real 272-byte client send whose first two bytes read as a bogus 13058-byte
  length under the old schema, which cannot be reconciled with a 272-byte
  total message under any endianness. Tracing the actual send path
  (FUN_00acd5f8 -> FUN_00acb6fc, 0x00acb6fc) - not the orchestrator
  FUN_003557a8 alone, whose decompile of the send call had its buffer/length
  arguments silently dropped by the decompiler, which is what produced the
  wrong original schema - shows the client wraps EVERY message sent by this
  helper (ticket_server_ticket_submit here; the analogous post-hello payload
  on every sibling *-server connection, since they share this same encoder)
  in a fixed 20-byte header + an encrypted, padded copy of the plaintext:

  ```
  offset 0      u1   frame_magic   = 0x33 (fixed literal, always this value)
  offset 1      u1   pad_count     = (-plaintext_len) & 3   (0..3, pads ciphertext to a multiple of 4)
  offset 2      u2   plaintext_len = length of the UNENCRYPTED payload (BE)
  offset 4      16B  auth_tag      = keyed digest over the plaintext (see below)
  offset 20     N    ciphertext    = plaintext_len + pad_count bytes, XOR-keystream-encrypted in place
  ```

  Confirmed BYTE-EXACT against the real 272-byte capture (session
  2026-08-14T08:11, `captures/tcp_catch.log`): raw bytes began `33 02 00 fa
  ...` -> magic=0x33 (matches), pad_count=2, plaintext_len=0x00fa=250.
  20 (header) + 250 + 2 (padding) = 272 - exactly the captured total. The
  pad_count formula `(-250) & 3 == 2` also matches independently. This is
  about as strong a confirmation as static analysis + one live capture can
  produce without a working decrypt implementation.

  The key/counter for THIS direction (client->server) is
  ticket_server_hello_response's session_token field (conn+0x50), which the
  client increments by 1 after every frame it sends on this connection - see
  protos/0x11_ticket_server_hello_response.ksy and the "Encrypted frame
  layer" section of docs/protocol/0x11_ticket_server_hello.md.

  UPDATE (2026-08-14, fourth pass): SOLVED. The ARX (add-rotate-xor)
  construction across FUN_00db5ec0/FUN_00db7f88/FUN_00db7c80/FUN_00db5e50/
  FUN_00db7cb0 is reimplemented in `tools/ticket_cipher.py` and now
  correctly decrypts this real capture - the static key was independently
  confirmed via a live RPCS3 memory read (matching the statically-resolved
  candidate byte-for-byte), which isolated the remaining bug to this
  module's own reconstruction of FUN_00db5ec0's finalization round (found
  and fixed via ground-truth Ghidra emulation, see the doc's "Encrypted
  frame layer" section for the full diagnosis). `decrypt_frame()` now
  passes its own auth_tag check and recovers a plaintext containing the
  literal strings "UP9000-BCUS98174_00" (this title's content ID) and
  "comradesean" (very likely the player's online ID) - a genuine, verified
  NP ticket.
doc-ref: ../docs/protocol/0x11_ticket_server_hello.md
seq:
  - id: frame_magic
    type: u1
    doc: "Fixed literal 0x33 ('3') - confirmed via `li r0,0x33; stb r0,0(dest)` in FUN_00acb6fc's encoder AND via the receiver FUN_00acbb90's `if (*pcVar3 == '3')` gate (any other value -> the connection is treated as fatally desynced and closed). Matches the real capture's first byte exactly."
  - id: pad_count
    type: u1
    doc: "Number of zero(?)-padding bytes appended after the plaintext so the ciphertext region is a multiple of 4 bytes, computed by the client as `(-plaintext_len) & 3`. Confirmed via disassembly (`neg r0,len; rlwinm r0,r0,0,0x1e,0x1f`) and matches the real capture (plaintext_len=250 -> pad_count=2, i.e. (-250)&3=2)."
  - id: plaintext_len
    type: u2
    doc: "Length of the ORIGINAL UNENCRYPTED payload (the raw NP ticket bytes here), big-endian - NOT the on-wire ciphertext length. Confirmed via disassembly (`sth len,...`) and matches the real capture (0x00fa = 250, plausible for an NP ticket; an earlier RPCS3 log line from an unrelated session observed 248, so ticket size legitimately varies run-to-run)."
  - id: auth_tag
    size: 16
    doc: "Keyed authentication tag over the plaintext, computed by the client's encoder (FUN_00db5ec0 keystream-init + FUN_00db7f88 digest + FUN_00db5e50 finalize) and independently RECOMPUTED and compared by the client's own decoder (FUN_00acbb90) whenever IT receives a frame from the server - meaning ticket_server_ticket_submit_response (message D) must carry a tag the client will recompute and verify, or the client closes the connection. Keyed by the session_token counter (this direction) + a static 16-byte table embedded in the client binary (both confirmed live - see doc). CONFIRMED WORKING: tools/ticket_cipher.py recomputes this tag and it matches the real capture's embedded tag exactly."
  - id: ciphertext
    size: plaintext_len + pad_count
    doc: "The plaintext (raw NP ticket bytes) plus pad_count padding bytes, encrypted in place via a keystream produced by the same ARX construction as auth_tag (FUN_00db7cb0 - identical math to FUN_00db7f88's digest pass but writes the mixed state back over the buffer instead of only accumulating it). CONFIRMED WORKING: tools/ticket_cipher.py decrypts this and recovers a real NP ticket (contains \"UP9000-BCUS98174_00\" and \"comradesean\" in plaintext, with consistent Sony TLV structure) - the first plaintext_len bytes are the raw NP ticket exactly as sceNpManagerGetTicket returned it."
