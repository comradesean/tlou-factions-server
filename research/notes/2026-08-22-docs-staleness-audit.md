# Docs staleness audit - cross-checking the 2026-08-21/22 rapid-edit session

Date: 2026-08-22. This session's own edits (`docs/OPEN-QUESTIONS.md`,
`protos/0x11_stat_line.ksy`, `protos/0x11_report_line.ksy`,
`protos/profile_21.ksy`, `docs/protocol/profile_21_record.md`,
`docs/protocol/0x11_sibling_servers_family.md`,
`docs/protocol/userdata_and_campaign_config_crypt.md`,
`docs/served-content.md`, `docs/protocol/knowledge-inventory.md`,
`server/lib/userdata_crypt.py`, `server/ticket_server.py`) happened fast,
several via parallel background agents on overlapping files. This is a
one-pass audit for exactly the failure mode that creates: a claim updated in
one file whose sibling/index reference to the same fact wasn't updated at the
same time.

## What was checked

1. Every file in the "heavily touched tonight" list, read in full, cross-
   referenced against every other file making the same claim.
2. `server/ticket_server.py`'s actual current code (`handle_single_player`,
   `build_stat_response`, `log_stat_event`, `handle_report`,
   `build_report_response`) against what the docs say it does - function
   names, `kind` values, log path (`server/logs/stat_events.jsonl`).
3. Every `research/notes/2026-08-21-*.md` / `2026-08-22-*.md` filename cited
   anywhere in `docs/`, `protos/`, `server/` - confirmed each resolves to a
   real file (`diff` of cited vs. actual, both directions: clean, zero
   mismatches).
4. Date consistency for the same event across files (all internally
   consistent - no 08-21-vs-08-22 mismatch found for the same event).
5. Lower-priority broad spot-check of `docs/protocol/knowledge-inventory.md`
   and `docs/protocol/proto-map.md` for staleness unrelated to tonight's
   specific work, since both are index/summary docs with a history of
   lagging behind detail docs.

## Found and fixed

1. **`docs/OPEN-QUESTIONS.md`, "Genuinely unknown" section** - the
   `stat_line`'s second `%s` entry still said "zero live samples", while the
   file's OWN earlier `single-player-server` section (and
   `protos/0x11_stat_line.ksy`) already documented it as
   live-confirmed (`BCUS98174`) on 2026-08-21. Rewrote in place as RESOLVED,
   redirected the genuinely-still-open piece (the `%x` task hash's specific
   meaning) to the right research notes.

2. **`protos/profile_21.ksy`, `game_data` type doc** - the top-level summary
   still claimed "everything past payload 0x1E6C (P+0x1E74) is zero in both
   real samples", directly contradicted by the `promotion_flags_1e74` field
   doc ~290 lines below it in the SAME file, which documents that range as
   genuinely non-zero on one of three accounts. Corrected the summary and
   pointed at the field doc for the resolved boundary
   (`P+0x1E8C` onward, not `P+0x1E74` onward, is the confirmed-zero span).

3. **`docs/protocol/profile_21_record.md`** - the `P+0x1E74` prose section
   (mtime predates the "angles 2/3" research pass) still said "Two angles
   remain genuinely open (not ruled out)" for the DLC-entitlement /
   capability-register hypotheses, when both were chased and closed the same
   night (`research/notes/2026-08-21-promotion-flags-angles-2-3.md`), leaving
   only the `promo1/` `.edat` circumstantial lead and the "static analysis
   exhausted" verdict. Updated to match the `.ksy` file's final state.

4. **`docs/protocol/knowledge-inventory.md`, Tier 3 item 50** - still read
   "the request is captured, the reply is not... Needs a capture" for
   `report-server`'s response grammar, while the SAME file's own Tier 1 item
   31 already says this was resolved 2026-08-21 and moved out of Tier 3. Item
   50 was an un-updated duplicate; rewrote it as resolved and removed the
   stale "our stub answers a ban check with a ticket blob" implementation-risk
   note (the dedicated `handle_report` handler has existed since 2026-08-19).

5. **`docs/protocol/knowledge-inventory.md`, item 56** - referenced
   "item 57-adjacent work", but there is no item 57 in this file (the
   numbered list ends at 56). Fixed the dangling reference to point directly
   at the doc it meant.

