# RoomJoined is gated on a local room-slot match - our reply's real fate is unconfirmed

Follow-up to `2026-08-14-room-create-joined.md`. Live result: the guessed `RoomJoined`
reply didn't crash or disconnect the client (it kept sending `Ping` normally for
minutes after), but produced **zero visible effect** and live testing still produced "Lobby
Server Error". This note traces why a `RoomJoined` message can be received and fully
consumed by the client's dispatch loop while doing *nothing* - no crash, no further
network traffic, no observable state change.

## The gating mechanism (confirmed via decompile)

`FUN_00ad7604`'s `iVar8 == 0x132` case (`research/ghidra/sessmgr_vtable_dump.txt`)
does NOT unconditionally process an incoming `RoomJoined`. It first searches the
client's own 4 pre-allocated room slots (`param_1+0x50`, `+0x9050`, `+0x12050`,
`+0x1b050`) for one where:
1. The slot pointer itself is non-null (a local room object was already registered
   there), AND
2. `*(longlong*)(room_obj+0x10)` equals the 8-byte value at the incoming message's
   own wire offset 8 (what our stub echoes back from `RoomCreate`'s offset 4:12).

**Only if both match** does it call `_opd_FUN_00ad33d8` (member-slot registration -
decompiled this pass, see below) to actually do anything. If no slot matches, the
loop falls through, the receive buffer is still advanced by 120 bytes (so no error,
no retry, no visible symptom), and the message is effectively discarded. This fully
explains the observed "received, logged, zero effect" behavior - it doesn't require
our reply's *content* to be wrong, only requires that no local slot matched.

## `_opd_FUN_00ad33d8` (decompiled this pass)

Straightforward member-slot registration: finds a free slot among up to 12 member
records on the room object, copies fields from the local struct we (indirectly)
populate from wire offsets 16-55 into it (team/rank/clan-loadout-shaped data - not
independently verified further this pass), then triggers a room-notify vtable call.
Nothing here looks like a validation/abort path back to `kNetLobbyFail` - it either
runs or doesn't, based purely on the slot-match gate above.

## Is the id-echo actually the problem? Evidence says probably not

`FUN_00ad0c90` (called right after a room object is registered into a slot via
`FUN_00ad5ab0`, vtable`+0xc`) was decompiled and turns out trivial - it only stores
the owning `SessionManager` back-pointer at `room_obj+4`. **It does not set
`room_obj+0x10`** (the field compared against our echoed id), so that field is set
by whatever client-side code actually initiates hosting - not yet located (see
below).

Notably, the 8-byte id at `RoomCreate` wire offset 4:12 was **byte-identical across
two independent room-create attempts several minutes apart** (`01 27 23 d8 01 38 3b
d8`, captured both ~13:43 and ~14:39, different room-name timestamps otherwise).
An id that's this stable across independent sessions on the same machine is much
more consistent with a deterministic heap pointer/handle (PS3 retail builds have no
ASLR, so repeated boots allocate the same addresses) than a per-request random
transaction id - which suggests the client already has this exact value available
locally (as `room_obj+0x10` or equivalent) by the time it sends `RoomCreate`, and
our straight echo is very likely already correct for this field.

## What's still genuinely open

The highest-value next step, **not resolved this pass**: find the actual client-side
function that runs when the player chooses "Host" (`game/net/lobby-flow.cpp`,
producing the `Host` / `GOTO NET_SM_CREATE_GAME_WAIT` log lines) and confirm it
calls vtable`+0xc` (`FUN_00ad5ab0`, room-slot registration) either before or
independently of sending `RoomCreate` - i.e. confirm the local slot genuinely exists
by the time our reply arrives. Two attempts to locate this by string/data
cross-reference (`e6aa18 "Host NET_SM = %i"`, and `FUN_00ad5ab0`/`FUN_00ad0c90`'s own
callers) came back empty - the call is almost certainly indirect (through a vtable on
an object reached via TOC-relative addressing), which is the same class of lookup
that needed `ResolveTocStrings.java`/manual disassembly tracing in earlier passes
rather than plain xref search. If a future pass confirms the slot genuinely doesn't
exist yet when `RoomCreate` is sent, then no `RoomJoined` reply content can fix this
- the real gap would be architectural (the room slot might only get created reactively
in response to a *different*, not-yet-identified message), not a field-value problem.

Also unconfirmed, lower priority: the 18x u16 "attribute" block (still sent zeroed)
and the trailing 64-byte region - `_opd_FUN_00ad33d8` reads up to 128 bytes from a
pointer anchored inside our 120-byte message for one field, meaning it reads 8 bytes
past our message's end into whatever the connection's receive buffer holds next
(not proven harmful - likely just reads into the following `Ping` message's leading
bytes in practice - but worth knowing about).

## No stub changes made this pass

`session_manager_stub.py`'s `RoomCreate`->`RoomJoined` handling is unchanged - the
evidence above doesn't point at a concrete, better field value to send instead of
what's already there, and speculative changes without a stronger basis aren't worth
the live-test cycle cost. Left running (pid unchanged, port 7314) in its existing
state.

## Raw evidence

- `_opd_FUN_00ad33d8` full decompile, `_opd_FUN_00ad0c90`, `FUN_00ad5ab0` -
  not saved to a dedicated evidence file this pass (ran via ad-hoc
  `DecompileByAddresses.java`/`FindCallersOf.java` invocations, output only to
  `/tmp`) - re-run against `research/ghidra/tlou_factions.gpr` with addresses
  `00ad33d8`, `00ad0c90`, `00ad5ab0` if needed again (see `docs/ghidra-setup.md`).
