meta:
  id: report_line
  title: report-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server (request); response not yet observed.

  The custom ND `report-server` sub-protocol, a member of the 0x11
  sibling-server family: same connect + 88-byte hello carrying the service name
  "report-server" + 8-byte reply whose byte[0] is 0x22 (see the sibling
  *_server_hello.ksy pair, which is byte-identical across services apart from
  the name), on the same ip:port as ticket-server. AFTER the hello the payload
  is wrapped in the shared encrypt-then-MAC 0x33 frame (magic 0x33, pad, BE u16
  plaintext_len, 16-byte tag, ciphertext - see
  docs/protocol/0x11_ticket_server_hello.md and server/lib/ticket_cipher.py).
  THIS spec models the DECRYPTED PLAINTEXT.

  DISCOVERED 2026-08-18 by mining service names out of every captured sibling
  hello (452 hellos in server/logs/ticket_server.log). This is the SIXTH sibling
  service and the only one with no spec until now; the other five are
  ticket-server (62 hellos), facebook-server (72), heartbeat-server (258),
  leaderboard-server (58) and single-player-server. report-server appeared twice.

  DEFINITION / PURPOSE: a player-standing / ban check. Before admitting an
  account to online play the client asks the backend whether that account is
  banned, so a banned player can be refused matchmaking. The administrative
  reason it exists is enforcement: the ban list lives server-side, and the
  "report" family name indicates this is the same backend that receives player
  reports.

  REQUEST (client->server, one NUL-terminated ASCII line), LIVE-CAPTURED:
    is-banned <online_id>\n
  Both captured frames decrypt to exactly `is-banned comradesean\n` (22 bytes =
  "is-banned "(10) + "comradesean"(11) + "\n"(1)). The argument is the PSN
  online-id, the same identity the heartbeat line carries.

  RESPONSE: NOT YET OBSERVED, and deliberately not guessed here. By family
  convention the line services answer with '+'-prefixed ASCII rows terminated by
  a trailing NUL, with the server holding the socket open until the client
  closes (the leaderboard reader's NUL-sentinel behaviour - a server-initiated
  EOF is the client's error path, see 0x11_leaderboard_line.ksy). The verb shape
  ("is-<predicate>") implies a boolean answer, but which encoding - `+0`/`+1`,
  `+true`/`+false`, or a row count - is unresolved. Resolve by decompiling the
  caller of the "is-banned %s" format string, or by capturing a real reply.

  SERVER-SIDE GAP (implementation, not protocol): server/ticket_server.py
  branches only on leaderboard-server and facebook-server, so a report-server
  connection falls through to the generic ticket path and is answered with a
  ticket_submit_response frame - which is how the captured plaintext came to be
  logged at all. That is the same mismatch class that produced the leaderboard
  "Error 9 / disconnected from game servers" boot and the Facebook retry spin
  before those services got dedicated line-oriented handlers. Answering a ban
  check with a ticket blob is a live risk to online entry and should be given a
  real handler once the reply grammar is known.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: verb
    type: str
    terminator: 0x20
    eos-error: false
    doc: "The literal ASCII verb \"is-banned\" followed by one space. Live-captured."
  - id: online_id
    type: str
    terminator: 0x0a
    eos-error: false
    doc: |
      The account being checked: a PSN online-id (account handle), terminated by
      '\n' then a trailing NUL. Live-verified value "comradesean". Both captured
      frames query the LOCAL player's own id, so whether this line is ever used
      to check a REMOTE player (a reported opponent) is unobserved.
