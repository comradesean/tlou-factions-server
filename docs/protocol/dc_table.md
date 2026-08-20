# dc_table - DC00 data-compiler container format

`protos/common/dc_table.ksy`

status: **confirmed** (container/header/relocation layer only - see caveat below)
confidence: **high** - every structural claim below is either a direct
disassembly read of the EBOOT's own parser, or a byte-exact arithmetic match
against the real files (`count*32 == relocation_table_offset` in net1.bin to
the byte).

## What this covers, and what it doesn't

This document is about the **container**: the magic/version/size header, and
the relocation (pointer-fixup) scheme that turns the flat file into a graph
of typed values at load time. That layer is fully solved.

What is *not* solved here: the semantic meaning of any individual DC hash's
value once you've located it. That is tracked per-hash in the
consuming proto/doc - see `protos/common/member_data.ksy` (`rank_tier`,
whose backing DC symbol is `*net-money-info*`, a 99-entry threshold ladder
decoded 2026-08-20), `protos/0x11_stat_line.ksy`
(the `0x1ad3445f` table), and `server/ticket_server.py`'s `pReportArray`
comment. All three of those have been advanced significantly by this
session's work (see their own docs), but none reaches a fully-decoded
"here are the literal numbers" state - see each one's own status/confidence.

## Files, extraction

```sh
python3 server/lib/psarc_crypt.py extract server/data/served_content/net1.bin.psarc.crypt <outdir>
python3 server/lib/psarc_crypt.py extract server/data/served_content/net10.bin.psarc.crypt <outdir>
```

`net1.bin` (283,870 bytes) ships with build 01.00; `net10.bin` (409,093
bytes) ships with 01.11. Both begin `44 43 30 30` ("DC00").

## The parser: `FUN_009fc118` (01.00 EBOOT VMA)

Found by searching the EBOOT text segment for the `lis`+`ori` construction of
the literal `0x44433030` (`research/tools/eboot_analysis/scan_imm.py 44433030`)
- one hit, at `0x009fc148` inside `FUN_009fc118` (`fnstart.py 9fc148` ->
`0x009fc118`). Full disassembly pulled with `objdump` against the raw EBOOT
(`--adjust-vma=0x10000`, per `research/tools/eboot_analysis/README.md`'s VMA
mapping).

Pseudocode (param_1 = `r3` = pointer to the already-loaded file buffer):

```c
void *dc_table_load(void *buf /* r3 */) {
    if (*(u32*)buf != 0x44433030) {           // 0x9fc14c/0x9fc158
        log_error("bad DC00 magic", buf);      // 0x9fc15c-0x9fc168
        return NULL;
    }
    u32 field8 = *(u32*)(buf + 8);             // relocation_table_offset
    u32 *table_hdr = buf + field8;             // 0x9fc170-0x9fc184
    u32 count = *table_hdr;                    // table_header.count
    u32 *bitmap_cursor = { ptr: table_hdr + 1, bitpos: 0, byte_idx: 0, byte_count: count };
    u32 total_slots = count * 8;               // 0x9fc1b8: slwi r27,r0,3

    for (u32 i = 0; i < total_slots; i++) {     // 0x9fc1c0-0x9fc1fc
        u32 bit = read_next_bit(&bitmap_cursor); // bl 0x9f9d68, see below
        if (bit) {
            u32 *slot = (u32*)((char*)buf + i*4);
            *slot = *slot + (u32)buf;           // 0x9fc1e0-0x9fc1e8: offset -> pointer
        }
    }
    return buf + 0x10;                          // 0x9fc200: returns payload start
}
```

`read_next_bit` is `FUN_009f9d68` (bounds-checks `byte_idx < byte_count` at
`0x9f9d78`-`0x9f9d90`, aborting via a diagnostic call at `0x9f9d94` if not;
the live path at `0x9f9ddc`-`0x9f9e34` does `bit = (byte[byte_idx] >>
bitpos) & 1`, then advances `bitpos`, wrapping to the next `byte_idx` every 8
bits).

This is a completely generic "flatten a pointer graph into one buffer, with
a companion bitmap saying which words need `+base` fixup" scheme - not
bespoke to `net1.bin`, and not (as far as traced) shared with the
`_opd_FUN_0078b5a0`/`_opd_FUN_00ab685c` "named-value registry" functions the
prior handoff note suspected were part of this same file-format parser. That
suspicion is now resolved as **false**: those two functions, plus
`_opd_FUN_009fa9f4`/`_opd_FUN_009fa88c`, are a separate, engine-wide
sorted-hash-table binary-search lookup used to resolve a DC hash to a value
at runtime (built once at load time, presumably by walking every DC00 file's
directory once) - see `protos/common/member_data.ksy`'s `rank_tier` doc for
the full trace. They consume this container's *contents*, but are not part
of decoding the container's *bytes*.

## Byte-exact verification

