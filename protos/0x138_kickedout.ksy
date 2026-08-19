meta:
  id: kickedout
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingKickedout - server -> client, over the Session Manager
  connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for; handler confirmed at
  0x00ad7f28.

  RENAMED from the earlier (wrong) `room_search_result` identity - the
  16-byte size and room_id-at-offset-8 shape were previously mistaken for a
  RoomSearchResult reply to RoomSearchInfo (see 0x137_kickout.ksy for the
  matching correction on the request side).

  The recipient's dispatcher at 0x00ad7f28 matches the room by id (offset
  8) and calls RequestLeave, i.e. the recipient leaves the room named by
  this message. THIS MESSAGE MUST BE ROUTED TO THE KICKED MEMBER ONLY - it
  carries no target member id of its own, so a server must send it
  exclusively on the kicked client's own connection, never broadcast to the
  whole room (broadcasting it would make every member leave).

  Compare 0x139/RoomClosed, which uses the harder full-teardown path
  (zeroes the room slot and fires an additional vtable callback) - this
  message is the lighter "you personally are out" notification.
  LIVE-VERIFIED 2026-08-18 (first retained capture of this opcode being sent -
  it was previously disassembly-only, because the standing rule is to never send
  it). A deliberate "Kick from Party" produced the correct exchange:

    21:43:22.209  in   conn1  0x137 Kickout target=2 requester=1
    21:43:22.210  out  conn2  0x138 Kickedout        <- to the TARGET only
    21:43:22.211  out  conn1  0x134 RoomLeave member_id=2

  The target left, the remaining member stayed, and the party survived - which
  is the positive control for the Join Party rule: 0x138 is correct precisely
  when it IS a kick, addressed to the member being kicked. Sending it to anyone
  else (in particular as a reply/ack to the requester, the historical bug) makes
  that member kick itself out of its own room. Live payload:
  `00000138 00000000 6000000101387f58` - pad_4 zero, room_id echoed.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x138 (312 decimal)."
  - id: pad_4
    size: 4
    doc: "Offset 4:8. Alignment padding. DEFINITION: the 4-byte gap before the 8-byte-aligned room_id (wire 8). REASON: the 0x138 receive arm reads only room_id (`ld r3,8(r29)` @0xad7f50); offset 4 is never loaded, it just aligns room_id. Send 0. (Was `unknown_4`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Matched against the connection's room slots by the 0x00ad7f28 handler; on a match, that room is left via RequestLeave."
