# Testing the DLC-entitlement hypothesis for `promotion_flags_1e74`

Date: 2026-08-21. Static only, no live RPCS3 session. Follows up
`research/notes/2026-08-21-profile21-zero-region-walk.md`, which found six
BE u32 words at `P+0x1E74..0x1E8B` (`promotion_flags_1e74`) that are
genuinely non-zero and per-account, but for which no EBOOT writer/reader
could be found — and whose "working theory" (a DC-side write with no EBOOT
code path) was explicitly flagged as unproven. That prior trace ran only
against the **01.00** EBOOT
(`/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The
Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf`). 01.00 has no visible DLC
UI/detection, unlike 01.11, so it was worth independently checking whether
01.00 is simply blind to a writer that exists only in the 01.11 build.

Binary used for this pass: `/mnt/f/rpcs3_testing/TLOU-FACTIONS
1.11/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf` (md5
`181d8d9534165bcde771a43fc16d9d78`, ~20MB). Program headers (`readelf -lW`):
LOAD #0 file-offset `0x000000` → VMA `0x00010000`, filesize `0x121ef68`
(R E); LOAD #1 file-offset `0x1220000` → VMA `0x01230000`, filesize
`0x1270d0` (RW). `file offset = VMA − 0x10000` holds for both segments, same
as 01.00. This project's `research/tools/eboot_analysis/eb.py` for 01.11 had
stale 01.00-sized `SEGS` left over from an earlier session; it was corrected
against the values above before use, and `scan_imm.py`'s
`TEXT_VA/TEXT_SZ/R2` (`0x01338de0`) were confirmed already correct for this
binary.

The disassembly used throughout, `powerpc64-linux-gnu-objdump -D -b binary
-m powerpc:common64 -EB --adjust-vma=0x10000` over the raw executable
segment, was generated fresh for this pass (this repo's checked-in
`research/disasm/full.asm` is 01.00 only). The system's plain `objdump` build
has no PowerPC support at all (`can't use supplied machine
powerpc:common64`) — `powerpc64-linux-gnu-objdump` (from the
`binutils-powerpc64-linux-gnu` package) does, and was used for every
disassembly step below.

## 1. Re-finding the profile record's universal accessor in 01.11

