meta:
  id: room_data_block_updated
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingRoomDataBlockUpdated - server -> client, over the Session
  Manager connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for; deciding handler
  confirmed at 0x00ad838c. Pairs with 0x143/SetRoomDataBlock, the client's
  own upload of the same block.

  RENAMED from `updated_room_name` to `room_data_block_updated` for the
  same reason as 0x143/SetRoomDataBlock: the wire field is a generic
  128-byte block mirrored into the room object's +0x18 field, not a
  dedicated protocol-level "name" - see 0x143_set_room_data_block.ksy for
  the full argument. 144 bytes total.

  KEY MECHANISM: the payload is copied with a NUL-terminated strcpy, not a
  fixed-length binary block copy. The handler is:

      addi r3,r3,24        ; matched_room + 0x18
      addi r4,r31,16       ; wire + 16
      bl   0xe45b10        ; <- strcpy, TWO arguments, no length

  `_opd_FUN_00e45b10` is unambiguously strcpy (word-at-a-time NUL detection
  via `(x & 0x7f7f7f7f) + 0x7f7f7f7f | x | 0x7f7f7f7f`, then a byte-wise
  tail) - there is no length argument at all, so any earlier "copies a
  128-byte block" reading (inferred from the packet size alone) was
  incomplete.

  PRACTICAL CONSEQUENCE: the block MUST be NUL-terminated within 128 bytes
  or the strcpy overruns `room_obj+0x18` into `room_obj+0x98` and beyond.
  Echoing the client's own 0x143 payload back (what
  server/session_manager.py does) is safe and correct for a
  confirmation reply, since the client only ever puts a strcpy'd
  `<npid>.<unix-timestamp>` string there in practice.

  SEQUENCING: the room lookup keys on `*(s64*)(room_obj+0x10) == wire[8..15]`
  across the connection's 4 room slots. room_obj+0x10 is set ONLY by Member's
  (0x131) handler. This message is silently swallowed if it arrives first.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x144 (324 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: pad_4
    size: 4
    doc: "Offset 4:8. Alignment padding. DEFINITION: the 4-byte gap before the 8-byte-aligned room_id (wire 8). REASON: the 0x144 receive arm reads only room_id (`ld r10,8(r29)` @0xad83c0) then strcpy's the data_block from wire+16; offset 4 is never loaded, it just aligns room_id. Send 0. (Was `unknown_4`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` for each of the 4 room slots."
  - id: data_block
    type: strz
    size: 128
    encoding: ASCII
    doc: "Offset 16:144. A NUL-terminated ASCII string within a 128-byte field, NOT an opaque binary block: the handler is a plain strcpy into `room_obj+0x18` (`bl 0xe45b10`, two arguments, no length - see doc), so embedded 0x00 is impossible by construction. Same field the client fills before sending 0x143/SetRoomDataBlock, and the same block RoomCreate (0x12f) carries at wire offset 0x28. Observed content is a `<npid>.<unix-timestamp>` string; a server MUST place a NUL within these 128 bytes or the client-side strcpy overruns room_obj+0x18 into +0x98."
