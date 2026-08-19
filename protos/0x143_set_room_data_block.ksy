meta:
  id: set_room_data_block
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetRoomDataBlock - client -> server, over the Session
  Manager connection (port 7314). Builder confirmed at 0x00ad5528. Pairs
  with 0x144/RoomDataBlockUpdated, the server's confirmation of the same
  block.

  RENAMED from `set_room_name` to `set_room_data_block`: the wire field is
  a generic 128-byte block mirrored to/from the room object's +0x18 field,
  not a dedicated "name" slot in the protocol's own terms. In every
  observed case that block happens to hold a NUL-terminated string of the
  form `<npid>.<unix-timestamp>` (see below), but the opcode/handler
  themselves treat it as an opaque block copy (`_opd_FUN_00e45b10`, a
  strcpy - two arguments, no declared length or type), so this proto names
  it accordingly.

  Observed content, still true post-rename: `FUN_00ad6f28` (vtable +0x3c)
  builds the string immediately before sending:

      uVar2 = _opd_FUN_00ada1c8(0);                             // timestamp
      _opd_FUN_00e46670(room+0x18, <fmt>, <npid_obj>+0x20, uVar2); // sprintf-like
      _opd_FUN_00e45b10(sendbuf+0x10, room+0x18);               // strcpy
      _opd_FUN_00a0e324(0x143);
      _opd_FUN_00acb93c(this+0x25060, sendbuf, 0x90, 1);        // 144 bytes

  `<npid_obj>+0x20` is the same NpId field ClientHello copies from, so the
  result is `<npid>.<unix-timestamp>` - byte-identical to the string
  RoomCreate (0x12f) sends at its own wire offset 0x28, which likewise
  strcpy's `room_obj+0x18`.

  `FUN_00ad54e0` (vtable +0x40) is the same sender without the string
  rebuild - it just strcpy's whatever `room_obj+0x18` already holds and
  sends it. Because the on-wire copy is a plain strcpy with no length
  argument, the SENDER'S OWN CONTENT MUST BE NUL-TERMINATED WITHIN 128
  BYTES, but the wire format itself places no other constraint on what
  goes in the block.

  LIVE CONFIRMATION + A TRAP (2026-08-18, 15 frames). The leading string is
  `<npid>.<unix-timestamp>` in every frame, with the npid equal to the ROOM OWNER
  and the timestamp equal to the send time (e.g. `comradesean.1787080629` sent at
  2026-08-18T19:17:09Z) - so it functions as a unique match-session identifier.

  DO NOT MINE THE BYTES AFTER THE NUL. Because the transfer is a bare
  two-argument strcpy, the remainder of the 128-byte field is whatever the send
  buffer already held, and it is full of recognisable pointers: 0xd0040140 /
  0xd00401b0 / 0xd00401e0 (main-thread stack), 0x0137d700 (NetGameManager player
  array base), 0x0039e96c and 0x0039ac24 (code), 0x01383bd8 (room object). Two of
  those residue words correlate PERFECTLY with room membership across all 15
  frames (+0x48 is 0 for a 1-member room and 2 for a 2-member room; +0x6c is 0
  and 1 respectively). That correlation describes what the sender happened to
  have on its stack, NOT a wire field, and must not be promoted to one. See
  research/notes/2026-08-18-wire-residue-and-field-corrections.md §6.

  Both senders are gated on `room_obj+0x10 != 0` (they set the dirty flag
  `room_obj+0xd8 = 1` and return without transmitting if the room has no id
  yet).
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x143 (323 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: pad_4
    size: 4
    doc: "Offset 4:8. Send-side alignment padding. DEFINITION: the 4-byte gap before the 8-byte-aligned room_id in the client's outbound packet. REASON: the builder (0x00ad5528) leaves offset 4 uninitialised, and there is NO client receive arm for 0x143 (whole-binary: no `cmpwi ...,323`), so nothing ever reads it - it only aligns room_id. Send 0. (Was `unknown_4`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field."
  - id: data_block
    type: strz
    size: 128
    encoding: ASCII
    doc: "Offset 16:144. A NUL-terminated ASCII string within a 128-byte field, NOT an opaque binary block: the transfer is a plain two-argument strcpy from `room_obj+0x18` (`_opd_FUN_00e45b10`, word-at-a-time NUL scan then a byte tail, no length argument), so by construction the content cannot contain an embedded 0x00 and is always NUL-terminated. Observed content is a `<npid>.<unix-timestamp>` string (that particular format is a content convention, not a wire constraint). The server's confirmation (0x144) strcpy's this straight back into the same field; a server MUST ensure a NUL appears within 128 bytes or the client-side strcpy overruns."
