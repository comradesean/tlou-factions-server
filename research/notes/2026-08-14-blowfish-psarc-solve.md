# `net1.bin.psarc.crypt`: full crypto + container solve

Supersedes the "not fully cracked" status in `2026-08-14-crypt-decrypt-investigation.md`.
The FIOS/dearchiver lead from that session was a red herring for the *cipher* itself
(FIOS is the loader that consumes the decrypted archive, not the thing doing the
decryption) - the actual encryption turned out to be much simpler and, in retrospect,
predictable: Naughty Dog reused the same Blowfish implementation and key across both
their PS3 save-game format and their content-delivery archives.

## The cipher

Found via `bucanero/save-decrypters` (`RipleyTom`-adjacent PS3 homebrew-scene tooling,
originally reversed by `Red-EyeX32`/`aerosoul94` from *The Last of Us*'s own PS3
save-game decrypter). Key facts, cross-checked against `common/blowfish.c`:

- Standard Blowfish Feistel core (`crypt_64bit_up`/`crypt_64bit_down`), but the key
  schedule is derived from a **custom 4168-byte `BLOWFISH_KEY_DATA` seed table**
  (`apply_keycode()`), not the textbook Blowfish P-array/S-box constants. This table
  had to be extracted verbatim from the reference header, not regenerated.
- `SECRET_KEY = "(SH[@2>r62%5+QKpy|g6"` - confirmed to be the **same key** for both
  PS3 save-games (the tool's original purpose) and `net1.bin.psarc.crypt` (Factions
  content delivery). No per-file or per-title key variation found.
- ECB, no IV - each 8-byte block encrypts independently. Any trailing partial block
  (`size & 0xFFFFFFF8` in the C source) is left untouched.
- **Endianness trap** (cost a full debugging pass): `apply_keycode()`'s C source
  builds each key-schedule word via `char tmp[4]; tmp[3]=...; tmp[2]=...; ...;
  keybuf[i] = keydata[...] ^ *(uint32_t*)tmp;` - a byte-reversed write followed by a
  **raw pointer-cast read**, which is little-endian-native on any x86-64 host running
  this code. That is mathematically equivalent to a direct big-endian read of the
  original bytes in forward order. A first Python port used big-endian
  `struct.unpack('>...')` uniformly (matching the PS3 target's own endianness, which
  seemed like the safer assumption) and produced a *self-consistent* cipher - its own
  `encrypt(decrypt(x)) == x` held - but did not match the independently-compiled C
  reference's actual decrypt output. Root-caused by re-deriving the pointer-cast
  semantics by hand; fixed in `tools/psarc_crypt.py` by using explicit little-endian
  reads (`_native_read_u32_array`/`_native_write_u32_array`) for key-schedule
  construction, while keeping the explicit `ES32()`/`_es32()` byte-swap **only** where
  the C source applies it (the data buffer being encrypted/decrypted, not the key
  schedule). After the fix, decrypt output matched the C reference byte-for-byte.

## The container: standard PSARC

Once decrypted, the plaintext (after a 24-byte prefix, see below) is a standard Sony
PSARC archive - the same container family used across other Naughty Dog/first-party
PS3 titles, structurally identical to the one `0x0L/rs-utils`'s `psarc.py` documents
for Rocksmith (that script's *keys* are Rocksmith-specific and irrelevant here, but its
container-format description was accurate and saved real time).

Confirmed empirically against the real file (`net1.bin.psarc.crypt`, 2 entries -
manifest + `net1.bin`):

- 32-byte big-endian header: `magic='PSAR'`, `version=0x00010004`, `compression='zlib'`
  (stored as a plain `u32`, but its 4 bytes spell the ASCII string), `toc_size`,
  `entry_size=30`, `num_entries`, `block_size=65536`, `flags=0`.
- TOC: `num_entries` x 30-byte rows - `md5(16)`, `zindex(u32 BE)`,
  `length(u40 BE)`, `offset(u40 BE)`.
