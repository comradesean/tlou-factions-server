meta:
  id: gamelist_line
  title: gamelist-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server (request). The server-to-client reply is real but
  UNPARSED - see "RESPONSE" below - so it is documented in prose rather than
  modelled as a struct.

  The custom ND `gamelist-server` sub-protocol, a member of the 0x11
  sibling-server family: same connect + 88-byte hello carrying the service name
  + 8-byte reply whose byte[0] is 0x22, then the shared encrypt-then-MAC 0x33
  frame (server/lib/ticket_cipher.py). THIS spec models the DECRYPTED PLAINTEXT.

  BUILD SCOPE: 01.11-ONLY. `gamelist-server` (VMA 0xeb2690) and its verb
  `game-add ` (0xeb2680) exist only in the 01.11 EBOOT; a byte search finds
  neither in 01.00. All VMAs here are 01.11 (VMA = file offset + 0x10000), in
  the ELF with sha256 241e2b1bca43c97431a1aa7acd1b29a20d292bec7263ab8ca318b8a03538e592.

  DEFINITION / PURPOSE: the client REGISTERING its live game with the backend.
  Live capture (2026-08-19, one frame, 50 bytes decrypted):

      game-add mgnomad2.1787116698 mgnomad2 comradesean\n

  The first argument is the MATCH-SESSION ID in the `<npid>.<unix-timestamp>`
  form that `0x143 SetRoomDataBlock` also carries (see
  protos/0x143_set_room_data_block.ksy) - here `mgnomad2` hosting at unix
  1787116698. The remaining tokens are the roster: the accounts in that game,
  host first.

  WRITE-ONLY. `game-add ` is the ONLY `game-` verb in the whole EBOOT - there is
  no `game-remove` and no `game-list`. So this is the client REPORTING a game,
  not discovering others, and it is NOT a second matchmaking path; discovery
  remains 0x135/0x136 on the session manager.

  SENDER: FUN_004047f4 (01.11), located by resolving the r2->anchor->
  displacement chain onto the string slots 0x129cd7c ("game-add "), 0x129cd8c
  ("gamelist-server") and 0x129cd70 ("games/%s"). r2 for this build is
  0x1338de0, read from the entry-point function descriptor at 0x12d5c08.

  The request line is assembled by literal strcat, which is where this spec's
  field boundaries come from - they are not inferred from the capture:

      buf[0] = *""          @0x4048c0-0x4048e0, slot 0x129cd78 -> "" (the
                            buffer simply starts empty), then memset(buf+1,0,255)
      strcat "game-add "    @0x4048ec  slot 0x129cd7c -> 0xeb2680
      strcat <session-id>   @0x4048fc / 0x40492c, r25 = arg+16222
      loop i < *(arg+16152) @0x404908-0x40494c:
          strcat " "        slot 0x129cd80 -> 0xeac140
          strcat <player>   arg + 17688 + i*212
      strcat "\n"           @0x404950  slot 0x129cd84 -> 0xf3efa0

  The capture matches that construction to the byte: 9 ("game-add ") + 19
  (session id) + 9 (" mgnomad2") + 12 (" comradesean") + 1 ("\n") = 50, the
  exact decrypted length observed. There is NO trailing NUL inside the frame;
  the length comes from strlen at 0x4049f0.

  CONNECT: at 0x4049b0 the service name "gamelist-server" is loaded and the
  ip/port pair is read out of the shared service-descriptor structure at
  *(0x15900b8) + 0x60; 0x4049d4 calls 0xaf9bb4, which is the family's shared
  hello function (li r5,88 for the 88-byte hello @0xaf9c94, li r5,8 for the
  8-byte reply @0xaf9d2c, cmpwi r0,34 for the 0x22 ack magic @0xaf9d60) - the
  same function report-server calls at 0x36e220, i.e. the 01.11 twin of 01.00's
  FUN_00acc424. That is what makes gamelist-server a 0x11 sibling rather than a
  lookalike. A non-zero return branches straight to the close at 0x404a20.

  RESPONSE (server->client): THE CLIENT DOES NOT PARSE IT. After the send at
  0x404a04 there is exactly one bounded 256-byte recv (li r5,256 @0x404a14, bl
  0xafacf8 @0x404a18) and then an immediate, unconditional close (bl 0xaf9260
  @0x404a24). The recv's return value in r3 is not even compared against
  anything - 0x404a1c is the call's nop and 0x404a20 overwrites r3 with the
  connection pointer for the close. There is no length field, no accumulator
  loop, no '+' test and no tokeniser anywhere in the function. This is the
  HEARTBEAT single-bounded-recv shape - weaker even than report-server's, which
  at least tests the byte count at 0x36e298 before parsing - and it is
  emphatically NOT the leaderboard accumulator shape. Consequences: the whole
  reply must arrive in ONE frame, and its CONTENT is free.

  PROVEN vs ASSUMED, stated explicitly because the reply body is a choice:
    * PROVEN from the binary - the verb, the session-id-then-roster token order,
      the " " separators, the trailing "\n", the absence of any other game-
      verb, the single bounded 256-byte recv, and the fact that the reply is
      never inspected.
    * PROVEN from a live capture - the 50-byte plaintext above, i.e. a
      two-player roster.
    * ASSUMED - that a roster longer than two behaves the same way (the loop at
      0x404908 is generic in the count at *(arg+16152), so this is a strong
      inference, but only a 2-player sample has been captured), and that the
      212-byte stride between roster entries is a player record rather than
      something reused; the stride is proven, its struct is not mapped.
    * A CHOICE, not a requirement - the reply body itself.

  SERVER BEHAVIOUR (server/ticket_server.py handle_gamelist /
  build_gamelist_response, implemented 2026-08-19): gamelist-server now has a
  dedicated handler in LINE_SERVICE_HANDLERS and no longer falls through to the
  ticket path (which answered it with a ticket_submit_response frame - the same
  request/response mismatch class that broke the leaderboard channel and the
  Facebook flow before each got a real handler). The handler records the
  session id and roster in an in-memory registry - the administrative purpose
  of the message - and replies "+0\n" plus the family's NUL sentinel, holding
  the socket until the client closes. The body is a family-consistency choice
  copied from handle_heartbeat, which answers an equally unparsed reader; what
  IS load-bearing is sending something at all, so the client's recv returns
  rather than waiting out its own timeout, and never closing first.

  ADJACENT BUT SEPARATE CHANNEL, recorded so it is not mistaken for this one:
  earlier in the same function (0x404820-0x4048b8) the client builds a buffer
  via 0xa49efc / 0xa49f14 / 0x403ca4, formats the path "games/%s" (0xeb2670)
  with the same session id, and hands it to 0xaf39c0 in a retry loop of up to 9
  attempts. 0xaf39c0 stores a method enum of 4 into its request object (li r0,4
  @0xaf39f8; its sibling entry point 0xaf3a30 stores 1), so that is an
  HTTP-style upload aimed at a DIFFERENT host object (slot 0x129cd74 ->
  0x13ba678), not this TCP line service. It is out of scope for this spec and
  is not handled by this server.
