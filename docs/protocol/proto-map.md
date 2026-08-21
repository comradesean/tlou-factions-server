# Proto map: who, why, where

One row per `.ksy` spec. Three columns carry the weight:

- **Who** - which side emits it, and which side acts on it. A message nobody
  consumes is not the same as a message with an unmapped payload.
- **Why** - the game or administrative reason it exists: what the client is
  trying to accomplish, and what visibly breaks without it. A schema without a
  reason is parsing, not understanding.
- **Where** - the evidence. `disasm` names a verified EBOOT address, `live` means
  observed on the wire in a capture the client visibly acted on. Both is the bar
  for tier A; neither is not a finding.

Tiers are message-level. Field-level status - which individual bytes are solved,
inferred, or unknown - is in [knowledge-inventory.md](knowledge-inventory.md);
that file is the companion to this one, not a duplicate. Where a tier-A message
contains a tier-B or tier-C field, the row says so.

Current as of 2026-08-20. Rows for `rank_tier`, `capability_flag`, `search_window_lo`/`_hi`,
`caller_arg_1c`/`flag_27`, `value_20`/`value_22`, `card_stat_2`/`card_stat_3`, and
`0x13f HostFlagUpdated` were updated 2026-08-20 to reflect that day's findings
(`research/notes/2026-08-20-tier2-followup.md`, `2026-08-20-rejoin-party-bug.md`);
see those rows for what changed. A later pass the same day
(`research/notes/2026-08-20-followup-open-items.md`) then resolved
`FUN_00ad5b78`'s caller, `0x13e` kind=3's encoding selector, and `0x142`'s
per-entry structure, and closed `capability_flag` bit 1 - the
`caller_arg_1c`/`flag_27`, `0x142 HostRank`, and `room_flags_e8` rows below
carry those updates. The `0x131 Member` row's citation was also
corrected (the addresses it previously cited did not show the write it claims).

Six of the eight sibling services are handled; `gamelist-server` joined them on
2026-08-19. The two still unhandled are `single-player-server` (never observed
carrying traffic) and the `report-server` *response* (fail-open, see tier C).

---

## Scope boundary: the P2P gameplay layer is deliberately out

`common/opcodes.ksy` holds 115 `NetEventType` ids (0-114), numerically confirmed
from the 116-slot name table at `0x012238e0` via the accessor `FUN_00388b80`.
Payload schemas for 41 of them were written and `ksc`-validated across two passes
(`research/notes/2026-08-14-gameplay-opcode-mapping.md`,
`2026-08-15-gameplay-opcode-schema-expansion.md`), then archived and deleted in
commit `c45c8af` - "no dependency, server not needed". That layer is peer-to-peer:
the server never sees those bytes, so a revival server does not need them.

This matters for reading the tier lists below: the ~74 unmapped net events are
**not** an open gap in the server protocol. They are outside it. Anyone counting
"unknown protocol surface" should not count them.

Three shared types are orphans of that removed scope and are imported by nothing
that ships:

| Spec | State |
|---|---|
| `common/opcodes.ksy` | Enum ids confirmed; the enum itself is sound. Imported only by `packet_header` and by a vestigial, unused import in `0x133_room_leaving.ksy`. |
| `common/packet_header.ksy` | Describes the P2P envelope, not session-manager framing: its `opcode` field is typed to `net_event_type`. That opcode byte is confirmed at high confidence, but the file's shape is wrong - the real envelope is a **continuation bit + 1-byte opcode + payload + optional recipient-list trailer** (`net_event_dispatch_and_simple_opcodes.md` section 2), not this file's `u4 sequence_number` + `u1 opcode`. The `sequence_number` prefix is hypothesis-only, inferred from a `net-phase-snapshot.cpp` assert string. Nothing imports it. Superseded by the dispatch doc. |
| `common/primitives.ksy` | Self-declared placeholder. Hypothesis types (`vec3` etc.), never imported. |

Session-manager messages carry no such header: they open with a bare `u4` opcode
at offset 0, and `0x145 Ping` is a complete packet at 4 bytes total. Treating
`packet_header` as the family's framing - as an earlier inventory line did - is
incorrect on both counts: it is hypothesis-only, and it is shared with nothing.

ADDED 2026-08-20 (audit found these two missing from every table on this page,
despite being added 2026-08-19 and cited extensively in prose elsewhere):

| Spec | State |
|---|---|
| `common/dc_table.ksy` | The DC00 container format - `{key_hash, type_hash, value_ptr}` directory records over `net1.bin`/`net10.bin`. SOLVED 2026-08-20 (the record-order fix that unblocked `rank_tier`, the emblem catalogs, and `capability_flag`); see `docs/protocol/dc_table.md`. Imported by nothing that ships - it's a research tool's schema for the game-data bundle, not wire traffic - but it is load-bearing for every DC-gated field elsewhere in this table. |
| `common/text_table.ksy` | `text1.psarc`'s StringId -> localized-text lookup. Confirmed live against real equipped items (`docs/protocol/text_table.md`, `research/tools/text_table.py`). Same status as `dc_table.ksy`: a research-tool schema, not wire traffic, but load-bearing for resolving any StringId this project cites. |

