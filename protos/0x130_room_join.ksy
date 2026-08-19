meta:
  id: room_join
  endian: be
  license: CC0-1.0
  imports:
    - common/member_data
doc: |
  Direction: client-to-server

  NetMatchmakingRoomJoin - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only, no reply
  processing implemented client-side).

  STATUS: confirmed 88 bytes (matching the declared size), sender fully
  identified 2026-08-15 via instruction-level disassembly (not just C
  decompile) of vtable+0x18 (`FUN_00ad6718`) and the field-touching helper
  it calls (`_opd_FUN_00ad5580`, disassembled separately to confirm exactly
  which 3 words it touches: offsets 0, 4, 8). That helper - like every
  similar one in this family - is composed entirely of calls to the
  confirmed no-op `FUN_00a0e324` (see
  `research/notes/2026-08-15-byteswap-helper-is-a-noop.md`); it does not
  actually byte-swap anything. Every field below is plain big-endian.

  NOTABLE: offset 8 is NOT this family's usual 8-byte room_id. It's a raw
  4-byte store of the sending client's own in-process room-object pointer
  (register r31/param_2 at the call site) - i.e. an opaque, meaningless-to-
  the-server local value, presumably intended purely as a correlation token
  for whatever reply eventually references it. Offset 4:8 is genuinely
  uninitialized stack (read and passed through the no-op helper along with
  the real fields, but never explicitly written by the caller) - same class
  of finding as the confirmed-garbage second word in 0x133's payload.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x130 (304 decimal), passed through _opd_FUN_00ad5580 (offset 0 of the 3 words it touches) - a confirmed no-op, so this stays plain big-endian."
  - id: pad_4
    size: 4
    doc: "Offset 4:8. Unused word between the opcode (wire 0) and local_room_ptr (wire 8). DEFINITION: not a field. REASON: the builder FUN_00ad6718 stores opcode@112 and local_room_ptr@120 but never writes 116(r1); the buffer is sent whole, so this is leaked stack. Send 0. (Was `unknown_4`.) CONFIRMED STATISTICALLY 2026-08-18: 99% of this gap word's live values are valid PS3 addresses (70% in the main-thread stack 0xd0001000-0xd0040fff, the range the client's own PPU dump reports) - see research/notes/2026-08-18-wire-residue-and-field-corrections.md §1."
  - id: local_room_ptr
    type: u4
    doc: "Offset 8:12. The sending client's own raw in-process room-object pointer at the time of the call (`stw r31,0x78(r1)` in FUN_00ad6718), passed through the same no-op helper as the opcode. An opaque client-local value, not a room_id."
  - id: member_data_length
    type: u1
    doc: |
      Offset 12:13 (wire 0x0c). CORRECTED 2026-08-17 (was "unknown_flag"):
      the LENGTH of the joiner's 32-byte member_data card carried at wire
      offset 0x18 (see member_data below), copied from the room object's own
      +0x19f8 byte (same source as RoomCreate's member_data_length). Live
      0x20 (=32). server/session_manager.py harvests the card keyed by
      this length on every 0x130 and replays it (0x131 roster + 0x13b) so the
      HOST's lobby shows the joiner's rank/faction card - the decisive fix,
      since the matchmade lobby never sends 0x13a and the host would otherwise
      see a blank card. See
      research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md.
  - id: pad_d
    size: 3
    doc: "Offset 13:16. Alignment padding. DEFINITION: the 3-byte gap between the 1-byte member_data_length (wire 12) and the 8-byte-aligned room_id (wire 16). REASON: room_id is stored with `std` at 128(r1); the length byte at 124(r1) leaves 125..127 as an alignment gap FUN_00ad6718 never writes. Send 0. (Was `unknown_3`.)"
  - id: room_id
    type: u8
    doc: |
      Offset 16:24. The TARGET room's id - the room the client is asking to
      join. RESOLVED 2026-08-18: the GAME_LIST_PICK join helper
      `_opd_FUN_003b2f40` calls `vtable+0x18(join_obj, state, *(session+0x98))`
      where `*(session+0x98)` was just compared equal to the picked 0x136
      RoomSearch entry's room_id (research/notes/2026-08-17-find-match-flow.md
      section 2); the raw 8-byte copy here (`std r29,0x80(r1)`) is that value.
      Live-proven: the server (server/session_manager.py) reads chunk[0x10:0x18]
      as the target room id and Join Party + find-match joins work on that
      basis. Was previously the untraced `param3_value`.
  - id: member_data
    type: member_data
    doc: |
      Offset 24:56 (wire 0x18:0x38). The joiner's lobby card - the first 32
      bytes of a 64x single-byte lbz/stb copy of the room object's own bytes
      0x0-0x3f. CORRECTED 2026-08-17 (was "room_snapshot"). Each field is
      decoded in common/member_data.ksy; member_data_length (wire 0x0c) is its
      length. The stub reads chunk[0x18:0x38] to populate the joiner's card in
      the host's roster."
  - id: room_object_tail
    size: 32
    doc: |
      Offset 56:88 (wire 0x38:0x58). RESOLVED 2026-08-19, unlike its `0x12f`
      sibling `room_settings_tail` (which turned out to be pure sender-side
      stack residue, never written at all - see that field's doc for the
      contrast): this one IS a real copy. Confirmed by exhaustively
      disassembling the sender (`FUN_00ad6718`, opcode literal `li r0,304`
      @0xad67a4, send call `_opd_FUN_00acb93c(this+0x25060, buf, 0x58, 1)`
      @0xad69fc, buffer base r1+112): a 64-byte byte-copy loop
      (0xad67a8-0xad69bc) reads `room_obj[0x0:0x40]` into wire offset
      24:88 - `member_data` is `room_obj[0x0:0x20]`, and `room_object_tail`
      specifically is `room_obj[0x20:0x40]`.

      `room_obj` (the function's own `param_2`, `r31`) LIVE-CONFIRMED
      2026-08-19 in RPCS3's debugger: breakpoint at `0x00ad6718` during a
      real party join hit with `r4 = 0x01387f58` - the well-known PARTY
      object, not the game-room object. (The breakpoint fired only on the
      JOINER's client, never the party owner's, confirming this message's
      documented client-to-server/joiner-only direction.) So for this
      sample, `room_object_tail`'s absolute source is
      `0x01387f78:0x01387f98`.

      An exhaustive scan of the whole binary for any reader of that address
      range (both known addressing idioms - the r2-anchor chain and
      `lis`+`addi`/`ori` absolute construction, the same method used for
      `attr_tail` and `member_slot_ec`) found NOTHING - no reader anywhere.
      Same status as those two fields: mechanism and source fully pinned,
      live-verified, no consumer found. RESIDUAL GAPS: (a) this is one
      sample (a party join) - whether a game-room join sends a DIFFERENT
      `room_obj` (and therefore a different absolute range) is untested;
      (b) same as the other two fields, an indexed/bulk-copy reader would
      evade this scan. Send 0.
