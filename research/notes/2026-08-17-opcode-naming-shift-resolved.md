# SessionManager opcode naming shift, resolved: Analysis B is correct

Definitive settlement of the `NetMatchmaking*` name/size-table alignment dispute
between:

- **Analysis A** — `research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md`
  §5 (and the current `docs/protocol/session_manager_and_matchmaking.md` table):
  phantom declared entries at declared indices **22/23** (`UpdatedRoomFlags`,
  `HostRank`); the +2 shift starts at declared index 24 / wire `0x143`.
- **Analysis B** — `research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md`
  §2: phantom declared entries at declared indices **13/14** (`Kickedout`,
  `RoomDestroyed`); the +2 shift starts at declared index 15 / wire `0x13a`.

**Verdict: Analysis B is correct, at very high confidence.** The declared
name/size table lines up with the real wire sizes *exactly* under B and is a
scrambled 4-entry size inversion under A. Three behavioral tie-breakers all
corroborate B. Full instruction-level evidence below.

Binary: `EBOOT.elf`, SHA256
`2e44426f00fbb13f192548efa27b7101fb71807d3772ee6e3807ff5053fa94ff`.
EBOOT path:
`/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf`.
All disassembly this pass via capstone (`CS_ARCH_PPC`, big-endian 64), VMA→file
mapping `file_off = VMA - 0x10000` for the text LOAD segment.

---

## 1. Ground truth: the declared name/size table, recovered from `Init()`

`Init()` = `FUN_00ad71a0` (SessionManager vtable `+0x0`). Right after the raw
`connect()` (`bl 0xacbf90` @ `0xad728c`) and before the ClientHello send, it
runs **exactly 28** debug-log registration calls, each of the literal form:

```
li   r4, <size>
lwz  r3, <disp>(r30)      ; r30 = *(r2 - 0x6bd0), r2 = 0x01305870, so r30 = 0x0129f5c0
bl   0xe46460             ; _opd_FUN_00e46460(name_string, size)
nop
```

at `0xad72a0` … `0xad7450` (stepping the size literal and the r30-relative
string-pointer displacement `-0x7fb4` … `-0x7f48` by 4 each iteration). The
string pointers resolve through the slot table at `0x0129760c`…`0x01297678`
into the rodata strings at `0x00ed80a8`…`0x00ed8430`. This is the game emitting
its own opcode names and sizes; it is the authoritative order.

Recovered sequence (declared index = position in this loop; `naive opcode` =
`0x12d + index`, which is what the old formula assumed):

| decl idx | naive opc | declared name (rodata addr) | declared size |
|---|---|---|---|
| 0  | 0x12d | `NetMatchmakingClientHello` (0x00ed80a8) | 48 |
| 1  | 0x12e | `NetMatchmakingServerHello` (0x00ed80c8) | 16 |
| 2  | 0x12f | `NetMatchmakingRoomCreate` (0x00ed80e8) | 232 |
| 3  | 0x130 | `NetMatchmakingRoomJoin` (0x00ed8108) | 88 |
| 4  | 0x131 | `NetMatchmakingMember` (0x00ed8128) | 104 |
| 5  | 0x132 | `NetMatchmakingRoomJoined` (0x00ed8148) | 160 |
| 6  | 0x133 | `NetMatchmakingMemberJoined` (0x00ed8168) | 120 |
| 7  | 0x134 | `NetMatchmakingRoomLeave` (0x00ed8188) | 16 |
| 8  | 0x135 | `NetMatchmakingRoomLeft` (0x00ed81a8) | 24 |
| 9  | 0x136 | `NetMatchmakingRoomSearch` (0x00ed81c8) | 36 |
| 10 | 0x137 | `NetMatchmakingRoomSearchInfo` (0x00ed81e8) | 56 |
| 11 | 0x138 | `NetMatchmakingRoomSearchResult` (0x00ed8210) | 16 |
| 12 | 0x139 | `NetMatchmakingKickout` (0x00ed8238) | 16 |
| **13** | 0x13a | **`NetMatchmakingKickedout`** (0x00ed8258) | **16** |
| **14** | 0x13b | **`NetMatchmakingRoomDestroyed`** (0x00ed8278) | **16** |
| 15 | 0x13c | `NetMatchmakingMemberSetData` (0x00ed8298) | 80 |
| 16 | 0x13d | `NetMatchmakingMemberUpdatedData` (0x00ed82b8) | 80 |
| 17 | 0x13e | `NetMatchmakingPromote` (0x00ed82e0) | 16 |
| 18 | 0x13f | `NetMatchmakingOwnerChanged` (0x00ed8300) | 16 |
| 19 | 0x140 | `NetMatchmakingSetAttrFlags` (0x00ed8320) | 16 |
| 20 | 0x141 | `NetMatchmakingUpdatedAttrFlags` (0x00ed8340) | 16 |
| 21 | 0x142 | `NetMatchmakingSetRoomFlags` (0x00ed8368) | 16 |
| 22 | 0x143 | `NetMatchmakingUpdatedRoomFlags` (0x00ed8388) | 16 |
| 23 | 0x144 | `NetMatchmakingHostRank` (0x00ed83b0) | 16 |
| 24 | 0x145 | `NetMatchmakingSetRoomName` (0x00ed83d0) | 144 |
| 25 | 0x146 | `NetMatchmakingUpdatedRoomName` (0x00ed83f0) | 144 |
| 26 | 0x147 | `NetMatchmakingPing` (0x00ed8418) | 4 |
| 27 | 0x148 | `NetMatchmakingClientHello2` (0x00ed8430) | 8 |

