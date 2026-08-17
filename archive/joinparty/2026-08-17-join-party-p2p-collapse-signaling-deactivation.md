# "Join Party" collapses ~1s after join: it is a sceNpSignaling DEAD (0x8002a810) deactivation, not a room/roster bug — and the server side is provably identical to the working invite path

Follow-up to `2026-08-17-join-party-presence-discovery.md`. That note closed the
`presence -> tag267 -> tag268 -> 0x130` handshake, and the join now COMPLETES live
(`0x130 ... JOINED comradesean's room 0000000001387f58 as member_id=2`). New
symptom: ~1s later the party collapses, RPCS3 TTY spamming
`****lost connection to party member <name>, kicking from party` at ~30x/s, one
client abandons (0x133), UI shows "left the party / failed to join". The SAME spam
ends the WORKING invite path at game-end.

Sources, all cross-checked:
- Decrypted EBOOT via `tools/eboot_analysis/` (objdump `--adjust-vma=0x10000`).
- `tools/session_manager_stub-run.log` (live stub).
- `backend/rpcn/rpcn-run.log` (2438 lines) and RPCN source.
- RPCS3 log (1.06 GB / 10.1M lines) `.../log/RPCS3.log`, grepped `-a`.

Every EBOOT address verified against disassembly.

---

## TL;DR

1. **Trigger of the spam (log-confirmed):** the party keepalive kicks a member
   when it receives a sceNpSignaling **`PEER_DEACTIVATED`** (EXT) event whose
   callback errorCode is **`0x8002a810`** (a fatal "connection dead / timed out";
   RPCS3 does not symbolically resolve the name, so treat it as unverified). The
   deactivation callback arrives with a **BLANK NpId**, so the game cannot match
   it to a specific member and kicks party members wholesale -> the ~30x/s spam.
   Contrast `0x8002a818`, which is **recoverable** (log shows it immediately
   re-activates). A member is "connected" iff its signaling connection is ACTIVE
   (errorCode 0, `PEER_ACTIVATED`/`MUTUAL_ACTIVATED`).

2. **Invite vs Join-Party divergence in signaling ESTABLISHMENT: THERE IS NONE.**
   On both paths the pair **mutually activates** for the correct single peer
   (`PEER_ACTIVATED mgnomad2` + `MUTUAL_ACTIVATED mgnomad2`, errorCode 0). The
   P2P/signaling link comes up identically. The collapse is a *post-establishment*
   `0x8002a810` timeout, the same event that ends the invite path at game-end.

3. **Shared-`0x1387f58` collision theory: REFUTED.** Signaling never confuses the
   peer identity - every activation names `mgnomad2`. The only empty identity is
   the `PEER_DEACTIVATED` callback's NpId, which is an RPCS3 emulator artifact of
   the deactivation event, not a room-object collision. `room_id
   0000000001387f58` is a static-object-derived constant identical on both
   consoles in BOTH paths, including the working invite path.

4. **Server-fixable?** No stub fix: the stub is byte-identical across the two
   paths (it cannot even tell them apart) and its job (room setup) succeeds. RPCN
   brokered the rendezvous correctly and symmetrically. The collapse is a
   client-to-client P2P signaling keepalive timeout. The one server-shaped lever
   that is causally in the loop is **RPCN connection stability** (see §4) - but it
   affects both paths equally, so it is a general P2P-fragility contributor, not
   the specific join-vs-invite differentiator. That differentiator is
   client-internal party-state (reactive auto-create vs active invite).

---

## 1. The emitter string is table-driven and NOT statically traceable

- `****lost connection to party member %s, kicking from party` @ VMA `0xe69f90`;
  sibling `...party host %s, leaving party` @ `0xe69fd0`;
  `A party member couldn't talk to the game host` @ `0xe6a8a8`; `pPartyMember` @
  `0xe6a900` - one compilation unit (a party/friend manager).
- The ONLY reference to `0xe69f90` in the image is pointer slot `0x0125c818`,
  loaded once at `0x0016d488`, which is inside `_opd_FUN_0016a204` - the
  recognized generic debug-string-builder **NOISE** pattern
  (`2026-08-16-net-sm-server-lobby-dispatch.md`: a long run of adjacent string
  slots each `bl 0x9f9d24` with `li r6,1`). FALSE POSITIVE.
- Siblings `0xe69fd0`/`0xe6a8a8` have NO 4-aligned pointer slot and no
  `lis+addi`/`ori` immediate build anywhere. => these party-health strings are
  reached only through a table the noise builder fills; the runtime emit indexes
  it by enum. String->emitter xref is a dead end. Per-frame cadence (~30ms) plus
  the runtime evidence in §2 identify the mechanism instead of the string.
- The liveness check reads each member's signaling status via the
  `0x00adc..0x00ade` helper family (`GetConnectionStatus` callers @ 0xadc56c/
  0xadcf40/0xaddb00/0xade11c; `GetConnectionFromNpId` @ 0xadce2c). The kick is
  driven by the EXT `PEER_DEACTIVATED` callback, not a polled status read (§2).

