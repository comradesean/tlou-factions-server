# UC2 packet captures: solo-host lobby→match-start needs no extra server round trip (directional evidence, not proof)

Surveyed real Wireshark captures of *Uncharted 2* (PS3, 2009, same dev/console
generation as TLOU) from `ref/packet dumps/Uncharted 2/`, focused on the
solo-host file closest to our stuck scenario. Goal: does a comparable
lobby-ready/team-assignment handshake exist in this protocol family, and if so
what does it look like structurally? **UC2 turns out to use Sony's own NP
Matching2 SDK wire format**, not a Naughty Dog-authored protocol like TLOU's -
so this is *not* a byte-for-byte analog. It's still useful as architectural
precedent.

## What UC2's session traffic actually is

`custom game - host multiplayer match deathmatch - play alone hosting - quit
match - exit.pcapng`: `strings` on the capture shows cleartext hostnames
`lookup-22101.ww.np.matching.playstation.net`,
`session-22111.ww.np.matching.playstation.net`, title ID `NPWR00462_00` - this
is Sony's stock NP Matching2 middleware (room/member/session concepts), not a
custom ND protocol. TCP conversations: port 3478 (52.26.114.252, "matching"),
3479/3480 (52.34.71.144 / 52.37.243.133, "session"/lookup") - these are Sony's
generic matching servers, unrelated to TLOU's bespoke `NetMatchmaking*` opcode
table (`docs/protocol/session_manager_and_matchmaking.md`) or `backend/rpcn`'s
model. Confidence this maps 1:1 onto TLOU's wire bytes: **low**. Confidence it
shows real Naughty Dog netcode *architecture* for this era: **medium-high**
(same dev, same problem, same console).

## The finding: room-setup burst, then silence, then teardown burst

In the solo-host file, all NP-matching traffic (ports 3478/3479/3480) happens
in two short bursts:
- **t=26.0s-28.4s** (frames 41-83): room create/join burst - client sends,
  server replies with a 198-byte then later 240-byte payload containing the
  room's per-member binary attributes (TLV fields `PL`/`PM`/`PS`/`PN`/`PO`/`PP`
  + country code `us` + IP/port-shaped 8-byte and 12-byte blobs - values not
  decoded, out of scope per task brief).
- **t=28.4s → t=533.9s (~505 seconds, the entire "play alone hosting" span)**:
  **zero packets** on ports 3478/3479/3480. Only unrelated keepalives (PSN
  presence heartbeat every ~60s to 174.129.16.161, port-5223 ping every ~40s).
- **t=533.9s onward** (frame 912+): a second matching-server burst, correlating
  with "quit match - exit" - HTTP POSTs to Akamai-style hosts (stat/telemetry
  upload) plus a final 240-byte room-data update.

Cross-checked against `host game - deathmatch - round end - exit to
lobby.pcapng`: identical shape - setup burst at t≈48-64s, **zero** matching-
server traffic until t≈363s (round end), then another 240-byte room-data-
update burst matching the same signature.

## Interpretation

1. For a **solo host**, once the initial room-create burst completes (~2.4s
   after the first packet), the client gets **no further message** from the
   matching server for the rest of the session until it explicitly quits. It
   begins/plays the match with no additional "go"/"ready" round trip visible
   on the wire.
2. State transitions that *do* need a new server exchange (round end, room
   teardown) all show the **same 240-byte "room/member data update" shape**
   echoed both directions - consistent with a `SetRoomDataInternal`/
   `SetRoomMemberDataInternal`-style broadcast pattern, i.e. state changes
   (including presumably ready/team fields) are pushed as a room-data update,
   not a dedicated new opcode.
3. No isolated small message (a few bytes, "flag only") appears anywhere near
   these transitions - every state-change message is bundled into the larger
   (~240-316 byte) room/member-data blob alongside NAT/attribute fields, not a
   standalone ready/team packet.

## Confidence and how to apply

**Confidence: low-medium**, directional only - different wire protocol
(Sony SDK vs. ND-authored), can't be read as TLOU's actual byte layout.

**What it does support**: the working theory that TLOU blocks on a per-member
field inside a broadcast room/member-data message (matches `0x13c`/`0x13d` in
`protos/`) is architecturally consistent with how this same-era ND title used
Sony's equivalent primitive. **What it argues against**: solo-hosting requiring
an *additional* round trip beyond initial room setup - in UC2, solo hosting
needed nothing extra once the room existed. If TLOU's stub already sends a
complete room/member-data broadcast (even with team/ready zeroed) after
room-join, the fix is more likely "the zeroed field itself is wrong" than
"a whole message is missing" - narrows the theory, doesn't confirm the specific
team+ready-flag mechanism.

