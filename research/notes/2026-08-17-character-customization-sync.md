# Character "customization"/appearance not syncing between players — full data-path trace

Root-cause pass on the live symptom: **each player sees their own character
correctly, but sees the *other* player as a different character; the mismatch
is symmetric and consistent (both render self as X, both render the other as
Y, X≠Y), on two near-empty profiles.**

Bottom line up front, so the actionable part isn't buried:

1. **There is no separate "character appearance / outfit / head" customization
   system in the EBOOT for MP.** The only outfit/hat strings in the binary are
   Joel/Ellie **single-player** cosmetics. MP visible appearance = **faction
   (team) model** + **DC/`.pak`-driven head/emblem cosmetics that are
   clan-size-gated** (so **empty on empty profiles** — "customizations aren't
   showing" is largely this, not a sync failure). The thing players *select* in
   MP that the EBOOT actually stores is the **loadout** (weapons/skills), which
   is a different axis and already understood.
2. **The self-vs-remote split that produces X≠Y is the same defect the sibling
   member-blob note already found: our stub relays the 32-byte per-member blob
   as 64 bytes, so `FUN_00ad2650`'s `len==32` gate returns `NULL` for every
   *remote* member** while the *local* player takes a different branch
   (`room_obj+0x19FC`, length 32, correct). Self reads a good source → X;
   remote reads `NULL` → default/stale → a *consistent wrong* Y. This is the
   textbook shape of the reported symptom.
3. **New correction to the sibling note (`2026-08-17-member-data-blob-...`):**
   `FUN_00ad2650` is **not** "all UI/lobby" callers. One of its callers,
   **`0x38e7e4`, is inside `assign_team`'s Execute (`0x0038e6bc`) — an in-match
   *gameplay* NetEvent handler**, keyed by member id. So the blob we relay
   reaches the in-match per-player setup/roster path, not just the lobby card.
4. **Server-fixable? Partly, and the fixable part is the highest-value one.**
   The blob-relay length fix (64→32, already sketched in the sibling note) is a
   concrete, testable server change that plausibly corrects the *remote-player
   card/nameplate/loadout* display. The pure **3D faction model** and the
   **DC-cosmetic** aspects are P2P/`.pak`/profile-gated respectively; the lever
   there is **seeding populated profiles** (the profile round-trip) and
   **team-assignment consistency**, not a per-player relay we can add.

Every EBOOT address below was read off `powerpc64-linux-gnu-objdump`
(`file_off = VMA − 0x10000`) and/or resolved through the r2→anchor /
`.opd`-descriptor idioms in `tools/eboot_analysis/`. Vtable double-derefs use
the same method as `docs/protocol/net_event_dispatch_and_simple_opcodes.md`.

---

## 1. The appearance data representation — what actually exists

### 1a. There is no MP "appearance customization" field. Confidence: high.

A full EBOOT string sweep for customization/appearance/head/outfit terms
returns only:

| VMA | string | what it is |
|---|---|---|
| `0x00e4a018` | `Joel Outfit Index` | **single-player** |
| `0x00e4a048` | `Ellie Outfit Index` | **single-player** |
| `0x00e4a078` | `Ellie Hat Index` | **single-player** |
| `0x00e89988` | `ellie-bonus-hat-a` | SP DC asset |
| `0x00e4a9c0` | `torso` | generic body-part token |
| `0x00e69658` | `emblems/%s`, `emblems/spray-01`, `emblems/emblem-16-drips` | asset-path templates |
| `0x00e7c6c0` | `DrawEmblem` | render helper name |

None of the emblem/torso/outfit strings have **any** EBOOT code reference
(`scan_imm.py` and a raw big-endian pointer scan over both LOAD segments both
return zero refs). That is the signature of **DC (`.pak`) script-driven**
content — the same conclusion the metagame note reached: character
customization items live in the data-compiler modules, keyed by ids, and
**unlock by clan size**. On a near-empty profile the unlocked-cosmetic set is
essentially empty, so every player is on the **default** head/emblem. There is
nothing to *mismatch* on the cosmetic axis — both ends default.

By contrast the **loadout** system is fully present in the EBOOT
(`NET_SM_SELECT_LOADOUT_SCREEN` `0x00e6d6f8`,
`loadoutNum >= 0 && loadoutNum < kNumCustomLoadoutsPerMode` `0x00e6e078`,
`kLoadoutSize`) and stored in the profile at `P+0x08..0xE7`
(`2026-08-16-profile-and-userdata-reverse-engineering.md` §5). Loadout is
weapons/skills — **not** what a player *looks* like.

### 1b. MP visible appearance = faction/team model. Confidence: high (that the
axis exists), medium (that it is the reported "wrong model").

