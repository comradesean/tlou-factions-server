# SessionManager receive-dispatch audit: unsent opcodes, ownership gap, and RoomCreate field corrections

Full instruction-level audit of `FUN_00ad7604` (SessionManager receive-dispatch,
vtable `+0x4` @ `0x00ad7604`) and every sender/handler it touches, cross-checked
against `powerpc64-linux-gnu-objdump` raw disassembly, Ghidra decompilation, and
the project's own live capture log (`captures/tcp_catch.log`).

Binary: `EBOOT.elf`, SHA256 `2e44426f00fbb13f192548efa27b7101fb71807d3772ee6e3807ff5053fa94ff`
(re-verified this pass, matches `docs/tooling.md`).

VMA→file mapping used for objdump: LOAD segment 0 maps file offset `0` to VMA
`0x10000`, size `0x11eac68`, so `file_off = VMA - 0x10000`. `objdump -d
--start-address=<VMA>` on the ELF works directly.

---

## 1. The dispatch chain is exactly 11 cases, and it is exhaustive

`FUN_00ad7604` spans `0x00ad7604`–`0x00ad84c8` (`blr`). It is a flat
`if/else-if` chain on the 4-byte opcode at the head of the receive buffer
(`this+0x24058`, cursor at `this+0x24054`). No jump table, no second dispatcher.

Every opcode literal in the function, with its own size gate (all verified by
raw disasm this pass):

| VMA | opcode | size gate | bytes consumed |
|---|---|---|---|
| `0xad778c` | `0x131` Member | `cmplwi r0,159` then `160 + count*104` | `160 + roster_count*104` |
| `0xad7ac0` | `0x132` RoomJoined | `cmpwi r0,119` | 120 |
| `0xad7c5c` | `0x134` RoomLeave | `cmpwi r0,23` | 24 |
| `0xad7d24` | `0x136` RoomSearch | `cmplwi r0,15` then `16 + n*56` | `16 + num_entries*56` |
| `0xad7f28` | `0x138` RoomSearchResult | `cmpwi r0,15` | 16 |
| `0xad7fc4` | `0x139` Kickout | `cmpwi r0,15` | 16 |
| `0xad808c` | `0x13b` (per-member blob) | `cmpwi r0,79` | 80 |
| `0xad817c` | `0x13d` (owner-id set) | `cmpwi r0,15` | 16 |
| `0xad825c` | `0x13f` OwnerChanged | `cmpwi r0,15` | 16 |
| `0xad82d4` | `0x141` UpdatedAttrFlags | `cmpwi r0,15` | 16 |
| `0xad838c` | `0x144` (room-name confirm) | `cmpwi r0,143` | 144 |

Confirms the 11 documented in `docs/protocol/session_manager_and_matchmaking.md`.
**Confidence: high.** Nothing new was hiding in the dispatcher.

### 1a. DANGER: an unrecognised opcode wedges the connection forever

`0xad838c: cmpwi cr7,r3,324` / `bne cr7,0xad8474`. `0xad8474` is
`li r3,0; ... blr` — it returns **without advancing the cursor and without
consuming anything**. The poll loop re-enters at `0xad7778` on the next tick,
reads the same 4-byte opcode from the same buffer position, and returns 0 again.

**Any opcode the stub sends that is not one of the 11 above permanently
deadlocks the SessionManager receive path** (buffer never drains; it fills to
4096 and then `recv` is called with length 0 forever). This includes a stray
`0x12e`/ServerHello, `0x135`, `0x137`, `0x13a`, `0x140`, `0x142`, `0x143`,
`0x145`, `0x146`. `tools/session_manager_stub.py` currently sends only opcodes
from the legal set, so this is a landmine rather than an active bug — but it is
the single easiest way to break the connection while experimenting.

**Confidence: high** (direct branch-target read).

---

## 2. THE HEADLINE: the client never learns it is the room host

### Evidence chain

**(a) `room_obj+0x19F4` is the "I am the room owner/host" boolean.**

`FUN_00ad6a34` (`0x13e`/Promote sender, vtable `+0x20`) at `0xad6ab4`–`0xad6c08`:

```
r11 = param_3 & 0xff                 ; requested promote/demote
r0  = *(u8*)(room_obj + 0x19F4)      ; current owner flag
if (r11 != 0) {                       ; want to become owner
    if (r0 != 0) return -1;           ;   already owner -> reject
    *(u8*)(room_obj+0x19F4) = 1;      ;   0xad6af0
} else {                              ; want to relinquish
    if (r0 == 0) return -1;           ;   already not owner -> reject
    *(u8*)(room_obj+0x19F4) = 0;      ;   0xad6c04
}
... send 0x13e (16 bytes)
```

