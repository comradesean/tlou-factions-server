# Survivor roster sub-structure (P+0xA3C–0x1A3C) — solved, and it's smaller than it looked

## Question

`protos/profile_21.ksy`'s `game_data` type has a byte range, payload
`0xA34–0x1A34` (`P+0xA3C–0x1A3C`), that every prior pass left as "dense
per-survivor appearance/state; only the name-seed array (`survivor_seeds`,
a flat `u64[survivor_count]`) is decompile-pinned." The project's own
`docs/factions-metagame-reference.md` (community-research-sourced,
pre-dating any byte-level work here) independently describes a conceptual
`survivor_roster: [(name, state)]` where `state ∈ {healthy, starving,
sick}`. The working hypothesis going in: the unexplained remainder of this
~4KB region holds a per-survivor health/state byte (or word), either
interleaved with the seed (`{u64 seed, u32 state}` repeating) or as a
second flat array tacked on after the seeds end.

No RPCS3 access this pass — this is 100% static (decompile + byte
inspection of the two real captured samples), so it can rule structural
hypotheses in or out but can't do a live before/after edit.

## Finding: there is no second array. The whole region is the seed array — at fixed 512-entry capacity, not `survivor_count` entries.

The doc's stated region size, `0x1A3C - 0xA3C = 0x1000` = 4096 bytes, is
suspiciously exactly `512 * 8`. That's not a coincidence — decompiling the
three functions that touch this region shows the array is fixed at **512
u64 slots**, always fully populated, and `survivor_count` (the "population"
scalar next to it) is only a *count of how many of those 512 slots are
currently active*, not the array's length.

### The setter: `FUN_003cd060(this_unused, index, u64* value)`

```
3cd060: r29 = r4 << 3            ; index * 8
        r28 = ld r5, 0(r5)       ; *value (the u64 to store)
        bl 0x3cb89c              ; r3 = GetProfile() (profile base = mgr+200,
                                 ;   confirmed separately: 0x3cb89c returns r31+200)
        r29 = r29 + 2612
        r3 = r3 + r29
        std r28, 8(r3)           ; *(profile + 2612 + index*8 + 8) = value
```

Effective address: `profile + 2620 + index*8` = `profile + 0xA3C + index*8`
— exactly `survivor_seeds[index]`, decompile-confirmed address arithmetic,
not inferred.

### The getter: `FUN_003cb92c(this_unused, category, index)`

```
3cb92c: r28 = r5 << 1            ; index * 2
        r29 = r4 + r28           ; category + index*2
        bl 0x3cb89c              ; r3 = GetProfile()
        r29 = r29 << 2           ; (category + index*2) * 4
        r3 = r3 + r29
        r3 = ld r3, 8(r3)        ; return *(profile + (category+2*index)*4 + 8)
```

Called from `FUN_00378a24` (below) with `category = 653` (`li r4,653` at
`0x378b70`). `653*4 = 2612`, so the address is `profile + 2612 + index*8 +
8` = `profile + 2620 + index*8` — **the identical formula** to the setter.
`FUN_003cb92c` is the seed-array's getter, confirmed by matching address
arithmetic against the setter, not by name or convention.

Only three call sites reach `FUN_003cd060` in the whole binary
(`research/tools/eboot_analysis/scan_bl.py 3cd060`): two inside
`FUN_0037a7b4` (clan init) and one inside `FUN_00378a24` (survivor-add).
Nothing else in the binary writes into this address range under any other
stride or offset.

### `FUN_0037a7b4` (clan init) populates all 512 slots, unconditionally, at creation time

Two back-to-back loops, both `for i in [0, 512)` (bounded by `cmpwi
cr7,r28,511` at `0x37a8ac` / `0x37a918`, i.e. `i <= 511`, 512 iterations):

- **Loop 1** (`0x37a880–0x37a8d4`): for each `i`, calls an accessor
  (`bl 0xac0194` / `0xac12c0`, conditionally), loads a `u64` from its
  result, and writes it to `survivor_seeds[i]` via `FUN_003cd060`.
