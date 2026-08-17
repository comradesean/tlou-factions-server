# The per-member 32-byte data blob: where lobby RANK/loadout comes from, and what `0x142` really is

Instruction-level trace of the lobby's per-member display data, answering
"why does only the local player's RANK render". Everything below was read off
`powerpc64-linux-gnu-objdump` raw disassembly of the decrypted EBOOT
(SHA256 `2e44426f00fbb13f192548efa27b7101fb71807d3772ee6e3807ff5053fa94ff`,
`file_off = VMA - 0x10000`) and cross-checked against live bytes in
`captures/tcp_catch.log`.

**Headline: the client already ships the data. The server just never gives it
back.** Every per-member display value in the lobby (rank-shaped u16 stats,
loadout selection ids, a title/badge index) comes from a single 32-byte
per-member blob. For the local player the client reads its own local copy, so it
always renders. For a remote player it reads `member_slot+0xFC`, which is written
by exactly two wire messages — `0x13b`, and `0x131`/Member's *per-entry offset
39/40* — and the stub currently sends a zero length in both. The getter then
returns `NULL` and every consumer bails or keeps stale values.

---

## 1. `0x142` is `NetMatchmakingHostRank`, and it is fire-and-forget

### Sender: `FUN_00ad5ffc`, SessionManager vtable `+0x38`

`li r0,322` @ `0xad60c4`. Signature
`FUN_00ad5ffc(this, room_obj, const u16 *values, u32 count)`.

```
ad6074:  ld   r11,16(r4)          ; room_id = room_obj+0x10
ad6078:  cmpdi r11,0
ad6088:  stb  r0,208(r4)          ; if room_id == 0: room_obj+0xD0 = 1, return 0  (deferred, NOT sent)
ad6090:  slwi r28,r6,1            ; r28 = count*2
ad60a8:  addi r28,r28,16          ; total size = 16 + count*2
ad60c4:  li   r0,322              ; 0x142
ad60d4:  stw  r0,0(r29)           ; wire[0]   = opcode
ad60dc:  sth  r6,4(r29)           ; wire[4]   = (u16)count
ad60d8:  std  r11,8(r29)          ; wire[8]   = room_id (8 bytes)
ad60e0:  bl   0xe3e064            ; memcpy(wire+16, values, count*2)
ad60ec:  bl   0xad5640            ; byteswap/serialize pass over the buffer
ad610c:  bl   0xacb93c            ; send(this+0x25060, buf, 16 + count*2, 1)
```

**Wire offset 6:7 is never written — uninitialised stack.** That is the whole
explanation for the `00 60` the task brief flagged as "=96?": live captures show
`00 00` in one variant and `00 60` in another with everything else identical.

Live confirmation (`captures/tcp_catch.log`):

```
line 60487:   00 00 01 42 | 00 00 | 00 00 | 01 27 23 d8 01 38 3b d8              (count=0, 16 bytes)
line 102209:  00 00 01 42 | 00 01 | 00 60 | 01 27 23 d8 01 38 3b d8 | 00 02      (count=1, 18 bytes)
```

So the trailing `00 02` is **not** a member id — it is `values[0]`, one u16 per
*local* player on the sending console.

### What the values are: `FUN_0039b720` (call site `0x39b964`)

```
39b720:  fn(r3 = obj)
39b744:  obj->vtable[0](obj)                 ; bool gate; false -> return, nothing sent
loop r28 = 0..7:                             ; 8 local-player slots
   player = 0
   if (*(u8*)(0x013835c0 + 25) != 0) player = 0x0137d700 + r28*0x920 + 0x40
   skip if player->vtable[0xC]() != 0
   skip if *(u8*)(player+0xA8)  == 0
   skip if player->vtable[0]()  == 0
   skip if *(u8*)(player+0x3F4) != 0
   skip if *(u32*)(player+0x1AC) == 1
   skip if *(u8*)(player+0x400) != 0
   skip if *(u8*)(player+0x538) != 0
   else: append player to a local list          ; count in r27
sort the list so entries with *(u8*)(player+0x3FF) != 0 come first
for each listed player i:
   out_u16[i] = (u16)player->vtable[0](player)   ; 0x39b8fc-0x39b934
39b958:  r3 = 0x01383bd8 (the game/session room object)
39b964:  bl 0x00ad13b8    ; thin room wrapper -> sm->vtable[0x38](sm, room, out_u16, count)
```