This is an unambiguous "am I the owner" flag with a matched
promote/demote guard.

**(b) The RoomCreate sender clears it, unconditionally.**

`FUN_00ad5b78` (vtable `+0x10`) is confirmed to be the `0x12f`/RoomCreate sender
(`li r0,303` at `0xad5c38`, `_opd_FUN_00acb93c(this+0x25060, buf, 0xe8=232, 1)`
at `0xad5fac`). Its second argument `r4` is the room object (`mr r31,r4` at
`0xad5b84`). At `0xad5c98`:

```
ad5c6c:  li   r27,0
ad5c98:  stb  r27,6644(r31)      ; room_obj+0x19F4 = 0
```

Unconditional, on the straight-line RoomCreate path.

**(c) The ONLY inbound message that can set it is `0x13f`/OwnerChanged — which
this project's stub has never sent.**

Complete list of writers to `room_obj+0x19F4` in the whole binary (from a full
`objdump -d` sweep for displacement `6644`):

- `0xad1f58` — internal
- `0xad5c98` — RoomCreate sender, sets **0** (above)
- `0xad6af0` / `0xad6c04` — Promote sender, local optimistic toggle (only
  reachable from an explicit in-UI promote/demote action, and it *rejects* the
  promote when the flag is already the requested value)
- `0xad82cc` — **the `0x13f` receive-dispatch case**

Readers (external to the SessionManager module, i.e. the game/lobby layer):
`0x397e08`, `0x3cab10`, `0x3cb3d0`.

So on the solo-host path: RoomCreate zeroes the flag, nothing ever sets it, and
`_opd_FUN_003ca9d0`'s room state machine (`0x3cab10`) takes the
"not owner" branch (`beq cr7,0x3caffc`) skipping its whole owner-side block,
while `FUN_003cb204`'s member-removal path (`0x3cb3d0`) skips its
`_opd_FUN_00ad124c` owner bookkeeping.

**Confidence: high** on the mechanism (all four writers and all three readers
read directly off disassembly). **Confidence: medium-high** that this is a
direct cause of the "Starting Game…" stall — the gated blocks were not fully
traced to a state transition.

### The fix (ready to apply)

`0x13f` is 16 bytes: `opcode(4) | is_owner_byte(1) | unread(3) | room_id(8)`,
and its handler (`0xad8264`–`0xad82d0`) searches the 4 room slots for
`*(s64*)(room_obj+0x10) == wire[8..15]` before writing
`*(u8*)(room_obj+0x19F4) = wire[4] & 1`.

**Sequencing constraint: `0x13f` must be sent AFTER `Member`**, because
`room_obj+0x10` is only set by Member's handler (`std r9,16(r29)` at
`0xad780c`, sourced from Member wire offset 16). Sending it before Member means
the 4-slot search finds nothing and the message is silently swallowed.

```python
OWNER_CHANGED_OPCODE = 0x13f

def build_owner_changed(room_id, is_owner=1):
    """0x13f NetMatchmakingOwnerChanged, 16 bytes.
    Handler @0xad825c: finds the room whose room_obj+0x10 == room_id,
    then room_obj+0x19F4 = payload[4] & 1.  MUST follow Member."""
    body = bytearray(16)
    struct.pack_into(">I", body, 0, OWNER_CHANGED_OPCODE)
    body[4] = is_owner & 1
    body[8:16] = room_id
    return bytes(body)
```

...and in the `RoomCreate` branch, append it to the same write:
`conn.sendall(member + build_owner_changed(room_id, 1))`.

---

## 3. Sequencing violation: RoomJoined-before-Member creates a phantom 2nd member

### `FUN_00ad33d8` is first-registration-wins, permanently

`_opd_FUN_00ad33d8(room_obj, member_local_80B, is_local, is_owner, ...)`
@ `0xad33d8`. Member slots live at `room_obj + i*0x180 + 0x668`, 12 of them;
`slot+0xE0` = occupied byte, `slot+0xE8` = member_id.

```
; 0xad3430 - dedupe pass
for i in 0..11:
    slot = room + i*0x180 + 0x668
    if (*(u8*)(slot+0xE0) != 0) {
        if (FUN_00e459bc(slot, member_local+4) == 0)   ; NpId compare, 16 bytes
            return *(u32*)(slot+0xE4);                 ; <-- EARLY RETURN, nothing updated
    }
; 0xad347c - allocate pass (only reached if no NpId match)
...
; 0xad37b8
if (is_local != 0)  *(u32*)(room_obj+0x19EC) = *(u32*)(new_slot+0xE8);  ; my member id
if (is_owner != 0)  *(u32*)(room_obj+0x19F0) = *(u32*)(new_slot+0xE8);  ; owner's member id
```

