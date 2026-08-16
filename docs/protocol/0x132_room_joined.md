# `NetMatchmakingRoomJoined` (opcode `0x132`)

Companion doc for `protos/0x132_room_joined.ksy`.

**status: partial** - size, the create-id echo requirement, and overall shape
confirmed by decompile; two field blocks (54 bytes total) have confirmed
*existence and that the client reads them* but not confirmed semantics/values.

## What this is

Server -> client reply on the Session Manager connection (port 7314),
confirming the player is now a member of a room. This project's stub sends it
in response to `RoomCreate` (`0x12f`) - see `session_manager_stub.py`'s
`build_room_joined()`. Whether it's also the correct reply to `RoomJoin`
(`0x130`, an actual join-an-existing-room request) is untested; the name and
the shared "you are now in a room" shape make it a reasonable guess but this
hasn't been exercised.

Decompiled from `FUN_00ad7604` (SessionManager's receive-dispatch loop,
vtable `+0x4` at base `0x01243b38`), the `iVar8 == 0x132` case - see
`research/ghidra/sessmgr_vtable_dump.txt` for the raw decompile and
`research/notes/2026-08-14-room-create-joined.md` for the full field-offset
derivation.

## Confirmed by decompile (not guessed)

- **Total size is 120 bytes (`0x78`), not the 160 the opcode/size debug-log
  table declares.** The dispatch code's own buffer-advance amount after
  processing this case is authoritative and directly contradicts the table -
  third such correction found this session (after `ClientHello2` and `Ping`'s
  opcode corrections in the parent doc). Treat the debug table as unreliable
  for any opcode without an independent check.
- Offset 8-15 (`create_id`): must equal the triggering `RoomCreate` request's
  own `create_id` field. The dispatch code searches the connection's 4 room
  slots for a longlong match at this offset and does nothing further if none
  is found - this is the correlation mechanism between request and reply.

## Read by the client, semantics unconfirmed

- Offset 16-51 (36 bytes, 18x `u16`): copied into a local struct and passed
  to a helper (`_opd_FUN_00ad33d8`) alongside two flag bits derived from a
  room-id comparison. Likely room settings (mode/team/slot counts) by
  analogy with `RoomCreate`'s own similarly-sized field cluster, but the two
  messages' offsets don't line up 1:1, so no mapping was attempted. Stub
  sends zero.
- Offset 52-55: a `u16` + 2 more bytes, same status. Stub sends zero.
- Offset 56-119 (64 bytes): the client stores a *pointer* to this region
  rather than reading fixed sub-fields in the traced excerpt - consistent
  with a name/string buffer. Stub fills it with the same
  `<npid>.<timestamp>` string the client itself sent in `RoomCreate`.

## What would close this out

Live-test whether the current best-effort reply is accepted (can't be done
from a coding session - needs a real RPCS3 run). If rejected, the 18-field
attribute block is the most likely culprit; cross-referencing it against
`RoomCreate`'s send-site decompile (see that doc's "what would close this
out") would let both messages' shared fields be filled in with real values
instead of zero.

## Confidence summary

| Field | Confidence | Reason |
|---|---|---|
| Total size (120 bytes, not the declared 160) | high | Confirmed by decompile of the receive-dispatch's own buffer-advance logic (`FUN_00ad7604`) - about as strong as evidence gets in this project, and it directly contradicts the debug-log table |
| `create_id` echo requirement (offset 8-15) | high | Decompile-confirmed: the dispatch code searches the connection's 4 room slots for a longlong match at this offset and does nothing further if none is found |
| Existence, size, and that the client reads offset 16-51 (18x u16), 52-55, and 56-119 | high | Decompile-confirmed - traced directly in `FUN_00ad7604`/`_opd_FUN_00ad33d8`, not inferred |
| Semantic meaning of offset 16-51, 52-55, and 56-119 | low | Only presence/size is confirmed; the 18x u16 block is guessed-by-analogy to `RoomCreate`'s similarly-sized cluster (offsets don't line up 1:1 between the two messages, so no real mapping was attempted), and offset 56-119 being a name/string buffer is inferred from the client storing a pointer to it rather than reading fixed sub-fields |
| Whether this message is also the correct reply to `RoomJoin` (`0x130`) | low | Untested - a reasonable guess from the shared "you are now in a room" shape, never exercised live |

Overall: **medium-high** on wire framing and the one enforced correlation
field (`create_id`); low on everything else's semantics - matches this
doc's `status: partial`.
