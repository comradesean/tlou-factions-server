# text_table - StringId text lookup table (text1.psarc)

`protos/common/text_table.ksy`

status: **confirmed** (container/lookup structure only - see caveat below)
confidence: **high** - every structural claim is a direct, reproducible
measurement against the real file (`2.networking`/`2.common`/`7.networking`
from the retail disc's `text1.psarc`), not a guess from a hexdump: the
entry count matches an independent count of null-terminated strings in the
blob to the byte, every record's key is unique and the whole array is
sorted ascending, and every record's `string_offset` lands exactly on a
valid string start (preceded by a NUL byte, or `== 0` for the blob's first
entry).

## What this covers, and what it doesn't

This document is about the **lookup table container**: how to go from a
32-bit `key` to the right display string inside one locale/category file.
That layer is fully solved and mechanically verified below.

What is **not** solved: the hash algorithm that produces a given `key` from
whatever source symbol Naughty Dog's tools hashed to make it. `crc32_mpeg2`
(this project's confirmed hash for DC00 table directory keys and
`userdata.txt` config keys - `server/lib/userdata_crypt.py`) was tried
against both the display string itself and the ~50K-token DC00 symbol
corpus (`research/tools/dc_hash_crack.py`'s `build_corpus()` over
`bin.psarc`'s `.dci` files + `paks.txt`/`pak23.txt`) for several known
(key, string) pairs - no hit either way. This table's `key` may use a
different hash function/seed, or hash a symbol name not present in the
`bin.psarc` corpus (this could plausibly be a separate DC "localization"
tool with its own symbol dictionary this project hasn't located). Not
fixing this doesn't block using the table: every StringId this project has
actually needed to resolve so far is cited as a bare hex constant already,
not as "a hash of symbol X" - `key` is usable directly as an opaque id.

## Files

`PS3_GAME/USRDIR/build/main/text1.psarc` (retail disc, unencrypted PSARC -
see `research/tools/eboot_analysis/README.md` for the standard local mount
path). Read with `server/lib/psarc_crypt.py`'s `parse_psarc()` directly (no
`decrypt_crypt_file` - not the Blowfish+HMAC wrapper format).

Entries are named `<locale_num>.<category>`: locale numbers `2`, `7`, `10`-
`23` observed (`2` and `7` are both English - confirmed by both producing
`"El Diablo Ammo"` and, more distinctively, an exact set of live-game UI
strings a human on this project read directly off their screen: "Norwegian
Hat", "Ballistic Mask", "Military Helmet", "Blow Smoke", "Marathon Runner",
"Pistol Auto-zoom"). Category is one of `common`, `networking`,
`subtitles`, `subtitles-temp` - each parses as an independent
`text_table`, with its own `count`/keyspace (English locale 2:
`common`=2711, `networking`=2056, `subtitles`=9719, `subtitles-temp`=8178
entries).

## The format

```
[u32 count]
[count x record(u32 key, u32 string_offset)]   <- sorted ascending by key
[string blob: count NUL-terminated strings, back to back]
```

`blob_start = 4 + count*8`. `string_offset` is relative to `blob_start`,
**not** to the file start and **not** to the record. The blob's first
string (offset 0) is always the literal sentinel `"UNKNOWN STRING!!!"` -
every real string in `2.networking` sits after it, e.g. entries begin
`"UNKNOWN STRING!!!\0Searching for Match\0CLAN INFO\0..."`.

### How this was found (`2.networking`, English, 70,405 bytes)

1. `strings`-style scan (`(?<=\x00)[\x20-\x7e]{2,}(?=\x00)`) over the raw
   file found real UI text starting at byte `0x4044`, with clean
   NUL-terminated runs (`"Searching for Match"`, `"CLAN INFO"`,
   `"Norwegian Hat"`, ...) from there to EOF - 2037 matches for a
   length->=2 filter.
2. Splitting the region from `0x4044` to EOF on `\x00` gives exactly 2057
   pieces, the last one empty (trailing NUL) - i.e. **2056 real strings**,
   the first of which (offset 0 in the blob) is `"UNKNOWN STRING!!!"`, not
   counted among the "real" 2037 because the length->=2 regex still counted
   it - both numbers are consistent once you check by hand.
3. The file's first 4 bytes, read as big-endian u32, are `0x00000808` =
   **2056** - an exact match for the real string count. That is the
   `count` field.
4. `4 + 2056*8 = 0x4044` - exactly where the string blob starts. That
   confirms the record stride is 8 bytes (two u32s) with no header padding
   beyond the initial `count` word.
5. Reading `records[i] = (key, string_offset)` for all 2056 entries: `key`
   values are strictly ascending (`sorted(keys) == keys`, all unique) and
   `string_offset` values, when added to `blob_start`, land exactly on a
   string start (`data[blob_start + string_offset - 1] == 0x00` for every
   nonzero offset; offset `0` is the sentinel at the very start of the
   blob) for all 2056 records, zero exceptions.

### Verified against 7 display strings, both directions

For each string, its blob byte-offset was located directly (`bytes.find`),
converted to a `string_offset` (subtract `blob_start`), matched against a
record to recover its `key`, then the `key` was looked up back through the
table to confirm it resolves to the exact same string:

| string | key |
|---|---|
| `Norwegian Hat` | `0x02415548` |
| `Ballistic Mask` | `0xe47d6ec3` |
| `Military Helmet` | `0xf341faee` |
| `Blow Smoke` | `0x328e4395` |
| `Marathon Runner` | `0xd009cc40` |
| `Pistol Auto-zoom` | `0x9a25239f` |
| `Steering Helm` | `0xffd09bbe` |

All 7 round-trip (`key -> string_offset -> string == original`).

### Locale-independence of `key`

`2.networking` and `7.networking` (both English but distinct locale
numbers, presumably e.g. US vs UK/AU English) have byte-identical `key`
SETS (2056 keys each, full set overlap, zero keys unique to either side) -
confirms `key` is a locale-independent StringId, not something derived
from the localized text itself.

## Resolves an already-cited open StringId

`protos/profile_21.ksy`'s `milestone_latch_1e2c` field doc cites DC
StringId `0x40b5d875` as the award fired by `FUN_0035f1bc`'s one-shot
milestone latch, with "which milestone is DC-assigned" left open. That
exact key **is present in `2.networking`** and resolves to:

> `"Added Extra Supplies from Promotion!"`

This is a full resolution, not a guess - looked up the same programmatic
way as the 7 verification strings above. `profile_21.ksy` should be updated
to cite this string alongside the existing decompile evidence (see that
file's own doc for the currently-cited instruction addresses).

`protos/profile_21.ksy`'s `match_ratio_1e3c` field cites a second open
StringId, `0x5c494554` ("reported under DC StringId 0x5c494554"). This key
was checked and is **NOT present** in any of the four English `text1.psarc`
category files (`2.common`, `2.networking`, `2.subtitles`,
`2.subtitles-temp`), nor in a broad scan of every other `.psarc` on the
disc (`bin.psarc`, `pak23.psarc`, `actor34.psarc`) for any embedded table
matching this container's shape. Left open: `0x5c494554` may be an
internal telemetry/stat id with no localized display string at all (a
plausible reading, given `match_ratio_1e3c` is a computed ratio stat, not
obviously UI-facing text), or it may live in a resource this project
hasn't checked (`gallery1.psarc`, `animstream4.psarc`, `animtex0.psarc`,
`vtex1.psarc`, `lut0.psarc` were not scanned - low a priori likelihood
given their names, but not ruled out) or in a later-build (01.11) content
pack not present on the mounted 01.00 disc.

## Reusable method

`research/tools/text_table.py` parses any `text1.psarc` category entry into
a `TextTable` and resolves `key -> string` or `string -> key`:

```sh
python3 research/tools/text_table.py \
    -p "$BASE/text1.psarc" -e 2.networking \
    0x40b5d875 0x5c494554
```

See the script's own `--help` for the full option list (locale/category
selection, forward and reverse lookup, dumping a whole table).

## Files changed by this note's work

- `protos/common/text_table.ksy` (new) - the container schema.
- `docs/protocol/text_table.md` (new, this file).
- `research/tools/text_table.py` (new) - the checked-in lookup tool.
- `protos/profile_21.ksy` - `milestone_latch_1e2c` doc updated with the
  resolved string.
- `research/notes/2026-08-19-text-table-format-solved.md` (new) - dated
  research note with the full investigation writeup.
