meta:
  id: heartbeat_line
  title: heartbeat-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server (request), server-to-client (unparsed ack)

  The custom ND `heartbeat-server` sub-protocol, a member of the 0x11
  sibling-server family: same connect + 88-byte hello carrying the service name
  "heartbeat-server" + 8-byte reply whose byte[0] is 0x22 (see
  0x11_heartbeat_server_hello.ksy / _response.ksy), on the same ip:port as
  ticket-server. AFTER the hello, the payload is wrapped in the shared
  encrypt-then-MAC 0x33 frame (magic 0x33, pad, BE u16 plaintext_len, 16-byte
  tag, ciphertext - see docs/protocol/0x11_ticket_server_hello.md and
  server/lib/ticket_cipher.py, keyed by the per-connection rolling counter).
  THIS spec models the DECRYPTED PLAINTEXT.

  Single round trip (Ghidra FUN_00353cd8): build one status line via snprintf
  (FUN_00e46560, 254-byte buffer) @ 0x353da0, send (FUN_00acd5f8) @ 0x353dc0,
  one bounded 256-byte recv (FUN_00acd568) @ 0x353dd4, close (FUN_00acbad0) @
  0x353de0. Reads like a periodic matchmaking presence/keepalive ping on its
  own PPU thread.

  REQUEST (client->server, one NUL-terminated ASCII line, space-delimited, NO
  trailing '\n'; note the literal DOUBLE space before "headset"):
    <npid> heartbeat <session_id>  headset <d> party <d> match_mode <d> gametype <d> nat <d> playlist <d>
  Verbatim format string @ research/strings/strings_ascii.txt file offset
  0xe6a030 (VMA 0xe7a030):
    "%s heartbeat %s  headset %d party %d match_mode %d gametype %d nat %d playlist %d"
  1st %s = sender identity (player NpId, by analogy to leaderboard-update;
  medium confidence). 2nd %s = secondary session/party/match token (inferred;
  low-medium). The two %s runtime values are TOC/data-section pointers not
  resolvable from the code-only disasm this pass.

  RESPONSE (server->client): a single bounded 256-byte recv that the client does
  NOT parse (no response-parse loop in FUN_00353cd8) - any bytes satisfy it,
  so there is no structured response to model.

  STATUS: heartbeat-server is NOT yet handled in server/ticket_server.py
  (handle() branches only on leaderboard-server and facebook-server; a heartbeat
  connection currently falls through to the ticket path) and no heartbeat frame
  has been captured live - the format string is verified verbatim but the field
  meanings and the encrypted round trip are unconfirmed against a real session.

  Evidence: strings_ascii.txt 0xe6a030 (fmt), 0xe6a0e8 ("heartbeat-server"),
  0xe6a100 ("heartbeat %s"); Ghidra FUN_00353cd8 (research/ghidra/
  sibling_servers_report.txt); research/disasm/full.asm 0x353cd8..0x353e30;
  docs/protocol/0x11_sibling_servers_family.md (heartbeat-server section).
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: request
    type: str
    terminator: 0
    eos-error: false
    doc: |
      One heartbeat status line. Tokenize on space (note the empty token from
      the double space before "headset"). Layout: <npid> "heartbeat"
      <session_id> "headset" <int> "party" <int> "match_mode" <int> "gametype"
      <int> "nat" <int> "playlist" <int>. All ints are decimal ASCII.
