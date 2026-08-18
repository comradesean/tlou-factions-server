# Client patch: lower the find-match minimum-players-to-start to 2

**Status:** research complete. Patch bytes verified against the decrypted EBOOT;
**the mode minimum is now known exactly — it is 6** (§3, recovered from the
on-disc DC data, not guessed).
**Target:** `PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6` (TLOU v1.00, BCUS98174).
**Applies to:** BOTH RPCS3 machines. It is a *host-side* gate, but either machine
can end up the host, so patch both.

Every address here was read off `powerpc64-linux-gnu-objdump` disassembly of

```
/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf
```

VMA = file offset + 0x10000, and for this non-PIE PS3 ELF the PPU effective
address == the VMA, so every address below is simultaneously (a) what you type
into RPCS3's debugger and (b) what you put in `patch.yml`.

---

## 0. THE ANSWER — one line of YAML

```yaml
- [ be32, 0x003b7ab8, 0x38600002 ]   # was 0x4bfe7729 (bl 0x39f1e0) -> li r3,2
```

That single 32-bit write replaces the *call* to the mode's min-players getter,
at the one and only place the game ever asks for it, with `min := 2`. Nothing
else in the 18 MB executable reads that value, so the blast radius is exactly
one comparison.

**The number it overrides is 6.** Both live Factions playlists — Supply Raid
(`deathmatch`) and Survivors (`elimination`) — ship `min = 6`, `expected = 8`,
`teamSize = 4`. The working hypothesis was right. Full derivation and the on-disc
bytes in §3.

**And if you would rather not patch code at all:** the game ships a developer
setting for precisely this, *"Force Matchmaking Min Players"*, and its storage
is a fixed u32 at **`0x01385D40`**. Write `2` there in RPCS3's memory viewer
before the host creates its room and the same gate opens (§3.4 / §4b).

---

## 1. Why this exact instruction — the whole consumer graph

### 1.1 The gate (`FUN_003b7a78`, the SERVER_LOBBY go/no-go)

```
3b7aa8:  4b ff 9f 1d   bl      0x3b19c4      ; r3 = present-member count
3b7aac:  83 fe 80 38   lwz     r31,-32712(r30)  ; r31 = gameMgr (the arg is discarded)
3b7ab0:  7c 7d 1b 78   mr      r29,r3        ; r29 = COUNT
3b7ab4:  7f e3 fb 78   mr      r3,r31
3b7ab8:  4b fe 77 29   bl      0x39f1e0      ; r3 = MIN   <<<<< PATCH THIS
3b7abc:  60 00 00 00   nop
3b7ac0:  7f 9d 18 40   cmplw   cr7,r29,r3    ; COUNT vs MIN   <<<<< breakpoint here to read them
3b7ac4:  40 9c 00 1c   bge     cr7,0x3b7ae0  ; count >= min -> start-gate
3b7ac8:  81 3e 80 88   lwz     r9,-32632(r30)   ; r9 = dev-settings struct 0x01385cdc
3b7acc:  80 09 00 64   lwz     r0,100(r9)       ; +0x64 = "Force Matchmaking Min Players"
3b7ad0:  2f 80 00 00   cmpwi   cr7,r0,0
3b7ad4:  7f 1d 00 00   cmpw    cr6,r29,r0
3b7ad8:  41 9e 00 8c   beq     cr7,0x3b7b64  ; floor == 0        -> TEAR DOWN
3b7adc:  41 98 00 88   blt     cr6,0x3b7b64  ; count < floor     -> TEAR DOWN
```

Replacing `bl 0x39f1e0` with `li r3,2` (`0x38600002`) is safe here because:

* `bl` clobbers LR and the volatile registers; `li` clobbers strictly less.
  LR is not live (it was spilled to `176(r1)` in the prologue at `0x3b7a90` and
  is reloaded from there in both epilogues).
* `r3` is dead on entry to the call (it is only the discarded `id` argument —
  see §1.3), and is immediately consumed by the `cmplw` at `0x3b7ac0`.
* The `nop` at `0x3b7abc` is the PPC64 ABI's TOC-restore slot; leaving it is
  harmless.

### 1.2 The getter has exactly one caller, and `cfg+0x14` exactly one reader

`FUN_0039f1e0` = "min players to start":

```
39f1e0:  f8 21 ff 81   stdu    r1,-128(r1)
39f1e4:  7c 08 02 a6   mflr    r0
39f1e8:  f8 01 00 90   std     r0,144(r1)
39f1ec:  4b fa a1 75   bl      0x349360        ; r3 = active mode's DC config record
39f1f4:  2f 83 00 00   cmpwi   cr7,r3,0
39f1f8:  38 00 00 00   li      r0,0
39f1fc:  41 9e 00 08   beq     cr7,0x39f204
39f200:  80 03 00 14   lwz     r0,20(r3)       ; cfg+0x14  == MIN
39f204:  78 03 00 20   clrldi  r3,r0,32
...      4e 80 00 20   blr
```

`tools/eboot_analysis/scan_bl.py 39f1e0` over the whole `.text`:

```
bl from 0x003b7ab8 -> 0x0039f1e0
```

**One call site. That's it.** And a dataflow sweep of **all 35** `bl 0x349360`
(config-record getter) call sites — following the returned `r3` through `mr` /
`clrldi` copies until the next call and collecting every displacement loaded off
it — gives the complete set of config-record fields the executable ever reads:

```
0x14  0x18  0x1c  0x20  0x28  0x2c  0x30  0x34  0x38  0x44  0x48  0x4c  0x50  0x54  0x58
```

and `0x14` is produced by **exactly one instruction in the whole binary**:
`0x0039f200`, inside `FUN_0039f1e0`. So the mode minimum genuinely feeds one
comparison and nothing else.

Consequences that matter for us:

* **It does not feed any UI.** The lobby "N / 8" text is not driven by it.
* **It does not feed RoomCreate.** The `0x12f` `max_players=8` on the wire comes
  from `cfg+0x18` (EXPECTED) via `FUN_0039f218`, read at `0x003b7f6c` inside the
  RoomCreate builder `FUN_003b7d70` and passed as arg 5 of the vtable call at
  `0x003b7fb0`. Our patch leaves that at 8, so rooms still advertise 8 slots.
* **It does not feed the joiner.** `FUN_0039f1e0` is never called on the client
  path (states 5–15).

`0x0039f1e0` does have an OPD function descriptor at `0x012bcf48`, but the only
`bl` to it is the one above; no indirect-call table references it.

