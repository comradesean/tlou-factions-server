# Minimum players to START a matchmade game — the go/no-go for 2-player Find Match

## THE ANSWER (one line)

**The mode minimum is NOT statically readable — it lives in a runtime-loaded DC
config record (`modeCfg+0x14`), keyed by the active mode's 32-bit name hash in a
heap reflection registry, not in a static EBOOT table.** To read the actual
number live: **set a PPU breakpoint at `0x003b7ac0` and read `r3` = min-to-start
and `r29` = current present-member count** (one breakpoint gives both). Escape
hatch: the server CANNOT change the min value (it is the client's own local DC
data); the only reliable lever to a 2-player counted game is a **client-side
patch** — patch `FUN_0039f1e0` to `li r3,2; blr` (min := 2 everywhere it is
consulted), or unconditional-branch the teardown at `0x003b7ac4`. Both make a
2-player (1v1) matchmade lobby pass the count gate; a 2-player game is otherwise
team-balanced-OK, so if the true min is ≤2 no patch is needed and 2-player Find
Match CAN start a counted game.

Every EBOOT address below was read off `powerpc64-linux-gnu-objdump` disassembly
of the quoted EBOOT, not guessed. VMA = file offset + 0x10000; RPCS3's PPU
effective address equals the VMA (non-PIE PS3 ELF), so the breakpoint addresses
below are the addresses you type into RPCS3's debugger directly.

---

## 1. The two accessors — confirmed, exactly as predicted

`FUN_0039f1e0` (MIN getter) and `FUN_0039f218` (EXPECTED getter) are trivial
wrappers over the config-record getter `FUN_00349360`:

```
FUN_0039f1e0(id):                 FUN_0039f218(id):
  0x39f1ec bl 0x349360  ; cfg       0x39f224 bl 0x349360  ; cfg
  0x39f1f4 cmpwi r3,0               0x39f22c cmpwi r3,0
  0x39f200 lwz r0,20(r3) ; cfg+0x14   0x39f238 lwz r0,24(r3) ; cfg+0x18
  return r3 ? cfg[0x14] : 0         return r3 ? cfg[0x18] : 0
```

- `FUN_0039f1e0` → **`cfg+0x14` = MIN players to start.** (`lwz r0,20(r3)`)
- `FUN_0039f218` → **`cfg+0x18` = EXPECTED/ideal count.** (`lwz r0,24(r3)`)

Adjacent siblings in the same family read the same record: `FUN_0039f250` →
`cfg+0x20` (a normalized boolean), the `+0x34`/`+0x44`/`+0x54` getters, etc. The
config record stride is **0x5C = 92 bytes** (see §3).

**The `id` argument is a red herring — it is discarded.** `FUN_00349360(id)`
does *not* pass `id` to the record match; it computes the match key from
*current global runtime state* (§2) and ignores `id`. So `FUN_0039f1e0` always
returns the min for **whatever mode is currently active**, regardless of the
argument. The only caller of the MIN getter is the SERVER_LOBBY handler
(`scan_bl 39f1e0` → single site `0x003b7ab8`).

---

## 2. Where the mode/config record comes from — RUNTIME, not static

### 2.1 The getter is a hash-registry lookup

`FUN_00349360(id)`:

```
addi r3,r1,0x70 ; &keybuf
mr   r4,id
bl   0x39abdc   ; build the match KEY into keybuf  (IGNORES id — see below)
mr   r3,id      ; (clobbered inside 0x39e900 immediately)
lwz  r4,0x70(r1); r4 = KEY
bl   0x39e900   ; linear-search the config container for record[0]==KEY
```

`FUN_0039e900(_, key)`:

```
r3 = 0xC1B0BE0D             ; type-hash constant (lis -15952; ori 48653)
bl 0x9fa9b8                 ; registry lookup by hash -> container r27
count = [r27+0]; base = [r27+4]
for i in 0..count:
   entry = base + i*0x5C    ; 92-byte records
   if FUN_003881d0(entry[0x24]) and entry[0] == key: return entry
```

