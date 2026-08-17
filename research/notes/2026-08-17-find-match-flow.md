# Find Match (public matchmaking): the real search → list → join/host flow

**Scope:** the client-side "Find Match" state machine in `net-matchmaking.cpp`
and the SessionManager (`NetMatchmaking*`, port 7314) wire messages it drives.
Traced instruction-level this pass; every EBOOT address below was read off the
decompile/disasm, not guessed. Companion to
`docs/protocol/session_manager_and_matchmaking.md` and the two-player-party note.

**Headline:** the current stub answers the `0x135` find-match broadcast by
pushing room-membership (`Member 0x131` + `OwnerChanged 0x13f`). That is the
**wrong protocol layer** for this point in the flow, which is exactly why the
client parks in `NET_SM_CLIENT_GAME_LIST_WAIT` and never advances: that state is
waiting for a **game list** (`RoomSearch 0x136`, server→client), not room
membership. `Member`/`OwnerChanged` are not in the set of messages
`GAME_LIST_WAIT` consumes, so the client ignores them and keeps waiting.

The correct sequence is **`0x135` (client search request) → `0x136` (server
pushes the game list) → client picks an entry → `0x130 RoomJoin` (join it) OR,
if the list is empty, the client is designated host and creates via `RoomCreate
0x12f`**. All four legs are confirmed below.

---

## Why this is on the metagame critical path (2026-08-17 coordinator update)

A sibling agent proved the "match counts" progression latch (`g_70[0x6C]`, which
gates supplies/rank/journeys/wins) arms ONLY for a **counted = matchmade / public
playlist** game that reaches a normal end; **custom / private games never arm it**
(shipped design). Invite-to-Party yields a CUSTOM game, so it can never credit
progression. **Find Match (public matchmaking) is therefore the ONLY path to a
counted game** — so the "create-if-none" host this note specs MUST be a
matchmade/public game (the `net-matchmaking.cpp` matchmaking states), NOT the
custom-game host flow (`NET_SM_CUSTOM_GAME_HOST_WAIT_INFO`). §3/§4 below now pin
exactly what separates the two and how the server keeps a lone-searcher host on
the counted path.

## Confidence summary

