meta:
  id: host_rank
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingHostRank - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only), and fire-and-forget:
  no 0x142 receive case exists and the deferred marker at room+0xD0 has no
  reader, so a server MUST ignore it and MUST NOT reply (a reply wedges the
  receive cursor).

  NAME RESTORED 2026-08-18, then HAND-CONFIRMED LIVE. An earlier pass renamed
  this to the placeholder `room_u16_list_upload` out of caution; the opcode has
  since been tested and confirmed by hand as HostRank, so the restoration
  stands (not medium-confidence any more at the message level). Supporting
  decompile evidence: the shifted declared-name table matches by exact size
  across 4 messages plus 3 semantic corroborations, and the collector
  FUN_0039b720 builds the u16 list by iterating the 8 local-player slots of the
  NetGameManager player array (0x0137D700 + i*0x920 + 0x40), filtering by seven
  state bytes, sorting entries with `*(u8*)(player+0x3FF) != 0` first, then
  `out_u16[i] = (u16)player->vtable[0](player)` (`bctrl` @ 0x39b920,
  `sth r3,0(r9)` @ 0x39b934). The per-entry VALUE is the player vtable[0]
  getter's return (the same getter used as the roster rank sort override);
  the message is a per-player rank report. Only the exact numeric encoding of
  each u16 (vs a captured ranked-account value) remains to be pinned down.

  STATUS: variable-length message, a 16-byte header plus a `count * 2`-byte
  trailing payload copied verbatim from a caller-supplied buffer
  (`_opd_FUN_00e3e064`, a plain memcpy-shaped helper, not decompiled
  further). Builder confirmed at 0x00ad60c4 / FUN_00ad5ffc. Every header
  field's exact store instruction was located.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x142 (322 decimal), stored as a raw big-endian compile-time constant (no runtime byteswap call needed for this one - the literal is already emitted in wire order)."
  - id: count
    type: u2
    doc: "Offset 4:6. The sender's entry count (`sth r6,4(r29)` @ 0xad60dc), truncated to 16 bits and stored raw. Number of u16 entries in the trailing list (one per qualifying local player)."
  - id: uninit_6
    size: 2
    doc: "Offset 6:8. NEVER WRITTEN by the sender - uninitialised stack. RESOLVED 2026-08-18: FUN_00ad5ffc stores opcode @ 0xad60d4, count @ 0xad60dc, room id @ 0xad60d8, and the memcpy to +16 @ 0xad60e0 - nothing at offset 6:7. Explains the live `00 00` vs `00 60` variation. Was `unknown_2`."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field (`std r11,8(r29)` @ 0xad60d8) - matches the room_id-echo pattern used throughout this opcode family."
  - id: entries
    type: u2
    repeat: expr
    repeat-expr: count
    doc: "Offset 16 onward, count*2 bytes. One u16 per qualifying local player, collected by FUN_0039b720 from the player array (see doc): each value is that player's vtable[0] getter return, sorted by the +0x3FF flag - a per-player rank (message hand-confirmed as HostRank). Only the exact numeric encoding of each u16 is still open (one live sample 0x0002 from an unranked account). Server ignores this message; it need not interpret the values."
