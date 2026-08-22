# `enable-dlc-facebook` / `enable-dlc-facebook-text`: 01.11-only consumer trace

Follow-up to `2026-08-17-userdata-txt-crypt-format.md`, which decoded a real
`campaign3.config.txt.crypt` sample and found two extra key/value pairs beyond
the four already-traced `campaign.config.txt.crypt` keys, but never located
their EBOOT consumer:

    key                        CRC32/MPEG-2      observed value (campaign3 sample)
    enable-dlc-facebook        0xE6B56490        1
    enable-dlc-facebook-text   0xA1719B90        0

Bottom line up front: **both keys ARE consumed, but only in the 01.11 EBOOT,
not 01.00.** Both are read in the exact same function as the four
already-known keys - the 01.11 relocation of `FUN_007f149c` (the campaign
save-manager constructor) - via the same local key-lookup call, against the
same parsed config object. Both are treated as `"1"`-prefixed boolean toggles
(matching the `enable-` naming), and each gates one standalone global BSS
byte. No other code anywhere in the 01.11 image reads either byte back - so
while the *write* side is fully traced and proven, no active consumer of
either resulting flag was found. Neither key appears anywhere in the 01.00
EBOOT.

## Method

Same technique as the original four-hash discovery (§3 of the 2026-08-17
note): search the whole EBOOT for the literal 32-bit key hash as a PPC
immediate-load sequence. That note's own worked example turned out to use an
idiom the project's existing `research/tools/eboot_analysis/scan_imm.py`
does not cover - `li rD,0 ; oris rD,rD,HI ; ori rD,rD,LO` - rather than
`lis rD,HI ; ori rD,rD,LO`. `scan_imm.py` only implements the latter, which is
why it originally found only `queue-server-port` (the one key whose HI/LO
split happens to compile to a real `lis`) and missed the other three.

A corrected scanner (`/tmp/.../scratchpad/scan_imm2.py`, this session, not yet
promoted to `research/tools/`) tracks `lis`/`li`/`oris`/`ori` accumulation
into any destination register and checks the final value after every step.
Validated against the four already-known hashes in 01.00 before trusting it
on the unknowns - it recovers all four (including the three `scan_imm.py`
missed):

    0x000804bc r4 = 0xcf0ad2c7   (queue-server-addr)
    0x000804d0 r4 = 0x07de9d65   (queue-server-port)
    0x007f171c r4 = 0xe6aceefc   (interval)
    0x007f1754 r4 = 0x8516dacd   (enable)
    0x007f1788 r4 = 0xcf0ad2c7   (queue-server-addr, 2nd site)
    0x007f179c r4 = 0x07de9d65   (queue-server-port, 2nd site)

A raw 32-bit word scan (catching the value as an inline data-pool constant,
not just a register-build sequence) was also run over both LOAD segments of
each binary, as a second independent check. Neither method found anything for
the two unknown hashes anywhere in **01.00**:

```
$ python3 scan_imm2-style scan  0xE6B56490 0xA1719B90   # against 01.00 EBOOT
(no output - not found)
$ raw word scan for 0xE6B56490 / 0xA1719B90 across both 01.00 LOAD segments
(no output - not found)
```

01.00 EBOOT used: `/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf` (the binary `research/tools/eboot_analysis/eb.py` already points at).

## 01.11: found, in the save-manager's relocated constructor

