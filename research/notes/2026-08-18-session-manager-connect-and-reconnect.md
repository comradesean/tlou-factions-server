# Session-manager (port 7314) connect site, trigger, and the absence of a reconnect path

Verdict up front: the claim "the session-manager connection is opened once when
the client enters multiplayer, and there is no reconnect path" is **correct for
every situation that matters to the server**, but it is not literally true — the
binary does contain a second, automatic re-drive of the whole network-init
sequence. That re-drive lives in the *not-signed-in-to-PSN* state and is
inactive during a healthy multiplayer session. And "no reconnect path" should
not be read as "the client ignores the dead socket": it sets a global error flag
every frame, which fails matchmaking and, on the right screen transition, boots
the player with an error. None of that ever re-opens the socket.

One incidental result outranks the original question: the flag the client sets
on session-manager socket failure is **`g_70[0x6C]`** (`0x013835c0 + 0x6c`,
VMA `0x0138362c`) — the same byte `2026-08-17-match-counts-latch.md` documents as
the progression-crediting latch. That note's "only one setter" claim is wrong;
all nine setters hit this one byte. Details and the corrected table are in §4;
that note has been corrected in place.

A **server cannot trigger a reconnect**. Proven below by exhaustive call-site
enumeration: the only function that can ever produce a `connect()` to 7314 has
exactly three call sites in the whole EBOOT, all three inside the menu/state
machine, none reachable from any socket-receive path.

## Address-convention correction

`research/strings/strings_ascii.txt` lists **file offsets**, not VMAs. The
addresses quoted for the ndlib net strings in earlier work are 0x10000 low.
Actual VMAs: `ndlib/net/nd-net-controller.cpp` = `0x00ed7a30`,
`ndlib/net/net-session-manager-nd.cpp` = `0x00ed8048`,
`game/net/net-matchmaking.cpp` = `0x00e7d380`,
`recv() failed (errno=%d)` = `0x00ed7a60`. Pointer *values* stored in the
binary (e.g. the `'Multiplayer'` literal at `0x00e7a140`, the
`g_pSessionManager->Init()() failed. ret = 0x%x` literal at `0x00e7a320`) are
true VMAs and need no adjustment.

## 1. Where the 7314 socket is opened  (PROVEN)

`SessionManager::Init()` = `FUN_00ad71a0`, slot `+0x00` of the SessionManager
vtable at `0x01243b38` (opd `0x012e9ca8`). The connect sequence:

```
00ad724c  lwz   r9,-32768(r30)     ; net-config holder
00ad7250  lwz   r11,0(r9)          ; net-config object
00ad7258  addis r9,r28,2           ; r28 = this
00ad7260  addi  r9,r9,20576        ; r27 = this + 0x25060  (the control connection)
00ad7268  lwz   r11,92(r11)        ; cfg->service_table  (+0x5c)
00ad727c  lwz   r9,4(r11)          ; entry = table[+0x04]
00ad7280  lwz   r5,4(r9)           ; entry->port
00ad7284  lwz   r4,0(r9)           ; entry->host  (char*)
00ad728c  bl    0xacbf90           ; ndlib connect wrapper
```

`FUN_00acbf90` is the wrapper that prints `connect to %s:%i ...` /
`connect ok` / `connect() failed %x (errno=%d)`, i.e. the same one every other
service uses. The connection object is embedded in the SessionManager at
`this+0x25060` — the "4 room slots + 1 control connection" layout already
documented in `docs/protocol/session_manager_and_matchmaking.md`.

Resolution is therefore the same service-table mechanism as the siblings, but a
**different slot**: the session manager reads `cfg+0x5c`, not `cfg+0x54`.
Confirmed neighbours, same `{char* host; s32 port}` entry shape at `+0x04`:

| connect site | containing function | table slot |
|---|---|---|
| `0x003536e8` | `FUN_0035363c` | `cfg+0x4c` |
| `0x003d7934` | `FUN_003d7890` | `cfg+0x58` |
| `0x00ad728c` | `Init()` `FUN_00ad71a0` | **`cfg+0x5c`** |

