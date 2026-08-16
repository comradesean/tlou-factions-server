# "Join Party" (friend-menu discovery join): the full data path, and why the invite works but the discovery-join is fragile

Mission: reverse the friend-menu **"Join Party"** flow (mgnomad2 selects comradesean
and asks to join HIS party — no direct invite message) so the revival can support it.
Contrast with **"Invite to Party"** (already working: host pushes the room_id to the
joiner in an NP message).

Everything below is evidence-first with confidence levels. Sources:
- Decrypted EBOOT `/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf`
  via `tools/eboot_analysis/` (objdump `--adjust-vma=0x10000` + `eb.py`/`scan_*`).
- Live RPCS3 log (comradesean's machine, 419 MB)
  `/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/log/RPCS3.log`.
- `backend/rpcn/rpcn-run.log` (running RPCN, 2161 lines) and RPCN source.
- Cross-refs: `2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md` (tag-267
  inbox + m_roomSize), `2026-08-16-two-player-party-and-match-working.md`,
  `2026-08-15-createparty-trace.md`.

Every EBOOT address below was verified against the disassembly and, where possible,
against the RPCS3 log's own HLE/LR lines.

---

## TL;DR (the one thing that reframes this)

**"Join Party" is NOT a separate join mechanism — it feeds the SAME
`tag-267 → tag-268 → 0x130` handshake the invite-accept path uses.** The only
difference is *where the joiner gets the host's room_id*: from the host's **presence
`data` blob** instead of from a pushed invite message.

Chain (all addresses verified):

```
click Join Party
  └─ FUN_00348e78 → FUN_0035ca28  (the Join-Party action)
       ├─ sceNpBasicGetFriendPresenceByNpId(host_npid)   ; read host presence
       ├─ extract be64 room_id from presence data blob +0x28 (offset 40)
       └─ FUN_003c908c → sceNpBasicSendMessage  tag 267 {room_id,flag}  → HOST
HOST receives 267
  └─ _opd_FUN_003ca9d0  (poll tag 267 @0x3caad0)
       ├─ gate: lbz r0,6644(party_obj)  (obj+0x19f4)  — must be nonzero
       └─ FUN_003c908c  tag 268 {host's own room_id} → JOINER
JOINER receives 268
  └─ FUN_0035ed78 (poll tag 268 @0x35ee20) → FUN_0035b2c8 → FUN_00ad2768
       → vtable+0x18 → FUN_00ad6718  =  0x130 RoomJoin sent to SessionManager
```

The final `0x130`'s room_id comes from the **268 reply body** (the host's authoritative
room_id), not from the joiner's presence read. So the presence value is *not*
load-bearing for the 0x130 itself — the handshake self-corrects. Presence only gates
whether the friend menu offers "Join" and seeds the 267.

**Consequences for the server:**
1. RPCN's presence store/deliver path is **complete and correct** (verified below):
   the 96-byte blob is stored verbatim and delivered to friends at login and on change.
2. The SessionManager stub **already handles `0x130`** (`session_manager_stub.py:919`)
   and would pair the join, exactly as it does for invite-accept.
3. Therefore the remaining gap is **not** "the server doesn't carry a room descriptor."
   The descriptor is carried. The gap is in the **client-to-client 267/268 handshake
   completing for the discovery-initiated case** — most concretely, whether the HOST
   answers the joiner's tag-267 with a tag-268 (host-side gate `obj+0x19f4`). This needs
   the *joiner's* log during a real Join-Party attempt to close; the exact diagnostic and
   the one server-side robustness lever are in §4.

---

## 1. The presence blob layout the game publishes  (confidence: HIGH)

TLOU publishes presence via **`sceNpBasicSetPresenceDetails`** — NID `0xbe81c71c`,
import stub `0xe5750c` (idx 8 in the sceNp NID table @ `0xe59460`; RegisterHandler
`0xBCC09FE7` @ idx 5 anchors the table). Log confirms both the identity and the call
site:

```
ppu_loader: [sceNpBasicSetPresenceDetails] (0xbe81c71c) -> 0xe5750c
sceNp: sceNpBasicSetPresenceDetails(pres=*0xd003fbc8, options=0x3)   [LR:0x00398168]
```

It fires on a ~10 s heartbeat (0:58, 1:18, 1:30, 1:40, …), `options=3`.

Two builders call it (both confirmed):
- **`FUN_00396ad8`** — a *title-only* clear: memsets a 392-byte details struct,
  strncpy's a title, sets `data_size = 0`. Publishes **no** data blob. (Idle / reset.)