The dedupe key is the NpId only. On a hit it returns immediately and **never
touches `is_local`/`is_owner`/`member_id`**. First registration of a given NpId
wins forever.

Also at `0xad34a4`:
```
if ((is_local & 0xff) == 0)
    *(u32*)(slot+0xF0) = g_singleton->vtable[0x10](g_singleton, npid);
```
i.e. **the client opens an NP signaling connection for every member registered
with `is_local == 0`.**

### What the two handlers pass

- `0x131`/Member (`0xad795c`–`0xad79d0`): `is_owner = (entry.member_id ==
  header.owner_ref_id)`, `is_local = (entry.member_id == header.local_ref_id)` —
  computed per entry by XOR + `srdi 63`.
- `0x132`/RoomJoined (`0xad7bdc`/`0xad7be8`): `li r5,0; li r6,0` — **is_local
  and is_owner are hardcoded 0.**

### The bug, confirmed against the live wire

`tools/session_manager_stub.py`'s solo-host branch sends `RoomJoined + Member`
in one write, **RoomJoined first**, with:
- RoomJoined offset 16..31 = the recipient's **own** NpId (`"mgnomad2"` in
  `captures/tcp_catch.log` line ~82008)
- Member entry 0 offset 0..15 = **all zeros** (the deliberate
  `member_id != local_ref_id` self-skip)

Since the two NpIds differ, the dedupe never fires and the client ends up with
**two occupied member slots for a one-player room**:

| slot | NpId | member_id | is_local | is_owner | side effect |
|---|---|---|---|---|---|
| 0 (from RoomJoined) | the host's real NpId | 0 | 0 | 0 | signaling connection opened **to itself** |
| 1 (from Member) | all zeros | 1 | 1 | 1 | sets `+0x19EC`/`+0x19F0` |

Consequences, each mechanically traceable:

1. `SCE_NP_SIGNALING_ERROR_OWN_NP_ID` on the **solo-host** path, not just
   find-match — slot 0 has `is_local == 0` and the host's own NpId, which is
   exactly the `vtable[0x10]` resolve above. This matches the live errors the
   project has been chasing and previously attributed only to the find-match
   roster.
2. `_opd_FUN_00ad0fd0(room)` (highest occupied index + 1) and
   `_opd_FUN_00ad1024(room)` (true occupied count) both return **2** for a solo
   host. `FUN_003cb528` gates its whole body on `1 < _opd_FUN_00ad0fd0(...)`,
   i.e. the game genuinely believes there are two players.
3. The member with the real NpId is flagged neither local nor owner, so any
   code that looks up "the player named X" finds a non-local, non-owner record.

### Recommended change (untested, but evidence-backed)

**On the solo-host RoomCreate path, send `Member` alone — drop `RoomJoined`.**

Member's handler is self-sufficient for room creation: it takes the room pointer
straight from wire offset 8 (no id-gate search), writes `room_obj+0x10` (room
id) and `room_obj+0x1F8` (capacity), registers the roster with correct
local/owner flags, and then runs the completion latch at `0xad79ec`:

```
if (*(u8*)(room_obj+0xAC) == 0) {
    if (*(s64*)(room_obj+0x10) != 0) {
        *(u32*)(room_obj+0xB0) = 0;      ; error code = 0
        *(u32*)(room_obj+0xB4) = 1;      ; success
        room_obj->vtable[0x1c](room_obj);  ; <-- "room create completed" callback
    } else {
        *(u32*)(room_obj+0xB4) = 0;
        *(u32*)(room_obj+0xB0) = -1;     ; error
    }
    *(u8*)(room_obj+0xAC) = 1;           ; ONE-SHOT LATCH
}
```

This is the actual "RoomCreate succeeded" signal, and it lives in Member, not
RoomJoined. Note the latch: **if the first Member the client processes carries a
zero room id at wire offset 16, the client latches `+0xB0 = -1` (error) and
`+0xAC = 1` and will never re-evaluate** — no later Member can fix it.
(The stub already sends a nonzero id, so this is a guard-rail, not a live bug.)

`0x132`/RoomJoined's real role is "some *other* player joined the room you are
in" — hence the hardcoded `is_local=0, is_owner=0`. Sending it about yourself is
semantically wrong.

