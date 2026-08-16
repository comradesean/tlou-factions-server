# `NET_SM_SERVER_LOBBY` dispatcher and the team-assignment assert — Ghidra trace, unresolved

Consolidates several live Ghidra passes run over one session chasing why a
solo-hosted match either (a) permanently stalls on "Starting Game..." with no
timeout, or (b) loads into the match then boots back to lobby after ~10-15s via
`*** ASSERTION: team >= 0 && team < NetInfo::kMaxNetTeams *** game/net/net-game-
manager.cpp:1358`. Neither is resolved - this note records the trail so it isn't
re-walked from scratch.

## `NET_SM_SERVER_LOBBY`'s dispatcher

String `"NET_SM_SERVER_LOBBY"` at EBOOT VMA `0xe6aa78`. Its handler:
`_opd_FUN_001594bc` @ `0x1594bc` (found via `GetReferencesTo.java` against the
string address, then locating the state-table entry containing it - a
12-byte-stride `{name_string_ptr, unidentified_field, handler_OPD_ptr}` array
at `0x0125cc00`+). For contrast, `NET_SM_SETUP_TEAMS`'s handler is
`_opd_FUN_00156278` @ `0x156278`.

Both handlers share a generic shape: call `_opd_FUN_007f4540` to build a local
queue-view (capacity, array base, item count, read cursor - a bounded
producer/consumer queue, capacity 2 for this call site per the decompile:
`param_1[3] = param_5` where `r7=2` is passed explicitly), then pop from it via
a helper (`_opd_FUN_000600c0` for SERVER_LOBBY, `_opd_FUN_007f5990` for
SETUP_TEAMS - structurally identical, different queue instance). If a nonnull
item comes back, call vtable`+0x368` on it; nonzero result gets translated by a
per-state helper into the real state-transition code. **Zero at any step means
"stay put" - no timeout anywhere in this path**, matching the live symptom
exactly.

**Key difference from SETUP_TEAMS**: SETUP_TEAMS's handler requires a second
condition (`local_40[0] != 0` via helper `_opd_FUN_007f3c2c`) that SERVER_LOBBY
does not have - SERVER_LOBBY only needs one queued item to exist at all.

**The item count/array-base values are set up by SERVER_LOBBY's own caller**
(the outer state-machine dispatch loop), not read from a private global inside
the handler itself - i.e. this is a shared, generic bounded-queue mechanism
handed down by the dispatcher, not something local to this one state. The
outer dispatch loop's own entry point was never located.

**Not the room-slot array**: an early hypothesis (that the queue was actually
the client's well-known 4-slot room array, since one of the party-invite bug's
bogus pointers happened to match room-slot #2's address) was checked and
disproven - see `2026-08-16-team-selection-field-confirmed.md`'s cross-reference
and the party-invite investigation. Confirmed via decompile: the two objects
involved are unrelated.

**Producer never found.** Multiple passes searching for what writes into this
queue's count/array-base fields came up empty - either a dead end (one
candidate write site turned out to be inside a giant generic debug-string
formatter, a recognized noise pattern in this binary - see "Noise pattern"
below) or simply not reached within budget. **Live watchpoint on the queue's
count field is the recommended next step**, not more static tracing.

## The team-assignment array (separate investigation, same session)

`net-game-manager.cpp:1358`'s assert is inside a generic bounds-checked
accessor, `_opd_FUN_0039a5a0` @ `0x39a5a0`:
```c
if (1 < param_2) { trapWord(0x1f, ...); }
return *(undefined4*)(param_1 + param_2*4 + 0x4b1c);
```
Confirms `kMaxNetTeams == 2` (param_2 valid range 0/1) and pins the array at
`param_1+0x4b1c` (team[0]) / `param_1+0x4b20` (team[1]), stride 4.

Traced 8 callers of this accessor: **zero read session-manager wire data
directly** - all operands trace to local engine globals and locally-held
member-slot/party objects. This does NOT mean the bug is unfixable - see the
explicit correction in `2026-08-16-team-selection-field-confirmed.md` for why
that conclusion was wrong when first stated, and don't repeat the mistake.

Found the only literal-displacement write to this array
(`0x3ab49c`, inside `_opd_FUN_003aae8c` @ `0x3aae8c`, a ~250-line match-setup
routine): both team[0] and team[1] get set to the **identical** value, sourced
from a per-map/per-mode config record (`iVar15+0x34`, `iVar15` looked up via
`*(param_1+0x499c)` as an index). This is a **level-load default/fallback
seed**, not the real per-player assignment write - the actual write almost
certainly happens via a register-computed address elsewhere, which a literal-
displacement text search cannot find.

`param_1` here (the NetGameManager/match-state object, fields extend past
`0x4b58`) is confirmed **NOT the same object** as `room_obj`
(SessionManager's room-slot struct, fields top out around `0x1f8`) that
`0x143`/`0x144` (HostRank) read/write via `room_obj+0x18`. No bridge between
the two object families was found or ruled out - genuinely unexplored, not a
dead end.

## `0x144`/HostRank cross-check (bonus finding)

While tracing the above, `0x144`'s dispatch case was re-confirmed (already
decompiled, `research/ghidra/sessmgr_vtable_dump.txt:571-590`): 144 bytes,
gated by the same `room_obj+0x10` id-gate as every other opcode in this
family, memcpy's 128 bytes into `room_obj+0x18`. Bonus: the `0x141` case
immediately above it in the same dispatch function writes into
`room_obj+0x1f0` on receipt - the exact field `0x140`'s sender
(`_opd_FUN_00ad62dc`) writes locally. Confirms `room_obj+0x1f0` = "current
attr-flags" from both the send and receive sides independently.

Payload shape guess (not confirmed at the byte level): `_opd_FUN_003aae8c`
(the same match-setup function above) has a `while (iVar17 != 8)` loop over 8
player slots - 128 ÷ 8 = 16 bytes/slot exactly, a clean but unverified fit.

## Noise pattern to recognize and skip

`_opd_FUN_0016a204`-shaped functions (gated on a `param_1==1 && param_2==0xffff`
check, ~250-650 lines, full of unrelated subsystem debug-tree strings - hit
once with Havok physics strings, once with Google Analytics beacon strings in
the unrelated `CreateParty`/`0x13a` investigation) are a generic debug-string-
builder pattern reused across multiple engine subsystems in this binary. If
`GetReferencesTo` on a target address lands inside one of these, it's very
likely a false positive (the subsystem using it as scratch data, not a real
caller) - don't re-decompile it, move to the next candidate.

## How to apply

Both open threads (queue producer, team-array real write site) hit the same
wall: static tracing found the read/consume side cleanly but not the
write/produce side, because the actual writes are very likely through
register-computed addresses invisible to text/literal search. Live
breakpoints or watchpoints (on the queue's count field, and on
`param_1+0x4b1c`/`+0x4b20`) are the recommended next step for both, not
another static pass.
