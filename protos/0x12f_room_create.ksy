meta:
  id: room_create
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingRoomCreate - sent by the client over the Session Manager
  connection (port 7314) when the player chooses to host a game, right after
  the NET_SM_READY_UP/NET_SM_CREATE_GAME_WAIT lobby-flow state transition
  (game/net/lobby-flow.cpp). Fixed 232 bytes, matching the opcode/size debug
  table exactly (unlike several nearby opcodes - see doc-ref for corrections
  found this session).

  STATUS: only offsets 0, 4, and the name string at 0x28 are confirmed by
  reasoning from a single live capture plus the corresponding RoomJoined
  reply's requirements; the middle "attribute" region (offsets ~0x10-0x50) is
  NOT decompiled from the send side - values below are transcribed from one
  real captured instance, not derived from send-site code. Several fields
  look like raw PS3 heap pointers copied verbatim (not meaningful protocol
  data) rather than something a server needs to validate - flagged per-field
  where suspected.
doc-ref: ../docs/protocol/0x12f_room_create.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x12f (303 decimal). Confirmed live, big-endian."
  - id: create_id
    size: 8
    doc: "8-byte client-generated value, live-captured as 01 27 23 d8 01 38 3b d8. Confirmed high-confidence by cross-reference: the corresponding RoomJoined reply (opcode 0x132) MUST echo this exact value at its own offset 8 for the client to match it to the pending room slot (see 0x132_room_joined.ksy). Likely a creation/transaction id rather than anything semantically meaningful to the server."
  - id: unconfirmed_middle
    size: 216
    doc: "Offsets 0xc-0xe3 of the payload. Contains, from a single live capture: an ASCII region code ('us\\x00\\x01' around relative offset 0x10), several u16 fields that look like counts/limits (e.g. 1000/1000-shaped values), and a null-terminated ASCII string '<npid>.<unix-timestamp>' (e.g. 'comradesean.1786732043') starting at relative offset 0x1c - this same string is echoed back in the stub's RoomJoined reply on the theory it's a room/session name. Several other 4-byte spans in this region look like raw uninitialized-or-opaque PS3 heap pointers (0x01xxxxxx/0xd0xxxxxx-shaped) rather than meaningful fields. NOT decompiled from the send-site code - treat every sub-field here as unconfirmed until traced."