There is **one contiguous list, no gaps in the table itself** — the "phantoms"
are declared names that simply have no wire opcode. (The 29th stray
`NetMatchmakingOwnerChanged` string at `0x00ec8450` is outside this loop and is
an unused duplicate, as prior notes observed.)

## 2. Real wire sizes for the contested range (re-verified this pass)

Sizes taken directly from receive-dispatcher (`FUN_00ad7604`) buffer-advance
gates and from each sender's `li r0,<opcode>` + `li r5,<size>` before
`bl 0xacb93c`:

| wire opc | how found | address(es) | real size |
|---|---|---|---|
| 0x139 | dispatch case + teardown | `0xad7fc4` (`cmpwi r0,15`) | 16 |
| **0x13a** | sender (client→server) | `li r0,0x13a`@`0xad6250`; `li r5,0x50`@`0xad6294`; `bl 0xacb93c`@`0xad629c` | **80** |
| **0x13b** | dispatch case (server→client) | `cmpwi r3,0x13b`@`0xad808c`; size gate `cmpwi r0,0x4f`@`0xad80b4` | **80** |
| **0x13c** | sender (`FUN_00ad6408`) | `li r0,0x13c`@`0xad6480`; `li r5,0x10`@`0xad64c0`; `bl 0xacb93c`@`0xad64c8` | **16** |
| **0x13d** | dispatch case | `cmpwi r3,0x13d`@`0xad817c`; size gate `cmpwi r0,0xf`@`0xad81f0` | **16** |
| 0x13e | sender (`FUN_00ad6a34`) | `li r0,0x13e`@`0xad6b58` | 16 |
| 0x13f | dispatch case | `cmpwi r3,0x13f`@`0xad825c` (`cmpwi r0,15`) | 16 |
| 0x140 | sender (`FUN_00ad62dc`) | `li r0,320` | 16 |
| 0x141 | dispatch case | `cmpwi r3,0x141`@`0xad82d4` | 16 |
| 0x142 | sender (`FUN_00ad5ffc`), no dispatch case | `li r0,322` | 16 + n*2 (base 16) |
| 0x143 | senders (`FUN_00ad6f28`/`FUN_00ad54e0`) | — | 144 |
| 0x144 | dispatch case | `cmpwi r3,0x144`@`0xad838c` (`cmpwi r0,143`) | 144 |
| 0x145 | `Ping`, client-timer send, no reply | live-confirmed | 4 |
| 0x146 | `ClientHello2`, `Init()` send | live-confirmed | 8 |

The four load-bearing sizes — **0x13a=80, 0x13b=80, 0x13c=16, 0x13d=16** — were
disassembled fresh this pass (addresses above), not taken on faith from the
prior notes.

## 3. Alignment: the shift K

Two hard anchors bracket the table:

- **Head anchor:** ClientHello's own outbound magic is a literal `0x12d`
  (`li r0,0x12d`@`0xad7464`) and ServerHello's required magic is `0x12e`
  (`if (resp[0]==0x12e)` in `Init()`), matching declared idx 0/1 with **K=0**.
