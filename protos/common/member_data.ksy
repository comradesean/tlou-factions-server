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
      whose required mask is 0 is always eligible. INDIVIDUAL BIT MEANINGS are
      DC/entitlement-defined (which bit = which DLC pack lives in the .pak
      descriptor tables + the owned-content register, not the EBOOT). Was 0 in all
      47 captures (both test accounts had no MP DLC), which is why the old u16
      `team` read as a clean 0/1/2. Confidence: high (mechanism); bit-level
      semantics are DC-dependent.
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
    type: u1
    doc: |
      Offset 10. CORRECTED 2026-08-17 (was mislabeled "loadout_slot_0"): NOT
      loadout. This byte and recent_level_1..3 are the host map-picker's
      RECENT-LEVEL ring - the low bytes of `NetGameManager+0x4982` (global
      0x01382082), a ring of recently-played level/map indices. The blob
      producer FUN_003b15bc copies them here; the host's weighted-random map
      picker FUN_003a2310 reads them byte-wise (`lbz r0, 0xa(blob+k)`, k=0..3)
      and applies a DC penalty when a candidate map matches - i.e. "don't
      replay a map these players just played." 0xff = unset. They churn every
      match, and reset to 0xff on a fresh boot, because they are map history,
      not equipped gear. NB: MP cosmetics are NOT in this blob - they are built
      from the persisted profile (P+0x670..). See research/notes/
      2026-08-17-member-blob-vanity-semantics.md.
  - id: recent_level_1
    type: u1
    doc: "Offset 11. Recent-level ring entry 1. See recent_level_0."
  - id: recent_level_2
    type: u1
    doc: "Offset 12. Recent-level ring entry 2. See recent_level_0."
  - id: recent_level_3
    type: u1
    doc: "Offset 13. Recent-level ring entry 3. See recent_level_0."
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
      `sth r3,0x88(r1)` @ 0x003b16bc. FUN_003c8e30 returns the override at
      `global+0x78`-1, else the first satisfied bracket in a DC threshold table
      (hash 0xC85E199D) - rank/tier-bracket shaped. CORRECTED 2026-08-18 (was
      the first 2 bytes of `reserved_10`). Medium confidence: bracket-lookup
      mechanism verified; the displayed meaning needs the DC table contents.
  - id: card_stat_2
    type: u2
    doc: |
      Offset 18:20. First half of BE u32 `P+0x654` copied verbatim
      (`lbz 0x654..0x655` @ 0x003b1714+, byte stores to r1+0x8a/0x8b). `P+0x654`
      is the first word of the character-customization block; the UI reads this
      as card cell index 2 (`blob+0xE+idx*2`). CORRECTED 2026-08-18 (was inside
      `reserved_10`). High confidence on bytes/source, medium on display meaning.
  - id: card_stat_3
    type: u2
    doc: |
      Offset 20:22. Second half of the same BE u32 `P+0x654` (byte stores to
      r1+0x8c/0x8d @ 0x003b1730+). UI card cell index 3. Same provenance and
      confidence as card_stat_2.
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
