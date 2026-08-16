meta:
  id: facebook_server_hello
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  First message the client sends after connecting to the "facebook-server"
  backend, on the same raw-TCP opcode-0x11 control channel as ticket-server.
  Fixed size, 0x58 (88) bytes - byte-for-byte identical layout to
  ticket_server_hello.ksy.

  STATUS: confirmed high confidence via the shared-function argument (see
  0x11_heartbeat_server_hello.ksy's doc for the general method). Two
  independent call sites confirmed: FUN_003538c0 (@ 0x003538c0, call
  0x00353a68 - friends' online-status batch check, reads its IP/port pair
  from +0x50) and FUN_00ac17b0 (@ 0x00ac17b0, call 0x00ac1828 - NpId
  lookup/resolve, receives an already-resolved IP/port pair as an argument
  rather than reading the table itself at this call site). See
  docs/protocol/0x11_sibling_servers_family.md.
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
    doc: "NUL-terminated ASCII, observed/expected value \"facebook-server\" (string address 0x00e7a0c0 in this build). Same buffer/copy mechanism as ticket-server's field."
