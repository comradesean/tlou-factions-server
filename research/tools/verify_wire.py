#!/usr/bin/env python3
"""Verify captured session-manager wire traffic against the Kaitai (.ksy) protos.

Reads the raw packet tap written by server/session_manager.py
(server/logs/wire.jsonl - one JSON record per recv/sendall event, both
directions), reassembles each connection's per-direction byte stream, re-frames
it into individual messages by opcode, parses every message with the COMPILED
ksy parsers, and reports:

  1. COVERAGE      - packet counts per opcode + direction, and parse failures.
  2. UNKNOWN       - opcodes seen on the wire that have no ksy (protocols we
                     have not modelled yet).
  3. INCONSISTENCY - messages the ksy could not parse (length mismatch, a
                     `contents:` constant that did not match, framing desync).
  4. PADDING WATCH - every field we call padding/reserved/inert (pad_*,
                     reserved_*, uninit*, zero_*, member_slot_ec) that was ever
                     NON-ZERO on the wire, with the value and the packet. This
                     is the "is the client sending us something we call
                     nothing?" detector.
  5. FIELD CENSUS  - for every (opcode, field), the set of distinct values seen
                     across the whole capture, flagged CONST or VARIES. This is
                     the analysis engine: it shows exactly which fields are
                     fixed, which vary, and what values an undefined field takes.

The client->server ("in") direction is the one that carries unknowns; server->
client ("out") is authored by us and shown for completeness.

Usage:
    verify_wire.py [wire.jsonl]                 # default server/logs/wire.jsonl
    verify_wire.py --from-humanlog session_manager.log   # bootstrap from the
        # existing human log's inbound hexdumps (in-direction only), so the
        # tool can run on captures taken before the tap existed.
    verify_wire.py ... --opcode 0x140           # restrict to one opcode
    verify_wire.py ... --census-all             # census even CONST fields
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PROTOS = os.path.join(REPO, "protos")
DEFAULT_WIRE = os.path.join(REPO, "server", "logs", "wire.jsonl")

# opcode -> ksy meta id (module stem; class = CamelCase of it). Direction:
# 'in' = client->server, 'out' = server->client, 'both' for 0x134.
OPCODES = {
    0x12d: ("netmatchmaking_client_hello", "in"),
    0x12e: ("netmatchmaking_server_hello", "out"),
    0x12f: ("room_create", "in"),
    0x130: ("room_join", "in"),
    0x131: ("member", "out"),
    0x132: ("room_joined", "out"),
    0x133: ("room_leaving", "in"),
    0x134: ("room_leave", "both"),
    0x135: ("find_match", "in"),
    0x136: ("room_search", "out"),
    0x137: ("kickout", "in"),
    0x138: ("kickedout", "out"),
    0x139: ("room_closed", "out"),
    0x13a: ("member_set_data", "in"),
    0x13b: ("member_updated_data", "out"),
    0x13c: ("promote", "in"),
    0x13d: ("owner_changed", "out"),
    0x13e: ("set_host_flag", "in"),
    0x13f: ("host_flag_updated", "out"),
    0x140: ("set_room_flags", "in"),
    0x141: ("updated_room_flags", "out"),
    0x142: ("host_rank", "in"),
    0x143: ("set_room_data_block", "in"),
    0x144: ("room_data_block_updated", "out"),
    0x145: ("ping", "in"),
    0x146: ("client_hello2", "in"),
}


def _u16(b, o):
    return (b[o] << 8) | b[o + 1]


def _u32(b, o):
    return (b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]


# opcode -> message size in bytes: an int, or a callable(buf, pos) for the
# three variable-length messages. Sizes are the wire totals confirmed from the
# ksy/decompile (see the corresponding protos/*.ksy STATUS blocks).
SIZES = {
    0x12d: 48, 0x12e: 16, 0x12f: 232, 0x130: 88, 0x132: 120, 0x133: 16,
    0x134: 24, 0x135: 36, 0x137: 16, 0x138: 16, 0x139: 16, 0x13a: 80,
    0x13b: 80, 0x13c: 16, 0x13d: 16, 0x13e: 16, 0x13f: 16, 0x140: 16,
    0x141: 16, 0x143: 144, 0x144: 144, 0x145: 4, 0x146: 8,
    0x131: lambda b, p: 160 + 104 * _u16(b, p + 26),   # member roster
    0x136: lambda b, p: 16 + 56 * _u32(b, p + 12),      # room-search list
    0x142: lambda b, p: 16 + 2 * _u16(b, p + 4),        # host-rank u16 list
}

# Field-id prefixes/names we assert carry no meaning. A NON-ZERO value in any of
# these on the wire is the headline finding.
PAD_RE = re.compile(r"^(pad_|reserved_|reserved$|uninit|zero_|leaked_stack|slack$)")
PAD_NAMES = {"member_slot_ec", "pad_count"}  # pad_count is a real length; excluded below


def is_padding(leaf):
    leaf = re.sub(r"\[\d+\]$", "", leaf)
    if leaf == "pad_count":
        return False   # pad_count is a meaningful frame field, not padding
    return bool(PAD_RE.match(leaf)) or leaf in PAD_NAMES


def camel(meta_id):
    return "".join(p[:1].upper() + p[1:] for p in meta_id.split("_"))


def compile_protos():
    """Compile every .ksy to a temp dir and return (tmpdir, {stem: class})."""
    tmp = tempfile.mkdtemp(prefix="verify_wire_ksy_")
    ksy = [os.path.join(PROTOS, f) for f in os.listdir(PROTOS)
           if f.endswith(".ksy") and f != "_template.ksy"]
    ksy += [os.path.join(PROTOS, "common", f)
            for f in os.listdir(os.path.join(PROTOS, "common"))
            if f.endswith(".ksy")]
    r = subprocess.run(
        ["kaitai-struct-compiler", "-t", "python", "--outdir", tmp,
         "-I", PROTOS] + ksy,
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"kaitai compile failed:\n{r.stderr}")
    sys.path.insert(0, tmp)
    classes = {}
    for op, (stem, _dir) in OPCODES.items():
        try:
            mod = __import__(stem)
            classes[op] = getattr(mod, camel(stem))
        except Exception as e:              # noqa: BLE001
            classes[op] = None
            print(f"  [warn] no parser for {stem} ({op:#x}): {e}", file=sys.stderr)
    return tmp, classes


def walk(obj, prefix=""):
    """(path, value) for every leaf field, in wire order (dict insertion)."""
    out = []
    for name, val in getattr(obj, "__dict__", {}).items():
        if name.startswith("_"):
            continue
        path = prefix + name
        if isinstance(val, (bytes, bytearray)):
            out.append((path, bytes(val)))
        elif isinstance(val, (int, str)):
            out.append((path, val))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, (bytes, bytearray)):
                    out.append((f"{path}[{i}]", bytes(item)))
                elif isinstance(item, (int, str)):
                    out.append((f"{path}[{i}]", item))
                else:
                    out.extend(walk(item, f"{path}[{i}]."))
        elif hasattr(val, "__dict__"):
            out.extend(walk(val, path + "."))
    return out


def vhex(v):
    return v.hex() if isinstance(v, (bytes, bytearray)) else (
        f"{v:#x}" if isinstance(v, int) else repr(v))


def nonzero(v):
    if isinstance(v, (bytes, bytearray)):
        return any(v)
    if isinstance(v, int):
        return v != 0
    return bool(v)


# ---- input readers --------------------------------------------------------

def read_wire_jsonl(path):
    recs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def read_humanlog(path):
    """Extract inbound packets from the human session_manager.log.

    Recognises `-- recv client_hello` and `-- further data (N bytes) --`
    markers followed by hexdump rows, and `==== ... connection from` as a new
    connection boundary. Returns wire-style records (dir='in' only)."""
    recs = []
    conn = 0
    collecting = False
    buf = bytearray()
    row = re.compile(r"^\[[^\]]+\]\s+[0-9a-f]{8}\s+((?:[0-9a-f]{2} )+)")
    ts = re.compile(r"^\[([^\]]+)\]")

    def flush():
        nonlocal buf
        if buf:
            recs.append({"t": "", "dir": "in", "conn": conn, "hex": bytes(buf).hex()})
            buf = bytearray()

    with open(path, errors="replace") as f:
        for line in f:
            if "SESSION MANAGER connection from" in line:
                flush(); conn += 1; collecting = False
                continue
            if "-- recv client_hello" in line or "-- further data (" in line:
                flush(); collecting = True
                continue
            m = row.match(line)
            if collecting and m:
                for h in m.group(1).split():
                    buf.append(int(h, 16))
            elif collecting and not m and "  " not in line[:12]:
                flush(); collecting = False
    flush()
    return recs


# ---- framing --------------------------------------------------------------

def frame(stream, direction):
    """Yield (opcode, msg_bytes, ok, note) walking a reassembled byte stream."""
    pos = 0
    n = len(stream)
    while pos + 4 <= n:
        op = _u32(stream, pos)
        if op not in SIZES:
            yield (op, bytes(stream[pos:pos + 16]), False, "UNKNOWN opcode - stop framing this stream")
            return
        sz = SIZES[op]
        size = sz(stream, pos) if callable(sz) else sz
        if size <= 0 or pos + size > n:
            yield (op, bytes(stream[pos:]), False, f"INCOMPLETE/bad size {size} (remaining {n - pos})")
            return
        yield (op, bytes(stream[pos:pos + size]), True, "")
        pos += size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wire", nargs="?", default=DEFAULT_WIRE)
    ap.add_argument("--from-humanlog", metavar="LOG")
    ap.add_argument("--opcode", help="restrict to one opcode, e.g. 0x140")
    ap.add_argument("--census-all", action="store_true",
                    help="show CONST fields in the census too")
    args = ap.parse_args()

    only = int(args.opcode, 0) if args.opcode else None
    recs = (read_humanlog(args.from_humanlog) if args.from_humanlog
            else read_wire_jsonl(args.wire))
    if not recs:
        sys.exit("no packet records found")

    _tmp, classes = compile_protos()

    # reassemble per (conn, dir) streams in file order
    streams = {}
    for r in recs:
        streams.setdefault((r["conn"], r["dir"]), bytearray()).extend(
            bytes.fromhex(r["hex"]))

    coverage = {}          # (dir, op) -> count
    unknown = {}           # op -> [hex samples]
    bad = []               # (dir, op, note, hex)
    padhits = {}           # (op, field) -> {valhex: count}
    census = {}            # (dir, op, field) -> {valhex: [refs]}
    nmsg = 0

    for (conn, direction), stream in sorted(streams.items()):
        idx = 0
        for op, msg, ok, note in frame(stream, direction):
            idx += 1
            if only is not None and op != only:
                continue
            name = OPCODES.get(op, ("?", direction))[0]
            coverage[(direction, op)] = coverage.get((direction, op), 0) + 1
            if not ok:
                if "UNKNOWN" in note:
                    unknown.setdefault(op, []).append(msg.hex())
                else:
                    bad.append((direction, op, note, msg.hex()))
                continue
            nmsg += 1
            cls = classes.get(op)
            if cls is None:
                bad.append((direction, op, "no ksy parser", msg.hex()))
                continue
            try:
                obj = cls.from_bytes(msg)
                # force lazy instances to read (seq is eager; instances aren't)
                fields = walk(obj)
            except Exception as e:              # noqa: BLE001
                bad.append((direction, op, f"PARSE FAIL: {type(e).__name__}: {e}",
                            msg.hex()))
                continue
            ref = f"conn{conn}#{idx}"
            for path, val in fields:
                leaf = path.split(".")[-1]
                key = (direction, op, path)
                census.setdefault(key, {}).setdefault(vhex(val), []).append(ref)
                if is_padding(leaf) and nonzero(val):
                    d = padhits.setdefault((op, path), {})
                    d[vhex(val)] = d.get(vhex(val), 0) + 1

    def opname(op):
        return f"{op:#x} {OPCODES.get(op, ('?',))[0]}"

    print("=" * 72)
    print(f"WIRE VERIFICATION  -  {nmsg} messages framed from "
          f"{len(streams)} stream(s)")
    print("=" * 72)

    print("\n## 1. COVERAGE (packets per direction/opcode)")
    for (d, op), c in sorted(coverage.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        print(f"  {d:<3} {opname(op):<32} {c}")

    print("\n## 2. UNKNOWN OPCODES (no ksy - unseen protocol)")
    if not unknown:
        print("  none")
    for op, samples in sorted(unknown.items()):
        print(f"  {op:#x}: {len(samples)}x  e.g. {samples[0][:48]}")

    print("\n## 3. INCONSISTENCIES (ksy could not parse / framing desync)")
    if not bad:
        print("  none - every framed message parsed clean against its ksy")
    for d, op, note, h in bad[:80]:
        print(f"  {d:<3} {opname(op):<28} {note}\n        {h[:64]}")
    if len(bad) > 80:
        print(f"  ... and {len(bad) - 80} more")

    print("\n## 4. PADDING WATCH  <<< non-zero data in fields we call nothing")
    if not padhits:
        print("  clean - every pad_*/reserved_*/inert field was all-zero on the wire")
    for (op, path), vals in sorted(padhits.items()):
        print(f"  {opname(op)} :: {path}")
        for vh, cnt in sorted(vals.items()):
            print(f"        {vh}   x{cnt}")

    print("\n## 5. FIELD CENSUS (distinct values per field; VARIES = worth a look)")
    last_op = None
    for (d, op, path), vals in sorted(census.items(),
                                      key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        varies = len(vals) > 1
        if not varies and not args.census_all:
            continue
        if (d, op) != last_op:
            print(f"\n  [{d}] {opname(op)}")
            last_op = (d, op)
        tag = f"VARIES({len(vals)})" if varies else "CONST"
        shown = [v if len(v) <= 40 else v[:37] + "..." for v in sorted(vals)[:8]]
        more = "" if len(vals) <= 8 else f" +{len(vals) - 8} more"
        print(f"    {path:<28} {tag:<11} {', '.join(shown)}{more}")
    if not args.census_all:
        print("\n  (only VARYING fields shown; --census-all to include CONST)")


if __name__ == "__main__":
    main()
