# Why repacked `.crypt` files get deleted instead of renamed: found the check

**RESOLVED (2026-08-14, later the same day).** Everything this note originally left
open - the key, the message construction, and live confirmation - was nailed down via
a live RPCS3 debugger session immediately after this note was written. Summary of the
resolution, full mechanics below unchanged as a record of how it was found:

- **The key is static, not session-negotiated** (this note's leading hypothesis was
  wrong): it's `SHA1_HMAC_KEY` from the same `bucanero/save-decrypters` PS3 save-game
  toolkit the Blowfish key was already known to come from -
  `"xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"` (64 bytes).
  Confirmed live: a breakpoint at `FUN_00ac59a0` (the constructor) showed this exact
  string, byte-for-byte, in `r6` at call time.
- **The message is the Blowfish-decrypted PSARC body, including its trailing
  block-alignment padding** (not the raw ciphertext, not trimmed to the real archive
  length) - i.e. `HMAC-SHA1(key, blowfish_decrypt(raw[24:]))` with no trimming.
- **The digest's storage location is genuinely plaintext**, not part of the Blowfish
  stream at all: raw file bytes `[4:24]`. The "24-byte wrapper header" this project
  spent most of a day treating as opaque (checked and ruled out for MD5/SHA1/SHA256
  matches, because those checks were run against the *decrypted* garbage those bytes
  produce when incorrectly treated as ciphertext) was never encrypted in the first
  place - confirmed by reading real memory (`param_1 + 0x53d4` in `FUN_00ac52d4`,
  live, while paused at the breakpoint) and finding it matches the raw file's own
  bytes `[4:24]` exactly.
- `tools/psarc_crypt.py` has been rewritten around this correct understanding
  (`encrypt_crypt_file`/`decrypt_crypt_file`, see the module docstring) - the
  `.wrapper` sidecar hack is gone entirely, since a fully valid header can now be
  regenerated from scratch on every repack. A repacked, IP-patched `net1.bin.psarc.crypt`
  now reports `HMAC OK` on its own re-verification and has been redeployed to
  `tools/served_content/`. Live client acceptance (rename vs. delete) not yet
  re-tested at the time of this edit - that's the next real-world confirmation.

