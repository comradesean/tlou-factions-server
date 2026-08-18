# Raw-EBOOT analysis helpers (no Ghidra required)

Small Python tools for analysing the decrypted TLOU EBOOT directly, for when the
Ghidra project is locked/busy or when Ghidra's reference manager misses this
binary's addressing idioms (it frequently does — see below).

Target binary (not vendored; path is the user's RPCS3 game install):

```
/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf
```

VMA↔file mapping is uniform for both LOAD segments: **file offset = VMA − 0x10000**.
That means plain objdump works with no ELF parsing at all:

```sh
powerpc64-linux-gnu-objdump -D -b binary -m powerpc:common64 -EB \
  --adjust-vma=0x10000 --start-address=0x355258 --stop-address=0x355340 "$EBOOT"
```

## The two global-addressing idioms in this binary

Everything here exists because TLOU reaches globals two ways, and neither shows
up as a flat address literal:

1. **`r2` → anchor → displacement.** `r2` is a single program-wide TOC pointer,
   **`0x01305870`** (derived from `lwz r30,-31188(r2)` at `0x355264` against
   Ghidra's known anchor `0x012fde9c`; independently confirmed by a live PPU
   register dump in the marathon RPCS3 log). Each compilation unit loads its own
   "small data" anchor from a TOC slot, then reaches globals as
   `lwz rX, off(anchor)`. `scan_anchor.py` resolves this chain binary-wide.
2. **`lis` + `addi`/`ori`** immediate address construction. `scan_imm.py`
   handles this one.

## Tools

| file | purpose |
|---|---|
| `eb.py` | VMA-addressed reader: `rd/u32/u16/s32/cstr/hexd`. Import this from the others. |
| `scan_anchor.py` | `<slot-vma>...` → every instruction reaching those globals via the r2→anchor idiom. The workhorse: answers "who else touches this global". |
| `scan_imm.py` | `<abs-vma>...` → every `lis`+`addi`/`ori` pair that builds those addresses. |
| `scan_bl.py` | `<target>...` → every `bl` call site. |
| `fnstart.py` | `<vma>...` → containing function entry (scans back for `stdu/stwu r1,-N(r1)`). |
| `fnglobals.py` | `<start> <end>` → every global a function range touches, with the C string at the target when there is one. Best way to identify an unnamed function. |

All take VMAs in hex without `0x`. Run them from this directory (they
`import eb`).

## Worked example — finding an assert site from its message

`*** ASSERTION: m_roomSize > 0 / ndlib/net/net-session.cpp:227` in the game's
TTY output:

```sh
# 1. locate the string (searching BOTH segments matters - the pointer tables
#    live at 0x0126xxxx in segment 1, the strings at 0x00exxxxx in segment 0)
python3 -c "from eb import *; import struct; b=rd(0x10000,0x11eac68); i=b.find(b'm_roomSize > 0'); print(hex(0x10000+i))"
# -> 0x00ed7fc0

# 2. find the pointer slot holding it (again: search both segments)
# -> 0x0129759c

# 3. find the code that loads that slot
python3 scan_anchor.py 0129759c
# -> 0x00ad3894 (fn>=0x00ad33d8)  lwz r3, -32700(r30) -> slot 0x0129759c
```

…which pins the assert inside `_opd_FUN_00ad33d8`, cross-checked against the
`li r7,0xe3` (= line 227) two instructions away.

## Bonus: the game logs to `sys_tty`, and RPCS3 records it

TLOU writes its own diagnostics (`Post/Get/Send Message %x, size %i`, assert
banners with file+line, `%s joined match`, `Removing User '%s' failed`) through
`sys_tty_write`. Grepping the RPCS3 log for `sys_tty_write():` gives a readable
trace of the game's internal networking decisions — often faster and more
conclusive than static analysis. See
`research/notes/2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md`.
