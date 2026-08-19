meta:
  id: set_room_flags
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

  DEFINITION / PURPOSE: "set one room attribute". The client tells the server
  which host-configurable lobby attribute changed, so the server can store it on
  the room and advertise it to searchers. 0x141 is the server's confirming echo.
  The only payload the wire actually carries is the attribute SELECTOR at 4:6;
  offset 6:8 is leaked stack, not a value (see below).

  WIRE STRUCTURE (sender `_opd_FUN_00ad62dc`, vtable +0x2c; send buffer base
  r1+112):
      ad636c:  stw  r0,112(r1)     ; offset 0 = 0x140
      ad6374:  sth  r28,116(r1)    ; offset 4 = (u16) selector
      ad6370:  std  r9,120(r1)     ; offset 8 = room_obj+0x10  (8 bytes)
      ad63a8:  li   r5,16          ; 16 bytes sent
  The 0x141 handler reads back only offset 4:6 (`lhz r3,4(r29)` @ 0x00ad82ec)
  into room_obj+0x1f0 (which no consumer branch ever reads - so the client-side
  effect of the round trip is inert; the ACTION is the value delivered to the
  server at 6:8).

  OFFSET 6:8 IS SENDER-SIDE RESIDUE (settled 2026-08-18, second pass). An
  intermediate revision promoted 6:8 to a real client->server attribute value
  because its values recurred across captures taken on different days. That
  inference was wrong: a leaked POINTER reproduces exactly on a deterministic
  emulator, so cross-session reproducibility cannot distinguish a real field from
  leaked stack. See research/notes/2026-08-18-wire-residue-and-field-corrections.md
  for the statistical proof (99% of these gap words are valid PS3 addresses, and
  the client's own PPU dump gives the matching stack range 0xd0001000-0xd0040fff).

  The larger capture (355 frames) refutes the field reading directly:
    - ROOM-INDEPENDENT. The same five values appear against the static party room
      012723d8... and against ~25 distinct synthesized public room ids
      (50000001... through 50000030...). An attribute that is identical for every
      room ever created is not an attribute of the room.
    - CALL-SITE DETERMINED, not setting determined: `fbe0` follows a prior 0x140
      in 28/28 cases, `197c` follows a 0x13a in 4/4 cases, and the cycle
      ff50 -> fbe0 -> 2f78 repeats per lobby regardless of any host choice.
    - Only 5 distinct values across 355 frames: ff50 (x238), 2f78 (x74),
      fbe0 (x28), 197c (x4), 3954 (x1).
  The `sth` at 4:6 overwrites the HIGH half of whatever pointer occupied the
  slot, which is exactly why only a plausible low half is ever visible on the
  wire. The selector at 4:6 was 0x0001 in every 2026-08-18 capture (an earlier
  capture also saw 0x0000).

  Gating (unchanged, still confirmed): if `room_obj+0x10 == 0` the action
  only writes locally (`room_obj+0x1f0 = selector`, dirty flag
  `room_obj+0xe0 = 1`) and nothing reaches the wire at all.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x140 (320 decimal). Confirmed live, big-endian."
  - id: attr_selector
    type: u2
    doc: "Offset 4:6. `sth r28,116(r1)` @ 0x00ad6374 - low 16 bits of the sender's 3rd argument. The only half the client reads back (from the 0x141 echo, into room_obj+0x1f0, which is then never branched on). Logged 0x0001 in all 2026-08-18 captures; an earlier capture saw 0x0000. Selects/tags which room attribute is being set."
  - id: pad_6
    type: u2
    doc: "Offset 6:8. NOT A FIELD - sender-side residue. DEFINITION: the low half of a stale pointer left in the reused send buffer at r1+118; the builder's only stores are wire 0 (`stw`), wire 4:6 (`sth` selector) and wire 8:16 (`std` room_id), and the selector's `sth` clobbers the pointer's high half, leaving its low half on the wire. REASON: unwritten gap between the 2-byte selector and the 8-byte-aligned room_id. Live: 5 distinct values in 355 frames (ff50/2f78/fbe0/197c/3954), identical across ~25 different rooms, and call-site-determined (fbe0 follows a prior 0x140 28/28). Send 0. (Was `attr_value`; see research/notes/2026-08-18-wire-residue-and-field-corrections.md §2.)"
  - id: room_id
    size: 8
    doc: "Offset 8:16. Matches the room_id this server assigned via Member's header - echoed back verbatim in the stub's UpdatedAttrFlags reply."