Called from `FUN_003a2a7c` (`0x3a2d10`). Player-object stride is `0x920`
(2336), array base `0x0137d700`, first element at `+0x40`.

### Reply expectation: **none**

- The sender returns `0`/`-1` immediately; the caller ignores the return value
  and polls nothing.
- There is **no `0x142` counterpart in `FUN_00ad7604`'s 11-case receive
  dispatch**, so no reply is even representable. Sending one back would hit the
  default branch and permanently wedge the receive cursor (see the dispatch
  audit §1a).
- `room_obj+0xD0 = 1` on the `room_id == 0` early-out is a write-only "deferred"
  marker — a full `lbz`/`stb` sweep of `0xad0000-0xada000` and `0x390000-0x3d0000`
  found no reader, and no retry path.

**Conclusion: `0x142` is a host-side telemetry/report of its local players'
rank values. Keep ignoring it. It is not the missing link for the rank display.**
**Confidence: high.**

---

## 2. Opcode-name table: the 2-entry phantom gap starts at `0x13a`, not `0x143`

`docs/protocol/session_manager_and_matchmaking.md` and the 2026-08-16 dispatch
audit place the two phantom entries at declared indices 22/23
(`UpdatedRoomFlags`, `HostRank`). That is wrong — the gap is between declared
index 12 (`Kickout`) and index 15 (`MemberSetData`), i.e. the phantoms are
**`Kickedout` (13)** and **`RoomDestroyed` (14)**.

Evidence: declared sizes vs. confirmed real sizes line up perfectly under the
shifted mapping and are exactly *inverted* under the unshifted one.

| real opcode | real size (confirmed) | declared idx | declared name | declared size |
|---|---|---|---|---|
| `0x139` | 16 | 12 | `Kickout` | 16 |
| — | — | **13** | **`Kickedout`** | **phantom** |
| — | — | **14** | **`RoomDestroyed`** | **phantom** |
| `0x13a` | **80** | 15 | `MemberSetData` | **80** |
| `0x13b` | **80** | 16 | `MemberUpdatedData` | **80** |
| `0x13c` | 16 | 17 | `Promote` | 16 |
| `0x13d` | 16 | 18 | `OwnerChanged` | 16 |
| `0x13e` | 16 | 19 | `SetAttrFlags` | 16 |
| `0x13f` | 16 | 20 | `UpdatedAttrFlags` | 16 |
| `0x140` | 16 | 21 | `SetRoomFlags` | 16 |
| `0x141` | 16 | 22 | `UpdatedRoomFlags` | 16 |
| `0x142` | 16 + n*2 | 23 | **`HostRank`** | 16 |
| `0x143` | 144 | 24 | `SetRoomName` | 144 |
| `0x144` | 144 | 25 | `UpdatedRoomName` | 144 |
| `0x145` | 4 | 26 | `Ping` | 4 |
| `0x146` | 8 | 27 | `ClientHello2` | 8 |

Under the old (unshifted) reading, `0x13a`/`0x13b` are declared 16 bytes but are
really 80, and `0x13c`/`0x13d` are declared 80 but are really 16 — a clean
2-slot inversion. Three independent semantic checks agree with the shifted
mapping:

1. `0x13a` writes a `<=64`-byte caller blob into the room object and broadcasts
   it; `0x13b` writes that blob onto ONE member record. That is literally
   `MemberSetData` / `MemberUpdatedData`.
2. `0x13c`'s sender (`FUN_00ad6408`) carries a **u16 at offset 4** — the same
   offset and width `0x13b` uses for `member_id`. The doc puzzled over "no
   per-member id anywhere, so this is room-scoped despite the name"; it is a
   member id, and `Promote(member_id)` fits.