- **TOC `md5` field is `md5(entry name)`, not `md5(entry content)`.** Confirmed by
  direct computation: entry 1's TOC md5 (`3ef303e716c6404baa395d2ddbef6c44`) matches
  `hashlib.md5(b"net1.bin").hexdigest()` exactly, while `md5(actual file content)` is a
  completely different value (`4c40ce2e82b94ca34e63ff0f23d50fc5`). Entry 0 (the
  manifest) has an all-zero md5 rather than a hash of anything - it has no "name" of
  its own in the manifest-list sense.
- Immediately after the TOC: one `u16` BE `zlength` per block, globally sequential
  across *all* entries in TOC order (entry 0's blocks first, then entry 1's, etc. -
  `zindex` is just this array's starting index for a given entry, not a per-entry
  restart).
- `zlength[i]` semantics (this took a second bug to get right - see below):
  `0` or `== raw_block_size` (the block's actual uncompressed size, `min(block_size,
  bytes_remaining_in_this_entry)`) both mean "stored, this block was not zlib-compressed
  at all -  use `raw_block_size` bytes verbatim from the data section." Any other,
  strictly smaller value means "zlib-compressed, `zlength[i]` bytes of deflate stream."
  The `== raw_block_size` case is easy to miss if you only test against a full 64KB
  block (where "not compressed" always shows up as literal `0`) - it's only forced by
  a *small* stored entry, e.g. the 8-byte manifest here (`zlength[0] = 8`, matching
  `raw_block_size = 8`, not `0`). Missing this case produced `zlib.error: Error -3 ...
  invalid block type` from trying to inflate the manifest's raw ASCII text.
- Entry offsets are contiguous, immediately following each other with no padding
  (manifest at offset 104 [`= toc_size`], length 8; `net1.bin` at offset 112 = 104+8).
- Confirmed via direct SHA256 comparison against `research/net1bin/net1.bin.orig-backup`
  (the real game's own extraction of the real file) that this decode is exact.

`tools/psarc_crypt.py`'s `build_psarc()` mirrors all of the above in reverse to
produce a fresh, valid archive from a `(name, content)` entry list, and `list`/`extract`
against a repacked-but-unmodified file reproduce the exact same SHA256 as the original,
proving the round-trip is lossless before ever touching real content.

## The 24-byte prefix - still unconfirmed, treated as opaque

Before the `PSAR` magic there's a 24-byte block
(`fa6e755c5ff7c67f960bd3086a6b4496c3dbea7550aaaa21` in the real file) whose purpose
isn't understood. Checked and ruled out as a simple integrity mechanism:

- Not `MD5`/`SHA1`/`SHA256` of the PSARC body that follows it (no match against any of
  the three, full or truncated).
- Doesn't correspond to any obvious size field (body length, file length, or block
  count) interpreted as big-endian `u32`s or `u64`s.

Given no evidence it's derived from content, `build_crypt_file()` currently just
**carries the original 24 bytes through unmodified** rather than attempting to
regenerate something we don't understand. This is the one part of the round-trip not
yet validated live - if the client checks this field against body content in a way we
haven't observed yet (e.g. some kind of signature), a repacked file could still be
rejected downstream. Next live test against the real client will confirm.

## Result

`tools/psarc_crypt.py` CLI:
- `decrypt <in> <out>` - raw Blowfish decrypt, no container parsing.
- `list <in>` - decrypt + parse PSARC + print entries.
- `extract <in> <out> --entry <name>` - decrypt + parse + extract one entry's content.
- `repack <in> <out> [--replace FIND REPLACE] [--target-entry NAME]` - decrypt, parse,
  optionally do a same-length find/replace inside one entry's content, rebuild the
  PSARC container, re-encrypt, write a new `.crypt` file.

`tools/served_content/net1.bin.psarc.crypt` has been replaced with the output of:

```
python3 psarc_crypt.py repack served_content/net1.bin.psarc.crypt.pre-repack-backup \
    served_content/net1.bin.psarc.crypt --replace "50.18.104.153" "192.168.1.100"
```

verified via `cmp -l` against the known-good extraction to differ in **exactly** the
13-byte IP field (11 of 13 bytes differ; 2 digits coincide between the two IP strings)
and nowhere else across the full 283,870-byte file.
