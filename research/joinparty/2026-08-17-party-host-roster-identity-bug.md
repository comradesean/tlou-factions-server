# Join-Party "wrong player id / kicks itself" (mgnomad2 host): the roster the stub sends the party HOST is provably correct — the self-named kick is a blank-NpId PEER_DEACTIVATED display artifact, not a roster identity swap

Fourth pass on the friends-list Join-Party collapse, this time re-examining the
**identity** angle on a fresh clean single-attempt capture (stub clock 09:53-09:54,
room `0x1387f58`, role REVERSED vs the earlier notes: **mgnomad2 = party HOST,
comradesean = JOINER**). Builds on and does not re-derive:
- `2026-08-17-join-party-p2p-collapse-signaling-deactivation.md` ("note A") — collapse = `PEER_DEACTIVATED` blank-NpId → wholesale kick.
- `2026-08-17-join-party-friendslist-rootcause.md` ("note B") — RPCN is broker+STUN not relay; the npid-derived fake-IP is RPCS3 internal; server inputs byte-identical across invite/join.

Every EBOOT address below was re-verified this pass against the decompile/disasm
(`research/ghidra/fm_reg_decomp.txt`, `research/ghidra/dispatch_raw2.txt`).

---

## TL;DR (bottom line)

The orchestrator's four candidate stub defects — (a) host self-entry is_local/owner
flag wrong so the host signals itself, (b) NpId-handle format read as an address,
(c) member_id/roster-index collision from the shared static room `0x1387f58`,
(d) joiner entry carrying the host's npid — are **ALL FALSIFIED by evidence.**
The 2-member roster the stub sends the HOST is byte-correct: entry0 = `mgnomad2`
/ member_id=1 (flagged local+owner, never signals), entry1 = `comradesean`
/ member_id=2 (flagged remote, signals to the real peer). Live signaling
mutually activates for `comradesean` at the correct real address
`192.168.1.100:3658`. **There is no stub roster/id/flag/NpId-format defect to fix.**

The `****lost connection to party member mgnomad2, kicking from party` line naming
the LOCAL player is a **display fallback**: the `PEER_DEACTIVATED` callback arrives
with a BLANK NpId (note A, HIGH), the kick formatter's `%s` cannot resolve it to the
actual dead remote, and it falls back to a default member record — on the host's
console that default is the host's own/first slot (`mgnomad2`). It is a symptom of
the P2P signaling deactivation, **not** proof that `comradesean`'s slot was
overwritten with `mgnomad2`'s identity. This confirms notes A/B: the residual break
is a client-to-client sceNpSignaling keepalive collapse; the only server-shaped
lever is RPCN's Drop-path (out of scope here), not the SessionManager stub.

---

## 1. Why the lost member resolves to the LOCAL player ("mgnomad2")

**The kick string is table-driven and its `%s` is NOT statically traceable** (note A §1,
re-confirmed): `****lost connection to party member %s, kicking from party` @ VMA
`0xe79f90` (file off `0xe69f90`); the only image reference is the generic
debug-string-builder noise slot `0x0125c818` (false positive). So the printed name
cannot be tied to a specific member slot from the string side.

**The name is unreliable by construction.** Note A established (HIGH, direct
RPCS3-log evidence) that the collapse is a `SCE_NP_SIGNALING_EVENT_EXT_PEER_DEACTIVATED`
delivered with a **blank NpId**. The party-liveness kick formats `%s` from resolving
that event's npid to a party-member record; a blank npid matches nothing, so the
resolver returns a default (the local/first member). On MGNOMAD2's console the local
member is `mgnomad2` (member_id=1, first roster slot) → the kick prints "mgnomad2".
On the earlier joiner-console captures it printed the remote host it was joined to.
Same fallback, different console — **a display artifact of the blank-npid deactivation,
not a roster identity swap.**

**Signaling itself identifies the peer CORRECTLY**, which rules out a genuine identity
mixup: the live TTY shows both
`PEER_ACTIVATED comradesean 99.111.109.114 24932` and
`MUTUAL_ACTIVATED comradesean … 192.168.1.100:3658`. The second is the *real* LAN
address RPCN resolved for comradesean. The first "address" `99.111.109.114:24932`
decodes to ASCII `comr`+`ad` — i.e. RPCS3's **internal fake-IP encoding of the npid
string** (note B §3, HIGH: RPCS3 represents an npid as a fake IP; it is not routed and
not a stub data-misinterpretation). Both events **name `comradesean`**, so the peer
identity in the signaling layer is intact.

Confidence: name-is-a-blank-npid-fallback **HIGH** (note A log evidence + the correct
`comradesean` activations this capture); exact `%s` source slot **not traceable** (table-driven).

## 2. The exact roster/flag/NpId logic — verified, and correct