---

## TIER A - fully understood

Who, why, and where are all answered, each backed by disassembly, live capture,
or both.

### Session transport (port 7314)

| Spec | Who | Why | Where |
|---|---|---|---|
| `netmatchmaking_client_hello` (0x12d) | client -> server, first frame on the connection | Opens the session and announces PSN identity. No session exists without it. | disasm `FUN_00ad71a0` @ `0x00ad71a0`; live every connect |
| `netmatchmaking_server_hello` (0x12e) | server -> client | Reply carries `session_seed`, which seeds the client's ARX key schedule (`FUN_00db7f88`). Everything downstream depends on it. Opcode mismatch aborts the connection outright. | disasm: recv @ `0xad74fc`, loads @ `0xad7510`/`0xad7534`; live |
| `0x146 ClientHello2` | client -> server, fire-and-forget | Session-derived checksum, not a nonce - the client sums four key-schedule words. Proves the client derived the same session state the server did. | disasm builder `0xad7554`-`0xad7598`; live 53 frames, 3 distinct values across 3 machines |
| `0x145 Ping` | client -> server, fire-and-forget | Client-timer keepalive on the session connection. Bare 4-byte opcode, no payload, no reply expected. | live; server sends no reply and the client never stalls |
| `common/np_id` | embedded in several messages | Sony's 36-byte `SceNpId`. The first 16 bytes are the online-id handle: the confirmed dedupe and signaling key every roster and service line is keyed on. | disasm `_opd_FUN_00e459bc` NUL-scan @ `0xe459dc`-`0xe45a34`; resolve @ `0x00ad34a4` |

Carve-out: `np_id.opt` / `np_id.reserved` (the trailing 20 bytes) are structural
names from Sony's public struct, not behaviourally confirmed - tier B.

### Room lifecycle

| Spec | Who | Why | Where |
|---|---|---|---|
| `0x12f RoomCreate` | client (host) -> server | A host opens a room. Carries the host's own room-object pointer, which the server MUST echo into `0x131 Member`, plus the host's 32-byte member card and the `<npid>.<unix-ts>` session id. | disasm `0x00ad5c38`+; live |
| `0x130 RoomJoin` | client (joiner) -> server | A client asks to enter a room. `local_room_ptr` is per-client and must be echoed back to *that* client. The only place a joiner supplies its own card on the find-match path. | disasm; live |
| `0x131 Member` | server -> client | The roster push, and the load-bearing message of the protocol. `room_id_overwrite` writes `room_obj+0x10` and must be nonzero or the completion latch never arms; `room_capacity_field` writes `room_obj+0x1f8` and zero trips a compiled-in assert. | CITATION CORRECTED 2026-08-20: the claim is correct but the previously-cited addresses (`0x00ad2734`/`0x00ad3430`/`0x00ad3478`) do not show it - `ad2734` is an unrelated `member_data_length==32` check, `ad3430`/`ad3478` are a register move and a bare branch inside the slot-lookup loop. The actual writes are `ld r9,16(r28)`/`std r9,16(r29)` @`0x00ad7804`-`0x00ad7808` (`room_id_overwrite`) and `lhz r0,24(r28)`/`stw r0,504(r29)` in the same range (`room_capacity_field`), matching `protos/0x131_member.ksy`'s own citation. disasm `0x00ad7804`-`0x00ad7808`; live, including a confirmed crash on the zero case |
| `0x132 RoomJoined` | server -> client | Understood precisely well enough to know it must NOT be sent: the handler registers a member with `is_local`/`is_owner` hardcoded to 0, creating a phantom slot and self-signaling. Deliberately unused. | disasm `0x00ad79ec`/`0x00ad7b4c`; **never live-verified** - see evidence gaps |
| `0x133 RoomLeaving` | client -> server | Member announces departure, keyed on the room's own `+0x10` id, read and sent immediately before the client zeroes it. | disasm; live |
| `0x134 RoomLeave` | bidirectional - client sends it, and the client's receive-dispatch `FUN_00ad7604` has a case for it | Server relays a departure to remaining members, keyed by `member_id`. | disasm; live |
| `0x139 RoomClosed` | server -> client | "The room is gone" - distinct from `0x138` ("you personally were kicked"). Its handler runs `0x133`'s full teardown AND zeroes the room's id fields. Sent to survivors when an owner departs, and on graceful shutdown. | disasm `0x00ad7fc4`; live since the host-departure fix |
| `0x137 Kickout` | client -> server | Two distinct roles separated by live evidence: `requester=0` is join-flow status, `requester=1` is a real kick. | disasm `0x00ad6570`+; live, both shapes (4x requester=0, 1x requester=1) |
| `0x138 Kickedout` | server -> client | Means "you are kicked" - so it must never be sent as an acknowledgement. Doing so self-kicked the host and broke Join Party. | disasm `0x00ad7f28`; live |
| `0x13c Promote` | client -> server | Requests ownership transfer. | disasm; live, captured twice in both directions |
| `0x13d OwnerMemberChanged` | server -> client | Writes `room_obj+0x19f0` and fires the ownership callback (`vtable[0x34]`, the "New host : X" print). Re-firing it into an already-established room tore down join-in-progress until it was removed. | disasm `0x00ad37dc`/`0x00ad8070`/`0x00ad817c`; live |
| `0x13e SetHostFlag` | client -> server | RESOLVED 2026-08-19 (live RPCS3 debugger, ~14 hits across an extended two-client session, cross-validated against `0x140`'s own match-end finding). Two sender call sites, `kind=3`/`FUN_00ad6a34` and `kind=4`/`FUN_00ad7024`, both dispatched through confirmed vtable slots (`+0x20`/`+0x34`) on the SessionManager class. `kind=3` is a generic is-host-flag setter (`+0x19f4`) that fires whenever the LOCAL client claims or releases its own host status on either the party object (`0x01387f58`) or the game-room object (`0x01383bd8`) - connect bootstrap, party join/leave/kick, private-match creation, find-match search, game-room lobby creation, and reclaiming party host after a match ends. `kind=4` never touches the host flag at all (confirmed statically); it's a set-then-clear pair tied specifically to the game room's own active-match lifecycle - `1` at map-load completion, `0` at match end, the latter live-confirmed with the same stat-shaped register values as `0x140`'s `selector=0` hit in the same session. Trigger conditions for both are now solidly established; the server-side consequence remains unrecoverable from the client, same as `0x140`. | disasm `0x00ad6a34`/`0x00ad7024`/vtable+0x20 and +0x34 thunks; live RPCS3 debugger, two independent clients |
| `0x13f HostFlagUpdated` | server -> client | Sets `room_obj+0x19f4`. Without it a solo host never becomes host. UPDATED 2026-08-20: for the PARTY room object this byte is ALSO published verbatim into NP presence (blob offset 7) and gates whether a friend's client draws "Join Party" for that host - sending flag=1 for a party host (as this server's RoomCreate and Promote replies both did until 2026-08-20) makes that party permanently unjoinable from every friend's list. Party creates/Promotes now send 0; game/match rooms keep 1, since that copy never reaches presence. See `research/notes/2026-08-20-rejoin-party-bug.md`. | disasm `0x00397dfc`-`0x00397e14` (presence publish), `0x00348e14`/`0x0034be10` (friends-list gate), `0x003cab10`+ (room-object write); live, `kind` 3 or 4 in 117/117 frames; rejoin-party fix live-confirmed |
| `0x143 SetRoomDataBlock` | client -> server | Carries the match-session id string `<owner_npid>.<unix-timestamp>`, generated at match start. | disasm `0x0039ac24`/`0x00ad5528`; live 15/15, owner name and send-time verified |
| `0x144 RoomDataBlockUpdated` | server -> client | Relays that block to the room. | disasm `0x00ad838c`; live |

