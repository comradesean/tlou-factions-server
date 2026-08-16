meta:
  id: set_room_name
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  REAL IDENTITY (corrected 2026-08-16): this is `NetMatchmakingSetRoomName`,
  NOT `NetMatchmakingUpdatedRoomFlags`. The filename is kept opcode-keyed for
  continuity; the `meta/id` and the analysis below use the corrected name.
  See research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 5.

  Why the declared table was wrong: the 28-entry name/size debug table in
  Init() has TWO phantom entries (index 22 `UpdatedRoomFlags` and index 23
  `HostRank`, both declared 16 bytes) that have no wire opcode at all. From
  declared index 24 onward the real wire opcode is `0x12d + index - 2`:

      declared idx 24 `SetRoomName`   (144 bytes) -> wire 0x143 (144) THIS FILE
      declared idx 25 `UpdatedRoomName`(144 bytes) -> wire 0x144 (144)
      declared idx 26 `Ping`          (4 bytes)   -> wire 0x145 (4)   [already known]
      declared idx 27 `ClientHello2`  (8 bytes)   -> wire 0x146 (8)   [already known]

  All four declared sizes match the real wire sizes exactly, and the two
  previously-unexplained tail corrections (Ping = 0x145, ClientHello2 =
  0x146, both live-confirmed) fall out of the same single 2-entry shift
  instead of being two independent one-offs.

  Semantic confirmation, independent of the size argument: the 128-byte
  payload is `room_obj+0x18`, and `room_obj+0x18` is confirmed to be the room
  NAME string. `FUN_00ad6f28` (vtable +0x3c) builds it immediately before
  sending:

      uVar2 = _opd_FUN_00ada1c8(0);                             // timestamp
      _opd_FUN_00e46670(room+0x18, <fmt>, <npid_obj>+0x20, uVar2); // sprintf-like
      _opd_FUN_00e45b10(sendbuf+0x10, room+0x18);               // strcpy
      _opd_FUN_00a0e324(0x143);
      _opd_FUN_00acb93c(this+0x25060, sendbuf, 0x90, 1);        // 144 bytes

  `<npid_obj>+0x20` is the same NpId field ClientHello copies from, so the
  result is `<npid>.<unix-timestamp>` - byte-identical to the string
  RoomCreate (0x12f) sends at its own wire offset 0x28, which
  `FUN_00ad5b78` likewise produces by strcpy'ing `room_obj+0x18`.

  `FUN_00ad54e0` (vtable +0x40) is the same sender without the name rebuild -
  it just strcpy's whatever `room_obj+0x18` already holds and sends it.

  Both senders are gated on `room_obj+0x10 != 0` (they set the dirty flag
  `room_obj+0xd8 = 1` and return without transmitting if the room has no id
  yet).
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x143 (323 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not written by either confirmed sender - uninitialised stack, same pattern as RoomCreate offset 4 and SetAttrFlags offset 6."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field."
  - id: room_name
    size: 128
    doc: "Offset 16:144. NUL-terminated room name, strcpy'd from `room_obj+0x18` (`_opd_FUN_00e45b10`, confirmed this pass to be a plain two-argument strcpy - word-at-a-time NUL scan then a byte tail). Format `<npid>.<unix-timestamp>`. The server's confirmation (0x144) strcpy's this straight back into the same field."