Same two scans against the 01.11 EBOOT
(`/mnt/f/rpcs3_testing/TLOU-FACTIONS 1.11/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf`,
LOAD segments `[fileoff 0, VA 0x10000, size 0x121ef68]` and
`[fileoff 0x1220000, VA 0x1230000, filesz 0x1270d0]`, TOC/`r2` resolved from
the ELF entry point's `.opd` descriptor at `0x12d5c08` → `r2 = 0x01338de0`)
found both, back to back, right after the already-known `enable` key:

    0x00815e20-0x00815e2c   li r4,0x6490 / oris r4,r4,0xe6b5   -> r4 = 0xe6b56490
    0x00815e5c-0x00815e60   oris r4,r4,0xa171 / ori r4,r4,0x9b90 -> r4 = 0xa1719b90

Both sites sit inside one function, `0x00815b2c`-`0x00815f28` (`stdu
r1,-512(r1)` at entry, matching `blr` epilogue at `0x815f28`) - the 01.11
relocation of `FUN_007f149c`. Full disassembly of the relevant block
(`powerpc64-linux-gnu-objdump -D -b binary -m powerpc:common64 -EB
--adjust-vma=0x815c00`, dumped from a raw copy of the mapped bytes):

```
815d94: addi    r29,r25,5084        ; r29 = this+0x13DC (parsed config sub-object)
...
815d9c: clrldi  r31,r29,32          ; r31 = r29  (same object, two register aliases)
...
815db0: bl      0xb08140            ; parse/load the campaign-config file into it
                                     ;   (analog of FUN_00ada3ac/FUN_00ada7b8)
815db8: li      r4,0
815dbc: oris    r4,r4,0xe6ac
815dc0: mr      r3,r31              ; obj = this+0x13DC
815dc4: ori     r4,r4,0xeefc        ; r4 = 0xe6aceefc (interval)
815dc8: bl      0xb080ec            ; lookup(obj, hash)  -- analog of FUN_00ada358
...                                  ; (atoi the value, store into this+0x13EC)
815df0: li      r4,0
815df4: mr      r3,r31
815df8: oris    r4,r4,0x8516
815dfc: ori     r4,r4,0xdacd        ; r4 = 0x8516dacd (enable)
815e00: bl      0xb080ec
815e04: nop
815e08: cmpwi   cr7,r3,0            ; value == NULL?
815e0c: beq     cr7,0x815e1c
815e10: lbz     r0,0(r3)            ; value[0]
815e14: cmpwi   cr7,r0,0x31         ; == '1' ?
815e18: beq     cr7,0x815e20        ; yes -> skip the "disable" store, fall into next key
815e1c: stw     r28,5100(r27)       ; no  -> this+0x13EC (the interval field!) = 0
                                     ;        i.e. `enable` GATES `interval`'s storage
815e20: li      r4,0x6490
815e24: clrldi  r3,r29,32           ; obj = this+0x13DC (same object, other alias)
815e28: oris    r4,r4,0xe6b5        ; r4 = 0xe6b56490 (enable-dlc-facebook)
815e2c: bl      0xb080ec            ; lookup(obj, hash)
815e30: nop
815e34: cmpwi   cr7,r3,0            ; value == NULL?
815e38: beq     cr7,0x815e54
815e3c: lbz     r0,0(r3)            ; value[0]
815e40: cmpwi   cr7,r0,0x31         ; == '1' ?
815e44: bne     cr7,0x815e54        ; not '1' -> leave the flag at its init value (0)
815e48: lwz     r9,-32408(r30)      ; r9 = &g_flag_dlcFacebook  (0x012b5658)
815e4c: li      r0,1
815e50: stb     r0,0(r9)            ; g_flag_dlcFacebook = 1
815e54: li      r4,0
815e58: clrldi  r3,r29,32           ; obj = this+0x13DC (same object again)
815e5c: oris    r4,r4,0xa171
815e60: ori     r4,r4,0x9b90        ; r4 = 0xa1719b90 (enable-dlc-facebook-text)
815e64: bl      0xb080ec            ; lookup(obj, hash)
815e68: nop
815e6c: cmpwi   cr7,r3,0
815e70: beq     cr7,0x815e8c
815e74: lbz     r0,0(r3)
815e78: cmpwi   cr7,r0,0x31
815e7c: bne     cr7,0x815e8c
815e80: lwz     r9,-32404(r30)      ; r9 = &g_flag_dlcFacebookText  (0x012b565c)
815e84: li      r0,1
815e88: stb     r0,0(r9)            ; g_flag_dlcFacebookText = 1
815e8c: li      r4,0
815e90: clrldi  r29,r29,32
815e94: oris    r4,r4,0xcf0a
815e98: mr      r3,r29
815e9c: ori     r4,r4,0xd2c7        ; r4 = 0xcf0ad2c7 (queue-server-addr)
815ea0: bl      0xb080ec
```

`r30` for this compilation unit is the literal-pool anchor, resolved by
finding its own load (`lwz r30,-29540(r2)` at `0x8158e8`) and reading
`*(r2-29540)` from the image: `r30 = 0x012bd4f0`. That resolves the two
flag targets:

    -32408(r30)  = 0x012bd4f0 - 0x7e98 = 0x012b5658   -> g_flag_dlcFacebook
    -32404(r30)  = 0x012bd4f0 - 0x7e94 = 0x012b565c   -> g_flag_dlcFacebookText

Both bytes are explicitly zero-initialized earlier in the same function
(`stb r0,0(r9)` / `stb r0,0(r11)` with `r0=0`, at `0x815d10`/`0x815d14`,
alongside the same-function zeroing of the `interval`/`enable`-derived
fields at `this+0x13E8/0x13EC/0x13F0/0x13F4/0x13FC`) - so both start `0` and
are only ever set to `1`, never explicitly cleared, matching a plain
`"1"`-prefixed boolean-enable semantic.

**Confirms the "enable-" naming and the boolean-toggle guess exactly**: same
`value != NULL && value[0]=='1'` pattern already used for `enable` itself, one
call after the other, in the same function, against the same object.

**Does NOT live on the save-manager singleton itself.** The four original
keys write into fields of the parsed config object (`this+0x13DC`, e.g.
`interval` -> `+0x13EC` off that sub-object). These two write into two
*separate, standalone* global bytes reached through this compilation unit's
own literal-pool anchor (`r30 = 0x012bd4f0`), not through the config object
or the save-manager `this` pointer at all. Whatever those two bytes represent,
they are file-scope statics in `saveworker.cpp` (or a very tightly-coupled
neighbor), not save-manager object state.

## No reader found for either flag, anywhere in 01.11

Two independent whole-image scans were run for readers of `0x012b5658` /
`0x012b565c`, both over the full 01.11 executable:

1. **`scan_anchor`-style two-hop scan** (project's established technique from
   `2026-08-20-followup-open-items.md` §0.3: find every `lwz rD,-N(r2)` whose
   resolved value equals a per-CU anchor, then every subsequent
   `load/store rX, off(rD)` whose `anchor+off` lands on the target address).
   Result: **only the two write sites already traced above** (`0x815e48`,
   `0x815e50`'s `lwz`, and `0x815e80`/`0x815e88`'s `lwz`, plus the two
   zero-init `stb`s at `0x815d10`/`0x815d14`). No hits anywhere outside this
   one function.
2. **Direct absolute-literal scan** (the same `lis`/`li`+`oris`/`ori` register
   tracker used to find the hashes themselves, retargeted at the two raw
   addresses `0x012b5658`/`0x012b565c` instead of the key hashes) - covering
   every other addressing idiom this binary uses for globals. Result: **zero
   hits anywhere in the image**, including inside the writer function itself
   (which reaches them exclusively through the `r30` anchor, not a direct
   literal).

Both scans cover the entirety of both LOAD segments (all executable code),
so this is not a partial search. **Verdict: the write is fully traced and
proven; no consumer of either resulting flag exists anywhere in the static
01.11 EBOOT.** This is a `NetInfo+0x80`/`0x8EFC1478`-shaped dead end, not an
open question to keep chasing - the same category the project already
accepts for `userdata/<id>.txt.crypt`'s one unrecovered key.

## Why 01.00 doesn't have this at all

`campaign3.config.txt.crypt`'s two extra keys line up with this project's
existing convention that this filename is requested only by "a later client
version" (per `2026-08-17-userdata-txt-crypt-format.md`). This pass makes
that concrete: 01.00's copy of the save-manager constructor
(`FUN_007f149c`, VMA `0x007f149c`) only ever looks up the original four key
hashes - confirmed by the same corrected literal scanner that found all four
correctly, finding *nothing* for either new hash anywhere in that binary.
01.11's copy of the same function is otherwise structurally identical (same
four original keys, same object, same `bl` lookup pattern, just relocated to
`0x00815b2c`) but has two extra lookup blocks appended right after `enable`.
So the two extra keys are a genuinely later addition to this one function,
not something 01.00 reads via a different code path.

