# "Join Party" (friends-list) root cause: the handshake works and the stub no longer churns — the residual break is a P2P sceNpSignaling collapse driven by mid-party RPCN NP-session churn, and RPCN is provably a broker (not a relay), so the one server lever is a Drop-path grace window

Third pass, building on (cite, do not re-derive):
- `2026-08-17-join-party-presence-discovery.md` — the presence→267→268→0x130 read chain (all EBOOT addresses verified there).
- `2026-08-17-join-party-p2p-collapse-signaling-deactivation.md` ("note A") — the collapse = `PEER_DEACTIVATED` errorCode `0x8002a810` with blank NpId → wholesale kick.
- `2026-08-14-room-create-joined.md`, `2026-08-14-signaling-crash-npid-trace.md` — the 0x132/0x130 stub layout and the earlier (now-fixed) malformed-signaling crash class.

Sources this pass (all fresh, same live run):
- `tools/session_manager_stub.py` + `session_manager_stub-run.log` (Aug 17, through 08:42).
- `backend/rpcn/src/server/{client.rs, udp_server.rs, client/cmd_misc.rs}` (source read this pass).
- `backend/rpcn/rpcn-run.log` (5143 lines, same run).
- RPCS3 log `/mnt/f/rpcs3_testing/.../log/RPCS3.log` (5.1 GB, single-pass marker extraction).

---

## TL;DR

1. **The friends-list Join-Party handshake fully completes** and is byte-for-byte the
   invite path's terminal step. Confirmed AGAIN live this pass: at stub-clock
   `04:32:37` mgnomad2 hosts PARTY room `0000000001387f58` (room_ptr=`0x1387f58`),
   comradesean sends `0x130` and is **`JOINED ... as member_id=2`**
   (`session_manager_stub-run.log:17509,17537`). This is not the break.

2. **The stub's periodic member-refresher — note A's suspected-but-unproven "no fix
   exists" wall — was itself the churn cause and is now FIXED.** The refresher's every-10s
   full-roster re-broadcast made the host "join and LEAVE its own party," emitting the
   exact `PEER_DEACTIVATED`/kick spam. `start_member_refresher` now SKIPS any room with
   `len(members) > 1` AND any solo `PARTY_ROOM_PTR` occupant (`session_manager_stub.py`
   guards at the two `return`s). This is live-observed skipping correctly on the
   `04:32:37` Join-Party (`...-run.log:17539-17556`), and commit `6b66c4b` validated a
   **~25-min held 2-member match with ZERO party-churn**. So for a stub-clean party the
   room self-maintains over P2P. **This supersedes note A §3's "no stub fix exists."**

