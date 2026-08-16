# Directionality pass: `sync_stats`/`sync_stats_player` numeric IDs, and why they (and the whole `net_event_type` family) never reach a server we operate

Written while adding a `direction:` field to every `.ksy` across all three
opcode families (see `docs/protocol/README.md` and each family's companion
doc for the resulting per-opcode ledger). Two things fell out of that pass
that are worth recording on their own:

## 1. `sync_stats`/`sync_stats_player` numeric ID correction

`docs/protocol/net_event_dispatch_and_simple_opcodes.md`'s "Set aside this
pass" section (and `research/notes/2026-08-15-gameplay-opcode-schema-expansion.md`)
both parenthesize these as `sync_stats (65)` / `sync_stats_player (66)` -
**decimal** values, matching `protos/common/opcodes.ksy`'s enum
(`65: sync_stats`, `66: sync_stats_player`). In hex that's **`0x41`/`0x42`**,
NOT `0x65`/`0x66` - `0x65` hex is decimal 101, which in the enum is
`increment_tally_stat`, a different opcode entirely. Double-checked directly
against `protos/common/opcodes.ksy` (the single source of truth per
`CONVENTIONS.md`) to be sure: confirmed `65: sync_stats  # NetEventSyncStats`
and `66: sync_stats_player  # NetEventSyncStatsPlayer` are the correct
decimal/name pairing. Any future note or doc referring to these by hex must
use `0x41`/`0x42`.

## 2. Are they P2P-only, or do they ever reach a server we'd operate?

**Conclusion: P2P-only. They never reach any server this project operates or
could operate**, and mapping their external stats-manager-singleton payload
is therefore not "the server's duty" under the project's current decided
scope (auth/matchmaking/signaling backbone, not gameplay-simulation
reimplementation - see `research/notes/network-topology.md`).

Reasoning: `sync_stats`/`sync_stats_player` are ordinary `NetEventType`
values (65/66 of 0-114), dispatched through the exact same mechanism as
every other opcode in that enum - the 115-entry allocator jump table at
`0x0038ec40` documented in `docs/protocol/net_event_dispatch_and_simple_opcodes.md`.
`research/notes/network-topology.md` already established, from direct string
evidence in the EBOOT (`[udpp2p] : recv from %s:%d`, `bind P2P to
localhost:%d:%d`, the `sceNpSignaling*` NAT-traversal API family, and
`g_netGameManager.IsHost()`/`g_matchSession.IsHost()` gating) that **all**
`NetEventType` gameplay traffic is direct P2P UDP between game clients,
relayed through whichever peer currently holds "host" status via Sony's
`sceNpSignaling` rendezvous - not routed through any server infrastructure at
all, ours or Naughty Dog's. That finding was general (it covers "the ~115
`NetEvent*` messages" as a whole) but didn't call out `sync_stats`/
`sync_stats_player` by name; this note closes that gap explicitly for the
two opcodes flagged as set-aside/high-value in the 2026-08-15 schema pass.

Nothing about `sync_stats`/`sync_stats_player` specifically contradicts or
carves an exception into the general finding - they're dispatched, allocated,
and Deserialize/Serialize'd through the identical per-opcode trampoline
mechanism as every confirmed opcode already in the P2P-relayed table (e.g.
`kill_entity`, `player_left`), just with a larger, not-yet-fully-mapped
payload (the external stats-manager singleton reads noted in
`docs/protocol/net_event_dispatch_and_simple_opcodes.md`). There is no
separate stats-reporting-to-a-server code path found anywhere in this
opcode's Deserialize/Serialize/Execute trio - if one existed, it would need
its own distinct opcode/dispatch path outside the `net_event_type` P2P
envelope, which nothing in the decompiled trampoline/dispatch table
supports.

**Practical implication:** finishing the `sync_stats`/`sync_stats_player`
external-singleton field mapping only matters for a full client-side/host-side
gameplay-simulation reimplementation (the options this project's owner
explicitly declined in favor of the auth/matchmaking/signaling backbone scope
- see `research/notes/network-topology.md`'s "Decided" note). It is not
required to stand up the server backbone and is not on this project's current
critical path. Left as a legitimate future target (per the schema-expansion
note) but re-scoped here as "useful for a client/host reimplementation",
not "a server responsibility".

## Where this is reflected

- `docs/protocol/README.md`'s `net_event_type` table now carries a top-of-section
  note stating the family is peer-to-peer/host-relayed rather than a
  Direction column of server↔client values (forcing 115 P2P opcodes into
  that framing would misrepresent the evidence - see the README for the exact
  wording).
- Every confirmed `net_event_type` `.ksy` (41 files) now states this in its
  own `doc:` block as a `Direction: peer-to-peer (...)` line, consistent with
  the `direction:`-field pass done across all three families this session.
