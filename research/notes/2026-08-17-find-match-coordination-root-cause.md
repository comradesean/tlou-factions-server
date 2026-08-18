# find-match host/joiner coordination: root cause, verified timings, and the serialized-election design

Deep trace (2026-08-17) answering the blocker left open in
`2026-08-17-session-handoff.md`:
why two clients never resolve into one host + one joiner at the end of lobby
creation. Extends `2026-08-17-find-match-flow.md`. Every address below was read
off disassembly of the decrypted EBOOT, not guessed.

## ROOT CAUSE (TL;DR)

The host's SERVER_LOBBY member count is **not** derived from our `0x131` Member
roster's *contents* — it is derived from the **P2P connection state of each
rostered member**. `FUN_003b19c4` counts a member only if the net-connection
manager returns state `2` (established) for the connection handle stored at
`member+0xF0`, or if the member is the local player. Our roster push is what
*creates* that handle (the Member-apply code calls `mgr->Connect(npid)`), so it
is necessary — but it only converts into a count when a real P2P link comes up
and stays up.

Separately, the last run never even got that far: the stub **deliberately
withheld a `0x136`** from a client that was legitimately searching (it was
still flagged "public host" inside a 10 s abandon grace), parking it in
`GAME_LIST_WAIT` for the full 60 s timeout and destroying the run. That is a
stub bug, not a protocol gap.

---

## 1. Where the SERVER_LOBBY count comes from (answer to question A)

