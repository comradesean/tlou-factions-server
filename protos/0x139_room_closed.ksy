meta:
  id: room_closed
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingRoomClosed (forced teardown) - server -> client, over the
  Session Manager connection (port 7314). One of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for; handler
  confirmed at 0x00ad7fc4.

  RENAMED from `kickout` - the earlier reading (single-member kick,
  tearing down the whole room as an over-broad side effect) is superseded
  by the disassembly-verified opcode map: 0x137/0x138 are the real
  Kickout/Kickedout pair (per-member, routed to one client), and this
  opcode is a distinct, harder, server-initiated teardown of the room as a
  whole - not a kick at all.

  STATUS: confirmed 16 bytes. Looks up the room matching room_id (offset
  8), then: calls the room's vtable+0x2c callback, runs the same full
  room-teardown routine (`_opd_FUN_00ad32c4`) the confirmed 0x133
  room-abandon case uses (RequestLeave-equivalent for every member), ALSO
  zeroes the room's own id fields (struct+0x10/+0x14, not touched by
  0x138/Kickedout's lighter single-recipient path), then calls the room's
  vtable+0x20 callback. Net effect: this client's entire room object is
  torn down and invalidated, regardless of which member it is - "the room
  itself is gone", distinct from "I personally was kicked" (0x138).
  LIVE-VERIFIED 2026-08-18 - first send in the project's history. Until this
  date the stub had no builder for 0x139 at all, and an owner leaving simply
  vanished: the room was deleted from the registry and the remaining members
  were told NOTHING (no 0x134, no 0x139), leaving a survivor holding a room the
  server had forgotten, with no keepalive (start_member_refresher skips
  multi-member rooms) and no surviving peer - the documented road to
  room_obj+0x10 going zero and code that assumes a valid room id trapping.

  Captured exchange:
    22:30:59.864  in   owner  0x133 RoomLeaving  room=012723d801383bd8
    22:30:59.867  out  member 0x134 RoomLeave(member_id=1) + 0x139 RoomClosed

  The survivor accepted it cleanly and kept running: six seconds later it was
  still exchanging 0x13a/0x13b member data on its PARTY room. So the teardown
  is correctly scoped to the room named in room_id - it invalidates that room
  object only, and other rooms the same client belongs to are untouched.
  Send it to every remaining member when a room's owner departs, paired with a
  0x134 RoomLeave naming the departed owner.

doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x139 (313 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: pad_4
    size: 4
    doc: "Offset 4:8. Alignment padding. DEFINITION: the 4-byte gap before the 8-byte-aligned room_id (wire 8). REASON: the 0x139 receive arm reads only room_id (`ld r3,8(r29)` @0xad7fec); offset 4 is never loaded, it just aligns room_id. Send 0. (Was `unknown_4`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` for each of the connection's 4 room slots (slot i's room-object pointer is at `this + i*0x9000 + 0x50`; the `addis r11,r11,1 / addi r11,r11,-28672` idiom is a 0x9000 stride). Silently dropped if no slot matches - and room_obj+0x10 is set ONLY by Member's (0x131) handler, so this message must follow a Member. Same room_id-echo pattern used throughout this opcode family."
