meta:
  id: leaderboard_request_line
  title: leaderboard-server REQUEST line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server

  Client->server REQUEST lines for the custom ND `leaderboard-server`
  sub-protocol. The RESPONSE side is modeled in
  protos/0x11_leaderboard_line.ksy - this file specifies the requests. Member of
  the 0x11 sibling-server family: connect + 88-byte hello carrying
  "leaderboard-server" + 8-byte 0x22 reply, same ip:port as ticket-server. AFTER
  the hello every payload rides the shared encrypt-then-MAC 0x33 frame (magic
  0x33, pad, BE u16 plaintext_len, 16-byte tag, ciphertext - see
  docs/protocol/0x11_ticket_server_hello.md, server/lib/ticket_cipher.py);
  confirmed live (requests decrypt tag_ok). THIS spec models the DECRYPTED
  PLAINTEXT request line. Fields are space-delimited (delimiter " " @
  0x00e79948; '\n' terminator @ 0x00f0b170).

  REQUESTS (one printf-built line each):
    leaderboard-get   <board:int> 1 <name0> <name1> ...   (<=16 names/line; trailing "1" = version/include-metadata flag; batch lookup by name)
    leaderboard-range <board:int> <start:int> <end:int> 1  (start=0xffffffff = "center on my rank"; "<board> 0 1" = clan total-only variant)
    leaderboard-update <board:int> <npid:str> <score:int64> <base64-blob>  (submit; reply ignored)
  Format strings: "leaderboard-get %i 1" @ file 0xe6d280 (names appended after
  via strncat); "leaderboard-range %i %i %i 1\n" @ 0xe6d298;
  "leaderboard-update %i %s %lld %s\n" @ 0xe6d2b8. Confirmed board ids (decimal):
  405 (overall/clan-supplies, always submitted), 406 (mode-2 skill), 404 (mode-3
  skill).

  The update's <base64-blob> is NOT opaque and NOT a signature: standard base64
  of the SAME big-endian 5-u32 secondary-stat struct modeled as `leaderboard_blob`
  in protos/0x11_leaderboard_line.ksy (best_game, time_played_sec, executions,
  deaths, rank; trailing-zero-truncated on the wire). base64 encode via
  FUN_0001fd54; LUT @ 0x00f022c0.

  RESPONSES: see protos/0x11_leaderboard_line.ksy (GET "+<rank> <name> <score>
  <b64>", RANGE-blob "+<name> <score> <b64>" + "+<total>", RANGE-clan "+<total>"
  / "+<a> <b>"). Response terminates on a trailing NUL, then the client closes.

  Evidence: strings_ascii.txt 0xe6d280 / 0xe6d298 / 0xe6d2b8; Ghidra
  FUN_003aeee8 (GET), FUN_003afb74 (range-blob), FUN_003af46c (range-clan),
  FUN_003b0f6c (update); server/ticket_server.py (leaderboard-server handling);
  research/notes/2026-08-17-leaderboard-server-protocol.md.
  BOARD IDS (live-observed 2026-08-18/19). Boards are served purely on request -
  the server keys its store by (board_id, player) and has no board whitelist, so
  a client only ever sees a board it asks for.

    404  per-mode board   (0x194)  requested by 01.00 and 01.11
    405  overall / clan supplies (0x195), submitted on every match end
    406  per-mode board   (0x196)  requested by 01.00 and 01.11
    407  01.11 ONLY - the mode 01.11 added (Interrogation). 01.00 has never
         requested it in any captured session, so it is naturally invisible to
         that build; no server-side gating is needed to keep it separate.

  CROSS-BUILD NOTE: 404/405/406 are SHARED between builds - both read and write
  them, and scores land in the same rows. That is accepted for this project. Be
  aware the playlist ids were renumbered between builds (see
  protos/0x12f_room_create.ksy), so it should NOT be assumed that board 404
  denotes the same mode on both; if per-build separation is ever wanted, key the
  store by (build, board_id, player) - the build is known per npid from the
  session-manager registry.

doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: request
    type: str
    terminator: 0x0a
    eos-error: false
    doc: |
      One request line (get is NUL-terminated after the appended names; range
      and update carry a literal '\n' from their format strings). Tokenize on
      space; token[0] = verb. See top doc for per-verb token layout. The
      update's last token is base64 of a `leaderboard_blob`
      (protos/0x11_leaderboard_line.ksy).
