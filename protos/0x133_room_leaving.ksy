meta:
  id: room_leaving
  endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: client-to-server

  net_event_type opcode 0x133 (307). Declared table calls this
  NetMatchmakingMemberJoined (naive "0x12d + table index" formula), but that
  name is confirmed WRONG - see doc-ref for full decompiled evidence
  (_opd_FUN_00ad65e8/00ad32c4). This fires when the client decides to abandon
  a room it's tracking: sets a client-local bookkeeping flag on the room
  object, sends this message, zeroes its own local room-id copy, then
  walks every member slot running the exact same per-member removal path the
  confirmed 0x134 (RoomLeave) dispatch case uses. Conceptually a
  "room leaving/abandoned" notice, not a join event.

  SENDER SIDE-EFFECTS, EXACT (re-read 2026-08-20 - the earlier "inactive
  flag" wording had the polarity backwards and hid a server-visible bug):

      ad665c  ld   r9,16(r31)   ; room_id = *(room_obj+0x10)
      ad6664  cmpdi r9,0        ; already 0 -> set the flag and send NOTHING
      ad667c  li   r0,1
      ad6684  stb  r0,184(r31)  ; *(room_obj+0xb8) = 1   -> stays VALID
      ad6690  stw  r0,188(r31)  ; *(room_obj+0xbc) = 0
      ...     build + send the 16 bytes
      ad66e0  std  r0,16(r31)   ; *(room_obj+0x10) = 0   -> id CLEARED
      ad66e4  bl   0xad32c4     ; wipe all 12 member slots

  So the leaver ends up holding a room object that still advertises itself as
  valid (+0xb8 == 1) with a ZERO room id, and no client code path ever puts an
  id back: `room_obj+0x10` has exactly one writer, the 0x131 Member receive arm
  (`ld r9,16(r28)` / `std r9,16(r29)` @0x00ad7804-0x00ad780c), which takes the
  room object from the message's own wire offset 8 and is not gated on +0xb8.
  Only the server can restore it. For a PARTY room that matters immediately:
  the party join/invite state machine at 0x00354ee0 refuses to run while
  `*(0x01387f58+0x10)` is zero (`ld r0,16(r9)` @0x00354f50, `beq` @0x00354f58,
  3000 ms then abort), and the presence blob built at 0x00397d74 publishes that
  same field at blob offset 0x28 - so a party member that leaves becomes unable
  to be invited or to join again until the server hands it a fresh party room
  id. See research/notes/2026-08-20-rejoin-party-bug.md and
  `reseed_departed_party` in server/session_manager.py.

  Client-to-server only, fire-and-forget: not one of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for, so no reply is
  expected - live-confirmed 2026-08-15 (a same-opcode echo reply had zero
  effect on client behavior either way).

  WIRE SIZE CORRECTION 2026-08-18: the message is 16 bytes, not 12. The
  sender is `_opd_FUN_00acb93c(..., 0x10, 1)` (0x10 = 16 bytes) with the
  opcode built into the buffer first, exactly like every sibling in this
  family; an earlier version of this schema omitted the leading opcode field
  and only accounted for 12 of the 16 wire bytes.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Offset 0:4. Fixed 0x133 (307 decimal), built into the send buffer before transmit like every sibling opcode. Plain big-endian (the family's FUN_00a0e324 pass-through is a confirmed no-op, research/notes/2026-08-15-byteswap-helper-is-a-noop.md)."
  - id: pad_4
    type: u4
    doc: "Offset 4:8. Unused word. DEFINITION: not a field. REASON: builder FUN_00ad65e8 reads this slot from uninitialised stack (`lwz r3,116(r1)` @0xad66a8) and writes the same value back through the no-op swap (`stw r3,116(r1)` @0xad66bc) with no prior init - a pass-through of stack garbage, not a deliberate store. Live captures show non-repeating stack-address-shaped values. Send 0. (Was `unknown`.) CONFIRMED STATISTICALLY 2026-08-18: 99% of this gap word's live values are valid PS3 addresses (70% in the main-thread stack 0xd0001000-0xd0040fff, the range the client's own PPU dump reports) - see research/notes/2026-08-18-wire-residue-and-field-corrections.md §1."
  - id: room_id
    type: u8
    doc: "STATUS: confirmed. The room object's own +0x10 id field, read and sent immediately before the client zeroes that same +0x10 field locally. Matches the room_id this server assigns via Member's header. Sent as a raw copy with no processing call around it at all, unlike the opcode field which is passed through FUN_00a0e324 first - though that call is itself a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so both fields end up plain big-endian regardless."
