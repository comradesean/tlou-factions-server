# Join-from-friends-list takes the heavy session-manager path (Invite does not): the decision, the presence field, the NP-re-init ordering, and why no stub-only fix exists

Bottom line up front, then per-claim evidence with verified addresses and confidence tiers.

Builds on / corrects (cite, do not re-derive):
- `2026-08-17-join-party-presence-discovery.md` — the verified `presence -> tag267 -> tag268 -> 0x130` EBOOT chain and the 96-byte presence blob layout (all EBOOT addresses verified there).
- `2026-08-17-join-party-p2p-collapse-signaling-deactivation.md` ("collapse note") — the collapse = `PEER_DEACTIVATED` (`0x8002a810`/`0x8002a818`) with blank NpId -> wholesale kick.
- `2026-08-17-join-party-friendslist-rootcause.md` ("rootcause note") — the Drop-path grace-window mitigation and RPCN=broker-not-relay proof.

**This note CORRECTS a load-bearing claim in both prior notes** (collapse §3, rootcause §1): that "the server is byte-identical across Invite and Join and the stub cannot tell them apart." The fresh controlled A/B disproves it — Invite never registers a party room in the session-manager; Join does. There *is* a clean server-observable discriminator.

Fresh sources this pass (same live session as the A/B):
- `session_manager_stub-run.log` — the broken Join at wall-clock **09:53:55–09:54:21**, party room `0x1387f58` (lines 22987–23101). Read in full.
- `backend/rpcn/rpcn-run.log` (715 KB) — SendMessage main_type diagnostics + churn counts.
- Prior verified EBOOT chains (presence-discovery note) reused, not re-disassembled.

---

## TL;DR

1. **There is no runtime "light vs heavy" branch that a presence field flips.** "Invite to
   Party" and "Join from friends list" are two *structurally distinct client flows*.
   Invite = a pure RPCN flow (an NP invite `SendMessage main_type=3` + `SetPresence` +
   `RequestSignalingInfos` P2P), it **never** opens a session-manager room. Join = the
   `presence-read -> tag267 -> host tag268 -> 0x130` handshake which **always** terminates
   in a session-manager **RoomJoin (0x130)** against a host **RoomCreate (0x12f)**. The
   friends-list Join code path (`FUN_0035ca28`) has **no lightweight-add alternative** — it
   always emits the 267 (presence-discovery note §2). So "what field steers it" is the wrong
   frame: the *menu affordance itself* is the fork. Presence only decides whether the friend
   menu **offers** "Join" (and seeds the 267); once the user clicks Join, the heavy path is
   the only path.

2. **mgnomad2's presence DOES advertise a joinable session** — a be64 party room_id at
   presence-blob **offset +40** (= `room_obj+0x10`, the party room `0x1387f58`) plus a
   "joinable" byte at +7 (presence-discovery note §1, both SET and READ sides verified).
   This is what makes the friend menu light up "Join Party" while mgnomad2 sits at the main
   menu with a party. It is not *wrong* data (a party is legitimately joinable) — but it is
   the enabling condition for the heavy path. RPCN relays this blob **verbatim**; the content
   is authored by mgnomad2's own game client.

3. **The session-manager party registration is a clean discriminator (corrects prior
   notes).** Across the whole 24.7k-line stub log there are exactly **4** RoomCreates with
   `room_ptr=0x1387f58` / `map_id=0x12` — **all four are friends-list Joins** — versus **209**
   game-room RoomCreates (`room_ptr=0x1383bd8`, map_id 0x02/0x09/0x13). Invite parties
   produce **zero** session-manager rooms. The signature `map_id=0x12` occurs only 4× in the
   entire log. So the stub *can* tell Join from Invite; the earlier "byte-identical" claim
   conflated the find-match **game**-room RoomCreates with party establishment.

4. **The NP re-init is INHERENT to the Join flow and happens BEFORE our stub's RoomCreate
   exchange — our stub is provably not the trigger.** In the 09:53 capture both consoles open
   *fresh* session-manager TCP connections at 09:53:55 (comradesean/.100) and 09:53:59
   (mgnomad2/.121); the stub then sits **idle** for ~21 s (it only answered the hellos); the
   RoomCreate arrives at **09:54:20**, RoomJoin at 09:54:20.47, and the collapse (0x133
   abandon) at 09:54:21.07. The `ResetState -> Terminate -> Login` churn (RPCN log) occurs in
   that pre-RoomCreate window as part of the client's own session-join setup. Our stub emits
   nothing between the hellos and the client's RoomCreate, so it cannot cause the re-init.
   The re-init is client-inherent session-join behaviour.

