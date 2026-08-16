meta:
  id: set_attr_flags
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetAttrFlags - sent by the client over the Session Manager
  connection (port 7314). Live-captured for the first time 2026-08-15,
  only reachable once a room survives long enough to actually load into a
  match (see research/notes/2026-08-15-room-teardown-and-flag-chain.md and
  the RPCS3 "Stub PPU Traps" workaround that finally got a client this
  far).

  STATUS: 16 bytes total, confirmed live. NOT one of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for (unlike its
  reply, UpdatedAttrFlags/0x141) - client-to-server only.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x140 (320 decimal). Confirmed live, big-endian."
  - id: flags
    size: 4
    doc: "Offset 4:8. A flags-shaped value - one live capture showed 00 01 2f 78. Real bit meaning unconfirmed. tools/session_manager_stub.py (SET_ATTR_FLAGS_OPCODE) echoes this value verbatim back in its UpdatedAttrFlags reply, on the general 'echo the client's own correlation value' pattern used throughout this protocol - untested against live client behavior at time of writing."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Matches the room_id this server assigned via Member's header - echoed back verbatim in the stub's UpdatedAttrFlags reply."
