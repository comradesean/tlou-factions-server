# The "match counts" latch g_70[0x6C]: what sets it, the counted-game predicate, and why our matches never satisfy it

Extends `2026-08-17-supplies-and-survivor-state.md` (the top gate at `0x3f2194`
that skips the entire match-end crediting body of `FUN_003f208c` unless
`g_70[0x6C] || g_84[0x1A4D] || g_8c[0]`). That note asked: **what SETS
`g_70[0x6C]=1`, and why doesn't it happen in our stubbed matches?** This note
answers it, instruction-level against the quoted EBOOT plus a decisive read of
the live RPCS3 TTY log.

Address convention: VMA = file offset + 0x10000. Anchors resolved via the
task-manager-online unit small-data base `r30 = *(0x01305870-30960) = 0x01272f78`
(`tools/eboot_analysis/scan_anchor.py`), so e.g. `-32656(r30)` → slot
`0x0126afe8` → object `0x013835c0` (g_70). Every address below was read off
`powerpc64-linux-gnu-objdump` disassembly, not guessed.

---

## 0. TL;DR — the matches are CUSTOM (private) games, which are not stats-eligible

1. **`g_70[0x6C]` has exactly ONE setter in the whole EBOOT: `0x3f020c`**, inside
   `FUN_003f00c8` (an *unnamed transient state* — record index 2 — of the 11-state
   in-match sub-machine in `task-manager-online.cpp`). All eight other callers of
   the byte-setter `FUN_003abf70` write offset `0x6C` on **different** objects
   (`0x0132c530`, `0x01231258`), never g_70. So the latch is armed by, and only
   by, this one code path. (Confidence: **high**.)

2. **The arming predicate is a client-internal post-match check**, not a server
   message or room attribute:
   `g_70[0x6C]=1` iff, in `FUN_003f00c8`,
   `sess[0xB4]==0` **and** `FUN_0039d188(gameMgr) == 0` (the match is no longer
   "active") **and** `sess->vtable[0x48](&out); out > 4500`. `sess` is the match
   session object at `taskMgr+4`. (Confidence: **high** on the mechanism; **medium**
   on the exact meaning of the `>4500` magnitude — see §2.)

3. **The decisive live-log finding: even a fully-completed, normally-ended match
   credits nothing here, because every live-tested match is a CUSTOM game.** The
   RPCS3 log shows the lobby always routes through
   `NET_SM_CUSTOM_GAME_HOST_WAIT_INFO` (lobby-flow.cpp:1539) — i.e. the *Custom
   Game* menu path — and a complete 4-round Survivors match that reached
   `NET_SM_ROUND_RESULTS` ×4 and finally `NET_SM_RESULTS` (line 1236) still left
   every `profile.21` match field at 0 (per the supplies note's decrypted
   profiles). Custom/private games in TLOU Factions are **not** counted for
   supplies/XP/clan/journey — they never arm this latch. That is the root cause,
   and it matches the shipped game's design. (Confidence: **high** empirically;
   **medium** on the exact flag that couples "custom" → "latch not armed".)

4. **Two independent failure layers, both present:**
   - **Primary (applies even to perfectly-completed matches): the game is a
     custom game → not counted.** Fix = get the client into a **matchmade /
     public-playlist** game, which requires the stub to implement the
     matchmaking flow (currently absent).
   - **Secondary (recent sessions): the match doesn't even reach `NET_SM_RESULTS`.**
     It takes the abnormal-leave exit `task-manager-online.cpp:1526 → NET_SM_LEAVE_GAME`
     ("Leaving Game 1 0 20462552"), driven by `FUN_003ee6b4` returning non-zero.
     For 2-player this is the game-end P2P `sceNpSignaling 0x8002a810` collapse
     (`2026-08-17-join-party-p2p-collapse-signaling-deactivation.md`); for solo
     it is an ordinary user-quit because a solo Supply Raid / Survivors match can
     never reach its win condition (no opponents to score against / eliminate).

**Net:** this is **not** fixable by seeding `profile.21` or by a single RoomCreate
field. The latch is set by the client's own settlement of a *counted* game; the
server's lever is to make the client play a **matchmade** game instead of a
custom one (plus keeping the P2P link alive to match-end). See §5.