**Confidence: high** on the mechanism and on the phantom-member outcome
(disassembly + live wire bytes). **Confidence: medium** that removing RoomJoined
is a net improvement — it has never been tested, and the id-gate at `0xad7b14`
was historically credited with fixing "Lobby Server Error". That credit is
probably misattributed: the original bug was the client's *timeout* on getting
no reply at all, which Member alone also satisfies.

---

## 4. Part 1 corrections: `0x12f` RoomCreate is substantially mis-mapped

Full field map of `FUN_00ad5b78`'s send buffer (base `r1+144`, 232 bytes; wire
offset = `r1_offset - 144`). Every store to the buffer was enumerated
exhaustively from the disassembly, then checked against 30 live RoomCreate
captures in `captures/tcp_catch.log`.

| wire off | width | source | evidence |
|---|---|---|---|
| 0x00 | 4 | `0x12f` | `stw r0,144(r1)` @ `0xad5c40` |
| 0x04 | 4 | **NEVER WRITTEN — uninitialised stack** | no store to `148(r1)` anywhere in the function |
| 0x08 | 4 | **`room_obj` pointer** | `stw r29,152(r1)` @ `0xad5f34`, `r29 = r4 = room object` |
| 0x0c | 4 | `*(u32*)(room_obj+0x0C)` | `lwz r0,12(r31)` / `stw r0,156(r1)` @ `0xad5f30` |
| 0x10 | 4 | region/language (`"us\0\x01"`) | `stw r0,160(r1)`, built from `sceNpManagerGetAccountRegion`-shaped calls |
| 0x14 | 4 | `*(u32*)(room_obj+0xE8)`, optionally `\|= 0x40000000` | `0xad5c44`/`0xad5c4c`/`0xad5c5c` |
| 0x18 | 2 | 0 | `sth r24,168(r1)` @ `0xad5c94` |
| 0x1a | 2 | 0 | `sth r24,170(r1)` |
| 0x1c | 2 | caller arg (`0xffff` or `0x0000` live) | `sth r27,172(r1)` @ `0xad5c60` |
| **0x1e** | 2 | **NEVER WRITTEN — uninitialised stack** | gap between `172(r1)` (2 bytes) and `176(r1)` |
| 0x20 | 2 | float→int, live `0x03e8` | `stfiwx`/`sth r0,176(r1)` |
| 0x22 | 2 | float→int, live `0x03e8` | `sth r0,178(r1)` |
| **0x24** | 2 | **max players / capacity** | `sth r23,180(r1)` **and** `stw r23,504(r31)` = `room_obj+0x1F8` @ `0xad5f80` |
| 0x26 | 1 | `*(u8*)(room_obj+0x19F8)` | `stb r11,182(r1)` |
| 0x27 | 1 | 0 or 4 | `stb r27/r0,183(r1)` |
| 0x28 | 128 | room name, `strcpy` | `_opd_FUN_00e45b10(r1+184, room_obj+0x18)` @ `0xad5f74` |
| 0xa8 | 64 | verbatim copy of `room_obj+0x19FC .. +0x1A3B` | byte-by-byte loop `0xad5d30`–`0xad5f2c` into `r1+312` |

### 4a. `create_id` at offset 4 does not exist

`protos/0x12f_room_create.ksy` declares an 8-byte `create_id` at offset 4 and
calls it "high-confidence". It is not: offset 4..7 is never written by the
sender. The live captures prove it directly — the same client emits
`01 27 23 d8` at offset 4 in one session and `00 00 00 00` in the next, with
everything else identical. Classic uninitialised-stack tell.

`tools/session_manager_stub.py` reads `room_id = chunk[4:12]`, which is
therefore `4 bytes of stack garbage || the room pointer`. It happens to be
nonzero (satisfying the `m_roomId != 0` assert), so nothing visibly broke — but
the field is a fiction.

**The 8-byte room id is the server's to choose.** Nothing in RoomCreate carries
one. Recommend `room_id = os.urandom(8)` (or a counter) on the solo-host path,
exactly as the find-match path already does.

### 4b. Offset 8 is the room-object pointer — stop hardcoding `ROOM_PTR`

`stw r29,152(r1)` with `r29 = r4` (the room object). Live proof across the
capture log:

```
comradesean:  00 00 01 2f 01 27 23 d8 | 01 38 3b d8 | 00 00 00 09
mgnomad2:     00 00 01 2f 00 00 00 00 | 01 38 7f 58 | 00 00 00 12
```

`0x01383bd8` is **exactly** the value the stub hardcodes as `ROOM_PTR`, which
was obtained by a live RPCS3 debugger breakpoint at `FUN_00ad5ab0`. The second
client's room object is at `0x01387f58` — a different address.

