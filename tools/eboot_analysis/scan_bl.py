"""Find every `bl <target>` in the EBOOT text for the given absolute targets."""
import struct, sys
from eb import rd
TEXT_VA, TEXT_SZ = 0x00010000, 0x11eac68
def scan(targets):
    blob = rd(TEXT_VA, TEXT_SZ); out = []
    for i in range(0, len(blob) - 3, 4):
        w = struct.unpack_from(">I", blob, i)[0]
        if (w >> 26) != 18 or (w & 1) != 1 or (w & 2) != 0:  # I-form, LK=1, AA=0
            continue
        li = w & 0x03fffffc
        if li >= 0x02000000: li -= 0x04000000
        va = TEXT_VA + i
        tgt = (va + li) & 0xffffffff
        if tgt in targets: out.append((va, tgt))
    return out
if __name__ == "__main__":
    for va, tgt in scan({int(a, 16) for a in sys.argv[1:]}):
        print("bl from 0x%08x -> 0x%08x" % (va, tgt))
