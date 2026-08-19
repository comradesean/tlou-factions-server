# Join-in-progress (JIP) — RESOLVED

Goal: a 3rd client joining an already-playing match (JIP / late-join).
Status: **WORKING** (live-confirmed 2026-08-18). Two fixes were required.

## Fix 1 — N-member roster (`server/session_manager.py`, 0x130 RoomJoin handler)

The stub used a fixed `JOINER_MEMBER_ID=2` for every joiner, so a 3rd
participant collided with the 2nd, overwrote it, and tore the session down (root
cause: `2026-08-18-jip-roster-collision.md`). Fixed with a monotonic per-room
`next_member_id` (host=1, joiners 2,3,4…), an N-slot roster sent to every member,
per-member `room_ptr` (`room_ptrs` map), and a notification to every existing
member when a newcomer arrives. The 2-member path is unchanged.

This removed the fatal collision but did NOT fix JIP on its own: joins into a
LOBBY host stuck, joins into a MID-MATCH host still bounced, and the `0x131`
roster bytes were identical between the two cases.

## Fix 2 — stop re-firing OwnerMemberChanged into an established room

**This is what made mid-match joining work.** On every join the stub sent
`0x13d OwnerMemberChanged` to each existing member (including the host) alongside
the roster. The owner does not change on a join, but `0x13d`'s handler writes
`room_obj+0x19f0` and calls `room->vtable[0x34]`, the ownership-notification
callback — the source of the host TTY line `"New host : <owner>"` that printed on
every bounced attempt, ~1.5 s apart, matching the joiner's retry loop.

Re-announcing host ownership into a running match tore the join down: the joiner
was admitted, then self-left with `0x133 RoomLeaving` in ~100–200 ms and retried
at ~1 Hz, with member ids climbing until the host's RPCS3 died with
`VK_ERROR_DEVICE_LOST` from the member churn.

The fix is one line in the existing-member push loop of the 0x130 handler: send
the roster alone.

```python
mconn.sendall(m)          # was: m + build_owner_member(target_room_id, MEMBER_ID)
```

The joiner still receives `0x131 Member` + `0x13f OwnerChanged(is_owner=0)` +
`0x13d OwnerMemberChanged(owner=1)` — for a newcomer that is the FIRST owner
announcement, not a re-announcement, and it is required for the joiner to know
who the host is.

This is the same bug class as the Join Party fix (the stub replying to `0x137`
with `0x138 Kickedout`, self-kicking the host): the stub emits a control opcode
the client acts on as disruptive while the stub treats it as an ack. The general
rule that falls out of both: **never re-assert ownership/membership state into a
room that is already established** — see also `start_member_refresher`, which
skips periodic roster refresh for any room with more than one member for exactly
the same reason (party churn / "kicked from the party" spam).

## Tooling

- **Wire tap:** `server/session_manager.py` mirrors every packet to
  `server/logs/wire.jsonl` (JSON per event). `research/tools/verify_wire.py`
  parses it against the ksy (coverage / unknown opcodes / padding / checksum).
- **Client diagnostics:** the game prints to `sys_tty_write` in the RPCS3 log
  (`/mnt/f/rpcs3_testing/*/log/RPCS3.log`, multi-GB, `grep -a`). It rotates on
  each RPCS3 relaunch, so grab it before restarting a crashed VM.
- The session manager must be RESTARTED after any `session_manager.py` edit; a
  restart resets the tap's conn-id counter (low conn ids = fresh restart).
  **TREAT A RESTART AS DESTRUCTIVE.** The client never reconnects to port 7314
  (proven: research/notes/2026-08-18-session-manager-connect-and-reconnect.md),
  so every connected client is stranded until it re-enters the Multiplayer menu
  by hand - and it will look healthy while disconnected, since the socket death
  is silent client-side. Batch edits and restart BETWEEN test sessions. A
  SIGTERM/SIGINT now drains rooms first (0x134+0x139) so clients at least tear
  down cleanly; a crash or hard kill still strands them.

## Unrelated cleanup

The in-game timeout-disable patches (`client/patches/ingame_timeouts_patch.yml`
and `docs/ingame-timeout-patches.md`) were REMOVED 2026-08-19: static-only,
never validated, and they crashed the game. JIP was solved without them. The
located timeout branches survive in git history at 23db204..de9db95 if those
addresses are ever wanted.