Consequences:
- The "room_ptr hazard" documented in `protos/0x131_member.ksy` and
  `docs/protocol/0x131_member.md` is **solved**: read it off RoomCreate wire
  offset 8 per connection. No debugger, no staleness after an RPCS3 restart.
- The find-match pairing path currently sends comradesean's `ROOM_PTR` to
  *both* paired clients. For the non-owning client that is a wild pointer
  dereferenced through an unchecked vtable call. This is a plausible,
  previously-unidentified cause of the find-match failures. (Find-match has no
  RoomCreate to read from; `0x130`/RoomJoin's offset 8 is the same kind of
  pointer and is the right source there.)

Ready-to-apply change in the `ROOM_CREATE_OPCODE` branch:

```python
room_ptr = struct.unpack(">I", chunk[8:12])[0]   # client's own room object
room_id  = os.urandom(8)                          # server-chosen, must be nonzero
max_players = struct.unpack(">H", chunk[0x24:0x26])[0] or 8
```
plus threading `room_ptr` through `build_member` instead of the module-level
`ROOM_PTR` constant.

### 4c. `max_players` is read from the wrong offset

The stub reads `chunk[0x1e:0x20]`; that span is never written by the sender. All
30 captures show `00 0a` or `00 00` there — leftover stack, and the `or 10`
fallback masked it. The real capacity is at **offset 0x24**, live-constant
`00 08` in every capture, and it is the same value the client writes into
`room_obj+0x1F8` itself.

So the stub has been telling the client capacity=10 while the client's own
RoomCreate said 8. `FUN_00ad33d8` compares the occupied-slot count against
`room_obj+0x1F8` (`0xad38c8`) and takes a reject path when the count exceeds
it, so an over-large value is permissive rather than fatal — but it is wrong,
and combined with the phantom member (§3) it is one of the things keeping the
room's player accounting incoherent.

### 4d. `map_id` (offset 0x0c)

Now sourced: it is `*(u32*)(room_obj+0x0C)`, copied verbatim. This neither
confirms nor refutes the map-vs-team dispute in
`2026-08-16-map-id-vs-team-confound.md`, but it does give the next investigator
a concrete target — find the writer of `room_obj+0x0C`, not the wire field.
Live values seen: `0x02`, `0x09`, `0x12`, `0x13`.

---

## 5. Part 1 corrections: the opcode/size table's tail is shifted by 2, and
## `0x143`/`0x144` are the room-NAME pair, not "room flags"/"host rank"

### `_opd_FUN_00e45b10` is `strcpy`

Decompiled this pass: word-at-a-time NUL scan (`(x & 0x7f7f7f7f) + 0x7f7f7f7f |
x | 0x7f7f7f7f`) with a byte-wise tail. Two arguments, no length. It is
`strcpy`, not a sized `memcpy`.

### `0x144`'s handler copies a STRING into `room_obj+0x18`

`0xad8400`:
```
addi r3,r3,24        ; matched_room + 0x18
addi r4,r31,16       ; wire + 16
bl   0xe45b10        ; strcpy
```

### `room_obj+0x18` is the room NAME

`FUN_00ad6f28` (`0x143` sender, vtable `+0x3c`) builds it first:
```c
uVar2 = _opd_FUN_00ada1c8(0);                      // timestamp
_opd_FUN_00e46670(room+0x18, <format>, <npid_obj>+0x20, uVar2);  // sprintf-like
_opd_FUN_00e45b10(local_128, room+0x18);           // strcpy into the send buffer
_opd_FUN_00a0e324(0x143);
_opd_FUN_00acb93c(this+0x25060, buf, 0x90, 1);     // 144 bytes
```
`<npid_obj>+0x20` is the same NpId field `ClientHello` copies from. The result is
`"<npid>.<unix-timestamp>"` — **byte-identical to the string RoomCreate sends at
wire offset 0x28**, which `FUN_00ad5b78` also produces by `strcpy`ing
`room_obj+0x18`. `FUN_00ad54e0` (vtable `+0x40`) is the same sender without the
name rebuild.

### Therefore the declared table is offset by 2 from index 24 onward

| declared idx | declared name | declared size | real wire opcode | real size |
|---|---|---|---|---|
| 21 | `SetRoomFlags` | 16 | `0x142` | 16 + n*2 |
| **22** | `UpdatedRoomFlags` | 16 | **none — phantom** | — |
| **23** | `HostRank` | 16 | **none — phantom** | — |
| 24 | `SetRoomName` | **144** | **`0x143`** | **144** |
| 25 | `UpdatedRoomName` | **144** | **`0x144`** | **144** |
| 26 | `Ping` | **4** | `0x145` | **4** |
| 27 | `ClientHello2` | **8** | `0x146` | **8** |

