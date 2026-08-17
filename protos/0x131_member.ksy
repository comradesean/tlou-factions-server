meta:
  id: member
  endian: be
  license: CC0-1.0
  imports:
    - common/member_data
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

  ROOM_PTR HAZARD - SOLVED 2026-08-16. The header's offset 8 is read straight
  off the wire and immediately dereferenced through a C++ vtable call with NO
  null or validity check (`lwz r24,0x8(r28)` @ 0x00ad77d4 -> `lwz r9,0x0(r29)`
  -> `bctrl`). It must be the address of an object the CLIENT ITSELF
  allocated. Previously this required a live RPCS3 debugger breakpoint and was
  hardcoded in tools/session_manager_stub.py as ROOM_PTR = 0x01383bd8.

  **The client hands it to us on every RoomCreate.** `FUN_00ad5b78` (the
  0x12f/RoomCreate sender) stores its own room-object pointer into RoomCreate
  wire offset 8 (`stw r29,152(r1)` @ 0x00ad5f34, buffer base r1+144, r29 =
  the room object). Live proof from captures/tcp_catch.log: comradesean's
  client sends `01 38 3b d8` there - byte-for-byte the value the debugger
  breakpoint recovered - and a second real client (mgnomad2) sends
  `01 38 7f 58`. Read RoomCreate's `chunk[8:12]` per connection instead of
  hardcoding; the hardcoded constant is wrong for any client other than the
  one it was captured from, and sending one client's pointer to another is a
  wild-pointer vtable dereference. (0x130/RoomJoin's offset 8 is the same
  kind of pointer and is the right source on the join path.)

  MEMBER REGISTRATION IS FIRST-WRITE-WINS - SEQUENCING HAZARD. Each roster
  entry is passed to `_opd_FUN_00ad33d8(room_obj, local_struct, is_local,
  is_owner, ...)`, which first walks the room's 12 member slots
  (`room + i*0x180 + 0x668`, occupied byte at +0xe0) comparing NpIds via
  `_opd_FUN_00e459bc(slot, local_struct+4)`. **On a match it returns
  immediately and updates NOTHING** - not is_local, not is_owner, not the
  member id (0x00ad3430-0x00ad3478). Only on a miss does it allocate a slot
  and, at 0x00ad37b8:

      if (is_local != 0) *(u32*)(room_obj+0x19ec) = new_slot->member_id;
      if (is_owner != 0) *(u32*)(room_obj+0x19f0) = new_slot->member_id;

  and, at 0x00ad34a4, for NON-local members only:

      *(u32*)(slot+0xf0) = g_singleton->vtable[0x10](g_singleton, npid);

  i.e. it opens an NP signaling connection for every member registered with
  is_local == 0. Because 0x132/RoomJoined's handler passes is_local=0 AND
  is_owner=0 hardcoded (`li r5,0; li r6,0` @ 0x00ad7bdc/0x00ad7be8), sending
  a RoomJoined that carries the RECIPIENT'S OWN NpId makes the client attempt
  NP signaling to itself (SCE_NP_SIGNALING_ERROR_OWN_NP_ID) and registers a
  second, phantom member record that Member's own entry can never merge with
  or correct. See
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 3.

  MEMBER IS THE ROOM-CREATE COMPLETION SIGNAL, NOT RoomJoined. After the
  roster loop, at 0x00ad79ec:

      if (*(u8*)(room_obj+0xac) == 0) {          // ONE-SHOT LATCH
          if (*(s64*)(room_obj+0x10) != 0) {
              *(u32*)(room_obj+0xb0) = 0;        // error code = 0
              *(u32*)(room_obj+0xb4) = 1;        // success
              room_obj->vtable[0x1c](room_obj);  // "room create completed"
          } else {
              *(u32*)(room_obj+0xb4) = 0;
              *(u32*)(room_obj+0xb0) = -1;       // error
          }
          *(u8*)(room_obj+0xac) = 1;
      }

  The latch means the FIRST Member the client processes decides success or
  failure permanently: if its room_id_overwrite field is zero, the room is
  latched into the error state and no later Member can undo it.

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
    doc: "Offset 8. Raw client-side room-object pointer, immediately dereferenced through its own vtable with no validity check. NEVER guess this value - read it from the same connection's RoomCreate (0x12f) wire offset 8, or RoomJoin (0x130) wire offset 8 on the join path. See the doc-level 'ROOM_PTR HAZARD - SOLVED' note above."
  - id: owner_ref_id
    type: u2
    doc: "Offset 12. Compared (XOR) against each roster entry's own member_id (offset 36 within each entry, see member_entry below) - a match marks that entry as the room owner (sets the client's internal owner-member index)."
  - id: local_ref_id
    type: u2
    doc: "Offset 14. Same mechanism as owner_ref_id but marks the matching entry as the LOCAL player (sets the client's internal 'this is me' member index). For a solo host, this and owner_ref_id should both equal the single roster entry's own member_id."
  - id: room_id_overwrite
    size: 8
    doc: "Offset 16-23. Copied verbatim into the target room object's id field, room_obj+0x10 (`ld r9,16(r28)` / `std r9,16(r29)` @ 0x00ad7804-0x00ad780c). MUST BE NONZERO: the one-shot completion latch at 0x00ad79ec reads this field immediately afterwards and permanently latches the room into an error state (room_obj+0xb0 = -1) if it is zero. It is also the lookup key for every subsequent room-scoped message (0x134, 0x139, 0x13b, 0x13d, 0x13f, 0x141, 0x144) - all of them are silently dropped until this is set. The server chooses this value freely; RoomCreate does not supply one (its offset 4 is uninitialised stack, see protos/0x12f_room_create.ksy)."
  - id: room_capacity_field
    type: u2
    doc: "Offset 24. Stored into room_obj+0x1f8 (`lhz r0,24(r28)` / `stw r0,504(r29)` @ 0x00ad7800-0x00ad7808) - the max-member count. `_opd_FUN_00ad33d8` has a compiled-in `if (room_obj+0x1f8 == 0) trap` assert (live-crash-confirmed) and compares the occupied-slot count against it at 0x00ad38c8 to decide whether to reject a new member. The authoritative source is RoomCreate's own wire offset 0x24 (NOT 0x1e - see protos/0x12f_room_create.ksy correction 3), live-constant 8; the client itself writes that same value into room_obj+0x1f8 at RoomCreate time."
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
        doc: "Offset 0 within entry. Copied byte-by-byte (0x00ad786c-0x00ad79a8) into the local struct's +4..+0x27 that is handed to `_opd_FUN_00ad33d8` as param_2. CONFIRMED 2026-08-16: the FIRST 16 BYTES ARE THIS MEMBER'S SceNpId HANDLE - that is the key `_opd_FUN_00ad33d8` dedupes on (`_opd_FUN_00e459bc(slot, param_2+4)`, the same 16-byte NpId comparator used elsewhere in the binary), and the value the non-local branch feeds to the signaling-connection resolve at 0x00ad34a4. Bytes 16..35 remain unmapped."
      - id: member_id
        type: u2
        doc: "Offset 36 within entry. This entry's own id, XOR-compared against the header's owner_ref_id/local_ref_id (0x00ad795c-0x00ad79bc: `xor` then `addi -1` then `srdi 63`, i.e. is_x = (member_id == x_ref_id)) to derive the is_local/is_owner arguments to `_opd_FUN_00ad33d8`. Those two flags are what set room_obj+0x19ec (my member id) and room_obj+0x19f0 (the owner's member id). Note they are only applied on FIRST registration of this NpId - see the doc-level first-write-wins note."
      - id: unknown_byte
        type: u1
        doc: "Offset 38 within entry. Read (local_98) but not further traced. Unconfirmed."
      - id: member_data_length
        type: u1
        doc: |
          Offset 39 within entry. CORRECTED 2026-08-17: the LENGTH of the
          member_data record at offset 40. The Member dispatch (0x00ad79b8/
          0x00ad79c8 -> _opd_FUN_00ad33d8) memcpys member_data[0:this_length]
          into the member slot's +0xFC field and writes this length into
          member_slot+0xF8. Must be <= 64 (compiled assert at 0x00ad3744).
          CRITICALLY, the card UI getter _opd_FUN_00ad2650 returns the record
          only if this length is exactly 32 (`cmpwi 32; beq` @ 0x00ad2734) -
          any other length renders the remote player's card as absent. Live 32.
      - id: member_data
        type: member_data
        doc: |
          Offset 40:72 within entry. The player's lobby card (team/faction,
          loadout, rank) - each field decoded in common/member_data.ksy. The
          member's DISPLAY NAME does NOT come from here; it comes from the
          SceNpId in the first 16 bytes of the `attributes` block above. The
          client also supplies this same record at runtime via 0x13a and it is
          re-delivered per-member via 0x13b; Member SEEDS it, 0x13b UPDATES it
          (the dedupe early-return means the refresher cannot update an
          already-registered member).
      - id: member_data_padding
        size: 32
        doc: "Offset 72:104 within entry. Send-zero padding after the 32-byte member_data (the slot field is 64 bytes but only 32 are meaningful)."
