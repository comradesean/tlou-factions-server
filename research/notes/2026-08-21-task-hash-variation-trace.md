# Why `task-%x` varies across six live captures despite tracing to a compile-time-constant key

Date: 2026-08-21/22. Follow-up to the six live `task-%x` captures from one
continuous campaign session (chapter 1 through the start of chapter 2, all
account `comradesean`):

    stat comradesean task-7d9d7acc BCUS98174 HD
    stat comradesean task-ad611b77 BCUS98174 HD
    stat comradesean task-1ca07d2f BCUS98174 HD
    stat comradesean task-8f436eab BCUS98174 HD
    stat comradesean task-f72c7bf9 BCUS98174 HD
    stat comradesean task-a3dd87ca BCUS98174 HD

`protos/0x11_stat_line.ksy`'s existing doc traces `%x` to `param_1[0x1b]`,
populated by `FUN_0032241c` via a STRING-keyed lookup
(`_opd_FUN_00ab685c(table, keyPointer)`) against DC table `0x1AD3445F`, where
`keyPointer` resolves to the literal C-string `"general/hud/prize-icon/Default"`
- a compile-time constant. That doc predicted every `task-%x` from this path
"very likely reports the SAME resolved id". The six captures disprove that
prediction outright: only the `%x` field ever changes, across six consecutive
autosaves.

This note is static-only (no live RPCS3 session run this pass), per the
task's own framing - the current state of the trace narrows the mechanism
enough that a live test is the clear next step, described at the end.

## Part 1: hash-crack results - all six MISS

Ran `research/tools/dc_hash_crack.py` against the widest corpus this project
has assembled to date (per `research/notes/2026-08-20-followup-open-items.md`
§2 and `research/notes/2026-08-21-promotion-flags-angles-2-3.md`'s "Widened
hash-crack corpus" section): `bin.psarc`'s `.dci` symbol corpus plus
`paks.txt` + `pak23.txt` + `banks.txt` + `rulebook-audio-precache.txt` +
`ss-audio-precache.txt` (50,676 unique candidate tokens), run against BOTH
local installs (01.00 disc and the 01.11 patched install's own `build/main`,
in case a later build's `.dci`/manifest set carried a matching token - both
installs produced byte-identical corpora and results):

```
0xad611b77	NO MATCH
0xf72c7bf9	NO MATCH
0xa3dd87ca	NO MATCH
0x8f436eab	NO MATCH
0x7d9d7acc	NO MATCH
0x1ca07d2f	NO MATCH
```

**0 of 6 cracked.** Consistent with this corpus's established blind spots
(documented in both source notes): `pak23.psarc` (10.8 GB) and
`actor34.psarc` (1.9 GB) still can't be parsed in practical time, and no
01.11 `text1.psarc` is available locally. No direct string recovery for
`task-%x` this pass. This also means the "a cracked hash names an actual
level/checkpoint" strongest-possible-confirmation path is NOT available yet -
the verdict below rests entirely on the dynamism trace (Part 2).

## Part 2: what's actually dynamic - the caching gate and the module registry

### Re-reading `FUN_0032241c`'s `0x1AD3445F` block found a caching/memoization gate the prior pass didn't note

Full decompile: `research/ghidra/fm_applyrefs.txt`. The relevant shape
(all three hash groups in this function follow the same pattern; this is the
`0x1AD3445F` one that reaches `param_1[0x1b]`):

```c
iVar12 = _opd_FUN_0078b5a0(*(puVar8 + -0x7f0c), 0x1ad3445f);   // resolve table
uVar9 = <table-valid flag, from *(iVar12+0x20) bit 3>;

if (param_1[0x1c] == 0) {                    // <-- CACHE-VALID GATE
    if (uVar9 != 0) {
        /* fresh lookup: param_1[0x1b] = table[key("general/hud/prize-icon/Default")] */
        /* ...13 sibling fields resolved the same way, including... */
        param_1[0x1c] = uVar13;              // <-- ALSO the gate's own value
    }
} else if (uVar9 == 0) {
    /* table became invalid: zero out param_1[0x1b], 0x1c, and 12 siblings */
    param_1[0x1b] = 0; param_1[0x1c] = 0; /* ...12 more fields... */
}
/* else (param_1[0x1c] != 0 AND uVar9 != 0): do nothing - keep the cached value */
```

`param_1[0x1c]` does double duty: it is itself one of the 14 sibling fields
resolved from the same table (key at anchor slot `-0x7ed4`), **and** it is
read first as a "have I already resolved this group" sentinel. The practical
effect: **`param_1[0x1b]` is only (re)computed from the table on a call where
the cache is empty (`0x1c == 0`)** - either the object's first-ever
population, or immediately after an invalidation reset zeroed it back to 0.
On every other call, while the table stays valid, the existing value is left
untouched. This is a genuine memoization pattern the earlier pass's doc did
not identify - it was reading the write site as an unconditional recompute.

### Confirmed this pass: `param_1` in `FUN_0032241c`/`FUN_007f1acc` is the SAME persistent save-manager singleton, not a per-event object

This matters because a memoized value on a **freshly-allocated-per-event**
object would recompute every time trivially (no puzzle); a memoized value on
a **long-lived singleton** only recomputes when something explicitly
resets it - which is the more interesting and more falsifiable claim, so it
was worth re-verifying independently rather than trusting the byte-offset
coincidence.

Re-reading `FUN_007f1acc`'s own read site (`research/disasm/full.asm`,
01.00 VMAs) settles it:

```
7f1ccc: lwz r5,5008(r31)   ; +0x1390 = savemgr port   (GATE 1 field)
7f1cd0: lwz r4,5004(r31)   ; +0x138c = savemgr ip      (GATE 1 field)
...
7f1cf4: lwz r29,108(r31)   ; +0x6c  = param_1[0x1b], the task-%x source
```

`r31` here is the exact same base register the config-writer-trace note
(`research/notes/2026-08-21-stat-line-config-writer-trace.md`) already
proved is the save-manager singleton (`+0x1384`/`+0x138c`/`+0x1390` =
throttle modulus/ip/port, one lazy construction, one object for the process
lifetime, live-observed at `0x44148220`). The `task-%x` read (`+0x6c`) sits
in the SAME instruction block, off the SAME `r31`, immediately after two of
that singleton's own already-proven fields are read - not a coincidental
offset match on an unrelated object. **`param_1[0x1b]` is a field of the
one-shot-constructed save-manager singleton, confirmed independently this
pass, not re-derived from the older doc's byte-offset-only inference.**

(`FUN_0032241c`'s own `param_1` argument arrives via its only found caller,
a wrapper at `0x334294` that passes `param_1 = (wrapper's r3) + 0x10` - a
constant `this`-adjustment consistent with a multiple-inheritance thunk
rather than a different object; the wrapper itself has zero discoverable
direct callers, the same "call site outside this project's current static
addressing coverage" pattern already documented for `FUN_007f1acc`'s own
thread-spawn site.)

**Consequence:** since this is a singleton constructed exactly once per
process lifetime, `param_1[0x1b]`/`task-%x` can only differ across six saves
in one continuous session if `FUN_0032241c` ran more than once in that
session AND found the cache flag (`param_1[0x1c]`) reset to `0` on each
re-run - i.e. something invalidated and re-armed the cache between saves.

### Theory 1 (param_3 selects the table instance) - disproven as literally stated, but its underlying idea is independently supported by a different mechanism

Traced the exact table-resolution call for the `0x1AD3445F` group:

```
3224c8: lis  r4,-12282        ; hash immediate, high half
3224cc: lwz  r3,-32524(r30)   ; r3 = *(anchor-32524) -- FIXED slot, NOT param_3
3224d0: ori  r4,r4,59317      ; -> 0xD006E7B5 (a *different* hash group)
3224d4: bl   0x78b5a0         ; _opd_FUN_0078b5a0(materialCollection, hash)
```

(same pattern repeats for `0x1AD3445F` a few lines later at `0x322794`, per
the existing doc). `r3` (the "materialCollection" argument) is loaded from a
fixed anchor-relative TOC slot every time - **`param_3` is never read for
this call**; `param_3` is used elsewhere in the function (`param_1[0x31] =
param_3`, and reading `*(param_3+0x480..0x48c)` into other fields), but not
here. Resolved the slot's actual stored value:

    anchor 0x0126ef94 - 0x7f0c = 0x01267088, contents = 0x013e2f28

`0x013e2f28` is outside both static LOAD segments (`0x10000..0x11fac68` and
`0x11f0000..0x13231d0`) - a heap/BSS-resident singleton address, same
pattern as every other runtime-constructed global this project has already
identified (the netsession object at `0x01441194`, the promotion register at
`0x01459260`, etc). **So the collection selected is a single fixed global
object, always the same one, every call - the literal "`param_3` picks the
instance" theory is disproven for this call site.**