`game/faction.cpp` (`0x00e4c368`) defines the faction table, and it contains
two **MP-team** factions:

```
0x00e4c8a8  g_factionMgr.LookupFactionByNameId( StringId(0x33ea0868) ) == FactionIdNetTeam0()
0x00e4c900  g_factionMgr.LookupFactionByNameId( StringId(0x372b15df) ) == FactionIdNetTeam1()
```

plus `FactionIdHunter()` / `FactionIdFirefly()` and the DC verbs
`set-object-faction` (`0x00e50dc8`) / `get-object-faction`. In Factions the two
sides are `NetTeam0`/`NetTeam1` (skinned Hunters vs Fireflies), and the
character **model** a player renders for another player follows that player's
**team/faction**. So the concrete meaning of "B looks like a different
character" is most naturally **B is being drawn on the wrong faction/team** by
the observer.

Team is a real, server-touching field: `RoomCreate` (`0x12f`) wire
`0xb0:0xb2` carries the host's selected team (`0/1/2` = unset/Blue/Red,
`2026-08-16-team-selection-field-confirmed.md`), and the in-match team array
lives in the NetGameManager (`param_1+0x4b1c/0x4b20`, `kMaxNetTeams==2`,
`2026-08-16-net-sm-server-lobby-dispatch.md`). **Important live caveat:** in
the *current* working-match state there is **no** `kMaxNetTeams` / faction
assert in `RPCS3.log` (grep count 0) — teams *are* being assigned, matches load
and play. So the residual model mismatch, if it is faction, is a **consistency**
problem (each client picks a different team for the *other* player), not the
old hard assert/boot.

---

## 2. The transmission channels

### 2a. In-match per-player state is P2P. Confidence: high.

All gameplay `net_event_type` opcodes (0..114) are **direct P2P UDP**, relayed
through whichever peer is host, brokered by `sceNpSignaling` — never through a
server we operate (`research/notes/network-topology.md`,
`2026-08-15-directionality-and-sync-stats-p2p.md`; EBOOT strings
`[udpp2p] : recv from %s:%d`, `bind P2P to localhost:%d:%d`). The per-player
identity/appearance carriers in that family are:

**`player_info` (opcode 44 / `0x2c`), handled by `net-player-tracker.cpp`.**
Factory `[44] 0x0038f898` → ctor `FUN_004090dc`, object size **200**, derived
vtable `0x012254b8` (`sendhook`/`queuehook` = the inherited `FUN_00acb460`/
`FUN_00acb30c`, confirming a genuine `NetEvent`). Deserialize `0x0040bce8`
reads, in wire order:

| obj off | read | via | meaning (shape) |
|---|---|---|---|
| `+0x10` | `ReadBits(13)` | `FUN_00a1a8dc` | player index |
| — | 8× pair | `FUN_00a1b218` (bit read) | per-slot small values |
| `+0x24..0x30` | 4× `Read32` | `FUN_00a1af50` | ids/stats |
| `+0x34` | `Read8` | `FUN_00a1ab64` | byte selector |
| `+0x38` | **256-byte buffer** | `FUN_00a1b2a0` (ReadBytes) | name / clan string |
| `+0x58` | `ReadFloat` | `FUN_00a1add0` | — |
| `+0x60` | **64-byte buffer** | ReadBytes | string |
| `+0x68` | **64-byte buffer** | ReadBytes | string |
| `+0x70,+0x71` | 2× `Read8` | | byte selectors |
| tail | **2×8×3 u32 array** | Read32 | per-team/per-player table |