3. **The residual break is a genuine client-to-client sceNpSignaling keepalive collapse**
   (`0x8002a810` `PEER_DEACTIVATED`, blank NpId → wholesale "lost connection to party
   member" kick — note A). It is real and still present: the current run's RPCS3 log
   has **121,643 kick-spam lines / 103 `PEER_DEACTIVATED` / 202 `0x8002a810`**, yet the
   SAME log also holds parties that survive **30 minutes** (last `joined party` for BOTH
   players at in-game `[1801.4167]`). Intermittent, not deterministic → a robustness/race,
   not a protocol bug.

4. **RPCN is a signaling ADDRESS BROKER + STUN echo, NOT a P2P packet relay** (source-
   verified this pass — corrects note A §2/§4, which flagged this MEDIUM/"addressing mode
   not source-verified"). `ClientSharedSignalingInfo` holds only
   `addr_p2p_ipv4/ipv6/local_addr_p2p` (`client.rs:68-71`); `req_signaling_infos` hands
   the caller the peer's IP:port (`cmd_misc.rs:82-111`, log shows correct
   `comradesean => 192.168.1.100:3658`, `mgnomad2 => …121:3658`); `udp_server.rs:130-182`
   is a STUN-style echo that only records each client's observed public addr. **RPCN never
   forwards packets between two clients.** Therefore evicting `signaling_info` cannot sever
   an already-flowing P2P datapath — it can only break a *future* lookup or a friend-status
   view. This narrows the causal surface precisely.

5. **The one server-shaped causal lever, with stronger evidence than note A had:**
   **both consoles churn their RPCN/NP session mid-party.** In the party window
   (`rpcn-run.log` lines ~1150-1780) the live 267/268 handshake (`SendMessage
   main_type=3`, ×19) and `RequestSignalingInfos` (both directions, correct addrs) are
   **interleaved with a repeating `…ResetState → Terminate → Disconnecting client(X) →
   Login`** for BOTH comradesean and mgnomad2. Each `Terminate` → RPCN `Client::drop`
   (`client.rs:356-388`) → (a) `create_friend_status_notification(npid, …, false)` pushed
   to the peer (**peer sees the party member go OFFLINE**) and (b) `client_infos.remove`
   → **`signaling_info` evicted**, with **no grace window**. This is the churn class the
   project forked RPCN to escape.

6. **Single most-actionable fix (server-side mitigation of a client-side root):** add a
   **~10 s grace window to RPCN's Drop path** — defer both the offline `FriendStatus`
   notification AND the `signaling_info`/`client_infos` eviction, and CANCEL them if the
   same `user_id` re-logs-in within the window (the log shows the client re-`Login`s
   almost immediately). This makes the mid-party churn invisible to the peer: the party
   member never appears offline and a peer's re-query never sees the eviction gap.
   **Confirming observable (note A §5, still the closing capture):** a Join-Party held
   across a logged peer `Terminate`+relogin should then show NO new `0x8002a810` /
   "lost connection to party member" in that window; a Wireshark trace on UDP 3658 tells
   apart the two sub-vectors in §4 below.

---

## 1. Divergence point from the working Invite path: there isn't one anymore

Note A §3 established the server inputs are byte-identical (one RoomCreate + one 0x130,
identical rosters). This pass confirms the handshake completes identically for the
discovery-join and that the stub's post-join behaviour is now churn-free:

- `04:32:36.897` mgnomad2 `0x12f` RoomCreate, room_ptr **`0x1387f58` = PARTY_ROOM_PTR**,
  map_id `0x12` (`...-run.log:17508`). `04:32:37.159` refresher **SKIPPED — PARTY room**
  (solo guard). `04:32:37.395` comradesean `0x130` → **JOINED as member_id=2**
  (`:17537`). `04:32:37.416/.417` refresher **SKIPPED — 2-member room** (multi guard).

So the discovery-join produces the same `member_id=2` join the invite path does, and the
stub then correctly stands back. The Invite vs Join divergence in *establishment* is nil
(note A §2) and the divergence in *stub handling* is now nil too. **The only remaining
difference is timing/robustness of the post-join P2P link, not a protocol path.**

Confidence: **HIGH** (live stub log this pass + note A/B verified chains).

## 2. Layer of the break: SIGNALING (P2P keepalive), not presence, not matchmaking

- **Presence layer — ruled out.** Note B proved RPCN stores/delivers the 96-byte blob
  verbatim at login + on change; the `0x130`'s room_id comes from the host's authoritative
  268 reply, not the presence read, so presence is not load-bearing for the join packet.
  This run: 1103 `SetPresence` succeed, presence flows.
- **Matchmaking layer — ruled out for this path.** RPCN handles **zero** room/Matching2
  commands (`grep` of `rpcn-run.log`: 0 CreateRoom/JoinRoom/SearchRoom/Matching2); the
  `0x130` is entirely SessionManager-stub territory and the stub pairs it correctly (§1).
- **Signaling layer — this is the break.** Current RPCS3 log: 121,643 "lost connection to
  party member", 103 `PEER_DEACTIVATED`, 202 `0x8002a810`, against 231 `joined party` /
  221 `MUTUAL_ACTIVATED`. Same signature note A nailed (blank-NpId `PEER_DEACTIVATED`
  errorCode `0x8002a810` → wholesale kick), still live.

Confidence: **HIGH** (marker counts direct from the 5.1 GB current log; mechanism from
note A).

## 3. RPCN presence/friends/signaling: complete, correct, and NOT in the P2P datapath

- Presence store/deliver: complete (note B §3; re-confirmed, 1103 SetPresence OK).
- **Signaling is BROKER + STUN only (new source proof):**
  - `ClientSharedSignalingInfo { addr_p2p_ipv4:([u8;4],u16), addr_p2p_ipv6, local_addr_p2p }`
    — addresses only (`client.rs:68-71`).
  - `req_signaling_infos` returns the peer's IP:port to the caller (`cmd_misc.rs:82-111`);
    live log returns correct LAN externs (.100/.121).
  - `udp_server.rs:130-182`: receives a 13-byte `[0x01|user_id|local_addr]` probe, records
    the observed public addr into `signaling_info` (`update_signaling_information`), echoes
    it back. **No two-client forwarding anywhere.**
  - ⇒ Once RequestSignalingInfos hands over the peer address, the sceNpSignaling keepalive
    is **direct console↔console UDP 3658** (same LAN here). RPCN is out of the datapath.
    This **retires note A §2/§4's MEDIUM** "peer addressed via RPCN's signaling layer"
    worry: the npid-derived display address there is RPCS3's internal fake-IP for the
    npid, not a routed-through-RPCN transport.

Consequence: an RPCN `signaling_info` eviction cannot cut a *flowing* link — it can only
(a) fail a *future* `RequestSignalingInfos` lookup, or (b) flip the peer's *friend-status
view* to offline. Both are exactly what the Drop path does, and both are addressable.

Confidence: **HIGH** (all four points source-read this pass).

## 4. The causal lever: mid-party NP-session churn on BOTH consoles

Evidence (`rpcn-run.log`, party window lines ~1150-1780, both npids):

```
… SendMessage(main_type=3)  [267/268 party handshake]
… RequestSignalingInfos comradesean => (extern ipv4) 192.168.1.100:3658  (Succeeded)
… RequestSignalingInfos mgnomad2   => (extern ipv4) 192.168.1.121:3658  (Succeeded)
… SetPresence …
… ResetState
… Terminate
Disconnecting client(comradesean)      <-- mid-party drop
… Login                                <-- immediate reconnect
… SendMessage(main_type=3) …           <-- handshake retried
… Terminate → Disconnecting client(mgnomad2) → Login   <-- other console too
```

Run totals: 90 `Terminate`, 93 `Disconnecting`, 107 `Login`, 9
`Connection reset by peer (os error 104)`. The *bulk* of the churn is boot-time NP
sign-in retry (`Login→GetNetworkTime→RequestTicket→Terminate`, lines ~190-430, before any
party traffic) — but a material amount is **interleaved with live party signaling** as
shown. Each `Terminate` returns `Err(NoError)` (`client.rs:651`) → process loop exits →
`Client::drop` runs (`client.rs:356-388`), which:
  1. pushes `create_friend_status_notification(npid, ts, false)` to all friends
     (`client.rs:382`) — **peer's party/friend manager sees the member go offline**, and
  2. `client_infos.remove(user_id)` (`client.rs:379`) — **evicts `signaling_info`**.

Two sub-vectors, both downstream of this churn, either of which produces the observed
`0x8002a810`:
- **(A) friend-status:** the kick string lives in the party/friend-manager CU
  (note A §1: `pPartyMember`, `…lost connection to party member %s…`). A member's
  friend-status flip to offline can make that manager treat the member as gone —
  independent of P2P UDP state.
- **(B) signaling re-query gap:** RPCS3 re-queries `RequestSignalingInfos` periodically
  (312 this run, both directions). If a re-query for the peer lands while the peer is
  in its `Terminate→Login` gap, `cmd_misc.rs` `client_infos.get(user_id).is_none()`
  returns **NotFound** (silently — no distinctive log line), and RPCS3 cannot refresh the
  peer address → signaling drops.

**Honest limit on the bridge:** the 5 `NotFound` visible in this log were all the
*empty-npid* soft-fail case (`cmd_misc.rs:37-59`, a find-match empty-slot artifact,
already handled), NOT a caught-red-handed peer eviction. The eviction→NotFound branch
(`cmd_misc.rs`, `is_none()`) is **code-path-confirmed and timing-plausible** but not
timestamp-proven here — RPCN's log carries no wall-clock, and RPCS3's is emulation-relative,
so the exact fatal coincidence still needs note A §5's unified capture. Vector (A) is
arguably the likelier fatal one (kick lives in the friend/party manager) and is not
gated on P2P state at all.

Confidence: mid-party churn on both consoles is real and coincident — **HIGH**.
Which sub-vector (A/B) is the dominant killer — **MEDIUM** (needs §5 capture / Wireshark).

## 5. The single most-actionable fix, and the honest scope

**Root** is client-side: RPCS3/TLOU tears down and re-inits its NP session
(`ResetState→Terminate→Login`) mid-party. The server cannot stop the client from
Terminating. But the server can make that churn **non-fatal to the peer's party**:

**RPCN Drop-path grace window (bounded change, `client.rs:356-388`):**
- On `drop`, do NOT immediately (a) send the offline `FriendStatus` notification or
  (b) `client_infos.remove`/evict `signaling_info`. Instead register the `user_id` in a
  "pending-offline" set with a ~10 s timer (`cleanup_duty` already exists as scaffolding).
- If the same `user_id` `Login`s within the window, cancel both — the peer never observes
  an offline flip and a re-query never sees the gap.
- Only after the window elapses without reconnect, run the current teardown.

Why this is the right lever: it directly neutralises BOTH sub-vectors in §4 with one
change, it's fully inside the forked RPCN the project controls, and the log shows the
client re-`Login`s almost immediately (grace window will virtually always catch it). It
subsumes and sharpens note A §4's `signaling_info`-only sketch by ALSO deferring the
friend-offline notification (the vector note A did not identify).

**Explicitly NOT the fix:** no stub change (the stub is clean — §1); no presence change
(complete — §3); reverting the refresher-skip (that WAS a real fix — §TL;DR 2). And
because RPCN is not a relay (§3), any "relay the P2P packets through RPCN" idea is a
non-starter for robustness.

**Do first (unchanged from note A §5, now with a concrete trigger to grep):** one
Join-Party attempt captured across three clocks — RPCS3 TTY (the `0x8002a810` instant),
`rpcn-run.log` (a peer `Terminate`+`Login` in the same window), and Wireshark UDP 3658
between the consoles. If the console-to-console keepalive datagrams **keep flowing** across
the peer's RPCN churn and the kick still fires → vector (A), friend-status; the grace
window's *notification deferral* half is the fix. If they **stop** coincident with the
churn → vector (B)/genuine P2P; the *signaling_info retention* half is the fix. Either
way the same one-change grace window covers it.

## Confidence summary
- Join-Party handshake completes = invite terminal step; not the break: **HIGH**.
- Stub refresher was the churn cause and is now fixed (multi-member skip): **HIGH**
  (source + live skip log + 25-min zero-churn validation) — supersedes note A §3.
- Residual break = P2P `0x8002a810` signaling collapse, intermittent: **HIGH**.
- RPCN is broker + STUN, not a relay (eviction ≠ cutting a flowing link): **HIGH**
  (source-verified) — corrects note A §2/§4 MEDIUM.
- Mid-party `ResetState→Terminate→Login` churn on both consoles, coincident with the
  party signaling window: **HIGH**.
- The specific fatal sub-vector (friend-offline vs signaling re-query NotFound) and the
  exact churn↔deactivation timestamp coincidence: **MEDIUM** (needs §5 capture).
- Grace-window Drop-path fix as the correct server lever: **MEDIUM-HIGH** as a mitigation;
  the churn *origin* is client-side and unremovable server-side.

## Tooling
No new tools. `grep -a` single-pass marker extraction over the 5.1 GB RPCS3 log
(`scratchpad/rpcs3_markers.txt`), grep over `rpcn-run.log` + `session_manager_stub-run.log`,
and source reads of `backend/rpcn/src/server/{client.rs, udp_server.rs, client/cmd_misc.rs}`.
RPCN's log has no wall-clock timestamps (tracing default here), which is the single biggest
obstacle to closing the §4 sub-vector — worth enabling `%time%` on the live RPCN before the
§5 capture.
