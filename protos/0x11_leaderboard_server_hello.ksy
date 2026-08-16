meta:
  id: leaderboard_server_hello
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  First message the client sends after connecting to the "leaderboard-server"
  backend, on the same raw-TCP opcode-0x11 control channel as ticket-server.
  Fixed size, 0x58 (88) bytes - byte-for-byte identical layout to
  ticket_server_hello.ksy.

  STATUS: confirmed high confidence via the shared-function argument (see
  0x11_heartbeat_server_hello.ksy's doc for the general method). Notably
  strong for this service: FOUR independent call sites all call
  FUN_00acc424 with what this pass infers is the same "leaderboard-server"
  service_name (FUN_003b0f6c @ 0x003b0f6c call 0x003b1018 - the main
  "submit my score" handler; FUN_003aeee8 @ 0x003aeee8 call 0x003aefc8 and
  its two thin wrappers FUN_003af46c/FUN_003afb74, calls 0x003af8c8/
  0x003b0abc - a separate bulk roster-fetch sub-protocol). All four read
  their IP/port pair from the identical +0x54 service-descriptor table
  offset, which is strong independent corroboration they really are all the
  same logical service despite having very different post-hello payload
  shapes (see docs/protocol/0x11_sibling_servers_family.md).
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: opcode
    type: u1
    doc: "Fixed 0x11 - shared code with ticket-server's FUN_00acc424."
  - id: reserved0
    type: u1
    doc: "Always 0x00 - see 0x11_ticket_server_hello.ksy for evidence (identical code path)."
  - id: reserved1
    type: u2
    doc: "Always 0x0000 - see 0x11_ticket_server_hello.ksy for evidence (identical code path)."
  - id: client_nonce
    type: u4
    doc: "Client-local PRNG output, cached at conn+0x4c, also the key/counter for this connection's inbound encrypted frames (see docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section)."
  - id: leaked_stack_garbage
    size: 16
    doc: "Proven-uninitialized stack bytes - identical root cause to ticket_server_hello.ksy's field of the same name. Not meaningful."
  - id: service_name
    size: 64
    doc: "NUL-terminated ASCII, observed/expected value \"leaderboard-server\" (string address 0x00e7d268 in this build). Same buffer/copy mechanism as ticket-server's field."
