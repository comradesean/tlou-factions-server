# Send-buffer residue: statistical proof, and the field corrections that follow

Source: `server/logs/wire.jsonl`, 5880 tapped events from a full multi-client
day (solo host, 2-player matchmade games, 3-player join-in-progress), plus the
PPU thread dump in a client-side RPCS3 log.

## 1. The "uninitialised stack" gap fields are leaked POINTERS

Several schemas describe a gap field as "never written by the sender -
uninitialised stack" (`0x12f` pad_4, `0x130` pad_4, `0x133` pad_4, `0x135`
pad_4, `0x142` pad_6, `0x13e` pad_6, `0x143` pad_4). That description was
derived from store-enumeration of each builder. The capture now proves it
independently, and says what the leaked bytes actually are.

Taking the 4:8 word of `0x12f` / `0x130` / `0x133` / `0x135` across 1052
samples and classifying each value by memory region:

| region | samples | share |
|---|---|---|
| main-thread stack `0xd0001000-0xd0040fff` | 736 | 70.0% |
| EBOOT code/data | 149 | 14.2% |
| zero | 93 | 8.8% |
| globals / heap `0x0e00000-0x2000000` | 63 | 6.0% |
| not a valid address | 11 | 1.0% |

**99% of the values are valid PS3 addresses.** The stack bounds are not assumed:
a PPU thread dump in the client RPCS3 log states `Stack: 0xd0001000..0xd0040fff`
for the game's main thread, which is the thread that builds every one of these
messages. Individual values corroborate it further - the most common globals-
region value is `0x013835c0`, which is `g_70` / NetInfo, a pointer the same code
paths hold live.

Most frequent values: `0xd00401a0` (x523), `0x0039b4f0` (x149), `0xd0040280`
(x129), `0xd00401e0` (x79), `0x012723d8` (x28), `0x013835c0` (x25).

### Why this matters for reading captures

A leaked pointer is **perfectly reproducible** on a deterministic emulator: the
same call path, at the same stack depth, leaves the same address in the same
slot, on every boot and on every machine running the same build. Reproducibility
across sessions and across days therefore does NOT distinguish a real field from
residue, and must never again be used as the argument that a gap byte is
meaningful. The discriminators that DO work:

1. Does any store in the builder write that offset? (decisive)
2. Is the value a plausible address for this title's memory map? (strong)
3. Does the value vary with the thing it would have to mean - the room, the
   host, the map, the mode? (strong when it does not)

## 2. CORRECTION - `0x140` attr_value (offset 6:8) is residue, not a field

A 2026-08-18 revision promoted `0x140` 6:8 from "uninitialised" to a real
client-to-server attribute value, on the grounds that its values recurred across
captures taken on different days. Per §1 that argument does not hold, and the
larger capture refutes the conclusion outright:

- **Room-independent.** The same values appear against the static party room
  `012723d8...`, and against ~25 distinct synthesized public room ids
  (`50000001...` through `50000030...`). An attribute of a room that is
  identical for every room ever created is not an attribute of the room.
- **Call-site determined, not setting determined.** Value `fbe0` follows a prior
  `0x140` in 28/28 cases; value `197c` follows a `0x13a` in 4/4 cases. The
  three-value cycle `ff50 -> fbe0 -> 2f78` repeats per lobby regardless of any
  host choice.
- **Distribution matches residue.** Only five distinct values across 355 frames,
  all 16-byte-aligned-looking low halves, in a message whose builder
  (`FUN_00ad62dc`) writes wire 0 (`stw`), wire 4:6 (`sth`) and wire 8:16 (`std`)
  and nothing else. The `sth` at 4:6 clobbers the high half of whatever pointer
  was in the slot, which is exactly why only a low half is ever visible.

Classification returns to sender-side residue. The retail server cannot have
consumed it.

## 3. `0x13e` flag byte is not boolean on the wire

`0x13e`'s offset 4 is documented as "a single boolean-shaped byte (0 or 1)".
Across 117 live frames the observed (flag, kind) byte pairs are:

| flag (4:5) | kind (5:6) | count |
|---|---|---|
| 0x04 | 4 | 40 |
| 0x00 | 3 | 35 |
| 0x03 | 3 | 35 |
| 0x00 | 4 | 4 |
| 0x01 | 3 | 2 |
| 0x03 | 4 | 1 |

`kind` is 3 or 4 in 117/117 frames, confirming the discriminator. `flag`,
however, takes 0, 1, 3 and 4 - and in the two most common shapes it is **equal to
the kind byte of the frame**, which is the signature of a stale byte left by the
previous `0x13e` build in the same buffer slot rather than a freshly written
boolean. Treat offset 4 as "boolean when written, stale kind byte otherwise";
only 0 and 1 are meaningful values.

## 4. `field_0c` is team-independent - the map-vs-team confound is dead

`0x12f` `room_field_0c` and `0x135` `field_0c` (both `*(u32*)(obj+0x0c)`) carried
an unresolved caveat: an earlier controlled test saw values 0x09/0x13 track TEAM
with the map held constant, so "map id" could not be separated from "map+team
combined index". A 2x2 capture was listed as the way to settle it.

126 live RoomCreate frames settle it without one. Pairing `field_0c` against the
team u16 at wire 0xb0:

| field_0c | teams it occurs with | counts |
|---|---|---|
| 0x00000002 | 0 | 92 |
| 0x00000009 | 0, 1 | 2, 9 |
| 0x00000012 | 1 | 4 |
| 0x00000013 | **0, 1, 2** | 1, 15, 3 |

`0x13` spans the COMPLETE team domain - the team byte takes only 0, 1 and 2, and
a single `field_0c` value occurs with every one of them. If `field_0c` encoded
team in any bit, a fixed `field_0c` would force a fixed team; instead one value
covers every team there is. `field_0c` carries no team component. (What it DOES
carry is narrowed further in 4b below - it is not a map id either.)

### 4b. It is not a map id either - it splits by ROOM OBJECT

**[SUPERSEDED - see 4d. The "zero crossover" below did not hold.]**

131 live RoomCreate frames, zero crossover at the time of writing:

| field_0c | room object | count |
|---|---|---|
| 0x12 | PARTY room (`0x01387f58`) | 6 |
| 0x02 | GAME room (`0x01383bd8`) | 92 |
| 0x09 | GAME room | 12 |
| 0x13 | GAME room | 21 |

A party lobby has no map, so a value constant across every party room and absent
from every game room cannot be a map identifier. `obj+0x0c` is better read as a
ROOM CONTEXT / MODE descriptor of whichever room object is being created: the
party object carries a constant 0x12; game rooms carry 0x02 matchmade and
0x09/0x13 on custom games.

LEAD: a friend-card presence capture during a live custom game read
"Checkpoint / SUPPLY RAID". Factions custom games are mode-selectable, so
0x09/0x13 plausibly encode MODE rather than map - which would also explain the
2026-08-16 confound where they appeared to track TEAM with map held constant,
since mode and faction are set on the same lobby screen. Unresolved: the
historically logged 0x5a (90) and 0x63 (99) are too many for a two-mode reading.

### 4c. Matchmade path - the SEARCH field is the game mode

(Section 4b's "disjoint by room class, zero crossover" claim is RETRACTED in 4d
below. Read 4d before relying on anything here.)

`field_0c` looked invariant at `0x02` (411/411 searches) only because every
capture until then was of a single playlist. A second playlist produced `0x03`:

| | `0x02` | `0x03` |
|---|---|---|
| `0x135` FindMatch | 554 | 11 |
| `0x12f` RoomCreate (PUBLIC) | 94 | 2 |

