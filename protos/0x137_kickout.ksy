meta:
  id: kickout
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingKickout - "Kick from Party" request, client -> server, over
  the Session Manager connection (port 7314). Sender builder confirmed at
  0x00ad6570 (`li r9,311` / `li r3,311` @ 0x00ad6570-0x00ad6574, buffer base
  r1+112, 16-byte send at 0x00ad65bc).

  RENAMED from the earlier (wrong) `room_search_info` identity - the
  16-byte size and room_id-at-offset-8 shape were previously mistaken for a
  RoomSearchInfo message. Disassembly-verified opcode map corrects this:
  0x137 is the client's kick request, and its former "unknown offset 4:8"
  region decodes into two separate u16 member-id fields, not one opaque
  4-byte unknown.

  A `requester_member_id` of 0 is NOT a real user-initiated kick - it is the
  join flow's own auto-emitted status message, sent as a side effect of
  joining rather than as a deliberate "kick this member" action from the
  UI. Only treat this as a genuine kick request when requester_member_id is
  a real (nonzero) member id.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x137 (311 decimal). `li r9,311` / `li r3,311` @ 0x00ad6570/0x00ad6574."
  - id: target_member_id
    type: u2
    doc: "Offset 4:6. The member id being kicked from the party/room."
  - id: requester_member_id
    type: u2
    doc: "Offset 6:8. The member id requesting the kick. A value of 0 marks this as the join flow's own auto-emitted status message, NOT a genuine user-initiated kick - see doc-level note."
  - id: room_id
    type: u8
    doc: "Offset 8:16. The room the target/requester both belong to - same room_id-echo pattern used throughout this opcode family."
