# Supplies, the clan metagame credit path, and survivor/population state

Root-causing why finishing a match credits **zero supplies**, and mapping where
the clan/survivor metagame state actually persists. Evidence-first, with the
decisive datum being two **decrypted, live-captured `profile.21` records** read
off disk (`tools/served_content/profiles/{comradesean,mgnomad2}/profile.21`),
cross-checked against raw EBOOT disassembly.

Address convention: **VMA = file offset + 0x10000**. Record offsets are written
`P+0x…`, where `P` = the 0x5028-byte `m_tusData` base returned by the universal
accessor `FUN_003cb89c` (`this+200`). Payload byte `k` = `P+8+k`. All EBOOT
addresses below were read off `powerpc64-linux-gnu-objdump` disassembly of the
quoted EBOOT and re-verified, not guessed.

---

## 0. TL;DR — the root cause is NOT what was first hypothesised

The three prime hypotheses going in were (a) clan/journey not *started*, (b) a
game-mode/result guard, (c) a missing backend stats POST. **The decrypted live
profiles falsify all three as the primary cause and point somewhere else:**

1. **The clan roster IS already initialised.** Both players' profiles carry
   **5 survivors** (`P+0xA38 = 5`), five real survivor name-seeds, and a
   population high-water of 5 (`P+0x1E30 = 5`). So an empty-roster / "clan not
   created" theory is dead — the clan-creation menu ran and persisted.
2. **Every match-progression field is still ZERO** after a completed
   Supply Raid *and* a completed Survivors match: matches-played `P+0x1E34 = P+0x1E38 = 0`,
   wins `P+0x1E4C = P+0x1E50 = 0`, journeys `P+0x1E44 = 0`, clan-started
   `P+0x1E28 = 0`, and every population accumulator/high-water that
   `ClanManager::OnMatchEnd` touches *except* the menu-written one is 0
   (`P+0x1BE0 = P+0x1E20 = P+0x1E24 = P+0x1E54 = 0`).
3. **Therefore the match-end handler `FUN_003f208c` never ran its crediting
   body at all.** matches-played is incremented *near-unconditionally* (only a
   `mode==2`/`==3` split gates *which* of the two counters moves), so for BOTH
   counters to remain 0 across two different modes, execution is being cut off
   **before** the increment block — at the session-flag gate at the top of the
   function (`beq 0x3f3500`), not at the supplies math.

**Root cause (high confidence):** the match is not being recognised as a
*counted / stats-eligible online match*. `FUN_003f208c` bails at its top gate
because the NetInfo session-state flag it checks (`g_netInfo[0x6C]`, read via
`FUN_003abf68`) is 0, and the two companion "this match counts" flags
(`g_84[0x1A4D]`, `g_8c[0]`) are also 0. With the body skipped, nothing —
matches, wins, population, or supplies — is credited, and `OnMatchEnd` is
never reached. Fixing this is a **match/session-state** problem, not a
profile-seeding or backend-stats problem.

Supplies specifically: even once the body runs, the per-match supply total is
handed to `ClanManager::OnMatchEnd` as an argument and folded into the
DC-script-driven clan economy; **there is no single literal `profile.21`
offset called "supplies_acquired_lifetime"** — it is a DC "net-stat" variable
(the `net-tus-variable.cpp` / `IncrementDcNetStat` layer), stored in the record
at a registry-assigned index, not a hard displacement. See §4.

---

## 1. The decisive evidence: two decrypted live profiles

Decrypted with the project's own codec (LZF → Blowfish-ECB with the solved
`SECRET_KEY`; round-trips cleanly, HMAC-bearing). Values are BE u32 at `P+off`.

