# `leaderboard-server` client + wire protocol (EBOOT)

**Date:** 2026-08-17
**Scope:** full client-side decode of the custom `leaderboard-server`
sub-protocol (the four `leaderboard-*` command strings), sufficient to write a
stub. Companion to `docs/protocol/0x11_sibling_servers_family.md` (which
identified `leaderboard-server` as a member of the ticket-server handshake
family but explicitly left the plaintext command/response layout OPEN). This
note closes that gap.

All addresses verified against the shared Ghidra project
(`research/ghidra/tlou_factions`). String file-offset -> VMA = +0x10000.

---

## BLUF

- **Transport: TCP control connection**, identical framing to `ticket-server`
  and the other `*-server` siblings. The client resolves a `{ip,port}` pair
  from the shared `net1.bin`-populated service-descriptor table (leaderboard's
  entry at struct offset `+0x54`), TCP-connects (`FUN_00acbf90` = build
  sockaddr / socket / setsockopt / connect), sends the **88-byte hello**
  carrying the literal service name `"leaderboard-server"`, and requires an
  **8-byte hello reply whose byte[0] == `0x22` (`"`)** before proceeding
  (`FUN_00acc424`, the shared handshake helper). This is the exact same
  connect+hello as ticket-server — see `docs/protocol/0x11_ticket_server_hello.md`.
- **After the hello, the logical payload is line-oriented ASCII**: a
  `printf`-built command line is sent, and (for reads) `\n`-delimited response
  lines are parsed, each entry line prefixed with `+`. Fields are separated by
  a **single SPACE** (verified: delimiter global = `0x00e79948` = `" "`;
  terminator global = `0x00f0b170` = `"\n"`). **The prior sibling doc guessed a
  `,` delimiter — that is wrong; it is a space.**
- The blob field on each entry is **standard base64** (decode LUT verified at
  `0x00f022c0`: `A-Z`=0..25, `a-z`=26..51, `0-9`=52..61, `+`=62, `/`=63,
  `=`-terminated), decoded by a hand-unrolled 4-in/3-out state machine.
- **Four commands, all built by the same code region** (`net-leaderboard.cpp`,
  functions `0x003aeee8`..`0x003b0f6c`), each running on its own short-lived
  PPU thread (`sys_ppu_thread_exit` at the end of each).
- **Confirmed board IDs (decimal):** `0x194`=404, `0x195`=405, `0x196`=406
  (write path). Reads use `0x195` (clan/overall summary) plus any board chosen
  from a runtime-populated UI board-descriptor table. Board list beyond these
  is populated at runtime (BSS `0x01374884`), not statically enumerable.
- **Stubbable with the existing TCP-control-server pattern** (same as
  `tools/session_manager_stub.py`): accept TCP, answer the 8-byte
  `22 00 00 00 xx xx xx xx` hello reply, then speak the line protocol below.
  **One open dependency:** whether the post-hello bytes are sent raw or through
  the disputed "encrypt-then-MAC frame" layer — see "Framing caveat" at the end.

---

## 1. Code map (verified addresses)

Command strings (file offset -> VMA), all confirmed via Ghidra reference
manager as `printf` format args:

| VMA | string |
|---|---|
| `0x00e7d268` | `leaderboard-server` (service name passed to hello) |
| `0x00e7d280` | `leaderboard-get %i 1` |
| `0x00e7d298` | `leaderboard-range %i %i %i 1\n` |
| `0x00e7d2b8` | `leaderboard-update %i %s %lld %s\n` |
| `0x00e7d258` | `Page`  (nearby label) |
| `0x00e7d260` | `Score` (nearby label) |

Functions (code VMA; each is a PPU-thread body unless noted):

