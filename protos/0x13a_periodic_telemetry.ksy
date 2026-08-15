meta:
  id: periodic_telemetry
  endian: be
  license: CC0-1.0
doc: |
  Provisionally named - real purpose still UNCONFIRMED. Wire opcode 0x13a,
  80 bytes, client -> server, fire-and-forget over the Session Manager
  connection (port 7314).

  The declared opcode/size table (docs/protocol/session_manager_and_
  matchmaking.md) names this NetMatchmakingKickedout at 16 bytes - WRONG on
  both counts, same "declared table lies" pattern as 0x133/0x135. It was
  first named "CreateParty" after appearing to correlate with the in-game
  "invite to party" UI action, but a 2026-08-15 live-breakpoint trace of the
  actual sending function (_opd_FUN_00ad6148, called from 0x003B17CC/
  0x003B17E0) DISPROVED that: it fires on a periodic/UI-transition tick
  from the main menu onward, completely independent of party or room
  state, and the caller's own register context at the time contains a
  literal Google Analytics beacon URL string ("GET /__utm.gif?..."). See
  research/notes/2026-08-15-createparty-trace.md for the full trace.

  KNOWN BYTE LAYOUT (confirmed from two live captures), UNKNOWN MEANING:
  the 80-byte wire shape below is confirmed by direct inspection of two
  real captures, but since the opcode's actual purpose is unknown, none of
  these field names should be read as confirmed semantics - only as "this
  is what's observed at this offset."
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13a (314 decimal). Confirmed live, big-endian."
  - id: unknown_field
    size: 4
    doc: "Offset 4:8. Identical (0x2026e00c) across both live captures referenced in this file's doc block - constant within a session at least, not independently traced. Possibly a session/connection identifier; not confirmed."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Matches the currently-open room's own room_id (the same value this server assigned via Member's header) in both live captures - confirmed by direct comparison. Despite matching the room id, the sender function has been proven (see doc block above) to fire independent of any room/party action, so this is likely just ambient state read at send time, not evidence of room-related purpose."
  - id: unconfirmed_middle
    size: 48
    doc: "Offset 16:64. Mostly zero in both captures, with a few notable non-zero spans (a 4-byte 0xffffffff marker around relative offset 0x1a, a 0x0000bb70-shaped value, and an 8-byte span that DIFFERS between the two captures - possibly a timestamp or counter). Not independently offset-mapped this pass."
  - id: tail_floats
    size: 16
    doc: "Offset 64:80. 4x IEEE-754 big-endian floats, identical across both captures: 1.0, ~0.729, ~0.710, ~0.650. Shape suggests weighting/scoring coefficients (matchmaking skill weighting was the original speculative theory) but this is UNCONFIRMED and now suspect given the sender is proven to be a generic telemetry tick, not anything party/room/matchmaking-specific."
