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
        not inferred. What remains open: the actual integer VALUE associated
        with `"general/hud/prize-icon/Default"` in a live-resolved table
        (a runtime read, not a static one, since the lookup goes through the
        engine's runtime hash-registry rather than a raw file offset this
        project can point at with full confidence - see
        `protos/common/member_data.ksy`'s `rank_tier` doc for why that
        registry's file-offset correspondence is not fully nailed down
        either). High confidence on the mechanism and the key string; open
        on the resolved numeric value.
    %s (2nd) = _opd_FUN_00952520(**(anchor-0x7f3c)) - RESOLVED 2026-08-19 to a
        MECHANISM, not a value: the "function" is a 3-instruction accessor
        (`addi r3,r3,0x2e6c; clrldi r3,r3,32; blr`, i.e. `return base +
        0x2e6c`), so this is a string field at offset 0x2e6c of some global
        object. The object's address is reached through a double pointer
        indirection whose final hop (0x01441194) falls outside the static
        file image - i.e. it is a runtime-allocated (heap/BSS-resident)
        object, not static data. DC/RUNTIME-BLOCKED: the field's content
        cannot be recovered by static analysis alone; a live memory read
        (debugger or emulator) at that address while a save is in flight
        would close this.
    %s (3rd) = one of two fixed 2-byte string literals chosen by a size/
        threshold comparison (`*(uint*)(anchor-0x7eb4) < 0x2d0`): "SD" (slot
        anchor-0x7eac, 0xe9d170) or "HD" (slot anchor-0x7eb0, 0xe9d168). Reads
        as a save-icon/screenshot resolution or storage-medium tag attached to
        the campaign autosave the stat line accompanies - not independently
        confirmed.

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
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: line
    type: str
    size-eos: true
    doc: "One of the two grammars above, newline-terminated. No further framing beyond the shared encrypt-then-MAC 0x33 layer (see 0x11_ticket_server_hello.md)."
