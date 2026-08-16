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

  *** DO NOT USE THIS AS THE RoomCreate REPLY (2026-08-16) ***

  This handler calls `_opd_FUN_00ad33d8` with `is_local = 0` and
  `is_owner = 0` HARDCODED (`li r5,0; li r6,0` @ 0x00ad7bdc/0x00ad7be8) -
  because RoomJoined is semantically "some OTHER player joined the room you
  are in", never "you joined". Two consequences, both confirmed against live
  wire bytes in captures/tcp_catch.log:

  1. is_local=0 sends this message's NpId (offset 0x10, 16 bytes) through the
     NP signaling-connection resolve at 0x00ad34a4. If that NpId is the
     recipient's own, the client tries to open signaling to itself and Sony's
     API rejects it (SCE_NP_SIGNALING_ERROR_OWN_NP_ID).

  2. `_opd_FUN_00ad33d8` dedupes purely by NpId and returns immediately on a
     hit without updating anything. So a RoomJoined carrying the host's real
     NpId followed by a Member whose own entry has a zeroed NpId (the
     stub's deliberate self-skip) produces TWO occupied member slots for a
     one-player room - one with the real NpId and no local/owner flags, one
     with a blank NpId that is flagged local+owner. `_opd_FUN_00ad0fd0` and
     `_opd_FUN_00ad1024` then both report 2 players.

  Member (0x131) alone is sufficient for room creation: it establishes the
  room pointer, room id and capacity, registers the roster WITH correct
  local/owner flags, and fires the room-create-completed callback via the
  one-shot latch at 0x00ad79ec. See
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 3.

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
    doc: "Offset 0x10-0x33. 18x u16 fields (`lhz` x18 from wire+0x10 in steps of 2, 0x00ad7b4c-0x00ad7bf0), copied into the local struct passed to _opd_FUN_00ad33d8 as param_2+4. CORRECTED 2026-08-16: the FIRST 16 BYTES ARE THE JOINING MEMBER'S SceNpId HANDLE - it is the dedupe key (`_opd_FUN_00e459bc`) and, because this handler passes is_local=0, the value fed to the NP signaling-connection resolve at 0x00ad34a4. Putting the RECIPIENT'S OWN NpId here therefore makes the client signal itself (SCE_NP_SIGNALING_ERROR_OWN_NP_ID). This message is about OTHER players joining, never about yourself."
  - id: member_id
    type: u2
    doc: "Offset 0x34-0x35. CONFIRMED 2026-08-16: `lhz r0,36(r29)` @ 0x00ad7b4c where r29 = wire+0x10, i.e. wire offset 52. Stored as the joining member's own id (local struct +0x38, then slot+0xe8 in _opd_FUN_00ad33d8). Previously lumped into an unnamed 4-byte `flags_field`. Must be unique within the room and distinct from every member_id already registered via Member (0x131) - it is the key 0x134/RoomLeave and 0x13b look members up by."
  - id: unknown_byte_36
    type: u1
    doc: "Offset 0x36. `lbz r9,38(r29)` -> local struct +0x40 -> slot+0xec. Unconfirmed."
  - id: unknown_byte_37
    type: u1
    doc: "Offset 0x37. `lbz r7,39(r29)` @ 0x00ad7bec -> stored into a secondary local struct. Unconfirmed."
  - id: trailing
    size: 64
    doc: "Offset 0x38-0x77 (56 bytes into the message through the end at 120 bytes total). The client stores a pointer to this region (local_e4) rather than reading fixed sub-fields directly in the traced excerpt - likely a name/string buffer. Stub fills this with the same '<npid>.<timestamp>' string RoomCreate itself sent (echoed back), on the unconfirmed theory this is meant to be the room's display name."
