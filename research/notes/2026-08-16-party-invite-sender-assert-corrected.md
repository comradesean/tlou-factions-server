# Party invites, part B: the sender-side assert — caller loop found, and the 2026-08-15 mechanism was WRONG

> **CORRECTION 2026-08-16 (later, from the marathon RPCS3 log) — the assert
> analysed in this note NEVER FIRED.** Grepping the full 3.4 GB log for
> `*** ASSERTION:` banners yields exactly three distinct texts:
> `team >= 0 && team < NetInfo::kMaxNetTeams` (1090x,
> `game/net/net-game-manager.cpp:1358`), `m_roomId != 0` (26x,
> `game/net/net-event/net-event-player.cpp:560`), and `m_roomSize > 0` (15x,
> `ndlib/net/net-session.cpp:227`). `_opd_FUN_00ad1fc0`'s trap
> (`net-session.cpp:786`, message text literally `"0"`, i.e. a plain
> `ASSERT(0)` "unreachable") produced **zero** log lines all session. The
> mechanism described below is real and correctly decoded, but it is **not**
> what boots the sender. The one that actually fires - 15 times, on nearly
> every online session - is `m_roomSize > 0`, and it is squarely ours:
> see `2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md`.
>
> Useful byproduct that *is* confirmed: the whole `0xad1xxx`-`0xad3xxx`
> function family is `ndlib/net/net-session.cpp`, and the assert ids in this
> note are that file's line numbers - `0x312` = 786 (`_opd_FUN_00ad1fc0`),
> `0xe3` = 227 and `0xda` = 218 (`_opd_FUN_00ad33d8`, the latter being
> `member->m_binDataSize <= SCE_NP_MATCHING2_ROOMMEMBER_BIN_ATTR_...`),
> `0x567` = 1383 (`_opd_FUN_00ad6148`,
> `size <= SCE_NP_MATCHING2_ROOM_BIN_ATTR_INTERNAL_MAX_SIZE`).

Static Ghidra pass against open item #3 / the "sender gets booted fully offline
on invite" half of `2026-08-16-session-handoff.md`. Every address below was
sanity-checked against the decompile *and* the raw disassembly before anything
was concluded from it. Cross-refs: `2026-08-15-createparty-trace.md` (which this
note corrects), `2026-08-16-party-invite-commid-and-npbasic-gates.md`.

## Correction 1: the two `this` pointers are not stale, corrupt, or garbage

`2026-08-15-createparty-trace.md` describes hit 2's `param_1` as "a
garbage-looking address ... that does NOT match this session's actual room_id,
`ROOM_PTR`, or anything else recognizable", and recommends re-testing after a
clean RPCS3 restart to see whether it is leftover state. **That test is not
worth running - both pointers are statically initialised globals.**

The only two callers of `_opd_FUN_00ad1fc0` are `0x003b17cc` and `0x003b17e0`,
both inside `_opd_FUN_003b15bc` @ `0x3b15bc`, and they are not a loop:

```c
  _opd_FUN_00ad0fd0(*(u32*)(TOC - 0x7fe4));
  _opd_FUN_00ad1fc0(*(u32*)(TOC - 0x7ffc), local_48, 0x20);   // TOC = 0x01271af8
  _opd_FUN_00ad1fc0(*(u32*)(TOC - 0x7fe4), local_48, 0x20);
```

Two hardcoded consecutive calls on two different global singletons. Dumping the
pointer table settles it:

```
01269af0: 00e5dc80 014db2ac 01385628 01383bd8   <- 0x01269afc = 0x01383bd8
01269b00: 01222d58 01459260 01389a38 01387240
01269b10: 0132c530 01387f58 01382082 013858c2   <- 0x01269b14 = 0x01387f58
```

`0x01383bd8` is the live `ROOM_PTR` (hit 1) and `0x01387f58` is the "bogus"
hit-2 value from test run 1 - **both read straight out of the image, from
adjacent slots in the same global pointer table.** Object A is the one every
message our stub sends is addressed to (`ROOM_PTR`); object B is a second,
identical-class object the game also ticks and that our server has never
touched. `_opd_FUN_00ad0fd0` (called on object B immediately above) walks 12
member slots at `obj + i*0x180 + 0x748`, confirming both are room/party objects
of the same type.

`_opd_FUN_003b15bc` has 14 callers, almost all `_opd_FUN_0035xxxx` /
`_opd_FUN_003exxxx` UI-screen functions - consistent with the 2026-08-15
observation that it fires on every menu transition. (It is *not* the Google
Analytics beacon path; the GA string in the register dump was unrelated stack
residue. The function does also push a stats blob via `_opd_FUN_00323818`, which
is probably where that impression came from.)