3. `0x13d`'s handler writes `room_obj+0x19F0` = *the owner's member id* and
   fires a callback. The audit itself concluded "`OwnerMemberChanged` fits" —
   the shifted table just calls it `OwnerChanged`.
4. `0x142` = `HostRank` matches §1 exactly (an array of per-local-player rank
   u16s sent by the room host), and its declared fixed size 16 is the `count=0`
   case.

Consequence for the stub's naming only (no behaviour change):
`0x13e`/`0x13f` are `SetAttrFlags`/`UpdatedAttrFlags` (the stub calls them
Promote/OwnerChanged), `0x140`/`0x141` are `SetRoomFlags`/`UpdatedRoomFlags`
(the stub calls them SetAttrFlags/UpdatedAttrFlags), and the stub's
`HOST_RANK_OPCODE = 0x144` is really `UpdatedRoomName` (already known).
`room_obj+0x19F4` is therefore an *attribute* bool rather than provably
"am I the host" — but it is empirically the flag that unblocked solo hosting, so
nothing about the working fix changes.

**Confidence: high** (size table is a 4-message exact match plus three
independent semantic corroborations).

---

## 3. The rank / customization data source chain

### 3a. The getter: `FUN_00ad2650(room_obj, npid) -> const u8 *blob32`

```
ad2650:  fn(r3 = room_obj, r4 = npid_ptr)
ad2660:  if (room_obj+0x10 == 0) goto LOCAL
         for i in 0..11:                                    ; 12 member slots
             slot = room_obj + i*0x180 + 0x668
             if (slot+0xE0 occupied && FUN_00e459bc(slot, npid) == 0) { found = slot; break }
         if (!found) return 0
         for j in 0..11:                                    ; find the LOCAL member
             if (occupied && *(u32*)(slot+0xE8) == *(u32*)(room_obj+0x19EC)) { local = slot; break }
         if (found == local) goto LOCAL
ad2728:  ptr = found + 0xFC ; len = *(u32*)(found + 0xF8)    ; REMOTE member
         goto CHECK
LOCAL:                                                       ; 0xad271c
ad271c:  len = *(u32*)(room_obj + 0x19F8) ; ptr = room_obj + 0x19FC
CHECK:
ad2734:  if (len != 32) return 0                             ; cmpwi r0,32 / beq
         return ptr
```

Two things matter enormously:

* **The local player takes a completely different branch.** It reads
  `room_obj+0x19FC`, which the client writes itself. That is *exactly* why the
  local rank renders and no remote rank ever does — the remote path was never a
  UI bug, it is a missing wire payload.
* **The length must be EXACTLY 32.** Not "at most 32". Any other value, including
  the 64 the stub currently relays, makes this return `NULL`.

Callers (all UI/lobby/social-list layer): `0x38e7e4`, `0x39f9ec`, `0x3a261c`,
`0x3a4998`, `0x3b71d4`, `0x3bad4c`, `0x3bae18`, `0x3c2310`, `0x3c2770`,
`0x3c2ac0`, `0x3c2af4`, plus two SessionManager-internal ones (`0xad2898`,
`0xad2b60`).

### 3b. The 32-byte blob's layout, from its producer `FUN_003b15bc`

`FUN_003b15bc` builds the blob on the stack at `r1+120` and pushes it to **both**
room objects via `FUN_00ad1fc0(room, buf, 32)` (`0x3b17cc` → room `0x01383bd8`,
`0x3b17e0` → room `0x01387f58`).