| Field (`P+off`) | meaning | comradesean | mgnomad2 |
|---|---|---|---|
| `0xA38` | **survivor roster count** | **5** | **5** |
| `0xA3C+i*8` | survivor name-seeds (u64) | 5 populated | 5 populated |
| `0x1B04…` | per-survivor state bitfield | **all zero** | **all zero** |
| `0x1BE0` | population high-water (OnMatchEnd) | 0 | 0 |
| `0x1E20` | population accumulator (OnMatchEnd) | 0 | 0 |
| `0x1E24` | accumulator high-water (OnMatchEnd) | 0 | 0 |
| `0x1E28` | **clan-started flag** | **0** | **0** |
| `0x1E30` | population high-water (**menu-written**) | **5** | **5** |
| `0x1E34` | matches played, mode A | **0** | **0** |
| `0x1E38` | matches played, mode B | **0** | **0** |
| `0x1E44` | journeys completed | **0** | **0** |
| `0x1E48` | (per-player; healthy count?) | 4 | 5 |
| `0x1E4C` | wins, mode A | 0 | 0 |
| `0x1E50` | wins, mode B | 0 | 0 |
| `0x1E54` | population high-water (OnMatchEnd) | 0 | 0 |
| `0x1BF0` | (clan/faction state?) | 2 | 2 |
| `0x300` | lobby title/badge | 0 | 0 |

**The tell:** `P+0x1E30 = 5` but its OnMatchEnd siblings `P+0x1BE0`, `P+0x1E54`
(all `= max(field, population)` in the same settlement pass — see §3) are 0.
So `0x1E30` was written by a *different* path (the clan-creation menu,
`FUN_0037a7b4`, called from menu sites `0x350198`/`0x350950`, which writes the
roster count at `0x37a868`), while **`OnMatchEnd` — which would have moved
`0x1BE0`/`0x1E54`/`0x1E20` — never executed.** That is independent confirmation
of the §0 conclusion.

The roster count is also written by `FUN_00378a24` (`stw …,2616(r3)` at
`0x378b34`), which `OnMatchEnd` calls at `0x37d530` for recruit/casualty — but
since `OnMatchEnd` never runs, only the menu writer's value (5) survives.

---

## 2. The match-end handler and its top gate — where zero comes from

`FUN_003f208c` (`game/net/task-manager-online.cpp`) is the match-end
stat/progression routine (the work behind the "Save Game Stats" thread; the
RPCS3 log shows `NET_SM_ROUND_RESULTS` → `NET_SM_RESULTS` → a `Save Game Stats`
thread that runs only ~800 instructions and exits — consistent with an early
return). Its confirmed record writes (all via `FUN_003cb89c`):

| EBOOT | writes | guard |
|---|---|---|
| `0x3f2598` | `P+0x1E34` matches-A `++` | `FUN_003a3d40(...) == 2` |
| `0x3f2654` | `P+0x1E38` matches-B `++` | `FUN_003a3d40(...) == 3` |
| `0x3f25f8` | `P+0x1E4C` wins-A `++` | team match + result `== 3` |
| `0x3f26b4` | `P+0x1E50` wins-B `++` | " |
| `0x3f2700` | `P+0x0A1C` `++` | always |
| `0x3f2750` | `P+0x0A20` `++` | result `== 3` |
| `0x3f2494`→`0x3f2510` | `record[8+(statIdx+581)*4] ++` | DC net-stat write (§4) |
| `0x3f27c4` | calls `ClanManager::OnMatchEnd` | supplies path (§3) |

### The gate that skips all of it

Top of the function (`0x3f2164`–`0x3f2194`), verified instruction-by-instruction:

```
lbz  r0, 6733(g_84)     ; g_84 = *(-32636) = 0x01383bd8 ; [0x1A4D]
cmpwi 0 ; bne 0x3f2198  ; if g_84[0x1A4D] != 0  -> run body
lbz  r0, 0(g_8c)        ; g_8c = *(-32628) = 0x01305e84
cmpwi 0 ; bne 0x3f2198  ; if g_8c[0]      != 0  -> run body
mr   r3, g_70           ; g_70 = *(-32656) = 0x013835c0  (NetInfo/session state)
bl   0x3abf68           ; FUN_003abf68: return g_70[0x6C]   (byte getter)
cmpwi 0 ; beq 0x3f3500  ; if all three are 0  -> JUMP PAST THE ENTIRE BODY
```

