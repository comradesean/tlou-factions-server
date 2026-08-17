# NpId resolution, the team-broadcast lifecycle, and how the faction model is *actually* picked

Follow-up to `2026-08-17-team-assignment-consistency.md` (team data path) and
`2026-08-17-character-customization-sync.md` (appearance). This pass answers:
where does the 36-byte SceNpId on an engine player come from, where does the
player-tracker's copy come from, when is `assign_team` (re)sent, what
`sync_players` (71) actually carries — and, added mid-pass, **how the renderer
chooses which faction skin to draw**.

Every address below was read as decompiled C and/or raw PPC disassembly this
session (`powerpc64-linux-gnu-objdump`, `file_off = VMA − 0x10000`; vtables
resolved through the `.opd` double-deref). Raw dumps: `research/ghidra/nr_batchA.txt`,
`nr_batchB.txt`, `nr_batchC.txt`, `nr_spawn.txt`, `nr_flip.txt`, `nr_pref.txt`,
`nr_desc.txt`, `nr_faction_fn.txt`.

---

## Bottom line up front

1. **The cross-screen "we each see the other as a different character" symptom is
   retail-correct local presentation, not a team desync.** Proven at the
   instruction level: every player object carries **two** appearance blobs — one
   per team slot (`player+0x410` and `player+0x438`, 0x28 bytes each) — and the
   renderer selects between them with
   `index = clamp(player->team, 0) XOR g_swapFactionSkins`, where
   `g_swapFactionSkins` is computed **locally** as
   `(localPlayer.GetTeam() != BE32(profile+0x1adc))`. Accessor:
   **`FUN_003cd6fc` @ `0x003cd6fc`**. Consequence: `index` for the local player
   is *always* the local profile's own faction pick, and for anyone on the other
   team it is *always* the opposite. Two clients with different profile picks
   render the *same* player as different factions. `assign_team_desc` (opcode 19)
   ships **both** blobs per player over the wire (builder `FUN_0038b7c8`), which
   is exactly what a local-choice filter needs and would be pointless otherwise.
2. **The `-1` hypothesis is actively contradicted by the reported symptom.** With
   `team == -1` the index clamps to `0`, i.e. the un-resolved remote is drawn with
   the *team-0* skin — the same skin the local player uses whenever their own team
   is 0. In a 1v1 exactly one client is on team 0, so under the `-1` model at
   least one of the two players should have reported "we look identical." Both
   reported "different." (And if the joiner's *own* team were also `-1`, that
   client would see both players identical — also not reported.) So teams almost
   certainly *were* assigned in that match.
3. **NpId provenance is a single chain, entirely server-fed.** Engine player
   `+0x3c8` (36 bytes) is written by exactly one function, **`FUN_0039f75c`
   @ `0x0039f75c`**, always copying from the **player-tracker/room member slot's
   npid at `room+i*0x180+0x668`**. That slot is written by exactly one function,
   **`FUN_00ad33d8` @ `0x00ad33d8`**, from bytes **`[0:36]` of a Member (`0x131`)
   roster entry**. There is no P2P hello, no `sceNpSignaling` path, and no
   `sceNpManagerGetNpId` call in this chain — local and remote alike. **Our
   SessionManager roster is the sole source of the key `assign_team` matches on.**
4. **`assign_team` is not one-shot.** It is (re)broadcast at four host-gated
   sites, including a dedicated **late-join** variant (`FUN_00395bd0` @
   `0x00395bd0`, sets `event+0x14 = 1`) fired from the mid-match spawn admission
   loop `FUN_003ae428`, right after `FUN_003a0144` assigns the new player to the
   smaller team. A player who joins after the initial balance does get teamed and
   does get the broadcast.
5. **`sync_players` (71) carries no team.** Its Execute (`FUN_0040d720` @
   `0x0040d720`) resolves players by a **u32 player id**, not NpId, and only
   drives spawn/despawn plus two per-team score words. It is not a second team
   carrier.

---

## 1. Rendering: `faction skin = f(team XOR local flag)` — the decisive finding

### 1a. Faction ids and the team→faction map

