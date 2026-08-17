meta:
  id: member_set_data
  endian: be
  license: CC0-1.0
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
  - id: send_tag
    size: 3
    doc: "Offset 5:8. Varies every send (e.g. 3a e1 48 / 9f a9 6c / 27 0e 9c / 3e 6d 94). Unidentified - a per-send sequence, checksum, or hash. Not consumed by the server relay."
  - id: room_id
    size: 8
    doc: "Offset 8:16. The currently-open room's room_id (matches the value the server assigned via Member's header). Used by the stub to route the relay to that room's members. Low 4 bytes coincide with the room-object pointer because the stub derives room_id from RoomCreate's wire bytes; that is a stub artifact, not a wire requirement."
  - id: member_blob
    size: 32
    doc: |
      Offset 16:48. The 32-byte per-member data blob - the SAME structure the
      lobby UI reads for a remote player (see protos/0x131_member.ksy
      data_blob and protos/0x13b's blob). Decoded from live captures:
      byte 8 = flags, byte 9 = title index, bytes 10..13 = the host map-picker's
      recent-level ring (CORRECTED 2026-08-17 — was "four loadout item-ids"; NOT
      loadout, it is NetGameManager+0x4982 recently-played map indices, see
      protos/common/member_data.ksy; 0xff = unset, live `00 0e ff ff` in a game
      room vs `ff ff ff ff` fresh), u16 at
      byte 14 = the rank-widget value, remaining bytes = a stat region that
      is zero on an empty profile. The server relays these 32 bytes verbatim.
  - id: tail
    size: 32
    doc: "Offset 48:80. Beyond the declared 32-byte blob length. In live captures this holds leaked stack (e.g. a 0x0137d700 player-array pointer) - uninitialised, not meaningful. (An older capture happened to show four IEEE-754 floats 1.0/~0.729/~0.710/~0.650 here; treated as coincidental stack residue given the blob length is 32, not evidence of scoring coefficients.)"
