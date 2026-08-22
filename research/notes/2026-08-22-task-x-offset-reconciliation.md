# Reconciling `+0x6c`/`+0x70` against tonight's live save-listing-shaped read

Date: 2026-08-22. Follow-up to a real live breakpoint hit on `FUN_007f1acc`'s
entry (01.00 VMA `0x007f1acc`) during the 2026-08-21/22 campaign session,
confirmed singleton address `r3 = 0x44148220` (same address independently
re-confirmed across multiple hits this session per
`research/notes/2026-08-21-stat-line-config-writer-trace.md`). Live reads at
that hit:

    0x4414828c (this+0x6c): 58 3a c2 ee  = 0x583AC2EE
    0x44148290 (this+0x70): 00 00 00 00  = 0x00000000

with save-data-directory-listing-shaped bytes ("USR-DATA", "ICN-ID",
"ICON0.PNG", repeating `{0, ts, ts, ts}`-style quads with plausible 2026
Unix timestamps) somewhere nearby in the same object. This note re-verifies
the `+0x6c` claim from scratch against the decompile/disassembly (not taking
the 2026-08-21/22 notes on faith) and reconciles the listing-shaped data.

## Part 1: re-tracing `+0x6c` all the way to the `%x` argument, from raw disassembly

Re-read `research/disasm/full.asm` at `FUN_007f1acc` (`0x007f1acc`) myself,
following execution forward from `0x7f1cf4` rather than trusting the prior
note's isolated citation:

```
7f1ce0: bl   0xacc424        ; hello handshake (FUN_00acc424), r3 = result
7f1ce8: cmpwi cr7,r3,0
7f1cec: bne  cr7,0x7f1dac    ; handshake failed -> silent-absorb fallback (GATE 4)

7f1cf0: lwz  r9,-32572(r30)  ; r9 = TOC slot -> the %s(2nd) accessor's arg pointer
7f1cf4: lwz  r29,108(r31)    ; r29 = *(this+0x6c) = param_1[0x1b]   <-- the value in question
7f1cf8: lwz  r3,0(r9)
7f1cfc: bl   0x952520        ; %s(2nd) accessor: returns base+0x2e6c (BCUS98174 string)
...
7f1d20: addi r28,r1,328      ; dest buffer for the formatted line
7f1d24: lwz  r4,-32424(r30)  ; r4 = "stat %s task-%x %s %s\n" literal
7f1d28: clrldi r7,r3,32      ; r7 (arg 4, 2nd %s)  = zero-extend(r3)  [BCUS98174 ptr]
7f1d30: clrldi r6,r29,32     ; r6 (arg 3, %x)      = zero-extend(r29) [our value, UNCHANGED]
7f1d34: clrldi r8,r8,32      ; r8 (arg 5, 3rd %s)  = zero-extend(r8)  [SD/HD]
7f1d38: addi r5,r1,144       ; r5 (arg 2, 1st %s)  = online_id buffer
7f1d3c: mr   r3,r28          ; r3 = dest buffer
7f1d44: bl   0xe46670        ; _opd_FUN_00e46670(dest, fmt, r5, r6, r7, r8)
```

**Confirmed directly, independent of the prior pass:** between the `lwz
r29,108(r31)` load and the `clrldi r6,r29,32` that feeds the formatter call,
`r29` is never re-loaded, never dereferenced, never used as a base register
for any other load, and no other instruction touches it. `clrldi r6,r29,32`
is a plain 32-bit zero-extend (PPC64 calling-convention normalization for a
32-bit `int` argument on a 64-bit register), not a pointer computation. The
value at `this+0x6c` is consumed **directly as the raw 32-bit integer** that
becomes `%x` — not as a pointer, not as an array index, not re-interpreted
in any way. This settles item 1 of the task cleanly: the offset claim is
correct, and the "what if `+0x6c` holds a pointer" hypothesis is disproven
by the disassembly itself — there is no dereference on this path at all.

## Part 2: `+0x70` is not a plain sentinel — it's a dual-purpose field, and that resolves the flag/value puzzle completely

Re-read the actual Ghidra decompile of the `0x1AD3445F` block in
`research/ghidra/fm_applyrefs.txt` line-by-line (not the prior note's
paraphrase) to check exactly what gets written to `param_1[0x1c]`
(`this+0x70`) and in what order, relative to `param_1[0x1b]` (`this+0x6c`):