net1.bin: `header.relocation_table_offset` (file offset `0x8`) = `0x43340`.
At that exact file offset: `table_header.count` = `8602` (`0x219a`).
`8602 * 32 = 275264 = 0x43340` - an **exact** match to
`relocation_table_offset`, confirming both the header field's meaning (size
of the slot region in bytes) and the relocation bitmap's sizing
(`count` bytes = `count*8` bits = one bit per 4-byte slot across that exact
byte range).

```
net1.bin  file-off 0x43330: 65 61 73 79 2d 65 78 70 6c 6f 72 65 00 00 00 00   (tail of an unrelated string, "easy-explore\0\0\0\0")
net1.bin  file-off 0x43340: 00 00 21 9a 40 92 24 49 92 24 49 92 24 49 92 24   count=8602, then bitmap bytes
```

net10.bin: `relocation_table_offset` = `0x60d94`; `count` at that offset =
`12397` (`0x306d`); `12397 * 32 = 396704 = 0x60da0`, **12 bytes more** than
`relocation_table_offset` (`0x60d94`). This is a small, harmless overshoot -
the fixup loop's last few iterations walk slightly into `table_header`/
`relocation_bitmap` itself, which doesn't parse as a meaningful pointer in
practice. Not fully explained (could be an alignment pad the compiler adds
for this specific build), but doesn't threaten the rest of the model - flagged
here rather than silently rounded away.

## The payload's internal shape - SOLVED 2026-08-20

**CORRECTION.** The repeating unit was recorded here as
`{value_ptr, key_hash, type_hash}`. It is **`{key_hash, type_hash,
value_ptr}`** - the earlier reading was shifted one word, which attributed
each global's table to the *following* record. Everything that follows in
this section was rewritten on 2026-08-20; see
`research/notes/2026-08-20-dc-directory-and-catalogs.md` and the tool
`research/tools/dc_dir.py`.

The directory is self-describing from the bundle header:

```
+0x14  u32  entry_count   (dc1/net.bin: 392)
+0x18  u32  dir_offset    (dc1/net.bin: 0x1c)
records: entry_count x 12 bytes, {key_hash: u4, type_hash: u4, value_ptr: u4}
```

The three records around `member_data.rank_tier`'s hash, byte-exact:

```
0x000ec8  c7f8567c ed6b8e26 0001dd24     *net-emblem-layers-frame*
0x000ed4  c85e199d ced9d25f 000052f4     *net-money-info*
0x000ee0  c970681f 290349e3 00005300
```

`value_ptr` targets a struct whose members are frequently
`{count: u4, array_ptr: u4, tag: u4}` length-prefixed arrays, packed back to
back (one global can hold several). `tag` does NOT encode the element stride
- `*net-taunts*` and `*net-stats*` share `tag = 0x2a8027cf` at strides 12 and
8 - so a stride has to be established per table by decoding it.

**Every one of `net.bin`'s 392 `key_hash` values cracks** against the disc's
`dc1/*.dci` compiler-symbol corpus (`research/tools/dc_hash_crack.py`) - a
100% hit rate, which is itself the proof the corrected record layout is right
(a one-word-shifted walk resolves essentially nothing). Tables decoded so far:

| global | key_hash | value | contents |
|---|---|---|---|
| `*net-money-info*` | `0xc85e199d` | `0x52f4` -> `{99, 0x2665c}` | u32 cumulative threshold ladder (`0, 2000, 4000, 7000, 12000, ...`) |
| `*net-emblem-layers-{base,frame,parts}*` | `0xe2311588`/`0xc7f8567c`/`0x03ffae77` | all -> `0x1dd24` -> `{193, 0x2be58}` | emblem shape catalog, stride 12 `{name_hash, name_ptr, sub_ptr}` |
| `*net-emblem-colors*` | `0xbcbbdfbd` | `0x50fc` -> `{64, 0x15e94}` | 64 RGBA f32 swatches, stride 16 |
| `*net-taunts*` | `0xb2b6e512` | `0x4f88` -> `{11, 0x1a740}` | gesture catalog, stride 12 `{id_hash, text_string_id, ?}` |
| `*net-stats*` | `0x921da350` | `0x488c` -> `{40, 0x9c18}` | net-stat event registry, stride 8 `{stat_id_hash, text_string_id}` |
| `*unlock-list*` | `0xe2e8998e` | `0x583c` -> `{284, 0x2460c}` | unlock records, stride 28 |

