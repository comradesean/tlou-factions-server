meta:
  id: room_leaving
  endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  net_event_type opcode 0x133 (307). Declared table calls this
  NetMatchmakingMemberJoined (naive "0x12d + table index" formula), but that
  name is confirmed WRONG - see doc-ref for full decompiled evidence
  (_opd_FUN_00ad65e8/00ad32c4). This fires when the client decides to abandon
  a room it's tracking: sets a client-local "inactive" bookkeeping flag on the
  room object, sends this message, zeroes its own local room-id copy, then
  walks every member slot running the exact same per-member removal path the
  confirmed 0x134 (RoomLeave) dispatch case uses. Conceptually a
  "room leaving/abandoned" notice, not a join event.

  Client-to-server only, fire-and-forget: not one of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for, so no reply is
  expected - live-confirmed 2026-08-15 (a same-opcode echo reply had zero
  effect on client behavior either way).
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: unknown
    type: u4
    doc: "STATUS: confirmed garbage. Instruction-level trace (objdump) shows this 4 bytes is read from a stack slot the sending function never writes - genuinely uninitialized stack content at send time, not meaningful data. Matches live captures showing an arbitrary, non-repeating stack-address-shaped value here."
  - id: room_id
    type: u8
    doc: "STATUS: confirmed. The room object's own +0x10 id field, read and sent (unswapped, unlike the opcode field) immediately before the client zeroes that same +0x10 field locally. Matches the room_id this server assigns via Member's header."
