#!/usr/bin/env python3
"""Decode (and diff) `profile.21` records - the ~0x5028-byte NetPlayerData
progression file the client PUTs/GETs at
`profiles/<online_id>/profile.21` (see protos/profile_21.ksy /
docs/protocol/profile_21_record.md for the field-level schema).

This is the standalone codec that .ksy's own doc comment calls "an open
want" - it did not exist anywhere in the repo before this tool. Container
framing, decompile-confirmed in `protos/profile_21.ksy`'s doc:

    LZF( [u32 version][u32 enc_len][ Blowfish-ECB(game_data || hmac_pad ||
    hmac_sha1) ][8 trailing bytes] )

`version`/`enc_len` sit in plaintext before the encrypted region.
`enc_len` (always 0x5018 in practice) is the exact byte length of the
Blowfish-ECB region: 0x5000 game_data + 4 hmac_pad + 20 hmac_sha1. LZF is
the standard liblzf byte-oriented format (not implemented anywhere else in
this repo - psarc_crypt.py's container has no compression layer at all).
Blowfish uses the exact same key/primitives as
`server/lib/psarc_crypt.py`'s `.psarc.crypt` codec (`SECRET_KEY`,
`blowfish_init_key`/`blowfish_decrypt`) - confirmed by successfully
round-tripping two real, live-captured profile.21 samples.

USAGE
-----
    # print every named field this project has decompile-confirmed:
    python3 research/tools/profile21_codec.py server/data/served_content/profiles/comradesean/profile.21

    # dump the raw decrypted game_data blob to a file, for ad hoc byte
    # inspection (hexdump, brute-force scans against text_table.py /
    # dc_hash_crack.py, etc):
    python3 research/tools/profile21_codec.py --raw-out /tmp/game_data.bin \\
        server/data/served_content/profiles/comradesean/profile.21

    # diff two captures of the SAME account, e.g. a before/after snapshot
    # around one deliberate in-game change - the technique that
    # live-verified custom_appearance's equipped_item_ids and the
    # emblem_layers persisted format (see docs/protocol/profile_21_record.md):
    python3 research/tools/profile21_codec.py --diff BEFORE.profile21 AFTER.profile21
"""
import argparse
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "lib"))
import psarc_crypt as pc  # noqa: E402


def lzf_decompress(data):
    """Standard liblzf decompression (Marc Lehmann's byte-oriented LZ77
    variant) - not implemented anywhere else in this repo."""
    ip = 0
    out = bytearray()
    n = len(data)
    while ip < n:
        ctrl = data[ip]
        ip += 1
        if ctrl < 32:
            ln = ctrl + 1
            out += data[ip:ip + ln]
            ip += ln
        else:
            ln = ctrl >> 5
            ref = len(out) - ((ctrl & 0x1f) << 8) - 1
            if ln == 7:
                ln += data[ip]
                ip += 1
            ref -= data[ip]
            ip += 1
            ln += 2
            for _ in range(ln):
                out.append(out[ref])
                ref += 1
    return bytes(out)


def decode(raw):
    """raw: the exact bytes of a profile.21 file (as served/stored by
    http_gateway.py - LZF-compressed, Blowfish-encrypted). Returns the
    decrypted game_data+hmac_pad+hmac_sha1 blob (0x5018 bytes), i.e.
    protos/profile_21.ksy's `game_data` field starts at byte 0 of this
    return value."""
    pc.blowfish_init_key(pc.SECRET_KEY)
    container = lzf_decompress(raw)
    version, enc_len = struct.unpack(">II", container[0:8])
    if version != 21:
        raise ValueError(f"unexpected profile version {version} (expected 21)")
    enc_body = container[8:8 + enc_len]
    return pc.blowfish_decrypt(enc_body)