## Confidence

**High** - both key hashes and their consumer are decompile-verified
instruction-by-instruction in 01.11, using the same scanner methodology this
project already validated by round-tripping the four known hashes. The
boolean-toggle semantics and the "different object than the other four keys"
finding are read directly off the disassembly, not inferred.

**High** (absence) - the "no consumer found" verdict for either flag rests on
two independent whole-image scans, each already proven (by the four-hash
validation pass and by the project's prior use of this exact anchor-scan
technique) to correctly find real cross-function references when they exist.

**Not established:** what the two global bytes at `0x012b5658`/`0x012b565c`
are *for* - no string, symbol, or other code path ties them to Facebook Graph
integration specifically; the `-dlc-facebook`/`-dlc-facebook-text` naming is
the only evidence of intent, and it comes from the key names themselves
(unrecoverable-string caveat does not apply here, since these two ARE the
literal plaintext key names from the real `campaign3.config.txt.crypt`
sample - unlike `userdata`'s `0x8EFC1478`).

## Practical effect on this project

None currently required. This server already serves
`campaign3.config.txt.crypt` with the real captured sample's content
unchanged (`enable-dlc-facebook 1`, `enable-dlc-facebook-text 0`); since no
01.11 consumer of either resulting flag was found, there's nothing to tune.
If this project ever targets 01.11 specifically and something Facebook- or
DLC-gated turns out to depend on these bytes via a mechanism this static pass
can't see (e.g. reached only through a vtable `bctrl` this linear scan
doesn't resolve), that would be the next thing to chase - but there is no
positive evidence for that today.
