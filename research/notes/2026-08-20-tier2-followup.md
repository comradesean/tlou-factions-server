# Tier 2 follow-up: capability bits, card_stat, the search window, rank_tier's override

Date: 2026-08-20 (second pass, after the DC00 directory record fix)

Static only - no live RPCS3 session, no new captures. Everything below is either
retail-disc / netN.bin bytes, 01.00 EBOOT disassembly verified with
`objdump -D -b binary -m powerpc:common64 -EB --adjust-vma=0x10000`, or a
re-count over the existing `server/logs/wire.jsonl`.

Two build-data bundles are used throughout:

| file | build | source |
|---|---|---|
| `dc1/net.bin` | 01.00 | `PS3_GAME/USRDIR/build/main/bin.psarc`, via `dc_dir.py --extract-from` |
| `net10.bin` | 01.11 | `server/data/served_content/net10.bin.psarc.crypt`, via `server/lib/psarc_crypt.py extract` |

`net10.bin`'s directory has 437 records to `net.bin`'s 392 and cracks by name
the same way. Only three exported symbols are new in 01.11
(`*net-molotov-radius-upgrades*`, `*net-proximity-bomb-radius-upgrades*`,
`*net-smoke-bomb-upgrades*`); everything else that changed between builds
changed in the *contents* of an already-existing global, which is exactly what
made the two files comparable below.

### Binaries, and the version-segregation rule applied to them

**The primary binary throughout this note is 01.00.** Every address is 01.00
unless it is explicitly labelled otherwise, and 01.11 is a recompile, so
addresses do not translate by a fixed delta.

| build | path | TOC (`r2`) |
|---|---|---|
| 01.00 | `games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf` | `0x01305870` |
| 01.11 | `TLOU-FACTIONS 1.11/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf` | `0x01338DE0` |

