meta:
  id: room_create
  endian: be
  license: CC0-1.0
  imports:
    - common/member_data
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
     server/session_manager.py hardcodes as ROOM_PTR; a second real
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
  - id: pad_4
    size: 4
    doc: "Offset 4:8. NEVER WRITTEN by the sender - uninitialised stack. Previously and wrongly documented as an 8-byte `create_id` spanning 4:12. Do not read anything from here; live captures show it varying between `01 27 23 d8` and `00 00 00 00` on the same client across sessions."
  - id: room_ptr
    type: u4
    doc: "Offset 8:12. The client's own in-process room-object pointer, copied verbatim (`stw r29,152(r1)` @ 0x00ad5f34). THIS is where a server gets the value it must echo into Member's (0x131) own offset-8 room_ptr field. Differs per client - live-captured as 0x01383bd8 (comradesean) and 0x01387f58 (mgnomad2)."
  - id: room_field_0c
    type: u4
    doc: |
      Offset 12:16. Verbatim copy of `*(u32*)(room_obj + 0x0c)` (`lwz r0,12(r31)`
      / `stw r0,156(r1)` @ 0x00ad5f30).

      DEFINITION: the PLAYLIST ID. A playlist is a DC record that bundles the
      game MODE with its PARTY RULES, so this one field covers what the UI
      presents as two separate choices. The table ships inside the netN.bin
      config bundle, which is why the numbering is PER BUILD. The binary asserts
      `(playlist & 0xFFFFFF00) == 0` (VMA 0xe9fa28 in 01.11) - one byte.

      REASON it exists: it is the matchmaking key. A searcher asks for exactly
      one playlist in 0x135, and the elected host stamps that same id on the
      room it creates, so the server can advertise a room only to searchers
      wanting that playlist.

      01.11 TABLE - all nine live-confirmed 2026-08-19, each verified on BOTH
      sides (the searcher's 0x135 and the host's 0x12f stamp):

        playlist  mode           style
           1      Supply Raid    Parties Allowed
           2      Supply Raid    No Parties
           3      Supply Raid    DLC
           6      Survivors      Parties Allowed
           7      Survivors      No Parties
           8      Survivors      DLC
          11      Interrogation  Parties Allowed
          12      Interrogation  No Parties
          13      Interrogation  DLC

      Each mode owns a FIVE-slot block starting at 1, 6, 11 and uses the first
      three; 4/5, 9/10 and 14/15 are unused capacity, not missing content. Id 0
      has never been observed and reads as a none/invalid sentinel.

      01.00 had only TWO playlists, 2 and 3 - one per mode, because that build
      shipped no style variants. So id 3 means Survivors on 01.00 but Supply
      Raid/DLC on 01.11. IDS ARE NOT COMPARABLE ACROSS BUILDS, which is why
      matchmaking must be segregated by build as well as by playlist
      (server/session_manager.py CLIENT_BUILDS).

      NON-MATCHMAKING LOBBIES use their own ids in the same one-byte space:
        0x58 (88)  party room (observed on the party object, 2/2)
        0x5a (90)  seen once on the game object at client start-up
        0x63 (99)  PRIVATE match - the SAME value for Supply Raid (00:55:23)
                   and Survivors (01:01:29), so it is not mode-specific
      A server must never advertise these in the find-match list.

      RULED OUT, each by live evidence:
        NOT the team - one value (0x13) occurs with team 0, 1 AND 2, the
          complete team domain.
        NOT the map - a party lobby has no map, yet carries a value; and the
          map has its own field (member_data.recent_level, where Checkpoint on
          01.11 is 0x1f).
        NOT simply "the mode" - one mode spans three ids, one per style.

      HISTORY: this field was documented as a map id, then as a map-or-team
      combined index, then as a mode, and was retracted twice on 2026-08-18
      before the 01.11 style walkthrough made the playlist structure visible.
      The earlier readings were each consistent with the data available at the
      time - 01.00 has one playlist per mode, so "mode" and "playlist" are
      indistinguishable on that build alone.
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
  - id: pad_1e
    size: 2
    doc: "Offset 30:32. NEVER WRITTEN - uninitialised stack. server/session_manager.py reads max_players from here; that is a bug (see doc, correction 3). Live values `00 0a` and `00 00`."
  - id: value_20
    type: u2
    doc: "Offset 32:34. A float converted to int via fctiwz. Live-constant 1000 (0x03e8)."
  - id: value_22
    type: u2
    doc: "Offset 34:36. Second float converted to int. Live-constant 1000 (0x03e8)."
  - id: max_players
    type: u2
    doc: "Offset 36:38. Max players / room capacity. `sth r23,180(r1)`, and the SAME r23 is written to `room_obj+0x1f8` at 0x00ad5f80 - the field `_opd_FUN_00ad33d8`'s `if (room_obj+0x1f8 == 0) trap` assert reads and the field Member's (0x131) offset 24 overwrites. Live-constant 8 across every capture. This is the field a server should echo into Member's capacity slot."
  - id: member_data_length
    type: u1
    doc: |
      Offset 38:39 (wire 0x26). CORRECTED 2026-08-17: the LENGTH of the local
      player's 32-byte member_data card carried at wire 0xa8 (see member_data
      inside room_tail_block below), sourced from `*(u8*)(room_obj + 0x19f8)`
      (`stb r11,182(r1)`). Live 0x20 (=32), the exact length the card UI getter
      (_opd_FUN_00ad2650) demands. server/session_manager.py HARVESTS the
      32 bytes at wire 0xa8 keyed by this length and replays them into its
      0x131 Member roster + 0x13b so the host's lobby shows the joiner's card -
      the matchmade lobby never sends a 0x13a request, so this (and 0x130's
      equivalent) is the ONLY card supplier on the find-match path. See
      research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md.
  - id: flag_27
    type: u1
    doc: "Offset 39:40. 0 normally, 4 on one conditional branch (`stb r0,183(r1)` @ 0x00ad5cbc). Live values 0x00 and 0x04."
  - id: room_name
    size: 128
    doc: "Offset 40:168. NUL-terminated room name, produced by `_opd_FUN_00e45b10(r1+184, room_obj+0x18)` @ 0x00ad5f74 - i.e. a plain strcpy of `room_obj+0x18`. Format is `<npid>.<unix-timestamp>` (e.g. `comradesean.1786863559`), built by the 0x143 sender's own sprintf-like call. room_obj+0x18 is the SAME 128-byte region 0x143 sends and 0x144 strcpy's into on receipt - see protos/0x143_set_room_data_block.ksy."
  - id: member_data
    type: member_data
    doc: |
      Offset 168:200 (wire 0xa8:0xc8). The local player's lobby card - the
      FIRST 32 bytes of the `room_obj+0x19fc..` copy loop (0x00ad5d30-
      0x00ad5f2c into r1+312). Each field is decoded in
      common/member_data.ksy. Its length is member_data_length above (0x20).
      The stub harvests chunk[0xa8:0xc8] on every RoomCreate and reuses it as
      this member's card. (The old "team-selection u16 at wire 0xb0" finding
      is now member_data.team at offset 9 of this record - the u16 read cleanly
      as 0/1/2 because offset 8, member_data.capability_flag, was 0 in every
      capture; see the member_data.ksy 2026-08-18 boundary revision.)
  - id: room_settings_tail
    size: 32
    doc: |
      Offset 200:232 (wire 0xc8:0xe8). RESOLVED 2026-08-19: this is NOT a
      room-object field copy at all - it is uninitialised sender-side stack,
      the same class of residue as this project's many `pad_N` fields
      elsewhere. Confirmed by exhaustively disassembling the sender
      (`FUN_00ad5b78`, opcode literal `li r0,303` @0xad5c38, send call
      `_opd_FUN_00acb93c(this+0x25060, buf, 0xe8, 1)` @0xad5fac, buffer base
      r1+144): the stack range corresponding to wire 0xc8:0xe8 (r1+344
      through r1+376) has ZERO stores anywhere in the function - no `stb`/
      `stw`/`std` targets that range, and no `bl` to a copy/memset helper
      touches it either. The function's own frame (`stdu r1,-480(r1)`) is
      never zero-filled. So the "mostly zero with occasional stale-stack
      values" behaviour already observed live is exactly what leaked,
      never-written stack looks like - not a room field that happens to be
      usually zero. The earlier "room_obj+0x19fc..+0x1a3b copy" framing was
      never verified against this function's actual disassembly and is
      retracted. Send 0. (This closes the same class of question
      `room_object_tail` in 0x130_room_join.ksy has - see that file for the
      contrasting case where the copy IS real.)
