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

  Implemented in tools/session_manager_stub.py (build_room_search): the stub
  replies to every 0x135 with the current public-game list. LIVE STATUS: the
  search->list->pick->CONNECT_TO_HOST chain works and the joiner reaches
  NET_SM_CLIENT_RESERVE with the host NpId fix; the remaining blocker is the
  two-client host/joiner coordination (both clients self-elect host), NOT this
  message's format. See the handoff note.

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
        doc: "Offset 0:8. The join key. The client feeds this into its subsequent flow; the stub advertises the host room's id here. (Note the game-room id collides on 0x01383bd8-derived values across clients - see the handoff's open items.)"
      - id: unknown_a
        size: 4
        doc: "Offset 8:12. Unconfirmed; stub sends 0."
      - id: cur_players
        type: u2
        doc: "Offset 0xc:0xe. Current player count (stub sends the roster size). Semantics inferred, not confirmed."
      - id: unknown_b
        type: u2
        doc: "Offset 0xe:0x10. Unconfirmed; stub sends 0."
      - id: max_players
        type: u2
        doc: "Offset 0x10:0x12. Capacity (stub sends 8). Semantics inferred."
      - id: unknown_c
        size: 2
        doc: "Offset 0x12:0x14. Unconfirmed; stub sends 0."
      - id: host_npid
        size: 16
        doc: |
          Offset 0x14:0x24. The HOST'S NpId. CONFIRMED load-bearing 2026-08-17:
          the joiner's CONNECT_TO_HOST handler (_opd_FUN_003b2a9c) copies this
          entry's attribute block and starts a P2P SIGNALING connect to the
          host peer BY NPID (there is no 0x130 to the server at this step).
          With this zeroed the joiner resolved no peer and CONNECT_TO_HOST
          timed out ~30s -> force-leave. Filling it advanced the joiner to
          NET_SM_CLIENT_RESERVE. (Exact sub-offset of the NpId within the
          0x14:0x38 block is the best current guess; verify live.)
      - id: attr_tail
        size: 20
        doc: "Offset 0x24:0x38. Remainder of the 36-byte attribute block (map/mode/etc.) - not field-mapped; stub sends zero."
