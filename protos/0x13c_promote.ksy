meta:
  id: promote
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingPromote - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only). Pairs with
  0x13d/OwnerChanged, the server's confirmation of the same ownership
  change.

  STATUS: confirmed 16 bytes (matching the declared size), sender fully
  identified 2026-08-15 via instruction-level disassembly of vtable+0x28
  (`FUN_00ad6408`). Every field's exact store instruction was located.

  LIVE-VERIFIED 2026-08-18 (first retained wire capture of this opcode - it was
  previously disassembly-only). Two promotions were captured in one party,
  in both directions, with the full round trip:

    21:43:03  in  conn1  0x13c new_owner=2        (host promotes the other member)
    21:43:03  out both    0x13d OwnerMemberChanged + 0x13f HostFlagUpdated
    21:43:03  in  conn1  0x13e SetHostFlag        (demoted host acknowledges)
    21:43:17  in  conn2  0x13c new_owner=1        (promoted back)
    21:43:17  out both    0x13d + 0x13f
    21:43:17  in  both   0x13e SetHostFlag

  So the server's correct response to a Promote is `0x13d OwnerMemberChanged`
  plus `0x13f HostFlagUpdated` to EVERY member, and the clients confirm by
  sending their own `0x13e`. Ownership changed both ways with no churn.

  IMPORTANT CONTRAST with the join-in-progress rule: re-firing `0x13d` into an
  already-established room is what broke JIP (see
  research/notes/2026-08-18-jip-handoff.md), but that is not a contradiction -
  there the owner had NOT changed and the re-announcement was spurious. Here the
  owner genuinely changes, and `0x13d` is exactly the right message. The rule is
  "never re-assert UNCHANGED ownership", not "never send 0x13d".

  Note the live `pad_6` bytes are `f940` in both frames, not zero - sender-side
  residue, consistent with the rest of the family.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13c (316 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: new_owner_member_id
    type: u2
    doc: "Offset 4:6. The function's third argument (a caller-supplied u16 member id), passed through the equally-no-op _opd_FUN_00a0e320 before send - the member being promoted to room owner. Pairs with 0x13d/OwnerChanged's own new_owner_member_id field."
  - id: pad_6
    size: 2
    doc: "Offset 6:8. Alignment padding. DEFINITION: the 2-byte gap between the u16 new_owner_member_id (wire 4:6) and the 8-byte-aligned room_id (wire 8). REASON: the builder FUN_00ad6408 writes member_id (`sth r5,116(r1)` @0xad6490) then room_id (`std r4,120(r1)` @0xad648c) and never touches 118..119, which align room_id. Send 0. (Was `unknown_2`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field (`std r4,0x78(r1)` in the disassembly) - matches the room_id-echo pattern used throughout this opcode family, and confirms that pattern is a genuine unswapped-longlong copy, not just a coincidence of C-level decompile."