**Standing rule, learned twice the hard way** (from `0x138` and from `0x13d`):
never re-assert ownership or membership state into a room that is already
established. A genuine Promote still sends `0x13d`; an unchanged one must not.

### Member card relay

| Spec | Who | Why | Where |
|---|---|---|---|
| `0x13a SetMemberData` | client -> server | The client's own card update. On the find-match path the client never sends it - so the server must harvest cards from `0x12f`/`0x130` and replay them, or remote rank/faction render blank. | live; `research/joinparty/2026-08-15-createparty-trace.md` |
| `0x13b MemberUpdatedData` | server -> client | The replay half of that relay: each member's 32-byte card, delivered per-member. | disasm; live |
| `common/member_data` | embedded, both directions | The 32-byte card: `party_id` (roster grouping), `capability_flag` (DLC AND-reduce gating the map picker), `team` (faction sort/colour), `recent_level_0..3` (map-picker "don't replay this" ring), `rank_value` (`journeys*1000 + matches/7`). | disasm producer `FUN_003b15bc` @ `0x003b15dc`+, picker `FUN_003a2310`; live 376+ samples |

`member_data.pad_16` is send-buffer residue, but must be relayed **verbatim** when
forwarding another member's card - the same struct carries the live fields.

Map ids are read out of `recent_level_0`; this ring is the project's only
ground-truth source for them. Named on 01.11 so far: `0x1f` Checkpoint, `0x31`
Lakeside, `0x3a` Suburbs.

### Matchmaking

| Spec | Who | Why | Where |
|---|---|---|---|
| `0x135 FindMatch` | client -> server | A search. `search_obj_ptr` must be echoed in the `0x136` reply, which the handler dereferences; `burst_marker` is the criteria index the host/joiner election keys on. | live 17+ refs; `2026-08-17-find-match-flow.md` |
| `0x136 RoomSearch` | server -> client | The reply listing live public games - what lets a searcher join a host instead of self-hosting. Filtered on the searcher's playlist and build. | disasm (fixed 36-byte declared size confirmed); live |


### Sibling services (port 7320 family)

