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

**Decided (user, based on prior PS3-era server-revival experience): neither.** The project is scoped as **(3) the server-side auth/matchmaking/signaling backbone** - reimplementing what `sceNpMatching2` (rooms) and `sceNpSignaling` (NAT traversal/rendezvous) provide, so real, unmodified PS3 clients can find each other and do their own P2P host-migration exactly as originally designed. Not recreating the client or the host-side gameplay simulation - recreating the *original online experience* faithfully by standing up the backend that brings clients together. This means the `NetEvent*` opcode work (protos/) still matters for understanding/validating what flows over the resulting P2P links, but the actual server build target is the auth/matchmaking/signaling layer, not a game-logic host.

Open implementation question for when backend design starts: build on top of / extend RPCN (which already reimplements the generic PSN layer many PS3 games share), or build an independent backend implementing just what Factions needs directly. Not yet decided.