**Dispatch resolved (closes the prior note's open "state-code caveat"):**
current net-SM state code lives at **`0x0137968c`** (written by `FUN_00347160`,
read by `FUN_003471dc`). The per-frame dispatcher is `FUN_003b9244`; at
`0x003b99a4` it does `state-4`, bounds-checks `>41`, and indexes the jump table
at **`0x003b99cc`** (`lwz r9,-32224(r30)`, slot `0x01269d3c` = `0x003b99cc`).

Verified state ↔ code ↔ handler map (from that table + the `bl 0x347160` sites):

| code | state | handler |
|---|---|---|
| 4 | CREATE_GAME_WAIT | `FUN_003b4de0` |
| 5 | CLIENT_START (sends `0x135`) | `FUN_003b5ff4` |
| 6 | CLIENT_GAME_LIST_WAIT | `FUN_003b4bf4` |
| 7 | CLIENT_GAME_LIST_PICK | `FUN_003b6c78` |
| 8 | CLIENT_CONNECT_TO_HOST | `FUN_003b6584` |
| 10 | CLIENT_RESERVE_SLOTS_WAIT | `FUN_003b6404` |
| 13 | CLIENT_WAIT_FOR_PARTY_HOST_JOIN | `FUN_003b2dcc` |
| 15 | CLIENT_JOIN_GAME_WAIT | `FUN_003b48f8` |
| 17 | **SERVER_LOBBY** | **`FUN_003b7c0c`** |
| 19 | CHOOSE_HOST_JOIN | `FUN_003b3ad0(1)` — pure force-leave |
| 20 | START_MATCHMAKING | `FUN_003b8300` |
| 40 | LEAVE_GAME | `FUN_003b51a0` |

(The prior note named `FUN_003b7a78` as the SERVER_LOBBY handler; it is
actually the *gate* that `FUN_003b7c0c` tail-calls once its countdown expires —
that distinction is what explains the ~12 s.)

**The ~12 s is now exact.** `FUN_003b7c0c`:
- `0x003b7c78 bl 0x3b2810` → wait seconds.
- `0x003b7c8c` reads base `*(float*)0x01385850`; `0x003b7d08 fcmpu cr7,f30,f0`
  → if `base+wait >= now` **return** (keep waiting); else `0x003b7d48
  b 0x3b7a78` (run the count-vs-min gate).

`FUN_003b2810` (`0x003b2810`): `IsHost()==0 → 0.0`; else
`count = FUN_003b19c4()`, then `0x003b2894 lwz r0,112(r8)` picks
`lobbyWaitTable[count]` from the 13-int table at **`0x00e7d340`** =
`{0, 4, 8, 15, 20, 25, 30, 35, 40, 50, 50, 50, 0}` seconds; if
`*(u32*)(0x01385cdc+0x64)==1` it is forced to 4.

Base `0x01385850` is written at RoomCreate time by `FUN_003b7d70`
(`0x003b7e80`) as `t(create) + f30`, where `f30 = max(1.0, dcFloat)` with EBOOT
default **8.0** (float at `0x01269cd4`).

⇒ **teardown deadline = t(RoomCreate) + 8.0 + lobbyWaitTable[count]**
- count 1 → **12.0 s** (measured 12.04 / 12.03 s — dead on)
- count 2 → **16.0 s**, count 3 → 23 s, count 4 → 28 s, count 8 → 48 s

**The count itself — `FUN_003b19c4` @ `0x003b19c4`:**

```
r29 = *(0x01269b28) = 0x01383bd8            ; SessionManager room object
      = the SAME object the 0x135 search_obj_ptr points at
bl 0xad2768                                 ; enumerate roster: 12 slots, stride 0x180,
                                            ;   member rec at slot+0x668, active byte at +0xE0
bl 0xad0e40   -> r25 = MY member record
per member m (r28/r29):
  0x3b1a44  r4  = *(s32*)(m + 0xF0)                  ; <-- P2P CONNECTION HANDLE
  0x3b1a3c  r9  = *(*(0x01269b2c)) = *(0x0131a200)   ; net-connection manager singleton
  0x3b1a58  r0  = mgr->vtable[0x18]                  ; GetConnectionState(handle)
  0x3b1a64  bctrl
  0x3b1a70  cmpwi cr7,r3,2      <-- counted only if state == 2
  0x3b1a6c  cmpw  cr6,r28,r25   <-- ...or if it is me
  0x3b1a80  bl 0xad147c   = `li r3,0; blr` (stub) -> second increment term always 0
```

That the manager is the **P2P layer** is proven by identical vtable use
elsewhere on the same global:
- `FUN_003b2a9c` (CONNECT_TO_HOST entry, line 1194): `0x003b2bd8
  mgr->vtable[0x10](mgr, hostAddrBlock)` → handle stored at
  `0x01383bd8+0x1A48`; `0x003b2c10 vtable[0x14](mgr, handle)`.
- `FUN_003b6584` (CONNECT_TO_HOST poll): `0x003b65e8 vtable[0x18](mgr, handle)`
  — **1 = connecting, 2 = connected**, anything else = failed.
- **`FUN_00ad33d8`** (the `0x131` Member roster-apply, the `m_roomSize > 0`
  function): `0x00ad34b0-0x00ad34c4 handle = mgr->vtable[0x10](mgr,
  wireNpId)`; `0x00ad34e0 stw r3,240(r31)` → `member+0xF0`.
- `FUN_00ad3190` (member removal): `0x00ad3268 mgr->vtable[0x1c](mgr,
  member[0xF0])`; `0x00ad3290` sets `member+0xF0 = -1`.

**Verdict (high confidence):** the roster (*which* members exist) is 100 %
server-controlled by our `0x131`. The count (*which* members are counted) is
**P2P-gated**. A server message alone cannot hold the host in the lobby — but
it is not useless either: pushing the roster is exactly what makes the host
dial the peer. In the failed run's TTY the host did reach
`SCE_NP_SIGNALING_EVENT_EXT_MUTUAL_ACTIVATED mgnomad2` purely from our `[pair]`
roster push — and then lost it 16 s later (`PEER_DEACTIVATED 0x8002a810` →
`Kicking 'mgnomad2' out`). So: **a roster push can raise the count, but only
while a real, traffic-carrying P2P link exists; the link only stays up if the
genuine join handshake produced it.**

Also: `FUN_00ad33d8` de-dupes by NpId (first loop, `bl 0xe459bc`) and returns
early — re-pushing an *identical* roster does not reconnect; but a push that
*omits* a member tears its connection down (`vtable[0x1c]`) and the next push
redials. The 6 leaked 10 s refresher threads in the last run were doing exactly
this kind of churn.

---

## 2. After CONNECT_TO_HOST (answer to question B)

`FUN_003b6584` (state 8), on `vtable[0x18] == 2`:
1. gate `FUN_00358924(35)`;
2. read link quality `vtable[0x34]` / `vtable[0x30]` (ping/bandwidth — the TTY
   `Ping = 0 ms Bandwidth = …` line);
3. reject if ping ≥ a DC threshold (`FUN_009fa9f4(0xB25AB071)` record `+8`) →
   `FUN_003b5d00`;
4. else `0x003b6854 bl 0x3ca178` — **`FUN_003ca178(room_id, connHandle)`
   builds a message containing the whole SM member list (36 bytes/member via
   `FUN_00ad2768`) and sends it over the P2P connection: this is the
   slot-reserve / join request to the host**;
5. `0x003b68bc` writes `*(float*)0x0138594c = now + 6.0` (float `6.0` at
   `0x01269cbc`) — the reserve deadline;
6. line **1327** → state **10 CLIENT_RESERVE_SLOTS_WAIT**.

State 10 handler = **`FUN_003b6404`**: polls `FUN_003c8f20(0x101, …)` for the
**host's reservation reply** (a game-layer event record, arriving over P2P),
decodes it with `FUN_003c9228` (56 bytes), checks
`entry.room_id == NetInfo+0x98`, then `FUN_003b2f40(entry)` → SessionManager
**vtable+0x18 = `FUN_00ad6718` = the 88-byte `0x130 RoomJoin`** → line 1390 →
state 15 `JOIN_GAME_WAIT`. On the 6 s deadline: `FUN_003b26c0` → toast
`"Joining Request timed out"` (`0x00e7abc0`) → line 1400 → back to state 7
`GAME_LIST_PICK`.

**What the host sends the server during reserve: nothing.** The reserve
handshake is entirely peer-to-peer. The only SessionManager-visible artifact of
a successful join is the **joiner's `0x130`** — and the stub already handles it
correctly. An exhaustive tally over the final window found **zero**
unknown/unhandled opcodes (`0x12d`×2, `0x146`×2, `0x145`×48, `0x135`×48,
`0x12f`×9, `0x140`×17, `0x133`×8, `0x137`×7, `0x13a`×7, `0x130`×0, `0x134`×0).
The one damaging non-reply was deliberate — stub log line 15960:

```
parsed opcode=0x135 (find-match search) - this connection is already a public HOST;
not sending a game list (letting its SERVER_LOBBY wait run)
```

…sent to a client that had abandoned its room 4.8 s earlier and was a genuine
searcher.

---

## 3. Timing constraints (all verified in disassembly)

| Constraint | Value | Where |
|---|---|---|
| **`GAME_LIST_WAIT` max hold on a `0x136`** | **60.0 s**, then error dialog + `CHOOSE_HOST_JOIN`(19) → `LEAVE_GAME` | float `0x01269c48`; `FUN_003b4bf4` @ `0x3b4d10` `lfs f1,-32468(r30)` + `bl 0x347188`; line 1112 @ `0x3b4d74` |
| **Re-search backoff** (empty list → next `0x135`) | `1.0 + 2·rand()` s ⇒ **1–3 s** | `FUN_003b6c78` @ `0x3b6d64-0x3b6d80`; const `1.0` @ `0x01269c68`; matches measured 1.47–2.70 s |
| **Searches per burst before self-hosting** | DC value, **observed 5** (criteria 0…4) | `FUN_003b5e9c`; counter global **`0x013858b4`**; limit = `FUN_009fa9f4(0xB25AB071)[0]` |
| **Burst → self-host latency** | ~9–11 s | measured 32.28 → 44.08 s |
| **Host lobby deadline** | `t(0x12f) + 8.0 + table[count]` → **12.0 s at count 1, 16.0 s at count 2** | §1 |
| **`CONNECT_TO_HOST` timeout** | **30.0 s** | float `0x01269c38`; `FUN_003b6584` @ `0x3b660c` |
| **`RESERVE_SLOTS_WAIT` timeout** | **6.0 s** | float `0x01269cbc`; written to `0x0138594c` @ `0x3b68bc` |
| **`0x135` burst-position marker** | wire off `0x18` u16 = `5,10,10,0,0`; wire off `0x20` region = `"us","us",0,0,0` | raw captures in the stub log |

`CHOOSE_HOST_JOIN` is **not** a retry state — `FUN_003b3ad0` sets the abort
flag, drops the P2P handle, sends `0x133`, clears the matchmaking marker
(`FUN_003abe9c(NetInfo,0)`), and goes straight to `LEAVE_GAME` (line 596). The
observed re-search loop is `LEAVE_GAME`(40) → `FUN_003b51a0` → line 2032 →
`START_MATCHMAKING`(20) → host election `FUN_003b3318`.

---

## 4. Recommended stub design: serialized election via a withheld 0x136

Deterministic host/joiner designation. All timings above make this legitimate
and the budget generous.

1. **Elect deterministically.** On a `0x135` with `off18==5 && region=="us"`
   (criteria 0) from a connection with no election in progress: mark that
   connection **HOST-ELECT (A)**. Any *other* connection's criteria-0 `0x135`
   while an election is pending → mark **JOINER-PEND (B)** and **send nothing
   at all**. B parks in `GAME_LIST_WAIT`; because it is blocked there it sends
   no further `0x135`s, so holding costs zero retries.
2. **Let A self-host.** Answer all five of A's `0x135`s with an empty `0x136`
   (~9–11 s). A goes `1214 LEAVE_GAME → 2032 START_MATCHMAKING → GATHER →
   725 CREATE_GAME_WAIT → 0x12f → 874 SERVER_LOBBY`.
3. **Release B the instant A's `0x12f` lands.** One-entry `0x136`:
   `entry[0:8]` = a **stub-synthesized unique room_id** (both clients literally
   send `0x0000000001383bd8`, a client-side heap pointer — never key the
   registry on it), `entry[0x14:0x24]` = **A's real NpId**, counts at
   `entry[0x0c]`/`entry[0x10]`.
4. **Budget.** A's lobby deadline is `t(0x12f) + 12.0 s`. B's path `PICK →
   CONNECT_TO_HOST → MUTUAL_ACTIVATED → RESERVE → 0x130` took **0.17 s** in the
   known-working reference trace (TTY 189.33 → 189.53). Worst case (30 s
   connect + 6 s reserve) blows the window, so: if B's `0x130` has not arrived
   within **~9 s** of A's `0x12f`, abandon the election and restart (A tears
   down at 12 s anyway).