- **`FUN_00397d74`** (LR `0x398168` in the log) — the **real builder**. It assembles a
  **96-byte `data` blob** on the stack (`r1+120`), only republishes when the blob
  **changed** (memcmp guard @ `0x398074` against the last-published copy at
  `presence_obj+0x50`), then memcpy's it into the details struct's `data` field and sets
  `data_size = 96`.

### The 96-byte blob (offsets are blob-relative; builder writes @ `r1+120+off`)

| off | src instruction | meaning |
|----:|---|---|
| +0  | `FUN_003ac0fc(party_obj,0,0)` | u32 session/party id or seq |
| +5  | `FUN_00ad1024()` | u8 |
| +6  | `lbz 24(party_obj)` | u8 (the same offset-24 flag the builder bails on) |
| +7  | `lbz 6644(room_obj)` = **`obj+0x19f4`** | u8 **"party joinable / accepting" state** — see §2, this is the byte the host's 267-handler gates on |
| +8  | `lwz 856(party_obj)` low byte | u8 |
| +12,+16 | 0 | |
| +20,+24 | `0xffffffff` | sentinels |
| +32 | 0 (8 B) | |
| **+40** | **`ld 16(room_obj)` = `room_obj+0x10`** | **be64 room_id — THE JOINABLE DESCRIPTOR** |
| +48 | `FUN_003c8ccc()` | u32 |
| +52 | 0 | |
| +56..+72 | big-endian u32s assembled byte-by-byte from `member_obj+788..807` (via `FUN_003cb89c`) | host/member **signaling address descriptors** (IP:port-shaped) |
| +84 | be u32 from `member_obj+812..815` | |
| +88 | `ld 304(*(-32704))` (8 B) | 64-bit value |

`room_obj+0x10` is the established room_id field for this object family: the `0x13a`
sender (`FUN_00ad6148`) and the tag-267 invite sender both read `room+0x10` as the
room_id (see the invite notes). So **+0x28 (offset 40) of the presence blob is the party
room_id** — the exact id the SessionManager and the invite path use.

**Verified on the READ side too** (§2): `FUN_0035ca28` copies the blob out and does
`ld r9,168(r1)` where the blob base is `r1+128` → `r1+168 = blob+40` → room_id.
Same offset both directions. That is the strongest single confirmation of the layout.

RPCN caps `data` at 128 bytes; 96 fits, no truncation.

> **Answer to task 1:** Yes — the presence blob carries a joinable room descriptor:
> a **be64 party room_id at blob offset 40**, plus a joinable-state byte at +7 and
> host signaling-address descriptors at +56..+87. It is **not** a `sceNpMatching2`
> room descriptor (Matching2 is dead code — see the box below).

### sceNpMatching2 is linked but dormant (confidence: HIGH)

The EBOOT imports ~28 `sceNpMatching2*` functions, and strings like
`sceNpMatching2JoinRoom() failed …` / `game/net/net-late-join.cpp` exist — but the
**419 MB runtime log shows only `sceNpMatching2Term` ever called (×4, teardown).**
No `Init2`, `CreateContext`, `JoinRoom`, `SearchRoom`, etc. ever ran. Those strings are
unreached asserts. **Join Party does not use Matching2; it uses the custom
SessionManager `0x130` path.** This matches the project's whole session model.

---

## 2. The "Join Party" read chain in the EBOOT  (confidence: HIGH)

### Read function

**`sceNpBasicGetFriendPresenceByNpId`** — NID `0xfd39ae13`, stub `0xe5770c`. Log:

```
ppu_loader: [sceNpBasicGetFriendPresenceByNpId] (0xfd39ae13) -> 0xe5770c
sceNp: sceNpBasicGetFriendPresenceByNpId(npid=*0x33749739, pres=*0x33749814, ...) [LR:0x00396c34]  ; background poll
sceNp: sceNpBasicGetFriendPresenceByNpId(npid=*0x013799a4, pres=*0xd003f7a0, ...) [LR:0x0035cac0]  ; ON-DEMAND join
```

Two call sites:
- **`FUN_00396be0`** (LR `0x396c34`) — `RefreshFriendPresence(friendObj)`: memsets a
  392-byte details struct at `friendObj+220`, fills it, timestamps `friendObj+752`.
  Driven by the background friend-list poller `FUN_00398674` (staleness = `+752 + 6000`
  vs now). This is the friends-list cache, not the join.
