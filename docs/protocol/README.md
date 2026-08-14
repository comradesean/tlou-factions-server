# Protocol Documentation Index

**Numeric opcode IDs are confirmed** for 115 `NetEventType` values (0-114) — recovered directly from an in-memory enum-to-name table via Ghidra, see `protos/common/opcodes.ksy` and `research/notes/ghidra-opcode-recovery.md`. **The opcode-to-payload dispatch mechanism is now found and fully mapped** (a 115-entry allocator jump table at `0x0038ec40`, keyed directly by opcode) — see `docs/protocol/net_event_dispatch_and_simple_opcodes.md` for the discovery and `research/notes/2026-08-14-gameplay-opcode-mapping.md` for the full per-opcode status ledger. 16 opcodes have fully confirmed, `ksc`-validated payload schemas so far; every other opcode has at least a known object size and (for ~82 of them) a known constructor address ready for the next pass. The project is still in the static-analysis-only phase; no live capture has happened.

Also known: a 38-entry catalog of lobby/match state names (`NET_SM_*`) pulled from the binary's string table, status unconfirmed either way (state-machine states vs. actual wire opcodes) — see `protos/pending/net_sm_states_catalog.md`.

## `net_event_type` gameplay-event family (opcodes 0-114)

See `docs/protocol/net_event_dispatch_and_simple_opcodes.md` for the dispatch mechanism, the confirmed BitStream field-level API, and the common per-event wire envelope (continuation bit + opcode byte + payload + optional recipient-list trailer — this also confirms `protos/common/packet_header.ksy`'s `opcode: u1` field at high confidence).

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
| 0x00–0x72 (all 115) | *(remaining ~99 opcodes)* | not yet payload-confirmed; every opcode has a known object size, ~82 have a known constructor address | — | — | `research/notes/2026-08-14-gameplay-opcode-mapping.md` (full per-opcode ledger) |

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

| # | Name | Status | Confidence | `.ksy` |
|---|---|---|---|---|
| A | `ticket_server_hello` | confirmed | high | `protos/0x11_ticket_server_hello.ksy` |
| B | `ticket_server_hello_response` | confirmed structurally; session_token confirmed as live encrypted-frame key material (not inert) | high | `protos/0x11_ticket_server_hello_response.ksy` |
| C | `ticket_server_ticket_submit` | CONFIRMED WORKING - cipher decrypts real capture, recovers genuine NP ticket | high | `protos/0x11_ticket_server_ticket_submit.ksy` |
| D | `ticket_server_ticket_submit_response` | frame format/crypto confirmed working (real frame constructible via `tools/ticket_cipher.py`); content still unconfirmed (never captured) | high (framing/crypto) / unconfirmed (content) | `protos/0x11_ticket_server_ticket_submit_response.ksy` |

### Sibling `*-server` family (same opcode-0x11 hello, different service_name)

Four more services confirmed to share ticket-server's exact hello/hello_response
handshake (same function, `FUN_00acc424`); a fifth (`invite-server`) has no
live code call site in this build. See
`docs/protocol/0x11_sibling_servers_family.md` for the full survey,
per-service post-hello payload shapes, and evidence.

| Service | Hello/ack | `.ksy` (hello / hello_response) |
|---|---|---|
| `heartbeat-server` | confirmed (shared function) | `protos/0x11_heartbeat_server_hello.ksy` / `_hello_response.ksy` |
| `leaderboard-server` | confirmed (shared function, 4 call sites) | `protos/0x11_leaderboard_server_hello.ksy` / `_hello_response.ksy` |
| `facebook-server` | confirmed (shared function, 2 call sites) | `protos/0x11_facebook_server_hello.ksy` / `_hello_response.ksy` |
| `single-player-server` | confirmed (shared function, 2 call sites) | `protos/0x11_single_player_server_hello.ksy` / `_hello_response.ksy` |
| `invite-server` | no live call site found - likely dead/unused in this build | — |

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

| # | Name | Opcode | Size | `.ksy` |
|---|---|---|---|---|
| 0 | `NetMatchmakingClientHello` | 0x12d | 48 | `protos/netmatchmaking_client_hello.ksy` |
| 1 | `NetMatchmakingServerHello` | 0x12e | 16 | `protos/netmatchmaking_server_hello.ksy` |
| 2-27 | `NetMatchmakingRoomCreate` ... `NetMatchmakingClientHello2` | 0x12f-0x148 | see doc | opcode ID + size confirmed, full field-level `.ksy` not yet written (11 of 26 already have their receive-handler decompiled - see doc) |

Full 28-entry table, evidence, and the live-capture root-cause trail:
`docs/protocol/session_manager_and_matchmaking.md`.
