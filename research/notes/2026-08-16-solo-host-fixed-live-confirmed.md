# Solo-host Custom Game WORKS — live-confirmed, first attempt, no asserts

**Status: confirmed live, 2026-08-16.** A solo-hosted Custom Game reached
`NET_SM_UPDATE` (in-match steady state) on the FIRST attempt after a stub
restart, with zero assertion lines in the RPCS3 log for the whole run. The
host played in the match. Every historical failure mode of this path was
absent in one attempt:

- No "Starting Game..." permanent stall (`NET_SM_SERVER_LOBBY` cleared in
  **33 ms** — it was previously a no-timeout permanent stall on 3rd+
  attempts and an intermittent first-attempt failure).
- No 10-15s post-load boot (`net-game-manager.cpp:1358` `team >= 0` assert —
  1090 occurrences across the prior marathon log (`research/logs/2026-08-16-marathon-tty-asserts.txt`), zero this run).
- No first-attempt "Lobby Server Error" id-gate race.
- Local player has a real identity: TTY logs `comradesean joined match`
  (previously `' joined match'` with an empty name, and
  `Removing User '' failed!!!!!!` on teardown).

## The state trace (game TTY, one attempt, uninterrupted)

```
NET_SM_READY_UP -> NET_SM_CREATE_GAME_WAIT
comradesean joined match
NET_SM_CLIENT_WAIT_FOR_PARTY_CONNECT_GAME_HOST
NET_SM_SETUP_TEAMS -> NET_SM_SERVER_LOBBY (0.03s) -> NET_SM_CUSTOM_GAME_HOST_WAIT_INFO
NET_SM_READY_UP -> PRE_LOAD_SCREEN -> LOAD_SCREEN -> LOAD_SCREEN_2 -> LOAD_SCREEN_3
NET_SM_UPDATE            <- in match
```

Server reply on the wire (stub log): `Member+OwnerChanged as one write, NO
RoomJoined (264+16 bytes, room_ptr=0x1383bd8 (parsed from wire offset 8),
max_players=8 (parsed from wire offset 0x24), self npid populated)`.

## What fixed it — the four-part stack (commits `776bd51` + `4a2f925`)

All four derive from `2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md`
(the objdump/Ghidra dispatch audit). Tested in two steps:

**Step 1 (`776bd51`) alone was NOT sufficient** — a live test with only these
still hit the team assert and booted to menu (~15s post-load), though it did
reach map load on the 2nd attempt:

1. `0x13f` OwnerChanged sent after Member (RoomCreate's own sender clears the
   client's I-am-the-host flag at `room_obj+0x19f4`; `0x13f`'s handler is the
   only inbound writer).
2. `room_ptr` parsed from RoomCreate wire offset 8 (the client's own room
   object address) instead of the hardcoded debugger-recovered `ROOM_PTR`.
3. `max_players` parsed from wire offset 0x24 (real field, live-constant 8)
   instead of the never-written 0x1e.

**Step 2 (`4a2f925`) completed the fix** — the step-1 failure run's TTY showed
`Removing User '' failed!!!!!!`, pinning the blank-identity mechanism:

4. RoomJoined DROPPED from the solo-host reply, and the self entry's real
   NpId restored in Member (`populate_self_npid=True`). These are mutually
   dependent halves: the self-npid zeroing (2026-08-15's anti-`OWN_NP_ID`
   hack) only existed because RoomJoined's registration (is_local hardcoded
   0) opened NP signaling to self — but that registration ALSO created a
   phantom 2nd member, and the zeroed NpId left the LOCAL member nameless,
   which starved the find-player-by-npid lookup that feeds team assignment
   (the direct cause of the 1358 assert). Removing RoomJoined removes the
   self-signaling source, which makes restoring the real NpId safe, which
   gives the local member an identity, which lets team assignment succeed.
   Member's handler carries the real room-create-completed latch (`0xad79ec`)
   so RoomJoined is not needed for create confirmation, and Member has no
   id-gate, which also explains the first-attempt reliability.

## Causal notes

- The `NET_SM_SERVER_LOBBY` stall resolving is consistent with the audit's
  observation that `_opd_FUN_003ca9d0`'s state machine gates on the host
  flag — but the queue-producer mechanism was never traced, so "OwnerChanged
  fixed the stall" is inference from one clean run, not a proven mechanism.
- One attempt = strong signal, not statistics. The historical failure modes
  were intermittent (first attempt sometimes worked before). Repeat runs —
  especially back-to-back host attempts on ONE connection (the old 3rd-attempt
  stall) — are the next validation target.

## What this does NOT cover yet

- **Find-match (2-player) path unchanged** — still sends RoomJoined +
  zeroed self npids, so it presumably still has the phantom-member and
  blank-identity defects. Needs the same treatment: per-recipient
  Member+OwnerChanged(is_owner for host only), no RoomJoined — but note
  find-match has NO RoomCreate to parse each client's room_ptr from
  (`0x136` RoomSearch was audited as not carrying it — see the audit note
  §8.5). Finding each joiner's room pointer source is the open problem.
- **Party invites** — the invite bus itself works end-to-end (see
  `2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md`); its
  `m_roomSize > 0` assert was caused by an unpopulated room object, which
  this fix plausibly repairs for the HOST side. Receiver side untested.
- Checkpoint's empty-skybox symptom — unrelated, still unexplained.
