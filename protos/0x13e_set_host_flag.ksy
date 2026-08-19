meta:
  id: set_host_flag
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingSetHostFlag - client -> server, over the Session Manager
  connection (port 7314). Not one of the 11 opcodes the client's own
  receive-dispatch has a case for (client-to-server only). Pairs with
  0x13f/HostFlagUpdated, the server's confirmation of the same flag change.

  RENAMED from `set_attr_flags` to match the disassembly-verified opcode
  map's confirmed field shape: a single flag byte plus a "kind" byte that
  discriminates the two sender paths (3 or 4), not a generic attribute-flags
  word.

  STATUS: confirmed 16 bytes. Two distinct sender call sites build and send
  this shape (builders at 0x00ad6b58 and 0x00ad7120), differing in how the
  flag byte at offset 4 is derived from their respective boolean inputs -
  one is gated on the room's own +0x19f4 "is host" flag (toggling it
  locally either way), the other computes it via a small bitwise
  negate-and-shift sequence. Both are plausible "request to become/cease
  being room host" call sites; which UI/game-logic path triggers each was
  not traced this pass.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x13e (318 decimal), passed through _opd_FUN_00a0e324 before send - a confirmed no-op (research/notes/2026-08-15-byteswap-helper-is-a-noop.md), so this stays plain big-endian."
  - id: flag
    type: u1
    doc: |
      Offset 4:5. Boolean WHEN WRITTEN (0 or 1), derived differently by each of
      the two confirmed sender call sites - see doc for both. Written into the
      matched room's +0x19f4 'is host' flag by 0x13f's handler on the round trip.
      LIVE CAVEAT (117 frames, 2026-08-18): on the wire this byte takes 0, 1, 3
      AND 4, and in the two most common shapes it EQUALS the frame's own kind
      byte (0x0404, 0x0303) - the signature of a stale byte left by the previous
      0x13e build in the same buffer slot rather than a freshly written boolean.
      Observed (flag, kind) pairs: (4,4) x40, (0,3) x35, (3,3) x35, (0,4) x4,
      (1,3) x2, (3,4) x1. A reader must treat only 0 and 1 as meaningful and
      ignore values >1 as residue. See
      research/notes/2026-08-18-wire-residue-and-field-corrections.md §3.
  - id: kind
    type: u1
    doc: |
      Offset 5:6. A sender-path discriminator, 3 or 4 depending on which
      builder sent it - NOT a fixed constant. CORRECTED 2026-08-18 (objdump):
      builder FUN_00ad6a34 stores 3 (`li r0,3` @ 0xad6b64, `stb r0,117(r1)` @
      0xad6b6c), builder FUN_00ad7024 stores 4 (`li r0,4` @ 0xad7130,
      `stb r0,117(r1)` @ 0xad713c); buffer base r1+112 so wire 5.
      LIVE-CONFIRMED 2026-08-18: 3 or 4 in 117/117 captured frames, no other
      value.

      KIND=3'S CALLING CONTEXT, LIVE-TRACED 2026-08-19 (RPCS3 debugger,
      breakpoint at 0x00ad6a34, ~12 hits across an extended session with two
      independent clients, comradesean and mgnomad2). EVERY hit fired
      through the identical caller (a vtable+0x20 dispatch thunk at
      0x00ad1150-0xad11a8, confirmed by disassembly: `lwz r9,32(r9)` = offset
      0x20) - so this is genuinely one calling site, not several. The target
      object (`param_2`, this function's own `r4`) and the requested state
      (`param_3`, `r5`: 1=become host, 0=cease host) varied with context:
        - Connect-time bootstrap (both clients, independently): party object
          (`0x01387f58`), 1 then 0 - set then immediately clear.
        - Party join / voluntary leave / getting kicked / a failed kick
          retried and then succeeding: party object, 0 (cease) on whichever
          side's own membership just changed - never on the side acting on
          someone else (the kicker never fires; the kicked client does).
        - Starting a private match: party object, 0 (cease) - the handoff
          away from party-level host status.
        - Clicking Find Match: party object, 1 (become) - re-claiming solo
          party host at the start of a fresh matchmaking search.
        - THE HOST'S LOBBY BEING CREATED (end of a find-match search that
          elected this client as host): GAME ROOM object (`0x01383bd8`,
          the same well-known static game-room pointer used throughout this
          project's find-match research), 1 (become host) - the FIRST
          confirmed hit on the game-room object, not the party object.
      CORRECTION: an earlier pass of this note claimed kind=3 was
      "exclusively" the party object's host-flag toggle and never touched
      the game-room object. The lobby-creation hit above disproves that
      directly. The corrected reading: kind=3 (`FUN_00ad6a34`) is a GENERIC
      is-host-flag setter that operates on WHATEVER object (`+0x19f4`) is
      passed to it - party or game room - fired by the client itself
      whenever ITS OWN local host status on that specific object needs to
      change. "kind" is not "which object type"; every observed trigger is
      still consistent with "a direct, locally-initiated host-flag change,"
      which may be the real axis kind=3 vs kind=4 splits on - kind=4's
      builder (`FUN_00ad7024`) is confirmed by static disassembly to never
      touch `+0x19f4` at all (see its own doc above), so kind=4 is
      structurally NOT this same "I am claiming/releasing host" action.
      kind=4's calling context (vtable+0x34) has NOT been live-captured in
      any session so far, despite covering party bootstrap, join, leave,
      kick (both directions, both outcomes), private-match creation,
      find-match search, and host lobby creation - genuinely still open,
      and the search for it should now look OUTSIDE "local client claims or
      releases its own host flag," since that whole category is kind=3's.

      KIND=4 LIVE-CAPTURED 2026-08-19 (same extended session, after the
      above was written): breakpoint at 0x00ad7024 finally hit, right as a
      map finished loading for the host of a private match. Confirmed
      correct vtable slot by disassembling the caller at `LR=0x00ad13a0`
      (thunk at 0x00ad1368-0xad13b4): `lwz r9,52(r9)` = offset 0x34,
      matching kind=4's vtable+0x34 exactly. `param_2 (r4) = 0x01383bd8`,
      the GAME ROOM object (same one kind=3 used for its own lobby-creation
      hit) - `param_3 (r5) = 1`. Immediately following this single kind=4
      hit, in the same map-load sequence, kind=3 fired twice more: once on
      the party object and once again on the game-room object, both
      `param_3=1`. So the observed order for a host's map load is: kind=4
      once (game room) -> kind=3 (party) -> kind=3 (game room again).
      Because kind=4's builder is confirmed to never touch `+0x19f4` (see
      above), this `param_3=1` is NOT a "become host" action in the same
      behavioral sense as kind=3's - per the static decompile, `param_3`
      here only selects between two debug-log string indices
      (`puVar2+(-0x7fc0)` vs `puVar2+(-0x7fbc)`), with no other observable
      branch.

      A SECOND kind=4 hit, same session, closed the picture completely: at
      MATCH END (scoreboard visible, same 0x00ad7024/vtable+0x34 caller),
      `param_2 (r4) = 0x01383bd8` (the same game-room object) again, but
      `param_3 (r5) = 0` this time - and the surrounding float registers
      (f2=85, f5=5, f6=100, f8=85, f9=20) are the SAME plainly stat-shaped
      values already live-confirmed for `0x140`'s `selector=0` hit earlier
      this session (see protos/0x140_set_room_flags.ksy) - i.e. this is the
      identical `NET_SM_RESULTS`/match-end moment, corroborated across two
      independent opcodes in the same live session. Immediately after this
      second kind=4 hit, kind=3 fired again too - on the PARTY object,
      `param_3=1` (become host) - matching the established pattern of
      reclaiming solo party-host status once a match concludes (this was
      then reconfirmed a third time, live, when the game entered the lobby
      after the deconstructed match: kind=3, party object, `param_3=1`).
      READING, NOW COMPLETE: kind=4 (`FUN_00ad7024`) is a clean SET-THEN-
      CLEAR pair tied to the GAME ROOM's own active-match lifecycle -
      `param_3=1` when a match starts (map load complete), `param_3=0` when
      it ends (results/scoreboard) - the room-level counterpart to kind=3's
      broader, more frequently-firing host-flag claim/release. Because
      kind=4's builder never touches `+0x19f4` (confirmed by static
      disassembly), this pair is NOT a host-flag toggle in the same
      behavioral sense as kind=3 - functionally it only selects between two
      debug-log string indices per the decompile - but its TRIGGER
      CONDITIONS are now fully named and, like kind=3, appear to be
      LOCALLY-INITIATED notifications of the client's own match-lifecycle
      state (active/not-active on the room), mirroring kind=3's own
      lobby/results split for the party object. Both kind=3 and kind=4 are
      now closed to the same standard: trigger conditions solidly
      established via live debugging and cross-opcode corroboration. The
      SERVER-SIDE consequence of either, like `0x140`, remains permanently
      unrecoverable from the client alone (see docs/OPEN-QUESTIONS.md's PS4
      capture plan).
  - id: pad_6
    size: 2
    doc: "Offset 6:8. ALIGNMENT PADDING (proven 2026-08-18): both builders (FUN_00ad6a34, FUN_00ad7024) store only wire+0 (opcode), wire+4 (flag byte) and wire+5 (kind); neither writes wire+6, and the 16-byte send leaves it as uninitialised stack. Definition: 2-byte gap aligning the 8-byte room_id after the kind byte. Not a field - send 0. (Was `unknown_2`.)"
  - id: room_id
    type: u8
    doc: "Offset 8:16. Raw (unswapped) copy of the room object's own +0x10 room-id field, matching the room_id-echo pattern used throughout this opcode family."
