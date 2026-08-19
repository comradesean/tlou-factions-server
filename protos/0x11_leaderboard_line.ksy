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
  docs/protocol/0x11_ticket_server_hello.md and server/lib/ticket_cipher.py, keyed
  by the same per-connection rolling counter). THIS spec models the DECRYPTED
  PLAINTEXT of a server->client response; the requests are documented below.
  The client opens one TCP connection per command and reads until a TRAILING NUL
  (0x00), then closes the connection ITSELF. A server-initiated EOF before the
  NUL is the client's ERROR path (recv() failed -> "disconnected from game
  servers"); no-NUL-no-EOF hangs the spinner. So a response is '+'-rows followed
  by a single 0x00, and the server must hold the socket open until the client
  FINs (LIVE-DISPROVED the earlier "EOF = end-of-response" reading). Full decode
  + evidence: research/notes/2026-08-17-leaderboard-server-protocol.md and the
  working handler in server/ticket_server.py (build_leaderboard_response).

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
    RANGE(clan):      +<total>   then the STANDARD 3-token row +<name> <score> <b64>
                      (the rank-0/leader entry of a "range <board> 0 1" query).
                      CORRECTED 2026-08-18 (was wrongly "+<a> <b>"): the clan
                      worker FUN_003af46c requires all THREE tokens (name/score/
                      b64); it keeps only <score> (strtol -> job+0x88, @0x3afa44-60)
                      and counts rows (job+0x70), discarding <name> and <b64>. A
                      2-token line stores nothing. So <score> here = the queried
                      board's leader score; its on-screen label is DC-driven.
  A minimal legal answer is a single "+0\n" (empty board) or an empty response.

  The trailing `<b64>` token is NOT opaque: it is standard base64 of an ARRAY of
  big-endian u32 secondary-stat slots, trailing-zero-truncated on the wire.
  Every blob observed decodes to a whole number of u32s - no partial slot, no
  remainder. The first five are named (best_game, time_played_sec, executions,
  deaths, rank); Interrogation additionally sends slots 5..8 (see
  `leaderboard_blob` below). CORRECTED 2026-08-19: this was documented as a
  fixed 5-u32 struct, which is the SUPPLY RAID shape, not the general one -
  board 407 sends 8-9 slots. Decoded layout is the `leaderboard_blob` type
  below; the server decomposes every slot into its own database column and
  never stores the blob in wire form, and the field order was verified live
  against the on-screen leaderboard columns
  (research/notes/2026-08-17-leaderboard-server-protocol.md). base64 LUT @
  0x00f022c0, space delimiter @ 0x00e79948, '\n' terminator @ 0x00f0b170.
seq:
  - id: rows
    type: response_row
    repeat: eos
    doc: "Zero or more '+'-prefixed response rows. The response is terminated by a trailing NUL (0x00) that the server appends after the last row, at which point the client closes the connection itself (a server-initiated close BEFORE the NUL is the client's error path — see top-level doc)."
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
      The decoded form of a row's trailing base64 token: an array of big-endian
      u32 secondary stats, trailing-zero-truncated on the wire. This is a
      structural spec for the DECODED bytes - Kaitai does not base64-decode
      inline, so a consumer base64-decodes the token first, then parses it with
      this type.

      TRUNCATION CARRIES NO INFORMATION. A slot the wire omits IS zero; the
      client is simply declining to spend bytes on zeros. A reader should treat
      an absent trailing slot as 0, not as "unknown" or "not applicable", and a
      writer is free to emit the zero explicitly - the two forms describe the
      same record. The `if` guards below therefore describe what the WIRE may
      carry, not a distinction in meaning.

      SLOT COUNT IS PER-MODE, not fixed. Live 2026-08-19, all u32-aligned:
        board 404 (Supply Raid)   5 slots
        board 406 (Supply Raid)   4-5 slots (4 = rank truncated off at 0)
        board 407 (Interrogation) 8-9 slots
      BOARD 407 SCORE = PARTS/MIN x 100 (fixed-point, confirmed 2026-08-19
      against the on-screen INTERROGATION - GLOBAL table): score 53454 renders
      534.5, score 44694 renders 446.9. The x100 keeps the board sortable as an
      integer while displaying one decimal.

      The board 407 display columns are, in order:
        POSITION | PLAYER | PARTS/MIN | INTERROGATIONS | INTERROGATIONS DENIED
        | OFFENSIVE EXECUTIONS | DEFENSIVE DOWNS
      plus a rank badge left of the player name. PARTS/MIN comes from the score,
      not the blob, leaving FOUR displayed stat columns to be sourced from blob
      slots - and the blob carries 8-9 slots, so not every slot is displayed.
      Note the five names below (best_game / time_played_sec / executions /
      deaths / rank) were pinned against the SUPPLY RAID columns on board 406;
      they are almost certainly per-mode labels rather than universal ones, so
      do not assume slot 0 means "best_game" on board 407.

      BOARD 407 SLOT MAPPING - PINNED 2026-08-19 against the on-screen
      INTERROGATION - GLOBAL table, two players:
        stored  comradesean (4485, 3607, 42, 17, 2, 0, 5, 1)
                mgnomad2    (3740, 3144, 16, 38, 1, 0, 4, 0, 5)
        slot[0..3]  NOT DISPLAYED on this board (4485/3607/42/17 and
                    3740/3144/16/38 appear nowhere on screen).
        slot[4]     rank -> the badge left of the player name. Live 2 / 1.
        slot[5]     INTERROGATIONS DENIED. INFERRED, not proven: both samples
                    are 0, so any all-zero column would fit equally well. It is
                    the only unclaimed slot left for the only unclaimed column.
        slot[6]     INTERROGATIONS.        Live 5 / 4  - exact, distinct values.
        slot[7]     OFFENSIVE EXECUTIONS.  Live 1 / 0  - exact, distinct values.
        slot[8]     DEFENSIVE DOWNS.       Live 0 / 5  - exact, distinct values.
      NOTE the wire order is NOT the display order: slot[5] (denied) precedes
      slot[6] (interrogations), while the screen shows interrogations first.
      The slots keep positional names in this shared type because slot meaning
      is PER-BOARD - slot[6] is "interrogations" only on 407. A per-board naming
      belongs in a consumer, not in this struct.
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
        doc: "Rank / progression value. On Supply Raid boards this is the last slot and is absent when the wire blob is truncated before it; on Interrogation boards four more slots follow."
        if: _io.size >= 20
      - id: slot_5
        type: u4be
        doc: "Board 407: INTERROGATIONS DENIED (inferred - both live samples 0, assigned by elimination). Meaning on other boards unknown."
        if: _io.size >= 24
      - id: slot_6
        type: u4be
        doc: "Board 407: INTERROGATIONS. Confirmed on distinct live values 5 (comradesean) / 4 (mgnomad2). Meaning on other boards unknown."
        if: _io.size >= 28
      - id: slot_7
        type: u4be
        doc: "Board 407: OFFENSIVE EXECUTIONS. Confirmed on distinct live values 1 / 0. Meaning on other boards unknown."
        if: _io.size >= 32
      - id: slot_8
        type: u4be
        doc: "Board 407: DEFENSIVE DOWNS. Confirmed on distinct live values 0 / 5. Meaning on other boards unknown."
        if: _io.size >= 36
