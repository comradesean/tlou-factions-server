# Team/faction assignment consistency — full data-path trace (the symmetric X/Y remote-model mismatch)

Root-cause pass on the live symptom: **each player renders itself as character X
and the other player as character Y, symmetric and consistent (X≠Y), on two
near-empty profiles.** The companion note
(`2026-08-17-character-customization-sync.md`) established MP appearance = the
player's **faction/team model** (Hunters vs Fireflies, `FactionIdNetTeam0/1`), so
this is a **team-assignment consistency** failure: each client disagrees about the
*other* player's team.

Every EBOOT address below was disassembled directly with
`powerpc64-linux-gnu-objdump` (`file_off = VMA − 0x10000`) and read
instruction-by-instruction; vtable slots were resolved through the `.opd`
double-deref (`slot → opd_descriptor → code_addr`). Nothing here rests on a
guessed address.

---

## Bottom line up front

1. **Team is host-authoritative and keyed by SceNpId, end-to-end.** The room
   owner (host) runs the team balancer over its own engine player table and
   broadcasts the result via the **P2P** `assign_team` (opcode 18) NetEvent. Each
   packed slot carries the target player's **36-byte SceNpId/attributes blob**,
   and the receiver resolves that blob back to a local engine player. **Roster
   array *position* is never used to key team.**
2. **Therefore our per-recipient own-first roster ordering does NOT cause the
   mismatch — hypothesis (b) is falsified at the instruction level.** The
   symmetric X/Y symptom is **hypothesis (a)**: the host's authoritative
   assignment is not being *applied* on the joiner, so the other player's team
   stays at the engine default **`-1`** ("unassigned"), which the faction/model
   code renders as the default/"other" faction.
3. **This transport is pure P2P (`sceNpSignaling`), which our SessionManager
   server neither sees nor relays.** There is **no** SessionManager opcode that
   carries per-player team, nothing to echo, and nothing to add. The `RoomCreate`
   `0xb0` field (hypothesis c) is only the host's *own* menu pick fed to the
   host-side balancer — correctly found inert when echoed. `0x144`/HostRank is
   rank data, not team. The server's only levers are **indirect**: make both
   players resolvable-by-NpId engine players on both clients (roster NpIds +
   is_local/is_owner → P2P signaling), and don't advance the host into the team
   broadcast before the joiner's P2P player exists. Both overlap the parallel
   Join-Party/signaling investigation.

---

## 1. How team/faction is represented and assigned

### 1a. The per-player team field: `player_obj + 0x1dc` (u32), default `-1`

The single per-player team value the whole match pipeline reads/writes is
`player_obj + 0x1dc` (offset 476). It has one setter and one default:

* **Setter — `FUN_003cf6d8`** (`0x003cf6d8`), signature
  `(player, team, _, aux_u32)`:
  ```
  3cf70c  stw r4,476(r3)    ; player+0x1dc = team      (arg2)
  3cf704  stw r5,480(r3)    ; player+0x1e0 = 0         (arg3, always 0 at call sites)
  3cf708  stb r0,515(r3)    ; player+0x203 = 1         ("team is set" flag)
  3cf760  stw r6,680(r3)    ; player+0x2a8 = aux_u32   (arg4; may be overridden by a global)
  3cf6e0  cmpwi r4,0 / bge  ; team must be >= 0, else trapWord path
  ```
  The `team >= 0` guard here is the same invariant as the historical assert
  `team >= 0 && team < kMaxNetTeams` (`net-game-manager.cpp:1358`).
* **Default/reset — literal `-1`.** Three sites reset a player right after the
  per-player setup helper `FUN_0039f75c`:
  ```
  3596f8  li r0,-1 ; 3596fc  stw r0,476(r3)     ; player+0x1dc = -1
  35a858  li r0,-1 ; 35a860  stw r0,476(r3)
                     35a99c  stw r0,476(r29)     ; (player clear/init)
  ```
  So an engine player that never receives a team is left at **`-1` = unassigned**
  — the exact value that fails `team >= 0`, and the value the faction/model
  selection sees for any un-resolved remote player.

`player+0x1dc` has 30+ read sites across rendering/scoring/HUD — it *is* the team
the game keys everything (including faction-model selection, `FactionIdNetTeam0/1`
→ Hunters/Fireflies) off of. (A separate aggregate, the NetGameManager team array
`GM+0x4b1c/+0x4b20`, `kMaxNetTeams==2`, accessor `FUN_0039a5a0`, holds per-*team*
data, not per-*player* team — distinct object family, not wire-seeded.)

### 1b. The assignment is host-authoritative, gated by "am I the room owner?"

