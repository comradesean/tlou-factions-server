meta:
  id: host_rank
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingHostRank - server -> client, over the Session Manager
  connection (port 7314). One of the 11 opcodes the client's own
  receive-dispatch (FUN_00ad7604) has a case for.

  STATUS: declared size in the Init() size table is 16 bytes - CONFIRMED
  WRONG. The dispatch case requires >143 buffered bytes and consumes exactly
  144 (0x90) bytes. Looks up the room matching room_id (same room_id-echo
  pattern used throughout this opcode family), then copies a 128-byte block
  (offset 16 onward) into that room's struct at +0x18 via a helper
  (_opd_FUN_00e45b10) whose own internal size argument wasn't captured this
  pass - the 128-byte figure is inferred from the packet's total confirmed
  size (144) minus this handler's 16-byte header, not read directly off a
  size literal. Declared name plausible (a per-member rank/host-eligibility
  table sized for a multi-member room would fit a 128-byte blob) but the
  block's internal layout is entirely unconfirmed.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x144 (324 decimal), passed through FUN_00a0e324 in place before dispatch - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: unknown_4
    size: 4
    doc: "Offset 4:8. Not read by the traced portion of the 0x144 dispatch case - unconfirmed."
  - id: room_id
    type: u8
    doc: "Offset 8:16. Compared against the session's own tracked room id - same room_id-echo pattern used throughout this opcode family."
  - id: rank_data
    size: 128
    doc: "Offset 16:144. Copied verbatim into the matched room's struct at +0x18. Internal layout (likely per-member rank/host-priority entries) not reversed this pass."
