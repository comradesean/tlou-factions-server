#!/usr/bin/env python3
"""Minimal PSARC reader/writer for Naughty Dog's PS3-era .psarc.crypt files.

Format (confirmed empirically against net1.bin.psarc.crypt):
  [24-byte wrapper header, meaning not yet fully understood] +
  [standard PSARC archive, Blowfish-ECB encrypted as a whole]

Blowfish: same algorithm/key as bucanero/save-decrypters' naughtydog-decrypter
(PS3 save-game tool) - SECRET_KEY = "(SH[@2>r62%5+QKpy|g6", standard Blowfish
Feistel core with big-endian 32-bit word swaps per 8-byte block (ECB, no IV).

PSARC container (from 0x0L/rs-utils psarc.py, Rocksmith - same container
format family as Naughty Dog's PS3 titles):
  32-byte BE header: magic(4)='PSAR', version(4), compression(4)='zlib',
    toc_size(4), entry_size(4)=30, num_entries(4), block_size(4), flags(4)
  TOC: num_entries x 30-byte entries: md5(16), zindex(4), length(5), offset(5)
    (5-byte big-endian length/offset fields)
  zlength table: one u16 BE per (total_uncompressed_size / block_size) block,
    shared across all entries, immediately after the TOC entries
  Entry 0 is always the manifest (newline-separated list of entry filepaths,
    in order - entry N's name is the Nth line, 0-indexed after the manifest
    itself)
  Data section: concatenated per-entry compressed blocks (zlib), zlength[i]
    of 0 means the corresponding block is stored uncompressed (block_size
    bytes, or the remainder for the last block of a file)
"""
import hashlib
import struct
import sys
import zlib

SECRET_KEY = "(SH[@2>r62%5+QKpy|g6"
WRAPPER_HEADER_SIZE = 24

# ---- Blowfish (ported faithfully from bucanero/save-decrypters common/blowfish.c) ----

_key_buffer = None
KEYSIZE_WORDS = 1042  # 0x1048 bytes / 4


def _load_blowfish_key_data():
    from blowfish_key_data import BLOWFISH_KEY_DATA
    return BLOWFISH_KEY_DATA


def _native_read_u32_array(data_bytes, count=None):
    # Matches a raw `(uint32_t*)` pointer cast on this (little-endian x86-64) host.
    n = count if count is not None else len(data_bytes) // 4
    return list(struct.unpack(f"<{n}I", data_bytes[:n * 4]))


def _native_write_u32_array(words):
    return struct.pack(f"<{len(words)}I", *words)


def _apply_keycode(keybuf, keydata_native, keycode):
    kc = keycode.encode("ascii")
    klen = len(kc)
    for i in range(18):
        b0 = kc[(i * 4 + 0) % klen]
        b1 = kc[(i * 4 + 1) % klen]
        b2 = kc[(i * 4 + 2) % klen]
        b3 = kc[(i * 4 + 3) % klen]
        value = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        keybuf[i] = keydata_native[0x400 + i] ^ value

    scratch = [0, 0]
    for i in range(0, 0x412, 2):
        _crypt_64bit_up(keybuf, scratch)
        keybuf[i] = scratch[0]
        keybuf[i + 1] = scratch[1]


def _crypt_64bit_up(keybuf, ptr):
    x, y = ptr[0], ptr[1]
    for i in range(16):
        z = (keybuf[i] ^ x) & 0xFFFFFFFF
        x = keybuf[0x012 + ((z >> 24) & 0xff)]
        x = (keybuf[0x112 + ((z >> 16) & 0xff)] + x) & 0xFFFFFFFF
        x = keybuf[0x212 + ((z >> 8) & 0xff)] ^ x
        x = (keybuf[0x312 + (z & 0xff)] + x) & 0xFFFFFFFF
        x = y ^ x
        y = z
    ptr[1] = x ^ keybuf[0x10]
    ptr[0] = y ^ keybuf[0x11]


def _crypt_64bit_down(keybuf, ptr):
    x, y = ptr[0], ptr[1]
    for i in range(17, 1, -1):
        z = (keybuf[i] ^ x) & 0xFFFFFFFF
        x = keybuf[0x012 + ((z >> 24) & 0xff)]
        x = (keybuf[0x112 + ((z >> 16) & 0xff)] + x) & 0xFFFFFFFF
        x = keybuf[0x212 + ((z >> 8) & 0xff)] ^ x
        x = (keybuf[0x312 + (z & 0xff)] + x) & 0xFFFFFFFF
        x = y ^ x
        y = z
    ptr[1] = x ^ keybuf[1]
    ptr[0] = y ^ keybuf[0]


def blowfish_init_key(key):
    global _key_buffer
    raw = _load_blowfish_key_data()
    keydata_native = _native_read_u32_array(raw, KEYSIZE_WORDS)
    keybuf = [0] * KEYSIZE_WORDS
    keybuf[18:18 + 1024] = keydata_native[0:1024]  # memcpy(key_buffer + 0x48, ..., 0x1000)
    _apply_keycode(keybuf, keydata_native, key)
    _key_buffer = keybuf


