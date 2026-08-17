meta:
  id: promote
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingPromote - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only). Pairs with
  0x13d/OwnerChanged, the server's confirmation of the same ownership
  change.

  STATUS: confirmed 16 bytes (matching the declared size), sender fully
  identified 2026-08-15 via instruction-level disassembly of vtable+0x28
  (`FUN_00ad6408`). Every field's exact store instruction was located.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13c (316 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: new_owner_member_id
    type: u2
    doc: "Offset 4:6. The function's third argument (a caller-supplied u16 member id), passed through the equally-no-op _opd_FUN_00a0e320 before send - the member being promoted to room owner. Pairs with 0x13d/OwnerChanged's own new_owner_member_id field."
  - id: unknown_2
    size: 2
    doc: "Offset 6:8. Uninitialised - confirmed via disassembly to never be written by this sender."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field (`std r4,0x78(r1)` in the disassembly) - matches the room_id-echo pattern used throughout this opcode family, and confirms that pattern is a genuine unswapped-longlong copy, not just a coincidence of C-level decompile."