The whole EBOOT contains exactly **eight** call sites to `FUN_00acbf90`
(`0x000211ac`, `0x003536e8`, `0x00356d50`, `0x003d7934`, `0x00acc4a4`,
`0x00ad4f90`, `0x00ad5264`, `0x00ad728c`). Only `0x00ad728c` targets the
session-manager service entry; `0x00ad4f90`/`0x00ad5264` build their addresses
arithmetically (peer/room connections, not a service-table lookup).

## 2. What triggers the connect  (PROVEN for the call chain, STRONGLY SUPPORTED for the naming)

```
main frame loop  0x000363c8 ─(guarded)─> …
UI / state machine
  ├ FUN_00354698  (0x00354884) ─┐
  ├ FUN_003548c8  (0x00354a2c) ─┼─> FUN_00353e34  "NetStartup"
  └ FUN_00354a90  (0x00354b84) ─┘        │
                                          │ 0x00354580  thread-create (0xe58a8c),
                                          │   entry = FUN_003557a8, stack 0xc000
                                          ▼
                                 FUN_003557a8  "NetInit" (own PPU thread)
                                          │ 0x003562ac  new(0x250d0) + ctor FUN_00ad84cc
                                          │ 0x00356324  bctrl  vtable[0] = Init()
                                          ▼
                                 FUN_00ad71a0  Init()  → connect 7314
```

`FUN_00353e34` is reached only via those three `bl`s; the function's `.opd`
descriptor (`0x0012baea8`) has no data references anywhere in either segment, so
it is never taken indirectly. Verified with a byte-level scan of both LOAD
segments for the word `0x00353e34` (one hit: its own `.opd`) and for
`0x012baea8` (zero hits).

`FUN_003557a8`'s own `.opd` (`0x012baf00`) is referenced from exactly one data
slot (`0x01268490`), which is read at `0x00354560` and handed to the
thread-create at `0x00354580` — i.e. NetInit exists solely as a thread entry
point, spawned once per NetStartup call.

The three NetStartup call sites:

- **`FUN_00354a90` — the Multiplayer menu command.** Logs the literal
  `'Multiplayer'` (`0x00e7a140`, loaded at `0x00354ae8`), runs sign-in/EULA
  checks (`0x007efbd8`, `0x007efc40`, `0x007edc7c`, `0x009a20b8`), then
  `0x00354b84  bl 0x353e34` with `r4 = 0`. Registered as a UI command in the
  big binding table `FUN_0034a560` under hashes `0xed9d8ae1` and `0x8216c72a`
  (`0x0034a5a0`, sites `0x0034a5b8` / `0x0034a5d8`). **This is the trigger for
  the 7314 connection in normal play: entering the Multiplayer menu.**
- **`FUN_00354698`** — the state function installed by NetStartup itself at
  `0x003541bc` on the *not-signed-in* branch (`0x00354194 bl 0xade448` returns
  0 → `0x003541a8`), after which NetStartup returns 0. It calls
  `0x00354884  bl 0x353e34` with `r3 = 0, r4 = 0`. Details in §3.
- **`FUN_003548c8`** — invite/join flow; calls NetStartup with **`r4 = 1`**
  (`0x00354a24 li r4,1`). `r4` is stored to net-globals `+0x18`
  (`0x00353ebc  stb r28,24(r9)`), and NetInit branches on that byte at
  `0x00356274`: zero selects the SessionManager (`FUN_00ad84cc`, 0x250d0
  bytes, the 7314 path), non-zero selects a different manager
  (`FUN_00ad53d8`, 0x26528 bytes) that never touches the service table. So
  **this call site never opens 7314.**

Net result: two paths can open 7314 — the Multiplayer menu command, and the
not-signed-in retry state.

## 3. Retry / reconnect logic  (PROVEN)

