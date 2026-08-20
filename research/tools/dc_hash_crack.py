#!/usr/bin/env python3
"""Recover DC00 hash strings by reversing `crc32_mpeg2` against the source
symbol names shipped in plaintext inside the retail PS3 disc's `.dci` files.

BACKGROUND - read this if you're new to the DC00 hash problem
---------------------------------------------------------------
`net1.bin`/`net10.bin` (server/data/served_content/*.psarc.crypt, see
docs/protocol/dc_table.md) are hash-keyed binary tables: every entry is
identified by a `key_hash`/`type_hash` pair (both 4-byte `crc32_mpeg2` values,
see server/lib/userdata_crypt.py's crc32_mpeg2()), and NOTHING in those files
tells you what string produced a given hash. Guessing candidate strings by
hand is unreliable. This script instead pulls the REAL candidate strings
straight from the game.

The retail PS3 disc (mounted for RPCS3 - see research/tools/eboot_analysis/
README.md for the standard local install paths this project uses) ships an
UNENCRYPTED `.psarc` at `PS3_GAME/USRDIR/build/main/bin.psarc`. Inside it,
every `dc1/<name>.bin` compiled data file has a sibling `dc1/<name>.dci` -  a
small PLAINTEXT file (not DC00/binary) that looks like:

    (net (283615)
      (import player-overlay-defines anim-player-funcs ...)
      (export *net-global-levels* *net-maps* net-limb ...)
      )

That's the DC compiler's own import/export symbol list for the module - i.e.
a ready-made dictionary of every plausible hash-input string, in the game's
own naming convention (`*star*`-wrapped for global variables, bare for
type/struct names). This script:

  1. Reads `bin.psarc` directly (no manual unpack needed - plain PSARC, NOT
     the Blowfish+HMAC `.crypt` wrapper `served_content/` files use).
  2. Tokenizes every `dc1/*.dci` entry into a corpus of candidate strings.
  3. Hashes each candidate (both as-is and with `*stars*` stripped) with
     `crc32_mpeg2` and reports which ones match your target hash(es).

`build/main/` also ships several PLAIN TEXT manifests alongside the .psarc
archives - `paks.txt` (one pak/table name per line), `pak23.txt`
(`<field> <value>` pairs), `banks.txt`, `*-audio-precache.txt`. These are a
second, independent source of candidate strings, worth checking alongside
the .dci corpus: `crc32_mpeg2("hud") == 0x1ad3445f` (the `stat_line` table's
hash) was found this way - `"hud"` is a literal line in `paks.txt`, not a
`.dci` symbol. Pass plain-text files with `--wordlist`/`-w` (repeatable),
tokenized on whitespace.

USAGE
-----
    # crack one or more hashes against the disc's own bin.psarc + manifests:
    python3 research/tools/dc_hash_crack.py \\
        -p "/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main/bin.psarc" \\
        -w "/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main/paks.txt" \\
        -w "/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main/pak23.txt" \\
        0xC85E199D 0xced9d25f 0x1ad3445f

    # dump the whole candidate corpus instead of cracking anything (for
    # manual grep, or to point another script at a text file):
    python3 research/tools/dc_hash_crack.py --dump-corpus corpus.txt \\
        -p "/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main/bin.psarc"

Repeat `-p`/`-w` to pool more than one archive/wordlist (e.g. also try
pak23.psarc, actor34.psarc, banks.txt) into one corpus. Only bin.psarc is
known to carry .dci files as of the 2026-08-19 investigation that wrote this
script, but the disc has other .psarc archives (see
`PS3_GAME/USRDIR/build/main/*.psarc`) worth checking if bin.psarc's corpus
ever comes up empty for a hash you're chasing.

WHY THIS OFTEN COMES UP EMPTY FOR A GIVEN HASH: the disc under the path
above is the 01.00 base build. Any DC hash introduced by a later patch
(01.11, etc.) has no reason to appear in the 01.00 disc's .dci files at all
- see docs/protocol/dc_table.md's `pReportArray` case (01.11-only, confirmed
NOT in this corpus). A matching later-build install (if one becomes
available - see research/tools/eboot_analysis/README.md for both known
local EBOOT install paths) would need its own build/main content checked
the same way; as of this writing, the 01.11 install directory found locally
holds no build/main .psarc files, only a promo/DLC .edat.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "lib"))
import psarc_crypt as pc  # noqa: E402
from userdata_crypt import crc32_mpeg2  # noqa: E402

TOKEN_RE = re.compile(rb"[A-Za-z0-9_*.\-]+")


def _add_tokens(corpus, content):
    for m in TOKEN_RE.finditer(content):
        tok = m.group()
        corpus.add(tok)
        stripped = tok.strip(b"*")
        if stripped != tok:
            corpus.add(stripped)


def build_corpus(psarc_paths, wordlist_paths=()):
    """Return the set of unique byte-string tokens found in every .dci entry
    across the given .psarc files (plain PSARC, not .crypt), plus every
    whitespace-separated token in the given plain-text wordlist files."""
    corpus = set()
    for path in psarc_paths:
        with open(path, "rb") as f:
            data = f.read()
        psarc = pc.parse_psarc(data)
        dci_entries = [e for e in psarc["entries"][1:] if e.name and e.name.endswith(".dci")]
        for e in dci_entries:
            content = psarc["read_entry_data"](e)
            _add_tokens(corpus, content)
    for path in wordlist_paths:
        with open(path, "rb") as f:
            _add_tokens(corpus, f.read())
    return corpus


def crack(corpus, target_hashes):
    """target_hashes: set of ints. Returns list of (token_str, hash_hex)."""
    found = []
    for tok in corpus:
        h = crc32_mpeg2(tok)
        if h in target_hashes:
            found.append((tok.decode("utf-8", "replace"), f"0x{h:08x}"))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--psarc", action="append", default=[],
                     help="path to a plain (unencrypted) .psarc from the retail disc, "
                          "e.g. bin.psarc - repeat -p to pool multiple archives")
    ap.add_argument("-w", "--wordlist", action="append", default=[],
                     help="path to a plain-text manifest (e.g. paks.txt, pak23.txt) "
                          "to tokenize on whitespace - repeat -w to pool multiple")
    ap.add_argument("hashes", nargs="*", help="target hash(es) to crack, e.g. 0xC85E199D")
    ap.add_argument("--dump-corpus", metavar="FILE",
                     help="write every candidate token to FILE (one per line) instead "
                          "of / in addition to cracking")
    args = ap.parse_args()
    if not args.psarc and not args.wordlist:
        ap.error("pass at least one -p/--psarc or -w/--wordlist source")

    corpus = build_corpus(args.psarc, args.wordlist)
    print(f"[+] {len(corpus)} unique candidate tokens from {len(args.psarc)} archive(s) "
          f"+ {len(args.wordlist)} wordlist(s)", file=sys.stderr)

    if args.dump_corpus:
        with open(args.dump_corpus, "w") as f:
            for tok in sorted(corpus, key=lambda b: b.lower()):
                f.write(tok.decode("utf-8", "replace") + "\n")
        print(f"[+] wrote corpus to {args.dump_corpus}", file=sys.stderr)

    if not args.hashes:
        return

    targets = {int(h, 16) for h in args.hashes}
    found = crack(corpus, targets)
    matched = {int(h, 16) for _, h in found}
    for tok, h in sorted(found, key=lambda x: x[1]):
        print(f"{h}\t{tok}")
    for h in targets - matched:
        print(f"0x{h:08x}\tNO MATCH", file=sys.stderr)


if __name__ == "__main__":
    main()
