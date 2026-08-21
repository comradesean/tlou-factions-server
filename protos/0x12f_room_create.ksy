meta:
  id: room_create
  endian: be
  license: CC0-1.0
  imports:
    - common/member_data
doc: |
  Direction: client-to-server

  NetMatchmakingRoomCreate - sent by the client over the Session Manager
  connection (port 7314) when the player chooses to host a game. Fixed 232
  bytes, matching the opcode/size debug table exactly.

  STATUS (rewritten 2026-08-16): the send site is now fully disassembled -
  `FUN_00ad5b78` (SessionManager vtable +0x10), confirmed by its `li r0,303`
  opcode literal at 0x00ad5c38 and its
  `_opd_FUN_00acb93c(this+0x25060, buf, 0xe8, 1)` send call at 0x00ad5fac.
  The send buffer's base is `r1+144`, so wire offset = (r1 offset) - 144.
  EVERY store into that buffer was enumerated exhaustively from the
  disassembly and then cross-checked against 30 live RoomCreate captures in
  captures/tcp_catch.log. See
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 4 for the full table and the raw instruction evidence.

  THE SENDER'S OWN CALLERS - RESOLVED 2026-08-20 (static; see
  research/notes/2026-08-20-followup-open-items.md section 1). `FUN_00ad5b78`
  is reached only through a `bctrl` on vtable slot `+0x10`, invisible to a
  direct-`bl` scan. Resolved by locating the function's `.opd` descriptor
  (`0x012E9C40`, the unique occurrence of `0x00AD5B78` in the image) and then
  the unique occurrence of THAT address, `0x01243B48` = vtable base
  `0x01243B38` + 0x10 - the same base whose `+0x20`/`+0x34` are `0x13e`'s two
  builders, which self-checks the identification. That vtable belongs to the
  ND Session Manager (`ndlib/net/net-session-manager-nd.cpp`), installed by
  the constructor `FUN_00ad84cc` (`stw r0,0(r3)` @0xad8500) whose instance is
  stored into the global `0x014DB270` (`stw r28,0(r9)` @0x3562cc). A sibling
  LAN implementation shares the interface at vtable `0x01243AE8`
  (`+0x10` = `FUN_00ad512c`).

  THREE call sites dispatch through that slot. Two were found by the static
  `bctrl`-pattern scan, both passing `param_2 = 0x01383BD8` (the GAME ROOM
  object):
    - `0x0035D440`, in `FUN_0035D1FC` - the state that logs `"Host"`.
    - `0x003B7FB0`, in `FUN_003B7D70` - the state that logs
      `"****** GATHER ******"`.
  The third is the PARTY path (`0x003CAC5C`, `param_2 = 0x01387F58`), which
  that scan's search window did not cover; it is documented in its own
  section below. All three sites' arguments are decoded field-by-field in
  the docs below (`max_players`, `caller_arg_1c`, `is_party`,
  `room_flags_e8`).

  THE INTERFACE TAKES A SEVENTH ARGUMENT THIS IMPLEMENTATION IGNORES. Both
  call sites set `r9` before the `bctrl`; at the GATHER site it is the
  party-wide capability AND-reduce `FUN_00ad2b14(0x01387F58)` (see
  common/member_data.ksy's `capability_flag`). `FUN_00ad5b78` never reads
  `r9` - its first write is `clrldi r9,r11,32` @0xad5be4 - and neither does
  the LAN sibling. So the lobby-common capability mask is computed at
  RoomCreate time and then DISCARDED on this path; it never reaches the wire.
  The sibling RoomJoin builder (vtable `+0x14`, `FUN_00ad6c70`) is called with
  the same 7-argument shape at `0x003B6230`.

  THE PARTY'S ROOMCREATE - RESOLVED 2026-08-20, LIVE (RPCS3 breakpoint at
  `0xad5b78` during a real party join). Register state at entry: `r3` (this)
  `= 0x337238A0` (matches `*(0x014DB270)`, the same ND Session Manager
  singleton the two static sites use), `r4` (room) `= 0x01387F58` (the PARTY
  object), `r5` (max_players) `= 8`, `r6` (`is_party` source) `= 1`, `r7`
  (`caller_arg_1c` source) `= 0xFFFFFFFF`, `r8` (`room_flags_e8` gate)
  `= 0`, `r9` (the discarded 7th argument) `= 0`. `LR = 0x003CAC60`, the
  return address, pins the call site exactly - this is a THIRD dispatch the
  static `bctrl`-pattern scan's search window did not cover, not a reachable-
  by-the-two-known-sites case.

  The call site is `0x003CAC5C` (`bctrl` at `ld r2,40(r1)` immediately after
  @`0x3cac60`, matching `r5=0xE8`=232=this message's own declared size held
  live in the return-site register dump - independent confirmation this is
  really the RoomCreate call), inside **`FUN_003CA9D0`** - the SAME 9-state
  room-state-machine function `protos/0x13f_host_flag_updated.ksy` and
  `docs/protocol/proto-map.md` already cite as gating a block on
  `room_obj+0x19f4`. It dispatches via a `bctr` jump table at `0x003CAA9C`
  (9 entries, offsets relative to the table base `0x003CAA9C`); the call is
  in the block reached by table entry 1 (offset `0xE4`, landing at
  `0x003CAB84`), specifically its `party_obj+0x1A50 == 0` branch
  (`ld r28,6736(r31); cmpdi cr7,r28,0; beq -> 0x3cac00` @`0x3cabb0`-
  `0x3cabb4`) - i.e. this fires when the party object has not yet had a room
  created for it. That branch is only reached when the counted-match latch
  is clear (`bl 0x3abf68` @`0x3cab8c`, the already-documented `g_70[0x6C]`
  "this match counts" accessor - see `research/notes/2026-08-17-match-counts-
  latch.md`; `bne -> 0x3cb130` skips the whole block if a match is currently
  counting).

  This also resolves the two field gaps the two static sites left open:
  **`is_party`'s live `0x04`** comes from here - `r6=1` at this site, and
  `is_party = 4 iff param_4 != 0` (see that field's own doc), so `1 != 0`
  produces the wire `4`. **`caller_arg_1c`'s live `0xffff`** is confirmed
  again here too (`r7 = 0xFFFFFFFF`, same as both static sites - this is
  evidently a constant across every known call site, not path-specific).
  `room_flags_e8`'s OR-gate is off here (`r8=0`), consistent with both other
  sites. Full trace: `research/notes/2026-08-20-followup-open-items.md`
  section 1 update.

  THREE CORRECTIONS to the previous version of this file, all high
  confidence:

  1. There is NO `create_id` at offset 4. Offsets 4:8 are never written by
     the sender - no store to `148(r1)` exists anywhere in the function - so
     they carry uninitialised stack. The live captures prove it directly:
     the same client emits `01 27 23 d8` there in one session and
     `00 00 00 00` in the next with every other field identical. The
     8-byte room id this protocol family uses everywhere else is the
     SERVER's to choose; RoomCreate does not supply one.

  2. Offset 8 is a 4-byte raw pointer to the CLIENT'S OWN room object
     (`stw r29,152(r1)` at 0x00ad5f34, where r29 is this function's own
     `param_2`/room object). This is the same value `Member` (0x131) wire
     offset 8 must echo back and immediately dereferences through an
     unchecked vtable call. Live-proven: comradesean's client sends
     `01 38 3b d8`, which is byte-for-byte the address a live RPCS3
     debugger breakpoint previously recovered and which
     server/session_manager.py hardcodes as ROOM_PTR; a second real
     client (mgnomad2) sends `01 38 7f 58`. Read it off this field per
     connection instead of hardcoding it.

  3. max-players/capacity is at offset 0x24, NOT 0x1e. Offset 0x1e is
     another never-written gap (between the `sth ...,172(r1)` and
     `sth ...,176(r1)` stores) and reads as stack leftovers - `00 0a` or
     `00 00` across the captures. Offset 0x24 is `sth r23,180(r1)`, and the
     same r23 is simultaneously written to `room_obj+0x1f8` at 0x00ad5f80 -
     the exact field `_opd_FUN_00ad33d8`'s compiled-in capacity assert
     checks. Live-constant `00 08` in every capture.
doc-ref: ../docs/protocol/0x12f_room_create.md
seq:
  - id: opcode
    type: u4
    doc: "Offset 0. Fixed 0x12f (303 decimal). `stw r0,144(r1)` @ 0x00ad5c40."
  - id: pad_4
    size: 4
    doc: "Offset 4:8. NEVER WRITTEN by the sender - uninitialised stack. Previously and wrongly documented as an 8-byte `create_id` spanning 4:12. Do not read anything from here; live captures show it varying between `01 27 23 d8` and `00 00 00 00` on the same client across sessions."
  - id: room_ptr
    type: u4
    doc: "Offset 8:12. The client's own in-process room-object pointer, copied verbatim (`stw r29,152(r1)` @ 0x00ad5f34). THIS is where a server gets the value it must echo into Member's (0x131) own offset-8 room_ptr field. Differs per client - live-captured as 0x01383bd8 (comradesean) and 0x01387f58 (mgnomad2)."
  - id: room_field_0c
    type: u4
    doc: |
      Offset 12:16. Verbatim copy of `*(u32*)(room_obj + 0x0c)` (`lwz r0,12(r31)`
      / `stw r0,156(r1)` @ 0x00ad5f30).

      DEFINITION: the PLAYLIST ID. A playlist is a DC record that bundles the
      game MODE with its PARTY RULES, so this one field covers what the UI
      presents as two separate choices. The table ships inside the netN.bin
      config bundle, which is why the numbering is PER BUILD. The binary asserts
      `(playlist & 0xFFFFFF00) == 0` (VMA 0xe9fa28 in 01.11) - one byte.

      REASON it exists: it is the matchmaking key. A searcher asks for exactly
      one playlist in 0x135, and the elected host stamps that same id on the
      room it creates, so the server can advertise a room only to searchers
      wanting that playlist.

      PRIVATE-MATCH VALUE RESOLVED 2026-08-21, LIVE (RPCS3 memory
      write-breakpoint on `room_obj+0xc` = `0x1383be4`, PPU Interpreter mode
      required - the default LLVM recompiler does not enforce memory
      breakpoints at all, which is why the first attempt silently never
      hit). It IS genuinely random, drawn from a small candidate pool at
      RoomCreate time - not residue, not a hidden correlate. Full register
      dump and disassembly at the hit:

        CIA=0x00ad0c9c: `stw r4,12(r3)` - a 3-instruction generic field
        setter (`obj->+0xc = val; return 0;`). `r3=0x01383bd8` (this
        session's room object, confirming this write targets the SAME
        singleton the sender later reads), `r4=0x9` (exactly the private
        `field_0c` value already known from tonight's sweep).

        LR=0x0035d3f4, return address into `FUN_0035D1FC` - the SAME
        function that owns this doc's already-documented `"Host"`
        RoomCreate call site at `0x0035D440`; this write is 0x50 bytes
        BEFORE that call, in the same function, so it is pinned to the
        PRIVATE-match `"Host"` path specifically, not a generic/shared
        setter used elsewhere. The caller code (VMA 0x35d3b8-0x35d3f4):

          lwz r11,0(r29)      ; r11 = candidate_desc->count
          bl 0xe408d8         ; r3 = rng_next()
          mr r9,r3
          mr r3,r26           ; r3 = room_obj (for the call below)
          divw/mullw/subf     ; r9 = rng_result % count   (classic modulo)
          slwi r9,r9,2 ; add r9,r28  ; r9 = &candidate_desc->table[idx]
          lwz r4,0(r9)        ; r4 = table[idx]
          bl 0xad0c9c         ; room_obj->field_0c = table[idx]

        `r29` (`= 0x4309de6c` live) points to an 8-byte descriptor -
        `{count:u32, table_ptr:u32}` - read live as `{2, 0x430b062c}`.
        The table itself, read live at `0x430b062c`: `00 00 00 09  00 00
        00 13` - i.e. literally `{0x09, 0x13}`, the exact two values this
        project has captured all session. `0xe408d8` is a lazily-seeded
        LCG PRNG (`x = x*1664525 + ~1013904223`, the textbook "Numerical
        Recipes in C" constants - `0x19660D` = 1664525 is the multiply
        immediate at `0xe408fc`/`0xe40928`).

        This whole random-pick block is itself CONDITIONAL - guarded a
        few instructions earlier (`0x35d3ac`-`0x35d3b4`) by a flag global
        (`*(r2-31180)` anchor `-32572`, live address `0x1268714` this
        session) being nonzero; when false, the block (and this write) is
        skipped entirely, meaning the private-match room keeps whatever
        `field_0c` a PRIOR create on the same singleton object left there
        - which is exactly why some reloads of the identical map came back
        with the SAME value as the previous round (`field_0c` is only
        re-randomized on the sessions where this gate is true, otherwise
        it free-runs as literal object residue from the last randomize).
        What that gate flag specifically means was not chased further
        this pass. The 25-round sweep's `AAAAABBAABBBBBAA | ABAAAABA`
        streaky-but-not-periodic pattern is exactly what you'd expect from
        a real PRNG occasionally gated off (streaks = gate false, holding
        the previous roll; flips = gate true, re-rolling) - consistent
        with theories 1 and 2 below both being partially right, not
        competing explanations.

        PRACTICAL UPSHOT for a server: this field is NOT meaningful for
        private matches - it is cosmetic/internal client state, safe to
        ignore entirely as long as it is never mistaken for a real
        matchmaking playlist id (see the `NON_MATCHMAKING_PLAYLISTS`->
        allowlist fix in server/session_manager.py, which already made
        this assumption independently and correctly).

      WHY IT'S RANDOM AT ALL: two things point at this being incidental,
      not a deliberate feature. First, `FUN_0035D1FC` runs this EXACT
      random-pick-from-descriptor-table pattern TWICE in a row for two
      DIFFERENT fields (a different setter at `0xad3a00` immediately
      before this one, targeting a different object) - a generic "pick one
      at random from a small candidate table" utility being reused, not
      something bespoke for the playlist slot. Second, `0x09`/`0x13` are
      not real 01.00 matchmaking playlist ids (those are `2`/`3` only,
      confirmed elsewhere in this doc) - they live in the same
      "non-matchmaking sentinel" space this doc already documents for
      `0x58`(party)/`0x5a`/`0x63`(01.11 private), just 01.00's own reserved
      pair. Put together: a private "Host" never runs a real matchmaking
      search, so nothing legitimately populates this field. Rather than
      leave raw uninitialised residue (risking the `(playlist &
      0xFFFFFF00) == 0` one-byte assert, or confusing anything downstream
      expecting a valid-shaped id), the client falls back to stamping a
      harmless placeholder drawn at random from a small reserved pool of
      known-not-a-real-playlist sentinels. The randomness is a side effect
      of reusing a generic fallback-fill utility, not a designed feature -
      which is also exactly why nothing ever correlated with it.

      WHAT `0x09`/`0x13` SPECIFICALLY MEAN: NOT RECOVERED, and a lead that
      looked promising was chased and retracted the same session. The
      live descriptor (`r27=0x4309de6c` -> `{count=2,
      table=0x430b062c={0x09,0x13}}`) is heap state, not a static EBOOT
      address, so its ultimate source wasn't traced further. A byte-exact
      `{0x09,0x13}` (and an adjacent `{0x08,0x12}`) WAS found in the
      decrypted `net1.bin` DC00 bundle at file offset `0x1806c`, initially
      reported as "confirmed" via a repeating 4-byte value
      (`1ed2e0a2`) that also appeared next to a live matchmaking-path
      register dump - RETRACTED on closer check: that 4-byte value
      recurs literally thousands of times across a huge unrelated stretch
      of the file (character-customization color/geometry tables,
      `cc-*`/`mp-*` entries), i.e. it is a common generic type-tag, not a
      distinctive marker, and neither of `*playlists*`'s own two real
      sub-lists (tags `2a8027cf`, `ee949ef7`) use it. So the net1.bin
      match is most likely coincidence, not a real link - decrypt method
      for reference (works for any served `*.psarc.crypt`):
      `psarc_crypt.decrypt_crypt_file()` -> `parse_psarc()` -> the single
      `net1.bin` entry -> `research/tools/dc_dir.py --list/--show`.

      This resolves the "private-match field_0c" open question as far as
      MECHANISM goes (proven, live, instruction-level) - the specific
      sentinel values remain cosmetic and unexplained, which does not
      matter for a server (see practical upshot above).

      THE MATCHMAKING-SIDE WRITE - ALSO RESOLVED 2026-08-21, LIVE, same
      breakpoint (`0xad0c9c`), a SEPARATE hit during a real Find Match
      search: `r3=0x01383bd8` (same room object), `r4=2` (Supply Raid's
      real 01.00 playlist id), `LR=0x0035b07c`, inside `FUN_0035ADB4`
      (a DIFFERENT function from the private "Host" path). This finally
      instruction-verifies the "elected host stamps the playlist"
      claim the correction below flagged as inference-only. Two calls to
      the same generic setter appear in sequence here (`0x35b024` then
      `0x35b078`, the caught one) - the second is gated behind the exact
      same flag global (`*(r2-31180 anchor)-32572`) the private path's
      re-roll used, and its value is built from fields of a live object
      (`r26=0x430b23e4`) rather than a fixed literal, i.e. genuinely
      derived from the current search/mode selection, not hardcoded -
      consistent with this being the real per-mode playlist lookup. Not
      pursued further into `FUN_0035ADB4`'s own internals this pass (the
      night's goal was the private-match mystery, now closed); worth a
      dedicated follow-up if the exact selection logic (how the mode maps
      to `2` vs `3`) is ever needed.

      MODE-CORRECTNESS CONFIRMED TWICE, LIVE: a second capture, Survivors
      -> Find Match, hit the identical site (`CIA=0xad0c9c`,
      `LR=0x0035b07c`) with `r4=3` - Survivors' real 01.00 playlist id -
      versus the Supply Raid capture's `r4=2`. Both real ids, both
      mode-correct, same call site. (`r9` differed between the two
      captures - count `2` for Supply Raid, `3` for Survivors, both
      followed by the ubiquitous `1ed2e0a2` tag - but the disassembly
      traces `r4`'s actual source to `r26`'s own fields, not `r9`, and
      `1ed2e0a2` is now known to be non-distinctive per the retraction
      above, so this is most likely unrelated adjacent heap state, not
      part of the real selection path - noted for completeness, not read
      into further.)

      CORRECTION 2026-08-21: "the elected host stamps that same id" has
      never actually had a WRITE instruction located and cited - only the
      READ site at the bottom of this doc's opening paragraph (`0xad5f30`,
      shared with every other case of this field, private matches
      included). The claim was inferred purely from correlation - a
      matchmaking host's `field_0c` reliably equals a real playlist id - not
      from finding the store instruction that puts it there. An exhaustive
      static write-scan for ANY writer to `room_obj+0x0c` across the whole
      01.00 EBOOT (2026-08-21, three independent search strategies - see
      the private-match section below for the full method and result) found
      none, for either the matchmaking or the private case. That doesn't
      disprove the matchmaking stamp - the field demonstrably DOES change
      value during a live session, so something writes it - it just means
      this project has never actually pinned down where, for any code path,
      not just the private one.

      01.11 TABLE - all nine live-confirmed 2026-08-19, each verified on BOTH
      sides (the searcher's 0x135 and the host's 0x12f stamp):

        playlist  mode           style
           1      Supply Raid    Parties Allowed
           2      Supply Raid    No Parties
           3      Supply Raid    DLC
           6      Survivors      Parties Allowed
           7      Survivors      No Parties
           8      Survivors      DLC
          11      Interrogation  Parties Allowed
          12      Interrogation  No Parties
          13      Interrogation  DLC

      Each mode owns a FIVE-slot block starting at 1, 6, 11 and uses the first
      three; 4/5, 9/10 and 14/15 are unused capacity, not missing content. Id 0
      has never been observed and reads as a none/invalid sentinel.

      01.00 had only TWO playlists, 2 and 3 - one per mode, because that build
      shipped no style variants. So id 3 means Survivors on 01.00 but Supply
      Raid/DLC on 01.11. IDS ARE NOT COMPARABLE ACROSS BUILDS, which is why
      matchmaking must be segregated by build as well as by playlist
      (server/session_manager.py CLIENT_BUILDS).

      NON-MATCHMAKING LOBBIES use their own ids in the same one-byte space:
        0x58 (88)  party room (observed on the party object, consistent)
        0x5a (90)  seen repeatedly on private-match GAME room creates
        0x63 (99)  seen repeatedly on private-match GAME room creates

      CORRECTED 2026-08-21 (re-checked directly against
      server/logs/session_manager.log and server/logs/wire.jsonl, not just
      the earlier note's small sample): `0x5a` was previously written up as
      "seen once," and `0x63` as "the same constant across two modes, so not
      mode-specific." Both undersold what the fuller log shows: the SAME
      private-match GAME room object (`room_ptr=0x13babd8`, same host
      `comradesean`) was re-created eight times over eight minutes on
      2026-08-19, and `field_0c` alternated `0x5a`/`0x63` with no clean
      pattern (`5a,5a,63,63,5a,63,63,63`).

      FIRST HYPOTHESIS TESTED AND NOT CONFIRMED: that the alternation simply
      tracks which map/mode was actually being played. Cross-referencing
      each RoomCreate's own `common/member_data.recent_level_0` (the host's
      most-recently-played-map ring, same 32-byte blob, offset 10:12) shows
      real map/mode changes DID happen between these re-creates - this was
      not an idle "nothing else changed" sequence:

        04:08:40  field_0c=0x5a  recent_level_0=0xffff (unset - first match)
        04:10:56  field_0c=0x63  recent_level_0=0x0f (Lakeside, Supply Raid)
        04:12:18  field_0c=0x63  recent_level_0=0x20 (Lakeside, Survivors)
        04:13:29  field_0c=0x5a  recent_level_0=0x1f (Checkpoint, Survivors)
        04:14:25  field_0c=0x63  recent_level_0=0x21 (Bill's Town, Survivors)
        04:15:24  field_0c=0x63  recent_level_0=0x22 (University, Survivors)
        04:16:15  field_0c=0x63  recent_level_0=0x23 (High School, Survivors)

      So across four consecutive SURVIVORS-mode private matches (Checkpoint,
      Bill's Town, University, High School - `recent_level_0` 0x1f-0x23),
      `field_0c` was `0x5a` once (Checkpoint) and `0x63` the other three
      times. It does not track mode (four same-mode matches, two different
      field_0c values), and it does not obviously track the specific map
      either (Checkpoint got 0x5a here, but Checkpoint was also captured
      under 0x63 in a separate session - see the original 00:55:23/01:01:29
      pair in git history of this doc). NEITHER "stable per-mode constant"
      NOR "pure residue independent of game state" is fully supported by
      this data; the honest status is UNRESOLVED, not closed either way.
      STILL UNTESTED: whether it correlates with something not yet
      correlated here - lobby PARTY-SIZE setting, "Parties Allowed / No
      Parties / DLC"-style option (the matchmaking-only styles proven for
      playlists 1-13 may have an unlabeled private-lobby analogue), or
      per-round elapsed/retry state. A server must never advertise any of
      these values in the find-match list regardless of what they mean.

      FULL 01.00 SWEEP, 2026-08-21 (comradesean + mgnomad2 party, build
      01.00 throughout, room_ptr constant at `0x1383bd8` the entire
      session). A deliberate map-by-map, mode-by-mode private-match sweep -
      every Supply Raid map, twice each, then every Survivors map once
      (01.00 has no Interrogation - confirmed live tonight, not just
      inferred). `field_0c` values are `0x13` (19) or `0x09` (9) only, no
      other value seen this session (the 01.00 space is disjoint from the
      01.19 `0x5a`/`0x63` pair documented above - a different session,
      different day, same room object address by chance of reuse, but note
      the 01.19 run above was on build 01.11, not 01.00 - BUILD SEPARATION
      applies here too). Full round-by-round record (map id from
      `member_data.recent_level_0`, independently confirmed correct every
      round via the continuation model in `protos/common/member_data.ksy`):

        SUPPLY RAID
        03:07:13  Checkpoint                field_0c=0x13  map=0x0e
        03:10:52  Lakeside                   field_0c=0x13  map=0x0f
        03:15:11  Bill's Town                field_0c=0x13  map=0x10
        03:16:26  University                 field_0c=0x13  map=0x11
        03:18:14  High School                field_0c=0x13  map=0x12
        03:20:35  Downtown                   field_0c=0x09  map=0x13
        03:22:06  The Dam                    field_0c=0x09  map=0x14
        03:24:24  Checkpoint (reload)        field_0c=0x13  map=0x0e
        03:25:46  Lakeside (reload)          field_0c=0x13  map=0x0f
        03:26:41  Bill's Town (reload,       field_0c=0x09  map=0x10
                   loadout screen visited)
        03:28:06  Bill's Town (reload,       field_0c=0x09  map=0x10
                   loadout visited again)
        03:29:20  Bill's Town (reload,       field_0c=0x09  map=0x10
                   loadout NOT touched)
        03:29:57  University (reload)        field_0c=0x09  map=0x11
        03:30:55  High School (reload)       field_0c=0x09  map=0x12
        03:31:47  Downtown (reload)          field_0c=0x13  map=0x13
        03:32:50  The Dam (reload)           field_0c=0x13  map=0x14
        03:38:51  [Find Match search, cancelled, then Private->The Dam]
                   field_0c=0x09  map=0x14  - CONFOUNDED, exclude from
                   pattern analysis: this create also tripped the
                   NON_MATCHMAKING_PLAYLISTS denylist bug (fixed same
                   session, see server/session_manager.py) and was
                   misregistered PUBLIC/matchmade, so its surrounding state
                   is not comparable to the clean rounds.

        SURVIVORS (same client session, no restart, switched mid-sweep)
        03:40:52  Checkpoint                 field_0c=0x13  map=(stale
                   read this round, 0x15 from a pre-load snapshot -
                   member_data ring not yet settled; field_0c itself is
                   still a clean direct read, only the map-id cross-check
                   for THIS round is unreliable)
        03:47:15  Checkpoint (reload)        field_0c=0x09  map=0x15
        03:50:39  Lakeside                   field_0c=0x13  map=0x16
        03:51:36  Bill's Town                field_0c=0x13  map=0x17
        03:53:21  University                 field_0c=0x13  map=0x18
        03:54:43  High School                field_0c=0x13  map=0x19
        03:56:15  Downtown                   field_0c=0x09  map=0x1a
        03:57:26  The Dam                    field_0c=0x13  map=0x1b

      As a binary string in round order (excluding the confounded round),
      A=0x13, B=0x09: AAAAABBAABBBBBAA | ABAAAABA
      (space marks the Supply-Raid/Survivors mode switch). 15 A / 9 B out
      of 24 clean rounds - not nose-to-tail with either value, not a fixed
      period, and no clean correlation found yet against: current map,
      current mode, round count within a streak (Downtown broke the streak
      at round 6 in BOTH the Supply Raid and Survivors runs, but the
      following round diverged - Supply Raid stayed 0x09 for round 7, Survivors
      flipped back to 0x13 - so "6th create in a run" is not the trigger
      either), loadout-screen visits (ruled out directly: round 12 got the
      same 0x09 as rounds 10-11 despite NOT visiting the loadout screen),
      or a preceding Find Match search (ruled out: the search's own
      playlist id, e.g. 0x02, never appeared - the confounded round still
      read 0x09, from the SAME `{0x13, 0x09}` pool as every other round,
      not something new). Wall-clock gaps between creates were checked for
      a fixed period at each flip point (55s, 141s, 138s, 52s, 92s, 71s,
      ...) - no consistent modulus found, so a simple fixed-interval timer
      is not obviously it either, though a more complex time-dependent
      process isn't ruled out.

      RESOLVED 2026-08-21 - see the write-site trace earlier in this doc
      (live memory write-breakpoint). The theories below are kept for the
      record; (1) and (2) both turned out partially right (a real 2-entry
      RNG-picked pool that only re-rolls when a separate gate flag allows
      it), (3) is not it (no timer, a PRNG).

      THEORIES, none confirmed [pre-resolution, kept for the record]:
        1. UNRELATED CODE PATH LEAVES RESIDUE HERE. Since this field is a
           READ of a persistent room-object slot the private-match create
           path itself never appears to write (per the mechanism already
           established below), the value may simply be whatever some
           OTHER, unrelated system last wrote to that same object offset -
           a UI screen, a menu transition, an animation/HUD counter, or
           something in the party-sync path (a second player, mgnomad2,
           was active in the party for the whole Survivors run and part of
           the Supply Raid reload run - his own client-side actions were
           not logged move-by-move, so cannot yet be ruled in or out as a
           trigger).
        2. TWO-STATE TOGGLE, not free-running residue. Only ever `0x13` or
           `0x09` all session (never 0x00, never garbage) argues against
           classic uninitialized-stack noise (which would be expected to
           show more variety) and toward a real, intentional two-valued
           flag somewhere being read - just not one this project has
           identified the source of yet.
        3. FRAME/TIMING-DEPENDENT STATE sampled at create-time. Streaks
           correlate loosely with short real-world gaps between creates,
           flips more often follow longer gaps - consistent with a
           slow-moving counter/timer whose value only changes when enough
           real time or ticks pass, but the wall-clock check above didn't
           find a clean period, so this is weakly suggestive at best.

      RESEARCH PLAN [SUPERSEDED 2026-08-21 by the live write-breakpoint
      resolution above - kept for the record, not actionable anymore]:
        A. STATIC WRITE-SCAN - ATTEMPTED 2026-08-21, NEGATIVE RESULT. Three
           independent, largely-exhaustive search strategies against the
           01.00 EBOOT: (1) address-anchored scan - found all 18 literal-
           pool slots holding the room object's constant address
           `0x01383bd8`, then 197 load sites across `.text` that reload it,
           forward-scanned every containing function to its end for a
           store at displacement 12 off that register - zero hits (the
           method's soundness was cross-checked: it DID correctly surface 3
           previously-undocumented plain READS of `+0xc`, so it isn't
           simply failing to find anything at that offset). (2) parameter-
           threading scan - since the known reader (`FUN_00ad5b78`)
           receives `room_obj` as an argument rather than a fresh pool
           load, grepped for every `st{w,b,h} rX,12(r31)` in the plausible
           code regions (111 raw hits, 72 unique functions), checked each
           prologue for the same `mr r31,r3/r4` pattern the reader uses -
           none matched, all touch unrelated engine objects. (3) one real
           near-miss (`FUN_00ad33d8`, a 12-slot/384-byte pool constructor
           that DOES write `+0xc` and also inits `+0xe8`, the room's other
           documented field) was traced to its 4 call sites; none resolve
           to this singleton's fixed address - it builds unrelated per-
           member/candidate-room objects, not this one. CAVEAT, stated
           plainly by the same investigation: since the value provably
           changes within one live session on a fixed BSS address, SOME
           writer must exist during normal operation - a field nothing
           ever writes cannot change. So this is a "not found by these
           addressing idioms" result, not proof no writer exists anywhere.
           Flagged blind spots: indexed stores (`stwx`/`stwux`) this
           project's tools don't model, or a literal pool reached through a
           secondary anchor register. NOT SUPERSEDED by a live write-
           watchpoint yet - RPCS3 does support one (merged March 2025,
           store-instruction fix April 2025) but only in a self-compiled
           build with `-DHAS_MEMORY_BREAKPOINTS=ON` (not present in
           standard downloads, and reportedly 2-3x slower in PPU
           interpreter mode while enabled) - a custom build was in progress
           as of this pass. Until/unless that lands, the fallback is manual
           breakpoint-and-read polling across chosen UI transitions (open
           mode-select menu, click Find Match, cancel, open private-match
           menu, hit Create), reading `room_obj+0xc` (`0x01383be4` this
           session) at each point to bisect WHEN between two known states
           the value changes, without needing to catch the write itself.
        B. CONTROLLED-CADENCE LIVE TEST. Re-create the SAME private match
           repeatedly at a fixed, precise real-world interval (e.g. exactly
           every 60s), touching nothing else (no menus, no loadout, no
           party changes) - tests the timing theory (3) directly. If it
           stays constant or flips with a clean period under this
           discipline, that is strong evidence either way.
        C. SOLO REPEAT OF TONIGHT'S SWEEP, no second player in the party -
           isolates whether mgnomad2's independent client actions (theory
           1's least-tested branch) are a factor.
        D. ONE-SCREEN-AT-A-TIME UI BISECTION. Between otherwise-identical
           re-creates, deliberately visit exactly one menu (loadout,
           stats, leaderboard, friends list, party-invite) and nothing
           else, to find which screen (if any) is a trigger - loadout
           alone is already ruled out, but this project hasn't tried the
           others in isolation.

      RULED OUT, each by live evidence:
        NOT the team - one value (0x13) occurs with team 0, 1 AND 2, the
          complete team domain.
        NOT the map - a party lobby has no map, yet carries a value; and the
          map has its own field (member_data.recent_level, where Checkpoint on
          01.11 is 0x1f).
        NOT simply "the mode" - one mode spans three ids, one per style.

      HISTORY: this field was documented as a map id, then as a map-or-team
      combined index, then as a mode, and was retracted twice on 2026-08-18
      before the 01.11 style walkthrough made the playlist structure visible.
      The earlier readings were each consistent with the data available at the
      time - 01.00 has one playlist per mode, so "mode" and "playlist" are
      indistinguishable on that build alone.
  - id: region_language
    size: 4
    doc: "Offset 16:20. Region/language, built from the sceNpManagerGetAccountRegion / GetMyLanguages pair this function calls. Live-constant `75 73 00 01` = \"us\\0\" + language 1."
  - id: room_flags_e8
    type: u4
    doc: |
      Offset 20:24. `*(u32*)(room_obj + 0xe8)`, conditionally OR'd with
      0x40000000 (`oris r0,r0,16384` @ 0x00ad5c4c, gated on
      `cmpwi cr7,r28,0; beq skip` @ 0xad5c30/0xad5c48, where `r28` is
      `FUN_00ad5b78`'s own 6th argument).

      GATE CONDITION LIVE-RESOLVED 2026-08-19 (RPCS3 debugger, breakpoint at
      the sender `0x00ad5b78`, two independent room types): creating a PARTY
      (`room_obj=0x01387f58`) showed the gate register at `0` (twice,
      including a second independent client, mgnomad2); creating a GAME ROOM
      via find-match self-host (`room_obj=0x01383bd8`, "Searching for
      players" transition) ALSO showed it at `0`. In both observed cases the
      gate is FALSE and the OR is skipped.

      READING: the top-nibble variation already observed live (`00 0c 50
      3f`, `10 2c 50 3f`, `20 0c 50 3f`) is NOT produced by this OR-gate -
      it never fired in either sample. It must come from the raw
      `*(u32*)(room_obj+0xe8)` value itself differing by context (build,
      session state, or room-object memory layout at read time), not from
      conditional logic in this sender.

      GATE SOURCE RESOLVED STATICALLY 2026-08-20 (see
      research/notes/2026-08-20-followup-open-items.md section 1). `param_6`
      is hardcoded `li r8,0` at the `"Host"` call site (@0x35d434), so the OR
      can NEVER fire on that path; at the `"GATHER"` call site it is
      `clrldi r8,r31,63` @0x3b7fa8, where `r31` is `1` iff
      `FUN_003a1f5c() != 0` AND
      `*(u32*)(0x01459260+0xC) == *(u32*)(candidate+0x8C)`
      (@0x3b7f3c-0x3b7f54). `0x01459260+0xC` is the same local
      entitlement/caps register that common/member_data.ksy names as
      `capability_flag`'s producer, so the `0x40000000` bit means "the local
      content set matches this candidate's" - it needs a specific candidate to
      compare against, which is consistent with both live samples reading
      false.

      STILL OPEN: what sets that raw
      value, and whether the OR ever fires under some untested condition
      (e.g. a private match specifically, which was attempted live but the
      breakpoint hit was inconclusive - see room_object_tail's doc in
      0x130_room_join.ksy for the unrelated finding from the same session).
      Whether `room_obj+0xe8`'s raw value or the `0x40000000` bit has any
      client-side reader was not checked this pass."
  - id: zero_18
    type: u2
    doc: "Offset 24:26. Always 0 (`sth r24,168(r1)` @ 0x00ad5c94 with r24=0)."
  - id: zero_1a
    type: u2
    doc: "Offset 26:28. Always 0 (`sth r24,170(r1)`)."
  - id: caller_arg_1c
    type: u2
    doc: |
      Offset 28:30. A caller-supplied argument (`sth r27,172(r1)` @ 0x00ad5c60,
      before r27 is reset to 0) - the sender's `param_5` (`r7`) verbatim.

      SOURCE RESOLVED 2026-08-20 from the three now-known call sites (see
      the doc-level caller note): the `"Host"` site hardcodes `li r7,-1`
      @0x35d430, which is the live `ff ff`; the `"GATHER"` site passes
      `extsw r7,r26` @0x3b7fa4, which is the live `00 00`; the PARTY site
      was caught live with `r7 = 0xFFFFFFFF`, matching the `"Host"` site. So this is a
      per-call-path constant token, not a runtime quantity - which is exactly
      why only two distinct values have ever been observed. A server can
      ignore it.
  - id: pad_1e
    size: 2
    doc: "Offset 30:32. NEVER WRITTEN - uninitialised stack. Live values `00 0a` and `00 00`. server/session_manager.py USED to read max_players from here, which was a bug (see doc, correction 3); since 2026-08-16 it reads offset 0x24, and since 2026-08-20 it clamps that value to 1..8 on ingestion."
  - id: value_20
    type: u2
    doc: |
      Offset 32:34. A float converted to int via fctiwz. Live-constant 1000
      (0x03e8).

      SOURCE STRUCTURALLY RESOLVED 2026-08-21 (static). Both this field and
      `value_22` come from the same tiny getter, `0x00acb6bc` (`lfs
      f0,72(r3)`/`stfs f0,0(r4)`, `lfs f0,76(r3)`/`stfs f0,0(r5)`, `blr` -
      it just copies two floats verbatim out of some object's `+0x48`/
      `+0x4c`). `scan_bl.py acb6bc` finds every call site; the RoomCreate
      sender's own call (`0x00ad5c68`-`0x00ad5c70`) resolves `r3` through
      `*(anchor-32748)` -> global `0x01441194` -> `*(0x01441194+4)` ->
      **`0x013835c0` = `g_70`/NetInfo**, the same per-client
      matchmaking-singleton object this project has mapped extensively
      elsewhere (`+0x6c` counted-match latch, `+0x80` userdata,
      `+0xb0:0xc4` attr_tail target - see `protos/0x136_room_search.ksy`).
      So `value_20`/`value_22` are `g_70+0x48`/`g_70+0x4c` - a per-CLIENT
      persistent pair, not anything room- or search-derived. Independently
      corroborated live, not just statically: a memory write-breakpoint hit
      caught the same night for an unrelated field (`room_field_0c`)
      incidentally dumped register `r24 = 0x1441194` with its own memory
      preview showing `*(0x1441194+4) = 0x013835c0` - the exact same
      pointer chain, confirmed from a real running process.

      `protos/0x135_find_match.ksy`'s `value_pair_14` uses the IDENTICAL
      chain at its own sender (`0x00ad6cf4`-`0x00ad6d00`, same anchor slot,
      same `0x01441194`/`g_70` resolution) - so all three wire fields are
      one and the same per-client value, echoed onto both message types.
      This is why it reads live-constant across every capture: it's not
      "coincidentally always 1000 on both messages", it's structurally the
      SAME read of the SAME object both times.

      SEMANTIC CONTENT NOT CONFIRMED - stopped here deliberately rather
      than guess. A different, unrelated function (`FUN_00352de8`, the
      presence/status telemetry line builder documented in
      `protos/0x11_heartbeat_line.ksy` as "NOT the heartbeat line") reads
      this SAME `g_70+0x48`/`+0x4c` pair via the same getter
      (`0x003531d4`) immediately after computing a fresh float from an
      integer input via a scale-then-offset formula (`fcfid`->`fmul`-
      >`fadds`, i.e. `raw*scale+offset`, the shape of a fixed-point ->
      real-unit conversion) and gates a branch on whether the pair still
      equals a threshold constant - suggestive of "has this drifted from a
      default/unset sentinel yet", consistent with either a matchmaking
      skill/rating pair sitting at an unused default, or a location/
      coordinate pair (the same function also references the `"GetLocation"`
      string and this project's `location_server.py` stub, which always
      replies `0.000000 0.000000`). The two candidates were NOT
      distinguished - the format string this function builds has no
      float specifier that would settle it either way, and the threshold
      constant's own value wasn't read. Left unrenamed on purpose: this is
      a real, confirmed structural finding (identity of the source) without
      a confirmed semantic one, and this project's standard is not to
      rename past what's actually settled. A live write-breakpoint on
      `g_70+0x48` (address varies by session - resolve via the same
      `*(0x1441194+4)` chain live) during a deliberate action expected to
      move a rating OR a location would settle it in one hit; not attempted
      this pass (static-only).
  - id: value_22
    type: u2
    doc: "Offset 34:36. Second float converted to int. Live-constant 1000 (0x03e8) - see value_20's doc for the full source trace; this is g_70+0x4c, the second half of the same pair."
  - id: max_players
    type: u2
    doc: "Offset 36:38. Max players / room capacity - the sender's `param_3` (`r5`). NOT A HARDCODED CONSTANT (resolved 2026-08-20): the `\"GATHER\"` call site passes `FUN_0039f218()` (@0x3b7f6c), which is `FUN_00349360()->+0x18` - a field of the CURRENT GAME-MODE DESCRIPTOR - and the `\"Host\"` call site passes `FUN_003a3dc8()` (@0x35d40c). That is why the value is live-constant 8 without being a literal anywhere. `sth r23,180(r1)`, and the SAME r23 is written to `room_obj+0x1f8` at 0x00ad5f80 - the field `_opd_FUN_00ad33d8`'s `if (room_obj+0x1f8 == 0) trap` assert reads and the field Member's (0x131) offset 24 overwrites. Live-constant 8 across every capture. This is the field a server should echo into Member's capacity slot."
  - id: member_data_length
    type: u1
    doc: |
      Offset 38:39 (wire 0x26). CORRECTED 2026-08-17: the LENGTH of the local
      player's 32-byte member_data card carried at wire 0xa8 (see member_data
      inside room_tail_block below), sourced from `*(u8*)(room_obj + 0x19f8)`
      (`stb r11,182(r1)`). Live 0x20 (=32), the exact length the card UI getter
      (_opd_FUN_00ad2650) demands. server/session_manager.py HARVESTS the
      32 bytes at wire 0xa8 keyed by this length and replays them into its
      0x131 Member roster + 0x13b so the host's lobby shows the joiner's card -
      the matchmade lobby never sends a 0x13a request, so this (and 0x130's
      equivalent) is the ONLY card supplier on the find-match path. See
      research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md.
  - id: is_party
    type: u1
    doc: |
      Offset 39:40 (was `flag_27` - renamed 2026-08-21). 0 normally, 4 on one
      conditional branch (`stb r0,183(r1)` @ 0x00ad5cbc) - `4` iff the
      sender's `param_4` (`r6`) is nonzero. Live values 0x00 and 0x04.

      2026-08-20 (static): both then-known "Host"/"GATHER" call sites pass
      `li r6,0` (@0x35d424 and @0x3b7fac), so both produce `0x00`.

      2026-08-20 (live, later same day): the party's RoomCreate call site
      (see the doc-level caller note) passes `r6=1`, which produces the live
      `0x04` - this is the source of every `0x04` frame. All three known call
      sites are now accounted for.

      RENAMED 2026-08-21: this crosses the project's usual "don't rename on
      an inferred semantic" bar because the caller set isn't a sample - the
      doc-level caller note above states plainly that THREE call sites is
      the EXHAUSTIVE set reaching this sender (found via a `bctrl`-pattern
      scan of the whole binary plus one live-caught third site), not an
      open-ended "observed so far". Against that closed set the split is
      clean: the one PARTY call site passes nonzero, both non-party call
      sites ("Host", "GATHER") pass zero - 3-for-3 of every known caller,
      not 1-for-1. That's different in kind from `value_20`/`value_22`/
      `flag_27`-neighbors left alone the same night, where the caller set
      itself isn't exhaustively known or the value's own producer is
      unresolved. Still genuinely a correlation, not a confirmed source
      read (nobody traced WHERE param_4's value is decided upstream of
      these three call sites, only that it's a compile-time constant at
      each) - if a fourth call site is ever found reaching this sender, the
      name may need revisiting.
  - id: room_name
    size: 128
    doc: "Offset 40:168. NUL-terminated room name, produced by `_opd_FUN_00e45b10(r1+184, room_obj+0x18)` @ 0x00ad5f74 - i.e. a plain strcpy of `room_obj+0x18`. Format is `<npid>.<unix-timestamp>` (e.g. `comradesean.1786863559`), built by the 0x143 sender's own sprintf-like call. room_obj+0x18 is the SAME 128-byte region 0x143 sends and 0x144 strcpy's into on receipt - see protos/0x143_set_room_data_block.ksy."
  - id: member_data
    type: member_data
    doc: |
      Offset 168:200 (wire 0xa8:0xc8). The local player's lobby card - the
      FIRST 32 bytes of the `room_obj+0x19fc..` copy loop (0x00ad5d30-
      0x00ad5f2c into r1+312). Each field is decoded in
      common/member_data.ksy. Its length is member_data_length above (0x20).
      The stub harvests chunk[0xa8:0xc8] on every RoomCreate and reuses it as
      this member's card. (The old "team-selection u16 at wire 0xb0" finding
      is now member_data.team at offset 9 of this record - the u16 read cleanly
      as 0/1/2 because offset 8, member_data.capability_flag, was 0 in every
      capture; see the member_data.ksy 2026-08-18 boundary revision.)
  - id: room_settings_tail
    size: 32
    doc: |
      Offset 200:232 (wire 0xc8:0xe8). RESOLVED 2026-08-19: this is NOT a
      room-object field copy at all - it is uninitialised sender-side stack,
      the same class of residue as this project's many `pad_N` fields
      elsewhere. Confirmed by exhaustively disassembling the sender
      (`FUN_00ad5b78`, opcode literal `li r0,303` @0xad5c38, send call
      `_opd_FUN_00acb93c(this+0x25060, buf, 0xe8, 1)` @0xad5fac, buffer base
      r1+144): the stack range corresponding to wire 0xc8:0xe8 (r1+344
      through r1+376) has ZERO stores anywhere in the function - no `stb`/
      `stw`/`std` targets that range, and no `bl` to a copy/memset helper
      touches it either. The function's own frame (`stdu r1,-480(r1)`) is
      never zero-filled. So the "mostly zero with occasional stale-stack
      values" behaviour already observed live is exactly what leaked,
      never-written stack looks like - not a room field that happens to be
      usually zero. The earlier "room_obj+0x19fc..+0x1a3b copy" framing was
      never verified against this function's actual disassembly and is
      retracted. Send 0. (This closes the same class of question
      `room_object_tail` in 0x130_room_join.ksy has - see that file for the
      contrasting case where the copy IS real.)