- **Loop 2** (`0x37a8e4–0x37a920`): for each `i` again 0..511, calls `bl
  0xe408d8` **twice** (a 32-bit RNG draw, called elsewhere in this same
  function for other fields too), assembles the two 32-bit halves into a
  64-bit value on the stack, and writes it to `survivor_seeds[i]` via
  `FUN_003cd060` — **unconditionally overwriting loop 1's value for every
  index**.

Since loop 2 runs second and touches every index loop 1 touched, loop 1's
writes to this array are dead for this field (loop 1's accessor calls may
still matter for a different field/side effect not investigated here —
out of scope). The net, observable effect: **all 512 `survivor_seeds`
slots are independently RNG-initialized in one pass at clan creation**,
before the account has anywhere near 512 survivors.

### `FUN_00378a24` (survivor-add) never regenerates a seed on the happy path

This is the function the existing doc already cites as `survivor_count`'s
writer (`stw …,2616` = `profile+0xA38`). Full trace of its "add one
survivor" path:

1. `r28` = current `survivor_count` (byte-loaded from `profile+2616`).
2. Bounds check: `cmpwi cr7,r28,511 / ble` — only proceeds past 511 (i.e.
   refuses to add) once `survivor_count` would exceed 512. This independently
   confirms the 512 capacity from the other direction (a hard ceiling, not
   just an init-time loop bound).
3. `stw r0,2616(r3)` where `r0 = old_count + 1` — increments
   `survivor_count`. **No write to the seed array happens here.**
4. It then calls the getter `FUN_003cb92c(_, 653, new_index)` — i.e. it
   *reads* `survivor_seeds[new_index]`, the value already written by the
   init-time RNG loop — and uses it purely for a duplicate-name check
   against an external name registry (a loop over a global list at
   `-32700(r30)`, bounded by that list's own count field, unrelated to
   `survivor_count`).
5. **Only if that duplicate check fires** does it call `FUN_003cd060`
   again (`bl` at `0x378c0c`), rerolling a *different*, randomly chosen
   existing index (`r26`, bounded by an unrelated list-size field at
   `this+44/this+48`) with a fresh two-`0xe408d8`-draw value — a
   maintenance/dedup reroll, not part of the normal growth path.

Called from two sites (`0x0037d530`, `0x0037e13c`) — both inside the
settlement-tick subsystem, consistent with "survivor arrives during normal
clan-sim ticking," not a menu action.

### `FUN_0037cf90` (settlement per-tick updater) never touches this array at all

Full disassembly of the function (`0x37cf90–0x37d300`, covering the whole
`clan_state`/`healthy_count` tick logic) has zero references to
`profile+0xA3C` or any address built from `2612`/`2620`/`653`. It reads and
writes `clan_state` (`profile+0x1BF0`), `healthy_count`
(`profile+0x1E48`, at `0x37d07c` — identical RNG-modulo-population formula
as the init function, matching the existing doc entry exactly), and a
handful of adjacent day-counter/timer fields. **No loop indexed by
`survivor_count` appears anywhere in this function.**

## Byte-level corroboration on both real samples

If the above is right, every one of the 512 `u64` slots in
`payload[0xA34:0x1A34]` should be non-zero in a live account, not just the
first `survivor_count` of them (since all 512 were RNG-populated at clan
creation, and growth never touches unused slots except the rare reroll
case). Checked directly against both real, currently-live captures
(note: both accounts have progressed since the last profile.21 pass —
`comradesean` is now `survivor_count=164` where the record previously said
86, `mgnomad2` is `survivor_count=55` where it previously said 33; this is
expected, live play between sessions, not a discrepancy in the finding):

```
comradesean: survivor_count=164, healthy_count=7  -> 512/512 qwords non-zero
mgnomad2:    survivor_count=55,  healthy_count=5   -> 512/512 qwords non-zero
```