- **Tail anchor:** `Ping` is live-confirmed wire `0x145` and `ClientHello2` is
  live-confirmed wire `0x146` — i.e. declared idx 26/27 map to wire
  `0x12d + idx − 2`, so **K=+2** at the tail. (Both A and B agree on the tail;
  it does not discriminate them.)

The +2 must appear somewhere in the middle. Define the mapping
`wire = 0x12d + decl_idx − K`, K = number of phantom declared entries seen so
far. Aligning declared **sizes** to real wire sizes:

**Under B** (phantoms at idx 13/14, K jumps 0→2 between idx 12 and idx 15):

| decl idx (name / size) | → wire | real size | match? |
|---|---|---|---|
| 15 MemberSetData / 80 | 0x13a | 80 | ✓ |
| 16 MemberUpdatedData / 80 | 0x13b | 80 | ✓ |
| 17 Promote / 16 | 0x13c | 16 | ✓ |
| 18 OwnerChanged / 16 | 0x13d | 16 | ✓ |
| 19 SetAttrFlags / 16 | 0x13e | 16 | ✓ |
| 20 UpdatedAttrFlags / 16 | 0x13f | 16 | ✓ |
| 21 SetRoomFlags / 16 | 0x140 | 16 | ✓ |
| 22 UpdatedRoomFlags / 16 | 0x141 | 16 | ✓ |
| 23 HostRank / 16 | 0x142 | 16 (base) | ✓ |
| 24 SetRoomName / 144 | 0x143 | 144 | ✓ |
| 25 UpdatedRoomName / 144 | 0x144 | 144 | ✓ |
| 26 Ping / 4 | 0x145 | 4 | ✓ |
| 27 ClientHello2 / 8 | 0x146 | 8 | ✓ |

**13 for 13.** Phantoms `Kickedout`(16)/`RoomDestroyed`(16) have no wire opcode.

**Under A** (phantoms at idx 22/23, K stays 0 through idx 21):

| decl idx (name / size) | → wire | real size | match? |
|---|---|---|---|
| 13 Kickedout / 16 | 0x13a | **80** | ✗ |
| 14 RoomDestroyed / 16 | 0x13b | **80** | ✗ |
| 15 MemberSetData / 80 | 0x13c | **16** | ✗ |
| 16 MemberUpdatedData / 80 | 0x13d | **16** | ✗ |
| 17 Promote / 16 | 0x13e | 16 | ✓ |
| … (idx 18–21 all 16→16) | … | 16 | ✓ (degenerate) |

**A puts the declared `(16,16,80,80)` block against the real `(80,80,16,16)`
block — a clean four-entry size inversion.** That is exactly the tell B
identified.

### Why A missed it

A asserted K=0 through idx 21 from the *behavior* of the 16-byte opcodes
0x13e–0x142, which are size-degenerate — every one is 16 bytes, so a ±2 slide
inside that run cannot be caught by size. A never lined up the four declared
sizes at idx 13–16 (`16,16,80,80`) against the real sizes at 0x13a–0x13d
(`80,80,16,16`); had it done so the inversion is immediate. A then validated
only the tail block (idx 24–27), where A and B agree, and concluded the shift
must start there. The discriminating evidence sits in the two 80-byte messages
0x13a/0x13b, which A's size check skipped.

**Shift verdict:** K=0 for wire opcodes `0x12d`–`0x139` (declared idx 0–12);
declared idx **13 `Kickedout`** and **14 `RoomDestroyed`** are PHANTOM (no wire
opcode); K=+2 for wire opcodes `0x13a`–`0x146` (declared idx 15–27), i.e.
`wire = 0x12d + decl_idx − 2`.

## 4. Behavioral tie-breakers — all three corroborate B