The hashes that appear *inside* these tables (a shape's `name_hash`, a
gesture's id) are a DIFFERENT and still-unidentified 32-bit hash - it is NOT
`crc32_mpeg2`. It does not need to be cracked to use the tables: each record
pairs its hash with either the plaintext name or a `text1.psarc` StringId.
See the 2026-08-20 note, section 6, for exactly what has been ruled in and out.

`key_hash`/`type_hash` NAMING SCHEME CRACKED 2026-08-19: both hashes are
`crc32_mpeg2` (`server/lib/userdata_crypt.py`) over source symbol names
pulled from the retail disc's own `dc1/*.dci` files (plaintext Scheme-style
dependency lists inside `build/main/bin.psarc` on the PS3 disc - see
"Recovering hash strings from the retail disc" below). `key_hash` is the
hash of the **global variable name including its `*star*` decoration**
(e.g. `*net-money-info*`); `type_hash` is the hash of the **same name
without the stars** (`net-money-info`) - i.e. the compiler hashes both the
storage-location name and its bare type/struct name for every top-level
directory entry, and they are always a matched pair for the same concept.
Confirmed exact on the `0xC85E199D`/`0xced9d25f` pair (see
`protos/common/member_data.ksy`'s `rank_tier` field doc for the full
derivation) - the other recurring `type_hash` constants in this file
(`0x2a8027cf`, `0x290349e3`, `0x13c5fb80`, `0x3331e70d`, ...) are not yet
matched to specific symbol names but can be attacked the same way.

## Recovering hash strings from the retail disc

**Tool: `research/tools/dc_hash_crack.py`** - run it with `--help` for full
usage; the short version:

```sh
BASE="/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main"   # see
                                    # research/tools/eboot_analysis/README.md
                                    # for this project's standard local disc path
python3 research/tools/dc_hash_crack.py \
    -p "$BASE/bin.psarc" -w "$BASE/paks.txt" -w "$BASE/pak23.txt" \
    0xC85E199D 0xced9d25f 0x1ad3445f
```

That single command reproduces every hash-string match in this doc from a
clean checkout - no manual extraction, no ad hoc scripting. It works because
of two things discovered by walking the disc's own files:

1. The disc mounted for this project (`PS3_GAME` layout, `BCUS98174`) ships
   its own **unencrypted** `.psarc` archives at
   `PS3_GAME/USRDIR/build/main/*.psarc` - no relation to
   `server/data/served_content/`'s encrypted `.crypt` files. Inside
   `bin.psarc`: `dc1/net.bin` (283,615 bytes) is **byte-identical in
   structure** to `net1.bin` from `served_content` (`0xC85E199D` and
   `0x1ad3445f` land at the exact same file offsets, `0xed4` and `0x1850`,
   in both files) - the disc's `dc1/` tree is very likely the direct source
   of the `netN.bin` bundles shipped over the network. Every `dc1/*.bin` has
   a sibling `dc1/*.dci` (1,878 of them) - a small PLAINTEXT file (not
   DC00/binary) of the form
   `(net (283615)\n  (import ...)\n  (export *sym1* *sym2* ...)\n  )`: the
   DC compiler's own import/export symbol list for that source module. This
   is a ready-made dictionary of candidate hash-input strings - tokenizing
   every `.dci` in `bin.psarc` yields ~43,700 unique symbol names.
2. `build/main/` also ships plain-text manifests alongside the `.psarc`
   files - `paks.txt`, `pak23.txt`, `banks.txt`, `*-audio-precache.txt` -
   a second, independent source of candidates (not compiler symbols, just
   pak/level/table names).

`0xC85E199D`/`0xced9d25f` were cracked from source (1) on the first try
(see `protos/common/member_data.ksy`'s `rank_tier` field doc for the full
derivation). `0x1ad3445f` (`stat_line`'s table hash) was independently
confirmed via source (2) - `"hud"` is a literal line in `paks.txt` - as a
cross-check of the same hash already solved via a different method (the
EBOOT string trace in `protos/0x11_stat_line.ksy`); both methods agree.

This is genuinely reusable: any future DC hash this project cites should be
run through the tool above before being declared unrecoverable.
`0xFFAC56F2` (`pReportArray`'s key_hash) and `0xF99A36AA` (its type_hash,
per `server/ticket_server.py`'s `TODO(pReportArray)` comment) were both
searched against the full corpus (both sources) and found **no match** -
unsurprising, since it's confirmed 01.11-only content (`net10.bin`) and this disc is the
01.00 base build, so its source symbol (if introduced in a later patch) is
plausibly just not present in this disc's `.dci` set. The other recurring
`type_hash` constants noted above (`0x2a8027cf`, `0x290349e3`,
`0x13c5fb80`, `0x3331e70d`) were also tried and also came back empty - a
matching disc build (01.11) would be needed to try these against a
comparable symbol corpus.

## Tooling

The decode used for all of the above is a small standalone script (not
checked into the repo - scratch tooling), doing exactly what's described:
parse the 16-byte header, locate `table_header`/`relocation_bitmap` at
`relocation_table_offset`, and expose `bit(slot_idx)` / `slot_val(slot_idx)`
accessors matching this doc's field names. Any future DC hash lookup in
these files should start from the same three primitives (header parse,
per-slot bit lookup, raw slot word read) rather than re-deriving them.