| blob off | width | source | notes |
|---|---|---|---|
| 0 | 8 | `*(u64*)(room_0x01387f58 + 0x10)` or 0 | party-room id; 0 unless member count > 1 and `+0xB8` set. Read back as a u64 at `0x3b71f4`. |
| 8 | 1 | low byte of `*(u32*)(0x01459260 + 0x0C)` | AND-reduced across all room members at `0xad2b6c` |
| 9 | 1 | `*(u8*)(x+0x303)` or 0 | used as `value-1` index into a name/string lookup (`0x3c2ad0` → `FUN_0039c69c`) — title/badge shaped |
| 10..13 | 4 | 4 bytes from global `0x01382082` | 4 one-byte ids; `FUN_003a2310` loops `k=0..3` comparing `blob[10+k]` and subtracting a cost (`0x3a262c`-`0x3a2664`) — **loadout / equipped-item shaped** |
| 14 | 2 | `FUN_00323818(a, b)` | `min(a,999) + min(b,9)*1000`, where `a = (P[0x1E34] + P[0x1E38]) / 7` and `b = P[0x1E44]`, `P = FUN_003cb89c(...)` (the persistent progression record) |
| 16 | 2 | `FUN_003c8e30(0x01387240, 1)` | an override at `<global>+0x78` minus 1, else a walk over a resource table (hash `0xC85E199D`) returning the first bracket index whose two thresholds are satisfied — **rank/tier-lookup shaped**. (Its two arguments are dead on the traced path; `r3` is overwritten with the hash at `0x3c8e58`.) |
| 18..21 | 4 | 4 bytes from `FUN_003cb89c(...)+0x654` | two more u16s |
| 22..31 | 10 | **NEVER WRITTEN — uninitialised stack** | live captures show the player-array global `0x0137d700` and TOC `0x01305870` leaking through here |

Live proof of the 32-byte length and of the uninitialised tail
(`captures/tcp_catch.log` line 60490, comradesean):

```
00 00 01 3a  20  27 0e 9c  01 27 23 d8 01 38 3b d8   <- 0x13a, len byte = 0x20 = 32 @ offset 4
00 00 00 00 00 00 00 00  00 00  00 0e ff ff  00 00   <- blob 0..7 room id, 8, 9, 10..13 loadout, 14..15
00 00 00 00 00 00 00 01  00 00 00 00  01 37 d7 00    <- blob 16..21 stats, then 0x0137d700 = stack junk
```

and mgnomad2 (line 37450) with `blob[10..13] = ff ff ff ff` — a different
loadout, all-`0xff` = unset.

### 3c. The UI read

`FUN_003c203c` / `FUN_003bab9c` are the lobby/roster data providers (they also
build `|@Cffff0000|%s %s` coloured name strings and Facebook avatar URLs, so
this is definitively the player-list UI). The rank-shaped path:

```
3c2768:  r3 = 0x01387f58 (party room)  /  0x3bae04 picks 0x01387f58 or 0x01383bd8
3c2770:  bl 0x00ad2650                      ; blob = getter(room, npid)
3c277c:  if (blob == 0) return              ; <-- REMOTE PLAYERS TAKE THIS EXIT TODAY
3c2780:  r0 = (index << 1) & 0x1FE          ; index = req->field_sel, a byte at req+4
3c27a0:  lhz r9, 14(blob + r0)              ; *(u16*)(blob + 14 + index*2)
3c27a4:  stw 0x2c, 8(r31)                   ; widget value-type = 44
3c27b4:  stw r9, 16(r31)                    ; widget value
3c27a4:  stw 1.0f, 40(r31)
```

So blob offsets `14, 16, 18, 20, ...` are a UI-selectable array of per-member
numeric stats, and the rank display is one of them. (Only indices 0..3 are ever
written by the producer; 4..8 fall in the uninitialised tail.)

Sibling reads confirm the rest of the blob is also lobby display data:
`blob[9]` → a title/badge string index (`0x3c2ad0`), `blob[8]` → a room-wide
AND-reduced boolean (`0xad2b6c`), `blob[10..13]` → the 4 loadout ids
(`0x3a262c`), `blob[0..7]` → the party grouping id (`0x3b71f4`).

