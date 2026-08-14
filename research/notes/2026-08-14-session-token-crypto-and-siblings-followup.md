# Follow-up pass: session_token traced, message-C schema corrected (major), sibling family mapped

Follow-up to `research/notes/2026-08-14-ticket-server-protocol-mapping.md`
and `docs/protocol/0x11_ticket_server_hello.md`. Two goals this pass: (1)
resolve the two open items flagged there (`session_token`'s consumer,
message D's consumer), (2) map the five sibling `*-server` names to confirm
whether they share ticket-server's handshake. Goal 1 produced a much bigger
result than expected - a live capture arrived mid-session that disproved
the existing message-C schema outright, and chasing that down uncovered a
whole encrypted-frame layer this investigation didn't previously know
existed. Full evidence in `docs/protocol/0x11_ticket_server_hello.md`
(updated in place) and the new `docs/protocol/0x11_sibling_servers_family.md`.

## Headline results

1. **`session_token` is not dead - it's live encryption key material.** A
   full decompile of `FUN_003557a8` (the NetInit orchestrator) confirmed it
   never reads `conn+0x50` back out directly - that part of the original
   "resolved: dead field" conclusion this pass first reached was correct as
   far as it went, but **incomplete**: one level deeper, in the actual send
   helper `FUN_00acb6fc` (reached via `FUN_00acd5f8`, which the
   orchestrator calls), `conn+0x50` is read, used to key a custom cipher,
   and incremented after every frame sent. The "dead field" conclusion
   was reached, written into a `.ksy` file, and then reversed again within
   this same pass once the deeper trace was done - see "How this was
   caught" below for why the first pass missed it.

2. **The existing `ticket_server_ticket_submit.ksy` schema (2-byte BE
   length + raw ticket bytes) was wrong**, disproven by the first-ever real
   live capture of this message (272 bytes, `captures/tcp_catch.log`,
   `2026-08-14T08:11:28`). The real format is a 20-byte header (`0x33`
   magic, pad count, BE plaintext length, 16-byte auth tag) followed by an
   encrypted, padded copy of the payload - confirmed **byte-exact** against
   the capture: header says `plaintext_len=250, pad_count=2`, and
   `20 + 250 + 2 = 272`, exactly the captured length, with the pad-count
   formula (`(-250)&3==2`) independently matching too.

3. **Message D (ticket_submit_response) is not a fixed 16 bytes either** -
   that was traced to a decompiler-dropped function argument, not a real
   constraint. It shares message C's frame format, decoded by a different
   function (`FUN_00acbb90`) keyed by `client_nonce` (`conn+0x4c`) rather
   than `session_token` - the receive-side counter is seeded by the value
   the *client* sent in message A, so a server can derive it without any
   secret exchange.

4. **This encrypted frame layer is shared code, not ticket-server-specific**
   - the same `FUN_00acd5f8`/`FUN_00acb6fc`/`FUN_00acd568`/`FUN_00acbb90`
   functions are used by every sibling `*-server` connection's post-hello
   traffic too. This means every "plain ASCII text command" this pass
   found in the sibling survey (see below) is actually plaintext input to
   this same cipher, not what's actually on the wire.

5. **The cipher itself is fully decompiled (a custom, unnamed ARX
   construction) but not yet reimplemented or verified** - a candidate
   static 16-byte key was located, but flagged medium confidence pending an
   actual working decrypt attempt. This is now the single highest-value
   next step for the whole investigation.

6. **Four of the five sibling `*-server` names are confirmed to share
   ticket-server's exact hello/hello_response handshake** - not by
   independently re-deriving each one, but via reference enumeration
   confirming they all call the literal same function, `FUN_00acc424`.
   `invite-server` has **zero code call sites** anywhere in the binary
   (only a data-table entry) - likely dead/unused in this build.

## How the wrong "session_token is dead" conclusion happened (worth recording)

This pass's own process is instructive. Step 1 was a full decompile of
`FUN_003557a8` and a grep for every use of the connection-object stack
variable (`auStack_56c`) - found exactly 8 uses, none reading `+0x50`, and
concluded "write-only, dead." This was **methodologically reasonable but
scoped too narrowly**: it only checked the ORCHESTRATOR function, not the
several layers of socket-helper functions underneath it
(`FUN_00acd5f8` -> `FUN_00acb6fc`) that the orchestrator calls but doesn't
inline. The mistake was compounded by a genuine Ghidra decompiler
limitation: `FUN_00acd5f8`'s own decompiled body shows only ONE parameter
being used, even though its caller passes three - raw disassembly showed
why (the function never touches r4/r5 at all, so they pass through to its
own `bl` call by register inertia, invisible to a per-function decompile
without inter-procedural analysis, which this headless Ghidra session
doesn't have since the project is opened with `-noanalysis`). This same
parameter-drop pattern recurred at least four more times this pass
(`FUN_00acd568`, `FUN_00db5ec0`'s 2nd parameter, `FUN_00db7c80`'s call
inside `FUN_00db7f88`) - flagging it explicitly here since it's a trap this
investigation will likely hit again: **whenever a Ghidra decompile of a
small wrapper function shows fewer parameters used than its call sites
pass it, get the raw disassembly of that specific function before trusting
the decompiled prototype.**

## What triggered the correction

Mid-pass, the coordinator reported the first-ever live capture of message
C (a real 272-byte client send, obtained after the coordinator's
`tools/ticket_server_stub.py` correctly got past message B for the first
time). The captured bytes' first two bytes, read under the then-current
schema as a big-endian length field, gave a nonsensical 13058 - far larger
than the 272-byte total message, under any endianness. That contradiction
is what prompted re-deriving the send/recv path from raw disassembly
instead of trusting the orchestrator-level decompile, which is what
surfaced the whole frame/cipher layer.

## Sibling family survey (goal 2)

Full method and evidence in `docs/protocol/0x11_sibling_servers_family.md`.
Summary:

- **Confirmed live (share `FUN_00acc424`)**: `heartbeat-server` (1 call
  site), `leaderboard-server` (4 call sites - 2 distinct sub-protocols:
  score-submit and a batched line-oriented roster-fetch), `facebook-server`
  (2 call sites - presence-check and NpId lookup), `single-player-server`
  (2 call sites - save-sync and trophy-unlock notify).
- **Not found**: `invite-server` - only a data-table reference, zero code
  call sites anywhere in the binary. Best read: cut/unused feature in this
  build.
- Per-service plaintext payload shapes were traced structurally (buffer
  sizes, loop counts, helper functions used) but not byte-mapped to the
  same depth as ticket-server, per the coordinator's "breadth over depth"
  instruction - and given the encrypted-frame-layer discovery, byte-mapping
  the plaintext for these is lower priority than finishing the cipher
  reimplementation for ticket-server first (the frame layer has to be
  crackable before any of these payloads are recoverable from a real
  capture anyway).

## What's still open

1. **Reimplement and test the ARX cipher** against the real 272-byte
   capture (candidate key + `session_token=0`) - see the "Encrypted frame
   layer" section of `docs/protocol/0x11_ticket_server_hello.md` for the
   full algorithm as decompiled, and its "Next steps" for specifics. This
   is now the top priority for the whole ticket-server thread.
2. **Update `tools/ticket_server_stub.py`** to build protocol-legal
   encrypted frames for message D once the cipher works - its current
   all-zero 16-byte reply is very likely not a valid frame.
3. **Confirm the static key bytes** found this pass
   (`research/ghidra/key_dump3.txt`, `00ed7a50`: `78 56 34 12 32 54 76 98
   88 ef cd ab ef cd ab 89`) - flagged medium confidence, sits directly
   against an unrelated string literal in memory, not yet used in a working
   decrypt.
4. **Sibling per-service plaintext field layouts** - structurally
   identified, not byte-mapped (lower priority per above).
5. **Real port numbers for the four live siblings** - only ticket-server's
   7320 is confirmed; `net1.bin`'s raw binary layout wasn't decoded this
   pass to pull the others.

## Deliverables from this pass

- `docs/protocol/0x11_ticket_server_hello.md` - updated in place: message D
  section rewritten, new "Encrypted frame layer" section (the bulk of the
  new evidence), "Ruled out / corrected" section added, confidence table
  and next-steps rewritten.
- `docs/protocol/0x11_sibling_servers_family.md` - new companion doc, the
  sibling survey.
- `protos/0x11_ticket_server_hello_response.ksy` - `session_token` field
  doc corrected (dead -> live key material).
- `protos/0x11_ticket_server_ticket_submit.ksy` /
  `_ticket_submit_response.ksy` - rewritten for the real frame format.
- `protos/0x11_heartbeat_server_hello.ksy` / `_hello_response.ksy`
- `protos/0x11_leaderboard_server_hello.ksy` / `_hello_response.ksy`
- `protos/0x11_facebook_server_hello.ksy` / `_hello_response.ksy`
- `protos/0x11_single_player_server_hello.ksy` / `_hello_response.ksy`
- `docs/protocol/README.md` - opcode-family table updated.
- Ghidra evidence dumps: `research/ghidra/netinit_full_decomp.txt` (full
  `FUN_003557a8` decompile), `research/ghidra/sibling_servers_report.txt`,
  `research/ghidra/acc424_all_callers.txt`, `research/ghidra/
  send_path_disasm.txt`, `research/ghidra/base64_layer_decomp.txt`,
  `research/ghidra/cipher_core_decomp.txt`, `research/ghidra/key_dump3.txt`.
- New reusable Ghidra scripts: `tools/ghidra_scripts/DecompileFull.java`,
  `FindSiblingServers.java`, `DumpRawDisasm.java`, `ResolveTocPointerChain.java`.

## Addendum (same day, third pass): cipher reimplemented and verified - decrypt not yet working

Coordinator follow-up ask: reimplement the ARX cipher in Python, actually
decrypt the real 272-byte capture, verify via the frame's own auth_tag
(not just eyeballing plaintext), resolve two specific ambiguities
(`FUN_00db5ec0`'s exact key-mixing mechanism, and whether `FUN_00db7e08`
decrypt is really a mirror of `FUN_00db7cb0` encrypt), and if it works,
derive a real message-D response.

**Both flagged ambiguities are now fully resolved**, by disassembling
`FUN_00db5ec0` and `FUN_00db7e08` directly (raw PPC, not decompiled C,
which drops parameters here like everywhere else in this call chain) - see
the "Encrypted frame layer" section of `docs/protocol/0x11_ticket_server_hello.md`
for the full derivation. Headline: the coordinator's specific worry about
decrypt/encrypt asymmetry was correct and confirmed real -
`FUN_00db7e08`'s CFB feedback uses the ORIGINAL ciphertext word for the
next round, not the recovered plaintext, unlike a naive symmetric
assumption which would silently produce garbage after the first 4-byte
word.

**The algorithm was reimplemented in `tools/ticket_cipher.py` and verified
three independent ways**: self round-trip (encrypt then decrypt recovers
the original plaintext and passes tag verification for arbitrary
keys/counters), a from-scratch literal byte-level re-simulation of
`FUN_00db5ec0` matching the simplified implementation bit-exact across 5
random trials, and manual instruction-by-instruction re-derivation of the
shared round function against raw disassembly from BOTH `FUN_00acb6fc`
(encode) and `FUN_00acbb90` (decode) independently - confirming both
resolve the static key through identical TOC offsets, ruling out a
per-function key mismatch.

**Despite this, `decrypt_frame()` does not currently produce a valid
decrypt of the real capture.** Using the candidate key from
`research/ghidra/key_dump3.txt` and `session_token=0` (confirmed correct -
the stub's own log shows it sent literal zero bytes), the recovered
"plaintext" is high-entropy with no ticket-like structure, and its
self-computed auth_tag does not match the frame's embedded tag. Checked
and ruled out as explanations: a transcription error in the capture bytes
(re-verified byte-for-byte against the raw log file), a brute-force sweep
of session_token/counter values 0-19999, and several plausible key
byte-order variants (full reverse, per-word reverse, word-order reverse).
Given the algorithm is now verified this thoroughly by three independent
methods, **the remaining suspect is the candidate key value itself** -
even though its address-resolution mechanism is independently corroborated
by neighboring table entries correctly resolving to real, recognizable
debug strings (including `"connect to %s:%i"`, already known from earlier
sessions of this investigation).

**Did not attempt** deriving a real message-D response, since doing so
without a confirmed-working encrypt would just be producing another
unverified guess dressed up as "real" - not what was asked for. Once the
key is confirmed (see next step), `tools/ticket_cipher.py`'s
`encrypt_frame()` is ready to use for this immediately.

**Next step (unchanged from the main doc, repeated here for emphasis given
this is flagged high-priority)**: a live RPCS3 debugger session - set a
breakpoint at `FUN_00db5ec0` (`0x00db5ec0`) or `FUN_00acb6fc`'s call into
it (`0x00acb788`) during a real live-test connection, dump the actual
runtime key bytes and/or step through comparing register values against
`tools/ticket_cipher.py`'s `arx_round()`. This is likely a single-session
task given the algorithm is already verified - it worked for the `.crypt`
HMAC key in `research/notes/2026-08-14-repack-rejection-investigation.md`
and should work here too.

### Deliverables from this addendum

- `tools/ticket_cipher.py` - verified cipher-algorithm reimplementation
  (encrypt/decrypt/digest/key-schedule/tag-finalize), not yet confirmed
  against real ciphertext (key unconfirmed).
- `docs/protocol/0x11_ticket_server_hello.md` - "Encrypted frame layer"
  section rewritten with the fully-resolved round function, CFB asymmetry,
  key schedule, and tag finalization, plus the reimplementation attempt's
  honest result.
- `protos/0x11_ticket_server_ticket_submit.ksy` - doc updated to reflect
  algorithm verification status.
- `research/ghidra/cipher_final_disasm.txt`, `round_funcs_disasm.txt`,
  `finalize_disasm.txt`, `acbb90_key_check.txt`, `alt_keys.txt` - raw
  disassembly evidence backing all of the above.
- New Ghidra script: `tools/ghidra_scripts/DumpBytesAt.java`.

## Addendum 2 (same day, fourth pass): SOLVED - key confirmed live, bug found via emulation, real ticket decrypted

The coordinator broke into a live RPCS3 process at `FUN_00db5ec0`'s entry
during a real NetInit run and confirmed, directly from process memory: `r3`
(key pointer) = `0xed7a50` on both call sites within one frame, and the 16
bytes actually AT that address matched the candidate key byte-for-byte;
`r4` (counter) = `0` on both hits. This independently confirmed the key two
ways (static TOC-chain resolution + live memory read) and correctly
concluded the remaining bug had to be in this project's own Python
reconstruction of the algorithm, not the key material - and asked for a
concrete, byte-by-byte trace comparison to pin it down rather than further
architectural guessing.

**Method: ground-truth Ghidra emulation, not more disassembly reading.**
Wrote `tools/ghidra_scripts/EmulateKeySchedule.java`, using
`ghidra.app.emulator.EmulatorHelper` (Ghidra's own PPC pcode emulator) to
actually *execute* `FUN_00db5ec0` with the confirmed key and `counter=0`
against a scratch memory region, checkpointing the 4-word state at every
internal call boundary (full trace: `research/ghidra/keysched_trace.txt`).
Comparing each checkpoint against the equivalent value computed by
`tools/ticket_cipher.py` found that every step matched exactly except the
very last one (the finalization round).

**The bug**: `key_schedule()`'s finalization step modeled
`FUN_00db5ec0`'s explicit `FUN_00db7c80` byte-swap of a state snapshot as
producing a "reversed_words" array to feed into the final ARX round. This
double-counted a transformation: `FUN_00db7cb0` (the function actually
called for that step) *also* performs its own internal byte-swap-in on its
data argument - the same pattern this module's `words_from_bytes()`/
`bytes_from_words()` helpers already correctly modeled for every other call
site in the whole cipher. Two byte-swaps in a row cancel out (it's an
involution), so the real data fed into the finalization round is simply the
state's own current words, unchanged - the state is fed through itself.
One-line fix in `key_schedule()`; confirmed to match the emulated ground
truth bit-for-bit at every checkpoint afterward.

**Result: `tools/ticket_cipher.py` now correctly decrypts the real
capture.** `decrypt_frame()` on the message-C capture, confirmed key, and
`session_token=0` passes its own tag check exactly
(`computed_tag == embedded_tag`) and recovers a 250-byte plaintext that is
unambiguously a real Sony NP ticket: it contains the literal ASCII
substrings `"UP9000-BCUS98174_00"` (this title's own content ID) and
`"comradesean"` (very likely the connecting player's PSN online ID), with
consistent Sony-style TLV structure throughout. This is about as strong a
confirmation as this investigation could hope for.

**Message D**: derived a real, cryptographically valid frame via
`encrypt_frame()` keyed by this session's own `client_nonce`
(`0x3b188d6f`), self-verified by round-tripping it back through
`decrypt_frame()`. Content is still a 16-byte all-zero placeholder - message
D's real content was never captured/observed, so this remains a guess, but
the wrapper (magic byte, length, auth_tag) around it is now real and
correct, which is what actually mattered for unblocking live testing.

### Deliverables from this addendum

- `tools/ticket_cipher.py` - bug fixed, decrypt confirmed working against
  real capture, message-D frame derivation added to the demo.
- `tools/ghidra_scripts/EmulateKeySchedule.java`,
  `tools/ghidra_scripts/EmulateCipherFuncs.java` - new Ghidra emulation
  scripts (ground-truth execution, not just disassembly reading).
- `research/ghidra/keysched_trace.txt`, `emu_trace.txt`,
  `acbb90_key_check.txt` - emulation evidence.
- `docs/protocol/0x11_ticket_server_hello.md` - "Encrypted frame layer"
  section rewritten again with the working status, the bug diagnosis, and
  the decrypted ticket confirmation; confidence table and next-steps
  updated accordingly.
- `protos/0x11_ticket_server_ticket_submit.ksy` /
  `_ticket_submit_response.ksy` - updated to CONFIRMED WORKING status.
