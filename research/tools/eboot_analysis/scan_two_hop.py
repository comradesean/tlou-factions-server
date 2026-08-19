"""Two-hop scan, anchor-value-exact: find every place that (1) loads the
anchor register from r2 such that the resolved anchor VALUE equals
ANCHOR_VAL, (2) then loads a pointer from anchor+disp1, (3) then reads/writes
an offset within [lo,hi) of that pointer - before a redefinition or a bl/bctrl
clobbers the volatile register holding it. Filtering on the resolved anchor
VALUE (not just the raw displacement) avoids cross-compilation-unit collisions
where an unrelated function's anchor happens to sit at the same displacement
from r2 but resolves to a different physical global."""
import struct, sys
from eb import rd, u32
TEXT_VA, TEXT_SZ = 0x00010000, 0x11eac68
R2 = 0x01305870
DFORM = {32:'lwz',34:'lbz',36:'stw',38:'stb',40:'lhz',42:'lha',44:'sth'}
DSFORM = {58:'ld/lwa', 62:'std/stdu'}
VOLATILE = set([0] + list(range(3, 13)))

def scan(anchor_val, disp1, lo, hi):
    blob = rd(TEXT_VA, TEXT_SZ)
    hits = []
    anchors = {}   # reg -> resolved anchor VALUE (only kept if == anchor_val)
    objptr = {}
    func_start = TEXT_VA
    for i in range(0, len(blob) - 3, 4):
        w = struct.unpack_from(">I", blob, i)[0]
        va = TEXT_VA + i
        op = w >> 26
        rD = (w >> 21) & 31
        rA = (w >> 16) & 31
        imm = w & 0xffff
        if imm >= 0x8000: imm -= 0x10000

        if w == 0x4E800020:
            anchors = {}; objptr = {}; func_start = va + 4; continue
        if (w & 0xffff0000) in (0xf8210000, 0x94210000):
            anchors = {}; objptr = {}; func_start = va; continue
        if op == 19 and (w & 0x7fe) == 0x210:
            for r in VOLATILE:
                anchors.pop(r, None); objptr.pop(r, None)
            continue
        if op == 18:
            if w & 1:
                for r in VOLATILE:
                    anchors.pop(r, None); objptr.pop(r, None)
            continue

        is_load_or_store = op in DFORM or op in DSFORM

        if is_load_or_store and rA in objptr and lo <= imm < hi:
            hits.append((va, func_start, DFORM.get(op, DSFORM.get(op)), rD, rA, imm, objptr[rA]))

        if op == 32 and rA == 2:
            try:
                val = u32((R2 + imm) & 0xffffffff)
            except Exception:
                val = None
            if val == anchor_val:
                anchors[rD] = val
            else:
                anchors.pop(rD, None)
            objptr.pop(rD, None)
            continue
        if is_load_or_store and rA in anchors and imm == disp1:
            objptr[rD] = va
            continue
        if is_load_or_store or op == 14:
            if op not in (36, 38, 44, 62):
                anchors.pop(rD, None)
                objptr.pop(rD, None)
    return hits

if __name__ == "__main__":
    anchor_val = int(sys.argv[1], 16)
    disp1 = int(sys.argv[2], 16)
    lo = int(sys.argv[3], 16)
    hi = int(sys.argv[4], 16)
    for va, fs, mn, rD, rA, off, load_va in scan(anchor_val, disp1, lo, hi):
        print("0x%08x (fn>=0x%08x)  %-8s r%d, %d(r%d)  [objptr loaded @ 0x%08x]" %
              (va, fs, mn, rD, off, rA, load_va))