**Both symptoms in the brief — missing remote rank AND "randomized" remote
customization — are the same single failure: `FUN_00ad2650` returning `NULL`
for every remote member.** Consumers that bail leave the widget at whatever it
last held; consumers that don't check leave stale/garbage selections.

### 3d. Who writes `member_slot+0xF8` / `+0xFC`

Complete list of writers, from a displacement sweep of the whole SessionManager
module:

| site | what |
|---|---|
| `0xad3724` | `FUN_00ad33d8` registration: `member+0xF8 = 0` (the default — this is today's state for every remote member) |
| `0xad3748` / `0xad37a0` | `FUN_00ad33d8`, **only when `param_2+0x4C == 1`**: `member+0xF8 = len`, `memcpy(member+0xFC, data, len)`, with an assert `len <= 64` (`0xad3744`, source line 218) |
| `0xad20c8` / `0xad20ac` | `FUN_00ad1fc0` local mirror — only ever for the *local* member |
| `0xad8138` / `0xad8140` | **the `0x13b` receive-dispatch case** |

So exactly two wire messages can fill a remote member's blob.

#### (i) `0x131`/Member — per-entry offset **39** (length) and **40..103** (payload)

This corrects the dispatch audit §7, which recorded entry `+39` as "unread" and
`+40..103` as a "name buffer (pointer stored, not copied)". It IS copied, into
`member+0xFC`:

```
ad7828:  addi r28,r1,128            ; descriptor struct
ad79b8:  addi r0,r25,40 ; stw r0,12(r28)   ; descriptor+0x0C = entry + 40   (data pointer)
ad79b0:  lbz  r9,3(r7)  ; r7 = entry+36
ad79c8:  stw  r9,144(r1)                   ; descriptor+0x10 = entry[39]    (LENGTH)
ad79ac:  stw  r28,224(r1)                  ; member_local+0x48 = descriptor
ad7994:  li r0,1 ; stw r0,228(r1)          ; member_local+0x4C = 1          (blob present)
ad79d0:  bl 0xad33d8
```

`FUN_00ad33d8` then reads `*(u32*)(desc+0x10)` as the length and
`*(u32*)(desc+0x0C)` as the source. Caveat: `FUN_00ad33d8` is
first-registration-wins (NpId dedupe early-return at `0xad3430`), so **Member can
only seed the blob, never update it.**

`tools/session_manager_stub.py`'s `build_member` currently writes `entry[39] = 0`
(never set) and stuffs the member's NpId into `entry[40:104]` on a "probably a
name buffer, safe to echo" theory. With length 0 the NpId bytes are ignored and
`member+0xF8 = 0`. **That is the bug.**

#### (ii) `0x13b` — the update path

Handler `0xad808c`-`0xad8148`, re-verified this pass:

```
ad80a4:  lhz r3,4(r29)                       ; member_id (u16, byteswapped)
ad80b4:  cmpwi r0,79                         ; size gate: >= 80
ad80c8:  ld  r10,8(r29)                      ; room_id -> search 4 room slots for room_obj+0x10 match
ad810c:  bl  0xad0d4c                        ; member = lookup(room, member_id)
ad8130:  lbz r0,6(r9)  ; stw r0,248(r11)     ; member+0xF8 = wire[6]   (RAW byte, not swapped)
ad813c:  lbz r5,6(r9)
ad8140:  bl  0xe3e064                        ; memcpy(member+0xFC, wire+16, wire[6])
```

The supplier is `0x13a`, whose **length lives in the byte at wire offset 4**
(`stb r31,116(r1)` @ `0xad6268`, buffer base `r1+112`), payload at offset 16,
room id at offset 8, fixed 80-byte frame. Live: that byte is `0x20` = 32 in
every capture.

**The stub's existing `0x13a` → `0x13b` relay cannot work as written**: it
forwards `chunk[16:80]` and therefore declares `len = 64`. `FUN_00ad2650`'s
`len == 32` gate rejects that outright. The relay has been running and doing
nothing.

---

## 3e. CORRECTION/EXTENSION (2026-08-17, later): `0x13a` is NOT the only
## supplier — the blob is uploaded inside `0x12f` RoomCreate and `0x130` RoomJoin

§3d listed only `0x13a` as the client→server supplier. That is why the
find-match lobby still showed no remote ranks after 4a–4c were applied: **on the
find-match path the client never sends a `0x13a` at all.**

### Why no `0x13a` there

The `0x13a` sender is `FUN_00ad6148` (`this, room, data, len`), reached from
`FUN_00ad1fc0` (`0x3b17cc` / `0x3b17e0`):

```
ad6148:  cmplwi cr7,r6,64 ; assert len <= 64        (net-session.cpp:1383)
ad61d4:  addi r3,r27,6652        ; room+0x19FC
ad61e4:  stw  r31,6648(r29)      ; room+0x19F8 = len       <- LOCAL MIRROR, always
ad61e8:  bl   0xe3e064           ; memcpy(room+0x19FC, data, len)
ad6240:  ld   r9,16(r29)         ; room_id = room+0x10
ad6244:  li   r3,0
ad624c:  beq  cr7,0xad62b0       ; room_id == 0 -> RETURN 0, SEND NOTHING
ad6250:  li   r0,314 (0x13a) ... stb r31,116(r1)  ; wire[4] = len
ad629c:  bl   0xacb93c           ; send 80 bytes
```

`FUN_003b15bc` builds the blob and pushes it to both room objects long before a
matchmade room exists, so `room+0x10` is still 0 and the message is dropped with
**no deferred-retry marker of any kind** (unlike `0x142`'s write-only
`room_obj+0xD0`). Live proof: an exhaustive opcode tally over the whole
2026-08-17 find-match session (`session_manager_stub-run.log`, 6308 lines, the
stub logs every unhandled opcode) is `0x135`×310, `0x140`×115, `0x133`×111,
`0x145`×98, `0x12f`×65, `0x130`×50, `0x146`×8 — **`0x13a`×0**.

### Where the blob actually rides on that path

Both membership-creating messages carry the local mirror verbatim:

| message | length byte | blob bytes | evidence |
|---|---|---|---|
| `0x12f` RoomCreate (`FUN_00ad5b78`, buffer base `r1+144`) | wire **`0x26`** | wire **`0xa8..0xc7`** | `ad5d10 lwz r11,6648(r31)` / `ad5d18 stb r11,182(r1)`; `ad5d20 addi r11,r1,312` / `ad5d30 lbzu r7,6652(r9)` |
| `0x130` RoomJoin (`FUN_00ad6718`, buffer base `r1+112`) | wire **`0x0c`** | wire **`0x18..0x37`** | `ad67a0 lwz r9,6648(r28)` / `ad67ac stb r9,124(r1)`; `ad67a8 addi r11,r1,136` / `ad67c0 lbzu r0,6652(r9)` |

Live bytes (stub log 2026-08-17 01:55:25, comradesean hosting / mgnomad2
joining) — both length bytes are `0x20` = 32 and both payloads decode exactly to
§3b's layout, including the uninitialised `blob[22..]` tail:

```
0x12f  wire[0x26]=20   wire[0xa8]: 00*8 | 00 00 ff ff ff ff 00 00 | 00*8 | 56 7c 00 00 00 00 00 00
0x130  wire[0x0c]=20   wire[0x18]: 00*8 | 00 00 ff ff ff ff 00 00 | 00*8 | 56 9c 00 00 00 00 00 00
```

Note this also identifies the field the stub had been reading as `team` from
RoomCreate `0xb0:0xb2`: it is `blob[8]<<8 | blob[9]`, i.e. **`blob[9]` is the
team/faction byte** — consistent with §3b's "`value-1` index into a name/string
lookup (`0x3c2ad0` → `FUN_0039c69c`)" being the faction-name table, and with the
live-confirmed `0/1/2` = unset/Blue/Red value set.

### Consequence for the server

The server is expected to **harvest** each player's blob from that player's own
`0x12f`/`0x130` and **redistribute** it:

- `0x131` Member entry `[39]`=len / `[40..]`=blob **seeds** a member record at
  registration time (`FUN_00ad33d8`);
- `0x13b` **updates** one that is already registered — mandatory, because
  `FUN_00ad33d8` de-dupes by NpId and early-returns (`0x00ad3474`), so a
  re-pushed Member can never change an existing member's blob.

That ordering is load-bearing for the election flow specifically: the `[punch]`
roster reaches the host *before* the joiner's `0x130`, so the host registers the
joiner with an empty blob and only a subsequent `0x13b` can fill it in.

Applied in `tools/session_manager_stub.py` (`extract_member_blob` +
`ROOM_CREATE_BLOB_*` / `ROOM_JOIN_BLOB_*`, harvest sites in the `0x12f` and
`0x130` branches). **Confidence: high** — disassembly plus live wire bytes on
both messages.

---

## 4. Ready-to-apply stub implementation sketch (NOT applied — live testing in progress)

All of this is in `tools/session_manager_stub.py`.

### 4a. Fix the `0x13a` → `0x13b` relay length (one-line class of bug, highest value)

```python
# in the CREATE_PARTY_OPCODE (0x13a) branch, replacing `chunk[16:80]`:
blob_len = chunk[4]                       # client's own declared length, live-constant 32
blob     = chunk[16:16 + blob_len]        # NOT chunk[16:80]
# FUN_00ad2650 @0xad2734 rejects anything whose length != 32, so forwarding
# 64 bytes silently disabled this whole feature.
```

`build_member_blob` already puts `len(payload)` in `body[6]`, which is the byte
the handler reads, so passing the right-length payload is the entire fix.

Also stop relaying a member's blob back to itself (harmless — the local read
path uses `room_obj+0x19FC` — but it makes the logs honest):