### 2a. is_local / is_owner are `(member_id == local_ref_id/owner_ref_id)` — verified disasm
`FUN_00ad7604` case `0x131`, the per-entry flag computation at `0x00ad795c`-`0x00ad7998`
(`research/ghidra/dispatch_raw2.txt`), register provenance verified from the loop setup
at `0x00ad77c4`-`0x00ad7838`:
- r31 = message/header base; r23 = `header+0xc4` = first entry `+0x24` = **member_id** (stride `0x68`); r26 = header (owner_ref_id @ `+0xc`, local_ref_id @ `+0xe`).
- `lhz r5,0(r7)` = member_id; `lhz r0,0xe(r26)` = local_ref_id; `lhz r6,0xc(r26)` = owner_ref_id.
- `xor r5,r5,r0` then `subi r5,r5,1` then `rldicl r5,r5,1,0x3f` → r5 = sign-bit of `(member_id ^ local_ref_id) - 1` = **1 iff member_id == local_ref_id** (is_local). Same pattern for r6 with owner_ref_id (is_owner).
- r5 (is_local) and r6 (is_owner) are passed to `FUN_00ad33d8` at `0x00ad79d0`.

### 2b. Signaling opens ONLY for is_local==0 — verified decompile
`FUN_00ad33d8` @ `0x00ad33d8` (`research/ghidra/fm_reg_decomp.txt`),
`param_3` = is_local flag (r5):
```c
if ((param_3 & 0xff) == 0) {                 // is_local == 0 only
    piVar5 = **(signaling ctx);
    pcVar6 = *(vtable + 0x10);               // signaling connect (== docstring 0xad34a4)
    iVar18 = (*pcVar6)(piVar5, param_2 + 4);  // connect to entry npid (param_2+4 = entry[0:] npid)
    param_1[slot*0x60 + 0x1d6] = iVar18;      // store conn handle
}
```
The entry loop above it looks members up **by npid compare** (`FUN_00e459bc(slot+0x19a, param_2+4)`),
confirming member identity is npid-keyed. So an is_local==1 slot **never** opens
signaling regardless of whether its npid field is filled — which is also why the
**solo host works** (populate_self_npid=True + is_local=1, no self-signal crash,
live-confirmed in prior passes).

### 2c. The actual bytes the stub sends the HOST — reconstructed and correct
Regenerated offline from the live stub's own `build_member` (no code edits;
`scratchpad/gen_roster.py`), inputs taken from the 09:54 capture
(`host_entry=(1, "mgnomad2")`, `joiner_entry=(2, "comradesean")`, owner_ref=local_ref=1,
room_ptr=`0x1387f58`, populate_self_npid=True):
```
 header: opcode 0131 | room_ptr 01387f58 | owner_ref 0001 | local_ref 0001
         room_id 0000000001387f58 | capacity 0008 | roster_count 0002
 entry0 @0xa0 : npid "mgnomad2"    member_id 0001  → is_local=1 is_owner=1  (NO signal)
 entry1 @0x108: npid "comradesean" member_id 0002  → is_local=0 is_owner=0  (signals comradesean)
```
This is exactly what §2a/§2b require. **No self-signal, no npid swap, distinct correct
npids, correct member_ids.** The 1-member RoomCreate roster hexdumped live at
`session_manager_stub-run.log` 09:54:20.360 is the same shape (member_id=1, `mgnomad2`,
local+owner) and is what the solo host already runs on successfully.

