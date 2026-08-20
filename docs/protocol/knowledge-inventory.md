# Protocol knowledge inventory

What is fully understood, what is partly understood, and what is unknown, across
all 53 real `.ksy` specs (46 message specs + 7 shared types, plus one unused
template stub; 325 declared fields - COUNTS CORRECTED 2026-08-20, an audit
found the previous "50 specs / 260 fields" figures undercounted both;
`0x11_stat_line.ksy`, `common/dc_table.ksy` and `common/text_table.ksy`, all
added 2026-08-19, were missing from this count and from `proto-map.md`'s
tables entirely).
Current as of 2026-08-20. The 2026-08-19 pass covered `0x140`/`0x141`,
`0x13e`/`0x13f`, `0x136 attr_tail`, `member_slot_ec`,
`0x12f room_settings_tail`/`0x130 room_object_tail`, `room_flags_e8`,
`member_data.card_stat_2`/`card_stat_3`, and `stat_line`'s `task-%x`. The
2026-08-20 pass opened the DC00 payload's directory - all 392 of `net.bin`'s
globals are now named and their tables dumpable (`research/tools/dc_dir.py`,
`research/notes/2026-08-20-dc-directory-and-catalogs.md`), which moved
`rank_tier`, `equipped_gesture_id`, the emblem colour catalog and
`search_window_lo`/`search_window_hi`, and shrank the DC-blocked set. A
SECOND 2026-08-20 pass (`research/notes/2026-08-20-tier2-followup.md`)
fully solved `search_window_lo`/`_hi` (a career K/D ratio, not "0 in every
capture"), `member_data.capability_flag` bit-by-bit, closed `rank_tier`'s
last open question (no override writer exists anywhere in the binary),
resolved `caller_arg_1c`/`value_20`/`value_22`'s producers, and reframed
`card_stat_2`/`card_stat_3` as an ASCII string field rather than numeric.
A THIRD 2026-08-20 pass (`research/notes/2026-08-20-rejoin-party-bug.md`)
found that `0x13f HostFlagUpdated`'s flag byte is published into NP
presence for party rooms and gates the friends-list "Join Party" row - a
side effect neither this file nor `proto-map.md` previously documented. An
AUDIT the same day found one of the second pass's own claims wrong: see
`0x13e`'s `flag` field entry below and `protos/0x13e_set_host_flag.ksy`.

The bar for **Tier 1** is the project's reserved standard applied to a whole
message or field: a NAME, a DEFINITION (what the bytes are), and a game or
administrative REASON (why the message exists / what breaks without it) - each
backed by disassembly, live capture, or both. "We can parse it" is not enough.

**Tier 2** means the mechanism is traced - producer, consumer, or both - but the
semantic is inferred, constant across every capture, or locked behind DC `.pak`
tables. **Tier 3** means no definition: unmapped spans, unobserved grammars, and
values with no known meaning.

Per-message **who / why / where** - direction, game reason, and the specific
disassembly address or capture behind each - is the companion document
[proto-map.md](proto-map.md), which also states the P2P-gameplay scope boundary
and the orphaned shared types. This file stays field-level.

Separately, **not-a-field** entries (send-buffer residue) are listed at the end:
they are *solved* in that we know exactly what they are and why they exist, but
they carry no protocol meaning. See
`research/notes/2026-08-18-wire-residue-and-field-corrections.md`.

---

## Verification status of Tier 1 (live capture vs disassembly)

Tier 1 requires evidence, and disassembly alone is weaker evidence than a live
exchange the client visibly acted on. Status as of 2026-08-18 late:

**Live-verified, message and behaviour:** `0x12d`/`0x12e`/`0x145`/`0x146`,
`0x12f`, `0x130`, `0x131`, `0x133`/`0x134`, `0x135`/`0x136`, `0x137` (BOTH
shapes), `0x138`, `0x13a`/`0x13b`, `0x13c`, `0x13d`, `0x13e`/`0x13f`,
`0x140`/`0x141`, `0x142`, `0x143`/`0x144`; sibling ticket / heartbeat /
leaderboard / facebook / report hellos and lines; profile_21 round-trip.

**Closed 2026-08-18 by a deliberate party session** (previously
disassembly-only): `0x13c` Promote captured twice in both directions with its
full `0x13d`+`0x13f` round trip; `0x138` Kickedout captured being sent correctly
for a genuine kick; and `0x137`'s two roles separated by live evidence
(4x requester=0 join-flow status, 1x requester=1 real kick).

**Closed 2026-08-18 by the host-departure fix:** `0x139` RoomClosed, first send
in the project's history - an owner leaving a room with a survivor in it now
produces `0x134 RoomLeave(owner)` + `0x139`, and the survivor accepted it
cleanly while keeping its separate party room. Every Tier 1 room-lifecycle
message is now live-verified.

**Still not live-verified:**

- `0x132` RoomJoined - deliberately never sent; the "must not send" reason rests
  on disassembly plus an unretained 2026-08-15 regression.
- `single-player-server` hello - 0 of 452 captured sibling hellos.

**Live but unexercised** (the message is observed; the claim is not):

- `member_data.capability_flag` - was `0x00` in 376/376 samples on 01.00 (no MP
  DLC on those accounts). NOW EXERCISED: 01.11 clients with DLC installed send
  `0x0d` (2026-08-19), so the AND-reduce that gates map/mode availability finally
  has a nonzero input. Individual bit meanings remain DC-defined.
- `region_language` - observed, but constant `"us\0"`+1 in every frame.
- `party_id` - nonzero in only 21/376 samples.

Well-exercised: `team` (0/1/2), `rank_value` (0/1/2), `recent_level_*`,
`roster_count` (1/2/3, the 3 from join-in-progress).

---

## TIER 1 - SOLVED (schema + definition + game reason)

### Session transport

1. **`0x12d` NetMatchmakingClientHello** - client opens the session-manager
   connection and announces its PSN identity (`np_id`). Without it there is no
   session. Live-confirmed on every connect.
2. **`0x12e` NetMatchmakingServerHello / `session_seed`** - server's reply seeds
   the client's session key schedule (`FUN_00db7f88`). Everything downstream
   depends on it.
3. **`0x146` ClientHello2 `payload`** - session-derived checksum, not a nonce:
   the client sums the four key-schedule output words. Live-confirmed - 53
   frames, exactly 3 distinct values across 3 machines, stable per machine.
4. **`0x145` Ping** - 4-byte opcode-only keepalive; the client's liveness tick on
   the session connection.
5. ~~**`packet_header`**~~ - **DEMOTED 2026-08-19, see
   [proto-map.md](proto-map.md).** It is not the family's framing and is not
   shared: nothing imports it, its `opcode` field is typed to `net_event_type`
   (the P2P layer removed in `c45c8af`), and its own doc calls it an
   "unconfirmed skeleton". Session-manager messages open with a bare `u4`
   opcode at offset 0 - `0x145 Ping` is a complete 4-byte packet. Now tier 3.
6. **`np_id`** - the 36-byte SceNpId: `online_id` handle plus terminator and
   dummy. The identity key every roster and service line is keyed on.

### Room lifecycle

7. **`0x12f` RoomCreate** - a host opens a room. Solved fields: `opcode`,
   `room_ptr` (the client's own room-object pointer, which the server MUST echo
   into Member), `max_players`, `member_data_length`, `room_name` (the
   `<npid>.<unix-ts>` session id), `member_data` (the host's 32-byte card),
   `region_language` (`"us\0"` + language 1).
8. **`0x130` RoomJoin** - a client asks to enter a room. Solved: `local_room_ptr`
   (per-client, must be echoed back to *that* client), `room_id`,
   `member_data_length`, `member_data` (the joiner's card - the only place the
   joiner supplies its rank/faction on the find-match path).
9. **`0x131` Member** - the roster push, and the load-bearing message of the
   whole protocol. Solved: `room_ptr`, `owner_ref_id`, `local_ref_id`,
   `room_id_overwrite` (writes `room_obj+0x10`; must be nonzero or the
   completion latch never arms), `room_capacity_field` (writes `room_obj+0x1f8`;
   zero trips a compiled-in assert - live-crash-confirmed), `roster_count`, and
   per-entry `attributes` (SceNpId), `member_id`, `member_data`.
10. **`0x132` RoomJoined** - understood well enough to know it must NOT be sent:
    its handler registers a member with `is_local`/`is_owner` hardcoded 0,
    creating a phantom slot and self-signaling. Deliberately unused.
11. **`0x133` RoomLeaving / `0x134` RoomLeave** - member departure and the
    server's relay of it to the remaining members, keyed by `member_id`.
12. **`0x139` RoomClosed** - server-initiated teardown of a whole room. Its
    handler runs the same full teardown routine `0x133` uses AND zeroes the
    room's own id fields, so it means "the room is gone", distinct from `0x138`
    ("you personally were kicked"). Sent to every survivor when a room's owner
    departs, and on the server's graceful shutdown.
13. **`0x137` Kickout / `0x138` Kickedout** - `target_member_id` +
    `requester_member_id`. Reason fully established the hard way: `0x138` means
    "you are kicked", so it must never be sent as an acknowledgement - doing so
    self-kicked the host and broke Join Party.
14. **`0x13c` Promote / `0x13d` OwnerMemberChanged** - ownership transfer;
    `0x13d` writes `room_obj+0x19f0` and fires the ownership callback
    (`vtable[0x34]`, the "New host : X" print). Reason established the hard way
    twice over: re-firing `0x13d` into an already-established room tore down
    join-in-progress until it was removed (2026-08-18).
15. **`0x13e` SetHostFlag `kind` / `0x13f` HostFlagUpdated `flag`** - host-flag
    request and confirmation; `0x13f` sets `room_obj+0x19f4`, and without it a
    solo host never becomes host. `kind` is 3 or 4 in 117/117 live frames.
    UPDATED 2026-08-20 (two findings): (a) for a PARTY room, that byte is ALSO
    published verbatim into NP presence and gates whether a friend's client
    draws "Join Party" for that host - see `research/notes/2026-08-20-rejoin-
    party-bug.md`. (b) `0x13e`'s `kind=3` flag byte is NOT unwritten residue as
    an earlier same-day pass claimed - it carries a real value (0, 1, or 3)
    from one of two write paths in the sender; see `protos/0x13e_set_host_
    flag.ksy`'s `flag` field and `research/notes/2026-08-20-tier2-followup.md`
    §5 (retraction noted inline).
16. **`0x143` SetRoomDataBlock / `0x144` `data_block`** - the match-session id
    string `<owner_npid>.<unix-timestamp>`, generated at match start. 15/15 live
    frames; owner name and send-time both verified.
17. **General rule, learned from 13/14 and the refresher:** never re-assert
    ownership or membership state into a room that is already established.

### Matchmaking

18. **`0x135` FindMatch** - a search. Solved: `search_obj_ptr` (must be echoed in
    the `0x136` reply, which the handler dereferences), `burst_marker` (criteria
    index; the stub keys host/joiner election on it), `locale`.
19. **`0x136` RoomSearch** - the reply listing live public games: `room_id`,
    `cur_players`, `max_players`, `host_npid`, `num_entries`. This is what lets a
    searcher find and join a host instead of self-hosting.

### The 32-byte member card (`common/member_data`)

20. **`party_id`** - the member's current party-room id; the client groups the
    roster by it. Zeroing it degrades live party grouping.
21. **`capability_flag`** - per-player DLC/entitlement bitmask, AND-reduced
    across the lobby so the map picker only offers content everyone owns.
    (Individual bit meanings are DC-defined - see Tier 2.)
22. **`team`** - faction selection, values 0/1/2, drives roster sort and faction
    name/colour lookup.
23. **`recent_level_0..3`** - the host map-picker's recent-level ring; the
    weighted-random picker penalises a candidate map that matches, i.e. "don't
    replay what these players just played."
24. **`rank_value`** - `journeys*1000 + matches/7`, the Factions rank display.
    Encoding confirmed producer-to-wire, and now live-nonzero (0/1/2).
25. **`0x13a` SetMemberData / `0x13b` MemberUpdatedData** - the card relay. On
    the find-match path the client never sends `0x13a`, so the server must
    harvest cards from `0x12f`/`0x130` and replay them as `0x13b`, or remote
    rank/faction cards render blank.

### Sibling services (port 7320 family)

26. **`0x11` hello / hello_response** - `opcode`, `client_nonce`,
    `service_name`, `ack_magic` (0x22), `session_token`, `server_choice_1`. One
    multiplexed transport, service selected by name.
27. **`ticket_submit` / `_response` frame** - `frame_magic` 0x33,
    `plaintext_len`, 16-byte `auth_tag`, `ciphertext`; encrypt-then-MAC keyed by
    the per-connection rolling counter. Verified by clean tag checks live.
28. **`heartbeat_line`** - `heartbeat <online_id>\n`. Presence/liveness beacon so
    the backend keeps the account in its queue tables. Live-confirmed.
29. **`leaderboard_line` / `leaderboard_request_line`** - get / range / update
    grammars, `+`-prefixed rows, NUL sentinel, and the rule that a
    server-initiated EOF is the client's error path. Blob fields `best_game`,
    `time_played_sec`, `executions`, `deaths`, `rank`.
30. **`facebook_line`** - the Graph-backed friend/name flow.
31. **`report_line` request** - `is-banned <online_id>\n`, a player-standing /
    ban check. Request live-captured 2026-08-18. (Response is Tier 3.)

### Profile

32. **`profile_21` envelope** - `version`, `enc_len`, `hmac_pad`, `hmac_sha1`,
    `slack`; the container, its crypto, and round-tripping via S3 are solved.
33. **`custom_appearance`** - chosen character ids per team, survivor variant,
    equipped item ids, palette, tint; plus the randomise latch. Enough to explain
    the "random appearance each match" behaviour end to end.

---

## TIER 2 - MECHANISM KNOWN, MEANING PARTIAL

34. **`field_0c` - RESOLVED 2026-08-19: the PLAYLIST ID.** A playlist bundles
    game MODE with PARTY RULES in one byte, indexed into a table shipped in
    netN.bin - which is why the numbering is per build. 01.11 has nine, all
    live-confirmed on both the searcher's `0x135` and the host's `0x12f` stamp:
    Supply Raid `1`/`2`/`3`, Survivors `6`/`7`/`8`, Interrogation `11`/`12`/`13`
    (Parties Allowed / No Parties / DLC), in five-slot blocks at `1`/`6`/`11`.
    01.00 had only `2` and `3`, one per mode, which is why "mode" and "playlist"
    were indistinguishable on that build and the field was misread three times.
    Id `3` is Survivors on 01.00 but Supply Raid/DLC on 01.11 - **ids are not
    comparable across builds**. Non-matchmaking lobbies use the same space:
    `0x58` party, `0x63` private (Supply Raid, Survivors), `0x5a` private
    (Interrogation). Implemented: the `0x136` list is filtered on the SEARCHER's
    playlist and the client's build, exact match, never on the host's room field.

35. **`room_flags_e8` / `room_flags_10`** - `*(u32*)(obj+0xE8)` conditionally
    OR'd with `0x40000000`. GATE RESOLVED for `room_flags_e8` 2026-08-19: live
    RPCS3 breakpoints across two independent room types (party creation,
    game-room creation via find-match) both showed the gate register at 0 -
    the OR never fires in either sample. The already-observed top-nibble
    variation must come from the raw `+0xe8` value itself, not this
    conditional. `room_flags_10` (a different function, "identical
    construction") likely follows the same pattern but wasn't independently
    live-checked.
36. **`0x140` `attr_selector`** - RESOLVED 2026-08-19 as a binary client-phase
    announcement, not an attribute selector: `1` = the client's lobby/roster
    model is being rebuilt (`FUN_0035a7dc`), `0` = `NET_SM_RESULTS`/match-end
    stat crediting (`FUN_003f208c`) - both named by pre-existing project
    research and cross-confirmed live (RPCS3 debugger, plus a log-level
    correlation showing 87% of `selector=0` events land within milliseconds of
    a real leaderboard-update). Still Tier 2: the round-trip is proven inert
    client-side, and what a real backend does with either notification remains
    permanently unrecoverable from the client alone. See
    `protos/0x140_set_room_flags.ksy`.
37. **`0x142` HostRank `entries`** - per-player values from the player object's
    `vtable[0]` getter. Live: constant `0x0002` on unranked accounts. Proven NOT
    to be `member_data.rank_value`. Encoding needs a ranked capture.
    RECONFIRMED 2026-08-20 across all 241 captured frames (3 more than the
    previous pass): every one still ends in `0x0002`. Still blocked.
38. **`member_data.rank_tier`** - **DC PATH RESOLVED 2026-08-20, and it is
    INERT.** The DC00 directory record is `{key_hash, type_hash, value_ptr}`,
    not `{value_ptr, key_hash, type_hash}`; the 2026-08-19 "193-entry array
    that never read as thresholds" belonged to the PRECEDING record
    (`*net-emblem-layers-frame*`). `*net-money-info*`'s real table is
    `{count: 99, array -> dc1/net.bin 0x2665c}`, a monotonic cumulative
    ladder `0, 2000, 4000, 7000, 12000, ...`. Running `FUN_003c8e30`'s
    instruction-verified loop on it exits on the first iteration returning 0
    (`array[0] == 0`, `array[1] > 0` trips the sentinel), so the DC branch
    can only ever produce 0 - which is exactly the capture (0x0000 in
    855/855 live `0x13a` frames). The field is nonzero ONLY via the override
    at `*(global+0x78)`. FULLY CLOSED 2026-08-20: two independent whole-binary
    pointer-taint scans (187 and 246 field accesses to the resolved object)
    agree offset `0x78` is touched exactly once in the entire 01.00 binary,
    and that touch is the READ inside `FUN_003c8e30` itself - no writer
    exists anywhere. `rank_tier` is structurally `0x0000` on 01.00 for every
    account, ranked or not. See
    `research/notes/2026-08-20-dc-directory-and-catalogs.md` sections 1/3 and
    `research/notes/2026-08-20-tier2-followup.md` §7.
39. **`member_data.capability_flag` bit meanings** - SOLVED 2026-08-20, bit by
    bit, against `*net-maps*`'s `+0x14` required-mask column (stride 76,
    instruction-verified at `0x003a2574`-`0x003a25b4`, a second identical gate
    at `0x0035ad74`-`0x0035ad8c`). Decoded from both bundles: bit 0 = a
    four-map pack (Bookstore/Bus Depot/Hometown/Suburbs), bit 2 = a four-map
    pack (Water Tower/Coal Mine/Capitol/Wharf), bit 3 = a two-map pack
    (Plaza/Beach); bit 1 is required by no map descriptor in either bundle,
    which is why the live 01.11 value is `0x0d` not `0x0f`. Retail marketing
    names for the packs are not asserted, only what the shipped table
    requires. See `research/notes/2026-08-20-tier2-followup.md` §1.
40. **`member_data.card_stat_2` / `card_stat_3`** - TYPE CORRECTED 2026-08-20:
    `P+0x654..0x65B` is not a numeric stat pair, it is an 8-byte NUL-terminated
    ASCII string (`strcmp`/`strcpy` on the same buffer, `0xe459bc`/`0xe45b10`,
    verified instruction by instruction), and `card_stat_2`/`card_stat_3` are
    its first four characters. The buffer is reachable from exactly two
    functions in the whole binary, and the only value either can write into
    it (besides reading it back from the profile) is the literal string `"*"`,
    gated on a byte nothing in the binary ever stores to - so the value space
    is closed to `""` or `"*"` on 01.00, consistent with 855/855 zero frames
    without needing "no live data ever populated it" as an unproven excuse.
    Display meaning of `"*"`, if it ever appears, is still open. See
    `research/notes/2026-08-20-tier2-followup.md` §2.
41. **`0x13e` `flag` byte** - RETRACTED-AND-CORRECTED 2026-08-20 (two rounds
    same day). NOT simple stale-byte residue: on `kind=4` the byte is real
    (4 or 0, never other values - `rlwinm` masks to a single bit worth 4).
    On `kind=3` a same-day pass first claimed the byte was "genuinely
    uninitialised stack" and should be ignored entirely - THAT WAS WRONG, an
    audit caught it: `kind=3`'s builder has TWO real stores to that byte,
    selected by a vtable+0x18 call's result - a RAW path (0 or 1, param_3
    verbatim) and an ENCODED path (3 if param_3 != 0, else 0). So on
    `kind=3`, any nonzero value (1 or 3) means "become/claim host" and 0
    means "cease" - not residue to be ignored. `kind` itself is RESOLVED
    2026-08-19: `kind=3` is a generic host-flag claim/release on either the
    party or game-room object; `kind=4` is a set-then-clear pair tied to the
    game room's active-match lifecycle. Additionally (2026-08-20): for a
    PARTY room, `0x13f`'s confirmation of this flag is published verbatim
    into NP presence and gates the friends-list "Join Party" row - see item
    15 above. See `protos/0x13e_set_host_flag.ksy`.
42. **`value_20` / `value_22` / `value_pair_14`** - PRODUCER RESOLVED
    2026-08-20: `bl 0xacb6bc` @`0xad5c70`, a three-instruction getter reading
    floats off a config object at `+0x48`/`+0x4C`. A float-derived pair,
    live-constant 1000/1000. Reads as a default rating pair; disabled in every
    capture.
43. **`search_window_lo` / `search_window_hi`** - SOLVED 2026-08-20 (not just
    corrected). The value is the game's own matchmaking "rank value" - a
    career kill/death ratio x100, summed over both game modes, from two
    20-byte per-mode career-stat records this pass also decoded in
    `profile_21.ksy` - +/- a half-width read from the
    `*net-matchmaking-criteria*` DC column (5/10/0 on 01.00, 60/0 on 01.11,
    not a code constant). "0 in every live capture" was drawn from a smaller
    sample; across all 2,188 captured `0x135` frames the pair is NONZERO in
    653, decomposing exactly against the decompiled clamp. The 01.00 producer
    is a hard-0 stub (dead on the primary build, which is why 1,535/1,535
    01.00-sender frames are `(0,0)`); the ratio is computed only in the 01.11
    EBOOT, cited for that reason only. Numerically verified against both
    stored profiles. See `research/notes/2026-08-20-tier2-followup.md` §6.
44. **`caller_arg_1c`** - PRODUCER RESOLVED 2026-08-20: the sender's own
    `param_5` (`r7`), verbatim, against `FUN_00ad5b78`'s prologue. Live
    `0xffff` and `0x0000` are the values that argument actually carried; the
    function's OWN caller (reached via `bctrl` through vtable slot `+0x10`,
    invisible to a static branch scan) is not traced.
