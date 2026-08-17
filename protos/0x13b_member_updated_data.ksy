meta:
  id: member_updated_data
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingRoomDestroyed (declared name) - server -> client, over the
  Session Manager connection (port 7314). One of the 11 opcodes the client's
  own receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: declared size in the Init() size table is 16 bytes - CONFIRMED
  WRONG. The dispatch case requires >79 buffered bytes and consumes exactly
  80 (0x50) bytes.

  NAME CORRECTED 2026-08-17: this is per-member DATA DELIVERY (the
  server->client counterpart of the client's 0x13a/SetPartyData), NOT
  room destruction. It looks up ONE member by id (member_id at offset 4, via
  the same `_opd_FUN_00ad0d4c` lookup helper 0x134/RoomLeave uses) and, if
  found, copies a length-prefixed blob (length byte at offset 6, payload
  starting at offset 16) into that member's own struct at +0xfc, plus stashes
  the length at +0xf8. That +0xfc field is exactly what the lobby rank/loadout
  UI getter (_opd_FUN_00ad2650) reads for a REMOTE player - and it returns the
  blob to the UI only if the stored length is exactly 32. So this is the
  message that makes another player's rank, title and loadout render. The
  stub sends it by relaying each client's 0x13a blob; live-confirmed the
  member slot is populated. (The "RoomDestroyed" declared name is part of the
  same 2-slot table-shift error discussed in
  research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md; the
  matching client supplier is protos/0x13a_member_set_data.ksy.) The
  0x13b message MUST follow a Member (0x131) for this room - it is dropped
  until room_obj+0x10 is set, which only Member does.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13b (315 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: member_id
    type: u2
    doc: "Offset 4:6. Passed to the member-lookup helper (_opd_FUN_00ad0d4c) - same helper 0x134/RoomLeave uses."
  - id: blob_length
    type: u1
    doc: "Offset 6:7. Used both as the byte count copied from the trailing blob and stored verbatim into the matched member's own struct at +0xf8."
  - id: unknown_1
    size: 1
    doc: "Offset 7:8. Not read by the traced portion of the 0x13b dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` for each of the connection's 4 room slots (slot i's room-object pointer is at `this + i*0x9000 + 0x50`; verified by raw disasm this pass, the `addis r11,r11,1 / addi r11,r11,-28672` idiom is a 0x9000 stride). Silently dropped if no slot matches - and room_obj+0x10 is set ONLY by Member's (0x131) handler, so this message must follow a Member. Same room_id-echo pattern used throughout this opcode family."
  - id: blob
    size: 64
    doc: |
      Offset 16:80. Copied (blob_length bytes) into the matched member's
      struct at +0xfc. CONFIRMED 2026-08-17: this is the remote player's
      32-byte rank/loadout card (blob_length is 32 in practice, and the UI
      getter _opd_FUN_00ad2650 requires exactly 32). Structure (see
      protos/0x131_member.ksy data_blob and protos/0x13a member_blob): byte 8
      = flags, byte 9 = title index, bytes 10..13 = the host map-picker's
      recent-level ring (CORRECTED 2026-08-17 — was "four loadout item-ids"; NOT
      loadout, it is NetGameManager+0x4982 recent-map indices, see
      protos/common/member_data.ksy; 0xff = unset), u16 at byte 14 = rank-widget
      value, rest = stat region.
      The packet is always 80 bytes regardless of blob_length, so bytes past
      blob_length (i.e. 48:80 when length is 32) are unused padding."