All four sizes match exactly, and the two already-known tail corrections
(`Ping` = `0x145`, `ClientHello2` = `0x146`, both live-confirmed) fall out of
the *same* 2-entry shift instead of being two unexplained one-offs. Two
independent signals (declared size, and the `strcpy`-a-name semantics) agree.

**Confidence: high.**

Practical effect on the stub: none functionally — the `0x144` reply it added on
2026-08-16 echoes the client's own 128-byte payload back, which for a room-name
confirmation is exactly the right behaviour. But it should be renamed, and the
"128-byte per-member rank table" reading in `docs/protocol/session_manager_and_
matchmaking.md` rows 22–23 and in `protos/0x143_*.ksy`/`protos/0x144_*.ksy` is
wrong. Also: the reply **must** stay NUL-terminated within 128 bytes or the
`strcpy` at `0xad8410` overruns `room_obj+0x18` into `room_obj+0x98`.

---

## 6. Part 1 corrections: `0x140`/`0x141` carry a u16, and offset 6 is garbage

`FUN_00ad62dc` (`0x140` sender, vtable `+0x2c`), buffer base `r1+112`:
```
ad636c:  stw  r0,112(r1)      ; offset 0  = 0x140
ad6370:  std  r9,120(r1)      ; offset 8  = room_obj+0x10 (room id, 8 bytes)
ad6374:  sth  r28,116(r1)     ; offset 4  = (u16)param_3      <-- 2 bytes only
ad63a8:  li   r5,16           ; 16 bytes sent
```
**Offset 6..7 is never written.** The `0x141` handler agrees: `lhz r3,4(r29)` at
`0xad82ec`, zero-extended to a `stw` into `room_obj+0x1F0` at `0xad8354`.

This retires the "20-bit packed bitmask" reading in
`docs/protocol/session_manager_and_matchmaking.md` row 19. The four live values
`0x00012f78 / 0x0000197c / 0x0001fbe0 / 0x0001fba0` decompose as
`(0x0001, 0x2f78) / (0x0000, 0x197c) / (0x0001, 0xfbe0) / (0x0001, 0xfba0)` —
**a u16 field taking only 0 and 1, followed by stack garbage.** The apparently
random 20-bit spread was entirely in the garbage half, which is why it never
resolved into a sensible bitmask. The `0x40` single-bit difference between the
last two values was coincidence in uninitialised memory.

The stub's echo of `chunk[4:8]` preserves the meaningful u16 correctly (and
echoes garbage in 6..7, which the client ignores), so behaviour is accidentally
fine. The `.ksy` files and the "several settings packed into one bitmask" note
are wrong.

**Confidence: high.**

---

## 7. Part 1: everything else in the dispatcher, verified

Field-level confirmations from this pass (all raw-disasm):

- **`0x131` Member.** Header: `+0` opcode, `+4` unread, `+8` room_ptr (u32,
  `lwz r24,8(r28)` @ `0xad77d4`, immediately `vtable[0x18]` called on it with no
  null check), `+12` owner_ref_id (u16), `+14` local_ref_id (u16), `+16` room id
  (8 bytes → `room_obj+0x10`), `+24` capacity (u16 → `room_obj+0x1F8`), `+26`
  roster_count (u16), rest of the 160-byte header unread. Per entry (104 bytes):
  `+0..35` the 36-byte block handed to `FUN_00ad33d8` as `param_2+4` (first 16
  bytes are the NpId, per the `FUN_00e459bc` dedupe), `+36` member_id (u16),
  `+38` byte → member struct `+0x40`, `+39` byte, `+40..103` name buffer
  (pointer stored, not copied by the dispatcher). **Matches
  `protos/0x131_member.ksy` exactly.** The only change needed is the room_ptr
  "do not guess this" warning, which §4b resolves.
- **`0x132` RoomJoined.** 120 bytes; `+8` id gate compared against
  `room_obj+0x10` at `0xad7b14`; `+16..51` = 18 u16 attribute block;
  **`+52` = member_id (u16)** (`lhz r0,36(r29)` where `r29 = wire+16`) — the
  `.ksy` currently lumps `+52..55` into an unnamed `flags_field`; `+54`, `+55`
  bytes; `+56..119` name buffer. `is_local`/`is_owner` hardcoded 0.
