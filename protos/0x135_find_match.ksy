meta:
  id: find_match
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmaking find-match search broadcast, sent by the client repeatedly
  (~5s cadence, same as Ping) while sitting in the "Find Match" screen -
  correlates with the client's *own* matchmaking-search state, not a
  one-off "I left a room" event.

  STATUS: the declared opcode/size table (docs/protocol/session_manager_and_
  matchmaking.md) names this NetMatchmakingRoomLeft at 24 bytes - WRONG on
  both counts, per this project's now-established pattern of declared-table
  errors past the initial handshake opcodes (see 0x133/0x13a for two prior
  examples). Live capture 2026-08-15 of two real clients both sitting in
  "Find Match" shows this fires unprompted every ~5s, 36 bytes, containing
  (unconfirmed offsets): a locale field ("us"), a repeated 0x03e8/0x03e8
  (1000/1000-shaped) u16 pair, and a small mode-shaped field - not
  independently offset-mapped this pass, only the aggregate content and
  total size are confirmed. tools/session_manager_stub.py only checks the
  opcode itself (not any field within the body) to trigger matchmaking
  pairing - see FIND_MATCH_OPCODE's docstring there for the full evidence
  and the "heartbeat/broadcast, not a leave event" theory.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x135 (309 decimal). Confirmed live, big-endian."
  - id: body
    size: 32
    doc: "Offsets 4-35 of the 36-byte total. Contains a locale field ('us'), a repeated 0x03e8/0x03e8 u16 pair, and a small mode-shaped field per live capture - not independently offset-mapped. tools/session_manager_stub.py does not parse this region at all; the client's own periodic re-send (not any field value within this body) is what drives the stub's cross-connection find-match pairing."
