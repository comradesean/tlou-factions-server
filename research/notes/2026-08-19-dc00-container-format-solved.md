# DC00 container format: solved (parser found and decompiled); payload semantics partially advanced

Follow-up to `research/notes/2026-08-19-dc00-record-format-handoff.md`, which
left the exact record layout of `net1.bin`/`net10.bin` unsolved and
recommended finding the EBOOT's own parser rather than continuing to guess
from a hexdump. That parser was found this session. The container format
(header + relocation/fixup scheme) is now fully solved and documented at
`docs/protocol/dc_table.md` / `protos/common/dc_table.ksy`. The three known
DC hashes were traced further into the payload than before, with concrete
(if still partial) results folded into their own docs. Full findings live in
those files; this note is a pointer plus the parts that don't belong in any
single proto doc.

## What's solved

- The parser is `FUN_009fc118` (01.00 EBOOT VMA), found by searching the
  text segment for the `lis`+`ori` construction of `0x44433030` ("DC00")
  via `research/tools/eboot_analysis/scan_imm.py`. Fully decompiled.
- Header: `magic(u4) version(u4) relocation_table_offset(u4) pad(u4)`.
- Everything from byte 0 through `relocation_table_offset` is a flat array
  of 4-byte slots. A trailing region starting at `relocation_table_offset`
  holds `count(u4)` followed by `count` bytes of a bitmap - one bit per
  slot, LSB-first, in slot order - marking which slots are file-relative
  fixup offsets (bit=1) vs literal values (bit=0, ints/floats/hashes/tags).
- Verified byte-exact against net1.bin: `count * 32 ==
  relocation_table_offset` (`8602 * 32 = 275264 = 0x43340`, both read
  directly from the file). net10.bin matches to within 12 bytes (see
  `dc_table.md` for the discrepancy, left unexplained but harmless).

## What's genuinely still open (said honestly, not smoothed over)

- **The payload's internal typed-value shape.** The directory pattern found
  around all three hashes (`{value_ptr, key_hash, type_hash}` triples,
  `value_ptr` often targeting a `{count, array_ptr}` pair) is consistent
  across every hit inspected, but what the recurring `type_hash` constants
  mean (`0x2a8027cf`, `0x290349e3`, `0xced9d25f`, `0x13c5fb80`,
  `0x3331e70d`, ...) is not decoded - no on-disk string table maps them to
  names, and the two engine functions this project hoped would resolve
  that (`_opd_FUN_0078b5a0`, `_opd_FUN_00ab685c`) turned out NOT to be this
  file's parser at all (see below) - they're a separate, engine-wide
  runtime hash/string registry that *consumes* DC00 files' contents rather
  than reading their raw bytes, so tracing them doesn't directly explain
  the byte layout.

  CORRECTED 2026-08-20: the record field order above is WRONG - it is
  `{key_hash, type_hash, value_ptr}`, not `{value_ptr, key_hash, type_hash}`.
  See `docs/protocol/dc_table.md`'s "SOLVED 2026-08-20" section and
  `research/notes/2026-08-20-dc-directory-and-catalogs.md` for the
  corrected layout and everything it unblocked - including `rank_tier`
  immediately below, which this off-by-one had been misreading.
- **`rank_tier` (`0xC85E199D`)**: directory entry pinpointed
  (net1.bin `0xed4` -> value blob `0x27da8` -> `{count=193, array@0x2950c}`),
  consumer function (`FUN_003c8e30`) fully decompiled, but the 193-entry
  array at `0x2950c` doesn't read as clean flat thresholds under the
  consumer's literal 4-byte-stride access pattern - it looks like more
  directory-shaped data. Left unresolved; see
  `protos/common/member_data.ksy`'s `rank_tier` field doc for the full
  writeup, including a correction to the scan-loop semantics (it is NOT
  "first satisfied bracket", contrary to the previous day's read).
  RESOLVED 2026-08-20 - see that same field doc: the 193-entry array
  belonged to the *next* record over, and `rank_tier`'s real DC branch is
  dead code.
- **`stat_line` task table (`0x1ad3445f`)**: this is the biggest correction
  of the session. The hash's table is NOT a task/objective-definitions
  table - it's a string-keyed HUD material/icon-path lookup table (real
  keys recovered: `"general/hud/prize-icon/Default"`,
  `"general/hud/alpha-icon24/default"`, `"general/hud/spinner/default"`,
  etc, 14 confirmed in total). `FUN_0032241c` (the function believed to
  write `task-%x`'s value) builds a UI reward-popup descriptor, and
  `_opd_FUN_00ab685c` does STRING comparison (strlen/memcmp-shaped calls),
  not hash comparison as previously assumed. See
  `protos/0x11_stat_line.ksy`'s `%x` field doc for the full trace,
  including which prior "sibling fields" claim was wrong (those siblings
  belong to a *different* base hash, `0xD006E7B5`, not `0x1ad3445f`).
- **`pReportArray` (`0xFFAC56F2`)**: directory entry pinpointed in
  net10.bin (`0x148c` -> value blob `0x25314` -> `{count=1,
  array@0x3bc68, tag=0x13c5fb80}`) - the table currently defines exactly
  one entry. The entry's actual name/id (needed to construct a real ban,
  not needed for this project's current fail-open behavior) is inside
  `0x3bc68`'s further nested, undecoded structure. See
  `server/ticket_server.py`'s `TODO(pReportArray)` comment.

## The runtime hash-registry tangent (useful to record, not useful to chase further right now)

The prior handoff's strongest lead - `_opd_FUN_0078b5a0` (hash-to-table
resolver) and `_opd_FUN_00ab685c` (per-key lookup) - was followed to ground
this session. Both are real, decompiled functions, but they are **not**
part of `dc_table.ksy`'s file-format parser. They implement a separate,
engine-wide sorted-array binary search (`_opd_FUN_009fa9f4` ->
`_opd_FUN_009fa88c`, 8-byte `{key_hash, value}` stride, classic
`sradi`-based binary search) over a table the engine builds once at
startup - presumably by walking every DC00 file's directory and inserting
entries, though that construction step itself was not traced. `ab685c`
resolves to a DIFFERENT string-keyed lookup (linear/binary scan comparing
C-strings via `strlen`+`memcmp`), used by `FUN_0032241c` for its
per-material-path field lookups. Neither one reads `net1.bin`/`net10.bin`
bytes directly at the call sites traced - they consume already-resolved
runtime state. This means static analysis of these two functions alone
cannot confirm that a given file offset found by scanning the raw
`net1.bin` bytes is the SAME pointer the runtime registry hands back
(same numeric coincidence risk noted for `rank_tier` above) - a live
RPCS3 memory read while a relevant UI element is on-screen is the only way
to close that gap with certainty.

## Tooling used (not checked into the repo)

A ~60-line Python decoder (header parse + `bit(slot_idx)` / `slot_val(slot_idx)`
accessors matching `dc_table.ksy`'s field names) was written in scratch
space to do all of the above. It is not part of this repo - any future
session picking up a new DC hash should re-derive the same three
primitives from `docs/protocol/dc_table.md` rather than assume a decoder
script exists somewhere.