So the body runs **iff** `g_84[0x1A4D] != 0` **or** `g_8c[0] != 0` **or**
`g_70[0x6C] != 0`. With a fresh online match in the revival environment all
three read 0 → jump to `0x3f3500` → **nothing is credited.** This matches the
profiles exactly (every match field 0).

- `FUN_003abf68` is a one-line accessor: `lbz r3,108(r3); blr` — returns
  `g_70[0x6C]`. Its sibling setter `FUN_003abf70` (`stb r4,108(r3); blr`) is
  called from ~9 state-transition sites, one of them `0x3f020c`, immediately
  before this handler in the same task-manager unit. `g_70` (`0x013835c0`) is
  the NetInfo/`TaskManagerOnline` session-state object (getters/setters at
  offsets 0x50/0x68/0x6C/0x74/0x7C; the object also backs `FUN_003abe80`, which
  returns `g_70[0x7C]` and gates a mid-function `Publish`).
- `g_84[0x1A4D]` is a companion "don't count / abnormal end" flag: at the very
  top of the same handler (`0x3f211c`), *if* `g_84[0x1A4D] != 0` the code forces
  `g_8c[0] = 1`. Both then also force the **zero-supplies** branch in §3.

**Interpretation (confidence: medium-high).** `g_70[0x6C]` is the
"this was a real, stats-eligible online match" latch, set as the match state
machine transitions into a counted online game and cleared otherwise. In the
solo-host RPCN revival — where the session-manager/matchmaking is stubbed and
the match is likely seen as private/unranked/host-authoritative — that latch is
never set, so the handler treats every finished match as a non-counting game.

**Secondary possibility (kept, not primary).** `FUN_003a3d40` (the mode
discriminator) is a DC-gametype-table lookup: it hashes a DC symbol
(`0x3b9a067d`), indexes a 112-byte descriptor table, and reads
`g_mission[0x8D]` (`0x01385cdc`). If the current match has no valid gametype
descriptor it can return a value that is **neither 2 nor 3**, in which case even
a body that *did* run would move no matches-played counter. But this cannot be
the whole story here, because the *unconditional* counters `P+0x0A1C` and the
DC-stat writes are also 0 — only a body that never executed explains that. Mode
mismatch would still leave those nonzero. So the top gate is primary; verify
both live (§7).

---

## 3. Supplies storage and the OnMatchEnd credit path

`FUN_003f208c` credits supplies by calling **`ClanManager::OnMatchEnd`** — the
function whose true entry is `0x37d6f0` (`mfcr r12` prologue; body continues at
`0x37d6f4`, i.e. the routine previously labelled `FUN_0037d6f4` in
`net-clan-manager.cpp`). Two call sites, and the choice between them is the
supplies gate:

```
0x3f21f8:  OnMatchEnd(clanMgr, 0, 0)                 ; zero-supplies variant
0x3f27c4:  OnMatchEnd(clanMgr, r4, r5)               ; r5 = *(taskMgr+4) = match supply total
```

The selector at `0x3f2754`–`0x3f2770`:

```
if (g_84[0x1A4D] != 0)  -> zero path
else if (g_8c[0]  != 0) -> zero path
else                    -> OnMatchEnd(clanMgr, FUN_003e4c14(...), *(taskMgr+4))   ; REAL supplies
```

So **real supplies are credited only when `g_84[0x1A4D] == 0 && g_8c[0] == 0`** —
the same flags that (with `g_70[0x6C]`) gate the whole body. The per-match
supply total is `*(taskMgr+4)`, the task-manager's accumulated supply score for
the match (the parts→supplies conversion having already been applied upstream in
gameplay/DC code — the EBOOT here only carries the final integer).

### What OnMatchEnd does with it, and where "lifetime supplies" lives

`OnMatchEnd` (`0x37d6f4`) `operator new`s a heap **clan-event object** (`r28`)
and stores the supply value into it: raw at `+76` (`stw r25,76(r28)`), a scaled
copy at `+72` (`fmuls` by a per-event factor, `0x37d8a8`). It then runs the
**clan-day settlement** against the profile, whose record writes are:

| EBOOT | record write | semantics |
|---|---|---|
| `0x37d948` | `P+0x1AD4 ++` | day/settlement counter |
| `0x37da4c` | `P+0x1AD8` | " |
| `0x37e340` | `P+0x1BE0 = max(·, pop)` | population high-water |
| `0x37e38c/…3f0` | `P+0x1E30 = max(·, pop)` | population high-water |
| `0x37e430` | `P+0x1E20 += pop` | population accumulator (guarded) |
| `0x37e4f4` | `P+0x1E24 = max(·, P+0x1E20)` | accumulator high-water |
| `0x37e6b8` | `P+0x1E28 = 1` | **clan-started** (set, not required) |
| `0x37e6f4` | `P+0x1E44 ++` | journeys |
| `0x37e740` | `P+0x1E54 = max(·, pop)` | population high-water |

**Crucially, none of these is "add supply total to a lifetime counter."** The
supply integer goes into the heap clan-event object and is consumed by the
DC-script clan economy (recruiting / feeding / heal), which stores its running
totals as **DC net-stats**. The EBOOT's DC-stat storage is visible at
`0x3f2494`: `record[8 + (statIdx + 581)*4] ++`, i.e. DC net-stats occupy the
record from ≈`P+0x91C` upward, indexed by a registry-assigned `statIdx`
(resolved via `FUN_0036655c` from the DC stat table `0x0137a9dc`). **The
gear-gating `supplies_acquired_lifetime` is one of these DC net-stats**; its
exact index/offset is not recoverable from the EBOOT alone (it lives in the DC
`.pak` modules — same limitation the profile note already flagged for the
`net-tus-variable` named-variable layer). This is consistent with there being
no `supplies` string and no literal supply displacement anywhere in the EBOOT.

### OnMatchEnd's own early-out

Independently, `OnMatchEnd` opens (`0x37d778`–`0x37d808`) by looping over the
roster (bound by the profile count near `P+0xA38`) counting survivors whose
per-survivor bit (in the live clan-singleton bitfield, base
`*(clanSingleton)+6916+…`, mask `1<<(i&31)`) is set, into `r27`; if `r27 == 0`
it jumps to `0x37e778`, **skipping the whole settlement.** With the persisted
state bitfield `P+0x1B04` all-zero (see §1) and the live clan bits presumably
likewise unset outside an active journey, this is a *second* reason nothing gets
credited even if the handler body did run. So there are two layers to clear:
the match must count (§2), and the roster must have event-eligible survivors.

---

## 4. Is starting a clan / journey a prerequisite? (init question)

**No profile seeding of a "started clan" is required, and it would not fix the
symptom.** Evidence:

- The roster is already created client-side by the metagame menu
  (`FUN_0037a7b4` → roster count 5, name-seeds, `P+0x1E30=5`), with **no
  backend dependency** in that path. The client self-initialises the clan when
  you enter Factions and pick a faction; the served profiles prove it already
  did.
- `clan-started` (`P+0x1E28`) is a **result**, not a precondition: `OnMatchEnd`
  *sets* it to 1 (`0x37e6b8`) the first time it settles a match with eligible
  survivors (alongside `journeys++`). Nothing reads it as a gate before
  crediting. Seeding `P+0x1E28=1` in a served profile therefore changes
  nothing about whether a match credits.
- So the "does the profile need a started-clan/active-journey seeded, or does
  the client self-init?" question resolves to: **the client self-inits the
  roster; the missing piece is not profile state at all, it's the match being
  flagged as counted (§2)**, after which `OnMatchEnd` sets clan-started and the
  journey advances on its own.

(If a future served profile *is* generated from scratch rather than
round-tripped, seed `P+0xA38 = 5` and five `P+0xA3C+i*8` name-seeds to mirror a
menu-created clan; but that is bootstrap parity, not the fix.)

---

## 5. Survivor health-state and population field locations

