meta:
  id: room_search
  endian: be
  license: CC0-1.0
doc: |
  Direction: SERVER -> CLIENT (the find-match game list). CLARIFIED 2026-08-17
  (research/notes/2026-08-17-find-match-flow.md): this is what
  NET_SM_CLIENT_GAME_LIST_WAIT is blocked on. The find-match client sends its
  0x135 search broadcast, then its GAME_LIST_WAIT handler (FUN_003b4bf4) polls
  for 0x136 to arrive; the ONLY writer of the "list ready" flag / count / entry
  array (search_obj +0xa4 / +0x200 / +0x208) is this 0x136 receive case in
  FUN_00ad7604. So the SERVER must PUSH 0x136 in reply to 0x135 - the client
  never sends a 0x136 request. An empty list (num_entries=0) lets a lone
  searcher fall through to hosting a public game itself; a non-empty list lets
  the client pick an entry (NET_SM_CLIENT_GAME_LIST_PICK) and then P2P-connect
  to that entry's host (NET_SM_CLIENT_CONNECT_TO_HOST, via the host NpId in the
  entry - see below), NOT via a 0x130 to us.

  Implemented in server/session_manager.py (build_room_search). LIVE STATUS
  2026-08-17: the FULL loop works end-to-end - the stub's serialized election
  (see protos/0x135_find_match.ksy) replies with an EMPTY list to the elected
  host through its whole search burst, PARKS the other searcher (sends no
  0x136 at all) until the host's 0x12f RoomCreate lands, then releases it with
  a 1-entry list whose host_npid points at the elected host. The joiner picks,
  P2P-connects, reserves, and sends a real 0x130; the host counts it and holds
  its lobby. This produced the project's first counted, credited matchmade
  game. The former "both clients self-elect host" blocker is SOLVED by the
  election - do NOT reintroduce the roster-push band-aid. See
  research/notes/2026-08-17-find-match-coordination-root-cause.md.

  STATUS: declared size in the Init() size table is a fixed 36 bytes - CONFIRMED
  WRONG. Real minimum size is `num_entries * 0x38 + 0x10` (16-byte header +
  num_entries x 56-byte entries), variable length.

  Offset 8 is the SEARCH-OBJECT POINTER the requesting client supplied in its
  own 0x135 (wire offset 8, live-constant 0x01383bd8 = the game-room global);
  the 0x136 handler dereferences and writes through it, so the reply MUST echo
  that value back. This resolves the earlier "raw pointer, doesn't fit the
  room_id-echo pattern" open question - it is a pointer, echoed from the 0x135.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x136 (310 decimal). Passed through a dedicated per-opcode field-touching helper (_opd_FUN_00ad5730) - decompiled 2026-08-15 and confirmed to be composed entirely of calls to the no-op FUN_00a0e324, so this stays plain big-endian; see research/notes/2026-08-15-byteswap-helper-is-a-noop.md."
  - id: pad4
    type: u4
    doc: "Offset 4:8. Zero (the stub sends 0)."
  - id: search_obj_ptr
    type: u4
    doc: "Offset 8:12. MUST echo the requesting client's own search-object pointer from its 0x135 (wire offset 8; live 0x01383bd8). The handler dereferences and writes the list through it."
  - id: num_entries
    type: u4
    doc: "Offset 12:16. Number of 56-byte entries following. Confirmed structurally: this dispatch case's minimum-size check is literally `num_entries * 0x38 + 0x10`. 0 = empty list (16 bytes total; the client then self-hosts)."
  - id: entries
    type: room_search_entry
    repeat: expr
    repeat-expr: num_entries
    doc: "Offset 16 onward, 0x38 (56) bytes each - one per joinable public game."
types:
  room_search_entry:
    doc: |
      56-byte game-list entry. Partially field-mapped 2026-08-17. Only room_id
      and the host identity are load-bearing so far; the rest of the 36-byte
      attribute block (map/mode) is unconfirmed and the stub sends it zero.
    seq:
      - id: room_id
        size: 8
        doc: |
          Offset 0:8. The join key. RESOLVED 2026-08-17: both clients send the
          SAME client-local pointer (0x01383bd8) as their room "id" on
          RoomCreate/Join, so the stub must NOT key its registry on the raw
          value. It mints a unique server-side id per elected host (live form
          0x5000000N01383bd8) and advertises THAT here; a 0x130 carrying an
          unrecognised id still resolves via the per-connection election
          mapping. See the coordination root-cause note."
      - id: unused_8
        size: 4
        doc: "Offset 8:12. PROVEN unused (2026-08-18): the 0x136 deserializer (0x136 case of FUN_00ad7604) copies wire[0:8] then jumps straight to wire[0x14]; bytes 8..0xb are never loaded, and no object-entry slot exists for them. Definition: a gap in the entry struct the client does not read - send 0. (Was `unknown_a`.)"
      - id: cur_players
        type: u2
        doc: "Offset 0xc:0xe. Current player count in the room. CONFIRMED READ 2026-08-18: deserialized to entry+0x2c (`lhz r9,12(r8)` @0xad7eb8), then read by the game-list sort/score (converted to a float fill-ratio @0x3b6be4/0x3b6bf4) and shown as a browser column (@0x3bbb74). Stub sends roster size. (Count semantics inferred from its float-ratio use; the read is proven.)"
      - id: unused_e
        type: u2
        doc: "Offset 0xe:0x10. PROVEN unused: the deserializer's only halfword loads are wire[0xc] and wire[0x10]; 0xe/0xf are never loaded. Struct gap - send 0. (Was `unknown_b`.)"
      - id: max_players
        type: u2
        doc: "Offset 0x10:0x12. Room capacity. CONFIRMED READ: deserialized to entry+0x34 (`lhz r0,16(r8)` @0xad7ebc), read alongside cur_players for the browser's sort/fill-ratio and shown as the second population column (@0x3bbb84). Stub sends 8. (Capacity semantics inferred; read proven.)"
      - id: unused_12
        size: 2
        doc: "Offset 0x12:0x14. PROVEN unused: never loaded by the deserializer (byte copy starts at 0x14; halfword loads are only 0xc/0x10). Struct gap - send 0. (Was `unknown_c`.)"
      - id: host_npid
        size: 16
        doc: |
          Offset 0x14:0x24. The HOST'S NpId. CONFIRMED load-bearing 2026-08-17:
          the joiner's CONNECT_TO_HOST handler (_opd_FUN_003b2a9c) copies this
          entry's attribute block and starts a P2P SIGNALING connect to the
          host peer BY NPID (there is no 0x130 to the server at this step).
          With this zeroed the joiner resolved no peer and CONNECT_TO_HOST
          timed out ~30s -> force-leave. Filling it advanced the joiner to
          NET_SM_CLIENT_RESERVE, and (2026-08-17) all the way to a real 0x130
          join and a counted match. The NpId at exactly 0x14:0x24 is now
          live-confirmed load-bearing, not a guess.
      - id: attr_tail
        size: 20
        doc: "Offset 0x24:0x38. Remainder of the 36-byte attribute block (map/mode/etc.) - not field-mapped; stub sends zero."
