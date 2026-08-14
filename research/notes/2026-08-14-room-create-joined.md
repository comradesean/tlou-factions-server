# "Lobby Server Error" root-caused: RoomCreate needs a RoomJoined reply

Follow-up to `2026-08-14-voice-server-discovery.md`. With the port-7313 hang fixed,
live testing got much further: game-data version load, level sync, NAT detection,
host lobby-flow states (`NET_SM_READY_UP` -> `NET_SM_CREATE_GAME_WAIT` ->
`NET_SM_CHOOSE_HOST_JOIN`) - then pressing "Start Game" produced "Lobby Server Error".

## The one-line answer

The client sends `NetMatchmakingRoomCreate` (opcode `0x12f`, 232 bytes - matches the
declared table size exactly) over the Session Manager connection and gets nothing
back. `session_manager_stub.py` was only handling the initial handshake; anything
sent afterward was logged and ignored. The client's own timeout on the pending
create request is what surfaces as "Lobby Server Error" - confirmed by finding that
exact string in the game's own localization data (see below), sitting right next to
"The host left the game." / "Some party members failed to join the game." - i.e. it's
a generic member of the client's own `kNetLobbyFail` reason enum
(`flag >= 0 && flag < kNetLobbyFailCount`, `game/net/lobby-flow.cpp`), not a crash.

Fix: `session_manager_stub.py` now recognizes `RoomCreate` and replies with a
best-effort `NetMatchmakingRoomJoined` (opcode `0x132`). See `build_room_joined()`'s
docstring in that file for the full field-level writeup - short version below.

## How "Lobby Server Error" was actually found (not obvious - no hits in the compiled
binary's own strings)

`grep -i "lobby server\|server error" research/strings/strings_ascii.txt` found
nothing - the string isn't in the ELF at all. It turned out to live in a
*localization* bundle: `build/main/text1/2.networking.crypt`, which the client fetches
over HTTP during NetInit (already being live-fetched-and-cached by `catch_http.py`'s
upstream-proxy fallback from the earlier level-sync fix). That file isn't a PSARC
archive - `psarc_crypt.py decrypt` still applies (same 24-byte header + Blowfish
wrapper, HMAC verifies OK), but the decrypted payload is a flat encrypted text table,
not a `PSAR`-magic container - so `extract`/`unpack` don't apply, just decrypt then
`strings` the result directly. Worth remembering as a technique: any other UI string
that doesn't show up in the eboot's own strings dump is probably in one of these
`textN/M.category.crypt` bundles, not missing from the binary.

## Debugging method note: the stub was itself hiding the evidence

Two bugs in `session_manager_stub.py` masked this for a while:
1. The post-handshake idle timeout was 10 seconds. Real usage involves minutes of
   menu navigation between the handshake and the next real message - the stub was
   closing the connection long before the client ever got to sending `RoomCreate`,
   so early tests saw no error-causing traffic at all. Bumped to 600s.
2. The connection's log entry was only written in the `finally` block, i.e. only
   once the connection *closed*. With a long-lived connection, nothing was visible
   while it was still open (which is most of the time) - had to restructure to an
   `emit()` helper that writes+flushes immediately per message, not just at the end.

Once both were fixed, the very next live attempt showed the real `RoomCreate` payload
and the periodic `Ping` (`0x145`) keepalives, live, while the connection was still
open - this is what let the actual field-level decompile happen against real data
instead of a guess.

## RoomJoined (0x132) field layout - from decompiling `FUN_00ad7604`

Wire offsets relative to the message's own opcode field (offset 0):

