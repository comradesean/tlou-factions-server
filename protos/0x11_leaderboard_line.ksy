meta:
  id: leaderboard_line
  title: leaderboard-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  The custom ND `leaderboard-server` sub-protocol (NOT sceNpScore). It is a
  member of the 0x11 sibling-server family: same connect + 88-byte hello
  carrying the service name "leaderboard-server" + 8-byte reply whose byte[0]
  is 0x22 (see 0x11_leaderboard_server_hello.ksy / _hello_response.ksy), on the
  same ip:port as ticket-server (192.168.1.100:7320 live). AFTER the hello,
  every payload is wrapped in the shared encrypt-then-MAC 0x33 frame (magic
  0x33, pad, BE u16 plaintext_len, 16-byte tag, ciphertext — see
  docs/protocol/0x11_ticket_server_hello.md and tools/ticket_cipher.py, keyed by
  the same per-connection rolling counter). THIS spec models the DECRYPTED
  PLAINTEXT of a server->client response; the requests are documented below.
  The client opens one TCP connection per command and treats the connection
  CLOSE (EOF) as end-of-response. Full decode + evidence:
  research/notes/2026-08-17-leaderboard-server-protocol.md and the working stub
  in tools/ticket_server_stub.py (build_leaderboard_response).

  REQUESTS (client->server, one printf-built line, space-delimited, '\n'-term):
    leaderboard-get   <board:int> 1 <name0> <name1> ...   (<=16 names/line; batch lookup by name)
    leaderboard-range <board:int> <start:int> <end:int> 1  (start=0xffffffff = "center on my rank")
    leaderboard-update <board:int> <npid:str> <score:int64> <base64-metadata>  (submit; reply ignored)
  Confirmed board ids (decimal): 405 (overall/clan-supplies, always submitted),
  406 (game-mode-2 skill), 404 (game-mode-3 skill). The update's trailing field
  is base64 of BE-u32 secondary stats, NOT a signature (no signing).

  RESPONSES (server->client), '\n'-delimited '+'-prefixed rows, decimal ints,
  s64 score via strtoll, blob = standard base64:
    GET row:          +<rank> <name> <score> <b64>     (client stores rank = atoi(<rank>)+1)
    RANGE(blob) row:  +<name> <score> <b64>            (rank computed positionally = start+index+1)
    RANGE(blob) total:+<total>
    RANGE(clan):      +<total>   and   +<a> <b>
  A minimal legal answer is a single "+0\n" (empty board) or an empty response.

  The trailing `<b64>` token is NOT opaque: it is standard base64 of a
  big-endian 5-u32 secondary-stat struct (best_game, time_played_sec,
  executions, deaths, rank), trailing-zero-truncated on the wire. Decoded
  layout is the `leaderboard_blob` type below; the server stub round-trips it
  with `struct.unpack(">IIIII", ...)` and the field order was verified live
  against the on-screen leaderboard columns
  (research/notes/2026-08-17-leaderboard-server-protocol.md). base64 LUT @
  0x00f022c0, space delimiter @ 0x00e79948, '\n' terminator @ 0x00f0b170.
seq:
  - id: rows
    type: response_row
    repeat: eos
    doc: "Zero or more '+'-prefixed response rows, terminated by connection close."
types:
  response_row:
    seq:
      - id: row
        type: str
        terminator: 0x0a
        eos-error: false
        doc: |
          One response line including its leading '+'. Tokenize on space; shape
          depends on the request (see the top-level doc). The last token of a
          GET/RANGE(blob) row is base64 of a `leaderboard_blob` (below).
          Empty/no rows = empty board (the client tolerates zero entries).
  leaderboard_blob:
    doc: |
      The decoded form of a row's trailing base64 token: five big-endian u32
      secondary stats, trailing-zero-truncated on the wire (a shorter decoded
      blob means the tail fields are 0). This is a structural spec for the
      DECODED bytes - Kaitai does not base64-decode inline, so a consumer
      base64-decodes the token first, then parses it with this type.
    seq:
      - id: best_game
        type: u4be
        doc: "Best single-game score."
      - id: time_played_sec
        type: u4be
        doc: "Total time played, seconds."
      - id: executions
        type: u4be
        doc: "Execution count."
      - id: deaths
        type: u4be
        doc: "Death count."
      - id: rank
        type: u4be
        doc: "Rank / progression value (trailing field; absent when the wire blob is truncated before it)."