- **Population count.** Roster count = `P+0xA38` (u32; currently 5). Persisted
  high-water marks at `P+0x1BE0`, `P+0x1E30`, `P+0x1E54` (each
  `= max(field, livePopulation)`), plus a cumulative accumulator at `P+0x1E20`
  and its high-water `P+0x1E24`. The **live** population is computed from the
  roster in the clan singleton, not read from a single profile scalar. Changes
  (recruit/casualty) are applied by `FUN_00378a24` (writes `P+0xA38`), called
  from `OnMatchEnd` (`0x37d530`) — i.e. population only moves when a match
  settles, which currently never happens.
- **Survivor roster structs are live, 72 bytes each**, in the clan-manager
  singleton (`0x01389a38` region): `mulli r9,r9,72` at `0x37e598`, base
  `*(clanSingleton)`, indexed by survivor number. The **healthy/hungry/sick/dead
  state is a field inside these 72-byte structs** (the settlement loop tests a
  per-survivor bit at struct-relative offset 16), **not** a clean profile
  scalar.
- **Persisted survivor state is a packed bitfield in the record** around
  `P+0x1B04` (the array the settlement loop indexes as `6916+(i>>5)*4`), with
  the other dense stat regions the profile note listed (`0x1BB8–0x1BF3`,
  `0x1CF8–0x1D13`). In the captured profiles `P+0x1B04 = 00…00` — no survivor
  has been driven to a non-default state yet, again because no day has settled.
- `P+0x1E48` differs per player (4 vs 5) and `P+0x1BF0 = 2` for both — likely a
  healthy-count and a faction/clan-state respectively, but **not pinned this
  pass** (they are menu-written; low priority for the supplies question).

**Verdict:** the survivor mini-game is *both* live-computed (72-byte structs,
transient per-day state) *and* profile-persisted (packed bitfield + counts at
`P+0x1B04…/0xA38`). It is driven entirely by `OnMatchEnd`/DC settlement, so it
is frozen at its initial state until matches start counting.

---

## 6. `userdata/<npid>.txt.crypt` — verdict

Confirmed **not** a clan-init or supplies channel. Its consumer `FUN_00ada3ac`
is a generic line-oriented text/config parser (calls the tokeniser `0xe56a2c`
and allocator `0x915a30`); its callers (`0x804a8`, `0x7f1708`, `0xada7d0`) are
generic config sites — **none in `net-clan-manager.cpp` (`0x37xxxx`) or
`net-player-data.cpp` (`0x3cxxxx`)**. It is download-only (173 GETs / 0 PUTs),
so it structurally cannot hold mutable supplies, and nothing in the clan or
profile path reads it. Serving `200 OK` empty (current behaviour) is correct;
leave it alone. This matches the earlier profile note's characterisation.

---

## 7. Concrete fix plan

The problem is **match-state recognition**, not profile content or a backend
call. Order of work:

1. **Confirm the gate live (cheap, decisive).** With RPCS3, at the moment the
   match reaches `NET_SM_RESULTS`, read the three flags:
   - `g_70[0x6C]` at `0x013835c0 + 0x6C = 0x0138362C` (byte)
   - `g_84[0x1A4D]` at `0x01383bd8 + 0x1A4D = 0x01385625` (byte)
   - `g_8c[0]` at `0x01305e84` (byte)
   The §0 prediction is all three read 0. Also read `FUN_003a3d40`'s return /
   `g_mission[0x8D]` at `0x01385cdc+0x8D` to confirm the mode is a real 2/3.
   (A conditional breakpoint at `0x3f2194` and observing the `beq 0x3f3500`
   being taken is the single cleanest confirmation.)

2. **Make the match count.** The fix is to drive the online-match state machine
   through the transition that latches `g_70[0x6C] = 1` (via `FUN_003abf70`).
   That transition is owned by the session/matchmaking flow the revival stubs —
   i.e. the same `net-session-manager` path the parallel live-testing work is on.
   The likely missing signal is the server-side acknowledgement that this is a
   *ranked/counted* session rather than a private/unranked one. This wants
   confirmation against the session-manager stub's result/round-result handling
   (`NET_SM_RESULTS` = `task-manager-online.cpp:1236`, `NET_SM_ROUND_RESULTS` =
   `:1360`) rather than a profile edit. **Do not** try to fix this by seeding
   profile fields — the increments are what set those fields, and they are being
   skipped upstream.

