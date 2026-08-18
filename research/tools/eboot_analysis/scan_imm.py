"""Find absolute addresses built with lis+addi / lis+ori pairs (the other half of
this EBOOT's global-addressing idiom, alongside the r2->anchor form)."""
import struct, sys
from eb import rd
TEXT_VA, TEXT_SZ = 0x00010000, 0x11eac68
def scan(targets):
    blob = rd(TEXT_VA, TEXT_SZ); hi = {}; out = []
    for i in range(0, len(blob) - 3, 4):
        w = struct.unpack_from(">I", blob, i)[0]; va = TEXT_VA + i
        op = w >> 26; rD = (w >> 21) & 31; rA = (w >> 16) & 31; imm = w & 0xffff
        if op == 15 and rA == 0:                       # lis rD, imm
            hi[rD] = (imm << 16, va); continue
        if op == 14 and rA in hi and rA == rD:         # addi rD, rD, simm
            s = imm - 0x10000 if imm >= 0x8000 else imm
            val = (hi[rA][0] + s) & 0xffffffff
            if val in targets: out.append((hi[rA][1], va, rD, val))
            del hi[rA]; continue
        if op == 24 and rA in hi and rA == rD:         # ori rD, rD, uimm
            val = (hi[rA][0] | imm) & 0xffffffff
            if val in targets: out.append((hi[rA][1], va, rD, val))
            del hi[rA]; continue
        if op == 14 and rA in hi:                      # addi rD, rA(hi), simm -> different dest
            s = imm - 0x10000 if imm >= 0x8000 else imm
            val = (hi[rA][0] + s) & 0xffffffff
            if val in targets: out.append((hi[rA][1], va, rD, val))
            continue
        if rD in hi and op not in (15,):
            hi.pop(rD, None)
    return out
if __name__ == "__main__":
    for lisva, va, rD, val in scan({int(a, 16) for a in sys.argv[1:]}):
        print("0x%08x (lis @0x%08x) r%d = 0x%08x" % (va, lisva, rD, val))