### 1.3 The `id` argument is discarded (so `li r3,2` cannot break an argument)

`FUN_00349360(id)` builds its lookup key from *current global runtime state* and
throws `id` away: `addi r3,r1,0x70` / `bl 0x39abdc`, and `FUN_0039abdc` selects
either the constant `0x0B70ED28` (when the override byte
`[0x0132c530+0x371c] != 0`) or the big-endian u32 at `mode+0x2F8` — the active
mode's 32-bit name hash. So "the min" is always "the min of whatever mode is
currently selected", and `r3` at `0x003b7ab8` carries nothing that survives.

---

## 2. Are there OTHER minimum-player checks downstream? — No.

This was the real risk (patch the lobby gate, trip a later 6-player check), so
it was chased to the end.

### 2.1 The present-member count function has two callers, total

`scan_bl.py 3b19c4`:

```
bl from 0x003b2840 -> 0x003b19c4     (inside FUN_003b2810 = lobby wait-seconds)
bl from 0x003b7aa8 -> 0x003b19c4     (the gate above)
```

Nothing else in the binary computes the SERVER_LOBBY member count, so nothing
else can compare it to anything.

(The count itself, `FUN_003b19c4`, counts a member iff the P2P connection
manager's `vtable[0x18](member[0xF0])` returns 2, or the member is me:
`3b1a70 cmpwi cr7,r3,2` / `3b1a6c cmpw cr6,r28,r25`. Unchanged by this patch.)

### 2.2 What the host actually does next — mapped

The prior notes left "the next step" unnamed. It is
**`NET_SM_SERVER_VOTE_SCREEN`, state code 21**, logged as
`net-matchmaking.cpp:1017 : GOTO NET_SM_SERVER_VOTE_SCREEN`.

Proof: the transition function is `FUN_003b7920`, ending

```
3b7a2c:  83 be 81 d8   lwz     r29,-32296(r30)   ; slot 0x01269cf4 -> 0x00e7d608
3b7a3c:  38 a0 03 f9   li      r5,1017           ; source line
3b7a40:  48 a8 ea 21   bl      0xe46460          ; TTY "GOTO NET_SM_%s"
3b7a4c:  38 60 00 15   li      r3,21             ; new state = 21
3b7a50:  4b f8 f7 11   bl      0x347160          ; SetNetSmState
```

and `*(u32*)0x01269cf4 == 0x00e7d608`, where the C string at `0x00e7d608` is
`"NET_SM_SERVER_VOTE_SCREEN"`. (Method cross-checked against the known
`state 17 / line 874` site at `0x003b3874`, whose slot `0x01269bfc` holds
`0x00e7aa78 = "NET_SM_SERVER_LOBBY"`.)

Corrected control flow of the start-gate (the previous note had the flag
polarity inverted):

```
3b7ae0:  lwz r9,-32632(r30)                ; lobby-state obj 0x01385cdc
3b7ae8:  lbz r0,143(r9)  / beq -> 3b7b44   ; obj[0x8f] == 0  -> GO
3b7af4:  bl 0x349360 ; lwz r0,84(r3)       ; cfg[0x54]
3b7b08:  beq -> 3b7b44                     ; cfg[0x54] == 0  -> GO
3b7b0c:  bl 0x3b5468 (teamBalance(count))
3b7b20:  bne -> 3b7b44                     ; result != 0     -> GO
3b7b24..3b7b40: (all three "not yet") -> tail-call FUN_003b6dfc(roomObj, 0), stay in SERVER_LOBBY
3b7b44..3b7b60: GO -> b 0x3b7920 -> state 21 SERVER_VOTE_SCREEN
```

`FUN_003b5468` returns 1 immediately when `[0x01385cdc + 0x59] != 0`
(`3b54a0 lbz r0,89(r9)` / `3b54b4 bne cr7,0x3b56a4` / `3b56a4 li r3,1`) — i.e.
"teams already assigned" short-circuits to GO. For a 2-player 1v1 the
non-short-circuit path also resolves cleanly (`count / numTeams` with
`FUN_003a06e0` giving the team count).

### 2.3 The SERVER_VOTE_SCREEN handler does not re-check any count

State 21 dispatches through the jump table at `0x003b99cc` (index `state-4`,
entry `0x118`) to `0x003b9ae4 → bl 0x3b8730`. `FUN_003b8730` disassembled in
full (`0x3b8730`–`0x3b88a0`): it is purely a vote timer — `FUN_003b3fb8(1)`,
`FUN_00ad0eec`, `FUN_003589f8`, the `[0x013858b8]` byte, `FUN_0039fed0`,
`FUN_003a64b4(mode,1,1,1,0,0)`, `FUN_00347188` (timeout), `FUN_00358924(46)`.
**No member count, no config-record read, no comparison against a minimum.**

### 2.4 The only other count-vs-threshold in the game uses EXPECTED, not MIN

`FUN_003f10b8` (`game/net/task-manager-online.cpp`, the in-game host monitor —
it owns the strings `"Cheating"`, `"Host quit for cheating"`,
`"Leaving Game Normally"`) contains:

```
3f1848:  bl 0xad1024        ; r29 = joined-player count
3f1858:  bl 0x39f218        ; r3 = cfg+0x18 = EXPECTED (= 8)
3f1860:  cmplw cr7,r29,r3
3f1864:  bge cr7,0x3f1884   ; count >= expected -> stop advertising / close the room
```

That is a **full**-room check, not a minimum, it is on the EXPECTED field which
this patch does not touch, and `bge` means a 2-player game simply never takes
that branch. Harmless either way.

### 2.5 There is a *second*, unrelated min-players helper — and it maxes out at 2

`FUN_003a44ac(x, flag)` is a genuine "minimum players" function and it *is*
compared against a live player count:

```
35ac54:  bl 0xad1024        ; r29 = player count
35ac68:  bl 0x3a44ac        ; r3  = min (1 or 2)
35ac74:  cmplw cr7,r29,r3
35ac78:  blt  cr7,0x35ab98  ; count < min -> not ready
```

But its return is masked to two bits (`3a4554 clrldi r3,r10,62`) and the only
values it can produce are **1 and 2** (`li r10,2` at `0x3a4500`, `li r10,1` at
`0x3a454c`). It reads the DC map/game-type table (type hash `0x3B9A067D`,
112-byte records, field `+0xc == 3`) and is short-circuited to `1` by the
"Disable Min Player Limit" flag at `0x01385d68`. Callers: `0x0035ac68`
(`FUN_0035aad8`, lobby-flow), `0x003a8470`, `0x003d04cc`.