doc-ref: ../docs/protocol/0x11_gamelist_line.md
seq:
  - id: verb
    type: str
    terminator: 0x20
    eos-error: false
    doc: |
      The literal ASCII verb "game-add" followed by the one space that is part
      of the format string `game-add ` @ 0xeb2680 (01.11), strcat'd at
      0x4048ec. The only game- verb in the binary.
  - id: session_id
    type: str
    terminator: 0x20
    eos-error: false
    doc: |
      The match-session id, `<npid>.<unix-timestamp>` - the same string 0x143
      SetRoomDataBlock carries for the room. Source: arg+16222 at 0x4048fc.
      Live value "mgnomad2.1787116698". Terminated here by the first roster
      separator, because each roster entry is emitted as " " + name; a game
      registered with an EMPTY roster (count at *(arg+16152) == 0) would end
      this token at the '\n' instead. No such line has been captured and the
      host is always in the roster, so the empty case is a theoretical branch
      of the sender's loop, not an observed shape.
  - id: players
    type: player
    repeat: eos
    doc: |
      The roster, host first, one entry per iteration of the sender loop at
      0x404908-0x40494c, whose trip count is *(arg+16152) and whose entries are
      strided 212 bytes apart from arg+17688. Live: ["mgnomad2",
      "comradesean"].
types:
  player:
    seq:
      - id: name
        type: str
        terminator: 0x20
        eos-error: false
        doc: |
          One roster member's PSN online-id. NOTE ON THIS MODEL: the wire uses
          ' ' between entries and a single '\n' after the last one, and Kaitai's
          `terminator` takes one byte, not a set - so the FINAL player parses
          with the trailing '\n' still attached to its name. Strip it when
          consuming. The '\n' is a real, proven part of the grammar (strcat at
          0x404950 from slot 0x129cd84), not padding, which is why it is
          documented here rather than silently dropped.