`FUN_009fa9b8(0xC1B0BE0D,0)` → `FUN_009fa88c` is a **binary search over a
runtime hash-map**: `lwz r9,-32732(r30); lwz r7,200(r9)` reads the map's bucket
array at `[registry+0xC8]`, then a classic `sradi r11,r0,1` / `add r8,r6,r11`
bisection comparing `[bucketEntry+0]` against the hash. This is Naughty Dog's DC
(Design-Configuration) symbol/reflection registry. **The container's record
array (`[r27+4]`) is a heap pointer populated at data-load time from DC data
inside the game's `.pak`/`.dc` files — it is NOT a compiled-in EBOOT array.**
Statically the registry map is empty (the bucket array pointer is a BSS global,
zero at rest). Therefore the min/expected VALUES cannot be dumped from the EBOOT
file; they only exist after the mode's DC record is loaded and registered.

### 2.2 The active-mode key (what actually selects the record)

`FUN_0039abdc(&keybuf, id)` ignores `id` and writes a 32-bit key:

```
if [0x0132c530 + 0x371c] != 0:          ; an override flag byte
     *keybuf = 0x0B70ED28               ; fixed mode-name hash (override mode)
else:
     obj = FUN_003cb89c(*[modeStateSlot 0x01269604 -> 0x01389a38])
     *keybuf = big-endian u32 at obj+0x2F8   ; current mode's name-hash
```

So the record is selected by a **32-bit StringId hash of the active mode's name**
(`obj+0x2F8`), or a hard override constant `0x0B70ED28`. This is client-side
runtime state — set when the player/matchmaker selects the playlist — not a
value the server hands over.

### 2.3 Runtime globals resolved (for orientation / live inspection)

Anchors: SERVER_LOBBY handler r30 = `*(r2-31056)` = `0x01271b1c`
(r2 = `0x01305870`). `FUN_0039abdc` r30 = `*(r2-31092)` = `0x012715a4`.

| slot | global | role |
|---|---|---|
| `-32712(r30_lobby)` → `0x0137d700` | gameMgr | passed as (ignored) id to MIN getter |
| `-32632(r30_lobby)` → `0x01385cdc` | lobby/session state obj2 | holds `+0x64`, `+0x8f`, `+0x59` gate flags |
| `-32704(r30_lobby)` → `0x01385660` | SM room obj | member table walked by the count getter |
| `-32676(r30_abdc)` → `0x0132c530` | mode-override obj | flag byte at `+0x371c` |
| `-32672(r30_abdc)` → `0x01389a38` | mode-state obj | dereferenced for the active mode hash (`+0x2F8`) |

---

## 3. The SERVER_LOBBY gate — the exact count-vs-min decision (verified)

`_opd_FUN_003b7a78`, the per-frame SERVER_LOBBY handler:

```
0x3b7aa8 bl 0x3b19c4        ; r3 = count = present member count (walks SM room slots)
0x3b7aac lwz r31,-32712(r30); r31 = (ignored) mode id
0x3b7ab0 mr  r29,r3         ; r29 = count
0x3b7ab8 bl 0x39f1e0        ; r3  = MIN  = FUN_0039f1e0(id)
0x3b7ac0 cmplw cr7,r29,r3   ; <<< compare COUNT (r29) vs MIN (r3)  — BREAKPOINT HERE
0x3b7ac4 bge   cr7,0x3b7ae0 ; count >= min -> go to START-gate
0x3b7ac8 lwz r9,-32632(r30); lwz r0,0x64(r9)  ; obj2[0x64] = lower-bound fallback
0x3b7ad4 cmpw cr6,r29,r0
0x3b7ad8 beq  cr7,0x3b7b64  ; obj2[0x64]==0        -> TEAR DOWN
0x3b7adc blt  cr6,0x3b7b64  ; count < obj2[0x64]   -> TEAR DOWN
; --- START-gate (0x3b7ae0): count>=min OR the +0x64 fallback saved it ---
0x3b7ae8 lbz r0,0x8f(r9)    ; obj2[0x8f] flag; if 0 -> wait (0x3b7b44)
0x3b7af4 bl 0x349360; lwz r0,0x54(r3) ; cfg[0x54]; if 0 -> wait
0x3b7b0c bl 0x3b5468        ; team-balance; if !=0 (unbalanced) -> wait
0x3b7b60 b  0x3b7920        ; START MATCH
; --- teardown (0x3b7b64) -> ... -> 0xad0ca8  == LEAVE_GAME (net-matchmaking.cpp:1039) ---
```

