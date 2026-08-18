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
  the value of a host-configurable lobby attribute (a room setting the host just
  changed) so the server can store it on the room and advertise it to searchers.
  0x141 is the server's confirming echo. The wire carries an attribute SELECTOR
  (4:6) plus the attribute VALUE (6:8).

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

  CORRECTION 2026-08-18 - offset 6:8 is NOT uninitialised stack. A prior pass
  (2026-08-16) read 6:8 as garbage because a small sample looked random. The
  live server log (server/logs/session_manager.log) DISPROVES that: 6:8 takes
  STRUCTURED, REPRODUCIBLE values - `ff50 fbe0 2f78` recur as an ordered sequence
  across two separate solo-host lobby sessions, and two values (`0x2f78`,
  `0xfbe0`) reproduce across captures taken on different days. Uninitialised
  stack does not reproduce across reboots, so 6:8 is a real client->server field
  the retail server consumed. Logged 6:8 values: ff50 / fbe0 / 2f78 (room
  012723d8...), 03f0 / 0030 / 4fe0 (room 012a426c...). The selector at 4:6 was
  0x0001 in every 2026-08-18 capture (an earlier capture also saw 0x0000).

  MEANING of the 6:8 value: still capture-dependent. It is a real lobby-setting
  payload, but which host option it encodes is not statically recoverable (no
  EBOOT branch reads room_obj+0x1f0; the sender's caller is pure vtable dispatch)
  and our logs are all solo-host, so the value can't yet be tied to a specific
  toggle. Resolve by changing ONE lobby option at a time and diffing 6:8 (see
  docs/capture-howto.md, "0x140 room-attribute value").

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
  - id: attr_value
    type: u2
    doc: "Offset 6:8. The attribute payload the client sends to the server (client->server only; the client never reads it back). REPRODUCIBLE, not stack garbage: logged values ff50/fbe0/2f78 (recurring in order) and 03f0/0030/4fe0, with 2f78/fbe0 reproduced across different-day captures. Encodes a host-set lobby option; which one is capture-dependent (see doc, toggle-one-and-diff)."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Matches the room_id this server assigned via Member's header - echoed back verbatim in the stub's UpdatedAttrFlags reply."
