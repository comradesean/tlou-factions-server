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

Current as of 2026-08-19.

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
| `0x131 Member` | server -> client | The roster push, and the load-bearing message of the protocol. `room_id_overwrite` writes `room_obj+0x10` and must be nonzero or the completion latch never arms; `room_capacity_field` writes `room_obj+0x1f8` and zero trips a compiled-in assert. | disasm `0x00ad2734`/`0x00ad3430`/`0x00ad3478`; live, including a confirmed crash on the zero case |
| `0x132 RoomJoined` | server -> client | Understood precisely well enough to know it must NOT be sent: the handler registers a member with `is_local`/`is_owner` hardcoded to 0, creating a phantom slot and self-signaling. Deliberately unused. | disasm `0x00ad79ec`/`0x00ad7b4c`; **never live-verified** - see evidence gaps |
| `0x133 RoomLeaving` | client -> server | Member announces departure, keyed on the room's own `+0x10` id, read and sent immediately before the client zeroes it. | disasm; live |
| `0x134 RoomLeave` | bidirectional - client sends it, and the client's receive-dispatch `FUN_00ad7604` has a case for it | Server relays a departure to remaining members, keyed by `member_id`. | disasm; live |
| `0x139 RoomClosed` | server -> client | "The room is gone" - distinct from `0x138` ("you personally were kicked"). Its handler runs `0x133`'s full teardown AND zeroes the room's id fields. Sent to survivors when an owner departs, and on graceful shutdown. | disasm `0x00ad7fc4`; live since the host-departure fix |
| `0x137 Kickout` | client -> server | Two distinct roles separated by live evidence: `requester=0` is join-flow status, `requester=1` is a real kick. | disasm `0x00ad6570`+; live, both shapes (4x requester=0, 1x requester=1) |
| `0x138 Kickedout` | server -> client | Means "you are kicked" - so it must never be sent as an acknowledgement. Doing so self-kicked the host and broke Join Party. | disasm `0x00ad7f28`; live |
| `0x13c Promote` | client -> server | Requests ownership transfer. | disasm; live, captured twice in both directions |
| `0x13d OwnerMemberChanged` | server -> client | Writes `room_obj+0x19f0` and fires the ownership callback (`vtable[0x34]`, the "New host : X" print). Re-firing it into an already-established room tore down join-in-progress until it was removed. | disasm `0x00ad37dc`/`0x00ad8070`/`0x00ad817c`; live |
| `0x13e SetHostFlag` | client -> server | Host-flag request. Two distinct sender call sites. | disasm `0x00ad6b58`/`0x00ad7120`; live |
| `0x13f HostFlagUpdated` | server -> client | Sets `room_obj+0x19f4`. Without it a solo host never becomes host. | disasm `0x003cab10`+; live, `kind` 3 or 4 in 117/117 frames |
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

Carve-out: `0x136 attr_tail` (20 bytes) is tier C - see below.

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
| `0x140 SetRoomFlags` `attr_selector` | client -> server | Selects *an* attribute (live 0x0000/0x0001) and round-trips into `room_obj+0x1f0`. Which attribute is unknown, and no client branch reads it - the retail server was its only consumer. | disasm `0x00ad6374`/`0x00ad82ec`; live |
| `0x141 UpdatedRoomFlags` | server -> client | The confirmation half; 16 bytes matching SetAttrFlags' own size. Same unknown attribute identity. | disasm `0x00ad82d4`+; thin live evidence |
| `0x142 HostRank` `entries` | client -> server | Per-player values from the player object's `vtable[0]` getter. Proven NOT to be `member_data.rank_value`. Live-constant `0x0002` on unranked accounts, so the encoding needs a ranked capture. | disasm `0x00ad60c4`; live |
| `room_flags_e8` / `room_flags_10` | - | `*(u32*)(obj+0xE8)` conditionally OR'd with `0x40000000`; low 20 bits constant across captures. The `oris` gate condition sits outside the traced function body. | disasm, partial |
| `member_data.rank_tier` | - | Bracket-lookup mechanism verified; the displayed tier needs the DC threshold table (hash `0xC85E199D`). | DC-blocked |
| `member_data.capability_flag` bits | - | The AND-reduce is solved and now has nonzero input (01.11 DLC clients send `0x0d`). Which bit is which DLC pack lives in `.pak` descriptors, not the EBOOT. | DC-blocked |
| `member_data.card_stat_2` / `card_stat_3` | - | Bytes and source pinned (`P+0x654`, the character-customization word); display meaning unresolved. | disasm |
| `0x13e` `flag` byte | client -> server | Boolean when written, but live values 0/1/3/4, with the stale value often equal to the frame's own `kind`. Only 0 and 1 are meaningful; which UI path drives kind 3 vs 4 is vtable-dispatched and untraced. | disasm + live |
| `value_20` / `value_22` / `value_pair_14` | - | Float-derived pair, live-constant 1000/1000. Reads as a default rating pair, disabled in every capture. | live |
| `search_window_lo` / `_hi` | - | A clamped rating/filter window; 0 in every capture (disabled while searching). | live |
| `caller_arg_1c`, `flag_27` | - | `0xffff`/`0x0000` and 0/4 respectively; the callers and branch conditions are untraced. | disasm, partial |
| `member_slot_ec` (`0x131` entry) | server -> client | Genuinely read off the wire into `member_slot+0xEC`; the consumer of that slot is not pinned. | disasm |
| `0x134 trailing` | - | Present because the dispatch loop consumes 24 bytes; not read by the traced portion. | disasm |
| `0x12f room_settings_tail` / `0x130 room_object_tail` | client -> server | Provenance known - copies of specific room-object spans - interiors not field-mapped. | disasm |
| `np_id.opt` / `np_id.reserved` | - | Sony's opaque bytes, copied verbatim; readers past the handle untraced. | structural only |
| `single_player_server_hello` / `_response` / `stat_line` | client -> server | Structurally confirmed by the same shared-function argument as its siblings, and the post-hello payload grammar is now fully resolved (`stat_line.ksy`) - but **0 of 452 captured hellos** were this service. The specs are sound; that the service ever carries traffic is not established. | disasm `0x00080268`/`0x007f1acc`; no live traffic |
| `profile_21.game_data` interior | - | The 0x5000-byte payload; subsystem index ranges only partly claimed. | partial |

