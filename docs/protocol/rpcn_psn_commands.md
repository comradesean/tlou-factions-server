# RPCN/PSN command & notification families (fourth protocol family)

**Evidence source note (differs from the other three families):** everything
below is read directly from this project's own forked RPCN server source
(`backend/rpcn/`, submodule at commit `5ff5c6f` / tag `1.8.8-1-g5ff5c6f` as of
this doc), not decompiled or captured. Per `CONVENTIONS.md`'s confidence
discipline, that makes numeric IDs, wire framing, and command/notification
purpose **high confidence by construction** wherever a claim is a direct
read of `client.rs`/`notifications.rs`/`cmd_*.rs` - there is no
guesswork about "what the enum discriminant is" the way there is for a
decompiled dispatch table. What's still genuinely uncertain here isn't the
protocol shape, it's **which of RPCN's commands Factions' EBOOT actually
exercises at runtime** - that part leans on the same Ghidra/string-recon
evidence already gathered for the other three families (mainly
`research/notes/clan-tus-commerce-findings.md`'s NID-table dump), which is
decompilation-grade confidence, not source-grade, and is called out
per-command below.

Not part of `net_event_type`, the `0x11` ticket-server family, or the
`NetMatchmaking*`/session-manager family - this is Sony's own PSN client-server
protocol (auth, friends, matching, scoreboards, TUS, signaling), which RPCN
reimplements wholesale as a public, community-documented API. Factions talks
to it exactly like any other PS3 title that links `sceNp`/`sceNp2` would.

## Where this lives, and why it's a separate family from the other three

The other three families were all recovered by reverse-engineering
`EBOOT.elf` - there was no source to read. RPCN is different: it's **already
fully defined in source**, vendored as a git submodule
(`backend/rpcn/`, forked from `RipleyTom/rpcn` - see `backend/README.md`).
`backend/README.md` is explicit that "No Factions-specific server-side logic
has been added to the fork itself yet" - so everything in `backend/rpcn/src/`
is generic RPCN/PSN reimplementation, not anything written for this project.
This doc's job is to catalog that generic surface and mark which parts
Factions' EBOOT evidence says it actually uses.

## Transport & framing

TLS connection (self-hosted fork listens on `Host=0.0.0.0, Port=31313` by
default per `backend/README.md`; RPCS3 is pointed at it via
`config/rpcn.yml`). Every packet - both directions - shares one 15-byte
header (`HEADER_SIZE = 15`, `client.rs`):

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 1 | `packet_type` | `PacketType` enum: `Request=0`, `Reply=1`, `Notification=2`, `ServerInfo=3` |
| 1 | 2 | `command`/`notification_type` (LE u16) | `CommandType` discriminant for `Request`/`Reply`; `NotificationType` discriminant for `Notification` |
| 3 | 4 | `packet_size` (LE u32) | total packet size including this header; capped at `MAX_PACKET_SIZE = 0x800000` (8 MiB) |
| 7 | 8 | `packet_id` (LE u64) | request/reply correlation id; `0` for `Notification` ("packet_id doesn't matter for notifications" - `notifications.rs`) |

**Direction is enforced at the framing level, not just by convention:** the
server's own main read loop (`Client::process`, `client.rs` ~line 520)
disconnects any client whose incoming byte isn't `PacketType::Request` -
`if header_data[0] != PacketType::Request as u8 { warn!(...); break; }`. The
server, conversely, only ever constructs `Reply` (in direct response to a
`Request`, same `packet_id`) or `Notification` (unsolicited, `packet_id=0`)
packets and writes them out via each client's own `channel_sender` -
`Client::create_notification`/`interpret_command`'s reply-building code path.
So: **`CommandType` values are strictly client→server** (carried in
`Request` packets; a `Reply` echoes the same discriminant back but is
itself server→client) and **`NotificationType` values are strictly
server→client** - confirmed structurally by the framing/read-loop code, not
inferred from naming.

## Where directionality gets more interesting: request handlers pushing notifications as a side effect

The two-enum split is clean in principle, but many `CommandType` handlers
don't just reply to the caller - they also construct and push
`NotificationType` messages to **other** connected clients as a side effect
of a single request, via `Client::send_notification`/`send_single_notification`
(or queue one to the caller itself post-reply via `Client::self_notification`).
This doesn't break the direction of either enum (the notification is still
server→client, same as always) but it does mean **a single client action can
fan out server-initiated pushes to third parties**, not just a reply to the
sender - worth knowing before assuming "client sends command X" implies
"only the sender hears back." Confirmed handlers doing this (`grep -rn
"NotificationType::" backend/rpcn/src/server/client/*.rs backend/rpcn/src/server/*.rs`):