01.00's accessor is `FUN_003cb89c` (436 call sites, per the prior note). Its
01.11 VMA is not assumed — this is a recompile, not a fixed-delta rebuild
(per `research/tools/eboot_analysis/README.md`'s own warning). It was
re-derived by signature:

1. Located every `stw/lbz/... offset,820(rX)` site (`820` = 0x334, the known
   `career_stats[0].score_total` byte offset — struct layout offsets survive
   a recompile even though code addresses don't).
2. Wrote a small per-function register-dataflow tracker (tracking `bl`
   returns through `mr`/`clrldi`/`extsw`/`addi`-with-constant chains, reset
   at each `stdu/stwu r1,-N(r1)` prologue) and ran it over ALL `bl` targets,
   not just the offset-820 sites, to find which single callee's return value
   most often feeds these known-field immediate accesses.
3. `0x3e6adc` stood out immediately on inspection, independent of the
   frequency test: it has the exact "resolve-once, cache, return `this+200`"
   shape (`addis r29,r3,1` / TLS-style flag check at `-3772(r29)` / one-shot
   init call `bl 0xb0c1d8` / constructor call `bl 0x3e6a58` / `addi
   r3,r31,200`) that a lazily-initialized singleton accessor should have,
   and its callers immediately index the returned pointer with small
   constant offsets (e.g. `stbu r0,2024(r9)` at `0x3e6be8`, matching the
   `custom_appearance`-region offset range `0x654..0x8xx` from the 01.00
   trace).
4. **Call-site count: 501** (`grep -c 'bl      0x3e6adc'`), the same order
   of magnitude as 01.00's 436 (expected to differ somewhat — a different
   compiler pass, possibly different inlining — not expected to match
   exactly).

Confirmation, not just plausibility: running the same "does this immediate
access trace back through the accessor" tracker specifically for offsets in
`[0x1e6c, 0x1e90]` (chosen to bracket `promotion_flags_1e74` from both
sides) found **41 accessor-derived memory accesses, all of them landing in
`P+0x1E6C..0x1E73`** — the 8 bytes immediately BEFORE `promotion_flags_1e74`
starts, inside the "genuinely unmapped middle" gap the 01.00 note explicitly
called out of scope (`P+0x1E58..0x1E73`, between `pop_highwater_c` and this
field). Concretely: five distinct functions (`0x30f914`, `0x349c28`,
`0x363xxx`, `0x368590`, `0x3b51e8`, `0x3c1778`) read/write that 8-byte span
via the confirmed accessor, in the same "4 individual `lbz`/`stb` bytes
composing one BE u32" idiom seen elsewhere in this record. This is new,
previously-undocumented territory in that gap (not folded into
`profile_21.ksy` here — it's outside this task's scope, no field boundary
or semantics were established, just noted for a future pass) — but it is
**not** `promotion_flags_1e74` itself: nothing in the 41 hits reaches
`0x1E74` or beyond.

**Result: zero accessor-derived reads or writes anywhere in `P+0x1E74..0x1E8B`
in the 01.11 EBOOT**, matching the 01.00 result exactly. This directly rules
out the simplest form of the "01.00-only blind spot" theory: the record's
shared field accessor — the mechanism responsible for essentially every
other resolved field in this file — behaves identically in both builds with
respect to this range.

## 2. The dynamic loop-based mechanism (01.00 §2.5 equivalent), re-checked in 01.11

01.00's note flagged one unresolved dynamic-offset mechanism,
`FUN_0037a28c`, which sums a DC name-catalog's per-row values and adds the
sum (`<<2`) as a byte offset to a **fixed base of `0x1BEC` (7148)** into the
profile record, reaching somewhere at or after `P+0x1BF4` — bounded, in
01.00, well short of `0x1E74` given every known DC catalog's small row
count.

The same base offset, `addi r9,r9,7148`, appears in 01.11 too (4 sites:
`0x39291c`, `0x392af0`, `0x392cf4`, `0x3973c0`), reached via the same idiom:
`bl 0x3e6adc` (the confirmed accessor) → `slwi r9,<loop counter>,2` → `addi
r9,r9,7148` → `add r3,r3,r9` → byte reads at `+8..+11` of the resolved
address. This is the same mechanism, unchanged, in 01.11. It was not
independently re-bounded here (that would mean re-deriving the DC
catalog(s) that feed this loop in the 01.11 `net10.bin`, not attempted this
pass) — flagged as carried-forward, not newly re-verified, but nothing
suggests it changed shape between builds.

## 3. DLC/entitlement string and table search

A scan of every printable string in the 01.11 executable segment containing
`dlc`/`entitle`/`downloadable` (case-insensitive) turned up two genuine,
compact tables, both in the RW data segment as tightly-packed pointer
arrays bracketed by zero words (i.e., clean, deliberate tables, not
coincidental string proximity):

- **An 8-entry table at `0x1253fc4`**: `-DLCITEMS01`, `-DLCITEMS02`,
  `-DLCITEMSNEW01` through `-DLCITEMSNEW06` — PSN product-suffix-shaped
  strings (used with a `%s` prefix elsewhere, e.g. `%s-THELASTOFUSDLC0%d`),
  most plausibly a store/unlockable-item-pack entitlement list. **8
  entries, not 6.**
- **A 4-entry family**: `%s-THELASTOFUSDLC01` through `04` (plus a generic
  `%s-THELASTOFUSDLC0%d` format string and `%s-DLC3BRUTALMODE00`), matching
  the four served-content DLC map-pack files this project already serves
  (`dlc-map1.psarc`, `dlc-map3.psarc`, `dlc-map4.psarc`, plus `SPDLC1.psarc`
  — no `dlc-map2` exists in `server/data/served_content/`, consistent with
  a 4-slot table with one gap). **4 entries, not 6.**

No consumer of the 8-entry table was located within this pass's time budget
(a `scan_imm.py`/`scan_anchor.py` lookup on the table's own address found no
direct reference, meaning it's reached through an addressing idiom other
than the two this project's tooling currently covers, or through a
per-element rather than per-table-base reference — not chased further).

**Neither table's count matches the six words this field holds.** This is
evidence against, not for, "six" being a DLC-pack-count coincidence — but it
is not exhaustive: a table of exactly 6 DLC-flavored items may still exist
somewhere unfound, and the entitlement/capability register this project
already knows about (`0x01459260` in 01.00, per
`research/notes/2026-08-20-followup-open-items.md` §1's `FUN_003a1f5c()`
discussion) was **not** relocated or traced against 01.11 in this pass —
genuinely left open, not ruled out. Re-deriving it would need the same
signature-relocation technique used in §1 above (it wasn't a quick lookup;
`0x01459260`'s own literal-pool chain would need re-tracing from 01.11's
TOC, `0x01338de0`, the same way `0x3e6adc` was re-derived).

## 4. `net10.bin` (01.11's DC bundle) directory diff against `net1.bin` (01.00)

Extracted both served bundles with `server/lib/psarc_crypt.py extract`
(`net1.bin.psarc.crypt` → 283870 bytes, `net10.bin.psarc.crypt` → 409093
bytes; both HMAC-verified OK) and read their DC00 directories directly
(`{key_hash, type_hash, value_ptr}` records per `research/tools/dc_dir.py`'s
already-established format, no name-cracking wordlist was available for
01.11 in this pass so entries are hash-only):

- `net1.bin` (01.00): 392 directory entries.
- `net10.bin` (01.11): 437 directory entries — **46 new `key_hash` values**
  not present in `net1.bin` at all (net10.bin is not a strict superset by
  hash — all 392 of net1.bin's keys are also present in net10.bin, plus
  these 46 new ones).

Dumped each of the 46 new entries' raw struct members
(`Bundle.members()`, `{count, array_ptr, tag}` triples). Most decode as
implausible past-struct-end noise (the tool has no boundary information
without name-cracking to pin exact struct sizes). One entry, key
`0x6ca29d9b` (type `0xc7cb275c`), shows `count=6` — but its accompanying
`array` field, `0x2a8027cf`, is **not a valid file offset** (it exceeds
`net10.bin`'s own length, `0x63e05`) — `0x2a8027cf` is actually the
recurring `tag` constant seen elsewhere in this bundle family (the
`*net-taunts*`/`*net-stats*` tag from the 01.00 net.bin work), meaning this
"6" is very likely a misaligned read into the tag word of an adjacent
member, not a genuine 6-row table. No other candidate among the 46 new
entries shows a clean, plausible 6-row shape.

This check is **inconclusive, not negative**: without hash-cracking (which
needs the 01.11 disc's `paks.txt`/`pak23.txt`/`.dci` symbol corpus — not
attempted this pass, no local disc dump path was on hand) none of the 46
new keys can be named, so "no obviously DLC-shaped 6-row table" is as far
as this angle could be pushed here.

## Verdict

**The specific hypothesis under test — that `promotion_flags_1e74` has a
writer that exists only in 01.11 and was invisible to the earlier 01.00-only
trace — is NOT supported by this pass.** The 01.11 EBOOT's profile-record
accessor was independently re-derived (not assumed to share 01.00's address)
and confirmed via call-site convergence (501 sites, matching shape, reaches
the immediately-adjacent `P+0x1E6C..0x1E73` gap byte-for-byte) — and it
shows the exact same "nothing reaches `0x1E74..0x1E8B`" result 01.00 showed.
If this field had an ordinary accessor-mediated EBOOT writer unique to
01.11, this trace would have found it, the same way it found the
previously-undocumented `0x1E6C..0x1E73` accesses one field over.

The broader "is it DLC-related at all" question is **inconclusive, leaning
negative**: the two genuine DLC/entitlement tables found in 01.11's strings
have 8 and 4 entries respectively, not 6, and the DC bundle diff turned up
no clean 6-row candidate among 01.11's 46 new globals. But two real gaps
remain unclosed: the entitlement/capability register
(`0x01459260`-in-01.00) was not relocated or traced against 01.11's code,
and `net10.bin`'s 46 new keys were not name-cracked. Either could still turn
up a DLC connection; this pass just didn't find one.

**Practical implication for `docs/OPEN-QUESTIONS.md`/`profile_21.ksy`:** the
live RPCS3 memory-write-breakpoint test recommended in the prior note's §5
is still the fastest real path to closing this — this pass narrows "which
build to test in" not at all (both builds show the same negative static
result, so either would do), but it does add one new fact worth testing
against: if a live breakpoint ever fires on this range, check whether the
call stack includes `0x3e6adc` (01.11) — if it doesn't, the write is
happening through some entirely different mechanism than every other known
field in this record, which would itself be a notable finding.