Teardown predicate matches the predicted form exactly:
`count < min && (obj2[0x64]==0 || count < obj2[0x64])` → LEAVE. Otherwise the
lobby proceeds to the start-gate and (if the state/team flags are set and teams
balance) starts the match at `0x3b7920`.

Note `obj2[0x64]` is a **runtime fallback lower bound** on a *different* object
(the lobby-state obj, not the DC cfg). If it is nonzero and `count >= obj2[0x64]`
the lobby is NOT torn down even when `count < min` — it holds. This is the
"start with fewer, fill in progress" latch: real Factions modes are nominally
4v4, but the lobby survives below the cfg min as long as `count >= obj2[0x64]`.
Whether it then *starts* still requires the `0x3b7ae0` start-gate flags; but the
key point is there are TWO thresholds — cfg `min` (`+0x14`) and the runtime
`obj2[0x64]` floor — and either can be the effective start floor.

### Team balance is fine for 2 players

`FUN_003b5468(count)` short-circuits to "balanced" if `[obj2+0x59]!=0`; otherwise
it computes `count / numTeams` (`FUN_003a06e0` gives the team count) and checks
slot assignment. For 2 players over 2 teams this is a clean 1v1 split and passes.
So team balance is not what blocks a 2-player start — the count-vs-min gate is.

---

## 4. Per-mode numbers — NOT statically available (this is the honest finding)

Because §2 proves the record array is heap DC data, the actual Supply Raid /
Survivors / Interrogation min & expected values are **not present in the EBOOT
file** and cannot be dumped here. Real-world context: Factions Supply Raid and
Survivors are presented as 4v4 (8-player) modes, but the lobby is explicitly
built to start under capacity and backfill (the `obj2[0x64]` floor in §3). The
*start minimum* is therefore some small number ≤ the 8-player capacity — but its
exact value is a data value, so it must be read live, not asserted.

### Live-read recipe (one step in RPCS3's debugger)

1. Get the client into a **matchmade** Find Match lobby for the target mode so it
   reaches SERVER_LOBBY (per `2026-08-17-find-match-flow.md`).
2. Breakpoint **`0x003b7ac0`** (`cmplw cr7,r29,r3`).
3. On hit: **`r3` = MIN players to start** (`cfg+0x14`), **`r29` = current present
   count**. Do this per mode (switch playlists) to tabulate each mode's min.
4. To also capture EXPECTED and the whole record, breakpoint **`0x0039f200`**
   (`lwz r0,20(r3)` inside the MIN getter): there **`r3` = the DC config-record
   base**; dump 0x5C bytes from `r3` and read `+0x14` (min), `+0x18` (expected),
   `+0x54` (start-enable), `+0x00` (the mode name-hash key). The record base also
   lets you read the mode hash to confirm which mode it is.
5. The runtime floor: breakpoint **`0x003b7ac8`** and read `[obj2+0x64]`
   (`obj2 = *(0x01271b1c-32632) = 0x01385cdc`, field `+0x64`).

---

## 5. Escape-hatch verdict — can a 2-player counted game be made possible, and how

**Server lever: NO (for the value).** The min is `cfg+0x14` of a DC record on the
client's own heap, selected by the *client's* active-mode hash (§2.2). No wire
field the server controls writes `cfg+0x14`; the server does not supply the mode
config at all. The mode/playlist selection (`obj+0x2F8` hash) is set client-side
when the player picks the playlist. So the server cannot lower the number and
cannot, in general, force a different config.

