meta:
  id: text_table
  title: StringId text table (text1.psarc locale bundles)
  endian: be
  license: CC0-1.0
  doc-ref: docs/protocol/text_table.md
doc: |
  Per-locale UI/gameplay text lookup table, as shipped inside
  `PS3_GAME/USRDIR/build/main/text1.psarc` on the retail disc (a PLAIN,
  unencrypted PSARC - see `server/lib/psarc_crypt.py`'s `parse_psarc()` -
  distinct from `server/data/served_content/`'s Blowfish+HMAC `.crypt`
  files). Each entry inside `text1.psarc` (named `<locale_num>.common`,
  `<locale_num>.networking`, `<locale_num>.subtitles`,
  `<locale_num>.subtitles-temp`) parses independently as one of these
  tables. Locale 2 and 7 are both English.

  This is a sorted (StringId -> string-blob-offset) lookup table, structured
  for binary search: `keys` is monotonically ascending and every value is
  unique (byte-verified across `2.networking`, 2056 entries, and cross-
  checked against `7.networking`, whose key SET is byte-identical - i.e.
  StringIds are locale-independent, only the string blob differs).

  STATUS: container/lookup structure CONFIRMED by direct construction
  (count field, record stride, sorted keys, and every record's blob offset
  landing exactly on a valid null-terminated string were all verified
  programmatically - see docs/protocol/text_table.md). The hash algorithm
  that PRODUCES a given `key` from a source symbol name is NOT identified
  (tried `crc32_mpeg2`, this project's confirmed DC00/userdata.txt hash,
  against both the display string itself and the ~50K-token `bin.psarc`
  .dci/manifest symbol corpus `research/tools/dc_hash_crack.py` uses for
  DC00 hashes - no hit). Practically this does not block lookup: a `key` is
  usable directly as an opaque 32-bit id (which is how the two open
  StringIds this table format was tested against, `0x5c494554` and
  `0x40b5d875`, are actually cited elsewhere in this project's docs -
  neither is cited as a symbol name in need of `crc32_mpeg2`-reversal).
seq:
  - id: count
    type: u4
    doc: |
      Number of entries. `2.networking` = 2056, `2.common` = 2711,
      `2.subtitles` = 9719, `2.subtitles-temp` = 8178 (English, locale 2).
  - id: records
    type: record
    repeat: expr
    repeat-expr: count
    doc: |
      `records` is sorted ascending by `key` with no duplicates (verified
      over all 2056 `2.networking` entries) - a flat array shaped for
      binary search, though this project's own tooling
      (`research/tools/text_table.py`) just does an O(n) dict lookup since
      a few thousand entries is trivial either way.
instances:
  blob_start:
    value: 4 + count * 8
    doc: |
      Byte offset (from the start of this file) where the null-terminated
      string blob begins - immediately after the last record. The blob's
      very first string (`record[i].string_offset == 0` for any i) is
      always the literal sentinel `"UNKNOWN STRING!!!"` - a fallback string
      for a failed/unresolved lookup, not real game content.
types:
  record:
    seq:
      - id: key
        type: u4
        doc: |
          32-bit StringId. Hash algorithm/source-symbol convention unknown
          (see meta doc: NOT `crc32_mpeg2` of the display string, and no hit
          against the DC00 symbol corpus either). Table is sorted ascending
          on this field.
      - id: string_offset
        type: u4
        doc: |
          Byte offset of this entry's string, RELATIVE TO `blob_start`
          (i.e. NOT relative to the start of the file, and NOT relative to
          this record). The string is ASCII/UTF-8, NUL-terminated, and may
          contain in-band markup tokens observed in real strings (e.g.
          `|FB|`, `|@C00C0AA55|`, `|L3|`, `|START|`, `[A]`/`[B]` - button
          glyphs / color codes / template substitution placeholders; not
          decoded further here, out of scope for the container schema).
