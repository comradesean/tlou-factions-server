# The `*-server` family: sibling services sharing ticket-server's handshake

Companion doc to `docs/protocol/0x11_ticket_server_hello.md`, which fully
maps `ticket-server` (opcode `0x11`, port 7320 in this build's `net1.bin`
config). This doc confirms/refutes whether the five other `*-server` string
literals found alongside `"ticket-server"` in the binary
(`heartbeat-server`, `leaderboard-server`, `invite-server`,
`facebook-server`, `single-player-server`) use the same connect/hello
handshake, per the coordinator's ask this session.

**status: partial** - messages A/B (hello/hello_response) confirmed
identical for four of the five (by construction: literally the same
function, `FUN_00acc424`); `invite-server` confirmed to have **no live code
call site at all** in this build. Post-hello payload shapes documented per
service to the depth time allowed - breadth prioritized over depth per the
coordinator's brief, and see the "Encrypted frame layer" cross-reference
below, which affects every service in this family.

## Method

`FUN_00acc424` (the hello/hello_response handshake function, fully mapped in
the companion doc) is a generic helper that takes the service name as a
plain string argument - not `ticket-server`-specific. Ghidra's reference
manager was used to enumerate every function in the whole binary that calls
it (`research/ghidra/acc424_all_callers.txt`), independently confirming
which services actually have a live, compiled call site (as opposed to just
appearing as an unused string literal):

```
Callers of 00acc424:
  00080594  FUN_00080268     (single-player-server: trophy-unlock notify)
  00353a68  FUN_003538c0     (facebook-server: friends online-status batch)
  00ac1828  FUN_00ac17b0     (facebook-server: NpId lookup/resolve)
  00353d78  FUN_00353cd8     (heartbeat-server)
  00355f84  FUN_003557a8     (ticket-server - see companion doc)
  003aefc8  FUN_003aeee8     (leaderboard-server: batch entry fetch, "+"-line protocol)
  003af8c8  FUN_003af46c     (leaderboard-server: another batch-fetch wrapper)
  003b0abc  FUN_003afb74     (leaderboard-server: another batch-fetch wrapper)
  003b1018  FUN_003b0f6c     (leaderboard-server: main "submit my score" handler)
  007f1ce0  FUN_007f1acc     (single-player-server: save-sync / campaign checkpoint)
  012e97d0  <data ref only>  (the service-descriptor table entry for ticket-server itself)
```

Exactly **10 code call sites**, covering 4 of the 5 sibling names plus
ticket-server. `invite-server` has zero entries in this list.

## `invite-server`: no live call site found - very likely dead/unused in this build

`invite-server`'s string (`0x00e7d0b0`) has exactly **one** cross-reference
in the whole binary (`research/ghidra/sibling_servers_report.txt`,
address `0x01269950`), and it is a **data reference**, not a call site or
even a load-into-register in any function body - i.e. it sits in a table
(almost certainly the same service-descriptor table that holds
ticket-server's own IP/port/name-pointer entry, going by the shape of the
"other" data ref that shows up for every other confirmed-live service too)
but nothing in the compiled code ever reads that particular table slot to
build a connection. Every other sibling has both a data-table entry AND one
or more real code call sites; `invite-server` has only the former.