| Command handler (`cmd_*.rs`) | Pushes | To whom |
|---|---|---|
| `add_friend` (`cmd_friend.rs`) | `FriendQuery` | the other user (friend request) |
| `remove_friend` (`cmd_friend.rs`) | `FriendLost` | both the caller (self-notification) and the other user |
| `req_signaling_infos` (`cmd_misc.rs`) | `SignalingHelper` | the target user, to help NAT traversal on their end too |
| `send_message` (`cmd_misc.rs`) | `MessageReceived` | the message's recipient(s) |
| `set_presence` (`cmd_misc.rs`) | `FriendPresenceChanged` | the caller's friends |
| `req_join_room`/room join path (`cmd_room.rs`) | `UserJoinedRoom` | other room members |
| `leave_room` (`cmd_room.rs`) | `RoomDestroyed` (if last member) or `UserLeftRoom` | remaining room members |
| `req_set_roomdata_internal` (`cmd_room.rs`) | `UpdatedRoomDataInternal` | other room members |
| `req_set_roommemberdata_internal` (`cmd_room.rs`) | `UpdatedRoomMemberDataInternal` | other room members |
| `req_send_room_message` (`cmd_room.rs`) | `RoomMessageReceived` | other room members (or a specific target) |
| `req_join_room_gui`/GUI room join path (`cmd_room_gui.rs`) | `MemberJoinedRoomGUI` | other GUI-room members |
| `req_quickmatch_gui` (`cmd_room_gui.rs`) | `QuickMatchCompleteGUI` | matched party |
| `gui_room_manager.rs` internals (leave/owner-change paths, triggered from `cmd_room_gui.rs`) | `RoomDisappearedGUI`, `RoomOwnerChangedGUI`, `MemberLeftRoomGUI` | remaining GUI-room members |

## `CommandType` (client→server requests) - `client.rs` ~line 204

Grouped by handling file. "Factions relevance" reflects the NID-import
evidence in `research/notes/clan-tus-commerce-findings.md` (decompilation-grade,
not source-grade - see the note at the top of this doc), not a runtime trace.

### `cmd_account.rs` - account management (generic PSN-adjacent, RPCN's own account system)

`Login`, `Terminate`, `Create`, `Delete`, `SendToken`, `SendResetToken`,
`ResetPassword`. This is **not** a Sony API at all - it's RPCN's own
username/password/email account system (backed by its own SQLite DB and
optional SMTP email flow, `send_email_template`/`send_token_mail` in
`cmd_account.rs`), which every RPCN-hosted title uses identically. **Used by
Factions**: this is simply how any RPCN client authenticates before doing
anything else; not Factions-specific, but load-bearing for every Factions
session.

### `cmd_session.rs`/`cmd_misc.rs`/`cmd_server.rs` - session, presence, tickets, signaling

