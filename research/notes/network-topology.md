# Network Topology: Host-Migration P2P, Not Client-Server

Confirmed via strings in `EBOOT.elf` (verified independently against `research/strings/strings_ascii.txt`):

- **Gameplay traffic is direct P2P UDP, not routed through any server**: `[udpp2p] : recv from %s:%d` (offset `0xe698c0`), `bind P2P to localhost:%d:%d ...` (`0xec8578`).
- **NAT traversal/rendezvous goes through Sony's `sceNpSignaling` API**, not custom infra: `sceNpSignalingActivateConnection`, `sceNpSignalingTerminateConnection`, `sceNpSignalingGetConnectionFromNpId`, `sceNpSignalingGetConnectionInfo`, `sceNpSignalingGetPeerNetInfoResult` (offsets `0xec8aa0`-`0xec8e40`). This is Sony's standard PSN hole-punching/mutual-connection-activation facility - it brokers the P2P handshake, then gets out of the way. Already covered by RPCN's reimplementation (see `research/prior-art.md`), same as `sceNpMatching2`.
- **One peer is elected authoritative "host"; the rest are clients of that peer, not of any server** — `g_netGameManager.IsHost()` / `g_matchSession.IsHost()` gate behavior throughout the net code (e.g. `g_matchSession.IsHost() ? NET_SM_SERVER_LOBBY : NET_SM_CLIENT_LOBBY`), matching the earlier-catalogued `NET_SM_CLIENT_CONNECT_TO_HOST` state.
- **Host migration exists** for when the host peer drops: `Host Migrate` / `No Host Migrate` (offsets `0xec8098`/`0xec8088`).

## Why this matters for the project's goal

`sceNpMatching2` (rooms/matchmaking) and `sceNpSignaling` (P2P rendezvous) are the *only* parts of this that ever went through Sony/Naughty Dog infrastructure - both already reimplemented by RPCN. The actual gameplay simulation (the ~115 `NetEvent*` messages in `protos/common/opcodes.ksy`) runs **client-side, on whichever peer is currently "host"** - not on any authoritative server.

This means "build a custom server for Factions" is not the traditional shape of that problem (an authoritative server receiving client input and broadcasting world state). The realistic options are:

1. **A headless client that wins host election** and runs the real game simulation itself (essentially running the actual client logic without the graphics/audio it doesn't need) - would inherit correctness from the real implementation, but means reverse-engineering / hosting the actual simulation code, not just a protocol.
2. **An external reimplementation of the host-side simulation logic** - a from-scratch server that speaks the `NetEvent*` protocol from the *host* role, driven entirely by our own understanding of the game rules - harder, but doesn't depend on running the real client's code.

Not a decision to make now - flagging it here because it changes what "done" looks like for this whole project, and should be settled explicitly before deep server-implementation design work starts (it doesn't change anything about the current groundwork: opcode/protocol documentation is needed either way).