**Confidence: medium.** This is a real, cheap, mechanically-verifiable
negative result (Ghidra's reference manager finding zero code xrefs is not
a matter of interpretation), but it can't rule out a call reached only
through fully dynamic dispatch (e.g. a function-pointer table walked by
index with no direct reference Ghidra's static analysis would catch) -
considered unlikely given every other sibling in this same family resolves
via a direct, statically-visible literal load, and there'd be no obvious
reason for just one service in an otherwise-uniform family to be wired up
differently. Best read: the invite/friend-invite feature was either never
shipped, or its client-side networking code was cut from this particular
build while the string/table-slot metadata was left in place.

## Messages A/B: confirmed identical for all four live siblings

Because all four call `FUN_00acc424` - the exact same function whose
byte-exact 88-byte hello and 8-byte hello_response the companion doc
verified against raw disassembly - the wire format of messages A and B is
**not independently re-derived per service**; it is the same code producing
the same byte layout, with only the `service_name` field's content
differing. This is about as strong a "shared protocol" claim as static
analysis can produce (stronger than re-deriving each one from scratch and
finding them merely *similar* - they are, byte for byte, the same
function). See `protos/0x11_ticket_server_hello.ksy` /
`_hello_response.ksy` for the full field-by-field evidence, which applies
unchanged.

Per-service IP/port resolution: each call site loads its own
`{ip_ptr, port}` pair from a distinct byte offset within what all evidence
points to being one shared, `net1.bin`-populated service-descriptor
structure (ticket-server: `+0x7c`; heartbeat-server: `+0x48`;
leaderboard-server: `+0x54`, consistently across all four of its call
sites; facebook-server (`FUN_003538c0`): `+0x50`; the other two facebook-
and single-player-server call sites receive an already-resolved
`{ip,port}` pair as a function argument rather than re-reading the table,
so their originating offset wasn't traced this pass). This is consistent
with - but does not independently prove - each service having its own
configured port; only ticket-server's port (7320) has actually been
confirmed live (see `research/notes/net1bin-server-list.md`). **Not
confirmed**: the actual port number for any sibling. Reading `net1.bin`'s
raw binary layout (283,870 bytes, mostly non-text) to pull the real
IP/port table would resolve this but wasn't attempted this pass - flagged
as a next step.

## Encrypted frame layer applies here too

**Important correction relative to how this session first characterized
these services' post-hello traffic** (as "plain ASCII text commands"): all
four services' post-hello sends/receives go through the exact same
`FUN_00acd5f8` (send) / `FUN_00acd568` (recv) wrappers as ticket-server's
message C/D, which - per the major correction in the companion doc's
"Encrypted frame layer" section - wrap every payload in a keyed
encrypt-then-MAC frame (`0x33` magic, pad count, BE length, 16-byte tag,
then encrypted payload), not send it raw. The `sprintf`-built text commands
and `"+"`-prefixed line-based responses described per-service below are the
**plaintext** these functions build/parse - correct as a description of
the logical payload - but that plaintext is not what actually crosses the
wire; it is encrypted first, keyed by the same per-connection rolling
counter (`session_token`/`client_nonce`) as ticket-server's messages C/D.
No sibling's frame layer was independently live-captured this pass (only
ticket-server's message C has a real capture so far); this is a
by-construction inference from shared code, not independent per-service
confirmation.

## Per-service post-hello payload shapes (plaintext, before the frame layer above)

### `heartbeat-server` (`FUN_00353cd8` @ `0x00353cd8`)

Single round trip: after hello/ack, builds one text command via
`FUN_00e46560` (`sprintf`-style, into a 0xfe/254-byte buffer, using a
format string + 2 opaque TOC-loaded args this pass didn't resolve), sends
it (length via `FUN_00e40ad8`, a `strlen`-equivalent - meaning the
plaintext is NUL-terminated ASCII), then a single `FUN_00acd568` receive
call bounded at `0x100` (256) bytes, then closes. No response-parsing loop
- whatever comes back is not inspected by this function beyond the recv
call succeeding. Runs as a dedicated PPU thread spawned specifically for
this exchange (`sys_ppu_thread_exit(0)` at the end), i.e. this looks like a
periodic background keepalive/heartbeat ping, consistent with the name.

### `leaderboard-server` - two distinct sub-protocols, four call sites, same service name

- **`FUN_003b0f6c` (@ `0x003b0f6c`, call site `0x003b1018`)** - "submit my
  score" shape: after hello/ack, copies a trailing player-name-like string
  out of a per-record struct (`FUN_0001fd54`), builds one text command via
  `FUN_00e46560` embedding it, sends, does one bounded `0x100`-byte receive,
  closes. Single round trip, same shape as heartbeat-server.
- **`FUN_003aeee8` (@ `0x003aeee8`, call site `0x003aefc8`), and its two
  thin wrapper/callers `FUN_003af46c`/`FUN_003afb74` (call sites
  `0x003af8c8`/`0x003b0abc`)** - a richer, looped, **line-oriented text
  protocol**: after hello/ack, builds a batch request line listing up to 16
  numeric IDs at a time (`FUN_00e45684`, string-append, looped), sends,
  then loops receiving into a 2048-byte buffer, splitting on `\n`, and for
  any line starting with `+` parses 4 `,`-or-similar-delimited fields via
  `FUN_00e40e58` (a tokenizer) - the 3rd/4th fields undergo a manual,
  hand-unrolled base64-style decode (a 4-symbols-in/3-bytes-out state
  machine keyed off a lookup table, terminating on `=` padding) into a
  fixed-size per-entry record. This is a genuine bulk clan/leaderboard
  roster-fetch protocol - a plaintext line format worth fully specifying in
  a future pass, but out of this pass's depth budget (breadth
  prioritized).

### `facebook-server` - two call sites, both looped line-protocols

- **`FUN_003538c0` (@ `0x003538c0`, call site `0x00353a68`)** - loops in
  batches of up to 127 friend IDs, building a comma-joined ID list per
  batch via `FUN_00e46560`/`FUN_00e45684`, sends, receives up to 2048
  (`0x800`) bytes, and parses `+`-prefixed lines (`FUN_00e40e58`) for a
  single numeric field per friend (looks like an online/offline status
  flag, given the surrounding code path is about clan-member online
  presence, not identity resolution).
- **`FUN_00ac17b0` (@ `0x00ac17b0`, call site `0x00ac1828`)** - sends the
  local player's own `NpId` (`sceNpManagerGetNpId`) first, receives up to
  3072 (`0xc00`) bytes, then loops in batches of 32 friends doing
  `sceNpLookupNpId`-based identity resolution against `+`-prefixed reply
  lines. This looks like the actual Facebook-friend-to-NpId linking
  handshake, distinct from the presence-check above.

### `single-player-server` - two call sites, both single round trip(s)

- **`FUN_007f1acc` (@ `0x007f1acc`, call site `0x007f1ce0`)** - runs
  immediately after `cellSaveDataListSave2`/`AutoSave` calls; builds one
  message via `FUN_00e46670` (a different formatter than `FUN_00e46560`,
  seen elsewhere embedding an `NpId` plus 2 numeric fields), sends, does
  one bounded `0x40` (64)-byte receive, closes. Reads as a campaign
  save/checkpoint sync tied to a specific save slot.
- **`FUN_00080268` (@ `0x00080268`, call site `0x00080594`)** - a
  trophy-unlock event handler (`sceNpTrophyUnlockTrophy` runs immediately
  before); builds and sends a message the same way, receives `0x40` bytes,
  then conditionally (`local_20c != 0xffffffff`) builds/sends/receives a
  **second** `0x40`-byte exchange - looks like an optional follow-up (e.g.
  a "next milestone" or group-progress query) gated on the first reply's
  content.

## What's still open

- Independent live capture/confirmation for any sibling's post-hello frame
  (only ticket-server's message C has one so far).
- Full plaintext field layout for the `"+"`-line-based bulk protocols
  (leaderboard batch-fetch, facebook presence/lookup) - structurally
  identified, not byte-mapped.
- Real port numbers for the four live siblings (only ticket-server's 7320
  is confirmed).
- The exact format strings passed to `FUN_00e46560`/`FUN_00e46670` per call
  site (TOC-resolved addresses, not chased to their string contents this
  pass).

## Confidence summary

| Claim | Confidence | Reason |
|---|---|---|
| `heartbeat-server`, `leaderboard-server`, `facebook-server`, `single-player-server` all use the identical `FUN_00acc424` hello/hello_response (messages A/B) | high | Same function, confirmed via `FindCallersOf` reference enumeration - not re-derived, structurally identical by construction |
| `invite-server` has no live call site in this build | medium-high | Zero code xrefs found via the same mechanical method that found 10/10 real call sites for the others; can't rule out fully-dynamic dispatch |
| Post-hello payloads for all five are wrapped in the same encrypted frame as ticket-server's messages C/D | high (structural), unconfirmed (independently, per-service, live) | Same shared `FUN_00acd5f8`/`FUN_00acb6fc`/`FUN_00acd568`/`FUN_00acbb90` functions confirmed via decompile; no sibling-specific live capture exists yet |
| Per-service plaintext payload shapes (this doc's per-service section) | medium | Structurally traced via decompile (loop counts, buffer sizes, helper functions used) but format-string contents and exact field boundaries not fully resolved |
| Per-service IP/port table offsets | medium | Directly visible in decompile; actual port *values* not decoded from `net1.bin` this pass |

## Deliverables from this pass

- `protos/0x11_heartbeat_server_hello.ksy` / `_hello_response.ksy`
- `protos/0x11_leaderboard_server_hello.ksy` / `_hello_response.ksy`
- `protos/0x11_facebook_server_hello.ksy` / `_hello_response.ksy`
- `protos/0x11_single_player_server_hello.ksy` / `_hello_response.ksy`
- `research/ghidra/sibling_servers_report.txt` - raw decompile dump backing
  the per-service payload descriptions above
- `research/ghidra/acc424_all_callers.txt` - the reference-enumeration
  backing the "10 call sites, invite-server has none" finding
