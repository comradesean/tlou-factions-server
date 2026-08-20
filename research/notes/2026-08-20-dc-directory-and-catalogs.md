# 2026-08-20 - the DC00 directory is fully readable: 392 named globals, and four catalogs out of it

Status: **solved** for everything marked SOLVED below; the per-entry hash in
§6 is explicitly **not** solved and is called out as such.

Working file throughout: `dc1/net.bin` (283,615 bytes) out of the retail
disc's plain `build/main/bin.psarc`. `docs/protocol/dc_table.md` already
established that this file is structurally identical to `served_content`'s
`net1.bin`. New tool: `research/tools/dc_dir.py` - every offset quoted here
is reproducible from a clean checkout with it.

---

## 1. The directory record was being read one word off

`dc_table.md` read the repeating unit as
`{value_ptr, key_hash, type_hash}`. It is
**`{key_hash, type_hash, value_ptr}`**, and the bundle header states where the
directory is and how long it is:

```
net.bin +0x14 : u32 entry_count = 392
net.bin +0x18 : u32 dir_offset  = 0x1c
records       : 392 x 12 bytes at 0x1c .. 0x127c
```

Byte-exact demonstration - the record for `member_data.rank_tier`'s hash:

```
0x000ec8  c7f8567c ed6b8e26 0001dd24     <- *net-emblem-layers-frame*
0x000ed4  c85e199d ced9d25f 000052f4     <- *net-money-info*
0x000ee0  c970681f 290349e3 00005300
```

The old reading paired `0xc85e199d` with the value pointer `0x0001dd24`
sitting one word *above* it. That pointer belongs to the **previous** record.
This is the direct cause of a wrong claim in `dc_table.md` and in
`protos/common/member_data.ksy` - that `*net-money-info*` resolves to a
"193-entry payload" that "never read cleanly as flat rank thresholds". The
193-entry table is `*net-emblem-layers-frame*`. `*net-money-info*` is a
99-entry table and it reads perfectly (§3).

Independent confirmation of the corrected layout, on a record that the old
layout would have mis-assigned as well: `0xbcbbdfbd` (`*net-emblem-colors*`,
already cracked 2026-08-19) sits at `0xdf0`, and `value_ptr` at `0xdf8` =
`0x50fc` = `{count:64, array:0x15e94}`, whose 64 elements are 64 RGBA float
quads laid out as an 8x8 hue grid (§4). Under the old layout the same record
would have pointed at `0x50f0` = `{5, 0x19034}`, which decodes to nothing.

## 2. SOLVED: all 392 globals are recoverable by name

`value_ptr` targets are structs whose members are frequently
`{count: u4, array_ptr: u4, tag: u4}` length-prefixed arrays, packed back to
back. Feeding all 392 `key_hash` values through
`research/tools/dc_hash_crack.py` against the disc's own `dc1/*.dci`
compiler-symbol corpus resolves **392 of 392** - the entire table of contents,
no misses, no guessing. Reproduce:

```sh
DISC=".../PS3_GAME/USRDIR/build/main"
python3 research/tools/dc_dir.py --extract-from "$DISC/bin.psarc" \
    --entry dc1/net.bin -o /tmp/net.bin
python3 research/tools/dc_dir.py /tmp/net.bin -p "$DISC/bin.psarc" \
    -w "$DISC/paks.txt" -w "$DISC/pak23.txt" --list
```

A 100% hit rate on 392 independent 32-bit hashes is itself the proof that the
record layout in §1 is right - a one-word-shifted walk resolves essentially
nothing.

Globals immediately relevant to open protocol items:

| symbol | key_hash | value | what it is |
|---|---|---|---|
| `*net-money-info*` | `0xc85e199d` | `0x52f4` -> `{99, 0x2665c}` | cumulative threshold ladder (§3) |
| `*net-emblem-layers-base/-frame/-parts*` | `0xe2311588` / `0xc7f8567c` / `0x03ffae77` | all three -> `0x1dd24` -> `{193, 0x2be58}` | the emblem shape catalog (§5) |
| `*net-emblem-colors*` | `0xbcbbdfbd` | `0x50fc` -> `{64, 0x15e94}` | the emblem colour swatches (§4) |
| `*net-taunts*` | `0xb2b6e512` | `0x4f88` -> `{11, 0x1a740}` | the gesture catalog (§5) |
| `*net-stats*` | `0x921da350` | `0x488c` -> `{40, 0x9c18}` | the net-stat event registry (§7) |
| `*unlock-list*` | `0xe2e8998e` | `0x583c` -> `{284, 0x2460c}` | unlock ids, 28-byte records |
| `*net-rank-version*`, `*dlc-version*`, `*net-global-levels*`, `*net-hdd-levels*`, `*net-weapon-upgrade-level-costs*`, `*net-default-{challenge,deathmatch,elimination,objective}-tasks*`, `*net-{tdm,elim}-*-stat-rewards*`, `*net-kill-stats*` | - | - | present and addressable; not decoded here |