## 2. Runtime: establishment is identical; the collapse is a DEAD deactivation

RPCS3-log evidence (line anchors are into the 10.1M-line log):

**Working establishment (both paths look like this):** e.g. line 164965
`GetConnectionFromNpId -> 0x8002a80e CONN_NOT_FOUND` (expected first time) ->
`mgnomad2 joined party` -> `ActivateConnection` -> `NpId mgnomad2 connId 1` ->
`Activate Connection mgnomad2 4660 1` -> `sig CB 0x1 errorCode 0` ->
`GetConnectionStatus` -> `CB 0xc errorCode 0` -> **`MUTUAL_ACTIVATED mgnomad2`**.
Counts: `PEER_ACTIVATED` x12, `MUTUAL_ACTIVATED` x12, both always naming
`mgnomad2`, all errorCode 0. So the link ESTABLISHES for the correct peer.

**The collapse signature (invariant), first at line 596157 (t=296.70):**
`GetConnectionInfo(conn_id=1,code=3)` ->
**`*************** has left : SCE_NP_SIGNALING_EVENT_EXT_PEER_DEACTIVATED`** with
a **BLANK npid** -> `NpSignalingCallback 0 errorCode = 8002a810` ->
`sceNpSignalingTerminateConnection(conn_id=1)` ->
**`****lost connection to party member mgnomad2, kicking from party`**. The
sustained bursts (e.g. 622048+, ~37k lines) are the same kick logic spinning; the
surrounding lines are only PPU register dumps (r27 -> `", kicking from party"`),
**no CPU exception / assert / fatal nearby** - the game's own party code looping.

Total spam: 72,027 lines (comradesean 72,023, mgnomad2 4). `lost connection to
party host` = 0, `couldn't talk to the game host` = 0. `RequestSignalingInfos`
malformed / `reply_req_sign_infos` crashes = 0 (the old `2026-08-14` crash class
is gone). errorCodes seen in callbacks: `0` x63 (ok), **`0x8002a810` x10 (fatal -
every collapse)**, `0x8002a818` x28 (transient, re-activates).

**The connection stayed up ~266 s (t=30 -> t=296) before the first `0x8002a810`
killed it**, with zero intervening re-activations - i.e. an established link whose
keepalive eventually stopped being answered, not a link that failed to form. In
later/tighter sessions activate->MUTUAL->`0x8002a810` compresses to seconds
(e.g. activate t=134 -> MUTUAL t=134.5 -> dead t=172; and one PEER_ACTIVATED +
PEER_DEACTIVATED at the *same instant* t=143.0467). That compression is the "~1s
after join" symptom.

**Address note (medium confidence):** every `PEER_ACTIVATED` prints
`mgnomad2 109.103.110.111 28001` and every `Activate Connection` prints
`mgnomad2 4660 1` (4660 = 0x1234 placeholder). `109.103.110.111` = the ASCII
bytes `0x6d 0x67 0x6e 0x6f` = **"mgno"**, and port 28001 = `0x6d61` = **"ma"** -
i.e. the peer "address:port" is the first 6 bytes of the npid **"mgnomad2"**, not
the real LAN `192.168.1.121:3658` that RPCN returns. This strongly indicates the
P2P peer is addressed through RPCN's signaling layer (npid-keyed), not a direct
routable IP - which is why RPCN's liveness is causally in the P2P path (§4).
Flagged medium-confidence: the exact RPCS3 addressing mode was not source-verified
this pass.

## 3. Server side is byte-identical across the two paths (so no stub fix exists)

- **Stub** (`session_manager_stub-run.log`): every party sequence is exactly ONE
  RoomCreate from comradesean (room_ptr=`0x1387f58`) + ONE `0x130` from mgnomad2;
  mgnomad2 NEVER does its own party RoomCreate; identical rosters both ways
  (Member self-first, real npids populated, OwnerChanged/OwnerMember). The stub
  literally cannot distinguish invite from Join-Party.
- **RPCN** (`rpcn-run.log`): only auth/presence/messaging/signaling-info commands;
  no Matching2, no room commands. Join window (~line 1173): mgnomad2
  SendMessage(267) -> mgnomad2 RequestSignalingInfos(comradesean) -> comradesean
  SendMessage(268) + its own RequestSignalingInfos(mgnomad2). Mutual signaling-
  info exchange fires symmetrically, correct cross LAN addrs (.100/.121), and RPCN
  pushes a `SignalingHelper` notification to the opposite peer each way
  (`cmd_misc.rs:86-100`). No Malformed.
- **Signaling setup is npid-driven, path-independent:** the joiner's 268->join
  bridge `FUN_0035b2c8` (-> `0xad2768` -> vtable+0x18 -> `0xad6718` = 0x130
  sender) does not open signaling itself; signaling is opened when the stub's
  Member roster registers (`FUN_00ad33d8`, resolve @ `0xad34a4` for is_local==0)
  via `GetConnectionFromNpId(peer_npid)`. Same mechanism, same rosters, both paths.