45. **`flag_27`** - PRODUCER RESOLVED 2026-08-20: `4` iff the sender's own
    `param_4` (`r6`) `!= 0`, else `0`, against the same `FUN_00ad5b78`
    prologue. The caller (same untraced `bctrl`, see item 44) is still open.
46. **`member_slot_ec`** (`0x131`/`0x132` entry) - genuinely read off the wire
    into `member_slot+0xEC`; write-only, no consumer. STRENGTHENED 2026-08-19:
    independently re-verified across the WHOLE binary (not just the original
    instruction-address band) by searching for every other use of the
    member-slot addressing idiom - still no reader found anywhere.
47. **`0x134` `trailing`** - present because the dispatch loop consumes 24 bytes;
    not read by the traced portion.
48. **`np_id.opt` / `np_id.reserved`** - Sony's opaque SceNpId bytes, copied
    verbatim; readers past the handle untraced.
49. **`0x12f room_settings_tail`** / **`0x130 room_object_tail`** - RESOLVED
    2026-08-19, two different findings after re-verifying the earlier
    citation inconsistency properly. `room_settings_tail`'s sender
    (`FUN_00ad5b78`) was exhaustively disassembled and never writes that
    stack region at all - pure uninitialised residue, not a room-object
    field. `room_object_tail` IS a real copy (`room_obj[0x20:0x40]`, via
    sender `FUN_00ad6718`'s 64-byte copy loop), with `room_obj`
    live-confirmed as the party object (`0x01387f58`) during a real party
    join, and an exhaustive whole-binary scan of that range found no reader
    - same status as `attr_tail`/`member_slot_ec`.
49a. **`0x136 attr_tail`** - MECHANISM FULLY RESOLVED 2026-08-19, interior
    meaning still unknown. Both copy sites traced at instruction granularity
    and live-confirmed in RPCS3's debugger: lands in `g_70`/NetInfo
    (`0x013835c0` on 01.00, a well-known object this project has mapped since
    2026-08-17), offsets `0xb0:0xc4`. An exhaustive scan of the object's only
    addressing path (51 call sites, one compilation unit) found no reader
    anywhere in the retail binary, and a live canary-byte test confirmed zero
    client-visible effect. Closing the interior meaning needs a live retail
    capture (see docs/OPEN-QUESTIONS.md's PS4 capture plan) - this is now the
    strongest-evidenced item in this tier, promoted out of tier 3 below.

---

## TIER 3 - UNKNOWN

50. **`report-server` response grammar** - the request is captured, the reply is
    not. Deliberately not guessed. Also an implementation risk: our stub answers
    a ban check with a ticket blob. RECHECKED 2026-08-20: 59 `is-banned`
    requests in `server/logs/ticket_server.log`, still zero retail replies.
    Needs a capture.
51. **`profile_21.game_data` interior** - the 0x5000-byte payload; subsystem
    index ranges only partly claimed. NEW LEAD 2026-08-20: the DC stat registry
    now has a name and a dump - `*net-stats*` (`crc32_mpeg2` `0x921da350`), 40
    entries at `dc1/net.bin 0x9c18`, stride 8, `{stat_id_hash,
    text_string_id}`, 28 of the 40 resolving to display names ("Downed Enemy",
    "Revive", "Heal Ally", "Execution", "Supplies", "Parts", ...). RETRACTED
    same day: this item originally claimed entry 0's `stat_id_hash`
    `0x5c494554` was the id `protos/profile_21.ksy` cited for `match_ratio_1e3c`
    at P+0x1E3C, "explaining" why that id was never found in a text table.
    That was a misread of one instruction later in the same pass -
    `0x5c494554` is set up as the argument to the NEXT statement's stat-query
    call (`bl 0x3e7430` @`0x3f29d4`), which accumulates into a newly-decoded
    `career_stats[0].downs_dealt` field, and has nothing to do with
    `match_ratio_1e3c`. `0x5c494554` = row 0 = "Downed Enemy". See
    `protos/profile_21.ksy`'s `match_ratio_1e3c` doc (correction) and
    `career_stat_record` type (the new field), and
    `research/notes/2026-08-20-tier2-followup.md` §6. Separately, whether
    `profile.21`'s `record[8 + (statIdx+581)*4]` indexes `*net-stats*` is
    still not established.
52. **`profile_21` zero region `P+0x1E74..0x5008`** - purpose unknown.
53. **DC-blocked set** - all net-stat slots (including the supplies gate;
    `rank_tier`'s own `net-money-info` table is now fully decoded and RESOLVED
    as inert dead code - see item 38, not part of this blocked set anymore),
    `stat_line`'s `task-%x`
    (mechanism resolved 2026-08-19 - a genuine DC task-definitions table
    lookup, removed from this list as its own item and folded in here; see
    the "resolved out of this tier" note below - only the specific task
    identity remains DC-blocked), and most of the id→asset map (cosmetics,
    character/name pools) - PARTIALLY UNBLOCKED 2026-08-19: `net1.bin`/
    `net10.bin`'s container format is solved (`docs/protocol/dc_table.md`),
    and cosmetic/customization StringIds are now resolvable via
    `research/tools/text_table.py` against `text1.psarc`'s locale text
    tables (confirmed live: hat/mask/helmet, a milestone-event message) or
    via `research/tools/dc_hash_crack.py` against the retail disc's
    compiler-symbol corpus (confirmed live: character skin variant,
    `net-money-info`, `hud`). What's still genuinely blocked: DC hashes
    this project has not yet cited anywhere (no known hash to search for),
    and most of the emblem shape/colour catalog. UPDATE 2026-08-20: the
    emblem shape catalog is fully SOLVED, all four layers directly and
    independently tested (none inferred) - live edit-and-diff testing (not
    a memory read) found the off-by-one a static-analysis-only pass had
    missed; `shape_index-1` indexes directly into a 192-entry flat name
    catalog on the retail disc, proven against the entire catalog on
    layer0 (192/192, zero mismatches) and confirmed on layers 1-3 too, one
    identical formula, no per-layer offset. Rotation/scale/opacity and the
    colour picker's grid-position formula are also solved. Two more
    customization fields cracked by the same method: `equipped_gesture_id`
    (was `gated_customization_id` - location/mechanism solved via six
    live edits, but the hash behind the six confirmed values is NOT
    solved, ruled out against every hash scheme this project has) and
    `emblem_location` (was `flag_1e40`, wrongly documented as a boolean -
    it's a 4-value enum, None/Torso/Helmet/Backpack). See
    `research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md`
    §9-§11 and `research/notes/2026-08-20-emblem-shape-catalog.tsv`.
    UPDATE 2026-08-20 (a second, purely static pass): the DC00 directory
    record was being read one word off - it is `{key_hash, type_hash,
    value_ptr}`. Fixing that made the payload's tables directly dumpable,
    and ALL 392 of `net.bin`'s globals crack by name against the disc's
    `.dci` corpus (`research/tools/dc_dir.py`). Closed by that route: the
    emblem COLOUR catalog (`*net-emblem-colors*` = 64 RGBA f32 swatches, an
    8x8 hue grid - `research/notes/2026-08-20-emblem-color-catalog.tsv`);
    the GESTURE id map (`*net-taunts*`, 11 rows, all named via
    `text_table.py` - six byte-exact against the earlier live edits, and the
    other five exactly the names seen locked in-game); and the shape
    catalog's provenance (`*net-emblem-layers-{base,frame,parts}*` all
    literally share ONE array, which is why the four layers use one catalog,
    and index 0 of that array is the string `none` itself, so
    `catalog[shape_index]` is direct rather than off-by-one). Still open:
    the intra-table hash ALGORITHM - pinned to CRC-32 poly `0x04C11DB7`,
    MSB-first, forward byte order by exact single-byte-delta tests, but NOT
    globally GF(2)-affine over the name, so something outside the visible
    string enters the message. That is now a curiosity rather than a
    blocker, since every table pairs its hash with a plaintext name or a
    StringId. Also still open: a handful of unexplained bytes.
54. **`0x142` numeric encoding for a ranked account** - needs a ranked
    capture. RE-CHECKED 2026-08-20 against all 241 live captured `0x142`
    frames (238 on the previous pass): every one still ends in the
    unranked-account constant `0x0002` - the test accounts have not earned a
    rank change. Still blocked.
55. **Intermittent "Host quit for cheating"** teardown - rare, unexplained, no
    packet correlated with it yet. RECHECKED 2026-08-20: the string appears
    nowhere in `server/logs/`. Needs a live reproduction, not static analysis.
56. **`stat_line` task line's 2nd `%s`** - the accessor is pinned (`base+0x2e6c`
    string field), but `base` resolves to a runtime-allocated object with no
    file-backed content - needs a live memory read during a campaign autosave.

RESOLVED OUT OF THIS TIER since 2026-08-18 and removed from the numbered list
above (kept here so old cross-references aren't silently broken): `single-
player-server` line protocol (now `protos/0x11_stat_line.ksy`, 2026-08-19),
`0x136 attr_tail` contents' mechanism (see item 49a above; interior meaning
still open but promoted to tier 2), `0x12f room_settings_tail` /
`0x130 room_object_tail` (both resolved, see item 49 above), `0x140`'s
attribute identity (resolved,
`protos/0x140_set_room_flags.ksy`), `0x13e` kind 3 vs kind 4 (resolved,
`protos/0x13e_set_host_flag.ksy`), `gamelist_line` grammar (resolved
2026-08-19), `stat_line` task line's `%x` mechanism (resolved 2026-08-19 -
a genuine DC task-table lookup, folded into the DC-blocked set as item 53;
only the specific task identity remains unresolved).

---

## NOT A FIELD - proven send-buffer residue

These are solved, but carry no protocol meaning. 99% of sampled values are valid
PS3 addresses (70% main-thread stack `0xd0001000-0xd0040fff`). A server should
send 0; a reader must never mine them.

- `0x12f pad_4`, `pad_1e` · `0x130 pad_4`, `pad_d` · `0x131 pad_4`,
  `reserved_28`, `header_padding`, `member_data_padding` · `0x132 pad_4`,
  `trailing_tail` · `0x133 pad_4` · `0x134 pad_4` · `0x135 pad_4`, `pad_1a` ·
  `0x136 pad4`, `unused_8`, `unused_e`, `unused_12` · `0x138/0x139 pad_4` ·
  `0x13a pad_5`, `tail` · `0x13b pad_7`, `reserved_blob_tail` ·
  `0x13c/0x13d/0x13e pad_6` · `0x13f pad_5` · `0x140/0x141 pad_6` ·
  `0x142 pad_6` · `0x143/0x144 pad_4` · `netmatchmaking hello reserved_4`,
  `pad_2c`, `reserved_c` · `member_data pad_16` · `0x11 hello pad_08`.
- `0x11 hello pad_08` is the notable one: 16 bytes that in 38 of 452 captures
  leak ASCII from the client's web stack (`"outube/accounts/"`,
  `'Roberts", "id": '`) - a real privacy leak, not just an untidy gap.
- **Relay exception:** `member_data pad_16` must be replayed VERBATIM when
  forwarding another member's card - the same 32-byte struct carries
  `party_id`, `team`, `recent_level` and `rank_value`.