5. **On B's `0x130`, push both sides the 2-member roster immediately.** That is
   what makes A dial B (`mgr->Connect`), which — because B already established
   the link — resolves to state 2 quickly, raising A's count to 2 and extending
   A's deadline from 12 s to **16 s**, at which point `FUN_003b7a78` evaluates
   `count >= min`.
6. **Hold cap.** Never hold a `0x136` longer than **40 s** (60 s hard limit).
   On expiry, release with an empty list so B self-hosts and becomes the host
   for the next round.

### Prerequisite fixes (not optional)

- **Delete the `[pair]` synthetic roster push.** It desynchronises the roster
  from the matchmaking SM (comradesean logged `mgnomad2 joined match` +
  `MUTUAL_ACTIVATED` while its SM was still in `CLIENT_START` criteria 2) and
  produces a link with no game-layer traffic that dies in ~16 s.
- **Clear the "is a public host" flag on `0x133`, immediately.** Keep the room
  *discoverable* for a grace period if desired, but never let the grace
  suppress a `0x136` to a connection that is searching. This single bug caused
  the 60 s hang.
- **Unique room_id per host** (both clients collide on `0x01383bd8`).
- **Fix the Member-refresher thread leak** (6 concurrent threads re-pushing
  every 10 s at the end of the run) and only re-push when the roster actually
  changes — an omit-then-re-add cycles `vtable[0x1c]`/`vtable[0x10]` and churns
  the P2P link.