The faction name table lives at **`0x012089d0`** (16 `const char*` slots),
recovered by scanning for pointers to the `game/faction.cpp` string block
(note: the customization note's string addresses are *file offsets*; VMAs are
`+0x10000`, e.g. `game/faction.cpp` is at VMA `0x00e5c368`):

| id | name | id | name |
|---|---|---|---|
| 0 | `object` | 8 | `marauder` |
| 1 | `threat` | 9 | `military` |
| 2 | `player` | 10 | `ellie` |
| 3 | `hunter` | 11 | `buddy` |
| 4 | `infected` | **12** | **`netAlly`** |
| 5 | `civilian` | **13** | **`net-team-0`** |
| 6 | `cannibal` | **14** | **`net-team-1`** |
| 7 | `firefly` | 15 | `dying-ally` |

Confirmed against the compiled `LookupFactionByNameId(...) == FactionId*()`
assert chain at `0x0002ef64` / `0x0002efd0` (`StringId(0x33ea0868) == 13`,
`StringId(0x372b15df) == 14`) and against the accessor thunks:

```
0002e204  li r0,12 ; stb r0,0(r9)      ; FactionIdNetAlly()
0002e218  addi r4,r4,13 ; stb r4,0(r9) ; FactionIdNetTeam(n) = 13 + n   <-- team -> faction
0002e22c  li r0,13                     ; FactionIdNetTeam0()
0002e240  li r0,14                     ; FactionIdNetTeam1()
```

All six callers of `FUN_0002e218` feed it **the subject player's own
`player+0x1dc`** and then hand the result to a virtual `SetFaction`/relationship
call — e.g. in the spawn path `FUN_003d3ebc`:

```
3d4140  lwz r4,476(r31)      ; player+0x1dc = team
3d415c  bl  0x2e218          ; FactionIdNetTeam(team)
3d4164  lbz r4,464(r1) ; ... ; (*(**(char_obj))+0x198)(char_obj, faction)   ; SetFaction
```

So the *logical* faction is a direct, un-filtered function of the team. **This is
not where the local filter lives** — which is why a naive "faction is direct"
reading is misleading.

### 1b. The filter: two appearance blobs per player, chosen with a local XOR

`FUN_003cd6fc` @ `0x003cd6fc` is the whole story (verbatim decompile):

```c
ulonglong _opd_FUN_003cd6fc(longlong player) {
  uVar1 = *(uint *)((int)player + 0x1dc);              // team
  uVar3 = (ulonglong)uVar1 & (longlong)((int)~uVar1 >> 0x1f);   // clamp(team, >=0)
  if (*(char *)(*(int *)(PTR_PTR_012fdf4c + -0x7fd8) + 0x34c) != '\0')
      uVar3 = ((abs(uVar3) - 1) << 0x20) >> 0x3f;      // flip 0<->1
  return player + uVar3 * 0x28 + 0x410;                // &player->appearance[idx]
}
```

i.e. **`&player->appearance[ clamp(team,0) ^ g_swapFactionSkins ]`**, blobs at
`player+0x410` and `player+0x438`, `0x28` bytes each. The same logic is inlined
in the two MP character-spawn functions:

* `FUN_003d3ebc` @ `0x003d3ebc` — `3d4030 lbz r0,844(r11)` (the flag) then
  `local_130 = *(undefined8 *)(param_1 + uVar8*10 + 0x104)` … five 8-byte loads,
  i.e. the 0x28-byte blob at `player + 0x410 + idx*0x28`, handed to the model
  build (`FUN_00041efc` / `FUN_009e98cc` → the character process).
* `FUN_003d475c` @ `0x003d475c` — identical, `3d4bc8 lbz r0,844(r11)`.

Consumers of the accessor: `FUN_0039e4f4` @ `0x0039e4f4` (precache: `FUN_003cd6fc(player)`
→ `FUN_0039e134`, which does the DC art lookups `FUN_00340088(mgr, blob[0],
blob[1], i, blob[k], 1)`) and `FUN_00314bec` @ `0x00314bec` (the "your squad"
screen — note it filters teammates by `piVar7[0x77] == localPlayer->0x1dc`, i.e.
same-team, and copies *their* `FUN_003cd6fc` blob).

