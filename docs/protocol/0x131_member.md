# `NetMatchmakingMember` (0x131) - room roster broadcast

Companion doc for `protos/0x131_member.ksy`.

**status: implemented and live-confirmed working (crash-free) as of
2026-08-14.** Wire layout mapped from decompile + raw disassembly
cross-check, then the two highest-risk fields (`room_ptr`, `capacity`) were
each nailed down via live RPCS3 debugging after two real crashes - see "The
`room_ptr` hazard" and "The `capacity` field" below for exactly how each was
found. This is the mechanism this project believes is needed to tell the
client "you are both a member of this room AND its owner" - something
`RoomJoined` (0x132) alone does not do (see "Why this message matters"
below). `tools/session_manager_stub.py` sends this immediately after
`RoomJoined` in response to `RoomCreate`.

## Why this message matters

Decompiling `_opd_FUN_00ad33d8` (member-slot registration, called from both
the `RoomJoined` and `Member` dispatch cases) shows it takes two flag
parameters:

```c
if (param_3 != 0) { param_1[0x67b] = param_1[iVar20*0x60+0x1d4]; }  // mark as local player
if (param_4 != 0) { param_1[0x67c] = param_1[iVar20*0x60+0x1d4]; }  // mark as room owner
```

The `RoomJoined` call site (`FUN_00ad7604`'s `iVar8 == 0x132` case) always
passes **literal `0, 0`** for these - hardcoded in the compiled dispatch
code, not influenced by anything the server sends in the `RoomJoined` reply
itself. This means a `RoomCreate` -> `RoomJoined`-only flow registers a room
member but never tells the client which member is itself or who owns the
room - a real candidate for why solo-host testing spins at
`NET_SM_CHOOSE_HOST_JOIN` and eventually times out into "Lobby Server Error"
with zero further network traffic (a local state gap, not a network wait).

The **only other call site** for `_opd_FUN_00ad33d8` is inside the `Member`
(0x131) case, where the flags are computed per-roster-entry by XOR-comparing
each entry's own id against two header reference fields - i.e. `Member` is
how the client is meant to learn "entry N in this roster is you" / "entry N
is the owner."

## Header layout (160 bytes / 0xa0)

Confirmed via `_opd_FUN_00ad6e34` (the byte-swap-in-place helper called
before this case's own logic runs - see `research/ghidra/member_decomp.txt`)
plus the buffer-size-check arithmetic (`0xa0 + roster_count * 0x68`,
`research/ghidra/dispatch_raw2.txt` lines ~100-113):

| offset | size | field | confidence |
|---|---|---|---|
| 0 | 4 | opcode = 0x131 | high |
| 4 | 4 | unknown - swapped but unread in the traced case body | low |
| 8 | 4 | **`room_ptr`** - see hazard section below | high (mechanism), none (value) |
| 12 | 2 | `owner_ref_id` - XOR-compared against each entry's own id | high |
| 14 | 2 | `local_ref_id` - same mechanism, marks the local player's entry | high |
| 16 | 8 | overwrites the target room object's own id field (`room_obj+0x10`) - the SAME field `RoomJoined`'s `create_id` gate-checks against | high (mechanism) |
| 24 | 2 | `capacity` - see "The `capacity` field" below | high (mechanism + value, live-confirmed) |
| 26 | 2 | `roster_count` - confirmed, drives both the loop bound and the size check | high |
| 28 | 2 | unknown - swapped but unread | low |
| 30 | 130 | not read by the traced code at all - padding out to the confirmed 160-byte header | unconfirmed (assumed zero-safe) |

## Per-entry layout (104 bytes / 0x68, x `roster_count`)

Two parallel data streams both step by 0x68 bytes per entry - `puVar19`
(entry start) feeds an 18x u16 "attributes" block into
`_opd_FUN_00ad33d8`'s local struct, and `puVar18` (entry start + 36) feeds
the entry's own id plus two more bytes:

| entry offset | size | field | confidence |
|---|---|---|---|
| 0 | 36 | 18x u16 "attributes" - structurally parallel to `RoomJoined`'s own unconfirmed attribute block, not independently mapped | low |
| 36 | 2 | `member_id` - XOR-compared against the header's `owner_ref_id`/`local_ref_id` | high |
| 38 | 1 | unread byte in traced code | low |
| 39 | 1 | unread byte (flags-shaped) in traced code | low |
| 40 | 64 | not read by the traced loop - by parallel with `RoomJoined`'s own trailing region, likely a name/NpId buffer | unconfirmed |

## The `room_ptr` hazard - resolved

Raw disassembly of the `0x131` case (`research/ghidra/dispatch_raw2.txt`
lines 118-127) shows the header's offset-8 field is:

```
lwz r24,0x8(r28)     ; r24 = wire bytes [8:12], already byte-swapped
rldicl r29,r24,0x0,0x20
or r3,r29,r29
lwz r9,0x0(r29)      ; r9 = *(r29+0)          <- vtable pointer of the OBJECT AT r29
lwz r9,0x18(r9)      ; r9 = vtable[0x18]
lwz r0,0x0(r9)       ; r0 = .opd descriptor -> real function pointer
mtspr CTR,r0
bctrl                ; CALL through the wire-supplied pointer
```

**There is no null check or validity check of any kind before this call.**
The client treats whatever the server sends at wire offset 8 as the address
of an already-existing local object and immediately calls a virtual method
through it. This is not something a remote server can legitimately compute -
it has to be the exact live address of the client's own room-slot object,
which is private client-side heap state. Sending zero, or any other guessed
value, will very likely crash the emulator (a bad-vtable or unmapped-page
dereference) rather than degrade gracefully - a worse outcome than the
current "spins into Lobby Server Error" behavior this message is meant to
fix.

Immediately after the call, the client also writes into fields of the
target object (`room_obj+0x10` and `room_obj+0x1f8`) using data partly
sourced from THIS message's own wire bytes (offset 16:24 and 24:26
respectively) - consistent with "the server tells the client which of its
own local room-slot objects to finalize, using data the server provides",
which only makes sense if the server already knows that object's address.

**Resolved 2026-08-14**: `ROOM_PTR = 0x01383bd8` in `session_manager_stub.py`.
Confirmed live via a fresh RPCS3 debugger breakpoint at `0x00ad7b14` (the
`RoomJoined` id-gate, `r27`) taken specifically for the boot this value was
used in - matching the same value observed identically across at least four
separate breakpoint hits (`FUN_00ad5ab0`'s `r4`, and `0x00ad7b14`'s `r27`
three times) spanning multiple independent "back to menu, host again"
attempts within the same RPCS3 process. PS3 retail builds have no ASLR, so
this address is stable per-boot; if it ever needs re-deriving (e.g. after a
full RPCS3 restart), break at `0x00ad7b14` during a fresh `RoomCreate` and
read `r27`.

## The `capacity` field - resolved via a live crash

Sending `0` for the header's offset-24 field (originally logged as "low
confidence, capacity-shaped") crashed RPCS3 outright with a PPU trap at
`0x00ad38b8` - inside `_opd_FUN_00ad33d8` itself:

```c
if (param_1[0x7e] == 0) {   // room_obj + 0x1f8, written from this field
    ...
    trapWord(0x1f, ...);    // explicit compiled-in assert - fires here
}
```

An explicit "this must never be zero" assertion, not a guess about intent.
Fixed by sourcing this field from `RoomCreate`'s own wire offset `0x1e`
(2 bytes, live-captured as `00 0a` = 10) - the room's own declared
max-player count, which is the obvious source of truth for a room-object
"capacity" field and reads naturally as the room's own player limit.

## Confidence

Header/entry offsets: high (mechanically confirmed via the byte-swap helper
and size-check arithmetic touching exactly these locations). `room_ptr` and
`capacity`: high, both live-confirmed (the former via direct memory read,
the latter via a crash that named the exact required invariant). Field
semantics beyond `roster_count`/`member_id`/`owner_ref_id`/`local_ref_id`/
`room_id_overwrite`/`capacity`: still low/unconfirmed, but the message as
currently built is empirically crash-free end to end.