---

## 1. The unique setter and the exact trigger chain

### 1.1 Setter site (verified)

`FUN_003abf70` = `stb r4,108(r3); blr` — a generic "write byte at +0x6C".
`FUN_003abf68` = `lbz r3,108(r3); blr` — the matching reader. Nine `bl 0x3abf70`
call sites exist (`scan_bl.py 3abf70`); their `r3`/`r4`:

| site | object (r3 via anchor) | r4 | is it g_70? |
|---|---|---|---|
| `0x34b538`,`0x353430`,`0x354278`,`0x354f90` | `0x0132c530` (`-32616`) | 1/0 | no |
| `0x3af7a8`,`0x3b0a14`,`0x3b0ea4` | `0x01231258` (`-32664`) | 1 | no |
| `0x3555bc` | r31 (passed-in) | 1 | no |
| **`0x3f020c`** | **`0x013835c0` (`-32656`)** | **1** | **YES — g_70[0x6C]=1** |

`0x3f020c` is in `FUN_003f00c8`; `fnglobals` confirms `0x3f0204 lwz r3,-32656(r30)`
→ slot `0x0126afe8` → `0x013835c0`. This is the **only** write to g_70[0x6C].

### 1.2 What `FUN_003f00c8` is (record 2 of the in-match sub-machine)

`FUN_003f00c8` is the per-frame **update handler** for state record index 2 of an
11-entry state table at `0x01224760` (records are 0x30 bytes; the update handler
is at record offset `0x2c`, the enter handler at `0x24`; the table base pointer
lives at small-data slot `0x0126afb4 → 0x01224748`, ticked by the dispatcher at
`~0x3edcd8`). The records map to NET_SM states by their enter handler (each enter
logs `GOTO NET_SM_x`):

| rec | enter | update | NET_SM |
|---|---|---|---|
| 0 | `0x3ef21c` | `0x3efa68` | ROUND_RESULTS |
| 1 | `0x3ef358` | `0x3f04b0` | RESULTS |
| **2** | **`0x3ef1dc`** | **`0x3f00c8`** | **(unnamed — no GOTO)** |
| 5 | `0x3f0b34` | `0x3f0268` | RESET |
| 6 | `0x3f1c0c` | `0x3f10b8` | UPDATE (in-match) |

Record 2's enter `FUN_003ef1dc` does only two things: `FUN_003963e0(0)` and
`stb 0,180(sess)` — i.e. it clears `sess[0xB4]`, the phase byte `FUN_003f00c8`
keys on. So record 2 is a short transient "settle / decide-if-counts" state, not
a screen (hence no log line).

### 1.3 The arming predicate (control flow of `FUN_003f00c8`, verified)

`this = taskMgr`; `sess = *(taskMgr+4)`.

```
0x3f00f4  r3 = sess; bl 0x3ee6b4      ; abnormal-leave check → if !=0 return
0x3f0114  if sess[0xB4]!=0  -> 0x3f017c (deadline branch)
0x3f012c  bl 0x39d188(gameMgr 0x0137d700)  ; "is match still active?"
0x3f013c  if ret != 0  -> refresh a 300/900-tick watchdog deadline, return
0x3f0240  (ret==0, match inactive) if sess[0xB4]==0 -> 0x3f01cc
0x3f01cc  r3=&out; r4=sess; call sess->vtable[0x48](&out,sess)   ; sret value
0x3f01f8  r0 = out
0x3f01fc  cmpwi r0,4500
0x3f0200  ble  -> skip (return, latch NOT set)
0x3f0204  r3 = g_70;  r4 = 1
0x3f020c  bl 0x3abf70                 ; g_70[0x6C] = 1  ← THE LATCH
```

So the latch is armed only when the match has gone **inactive**
(`FUN_0039d188(gameMgr)==0`) and the session object reports a per-match magnitude
**> 4500** via virtual slot `0x48`. `FUN_0039d188` = `obj->m->m->vtable[0]()` on
the task-manager-online game-manager singleton `0x0137d700`; while it returns true
the state just refreshes a watchdog, so record 2 is the "wait for the match to
finish, then decide whether it counted" step.

### 1.4 Downstream: the crediting bail (already established, re-confirmed)

