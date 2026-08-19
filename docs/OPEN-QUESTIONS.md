# Open questions

Things that are known-unknown rather than undiscovered. Each entry says what is
blocking it and what would unblock it, so none of them silently become "we never
looked".

## Blocked on data-compiler (.pak / netN.bin) payload

Not recoverable from the EBOOT by any amount of static analysis - the values
live in the data-compiler payload the game loads at runtime.

- **`pReportArray` entry names.** The ban check (`report-server`, `is-banned`)
  reports an account as banned iff the reply's second token `strcmp`-matches an
  entry name in this table. The table's SHAPE is high confidence (12-byte
  entries, `[+4]` message StringId, `[+8]` `const char*` name, resolved by DC
  symbol hash `0xFFAC56F2`); the literal strings are not.
  IMPACT: none on current behaviour. The server answers "not banned" with an
  empty body, which fails the parser's `'+'` test at `0x36e2cc` and leaves the
  ban index at its `-1` default. Knowing the names would only be needed to
  deliberately ban somebody, which this project has no reason to do.
  UNBLOCK: a DC/.psarc dump, or a runtime read of the resolved table.

- **The integer at `g_net+920`.** Parsed from the ban reply's first token and
  formatted into the ban message shown to the player. Duration / expiry / days
  is a guess and is deliberately not recorded as fact. Its format-string pointer
  `0x1530d90` is bss, so it is only readable at runtime.
  IMPACT: none - see above.

- **DC net-stat slots, `rank_tier` thresholds, and every id->asset map**
  (cosmetics, character and name pools). Long-standing; see
  `docs/protocol/knowledge-inventory.md` Tier 3.

## Unmapped wire spans

- **`0x136` `attr_tail`** - the 20-byte remainder of each game-list entry's
  36-byte attribute block (`0x24:0x38`). The server sends zeros and matchmaking
  works, so nothing is visibly broken; the interior was simply never mapped.
  UNBLOCK: decompile the `0x136` deserializer's copy of that block
  (`_opd_FUN_003b2a9c` handles the entry) and correlate against a capture where
  the host varies one lobby option at a time.

- **`0x12f room_settings_tail` / `0x130 room_object_tail`** - 32 bytes each,
  provenance known (copies of specific room-object spans), interiors unmapped.

## Unhandled sibling services

Eight service names exist in the 01.11 EBOOT. Five have handlers.

- **`gamelist-server`** (01.11-only, `0xeb2690`). One verb: `game-add ` at
  `0xeb2680`. Live capture:
  `game-add mgnomad2.1787116698 mgnomad2 comradesean` - the match-session id
  (`<npid>.<unix-ts>`, the same string `0x143` carries) followed by the roster.
  No `game-remove` or `game-list` verb exists anywhere in the binary, so this
  looks like write-only registration rather than a discovery path.
  UNBLOCK: decompile the sender near `0xeb2680` to confirm whether the reply is
  parsed (heartbeat-style single bounded recv, or leaderboard-style accumulator)
  before writing a handler.

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