But reading what `FUN_0078b5a0` (`0x0078b5a0`) actually does with that
object reveals a different, still-dynamic mechanism:

```
78b5b0: li   r0,5          ; loop 5 times
78b5bc: mtctr r0
78b5d0: addi r26,r3,8      ; slot array starts at object+8, stride 8
78b5e8: add  r9,r10,r26
78b5f4: ld   r11,0(r9)     ; slot pointer
78b5f8: cmpdi cr7,r11,0
78b5fc: bne  cr7,0x78b6ec  ; nonzero slot -> check its hash
78b600: addi r8,r8,1
78b604: bdnz 0x78b5e8      ; next slot
...
78b620: lwz  r0,100(r11)   ; candidate module's own hash field, +0x64
78b624: cmpw cr7,r0,r25    ; compare against the requested hash (r25 = param_2)
```

This is a **5-slot linear-scan module registry**, not a flat static table:
the singleton holds up to five registered "collection module" pointers, and
`FUN_0078b5a0` finds whichever currently-registered slot's own `+0x64` hash
field matches the requested `0x1AD3445F`. Nothing here is param_3-driven,
but the registry's *contents* - which physical module currently answers a
given hash - are exactly the kind of thing a level/chapter-scoped content
stream would rewrite as chapters load and unload their own HUD-material
overlay modules. A module carrying the SAME registration hash
(`0x1AD3445F`, i.e. still nominally "the hud materials table") could very
plausibly be swapped for a different chapter-specific module with a
different set of key->id mappings behind the identical
`"general/hud/prize-icon/Default"` key - the compile-time-constant key would
keep resolving through the registry lookup unchanged, while the *answer*
changes because the module underneath it changed.

**Refined verdict on theory 1: the literal mechanism (param_3 selecting an
instance) is disproven, but a same-family mechanism (a dynamic 5-slot module
registry, keyed by hash, that different loaded content can register/re-register
into) is real, present, and is the only thing in this whole trace capable of
making a fixed key resolve to a different integer over time.** Whether it
actually correlates with level/chapter transitions during this specific
session is not provable statically - see the live-test section below.

### Theory 2 (a second writer) - no second writer found in the traced call path; not exhaustively ruled out project-wide

Within the two functions actually on this call path (`FUN_0032241c` and its
only known caller, the wrapper at `0x334294`), no code other than the single
`_opd_FUN_00ab685c` lookup traced above writes `param_1[0x1b]` (dword index
`0x1b`, byte offset `0x6c`). A project-wide, type-aware exhaustive scan for
every writer of byte offset `0x6c` specifically on the save-manager
singleton's class (as opposed to grepping the generic immediate `0x6c`
displacement, which hits unrelated objects constantly and isn't a targeted
search) was not performed this pass - doing that properly needs a
Ghidra structure-aware xref, which is how the original writer was found in
the first place (`research/ghidra/fm_applyrefs.txt`) and that scan reported
exactly one writer. Taking that scan's completeness at face value (as the
existing doc already did), **no second writer is known to exist**, but this
pass did not independently re-run an exhaustive project-wide version of that
scan, so it's stated as "not found in the traced path" rather than "proven
absent everywhere".

## Verdict on the "per-autosave location/checkpoint identifier" hypothesis

**Corroborated, not proven, and refined.** The chain of evidence:

1. `task-%x` is not a "shared connection/job id" (ruled out earlier) and not
   literally "the same UI popup id every time" (the six live captures
   already disprove that outright).
2. The value is memoized on a process-lifetime singleton - it can only
   change if something invalidates and re-triggers the lookup between saves.
3. The only mechanism this trace found that could make the SAME
   compile-time-constant key answer differently across such re-triggers is
   the 5-slot dynamic module registry inside `FUN_0078b5a0` - a mechanism
   whose natural driver, in a game engine, is level/chapter content
   streaming (different chapters' HUD-material overlay modules registering
   under the same nominal hash).
4. `FUN_0032241c` itself was already independently characterized (prior
   session) as building a "UI reward/notification-popup descriptor" - i.e.
   its natural trigger is a reward/milestone event, which in TLOU's
   single-player campaign fires at specific story beats and chapter
   progress points, not at arbitrary moments. That trigger cadence is
   itself consistent with "one value per campaign checkpoint" even before
   considering the registry-swap mechanism.

