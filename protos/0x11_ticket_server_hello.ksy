meta:
  id: ticket_server_hello
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  First message the client sends after connecting (raw TCP, port 7320 in this
  build's net1.bin config) to the "ticket-server" backend, as part of NetInit's
  post-RPCN-ticket session establishment. Fixed size, 0x58 (88) bytes.

  STATUS: confirmed structurally via decompilation and raw disassembly of the
  function that builds and sends it, FUN_00acc424 (0x00acc424), called from
  the NetInit orchestrator FUN_003557a8 (0x003557a8) right after a successful
  low-level TCP connect. Every byte of the 88-byte buffer is accounted for -
  either as an explicit store instruction (opcode/reserved/nonce/service-name
  fields) or as a proven *unwritten* region of FUN_00acc424's own fresh stack
  frame (the pad_08 field below). See
  docs/protocol/0x11_ticket_server_hello.md for the full disassembly evidence.

  This opcode namespace is UNRELATED to protos/common/opcodes.ksy's
  net_event_type enum (the in-game gameplay event IDs). Opcode 0x11 here is a
  distinct control-channel protocol multiplexed by service-name string
  ("ticket-server", and siblings "heartbeat-server", "leaderboard-server",
  "invite-server", "facebook-server", "single-player-server" found in the
  string table but not individually analyzed) - not a NetEventType value. Do
  not conflate the two opcode spaces.
doc-ref: ../docs/protocol/0x11_ticket_server_hello.md
seq:
  - id: opcode
    type: u1
    doc: "Fixed value 0x11 (17) for this hello/service-select message. Explicit `li r0,17; stb r0,...` store in FUN_00acc424 - confirmed, not inferred."
  - id: reserved0
    type: u1
    doc: "Always observed 0x00. Explicit `li r0,0; stb` store - confirmed zero (not garbage, unlike leaked_stack_garbage below). Purpose unknown - possibly a version/flags byte that just happens to always be 0 in this build."
  - id: reserved1
    type: u2
    doc: "Always observed 0x0000. Explicit `li r0,0; sth` halfword store - confirmed zero. Purpose unknown."
  - id: client_nonce
    type: u4
    doc: "Output of the client's local PRNG (FUN_00e408d8, a 32-slot LCG-based generator seeded once per process), masked to 30 bits (top 2 bits always 0 - matches every captured sample). Also cached into the connection object at offset +0x4c for later use; what (if anything) later compares against it was not traced in this pass. Best-guess purpose: a client-side session/correlation nonce. Confirmed NOT derived from the RPCN ticket bytes (ruled out - see companion doc's evidence log)."
  - id: pad_08
    size: 16
    doc: |
      Offset 8:24. NOT A FIELD - sender-side residue, and the largest single
      leak in this protocol family. RENAMED 2026-08-18 from
      `leaked_stack_garbage` to satisfy the repo's pad_<off> convention and the
      name+definition+reason standard.
      DEFINITION: an unwritten 16-byte gap between client_nonce and the 64-byte
      service_name buffer. REASON: FUN_00acc424 byte-copies 16 bytes from its own
      fresh stack frame (r1+120..135) which the function never writes before the
      copy, then sends the whole 88-byte hello - so whatever the previous user of
      that stack region left behind goes on the wire.
      LIVE CONTENT (452 captured hellos, server/logs/ticket_server.log,
      classified per 4-byte word): mostly zero (316-414 of 452 per word), plus
      main-thread STACK addresses (0xd00f7880 x60, 0xd00f7780, 0xd0bf3b90),
      globals (0x01383708 x34, 0x012a3908, 0x01305870), and a float around
      138.8-139.6 (0x430acd88 x44, 0x430ae988 x15) that reads as a seconds-since-
      boot timer.
      IT ALSO LEAKS TEXT. In 36 hellos the 16 bytes are a contiguous slice of a
      URL - `6f757475 62652f61 63636f75 6e74732f` = "outube/accounts/" - and in 2
      more they are a slice of JSON - `526f6265 72747322 2c202269 64223a20` =
      'Roberts", "id": '. That is HTTP/JSON buffer content from the client's web
      stack showing through, i.e. this field can disclose account identifiers and
      real names to whatever server the client connects to. Worth stating plainly
      because it is a genuine privacy leak in the retail client, not merely an
      untidy gap.
      A server MUST ignore these bytes. Send 0 when generating a hello.
      See research/notes/2026-08-18-wire-residue-and-field-corrections.md §1, §8.
  - id: service_name
    size: 64
    doc: "NUL-terminated ASCII service name identifying which backend this multiplexed connection is for (observed: \"ticket-server\"), left-justified in a 64-byte buffer via a strcpy-equivalent (FUN_00e45b10) with NO trailing zero-fill - bytes after the NUL terminator are leftover stack garbage from the same uninitialized region as leaked_stack_garbage, not meaningful padding. A caller-side strlen check (FUN_00e40ad8) rejects service names >= 64 bytes before this function is even entered, so the field's max useful length is 63 chars + NUL."