- `ResetState` (`cmd_misc.rs`) - clears session-level state (rooms, presence) without a full disconnect.
- `SetUserInfo` (`cmd_session.rs`, `req_set_userinfo`) - sets `sceNpMatching2`'s `SCE_NP_MATCHING2_USER_BIN_ATTR_1_ID` (`0x5F`) user binary attribute, a generic per-user opaque blob attached to matching. Generic `sceNpMatching2` capability.
- `GetServerList`/`GetWorldList` (`cmd_server.rs`) - `sceNpMatching2`'s server/world discovery (a title's `ComId` can have multiple logical "worlds"/regions). **Used by Factions** - required before any room create/join under `sceNpMatching2`.
- `RequestSignalingInfos` (`cmd_misc.rs`, `req_signaling_infos`) - the `sceNpSignaling` NAT-traversal/rendezvous request: looks up the target user's cached P2P address info and returns it, while also pushing a `SignalingHelper` notification to the target so their side gets the caller's address too. **Confirmed used by Factions and directly load-bearing for the `net_event_type` family**: `research/notes/network-topology.md` establishes that all 115 `NetEventType` gameplay opcodes travel over a direct P2P UDP link set up via `sceNpSignaling` - this command is exactly the mechanism that hands out the P2P addresses that link is built from.
- `RequestTicket` (`cmd_misc.rs`, `req_ticket`) - generates and returns a signed NP ticket blob (`Ticket::new`/`generate_blob`, `ticket.rs`) for a given `service_id`. **Confirmed used by Factions, and directly the source of the ticket the already-documented ticket-server family submits**: `protos/0x11_ticket_server_ticket_submit.ksy` already states the ticket-server's message C "Carries the raw NP ticket RPCN already issued via `sceNpManagerRequestTicket2`/`sceNpManagerGetTicket`" - this `RequestTicket` command is that issuance, on RPCN's own TLS channel, upstream of the raw-TCP ticket-server handshake on port 7320. This is the one place this family and an already-documented family are known to hand data directly to each other.
- `SendMessage` (`cmd_misc.rs`) - generic PSN inter-user messaging (`sceNpBasic` message types: data attachment, general, add-friend, invite - see the `MessageMainType` enum in `cmd_misc.rs`). Plausible but unconfirmed for Factions (no direct evidence either way).
- `GetNetworkTime` (`cmd_misc.rs`) - trivial server-clock query. Generic.
- `SetPresence` (`cmd_misc.rs`) - sets the caller's rich presence (title/status/comment/data, `ClientSharedPresence`) and notifies friends (`FriendPresenceChanged`). Generic `sceNpBasic` capability; plausible for Factions' friends-list/"what are they playing" UI, unconfirmed.

### `cmd_friend.rs` - friends list (generic `sceNpBasic`)

`AddFriend`, `RemoveFriend`, `AddBlock` (stub, returns `NoError` doing
nothing - `#[allow(dead_code)]`-adjacent no-op in this fork), `RemoveBlock`
(same). Standard PSN friends-list management, identical for every RPCN
title. Not Factions-specific in any way; whether Factions' own UI surfaces
it is unconfirmed but irrelevant to server scope either way (RPCN handles it
completely already).

### `cmd_room.rs`/`cmd_session.rs` - `sceNpMatching2` rooms (generic, but confirmed heavily used by Factions)

`CreateRoom`, `JoinRoom`, `LeaveRoom`, `SearchRoom`, `GetRoomDataExternalList`,
`GetRoomMemberDataExternalList`, `SetRoomDataExternal`, `GetRoomDataInternal`,
`SetRoomDataInternal`, `GetRoomMemberDataInternal`, `SetRoomMemberDataInternal`,
`PingRoomOwner`, `SendRoomMessage`. This is RPCN's reimplementation of Sony's
`sceNpMatching2` room API, protobuf-framed (`np2_structs`,
`CreateJoinRoomRequest`/`JoinRoomRequest`/etc. via `get_com_and_pb::<T>`),
scoped per-title by the 12-byte `ComId`. **Confirmed used by Factions at the
API-surface level**: `research/notes/clan-tus-commerce-findings.md` found
Factions' `sceNp2` import is **100% `sceNpMatching2`, all 29/29 functions
resolved** - i.e. every one of these room commands corresponds to an API
Factions genuinely links and calls. See "Relation to the `NetMatchmaking*`
family" below for how this layer relates to the already-documented
Factions-specific session-manager protocol - they are NOT the same thing.

### `cmd_room_gui.rs` - the *other*, older room API (generic, but likely NOT used by Factions)

`CreateRoomGUI`, `JoinRoomGUI`, `LeaveRoomGUI`, `GetRoomListGUI`,
`SetRoomSearchFlagGUI`, `GetRoomSearchFlagGUI`, `SetRoomInfoGUI`,
`GetRoomInfoGUI`, `QuickMatchGUI`, `SearchJoinRoomGUI`,
`GetRoomMemberDataExternalList`. The source file's own header comment calls
this "Room Commands for **old GUI api**" - this is Sony's original
`sceNpMatching` (v1, no "2") room API that `sceNpMatching2` superseded.
**Likely not used by Factions** (medium confidence, absence-of-import
evidence): `research/notes/clan-tus-commerce-findings.md`'s full resolved
NID dump of Factions' main `sceNp` import (56/56 named) lists
`sceNpManager*`/`sceNpBasic*`/`sceNpSignaling*`/`sceNpLookup*`/
`sceNpProfileCallGui`/`sceNpUtilCmpNpId`/`sceNpDrmIsAvailable[2]`/
`sceNpScoreInit` and nothing else - no `sceNpMatching` (non-"2") function
appears anywhere. Since `sceNp2` is separately confirmed 100%
`sceNpMatching2`, and no plain `sceNpMatching` import exists, this whole
command family is plausibly dead weight for Factions specifically - flagged
here, not independently re-verified this pass (would need a direct
"is `sceNpMatching` linked at all" check to promote past medium confidence).