| Spec | Who | Why | Where |
|---|---|---|---|
| `0x11 hello` / `hello_response` (ticket, heartbeat, leaderboard, facebook, single-player) | client -> server, then server -> client | One multiplexed transport; the service is selected by `service_name`. `ack_magic` 0x22, `session_token`, `server_choice_1`. | disasm `FUN_00acc424` shared-argument proof; live 452 captured hellos |
| `ticket_submit` / `_response` | client -> server, then server -> client | `frame_magic` 0x33, `plaintext_len`, 16-byte `auth_tag`, ciphertext. Encrypt-then-MAC keyed by the per-connection rolling counter - the authentication the whole session hangs off. | disasm `0x00acb6fc`/`0x00acbb90`; live, clean tag checks |
| `heartbeat_line` | client -> server; ack unparsed | `heartbeat <online_id>\n`. Presence beacon that keeps the account in the backend queue tables. | live-corrected against a real capture |
| `leaderboard_line` / `leaderboard_request_line` | client -> server (requests), server -> client (`+`-prefixed rows) | get / range / update grammars, NUL sentinel. A server-initiated EOF is the client's error path. | disasm workers `0x003aeee8`/`0x003af46c`/`0x003afb74`; live |
| `facebook_line` | client -> server, server -> client | The Graph-backed friend/name flow. | disasm `0x00353a68`/`0x00ac1828`; live |
| `report_line` (request half) | client -> server | `is-banned <online_id>\n` - a player-standing / ban check. | live-captured 2026-08-18 |
| `gamelist_line` | client -> server; reply received but **not parsed** | `game-add <session-id>[ <player>]...\n` - registers the started match with the backend game list. Resolved 2026-08-19: the sender is `0x004047f4`, identified by three independent string slots landing in one body (`0x129cd7c` `"game-add "`, `0x129cd8c` `"gamelist-server"`, `0x129cd70` `"games/%s"`). The recv is heartbeat-style and weaker: `li r5,256` @`0x404a14`, a single `bl 0xafacf8` @`0x404a18`, then close - two instructions between recv and close, neither reading `r3`, so the return is overwritten unread. The server must send *something* and must not close first; content is free. | disasm `0x004047f4`-`0x00404a54`; live 50-byte request matching the strcat byte-for-byte (9+19+9+12+1) |
| `stat_line` (single-player-server) | client -> server; reply unparsed, same weak-recv pattern as `gamelist_line` | `stat %s task-%x %s %s\n` (campaign-save path) / `stat %s trophy-%x\n` (trophy-unlock path) - one-way completion telemetry keyed on the player's own NpId. Resolved 2026-08-19, closing a live hypothesis that this service broadcasts campaign chapter progress to friends: it does not - neither call site touches a friend list or a presence API, both run entirely inside save-sync/trophy-unlock handlers. | format strings recovered via TOC anchor+displacement (`research/tools/eboot_analysis`) at two independent call sites, `FUN_007f1acc`/`FUN_00080268`; trophy line's `%x` traced to its `sceNpTrophyUnlockTrophy` argument, fully confirmed |

### Profile

| Spec | Who | Why | Where |
|---|---|---|---|
| `profile_21` envelope | client <-> server, S3 GET/PUT of `profiles/<online_id>/profile.21` | `version`, `enc_len`, `hmac_pad`, `hmac_sha1`, `slack`. Container, crypto, and round-trip solved. | disasm `0x003414dc`+; live round-trip |
| `profile_21.custom_appearance` | same | Character ids per team, survivor variant, equipped items, palette, tint, and the randomise latch. Explains the "random appearance each match" behaviour end to end. | disasm; live |

---

## TIER B - mechanism traced, meaning partial

The producer or consumer is pinned, but the semantic is inferred, constant across
every capture, or locked behind DC `.pak` tables.

