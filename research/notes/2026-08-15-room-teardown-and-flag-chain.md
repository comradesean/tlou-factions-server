# The room-active flag, and why 0x133 is a leave/teardown notice, not "MemberJoined"

Traced via live-crash-driven Ghidra work (`_opd_FUN_0040b210`, `_opd_FUN_00ad1410`,
`_opd_FUN_00ad65e8`, `_opd_FUN_00ad32c4` all fully decompiled this pass) plus
`powerpc64-linux-gnu-objdump` for exact instruction-level verification of the wire
format `_opd_FUN_00ad65e8` builds.

## The room object has two fields we never knew about: `+0xb8` (flag) and `+0xbc`

`ROOM_PTR` (`0x01383bd8`, see `docs/protocol/0x131_member.md`) has, in addition to
the already-known `+0x10` (8-byte room id) and `+0x1f8` (2-byte capacity) fields:

- `+0xb8` (1 byte) - a flag, checked in at least two other places
  (`_opd_FUN_0040b210`, `_opd_FUN_00ad1410`) as `*(char*)(ROOM_PTR+0xb8) != 0`,
  gating whether `+0x10`'s room id is treated as live or as 0.
- `+0xbc` (4 bytes) - written alongside `+0xb8` in `_opd_FUN_00ad65e8`, not yet
  independently traced.

Both live entirely in memory nobody sends us on the wire (they're at ROOM_PTR
offsets far outside anything our `Member`/`RoomJoined` payloads write) - this is
**purely client-internal bookkeeping**, not something our server can set directly
via existing message fields.

## `_opd_FUN_00ad65e8` (a vtable+0x1c method) is a room search-and-teardown routine, not a "member joined" handler

Full decompile (`research/ghidra/session_global_probe` search output, function
body reproduced below):

```c
undefined4 _opd_FUN_00ad65e8(int param_1, int param_2)
{
  // search up to 4 slots at param_1+0x50 (stride 0x2400) for one matching param_2
  ...
  if (*(longlong *)(param_2 + 0x10) != 0) {
    *(undefined1 *)(param_2 + 0xb8) = 1;
    *(undefined4 *)(param_2 + 0xbc) = 0;
    _opd_FUN_00a0e324(0x133);              // build+swap opcode 0x133 into the send buffer
    _opd_FUN_00a0e324(<garbage-stack-word>); // second 4 bytes - genuinely uninitialized stack, not meaningful data
    _opd_FUN_00acb93c(param_1+0x25060, &sendbuf, 0x10, 1); // SEND 16 bytes: [opcode][garbage][room_id, unswapped]
    *(undefined8 *)(param_2 + 0x10) = 0;   // zero the room's OWN id right after sending
    _opd_FUN_00ad32c4(param_2);            // -> teardown, see below
    return 0;
  }
  *(undefined1 *)(param_2 + 0xb8) = 1;
  return 0;
}
```

`_opd_FUN_00ad32c4(param_2)`:

```c
undefined8 _opd_FUN_00ad32c4(int param_1)
{
  // loop all 12 member slots (stride 0x180 bytes - same array _opd_FUN_00ad33d8
  // registers into), for every slot still marked valid (flag at slot+0x748,
  // matching _opd_FUN_00ad33d8's own +0x1d2 int-indexed validity flag):
  //   call _opd_FUN_00ad3190(room, slot+0x668)  - the SAME per-member "remove"
  //     callback the ALREADY-DECOMPILED 0x134 (RoomLeave) dispatch case uses
  //     (docs/protocol/session_manager_and_matchmaking.md's own opcode table
  //     entry for 0x134 cites this exact function)
  //   clear the slot's validity flag
}
```

**This is room teardown, not "member joined".** The declared opcode/size table
(`docs/protocol/session_manager_and_matchmaking.md`) names 0x133
`NetMatchmakingMemberJoined` purely from the `0x12d + table index` formula - a
formula the same doc already flags as unconfirmed past the handshake opcodes,
and this is now a second confirmed case (after `ClientHello2`/`Ping`) where
that formula's name is wrong. `0x133` fires when the client decides to abandon
a room it's tracking: it announces the departure (opcode 0x133, wire format
above), zeroes its own copy of the room id, then walks every member slot and
runs the *exact same* per-member removal path the confirmed `0x134`
(`RoomLeave`) dispatch case uses. Whatever this game calls it internally, it
belongs conceptually next to `RoomLeave`/`RoomLeft`, not `MemberJoined`.

`0x133` is also not one of the 11 opcodes the client's own receive-dispatch
(`FUN_00ad7604`) has a case for - confirming it really is fire-and-forget
outbound-only, matching every live capture (never followed by anything
resembling a reply from a live server). A same-opcode echo reply was tried
live 2026-08-15 and had zero effect either way, consistent with this.

## Why this matters for the "stuck forever" investigation

Every capture that reaches this point (both solo Custom Game, after enough
UI dwell time, and 2-player Find Match pairings) eventually sends 0x133 and
then goes quiet except `Ping` - this is the client **giving up on the room
and tearing it down locally**, not a client waiting on us for anything further.
The room isn't failing to progress because of a missing reply; the client's
own logic has already independently concluded the room should be abandoned.

**What's not yet found**: the actual CALLER of `_opd_FUN_00ad65e8` (an indirect
vtable+0x1c dispatch - same static-analysis wall hit all session on virtual
calls) - i.e. *why* the client decides to invoke this teardown. Leading
candidates, none confirmed: a client-side timeout waiting for some condition
that never arrives; a validation check against room/member data that our
wire payloads don't satisfy; or normal behavior when backing out of a menu
(would need to be ruled out by correlating exact UI action with capture
timing). **Next step recommended**: live RPCS3 debugger breakpoint directly
on `0x00ad65e8` (the function entry) to catch it firing in real time, read
the call stack, and see what condition/timer led to it - this needs a live
session, not more static tracing, since the caller is only reachable via
indirect dispatch.
