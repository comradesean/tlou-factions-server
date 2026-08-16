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
stub's reply are in `tools/session_manager_stub.py`'s `build_room_joined()`; several
fields (an 18x-`u16` "attribute" block, offset 16:52) are still unconfirmed/zeroed -
see that function's docstring and the note for what's still open.

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
in any way. This rules out coordinator hypothesis (b) from the task brief.

**The real cause is coordinator hypothesis (a): a new connection to a different
backend, and it is live-confirmed failing because nothing listens on the port
it targets.** `Init()` connects to **the same redirected host as ticket-server
(`192.168.1.100`) but on port `7314`, not `7320`**. Live RPCS3 TTY/syscall log
(`/mnt/f/rpcs3_testing/.../RPCS3.log`, run ending `5:02:05` in this session's most
recent capture) shows:

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

Starting from the two log strings in the task brief:
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
return value logged verbatim as `%x` on failure. This exactly matches the brief's
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
| 2 | 0x12f | 303 | `NetMatchmakingRoomCreate` | client→server | 232 |
| 3 | 0x130 | 304 | `NetMatchmakingRoomJoin` — **sender disassembled 2026-08-15** (`FUN_00ad6718`, vtable+0x18): confirmed 88 bytes. Offset 8 is NOT this family's usual 8-byte room_id - it's a raw 4-byte copy of the client's own in-process room-object pointer (an opaque local correlation value, not wire-meaningful). Offset 12 is a 1-byte room-object field; offset 16 is a raw 8-byte copy of the caller's 3rd argument (source untraced); offset 24-87 is a verbatim 64-byte copy of the room object's own bytes 0x0-0x3f. `.ksy`: `protos/0x130_room_join.ksy` | client→server | 88 |
| 4 | 0x131 | 305 | `NetMatchmakingMember` | server→client | 104 |
| 5 | 0x132 | 306 | `NetMatchmakingRoomJoined` | server→client | 160 |
| 6 | 0x133 | 307 | ~~`NetMatchmakingMemberJoined`~~ **CONFIRMED WRONG NAME — real behavior is room abandon/teardown**: fires when the client gives up on and tears down a room it's tracking, walking every member slot through the same removal path `RoomLeave` uses; not a join event. Fire-and-forget, no reply expected (a same-opcode echo was tried live, zero effect). See `research/notes/2026-08-15-room-teardown-and-flag-chain.md`. `.ksy`: `protos/0x133_room_leaving.ksy` | client→server | 120 (declared) / 16 (actual, live-confirmed) |
| 7 | 0x134 | 308 | `NetMatchmakingRoomLeave` — **decompiled 2026-08-15**: declared 16 bytes CONFIRMED WRONG, dispatch case consumes exactly 24. Looks up one member by id (offset 16) via the same `_opd_FUN_00ad0d4c` helper and removes them via `_opd_FUN_00ad3190` - the same per-member removal path 0x133's room-abandon uses, but targeting a single member rather than the whole room. Name fits. `.ksy`: `protos/0x134_room_leave.ksy` | **bidirectional** (sender disassembled AND a confirmed receive-dispatch case - see this row) | 16 (declared) / 24 (actual, decompile-confirmed) |
| 8 | 0x135 | 309 | `NetMatchmakingRoomLeft` (declared) — **live-tested 2026-08-15**: two real clients both sitting in Find Match each broadcast this opcode unprompted every ~5s (same cadence as `Ping`), actual size 36 bytes not the declared 24, payload carries a locale field (`"us"`), a repeated `0x03e8` pair, and a small mode-shaped field — shaped like a periodic find-match search-criteria advertisement/heartbeat, not a one-off "I left a room" event. Treated as the find-match broadcast trigger in `tools/session_manager_stub.py` (`FIND_MATCH_OPCODE`) until proven otherwise; the stub pairs the first two distinct searchers it sees and pushes both a real 2-member `Member`+`RoomJoined`. `.ksy`: `protos/0x135_find_match.ksy` | client→server | 24 (declared) / 36 (actual, live-confirmed) |
| 9 | 0x136 | 310 | `NetMatchmakingRoomSearch` — **decompiled 2026-08-15**: declared fixed 36 bytes CONFIRMED WRONG, this is a variable-length message (16-byte header + `num_entries` × 56-byte entries, count at offset 12). Per-entry field layout not reversed (nontrivial byte-reordering shuffle). The offset-8 field also doesn't fit this family's usual room_id-echo pattern - read and used as a raw pointer rather than compared, unresolved without a live capture. `.ksy`: `protos/0x136_room_search.ksy` | **bidirectional** (primary framing client-sent AND a confirmed receive-dispatch case - see this row) | 36 (declared, fixed) / 16 + `num_entries`×56 (actual, decompile-confirmed) |
| 10 | 0x137 | 311 | `NetMatchmakingRoomSearchInfo` — **live-tested 2026-08-15**: client sends this unprompted after `Member`/`RoomJoined`; actual size 16 bytes not the declared 56, tail 8 bytes exactly match the room_id assigned via `Member`. The stub echoes that room_id back as `RoomSearchResult` (0x138), but a room_id-echo reply was tried live and had zero effect on the "Searching for Optimal Game"/"Starting Game" hang — `0x133`'s room-abandon (row 6 above) is the more likely actual cause of that hang, not a missing reply here. **Sender confirmed 2026-08-16** as a byproduct of decompiling 0x140's sender (`_opd_FUN_00ad64f4`, vtable+0x24, adjacent slot). `.ksy`: `protos/0x137_room_search_info.ksy` | client→server | 56 (declared) / 16 (actual, live-confirmed) |
| 11 | 0x138 | 312 | `NetMatchmakingRoomSearchResult` — IS one of the 11 opcodes the client's own receive-dispatch (`FUN_00ad7604`) has a case for; its handler searches a 4-slot local array by an 8-byte key at wire offset 8, matching the room_id-echo shape the stub sends. `.ksy`: `protos/0x138_room_search_result.ksy` | server→client | 16 |
| 12 | 0x139 | 313 | `NetMatchmakingKickout` — **decompiled 2026-08-15**: confirmed 16 bytes, matching declared size. Room lookup by room_id (offset 8), then calls the room's vtable+0x2c callback, zeroes the room's own id fields, and runs the same full room-teardown (`_opd_FUN_00ad32c4`) 0x133's abandon path uses. Name fits ("you're kicked, tear down"). `.ksy`: `protos/0x139_kickout.ksy` | server→client | 16 |
| 13 | 0x13a | 314 | `NetMatchmakingKickedout` (declared) — **CONFIRMED WRONG, real purpose still unnamed but is NOT party/kick-related**: originally nicknamed "CreateParty" after appearing to correlate with the in-game party-invite action, but a live breakpoint trace of the actual sender (`_opd_FUN_00ad6148`, called from `0x003B17CC`/`0x003B17E0`) proved it fires on a periodic UI-transition tick from the main menu onward, independent of party or room state — the caller's own register context holds a literal Google Analytics beacon URL string (`"GET /__utm.gif?..."`). This is periodic analytics telemetry, not party creation or a kick notice; the original correlation was timing coincidence. Fire-and-forget, no reply behavior ever demonstrated to matter. See `research/notes/2026-08-15-createparty-trace.md`. `.ksy`: `protos/0x13a_periodic_telemetry.ksy` | client→server | 16 |
| 14 | 0x13b | 315 | ~~`NetMatchmakingRoomDestroyed`~~ **NAME QUESTIONABLE, decompiled 2026-08-15**: declared 16 bytes CONFIRMED WRONG, dispatch case consumes exactly 80. Looks up ONE member by id (offset 4, via the same `_opd_FUN_00ad0d4c` helper 0x134/RoomLeave uses), then stashes a length-prefixed blob (length byte at offset 6, payload at offset 16+) onto that member's own struct - per-member data delivery, not room-wide destruction. No confirmed alternate name. `.ksy`: `protos/0x13b_room_destroyed.ksy` | server→client | 16 (declared) / 80 (actual, decompile-confirmed) |
| 15 | 0x13c | 316 | ~~`NetMatchmakingMemberSetData`~~ **declared size CONFIRMED WRONG, sender disassembled 2026-08-15** (`FUN_00ad6408`, vtable+0x28): confirmed 16 bytes, not 80. Sends a caller-supplied u16 "value" (offset 4) plus the room's own room_id (offset 8, raw/unswapped) - no per-member id anywhere in this payload, so despite the declared name this is room-scoped, not member-scoped (same class of naming mismatch as 0x13b/0x13d). `.ksy`: `protos/0x13c_member_set_data.ksy` | client→server | 80 (declared) / 16 (actual, disassembly-confirmed) |
| 16 | 0x13d | 317 | ~~`NetMatchmakingMemberUpdatedData`~~ **NAME QUESTIONABLE, decompiled 2026-08-15**: declared 80 bytes CONFIRMED WRONG, dispatch case consumes exactly 16. Room lookup here matches by ROOM id (not via the member-lookup helper), and the one payload field (offset 4) is written into the matched ROOM struct at +0x19f0 - four bytes before 0x13f/OwnerChanged's +0x19f4 flag. Looks like a room-level attribute next to ownership state, not a per-member update. No confirmed alternate name. `.ksy`: `protos/0x13d_member_updated_data.ksy` | server→client | 80 (declared) / 16 (actual, decompile-confirmed) |
| 17 | 0x13e | 318 | `NetMatchmakingPromote` — **two senders disassembled 2026-08-15** (`FUN_00ad6a34`/vtable+0x20, `FUN_00ad7024`/vtable+0x34): confirmed 16 bytes, matching declared size, from both call sites. A flag byte (offset 4, promote/demote-shaped) and a fixed per-call-site tag byte (offset 5: 3 vs. 4) precede the usual room_id (offset 8). `FUN_00ad6a34`'s variant also toggles the room's own +0x19f4 "is owner" flag (the same flag 0x13f/OwnerChanged sets) locally before sending. Name fits. `.ksy`: `protos/0x13e_promote.ksy` | client→server | 16 |
| 18 | 0x13f | 319 | `NetMatchmakingOwnerChanged` — **decompiled 2026-08-15**: confirmed 16 bytes, matching declared size. Room lookup by room_id (offset 8), writes the low bit of offset-4's byte into the matched room's +0x19f4 "is owner" flag - the same flag already referenced by this doc's own dispatch-table cross-check further below. Name and behavior agree cleanly. `.ksy`: `protos/0x13f_owner_changed.ksy` | server→client | 16 |
| 19 | 0x140 | 320 | `NetMatchmakingSetAttrFlags` — **live-captured 2026-08-15**, only reachable once a room survives long enough to actually load into a match. Arrived matching the declared 16 bytes: opcode(4) + a 4-byte flags value + echoed room_id(8) (four distinct real values captured across sessions: `0x00012f78`, `0x0000197c`, `0x0001fbe0`, `0x0001fba0` — the last two differ by exactly one bit (`0x40`), consistent with one UI setting toggled once, but not confirmed as a single clean field; the full 20-bit spread across all four looks like several settings packed into one bitmask). **Sender decompiled 2026-08-16** (`_opd_FUN_00ad62dc`, vtable+0x2c, confirmed live via vtable dump at `0x1243b38+0x2c`): gated on the SAME `room_obj+0x10` id-gate field this whole session's staleness investigation has centered on — if `room_obj+0x10 == 0` (room not yet "finalized" from the client's own perspective), the triggering UI action only writes locally (`room_obj+0x1f0 = value`, dirty flag `room_obj+0xe0 = 1`) and the message **never reaches the wire at all**; only once `room_obj+0x10` is nonzero does the same action actually transmit `0x140`. Practical implication: a stale/never-finalized room can silently swallow whatever this flags value represents (plausibly team-select) before it ever becomes a network event, independent of anything the stub replies. The stub currently replies with `UpdatedAttrFlags` (0x141) echoing the flags value and room_id straight back, matching the room_id-echo pattern already used for `RoomSearchInfo`/`RoomSearchResult` — implemented but not yet confirmed to unblock anything downstream. Which bit(s), if any, correspond to team selection is still unconfirmed — no static caller of `_opd_FUN_00ad62dc` found (purely vtable-dispatched); needs a live breakpoint at `0xad62dc` to resolve. Also unconfirmed: whether `room_obj+0x1f0` (a SessionManager room-slot field) feeds the same per-member team array `net-game-manager.cpp:1358`'s `team >= 0 && team < NetInfo::kMaxNetTeams` assert reads (different object family, no bridging evidence found yet — see `research/notes/2026-08-16-net-sm-server-lobby-dispatch.md` and follow-ups). `.ksy`: `protos/0x140_set_attr_flags.ksy` | client→server | 16 |
| 20 | 0x141 | 321 | `NetMatchmakingUpdatedAttrFlags` — IS one of the 11 opcodes the client's own receive-dispatch already has a case for (unlike 0x140/0x142/0x143) — a classic "client sets X, server confirms updated X" pair; see row 19. `.ksy`: `protos/0x141_updated_attr_flags.ksy` | server→client | 16 |
| 21 | 0x142 | 322 | ~~`NetMatchmakingSetRoomFlags`~~ **declared fixed size CONFIRMED WRONG, sender disassembled 2026-08-15** (`FUN_00ad5ffc`, vtable+0x38): variable-length, a 16-byte header (opcode, a u16 `num_entries` at offset 4, room_id at offset 8) plus `num_entries*2` bytes of raw caller-supplied payload, copied via a plain memcpy-shaped helper. Per-entry semantics unconfirmed. `.ksy`: `protos/0x142_set_room_flags.ksy` | client→server | 16 (declared, fixed) / 16 + `num_entries`×2 (actual, disassembly-confirmed) |
| 22 | 0x143 | 323 | ~~`NetMatchmakingUpdatedRoomFlags`~~ **declared size CONFIRMED WRONG, two senders disassembled 2026-08-15** (`FUN_00ad6f28`/vtable+0x3c, `FUN_00ad54e0`/vtable+0x40): confirmed 144 bytes, not 16. Header is opcode + room_id (offset 8); the trailing 128 bytes (offset 16-143) are a verbatim copy of the room object's own +0x18 region - the SAME region 0x144/HostRank writes into on receipt, suggesting these two opcodes are a matched send/receive pair for the same rank/host-priority table, not independent boolean "room flags". Despite the declared name implying a server->client confirmation, this is client->server. `.ksy`: `protos/0x143_updated_room_flags.ksy` | client→server | 16 (declared) / 144 (actual, disassembly-confirmed) |
| 23 | 0x144 | 324 | `NetMatchmakingHostRank` — **decompiled 2026-08-15**: declared 16 bytes CONFIRMED WRONG, dispatch case consumes exactly 144. Room lookup by room_id (offset 8), then copies a 128-byte block (offset 16 onward) into the matched room's struct at +0x18 - internal layout not reversed, but declared name is plausible for a 128-byte per-member rank/host-priority table. **Never sent by this project's stub before 2026-08-16** - a confirmed-real message the original server would have sent that ours simply never implemented. Now sent (`tools/session_manager_stub.py`), echoing the client's own `0x143` 128-byte payload straight back, matching this family's established "echo the client's own data" pattern (`0x137`/`0x138`, `0x140`/`0x141`) - EXPERIMENTAL, not yet live-tested; a live Ghidra trace found no link between this payload's destination (`room_obj+0x18`, SessionManager's own room-slot object) and the separate object the client-side team-assignment array lives on, so this is not expected to fix the team-assert boot specifically, but it's still a real protocol gap worth closing on its own. `.ksy`: `protos/0x144_host_rank.ksy` | server→client | 16 (declared) / 144 (actual, decompile-confirmed) |
| 24 | 0x145 | 325 | ~~`NetMatchmakingSetRoomName`~~ **wire opcode reassigned**: this table index's declared opcode (`0x145`) is not used by SetRoomName on the wire — it's the real, live-confirmed opcode for `Ping` (see the 2026-08-14 correction above and row 26). `.ksy`: `protos/0x145_ping.ksy` documents the wire-confirmed version — a bare 4-byte opcode-only fire-and-forget keepalive, client-side-timer-driven, no reply sent (`tools/session_manager_stub.py`) | client→server | 144 (declared, unused) / 4 (actual `Ping`, live-confirmed) |
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
shared symbol). This means **`tools/ticket_cipher.py`'s already-solved and
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
   past `g_pSessionManager::Init()` for the first time. (Per this task's "hands
   off" list, `tools/ticket_server_stub.py` and the other live-testing files
   were explicitly not touched this pass - this is a note for whoever picks up
   the implementation work next, not a change made here.)
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
   this session's dump also decompiled by accident (`+0x50` onward -
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
- **RPCN already implements this** - ruled out. `grep -ril "7314\|NetMatchmaking"
  backend/rpcn/` (case-sensitive on `NetMatchmaking`, excluding the build
  directory's incidental fingerprint-hash matches on `7314`) finds nothing.
  RPCN's own `room_manager.rs`/`cmd_room.rs` implement Sony's standard
  `sceNpMatching2` protocol (a different, unrelated NP subsystem - see the
  "ruled out" section of `docs/protocol/0x11_ticket_server_hello.md` from the
  prior session), and this `NetMatchmaking*` family is a raw custom TCP
  protocol multiplexed the same way ticket-server is (not going through any
  `sceNpMatching2`/`sceNpSignaling` call) - confirming it is genuinely new
  protocol surface needing a from-scratch stub, same conclusion as
  ticket-server.