### 2d. Verdict on the four candidate defects
- **(a) host signals itself — FALSIFIED** (§2a/§2b: is_local=1 for the host entry, and the signaling call is gated `is_local==0`; plus the working-solo-host precedent).
- **(b) NpId-as-address format bug — FALSIFIED** (§1: the "comrad" fake-IP is RPCS3's own npid encoding; the *real* address resolved and `MUTUAL_ACTIVATED comradesean 192.168.1.100:3658` fired, so the npid handle is valid for signaling). The raw-16-byte online-id is what RPCN keys on and it matched.
- **(c) member_id / room-index collision from shared `0x1387f58` — FALSIFIED for this capture** (single clean attempt, no stale entry; the stub's most-recent-match join logic picked the live host; member_ids 1/2 distinct).
- **(d) joiner entry carries host npid — FALSIFIED** (§2c and the RoomCreate handler at `session_manager_stub.py:1163-1171`: `host["npid"]` = the RoomCreate sender `mgnomad2`; `own_npid` on the 0x130 connection = `comradesean`; entries are `(1,mgnomad2)`,`(2,comradesean)`).

Confidence: **HIGH** (disasm + decompile + regenerated wire bytes + live log all agree).

## 3. Why Invite works but Join doesn't (role reversal / friends-list path)

Server inputs are **byte-identical** across the two paths (notes A §3 / B §1, re-confirmed:
one RoomCreate + one 0x130, self-first rosters, real npids, OwnerChanged/OwnerMember;
the stub literally cannot tell invite from Join-Party). The only differences are:
1. **Role reversal** — invite = comradesean HOST / mgnomad2 JOIN (works); Join-Party =
   mgnomad2 HOST / comradesean JOIN (breaks). This reversal changes *which console emits
   the self-named kick* (§1) but not the roster correctness (§2, symmetric by member_id).
2. **Client-internal party arming** — the joiner's party on the Join-Party path is
   **auto-created reactively** from the incoming 267 tag rather than by an active Invite
   click (note B §1/§5). The P2P signaling keepalive arming differs between those two
   local flows, and that difference is entirely client-side — the stub/RPCN inputs are
   provably identical, so it is not reshapeable from the SessionManager stub.

Confidence: server-identical **HIGH**; client-internal-arming-is-the-differentiator
**MEDIUM** (note B, not yet isolated by capture).

## 4. Concrete fix + wire validation

**There is no targeted SessionManager-stub fix**, because the data the stub sends the
host is verified correct (§2). Inventing a roster/flag change would regress the working
solo-host and invite paths without addressing the actual break (a post-`MUTUAL_ACTIVATED`
P2P signaling deactivation).

- **Wire validation of the host roster (already correct):** capture the 2-member
  `0x131` Member the stub sends the host on join and confirm it matches §2c — in
  particular `owner_ref@0xc = 0001`, `local_ref@0xe = 0001`, entry0 npid `mgnomad2`
  with member_id@`0xc4 = 0001`, entry1 npid `comradesean` with member_id@`0x12c = 0002`.
  Live RPCS3 TTY should then show exactly ONE `Activate Connection` — toward
  `comradesean` — and NO `sceNpSignaling…0x8002a816 OWN_NP_ID` self-signal (this capture
  shows precisely that: `Activate Connection comradesean`, no OWN_NP_ID). That is the
  positive proof the host is not signaling itself.

- **The actual server-shaped lever (out of scope here, RPCN):** note B §5's Drop-path
  grace window — defer the offline `FriendStatus` notification and the
  `signaling_info`/`client_infos` eviction ~10 s and cancel on re-Login — is the only
  server change causally in the loop, and it is in RPCN (explicitly off-limits for this
  task). No stub change substitutes for it.

## Appendix: the 0x8002a818 callback code

This clean capture's collapse callback is `NpSignalingCallback 0 errorCode = 8002a818`,
which is **NOT** `0x8002a816` (`SCE_NP_SIGNALING_ERROR_OWN_NP_ID`, the self-signal
rejection) — so the host is not signaling itself (consistent with §2). Per note A's
empirical tally `0x8002a818` is the **transient/recoverable** signaling state (x28,
re-activates), distinct from the fatal DEAD `0x8002a810` (x10, every collapse). The exact
Sony symbol for `0x8002a818` was **not resolved** by RPCS3 in the logs and is left
UNVERIFIED here (candidate cluster: peer/netinfo timeout, not OWN_NP_ID); it should be
cross-checked against RPCS3's `sceNp.h` before being named. That a *transient* code
preceded a fast collapse matches note A's "activate→MUTUAL→deactivate compresses to ~1s"
tight-session behavior — the same mechanism, caught in a single clean attempt.

## Confidence summary
- Stub host roster is byte-correct (no self-signal, no npid swap): **HIGH** (disasm 2a + decompile 2b + regenerated bytes 2c + live activations).
- "Names local player" = blank-npid PEER_DEACTIVATED display fallback, not identity swap: **HIGH** (note A) — the `%s` slot itself is table-driven/untraceable.
- All four candidate stub defects falsified: **HIGH**.
- Invite/Join server-identical; differentiator is client-internal: server-identical **HIGH**, client-arming-cause **MEDIUM**.
- No stub fix exists; lever is RPCN Drop-path (off-limits): **HIGH** for "not the stub", **MEDIUM-HIGH** for the RPCN mitigation (note B).
- `0x8002a818` exact Sony symbol: **UNVERIFIED** (empirically transient per note A).

## Tooling
Ghidra headless `DecompileByAddresses.java` (`ad33d8`, `ad7604` → `research/ghidra/fm_reg_decomp.txt`);
`research/ghidra/dispatch_raw2.txt` (raw 0x131 disasm); `scratchpad/gen_roster.py`
(offline `build_member` regeneration, no stub edits); reads of
`tools/session_manager_stub.py` + `session_manager_stub-run.log` (09:53-09:54 capture).
Stale Ghidra project lock (`tlou_factions.lock{,~}`) removed once after a killed run.
