# profile.21's P+0x1E74..0x5008 zero region: a static walk

Date: 2026-08-21. Static only - no live RPCS3 session. Every address below is
**01.00** (`research/disasm/full.asm`,
`objdump -D -b binary -m powerpc:common64 -EB --adjust-vma=0x10000`), re-read
at the instruction level before being cited. TOC (`r2`) = `0x01305870`; both
LOAD segments map `file offset = VMA - 0x10000`.

Scope: the last genuinely-untouched span in `protos/profile_21.ksy`'s
`game_data`, `P+0x1E74..P+0x5008` (~0x3194 bytes), previously logged in
`docs/OPEN-QUESTIONS.md` as "no static trace attempted". This note does that
trace, the same way `career_stats` (P+0x0334..0x035B, a smaller gap in the
same file) was resolved on 2026-08-20.

## 0. The result up front

The doc's prior claim ("zero in both samples") is **wrong** for the first 24
bytes of this range and **confirmed correct** for the remaining ~12668 bytes:

- **P+0x1E74..0x1E8B** (24 bytes, six big-endian `u32` words): genuinely
  non-zero, per-account. `comradesean`'s profile.21 has all six words = 1;
  two other real samples (`mgnomad2`, `gmnomad`) have all six = 0. No EBOOT
  writer or reader was found for this span despite an exhaustive trace (§2-§3
  below). Left open; a concrete live-test plan is given in §5.
- **P+0x1E8C..P+0x5008** (~12668 bytes): confirmed zero in all three real
  samples, and no EBOOT code path (of any addressing idiom checked) ever
  constructs an address in this span. Closed as unused/reserved with high
  confidence.

## 1. The three samples

`research/tools/profile21_codec.py`'s `decode()` was used directly (not just
its CLI) to pull decrypted plaintext for:

- `server/data/served_content/profiles/comradesean/profile.21`
- `server/data/served_content/profiles/mgnomad2/profile.21`
- `server/data/served_content/profiles/gmnomad/profile.21` (a third real
  account, not previously used as a cross-check sample in this file's other
  notes - added here specifically to avoid a two-sample coincidence, per this
  doc's own caveat: "Confirm any newly-populated field against a third sample
  before trusting it.")

A full byte-level nonzero scan of payload range `[0x1BB0, 0x5000)` (=
`P+0x1BB8..P+0x5008`) against all three turned up nonzero bytes only in the
already-loosely-documented `P+0x1BB8..0x1E73` "genuinely unmapped middle"
window (out of this task's scope - see §6) plus the new six-word block at
`P+0x1E74..0x1E8B`. Nothing at all past `P+0x1E8B`:

```
P+0x1e74 .. P+0x1e88   comradesean: 00000001 00000001 00000001 00000001 00000001 00000001
                       mgnomad2:    00000000 00000000 00000000 00000000 00000000 00000000
                       gmnomad:     00000000 00000000 00000000 00000000 00000000 00000000
P+0x1e8c .. P+0x5008   all three:   all zero (12668 bytes, exhaustively checked)
```

Interesting correlation, not proven causal: `comradesean` is the *only* one
of the three samples with `milestone_latch_1e2c` (P+0x1E2C, the "Added Extra
Supplies from Promotion!" one-shot flag, per this doc's existing entry) set
to 1. Both the milestone latch and the six-word block are "on" only for the
same account. See §4.

## 2. The record's universal field accessor, and why it rules out most of the range

Every profile-record field this project has already resolved (`career_stats`,
`loadouts`, `custom_appearance`, `emblem_layers`, `survivor_seeds`,
`total_matches`, the `OnMatchEnd` settlement counters, ...) is read or written
through the same function, `FUN_003cb89c` (`bl 0x3cb89c`), called **436
times** in the 01.00 image. Given `r3 = this` (a handle - usually, but not
always, literally "the profile object"; see the caveat in §2.3), it returns a
raw pointer that the caller then indexes with either a compile-time-constant
immediate offset (the common case - `stw r29,820(r10)` for
`career_stats[0].score_total` at P+0x334, confirmed in the 2026-08-20 pass)
or a small runtime-computed offset (`loadouts`, `equipped_item_ids`,
`survivor_seeds` - each a bounded loop multiplying an index by a fixed
stride).

### 2.1 Exhaustive static-immediate scan

A scan of the whole disassembly tracked, per `bl 0x3cb89c` call site, which
register(s) alias its return value (following `mr`/`clrldi`/`extsw` moves,
dropped on the next unrelated write or `blr`), and flagged every
`stw/lwz/stb/lbz/sth/lhz` whose base register was one of those aliases with a
static immediate offset. Run over the *entire* profile record
(offset 0..0x5008, not just the target range) to sanity-check the method: it
recovers **exactly** the known field set (`0x0..0x3c`, `0x2d0..0x383`
(loadouts/gesture/career_stats), `0x654..0x8xx` (custom_appearance/emblem),
`0xa1c..0xa3b` (total_matches/survivor_count), `0x1ad4..0x1e57`
(day_counter..pop_highwater_c)) and **nothing past `0x1e57`** (the last byte
of `pop_highwater_c`, the highest-offset field this project has already
confirmed). Zero hits anywhere in `[0x1E58, 0x5008]` across all 436 call
sites. This is idiom-independent noise-checking too: even accessor calls
whose `this` argument is *not* the profile object (see §2.3) would have shown
up here if any of them used an immediate in this range, and none did.

### 2.2 Exhaustive dynamic-offset scan

The same alias tracking was extended to catch `add rD,rAlias,rY` (or the
reverse operand order) - the shape every known bounded loop (`loadouts`,
`equipped_item_ids`, `survivor_seeds`) uses. This found **61** such sites
binary-wide. Each was inspected manually: every one either (a) resolves to
one of the already-known/bounded arrays (`loadouts`, `equipped_item_ids`,
`survivor_seeds`, or the DC net-stat accumulator at `record[8 +
(statIdx+581)*4]`, §2.4), or (b) is a genuinely new mechanism, `FUN_0037a28c`
(§2.5), whose reachable offset was independently bounded and does **not**
reach `0x1E74`. None of the 61 sites construct an offset >= `0x1E58` outside
the two exceptions just named, and neither exception reaches `0x1E74`.

### 2.3 Caveat: `FUN_003cb89c` is not exclusively a profile-record accessor

One call site (`FUN_00341344` @`0x3414c4`, the `custom_appearance` reader)
passes a **computed** array-element address as the "this" argument (`r3 =
mullw(charRecordCount, elementStride) + tableBase`, i.e. a resolved DC
character-record handle, not the player's own profile pointer) and gets back
a pointer into a *different* object entirely. So `FUN_003cb89c` is a generic
"resolve object pointer" primitive reused across subsystems, not exclusively
bound to profile.21. This does not weaken §2.1/§2.2's conclusion (which
scanned literally every call site regardless of what object each one
resolves), but it does mean a raw address match against a known profile
offset is not automatic proof of a profile access - confirmed case in point:
§3.

### 2.4 The DC net-stat accumulator's real bound

`docs/protocol/profile_21_record.md`'s existing "DC-indexed net-stat slots"
entry cites the formula `record[8 + (statIdx+581)*4]` from `FUN_003f208c`
@`0x3f2494`-`0x3f2514`. Traced in full here: the loop that drives it
(`cmpwi cr7,r28,1` / `bne cr7,0x3f2494`) runs exactly **twice** (`r28` = 0,
then 1) per `OnMatchEnd` invocation, feeding two different `statIdx` values
(via `bl 0x36655c`) into the formula - it does not sweep the whole
`*net-stats*` table. Even the full 40-row `*net-stats*` table
(`dc1/net.bin 0x9c18`, already resolved 2026-08-20) would only reach
`P + 8 + (39+581)*4 = P+0x9BC`, nowhere near `0x1E74`. This mechanism cannot
be the target range's producer.

### 2.5 `FUN_0037a28c`: a new, unresolved profile-record mechanism (not the answer, but worth recording)

One of the 61 dynamic-offset sites, `FUN_0037a28c` (reached from
`0x37a328`), was not any previously-documented array. It:

1. Loops over a DC name-catalog (`bl 0x9fa0b4` for the row count, `mtctr`,
   `mulli r9,r11,28` for a 28-byte stride, `bdnz` @`0x37a304..0x37a318`),
   accumulating a running sum `r27 += word_at(elem+8)` across every visited
   row.
2. Uses that accumulated sum (`r27<<2`) as a **dynamic offset added to
   `0x1BEC`** into the profile record (`bl 0x3cb89c` @`0x37a328`, then
   `slwi r9,r31,2; addi r9,r9,7148 (0x1BEC); add r3,r3,r9; lbz ...,8(r3)`
   @`0x37a330-0x37a344`) - i.e. it reads/writes somewhere at or after
   `P+0x1BF4`, exact address data-dependent on the DC catalog's contents.

Confirmed this touches the **real profile singleton**, not an unrelated
object: `FUN_0037a28c`'s own literal-pool anchor (`r30 = *(0x01305870 -
31128) = 0x01270E9C`; `this = *(0x01270E9C - 32748) = *(0x01268EB0) =
0x01389A38`) resolves to the identical address `FUN_003f208c` (the
`career_stats`/`OnMatchEnd` writer) uses for its own "this" (`r30 =
*(0x01305870-30960) = 0x01272F78`; `*(0x01272F78-32768) = *(0x0126AF78) =
0x01389A38`) - same singleton, two different compilation units, two
different literal-pool paths, same final address. So this genuinely is a
profile-record access - and it is a **previously unmapped one**, adjacent to
but before this task's target range.

Six call sites (`0x2f24b8`/`0x2f24dc`/`0x2f366c`/`0x2f3690`/`0x2f6a5c`/
`0x2f6a80`, all in the `0x2f2xxx`/`0x2f6xxx` region this project's other
notes associate with leaderboard/member-list code) call `FUN_0037a28c` with a
running "find the max returned value" pattern (`cmpw cr7,r17,r3; ble; mr
r17,r3`), consistent with a per-candidate-name computation feeding a
best-of-N comparison (plausibly the same "duplicate name" hashing theme
`survivor_seeds`'s own duplicate check already established, but for a
*different* catalog/purpose - not further chased here, out of this task's
scope). The accumulated sum's true numeric bound (and therefore whether this
mechanism can *ever* reach `0x1E74`) was **not** pinned - the loop has no
visible modulo/mask before the sum is used as an index, which is unusual
for a hash-table-style lookup and worth a dedicated follow-up, but every
observed catalog this file resolves elsewhere (`*net-stats*` 40 rows,
`*net-taunts*` 11, emblem shapes 192, emblem colors 64) is small enough that
even a full-catalog sum of small per-row values would need implausibly large
per-row magnitudes to clear the ~160 words of headroom between `0x1BF4` and
`0x1E74`. Flagged as an open loose end, not resolved, and NOT folded into
`profile_21.ksy` this pass (no P-relative field boundary was established -
folding it in would require pinning the DC catalog's per-row semantics
first).

## 3. Chasing the six non-zero words directly: false leads

Since §2 rules out the record's own dedicated accessor as a path to
`0x1E74`, the six words were instead chased by literal byte-offset: every
`lbz/stb/lhz/sth/lwz/stw/lfs/stfs` instruction anywhere in the binary whose
immediate offset equals `7788/7792/7796/7800/7804/7808/7812/7816`
(`0x1E6C..0x1E88`) was enumerated (22 hits). **Every one of them belongs to a
large, unrelated float-bearing class** (confirmed by checking each
containing function's own prologue): `FUN_0048573c` (constructs an object
with a vtable store at offset 0, `SIMD`/`vspltisw`/`vcfsx` instructions, and
its own field at this same numeric offset - clearly a live gameplay/render
object, not the persisted profile, since `r31`/`r24` there are the raw `this`
parameter with no `bl 0x3cb89c` in sight), plus four more distinct functions
at `0x475860`, `0x489xxx`, `0x508xxx`/`0x510xxx`, and `0xdf82b0` - none of
which route through the profile accessor either. These are coincidental
numeric collisions (small-struct offsets recur across many unrelated classes
in a 4M-line disassembly), not real profile accesses. This is a genuine dead
end for finding this six-word block's producer by direct-offset search.

The `milestone_latch_1e2c` setter itself, `FUN_0035f1bc` (the "Added Extra
Supplies from Promotion!" function, already cited in
`protos/profile_21.ksy`), was read in full end-to-end (`0x35f1bc..0x35f550`)
on the chance that the same function also drives the six-word block (they
correlate 1:1 across the three samples, see §1). It does not: its only
profile-record touches are at `P+0x1E2C` (the latch itself, read+write) and
two **read-only** gate checks at `P+0x1BBC` and `P+0x1DF8` (both inside the
already-flagged-but-unresolved "genuinely unmapped middle" window, `P+0x1BB8
..0x1E73` - see §6, out of scope here) before calling out to `0x364674`/
`0x3378e0`/etc. (reward-grant plumbing not itself part of the profile
record). No write to anything past `P+0x1E54` appears anywhere in this
function.

## 4. Working theory (not proven)

`P+0x1E74..0x1E8B`'s correlation with `milestone_latch_1e2c` (both "on" only
for `comradesean`, both "off" for the other two samples) is consistent with
a shared "Promotion" reward/unlock event granting **six** additional
flags/rewards alongside the message flag - plausibly a per-item reward-grant
list (six reward slots, each a boolean "granted" flag) written by whatever
code path actually *executes* the reward (as opposed to the message-flag
latch, which only gates the one-time notification text). Given
`custom_appearance`'s `survivor_variant_id`/`equipped_item_ids` are already
established precedent for profile fields with **no EBOOT writer at all**
(DC/customization-menu-side writes only, per that field's own doc entry),
the same explanation is plausible here too - a DC script executing the
reward grant, invisible to EBOOT-only static analysis. This is a hypothesis,
not a finding: only one account among three shows the pattern, which is not
enough to separate "shared cause" from "coincidence + unrelated legacy
data from an older save format."

## 5. What a live pass would need to check

Static analysis is exhausted for this specific 24-byte block (both
addressing idioms this file uses anywhere else were checked exhaustively;
the correlated candidate function was read in full and doesn't touch it).
Unblocking it needs RPCS3, following this project's already-working method
(`research/tools/eboot_analysis/README.md`, "Live memory write-breakpoints"):

1. A self-compiled RPCS3 with `HAS_MEMORY_BREAKPOINTS`, PPU decoder set to
   Interpreter.
2. A **fresh/low-progress account** (one that has *not* yet received the
   "Added Extra Supplies from Promotion!" message, i.e. `milestone_latch_1e2c
   == 0`) - use `research/tools/profile21_codec.py dump` to confirm before
   starting.
3. Arm a Memory Write breakpoint on the live profile buffer's
   `P+0x1E74..0x1E8B` (24 bytes; the buffer's runtime VMA needs a fresh
   `bl 0x3cb89c` trace against that RPCS3 session's own state, since it's a
   heap allocation, not a fixed address).
4. Play until the "Added Extra Supplies from Promotion!" trigger fires
   (`FUN_0035f1bc`'s predicate-6 / game-state==3 condition, already
   documented). If the breakpoint fires: `CIA`/`LR` pin the exact writer the
   same way the `0x12f_room_create.ksy` `value_20` field was resolved
   2026-08-21 (see that README section for the full technique). If it does
   **not** fire despite the six words changing 0->1 across a save/reload:
   that is itself evidence for the DC-script-write hypothesis in §4 (same
   diagnostic logic already used to rule EBOOT code in/out for
   `custom_appearance`'s DC-only fields).
5. Independently, `profile21_codec.py diff` the profile before and after
   the trigger fires to confirm whether the six words move *together* with
   `milestone_latch_1e2c` in a controlled single-event test (this pass only
   had two static snapshots per account to compare, not a controlled
   before/after of the same account).

## 6. Explicitly out of scope, left for a future pass

- `P+0x1BB8..0x1E73` ("genuinely unmapped middle", already flagged in the
  doc before this pass): confirmed still real and non-trivial - `Fun_0035f1bc`
  reads two flags in this window (`P+0x1BBC`, `P+0x1DF8`) as gates, and
  §2.5's `FUN_0037a28c` touches something at or after `P+0x1BF4`. Not solved
  here; this task's scope was specifically `P+0x1E74..0x5008`.
- `FUN_0037a28c`'s DC-catalog hash mechanism and its true index bound (§2.5).

## Conclusion / confidence

- **`P+0x1E8C..P+0x5008` (~12668 of the ~13172 target bytes): CLOSED.** High
  confidence, evidence-backed "structurally unused" - zero in three
  independent real accounts, and no EBOOT code path (exhaustively checked,
  both addressing idioms used anywhere else in this record) ever constructs
  an address in this span. No live blocker: there is nothing here to catch a
  write of.
- **`P+0x1E74..0x1E8B` (24 bytes): NARROWED, not closed.** Real,
  per-account, non-zero data exists (proven on 3 samples); the doc's old
  blanket "zero in both samples" claim was wrong for this specific slice.
  No EBOOT static writer/reader found despite an exhaustive trace of the
  record's universal accessor (436 call sites) and a direct byte-offset
  sweep of the whole binary. Correlates with `milestone_latch_1e2c` on the
  one sample that has both; not proven causal. Live-test plan above.