# (field name, payload offset, width in bytes) - the decompile-confirmed
# scalars from protos/profile_21.ksy's `game_data` type. Payload offset =
# P-offset minus 8 (P = the whole profile.21 record; game_data starts at
# P+0x0008). Kept in sync with the .ksy by hand - the .ksy remains the
# source of truth for field semantics/evidence, this list exists only so
# the CLI can print a readable summary.
FIELDS = [
    ("equipped_gesture_id", 0x0300, 4),
    ("member_blob_word", 0x064C, 4),
    ("chosen_char_id_team0", 0x0658, 4),
    ("chosen_char_id_team1", 0x065C, 4),
    ("unmapped_668", 0x0660, 4),
    ("survivor_variant_id", 0x0664, 4),
    ("equipped_item_id_0", 0x0668, 4),
    ("equipped_item_id_1", 0x066C, 4),
    ("equipped_item_id_2", 0x0670, 4),
    ("equipped_item_id_3", 0x0674, 4),
    ("equipped_item_id_4", 0x0678, 4),
    ("equipped_item_id_5", 0x067C, 4),
    ("palette", 0x0680, 4),
    ("tint", 0x0684, 4),
    ("emblem_layer0_shape", 0x07E0, 4),
    ("emblem_layer0_color", 0x07E4, 4),
    ("emblem_layer1_shape", 0x07E8, 4),
    ("emblem_layer1_color", 0x07EC, 4),
    ("emblem_layer2_shape", 0x07F0, 4),
    ("emblem_layer2_color", 0x07F4, 4),
    ("emblem_layer3_shape", 0x07F8, 4),
    ("emblem_layer3_color", 0x07FC, 4),
    ("total_matches", 0x0A14, 4),
    ("total_wins_result3", 0x0A18, 4),
    ("day_counter", 0x1ACC, 4),
    ("day_counter2", 0x1AD0, 4),
    ("faction", 0x1AD4, 4),
    ("pop_highwater_a", 0x1BD8, 4),
    ("clan_state", 0x1BE8, 4),
    ("milestone_latch_1e2c", 0x1E24, 4),
    ("match_ratio_1e3c", 0x1E34, 4),
    ("emblem_location", 0x1E38, 4),
    ("journeys_completed", 0x1E3C, 4),
]


def read_field(plain, off, width):
    return int.from_bytes(plain[off:off + width], "big")


def cmd_dump(args):
    raw = open(args.profile21, "rb").read()
    plain = decode(raw)
    print(f"[+] {args.profile21}: {len(raw)} bytes on disk, "
          f"{len(plain)} bytes decrypted game_data+hmac", file=sys.stderr)
    for name, off, width in FIELDS:
        val = read_field(plain, off, width)
        print(f"P+0x{off+8:04x}  {name:<26} 0x{val:0{width*2}x}")
    if args.raw_out:
        with open(args.raw_out, "wb") as f:
            f.write(plain)
        print(f"[+] wrote decrypted blob to {args.raw_out}", file=sys.stderr)


def cmd_diff(args):
    before = decode(open(args.before, "rb").read())
    after = decode(open(args.after, "rb").read())
    n = min(len(before), len(after))
    print(f"[+] diffing {args.before} -> {args.after} ({n} bytes each)", file=sys.stderr)
    count = 0
    for off in range(0, n - 4 + 1, 4):
        a = int.from_bytes(before[off:off + 4], "big")
        b = int.from_bytes(after[off:off + 4], "big")
        if a != b:
            count += 1
            print(f"P+0x{off+8:04x}  0x{a:08x} -> 0x{b:08x}")
    print(f"[+] {count} differing u32 words", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    dump_ap = sub.add_parser("dump", help="decode and print known fields (default command)")
    dump_ap.add_argument("profile21")
    dump_ap.add_argument("--raw-out", metavar="FILE",
                          help="also write the decrypted game_data+hmac blob to FILE")

    diff_ap = sub.add_parser("diff", help="diff two captures of the same account")
    diff_ap.add_argument("before")
    diff_ap.add_argument("after")

    # allow `profile21_codec.py FILE` as shorthand for `profile21_codec.py dump FILE`
    if len(sys.argv) > 1 and sys.argv[1] not in ("dump", "diff", "-h", "--help"):
        sys.argv.insert(1, "dump")

    args = ap.parse_args()
    if args.cmd == "diff":
        cmd_diff(args)
    else:
        cmd_dump(args)


if __name__ == "__main__":
    main()
