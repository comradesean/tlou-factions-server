meta:
  id: client_hello2
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

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
    type: u4
    doc: |
      Offset 4:8. A DETERMINISTIC session-derived checksum, NOT a random nonce
      (corrected 2026-08-18 from a full disasm trace of the builder @0xad7554-
      0xad7598). The client calls the ARX keyschedule FUN_00db7f88(session_state,
      buf, 0x24) - the same primitive that keys the session_seed from ServerHello -
      then sums its four output words at 136/140/144/148(r1) mod 2^32
      (add-chain @0xad7580-0xad758c) and byteswaps the result into this field.
      So it is reproducible from the session_seed, varies per session, and a
      server that ever needed to validate it would recompute via FUN_00db7f88 over
      the session material. One live capture: 18 ac 7a d2. The stub does not
      validate it (Init sends this fire-and-forget)."
