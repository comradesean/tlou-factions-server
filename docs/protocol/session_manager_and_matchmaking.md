# Session Manager init + the `NetMatchmaking*` opcode family

Companion doc for:
- `protos/netmatchmaking_client_hello.ksy`
- `protos/netmatchmaking_server_hello.ksy`

**2026-08-14 correction, see `research/notes/2026-08-14-voice-server-discovery.md`
for full detail:** the "what's still open" items below turned out NOT to be the
live-testing blocker they were assumed to be. `Init()` does not wait for a response
to `ClientHello2`, and the receive/dispatch loop is non-blocking/polled - a client
with nothing past `ClientHello`/`ClientHello2` implemented will not hang on this
connection. `ClientHello2`'s real on-wire opcode is confirmed **`0x146`** (not `0x148`
as the naive `opcode = 0x12d + table-index` formula below implied), and the periodic
keepalive `Ping` uses literal **`0x145`** (not `0x147`) - the formula is confirmed
wrong for at least these two tail entries; the 11 receive-dispatch cases (`0x131`-
`0x144`) are unaffected, those were read directly off switch-statement literals.
Also newly confirmed: post-handshake `NetMatchmaking*` traffic is plain unframed
bytes (`[4-byte opcode][payload]`), not wrapped in ticket-server's encrypt-then-MAC
frame - this resolves open item #3 below. The actual "connecting..." hang turned out
to be a previously-undocumented fourth port, 7313 - see the new note.

**2026-08-15 correction, see `research/notes/2026-08-15-room-teardown-and-flag-chain.md`
and `protos/0x133_room_leaving.ksy` for full detail:** unlike ClientHello2/Ping
(wrong *numeric* opcode), `0x133`'s numeric value is fine (live-captured directly on
the wire) but its declared *name*, `NetMatchmakingMemberJoined`, is now confirmed
wrong via full decompile of the function that sends it (`_opd_FUN_00ad65e8`) - it
fires when the client abandons a room it's tracking, immediately zeroes its own
room-id copy, and walks every member slot through the exact same removal path the
confirmed `0x134`/`RoomLeave` case uses. It belongs conceptually next to
`RoomLeave`/`RoomLeft`, not `MemberJoined`. Also confirmed not one of the 11
client-receivable opcodes below - fire-and-forget, no reply expected or useful (a
same-opcode echo reply was tried live and had zero effect).

**2026-08-14 second correction, see `research/notes/2026-08-14-room-create-joined.md`:**
with the port-7313 hang fixed, live testing progressed further and hit a new error,
"Lobby Server Error" - this comes from the client's own client-side timeout after
sending `RoomCreate` (opcode `0x12f`, live-captured at the full 232 bytes the table
predicts) and getting no reply. Decompiling `FUN_00ad7604`'s `iVar8 == 0x132`
(`RoomJoined`) case against the live capture found another size-table error: the real
wire size for `RoomJoined` is **120 bytes (`0x78`), not the declared 160** - the
dispatch code's own buffer-advance amount is authoritative. Field-level layout and the
stub's reply are in `server/session_manager.py`'s `build_room_joined()`; several
fields (an 18x-`u16` "attribute" block, offset 16:52) are still unconfirmed/zeroed -
see that function's docstring and the note for what's still open.

**2026-08-16 audit corrections — see
`research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md` for the
full instruction-level evidence. Five things in the table below are now known to
be wrong:**

1. **The declared name/size table has two PHANTOM entries** (index 22
   `UpdatedRoomFlags`, index 23 `HostRank`) with no wire opcode at all. From
   index 24 onward the real opcode is `0x12d + index - 2`, so
   **`0x143` = `SetRoomName`** and **`0x144` = `UpdatedRoomName`** (both 144
   bytes, matching those declared sizes exactly), and the already-known
   `Ping`=`0x145` / `ClientHello2`=`0x146` corrections fall out of the same
   single 2-entry shift instead of being unexplained one-offs. `0x144`'s
   handler does a plain `strcpy` (`_opd_FUN_00e45b10`, decompiled and
   confirmed) of the payload into `room_obj+0x18`, which is confirmed to be the
   room NAME (`"<npid>.<timestamp>"`, the same string RoomCreate carries at its
   own offset 0x28). Rows 22–23 below are superseded.
2. **`RoomCreate` (0x12f) has no `create_id`.** Wire offset 4:8 is never
   written by the sender — uninitialised stack, live-proven varying between
   `01 27 23 d8` and `00 00 00 00` on the same client. **Wire offset 8:12 is
   the client's own room-object pointer** (the value `Member`'s room_ptr field
   needs, previously only obtainable with a live debugger), and
   **max-players is at offset 0x24, not 0x1e** (0x1e is another
   never-written gap).
3. **`0x140`/`0x141`'s payload is a u16 at offset 4, not a 4-byte bitmask.**
   Offset 6:8 is uninitialised stack — which is the entire explanation for the
   "several settings packed into one bitmask" reading in row 19: the four
   captured values decompose as `(1, garbage)`, `(0, garbage)`, `(1, garbage)`,
   `(1, garbage)`.
4. **`0x13d` is an owner-designation message**, not `MemberUpdatedData`: the
   field it writes (`room_obj+0x19f0`) is independently written by member
   registration from the roster entry carrying `is_owner`, and is read back by
   a dedicated "find the owner's member record" lookup (`_opd_FUN_00ad0d98`).