### 1c. The flag is per-client, derived from the local profile

`g_swapFactionSkins` is the byte at `<presentation singleton>+0x34c`. It is
recomputed identically at three sites — `FUN_00395cfc` @ `0x00395e20` (host, as
it broadcasts `assign_team`), `FUN_0038e6bc` @ `0x0038eb48` (receiver, inside
`assign_team` Execute), and reset to 0 at `FUN_00378d14` @ `0x00378d5c` /
`FUN_002fb5b4` @ `0x002fb714`. Raw form (from `0x00395d9c`):

```
395d9c  bl 0x39a380                ; FUN_0039a380(GM, 0) -> LOCAL player object (GM+0x2c)
395dac  lwz r9,0(r9) ; lwz r9,24(r9) ; bctrl     ; vtable+0x18 = GetTeam()  [-> 0x003cd488]
395dd8  bl 0x3cb89c                ; -> local profile/savedata object
395de4..395e08                     ; v = BE32( profile + 0x1adc )   (four lbz, shifted)
395e0c  xor  r29,r29,r0            ; localTeam ^ v
395e10..395e1c                     ; flag = (r29 != 0)
395e20  stb  r0,844(r10)           ; g_swapFactionSkins
```

* `FUN_0039a380(GM, i)` returns `*(GM + 0x2c + i*4)` with a `0 <= i < 2` assert —
  the **local** player slot(s) (split-screen), written by `FUN_0039f75c` at
  `iVar8 + param_4*4 + 0x2c` when `FUN_00ad0ea4(PT, member_id)` says "this member
  is me."
* vtable slot `+0x18` on the player resolves through `.opd 0x012bdf48` to
  `0x003cd488`, which is literally `lwz r3,476(r3); extsw; blr` — `GetTeam()`.
  (Same vtable: `+0x04` → `0x3cd47c` = `return this+0x3c0`, the signaling handle;
  `+0x10` → `0x3ce654` = the "is active" predicate used by the `assign_team`
  builder.)
* `profile+0x1adc` is a big-endian u32 inside the local save/profile blob
  (`FUN_003cb89c(...) + 200`). It has ~30 read sites, **no byte-store writers** —
  it arrives as part of the loaded profile blob. `FUN_003410d0` @ `0x003410d0`
  reads the same field and feeds it to the *single*-appearance builder
  `FUN_00341d6c`, i.e. it is the profile's chosen character/faction identity.
  The `clan/hunter` / `clan/firefly` string pair (`0x00e7da50` / `0x00e7da60`,
  a 2-entry pointer table at `0x01269f5c`) is the metagame's name for the same
  binary choice.

**Net effect.** `displayIdx(P) = P.team ^ (localTeam != localFactionPick)`.
For `P == local`, that is identically `localFactionPick`. For any P on the other
team, it is `!localFactionPick`. Two clients that picked different journey
factions therefore draw **the same player as different factions** — and both
players see themselves as their own pick. Retail behaviour, byte for byte.

### 1d. Corroboration: the wire carries *both* skins, and VO is bucketed the same way

`FUN_0038b7c8` @ `0x0038b7c8` — the `assign_team_desc` (opcode 19) builder,
called per active player from `FUN_00395a18` @ `0x00395a18`:

```
event+0x18 .. +0x3f  <- player+0x410 (0x28 bytes)   ; appearance for team slot 0
event+0x40 .. +0x67  <- player+0x438 (0x28 bytes)   ; appearance for team slot 1
event+0x68 .. +0x87  <- player+0x8e4..0x900         ; loadout words
event+0x88 .. +0x97  <- player+0x8bc / +0x564 byte arrays
event+0x98/0x9c/0xa0/0xa4 <- player+0x1c4/0x1c8/0x2b0/0x540
```

A player sends **both** of its team-slot appearances. That only makes sense if the
receiver decides which one to show — exactly what `FUN_003cd6fc` does.