- **Never send a `0x136` to a live host.** The search object *is* the room
  object (`0x01383bd8`); a `0x136` writes `+0xa4/+0x200/+0x208` on it. (A true
  host is in `SERVER_LOBBY` and won't send `0x135` anyway — so gate on
  "between its `0x12f` and its `0x133`", not on a grace timer.)

---

## 5. Timeline of the last failed 2-client attempt

Wall clock pinned to `T0 = 2026-08-17 00:21:16.79` by seven independent
heartbeat correlations between TTY.log and `captures/tcp_catch.log`. Only one
RPCS3 log exists — comradesean's (32× `mgnomad2 is offline`, 0×
`comradesean is offline`); mgnomad2's behaviour inferred from the stub wire log.

| Wall | Event |
|---|---|
| 00:21:24.20 | comradesean presses Find Match (`flow.cpp:2286 START_MATCHMAKING`) |
| 00:21:49 → 00:21:58 | **5 × `0x135`** (criteria 0–4), 5 × empty `0x136`; gaps 1.90 / 2.70 / 2.37 / 2.33 s |
| 00:22:00.83 | `1214 LEAVE_GAME` → `2032 START_MATCHMAKING` → `GATHER` → `725 CREATE_GAME_WAIT` |
| 00:22:00.87 | **`0x12f` RoomCreate #1**, room `0000000001383bd8`, max 8 |
| 00:22:01.14 | stub `0x131`+`0x13f` → `874 GOTO NET_SM_SERVER_LOBBY` |
| 00:22:12.91 | **`1039 GOTO NET_SM_LEAVE_GAME` + `0x133`** — exactly **12.04 s** after `0x12f` (= 8.0 + table[1]=4) |
| 00:22:13.86 | **mgnomad2 connects** — ~13 s after comradesean's search started; permanently out of phase |
| 00:22:13 → 00:22:21 | comradesean burst #2, 5 empty lists |
| 00:22:22.91 | **`0x12f` RoomCreate #2** → `874 SERVER_LOBBY` at 00:22:23.17 |
| 00:22:34.94 | `1039 LEAVE_GAME` + `0x133` — again **12.03 s**. Stub logs *"keeping 10s grace"* and **leaves the host flag set** |
| 00:22:37.30 | mgnomad2's first `0x135` → stub lists comradesean's room (inside the grace) — **but comradesean is no longer a host, it is searching** |
| 00:22:37.30 | **`[pair]` synthetic 2-member roster pushed to both** ← divergence #1 |
| 00:22:37.34 | comradesean applies it: `mgnomad2 joined match` / `Activate Connection mgnomad2` / `MUTUAL_ACTIVATED` — yet its SM keeps searching (`1210 CLIENT_START`, criteria 2, t=82.92) |
| **00:22:39.74** | **comradesean's criteria-2 `0x135` → stub sends NOTHING** ("already a public HOST", grace not expired: 82.95 < 78.15+10) ← **divergence #2, the fatal one** |
| 00:22:39.7 → 00:23:39.77 | comradesean stalled **60.03 s** in `CLIENT_GAME_LIST_WAIT` |
| 00:22:55 onward | mgnomad2 runs 7 independent create→12 s→abandon cycles; comradesean sees `mgnomad2 joined match` every ~23 s followed ~12 s later by `PEER_DEACTIVATED 0x8002a810` → `Kicking 'mgnomad2' out` |
| 00:23:39.77 | 60 s timeout → `1112 GOTO NET_SM_CHOOSE_HOST_JOIN` → `596 GOTO NET_SM_LEAVE_GAME` ×2 — last `GOTO` in the file |