## 3. SOLVED: `*net-money-info*` is a 99-entry cumulative threshold ladder, and `rank_tier` is a hard 0 because of its first two entries

`{count: 99, array_ptr: 0x2665c}`, stride 4, signed:

```
idx  0   1     2     3     4      5      6      7      8      9     10
val  0  2000  4000  7000  12000  18750  27000  36750  48000  60750  75000 ...
```

Monotonic from 0 up to 2,640,000 by entry 47 and beyond - an earnings/level
ladder, exactly the shape `dc_table.md` predicted for a currency table and
never managed to see because it was reading the wrong array.

That settles the open question in `protos/common/member_data.ksy`'s
`rank_tier` doc. Re-disassembling `FUN_003c8e30` instruction by instruction
(01.00 EBOOT, VMA `0x3c8e30`-`0x3c8eec`, `objdump -D -b binary`) against the
real array:

```
3c8e44  lwz r9,-32756(r30)      ; global
3c8e48  lwz r9,120(r9)          ; global+0x78 = the override
3c8e4c  cmpwi cr7,r9,0
3c8e50  addi r11,r9,-1          ; result = override - 1
3c8e54  bne  cr7,0x3c8ed8       ; ...and return it if nonzero
3c8e58  lis r3,-14242 / ori r3,r3,6557   ; 0xC85E199D
3c8e60  bl  0x9fa9f4            ; DC hash registry lookup -> r3 = value ptr
3c8e68  li  r11,0               ; result = 0
3c8e70  beq cr7,0x3c8ed8        ; lookup failed -> return 0
3c8e80  lwz r9,0(r7)            ; count      (= 99)
3c8e84  addi r8,r9,-1           ; count-1
3c8e88  mtctr r9
...
3c8ea0  lwz r9,4(r7)            ; array_ptr  (= 0x2665c)
3c8ea4  add r9,r0,r9            ; + i*4      (4-byte stride, overlapping reads)
3c8eac  lwz r0,0(r9)            ; a = array[i]
3c8eb0  lwz r9,4(r9)            ; b = array[i+1]
3c8ebc  bgt cr7,0x3c8ec4        ; a > 0  -> keep scanning
3c8ec0  bgt cr6,0x3c8ed8        ; a <= 0 && b > 0 -> return current result
3c8ec4  slwi r0,r10,2 / mr r11,r10 / addi r10,r10,1 / bdnz
3c8ed4  mr r11,r8               ; fell off the end -> count-1
```

Trace it on the real data: the loop is entered at `0x3c8ec4` with `i=0`, so
`result=0` and `r0=0`; the first body iteration reads `a = array[0] = 0` and
`b = array[1] = 2000`. `a > 0` is false, `b > 0` is true, so it returns
immediately with `result = 0`.

**`FUN_003c8e30` returns a hard 0 for the shipping table unless the override
at `global+0x78` is set.** This is not an inference - it is the only path the
data allows. And it matches the capture exactly: `rank_tier` is `0x0000` in
**855/855** live `0x13a` frames (re-counted 2026-08-20 from
`server/logs/wire.jsonl`, up from the 852 of the previous pass).

So the field is neither "money-derived" nor "rank-derived" on the DC path -
the DC path is inert. The only producer of a nonzero `rank_tier` is
`*(global+0x78)`, whose writer is **not traced**; that is the remaining open
piece, and it is a much smaller one than "what does the DC table mean". The
field name should still not be changed off this finding alone.

## 4. SOLVED: the emblem colour swatches, all 64 RGBA values

`*net-emblem-colors*` -> `{64, 0x15e94}`, stride 16, four big-endian f32
(r, g, b, a). Alpha is `1.0` in all 64. Full table:
`research/notes/2026-08-20-emblem-color-catalog.tsv`.

The layout independently confirms the already-solved
`color_index = row*8 + col` grid formula (`research/notes/2026-08-19-emblem-
name-resolver-and-dc-catalog.md` §10c): the 64 entries fall into eight clean
runs of eight, each run one hue ramped light-to-dark.