5. **No stub-only or served-data fix makes Join behave like Invite.** The killer is the
   client-inherent NP re-init collapsing the P2P sceNpSignaling link (`0x8002a810` blank-NpId
   `PEER_DEACTIVATED` -> wholesale kick — collapse note). The stub is not in the P2P path and
   is not in the NP path. The only thing that would suppress the heavy path is **not
   advertising the joinable room_id in presence** — but presence is client-authored and
   RPCN-relayed, and RPCN is off-limits, so we cannot strip it server-side without touching
   RPCN. **Verdict: the heavy path is inherent client behaviour for friends-list Join.** The
   one server-shaped lever that would let P2P *survive* the inherent re-init is the RPCN
   Drop-path grace window (rootcause note §5) — an RPCN change, explicitly out of scope.

---

## 1. The two flows are different mechanisms, not two settings of one (Q1)

### The join flow always goes heavy — verified, no branch

`FUN_0035ca28` (the friends-list Join action, LR `0x35cac0`, presence-discovery note §2):
reads the selected friend's presence via `sceNpBasicGetFriendPresenceByNpId`, extracts the
be64 room_id from `blob+40` (`ld r9,168(r1)` where blob base `r1+128`), and **unconditionally
emits `sceNpBasicSendMessage` tag 267** to the host. The only early-out is *"I am already in
that exact room"* (`ld r0,16(party_obj); cmpd r0,r9; beq skip`). It sends the 267 even if the
presence read failed or room_id==0. **There is no code path in the join action that does a
lightweight presence/P2P-only add** — that alternative exists only in the separate
Invite-accept flow. So friends-list Join is hardwired to `267 -> 268 -> 0x130`.

The host answers 267 in `_opd_FUN_003ca9d0` (poll tag 267 @ `0x3caad0`), gated on
`lbz r0,6644(party_obj)` (`obj+0x19f4`, the same "joinable" byte published at presence +7),
then replies tag 268; the joiner's 268 handler `FUN_0035ed78` -> `FUN_0035b2c8` @ `0x35b358`
-> `FUN_00ad2768` -> **vtable+0x18 = `0x00ad6718` (the 0x130 RoomJoin sender)**. All addresses
verified in the presence-discovery note.

### What the wire proves the host also does: register the party in the session-manager

The presence-discovery note traced the *joiner's* 0x130 but did not note that the **host**
registers a session-manager room. The 09:53 capture shows it directly: on receiving the 267,
**mgnomad2 (the host/target) sends `0x12f` RoomCreate for the party room** before the joiner's
0x130 lands:

```
09:53:55.259  SM conn from .100 (comradesean)  client_hello
09:53:59.558  SM conn from .121 (mgnomad2)      client_hello
09:54:20.105  0x12f RoomCreate  room_ptr=0x1387f58  map_id=0x12   (from mgnomad2)   <-- host registers PARTY as a session
09:54:20.469  0x130 RoomJoin    room 0x1387f58 member_id=2         (from comradesean) <-- joiner joins it
09:54:21.071  0x133 abandon     room 0x1387f58                     (from comradesean) <-- collapse, ~0.6s later
```

The RoomCreate wire (line 23011f) carries a full matchmaking-style host descriptor: region
`"us"` at +0x10, and a host session token **`mgnomad2.1786974860`** at +0x2c — i.e. the party
is being registered as if it were a matchmade **game session**, not a lightweight party.
Invite never does this.

> **Answer Q1:** The friends-list Join does not *decide* between light and heavy at runtime —
> it *is* the heavy path. Reading the target's presence only (a) gates whether the menu offers
> "Join" and (b) seeds the 267. The presence field that enables it is the be64 room_id at
> blob +40 (and the joinable byte at +7). Once Join is clicked, the client always runs
> `267 -> host 0x12f RoomCreate + tag268 -> joiner 0x130 RoomJoin`, and both consoles re-init
> NP as part of entering that session-join. Invite is a wholly separate mechanism (NP invite
> message + presence + P2P) that never touches the session-manager. **Confidence: HIGH**
> (EBOOT chain verified in presence-discovery note; the host-RoomCreate escalation and the
> discriminator are direct from the 09:53 wire).

