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

- **DC net-stat slots, `rank_tier` thresholds, and every id->asset map**
  (cosmetics, character and name pools). Long-standing; see
  `docs/protocol/knowledge-inventory.md` Tier 3.

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
  WHY ZEROS ARE CURRENTLY SAFE: the server sends 20 zero bytes and the full loop
  works - browse, join, load, counted and credited match. So no consumer reached
  so far either requires a non-zero value or rejects zero. That is an absence of
  evidence, not a proof of inertness: a consumer keyed off this span would show
  up as a cosmetic or a filtering difference in the browser (a wrong icon, a
  room that should have been filtered out), not as a hard failure, so it could
  sit unnoticed indefinitely. It cannot be fixed blind - inventing field
  meanings here would put unverified fields into a proto, which is exactly what
  `docs/methodology.md`'s confidence discipline forbids.
  UNBLOCK - both halves are needed, neither alone suffices:
    (a) decompile the copy of that block on BOTH sides. The `0x136`
        deserializer is the `0x136` case of `FUN_00ad7604`, which byte-copies
        from `wire[0x14]` into the entry object; the consumer is
        `_opd_FUN_003b2a9c` (the joiner's `CONNECT_TO_HOST` handler), which
        copies the entry's attribute block again. Find the loads that land
        inside `0x24:0x38` and note their widths and offsets.
    (b) correlate against a live capture in which the host varies exactly ONE
        search/lobby option at a time (mode, map, playlist, privacy, NAT, party
        size) between otherwise identical rooms, so each byte that changes is
        attributable to one option.
  Static analysis alone yields offsets with no meanings; captures alone yield
  byte diffs with no proof of what reads them. Together they yield named
  fields.

- **`0x12f room_settings_tail` / `0x130 room_object_tail`** - 32 bytes each,
  provenance known (copies of specific room-object spans), interiors unmapped.

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

- **`single-player-server`** - has a hello spec; has NEVER been observed sending
  anything, so its line grammar is unknown. `ticket_server.py` now emits a loud
  first-contact warning if it ever speaks, since that request would be the only
  evidence of its grammar.

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

- **Are map ids stable across builds?** 01.11: `0x1f` Checkpoint, `0x31`
  Lakeside. 01.00's seven observed ids (`0x0e`-`0x17`) are all unnamed. The
  ranges do not overlap, but 01.00's test accounts own no MP DLC and so could
  only ever play base maps - a narrower range is expected either way, and proves
  nothing. UNBLOCK: play ONE known map on a 01.00 client without being booted in
  between, and read slot 0 of the next member card.

- **What distinguishes the private-match `field_0c` values?** `0x63` (99) for
  Supply Raid and Survivors, `0x5a` (90) for Interrogation. Not a clean
  per-mode mapping. Playlist ids `4`/`5`, `9`/`10`, `14`/`15` are unused
  capacity in each mode's five-slot block.

- **The VM freezes.** Clients stop with no fatal in the RPCS3 log. Server-side
  orphaning was a real candidate and has been fixed; if freezes continue at the
  same rate the hypothesis is dead and it is environmental. UNBLOCK: copy
  `RPCS3.log` immediately after a freeze, before relaunching.
