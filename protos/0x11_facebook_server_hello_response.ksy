meta:
  id: facebook_server_hello_response
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  Server's reply to facebook_server_hello, on the same connection. Fixed
  size, 8 bytes - identical layout/validation to
  ticket_server_hello_response.ksy, same shared function (FUN_00acc424).

  STATUS: confirmed structurally by the same shared-function argument as
  facebook_server_hello.ksy. Not independently live-captured.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: ack_magic
    type: u1
    doc: "MUST equal 0x22 or the client aborts - identical check, shared code with ticket-server."
  - id: server_choice_1
    size: 3
    doc: "Offset 1:4. UNCONSTRAINED server-choice bytes (RESOLVED 2026-08-18). The shared decoder FUN_00acc424 acts only on byte[0] (the 0x22 magic check) and bytes[4:8] (stored to conn+0x50 as the frame counter); bytes[1:4] are never read or branched on - same trace as ticket_server_hello_response.server_choice_1. A stub may send zero. (Was `unknown1`, \"read but not validated\".)"
  - id: session_token
    type: u4
    doc: "Stored at conn+0x50 - the rolling encrypted-frame key/counter for this connection's client->server traffic (see docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section, shared code). facebook-server uses this across up to two distinct sub-protocols (friends' online-status batches and NpId lookup/resolve) depending on which call site opened the connection - see docs/protocol/0x11_sibling_servers_family.md."