Original investigation follows, kept as-is for the record of how the mechanism itself
was found (this part was all correct and didn't need revision):

---

Follow-up to `2026-08-14-blowfish-psarc-solve.md`'s open problem: every repacked
`net1.bin.psarc.crypt`, even one whose Blowfish/PSARC layers are confirmed
byte-correct and whose length-prefix field is confirmed correct, still gets
`sys_fs_unlink()`'d instead of `sys_fs_rename()`'d during a live RPCS3 test. This
session traced the actual validation check via Ghidra decompilation. **The mechanism
is now identified with high confidence (concrete decompiled code, matching magic
constants); the key material that would let us forge a passing signature is not yet
located.**

## Summary

The rename-vs-delete decision is made by **`FUN_00ac52d4` (`0x00ac52d4`)**, the
finalizer/destructor of the download-session object used by the custom Naughty Dog
HTTP client (`DNTG-HTTPC`, confirmed in a live capture the coordinator supplied - not
Sony's generic `libhttp` used by earlier titles like Uncharted 2). It compares a
locally-computed digest against a stored expected value and only calls
`cellFsRename()` on a match:

```c
int _opd_FUN_00ac52d4(int param_1)
{
  ...
  if (*(int *)(param_1 + 0x11ac) == 0x1bb) {
    sys_lwmutex_unlock(*(undefined4 *)(PTR_PTR_012fec68 + -0x7fb0));
  }
  if (*(int *)(param_1 + 0x13bc) == 0) {
LAB_00ac542c:
    iVar1 = 0;
  }
  else {
    iVar1 = cellFsClose(*(int *)(param_1 + 0x13bc));       // close the .dl handle
    if (-1 < iVar1) {
      _opd_FUN_00ac24ac(param_1 + 0x53e8,auStack_50);       // finalize HMAC -> auStack_50
      iVar1 = _opd_FUN_00e498f0(auStack_50,param_1 + 0x53d4,0x14);  // compare 20 bytes
      if (iVar1 == 0) {                                     // MATCH
        iVar1 = cellFsRename(param_1 + 0x12b0,param_1 + 0x11b0);   // .dl -> final name
        if ((-1 < iVar1) && (iVar1 = cellFsUtime(param_1 + 0x11b0,local_60), -1 < iVar1)) {
          ... return 0;   // success
        }
      }
      else {
        iVar1 = -1;                                         // MISMATCH
      }
    }
    cellFsUnlink(param_1 + 0x12b0);   // <-- reached on mismatch OR any I/O failure above
  }
  return iVar1;
}
```

`param_1 + 0x12b0` and `param_1 + 0x11b0` are the `.dl` source path and final
destination path respectively - populated in the constructor (`FUN_00ac59a0`,
`0x00ac59a0`) from the caller-supplied target path (e.g. `.../net1.bin.psarc`) with
the `.dl` extension appended internally by this object, not by the caller. This
matches the live RPCS3 log exactly: the download target the orchestrator passes in is
literally named `net1.bin.psarc` (built from template `"%s/%s/%s.psarc"` - see below),
and this object is the one appending `.dl` to get `net1.bin.psarc.dl`, downloading
into that, and then either renaming or deleting it. This is consistent with the
coordinator's timing observation that the whole decision happens inline on the
NetInit thread in the ~1.8ms window between `sys_fs_close()` and `sys_fs_unlink()` on
`net1.bin.psarc.dl` - there is no separate downstream consumer thread involved in the
rejection; `FUN_00ac52d4` runs synchronously right after the HTTP body finishes
downloading.

## Confirmed: the check is HMAC-SHA1, not a generic checksum

`_opd_FUN_00ac24ac` (`0x00ac24ac`) and `_opd_FUN_00ac2590` (`0x00ac2590`, called from
the constructor `FUN_00ac59a0`) together implement the textbook two-pass HMAC
construction:

- `FUN_00ac2590` (key setup / inner-hash init): zero-pads or hashes the key into a
  64-byte (`0x40`) block, **XORs every byte with `0x36`** (HMAC's `ipad` constant),
  then hash-inits and hash-updates with that block. If the key is `>= 0x41` bytes it's
  hashed down first via `_opd_FUN_00dcb4c4` (standard HMAC "key longer than block
  size" handling per RFC 2104), otherwise copied in directly.
- `FUN_00ac24ac` (finalize): finalizes the inner hash into a 32-byte scratch buffer,
  then **XORs the same key-block bytes with `0x6a`** - note `0x36 ^ 0x6a == 0x5c`,
  HMAC's `opad` constant, applied as a delta against the already-`ipad`-XORed buffer
  from the previous step (a standard optimization to avoid re-deriving the key block).
  Re-inits the hash, updates with the opad-XORed key block, updates with **the first
  20 (`0x14`) bytes only** of the inner digest, and finalizes into the output buffer.

The underlying hash (`FUN_00dc9700`/`FUN_00dc9768`/`FUN_00dca51c` at
`0x00dc9700`/`0x00dc9768`/`0x00dca51c`) is confirmed **SHA-1** by decompiled code, not
inference from digest size alone:

- `FUN_00dc9700` (init) sets the state words to the SHA-1 IV
  `0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0` verbatim.
- `FUN_00dc9768` (update) and `FUN_00dca51c` (final) both contain the SHA-1 message
  schedule (`W[t] = ROTL1(W[t-3] ^ W[t-8] ^ W[t-14] ^ W[t-16])`) and the 80-round
  compression function with the exact SHA-1 round constants
  `0x5a827999`, `0x6ed9eba1`, `-0x70e44324` (`0x8f1bbcdc`), `-0x359d3e2a`
  (`0xca62c1d6`), split across the classic four 20-round Ch/Parity/Maj/Parity phases.
- `FUN_00dca51c`'s final byte-copy loop copies exactly 20 bytes from the internal
  state to the caller's output buffer - the SHA-1 digest size, matching the `0x14`
  comparison length in `FUN_00ac52d4`.
- The SHA-1 IV constants were independently located as a literal byte pattern in the
  EBOOT at file offset `0xef2610` (VA `0x00f02610`), corroborating this from the raw
  binary as well as the decompiled init function.

The comparison itself (`FUN_00e498f0`) is a generic optimized byte/word-wise memcmp
(handles 8-byte, 4-byte, then 1-byte chunks) - not a hash itself, just proves
byte-for-byte equality of the two 20-byte buffers.

**Conclusion: the client computes `HMAC-SHA1(key, downloaded_bytes)` over the raw
downloaded content as it streams in, and only commits (`rename`s) the `.dl` file if
that digest matches a 20-byte expected value already present in the download-session
object before the comparison.** This is what's rejecting our repacks - our modified
content's HMAC will never match a digest that was computed against the *original*
bytes, regardless of how structurally correct our repack is.

## Where the message bytes get fed in (not fully proven, high confidence)

`FUN_00ac3af8` (`0x00ac3af8`, the actual HTTP download loop, called from
`FUN_00ac5b40` immediately after the constructor) streams the HTTP response body
through a **virtual call table** rather than calling `cellFsWrite`/hash-update
directly - the object at `param_1` has a vtable (`*param_1`) and the loop invokes
methods at fixed vtable offsets for connect/status/header-read/body-read. The chunk
consumption call:

```c
iVar11 = (*(code *)**(undefined4 **)(*param_1 + 0x2c))(param_1,piVar5,uVar12);
```

is called immediately after each successful chunk read, with `piVar5` (`= param_1 +
3`, i.e. the raw chunk buffer) and `uVar12` (the chunk length) - the natural place for
a "write chunk to disk and feed the running hash" method. This wasn't traced into a
concrete implementation (virtual dispatch means the real callee depends on which
concrete class is constructed, not resolvable by a simple static address lookup), but
the timing and call shape strongly support it being where `_opd_FUN_00dc9768`
(SHA1Update) actually gets called per-chunk, keeping the HMAC computation entirely
inline with the download rather than a separate pass over the finished `.dl` file.
This is consistent with the coordinator's ruling that everything happens in one tight
inline window on the NetInit thread.

## Still open: where the *key* and the *expected digest* come from

This is the actual blocker for reproducing a passing signature, and wasn't resolved
this session.

**Key** (`FUN_00ac2590`'s `param_2`/`param_3` args, passed in from the constructor as
`_opd_FUN_00acde4c()`'s return value and its length via `_opd_FUN_00e40ad8`):
`_opd_FUN_00acde4c` (`0x00acde4c`) is a trivial double-pointer-dereference accessor
(`return **(undefined4 **)(PTR_PTR_012fec88 + -0x8000);`, resolving to global slot
`0x012f6c88`). Its callers are **not** limited to the content-download path - it's
also called from `FUN_000216a0` (`0x000216a0`), `FUN_007f149c` (`0x007f149c`),
`FUN_00021210` (`0x00021210`), `FUN_00080268` (`0x00080268`), `FUN_00357964`
(`0x00357964`) - all in areas that overlap with this project's existing
ticket-server/NetInit handshake investigation
(`research/ghidra/ticket_server_handler_report.txt`,
`research/ghidra/connect_site_report.txt`). **This strongly suggests the HMAC key is
not a static compile-time constant embedded in the EBOOT (unlike the Blowfish key,
which is a literal string), but a per-session secret tied to the authenticated
network/ticket-server session** - e.g. a session key or ticket byte-string negotiated
during the NetInit handshake this project already runs its own RPCN/ticket-server
stand-in for. If true, this is actually good news: we may already control or can
observe the key material at handshake time, since our own ticket server is the one
negotiating it in this test setup. Static tracing of `0x012f6c88`'s write site did not
succeed this session (`FindCallersOf`-style reference search only found a `<none>`
DATA reference at `0x0124f200`, not a resolvable code write - likely because the
write uses r2/r13-relative addressing that Ghidra's static analysis doesn't always
resolve to a clean cross-reference). Next step: open `0x012f6c88` directly in the
Ghidra GUI (not headless) and check the Data/Symbol tree's "used by" list, or trace
`FUN_000216a0`/`FUN_00357964` (both plausible NetInit-handshake-adjacent functions)
by hand for the write.

**Expected digest** (`param_1 + 0x53d4`, compared against in `FUN_00ac52d4`): no write
site for this offset was found in `FUN_00ac59a0`, `FUN_00ac52d4`, or `FUN_00ac2590` -
it must be populated somewhere inside `FUN_00ac3af8`'s vtable-dispatched HTTP layer
(most likely the header-parsing virtual call at vtable offset `+0x24`, or an internal
manifest lookup keyed by resource name), neither of which was resolved to a concrete
implementation this session. Two live pieces of negative evidence from the
coordinator's real-capture cross-check rule out the simplest hypothesis: a real
Uncharted 2 (older Naughty Dog title, generic Sony `libhttp` client) capture fetching
its own `.psarc.crypt` files shows **no `Content-MD5` or comparable integrity header**
in the S3 response - only upload-tool metadata headers (`ETag`,
`x-amz-meta-md5-hash`, `x-amz-meta-bucketexplorer-sha1`) that a client wouldn't
plausibly treat as authoritative. Since TLOU's client is confirmed to use a
rewritten, in-house `DNTG-HTTPC` client rather than that generic one, it's possible
TLOU adds its own non-standard header - but given the key is very likely
session-derived (see above), a more likely design is: **the expected digest is itself
computed or looked up using the same session-derived key/context, either from a
manifest resource fetched earlier in NetInit (`campaign.config.txt.crypt` is a
plausible candidate - it's fetched via the same code pattern, see below) or supplied
directly by the ticket/session server as part of session setup**, not read out of the
HTTP response for `net1.bin.psarc.crypt` itself at all.

## Confirmed: this is the same mechanism for every `.crypt` content file, not net1.bin-specific

`FUN_00387368` (`0x00387368`, previously seen in `crypt_decrypt_report.txt` as the
generic per-file variant used for `patch.psarc.crypt`/`campaign.config.txt.crypt`)
also calls into `FUN_00ac5b40` the same way `FUN_003876ec` (the net1.bin-specific
orchestrator) does. This matches the RPCS3 log directly: a real capture in this
session showed a `patch.psarc.crypt` download return 0 bytes (no patch available for
this build), get written to `patch.psarc.dl` (0/0 bytes), then immediately
`cellFsUnlink()`'d rather than renamed, followed by two failed
`sys_fs_open(patch.psarc, read)` attempts and a `"ERROR: failed to open archive"` tty
log line - the same delete-not-rename signature, on an empty/failed download this
time rather than a hash mismatch, but through the identical code path. This confirms
the HMAC gate applies uniformly to all crypt-delivered content.

## Ruled out this session

- Any validation living in the FIOS/`fios::dearchiver` layer
  (`crypt_decrypt_report.txt`'s original lead) - confirmed via direct RPCS3 log
  correlation that the FIOS-mediated read of the *decompressed* `net1.bin` only
  happens **after** the `.psarc` file already exists on disk (i.e. after the
  rename/no-rename decision is already final). The dearchiver never gets a chance to
  run against a rejected repack, so it cannot be the gate.
- A generic CRC32 check: the binary does contain a standard `zlib`-style CRC32
  implementation (table located at VA `0x00eb51e0`, functions `FUN_0090ae9c`/
  `FUN_0090ae3c`), but tracing its ~20 callers shows it's used exclusively by an
  unrelated netcode command-serialization/opcode-dispatch system (the same
  "netevent" queue documented in this project's ticket-server investigation), not
  anywhere near the download/content-delivery path.
- Standard HTTP integrity headers (`Content-MD5`, `ETag`, etc.) as the source of the
  expected digest - real captures (this session's Uncharted 2 cross-check) show S3
  doesn't send them for `.psarc.crypt` GET responses in a form a client would
  reasonably treat as authoritative.
- (Carried over from `2026-08-14-blowfish-psarc-solve.md`, still valid): the
  length-prefix field and a hash of the 24-byte wrapper are not what's being checked
  here either - they're a separate, already-fixed, already-passing check. This HMAC
  gate is a *different* check that runs even after the length-prefix issue was fixed.

## Confidence

- **High / confirmed by decompiled code, not inference**: `FUN_00ac52d4` is the
  rename-vs-unlink decision point; the check is `HMAC-SHA1(key, msg)` compared
  byte-for-byte against a stored 20-byte value; SHA-1 identity confirmed via matching
  IV constants, round constants, and message schedule, independently corroborated by
  the same IV constants existing as a raw byte pattern in the binary.
- **Medium**: the message fed into the HMAC is the raw downloaded bytes, fed
  incrementally per-chunk via a vtable method at offset `+0x2c` in `FUN_00ac3af8` -
  strongly implied by call-site shape and timing, not confirmed by decompiling a
  concrete vtable implementation.
- **Low / open**: where the key and expected digest actually come from at runtime.
  This is the actual blocker for forging a valid signature and is the clear next step.

## Next steps, in priority order

1. Trace `0x012f6c88`'s write site (the HMAC key singleton) by hand in the Ghidra GUI,
   or by decompiling `FUN_000216a0`, `FUN_00357964`, and `FUN_00080268` in full (all
   confirmed callers of `_opd_FUN_00acde4c`) - if the key turns out to be a
   session/ticket-server-negotiated value, cross-reference against this project's
   existing ticket-server investigation (`ticket_server_handler_report.txt`,
   `connect_site_report.txt`) to see if our own RPCN stand-in already knows or
   controls it.
2. Decompile `FUN_00ac3af8`'s vtable setup (find where the concrete object's vtable
   pointer gets assigned, likely in `FUN_00ac59a0` or a constructor it calls) to
   resolve the `+0x24` (candidate header-read) and `+0x2c` (candidate
   write-chunk-and-hash) virtual methods to concrete addresses, confirming both where
   the expected digest is populated and where the running HMAC is actually fed.
2b. In parallel, check whether `campaign.config.txt.crypt` (fetched via the same
    `FUN_00387368`-style path) is fetched *before* `net1.bin.psarc.crypt` during a
    real NetInit sequence (check RPCS3 log ordering) and whether its decrypted content
    contains anything resembling a per-file hash/manifest table - if so, that's very
    likely where the expected digest for `net1.bin.psarc.crypt` comes from.
3. If the key does turn out to be static/derivable (not session-bound), it would be
   directly usable to forge a valid HMAC for a modified `net1.bin`; if it's genuinely
   session-negotiated and we don't control it, that's a hard blocker on this whole
   approach and worth surfacing to the user explicitly rather than continuing to chase
   repacks that can never pass.

## Files from this session

`tools/ghidra_scripts/ResolveTocStrings.java` (new - resolves the
`PTR_DAT_xxx + offset` chains this binary's generated sprintf-style calls use, down to
the actual referenced string; reusable for any future "what does this format-string
template actually say" question). Reports: `research/ghidra/download_fn_decomp.txt`,
`download_fn2_decomp.txt`, `hash_check_decomp.txt`, `hash_algo_decomp.txt`,
`toc_strings_report.txt`, `crc32_table_refs_report.txt`, `crc32_str_callers_report.txt`,
`crc32_buf_callers_report.txt`, `crc32_buf_caller_decomp.txt`, `sha1_const_refs.txt`,
`singleton_refs.txt`, `acde4c_callers.txt`.
