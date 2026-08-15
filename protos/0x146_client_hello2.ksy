meta:
  id: client_hello2
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingClientHello2 - client -> server, sent once over the Session
  Manager connection (port 7314) right after the initial ClientHello/
  ServerHello exchange, as part of Init()'s startup sequence. The declared
  opcode/size table originally guessed opcode 0x148 via the naive
  "0x12d + table index" formula - WRONG, confirmed live opcode is 0x146
  (see docs/protocol/session_manager_and_matchmaking.md's intro for the
  correction).

  STATUS: 8 bytes total, confirmed live. Fire-and-forget: tools/
  session_manager_stub.py (CLIENT_HELLO2_OPCODE) sends no reply - Init()
  sends this message and moves on without waiting for one, confirmed by
  the decompiled startup sequence.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x146 (326 decimal). Confirmed live, big-endian."
  - id: payload
    size: 4
    doc: "Offset 4:8. One live capture showed 18 ac 7a d2 - shape consistent with a random/session nonce or a hash, but not independently traced. Real meaning unconfirmed."