```python
for mid, c, em in targets:
    if mid == sender_member_id:
        continue
```

### 4b. Cache blobs and seed them through `0x131`/Member

```python
# module level
member_blobs = {}   # (room_id_bytes, member_id) -> bytes (exactly 32)

# in the 0x13a branch, after computing blob/blob_len:
member_blobs[(entry["room_id"], sender_member_id)] = blob
```

`build_member` gains a `blobs=None` parameter and fills the two real fields:

```python
    for member_id, npid in members:
        entry = bytearray(104)
        ...
        struct.pack_into(">H", entry, 36, member_id)
        # CORRECTED 2026-08-17: entry[39] is the per-member data-blob LENGTH and
        # entry[40:] is the blob itself - FUN_00ad7604's Member case stores
        # entry+40 as the source pointer and entry[39] as the length into the
        # descriptor FUN_00ad33d8 reads (0xad79b8 / 0xad79c8), which memcpys it
        # into member_slot+0xFC with member_slot+0xF8 = length.  It is NOT a
        # name buffer.  Length MUST be <= 64 (assert at 0xad3744) and must be
        # exactly 32 for FUN_00ad2650 to hand it to the UI (0xad2734).
        blob = (blobs or {}).get(member_id)
        if blob:
            entry[39] = len(blob)
            entry[40:40 + len(blob)] = blob
        entries += entry
```

