# Member-blob bytes 10..13, global `0x01382082`, and the real head-item pipeline

Scope: what the 32-byte member-data blob actually means byte-for-byte on the
**consumer** side, what the live global `0x01382082` is, and what really drives
the in-match head/vanity look. Companion to
`2026-08-16-profile-and-userdata-reverse-engineering.md` §6 (producer map) and
`2026-08-17-character-customization-sync.md` (which this note corrects in two
material places).

---

## 0. Bottom line up front

1. **`0x01382082` is `NetGameManager + 0x4982` = the RECENTLY-PLAYED-LEVEL
   HISTORY.** The NetGameManager singleton is at **`0x0137D700`**;
   `NGM+0x4980` (s16) is the *current* level/map index and `NGM+0x4982..0x4989`
   is a 4-entry u16 ring of the *previous* level indices. It is shifted at
   match teardown (`FUN_003a6e78`, `0x003a6f84`–`0x003a6fa0`), which then calls
   the blob producer `FUN_003b15bc` on the very next line — which is exactly why
   the harvested bytes churn once per game. `0xFFFF` = "no such previous level".
2. **`blob[10..13]` is therefore `recent_level[0]` and `recent_level[1]`
   (2 × BE u16), NOT loadout item-ids and NOT vanity.** Its one and only
   consumer is `FUN_003a2310`, the host's **weighted-random map picker**: for
   every candidate level it walks all 12 member slots, and for each of the four
   bytes at `blob+10..13` that equals the candidate level index it subtracts a
   DC-configured penalty from that map's weight. It is a "don't replay the maps
   these players just played" heuristic. Nothing else reads those bytes.
3. **No byte of the member blob reaches character rendering.** All ten distinct
   `FUN_00ad2650` callers were traced: party grouping (`blob[0..7]`), roster
   sort key + title/colour (`blob[9]`), map-rotation penalty (`blob[10..13]`),
   four u16 lobby-card numeric cells (`blob[14/16/18/20]`), and the
   `[%s] %s` roster-name formatter. **The blob cannot explain the hat symptom.**
4. **The head/vanity pipeline is `game/net/custom-player-manager.cpp`
   (`0x0033f8e0`–`0x00346a24`), and it is driven by the PERSISTED PROFILE, not
   by anything on our wire.** Six equipped item ids live at
   **`P+0x670, 0x674, 0x678, 0x67C, 0x680, 0x684`** (u32 each), the survivor id
   at `P+0x66C`, palette at `P+0x688`/`P+0x68C`, faction at `P+0x1ADC` — all
   inside the 0x5000-byte `profile.21` record. When that block is empty the
   builder falls into two fallbacks: unknown item id → `FUN_0033ff54` returns
   **index 0** (first item in the DC array), and the base survivor is chosen by
   **`rand() % availableCount`** (`FUN_00340a6c` / `FUN_00340998`,
   re-run by `FUN_003433d0`). **That is the "different/random head every game,
   on my own screen too" symptom.**
5. **SUPERSEDED by §6e — read §6e first, then §6.** Both real end-of-session
   `profile.21` files were decoded: they DO round-trip and both
   customization blocks are populated, and **both persist `P+0xA28 == 1`**. That
   ground truth **FALSIFIES** §6b's "mgnomad2 fell into the randomise arm": both
   are on the deterministic NORMAL arm, the EBOOT never resets the latch to 0,
   and the randomise arm is symmetric across the two accounts so it cannot
   produce the observed asymmetry. §6e gives the corrected model: the head
   symptom is a **deterministic `FUN_0033ff54` item-resolution failure**
   (mgnomad2's equipped item StringIds are not present in his built character's
   DC item arrays → default model), and the "random every game" component is a
   DC/unlock-store effect, not the character randomiser. Resolving it needs a DC
   dump of char array `0xBD3BB3B9`.

---

## 1. Global `0x01382082`: identity, writers, readers

### 1a. It is a *field*, and the enclosing object is the NetGameManager. Confidence: high.

`0x01382082` is a `.bss` address (`SECTION29`, `0x01323200`–`0x015282F7`,
`initialized=false`), so it is never a literal in the image — it is reached
through the per-CU anchor idiom. The producer `FUN_003b15bc` loads it whole:

```
003b1788  lwz  r9,-0x7fe0(r30)   ; r9 = *(0x01269b18) = 0x01382082
003b178c  addi r11,r1,0x82       ; r11 = blob + 10 (blob base = r1+0x78)
003b17a4  lbz  r0,0x3(r9)
003b17ac  lbz  r10,0x0(r9)
003b17b0  lbz  r8,0x1(r9)
003b17b4  lbz  r9,0x2(r9)
003b17b8-c4  stb ... 0..3(r11)   ; blob[10..13] = 4 bytes at 0x01382082
```

The anchor slot at `0x01269b18` literally holds `01 38 20 82` (raw dump), so
`blob[10..13] = *(u8[4])0x01382082`. Ghidra's reference manager agrees:
`READ from 003b17ac → 01382082`, `003b17b0 → 01382083`, `003b17b4 → 01382084`,
`003b17a4 → 01382085`; the only other reference to `0x01382082` in the whole
image is the `DATA` ref from the anchor slot itself. **There is no direct
writer of `0x01382082` anywhere** — because writers address it as a struct
field.

The neighbour `0x01382080` has 14 readers, and every one of them is the same
shape:

```
003a55dc  lwz  r10,-0x7fd8(r30)
003a55e0  lhz  r0,0x4980(r10)     ; ← Ghidra resolves the EA to 0x01382080
003a55e4  extsh r9,r0
003a55e8  cmpwi r9,0x0 / blt      ; index >= 0
003a55f4  cmpw  r9,*(r3)  / bge   ; index < count
```
(same at `0x0035c504`, `0x0038c33c`, `0x0038c40c`, `0x0038e73c`, `0x00397ffc`,
`0x003a5a24`, `0x003a5a90`, `0x003a60bc`, `0x003aa604`, `0x003b2240`,
`0x003b8594`, `0x003e5d80`, `0x0035e0b0`).

So `0x01382080 = OBJ + 0x4980` ⇒ **`OBJ = 0x0137D700`**. That address is
already known in the corpus as the "player-array base" that leaks into
`blob[22..31]` — and `FUN_0039f75c` indexes it as `param_1 + i*0x920 + 0x40`,
i.e. it *is* the NetGameManager with its 0x920-stride player array. The
NetGameManager team array previously located at `+0x4B1C/+0x4B20`
(`2026-08-16-net-sm-server-lobby-dispatch.md`) belongs to the same object,
which cross-confirms the base.

Field map recovered this pass (immediate-displacement scan over the whole
`.text` for `0x4978..0x4998`):

| VMA | NGM offset | width | meaning | evidence |
|---|---|---|---|---|
| `0x0138207c` | `+0x497C` | u32 | current mode/variant id; set to `-1` whenever the level changes; `-1 → 0` normalisation at `0x0035e0a4` | `sth`/`stw` pair at `0x003a3224/0x003a3228`; writers `0x0035decc`, `0x0035e0ac`, `0x003b52a8`, `0x003a35c4` |
| `0x01382080` | `+0x4980` | s16 | **current level/map index** | 14 bounds-checked readers above; sole writer `0x003a3224 sth r4,0x4980(r3)` |
| `0x01382082` | `+0x4982` | u16 | **previous level** (`hist[0]`) | shift below |
| `0x01382084` | `+0x4984` | u16 | **level before that** (`hist[1]`) | shift below |
| `0x01382086` | `+0x4986` | u16 | `hist[2]` | shift below |
| `0x01382088` | `+0x4988` | u16 | `hist[3]` | shift below |

### 1b. The writer: a 4-deep shift register, run at match teardown. Confidence: high.

`FUN_003a6e78(NGM)` — the only code in the image that touches `0x4982`–`0x4988`:

```
003a6f84  lhz r0,0x4986(r28)      003a6f94  sth r0,0x4988(r28)
003a6f88  lhz r9,0x4984(r28)      003a6f98  sth r9,0x4986(r28)
003a6f8c  lhz r11,0x4982(r28)     003a6f9c  sth r11,0x4984(r28)
003a6f90  lhz r10,0x4980(r28)     003a6fa0  sth r10,0x4982(r28)
003a6fa4  bl  0x003b15bc          ; ← the member-blob producer, immediately after
```

Decompiled, the same function also resets `NGM+0x5894..0x58A4`, `+0x4970/4974`,
`memset(NGM+0x4B28,0,0x20)`, `+0x49DC=1`, `+0x4990=+0x498C=-1`, `+0x49EC=0`,
`+0x4AF0=+0x4AF4=0` — i.e. it is the **end-of-match / leave-level teardown**.
Sole caller: `FUN_003ef024` (task-manager-online band).

That single `bl 0x003b15bc` is the mechanism behind every live observation:

* **churn per game** — the history shifts, then the blob is rebuilt and
  re-pushed to both room objects via `FUN_00ad1fc0(room, blob, 32)`.
* **`hist[1]_new == hist[0]_old`** — mgnomad2's harvested
  `00 12 00 14` → `00 0e 00 12` is exactly `hist[1] ← hist[0]`.
* **`ff ff ff ff` on a fresh boot / after a client restart** — `NGM+0x4980` is
  `-1` ("no level") until `FUN_003a31dc` sets one; the shift propagates
  `0xFFFF` into the ring. `FUN_0035e06c` even has the guard
  `if (*(short*)(NGM+0x4980) < 0) FUN_003a31dc(NGM,0,0,0xc);`.
* **both players often identical** — they played the same maps. (This is *not*
  load-bearing evidence, but it is now an explained coincidence rather than an
  anomaly.)

The level-index setter is `FUN_003a31dc(NGM, levelIdx, pSettings, 0xC)`
(`0x003a31dc`): on a change it writes `sth r4,0x4980(r3)` and `stw -1,0x497c(r3)`,
resets `+0x49C4/49C8/49CC/49D0/4998/499C`, then looks the level up in the DC
array `StringId(0x3B9A067D)` (stride `0x70`) and copies five u32 game-rule
words into `NGM+0x4B08..0x4B18`. Called from `FUN_0035de3c` with
`(short)*(param_1+8)` — the level id off the net message that starts a match.

### 1c. The consumer: the host's weighted-random map picker. Confidence: high.

`FUN_003a2310` (`0x003a2310`–`0x003a31d8`) is the only reader of
`blob[10..13]`. Structure:

