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
    %x       = param_1[0x1b]. RESOLVED 2026-08-19 to a MECHANISM, not yet a
        firm semantic: this exact offset is read with the identical idiom
        (`uVarNN = param_1[0x1b]`, immediately adjacent to a call into the
        shared connect routine _opd_FUN_00acc424) in several otherwise-
        unrelated service handlers - leaderboard's and find-match's own
        connection-state structs, not just this one. That recurrence across
        independently-compiled handlers is consistent with 0x1b being a
        common field of a shared per-connection/per-async-job state struct
        (a generic ND job/task-dispatch id), not a campaign objective id -
        which would also explain the literal "task-" prefix without requiring
        gameplay-specific state. Not fully proven: no single writer of this
        field was traced to confirm it, only the read-site idiom's recurrence.
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
