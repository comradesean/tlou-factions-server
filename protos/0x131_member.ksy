meta:
  id: member
  endian: be
  license: CC0-1.0
doc: |
  Direction: server-to-client

  NetMatchmakingMember - server -> client roster broadcast over the Session
  Manager connection (port 7314), presumably sent after RoomCreate/RoomJoin
  to populate/update a room's member list. Field layout decompiled from
  FUN_00ad7604 (SessionManager's receive-dispatch loop, vtable+0x4 at base
  0x01243b38), the `iVar8 == 0x131` case, cross-checked against the raw
  disassembly at the same address (see docs/protocol/0x131_member.md for the
  full trace) and against research/ghidra/sessmgr_vtable_dump.txt lines
  ~195-264 (partially decompiled in an earlier pass).

  STATUS: variable-length total size (0xa0 header + 0x68 per roster entry)
  and the header/entry field offsets below are confirmed mechanically from
  the decompile's own field-touching helper (_opd_FUN_00ad6e34, which
  touches exactly these offsets) and buffer-size-check arithmetic. That
  helper was previously described as a byte-swap - now decompiled and
  confirmed to be composed entirely of calls to the no-op FUN_00a0e324/
  FUN_00a0e320 (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so
  every field it touches is plain big-endian, not runtime-swapped. The
  per-entry "attribute" block and the header's offset-4 field are
  unconfirmed, same caveat as RoomJoined's equivalent regions.

  DANGER - NOT IMPLEMENTED IN tools/session_manager_stub.py THIS PASS: the
  header's offset 8 (room_ptr field, see below) is read straight off the
  wire and immediately dereferenced through a C++ vtable call with NO null
  or validity check anywhere in the traced disassembly
  (research/ghidra/dispatch_raw2.txt lines ~118-127, `lwz r24,0x8(r28)` ->
  `lwz r9,0x0(r29)` -> `bctrl`, r29 built directly from r24). This means the
  server is expected to supply the address of an object the CLIENT ITSELF
  already allocated (its own room-slot object) - not something a remote
  server can legitimately compute. Sending any value that isn't the exact
  live pointer the client is holding will almost certainly crash the
  emulator (an unmapped-page or garbage-vtable dereference), which is worse
  than the current graceful "spins into Lobby Server Error" outcome. Do not
  send this message without first live-debugger-confirming the real pointer
  value for the specific test run (addresses are stable within one RPCS3
  session per this project's "no ASLR" findings elsewhere, but not
  confirmed stable enough to hardcode blind).

  IMPORTANT CORRECTION: the opcode/size debug-log table claims 104 bytes for
  this opcode. That's the PER-ENTRY size only (0x68 = 104, confirmed - the
  loop steps its entry pointers by exactly this much) - the actual on-wire
  message is a 160-byte header plus 104 bytes per roster entry, variable
  total length. Fourth such correction found this session (after
  ClientHello2, Ping, RoomJoined).
doc-ref: ../docs/protocol/0x131_member.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x131 (305 decimal)."
  - id: unknown_field
    type: u4
    doc: "Offset 4. Touched (not swapped - see doc-level note) by _opd_FUN_00ad6e34 but not read anywhere in the traced 0x131 case body. Unconfirmed."
  - id: room_ptr
    type: u4
    doc: "Offset 8. DANGEROUS - see doc-level warning above. Read as a raw client-side object pointer and immediately dereferenced through its own vtable with no validity check. Do not guess this value; requires a live debugger read of the client's own room-slot address for the specific test session."
  - id: owner_ref_id
    type: u2
    doc: "Offset 12. Compared (XOR) against each roster entry's own member_id (offset 36 within each entry, see member_entry below) - a match marks that entry as the room owner (sets the client's internal owner-member index)."
  - id: local_ref_id
    type: u2
    doc: "Offset 14. Same mechanism as owner_ref_id but marks the matching entry as the LOCAL player (sets the client's internal 'this is me' member index). For a solo host, this and owner_ref_id should both equal the single roster entry's own member_id."
  - id: room_id_overwrite
    size: 8
    doc: "Offset 16-23. Copied verbatim into the target room object's own id field (the SAME field RoomJoined's create_id gate-checks against, confirmed offset-identical: room_obj+0x10). Sending anything other than zero here would change the room's id out from under the already-established RoomJoined convention (confirmed live to need to be zero) - send zero to avoid disturbing it."
  - id: room_capacity_field
    type: u2
    doc: "Offset 24. Stored into the target room object at a separate internal field (room_obj+0x1f8, distinct from the id field above). Unconfirmed semantics - plausibly a max-member-count or similar capacity value."
  - id: roster_count
    type: u2
    doc: "Offset 26. Number of member_entry records that follow the 160-byte header. Confirmed - directly used as the dispatch loop's own iteration bound and as the multiplier in the message's total-size check (`0x68 * roster_count + 0xa0`)."
  - id: unknown_field2
    type: u2
    doc: "Offset 28. Touched (not swapped - see doc-level note) by _opd_FUN_00ad6e34 but not read in the traced case body. Unconfirmed."
  - id: header_padding
    size: 130
    doc: "Offset 30-159. Not read by the traced code at all in this pass - padding to reach the confirmed 160-byte (0xa0) header size implied by the buffer-size-check arithmetic. Send zero."
  - id: entries
    type: member_entry
    repeat: expr
    repeat-expr: roster_count
    doc: "roster_count x 104-byte (0x68) entries, starting immediately after the 160-byte header."
types:
  member_entry:
    seq:
      - id: attributes
        size: 36
        doc: "Offset 0 within entry. 18x u16 fields, copied into a local struct passed to _opd_FUN_00ad33d8 alongside this entry's identity flags. Same unconfirmed-semantics caveat as RoomJoined's own 'attributes' block - structurally parallel (both are 18x u16 clusters), plausibly a shared room/member-attribute sub-format, not independently mapped field-by-field this pass."
      - id: member_id
        type: u2
        doc: "Offset 36 within entry. This entry's own id, XOR-compared against the header's owner_ref_id/local_ref_id to determine identity flags for this specific member."
      - id: unknown_byte
        type: u1
        doc: "Offset 38 within entry. Read (local_98) but not further traced. Unconfirmed."
      - id: flags_byte
        type: u1
        doc: "Offset 39 within entry. Read (local_e0) but not further traced - plausibly a status/ready flag. Unconfirmed."
      - id: trailing
        size: 64
        doc: "Offset 40-103 within entry. Not read by the traced dispatch-loop code at all - by structural parallel with RoomJoined's own trailing 64-byte region (also unread by fixed offset, treated as a pointer target there), likely a per-member name/NpId buffer. Not independently confirmed this pass."