…and every `build_member(...)` call site (solo-host reply, find-match pairing,
`start_member_refresher`, `broadcast_member_departure`) passes
`blobs={mid: member_blobs.get((room_id, mid)) for mid, _ in members}`.

Note `FUN_00ad33d8` dedupes by NpId and early-returns, so the 10-second Member
refresher will NOT push blob updates to an already-registered member. Member
seeds; `0x13b` updates. Both are needed.

### 4c. Replay cached blobs to a member that joins late

When a new connection joins a room (the `0x130`/RoomJoin branch and the
find-match pairing branch), after sending it Member, send it one `0x13b` per
already-known member of that room:

```python
for (rid, mid), blob in list(member_blobs.items()):
    if rid == entry["room_id"] and mid != new_member_id:
        conn.sendall(build_member_blob(mid, rid, blob))
```

…and push the newcomer's own cached blob (if any) to the incumbents. Ordering
constraint: `0x13b` looks the room up by `room_obj+0x10`, which only Member
sets, so **`0x13b` must follow Member** — same rule as `0x13f`.

### 4d. Leave `0x142` alone

Keep ignoring it. There is no `0x142` case in the client's receive dispatch;
replying with `0x142` (or any opcode outside the legal 11) permanently wedges
the receive cursor. Optionally log `count = be16(chunk[4:6])` and the
`count` u16s from offset 16 as "host reported local player ranks".

