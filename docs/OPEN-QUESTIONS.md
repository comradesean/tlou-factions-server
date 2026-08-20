# Open questions

Things that are known-unknown rather than undiscovered. Each entry says what is
blocking it and what would unblock it, so none of them silently become "we never
looked".

## Blocked on data-compiler (.pak / netN.bin) payload

Not recoverable from the EBOOT by any amount of static analysis - the values
live in the data-compiler payload the game loads at runtime.

- **`pReportArray` entry names.** Tracked in code as
  `TODO(pReportArray)` in `server/ticket_server.py`, in the block comment above
  `build_report_response`. The ban check (`report-server`, `is-banned`) reports
  an account as banned iff the reply's second token `strcmp`-matches an entry
  name in this table. The table's SHAPE is high confidence (12-byte entries,
  `[+4]` message StringId, `[+8]` `const char*` name, resolved by DC symbol hash
  `0xFFAC56F2`); the literal strings are not.
  NOTHING NEEDS DOING unless this project ever wants to deliberately ban an
  account. Our reply is an EMPTY body, so `buf[0]` is `0x00`, the parser's `'+'`
  test fails, and the ban index at `g_net+916` keeps the `-1` it was initialised
  to - the check is FAIL-OPEN at every branch, so an unknown table cannot
  produce a false ban. The names would only ever be needed to CONSTRUCT a reply
  that bans somebody.
  VERIFIED 2026-08-19 against the 01.11 ELF instruction by instruction, rather
  than restated on trust: `0x36e1a0 li r0,-1` / `0x36e1a8 stw r0,916(r9)` is the
  `-1` default; `0x36e2c8 lbz r0,904(r1)` / `0x36e2cc cmpwi cr7,r0,43` /
  `0x36e2d0 bne cr7,0x36e388` is the `'+'` test and its skip; `0x36e298 cmpwi` /
  `0x36e29c ble cr7,0x36e388` skips on `n <= 0`; and `0x36e388` (the shared
  "done" label every non-ban path reaches) never touches `g_net+916`. Only the
  strcmp-match arm at `0x36e360`-`0x36e368` writes it. Also corrected there: the
  connect call is the `bl 0xaf9bb4` at `0x36e220`; `0x36e1fc` merely loads the
  `"report-server"` string pointer (slot `0x129a3c8`).
  UNBLOCK (if ever wanted): a DC/.psarc dump, or a runtime read of the resolved
  table.

- **The integer at `g_net+920`.** Tracked in code as `TODO(g_net+920)` beside
  the entry above. Parsed from the ban reply's first token (`strtol` at
  `0xe75d78`, result held in `r27`) and stored only on a name match at
  `0x36e364`, then formatted into the ban message shown to the player. Duration
  / expiry / days is a guess and is deliberately not recorded as fact. Its
  format-string pointer `0x1530d90` is bss, so it is only readable at runtime.
  NOTHING NEEDS DOING - it is reachable only on the banned path, which our empty
  reply never enters. Same disposition and same unblock as above.

- **DC net-stat slots, `rank_tier`'s `net-money-info` array contents, and
  every id->asset map** (cosmetics, character and name pools). Long-standing;
  see `docs/protocol/knowledge-inventory.md` Tier 3. `rank_tier`'s backing DC
  symbol was name-corrected 2026-08-19 - see `docs/protocol/dc_table.md`.

## Unmapped wire spans