Independently, the VO/dialog selector `FUN_005b09e0` @ `0x005b09e0` maps a
character's faction byte (`obj+0xec`) into six speech buckets; every non-net
faction maps to a fixed bucket, but **`net-team-0` and `net-team-1` both fall
into a final branch that picks the "player/ally" bucket vs the "enemy" bucket via
a per-object bit test** (`(*(u64*)(obj->tags + (idx>>6)*8 + 0x18) >> (idx & 0x3f)) & 1`).
Same local-relative philosophy; matches the reported "faction voice callouts
mismatch over voice chat."

### 1e. Verdict on the symptom, and the discriminating test

**(a) retail-correct local presentation.** The observed 1v1 symmetric
"self = X, other = Y" is precisely what §1b–1c predict for correctly-assigned
opposite teams, and it is *not* what the `-1` model predicts (§BLUF-2).

Discriminators, cheapest first:

1. **Same-team pair (2v2, or 1v1 + a bot on your side).** Local-filter model:
   a teammate is drawn with *your* faction skin, always, regardless of what the
   teammate picked. `-1` model: a teammate stuck at `-1` renders at index
   `0 ^ flag`, which differs from your own index whenever your team is 1.
2. **Both players pick the SAME journey faction, then 1v1.** Local-filter: both
   still see self = that faction, other = the opposite (unchanged symptom).
   Combined with (1) this isolates the filter from the team value.
3. **Direct read of `player+0x1dc`** for the remote slot
   (`GM + i*0x920 + 0x40 + 0x1dc`). `-1` = never resolved; `0`/`1` = teams fine.
   This is the only unambiguous observation and is cheap under an RPCS3
   watchpoint.

Teams still matter for scoring, friendly fire, HUD/nameplate colour, spawn
selection and the "same team?" predicates (30+ read sites of `+0x1dc`, many of
them the paired `lwz rA,476(rX); lwz rB,476(rY)` compare-two-players idiom) — so
§2–§4 below remain load-bearing. They are just **decoupled from the model
mismatch**.

---

## 2. Task 1 — every writer of engine `player+0x3c8`