`FUN_003f208c` reads the latch at `0x3f2184 (bl 0x3abf68, r3=g_70)` and, at
`0x3f2194 (beq 0x3f3500)`, skips its entire matches/wins/supplies/`OnMatchEnd`
body when `g_70[0x6C]==0 && g_84[0x1A4D]==0 && g_8c[0]==0`. With record 2 never
arming the latch, the body is skipped → zero everything. (This is the §2 gate of
the supplies note; here we've found *why* the latch input is 0.)

---

## 2. The "counted game" predicate and its inputs

The predicate is **client-authoritative and two-part**:

**(a) The match must reach the NORMAL-END path (→ NET_SM_RESULTS), not the
abnormal-leave path.** In the in-match update `FUN_003f10b8` (record 6,
NET_SM_UPDATE), match end is decided at `0x3f1620`:

```
0x3f1620  r3 = sess; bl 0x3ee6b4          ; abnormal-leave detector
0x3f1638  if ret==0 -> 0x3f16fc (normal)  else fall through (abnormal)
   abnormal: 0x3f16a8 printf "Leaving Game %i %i %i"  -> line 1526 GOTO NET_SM_LEAVE_GAME
   normal:   0x3f16fc r3=sess,r4=0; bl 0x3ee9d8       ; "win condition met?"
             if !=0: 0x3f1758 printf "Leaving Game Normally" -> line 1236 GOTO NET_SM_RESULTS
             else: keep playing
```

`FUN_003ee9d8` (the normal-end test) reads `sess[0xB5]`/`sess[0xB0]` and
`gameMgr[0x49E0]/[0x49E4] == 3` (game-over state), i.e. it fires only when the
gameplay/DC simulation declares the round/match over by its win condition.

**(b) Even on the normal-end path, the game must be a COUNTED game.** A custom /
private game runs the identical `NET_SM_UPDATE → RESULTS` machinery but does not
arm `g_70[0x6C]`. The `>4500` slot-0x48 magnitude in §1.3 is the concrete gate
that fails for a non-counting game (see confidence note below).

**Inputs that decide (a)/(b):**
- **Lobby route** — `NET_SM_CUSTOM_GAME_*` (Custom Game menu) vs
  `NET_SM_START_MATCHMAKING` (public playlist). This is chosen by the player's menu
  selection *and* is the only route the stub currently supports (custom).
- **Win-condition reachability** — needs real opposing players (matters for solo).
- **P2P/session liveness at match end** — an abnormal peer/session drop forces
  the LEAVE_GAME exit regardless of (b).

> Confidence: The *mechanism* of §1 (the unique setter and its predicate) is
> **high**. That **custom games are the non-counting class** is **high**
> empirically (the completed 4-round custom match crediting nothing; consistent
> with the shipped game). The precise coupling — whether "custom" makes
> `sess->vtable[0x48]()` return ≤4500, or makes `FUN_0039d188` never go false, or
> keeps record 2 from being entered — is the one link **not** pinned statically
> (the `sess` vtable is a heap type). Pin it live via §6.

---

## 3. Why our matches don't satisfy the predicate — solo and 2-player

Read directly off the RPCS3 TTY log (`GOTO NET_SM_*` and "Leaving Game…" lines):

- **Every match is a custom game.** Counts over the captured log:
  `NET_SM_CUSTOM_GAME_HOST_WAIT_INFO ×11`, `CUSTOM_GAME_LOAD_SCREEN ×13`, …,
  vs `NET_SM_START_MATCHMAKING ×1` (which produced **no** match). The lobby always
  goes `CREATE_GAME_WAIT → SERVER_LOBBY → CUSTOM_GAME_HOST_WAIT_INFO → …`.

- **A completed custom match still credits nothing.** An earlier live test ran
  a full Survivors match:
  `Leaving Game Normally → ROUND_RESULTS (1360)` four times, then
  `Leaving Game Normally → RESULTS (1236)`. Per the supplies note the served
  profiles remained all-zero. So reaching RESULTS is necessary but **not
  sufficient** — the custom game never armed the latch.

- **Recent (revival) matches don't even reach RESULTS.** They end with
  `"Leaving Game 1 0 20462552"` → `task-manager-online.cpp:1526 → NET_SM_LEAVE_GAME`
  (the abnormal `FUN_003ee6b4 != 0` exit). The three printed ints are
  `g_84[0xB8]=1, g_8c[0]=0, g_84[16]=0x01381E58` (a .bss leave-context pointer) —
  a recorded leave, not a clean settlement.
  - **2-player:** the game-end `sceNpSignaling PEER_DEACTIVATED 0x8002a810`
    collapse (blank-NpId, the same event that ends the working invite path at
    game-end — see the P2P-collapse note) tears the session down as an abnormal
    leave before it can settle.
  - **Solo-host:** a solo Supply Raid / Survivors match has no opponents, so the
    win condition (`gameMgr state → 3` in `FUN_003ee9d8`) is never reached; the
    user eventually quits → abnormal leave. **A solo match is structurally
    non-countable** even before the custom-vs-ranked question.

So both cohorts fail, for compounding reasons: **custom (both) + abnormal-leave
(recent 2p via P2P collapse; solo via unavoidable quit).**

---

## 4. Is this something the server can set directly? (tracing one level further)

No single server datum flips `g_70[0x6C]`. Verified levers and dead-ends:

- **Not a RoomCreate/`SetRoomFlags` attribute.** The custom-vs-matchmade decision
  is a *client lobby-flow* branch (`NET_SM_CUSTOM_GAME_*` vs
  `NET_SM_START_MATCHMAKING`), taken from the player's menu choice, not read back
  from a room attribute at settlement time. Echoing a different room flag will not
  move the branch that the completed-custom-match evidence shows is decisive.
- **Not a results/settlement opcode we can inject.** The latch is written by the
  client's own record-2 update after `FUN_0039d188(gameMgr)` reports the match
  inactive; it is gated on the local `sess->vtable[0x48]()>4500` magnitude, which
  the server never supplies. The RESULTS state does wait on net events (event 261
  via `FUN_003c8f20` at `0x3f05a0`) and the abnormal detector polls event 279,
  but those feed the RESULTS/LEAVE routing, not the latch value.
- **What the server CAN do:** provide a working **matchmaking** path so the client
  enters a public/ranked game (the counted class) rather than a custom game, and
  keep the P2P/signaling link alive to match-end so a real match settles normally.
  The one `START_MATCHMAKING` attempt in the log did not produce a match, and a
  separate forced leave came from `net-matchmaking.cpp:596 → NET_SM_LEAVE_GAME` —
  i.e. matchmaking is not yet functional in the stub.

Conclusion: the **arming of the latch is client-internal**, but the **precondition
(be a matchmade game + reach a clean results settlement)** is squarely in the
matchmaking/signaling backbone the server owns. This is the project's scoped work,
not an unfixable client wall.

---

## 5. Concrete server work (proposed; do not edit the live stub here)

Ordered, cheapest-first. None is a `profile.21` edit.

1. **Confirm the two gates live (decisive, cheap) — see §6.** Prove (i) the
   completed-custom path reaches record 2 but `sess->vtable[0x48]()<=4500` (or
   `FUN_0039d188` never goes false), and (ii) the recent path never reaches
   record 2 at all (abnormal leave).

2. **Stand up the matchmaking flow in `tools/session_manager_stub.py`.** Target
   `net-matchmaking.cpp` (the `NET_SM_START_MATCHMAKING` path and the leave at
   `net-matchmaking.cpp:596`). The client must be able to matchmake into a
   *public playlist* Supply Raid / Survivors game (host-authorized public game or
   a joinable matchmade session) rather than the Custom Game host flow. This is
   the change that flips the game into the counted class. Concretely, capture and
   answer the matchmaking request/response opcodes the client emits after
   `START_MATCHMAKING` (`captures/tcp_catch.log`), mirroring how the working
   custom-game `CREATE_GAME_WAIT`/`SERVER_LOBBY` handshakes are already answered.

3. **Keep the P2P link alive through match-end** so a real 2-player matchmade
   game reaches `Leaving Game Normally → RESULTS` instead of the `0x8002a810`
   abnormal collapse. This is the signaling-deactivation fix already scoped in
   `2026-08-17-join-party-p2p-collapse-signaling-deactivation.md`.

4. **Two-player is required.** Solo cannot count (no win condition). Progression
   testing needs two matchmade clients completing a public game.

No stats/clan/leaderboard backend endpoint is needed for the local loop — once a
counted match settles, crediting and the `profile.21` PUT round-trip already work
(supplies note §3/§7).

---

## 6. Live-debug confirmation recipe (RPCS3 debugger / PPU breakpoints)

Flag bytes (unchanged from the supplies note):
- `g_70[0x6C]` (the latch) @ `0x0138362C`
- `g_84[0x1A4D]` @ `0x01385625`
- `g_8c[0]` @ `0x01305e84`

Break/watch sequence for a match played to its end:

1. **Crediting bail:** BP `0x3f2194` (`beq 0x3f3500`). Confirm the branch is taken
   and read the three flag bytes above — all 0 predicts the bail (matches the
   zero profiles).

2. **Latch state reached?** BP `0x3f01fc` (`cmpwi r0,4500`) in `FUN_003f00c8`.
   - If it **never hits**, record 2 (the latch state) isn't entered on this path
     → confirms the abnormal-leave / non-results route (recent matches).
   - If it hits, read `r0` = `sess->vtable[0x48]()`. `r0 <= 4500` proves the
     magnitude gate fails for this (custom) game; `r0 > 4500` would step to
     `0x3f020c` and set the latch.

3. **Active-gate:** BP `0x3f012c` (`bl 0x39d188`); inspect the return. If it stays
   non-zero across the whole post-match window, the match is treated as still
   "active" and the latch check is never reached.

4. **RESULTS vs LEAVE routing:** BP `0x3f1628` (`bl 0x3ee6b4`) in the in-match
   update and watch `0x3f1634 beq 0x3f16fc`. Branch NOT taken (r3!=0) ⇒
   abnormal ⇒ "Leaving Game %i %i %i" ⇒ NET_SM_LEAVE_GAME. Branch taken ⇒ normal
   ⇒ `FUN_003ee9d8` decides RESULTS.

5. **Cross-check in the TTY log** (`.../log/RPCS3.log`, `grep -a`): a counted run
   must show `NET_SM_START_MATCHMAKING` producing a match and end with
   `Leaving Game Normally → task-manager-online.cpp:1236 GOTO NET_SM_RESULTS`
   (never `1526 GOTO NET_SM_LEAVE_GAME`, never `CUSTOM_GAME_HOST_WAIT_INFO`).

---

## 7. Confidence summary

**High (raw disasm + live log):**
- `g_70[0x6C]` has a single setter, `0x3f020c` in `FUN_003f00c8` (record 2 of the
  in-match sub-machine); all other `FUN_003abf70` callers target other objects.
- Arming predicate = `sess[0xB4]==0 && FUN_0039d188(gameMgr)==0 && sess->vf[0x48]()>4500`.
- `FUN_003f208c` bails at `0x3f2194` when the three flags are 0.
- In-match update routes RESULTS vs LEAVE_GAME via `FUN_003ee6b4`/`FUN_003ee9d8`
  (`task-manager-online.cpp` lines 1236 / 1526, log-confirmed).
- All live-tested matches are custom games; a fully-completed custom match still
  credited nothing; recent matches take the abnormal-leave exit.

**Medium:**
- The exact semantics of the `sess->vf[0x48]()>4500` magnitude (match
  time/score/points), and the precise mechanism by which "custom game" makes it
  fail vs "matchmade" — to be pinned by §6 step 2. The empirical "custom ⇒ not
  counted" conclusion is independent of this and stands.
- 2-player abnormal leave = the `0x8002a810` P2P game-end collapse (strong
  cross-evidence, but the exact `FUN_003ee6b4` branch should be confirmed live).

**Not established (needs matchmaking stood up, not more EBOOT work):**
- The matchmaking request/response opcodes to make the client enter a public
  counted game; the one `START_MATCHMAKING` attempt did not produce a match.

## Deliverables
- This note.
- Evidence: EBOOT disassembly via `tools/eboot_analysis/`; RPCS3 TTY log
  (`GOTO NET_SM_*`, "Leaving Game …"); the decrypted-profile findings in
  `2026-08-17-supplies-and-survivor-state.md`.
