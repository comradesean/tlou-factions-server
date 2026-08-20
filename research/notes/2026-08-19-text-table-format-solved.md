# text1.psarc's StringId text table format solved; resolves the 0x40b5d875 milestone string

Follow-up to `research/notes/2026-08-19-dc00-hash-strings-from-disc.md`,
which used the retail disc's `bin.psarc` to crack DC00 table hashes. This
note covers a different, previously-untouched archive on the same disc:
`PS3_GAME/USRDIR/build/main/text1.psarc` - per-locale UI/gameplay text.

## What's in text1.psarc

Entries are named `<locale_num>.<category>` - locale numbers `2`, `7`,
`10`-`23` observed; category one of `common`, `networking`, `subtitles`,
`subtitles-temp`. Locale `2` and `7` are both English, confirmed two ways:
both produce `"El Diablo Ammo"`, and both contain an exact set of live-game
UI strings a human on this project read directly off their screen while
this investigation was underway: `"Norwegian Hat"`, `"Ballistic Mask"`,
`"Military Helmet"`, `"Blow Smoke"`, `"Marathon Runner"`, `"Pistol
Auto-zoom"`.

Running `strings`-equivalent extraction (a regex for NUL-bounded printable
runs) over the raw bytes of `2.networking` found real text starting only at
byte `0x4044` - everything before that is clearly binary, not text.

## The format

```
[u32 count]
[count x record(u32 key, u32 string_offset)]   <- sorted ascending by key
[string blob: count NUL-terminated strings, back to back]
```

`blob_start = 4 + count*8`; `string_offset` is relative to `blob_start`.
Full writeup with the field-by-field construction, verification method, and
worked example lives in `docs/protocol/text_table.md`
(`protos/common/text_table.ksy` is the paired Kaitai schema). Short version
of how it was nailed down for `2.networking` (70,405 bytes):

- Counting real NUL-delimited strings from `0x4044` to EOF gives exactly
  2056 (2057 pieces when split on `\x00`, the last one an empty trailing
  piece).
- The file's first 4 bytes, as big-endian u32, are `0x00000808` = 2056 -
  an exact match. That's `count`.
- `4 + 2056*8 = 0x4044` - exactly the byte where the string blob starts,
  confirming an 8-byte record stride with no extra header padding.
- Reading all 2056 `(key, string_offset)` records: `key` is strictly
  ascending and unique across the whole table (zero exceptions), and every
  `string_offset`, added to `blob_start`, lands exactly on a string start
  (preceded by a `\x00` byte, or `==0` for the very first entry) - zero
  exceptions across all 2056 records. This is not a coincidental read: it's
  a real sorted lookup table, shaped for binary search.
- The blob's first string (`string_offset == 0`) is the literal sentinel
  `"UNKNOWN STRING!!!"` - a fallback for a failed lookup, not real content.

Verified end-to-end (string -> key -> string round trip, byte-exact) against
7 display strings: `Norwegian Hat` (key `0x02415548`), `Ballistic Mask`
(`0xe47d6ec3`), `Military Helmet` (`0xf341faee`), `Blow Smoke`
(`0x328e4395`), `Marathon Runner` (`0xd009cc40`), `Pistol Auto-zoom`
(`0x9a25239f`), `Steering Helm` (`0xffd09bbe`).

Cross-locale check: `2.networking` and `7.networking` (both English) have
**byte-identical key sets** (2056 keys, full overlap, zero unique to
either side) - `key` is a locale-independent StringId as expected, only the
string blob content differs per locale.

## The hash algorithm behind `key` is NOT identified

The obvious hypothesis going in - reuse `crc32_mpeg2` (this project's
confirmed hash for DC00 table keys and `userdata.txt` config keys) over
some source symbol name, the same way DC00 hashes were cracked earlier this
session - was tried and did not pan out:

- `crc32_mpeg2("Added Extra Supplies from Promotion!")` (the display string
  itself, for the milestone key below) = `0x05dbfa05`, not `0x40b5d875`.
- Ran `research/tools/dc_hash_crack.py`'s corpus (43,674-plus tokens from
  `bin.psarc`'s `.dci` files plus `paks.txt`/`pak23.txt`) against 8 target
  keys pulled from this table (the 7 verification strings' keys above, plus
  `0x40b5d875`) - zero hits.