**Inside `Init()`: none.** The decompile (`research/ghidra/sessmgr_vtable_dump.txt`,
vtable+0x0) is straight-line: one `FUN_00acbf90`, the 28 opcode-size log lines,
one `ClientHello` send, one `ServerHello` recv, one `ClientHello2` send, return.
No loop, no second connect. It does not even check the connect return before
sending — `uVar6` (the connect result) is simply returned at the end, and the
only way `Init()` reports failure is a `ServerHello` opcode that is not `0x12e`.

**Inside `NetInit` (`FUN_003557a8`): none.** `Init()` is invoked once
(`0x00356324`); a negative return logs
`g_pSessionManager->Init()() failed. ret = 0x%x` (`0x00356338`) and sets error
`0x3c881700`, then jumps to the common exit `0x00356c84`. No retry loop.

**Inside `NetStartup` (`FUN_00353e34`): none.** It is linear; the success path
`0x003545e4 → 0x00354508 → 0x00354560` creates the thread and returns 1
(`0x003545ac li r3,1`), the failure paths return 0. There is no
"already-connected" guard on the thread-create either — every call spawns a new
NetInit thread and allocates a fresh SessionManager.

**The one automatic re-drive: `FUN_00354698`.** This is the update function of
the state NetStartup enters when the player is *not signed in* to PSN. Its
message-type-6 branch (`0x00354724`) computes three trigger conditions, all
suppressed when the byte at `0x014413b3` is set:

- `r31` — byte at `0x01305e90` is non-zero (`0x0035474c`–`0x00354758`);
- `r8`  — `FUN_00ade448()` (sign-in query) returns non-zero (`0x0035476c`);
- `r10` — `now - saved_time > 900` seconds (`0x003547a8`–`0x003547b8`; `now`
  read from `0x01329d30 + 0xf8`, `saved_time` stored at `0x0137a1e0`).

If all three are false it falls to `0x00354898` and does nothing. Otherwise it
re-queries sign-in and, when signed in, falls through to
`0x0035487c  li r3,0 / li r4,0 / bl 0x353e34` — a full network re-init,
including a fresh 7314 connect. The 900-second constant is a PSN-ticket-age
retry, not a socket-health retry.

Because this state is installed only on NetStartup's *not-signed-in* branch, it
is not the active state during a working multiplayer session. Confidence:
PROVEN that the branch installs it there and that no other site installs
`FUN_00354698`; STRONGLY SUPPORTED (not proven) that this state is never
re-entered while the player stays inside multiplayer.

## 4. What the client does when the socket dies mid-session  (PROVEN)

### The receive side

The poll/dispatch method is vtable slot `+0x04`, `FUN_00ad7604`:

```
00ad7624  lwz  r9,-32568(r30)      ; -> 0x014db290
00ad765c  lbz  r0,0(r9)            ; global suspend flag
00ad7664  bne  0xad8474            ; set -> return 0, no I/O at all
00ad7670  r26 = this + 0x25060
00ad7678  bl   0xacc634            ; poll(conn, 0, 5) & 5
00ad7684  li   r3,-1
00ad7688  blt  cr4,0xad8478        ; poll error -> return 0xffffffff
          … 30-second keepalive: send opcode 0x145, 4 bytes …
          … FUN_00acbd98 recv; if it returns 0 -> return 0xffffffff …
```

`FUN_00acc634` is `poll(fd, POLLIN|POLLHUP-ish mask 5, 0)`, so a peer FIN makes
the socket readable and the code proceeds to the recv.

`FUN_00acbd98` (recv wrapper) distinguishes two cases:

- **`recv() == 0` (clean EOF, our case)**: `0x00acbe20 cmpwi r3,0` /
  `0x00acbe4c beq 0xacbf5c` (buffered path) and `0x00acbed8`/`0x00acbefc`
  (plain path) both return 0. **No log line, no `shutdown()`, no `close()`,
  no flag.** This is why a server-side process kill produces *no* TTY output
  on the session-manager channel, unlike the leaderboard `recv() failed
  (errno=0)` case.
- **`recv() < 0` and `errno != EAGAIN(35)`**: `0x00acbf04`/`0x00acbf28` log
  `recv() failed (errno=%d)` (`0x00ed7a60`), then `0x00acbf4c bl 0xa0f6b8`
  (shutdown, how=2) and `0x00acbf58 bl 0xacbad0` (close). Returns -1.

