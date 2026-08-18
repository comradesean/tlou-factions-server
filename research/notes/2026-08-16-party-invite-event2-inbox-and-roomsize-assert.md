# Party invites, part C: the invite is delivered and consumed correctly — it dies on `m_roomSize > 0` in OUR room object

This supersedes the open question in
`2026-08-16-party-invite-commid-and-npbasic-gates.md`. Driven by new evidence
from the marathon RPCS3 log (assert-filtered extract: `research/logs/2026-08-16-marathon-tty-asserts.txt`)
(`/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/log/RPCS3.log`,
3.4 GB, comradesean's machine) plus raw-disassembly work against the decrypted
EBOOT at
`/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf`.
Ghidra was not used (project locked by a concurrent headless run); everything is
`powerpc64-linux-gnu-objdump -b binary -m powerpc:common64 -EB
--adjust-vma=0x10000` plus small Python readers, now kept in
`tools/eboot_analysis/`. Cross-refs:
`2026-08-16-party-invite-sender-assert-corrected.md` (same source file, same
function family), `2026-08-15-createparty-trace.md`.

## The runtime chain, end to end, from one 300-millisecond window

The game writes its own diagnostics to `sys_tty`, and RPCS3 logs them. That
turns out to settle almost everything:

```
1:07:00.890  rpcn:      Received message from mgnomad2:
1:07:00.890  sceNp:     commId: NPWR03073, msgId: 3, mainType: 1, subType: 0, ... data_size: 20
1:07:01.058  NPHandler: basic_event: event:2, from:mgnomad2(mgnomad2), size:20   [LR 0x003552d8]
1:07:01.060  TTY:       "Post Message 10b, size 16"
1:07:01.076  TTY:       "Get Message 10b, size 16"
1:07:01.377  TTY:       "sceNpSignalingGetConnectionFromNpId() failed . ret = 0x8002a816"
1:07:01.378  TTY:       "*** ASSERTION: m_roomSize > 0"
1:07:01.379  TTY:       "***      File: ndlib/net/net-session.cpp"
1:07:01.379  TTY:       "***      Line: 227"
1:07:01.380  TTY:       "[713.2134]  joined match"                <- the %s player name is EMPTY
...
1:07:19.754  TTY:       "Error 9"
1:07:19.754  TTY:       "[731.5800] comradesean left match"
1:07:19.755  TTY:       "[731.5800] Removing User 'comradesean' failed!!!!!!"
1:07:19.755  TTY:       "[731.5800] Terminate Connection comradesean 4660 1"
1:07:19.755  TTY:       "[731.5800]  left match"                  <- EMPTY again
1:07:19.756  TTY:       "[731.5800] Removing User '' failed!!!!!!"
1:07:19.757  sceNp:     sceNpBasicUnregisterHandler()             [LR 0x0034f454]
1:07:19.773  TTY:       "Pushing sys module configuration 'single-player'"
```

**Everything the previous two notes worried about is exonerated.** The commId
matched, the basic handler was registered, gate 4 passed, the pump ran, the
game enqueued the message and consumed it 17 ms later. The invite works. What
fails is the *join* it triggers, 300 ms later, on a room object our server
built.

(Bonus: the PPU register dump attached to the first TTY write shows
`r2 : 0x1305870`, independently confirming the TOC base derived statically
below.)

## Correction to part A: the commId theory is dead, and the stub theory is dead

- **commId mismatch: dead for this pair.** Every `sceNpBasicRegisterHandler`
  line in the entire 3.4 GB log registers `NPWR03073`, 12+ boots, no
  exceptions, and the incoming message carried `commId: NPWR03073`. The
  `NPWR03073` / `NPWR00795` split found statically is real but did not fire
  here. The RPCN normalization committed in submodule `1f272cd` is therefore a
  **no-op for this pair** - keep it as a guard for the `NPWR00795` case, do not
  expect it to change anything.
- **`sceNpBasicGetMessageEntryCount` / `GetCustomInvitationEntryCount` stubs:
  irrelevant.** Retire that theory. Those two have exactly one caller,
  `_opd_FUN_0034923c` @ `0x34923c`, whose only effect is
  `*(0x0137cb08) = count` for message *info type 4*
  (`SCE_NP_BASIC_MESSAGE_INFO_TYPE_CUSTOM_DATA_MESSAGE`) - a badge counter for
  the custom-data channel, read only by the event-20/21 handlers
  (`0x388700` / `0x3887e8` / `0x388754`) and one UI site at `0x34b08c`.
  Nothing on the party-invite path touches it. **No RPCS3 patch is needed.**
  (Also a small accuracy fix: the earlier Ghidra decompile rendered that store
  as `= 0`; the disassembly at `0x349288-0x349290` shows
  `lwz r9,-32452(r30); lwz r0,112(r1); stw r0,0(r9)` - it stores the real
  out-param, which merely happens to always be 0 under RPCS3.)

## How TLOU actually receives an invite (static, verified)

### The event pump and its jump table

`_opd_FUN_00355258` @ `0x355258`. `lwz r30,-31188(r2)` at `0x355264` pins
**r2 = 0x01305870** (`0x012fde9c + 0x79d4`; independently corroborated by
Ghidra naming the stored TOC value `vfn_01305870`, and by the live register
dump above). Then:

```
355308  cmplwi cr7,r0,23
35530c  bgt    cr7,0x3554dc        ; events 0..23 only
355310  lwz    r9,-31036(r30)      ; r9 = *(0x012684e4) = 0x0035532c  (jump table base)
355318  lwzx   r0,r9,r0            ; table[event] : self-relative s32
355320  add    r0,r0,r9
355328  bctr
```

The 24-entry table at **`0x0035532c`**, fully decoded - only **seven** distinct
targets:

| target | events |
|---|---|
| `0x0035538c` | 0 OFFLINE |
| `0x003553c4` | 1 PRESENCE |
| **`0x0035540c`** | **2 MESSAGE** |
| `0x00355434` | 16 INCOMING_CUSTOM_INVITATION, 23 INCOMING_BOOTABLE_INVITATION |
| `0x0035545c` | 21 INCOMING_CUSTOM_DATA_MESSAGE |
| `0x0035546c` | 20 RECV_CUSTOM_DATA_RESULT |
| `0x003554c4` | 14 RECV_INVITATION_RESULT |
| `0x003554dc` | 3, 4, **5**, 6, 7, 8, 9, 10, 11, 12, 13, 15, 17, 18, 19, 22 — the shared loop-continue, i.e. **ignored** |

**`SCE_NP_BASIC_EVENT_INCOMING_INVITATION` (5) is a no-op in this game.** So
is `INCOMING_ATTACHMENT` (4). Remember that for the next section.

### Event 2 -> the game's own message bus

```
35540c  lwz  r9,-31044(r30)   ; r9 = *(0x012684dc) = 0x0137a268, the 0x200 GetEvent data buffer
355410  addi r3,r1,124        ; from  (SceNpUserInfo the pump passed to sceNpBasicGetEvent)
355414  lwz  r6,120(r1)       ; *size  (= 20 here)
355418  addi r5,r9,4          ; payload = data + 4
35541c  addi r6,r6,-4         ; len    = size - 4  (= 16)
355420  lwz  r4,0(r9)         ; tag    = *(u32*)data
355428  bl   0x3c9434
```

`0x3c9434` enqueues into a fixed-size global inbox:

- **count (u64) at `0x01387250`**
- **array at `0x01387258`**, 64 entries x 52 bytes (`0xD00`, ending `0x01387f58`)
- entry layout: `+0x00` sender `SceNpId` (36 B, npid string at +0),
  `+0x24` pad, `+0x28` `u32 tag`, `+0x2c` `u32` heap pointer to the payload
  (allocated at `0x3c9600` via `0x915a30`), `+0x30` `u32 len`
- silent drops: `len + 4 > 511`, or `count == 64` (queue full)
- it logs `"Post Message %x, size %i"` on the way in - which is exactly the TTY
  line above.

Read side, same compilation unit: `0x3c8f20(tag, out, remove_flag)` =
find-by-tag, copy out, compact the array, decrement count; logs
`"Get Message %x, size %i"`. It is called from **36 sites** across the UI and
state machines. `0x3c8f00` clears the whole inbox; `0x3c9160` debug-dumps it.

Send side is the exact mirror: `0x3c908c(to_npid, tag, data, len)` builds
`[u32 tag][data]` and calls `sceNpBasicSendMessage`, which RPCS3 hardcodes to
`mainType = SCE_NP_BASIC_MESSAGE_MAIN_TYPE_GENERAL`
(`sceNp.cpp:1197`). **So `mainType: 1` is correct and deliberate** - this is
TLOU's private RPC-over-NP-messages channel, not an XMB invite.

### Answer to "should we rewrite mainType 1 -> 3?": NO. It would break it.

- `mainType 3` without `BOOTABLE` -> `SCE_NP_BASIC_EVENT_INCOMING_INVITATION`
  (5) -> jump-table target `0x003554dc` -> **ignored, payload discarded**.
- `mainType 3` with `msgFeatures |= BOOTABLE` -> event 23 -> `0x00355434`,
  which does only `n = get(cfg); set(cfg, n + 1)` (`0x3abfa8` / `0x3abfb0`) -
  a pending-bootable-invitation *counter*. It never touches the inbox and
  never sees the tag.

Either way the invite is destroyed. This would convert a delivery that
currently works into a guaranteed drop. **Do not do it.**

## Payload semantics (part C)

Wire format is `[be32 tag][body]`; `data_size: 20` = tag + 16 bytes.

Tag space in this build is `0x100`-`0x125` (256-293). The tag that arrived was
logged by the game itself as **`10b` = 267**.

All three tag-267 senders build an identical 16-byte body:

```
  35b71c  std r9,120(r1)      ; +0  be64  room / session id
  35b720  stb r29,128(r1)     ; +8  u8    flag = 0
  35b70c  li  r4,267
  35b714  li  r6,16
```
```
  39f148  std r9,112(r1)      ; +0  be64  room / session id
  39f14c  stb r0,120(r1)      ; +8  u8    flag = 1
```
(third at `0x35cb20`, same shape.) `+9..15` is left as stack residue.

> `body = { be64 room_id; u8 flag; u8 pad[7] }`

The `be64` is a room id with high confidence: at `0x35b6f8` the sender guards
with `ld r0,16(r11); cmpd cr7,r0,r9; beq -> skip`, i.e. "don't send if this is
already my current room", and `+0x10` is the established room_id field on this
object family (`_opd_FUN_00ad6148` reads `*(room+0x10)` as the room_id it puts
in the `0x13a` packet - see `2026-08-16-party-invite-sender-assert-corrected.md`).
The same `obj+0xb8` flag / `obj+0x10` u64 pair is what `_opd_FUN_00354c2c`
packs into the *GUI* invite path too.

Tag 267 is polled at `0x3caad0` and `0x3cad48` inside `_opd_FUN_003ca9d0`,
which replies with **tag 268** (also 16 bytes) via `0x3c908c`; 268 is polled at
`0x35ee24` and `0x39ef88`. So 267/268 are a request/reply pair.
**Labels (267 = "join my room" invite, 268 = the reply) are a medium-confidence
inference** - this compilation unit carries no debug strings - but the payload
layout is high confidence (three independent identical senders) and the
request/reply structure is certain.

Note the log shows **no** outgoing `sceNpBasicSendMessage` from comradesean in
the 19 s after receipt, i.e. the tag-268 reply was never sent - consistent with
`_opd_FUN_003ca9d0` bailing at `0x3cab0c` (`cmpwi cr7,r3,0; bne 0x3cab74`) or
with the assert firing first.

## THE ACTUAL BUG: `m_roomSize > 0`, net-session.cpp:227

The assert string `"m_roomSize > 0"` lives at `0x00ed7fc0`. Its pointer slot is
`0x0129759c`, and the **only** instruction that loads it is:

```
00ad3894  lwz r3,-32700(r30)     ; r3 = "m_roomSize > 0"     (anchor 0x0129f558 - 0x7fbc)
```

which is inside **`_opd_FUN_00ad33d8`** - the member-slot registration routine
already traced in `2026-08-16-party-invite-sender-assert-corrected.md`. The
matching decompile is:

```c
  if (param_1[0x7e] == 0) {                       // room_obj + 0x1f8 == 0
    ... log(msg="m_roomSize > 0", file="ndlib/net/net-session.cpp", line=0xe3 /* 227 */) ...
    trapWord(0x1f, ...);
  }
```

`0xe3 == 227` matches the logged line number exactly, the file-string slot
(`0x01297570` -> `ndlib/net/net-session.cpp`) is loaded at `0x00ad388c` into
`r4` two instructions earlier, and the message slot resolves to the exact
asserted text. **Triple-verified.**

`room_obj + 0x1f8` is `m_roomSize`, and it is written in exactly **one** place
in the whole binary - the `0x131` (Member) case of the SessionManager receive
dispatch `_opd_FUN_00ad7604`:

```c
piVar20[0x7e] = (uint)*(ushort *)(param_1 + 0x24070);   // room_obj+0x1f8 = wire u16 @ offset 24
```

which is exactly what our stub writes:

```python
struct.pack_into(">H", header, 24, max_players)  # tools/session_manager_stub.py, build_member()
```

The **`0x132` case calls the same `_opd_FUN_00ad33d8` without ever setting
`piVar20[0x7e]`.**

> ### Verdict
> The invitee's client accepted the invite, went to join mgnomad2's room, and
> ran member registration against a room object whose `m_roomSize` was still 0,
> because our server drove that object through a path that never delivered a
> `0x131` Member packet (whose wire offset 24 is the only thing that sets
> `m_roomSize`). It asserted, reported `" joined match"` with an empty player
> name, and ~18 s later tore the whole multiplayer session down
> (`Removing User '' failed!!!!!!` -> `Pushing sys module configuration
> 'single-player'`).

`tools/session_manager_stub.py`'s own `build_room_joined` docstring already
flags this as an untested guess: *"Only RoomJoined is sent here, not a
follow-up Member (0x131) roster ... this is unconfirmed against live
behavior."* It is now confirmed - as wrong.

### It is systemic, not invite-specific — and it has a twin

Grepping the **whole** 3.4 GB log for assert banners:

| assertion | file:line | count |
|---|---|---|
| `team >= 0 && team < NetInfo::kMaxNetTeams` | `game/net/net-game-manager.cpp:1358` | 1090 |
| `m_roomId != 0` | `game/net/net-event/net-event-player.cpp:560` | 26 |
| **`m_roomSize > 0`** | **`ndlib/net/net-session.cpp:227`** | **15** |

`m_roomSize > 0` fires roughly **every online session of the marathon**
(0:01:58, 0:07:33, 0:12:21, 0:15:01, 0:23:50, 0:40:49, 0:55:23, 0:57:49,
1:07:01, …) - long before the 2-player invite ever happened. **This is not an
invite bug; the invite just walks into an already-broken room-join path.**
That raises its priority a long way: it is plausibly upstream of several other
open items.

It is also almost always preceded, seconds earlier, by one or more
`m_roomId != 0`. That assert (function at `0x0040b210`) is:

```
40b278  ld    r0,16(r10)        ; r0 = room_obj->m_roomId  (room_obj + 0x10)
40b27c  cmpdi cr7,r0,0
40b280  std   r0,96(r3)         ; copy into the net-event-player record at +0x60
40b284  bne   cr7,0x40b2d0      ; nonzero -> fine
        ... assert "m_roomId != 0", net-event-player.cpp:560 ...
40b2cc  twu   r1,r1
```

**The two asserts are the same root cause.** The `0x131` Member dispatch case
writes *both* of these fields, from the same packet, and nothing else in the
binary writes either:

```c
uVar16        = *(u64*)(pkt + 16);                  // wire offset 16
piVar20[0x7e] = (uint)*(u16*)(pkt + 24);            // wire offset 24  -> room_obj+0x1f8 = m_roomSize
*(u64*)(piVar20 + 4) = uVar16;                      //                 -> room_obj+0x10  = m_roomId
```

and `build_member()` packs exactly those:

```python
header[16:24] = room_id
struct.pack_into(">H", header, 24, max_players)
```

So `m_roomId == 0` **and** `m_roomSize == 0` is precisely the signature of *"this
room object never received a `0x131` Member packet, or lost it"*. Which closes a
loop with something the project already observed live and worked around blindly -
`start_member_refresher()`'s docstring: *"read that ROOM_PTR+0x10 (room id) goes
to zero shortly after Member is [sent]"*. That refresher exists because of this
exact bug. Note that the id-gate fix in `2026-08-16-session-handoff.md` #1
made the refresher stop on room abandon, which may have widened the window.

The `sceNpSignalingGetConnectionFromNpId() failed . ret = 0x8002a816`
(`SCE_NP_SIGNALING_ERROR_OWN_NP_ID`) 1 ms earlier is the same class of bug
`build_member` already fixed once for the roster path (see its docstring), and
the empty `%s` in `" joined match"` / `"Removing User ''"` says the member
record the client built had no npid. All three symptoms are consistent with
one cause: **the joining client was given a room with no valid roster.**

### Cross-check against `776bd51` (landed concurrently, in a parallel workstream)

`776bd51` ("parse real room_ptr and max_players from RoomCreate") lands right
on top of this, from the opposite direction, and the two findings agree:

- **The value was never the problem.** Both before and after that commit
  `max_players` has an `or 10` / `or 8` fallback, so `build_member`'s wire
  offset 24 was never zero. `m_roomSize == 0` therefore cannot mean "we sent a
  zero"; it means **that room object never received a `0x131` at all**.
- **Which the same commit plausibly explains and fixes.** Member header offset
  8 is `piVar20 = *(int**)(pkt + 8)` - *the room object the whole packet
  applies to*. Until `776bd51` the stub sent a hardcoded `ROOM_PTR` there;
  it now echoes the client's own room-object pointer parsed from `RoomCreate`.
  If the hardcoded pointer ever disagreed with the object the client was
  actually using, then `m_roomId` (offset 16) and `m_roomSize` (offset 24) were
  being written into the *wrong* object - leaving the real one at zero on both,
  which is exactly the observed
  `m_roomId != 0` + `m_roomSize > 0` assert pair.

**So the first thing to check in follow-up work is whether `m_roomSize > 0` still
fires at all after `776bd51`** - it may already be fixed. If it does still
fire, the invite-join path (RoomJoined without a preceding Member) is the
remaining suspect and the spec below applies.

## Recommended server fix (spec only - not applied here)

`tools/session_manager_stub.py` was deliberately **not edited** in this block:
the stub was live and concurrent work on the protocol surface was in flight. Spec:

1. On the invite-driven join, send a `0x131` **Member** packet to the joining
   client *before* (or instead of) a bare `0x132`, with:
   - header offset 24 (`max_players`) **nonzero** - this is `m_roomSize`, and
     zero is the exact assert condition;
   - header offset 12 = `owner_ref_id`, offset 14 = `local_ref_id` where
     `local_ref_id` **must** equal the `member_id` (entry offset 36) of the
     joiner's own roster entry - otherwise `room_obj+0x19ec` is never set and
     you get the *other* assert (net-session.cpp:786, see the part-B note);
   - a roster containing both the host and the joiner, each with a real npid,
     and with the recipient's own entry's attribute-block npid left empty (the
     existing `member_id != local_ref_id` guard) so signaling is never opened
     to self - that is the `0x8002a816` seen 1 ms before the assert.
2. Only then send `0x132` for subsequent member-joined deltas.

## Live-test checklist (part C)

The inbox is at fixed absolute addresses, so this needs no breakpoints:

1. Repeat the 2-player invite.
2. **RPCS3 log, receiver:** confirm the sequence
   `Received message` -> `basic_event: event:2` -> TTY `Post Message 10b` ->
   TTY `Get Message 10b`. If all four appear, delivery is fine (it was) and the
   problem is entirely in what the join produces.
3. **Watch the TTY lines specifically** - `ASSERTION: m_roomSize > 0` at
   `net-session.cpp:227` is the signature. If it is gone after a stub change,
   the fix landed.
4. If you want the raw payload: dump memory at **`0x01387250`** (u64 count) and
   **`0x01387258`** (52-byte entries) immediately after the invite arrives and
   before the game polls. Entry `+0x28` is the tag (expect `0x10b`), `+0x2c` is
   a pointer to the 16-byte body, `+0x30` is the length. The first 8 bytes of
   the body are the room id the sender wants you to join - compare it against
   the room id the stub actually created.
5. Breakpoint **`0x00AD3894`** if you want to catch the assert with the room
   object in `r?` - but the TTY line is usually enough.

## Tooling note

`tools/eboot_analysis/` now holds the raw-disassembly helpers used here
(`eb.py` VMA reader, `scan_anchor.py` for the r2->anchor->displacement global
idiom, `scan_imm.py` for `lis`+`addi`/`ori` absolute addresses, `scan_bl.py`
for call sites, `fnstart.py`, `fnglobals.py`). They need only the decrypted
EBOOT and no Ghidra project, so they work while the Ghidra project is locked -
and `scan_anchor.py` in particular answers "who else touches this global",
which Ghidra's reference manager misses for this binary's addressing style.