```
row 0  #EBEBEB #DADADA #B6B6B6 #919191 #6D6D6D #484848 #242424 #101010   grey
row 1  #E7C5C5 #EBAAA7 #EB7F7F #EB3F3F #DA1717 #942626 #4F1E1E #251010   red
row 2  #E7D4C5 #EBC8A7 #EBB07F #E78C3F #DA6F17 #945726 #4F341E #251910   orange
row 3  #E7E5C5 #EBEAA7 #EBE67F #EBE23F #DAD017 #948E26 #4F4C1E #252310   yellow
row 4  #D3E7C5 #C1EBA7 #ABEB7F #86EB3F #68DA17 #549426 #294F1E #1A2510   green
row 5  #C5E7E1 #A7EBE1 #7FEBD8 #3FEBCC #17DAB6 #26947F #1E4F45 #102520   teal
row 6  #C5D6E7 #A7DBEB #7FB6EB #3F97EB #177CDA #266094 #1E384F #101C25   blue
row 7  #D0C5E7 #C0A7EB #A27FEB #773FEB #5517DA #482694 #3A2271 #2D1E4F   purple
```

The 2026-08-19 note's §3/§10c "nested-DC-structure wall" is gone: the wall was
the one-word record misread, not any nesting.

## 5. SOLVED: `equipped_gesture_id`, all eleven values, without cracking the hash

`*net-taunts*` -> `{11, 0x1a740}`, stride 12:
`{taunt_id_hash, display_string_id, unknown_hash}`. Resolving word 1 through
`research/tools/text_table.py` against `text1.psarc`'s `2.networking` table:

| `equipped_gesture_id` | display name | word 2 |
|---|---|---|
| `0x0e69839d` | NONE | `0xed22a97d` |
| `0xd40e5495` | Fist Pump | `0x8f43b5a4` |
| `0xdd8c6ffb` | Knuckles | `0xcd47f77b` |
| `0xc70a2249` | Chest Pound | `0x7a9cb5f2` |
| `0xd94d724c` | Blow Smoke | `0xf1751261` |
| `0xce881927` | Salute | `0xbbae53e8` |
| `0xf6c7a49a` | Come Here | `0x1f610ac5` |
| `0x02d688fe` | Back Off | `0xaa4fe8e5` |
| `0xc3cb3ffe` | Neck Crack | `0xc1ad9766` |
| `0xca490490` | Bow | `0x6c9ad722` |
| `0xf206b92d` | Close Call | `0x38b02b1d` |

This is a byte-exact match, in order and with no leftovers, against the ground
truth that already existed in `protos/profile_21.ksy`: the six values captured
by controlled live edits (NONE, Fist Pump, Knuckles, Chest Pound, Blow Smoke,
Back Off) and the five names observed as locked-and-unselectable (Salute, Come
Here, Neck Crack, Bow, Close Call). Six independent live-verified pairs landing
on the right rows of an 11-row table found by an unrelated static route is
conclusive. `0xd94d724c`'s neighbour `0x328e4395` is also exactly the
"Blow Smoke" text key that `profile_21.ksy` had already cited and ruled out as
the id itself - it is the *sibling* field, not the id, which is now explained
rather than merely excluded.

Word 2 resolves in none of the four English `text1.psarc` categories; not
identified.

The same route re-derives the emblem shape catalog with a proper DC anchor:
`*net-emblem-layers-{base,frame,parts}*` all carry the **same** `value_ptr`
(`0x1dd24` -> `{193, 0x2be58}`), stride 12, `{name_hash, name_ptr, sub_ptr}`.
Dumping `name_ptr` gives 193 plaintext asset names, which match
`research/notes/2026-08-20-emblem-shape-catalog.tsv` at **193/193, zero
mismatches**. Two consequences:

* The live-tested "all four layers share one catalog, no per-layer offset"
  finding now has a static cause: the DC globals literally point at one array.
* The formula is simpler than recorded. Index 0 of the DC array is the literal
  string `"none"` - the sentinel is *in* the catalog, not outside it. So
  `catalog[shape_index]` is direct, and the "192-entry catalog indexed by
  `shape_index - 1`" phrasing in the 2026-08-19 note describes the same
  mapping with the sentinel peeled off by hand.

## 6. NOT SOLVED: the intra-table hash, but it is no longer load-bearing