**Divergence from the known-working path.** The reference success (TTY
59936–59946, earlier capture) reads `1107 GAME_LIST_PICK → "*********** Joining
Room mgnomad2 1 players" → 1194 CONNECT_TO_HOST → MUTUAL_ACTIVATED → Ping =
0 ms → 1327 CLIENT_RESERVE_SLOTS_WAIT`, with a `0x130` on the wire. In the
final run neither `Joining Room` nor `CONNECT_TO_HOST` ever appears and the
stub receives zero `0x130`s. The flow diverged at 00:22:37.30 (fake roster
substituted for the real pick→connect→reserve handshake) and was killed at
00:22:39.74 by the withheld `0x136`.

**Structural cause underneath both:** the two clients' matchmaking cycles are
~22–23 s each and were ~13 s out of phase. With a 12 s host window inside a
23 s cycle, unassisted rendezvous is roughly a coin flip per cycle — and the
stub's 10 s grace window exceeded the ~4.7 s re-search burst, guaranteeing the
suppression collision.

---

## 5b. LIVE OUTCOME (2026-08-17, same session) — election works; min gate is the last wall

The serialized election was implemented (commits `ca47fc6`, `17270b1`) and
live-tested with both clients. Confirmed host-side (a cycle where the local
client hosted): create → SERVER_LOBBY, `MUTUAL_ACTIVATED` +0.5 s, "joined
match" for the joiner +0.7 s, teardown at `net-matchmaking.cpp:1039` after
**16.03 s** = `8.0 + lobbyWaitTable[2]` — i.e. `FUN_003b19c4` counted **2**
members the whole window (the next, joinerless cycle held 12.03 s = table[1]).
So §1's "a server message alone cannot hold the host" is superseded in
practice: the roster push, backed by the joiner's real established P2P link,
does raise the count and extend the hold. The remaining teardown is purely the
**min-players gate** `0x003b7ac0` (`r29`=count=2 < `r3`=min, believed 6) —
client-side runtime DC data, unreachable by any server message. Lever:
client patch (see `2026-08-17-min-players-client-patch.md`).

