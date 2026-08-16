meta:
  id: kickout
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingKickout - server -> client, over the Session Manager
  connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: confirmed 16 bytes, matching the declared size exactly. Looks up
  the room matching the room_id field (comparing against struct+0x10, the
  same field every room-id-echo case in this family checks), then: calls the
  room's vtable+0x2c callback (unconfirmed purpose - a kick/eject
  notification to game logic, by name/position), zeroes the room's own
  room_id fields (struct+0x10/+0x14), runs the SAME full room-teardown
  routine (_opd_FUN_00ad32c4) the confirmed 0x133 room-abandon case uses,
  then calls the room's vtable+0x20 callback. Net effect: the client tears
  down the whole room it's in, not just one member - "you are being kicked"
  reads correctly for the declared name.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x139 (313 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not read by the traced portion of the 0x139 dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against the session's own tracked room id to find the room being torn down - same room_id-echo pattern used throughout this opcode family."
