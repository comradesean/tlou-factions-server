import struct, sys
from eb import rd
def fstart(va, back=0x1000):
    blob = rd(va - back, back + 4)
    for i in range(back, -1, -4):
        w = struct.unpack_from(">I", blob, i)[0]
        if (w >> 16) in (0xf821, 0x9421):   # stdu/stwu r1,-N(r1)
            return va - back + i
    return None
if __name__ == "__main__":
    for a in sys.argv[1:]:
        v = int(a, 16); print("0x%08x -> fn 0x%08x" % (v, fstart(v)))
