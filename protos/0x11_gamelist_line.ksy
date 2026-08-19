meta:
  id: gamelist_line
  title: gamelist-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server. Response not yet characterised.

  The custom ND `gamelist-server` sub-protocol, a member of the 0x11
  sibling-server family: same connect + 88-byte hello carrying the service name
  + 8-byte reply whose byte[0] is 0x22, then the shared encrypt-then-MAC 0x33
  frame (server/lib/ticket_cipher.py). THIS spec models the DECRYPTED PLAINTEXT.

  BUILD SCOPE: 01.11-ONLY. `gamelist-server` (VMA 0xeb2690) and its verb
  `game-add ` (0xeb2680) exist only in the 01.11 EBOOT; a byte search finds
  neither in 01.00. All VMAs here are 01.11 (VMA = file offset + 0x10000).

  DEFINITION / PURPOSE: the client REGISTERING its live game with the backend.
  Live capture (2026-08-19, one frame, 50 bytes decrypted):

      game-add mgnomad2.1787116698 mgnomad2 comradesean\n

  The first argument is the MATCH-SESSION ID in the `<npid>.<unix-timestamp>`
  form that `0x143 SetRoomDataBlock` also carries (see
  protos/0x143_set_room_data_block.ksy) - here `mgnomad2` hosting at unix
  1787116698. The remaining tokens are the roster: the two accounts in that
  game, host first.

  WRITE-ONLY, as far as the binary shows. `game-add ` is the ONLY `game-`
  verb in the whole EBOOT - there is no `game-remove` and no `game-list`. So
  this is the client REPORTING a game, not discovering others, and it is NOT a
  second matchmaking path; discovery remains 0x135/0x136 on the session
  manager. A nearby `games/%s` (0xeb2670) suggests the backend keys the list by
  something per-game, plausibly that session id.

  STATUS: NOT HANDLED by server/ticket_server.py. It falls through to the
  generic ticket path and is answered with a ticket_submit_response frame,
  which is probably not what it expects - the same mismatch class that broke
  the leaderboard channel and the Facebook flow before each got a real handler.
  The fall-through now logs a loud warning naming the service.

  BEFORE WRITING A HANDLER: decompile the sender near 0xeb2680 and determine
  whether the reply is parsed at all, and if so in which shape - the single
  bounded recv that heartbeat-server and report-server use, or the NUL-sentinel
  accumulator that leaderboard-server uses. Do not guess; that distinction
  decides whether the server may close first, and getting it wrong is what
  produced the leaderboard "Error 9 / disconnected from the game servers" boot.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: verb
    type: str
    terminator: 0x20
    eos-error: false
    doc: "The literal ASCII verb \"game-add\" followed by one space. From the format string `game-add ` @ 0xeb2680 (01.11). The only game- verb in the binary."
  - id: rest
    type: str
    terminator: 0x0a
    eos-error: false
    doc: |
      Space-separated remainder, terminated by '\n': the match-session id
      (`<npid>.<unix-timestamp>`, same form as 0x143's data_block) followed by
      the roster's online-ids, host first. Live: `mgnomad2.1787116698 mgnomad2
      comradesean`. Modelled as one token run rather than fixed fields because
      the roster length varies with the player count, and only a 2-player
      sample has been captured.
