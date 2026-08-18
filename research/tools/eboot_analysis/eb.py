import sys, struct
EB="/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf"
SEGS=[(0x000000,0x00010000,0x11eac68),(0x11f0000,0x01200000,0x1231d0)]
_f=open(EB,'rb')
def off(vma):
    for fo,va,sz in SEGS:
        if va<=vma<va+sz: return fo+(vma-va)
    raise ValueError("vma 0x%x not mapped"%vma)
def rd(vma,n):
    _f.seek(off(vma)); return _f.read(n)
def u32(vma): return struct.unpack(">I",rd(vma,4))[0]
def u16(vma): return struct.unpack(">H",rd(vma,2))[0]
def s32(vma): return struct.unpack(">i",rd(vma,4))[0]
def cstr(vma,n=64):
    b=rd(vma,n); i=b.find(b"\0"); return b[:i if i>=0 else n].decode('latin1')
def hexd(vma,n):
    b=rd(vma,n)
    for i in range(0,len(b),16):
        print("%08x: %s  %s"%(vma+i," ".join("%02x"%c for c in b[i:i+16]),
            "".join(chr(c) if 32<=c<127 else '.' for c in b[i:i+16])))