def _es32(v):
    return struct.unpack(">I", struct.pack("<I", v & 0xFFFFFFFF))[0]


def blowfish_crypt_buffer(data, encrypt):
    data = bytearray(data)
    n_bytes = (len(data) // 8) * 8
    words = _native_read_u32_array(bytes(data[:n_bytes]), n_bytes // 4)
    for i in range(0, len(words), 2):
        buf = [_es32(words[i]), _es32(words[i + 1])]
        if encrypt:
            _crypt_64bit_up(_key_buffer, buf)
        else:
            _crypt_64bit_down(_key_buffer, buf)
        words[i] = _es32(buf[0])
        words[i + 1] = _es32(buf[1])
    data[:n_bytes] = _native_write_u32_array(words)
    return bytes(data)


def blowfish_decrypt(data):
    return blowfish_crypt_buffer(data, encrypt=False)


def blowfish_encrypt(data):
    return blowfish_crypt_buffer(data, encrypt=True)


# ---- PSARC container ----

class PsarcEntry:
    def __init__(self, md5, zindex, length, offset, name=None):
        self.md5 = md5
        self.zindex = zindex
        self.length = length
        self.offset = offset
        self.name = name


def _read_uint40(b, off):
    return int.from_bytes(b[off:off + 5], "big")


def _write_uint40(v):
    return v.to_bytes(5, "big")


def parse_psarc(data):
    if data[:4] != b"PSAR":
        raise ValueError(f"not a PSARC (magic={data[:4]!r})")
    magic, version, compression, toc_size, entry_size, num_entries, block_size, flags = \
        struct.unpack(">4sIIIIIII", data[:32])
    assert entry_size == 30, f"unexpected entry_size {entry_size}"

    entries = []
    pos = 32
    for _ in range(num_entries):
        md5 = data[pos:pos + 16]
        zindex = struct.unpack(">I", data[pos + 16:pos + 20])[0]
        length = _read_uint40(data, pos + 20)
        offset = _read_uint40(data, pos + 25)
        entries.append(PsarcEntry(md5, zindex, length, offset))
        pos += 30

    zlen_table_bytes = toc_size - pos
    num_blocks = zlen_table_bytes // 2
    zlengths = list(struct.unpack(f">{num_blocks}H", data[pos:pos + zlen_table_bytes]))
    pos = toc_size

    def read_entry_data(entry):
        # zlength[i] == 0 means "stored, full block_size" (compression didn't help,
        # encoder recorded len(raw) % block_size which is 0 for a full block).
        # zlength[i] == raw_block_size (the block's actual uncompressed size, which
        # is block_size for all but possibly the last block of an entry) means
        # "stored, this exact size" - covers small entries (e.g. the manifest)
        # whose raw size is below block_size, where the mod trick doesn't hit 0.
        # Any other (necessarily smaller) zlength means "compressed, that many
        # zlib bytes". Compression is chosen only when it strictly shrinks the
        # block, so these three cases are unambiguous.
        out = bytearray()
        zi = entry.zindex
        remaining = entry.length
        off = entry.offset
        while remaining > 0:
            raw_block_size = min(block_size, remaining)
            zlen = zlengths[zi]
            if zlen == 0 or zlen == raw_block_size:
                out += data[off:off + raw_block_size]
                off += raw_block_size
            else:
                out += zlib.decompress(data[off:off + zlen])
                off += zlen
            remaining -= raw_block_size
            zi += 1
        return bytes(out)

    manifest = read_entry_data(entries[0]).decode("utf-8", errors="replace")
    names = manifest.split("\n")
    for i, name in enumerate(names):
        if i + 1 < len(entries):
            entries[i + 1].name = name

    return {
        "version": version, "compression": compression, "block_size": block_size,
        "flags": flags, "entries": entries, "zlengths": zlengths,
        "read_entry_data": read_entry_data,
    }


def build_psarc(entries, version=0x00010004, compression=b"zlib", block_size=65536, flags=0):
    """Build a fresh PSARC body from (name, content_bytes) entries (manifest excluded -
    it's synthesized here as entry 0). Mirrors parse_psarc's block/offset/zindex layout
    exactly (verified against the real net1.bin.psarc.crypt's TOC), so a round-trip
    through parse_psarc(build_psarc(x)) reproduces x exactly. Confirmed empirically that
    entry_size TOC md5 is md5(entry NAME), not md5(content) - the manifest entry (name is
    conceptually absent) uses an all-zero md5.
    """
    names = [name for name, _ in entries]
    manifest = "\n".join(names).encode("utf-8")
    all_items = [(None, manifest)] + list(entries)

    zlengths = []
    data_chunks = []
    toc_rows = []  # [md5, zindex, length, offset(filled in below)]
    zindex = 0
    for name, content in all_items:
        md5 = b"\x00" * 16 if name is None else hashlib.md5(name.encode("utf-8")).digest()
        entry_zindex = zindex
        pos = 0
        remaining = len(content)
        while remaining > 0:
            raw_block_size = min(block_size, remaining)
            block = content[pos:pos + raw_block_size]
            compressed = zlib.compress(block, 9)
            if len(compressed) < raw_block_size:
                data_chunks.append(compressed)
                zlengths.append(len(compressed))
            else:
                data_chunks.append(block)
                zlengths.append(raw_block_size % block_size)
            pos += raw_block_size
            remaining -= raw_block_size
            zindex += 1
        toc_rows.append([md5, entry_zindex, len(content), None])

    num_entries = len(toc_rows)
    entry_size = 30
    header_size = 32
    toc_size = header_size + num_entries * entry_size + len(zlengths) * 2

    offset = toc_size
    chunk_offsets = []
    for c in data_chunks:
        chunk_offsets.append(offset)
        offset += len(c)
    for row in toc_rows:
        row[3] = chunk_offsets[row[1]]

    comp_int = struct.unpack(">I", compression)[0] if isinstance(compression, (bytes, bytearray)) else compression
    header = struct.pack(">4sIIIIIII", b"PSAR", version, comp_int, toc_size, entry_size, num_entries, block_size, flags)

    toc_bytes = bytearray()
    for md5, zi, length, off in toc_rows:
        toc_bytes += md5
        toc_bytes += struct.pack(">I", zi)
        toc_bytes += _write_uint40(length)
        toc_bytes += _write_uint40(off)

    zlen_bytes = struct.pack(f">{len(zlengths)}H", *zlengths)

    return header + bytes(toc_bytes) + zlen_bytes + b"".join(data_chunks)


def build_crypt_file(wrapper_header, entries, **psarc_kwargs):
    """Full repack: PSARC body + prepended (preserved, unmodified) wrapper header,
    Blowfish-encrypted as a whole. wrapper_header's meaning is unconfirmed (not a
    hash of the body under MD5/SHA1/SHA256, not a size field) so it is carried
    through byte-for-byte from the original file rather than regenerated.
    """
    body = build_psarc(entries, **psarc_kwargs)
    plain = wrapper_header + body
    pad = (-len(plain)) % 8
    if pad:
        plain += b"\x00" * pad
    blowfish_init_key(SECRET_KEY)
    return blowfish_encrypt(plain)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["decrypt", "list", "extract", "repack"])
    ap.add_argument("infile")
    ap.add_argument("outfile", nargs="?")
    ap.add_argument("--entry", help="entry name to extract (with --action extract)")
    ap.add_argument("--replace", nargs=2, metavar=("FIND", "REPLACE"),
                     help="with --action repack: byte string to find/replace in the "
                          "target entry's content before repacking (same-length only)")
    ap.add_argument("--target-entry", default=None,
                     help="with --action repack: which entry to modify (default: the "
                          "sole non-manifest entry)")
    args = ap.parse_args()

    raw = open(args.infile, "rb").read()
    blowfish_init_key(SECRET_KEY)
    plain = blowfish_decrypt(raw)

    if args.action == "decrypt":
        open(args.outfile, "wb").write(plain)
        print(f"wrote {len(plain)} bytes to {args.outfile}")
    else:
        wrapper_header = plain[:WRAPPER_HEADER_SIZE]
        psarc = parse_psarc(plain[WRAPPER_HEADER_SIZE:])
        if args.action == "list":
            for e in psarc["entries"][1:]:
                print(f"{e.name}\t{e.length} bytes")
        elif args.action == "extract":
            for e in psarc["entries"][1:]:
                if e.name == args.entry:
                    content = psarc["read_entry_data"](e)
                    open(args.outfile, "wb").write(content)
                    print(f"wrote {len(content)} bytes to {args.outfile}")
                    break
            else:
                print(f"entry {args.entry!r} not found")
        elif args.action == "repack":
            target_name = args.target_entry
            entries_out = []
            for e in psarc["entries"][1:]:
                content = psarc["read_entry_data"](e)
                if target_name is None or e.name == target_name:
                    if args.replace:
                        find, repl = args.replace[0].encode(), args.replace[1].encode()
                        if len(find) != len(repl):
                            raise SystemExit("--replace strings must be the same length "
                                              "(archive/container layout is not being resized)")
                        n = content.count(find)
                        content = content.replace(find, repl)
                        print(f"{e.name}: replaced {n} occurrence(s) of {find!r} with {repl!r}")
                entries_out.append((e.name, content))
            new_crypt = build_crypt_file(wrapper_header, entries_out,
                                          version=psarc["version"], compression=psarc["compression"],
                                          block_size=psarc["block_size"], flags=psarc["flags"])
            open(args.outfile, "wb").write(new_crypt)
            print(f"wrote {len(new_crypt)} bytes to {args.outfile}")