- **`0x134` RoomLeave.** 24 bytes; `+8` room id; **`+16` member_id (u16)**
  (`lhz r4,16(r9)` @ `0xad7cc8`) → `FUN_00ad0d4c` lookup → `FUN_00ad3190`
  removal. Confirms the doc and pins the member_id offset.
- **`0x136` RoomSearch.** `+8` is a **raw client-side pointer** (`lwz r11,8(r9)`
  @ `0xad7d70`, then `*(u32*)(ptr+0xA8) = 0`, `*(u8*)(ptr+0xA4) = 1`) — same
  class of hazard as Member's room_ptr. `+12` = num_entries (u32), entries are
  56 bytes. Not sendable without a live pointer.
- **`0x139` Kickout.** 16 bytes; room lookup by `+8`; `room->vtable[0x2c]()`,
  `room_obj+0x10 = 0`, `FUN_00ad32c4` teardown, `room->vtable[0x20]()`.
- **`0x13b`.** 80 bytes; `+4` member_id (u16), **`+6` = a length byte**,
  `+8` room id, `+16..` blob. Handler: `FUN_00ad0d4c(room, member_id)` →
  `*(u32*)(member+0xF8) = wire[6]`, `memcpy(member+0xFC, wire+16, wire[6])`.
  The length byte at offset 6 is new (the `.ksy` should cap it at 64).
- **`0x13d`.** 16 bytes; `+4` u16 → `room_obj+0x19F0`; then
  `room->vtable[0x34]()`. **`room_obj+0x19F0` is now identified**: it is the
  **owner's member id** — `FUN_00ad33d8` writes it from the roster entry whose
  `is_owner` flag is set (`0xad37dc`), and `FUN_00ad0d98` is a dedicated
  "find the member whose id == `room_obj+0x19F0`" lookup used by
  `FUN_003cb528`. So `0x13d` is "the room owner is now member X", i.e. a second,
  complementary half of ownership signalling. Its declared name
  `MemberUpdatedData` is wrong; `OwnerMemberChanged` fits.
  (`room_obj+0x19EC`, four bytes earlier, is the **local** player's member id,
  written from `is_local`.)
- **`0x141`.** See §6.
- **`0x144`.** See §5.

`FUN_00ad0d4c` @ `0xad0d4c` verified: 12 slots, stride `0x180`, base `+0x668`,
occupied byte `+0xE0`, member id `+0xE8`.

---

## 8. The unsent-opcode list, ranked

Stub currently sends: `0x12e`, `0x131`, `0x132`, `0x138`, `0x141`, `0x144`.
Client can consume 11. **Six are never sent.**

### 1. `0x13f` OwnerChanged — HIGH, send it
Trigger: after `Member`, on the RoomCreate reply path (and to whoever becomes
host on the find-match path). State fed: `room_obj+0x19F4`, the host boolean,
which RoomCreate explicitly clears and nothing else can set. Sketch in §2.
Ordering: strictly after Member.

### 2. `0x13d` "OwnerMemberChanged" — MEDIUM-HIGH, send it
16 bytes: `opcode | owner_member_id(u16 @4) | pad(2) | room_id(8)`. Writes
`room_obj+0x19F0` and then fires `room->vtable[0x34]()` — a client-side
notification `Member` does *not* fire (Member sets `+0x19F0` silently as a side
effect of the `is_owner` flag). Sending it makes the ownership designation
explicit and triggers the callback. Same ordering constraint (after Member).
```python
def build_owner_member(room_id, owner_member_id=1):
    body = bytearray(16)
    struct.pack_into(">I", body, 0, 0x13d)
    struct.pack_into(">H", body, 4, owner_member_id)
    body[8:16] = room_id
    return bytes(body)
```

### 3. `0x13b` per-member blob — LOW-MEDIUM, speculative
80 bytes, delivers up to 64 bytes of opaque data onto a member record
(`member+0xF8` = length, `member+0xFC` = payload). No reader of `member+0xFC`
was traced this pass, and there is no client→server message that obviously
supplies the data, so there is nothing principled to put in it yet. Safe to
send (well-formed, len=0) but unlikely to change anything.

### 4. `0x134` RoomLeave — situational, correctness not stall
The correct way to tell a client that another member left. Only relevant once
multi-member rooms work; the stub has no member-departure event today.

### 5. `0x136` RoomSearch — BLOCKED
Would deliver an actual room list, but wire offset 8 is a raw client-side
pointer to the search-results object, which the server has no way to know
(no client→server message carries it). Not sendable without a live debugger
read. Note this is *the* mechanism a real browse/find-match would use, so it is
worth revisiting if the pointer's provenance can be found.