- **`FUN_0035ca28`** (LR `0x35cac0`) — the **Join-Party action**. `npid=*0x013799a4` is
  the *selected friend's* record (the on-stack `pres` buffer, not a cache slot, marks it
  as an on-demand read). Its only caller is `FUN_00348e78` (the friend-menu action).

### FUN_0035ca28 decompiled (the join action)

```
r29 = FUN_003985dc(list=*(-32536), key=*(-32448))   ; find selected-friend record; key obj @0x013799a4
...
bl 0xe5770c                          ; sceNpBasicGetFriendPresenceByNpId(host_npid, pres, 0)
cmpwi r3,0 ; bne 0x35cb0c            ; on FAIL still proceeds to the send
memcpy(r1+128, r1+480, 96)           ; copy the 96-byte presence data blob out
r9 = *(r1+168)                       ; = blob+40 = HOST room_id
cmpdi r9,0 ; std r9,112(r1)          ; body.room_id = r9
  beq 0x35cb0c                       ; room_id==0 -> still send (below)
r11 = *(-32724)                      ; my PARTY room object (= 0x01387f58)
lbz r0,184(r11) ; beq 0x35cb0c       ; if I'm not in a party -> send
ld  r0,16(r11)  ; cmpd r0,r9         ; my room_id == host room_id ?
  beq 0x35cb70                       ; already in that room -> SKIP send
0x35cb0c:
  r3 = r29+1 (HOST npid)             ; recipient = the selected friend (host)
  r4 = 267 ; r5 = body{room_id,flag} ; r6 = 16
  bl FUN_003c908c                    ; sceNpBasicSendMessage tag 267 -> HOST
```

Confirmations:
- `*(-32448) = 0x013799a4`, and the log's on-demand read is `npid=*0x013799a4`. **The
  read target is the selected friend (the host).** ✔
