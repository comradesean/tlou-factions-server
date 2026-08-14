meta:
  id: single_player_server_hello
  endian: be
  license: CC0-1.0
doc: |
  First message the client sends after connecting to the
  "single-player-server" backend, on the same raw-TCP opcode-0x11 control
  channel as ticket-server. Fixed size, 0x58 (88) bytes - byte-for-byte
  identical layout to ticket_server_hello.ksy.

  STATUS: confirmed high confidence via the shared-function argument (see
  0x11_heartbeat_server_hello.ksy's doc for the general method). Two
  independent call sites confirmed: FUN_007f1acc (@ 0x007f1acc, call
  0x007f1ce0 - runs right after cellSaveDataListSave2/AutoSave, a
  campaign-save/checkpoint sync) and FUN_00080268 (@ 0x00080268, call
  0x00080594 - a trophy-unlock event handler, sceNpTrophyUnlockTrophy runs
  immediately before it). Despite the name, this service is reached from
  campaign/single-player-adjacent systems (save sync, trophies), not
  matchmaking. See docs/protocol/0x11_sibling_servers_family.md.
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
    doc: "NUL-terminated ASCII, observed/expected value \"single-player-server\" (string address 0x00e62aa8 in this build). Same buffer/copy mechanism as ticket-server's field."
