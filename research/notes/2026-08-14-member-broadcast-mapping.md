# Member (0x131) mapped, but NOT implemented - it needs a pointer we can't safely guess

Follow-up to `2026-08-14-room-create-joined.md` and
`2026-08-14-room-slot-gating.md`. Starting point: the working hypothesis,
based on experience with similar projects - "there's a flag telling the
client it's a client vs. a host, and we're sending the wrong one." That
hypothesis pointed at the right mechanism, but the actual fix turned out to
be more dangerous than expected.

## The headline answer

`_opd_FUN_00ad33d8` (member-slot registration) takes two flag params that
mark a registered member as "this is the local player" (writes
`room_obj+0x67b`) or "this is the room owner" (writes `room_obj+0x67c`). The
`RoomJoined` (0x132) call site - the only message this project currently
sends after `RoomCreate` - **always passes literal `0, 0`** for these,
hardcoded in the compiled dispatch code. So a solo host who gets a working
`RoomJoined` reply (as of the last pass) ends up with a room containing one
registered member, but the client has no idea that member is itself, or
that it owns the room. This is a strong candidate for why the flow spins at
`NET_SM_CHOOSE_HOST_JOIN` and times out into "Lobby Server Error" with zero
further network traffic - a local state gap, not something waiting on the
network.

The only OTHER call site is inside the `Member` (0x131) dispatch case, which
computes these flags per-roster-entry by comparing each entry's own id
against two header reference fields. Mapped the full wire format for this
message (see the new `protos/0x131_member.ksy` / `docs/protocol/0x131_member.md`
- header layout, per-entry layout, all confirmed via `_opd_FUN_00ad6e34`'s
own byte-swap-in-place code plus the buffer-size-check arithmetic, the same
technique that nailed `RoomJoined`'s real size in the prior pass).

## Why it's not implemented this pass

Raw disassembly of the `0x131` case (`research/ghidra/dispatch_raw2.txt`,
lines ~118-127) shows the header's offset-8 field is read straight off the
wire and **immediately dereferenced through its own vtable with no null or
validity check anywhere**:

```
lwz r24,0x8(r28)     ; wire bytes [8:12]
lwz r9,0x0(r29)      ; *(r29+0) - vtable ptr of "object at r29"
lwz r9,0x18(r9)      ; vtable[0x18]
lwz r0,0x0(r9)       ; real function pointer
bctrl                ; CALL through it
```

The server is expected to supply the address of an object the client itself
already allocated (its own room-slot object) - genuinely private client-side
heap state, not something a remote server can compute. Getting this wrong
doesn't degrade gracefully; it almost certainly crashes RPCS3 outright, same
class of failure as the `RequestSignalingInfos`-malformed crash from two
passes ago, except with no fallback error path at all this time (no null
check to even hit).

Two previously-observed, live-debugger-confirmed room-slot addresses exist
in this project's history (`0x01383bd8` and `0x01387f58`, from a
`FUN_00ad5ab0` breakpoint session), and separately, `RoomCreate`'s own
transaction id was found to be byte-identical across two independent
attempts minutes apart - both consistent with this build having no ASLR and
stable per-session heap addresses. That's a real lead, but not strong enough
to hardcode blind: a wrong guess trades a recoverable "spin and error" for a
hard crash requiring a full RPCS3 restart, which is a worse debugging loop,
not a better one.

## Recommended next step

Live-debugger session, not more static analysis: breakpoint at the client's
own "Host" button handler (not yet located - `FindCallersOf` on the
lobby-flow `"Host NET_SM = %i"` string and on `FUN_00ad5ab0` both came back
empty in an earlier pass, indirect vtable call), or simpler, re-break at
`FUN_00ad5ab0` (`0x00ad5ab0`) the same way as the earlier pass and read
`r3`/`r3+0x10` for the *current* run's room-slot address before ever
constructing a `Member` message with it. Confirming this address fresh per
run (rather than trusting a possibly-stale hardcoded value) is the safe path
forward.

## Raw evidence

- `research/ghidra/member_decomp.txt` - decompile of `_opd_FUN_00ad6e34`
  (header byte-swap helper, confirms exact field offsets) and
  `_opd_FUN_00ad5920` (a smaller sibling doing the same for a different
  opcode, not otherwise used this pass).
- `research/ghidra/dispatch_raw2.txt` - full raw disassembly of
  `FUN_00ad7604`, including the unguarded `room_ptr` dereference this note
  is about.
