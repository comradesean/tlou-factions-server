meta:
  id: heartbeat_server_hello_response
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  Server's reply to heartbeat_server_hello, on the same connection. Fixed
  size, 8 bytes - byte-for-byte identical layout to
  ticket_server_hello_response.ksy, same shared validating function
  (FUN_00acc424).

  STATUS: confirmed structurally by the same shared-function argument as
  heartbeat_server_hello.ksy. Never independently live-captured for this
  specific service (only ticket-server's handshake has a real capture so
  far - see docs/protocol/0x11_ticket_server_hello.md).
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: ack_magic
    type: u1
    doc: "MUST equal 0x22 or the client aborts the connection - identical check, same shared code as ticket-server's ack_magic."
  - id: server_choice_1
    size: 3
    doc: "Offset 1:4. UNCONSTRAINED server-choice bytes (RESOLVED 2026-08-18). The shared decoder FUN_00acc424 acts only on byte[0] (the 0x22 magic check) and bytes[4:8] (stored to conn+0x50 as the frame counter); bytes[1:4] are never read or branched on - same trace as ticket_server_hello_response.server_choice_1. A stub may send zero. (Was `unknown1`, \"read but not validated\".)"
  - id: session_token
    type: u4
    doc: "Stored at conn+0x50. CONFIRMED (via the ticket-server investigation, same shared code): this is NOT inert - it is the initial value of the rolling key/counter used by FUN_00acb6fc to encrypt-and-tag every frame this connection's client sends after this handshake (see docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section). A server implementation must track whatever value it sends here and increment it per frame to build/verify heartbeat-server's post-hello traffic correctly, once that traffic's plaintext shape is mapped (not done this pass - see docs/protocol/0x11_sibling_servers_family.md)."
