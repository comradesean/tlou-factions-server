meta:
  id: set_attr_flags
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetAttrFlags - sent by the client over the Session Manager
  connection (port 7314). Live-captured for the first time 2026-08-15,
  only reachable once a room survives long enough to actually load into a
  match (see research/notes/2026-08-15-room-teardown-and-flag-chain.md and
  the RPCS3 "Stub PPU Traps" workaround that finally got a client this
  far).

  STATUS: 16 bytes total, confirmed live. NOT one of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for (unlike its
  reply, UpdatedAttrFlags/0x141) - client-to-server only.

  CORRECTION 2026-08-16 - the payload is a u16, not a 4-byte bitmask.
  The sender `_opd_FUN_00ad62dc` (vtable +0x2c) was disassembled at the
  instruction level this pass. Its send buffer base is r1+112:

      ad636c:  stw  r0,112(r1)     ; offset 0 = 0x140
      ad6374:  sth  r28,116(r1)    ; offset 4 = (u16)param_3   <- 2 BYTES
      ad6370:  std  r9,120(r1)     ; offset 8 = room_obj+0x10  (8 bytes)
      ad63a8:  li   r5,16          ; 16 bytes sent

  Offset 6:8 is NEVER WRITTEN - uninitialised stack. The 0x141 handler
  agrees: `lhz r3,4(r29)` @ 0x00ad82ec, zero-extended into room_obj+0x1f0.

  This retires the "several settings packed into one bitmask" reading. The
  four live values 0x00012f78 / 0x0000197c / 0x0001fbe0 / 0x0001fba0
  decompose as (0x0001, 0x2f78) / (0x0000, 0x197c) / (0x0001, 0xfbe0) /
  (0x0001, 0xfba0): a u16 field taking only 0 and 1, followed by garbage.
  The apparently random 20-bit spread lived entirely in the garbage half,
  and the 0x40 single-bit difference between the last two values was
  coincidence in uninitialised memory - not a UI toggle.

  Gating (unchanged, still confirmed): if `room_obj+0x10 == 0` the action
  only writes locally (`room_obj+0x1f0 = value`, dirty flag
  `room_obj+0xe0 = 1`) and nothing reaches the wire at all.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x140 (320 decimal). Confirmed live, big-endian."
  - id: value
    type: u2
    doc: "Offset 4:6. `sth r28,116(r1)` @ 0x00ad6374 - the low 16 bits of the sender's 3rd argument. Live values: 0 and 1 only. Written into room_obj+0x1f0 by the 0x141 reply's handler (zero-extended)."
  - id: uninitialised_2
    size: 2
    doc: "Offset 6:8. NEVER WRITTEN by the sender - uninitialised stack. Not read by the 0x141 handler either. Ignore."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Matches the room_id this server assigned via Member's header - echoed back verbatim in the stub's UpdatedAttrFlags reply."