The team decision + broadcast is gated by **`FUN_00ad0eec`**, which is a pure
owner check:
```
ad0eec:  r0 = *(room_obj+0x10)                     ; if 0 -> return 1
         r9 = *(room_obj+0x19ec) ^ *(room_obj+0x19f0)
         return (r9 == 0) ? 1 : 0                   ; my_member_id == owner_member_id
```
i.e. **`AmIHost = (room_obj+0x19ec == room_obj+0x19f0)`**. Both fields are seeded
by **our** Member (`0x131`) message: `room_obj+0x19ec` = my member id (the
is_local entry), `room_obj+0x19f0` = the owner's member id (the is_owner entry)
— see `protos/0x131_member.ksy`.

The host path lives in `FUN_00358b08` (reached via `0x35c290`, in fn `0x35bfbc`,
triggered from a match-flow tick at `0x3884c0`/`0x35c814`):
```
358b4c  bl 0xad0eec                 ; AmIHost?
358b64  beq -> 0x358b8c             ; NOT owner: FUN_0039cd4c (joiner path, NO balance/broadcast)
358b70  bl 0x3a482c                 ; owner: BALANCE teams (writes engine players' +0x1dc)
358b78  bl 0x395cfc                 ; owner: broadcast assign_team    (opcode 18)
358b80  bl 0x395a18                 ; owner: broadcast assign_team_desc (opcode 19)
```
`FUN_003a482c` is the balancer: it iterates the host's own engine player slots
(`GM + i*0x920 + 0x40`) and calls `FUN_003cf6d8(player, team, …)` to stamp each
one's `+0x1dc`. **The joiner never runs this** — it must *receive* the result.

**Verified our stub seeds `AmIHost` correctly** (read-only inspection of
`tools/session_manager_stub.py`):
* Host's Member: `build_member([host(id=1), joiner(id=2)], owner_ref=1,
  local_ref=1)` → `+0x19ec==+0x19f0==1` → **AmIHost = TRUE** ✓
* Joiner's Member: `build_member([joiner(id=2), host(id=1)], owner_ref=1,
  local_ref=2)` → `+0x19ec=2, +0x19f0=1` → **AmIHost = FALSE** ✓

So the two clients **agree on who is authoritative**; the bug is *not* "both think
they're host," and it is *not* corrupted by own-first ordering here (each
recipient's own entry is still correctly flagged local, the owner ref still points
at the host's id).

---

## 2. `assign_team` (opcode 18) is NpId-keyed — build, wire, and apply

vtable `0x01223c08`: Deserialize `0x00389d5c`, Serialize `0x00389ba4`, Execute
`0x0038e6bc`; constructor `FUN_00388c94` (object size `0x190`), trampoline
`0x0038f308`. It is a genuine `NetEvent` (vtable+0x14/+0x18 = the inherited
`FUN_00acb460`/`FUN_00acb30c` send/queue hooks) → **direct P2P UDP**, brokered by
`sceNpSignaling`, never through our server.

### 2a. Builder `FUN_0038b924` (host side) — packs *resolved team keyed by NpId*

Iterates the sender's **own** engine player table via `FUN_003994ac(GM, i)`,
`i = 0..7`; for each *active* slot (gates: `player+0xa8 != 0`, a vtable predicate,
`player+0x3f4 == 0`, `player+0x203 != 0`) it packs at **`n = event->count`**
(a running packed index, incremented per emitted entry — **not** the slot index):

| event offset | source | meaning |
|---|---|---|
| `+0x15 + n`     | `player+0x1dc` | **the team** (already resolved on the host) |
| `+0x20 + n*4`   | `player+0x2a8` | aux u32 |
| `+0x40 + n*36`  | `player+0x3c8` (36 bytes) | **the player's SceNpId/attributes blob** |
| `+0x160 + n`    | `bool(player+0x1ac != 0)` | per-slot flag |
| `+0x168 + n*4`  | `player+0x1a8` | per-slot u32 |

So `assign_team` is a **host snapshot of already-resolved per-player teams, each
labeled by that player's SceNpId.** Order carries no meaning.

### 2b. Deserialize `FUN_00389d5c` mirrors it

`count = ReadBits(4)`; a bool at `+0x14`; then per slot: `ReadU8 → +0x15+i`,
`Read32 → +0x20+i*4`, `ReadBytes(288 bits = 36 bytes) → +0x40+i*36`,
`ReadBool → +0x160+i`, `Read32 → +0x168+i*4`; trailing `Read32 → +0x188`.

### 2c. Execute `FUN_0038e6bc` (receiver) — **resolves by NpId, skips on miss**

For each of `count` slots:
```
38e76c  FUN_0039b3fc(GM, &blob[i])        -> r29   ; GM-side NpId resolve
38e7a4  FUN_00ad1e64(PT, &blob[i])        -> r31   ; player-tracker NpId resolve
38e7cc  cmpwi r31,0 ; beq 0x38e8e0                 ; if PT lookup == 0 -> SKIP this slot
        ...