| addr | role |
|---|---|
| `0x003aeee8` | **GET** worker. `int get(ctx, board, count, names[], entries[], blobs[])`. Batches up to 16 names/req. |
| `0x003afb74` | **RANGE (blob)** worker. Page of 10 entries around the caller's rank; decodes per-entry base64 blob. Calls GET (`0x003aeee8`) to find own rank first. |
| `0x003af46c` | **RANGE (clan/aggregate)** worker. Fetches party/clan members' ranks via GET, computes an average score, then a `range board 0 1` query. |
| `0x003b0f6c` | **UPDATE** worker ("submit my score"). Single round trip. |
| `0x003aea3c` | UPDATE enqueue+spawn. `submit(this, board, score_s64, record[64])` -> writes 1 of 4 job slots -> spawns `0x003b0f6c`. |
| `0x003ae944` | RANGE-clan launcher. `start_clan(job, board)` -> `job+0x68=board` -> spawns `0x003af46c`. |
| `0x003ae9bc` | RANGE-blob launcher. `start_range(job, board, start)` -> `job+0x50=board`, `job+0x54=start` (`0xffffffff` = "center on my rank") -> spawns `0x003afb74`. |
| `0x003afb18`,`0x003b0f10` | thin thread trampolines (call `0x003af46c` / `0x003afb74`). |

Net primitives (shared with the whole `*-server` family):

| addr | role |
|---|---|
| `0x00acc424` | connect + hello handshake (name arg, 88B hello, 8B reply, byte[0]==`"`). |
| `0x00acbf90` | TCP connect (sockaddr/socket/setsockopt/connect). |
| `0x00acd5f8` | send-all (buffered). |
| `0x00acd568` | recv (buffered; returns bytes, `<1` = closed/done — but see §8: at the leaderboard call sites a server EOF is treated as an ERROR, not end-of-response). |
| `0x00acbad0` | close/teardown. |
| `0x00e46560` | `snprintf(dst, size, fmt, ...)`. |
| `0x00e45684` | `strncat`/`strlcat` (append). |
| `0x00e40ad8` | `strlen`. |
| `0x00e40e58` | `strtok_r(str, delim, saveptr)`. |
| `0x00e441ac` | `strtoll(str, end, base)`. |
| `0x00e45b10` | `strcpy`. |
| `0x0001fd54` | base64 **encode** (used by UPDATE for the trailing blob). |

Global anchors (base ptr `*(0x012fdf14)` = `0x01271a3c`; offsets as Ghidra
prints them): delimiter `" "` @ `-0x7fac` (`0x00e79948`); terminator `"\n"` @
`-0x7fa8` (`0x00f0b170`); base64 decode LUT @ `-0x7fa0` (`0x00f022c0`); player
NPID string @ `-0x7fd0` (subsystem obj `0x013839d0`, runtime); connection
singleton @ `-0x7fb8` (`0x014db280`, runtime); pending-update queue @ `-0x7f88`
(`0x01383a68`, runtime); party/clan member array @ `-0x7f9c` (`0x0137d258`,
runtime, `0x2f8`-byte records).

---

## 2. Request formats (plaintext line, before any frame layer)

Field separator is a single space; lines end with `\n`. The trailing literal
`1` in get/range is a constant emitted by the format string (protocol
version / "include-metadata" flag; always `1`).

### 2.1 `leaderboard-get` — batch lookup by name
Built in `FUN_003aeee8`:
```
leaderboard-get <board:int> 1 <name0> <name1> ... <nameN>\n
```
- `<board>` = `%i` board id (caller arg).
- Names come from the `names[]` array (`0x24`-byte records, one per player);
  appended **up to 16 per request** (`strncat` loop `uVar17 != uVar18+0x10`),
  then the outer loop re-issues `leaderboard-get` for the next 16 until all
  `count` names are queried.
- Purpose: look up specific players' ranks/scores by their id/name.

### 2.2 `leaderboard-range` — page of the board
Format string already carries the trailing `1\n`:
```
leaderboard-range <board:int> <start:int> <end:int> 1\n
```
- **`FUN_003afb74` (blob page):** first calls GET to learn the caller's own
  rank `r`, computes `start = ((r-1)/10)*10`, `end = start+9` -> a 10-row page
  aligned to the caller's position. `job+0x54 == 0xffffffff` triggers this
  "center on me" behavior; otherwise `job+0x54` is used as an explicit start.
