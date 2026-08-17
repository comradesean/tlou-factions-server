#!/usr/bin/env python3
"""Build / decode `userdata/<online_id>.txt.crypt` (and its siblings like
`campaign.config.txt.crypt`) for TLOU Factions (BCUS98174).

WHAT THIS OBJECT IS
-------------------
`t1.final.prod.s3.amazonaws.com/userdata/<online_id>.txt.crypt` rides the game's
generic content-delivery downloader (the same one that fetches
`campaign.config.txt.crypt`, `net1.bin.psarc.crypt`, `build/<user>/...`). It is
NOT the player-progression record - that is `profiles/<id>/profile.21`, a
different 0x5028-byte LZF container. This file is a small line-oriented config.

Full reverse-engineering write-up (every address verified in disassembly):
    research/notes/2026-08-17-userdata-txt-crypt-format.md

CONTAINER  (identical to net1.bin.psarc.crypt / campaign.config.txt.crypt;
            confirmed by decrypting the real campaign2/3 samples with HMAC OK and
            rebuilding them byte-for-byte):

    [ BE u32 plaintext_length ]
    [ 20-byte HMAC-SHA1(HMAC_KEY, padded_body) ]      <- both fields PLAINTEXT
    [ Blowfish-ECB(padded_body) ]  padded_body = plaintext zero-padded to /8

  Same keys as everything else in this title (see tools/psarc_crypt.py):
    Blowfish key  = "(SH[@2>r62%5+QKpy|g6"
    HMAC-SHA1 key = "xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"
  There is NO LZF layer on these `.txt.crypt` files (unlike profile.21). The
  Blowfish body decrypts straight to the config text. The HMAC IS enforced by the
  client's downloader (a bad digest is rejected), so a synthesized file must carry
  a valid one - which encrypt_crypt_file() below always produces.

PLAINTEXT STRUCTURE
-------------------
Whitespace-delimited `key value` pairs, one per line, e.g. (real campaign2):

    queue-server-addr 50.18.47.114
    queue-server-port 7320
    interval 10
    enable 1

The client's loader (EBOOT FUN_00ada3ac) tokenizes on whitespace (space, tab,
CR, LF - `\n` and `\r\n` are both fine) and builds, per pair, a record
{ CRC32(key) , pointer-to-value-string }. Consumers look a key up BY HASH
(EBOOT FUN_00ada358) - the literal key string is never compared, only its hash.

The hash is CRC-32/MPEG-2:  poly 0x04C11DB7, init 0x00000000, no input/output
reflection, no final XOR. (Verified: it reproduces the four campaign-config key
hashes baked into the EBOOT exactly.)

  key                     CRC32/MPEG-2
  queue-server-addr       0xCF0AD2C7
  queue-server-port       0x07DE9D65
  interval                0xE6ACEEFC
  enable                  0x8516DACD

For `userdata/<id>.txt` specifically, the game reads exactly ONE key, whose hash
is 0x8EFC1478 (EBOOT 0x003568e8), CRC-hashes that key's VALUE string, and stores
the result in the online/NetInfo singleton at +0x80. The plaintext KEY string
behind 0x8EFC1478 was not recovered (CRC is not invertible and the string is not
in the EBOOT); every other key/value in the file is ignored by the retail client.
A minimal file the client accepts is therefore *any* valid container - even an
empty body - and the current revival stub's empty 200 response is already valid.

Usage:
    # encode key/value pairs -> .txt.crypt
    python3 userdata_crypt.py build out.txt.crypt  key1=val1 key2=val2 ...
    python3 userdata_crypt.py build out.txt.crypt --from pairs.txt   # a plain text file
    # decode a .txt.crypt -> show plaintext + parsed pairs + each key's CRC
    python3 userdata_crypt.py decode in.txt.crypt
    # CRC32/MPEG-2 of a key name (to match against a hash the EBOOT looks up)
    python3 userdata_crypt.py keyhash queue-server-addr
"""
import os
import sys
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psarc_crypt as pc