### `cmd_score.rs` - `sceNpScore` scoreboards (generic, likely barely/not used by Factions)

`GetBoardInfos`, `RecordScore`, `RecordScoreData`, `GetScoreData`,
`GetScoreRange`, `GetScoreFriends`, `GetScoreNpid`. Reimplements Sony's
`sceNpScore` leaderboard API (SQLite-backed board config plus a
filesystem-backed large-score-data blob store, `score_data/*.sdt`).
**Likely barely relevant to Factions** (medium confidence, same
absence-of-import reasoning as the GUI room family):
`research/notes/clan-tus-commerce-findings.md` found exactly **one** Score
function imported anywhere in Factions' `sceNp`/`sceNp2` - `sceNpScoreInit`
- with none of `sceNpScoreRegisterScore`/`GetRanking`/etc. present. That note
already concluded this "suggests Score is barely used, if the game uses it
for anything beyond a token initialization." Factions instead has its own
custom `leaderboard-server` (a sibling of the ticket-server family, port
7320-multiplexed, see `docs/protocol/0x11_sibling_servers_family.md`) which
is the far more likely real leaderboard mechanism - **don't confuse the two**:
this `cmd_score.rs` surface is Sony's/RPCN's generic scoreboard API;
`leaderboard-server` is Naughty Dog's own from-scratch protocol, already
documented separately, unrelated code path.

### `cmd_tus.rs` - `sceNpTus` Title User Storage (generic, confirmed NOT used by Factions)

`TusSetMultiSlotVariable`, `TusGetMultiSlotVariable`, `TusGetMultiUserVariable`,
`TusGetFriendsVariable`, `TusAddAndGetVariable`, `TusTryAndSetVariable`,
`TusDeleteMultiSlotVariable`, `TusSetData`, `TusGetData`,
`TusGetMultiSlotDataStatus`, `TusGetMultiUserDataStatus`,
`TusGetFriendsDataStatus`, `TusDeleteMultiSlotData` - 13 commands, and by far
RPCN's largest single `cmd_*.rs` file (1006 lines). This reimplements Sony's
`sceNpTus` key/value + blob per-user storage service. **Confirmed NOT used by
Factions, high confidence**: `research/notes/clan-tus-commerce-findings.md`
states plainly, from the same full resolved NID dump used above, "No
`sceNpTus*` function appears anywhere in either `sceNp` or `sceNp2`" - not
one of the 13 commands here has a corresponding import in the EBOOT at all.
That note also explains the resulting naming trap: Factions' own
`net-tus-variable.cpp` source filename is coincidental/Naughty-Dog-internal,
not a reference to Sony's TUS - whatever persists Factions' stats/experience
data goes through a different mechanism entirely (working theory: a custom
HTTP(S) backend via `cellHttp`/`cellSsl`, still unconfirmed - see that note).
**Practical implication: this entire command family, despite being the
largest single chunk of RPCN's command surface, can very likely be ignored
for Factions server-parity purposes.**

### `cmd_admin.rs` - RPCN server operator tooling (not a PSN/client API at all)

`UpdateDomainBans`, `TerminateServer`, `UpdateServersCfg`, `BanUser`,
`DelUser` - all gated by `Client::is_admin()`/`check_admin()`, intended for
the server operator's own admin client, not any game client. N/A to the
generic-vs-Factions-specific question; this is operational tooling for
whoever runs the RPCN instance (this project's own dev config sets
`AdminsList=comradesean` per `backend/README.md`).

## `NotificationType` (server→client pushes) - `notifications.rs`

