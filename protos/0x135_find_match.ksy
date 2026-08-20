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
  server/session_manager.py uses this to run a deterministic election: the
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
      `stw r11,156(r1)`).

      DEFINITION: the PLAYLIST the client is queueing for - mode plus party
      rules in one id. See protos/0x12f_room_create.ksy room_field_0c for the
      full table, the per-build numbering caveat, and the non-matchmaking ids.

      A searcher asks for EXACTLY ONE playlist and never widens: across the nine
      01.11 playlists walked on 2026-08-19, every burst carried a single value.
      (An earlier note claimed Supply Raid/Parties-Allowed searched both 1 and 2;
      that was a measurement error - the 2s were the tail of the previous queue,
      caught by a wall-clock window that straddled the style switch. Segment by
      the switch, not by the clock.)

      SERVER RULE: filter the 0x136 game list on THIS field - the searcher's own
      request - and never on the host's room_field_0c, which is not reliably
      reset. Implemented in server/session_manager.py after a live cross-playlist
      match on 2026-08-18 (a Survivors searcher was handed a Supply Raid room and
      joined it). Match on the game BUILD too: ids are not comparable across
      builds.
  - id: room_flags_10
    type: u4
    doc: |
      Offset 16:20. `*(u32*)(search_obj+0xE8)` conditionally OR'd with
      0x40000000 (`lwz r0,232(r29)` @ 0xad6cd0, `oris r0,r0,16384` @
      0xad6cf0) - identical construction to RoomCreate's `room_flags_e8`.
      Live `10 2c 50 3f`. The gate compares `r10` (`cmpwi cr7,r10,0` @
      0xad6c94) - this register's origin within THIS function was not
      traced this pass (a different function from `room_flags_e8`'s sender,
      so its result does not transfer automatically).

      `room_flags_e8`'s own gate WAS live-resolved 2026-08-19 (see that
      field's doc in 0x12f_room_create.ksy): two independent room types
      (party creation, game-room creation via find-match self-host) both
      showed the gate register at 0, meaning the OR never fired in either
      sample, and the observed top-nibble variation must come from the raw
      `+0xe8` value itself, not this conditional. Given the identical
      construction, that reading likely transfers here too, but `r10`'s
      value has not been independently live-checked for this specific
      function - treat as a strong inference, not a confirmed result.
  - id: value_pair_14
    size: 4
    doc: "Offset 20:24. The 0x03e8/0x03e8 (1000/1000) u16 pair, same source as RoomCreate's value_20/value_22 (the two float out-params of _opd_FUN_00acb6bc, fctiwz->sth). Likely a default rating pair; disabled/constant in all live captures."
  - id: burst_marker
    type: u2
    doc: |
      Offset 24:26 (wire 0x18). BURST/criteria marker = the sender's own 3rd
      argument (`mr r31,r5` @ 0xad6cc8, `sth r31,168(r1)` @ 0xad6d28).

      CORRECTED 2026-08-20: it is NOT "a caller-supplied criteria index". It
      is the criteria row's OWN first column. The find-match state machine
      indexes the DC global `*net-matchmaking-criteria*`
      (`crc32_mpeg2` `0xB25AB071`) by an attempt counter, stride 20
      (`mulli r9,r9,20` @ 0x3b60c8 in 01.00's `FUN_003b5ff4`), and passes
      `criteria[attempt] + 0x00` straight through as this field
      (`lwz r26,0(r9)` @ 0x3b61d4, `extsw r5,r26` @ 0x3b6200). That is why
      the value repeats across consecutive searches instead of counting up.

      The record is
      `{+0x00 burst_marker, +0x04 send_locale, +0x08 give-up threshold,
      +0x0c type_hash, +0x10 window half-width}`; `+0x08` is read by the
      second consumer `FUN_003b6584` (`lwz r0,8(r9)` @ 0x3b681c, `cmpw` /
      `bge -> give up and self-host` @ 0x3b6828).

      **The marker values are BUNDLE-specific, not comparable across
      builds** - they are data, and the served `netN.bin` decides them:

          dc1/net.bin (01.00), count 5,  array 0x197f4:  markers 5, 10, 10, 0, 0
          net10.bin   (01.11), count 21, array 0x1359c:  markers 35 x6, 50 x10,
                                                         70 x3, 0 x2

      Every marker on the wire across all 2,188 captured `0x135` frames is a
      marker column of one of those two tables. The stub keys its serialized
      election on marker==5 (01.00 criteria row 0 = a fresh burst start) -
      see the doc note above; that key is bundle-specific and does not hold
      for a client served net10.bin.
  - id: pad_1a
    size: 2
    doc: "Offset 26:28. Uninitialised padding. DEFINITION: an unwritten 2-byte gap after burst_marker, before the search-window pair. REASON: FUN_00ad6c70's store enumeration (base r1+144) has no store to 170(r1) = wire 26; it captures as 0. Send 0. (This offset plus search_window_lo/hi below were once a single field wrongly named `pad_1a`.)"
  - id: search_window_lo
    type: u2
    doc: |
      Offset 28:30. `max(0, rank_value - param_6)` when `rank_value >= 0`,
      else 0 (`subf/not/srawi/and` clamp @ 0xad6d90-0xad6dc4). The low end of
      a matchmaking rank window.

      SOLVED 2026-08-20. Two earlier readings were both wrong: "0 in all live
      captures" (drawn from too small a sample) and then "a per-account
      quantity that climbs with play, source not identified". A census of all
      2,188 captured `0x135` frames in `server/logs/wire.jsonl` finds the
      pair nonzero in 653, and every nonzero pair decomposes exactly against
      the clamp as either a point window at `rank_value` or
      `rank_value +/- 60`:

          (397,397) x198  (337,457) x91   -> rank_value = 397
          ( 29, 29) x179  (  0, 89) x82   -> rank_value = 29 (lo clamped to 0)
          ( 31, 31) x31   (  0, 91) x23   -> rank_value = 31
          (365,365) x18   (305,425) x10   -> rank_value = 365
          (373,373) x15   (313,433) x6    -> rank_value = 373

      **The half-width is a DC column, not a constant in the code.**
      `param_6`/`param_7` are `*net-matchmaking-criteria*`'s `+0x10`
      (see `burst_marker`): 5/10/0 on `dc1/net.bin`, and 60 or 0 on
      `net10.bin`, where exactly the rows with marker 35 or 50 carry 60. That
      is where the observed `+/-60` comes from, and it is why the same client
      alternates a widened and a point probe.

      **`rank_value` is the game's own name for the centre.** The 01.11
      producer prints it: the format string at `-32372(r30)` on that path is
      `"------------------Use rank value of %d\n"`, passed the same register
      that becomes `param_5` two instructions later.

      **Where it comes from depends on the build**, and the two builds are
      cleanly separated in the capture (the marker families never mix within
      one server run, and the 01.11-era frames additionally carry a nonzero
      attempt counter at offset 26 and a different fixed header, which the
      01.00 sender never writes):

      * **01.00 (the primary EBOOT): structurally 0.** The producer at this
        call site is `FUN_003b3898` (`mr r23,r3` @ 0x3b612c), which returns
        `*playlists*` row `+0x50` and 0 when that is `<= -1`. `+0x50` is
        `-1` for every real matchmaking row in both bundles, so the function
        returns 0 for every playlist. All 1,535 captured frames from 01.00
        senders have `(0,0)`, without exception.
      * **01.11 only: a career kill/death ratio, x100.** See the note below.

      The 01.11 producer is inline in `FUN_003cfd90` (**01.11 EBOOT**,
      `TLOU-FACTIONS 1.11/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf`; the
      01.00 EBOOT has no equivalent code, which is exactly why this field is
      dead there - 01.11 is cited here ONLY for behaviour that does not
      exist in the primary build, and none of its addresses transfer):

          3cff10  bl 0xa22108           ; DC lookup of hash 0xB4744777
          3cff1c  lwz  r0,0(r3)
          3cff20  cmpwi cr7,r0,1
          3cff24  beq  cr7,0x3cff38     ; == 1 -> the ratio branch (live)
          3cff28  add  r9,r28,r29       ; else (P+0x1E34 + P+0x1E38) / 7
          3cff2c  li   r0,7
          3cff30  divw r31,r9,r0
          ; ---- ratio branch ----
          3cff4c  lbz  ... 852(r10)     ; P+0x0354  downs_dealt   (mode 3)
          3cff84  lbz  ... 832(r10)     ; P+0x0340  downs_dealt   (mode 2)
          3cffac  add  r29,r29,r0
          3cffc4  lfs  f0,-32360(r30)   ; = 100.0
          3cffc8  fmuls f31,f31,f0
          3cffdc  lbz  ... 856(r10)     ; P+0x0358  downs_taken   (mode 3)
          3d000c  lbz  ... 836(r3)      ; P+0x0344  downs_taken   (mode 2)
          3d0038  add  r29,r29,r0
          3d0050  fdivs f31,f31,f0
          3d0054  fctiwz f31,f31        ; -> rank_value
          3d0060  extsw r4,r31          ; -> the "Use rank value of %d" print
          3d0128  extsw r7,r31          ; -> param_5 of the 0x135 sender

      `r10` is the profile block (`bl 0x3e6adc`, which returns `obj + 0xC8`);
      the fallback branch's `P+0x1E34`/`P+0x1E38` are `profile_21.ksy`'s
      already-named `matches_mode_a`/`matches_mode_b`, which is what pins the
      base. So:

          rank_value = (int)( 100.0 * (downs_dealt[0] + downs_dealt[1])
                                    / (downs_taken[0] + downs_taken[1]) )

      i.e. **a career kills-to-deaths ratio in percent**, summed over both
      game modes, from `profile_21.ksy`'s `career_stats` records (which this
      pass decoded from the primary 01.00 EBOOT's OnMatchEnd writer).

      The DC gate `0xB4744777` exists ONLY in `net10.bin` (word 0 = 1, so the
      ratio branch is the live one); it is absent from `dc1/net.bin` and from
      the 392-record 01.00 directory, and no `.dci` symbol in the retail
      disc's compiler-symbol corpus reverses to it, so it is unnamed.

      Numerically verified against the two stored profiles:
      `comradesean` 100*(166+46)/(36+19) = 385, `mgnomad2`
      100*(32+18)/(133+42) = 28 - against wire values of 397/373/365 and
      29/31 recorded a day earlier, and the direction of travel matches
      (comradesean's dropped 397 -> 373 -> 365 within one session while he
      accumulated deaths). Note this also corrects "climbs with play": it is
      a ratio and moves both ways.

      Was the middle of `pad_1a`.
  - id: search_window_hi
    type: u2
    doc: |
      Offset 30:32. `rank_value + param_7` when `rank_value >= 0`, else 0
      (same clamp). The high end of the rank window; `param_7` is the same
      `*net-matchmaking-criteria*` `+0x10` half-width as `param_6`. On 01.11
      the two are literally the same register (`extsw r8,r24` @ 0x3d010c then
      `mr r9,r8` @ 0x3d0140, **01.11 EBOOT**), which is why every widened
      pair in the capture is symmetric. See `search_window_lo` for the full
      derivation of `rank_value`, the census, and the build split. Was the
      tail of `pad_1a`.
  - id: locale
    size: 4
    doc: "Offset 32:36 (wire 0x20). Region/language, zeroed by default (`stw r26,176(r1)` @ 0xad6d1c) and overwritten with region|language only when param_4 != 0. Live `75 73 00 01` = 'us\\0' + language 1 on criteria-0 searches (same as RoomCreate's region_language); later criteria in a burst send zeros here."