**A 2-player game passes it unconditionally.** Noted only so nobody re-discovers
it later and mistakes it for a blocker.

### 2.6 Verdict

**There is exactly one minimum-players gate on the find-match path, and it is
the `cmplw` at `0x003b7ac0`.** Passing it puts the host straight into
SERVER_VOTE_SCREEN and from there down the normal load-level path. No second
gate exists to trip.

---

## 3. What the minimum actually IS — **6**, recovered from the on-disc DC data

Not in the EBOOT (the array is heap DC data reached through a runtime hash
registry — `FUN_0039e900` does `lis r3,-15952 / ori r3,r3,48653` = `0xC1B0BE0D`,
`bl 0x9fa9b8`, then `mulli r0,r28,92` over `[container+4]`). But it *is* in the
game's data files, and it has now been read out of them.

### 3.0 The table

`build/main/bin.psarc` → `dc1/net.bin` (283,615 bytes, magic `DC00`; the archive
is **plaintext** — no Blowfish, that only wraps the CDN `.crypt` files). The DC
symbol table entry `nameHash=0xC1B0BE0D, typeHash=0x3C3647D2, dataOffset=0x515C`,
and at `0x515C`:

```
0000 0004 0000 6308      ; count = 4, base = 0x6308   <- exactly [r27+0] / [r27+4]
```

Four 0x5C-byte records at `0x6308`:

| # | file offset | key `+0x00` | name | **min `+0x14`** | expected `+0x18` | team `+0x1c` | idx `+0x3c` | `+0x24` | `+0x54` |
|---|---|---|---|---|---|---|---|---|---|
| 0 | `0x6308` | `0xA8EE9C4F` | *(name not recovered)* | **2** | 2 | 2 | 0 | 1 | 0 |
| 1 | `0x6364` | `0x240E467D` | *(name not recovered)* | **2** | 2 | 2 | 1 | 1 | 0 |
| 2 | `0x63C0` | `0xD3B86D60` | **`deathmatch`** = Supply Raid | **6** | **8** | 4 | 2 | 1 | 0 |
| 3 | `0x641C` | `0xAE00A01F` | **`elimination`** = Survivors | **6** | **8** | 4 | 3 | 1 | 0 |

> **Supply Raid and Survivors both require 6 players to start.**

### 3.1 Why this is trustworthy

* `+0x18 = 8` matches the `max_players=8` our own stub logs on every real `0x12f`
  RoomCreate, which independently pins the field alignment — so `+0x14 = 6` is
  the min.
* The names decode under a hash function verified on thousands of pairs:
  **32-bit CRC-32, MSB-first / non-reflected, poly `0x04C11DB7`, init 0, no final
  XOR, no trailing NUL.** Re-derived and re-checked here:
  `sid("*playlists*") = 0xC1B0BE0D`, `sid("*net-games*") = 0x3B9A067D`,
  `sid("net-playlist-array") = 0x3C3647D2`, `sid("deathmatch") = 0xD3B86D60`,
  `sid("elimination") = 0xAE00A01F`, `sid("test") = 0x0B70ED28` — all exact.
* A sweep of every top-level `dc1/*.bin` for 0x5C-strided regions with
  `+0x18 == 8` and `1 ≤ +0x14 ≤ 8` returns **exactly one** hit: this array. There
  is no competing table.
* No title update is installed (`dev_hdd0/game/BCUS98174/USRDIR/build/main/` holds
  only `promo1`), so this disc `net.bin` *is* what the running client loads.

**Interrogation is not in this build at all** — the disc (2013-05-15) ships four
playlists, and Interrogation arrived in a later update. Its min cannot be read
from on-disc data.

### 3.2 Consequence: `cfg+0x54 == 0`, so the count gate is the *only* gate

All four records have `+0x54 = 0`. Re-read the start-gate (§2.2): once the count
comparison passes, `obj[0x8f]` is tested and then `cfg[0x54]`, and **`cfg[0x54]
== 0` branches straight to `0x3b7b44 → 0x3b7920 → SERVER_VOTE_SCREEN`**. The
team-balance call at `0x3b7b0c` is never even reached on this path.

So with the patch applied, `count >= 2` is *literally the last thing* between the
host and the vote screen. That is a stronger result than §2 could claim on
static analysis alone.

### 3.3 Reading it live anyway (record base at runtime)

If you would rather poke the data than patch the code, the record is reachable
from a fixed address:

```
0x01463720                       ; DC reflection registry object (static/BSS)
  + 0xC8    -> bucketHdr         ; lwz r9,-32732(r30) ; lwz r7,200(r9)   @0x9fa8b0
bucketHdr + 0x00 -> entryBase    ; array of 8-byte {u32 hash, u32 value}, sorted
bucketHdr + 0x04 -> entryCount
  binary-search entryBase for hash 0xC1B0BE0D  -> container = entry.value
container + 0x00 -> recordCount
container + 0x04 -> recordBase
record i   = recordBase + i*0x5C
  +0x00 u32  mode name hash (StringId)
  +0x14 u32  MIN players to start     <-- write 2 here
  +0x18 u32  EXPECTED (= 8)
  +0x54 u32  start-enable flag
```

(`0x01463720` derived as: `r2 = 0x01305870`; `lwz r30,-28256(r2)` →
`*(0x012fea10) = 0x012999e0`; `lwz r9,-32732(r30)` → `*(0x01291a04) =
0x01463720`.)

Much easier in practice: breakpoint `0x0039f200` (`lwz r0,20(r3)`) — at that
instant **`r3` is the record base**, one hop, no chain walking.

### 3.4 The runtime floor at `[0x01385cdc + 0x64]` is the game's own **"Force Matchmaking Min Players"** developer setting

This is the best find of the pass. `0x01385cdc` is not a lobby object at all —
it is Naughty Dog's global **developer-settings struct** (a big blob of dev
toggles in BSS, referenced from ~44 compilation units). The debug menu builder
`FUN_003c8154` in `game/net/net-menu-host.cpp` wires three items straight into
it:

```
3c81bc:  83 9e 80 98   lwz     r28,-32616(r30)  ; r28 = 0x01385d76
3c81c0:  80 9e 80 94   lwz     r4,-32620(r30)   ; "Show Debug Traffic"
3c81c8:  7f 85 e3 78   mr      r5,r28           ;   &0x01385d76
3c81d0:  48 5e 22 21   bl      0x9aa3f0         ; add bool item
3c81f4:  38 bc ff f2   addi    r5,r28,-14       ;   &0x01385d68
3c81f8:  80 9e 80 9c   lwz     r4,-32612(r30)   ; "Disable Min Player Limit"
3c8204:  48 5e 21 ed   bl      0x9aa3f0         ; add bool item
3c8228:  80 fe 80 a8   lwz     r7,-32600(r30)   ; "%2d"
3c822c:  80 9e 80 a0   lwz     r4,-32608(r30)   ; "Force Matchmaking Min Players"
3c8238:  39 1c ff ca   addi    r8,r28,-54       ;   &0x01385d40
3c823c:  38 c0 00 02   li      r6,2
3c8248:  48 5e 4d 95   bl      0x9acfdc         ; add integer item
```

`0x01385d76 - 54 = 0x01385d40 = 0x01385cdc + 0x64` — **byte-exact**. So:

> **`(u32*)0x01385d40` IS "Force Matchmaking Min Players".**

And a whole-binary sweep of every field access to this struct shows `+0x64` is
touched at exactly two instructions in the entire executable: `0x003b2868`
(lobby wait) and `0x003b7acc` (the gate). Nothing else reads or writes it.

That makes it a first-class, developer-sanctioned lever: set it to 2 and the
gate lets a 2-player lobby through *without lying about the mode's own min*.

`0x01385d68 = struct+0x8c` is **"Disable Min Player Limit"**. It is *not* on the
host gate path — its only two readers are `0x003a44e0` (`FUN_003a44ac`) and
`0x003a7b5c` (`FUN_003a79b4`), map/game-type availability helpers that do a DC
lookup of type hash `0x3B9A067D` over 112-byte records and return a 2-bit enum;
setting the flag makes them return the constant `1` instead. Leave it alone
unless the vote screen turns out to offer no selectable maps at 2 players — then
it is the thing to try.

Full semantics of `struct+0x64` (u32):

| value | effect in `FUN_003b7a78` (the gate, `0x3b7ac8`) | effect in `FUN_003b2810` (lobby wait, `0x3b2868`) |
|---|---|---|
| `0` (default / not forced) | `count < mode min` ⇒ **tear down** unconditionally | none (wait = `table[count]`) |
| `1` | forced min of 1: `count >= 1` proceeds even below the mode min | **wait is forced to 4.0 s** (`3b2870 cmpwi cr7,r11,1` / `3b289c li r0,4`) |
| `N > 1` | forced min of N: `count >= N` proceeds even below the mode min | none |

**`2` is exactly what we want**: a 2-player lobby proceeds, a solo host still
does not, and the lobby wait table is untouched.

Worth reading once live (breakpoint `0x003b7ac8`, step, read `r0`) — if it is
already ≤ 2 in our runs then the min gate was never the blocker at all.

---

## 4. THE PATCH — three forms

Primary target, verified byte-for-byte out of the file:

| | VMA (RPCS3 address) | EBOOT.elf file offset | original bytes | new bytes | meaning |
|---|---|---|---|---|---|
| **P1 (use this)** | `0x003b7ab8` | `0x003a7ab8` | `4b fe 77 29` | `38 60 00 02` | `bl 0x39f1e0` → `li r3,2` |

Alternatives (documented, **not** recommended — do not combine with P1):

| | VMA | file offset | original | new | meaning |
|---|---|---|---|---|---|
| P1b | `0x003b7acc` | `0x003a7acc` | `80 09 00 64` | `38 00 00 02` | `lwz r0,100(r9)` → `li r0,2`, i.e. hard-code **"Force Matchmaking Min Players" = 2** |
| P2 | `0x0039f1e0` | `0x0038f1e0` | `f8 21 ff 81` | `38 60 00 02` | getter → `li r3,2` |
| P2 | `0x0039f1e4` | `0x0038f1e4` | `7c 08 02 a6` | `4e 80 00 20` | `blr` |
| P3 | `0x003b7ac4` | `0x003a7ac4` | `40 9c 00 1c` | `48 00 00 1c` | `bge cr7,0x3b7ae0` → `b 0x3b7ae0` (min gate can never fail at all, even at count 1) |

P1 is preferred over P2 because it is one word instead of two and leaves the
getter callable; over P3 because P3 also lets a **solo** host start a match,
which would make the host stop waiting for the second player and start a 1-man
game — the opposite of what we want during a 2-client test. P1 keeps the
semantics "wait until there really are 2 present, connected members".

**P1 vs P1b** is a genuine toss-up and they are behaviourally identical at
count ≥ 2 (P1: `count >= min(2)` takes the first branch; P1b: `count < modeMin`
falls through to `floor = 2` and `count >= 2` takes the second). P1b has the
aesthetic advantage of driving the developers' own override rather than
falsifying the mode min, and it is the static equivalent of the live poke in
§4b — if you use the live poke for one machine and a patch for the other, use
P1b so both machines are doing literally the same thing. P1 is listed first only
because it is the shorter reasoning chain. **Pick one, never both.**

### 4a. RPCS3 `patch.yml` — the recommended form

Create a **new file** (do not edit `patch.yml`; it is overwritten by RPCS3's
patch downloader) at:

```
<rpcs3 folder>\patches\tlou_factions_patch.yml
```