- **`0x136` `attr_tail`.**
  WHAT IT IS: the trailing 20 bytes of each game-list entry's 36-byte attribute
  block. The block spans `0x14:0x38` of an entry; its first 16 bytes are the
  host's NpId (`host_npid`, live-confirmed load-bearing - zeroing it strands the
  joiner in `CONNECT_TO_HOST` until it times out). Bytes `0x24:0x38` are the
  remainder and no interior field of them has a confirmed offset, width or
  meaning.
  WHERE: `protos/0x136_room_search.ksy`, the `attr_tail` field of the per-entry
  type, immediately after `host_npid`. It is modelled as an opaque 20-byte span
  because that is genuinely all that is known - the field name and its `doc:`
  are deliberately non-committal, and the "map/mode/etc." reading that used to
  appear beside it was a guess from the block's role, not a decode.
  ESSENTIALLY CLOSED ON THE MECHANISM SIDE, 2026-08-19 - both copy sites
  traced at instruction granularity and then LIVE-CONFIRMED in RPCS3's
  debugger (01.00, breakpoint `0x003b2a9c`, read-back `0x003b2bd4`). The
  `0x136` deserializer copies attr_tail verbatim into the entry object (wire
  `0x24:0x38` -> entry_obj `0x18:0x2c`). `_opd_FUN_003b2a9c` (CONNECT_TO_HOST)
  then copies the whole 36-byte attribute block, attr_tail included, into
  `g_70`/NetInfo at `0x013835c0` (01.00), offsets `0xb0:0xc4` - confirmed
  live: r30 resolved to the predicted anchor `0x1271b1c`, r11 resolved to
  `0x013835c0` exactly, and a memory read at that object's `0xb0:0xc4`
  showed the server's 20 zero bytes landed there untouched.

  IDENTITY RESOLVED 2026-08-19: this is not an anonymous struct - `g_70` is a
  singleton independently mapped across extensive prior project research
  (2026-08-17/18, written before this investigation): `2026-08-17-match-
  counts-latch.md`, `-member-data-blob-rank-and-0x142-hostrank.md`,
  `-min-players-client-patch.md`, `-mode-min-players.md`, `-session-
  handoff.md`, `-supplies-and-survivor-state.md`, `-userdata-txt-crypt-
  format.md`, `2026-08-18-session-manager-connect-and-reconnect.md`, and
  `2026-08-18-wire-residue-and-field-corrections.md` all independently
  resolve the identical address via the identical anchor/slot chain. Known
  sibling fields on the SAME object: `+0x6C` is the "counted game" crediting
  latch (nine setter sites, two of them inside the leaderboard get/update
  workers `FUN_003af46c`/`FUN_003afb74` - the same compilation unit as
  attr_tail's own writer); `+0x80` holds a CRC32-hashed userdata config
  value with its own "no active retail reader found" note - an exact
  structural parallel to attr_tail. A search of every prior `g_70`-related
  note for a bulk-copy/memcpy operation on the object (which would evade the
  offset-based scan below) found none - this narrows confidence without
  fully closing the residual gap.

  Then an EXHAUSTIVE static search closed the "is it read anywhere" question
  as far as static analysis can: the object is reached through exactly ONE
  addressing path in the entire binary (51 call sites, one compilation unit,
  `0x3b21e8`-`0x3b978c`, no other anchor or absolute-address construction
  reaches it). Of those 51 sites, only the CONNECT_TO_HOST writer above
  touches offsets `0xb0:0xc4` - nothing else in the retail 01.00 binary reads
  that span via a direct field access.
  WHY IT IS STILL "OPEN" AT ALL: this rules out direct offset reads only. A
  bulk copy of a wider span (the whole singleton, or `+0x98` onward) into a
  second buffer, read back elsewhere, would evade an offset-based scan - not
  found near the writer in this pass, not exhaustively ruled out across all
  51 sites either.
  CANARY TEST, RUN 2026-08-19: sent a distinctive non-zero attr_tail (byte
  run `0x10..0x23`) instead of zeros for one live join. Live memory read
  confirmed the pattern landed byte-for-byte at the singleton's `0xb0:0xc4`,
  and the joiner completed a normal join with it live on the wire - no
  browser glitch, no TTY anomaly, no stall, no crash, no difference from a
  zero-filled attr_tail. Expected given the exhaustive static result, and
  corroborates it without closing the residual bulk-copy-read possibility.
  Reverted immediately after; the server sends zero attr_tail again.
  WHY ZEROS ARE STILL SAFE: the server sends 20 zero bytes and the full loop
  still works end to end - browse, join, load, counted and credited match,
  and the live debugger read confirms those zeros (and, briefly, the canary)
  land exactly where traced.
  REMAINING UNBLOCK, if ever revisited: correlate against a live capture in
  which the host varies exactly ONE search/lobby option at a time (mode, map,
  playlist, privacy, NAT, party size) between otherwise identical rooms, so
  each byte that changes is attributable to one option - the only path left
  that could still name the interior fields, since no reader exists to trace
  backward from.

  IMPORTANT - IF PS4 ACCESS EVER HAPPENS: The Last of Us Remastered (PS4) has
  a real retail backend STILL RUNNING as of 2026-08-19 - not speculative,
  confirmed - which the PS3 original's long-dead ND servers can no longer
  provide. No PS4 hardware/access exists right now, so nothing further can
  be done on this item until that changes; recorded here so the plan isn't
  lost. If PS4 hardware/access is ever obtained, capture `0x136 RoomSearch`
  traffic (or Remastered's equivalent opcode, IF ONE EXISTS - the PS4
  build's session-manager protocol may not use the same opcode numbering as
  this repo's PS3 findings; do not assume opcode 0x136 or these exact byte
  offsets carry over without re-deriving them the way this project derived
  the PS3 ones). What to capture and why:
    - The FULL wire capture of the whole session-manager connection, not
      just the game-list reply - `attr_tail`'s producer/consumer chain spans
      multiple opcodes on the PS3 side, and the PS4 equivalent may too.
    - MULTIPLE game-list entries taken while DELIBERATELY varying exactly
      ONE lobby/search property at a time between captures (game mode, map,
      playlist, public/private, NAT type, party size, host DLC ownership) -
      this is the "vary one option at a time" method already on record above
      as the only way left to attribute specific byte changes to specific
      causes, since PS3-side static analysis found no in-client reader to
      trace backward from.
    - The PS3 EBOOT's structural findings likely transfer as a MAP, not as
      exact bytes: this repo's `attr_tail` sits at PS3 wire offset `0x24:0x38`
      of a 36-byte attribute block whose first 16 bytes are `host_npid`
      (protos/0x136_room_search.ksy). If Remastered kept a similar wire
      shape, look for an equivalent NpId-sized block and a same-length
      trailing span in the equivalent list-reply message; if the shape
      changed, the whole message needs re-deriving from scratch (Kaitai spec
      + Who/Why/Where, same method as every other proto in this repo).
    - Tools already in this repo that would carry over: `research/tools/
      eboot_analysis` (works on any ELF given updated `EBOOT` path/segment
      map in `eb.py`) for static tracing on the PS4 binary if it's ever
      decrypted/available, and `research/tools/catch_tcp.py` /
      `server/logs/wire.jsonl`-style capture logging for the live side.
    - Record findings the same way as the rest of this repo: a dated note in
      `research/notes/`, then fold the confirmed fields into a `.ksy` spec
      with Who/Why/Where evidence, not directly into this file.
    - ALSO CAPTURE (added 2026-08-19, from the `0x140`/`0x141` investigation):
      `SetAttrFlags`/`UpdatedAttrFlags` traffic (or its PS4 equivalent) across
      a full lobby-to-results cycle. The PS3 side already has the CLIENT'S
      half fully solved - `attr_selector` is a binary phase announcement (1 =
      lobby/roster model rebuild, 0 = `NET_SM_RESULTS`/match-end stat
      crediting; see `protos/0x140_set_room_flags.ksy` and this project's own
      prior research naming both call sites, `FUN_0035a7dc` and
      `FUN_003f208c`) - what's missing and UNRECOVERABLE from the PS3 client
      alone is the SERVER-SIDE consequence: what a real ND/Remastered backend
      DOES with a lobby-rebuild vs. results notification (matchmaking
      bookkeeping? stats/leaderboard timing? nothing at all?). A retail
      capture can't show this directly either (the server's internal logic
      still isn't observable from outside), but it CAN show whether the
      retail server's OWN reply behavior differs from what would be
      predicted from this repo's current stub (e.g. does retail reply
      immediately every time the way our stub does, or does it withhold/
      delay a reply under some condition, which would be an indirect clue to
      server-side gating this repo can't otherwise discover).
      Also applies to `0x13e SetHostFlag`/`0x13f HostFlagUpdated`
      (added 2026-08-19): trigger conditions for both `kind=3`
      (`FUN_00ad6a34` - a generic host-flag claim/release on either the
      party or game-room object) and `kind=4` (`FUN_00ad7024` - a
      set-then-clear pair tied to the game room's active-match lifecycle)
      are now fully named client-side (see `protos/0x13e_set_host_flag.ksy`)
      via the same kind of live RPCS3 debugging session as `0x140`. Same
      ceiling applies: what a real backend does with either notification is
      unrecoverable without a retail capture.

- **`0x12f room_settings_tail` / `0x130 room_object_tail`** - RESOLVED
  2026-08-19. `room_settings_tail` is not a room-object field at all: its
  sender (`FUN_00ad5b78`) was exhaustively disassembled and never writes
  that stack region, nor calls any copy/memset helper touching it - pure
  uninitialised residue. `room_object_tail` IS a real copy (`room_obj
  [0x20:0x40]`, confirmed via its sender `FUN_00ad6718`'s 64-byte copy
  loop), with `room_obj` live-confirmed as the party object (`0x01387f58`)
  during a real party join. An exhaustive whole-binary scan for any reader
  of that address range found none - same status as `attr_tail` and
  `member_slot_ec`. Untested: whether a game-room join uses a different
  `room_obj` than a party join does. See `protos/0x12f_room_create.ksy` and
  `protos/0x130_room_join.ksy`.

## Unhandled sibling services

Eight service names exist in the 01.11 EBOOT. Six have handlers; one is dead
code; one has never spoken.

`gamelist-server` was RESOLVED 2026-08-19 and is no longer open. The sender is
`FUN_004047f4` (01.11), reached from the string slots `0x129cd7c`
(`"game-add "`), `0x129cd8c` (`"gamelist-server"`) and `0x129cd70`
(`"games/%s"`). It does ONE bounded 256-byte recv at `0x404a18` and closes at
`0x404a24` without ever inspecting the result - the heartbeat shape, not the
leaderboard accumulator. Handler, proto and doc:
`server/ticket_server.py` `handle_gamelist`, `protos/0x11_gamelist_line.ksy`,
`docs/protocol/0x11_gamelist_line.md`. Two things about it stay open, both
minor and both needing a capture rather than more static analysis:

- **Rosters larger than two.** Only a 2-player `game-add` line has ever been
  captured. The sender's loop at `0x404908` is generic in the count at
  `*(arg+16152)`, so a longer roster is expected to be more `" " + <player>`
  tokens and nothing else, but that is an inference. UNBLOCK: capture a
  `game-add` frame from a 4-, 6- or 8-player match and confirm the line is
  still one verb + one session id + N names + `\n`, with no count field and no
  second line.

- **The `games/%s` upload beside it.** Earlier in the same function
  (`0x404820`-`0x4048b8`) the client formats the path `games/<session-id>` and
  hands it to `0xaf39c0` - an HTTP-style request object with a method enum of 4
  (`li r0,4` @ `0xaf39f8`) aimed at a DIFFERENT host object (slot `0x129cd74`
  -> `0x13ba678`) - retrying up to 9 times. That is a separate channel, not
  this TCP line service, and this server does not handle it. What it uploads
  and to which host is not established. UNBLOCK: a capture of the client's
  outbound HTTP during a match end, or resolving `0x13ba678` at runtime.

- **`single-player-server`** - has a hello spec, and its line grammar is now
  RESOLVED via static analysis (2026-08-19, `protos/0x11_stat_line.ksy`):
  `stat %s task-%x %s %s\n` from the campaign-save path, `stat %s trophy-%x\n`
  from the trophy-unlock path, both format strings recovered directly from
  the EBOOT. It has still NEVER been observed sending anything live (0 of 452
  captured sibling hellos), so the grammar is confirmed by decompile, not by
  a real frame. `ticket_server.py` still emits a loud first-contact warning
  if it ever speaks, since that would be the first live confirmation.

- **`invite-server`** - previously investigated and recorded as dead code.

## Behavioural, deliberately not implemented

- **Cross-build join refusal.** A cross-build party invite crosses PSN rather
  than our server, so it is possible in principle; `session_manager.py` WARNS
  but does not refuse, because refusing risks false positives on a build not yet
  in `CLIENT_BUILDS`. Enforce once there is evidence it fires in real use.

- **Host migration.** The engine library (`ndlib`) has the concept
  (`Host Migrate` / `No Host Migrate`, `DebugMigrationStatus`), but this game's
  matchmaking layer has no migration state in its `NET_SM_*` machine and its
  host-loss vocabulary is `matchmaking room host left` / `matchmaking room
  destroyed`, both of which tear down. No server message can create a feature
  the game layer does not implement. See
  `research/notes/2026-08-18-host-migration-feasibility.md`.

## Unresolved facts

- **Are map ids stable across builds?** NARROWED 2026-08-19: the entire
  51-id map-id space (all three mode blocks, `0x0e..0x40`) is now solved on
  01.11, and all seven ids previously observed on 01.00 (`0x0e Checkpoint,
  0x0f Lakeside, 0x10 Bill's Town, 0x13 Downtown, 0x14 The Dam, 0x15
  Bookstore, 0x17 Bus Depot`) line up exactly with the 01.11 roster
  positions - strong evidence for cross-build stability. What's still
  genuinely unresolved: no map has been loaded ON a 01.00 client and its id
  read directly THIS session to prove the match rather than infer it from
  historical captures. See `protos/common/member_data.ksy` for the full
  solved-space writeup. UNBLOCK: play one known map on a 01.00 client without
  being booted in between, and read slot 0 of the next member card.

- **What distinguishes the private-match `field_0c` values?** `0x63` (99) for
  Supply Raid and Survivors, `0x5a` (90) for Interrogation. Not a clean
  per-mode mapping. Playlist ids `4`/`5`, `9`/`10`, `14`/`15` are unused
  capacity in each mode's five-slot block.

- **The VM freezes.** Clients stop with no fatal in the RPCS3 log. Server-side
  orphaning was a real candidate and has been fixed; if freezes continue at the
  same rate the hypothesis is dead and it is environmental. UNBLOCK: copy
  `RPCS3.log` immediately after a freeze, before relaunching.
