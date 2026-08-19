meta:
  id: ping
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingPing - client -> server keepalive over the Session Manager
  connection (port 7314). The declared opcode/size table (docs/protocol/
  session_manager_and_matchmaking.md) originally guessed opcode 0x147 via
  the naive "0x12d + table index" formula - WRONG, confirmed live opcode is
  0x145 (see that doc's intro for the correction).

  STATUS: fully confirmed. Bare 4-byte opcode-only packet, no payload at
  all. Fire-and-forget: server/session_manager.py (PING_OPCODE) sends
  no reply, and the client has shown no sign of expecting one - appears to
  be a client-side-timer-driven keepalive rather than something requiring
  server acknowledgment.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x145 (325 decimal). Confirmed live, big-endian. This is the ENTIRE packet - no payload follows."