| Spec / field | Who | What is known vs missing | Where |
|---|---|---|---|
| `0x140 SetRoomFlags` `attr_selector` / `0x141 UpdatedRoomFlags` | client -> server, then server -> client (confirming echo) | CLIENT-SIDE PURPOSE NAMED 2026-08-19, SERVER-SIDE CONSEQUENCE STILL UNCONFIRMED. Both wire values trace to functions independently named by PRE-EXISTING project research (written 2026-08-17, before today's live session, so this is a cross-check rather than a single investigation confirming itself): selector=1 is sent from `FUN_0035a7dc`, documented as "the lobby / party-screen member-list model rebuild" (UI state `0x11`) - matches every live trigger observed (room creation, loadout render, load-timer completion, actively searching for players). selector=0 is sent from `FUN_003f208c`, documented as the client's `NET_SM_RESULTS` handler that runs the matches/wins/supplies/`OnMatchEnd` crediting body - matches a live hit whose float registers held plainly stat-shaped values (85, 100, 75, 67, 20) at the exact same breakpoint. A full `wire.jsonl` scan confirms these are the ONLY two values ever sent (926:23, exhaustive). LOG-LEVEL CROSS-CHECK (no debugger involved): every selector=0 timestamp compared against every `leaderboard-update` connection in `ticket_server.log` - 20 of 23 (87%) land within 5-31 milliseconds of a leaderboard credit, and the 3 that don't have no nearby leaderboard update at all, matching this project's own prior documentation of private/custom games reaching `NET_SM_RESULTS` without arming the counted-game latch. A third client-side value (8) exists in the sender but is gated out before reaching the wire (fires during a pre-room-resolution find-match sub-state, "Searching for Close Game", where `room_obj+0x10==0` blocks the send). WHY THIS STAYS TIER B: the round-trip is proven inert client-side - no branch anywhere reads the `0x141` echo back into any decision - so there is no client-visible effect from either value, and no retail server survives to show what Naughty Dog's own backend did with a lobby-rebuild vs results notification. | disasm `0x00ad6374`/`0x00ad82ec`/`0x00ad11fc` thunk/`0x0035a7dc`/`0x003f208c`; live RPCS3 debugger across a full match and a full find-match search, cross-checked against the complete wire capture and against `research/notes/2026-08-17-member-blob-vanity-semantics.md` §9d and `2026-08-17-match-counts-latch.md` §1.4 |
| `0x142 HostRank` `entries` | client -> server | FULLY RESOLVED 2026-08-20 (live). The producing getter is `FUN_003CD6C8`, slot 0 of the player vtable `0x01224438` (installed into all 8 player slots at `0x39c4ac`), returning `entry = (b & 0xFFF) + (0x800 if a && (b & 0xFFF) else 0) + (c << 12)` where `b/a/c = player+0x1A8/0x1B0/0x1AC`, all written by `FUN_0039F75C`, with `b`'s live source being `member_slot+0xE8` (the `0x131 Member` entry's own `member_id` off the wire). Five live breakpoint hits (solo, find-match x2, post-loadout, both accounts) confirmed `a=c=0` in every real send, so `entry` reduces to a plain `member_id` in practice - never a rank, never blocked on a ranked account. Correlating `wire.jsonl` against `session_manager.log`'s room-registry `member_id` for two role-swapped live matches plus one historical 3-member capture settles the old "why is `1` never on the wire" question: **the host's own `0x142` lists every OTHER room member's `member_id`, never its own** - `HostRank` reports who else is present, not a self-report. That is also why `count` varies exactly as observed (0 solo, 1 in a 2-player match, 2 in the 3-member capture). Which of `FUN_0039b720`'s seven filters performs the self-exclusion is unpinned (the effect is proven, not the exact instruction) - low-priority, since whose id reaches the wire is now closed. Still proven NOT to be `member_data.rank_value`. | disasm `0x00ad60c4`, `0x003CD6C8`, `0x0039F75C`, `0x00AD34F0`; live RPCS3 breakpoints (5 hits, both accounts); `wire.jsonl`+`session_manager.log` correlation across 3 independent matches; `research/notes/2026-08-20-followup-open-items.md` §3 |
| `room_flags_e8` / `room_flags_10` | - | GATE FULLY RESOLVED for `room_flags_e8` 2026-08-20 (static, on top of the 2026-08-19 live result). The gate is the sender's `param_6`: the `"Host"` call site hardcodes `li r8,0` (@`0x35d434`), so the `0x40000000` OR can never fire there at all; the `"GATHER"` call site passes `1` iff `FUN_003a1f5c() != 0` AND `*(u32*)(0x01459260+0xC) == *(u32*)(candidate+0x8C)` (@`0x3b7f3c`-`0x3b7f54`) - i.e. "the local entitlement word matches this candidate's", using the same caps register that produces `member_data.capability_flag`. That explains the 2026-08-19 live result rather than contradicting it: live RPCS3 breakpoints across two room types (party creation, game-room creation via find-match) both showed the gate register at 0, so the top-nibble variation already seen live must come from the raw `+0xe8` value itself, not this conditional. `room_flags_10` (`0x135`'s own, different function, "identical construction") likely follows the same pattern but wasn't independently live-checked. | disasm; live RPCS3 debugger for `room_flags_e8` |
| `member_data.rank_tier` | - | FULLY RESOLVED 2026-08-20. DC branch proven inert 2026-08-20 (`research/notes/2026-08-20-dc-directory-and-catalogs.md` §1/§3 - the DC record layout is `{key_hash, type_hash, value_ptr}`; `FUN_003c8e30`'s scan loop against `*net-money-info*` returns 0 on the first iteration). The remaining question - who writes the override at `*(global+0x78)` - is ALSO now closed: two independent whole-binary pointer-taint scans (187 and 246 field accesses to the resolved object) agree that offset `0x78` is touched exactly once in the entire 01.00 binary, and that touch is the READ in `FUN_003c8e30` itself, not a write. No writer exists. `rank_tier` is structurally `0x0000` on 01.00 for every account. See `protos/common/member_data.ksy`'s `rank_tier` field doc and `research/notes/2026-08-20-tier2-followup.md` §7. | Both the DC branch and the override write are proven closed - graduated to Tier A in effect, kept here pending a table pass |
| `member_data.capability_flag` bits | - | SOLVED 2026-08-20, bit by bit. The AND-reduce gate is `*net-maps*`'s `+0x14` column (stride 76, instruction-verified at `0x003a2574`-`0x003a25b4`). Decoded from both bundles: bit 0 = a four-map pack (Bookstore/Bus Depot/Hometown/Suburbs), bit 2 = a four-map pack (Water Tower/Coal Mine/Capitol/Wharf), bit 3 = a two-map pack (Plaza/Beach), and bit 1 is required by no map descriptor in either bundle (why the live 01.11 value is `0x0d`, not `0x0f`). Retail marketing names for the packs are not asserted, only what the shipped table requires. See `research/notes/2026-08-20-tier2-followup.md` §1. | disasm `0x003a2574`-`0x003a25b4` (and a second identical gate at `0x0035ad74`-`0x0035ad8c`); byte-exact `*net-maps*` decode from both `dc1/net.bin` and `net10.bin` |
| `stat_line` task line's `%x` (`task-%x`) | client -> server | MECHANISM RE-RESOLVED 2026-08-19 (corrects the prior day's own "task/objective-definitions table" reading, not just the original job-id guess): `FUN_0032241c` is a UI reward/notification-popup builder, not a task-table reader. Its DC base table for hash `0x1ad3445f` (located and structurally confirmed in `net1.bin`/`net10.bin` via `docs/protocol/dc_table.md`'s now-solved container format) is a **string-keyed HUD material/icon-path table** - `_opd_FUN_00ab685c` does a strcmp-based lookup, not a hash lookup, and the literal key resolved for `param_1[0x1b]` is the C string `"general/hud/prize-icon/Default"`. So `task-%x` is whatever integer that icon-path table associates with that fixed key, not a distinct per-task identity. The resolved integer value itself is still open (needs a runtime read - see the field's own doc). | disasm `FUN_0032241c`, `research/ghidra/fm_applyrefs.txt`, `docs/protocol/dc_table.md`; DC00 container solved, resolved-value still open |
| `member_data.card_stat_2` / `card_stat_3` | - | TYPE CORRECTED 2026-08-20: `P+0x654..0x65B` is not a numeric stat pair - it's an 8-byte, NUL-terminated ASCII string (`strcmp`/`strcpy` on the same buffer at `0xe459bc`/`0xe45b10`, confirmed instruction by instruction), and `card_stat_2`/`card_stat_3` are its first four characters. The buffer is reachable from exactly two functions in the whole binary, and the only value either can ever write into it (besides what it reads back from the profile) is the literal string `"*"`, gated on a net-event-recorder object's byte at `+0x40` that no store anywhere touches. Value space closed to `""` or `"*"` on 01.00 - consistent with 855/855 zero frames without "no live data ever populated it" as an unproven excuse. Display meaning of `"*"` (if it ever appears) is still open. See `research/notes/2026-08-20-tier2-followup.md` §2. | disasm `0x0034d378`, `0xe459bc`/`0xe45b10`; live (855 frames, all zero) |
| `value_20` / `value_22` / `value_pair_14` | - | PRODUCER RESOLVED 2026-08-20: `bl 0xacb6bc` @`0xad5c70`, a three-instruction getter reading floats off a config object at `+0x48`/`+0x4C` (`FUN_00acb6bc`). Float-derived pair, live-constant 1000/1000. Reads as a default rating pair, disabled in every capture. | disasm `0x00acb6bc`; live |
| `search_window_lo` / `_hi` | - | SOLVED 2026-08-20: the game's own matchmaking "rank value" (a career kill/death ratio x100, summed over both game modes) +/- a half-width read from the `*net-matchmaking-criteria*` DC column, NOT a constant 0 as previously documented from a smaller sample - nonzero in 653 of 2,188 captured `0x135` frames. The 01.00 producer is a hard-0 stub (dead on the primary build); the ratio is computed only in the 01.11 EBOOT. See `research/notes/2026-08-20-tier2-followup.md` §6 and `protos/0x135_find_match.ksy`. | disasm `0x00ad6d90`-`0x00ad6dc4` (clamp), 01.11 EBOOT `0x3cff10`-`0x3d0054` (rank-value producer); live, numerically verified against stored profiles |
| `caller_arg_1c`, `flag_27` | - | FULLY RESOLVED 2026-08-20 (closed same day, live). `caller_arg_1c` is the sender's `param_5` verbatim (constant `0xffff` across every known call site); `flag_27` is `4` iff the sender's `param_4 != 0`, else `0`. All THREE `bctrl`-dispatched call sites are now known: `0x0035D440` (the `"Host"` game-room state, `r6=0`), `0x003B7FB0` (the `"GATHER"` game-room state, `r6=0`), and - found via a live RPCS3 breakpoint at `FUN_00ad5b78` during a real party join - `0x003CAC5C` inside `FUN_003CA9D0` (the 9-state room state machine), the PARTY path, with `r6=1`. That third site is exactly where the live `0x04` frames come from (`flag_27 = 4 iff r6 != 0`). | disasm `0x00ad5bc0`-`0x00ad5cc0`, `0x0035D3F8`-`0x0035D440`, `0x003B7F3C`-`0x003B7FB0`, `0x003CAB84`-`0x003CAC5C`; live RPCS3 breakpoint for the party site; `research/notes/2026-08-20-followup-open-items.md` §1 |
| `member_slot_ec` (`0x131`/`0x132` entry) | server -> client | STRENGTHENED 2026-08-19: genuinely read off the wire into `member_slot+0xEC` by a shared writer (`0xad34f8`). Independently re-verified (not just trusting the original instruction-band grep) by searching the WHOLE binary for every other site using the same distinctive member-slot-address arithmetic (`room_obj+0x668+slot_index*0x180`) - 30 sites found, none read `+0xEC` nearby. Write-only, functionally inert, on firmer ground than before. Same residual gap as `attr_tail`: an indexed/runtime-computed-offset reader or a bulk-copy read would evade this search too. | disasm; whole-binary idiom search |
| `0x134 trailing` | - | Present because the dispatch loop consumes 24 bytes; not read by the traced portion. | disasm |
| `0x12f room_settings_tail` / `0x130 room_object_tail` | client -> server | RESOLVED 2026-08-19, two different findings. `room_settings_tail` is NOT a room-object copy at all - exhaustive disassembly of its sender (`FUN_00ad5b78`) found zero stores and zero copy calls anywhere touching that stack range; it is pure uninitialised sender-side stack, the same class as this project's `pad_N` fields. `room_object_tail` IS a real copy - `room_obj[0x20:0x40]`, confirmed via its sender's (`FUN_00ad6718`) 64-byte copy loop, with `room_obj` LIVE-CONFIRMED as the party object (`0x01387f58`) during a real party join. An exhaustive scan (both known addressing idioms) of that absolute range found no reader anywhere in the binary - same status as `attr_tail`/`member_slot_ec`. Untested: whether a game-room join uses a different `room_obj`. | disasm, exhaustively enumerated for both senders; live RPCS3 debugger for `room_object_tail`'s source object |
| `np_id.opt` / `np_id.reserved` | - | Sony's opaque bytes, copied verbatim; readers past the handle untraced. | structural only |
| `single_player_server_hello` / `_response` / `stat_line` | client -> server | Structurally confirmed by the same shared-function argument as its siblings, and the post-hello payload grammar is now fully resolved (`stat_line.ksy`) - but **0 of 452 captured hellos** were this service. The specs are sound; that the service ever carries traffic is not established. | disasm `0x00080268`/`0x007f1acc`; no live traffic |
| `profile_21.game_data` interior | - | The 0x5000-byte payload; subsystem index ranges only partly claimed. | partial |
| `0x136 attr_tail` (20 bytes) | client (host's `0x12f`, indirectly) -> server -> client (game-list browser) | GRADUATED FROM TIER C 2026-08-19: both copy sites traced at instruction granularity and live-confirmed in RPCS3's debugger - deserializer copies it verbatim into the entry object, `CONNECT_TO_HOST` copies it again into `g_70`/NetInfo (`0x013835c0` on 01.00 - identity resolved 2026-08-19 by cross-referencing extensive PRE-EXISTING project research that independently maps this same object, including its `+0x6C` counted-game latch and `+0x80` userdata setting) at that object's `0xb0:0xc4`, right before the P2P connection handle. An exhaustive scan of the ONLY addressing path to that object (51 call sites, one compilation unit, `0x3b21e8`-`0x3b978c`) found no other reader of `0xb0:0xc4` anywhere in the retail binary, and no prior note on `g_70` documents a bulk-copy operation that would evade that scan either. So the mechanism is now fully pinned and live-verified; only the INTERIOR MEANING remains unknown - no direct consumer was found to read it back out, only a still-unaudited possibility of a bulk-copy read evading an offset-based scan. | disasm `dispatch_raw2.txt`/`fm_stab_handlers.txt`; live RPCS3 debugger confirmation (r30/r11/memory read all matched prediction exactly); cross-checked against `research/notes/2026-08-17-match-counts-latch.md` and five other independent prior notes naming the same object |

`field_0c` graduated out of this tier on 2026-08-19: it is the **playlist id**,
bundling game mode with party rules in one byte, indexed into a table shipped in
`netN.bin` - which is why numbering is per-build and why the field was misread
three times on 01.00. Ids are **not comparable across builds**.

---

## TIER C - no definition

| Item | Why it is open | What would close it |
|---|---|---|
| `report-server` response grammar | Request captured, reply never observed. Not guessed. | A retail capture. **Fail-open re-verified 2026-08-19 against the 01.11 ELF** (the earlier citation pointed into `research/disasm/full.asm`, which is the **01.00** binary - report-server is 01.11-only, so that address was an unrelated instruction): `-1` default stored @`0x36e1a0`/`0x36e1a8`, the `'+'` test `cmpwi cr7,r0,43` @`0x36e2cc` skipping to the shared done-label `0x36e388`, and `+916`/`+920` written only on a strcmp match @`0x36e360`-`0x36e368`. Nothing needs doing unless a deliberate ban is ever wanted - tagged `TODO(pReportArray)` / `TODO(g_net+920)`. `pReportArray`'s DC directory entry (hash `0xFFAC56F2`) is now pinpointed in net10.bin (`server/ticket_server.py`'s TODO comment) - it currently defines exactly one entry; the entry's name/id are the remaining unknowns. |
| `profile_21` zero region `P+0x1E74..0x5008` | Purpose unknown. | - |
| DC-gated set | Every id->asset map (cosmetics, character and name pools) and net-stat slots not otherwise itemized in this table. The "DC-blocked" framing this row used to carry is now OUTDATED for anything whose DC hash this project has cited: `net1.bin`/`net10.bin`'s container format is solved (`docs/protocol/dc_table.md`) and all three originally-cited hashes (`rank_tier`, `stat_line`'s task table, `pReportArray`) have been traced into the files with concrete, if still partial, results - see their own rows/docs above. FURTHER UNBLOCKED 2026-08-19: two more resolution paths now exist for cosmetic/customization StringIds specifically - `research/tools/text_table.py` (a `text1.psarc` StringId->display-text lookup, `docs/protocol/text_table.md`, confirmed live against real equipped hat/mask/helmet) and `research/tools/dc_hash_crack.py` (a DC-symbol-name reverser against the retail disc's compiler-symbol corpus, confirmed live against `profile_21.ksy`'s `survivor_variant_id`). What's genuinely still blocked: any DC hash this project has **not yet cited anywhere** (no known hash to search for). UPDATE 2026-08-20: the emblem shape/colour catalog (`protos/profile_21.ksy`'s `emblem_layer` type) - previously cited here as a third instance of the un-decoded-nested-payload wall - is now SOLVED for the shape catalog on all four layers, each directly and independently tested (one identical formula, no per-layer offset - an earlier theory that layer2 needed a different offset was retracted once it turned out to be a mislabeled ground-truth value): `shape_index-1` indexes directly into a 192-entry flat name catalog on the retail disc, proven against all 192 entries with zero mismatches via live edit-and-diff testing (`profile21_codec.py`), not a memory read - plus rotation/scale/opacity and the colour picker's 8x8 grid-position formula, solved the same way. Two more customization fields solved by the same method and renamed: `equipped_gesture_id` (was `gated_customization_id`) and `emblem_location` (was `flag_1e40`, corrected from a wrong "boolean" claim to its real 4-value enum). See `research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md` §9-§11 and `research/notes/2026-08-20-emblem-shape-catalog.tsv`. UPDATE 2026-08-20 (second pass, static): the "nested-structure wall" itself was a bug, not a wall - the DC00 directory record is `{key_hash, type_hash, value_ptr}`, not `{value_ptr, key_hash, type_hash}` (see `docs/protocol/dc_table.md`'s "SOLVED 2026-08-20" section); fixing the read makes all 392 of `net.bin`'s globals dumpable by name (`research/tools/dc_dir.py`). That closed the two items this row previously listed as still-open: the emblem colour swatches (`*net-emblem-colors*` = 64 real RGBA f32 values, an 8x8 hue grid) and `equipped_gesture_id` (the "hash algorithm" question was moot - the ids are rows of a real DC table, `*net-taunts*`, no hash-cracking needed; all 11 gestures named, six matching prior live edits exactly). Still unmapped: a still-unidentified 32-bit hash used for the *intra-table* ids (a shape's name-hash, a gesture's id-hash) - confirmed NOT `crc32_mpeg2` by exact single-byte-delta tests, though the CRC-32 polynomial itself (`0x04C11DB7`) is visible in the deltas - and a handful of bytes untouched by every edit tried so far. | For an already-cited hash: try `dc_hash_crack.py`/`text_table.py` first, then `research/tools/dc_dir.py` to walk the corrected directory - most "nested structure" dead ends turned out to be this same off-by-one bug. For an uncited one: still needs a hash to search for in the first place. For a hash that resolves into a nested structure: try a live-edit-and-diff test (`profile21_codec.py diff`) against a real account, or `dc_dir.py` against the corrected layout, BEFORE reaching for a debugger. |
| Intermittent "Host quit for cheating" | Rare teardown, no packet correlated with it yet. | Catch it in a capture. |
| `stat_line` task line's 2nd `%s` | The accessor is pinned (`base+0x2e6c` string field, `_opd_FUN_00952520`), but `base` resolves through a double pointer indirection to `0x01441194` - outside the static file image, so it is a runtime-allocated object with no file-backed content to read. | A live memory read at that address while a campaign autosave is in flight (debugger or emulator), not reachable by static analysis alone. |
| `common/packet_header` | Wrong shape for the layer it describes, and that layer is out of scope. The envelope it gets wrong is already correctly documented in `net_event_dispatch_and_simple_opcodes.md`. | Nothing - delete or rewrite against the dispatch doc. See the scope boundary above. |

---

## Evidence-quality gaps inside tier A

Tier A requires evidence, and disassembly alone is weaker than a live exchange the
client visibly acted on. Two rows do not fully clear that bar:

- **`0x132 RoomJoined`** - never live-verified. The "must not send" conclusion
  rests on disassembly plus an unretained 2026-08-15 regression. The conclusion is
  almost certainly right and is cheap to honour (the message is simply never sent),
  but it has never been tested.
- **`single-player-server` hello** - 0 of 452 captured sibling hellos. Listed in
  tier B above for that reason.

**Live but unexercised** - the message is observed, the claim is not:
`region_language` is constant `"us\0"`+1 in every frame; `party_id` is nonzero in
only 21/376 samples. `capability_flag` left this category on 2026-08-19 when 01.11
DLC clients began sending `0x0d`.

Well-exercised: `team` (0/1/2), `rank_value` (0/1/2), `recent_level_*`,
`roster_count` (1/2/3, the 3 from join-in-progress).
