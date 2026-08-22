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

- **DC net-stat slots and most of the id->asset map** (cosmetics,
  character and name pools). Long-standing; see
  `docs/protocol/knowledge-inventory.md` Tier 3. `rank_tier` is REMOVED
  from this item as of 2026-08-20 - it's fully resolved, see below.
  PARTIALLY UNBLOCKED 2026-08-19: cosmetic StringIds are now resolvable
  live via `research/tools/text_table.py` (confirmed: hat/mask/helmet) and
  `research/tools/dc_hash_crack.py` (confirmed: character skin variant).
  SOLVED 2026-08-20 for the emblem shape catalog on all four layers (one
  identical formula, no per-layer offset): `shape_index-1` indexes
  directly into a 192-entry flat name catalog on the disc, proven against
  all 192 entries via live edit-and-diff testing
  (`research/tools/profile21_codec.py`). Rotation/scale/opacity and the
  colour picker's grid-*position* formula are solved too. Full table:
  `research/notes/2026-08-20-emblem-shape-catalog.tsv`; derivation:
  `research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md` §9-§11.
  Also solved: `emblem_location` (was `flag_1e40`, wrongly documented as a
  boolean - it's a 4-value enum, None/Torso/Helmet/Backpack).

  UPDATE 2026-08-20 (second, purely static pass): root-caused why several
  of the above kept hitting a "nested DC structure" wall - the DC00
  directory record was being read as `{value_ptr, key_hash, type_hash}`;
  it is actually `{key_hash, type_hash, value_ptr}`, one word off. Fixing
  that makes `net.bin`'s entire 392-entry directory dumpable by name
  (`research/tools/dc_dir.py`, 392/392 crack). This closed three more
  items:
  - **`member_data.rank_tier` - RESOLVED.** The "193-entry table that
    never read as thresholds" was the *preceding* record
    (`*net-emblem-layers-frame*`); `*net-money-info*`'s real table is a
    clean monotonic ladder, and running the consuming function's loop on
    it proves the DC branch is dead code - `rank_tier` is nonzero only
    via an untraced override at `*(global+0x78)`, matching 855/855 live
    captures. See `protos/common/member_data.ksy`'s field doc.
  - **Emblem colour swatches - SOLVED.** `*net-emblem-colors*` is 64 real
    RGBA f32 values, an 8x8 hue/shade grid - independently corroborates
    the grid-*position* formula found via live testing.
    `research/notes/2026-08-20-emblem-color-catalog.tsv`.
  - **`equipped_gesture_id`'s "hash algorithm" - dissolved, not solved.**
    It was never a hash to crack: the ids are rows of a real DC table,
    `*net-taunts*` (11 entries), resolved via `text_table.py` against
    `text1.psarc`. All 11 gestures named; six match the prior live-edit
    values exactly, the other five are the names already seen locked
    in-game.

  Still open: the intra-table hash used for a shape's name-hash / a
  gesture's id-hash (confirmed NOT `crc32_mpeg2` by exact single-byte-delta
  tests, though the CRC-32 polynomial is visible in the deltas - a
  curiosity, not a blocker, since every table pairs its hash with a
  plaintext name or StringId anyway), and a handful of unexplained bytes in
  the emblem words. CLOSED 2026-08-20: `member_data.capability_flag` bit
  meanings (solved bit-by-bit against `*net-maps*`'s required-mask column -
  see `research/notes/2026-08-20-tier2-followup.md` §1) and `global+0x78`'s
  writer (proven to not exist anywhere in the binary, closing `rank_tier`
  entirely - see §7 of the same note).

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