- **`FUN_003af46c` (clan/aggregate):** issues `leaderboard-range <board> 0 1 1`
  (top row) to read the board total, having already GET-fetched each clan/party
  member to compute an average score (`job+0x78`/`+0x7c`).

### 2.3 `leaderboard-update` — submit my score
Built in `FUN_003b0f6c`:
```
leaderboard-update <board:int> <npid:string> <score:int64> <base64-metadata>\n
```
- `<board>` = job-slot offset `+4` (the board id from the enqueue call).
- `<npid>` = player NPID/online-id string (subsystem global `0x013839d0`).
- `<score>` = `%lld`, signed 64-bit, job-slot offset `+8`.
- `<base64-metadata>` = base64 of the job's trailing record (job-slot `+0xc`,
  up to 0x40 bytes, trailing NUL bytes trimmed before encoding via
  `FUN_0001fd54`). In the match-end path this record is often zero-filled
  (`memset(local_b8,0,0x40)` before submit), i.e. the blob may be empty.
- Single round trip: send, one bounded `0x100`-byte recv, close. **Reply is not
  parsed** — the client only needs the recv to succeed.

---

## 3. Response formats (what the client parses)

Read replies are a stream split on `\n`; the client scans each complete line
and only acts on lines whose first char is `+`. Tokens are space-separated
(`strtok_r`). Two line shapes:

> **LIVE CORRECTION (2026-08-17 evening, see §8):** the response must end with
> a trailing NUL byte — that, not EOF, is what terminates the client's read
> loop. This section's static read missed it.

### 3.1 GET reply line (`FUN_003aeee8`) — 4 tokens
```
+<rank:int> <name:string> <score:int64> <base64-blob>\n
```
Per matched entry, the client stores:
- `entry.name`   = `<name>`            (`strcpy`, entry offset `+0x00`)
- `entry.rank`   = `atoi(<rank>) + 1`  (entry offset `+0x5c`)
- `entry.score`  = `atoll(<score>)`    (s64, entry offset `+0x70`)
- `blob[idx]`    = base64decode(`<base64-blob>`) into the `0x40`-byte
  per-entry blob array.
(Entry stride `0x80`; blob stride `0x40`.)

### 3.2 RANGE (blob) reply line (`FUN_003afb74`) — 3 tokens, or 1
```
+<name:string> <score:int64> <base64-blob>\n     (a ranked entry)
+<total:int>\n                                   (single token = board total count)
```
- Ranked entry: `entry.name=<name>`, `entry.score=atoll(<score>)`,
  `entry.rank = start + index + 1` (computed positionally — **not** read from
  the wire here), `blob = base64decode(<base64-blob>)`.
- Single-token line sets `job.total (+0x24) = atoi(<total>)`.

### 3.3 RANGE (clan) reply line (`FUN_003af46c`) — 1 or 2 tokens
```
+<total:int>\n            -> job.total (+0x24) = atoi(total)
+<a:int> <b:int>\n        -> job.+0x88 = atoi(b); job.count (+0x70)++
```
No base64 in this variant.

**Endianness / framing of the logical payload:** none — it is NUL-terminated /
`\n`-delimited ASCII. All integers are decimal text; the s64 score is decimal
text parsed with `strtoll`. Read loops use a 2048-byte (`0x800`) receive
buffer and re-pack partial lines across recvs. There is **no** length prefix
and **no** binary opcode at the logical layer.

---

## 4. Triggers (when each command fires)

- **UPDATE (submit):** the match-end scoring routine `FUN_003f208c`
  (task-manager-online / OnMatchEnd family) calls `FUN_003aea3c` **three times**
  per match end:
  - board **`0x195`** — always (overall / clan-supplies score; value read from
    a per-clan 32-bit stat at `+0x1be0`).
  - board **`0x196`** — when game mode `*(short*)(state+0xc) == 2` (per-mode
    performance metric, float-derived, clamped/normalized to s64).
  - board **`0x194`** — when game mode `== 3` (same shape as `0x196`, other mode).
  So `0x195` is the common board; `0x194`/`0x196` are the two mode-specific
  skill boards. Modes 2/3 correspond to the two Factions objective modes
  (Supply Raid / Survivors — see `research/notes/2026-08-16-factions-metagame-reference.md`).