1. **0x13d writes `room_obj+0x19f0` (the owner's member id).** Dispatch case
   `cmpwi r3,0x13d`@`0xad817c`; writes the u16 at wire offset 4 into
   `room_obj+0x19f0` and fires `room->vtable[0x34]()` (owner-designation
   callback). Under **B this opcode's declared name is literally
   `OwnerChanged`** (idx 18) — a perfect semantic fit. Under A it is
   `MemberUpdatedData` (idx 16), a name A itself had to reject and hand-rename
   "OwnerMemberChanged".

2. **0x13f writes `room_obj+0x19f4` (the attribute/"is-owner" flag that
   empirically unblocked solo hosting).** Dispatch case `cmpwi r3,0x13f`
   @`0xad825c`; writes `wire[4] & 1` into `room_obj+0x19f4` (`stb`@`0xad82cc`).
   Its optimistic-toggle *sender* is `FUN_00ad6a34` = wire **0x13e**
   (`li r0,0x13e`@`0xad6b58`; reads/sets `room_obj+0x19f4` at `0xad6ab8` /
   `0xad6af0` / `0xad6c04`). Under **B** this is the pair
   **`SetAttrFlags`(0x13e) → `UpdatedAttrFlags`(0x13f)**, both operating on the
   same `+0x19f4` attribute byte — a clean Set/Updated pair. `room_obj+0x19f4`
   is therefore an *attribute* boolean, not provably "am I the host"; it is
   nonetheless the flag that unblocks solo hosting, so nothing about the working
   fix changes.

3. **0x142 is fire-and-forget with no receive-dispatch case**, sender
   `FUN_00ad5ffc` (`li r0,322`), variable `16 + count*2` carrying an array of
   per-local-player u16 rank values (see the 2026-08-17 member-blob note §1).
   Under **B its declared name is `HostRank`** (idx 23) — an array-of-rank-u16s
   message named "HostRank". Under A the array message would be called
   `SetRoomFlags` and the name `HostRank` would be discarded as a phantom —
   semantically backwards.

## 5. Definitive verdict table

`wire opcode → correct declared name (B) → real size → confirmed behavior`.
Names 0x12d–0x139 are K=0 (naive) and were already correct.

| wire | correct declared name | real size | behavior / direction |
|---|---|---|---|
| 0x139 | Kickout | 16 | s→c room teardown |
| — | *Kickedout* (PHANTOM) | (16 decl) | no wire opcode |
| — | *RoomDestroyed* (PHANTOM) | (16 decl) | no wire opcode |
| 0x13a | **MemberSetData** | 80 | c→s: client publishes its own 32-byte member card (blob len at off 4) |
| 0x13b | **MemberUpdatedData** | 80 | s→c: writes blob into `member+0xFC` (len `member+0xF8`); UI rank/loadout source |
| 0x13c | **Promote** | 16 | c→s: u16 (member id) at off 4 + room_id |
| 0x13d | **OwnerChanged** | 16 | s→c: writes owner member id → `room_obj+0x19f0`, fires vtable[0x34] |
| 0x13e | **SetAttrFlags** | 16 | c→s: value byte off 4 + tag byte off 5; optimistically toggles `room_obj+0x19f4` |
| 0x13f | **UpdatedAttrFlags** | 16 | s→c: writes `wire[4]&1` → `room_obj+0x19f4` (the solo-host unblock flag) |
| 0x140 | **SetRoomFlags** | 16 | c→s: u16 at off 4 + room_id |
| 0x141 | **UpdatedRoomFlags** | 16 | s→c: u16 off 4 → `room_obj+0x1f0` |
| 0x142 | **HostRank** | 16 + n*2 | c→s fire-and-forget: n×u16 local-player ranks; no dispatch case |
| 0x143 | **SetRoomName** | 144 | c→s: 128-byte room-name copy of `room_obj+0x18` |
| 0x144 | **UpdatedRoomName** | 144 | s→c: `strcpy` payload → `room_obj+0x18` (room name) |
| 0x145 | Ping | 4 | c→s keepalive |
| 0x146 | ClientHello2 | 8 | c→s, `Init()` fire-and-forget |

**Confidence: very high.** Two fully independent signals agree (all 13 declared
sizes match B exactly and are inverted under A; three behavioral semantics fit
B's names and misfit A's), bracketed by hard anchors at both ends
(0x12d/0x12e literal; 0x145/0x146 live).

## 6. Consequence for the live stub — naming only, NOT a functional bug

`tools/session_manager_stub.py` keys every decision off wire opcode **numbers**
and confirmed **behaviors**, both of which are correct. Its internal constant
*names* are mislabeled under the corrected table. **This is a documentation
fix, not a code-correctness fix — the running stub is behaviorally right and
must not be edited (live testing in progress).** For the record, the mislabels:

| stub symbol / call | wire opc | stub's implied name | correct declared name (B) | behavior stub relies on |
|---|---|---|---|---|
| `OWNER_CHANGED_OPCODE` | 0x13f | OwnerChanged | **UpdatedAttrFlags** | writes `+0x19f4` — correct, unblocks solo host |
| `build_owner_member` (0x13d) | 0x13d | OwnerMemberChanged | **OwnerChanged** | writes `+0x19f0` owner id — correct |
| `MEMBER_BLOB_OPCODE` | 0x13b | (member blob) | **MemberUpdatedData** | writes `member+0xFC` — correct |
| `CREATE_PARTY_OPCODE` | 0x13a | SetPartyData | **MemberSetData** | c→s member card — correct |
| `SET_ATTR_FLAGS_OPCODE` | 0x140 | SetAttrFlags | **SetRoomFlags** | echoed — correct |
| `UPDATED_ATTR_FLAGS_OPCODE` | 0x141 | UpdatedAttrFlags | **UpdatedRoomFlags** | echoed — correct |
| `UPDATED_ROOM_FLAGS_OPCODE` | 0x143 | UpdatedRoomFlags | **SetRoomName** | echoed — correct |
| `HOST_RANK_OPCODE` | 0x144 | HostRank | **UpdatedRoomName** | already known misnomer; echo is correct |

The stub sends no 0x13c/0x13e and correctly never replies to 0x142.

## 7. Naming changes needed in docs / protos (LISTED, NOT APPLIED)

For the main session to reconcile. All are name-only; no size/field/behavior
change is implied for any opcode already documented from its handler/sender.

### `docs/protocol/session_manager_and_matchmaking.md`
- The 28-entry table currently follows Analysis A (phantoms at idx 22/23).
  Replace with the §5 mapping above: phantoms are **`Kickedout` (idx 13)** and
  **`RoomDestroyed` (idx 14)**; from `0x13a` on, correct name =
  declared name at `idx = opcode − 0x12d + 2`. Concretely the row renames:
  `0x13a`→SetPartyData/MemberSetData, `0x13b`→MemberUpdatedData,
  `0x13c`→Promote, `0x13d`→OwnerChanged, `0x13e`→SetAttrFlags,
  `0x13f`→UpdatedAttrFlags, `0x140`→SetRoomFlags, `0x141`→UpdatedRoomFlags,
  `0x142`→HostRank, `0x143`→SetRoomName, `0x144`→UpdatedRoomName
  (`0x145`/`0x146` already right).
- Correction-banner item 1 (phantoms at "index 22/23") and item 4
  (`0x13d` "not MemberUpdatedData") both need updating: `0x13d` IS declared
  `OwnerChanged`; `MemberUpdatedData` is `0x13b`.
- The "Naming caveat" paragraph can be promoted from "plausible reinterpretation
  not yet reconciled" to the confirmed mapping.

### `protos/*.ksy` filename + `id`/`doc` renames (the file at wire opcode N
currently carries the naive name = declared idx N; correct name = declared idx N+2):
- `0x13a_periodic_telemetry.ksy` → **MemberSetData** (already flagged misnomer)
- `0x13b_room_destroyed.ksy` → **MemberUpdatedData** (already flagged misnomer)
- `0x13c_member_set_data.ksy` → **Promote**
- `0x13d_member_updated_data.ksy` → **OwnerChanged**
- `0x13e_promote.ksy` → **SetAttrFlags**
- `0x13f_owner_changed.ksy` → **UpdatedAttrFlags**
- `0x140_set_attr_flags.ksy` → **SetRoomFlags**
- `0x141_updated_attr_flags.ksy` → **UpdatedRoomFlags**
- `0x142_set_room_flags.ksy` → **HostRank**
- `0x143_updated_room_flags.ksy` → **SetRoomName** (doc already half-corrected)
- `0x144_host_rank.ksy` → **UpdatedRoomName** (doc already corrected)
- `0x145_ping.ksy`, `0x146_client_hello2.ksy` — already correct.

Note these are pure label changes: each `.ksy`'s actual field layout was
reversed from the opcode's own handler/sender and remains valid; only the
human-readable name attached to it moves by the +2 shift.