```
003a2454  ... outer loop over the candidate list
003a247c  bl  0x009fa9b8 (0x3B9A067D)   ; DC level array, stride 0x70
003a24c4  cmpw r0,r29 / beq             ; resolve candidate name-id -> level index
003a24fc  or   r27,r29,r29              ; r27 = candidate LEVEL INDEX
003a25a8  bl  0x00ad2b14                ; per-room capability mask
003a25b0  lwz r0,0x14(r29) / and        ; &= level record's requirement flags
  inner: r28 = 0 .. 0xB                  ; 12 member slots
003a2600  bl  0x00ad1c24                ; member by index
003a261c  bl  0x00ad2650                ; that member's 32-byte blob (NULL-checked)
003a2638  li  r0,0x4 ; mtctr            ; k = 0..3
003a264c  lbz r0,0xa(r9)                ; blob[10 + k]
003a2650  cmpw r0,r27                   ; == candidate level index?
003a265c  lwz r9,0x70(r31)              ; DC penalty
003a2660  subf r0,r9,r0                 ; weight -= penalty
003a267c  lwz r9,0x74(r31) / clamp to minimum
003a2694  add r15,r15,r9                ; accumulate total weight
003a26b8  bl  0x00a16240                ; rand -> weighted pick
```

Two footnotes worth recording:

* The producer stores two **u16s** but the consumer compares **bytes**. For
  level indices < 256 the low byte carries the value and the compare works; the
  high byte (`0x00`) will spuriously match candidate level index `0`. That is an
  original-game quirk, not something our relay causes.
* `FUN_00ad2b14` (which wraps `FUN_00ad2768`) supplies the mask ANDed with the
  level record's `+0x14`. This is the path `blob[8]` feeds; not chased further
  this pass.

**Verdict on task 1: `blob[10..13]` = recently-played level indices. The
existing field names `loadout_slot_0` / `loadout_slot_1` in
`protos/common/member_data.ksy` and "equipped loadout item-ids" in the profile
note §6 are WRONG and should be renamed `recent_level_0` / `recent_level_1`.**

---

## 2. Complete consumer map of the 32-byte blob