**Server lever: PARTIAL (steer to a low-floor path).** The lobby is NOT torn
down while `count >= obj2[0x64]` even below the cfg min (§3). `obj2[0x64]` is a
runtime lobby-state field. If the find-match/RoomCreate flow the stub drives can
land `obj2[0x64]` at ≤2 (or 0-with-min≤2), a 2-player lobby survives the teardown
gate without any client patch. This is worth probing live (breakpoint
`0x003b7ac8`) — it may already be the intended "start under capacity" path. But
surviving teardown is necessary, not sufficient: the start-gate flags
(`obj2[0x8f]`, `cfg[0x54]`, team-balance) must also be satisfied to actually
start at `0x3b7920`.

**Client patch: YES — the reliable lever.** Two surgical options, both making the
count gate pass for 2 players:

- **Force min := 2 globally.** Patch `FUN_0039f1e0` entry `0x0039f1e0` to
  `li r3,2; blr` = bytes `38 60 00 02 4e 80 00 20`. The MIN getter's only
  consumer is the SERVER_LOBBY gate, so this is safe and narrow; `count(2) >=
  min(2)` passes and the lobby proceeds to the (flag-gated) start.
- **NOP the teardown branch.** At `0x0039...` no — at **`0x003b7ac4`** replace
  `bge cr7,0x3b7ae0` (`40 9c 00 1c`) with the unconditional `b 0x3b7ae0`
  (`48 00 00 1c`). The count-<-min teardown can then never fire; flow always
  reaches the start-gate. (Leaves the cfg untouched; slightly blunter.)

With either patch, and 2 real present members, a 2-player (1v1) matchmade lobby
reaches the start-gate; team-balance passes for 1v1 (§3); so a **2-player counted
matchmade game is achievable**, provided the remaining coordination pieces (the
`0x136` game-list reply that gets a second client into the same room, and the
game-end P2P link staying alive to `NET_SM_RESULTS`) are solved — those, not the
min gate, are then the residual blockers documented in the sibling notes.

**Net go/no-go:** the min gate is **not a hard wall** for 2 players. It is either
already ≤2 (read it live at `0x003b7ac0`), bypassable via the `obj2[0x64]` floor,
or trivially patchable client-side (`FUN_0039f1e0 -> return 2`). None of the
find-match coordination work is futile on account of the mode minimum. The real
open blockers remain P2P/lobby coordination, per `2026-08-17-find-match-flow.md`
and `2026-08-17-match-counts-latch.md`.

---

## Confidence

| Claim | Confidence |
|---|---|
| MIN = `cfg+0x14` via `FUN_0039f1e0`; EXPECTED = `cfg+0x18` | **High** (decompiled) |
| `id` arg is ignored; active mode selected by runtime hash (`obj+0x2F8` or const `0x0B70ED28`) | **High** (decompiled `FUN_00349360`/`FUN_0039abdc`) |
| Config record is heap DC data via hash-registry (`0xC1B0BE0D`), NOT a static EBOOT table | **High** (decompiled `FUN_0039e900`/`FUN_009fa9b8`/`FUN_009fa88c`) |
| SERVER_LOBBY teardown predicate `count<min && (obj2[0x64]==0 || count<obj2[0x64])` | **High** (decompiled `0x3b7a78`) |
| Live-read `r3`=min / `r29`=count at `0x3b7ac0` | **High** (register dataflow) |
| Team balance passes for 2-player 1v1 | **Medium-High** (`FUN_003b5468` structure) |
| Exact per-mode min numbers | **Unknown by design** — runtime data, must be read live |
| Client patch (`FUN_0039f1e0 -> li r3,2; blr`) enables a 2-player start | **High** on the gate; **Medium** overall (residual start-gate flags/coordination still required) |
