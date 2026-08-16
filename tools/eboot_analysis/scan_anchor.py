"""Find every instruction that reaches a given absolute global through the PS3
r2->anchor->displacement idiom used all over this EBOOT:
    lwz rN, -D(r2)        ; rN = *(r2 - D)  == a per-compilation-unit "small data" anchor
    lwz/stw/addi rX, off(rN)   ; touches (anchor + off)
Linear scan; register anchor map is reset on `blr`/`stdu r1` boundaries."""
import struct, sys
from eb import rd, u32, SEGS

R2 = 0x01305870
TEXT_VA, TEXT_SZ = 0x00010000, 0x11eac68
DFORM = {32:'lwz',34:'lbz',36:'stw',38:'stb',40:'lhz',42:'lha',44:'sth',14:'addi',46:'lmw',47:'stmw'}
DSFORM = {58:'ld/lwa', 62:'std/stdu'}

def scan(targets):
    blob = rd(TEXT_VA, TEXT_SZ)
    hits = []
    anchors = {}
    func_start = TEXT_VA
    for i in range(0, len(blob) - 3, 4):
        w = struct.unpack_from(">I", blob, i)[0]
        va = TEXT_VA + i
        op = w >> 26
        rD = (w >> 21) & 31
        rA = (w >> 16) & 31
        imm = w & 0xffff
        if imm >= 0x8000: imm -= 0x10000
        if w == 0x4E800020:            # blr -> function boundary
            anchors = {}; func_start = va + 4; continue
        if (w & 0xffff0000) == 0xf8210000 or (w & 0xffff0000) == 0x94210000:  # stdu/stwu r1,-N(r1)
            anchors = {}; func_start = va; continue
        if op == 32 and rA == 2:       # lwz rD, -D(r2) : anchor load
            try: anchors[rD] = u32(R2 + imm)
            except Exception: pass
            continue
        if rA in anchors and (op in DFORM or op in DSFORM):
            off = imm & ~3 if op in DSFORM else imm
            slot = (anchors[rA] + off) & 0xffffffff
            if slot in targets:
                hits.append((va, func_start, DFORM.get(op, DSFORM.get(op)), rD, rA, off, slot))
        if op in (32, 58) and rD == rA and rA in anchors:
            del anchors[rA]            # anchor register overwritten
    return hits

if __name__ == "__main__":
    targets = {int(a, 16) for a in sys.argv[1:]}
    for va, fs, mn, rD, rA, off, slot in scan(targets):
        print("0x%08x (fn>=0x%08x)  %-8s r%d, %d(r%d)  -> slot 0x%08x" % (va, fs, mn, rD, off, rA, slot))
