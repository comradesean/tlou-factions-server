meta:
  id: member_data
  endian: be
  license: CC0-1.0
doc: |
  The 32-byte per-member data record that carries a player's lobby CARD
  (team/faction, host map-picker recent-level history, rank). NB: this record
  does NOT carry MP cosmetics or a gear loadout - the "loadout_slot" labels here
  were CORRECTED 2026-08-17 to recent_level_* (see that field). The same 32 bytes
  appear in four places, all cross-confirmed:

  - `0x12f` RoomCreate wire 0xa8:0xc8 (the host's own card), length at wire 0x26
  - `0x130` RoomJoin  wire 0x18:0x38 (the joiner's own card), length at wire 0x0c
  - `0x131` Member    each roster entry offset 40:72, length at entry offset 39
  - `0x13a`/`0x13b`   SetMemberData / MemberUpdatedData payload

  The rank/loadout UI getter `_opd_FUN_00ad2650` hands this record to the lobby
  card ONLY when its length is exactly 32 (`cmpwi 32; beq` @ 0x00ad2734); any
  other length renders the remote player's card as absent. See
  research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md.

  FIELD LAYOUT — originally decoded from 47 distinct live RoomCreate cards across
  both test accounts (comradesean, mgnomad2) in captures/tcp_catch.log. REVISED
  2026-08-18 against the fully-disassembled blob PRODUCER `FUN_003b15bc`
  (research/ghidra/vg_3b15bc_disasm.txt; blob base r1+0x78, every store located):
  the producer resolves nearly every field WITHOUT a ranked capture, and
  corrects four field BOUNDARIES the capture-only inference got wrong — offsets
  0:8 are one real u64 (not two reserved gaps), the old u16 `team` at 8:10 is
  actually two independent bytes, and the old `reserved_10` at 16:22 is three
  named fields. The rank/stat encodings below are now read from the producer's
  own arithmetic; a ranked-account capture is only needed to OBSERVE them render
  nonzero, not to define them. Per-field confidence is stated inline.
seq:
  - id: party_id
    type: u8
    doc: |
      Offset 0:8. The player's current party-room id. Producer: a single u64
      store `std r7,0x78(r1)` @ 0x003b17c8, where r7 = `*(u64*)(party_room+0x10)`
      (`ld r7,0x10(r29)` @ 0x003b177c) when `FUN_00ad0fd0(party_room) > 1` AND
      `*(u8*)(party_room+0xB8) != 0` (gate @ 0x003b1760-0x003b1778), else 0
      (`li r7,0` @ 0x003b1784). Consumer: `FUN_003b6dfc` reads it back as a u64
      @ 0x003b71f4 and groups the roster by party. CORRECTED 2026-08-18: this
      span was previously split into `reserved_0` (u4) + `uninit_4` (stack
      leak); the "stale room-object pointer `01 38 7f 58`" reading was the
      party-room id itself (the stub derives room ids from the RoomCreate
      pointer, so it is a live value, not stack garbage). A server that zeroes
      this degrades live party-grouping. High confidence (producer store, gate
      and consumer read all instruction-verified).
  - id: capability_flag
    type: u1
    doc: |
      Offset 8. DEFINITION: a per-player CAPABILITY BITMASK - the set of
      content/entitlement capabilities (owned DLC map packs / modes) this member
      brings to the lobby. PURPOSE: it lets the host's map/mode picker offer only
      maps every member can play, so a matched game never picks content someone
      lacks. Producer: `stb r0,0x80(r1)` @ 0x003b15e8, source = low byte of the
      caps/entitlement register `*(u32*)(0x01459260+0xC)` (`lwz r9,-0x7ff4(r30)` /
      `lwz r0,0xc(r9)` @ 0x003b15dc/0x003b15e4). Consumer (verified 2026-08-18):
      FUN_00ad2b14 folds every member's byte 8 into a lobby-common mask
      (`li r28,-1` @ 0xad2b44; `lbz r0,8(r3)` / `and r28,r28,r0` @ 0xad2b6c-70),
      then each map/mode candidate is kept only if `common_caps &
      descriptor.required_mask(+0x14) != 0` (@0x3a25b4, @0x35ad84); a candidate
      whose required mask is 0 is always eligible.

      INDIVIDUAL BIT MEANINGS - SOLVED 2026-08-20. The descriptor table the
      AND-reduce is tested against is the DC global `*net-maps*`, stride 76
      (`mulli r0,r11,76` @ 0x3a2574), and the required mask is its word at
      `+0x14` (`lwz r0,20(r29)` @ 0x3a2598, then `and r3,r3,r0` @ 0x3a25b4).
      Decoding that table from both shipped bundles:
        01.00 `dc1/net.bin`  {count 8,  array 0x14984} - mask 0 on all 8 maps.
        01.11 `net10.bin`    {count 19, array 0x23740}:
          mask 0x00  huntercity-2 lakeside-2 university-2 billschurch-2
                     highschool-2 outskirts-2 dam-2 (x2) warzone
          mask 0x01  bookstore-2 busdepot-4 hometown-1 suburbs-1
          mask 0x04  watertower-1 mine-1 capitol-4 wharf-3
          mask 0x08  plaza-3 beach-final
      So bit 0 = a four-map pack (Bookstore/Bus Depot/Hometown/Suburbs),
      bit 2 = a four-map pack (Water Tower/Coal Mine/Capitol/Wharf),
      bit 3 = a two-map pack (Plaza/Beach), and **bit 1 is required by no map
      descriptor in either bundle** - which is why the live 01.11 value is
      0x0d and not 0x0f. Retail marketing names for the three packs are NOT
      asserted; the grouping above is what the shipped data says. Confidence:
      high (byte-exact table contents plus the instruction-verified gate; the
      01.00 all-zero table independently corroborates the column's role).
      A server synthesizing a card should send 0x00 (base maps only) unless it
      intends to advertise DLC ownership. See
      research/notes/2026-08-20-tier2-followup.md section 1.

      Was 0 in all
      47 captures (both test accounts had no MP DLC), which is why the old u16
      `team` read as a clean 0/1/2. Confidence: high (mechanism); bit-level
      semantics are DC-dependent.
      NOW EXERCISED (2026-08-19): was 0x00 in 376/376 samples on 01.00, whose
      test accounts own no MP DLC. A 01.11 client with the DLC installed sends
      0x0d, so the AND-reduce above finally runs with a nonzero input.
  - id: team
    type: u1
    doc: |
      Offset 9. Team / faction selection, live values 0, 1, 2 only. This is the
      byte the controlled 24-RoomCreate sweep tracked as team in
      research/notes/2026-08-16-team-selection-field-confirmed.md (0=unset,
      1/2 = the two factions). Producer: `stb r0,0x81(r1)` @ 0x003b16f0, source
      `*(u8*)(P+0x303)` (`lbz r0,0x303(r3)` @ 0x003b16e8) unless the gate
      `FUN_0003b584` returns nonzero (then 0, branch @ 0x003b16d8). Consumers:
      the roster sort key and the faction name+colour lookup
      `FUN_0039c69c(blob[9]-1)` @ 0x003c2ad0. CORRECTED 2026-08-18: precisely
      located at offset 9 (was the low half of the u16 `team` at 8:10). High
      confidence.
  - id: recent_level_0
    type: u2
    doc: |
      Offset 10:12. CORRECTED 2026-08-18 - this is a u2, not two u1s. The ring
      was modelled as four separate bytes (recent_level_0..3); live census over
      the whole day proves it is TWO u16 entries: every value is either `ffff`
      (unset) or `00xx`, never a lone byte, and the `00` high-byte count (204)
      exactly equals the sum of all id-byte counts (204). A u8 ring would show
      id bytes in the high position too; none ever appear there.
      CORRECTED 2026-08-17 (was mislabeled "loadout_slot_0"): NOT loadout. This
      and recent_level_1 are the host map-picker's RECENT-LEVEL ring - the low
      halves of `NetGameManager+0x4982` (global 0x01382082), a ring of recently
      played level/map ids. The blob producer FUN_003b15bc copies them here; the
      host's weighted-random map picker FUN_003a2310 reads them (`lbz r0,0xa(blob+k)`)
      and applies a DC penalty when a candidate map matches - i.e. "don't replay
      a map these players just played". 0xffff = unset.
      LIVE MAP IDS - THE ID IS PER (MAP, MODE) VARIANT, NOT PER MAP.
      Established 2026-08-19 and confirmed by out-of-sample PREDICTION: the same
      map loaded under a different game mode yields a DIFFERENT id, and the mode
      blocks are spaced exactly 0x11 (17) apart:
          Survivors     = Supply Raid + 0x11
          Interrogation = Supply Raid + 0x22
      Confirmed pairs (each loaded and read off the ring head):
        Checkpoint   Supply Raid 0x0e   Survivors 0x1f
        Lakeside     Supply Raid 0x0f   Survivors 0x20   Interrogation 0x31
      The prediction test: after pinning Checkpoint=0x0e (Supply Raid) and
      Lakeside 0x0f/0x20, "Survivors Checkpoint" was predicted to be 0x1f BEFORE
      loading it; the ring then read [001f,0020]. That is why the earlier
      0x1f/0x31 records - briefly retracted as contradictory - are RIGHT: they
      were simply the Survivors and Interrogation variants, named in sessions
      whose find-match playlists were 6/7/8 and 11/12/13 respectively, while the
      2026-08-19 late session used private Supply Raid matches.

      ALL IDS OBSERVED, with the mode each was captured under:
        0x0e (14) Checkpoint       Supply Raid
        0x0f (15) Lakeside         Supply Raid
        0x10 (16) Bill's Town      Supply Raid  (private match, 2026-08-19)
        0x11 (17) University       Supply Raid  (private match, 2026-08-19)
        0x12 (18) High School      Supply Raid  (private match, 2026-08-19)
        0x13 (19) Downtown         Supply Raid  (private match, 2026-08-19)
        0x14 (20) The Dam          Supply Raid  (private match, 2026-08-19)
        0x15 (21) Bookstore        Supply Raid  (private match)
        0x16 (22) Hometown         Supply Raid  (private match, 2026-08-19)
        0x17 (23) Bus Depot        Supply Raid  (private match, 2026-08-19)
        0x18 (24) Suburbs          Supply Raid  (private match, 2026-08-19)
        0x19 (25) Wharf            Supply Raid  (private match, 2026-08-19)
        0x1a (26) Water Tower      Supply Raid  (private match, 2026-08-19)
        0x15 (21) Bookstore        Supply Raid  (private match)
        0x1d (29) Financial Plaza  Supply Raid  (playlist 3)
        0x1f (31) Checkpoint       Survivors
        0x20 (32) Lakeside         Survivors
        0x21 (33) Bill's Town      Survivors    (playlist 8)
        0x22 (34) University       Survivors    (private match)
        0x23 (35) High School      Survivors    (private match)
        0x24 (36) Downtown         Survivors    (private match)
        0x25 (37) The Dam          Survivors    (private match)
        0x26 (38) Bookstore        Survivors    (private match)
        0x27 (39) Hometown         Survivors    (private match)
        0x28 (40) Bus Depot        Survivors    (private match)
        0x29 (41) Suburbs          Survivors    (private match)
        0x2a (42) Wharf            Survivors    (private match)
        0x2b (43) Water Tower      Survivors    (private match)
        0x2c (44) Coal Mine        Survivors    (private match)
        0x2d (45) Capitol          Survivors    (private match)
        0x2e (46) Financial Plaza  Survivors    (private match)
        0x2f (47) Beach            Survivors    (private match)
        0x30 (48) Checkpoint       Interrogation (private match, 2026-08-19)
        0x31 (49) Lakeside         Interrogation (private match, 2026-08-19 -
                                   previously known only via the three-way tie,
                                   now also directly observed)
        0x32 (50) Bill's Town      Interrogation (private match, 2026-08-19)
        0x33 (51) University       Interrogation (private match, 2026-08-19)
        0x34 (52) High School      Interrogation (private match, 2026-08-19)
        0x35 (53) Downtown         Interrogation (private match, 2026-08-19)
        0x36 (54) The Dam          Interrogation (private match, 2026-08-19)
        0x37 (55) Bookstore        Interrogation (private match, 2026-08-19)
        0x38 (56) Hometown         Interrogation (private match, 2026-08-19)
        0x39 (57) Bus Depot        Interrogation (private match, 2026-08-19)
        0x3a (58) Suburbs          Interrogation (playlist 13; also directly
                                   reconfirmed in a private match, 2026-08-19)
        0x3b (59) Wharf            Interrogation (private match, 2026-08-19)
        0x3c (60) Water Tower      Interrogation (private match, 2026-08-19)
        0x3d (61) Coal Mine        Interrogation (private match, 2026-08-19)
        0x3e (62) Capitol          Interrogation (private match, 2026-08-19)
        0x3f (63) Financial Plaza  Interrogation (private match, 2026-08-19)
        0x40 (64) Beach            Interrogation (private match, 2026-08-19)
      Unnamed, seen on 01.00 (all inside the Supply Raid block):
        0x10, 0x13, 0x14, 0x17
      IMPLIED but not yet loaded, from the +0x11 rule - treat as predictions to
      be verified, not as records: Bill's Town Supply Raid 0x10 (0x10 IS in the
      01.00 observed set, which is corroboration), Suburbs Supply Raid 0x18.

      BLOCK INDEX (id - block base) IS A PLAIN ORDERED ROSTER. The Survivors
      block fills contiguously from its base: 0x1f Checkpoint (0), 0x20 Lakeside
      (1), 0x21 Bill's Town (2), 0x22 University (3), 0x23 High School (4),
      0x24 Downtown (5),
      0x25 The Dam (6),
      0x26 Bookstore (7),
      0x27 Hometown (8),
      0x28 Bus Depot (9),
      0x29 Suburbs (10),
      0x2a Wharf (11),
      0x2b Water Tower (12),
      0x2c Coal Mine (13),
      0x2d Capitol (14),
      0x2e Financial Plaza (15),
      0x2f Beach (16). Each was loaded and read
      independently; the ordering is the game's own map roster order, not
      alphabetical. An index therefore predicts the same map in every other
      mode, e.g. University -> Supply Raid 0x11, Interrogation 0x33.

      THE ROSTER ORDER IS SHARED ACROSS MODES - CONFIRMED 2026-08-19. Bookstore
      is index 7 in BOTH blocks: Supply Raid 0x15 (0x15-0x0e=7), captured hours
      earlier in a private Supply Raid match, and Survivors 0x26 (0x26-0x1f=7),
      predicted from that index and then loaded. So the whole scheme is:

          id = block_base(mode) + roster_index(map)
          block_base: Supply Raid 0x0e, Survivors 0x1f, Interrogation 0x30

      All three bases are cross-validated by a map appearing at the SAME index
      in two different blocks: Bookstore index 7 (Supply Raid 0x15 / Survivors
      0x26) and Financial Plaza index 15 (Supply Raid 0x1d / Survivors 0x2e) tie
      Supply Raid to Survivors; Suburbs index 10 (Survivors 0x29 / Interrogation
      0x3a) ties Survivors to Interrogation. Lakeside is a fourth tie, appearing
      in all three blocks (0x0f / 0x20 / 0x31).

      THE SURVIVORS BLOCK IS COMPLETE (2026-08-19): all 17 roster slots
      0x1f..0x2f were individually loaded and read off the ring - no gaps, no
      derivation. The roster is 17 maps, indices 0..16:
          0 Checkpoint    1 Lakeside      2 Bill's Town   3 University
          4 High School   5 Downtown      6 The Dam       7 Bookstore
          8 Hometown      9 Bus Depot    10 Suburbs      11 Wharf
         12 Water Tower  13 Coal Mine    14 Capitol      15 Financial Plaza
         16 Beach
      THE BLOCKS ARE EXACTLY PACKED: 17 maps against a 0x11 (17) stride leaves
      ZERO slack, and Interrogation's base 0x30 abuts Beach's Survivors id 0x2f
      directly. So the stride is not an arbitrary round number - it IS the map
      count. (An earlier note here said the roster was 16 with one spare slot
      per block; that was written before Beach was loaded and is wrong.)
      Full derived ranges: Supply Raid 0x0e..0x1e, Survivors 0x1f..0x2f,
      Interrogation 0x30..0x40.

      ROSTER INDEX -> MAP (from the Survivors block, all directly loaded):
          0 Checkpoint   1 Lakeside     2 Bill's Town  3 University
          4 High School  5 Downtown     6 The Dam      7 Bookstore
          8 Hometown     9 Bus Depot   10 Suburbs     11 Wharf
         12 Water Tower 13 Coal Mine   14 Capitol     15 Financial Plaza
      (10 from Interrogation 0x3a, 15 from Supply Raid 0x1d.)

      THE SUPPLY RAID BLOCK IS ALSO COMPLETE (2026-08-19): all 17 roster slots
      0x0e..0x1e were individually loaded and read off the ring - no gaps, no
      derivation left. Every entry below was independently confirmed by
      loading that exact map in a private Supply Raid match:
          0x0e Checkpoint*  0x0f Lakeside*  0x10 Bill's Town*  0x11 University*
          0x12 High School* 0x13 Downtown*   0x14 The Dam*      0x15 Bookstore*
          0x16 Hometown*    0x17 Bus Depot*  0x18 Suburbs*     0x19 Wharf*
          0x1a Water Tower* 0x1b Coal Mine*  0x1c Capitol*     0x1d Financial Plaza*
          0x1e Beach*
      (* = directly observed, not derived.) With this, Supply Raid and
      Survivors are both fully pinned index-by-index. THE INTERROGATION BLOCK
      IS NOW ALSO COMPLETE (2026-08-19): all 17 roster slots 0x30..0x40 were
      individually loaded and read off the ring - no gaps, no derivation left,
      not even for Lakeside/Suburbs which had previously been known only via
      cross-block tie and are now directly reconfirmed too:
          0x30 Checkpoint     0x31 Lakeside      0x32 Bill's Town
          0x33 University      0x34 High School   0x35 Downtown
          0x36 The Dam         0x37 Bookstore     0x38 Hometown
          0x39 Bus Depot       0x3a Suburbs       0x3b Wharf
          0x3c Water Tower     0x3d Coal Mine     0x3e Capitol
          0x3f Financial Plaza 0x40 Beach

      THE ENTIRE MAP-ID SPACE IS SOLVED (2026-08-19). Every one of the 51 ids
      across all three mode blocks (0x0e..0x40) has been directly loaded and
      read off the ring at least once. There are no remaining unknowns, no
      derived-only entries, and no gaps.
      ALL SEVEN 01.00 IDS ARE NOW DIRECTLY OBSERVED on 01.11 (2026-08-19), not
      merely derived - each was loaded in a private Supply Raid match and read
      off the ring head:
          0x0e Checkpoint   0x0f Lakeside   0x10 Bill's Town  0x13 Downtown
          0x14 The Dam      0x15 Bookstore  0x17 Bus Depot
      (0x17 was the last holdout; roster index 9 was pinned by loading Bus Depot
      in Survivors as 0x28.) It is
      also strong evidence that ids are STABLE ACROSS BUILDS, since those 01.00
      observations line up with the 01.11 roster - though no map has yet been
      loaded on an 01.00 client to prove it directly.

      A LIKELY BLOCK LAYOUT, consistent with every observation but NOT proven:
      Supply Raid occupies 0x0e..0x1e, Survivors 0x1f..0x2f, Interrogation
      0x30..0x40 - i.e. 17 map slots per mode starting at 0x0e, with a map's
      index inside its block stable across modes (Checkpoint 0, Lakeside 1,
      Bill's Town 2). Do not rely on the block bases until a third mode is
      pinned for a map already known in two.

      CONSEQUENCE FOR NAMING: a map name alone is not an id. Always record the
      MODE alongside it, and prefer a private match where the mode and map are
      both chosen deliberately - matchmaking votes make the loaded map
      uncertain, which is what produced the false contradiction above.

      This ring is the project's only ground-truth source of map ids: load a
      KNOWN map, then read the id at entry 0 of the next card.
      THE RING RECORDS AT MAP *LOAD*, NOT AT MATCH COMPLETION (established
      2026-08-19 from wire.jsonl). Three transitions are each far too short for
      a played match, two of them starting from a CLEARED ring: conn2
      [ffff,ffff]@01:01:27 -> [001f,ffff]@01:01:56 (29s, Checkpoint); conn1
      [ffff,ffff]@01:18:08 -> [0031,ffff]@01:18:52 (44s, Lakeside); and
      [003a,ffff] -> [0021,003a] 43s after the 0x143 match-start
      `comradesean.1787121636`@02:40:37 (Bill's Town), a match that then ran to
      completion, its 0x133 RoomLeaving landing at 02:52:26 - the id was in the
      ring ~11 minutes BEFORE the match ended. Reconfirmed the same night on a
      fourth map: 0x143 match-start @02:55:09, ring [0021,ffff] -> [001d,0021]
      @02:55:50 (Financial Plaza), 41s later - the same load-time offset. "Recently PLAYED" is therefore a
      misnomer for the write trigger - the entry lands when the level loads.
      PRACTICAL CONSEQUENCE: a map can be named by loading into it and quitting
      immediately; there is no need to play the match out.
      CAVEAT: the ring is CLEARED when a client is booted back to the menu, not
      only on a full game restart - two naming attempts were lost that way on
      2026-08-18. Do not get booted between loading the map and reading a card.
      CROSS-BUILD IDS LOOK STABLE (2026-08-19). Three maps named on 01.11 -
      0x0e Checkpoint, 0x0f Lakeside, 0x15 Bookstore - are all inside the set
      independently observed on 01.00 (0x0e, 0x0f, 0x10, 0x13, 0x14, 0x15,
      0x17). That is what id stability across builds would look like, and it
      retro-names three of the seven 01.00 observations. It is not yet proof:
      no map has been loaded on an 01.00 client and had its id read. That one
      test still settles it.

      CROSS-BUILD RANGES OVERLAP - CORRECTED 2026-08-19. The earlier reasoning
      here ("01.11's named values fall outside 01.00's observed range") was an
      artifact of the small 01.11 sample: every id then named (0x1f, 0x21, 0x31,
      0x3a) happened to sit above the 01.00 set. Later the same night, with both
      clients confirmed on net10.bin (.121 switched 00:16:47, .100 at 00:35:11),
      01.11 produced 0x0e and 0x15 - both squarely inside 01.00's observed range
      0x0e..0x17. So the two id spaces are NOT disjoint. Whether a given map
      keeps its id across builds is still unresolved and needs the same map named
      on both; 0x15 = Bookstore on 01.11 is the natural first candidate, since
      0x15 was also observed on 01.00.
      (An earlier note here wondered whether these ids overlapped
      room_field_0c's private-match values. That question is closed:
      room_field_0c is the PLAYLIST id, an unrelated quantity - see
      protos/0x12f_room_create.ksy.)
      MP cosmetics are NOT in this blob - they come from the persisted profile
      (P+0x670..). See research/notes/2026-08-17-member-blob-vanity-semantics.md.
  - id: recent_level_1
    type: u2
    doc: "Offset 12:14. Recent-level ring entry 1 (u16, 0xffff = unset). See recent_level_0. Entry 0 is the most recent; a second entry appears once two different maps have been played."
  - id: rank_value
    type: u2
    doc: |
      Offset 14:16. Packed rank / progression value read by the card UI (card
      cell index 0, `lhz r9,14(blob+r0)` @ 0x003c27a0). ENCODING RESOLVED
      2026-08-18 from the producer: `bl 0x00323818` @ 0x003b16a0 then
      `sth r3,0x86(r1)` @ 0x003b16ac. FUN_00323818 computes
      `min(a,999) + min(b,9)*1000` (`cmplwi 999` @ 0x323818, `cmplwi 9` @
      0x323820, `mulli 1000` @ 0x323838, `add` @ 0x32383c) where
      `a = (BE32(P+0x1E34) + BE32(P+0x1E38)) / 7` (matches-played counters,
      `li r0,7` / `divw` @ 0x003b1660/0x003b1664) and `b = BE32(P+0x1E44)`
      (journeys completed) - i.e. `rank_value = journeys*1000 + weeks_survived`,
      weeks = matches/7, the Factions rank display.
      LIVE-CONFIRMED NONZERO 2026-08-18: the field takes 0x0000, 0x0001 AND
      0x0002 across the day's captures (all three test accounts), superseding the
      earlier "zero for the two UNRANKED test accounts" reading - the accounts
      simply had not played enough matches yet. The observed progression 0 -> 1
      -> 2 with no jump to the 1000s is exactly what the formula predicts:
      journeys = 0, so the value IS weeks_survived = matches/7, ticking up one
      per seven matches played. That is the encoding confirmed end-to-end from
      producer arithmetic to wire. A ranked account is still wanted only to
      exercise the journeys*1000 term. High confidence.
      NOT the same quantity as 0x142 HostRank's list entries: in 115 frames where
      both are observable, the 0x142 entry is a constant 0x0002 while this field
      reads 0x0001 (x80) or 0x0002 (x35). The two must not be conflated - see
      protos/0x142_host_rank.ksy.
  - id: rank_tier
    type: u2
    doc: |
      Offset 16:18. Producer: `bl 0x003c8e30` @ 0x003b16b4 (args
      r3 = `*(anchor-0x7fec)` = 0x01387240, `li r4,1` @ 0x003b16a8), then
      `sth r3,0x88(r1)` @ 0x003b16bc. CORRECTED 2026-08-18 (was the first 2
      bytes of `reserved_10`).

      RESOLVED 2026-08-20 - the DC branch of this producer is INERT, and the
      field's only live source is an untraced override. See
      `research/notes/2026-08-20-dc-directory-and-catalogs.md` sections 1 and 3.

      `FUN_003c8e30` (01.00, VMA 0x3c8e30-0x3c8eec, verified against
      `objdump -D -b binary -m powerpc:common64 -EB --adjust-vma=0x10000`):

          r9 = *(global+0x78)
          if (r9 != 0) return r9 - 1                 ; the override
          r3 = 0xC85E199D ; bl 0x9fa9f4              ; DC hash registry lookup
          if (!r3) return 0
          count = r3[0]; array = r3[1]; result = 0
          for (i = 0; i < count; i++) {              ; 4-byte stride, overlapping
              a = array[i]; b = array[i+1]
              if (a > 0) { result = i; continue; }
              if (b > 0) return result                ; sentinel exit
              result = i;
          }
          return count - 1

      The table `0xC85E199D` resolves to is now decoded, and it decides the
      question. `crc32_mpeg2("*net-money-info*") == 0xC85E199D` and
      `crc32_mpeg2("net-money-info") == 0xced9d25f` (both reverse-matched
      2026-08-19 against the retail disc's `dc1/*.dci` compiler-symbol
      corpus, `research/tools/dc_hash_crack.py`). What was WRONG in the
      2026-08-19 write-up here was the payload, not the name: the DC00
      directory record is `{key_hash, type_hash, value_ptr}`, not
      `{value_ptr, key_hash, type_hash}`, so the "193-entry array that never
      read cleanly as thresholds" was the PRECEDING record's table
      (`*net-emblem-layers-frame*`, which is the emblem shape catalog and
      reads perfectly as one). `*net-money-info*`'s own `value_ptr` is at
      `dc1/net.bin` file offset `0xedc` -> `0x52f4` = `{count: 99,
      array -> 0x2665c}`, and that array is a clean, monotonic, cumulative
      threshold ladder:

          idx  0   1     2     3     4      5      6      7      8      9
          val  0  2000  4000  7000  12000  18750  27000  36750  48000  60750  ...

      Run the loop above on it: entry is at `i = 0` with `result = 0`, the
      first body iteration reads `a = array[0] = 0` (not > 0) and
      `b = array[1] = 2000` (> 0), so it returns immediately with 0. There is
      no input that changes this - `param_2`/`r4` (the literal `1` at the
      call site) is never read in the function body, and the table is static.

      **So the DC path returns a hard 0, and `rank_tier` is nonzero only when
      `*(global+0x78)` is nonzero.** That matches the capture exactly: the
      field is `0x0000` in 855/855 live `0x13a` frames
      (`server/logs/wire.jsonl`, re-counted 2026-08-20; was 852 on the
      previous pass) across three test accounts, and stayed 0 while those
      accounts' board-405 supplies score visibly climbed
      (`mgnomad2` 35 -> 53, `server/logs/ticket_server.log`) - which the old
      "bracket over a money ladder" reading could not have explained on its
      own but this one does.

      Status: RESOLVED for the DC branch (confidence HIGH - byte-exact table
      contents plus instruction-level disassembly, and the predicted constant
      0 matches 855/855 captured frames).

      THE OVERRIDE IS ALSO RESOLVED, 2026-08-20: **nothing writes
      `*(global+0x78)` anywhere in the 01.00 binary**, so `rank_tier` is
      structurally `0x0000` on this build for every account, ranked or not.

      The pointer chain was re-derived from the bytes rather than reused:
      `r2 = 0x01305870`; `r30 = *(0x012FDF3C) = 0x0127227C` (the CU anchor);
      `objptr_slot = 0x0127227C - 32756 = 0x0126A288`, which holds the
      literal `0x01385CDC` - the lobby-state / `g_mission` object, and a
      fixed `.bss` address (`eb.py` reports `0x01385D54` unmapped in both
      LOAD segments, i.e. zero at load). Verified against the actual
      disassembly:

          3c8e3c  lwz  r30,-31028(r2)
          3c8e44  lwz  r9,-32756(r30)     ; -> the object
          3c8e48  lwz  r9,120(r9)         ; <- the +0x78 read, and the ONLY one

      A whole-binary pointer-taint scan (all 44 TOC slots that hold
      `0x01385CDC`; propagate the loaded pointer through `mr` and `clrldi`
      aliases, function-scoped, over `.text`) finds 187 field accesses to
      this object, 12 of them stores, at displacements `0x00, 0x04, 0x08,
      0x44, 0x72, 0x7e, 0x7f, 0x88, 0xb8, 0xbc` - **`0x78` is touched exactly
      once in the whole binary and it is the read above**. No indexed
      (X-form) store lands on the object at all, and `scan_imm.py` finds no
      `lis`+`addi` construction of either `0x01385CDC` or `0x01385D54`, so
      there is no immediate-addressed writer either. An earlier, independent
      scan of the same object by a different method (resolving each candidate
      slot's content, 246 accesses / 21 stores) reached the same verdict on
      `0x78`.

      Caveats, stated plainly: a whole-struct `memset`/`memcpy` through a
      pointer the scanner loses track of would still write zero and so cannot
      change the conclusion; a write through a pointer spilled to memory and
      reloaded elsewhere would not be caught. Within 01.00 this is as close
      to exhaustive as a static scan gets. 01.11 was deliberately NOT
      substituted in - the field reads 0 in captured frames from both
      builds, so there is no 01.11-only behaviour here to explain.

      Do not rename this field - its behavioural justification (the value the
      lobby reads for a REMOTE player's rank/title, see
      `docs/protocol/0x131_member.md`) is independent of the DC table's name.

      The DC hash is resolved at runtime through an engine-wide sorted-hash
      registry (`_opd_FUN_009fa9f4` -> `_opd_FUN_009fa88c`, binary search over
      a `{key_hash:4, value:4}` array, 8-byte stride) - NOT the DC00 file
      parser; it consumes the container's contents rather than parsing its
      bytes. `research/tools/dc_dir.py` walks the same directory statically
      and reproduces every offset quoted above.
  - id: card_stat_2
    type: u2
    doc: |
      Offset 18:20. First half of BE u32 `P+0x654` copied verbatim
      (`lbz 0x654..0x655` @ 0x003b1714+, byte stores to r1+0x8a/0x8b). `P+0x654`
      is a SEPARATE, PRECEDING field, not literally "word 0 of" the
      `custom_appearance` struct - `custom_appearance` itself begins 12 bytes
      later at `P+0x0660` (`protos/profile_21.ksy`'s `member_blob_word` @
      `P+0x0654` is the correctly-named field for this source; the phrase
      "word 0 of the customization block" in that file's doc is a loose
      description, not a structural claim - fixed here for precision). The
      UI reads this as card cell index 2 (`blob+0xE+idx*2`).

      EXHAUSTIVELY RE-CHECKED 2026-08-19 against live traffic, not just the
      original 2 samples: every `0x13a` frame in `server/logs/wire.jsonl`
      (842 total) has this field at exactly zero - including AFTER the
      profile S3 PUT/GET round-trip was implemented and confirmed working
      (`server/http_gateway.py`'s `build_put_response`; real, non-empty
      `profile.21` files exist for multiple accounts with genuine non-zero
      DATA ELSEWHERE in the same file, e.g. `custom_appearance`'s
      `equipped_item_ids`). This rules out "the round-trip just needs
      fixing" as the blocker - the round-trip works, and this specific word
      is still always zero for every account observed. The real blocker is
      unidentified: either this word requires some specific client action
      never yet triggered by these accounts (distinct from whatever writes
      `custom_appearance`'s other fields, which DO show real values), or it
      is DC-asset-dependent and would need non-zero live data plus a DC
      table to interpret even if triggered. High confidence on bytes/source;
      display meaning remains unresolved, now on a much larger evidence base.
  - id: card_stat_3
    type: u2
    doc: |
      Offset 20:22. Second half of the same BE u32 `P+0x654` (byte stores to
      r1+0x8c/0x8d @ 0x003b1730+). UI card cell index 3. Same provenance,
      the same 842-frame exhaustive re-check, and the same still-zero result
      as `card_stat_2` - see that field's doc.
  - id: pad_16
    size: 10
    doc: |
      Offset 22:32. Genuinely opaque - and NEVER WRITTEN BY THE PRODUCER for
      ANY account: the disassembly of FUN_003b15bc contains no store to
      r1+0x8e..0x97, and the copy length is a fixed `li r5,0x20` (=32) @
      0x003b17a0 before both FUN_00ad1fc0 pushes. Consumers select card cells
      0..3 only (offsets 14..21). The bytes vary randomly across captures
      (stale pointers `01 45 cd 40`, `d0 03 fa b0`, timestamp-shaped values) -
      leftover stack, not a field that populates on ranked accounts.
      LIVE CENSUS 2026-08-18 (research/tools/verify_wire.py over 5880 events)
      confirms the residue reading and gives its shape: the 10 bytes decompose as
      u16 + zero u32 + a 4-byte pointer, e.g. `0001 00000000 0137d700` (x264 in
      one roster slot alone), `0002 00000000 0145cd40`, `0000 00000000 d003fab0`.
      `0x0137d700` is the NetGameManager player-array base and `0xd003fab0` is a
      main-thread stack address - two adjacent stack slots showing through, not a
      counter and a field. See research/notes/2026-08-18-wire-residue-and-field-
      corrections.md §1.
      RELAY GUIDANCE (supersedes a bare "send zero" for servers): when RELAYING a
      member's card - 0x131 rosters, 0x13b updates - replay the client's own 32
      bytes VERBATIM, residue included. Do not zero this span selectively: the
      same 32-byte struct carries party_id, team, recent_level and rank_value,
      and rebuilding it risks corrupting those. Zeroing applies only when a
      server SYNTHESIZES a card with no client blob to copy.
