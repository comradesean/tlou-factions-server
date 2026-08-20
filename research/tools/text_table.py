#!/usr/bin/env python3
"""Resolve StringId text lookups against `text1.psarc`'s locale/category
tables - the format documented in `docs/protocol/text_table.md` /
`protos/common/text_table.ksy`.

BACKGROUND
----------
`PS3_GAME/USRDIR/build/main/text1.psarc` (retail disc, unencrypted PSARC -
see `research/tools/eboot_analysis/README.md` for the standard local mount
path) contains per-locale text bundles named `<locale_num>.<category>`
(category one of `common`, `networking`, `subtitles`, `subtitles-temp`;
locale `2`/`7` are both English). Each entry is a binary lookup table:

    [u32 count]
    [count x record(u32 key, u32 string_offset)]   <- sorted ascending on key
    [string blob: count NUL-terminated strings, back to back]

`string_offset` is relative to the start of the string blob (`4 +
count*8`), NOT the file start. The hash algorithm behind `key` is NOT
identified (not `crc32_mpeg2` of the display string or of anything in the
DC00 symbol corpus `dc_hash_crack.py` uses - see `docs/protocol/
text_table.md` for what was tried). `key` is used here as an opaque id,
exactly the way this project's docs already cite these StringIds (e.g.
`0x40b5d875`, `0x5c494554` in `protos/profile_21.ksy`).

USAGE
-----
    # resolve one or more keys against one category entry:
    python3 research/tools/text_table.py \\
        -p "/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main/text1.psarc" \\
        -e 2.networking \\
        0x40b5d875 0x5c494554

    # reverse lookup: find the key for a known display string:
    python3 research/tools/text_table.py -p text1.psarc -e 2.networking \\
        --find-string "Norwegian Hat"

    # list every entry name in text1.psarc:
    python3 research/tools/text_table.py -p text1.psarc --list-entries

    # dump every (key, string) pair in one table:
    python3 research/tools/text_table.py -p text1.psarc -e 2.common --dump
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "lib"))
import psarc_crypt as pc  # noqa: E402


class TextTable:
    """Parses one text1.psarc entry's bytes into a key->string lookup table."""

    def __init__(self, data):
        self.data = data
        self.count = struct.unpack(">I", data[0:4])[0]
        self.records = []
        for i in range(self.count):
            off = 4 + i * 8
            key, string_offset = struct.unpack(">II", data[off:off + 8])
            self.records.append((key, string_offset))
        self.blob_start = 4 + self.count * 8
        self._by_key = {k: o for k, o in self.records}

    def get(self, key):
        """key: int. Returns the decoded string, or None if key isn't in the table."""
        off = self._by_key.get(key)
        if off is None:
            return None
        start = self.blob_start + off
        end = self.data.index(b"\x00", start)
        return self.data[start:end].decode("utf-8", "replace")

    def find_key(self, s):
        """Reverse lookup: byte-exact string -> its key, or None if not present
        as a record's own string (a substring match of another string's blob
        bytes would not have its own record and returns None)."""
        target = s.encode("utf-8")
        idx = self.data.find(target)
        if idx < 0:
            return None
        rel = idx - self.blob_start
        for key, off in self.records:
            if off == rel:
                return key
        return None

    def items(self):
        for key, off in self.records:
            start = self.blob_start + off
            end = self.data.index(b"\x00", start)
            yield key, self.data[start:end].decode("utf-8", "replace")


def load_psarc_entry(psarc_path, entry_name):
    with open(psarc_path, "rb") as f:
        data = f.read()
    psarc = pc.parse_psarc(data)
    for e in psarc["entries"]:
        if e.name == entry_name:
            return psarc["read_entry_data"](e)
    raise KeyError(f"no entry named {entry_name!r} in {psarc_path}")


def list_entries(psarc_path):
    with open(psarc_path, "rb") as f:
        data = f.read()
    psarc = pc.parse_psarc(data)
    return [e.name for e in psarc["entries"] if e.name]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--psarc", required=True, help="path to text1.psarc")
    ap.add_argument("-e", "--entry", help="entry name, e.g. 2.networking")
    ap.add_argument("--list-entries", action="store_true",
                     help="list every entry name in the psarc and exit")
    ap.add_argument("--find-string", help="reverse lookup: print the key for this exact string")
    ap.add_argument("--dump", action="store_true", help="print every (key, string) pair")
    ap.add_argument("keys", nargs="*", help="key(s) to resolve, e.g. 0x40b5d875")
    args = ap.parse_args()

    if args.list_entries:
        for name in list_entries(args.psarc):
            print(name)
        return

    if not args.entry:
        ap.error("-e/--entry is required unless --list-entries")

    data = load_psarc_entry(args.psarc, args.entry)
    table = TextTable(data)
    print(f"[+] {args.entry}: {table.count} entries, blob_start=0x{table.blob_start:x}",
          file=sys.stderr)

    if args.find_string is not None:
        key = table.find_key(args.find_string)
        if key is None:
            print(f"{args.find_string!r}\tNOT FOUND", file=sys.stderr)
        else:
            print(f"0x{key:08x}\t{args.find_string!r}")

    if args.dump:
        for key, s in table.items():
            print(f"0x{key:08x}\t{s}")
        return

    for k in args.keys:
        key = int(k, 16)
        s = table.get(key)
        if s is None:
            print(f"0x{key:08x}\tNO MATCH", file=sys.stderr)
        else:
            print(f"0x{key:08x}\t{s}")


if __name__ == "__main__":
    main()