- **`single-player-server`** - RESOLVED, both line grammars now LIVE-CONFIRMED
  (2026-08-19 static, 2026-08-21 live). `stat %s task-%x %s %s\n`
  (campaign-save path) and `stat %s trophy-%x\n` (trophy-unlock path), both
  format strings recovered from the EBOOT and both since observed live
  byte-for-byte. Has a real handler (`handle_single_player` /
  `build_stat_response` in `ticket_server.py`).

  The campaign-save line specifically took real work to reach: it was
  structurally unreachable for most of 2026-08-21, root-caused
  (`research/notes/2026-08-21-stat-line-config-writer-trace.md`) to
  `FUN_007f1acc`'s throttle modulus and single-player-server ip/port fields
  never getting populated by the save-manager singleton's constructor
  (`FUN_007f149c`), which only runs that population step once, and only if
  a live HTTP GET+decrypt of `campaign.config.txt.crypt` succeeds -
  `http_gateway.py`'s upstream S3 bucket for that path is dead, so it was
  falling back to an empty `200 OK` that can't decrypt (confirmed both by
  decompile and by a live breakpoint reading the singleton's fields as
  all-zero at the moment of a real save).

  FIX: the `.crypt` container turned out to already be a solved format -
  the same one this project cracked for `userdata/<id>.txt.crypt`
  (`server/lib/userdata_crypt.py`), which explicitly documents
  `campaign.config.txt.crypt` as a sibling using an identical container
  with a static, title-wide (not per-session/digest-pinned) Blowfish+HMAC
  key pair. The real retail plaintext for this file family was already
  decrypted back on 2026-08-17
  (`research/notes/2026-08-17-userdata-txt-crypt-format.md`):
  `queue-server-addr 50.18.47.114` / `queue-server-port 7320` /
  `interval 10` / `enable 1` (port 7320 matches this project's own
  ticket_server/single-player-server listener - not a coincidence). Built
  and deployed a replacement at
  `server/data/served_content/campaign.config.txt.crypt` with
  `queue-server-addr=192.168.1.100`, everything else unchanged - HMAC
  verified OK on decode.

  LIVE-VERIFIED END-TO-END, 2026-08-21, after a fresh RPCS3 boot picked up
  the new file: `single-player-server` opened a fresh connection and sent

      stat comradesean task-7d9d7acc BCUS98174 HD

  which also closes three previously-open sub-fields in one live capture:
  `task-%x` resolves to `0x7d9d7acc` (the "general/hud/prize-icon/Default"
  DC-table id, previously known only structurally), the 2nd `%s` is the
  title's own product code `BCUS98174` (previously DC/runtime-blocked -
  turned out to be a per-title constant, not save-specific), and the 3rd
  `%s` is `"HD"`, matching the predicted two-value enum. See
  `protos/0x11_stat_line.ksy` for full field-level detail.

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

- **Are map ids stable across builds? - RESOLVED (live) 2026-08-21.** Loaded
  Checkpoint on a build-01.00 client this session (private match, Supply
  Raid) and read `member_data.recent_level_0` directly off the wire in the
  following `0x13a SetPartyData` frame (`03:07:41`): `0x000e` - the exact
  historical value for Checkpoint/Supply Raid, matching every prior
  capture. This was the one open piece after the 2026-08-19 01.11 solve
  (which covered all 51 ids by static/historical-capture inference but
  never re-read a live 01.00 client this session). See
  `protos/common/member_data.ksy` for the full solved-space writeup.

