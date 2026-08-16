# Protocol Documentation Index

**Numeric opcode IDs are confirmed** for 115 `NetEventType` values (0-114) — recovered directly from an in-memory enum-to-name table via Ghidra, see `protos/common/opcodes.ksy` and `research/notes/ghidra-opcode-recovery.md`. **The opcode-to-payload dispatch mechanism is now found and fully mapped** (a 115-entry allocator jump table at `0x0038ec40`, keyed directly by opcode) — see `docs/protocol/net_event_dispatch_and_simple_opcodes.md` for the discovery and `research/notes/2026-08-14-gameplay-opcode-mapping.md` for the full per-opcode status ledger. 41 opcodes have fully confirmed, `ksc`-validated payload schemas so far (16 from the first pass's inline-constructed opcodes, 25 more from a 2026-08-15 pass that generalized the vtable-resolution technique to opcodes with a dedicated external constructor — see `docs/protocol/net_event_dispatch_and_simple_opcodes.md` section 5 and `research/notes/2026-08-15-gameplay-opcode-schema-expansion.md`); every other opcode has at least a known object size and (for ~57 of the remaining ones) a known constructor address ready for the next pass. **Live testing on the `NetMatchmaking*`/session-manager family below now reaches full 2-player gameplay** (2026-08-16/17): against a self-hosted stub (`tools/session_manager_stub.py`), a real client goes through auth, solo-host into an actual match, party invite + accept + join, cross-connection find-match pairing, and two real players loading into and playing a match together. See the "LIVE-CONFIRMED WORKING" banner in `docs/protocol/session_manager_and_matchmaking.md` and the `research/notes/2026-08-16-solo-host-fixed-live-confirmed.md` / `2026-08-16-two-player-party-and-match-working.md` / `2026-08-17-member-data-blob-rank-and-0x142-hostrank.md` notes. Open items: remote-player rank/gear render empty (served profiles are empty — rank/gear progression needs the `profiles/…`+`userdata/….txt.crypt` pipeline, under investigation), the party P2P link drops at game end, and an intermittent "Host quit for cheating" teardown. Earlier trail: the `research/notes/2026-08-14-*`/`2026-08-15-*` session notes. The `net_event_type` gameplay-event family immediately below (opcodes 0-114) remains primarily static-analysis-confirmed, consistent with the project's decided scope (auth/matchmaking/signaling backbone, not gameplay-simulation reimplementation).

Also known: a 38-entry catalog of lobby/match state names (`NET_SM_*`) pulled from the binary's string table, status unconfirmed either way (state-machine states vs. actual wire opcodes) — see `protos/pending/net_sm_states_catalog.md`.

**A fourth family, added 2026-08-15, is not reverse-engineered at all**: RPCN's own `CommandType`/`NotificationType` PSN protocol, read directly from this project's forked RPCN server source (`backend/rpcn/`) rather than decompiled — see the summary below and `docs/protocol/rpcn_psn_commands.md`.

## `net_event_type` gameplay-event family (opcodes 0-114)

See `docs/protocol/net_event_dispatch_and_simple_opcodes.md` for the dispatch mechanism, the confirmed BitStream field-level API, and the common per-event wire envelope (continuation bit + opcode byte + payload + optional recipient-list trailer — this also confirms `protos/common/packet_header.ksy`'s `opcode: u1` field at high confidence).

**Direction note (this whole family): peer-to-peer, not server-terminated.**
`research/notes/network-topology.md` confirms (direct string evidence in the
EBOOT: `[udpp2p] : recv from %s:%d`, `bind P2P to localhost:%d:%d`, the
`sceNpSignaling*` NAT-traversal API family, and `g_netGameManager.IsHost()`/
`g_matchSession.IsHost()` host-election gating) that **all** `NetEventType`
gameplay traffic is direct P2P UDP between game clients, relayed through
whichever peer currently holds "host" status — not routed through any server
this project operates or could operate. Per the project's decided scope
(auth/matchmaking/signaling backbone, not gameplay-simulation
reimplementation), a server→client/client→server column would misrepresent
this family, so no Direction column is given below; every confirmed `.ksy`
instead states `Direction: peer-to-peer (...)` in its own `doc:` block. This
was checked specifically for `sync_stats` (opcode 65/`0x41`) and
`sync_stats_player` (opcode 66/`0x42`) — both ordinary `NetEventType` values
dispatched through the same P2P-relayed mechanism as every other opcode in
this table, so mapping their external stats-manager-singleton payload (see
"Set aside this pass" in `net_event_dispatch_and_simple_opcodes.md`) is not a
server responsibility under current scope; see
`research/notes/2026-08-15-directionality-and-sync-stats-p2p.md` for the full
reasoning and the opcode-65-vs-`0x65` numbering correction.

| Opcode (hex) | Name | Status | Confidence | `.ksy` | Doc |
|---|---|---|---|---|---|
| 0x00 | `start_connection` | confirmed (empty payload) | high | `protos/0x00_start_connection.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x01 | `connection_done` | confirmed structurally; field semantics medium confidence | high (type) / medium (semantics) | `protos/0x01_connection_done.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x03 | `ready_to_start` | confirmed | high | `protos/0x03_ready_to_start.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x06 | `end_round` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x06_end_round.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x14 | `assign_team_done` | confirmed (empty payload) | high | `protos/0x14_assign_team_done.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x32 | `play_vox` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x32_play_vox.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x34 | `simple_snapshot_phys_fx` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x34_simple_snapshot_phys_fx.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x37 | `complete_task` | confirmed structurally; partial semantics | high | `protos/0x37_complete_task.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x38 | `start_net_task` | confirmed | high | `protos/0x38_start_net_task.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x3c | `coop_team_failed` | confirmed | medium-high | `protos/0x3c_coop_team_failed.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x3e | `spawn_entity` | confirmed | high | `protos/0x3e_spawn_entity.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x3f | `kill_entity` | confirmed | high | `protos/0x3f_kill_entity.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x40 | `animation_sync` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x40_animation_sync.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x4a | `deny_ownership_request` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x4a_deny_ownership_request.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x4b | `net_go` | confirmed (empty payload) | high | `protos/0x4b_net_go.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x55 | `debug` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x55_debug.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x09 | `kill_projectile_throwable` | confirmed | high | `protos/0x09_kill_projectile_throwable.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x0c | `grenade_start_fuse` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x0c_grenade_start_fuse.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x15 | `request_interact` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x15_request_interact.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x19 | `end_interact` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x19_end_interact.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x1b | `remove_interactable` | confirmed | high | `protos/0x1b_remove_interactable.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x1c | `set_interactable_ammo` | confirmed | high | `protos/0x1c_set_interactable_ammo.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x1e | `signal_respawn_player` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x1e_signal_respawn_player.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x20 | `secured_flag_score` | confirmed | high | `protos/0x20_secured_flag_score.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x22 | `stop_pack_or_deploy` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x22_stop_pack_or_deploy.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x23 | `spawn_carry_object` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x23_spawn_carry_object.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x27 | `npc_kill` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x27_npc_kill.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x2f | `revive` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x2f_revive.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x3d | `abort_interact` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x3d_abort_interact.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x4c | `swap_booster` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x4c_swap_booster.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x51 | `reset_melee_history` | confirmed structurally and semantically | high | `protos/0x51_reset_melee_history.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x53 | `melee_block` | confirmed | high | `protos/0x53_melee_block.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x5f | `npc_set_host` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x5f_npc_set_host.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x64 | `item_received` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x64_item_received.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x66 | `increment_score` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x66_increment_score.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x67 | `set_player_exposed` | confirmed | high | `protos/0x67_set_player_exposed.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x68 | `add_net_marker` | confirmed structurally; partial semantics | high (type) / medium (semantics) | `protos/0x68_add_net_marker.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x69 | `player_left` | confirmed | high | `protos/0x69_player_left.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x6b | `kill_all_mines` | confirmed (empty payload) | high | `protos/0x6b_kill_all_mines.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x6d | `sync_proxy_mine` | confirmed structurally; semantics unconfirmed | high (type) / low (semantics) | `protos/0x6d_sync_proxy_mine.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x6f | `set_weapon_upgrade_level` | confirmed | high | `protos/0x6f_set_weapon_upgrade_level.ksy` | net_event_dispatch_and_simple_opcodes.md |
| 0x00–0x72 (all 115) | *(remaining ~74 opcodes)* | not yet payload-confirmed; every opcode has a known object size, ~57 have a known constructor address not yet used | — | — | `research/notes/2026-08-14-gameplay-opcode-mapping.md` (full per-opcode ledger) + `research/notes/2026-08-15-gameplay-opcode-schema-expansion.md` (this pass's worklist) |

All 115 opcodes (confirmed and not-yet-confirmed alike) are peer-to-peer per the note above; `sync_stats`/`sync_stats_player` are not a wire-format exception to that.

## `ticket-server` control-channel family (separate opcode namespace)

Not part of the `net_event_type` gameplay-event table above - this is a
distinct raw-TCP control-channel protocol (port 7320) used during `NetInit`,
after RPCN issues the client's NP ticket, multiplexed by service-name string
rather than by `net_event_type`. See
`docs/protocol/0x11_ticket_server_hello.md` for full evidence.

**Every post-hello message on this whole family (ticket-server's C/D and
every sibling's post-hello payload below) is wrapped in a shared,
keyed encrypt-then-MAC frame - see "Encrypted frame layer" in
`0x11_ticket_server_hello.md`. The cipher itself is SOLVED: `tools/
ticket_cipher.py` decrypts a real captured message C, passes its own
auth_tag check, and recovers a genuine Sony NP ticket (contains
"UP9000-BCUS98174_00" and "comradesean" in plaintext) - confirmed
2026-08-14 via a live RPCS3 memory read of the static key plus ground-truth
Ghidra emulation to debug the Python reimplementation.**

| # | Name | Direction | Status | Confidence | `.ksy` |
|---|---|---|---|---|---|
| A | `ticket_server_hello` | client→server | confirmed | high | `protos/0x11_ticket_server_hello.ksy` |
| B | `ticket_server_hello_response` | server→client | confirmed structurally; session_token confirmed as live encrypted-frame key material (not inert) | high | `protos/0x11_ticket_server_hello_response.ksy` |
| C | `ticket_server_ticket_submit` | client→server | CONFIRMED WORKING - cipher decrypts real capture, recovers genuine NP ticket | high | `protos/0x11_ticket_server_ticket_submit.ksy` |
| D | `ticket_server_ticket_submit_response` | server→client | frame format/crypto confirmed working (real frame constructible via `tools/ticket_cipher.py`); content still unconfirmed (never captured) | high (framing/crypto) / unconfirmed (content) | `protos/0x11_ticket_server_ticket_submit_response.ksy` |

### Sibling `*-server` family (same opcode-0x11 hello, different service_name)

Four more services confirmed to share ticket-server's exact hello/hello_response
handshake (same function, `FUN_00acc424`); a fifth (`invite-server`) is
confirmed dead code in this build. See
`docs/protocol/0x11_sibling_servers_family.md` for the full survey,
per-service post-hello payload shapes, and evidence.

| Service | Hello/ack | Direction (hello / ack) | `.ksy` (hello / hello_response) |
|---|---|---|---|
| `heartbeat-server` | confirmed (shared function) | client→server / server→client | `protos/0x11_heartbeat_server_hello.ksy` / `_hello_response.ksy` |
| `leaderboard-server` | confirmed (shared function, 4 call sites) | client→server / server→client | `protos/0x11_leaderboard_server_hello.ksy` / `_hello_response.ksy` |
| `facebook-server` | confirmed (shared function, 2 call sites) | client→server / server→client | `protos/0x11_facebook_server_hello.ksy` / `_hello_response.ksy` |
| `single-player-server` | confirmed (shared function, 2 call sites) | client→server / server→client | `protos/0x11_single_player_server_hello.ksy` / `_hello_response.ksy` |
| `invite-server` | confirmed dead code - zero code xrefs across its entire `net-invite.cpp` literal pool (name, both command formats, `ASSERT` condition and filename) | — (dead code) | — |

## `NetMatchmaking*` family: Session Manager connection (separate opcode namespace again)

Also not part of `net_event_type`, and not part of the ticket-server `0x11`
family either - a **third**, independent raw-TCP protocol, opcodes `0x12d`-`0x148`
(301-328), opened by `g_pSessionManager::Init()` right after the ticket-server
handshake finishes. **This is the connection behind the
`g_pSessionManager->Init()() failed` / `recv() failed (errno=9)` failure that
was the live blocker going into this session** - root-caused and confirmed via
a live RPCS3 syscall-log capture: `Init()` opens a brand-new connection to the
same redirected host as ticket-server but **port 7314** (not 7320), the
connect silently fails (`s=-1` on every subsequent syscall), and `Init()`
never checks the connect's return value before blindly sending/receiving on
the dead connection. **Not dependent on ticket-server's message D content in
any way** - see `docs/protocol/session_manager_and_matchmaking.md` for the
full evidence trail and the concrete unblock (a stub listener on port 7314).

All 28 `NetMatchmaking*` opcodes have confirmed numeric IDs and wire sizes
(cross-checked three independent ways: static decompile, live TTY capture, and
the receive dispatcher's own switch-case literals). The cipher this family
uses to key its post-handshake traffic reuses the exact same static key as
ticket-server (see `docs/known-keys.md`), so `tools/ticket_cipher.py`'s already
-solved ARX implementation should carry over once the frame format is
confirmed.

| # | Name | Opcode | Direction | Size | `.ksy` |
|---|---|---|---|---|---|
| 0 | `NetMatchmakingClientHello` | 0x12d | client→server | 48 | `protos/netmatchmaking_client_hello.ksy` |
| 1 | `NetMatchmakingServerHello` | 0x12e | server→client | 16 | `protos/netmatchmaking_server_hello.ksy` |
| 2-27 | `NetMatchmakingRoomCreate` ... `NetMatchmakingClientHello2` | 0x12f-0x148 | mixed - 24 confirmed single-direction (11 server→client via the client's own receive-dispatch, 13 client→server via disassembled senders, including the 5 client-to-server-only opcodes below) + 2 confirmed bidirectional (`RoomLeave`/0x134, `RoomSearch`/0x136 - each has both a disassembled sender AND a receive-dispatch case; see each opcode's own `.ksy` `doc:` block and the full table below) | see doc | **All 26 have opcode ID + size confirmed AND a full field-level `.ksy`** as of 2026-08-15 - the 11 with a decompiled receive-handler, plus the 5 client-to-server-only opcodes (`RoomJoin`/0x130, `MemberSetData`/0x13c, `Promote`/0x13e, `SetRoomFlags`/0x142, `UpdatedRoomFlags`/0x143) found by extending the vtable dump and disassembling their senders at the instruction level, plus the rest from earlier live/decompile work. Remaining open work is depth, not coverage: several payloads have unconfirmed internal sub-field layouts (see doc) |

Full 28-entry table (now with a per-opcode Direction column), evidence, and
the live-capture root-cause trail: `docs/protocol/session_manager_and_matchmaking.md`.

**2026-08-16 audit — read the correction banner at the top of that doc before
using the table.** A full instruction-level pass over the receive-dispatch
(`FUN_00ad7604`) and every sender it pairs with produced five corrections and one
headline gap; full evidence in
`research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md`:

- The dispatch chain is **exactly 11 cases and exhaustive** (no jump table, no
  second dispatcher), and its **default branch returns without advancing the
  receive cursor** — so any opcode outside those 11 permanently wedges the
  SessionManager connection.
- The declared name/size table has **two phantom entries** (indices 22-23);
  everything from index 24 on is shifted by two, making **`0x143` =
  `SetRoomName`** and **`0x144` = `UpdatedRoomName`** (the payload is a
  NUL-terminated room-name string `strcpy`'d into `room_obj+0x18`, not a
  128-byte "host rank" table), and explaining the previously-unexplained
  `Ping`=`0x145` / `ClientHello2`=`0x146` corrections as the same single shift.
- `RoomCreate` (`0x12f`) has **no `create_id`** (offset 4 is uninitialised
  stack), its offset **8 is the client's own room-object pointer** (which
  retires the "room_ptr hazard" — no debugger needed any more), and
  **max_players lives at 0x24, not 0x1e**.
- `0x140`/`0x141` carry a **u16 at offset 4**, not a 4-byte bitmask; offset 6 is
  uninitialised stack, which fully explains the phantom "packed settings"
  bitmask.
- **`0x13f`/OwnerChanged is a real server→client message the stub has never
  sent**, and `RoomCreate`'s own sender clears the `room_obj+0x19f4` "I am the
  host" flag it is the only writer of — so a solo-hosting client currently never
  learns it is the host. Ranked first in that note's unsent-opcode list.

## RPCN/PSN `CommandType`/`NotificationType` family (fourth family, source-derived not decompiled)

Not reverse-engineered from `EBOOT.elf` like the other three - this is
Sony's own PSN client-server protocol, already fully defined in source in
this project's own forked RPCN server (`backend/rpcn/`, see `backend/README.md`).
Evidence source is direct source-code reading (`client.rs`, `notifications.rs`,
the `cmd_*.rs` handlers), which per `CONVENTIONS.md`'s confidence discipline
is a *stronger* basis than decompilation for the protocol shape itself - what
remains genuinely uncertain is only which parts of this generic PSN surface
Factions' EBOOT actually exercises, which leans on the existing NID-import
evidence in `research/notes/clan-tus-commerce-findings.md`.

**Direction is enforced by the wire framing itself, not just convention**:
every packet shares a 15-byte header whose first byte is a `PacketType`
(`Request`/`Reply`/`Notification`/`ServerInfo`); the server's own read loop
disconnects any client that sends anything but `Request`. So `CommandType`
(carried in `Request` packets) is strictly client→server, and
`NotificationType` (carried in `Notification` packets) is strictly
server→client - confirmed structurally, not inferred. The one nuance:
several `CommandType` handlers push `NotificationType` messages to *other*
clients as a side effect of a single request (e.g. `JoinRoom` → `UserJoinedRoom`
pushed to existing room members) - this doesn't break either enum's own
direction, but means one client's request can fan out server-initiated
pushes to third parties, not just a reply to the sender. See
`docs/protocol/rpcn_psn_commands.md` for the full per-handler table.

**Important disambiguation**: RPCN's own room system (`CreateRoom`/`JoinRoom`/etc.
below) is Sony's standard `sceNpMatching2` API - confirmed used by Factions
(its `sceNp2` import is 100% `sceNpMatching2`, 29/29 functions) - and is a
**completely separate layer** from the already-documented `NetMatchmaking*`
family above (raw custom TCP on port 7314, confirmed absent from RPCN by a
repo-wide grep, confirmed not routed through `sceNpMatching2`/`sceNpSignaling`
either). Don't conflate "RPCN's rooms" with "`NetMatchmaking*`" - see
`docs/protocol/rpcn_psn_commands.md`'s dedicated section for how the two
relate at runtime.

| Group | Commands (`CommandType`) | Direction | Generic PSN or Factions-specific |
|---|---|---|---|
| Account (`cmd_account.rs`) | `Login`, `Terminate`, `Create`, `Delete`, `SendToken`, `SendResetToken`, `ResetPassword` | client→server | generic (RPCN's own account system, not a Sony API) - used by every Factions session |
| Session/presence/tickets/signaling (`cmd_session.rs`/`cmd_misc.rs`/`cmd_server.rs`) | `ResetState`, `SetUserInfo`, `GetServerList`, `GetWorldList`, `RequestSignalingInfos`, `RequestTicket`, `SendMessage`, `GetNetworkTime`, `SetPresence` | client→server (some trigger server→client `NotificationType` pushes as a side effect - see doc) | generic `sceNpManager`/`sceNpBasic`/`sceNpSignaling` — `RequestSignalingInfos` and `RequestTicket` are confirmed load-bearing for Factions (P2P rendezvous for the `net_event_type` link, and the literal source of the ticket `0x11_ticket_server_ticket_submit.ksy` submits) |
| Friends (`cmd_friend.rs`) | `AddFriend`, `RemoveFriend`, `AddBlock`, `RemoveBlock` | client→server | generic `sceNpBasic`; `AddBlock`/`RemoveBlock` are TODO no-op stubs in this RPCN version |
| Rooms — `sceNpMatching2` (`cmd_room.rs`) | `CreateRoom`, `JoinRoom`, `LeaveRoom`, `SearchRoom`, `GetRoomDataExternalList`, `GetRoomMemberDataExternalList`, `SetRoomDataExternal`, `GetRoomDataInternal`, `SetRoomDataInternal`, `GetRoomMemberDataInternal`, `SetRoomMemberDataInternal`, `PingRoomOwner`, `SendRoomMessage` | client→server | generic `sceNpMatching2`, but **confirmed used by Factions** (100% of its `sceNp2` import) - see disambiguation above |
| Rooms — old GUI API (`cmd_room_gui.rs`) | `CreateRoomGUI`, `JoinRoomGUI`, `LeaveRoomGUI`, `GetRoomListGUI`, `SetRoomSearchFlagGUI`, `GetRoomSearchFlagGUI`, `SetRoomInfoGUI`, `GetRoomInfoGUI`, `QuickMatchGUI`, `SearchJoinRoomGUI`, `GetRoomMemberDataExternalList` | client→server | generic legacy `sceNpMatching` (v1); likely NOT used by Factions (medium confidence - no `sceNpMatching` v1 import found in the EBOOT's resolved NID table) |
| Scoreboards (`cmd_score.rs`) | `GetBoardInfos`, `RecordScore`, `RecordScoreData`, `GetScoreData`, `GetScoreRange`, `GetScoreFriends`, `GetScoreNpid` | client→server | generic `sceNpScore`; likely barely/not used by Factions (medium confidence - only `sceNpScoreInit` is imported, no Record/Get functions) - Factions' real leaderboard mechanism is almost certainly the separate, already-documented `leaderboard-server` (`0x11` sibling family) instead |
| TUS (`cmd_tus.rs`) | `TusSetMultiSlotVariable`, `TusGetMultiSlotVariable`, `TusGetMultiUserVariable`, `TusGetFriendsVariable`, `TusAddAndGetVariable`, `TusTryAndSetVariable`, `TusDeleteMultiSlotVariable`, `TusSetData`, `TusGetData`, `TusGetMultiSlotDataStatus`, `TusGetMultiUserDataStatus`, `TusGetFriendsDataStatus`, `TusDeleteMultiSlotData` | client→server | generic `sceNpTus`; **confirmed NOT used by Factions** (high confidence - zero `sceNpTus*` imports anywhere in the EBOOT, per `research/notes/clan-tus-commerce-findings.md`) - RPCN's single largest command family, and irrelevant to this project |
| Admin (`cmd_admin.rs`) | `UpdateDomainBans`, `TerminateServer`, `UpdateServersCfg`, `BanUser`, `DelUser` | client→server (admin-only) | N/A - server-operator tooling, not a game-client API at all |

`NotificationType` (all server→client): `UserJoinedRoom`, `UserLeftRoom`,
`RoomDestroyed`, `UpdatedRoomDataInternal`, `UpdatedRoomMemberDataInternal`
(room-state, paired with `cmd_room.rs`); `FriendQuery`, `FriendNew`,
`FriendLost`, `FriendStatus`, `FriendPresenceChanged` (friends/presence);
`RoomMessageReceived`, `MessageReceived` (messaging); `SignalingHelper`
(P2P-rendezvous push, load-bearing for Factions); `MemberJoinedRoomGUI`,
`MemberLeftRoomGUI`, `RoomDisappearedGUI`, `RoomOwnerChangedGUI`,
`QuickMatchCompleteGUI`, `_UserKickedGUI` (unused/dead - never constructed
anywhere in the fork) - all paired with the likely-unused GUI room family.

Full command-by-command detail, the notification side-effect table, and the
`NetMatchmaking*` relationship writeup: `docs/protocol/rpcn_psn_commands.md`.