6. **`docs/protocol/knowledge-inventory.md`, header** - said "Current as of
   2026-08-20" while the same paragraph describes a 2026-08-21/22 pass.
   Updated the date.

7. **`server/ticket_server.py`, `log_stat_event`'s header comment** - said
   "The sibling campaign-save grammar... is still unconfirmed live", which
   was true when written but is now wrong: both grammars are live-confirmed
   (seven task-line captures, per `protos/0x11_stat_line.ksy`). Updated in
   place, preserving the original trophy-line confirmation text.

8. **`server/lib/userdata_crypt.py` module docstring** - said "six real
   `task-%x` telemetry sends", but a seventh capture
   (`task-e4c65aa7`, 2026-08-22 00:59:41, directly correlated against the
   GATE 2 throttle counter) was added later the same night and this count
   was never bumped. Fixed to "seven" and the date range to "2026-08-21/22".

9. **`docs/protocol/0x11_sibling_servers_family.md`** - the "What's still
   open" list and confidence-summary table both said no sibling besides
   ticket-server had an independent live post-hello-frame capture. That's
   stale as of the same night's work: `single-player-server`'s frame is now
   live-confirmed (nine real captures decrypting to the documented
   plaintext), and `report-server`'s request side has nine live captures of
   its own. Updated both the open-items list and the confidence table in
   place, without removing the still-genuinely-open siblings
   (heartbeat/leaderboard/facebook/gamelist).

10. **`docs/protocol/proto-map.md`** (mtime 2026-08-21 15:42, predates
    essentially all of that night's resolution work - not on the original
    "heavily touched" list, but caught by the broader spot-check the task
    asked for) - four stale rows in its "Open questions" table, all
    superseded hours later by work already reflected everywhere else:
    - `report-server` response grammar: said "reply never observed... A
      retail capture [needed]"; actually resolved from the binary alone,
      2026-08-21, no capture needed or obtained.
    - `profile_21` zero region: said "Purpose unknown. -"; actually mostly
      resolved the same night (see items 2-3 above).
    - `stat_line` task line's 2nd `%s`: said it needs "a live memory read...
      not reachable by static analysis alone"; that live read happened
      the same night (`BCUS98174`).
    - `single_player_server_hello`/`stat_line` row and the `task-%x` row in
      the main table: both still said "0 of 452 captured hellos" / "resolved
      integer value itself is still open"; both superseded by the same
      gate-fix-and-live-capture work as everything else in this audit.
    All five rows rewritten in place, preserving the original static-analysis
    reasoning as history rather than deleting it.

## Checked and found NOT stale (no change made)

- `protos/0x11_stat_line.ksy` and `protos/0x11_report_line.ksy` themselves -
  both read as internally consistent and already carry the full
  correction-in-place history; no fix needed to either file's own body.
- `docs/protocol/userdata_and_campaign_config_crypt.md` and
  `docs/served-content.md` - both newly-created tonight, both internally
  consistent with each other and with `server/lib/userdata_crypt.py`'s
  container-format claims.
- `server/ticket_server.py`'s `build_report_response`/`handle_report` -
  matches `protos/0x11_report_line.ksy`'s documented empty-body/fail-open
  behavior exactly; no drift found.
- `docs/protocol/knowledge-inventory.md` items 31, 31b, 52, 53 (the
  Tier-1/Tier-2 entries for the same facts fixed in item 50 above) - already
  correctly updated; only the Tier-3 duplicate (item 50) and the dangling
  "item 57" reference were stale.
- `docs/protocol/profile_21_record.md`'s field table (row for
  `promotion_flags_1e74[6]`) - confidence rating ("med/open") still
  accurately reflects the final state after the angles-2-3 pass; the prose
  section above it needed the fix (#3), the table row did not.
- Research note filenames: zero broken references, zero orphaned notes not
  cited anywhere relevant, in either direction.

## Left open for a human call

Nothing found during this pass required an arbitrary pick between two
genuinely conflicting claims - every inconsistency found had one side that
was clearly the later, more-verified state (a live capture superseding a
"needs a capture" note, a later research pass superseding an earlier "two
angles remain open" note, etc.), so all were resolved by updating the stale
side to match the verified side rather than guessing. Nothing is queued here
for a human decision.