Also found and fixed in `17270b1`: the joiner's FIRST P2P reserve against a
remote host timed out at exactly 6.00 s (3/3 cycles) because the host only
dials back once a roster naming the joiner arrives — previously sent only
after the 0x130, which itself needs the reserve. The stub now pushes the host
the 2-member roster at RELEASE time (`[punch]`), byte-identical to the post-
0x130 push (de-duped client-side by NpId at `0x00ad3458`), cutting join
latency from ~8.4 s to ~1.3 s. Self-recognition was verified NOT NpId-based:
`FUN_00ad0e40` matches `member+0xE8 == room_obj+0x19EC` (written at
`0x00ad37c8` when `member_id == header.local_ref_id`). Stub log lines now
carry `[HH:MM:SS.mmm]` timestamps.

## 6. Confidence and confirming tests

| Claim | Confidence | Live test |
|---|---|---|
| SERVER_LOBBY deadline = `t(create) + 8.0 + table[count]`, table at `0x00e7d340` | **High** (disassembled; predicts 12.0 s vs measured 12.04/12.03) | BP `0x003b7d08`; read `f30` and `0x01385850` |
| Member counted iff `mgr->vtable[0x18](member[0xF0]) == 2` or is self | **High** (disassembled `FUN_003b19c4`; `0xad147c` is `li r3,0`) | BP **`0x003b1a70`**: `r3` = per-member connection state; `r29` = member rec, `r25` = self |
| That manager is the P2P layer (same vtable+0x10 used by CONNECT_TO_HOST *and* by the `0x131` roster-apply) | **High** | BP `0x00ad34e0` while a Member push lands: `r3` = handle written to `member+0xF0` |
| A roster push alone *can* raise the count, but the link dies without real join traffic | **Medium-high** (TTY: `MUTUAL_ACTIVATED` from the push, `PEER_DEACTIVATED` 16 s later) | Push a roster to a host actually in SERVER_LOBBY (state `0x0137968c == 17`) and watch `r3` at `0x003b1a70` |
| `GAME_LIST_WAIT` hold budget = 60.0 s → error + LEAVE | **High** (float + measured 60.03 s hang) | already observed |
| Re-search backoff `1 + 2·rand`, 5 attempts, counter at `0x013858b4` | **High** (disassembled; matches 1.47–2.70 s and 5 criteria) | read `0x013858b4` during a burst |
| Serialized election + held `0x136` → deterministic host/joiner | **Medium-high** (all timings verified; end-to-end unproven) | two clients; stub holds B's `0x136` until A's `0x12f`; expect `Joining Room` + `1194` + `1327` + a `0x130` within ~0.5 s |
| `count >= min` then passes at 16 s | **Unknown — runtime DC data** | BP **`0x003b7ac0`**: `r29` = count, `r3` = min. Also `0x0039f200` for the 0x5C config record, `0x003b7ac8` for the `obj2[0x64]` floor |

**Useful live-inspection globals discovered this pass:** net-SM state code
`0x0137968c` (values per the table in §1), state-entry frame `0x01379690`,
lobby-timer base `0x01385850`, search-attempt counter `0x013858b4`, abort flag
`0x013858b0`, connection handle `0x01383bd8+0x1A48`, reserve deadline
`0x0138594c`, lobby-state obj `0x01385cdc`.

## §7 Real-server model validation 2026-08-17

**Verdict: the real-server model is CORRECT and COMPLETE. The election was NOT
load-bearing.** Every claim below re-verified in disassembly this pass (objdump
of the decrypted EBOOT, VMA = file+0x10000). Proceeding to gut the inert
election machinery; no correctness tweaks required.

### Q1 — GAME_LIST_WAIT / PICK robustness to multi/empty/stale lists

- **`FUN_003b4bf4` (GAME_LIST_WAIT) handles any entry count, empty included.**
  `0x3b4c14 bl 0xad0f60` (status); `0x3b4c38 cmpwi r3,1 / beq 0x3b4d10`: if
  still-searching, poll the 60 s timeout; else (search done, ANY count) it
  reads the count via `0x3b4c58 bl 0xad2594` and runs a zero-loop
  `0x3b4c7c..0x3b4c90` bounded by `*count` (stride 4) — count 0 skips the loop
  cleanly — then `0x3b4d00 li r3,7 / bl 0x347160` → PICK. Empty and multi both
  fall through the same door.