`UserJoinedRoom`, `UserLeftRoom`, `RoomDestroyed`, `UpdatedRoomDataInternal`,
`UpdatedRoomMemberDataInternal` (all `sceNpMatching2` room-state pushes,
paired with the `cmd_room.rs` commands above); `FriendQuery`, `FriendNew`,
`FriendLost`, `FriendStatus`, `FriendPresenceChanged` (friends-list/presence
pushes, `sceNpBasic`); `RoomMessageReceived`, `MessageReceived` (chat/message
delivery); `SignalingHelper` (the P2P-rendezvous-info push described above -
load-bearing for Factions' P2P gameplay link); `MemberJoinedRoomGUI`,
`MemberLeftRoomGUI`, `RoomDisappearedGUI`, `RoomOwnerChangedGUI`,
`QuickMatchCompleteGUI`, and an unused `_UserKickedGUI` (leading underscore in
the enum itself - dead/reserved, never constructed anywhere in
`backend/rpcn/src/`) - all paired with the likely-unused GUI room family
above, so likely similarly low-relevance to Factions specifically.

## Relation to the already-documented `NetMatchmaking*` family - these are two separate matchmaking layers, don't conflate them

This is the point most likely to confuse a future reader, so it's worth
stating plainly:

1. **RPCN's own room system** (`CreateRoom`/`JoinRoom`/etc., this doc, "generic, but confirmed heavily used by Factions" above) is a reimplementation of **Sony's `sceNpMatching2`** - the standard PSN room/matching API any RPCS3 title using that library gets from RPCN "for free," scoped per-title by `ComId`, running over RPCN's own TLS connection (port 31313 in this build's config, same connection as login/friends/tickets/everything else in this doc).
2. **The `NetMatchmaking*` family** (`docs/protocol/session_manager_and_matchmaking.md`, opcodes `0x12d`-`0x148`) is a **raw custom TCP protocol on a separate port (7314)**, opened independently by `g_pSessionManager::Init()`, that does **not** go through `sceNpMatching2` or `sceNpSignaling` at all. That doc's own "Ruled out this pass" section already confirmed this directly: a repo-wide grep for `"7314"`/`"NetMatchmaking"` in `backend/rpcn/` finds nothing, and concluded RPCN's room code "implement[s] Sony's standard `sceNpMatching2` protocol (a different, unrelated NP subsystem)" while `NetMatchmaking*` "is a raw custom TCP protocol... not going through any `sceNpMatching2`/`sceNpSignaling` call... genuinely new protocol surface needing a from-scratch stub." Nothing in this pass overturns that - it's restated here because it's the single most important fact for relating these two docs.

**How they fit together at runtime**, per `research/notes/network-topology.md`'s framing (RPCN mechanically provides "rooms/matchmaking" via `sceNpMatching2` and "P2P rendezvous" via `sceNpSignaling`, while "the actual matchmaking criteria, ready-up/team-assignment flow, and room search/attribute data are game-specific" and live in Factions' own `lobby-flow.cpp`/`net-matchmaking.cpp` plus the `NetMatchmaking*` wire family): the `sceNpMatching2` room (created via this doc's `CreateRoom`, tagged with Factions' `ComId`) is the outer, PSN-level room membership/presence/signaling-info container, while the `NetMatchmaking*` protocol on port 7314 layers Factions' actual lobby state machine, ready-up flow, and richer room search/attribute data on top of it once a session is established. The opaque `SetRoomDataInternal`/`SetRoomDataExternal` blobs this doc's room commands carry are exactly the kind of payload `network-topology.md` already flagged as needing correlation against the `NetMatchmaking*` fields to fully understand - **not resolved by this pass**, left as open work in that note.

**Practical implication for anyone implementing "the server's matchmaking":** it spans *both* layers. RPCN's `room_manager`/`cmd_room.rs` already works generically and needs no Factions-specific code (per `backend/README.md`, nothing has been added to the fork yet and none is obviously required here). The `NetMatchmaking*` layer is the one that's entirely from-scratch Factions-specific protocol, served today by `tools/session_manager_stub.py`. Don't assume RPCN "already handles matchmaking" makes the `NetMatchmaking*` stub redundant, and don't assume the `NetMatchmaking*` stub is the only matchmaking-shaped traffic a real client generates - a real session exercises both concurrently.