- **READ, clan/overall summary:** `FUN_00348f18` (a menu state handler) calls
  `FUN_003ae944(job, 0x195)` when its state == 0 — i.e. opening the
  clan/post-match summary reads board `0x195`.
- **READ, leaderboard screen:** `FUN_0031e1a8` (the leaderboard UI
  scroll/paging handler) calls
  `FUN_003ae9bc(job, board = table[sel*0x0c], start = ui.start)`, where the
  selected board id comes from a runtime board-descriptor table
  (`*(0x12fde68)-0x7fb8` -> `0x01374884`, `0x0c`-byte records
  `{u32 board_id, u32, u32}`), and `start = 0xffffffff` means "center the page
  on my own rank". Paging updates `ui.start` and re-issues the range.

---

## 5. Board IDs

| board id | dec | use | evidence |
|---|---|---|---|
| `0x195` | 405 | overall / clan-supplies; submitted every match; read by clan summary | `FUN_003f208c` unconditional submit; `FUN_00348f18` read |
| `0x196` | 406 | mode-2 skill board | `FUN_003f208c`, `mode==2` |
| `0x194` | 404 | mode-3 skill board | `FUN_003f208c`, `mode==3` |
| (others) | — | additional boards shown in the leaderboard UI | ids live in runtime table `0x01374884`; not statically enumerable this pass |

The `Page` / `Score` string labels adjacent to the command strings
(`0x00e7d258` / `0x00e7d260`) are UI column/tab labels for this screen.

---

## 6. Kaitai-style sketch (logical payloads)

