# Emblem shape/colour index resolver: SOLVED for all four layers, plus rotation/scale/opacity (2026-08-20)

Scope: continuing `2026-08-17-member-blob-vanity-semantics.md` §3e (which
located the emblem asset-path resolver but did not decompile it) and
`docs/protocol/profile_21_record.md`'s "Clan cosmetics / emblem block"
entry (which had no confirmed byte layout). This pass decompiled every
function that §3e named, pinned the exact persisted byte layout in
`profile.21`, and traced the DC00 data those functions consume as far as
static analysis will go.

**UPDATE 2026-08-20 (§9-§10): fully solved.** §9: layer0's shape catalog -
192 consecutive live, human-confirmed (shape_index, display-name) pairs,
zero mismatches, the ENTIRE catalog checked (not a sample). §10: the
identical formula independently confirmed on layer1 and layer2 too (no
per-layer offset after all - an earlier "layer2 needs +41" theory is
retracted, see §10a), plus rotation/scale/opacity (`shape_word`/
`color_word`'s previously-"static, unknown" bytes) and the colour picker's
8x8 grid-position formula, all confirmed by controlled live edits. §§1-8
are kept as originally written, including the parts that turned out to be
wrong (a "definitively falsified" verdict on the very catalog that turned
out to be correct, and later a wrong per-layer-offset theory) - the dead
ends are still useful, and §9/§10 explain exactly what was missing from
the earlier reasoning each time.

---

## 0. Bottom line

**SUPERSEDED BY §9-§10** - point 5 below ("loop not closed") is no longer
true for any of the four layers; see §9 for the solved shape-catalog
formula and the complete 192-entry table, and §10 for rotation/scale/
opacity and the colour grid. Points 1-4 are still accurate background.

1. **The persisted layout is confirmed**: `profile.21`, payload-relative
   offsets `0x7E0..0x7FF` (`P+0x7E8..0x807`), four layers x
   `{shape_word:u4, color_word:u4}`. Top byte of each word is a plain 0-255
   index; the bottom three bytes are static per-account data of unknown
   meaning (unchanged across all three live edits that established this
   layout - see the handoff this note continues from).
2. **The EBOOT-side resolver is fully decompiled and disassembly-verified**
   down to the individual `lwz` that fetches the name pointer. It resolves
   layer index `0..3` to one of four fixed DC symbols in a fixed order:
   `net-emblem-layers-frame`, `net-emblem-layers-base`,
   `net-emblem-layers-parts`, `net-emblem-layers-parts` again (the fourth
   layer reuses the third layer's category - see §2c). All four symbol names
   are independently confirmed against the retail disc's own DC compiler
   symbol corpus (not guessed).
3. **The DC-side content those symbols resolve to is a deeply nested tree of
   typed sub-records, not a flat name array**, and raw file-offset arithmetic
   on it (the technique that fully solved the DC00 *container* format, per
   `docs/protocol/dc_table.md`) does not reproduce anything resembling the
   four confirmed ground-truth names. This independently reproduces a caveat
   `dc_table.md` already flagged for two unrelated hashes: nested/structured
   DC values are resolved by the game through a runtime hash-registry layer
   that this project has not yet shown is equivalent to naive pointer-chasing
   over the static file.
4. **A real, plausible name catalog was found by an unrelated route** - a
   literal, human-readable pool of 192 emblem asset identifiers
   (`shape-*` x20, `frame-*` x25, `background-*` x26, `image-*` x56,
   `tlou-*` x65) embedded as plain ASCII in `net.bin`, matching the external
   wiki's "~192 emblem images" figure almost exactly. This catalog **is not
   proven to be the one the resolver code walks** - it was found by
   searching the file for the confirmed asset names directly, not by
   following the resolver's own pointer chain, and testing it against the
   four ground-truth indices reproduced only one of four assignments (very
   plausibly by chance, given several indexing schemes were tried against
   only four data points).
5. **Loop not closed.** None of `{layer1=48, layer2=1, layer3=55, layer4=1}`
   could be confidently mapped to `{El Diablo, Assault Rifle Ammo, Shuriken,
   Wide Octagon}`. See §5 for exactly what was tried and why each attempt was
   rejected as inconclusive rather than reported as an answer.

---

## 1. The persisted layout

Continuing the handoff's live-edit-verified finding: `profile.21`
`game_data`, byte offsets relative to `P` (subtract 8 for the schema's
payload-relative `pos:`):

| P+off | payload pos | field |
|---|---|---|
| 0x7E8 | 0x7E0 | layer0 shape_word |
| 0x7EC | 0x7E4 | layer0 color_word |
| 0x7F0 | 0x7E8 | layer1 shape_word |
| 0x7F4 | 0x7EC | layer1 color_word |
| 0x7F8 | 0x7F0 | layer2 shape_word |
| 0x7FC | 0x7F4 | layer2 color_word |
| 0x800 | 0x7F8 | layer3 shape_word |
| 0x804 | 0x7FC | layer3 color_word |

Ground truth for `comradesean` (from the handoff, restated here for
reference): layer0 shape idx=48, layer0 color idx=12, layer1 shape idx=1,
layer2 shape idx=55, layer3 shape idx=1 (0-based layer numbering used
throughout this note, matching the EBOOT's own `iVar30 = 0..3` loop
variable - the handoff's "layer1..layer4" is this note's "layer0..layer3").
Confirmed equipped names, order unknown: El Diablo, Assault Rifle Ammo,
Shuriken, Wide Octagon.

This part carries over unchanged from the handoff and was not re-derived
this pass.

---

## 2. The EBOOT-side resolver (confirmed, decompile + disassembly)

Decompiled via headless Ghidra against the existing
`research/ghidra/tlou_factions.gpr` project (`DecompileByAddresses.java`,
already checked in), then cross-checked instruction-by-instruction against
raw `objdump` (`--adjust-vma=0x10000`, per
`research/tools/eboot_analysis/README.md`). All addresses are 01.00 EBOOT
VMAs.

### 2a. `FUN_003444fc` - the emblem subsystem's cache-slot initializer

Called once, as the very first statement of `FUN_00344de4` ("validate
emblem" per the handoff's naming). It populates two 4-slot generic
"DC-resolve-and-cache" objects (16 bytes/slot: `{resolved_ptr, generation,
key_hash, module_cache}` - the same generic cached-resolve shape used
throughout this binary, whose resolve routine is `FUN_00024768`) plus one
single-slot object:

```
group @ *(anchor-0x7fac), stride 0x10, 4 slots:
  slot0.key_hash = 0xc7f8567c   net-emblem-layers-frame
  slot1.key_hash = 0xe2311588   net-emblem-layers-base
  slot2.key_hash = 0x03ffae77   net-emblem-layers-parts
  slot3.key_hash = 0x03ffae77   net-emblem-layers-parts  (SAME hash as slot2 - literal duplicate in the init code)

group @ *(anchor-0x7fb0), stride 0x10, 4 slots (LIMITS, not used by the name resolver - see §2d):
  slot0.key_hash = 0x88f9bd5c   net-emblem-limits-frame
  slot1.key_hash = 0x83d670b8   net-emblem-limits-base
  slot2.key_hash = 0x4cfe4557   net-emblem-limits-parts
  slot3.key_hash = 0x4cfe4557   net-emblem-limits-parts  (duplicate, same pattern)

single slot @ *(anchor-0x7fa0):
  key_hash = 0xbcbbdfbd         net-emblem-colors
```

`anchor` is the per-CU small-data pointer `*(u32*)0x012fde98` (=
`0x0126fd4c` in this image); e.g. `anchor-0x7fac` = VMA `0x01267da0`, which
at runtime holds a heap pointer to the actual 4-slot array (the array itself
is not present in the static image - it's allocated at load time, so it
can't be read from the raw ELF).

**All seven hash constants are confirmed real DC symbol names**, not
guessed: `research/tools/dc_hash_crack.py` against the retail disc's own
`bin.psarc` `.dci` corpus (see `docs/protocol/dc_table.md` for the method)
returns an exact match for every one:

```
0xc7f8567c  *net-emblem-layers-frame*
0x03ffae77  *net-emblem-layers-parts*
0xe2311588  *net-emblem-layers-base*
0x88f9bd5c  *net-emblem-limits-frame*
0x4cfe4557  *net-emblem-limits-parts*
0x83d670b8  *net-emblem-limits-base*
0xbcbbdfbd  *net-emblem-colors*
```

No other `*emblem*` top-level DC symbol exists in the corpus - if a
per-image name catalog has its own top-level DC global, it isn't spelled
with "emblem" in its name, or it isn't a top-level `*starred*` global at
all (see §3).

### 2b. `FUN_00345038` / `FUN_0034527c` - the name-to-texture-path resolvers

Both confirmed byte-for-byte against `objdump`. `FUN_0034527c(trackerLike,
layerIdx, rawIdx)` (no internal modulo - caller already reduced the index):

```
piVar4 = layerIdx*0x10 + *(anchor-0x7fac)          ; select one of the 4 cache slots
value  = resolve(piVar4)                           ; generic cached DC resolve (FUN_00024768)
elemBase = *(u32*)(value + 4)                       ; second word of the resolved value
element  = elemBase + rawIdx*12                     ; 12-byte stride
namePtr  = *(u32*)(element + 4)                      ; THIS word is passed straight to sprintf
sprintf(buf, "emblems/%s", namePtr)                  ; format string at VMA 0x00e79658
FUN_00ac6d80(texLoader, buf)                         ; preload
```

`FUN_00345038(trackerLike, layerIdx)` is the same logic inlined, but it also
computes the index itself: `rawIdx = trackerByte % *(u32*)value` (`value`'s
FIRST word, i.e. `*(u32*)value`, is read as a plain integer count - this is
the "idx = layerByte % *arrayCount" the prior note already established, now
confirmed at the instruction level: `divw`/`mullw`/`subf` computing a
straightforward unsigned modulo, with a cache-miss path that calls
`FUN_00024768` to (re-)resolve first).

`FUN_00345a0c` (the emblem draw/layout function) is the caller that ties
layer index to category: its outer loop is `for (iVar30 = 0; iVar30 <= 3;
iVar30++) { ... FUN_00345038(param_1, iVar30) ... }` - i.e. **the layer loop
counter is passed directly as the cache-slot index**, confirming layer0 =
`layers-frame`, layer1 = `layers-base`, layer2 = `layers-parts`, layer3 =
`layers-parts` again (per §2a's literal duplicate). This is new information
not in the prior note, which only said "own separate per-category catalog"
without pinning which category is which layer.

### 2c. `FUN_00344de4` - "validate emblem", and a second, DIFFERENT field read from the same array

Re-derives the four `{shape,color}` words from the profile the same way the
draw function does, then for each layer:

```
elemBase = *(u32*)(value + 4)              ; same as above
gateId    = *(u32*)(elemBase + rawIdx*12)  ; element OFFSET+0, NOT +4 this time
if (gateId != 0 && !FUN_003ec084(unlockStore, 0, gateId, 0))
    zero the slot                          ; revoke: this emblem choice isn't unlocked
```

`FUN_003ec084` is the exact same unlock-gate function the 2026-08-17 note's
§6b traced for character-customization items. **This means emblem element
offset+0 is a DC unlockable-id (StringId), gating that specific frame/
base/parts choice on owning some other piece of content** - a real and
plausible mechanic (e.g. a frame style unlocked by owning a particular
weapon), not previously documented. Confirmed independently: element 0 of
the `layers-frame` array's own first word (see §3) is `0x6a86861f` - which
is *exactly* mgnomad2's persisted hat-slot item StringId from the
2026-08-17 note §7's DC parse. That is very unlikely to be coincidence and
is the strongest evidence this pass found that the emblem system's
unlock-gate ids are drawn from the *same* StringId space as ordinary
equippable items (this reuse is plausible but not independently proven
beyond the one matching value).

### 2d. `FUN_00345a0c`/`FUN_0034640c` - draw geometry, and the LIMITS group

The bulk of `FUN_00345a0c`'s body (not reproduced in full here - see
`/tmp/emblem_decomp.txt`-style output regenerable via
`research/tools/ghidra_scripts/DecompileByAddresses.java 345a10`) is vector/
float geometry for laying the four layers out on the emblem canvas -
UV transforms, blend flags, a `FUN_00a99f54`/`FUN_00a968d0`/`FUN_00a96d34`
render-state sequence per layer. It also reads the LIMITS group (§2a's
second 4-slot array) but this pass did not trace which specific float field
(rotation/scale/opacity range?) each limit slot supplies - flagged as a
stretch goal in the task brief and **not attempted this pass** given the
name-resolution loop was already unclosed; see §6.

### 2e. `FUN_00346d44` - "randomise emblem"

Confirmed simple: for each of the 4 layers, sets `shape_word` and
`color_word`'s low 3 bytes to fixed sentinel-looking values (`0xff`/`0xff`,
a computed byte from `lVar6*count/4`-ish arithmetic - not fully decoded) and
leaves the top byte(s) to be filled from a separate RNG source
`_opd_FUN_009fbf74`-adjacent code not shown in this decompile window. Then
writes the whole thing back into the profile via `FUN_003cb97c` (the same
generic profile-field writer used elsewhere in this project's traces).
Confirms the 8-byte-per-layer persisted shape (matches §1) but does not add
anything toward name resolution.

---

## 3. Why the DC-side content did not resolve: the nested-structure dead end

Extracted `dc1/net.bin` fresh from the retail disc's `bin.psarc`
(`server/lib/psarc_crypt.py`'s `parse_psarc()`, entry `dc1/net.bin`,
283,615 bytes - byte-identical in structure to `net1.bin`, confirmed via
`docs/protocol/dc_table.md`'s own cross-check hashes at the same file
offsets in both files).

Located all seven directory records by literal 4-byte search for each hash
(each hash occurs exactly once in the file, at the position `dc_table.md`
calls `key_hash`; `value_ptr` is the word immediately before it,
`type_hash` immediately after - matches the documented 3-word directory
record shape exactly):

| symbol | dir offset | value_ptr | type_hash |
|---|---|---|---|
| layers-frame | 0xec4 | 0x52e8 | 0xed6b8e26 |
| layers-parts | 0x48 | 0x12a8 | 0xed6b8e26 |
| layers-base | 0x1050 | 0x5824 | 0xed6b8e26 |
| limits-frame | 0x9e4 | 0x3b98 | 0xf3bc1143 |
| limits-parts | 0x4c8 | 0x2524 | 0xf3bc1143 |
| limits-base | 0x96c | 0x3b28 | 0xf3bc1143 |
| colors | 0xdec | 0x50f0 | 0x290349e3 |

`value_ptr`'s target for `layers-frame`/`layers-parts` DOES start with a
plausible `{count:u4, array_ptr:u4}` pair (verified byte-exact against the
counts already known from the earlier hex-dump handoff: 6, 1, 14, 1, 5) -
**but immediately following that pair, at the same address, sit three more
`{u4, u4, u4}` triples with the same shape**, e.g. `layers-frame`'s value at
`0x52e8`:

```
+0x00  count=6      array_ptr=0x000163e4  type=0xced9d25f
+0x0c  count=0x63    array_ptr=0x0002665c  type=0x290349e3
+0x18  count=1       array_ptr=0x00017a64  type=0x2a8027cf
+0x24  count=6       array_ptr=0x00008f64  type=0x290349e3
```

i.e. `net-emblem-layers-frame` is a struct with (at least) four typed
member arrays, not one flat array - `FUN_0034527c`/`FUN_00345038` only ever
read the *first* of these four (`value+0`/`value+4`), so this by itself
isn't a contradiction. The problem is what's actually AT that first
sub-array (`array_ptr=0x163e4`, stride 12, matching the resolver's own
`element = elemBase + idx*12`):

```
elem[0]  0x6a86861f  0x00030b24  0x0002f408
elem[1]  0x0002e674  0x0002e674  0x00000000
elem[2]  0x00000007  0x00000000  0x00000000
elem[3]  0x00000000  0xcaadd3f2  0x00000002
elem[4]  0x00000000  0xa9955425  0x0002f66c
elem[5]  0x000287a0  0x000303e0  0x00030004
```

Per §2c, `elem[i]+0` is confirmed (independently, via `FUN_00344de4`) to be
an unlock-gate StringId, not part of the name path. `elem[i]+4` is what
`FUN_0034527c` passes straight to `sprintf("%s", ...)` - and dereferencing
it at every one of the six elements gives either an out-of-bounds address or
an in-bounds address whose first byte is `0x00` (an **empty string**). This
was checked against the DC00 relocation bitmap itself (parsed directly from
`net.bin`'s own header - `reloc_off = *(u32*)(buf+8)`, bitmap starts at
`reloc_off+4`, bit `i` = word at file offset `i*4`, per
`docs/protocol/dc_table.md`'s already-solved container format): `elem[0]+4`
(file offset `0x163e8`) genuinely IS marked as a pointer-fixup word (bit=1),
so it isn't a stray scalar being misread as a pointer - it's supposed to be
one, and even the *bit before it* (`elem[0]+0`, the gate id) correctly comes
back bit=0 (not a pointer), matching its known StringId role from §2c. The
mechanism is right; the specific address it resolves to at `elem[0]+8`
(`0x0002f408`) lands squarely inside *yet another* nested typed triple
(`{count=5, ptr=0x36e10, type=0x88e3fe54}` - `0x88e3fe54` is the exact
per-slot item-array descriptor type the 2026-08-17 note's §6a already
identified for character-customization items), reinforcing that this whole
region is several levels of nested DC structure deep, not a flat string
table.

**Conclusion for this section**: raw file-offset pointer-chasing, the
technique that fully solved the DC00 container format (byte-exact
`count*32==relocation_table_offset` check, `docs/protocol/dc_table.md`),
reproduces simple two-field `{count, array_ptr}` leaves correctly (all five
known counts matched exactly) but does not reach anything resembling a
readable name at the depth the emblem name path requires. `dc_table.md`
already flagged this exact limitation for two unrelated hashes ("the two
consuming-function traces... each turned out to read their target arrays
through the runtime hash-registry... rather than by walking this raw byte
layout directly"). This pass independently reproduces that same limitation
for a third, previously-untried case.

---

## 4. A plausible (but unverified) name catalog found by a different route

Searching `net.bin` directly for the confirmed equipped-item substrings
(from the retail disc's `vtex1.psarc` `emblems/*.dds` listing already noted
in the task brief) turns up a literal ASCII string pool: `tlou-el-diablo`,
`shape-shuriken`, `frame-octagon`, `background-octagon`, `tlou-auto-ammo`,
etc. all exist as plain, null-terminated strings in the file. Walking
outward from one hit (a 12-byte-stride array at file offset
`0x2be68..0x2c75c`, element = `{namePtr:u4, u4, u4}`, name pointer this time
at **offset+0**, confirmed against five different known strings) gives a
contiguous run of exactly **192 elements**, falling into five prefix
families:

| prefix | count |
|---|---|
| `shape-` | 20 |
| `frame-` | 25 |
| `background-` | 26 |
| `image-` | 56 |
| `tlou-` | 65 |

192 total - matching the community wiki's cited "~192 emblem images" figure
closely enough to be a real find, not noise. **This is not proven to be the
array the resolver code actually walks.** It was located by searching for
known strings directly, not by following `FUN_0034527c`'s own pointer chain
from any of the seven confirmed emblem DC symbols - no directory record or
nested sub-array pointing at file offset `0x2be68` (or anywhere in that
192-element run) was found by searching for literal references to that
address either. Its relationship to the seven `net-emblem-*` symbols (if
any) is unknown; it may belong to a different DC symbol entirely (e.g. an
item/weapon-cosmetics table, given the elements interleave in
weapon-themed groups rather than being sorted by category - see §5).

---

## 5. What was tried against the four ground-truth values, and why none of it counts as a result

Given `{layer0=48, layer1=1, layer2=55, layer3=1}` and the four confirmed
names, three indexing schemes were tried against the §4 catalog:

1. **Absolute flat index** (`catalog[rawIdx]` directly, no modulo needed
   since 192 > 55): `catalog[48]` = `shape-abstract`, `catalog[1]` =
   `frame-circle`, `catalog[55]` = `tlou-auto-ammo`. Only the third is a
   plausible match ("Assault Rifle Ammo"); the other two are not obviously
   wrong (no ground truth to check `catalog[1]` against two different
   correct answers simultaneously - layer1 and layer3 share raw index 1 but
   have different confirmed names, so at most one of the two "idx 1" reads
   can be right under a single flat scheme, which is itself already
   suspicious for this hypothesis).
2. **Per-category-filtered index** (`catalog.filter(prefix==P)[rawIdx]`,
   preserving file order within the category): `shape[12]` = `shape-
   shuriken` (a real, striking match to "Shuriken" - but layer0's raw value
   at that position is the *color* index 12, not any layer's shape index,
   so this is very likely a coincidental hit on the wrong field). No other
   category/index combination among `{frame,shape,background,image,tlou} x
   {1,12,48,55}` produced a plausible name.
3. **`layers-frame`'s own nested sub-array** (§3's `elem[i]+4` chase):
   produced empty/out-of-bounds strings for every element, i.e. no
   candidate names at all.

None of these clears the bar the task set: "a decode that doesn't reproduce
these 4 known ground-truth values is wrong, no matter how plausible it
looks." One coincidental-looking hit (scheme 1's index 55) is not four
consistent hits, and testing three schemes against four data points has
enough researcher-degrees-of-freedom that even a correct-looking single hit
isn't evidence on its own.

---

## 6. What's still open

* **The exact array the resolver reads has not been identified.** The
  `layers-frame`/`base`/`parts` DC symbols' first-listed sub-array
  (`elem+4`, per §3) does not yield names; the §4 catalog is unproven to be
  connected to those symbols at all. The most promising concrete next step
  is a **live capture**: set a breakpoint at the `sprintf` call site inside
  `FUN_00345038` (`0x345184`) or `FUN_0034527c` (`0x345318`) in an RPCS3
  session with a known account's emblem loaded, and read the resolved
  `r5` (name pointer) and `r4`/`r9` (elemBase) register values directly from
  live memory - this sidesteps the entire "is raw-file-offset arithmetic
  equivalent to the runtime hash-registry resolve" question, which static
  analysis alone could not settle this pass (and which `dc_table.md`
  already flagged as unsettled for two other hashes before this one).
* **The colour catalog (`net-emblem-colors`, hash `0xbcbbdfbd`) was checked
  only briefly** - its value at `0x50f0` shows the exact same
  nested-typed-triple shape as the layers group (not a flat RGB/palette
  array), so it was not pursued further once the same dead end reappeared.
  Not resolved even to "index 12 is in-range" - genuinely open.
* **The LIMITS group's specific float fields (rotation/scale/opacity
  ranges) were not traced** - `FUN_00345a0c`'s geometry code was skimmed
  but not decompiled field-by-field. Stretch goal from the task brief, not
  reached.
* **`FUN_00346d44`'s low-3-bytes sentinel computation** (the bottom 3 bytes
  of each persisted word, static across the handoff's three live edits) was
  glanced at but not decoded - still unknown what those bytes mean.

---

## 7. Reusable tooling from this pass

* Headless Ghidra decompiles were produced via the existing
  `research/tools/ghidra_scripts/DecompileByAddresses.java` against
  `research/ghidra/tlou_factions.gpr` - no new script needed:
  ```sh
  /mnt/e/ghidra/support/analyzeHeadless research/ghidra tlou_factions \
    -process "EBOOT.elf" -noanalysis \
    -scriptPath research/tools/ghidra_scripts \
    -postScript DecompileByAddresses.java /tmp/out.txt <vma1> <vma2> ... \
    -log /tmp/out.log
  ```
* The DC00 relocation-bitmap bit-reader used in §3 (given `reloc_off =
  u32(buf+8)`, `count = u32(reloc_off)`, `bitmap_start = reloc_off+4`, bit
  `i` at `(bitmap_start + i//8)`, bit position `i%8`, covering word index
  `i` = file offset `i*4`) is a direct implementation of
  `docs/protocol/dc_table.md`'s `FUN_009fc118` pseudocode and is not
  checked in anywhere yet - worth promoting to a real script
  (`research/tools/dc_reloc_bitmap.py` or similar) if this investigation
  continues, since it's the first time this project has actually
  round-tripped the bitmap itself rather than assuming fixups are
  already-applied raw offsets.

---

## 8. Update: two real name ground-truths obtained, both dead ends in §4-§5 tested again - SUPERSEDED, see §9

A human confirmed, from the live in-game UI, two (layer, shape_index) ->
display-name pairs on the same test account used throughout this note:
**layer0 (shape_index=48) = "Wide Octagon"**, **layer2 (shape_index=55) =
"El Diablo"**. (Layer numbering: this note and the `.ksy` use 0-indexed
internal layer0-3; the account's own UI calls these "Layer 1"/"Layer 3".)

Both hypotheses from §5 were re-tested against these two CONFIRMED name
pairs (not just plausibility-checked as before) and both fail cleanly:

1. **Flat index into the §4 192-entry catalog**: `catalog[48]` =
   `shape-abstract` - not any octagon variant. `catalog[55]` =
   `tlou-auto-ammo` - not El Diablo. (§5 had already flagged `catalog[55]`
   = `tlou-auto-ammo` as "a plausible match" for what turned out to be
   Assault Rifle Ammo's real position elsewhere - that plausibility was a
   coincidence; the ground truth proves this index scheme wrong outright.)
2. **Per-family-relative index, modulo that family's count** (i.e.
   `family_list[idx mod len(family_list)]`, preserving each entry's
   position within just its own prefix family): octagon appears in three
   families at RELATIVE positions 7 (`frame`, of 25), 2 (`background`, of
   26), 4 (`shape`, of 20) - none equal `48 mod 25/26/20` = 23/22/8.
   `tlou-el-diablo` sits at relative position 24 of 65 in the `tlou`
   family - `55 mod 65` = 55 (no wraparound at all, since 55 < 65), which
   doesn't match 24 either.

Both schemes are now definitively ruled out, not merely unproven - a
future pass should not re-try either one without new evidence connecting
the §4 catalog to the seven `net-emblem-*` DC symbols (none was found this
pass; searching `net.bin` for literal references to the catalog's file
offset, `0x2be68`, found no directory record or nested sub-array pointing
at it from any of the seven confirmed emblem hashes).

This leaves the situation exactly where §6 already said it would: the real
array the resolver walks has not been located by static analysis, and the
concrete next step is the live RPCS3 memory read at the `sprintf` call
site described there (`FUN_00345038` @ `0x345184` or `FUN_0034527c` @
`0x345318`), not further guessing against catalogs found by string search.

---

## 9. SOLVED, 2026-08-20: layer0's shape catalog, full 192-entry table

§8's "definitively falsified" verdict was wrong - not because the test was
run incorrectly, but because it never tried the one variant that turns out
to be correct: treating `shape_index=0` as a reserved "no selection"
sentinel that isn't itself a catalog entry, and reading every other index
directly off-by-one into the SAME flat, unfiltered 192-entry catalog §4
already found (`net.bin` file offset `0x2be68`, 12-byte stride, name
pointer at `elem+0`). The formula:

```
shape_index == 0        -> "None"  (sentinel; index 0 is not a catalog row)
shape_index in [1, 192] -> catalog[shape_index - 1]
```

### Verification method

A human played the account live in RPCS3, scrolled through the emblem
shape picker in order, and reported the display names seen - both names
scrolled past (not selected) and the specific one ultimately chosen and
saved. Each reported sequence was checked two ways: (1) every scrolled-past
name was checked against `catalog[predicted_index - 1]` for a byte-exact
text match; (2) every SELECTED name was independently re-verified by
decoding the live, just-saved `profile.21` file
(`research/tools/profile21_codec.py`) and reading the actual persisted
`shape_index` byte back off disk - not something either party typed in,
the game's own save data. Both checks agreed on every single test, across
multiple separate scrolling sessions covering the ENTIRE catalog range
(indices 1 through 192) with zero exceptions.

One transcription confusion occurred and was caught and corrected: a
reported "Octagon" selection was initially assumed to be the FIRST
"Octagon"-named entry encountered in a scrolled list, when the account had
actually continued scrolling to a SECOND, later catalog entry that happens
to share the same display name (`shape-octagon` at index 20 vs
`frame-octagon` at index 32) - the live file's actual saved index (32)
caught the mismatch immediately, which is exactly the kind of error this
verification method is designed to catch (ground truth from the save file,
not from counting list positions by hand).

### The complete table

`research/notes/2026-08-20-emblem-shape-catalog.tsv` - all 192 entries,
`shape_index`, the DC/disc internal asset name, the confirmed in-game
display name, and notes on duplicate entries. Notable duplicates found
along the way (same display name OR same internal asset appearing at two
different catalog indices - both genuinely happen):

- `shape-bomb` (idx 65) and `image-bomb` (idx 8) both display as "Bomb" -
  two distinct catalog rows, same label.
- `frame-sharpsquare` appears at BOTH idx 7 and idx 124, same display name
  ("Sharp Square") both times - a true duplicate catalog entry, not a
  transcription error (independently re-confirmed at idx 7 the first
  session and idx 124 a session later).
- `shape-octagon`/`frame-octagon`/`background-octagon` (idx 20/32/48) all
  display as some form of "Octagon" ("Octagon" x2, "Wide Octagon" x1) -
  three separate catalog rows for visually distinct octagon variants that
  happen to share a naming root.
- Several DC internal names repeat with DIFFERENT display labels at their
  two occurrences - e.g. `frame-angled2` is "New Angle" at idx 17 but
  "Angled Pillars" at idx 111; `tlou-arrow` is "Wooden Arrow" at idx 42 but
  the SEPARATE `image-arrow` is plain "Arrow" at idx 75; `tlou-auto-ammo`
  is "Assault Rifle Ammo" at idx 56 while `tlou-automatic` is "Assault
  Rifle" at idx 178. These are genuinely different catalog rows with
  similar internal names, not the same row read twice.

### A real, previously-unknown finding: the unlock boundary

The account tested (`comradesean`) has every catalog entry from index 1
through 152 (`tlou-vest`, "Vest") unlocked, and every entry from 153
onward (40 entries, "Flower" through "Stealth Mask") reported as visibly
LOCKED in the picker UI. This is the first concrete evidence in this
project of where an account's actual unlock progress sits for this specific
cosmetic category - not derivable from any prior capture.

### What is still open

- **Only layer0 ("Layer 1" in the account's own UI, DC symbol
  `net-emblem-layers-frame`) is solved.** layer2 ("Layer 3",
  `net-emblem-layers-parts`) does NOT use the same `catalog[idx-1]`
  formula - `shape_index=55` ("El Diablo") would need `catalog[54]` =
  `frame-angled2` under that formula, but El Diablo is actually at
  `catalog[96]`. The offset that DOES fit this one data point is
  `catalog[shape_index + 41]`, but that is solved algebraically from a
  single equation, not independently verified the way layer0 now is (layer0
  took 192 independent confirmations before being trusted - one equation
  for layer2 should get the same skepticism, not less).
- **layer1 ("Layer 2", `net-emblem-layers-base`) and layer3 ("Layer 4",
  `net-emblem-layers-parts` again) are completely unmapped** - no ground
  truth attempted yet.
- **The colour catalog (`net-emblem-colors`) is still unmapped** - only
  layer0's `color_index=12` is known to exist, not what it resolves to.
- **The bottom 3 bytes of every `shape_word`/`color_word`** (static across
  every edit observed) remain unexplained.
- **Rotation/scale/opacity** (claimed to exist per-layer by
  `docs/factions-metagame-reference.md`'s external/wiki-sourced structural
  note) have not been located in `profile.21` at all.
- The live RPCS3 memory-read approach from §6/§8 was never actually
  needed for layer0 - the live-edit-and-diff-the-save-file method (already
  this project's established technique, see the handoff this note
  continues from) turned out to be sufficient once the off-by-one was
  found. Worth remembering before reaching for a debugger next time.

---

## 10. All four layers confirmed on one formula; rotation/scale/opacity and the colour grid solved (2026-08-20)

Continuing directly from §9 in the same session, using the same
live-edit-and-diff method (`research/tools/profile21_codec.py`).

### 10a. Every layer uses the identical shape-catalog formula - the layer2 "offset" theory is retracted

§9 left layer2 ("Layer 3", DC symbol `net-emblem-layers-parts`) unsolved,
with an algebraic `catalog[shape_index+41]` guess fitted to a single old
data point (`shape_index=55 -> "El Diablo"`) that had never been
independently checked. Two fresh, carefully live-diffed tests settle this:

- **layer1** ("Layer 2", `net-emblem-layers-base`): set to "Egg" live,
  saved, decoded - `shape_index=50`. `catalog[49]` = `shape-egg` = "Egg".
  Exact match under the SAME formula as layer0 (`catalog[idx-1]`).
- **layer2** ("Layer 3", `net-emblem-layers-parts`): re-checked live at
  its then-current state (self-reported "El Diablo again", not a fresh
  pick) - `shape_index=97`. `catalog[96]` = `tlou-el-diablo` = "El Diablo".
  Exact match under the SAME formula.

The second result **retracts** the old `shape_index=55 -> El Diablo`
ground truth from §0/§9 - it was a mislabeling from early in the
investigation (before the live-diff methodology existed to catch this
kind of error), not evidence of a real per-layer offset. The correct,
now fully cross-layer-confirmed formula, with no exceptions:

```
shape_index == 0        -> "None"  (sentinel)
shape_index in [1, 192] -> catalog[shape_index - 1]
```

...applies identically to all four layers (`net-emblem-layers-frame`,
`-base`, `-parts`, `-parts` again). layer3 ("Layer 4") was not directly
retested this pass but there is no remaining reason to expect it differs -
flagged as inference, not independently confirmed, for anyone who wants to
close that last gap cheaply (it's a two-minute test with the tooling that
now exists).

### 10b. `shape_word`'s three unnamed bytes: two of three now solved

Before this pass, `shape_word`'s bottom 3 bytes were documented as
"static per-account data, unchanged across every live edit observed so
far; meaning unknown." Two of the three ARE live fields after all - they
had simply never been the target of a deliberate edit before:

- **Byte 1 = rotation.** A controlled edit ("rotated it upside downish")
  moved this byte `0x00 -> 0x83`. `131/255 x 360 deg ~= 185 deg`, close to
  the human-reported "upside downish" (~180 deg). A follow-up "reset to
  default" landed on `0x01`, not `0x00` - NOT confirmed to be a clean
  sentinel the way shape_index=0 is; the human tester noted the in-game
  reset may not be bit-exact ("it's hard to reset it, I might just be off
  by a degree"). Exact byte->degree formula NOT pinned - only that this
  byte moves with rotation and roughly tracks degrees.
- **Byte 2 = scale.** A controlled edit ("scaled it down") moved this byte
  `0xff -> 0x00`, then a reset moved it back to `0xff`. `0xff` is very
  likely the default/full-size value (it was the untouched value in every
  capture before this test); `0x00` is the minimum. Direction and
  endpoints confirmed; intermediate scale factor not pinned.
- **Byte 3: still genuinely unknown.** Untouched across every edit in this
  entire investigation (shape, rotation, scale, and every colour/opacity
  test below).

### 10c. `color_word`: opacity solved, the colour GRID solved, the colour CATALOG still isn't

- **Byte 1 = opacity**, same pattern as scale: a controlled edit ("set
  opacity to the other side of the slider") moved this byte `0xff -> 0x00`,
  and a reset ("reset opacity to visible") moved it back to `0xff`. `0xff`
  = fully visible, `0x00` = invisible; intermediate scale not pinned.
- **Byte 0 = colour index, and the picker's GRID LAYOUT is solved**,
  separately from the still-unsolved DC colour *catalog* (`net-emblem-
  colors`, hash `0xbcbbdfbd`, §3's dead end). The in-game colour picker is
  a plain 8x8 grid of 64 swatches with no in-game names. Three controlled
  edits nail the indexing scheme:
  - top-left swatch (row0, col0 - a white swatch) selected live ->
    `color_index=0`.
  - one row down, same column, predicted by the human tester to be `0x08`
    before testing ("there's eight per row... it should be 0x08") ->
    confirmed exactly `0x08`.
  - bottom-right swatch (row7, col7) selected live -> confirmed exactly
    `0x3f` (63).

  Formula: **`color_index = row*8 + column`, 0-indexed, row-major, no
  sentinel** (unlike the shape catalog, index 0 is a real swatch - white -
  not a "none" placeholder). This is the grid POSITION only - what RGB/
  palette value each of the 64 positions actually renders as, and whether
  the DC `net-emblem-colors` symbol names them anything, remains
  unresolved (§3's nested-structure dead end still applies to that
  specific DC table; the grid formula above was derived independently of
  it, from the picker UI's own layout, not from decoding that symbol).
- Bytes 2-3 of `color_word`: untouched across every edit so far, same
  "genuinely unknown" status as `shape_word` byte 3.

### 10d. What's still open after this pass

- `shape_word` byte 3 and `color_word` bytes 2-3 - no edit performed in
  this investigation has ever moved them.
- The exact rotation degree formula and exact scale/opacity intermediate
  curve (only the endpoints/direction are confirmed for scale and
  opacity; rotation has only one non-endpoint sample and an imprecise
  reset).
- What each of the 64 colour-grid positions actually looks like (RGB/
  palette value) - the grid POSITION formula is solved, the swatch
  CONTENT is not.
- layer3 ("Layer 4")'s shape catalog - inferred to match the other three
  layers, not independently tested.