| Claim | Confidence |
|---|---|
| `GAME_LIST_WAIT` advances on `search_obj+0xa4` going nonzero, which ONLY the inbound `0x136` handler sets | **High** (decompiled both sides: `FUN_00ad0f60`, `FUN_00ad7604`'s 0x136 case) |
| The search REQUEST on the wire is `0x135` (36 bytes), sent by SessionManager vtable+0x14 (`FUN_00ad6c70`); server must PUSH `0x136` back | **High** (sender decompiled; matches captured 36-byte packet byte-for-byte) |
| The game list is `0x136` = 16-byte header + N×56-byte entries; header offset 8 must echo the client's search-object pointer | **High** (0x136 receive-dispatch decompiled) |
| Join path = `0x130 RoomJoin` (88 bytes), vtable+0x18 (`FUN_00ad6718`) | **High** (sender decompiled, 0x58-byte send confirmed) |
| Per-entry 56-byte wire→struct field mapping (the byte shuffle) | **High** on which bytes move where; **Low** on per-field *semantics* (room_id at [0:8] is solid; the rest inferred) |
| `IsHost()` = one byte at `g_matchSession+0x5c`; set by the matchmaking SM's own host-election (`FUN_003b3318`), not by a wire "you are host" message | **High** (`FUN_003abe70`/`FUN_003abe78`/`FUN_003b8168` decompiled) |
| A lone searcher self-elects host and hosts a PUBLIC/matchmade game via the matchmaking states (`FUN_003b7d70` → RoomCreate `0x12f` → CREATE_GAME_WAIT/SERVER_LOBBY), distinct from the custom flow | **High** on the code path; **Medium** on precisely which `FUN_003b3318` branch fires when (retry-exhaustion vs count-match) |
| The public-vs-custom distinction is the ENTRY path (matchmaking vs custom state sequence), marked by `g_matchSession+0x7c=1` set only at START_MATCHMAKING | **High** the paths are separate; **Medium** that `+0x7c` is specifically the flag the `g_70[0x6C]` latch keys on (not cross-referenced to the sibling's arming site) |
| Server keeps the host public by replying empty `0x136` (never routes it to custom) + registering the room in the pool; discriminate public hosts by "this conn already sent `0x135`" | **Medium-High** (mechanism follows directly from the decompiled election; the exact `0x12f` "public" attribute byte is unconfirmed, hence the `0x135`-precedence heuristic) |

---

## 1. What `GAME_LIST_WAIT` consumes, and the exact request/response

### The game-layer state machine (net-matchmaking.cpp)

State-name strings (via `FindStringsMatching`):

| state | string VMA |
|---|---|
| `NET_SM_START_MATCHMAKING` | `0x00e799e8` |
| `NET_SM_CLIENT_START` | `0x00e7d538` |
| `NET_SM_CLIENT_GAME_LIST_WAIT` | `0x00e7d578` |
| `NET_SM_CLIENT_GAME_LIST_PICK` | `0x00e7d3b8` |
| `NET_SM_CLIENT_JOIN_GAME_WAIT` | `0x00e7ac40` |

Handlers were identified by dataflow (not by the numeric state code — see the
"state-code caveat" at the end). The debug logger `_opd_FUN_00e46460(fmt, file,
LINE, name_str)` embeds the `net-matchmaking.cpp` line number as its 3rd arg, so
each handler's transitions are self-labelling:

- **`NET_SM_CLIENT_START` handler = `_opd_FUN_003b5ff4`.** Builds/sends the
  search request through the SessionManager object's **vtable+0x14**
  (`(*(code*)*(*obj+0x14))(obj, …)`), then logs `GOTO NET_SM_CLIENT_GAME_LIST_WAIT`
  at **line 0x35c = 860** (matches the brief) and sets the next state; the
  failure branch logs line 0x356 = 854 and jumps to an error state (calls
  `_opd_FUN_003b3ad0(1)` + the `_opd_FUN_00338678` error dialog).
- **`NET_SM_CLIENT_GAME_LIST_WAIT` handler = `_opd_FUN_003b4bf4`.** This is the
  poll loop. It reads the search status via `_opd_FUN_00ad0f60(session)`:
  - `== 1` → still searching: check a timeout (`_opd_FUN_00347188`); on timeout,
    error state 0x13 + `_opd_FUN_003b3ad0(1)`; otherwise **stay put** (no state
    change — no timeout means it waits forever, exactly the observed park).
  - `!= 1` (search done) → read the result count via
    `_opd_FUN_00ad2594(session)`, zero a UI array of that many entries, and
    `GOTO NET_SM_CLIENT_GAME_LIST_PICK`.

### What actually flips the status — the SessionManager side

`_opd_FUN_00ad0f60` (status getter) and `_opd_FUN_00ad2594` (count getter) both
read the client's **search object**:

```c
int FUN_00ad0f60(search_obj){            // status
  int r = 1;                              // 1 = "still searching"
  if (*(char*)(search_obj + 0xa4) != 0)   // done-flag
      r = 2 - (~*(uint*)(search_obj+0xa8) >> 31);  // 2 = success (a4 set, a8>=0)
  return r;
}
int FUN_00ad2594(search_obj){            // count
  int p = search_obj + 0x200;             // &count
  if (*(char*)(search_obj+0xa4)==0 || *(int*)(search_obj+0xa8)<0) p = 0;
  return p;                               // pointer to the +0x200 count field
}
```

The search request sender **`_opd_FUN_00ad6c70` (vtable+0x14)** *clears* those
fields before sending, so `GAME_LIST_WAIT` starts from "searching":

```c
undefined8 FUN_00ad6c70(this, search_obj, arg3, want_region){
  *(uint*)(search_obj + 0x200) = 0;       // count = 0
  FUN_00acb6bc(...);                       // header build
  if (want_region){ sceNpManagerGetMyLanguages(...);
                    sceNpManagerGetAccountRegion(...); }   // "us"
  FUN_00ad57e0(payload);                   // 36-byte body byteswap-noop pass
  FUN_00acb93c(this + 0x25060, payload, 0x24, 1);  // SEND 36 bytes on the control conn
  *(byte*)(search_obj + 0xa4) = 0;         // done-flag = 0
  *(uint*)(search_obj + 0xa8) = 0;
  return 0;
}
```

**The ONLY writer of `search_obj+0xa4 = 1` / `+0x200 = count` / `+0x208[] =
entries` is the inbound `0x136` case of the receive-dispatch loop
`FUN_00ad7604`** (`research/ghidra/sessmgr_vtable_dump.txt:337-425`):

```c
else if (opcode == 0x136){
  min = (buffered > 0xf) ? num_entries*0x38 + 0x10 : 0x10;
  if (min <= buffered){
     search_obj = *(int*)(this+0x24060);   // <-- WIRE OFFSET 8, used as a raw pointer
     *(uint*)(search_obj+0xa8) = 0;
     *(byte*)(search_obj+0xa4) = 1;         // <-- flips GAME_LIST_WAIT out of "searching"
     for (i=0; i < num_entries; i++){       // copy each 56-byte wire entry (shuffled)
        ... dest = search_obj+0x208 + i*0x38 ...
        *(int*)(search_obj+0x200) += 1;      // running count
     }
  }
}
```

**Conclusion (high confidence):** `GAME_LIST_WAIT` is waiting for a
server-pushed **`RoomSearch (0x136)`** message. The client does NOT send a
`0x136` request — the request it sends is the **`0x135`** broadcast (via
vtable+0x14), and the server must reply/push `0x136` carrying the list. There is
no client-sent `0x136` anywhere in the find-match captures; the "0x136
bidirectional / client-sent" line in `protos/0x136_room_search.ksy` is not
exercised on this path and appears to conflate a different builder. **`0x137`
RoomSearchInfo / `0x138` RoomSearchResult are a separate per-room info echo
(client sends a room_id, server echoes it) and are NOT the game list** — the
list is `0x136`.

### The request: `0x135` (36 bytes) — confirmed layout

Live capture (`captures/tcp_catch.log`), one real client in Find Match:

```
00 00 01 35  d0 04 01 a0  01 38 3b d8  00 00 00 02   | opcode | ? | SEARCH_OBJ_PTR | 2
10 2c 50 3f  03 e8 03 e8  00 05 00 00  00 00 00 00   | ? | 1000 | 1000 | 5 | ...
75 73 00 01                                           | "us" | 0x0001
```

`FUN_00ad57e0` walks this exact shape (five u32 at 0,4,8,12,16; six u16 at
0x14,0x16,0x18,0x1a,0x1c,0x1e; one u32 at 0x20), all through the no-op
byteswap helpers (plain big-endian, per the established convention).

| off | sz | field | note |
|---|---|---|---|
| 0 | 4 | opcode `0x135` | |
| 4 | 4 | unknown (`d0 04 01 a0`) | pointer-shaped, not read by server |
| **8** | **4** | **search-object pointer** = `0x01383bd8` | **the server MUST echo this into the `0x136` reply's offset 8** |
| 0xc | 4 | `0x00000002` | search type/version (const) |
| 0x10 | 4 | unknown (`10 2c 50 3f`) | |
| 0x14 | 2×3 | filters: `0x3e8, 0x3e8, 0x0005` | matchmaking criteria (skill/mode-ish) |
| 0x1a | 2×3 | `0,0,0` | more criteria |
| 0x20 | 4 | region `"us"` + `0x0001` | from `sceNpManagerGetAccountRegion` |

The search object at `0x01383bd8` is the same `GAME_ROOM_PTR` global already
known to this project; it doubles as the search-results holder (done-flag
`+0xa4`, count `+0x200`, entry array `+0x208`).

### The response: `0x136` game list — required layout

```
off 0   u32   opcode = 0x136
off 4   u32   0  (not read by the handler)
off 8   u32   search-object pointer  ==  echo of the 0x135 offset-8 value (0x01383bd8)
off 12  u32   num_entries
off 16  ...   num_entries × 56 (0x38) bytes, wire/source layout below
```

Handler gate: it only proceeds once `buffered >= num_entries*0x38 + 0x10`, so
the whole message must arrive as one write of exactly `16 + num_entries*56`
bytes. **Offset 8 is dereferenced and written to** (`+0xa4`, `+0x208`), so it
MUST be the client's real search object — echoing the value the client sent in
its own `0x135` at offset 8 is correct and safe (it is one of the client's own
static globals). Sending a bogus pointer there will corrupt client memory.

### Per-entry 56-byte wire layout (from the copy shuffle)

The handler copies each 56-byte **wire (source)** entry into a 56-byte
**struct (dest)** entry at `search_obj+0x208`, reordering bytes. Source→dest map
(source offsets are what the server must fill; dest is internal):

| dest | source | width | likely meaning |
|---|---|---|---|
| [0:8] | [0:8] | 8 | **room_id** (the 8-byte join key) — **high conf** |
| [8:0x2c] | [0x14:0x38] | 36 | straight copy — host NpId / room name / attributes |
| [0x2c] | [0xc:0xe] | u16→u32 | a count (player count or similar) |
| [0x34] | [0x10:0x12] | u16→u32 | a second count (max players?) |

Source bytes `[8:0xc]`, `[0xe:0x10]`, `[0x12:0x14]` are **not copied** (padding/
ignored). Per-field semantics inside the 36-byte straight-copied block are
**unconfirmed** — that block is where a public/private/open flag and the map/mode
identifiers live (see §4). For a first cut, room_id at `[0:8]` is the only field
the join path strictly needs.

---

## 2. The JOIN path — `0x130 RoomJoin` (already handled by the stub)

`NET_SM_CLIENT_GAME_LIST_PICK` handler = `_opd_FUN_003b6404`:

```c
if (!aborting){
   FUN_003c8f20(0x101, &sel, 0);           // find a selectable game-list entry
   iVar4 = FUN_003c8f20(...);
   if (iVar4 == 0){                          // a game is selectable
      FUN_003c9228(sel, ..., entry, &rid);   // decode entry, rid = its room_id
      if (rid == *(session+0x98))            // sanity: room_id matches
          FUN_003b2f40(entry);               // JOIN it
   } else { ...empty-list branch... }        // see §3
}
```

The join helper `_opd_FUN_003b2f40(entry)`:

```c
if (*entry == 0 || debugSkip) { FUN_003b25c8(); return; }   // re-pick / loop
FUN_003ca3fc();
FUN_0039b4b0(session);
ret = (*(code*)*(*session_join_obj + 0x18))(session_join_obj, state, *(session+0x98));  // vtable+0x18
if (ret >= 0 && ok){
   flag = entry[0x30];                       // per-entry flag
   FUN_00ad11fc(session, flag ? 1 : 0);       // session vtable+0x2c(this, flag)
   GOTO NET_SM_CLIENT_JOIN_GAME_WAIT;         // line 0x56e = 1390
}
```

vtable+0x18 = **`_opd_FUN_00ad6718`**, which sends an **88-byte (0x58)** payload
on the control connection — i.e. **`0x130 RoomJoin`**, confirmed:

```c
FUN_00ad6718(this, room_obj){
  // walk the 4 room slots (stride 0x9000, field +0x50) for the one == room_obj
  ... FUN_00ad5580(buf88); FUN_00acb93c(this+0x25060, buf88, 0x58, 1);  // 0x130 send
}
```

**This is the SAME `0x130` the party-invite-accept path already exercises** —
the stub's existing `0x130` handler (cross-connection `active_rooms` registry)
covers it. The joiner transitions `GAME_LIST_PICK → JOIN_GAME_WAIT` on a
non-negative `0x130` send and then into the lobby once the roster
(`Member 0x131`) arrives — exactly what the stub's `0x130` handler already
pushes. `entry[0x30]` (a per-entry flag) is fed to session vtable+0x2c on join;
its meaning is unconfirmed (candidate: ranked/open vs. something).

**What makes the client pick an entry:** the UI list is a game-layer container of
0x34 (52)-byte descriptors (`FUN_003c8f20`/`FUN_003c9228` iterate stride 0x34),
built from the SessionManager's 56-byte `+0x208` results. `FUN_003c8f20(0x101,…)`
looks up the currently-highlighted/first eligible descriptor by a key; a
non-empty list yields a selection, an empty list returns `0xffffffff`.

---

## 3. The CREATE / HOST path — a PUBLIC / matchmade host (no game found)

This is the metagame-critical leg: the host a lone searcher becomes must be a
**matchmade/public** game (so `g_70[0x6C]` can arm), NOT a custom game.

### The whole find-match flow starts at START_MATCHMAKING, which elects host or client

`NET_SM_START_MATCHMAKING` handler = **`_opd_FUN_003b8168`**:

```c
FUN_003abe9c(g_matchSession, 1);          // g_matchSession+0x7c = 1  ("matchmaking active" marker)
host = FUN_003b3318();                      // ELECT host vs client (see below)
FUN_003abe78(g_matchSession, host);         // g_matchSession+0x5c = host   (IsHost() byte)
if (FUN_003abe70(g_matchSession) != 0)      // IsHost()?
     FUN_003b7d70();                         //   YES -> PUBLIC host setup (RoomCreate)
else GOTO NET_SM_CLIENT_START;               //   NO  -> search (send 0x135), line 749
```

`IsHost()` is literally `return *(byte*)(g_matchSession + 0x5c)`
(`_opd_FUN_003abe70`); its only setter is `_opd_FUN_003abe78`
(`+0x5c = val`). **There is no inbound wire message that sets host** — the
matchmaking state machine self-elects.

### The host election (`_opd_FUN_003b3318`)

```c
if (FUN_00ad1024(sm_conn) == FUN_0039f218())   return 1;   // matchmaking count == expected -> HOST
if (g_matchSession+0x374 != 0) {                            // (a matchmaking-mode gate)
   ... config bits at (*-0x7ff8)+0x848 & 1 -> HOST, & 2 -> CLIENT ...
   if (retry_limit <= *(-0x7f30))               return 1;   // search RETRIES EXHAUSTED -> HOST
   if (!IsHost()) return <random tiebreak>;                 // else coin-flip
}
return 0;                                                    // CLIENT
```

- `FUN_00ad1024` = a matchmaking population count read off the SessionManager
  control connection (`+0x10` room-id / per-slot `+0x748` flags); `FUN_0039f218`
  = the configured expected count (`sessionCfg+0x18`).
- `*(-0x7f30)` is the search-attempt counter that the retry handler
  (`FUN_003b5e9c`) increments every time a search comes back empty.

**Net effect:** a searcher who keeps getting empty game lists eventually trips
`retry_limit <= attempts` and is elected HOST on a subsequent START_MATCHMAKING
pass. (The `count == expected` and random branches are the same "the matchmaking
layer designated exactly one host" idea; on Sony's real service the backend
biased these — for us the retry-exhaustion branch is the reliable, server-drivable
one.)

### The host setup routes through the matchmaking states, not custom

`IsHost()==1` → **`_opd_FUN_003b7d70`**, which calls SessionManager
**vtable+0x10 = `FUN_00ad5b78` = `RoomCreate` (`0x12f`)**:

```c
sm = **(-0x7f44);
create = *(*sm + 0x10);                    // vtable+0x10 = RoomCreate sender
ret = (*(code*)*create)(sm, state, room_id, 0, ...);   // send 0x12f
if (ret >= 0) GOTO state 4;                 // line 0x2d5 = 725, matchmaking host lobby
else          GOTO error(0x13);
```

`FUN_003b7d70` references the `NET_SM_CHOOSE_HOST_JOIN` and
`NET_SM_CREATE_GAME_WAIT` strings; the outer driver then runs
`g_matchSession.IsHost() ? NET_SM_CREATE_GAME_WAIT : NET_SM_CLIENT_LOBBY`
(`task-manager-online.cpp:1756`) and
`… ? NET_SM_SERVER_LOBBY : NET_SM_CLIENT_LOBBY` (`lobby-flow.cpp:1503`). **This is
a different state sequence from the custom-game host** (`NET_SM_CUSTOM_GAME_HOST_WAIT_INFO`,
handled in lobby-flow `_opd_FUN_0035cde0`, a separate `0x0035xxxx` file). The
opcode on the wire is the same (`0x12f`), but the surrounding matchmaking states —
entered because the player pressed Find Match and passed through START_MATCHMAKING
(`+0x7c=1`) — are what make the resulting game counted.

### What the server must do for "create-if-none" (and keep it PUBLIC)

1. **Reply to every `0x135` search with an EMPTY `0x136`** (`num_entries=0`, 16
   bytes) whenever the pool has no matching public game. Each empty result feeds
   the retry counter; after `retry_limit` attempts the client self-elects HOST and
   hosts a **public/matchmade** game (RoomCreate `0x12f` via `FUN_003b7d70`). The
   stub answers that `0x12f` exactly as it already does
   (`Member + OwnerChanged(1) + OwnerMember`) — nothing custom-specific is
   involved, so the "counted" property is preserved by the client's own state
   machine.
2. **Register that host's room in the public pool** (room_id + host npid +
   map/mode/counts) so a LATER searcher's `0x136` lists it → that searcher joins
   via `0x130` and is likewise on the matchmade/counted path. This is the piece
   the current stub lacks.
3. **Never route a find-match host into the custom flow.** The stub can't — it
   only answers opcodes — but it MUST tag the pool room as public so it is
   discoverable (see §4 for the discriminator).

**Server does NOT need to send a "you are host" message** — none exists on the
mapped wire; hosting is client-elected. The server's only levers are the `0x136`
list contents (empty → eventually host; non-empty → join) and registering hosted
public rooms.

---

## 4. Public/matchmade vs. private/custom — the distinction, and the server discriminator

**The distinction is the ENTRY state sequence, not primarily a wire field.** A
game is public/matchmade (and therefore counted) because the player pressed Find
Match and the flow went through `NET_SM_START_MATCHMAKING` → the matchmaking
CLIENT/host states. A game is custom/private because it entered the custom-game
flow (`NET_SM_CUSTOM_GAME_HOST_WAIT_INFO`, lobby-flow `_opd_FUN_0035cde0`) or came
from an accepted party invite. These are physically separate state sequences in
different translation units (`net-matchmaking.cpp` = `0x003bxxxx` vs
`lobby-flow.cpp` = `0x0035xxxx`).

**Concrete in-memory marker:** `START_MATCHMAKING` sets `g_matchSession+0x7c = 1`
(`FUN_003abe9c`) on entry; the custom entry does not. This `+0x7c` byte is the
best current candidate for the "this is a matchmade/counted game" flag that the
sibling agent's `g_70[0x6C]` arming site keys on — **candidate, not confirmed**:
I did not cross-reference it against that arming reader (sibling's scope). Worth a
direct check next: does the `g_70[0x6C]` arm-condition read `g_matchSession+0x7c`
(or something it seeds)?

**Server-side discrimination (what the stub can actually key on):** the stub can't
see `g_matchSession`, and both a matchmaking host and a custom host send the same
`RoomCreate 0x12f`. The clean, robust discriminator is the connection's history:

- A **find-match host** always sends `0x135` search broadcasts (during the search
  phase) BEFORE it self-elects and sends `RoomCreate 0x12f`. → mark its room
  **public**, add to the pool.
- A **custom/party host** never sends `0x135`; it goes straight to `RoomCreate`
  (custom) or its room is a party room (`PARTY_ROOM_PTR = 0x01387f58`). → mark
  **private**, keep out of the pool.

So: track per-connection "has sent `0x135` this session"; on `RoomCreate 0x12f`,
if that flag is set → public (pool it), else → private (exclude). This keeps
custom/party games out of Find Match results without needing to decode a `0x12f`
"public" attribute byte.

**Wire-field candidates for a create-time public flag (unconfirmed, lower
priority given the heuristic above):** `RoomCreate 0x12f` attribute block
(`0xa8:0xe8`, name at `0x28`, team at `0xb0`); the `0x140/0x141` room-flags u16;
and per-list-entry `entry[0x30]` (read by the join helper `FUN_003b2f40` and fed
to session vtable+0x2c). None is pinned to "public/private" this pass.

---

## 5. Stub design sketch (do NOT apply yet — stub is running live)

Replace the current `FIND_MATCH_OPCODE` branch (which wrongly pushes
`Member + OwnerChanged`) with a **search → list** responder, and add a
public-room pool fed by `RoomCreate`.

```python
# --- new shared state ---------------------------------------------------
public_pool_lock = threading.Lock()
public_pool = {}   # room_id(8B) -> {"host_npid", "map", "mode", "cur", "max",
                   #                 "conn", "entry56": bytes}  # PUBLIC games only

ROOM_SEARCH_OPCODE = 0x136

def build_room_search_list(search_obj_ptr, entries):
    """0x136 game list. entries = list of 56-byte wire entries (public rooms)."""
    body = bytearray(16)
    struct.pack_into(">I", body, 0, ROOM_SEARCH_OPCODE)
    # off 4 unread -> 0
    struct.pack_into(">I", body, 8, search_obj_ptr)   # MUST echo client's 0x135 off-8
    struct.pack_into(">I", body, 12, len(entries))
    for e in entries:
        assert len(e) == 56
        body += e
    return bytes(body)

def build_search_entry(room_id, host_npid, cur, mx, map_id=b"\0\0\0\0", mode=0):
    """56-byte SOURCE entry. Only room_id[0:8] is load-bearing today; the rest
    is best-effort until the 36-byte attribute block is field-mapped."""
    e = bytearray(56)
    e[0:8]   = room_id                              # dest[0:8] join key
    e[0x14:0x38-0][:]  # 36-byte attr block copied straight to dest[8:0x2c]:
    e[0x14:0x14+len(host_npid[:16])] = host_npid[:16]   # host identity (guess)
    struct.pack_into(">H", e, 0x0c, cur)            # -> dest[0x2c] (count)
    struct.pack_into(">H", e, 0x10, mx)             # -> dest[0x34] (count)
    return bytes(e)
```

Find-match branch (replaces the current two-searcher pairing entirely). Note it
records that this connection is a find-match participant — the discriminator that
later tags its `RoomCreate` as public (§4):

```python
elif opcode == FIND_MATCH_OPCODE and len(chunk) >= 12:
    searched_conns.add(id(conn))                            # <- this conn is doing find-match
    search_obj_ptr = struct.unpack(">I", chunk[8:12])[0]   # echo target (0x01383bd8)
    with public_pool_lock:
        # exclude this player's own room; only PUBLIC rooms
        entries = [build_search_entry(rid, r["host_npid"], r["cur"], r["max"],
                                      r.get("map", b"\0\0\0\0"), r.get("mode", 0))
                   for rid, r in public_pool.items()
                   if r["conn"] is not conn]
    conn.sendall(build_room_search_list(search_obj_ptr, entries))
    # EMPTY list -> after ~retry_limit empties the client self-elects HOST and sends
    #   RoomCreate 0x12f (a PUBLIC/matchmade host, counted). NON-empty -> client joins
    #   via 0x130 (also counted). Either way the game is on the counted path because the
    #   client came through START_MATCHMAKING; the stub must not, and does not, derail it.
```

RoomCreate branch: after the existing `Member + OwnerChanged` reply, register the
new room in the pool **only if this connection is a find-match host** (it sent
`0x135`). A custom/party host never sent `0x135`, so it is excluded — keeping
private games out of matchmaking results (§4):

```python
    is_public = id(conn) in searched_conns and room_ptr != PARTY_ROOM_PTR
    if is_public:
        with public_pool_lock:
            public_pool[room_id] = {"host_npid": npid, "conn": conn,
                                    "cur": 1, "max": max_players,
                                    "map": map_id, "mode": team}  # placeholder fields
```

(`searched_conns = set()` alongside the other module-level state; discard on
disconnect. Do NOT gate on it for the party/custom paths — they are untouched.)

`0x130 RoomJoin`: keep the existing cross-connection handler (already correct);
additionally bump the joined room's `public_pool[...]["cur"]` and drop the room
from the pool (or mark full) when `cur >= max`. On host disconnect / `0x133`
abandon, `del public_pool[room_id]`.

Keeping private games out: the pool is populated ONLY on a public
(Find-Match-hosted) `RoomCreate`; party/custom `RoomCreate` and party-room
objects (`PARTY_ROOM_PTR = 0x01387f58`) never enter it. The existing party/
custom flows are untouched — they use `Member`/`OwnerChanged`/`0x130` directly
and never emit `0x135`.

**Open items before this will fully load a joiner into a match:**
- The 36-byte per-entry attribute block (`src[0x14:0x38]`) is not field-mapped;
  a wrong host-npid/map/mode there may render the list oddly or fail a later
  join sanity check. Room_id at `[0:8]` is the only field proven load-bearing.
  First live test: send a **single-entry** list for a room a second client
  actually hosted and watch whether `GAME_LIST_PICK → 0x130` fires; iterate the
  attribute bytes from there.
- Confirm the empty-list path actually makes a lone searcher host (needs a live
  run: one client Find-Match with an empty `0x136` reply, watch for
  `IsHost()?…CREATE_GAME_WAIT` and a subsequent `RoomCreate 0x12f`).

---

## 6. Host stability + two-searcher coordination (2026-08-17 live-test follow-up)

Live test: the crash is fixed (RPCN soft-fails empty-npid RequestSignalingInfos)
and **search → 0x136 list → GAME_LIST_PICK works**. But the two searchers never
connect: each self-hosts, the host leaves SERVER_LOBBY after ~12s with no joiner,
both public rooms collide on the static room_id `0x01383bd8`, and the pool
flickers so the other searcher's list is almost always empty. Root causes, all
decompiled this pass:

### Q1 — why the host LEAVES SERVER_LOBBY (net-matchmaking.cpp:1039)

SERVER_LOBBY's per-frame handler is **`_opd_FUN_003b7a78`**:

```c
FUN_003b6dfc(members_obj, 1);                 // rebuild member table from the SM roster
count = FUN_003b19c4();                         // present member count (via FUN_00ad2768)
min   = FUN_0039f1e0();                         // = modeCfg+0x14  (min players to start)
if (count < min && (cfg+0x64 == 0 || count < cfg+0x64)) {
     FUN_003ca4a4(g_matchSession+0x98);          // room_id
     FUN_00ad0ca8(sm_conn);                       // TEAR DOWN the room  (emits 0x133 - see Q2)
     GOTO NET_SM_LEAVE_GAME;                       // line 0x40f = 1039  -> state 0x28
}
... if team-balanced (FUN_003b5468) and count>=min -> FUN_003b7920();   // START match, state 0x15=21
```

- **The count is the SessionManager room-member roster.** `FUN_00ad2768`
  enumerates the 4 room slots (`sm + i*0x180 + 0x748` = slot-active flag,
  `+0x668` = member record) — i.e. exactly the members our **`Member` (0x131)**
  broadcasts register. `FUN_0039f1e0`/`FUN_0039f218` read the selected mode's
  config record (`FUN_00349360`) at `+0x14` (min) / `+0x18` (expected).
- **What makes the host STAY:** the member count reaching `min`. **When a joiner
  arrives, the stub must push the host an updated 2-member `Member` roster** —
  that raises `FUN_00ad2768`'s count from 1 to 2. If `min <= 2`, the host then
  passes the check and `FUN_003b7920` starts the match (GOTO state 21) instead of
  leaving. So a join arriving + the 2-member roster IS what resets the wait.
- **Caveat (must verify live):** `min` = `modeCfg+0x14` is a per-playlist runtime
  value I can't read statically. If a public playlist's `min` is > 2, a lone host
  + one joiner will NEVER satisfy it and the host always bails. The `cfg+0x64`
  lower-bound term suggests the game can start below the ideal count, but the
  actual numbers need a live read (breakpoint `FUN_0039f1e0` / dump `modeCfg+0x14`
  and `+0x64`). If they exceed 2, 2-player find-match is not viable without
  additional real peers.

### Q2 — the 0x133 right after RoomCreate

The leave path calls **`FUN_00ad0ca8`**, which invokes SessionManager
**vtable+0x1c (`FUN_00ad65e8`)** = the room-slot teardown that sends the ~16-byte
**`0x133`** abandon (already documented as the "client abandons a room it's
tracking" sender). So the `0x133` the stub sees is the host giving up SERVER_LOBBY
because `count < min` — not a RoomCreate-reply defect. The RoomCreate reply itself
is fine (the one attempt that reached SERVER_LOBBY proves the matchmaking-host
path accepts `Member + OwnerChanged(1) + OwnerMember`).

Two things nonetheless make it churn *faster/worse* and must be fixed:
1. **room_id collision (Q4)** breaks the client's own room-slot id-gate on some
   attempts, so the host bails before even reaching SERVER_LOBBY.
2. **treating a host as a searcher:** once a connection has hosted, it is no
   longer in GAME_LIST_WAIT; **do not send it any more `0x136` lists.** They write
   into the same static object `0x01383bd8` (game room == search object) at
   `+0xa4/+0x200/+0x208` and re-arm search behavior on an object that is now a
   live room.

### Q3 — CONNECT_TO_HOST (1194) and CHOOSE_HOST_JOIN→force-leave (1294→596)

The joiner's connect handler is **`_opd_FUN_003b2a9c`**:

```c
host_rec = *(-0x7f60);                          // the selected game-list entry's host record
if (host_rec == 0) trapWord(0x1f);              // assert a host was selected
*(g_matchSession+0xa0) = host_rec[1];           // <- HOST ADDRESS BLOCK, copied from the
*(g_matchSession+0xa8) = host_rec[2];           //    0x136 entry's attribute region
*(g_matchSession+0xb0) = host_rec[3];           //    (entry src[0x14:0x38] -> struct[8:0x2c])
*(g_matchSession+0xb8) = host_rec[4];
*(g_matchSession+0xc0) = host_rec[5];
*(g_matchSession+0x98) = host_rec[0];           // room_id
p2p = (*net_obj.vtable[0x10])(net_obj, host_rec+1);   // START P2P CONNECT to the host peer
(*net_obj.vtable[0x14])(net_obj, p2p);
GOTO state 8;                                    // line 0x4aa = 1194
```

- **The connect is P2P signaling to the HOST PEER, not a `0x130` to us.** (The
  `0x130 RoomJoin` already happened back at GAME_LIST_PICK.) It uses the host
  identity carried in the **`0x136` entry's attribute block** — so that block MUST
  contain the **host's real NpId** or the joiner resolves nothing and
  CONNECT_TO_HOST times out (~30s) → CHOOSE_HOST_JOIN (1294) → force-leave (596),
  exactly the observed tail. Party 2-player matches prove P2P *can* establish;
  the two missing ingredients here are (a) the host still being present and (b)
  the entry carrying the host NpId.
- **Actionable:** fill the `0x136` entry attribute region (`src[0x14:0x38]`) with
  the host's 16-byte NpId (the value the host sent in its own RoomCreate name /
  the npid the stub already tracks for that connection). `entry[0:8]` = room_id,
  `entry[0x14:0x24]` = host NpId is the first concrete guess to try.

### Q4 — the room_id collision (both `0x01383bd8`)

Both game rooms carry the static room_id `0x01383bd8` because the stub derives the
public room_id from RoomCreate wire bytes that include the room-object pointer.
This is genuinely harmful: (a) the stub can't tell two public rooms apart in the
pool / when matching a `0x130` join, and (b) the client's own room-slot id-gate
(`room_obj+0x10`) can't distinguish rooms, so a joiner's `0x130` may match the
wrong slot. **The stub controls the room_id it advertises** (it fills `0x136`
`entry[0:8]`, the `Member` header `[16:24]`, and matches `0x130` by it), so it
must **synthesize a DISTINCT room_id per public host** (e.g. `os.urandom(8)` at
RoomCreate time) and use it consistently everywhere. The `room_ptr` hazard field
(wire offset 8) stays the client's real `0x01383bd8`; only the logical room_id
changes.

### The coordination fix (what the stub must do)

The deadlock is: host A needs a joiner to stay in SERVER_LOBBY (≤~12s window),
and searcher B needs A registered+stable to find it — but both run identical
self-host-on-timeout logic, and A's room flickers out of the pool. Resolve it by
making the stub the coordinator:

1. **Assign a unique room_id** to each public host at RoomCreate (fixes Q4).
2. **Register the host room immediately and keep it registered** across brief
   host wavering — only drop it on a real socket close, not on the first `0x133`
   (add a short grace, e.g. keep it discoverable for a few seconds after a stray
   abandon). This stops the flicker so B's `0x136` reliably lists A.
3. **Serve A's room to every other searcher's `0x136` at once** so B joins A
   rather than self-hosting. Because B's self-host needs several empty retries,
   one or two search cycles (~5-10s) is enough for B to find A first.
4. **On B's `0x130` join, push the HOST a fresh 2-member `Member` roster
   immediately** (before A's grace expires) so `FUN_00ad2768` reports 2 →
   `FUN_003b7a78` passes → A starts the match. Also push B its own 2-member
   roster (already done by the existing `0x130` handler).
5. **Once a connection has hosted, stop sending it `0x136`** (Q2).
6. **Put the host NpId in the `0x136` entry** so B's P2P connect resolves (Q3).

### Stub sketch delta (additions to §5)

```python
import os
# public_pool value gains a stable unique id + host npid + a grace timestamp:
#   public_pool[uid] = {"room_id": <8 unique bytes>, "host_npid", "conn",
#                       "cur", "max", "map", "mode", "abandon_ts": None}
hosted_conns = set()   # connections that became a public host (stop 0x136 to them)

# RoomCreate branch, when is_public (conn sent 0x135, room_ptr != PARTY_ROOM_PTR):
uid = id(conn)
room_id = os.urandom(8)                     # DISTINCT per host (fixes the 0x01383bd8 collision)
# ... build Member/OwnerChanged with THIS room_id (not chunk[4:12]) ...
hosted_conns.add(uid)
with public_pool_lock:
    public_pool[uid] = {"room_id": room_id, "host_npid": npid, "conn": conn,
                        "cur": 1, "max": max_players, "map": map_id, "mode": team,
                        "abandon_ts": None}

# 0x135 find-match branch:
if id(conn) in hosted_conns:
    continue                                 # a host is not a searcher - never send it a 0x136
searched_conns.add(id(conn))
search_obj_ptr = struct.unpack(">I", chunk[8:12])[0]
with public_pool_lock:
    entries = [build_search_entry(r["room_id"], r["host_npid"], r["cur"], r["max"])
               for r in public_pool.values()
               if r["conn"] is not conn]      # advertise OTHER hosts' unique room_ids
conn.sendall(build_room_search_list(search_obj_ptr, entries))

# build_search_entry: put the host NpId in the attribute block so the joiner's
#   CONNECT_TO_HOST P2P resolve succeeds (Q3):
def build_search_entry(room_id, host_npid, cur, mx, ...):
    e = bytearray(56)
    e[0:8] = room_id
    e[0x14:0x14+len(host_npid[:16])] = host_npid[:16]   # -> g_matchSession host-address block
    struct.pack_into(">H", e, 0x0c, cur); struct.pack_into(">H", e, 0x10, mx)
    return bytes(e)

# 0x130 RoomJoin branch (existing cross-connection handler), match by the UNIQUE
#   room_id, then IMMEDIATELY push the host a 2-member Member roster and bump cur.
#   That is the single most time-critical send: it must reach the host before its
#   SERVER_LOBBY grace (~12s from line 874) expires, or the host tears down (0x133).

# Host teardown grace: on 0x133 / socket close of a host, do NOT drop public_pool[uid]
#   instantly; set abandon_ts=now and purge only after a few seconds (or on real
#   close), so a searcher mid-cycle still finds it.
```

**Still to verify live (highest value):**
- `modeCfg+0x14` (min) and `+0x64` for the public playlists — the go/no-go for
  whether 2 players can ever start a matchmade game (breakpoint `FUN_0039f1e0`).
- That the host-address block is `entry[0x14:0x24]` = host NpId (breakpoint
  `FUN_003b2a9c` at the `host_rec[1..5]` copy, read what a working party-host
  connection would put there).

## State-code caveat (for the next session)

The numeric argument to `_opd_FUN_00347160(code, name_str)` is **not** a direct
index into the handler dispatch table at `0x012bd640` (8-byte stride,
`{handler_ptr, 0x01305870}`): e.g. `FUN_003b5ff4` (CLIENT_START, by dataflow) is
table index 40, yet logs `GOTO GAME_LIST_WAIT` with code 6. The handlers here
were pinned by **dataflow** (who sends the `0x135` search, who polls
`FUN_00ad0f60`, who calls the `0x130` sender), which is unambiguous and does not
depend on resolving that indirection. Resolving the code↔index map is left open;
it isn't needed for the flow.

## Evidence files (this pass)

- `research/ghidra/find_match_strings.txt` — state-name string VMAs.
- `research/ghidra/fm_state_refs.txt`, `fm_state_table.txt` — string xrefs + the
  `0x01269xxx` name table.
- `research/ghidra/fm_handlers.txt` — the 10 net-matchmaking state handlers.
- `research/ghidra/fm_sm_helpers.txt` — `FUN_00ad6c70` (search send),
  `FUN_00ad0f60` (status), `FUN_00ad2594` (count), + helpers.
- `research/ghidra/fm_handler_refs.txt` — dispatch table + PICK handler
  (`FUN_003b6404`).
- `research/ghidra/fm_dispatch_table.txt` — `0x012bd640` handler array.
- `research/ghidra/fm_entry_decode.txt` — `FUN_003c9228`/`FUN_003c8f20` (UI list
  decode), `FUN_00ad57e0` (0x135 body), `FUN_00ad6718` (0x130 join send).
- `research/ghidra/sessmgr_vtable_dump.txt:337-425` — the `0x136` receive case.
- `research/ghidra/fm_host_strings.txt`, `fm_host_refs.txt` — host/create/custom
  state strings + their handler xrefs.
- `research/ghidra/fm_host_decide.txt` — `FUN_003b8168` (START_MATCHMAKING),
  `FUN_003b7d70` (public host → RoomCreate), `FUN_003abe70/78` (`IsHost()`
  get/set = `g_matchSession+0x5c`), `FUN_003b3318` (host election),
  `FUN_003abe9c` (`g_matchSession+0x7c=1` marker), `FUN_003b3794`.
- `research/ghidra/fm_fork.txt` — `FUN_00ad1024`/`FUN_0039f218` (the count vs.
  expected host-election operands), `FUN_0035cde0` (custom-vs-server-lobby fork),
  `FUN_003f208c` (the `IsHost()` outer driver).
- `captures/tcp_catch.log` — the live 36-byte `0x135` packet.
