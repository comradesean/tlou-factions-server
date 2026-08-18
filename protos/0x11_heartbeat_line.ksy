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
  0x353de0. A periodic matchmaking presence/keepalive ping on its own PPU thread.

  DEFINITION / PURPOSE: a liveness beacon. The client periodically tells the
  matchmaking backend "account <online_id> is still online" so the server can
  keep the player in its presence/queue tables and time out stale sessions - the
  administrative reason the message exists. It carries exactly the identity the
  server needs to key that record.

  REQUEST (client->server, one NUL-terminated ASCII line):
    heartbeat <online_id>\n
  CORRECTED 2026-08-18 (was modelled as an 8-token line - WRONG): the real
  heartbeat-server line is the ONE-field format string "heartbeat %s\n" at VMA
  0xe7a100 (GOT slot 0x1268470), built by FUN_00353cd8. Its single %s argument is
  the global at 0x13835e0 = matchmaking-singleton(0x13835c0)+0x20 = the local
  player's SceNpId online-id handle (the same buffer passed to
  sceNpManagerRequestTicket2). LIVE-CONFIRMED in server/logs/ticket_server.log:
  the decrypted plaintext is exactly `heartbeat comradesean\n` (22 bytes =
  "heartbeat "(10) + "comradesean"(11) + "\n"(1)), one conversion, value = the
  PSN online-id.

  NOT this line: the 8-token string at 0xe7a030
  ("%s heartbeat %s  headset %d party %d match_mode %d gametype %d nat %d
  playlist %d") is built by a DIFFERENT function, FUN_00352de8, and written to a
  persistent object (0x1379184) on a different channel - it never reaches the
  heartbeat-server socket. It is a separate presence/status telemetry line; if it
  is ever modelled, note its 2nd %s is a game-STATE word ("menu" / "matchmaking"
  / "playing"), not a session token. Do not present it as the heartbeat request.

  RESPONSE (server->client): a single bounded 256-byte recv that the client does
  NOT parse (no response-parse loop in FUN_00353cd8) - any bytes satisfy it,
  so there is no structured response to model.

  STATUS: request line CORRECTED and LIVE-CONFIRMED against a real captured
  frame (ticket_server.log). heartbeat-server is NOT yet handled in
  server/ticket_server.py (handle() branches only on leaderboard-server and
  facebook-server; a heartbeat connection currently falls through to the ticket
  path, which is what produced the captured decrypted line) - a dedicated
  handler is an open implementation item, not a protocol unknown.

  Evidence: strings_ascii.txt 0xe6a100 ("heartbeat %s"), 0xe6a0e8
  ("heartbeat-server"); Ghidra FUN_00353cd8 (research/ghidra/
  sibling_servers_report.txt); GOT resolved against the real EBOOT.elf
  (fmt=0xe7a100, arg=0x13835e0); live frame in server/logs/ticket_server.log;
  docs/protocol/0x11_sibling_servers_family.md (heartbeat-server section).
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: verb
    type: str
    terminator: 0x20
    eos-error: false
    doc: "The literal ASCII verb \"heartbeat\" followed by one space."
  - id: online_id
    type: str
    terminator: 0x0a
    eos-error: false
    doc: |
      The sender's PSN online-id (account handle), terminated by '\n' then a
      trailing NUL. Source: EBOOT global 0x13835e0 = matchmaking-singleton+0x20
      (the local SceNpId handle). Live-verified value "comradesean". This is the
      key the matchmaking backend uses to refresh the account's presence/liveness
      record.
