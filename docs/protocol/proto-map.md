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

Current as of 2026-08-22. Rows for `rank_tier`, `capability_flag`, `search_window_lo`/`_hi`,
`caller_arg_1c`/`flag_27`, `value_20`/`value_22`, `card_string_0`/`card_string_1`, and
`0x13f HostFlagUpdated` were updated 2026-08-20 to reflect that day's findings
(`research/notes/2026-08-20-tier2-followup.md`, `2026-08-20-rejoin-party-bug.md`);
see those rows for what changed. A later pass the same day
(`research/notes/2026-08-20-followup-open-items.md`) then resolved
`FUN_00ad5b78`'s caller, `0x13e` kind=3's encoding selector, and `0x142`'s
per-entry structure, and closed `capability_flag` bit 1 - the
`caller_arg_1c`/`flag_27`, `0x142 HostRank`, and `room_flags_e8` rows below
carry those updates. The `0x131 Member` row's citation was also
corrected (the addresses it previously cited did not show the write it claims).

UPDATED 2026-08-22: all eight sibling services are now handled. `gamelist-server`
joined them on 2026-08-19; `single-player-server` (`stat_line`) went from "never
observed carrying traffic" to both grammars LIVE-CONFIRMED 2026-08-21/22, and the
`report-server` *response* grammar was resolved 2026-08-21 (fail-open on every
branch; the server's existing empty-body stub is provably correct without ever
needing a live retail reply) - see tier A below for both.

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
| `0x131 Member` | server -> client | The roster push, and the load-bearing message of the protocol. `room_id_overwrite` writes `room_obj+0x10` and must be nonzero or the completion latch never arms; `max_players` (was `room_capacity_field`, renamed 2026-08-21) writes `room_obj+0x1f8` and zero trips a compiled-in assert. | CITATION CORRECTED 2026-08-20: the claim is correct but the previously-cited addresses (`0x00ad2734`/`0x00ad3430`/`0x00ad3478`) do not show it - `ad2734` is an unrelated `member_data_length==32` check, `ad3430`/`ad3478` are a register move and a bare branch inside the slot-lookup loop. The actual writes are `ld r9,16(r28)`/`std r9,16(r29)` @`0x00ad7804`-`0x00ad7808` (`room_id_overwrite`) and `lhz r0,24(r28)`/`stw r0,504(r29)` in the same range (`max_players`), matching `protos/0x131_member.ksy`'s own citation. disasm `0x00ad7804`-`0x00ad7808`; live, including a confirmed crash on the zero case |
| `0x132 RoomJoined` | server -> client | Understood precisely well enough to know it must NOT be sent: the handler registers a member with `is_local`/`is_owner` hardcoded to 0, creating a phantom slot and self-signaling. Deliberately unused. | disasm `0x00ad79ec`/`0x00ad7b4c`; **never live-verified** - see evidence gaps |
| `0x133 RoomLeaving` | client -> server | Member announces departure, keyed on the room's own `+0x10` id, read and sent immediately before the client zeroes it. | disasm; live |
| `0x134 RoomLeave` | bidirectional - client sends it, and the client's receive-dispatch `FUN_00ad7604` has a case for it | Server relays a departure to remaining members, keyed by `member_id`. | disasm; live |
| `0x139 RoomClosed` | server -> client | "The room is gone" - distinct from `0x138` ("you personally were kicked"). Its handler runs `0x133`'s full teardown AND zeroes the room's id fields. Sent to survivors when an owner departs, and on graceful shutdown. | disasm `0x00ad7fc4`; live since the host-departure fix |
| `0x137 Kickout` | client -> server | Two distinct roles separated by live evidence: `requester=0` is join-flow status, `requester=1` is a real kick. | disasm `0x00ad6570`+; live, both shapes (4x requester=0, 1x requester=1) |
| `0x138 Kickedout` | server -> client | Means "you are kicked" - so it must never be sent as an acknowledgement. Doing so self-kicked the host and broke Join Party. | disasm `0x00ad7f28`; live |
| `0x13c Promote` | client -> server | Requests ownership transfer. | disasm; live, captured twice in both directions |
| `0x13d OwnerMemberChanged` | server -> client | Writes `room_obj+0x19f0` and fires the ownership callback (`vtable[0x34]`, the "New host : X" print). Re-firing it into an already-established room tore down join-in-progress until it was removed. | disasm `0x00ad37dc`/`0x00ad8070`/`0x00ad817c`; live |
| `0x13e SetHostFlag` | client -> server | RESOLVED (live). Two sender call sites: `kind=3`/`FUN_00ad6a34` is a generic is-host-flag setter, firing whenever the LOCAL client claims or releases its own host status on either the party or game-room object; `kind=4`/`FUN_00ad7024` never touches the host flag itself - it's a set-then-clear pair tied to the game room's active-match lifecycle (`1` at map-load completion, `0` at match end). Its `flag` byte is a real value (0, 1, or 3 on `kind=3`; 0 or 4 on `kind=4`), not residue. Trigger conditions for both are solidly established; the server-side consequence remains unrecoverable from the client, same as `0x140`. See `docs/protocol/knowledge-inventory.md` items 15 and 41 for the full trace. | disasm `0x00ad6a34`/`0x00ad7024`/vtable+0x20 and +0x34 thunks; live RPCS3 debugger, two independent clients |
| `0x13f HostFlagUpdated` | server -> client | Sets `room_obj+0x19f4`. Without it a solo host never becomes host. For the PARTY room object this byte is ALSO published verbatim into NP presence and gates whether a friend's client draws "Join Party" for that host (see `docs/protocol/knowledge-inventory.md` item 15 for the mechanism trace). SERVER FIX: party creates/Promotes now send 0; game/match rooms keep 1, since that copy never reaches presence - sending flag=1 for a party host previously made the party permanently unjoinable from every friend's list. | disasm `0x00397dfc`-`0x00397e14` (presence publish), `0x00348e14`/`0x0034be10` (friends-list gate), `0x003cab10`+ (room-object write); live; rejoin-party fix live-confirmed |
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
| `report_line` request / response | client -> server, then server -> client | Request: `is-banned <online_id>\n` - a player-standing / ban check, live-captured 2026-08-18. Response grammar RESOLVED 2026-08-21: `+<ban_index> <name>`, single-pass, fail-open on every branch - re-verified instruction-by-instruction against a fresh 01.11 objdump. No live retail reply was captured or is needed: the fail-open analysis alone proves `server/ticket_server.py`'s existing empty-body stub (`handle_report`/`build_report_response`, present since 2026-08-19) is a correct answer. See `docs/protocol/knowledge-inventory.md` item 31 (also cross-referenced as item 50) for the full trace. | request: live-captured 2026-08-18; response: `research/notes/2026-08-21-report-server-response-grammar.md`, `protos/0x11_report_line.ksy`'s `ban_reply_row` type |
| `gamelist_line` | client -> server; reply received but **not parsed** | `game-add <session-id>[ <player>]...\n` - registers the started match with the backend game list. Resolved 2026-08-19: the sender is `0x004047f4`, identified by three independent string slots landing in one body (`0x129cd7c` `"game-add "`, `0x129cd8c` `"gamelist-server"`, `0x129cd70` `"games/%s"`). The recv is heartbeat-style and weaker: `li r5,256` @`0x404a14`, a single `bl 0xafacf8` @`0x404a18`, then close - two instructions between recv and close, neither reading `r3`, so the return is overwritten unread. The server must send *something* and must not close first; content is free. | disasm `0x004047f4`-`0x00404a54`; live 50-byte request matching the strcat byte-for-byte (9+19+9+12+1) |
| `single_player_server_hello` / `_response` / `stat_line` (single-player-server) | client -> server, then server -> client for the hello; `stat_line` reply unparsed, same weak-recv pattern as `gamelist_line` | Structurally confirmed by the same shared-function argument as its siblings. THE LINE PROTOCOL ITSELF IS TIER A: both `stat_line` grammars are LIVE-CONFIRMED 2026-08-21/22 - `stat %s task-%x %s %s\n` (campaign-save path, seven captures) and `stat %s trophy-%x\n` (trophy-unlock path, two captures), all matching the decompiled format strings byte-for-byte - after finding and fixing a real dead upstream `campaign.config.txt.crypt` dependency this server now serves a working replacement for (previously 0 of 452 captured hellos were this service). One-way completion telemetry keyed on the player's own NpId; closes a live hypothesis that this service broadcasts campaign chapter progress to friends - it does not, neither call site touches a friend list or a presence API, both run entirely inside save-sync/trophy-unlock handlers. The line's own product-code field is separately fully resolved: the 2nd `%s` on the campaign-save line is `BCUS98174`, the title's own PS3 product/serial code, a per-title runtime constant. NOT covered by this Tier A claim: `task-%x`'s specific resolved VALUE meaning - that stays Tier B (see below). | disasm `0x00080268`/`0x007f1acc`, format strings recovered via TOC anchor+displacement (`research/tools/eboot_analysis`); trophy line's `%x` traced to its `sceNpTrophyUnlockTrophy` argument, fully confirmed; both grammars LIVE-CONFIRMED 2026-08-21/22; see `docs/protocol/knowledge-inventory.md` items 31b and 56 |

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
| `0x140 SetRoomFlags` `attr_selector` / `0x141 UpdatedRoomFlags` | client -> server, then server -> client (confirming echo) | CLIENT-SIDE PURPOSE NAMED, SERVER-SIDE CONSEQUENCE UNCONFIRMED: selector=1 marks a lobby/roster-model rebuild, selector=0 marks match-end stat crediting (`NET_SM_RESULTS`) - the only two values ever sent. The round-trip is proven inert client-side (nothing reads the `0x141` echo back), so no client-visible effect exists for either value. See `docs/protocol/knowledge-inventory.md` item 36 for the full trace. | disasm `0x00ad6374`/`0x00ad82ec`/`0x00ad11fc` thunk/`0x0035a7dc`/`0x003f208c`; live RPCS3 debugger across a full match and a full find-match search |
| `0x142 HostRank` `entries` | client -> server | FULLY RESOLVED (live): `entries` is a packed bitfield that reduces in every real send to a plain `member_id`, never a rank. The host's own `0x142` lists every OTHER room member's id, never its own - which is why `1` never appears on the wire and why `count` matches roster size minus the host. Still proven NOT to be `member_data.rank_value`. See `docs/protocol/knowledge-inventory.md` item 37 for the full trace. | disasm `0x00ad60c4`, `0x003CD6C8`, `0x0039F75C`, `0x00AD34F0`; live RPCS3 breakpoints (5 hits, both accounts); `wire.jsonl`+`session_manager.log` correlation across 3 independent matches |
| `room_flags_e8` / `room_flags_10` | - | GATE FULLY RESOLVED for `room_flags_e8`: the sender's `param_6` conditional (an entitlement-word match against the candidate, using the same caps register as `capability_flag`) never fires in either live-tested room type, so the observed top-nibble variation comes from the raw `+0xe8` value itself, not this conditional. `room_flags_10` likely follows the same pattern but wasn't independently live-checked. See `docs/protocol/knowledge-inventory.md` item 35 for the full trace. | disasm; live RPCS3 debugger for `room_flags_e8` |
| `member_data.rank_tier` | - | FULLY RESOLVED. The DC branch (`*net-money-info*`) can only ever produce 0, and an exhaustive whole-binary pointer-taint scan found no writer anywhere for the override at `+0x78`. `rank_tier` is structurally `0x0000` on 01.00 for every account. See `docs/protocol/knowledge-inventory.md` item 38 for the full trace. | Both the DC branch and the override write are proven closed - graduated to Tier A in effect, kept here pending a table pass |
| `member_data.capability_flag` bits | - | SOLVED, bit by bit, against `*net-maps*`'s required-mask column: bit 0/2/3 each gate a specific map pack (four-map, four-map, two-map), bit 1 is required by no map descriptor in either bundle (why the live 01.11 value is `0x0d`, not `0x0f`) and is consumed by nothing. Retail marketing names for the packs are not asserted, only what the shipped table requires. See `docs/protocol/knowledge-inventory.md` item 39 for the full trace. | disasm `0x003a2574`-`0x003a25b4` (and a second identical gate at `0x0035ad74`-`0x0035ad8c`); byte-exact `*net-maps*` decode from both `dc1/net.bin` and `net10.bin` |
| `stat_line` task line's `%x` (`task-%x`) | client -> server | MECHANISM RESOLVED: not a per-task identity, but a UI reward-icon lookup against a fixed HUD material/icon-path key, resolved through a 5-slot dynamic content-module registry - which is why seven real captures all differ even though the lookup key is compile-time-constant. What's still open: which module the registry has registered at each point, and the resolved integer's specific identity (DC-blocked). See `docs/protocol/knowledge-inventory.md` item 53 for the full trace. | disasm `FUN_0032241c`, `research/ghidra/fm_applyrefs.txt`, `docs/protocol/dc_table.md`; DC00 container solved, mechanism live-confirmed, registry-module identity still open |
| `member_data.card_string_0` / `card_string_1` | - | TYPE CORRECTED: `P+0x654..0x65B` is not a numeric stat pair - it's an 8-byte NUL-terminated ASCII string, and `card_string_0`/`card_string_1` are its first four characters. Value space is closed to `""` or the literal `"*"` on 01.00 (consistent with 855/855 zero live frames). Display meaning of `"*"`, if it ever appears, is still open. See `docs/protocol/knowledge-inventory.md` item 40 for the full trace. | disasm `0x0034d378`, `0xe459bc`/`0xe45b10`; live (855 frames, all zero) |
| `value_20` / `value_22` / `value_pair_14` | - | SENTINEL VALUE, fully traced: all three wire fields echo the same `g_70`/NetInfo `+0x48`/`+0x4c` pair, hardcoded to `1000.0` once at NetInit and never observed to change in any live capture. The exact parameter it configures (timeout vs. threshold vs. something else) was not recovered. See `docs/protocol/knowledge-inventory.md` item 42 for the full trace. | disasm `0x00acb6bc`, `0x00ad5c68`, `0x00ad6cf4`; live register dump corroboration |
| `search_window_lo` / `_hi` | - | SOLVED: the game's own matchmaking rank value (a career kill/death ratio x100, summed over both game modes) +/- a half-width from the `*net-matchmaking-criteria*` DC column - NOT a constant 0 as previously documented from a smaller sample, nonzero in 653 of 2,188 captured `0x135` frames. The 01.00 producer is a hard-0 stub; the ratio is computed only in the 01.11 EBOOT. See `docs/protocol/knowledge-inventory.md` item 43 for the full trace. | disasm `0x00ad6d90`-`0x00ad6dc4` (clamp), 01.11 EBOOT `0x3cff10`-`0x3d0054` (rank-value producer); live, numerically verified against stored profiles |
| `caller_arg_1c`, `is_party` (was `flag_27`, renamed 2026-08-21) | - | FULLY RESOLVED, live. `caller_arg_1c` is the sender's `param_5` verbatim (constant `0xffff` at two of three known call sites); `is_party` is `4` iff the sender's `param_4 != 0`, else `0` - an exhaustive 3-for-3 party/non-party split across all three known call sites, which is why this field was judged confident enough to rename. See `docs/protocol/knowledge-inventory.md` items 44 and 45 for the full trace. | disasm `0x00ad5bc0`-`0x00ad5cc0`, `0x0035D3F8`-`0x0035D440`, `0x003B7F3C`-`0x003B7FB0`, `0x003CAB84`-`0x003CAC5C`; live RPCS3 breakpoint for the party site |
| `member_slot_ec` (`0x131`/`0x132` entry) | server -> client | STRENGTHENED: genuinely read off the wire into `member_slot+0xEC` by a shared writer; a whole-binary search for every other site using the same member-slot addressing idiom (30 sites) found no reader nearby. Write-only, functionally inert. Same residual gap as `attr_tail`: an indexed or bulk-copy reader would evade this search. See `docs/protocol/knowledge-inventory.md` item 46 for the full trace. | disasm; whole-binary idiom search |
| `0x134 trailing` | - | Present because the dispatch loop consumes 24 bytes; not read by the traced portion. See `docs/protocol/knowledge-inventory.md` item 47. | disasm |
| `0x12f room_settings_tail` / `0x130 room_object_tail` | client -> server | RESOLVED, two different findings. `room_settings_tail` is NOT a room-object copy at all - it's pure uninitialised sender-side stack, the same class as this project's `pad_N` fields. `room_object_tail` IS a real copy (`room_obj[0x20:0x40]`), with `room_obj` LIVE-CONFIRMED as the party object during a real party join; an exhaustive scan found no reader anywhere in the binary. Untested: whether a game-room join uses a different `room_obj`. See `docs/protocol/knowledge-inventory.md` item 49 for the full trace. | disasm, exhaustively enumerated for both senders; live RPCS3 debugger for `room_object_tail`'s source object |
| `np_id.opt` / `np_id.reserved` | - | Sony's opaque bytes, copied verbatim; readers past the handle untraced. See `docs/protocol/knowledge-inventory.md` item 48. | structural only |
| `profile_21.game_data` interior | - | The 0x5000-byte payload; subsystem index ranges only partly claimed. See `docs/protocol/knowledge-inventory.md` item 51 for the DC stat-registry lead. | partial |
| `0x136 attr_tail` (20 bytes) | client (host's `0x12f`, indirectly) -> server -> client (game-list browser) | GRADUATED FROM TIER C: both copy sites traced at instruction granularity and live-confirmed - lands verbatim in `g_70`/NetInfo at `0xb0:0xc4`, right before the P2P connection handle. An exhaustive scan of the object's only addressing path found no reader anywhere in the retail binary. Mechanism fully pinned and live-verified; only the INTERIOR MEANING remains unknown. See `docs/protocol/knowledge-inventory.md` item 49a for the full trace. | disasm `dispatch_raw2.txt`/`fm_stab_handlers.txt`; live RPCS3 debugger confirmation (r30/r11/memory read all matched prediction exactly) |

`field_0c` graduated out of this tier on 2026-08-19: it is the **playlist id**,
bundling game mode with party rules in one byte, indexed into a table shipped in
`netN.bin` - which is why numbering is per-build and why the field was misread
three times on 01.00. Ids are **not comparable across builds**. See
`docs/protocol/knowledge-inventory.md` item 34 for the full trace, including the
private-match value's separately-resolved randomness.

`single_player_server_hello` / `_response` / `stat_line` graduated out of this
tier on 2026-08-22, matching `knowledge-inventory.md`'s current classification
(item 31b): both `stat_line` line grammars are now LIVE-CONFIRMED, so the LINE
PROTOCOL is Tier A - see the Tier A sibling-services table above. The `task-%x`
VALUE's specific resolved meaning did NOT graduate with it and stays in this
tier (see the `task-%x` row below, and `docs/protocol/knowledge-inventory.md`
item 53).

Five more fields graduate out of this tier on 2026-08-22, on a documentation
consistency pass that found their prose already read as resolved without the
formal pointer this section uses elsewhere. Rows are kept in the table above
for their evidence detail; this paragraph is the promotion record.

`0x142 HostRank`'s `entries` field: the per-entry value is a plain
`member_id`, never a rank, and the host's own `0x142` structurally lists only
OTHER room members, never itself - which is also why the message name reads
correctly at face value. The six auxiliary per-candidate filters in the
collector (`FUN_0039b720`) whose semantics were not traced past their byte
offset/polarity do not bear on this: the server ignores the whole message and
need not interpret them. See `docs/protocol/knowledge-inventory.md` item 37.

`member_data.rank_tier` (already marked "graduated to Tier A in effect" in
its own row above, pending exactly this pass): both the DC branch
(structurally always 0) and the `+0x78` override (no writer anywhere in the
01.00 binary) are fully closed. See `docs/protocol/knowledge-inventory.md`
item 38.

`member_data.capability_flag`'s individual bit meanings: bits 0/2/3 each gate
a specific DLC map pack, bit 1 is required by no map descriptor in either
bundle and consumed by nothing, and every one of the mask's five consumers
has been enumerated. Retail marketing names for the packs remain unasserted,
but that is cosmetic, not a mechanism gap. See
`docs/protocol/knowledge-inventory.md` item 39.

`search_window_lo` / `search_window_hi`: the windowed value is the game's own
matchmaking rank value (a career kill/death ratio x100 on 01.11, a hard-0
stub on the primary 01.00 build) plus a DC-column half-width, numerically
verified end to end against two stored profiles. See
`docs/protocol/knowledge-inventory.md` item 43.

`caller_arg_1c` and `is_party`: both are resolved against an exhaustive,
live-confirmed enumeration of all three call sites reaching the shared
RoomCreate sender - `caller_arg_1c` is a per-call-path constant token,
`is_party` a clean 3-for-3 party/non-party split. See
`docs/protocol/knowledge-inventory.md` items 44 and 45.

---

## TIER C - no definition

| Item | Why it is open | What would close it |
|---|---|---|
| `profile_21` zero region `P+0x1E74..0x5008` | MOSTLY RESOLVED (see `docs/protocol/profile_21_record.md`) - `P+0x1E8C..0x5008` is CLOSED (confirmed zero, reserved/unused); `P+0x1E74..0x1E8B` (`promotion_flags_1e74`) is narrowed but not closed - non-zero on one of three accounts, correlates with `milestone_latch_1e2c`, static analysis now exhausted. See `docs/protocol/knowledge-inventory.md` item 52 for the full trace. | Only remaining unblock: a live RPCS3 memory-write-breakpoint test. |
| DC-gated set | Every id->asset map (cosmetics, character and name pools) and net-stat slots not otherwise itemized in this table. The "DC-blocked" framing is now OUTDATED for anything whose DC hash this project has cited: `net1.bin`/`net10.bin`'s container format is solved (`docs/protocol/dc_table.md`), all 392 of `net.bin`'s globals are dumpable by name (`research/tools/dc_dir.py`), and the emblem shape/colour catalogs plus `equipped_gesture_id`/`emblem_location` are fully solved. What's genuinely still blocked: any DC hash this project has **not yet cited anywhere** (no known hash to search for), and the still-unidentified 32-bit hash used for *intra-table* ids (confirmed NOT `crc32_mpeg2`, though its polynomial is visible in the deltas). See `docs/protocol/knowledge-inventory.md` item 53 for the full trace. | For an already-cited hash: try `dc_hash_crack.py`/`text_table.py` first, then `research/tools/dc_dir.py` to walk the corrected directory. For an uncited one: still needs a hash to search for in the first place. For a hash that resolves into a nested structure: try a live-edit-and-diff test (`profile21_codec.py diff`) against a real account, or `dc_dir.py` against the corrected layout, BEFORE reaching for a debugger. |
| Intermittent "Host quit for cheating" | Rare teardown, no packet correlated with it yet. RECHECKED: the string appears nowhere in `server/logs/`. See `docs/protocol/knowledge-inventory.md` item 55. | Catch it in a capture. |
| `common/packet_header` | Wrong shape for the layer it describes, and that layer is out of scope. The envelope it gets wrong is already correctly documented in `net_event_dispatch_and_simple_opcodes.md`. | Nothing - delete or rewrite against the dispatch doc. See the scope boundary above. |

Two more items graduated out of this tier on 2026-08-22, matching
`knowledge-inventory.md`'s current classification: the `report-server`
*response* grammar (`+<ban_index> <name>`, single-pass, fail-open on every
branch - knowledge-inventory item 50/31, "no longer Tier 3") is folded into the
Tier A `report_line` row above, and `stat_line`'s task line 2nd `%s`
(`BCUS98174`, the title's own PS3 product/serial code - item 56) is folded into
the Tier A `stat_line` row above.

---

## Evidence-quality gaps inside tier A

Tier A requires evidence, and disassembly alone is weaker than a live exchange the
client visibly acted on. One row does not fully clear that bar:

- **`0x132 RoomJoined`** - never live-verified. The "must not send" conclusion
  rests on disassembly plus an unretained 2026-08-15 regression. The conclusion is
  almost certainly right and is cheap to honour (the message is simply never sent),
  but it has never been tested.

**`single-player-server` hello** - RESOLVED 2026-08-21/22, no longer belongs in
this gap list: after 0 of 452 captured sibling hellos, both `stat_line` grammars
were live-confirmed the same night (see the Tier A sibling-services table
above).

**Live but unexercised** - the message is observed, the claim is not:
`region_language` is constant `"us\0"`+1 in every frame; `party_id` is nonzero in
only 21/376 samples. `capability_flag` left this category on 2026-08-19 when 01.11
DLC clients began sending `0x0d`.

Well-exercised: `team` (0/1/2), `rank_value` (0/1/2), `recent_level_*`,
`roster_count` (1/2/3, the 3 from join-in-progress).
