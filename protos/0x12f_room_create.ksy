meta:
  id: room_create
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingRoomCreate - sent by the client over the Session Manager
  connection (port 7314) when the player chooses to host a game. Fixed 232
  bytes, matching the opcode/size debug table exactly.

  STATUS (rewritten 2026-08-16): the send site is now fully disassembled -
  `FUN_00ad5b78` (SessionManager vtable +0x10), confirmed by its `li r0,303`
  opcode literal at 0x00ad5c38 and its
  `_opd_FUN_00acb93c(this+0x25060, buf, 0xe8, 1)` send call at 0x00ad5fac.
  The send buffer's base is `r1+144`, so wire offset = (r1 offset) - 144.
  EVERY store into that buffer was enumerated exhaustively from the
  disassembly and then cross-checked against 30 live RoomCreate captures in
  captures/tcp_catch.log. See
  research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md
  section 4 for the full table and the raw instruction evidence.

  THREE CORRECTIONS to the previous version of this file, all high
  confidence:

  1. There is NO `create_id` at offset 4. Offsets 4:8 are never written by
     the sender - no store to `148(r1)` exists anywhere in the function - so
     they carry uninitialised stack. The live captures prove it directly:
     the same client emits `01 27 23 d8` there in one session and
     `00 00 00 00` in the next with every other field identical. The
     8-byte room id this protocol family uses everywhere else is the
     SERVER's to choose; RoomCreate does not supply one.

  2. Offset 8 is a 4-byte raw pointer to the CLIENT'S OWN room object
     (`stw r29,152(r1)` at 0x00ad5f34, where r29 is this function's own
     `param_2`/room object). This is the same value `Member` (0x131) wire
     offset 8 must echo back and immediately dereferences through an
     unchecked vtable call. Live-proven: comradesean's client sends
     `01 38 3b d8`, which is byte-for-byte the address a live RPCS3
     debugger breakpoint previously recovered and which
     tools/session_manager_stub.py hardcodes as ROOM_PTR; a second real
     client (mgnomad2) sends `01 38 7f 58`. Read it off this field per
     connection instead of hardcoding it.

  3. max-players/capacity is at offset 0x24, NOT 0x1e. Offset 0x1e is
     another never-written gap (between the `sth ...,172(r1)` and
     `sth ...,176(r1)` stores) and reads as stack leftovers - `00 0a` or
     `00 00` across the captures. Offset 0x24 is `sth r23,180(r1)`, and the
     same r23 is simultaneously written to `room_obj+0x1f8` at 0x00ad5f80 -
     the exact field `_opd_FUN_00ad33d8`'s compiled-in capacity assert
     checks. Live-constant `00 08` in every capture.
