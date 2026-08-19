meta:
  id: set_room_flags
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetAttrFlags - sent by the client over the Session Manager
  connection (port 7314). Live-captured for the first time 2026-08-15,
  only reachable once a room survives long enough to actually load into a
  match (see research/notes/2026-08-15-room-teardown-and-flag-chain.md and
  the RPCS3 "Stub PPU Traps" workaround that finally got a client this
  far).

  STATUS: 16 bytes total, confirmed live. NOT one of the 11 opcodes the
  client's own receive-dispatch (FUN_00ad7604) has a case for (unlike its
  reply, UpdatedAttrFlags/0x141) - client-to-server only.

  DEFINITION / PURPOSE: "set one room attribute". The client tells the server
  which host-configurable lobby attribute changed, so the server can store it on
  the room and advertise it to searchers. 0x141 is the server's confirming echo.
  The only payload the wire actually carries is the attribute SELECTOR at 4:6;
  offset 6:8 is leaked stack, not a value (see below).

  WIRE STRUCTURE (sender `_opd_FUN_00ad62dc`, vtable +0x2c; send buffer base
  r1+112):
      ad636c:  stw  r0,112(r1)     ; offset 0 = 0x140
      ad6374:  sth  r28,116(r1)    ; offset 4 = (u16) selector
      ad6370:  std  r9,120(r1)     ; offset 8 = room_obj+0x10  (8 bytes)
      ad63a8:  li   r5,16          ; 16 bytes sent
  The 0x141 handler reads back only offset 4:6 (`lhz r3,4(r29)` @ 0x00ad82ec)
  into room_obj+0x1f0 (which no consumer branch ever reads - so the client-side
  effect of the round trip is inert; the ACTION is the value delivered to the
  server at 6:8).

  OFFSET 6:8 IS SENDER-SIDE RESIDUE (settled 2026-08-18, second pass). An
  intermediate revision promoted 6:8 to a real client->server attribute value
  because its values recurred across captures taken on different days. That
  inference was wrong: a leaked POINTER reproduces exactly on a deterministic
  emulator, so cross-session reproducibility cannot distinguish a real field from
  leaked stack. See research/notes/2026-08-18-wire-residue-and-field-corrections.md
  for the statistical proof (99% of these gap words are valid PS3 addresses, and
  the client's own PPU dump gives the matching stack range 0xd0001000-0xd0040fff).

  The larger capture (355 frames) refutes the field reading directly:
    - ROOM-INDEPENDENT. The same five values appear against the static party room
      012723d8... and against ~25 distinct synthesized public room ids
      (50000001... through 50000030...). An attribute that is identical for every
      room ever created is not an attribute of the room.
    - CALL-SITE DETERMINED, not setting determined: `fbe0` follows a prior 0x140
      in 28/28 cases, `197c` follows a 0x13a in 4/4 cases, and the cycle
      ff50 -> fbe0 -> 2f78 repeats per lobby regardless of any host choice.
    - Only 5 distinct values across 355 frames: ff50 (x238), 2f78 (x74),
      fbe0 (x28), 197c (x4), 3954 (x1).
  The `sth` at 4:6 overwrites the HIGH half of whatever pointer occupied the
  slot, which is exactly why only a plausible low half is ever visible on the
  wire. The selector at 4:6 was 0x0001 in every 2026-08-18 capture (an earlier
  capture also saw 0x0000).

  Gating (unchanged, still confirmed): if `room_obj+0x10 == 0` the action
  only writes locally (`room_obj+0x1f0 = selector`, dirty flag
  `room_obj+0xe0 = 1`) and nothing reaches the wire at all.

  ATTR_SELECTOR'S TRIGGER CONDITIONS - RESOLVED AT THE WIRE LEVEL, 2026-08-19
  (its PURPOSE is still inferred, not confirmed - see the READING note below
  and docs/protocol/proto-map.md's tier-B row; the round-trip is proven
  inert client-side, so there is no client-visible consequence to point to,
  only the sender's own trigger conditions). Evidence (disasm +
  an extended live RPCS3 debugging session spanning a full private match AND
  a full find-match search). Live breakpoints at the sender itself
  (`0x00ad62dc`) fired repeatedly with `LR = 0x00ad1234` (the same generic
  thunk, `_opd_FUN_00ad11fc`, forwarding `(room_ptr, selector)` to this
  vtable+0x2c method) across every phase observed:
    - `r5 = 1` - room creation during level load, "Starting Game..." loadout
      render, load-timer completion, and again during find-match's
      "Searching for players..." state.
    - `r5 = 0` - mid-match (unlabeled), and explicitly at END OF MATCH, where
      the surrounding float registers held plainly stat-shaped values (85,
      100, 75, 67, 20 among them - accuracy/score/percentage-range numbers),
      corroborating the call-site analysis below.
    - `r5 = 8` - ONE additional value, seen live during "Searching for Close
      Game" (an earlier find-match sub-state, before a room/host is
      resolved).
  A CROSS-CHECK AGAINST THE ACTUAL WIRE (the full `server/logs/wire.jsonl`
  capture, not just call sites) resolves the apparent 3-value complication:
  every 0x140 frame that ever reached the wire carries ONLY 0 or 1 - 926
  frames at selector=1, 23 at selector=0, ZERO at selector=8 across the whole
  capture. The `r5=8` call is real but never reaches the network: it fires
  before the room object has a registered network id (the documented gating
  rule below - `room_obj+0x10 == 0` - applies, since "Searching for Close
  Game" precedes room creation/join). So the SENDER FUNCTION is used more
  broadly by the client than the wire protocol ever needs to represent; the
  earlier claim in this doc that the disassembly corpus search "found only
  TWO literal values ever passed" was based on an incomplete scan and is
  corrected here - a third value exists client-side, it just never leaves
  the console.
  A full-corpus search of `_opd_FUN_00ad11fc(...)` call sites in the
  decompiled disassembly (deduplicated by address - several
  `research/ghidra/*.txt` files are independent re-decompiles of the same
  underlying functions) found the wire-relevant pair:
    - selector=1: `FUN_0035a7dc` (research/ghidra/fm_alt_decomp.txt) - the
      FIRST thing this function does, followed immediately by heavy setup
      (`_opd_FUN_0040ee24(0)` then `(1)`, a conditional loop over what reads
      as a player/item list). NAMED by pre-existing, independent project
      research (research/notes/2026-08-17-member-blob-vanity-semantics.md
      §9d, written 2026-08-17 - BEFORE today's live session, so this is a
      cross-check, not a rationalization built to fit): `FUN_0035a7dc` is
      "the lobby / party-screen member-list model rebuild", reached from
      `FUN_0035cde0` under UI state `0x11` - it loops every roster member,
      recreates their entry, and resets each one's character-preview to a
      random pool pending a later resolved override. This matches every live
      trigger observed today (room creation, loadout render, load-timer
      completion, and while actively searching for players) - all moments
      where the lobby/roster UI model plausibly needs rebuilding.
    - selector=0: `FUN_003f208c` (research/ghidra/lb_trigger.txt - the
      working filename itself is a strong hint, and the live end-of-match
      float registers now directly corroborate it) - heavy float/vector math
      consistent with score/stat computation, gated behind a "has this
      already fired" flag check (`*(char*)(iVar34+0x1a4d) == '\0'` and two
      other conditions), i.e. a fire-once completion handler. NAMED by
      pre-existing, independent project research
      (research/notes/2026-08-17-match-counts-latch.md §1.4, also written
      2026-08-17): this exact function is the client's `NET_SM_RESULTS`
      handler - it reads the "counted game" latch and, when armed, runs the
      matches/wins/supplies/`OnMatchEnd` crediting body. Directly matches
      today's live hit, which fired with plainly stat-shaped register values
      (85, 100, 75, 67, 20) present at the same breakpoint.
    - A THIRD, independent function (research/ghidra/fm_handlers.txt, near
      `_opd_FUN_00358924` event-id checks 0x25/0x26) contains a direct
      if/else choosing selector=1 on one boolean flag branch
      (`param_1[0x30] != 0`, the "success" path storing `1` into a result
      slot) and selector=0 on the other (the "not success" path) - the same
      binary meaning, from a third, structurally different call site.
  READING - the CLIENT-SIDE PURPOSE is now well-evidenced, not just the
  trigger pattern: `attr_selector` is NOT a "which of several room
  attributes changed" selector despite the field's inherited name. It is the
  client announcing, to the session-manager server, which of two named
  client-side phases it has just entered - 1 = the lobby/roster model is
  being (re)built (`FUN_0035a7dc`, UI state `0x11`), 0 = the match has ended
  and results/stats are being processed (`FUN_003f208c`, the `NET_SM_RESULTS`
  handler). Both identities come from project research written independently
  of and BEFORE today's live session, so this is convergent evidence, not a
  single investigation reasoning in a circle. What remains genuinely
  unconfirmed is the SERVER-SIDE consequence: no client branch anywhere
  reads the `0x141` echo back into any decision (see pad/gating notes
  above), so there is no client-visible effect for either value, and there
  is no retail server left to observe what Naughty Dog's own backend did
  with a lobby-rebuild vs results notification. The generic "attribute
  selector" framing comes from this message's OPCODE/API shape
  (`SetAttrFlags`, a general-purpose room-property setter used by several
  unrelated client-side flags, including the gated-out selector=8 case
  above), not from anything actually selected on THIS project's wire.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x140 (320 decimal). Confirmed live, big-endian."
  - id: attr_selector
    type: u2
    doc: "Offset 4:6. `sth r28,116(r1)` @ 0x00ad6374 - low 16 bits of the sender's 3rd argument. The only half the client reads back (from the 0x141 echo, into room_obj+0x1f0, which is then never branched on) - so this value has NO confirmed client-visible effect either way. RESOLVED 2026-08-19 to a binary CLIENT-PHASE ANNOUNCEMENT, not a selector choosing among several distinct room attributes despite the inherited name (see the message-level doc above for the full live session and the independent, pre-existing project research that names both call sites): 1 = the client's lobby/roster model is being (re)built (`FUN_0035a7dc`, UI state 0x11) - fires at room creation, loadout render, load-timer completion, and while actively searching for players. 0 = the client has reached its `NET_SM_RESULTS` state and is processing match-end stats (`FUN_003f208c`) - live-confirmed with stat-shaped register values (85, 100, 75, 67, 20) present at the same breakpoint hit. Exhaustively 0x0000 or 0x0001 across the whole wire.jsonl capture (926:23). A third client-side value (8) exists in the sender function but is gated out before reaching the wire (fires during find-match's pre-room-resolution \"Searching for Close Game\" state, when room_obj+0x10 is still 0) - see the gating note above. The SERVER-SIDE consequence of either value remains unconfirmed - no client branch reads it back, and no retail server is left to observe."
  - id: pad_6
    type: u2
    doc: "Offset 6:8. NOT A FIELD - sender-side residue. DEFINITION: the low half of a stale pointer left in the reused send buffer at r1+118; the builder's only stores are wire 0 (`stw`), wire 4:6 (`sth` selector) and wire 8:16 (`std` room_id), and the selector's `sth` clobbers the pointer's high half, leaving its low half on the wire. REASON: unwritten gap between the 2-byte selector and the 8-byte-aligned room_id. Live: 5 distinct values in 355 frames (ff50/2f78/fbe0/197c/3954), identical across ~25 different rooms, and call-site-determined (fbe0 follows a prior 0x140 28/28). Send 0. (Was `attr_value`; see research/notes/2026-08-18-wire-residue-and-field-corrections.md §2.)"
  - id: room_id
    size: 8
    doc: "Offset 8:16. Matches the room_id this server assigned via Member's header - echoed back verbatim in the stub's UpdatedAttrFlags reply."
