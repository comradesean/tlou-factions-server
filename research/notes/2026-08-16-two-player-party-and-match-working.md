# Two-player party invites, party join, and real matches WORK — live-confirmed

**Status: confirmed live, 2026-08-16, same testing marathon as the solo-host run (assert extract: `research/logs/2026-08-16-marathon-tty-asserts.txt`)
fix** (`2026-08-16-solo-host-fixed-live-confirmed.md`). Two real machines,
`comradesean` (host) + `mgnomad2` (joiner), repeatedly:

- Party invite delivered AND visible in the Invites screen (sent as
  `main_type 3` via RPCN; the earlier delivery-chain analysis is in
  `2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md`).
- Accepting the invite joins the party: the joiner's client sends **`0x130`
  RoomJoin** (88 bytes — first live captures of it in this pass: offset 8 = the
  joiner's OWN party-room object pointer, offset 0x10:0x18 = target room_id
  learned from the invite's tag-267 NP-bus payload). The stub pairs it with
  the host's registered room and pushes per-recipient rosters both ways.
- The party then starts a real match: host RoomCreates the GAME room
  (object A) and the joiner's client sends a SECOND `0x130` for the game
  room — the same handler covers it. Both clients load in and play.
- Joiner leaving no longer breaks the host — live-confirmed fixed by
  `0x134` RoomLeave + refresher-roster shrink (commit `e3084e6`). Before
  that fix the host got "You were kicked from the game/party" **spammed at
  exactly the 10s Member-refresher cadence** (the stale joint roster
  re-registered the departed member every interval).
- Host leaving ends the party/match for both, cleanly (expected behavior).

## The two room objects, resolved

Every client has TWO statically-allocated room objects (the two globals
found in `2026-08-16-party-invite-sender-assert-corrected.md`):
`0x1383bd8` = the GAME room, `0x1387f58` = the PARTY room. RoomCreate /
0x135 / 0x130 all carry the relevant object's address at wire offset 8,
which is why parsing it per-message (instead of the old hardcode) was
load-bearing: party flows create rooms on object B, and the old hardcode
would have written every Member into object A.

## Working server behavior (tools/session_manager_stub.py, commits
`776bd51` → `4a2f925` → `b903f82` → `5fe13d9` → `e3084e6`)

- RoomCreate reply: `Member + OwnerChanged(1) + OwnerMember(1)`, NO
  RoomJoined, self npid populated, room_ptr/max_players parsed from wire.
- 0x130 RoomJoin: joiner gets `Member(self-first) + OwnerChanged(0) +
  OwnerMember(1)`; host connection gets updated roster + OwnerMember(1);
  both refreshers restart with the joint roster; cross-connection
  `active_rooms` registry with per-room member_id->connection map.
- 0x135 find-match: same shape per recipient (host OwnerChanged(1), joiner
  (0)); ghost third lobby slot (RoomJoined's phantom) live-confirmed GONE.
- 0x13a SetPartyData relayed to all room members as 0x13b (live-confirmed
  firing in party + pregame flows; find-match lobbies do NOT emit 0x13a).
- 0x133 abandon / socket close: 0x134 RoomLeave to remaining members,
  roster shrink.

## Open items after this pass

1. **Remote player's rank never renders** (either client). Find-match
   lobbies emit no 0x13a, so the 0x13b relay can't be the (only) carrier;
   prime suspect is the ignored client->server `0x142` (18 bytes,
   `00 01 00 60 | room_id | 0002` — shaped like "request member 2's data",
   presumably answered from server-side stat storage on Sony's real
   servers). A dedicated Ghidra/objdump trace is in flight as of this
   note: trace 0x142's sender + the rank UI's data source.
2. **Remote player's gear/customization randomized.** Possibly the same
   per-member data channel; the same trace covers it. Next live experiment:
   change gear locally and see whether even the local client honors it
   (splits save/profile bug vs transmission bug).
3. **"Host quit for cheating"** killed the very first 2-player match ~3.5s
   after NET_SM_UPDATE (after 'Host Migrate Room', which by itself is
   normal match-start behavior - it appeared in surviving matches too).
   Never recurred across subsequent matches, including before the
   0x13d/0x13b changes were live - so it is intermittent and unexplained,
   not fixed-and-verified. Watch for it.
4. One host-side RPCS3 crash during testing (suspected emulator bug, not
   reproduced).
5. `0x13e` (16 bytes, 4 varying bytes at +4 + room_id) still unhandled and
   unexplained - clients send it periodically in lobbies, no visible harm.
