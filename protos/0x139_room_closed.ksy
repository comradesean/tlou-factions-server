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