## 2. mgnomad2's presence advertises a joinable session (Q2)

- **Layout (verified both directions, presence-discovery note §1):** 96-byte blob published by
  `FUN_00397d74` via `sceNpBasicSetPresenceDetails`. `+7` = "party joinable/accepting" byte
  (= `room_obj+0x19f4`, the host's 267-gate byte); **`+40` = be64 room_id = `room_obj+0x10`**
  = the party room `0x1387f58`; `+56..+87` = host signaling-address descriptors. Not a
  `sceNpMatching2` descriptor (Matching2 is linked-but-dormant — presence-discovery §1 box).
- **RPCN carries it verbatim** (`cmd_misc.rs::set_presence`, data capped at 128 B; 96 fits) and
  delivers to friends at login and on change. This session: **1285 SetPresence** succeed. RPCN
  does not author or mutate the blob.
- **Invite vs Join presence content:** the blob is the same either way — mgnomad2 at the main
  menu with a party publishes room_id `0x1387f58` at +40 and the joinable byte at +7 in **both**
  scenarios (the presence heartbeat is party-state-driven, not menu-action-driven). That is why
  the friend menu offers "Join Party" at all. It is **not carrying a *wrong* session** — the
  party is genuinely joinable — but it *is* the enabling condition: presence advertises a
  joinable room, so the friend menu exposes the heavy Join, and clicking it commits to the
  session-manager RoomJoin path.

> **Answer Q2:** Yes — mgnomad2's presence advertises a joinable party as a be64 room_id at
> blob +40 (plus the joinable byte at +7). It is the same in the Invite and Join scenarios; it
> is legitimate data, but it is precisely what lights up the heavy "Join Party" affordance.
> RPCN relays it verbatim; the content is set by mgnomad2's client. **Confidence: HIGH** for
> the layout/relay; **MEDIUM-HIGH** that zeroing +40/+7 would suppress the menu affordance
> (inferred from the menu-gate logic, not live-tested by mutating presence).

## 3. The NP re-init is inherent and precedes our RoomCreate exchange (Q3)

Ordering, from the 09:53 stub capture (wall-clock) + RPCN churn:
- Fresh session-manager TCP connections open at **09:53:55** and **09:53:59** — i.e. the Join
  flow *begins* by re-connecting to the session-manager (the prior SM connection was closed at
  09:52:03; there was a ~38-min idle before that from the last match at 09:15). These are
  brand-new connections tied to the Join action.
- The stub answers only the two `client_hello`/`ClientHello2` and then **emits nothing** until
  the client's RoomCreate at **09:54:20** — a ~21–25 s idle gap on the stub side (log lines
  23010 -> 23011 contain no stub output).
- The `ResetState -> Terminate -> Login -> re-RequestTicket -> re-SetPresence` churn (RPCN log:
  81 ResetState, 94 Terminate, 112 Login, 10 os-error-104 across the session; interleaved with
  the party `SendMessage main_type=1` handshake per rootcause note §4) occurs in that
  pre-RoomCreate window as the client's own session-join bring-up.
- RoomCreate 09:54:20 -> RoomJoin 09:54:20.47 -> collapse (0x133) 09:54:21.07.

Because our stub produces no output between the hellos (09:53:55/59) and the client-initiated
RoomCreate (09:54:20), **the stub is causally out of the NP-re-init loop** — the re-init is
already underway before the stub does anything beyond the handshake, and NP is RPCN territory,
not the stub's. The re-init is inherent to the client entering the session-join flow.

> **Answer Q3:** The NP re-init is inherent client behaviour and happens **before** (and
> independent of) our session-manager RoomCreate/RoomJoin exchange. Our stub's responses do not
> trigger it. **Confidence: HIGH** (stub-side idle gap is directly in the timestamped log; NP
> path is RPCN, which the stub never touches).

## 4. The fix — and the honest "it's inherent" verdict (Q4)

**No stub-only or served-data change makes friends-list Join behave like Invite.** Reasons:

- The *establishment* difference (heavy session-manager RoomJoin vs light P2P add) is a client
  code-path choice made the instant Join is clicked (§1); the stub is downstream of it and
  merely services the RoomCreate/RoomJoin it is handed. Refusing to service the party RoomCreate
  would break the join outright, not silently downgrade it to the invite mechanism (the client
  has no fallback — §1).
