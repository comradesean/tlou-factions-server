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
  - id: pad_4
    type: u4
    doc: "Offset 4:8. NEVER WRITTEN by the sender - uninitialised stack. RESOLVED 2026-08-18: FUN_00ad6c70's buffer stores (base r1+144) are exactly at 144/152/156/160/164/166/168/172/174/176(r1); there is no store to 148(r1) = wire 4. The pointer-shaped live value `d0 04 01 a0` is stack residue. Was `header_04`."
  - id: search_obj_ptr
    type: u4
    doc: "Offset 8:12. The client's own search-object pointer (live 0x01383bd8, `mr`/store from the search object). This is the value the server's 0x136 RoomSearch reply MUST echo back at its own offset 8 - the 0x136 handler dereferences and writes the game list through it. See protos/0x136_room_search.ksy."
  - id: field_0c
    type: u4
    doc: |
      Offset 12:16. `*(u32*)(search_obj+0x0C)` (`lwz r11,12(r29)` @ 0xad6c90,
      `stw r11,156(r1)`) - literally the SAME struct offset as RoomCreate's
      room_field_0c (room_obj+0x0c), so it carries the same value: the selected
      MAP identifier (or a map-dominated map+team combined index), used here as
      the match-search map filter. Six distinct logged values across sessions
      rule out the team field, and the map-vs-team-combined caveat is now CLOSED
      (2026-08-18): the same field_0c value occurs with different team values in
      live RoomCreate captures, so it carries no team component - see
      0x12f_room_create.ksy room_field_0c and
      research/notes/2026-08-18-wire-residue-and-field-corrections.md §4.
      Live find_match value: 0x00000002 in 411/411 captured frames - this field
      never varies on the find-match path, so 0x02 is either the map id
      matchmaking always resolves to or an any/random sentinel (open). Resolving the writer of +0x0c settles both messages.
  - id: room_flags_10
    type: u4
    doc: "Offset 16:20. `*(u32*)(search_obj+0xE8)` conditionally OR'd with 0x40000000 (`lwz r0,232(r29)` @ 0xad6cd0, `oris r0,r0,16384` @ 0xad6cf0) - identical construction to RoomCreate's room_flags_e8. Live `10 2c 50 3f`. (The oris gate compares r10, whose definition is outside the function body - gate condition untraced.)"
  - id: value_pair_14
    size: 4
    doc: "Offset 20:24. The 0x03e8/0x03e8 (1000/1000) u16 pair, same source as RoomCreate's value_20/value_22 (the two float out-params of _opd_FUN_00acb6bc, fctiwz->sth). Likely a default rating pair; disabled/constant in all live captures."
  - id: burst_marker
    type: u2
    doc: "Offset 24:26 (wire 0x18). BURST/criteria marker = the sender's own 3rd argument (`mr r31,r5` @ 0xad6cc8, `sth r31,168(r1)` @ 0xad6d28), a caller-supplied criteria index from the find-match state machine. Steps 5, 10, 10, 0, 0 across the ~5 searches of one burst. The stub keys its serialized election on marker==5 (criteria 0 = a fresh burst start) - see the doc note above."
  - id: pad_1a
    size: 2
    doc: "Offset 26:28. Uninitialised padding. DEFINITION: an unwritten 2-byte gap after burst_marker, before the search-window pair. REASON: FUN_00ad6c70's store enumeration (base r1+144) has no store to 170(r1) = wire 26; it captures as 0. Send 0. (This offset plus search_window_lo/hi below were once a single field wrongly named `pad_1a`.)"
  - id: search_window_lo
    type: u2
    doc: "Offset 28:30. `max(0, param_5 - param_6)` when param_5 >= 0, else 0 (`subf/not/srawi/and` clamp @ 0xad6d90-0xad6dc4). The low end of a rating/filter window; 0 in all live captures (the window is disabled while searching). Was the middle of `pad_1a`."
  - id: search_window_hi
    type: u2
    doc: "Offset 30:32. `param_5 + param_7` when param_5 >= 0, else 0 (same clamp). The high end of the rating/filter window; 0 in all live captures. Was the tail of `pad_1a`."
  - id: locale
    size: 4
    doc: "Offset 32:36 (wire 0x20). Region/language, zeroed by default (`stw r26,176(r1)` @ 0xad6d1c) and overwritten with region|language only when param_4 != 0. Live `75 73 00 01` = 'us\\0' + language 1 on criteria-0 searches (same as RoomCreate's region_language); later criteria in a burst send zeros here."