RPCS3 globs `*_patch.yml` in that directory (the format string `%s%s_patch.yml`
and the glob `*_patch.yml` are both in `rpcs3.exe`; this is the same mechanism as
the repo's existing `BLUS41045_patch.yml`).

**Address convention proof.** RPCS3 patch addresses are PS3 *effective*
addresses (= our VMAs), not file offsets. Cross-checked against the community
TLOU patch already shipping in `patches/patch.yml` under the same PPU hash:

```yaml
- [ be32, 0x006b06a8, 0x483a4b95 ]   # "Branch"
- [ be32, 0x00a55248, 0x813d0040 ]   # "lwz r9,0x40(r29) // load as normal"
```

Disassembling this EBOOT at **VMA** `0x006b06a8` gives exactly
`81 3d 00 40  lwz r9,64(r29)` — the instruction that patch relocates into its
code cave. At the file-offset interpretation (`0x006c06a8`) it is `mflr r0`,
which is nonsense. So VMA it is.

```yaml
Version: 1.2

# The Last of Us v1.00 -- Factions find-match: lower "minimum players to start"
#
# The host's SERVER_LOBBY handler (FUN_003b7a78) decides go/no-go with
#     0x003b7ab8  bl 0x39f1e0      ; r3 = the active mode's min-players-to-start
#     0x003b7ac0  cmplw cr7,r29,r3 ; r29 = present member count
#     0x003b7ac4  bge   cr7,...    ; count >= min -> start
# The min is DC data (modeCfg+0x14), loaded from the game's data at runtime, so
# it cannot be changed from the server side and cannot be read out of the EBOOT.
# 0x0039f1e0 is called from exactly ONE place in the whole executable (this one),
# and modeCfg+0x14 is read from exactly one place (inside 0x0039f1e0), so
# replacing the call with a constant affects that single comparison and nothing
# else -- no UI, no RoomCreate max (that is modeCfg+0x18 = 8, untouched), no
# client-side path.

PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6:

  "Factions: minimum players to start = 2":
    Games:
      "The Last of Us":
        BCUS98174: [ All ]
        BCES01584: [ All ]
        BCES01585: [ All ]
        BCJS37010: [ All ]
        BCAS20270: [ All ]
        NPEA00435: [ All ]
        NPUA80960: [ All ]
    Author: "tlou_factions"
    Patch Version: "1.0"
    Notes: |
      Makes a 2-player (1v1) matchmade lobby pass the count>=min gate.
      Enable on EVERY machine -- either one can be elected host.
      A solo host still will NOT start a match (min is 2, not 1).
    Patch:
      - [ be32, 0x003b7ab8, 0x38600002 ]   # was 0x4bfe7729 (bl 0x0039f1e0); now: li r3,2

  # ---- OPTIONAL companion, see section 6 of the note. Leave OFF by default. ----
  "Factions: extend host lobby wait window (60s at 1-2 players)":
    Games:
      "The Last of Us":
        BCUS98174: [ All ]
        BCES01584: [ All ]
        BCES01585: [ All ]
        BCJS37010: [ All ]
        BCAS20270: [ All ]
        NPEA00435: [ All ]
        NPUA80960: [ All ]
    Author: "tlou_factions"
    Patch Version: "1.0"
    Notes: |
      Widens the host's SERVER_LOBBY decision deadline from 8.0+4 = 12 s (at 1
      member) and 8.0+8 = 16 s (at 2 members) to 8.0+60 = 68 s, giving the
      second client many more matchmaking cycles to find the room.
      TESTING AID ONLY -- a stuck host will now sit for 68 s instead of 12 s.
    Patch:
      - [ be32, 0x00e7d344, 0x0000003c ]   # lobbyWaitTable[1]: was 4  -> 60
      - [ be32, 0x00e7d348, 0x0000003c ]   # lobbyWaitTable[2]: was 8  -> 60

  # ---- ALTERNATIVES. Do NOT enable together with the first patch. ----
  "Factions: Force Matchmaking Min Players = 2":
    Games:
      "The Last of Us":
        BCUS98174: [ All ]
    Author: "tlou_factions"
    Patch Version: "1.0"
    Notes: |
      Same effect as the first patch, via the game's own developer override
      instead: hard-codes the "Force Matchmaking Min Players" dev setting
      (u32 at 0x01385D40 = devStruct+0x64) to 2 at its only read site on the
      matchmaking gate. The mode's real minimum is left intact and is still
      honoured whenever it is met. Pick this OR the first patch, never both.
    Patch:
      - [ be32, 0x003b7acc, 0x38000002 ]   # was 0x80090064 (lwz r0,100(r9)); now: li r0,2

  "Factions: min players to start = 2 (patch the getter instead)":
    Games:
      "The Last of Us":
        BCUS98174: [ All ]
    Author: "tlou_factions"
    Patch Version: "1.0"
    Notes: |
      Same effect as the first patch, applied at FUN_0039f1e0 instead of at its
      only call site. Redundant -- pick one.
    Patch:
      - [ be32, 0x0039f1e0, 0x38600002 ]   # was 0xf821ff81 (stdu r1,-128(r1)); now: li r3,2
      - [ be32, 0x0039f1e4, 0x4e800020 ]   # was 0x7c0802a6 (mflr r0);          now: blr

  "Factions: disable the min-players gate entirely (allows 1-player start)":
    Games:
      "The Last of Us":
        BCUS98174: [ All ]
    Author: "tlou_factions"
    Patch Version: "1.0"
    Notes: |
      Turns the count>=min branch into an unconditional branch. A LONE host will
      then start a match by itself and stop waiting for anyone. Only useful for
      probing the post-lobby path solo. Not for 2-player testing.
    Patch:
      - [ be32, 0x003b7ac4, 0x4800001c ]   # was 0x409c001c (bge cr7,0x3b7ae0); now: b 0x3b7ae0
```

**Enabling it in the GUI:** RPCS3 → `Manage` → `Game Patches` (a.k.a. the Patch
Manager) → find *The Last of Us* → tick **"Factions: minimum players to start =
2"** → `Save`. It applies at the next boot of the game. If the entry does not
appear at all, the running executable's hash does not match — re-check it per
§5 step 2.

### 4b. Live poke in the RPCS3 debugger

**The good one — write the developer setting, no code editing at all:**

> **Write the u32 `2` to address `0x01385D40`** ("Force Matchmaking Min
> Players"), any time before the host creates its room.

Fixed address, plain data, read fresh out of memory every time the gate runs
(`0x003b7acc lwz r0,100(r9)`), so it works with any PPU decoder and needs no
recompiler invalidation. Redo it after each emulation restart — it lives in BSS
and is presumably re-initialised on boot. (Do **not** write `1`: that also
squashes the lobby wait to 4.0 s, see §3.4.)

While you are there, `0x01385D68` is "Disable Min Player Limit" (a byte); it is
not on this path — see §3.4 — leave it `0` unless the vote screen has no
selectable maps.

**Instruction-edit alternative** (equivalent to patch P1). **Requires
`Settings → CPU → PPU Decoder = Interpreter (static)`** — RPCS3 refuses
breakpoints on recompiler decoders (`"Cannot set breakpoints on non-interpreter
decoders."`) and an instruction edit under LLVM may land after the block was
already compiled:

1. Boot the game, get to the multiplayer menu (any time before a lobby forms).
2. In the RPCS3 main window open the **Debugger** panel, select the PPU main
   thread in the thread dropdown.
3. `Go To Address` (Ctrl+G) → type `3B7AB8`.
4. Click that line, press **`E`** (Instruction Editor), enter `38600002`, OK.
5. The line must now read `li r3,2`.

**DC-record poke** (last resort, redo on every mode/map change): breakpoint
`0x0039f200`, let it hit, read `r3` = the DC record base, write `2` to
`r3 + 0x14`.

**Possible no-hex route — try this first, it costs 5 minutes:** RPCS3's stock
`patches/patch.yml` ships a `"Debug Menu"` patch for TLOU v1.00 (anchor
`tlou100_devmenu`, same PPU hash). The submenu built by `FUN_003c8154` — the one
holding *"Force Matchmaking Min Players"* as an editable `%2d` field — is
registered by its caller `FUN_00353e34` under the menu path string
**`"multi-player-menu"`** (`0x00e5eb88`, loaded at `0x00353f28`). So with the
Debug Menu enabled, look for a *multi-player* branch in the dev menu; the value
should be dialable in-game with no memory editing at all. **Unverified** — the
menu tree has not been walked.

### 4c. Raw EBOOT hex edit — last resort

```
file: .../PS3_GAME/USRDIR/EBOOT.elf
offset 0x003A7AB8 :  4B FE 77 29   ->   38 60 00 02
```

**Caveat:** RPCS3 boots `EBOOT.BIN` (encrypted), not `EBOOT.elf`. To use this you
have to put the patched *decrypted* ELF in place of `EBOOT.BIN`, which changes
the PPU hash — every other patch keyed to
`PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6` (MLAA fix, head-crash fix, …)
silently stops applying. Keep a backup of the original `EBOOT.BIN`. Use 4a
instead unless there is a specific reason not to.

---

## 5. Step-by-step for the second machine — send this verbatim

> **What this does:** The Last of Us refuses to start a Factions match until
> enough players are in the lobby. This one-line patch lowers that threshold to
> 2 so we can test with just the two of us. It changes nothing else.
>
> **1. Find your RPCS3 folder** — the one containing `rpcs3.exe`. Inside it
> there is a `patches` folder.
>
> **2. Check your game matches mine.** Boot The Last of Us once, then quit.
> Open `log\RPCS3.log` in a text editor and search for
> `PPU executable hash`. It should say:
>
> ```
> PPU executable hash: PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6
> ```
>
> If it says anything else, stop and send me that line — you have a different
> game version and the patch would silently do nothing.
>
> **3. Create the patch file.** In the `patches` folder, make a new text file
> named exactly:
>
> ```
> tlou_factions_patch.yml
> ```
>
> (Make sure Windows didn't name it `tlou_factions_patch.yml.txt` — turn on
> "File name extensions" in Explorer's View menu to check.)
>
> Paste in exactly this, save, close:
>
> ```yaml
> Version: 1.2
>
> PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6:
>
>   "Factions: minimum players to start = 2":
>     Games:
>       "The Last of Us":
>         BCUS98174: [ All ]
>         BCES01584: [ All ]
>         BCES01585: [ All ]
>         BCJS37010: [ All ]
>         BCAS20270: [ All ]
>         NPEA00435: [ All ]
>         NPUA80960: [ All ]
>     Author: "tlou_factions"
>     Patch Version: "1.0"
>     Notes: |
>       Lets a 2-player matchmade lobby start a game.
>     Patch:
>       - [ be32, 0x003b7ab8, 0x38600002 ]
> ```
>
> Indentation matters — it must be spaces, not tabs. Copy it as-is.
>
> **4. Turn it on.** Start RPCS3 → menu **`Manage` → `Game Patches`** → find
> **The Last of Us** in the list → tick the checkbox next to
> **"Factions: minimum players to start = 2"** → click **Save**.
>
> If The Last of Us does not appear in that list, the file has a typo — send me
> a screenshot.
>
> **5. Start the game.** That's it. There is nothing to do in-game.
>
> **6. Confirm it took (optional).** In the RPCS3 log window right after boot
> you should see a line mentioning `patch` and the game serial (RPCS3 logs how
> many patches it applied to the executable). The gameplay proof is simply that
> a Find Match lobby with the two of us in it now proceeds instead of dropping
> back to searching after ~16 seconds.

---

## 6. How to verify it worked

### 6.1 Static — before booting

Confirm the exact original bytes are what the patch expects. From the repo:

```sh
cd tools/eboot_analysis
python3 -c "from eb import rd; print(' '.join('%02x'%c for c in rd(0x003b7ab8,4)))"
# expect: 4b fe 77 29
```

### 6.2 In the RPCS3 log

RPCS3 logs the applied-patch count on the `PPU executable hash:` line, as
`(<- N)`. Note N before enabling, and confirm it went up by 1 afterwards. (This
install currently logs `(<- 76)` with the stock TLOU patches enabled.)

### 6.3 In the debugger — the definitive check

With `PPU Decoder = Interpreter (static)`:

1. Breakpoint **`0x003b7ac0`** (`cmplw cr7,r29,r3`).
2. Get a host into a Find Match lobby. When the breakpoint hits:
   * **`r3` must read `2`** — that is the patch working. Unpatched it reads
     **`6`** on Supply Raid and Survivors (§3); if you see `6`, the patch did not
     apply.
   * **`r29`** is the current present-member count. Both of you connected and
     P2P-established ⇒ `2`.
3. Continue. If `r29 >= r3` the very next branch (`0x003b7ac4 bge`) is taken and
   the host walks into `0x003b7ae0` → the start-gate.

While you are there, also worth reading once:

* the u32 at **`0x01385D40`** — the live value of "Force Matchmaking Min
  Players". `0` = not forced, so the mode min is the only thing in play. `1` or
  `2` = the gate was never the blocker in the first place. Read it straight from
  the memory viewer; no breakpoint needed.
* `0x0039f200` then `r3` = the whole 0x5C DC config record; dump it and compare
  against §3.0 — `+0x00` should be `0xD3B86D60` (Supply Raid) or `0xAE00A01F`
  (Survivors), `+0x14 = 6`, `+0x18 = 8`, `+0x1c = 4`, `+0x54 = 0`. That also
  confirms which playlist the client actually selected.

### 6.4 In the game's own TTY output

Grep RPCS3's `TTY.log`. The success signature is a line that has never yet
appeared in any of our runs:

```
game/net/net-matchmaking.cpp:1017 : GOTO NET_SM_SERVER_VOTE_SCREEN
```

The failure signature — what we see today — is:

```
game/net/net-matchmaking.cpp:1039 : GOTO NET_SM_LEAVE_GAME
```

roughly 12.0 s (1 member) or 16.0 s (2 members) after the `0x12f` RoomCreate.

---

## 7. OPTIONAL companion patch — extend the host's lobby window

**Label this optional.** It does not affect the minimum; it buys wall-clock
margin so the two clients' ~23 s matchmaking cycles have more chances to
overlap.

### The mechanism (verified)

`FUN_003b7c0c` (the real SERVER_LOBBY per-frame handler, state 17) runs the gate
only after a deadline:

```
3b7c78:  4b ff ab 99   bl      0x3b2810     ; f30 = wait seconds
3b7d08:  ff 9e 00 00   fcmpu   cr7,f30,f0
3b7d0c:  40 9c 00 40   bge     cr7,0x3b7d4c ; still waiting -> return
3b7d48:  4b ff fd 30   b       0x3b7a78     ; deadline passed -> run the count/min gate
```

`FUN_003b2810` picks the wait from a 13-entry table indexed by the *current*
member count:

```
3b2840:  bl 0x3b19c4                        ; r3 = count
3b2844:  lwz r9,-32636(r30)                 ; slot 0x01269ba0 -> table base 0x00e7d340
3b2850:  slwi r3,r3,2
3b2858:  lvx v0,0,r9 ; lvx v1,r9,16 ; lvx v13,r9,32 ; lwz r10,48(r9)
         (copied onto the stack at r1+112 .. r1+160)
3b2894:  lwz r0,112(r8)                     ; r8 = r1 + count*4  -> table[count]
3b2870:  cmpwi cr7,r11,1                    ; r11 = [0x01385cdc+0x64]
3b289c:  li r0,4                            ; if that field == 1, wait is FORCED to 4 s
```

Table at `0x00e7d340` (verified bytes
`00000000 00000004 00000008 0000000f 00000014 00000019 0000001e 00000023
00000028 00000032 00000032 00000032 00000000`):

```
index (count):  0  1  2   3   4   5   6   7   8   9  10  11  12
seconds:        0  4  8  15  20  25  30  35  40  50  50  50   0
```

Deadline = `t(RoomCreate) + 8.0 + table[count]` (the `8.0` is the float at
`0x01269cd4`, written into `0x01385850` by `FUN_003b7d70` at `0x003b7e80`).
That reproduces the measured 12.04 s / 12.03 s at count 1.

Because the wait is recomputed every frame from the *current* count, raising
`table[1]` only lengthens the lone-host window — the instant the joiner's P2P
link comes up, `table[2]` applies and the deadline collapses to `t+8+table[2]`,
which is already in the past, so the gate fires immediately. That is exactly the
behaviour we want.

### The three forms

| VMA | file offset | original | new | meaning |
|---|---|---|---|---|
| `0x00e7d344` | `0x00e6d344` | `00 00 00 04` | `00 00 00 3c` | `table[1]`: 4 s → 60 s |
| `0x00e7d348` | `0x00e6d348` | `00 00 00 08` | `00 00 00 3c` | `table[2]`: 8 s → 60 s |

**a. patch.yml** — the second block in §4a
(`"Factions: extend host lobby wait window (60s at 1-2 players)"`).

**b. Live poke** — Debugger → Memory Viewer at `0x00e7d344`, write
`0000003C 0000003C`. This is plain data (the `lvx` loads it fresh every frame),
so it takes effect immediately with no recompilation concerns. Do it before the
host creates its room.

**c. Raw file edit** —
`offset 0x00E6D344: 00 00 00 04 00 00 00 08  ->  00 00 00 3C 00 00 00 3C`
(same EBOOT.BIN caveat as §4c).

**Known limitation:** if `[0x01385cdc + 0x64] == 1` the wait is forced to 4.0 s
and this patch does nothing. Check that field (§3.4) before blaming the patch.

---

## 8. Confidence

| Claim | Confidence |
|---|---|
| `0x003b7ab8` is `bl 0x0039f1e0` and its result is the min compared at `0x003b7ac0`; bytes `4b fe 77 29` | **Certain** (disassembled + bytes read from file) |
| `0x0039f1e0` has exactly one caller in the whole `.text` | **Certain** (exhaustive `bl` scan of all 18.7 MB) |
| `modeCfg+0x14` is read at exactly one instruction (`0x0039f200`) | **Certain** (dataflow sweep of all 35 `bl 0x349360` sites; no other `+0x14` load) |
| Patching `bl` → `li r3,2` is register-safe at that site | **High** (LR spilled to stack, `r3` dead on entry, `r3` consumed 8 bytes later) |
| No second minimum-players check downstream (VOTE screen, in-game) | **High** (`FUN_003b19c4` has 2 callers total; state-21 handler fully read; the other count comparisons are vs EXPECTED (a full-room `>=` check) and vs `FUN_003a44ac`, whose value can only be 1 or 2) |
| Next state after the lobby gate = 21 = `NET_SM_SERVER_VOTE_SCREEN`, `net-matchmaking.cpp:1017` | **High** (state constant + name-string slot resolved, method cross-validated on the known state-17 site) |
| `cfg+0x18` EXPECTED == 8 for the live mode | **High** (wire `max_players=8` traced to `bl 0x39f218` → arg 5 of RoomCreate) |
| **`cfg+0x14` MIN == 6** for `deathmatch` (Supply Raid) and `elimination` (Survivors) | **High** — bytes read out of `dc1/net.bin`; container shape (`count=4, base=0x6308`) and 0x5C stride match the disassembly exactly; `+0x18 == 8` cross-checks against the live wire; array is unique in the whole DC corpus |
| StringId = CRC-32 MSB-first, poly `0x04C11DB7`, init 0, no final XOR | **High** (re-computed here: 6/6 known hashes exact, incl. `0xC1B0BE0D`, `0x3C3647D2`, `0x0B70ED28`) |
| `cfg+0x54 == 0` in shipped data ⇒ the start-gate short-circuits to SERVER_VOTE_SCREEN and team-balance never runs | **High** (field read from all four records; branch polarity disassembled) |
| Interrogation absent from this disc build | **High** (only 4 playlist records exist; no title update installed) |
| Two unused 2-player playlist records (`0xA8EE9C4F`, `0x240E467D`) exist in shipped data | **High** on their existence and values; **Unknown** on their names and whether they are usable (§9) |
| `[0x01385cdc+0x64]` semantics (0 = not forced, 1 = forced-1 **and** 4 s wait, N = forced-N) | **High** (both use sites disassembled) |
| `0x01385D40` is the debug menu's **"Force Matchmaking Min Players"** value, and `+0x64` is read at only 2 instructions binary-wide | **High** (`FUN_003c8154` computes `&(0x01385d76 - 54)` = `0x01385d40` = `struct+0x64`, byte-exact; whole-binary field sweep of the struct) |
| `0x01385D68` = **"Disable Min Player Limit"**, and it is *not* on the host gate path | **Medium-High** (`&(0x01385d76 - 14)`; its two readers are map/game-type availability helpers, not the gate) |
| The setting's submenu is registered under the `"multi-player-menu"` path | **High** (`FUN_00353e34` @ `0x00353f28` loads `0x00e5eb88` and calls `FUN_003c8154` at `0x00354110`) |
| The stock RPCS3 "Debug Menu" patch actually surfaces that submenu in-game | **Unverified** — plausible, untested |
| Lobby wait table `{0,4,8,15,…}` at `0x00e7d340`, deadline `t+8.0+table[count]` | **High** (disassembled; predicts 12.0 s vs measured 12.04/12.03 s) |
| RPCS3 loads `*_patch.yml` from `patches/`; addresses are effective addresses = VMAs | **High** (glob string in `rpcs3.exe`; existing TLOU entries in `patch.yml` use VMAs; repo's own `BLUS41045_patch.yml` works this way) |
| Patch makes a 2-player counted game *possible* | **High** on this gate; **Medium** end-to-end — the residual blockers are the `0x136`/P2P rendezvous and the game-end drop, not the minimum |

---

## 9. Appendix A — the two unused 2-player playlists (a different lever, untested)

Records 0 and 1 in §3.0 are **already-shipped 2-player playlists**:
`min = 2`, `expected = 2`, `teamSize = 2`, `+0x24 = 1` (passes the
`FUN_003881d0` enable predicate). Neither key is referenced anywhere else in
`net.bin` — `deathmatch` and `elimination` each get 5 further references in the
tasks/medals blobs, these get none. Their names could not be recovered
(CRC-32 preimage search is exhaustive to 6 chars with no hit and useless beyond
that).

If the client could be made to select key `0xA8EE9C4F` or `0x240E467D`, you would
get a legitimately 2-player-startable playlist with **no min patching at all** —
and `expected = 2` would also make RoomCreate advertise `max_players=2`, and
`teamSize = 2` a clean 1v1.

The mechanism is already in the binary. `FUN_0039abdc` (`0x0039abdc`) picks the
key:

```
39abec:  3d 60 0b 70   lis     r11,0x0B70          ; sid("test") -- a playlist that
39abf8:  61 6b ed 28   ori     r11,r11,0xED28      ;   DOES NOT EXIST in shipped data
39ac00:  81 3e 80 5c   lwz     r9,-32676(r30)      ; 0x0132c530
39ac04:  88 09 37 1c   lbz     r0,14108(r9)        ; override byte [0x0132c530+0x371c]
39ac0c:  41 9e 00 0c   beq     cr7,0x39ac18        ; flag == 0 -> normal path (mode+0x2F8)
39ac10:  91 7f 00 00   stw     r11,0(r31)          ; flag != 0 -> use the constant
```

`sid("test") = 0x0B70ED28` — a leftover dev playlist name with no record on disc,
so the override as shipped would select nothing. Repointing it at record 0 is
three words:

| VMA | file offset | original | new | meaning |
|---|---|---|---|---|
| `0x0039abec` | `0x0038abec` | `3d 60 0b 70` | `3d 60 a8 ee` | `lis r11,0xA8EE` |
| `0x0039abf8` | `0x0038abf8` | `61 6b ed 28` | `61 6b 9c 4f` | `ori r11,r11,0x9C4F` |
| `0x0039ac0c` | `0x0038ac0c` | `41 9e 00 0c` | `60 00 00 00` | `nop` — take the override path unconditionally |

**Do not lead with this.** It swaps the entire mode config, and those two records
are unreferenced by the tasks/medals data, so map lists, scoring and progression
are all unknowns — it could just as easily produce a lobby with no selectable
maps. The `0x003b7ab8` patch changes one number and nothing else. This is
recorded because it is the only route to a 2-player game that is arguably
*intended* by the shipped data, and it is worth an experiment once the
rendezvous work is done.

Note the corollary for the server side: none of the four playlist keys appear as
EBOOT immediates (only `0xC1B0BE0D` ×4 and `0x0B70ED28` ×1 do), so the active
playlist key always comes from runtime state, never a compiled-in constant.

---

## Appendix B — resolved runtime globals used above

net-matchmaking CU anchor `r30 = *(r2-31056) = 0x01271b1c` (`r2 = 0x01305870`).

| slot | value | role |
|---|---|---|
| `0x01269b28` | `0x01383bd8` | SessionManager / search+room object |
| `0x01269b54` | `0x0137d700` | gameMgr (the discarded `id` arg) |
| `0x01269b58` | `0x013835c0` | NetInfo |
| `0x01269b5c` | `0x01385660` | SM room object (`r28` in the gate) |
| `0x01269b6c` | `0x013858b0` | abort flag |
| `0x01269ba0` | `0x00e7d340` | lobby wait table base |
| `0x01269ba4` | `0x01385cdc` | **global developer-settings struct** (`+0x59`, `+0x64`, `+0x8c`, `+0x8f`) |
| — | `0x01385d40` | `struct+0x64` = **"Force Matchmaking Min Players"** (u32) |
| — | `0x01385d68` | `struct+0x8c` = "Disable Min Player Limit" (bool) |
| — | `0x01385d76` | `struct+0x9a` = "Show Debug Traffic" (bool) |
| `0x0126a234` | `0x00e7dd28` | `"Force Matchmaking Min Players"` label |
| `0x01269bfc` | `0x00e7aa78` | `"NET_SM_SERVER_LOBBY"` |
| `0x01269c24` | `0x0138562c` | (used by the start transition) |
| `0x01269c54` | `0x013858b8` | vote-screen byte flag |
| `0x01269ca4` | `0x01385850` | lobby timer base (`t(create)+8.0`) |
| `0x01269cd4` | float `8.0` | lobby base wait |
| `0x01269cf4` | `0x00e7d608` | `"NET_SM_SERVER_VOTE_SCREEN"` |
| `0x01291a04` | `0x01463720` | DC reflection registry object |