## Correction 2: a nonzero SetPartyData return is NOT fatal — the assert is somewhere else entirely

`2026-08-15-createparty-trace.md` states: "`_opd_FUN_00ad1fc0` treats that
nonzero return as fatal: logs, then `trapWord(0x1f, ...)`". **That is wrong.**
Raw disassembly of `0x00ad1fc0`:

```
00ad2030  bctrl                          ; vtable+0x30 -> SetPartyData
00ad2034  ld    r2,0x28(r1)
00ad2038  cmpwi cr7,r3,0x0
00ad203c  or    r27,r3,r3
00ad2040  bne   cr7,0x00ad2118           ; nonzero -> straight to the epilogue. No log, no trap.
00ad2044  ld    r0,0x10(r29)             ; room_id
00ad204c  cmpdi cr7,r0,0x0
00ad2058  bne   cr7,0x00ad206c
00ad205c  addi  r31,r29,0x1868           ; room_id == 0 -> use the spare record past slot 11
00ad2064  bne   cr7,0x00ad20a4
00ad206c  mulli r9,r11,0x180             ; --- 12-iteration member-slot scan ---
00ad2070  add   r9,r9,r28
00ad2078  addi  r31,r9,0x668
00ad2080  lbz   r0,0xe0(r9)              ; obj + i*0x180 + 0x748  (occupancy flag)
00ad2088  beq   cr7,0x00ad209c
00ad208c  lwz   r0,0xe8(r9)              ; obj + i*0x180 + 0x750  (that member's id)
00ad2090  lwz   r9,0x19ec(r29)           ; obj + 0x19ec           ("my own member id")
00ad2094  cmpw  cr7,r0,r9
00ad2098  beq   cr7,0x00ad20a4           ; match -> store party data into that slot, return 0
00ad209c  bdnz  0x00ad206c
00ad20a0  b     0x00ad20d0
...
00ad20d0  bl    0x00a16240               ; --- fallthrough: NO SLOT MATCHED ---
00ad20ec  li    r7,0x312                 ; assert id 0x312
00ad210c  bctrl                          ; log it
00ad2114  tw    r1,r1                    ; *** ASSERTION TRAP ***
```

So the trap is reachable **only when SetPartyData SUCCEEDED**. The real
condition, in full:

> `obj+4` (SessionManager ptr) is non-NULL
> **and** SetPartyData returned 0 (the object *is* registered in one of the
> SessionManager's four `0x9000`-stride room slots at `sessmgr+0x50`)
> **and** `obj+0x10` (room_id) != 0
> **and** none of the 12 member slots has `flag@+0x748 != 0 && id@+0x750 == *(obj+0x19ec)`
> → log assert `0x312`, `tw` → "You have been disconnected from the game servers".

Object B can therefore never trap under our server: our stub only ever names
object A in the wire `room_ptr` field, so object B is not in any SessionManager
room slot, SetPartyData returns `0xffffffff`, and `0x00ad2040` bails silently.
**Whatever booted the sender came from object A** - i.e. from the room our own
messages built.

Verified `_opd_FUN_00ad6148` (SetPartyData) directly to be sure of the return
semantics: it stores len/payload at `room+0x19f8`/`+0x19fc`, then scans
`*(int*)(sessmgr + 0x50 + i*0x9000)` for `== room` over 4 slots, `return
0xffffffff` on miss; on hit, if `room+0x10 != 0` it emits the 80-byte `0x13a`
packet and returns 0.

## Where `obj+0x19ec` and the member slots come from — this is ours to get right

`_opd_FUN_00ad33d8` @ `0xad33d8` is the member-slot registration routine. It has
exactly two live call sites, both inside the SessionManager receive dispatch
`_opd_FUN_00ad7604`: the `0x131` (Member) case at `0x00ad79d0` and the `0x132`
case at `0x00ad7c20`. From the `0x131` case:

```c
_opd_FUN_00ad33d8(room_obj, member_descriptor,
    (u64)(entry_member_id ^ *(u16*)(pkt + 14)) - 1 >> 0x3f,   // param_3: "this entry is ME"
    (u64)(entry_member_id ^ *(u16*)(pkt + 12)) - 1 >> 0x3f);  // param_4: "this entry is the OWNER"
```

`pkt + 12` / `pkt + 14` are exactly what `build_member` in
`tools/session_manager_stub.py` writes as `owner_ref_id` / `local_ref_id`, and
`entry_member_id` is read from `pkt + 0xa0 + i*0x68 + 36` - exactly the stub's
`struct.pack_into(">H", entry, 36, member_id)`. Confirmed both directions.

Inside `_opd_FUN_00ad33d8`:

```c
  // 1. dedupe: if an occupied slot's stored NpId string equals this entry's, RETURN
  //    EARLY with that slot's sequence number - before anything below runs.
  // 2. otherwise claim the first free slot iVar20:
  param_1[iVar20*0x60 + 0x1d4] = *(u16*)(param_2 + 0x38);   // slot+0x750 = member_id
  param_1[iVar20*0x60 + 0x1d2] = 1;                         // slot+0x748 = occupied
  ...
  if (param_3 != 0) param_1[0x67b] = param_1[iVar20*0x60 + 0x1d4];  // obj+0x19ec = my id
  if (param_4 != 0) param_1[0x67c] = ...;                           // obj+0x19f0 = owner id
```

Three consequences, all of them server-relevant:

1. **`obj+0x19ec` is only ever written, never cleared** by this routine, and
   only on the *first* add of a given NpId (the dedupe early-return skips the
   `param_3` block on every subsequent `Member` broadcast). Our
   `start_member_refresher` re-sends `Member` every 10s - those re-sends do
   **not** refresh `obj+0x19ec`.
2. Therefore: if the local player's member slot is ever freed (`0x134`
   RoomLeave / the `0x13b` per-member removal path both walk the same slot
   table) and he is later re-added under a **different** `member_id`,
   `obj+0x19ec` keeps the *old* id forever and no slot will ever match →
   assert `0x312` on the very next menu transition. `MEMBER_ID`/
   `JOINER_MEMBER_ID` in the stub are fixed constants (1 and 2), so any
   flow where the same account is re-added under the other constant, or where
   the roster is rebuilt after a removal, is a live candidate.
