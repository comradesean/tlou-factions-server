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
  frame (the leaked_stack_garbage field below). See
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
  - id: leaked_stack_garbage
    size: 16
    doc: "UNCONFIRMED CONTENT, CONFIRMED CAUSE: proven-uninitialized bytes. FUN_00acc424 byte-copies 16 bytes from its own fresh stack frame (r1+120..135, never written by this function before the copy) into the packet. This is a genuine client-side memory-disclosure bug, not an intentional protocol field - a server implementation MUST NOT depend on its value or try to validate it. Captures showing plausible-looking PS3 stack/heap addresses here (e.g. `d0 0f 78 80`) are coincidental - whatever happened to be on the stack at that depth when this function ran."
  - id: service_name
    size: 64
    doc: "NUL-terminated ASCII service name identifying which backend this multiplexed connection is for (observed: \"ticket-server\"), left-justified in a 64-byte buffer via a strcpy-equivalent (FUN_00e45b10) with NO trailing zero-fill - bytes after the NUL terminator are leftover stack garbage from the same uninitialized region as leaked_stack_garbage, not meaningful padding. A caller-side strlen check (FUN_00e40ad8) rejects service names >= 64 bytes before this function is even entered, so the field's max useful length is 63 chars + NUL."
