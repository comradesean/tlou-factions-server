meta:
  id: leaderboard_server_hello_response
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  Server's reply to leaderboard_server_hello, on the same connection. Fixed
  size, 8 bytes - identical layout/validation to
  ticket_server_hello_response.ksy, same shared function (FUN_00acc424).

  STATUS: confirmed structurally by the same shared-function argument as
  leaderboard_server_hello.ksy. Not independently live-captured.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: ack_magic
    type: u1
    doc: "MUST equal 0x22 or the client aborts - identical check, shared code with ticket-server."
  - id: unknown1
    size: 3
    doc: "Read but not validated by FUN_00acc424 - same as ticket-server's field of the same name."
  - id: session_token
    type: u4
    doc: "Stored at conn+0x50 - the rolling encrypted-frame key/counter for this connection's client->server traffic (see docs/protocol/0x11_ticket_server_hello.md's 'Encrypted frame layer' section, shared code). leaderboard-server has the richest post-hello traffic of any sibling mapped this pass (a looped, line-oriented bulk-fetch sub-protocol in addition to a single-shot score-submit shape - see docs/protocol/0x11_sibling_servers_family.md) - getting this counter right matters more here than for the single-round-trip siblings."
