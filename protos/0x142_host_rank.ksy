meta:
  id: host_rank
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingHostRank - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only), and fire-and-forget:
  no 0x142 receive case exists and the deferred marker at room+0xD0 has no
  reader, so a server MUST ignore it and MUST NOT reply (a reply wedges the
  receive cursor).

  NAME RESTORED 2026-08-18, then HAND-CONFIRMED LIVE. An earlier pass renamed
  this to the placeholder `room_u16_list_upload` out of caution; the opcode has
  since been tested and confirmed by hand as HostRank, so the restoration
  stands (not medium-confidence any more at the message level). Supporting
  decompile evidence: the shifted declared-name table matches by exact size
  across 4 messages plus 3 semantic corroborations, and the collector
  FUN_0039b720 builds the u16 list by iterating the 8 local-player slots of the
  NetGameManager player array (0x0137D700 + i*0x920 + 0x40), filtering by seven
  state bytes, sorting entries with `*(u8*)(player+0x3FF) != 0` first, then
  `out_u16[i] = (u16)player->vtable[0](player)` (`bctrl` @ 0x39b920,
  `sth r3,0(r9)` @ 0x39b934). The per-entry VALUE is the player vtable[0]
  getter's return.

  THE PER-ENTRY VALUE IS NOT A RANK - CORRECTED 2026-08-20. Earlier passes
  described the entry as "that player's rank" and the encoding as blocked on
  a ranked account, because the producing `vtable[0]` getter had never been
  located. It has now been located and read, and it returns a PACKED
  BITFIELD (a 12-bit field with a conditional marker in bit 11, plus a 4-bit
  tag in the top nibble), not a scalar. See the `entries` field doc below for
  the full derivation and research/notes/2026-08-20-followup-open-items.md
  section 3 for the trace. The MESSAGE name is untouched by this - `HostRank`
  was established by the shifted declared-name table matching by exact size
  across 4 messages plus 3 semantic corroborations, and then hand-confirmed
  live; only the reading of what the trailing u16s CONTAIN changes.

  LIVE ENTRY DATA RE-COUNTED 2026-08-20 over server/logs/wire.jsonl (187
  0x142 frames): the "always 0x0002" reading needs one refinement that turns
  out to matter. Exactly one frame carries count=2, and its two entries are
  `0x0002, 0x0003` - CONSECUTIVE (raw frame
  `0000014200020060012723d801383bd800020003`). Every single-entry frame reads
  `0x0002`, across ten distinct connections. So the value is not a global
  constant; with two qualifying players it is two adjacent small integers,
  which is the signature of a small per-member sequential quantity and is
  hard to reconcile with "rank". This is independent evidence for the
  bitfield reading below.

  LIVE ENTRY DATA (2026-08-18, 148 frames): the find-match path sends count=1
  with a single entry 0x0002 in 138/138 frames; the custom-game path sends
  count=0 (empty list) in 27/27 frames. The count difference follows the
  player-array state filter at send time rather than the room type as such.
  RETRACTED 2026-08-20: the rest of this paragraph used to read "every
  sampled account is unranked, so 0x0002 is the unranked value; a ranked
  account remains the capture needed to pin the encoding." That framing rests
  on the entry being a rank, which the getter's disassembly disproves (see
  above). A ranked account is not the blocker and never was.

  NEGATIVE RESULT worth keeping (it is a tempting coincidence): the entry value
  is NOT common/member_data's rank_value. Both read 0x0002 in some frames, but
  across 115 frames where the sender's own card is observable, this entry is a
  CONSTANT 0x0002 while member_data.rank_value reads 0x0001 (x80) or 0x0002
  (x35). Different quantities from different producers - the entry comes from the
  player object's vtable[0] getter, member_data.rank_value from
  FUN_00323818(journeys, matches/7). The 6:8 gap is sender-side
  residue like the rest of this family (live: d740, fe30, 00e0) - see
  research/notes/2026-08-18-wire-residue-and-field-corrections.md §1, §5.

  STATUS: variable-length message, a 16-byte header plus a `count * 2`-byte
  trailing payload copied verbatim from a caller-supplied buffer
  (`_opd_FUN_00e3e064`, a plain memcpy-shaped helper, not decompiled
  further). Builder confirmed at 0x00ad60c4 / FUN_00ad5ffc. Every header
  field's exact store instruction was located.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x142 (322 decimal), stored as a raw big-endian compile-time constant (no runtime byteswap call needed for this one - the literal is already emitted in wire order)."
  - id: count
    type: u2
    doc: "Offset 4:6. The sender's entry count (`sth r6,4(r29)` @ 0xad60dc), truncated to 16 bits and stored raw. Number of u16 entries in the trailing list (one per qualifying local player)."
  - id: pad_6
    size: 2
    doc: "Offset 6:8. NEVER WRITTEN by the sender - uninitialised stack. RESOLVED 2026-08-18: FUN_00ad5ffc stores opcode @ 0xad60d4, count @ 0xad60dc, room id @ 0xad60d8, and the memcpy to +16 @ 0xad60e0 - nothing at offset 6:7. Explains the live `00 00` vs `00 60` variation. Was `unknown_2`."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field (`std r11,8(r29)` @ 0xad60d8) - matches the room_id-echo pattern used throughout this opcode family."
  - id: entries
    type: u2
    repeat: expr
    repeat-expr: count
    doc: |
      Offset 16 onward, count*2 bytes. One u16 per qualifying player,
      collected by FUN_0039b720 from the player array and sorted by the
      +0x3FF flag. Server ignores this message and need not interpret the
      values; everything below is documentation, not a requirement.

      STRUCTURE RESOLVED 2026-08-20 (static). The producing getter is now
      identified. The 8 player sub-objects
      (`0x0137D700 + i*0x920 + 0x40`) are given vtable **`0x01224438`** by
      `FUN_0039C464`: it walks `r31` from `0x01381720` down by `0x920` to the
      sentinel `0x0137CE20` (and `0x0137CE20 + 0x920 = 0x0137D740` is exactly
      player slot 0), storing `*(pool-32576) = 0x01224438` at each `+0`
      (`stw r0,0(r9)` @`0x39c4ac`). Their base constructor `FUN_003d5518`,
      run from `FUN_0039BF10` @`0x39bf5c`, only installs the ALL-PURE-VIRTUAL
      base vtable `0x01224468`, which is why the concrete slot 0 is not
      findable from the constructor alone.

      `0x01224438 + 0x00` is `FUN_003CD6C8`:

          3cd6c8  lbz    r0,432(r3)   ; a = *(u8*) (player + 0x1B0)
          3cd6cc  lwz    r9,424(r3)   ; b = *(u32*)(player + 0x1A8)
          3cd6d4  clrlwi r9,r9,20     ; b &= 0x0FFF
          3cd6dc  beq    cr7,skip     ; a == 0 -> no marker
          3cd6e0  beq    cr6,skip     ; b == 0 -> no marker
          3cd6e4  addi   r9,r9,2048   ; b += 0x800
          3cd6e8  lwz    r3,428(r3)   ; c = *(u32*)(player + 0x1AC)
          3cd6ec  slwi   r3,r3,12     ; c <<= 12
          3cd6f0  add    r3,r9,r3
          3cd6f8  blr

      i.e. the wire u16 is

          entry = (b & 0x0FFF)
                + (0x800 if a != 0 and (b & 0x0FFF) != 0 else 0)
                + (c << 12)

      LOW 12 BITS = a small per-player quantity, BIT 11 = a conditional
      marker, TOP 4 BITS = a second small tag. Note the marker is ADDED, not
      OR'd, so a low field that already has bit 11 set would carry into the
      tag - an edge case the game presumably never reaches.

      WHERE THE THREE INPUTS COME FROM. All three are written by
      `FUN_0039F75C(r3=manager, r4=room, r5=member-slot ptr, r6, r7)`
      (prologue `0x39f794`-`0x39f7a8`), which the callers run once per room
      member after enumerating them with `FUN_00ad2768` (`0x003596F0`,
      `0x003B29E4`, `0x003B79A8`, all with `r4 = 0x01383BD8`, the game room):

        player+0x1AC (`c`) = `param_4` verbatim          (`stw r21,428(r31)` @0x39fa64)
        player+0x1B0 (`a`) = `param_5` verbatim, a byte  (`stb r22,432(r31)` @0x39fa6c)
        player+0x1A8 (`b`) = `*(u32*)(member_slot+0xE8)` when `param_5 == 0`
                                                        (`stw r0,424(r31)`  @0x39fa34)
        player+0x1A8 (`b`) = a global u8 counter that post-increments by 2,
                             when `param_5 != 0`         (`stw r9,424(r31)`  @0x39fa90)

      and `member_slot+0xE8` is itself WIRE-SOURCED, from this protocol's own
      `0x131 Member`: `lhz r0,0(r7)` @`0xad7854` (with `r7 = entry+36`, the
      same register the already-documented `lbz r0,2(r7)` @`0xad7858` and
      `lbz r9,3(r7)` @`0xad79b0` use for entry offsets 38 and 39) stores the
      entry's `member_id` into the 80-byte local struct at `+0x38`
      (`sth r0,208(r1)`, local base `addi r29,r1,152` @`0xad7814`), and
      `FUN_00ad33d8` copies it on to the member slot with
      `lhz r9,56(r29)` / `stw r9,232(r31)` @`0xad34e8`-`0xad34f0`. Full chain:

          0x131 entry.member_id -> local+0x38 -> slot+0xE8
                                -> player+0x1A8 -> low 12 bits of this u16

      STILL OPEN, stated plainly: which input produces the live `0x0002`.
      This server assigns `MEMBER_ID = 1` to the host and every captured
      `0x131` contains an entry with `member_id == 1`, yet no `0x142` frame
      ever reports `1`. Candidates not distinguished here: one of
      `FUN_0039b720`'s seven filters (notably
      `*(u32*)(player+0x1AC) != 1` @`0x39b818`) systematically excludes that
      member; or the `param_5 != 0` counter branch is the live one; or `b`
      picks up a write this pass did not find. The arithmetic and the writers
      are proven; the mapping onto the observed constant is not.

      ONE HARD CONSTRAINT THAT IS PROVEN, and useful if a server ever parses
      this: the SAME `vtable[0]` getter is invoked earlier in the same loop as
      a boolean filter (`bctrl` @`0x39b7fc`, `cmpwi r3,0; beq skip`
      @`0x39b804`-`0x39b808`), so a player whose getter returns 0 is never
      emitted. A legitimate entry can never be zero.