3. Equally: if any `Member` broadcast's roster contains **no** entry whose
   `member_id == local_ref_id`, `obj+0x19ec` is never set for that object at
   all (stays 0), and the scan cannot match either.

**Confidence:** the assert condition itself - very high (instruction-level
verified, two independent confirmations of every offset). Which *specific*
message sequence trips it during an invite - unknown; that needs a live
breakpoint, and the exact addresses are below.

## Not determined

- What actually clears `slot+0x748` during the invite flow (the `0x134`/`0x13b`
  removal path was not decompiled in this block).
- What object B (`0x01387f58`) is for, and whether retail expects it to be a
  registered SessionManager room too. Under our server it is inert.
- Whether the "sender booted offline" symptom is this assert at all. It is now
  the leading candidate with a concrete signature, but the 2026-08-15
  attribution was based on a misread and should not be treated as established.

## Live-test checklist (part B)

RPCS3 debugger, sender machine, solo-hosted Private Match room open.

1. Breakpoint **`0x00AD20D0`** - the "member-slot scan found nothing" path.
   Reaching this address at all *is* the bug; nothing else leads there.
   - **Never hit, but the sender still gets booted** → this assert is not the
     cause; the 2026-08-15 attribution was wrong in both directions and the
     disconnect needs a fresh trigger hunt.
   - **Hit** → read `r29` (the object). `r29 == 0x1383bd8` confirms it is
     object A / `ROOM_PTR`, i.e. squarely our room.
2. At that breakpoint, dump:
   - `[r29 + 0x19ec]` (u32) - the id the client thinks is "me".
   - `[r29 + 0x10]` (u64) - the room_id (must be nonzero to get here).
   - For `i` in `0..11`: `[r29 + i*0x180 + 0x748]` (byte, occupancy) and
     `[r29 + i*0x180 + 0x750]` (u32, member id).
   Compare against the stub's log for the last `Member` it sent:
   - **All occupancy flags zero** → the member table was wiped; find what wiped
     it (watch the `0x134`/`0x13b` handling around `_opd_FUN_00ad7604`).
   - **Slots occupied but no id equals `0x19ec`** → id-assignment mismatch;
     the stub is re-adding the local player under a different `member_id` than
     the one that first set `0x19ec`. Fix: make `local_ref_id` and the local
     player's `member_id` stable for the lifetime of the object, and never
     reuse the other constant for the same account.
   - **A slot does match** → impossible at this address; re-verify the dump.
3. Secondary breakpoint **`0x00AD2038`** (SetPartyData return, value in `r3`)
   to see how many of the two per-tick calls succeed. Expect `r3 == 0` for
   `r29 == 0x1383bd8` and `r3 == 0xffffffff` for `r29 == 0x1387f58`.
4. Breakpoint **`0x00AD79D0`** (the `0x131` Member -> `_opd_FUN_00ad33d8` call)
   to watch `r5`/`r6` - the computed `param_3`/`param_4` "is me"/"is owner"
   flags - for each roster entry. If `param_3` is 0 for every entry, the stub's
   `local_ref_id` does not match any `member_id` it shipped.

Do steps 1-2 before anything else: they are cheap and they either confirm or
kill the whole theory in one run.
