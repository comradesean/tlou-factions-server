# `NetMatchmakingRoomCreate` (opcode `0x12f`)

Companion doc for `protos/0x12f_room_create.ksy`.

**status: sender fully disassembled 2026-08-16** (`FUN_00ad5b78`, vtable+0x10,
`li r0,303` @ `0xad5c38`, send buffer base `r1+144`) — superseding the earlier
"transcribed from one capture" state. Three field corrections below; full
evidence in `research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md`.

## What this is

Sent by the client over the Session Manager connection (port 7314), after the
initial `ClientHello`/`ServerHello`/`ClientHello2` handshake, when the player
chooses to host a game - live-observed right after the
`NET_SM_READY_UP` -> `NET_SM_CREATE_GAME_WAIT` lobby-flow transition
(`game/net/lobby-flow.cpp`, confirmed via the live RPCS3 TTY log). Fixed 232
bytes, matching the opcode/size debug-log table's declared size exactly (this
opcode's table entry is trustworthy, unlike its neighbors - see
`session_manager_and_matchmaking.md`'s corrections).

## Confirmed fields (from the disassembled sender)

- Offset 0: opcode, literal `0x12f`.
- **Offset 4:8 — NOT a `create_id`, and NOT load-bearing (CORRECTED 2026-08-16).**
  The sender never writes it; it is uninitialised stack, live-proven varying
  between `01 27 23 d8` and `00 00 00 00` on the same client. The earlier
  "RoomJoined must echo this" reading was wrong (see the correction in
  `0x132_room_joined.md`); the stub's `room_id` only needs to be nonzero and
  session-consistent.
- **Offset 8:12 — the client's own room-object pointer** (`stw` of the room
  object `r29` @ `0xad5f34`). This is the value `Member`'s `room_ptr` field
  needs — read it per connection from here instead of hardcoding. Live-proven
  equal to the debugger-recovered pointer and different per client (comradesean
  `01 38 3b d8`, mgnomad2 `01 38 7f 58`; both are static globals in this build).
- **Offset 0x24 — `max_players`** (u16, live-constant 8), which the client also
  writes into `room_obj+0x1f8` itself. The earlier read at offset 0x1e was a
  never-written gap (masked by the stub's `or 8` fallback).
- Offset 0x28: a null-terminated ASCII string `<npid>.<unix-timestamp>` (e.g.
  `comradesean.1786732043`), `strcpy`'d from `room_obj+0x18` — the room NAME.
- Offset 0xb0 (u16): the CONFIRMED team-selection field (`0x0000` unset /
  `0x0001` Blue / `0x0002` Red — ~24 live captures, see
  `research/notes/2026-08-16-team-selection-field-confirmed.md`). Copied by the
  sender into `room_obj+0x1a04` via the 0xa8:0xe8 block.

## Unconfirmed

The remaining spans (a region code `us`, other u16-shaped fields, and
pointer-shaped 4-byte values) are not individually mapped but are no longer
load-bearing for the working host/join flow. Full raw hexdump:
`research/notes/2026-08-14-room-create-joined.md`.

## Confidence summary

| Field | Confidence | Reason |
|---|---|---|
| Opcode (`0x12f`) / total size (232 bytes) | high | Matches the debug-log table exactly, and this opcode's table entry is explicitly noted as trustworthy (unlike several neighboring opcodes - see `session_manager_and_matchmaking.md`'s corrections) |
| Offset 4:8 is NOT a `create_id` (uninitialised stack, not load-bearing) | high | Disassembled sender never writes it; live-proven varying on the same client — corrected 2026-08-16 |
| Offset 8:12 is the client's own room-object pointer | high | `stw` of the room object at the send site; live-proven equal to the debugger value and per-client distinct |
| `max_players` at offset 0x24 (not 0x1e) | high | Disassembled sender; also written to `room_obj+0x1f8` by the client itself |
| `<npid>.<timestamp>` room name (offset 0x28) | high | `strcpy` from `room_obj+0x18` at the send site |
| Team selection (offset 0xb0, u16) | high | ~24 live captures, zero exceptions |
| Region code (`us`), other u16/pointer-shaped spans | low | Not individually traced; not load-bearing for the working flow |

Overall: **high** for the fields the working host/join flow depends on (all
disassembled from the sender); the remainder of the 232-byte payload is
untraced but inert.