Every single slot in the 512-capacity region is non-zero in both samples,
including all slots far past each account's current `survivor_count` —
exactly what "RNG-initialize all 512 at clan creation, only `survivor_count`
of them currently active" predicts, and inconsistent with any hypothesis
where slots past the active count should read zero/reserved.

## Conclusion

**CONFIRMED, high confidence** (decompile-exact address arithmetic on the
sole three call sites that touch this memory range, cross-checked against
byte contents of both real samples): the entire payload range
`0xA34–0x1A34` is `survivor_seeds: u64[512]` — a single flat array at fixed
capacity, RNG-populated in full at clan creation, of which only the first
`survivor_count` entries are "active" roster members. It is not two
interleaved arrays, not a wider per-entry struct, and it does not contain
a per-survivor state/health field of any width.

**The community-doc hypothesis (`[(name, state)] ` per survivor, `state ∈
{healthy, starving, sick}`) is REFUTED for this byte region specifically**
— there is no per-survivor state data anywhere in
`0xA34–0x1A34`. This doesn't mean the game has no such concept (the
UI likely does show individual survivors as healthy/hungry/sick), just
that if it's persisted at all in `profile.21`, it isn't here. Every writer
that touches this region was fully decompiled (three call sites, all
traced) — this isn't a "not yet found" gap, it's an exhaustive negative
result for this specific address range.

The only per-account health-adjacent value found anywhere in `profile.21`
remains the existing `healthy_count` scalar (payload `0x1E40`, `P+0x1E48`)
— an **aggregate**, RNG-drawn as `1 + rng() % (population - 1)` by both
`FUN_0037a7b4` (init) and `FUN_0037cf90` (per-tick), not a sum/count
derived from any per-survivor field, and not menu-written. This was
already the doc's standing description; this pass adds no new evidence
about what "healthy" means numerically or whether the client's clan-camp
UI computes per-survivor status live (client-side only, never persisted)
or doesn't track it as discrete per-survivor state at all. That question
is now firmly **out of profile.21's byte range** — if it's answerable at
all, it needs a different research angle (client-side memory/behavior
during a live session), not more static analysis of this file.

## What's still genuinely open

- **Why does the game bother RNG-populating 512 slots up front** instead
  of generating a seed lazily when a survivor actually joins? Plausible:
  determinism/perf (avoid an RNG call during gameplay-critical clan-tick
  code), or simply matches an engine-wide "fixed capacity, pre-warmed
  pool" pattern seen elsewhere in this binary (the `this+120` bitmap
  in `FUN_00378a24`, and the 512-iteration clearing loops for the
  *other*, unrelated net-stat arrays in the same init function, both bounded
  at 511/512 too). Not resolved, not important to a server reimplementation.
- **What happens past 512 survivors?** `FUN_00378a24`'s bounds check
  (`cmpwi cr7,r28,511 / ble`) means growth silently stops being applied
  once `survivor_count` would exceed 512 — the function still runs to
  completion (falls through to the "not found, mark full" tail at
  `0x378be0` region) but the count itself never crosses 512. Not tested
  live; inferred from the branch structure alone.
- **`FUN_00378a24`'s `this+120` bitmap and `this+944` array**: confirmed
  these are NOT part of `profile.21` — `this` here is the function's own
  first argument (a transient clan-simulation manager object distinct from
  the profile singleton, which is fetched separately via `bl 0x3cb89c`
  inside the same function). Not investigated further; irrelevant to the
  persisted file.
- **`healthy_count`'s real-world meaning** (what "healthy" means to a
  player, and whether per-survivor status exists client-side-only) remains
  unresolved, as noted above — this pass narrows *where it isn't*, not
  what it is.

## `.ksy` / doc changes made alongside this note

- `protos/profile_21.ksy`: `survivor_seeds` now modeled as the true
  on-disk shape — fixed `u64[512]`, with `survivor_count` documented as
  the active-entry count into that fixed array rather than the array's
  length. The old `repeat-expr: survivor_count` under-modeled the real
  file (it only decoded the active prefix, not the full persisted
  region) — no data was being silently dropped by the schema before
  (parsers reading past the last struct field still see the right bytes,
  this only affects the semantic field boundary), but the KSY now matches
  what's actually persisted, byte for byte, region-wide.