Execute `0x0040c6ac` resolves the target via `FUN_0039f3d8(player_index)` (the
standard player-index→object lookup) and writes the fields onto the **player
object** (`+448/+452/+456/+508f/+512/+513/+688/+0x540`), plus name via
`FUN_003cee8c`/`FUN_003d0ba0`/`FUN_003ce89c`; `FUN_003d0ba0` references
`game/net/net-player-tracker.cpp` and `m_numAppliedBuffs < kMaxAppliedBuffs`.
So `player_info` is the **per-player network-tracker sync** (name, buffs,
several byte/u32 selectors, a 2×8×3 roster table). This is the channel that
sets *remote* players' per-player attributes on each client.

**`sync_players` (opcode 71 / `0x47`)** — factory `[71] 0x00390088` → ctor
`FUN_0040a840`, size **0x330** (room for the full 8-player roster). The bulk
host→joiner "here is everyone" sync. Not decompiled field-by-field this pass.

Because these are P2P, the **local** player's own attributes on machine A are
set by A's *local* code (its menu/equip/team state), while **remote** player B's
attributes on A are set by the *received* `player_info`/`sync_players` from B.
**That is the self-vs-remote source split the coordinator described** — two
different code paths writing the same player-object fields.

### 2b. Our server relays only the 32-byte lobby member blob — and it reaches a
gameplay handler. Confidence: high.

Our `0x13a`→`0x13b` (SessionManager `MemberSetData`/`MemberUpdatedData`) relay
writes the 32-byte per-member blob into `member_slot+0xFC`, read back by
`FUN_00ad2650` (`len==32` gate, local branch `room_obj+0x19FC`). The sibling
note catalogued its callers as "all UI/lobby/social-list." **That is wrong for
at least one:**

```
assign_team (opcode 18) Execute = 0x0038e6bc      (vtable 0x01223c08 +0x10)
  0x0038e7d8  lbz r28,0(r25)      ; member id from event's +0x160 per-slot array
  0x0038e7e4  bl  0x00ad2650      ; <-- MEMBER-BLOB GETTER, keyed by that member id
  0x0038e7f8  bl  0x00ad15b0      ; roster name formatter ('[%s] %s' @0x00e7da48)
  0x0038e814  bl  0x0039f75c      ; per-player setup(team_globals, ..., member_id, 0)
  0x0038e828  stb r0,513(r9)      ; per-player byte
  0x0038e830  stb r0,1012(r9)     ; per-player byte
```

`assign_team` is a **gameplay** `net_event_type` handler (P2P-dispatched), and
it consults `FUN_00ad2650` for the member's blob during team/roster setup. In
the traced path the getter's *return* is dominated by the adjacent name
formatter (`FUN_00ad15b0` = the `[%s] %s` roster-name builder), so the blob's
role here reads as **in-match roster/nameplate display** rather than proven 3D
model — but the structural point stands: **the data we relay is consumed inside
match code, not only lobby menus.** (Other `FUN_00ad2650` callers at `0x39f9ec`,
`0x3a261c`, `0x3a4998` sit in the same net-game-manager address band and were
also mis-filed as UI; not individually re-traced this pass — flagged.)

---

## 3. The exact divergence mechanism (why remote Y ≠ self X)

`FUN_00ad2650` (re-verified in the sibling note) has two branches:

* **local player:** `len = *(u32*)(room_obj+0x19F8)`, `ptr = room_obj+0x19FC`
  — the client writes this itself; length is 32; **always valid → X correct.**