- **What distinguishes the private-match `field_0c` values?** RESOLVED
  2026-08-21, LIVE (RPCS3 memory write-breakpoint, PPU Interpreter mode
  required - the field is genuinely random: private "Host" draws it from a
  small heap-allocated 2-entry candidate table (`{0x09,0x13}` this session)
  via a lazily-seeded LCG PRNG, gated by a flag that also explains the
  earlier "streaky but not periodic" pattern (streaks = gate false, value
  holds from the previous room; flips = gate true, re-rolled). Mechanism is
  reused generic code (the same function does an identical random-table-pick
  for a different, unrelated field immediately before it), not a bespoke
  "private match category" feature - the specific values `0x09`/`0x13` don't
  trace to anything named in `net1.bin` (a promising-looking byte-exact match
  there turned out to be coincidental - see the full writeup). Practically:
  cosmetic client-side placeholder, safe for a server to ignore entirely.
  SAME SESSION, SEPARATELY RESOLVED: the long-suspected but never
  instruction-verified "elected host stamps the real playlist id" claim -
  caught live twice at a different call site (`FUN_0035ADB4`), mode-correct
  both times (Supply Raid -> `2`, Survivors -> `3`, 01.00's real ids). Full
  disassembly, register dumps, and the retracted net1.bin lead are in
  `protos/0x12f_room_create.ksy`'s `room_field_0c` doc.

  PRE-RESOLUTION HISTORY (kept for the record): CORRECTED
  2026-08-21, re-checked against the full `server/logs/session_manager.log`
  and `wire.jsonl` rather than the earlier note's small sample: `0x5a` and
  `0x63` both recur repeatedly, not "one constant plus a single anomaly."
  The SAME private lobby (same room object `0x13babd8`, same host) was
  re-created eight times over eight minutes and `field_0c` alternated
  `0x5a`/`0x63` (`5a,5a,63,63,5a,63,63,63`). Cross-referenced against each
  create's own `member_data.recent_level_0` (the host's recently-played-map
  ring), real map/mode changes DID happen between these creates - it was
  not an idle no-op sequence - yet four consecutive SAME-MODE (Survivors)
  private matches still split `0x5a` once / `0x63` three times. So it
  tracks neither mode cleanly NOR reads as pure state-independent residue -
  genuinely UNRESOLVED, not closed in either direction. That sample was
  01.11. A much larger deliberate 01.00 sweep (2026-08-21, comradesean +
  mgnomad2 party, 24 clean private-match creates across every 01.00 map in
  both Supply Raid and Survivors, several maps reloaded 2-4x) reproduced the
  same shape of result with 01.00's own value pair (`0x13`/`0x09`, not
  `0x5a`/`0x63` - the two builds appear to use disjoint value pairs): a
  15/9 split with no clean correlation found against map, mode, a
  loadout-screen visit (directly ruled out - a non-touch round got the same
  value as touch rounds), streak position (the value broke its streak at
  the 6th create in both the Supply Raid and Survivors sub-runs, but the
  7th round then diverged between the two, ruling out "6th create" as the
  trigger too), or a preceding Find Match search (ruled out - the
  confounded round below still read from the same `{0x13,0x09}` pool, not
  the search's own playlist id). Full round-by-round table, three standing
  theories (unrelated-code-path residue, a real two-state toggle, and a
  timing/frame-dependent read), and a 4-step research plan are all in
  `protos/0x12f_room_create.ksy`'s `room_field_0c` doc. STEP A (static
  write-scan of every store to `room_obj+0x0c` across the whole EBOOT) WAS
  RUN 2026-08-21 - three independent, largely-exhaustive search strategies,
  no writer found by any of them (a genuine, cross-checked-sound negative
  result, not "didn't look hard enough" - it also surfaced that the
  matchmaking-side "host stamps the playlist" claim was never itself
  instruction-verified, only inferred). Not conclusive either way, since
  the field demonstrably changes value live - something must write it.
  Next: a live RPCS3 memory write-breakpoint (real feature, merged March
  2025, but needs a self-compiled build with `-DHAS_MEMORY_BREAKPOINTS=ON`
  - not in standard downloads, and ~2-3x slower in PPU interpreter mode
  while enabled; a custom build was in progress as of this pass) or manual
  breakpoint-and-read polling across chosen UI transitions as a fallback.
  SEPARATELY FOUND
  during this sweep: a real server bug, now fixed - `session_manager.py`'s
  `NON_MATCHMAKING_PLAYLISTS` denylist only knew 3 private/party values
  (`0x58`/`0x5a`/`0x63`, all from the older 01.11-era sample) and so
  misclassified any private match whose `field_0c` landed outside that list
  (which, per this sweep, is common) as PUBLIC/matchmade whenever a stale
  find-match search flag was set - reproduced live 2026-08-21, fixed by
  switching to an allowlist against the known `MATCHMAKING_PLAYLISTS` set
  instead of a denylist against private values (see the fix's comment in
  `server/session_manager.py` for the full reasoning and reproduction).
  Playlist ids `4`/`5`,
  `9`/`10`, `14`/`15` remain unused capacity in each mode's five-slot block
  for MATCHMAKING rooms, which is a separate and still-solid finding from
  this one.

## Remaining items after the 2026-08-20 tier-2/audit pass, categorized by blocker

The four tractable items from that pass were worked the same day; results in
`research/notes/2026-08-20-followup-open-items.md`. Outcomes:

- **`FUN_00ad5b78`'s caller - RESOLVED.** Two vtable-`+0x10` dispatch sites
  found statically (`0x0035D440` in the `"Host"` state, `0x003B7FB0` in the
  `"GATHER"` state), all seven arguments named, and `caller_arg_1c` /
  `max_players` / `room_flags_e8`'s OR-gate resolved as a consequence. A
  THIRD site (the party path, `0x003CAC5C`) was then caught live - see the
  residual-gaps entry below, which closes it.