Not pursued further per task scope: UC4 captures (lower priority, PS4/different
engine era, not checked this pass), and decoding the `PL/PM/PS/PN/PO/PP` TLV
field meanings (would need NP Matching2 SDK docs, separate task).

## Addendum 2026-08-16: UC4 capture checked - found a plaintext ND roster
## protocol, but no small-int team field in it (negative result)

Opened `ref/packet dumps/Uncharted 4/uncharted 4.pcapng` (160MB, PS4, 2016) -
previously skipped. Goal: does the same "small-int team field embedded in a
room/lobby broadcast" pattern show up here too, as corroborating evidence for
TLOU's `0x12f RoomCreate` team-field finding.

### What UC4's session traffic actually is

Unlike UC2 (Sony NP Matching2) or TLOU (bespoke session-manager on 7314), UC4
splits session traffic three ways:
- **TCP 6403/6408 to `54.183.153.197`** ("b4uspsp4"-tagged, Naughty Dog's own
  AWS-hosted backend, not Sony) - a plaintext, custom ND binary protocol. This
  carries NAT/keepalive traffic (`tcp.stream==13`) and, at match start, a
  structured **8-player roster/connect-info broadcast**.
- **TCP 443 to `44.232.123.34`** - TLS, encrypted, unidentified SNI. A large
  packet burst here lines up exactly with match start (t=978-982s in the
  capture) - this is almost certainly where actual matchmaking/room/team
  assignment happens, but it's opaque without keys.
- **UDP 9306** - full-mesh P2P game traffic directly between up to 7 peers
  simultaneously (confirmed via `conv,udp`: 7 distinct peer IPs each with
  ~32k frames / ~1048s duration starting at t≈981s) + the local player = a
  real 8-player match, consistent with UC4's 4v4 competitive modes.

### The plaintext roster message (frame 74503, TCP stream 13, port 6403)

At t=980.98s, right as the P2P mesh spins up, the server pushes a 1448-byte
message (seq/opcode-looking leading field `0x00000131`) containing 8
fixed-168-byte player records back-to-back, each anchored on a null-padded
16-byte username field followed by a `<letter><digit><region><ps4\0>` build
tag (e.g. `b1gbps4`, `d5rups4`, `a7grps4`, `b4usps4` for the local player
`idorocks232`) then ~144 bytes of session ID / port / NAT-looking binary
fields. Usernames recovered in order: `XaMeLyOn`, `Brazzerc`, `Freeman_l-_-l_`,
`Soffochka_l-_-l_`, `slon2207`, `OUTSIDER_6115`, `Sfigas10`, `idorocks232`
(self) - 8 names, matching the 8-way P2P mesh above.

Did a byte-by-byte diff of all 168-byte records (brute-force, same method
that found TLOU's team field) looking for any offset with only 2-3 distinct
small-int values. One candidate stood out: **relative offset 0x30**, values
`{1,3,1,3,1,1,1}` across the 7 fully-captured records (Brazzerc and
Soffochka_l = 3, the other five = 1). This is the closest thing to a
TLOU-style small-int field found in the capture - but it's a **2-vs-5 split**,
not a clean partition matching an 8-player 4v4 roster, and Brazzerc's record
also has an anomalous internal shift (a stray literal `ps4\0` appears where
other records have IP/port bytes), suggesting this field tracks per-player
**connection/NAT state** (e.g. direct-P2P-established vs. still-relayed).
No other offset in the 168-byte record showed a value set of size 2-3 that
split the roster evenly. Full per-offset diff is not preserved (ad hoc
Python in scratchpad, not checked in) - re-derivable from the same capture
and method if needed.

### Confidence and interpretation

**Confidence: low** that this rules anything in or out. What was checked and
found *negative*: the one plaintext, structured, per-player broadcast message
this capture exposes near match-start does **not** contain an obvious 8-way
team-partitioning small-int field. What wasn't checked (out of scope per task
brief): the TLS-encrypted `44.232.123.34:443` channel, which correlates far
more tightly with match-start timing and is the more likely home for actual
team/room assignment - inaccessible without a key log this capture doesn't
provide.

**Net effect on the "is this a deliberate ND design pattern" question**: this
pass neither confirms nor refutes it. It does newly establish that ND ships
a bespoke plaintext binary protocol for *out-of-band NAT/roster* purposes in
UC4 (architecturally a bit like TLOU's approach of rolling their own wire
format instead of Sony's), but the specific "team is a 1-2 byte int inside a
room broadcast" pattern wasn't found in the part of that protocol examined
here. Would need the TLS keys (or a different capture with visibility into
`44.232.123.34:443`) to actually check the more likely candidate channel.