The searcher ASKS for a mode in `0x135`. (The "and the elected host STAMPS it on
the room it creates" half of this claim is RETRACTED - see 4d.) `0x02` = Supply
Raid, `0x03` = Survivors, read off the live client
UI. This is the matchmaking filter, and the stub currently IGNORES it - it
returns every public room regardless of mode. Harmless while one playlist is in
use; wrong the moment two are.

The PRIVATE pair (`0x09`/`0x13`) remains open: either the same two modes in a
private encoding, or a different quantity (in a private match you choose the
MAP, whereas find-match votes it). The latter fits the historical `0x5a`/`0x63`.
Deciding test: two private matches differing ONLY in mode, then ONLY in map.

## 5. `0x142` HostRank - live entry data

Consistent with the decompiled collector (`FUN_0039b720`, per-player rank values
from the NetGameManager player array):

- Find-match path: `count = 1`, single entry `0x0002`, in 138/138 frames.
- Custom-game path: `count = 0`, empty list, in 27/27 frames.

The single entry value `0x0002` is from unranked accounts; the count difference
follows the player-array state filter at send time, not the room type as such.
The `6:8` gap is residue like everything else in §1 (`d740`, `fe30`, `00e0`).

## 6. `0x143` - do not mine the bytes after the NUL

`data_block` is a 128-byte field filled by a bare two-argument `strcpy`, so
everything after the terminator is whatever the send buffer already held. In 15
live frames the leading string is `<npid>.<unix-timestamp>` with the timestamp
equal to the send time and the npid equal to the room owner, exactly as
specified.

The trailing bytes are residue and contain recognisable pointers
(`0xd0040140`, `0xd00401b0`, `0xd00401e0` stack; `0x0137d700`, the
NetGameManager player-array base; `0x0039e96c`, `0x0039ac24` code;
`0x01383bd8` room object). Two of those residue words correlate perfectly with
room membership across all 15 frames (`+0x48` is 0 for a 1-member room and 2 for
a 2-member room; `+0x6c` is 0 and 1 respectively). That correlation describes
what the sender happened to have on its stack, NOT a wire field, and must not be
promoted to one - it is the §1 trap in miniature.

## 7. `0x146` checksum - one value per machine

53 frames carry exactly 3 distinct payloads (`18ac7ad2` x32, `ce2f229b` x13,
`e3508434` x8) across 3 client machines - one stable value each, unchanged over
many reconnects. Consistent with the session-derived checksum reading rather
than a per-connection nonce.

## 8. Full .ksy review pass (2026-08-18, all 44 specs)

Method: mechanical audit first (declared layout vs framed capture via
`research/tools/verify_wire.py`, field census, padding watch, YAML validity),
then targeted reads of whatever the audit flagged. Every framed message still
parses clean against its spec and no opcode is unmodelled on port 7314.

### 8a. NEW SERVICE - `report-server` (was entirely undocumented)

Mining the service name out of all 452 captured sibling hellos gives six
distinct services, not five:

| service | hellos |
|---|---|
| heartbeat-server | 258 |
| facebook-server | 72 |
| ticket-server | 62 |
| leaderboard-server | 58 |
| report-server | **2** |
| single-player-server | (spec exists, none this capture) |

`report-server` had no spec. Its request line is live-captured and decrypts to
`is-banned comradesean\n` - a player-standing / ban check. Modelled now in
`protos/0x11_report_line.ksy`; the RESPONSE grammar is unobserved and is
deliberately NOT guessed there.

IMPLEMENTATION RISK: `server/ticket_server.py` branches only on
leaderboard-server and facebook-server, so report-server falls through to the
generic ticket path and a ban check is answered with a ticket_submit_response
frame. That is the same mismatch class that caused the leaderboard "Error 9 /
disconnected from game servers" boot and the Facebook retry spin. It gates
online entry, so it deserves a real handler once the reply grammar is known.

### 8b. `leaked_stack_garbage` renamed to `pad_08`, and it leaks TEXT

The 16-byte gap at offset 8:24 of every sibling hello violated the repo's
pad_<off> naming convention. Renamed across all five hello specs (each still
totals 88 bytes, field order unchanged).

Classifying all 452 captures per 4-byte word confirms residue - mostly zero,
plus stack addresses (`0xd00f7880` x60), globals (`0x01383708` x34) and a
seconds-since-boot-shaped float (`0x430acd88` = 138.80, x44). But 38 hellos
carry ASCII: 36 hold the contiguous URL slice `"outube/accounts/"` and 2 hold
the JSON slice `'Roberts", "id": '`. So this gap can disclose account
identifiers and real names from the client's web-stack buffers to whatever
server it connects to - a genuine privacy leak in the retail client, and the
strongest single illustration of why these gaps matter.

### 8c. `member_data.rank_value` is live-nonzero - encoding confirmed end to end

The census shows 0x0000, 0x0001 AND 0x0002, superseding "zero for the two
UNRANKED test accounts". With journeys = 0 the producer formula reduces to
`weeks_survived = matches/7`, and a 0 -> 1 -> 2 progression with no jump to the
1000s is exactly that. The encoding is now confirmed from producer arithmetic
all the way to the wire; a ranked account is wanted only to exercise the
`journeys*1000` term.

### 8d. NEGATIVE RESULT - `0x142` entries are NOT `member_data.rank_value`

A tempting coincidence (both read 0x0002 in some frames) that does not hold: in
115 frames where the sender's own card is observable, the `0x142` entry is a
CONSTANT 0x0002 while `rank_value` reads 0x0001 (x80) or 0x0002 (x35).
Different producers, different quantities. Recorded in both specs so it is not
re-derived.

### 8e. Relay guidance added to `member_data.pad_16`

The census shows this span decomposing as u16 + zero u32 + pointer
(`0001 00000000 0137d700` x264 in one roster slot alone - the player-array
base), consistent with the existing producer-never-written proof. Its bare
"send zero" guidance was however wrong for a RELAY: a server forwarding a
member's card (0x131 rosters, 0x13b updates) must replay the client's own 32
bytes verbatim, residue included, because the same struct carries party_id,
team, recent_level and rank_value. Zeroing applies only to a synthesized card.

### 8f. Clean on re-check

`0x13a.tail`, `0x135.locale`, `0x133.pad_4`, `0x130.pad_4` and the `0x12f`
gap fields all match the capture exactly as documented. The only remaining uses
of a from-recurrence argument are the two corrected 0x140/0x141 passages and
`0x146`, where "reproducible from the session_seed" is a disassembly-backed
statement about a real checksum, not an inference from recurrence.


### 4d. RETRACTION - two claims in 4b/4c were wrong

Both were made and refuted the same day. Recording them because the error mode
is instructive, not just the conclusion.

**Retracted 1: "the searcher asks for a mode in 0x135 and the elected host
stamps it on the room."** Live counter-example: at 23:18:35 a client sent 0x135
with `field_0c=0x02`; 14 seconds later its own RoomCreate carried
`field_0c=0x13`, on a room the server registered PUBLIC/matchmade. Same client,
different values.

**Retracted 2: "the value ranges are disjoint by room class, zero crossover."**
The same frame puts `0x13` on a PUBLIC room; it also occurs 21 times on PRIVATE
ones. Updated distribution over 138 RoomCreate frames:

| field_0c | PUBLIC | PRIVATE | PARTY |
|---|---|---|---|
| 0x02 | 94 | - | - |
| 0x03 | 2 | - | - |
| 0x09 | - | 12 | - |
| 0x12 | - | - | 6 |
| 0x13 | **1** | 21 | - |

**The error:** `0x135`'s `field_0c` and `0x12f`'s `room_field_0c` are the same
struct OFFSET (+0x0c) but of DIFFERENT OBJECTS - `search_obj` versus `room_obj`.
Treating "same offset" as "same quantity" was an inference stated as a fact, and
the 94/94 agreement that appeared to confirm it was a correlation produced by
both being set during the same normal flow.

**What survives:** the SEARCH field (`0x135`) tracking the playlist is still
well supported - `0x02`/`0x03` across 565 searches, matching the client UI.
Only the room field is in doubt.

**Current reading of the room field (provisional):** a genuine room-object
member that nothing reliably resets, so a room created from a dirty client
state inherits a stale value. The single crossover frame came from a client
that had just been booted mid-match and reconnected, and the value it carried
(`0x13`) is in the same id space as the recent-level MAP ring - and that client
had just played a map. For private matches nothing in matchmaking reads the
field at all, so nothing forces it to be meaningful there.

**Server guidance:** filter the `0x136` game list on the SEARCHER's `0x135`
field, never on the host's `room_field_0c`; a stale value would otherwise make
a legitimate room unjoinable.
