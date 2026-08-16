meta:
  id: owner_changed
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingOwnerChanged - server -> client, over the Session Manager
  connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: confirmed 16 bytes, matching the declared size exactly. Looks up
  the room matching room_id (struct+0x10, same room_id-echo pattern used
  throughout this opcode family), then writes the low bit of the byte at
  offset 4 into that room's own struct at +0x19f4 - the "is owner"/"is host"
  flag referenced by the family-wide dispatch-table cross-check in this doc's
  own "numeric opcode IDs" section. Name and behavior agree cleanly.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13f (319 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: is_owner
    type: u1
    doc: "Offset 4:5. Only the low bit is used (ANDed with 1) before being stored into the matched room's +0x19f4 flag byte."
  - id: unknown_3
    size: 3
    doc: "Offset 5:8. Not read by the traced portion of the 0x13f dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against the session's own tracked room id - same room_id-echo pattern used throughout this opcode family."
