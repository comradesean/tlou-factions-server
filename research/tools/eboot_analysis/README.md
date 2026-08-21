# Raw-EBOOT analysis helpers (no Ghidra required)

Small Python tools for analysing the decrypted TLOU EBOOT directly, for when the
Ghidra project is locked/busy or when Ghidra's reference manager misses this
binary's addressing idioms (it frequently does — see below).

Target binary (not vendored; paths are the local RPCS3 game installs). TWO game
versions are in play as of 2026-08-19 - every address in this repo's notes is
1.00 unless stated otherwise, and 1.11 is a RECOMPILE, so addresses do not
translate by a fixed delta:

```
# 01.00  PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6
/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf

# 01.11  PPU-120fb71f7352d62521c639b0e99f960018c10a56
/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf
```

Port addresses between builds by SIGNATURE, then confirm with a property that
holds independently in both binaries (a unique instruction immediate, a
call-site count, an identical displacement pattern). `client/patches/` has two
worked examples in its comment blocks. The `VMA = file offset + 0x10000` mapping
below holds for BOTH builds - verified against each ELF's program headers.

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

## Live memory write-breakpoints (RPCS3) - CONFIRMED WORKING 2026-08-21

For a field that changes value live and a static write-scan (`scan_anchor.py`
+ manual `st{w,b,h} rX,off(rY)` grep) comes up empty, RPCS3 has a real
memory-breakpoint feature (merged March 2025, store-instruction fix April
2025) - first used successfully in this project 2026-08-21 to catch the
`0x12f_room_create.ksy` `room_field_0c` write site after the static scan's
negative result.

**Two requirements, both easy to miss and both silent-failure if skipped:**

1. **A self-compiled RPCS3 with `-DHAS_MEMORY_BREAKPOINTS=ON`.** Not in
   standard downloads. Delete the build dir / `CMakeCache.txt` before
   reconfiguring if you're adding the flag to an existing build tree - CMake
   caches `option()` values, so re-running cmake on top of a stale cache can
   silently keep the flag off (symptom: the breakpoint-type dropdown only
   offers "Execution", no Memory Read/Write).
2. **PPU Decoder must be set to Interpreter** (Settings -> CPU), not the
   default LLVM Recompiler. The recompiler JITs native code with no
   per-store watchpoint checks baked in, so a memory breakpoint set while
   running under it will simply never fire, with no error. ~2-3x slower
   while enabled; expected and fine for a one-shot catch.

**Usage**: Debug window -> Breakpoints panel -> right-click -> Add
Breakpoint (address, type = Memory Write) -> right-click the panel again ->
**Enable BPM** (Break-on-Memory) - the breakpoint sits inert without this
even if added correctly. On hit, RPCS3 dumps full GPR/FPR/VR state plus
`CIA` (the store instruction itself) and `LR` (the caller's return address,
i.e. the call site) - `CIA` -> `objdump --start-address=<CIA-a bit>
--stop-address=<CIA+a bit>` identifies the exact instruction, `LR` -> the
same technique on the caller pins the code path. `fnstart.py <LR>` gets the
containing function's entry point in one step.

## Bonus: the game logs to `sys_tty`, and RPCS3 records it

TLOU writes its own diagnostics (`Post/Get/Send Message %x, size %i`, assert
banners with file+line, `%s joined match`, `Removing User '%s' failed`) through
`sys_tty_write`. Grepping the RPCS3 log for `sys_tty_write():` gives a readable
trace of the game's internal networking decisions — often faster and more
conclusive than static analysis. See
`research/notes/2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md`.
