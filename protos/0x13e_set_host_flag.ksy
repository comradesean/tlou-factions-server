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
      Offset 4:5. NOT a plain boolean on the kind=3 path (builder
      `FUN_00ad6a34`) - CORRECTED 2026-08-20, reversing an earlier
      "unwritten stack residue" claim that was itself wrong (see below).
      `param_3` (`r29`, `mr r29,r5` @`0xad6a68` - the caller's request,
      1=become host / 0=cease host) reaches the wire through ONE of two
      real, deliberate stores, selected by the result of a vtable+0x18
      call (`bctrl` @`0xad6b8c`; result truncated to a byte and compared
      to 0 @`0xad6b94`-`0xad6b98`):

          ad6b9c  beq cr7,0xad6ba8      ; result == 0 -> ENCODED path
          ad6ba0  stb r29,116(r1)       ; result != 0 -> RAW path: 0 or 1
          ad6ba4  b   0xad6bc0
          ad6ba8  clrlwi r9,r29,24 / addi r9,r9,-1 / srawi r9,r9,31 /
                  not r9,r9 / clrlwi r9,r9,30
          ad6bbc  stb r9,116(r1)        ; ENCODED: 3 if param_3!=0, else 0

      So on the ENCODED path, "become host" (`param_3=1`) is sent as
      **3**, not 1 - `3` is a deliberate value meaning "claiming host",
      not leftover residue. Written into the matched room's +0x19f4 'is
      host' flag by 0x13f's handler on the round trip (that handler ANDs
      with 1, so a wire value of 3 arrives there as 1 - see
      `protos/0x13f_host_flag_updated.ksy`).

      Live observed (flag, kind) pairs (117 frames, 2026-08-18): (4,4) x40,
      (0,3) x35, (3,3) x35, (0,4) x4, (1,3) x2, (3,4) x1. On kind=3, `(3,3)
      x35` is the ENCODED path's "become" case, `(1,3) x2` is the RAW
      path's "become" case, and `(0,3) x35` is the "cease" case common to
      both (encode(0)=0, raw(0)=0) - not a case of stale/contaminated
      bytes, three genuinely different call outcomes on the same builder.

      RETRACTED (2026-08-20): `research/notes/2026-08-20-tier2-followup.md`
      §5 claimed this byte is "genuinely uninitialised stack" on kind=3 and
      that a reader "must... ignore values >1 as residue". Both claims are
      false - re-verified directly against `research/disasm/full.asm`
      `0xad6b90`-`0xad6bbc`, which shows the two real stores above. The
      EARLIER (2026-08-18) "stale byte from the previous build" hypothesis
      this note thought it was correcting was ALSO wrong, for the same
      reason: both non-boolean values (3 and, on kind=3 only, 1) are live
      writes, not left-over bytes.

      SELECTOR RESOLVED 2026-08-20 (static; see
      research/notes/2026-08-20-followup-open-items.md section 2). The object
      the vtable+0x18 call goes through is `*(u32*)0x01441198`
      (`lwz r9,-32748(r30)` @`0xad6b54` -> literal-pool slot `0x012975D4`,
      contents `0x01441194`; then `lwz r9,4(r9)` @`0xad6b68`). That is the
      SAME object `FUN_00ad5b78` reads `value_20`/`value_22` out of via
      `FUN_00acb6bc` (which is just
      `out1 = this->f32@+0x48; out2 = this->f32@+0x4C`), and its class is
      built by `FUN_003ac2e8`: base ctor `FUN_00acb6d0` installs the
      all-pure-virtual vtable `0x01243A18`, then `stw r9,0(r29)` @`0x3ac31c`
      overwrites it with the derived vtable **`0x01224178`**, and
      `+0x48`/`+0x4C` are zeroed at `0x3ac38c`/`0x3ac390` - the very floats
      `FUN_00acb6bc` reads back, which cross-checks the identification.

      `0x01224178 + 0x18` is `FUN_003abe4c`, a nine-instruction pure getter:

          3abe4c  lwz   r0,856(r3)   ; *(u32*)(this + 0x358)
          3abe50  xori  r0,r0,2
          3abe54  srawi r9,r0,31
          3abe58  xor   r3,r9,r0
          3abe5c  subf  r3,r9,r3     ; abs(x ^ 2)
          3abe60  addi  r3,r3,-1
          3abe64  srwi  r3,r3,31     ; -> 1 iff x == 2
          3abe6c  blr

      So the encoding is chosen by a single equality:

          netsession->field_0x358 == 2  ->  RAW      (param_3 verbatim, 0/1)
          netsession->field_0x358 != 2  ->  ENCODED  (param_3 ? 3 : 0)

      That accounts for the live distribution above: `(3,3) x35` and
      `(0,3) x35` are the ENCODED path and `(1,3) x2` the RAW path - RAW is
      rare because `field_0x358 == 2` is a rare state.

      WHAT `field_0x358` IS - partially pinned. It is a small enum, only ever
      assigned the literals 0, 1 and 2 on instances of this class (restricting
      a literal-pool-tracked scan to the static instance `0x013835C0`): `0` at
      `0x3ac368` (construction), `0x35ef90`, `0x33c37c`; `1` at `0x3b5908`,
      `0x3b5b04`, `0x3bf3f4`; `2` at `0x35bf88`, `0x35d5c0`, `0x35f174`. The
      clearest writer is `FUN_0035D59C`, the small function immediately after
      `FUN_0035D1FC` (the state that logs `"Host"` and issues the
      `0x12f RoomCreate` - see protos/0x12f_room_create.ksy's caller note): it
      sets the field to 2 and broadcasts the same value as net-event 272
      (`li r3,272`, `bl 0x3c9d20` @`0x35d5dc`). Readers agree it is a
      role/mode selector rather than a counter: `0x0039F314` and `0x0039F398`
      take their "a game-mode descriptor applies" branch only when it equals
      1; `0x003A41D0` SKIPS the `*net-games*` lookup when it equals 2;
      `0x003C05B4` uses it directly as an index into a 12-byte-stride runtime
      table, bounding the enum to a handful of values.

      READING: `field_0x358` is a three-valued net-session role/mode, `2` is
      the value the `"Host"` state installs, and kind=3 uses the raw 0/1
      encoding in that state and the 3-or-0 encoding otherwise. Not a problem
      for a server either way: `0x13f`'s handler ANDs the byte with 1, so
      both encodings arrive as the same boolean.

      VALUE `1`, LIVE-CONFIRMED 2026-08-20 (breakpoint at the writer
      `0x3b5908`, two independent hits, both accounts). Both landed in the
      same broad phase: on one account during the post-match results
      screen's survivor-count update, on the other slightly later in the
      same flow, after picking a new mission from the post-match menu.
      Matches the reader corroboration above (`0x0039F314`/`0x0039F398`'s
      "game-mode descriptor" branch) exactly - resolving what mission comes
      next needs a mode descriptor. Reading: **`field_0x358 == 1` marks the
      post-match results/mode-resolution phase**, the stretch between a
      match ending and a new mode descriptor being resolved for whatever
      comes next. Whether this is specifically "post-match" or more broadly
      "any pending mode-descriptor resolution" (e.g. also fresh matchmaking
      entry from the main menu) is not distinguished by these two hits alone,
      but the phase-level reading is solid.

      VALUE `0`, LIVE-CONFIRMED 2026-08-20 (breakpoint at the writer
      `0x35ef90`). Hit at the moment of confirming "Leave Matchmaking".
      Matches the inference exactly: **`field_0x358 == 0` is the idle/
      no-active-role state**, entered on leaving/cancelling matchmaking -
      the same value construction (`0x3ac368`) sets, now confirmed as a
      real reset transition.

      ALL THREE VALUES NOW HAVE A LIVE CORRELATION:
      `0` idle (Leave Matchmaking); `1` post-match results/mode-resolution
      phase (survivor-count update, post-match mission selection); `2`
      "Host" (party-creation state). Reading kind=3's RAW-vs-ENCODED
      selector in this light: RAW (plain 0/1) is reserved for the one state
      where becoming/ceasing host is the actual operation (`2`), and ENCODED
      (3-or-0) is the general-purpose form used in both other states.

      See `research/notes/2026-08-20-followup-open-items.md` section 2 for
      the full trace.
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
