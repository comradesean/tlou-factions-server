# Known keys and secret constants

Every cryptographic key, secret constant, or unique fixed value recovered from the
EBOOT so far, in one place. These are compile-time constants baked into the shipped
binary (not per-session/per-account secrets), recovered via a mix of static Ghidra
decompilation and live RPCS3 debugger reads. Each entry lists exactly how it was
confirmed and where it's actually used in this repo's tooling - treat "confirmed live"
entries as fully trustworthy, anything less as still provisional.

## Blowfish key - content-delivery `.crypt` files

```
"(SH[@2>r62%5+QKpy|g6"
```

- **Used for**: decrypting/encrypting `net1.bin.psarc.crypt` and the whole `.crypt`
  content-delivery family (`patch.psarc.crypt`, `campaign.config.txt.crypt`, etc.) -
  the Blowfish-ECB layer wrapping a PSARC archive.
- **Origin**: not unique to this game - reused verbatim from `bucanero/save-decrypters`
  (`naughtydog-decrypter`, a PS3 save-game decryption tool for *The Last of Us*,
  *Uncharted 2*, and *Uncharted 3*), where it's `SECRET_KEY`. Naughty Dog shipped the
  same Blowfish key for both save-game encryption and unrelated content-delivery
  encryption.
- **Confidence**: **confirmed** - not just plausible reuse. Verified by decrypting a
  real `net1.bin.psarc.crypt` and getting an exact SHA256 match against the game's own
  known-good extraction, and by an independently-compiled C reference implementation
  producing byte-identical output.
- **Also needed**: a companion 4168-byte seed table (`BLOWFISH_KEY_DATA`, the
  Blowfish key-schedule base data, not itself secret/unique but required alongside the
  key string above) - stored at `server/lib/blowfish_key_data.py`, extracted from the same
  reference source.
- **Used in code**: `server/lib/psarc_crypt.py`, `SECRET_KEY`.

## HMAC-SHA1 key - content-delivery integrity check

```
"xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"
```

(64 bytes)

- **Used for**: the plaintext `[4-byte length][20-byte HMAC-SHA1]` header prepended to
  every `.crypt` file's Blowfish-encrypted body - the check that decides whether the
  client renames a downloaded file into place or deletes it as corrupt/rejected.
- **Origin**: also reused from `bucanero/save-decrypters`, where it's
  `SHA1_HMAC_KEY` - the *second* secret Naughty Dog carried over from the save-game
  toolkit into unrelated content-delivery code.
- **Confidence**: **confirmed live** - read directly out of a register (`r6`) during
  an RPCS3 debugger session paused at the constructor (`FUN_00ac59a0`) that sets up
  the HMAC computation, byte-for-byte matching the save-game reference string.
  Separately confirmed functionally: a repack built with this key produced a real,
  passing HMAC that the live game client accepted (`connect ok` in RPCS3's own log,
  first time ever for a repacked file).
- **Used in code**: `server/lib/psarc_crypt.py`, `HMAC_KEY`.

## Ticket-server frame cipher key - post-handshake control-channel encryption

```
78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89
```

(16 bytes, EBOOT virtual address `0x00ed7a50`)

- **Used for**: keying a custom ARX (add-rotate-xor) stream cipher that encrypts every
  message after the initial hello/hello-response on the `ticket-server` control
  channel (port 7320) and its sibling services (`heartbeat-server`,
  `leaderboard-server`, `facebook-server`, `single-player-server`) - specifically the
  NP-ticket-submission message and its response.
- **Origin**: unique to this cipher/subsystem - not reused from the save-game toolkit
  like the two keys above. Sits in EBOOT rodata directly adjacent to an unrelated
  string literal (`"recv() failed (e..."`), no separator - a real compile-time
  constant table, not a string.
- **Confidence**: **confirmed live, twice** - both the resolved address (`r3 =
  0xed7a50` at two separate call sites into the key-mixing function,
  `FUN_00db5ec0`) and the 16 key bytes themselves were read directly out of live
  RPCS3 process memory during a real NetInit run, and matched byte-for-byte against
  the value independently resolved via static Ghidra TOC-chain analysis. **However**:
  a decrypt attempt using this key against a real captured ciphertext has not yet
  succeeded (auth-tag verification still fails) - the key is confirmed correct, but
  the cipher reimplementation still has an unresolved bug elsewhere (see
  `docs/protocol/0x11_ticket_server_hello.md` for the live investigation).
- **Used in code**: `server/lib/ticket_cipher.py`, `candidate_key` (name reflects that the
  *key* is confirmed even though the surrounding decrypt code is not yet working end
  to end - not a statement of doubt about the key itself).

## Ticket-server key, reused verbatim for the Session Manager / NetMatchmaking connection

The same 16 bytes above (`78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89`) are
also present at a **second** rodata address, `0x00ed8030`, resolved via the same
TOC-chain method (base `0x012feca0`, offset `-0x7f44`). This second copy is the
key `g_pSessionManager::Init()` (`FUN_00ad71a0`, the function that opens a new
raw TCP connection to port 7314 during NetInit, right after the ticket-server
handshake - see `docs/protocol/session_manager_and_matchmaking.md`) passes into
the exact same `FUN_00db5ec0` key-schedule function ticket-server uses, keyed by
a per-connection seed read from that connection's own `NetMatchmakingServerHello`
response (offset 8) rather than anything from ticket-server.

- **Confidence**: **confirmed** (static TOC-chain resolution, same mechanical
  method already used for the first copy) that these are the identical 16
  bytes at a second address - not yet independently confirmed live via a
  debugger read the way the first copy was, since this connection has never
  successfully completed its handshake (see the doc above for why: the
  connection to port 7314 currently fails before any real
  `NetMatchmakingServerHello` has ever been received to test the cipher
  against).
- **Practical implication**: `server/lib/ticket_cipher.py`'s already-solved and
  verified key-schedule/round functions should apply unchanged to this second
  protocol - no new cipher reversal expected to be needed, only new framing
  work (whether post-handshake `NetMatchmaking*` frames use the same 20-byte
  encrypt-then-MAC header as ticket-server's messages C/D was not confirmed
  this pass).

## Not yet found

- The exact key-mixing formula inside `FUN_00db5ec0` that combines the static key
  above with the per-connection `session_token`/`client_nonce` counter into the
  cipher's initial state - the high-level mechanism is decompiled (see
  `docs/protocol/0x11_ticket_server_hello.md`), but a working, verified
  reimplementation isn't done yet.
- Anything about how `sceNpManagerGetTicket`'s own 248-byte NP ticket is internally
  structured beyond RPCN's own (already-known, already-working) serialization in
  RPCN's `src/server/client/ticket.rs` - not investigated as EBOOT-side secret
  material since RPCN already round-trips it successfully.

## Notes for future entries

When adding a newly-recovered key here: state the exact bytes, what it's for, where it
came from (reused vs. unique to this subsystem), and the confidence level using the
same two-tier standard as above - *confirmed* (independently verified via a working
decrypt/round-trip, or an exact match against known-good output) vs. *confirmed live*
(read directly from process memory during a live debugger session, the strongest form
of evidence used in this project) vs. anything weaker should be flagged as
provisional/candidate, not listed as settled.
