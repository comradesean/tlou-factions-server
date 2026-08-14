# net1.bin: Confirmed Server List (All Dead)

Full pipeline now confirmed working end-to-end: RPCS3 DNS-hook redirects `t1.final.prod.s3.amazonaws.com` to our catcher -> catcher serves the real `net1.bin.psarc.crypt` (65,160 bytes, user-supplied, saved at `tools/served_content/net1.bin.psarc.crypt`, gitignored) -> game decrypts/extracts it to `net1.bin` (283,870 bytes, plain, `research/net1bin/net1.bin`, gitignored - see below) -> game reads it and attempts `connect to 50.18.104.153:7320`.

## Contents

`net1.bin` has no readable global strings pattern (`strings` finds nothing useful) - it's a large blob of mostly non-text data, but a `grep -a` for IP-address patterns finds exactly one small string cluster at offset `0x3fab2`:

```
174.129.210.135\0
50.18.104.153\0
50.18.47.114\0
>>>>>>>>>>> 25% or more of the population is already sick; preventing downward spiral!\0
>>>>>>>>>>> Player has a supply surplus, no one dies on this day!  Surplus is: %f \n\0
>>>>>>>>>>>>>> More than 10 clan members died today, clamping deaths to 10!\0
```

Three null-terminated IP strings sitting directly next to **unrelated campaign-mode debug text** (survivor-camp population/supply/clan mechanics). This strongly suggests `net1.bin` is a general debug/log string table shared across subsystems, not a purpose-built network config file - the three IPs are most likely **hardcoded fallback server addresses** compiled in as literal debug strings, not a structured server-list format.

Port `7320` (matching the `connect to 50.18.104.153:7320` log line) was not found as an adjacent string or an obvious packed value near the IP cluster - likely a separate hardcoded constant elsewhere (not chased further this session).

## All three confirmed dead

| IP | Reverse DNS | Status |
|---|---|---|
| `174.129.210.135` | `prdrelayb.collaboratemd.com` | **Reassigned to an unrelated company** - definitively not the game server anymore |
| `50.18.104.153` | `ec2-50-18-104-153.us-west-1.compute.amazonaws.com` | Unallocated/generic EC2 reverse DNS, unreachable |
| `50.18.47.114` | `ec2-50-18-47-114.us-west-1.compute.amazonaws.com` | Same - unallocated EC2, unreachable |

All three were almost certainly real Naughty Dog game-server addresses (AWS EC2, `us-west-1`) at some point - now fully decommissioned/recycled. No live target to connect to or capture against here.

## Files (not committed - gitignored)

- `tools/served_content/net1.bin.psarc.crypt` - the real encrypted file the user supplied, now served by `tools/catch_http.py`.
- `research/net1bin/net1.bin` - the decrypted/extracted plain file, pulled from RPCS3's `dev_hdd0/game/BCUS98174DATA2/USRDIR/net1.bin`.

Both are extracted game content (copyrighted), same reasoning as never committing `EBOOT.elf` itself - kept locally only.

## Local hex-patch: works, but does NOT persist (corrected)

`"50.18.104.153"` and `"192.168.1.100"` are both exactly 13 ASCII characters, so a same-length in-place string patch of the locally-decrypted `net1.bin` is trivial and was applied successfully. **However, confirmed by direct log evidence: the game deletes and freshly re-extracts `net1.bin` from the original (unpatched) `net1.bin.psarc.crypt` on every NetInit pass** (`sys_fs_unlink` on `net1.bin` followed by the full download/decrypt pipeline) - it does not durably reuse a cached copy across reconnects the way one boot-in-progress might briefly appear to. A same-boot-session earlier observation of what looked like cache reuse was misleading - don't trust it as a general rule.

**Stopgap in place:** `tools/watch_and_patch_net1bin.py` polls the file every 0.5s and re-applies the patch automatically whenever it changes, so testing isn't blocked by this. Not a real fix - purely a live-testing convenience.

## The real fix: round-trip `net1.bin.psarc.crypt` itself

