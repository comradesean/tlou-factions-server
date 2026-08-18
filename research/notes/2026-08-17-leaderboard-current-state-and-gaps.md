# Leaderboards: current state and gap analysis (2026-08-17)

Scope: "what happens today and what's missing" for in-game leaderboards.
The leaderboard-server **wire protocol** decode from the EBOOT is covered
separately (forthcoming
`research/notes/2026-08-17-leaderboard-server-protocol.md`, not present at
time of writing). This note is the current-state + gap-list half.

## TL;DR

- **The client already reaches leaderboard-server today.** It is one of the
  `0x11` sibling-server family; it resolves to `192.168.1.100:7320` (same IP
  and same port as `ticket-server`) and its connections land in
  `tools/ticket_server_stub.py`. 37 `leaderboard-server` hellos are logged in
  `tools/ticket_server_stub-run.log`, alongside 104 `ticket-server` and 926
  `heartbeat-server` on the same 0x7320 listener.
- **It does not crash and does not error.** The stub completes the 4-message
  handshake, decrypts the request cleanly, and replies with a fixed
  16-zero-byte placeholder frame. Net effect: `leaderboard-get`/`-range`
  return **zero rows** (empty board, no `+`-lines to parse), and
  `leaderboard-update` is **accepted-and-discarded** (client does one bounded
  recv, doesn't inspect the body). No "Lobby Server Error".
- **RPCN's score infra is irrelevant.** `sceNpScore` appears **nowhere** in
  the strings dump; TLOU rolls its own `leaderboard-*` verbs. `db_score.rs` /
  `score_cache.rs` / `stat_server.rs` are not on this path. Do not invest
  there.
- **No signing on updates.** The trailing `%s` in `leaderboard-update %i %s
  %lld %s` is a base64 array of big-endian u32 secondary stats, not a
  signature/HMAC.

## 1. Does the client attempt leaderboards, where, and what happens?

Yes. Evidence in `tools/ticket_server_stub-run.log` (grep `leaderboard`):

```
opcode=0x11 client_nonce=0x13ae1ceb service_name='leaderboard-server'
decrypted plaintext (34 bytes): b'leaderboard-get 405 1 comradesean\n'
decrypted plaintext (28 bytes): b'leaderboard-range 405 0 9 1\n'
decrypted plaintext (58 bytes): b'leaderboard-update 406 comradesean 43937 AAADogAAAH8AAAAB\n'
```

- **Transport:** the standard sibling-server `0x11` handshake (see
  `docs/protocol/0x11_sibling_servers_family.md`). 88-byte hello with
  `service_name='leaderboard-server'` -> 8-byte `0x22` hello_response
  (session_token=0) -> encrypted `0x33` request frame (decrypts fine with the
  live-confirmed key in `tools/ticket_cipher.py`) -> our `0x33` response
  frame. Client then closes the connection ("closed by peer after
  handshake") - i.e. it is satisfied with the handshake, it just got no data.
- **Verbs observed live** (matching the EBOOT format strings at `e6d280`/
  `e6d298`/`e6d2b8`):
  - `leaderboard-get <board_id> 1 <playername>` - fetch my own row.
  - `leaderboard-range <board_id> <start> <count> 1` - fetch a page of the
    board (seen `0 9`, i.e. top 10).
  - `leaderboard-update <board_id> <playername> <score> <base64_blob>` -
    submit my score. **This fires at match end** (updates are interleaved
    with the get/range reads across the capture, three board IDs seen: 404,
    405, 406 - distinct stat categories).
- **Outcome:** no crash, no error dialog. `-get`/`-range` render an empty
  board (client parses `+`-prefixed reply lines; a zero-filled frame yields
  none). `-update` is a single bounded recv the client doesn't parse, so it
  "succeeds" from the client's view while our stub throws the data away.

### The update blob is stat data, not a signature

`leaderboard-update ... <score> <base64>` - the base64 decodes to an array of
big-endian u32s (verified):

| board | score | blob u32s |
|---|---|---|
| 405 | 6/9/10/12/19/33 | `[]` (single 0x00 byte, `AA==`) |
| 404 | 36285 | `[2800, 463, 4]` |
| 406 | 43937 | `[930, 127, 1]` |
| 406 | 35352 | `[6305, 1928, 33, 4]` |

Writer-defined length (0, 3, or 4 u32 secondary/tiebreaker stats). So gap (e)
"auth/signing" does **not** exist - nothing to forge or sign. (Per the
project's no-opaque-blob rule these u32 fields should be named in the
protocol proto; that's the protocol-decode note's job.)

## 2. Address resolution status: SOLVED (already pointed at us)

Leaderboard-server is not un-redirected dead infra like the in-game-commerce
endpoint was. It rides the exact same resolution path as ticket-server:

- All sibling `*-server` IPs come from the `net1.bin`-populated
  service-descriptor struct (per-service offset; leaderboard-server = `+0x54`
  per `docs/protocol/0x11_sibling_servers_family.md`). The net1.bin IPs
  (`50.18.104.153` et al., all dead AWS EC2) are rewritten to
  `192.168.1.100` via the repacked `net1.bin.psarc.crypt`
  (`tools/served_content/`, served by `catch_http.py`; solve documented in
  `research/notes/net1bin-server-list.md`).
- In practice every sibling resolves to `192.168.1.100:7320` - proven by the
  log: `ticket-server`, `heartbeat-server`, and `leaderboard-server` hellos
  all arrive on the **single** `0.0.0.0:7320` listener of
  `ticket_server_stub.py`. So leaderboard-server needs **no new redirect and
  no new port**; it is already delivered to our stub.

There is no separate leaderboard hostname in a config file to chase - it is
IP/port from net1.bin, already handled.

## 3. ND stub pattern + is a catch-all already logging it

- The pattern (see `tools/session_manager_stub.py` / `ticket_server_stub.py`)
  is a TCP listener on the resolved host:port speaking the control protocol.
- Leaderboard traffic is **already** being caught and fully decrypted by
  `ticket_server_stub.py` because it shares the 0x11 handshake and the 7320
  port. `catch_tcp.py` is not in this path (the stub owns 7320).
- **No port collision to solve** - reuse is intended: one 7320 listener
  multiplexes all siblings by the `service_name` field in the hello. The stub
  already extracts `service_name`; it just doesn't branch on it yet.

## 4. RPCN score relevance: NOT RELEVANT (verdict)

`grep -i sceNpScore research/strings/strings_ascii.txt` -> **no hits**. The
game never calls the sceNpScore SDK path; it uses its custom `leaderboard-*`
verbs over the ND sibling-server transport. Therefore
`backend/rpcn/src/server/{database/db_score.rs,score_cache.rs,stat_server.rs}`
are dead weight for this feature. Do not extend or wire them. (The only reuse
worth borrowing from RPCN is the *idea* of a small sqlite store - see gap c.)

## 5. Prioritized gap list (to working in-game leaderboards)

Current handling in brackets.

### (a) Address resolution / redirect - DONE
Already resolves to `192.168.1.100:7320` and reaches our stub. Nothing
missing. (Depends only on the existing net1.bin repack + watcher already in
place.)

### (b) A stub that speaks the leaderboard reply protocol - THE core gap
[partial] The 0x11 handshake, decrypt, and `service_name` extraction are
done; the reply is a hardcoded 16-zero-byte placeholder shared with
ticket/heartbeat. **Missing:**
  1. Branch `ticket_server_stub.handle()` on `service_name ==
     'leaderboard-server'` (and parse the decrypted verb line).
  2. For `-get`/`-range`: build the `+`-prefixed line response the client's
     batch-fetch parser expects (per
     `docs/protocol/0x11_sibling_servers_family.md`: lines starting `+`, 4
     delimited fields, fields 3/4 base64-decoded to a per-entry record), then
     encrypt it as the message-4 frame (keyed by `client_nonce`, via the
     existing `ticket_cipher.encrypt_frame`). Exact field order/delimiter is
     the one item still owed by the protocol-decode note.
  3. For `-update`: store the row and return whatever minimal ack the client
     accepts (it doesn't parse the body, so an empty/short frame is fine).
This is where nearly all remaining work is. It is a modification of an
existing stub, not a new listener.

### (c) A data store for scores - not started
[none] Scores are currently discarded. Recommendation: a small **sqlite**
file keyed by `(board_id, player_name)` holding `score` + the decoded u32
stat array, mirroring how RPCN stores score data structurally (not its code).
Do **not** shoehorn scores into the profile blob store (`catch_http` profile
PUT/GET) - leaderboards are cross-player and queried by rank/range, which the
per-player profile store can't answer. A dozen-line sqlite table is the right
size. Board IDs seen: 404/405/406 (treat board_id as a column, not separate
tables).

### (d) Update path firing at match end - already fires
[done, client side] `leaderboard-update` is emitted live at match end (seen
in the log for both players, multiple boards). Missing only the server side:
persist it (gap c) inside the new handler (gap b.3). No client-side work.

### (e) Auth/signing on leaderboard-update - N/A
[does not exist] The trailing `%s` is a stat blob, not a signature. No
verification to implement; accept updates as-is. (If anti-cheat is ever
wanted it would be a bespoke addition, not something the protocol requires.)

## Recommended implementation path

1. **Extend `ticket_server_stub.py`**, don't write a new server: add a
   `service_name` switch and a `leaderboard-*` verb parser/handler in the
   existing 7320 listener. Everything upstream (redirect, handshake, crypto,
   decrypt) already works.
2. **Store:** one sqlite table `(board_id, player_name, score, stats_blob,
   updated_at)`, unique on `(board_id, player_name)`, upsert on `-update`,
   ordered SELECT on `-get`/`-range`.
3. **Blocker before b can be finished:** the exact `+`-line reply grammar for
   `-get`/`-range` (field order, delimiter, which fields are base64, the
   per-entry record layout the client's 4-symbol/3-byte decoder expects).
   That is the deliverable of the parallel protocol-decode note
   (`research/notes/2026-08-17-leaderboard-server-protocol.md`). Handshake/
   crypto/transport need nothing further from that note.

## Top 3 blockers

1. **Reply-format handler is missing** - stub returns a zero placeholder, so
   boards render empty. Need the `+`-line response builder + a
   `service_name`-branch in `ticket_server_stub.py`.
2. **No score store** - updates are discarded; need a small sqlite table
   (new).
3. **`+`-line reply grammar not yet byte-mapped** - structurally identified
   only; the exact field/delimiter/base64 layout is owed by the
   protocol-decode note before (1) can be finalized.
