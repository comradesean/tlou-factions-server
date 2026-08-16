meta:
  id: member_updated_data
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingMemberUpdatedData (declared name) - server -> client, over
  the Session Manager connection (port 7314). One of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: declared size in the Init() size table is 80 bytes - CONFIRMED
  WRONG. The dispatch case requires >15 buffered bytes and consumes exactly
  16.

  NAME RESOLVED 2026-08-16: this is an OWNER-DESIGNATION message - "the room
  owner is now member id X". `OwnerMemberChanged` fits; the declared
  `MemberUpdatedData` does not. Evidence (see
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 7):

  - `room_obj+0x19f0`, the field this message writes, is independently
    written by `_opd_FUN_00ad33d8` (member registration) at 0x00ad37dc from
    the member_id of whichever roster entry carried Member's (0x131)
    `is_owner` flag:
        if (is_owner != 0) *(u32*)(room_obj+0x19f0) = *(u32*)(new_slot+0xe8);
    (`slot+0xe8` is that member's own id.) Four bytes earlier,
    `room_obj+0x19ec` gets the same treatment from `is_local` - so
    +0x19ec = "my member id", +0x19f0 = "the owner's member id".

  - `_opd_FUN_00ad0d98(room_obj)` is a dedicated lookup that walks the 12
    member slots (stride 0x180, base +0x668) returning the one whose
    `slot+0xe8` equals `*(u32*)(room_obj+0x19f0)` - i.e. "get the room
    owner's member record". It is used by `_opd_FUN_003cb528`, which then
    compares that member's id against `room_obj+0x19ec` to decide whether the
    local player is the owner.

  So the room lookup being by ROOM id is correct and expected: the message is
  room-scoped, and its payload names a member.

  This is a DIFFERENT and complementary piece of ownership state from
  0x13f/OwnerChanged, which writes the boolean `room_obj+0x19f4` ("am I the
  host"). Neither is currently sent by tools/session_manager_stub.py.

  SIDE EFFECT worth noting: unlike Member's silent write of the same field,
  this handler also fires `room_obj->vtable[0x34]()` after the store
  (0x00ad8254 -> shared virtual-call tail at 0x00ad8070) - a client-side
  notification callback Member does not trigger.

  SEQUENCING: room_obj+0x10 is set only by Member's (0x131) handler. Sending
  this before a Member means the 4-slot search finds nothing and the message
  is silently swallowed.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13d (317 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: owner_member_id
    type: u2
    doc: "Offset 4:6. `lhz r3,4(r29)` @ 0x00ad81e0. Zero-extended and stored into the matched room's +0x19f0 = the member id of the room's owner. Must match a member_id already registered via Member (0x131) for `_opd_FUN_00ad0d98`'s lookup to resolve it."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Not read by the traced portion of the 0x13d dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` for each of the connection's 4 room slots (slot i's room-object pointer is at `this + i*0x9000 + 0x50`; verified by raw disasm this pass, the `addis r11,r11,1 / addi r11,r11,-28672` idiom is a 0x9000 stride). Silently dropped if no slot matches - and room_obj+0x10 is set ONLY by Member's (0x131) handler, so this message must follow a Member. Same room_id-echo pattern used throughout this opcode family."
