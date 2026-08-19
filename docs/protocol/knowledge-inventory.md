# Protocol knowledge inventory

What is fully understood, what is partly understood, and what is unknown, across
all 44 `.ksy` specs (262 declared fields). Current as of 2026-08-18.

The bar for **Tier 1** is the project's reserved standard applied to a whole
message or field: a NAME, a DEFINITION (what the bytes are), and a game or
administrative REASON (why the message exists / what breaks without it) - each
backed by disassembly, live capture, or both. "We can parse it" is not enough.

**Tier 2** means the mechanism is traced - producer, consumer, or both - but the
semantic is inferred, constant across every capture, or locked behind DC `.pak`
tables. **Tier 3** means no definition: unmapped spans, unobserved grammars, and
values with no known meaning.

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

**Still not live-verified:**

- `0x139` RoomClosed - zero frames in either direction, ever. Disassembly only.
  The one Tier 1 room-lifecycle message with no live backing.
- `0x132` RoomJoined - deliberately never sent; the "must not send" reason rests
  on disassembly plus an unretained 2026-08-15 regression.
- `single-player-server` hello - 0 of 452 captured sibling hellos.

**Live but unexercised** (the message is observed; the claim is not):

- `member_data.capability_flag` - `0x00` in 376/376 samples. The AND-reduce map
  filtering that IS its stated reason has never run with a nonzero input; needs
  an account owning MP DLC.
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
5. **`packet_header`** - `sequence_number` + `opcode` framing shared by the
   family.
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
12. **`0x139` RoomClosed** - room teardown notification.
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

34. **`room_field_0c` / `field_0c`** (`0x12f`, `0x135`) - `*(u32*)(obj+0x0c)`,
    map (or map-like) selection; team component now RULED OUT. Unknown: which map
    each of `0x09`/`0x12`/`0x13`/`0x5a`/`0x63` is, and whether find-match's
    invariant `0x02` is a real map id or an any/random sentinel.
35. **`room_flags_e8` / `room_flags_10`** - `*(u32*)(obj+0xE8)` conditionally
    OR'd with `0x40000000`. Low 20 bits constant across captures; the `oris` gate
    condition is outside the traced function body.
36. **`0x140` `attr_selector`** - selects *an* attribute (live 0x0000/0x0001) and
    round-trips into `room_obj+0x1f0`. Which attribute is unknown, and nothing
    client-side ever branches on it, so the retail server was its only consumer.
37. **`0x142` HostRank `entries`** - per-player values from the player object's
    `vtable[0]` getter. Live: constant `0x0002` on unranked accounts. Proven NOT
    to be `member_data.rank_value`. Encoding needs a ranked capture.
38. **`member_data.rank_tier`** - bracket-lookup mechanism verified; the
    displayed tier needs the DC threshold table (hash `0xC85E199D`).
39. **`member_data.capability_flag` bit meanings** - which bit is which DLC pack
    lives in the `.pak` descriptors, not the EBOOT.
40. **`member_data.card_stat_2` / `card_stat_3`** - bytes and source pinned
    (`P+0x654`, the character-customization word); display meaning medium.
41. **`0x13e` `flag` byte** - boolean when written, but live values 0/1/3/4 with
    the stale value often equal to the frame's own `kind`. Only 0 and 1 are
    meaningful; which UI path drives kind 3 vs 4 is untraced (vtable dispatch).
42. **`value_20` / `value_22` / `value_pair_14`** - a float-derived pair,
    live-constant 1000/1000. Reads as a default rating pair; disabled in every
    capture.
43. **`search_window_lo` / `search_window_hi`** - a clamped rating/filter window;
    0 in every live capture (window disabled while searching).
44. **`caller_arg_1c`** - caller-supplied, live `0xffff` and `0x0000`; the caller
    is not traced.
45. **`flag_27`** - 0 normally, 4 on one conditional branch; the branch condition
    is untraced.
46. **`member_slot_ec`** (`0x131` entry) - genuinely read off the wire into
    `member_slot+0xEC`; the consumer of that slot is not pinned.
47. **`0x134` `trailing`** - present because the dispatch loop consumes 24 bytes;
    not read by the traced portion.
48. **`np_id.opt` / `np_id.reserved`** - Sony's opaque SceNpId bytes, copied
    verbatim; readers past the handle untraced.
49. **`0x12f room_settings_tail` / `0x130 room_object_tail` / `0x136 attr_tail`** -
    provenance known (copies of specific room-object spans), interiors not
    field-mapped.

---

## TIER 3 - UNKNOWN

50. **`report-server` response grammar** - the request is captured, the reply is
    not. Deliberately not guessed. Also an implementation risk: our stub answers
    a ban check with a ticket blob.
51. **`single-player-server` line protocol** - a hello spec exists, but no line
    grammar at all; the service has never been observed carrying traffic.
52. **`0x136 attr_tail` contents** (20 bytes) - the map/mode attribute block
    interior.
53. **`0x12f room_settings_tail`** (32 bytes) and **`0x130 room_object_tail`**
    (32 bytes) - unmapped room-object spans.
54. **`0x140`'s attribute identity** - what lobby setting the selector actually
    names. No client branch reads it; only a retail-server capture or the
    vtable-dispatched caller would say.
55. **`profile_21.game_data` interior** - the 0x5000-byte payload; subsystem
    index ranges only partly claimed.
56. **`profile_21` zero region `P+0x1E74..0x5008`** - purpose unknown.
57. **DC-blocked set** - all net-stat slots (including the supplies gate),
    `rank_tier` thresholds, and every id→asset map (cosmetics, character/name
    pools). Blocked on extracting `net1.bin`/`net10.bin` registries; not
    reachable by decompiling the EBOOT.
58. **`0x142` numeric encoding for a ranked account** - needs a ranked capture.
59. **Which UI/game path drives `0x13e` kind 3 vs kind 4** - vtable dispatch,
    not statically resolvable.
60. **Intermittent "Host quit for cheating"** teardown - rare, unexplained, no
    packet correlated with it yet.

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