- **`0x13e` kind=3's vtable+0x18 selector - RESOLVED.** It is
  `*(u32*)(netsession + 0x358) == 2`, via `FUN_003abe4c` on vtable
  `0x01224178`. All three of the enum's values were live-confirmed later the
  same day - see the dedicated entry under "Residual gaps" below; details in
  `protos/0x13e_set_host_flag.ksy`.
- **`0x142`'s per-u16 encoding - FULLY RESOLVED (live).** The value is a
  packed bitfield mechanically, but reduces to a plain `member_id` in every
  real send. It's the host reporting every OTHER room member's id, never its
  own - which is also why `1` never appeared on the wire. See
  `protos/0x142_host_rank.ksy` and
  `research/notes/2026-08-20-followup-open-items.md` §3.
- **`capability_flag` bit 1 - CLOSED.** Nothing consumes it. See
  `protos/common/member_data.ksy`.

Everything below is what's left, sorted by WHY it's stuck rather than left as
an undifferentiated pile, so revisiting this list doesn't require re-deriving
the reason each item stalled.

### Blocked on a live resource this project doesn't have

- **`0x136 attr_tail`'s interior meaning.** Mechanism resolved at instruction
  granularity (producer, both copy sites, exhaustive no-reader scan); the
  bytes themselves are opaque without a reference implementation. UNBLOCK: a
  PS4 Remastered retail capture - see this file's existing `0x136` entry
  above for the full capture plan, already written and ready to execute the
  moment PS4 access exists.

### Residual gaps left by the 2026-08-20 follow-up pass

- **Where the PARTY's `0x12f RoomCreate` is sent from - RESOLVED (live).** A
  breakpoint at `FUN_00ad5b78` during a real party join caught it: the call
  is at `0x003CAC5C`, inside `FUN_003CA9D0` (the 9-state room state machine),
  the `party_obj+0x1A50 == 0` branch of its jump table. This also resolved
  `is_party`'s (was `flag_27`, renamed 2026-08-21) live `0x04` (the party
  site passes `r6=1`). See
  `protos/0x12f_room_create.ksy` and
  `research/notes/2026-08-20-followup-open-items.md` §1.
- **Which input produces `0x142`'s live `0x0002` - RESOLVED (live).** Not a
  mapping-onto-an-input problem after all: the write path is proven correct
  (five live breakpoints, both accounts), and the value that reaches the
  wire IS the correct `member_id` - just never the SENDER's own. `0x142` is
  the host listing every other room member's id. See
  `protos/0x142_host_rank.ksy` and
  `research/notes/2026-08-20-followup-open-items.md` §3. Which specific
  filter inside `FUN_0039b720` performs the self-exclusion is now
  RESOLVED 2026-08-21 (static): filter 1 of the seven-filter loop
  (`0x39b7a8`-`0x39b7d0`), an object-identity check against either
  local-player slot via `player->vtable[0xC]` (`FUN_003CDCB8` ->
  `FUN_0039a380(0x0137D700, 0|1)`), not a `member_id` comparison. See
  `protos/0x142_host_rank.ksy` for the full seven-filter breakdown.