The hashes *inside* these tables (`0xd94d724c` for Blow Smoke, `0x78e800eb`
for `frame-circle`) are **not** `crc32_mpeg2` and not any of ~50 stock
algorithms/variants tried (zlib CRC-32, all four reflect/init/xorout
combinations of seven CRC polynomials, FNV-1/1a, djb2/djb2-xor, sdbm, Jenkins
one-at-a-time, ELF, SAX, Adler-32, truncated MD5/SHA-1; each over the bare
name, uppercased, `*star*`-wrapped, NUL-terminated, and UTF-16 both endians).

What *is* established, from exact single-byte-difference tests on same-length
names within the shape catalog:

```
h("background-badge2") ^ h("background-badge3") = 0xF42BE268 ^ 0xF0EAFFDF
                                                = 0x04C11DB7   (= the CRC-32 poly)
h("background-badge3") ^ h("background-badge4") = 0xF0EAFFDF ^ 0xEEADAFDA
                                                = 0x1E475005   (= L(0x07), i.e.
                                                   x^32 ^ x^33 ^ x^34 mod P)
h("image-4star")       ^ h("image-5star")       agrees with the same linear map
                                                four bytes further from the end
```

so the construction is MSB-first, poly `0x04C11DB7`, forward byte order, byte
XOR'd into the high lane - the same family as `crc32_mpeg2`. But it is **not
globally GF(2)-affine over the name**: solving `h = A(crc32_mpeg2_0(name)) ^ K`
for a 32x32 matrix `A` and constant `K` is inconsistent on every one of the 32
output bits over the 193 pairs, and so is the weaker per-length-constant
variant fitted on same-length differences only. Something outside the visible
name string enters the message. No 256-entry CRC table exists anywhere in the
01.00 EBOOT (scanned, both LOAD segments), so the routine is bitwise, not
table-driven, and cannot be found that way.

This is now a curiosity rather than a blocker: every table above pairs the
hash with either a plaintext name or a text StringId, so id -> name resolution
is a table search. `research/tools/dc_dir.py` does it.

## 7. NEW LEAD: `*net-stats*` is the net-stat event registry

`{40, 0x9c18}`, stride 8, `{stat_id_hash, display_string_id}`. Entry 0's
`stat_id_hash` is `0x5c494554` - the exact "DC StringId" that
`protos/profile_21.ksy` cites for the P+0x1E3C ratio statistic and records as
"checked against text1.psarc ... NOT found in any of the four English category
files". It is not a text key at all; it is a `*net-stats*` **stat id**, and
the *display* string sits in the next word (`0x904a0c21` = "Downed Enemy").

Named entries (`2.networking`, then `2.common`):

```
 0 5c494554 Downed Enemy      13 acd2d064 Special Execution   27 5010c7c0 Retaliation
 3 5c21d694 Revive            14 6947bebc Pickup              28 688625b6 RUTHLESS
 4 7e7bedd4 Heal Ally         15 30b0d190 Craft Item          29 b4c27ec3 Supplies
 5 1b9ca468 Gave Item         18 c1e560e1 Execution           31 a12ddaf4 Won Game
 9 052fabfe Team Failed       19 3da6c914 Marked Target       32 46ea25e9 Lost Game
10 30b0d190 Craft Item        20 0be184bb Marked Target Downed 33 5f57a9ef WON ROUND
11 ae22a49d Melee Assist      21 dd39506e Rampage             34 4346c293 LOST ROUND
                              23 83e9b57e Multi-explosion     35-39         Parts x5
                              26 55f89ad1 Revenge
```

(entries 1, 2, 6, 7, 8, 12, 16, 17, 22, 24, 25, 30 have a `display_string_id`
that is absent from the English tables, or zero.)

**Deliberately not claimed:** that `profile.21`'s dense net-stat region indexes
*this* array. `docs/protocol/profile_21_record.md` records the in-record
formula `record[8 + (statIdx+581)*4]` and nothing here ties `statIdx` to a
`*net-stats*` row. What is now true is that the registry exists, is named, is
dumped, and contains the one stat id `profile_21.ksy` already cites - which is
a real lever the previous "no known hash to search for" verdict said did not
exist.

## 8. `search_window_lo` / `search_window_hi` are live-exercised after all

Unrelated to the DC work, from a fresh census of all 2,188 captured `0x135`
frames in `server/logs/wire.jsonl` (the previous pass looked at a smaller set):
the pair is **nonzero in 653 of 2,188 frames**, not "0 in all live captures".