**There is exactly one writer: `FUN_0039f75c` @ `0x0039f75c`** ("acquire/initialise an
engine player slot"), signature `(GM, PT, npidPtr, controllerIdx, isBot)`:

```c
*(u64 *)(player + 0x3c8) = *(u64 *)param_3;          // npid[0:8]
*(u64 *)(player + 0x3d0) = *(u64 *)(param_3 + 0x08);
*(u64 *)(player + 0x3d8) = *(u64 *)(param_3 + 0x10);
*(u64 *)(player + 0x3e0) = *(u64 *)(param_3 + 0x18);
*(u32 *)(player + 0x3e8) = *(u32 *)(param_3 + 0x20);  // = 36 bytes total, 0x3c8..0x3eb
*(u32 *)(player + 0x3c0) = *(u32 *)(param_3 + 0xf0);  // signaling connection handle
*(u32 *)(player + 0x1a8) = *(u32 *)(param_3 + 0xe8);  // SessionManager member id
*(u32 *)(player + 0x3c4) = *(u32 *)(param_3 + 0xe4);  // tracker slot handle (monotonic)
*(u32 *)(player + 0x1ac) = param_4;                   // local controller index (0 online)
*(u8  *)(player + 0x1b0) = param_5;                   // is-bot
```

`param_3` always points at **`room_obj + i*0x180 + 0x668`**, the member slot's
NpId — which is exactly what `FUN_00ad1e64` returns (it returns `entry+0x668`,
not the entry base). The relative offsets line up: `param_3+0xe0` = `+0x748`
(the occupied byte), `+0xe4` = `+0x74c`, `+0xe8` = `+0x750`, `+0xf0` = `+0x758`.

All 7 call sites (`grep 'bl 0x39f75c'` over the full disassembly):

| site | containing fn | role | `param_3` source |
|---|---|---|---|
| `0x0038e814` | `FUN_0038e6bc` (`assign_team` Execute) | create engine player for a packed NpId that resolved in the tracker but not yet in GM | `FUN_00ad1e64(PT, blob)` |
| `0x003ad554` | `FUN_003ad4e8` | host-side "peer connected → make an engine player" | caller's arg (a tracker npid ptr) |
| `0x003596f0` | `FUN_003596a0` | match teardown/bot path | (in the block Ghidra prunes) |
| `0x0035a850`, `0x0035a938` | `FUN_0035a7dc` | **bot** creation (`param_5 = 1`); explicitly stamps `+0x1dc = -1` | `FUN_00ad0e40(PT)` |
| `0x003b29e4`, `0x003b79a8` | `FUN_003b2994`, `FUN_003b7920` | match-flow resets | — |

`FUN_003ad4e8` @ `0x003ad4e8` has a single caller, `0x0034ed44` inside
`FUN_0034eaec` @ `0x0034eaec` — a SessionManager member event handler that is
gated on `FUN_00ad0eec(room)` (AmIHost) and a global state `== 0x1f`. It receives
the tracker npid pointer as `param_2` and uses `param_2+0xf0` (signaling handle),
`param_2+0xe8` (member id), `param_2+0xec`.

**There is no other source.** No `sceNpManagerGetNpId` and no P2P hello writes
`+0x3c8`; the *local* player's NpId also comes from the roster (its member slot),
found via `FUN_00ad0ea4(PT, member_id)`.

---

## 3. Task 2 — every writer of the tracker npid at `+0x668`

**One writer: `FUN_00ad33d8` @ `0x00ad33d8`** (`AddMember(room, desc, is_local,
is_owner)`), 12 slots of stride `0x180`:

```
dedupe :  for i in 0..11: if occupied(room + i*0x180 + 0x748)
                          && strcmp(room + i*0x180 + 0x668, desc + 4) == 0
                          -> RETURN existing handle, UPDATE NOTHING   (first-write-wins)
alloc  :  first free slot i
npid   :  room+i*0x180+0x668 .. +0x68b  <- desc+0x04 .. desc+0x27      (36 bytes, 9 words)
blob52 :  room+i*0x180+0x68c .. +0x6bf  <- *(desc+0x28)[0..0x33]
blob128:  room+i*0x180+0x6c0 .. +0x73f  <- *(desc+0x2c)[0..0x7f]   (if non-NULL)
         room+i*0x180+0x740 (u64)       <- *(u64*)(desc+0x30)
         room+i*0x180+0x748 (u8)        <- 1                        (occupied)
         room+i*0x180+0x74c (u32)       <- room[0x67a]++             (slot handle)
         room+i*0x180+0x750 (u32)       <- *(u16*)(desc+0x38)        (MEMBER ID)
         room+i*0x180+0x754 (u32)       <- *(u8 *)(desc+0x40)
         room+i*0x180+0x758 (u32)       <- signaling_connect(desc+4) ONLY if is_local == 0
         room+i*0x180+0x760/0x764       <- len / <=0x40 bytes from *(desc+0x48)  (if desc+0x4c==1)
         room+0x19ec                    <- this slot's member id, if is_local
         room+0x19f0                    <- this slot's member id, if is_owner
```

Callers (4 sites, 2 functions):

* **`FUN_00ad7604`** @ `0x00ad79d0` / `0x00ad7c20` — the SessionManager receive
  dispatch. `0x131` **Member** and `0x132` RoomJoined. This is the path our stub
  drives, and it is already fully documented in `protos/0x131_member.ksy`:
  **roster entry bytes `[0:36]` land verbatim at `+0x668`**, entry `+36` (u16) is
  the member id → `+0x750`, and the `is_local`/`is_owner` flags come from
  XOR-comparing that member id against the header's `local_ref_id`/`owner_ref_id`.
* **`FUN_00ad40e8`** @ `0x00ad4888` / `0x00ad4a60` — an internal event-queue
  dispatcher (event codes `0xca`, `0xcb`, `0xce`, …) that walks records of stride
  `0x74` and builds the same descriptor: **npid from record `+0x08 .. +0x2b`**,
  member id from record `+0x34` (u16), `is_local` from `+0x38`, `is_owner` from
  `+0x39`. Not the path our stub uses.

So the answer to "what exact bytes land at `+0x668`" is: **the first 36 bytes of
each `0x131` Member roster entry** — of which, because `FUN_00e459bc` is a plain
word-at-a-time **strcmp** (verified previously; `research/ghidra/npid_compare.txt`),
**only the NUL-terminated handle prefix is ever compared.** Trailing
`opt`/`reserved` bytes are irrelevant to matching (they still get copied into
`player+0x3c8` and re-broadcast, but nothing compares them).

---

## 4. Task 3 — the `assign_team` broadcast lifecycle

### 4a. `FUN_0038b924` (builder) gating, corrected

Per engine slot `i = 0..7` (`FUN_003994ac(GM, i)`), packs at running index `n`
only if: `player+0xa8 != 0`, vtable `+0x00` predicate true, `player+0x3f4 == 0`,
**and `player+0x203 != 0`** (team-has-been-set). Packed fields as previously
documented, plus:

* `event+0x160 + n` = `bool(player+0x1ac != 0)` — and `player+0x1ac` is the
  **local controller index** (`FUN_0039f75c` `param_4`, also the index into the
  `GM+0x2c` local-player array). Online it is `0` for every player, so this byte
  is always `0`.
* `event+0x188` = `*(GM + 0x4994)`.

### 4b. Execute `FUN_0038e6bc` — the skip condition is narrower than assumed

```c
p  = FUN_0039b3fc(GM, &blob[i], flag[i]);   // GM-side resolve
t  = FUN_00ad1e64(PT, &blob[i]);            // tracker resolve -> &entry.npid
if (p == 0 || p->0x3f4 != 0) {
    if (t != 0) {                            // <-- CREATES the engine player
        FUN_00ad15b0(t, flag, FUN_00ad2650(PT, &blob[i]));
        p = FUN_0039f75c(GM, PT, t, flag[i], 0);
        p->0x201 = 1; p->0x3f4 = 0; ...
        goto apply;
    }
    if (p != 0) goto apply;
    /* p == 0 AND t == 0  ->  SKIP, team stays -1 */
} else goto apply;
apply:  FUN_003cf6d8(p, team[i], 0, aux[i]);   // player+0x1dc = team
```

So a slot is dropped **only when both resolves fail**, i.e. the receiver has no
tracker member slot whose handle strcmp-matches the packed handle *and* no
existing engine player with that handle. If the tracker has it, Execute *builds*
the engine player on the spot. `FUN_0039b3fc` additionally requires
`flag[i] == *(int*)(GM + i*0x920 + 0x1ec)` (`player+0x1ac`) — both sides are `0`
online, so this is a no-op in practice.

### 4c. Where balance + broadcast fire

| trigger | site | what runs |
|---|---|---|
| match-flow state `0x2e` | `FUN_0035bfbc` → `FUN_00358ca0` @ `0x00358ca0` | `FUN_003a482c` (balance) + `FUN_00395cfc` (18) + `FUN_00395a18` (19) |
| match-flow state `0x30` | `FUN_0035bfbc` @ `0x0035c290` → `FUN_00358b08` | host-gated (`FUN_00ad0eec`): balance + 18 + 19; then advances to state `0x31` |
| round/phase restart | `FUN_003b4694` @ `0x003b47b8`, `FUN_003b8b70` @ `0x003b8db0` | host-gated (`FUN_003abe70`): balance + 18 + 19 |
| **mid-match join / spawn admission** | `FUN_003ae428` @ `0x003ae5f0` | `FUN_003a0144` (team the ONE new player) → **`FUN_00395bd0`** (18, late variant) → `FUN_00395a18` (19) → `FUN_003958f0` → `FUN_00395270(peerConn, 0x11f, …)` |

`FUN_0035bfbc` reads the match state via `FUN_003471dc()`; the `FUN_00358b08`
call is reached only on the exact value `0x30`, so *that* site is one-shot per
state entry — but it is not the only site.

**`FUN_00395bd0` @ `0x00395bd0`** is the previously-missed late sender. Same
constructor + same `FUN_0038b924` builder, then:

```
*(u8 *)(event + 0x14) = 1;                      // "late" flag
event[0x62] (= +0x188) = *(*(g) + 0x1c);        // overrides the builder's GM+0x4994
FUN_003a1f50(GM, event);                        // enqueue to peers
FUN_003a64b4(GM, 1, 0, 2, 0, 0);
```

`event+0x14` is the discriminator all over Execute: `0` = bulk assignment,
`1` = late/respawn variant (extra spawn bookkeeping, `FUN_003e7148`,
`FUN_00adac44`, and the `GM+0xc = event+0x188` write).

**`FUN_003a0144` @ `0x003a0144`** is the single-player balancer used on that path:
it finds the player by network id, counts live players per team via the
`GetTeam()` vcall, and calls `FUN_003cf6d8(player, (count0 <= count1), 0, freeSlot)` —
i.e. puts the newcomer on the smaller team.

---

## 5. Task 4 — `sync_players` (opcode 71) decoded

Factory trampoline `0x00390088` (table `0x0038ec40`, index 71) → constructor
**`FUN_0040a840`** @ `0x0040a840`, object size **`0x330`**, `obj+4 = 71`, vtable
**`0x01225398`**:

| slot | code | role |
|---|---|---|
| `+0x00` | `0x0040e16c` | re-stamp base vtable |
| `+0x04` | `0x0040e130` | destructor |
| `+0x08` | `0x0040a720` | **Deserialize** |
| `+0x0c` | `0x0040a604` | **Serialize** |
| `+0x10` | `0x0040d720` | **Execute** |
| `+0x14`/`+0x18` | `0x00acb460`/`0x00acb30c` | inherited NetEvent send/queue → **P2P** |

Layout (from Serialize `FUN_0040a604` / Deserialize `FUN_0040a720`):

```
obj+0x320 : u32                      ; team-0 aggregate
obj+0x324 : u32                      ; team-1 aggregate
obj+0x010 : count, 5 bits            ; number of player records
per record r = obj + 0x20 + i*0x60   ; 8 records reserved (ctor loops obj+0x20..0x320 step 0x60)
  r+0x50 : u32   player network id   ; the KEY
  r+0x54 : bool  alive/spawned
  r+0x55 : u8
  if (r+0x54)  FUN_00387fd8/FUN_00387d74(bs, r)   ; 0x50-byte transform/spawn sub-record
```

Execute `FUN_0040d720`:

```c
FUN_0039a4ec(GM, 0, obj+0x320);   FUN_0039a4ec(GM, 1, obj+0x324);   // per-TEAM data
for (i < count) {
  p = FUN_0039f3d8(GM, r->id_at_0x50);            // resolve by u32 id, NOT NpId
  if (!p || !p->vtbl[0x10](p,0)) continue;
  p->0x2ac = r+0x55;
  if (!r->alive) { despawn; p->0x22c = 300; }
  else if (needs respawn) FUN_003d1c74(p, 0, 1, r);
}
```

**No team field, no NpId, no resolve-and-skip.** It is a spawn/liveness/score
bulk sync. It cannot repair or corrupt a team assignment.

---

## 6. Task 5 — synthesis, and what the SessionManager must guarantee

**Which failure explains "remote team stayed −1 for a whole match while gameplay
synced"? Most likely none — the premise is probably false** (§1e). The reported
observable does not require any team failure, and under a genuine `team == −1`
the *same* observable would not have been symmetric.

If a future direct read of `player+0x1dc` does show `-1` for a remote, the only
mechanism left (given §4b) is: **the receiver's room-member table has no
occupied slot whose NpId handle strcmp-matches the handle the host packed.**
Everything else self-heals — a missing engine player is *created* from the
tracker slot inside Execute, and a stale/late player gets a fresh broadcast from
`FUN_003ae428`. Concretely the receiving client needs, before the broadcast lands:

1. A `0x131` **Member** entry for the remote player whose first 36 bytes contain
   the remote's NpId **handle string**, byte-identical (up to the NUL) to the
   handle in the *host's* copy of that same roster — because the host packs
   `player+0x3c8`, which it copied from *its* Member entry for that player. The
   server is the sole source of both, so this is a server-side consistency
   invariant, not a client-side one: **every recipient's roster must carry the
   same handle bytes for a given member** (including that member's own entry —
   `populate_self_npid` must be on, or the two sides key on different bytes).
2. `is_local` / `is_owner` derived from `local_ref_id` / `owner_ref_id` correctly
   per recipient (already true) — `is_local == 0` is what opens signaling and
   fills `+0x758`, which becomes `player+0x3c0`.
3. Beware `FUN_00ad33d8`'s **first-write-wins dedupe**: once a slot exists for a
   handle, a later Member with corrected bytes for that same handle updates
   nothing. A member registered with a *wrong* handle can never be fixed — only
   a room teardown clears it. (Same hazard already flagged for `0x132`
   RoomJoined's hardcoded `is_local=0, is_owner=0`.)
4. Nothing else. There is still **no SessionManager field that carries team**,
   and `assign_team` / `assign_team_desc` / `sync_players` remain pure P2P.

Also worth recording for the appearance work: because `assign_team_desc` (19)
ships *both* of a player's team-slot appearance blobs, an empty/zeroed
customization on either side shows up as a default skin in **both** slots — a
distinct, separately-diagnosable failure from the faction filter of §1.

---

## 7. Confidence

**High**

* `FUN_003cd6fc` = `&player->appearance[clamp(team,0) ^ g_swapFactionSkins]`;
  blobs at `player+0x410` / `+0x438`, `0x28` bytes; same logic inlined in both MP
  spawn functions `FUN_003d3ebc` / `FUN_003d475c`.
* `g_swapFactionSkins` (`<singleton>+0x34c`) `= (localPlayer.GetTeam() != BE32(profile+0x1adc))`,
  computed at `0x00395e20` and `0x0038eb48`; `GetTeam()` = player vtable `+0x18`
  = `0x003cd488` = `return this+0x1dc`; `FUN_0039a380(GM,0)` = the local player.
* `assign_team_desc` (19) builder `FUN_0038b7c8` copies **both** `+0x410` and
  `+0x438` onto the wire.
* Faction ids: `netAlly=12`, `net-team-0=13`, `net-team-1=14`; `FUN_0002e218` =
  `FactionIdNetTeam(n) = 13+n`; all its callers feed the subject's own `+0x1dc`.
* Sole writer of `player+0x3c8` is `FUN_0039f75c`, always from
  `room+i*0x180+0x668`; sole writer of that is `FUN_00ad33d8`, always from
  Member-entry bytes `[0:36]`.
* `assign_team` Execute skips a slot **only** when both resolves fail; otherwise
  it creates the engine player from the tracker slot.
* `assign_team` is re-sent at 4 host-gated sites incl. the late-join variant
  `FUN_00395bd0` (`event+0x14 = 1`) driven by `FUN_003ae428` + `FUN_003a0144`.
* `sync_players` (71) = vtable `0x01225398`, ctor `0x0040a840`, Ser `0x0040a604`,
  Deser `0x0040a720`, Exec `0x0040d720`; keyed by u32 player id; **carries no team**.

**Medium**

* That `profile+0x1adc` is specifically the Hunters/Fireflies *journey* pick
  rather than some other 0/1 profile flag. It is a BE32 in the profile blob with
  no local store site, it is XORed against a team index, and `FUN_003410d0` feeds
  it to the single-appearance builder — all consistent, but the save-layout
  offset was not traced to a UI write.
* That the 1v1 symptom is *definitely* case (a) rather than a coincidence: the
  argument in §1e is a strong elimination, not a direct measurement. The
  `player+0x1dc` watchpoint (or the same-team test) settles it.

**Not established**

* Whether `FUN_003ae428`'s late-join branch is reached on our stub's join
  sequence at all (it is gated on `FUN_003a4324` / `FUN_003a41a0` plus
  `player+0x3fe`/`+0x201`) — i.e. whether a mid-setup joiner actually gets the
  late broadcast in practice.
* The semantics of the tracker's 52-byte (`+0x68c`) and 128-byte (`+0x6c0`)
  member blobs beyond what `protos/common/member_data.ksy` already covers.
* The internal event path `FUN_00ad40e8` (stride-`0x74` records, npid at `+0x08`)
  — which subsystem feeds it, and whether it can ever race the `0x131` path.