# The one key hash the game reads out of userdata/<id>.txt (EBOOT 0x003568e8).
USERDATA_KEY_HASH = 0x8EFC1478


def crc32_mpeg2(s):
    """CRC-32/MPEG-2 (poly 0x04C11DB7, init 0, no reflection, no xorout).

    This is the exact key-hash the client applies to config keys - it matches the
    hashes the EBOOT bakes in for queue-server-addr / interval / enable, and it is
    the table-driven hash at EBOOT FUN_0090aee4 run with seed 0.
    """
    if isinstance(s, str):
        s = s.encode("utf-8")
    h = 0
    for b in s:
        h ^= (b << 24) & 0xFFFFFFFF
        for _ in range(8):
            h = ((h << 1) ^ 0x04C11DB7) if (h & 0x80000000) else (h << 1)
            h &= 0xFFFFFFFF
    return h


def build(pairs, line_ending="\n"):
    """pairs: list of (key, value) or dict -> raw .txt.crypt bytes.

    Values may not contain whitespace (the loader splits on it). Keys and values
    are written verbatim; the client hashes keys itself on load.
    """
    if isinstance(pairs, dict):
        pairs = list(pairs.items())
    lines = []
    for k, v in pairs:
        k = str(k)
        v = str(v)
        if any(c.isspace() for c in k) or any(c.isspace() for c in v):
            raise ValueError(f"key/value may not contain whitespace: {k!r} {v!r}")
        lines.append(f"{k} {v}")
    text = (line_ending.join(lines) + line_ending).encode("utf-8") if lines else b""
    return pc.encrypt_crypt_file(text)


def decode(raw):
    """raw .txt.crypt bytes -> (plaintext_bytes, hmac_ok, [(key, value, crc), ...])."""
    plaintext, ok = pc.decrypt_crypt_file(raw)
    text = plaintext.decode("utf-8", errors="replace")
    pairs = []
    toks = text.split()
    # The loader pairs tokens (key, value). An odd trailing token has no value.
    for i in range(0, len(toks) - 1, 2):
        key, val = toks[i], toks[i + 1]
        pairs.append((key, val, crc32_mpeg2(key)))
    return plaintext, ok, pairs


def _main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    action = sys.argv[1]

    if action == "keyhash":
        for s in sys.argv[2:]:
            print(f"0x{crc32_mpeg2(s):08X}\t{s}")
        return 0

    if action == "build":
        out = sys.argv[2]
        pairs = []
        args = sys.argv[3:]
        if args and args[0] == "--from":
            with open(args[1]) as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    parts = ln.split(None, 1)
                    pairs.append((parts[0], parts[1] if len(parts) > 1 else ""))
        else:
            for a in args:
                k, _, v = a.partition("=")
                pairs.append((k, v))
        blob = build(pairs)
        with open(out, "wb") as f:
            f.write(blob)
        print(f"wrote {len(blob)} bytes to {out} ({len(pairs)} pair(s))")
        # echo the key hashes so the caller can see which one the game reads
        for k, v in pairs:
            hh = crc32_mpeg2(k)
            tag = "  <-- userdata key the game reads" if hh == USERDATA_KEY_HASH else ""
            print(f"  0x{hh:08X}  {k} = {v}{tag}")
        return 0

    if action == "decode":
        raw = open(sys.argv[2], "rb").read()
        plaintext, ok, pairs = decode(raw)
        print(f"HMAC {'OK' if ok else 'MISMATCH'}   plaintext {len(plaintext)} bytes")
        print("--- plaintext ---")
        sys.stdout.write(plaintext.decode("utf-8", errors="replace"))
        if not plaintext.endswith(b"\n"):
            print()
        print("--- parsed pairs (key / value / CRC32-MPEG2 of key) ---")
        for k, v, hh in pairs:
            tag = "  <-- read by userdata consumer (EBOOT 0x3568e8)" if hh == USERDATA_KEY_HASH else ""
            print(f"  0x{hh:08X}  {k} = {v}{tag}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