Against the decompiled clamp in `protos/0x135_find_match.ksy`
(`lo = max(0, p5-p6)`, `hi = p5+p7`), the observed pairs decompose cleanly:

```
(397,397) x198   (337,457) x91    -> p5=397, and p6=p7=0 or p6=p7=60
( 29, 29) x179   (  0, 89) x82    -> p5=29,  p6=p7=0 or p6=p7=60 (lo clamped)
( 31, 31) x31    (  0, 91) x23    -> p5=31,  same
(365,365) x18    (305,425) x10    -> p5=365, same
(373,373) x15    (313,433) x6     -> p5=373, same
```

Every nonzero pair is either a point window at `p5` or `p5 +/- 60`, so `p6` and
`p7` are a single widen-by-60 step, and the client alternates a narrow and a
wide probe. Grouping by the connection's `0x12d` online id:

```
comradesean : centre 397 (x289), 365 (x28), 373 (x21)
mgnomad2    : centre  29 (x179),  44 (x82),  31 (x31), 45 (x23)
```

so `p5` is a **per-account quantity that climbs with play** - the two accounts
sit an order of magnitude apart and both grew across the capture window. Its
source is not identified: it is not `member_data.rank_value` (0/1/2/3 live),
not `rank_tier` (0), and not any board this project logs - `comradesean`'s
board values over the same period are 405:81, 404:51313-60516, 406:36712-39882,
407:53454, none near 397. Enough to retire "the window is disabled while
searching"; not enough to name the quantity.

## 9. What did not move

* `member_data.card_stat_2` / `card_stat_3` - re-checked on the current
  855-frame `0x13a` set (3 frames more than the last pass): still exactly
  `0x0000` in every one, at both offsets. Unchanged conclusion.
* `0x142 HostRank` - re-checked on all 241 captured frames (3 more than the
  last pass): every entry still ends in the unranked constant `0x0002`. Needs a
  ranked account; nothing on disc can supply one.
* "Host quit for cheating" - no occurrence of the string anywhere in
  `server/logs/`. Needs a live reproduction.
* `report-server` response grammar - `is-banned` requests appear 59 times in
  `server/logs/ticket_server.log`; the reply is still only ever our own stub's.
  Needs a retail capture.
* `0x136 attr_tail`, `member_slot_ec`, `0x134 trailing`, `np_id.opt/reserved` -
  no re-work attempted; the exhaustive whole-binary no-reader scans behind them
  stand.
* `stat_line`'s second `%s` - runtime-allocated, no file-backed content; a live
  memory read is still the only lever.
* `member_data.capability_flag` bit meanings - `*dlc-version*` and
  `*unlock-list*` are now addressable in `net.bin`, and `unlock-list`'s 28-byte
  records do carry a category byte (4 = taunt, 5 = emblem frame, 3 and 6 seen),
  but nothing in either table is a per-bit DLC-pack map, and no DLC-pack DC
  symbol appears among the 392 named globals. Still open.
* `0x13e`'s `flag`, `value_20`/`value_22`, `caller_arg_1c`, `flag_27` - the
  larger capture set does not change them: `value_20`/`value_22` are
  `1000`/`1000` in all 2,188 `0x135` frames, and `0x13e`'s `flag` still only
  ever takes the stale-or-boolean values already documented.

## Reproducing everything here

```sh
DISC=".../PS3_GAME/USRDIR/build/main"
T=research/tools
python3 $T/dc_dir.py --extract-from "$DISC/bin.psarc" --entry dc1/net.bin -o /tmp/net.bin
python3 $T/dc_dir.py /tmp/net.bin -p "$DISC/bin.psarc" -w "$DISC/paks.txt" \
        -w "$DISC/pak23.txt" --list                       # 392/392 named
python3 $T/dc_dir.py /tmp/net.bin --array 0x2665c 99 4    # money ladder
python3 $T/dc_dir.py /tmp/net.bin --array 0x15e94 64 16 --as f32          # colours
python3 $T/dc_dir.py /tmp/net.bin --array 0x2be58 193 12 --as hash+str    # shapes
python3 $T/dc_dir.py /tmp/net.bin --array 0x1a740 11 12 --as hash+strid \
        --text1 "$DISC/text1.psarc"                                       # gestures
python3 $T/dc_dir.py /tmp/net.bin --array 0x9c18 40 8 --as hash+strid \
        --text1 "$DISC/text1.psarc"                                       # net-stats
```
