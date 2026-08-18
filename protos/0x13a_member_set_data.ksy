meta:
  id: member_set_data
  endian: be
  license: CC0-1.0
  imports:
    - common/member_data
doc: |
  Direction: client-to-server

  Wire opcode 0x13a, 80 bytes, client -> server, fire-and-forget over the
  Session Manager connection (port 7314). (Filename says "periodic_telemetry"
  for historical reasons - that reading is now retired, see below - the
  message is the client publishing its own per-member data blob. Rename
  deferred to avoid breaking existing references.)

  CORRECTED 2026-08-16/17. This was previously read as generic "periodic
  telemetry" because a 2026-08-15 live-breakpoint trace of the sender
  function _opd_FUN_00ad6148 caught it firing on a UI-transition tick with a
  Google Analytics beacon string in an adjacent register
  (research/notes/2026-08-15-createparty-trace.md). That trace was about the
  unrelated CALLER LOOP, not this message's CONTENT: 0x13a carries the
  client's own 32-byte member data blob (SetPartyData / "MemberSetData") -
  the same blob the lobby UI reads for a REMOTE player, containing title,
  rank and the host map-picker's recent-level ring (NOT loadout — corrected
  2026-08-17, see the member_blob field). The stub relays it to the room's other
  members as 0x13b, and that path is live-confirmed working (the remote
  player's member slot +0xFC is populated from it). See
  research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md and
  research/notes/2026-08-16-two-player-party-and-match-working.md.

  The declared opcode/size table (docs/protocol/session_manager_and_
  matchmaking.md) names this NetMatchmakingKickedout at 16 bytes - wrong on
  both counts (a 2013-08-17 note argues the whole table tail is shifted 2
  slots from 0x13a onward, making this MemberSetData; pending reconciliation
  with the stub's functional naming, but the CONTENT below is what matters
  for implementation).
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13a (314 decimal). Confirmed live, big-endian."
  - id: blob_length
    type: u1
    doc: "Offset 4. The client's own declared length of the member blob that follows at offset 16. Live-constant 0x20 = 32 across every capture. This is the value the server must echo as 0x13b's length byte and seed as Member entry offset 39 - the rank/loadout UI getter (_opd_FUN_00ad2650) accepts the blob ONLY if it is exactly 32. (Earlier this whole 4-byte span was recorded as one constant 0x2026e00c; newer captures show byte 4 fixed at 0x20 and bytes 5-7 varying, so byte 4 is the length and 5-7 are a separate per-send field.)"
  - id: uninit_5
    size: 3
    doc: "Offset 5:8. NEVER WRITTEN by the sender - uninitialised stack. The full sender body FUN_00ad6148 (buffer base r1+0x70) writes exactly four things: opcode (r1+112), length byte (r1+116), room id (r1+120), and the memcpy to r1+128; bytes 5:7 (r1+117..119) get no store. The varying values seen across captures (e.g. 3a e1 48 / 9f a9 6c) are stack residue, not a per-send sequence/checksum. Same class as 0x13e/0x140/0x142."
  - id: room_id
    type: u8
    doc: "Offset 8:16. The currently-open room's room_id (the value the server assigned via Member's header), sourced from room+0x10 (`std r9,120(r1)` @ 0xad6264). Used by the stub to route the relay to that room's members. Low 4 bytes coincide with the room-object pointer only because the stub derives room_id from RoomCreate's wire bytes; that is a stub artifact, not a wire requirement."
  - id: member_blob
    type: member_data
    doc: |
      Offset 16:48. The 32-byte per-member data card (see
      protos/common/member_data.ksy for the full field decode). The SAME
      structure the lobby UI reads for a remote player (also carried by 0x131
      roster entries and re-delivered via 0x13b). The server relays these 32
      bytes verbatim.
  - id: tail
    size: 32
    doc: "Offset 48:80. Beyond the 32-byte member_data card. Confirmed uninitialised stack from the sender body: the memcpy copies only `blob_length` (=32) bytes to offset 16, and nothing writes r1+160..191. Live captures show leaked stack here (e.g. a 0x0137d700 player-array pointer). Send zero."
