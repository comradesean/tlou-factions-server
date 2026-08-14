meta:
  id: heartbeat_server_hello
  endian: be
  license: CC0-1.0
doc: |
  First message the client sends after connecting to the "heartbeat-server"
  backend, on the same raw-TCP opcode-0x11 control channel as ticket-server
  (see docs/protocol/0x11_ticket_server_hello.md). Fixed size, 0x58 (88)
  bytes - byte-for-byte identical layout to ticket_server_hello.ksy.

  STATUS: confirmed high confidence, NOT by independently re-deriving this
  service's wire format, but because heartbeat-server's connect handler
  (FUN_00353cd8 @ 0x00353cd8, call site 0x00353d78) calls the exact same
  function, FUN_00acc424 (0x00acc424), that ticket-server's handler calls -
  confirmed via Ghidra reference enumeration over every caller of
  FUN_00acc424 in the whole binary (research/ghidra/acc424_all_callers.txt).
  Only the service_name field's content differs (the literal string
  "heartbeat-server" instead of "ticket-server", loaded from a distinct
  service-descriptor table slot at +0x48 in FUN_00353cd8, vs. ticket-server's
  +0x7c). See docs/protocol/0x11_sibling_servers_family.md for the survey
  this was found in, and 0x11_ticket_server_hello.ksy/.md for the full
  disassembly-level field evidence (unchanged here - same code).
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: opcode
    type: u1
    doc: "Fixed 0x11 - same literal store in the shared FUN_00acc424, unrelated to which service_name follows."
  - id: reserved0
    type: u1
    doc: "Always 0x00 - see 0x11_ticket_server_hello.ksy for evidence (identical code path)."
  - id: reserved1
    type: u2
    doc: "Always 0x0000 - see 0x11_ticket_server_hello.ksy for evidence (identical code path)."
  - id: client_nonce
    type: u4
    doc: "Client-local PRNG output, also cached at conn+0x4c - identical mechanism to ticket-server's client_nonce. For THIS service's connection this also becomes the key/counter for any encrypted frames the server sends back after this handshake (see docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section, which applies to every *-server connection using this shared code)."
  - id: leaked_stack_garbage
    size: 16
    doc: "Proven-uninitialized stack bytes - identical root cause to ticket_server_hello.ksy's field of the same name (same function, same unwritten stack range). Not meaningful; do not depend on its value."
  - id: service_name
    size: 64
    doc: "NUL-terminated ASCII, observed/expected value \"heartbeat-server\" (string address 0x00e7a0e8 in this build). Left-justified in a 64-byte buffer with no trailing zero-fill, same as ticket-server's field - bytes after the NUL are leftover stack garbage."
