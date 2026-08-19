meta:
  id: room_joined
  endian: be
  license: CC0-1.0
  imports:
    - common/member_data
    - common/np_id
doc: |
  Direction: server-to-client

  NetMatchmakingRoomJoined - server -> client reply sent over the Session
  Manager connection (port 7314) in response to RoomCreate (0x12f) and
  presumably also RoomJoin (0x130), confirming the player is now a member of
  a room. Field layout decompiled from FUN_00ad7604 (SessionManager's
  receive-dispatch loop, vtable+0x4 at base 0x01243b38), the `iVar8 == 0x132`
  case.

  STATUS: total size (120 bytes, from the buffer-advance amount) and the
  room_id echo requirement (room-slot matching compare) are confirmed
  mechanically from the decompile. CORRECTED 2026-08-18: the message body is
  the same shape as one 0x131 roster entry - a 36-byte SceNpId (`attributes`),
  the member id, a length byte, then the 32-byte member_data card - not an
  "18x u16 attribute block + name buffer". The 20 bytes of the SceNpId past
  the online-id handle are copied verbatim into the member slot with untraced
  readers (see np_id.ksy); everything else is decoded.

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
  - id: pad_4
    type: u4
    doc: "Offset 4:8. Alignment padding. DEFINITION: the 4-byte gap before the 8-byte-aligned room_id. REASON: the LIVE 0x132 receive arm (@0xad7ac0, calling FUN_00ad33d8) reads room_id at `ld r3,8(r29)` @0xad7ae4 and never loads offset 4 - it just aligns room_id. (NB: it is the stub's build_room_joined that is dead code, not the client's receive handler, which is live.) Send 0. (Was `unknown_field`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. The server-assigned room id, matched against `*(s64*)(room_obj+0x10)` across the connection's 4 room slots (the dispatch does nothing if no slot matches) - this is how the client correlates the reply with a room it is tracking. CORRECTED 2026-08-18: renamed from `create_id`, which claimed it must equal a RoomCreate `create_id` field - but 0x12f has no such field (its offset 4 is uninitialised stack). room_obj+0x10 is set only by Member (0x131); this is the same room_id-echo used by 0x134/0x139/0x13d/0x13f."
  - id: attributes
    type: np_id
    doc: "Offset 0x10:0x34. The joining member's 36-byte SceNpId (see common/np_id.ksy), copied into the local struct passed to _opd_FUN_00ad33d8 as param_2+4. CONFIRMED 2026-08-16: the FIRST 16 BYTES ARE THE ONLINE-ID HANDLE - the dedupe key (`_opd_FUN_00e459bc`) and, because this handler passes is_local=0, the value fed to the NP signaling-connection resolve at 0x00ad34a4. Putting the RECIPIENT'S OWN NpId here makes the client signal itself (SCE_NP_SIGNALING_ERROR_OWN_NP_ID) - this message is about OTHER players joining, never yourself. (The 20 bytes past the handle are copied verbatim into the member slot; their readers are untraced - see np_id.ksy.)"
  - id: member_id
    type: u2
    doc: "Offset 0x34-0x35. CONFIRMED 2026-08-16: `lhz r0,36(r29)` @ 0x00ad7b4c where r29 = wire+0x10, i.e. wire offset 52. Stored as the joining member's own id (local struct +0x38, then slot+0xe8 in _opd_FUN_00ad33d8). Previously lumped into an unnamed 4-byte `flags_field`. Must be unique within the room and distinct from every member_id already registered via Member (0x131) - it is the key 0x134/RoomLeave and 0x13b look members up by."
  - id: member_slot_ec
    type: u1
    doc: "Offset 0x36. DEFINITION: the 0x131-entry+0x38 analog - a byte the client copies into member_slot+0xEC (`lbz r9,38(r29)` @0xad7b50 -> reg-struct+0x40 -> `stw r0,236(r31)` @0xad34f8), the SAME writer as `0x131`'s `member_slot_ec` - see protos/0x131_member.ksy for the full field-level doc. REASON it exists: a real server->client field, but member_slot+0xEC has no reader. RE-VERIFIED 2026-08-19 by an independent whole-binary search for the distinctive member-slot-address arithmetic (`room_obj+0x668+slot_index*0x180`), not just the original instruction-band grep - still write-only, still inert. Send 0. (Was `unknown_byte_36`.)"
  - id: member_data_length
    type: u1
    doc: "Offset 0x37. The length of the member_data card that follows at 0x38. CORRECTED 2026-08-18 (was `unknown_byte_37`): the 0x132 handler builds the byte-for-byte identical local struct as the 0x131 per-entry loop - it sets `local_e0 = *(byte*)(wire+0x37)` and `local_e4 = wire+0x38`, exactly as 0x131 sets `local_e0 = entry+39` (the established member_data length) and `local_e4 = entry+40` (the member_data blob), and hands both to the same registration call `_opd_FUN_00ad33d8`. Evidence: research/ghidra/sessmgr_vtable_dump.txt lines 266-305 vs 214-245. Live 32 - the card UI getter demands exactly 32."
  - id: member_data
    type: member_data
    doc: "Offset 0x38:0x58. The joining member's 32-byte rank/faction card (full decode in common/member_data.ksy), NOT a room-name string. CORRECTED 2026-08-18: this region is the member_data blob (`local_e4 = wire+0x38`, copied into the member slot exactly like 0x131 entries), retiring the earlier '<npid>.<timestamp>' name-echo theory. A server should send the joiner's real card here (the same 32 bytes it puts in 0x131/0x13b)."
  - id: trailing_tail
    size: 32
    doc: "Offset 0x58:0x78. The 32-byte tail after the member_data card, mirroring 0x131's member_data_padding (the member slot field is 64 bytes but only the first 32 are meaningful). Send zero."