The 01.11 binary is the decrypted retail 01.11 patch SELF (`APP_VER 01.11`, from
that install's `PARAM.SFO`). Its program headers give the same
`file offset = VMA - 0x10000` mapping as 01.00 for both LOAD segments, so plain
`objdump -D -b binary -m powerpc:common64 -EB --adjust-vma=0x10000` works on it
unchanged; its `r2` was taken from the OPD descriptor at `e_entry`.

It is used in **one** place in this note - section 6's `param_5` producer - and
only because that producer is genuinely 01.11-only: the corresponding 01.00 code
path returns a constant 0, which is why the field is dead on the primary build
and why no amount of 01.00 analysis could ever have explained the nonzero wire
values. Everything else that section 6 concludes about the *meaning* of those
values (the profile record layout, the two stat ids, who they are credited to)
is derived from the 01.00 binary. Section 7 explicitly declines to use 01.11 at
all, for the stated reason that there is no 01.11-only behaviour there to
explain.

---

## 1. `member_data.capability_flag` - SOLVED, bit by bit

The consumer side was already pinned in `protos/common/member_data.ksy`: every
member's byte 8 is AND-reduced into a lobby-common mask by `FUN_00ad2b14`, and a
map/mode candidate survives only if `common_caps & descriptor(+0x14) != 0`, with
a descriptor whose `+0x14` is 0 always eligible. What was missing was the
descriptor table.

It is `*net-maps*`, and `+0x14` is its sixth word.

Instruction-verified at the picker call site (01.00):

```
3a254c  lwz     r9,0(r3)          ; count      <- *net-maps* member0.count
3a2570  lwz     r9,4(r10)         ; array      <- *net-maps* member0.array_ptr
3a2574  mulli   r0,r11,76         ; STRIDE 76
3a2580  clrldi  r29,r0,32         ; r29 = &maps[i]
3a2598  lwz     r0,20(r29)        ; required_mask = maps[i] + 0x14
3a259c  cmpwi   cr7,r0,0
3a25a0  beq     cr7,0x3a25d0      ; mask == 0 -> always eligible
3a25a4  lwz     r3,-32696(r30)
3a25a8  bl      0xad2b14          ; common_caps = AND-reduce over the roster
3a25b0  lwz     r0,20(r29)
3a25b4  and     r3,r3,r0
3a25b8  cmpwi   r3,0
3a25bc  bne     0x3a25d0          ; owned -> keep
3a25c8  stw     r3,0(r9)          ; not owned -> drop the candidate
```

A second, identical gate is at `0x35ad74`-`0x35ad8c` on a different table
pointer (`-32724(r30)` vs `-32696(r30)`).

`*net-maps*` decoded with that stride (`{name_hash, alt_hash, type_tag,
name_ptr, ptr, REQUIRED_MASK, alt_name_ptr, ...}`; the two `_ptr` columns are
file offsets to plain C strings inside the bundle):

**01.00 `dc1/net.bin`, `*net-maps*` = `{count: 8, array -> 0x14984}`** - all
eight entries have `required_mask == 0`:

```
net-levels/huntercity-2  net-levels/lakeside-2   net-levels/university-2
net-levels/billschurch-2 net-levels/highschool-2 net-levels/outskirts-2
net-levels/dam-2         net-levels/warzone
```

**01.11 `net10.bin`, `*net-maps*` = `{count: 19, array -> 0x23740}`:**

| mask | maps |
|---|---|
| `0x00` | huntercity-2, lakeside-2, university-2, billschurch-2, highschool-2, outskirts-2, dam-2 (`coop-tom-river`), dam-2 (`coop-hun-hotel`), warzone |
| `0x01` | **bookstore-2, busdepot-4, hometown-1, suburbs-1** |
| `0x04` | **watertower-1, mine-1, capitol-4, wharf-3** |
| `0x08` | **plaza-3, beach-final** |

That is the whole answer to "which bit is which DLC pack":

- **bit 0 (`0x01`)** - a four-map pack: Bookstore, Bus Depot, Hometown, Suburbs.
- **bit 1 (`0x02`)** - **used by no map descriptor in either bundle.** This is
  why the one live data point is `0x0d` and not `0x0f`: the client owns
  everything the map table can ask for, and bit 1 simply never appears as a
  requirement. Whether bit 1 gates something that is not a map (a mode, an item
  pack) is not established - nothing in the 437-record directory carries a
  matching mask.
- **bit 2 (`0x04`)** - a four-map pack: Water Tower, Coal Mine, Capitol, Wharf.
- **bit 3 (`0x08`)** - a two-map pack: Plaza, Beach.

Retail *marketing* names for those three groups are deliberately NOT asserted
here. The two four-map groups are the right shape for the two retail four-map
Map Packs, but the grouping above is what the shipped data says, and that is
what a server should reason about.

Consequence for the stub: `0x0d` is the correct, complete "owns all shipped MP
map content" value on 01.11, and a server that fabricates a card should send
`0x00` (base maps only) unless it intends to advertise DLC ownership.

`*dlc-version*` is a scalar and irrelevant to the bit map: `1` on 01.00, `2` on
01.11. `*net-rank-version*` is the same shape: `6` on 01.00, `8` on 01.11. Both
are data-format stamps.

---

## 2. `member_data.card_stat_2` / `card_stat_3` - they are not numbers

The write condition for `P+0x654` was the question. Answering it changes what
the field IS.

`FUN_0034d378` (called once, from `0x0035564c`) is a two-way sync between the
profile record and a pair of globals:

```
34d398  lwz  r24,-31808(r30)      ; -> 0x01379b70   (a dirty flag byte)
34d3ac  lbz  r31,0(r24)
34d3b4  beq  -> 0x34d4f0          ; not dirty -> LOAD path

; ---- STORE path (dirty) ----
34d3b8  lwz  r28,-32496(r30)      ; -> 0x013839d0
34d3c0  bl   0x3ae8b4             ; `li r3,1; blr`  - a retail STUB, always true
34d3d4  lwz  r29,-31804(r30)      ; -> 0x01379b80   (an 8+ byte C string buffer)
34d3d8  lbz  r0,0(r29)
34d3e0  beq  -> 0x34d40c          ; string empty -> skip the overwrite
34d3e8  bl   0x3ae8bc             ; `lbz r3,64(r3); blr` -> *(u8*)(0x013839d0+0x40)
34d3f8  beq  -> 0x34d40c
34d3fc  li   r0,42
34d400  stb  r0,0(r29)            ; g[0] = 42  ('*')
34d404  li   r0,0
34d408  stb  r0,1(r29)            ; g[1] = 0   -> the string becomes "*"
...
34d48c  bl   0x3cb89c             ; profile-block accessor, the SAME one the
34d494  stw  r29,1620(r3)         ;   member-card producer reads at 0x3b1714
34d4b8  stw  r29,1624(r3)         ; P+0x658 gets bytes 4..7 of the same buffer
34d4d8  bl   0x3b15bc             ; re-run the member_data card producer
34d4e8  stb  r0,0(r9)             ; clear the dirty flag

; ---- LOAD path ----
34d514  bl   0x3cb89c             ; read P+0x654 / P+0x658 back into a stack temp
34d5fc  bl   0xe459bc             ; strcmp(0x01379b80, temp)      [word-at-a-time
34d614  bl   0xe45b10             ; strcpy(0x01379b80, temp)       0x7f7f7f7f idiom]
```

`0xe459bc` and `0xe45b10` were checked instruction by instruction: both are the
classic word-at-a-time `strcmp`/`strcpy` with the `0x7f7f7f7f` zero-byte trick,
and `0xe45b10` returns its `dest` in `r3` via `mr r6,r3`. So the profile's
`P+0x654..0x65B` is **an eight-byte, NUL-terminated ASCII string**, not two
numeric stat cells - and `card_stat_2`/`card_stat_3` are its first four
characters, byte-for-byte, byte order preserved (the producer at `0x3b1714`
loads `0x654..0x657` as four `lbz` and re-assembles them big-endian).

That reframes the field but does not name the string. What *can* be said
exhaustively:

- The two globals `0x01379b70` (dirty flag) and `0x01379b80` (the buffer) are
  reachable from exactly **two** functions in the whole binary - `FUN_0034d378`
  and `FUN_003557a8` (which clears both at `0x00356d00`/`0x00356d04`). Each has
  exactly one TOC slot (`0x012681e0`, `0x012681e4`) and no `lis`/`addi`
  literal anywhere. There is no UI text-entry path into this buffer.
- Therefore the ONLY value the buffer can ever hold, other than what it read
  back out of the profile, is the literal string `"*"` written at
  `0x34d3fc`-`0x34d408`.
- That write requires `*(u8*)(0x013839d0 + 0x40) != 0`.

`0x013839d0` is a net event recorder/playback object: `.bss` (not file-backed,
so zero at load), constructed at `0x3ae8c4` (memsets `+0x98` for 352 bytes,
zeroes `+0x08/+0x10/+0x24/+0x48/+0x70/+0x90/+0x94`, sets `+0x74 = -1`, and
never touches `+0x40`), with accessors for a frame count at `+0x24`
(`(count-1)/10`, i.e. seconds at 10 Hz), two per-frame record arrays at `+0x28`
(stride 128) and `+0x2c` (stride 64), a playback-speed word at `+0x90`, and
pause/step booleans at `+0x94`/`+0x95`. Several of its entry points are retail
stubs (`0x3ae818`, `0x3ae820`, `0x3ae8ac` are `li r3,0; blr`; `0x3ae8b4` is
`li r3,1; blr`). It is also the object the match-results path (`FUN_003f208c`,
already named `NET_SM_RESULTS` by this project) appends event `405` into.

A scan of the object's entire compilation-unit band (`0x3a0000`-`0x3c0000`) for
any `stb/sth/stw` at displacement `0x40` found two candidates, both of which
turned out to be per-frame-record writes (`0x3a2b28`, `0x3b03a8` - the latter
inside `FUN_003afb74`, writing `base+offset+0x40/0x41/0x42/0x43`), not the
object header.

**Status.** Bytes and provenance: high confidence, instruction-exact. Type
(a C string, not a number pair): high confidence - `strcmp`/`strcpy` on the same
buffer settles it. Meaning of the string: still open, but the space of possible
values is now closed to `""` or `"*"` on this build, which is consistent with
the 855/855 zero frames without needing "no live data ever populated it" as an
excuse. What would populate it is a nonzero `*(u8*)(0x013839d0+0x40)`, and no
store to that byte was found.

Not claimed: that `"*"` is a censorship marker, a recording marker, or anything
else. `42` is `'*'` and the buffer is string-typed; that is as far as the bytes go.

---

## 3. `0x142 HostRank` - still blocked (fast re-check)

`*net-rank-version*` exists in the directory and is a scalar (`6` on 01.00, `8`
on 01.11) - a data-format stamp, not `0x0002`. Nothing else in either bundle's
437/392 records is shaped like a per-player rank encoding, and the observed
value comes from the player object's `vtable[0]` getter, not a DC table. The
corrected directory does not move this item. Still needs a ranked capture.

---

## 4. `0x12f` small fields - producers closed, one still needs a caller

All four resolved against `FUN_00ad5b78`'s prologue, which is
`f(r3, room_obj=r4, max_players=r5, p4=r6, p5=r7, p6=r8)`:

| field | verdict | evidence |
|---|---|---|
| `caller_arg_1c` | the sender's **`param_5` (`r7`)**, verbatim | `mr r27,r7` @`0xad5bc4`, `sth r27,172(r1)` @`0xad5c60`, then `li r27,0` @`0xad5c6c` |
| `flag_27` | `4` iff the sender's **`param_4` (`r6`) != 0**, else `0` | `mr r26,r6` @`0xad5bc0`; `stb r27(=0),183(r1)` @`0xad5c8c`; `cmpwi cr7,r26,0` @`0xad5c90`; `beq 0xad5cc0`; `li r0,4` / `stb r0,183(r1)` @`0xad5cb8`-`0xad5cbc` |
| `value_20` / `value_22` | `(int)` of two floats read straight off a config object | `bl 0xacb6bc` @`0xad5c70` with `r3 = *(u32*)(*(anchor-32748) + 4)`, `r4 = r1+124`, `r5 = r1+112`; `FUN_00acb6bc` is a three-instruction getter: `*p4 = *(float*)(obj+0x48); *p5 = *(float*)(obj+0x4C)`. `value_20 = (int)obj->f[0x4C]`, `value_22 = (int)obj->f[0x48]`, both `1000.0` live |
| `room_flags_e8`'s `0x40000000` OR | gated on the sender's **`param_6` (`r8`) != 0** | `mr r28,r8` @`0xad5bc8`; `cmpwi cr7,r28,0` @`0xad5c30`; `beq 0xad5c50`; `oris r0,r0,16384` @`0xad5c4c` |

The last row independently corroborates item 35's live result (the gate register
read 0 in both breakpointed samples): the gate is a caller argument, not a
room-object field, so it is entirely determined by whoever calls the sender.