- `docs/protocol/profile_21_record.md`: the "Per-survivor roster
  sub-structure … dense per-survivor appearance/state" line is replaced
  with the solved finding — a fixed 512-slot seed pool, cited to this
  note — rather than left in its previous "not decompile-pinned" framing,
  since it now is.

## Live-test plan for a future RPCS3 session (cheap, targeted)

Everything above is inferred from decompile + static byte inspection of
two samples that can't be edited live this pass. The predictions below are
specific and falsifiable — this should take under 10 minutes of in-game
time to fully confirm or refute, versus the open-ended "dense unstructured
region" exploration this would otherwise require.

**Setup**: snapshot `profile.21` for a test account (same technique as
`research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md` §10 —
capture before, take one isolated in-game action, capture after, diff with
`profile21_codec.py --diff BEFORE.profile21 AFTER.profile21`). Use an
account where population is expected to grow soon (e.g. one close to a
"new survivor arrives" clan-sim tick), OR — if there's any dev/debug menu
or console access to force clan population growth directly, that's more
controllable than waiting for organic ticks.

**Test 1 — growth doesn't touch the seed array (the main prediction)**

1. Capture `BEFORE.profile21`.
2. Let clan population grow by exactly one survivor (via whatever
   organic trigger the game uses — a match completion, a clan-sim tick,
   etc; do NOT do anything else in the same session).
3. Capture `AFTER.profile21`.
4. Diff. **Predicted**: `survivor_count` (payload `0xA30`, 4 bytes)
   changes `N -> N+1`. **Nothing else in the `0xA34-0x1A34` region
   changes** — specifically, `survivor_seeds[N]` (the newly-activated
   slot, 8 bytes at payload `0xA34 + N*8`) should be byte-identical
   before and after, because per the decompile it was already
   RNG-populated back at clan creation and growth only flips the active
   count.
5. If `survivor_seeds[N]` DOES change on this diff, the "seeds are
   pre-generated at init, growth just activates" claim is wrong and needs
   revisiting — that would be the single most informative possible
   real-world contradiction of this note's finding.

**Test 2 — the survivor's displayed name matches its slot's seed both before and after activation**

1. From a `BEFORE.profile21` capture, decode `survivor_seeds[N]` (the
   slot that Test 1 predicts is about to activate) using
   `profile21_codec.py` (or a small script built on `codec.decode()`).
2. After the growth event, note the new survivor's displayed name in the
   in-game clan roster UI.
3. If there's any way to resolve a name-seed to a display string (no such
   resolver is known/built yet for this specific u64 — it's a different
   mechanism than the DC StringId hashes used for emblems/appearance,
   since 8 bytes of pure RNG output isn't a DC hash of anything
   meaningful) — this step may not be fully closeable this way. Worth
   attempting only opportunistically; Test 1 is the load-bearing one.

**Test 3 — rule out a per-survivor state elsewhere in the file (belt-and-suspenders)**

Since this note concludes there's no per-survivor state anywhere in
`profile.21`, a strong confirming test: in-game, deliberately let a
survivor's status visibly change (e.g. from "healthy" to "sick"/"hungry"
in the clan-camp UI, if that's player-visible and not just narrative
flavor) without any other action in between, and diff. **Predicted**: no
byte in the record changes at all (since no persisted field for this was
found anywhere, not just in the seed region) — OR, if something *does*
change, it should be the aggregate `healthy_count` scalar (payload
`0x1E40`) moving by ±1, not anything in the seed region. Either outcome is
informative: a `healthy_count` change would be the first real evidence of
what "healthy" numerically means; a truly silent diff would confirm the
per-survivor status the UI shows is entirely client-side/ephemeral and
never reaches the server at all.
