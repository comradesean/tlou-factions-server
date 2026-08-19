meta:
  id: single_player_server_hello
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

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
    doc: "NUL-terminated ASCII, observed/expected value \"single-player-server\" (string address 0x00e62aa8 in this build). Same buffer/copy mechanism as ticket-server's field."
