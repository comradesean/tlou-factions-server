#!/usr/bin/env python3
"""Walk a DC00 bundle's top-level directory and dump its named tables.

WHAT THIS SOLVES
----------------
`docs/protocol/dc_table.md` solved the DC00 *container* (header, payload,
relocation bitmap) but left the payload's interior as "a hash-keyed directory,
partially understood", with the record read as
`{value_ptr, key_hash, type_hash}` and the *contents* behind `value_ptr`
declared unresolved. Both of those are now fixed:

* The record is **`{key_hash, type_hash, value_ptr}`** - the previous reading
  was shifted one word, which is why `*net-money-info*`'s payload looked like
  a 193-entry table that never parsed as money (it is the *preceding* record's
  table, `*net-emblem-layers-frame*`).
* The **directory is self-describing**: bundle header word `0x14` is the entry
  count and word `0x18` is the file offset of the first record. `net.bin` has
  392 records, and **every one of the 392 `key_hash` values cracks against the
  disc's own `.dci` compiler-symbol corpus** (`dc_hash_crack.py`) - so the
  whole table of contents is recoverable by name, with no guessing.
* `value_ptr` points at a struct whose members are frequently
  **`{count: u4, array_ptr: u4, tag: u4}`** length-prefixed arrays, back to
  back (one DC global can hold several).

Element *stride* is NOT recoverable from the bundle - `tag` does not encode
it (`*net-taunts*` and `*net-stats*` share `tag=0x2a8027cf` at strides 12 and
8 respectively), so `--array` takes an explicit stride. Strides established
by decoding, each cross-checked against ground truth:

    global                        stride  shape
    *net-emblem-layers-{base,        12   {name_hash, name_ptr, sub_ptr}
      frame,parts}* (one array)
    *net-emblem-colors*              16   4 x f32 (RGBA, alpha always 1.0)
    *net-stats*                       8   {stat_id_hash, text_string_id}
    *net-taunts*                     12   {taunt_id_hash, text_string_id, ?}
    *net-money-info*                  4   u32, a cumulative threshold ladder
    *unlock-list*                    28   {unlock_id, category, item_hash,
                                           0, sub_index, ptr, flags}

NOTE ON THE PER-ENTRY HASHES: the *directory* `key_hash`/`type_hash` are
`crc32_mpeg2` of DC source symbol names (`dc_hash_crack.py`). The hashes
*inside* a table (e.g. `*net-emblem-layers-frame*`'s per-shape `name_hash`,
`*net-taunts*`' per-gesture id) are a DIFFERENT, still-unidentified 32-bit
hash - see `research/notes/2026-08-20-dc-directory-and-catalogs.md` §6 for
what has been ruled in (poly 0x04C11DB7, MSB-first, forward byte order,
confirmed by exact single-byte-delta tests) and ruled out. You do not need
that hash to use this tool: the tables carry the plaintext name or the text
StringId next to the hash, so a value seen on the wire or in a profile is
resolved by *searching the table*, not by recomputing it.

USAGE
-----
    DISC=".../PS3_GAME/USRDIR/build/main"

    # extract dc1/net.bin out of the disc's plain bin.psarc:
    python3 research/tools/dc_dir.py --extract-from "$DISC/bin.psarc" \\
        --entry dc1/net.bin -o /tmp/net.bin

    # list the whole directory, names resolved:
    python3 research/tools/dc_dir.py /tmp/net.bin --psarc "$DISC/bin.psarc" \\
        --wordlist "$DISC/paks.txt" --wordlist "$DISC/pak23.txt" --list

    # show one global's members (counts, array pointers, element types):
    python3 research/tools/dc_dir.py /tmp/net.bin -p "$DISC/bin.psarc" \\
        --show '*net-emblem-colors*'

    # dump an array: --array <file-offset> <count> <stride> [--as fmt]
    #   fmt: u32 (default) | f32 | hash+str | hash+hash | hash+strid
    python3 research/tools/dc_dir.py /tmp/net.bin \\
        --array 0x2be58 193 12 --as hash+str        # emblem shape catalog
    python3 research/tools/dc_dir.py /tmp/net.bin \\
        --array 0x15e94 64 16 --as f32              # emblem colour swatches
    python3 research/tools/dc_dir.py /tmp/net.bin \\
        --array 0x9c18 40 8 --as hash+strid \\
        --text1 "$DISC/text1.psarc"                 # *net-stats*, named
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "lib"))
import psarc_crypt as pc  # noqa: E402
from userdata_crypt import crc32_mpeg2  # noqa: E402

DC00_MAGIC = b"DC00"


def extract(psarc_path, entry_name, out_path):
    with open(psarc_path, "rb") as f:
        psarc = pc.parse_psarc(f.read())
    for e in psarc["entries"][1:]:
        if e.name == entry_name:
            with open(out_path, "wb") as g:
                g.write(psarc["read_entry_data"](e))
            return True
    return False


class Bundle:
    """One decompressed DC00 bundle (e.g. dc1/net.bin, or served net1.bin)."""

    def __init__(self, data):
        if data[:4] != DC00_MAGIC:
            raise ValueError("not a DC00 bundle (bad magic)")
        self.d = data
        self.count = self.u4(0x14)
        self.dir_off = self.u4(0x18)

    def u4(self, o):
        return struct.unpack_from(">I", self.d, o)[0]

    def f4(self, o):
        return struct.unpack_from(">f", self.d, o)[0]

    def cstr(self, o, limit=128):
        if not 0 < o < len(self.d):
            return None
        e = self.d.find(b"\x00", o)
        if e < 0 or not 0 < e - o <= limit:
            return None
        s = self.d[o:e]
        if not all(32 <= c < 127 for c in s):
            return None
        return s.decode("ascii")

    def records(self):
        """Yield (file_offset, key_hash, type_hash, value_ptr) per directory entry."""
        for i in range(self.count):
            o = self.dir_off + 12 * i
            yield o, self.u4(o), self.u4(o + 4), self.u4(o + 8)

    def members(self, value_ptr, n=8):
        """Read a global's struct as candidate {count, array_ptr, tag} triples.

        Value structs are packed back to back in the payload, so the walk is
        stopped at the next global's `value_ptr` - without that bound the
        listing silently runs on into the following global's members.
        """
        stop = min((v for _, _, _, v in self.records() if v > value_ptr),
                   default=len(self.d))
        out = []
        for i in range(n):
            o = value_ptr + 12 * i
            if o + 12 > len(self.d) or o >= stop:
                break
            cnt, ptr, ty = self.u4(o), self.u4(o + 4), self.u4(o + 8)
            plausible = 0 < cnt < 100000 and 0 < ptr < len(self.d)
            out.append((o, cnt, ptr, ty, plausible))
        return out


def build_names(psarc_paths, wordlists):
    import dc_hash_crack as dh
    corpus = dh.build_corpus(psarc_paths, wordlists)
    return {crc32_mpeg2(t): t.decode("utf-8", "replace") for t in corpus}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", nargs="?", help="path to a decompressed DC00 bundle")
    ap.add_argument("--extract-from", help="plain .psarc to pull an entry out of")
    ap.add_argument("--entry", default="dc1/net.bin", help="entry name for --extract-from")
    ap.add_argument("-o", "--out", help="output path for --extract-from")
    ap.add_argument("-p", "--psarc", action="append", default=[],
                    help="plain .psarc whose dc1/*.dci symbols name the hashes")
    ap.add_argument("-w", "--wordlist", action="append", default=[])
    ap.add_argument("--list", action="store_true", help="dump the whole directory")
    ap.add_argument("--show", help="show one global's members, by symbol name or 0xHASH")
    ap.add_argument("--array", nargs=3, metavar=("OFF", "COUNT", "STRIDE"))
    ap.add_argument("--as", dest="fmt", default="u32",
                    choices=["u32", "f32", "hash+str", "hash+hash", "hash+strid"])
    ap.add_argument("--text1", help="text1.psarc, for --as hash+strid")
    ap.add_argument("--text-entry", default="2.networking")
    args = ap.parse_args()

    if args.extract_from:
        if not args.out:
            ap.error("--extract-from needs -o")
        ok = extract(args.extract_from, args.entry, args.out)
        print(f"[{'+' if ok else '-'}] {args.entry} -> {args.out}")
        return 0 if ok else 1

    if not args.bundle:
        ap.error("need a bundle path (or --extract-from)")
    with open(args.bundle, "rb") as f:
        b = Bundle(f.read())

    names = build_names(args.psarc, args.wordlist) if (args.psarc or args.wordlist) else {}

    if args.list:
        print(f"[+] {b.count} directory entries at 0x{b.dir_off:x}")
        named = 0
        for o, k, t, v in b.records():
            nm = names.get(k, "")
            named += bool(nm)
            print(f"0x{o:06x}  key={k:08x} type={t:08x} value=0x{v:06x}  {nm}")
        if names:
            print(f"[+] named {named}/{b.count}")

    if args.show:
        want = int(args.show, 16) if args.show.startswith("0x") else None
        for o, k, t, v in b.records():
            if (want is not None and k == want) or (want is None and names.get(k) == args.show):
                print(f"{names.get(k, '')}  key={k:08x} type={t:08x} value=0x{v:x}")
                for mo, cnt, ptr, ty, ok in b.members(v):
                    mark = "" if ok else "   (implausible - past the struct's end?)"
                    print(f"  +0x{mo - v:02x}  count={cnt:<8} array=0x{ptr:06x} "
                          f"tag={ty:08x}{mark}")
                break
        else:
            print("not found")

    if args.array:
        off = int(args.array[0], 0)
        cnt = int(args.array[1], 0)
        stride = int(args.array[2], 0)
        tbl = None
        if args.fmt == "hash+strid":
            if not args.text1:
                ap.error("--as hash+strid needs --text1")
            import text_table as tt
            tbl = tt.TextTable(tt.load_psarc_entry(args.text1, args.text_entry))
        for i in range(cnt):
            o = off + stride * i
            words = [b.u4(o + 4 * j) for j in range(stride // 4)]
            if args.fmt == "u32":
                body = " ".join(f"{w:08x}" for w in words)
            elif args.fmt == "f32":
                body = " ".join(f"{b.f4(o + 4 * j):.4f}" for j in range(stride // 4))
            elif args.fmt == "hash+str":
                body = f"{words[0]:08x}  {b.cstr(words[1])!r}"
            elif args.fmt == "hash+hash":
                body = " ".join(f"{w:08x}" for w in words)
            else:  # hash+strid
                body = f"{words[0]:08x}  {tbl.get(words[1]) or ''}"
            print(f"{i:4d} 0x{o:06x}  {body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
