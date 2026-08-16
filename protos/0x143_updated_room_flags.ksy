meta:
  id: updated_room_flags
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingUpdatedRoomFlags - client -> server, over the Session
  Manager connection (port 7314). Not one of the 11 opcodes the client's
  own receive-dispatch has a case for (client-to-server only) - despite the
  declared name suggesting a server confirmation, this is confirmed
  outbound from the client.

  STATUS: confirmed 144 bytes (matching the declared size). Two nearly
  identical sender call sites found and fully disassembled 2026-08-15
  (`FUN_00ad6f28` at vtable+0x3c, `FUN_00ad54e0` at vtable+0x40) - both
  build and send the exact same 144-byte shape; `FUN_00ad6f28`'s variant
  additionally does a locale-aware analytics/telemetry call first
  (`_opd_FUN_00ada1c8`/`_opd_FUN_00e46670`) that doesn't touch the wire
  payload.

  NOTABLE: the 128-byte trailing block (offset 16-143) is a byte-for-byte
  copy of the room object's own +0x18 region - the EXACT SAME region
  0x144/HostRank (protos/0x144_host_rank.ksy) writes into on receipt. This
  strongly suggests the two are a matched pair: the server pushes a
  rank/host-priority table via HostRank, and the client echoes its own copy
  of that same table back via UpdatedRoomFlags - consistent with "flags"
  meaning something host-selection-related rather than simple boolean room
  flags, but not confirmed without a live capture correlating the two.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x143 (323 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not written by either confirmed sender - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field - matches the room_id-echo pattern used throughout this opcode family."
  - id: rank_data
    size: 128
    doc: "Offset 16:144. Byte-for-byte copy of the room object's own +0x18 region - the same region 0x144/HostRank populates on receipt. See doc for the suspected HostRank/UpdatedRoomFlags pairing. Internal layout not reversed this pass."