| offset | size | field | confidence |
|---|---|---|---|
| 0 | 4 | opcode = `0x132` | high |
| 4 | 4 | unknown - referenced by *other* opcodes (e.g. `0x13b`) as a u16 "room index"-shaped field, not read in this specific case in the traced decompile | unconfirmed, left zero |
| 8 | 8 | room/transaction id - MUST match `RoomCreate`'s own offset 4:12 (mechanically confirmed: the dispatch code searches the 4 room slots for `*(longlong*)(slot+0x10) == *(longlong*)(msg+8)`) | high (structural), semantics of "who assigns this id" unconfirmed - stub just echoes what the client itself sent |
| 16 | 36 | 18x `u16` "attribute" fields, read into a local struct and passed to `_opd_FUN_00ad33d8` | unconfirmed, left zero - if the client validates these against its own RoomCreate request, zero may be rejected |
| 52 | 4 | u16 + 2 flag bytes | unconfirmed, left zero |
| 56 | 64 | trailing buffer, treated as a pointer/string region by the client | unconfirmed - stub fills with the "npid.timestamp" name string echoed from RoomCreate's own offset 0x28, on the theory a room name is being echoed |

**Confirmed by decompile, not by guessing**: total consumed size is `0x78` = 120 bytes
- the dispatch code's own buffer-shift amount
(`_opd_FUN_00e3e064(puVar21, param_1+0x240d0, received-0x78)`) is authoritative and
contradicts the earlier session's "declared size 160" from the opcode/size debug-log
table. Third instance this session of that debug table being wrong for a specific
opcode (after `ClientHello2` and `Ping`'s opcode corrections) - **the size/opcode
table should not be trusted for any opcode without an independent check**, only the
11 already-cross-referenced switch-statement literals (`0x131`-`0x144`) and the two
handshake opcodes are solid.

Only `RoomJoined` is sent, not a follow-up `Member` (`0x131`) roster broadcast.
`RoomJoined`'s own handler already builds and registers a member-shaped local struct
(`_opd_FUN_00ad33d8`), which reads as self-sufficient for "you are now in this room" -
but this is unconfirmed against actual live client behavior past this point.

## Ping (0x145) and ClientHello2 (0x146) - confirmed no reply needed

Traced the `Ping` send site directly: it's gated by a client-side timer check
(`if (*(float*)(param_1+0x25058) < ...)`) inside the *receive* dispatch function
itself, sent proactively on a schedule, not waiting for or expecting any response.
`Init()`'s own code for `ClientHello2` (see the main doc) doesn't `recv()` after
sending it either. Both are safe to leave unanswered - now logged as "no reply sent,
here's why" instead of just a raw hexdump, to save the next person from wondering.

## What's still open

1. **Confirm the RoomJoined guess actually works live** - not tested this pass (can't
   drive RPCS3 from here). If the client still errors, check `captures/tcp_catch.log`
   for what it sends *next* over the same connection - either it accepted the room
   and moved on to something else, or it rejected this reply and the next thing to
   check is whether the 18 unconfirmed attribute fields need real values.
2. **The 18x u16 attribute block (offset 16:52) semantics** - RoomCreate's own payload
   has a cluster of plausibly-related fields in a similar relative region (region code
   "us", counts, what look like port numbers and 1000/1000-shaped limits) but the
   offsets don't line up 1:1 between the two message layouts, so no direct mapping was
   attempted this pass - flagged rather than guessed.
3. **Whether a second real player can actually join** - this session only exercises
   the solo-host path. `RoomSearch`/`RoomSearchResult`/`RoomJoin`/`MemberJoined` are
   still completely unimplemented; a real second connection would need those.
4. Many fields in the real captured `RoomCreate` payload look like raw PS3 heap
   pointers (`0x01xxxxxx`/`0xd0xxxxxx`-shaped) rather than meaningful protocol data -
   worth keeping in mind for future opcodes too: not every non-zero field is
   information the server needs to interpret.

## Raw evidence

- `research/ghidra/sessmgr_vtable_dump.txt` - already existed from the prior pass,
  has the full `FUN_00ad7604` decompile including the `0x132` case used here.
- `captures/tcp_catch.log` - live capture of the real `RoomCreate` payload, the
  `Ping`/`ClientHello2` traffic, and (once tested) whatever the client does with the
  stub's `RoomJoined` reply.
- `tools/served_content/build/main/text1/2.networking.crypt` - the decrypted
  localization bundle containing "Lobby Server Error" and its neighbors.
