# Join Party collapse: root cause found & fixed — Kick/Promote wired up, opcode tail corrected

**Status: confirmed live, 2026-08-17.** Friends-list Join Party, Invite-to-Party,
Kick, and Promote all work, repeatedly, against two real RPCS3 machines. This
closes the "Join Party: UNRELIABLE, OPEN — QUARANTINED" item carried forward
from the prior work-state note (`2026-08-17-session-handoff.md`) and
its archived investigation (`research/joinparty/`) — this pass did NOT read
that archive first (per its own README instruction), reached the answer
independently via live PPU breakpoints, and only cross-checked afterward.

Companion docs: `docs/protocol/session_manager_and_matchmaking.md` (maintained
in a parallel pass; carries the renamed `.ksy` files and full opcode
table) and the renamed protos themselves
(`protos/0x137_kickout.ksy`, `0x138_kickedout.ksy`, `0x139_room_closed.ksy`,
`0x13e_set_host_flag.ksy`, `0x13f_host_flag_updated.ksy`,
`0x142_room_u16_list_upload.ksy`, `0x143_set_room_data_block.ksy`,
`0x144_room_data_block_updated.ksy`). This note is the narrative/evidence
trail; opcode field-level detail lives in those files.

## The collapse, root-caused

Every friends-list Join Party attempt worked for a fraction of a second, then
the host's party silently dissolved — the pattern that produced the
"UNRELIABLE" verdict and the quarantine. The actual mechanism:

`tools/session_manager_stub.py` was replying to the client's `0x137` with
`0x138`. **`0x138` is `Kickedout`**, a server→client message with real
teardown semantics on the receiving client, not a generic ack:

- Client dispatcher `@0x00ad7f28` matches the packet's `room_id`@wire+8
  against the client's own local room.
- On a match it calls `RequestLeave` -> sets `m_leaveRequested`@`room+0x1a48`.
- The party state machine's state 6 (`@0x3cad3c`) observes the flag and calls
  `LeaveRoom` (`@0x3caf94`), which calls `sceNpSignalingTerminateConnection`.
- The host's own log shows `SCE_NP_SIGNALING_ERROR_TERMINATED_BY_MYSELF`
  (`0x8002a818`); the joiner sees `TERMINATED_BY_PEER` (`0x8002a810`).

So the backend was telling the host "you have been kicked from your own
party" roughly 15ms after every successful join — self-inflicted, server-side,
and entirely explaining both the "unreliable" symptom and the P2P-signaling
framing the quarantined investigation had converged on (the signaling
termination is real, but it is a downstream *effect* of the bad `0x138` reply,
not an independent P2P/NAT problem).

**Proven, not inferred**, via RPCS3 PPU breakpoints: a breakpoint at
`0x3cb174` (inside `RequestLeave`) fired with `r3` = the session object
(`0x1387f58`, the fixed global party-room object — see
`2026-08-16-two-player-party-and-match-working.md`) and `LR` = `0xad7fb0`,
which is inside the `0x138` dispatch arm at `0x00ad7f28`. That is a direct,
live capture of the exact instruction path from "stub sends `0x138`" to
"client tears its own party down."

**Fix:** stop sending `0x138` as a generic reply to `0x137`. `0x137` is not a
reply-needing handshake opcode at all — see below for what it actually is.

## Corrected opcode tail (0x137-0x144)

The earlier opcode-naming-shift pass (`2026-08-17-opcode-naming-shift-
resolved.md`) got the general +2 index-shift insight right but mislabeled
several of the tail entries as a "room search info/result" family. Live
Kick/Promote testing settled the real names:

| Opcode | Name | Direction | Payload / notes |
|---|---|---|---|
| `0x137` | `Kickout` | client→server | `{target@4, requester@6, room_id@8}` |
| `0x138` | `Kickedout` | server→client | see collapse mechanism above |
| `0x139` | `RoomClosed` / forced teardown | server→client | not "kickout" |
| `0x13c` | `Promote` | client→server | `{new_owner@4, room_id@8}` |
| `0x13d` | `OwnerMemberChanged` | server→client | writes `room+0x19f0` |
| `0x13e` | `SetHostFlag` | client→server | constant kind byte `3`@offset 5 |
| `0x13f` | `HostFlagUpdated` | server→client | writes `room+0x19f4` |
| `0x140`/`0x141` | `SetRoomAttr`/`RoomAttrUpdated` | client→server / server→client | writes `room+0x1f0`; meaning still UNKNOWN |
| `0x142` | `RoomU16ListUpload` | client→server | `16 + 2*count` bytes; NOT "host_rank"; purpose UNKNOWN |
| `0x143` | `SetRoomDataBlock` | client→server | 128-byte block <-> `room+0x18`; NOT a room "name" |
| `0x144` | `RoomDataBlockUpdated` | server→client | broadcasts the same 128-byte block |

Every opcode above is cleanly either received (a dispatcher arm in the
client's receive-dispatch) or sent (a client-side `li`-opcode builder) — never
both. That symmetry is itself a sanity check: nothing in this tail is genuinely
bidirectional the way `RoomLeave`/`0x134` and `RoomSearch`/`0x136` are.

## Kick and Promote, wired up and working

**Kick.** On receiving `0x137`, the stub routes `0x138` Kickedout to the
**target** member's connection only — never to the sender — and broadcasts
`0x134` MemberLeft to the rest of the room.

**GOTCHA, and the reason the collapse fix alone wasn't sufficient:** the
friends-list Join flow itself auto-emits a client-generated `0x137` right
after `RoomJoin`, with `requester`@+6 `= 0` and `target`@+4 `=` the joiner's
own id. If the stub treats every `0x137` as a real kick request, this
self-emitted packet kicks the joiner who just joined. **Fix: gate on
`requester != 0`** — a requester of 0 is the client's own post-join
housekeeping, not a player-initiated kick.

**Promote.** On receiving `0x13c`, the stub broadcasts `0x13d`
OwnerMemberChanged + `0x13f` HostFlagUpdated to the room.

Both are now live-confirmed working repeatedly.

## Unique party room id (supporting fix, not the collapse cause)

The party room object is the fixed global `0x01387f58` on **every** console
(confirmed in `2026-08-16-two-player-party-and-match-working.md`), so a stub
that used one shared static room id made cross-connection `RoomJoin` lookups
ambiguous once more than one party existed. The stub now mints a unique room
id per party create (high word `0x60000000`), which propagates to the joiner
two ways: via the client's own NP-268 reply (read from `room_obj+0x10`) and
via presence (`sceNpBasicSetPresenceDetails` re-reads `room_obj+0x10` every
tick). This was necessary for multi-party correctness but is a **separate,
supporting fix** — it was live-tested independently and did NOT by itself
explain or fix the ~15ms collapse; the `0x138` misuse did.

## Status summary

- **Working, live-confirmed, repeatedly:** friends-list Join Party,
  Invite-to-Party, Promote, Kick.
- Invite-to-Party uses the exact same RoomCreate/RoomJoin protocol as
  friends-list Join — confirmed NOT a separate PSN-only path.
- **View Profile** and **Mute** produce zero session-manager wire traffic —
  Profile is either served by a different backend entirely or a client no-op
  under RPCS3; Mute is client-local. Neither is a session-manager gap.

## Control model (worth stating plainly)

The retail client is a fixed black box. It autonomously **sends** messages we
cannot prevent or alter — we only control how the server reacts. It only
misbehaves when it **reacts** to a message the server sent. Every fix in this
note, and realistically every fix available to this project at all, is
server-side in that sense: don't send the message that makes the client do
the wrong thing (`0x138` as a blind `0x137` reply); do send the one that makes
it do the right thing (`0x138` routed only to the real kick target, `0x13d`/
`0x13f` on promote). There is no client patch, no P2P/NAT workaround, and no
signaling-layer fix required here — the signaling termination the quarantined
investigation observed was real, but it was the client correctly obeying a
server message we should never have sent.
