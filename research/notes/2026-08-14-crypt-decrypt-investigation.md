# `.crypt` File Decryption: Investigation (Not Fully Cracked)

Follow-up to `research/notes/net1bin-server-list.md`'s "real fix" section - attempted to find and characterize the decryption routine EBOOT.elf uses for `*.crypt` content-delivery downloads (`net1.bin.psarc.crypt`, `patch.psarc.crypt`, `campaign.config.txt.crypt`), well enough to write a standalone decrypt/re-encrypt implementation. **Not achieved this session** - documenting confirmed findings and the concrete next steps, per this task's own instructions that honest partial progress is a valid outcome.

## Confirmed: the download/decrypt/write pipeline

`FUN_003876ec` (`0x003876ec`) is the file-level orchestrator - referenced by the `"%s/%s/%s.psarc.crypt"` path-template string. Matches the exact `.dl` → rename → decrypt-loop → `.dl` → rename pattern observed live in RPCS3's own fs logs:

1. `cellFsStat`/`cellFsUnlink` on the target (staleness check).
2. Calls a download function (`FUN_00ac5b40`, not traced further - handles the actual HTTP GET).
3. Opens the downloaded file via `FUN_009bb00c` ("open").
4. Gets metadata via `FUN_009b9068` ("get info").
5. Loop: reads 0x1000 (4096)-byte chunks via `FUN_009b8bd8` ("read"), writes each chunk verbatim via `cellFsWrite` to a new `.dl` output file.
6. Closes via `FUN_009b822c`, renames the output into place.

**This confirms decryption+decompression happen transparently inside the "read" call** (`FUN_009b8bd8` → `FUN_00b5cc1c` → ...) - the orchestrator itself just copies whatever bytes come back, unmodified, to the final file.

## Confirmed: the read path goes through Sony's FIOS middleware, not custom Naughty Dog crypto

`FUN_00b5cc1c` (reached via `FUN_009b8bd8`) contains an explicit magic-number check: `*param_3 ^ 0x46494f53`, where `0x46494f53` is literal ASCII **`'FIOS'`**. Combined with extensive `fios*`-prefixed strings already known from earlier sessions (`fiosSndStreamFile...`, `FIOS cache couldn't resolve...`) and a `"fios mediathread 2"` thread name observed live in RPCS3's logs, this confirms the read/decrypt/decompress path is Sony's licensed **FIOS** (File I/O Scheduler) PS3 SDK middleware, not bespoke game code. All functions decompiled so far in this path (`FUN_009bb00c`, `FUN_009b9068`, `FUN_009b8bd8`, `FUN_009b822c`, `FUN_00b5cc1c`, `FUN_00b554f4`) are generic FIOS async-op/buffer-management plumbing (bitflag-driven open modes, timestamp conversion, buffer queues) - no visible cipher operations (no XOR loops, no S-box tables, no key material) in any of them.

## Confirmed: a "dearchiver" component sits on top of FIOS, and is shared with Uncharted 3

Strings reveal a `fios::dearchiver` class (`"sizeof(fios::dearchiver) <= Memory::GetSize(ALLOCATION_FIOS_DEARCHIVER_MEM)"`, `"FIOS dearchiver open file '%s' because it's compressed!"`, `DearchiverArchiveTOC`, `DearchiverArchiveManifest`, etc.) - this is very likely where the actual per-block decompress(+decrypt) transform is registered as a FIOS callback. Decompiled its constructor/buffer-fill functions (`FUN_009bdfb8`, `FUN_009b9868`) - still no visible cipher operations; the actual transform is registered as a function pointer somewhere not yet traced.

**Notable, useful for future work**: the same string cluster containing the content-delivery code also contains `"u3.beta.dev"` / `"u3.beta.prod"` (offsets `0xe6a200`/`0xe6a210`, right next to the `naughtydog.com` template strings) - `u3` almost certainly = *Uncharted 3*, a Naughty Dog title on the same PS3-era engine. **This strongly suggests the FIOS dearchiver/crypt scheme is shared cross-title engine middleware, not TLOU-specific** - meaning the (much larger) Uncharted 3 modding/preservation community may already have documented or cracked this exact format. Worth a dedicated prior-art search before continuing pure static analysis.

## Ruled out: trivial single-byte XOR

Brute-forced every single-byte XOR key against the first 64 bytes of `net1.bin.psarc.crypt`, checking for the PSARC magic (`PSAR`, `0x50534152`) appearing at any header offset 0-63. Zero hits - not a trivial single-byte XOR scheme (assuming the decrypted-then-decompressed... actually decrypted-but-still-PSARC-compressed intermediate does start with the standard PSARC magic, which is a reasonable but unconfirmed assumption - we don't have the intermediate `.psarc` file, only the final fully-decompressed `net1.bin`, since RPCS3 deletes the intermediate).

## Open lead, not validated: possible length-prefix header

The first 4 bytes of `net1.bin.psarc.crypt` are `00 00 fe 6d`. As a big-endian `u32`, `0xfe6d` = 65,133 decimal - suspiciously close to the file's own total size (65,160 bytes; 65,160 − 65,133 = 27 bytes of apparent overhead). Not yet confirmed as a real length field (could be coincidence, or could be counting something else - e.g. the file size minus this same 4-byte header minus a fixed-size IV/nonce of unusual length). Worth checking against `patch.psarc.crypt`/`campaign.config.txt.crypt` (both of which we also have, in `tools/served_content/`... actually only `net1.bin.psarc.crypt` was saved there this session - the other two were only ever proxied through the empty/200 catcher, never saved to disk) if/when copies of those become available, since a consistent header-encodes-total-size pattern across multiple files would confirm this quickly.

## What was NOT achieved

- The actual cipher algorithm (AES, RC4, proprietary, or otherwise) - not identified.
- No key material located.
- No working decrypt implementation - the success criterion (`tools/decrypt_crypt.py` producing byte-identical output to `research/net1bin/net1.bin.orig-backup`) was not reached. No such script was written since there was no validated hypothesis to implement.

## Recommended next steps, in priority order

1. **Search for Uncharted 3 FIOS/dearchiver prior art** - the `u3.beta` string strongly suggests this format is shared and may already be documented/cracked by that game's community.
2. **Check for SPU-side code.** Sony's Edge zlib (`edgezlib_inflate_queue.cpp`, confirmed present via strings in an earlier session) typically runs decompression on SPU threads for performance on Cell - if decryption is similarly SPU-offloaded, it would live in an embedded SPU ELF blob within `EBOOT.elf` that the current Ghidra project (analyzed as PPU-only) doesn't cover. Would need identifying and extracting SPU program blobs (Ghidra has separate SPU processor support) and re-analyzing those specifically.
3. **Trace the dearchiver's function-pointer/vtable setup** to find where the actual per-block transform callback gets registered - `FUN_009bdfb8`/`FUN_009b9868` were dead ends but weren't traced exhaustively (their own callees weren't decompiled).
4. **Validate the length-prefix hypothesis** against additional `.crypt` file samples if any become available.

## Files/scripts from this session

`tools/ghidra_scripts/FindCryptDecryptRoutine.java`, `FindDearchiver.java`, `DecompileByAddresses.java` (generic, reusable - decompile a fixed address list, takes `outPath addr1 addr2 ...` as script args). Reports: `research/ghidra/crypt_decrypt_report.txt`, `crypt_helpers_report.txt`, `crypt_deep_report.txt`, `dearchiver_report.txt`, `dearchiver_decomp.txt`.
