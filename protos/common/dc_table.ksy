meta:
  id: dc_table
  title: DC00 data-compiler container (net1.bin / net10.bin)
  endian: be
  license: CC0-1.0
  doc-ref: docs/protocol/dc_table.md
doc: |
  Container format for the "DC00"-magic registries shipped in the game's
  encrypted content bundles (`net1.bin` for build 01.00, `net10.bin` for
  01.11 - see `server/data/served_content/net*.bin.psarc.crypt`, extractable
  with `server/lib/psarc_crypt.py extract`). This is the format the EBOOT's
  own loader (`FUN_009fc118`, 01.00 VMA) parses - not a guess from a
  hexdump. STATUS: container-level structure CONFIRMED (see doc); the
  higher-level "what does a given DC hash's value actually mean" question is
  solved per-hash, tracked in each hash's own consuming `.ksy` (currently
  `protos/common/member_data.ksy`'s `rank_tier`, `protos/0x11_stat_line.ksy`'s
  task table, and `server/ticket_server.py`'s `pReportArray` comment).

  Any future DC hash this project ever needs to look up in one of these
  files can reuse this schema for the header/relocation layer, then walk
  the payload region by hand the same way this file's paired doc describes.
seq:
  - id: header
    type: header
  - id: payload
    size: header.relocation_table_offset
    doc: |
      The addressable "slot space": a dense sequence of 4-byte big-endian
      words (including the 4 header words themselves - the relocation loop
      walks from byte 0, not from the end of the header). Every word here is
      either a plain literal (int, float, packed flags, a DC hash used as a
      type/key tag) or a file-relative byte offset that the EBOOT's loader
      adds its buffer's load address to, turning it into a real pointer, iff
      the matching bit in `relocation_bitmap` is 1. This project's decoder
      does NOT perform that fixup (no reason to - the file is read
      standalone, not loaded at a chosen address); it reads the still-raw
      offset and treats it as "the byte offset, within this same file, this
      slot points to", which is equivalent for our purposes.
  - id: table_header
    type: table_header
  - id: relocation_bitmap
    size: table_header.count
    doc: |
      One bit per slot in `payload`, LSB-first within each byte, in slot
      order (bit i = slot i, i.e. the word at byte offset `i*4`). bit=1
      means "this slot is a fixup pointer" (a file-relative offset into this
      same file); bit=0 means "this slot is a literal value" - read verbatim.
      Total bit count is `table_header.count * 8`, i.e. exactly enough bits
      to cover every slot in `payload` (byte-verified: `count*32 ==
      header.relocation_table_offset` in net1.bin; net10.bin overshoots by
      12 bytes / 3 slots of harmless padding - the loop just walks a few
      slots into `table_header`/`relocation_bitmap` itself at the very end,
      which is inert in practice since those bytes don't parse as valid
      offsets that matter).
types:
  header:
    seq:
      - id: magic
        contents: [0x44, 0x43, 0x30, 0x30]
        doc: "\"DC00\". Compared as a big-endian u32 (`0x44433030`) at\
          \ `FUN_009fc118+0x00` (`0x009fc148`-`0x009fc158`, 01.00 VMA)."
      - id: version
        type: u4
        doc: Observed value 1 in both net1.bin and net10.bin. Not branched on
          anywhere seen in the parser - likely a format-compat guard for
          older/newer DC compiler output that this game build never exercises.
      - id: relocation_table_offset
        type: u4
        doc: |
          Byte offset, from the start of this file, to `table_header` (i.e.
          to the `count` field that starts the relocation-bitmap region).
          Equivalently, the byte length of `payload`. Read at parser offset
          `+0x08` (`lwz r9,8(r3)` @ `0x009fc170`).
      - id: pad
        type: u4
        doc: Always observed 0 in both files. Unused/reserved 4th header word.
  table_header:
    seq:
      - id: count
        type: u4
        doc: |
          Byte length of `relocation_bitmap` (also: `total_slots / 8`, since
          the bitmap covers every slot 1:1). net1.bin: 8602 (0x219a) ->
          68816 slots -> 275264 bytes of payload, which equals
          `header.relocation_table_offset` exactly. net10.bin: 12397
          (0x306d) -> 99176 slots -> 396704 bytes, 12 bytes more than
          `header.relocation_table_offset` (396692) - the small overshoot
          noted above.
