# Network Topology: Host-Migration P2P, Not Client-Server

Confirmed via strings in `EBOOT.elf` (verified independently against `research/strings/strings_ascii.txt`):

- **Gameplay traffic is direct P2P UDP, not routed through any server**: `[udpp2p] : recv from %s:%d` (offset `0xe698c0`), `bind P2P to localhost:%d:%d ...` (`0xec8578`).
- **NAT traversal/rendezvous goes through Sony's `sceNpSignaling` API**, not custom infra: `sceNpSignalingActivateConnection`, `sceNpSignalingTerminateConnection`, `sceNpSignalingGetConnectionFromNpId`, `sceNpSignalingGetConnectionInfo`, `sceNpSignalingGetPeerNetInfoResult` (offsets `0xec8aa0`-`0xec8e40`). This is Sony's standard PSN hole-punching/mutual-connection-activation facility - it brokers the P2P handshake, then gets out of the way. Already covered by RPCN's reimplementation (see `research/prior-art.md`), same as `sceNpMatching2`.
- **One peer is elected authoritative "host"; the rest are clients of that peer, not of any server** — `g_netGameManager.IsHost()` / `g_matchSession.IsHost()` gate behavior throughout the net code (e.g. `g_matchSession.IsHost() ? NET_SM_SERVER_LOBBY : NET_SM_CLIENT_LOBBY`), matching the earlier-catalogued `NET_SM_CLIENT_CONNECT_TO_HOST` state.
- **Host migration exists** for when the host peer drops: `Host Migrate` / `No Host Migrate` (offsets `0xec8098`/`0xec8088`).

## Why this matters for the project's goal

`sceNpMatching2` (rooms/matchmaking) and `sceNpSignaling` (P2P rendezvous) are the *only* parts of this that ever went through Sony/Naughty Dog infrastructure - both already reimplemented by RPCN. The actual gameplay simulation (the ~115 `NetEvent*` messages in `protos/common/opcodes.ksy`) runs **client-side, on whichever peer is currently "host"** - not on any authoritative server.

This means "build a custom server for Factions" is not the traditional shape of that problem (an authoritative server receiving client input and broadcasting world state). The realistic options are:

1. A headless client that wins host election and runs the real game simulation itself.
2. An external reimplementation of the host-side simulation logic.

**Decided, based on prior PS3-era server-revival experience: neither.** The project is scoped as **(3) the server-side auth/matchmaking/signaling backbone** - reimplementing what `sceNpMatching2` (rooms) and `sceNpSignaling` (NAT traversal/rendezvous) provide, so real, unmodified PS3 clients can find each other and do their own P2P host-migration exactly as originally designed. Not recreating the client or the host-side gameplay simulation - recreating the *original online experience* faithfully by standing up the backend that brings clients together. This means the `NetEvent*` opcode work (protos/) still matters for understanding/validating what flows over the resulting P2P links, but the actual server build target is the auth/matchmaking/signaling layer, not a game-logic host.

**Backend base decided (revised 2026-08-14): fork RPCN, not use it unmodified.** Third-pass finding: the public RPCN service (`np.rpcs3.net`) reset the client's connection 77 times in a single RPCS3 run at irregular intervals - see `research/notes/rpcn-connection-instability.md`. This is unworkable for reliable development/capture, so we forked `RipleyTom/rpcn` to `github.com/comradesean/rpcn`, vendored as a git submodule at `backend/rpcn/` (see `backend/README.md`). Gives us a stable self-hosted instance plus the ability to add whatever Factions-specific extensions turn out to be needed, without depending on the public server's reliability.

On top of that (unchanged), build custom Factions-specific backend services for what RPCN doesn't and can't know about:

- **Character customization / persistent profile data** - evidence: `game/net/net-clan-manager.cpp`, `net-booster-manager.cpp`, `net-buff-manager.cpp`, plus the `cellUserInfo` import (see `docs/tooling.md`). `in-game-commerce.cpp` turned out to be the real-money PSN Store (`sceNpCommerce2`), not a customization-currency system - see `research/notes/clan-tus-commerce-findings.md`.
- **"Experience"/progression** - mechanism not yet confirmed. The initial-pass guess (Sony TUS via `net-tus-variable.cpp`) was falsified - no `sceNpTus*` import exists anywhere in `sceNp`/`sceNp2` (full NID tables dumped and named). Working theory: a custom Naughty Dog HTTP(S) backend (`cellHttp`/`cellSsl`), not any Sony NP storage service - see `research/notes/clan-tus-commerce-findings.md`.
- **Lobby/matchmaking rules specific to Factions** - RPCN hosts rooms mechanically via `sceNpMatching2` (full 29-function API confirmed), but the actual matchmaking criteria, ready-up/team-assignment flow, and room search/attribute data are game-specific and live in `game/net/lobby-flow.cpp` / `net-matchmaking.cpp` / `net-menu-host.cpp` and the `NET_SM_*` state catalog (`protos/pending/net_sm_states_catalog.md`) - need to be understood well enough to replicate whatever the client reads/writes through the opaque `SetRoomDataInternal`/`SetRoomDataExternal` blobs RPCN just relays.

This is the concrete backend scope going forward: forked/self-hosted RPCN (`backend/rpcn/`) + a Factions-specific service covering profile/customization, progression (mechanism TBD), and lobby/matchmaking logic.
