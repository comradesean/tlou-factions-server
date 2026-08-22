meta:
  id: stat_line
  title: single-player-server stat line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server, fire-and-forget (no parsed reply expected -
  same weak-recv pattern as gamelist_line).

  RESOLVED 2026-08-19, in answer to the hypothesis that single-player-server
  broadcasts campaign progress to friends (e.g. "which chapter is this player
  on"). It does not: this is a one-way STAT/TELEMETRY ping from the client to
  a backend, keyed on the player's own NpId, with no friend-list or presence
  API involved anywhere in either call site. The two confirmed lines:

    stat %s task-%x %s %s\n     (campaign-save path, FUN_007f1acc @ 0x007f1acc)
    stat %s trophy-%x\n         (trophy-unlock path, FUN_00080268 @ 0x00080268)

  LIVE-CONFIRMED 2026-08-21: single-player-server had never once opened a
  connection across 452 prior captured hellos. It finally spoke during a
  real campaign session - two trophy unlocks first ("stat comradesean
  trophy-2f\n" and "stat comradesean trophy-2d\n"), then, after this session's
  campaign.config.txt.crypt fix (see the task-line doc below and
  research/notes/2026-08-21-stat-line-config-writer-trace.md), the
  campaign-save line itself:

      stat comradesean task-7d9d7acc BCUS98174 HD

  All three captures match the decompile-derived grammars byte-for-byte.
  BOTH lines of this proto are now live-confirmed. Handler:
  server/ticket_server.py's handle_single_player/build_stat_response.

  Both format strings were recovered by resolving the TOC-relative string
  constant each call site passes to the shared formatter _opd_FUN_00e46670
  (same anchor+displacement addressing documented in
  research/tools/eboot_analysis/README.md): "stat %s task-%x %s %s\n" lives at
  0xe9d178 (anchor 0x012fe508 -> 0x0128b390, slot -0x7ea8); "stat %s
  trophy-%x\n" at a second, independent compilation-unit anchor (0x012fd9dc ->
  0x0125f4c0, slot -0x7fa0). All addresses are 01.00 VMAs.

  FIELD MEANINGS, task line (all confirmed by tracing FUN_007f1acc):
    %s (1st) = the player's own online_id, from sceNpManagerGetNpId - same
        source as every other sibling service's identity field.
    %x       = param_1[0x1b]. CORRECTED 2026-08-19 (twice now): an earlier
        pass of this doc guessed a "shared connection/job-id" reading from
        the read-site idiom's recurrence alone, without finding an actual
        writer. A writer was then found (`FUN_0032241c`,
        research/ghidra/fm_applyrefs.txt) and its DC-table lookup mechanism
        traced to `net1.bin`/`net10.bin` this session (see
        `docs/protocol/dc_table.md` for the container format those files
        use). That trace REVISES the "task/objective-definitions table"
        reading down to something narrower and more surprising:

        `FUN_0032241c` builds a UI reward/notification-popup descriptor, not
        a task-definitions record. It resolves THREE separate DC base
        tables via `_opd_FUN_0078b5a0(materialCollection, hash)` - hash
        `0xD006E7B5` (populates struct indices `0x19`,`0x1a`,`0x1d`-`0x20`,
        `0x2e`,`0x2f`; NOT `param_1[0x1b]`'s siblings - the earlier doc's
        sibling list was wrong, those belong to a different base hash than
        the one `0x1b` uses), `0x1AD3445F` (the hash this proto cares about
        - populates `0x1b`,`0x1c`,`0x21`,`0x23`-`0x2b`,`0x2d`,`0x30`), and
        `0x4240EF2E` (untraced this session). Each resolved table is then
        looked up per-field via `_opd_FUN_00ab685c(table, keyPointer)` -
        and `_opd_FUN_00ab685c` is a STRING lookup (calls string-compare
        helpers, does a binary search keyed on `strlen`+`memcmp`-shaped
        calls), not a hash lookup as the prior pass assumed. The `keyPointer`
        arguments are literal compile-time C-string pointers baked into the
        EBOOT; resolving the actual TOC slot used for `param_1[0x1b]`'s key
        (`puVar8 + -0x7ee8` in the Ghidra decompile, confirmed against the
        raw disassembly at `0x322794`/`0x322780`) and reading the string at
        that address gives: **`"general/hud/prize-icon/Default"`**.

        So `0x1ad3445f`'s DC00 table (found literally 39 times in net1.bin,
        76 times in net10.bin, per the earlier handoff note's grep) is a
        **HUD material/icon-path lookup table** - string-keyed by asset
        paths like `general/hud/prize-icon/Default`,
        `general/hud/alpha-icon24/default`, `general/hud/spinner/default`,
        etc. (the other 13 key strings resolved for this struct's sibling
        fields are all in the same `general/hud/...` family) - NOT a
        task/objective-id table. `param_1[0x1b]`, and therefore `task-%x`,
        is whatever integer value that table associates with the literal
        key `"general/hud/prize-icon/Default"` (`_opd_FUN_00ab685c` returns
        an array index; the value itself is `*(index*4 +
        *(table+0x18))`). Since the key string is a compile-time constant
        for this call site, every `task-%x` line this specific code path
        produces very likely reports the SAME resolved id (this function's
        `param_3` context can still vary the icon *table instance*, e.g. a
        per-DLC or per-collection material set, so it's not necessarily a
        single global constant across all builds/regions - untested).

        This is a genuine, container-format-confirmed correction, not a new
        guess: the hash's literal on-disk hits were located in
        `net1.bin`/`net10.bin` via `docs/protocol/dc_table.md`'s parser, and
        the string read at the resolved TOC slot is a real EBOOT C string,
        not inferred.

        LIVE-CONFIRMED 2026-08-21: the campaign-save line was captured for
        the first time ever (after 2 prior LIVE-CONFIRMED trophy lines but
        zero task lines, following the `campaign.config.txt.crypt` fix - see
        `research/notes/2026-08-21-stat-line-config-writer-trace.md`):

            stat comradesean task-7d9d7acc BCUS98174 HD

        `%x` = `0x7d9d7acc` in this live capture - the resolved integer id
        for `"general/hud/prize-icon/Default"`.

        CORRECTED 2026-08-21/22, DISPROVEN BY SIX MORE LIVE SAMPLES: the
        "very likely the same id across every call from this code path"
        prediction above was wrong. The same continuous campaign session
        (chapter 1 into chapter 2) produced FIVE more task lines, all still
        `comradesean`/`BCUS98174`/`HD`, with a DIFFERENT `%x` every single
        time:

            stat comradesean task-7d9d7acc BCUS98174 HD
            stat comradesean task-ad611b77 BCUS98174 HD
            stat comradesean task-1ca07d2f BCUS98174 HD
            stat comradesean task-8f436eab BCUS98174 HD
            stat comradesean task-f72c7bf9 BCUS98174 HD
            stat comradesean task-a3dd87ca BCUS98174 HD

        Full trace: `research/notes/2026-08-21-task-hash-variation-trace.md`.
        Summary of what changed:

        - Hash-crack attempt on all six values, against this project's
          widest assembled corpus (`bin.psarc` + `paks.txt` + `pak23.txt` +
          `banks.txt` + both `*-audio-precache.txt` manifests, tried against
          both the 01.00 and 01.11 local installs): **0/6 cracked**. No
          direct string recovery for `task-%x` yet.
        - Re-reading `FUN_0032241c`'s `0x1AD3445F` block found a
          **memoization gate** the original pass missed: `param_1[0x1b]`
          (and 13 sibling fields, including `param_1[0x1c]` which doubles as
          the gate's own sentinel) is only (re)computed from the table when
          `param_1[0x1c] == 0` on entry - otherwise the previously-resolved
          value is left untouched, and if the underlying table has gone
          invalid the whole group is explicitly zeroed (including
          `param_1[0x1c]`, re-arming the gate for next time).
        - Confirmed independently this pass (not just re-trusting the
          byte-offset coincidence): `param_1` in this whole chain IS the
          same one-shot-constructed save-manager SINGLETON that GATE 1's
          throttle/ip/port fields already live on (`FUN_007f1acc` reads
          `+0x1390`/`+0x138c` [port/ip] and `+0x6c` [`task-%x`'s source] off
          the identical base register, `r31`, in the same instruction
          block). Since it's a singleton constructed once per process
          lifetime, the value can only change across a session if
          `FUN_0032241c` runs more than once AND finds the gate reset to `0`
          each time.
        - The "`param_3` selects the table instance" theory is DISPROVEN as
          literally stated: the `0x1AD3445F` table resolution
          (`_opd_FUN_0078b5a0`) reads its "materialCollection" argument from
          a fixed anchor-relative TOC slot (`anchor-0x7f0c`), never from
          `param_3`. That slot's stored value (`0x013e2f28`) is a single
          fixed heap/BSS-resident singleton, the same one every call.
        - BUT reading what that singleton's lookup function
          (`_opd_FUN_0078b5a0`, `0x0078b5a0`) actually does revealed a
          **5-slot dynamic module registry**: it linearly scans up to five
          registered "collection module" pointers (`object+8`, stride 8) and
          matches whichever slot's own `+0x64` hash field equals the
          requested hash. So which physical module answers a hash query
          like `0x1AD3445F` can change over a session if different modules
          get registered/deregistered into those slots - the natural driver
          of which, in a game engine, is level/chapter content streaming. No
          `param_3` selector exists, but a same-family dynamic mechanism
          does, and it's the only thing in the whole trace capable of making
          a fixed key ("general/hud/prize-icon/Default") answer differently
          over time.
        - No second writer to `param_1[0x1b]` was found in the two functions
          actually on this call path; a fully exhaustive project-wide
          type-aware scan for other writers was not re-run this pass (the
          existing single-writer result, `research/ghidra/fm_applyrefs.txt`,
          was taken at face value rather than independently reproduced).

        **Verdict, stated at the confidence it deserves**: the "per-autosave
        location/checkpoint identifier" hypothesis is CORROBORATED, not
        proven - refined to "`task-%x` is the resolved id of a fixed
        UI-reward-popup icon key, looked up against whichever content module
        is currently registered for that key's table; it tracks campaign
        progress indirectly through content-streaming state, not as a
        literal location id." No cracked string confirms this outright.
        Next step is a live test (breakpoint `FUN_0032241c` and the
        materialCollection registry across a real multi-save session,
        correlating gate resets and slot-pointer identity against `task-%x`
        changes and the in-game chapter at each save) - not yet run; full
        plan in the trace note above.

        RECONCILED 2026-08-22, against a real live read that at first looked
        like a contradiction: a live breakpoint hit on FUN_007f1acc's entry
        (same session, same singleton 0x44148220) read `this+0x6c` (task-%x's
        source) = 0x583AC2EE and `this+0x70` (the cache-gate field) = 0x0 -
        i.e. a NONZERO value with a ZERO gate, which the two-state model
        above (gate==0 implies value==0 too, either "never computed" or
        "explicitly invalidated") does not cover. Also present in the same
        live memory nearby: PS3 save-directory-listing-shaped bytes
        ("USR-DATA", "ICN-ID", "ICON0.PNG", repeating timestamp quads) that
        looked like they might mean `+0x6c` had been reinterpreted as a
        pointer into a cellSaveDataListGet-style buffer rather than the plain
        scalar this doc claims. Full re-trace:
        research/notes/2026-08-22-task-x-offset-reconciliation.md. Verdict on
        both questions, from the raw disassembly and the full Ghidra
        decompile (not the prior notes' paraphrases):

        - **`this+0x6c` is confirmed, directly from the disassembly, to be
          consumed as a raw 32-bit integer with zero indirection.** Traced
          every instruction from `lwz r29,108(r31)` (0x7f1cf4) to the
          formatter call (0x7f1d44, `bl 0xe46670`): r29 is never reloaded,
          never dereferenced, never used as a base register - the only thing
          done to it is `clrldi r6,r29,32`, a plain zero-extend, immediately
          before it becomes the `%x` argument. The "what if it's a pointer or
          index" hypothesis is disproven outright: there is no dereference on
          this path at all.
        - **The flag=0/value-nonzero combination is not a third state or an
          offset error - it's the fully expected result of the gate field's
          real nature.** Re-reading `research/ghidra/fm_applyrefs.txt`'s
          literal source (not the earlier paraphrase) shows `param_1[0x1c]`
          (`this+0x70`) is written by the EXACT SAME
          `_opd_FUN_00ab685c(table,key) -> table[index]` idiom as
          `param_1[0x1b]` and the other 12 siblings, using its own key (TOC
          slot `puVar8-0x7ed8`) - it is not a separate boolean/sentinel
          constant, it IS one of the 14 resolved values, which also happens
          to double as the "already resolved" gate. If that specific key
          currently resolves to the integer `0` (exactly what was read live
          tonight), the group write still completes in full - `this+0x6c`
          legitimately holds a freshly-resolved nonzero id - but the gate
          field itself, being `0`, can never be observed as "already
          resolved" on a later call. Net effect: for as long as that one
          sibling key answers `0`, `FUN_0032241c` redoes the ENTIRE 14-field
          lookup from scratch on every single call - the "memoization" this
          doc described upstream is real code but structurally never
          engages this session, which sharpens (not contradicts) the 5-slot
          dynamic-module-registry theory above: it's now the sole remaining
          explanation for why the resolved value differs call to call, since
          no caching effect is actually suppressing recomputation here.
        - **The save-listing-shaped bytes are a different field of the same
          singleton, not `this+0x6c`/`this+0x70`.** The full 14-field HUD-icon
          group this object's `0x1AD3445F` block populates spans byte range
          `this+0x6c` through `this+0xc0` (dword indices 0x1b-0x30)
          inclusive, and every one of those 14 fields is a plain scalar per
          the decompile - no pointer, no buffer base, anywhere in that range.
          The save-manager singleton (`FUN_007f149c`,
          `gamelib/save/saveworker.cpp`, 5024 bytes, same live address) is
          the actual campaign-autosave manager, so it plausibly owns a real
          `cellSaveDataListGet`-style directory buffer as some OTHER field in
          its remaining ~4900 bytes for its real job of slot/icon/timestamp
          bookkeeping - unsurprising and not in conflict with the `task-%x`
          mapping. This pass did not locate that field's exact offset
          (outside this proto's scope); see the reconciliation note's
          live-test spec for what would pin it down precisely.

        Both original open questions (item 1: is `+0x6c` really the direct
        source; item 3: does the flag model hold) are now resolved from
        static analysis alone. What's still open is unchanged from the prior
        entry: which module the 5-slot registry currently has registered for
        `0x1AD3445F`, and whether it actually correlates with chapter
        transitions - that still needs the live test already specified above.
    %s (2nd) = _opd_FUN_00952520(**(anchor-0x7f3c)) - RESOLVED 2026-08-19 to a
        MECHANISM, not a value: the "function" is a 3-instruction accessor
        (`addi r3,r3,0x2e6c; clrldi r3,r3,32; blr`, i.e. `return base +
        0x2e6c`), so this is a string field at offset 0x2e6c of some global
        object. The object's address is reached through a double pointer
        indirection whose final hop (0x01441194) falls outside the static
        file image - i.e. it is a runtime-allocated (heap/BSS-resident)
        object, not static data.

        LIVE-CONFIRMED 2026-08-21: this field's value is **`BCUS98174`** -
        the title's own PS3 product/serial code (see the same live capture
        above). Makes sense in hindsight for a heap-resident string this
        project couldn't point at statically: it's a per-title constant
        baked in at runtime init, not a save-specific computed value.
    %s (3rd) = one of two fixed 2-byte string literals chosen by a size/
        threshold comparison (`*(uint*)(anchor-0x7eb4) < 0x2d0`): "SD" (slot
        anchor-0x7eac, 0xe9d170) or "HD" (slot anchor-0x7eb0, 0xe9d168). Reads
        as a save-icon/screenshot resolution or storage-medium tag attached to
        the campaign autosave the stat line accompanies.

        LIVE-CONFIRMED 2026-08-21: the same capture above resolved to
        `"HD"`, matching the predicted enum exactly (one of exactly the two
        values the decompile said were possible).

  FIELD MEANINGS, trophy line (fully confirmed - both args traced to source):
    %s = the player's own online_id (same sceNpManagerGetNpId call).
    %x = the trophy id passed into sceNpTrophyUnlockTrophy just before this
        line is built (param_4 in FUN_00080268's lVar10==1 branch) - a direct,
        unambiguous trophy identifier.

  WHY THIS RULES OUT THE "FRIENDS SEE YOUR CHAPTER" HYPOTHESIS: both call
  sites run entirely inside save-sync (cellSaveDataListSave2/AutoSave) and
  trophy-unlock (sceNpTrophyUnlockTrophy) event handlers. Neither reads a
  friend list, neither touches sceNpBasic/presence APIs, and the destination
  is a private stat-collection backend (single-player-server), not a
  presence/rich-status service any other player's client could observe. The
  data these lines carry - task/objective completion and trophy unlocks tied
  to one account - is consistent with backend analytics or population-level
  completion tracking, not peer-visible progress.

  A stub server needs to do nothing but accept the connection and not close
  first, exactly like gamelist_line - the client does not read the reply.

  GATE CONDITIONS ON THE task-%x LINE - found 2026-08-21, in answer to two
  real, deliberate campaign-save events (an autosave and a manual pause-menu
  save) producing zero connections despite the server running and logging.
  Full trace: research/notes/2026-08-21-stat-line-save-gate-investigation.md.
  Re-reading FUN_007f1acc's own body (not just its format-string resolution)
  finds the send is gated, stacked, by:

    GATE 0  *(char*)(param_1+0x68) must be 0, or the ENTIRE notify branch -
            not just the send - is skipped in favor of a bare
            cellSaveDataListAutoSave with no attempt of any kind. Writer(s)
            not traced; plausibly a save-reason (autosave vs. explicit)
            selector, unconfirmed.
    GATE 1  param_1[0x4e1] (a throttle modulus N) > 0, param_1[3] >= 0 (valid
            save slot), and param_1[0x4e3]/param_1[0x4e4] (single-player-
            server's resolved ip/port) both nonzero - static config-present
            checks.
    GATE 2  param_1[0x4e0] (a counter, mod param_1[0x4e1]) must equal exactly
            0 - a genuine one-attempt-per-N-qualifying-saves THROTTLE. The
            counter advances on every qualifying save regardless of whether
            an attempt was made or succeeded, so one failed attempt at
            counter==0 pushes the next opportunity N saves further out.
    GATE 3  sceNpManagerGetNpId() must return 0 - a live NP/online-state
            precondition. Ties directly to this account's documented RPCN
            instability (research/notes/rpcn-connection-instability.md): a
            client mid-disconnect-cycle, or one that hasn't completed an NP
            login this boot, fails this check and the notify attempt is
            skipped for that save (though GATE 2's counter still advances).
    GATE 4  FUN_00acc424 (the same shared connect+hello handshake documented
            in docs/protocol/0x11_ticket_server_hello.md, which performs the
            raw connect() internally as its first step) must return 0. On
            failure, FUN_007f1acc takes a local-only fallback log call
            (_opd_FUN_007f0864) with NO network send and no visible error -
            a silent absorb, not a crash or retry.

  Net effect: GATE 2 (throttle) and GATE 3 (NP-state) together are sufficient
  to explain the observed silence without assuming anything is broken - the
  send is neither guaranteed on every save nor guaranteed to succeed when
  attempted. What's NOT resolved statically: GATE 0's writer(s) and the
  actual thread-spawn call site(s) for FUN_007f1acc itself (a full-image
  search for both its VMA and its .opd descriptor address found zero
  references, so the call site's own addressing idiom is not one this
  project's current static tools cover).

  GATE 1's WRITER, FOUND 2026-08-21 (research/notes/2026-08-21-stat-line-config-writer-trace.md):
  a live RPCS3 breakpoint at FUN_007f1acc's entry during a real autosave read
  the save-manager singleton (fixed live address 0x44148220 this session) and
  found counter=0, modulus=0, ip=0, port=0 at the moment of a genuine save -
  GATE 1 failing not from timing but because these fields had NEVER been
  populated. Tracing the writer statically: param_1[0x4e1]/[0x4e3]/[0x4e4] are
  written exactly once, by FUN_007f149c (0x007f149c), the save-manager's own
  constructor (gamelib/save/saveworker.cpp, same literal-pool anchor as
  FUN_007f1acc). The object is a confirmed lazy-constructed SINGLETON: exactly
  one `bl 0x7f149c` exists in the whole image (0x7ef9dc), guarded by a
  one-shot "already initialized" flag, allocating a 5024-byte
  (param_1[0x4e4]'s offset + slack) block immediately before constructing it -
  matching the live observation of the same object address across two
  breakpoint hits.

  The constructor's population of these three fields is itself double-gated:
  (1) sceNpManagerGetNpId() must succeed (0x7f1678-0x7f1688: failure skips the
  ENTIRE config block, leaving the zero-init from 0x7f1664-0x7f1674
  permanent), then (2) a live HTTP GET+decrypt of
  "<base>/campaign.config.txt.crypt" (default base
  "http://t1.campaign.config.s3.amazonaws.com") via the shared download
  function FUN_00ac5b40 must return >0 (0x7f16dc-0x7f16e8: failure skips the
  same way). Even on a successful download, the modulus specifically is
  double-gated again: a parsed config key must read as a "1"-valued toggle
  string, or the code deliberately resets the modulus back to 0
  (0x7f1768-0x7f1774) even though the download succeeded.

  LIVE-CORROBORATED, not just decompiled: server/http_gateway.py intercepts
  t1.campaign.config.s3.amazonaws.com, its real upstream bucket is dead, and
  it falls back to an EMPTY 200 OK body. server/logs/http_gateway.log shows
  the client requesting GET /campaign.config.txt.crypt and receiving that
  empty-body failure response repeatedly, including at 2026-08-21T21:58:48
  and :50 - directly bracketing the same session's live breakpoint read. An
  empty body cannot decrypt/parse, so FUN_00ac5b40 returns <=0, and every
  field this constructor would populate stays at its zero-init value for the
  rest of the process's life (one construction, confirmed singleton). This
  fully explains the live zero-read: not RPCN flakiness, not throttle
  timing, but a dead external S3 dependency this constructor's download
  depends on, which this project's HTTP gateway cannot presently satisfy.

  IMPORTANT: single-player-server's ip/port do NOT resolve through the same
  net1.bin/net10.bin hostname-table + DNS-redirect mechanism the other
  sibling services (heartbeat-server, leaderboard-server, etc.) use. They are
  parsed as plain integer fields OUT OF the downloaded campaign.config.txt
  content itself - a completely separate, S3-download-gated mechanism wired
  up only for this one field. Once GATE 1 (this config download) passes, the
  actual connection at GATE 4 still goes through the same shared
  FUN_00acc424 hello handshake every sibling uses - only the SOURCE of the
  {ip,port} pair differs, not how it's used afterward.

  RESOLVED AND DEPLOYED 2026-08-21 (same session, minutes later): the
  "not resolved this pass" note above was wrong to call this format unknown
  - it is the SAME container this project already fully cracked for
  userdata/<id>.txt.crypt, documented and tooled in
  server/lib/userdata_crypt.py, which explicitly names
  campaign.config.txt.crypt as a sibling of the same format:

      [ BE u32 plaintext_length ]
      [ 20-byte HMAC-SHA1(HMAC_KEY, padded_body) ]   <- both PLAINTEXT
      [ Blowfish-ECB(padded_body) ]

  with a STATIC, title-wide Blowfish/HMAC key pair (not per-session, not
  digest-pinned by the caller) - so the earlier "may be HMAC/digest-pinned
  against a value only Naughty Dog/Sony has" worry does not apply here; the
  same key this project already uses for net1.bin.psarc.crypt etc. works.
  The real retail plaintext for this file family was already decrypted back
  on 2026-08-17 (research/notes/2026-08-17-userdata-txt-crypt-format.md):

      queue-server-addr 50.18.47.114
      queue-server-port 7320
      interval 10
      enable 1

  (`queue-server-port` matching this project's own ticket_server/
  single-player-server listener port, 7320 - not a coincidence, since GATE 4
  connects to this exact {ip,port} via the same FUN_00acc424 hello
  handshake). A replacement file was built and deployed this session:

      python3 server/lib/userdata_crypt.py build \
          server/data/served_content/campaign.config.txt.crypt \
          queue-server-addr=192.168.1.100 queue-server-port=7320 \
          interval=10 enable=1

  Verified HMAC OK on decode, round-trips byte-for-byte. server/http_gateway.py
  always prefers a local file over its upstream-fetch fallback
  (build_response()'s `os.path.isfile(file_path)` check runs before any
  upstream attempt), so this now serves in place of the empty-body failure
  that caused tonight's live zero-read.

  LIVE-VERIFIED END-TO-END 2026-08-21, SAME NIGHT: a fresh RPCS3 boot picked
  up the new file and GATE 1 passed for real - six separate task-%x sends
  across one continuous campaign session (chapter 1 through the start of
  chapter 2), all well-formed, all replied-to and closed cleanly by
  handle_single_player. The "interval"->modulus / "enable"->toggle field
  mapping is therefore confirmed WORKING in practice (the notify path fires
  repeatedly, not just once), even though the exact _opd_FUN_00ada358
  key-lookup call sites were never individually re-verified - functional
  confirmation stands in for that instruction-level check.

  RUNNING LOG OF LIVE task-%x CAPTURES (all account comradesean, all
  BCUS98174/HD, one continuous chapter-1 -> chapter-2 campaign session,
  2026-08-21 night):

      23:24:08  task-7d9d7acc
      (unlogged connection between the two timestamps below - six total
       sends, five timestamps captured in this pass)
      23:35:00  task-1ca07d2f
      23:40:58  task-8f436eab
      23:46:21  task-f72c7bf9
      23:52:47  task-a3dd87ca

  All SIX values differ - see the %x field doc above and
  research/notes/2026-08-21-task-hash-variation-trace.md for the
  investigation into why (a live prediction that this code path would
  report the SAME id every time, made earlier in this same doc, is
  contradicted by this data - being corrected in place, not silently
  removed, so the reasoning trail stays visible).

  SEVENTH CAPTURE, 2026-08-22 00:59:41, DIRECTLY CORRELATED AGAINST THE
  THROTTLE GATE this time (not just observed after the fact): a live RPCS3
  breakpoint session tracked the GATE 2 throttle counter
  (param_1[0x4e0]/+0x1380) across several consecutive FUN_007f1acc hits on
  the SAME singleton (0x44148220, unchanged all night):

      counter=8 (modulus=10) -> no send, GATE 0 read 0 (pass) on this hit too,
                                 ruling out a distinct "profile save" gate as
                                 the reason for the frequent non-reporting hits
      counter=9              -> no send (predicted, confirmed live)
      counter=0              -> SENT: stat comradesean task-e4c65aa7 BCUS98174 HD

  This is the cleanest live confirmation yet of the GATE 2 mechanism: the
  counter was read directly at three consecutive qualifying-save hits,
  advanced by exactly 1 each time as predicted, and the transition to 0
  produced a real send within the same debugging session - not inferred
  from log timing alone. task-e4c65aa7 is a SEVENTH distinct value, further
  reinforcing that this field is not a fixed constant for this code path.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: line
    type: str
    size-eos: true
    doc: "One of the two grammars above, newline-terminated. No further framing beyond the shared encrypt-then-MAC 0x33 layer (see 0x11_ticket_server_hello.md)."