- `*(-32724) = 0x01387f58` = the PARTY room object (per the two-player note's global map). ✔
- **The joiner almost always SENDS the 267** — the only skip is "I'm already in that
  exact room." It sends even if the presence read failed or room_id==0.

### The 267 → 268 → 0x130 handshake (all verified)

- **Host receives 267** in `_opd_FUN_003ca9d0` (polls tag 267 @ `0x3caad0` via
  `FUN_003c8f20`, parses body via `FUN_003c9878`), then **replies tag 268**
  (`li r4,268; FUN_003c908c` @ `0x3cab58`) carrying its own room data. Gates before the
  reply:
  - `0x3cab08`: body parse must succeed.
  - **`0x3cab10`: `lbz r0,6644(party_obj)` (obj+0x19f4); `beq 0x3caffc` (bail, no reply)**
    — i.e. the host must be in the joinable state. *This is the same byte published at
    presence blob+7.*
  - `0x3cab24`: `FUN_00349360`; if result and `*(result+0x4c)!=0` → bail.
- **Joiner receives 268** in `FUN_0035ed78` (polls tag 268 @ `0x35ee20`, parses via
  `FUN_003c9878`) → **`FUN_0035b2c8`**.
- **`FUN_0035b2c8` @ `0x35b358` calls `FUN_00ad2768`**, which dispatches **vtable+0x18**
  (`lwz r9,0(obj); lwz r9,24(r9); bctrl` @ `0xad2928/0xad2954`). vtable+0x18 was
  read directly: vtable `0x01243b38` slot `+0x18` = `0x012e9c78` → OPD → **`0x00ad6718`
  = the `0x130` RoomJoin sender.** ✔ (Task's `FUN_00ad6718, vtable+0x18` is exactly right.)

So the entire "Join Party clicked → presence read → room descriptor extracted → join
sent" chain resolves to real, verified code, and it terminates in the same `0x130` the
invite-accept path uses.

> **Answer to task 2:** Join Party reads the selected friend's presence via
> `sceNpBasicGetFriendPresenceByNpId`, extracts the room_id from data blob +40, and
> emits a **tag-267 NP message to the host**, not a direct `0x130`. The host answers
> tag-268, and *that* reply drives the joiner's `0x130` through the same
> `FUN_00ad2768 → vtable+0x18 → FUN_00ad6718` sender the invite path uses. It does **not**
> use `sceNpMatching2`.

---

## 3. RPCN presence store/deliver, and where Join Party actually breaks

### RPCN is complete and verbatim  (confidence: HIGH)

`backend/rpcn/src/server/client/cmd_misc.rs::set_presence` (lines 272-322):
- Stores `com_id`, `title`, `status`, `comment`, and **`data` (Vec<u8>, truncated to
  `SCE_NP_BASIC_MAX_PRESENCE_SIZE = 128`)** verbatim in `ClientSharedPresence`.
- On *change* (compares all fields incl. `data`), builds a `FriendPresenceChanged`
  notification: `npid \0` + `presence.dump()` and sends it to **all** friends.
- `ClientSharedPresence::dump` (client.rs:104) writes exactly
  `com_id[12] · title\0 · status\0 · comment\0 · u32_LE(data_len) · data` — the precise
  layout RPCS3's np_handler parses, which is why RPCN was written this way.

Login sync — `cmd_account.rs::login` (lines 139-160): the `dump_usernames_and_status`
closure emits, for every **online** friend, `status=1` + `presence.dump(reply)` (or
`dump_empty` if that friend has no presence yet). So a client that logs in **also
receives each online friend's current presence data at login**, not only on subsequent
change.

Runtime proof it's flowing (`rpcn-run.log`): both accounts repeatedly
`Parsing command SetPresence → Succeeded with NoError`, and `RequestSignalingInfos`
succeeds both directions (`comradesean => 192.168.1.100:3658`,
`mgnomad2 => 192.168.1.121:3658`). Delivery proof (comradesean's RPCS3 log): the game's
own TTY prints **`mgnomad2 has updated presence` 41×** — comradesean's client is
receiving and reacting to mgnomad2's presence-changed events. Presence delivery works
end to end.

> RPCN stores comradesean's blob verbatim and delivers it to mgnomad2 both at login and
> on change. **The presence is not being dropped, emptied, or mangled by the server.**

### So where does it break?  (confidence: MEDIUM — needs the joiner's log to finalize)

Because the `0x130`'s room_id comes from the **268 reply** (host-authoritative), the
presence value is not load-bearing for the join packet — even an empty/zero presence
blob still yields a correct `0x130` *if the handshake completes*. Presence only gates (a)
whether the friend menu offers "Join," and (b) seeds the joiner's 267.

The symptom ("joiner connects to SessionManager but never sends `0x130`") means the
handshake did **not** complete: the joiner got as far as connecting to the SM (client
`hello`, `session_manager_stub.py:721`) but never received a **268**, so it never reached
`FUN_0035b2c8 → 0xad6718`. Ranked causes:

1. **Host does not reply 268 (most likely).** `_opd_FUN_003ca9d0` bails before the 268
   send if `party_obj+0x19f4 == 0` (or the `FUN_00349360/+0x4c` check trips). In the
   working *invite* flow the host **initiated** (clicked Invite), which drives him into
   the "hosting/accepting" state, so `obj+0x19f4` is set and he replies 268 (the log
   shows `Send Message 10c ×15` and two `… joined party`). In a **discovery** join the
   host is passively hosting; if that path doesn't set `obj+0x19f4` the same way, the
   host silently drops the joiner's 267 → joiner stalls after the SM connect. This is a
   **host-side client-state gate**, but it is driven by the room state our SessionManager
   stub establishes at RoomCreate — see §4.
2. **Friend menu never offered "Join," or offered it against stale presence.** If, at the
   instant the joiner opened the menu, comradesean's cached presence had `obj+0x19f4/room_id`
   = 0 (he wasn't hosting a joinable party yet, or a heartbeat overwrote it), the UI
   either wouldn't enable Join, or the 267 carried room_id 0. (The latter still works via
   the 268; the former means no 267 at all.)
3. **RPCS3 HLE round-trip of the `data` field.** RPCN's dump layout is written to match
   RPCS3's parser and this is the standard RPCN presence path, so this is *expected* to
   work — but it was not directly re-verified against build 19598's np_handler this pass
   (WebFetch of `onlinedata_to_presencedetails` was inconclusive). Low risk, listed for
   completeness.

**This is explicitly NOT a "client-internal, unfixable" verdict.** The frontier is a
single, identified host-side state byte (`party_obj+0x19f4`) that gates the 268 reply,
and it is the same byte the host publishes in presence. The next data point settles it
(see §4 diagnostic).

---

## 4. Fix plan

### 4a. What the server already does right (no change needed)
- **RPCN**: stores the 96-byte blob verbatim, delivers at login + on change, in the exact
  format RPCS3 parses. Confirmed working.
- **`session_manager_stub.py`**: already handles `0x130` RoomJoin
  (`elif opcode == 0x130`, line 919) with the cross-connection `active_rooms` registry
  and per-recipient rosters. If the client emits a `0x130`, the stub pairs it — proven by
  the working invite-accept join. **Do not edit the stub for this.**

### 4b. The one diagnostic that closes the root cause (do first — ~2 min)
Capture **the joiner's (mgnomad2's) RPCS3 log** during a real *Join Party* (menu-select
comradesean → Join), and grep the TTY:
```
grep -aE "Send Message 10b|Post Message 10b|Get Message 10c|Post Message 10c|NetMatchmakingRoomJoin" mgnomad2_RPCS3.log
```
- **`Send Message 10b` present** → joiner sent the 267. Then look for **`Get Message 10c`**:
  - *absent* → **host never replied 268** → cause #1 (host `obj+0x19f4` gate). Confirm on
    comradesean's log: no `Send Message 10c` in the window. Fix path 4c.
  - *present but no `NetMatchmakingRoomJoin`* → joiner got 268 but the
    `FUN_0035b2c8 → 0xad2768 → 0xad6718` path bailed (rare; different bug).
- **`Send Message 10b` absent** → joiner never ran `FUN_0035ca28` past the send → cause #2
  (menu didn't offer Join / stale presence). Then dump mgnomad2's cached presence for
  comradesean: breakpoint `0x0035cad8` (right after the blob memcpy) and read the 96 bytes
  at `r1+128`; `+0x28` (offset 40) is the room_id the joiner sees. Zero there ⇒ presence
  didn't carry a live room_id at read-time.

### 4c. If the host is bailing on the 267 (cause #1) — server-side lever
`party_obj+0x19f4` is set by the host's party/room state machine, which our stub drives
via the RoomCreate reply. The lever is to make the host's *solo/passive* hosting state
identical to the *invite-initiated* state. Concretely, in the stub's RoomCreate handler
(the `Member + OwnerChanged(1) + OwnerMember(1)` reply), verify the host is driven into
the full "owner + accepting members" state and that `m_roomSize` / roster are populated
(the `m_roomSize > 0` assert family, `net-session.cpp:227`, is the known symptom of an
under-populated room object; see the invite note). If a live host-state dump shows
`obj+0x19f4 == 0` while passively hosting, add the missing owner/roster field to the
RoomCreate reply so the host reaches the same joinable state it reaches after clicking
Invite. **This is a stub change — propose it in a follow-up; do not edit the running stub
here.** No RPCN change is implied by this path.

### 4d. RPCN robustness (optional, sketch only — not required by the evidence)
RPCN's presence delivery is correct, so **no RPCN patch is proposed**. If §4b shows the
joiner's cache was stale (cause #2 timing), the only RPCN-shaped hardening would be to
ensure a friend coming online re-triggers a presence push for already-online friends —
but login sync (cmd_account.rs:139-160) and change-notify already cover the normal
timeline, so this is speculative. If pursued: it would be a change in
`cmd_account.rs`/`cmd_friend.rs` to (re)send `FriendPresenceChanged` for online friends to
a newly-online user, and would need `cargo build --release` in `backend/rpcn` +
a submodule-pointer bump + a manual rpcn restart. **Not implemented — presence delivery
is not the demonstrated blocker.**

---

## Confidence summary
- Presence blob layout incl. room_id @ +40: **HIGH** (verified SET builder `FUN_00397d74`
  *and* READ path `FUN_0035ca28`, same offset; room_id = `room_obj+0x10`, the known field).
- Join-Party read chain `presence → 267 → 268 → 0x130` and every address in it: **HIGH**
  (each `bl`/vtable slot disassembled; 268→`0xad2768`→vtable+0x18→`0xad6718` traced).
- Matching2 dead: **HIGH** (linked, never called at runtime except Term).
- RPCN store/deliver correct and complete: **HIGH** (source + rpcn-run.log + RPCS3 TTY).
- Exact break point: **MEDIUM** — mechanism is nailed; the specific failing gate
  (host `obj+0x19f4` 268-reply gate vs. stale-presence menu) requires the *joiner's* log
  from a real Join-Party attempt (§4b) to finalize. Not client-internal-unfixable: the
  gate is identified and stub-addressable (§4c).

## Tooling
No new tools. Used `tools/eboot_analysis/{eb,scan_imm,scan_bl,fnstart}.py`, objdump,
and grep over the RPCS3 log + `backend/rpcn/rpcn-run.log`. NID table base for the sceNp
module: `0xe59460` (idx0 off `0x307c`); presence import stub `0xe5750c`
(SetPresenceDetails), read stub `0xe5770c` (GetFriendPresenceByNpId).
