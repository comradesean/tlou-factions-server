meta:
  id: room_search
  endian: be
  license: CC0-1.0
doc: |
  Direction: bidirectional - primary framing is client-sent, but the client's own receive-dispatch (FUN_00ad7604) also has a confirmed case for this opcode; see below and docs/protocol/session_manager_and_matchmaking.md

  NetMatchmakingRoomSearch - client -> server, over the Session Manager
  connection (port 7314). Client's own receive-dispatch (FUN_00ad7604) has a
  case for 0x136 too (this file documents that dispatch decompile).

  STATUS: declared size in the Init() size table is a fixed 36 bytes - CONFIRMED
  WRONG. The dispatch case computes its real minimum size as
  `entry_count * 0x38 + 0x10` (a 16-byte header plus entry_count 56-byte
  entries) and only proceeds once that many bytes are buffered - this is a
  variable-length message, not a fixed 36-byte one. entry_count sits at
  offset 12; entries start at offset 16 and are copied (with a nontrivial
  per-byte reordering shuffle, not decompiled field-by-field this pass) into
  a destination struct at a room-adjacent pointer.

  UNRESOLVED: the destination pointer (read from offset 8, dereferenced
  directly as a struct pointer at `+0xa8`/`+0x208` rather than looked up via
  the 4-slot room-id search loop every other 0x12d-0x148 case in this
  dispatcher uses) does not fit this family's usual room_id-echo pattern -
  it's read and used as a raw pointer, not compared against a tracked id.
  Whether offset 8 is genuinely wire-supplied here or this handler is
  reusing session-local state that happens to overlap the receive buffer at
  that address is NOT resolved by static analysis alone - flagged for a live
  capture to settle. Per-entry (56-byte) field semantics are entirely
  unconfirmed.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x136 (310 decimal). Passed through a dedicated per-opcode field-touching helper (_opd_FUN_00ad5730) - decompiled 2026-08-15 and confirmed to be composed entirely of calls to the no-op FUN_00a0e324, so this stays plain big-endian; see research/notes/2026-08-15-byteswap-helper-is-a-noop.md."
  - id: unknown_header
    size: 8
    doc: "Offset 4:12. Unconfirmed - offset 8 specifically is read as a raw pointer by this handler rather than compared as a room_id like every other opcode in this family; see doc-ref for the open question."
  - id: num_entries
    type: u4
    doc: "Offset 12:16. Number of 56-byte entries following. Confirmed structurally: this dispatch case's minimum-size check is literally `num_entries * 0x38 + 0x10`."
  - id: entries
    type: room_search_entry
    repeat: expr
    repeat-expr: num_entries
    doc: "Offset 16 onward, 0x38 (56) bytes each. Per-field semantics unconfirmed - copied via a nontrivial byte-reordering shuffle this pass did not fully reverse."
types:
  room_search_entry:
    seq:
      - id: raw
        size: 0x38
        doc: "STATUS: unconfirmed. Placeholder - the sending/receiving code reorders sub-fields byte-by-byte rather than doing a straight copy, and that shuffle was not fully reversed this pass."
