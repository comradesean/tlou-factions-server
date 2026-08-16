"""Resolve every r2->anchor->displacement global a function touches, and print
the target address plus, when it looks like one, the C string there."""
import struct, sys
from eb import rd, u32
R2 = 0x01305870
def printable(b): return 32 <= b < 127
def strat(va, n=80):
    try: b = rd(va, n)
    except Exception: return None
    i = 0
    while i < n and printable(b[i]): i += 1
    if i < 4: return None
    if i < n and b[i] != 0: return None
    return b[:i].decode('latin1')
def run(start, end):
    blob = rd(start, end - start); anchors = {}
    for i in range(0, len(blob), 4):
        w = struct.unpack_from(">I", blob, i)[0]; va = start + i
        op = w >> 26; rD = (w >> 21) & 31; rA = (w >> 16) & 31
        imm = w & 0xffff
        if imm >= 0x8000: imm -= 0x10000
        if op == 32 and rA == 2:
            anchors[rD] = u32(R2 + imm); continue
        if rA in anchors and op in (32, 34, 36, 38, 40, 44, 14, 58, 62):
            off = (imm & ~3) if op in (58, 62) else imm
            slot = (anchors[rA] + off) & 0xffffffff
            try: val = u32(slot)
            except Exception: val = None
            s = strat(val) if val else None
            extra = ""
            if val is not None:
                extra = " -> 0x%08x" % val
                if s: extra += "  %r" % s
            print("0x%08x  op=%2d r%-2d %6d(r%d)  slot=0x%08x%s" % (va, op, rD, off, rA, slot, extra))
if __name__ == "__main__":
    run(int(sys.argv[1], 16), int(sys.argv[2], 16))