`FUN_00ad5b78`'s callers were not located this pass. It is reached through
vtable slot `+0x10` of the vtable at `0x01243b38` (its OPD `0x012e9c40` appears
there and nowhere else; the `0x135` sender `FUN_00ad6c70`'s OPD `0x012e9c88` is
slot `+0x14` of the same vtable), so the call is a `bctrl` and `scan_bl.py`
cannot see it.

---

## 5. `0x13e`'s `flag` byte - CORRECTED: it is 4/0, not 0/1

The current doc calls the byte "boolean when written (0 or 1)" and treats the
live values 3 and 4 as stale residue. Half of that is right and half is wrong.

**Builder `FUN_00ad6a34` (`kind = 3`) never writes the flag byte at all.**
Disassembling the whole function `0xad6a34`-`0xad6bf8`: the only byte store into
the 16-byte send buffer at `r1+112` is `stb r0,117(r1)` (`li r0,3` @`0xad6b64`,
the `kind`). There is no `stb ..,116(r1)` anywhere in it. It reads and writes
the room's own `+0x19f4` host flag (`lbz r0,6644(r31)` @`0xad6ab8`,
`stb r0,6644(r31)` @`0xad6af0`) but never puts it on the wire. So on every
`kind=3` frame, wire offset 4 is genuinely uninitialised stack - which is
exactly the census's `(0,3) x35`, `(3,3) x35`, `(1,3) x2`.