3. **Once the body runs, supplies follow automatically.** With the gate open and
   `g_84[0x1A4D]==0 && g_8c[0]==0`, `OnMatchEnd(clanMgr, …, matchSupplyTotal)`
   fires, settles the day, sets `clan-started`, advances the journey, and the DC
   clan economy converts supplies → population and increments the
   `supplies_acquired_lifetime` DC net-stat that gates gear. No server-served
   supply value is needed; the client computes and persists it via the existing
   `profile.21` PUT round-trip.

4. **If a served/generated profile is ever needed for bootstrap** (not the fix,
   parity only): mirror the menu-created clan — `P+0xA38 = 5`, five
   `P+0xA3C+i*8` name-seeds, `P+0x1E30 = 5`. Leave `P+0x1E28` (clan-started) 0;
   the game sets it. Do **not** hand-set supply/population counters — let the
   client earn them once matches count.

**No stats/clan/leaderboard backend endpoint needs implementing for the core
loop.** The whole progression path is local + `profile.21` S3 round-trip; the
only "server" responsibility is making the session read as a counted match.
(Note: RPCS3's `Clans Enabled: false` in the Net config affects `sceNpScore`
clan *leaderboards* only — `sceNpScoreGetClansRankingByRange` etc. — not ND's
own S3-backed clan metagame; not the cause here, but worth flipping on when
leaderboards are tackled.)

---

## 8. Confidence

**High (decrypted live profiles + raw disasm):**
- Clan roster is initialised (5 survivors, name-seeds, `P+0x1E30=5`) yet every
  match-progression field is 0 → the match-end body never credited.
- `OnMatchEnd` never ran (its population siblings `0x1BE0`/`0x1E54`/`0x1E20`
  are 0 while the menu-written `0x1E30` is 5).
- The top gate at `0x3f2194` skips the entire body when
  `g_70[0x6C]==0 && g_84[0x1A4D]==0 && g_8c[0]==0`; `FUN_003abf68` returns
  `g_70[0x6C]`.
- Real vs zero supplies is selected by `g_84[0x1A4D]`/`g_8c[0]`; the per-match
  supply total is `*(taskMgr+4)`, passed as `OnMatchEnd`'s 3rd argument.
- Supplies are a DC net-stat (`record[8+(idx+581)*4]`), not a literal offset;
  no `supplies` string / displacement exists in the EBOOT.
- Population count `P+0xA38`; 72-byte live survivor structs in the clan
  singleton; persisted state bitfield `P+0x1B04`; clan-started `P+0x1E28` is set
  *by* `OnMatchEnd`, not required by it.
- `userdata/*.txt.crypt` is a generic config channel, not clan/supplies data.

**Medium:**
- The *semantic* of `g_70[0x6C]` as specifically "counted/ranked online match".
  The mechanism (it gates the body) is certain; the exact meaning and the state
  transition that should set it is inferred and needs the live read in §7.1 and
  a look at the session-manager result path.
- `FUN_003a3d40` returning non-{2,3} as a contributing factor — plausible but
  not primary (unconditional counters are also 0).

**Not established (needs DC `.pak`, not more EBOOT work):**
- The exact `statIdx`/record offset of `supplies_acquired_lifetime` and the
  other DC net-stats.
- The precise meaning of `P+0x1E48` (4/5) and `P+0x1BF0` (2).
- The per-survivor state encoding inside the 72-byte live structs and its exact
  packed form at `P+0x1B04`.

## Deliverables
- This note.
- Decrypted profile evidence read from
  `tools/served_content/profiles/{comradesean,mgnomad2}/profile.21`
  (via the project's LZF + `psarc_crypt` codec).
</content>
</invoke>