- **Names for `netsession->field_0x358`'s three values** (the `0x13e` kind=3
  encoding selector) - FULLY RESOLVED 2026-08-20, all three live-confirmed.
  `0` = idle/no active mode descriptor - two breakpoint hits by two different
  paths to the same transition ("Leave Matchmaking" -> Yes, and a "Searching
  for players..." attempt timing out on its own with no explicit cancel), so
  the reading is "whenever a matchmaking search stops", not "on cancel".
  `1` = actively resolving/committed to a mode descriptor - three
  breakpoint hits across two distinct contexts (post-match survivor-count
  update, post-match mission selection, AND a fresh find-match entry from
  the main menu at the "Starting in 3...2...1" countdown) settled that this
  is a general mode-commitment state, not specifically post-match. `2` =
  "Host" party-creation state (static, `FUN_0035D59C` immediately after the
  `"Host"` RoomCreate state). `kind=3`'s RAW-vs-ENCODED split now reads
  cleanly in light of this: RAW is reserved for the `"Host"`
  state specifically, ENCODED is the general form used in both other states.
  See `research/notes/2026-08-20-followup-open-items.md` §2.

### Blocked on a rare or never-reproduced live condition

- **"Host quit for cheating" match teardown.** Reported once, rare, trigger
  unknown. STATIC TRACE RUN 2026-08-22
  (`research/notes/2026-08-22-host-quit-for-cheating-string-trace.md`) -
  the partial unblock this entry used to describe as unattempted is now
  done. The string (VMA `0xe7fad0`) has exactly one code reference
  (`0x003f1580`, inside a function starting at `0x003f10b8`), reached only
  when a chain of five conditions all hold: a nonzero byte-sized "reason"
  parameter passed into the function, an unnamed flag byte at
  `some_object+11692` combined with an unnamed predicate (`0x3abe80`), a
  count from an unnamed helper (`0x39935c`) `> 3`, the same party predicate
  this project already names elsewhere (`0xad0eec`) returning true, and a
  second unnamed flag byte at `some_object+172` being zero. Full trace with
  every instruction cited is in the note above. STILL OPEN: none of the
  individual predicates/flag bytes are named yet - a real reproduction
  remains the only way to confirm which specific in-game action satisfies
  this five-way compound condition, since it's not something to guess the
  meaning of from addresses alone.

### Structurally closed, unless new evidence contradicts it

- **`member_data.card_string_0`/`card_string_1`'s string content.** Not blocked
  on a resource - CLOSED on 01.00: the only code path that could ever write a
  non-empty value into the 8-byte string is gated on a byte
  (`*(0x013839d0+0x40)`) that no store anywhere in the 01.00 binary touches
  (see `protos/common/member_data.ksy`'s field doc and
  `research/notes/2026-08-20-tier2-followup.md` §2). Revisit only if: (a) a
  future static pass finds a writer this one missed, or (b) the same check is
  ever run against the 01.11 binary (available since 2026-08-20 but not used
  for this - card_stat has read as zero in both build eras' captures, so
  there's no known build-specific behavior motivating the extra work yet).

- **`report-server`'s RESPONSE grammar** (distinct from the already-solved
  `is-banned` REQUEST / `pReportArray` table above). RESOLVED 2026-08-21 -
  see `research/notes/2026-08-21-report-server-response-grammar.md` and
  `protos/0x11_report_line.ksy`'s `ban_reply_row` type. Full token grammar
  traced and re-verified against a fresh 01.11 objdump: `'+' <ban_index
  decimal> <sep> <name> <ignored tail>`, single-pass (no repeating-row
  outer loop). Also settles a second open question - whether `report-server`
  handles any request beyond the ban self-check (the family name suggests
  "report a player"): NO. An exhaustive scan of all 12 call sites to the
  shared connect+hello function `0xaf9bb4` in the 01.11 EBOOT shows each
  passes a distinct service-name string, and only one (`0x36e220`) passes
  "report-server"; the string's neighborhood in the string table has no
  second verb literal either. "report" in the name is a naming artifact of
  the shared backend, not a second client-side grammar. This project's stub
  was already correctness-safe regardless (an empty body never triggers a
  ban - see the `pReportArray` entry above); this pass was documentation
  completeness only, and a live capture is not worth prioritizing since it
  couldn't add anything beyond the already-separately-tracked
  `pReportArray` name recovery and `g_net+920` meaning (both still
  data-compiler-blocked, unaffected by this pass).

- **`profile_21`'s zero region, `P+0x1E74..0x5008`.** WALKED 2026-08-21 - see
  `research/notes/2026-08-21-profile21-zero-region-walk.md`,
  `protos/profile_21.ksy`'s `promotion_flags_1e74`/`reserved_1e8c` fields.
  Mostly CLOSED: `P+0x1E8C..0x5008` (~12668 of the ~13172 bytes) is
  confirmed zero on three real accounts and has no EBOOT producer of any
  kind (the record's universal accessor's 436 call sites were exhaustively
  traced, both static-immediate and dynamic loop-computed forms) - genuinely
  unused/reserved, no live blocker. The remaining `P+0x1E74..0x1E8B` (24
  bytes, six flag words) is real, non-zero, per-account data with no EBOOT
  writer found despite the same exhaustive trace - narrowed to a live
  RPCS3 memory-write-breakpoint blocker (the note's §5 has the concrete
  test plan: a fresh/low-progress account, trigger the in-game "Promotion"
  reward event, watch the buffer for a write). DLC-entitlement hypothesis
  tested 2026-08-21 against the 01.11 EBOOT (in case the writer existed
  only in the DLC-aware build and was invisible to a 01.00-only trace) -
  see `research/notes/2026-08-21-promotion-flags-dlc-hypothesis.md`: NOT
  supported. 01.11's own record accessor was independently re-derived
  (`0x3e6adc`, 501 call sites) and shows the identical "nothing reaches
  P+0x1E74..0x1E8B" result as 01.00; two genuine DLC/entitlement tables
  found in 01.11 (8 and 4 entries) don't match the six-word count; a
  `net10.bin` vs `net1.bin` DC-directory diff found 46 new 01.11-only
  globals with no clean six-row candidate among them. Two angles that pass
  left open were both chased 2026-08-21 - see
  `research/notes/2026-08-21-promotion-flags-angles-2-3.md`: the
  capability/entitlement register was relocated to 01.11 by signature
  (`0x01502808`, via its two consumers `FUN_0037C85C`/`FUN_0037C95C`) and
  fully traced - confirmed uninvolved, closing that angle for good; the 46
  new `net10.bin` keys plus the `*unlock-list*` table's 169-row diff
  (284->453 rows) were name-cracked against a widened corpus (3/46
  resolved to new DLC5 skill-upgrade tables, none promotion-related). A
  strong circumstantial lead turned up outside the hash-crack path: the
  01.11 install's `build/main/promo1/` directory holds seven genuine PSN
  pre-order `.edat` entitlements, one of which (`PROMOEXTRASUPPLY`) is
  unmistakably `milestone_latch_1e2c`'s own grant - leaving exactly six
  sibling items (`PROMOEARLYBRAWLR`, `PROMOELLIESKIN01`,
  `PROMOHATSHELMETS`, `PROMOJOELSKIN001`, `PROMOLOADOUTPOIN`,
  `PROMOSPUPGRADESF`), matching the six-word count exactly - but nothing
  connects them to this field on the wire, in a cracked hash, or in a
  table row. **Static analysis is now exhausted for this field.** The live
  memory-write-breakpoint test remains the only real way to close this -
  check the call stack does NOT pass through the entitlement register's
  consumers (per this pass, it shouldn't), and if a live account's
  inventory is available, check it against the six named PROMO items
  above. CORROBORATED 2026-08-21: the six-item reading matches the real
  retail Factions pre-order/promo bonus lineup for these exact items
  (early Brawler unlock, an Ellie skin, a Joel skin, a hats/helmets
  cosmetic pack, a loadout-point grant, a supply-pickup upgrade) - real-
  world confirmation of the SET's identity, raising confidence in the
  "six per-item grant flags" reading, though it doesn't itself prove the
  write mechanism; the live breakpoint test above is still what would
  close that.

### Genuinely unknown - no static trace attempted, no live blocker identified

These are open because nobody has looked yet, not because looking is known to
fail. Lower priority than the tractable list above only because nothing
currently depends on the answer.

- **`stat_line`'s second `%s`** in the campaign-save line
  (`stat %s task-%x %s %s\n`) - RESOLVED (live) 2026-08-21, moved here from
  its earlier "zero live samples" status now that the campaign-save line has
  actually been captured (see the `single-player-server` entry above under
  "Unhandled sibling services" for the full fix/deploy story that unblocked
  it). Six task lines plus a seventh 2026-08-22 all read
  `stat comradesean task-<hash> BCUS98174 HD`: the 2nd `%s` is
  `BCUS98174`, the title's own PS3 product/serial code (a per-title runtime
  constant, not save-specific); the 3rd `%s` is `HD`, matching the predicted
  two-value size/medium enum exactly. Both are now closed. Full field-level
  detail and live-capture log: `protos/0x11_stat_line.ksy`. What's still
  open in this line is a DIFFERENT parameter - the `%x` task hash's exact
  per-save meaning (a HUD-icon-lookup id that varies call to call via a
  5-slot dynamic content-module registry, not yet correlated against actual
  chapter transitions) - see `protos/0x11_stat_line.ksy`'s `%x` field doc and
  `research/notes/2026-08-21-task-hash-variation-trace.md` /
  `research/notes/2026-08-22-task-x-offset-reconciliation.md`.
