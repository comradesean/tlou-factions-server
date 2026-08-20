meta:
  id: host_flag_updated
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingHostFlagUpdated - server -> client, over the Session
  Manager connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for; handler confirmed at
  0x00ad825c. Pairs with 0x13e/SetHostFlag, the client's request for the
  same flag change.

  RENAMED from `updated_attr_flags` to match the disassembly-verified
  opcode map and to pair cleanly with 0x13e/SetHostFlag.

  STATUS: confirmed 16 bytes, matching the declared size exactly. Looks up
  the room matching room_id (struct+0x10, same room_id-echo pattern used
  throughout this opcode family), then writes the low bit of the byte at
  offset 4 into that room's own struct at +0x19f4 - the "is owner"/"is
  host" flag. Name and behavior agree cleanly.

  *** WAS THE HIGHEST-VALUE UNSENT MESSAGE IN THE FAMILY (2026-08-16) - NOW
  SENT AND LIVE-VERIFIED (status corrected 2026-08-19) ***

  `server/session_manager.py` sends this on the solo-host path and on every
  ownership change; 271 frames in a single day's capture, and it is part of the
  live-verified Promote round trip (0x13c -> 0x13d + 0x13f to every member, see
  protos/0x13c_promote.ksy). The text below records WHY it was needed and
  remains the evidence for the field's meaning: without it a solo-hosting client
  never learns it is the host. Full evidence in
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 2; the short version:

  - `room_obj+0x19f4` is confirmed to be "I am the room owner/host" by the
    0x13e/SetHostFlag sender at 0x00ad6b58, which reads it as the current
    state, REJECTS a promote when it is already 1 and a demote when it is
    already 0, and otherwise sets it to the requested value.

  - The RoomCreate sender `FUN_00ad5b78` (vtable +0x10, confirmed by its
    `li r0,303` at 0x00ad5c38) CLEARS it unconditionally on the create path:
        ad5c6c:  li   r27,0
        ad5c98:  stb  r27,6644(r31)     ; room_obj+0x19f4 = 0
    with r31 = the room object (`mr r31,r4` at 0x00ad5b84).

  - A full-binary objdump sweep for displacement 6644 finds exactly four
    writers: 0x00ad1f58 (internal), 0x00ad5c98 (RoomCreate, sets 0), the two
    0x13e/SetHostFlag builders (only from an explicit in-UI promote/demote
    action), and 0x00ad82cc - THIS HANDLER. No other inbound message can
    set it.

  - Readers in the game/lobby layer: 0x00397e08, 0x003cab10 (inside the
    9-state room state machine dispatched by `_opd_FUN_003ca9d0`, gating a
    large block behind `if (room_obj+0x19f4 == 0) skip`), and 0x003cb3d0
    (`FUN_003cb204`, skipping its `_opd_FUN_00ad124c` owner bookkeeping).

  *** THE FLAG LEAVES THE CONSOLE - ADDED 2026-08-20 ***

  `room_obj+0x19f4` is not console-local state. When the room in question is
  the PARTY object (0x01387f58), the presence publisher copies the byte
  verbatim into the outgoing presence blob:

      00397dfc  lwz r9,-32756(r30)   ; r9 = 0x01387f58, resolved through the
                                     ; net-friends anchor 0x012714e8 -> slot
                                     ; 0x012694f4
      00397e08  lbz r0,6644(r9)      ; *(party_obj+0x19f4)
      00397e10  stb r0,127(r1)       ; presence blob offset 7

  and a REMOTE player's client reads that byte to decide whether to draw the
  "Join Party" row for this player in its friends list:

      00348e14  -> 1 when the friend has no usable presence data, else
                   `blob[7] != 0`
      0034be00  bl 0x00348e14
      0034be10  bne -> 0x0034be8c    ; nonzero: the "Join Party" item
                                     ; (StringId 0xb1600ce3, text1.psarc
                                     ; 2.common) is never written

  So sending `flag = 1` for a PARTY room makes that party unjoinable from
  every friend's list, silently and permanently. A party host is meant to sit
  at the 0 its own RoomCreate sender wrote. `server/session_manager.py` now
  sends 0 on the party-create path and keeps 1 only for game rooms, whose copy
  of the byte never reaches presence. See
  research/notes/2026-08-20-rejoin-party-bug.md.

  This is a DIFFERENT and complementary piece of ownership state from
  0x13d/OwnerChanged, which writes `room_obj+0x19f0` ("which member id is
  the owner"). Neither is currently sent by server/session_manager.py.

  SEQUENCING (hard requirement): room_obj+0x10 is set ONLY by Member's
  (0x131) handler. Send 0x13f strictly AFTER Member - sent first, the
  4-slot search finds nothing and the message is silently dropped with no
  error.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13f (319 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: flag
    type: u1
    doc: "Offset 4:5. Only the low bit is used (ANDed with 1) before being stored into the matched room's +0x19f4 'is host' flag byte. WHEN THE ROOM IS THE PARTY OBJECT THIS VALUE IS PUBLIC: the presence publisher exports it as presence blob offset 7 (0x00397e08/0x00397e10) and a remote client hides its \"Join Party\" menu row for any friend advertising a nonzero byte (0x00348e14, `bne` @0x0034be10). Send 0 for a party host; 1 is for a game room that genuinely needs the host flag set."
  - id: pad_5
    size: 3
    doc: "Offset 5:8. ALIGNMENT PADDING (proven 2026-08-18): the 0x13f receive arm (FUN_00ad825c, opcode 319) loads only wire+0 (opcode), wire+4 (`lbz r3,4(r29)` = host-flag byte, whose low bit -> room_obj+0x19F4) and wire+8 (room_id); wire+5..7 are never loaded. Definition: 3-byte gap aligning the 8-byte room_id after the single flag byte at +4. Not a field - send 0. (Was `unknown_3`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against `*(s64*)(room_obj+0x10)` for each of the connection's 4 room slots (slot i's room-object pointer is at `this + i*0x9000 + 0x50`; the `addis r11,r11,1 / addi r11,r11,-28672` idiom is a 0x9000 stride). Silently dropped if no slot matches - and room_obj+0x10 is set ONLY by Member's (0x131) handler, so this message must follow a Member. Same room_id-echo pattern used throughout this opcode family."