`field_0c` graduated out of this tier on 2026-08-19: it is the **playlist id**,
bundling game mode with party rules in one byte, indexed into a table shipped in
`netN.bin` - which is why numbering is per-build and why the field was misread
three times on 01.00. Ids are **not comparable across builds**.

---

## TIER C - no definition

| Item | Why it is open | What would close it |
|---|---|---|
| `report-server` response grammar | Request captured, reply never observed. Not guessed. | A retail capture. **Fail-open re-verified 2026-08-19 against the 01.11 ELF** (the earlier citation pointed into `research/disasm/full.asm`, which is the **01.00** binary - report-server is 01.11-only, so that address was an unrelated instruction): `-1` default stored @`0x36e1a0`/`0x36e1a8`, the `'+'` test `cmpwi cr7,r0,43` @`0x36e2cc` skipping to the shared done-label `0x36e388`, and `+916`/`+920` written only on a strcmp match @`0x36e360`-`0x36e368`. Nothing needs doing unless a deliberate ban is ever wanted - tagged `TODO(pReportArray)` / `TODO(g_net+920)`. |
| `0x136 attr_tail` (20 bytes) | NARROWED 2026-08-19: both copy sites are now traced at instruction granularity. The `0x136` deserializer copies it verbatim (wire `0x24:0x38` -> entry_obj `0x18:0x2c`, a fixed -0xc offset, confirmed via `dispatch_raw2.txt`'s `lbz`/`stb` loop), and `_opd_FUN_003b2a9c` (CONNECT_TO_HOST) copies the *whole* attribute block including this span into a live peer-connection object at that object's `0x98:0xc4`, right before writing the P2P connection handle to the same object's `+0x1a48` (a field independently confirmed load-bearing elsewhere). So attr_tail is proven to ride into a real, actively-used object at the exact moment the client commits to dialing a host - not proven inert, and not a throwaway copy. What's still open is narrower: no reader of that destination object's `0x98:0xc4` span was found. | Pin the peer-connection struct's concrete type from its confirmed fields (id `+0x98`, npid+attr_tail `+0xa0:0xc4`, P2P handle `+0x1a48`) and enumerate readers of `+0xb0:0xc4` on that type specifically (a bare offset grep is too noisy - those offsets collide with unrelated structs binary-wide); or correlate against a capture varying one search option at a time. |
| `0x12f room_settings_tail` (32 bytes), `0x130 room_object_tail` (32 bytes) | Unmapped room-object spans. Provenance known, interiors not. | Field-map the source spans in the room object. |
| `0x140`'s attribute identity | No client branch reads it; only the retail server consumed it. | A retail-server capture, or resolving the vtable-dispatched caller. |
| `0x142` encoding for a ranked account | Live-constant `0x0002` on every unranked account captured. | One capture from a ranked account. |
| `0x13e` kind 3 vs kind 4 | Vtable dispatch; not statically resolvable. | Runtime trace. |
| `profile_21` zero region `P+0x1E74..0x5008` | Purpose unknown. | - |
| DC-blocked set | All net-stat slots (including the supplies gate), `rank_tier` thresholds, and every id->asset map (cosmetics, character and name pools). | Extract the `net1.bin`/`net10.bin` registries. Not reachable by decompiling the EBOOT. |
| Intermittent "Host quit for cheating" | Rare teardown, no packet correlated with it yet. | Catch it in a capture. |
| `stat_line` task line's 2nd `%s` | The accessor is pinned (`base+0x2e6c` string field, `_opd_FUN_00952520`), but `base` resolves through a double pointer indirection to `0x01441194` - outside the static file image, so it is a runtime-allocated object with no file-backed content to read. | A live memory read at that address while a campaign autosave is in flight (debugger or emulator), not reachable by static analysis alone. |
| `stat_line` task line's `%x` (`task-%x`) | `param_1[0x1b]` is read with the same idiom across leaderboard's and find-match's own connection-state structs too, suggesting a shared per-connection/job-id field rather than a campaign objective id - but no single writer of the field was traced to confirm it. | Trace a writer of offset `0x1b` in one of the structs that share this read idiom. |
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