38e814  FUN_0039f75c(GM, PT, player, team_byte, 0) -> per-player struct
38e908  FUN_003cf6d8(player, *(+0x15+i), 0, *(+0x20+i*4))  ; player+0x1dc = team
```
The 36-byte blob (`event+0x40+i*36`) is the player's SceNpId; both resolves key on
it. **If either lookup returns 0 — i.e. the receiver has no engine player for that
NpId yet — the slot is skipped and no team is written**, leaving that player's
`+0x1dc` at the default `-1`.

**Conclusion for hypothesis (b): FALSIFIED.** The receiver never indexes team by
roster array position; it matches the 36-byte SceNpId. Sending each recipient its
own entry at roster index 0 cannot make two clients disagree about a player's
team via `assign_team`.

---

## 3. The exact divergence mechanism (why self=X, remote=Y, symmetric)

Team reaches the joiner **only** over P2P (`assign_team`/18, `assign_team_desc`/19,
and the bulk `sync_players`/71). Our SessionManager relays none of them. For the
joiner to render the host correctly, the received `assign_team` must resolve the
host's SceNpId to a **local engine player** — and that engine player only exists
once the joiner has opened a `sceNpSignaling` P2P connection to the host (the
Member handler's non-local branch, `slot+0xf0 = signaling_connect(npid)` at
`0x00ad34a4`, member ksy).

Two ways this produces the observed symptom, both leaving the *other* player at
`+0x1dc == -1`:

* **(i) The host omits the joiner from the broadcast.** The balancer/builder only
  packs engine players that are *active on the host* at broadcast time. If the
  host runs `FUN_00358b08` (balance + broadcast) before the joiner's P2P engine
  player is up, the joiner is never stamped with a team on the host **and** is
  never included in the `assign_team` the joiner receives.
* **(ii) The joiner can't resolve the host's NpId at apply time.** If the joiner
  receives `assign_team` before its engine player for the host exists (or that
  player's SceNpId doesn't byte-match what the host packed from its own
  `player+0x3c8`), Execute skips the host's slot.

Either way: each client resolves *itself* (the local player is always in the
engine table → team set → renders as **X**) but leaves the *other* player at the
`-1` default, which the faction/model code renders as the default/"other" faction
**Y**. This is symmetric by construction (both clients hit the same local-resolves
/ remote-defaults split) and consistent (a real default, not garbage) — matching
the reported shape exactly. It is the same `-1` that historically tripped the
`team >= 0` assert before the local-member-identity fix.

**Ruled out this pass, with evidence:**
* **(b) roster-index keying** — falsified; team is SceNpId-keyed on build *and*
  apply (§2).
* **(c) `RoomCreate 0xb0` not reaching the joiner** — `0xb0` is the host's own
  menu team pick, consumed only by the host-side balancer as a preference; it has
  no per-joiner propagation role, which is why echoing it into Member entry offset
  16 was correctly inert (`2026-08-16-team-selection-field-confirmed.md`).

---

## 4. Server fix

**There is nothing to add or echo on the SessionManager channel, and this is
provable, not a give-up:**

* No SessionManager opcode carries per-player team. The per-player team lives at
  `player+0x1dc` on the **engine** player object and is written *only* by
  `FUN_003cf6d8`, whose callers are the host balancer (`FUN_003a482c`) and the P2P
  `assign_team` Execute — never a wire-field copy. The NetGameManager team array
  `GM+0x4b1c` is a *different object family* (fields past `0x4b58`) than the
  SessionManager room slot (`room_obj`, fields top out ~`0x1f8`); no wire message
  writes it.
* `0x144`/HostRank memcpys 128 bytes into `room_obj+0x18` — rank data on the room
  slot, not the engine team. Sending it will not seed teams (consistent with prior
  falsifications).
* `assign_team`/`assign_team_desc`/`sync_players` are pure P2P — we can neither
  observe nor relay their contents.

**What WOULD make the two clients agree** (and the only server-reachable levers,
both already in the roster's remit — they overlap the Join-Party/signaling
work; do not duplicate it):

1. **Guarantee both peers are resolvable-by-NpId engine players on both clients
   *before* the host broadcasts.** Concretely, the roster the stub already sends is
   the right shape (own-first, `populate_self_npid=True`, the peer flagged
   non-local so `signaling_connect` fires). The remaining risk is *timing*: the
   host's balance+broadcast (`FUN_00358b08`) fires on a match-flow tick; if our
   server advances the host into the match before the joiner's `0x130` RoomJoin
   has produced a live P2P engine player on the host, the joiner is omitted from
   the very first `assign_team` (§3-i). Lever: don't push the host past the
   team-setup phase until the joiner's join is acknowledged. This is a sequencing
   change in the match-start handshake, not a new team field.
2. **Verify NpId fidelity** so the host's packed `player+0x3c8` SceNpId matches the
   roster NpId the joiner used to open signaling: our `host_entry` npid must be the
   host's exact `SceNpId` bytes (as sent at RoomCreate), and `joiner_entry` npid the
   joiner's own — both already true in the stub. If a future capture shows the
   joiner opening signaling to an NpId that differs from what the host packs,
   *that* mismatch (not team code) is the fault.

**Stub sketch — the honest one.** No `build_*` change adds team; the actionable
item is a diagnostic/sequencing guard, not a payload:

```python
# tools/session_manager_stub.py — DO NOT EDIT LIVE; sketch for the next window.
#
# (A) There is NO team message to add/echo. assign_team(18)/assign_team_desc(19)
#     are P2P; the joiner's engine player for the host is created from the Member
#     roster's non-local branch (signaling_connect), which the stub already emits.
#
# (B) The one team-adjacent server lever is ORDERING: ensure the host does not
#     reach its team-broadcast tick before the joiner's RoomJoin(0x130) has been
#     paired and both directions' rosters pushed. The 0x130 handler already pushes
#     host_member (host sees [host, joiner]) — the requirement is only that this
#     Member reaches the host and creates the joiner's non-local slot BEFORE the
#     host balances. If live capture shows the host emitting assign_team before the
#     joiner's Member round-trips, delay/gate the host's NET_SM match-start advance
#     (e.g. withhold the state-advance reply on the host connection until the
#     paired 0x130 for the same room_id has been serviced).
#
# (C) Diagnostic to confirm §3 on the next test: in RPCS3.log, grep the joiner for
#     a signaling connect to the HOST's exact npid around match start, and confirm
#     player+0x1dc != -1 for the remote (via sys_tty_write / a watchpoint on
#     GM+i*0x920+0x40+0x1dc). team==-1 on the remote == "assign_team never applied".
```

If, after both peers are confirmed resolvable and the ordering is right, the
remote team *still* stays `-1`, the residue is inside the P2P `assign_team`
exchange itself (delivery/`sceNpSignaling`), which our auth/matchmaking/signaling
backbone cannot patch — only the two indirect levers above reach it.

---

## 5. Confidence

**High:**
- `player+0x1dc` is THE per-player team; sole setter `FUN_003cf6d8`; default `-1`.
- Team is host-authoritative, gated by `FUN_00ad0eec = (my_member_id ==
  owner_member_id)`; balancer `FUN_003a482c`; broadcast `FUN_00395cfc`/`0x395a18`
  from `FUN_00358b08`; non-owner path does neither.
- `assign_team` (18) build (`FUN_0038b924`) and apply (`FUN_0038e6bc`) are both
  **SceNpId-keyed** (36-byte blob `player+0x3c8` ↔ `event+0x40+n*36`), packed by
  running count, resolved via `FUN_0039b3fc`/`FUN_00ad1e64`, **skipped on
  unresolved NpId** → default `-1`. Roster index is never used. Hypothesis (b)
  falsified; (c) inert.
- Our stub seeds `AmIHost` correctly on both clients (host TRUE / joiner FALSE).

**Medium:**
- Which of §3-(i) (host omits joiner from broadcast) vs §3-(ii) (joiner can't
  resolve host at apply) dominates — both give the identical `-1`/default symptom;
  discriminated only by the live watchpoint/log in §4-(C).
- That the faction *3D model* selection reads `player+0x1dc` specifically (vs a
  derived cache) — inferred from the field's 30+ consumers and the whole team
  pipeline converging on it; not traced into the render call itself this pass.

**Not established:**
- The exact match-flow state that fires `FUN_00358b08` on the host (fn `0x35bfbc`,
  caller `0x3884c0`) and whether our NET_SM sequencing can starve it — the
  sequencing lever in §4-(B) is a hypothesis to test, not a confirmed fix.
- `sync_players` (71) field layout — a second P2P team carrier, not decoded here.