Either way `FUN_00ad7604` returns `0xffffffff`.

### What the -1 does

`FUN_00ad7604` is called once per frame from `FUN_003532c8`, the network frame
update, which the main loop calls at `0x000363c8` gated on a "networking
active" byte (`[global]+0x19`, tested at `0x000363bc`):

```
003533f4  lwz  r9,-31532(r30)   ; -> 0x014db270, holds g_pSessionManager
003533f8  lwz  r9,0(r9)
00353400  lwz  r9,0(r9)         ; vtable
00353404  lwz  r9,4(r9)         ; vtable+0x04  = FUN_00ad7604
00353418  bctrl
0035341c  ld   r2,40(r1)
00353420  cmpwi cr7,r3,0
00353424  beq  cr7,0x353438     ; ret == 0 -> nothing
00353428  lwz  r3,-32616(r30)   ; -> 0x013835c0  (net-globals)
0035342c  li   r4,1
00353430  bl   0x3abf70
```

and `FUN_003abf70` is two instructions:

```
003abf70  stb  r4,108(r3)       ; r3->0x6c = r4
003abf74  blr
```

**That is the entire immediate reaction: one byte set to 1, every frame.** No
close, no state transition, no dialog, no reconnect. The only writer that clears
it is NetStartup itself (`0x00354278  li r4,0 / bl 0x3abf70`).

### The object in r3 at `0x00353430` — resolved, and it is g_70

`FUN_003abf70` is a generic `stb r4,108(r3)` used on whatever object the caller
supplies, so the displacement alone proves nothing. Resolved concretely:

```
r2                                   = 0x01305870
003532d4  lwz r30,-31188(r2)         ; TOC slot 0x012fde9c
          *0x012fde9c                = 0x0126fe20   (small-data anchor, this CU)
00353428  lwz r3,-32616(r30)         ; global slot 0x0126fe20 - 0x7f68 = 0x01267eb8
          *0x01267eb8                = 0x013835c0
0035342c  li  r4,1
00353430  bl  0x3abf70               ; stb 1, [0x013835c0 + 0x6c] = VMA 0x0138362c
```

So **r3 = `0x013835c0` — the object this project calls `g_70` / NetInfo — and
`r4 = 1`.** Confidence: PROVEN. The byte written is the same byte
(`0x0138362c`) that `2026-08-17-match-counts-latch.md` documents as the
"this match counts" latch gating all progression crediting at `0x003f2194`.

This falsifies that note's "`0x3f020c` is the only write to `g_70[0x6C]`" claim.
Re-resolving **all nine** `bl 0x3abf70` sites with each site's own small-data
anchor (the anchor is the *contents* of the per-unit TOC slot, and differs by
compilation unit) gives the same object every time:

| site | anchor (r30) | disp | global slot | r3 | r4 |
|---|---|---|---|---|---|
| `0x0034b538` | `0x0126fe20` | `-32616` | `0x01267eb8` | `0x013835c0` | 1 |
| `0x00353430` | `0x0126fe20` | `-32616` | `0x01267eb8` | `0x013835c0` | 1 |
| `0x00354278` | `0x0126fe20` | `-32616` | `0x01267eb8` | `0x013835c0` | **0** |
| `0x00354f90` | `0x0126fe20` | `-32616` | `0x01267eb8` | `0x013835c0` | 1 |
| `0x003555bc` | `0x0126fe20` | `-32616` (via `r31`, `0x0035577c`) | `0x01267eb8` | `0x013835c0` | 1 |
| `0x003af7a8` | `0x01271a3c` | `-32664` | `0x01269aa4` | `0x013835c0` | 1 |
| `0x003b0a14` | `0x01271a3c` | `-32664` | `0x01269aa4` | `0x013835c0` | 1 |
| `0x003b0ea4` | `0x01271a3c` | `-32664` | `0x01269aa4` | `0x013835c0` | 1 |
| `0x003f020c` | `0x01272f78` | `-32656` | `0x0126afe8` | `0x013835c0` | 1 |

