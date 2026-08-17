meta:
  id: find_match
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmaking find-match search broadcast, sent by the client repeatedly
  (~5s cadence, same as Ping) while sitting in the "Find Match" screen -
  correlates with the client's *own* matchmaking-search state, not a
  one-off "I left a room" event.

  CLARIFIED 2026-08-17: the server must REPLY to each 0x135 with a `0x136`
  RoomSearch game list (server->client) - that is what NET_SM_CLIENT_GAME_LIST_
  WAIT blocks on. Wire offset 8 is the client's search-object pointer (live
  0x01383bd8) which the 0x136 reply MUST echo back at its own offset 8. See
  protos/0x136_room_search.ksy and research/notes/2026-08-17-find-match-flow.md.
  Find-match (public matchmaking) is the ONLY path to a COUNTED game that
  credits progression (see 2026-08-17-match-counts-latch.md).

  SERIALIZED ELECTION (2026-08-17, live-confirmed end-to-end). The body is a
  serialization of the client's own search object and mirrors 0x12f/RoomCreate:
  wire offset 8 = search-object pointer, and wire offset 0x18 is a BURST
  MARKER (criteria index) that steps 5, 10, 10, 0, 0 across the ~5 searches of
  one find-match burst before the client gives up and self-hosts a public game.
  tools/session_manager_stub.py uses this to run a deterministic election: the
  FIRST criteria-0 (marker==5) searcher is elected HOST and gets empty 0x136
  lists through its whole burst so it self-hosts; any OTHER client searching
  during the election is PARKED (no 0x136 reply at all - it blocks silently in
  GAME_LIST_WAIT, 60s hard cap) until the host's 0x12f RoomCreate lands, then
  released with a 1-entry list pointing at the host. This makes exactly one
  host + one joiner every time. Combined with the joiner's real P2P join and a
  client-side min-players=2 patch, this drove the project's first COUNTED,
  CREDITED matchmade game (NET_SM_RESULTS -> OnMatchEnd; supplies/rank/clan
  population credited live). See
  research/notes/2026-08-17-find-match-coordination-root-cause.md.

  STATUS: the declared opcode/size table (docs/protocol/session_manager_and_
  matchmaking.md) names this NetMatchmakingRoomLeft at 24 bytes - WRONG on
  both counts, per this project's now-established pattern of declared-table
  errors past the initial handshake opcodes (see 0x133/0x13a for two prior
  examples). Live capture shows this fires every ~2-3s (1+2*rand backoff)
  while searching, 36 bytes; the body offsets below are mapped from the
  captures and mirror the RoomCreate serialization.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x135 (309 decimal). Confirmed live, big-endian."
  - id: header_04
    type: u4
    doc: "Offset 4:8. A value/flags word (live `d0 04 01 a0`). Not independently decoded; mirrors the RoomCreate serialization shape."
  - id: search_obj_ptr
    type: u4
    doc: "Offset 8:12. The client's own search-object pointer (live 0x01383bd8). This is the value the server's 0x136 RoomSearch reply MUST echo back at its own offset 8 - the 0x136 handler dereferences and writes the game list through it. See protos/0x136_room_search.ksy."
  - id: field_0c
    type: u4
    doc: "Offset 12:16. A small mode-shaped field (live 0x00000002). Corresponds to RoomCreate's room_field_0c (room_obj+0x0c)."
  - id: room_flags_10
    type: u4
    doc: "Offset 16:20. Room/search flags (live `10 2c 50 3f`), same shape as RoomCreate's room_flags_e8."
  - id: value_pair_14
    size: 4
    doc: "Offset 20:24. The 0x03e8/0x03e8 (1000/1000) u16 pair, as in RoomCreate."
  - id: burst_marker
    type: u2
    doc: "Offset 24:26 (wire 0x18). BURST/criteria marker. Steps 5, 10, 10, 0, 0 across the ~5 searches of one find-match burst. The stub keys its serialized election on marker==5 (criteria 0 = a fresh burst start) - see the doc note above."
  - id: pad_1a
    size: 6
    doc: "Offset 26:32. Zero across captures."
  - id: locale
    size: 4
    doc: "Offset 32:36 (wire 0x20). Region/language, live `75 73 00 01` = 'us\\0' + language 1 (same as RoomCreate's region_language). Present on criteria-0 searches; later criteria in a burst send zeros here."
