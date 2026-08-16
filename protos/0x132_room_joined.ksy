meta:
  id: room_joined
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingRoomJoined - server -> client reply sent over the Session
  Manager connection (port 7314) in response to RoomCreate (0x12f) and
  presumably also RoomJoin (0x130), confirming the player is now a member of
  a room. Field layout decompiled from FUN_00ad7604 (SessionManager's
  receive-dispatch loop, vtable+0x4 at base 0x01243b38), the `iVar8 == 0x132`
  case.

  STATUS: total size and the create_id echo requirement are confirmed
  mechanically from the decompile (buffer-advance amount, room-slot matching
  compare). The 18x u16 "attribute" block and trailing name region are
  observed to be READ by the client (passed into a local struct and a helper
  call) but their semantic meaning/required values were not traced - this
  project's stub (tools/session_manager_stub.py, build_room_joined()) sends
  them zeroed/best-effort and this has NOT been confirmed to work against a
  live client yet.

  IMPORTANT CORRECTION: the opcode/size debug-log table (see
  session_manager_and_matchmaking.md) claims this message is 160 bytes. That
  is WRONG - the dispatch code's own buffer-advance amount
  (`received - 0x78`) is authoritative and gives 120 bytes. Third such
  correction found this session (after ClientHello2 and Ping) - don't trust
  the debug table for opcodes past the initial handshake without an
  independent check.
doc-ref: ../docs/protocol/0x132_room_joined.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x132 (306 decimal)."
  - id: unknown_field
    type: u4
    doc: "Offset 4. Referenced by OTHER dispatch cases (e.g. 0x13b RoomDestroyed) as a u16-shaped 'room index' field, but not read anywhere in the traced 0x132 case itself. Unconfirmed for this opcode - stub sends zero."
  - id: create_id
    size: 8
    doc: "Offset 8. MUST equal the corresponding RoomCreate request's own create_id field (see 0x12f_room_create.ksy) - mechanically confirmed: the dispatch code searches the connection's 4 room slots for `*(longlong*)(slot+0x10) == *(longlong*)(msg+8)` and silently does nothing further if no match is found. This is how the client correlates the reply with its pending create/join request."
  - id: attributes
    size: 36
    doc: "Offset 0x10-0x33. 18x u16 fields, read into a local struct (auStack_d8) and passed to _opd_FUN_00ad33d8 along with two flag bits derived by XOR-comparing offsets 0x0e/0x0c against a room-id-shaped value at param_1+0x24066/0x24064. Semantics not traced - likely room settings (game mode/team/slot counts) given RoomCreate's own payload has a similarly-sized cluster of plausibly-related fields, but the two messages' offsets don't line up 1:1 so no direct mapping was attempted. Stub sends zero; if the client validates these against what it itself requested, zero may be rejected untested."
  - id: flags_field
    size: 4
    doc: "Offset 0x34-0x37. A u16 (local_a0) + 2 more bytes (local_98, local_e0/flags byte). Unconfirmed. Stub sends zero."
  - id: trailing
    size: 64
    doc: "Offset 0x38-0x77 (56 bytes into the message through the end at 120 bytes total). The client stores a pointer to this region (local_e4) rather than reading fixed sub-fields directly in the traced excerpt - likely a name/string buffer. Stub fills this with the same '<npid>.<timestamp>' string RoomCreate itself sent (echoed back), on the unconfirmed theory this is meant to be the room's display name."
