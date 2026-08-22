# `userdata/<id>.txt.crypt` and `campaign.config.txt.crypt` - line-config `.crypt` format

`server/lib/userdata_crypt.py`

status: **confirmed** (container, key hashes, and `campaign.config.txt.crypt`'s
consumer all solved and live-verified)
confidence: **high** - container confirmed by decrypting real retail samples
with HMAC OK and rebuilding them byte-for-byte; the consumer trace is both
decompile-verified and live-verified end to end (real telemetry sent and
received after deploying a server-authored replacement).

## What this covers

Both files ride the game's generic content-delivery downloader (the same one
that fetches `net1.bin.psarc.crypt`, `patch.psarc.crypt`, `build/<user>/...`)
and share one small, simple container - NOT the LZF-wrapped `profile.21`
player-progression format, and NOT the DC00 binary table format
(`dc_table.md`). This is plain line-oriented text.

## Container

```
[ BE u32 plaintext_length ]
[ 20-byte HMAC-SHA1(HMAC_KEY, padded_body) ]      <- both fields PLAINTEXT
[ Blowfish-ECB(padded_body) ]  padded_body = plaintext zero-padded to /8
```

Same keys as everything else in this title (`docs/known-keys.md`):

    Blowfish key  = "(SH[@2>r62%5+QKpy|g6"
    HMAC-SHA1 key = "xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"

Both keys are **static and title-wide**, not per-session or digest-pinned by
the caller - a server-authored file can be fully valid, not just a passthrough
of a captured original. No LZF layer. The HMAC IS enforced by the client's
downloader (a bad digest is rejected), so a synthesized file must carry a
valid one - `userdata_crypt.py build`/`encrypt_crypt_file()` always produce
one.

## Plaintext structure

Whitespace-delimited `key value` pairs, one per line:

    queue-server-addr 50.18.47.114
    queue-server-port 7320
    interval 10
    enable 1

The client's loader (EBOOT `FUN_00ada3ac`) tokenizes on whitespace and builds,
per pair, a record `{ CRC32(key), pointer-to-value-string }`. Consumers look a
key up BY HASH (`FUN_00ada358`) - the literal key string is never compared,
only its hash. Hash is CRC-32/MPEG-2 (poly `0x04C11DB7`, init `0`, no
reflection, no final XOR):

    key                     CRC32/MPEG-2
    queue-server-addr       0xCF0AD2C7
    queue-server-port       0x07DE9D65
    interval                0xE6ACEEFC
    enable                  0x8516DACD
    enable-dlc-facebook       0xE6B56490   (01.11 only - see below)
    enable-dlc-facebook-text  0xA1719B90   (01.11 only - see below)

## `userdata/<online_id>.txt.crypt`

The game reads exactly ONE key, hash `0x8EFC1478` (EBOOT `0x003568e8`),
CRC-hashes that key's VALUE string, and stores the result in the online/NetInfo
singleton at `+0x80`. The plaintext KEY string behind `0x8EFC1478` was not
recovered (CRC is not invertible, and the string isn't in the EBOOT); every
other key/value in the file is ignored by the retail client. A minimal file
the client accepts is therefore *any* valid container, even an empty body -
this project's revival stub's empty `200` response is already correct for
this file.

## `campaign.config.txt.crypt`

Unlike `userdata`, ALL FOUR keys above are actually consumed - by
`FUN_007f149c` (01.00 VMA `0x007f149c`), the campaign save-manager singleton's
own constructor (`gamelib/save/saveworker.cpp`). This is the SAME object that
later sends `single-player-server`'s `stat %s task-%x %s %s\n` telemetry line
(`protos/0x11_stat_line.ksy`) - this download is a hard prerequisite for that
line ever sending, not optional config.

**Sequence** (confirmed both by decompile and by live 2026-08-21/22 RPCS3
breakpoint sessions - full trace in
`research/notes/2026-08-21-stat-line-config-writer-trace.md`):

1. `sceNpManagerGetNpId()` must succeed, or the constructor skips this whole
   block permanently - it only runs once, at lazy construction, no retry.
2. A live HTTP GET+decrypt of `campaign.config.txt.crypt` (default URL
   `http://t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt`)
   must succeed. `enable` is read for a `"1"`-prefixed toggle check; `interval`
   becomes the notify throttle's modulus N; `queue-server-addr`/
   `queue-server-port` become the `{ip,port}` pair `single-player-server`'s
   hello handshake (`FUN_00acc424`, the same shared connect every 0x11 sibling
   uses) actually connects to.

The real retail values (decrypted 2026-08-17 from a genuine `campaign2`/`3`
sample) point at Naughty Dog's own long-dead `50.18.47.114:7320`.

## `enable-dlc-facebook` / `enable-dlc-facebook-text` (01.11 only)

The real `campaign3.config.txt.crypt` sample carries two more pairs beyond
the four above (`enable-dlc-facebook 1`, `enable-dlc-facebook-text 0`).
Traced 2026-08-22 (`research/notes/2026-08-22-dlc-facebook-config-keys-trace.md`):
**both keys are read, but only by the 01.11 EBOOT** - neither hash appears
anywhere in the 01.00 image, confirming these are a later-client-version
addition, consistent with `campaign3` (vs. plain `campaign`/`campaign2`)
being requested only by a later client.

In 01.11 both lookups sit immediately after `enable`'s, inside the same
relocated save-manager constructor (01.11 VMA `0x00815b2c`, the 01.11 copy of
`FUN_007f149c`), against the **same parsed config object** the other four
keys use. Each is read with the identical `"1"`-prefixed boolean-toggle
pattern already used for `enable` itself (`value != NULL && value[0] == '1'`)
- confirming the `enable-` naming. Unlike the other four keys, though, each
one's result is stored into a **separate standalone global byte** reached via
this compilation unit's own literal-pool anchor (`0x012b5658` for
`enable-dlc-facebook`, `0x012b565c` for `enable-dlc-facebook-text`) rather
than a field of the save-manager/config object itself.

