# Join-in-progress fails: the stub's fixed 2-member roster collides on a 3rd member

A third client attempting to join an already-formed 2-player matchmade room does
not just fail to join — it tears the whole session down: the joiner bounces in
~130 ms, the host is booted out of online play, and the earlier joiner is left
hung in-game. Root cause is a server-side (stub) roster bug, confirmed from both
the wire capture and the stub source.

## Root cause

`server/session_manager.py` models a room as exactly **two fixed slots**:

```
MEMBER_ID        = 1   # the host
JOINER_MEMBER_ID = 2   # every joiner  (line 490)
...
joiner_entry = (JOINER_MEMBER_ID, own_npid)   # line 1364
```

Every joiner is assigned `member_id = 2`. There is no unique-id allocation and no
growing roster. When a second joiner arrives it reuses slot 2 and **overwrites**
the first joiner instead of being added as a third member. The roster count never
exceeds 2, and the first joiner is silently dropped from every member's roster.

## Wire evidence

Captured `0x131` Member messages (`server/logs/wire.jsonl`), room
`5000000901383bd8`, host = c23:

| Event | Member roster sent | owner_ref | local_ref | count |
|---|---|---|---|---|
| c1 joins (join **holds**, ~2 min stable) | `[c1, host]` | 1 | 2 | 2 |
| c24 joins (JIP, **fatal**) — sent to c24 | `[c24, host]` | 1 | 2 | 2 |
| same moment — sent to host c23 | `[host, c24]` | 1 | 1 | 2 |

The header is identical between the good and fatal joins (`owner_ref=1`,
`local_ref=2`, `count=2`). The only change is roster **content**: c24's join
produces a roster of `[host, c24]` everywhere — c1 (the existing member) is
**absent**. The stub gave c24 the same slot (member 2) it had given c1, so:

- c24 receives a valid-looking 2-member roster and briefly accepts it;
- the host's roster is rewritten to `[host, c24]`, evicting c1;
- c1 is orphaned — it still believes it is in the room, but no other member lists
  it, and it is never told about c24.

The corrupt/contradictory room state then triggers the teardown cascade
(`0x134 RoomLeave` fanned out, host self-leaves, session dropped). The 130 ms
bounce is a client-side reaction to the received roster, not a P2P timeout (which
would take seconds), placing this in the same self-inflicted-teardown class as
the earlier party-collapse bug.

Confirmed not-a-timeout: the in-game timeout thresholds are all ≥ 5 s (see
the in-game timeout branches, since removed - see git history at 23db204..de9db95); a 130 ms leave cannot be any of them.

## What a correct 3rd-member join requires

The two-slot model must become an N-slot roster:

1. **Allocate a unique `member_id` per participant** (3, 4, … after the host's 1
   and the first joiner's 2) instead of the fixed `JOINER_MEMBER_ID`.
2. **Grow the roster:** the `0x131` Member sent on a join must contain *all*
   current members (host + existing joiners + the newcomer), with `count`
   reflecting the true membership — not overwrite an existing slot.
3. **Notify every existing member** of the newcomer, each with its own
   `local_ref_id` (each recipient must see itself), not only the host and the
   joiner. In the capture, c1 was never sent an update when c24 joined.
4. Keep `owner_ref_id` = the host's id and set each recipient's `local_ref_id` to
   that recipient's own id (the stub already does this per-recipient in
   `build_member`; the missing piece is the roster membership and unique ids).

Whether a real in-progress match then *accepts* a live P2P join is a separate
question (the P2P link to the in-progress host must establish), but the roster
collision is the first, fatal blocker and is entirely server-side.

## Scope

- Server-side only: the fix is in `server/session_manager.py` (member-id
  allocation + roster assembly). No client patch or protocol change is required —
  the capture shows join-in-progress rides opcodes already modelled
  (`0x135`/`0x136`/`0x130`/`0x131`/`0x13b`), with no unknown messages.
- The two-member path (one host + one joiner) works and is unaffected; the bug
  only manifests at the third participant.