- **`FUN_003b6c78` (PICK): non-empty → connect, empty → 1+2·rand re-search.**
  On first entry (its own `+0` flag == 0) it calls the selector
  `0x3b6cdc bl 0x3b6a08`: nonzero → `0x3b6d08 b 0x3b2a9c` (CONNECT_TO_HOST);
  zero → `0x3b6d0c` arms a backoff `const 1.0 (‑32436) + 2·rand` into two float
  globals and sets the flag. Subsequent passes (`0x3b6d88`) wait out the
  backoff then `0x3b6dd8 b 0x3b5e9c` (re-search, bumps the attempt counter).
- **`FUN_003b6a08` (selector) iterates the WHOLE list and self-blacklists stale
  picks.** Loop `0x3b6a68..0x3b6bd4` runs `r28` over all `*count` entries
  (stride 56), picking the best by a float metric at dest+0x2c. Return
  (`0x3b6c40..0x3b6c74`) = `(selected_ptr != 0)`. Critically, `0x3b6a78..
  0x3b6ac8` walks an **8-slot recently-failed table** (room_id at entry+8 vs 8
  stored ids) and, on a match within **≤ 8999 ms**, `ble 0x3b6bb8` SKIPS that
  entry. So a room the client just failed to reserve against is ignored for ~9 s.
- **Stale/full/gone pick → reserve times out → back to PICK, room blacklisted.**
  `FUN_003b6404` (RESERVE_SLOTS_WAIT): `0x3b6480 li r3,257 / bl 0x3c8f20` polls
  the host's reserve reply; on a reply it decodes (56 B, `bl 0x3c9228`), gates
  `entry.room_id == session+0x98`, then `0x3b64dc bl 0x3b2f40` (→ 0x130 join).
  No reply and deadline passed (`0x3b6510 fcmpu / blt 0x3b6530`) →
  `bl 0x3b26c0` ("Joining Request timed out") → back to GAME_LIST_PICK, where
  the selector now skips the just-failed room for ~9 s and picks another or
  re-searches.
  **⇒ plain list-return is robust to staleness; the client prunes dead/full
  picks itself. The stub does NOT need to prune.** (Its existing filter —
  public, `members < max_players`, exclude self — is a sufficient, sane prune
  that just avoids wasting the client a 6 s reserve cycle.)

### Q2 — the returned entry format is sufficient (and empirically proven)

The stub fills entry[0:8]=room_id (join key + the selector's blacklist key),
entry[0xc]=cur, entry[0x10]=max, entry[0x14:0x24]=host NpId. CONNECT_TO_HOST
(`FUN_003b2a9c`) copies the attribute block [0x14:0x38] as the host address and
starts P2P signaling **by NpId** — so entry[0x14:0x24]=host NpId is the one
load-bearing field beyond room_id, and it is present. A real 2-client Find Match
completed live with exactly this format, so the fields are correct/complete;
nothing is being sent wrong or zero that a pick requires.

### Q3 — registry timing matches what the client needs

Host is advertised the instant its `0x12f` lands (added to `active_rooms` with
`public=True` in the RoomCreate handler) and stays listed across its whole
SERVER_LOBBY window until its `0x133`, on which it is removed **immediately**
(no grace — the grace was the fatal bug of the last run). Host-migration is not
replicated and is not needed for 2-player convergence. This is exactly the
add-on-create / drop-on-leave a real server does.

### Q4 — no livelock; convergence is w.p. 1

Each client's cycle is search-burst (5×`0x135`, each `1+2·rand` s ⇒ ~5–11 s) →
self-host → SERVER_LOBBY (12 s at count 1) → `0x133` → repeat, ≈ 22–23 s total
with a host "listable" for >50 % of it. A livelock would require the two cycles
to hold **perfect anti-phase forever** (every searcher window disjoint from
every host window). The `1+2·rand` backoff (re-rolled every burst) plus variable
self-host latency make the phase relationship a random walk, so P(sustained
anti-phase) → 0. When both search simultaneously they both self-host (re-roll);
when both host simultaneously they both tear down at 12 s (re-roll); otherwise a
searcher's `0x135` overlaps the other's SERVER_LOBBY and it sees + joins the host.
Per-cycle overlap probability is high (order 40–70 %), so convergence typically
within a few cycles (~a minute) and is certain in the limit. The election bought
one-cycle determinism; the natural model trades that for real-server fidelity and
still converges. **The determinism the election guaranteed is genuinely not
needed** — confirmed by the live 2-client success on the natural-flow build.