- The *fatal* event is the P2P `sceNpSignaling` collapse (`0x8002a810` blank-NpId
  `PEER_DEACTIVATED` -> wholesale party kick — collapse note) driven by the inherent mid-join
  NP re-init evicting the peer's RPCN signaling registration and flipping friend-status offline.
  The stub is not in the P2P path or the NP path, so it cannot prevent this.
- The one served-data lever that would *prevent* the heavy affordance — **not advertising the
  joinable room_id (+40) / joinable byte (+7) in presence** — is not ours to set: presence is
  authored by mgnomad2's client and relayed verbatim by RPCN. Stripping those fields would
  require mutating presence inside RPCN, which is off-limits.

**Therefore the heavy path is inherent to friends-list Join.** What would have to be true
*server-side* for the P2P to survive the inherent re-init: the peer's **RPCN signaling
registration and friend-online status must persist across the mid-join `Terminate -> Login`
churn**, so that (a) the peer's periodic `RequestSignalingInfos` re-query never lands in a
`client_infos` NotFound gap and (b) the friend-status never flips offline and trips the
party-manager's "lost connection to party member" kick. Concretely that is the **RPCN
Drop-path grace window** (rootcause note §5): on `Client::drop`, defer both the offline
`FriendStatus` notification and the `client_infos`/`signaling_info` eviction for ~10 s and
cancel them if the same `user_id` re-logs-in within the window (the log shows the re-`Login`
is near-immediate). **This is an RPCN change and is explicitly out of scope here.** No change
confined to `session_manager_stub.py` or the data the stub serves closes the gap.

**Practical guidance for the revival, within scope:** friends-list "Join Party" cannot be made
lightweight from our side; steer users to **"Invite to Party"** (the working, session-manager-
free, churn-free mechanism). Making friends-list Join robust requires the RPCN grace-window
mitigation, which the project would have to accept as an RPCN patch.

> **Answer Q4:** No stub/served-data fix exists; the heavy path and its NP re-init are
> client-inherent to friends-list Join. The server-side condition that would let P2P survive is
> RPCN retaining the peer's signaling registration + online status across the mid-join relogin
> (a ~10 s Drop-path grace window) — an RPCN change, out of scope. **Confidence: HIGH** that no
> stub-only fix exists; **MEDIUM-HIGH** that the RPCN grace window is the correct and sufficient
> mitigation (mechanism is wired and sound; not yet closed by a unified-timestamp capture —
> rootcause note §5 / collapse note §5).

---

## Corrections logged against prior notes
- collapse note §3 and rootcause note §1 ("server byte-identical across Invite and Join; the
  stub cannot tell them apart"): **corrected.** Invite produces **zero** session-manager party
  rooms; Join produces a `room_ptr=0x1387f58` / `map_id=0x12` RoomCreate+RoomJoin pair (4/4
  occurrences in the log are Joins; that map_id appears only 4× total). The prior claim
  conflated the 209 find-match **game**-room RoomCreates (`0x1383bd8`) with party establishment.
- Everything else in the presence-discovery / collapse / rootcause notes stands and is reused.

## Confidence summary
- Two-distinct-mechanisms framing; join flow always heavy, no light branch: **HIGH** (EBOOT
  chain verified in presence-discovery note; host 0x12f escalation direct from 09:53 wire).
- Presence advertises joinable room_id @ +40 / byte @ +7; RPCN verbatim: **HIGH**.
- `map_id=0x12` / `0x1387f58` party RoomCreate is a Join-only discriminator: **HIGH** (4/4 in
  log; 209 game rooms are `0x1383bd8`).
- NP re-init inherent and precedes our RoomCreate; stub not the trigger: **HIGH** (timestamped
  idle gap).
- No stub/served-data fix; heavy path inherent: **HIGH**. RPCN grace-window as the sufficient
  server mitigation: **MEDIUM-HIGH** (out of scope; needs the unified capture to fully close).

## Tooling
No new tools. `grep`/`awk` over `session_manager_stub-run.log` and `backend/rpcn/rpcn-run.log`;
reused verified EBOOT addresses from `2026-08-17-join-party-presence-discovery.md` (no
re-disassembly this pass). RPCN log carries no wall-clock, so the NP-re-init ordering was
established from the stub's timestamped idle gap rather than cross-log timestamp correlation.