**Builder `FUN_00ad7024` (`kind = 4`) writes 4 or 0, never 1.**

```
ad711c  clrlwi  r9,r28,24     ; r28 = the builder's param_3 (r5), as a byte
ad7124  neg     r9,r9         ; -b : sign bit set iff b != 0
ad712c  rlwinm  r9,r9,3,29,29 ; keep MSB-bit 29 of rotl(x,3) -> the value 4 or 0
ad7130  li      r0,4
ad713c  stb     r0,117(r1)    ; kind = 4
ad7140  stb     r9,116(r1)    ; flag = 4 if param_3 != 0 else 0
```

`rlwinm rA,rS,3,29,29` masks to a single bit whose value is `4`, so the byte can
only be `0x04` or `0x00`. That is the census's `(4,4) x40` and `(0,4) x4` -
which the "boolean, treat >1 as residue" reading had been discarding as garbage.
The single `(3,4)` frame out of 117 is unexplained and is the only sample that
does not fit.

Practical effect: a server should read `kind=4`'s offset-4 byte as
`4 = set / 0 = clear`, and must ignore offset 4 entirely on `kind=3`.

---

## 6. `search_window_lo` / `search_window_hi` - SOLVED: a career K/D ratio, +/- a DC column

`*net-matchmaking-criteria*` (`crc32_mpeg2` `0xB25AB071`, already cited by this
project as the source of the "searches per burst" limit) is an array of
**20-byte** records. Stride and column roles are pinned by the find-match state
machine itself, `FUN_003b5ff4`:

```
3b6098  lis  r3,-19878 / ori r3,r3,45169   ; 0xB25AB071
3b60a0  bl   0x9fa9f4
3b60c0  lwz  r9,0(r28)                     ; attempt counter (global 0x013858b4)
3b60c4  lwz  r11,4(r11)                    ; criteria array pointer
3b60c8  mulli r9,r9,20                     ; STRIDE 20
3b60d0  add  r27,r9,r11                    ; r27 = &criteria[attempt]
...
3b61cc  lwz  r0,4(r9)                      ; criteria[i] + 0x04
3b61d4  lwz  r26,0(r9)                     ; criteria[i] + 0x00
3b61d8  srawi/xor/subf/srwi                ; r29 = (criteria[i].+0x04 != 0)
3b6164  lwz  r31,16(r9)                    ; criteria[i] + 0x10
...
3b6200  extsw r5,r26                       ; param_3 = burst_marker
3b6214  clrldi r6,r29,63                   ; param_4 = send-locale flag
3b621c  extsw r7,r23                       ; param_5
3b6224  extsw r8,r25                       ; param_6
3b6228  extsw r9,r31                       ; param_7
3b6230  bctrl                              ; -> FUN_00ad6c70 (opcode 0x135)
```

and a second consumer of the same row in `FUN_003b6584`:

```
3b6810  mulli r9,r9,20
3b681c  lwz  r0,8(r9)                      ; criteria[i] + 0x08
3b6828  cmpw cr7,r29,r0
3b682c  bge  -> give up / self-host
```

So the record is
`{+0x00 burst_marker, +0x04 send_locale, +0x08 give-up threshold, +0x0c type_hash, +0x10 window half-width}`.

**01.00 `dc1/net.bin` (`count: 5, array -> 0x197f4`):**

```
i  marker  locale  threshold  half
0     5      1        50        5
1    10      1       100        5
2    10      0       100       10
3     0      0       200       10
4     0      0         0        0
```

**01.11 `net10.bin` (`count: 21, array -> 0x1359c`):**

```
i       marker  locale  threshold  half
0-2       35      1        50       60
3-5       35      0        50        0
6-8       50      1        75       60
9-11      50      0        75        0
12-15     50      0       100        0
16-18     70      0       150        0
19-20      0      0       200        0
```

Cross-checked against a fresh census of all 2,188 captured `0x135` frames,
keyed on `(burst_marker, lo, hi)`:

```
(10,   0,   0) x564   (0,   0,   0) x534   (5,   0,   0) x437     <- 01.00 clients
(50, 397, 397)  x96   (50,  29,  29) x84
(35, 337, 457)  x49   (35, 397, 397) x46   (50, 337, 457) x42
(35,   0,  89)  x42   (35,  29,  29) x42   (50,   0,  89) x40
(70, 397, 397)  x37   (70,  29,  29) x33   ...                    <- 01.11 clients
```