This is a real, honest negative result, not a shortcut: the corpus that
cracked DC00 hashes cleanly on the first pass earlier the same day found
nothing here. Either this StringId system hashes a symbol name not present
in the `bin.psarc` corpus (plausible - text/localization tooling may have
its own separate symbol dictionary this project hasn't located), or it uses
a different hash function/seed entirely. Not knowing the algorithm does not
block using the table, though: `key` is usable as an opaque 32-bit id, and
every StringId this project has cited so far was already cited as a bare
hex constant, not as "the hash of symbol X" pending reversal.

## Resolves an already-open StringId

`protos/profile_21.ksy`'s `milestone_latch_1e2c` field previously read (in
part): "...awarding event 0x40b5d875 ... Which milestone is DC-assigned."
That key is present in `2.networking` and resolves to:

> **"Added Extra Supplies from Promotion!"**

`profile_21.ksy` has been updated to cite this directly. This is the
milestone the one-shot latch bit (`FUN_0035f1bc`, `stw r0,7724(r3)` @
`0x35f274`) gates: the first time its predicate holds during a match
(game-state==3), the player is credited with a supplies bonus tied to
promotion, and the bit persists so it only fires once per profile.

## Does NOT resolve the other cited open StringId

`match_ratio_1e3c`'s doc cites a second StringId, `0x5c494554`
("reported under DC StringId 0x5c494554"). Checked this key against:

- All four English `text1.psarc` category files (`2.common`,
  `2.networking`, `2.subtitles`, `2.subtitles-temp`) - not present in any.
- Every other `.psarc` on the disc (`bin.psarc`, `pak23.psarc`,
  `actor34.psarc`) scanned generically for any embedded table matching this
  same container shape (count field + sorted records) that happens to
  contain the key - zero hits.

Left genuinely open: `0x5c494554` may be an internal
telemetry/stat-reporting id with no localized display string at all (a
plausible read - `match_ratio_1e3c` is a computed ratio stat, not
obviously player-facing UI copy), or it may live in a resource not checked
here (`gallery1.psarc`, `animstream4.psarc`, `animtex0.psarc`,
`vtex1.psarc`, `lut0.psarc` were skipped on low a priori likelihood given
their names/purposes, not because they were checked and came up empty), or
in 01.11-only content not present on the mounted 01.00 disc. `profile_21.ksy`
now documents this negative result inline rather than leaving it silently
unaddressed.

## Reusable method, going forward

**Tool: `research/tools/text_table.py`.** Parses any `text1.psarc`
category entry and resolves `key -> string` (forward) or `string -> key`
(reverse, byte-exact match). Reproduces every lookup in this note:

```sh
BASE="/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main"
python3 research/tools/text_table.py -p "$BASE/text1.psarc" -e 2.networking \
    0x40b5d875 0x5c494554
python3 research/tools/text_table.py -p "$BASE/text1.psarc" -e 2.networking \
    --find-string "Norwegian Hat"
python3 research/tools/text_table.py -p "$BASE/text1.psarc" --list-entries
```

Any future StringId this project cites (from a decompile, a wire capture,
or an existing doc's "DC StringId 0xXXXXXXXX" note) should be run through
this before being declared unrecoverable - it's cheap and mechanical, the
same way `dc_hash_crack.py` already is for DC00 table hashes. Note the two
tools solve different problems: `dc_hash_crack.py` recovers a DC00 table's
directory-key *source symbol name*, whereas `text_table.py` resolves a
StringId directly to its *display text* without needing to know a source
symbol at all (the table itself carries key->string, no reversal needed).

## Files changed by this note's work

- `protos/common/text_table.ksy` (new) - the container schema.
- `docs/protocol/text_table.md` (new) - full construction/verification
  writeup, the format spec, and the two-StringId resolution results.
- `research/tools/text_table.py` (new) - the checked-in lookup tool
  (forward + reverse lookup, entry listing, full-table dump).
- `protos/profile_21.ksy` - `milestone_latch_1e2c` doc updated with the
  resolved string; `match_ratio_1e3c` doc updated to record the negative
  result for `0x5c494554` instead of leaving it silently unaddressed.