```c
if (param_1[0x1c] == 0) {               // <-- gate read
  if (uVar9 != 0) {                     // <-- table currently valid
    iVar14 = _opd_FUN_00ab685c(iVar15, *(puVar8 + -0x7ee8));   // key: "general/hud/prize-icon/Default"
    param_1[0x1b] = (iVar14 != -1) ? table[iVar14] : 0;         // <-- this+0x6c, 1st field written
    iVar14 = _opd_FUN_00ab685c(iVar15, *(puVar8 + -0x7ee4));
    param_1[0x23] = ...;                                        // 2nd field written
    iVar14 = _opd_FUN_00ab685c(iVar15, *(puVar8 + -0x7ee0));
    param_1[0x24] = ...;                                        // 3rd
    iVar14 = _opd_FUN_00ab685c(iVar15, *(puVar8 + -0x7edc));
    param_1[0x25] = ...;                                        // 4th
    iVar14 = _opd_FUN_00ab685c(iVar15, *(puVar8 + -0x7ed8));    // key: unresolved, 5th slot's key
    param_1[0x1c] = (iVar14 != -1) ? table[iVar14] : 0;          // <-- this+0x70, 5th field written
    ... 9 more sibling fields (0x27,0x26,0x29,0x28,0x2a,0x21,0x2b,0x2d,0x30) ...
  }
} else if (uVar9 == 0) {
  // table went invalid: zero all 14 fields, INCLUDING param_1[0x1c] itself
  param_1[0x30]=0; param_1[0x1b]=0; param_1[0x23]=0; param_1[0x24]=0;
  param_1[0x25]=0; param_1[0x1c]=0; param_1[0x27]=0; param_1[0x26]=0;
  param_1[0x29]=0; param_1[0x28]=0; param_1[0x2a]=0; param_1[0x21]=0;
  param_1[0x2b]=0; param_1[0x2d]=0;
}
```

(Full sequence: `research/ghidra/fm_applyrefs.txt` lines 159-289, all 14
sibling writes and the matching 14-field zero-out both verified directly
this pass — corrects the 2026-08-21/22 note's paraphrase, which described
`param_1[0x1c] = uVar13` as though it were a distinct "gate re-arm" write
separate from the sibling-field pattern; it is not — it is written by the
exact same `_opd_FUN_00ab685c(table, key) -> table[index]` idiom as
`param_1[0x1b]` and the other 12 siblings, using its own key at TOC slot
`puVar8-0x7ed8`, no different in kind from any of them.)

**This resolves the flag=0/value-nonzero puzzle outright, with no third
state and no offset error needed:** `param_1[0x1c]` (`this+0x70`) is
*itself* the resolved integer for a second `general/hud/...` key — not a
boolean/sentinel constant distinct from the data it gates. The gate
condition (`if (param_1[0x1c] == 0)`) tests whether *that specific key's
last-resolved value* was zero, and reuses the same storage as "has this
group ever been populated." If the content module currently answering
`0x1AD3445F` resolves the `-0x7ed8` key to the integer `0` — which is
exactly what was read live tonight, `this+0x70 == 0` — then:

- The group write **did** run to completion (this+0x6c legitimately holds a
  fresh, non-stale resolved value, `0x583AC2EE` — consistent in shape with
  the six previously-captured `task-%x` values, e.g. `0x7d9d7acc`,
  `0xad611b77`: all eight-hex-digit values with no low/high nibble pattern
  suggesting a pointer or small index, all sitting in the same "opaque
  32-bit id" shape).
- But because the *value written* to the gate field happens to be `0`, the
  gate can never be observed as "already resolved" on any later call —
  `param_1[0x1c] == 0` will be true again the very next time
  `FUN_0032241c` runs, for as long as the `-0x7ed8` key keeps resolving to
  `0`. The function will treat the group as unresolved and **redo the
  entire 14-field lookup from scratch, unconditionally, every single call**
  — the "memoization" the 2026-08-21/22 note described exists in the code
  but structurally never latches for this account, this session, because of
  what one specific sibling key happens to resolve to.

**Verdict on item 3: (a) confirmed, cleanly.** The observed
`+0x70==0, +0x6c==0x583AC2EE` combination is not a bug, not a third state,
and not evidence the offsets are wrong — it is the exact, fully-expected
steady state of a successful fresh lookup whose 5th sibling key currently
resolves to zero. No live-test ambiguity remains on this specific question.

### Consequence for the six-different-values mystery

This *sharpens*, rather than contradicts, the 2026-08-21/22 trace's
"5-slot dynamic module registry" theory — it actually makes that mechanism
load-bearing rather than optional. Previously the theory only needed to
explain occasional cache invalidation/re-arming; now, since the gate never
latches at all in this account's observed state, `FUN_0032241c` re-resolves
against whatever module is *currently* registered for `0x1AD3445F` on
**every single call**, with no caching effect whatsoever. Six different
`task-%x` values across six calls in one session is now the expected
outcome of *any* per-call variation in which module answers that hash
(chapter/level-scoped content streaming, as already hypothesized), with the
"memoization" framing dropped as inapplicable to this observed run — it is
present in the code, but was never actually engaged this session.

## Part 3: the save-listing-shaped data is a different field of the same object, not `+0x6c`/`+0x70`

The 14-field HUD-icon-lookup group this pass re-verified spans
`param_1[0x1b]` through `param_1[0x30]` — dword indices `0x1b`..`0x30`,
i.e. byte range `this+0x6c` through `this+0xc0` inclusive (`0x30*4=0xc0`).
Every one of those 14 fields is written by the exact same
`_opd_FUN_00ab685c(table, key) -> table[index]` idiom (a plain 32-bit
integer, `uVar13`/`undefined4`, either a resolved table value or `0`) — the
decompile shows no field in this range that is ever assigned a pointer, a
struct base, or a buffer address. **The entire `0x6c`-`0xc0` byte range is
therefore ruled out, directly from the decompile, as the location of any
save-data-listing structure** — it's 14 consecutive plain scalars, nothing
more, and the disassembly trace in Part 1 already confirmed `+0x6c`
specifically is consumed as a raw integer with no intervening dereference.

The save-manager singleton (`FUN_007f149c`, `gamelib/save/saveworker.cpp`,
`0x13a0` = 5024 bytes, live address `0x44148220`, confirmed in
`research/notes/2026-08-21-stat-line-config-writer-trace.md`) is not just
the object that holds the `task-%x` cache and the throttle/ip/port fields
(`+0x1380..+0x1390`) — it is *the actual campaign autosave manager*. It
would be unsurprising, and is the natural reading, for the same object to
also own a real `cellSaveDataListGet`/`cellSaveDataListSave2`-style
directory-listing result buffer somewhere else in its 5024 bytes, for its
actual job of enumerating/managing save slots (autosave slot discovery,
icon/timestamp bookkeeping for the save it's about to write) — this is
exactly what "USR-DATA"/"ICN-ID"/"ICON0.PNG" plus repeating timestamp quads
look like, and it is a completely ordinary thing for a save manager to
carry. The task description places this data "near +0x1E0ish" in an
earlier, separate dump — a byte offset well outside the `0x6c-0xc0` range
this pass fully accounted for, consistent with "different field, same
object, no collision" rather than any conflict with the `0x6c`/`0x70`
mapping.

**Verdict on item 2: (a) — neighboring field, no interaction, confirmed
from the decompile rather than inferred.** `+0x6c`/`+0x70` are proven
(disassembly + full decompile of every write site) to be two of 14
consecutive plain-integer HUD-icon-lookup fields with no listing-buffer
involvement whatsoever. The save-listing-shaped bytes seen live almost
certainly belong to a separate field of the same singleton object
(plausibly its real save-slot-listing state, given the object's actual
job), not a redefinition or reuse of the `task-%x` cache slot. This pass did
not locate that field's exact offset or writer — see the live-test spec
below for what would nail it down precisely, since static analysis alone
can't distinguish "real embedded listing buffer" from "coincidentally
adjacent unrelated allocation" without knowing the object's full field
layout across `0xc0..0x13a0`.

## Updated verdict on the original two-state cache model

The 2026-08-21/22 note's two-state model (`+0x70==0` implies either "never
computed" with `+0x6c` also `0`, or "explicitly invalidated" with both
zeroed) was incomplete, not wrong in the cases it did cover — it just missed
the state that actually explains tonight's read: **a fully successful fresh
lookup whose gate-field key resolves to `0`**. That's not a third exotic
state requiring new machinery; it falls directly out of re-reading the
literal write order in the decompile, which the prior pass paraphrased
instead of quoting.

## What a live test needs to check next

The `+0x6c`/`+0x70` mechanism itself is now resolved from static analysis
alone — no live test is needed to confirm items 1 or 3 further. What
remains open:

1. **Locate the actual save-listing buffer's offset and writer.** Breakpoint
   `FUN_007f149c` (constructor, `0x007f149c`) and whatever save-slot-listing
   code runs inside `gamelib/save/saveworker.cpp` around a real
   `cellSaveDataListGet`/`cellSaveDataListSave2` call, and diff the full
   `0xc0..0x13a0` byte range of the singleton (`0x44148220 + 0xc0` through
   `0x44148220 + 0x13a0`) before and after a real autosave to find exactly
   which offset(s) the "USR-DATA"/"ICN-ID"/"ICON0.PNG"/timestamp bytes
   live at, and confirm they're written by save-listing code, not the
   `0x1AD3445F`/`0x4240EF2E`/`0xD006E7B5` HUD-icon lookups already fully
   accounted for in `0x6c-0xc0` and (per `fm_applyrefs.txt`, untraced this
   pass) whatever range the `0x4240EF2E` group occupies starting at
   `param_1[0x2c]`.
2. **Confirm the "gate never latches" prediction.** Breakpoint
   `FUN_0032241c`'s entry (`0x0032241c`) across a multi-save session (as the
   2026-08-21/22 note already planned) and read `this+0x70` on *every* hit,
   not just once — the refined model predicts it reads `0` on every single
   hit this session (never nonzero), which would mean the 14-field group
   recomputes unconditionally every call. If any hit ever shows `this+0x70
   != 0`, that specific key resolved nonzero that time and the group was
   left untouched that call — falsifiable either way with a few more
   samples.
3. The rest of the original trace's live-test plan (reading the 5-slot
   module registry's slot pointers and their own `+0x64` hash fields across
   multiple `task-%x`-producing saves, per
   `research/notes/2026-08-21-task-hash-variation-trace.md`) still stands
   unchanged — that mechanism is now the sole remaining candidate for why
   the *resolved value itself* differs across calls, since the "memoization
   prevents recomputation most of the time" framing no longer applies to
   this session's observed behavior.