To make the patched IP stick without a watcher, the *served* `.crypt` file needs to actually contain the patched content. This requires reversing the encryption, since simple known-plaintext byte-patching doesn't work here: the encrypted file is 65,160 bytes vs. 283,870 bytes decrypted (~4.3:1 ratio) - real compression sits between the encryption and the final content, so ciphertext bytes don't correspond 1:1 to plaintext bytes at our target offset.

**Useful reference found:** [`0x0L/rs-utils/bin/psarc.py`](https://github.com/0x0L/rs-utils/blob/master/bin/psarc.py) - a PSARC archive reader/writer used for Rocksmith (same container format family). Confirms the general PSARC structure: 32-byte big-endian header (magic/version/compression type/TOC size/entry size/entry count/block size/flags), a TOC (per-entry 16-byte MD5 + z-index + length + offset, followed by a per-block `zlength` array), zlib-deflate-per-64KB-block compression with automatic fallback to stored (uncompressed) blocks when compression doesn't help, and a `create_psarc()`/`extract_psarc()` pair that can fully round-trip a modified archive. **Rocksmith's specific AES keys/TOC-encryption in that script are not TLOU's.**

**Ghidra investigation attempted (2026-08-14) - not fully cracked, see `research/notes/2026-08-14-crypt-decrypt-investigation.md` for full detail.** Confirmed the decrypt/decompress path runs through Sony's licensed FIOS SDK middleware (explicit `'FIOS'` magic-number check found in the read path), with a `fios::dearchiver` component on top of it that's very likely shared with *Uncharted 3* (a `u3.beta.dev`/`u3.beta.prod` string sits in the exact same code region as the content-delivery strings) - meaning Uncharted 3's much larger modding community may already have prior art on this format, worth searching before more static analysis. Ruled out trivial single-byte XOR. Found an unvalidated lead: the ciphertext's first 4 bytes (`00 00 fe 6d`) decode as a big-endian `u32` to 65,133 - suspiciously close to the file's own 65,160-byte size. No working decrypt implementation yet.

## SOLVED (2026-08-14): full round-trip, verified byte-for-byte

Full details in `research/notes/2026-08-14-blowfish-psarc-solve.md`. Summary: it's not FIOS-proprietary crypto - it's the same Blowfish cipher/key Naughty Dog reused from their PS3 save-game format (`bucanero/save-decrypters`), wrapping a standard PSARC container. `tools/psarc_crypt.py` now implements decrypt, PSARC parse/extract, PSARC build, and re-encrypt, all verified:

- **Decrypt correctness**: matches an independently-compiled C reference implementation byte-for-byte.
- **Extract correctness**: decrypting+extracting the real `net1.bin.psarc.crypt` reproduces `research/net1bin/net1.bin.orig-backup` (the game's own known-good extraction) with an **exact SHA256 match**.
- **Repack correctness (unmodified control)**: `build_psarc()` -> re-encrypt -> decrypt -> extract round-trips back to the exact same SHA256, proving the repack logic itself introduces no corruption.
- **Repack correctness (real patch)**: repacking with `50.18.104.153` -> `192.168.1.100` substituted in `net1.bin`'s content, then decrypting the result back out, differs from the known-good original at **exactly the 13-byte IP field and nowhere else** (`cmp -l` confirms 11 of 13 bytes differ - 2 digits happen to coincide between the two IP strings - with zero other byte differences across the full 283,870-byte file).

`tools/served_content/net1.bin.psarc.crypt` has been replaced with this properly re-encrypted, patched file (old version backed up alongside it as `.pre-repack-backup`, gitignored). The client now gets the correct redirected IP straight from its own decrypt of the served file - `tools/watch_and_patch_net1bin.py`'s live-patch race-condition workaround is no longer needed for this file and can be considered retired (kept in the repo for reference/history).

One open item, not yet load-bearing: the 24-byte prefix before the PSARC magic (`fa6e755c5ff7c67f960bd3086a6b4496c3dbea7550aaaa21` in the real file) is preserved byte-for-byte unmodified in the repacked output rather than regenerated, since its meaning is still unconfirmed (checked and ruled out: not MD5/SHA1/SHA256 of the body, doesn't match any obvious size field). If the client validates it against body content (e.g. as a signature) rather than treating it as opaque/unused, the repacked file could still fail a check we haven't seen yet - next live test will confirm either way.