An exhaustive whole-image scan (two independent methods - see the note) found
**no reader anywhere in the 01.11 EBOOT** for either resulting global byte.
The write side is fully decompile-traced; no consumer of either flag was
found. This is a dead end of the same shape as `NetInfo+0x80` /
`userdata`'s `0x8EFC1478` key below - documented, not chased further absent
new evidence (e.g. a vtable dispatch this linear static scan can't resolve).

## This server's deployment

Since `http_gateway.py`'s upstream S3 bucket for this path is dead, it was
falling back to an empty `200 OK` that can't decrypt - confirmed live: a
breakpoint on `FUN_007f1acc` (the telemetry sender) during a real autosave
read the save-manager singleton's fields as all-zero (throttle
modulus/ip/port never populated) at the exact moment the config download had
just failed.

Fix: build and serve a real replacement, same content shape as retail, just
pointed at this server:

```sh
python3 server/lib/userdata_crypt.py build \
    server/data/served_content/campaign.config.txt.crypt \
    queue-server-addr=<this server's LAN address> queue-server-port=7320 \
    interval=10 enable=1
```

`http_gateway.py` always prefers a local file over its upstream-fetch
fallback, so once this file exists it's served automatically - no code
change needed beyond having the file present.

**LIVE-VERIFIED END-TO-END, 2026-08-21/22**: deployed, and confirmed working
on the next fresh RPCS3 boot - seven real `task-%x` telemetry sends across
one campaign session, all successfully reaching and being handled by
`ticket_server.py`'s `handle_single_player`. One of those sends was directly
correlated against the GATE 2 throttle counter tracked live across three
consecutive breakpoint hits (counter 8 -> 9 -> 0, sending only at 0),
confirming the deployed `interval=10` value is actually driving the throttle
in practice, not just present in the file.

## What's still open

- The exact numeric-to-behavior mapping for `interval`->modulus and
  `enable`->toggle is confirmed WORKING functionally (the notify path fires
  repeatedly at the expected 1-in-10 cadence), but the individual
  `FUN_00ada358` key-lookup call sites inside `FUN_007f149c` were never
  re-verified instruction-by-instruction against which specific key feeds
  which specific field - functional confirmation stands in for that
  instruction-level check.
- `userdata/<online_id>.txt.crypt`'s one consumed key (hash `0x8EFC1478`) is
  still an unrecovered string - low priority, since the current empty-body
  stub is already a valid, correct response for it.
- `enable-dlc-facebook`/`enable-dlc-facebook-text` (01.11 only - see above):
  both keys' consumer is traced and both write a global flag byte, but no
  reader of either flag was found anywhere in the 01.11 EBOOT by static scan.
  Same low-priority dead-end status as the `0x8EFC1478` item above.