* **remote member:** `ptr = member_slot+0xFC`, `len = *(u32*)(member_slot+0xF8)`
  — filled only by our `0x13b` relay (and `0x131`/Member seed).
* Then `if (len != 32) return NULL;` (`cmpwi r0,32` @ `0x00ad2734`).

**`tools/session_manager_stub.py` relays `chunk[16:80]` = 64 bytes**, so every
remote member's `member_slot+0xF8` becomes 64, the gate fails, and
`FUN_00ad2650` returns **`NULL` for every remote player**. Consumers then:

* lobby/roster card + rank widget: bail on `NULL` → widget keeps stale/default
  value (the already-known "remote rank/loadout card wrong");
* `assign_team` Execute + the other net-game-manager callers: get `NULL` for the
  remote member → the per-player roster/setup falls back to a **default**.

This is *precisely* the reported symptom shape: **self (local branch, len 32) is
correct = X; every remote (relay branch, len 64 → NULL) is the same default =
Y; X≠Y, symmetric and consistent, not garbage** (it's a real default, not
uninitialised stack — matching the coordinator's "consistent wrong value, not
random" observation).

**Answering the coordinator's (a)/(b)/(c):** it is **(a)+(b) combined, not
pure (c)**. We *are* transmitting the blob (a), but at the **wrong length**
(64 vs 32), which the client's own getter treats as "absent" (b) — so the
remote-player data path is silently disabled while the local path is fine.
It is **not** the "appearance simply isn't transmitted and the client invents a
fallback" case in the sense of being beyond server reach — the fallback fires
*because our relay is malformed.*

### The two things this does NOT by itself explain

* The **3D outfit/head cosmetic** specifically: those are DC/`.pak`,
  clan-gated, and empty on empty profiles, so both ends default regardless of
  the blob. Fixing the blob length won't conjure cosmetics onto empty profiles.
* The **3D faction model**: if the residual "different character" is the
  Hunter/Firefly skin, that follows **team assignment**, which currently loads
  without asserting but whose per-remote-player *consistency* is unverified. The
  blob (`blob[10..13]` loadout ids from live global `0x01382082`, `blob[9]`
  title from `P+0x303`) is not proven to carry the team/faction the model uses.

Confidence: **high** that the 64→32 length bug produces a self-correct /
remote-consistently-wrong split for everything gated behind `FUN_00ad2650`;
**medium** that this is the *3D model* the user is describing vs. the in-match
nameplate/rank/loadout card; **medium** that a faction/team-consistency issue is
the residue if the 3D model still mismatches after the length fix.

---

## 4. Server-fixability and fix plan

### 4a. Highest-value, testable, server-side: fix the blob relay length. 

This is the sibling note's fix; this note adds the evidence that it reaches a
**gameplay** handler, so its blast radius is larger than "lobby rank." **Do not
edit `tools/session_manager_stub.py` (running live).** Sketch, for when testing
pauses — in the `0x13a` branch, replace the 64-byte slice with the client's own
declared length (live-constant 32):

```python
blob_len = chunk[4]                 # client's declared length byte, == 0x20
blob     = chunk[16:16 + blob_len]  # NOT chunk[16:80]
# forward `blob` (32 bytes) in the 0x13b relay so FUN_00ad2650's len==32 gate passes
```

`build_member_blob` already puts `len(payload)` in `body[6]` (the byte the
`0x13b` handler reads into `member_slot+0xF8` @ `0x00ad8130`), so passing a
32-byte payload is the entire change. Also seed `0x131`/Member entry `+39`
(length) / `+40..` (blob) so a member's blob is present before its first
`0x13b`, per the sibling note §4b. **Re-test after this:** if the remote
nameplate/rank/loadout corrects, that portion is solved; whatever visual
mismatch *remains* is the 3D-model residue below.

### 4b. For the 3D cosmetic/model residue: profiles + team consistency, not a relay.

* **Cosmetics are clan-gated and profiles are empty** → nothing unlocked → both
  ends default. The lever is the **profile round-trip** already scoped in
  `2026-08-16-profile-and-userdata-reverse-engineering.md` §4/§8: add
  `s3.amazonaws.com` to the RPCS3 IP-swap list and accept the client's `PUT`, so
  each client persists and re-loads a *populated* profile with a *matching*
  unlock set. Only then can any transmitted cosmetic id resolve to the same
  thing on both ends. This is server-adjacent (catcher + IP list), not a
  SessionManager message.
* **Faction/team model** rides P2P (`player_info`/`sync_players`/`assign_team`)
  and originates from host-authoritative team assignment. Our influence is the
  `RoomCreate 0xb0` team field and the member/room-attr data the host reads; the
  open item (multiple prior sessions) is *what feeds the NetGameManager team
  array* (`+0x4b1c`), with `0x144`/HostRank the standing never-sent lead
  (`2026-08-16-team-selection-field-confirmed.md`,
  `2026-08-16-net-sm-server-lobby-dispatch.md`). This is genuinely unresolved
  and is the same root as the historical team-assert boot.

### 4c. What is NOT server-fixable

`player_info`/`sync_players` themselves are pure P2P — we neither see nor relay
them, and cannot patch their contents. If, after the length fix and a populated
profile, appearance *still* diverges, the remaining cause is inside the P2P
client↔client exchange (or the client's own render from empty DC unlock tables),
which our auth/matchmaking/signaling backbone cannot reach. The only indirect
levers are the two in 4b (seed the profile so both clients share unlock state;
get team assignment consistent).

---

## 5. Confidence summary

**High:**
- No MP outfit/head customization in the EBOOT; only SP Joel/Ellie cosmetics;
  MP cosmetics are DC/`.pak`, clan-gated (empty on empty profiles).
- `player_info`(44)/`sync_players`(71) are the P2P per-player-state carriers;
  `player_info` field layout and its `net-player-tracker.cpp` ownership.
- The 64-vs-32 blob relay bug makes `FUN_00ad2650` return `NULL` for remote
  members only, giving self-correct / remote-consistently-wrong-default — the
  exact reported shape. Verdict (a)+(b), server-fixable.
- Correction: `FUN_00ad2650` is called from a gameplay handler
  (`assign_team` Execute `0x0038e6bc`, call site `0x0038e7e4`), not only UI.

**Medium:**
- Whether the user's "wrong character *model*" is the in-match nameplate/rank/
  loadout card (blob-gated, fixed by 4a) vs. the 3D faction skin (team-gated,
  4b). The blob's consumption in `assign_team` reads as roster/name display in
  the traced path; the 3D-model link is not proven.
- Faction/team-consistency as the 3D-model residue (teams currently assign
  without asserting; per-remote consistency untested).

**Not established this pass:**
- The send-side *builder* of `player_info` (construction is via an event pool,
  not the receive dispatcher `FUN_0038ec00`), so whether the sender packs its
  own appearance/team from the same live source it self-renders from is
  untraced — the instruction-level (i)-vs-(ii) distinction for the P2P channel.
- `FUN_0039f75c` (the per-player setup after the blob getter) field-by-field.
- Whether `blob[10..13]`/`blob[9]` are consumed by any 3D-model code (vs only
  cards). The item-id table itself lives in `.pak`, not the EBOOT.

## 6. Recommended next experiment

Apply 4a (32-byte relay + Member seed) on the next test window and observe the
remote player. Three outcomes discriminate the open questions cleanly:
- remote **card/rank/loadout** corrects but 3D avatar still wrong → residue is
  faction/team + empty-profile cosmetics (pursue 4b);
- remote avatar corrects too → blob was feeding more of the model than the trace
  showed (upgrade §3 to high);
- nothing changes → the visible axis is purely P2P `player_info`/team and the
  blob was a red herring for the 3D symptom (pursue 4b/4c only).