The earlier "different objects `0x0132c530` / `0x01231258`" reading came from
applying the single anchor `0x01272f78` (the task-manager-online unit) to
displacements belonging to other units: `0x01272f78 - 32616 = 0x0126b010` →
`0x0132c530`, and `0x01272f78 - 32664 = 0x0126afe0` → `0x01231258`. Both are
real globals, just not the ones those instructions reach.

Polarity, since it matters: the crediting gate needs the byte **set** —
`0x003f2190 cmpwi cr7,r3,0` / `0x003f2194 beq cr7,0x3f3500` skips the body when
the byte is zero. A dead session-manager socket therefore *sets* the byte the
gate requires, not clears it. That does not mean a socket death causes crediting
(the body has further gates and the match-end path has to be reached at all),
but it does mean the byte is not a dedicated "this match counts" latch. Given
the full writer set — socket poll failure, a 3000-unit timeout (`0x00354f90`), a
>100 counter (`0x0034b538`), `FUN_003aeee8` returning -1 (`0x003af7a8`,
`0x003b0a14`, `0x003b0ea4`), a not-signed-in check (`0x003555bc`), cleared by
NetStartup (`0x00354278`) — and the reader set (disconnected-screen handlers
`FUN_0034f8bc`/`FUN_003505c8`, matchmaking abort `FUN_003ca9d0`, abnormal-leave
check `FUN_003ee6b4`, crediting gate `FUN_003f208c`), it reads far more like an
**online-session-state / network-fault** byte. Its exact semantics are an open
question; `2026-08-17-match-counts-latch.md` has been corrected in place.

Note the client keeps *writing* into the dead socket: `FUN_00ad7604`'s 30-second
keepalive (opcode `0x145`, 4 bytes; interval constant `30.0f` at
`0x01297680`, deadline stored at `this+0x25058`) still fires, and the send
wrapper `FUN_00acb93c` performs **no error handling whatsoever** — it calls
`0xa0ea78` (send) at `0x00acb9f0`/`0x00acba4c`, never reads `errno`, never
logs, never closes, and returns -1 which all session-manager senders discard.
So the send direction is fully silent too.

### Who consumes `g_70[0x6C]` (`0x0138362c`)

Read through the accessor `FUN_003abf68` (`lbz r3,108(r3); blr`), ~20 call
sites. The ones that matter:

- **Matchmaking, per frame.** `FUN_003ca9d0` (called from the same network
  frame update at `0x0035343c`) reads the flag at `0x003cab8c`; if set it
  branches to `0x003cb130` and returns `-1` (`li r11,-1` at `0x003cab94`).
  So a client with a dead 7314 socket will fail matchmaking operations when it
  reaches that state — but only when it reaches it.
- **Screen handlers, on message types 3 and 6.** `FUN_0034f8bc` — the handler
  registered for screen id `0x63b19e18` at `0x0034aa80`, which is exactly the
  screen NetStartup transitions to on success (`0x003545fc  li r4,0x63b1 /
  oris 0x9e18 / bl 0x3378e0`). On type 3 (`0x0034f8f4`–`0x0034f91c`) it calls
  `FUN_0034f0fc` (NetShutdown); on type 6 (`0x0034f92c`–`0x0034f9bc`) it
  pushes an error screen (`0x61a3662e` or `0x6d347be1` depending on
  `FUN_00ade448()`). `FUN_003505c8` (screen id `0x28d9da1f`, registered at
  `0x0034a8c0`) does the same pair at `0x003506dc`–`0x00350784`, calling
  NetShutdown at `0x00350710` and then pushing the same two screen ids.
- `FUN_0034f0fc` (NetShutdown) closes the control connection through vtable
  slot `+0x08` (`0x0034f394 bctrl`, target `FUN_00ad5a7c` =
  `FUN_00acbad0(this+0x25060)`) and NULLs `0x014db270` at `0x0034f3a8`.