```ksy
# leaderboard commands are ASCII lines; model as text for the stub.
meta:
  id: leaderboard_line
  encoding: ASCII
# --- requests (client -> server), one line each ---
# "leaderboard-get <board> 1 <name>...<name>\n"     (<=16 names/line)
# "leaderboard-range <board> <start> <end> 1\n"
# "leaderboard-update <board> <npid> <score_s64> <b64>\n"
# --- responses (server -> client), '\n'-delimited, '+' entries ---
# GET:          "+<rank> <name> <score> <b64>\n"
# RANGE(blob):  "+<name> <score> <b64>\n"   and  "+<total>\n"
# RANGE(clan):  "+<total>\n"  and  "+<a> <b>\n"
```
The transport frame (hello + optional encrypt-then-MAC) is already modeled in
`protos/0x11_leaderboard_server_hello.ksy` / `_hello_response.ksy` (identical to
ticket-server's, by construction).

---

## 7. Stub recommendation

Reuse the `session_manager_stub.py` TCP-control pattern:
1. Accept TCP on the leaderboard port (port not yet decoded from `net1.bin`;
   descriptor offset `+0x54`. Only ticket-server's 7320 is confirmed live).
2. On connect, read the 88-byte hello, reply with 8 bytes
   `22 00 00 00 xx xx xx xx` (byte[0] `0x22` is the only byte the client
   branches on; the 4-byte tail is cached as a session token but never
   validated for these commands).
3. Read `\n`-terminated command lines and dispatch on the verb:
   - `leaderboard-update` -> accept, reply anything (client ignores the body;
     just don't hang the single bounded recv). A bare line is fine.
   - `leaderboard-get <board> 1 <name>...` -> for each name emit
     `+<rank> <name> <score> <b64>\n`.
   - `leaderboard-range <board> <start> <end> 1` -> emit `+<total>\n` then rows
     `+<name> <score> <b64>\n` for the requested range (blob variant), or
     `+<total>\n` / `+<a> <b>\n` for the clan variant. A minimal legal answer
     is a single `+0\n` (empty board) — the parsers tolerate zero entries.
4. Close after the client stops (recv returning 0 ends its loop).
   **LIVE CORRECTION (see §8):** "the client's loop ends on recv 0" is
   DISPROVED — the loop ends on a trailing NUL in the response, after which
   the client closes first. Never close (or half-close) before the client
   does: a server-initiated EOF here trips the client's network-error path.

**Framing caveat — RESOLVED LIVE (2026-08-17, see §8):** post-hello bytes ARE
keyed encrypt-then-MAC frames (`0x33` magic), both directions — client
requests decrypt with `tools/ticket_cipher.py` (tag_ok) and the stub's
encrypted replies are accepted and rendered. The raw-ASCII reading of
`0x11_ticket_server_hello.md` is wrong for this path. (Original text of the
caveat, for the record: `FUN_00acd5f8`/`FUN_00acd568` are the *same* buffered
send/recv wrappers ticket-server uses for its post-hello messages C/D, so
whatever ticket-server needs, leaderboard needs byte-for-byte the same.)

---

## Confidence

| claim | confidence | basis |
|---|---|---|
| TCP + shared hello handshake, service name `"leaderboard-server"`, 8B `0x22` reply | high | `FUN_00acc424`/`FUN_00acbf90` decompiled; matches ticket-server doc |
| Four command line formats (verbatim strings + space delimiter + `\n`) | high | format strings + delimiter/terminator globals resolved to bytes |
| GET/RANGE/UPDATE request field mapping | high | direct decompile of the four workers |
| Response line shapes + per-entry field offsets + base64 | high | decompile of the parse loops + LUT bytes |
| Board ids 0x194/0x195/0x196 and their triggers | high | `FUN_003f208c`/`FUN_00348f18`/`FUN_0031e1a8` decompiled |
| Full board enumeration | low | rest of the board table is runtime-populated (BSS), not read this pass |
| Whether post-hello bytes are raw vs encrypted-frame | ~~unresolved~~ **confirmed: encrypted frames** | live (2026-08-17): requests decrypt tag_ok, encrypted replies accepted + rendered (§8) |
| Response termination: trailing NUL sentinel, client closes first; server EOF = client error path | high (live) | three-way live evidence, §8; corrects §3/§7's "EOF ends the loop" static read |

---

## 8. Live corrections (2026-08-17 evening, stub commit `f2f4162`)

First live exercise of a real-reply stub (`tools/ticket_server_stub.py`
`handle_leaderboard`) surfaced two errors in this note's static reading and
closed its one open item:

1. **Response termination is a trailing NUL byte, not EOF.** Three-way live
   evidence, each isolating one variable:
   - NUL-only placeholder replies (pre-decode stub): client parses, closes the
     connection ITSELF, no error, empty board.
   - `'+'`-rows without NUL + prompt server half-close: rows RENDER, but the
     EOF trips the client's error path — TTY.log `recv() failed (errno=0)` →
     `Error 9` → "You have been disconnected from the game servers" boot to
     the main menu ~1s after the screen opens.
   - `'+'`-rows without NUL, server holds the socket: infinite spinner, then
     the same EOF error when the server's idle timeout finally closes.
   So the client's read loop consumes until NUL (mirroring its own
   strlen/NUL-terminated send side), then the client closes first. The recv
   wrapper's `<1 = closed/done` (§1 code map) is only the mechanical return
   convention — at the leaderboard call sites a server EOF is an ERROR, not a
   terminator.
2. **Framing is encrypted frames, both directions** (the §7 caveat, now
   resolved): requests decrypt via `tools/ticket_cipher.py` with valid tags;
   replies encrypted with the message-D direction convention (out-counter
   seeded from client_nonce) are accepted and rendered.
3. Working reply shape used by the stub, confirmed rendering on both clients
   across boards 404/405/406 (solo GET, multi-name GET, RANGE paging):
   `"+..." lines + "\x00"` in one encrypted frame, `+<total>` emitted before
   the RANGE rows, server holds the socket until client FIN (30s idle cap).
