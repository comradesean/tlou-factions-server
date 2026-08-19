# Protocol knowledge inventory

What is fully understood, what is partly understood, and what is unknown, across
all 50 `.ksy` specs (45 message specs + 5 shared types; 260 declared fields).
Current as of 2026-08-19, end of an extended live-debugging session covering
`0x140`/`0x141`, `0x13e`/`0x13f`, `0x136 attr_tail`, `member_slot_ec`,
`0x12f room_settings_tail`/`0x130 room_object_tail`, `room_flags_e8`,
`member_data.card_stat_2`/`card_stat_3`, and `stat_line`'s `task-%x`.

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
38. **`member_data.rank_tier`** - bracket-lookup mechanism verified; the
    displayed tier needs the DC threshold table (hash `0xC85E199D`).
39. **`member_data.capability_flag` bit meanings** - which bit is which DLC pack
    lives in the `.pak` descriptors, not the EBOOT.
40. **`member_data.card_stat_2` / `card_stat_3`** - bytes and source pinned
    (`P+0x654`, a separate word preceding `custom_appearance`, not literally
    "word 0" of it - corrected 2026-08-19). EXHAUSTIVELY RE-CHECKED
    2026-08-19 against all 842 live `0x13a` frames (not just the original 2
    samples): still exactly zero in every one, even after the profile S3
    round-trip was implemented and confirmed working with real non-zero data
    elsewhere in the same file - rules out "needs the round-trip" as the
    blocker. Display meaning remains unresolved on a much larger evidence
    base.
41. **`0x13e` `flag` byte** - boolean when written, but live values 0/1/3/4 with
    the stale value often equal to the frame's own `kind`. Only 0 and 1 are
    meaningful. `kind` itself is RESOLVED 2026-08-19 (see item 59's removal
    below): `kind=3` is a generic host-flag claim/release on either the party
    or game-room object; `kind=4` is a set-then-clear pair tied to the game
    room's active-match lifecycle. See `protos/0x13e_set_host_flag.ksy`.
42. **`value_20` / `value_22` / `value_pair_14`** - a float-derived pair,
    live-constant 1000/1000. Reads as a default rating pair; disabled in every
    capture.
43. **`search_window_lo` / `search_window_hi`** - a clamped rating/filter window;
    0 in every live capture (window disabled while searching).
44. **`caller_arg_1c`** - caller-supplied, live `0xffff` and `0x0000`; the caller
    is not traced.
45. **`flag_27`** - 0 normally, 4 on one conditional branch; the branch condition
    is untraced.
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
    a ban check with a ticket blob.
51. **`profile_21.game_data` interior** - the 0x5000-byte payload; subsystem
    index ranges only partly claimed.
52. **`profile_21` zero region `P+0x1E74..0x5008`** - purpose unknown.
53. **DC-blocked set** - all net-stat slots (including the supplies gate),
    `rank_tier` thresholds, `stat_line`'s `task-%x` (mechanism resolved
    2026-08-19 - a genuine DC task-definitions table lookup, removed from
    this list as its own item and folded in here; see the "resolved out of
    this tier" note below - only the specific task identity remains
    DC-blocked), and every id→asset map (cosmetics, character/name pools).
    Blocked on extracting `net1.bin`/`net10.bin` registries; not reachable by
    decompiling the EBOOT.
54. **`0x142` numeric encoding for a ranked account** - needs a ranked
    capture. RE-CHECKED 2026-08-19 against all 238 live captured `0x142`
    frames: every one still ends in the unranked-account constant `0x0002` -
    the test accounts have not earned a rank change. Still blocked.
55. **Intermittent "Host quit for cheating"** teardown - rare, unexplained, no
    packet correlated with it yet.
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