So the flag *is* wired to the "disconnected from game servers" boot — through
those two screen handlers. Observed behaviour (six minutes of nothing) is
consistent: the player was on some other multiplayer screen whose handler does
not read the flag, so the message types those handlers act on never arrived.
Confidence: PROVEN for the code paths; STRONGLY SUPPORTED for the mapping of
message types 0/1/2/3/6 to screen-lifecycle events (the enum values are
consistent across `FUN_0034f8bc`, `FUN_003505c8`, `FUN_003548c8`,
`FUN_00354698`, but the names are not recoverable without the DC).

## 5. Can a server cause a reconnect?  (PROVEN: no)

`connect()` to 7314 happens only at `0x00ad728c`, only inside `Init()`, only
from the NetInit thread, only spawned by `FUN_00353e34`. `FUN_00353e34` has
exactly three call sites, all in the UI/state-machine code
(`0x00354884`, `0x00354a2c`, `0x00354b84`), and no indirect references. Nothing
in the session-manager receive dispatcher (`FUN_00ad7604`, opcodes
`0x12d`–`0x146`), nothing in the ticket-server or leaderboard handlers, and
nothing in the P2P/gameplay opcode paths reaches it.

Therefore **no message the server can send — on 7314, 7312, 7320 or any other
channel — can re-drive the connect.** There is no "retry" opcode, no state that
returns to a connect step, no watchdog. The only recoveries are:

1. the player leaving and re-entering the Multiplayer menu
   (`FUN_00354a90` → NetStartup), which is what was observed to work; or
2. the not-signed-in retry state (`FUN_00354698`), which requires the client to
   have dropped out of PSN sign-in first — i.e. it is not reachable from a
   healthy session, and certainly not server-triggerable.

## What this means for the server

- **Never drop the 7314 listener while clients are attached.** Killing the
  Session Manager process strands every connected client silently and
  permanently until the player navigates out of and back into Multiplayer.
  There is no way to page them back.
- **Restarts must preserve the accepted sockets, or not happen.** Config
  reloads, handler reloads and schema changes should be done in-process. If the
  process must be restarted, plan on telling players to back out to the main
  menu — that is the only recovery mechanism the client has.
- **A crashed handler is as bad as a crashed process** if it closes the socket.
  Wrap per-message handling so an exception cannot propagate to a socket close.
- **The client will keep sending `0x145` every 30 seconds** into a dead socket
  without complaint. That keepalive is the client's only liveness signal, and
  it is one-way — the client draws no conclusion from its absence in the other
  direction, so there is no server-side keepalive we can withhold or send to
  provoke a reconnect.
- **A clean EOF from the server is invisible in the TTY.** Unlike the
  leaderboard channel (which produced `recv() failed (errno=0)` and an
  "Error 9" boot), a server-side FIN on 7314 logs nothing. Absence of TTY
  output is not evidence the connection is healthy.
- **Downstream symptom to expect**: the stranded client is not inert. Its
  `g_70[0x6C]` flag is set, so any matchmaking operation that reaches
  `FUN_003ca9d0`'s check will fail with -1, and the next transition onto screen
  `0x63b19e18` or `0x28d9da1f` will tear down networking and show the
  disconnected error. A stranded client can therefore look "fine" for minutes
  and then fail confusingly on the next action.

## Method notes

- `research/tools/eboot_analysis/scan_bl.py`, `scan_anchor.py`, `fnstart.py`,
  `fnglobals.py` plus raw byte scans of both LOAD segments for function
  addresses and `.opd` addresses. The byte scans are what make the "exactly
  three call sites" claim safe against Ghidra's known missed-xref problem: they
  cover indirect references through data as well as `bl`.
- The r2 TOC anchor for the `net-startup`/`net-init` compilation unit is
  `u32(0x012fde9c) = 0x0126fe20`; for the session-manager unit,
  `u32(0x012feca0) = 0x0129f5c0`; for `nd-net-controller.cpp`,
  `u32(0x012fec80) = 0x0129f378`. Ghidra's `PTR_PTR_012fde9c`-style displacement
  operands are relative to those values, not to the slot addresses.