`FUN_00ad2650(room, member)` re-verified in full (offsets differ from the
sibling note's convention; these are off the decompile):

```c
if (*(s64*)(room+0x10) == 0) goto local;                 // no room id -> local
for (i=0..11) { slot = room + i*0x180;                    // member slot stride 0x180
    if (slot[0x748] && FUN_00e459bc(slot+0x668, member)==0) break; }  // find member
for (j=0..11) { if (slot_j[0x748] && *(int*)(slot_j+0x750) == *(int*)(room+0x19EC))
    { if (found == slot_j) goto local; break; } }         // is it me?
ptr = found+0x764; len = *(int*)(found+0x760);            // remote path
local:  len = *(int*)(room+0x19F8); ptr = room+0x19FC;    // local path
if (len != 0x20) return NULL;                             // 0x00ad2734
return ptr;
```

Callers (Ghidra: 13 call refs, 10 distinct functions) and what each reads:

| caller | blob bytes used | role |
|---|---|---|
| `FUN_00ad2768` (`0x00ad2898`) | `blob[9]` | roster list builder: `blob[9]` is the sort key (overridden by a vtable rank getter when that returns ≠ −1); local member's key is then stamped into every row before `FUN_00ad1cd8` sorts |
| `FUN_00ad2b14` (`0x00ad2b60`) | — (wraps the above) | returns the room-wide capability mask used by the map picker |
| `FUN_003a2310` (`0x003a261c`) | `blob[10..13]` | **map picker penalty** (§1c) |
| `FUN_003b6dfc` (`0x003b71d4`) | `*(u64*)blob` = `blob[0..7]` | copies the party id into a list row at `+0x10`; groups the roster by party |
| `FUN_003c203c` (`0x003c2310/2770/2ac0/2af4`) | `*(u16*)(blob+0xE+idx*2)` → cell type `0x2C`; `blob[9]` → `FUN_0039c69c(..., blob[9]-1, 0)` + colour `0x80000000\|rgb` | lobby/roster **card** cells and title/colour |
| `FUN_003bab9c` (`0x003bad4c/0x003bae18`) | same `*(u16*)(blob+0xE+idx*2)`; blob passed to `FUN_00ad15b0` | second roster/card widget |
| `FUN_0039f75c` (`0x0039f9ec`) | blob passed **only** as arg 3 of `FUN_00ad15b0` (the `[%s] %s` name formatter) | per-player setup called from `assign_team` Execute `0x0038e814`; writes name/NpId into the player entry (`+0xA8/+0xE8/+0x128/+0x3C8`) — **no model, no vanity** |
| `FUN_003a482c` (`0x003a4998`) | return value discarded | — |

So, per blob field:

| bytes | meaning | reaches |
|---|---|---|
| 0..7 | party id | roster grouping (`FUN_003b6dfc`) |
| 8 | capability/session bit | `FUN_00ad2768/2b14` → map-picker mask |
| 9 | title/badge index (`P+0x303`) | roster sort key, title name + name colour |
| 10..13 | **recent level indices** | map picker only |
| 14..21 | 4 × u16 card stats (`14/16` computed live, `18/20` = `P+0x654` verbatim) | lobby card numeric cells |
| 22..31 | leaked stack | nothing |

**Answer to task 2: no blob byte reaches in-game character rendering.
`assign_team`'s use of the blob is the roster-name string, nothing more.**

---

## 3. The real head-item / vanity pipeline

### 3a. Correction: the "no code references to cosmetic strings" finding was an addressing error. Confidence: high.

`research/strings/strings_ascii.txt` lists **file offsets**, not VMAs
(`VMA = file_off + 0x10000`, per `tools/eboot_analysis/eb.py`'s segment map).
`2026-08-17-character-customization-sync.md` §1a quoted those offsets as VMAs
and concluded "zero refs" — the scan was looking at the wrong addresses. At the
corrected VMAs the references exist:

| string | file off (as listed) | **VMA** | referencing functions |
|---|---|---|---|
| `emblems/%s` | `e69658` | `0x00e79658` | `FUN_00345038`, `FUN_0034527c`, `FUN_003456dc` |
| `emblems/spray-01` | `e69668` | `0x00e79668` | `FUN_00345a0c`, `FUN_003456dc` |
| `emblems/emblem-16-drips` | `e69680` | `0x00e79680` | `FUN_0034640c`, `FUN_00345a0c`, `FUN_003456dc` |
| `%s/badges/%s` | `e6e2f8` | `0x00e7e2f8` | `FUN_003d1178` |
| `DrawEmblem` | `e7c6c0` | `0x00e8c6c0` | `FUN_005f8d3c` |
| `Skins...` / `Helmets` / `Team 0/1 Override` | `e6dc78/cb8/c88/c98` | `0x00e7dc78/dcb8/dc88/dc98` | debug-menu labels; item table at `0x0126a1a8..0126a1cc` |

### 3b. The module: `game/net/custom-player-manager.cpp`. Confidence: high.

String at VMA `0x00e79550`, referenced by `FUN_00340a6c`, `FUN_00340bd0`,
`FUN_00340e84`, `FUN_00340f80`, `FUN_00341344`, `FUN_0034279c`, `FUN_003433d0`.
Sibling asserts in the same block:

```
0x00e79528  %s/actor%i/%s.pak
0x00e79540  pSkeletonPart
0x00e79578  pModelnames
0x00e79588  pItemArray
0x00e79598  team >= 0 && team < NetInfo::kMaxNetTeams
0x00e795c8  pPalette
0x00e795d8  Missing palette for %s
0x00e795f0  More than %i models in custom slot
0x00e79618  pPart->m_modelNames->m_count <= DC::kSwappableSlotModelsPerSlot
```

### 3c. The local character build: profile → 13 swappable slots. Confidence: high.

`FUN_0034279c(cpm)` — rebuild the local player's custom character:

```c
faction = BE_u32(P + 0x1ADC);                     // asserted < 2 -> Hunters/Fireflies
charIdx = FUN_00340e84(cpm, faction);             // index into DC 0xBD3BB3B9, stride 0x3C
FUN_00341344(&desc, cpm, *(x+0x1724), charIdx, faction);   // build 16-byte descriptor
for (slot = 0; slot < 0xD; slot++) {              // 13 swappable slots
    rec = FUN_00340088(cpm, charIdx, desc[1], slot, desc_sel[slot], 1);   // jump table, slot<0xD
    memcpy(cpm + slot*0x40 + 0x1248, rec_models, 0x40 * n);               // n <= 5 model records
}
```

`FUN_00341344` is where the *equipped items* enter, all from the profile record
`P` (`FUN_003cb89c(NetPlayerData + screen*0xF158)`), read as unaligned BE u32s:

| profile offset | width | meaning | evidence |
|---|---|---|---|
| `P+0x654` | u32 | first word of the customization block — **the value copied verbatim into `blob[18..21]`** | `0x003b1714` (producer), `0x0034d52c`, `0x003be860` |
| `P+0x66C` | u32 | survivor id — linear-searched in the character record's list at `+0x0C`, giving `desc[1]` | `0x0034185c` |
| `P+0x670,674,678,67C,680,684` | 6 × u32 | **equipped customization item ids** → `FUN_0033ff54(cpm, charIdx, slot, itemId)` → `desc[2..7]` | loop at `FUN_00341344`, `iVar17 = 2..7`, `P + 0x660 + i*4 + 8` |
| `P+0x687` | u8 | `desc[7]` | `0x00341558` |
| `P+0x688`, `P+0x68C` | 2 × u32 | palette / tint | `0x0034157c`, `0x003415b8` |
| `P+0x1ADC` | u32 | **faction / team** (`0` or `1`) | asserted by `FUN_00340e84/00340a6c/00340f80/00341344` against `team >= 0 && team < NetInfo::kMaxNetTeams` |

This block sits inside the persisted 0x5000-byte `profile.21` payload; the
profile note §5 already flagged `0x0654-0x068F` as a "densely populated u32
region" without naming it — **it is the character-customization block**.

### 3d. The two fallbacks that produce "random every game". Confidence: high for the mechanisms, medium for which one fires live.

* **Unknown item id → default item.** `FUN_0033ff54` handles only slots
  `2`, `3`, `4` (from the character record's `+0x10/+0x14/+0x1C` item arrays,
  stride `0x34`); it linear-searches for `entry[0] == itemId` and **returns `0`
  if not found**. A zeroed/garbage profile item id silently becomes the DC
  array's first entry.
* **Random survivor.** `FUN_00340a6c(cpm, faction)` collects every DC character
  whose `+8 == faction` **and** passes the availability gate
  `FUN_003ec084(...)` (the unlock check), then returns
  `list[ rand() % count ]` (`FUN_0090c3b4`). `FUN_00340998` does the same for a
  sub-list. Cardinality decides the behaviour: **0 or 1 available → stable;
  ≥ 2 available → a different character every rebuild.**
* **When the randomiser runs.** `FUN_003433d0(cpm, idx)` calls
  `FUN_00340998`, stores `rand % count` into `cpm+0x2310` / `cpm+0x2314` and the
  descriptor into `cpm+0x2308..0x232C`. Its only caller is `FUN_003487a4`
  (`0x00348948`), a lobby/menu state function gated on
  `BE_u32(P+0x2FC) != *(someState+8)` — i.e. it re-randomises whenever that
  session key changes, which is once per lobby/match cycle.
  `FUN_00341344` then *uses* the cached randomised descriptor
  (`cpm+0x2308..`) when `cpm+0x2331 != 0` **and** the requested faction equals
  the local profile faction, and only otherwise rebuilds from the profile.
* Rebuild triggers: `FUN_00342cec`, `FUN_00342d20`, `FUN_00342d70`,
  `FUN_00314768` — all local, all on the single `cpm` singleton
  (`*(anchor-0x7f94)`). There is **no per-remote-player CustomPlayerManager**.

### 3e. Emblems are a separate, network-carried system. Confidence: high.

`FUN_003456dc` iterates 8 players via `FUN_003994ac(playerTracker, i)`, reads
**4 × u64 at `tracker + 0x8E4 + k*8`**, and for each of the 4 layers:

```c
idx   = layerByte % *arrayCount;                    // MODULO — never out of range
path  = sprintf("emblems/%s", array[idx].name);     // 0x00e79658
FUN_00ac6d80(texLoader, path);                      // preload
```
`FUN_00345a0c` / `FUN_0034640c` draw them, with the colour byte likewise
`% paletteCount` and `Missing palette for %s` as the failure string. Because
every index is taken modulo a live count, an emblem **always resolves to
something**, which is consistent with emblems rendering correctly for both
accounts live.

### 3f. Which P2P opcode carries what. Confidence: high for what it is NOT.

`player_info` (44) **does not carry vanity.** Deserialize `FUN_0040bce8` reads
8 pairs into `obj+0x14..0x1B` and `obj+0x1C..0x23`; Execute `FUN_0040c6ac`
feeds them to `FUN_003cee8c(tracker, i, a, b)` which stores
`a → tracker+0x8BC+i*4`, a timestamp `→ tracker+0x89C+i*4`, and
`b → tracker+0x564+i*4`. Those are consumed by `FUN_003d0ba0`, the function
carrying the `m_numAppliedBuffs < kMaxAppliedBuffs` assert — i.e. **8 booster
slots (id + level)**, matching `net-set-booster`, `kMaxNetUpgradeBoosters` and
opcode 76 `swap_booster`. The rest of `player_info` is name (256B), two 64-byte
strings, a float, a few selectors, and a 2 × (2 + 8) u32 stat table.

Remaining candidates for character/emblem transport, **not decoded here**
(deliberately, to avoid duplicating the parallel decode work):
* **`sync_players` (71)**, ctor `FUN_0040a840`, object size `0x330` — the
  host→joiner "here is everyone" bulk sync; the only event large enough to hold
  8 × (16-byte descriptor + 32-byte emblem).
* `debug_swap_part` (112), factory `0x00390b28` → ctor `FUN_0040994c`, size
  `0x40` — the dev-menu `Skins...` / `Helmets` part-swap channel, not used in
  retail flow.

---

## 4. Synthesis: why mgnomad2's own hat is wrong and random every game

**The member blob is not involved.** Nothing in §2 reaches a model, a mesh, or
a texture. Fixing the `0x13a` relay length will not change a single pixel of a
character; its only cosmetic-adjacent effect is that remote members' *level
history* is currently invisible to the host's map picker (`len != 32 → NULL`),
so maps repeat more than they should.

**What does drive it** is `P+0x654..0x68F` (+ `P+0x1ADC`) in `profile.21`, read
locally by the CustomPlayerManager to build the *local* avatar. That block is
persisted only if the client's `PUT` to S3 succeeds — which, per the profile
note §4, it currently never does (`s3.amazonaws.com` is not in the RPCS3
IP-swap list, so no PUT ever reaches us and nothing round-trips).

The asymmetry then follows from three independent switches, in order of
likelihood:

1. **Profile block populated vs empty.** The account whose progression started
   working (comradesean) has real item ids at `P+0x670..0x684` and a real
   survivor id at `P+0x66C` → `FUN_00341344` takes the deterministic
   profile branch and the same head renders every match. The account whose
   profile is empty/failed (mgnomad2) has zeros → `FUN_0033ff54` returns
   index 0 for every slot and the survivor comes from the randomiser.
2. **Availability-set cardinality.** `FUN_00340a6c` returns
   `rand() % count` over the characters that pass `FUN_003ec084`. `count <= 1`
   → stable; `count >= 2` → a new look every rebuild. A *partially* seeded
   unlock set is the worst case: enough entries to randomise, not enough state
   to pin a choice. This can invert naive expectations — the account with *more*
   unlocked content is the one that churns.
3. **The `cpm+0x2331` / faction-match gate** in `FUN_00341344` decides whether
   the cached randomised descriptor or the profile is authoritative; if
   `P+0x1ADC` (faction) is stale or zero for one account, the two accounts take
   opposite branches of that `if`.

Emblems are unaffected by all of this because they ride the tracker
(`+0x8E4`) with modulo-indexed lookups — hence "emblems render correctly for
both" while the head does not.

### 4a. Recommended server change

Complete the `profile.21` round-trip (profile note §4/§8): add
`s3.amazonaws.com` to the RPCS3 IP-swap list, accept and store the client's
`PUT` ciphertext verbatim, and serve it back on `GET`. That is the only lever
that makes `P+0x654..0x68F` stable across matches and restarts. Nothing in the
SessionManager protocol can substitute for it.

### 4b. Cheapest discriminating experiment (no client change, no new capture tooling)

`blob[18..21]` is `P+0x654` **verbatim** — the first word of the very
customization block in question — and we already receive it in every `0x13a`
and log it. Harvest it per account across a few matches and a restart:

| observation | conclusion |
|---|---|
| mgnomad2 `blob[18..21]` is `00 00 00 00` (or changes across matches) while comradesean's is stable non-zero | **hypothesis 1 confirmed**: mgnomad2's customization block is empty/not persisting → do the profile round-trip |
| both stable and non-zero, but the head still churns | fall to hypothesis 2/3: the randomiser is firing despite a populated profile; next step is the `FUN_003ec084` availability set and `cpm+0x2331` |
| both zero and only mgnomad2 churns | availability-set cardinality (hypothesis 2) — mgnomad2 has ≥2 candidate survivors, comradesean ≤1 |

A second, confirmatory probe: after the profile round-trip lands, `blob[14..15]`
(weeks/journeys, from `P+0x1E34/0x1E38/0x1E44`) should also stop reading `0000`.

### 4c. Documentation fixes this note obliges

* `protos/common/member_data.ksy`: rename `loadout_slot_0` → `recent_level_0`,
  `loadout_slot_1` → `recent_level_1`, and rewrite their docs
  (`0xFFFF` = no previous level; source = `NetGameManager+0x4982/0x4984`;
  consumer = the host's map picker `FUN_003a2310`).
* Profile note §6 row for `blob[10..13]`: "equipped loadout item-ids sourced
  from live global `0x01382082`" → "previous two level indices,
  `NetGameManager+0x4982/0x4984`". Also delete §5's "Not in the record: the four
  equipped loadout item-ids come from a live global" — the equipped *items* ARE
  in the record, at `P+0x670..0x684`; the live global was never loadout.
* Profile note §6's claim that `FUN_003a2310` performs "the loadout point-budget
  check" is wrong — that function is the map picker.
* `2026-08-17-character-customization-sync.md` §1a: the "zero code references"
  finding is void (file-offset vs VMA); MP cosmetics **are** implemented in the
  EBOOT, in `game/net/custom-player-manager.cpp`.

---

## 5. Confidence summary

**High**
* `0x01382082 = NetGameManager(0x0137D700) + 0x4982`; `+0x4980` = current level
  index, `+0x4982..0x4989` = 4-deep previous-level ring; shift at
  `0x003a6f84`–`0x003a6fa0` immediately followed by `bl 0x003b15bc`.
* `blob[10..13]` = `recent_level[0..1]`; sole consumer is the weighted-random
  map picker `FUN_003a2310` (`lbz r0,0xa(r9)` / `cmpw r0,r27` / weight penalty).
* Full consumer map of the blob; no byte reaches character rendering.
* `game/net/custom-player-manager.cpp` is the MP customization module and reads
  the equipped items from `P+0x670..0x684`, survivor from `P+0x66C`, faction
  from `P+0x1ADC`.
* `FUN_0033ff54` returns 0 (default item) for an unknown id;
  `FUN_00340a6c`/`FUN_00340998` use `rand() % count`.
* `player_info` (44)'s 8 pairs are **boosters**, not vanity.
* The strings-file offsets are not VMAs (`+0x10000`), invalidating the earlier
  "no cosmetic code" conclusion.

**Medium**
* *Which* of the three switches in §4 produces the live asymmetry. The §4b
  probe discriminates them.
* That `sync_players` (71) is the carrier of remote players' character
  descriptor/emblem (inferred from size `0x330` and elimination, not decoded).

**Not established this pass**
* The writer of `tracker+0x8E4` (the emblem source) — it is reached with a
  computed offset, so an immediate-displacement scan finds nothing.
* `FUN_00340088`'s 13-entry jump table (which slot is specifically the head/hat).
* `blob[8]`'s exact semantics beyond "ANDed into the map picker's capability
  mask via `FUN_00ad2b14`".

---

## 6. Reconciliation against the decoded `profile.21` ground truth (2026-08-17)

Both real end-of-session profiles were decoded. **Both round-trip
and both customization blocks are populated**, which falsifies the
"empty/non-persisting profile" branch of §4. The decoded values:

| field | comradesean | mgnomad2 |
|---|---|---|
| `P+0x66C` survivor | `0x638EF35A` | `0x638EF35A` (**identical**) |
| `P+0x670` | `93EA5D87` | `6A86861F` |
| `P+0x674` | `41ACAD8B` | `456DB03C` |
| `P+0x678` | `FD0E0860` | `0AE569A8` |
| `P+0x67C / 0x680 / 0x684` | `0` `0` `0` | `0` `0` `0` |
| `P+0x688 / 0x68C` palette | `0` / `0` | `0` / `0` |
| `P+0x1ADC` faction | `1` | `1` |
| `P+0x300` title | `0` | `0` |
| `P+0x1E34` matches A | `3` | `2` |

### 6a. (a) What `0x638EF35A` and the six hashes are. Confidence: high.

**Both are StringIds, and "3 of 6 populated" is structurally forced, not a
coincidence.** Verified in the raw disassembly of `FUN_00341344`:

```
; item loop, r29 = 2..7  (0x003414a4 - 0x00341534)
003414dc  addi r9,r9,0x660
003414ec  add  r11,r11,r9         ; r11 = P + r29*4 + 0x660
003414f4  extsw r4,r22            ; arg2 = charIdx
003414e8  extsw r5,r29            ; arg3 = slot index (2..7)
003414f8-0034151c  lbz +8..+0xb   ; arg4 = BE_u32(P + r29*4 + 0x668)
00341520  bl   0x0033ff54
00341530  stb  r3,0x0(r9)         ; desc[2 + (r29-2)]
```
`r29*4 + 0x668` for `r29 = 2..7` is exactly `P+0x670, 674, 678, 67C, 680, 684`.

`FUN_0033ff54(cpm, charIdx, slot, itemId)` **implements only slots 2, 3 and 4**:

```c
arr = ScriptManager(0xBD3BB3B9);                        // character array, stride 0x3C
if (slot==2) t = *(int*)(charIdx*0x3C + arr[1] + 0x10);
else if (slot==3) t = *(int*)(charIdx*0x3C + arr[1] + 0x14);
else if (slot==4) t = *(int*)(charIdx*0x3C + arr[1] + 0x1C);
else return 0;                                          // slots 5,6,7 are DEAD
list = ScriptManager(**(u32**)(t+4));                   // per-character item array, stride 0x34
for (i=0; i<list.count; i++) if (list[i].id == itemId) return i;
return 0;                                               // NOT FOUND -> index 0 = default item
```

So `P+0x670/674/678` are the **three live equipped-item StringIds** and
`P+0x67C/680/684` can never be read — which is precisely why both accounts show
exactly three populated slots. `FUN_0034279c` then maps
`desc[2] → engine slot 2`, `desc[3] → engine slot 3`, `desc[4] → engine slot 0`,
all other slots `0`; the head is one of those three.

`P+0x66C = 0x638EF35A` is the **persisted survivor/appearance-variant StringId**.
It is linear-searched in the DC list at `charRec+0x0C`, and the found index
becomes `desc[1]` (`li r11,0x0` @`0x00341494` → **`desc[1] = 0` if not found**).
`desc[1]` is then passed to **every one of the 13 slot resolvers** in
`FUN_0034279c`, so it controls the whole character mesh, head included.

Two facts follow directly, answering Q1 and Q3 (below):

* **`P+0x66C` IS the render survivor — but only on the profile branch.** It is
  byte-identical across the two accounts because **nothing in the EBOOT writes
  `P+0x66C`** (a whole-text store scan for `0x66C` finds no writer in the game
  band); it is written by the DC customization menu through the
  `net-tus-variable.cpp` named-variable layer. Both accounts therefore sit on
  the same default variant. **Identical `P+0x66C` means the profile branch
  cannot produce a per-account-different, per-game-changing survivor — so a
  client that visibly randomises is NOT on the profile branch.**
* **`FUN_0033ff54` has no unlock gate at all** (it has exactly two references in
  the image: the call from `FUN_00341344` and its `.opd` descriptor). Item
  eligibility is enforced *elsewhere and earlier* — see §6b.

### 6b. (b) The precise reason: the `P+0xA28` one-shot latch. Confidence: high on the mechanism, medium on it being live for mgnomad2 (one datum settles it).

`FUN_003487a4` — the lobby/clan-entry state function — contains a two-armed
branch on a profile `u32`, verified instruction by instruction:

```
003488fc  lbz r11,0xa28(r3)      \
00348900  lbz r9,0xa29(r3)        |  r9 = BE_u32(P + 0xA28)
00348908  lbz r0,0xa2a(r3)        |
0034891c  lbz r11,0xa2b(r3)      /
00348928  cmpdi r9,0x0
0034892c  bne  0x00348968                ; latch SET -> normal arm
  ; --- RANDOMISE ARM (latch == 0) ---
00348938  bl 0x00346d44(cpm2, 0)         ; randomise EMBLEM
00348948  bl 0x003433d0(cpm, 0)          ; randomise CHARACTER
00348960  stw r0(=1),0xa28(r3)           ; latch it
00348964  b  0x00348988
  ; --- NORMAL ARM (latch != 0) ---
00348968: bl 0x00344de4(cpm2, 0)         ; validate emblem
00348980: bl 0x0033f9b4(cpm, 0)          ; validate/REVOKE the six item ids
```

**`FUN_003433d0` (randomise arm) is exactly the reported symptom, both halves:**

```
003434ec  stw r28,0x8(r9)        ; P + 0x660 (faction 0) / P + 0x664 (faction 1) = chosen char id
003434f0  std r27,0x2308(r31)    ; r27 == 0  ->  desc[0..7] = 0  ==> ALL SIX ITEM SLOTS ZEROED
003434f4  stb r23,0x2308(r31)    ; desc[0] = charIdx
003434fc  bl  0x00340998         ; pick a variant
0034350c  stb r0,0x2309(r31)     ; desc[1] = that variant  <-- the survivor
0034358c  bl  0x0090c3b4         ; rand()
0034359c-003435ac  rand % count -> cpm+0x2310 / cpm+0x2314
```
`FUN_00340998` itself is `rand() % listCount` over the same `charRec+0x0C`
variant list. And crucially the randomised **variant is written only to
`cpm+0x2309` (RAM) — never to `P+0x66C`**, while the randomised **emblem *is*
persisted** by `FUN_00346d44`'s sibling path.

`FUN_00341344` serves that RAM cache verbatim whenever the override flag is up:

```
003413f0  lbz r0,0x2331(r24) ; beq -> profile branch
00341434  cmpw r0,r31        ; BE_u32(P+0x1ADC) != requested faction -> profile branch
0034143c-00341460            ; else: copy cpm+0x2308..0x232F (0x28 bytes) out verbatim
```
`FUN_00341b78(cpm, n)` is the setter for `cpm+0x2331` (`0x00341c04`), and it
refreshes the cache from the profile via `FUN_00341a00` first — so whichever of
`FUN_00341a00` (profile) or `FUN_003433d0` (random) ran **last** owns the cache.

**`FUN_0033f9b4` (normal arm) is the item unlock gate sought in Q3, and it
lives in the PROFILE, not in the render path:**

```c
for (i = 0x19A; i <= 0x19F; i++) {              // P+0x670 .. P+0x684
    id = BE_u32(P + i*4 + 8);
    if (id != 0 && !FUN_003ec084(unlockStore, /*kind*/0, id, 0))
        *(u32*)(P + i*4 + 8) = 0;               // REVOKE: zero the slot in the profile
}
id = BE_u32(P + 0x308);                          // one more gated field
if (id != 0 && !FUN_003ec084(...)) *(u32*)(P + 0x308) = 0;
```
`FUN_003ec084` → `FUN_003ea968` (find the DC unlockable record, stride `0x1C`,
matched on `+8 == kind` and `+0x10 == id`) → `FUN_003eac74` (walk its
requirement list, stride `0xC`, per-entry `FUN_003ead8c`, plus the DLC
entitlement check `FUN_003646c8`). If no record exists for the id,
`FUN_003ea968` returns 0 and `FUN_003ec084` returns **1 = allowed**. A global
debug byte at `+0xE2` disables all gating.

**Now put the ground truth against those two arms.** mgnomad2's three item ids
are still **non-zero** at end of session. If he had been running the normal arm,
`FUN_0033f9b4` would have run at every lobby entry and either (i) left them
alone — in which case `FUN_0033ff54` would find them and his hat would render —
or (ii) revoked them by writing `0`, which would show as zeros in the dump.
Neither matches "non-zero ids + wrong, randomising head". The **randomise arm**
matches all three observations simultaneously:

* his survivor is `rand() % variantCount` on **every** entry → different head
  mesh every game, on his own screen (local render reads the local cache);
* `desc[2..7]` are forced to `0` → `FUN_0033ff54(…, 0)` finds no entry → index
  `0` = the default model in each of the three live slots → the purchased hat
  never appears, and neither does a fresh account's default-unlocked hat if that
  is not literally item index 0;
* `FUN_0033f9b4` never runs, so his three item ids sit in the profile
  **untouched and unread** — exactly the dump we have;
* his **emblem still renders correctly** because the emblem randomiser
  (`FUN_00346d44`) persists its roll, whereas the character randomiser writes
  only `P+0x660/0x664` and keeps the variant in RAM.

comradesean, with the latch set, takes the normal arm: `FUN_0033f9b4` leaves his
three ids in place (they pass `FUN_003ec084`), `FUN_00341344` resolves them via
`FUN_0033ff54`, and his head renders correctly and identically every match. The
3-vs-2 match count is then incidental, not causal — the causal difference is a
single latched `u32`.

### 6c. (c) The decisive datum — already in the two decoded blobs

**Read `P+0xA28` (BE u32, plain offset `0xA20`) from both profiles.** No new
capture, no client change, no live session.

| result | conclusion |
|---|---|
| mgnomad2 `P+0xA28 == 0`, comradesean `!= 0` | **Confirmed.** mgnomad2 hits the randomise arm on every lobby entry: random survivor + all item slots forced to 0. |
| both `!= 0` | The latch is not it. Fall back to the item-scope explanation: `FUN_0033ff54` resolves item ids against `charArray[charIdx]`'s own arrays, so mgnomad2's three ids simply are not in the arrays of the character `FUN_00340e84(cpm, 1)` returns → all three fall to index 0. Next step is dumping DC array `0xBD3BB3B9` from the `.pak`. |
| both `== 0` | Both should randomise; the visible difference is then downstream of `cpm+0x2331` ordering (`FUN_00341a00` vs `FUN_003433d0` — whoever wrote the cache last). |

Two secondary fields worth pulling from the same blobs while there, all
`FUN_003433d0` / `FUN_0033f9b4` outputs:

* **`P+0x660` and `P+0x664`** (u32 each) — the per-faction chosen character-record
  id, written by `FUN_003433d0` at `0x003434ec`. Faction is 1 for both accounts,
  so `P+0x664` is the live one. Non-zero ⇒ the randomise arm has run at least once.
* **`P+0x308`** (u32) — the seventh gated customization field revoked by
  `FUN_0033f9b4`'s tail.
* **`P+0x2FC`** (u32) — the session key `FUN_003487a4` compares before all of
  this (`0x0034884c`); it is also force-zeroed at `0x003487f0` on one path.

### 6d. Fix, once the latch is confirmed

If `P+0xA28 == 0` for mgnomad2, the fix is **not** a protocol change — it is to
make the *write-back* of that latch survive. `FUN_003487a4` sets it at
`0x00348960` immediately after randomising, so it only persists if the client's
subsequent `PUT` of `profile.21` is accepted **and** the next `GET` returns that
newer object rather than a cached/older one. Concretely, on the S3 catcher:
serve back the most recent `PUT` body byte-for-byte per NpId, and confirm by
re-decoding the served object that `P+0xA28` is `1` before the next session
starts. A read-only or stale-serving S3 stub reproduces this symptom exactly
while leaving every other profile field looking healthy — which is why the
"profiles round-trip" observation and the symptom are not in conflict.

Two things this note explicitly does **not** claim: that the member blob is
involved (§2 stands — it is not), and that the item ids are progression-gated at
render time (`FUN_0033ff54` has no gate; the gate is `FUN_0033f9b4`, and it acts
by rewriting the profile, not by refusing to draw).

---

## 6e. CORRECTION (2026-08-17, second pass): the single-latch hypothesis is FALSIFIED

The check prescribed in §6c produced the decisive datum: **BOTH accounts persist
`P+0xA28 == 0x00000001`** (plain offset `0xA20`). Per the §6b table that lands
on "*The latch is not it.*" The "mgnomad2 fell into the randomise arm"
conclusion of §6b is **WRONG** and is retracted. This pass re-traced the full
branch and every writer; the corrected model:

### Q1 — the randomise/normal selection, and why a latched profile cannot randomise here

`FUN_003487a4`'s arm selection was re-read in full decompile **and** raw disasm
(`0x003488fc`–`0x00348988`). The condition is **solely** `BE_u32(P+0xA28)`:
all four bytes zero → randomise arm (`FUN_00346d44` emblem + `FUN_003433d0`
character, then `stw 1,0xA28`); non-zero → normal arm (`FUN_00344de4` +
`FUN_0033f9b4`). There is **no other input** to that branch. The `P+0x2FC`
"session key" block at the top of the function (`0x00348840`–`0x003488e0`,
zeroed at `0x003487fc` under the `+0x72` flag, compared against
`FUN_003888d4()+8`) drives only `bVar6` and the UI messages `0x506b0153` /
`0xda1f28d9` — it does **not** select the character arm. So the prior note's own
"only the latch" reading of this branch was correct; what was wrong was the
inference that mgnomad2 was on the randomise side of it.

Three independently-sufficient reasons a latched profile **cannot** be the
randomise source:

1. **Both are latched to 1** (ground truth) ⇒ both take the deterministic
   NORMAL arm. `FUN_003433d0` (character randomise) has **exactly one caller**
   — this arm (verified: `ListReferencesTo 003433d0` → only `0x00348948`).
2. **Nothing in the EBOOT ever resets `P+0xA28` to 0.** A whole-image store scan
   for displacement `0xA28` (decimal 2600) finds the profile latch written at
   **one** site only: `stw r0,0xA28(r3)` @ `0x00348960` (= 1). Every other
   `…,2600(rN)` store is either a stack spill (`rN == r1`) or an unrelated
   struct/enum-table slot (e.g. the constant tables at `0x2d3580`, `0x2d5354`,
   `0xa7fec0` that write sequential ids 110/112/313‑317). **A latched profile
   therefore stays on the normal arm for the entire process lifetime**; the only
   way to re-enter the randomise arm is to *load* a profile whose `P+0xA28` is 0,
   and both loaded profiles have it = 1.
3. **The randomise arm is symmetric across the two accounts.** Both are faction
   `1`; `FUN_00340e84(cpm,1)` (first DC char with `+8==1`) and the variant list
   it randomises over (`FUN_00340998` = `rand()%charRec[+0xC].count`) are
   identical *static DC data* for both. So even a counterfactual "both reset to
   0" would randomise **both** identically — it can never yield "mgnomad2
   randomises, comradesean is stable." The asymmetry is impossible to source
   from the randomise arm.

**The local in-match render is deterministic on the normal arm.**
`FUN_0034279c → FUN_00341344` (profile branch) → `FUN_00340088` (13-entry jump
table) contains **no `rand()`**: the first `bl 0x0090c3b4` in the whole module
is at `0x00340930`, inside `FUN_003407e0`. Every rand-using picker
(`FUN_003407e0`, `FUN_00340a6c`, `FUN_00340998`, `FUN_00340bd0`) is reachable
**only** through `FUN_0035a7dc`/`FUN_00341918` — a *separate* builder (see Q3),
never from the local deterministic character build.

### Q2 — the revoke inconsistency proves the items are legitimately unlocked

`FUN_0033f9b4` (re-decompiled) does the six-item loop FIRST
(`i = 0x19A..0x19F` ⇒ `P+0x670..0x684`, revoke on `!FUN_003ec084(store,0,id,0)`),
THEN a single tail check on `P+0x308` (same `kind=0`). mgnomad2's snapshot has
`P+0x308 == 0` (revoked) but `P+0x670/674/678` still populated. Only
`FUN_0033f9b4`'s tail zeroes `P+0x308`, so **mgnomad2 demonstrably ran the
NORMAL arm** (this is independent confirmation of the latch=1 ground truth), and
his three item ids **survived the revoke pass ⇒ they PASS `FUN_003ec084` ⇒ they
are legitimately unlocked.** `P+0x308` is a *different* unlockable id whose
requirement record evaluates false for him (a DLC/progression gate he doesn't
satisfy) — comradesean's `P+0x308 = 0xd40e5495` passes. **This proves the
failure is NOT the unlock gate; it is downstream in `FUN_0033ff54`'s DC-array
resolution.**

### Q3 — root cause and the one next step

Reconciling every fact (both latched→normal/deterministic; identical survivor
`P+0x66C`/charIdx; items populated-and-unlocked but different values;
`P+0x308` revoked only for mgnomad2; wrong-on-own-screen; emblem correct):

**Root cause (single, most likely): item-resolution failure in `FUN_0033ff54`.**
Both accounts resolve their three equipped item StringIds against the *same*
character `FUN_00340e84(cpm,1)` returns, via
`FUN_0033ff54(cpm, charIdx, slot 2/3/4, itemId)` = "return the index of the
entry whose `+0` matches `itemId` in `charRec[+0x10/+0x14/+0x1C]` (stride 0x34),
else **0** (default model)." comradesean's ids (`93ea5d87/41acad8b/fd0e0860`)
are present in those arrays and render; mgnomad2's ids
(`6a86861f/456db03c/0ae569a8`) are **not** present for that character ⇒ each of
his head/mask slots falls to index 0 = the character's default model ⇒ wrong
head, emblem unaffected (emblems ride the tracker with modulo lookups, §3e).

The **"different every game"** component is NOT the local deterministic build
(proven above). It is one of two DC-dependent effects, and the same DC dump
settles which:
* the lobby state-machine handler **`FUN_0035a7dc`** (state `0x11` in
  `FUN_0035cde0`) fills **every** player entry's `+0x410`/`+0x438` with a
  *fresh random* character descriptor each time that state is entered
  (`FUN_00340bd0(&d, cpm, faction)` twice; `FUN_00340bd0`→`FUN_003407e0` is
  `rand()%unlocked-per-slot`). This is a per-match random pool; if an entry
  whose real descriptor is empty/invalid falls back to `+0x410/+0x438`, it shows
  a new look each match. mgnomad2's invalid item resolution is exactly the
  "empty/invalid" condition; or
* `FUN_0033f9b4`'s revoke result oscillates across matches if the unlock/DC
  store is loaded racily at lobby-entry time (`FUN_003ec084` returns *allowed*
  when no record is found, so a not-yet-loaded store leaves the ids intact one
  game and revokes them the next), producing default-vs-resolved flip-flop.

Either way the discriminator is the **DC character array `0xBD3BB3B9`** and the
per-character item arrays, which live in the DC modules inside the net paks.

**Concrete next step (requires DC data — stated explicitly):** extract the DC
and check three things.
* **How:** `tools/psarc_crypt.py` unpacks the encrypted PSARCs
  (`net1.bin` at `.../dev_hdd0/game/BCUS98174DATA2/USRDIR/net1.bin`, and its
  `net10.bin` sibling — same Blowfish/HMAC scheme already validated in
  `2026-08-14-repack-rejection-investigation.md`). Inside, locate the DC record
  resolved by `ScriptManager StringId 0xBD3BB3B9` (the character array, stride
  `0x3C`; item sub-arrays at record `+0x10/+0x14/+0x1C`, stride `0x34`,
  `entry+0` = item StringId).
* **Check:** (i) which record is the first with `+8 == 1` (= `charIdx` for
  faction 1); (ii) whether mgnomad2's ids `6A86861F / 456DB03C / 0AE569A8` and
  comradesean's `93EA5D87 / 41ACAD8B / FD0E0860` are present in that record's
  `+0x10/+0x14/+0x1C` arrays (predict: comradesean's present, mgnomad2's
  absent); (iii) what `P+0x308` maps to (walk the unlockable table
  `FUN_003ea968` uses — stride `0x1C`, `+8==kind`, `+0x10==id` — for
  `id=0xd40e5495`) to confirm whether it is a rendered head item or an unrelated
  entitlement.
* If (ii) confirms mgnomad2's ids are simply absent for that character, the
  EBOOT-level truth is settled (no server/protocol fix helps — his persisted
  item ids don't belong to the character he's built as; this is a
  client-side/DC-menu authoring or a wrong-charIdx issue, not a transport bug),
  and the `s3.amazonaws.com` profile round-trip is *not* the fix for the head
  symptom.

**Cheapest live cross-check (no DC dump):** `blob[18..21]` is `P+0x654`
verbatim and is already logged from every `0x13a`; but for THIS symptom the
sharper probe is to watch whether mgnomad2's `P+0x670/674/678` values (or the
rendered head) change **between matches within one boot**. If they change, the
`FUN_0033f9b4` revoke-race / `FUN_0035a7dc` fallback (random) branch is live;
if they are stable-but-wrong, it is pure `FUN_0033ff54` mis-resolution (DC
authoring).

---

## 7. DC char-array id verification (net1.bin parse)

**Verdict: REFUTED.** All six persisted item StringIds — comradesean's three
*and* mgnomad2's three — are **present** in the character's item arrays. The
"mgnomad2's ids are absent → default" hypothesis is false. The symptom is
explained by a subtler fact (below): mgnomad2's ids resolve to **index 0**, the
same value the not-found path returns.

### Container format (confirmed by parse)

`research/net1bin/net1.bin` is a `DC00` archive, 0x454DE bytes:

```
+0x00 "DC00"        +0x04 u32 ver=1     +0x08 u32 0x43340
+0x10 u32 1         +0x14 u32 count=0x188 (392)   +0x18 u32 tocOff=0x1C
TOC[392] @0x1C, 12 bytes each = { u32 key (BE StringId, sorted asc),
                                  u32 typeId, u32 dataOffset (file-relative) }
```

`ScriptManager(key)` = TOC lookup → dataOffset. Array objects are
`{ u32 count, u32 elemBaseOffset }`.

### Resolution chain (validated end-to-end)

* char array `0xBD3BB3B9` → obj@0x5120 = `{count=69, recbase=0x243B4}`, stride 0x3C.
* char record for **faction 1 / P+0x660 = 0x3853C446 is record index 0** @0x243B4
  (the only record with that id). Both players use it, so both resolve against
  identical arrays — the *only* variable is the persisted StringId.
* Slot field at recRec+0x10/+0x14/+0x1C points to a 12-byte descriptor
  `{u32 cnt=1, u32 ptr, u32 type=0x88E3FE54}`; the per-slot item-array **DC key**
  is `*(u32*)ptr`. `ScriptManager(key)` → item array, entries stride 0x34,
  entry+0 = item StringId. This is exactly `FUN_0033ff54`'s
  `list = ScriptManager(**(u32**)(t+4))`.
* Slot→array keys for char 0x3853C446: slot2 `0x5854FB89` (39 entries),
  slot3 `0xC57086FD` (9), slot4 `0x49ECE8CD` (8).

The parse is corroborated by the fact that all 6 profile ids land in exactly the
three arrays in **profile-slot order** (id#1→slot2, id#2→slot3, id#3→slot4).

### Per-id presence table

| player.id | StringId | slot arr | index | note |
|---|---|---|---|---|
| comradesean #1 | 0x93EA5D87 | slot2 (0x5854FB89) | **9** @0x14170 | non-default |
| comradesean #2 | 0x41ACAD8B | slot3 (0xC57086FD) | **2** @0x22A98 | non-default |
| comradesean #3 | 0xFD0E0860 | slot4 (0x49ECE8CD) | **1** @0xE6F4 | non-default |
| mgnomad2 #1 | 0x6A86861F | slot2 (0x5854FB89) | **0** @0x13F9C | == index-0 default |
| mgnomad2 #2 | 0x456DB03C | slot3 (0xC57086FD) | **1** @0x22A64 | non-default |
| mgnomad2 #3 | 0x0AE569A8 | slot4 (0x49ECE8CD) | **0** @0xE6C0 | == index-0 default |

All six are present in the *correct* character's *correct* slot array. None is
absent. (Raw BE scans confirm every id also appears elsewhere in net1.bin — the
ids are legitimate DC content, not garbage. No id appears little-endian.)

### What this actually means

The resolver `FUN_0033ff54` returns an **index**, and that index drives the
model. Two paths both yield **index 0** (= the first/default item):

1. id **not found** → returns 0 (the original hypothesis), and
2. id **found at index 0** — i.e. the persisted id *is* the array's first item.

mgnomad2 is case (2), not case (1). His **slot2 (hat) id 0x6A86861F and slot4 id
0x0AE569A8 are literally the index-0 entries** of their arrays, so they correctly
resolve to index 0 = the default model. His slot3 id (0x456DB03C, index 1) is a
genuine non-default item. comradesean's three ids all resolve to non-zero
indices (9, 2, 1) → three distinct non-default models.

So the visible symptom (mgnomad2's hat renders as default) is real and matches
the data, but the cause is **not** a DC-authoring / lookup miss. mgnomad2's
persisted profile equips the *default (first-in-array) items* in the hat/head
slots. For his hat to render as a non-default model, his persisted profile ids at
`P+0x670/0x678` (slots 2/4) would have to hold StringIds that sit at a **non-zero
index** of arrays 0x5854FB89 / 0x49ECE8CD (as comradesean's do). The open
question is upstream: why his profile carries the index-0 item ids — most likely
the "randomise / reset-to-default" arm flagged in §5–6 (P+0xA28==0 latch) writing
the default items, not a resolution bug. This is consistent with the earlier
"stable-but-wrong" vs "random every game" test: the ids being valid-and-default
points at the profile writer, not `FUN_0033ff54`.

---

## 8. Bald + random reconciliation (2026-08-17, third pass) — the index-0 read was a category error

New live observation that re-opens §7: mgnomad2 spawns **BALD (no headwear at
all)** and **visibly DIFFERENT every match**, *on his own screen*, while his
persisted profile is a coherent, stable, latch=1 loadout (hat=Default idx0 =
industrial earmuffs / a real visible model, mask=Bandanna idx1, helmet=Riot
idx0 — three deliberate, correctly-persisted picks; DC parse 100% validated
against the 39/9/8 item name lists). §7 said "idx0 = earmuffs, so he
renders earmuffs stably." **He does not.** Bald+random cannot be a faithful
render of a stable profile, so the render is bypassing the profile. This pass
found the exact bypass and it is **not** what §7 assumed.
All addresses below re-verified against decompile + objdump this pass.

### 8a. Linchpin CORRECTED: `desc==0` and `id→index-0` are the SAME outcome — neither is bald

The reopening brief's premise ("a zeroed item slot renders NO ITEM/bald, whereas
a real id resolving to index 0 renders the earmuffs — two distinct outcomes") is
**mechanically false**, and settling that is the whole key. Traced the 13-slot
jump table `FUN_00340088` end to end:

* Table base resolves via `r2(TOC)=0x01305870` → `r30=*(0x012fde94)=0x0126fcf0`
  → table `*(0x0126fcf0-0x7fe0)=*(0x01267d10)=0x00340128` (the words right after
  the `bctr`). The 13 signed offsets give handlers: slot0 `0x003402ac`, slot1
  `0x003402a0`, slot2 `0x00340288`, slot3 `0x00340294`, slots4–11 share
  `0x003402b8`, slot12 `0x0034015c`.
* The **item-slot handlers (0,1,2,3)** all funnel to the common tail at
  **`0x00340488`**:

  ```
  340288  r9=charRec(r29); r0=*(r9+0x10)      ; slot2 item-array descriptor ptr
  340294  r0=*(r29+0x14)  ; slot3            3402a0 r0=*(r29+0x18) ; slot1
  3402ac  r0=*(r29+0x1c)  ; slot0
  340488  cmpwi r0,0; beq 0x3404b4            ; descriptor ptr == 0  -> return NULL
  340490  r9=*(r0+4); r3=*(r9); ScriptManager -> item MODEL array
  3404a8  r0=*(r3)          ; array count
  3404ac  cmpw r28,r0; blt 0x340408          ; selection < count -> take it
          (fall through)   -> 0x3404b4 return NULL   ; selection >= count -> NULL
  340408  r3 = &array[selection*0x34]         ; return the model record
  ```

  `r28` is the **selection = the descriptor byte (an ARRAY INDEX)**, `r29 =
  charArray[charIdx]` (the character, NOT the variant). So **`selection==0`
  returns `&array[0]` — the first model = "Default" = the earmuffs — a VISIBLE
  item.** The handler returns **no model (→ bald)** only when (i) the character's
  per-slot item-array pointer `charRec+0x10/0x14/0x18/0x1c == 0`, or (ii)
  `selection >= arrayCount`.

**Consequence.** Both the randomise arm's zeroed `desc[2..7]=0` *and* a profile
id resolving to index 0 hand `FUN_00340088` the identical `selection=0`, which
yields the identical `array[0]` = earmuffs. They are **not** distinguishable and
**neither is bald.** The render descriptor always carries **indices**, never
StringIds, so there is no "StringId 0 → empty" path in the local build at all.
§7's "idx0 = earmuffs" is the *correct* description of the profile branch — which
is exactly why the profile branch **cannot** be what mgnomad2 is running.

### 8b. What "bald + different every match" actually requires: a WRONG (random) CHARACTER

Because the item slots are keyed on `charRec` (the character), the *only* way the
head comes back NULL is that the character being rendered is **not** mgnomad2's
real one (record `0x3853C446`, whose slot arrays are the 39/9/8 the DC parse
validated). A different character's `charRec+0x10` may be 0, or his 39-entry hat
index may exceed that character's own hat count → NULL head = **bald**. A wrong,
*random* character every match also explains **different face/head every game**.
So the symptom is the signature of **rendering a randomly-chosen character**, not
of a zeroed hat slot. The random character comes from **`FUN_00340a6c`**
(`list = DC chars with +8==faction that pass the unlock gate; return
list[rand()%count]`). Two code paths call it, and the difference between them is
decisive:

1. **Boot latch arm `FUN_003433d0`** uses `FUN_00340e84` — the **FIRST** faction
   char (deterministic `0x3853C446`), and only randomises the *variant*
   (`desc[1]` via `FUN_00340998`), forcing `desc[2..7]=0`. Rendered, that is the
   *correct character* with a random variant and **earmuffs on the head** — it is
   NOT bald and NOT a different character. It also **persists** its roll into the
   profile (see 8d). So the latch arm fits the symptom *poorly*.
2. **Per-match pool `FUN_0035a7dc → FUN_00340bd0`** uses `FUN_00340a6c` — a
   **fully random character**, random variant, and random unlocked item indices
   per slot (`FUN_003407e0`). Rendered, that is a *different character every
   entry*, whose head slot frequently comes back NULL → **bald + different every
   match**. This fits the symptom exactly.

`FUN_0035a7dc` (the lobby/roster state handler) loops every player entry and
writes two fresh random descriptors into it every time the state is entered:
`FUN_00340bd0(&d,cpm,0)` → entry `+0x410..+0x430` (faction-0 pool),
`FUN_00340bd0(&d,cpm,1)` → entry `+0x438..+0x458` (faction-1 pool), and stamps
`+0x1dc = 0xffffffff`, `+0x1c4=+0x1c8=1`, `+0x201=1`, `+0x200=0`. The `+0x1dc =
-1` is the tell: it is the "no resolved character override — use the fallback
pool" marker. `FUN_00340bd0` builds the pool entry as random char
(`FUN_00340a6c`), random variant, and per-slot `FUN_003407e0` = "collect up to 16
*unlocked* items for this slot, return `list[rand()%count]`". **This is a live,
per-match `rand()` on every player, gated only by `*(x-0x7ff8)+0xb1 != 0`, and it
needs neither `P+0xA28==0` nor `cpm+0x2331`.** It is the strongest single fit for
bald+different-every-match.

The real per-player descriptor (the profile-faithful one) is written *elsewhere*,
by **`FUN_00341f34`** into the game object at `piVar5+0x12a…+0x132`, via
`FUN_00341344` (profile/cache), but only when its validity gate
`piVar5[0x14] == *(cpm+0x22f4)` holds. **If that gate fails for a player, his
real descriptor is never written and the render is left on the random `+0x410/
+0x438` fallback** — bald + random. The asymmetry (8e) is which player passes
that gate.

### 8c. `cpm+0x2331` cache lifecycle — it CANNOT shadow a latch=1 profile with random data on its own

Full writer/reader census of `cpm+0x2331` (= decimal 9009; the earlier note's
"stale-cache gate"):

* **Init/reset `FUN_0033f5xx` @ `0x0033f6b8`**: `stb r10(=0),0x2331` — the cache
  starts **disabled**. (Same routine sets `cpm+0x22F8=1`, `cpm+0x2410=0xFF…`,
  clears `+0x2330/+0x2332/+0x2408/+0x2409`.)
* **Setter `FUN_00341b78(cpm,v)` @ `0x00341c04`**: `stb r28(=v),0x2331`. When
  `v!=0` it FIRST calls `FUN_00341a00`, which **rebuilds the cache
  (`cpm+0x2308..0x232F`) from the PROFILE** (`FUN_00341344` profile branch). So
  *enabling* the cache always seeds it with **profile** data.
* **Readers**: only `FUN_00341344` @ `0x003413f0` (the serve-cache-vs-profile
  gate) and @ `0x0034164c` (its palette-copy tail). No other reader in the image.
* **The six `FUN_00341b78` callers**: `FUN_003b5a88`, `FUN_0035e06c`,
  `FUN_0034d09c`, `FUN_003883cc`, `FUN_003b588c` all pass **0** (disable, no
  reseed). Only `FUN_003c4b2c` (customization-menu event handler) can pass **1**,
  and only under event type `0x18` when `param_1[0xb]!=0` (a "preview/lock"
  flag) — and that path reseeds from the profile via `FUN_00341b78→FUN_00341a00`.

So the cache, whenever it is *turned on*, contains **profile** data, not random
data. The randomise arm `FUN_003433d0` fills `cpm+0x2308` but **never touches
`cpm+0x2331`**. The *only* way the RANDOM cache is ever served is a precise race:
`cpm+0x2331` already == 1 (someone entered the customization preview), THEN
`FUN_003487a4`'s randomise arm runs and overwrites `cpm+0x2308` while leaving
`cpm+0x2331`==1, THEN `FUN_0034279c`/`FUN_00341f34` serve it before the next
`FUN_00341b78`/`FUN_00341a00` reseeds. And entering the randomise arm still
requires **`P+0xA28==0`** at that instant. **Verified again this pass: the
`FUN_003487a4` arm branch is SOLELY on `BE_u32(P+0xA28)` (`0x003488fc`–`0x0034892c`);
there is no in-RAM side flag.** So "route to `FUN_003433d0` despite latch=1" is
**not possible within one process** — it can only happen if the profile that was
*loaded at that moment* had `P+0xA28==0`. The end-of-session snapshot (latch=1)
is a later state and does not prove what the boot GET returned. This is the *only*
way the cpm+0x2331/latch story can be live, and it makes it a **secondary**
candidate; even when it does fire it produces the *correct character* + earmuffs
+ a fixed (per-boot) random variant, i.e. it does not match "bald + a NEW look
every match" as cleanly as 8b's per-match pool does.

### 8d. New correction to §6a/§6b: the randomise arm DOES persist to the profile

Contrary to §6a/§6b ("nothing in the EBOOT writes `P+0x66C`; the random variant
lives only in `cpm+0x2309`"), the raw disasm of `FUN_003433d0` shows its tail
loop (`0x00343650`–`0x003437b8`, r26=0..7) writing straight into the profile
record `P = FUN_003cb89c(NetPlayerData + screen*0xF158)` via a *computed* offset
(`P + r27*4 + 8`, r27 = 0x198…): `P+0x668` = char-record id, **`P+0x66C` = the
chosen survivor StringId**, `P+0x670/0x674` = slot-2/3 model ids from
`FUN_00340088`, `P+0x678..0x684` = 0, `P+0x688..` = palette. The §6a
immediate-displacement scan missed it because the store uses a loop-computed
displacement, not `0x66C`. **Why this matters:** if the latch arm had run for
mgnomad2 it would have stamped a *random* survivor into `P+0x66C` and **zeroed
`P+0x678..0x684`** — but his snapshot has the SAME clean `P+0x66C=0x638EF35A` as
comradesean and three *non-zero* item ids (including a deliberate Bandanna at
`P+0x674`). So the latch arm demonstrably did **not** determine his persisted
profile — independent re-confirmation of §6e, and further reason to prefer 8b's
per-match pool (which persists nothing) over the latch arm.

### 8e. Why mgnomad2 and not comradesean (hypothesis) + the confirming capture

Under 8b the discriminator is `FUN_00341f34`'s validity gate
(`piVar5[0x14] == *(cpm+0x22f4)`) / the `+0x1dc == -1` fallback marker: comradesean's
player entry gets its real profile descriptor resolved and written to `+0x12a`
(so his stable loadout renders); mgnomad2's does not, so his entry stays on the
random `+0x410/+0x438` pool that `FUN_0035a7dc` refills every match. The most
likely runtime reasons the gate fails for exactly one account: (i) his
`profile.21` GET at boot/lobby-entry is late or returns an older/empty body, so
the resolve runs against a not-yet-populated `cpm+0x22fc`/char link while the
render has already fallen back; (ii) host-vs-joiner ordering (whoever's descriptor
is resolved from local profile vs awaited over the sync path); (iii) the
`P+0x308` revocation seen only on his account is a marker of a racy unlock-store
load at his lobby entry, and `FUN_003407e0`/`FUN_00341f34` both consult that same
store — a store that is empty one entry and populated the next flips resolve↔fallback.
This is a **runtime routing/timing** fault, not a data or persistence fault
(his saved loadout is coherent), and not the member blob (§2 stands).

**The one concrete next step — a single live capture that discriminates 8b from
8c and pins the cause:** in an RPCS3 session where mgnomad2 reproduces the bald
render, set two memory watches and grab one buffer:

1. **`cpm+0x2331`** and the **desc cache `cpm+0x2308` (16 bytes)** at match start.
   `cpm` is `*(anchor-0x7f94)` (the singleton used by `FUN_0034279c`); resolve it
   once, then watch. If `cpm+0x2331==0` at match start, the cpm+0x2331 shadow
   (8c) is **excluded** and the cause is the per-match pool (8b). If `cpm+0x2331==1`
   AND `cpm+0x2308` holds a char id ≠ `0x3853C446` / all-zero items, the
   randomise-cache shadow is live (8c) and the follow-up is the boot GET body.
2. **The rendered player entry's `+0x1dc`** (the `FUN_0035a7dc` fallback marker):
   if it reads `0xFFFFFFFF` at spawn for mgnomad2 but a small non-negative index
   for comradesean, the render is **confirmed** on the random fallback pool (8b),
   and the fix target is `FUN_00341f34`'s resolve gate, not the cache.
3. **The served-at-boot `profile.21` GET body for mgnomad2** (already capturable
   on the S3 catcher): decode `P+0xA28` and `P+0x670/0x674/0x678`. If `P+0xA28`
   arrives as `0` (or the body is empty/stale) at first render, the latch arm can
   run that session (8c precondition); if it arrives `1` with the real items, 8c
   is excluded and 8b is the sole cause.

Expected result given all static evidence: watch (1) shows `cpm+0x2331==0` and
watch (2) shows `+0x1dc==0xFFFFFFFF` for mgnomad2 → **root cause = the per-match
random fallback pool (`FUN_0035a7dc`/`FUN_00340bd0`) rendering because
`FUN_00341f34`'s profile-descriptor resolve did not populate his player entry**;
the server-side lever is to make his `profile.21` (and the DC unlock store) fully
present *before* first lobby entry, so the resolve gate passes on the first try.

### 8f. Corrections this pass obliges

* §7's "mgnomad2 correctly resolves to idx0 = default/earmuffs → renders
  earmuffs" is the *profile-branch* truth but is **not** what renders live; the
  live render is randomiser-driven (8a–8b). The open question §7 left ("why his
  profile carries index-0 ids") is now moot: his profile is a *deliberate*
  Default-hat pick and is fine; the fault is render-time routing.
* §6a ("nothing writes `P+0x66C`") and §6b ("random variant only in RAM") are
  **wrong**: `FUN_003433d0` persists `P+0x66C` and the item block via a computed
  offset (8d).
* The reopening brief's linchpin ("`desc==0`→bald vs id→idx-0→earmuffs are
  distinct") is **refuted** (8a): they are the same `array[0]`=earmuffs. Bald =
  NULL from a *wrong/random character*, which is why the cause is a randomiser,
  not a zeroed slot.

## 9. The resolve gate (why mgnomad2 fails) — CORRECTION: `FUN_00341f34` is the front-end loadout-preview apply, not the per-player in-match resolve

This pass decompiled `FUN_00341f34`, its gate, both operands, and every writer,
and the result **falsifies the §8b/§8e attribution** that `FUN_00341f34` is "the
per-player, in-match, profile-faithful descriptor writer, and mgnomad2 fails its
gate while comradesean passes." It is not a per-player function at all, it is not
in-match, and its gate cannot discriminate two live players in the same match.
All addresses re-verified against the decompile and the objdump this pass.

### 9a. What `FUN_00341f34` actually is (fully decompiled). Confidence: high.

`FUN_00341f34(cpm)` operates on **exactly one** object, not a loop over players:

```
piVar5 = *(int**)( *(cpm+0x22f0) + 4 );          // the live render entity via a stored handle
if (cpm+0x22f0 != 0 && cpm+0x22f4 != 0 && piVar5 != 0)
  if ( piVar5[0x14] == *(cpm+0x22f4) ) {         // <-- THE GATE  (piVar5+0x50 == cpm+0x22f4)
     rec  = FUN_003cb89c(*localPlayerNetData);   // LOCAL player's NetPlayerData record
     cid  = BE_u32(rec+0x1adc);                  // his survivor/character StringId
     v    = FUN_00340e84(cpm, cid);              // first-faction-char resolve of that id
     FUN_00341344(&desc, cpm, *(g+0x1724), v, cid); // build the profile-faithful descriptor
     piVar5+0x4a8 .. +0x4cf = desc;              // stamp it onto the render entity (40 bytes)
     (*piVar5->vt[0x470 or 0x46c])(piVar5,1); (*..)(piVar5,0); FUN_004571c0(piVar5); // refresh
     cpm+0x22f9 = 1;
  }
```

* `piVar5[0x14]` = byte offset **+0x50** on the render entity = the entity's
  **generation / liveness id**. Proven by the handle allocator `FUN_0047c5a4`,
  which builds every handle as the pair `{ entity+0x48 , entity+0x50 }` and also
  caches it into a global handle table (`*(tbl + slot*8) = entity+0x48`,
  `*(tbl + slot*8 + 4) = entity+0x50`). `+0x48` is the entity's handle-table
  back-pointer; `+0x50` is its generation stamp. This is Naughty Dog's standard
  weak-handle: to deref you follow `+0x48→+4` to the live object and compare its
  `+0x50` against the generation you stored; equal ⇒ still the same live entity,
  unequal ⇒ the slot was recycled and your handle is stale.
* `cpm+0x22f4` = the **generation snapshot** taken when the customization/loadout
  screen last recorded "the current preview entity" (see 9b). `cpm+0x22f0` = the
  matching `entity+0x48` handle pointer, from which `piVar5` is re-derived.
* **The gate is therefore a stale-handle / liveness guard**, *not* an identity
  match, faction match, member-slot match, or profile-loaded epoch. It reads:
  "is the render entity I recorded on the loadout screen still the same live
  object?" It passes while that entity is alive and fails once it is destroyed and
  its handle-table slot recycled (generation bumped).

### 9b. Who writes each operand. Confidence: high.

* **`cpm+0x22f0` and `cpm+0x22f4`** are written by **exactly two** sites in the
  whole image (verified by an image-wide scan for stores to displacements 8944 /
  8948):
  1. the **init/reset** routine at `0x0033f698` (`stwu r10=0,8944(r9)` then
     `stw r10,4(r9)`) — sets **both to 0**; and
  2. **`FUN_0033f4ac(cpm, E)`** @ `0x0033f4ac`: `cpm+0x22f0 = *(E+0x48)`,
     `cpm+0x22f4 = *(E+0x50)` (0 if `E==0`).
  `FUN_0033f4ac` has **one** caller: `0x00315dac`, inside **`FUN_00315af4`** — a
  **front-end loadout-screen** per-frame tick (it early-outs on the global pause
  flag, runs preview camera/animation math, and *rebuilds the preview render
  entity* via `FUN_0047c5a4`, storing the fresh `{ptr,gen}` handle into
  `screen+0xbbc/+0xbc0`, then records it into `cpm` via `FUN_0033f4ac`). So
  `cpm+0x22f4` is only ever the generation of **the loadout screen's preview
  mannequin**, captured on that screen — never anything set in a match.
* **`piVar5+0x50`** (the generation) is written by the render-entity lifecycle /
  allocator (the `FUN_0047c5a4` / `FUN_009e98cc` spawn path), bumped when a slot
  is reused. Not server-visible.
* **The two callers of `FUN_00341f34`** — `FUN_003188d4` and `FUN_0031896c` — are
  **virtual methods of the loadout-screen class** (their `.opd` descriptors sit in
  that class's method/vtable table at `0x012b9ca8` / `0x012b9cb0`, contiguous with
  `FUN_00315af4`@`0x012b9830` and the screen `update` `FUN_00316538`@`0x012b9840`;
  every entry is `funcptr,TOC=0x01305870`). Both are "set team / set faction on the
  local player, then re-apply his loadout to the preview": they write the local
  player's team byte at `NetPlayerData+0x1e40`, call `FUN_00341acc` (reseed the
  `cpm` desc cache from the profile), then `FUN_00341f34` (stamp the descriptor
  onto the preview entity if the handle is still live). The screen `update`
  `FUN_00316538` (which drives `FUN_00315af4`) is itself called from
  `FUN_0032241c`, the loadout-screen setup (aspect-ratio camera + skeleton
  attachment-node lookups) — an interactive full-screen character viewer.

### 9c. Why the gate cannot be the mgnomad2/comradesean discriminator. Confidence: high.

Both players run identical code on their own consoles, so any discriminator must
be data/timing. `cpm+0x22f4` has **no server-visible input** — no member id, no
NpId, no faction, no profile-GET-complete epoch, no unlock-store presence. It is
purely the generation of a client-local preview entity created by the local
loadout screen. Decisive corollary: **in a match, no code writes `cpm+0x22f0/22f4`**,
so they are either 0 (reset) or a stale front-end value, and `FUN_00341f34`'s own
outer guard (`*(cpm+0x22f0)!=0 && *(cpm+0x22f4)!=0`) makes it a **no-op in-match
for BOTH players equally**. Since comradesean nevertheless renders correctly
in-match, `FUN_00341f34` is demonstrably **not** the path that makes his in-match
render correct, and therefore **not** the path whose failure makes mgnomad2's
render wrong. §8b/§8e mis-identified it.

### 9d. Where the real in-match/lobby symptom comes from, and what remains to trace. Confidence: high for the mechanism, medium for the discriminator.

`FUN_0035a7dc` is the **lobby / party-screen member-list model rebuild** (reached
from `FUN_0035cde0` under UI state `0x11`). It loops every member entry, recreates
it via `FUN_0039f75c`, **copies the template fields from entry-0** (`iVar9 =
FUN_0039a380(list,0)`), and unconditionally writes a **fresh random preview pool**
to `+0x410/+0x438` plus the marker `+0x1dc = 0xFFFFFFFF` ("no resolved override —
use the random pool") on **every** entry. So immediately after this rebuild *all*
member previews are random; the entries that end up showing the player's real
character are the ones whose `+0x1dc` is later set to a valid resolved index by a
**separate** pass. `FUN_00341f34` does **not** write `+0x1dc` (it writes `+0x4a8`,
a different field on a different — front-end preview — entity), so the real
discriminator between "shows the true character" and "stays on the random pool"
is **the still-untraced `+0x1dc` resolver**, not this gate. Pinning it is the
correct next step (find the writer of `entry+0x1dc` to a non-`-1` value on this
member-entry class, and what per-member condition it keys on — likely whether the
member's resolved appearance descriptor has arrived, which *may* be server/stub
sequencing-sensitive, but that must be proven on the `+0x1dc` writer, not here).

### 9e. Fix / actionable lever. Confidence: high on the negative; the positive lever is deferred to the `+0x1dc` trace.

* **Negative (firm):** the `piVar5[0x14] == *(cpm+0x22f4)` gate is a **client-local
  handle-liveness guard** with no server-controllable input. No stub sequencing,
  profile field, or unlock-store change can make it "pass on first lobby entry,"
  because it does not run in the lobby/match and is not keyed on anything the
  server sends. The §8e lever ("ensure profile.21 + DC unlock store present before
  first lobby entry") is **not validated by this gate**; if it helps, it helps via
  the `+0x1dc` resolver in 9d, which is a different function.
* **Runtime observable that settles it (supersedes the §8e watch list):** in an
  RPCS3 session where mgnomad2 reproduces the symptom, watch (i) `cpm+0x22f0` and
  `cpm+0x22f4` at lobby/match entry — prediction: **both read 0 or a stale
  front-end value for mgnomad2 *and* comradesean alike**, and `FUN_00341f34` is
  skipped for both (confirms the gate is not the discriminator); and (ii) the
  rendered member entry's **`+0x1dc`** for each — if mgnomad2's is `0xFFFFFFFF`
  and comradesean's is a small non-negative index, the discriminator is the
  `+0x1dc` resolver (9d), and *that* function — not `FUN_00341f34` — is the fix
  target. Only after the `+0x1dc` writer is traced can we say whether the lever is
  server-side (a descriptor/unlock the stub must deliver before the resolve pass)
  or purely client-local P2P timing.

### 9f. Corrections this pass obliges

* §8b: "`FUN_00341f34` … writes the profile-faithful descriptor per player when
  `piVar5[0x14]==*(cpm+0x22f4)` holds; if it fails the entry stays on the random
  `+0x410/+0x438` fallback" — **wrong on attribution**. `FUN_00341f34` is the
  front-end loadout-screen preview apply (writes `+0x4a8` on the preview entity),
  is a no-op in-match, and never writes `+0x1dc`. The random `+0x410/+0x438`
  fallback and `+0x1dc=-1` are written by `FUN_0035a7dc` (lobby model rebuild),
  which is a separate object/pass.
* §8e: the gate is **not** a per-account discriminator and carries **no**
  server-visible input; its failure is not why mgnomad2 is bald+random. The true
  discriminator is the `+0x1dc` resolver (9d), still to be traced. The rest of
  §8e's runtime watch list is superseded by 9e(ii).
* §8b/§8e's identification of `piVar5[0x14]`/`cpm+0x22f4` as a
  "profile-loaded / resolve" gate is corrected to a **client-local handle
  generation (liveness) check** on the loadout-screen preview entity (9a).