### 4e. Bonus: both room-object pointers are static globals

`room_ptr` is not a per-run heap address after all:

- **`0x01383bd8`** — the game/session room (comradesean's RoomCreate offset 8;
  the old hardcoded `ROOM_PTR`; the room `0x142`/HostRank is sent on).
- **`0x01387f58`** — the party room (mgnomad2's RoomCreate offset 8).

Both are resolved statically from the r2→anchor slots `0x01269afc` /
`0x01269b14` (and `0x01269d80` / `0x01269db0` in the UI unit), i.e. they are
fixed data addresses in this build, not allocations. Parsing offset 8 from
RoomCreate remains the right approach, but the **find-match path — which has no
RoomCreate to parse — can safely use these two constants**, which closes the
"finding each joiner's room pointer source is the open problem" item in
`2026-08-16-solo-host-fixed-live-confirmed.md`. (Medium confidence: verified as
static addresses reached through TOC slots, not verified live.)

---

## 5. Bonus: `0x13e`'s "4 varying bytes" are 2 fields + 2 bytes of stack junk

Captured examples `01 03 2f a8`, `04 04 95 fc`, `00 03 f8 10` decompose as:

- offset 4: value byte (`01` / `04` / `00`)
- offset 5: call-site tag byte (`03` from `FUN_00ad6a34`/vtable`+0x20`,
  `04` from `FUN_00ad7024`/vtable`+0x34`)
- offset 6:7: **never written** — `2f a8`, `95 fc`, `f8 10` are uninitialised
  stack, the same pattern already documented for `0x140` and `0x142`.

Under §2's corrected naming this is `SetAttrFlags(attr_id = wire[5],
value = wire[4])`, and `0x13f`/`UpdatedAttrFlags` is its confirmation — which
is what the stub already sends on the solo-host path.

---

## 6. Confidence and what is NOT proven

**High confidence** (direct disassembly + live wire bytes):
- `0x142` field layout, semantics, and no-reply status.
- The `len == 32` gate in `FUN_00ad2650` and the local-vs-remote branch split.
- `0x131` Member entry `+39` length / `+40` payload feeding `member+0xFC`.
- `0x13a` length byte at offset 4 = 32, and the `0x13b` relay's 64-byte bug.
- The 2-entry opcode-name shift starting at `0x13a`.

**Medium confidence**:
- *Which* u16 index in `blob[14..21]` is the on-screen RANK. The index is a
  UI-supplied byte (`lbz r25,4(r11)` @ `0x3c229c`), so it is chosen by UI data,
  not by code. `blob[16]` (index 1) is the most rank-shaped: it comes from
  `FUN_003c8e30`, a threshold-table bracket lookup. `blob[14]` (index 0) is a
  packed `min(b,9)*1000 + min(a,999)`. Both are zero on both live test accounts,
  so the wire captures cannot discriminate.
- That remote *character customization* rides on `blob[10..13]`. Those four
  bytes are per-member selection ids with a cost/budget loop over them and they
  differ between the two live players (`00 0e ff ff` vs `ff ff ff ff`), which is
  the right shape — but no renderer was traced end to end.

**Not investigated**: the meaning of the progression-record fields
`+0x1E34`/`+0x1E38`/`+0x1E44`/`+0x654` that feed the u16 stats; whether
`FUN_003b15bc` is re-run (and therefore `0x13a` re-sent) when a player changes
loadout mid-lobby.