- **Host 267-handler** `_opd_FUN_003ca9d0` passes the `obj+0x19f4` joinable gate
  and sends tag-268 (join completes) - the auto-created party reaches the same
  joinable state as an invite-initiated one.

Because everything the server controls is identical across the two paths, no stub
message can selectively fix Join-Party without changing invite (which works).

## 4. What WOULD affect it (the one server-shaped lever) - and its limits

The `0x8002a810` DEAD event = the emulated signaling keepalive for that peer
stopped being satisfied. Given the npid-derived P2P address (§2), the peer link
runs through RPCN's signaling layer, so **RPCN connection liveness is causally in
the P2P keepalive path.** `rpcn-run.log` shows heavy client churn:
- 55 `Disconnecting client(...)`, 63 Logins across the session.
- **4 abrupt `Connection reset by peer (os error 104)`** drops (comradesean lines
  242/826/1761, mgnomad2 line 2164) - not clean `Terminate`s.
- On EVERY disconnect RPCN runs `client_infos.remove(user_id)` (`client.rs:377`),
  which drops that client's `signaling_info` entirely (`client.rs:370` comment:
  "remove him from signaling infos").

So a client's transient TCP reset tears down its RPCN signaling registration; if
that coincides with an active party, the peer's signaling relay/lookup vanishes
and the keepalive dies -> `0x8002a810` -> wholesale party kick. This is the
concrete, testable server-side lever and matches the known
`rpcn-connection-instability.md` class the project forked RPCN to escape.

**Honest limit:** this churn hits invite and Join-Party equally, so it does NOT by
itself explain why Join-Party collapses fast while invite is stable. The
join-specific fragility is client-internal: comradesean's party is auto-created
*reactively* (from the incoming 267) rather than by an active Invite click, and
the P2P heartbeat arming appears to differ between those two local flows - a
client party-state-machine difference the server cannot reshape (stub/RPCN inputs
are provably identical). No confirmed server fix closes the join-vs-invite gap.

## 5. Verdict and fix plan

- **Collision theory: refuted** (§2/§3). **Stub fix: none possible** (§3).
- **The collapse mechanism is a P2P sceNpSignaling DEAD (`0x8002a810`) timeout**
  reported as "lost connection to party member", amplified by RPCS3 delivering the
  deactivation with an empty NpId -> wholesale kick.
- **Server lever (general robustness, not a targeted join fix, NOT implemented):**
  in RPCN, do not evict `signaling_info` immediately on TCP disconnect - keep it
  for a short grace window so a transient reset (os error 104) does not orphan an
  in-flight P2P link. Sketch: split `client_infos.remove` so `signaling_info`
  (and the friend online-state) survive ~5-10 s and are reclaimed by a reconnect,
  and separately diagnose WHY the clients' RPCN TCP keeps resetting mid-session.
  Deliberately left as a sketch: (a) it is not proven to be the join-specific
  cause, (b) it would need a rebuild + manual restart of the live RPCN, and (c)
  the running system must not be disturbed without the confirming capture below.
- **The one capture that settles it (do first):** a single Join-Party attempt with
  UNIFIED timestamps across three sources - RPCS3 TTY (for the `0x8002a810`
  PEER_DEACTIVATED instant), `rpcn-run.log` (for any Disconnect/os-error-104 in
  the same second), and a Wireshark capture on UDP 3658 between the two consoles
  (to see whether keepalive datagrams actually flow console-to-console after
  MUTUAL_ACTIVATED, and whether they stop coincident with an RPCN drop). If the
  UDP keepalives stop with NO RPCN drop, it is the client's reactive-auto-create
  heartbeat state (client-internal, unfixable server-side). If they stop
  coincident with an RPCN disconnect, the §4 RPCN grace-window fix is the target.

## Confidence
- Collapse = `PEER_DEACTIVATED` + errorCode `0x8002a810` -> kick, with empty npid:
  HIGH (direct RPCS3-log evidence, invariant across every occurrence).
- Signaling establishes identically (mutual activation, correct peer) both paths:
  HIGH.
- Collision theory refuted: HIGH.
- Server byte-identical across paths / no stub fix: HIGH.
- P2P addressed via RPCN signaling layer (npid-derived address) -> RPCN liveness
  causal: MEDIUM (address decode is exact, but the RPCS3 addressing mode was not
  source-verified).
- RPCN disconnect -> `0x8002a810` causal chain: MEDIUM (plausible + wired in
  `client.rs`, but not proven by cross-log timestamp correlation - needs §5).
- `0x8002a810` symbol name: UNVERIFIED (RPCS3 did not resolve it).

## Tooling
No new tools. `tools/eboot_analysis/{eb,scan_imm,scan_bl,scan_anchor,fnstart}.py`,
objdump, grep over the RPCS3 log and `rpcn-run.log`. The RPCS3-log correlation was
done via a delegated grep pass (line anchors above).
