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
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x138 (312 decimal)."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not read by the traced portion of the 0x138 dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Matched against the connection's room slots by the 0x00ad7f28 handler; on a match, that room is left via RequestLeave."