5. **`0x13f`/OwnerChanged was the single highest-value message the stub had
   never sent — it is now sent and live-verified** (corrected 2026-08-19).
   `RoomCreate`'s own sender clears `room_obj+0x19f4` ("I am the host")
   unconditionally, and `0x13f` is the only inbound message that can set it, so
   without it a solo-hosting client never learns it is the host. The stub sends
   it on the solo-host path and on every ownership change (271 frames in one
   day's capture; part of the verified `0x13c` Promote round trip).

**Also: an opcode outside the 11-case dispatch chain permanently wedges the
connection** (the default branch returns without advancing the receive cursor).

**2026-08-17 — FIND-MATCH and PROGRESSION (read the 2026-08-17 status summary:
`research/notes/2026-08-17-session-handoff.md`).** Two load-bearing findings:
(1) **Progression (supplies/rank/journeys) credits ONLY for a COUNTED matchmade
game** — custom/invite games never set the "match counts" latch by design, so
only find-match (public matchmaking) can advance the metagame. (2) **`0x136`
RoomSearch is the SERVER->CLIENT find-match GAME LIST** the client's
`NET_SM_CLIENT_GAME_LIST_WAIT` blocks on (server must push it in reply to the
`0x135` search); the join is then pure P2P (`CONNECT_TO_HOST` by the host NpId
carried in the `0x136` entry at `[0x14:0x24]`), NOT a `0x130`.

**★ SOLVED / CREDITED (2026-08-17 PM) — the full loop works end-to-end.** The
two-client host/joiner coordination is fixed by a SERIALIZED ELECTION in the
stub: elect the first criteria-0 (`0x135` burst-marker==5) searcher as host and
feed it empty `0x136` lists so it self-hosts; PARK every other searcher (send it
NO `0x136` — it blocks silently in `GAME_LIST_WAIT`, 60s hard cap) until the
host's `0x12f` RoomCreate arrives, then release it with a 1-entry list pointing
at the host. Exactly one host + one joiner, every time. Two supporting fixes: a
pre-join `[punch]` roster push (host dials the joiner's P2P handle at release
time, killing a 6s reserve stall), and harvesting each player's 32-byte
rank/faction/loadout blob straight from their `0x12f`/`0x130` wire (`0x12f` wire
0xa8 / len 0x26; `0x130` wire 0x18 / len 0x0c) and replaying it via `0x131`+
`0x13b` — the matchmade lobby never sends `0x13a`, so this is the only blob
supplier, and without it the remote rank card is blank. With a client-side
min-players=2 patch (`client/patches/minplayers_patch.yml`; the shipped playlist
minimum is 6) this drove the project's FIRST counted, credited matchmade game:
`task-manager-online.cpp:1236 GOTO NET_SM_RESULTS` ("Leaving Game Normally") →
latch armed → `OnMatchEnd` → supplies/rank and clan population credited live
(clan grew 5 → 19 survivors on screen). See
`research/notes/2026-08-17-find-match-coordination-root-cause.md` (§5b live
outcome), `protos/0x135_find_match.ksy`, `protos/0x136_room_search.ksy`,
`2026-08-17-match-counts-latch.md`, `2026-08-17-min-players-client-patch.md`.

**2026-08-16/17 — LIVE-CONFIRMED WORKING. Solo-host, party invite + join, and
2-player matches all run end-to-end against `server/session_manager.py`.**
Full trail: `research/notes/2026-08-16-solo-host-fixed-live-confirmed.md`,
`research/notes/2026-08-16-two-player-party-and-match-working.md`,
`research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md`. This
supersedes several rows in the table below (noted inline); the headline changes:

- **Solo-host works.** The fix stack: parse `room_ptr` from RoomCreate wire
  offset 8 (per-client, not a hardcode), read `max_players` from 0x24, send
  `0x13f`/OwnerChanged after Member (the client never becomes host otherwise),
  and — critically — **stop sending `RoomJoined` (0x132) on the solo-host
  path** and populate the local member's real NpId in Member. RoomJoined's
  `is_local=0` registration created a phantom second member AND (with the old
  NpId-zeroing hack) left the local player nameless, which starved the
  team-assignment lookup and caused the `net-game-manager.cpp:1358` `team>=0`
  boot. Member alone carries the room-create-completed latch, so RoomJoined is
  not needed. `NET_SM_SERVER_LOBBY` (the old "Starting Game…" permanent stall)
  now clears in ~30ms.
- **`0x13a`/`0x13b` are the per-member DATA BLOB pair, not telemetry /
  destruction.** `0x13a` (client→server, SetPartyData) publishes a client's own
  32-byte member card (byte 8 flags, byte 9 title index, bytes 10..13 the host
  map-picker's recent-level ring — CORRECTED 2026-08-17, was "four loadout
  item-ids"; NOT loadout, it is NetGameManager+0x4982 recent-map indices, see
  protos/common/member_data.ksy — u16 at byte 14 the rank value, tail = stat
  region); the
  server relays it per-member as `0x13b`, which writes it to `member_slot+0xFC`.
  The lobby UI's rank/loadout getter (`_opd_FUN_00ad2650`) reads that field and
  accepts it ONLY at length exactly 32. Member (0x131) SEEDS the blob via entry
  offset 39 (length) / 40 (blob) — NOT a name buffer, corrected; the display
  name comes from the NpId in the entry's first 16 bytes. Supersedes rows 13/14.
- **`0x13d` is OwnerMemberChanged**, `0x134`/RoomLeave is now sent on joiner
  departure (prevents the host getting "kicked from party" spam), and both are
  live-exercised. `0x130`/RoomJoin (party-invite accept and party→match) is
  handled via a cross-connection room registry.
- **`0x142` is `HostRank`** (fire-and-forget host→server report of local player
  ranks, `count` at offset 4 then `count`×u16 at offset 16), and **`0x144` is
  `UpdatedRoomName`** — so the older "0x143/0x144 are a rank/host-priority pair"
  reading (row 23) is wrong; the HostRank echo the stub added on 2026-08-16 was
  on the wrong opcode and is not needed. `0x142` has no receive-dispatch case;
  keep ignoring it (replying would wedge the cursor).
- Both room-object pointers are **static globals**: `0x01383bd8` (game/session
  room) and `0x01387f58` (party room). Parsing wire offset 8 remains correct;
  the find-match path (no RoomCreate) can use the constants.
- **Still open:** remote-player rank/loadout render as empty because served
  profiles are empty (rank-up/gear unlock needs the profile pipeline —
  `t1.final.prod.s3.amazonaws.com/profiles/…` / `userdata/….txt.crypt`, under
  investigation); the party P2P link drops at game end ("lost connection to
  party member", a signaling/P2P-layer issue, not a room opcode); and an
  intermittent, unexplained "Host quit for cheating" match teardown.

**Naming RESOLVED 2026-08-17** — see `research/notes/2026-08-17-opcode-naming-shift-resolved.md`.
The declared name/size table (recovered as ground truth from the 28 registration
calls in `Init()`, strings at `0x00ed80a8`–`0x00ed8430`) IS shifted +2 slots from
0x13a: declared idx 13 (`Kickedout`) and 14 (`RoomDestroyed`) are PHANTOM (no wire
opcode), and `wire = 0x12d + declared_idx − 2` for 0x13a–0x146. Decisive evidence:
the two 80-byte messages 0x13a/0x13b line up with declared sizes 80/80 only under
the shift; all 13 tail entries match exactly; anchored by Ping=0x145/ClientHello2=0x146.
**This is a documentation/naming fix only — no functional bug.** The stub keys off
wire opcode numbers and behaviors (all correct); only its constant NAMES are
mislabeled. The correct wire→name mapping:

| wire | correct declared name | real size | stub's (mislabeled) name |
|---|---|---|---|
| 0x13a | `MemberSetData` (client→server, the member data blob) | 80 | (file "periodic_telemetry") |
| 0x13b | `MemberUpdatedData` (server→client blob delivery) | 80 | (file "room_destroyed") |
| 0x13c | `Promote` | 16 | (file "member_set_data") |
| 0x13d | `OwnerChanged` (writes owner member id `+0x19f0`) | 16 | `build_owner_member` |
| 0x13e | `SetAttrFlags` | 16 | (file "promote") |
| 0x13f | `UpdatedAttrFlags` (writes attr flag `+0x19f4`) | 16 | `OWNER_CHANGED_OPCODE` |
| 0x140 | `SetRoomFlags` | 16 | `SET_ATTR_FLAGS_OPCODE` |
| 0x141 | `UpdatedRoomFlags` | 16 | `UPDATED_ATTR_FLAGS_OPCODE` |
| 0x142 | `HostRank` (fire-and-forget, base 16 + n×2) | 16+ | `SET_ROOM_FLAGS`(unsent) |
| 0x143 | `SetRoomName` | 144 | (file "updated_room_flags") |
| 0x144 | `UpdatedRoomName` | 144 | `HOST_RANK_OPCODE` |

The inline row NAMES below (and the `.ksy` filename suffixes, which are shifted by
2) are being reconciled to this mapping; where a row's name disagrees with this
table, this table is correct. The behaviors described are unaffected.

**Superseded 2026-08-17 for rows `0x13e`-`0x144` — see the "FINAL CORRECTION"
banner directly below.** `SetAttrFlags`/`UpdatedAttrFlags` are renamed
`SetHostFlag`/`HostFlagUpdated` (same fields, same targets `+0x19f4`);
`SetRoomFlags`/`UpdatedRoomFlags` are renamed `SetRoomAttr`/`RoomAttrUpdated`
(same fields, target `+0x1f0`, meaning still UNKNOWN); and — the actual
correction, not just a rename — **`HostRank` (0x142) and `SetRoomName`/
`UpdatedRoomName` (0x143/0x144) are wrong readings, not just wrong names**:
0x142's u16 list has no confirmed purpose (do not call it host rank), and
0x143/0x144's 128-byte `room_obj+0x18` block is not confirmed to be a name
string (do not call it set/updated room name). Also superseded: rows `0x137`-
`0x139` below, which this table didn't touch but which turned out to be the
single biggest naming error in the whole family (see the banner).

**2026-08-17 FINAL CORRECTION — 0x137-0x144 tail fully re-verified against the
receive dispatcher (`FUN_00ad7604` @ `0x00ad7604`) and the client-side
builders (`0xad4c00`-`0xad7604`), triggered by root-causing the friends-list
Join Party bug live (see the new "Party lifecycle" section below and
`research/notes/2026-08-17-session-handoff.md`). This is the decisive,
disassembly-verified map — where any earlier row in this document disagrees,
this map wins:**

SERVER->CLIENT (dispatcher @`0x00ad7604`): `0x131` Member (160+104N); `0x132`
RoomJoined (120); `0x134` MemberLeft (24, member_id@16); `0x136`
RoomSearchResult/GameList (16+56N); `0x138` **Kickedout** (16, room_id@8 —
recipient leaves the room); `0x139` **RoomClosed/ForcedTeardown** (16,
server-initiated, harder teardown: RequestLeave + zeroes slot+0x10); `0x13b`
MemberDataUpdated (80); `0x13d` OwnerMemberChanged (16, new_owner_member_id@4
-> room+0x19f0); `0x13f` **HostFlagUpdated** (16, flag@4 -> room+0x19f4);
`0x141` RoomAttrUpdated (16, value@4 -> room+0x1f0, meaning UNKNOWN); `0x144`
RoomDataBlockUpdated (144, 128-byte block@16 -> room+0x18).

CLIENT->SERVER (builders in `0xad4c00`-`0xad7604`): `0x12d` ClientHello;
`0x12f` RoomCreate; `0x130` RoomJoin (88); `0x133` RoomLeaving (client
abandons); `0x135` FindMatch (36); `0x137` **Kickout** (16,
target_member_id@4, requester_member_id@6, room_id@8); `0x13a` SetMemberData
(80); `0x13c` **Promote** (16, new_owner_member_id@4, room_id@8); `0x13e`
**SetHostFlag** (16, flag@4, const kind byte 3@5, room_id@8); `0x140`
SetRoomAttr (16, value@4 -> room+0x1f0, UNKNOWN meaning); `0x142`
**RoomU16ListUpload** (16+2*count, count@4, u16[count]@16, purpose UNKNOWN —
**NOT** "host_rank"); `0x143` **SetRoomDataBlock** (144, 128-byte block@16
from room+0x18 — **NOT** "set_room_name"); `0x145` Ping (4); `0x146`
ClientHello2.

Request/response pairs: `0x137`->`0x138`, `0x13a`->`0x13b`, `0x13c`->`0x13d`,
`0x13e`->`0x13f`, `0x140`->`0x141`, `0x143`->`0x144`. Two singletons: `0x139`
(server-initiated RoomClosed, no client-sent request) and `0x142` (client u16-
list upload, still fire-and-forget with no dispatch case, unchanged from the
2026-08-15 finding). The headline rename is `0x137`/`0x138`/`0x139`: earlier
passes (rows 10-12 below) read `0x137` as `RoomSearchInfo` and `0x138` as
`RoomSearchResult` purely from the room_id-echo shape, and separately read
`0x139` as `Kickout`. All three field layouts were correct; only the naming
and the true request/response pairing were wrong. **This wrong naming is what
built the Join Party bug** — see below. The proto files were renamed to
match: `protos/0x137_kickout.ksy`, `protos/0x138_kickedout.ksy`,
`protos/0x139_room_closed.ksy`, `protos/0x13e_set_host_flag.ksy`,
`protos/0x13f_host_flag_updated.ksy`, `protos/0x142_host_rank.ksy`,
`protos/0x143_set_room_data_block.ksy`,
`protos/0x144_room_data_block_updated.ksy`.

**status: ROOT CAUSE FOUND AND LIVE-CONFIRMED for the `g_pSessionManager->Init()()
failed` blocker.** The `NetMatchmaking*` opcode/size table (28 entries) is fully
mapped at high confidence. Full field-level payload schemas for the 26 opcodes
beyond ClientHello/ServerHello are NOT done this pass (out of scope/depth budget -
see "What's still open").

## The headline answer

**Message D's content (the still-unconfirmed placeholder from the ticket-server
handshake) is NOT the blocker.** `g_pSessionManager::Init()` opens a brand-new,
independent raw TCP connection with its own from-scratch hello/response handshake -
it does not read, wait on, or depend on anything from the ticket-server connection
in any way. This rules out the candidate hypothesis (b) — a message-D dependency.

**The real cause is candidate hypothesis (a): a new connection to a different
backend, and it is live-confirmed failing because nothing listens on the port
it targets.** `Init()` connects to **the same redirected host as ticket-server
(`192.168.1.100`) but on port `7314`, not `7320`**. Live RPCS3 TTY/syscall log
(`/mnt/f/rpcs3_testing/.../RPCS3.log`, run ending `5:02:05` in the most
recent capture of this pass) shows:

```
[2056.6367] connect to 192.168.1.100:7314 ...
```
immediately followed - with **no intervening error line for the connect itself** -
by the full 28-entry `NetMatchmaking*` name+size debug dump, and then:
```
sys_net: sys_net_bnet_setsockopt(s=-1, ...)
SYS: 'sys_net_bnet_setsockopt' failed with 0xfffffff7 : -SYS_NET_EBADF [1]
SYS: 'sys_net_bnet_sendto' failed with 0xfffffff7 : -SYS_NET_EBADF [1]
sys_net: sys_net_bnet_setsockopt(s=-1, ...)
SYS: 'sys_net_bnet_setsockopt' failed with 0xfffffff7 : -SYS_NET_EBADF [2]
SYS: 'sys_net_bnet_recvfrom' failed with 0xfffffff7 : -SYS_NET_EBADF [1]
recv() failed (errno=9)
sys_net: sys_net_bnet_shutdown(s=-1, how=2)   [x3, all EBADF]
g_pSessionManager->Init()() failed. ret = 0xffffffff
ERROR NET INIT ffffffff
```

`s=-1` on every syscall is the smoking gun: **no socket was ever successfully
opened for this connection.** `Init()`'s own code (see below) never checks the
return value of the connect call before blindly sending and receiving on the
resulting (invalid) connection object - so the actual failure happens silently
one step earlier (most likely inside the connect helper's own `socket()`/host-
resolve step, given the fd is `-1` rather than some allocated-but-unconnected
value), and the *visible* symptom (`recv() failed (errno=9)`, `EBADF`) is really
just the first place the code happens to check anything. Nothing about this
requires ticket-server's message D, or anything else from the already-solved
ticket-server work, to be different.

**Concrete unblock**: stand up a TCP listener on `192.168.1.100:7314` that at
minimum accepts the connection and doesn't immediately drop it. Getting all the
way through `Init()`'s own handshake (see below) additionally requires answering
its 48-byte `NetMatchmakingClientHello` with a 16-byte `NetMatchmakingServerHello`
whose first 4 bytes equal `0x12e` and whose bytes 8-11 seed the very same ARX
cipher construction already solved for ticket-server (same static key, confirmed
byte-for-byte reused - see "Key reuse" below) - i.e. this is a smaller, structurally
familiar version of the same problem already solved once.

## How this was found

### Locating `g_pSessionManager::Init()`

Starting from the two log strings of the failure itself:
- `"g_pSessionManager->Init()() failed. ret = 0x%x"` (VMA `0x00e7a320`)
- `"ERROR NET INIT %x"` (VMA `0x00e7a4f8`)

Ghidra's reference manager (`FindCallersOf.java`) shows **both strings have exactly
one code cross-reference each, and it's the same function**: `FUN_003557a8`
(`0x003557a8`) - the already-known `NetInit` orchestrator that runs the entire
ticket-server handshake documented in `docs/protocol/0x11_ticket_server_hello.md`.
This confirms Session-Manager init is not a separate subsystem living elsewhere -
it's inline in the same function, right after the ticket-server exchange.

Raw disassembly of `FUN_003557a8` around the string-load site (`0x00356338`,
reached only on the "not taken" side of `bge cr7,0x003563fc` at `0x00356334`)
shows the exact call being checked:

```
003562e4  lwz   r0,0x30(r26)      ; NpId account-info fields being copied
   ...
00356304  stw   r10,0x20(r29)     ; into the freshly `operator new(0x250d0)`'d
00356308  lwz   r0,0x40(r26)      ; object (puVar29/r29) - see "Key reuse" /
0035630c  stw   r0,0x24(r29)      ; ClientHello field-layout below, same source
00356310  lwz   r9,0x0(r8)        ; r8 = *(r29+0) = vtable ptr
00356314  lwz   r0,0x0(r9)        ; r9 = vtable[0] -> .opd descriptor
0035631c  mtspr CTR,r0            ; PPC32 ABI virtual call: this->vtable[0](this)
00356320  lwz   r2,0x4(r9)
00356324  bctrl
00356328  ld    r2,0x28(r1)
0035632c  cmpwi cr7,r3,0x0
00356330  or    r25,r3,r3
00356334  bge   cr7,0x003563fc    ; success -> skip the error log entirely
00356338  lwz   r3,-0x78bc(r30)   ; <- "g_pSessionManager->Init()() failed..." string slot
0035633c  extsw r4,r25            ; r4 = the negative return value (0xffffffff here)
```

This is `this->vtable[0](this)` - a genuine C++ virtual call, called with the
return value logged verbatim as `%x` on failure. This exactly matches the observed
`g_pSessionManager->Init()() failed. ret = 0xffffffff` (the double `()` in that
string is itself a strong hint it's a debug-build macro wrapping a virtual-call
site, further corroborating this is a real vtable dispatch, not a plain function
call).

### Identifying the object and its vtable

`r29` (the object `bctrl` is called on) is allocated a few lines earlier:
`_opd_FUN_00915ae4(0x250d0, local_67c, 8)` - `operator new(152272 bytes)` -
followed by `_opd_FUN_00ad84cc(puVar30)`, its constructor. Ghidra's TOC-chain
resolution (`ResolveTocStrings.java`, base `0x012feca0`, offset `-0x7fc4`)
resolves the vtable-pointer store inside that constructor to vtable base
**`0x01243b38`**. Dumping and decompiling the first 8 slots of that vtable
(`DumpVtableAt.java`, new tool script added this pass) gives:

| slot | function | role |
|---|---|---|
| `+0x0` | `FUN_00ad71a0` | **`Init()`** - opens the connection, runs ClientHello/ServerHello, derives the cipher state |
| `+0x4` | `FUN_00ad7604` | Poll/receive-and-dispatch loop - reads from the connection, switches on a 4-byte opcode (`0x12d`-`0x148`, confirmed below), routes to per-opcode handlers |
| `+0x8` | `FUN_00ad5a7c` | Shutdown - closes the connection object at `this+0x25060` |
| `+0xc` | `FUN_00ad5ab0` | Register a room/session slot into one of the 4 embedded sub-objects (see constructor below) |
| `+0x10` | `FUN_00ad5b78` | Build+send a room-related outbound message (`sceNpManagerGetMyLanguages`/`GetAccountRegion` used - locale-aware) |
| `+0x14` | `FUN_00ad6c70` | Similar outbound builder, smaller (0x24-byte) payload |
| `+0x18` | `FUN_00ad6718` | Another outbound builder (0x58-byte payload), room-leave-shaped |
| `+0x1c` | `FUN_00ad65e8` | Room-slot teardown, sends a 0x10-byte notification if the slot had a live connection (`+0x10 != 0`) |

The class this vtable belongs to is unambiguously the `NetMatchmaking*` /
room-management subsystem: `_opd_FUN_00ad84cc` (the constructor) zero-inits **4
identical 0x9000-byte sub-objects** (`param_1+0x50` through `param_1+0x24050`,
each with its own `FUN_00acc668`-initialized embedded connection struct at
`+0x23e4` words in) plus **one more connection object at the very end**
(`param_1+0x25060`, 0x9000-byte-aligned right after the 4 slots) - i.e. this is a
"4 concurrent room slots + 1 control connection to the matchmaking backend"
object, matching the `NetMatchmakingRoom*`/`NetMatchmakingMember*` naming exactly.
`param_1+0x25060` (the control connection) is the object every send/recv call in
`Init()` operates on.

## `Init()` (`FUN_00ad71a0`) step by step

```c
iVar7 = param_1 + 0x25060;                              // the control connection object
puVar2 = *(undefined4 **)(*(int *)(iVar8 + 0x5c) + 4);  // {ip_ptr, port} from the SAME
                                                          // net1.bin-populated service-
                                                          // descriptor table ticket-server
                                                          // (+0x7c), heartbeat (+0x48),
                                                          // leaderboard (+0x54) and
                                                          // facebook (+0x50) already use -
                                                          // this service's slot is +0x5c.
uVar6 = _opd_FUN_00acbf90(iVar7, *puVar2, puVar2[1], 0, 0);  // raw connect() - SAME
                                                               // low-level helper
                                                               // ticket-server's
                                                               // FUN_00acc424 uses.
                                                               // RETURN VALUE NEVER
                                                               // CHECKED before the
                                                               // code below runs.

// 28x _opd_FUN_00e46460(name_string, size_literal) - see "The NetMatchmaking table" below

_opd_FUN_00acb93c(iVar7, local_88 /* buffer at r1+0x98 */, 0x30, 1);  // SEND 48 bytes:
                                                                        // NetMatchmakingClientHello
_opd_FUN_00acbd98(iVar7, local_a8, 0x10, 1);   // RECV 16 bytes: NetMatchmakingServerHello.
                                                 // THIS is the call that fails with
                                                 // errno=9/EBADF when connect() above
                                                 // silently failed and left the
                                                 // connection object's socket fd at -1.
_opd_FUN_00ad55d8(local_a8);                    // byte-order fixup on the response
if (local_a8[0] == 0x12e) {                     // magic check: must equal 0x12e (302)
  uVar3 = *(key table @ 0x00ed8030);            // SAME 16-byte static key as ticket-server
  _opd_FUN_00db5ec0(uVar3, local_a0 /* resp+8 */, &local_98);   // SAME key-schedule fn
  FUN_00db7f88(&local_98, local_80, 0x24);                       // SAME digest round fn
  _opd_FUN_00acb93c(iVar7, local_b0, 8, 1);      // SEND 8 bytes: NetMatchmakingClientHello2
  *(param_1 + 0x24054) = 0;                      // reset the receive-buffer cursor
} else {
  uVar6 = 0xffffffff;
  _opd_FUN_00acbad0(iVar7);                      // close, fail
}
return uVar6;
```

Live evidence confirms exactly where this run failed: the connect log line and
the full 28-entry name+size dump both appear (so the code reached and executed
the `_opd_FUN_00e46460` loop, meaning the connect call at least *returned*
without crashing), but the very next syscalls (`setsockopt`, `sendto`) already
show `s=-1` - so the "connect" that produced the `connect to
192.168.1.100:7314 ...` log line did not actually yield a usable socket. (The
`connect to HOST:PORT ...` log line itself is printed unconditionally before the
connect attempt runs, exactly like the analogous line for ticket-server - it is
not itself evidence of success. This is the same pattern already noted for
ticket-server's own dead-IP era, see `research/notes/net1bin-server-list.md`.)

## The `NetMatchmaking*` table: 28 opcodes, sizes AND numeric IDs, fully mapped

> **2026-08-18 proto-pass supersession.** A re-disassembly pass (verified
> against the EBOOT this session) revised several rows below; where this doc
> and a `.ksy` file disagree, **the `.ksy` is authoritative** for wire layout.
> The concrete reversals of earlier hedges in this file:
> - **0x142** — name **restored to `HostRank`** (file `protos/0x142_host_rank.ksy`)
>   and **hand-confirmed live 2026-08-18**. The row-21 retraction ("never
>   confirmed, treat host-rank as retracted") is superseded: the collector
>   `FUN_0039b720` builds the u16 list from the local player slots, the shifted
>   declared-name table matches by exact size across 4 messages, and the opcode
>   was tested by hand. Only the exact numeric encoding of each per-player u16
>   remains to be pinned against a ranked-account capture.
> - **0x143 / 0x144** — the 128-byte block is a **NUL-terminated string, not an
>   opaque block**. The `_opd_FUN_00e45b10` = strcpy reading (rows 22/23 marked
>   "not reconfirmed / treat as open") was independently **re-verified** this
>   pass (two-argument word-wise NUL-scan strcpy, no length), so embedded NUL is
>   impossible by construction. Content convention `<npid>.<timestamp>`.
> - **0x13e** — the `kind` byte at offset 5 is **`3` or `4`** (a sender-path
>   discriminator: `FUN_00ad6a34` writes 3, `FUN_00ad7024` writes 4), **not** the
>   constant `3` stated in row 18 and the summary lines above.

### The size table (from the 28 `_opd_FUN_00e46460(name, size)` debug-log calls)

Confirmed **twice independently**: once via static decompilation of `Init()`'s
literal integer arguments, and once via the live RPCS3 TTY capture (authoritative -
used below; the two matched exactly wherever compared).

**Direction column (added 2026-08-15):** formalizes evidence already present
in each row's own text/decompile - server→client for the 11 opcodes the
client's own receive-dispatch (`FUN_00ad7604`) has a case for, client→server
for opcodes with a disassembled/decompiled sender and no dispatch case
(including the "5 client-to-server-only opcodes" already called out
elsewhere in this doc), and **bidirectional** for the 2 opcodes
(`RoomLeave`/0x134, `RoomSearch`/0x136) where BOTH kinds of evidence exist -
a disassembled client sender AND a client-side receive-dispatch case for the
same opcode. Not forced into a single bucket per this project's
directionality conventions; see each opcode's own `.ksy` `doc:` block for the
identical `Direction:` line.

| # | opcode (hex) | opcode (dec) | name | Direction | size (bytes) |
|---|---|---|---|---|---|
| 0 | 0x12d | 301 | `NetMatchmakingClientHello` | client→server | 48 |
| 1 | 0x12e | 302 | `NetMatchmakingServerHello` | server→client | 16 |
| 2 | 0x12f | 303 | `NetMatchmakingRoomCreate` — **sender fully disassembled 2026-08-16** (`FUN_00ad5b78`, vtable+0x10, `li r0,303` @ `0xad5c38`; send buffer base `r1+144`). Three corrections: offset **4:8 is never written** (uninitialised stack, NOT a `create_id`); offset **8:12 is the client's own room-object pointer** (live-proven equal to the debugger-recovered `ROOM_PTR`, and different per client) — this is where `Member`'s room_ptr comes from; **max_players is at 0x24** (live-constant 8, also written to `room_obj+0x1f8` by the client itself), not 0x1e. Offset 0x28 is a `strcpy` of `room_obj+0x18` (the room name); offset 0xa8:0xe8 is a verbatim copy of `room_obj+0x19fc`, which puts the confirmed team-selection field (wire 0xb0) at `room_obj+0x1a04`. `.ksy`: `protos/0x12f_room_create.ksy` | client→server | 232 |
| 3 | 0x130 | 304 | `NetMatchmakingRoomJoin` — **sender disassembled 2026-08-15** (`FUN_00ad6718`, vtable+0x18): confirmed 88 bytes. Offset 8 is NOT this family's usual 8-byte room_id - it's a raw 4-byte copy of the client's own in-process room-object pointer (an opaque local correlation value, not wire-meaningful). Offset 12 is a 1-byte room-object field; offset 16 is a raw 8-byte copy of the caller's 3rd argument (source untraced); offset 24-87 is a verbatim 64-byte copy of the room object's own bytes 0x0-0x3f. `.ksy`: `protos/0x130_room_join.ksy` | client→server | 88 |
| 4 | 0x131 | 305 | `NetMatchmakingMember` | server→client | 104 |
| 5 | 0x132 | 306 | `NetMatchmakingRoomJoined` | server→client | 160 |
| 6 | 0x133 | 307 | ~~`NetMatchmakingMemberJoined`~~ **CONFIRMED WRONG NAME — real behavior is room abandon/teardown**: fires when the client gives up on and tears down a room it's tracking, walking every member slot through the same removal path `RoomLeave` uses; not a join event. Fire-and-forget, no reply expected (a same-opcode echo was tried live, zero effect). See `research/notes/2026-08-15-room-teardown-and-flag-chain.md`. `.ksy`: `protos/0x133_room_leaving.ksy` | client→server | 120 (declared) / 16 (actual, live-confirmed) |
| 7 | 0x134 | 308 | `NetMatchmakingRoomLeave` — **decompiled 2026-08-15**: declared 16 bytes CONFIRMED WRONG, dispatch case consumes exactly 24. Looks up one member by id (offset 16) via the same `_opd_FUN_00ad0d4c` helper and removes them via `_opd_FUN_00ad3190` - the same per-member removal path 0x133's room-abandon uses, but targeting a single member rather than the whole room. Name fits. `.ksy`: `protos/0x134_room_leave.ksy` | **bidirectional** (sender disassembled AND a confirmed receive-dispatch case - see this row) | 16 (declared) / 24 (actual, decompile-confirmed) |
| 8 | 0x135 | 309 | `NetMatchmakingRoomLeft` (declared) — **live-tested 2026-08-15**: two real clients both sitting in Find Match each broadcast this opcode unprompted every ~5s (same cadence as `Ping`), actual size 36 bytes not the declared 24, payload carries a locale field (`"us"`), a repeated `0x03e8` pair, and a small mode-shaped field — shaped like a periodic find-match search-criteria advertisement/heartbeat, not a one-off "I left a room" event. Treated as the find-match broadcast trigger in `server/session_manager.py` (`FIND_MATCH_OPCODE`) until proven otherwise; the stub pairs the first two distinct searchers it sees and pushes both a real 2-member `Member`+`RoomJoined`. `.ksy`: `protos/0x135_find_match.ksy` | client→server | 24 (declared) / 36 (actual, live-confirmed) |
| 9 | 0x136 | 310 | `NetMatchmakingRoomSearch` — **decompiled 2026-08-15**: declared fixed 36 bytes CONFIRMED WRONG, this is a variable-length message (16-byte header + `num_entries` × 56-byte entries, count at offset 12). Per-entry field layout not reversed (nontrivial byte-reordering shuffle). The offset-8 field also doesn't fit this family's usual room_id-echo pattern - read and used as a raw pointer rather than compared, unresolved without a live capture. `.ksy`: `protos/0x136_room_search.ksy` | **bidirectional** (primary framing client-sent AND a confirmed receive-dispatch case - see this row) | 36 (declared, fixed) / 16 + `num_entries`×56 (actual, decompile-confirmed) |
| 10 | 0x137 | 311 | ~~`NetMatchmakingRoomSearchInfo`~~ **RENAMED 2026-08-17 — this is `Kickout`, not a search-info message**: `target_member_id@4`, `requester_member_id@6`, `room_id@8` (matching the size-16 and room_id-at-offset-8 shape already found on 2026-08-15). Server's correct reply is `Kickedout` (`0x138`) to the TARGET's connection only, gated on `requester_member_id != 0` — see "Party lifecycle" section above. **GOTCHA**: the friends-list Join flow self-fires this opcode right after `RoomJoin` with `requester_member_id=0` (a self/status message, not a real kick request); an unconditional echo-reply is the exact bug that caused the Join Party collapse (see below). This also closes the 2026-08-15 open thread noting an echo reply "had zero effect on the hang" — it had a real effect (self-kick), just not one the 2026-08-15 test conditions surfaced. `.ksy`: `protos/0x137_kickout.ksy` | client→server | 56 (declared) / 16 (actual, live-confirmed) |
| 11 | 0x138 | 312 | ~~`NetMatchmakingRoomSearchResult`~~ **RENAMED 2026-08-17 — this is `Kickedout`, not a search result.** IS one of the 11 opcodes the client's own receive-dispatch (`FUN_00ad7604`) has a case for; its handler (`0x00ad7f28`) reads `room_id@8`, finds the matching local room, and calls `RequestLeave` — which tears down the P2P link via `sceNpSignalingTerminate` (host: `SCE_NP_SIGNALING_ERROR_TERMINATED_BY_MYSELF` 0x8002a818; joiner: `..._TERMINATED_BY_PEER` 0x8002a810). Sending this unconditionally in reply to every `0x137` (the old "echo the room_id back" behavior, believing this was `RoomSearchResult`) is the confirmed root cause of the Join Party collapse — see "Party lifecycle" section above. `.ksy`: `protos/0x138_kickedout.ksy` | server→client | 16 |
| 12 | 0x139 | 313 | ~~`NetMatchmakingKickout`~~ **RENAMED 2026-08-17 — this is `RoomClosed`/`ForcedTeardown`, not `Kickout`** (the real `Kickout` is `0x137`, row 10). **Decompiled 2026-08-15**: confirmed 16 bytes, matching declared size. Room lookup by room_id (offset 8), then calls the room's vtable+0x2c callback, zeroes the room's own id fields, and runs the same full room-teardown (`_opd_FUN_00ad32c4`) 0x133's abandon path uses — a harder, server-initiated teardown (RequestLeave + zeroing slot+0x10) than a single-member kick. Server-initiated only; no client-sent request pairs with it. `.ksy`: `protos/0x139_room_closed.ksy` | server→client | 16 |
| 13 | 0x13a | 314 | **UPDATED 2026-08-17 — this is `SetPartyData`: the client publishing its own 32-byte per-member data blob (rank/title/loadout card), 80 bytes on the wire (byte 4 = blob length 0x20, bytes 16:48 = the blob).** The earlier "periodic analytics telemetry" reading conflated the message content with an unrelated caller loop (the Google-Analytics-beacon register context was in `_opd_FUN_00ad6148`'s caller, not this payload). The stub relays it per-member as `0x13b`; live-confirmed the remote member slot +0xFC is populated. See the 2026-08-16/17 banner above, `research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md`, and `research/joinparty/2026-08-15-createparty-trace.md` (caller-loop trace). `.ksy`: `protos/0x13a_member_set_data.ksy` (filename now a misnomer) | client→server | 80 (actual, live-confirmed) |
| 14 | 0x13b | 315 | ~~`NetMatchmakingRoomDestroyed`~~ **UPDATED 2026-08-17 — this is per-member DATA DELIVERY (the server→client counterpart of `0x13a`/SetPartyData), NOT room destruction.** 80 bytes; looks up one member by id (offset 4), writes a length-prefixed blob (length at offset 6, payload at offset 16) into that member's `+0xFC` (length into `+0xF8`). `+0xFC` is exactly what the lobby rank/loadout UI getter `_opd_FUN_00ad2650` reads for a REMOTE player (accepted only at length 32) — so this is the message that makes another player's rank/title/loadout render. Must follow Member (0x131), which sets the room-id lookup key. The stub sends it by relaying each client's `0x13a`. See the banner above and `research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md`. `.ksy`: `protos/0x13b_member_updated_data.ksy` (filename now a misnomer) | server→client | 80 (actual, decompile + live confirmed) |
| 15 | 0x13c | 316 | ~~`NetMatchmakingMemberSetData`~~ **NAME CONFIRMED 2026-08-17: `Promote`.** **Declared size CONFIRMED WRONG, sender disassembled 2026-08-15** (`FUN_00ad6408`, vtable+0x28): confirmed 16 bytes, not 80. The offset-4 field previously described only as a "caller-supplied u16 value" is confirmed by the 2026-08-17 dispatcher/builder audit as `new_owner_member_id` (i.e. there IS a member id in this payload, correcting the 2026-08-15 note below that read it as room-scoped-only); `room_id@8`. Paired with the server's `OwnerMemberChanged` (`0x13d`) reply. `.ksy`: `protos/0x13c_promote.ksy` | client→server | 80 (declared) / 16 (actual, disassembly-confirmed) |
| 16 | 0x13d | 317 | ~~`NetMatchmakingMemberUpdatedData`~~ **NAME CONFIRMED 2026-08-17: `OwnerMemberChanged`.** **Decompiled 2026-08-15**: declared 80 bytes CONFIRMED WRONG, dispatch case consumes exactly 16. Room lookup here matches by ROOM id (not via the member-lookup helper), and the one payload field (offset 4, `new_owner_member_id`) is written into the matched ROOM struct at `+0x19f0` — four bytes before `0x13f`/`HostFlagUpdated`'s `+0x19f4` flag. Broadcast by the server as the reply half of `Promote`/`0x13c`, alongside `HostFlagUpdated`/`0x13f`. `.ksy`: `protos/0x13d_owner_changed.ksy` | server→client | 80 (declared) / 16 (actual, decompile-confirmed) |
| 17 | 0x13e | 318 | ~~`NetMatchmakingPromote`~~ **RENAMED 2026-08-17 — this is `SetHostFlag`** (the real `Promote` is `0x13c`, which carries `new_owner_member_id@4`+`room_id@8`; that identifies `0x13e` as a distinct flag-setter, not a second promote opcode). **Two senders disassembled 2026-08-15** (`FUN_00ad6a34`/vtable+0x20, `FUN_00ad7024`/vtable+0x34): confirmed 16 bytes. `flag@4`, a const per-call-site kind byte at offset 5 (3 vs. 4), then `room_id@8`. `FUN_00ad6a34`'s variant also toggles the room's own +0x19f4 "is owner" flag locally before sending, matching what `0x13f`/`HostFlagUpdated` writes on receipt at the server side. `.ksy`: `protos/0x13e_set_host_flag.ksy` | client→server | 16 |
| 18 | 0x13f | 319 | ~~`NetMatchmakingOwnerChanged`~~ **RENAMED 2026-08-17 — this is `HostFlagUpdated`** (the real `OwnerChanged` is `0x13d`, which writes `+0x19f0`; `0x13f` writes the adjacent-but-distinct `+0x19f4` "is host" flag). **Decompiled 2026-08-15**: confirmed 16 bytes, matching declared size. Room lookup by room_id (offset 8), writes the low bit of offset-4's byte (`flag@4`) into the matched room's `+0x19f4` flag. Sent by the server as the reply to `SetHostFlag`/`0x13e` and as the broadcast half of `Promote`/`0x13c`. CORRECTED 2026-08-20 (see [[project_rejoin_party_bug]] / `research/notes/2026-08-20-rejoin-party-bug.md`): this byte is published verbatim into presence for PARTY rooms (blob offset 7) and hides the friends-list "Join Party" row for whoever advertises it nonzero, so `Promote` now sends flag=0 to every recipient (new leader included) on a party room; leadership itself is conveyed by `0x13d`'s `+0x19f0`. flag=1 is reserved for game/match rooms, whose copy of the byte never reaches presence. `.ksy`: `protos/0x13f_host_flag_updated.ksy` | server→client | 16 |
| 19 | 0x140 | 320 | ~~`NetMatchmakingSetAttrFlags`~~ **RENAMED 2026-08-17 — this is `SetRoomAttr`** (`value@4` -> `room_obj+0x1f0`; meaning of the value still UNKNOWN — do not read the earlier "several settings packed into one bitmask" framing below as confirmed). **Live-captured 2026-08-15**, only reachable once a room survives long enough to actually load into a match. Arrived matching the declared 16 bytes: opcode(4) + a 4-byte value + echoed room_id(8) (four distinct real values captured across sessions: `0x00012f78`, `0x0000197c`, `0x0001fbe0`, `0x0001fba0` — the last two differ by exactly one bit (`0x40`), consistent with one UI setting toggled once, but not confirmed as a single clean field). **Sender decompiled 2026-08-16** (`_opd_FUN_00ad62dc`, vtable+0x2c, confirmed live via vtable dump at `0x1243b38+0x2c`): gated on the SAME `room_obj+0x10` id-gate field this whole session's staleness investigation has centered on — if `room_obj+0x10 == 0` (room not yet "finalized" from the client's own perspective), the triggering UI action only writes locally (`room_obj+0x1f0 = value`, dirty flag `room_obj+0xe0 = 1`) and the message **never reaches the wire at all**; only once `room_obj+0x10` is nonzero does the same action actually transmit `0x140`. The stub replies with `RoomAttrUpdated` (`0x141`) echoing the value and room_id straight back. Which bit(s), if any, correspond to team selection is still unconfirmed and remains UNKNOWN — no static caller of `_opd_FUN_00ad62dc` found (purely vtable-dispatched); needs a live breakpoint at `0xad62dc` to resolve. Also unconfirmed: whether `room_obj+0x1f0` feeds the same per-member team array `net-game-manager.cpp:1358`'s `team >= 0 && team < NetInfo::kMaxNetTeams` assert reads (different object family, no bridging evidence found — see `research/notes/2026-08-16-net-sm-server-lobby-dispatch.md` and follow-ups). `.ksy`: `protos/0x140_set_room_flags.ksy` | client→server | 16 |
| 20 | 0x141 | 321 | ~~`NetMatchmakingUpdatedAttrFlags`~~ **RENAMED 2026-08-17 — this is `RoomAttrUpdated`** (paired with `SetRoomAttr`/`0x140`; `value@4` -> `room+0x1f0`, meaning still UNKNOWN). IS one of the 11 opcodes the client's own receive-dispatch already has a case for (unlike 0x140/0x142/0x143) — a classic "client sets X, server confirms updated X" pair; see row 19. `.ksy`: `protos/0x141_updated_room_flags.ksy` | server→client | 16 |
| 21 | 0x142 | 322 | ~~`NetMatchmakingSetRoomFlags`~~ / ~~`HostRank`~~ **RENAMED AND RE-SCOPED 2026-08-17 — this is `RoomU16ListUpload`; "HostRank" was never confirmed and should not have been used as the name.** **Declared fixed size CONFIRMED WRONG, sender disassembled 2026-08-15** (`FUN_00ad5ffc`, vtable+0x38): variable-length, a 16-byte header (opcode, a u16 `count` at offset 4, room_id at offset 8) plus `count*2` bytes of raw caller-supplied `u16[count]` payload starting at offset 16, copied via a plain memcpy-shaped helper. **Purpose of the list is UNKNOWN** — per-entry semantics were never confirmed; treat any "host rank" reading of this opcode as retracted. Fire-and-forget, no receive-dispatch case (replying would wedge the cursor — keep ignoring it). **NAME RESTORED to `HostRank` 2026-08-18 — see the supersession banner at the top of this table; this row's retraction is superseded.** `.ksy`: `protos/0x142_host_rank.ksy` | client→server | 16 (declared, fixed) / 16 + `count`×2 (actual, disassembly-confirmed) |
| 22 | 0x143 | 323 | ~~`NetMatchmakingSetRoomName`~~ **RENAMED AND RE-SCOPED 2026-08-17 — this is `SetRoomDataBlock`; the 128-byte payload is NOT confirmed to be a room name.** (declared index 24; indices 22-23 are phantom, see the correction banner at the top of this file.) ~~`NetMatchmakingUpdatedRoomFlags`~~ **declared size CONFIRMED WRONG, two senders disassembled 2026-08-15** (`FUN_00ad6f28`/vtable+0x3c, `FUN_00ad54e0`/vtable+0x40): confirmed 144 bytes, not 16. Header is opcode + room_id (offset 8); the trailing 128 bytes (offset 16-143) are a verbatim copy of the room object's own `+0x18` region — the SAME region `0x144`/`RoomDataBlockUpdated` writes on receipt, i.e. `0x143`/`0x144` are a matched upload/broadcast pair for an opaque per-room 128-byte data block, not independent boolean "room flags", and not confirmed to be the display-name string despite the earlier `strcpy`-into-`+0x18` reading noted in the 2026-08-16 banner above — treat the block's content as UNKNOWN until decoded. Despite the old declared name implying a server->client confirmation, this direction is client->server. `.ksy`: `protos/0x143_set_room_data_block.ksy` | client→server | 16 (declared) / 144 (actual, disassembly-confirmed) |
| 23 | 0x144 | 324 | ~~`NetMatchmakingUpdatedRoomName`~~ **RENAMED AND RE-SCOPED 2026-08-17 — this is `RoomDataBlockUpdated`; not confirmed to be a room name.** (declared index 25.) The handler copies the 128-byte payload into `room_obj+0x18`; the earlier claim that `_opd_FUN_00e45b10` is a plain `strcpy` (making `+0x18` "the room NAME") is NOT reconfirmed by this pass's dispatcher/builder audit and should be treated as open again — the block is opaque, general per-room data, paired with `SetRoomDataBlock`/`0x143` as the request half. Room lookup by room_id (offset 8), then copies a 128-byte block (offset 16 onward) into the matched room's struct at `+0x18` — internal layout not reversed. Sent by `server/session_manager.py`, echoing the client's own `0x143` 128-byte payload straight back (the established "echo the client's own data" pattern also used for `0x137`/`0x138` and `0x140`/`0x141` — note `0x137`/`0x138` echoing was later found to be the Join Party bug, so treat any remaining un-live-tested echo pairing in this family with appropriate caution). A live Ghidra trace found no link between this payload's destination (`room_obj+0x18`) and the separate object the client-side team-assignment array lives on, so this is not expected to bear on the team-assert boot. `.ksy`: `protos/0x144_room_data_block_updated.ksy` | server→client | 16 (declared) / 144 (actual, decompile-confirmed) |
| 24 | 0x145 | 325 | ~~`NetMatchmakingSetRoomName`~~ **wire opcode reassigned**: this table index's declared opcode (`0x145`) is not used by SetRoomName on the wire — it's the real, live-confirmed opcode for `Ping` (see the 2026-08-14 correction above and row 26). `.ksy`: `protos/0x145_ping.ksy` documents the wire-confirmed version — a bare 4-byte opcode-only fire-and-forget keepalive, client-side-timer-driven, no reply sent (`server/session_manager.py`) | client→server | 144 (declared, unused) / 4 (actual `Ping`, live-confirmed) |
| 25 | 0x146 | 326 | ~~`NetMatchmakingUpdatedRoomName`~~ **wire opcode reassigned**: this table index's declared opcode (`0x146`) is not used by UpdatedRoomName on the wire — it's the real, live-confirmed opcode for `ClientHello2` (see the 2026-08-14 correction above and row 27). `.ksy`: `protos/0x146_client_hello2.ksy` documents the wire-confirmed version — an 8-byte message, fire-and-forget (`Init()` sends it and moves on without waiting for a reply) | client→server | 144 (declared, unused) / 8 (actual `ClientHello2`, live-confirmed) |
| 26 | 0x147 | 327 | `NetMatchmakingPing` (declared) — declared opcode doesn't match the wire; the real `Ping` opcode is `0x145` (row 24), confirmed via live capture | client→server (declared opcode unused on the wire; real `Ping` is 0x145, row 24) | 4 |
| 27 | 0x148 | 328 | `NetMatchmakingClientHello2` (declared) — declared opcode doesn't match the wire; the real `ClientHello2` opcode is `0x146` (row 25), confirmed via live capture | client→server (declared opcode unused on the wire; real `ClientHello2` is 0x146, row 25) | 8 |

(There is a 29th string, `NetMatchmakingOwnerChanged` again at VMA `0x00ec8450`,
with no trailing `%i` and not part of the 28-call log loop - almost certainly an
unused/leftover duplicate string, not a real 29th opcode. Not otherwise
investigated.)

### The numeric opcode IDs (independently derived AND cross-checked against the dispatcher's own switch statement)

`ClientHello`'s own outbound magic value is a literal `0x12d` (see field layout
below); `ServerHello`'s required magic is `0x12e` (`Init()`'s
`if (local_a8[0] == 0x12e)` check). These are exactly `0x12d + 0` and `0x12d + 1`
for table indices 0 and 1 - i.e. **the opcode IDs are simply `0x12d + table index`**,
in the exact declaration order the size table above already established.

This was **mechanically verified**, not just guessed from the arithmetic
coincidence of 2 data points: the receive/dispatch function `FUN_00ad7604`
(vtable `+0x4`) is a big `if (iVar8 == 0x131) {...} else if (iVar8 == 0x132)
{...} else if (iVar8 == 0x134) {...}` chain (11 cases fully decompiled this
pass: `0x131, 0x132, 0x134, 0x136, 0x138, 0x139, 0x13b, 0x13d, 0x13f, 0x141,
0x144`). Every single one of these literals equals `0x12d + index` for the
name at that exact table index above (`0x131` = index 4 = `Member`; `0x132` =
index 5 = `RoomJoined`; `0x134` = index 7 = `RoomLeave`; `0x136` = index 9 =
`RoomSearch`; `0x138` = index 11 = `RoomSearchResult`; `0x139` = index 12 =
`Kickout`; `0x13b` = index 14 = `RoomDestroyed`; `0x13d` = index 16 =
`MemberUpdatedData`; `0x13f` = index 18 = `OwnerChanged`; `0x141` = index 20 =
`UpdatedAttrFlags`; `0x144` = index 23 = `HostRank`) - **all 11 independently
observed switch-case values match the formula exactly**, and each case's
handler body is at least directionally consistent with its predicted name
(e.g. the `0x134`/`RoomLeave` case removes a member record via
`FUN_00ad0d4c`+`FUN_00ad3190`; the `0x13f`/`OwnerChanged` case sets an
"is owner" byte at `room+0x19f4`). This is the same confidence bar
`net_event_type`'s dispatch table was confirmed at
(`docs/protocol/net_event_dispatch_and_simple_opcodes.md`) - a real,
mechanically cross-checked table, not an inferred pattern.

Confidence: **high** on all 28 opcode-ID/size pairs (two-and-three-way
cross-check: static decompile, live capture, dispatcher switch literals).
Confidence on the **remaining 24 payload field layouts** (everything except
ClientHello/ServerHello, described below): **not attempted this pass** -
each would need its own decompile+disasm pass the way ClientHello/ServerHello
got here; `FUN_00ad7604`'s handler bodies for the 11 cases above are already
decompiled in `research/ghidra/sessmgr_vtable_dump.txt` if a future pass wants
to start there instead of from scratch.

## Party lifecycle, Kick/Promote, and the Join Party root cause (2026-08-17)

**Flow:** `RoomCreate` (`0x12f`) -> server mints a UNIQUE party `room_id`
(high word `0x60000000`, replacing the old shared static `0x01387f58` value,
which made cross-connection room lookup ambiguous whenever more than one
party existed at once) -> server pushes a `Member` roster (`0x131`) with
per-entry ownership recovered via XOR of `member_id` against header
`+0x0c`/`+0x0e` -> joiner sends `RoomJoin` (`0x130`) -> server pushes a fresh
2-member roster plus `OwnerMemberChanged` (`0x13d`).

**Room capacity is enforced at `RoomJoin`, not just at search-listing time.**
The retail ceiling is 8 players in every mode, for party rooms (`0x01387f58`)
and game rooms (`0x01383bd8` and the per-build equivalents) alike; both carry
the same capacity field at `RoomCreate` offset `0x24` (live-constant 8), which
`session_manager.py` clamps to 1..8 on ingestion rather than trusting the wire
value — the same number is advertised back in `Member` wire offset 24, where a
zero trips a compiled-in client assert. The `0x136` search-result filter that
hides a full room from searchers is advisory only: it does not cover the
party-invite/direct-join path, and two searchers can both see the same last
free slot. The authoritative gate is in the `0x130` handler, taken together
with the joiner's `member_id` allocation under one lock. There is no
server→client "room full" message anywhere in the 28-entry `NetMatchmaking`
table, so a refused join is logged and answered with silence — exactly what the
"no matching room" case already does, and the joiner falls through its own join
timeout.

**Kick:** client sends `Kickout` (`0x137`) with `target_member_id@4`,
`requester_member_id@6`, `room_id@8`; server sends `Kickedout` (`0x138`) to
the TARGET's own connection only, plus `MemberLeft` (`0x134`) to every other
member of the room.

**GOTCHA — the friends-list Join flow self-fires a `0x137`.** The client's
own Join-Party code path auto-emits a `Kickout` (`0x137`) right after
`RoomJoin`, with `requester_member_id`(+6) `= 0` and `target_member_id`(+4)
`=` the joiner's own member id — this is a self/status message, not an actual
kick request. **The server MUST gate on `requester_member_id != 0`** before
acting on a `0x137`; a naive implementation that always replies to `0x137`
with a `0x138` kicks the joiner immediately, surfacing as "Unable to join
party" / "You were kicked."

**Promote:** client sends `Promote` (`0x13c`) with `new_owner_member_id@4`;
server broadcasts `OwnerMemberChanged` (`0x13d`) plus `HostFlagUpdated`
(`0x13f`). CORRECTED 2026-08-20: `0x13f`'s flag is 0 to every recipient
(new leader included) for a party room - not flag=1 to the new leader as
originally implemented, which reproduced the rejoin-party bug (blob offset 7
in presence, hides "Join Party") for whoever got promoted. See
`research/notes/2026-08-20-rejoin-party-bug.md`. Leadership itself is
`0x13d`'s `+0x19f0`, unaffected. flag=1 stays reserved for game/match rooms.

### The Join Party collapse — root cause found and fixed

The live symptom: every friends-list "Join Party" attempt collapsed roughly
15ms after the join completed, tearing the party back down. Root-caused via
RPCS3 PPU breakpoints (breakpoint at `0x3cb174` fired with `LR=0xad7fb0`,
inside the message's `0x138` handling arm) to a single, precise cause: **the
stub was replying to the client's `0x137` with a `0x138`, and `0x138` is
`Kickedout`, not a search result.**

The client's `Kickedout` handler (`0x00ad7f28`) reads `room_id@8`, finds the
matching local room object, and calls `RequestLeave` (sets
`m_leaveRequested=1`). The party state machine (state 6 at `0x3cad3c`) then
calls `LeaveRoom` (`0x3caf94`), which tears down the P2P link via
`sceNpSignalingTerminate` — the host observes
`SCE_NP_SIGNALING_ERROR_TERMINATED_BY_MYSELF` (`0x8002a818`) and the joiner
observes `SCE_NP_SIGNALING_ERROR_TERMINATED_BY_PEER` (`0x8002a810`). In
plain terms: **the server was telling the host "you've been kicked from your
own party,"** roughly 15ms after every successful join, because the old
naming (`0x137`=`RoomSearchInfo`, `0x138`=`RoomSearchResult`, see rows 10-11
below) made an unconditional room_id-echo reply look correct. It closes the
open thread in row 10 below, which noted a room_id-echo reply on `0x137` "had
zero effect on the hang" back on 2026-08-15 — it had an effect, just not the
intended one, and not one visible in that session's test conditions.

**Fix:** never send `0x138` except to deliberately kick a specific member
(and even then, gated on `requester_member_id != 0` per the GOTCHA above).

### Status (2026-08-17)

Live-confirmed working end-to-end against `server/session_manager.py` as
of this pass: **friends-list Join Party, Invite-to-Party, Promote, and Kick**
all work. Invite-to-Party uses the exact same `RoomCreate`/`RoomJoin` room
protocol as friends-list Join — it is NOT a separate PSN-only signaling path.
**View Profile and Mute produce NO session-manager traffic at all**: Profile
is served elsewhere (likely a client no-op under RPCS3, or served from the
profile pipeline noted in the 2026-08-16/17 banner above) and Mute is
client-local only.

## `NetMatchmakingClientHello` (48 bytes) - field layout

Raw disassembly of `FUN_00ad71a0` around `0xad7458`-`0xad74e4`
(`research/ghidra/sessmgr_init_raw_disasm.txt`) shows the send buffer built at
`r1+0x98` (48 bytes, offsets below relative to that base) immediately before
`_opd_FUN_00acb93c(iVar7, r1+0x98, 0x30, 1)`:

```
li r0,0x12d ; li r3,0x12d
lwz r9,0x4(r31)   lwz r11,0x8(r31)   lwz r10,0xc(r31)   lwz r8,0x10(r31)
lwz r7,0x14(r31)  lwz r6,0x18(r31)  lwz r5,0x1c(r31)   lwz r4,0x20(r31)
lwz r29,0x24(r31)
stw r0,0x98(r1)    ; offset 0
stw r9,0xa0(r1)    ; offset 8
stw r11,0xa4(r1)   ; offset 12
stw r10,0xa8(r1)   ; offset 16
stw r8,0xac(r1)    ; offset 20
stw r7,0xb0(r1)    ; offset 24
stw r6,0xb4(r1)    ; offset 28
stw r5,0xb8(r1)    ; offset 32
stw r4,0xbc(r1)    ; offset 36
stw r29,0xc0(r1)   ; offset 40
stw r25,0x9c(r1)   ; offset 4  (r25's own load site not in this excerpt)
bl 0x00a0e324 ; r3 = FUN_00a0e324(0x12d) -> re-store to offset 0 (confirmed no-op, see byte-order note below - r3 comes back unchanged)
bl 0x00a0e324 ; r3 = FUN_00a0e324(r25's value) -> re-store to offset 4 (same no-op)
```

`r31 == param_1` (this function's own `this`, confirmed at function entry:
`or r31,r3,r3`) - i.e. offsets 8-43 are a **verbatim word-for-word copy of this
SessionManager object's own fields at `+4`..`+0x24`**. Those fields are, in
turn, populated by `FUN_003557a8` (the caller) immediately after allocating
this object and *before* calling `Init()`:
```c
puVar30[1] = *(iVar25 + 0x20); puVar30[2] = *(iVar25 + 0x24);
puVar30[3] = *(iVar25 + 0x28); puVar30[4] = *(iVar25 + 0x2c);
puVar30[5] = *(iVar25 + 0x30); puVar30[6] = *(iVar25 + 0x34);
puVar30[7] = *(iVar25 + 0x38); puVar30[8] = *(iVar25 + 0x3c);
puVar30[9] = *(iVar25 + 0x40);
```
...which is the exact same 36-byte block `FUN_003557a8` itself copied, at its
very start, from `sceNpManagerGetNpId`'s output buffer into `iVar25+0x20`
through `iVar25+0x43` (see the byte-copy loop at the top of
`docs/protocol/0x11_ticket_server_hello.md`'s call chain / `netinit_full_decomp.txt`
lines 100-176). **Conclusion: `ClientHello` embeds the local player's own
`SceNpId` (online ID + reserved bytes), not anything session-manager-specific.**
This is a genuinely useful, concrete finding for anyone implementing a stub
server: the ClientHello's identity fields don't need separate handling; they're
literally the game's own already-solved NpId plumbing.

| offset | size | field | confidence |
|---|---|---|---|
| 0 | 4 | `opcode` = `0x12d` (301), passed through `FUN_00a0e324` before the final store | high (literal + explicit store) |
| 4 | 4 | `local_field` - some other `Init()`-local u32, also passed through `FUN_00a0e324`; source not traced this pass | unconfirmed |
| 8-43 | 36 | `np_id` - verbatim copy of this object's own NpId-derived fields (see above) | high (structural - same fields as the already-solved NpId copy in `FUN_003557a8`); Sony's internal `SceNpId` sub-field layout not independently re-derived here |
| 44-47 | 4 | not captured in this pass's disassembly window | unconfirmed |

**Byte order caveat: RESOLVED 2026-08-15, see
`research/notes/2026-08-15-byteswap-helper-is-a-noop.md`.** `FUN_00a0e324`
was previously assumed to byte-swap the `opcode` and offset-4 fields before
the final store, purely from the load-call-store pattern. It's now been
decompiled and disassembled at the instruction level: the entire function
body is a single `blr` (unconditional return, no-op) - it never touches the
return register at all. Every field in this message, and every other field
in this whole opcode family processed through this function or any of its
per-opcode wrapper helpers, is plain big-endian, matching this project's
`endian: be` convention with no exceptions.

## `NetMatchmakingServerHello` (16 bytes) - field layout

```c
_opd_FUN_00acbd98(iVar7, local_a8, 0x10, 1);   // recv 16 bytes into local_a8
_opd_FUN_00ad55d8(local_a8);                    // previously assumed byte-order fixup; decompiled 2026-08-15 and confirmed to be composed entirely of calls to the no-op FUN_00a0e324 - does nothing, see research/notes/2026-08-15-byteswap-helper-is-a-noop.md
if (local_a8[0] == 0x12e) {                     // offset 0: magic check
  ...
  _opd_FUN_00db5ec0(uVar3, local_a0, &local_98);  // local_a0 = offset 8, used as the counter/seed
```

| offset | size | field | confidence |
|---|---|---|---|
| 0 | 4 | `opcode` - **must equal `0x12e` (302)** or `Init()` fails immediately (`uVar6 = 0xffffffff; close`) | high (explicit compare in decompile) |
| 4 | 4 | unconfirmed - declared (`local_a8[1]`) but not read by any branch traced this pass | unconfirmed |
| 8 | 4 | `session_seed` - fed directly as the counter argument to the SAME key-schedule function (`FUN_00db5ec0`) that keys ticket-server's ARX cipher, analogous to that protocol's `session_token`/`client_nonce` | high (structural - direct argument to a fully-solved function), semantics of "what value the server should pick" unconfirmed (never captured) |
| 12 | 4 | not read in the traced portion of `Init()` | unconfirmed |

## Key reuse: the SAME static ARX key as ticket-server, confirmed at a second address

`Init()`'s key-schedule call uses a 16-byte static key table resolved (same
TOC-chain method as ticket-server's key) to VMA **`0x00ed8030`**:

```
78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89
```

This is **byte-for-byte identical** to the ticket-server family's key at
`0x00ed7a50` (documented in `docs/known-keys.md`) - same 16 bytes, different
rodata address (the compiler/linker apparently emitted two separate copies of
this constant array for two different translation units, rather than one
shared symbol). This means **`server/lib/ticket_cipher.py`'s already-solved and
verified key-schedule/round functions apply unchanged to the
NetMatchmaking/SessionManager protocol** - no new cipher reversal needed, only
new framing (this family's post-ServerHello frames were not decompiled this
pass to see if they use the exact same 20-byte-header frame format as
ticket-server's messages C/D, or something simpler - flagged as the natural
next step). See `docs/known-keys.md` for the updated key entry.

## What's still open (prioritized)

1. **Stand up a TCP stub listener on `192.168.1.100:7314`** that accepts the
   connection and returns a well-formed `NetMatchmakingServerHello` (opcode
   `0x12e` at offset 0, anything at offset 4, a chosen `session_seed` at offset
   8) - this is the single concrete action that would let live testing get
   past `g_pSessionManager::Init()` for the first time. (This pass kept
   `server/ticket_server.py` and the other live-testing files
   deliberately untouched - this is a note for the follow-up
   implementation work, not a change made here.)
2. ~~Decompile `FUN_00ad55d8`~~ **DONE 2026-08-15**: `FUN_00ad55d8` (the
   assumed ServerHello byte-order-fixup) is composed entirely of calls to
   the no-op `FUN_00a0e324` - it does nothing; see
   `research/notes/2026-08-15-byteswap-helper-is-a-noop.md`. Still open: the
   remaining unread bytes of `ClientHello` (offsets 4 and 44-47) and
   `ServerHello` (offsets 4 and 12) - unconfirmed content, not unconfirmed
   byte order.
3. **Determine whether post-ServerHello frames on this connection use the same
   20-byte-header encrypt-then-MAC frame as ticket-server's messages C/D**, or
   send `NetMatchmakingClientHello2`/subsequent messages some other way -
   `Init()`'s own `_opd_FUN_00acb93c(iVar7, local_b0, 8, 1)` call for
   `ClientHello2` looks like a RAW send (same low-level helper as ClientHello
   itself), not a call through the `FUN_00acb6fc` frame-builder ticket-server
   uses - worth confirming explicitly rather than assuming either way.
4. ~~Full field-level payload schemas for the other 26 `NetMatchmaking*`
   opcodes~~ **DONE for all 28 opcodes as of 2026-08-15.** All 11 opcodes
   `FUN_00ad7604` (vtable `+0x4`) has decompiled receive-dispatch cases for
   now have `.ksy` files, and so do the remaining 5 that never appear in
   that dispatcher (`RoomJoin`/0x130, `MemberSetData`/0x13c, `Promote`/0x13e,
   `SetRoomFlags`/0x142, `UpdatedRoomFlags`/0x143) - these turned out to be
   client-to-server-only sends, found by extending the vtable dump from 8 to
   24 slots (`research/ghidra/sessmgr_vtable_extended.txt` - the real
   vtable ends at `+0x40`; slots `+0x44` onward read into unrelated memory,
   same class of dead end as the 2026-08-15 address-probe note below) and
   disassembling each candidate sender at the instruction level
   (`research/ghidra/sender_disasm.txt`, `research/ghidra/room_flags_disasm.txt`)
   to confirm exact field offsets rather than relying on size/name
   coincidence alone. This closed out RoomCreate's/RoomSearch's/RoomJoin's
   sibling outbound builders too and found two more size corrections
   (0x13c: declared 80 actually 16; 0x142/0x143: both declared-wrong) plus
   one more likely name mismatch (0x13c, room-scoped not member-scoped) and
   one cross-opcode pairing worth a live capture to confirm (0x143's 128-byte
   payload is the exact same room+0x18 region 0x144/HostRank populates).

   Genuinely still open: only the 4 remaining non-networking vtable slots
   the extended vtable dump also decompiled by accident (`+0x50` onward -
   Havok-shaped interpolation/sorting code, unrelated to this class, not
   investigated). The internal byte-order question this item used to flag
   is now CLOSED - see the dedicated entry immediately below.

   **Byte-order question, RESOLVED 2026-08-15**: every doc in this family
   (including this one, until now) took "`_opd_FUN_00a0e324` is the
   per-field byteswap helper" on faith from call-pattern consistency alone,
   without ever decompiling it. It's now been decompiled AND disassembled at
   the instruction level, along with its sibling `_opd_FUN_00a0e320` and
   every per-opcode wrapper helper built on top of them
   (`_opd_FUN_00ad6e34`/Member, `_opd_FUN_00ad58c8`/RoomLeave,
   `_opd_FUN_00ad5920`/RoomJoined, `_opd_FUN_00ad5730`/RoomSearch,
   `_opd_FUN_00ad55d8`/ServerHello): all of them are confirmed no-ops (the
   two base functions are each a single `blr` instruction; every wrapper is
   composed entirely of calls to them and nothing else). **No runtime
   byte-swapping happens anywhere in this opcode family, ever** - every
   field is plain big-endian, exactly matching this project's `endian: be`
   convention with no exceptions. Full evidence:
   `research/notes/2026-08-15-byteswap-helper-is-a-noop.md`.
5. **Resolve the service-descriptor `+0x5c` slot's exact IP/port encoding** in
   `net1.bin`'s binary layout (the way ticket-server's `+0x7c` slot was never
   directly decoded either - both were only confirmed via live capture of the
   resulting `connect to HOST:PORT` log line, not by reading `net1.bin`'s raw
   bytes). Not needed for the immediate unblock (the live capture already
   gives the real host:port), but would let a future net1.bin repack redirect
   this service explicitly rather than relying on it already resolving to the
   same patched host as ticket-server.

## Ruled out this pass

- **Session Manager depends on ticket-server message D's payload** - ruled
  out. `Init()` opens its own connection, runs its own hello/response
  handshake, and derives its own cipher seed from its own ServerHello
  response (`local_a0`, offset 8) - nothing here reads ticket-server's
  connection object, message D's buffer, or anything cached from that
  handshake.
- **RPCN already implements this** - ruled out. `grep -ril "7314\|NetMatchmaking"`
  across the RPCN source (case-sensitive on `NetMatchmaking`, excluding the build
  directory's incidental fingerprint-hash matches on `7314`) finds nothing.
  RPCN's own `room_manager.rs`/`cmd_room.rs` implement Sony's standard
  `sceNpMatching2` protocol (a different, unrelated NP subsystem - see the
  "ruled out" section of `docs/protocol/0x11_ticket_server_hello.md` from the
  earlier pass), and this `NetMatchmaking*` family is a raw custom TCP
  protocol multiplexed the same way ticket-server is (not going through any
  `sceNpMatching2`/`sceNpSignaling` call) - confirming it is genuinely new
  protocol surface needing a from-scratch stub, same conclusion as
  ticket-server.