doc-ref: ../docs/protocol/0x12f_room_create.md
seq:
  - id: opcode
    type: u4
    doc: "Offset 0. Fixed 0x12f (303 decimal). `stw r0,144(r1)` @ 0x00ad5c40."
  - id: uninitialised_4
    size: 4
    doc: "Offset 4:8. NEVER WRITTEN by the sender - uninitialised stack. Previously and wrongly documented as an 8-byte `create_id` spanning 4:12. Do not read anything from here; live captures show it varying between `01 27 23 d8` and `00 00 00 00` on the same client across sessions."
  - id: room_ptr
    type: u4
    doc: "Offset 8:12. The client's own in-process room-object pointer, copied verbatim (`stw r29,152(r1)` @ 0x00ad5f34). THIS is where a server gets the value it must echo into Member's (0x131) own offset-8 room_ptr field. Differs per client - live-captured as 0x01383bd8 (comradesean) and 0x01387f58 (mgnomad2)."
  - id: room_field_0c
    type: u4
    doc: "Offset 12:16. Verbatim copy of `*(u32*)(room_obj + 0x0c)` (`lwz r0,12(r31)` / `stw r0,156(r1)` @ 0x00ad5f30). This is the field previously nicknamed `map_id`; that label is DISPUTED (see research/notes/2026-08-16-map-id-vs-team-confound.md). Live values: 0x02, 0x09, 0x12, 0x13. Whatever it means, its real home is room_obj+0x0c - trace the writer of that, not this wire field."
  - id: region_language
    size: 4
    doc: "Offset 16:20. Region/language, built from the sceNpManagerGetAccountRegion / GetMyLanguages pair this function calls. Live-constant `75 73 00 01` = \"us\\0\" + language 1."
  - id: room_flags_e8
    type: u4
    doc: "Offset 20:24. `*(u32*)(room_obj + 0xe8)`, conditionally OR'd with 0x40000000 (`oris r0,r0,16384` @ 0x00ad5c4c). Live values `00 0c 50 3f`, `10 2c 50 3f`, `20 0c 50 3f` - the low 20 bits are constant across captures, the top nibble varies."
  - id: zero_18
    type: u2
    doc: "Offset 24:26. Always 0 (`sth r24,168(r1)` @ 0x00ad5c94 with r24=0)."
  - id: zero_1a
    type: u2
    doc: "Offset 26:28. Always 0 (`sth r24,170(r1)`)."
  - id: caller_arg_1c
    type: u2
    doc: "Offset 28:30. A caller-supplied argument (`sth r27,172(r1)` @ 0x00ad5c60, before r27 is reset to 0). Live values `ff ff` and `00 00`."
  - id: uninitialised_1e
    size: 2
    doc: "Offset 30:32. NEVER WRITTEN - uninitialised stack. tools/session_manager_stub.py reads max_players from here; that is a bug (see doc, correction 3). Live values `00 0a` and `00 00`."
  - id: value_20
    type: u2
    doc: "Offset 32:34. A float converted to int via fctiwz. Live-constant 1000 (0x03e8)."
  - id: value_22
    type: u2
    doc: "Offset 34:36. Second float converted to int. Live-constant 1000 (0x03e8)."
  - id: max_players
    type: u2
    doc: "Offset 36:38. Max players / room capacity. `sth r23,180(r1)`, and the SAME r23 is written to `room_obj+0x1f8` at 0x00ad5f80 - the field `_opd_FUN_00ad33d8`'s `if (room_obj+0x1f8 == 0) trap` assert reads and the field Member's (0x131) offset 24 overwrites. Live-constant 8 across every capture. This is the field a server should echo into Member's capacity slot."
  - id: room_field_19f8
    type: u1
    doc: "Offset 38:39. `*(u8*)(room_obj + 0x19f8)` (`stb r11,182(r1)`). Live value 0x20."
  - id: flag_27
    type: u1
    doc: "Offset 39:40. 0 normally, 4 on one conditional branch (`stb r0,183(r1)` @ 0x00ad5cbc). Live values 0x00 and 0x04."
  - id: room_name
    size: 128
    doc: "Offset 40:168. NUL-terminated room name, produced by `_opd_FUN_00e45b10(r1+184, room_obj+0x18)` @ 0x00ad5f74 - i.e. a plain strcpy of `room_obj+0x18`. Format is `<npid>.<unix-timestamp>` (e.g. `comradesean.1786863559`), built by the 0x143 sender's own sprintf-like call. room_obj+0x18 is the SAME 128-byte region 0x143 sends and 0x144 strcpy's into on receipt - see protos/0x143_set_room_name.ksy."
  - id: room_tail_block
    size: 64
    doc: "Offset 168:232. Verbatim byte-by-byte copy of `room_obj+0x19fc .. +0x1a3b` (copy loop 0x00ad5d30-0x00ad5f2c into r1+312). The live-confirmed team-selection field at wire offset 0xb0 (0=unset, 1=Blue, 2=Red - see research/notes/2026-08-16-team-selection-field-confirmed.md) is the u16 at relative offset 8 within this block, i.e. `room_obj+0x1a04`."