Every marker value on the wire is a marker column of the right build's table
(5/10/0 for 01.00, 35/50/70/0 for 01.11 - **not comparable across builds**, the
same way playlist ids aren't), and every widened pair is exactly `+/-60`, and
`60` appears in exactly the rows whose marker is 35 or 50. `337 = 397-60`,
`457 = 397+60`, `89 = 29+60` with the low end clamped at 0 by
`max(0, param_5 - param_6)`. The magic `60` is a shipped DC constant, and
`burst_marker` is not "a caller-supplied criteria index" - it is *the criteria
row's own first column*, which is why it repeats across consecutive searches.

### The build split in the capture, established rather than assumed

Every marker on the wire is a marker column of one of the two tables, and the
two families never mix inside a single server run. `wire.jsonl` is append-only
across server restarts and connection ids restart at 1 on each run, so the
connection id is not a stable client identity across the log; the reliable
separator is time plus frame shape. The families switch as a block, on every
connected client at once, at `2026-08-19T00:49` and back at
`2026-08-19T16:13`, and the two eras differ in fields the 01.00 sender never
writes at all:

```
01.00 era  00000135 d00401a0 01383bd8 00000002 102c503f 03e803e8 0005 0000 0000 0000 75730001
01.11 era  00000135 d0040630 013babd8 00000002 103c5020 03e803e8 0023 0001 0151 01c9 75730001
                     ^^^^^^^^ ^^^^^^^^          ^^^^^^^^              ^^^^ attempt counter
```

The attempt counter at offset 26 (documented as `pad_1a`, an unwritten gap) is
zero in every 01.00-era frame and counts `0,1,2,3,4,5` in the 01.11-era ones,
which is an independent, sender-side discriminator: two different builds, not
one build reading two bundles.

### `param_5` is the game's own "rank value"

The 01.11 producer names it in its own debug output. On the find-match path the
string at `-32372(r30)` is

```
------------------Use rank value of %d\n
```

and it is printed with exactly the register that becomes `param_5`.

**01.00 (the primary EBOOT): structurally 0.** The producer at this call site
is `FUN_003b3898` (`mr r23,r3` @`0x3b612c`):

```
3b3898:  M = *(anchor-32712)                    ; = 0x0137d700, the NetGameManager
         if (!FUN_0039f250(M)) return 0
         p = FUN_00349360(M)                    ; -> a *playlists* row
         if (!p) return 0
         if ((s32)p[0x50] <= -1) return 0
         return p[0x50]
```

`FUN_00349360` = `FUN_0039e900(M, FUN_0039abdc(M))`: `FUN_0039abdc` picks a key
- either the constant `0x0B70ED28` when `*(u8*)(g+14108)` is set, or the u32 at
profile `P+0x2F8` - and `FUN_0039e900` linearly scans DC table `0xC1B0BE0D`,
which `dc_hash_crack.py` reverses to `*playlists*`, stride 92
(`mulli r0,r28,92` @`0x39e950`), matching on the row's first word.
`FUN_0039f250` returns `p && p[0x20] == 0`.

Dumping `*playlists*` from both bundles with that stride: 01.00
`{count: 4, array -> 0x6308}`, `+0x50` = `2, 4, -1, -1`; 01.11
`{count: 17, array -> 0x22a24}`, `+0x50` = `2, 4` then `-1` for all fifteen
remaining rows, `+0x20` zero in every row. So the `<= -1` test fails for every
real matchmaking playlist and the producer returns 0 - which is exactly the
capture: **all 1,535 frames from 01.00 senders have `(0,0)`, without
exception.**

### `param_5` on 01.11 - a career kill/death ratio, x100

This is 01.11-only behaviour: the 01.00 EBOOT has no equivalent code on this
path, which is precisely why the field is dead there. The 01.11 binary is
therefore cited here **only** for the mechanism that does not exist in the
primary build, its addresses are marked as such throughout, and none of them
transfer.

Source: `TLOU-FACTIONS 1.11/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf`
(decrypted retail 01.11 patch SELF; `APP_VER 01.11`). Its program headers give
the same `file offset = VMA - 0x10000` mapping as 01.00 for both LOAD segments,
and its TOC is `r2 = 0x01338DE0` (from the `e_entry` OPD descriptor), *not*
01.00's `0x01305870`.

The 01.11 find-match state machine is `FUN_003cfd90` (**01.11 addresses**), with
`r30 = *(r2-31048) = 0x012A392C`. Its sender call is at `0x3d0148`, and the
argument mapping is the same shape as 01.00's plus one extra:

```
3d0114  extsw r5,r26            ; param_3 = criteria[i]+0x00  (burst_marker)
3d0120  clrldi r6,r28,63        ; param_4 = (criteria[i]+0x04 != 0)
3d0128  extsw r7,r31            ; param_5 = the rank value
3d010c  extsw r8,r24            ; param_6 = criteria[i]+0x10  (half width)
3d0140  mr    r9,r8             ; param_7 = the SAME half width
3d0134  clrldi r10,r25,63       ; param_8, new in 01.11
```

`param_6 == param_7` is why every widened pair in the capture is symmetric.

The rank value itself:

```
3cff10  bl 0xa22108             ; DC lookup, hash 0xB4744777
3cff1c  lwz  r0,0(r3)
3cff20  cmpwi cr7,r0,1
3cff24  beq  cr7,0x3cff38       ; == 1 -> ratio branch
3cff28  add  r9,r28,r29         ; else: (P+0x1E34 + P+0x1E38) / 7
3cff2c  li   r0,7
3cff30  divw r31,r9,r0
        ; ---- ratio branch ----
3cff4c  lbz ... 852(r10)        ; P+0x0354
3cff84  lbz ... 832(r10)        ; P+0x0340
3cffac  add  r29,r29,r0
3cffc4  lfs  f0,-32360(r30)     ; = 100.0
3cffc8  fmuls f31,f31,f0
3cffdc  lbz ... 856(r10)        ; P+0x0358
3d000c  lbz ... 836(r3)         ; P+0x0344
3d0038  add  r29,r29,r0
3d0050  fdivs f31,f31,f0
3d0054  fctiwz f31,f31          ; -> rank value
```

`r10` comes from `bl 0x3e6adc`, which returns `obj + 0xC8` after a lazy
init - the profile block. The base is pinned independently by the fallback
branch: `P+0x1E34` and `P+0x1E38` are `profile_21.ksy`'s already-named
`matches_mode_a` / `matches_mode_b`, so `(matches_a + matches_b) / 7` is
"matches played per week", and the same base makes `0x340/0x344/0x354/0x358`
profile offsets.

The gate `0xB4744777` is present **only** in `net10.bin`
(`key=b4744777 type=c7cb275c value=0x53d0`, word 0 = `1`, so the ratio branch
is the live one); it is absent from the 392-record `dc1/net.bin` directory, and
no `.dci` symbol in the retail disc's 43,674-token compiler-symbol corpus
reverses to it, so the global is unnamed.

### What the four profile counters are

`P+0x0334..0x035B` was an undocumented gap. It is **two 20-byte cumulative
career-stat records**, one per game mode, written at match end by
`FUN_003f208c` (this project's `NET_SM_RESULTS`) in the **primary 01.00
EBOOT** - so the field identity is established on the primary build, not
imported from 01.11. The mode gate is the same one that already explained
`matches_mode_a`/`matches_mode_b`:

```
3f28b0  lhz   r0,12(r9)
3f28b4  cmpwi cr7,r0,2
3f28b8  beq   cr7,0x3f28c8      ; -> record 0 arm (P+0x0334..)
3f28bc  cmpwi cr7,r0,3
3f28c0  bne   cr7,0x3f2ffc      ; neither -> write nothing
3f28c4  b     0x3f2c60          ; -> record 1 arm (P+0x0348..)
```

| off | field | writer (mode-2 arm) |
|---|---|---|
| +0x00 | `score_total` | `+= matchStat->0x04` (`lwz r29,4(r26)` @`0x3f2924`, `stw` @`0x3f2964`) |
| +0x04 | `time_total` | `+= matchStat->0x10` (`lwz r29,16(r25)` @`0x3f2968`, `stw` @`0x3f29a8`) |
| +0x08 | `score_best` | high-water, `cmplw`/`bge` guard @`0x3f2908`, `stw` @`0x3f291c` |
| +0x0C | `downs_dealt` | `+= statQuery(0x5C494554)` (`bl 0x3e7430` @`0x3f29d4`, `stw` @`0x3f2a28`) |
| +0x10 | `downs_taken` | `+= statQuery(0x230015B3)` (`bl 0x3e7430` @`0x3f2a2c`, `stw` @`0x3f2a78`) |

`score_total`/`time_total` are identified by the already-documented
`match_ratio_1e3c`, which is `(matchStat->0x04 * 6000) / matchStat->0x10`
(`mulli r29,r29,6000` / `divwu` @`0x3f29b4`-`0x3f29c8`) - score per minute
scaled by 100, which only works with a score numerator and a seconds
denominator.

The two stat hashes resolve against `*net-stats*` (`dc1/net.bin` array
`0x9c18`, stride 8, `{stat_id_hash, text_string_id}`, strings via
`text_table.py` on `text1.psarc`'s `2.networking` table):

- `0x5C494554` = row 0 = **"Downed Enemy"**.
- `0x230015B3` = row 2 = **no localized display string in any of the four
  English category tables**, so its retail name is not asserted.

Row 2's role is nevertheless established twice over, both in the primary
EBOOT:

1. **It is credited to the victim.** `FUN_0040d45c` is the downed-player event
   handler. `event->0x10` resolves to a player at `0x40d4cc` (`r26`, the
   victim) and `event->0x18` resolves to a player at `0x40d5d4` (`r28`, the
   attacker). `0x230015B3` is awarded with `target = r26` @`0x40d59c`, before
   the attacker is even looked up; `0x5C494554` is awarded with `target = r28`
   @`0x40d6bc`, after a same-team guard (`lwz r9,476(r27)` / `lwz r0,476(r3)` /
   `cmpw` / `beq -> 0x40d6ec` @`0x40d5ec`-`0x40d5fc`) that skips all attacker
   credit on friendly fire. The intervening awards are `0xACD2D064`
   "Special Execution" @`0x40d60c` and `0xC1E560E1` "Execution" @`0x40d68c`,
   both to the attacker - consistent with a kill handler.
2. **Lower is better.** The scoreboard comparator at `0x3e75f0` sorts
   `0x5C494554` descending (`cmpw` / `bgt -> -1` @`0x3e7644`-`0x3e7648`) and
   `0x230015B3` **ascending** (`cmpw` / `blt -> -1` @`0x3e76a0`-`0x3e76a4`).

So `downs_taken` is the player's own downs/deaths, and

```
rank_value = (int)( 100 * (downs_dealt[0] + downs_dealt[1])
                        / (downs_taken[0] + downs_taken[1]) )
```

is a **career kill/death ratio expressed in percent**.

### Numeric verification

Decoding the two stored profiles with `profile21_codec.py`:

| account | dealt (m2 / m3) | taken (m2 / m3) | computed | wire values |
|---|---|---|---|---|
| `comradesean` | 166 / 46 | 36 / 19 | `100*212/55` = **385** | 397, 373, 365 |
| `mgnomad2` | 32 / 18 | 133 / 42 | `100*50/175` = **28** | 29, 31 |
| `gmnomad` | 0 / 0 | 0 / 0 | n/a, 0/0 | none - all 258 of its `0x135` frames are 01.00-era |

The profiles are a day newer than the capture, so exact equality is not
expected; the magnitudes agree and the direction of travel does too -
`comradesean`'s wire value fell 397 -> 373 -> 365 inside one session as he
accumulated deaths. That also **corrects** the earlier characterisation of this
quantity as one that "climbs with play": it is a ratio and moves both ways,
which is why it matched no leaderboard board and no monotone counter.

**Net effect:** `burst_marker`, `param_6`/`param_7` and `param_5` are all fully
solved and named, on both bundles and both builds. Nothing about this field is
open.


## 7. `member_data.rank_tier` - the override has no writer, confirmed twice

The remaining question was "who writes `*(global+0x78)`". The answer is
**nobody**, in the whole 01.00 binary.

The pointer chain, re-derived from the bytes rather than reused:

```
r2                       = 0x01305870
*(r2 - 31028)            = *(0x012FDF3C) = 0x0127227C   ; the CU anchor
0x0127227C - 32756       = 0x0126A288                   ; the object-pointer slot
*(0x0126A288)            = 0x01385CDC                   ; the object (a literal)
                 +0x78   = 0x01385D54                   ; the override word
```

and the read, disassembled rather than inferred:

```
3c8e3c  lwz  r30,-31028(r2)
3c8e44  lwz  r9,-32756(r30)
3c8e48  lwz  r9,120(r9)          ; the +0x78 read
3c8e4c  cmpwi cr7,r9,0
3c8e50  addi r11,r9,-1
3c8e54  bne  cr7,0x3c8ed8        ; nonzero -> return r9 - 1
```

`0x01385CDC` is the object this project's 2026-08-17 notes call the
lobby-state / `g_mission` object (`+0x64` the runtime floor, `+0x8D` the
gametype byte). It is a fixed `.bss` address - the slot holds it as a literal,
and `eb.py` reports `0x01385D54` unmapped in both LOAD segments, i.e. zero at
load - which makes an address-based store scan valid.

Two independent scans, by different methods, agree:

- A whole-binary **pointer-taint** scan: collect all TOC/anchor slots whose
  contents equal `0x01385CDC` (**44** of them), then walk `.text` linearly,
  resetting state at each `stdu r1,-N(r1)` frame, tracking which registers hold
  the object pointer and propagating through `mr` and `clrldi` aliases. Result:
  **187 field accesses, 12 of them stores**, at displacements
  `0x00, 0x04, 0x08, 0x44, 0x72, 0x7e, 0x7f, 0x88, 0xb8, 0xbc`. No X-form
  indexed store lands on the object at all.
- An earlier scan that instead resolved each candidate slot's content and
  followed the loaded pointer function-scoped: **246 accesses, 21 stores**, at
  `0x00, 0x04, 0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x44, 0x72, 0x7e, 0x7f,
  0x88, 0xb8, 0xbc`.

The second scan is the more complete of the two (the first loses leaf functions
that never open a frame), but **both find offset `0x78` touched exactly once in
the whole binary, and both find that the one touch is the read at
`0x003c8e48`** - inside `FUN_003c8e30`, the `rank_tier` producer itself.
`scan_imm.py` additionally finds no `lis`+`addi` construction of either
`0x01385CDC` or `0x01385D54`, ruling out an immediate-addressed writer.

Combined with the already-established result that the DC branch returns a hard
`0`, `rank_tier` is structurally `0x0000` on 01.00 for every account, ranked or
not. That is exactly the capture: 855/855.

Caveats, stated plainly: a whole-struct `memset`/`memcpy` through a pointer the
scanner loses track of would still write zero, so it cannot change the
conclusion; a write through a pointer spilled to memory and reloaded elsewhere
would not be caught. Within 01.00 this is as close to exhaustive as a static
scan gets.

01.11 was deliberately **not** substituted in here, even though the binary is
now available. 552 of the 855 all-zero `0x13a` frames fall inside the 01.11 era
of the capture (see section 6 for how the eras are separated), so the field
reads `0` on both builds and there is no 01.11-only behaviour to explain. Using
the other binary would be a version-segregation violation with nothing to buy.


## 8. Items re-checked and unchanged

- **`member_slot_ec` (46), `0x134 trailing` (47), `np_id.opt`/`reserved` (48)** -
  none of these has a DC hash or a DC-table dependency; the corrected directory
  cannot bear on them, and the whole-binary reader scans behind them were
  already done twice. No re-work, no change.
- **`0x136 attr_tail` (49a)** - the ledger's status is accurate: mechanism
  resolved at instruction granularity, lands in `g_70`/NetInfo `0xb0:0xc4`, 51
  call sites in one compilation unit scanned with no reader, live canary test
  showed no client-visible effect. Interior meaning needs a retail PS4 capture.
  No further static tracing attempted, per that finding. The 01.11 PS3 binary
  becoming available does not bear on it either: the open question is what the
  RETAIL PS4 backend puts in those bytes, not whether a second PS3 build reads
  them, so no reader scan was run against 01.11.
- **`0x142` (37/54)** - see section 3.

---

## Tooling notes

`research/tools/dc_dir.py` works unchanged on `net10.bin`; the only thing needed
was to extract it first with `server/lib/psarc_crypt.py extract`. Two more
stride/shape entries worth adding to its docstring table:

```
*net-maps*                      76   {name_hash, alt_hash, tag, name_ptr,
                                      ptr, required_caps_mask, alt_ptr, ...}
*net-matchmaking-criteria*      20   {burst_marker, send_locale,
                                      giveup_threshold, type_hash, half_width}
*playlists*                     92   {key_hash, ..., +0x20 gate, +0x50 s32, ...}
*net-stats*                      8   {stat_id_hash, text_string_id}
```

`research/tools/profile21_codec.py --raw-out` plus a five-line `struct.unpack`
loop is the fastest way to test a candidate profile-offset reading against real
accounts; it is what settled section 6's formula. Note that its printed field
positions are `P - 8` (the record's 8-byte header), the same convention
`protos/profile_21.ksy`'s `pos:` uses.

`*net-maps*` and `*net-matchmaking-criteria*` both pair a hash with plaintext or
with values the EBOOT reads at a proven displacement, so neither needs the
still-unidentified intra-table hash algorithm.