None of this is a cracked string naming an actual level, so it is corroboration
of the working hypothesis, not confirmation. The hypothesis is refined from
"task-%x IS a location/checkpoint id" to: **task-%x is the resolved id of a
fixed UI-popup icon key, looked up against whatever content module is
currently registered for that key's table - a value that tracks campaign
progress indirectly, through content-streaming state, rather than encoding a
location id directly.** That is a materially different (and more falsifiable)
claim than "it's a checkpoint id field", worth stating precisely rather than
rounding up to a full confirmation.

## What a live test needs to check next

1. Breakpoint `FUN_0032241c`'s entry (`0x0032241c`) across a real multi-save
   campaign session (the same kind of session that produced the six
   captures). Confirm it fires more than once, and read `param_1[0x1c]`
   (`this + 0x70`, `this` = the save-manager singleton, live address
   `0x44148220` from the prior session's breakpoint work) on entry each
   time - the theory predicts it reads `0` (freshly invalidated) on every
   hit that's about to produce a NEW `task-%x` value, and nonzero on any hit
   that reuses a cached one.
2. On the same hits, read `*(materialCollection + 8 .. +0x28)`'s five slot
   pointers and each populated slot's own `+0x64` hash field (materialCollection
   address: `*(u32*)0x01267088`, live-resolvable the same way `0x1441194` was
   resolved previously) - confirm whether the slot that answers `0x1AD3445F`
   is a DIFFERENT module pointer across saves that produced different
   `task-%x` values, and the SAME module pointer across any saves that (if
   ever observed) produce a repeated value.
3. Correlate each `task-%x` capture against the exact in-game chapter/level
   at the moment of that specific autosave (this session's six captures
   already span chapter 1 into chapter 2 in known order - re-check whether
   the six hash values happen to fall into two clusters aligned with that
   chapter boundary, which the registry-swap theory would predict even
   without a cracked string).
4. If any future disc/patch source becomes available (`pak23.psarc`/
   `actor34.psarc` parsed to completion, or any build's `text1.psarc`),
   re-run `dc_hash_crack.py` against these six specific hashes - a crack
   would immediately either confirm or refute the "per-chapter HUD-material
   id" reading in one step.

## Corpus exhausted, 2026-08-22 - all seven values (six above plus a
## seventh live-captured the same night, `task-e4c65aa7`) still uncracked

Item 4 above was followed through in full this session, plus more:

- `pak23.psarc` (10.8 GB) parsed to completion - **contains zero `.dci`
  files**. Not a timeout/size problem, a real negative: this archive
  doesn't carry DC-compiler symbol data at all.
- `actor34.psarc` (1.9 GB) parsed to completion - same, zero `.dci` files.
- `level-1.psarc.crypt` (this project's own cached copy,
  `server/data/served_content/build/main/pak23/level-1.psarc.crypt`) -
  decrypted cleanly (HMAC OK) and listed. Turned out to be **multiplayer
  map data** (`coop-bil-church-ingame12.pak`, `coop-hom-town-ingame12.pak`,
  etc. - real Factions map names), not campaign/single-player content at
  all. Wrong domain, not worth pursuing further under this name.
- `text1.psarc`'s full English locale text bank (`2.common`,
  `2.networking`, `2.subtitles`, `2.subtitles-temp` - every display string
  in the game, 22,664 entries) tried as a wordlist.
- `research/strings/strings_ascii.txt` (the EBOOT's own extracted string
  dump) tried as a wordlist.
- Combined: **104,840 unique candidate tokens**, 0/7 hashes matched.

The remaining untried disc archives (`animstream4.psarc`, `animtex0.psarc`,
`gallery1.psarc`, `lut0.psarc`, `vtex1.psarc`) are animation/texture/
color-grading payloads - essentially certain to carry no embedded readable
symbol names, not worth parsing.

**Revised standing on the "cracked hash would settle this" plan**: this
project has now tried every readily-accessible string source from the
retail disc and the EBOOT itself. The honest read is that these seven
values' source strings may simply never ship in any retail asset this
project can reach - a dev/debug-only symbol, or something computed from
internal tooling this project has no access to. This project already has
a precedent for exactly this outcome: `userdata/<id>.txt.crypt`'s one
consumed key hash (`0x8EFC1478`,
`docs/protocol/userdata_and_campaign_config_crypt.md`) is fully traced
mechanically and permanently uncracked, and is treated as a documented dead
end rather than an open item to keep re-chasing. `task-%x`'s specific
values should carry the same status going forward - the MECHANISM (item 1-3
above, and the live gate/registry trace earlier in this note) is solid;
the literal identity of any one resolved value is not expected to crack
without a source this project doesn't currently have access to.