### 6. `0x139` Kickout — do not send
Tears the room down. Only useful as a deliberate eviction.

### Reverse direction: client→server messages the stub ignores

- `0x133` room abandon — confirmed fire-and-forget, correctly ignored.
- `0x135` find-match broadcast — handled.
- `0x13a` telemetry — correctly ignored.
- `0x145` Ping — the client sends it on its own timer from inside
  `FUN_00ad7604` itself (`li r0,325` at `0xad76c4`, guarded by a float
  deadline compare against `this+0x24058-0x8` region); no reply is read
  anywhere. Correctly ignored.
- `0x146` ClientHello2 — `Init()` sends and moves on. Correctly ignored.
- `0x130` RoomJoin, `0x13c`, `0x13e` Promote, `0x142` — the stub never receives
  these in practice. `0x13e`/Promote is the one to watch: if a client ever sends
  it, the correct reply is `0x13f` echoing the requested flag, since the sender
  has *already* set `room_obj+0x19F4` optimistically and expects confirmation.

No reply-wait/timeout loop was found on any client→server sender in this family
— every sender is `build buffer; _opd_FUN_00acb93c(...); return`. The client's
timeouts are elsewhere (lobby-flow state machine), which is consistent with the
"Lobby Server Error" being a lobby-level timeout rather than a per-message one.

---

## 9. `NET_SM_SERVER_LOBBY`: the previous identification does not hold up

`2026-08-16-net-sm-server-lobby-dispatch.md` identifies `_opd_FUN_001594bc` as
`NET_SM_SERVER_LOBBY`'s handler and describes it as popping a bounded
producer/consumer queue whose producer was never found.

Raw disassembly of `0x1594bc` shows the call it is built on cannot be what the
decompile claims:

```
1594c8:  addi r29,r1,112
1594d8:  li   r7,2
1594e4:  mr   r3,r29
159500:  bl   0x7f4540        ; r4, r5, r6 are NEVER SET in this function
```

Ghidra types `FUN_007f4540` as taking five parameters and storing `param_2`,
`param_3`, `param_4` into the output struct — but `r4`/`r5`/`r6` hold whatever
the caller left behind. A genuine 5-argument call cannot look like this.

Either Ghidra's signature for `FUN_007f4540` is wrong (most likely — the
`0x0006xxxx`/`0x007fxxxx` helpers it chains into, `FUN_000d2184`,
`FUN_009ef28c`, `FUN_000c7400`, look like a generic reflection/iterator
family with bitset membership tests, not a message queue), or `0x1594bc` is
not `NET_SM_SERVER_LOBBY`'s handler at all.

**I did not find the queue producer, and I now doubt the queue exists as
described.** Recommend re-deriving the state-table entry from
`0x0125cc00` before spending more static budget here — and treating the
"producer never found" framing as unconfirmed rather than as an open lead.
This does not affect anything else in this note.

**Separately, and more promising**: `_opd_FUN_003ca9d0` is a real 9-state
machine keyed on `room_obj+0x1a4c` (jump table at `0x3caa9c`, bounds-checked
`< 9`), and `0x3cab10` — inside one of its states — is a `room_obj+0x19F4`
"am I the host" gate that skips a large block when false. Given §2, **that gate
is currently always false on the solo-host path.** Decompiling the nine states
(the jump table is relative: `target = base + *(s32*)(base + state*4)`) is the
concrete next step, and it should be done *after* trying the `0x13f` fix, since
if the fix works the question is moot.

---

## 10. Summary of proposed stub changes (not applied — see the hands-off rule)

In `tools/session_manager_stub.py`'s `ROOM_CREATE_OPCODE` branch:

1. `room_ptr = struct.unpack(">I", chunk[8:12])[0]` — per-connection, replaces
   the hardcoded `ROOM_PTR`. Thread it into `build_member`.
2. `max_players = struct.unpack(">H", chunk[0x24:0x26])[0] or 8` — was `0x1e`.
3. `room_id = os.urandom(8)` — RoomCreate carries no id; offset 4 is garbage.
4. Drop the `build_room_joined(...)` call on this path; send `Member` alone.
5. Append `build_owner_changed(room_id, is_owner=1)` to the same write, after
   Member.
6. Optionally append `build_owner_member(room_id, MEMBER_ID)` (`0x13d`).

Recommended as **one change at a time**, in the order 1 → 2 → 5 → 4, so each is
individually attributable. (1) and (2) are strictly-correct fixes with live
evidence; (5) is the headline experiment; (4) is the riskiest because it removes
a message that has been in the flow since the first successful room create.
