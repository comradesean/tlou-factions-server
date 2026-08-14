# `NetMatchmakingRoomCreate` (opcode `0x12f`)

Companion doc for `protos/0x12f_room_create.ksy`.

**status: partial** - size and two fields confirmed from one live capture; the
bulk of the payload is transcribed but not decompiled from the send site.

## What this is

Sent by the client over the Session Manager connection (port 7314), after the
initial `ClientHello`/`ServerHello`/`ClientHello2` handshake, when the player
chooses to host a game - live-observed right after the
`NET_SM_READY_UP` -> `NET_SM_CREATE_GAME_WAIT` lobby-flow transition
(`game/net/lobby-flow.cpp`, confirmed via the live RPCS3 TTY log). Fixed 232
bytes, matching the opcode/size debug-log table's declared size exactly (this
opcode's table entry is trustworthy, unlike its neighbors - see
`session_manager_and_matchmaking.md`'s corrections).

## Confirmed fields

- Offset 0: opcode, literal `0x12f`.
- Offset 4-11 (`create_id`): an 8-byte client-generated value. Live-captured
  as `01 27 23 d8 01 38 3b d8`. Confirmed important (not just noise) because
  the required `RoomJoined` (`0x132`) reply must echo this exact value at its
  own offset 8, or the client's room-slot matching fails - see
  `0x132_room_joined.md`.
- A null-terminated ASCII string, `<npid>.<unix-timestamp>` (e.g.
  `comradesean.1786732043`), starting around relative offset 0x1c within the
  payload. Presumed a session/room name; echoed back verbatim by the stub's
  `RoomJoined` reply.

## Unconfirmed

Everything else - a region code (`us`), several u16-shaped fields that look
like counts/limits, and multiple 4-byte spans that look like raw PS3 heap
pointers (`0x01xxxxxx`/`0xd0xxxxxx`-shaped) rather than meaningful protocol
data. None of this was traced from the send-site decompile; the `.ksy` treats
it as one opaque blob. Full raw hexdump and reasoning:
`research/notes/2026-08-14-room-create-joined.md`.

## What would close this out

Decompile the client's own build site for this message (likely one of the
`Init()` vtable's outbound-builder slots, `+0xc`/`+0x10`/`+0x14`/`+0x18`, or a
separate function called from `game/net/lobby-flow.cpp`'s `NET_SM_READY_UP`
transition) to get real field semantics instead of transcribing one capture.
