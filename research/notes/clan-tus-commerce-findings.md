# Clan / TUS / Commerce Dig (second pass)

Follow-up on `net-tus-variable.cpp`, `net-clan-manager.cpp`, `net-booster-manager.cpp`, `net-buff-manager.cpp`, `in-game-commerce.cpp`.

## sceNp2 is entirely sceNpMatching2 - full API surface confirmed

Dumped the raw NID table for the `sceNp2` import (29/29 functions, all resolved - none unnamed). It is **100% `sceNpMatching2`**, nothing else. Full list: `research/ghidra/clan_booster_decompile_report.txt`. This is the exact matchmaking API surface the game uses - directly relevant to the RPCN-based matchmaking backend:

Context/lifecycle: `CreateContext`, `DestroyContext`, `CreateServerContext`, `DeleteServerContext`, `ContextStartAsync`, `AbortContextStart`, `ContextStop`, `Init2`, `Term2`, `RegisterContextCallback`.
Rooms: `SearchRoom`, `CreateJoinRoom`, `JoinRoom`, `LeaveRoom`, `KickoutRoomMember`, `GrantRoomOwner`.
Room data: `SetRoomDataInternal`, `SetRoomDataExternal`, `SetRoomMemberDataInternal`, `GetWorldInfoList`, `GetServerInfo`, `GetServerIdListLocal`, `SetDefaultRequestOptParam`.
Events/messages: `GetEventData`, `ClearEventData`, `RegisterRoomEventCallback`, `RegisterRoomMessageCallback`.

**Implication:** the internal/external room data set via `SetRoomDataInternal`/`SetRoomDataExternal` (opaque binary blobs to RPCN - it just relays them) is where Factions' own matchmaking criteria (game mode, map, skill, party info) almost certainly lives. That binary format is a real RE target once we can capture it - RPCN will pass it through unmodified since it doesn't need to understand it, so this is a case where live capture *is* worth doing even though we're not reimplementing the Matching2 protocol itself.

## sceNp (main library) - full API surface, and TUS hypothesis falsified

Also fully resolved, 56/56 named. Full list: `research/ghidra/scenp_nid_table.txt`. Covers: `sceNpManager*` (auth/session/ticket), `sceNpBasic*` (friends, presence, messaging, invitations), `sceNpSignaling*` (P2P NAT traversal, confirmed earlier), `sceNpLookup*` (title/transaction context), `sceNpProfileCallGui`, `sceNpUtilCmpNpId`, `sceNpDrmIsAvailable[2]`, and exactly one Score function: `sceNpScoreInit`.

**No `sceNpTus*` function appears anywhere in either `sceNp` or `sceNp2`.** This falsifies the earlier assumption (initial pass) that `net-tus-variable.cpp` backs onto Sony's Title User Storage service - it doesn't seem to be imported at all. "TUS" in that filename is very likely Naughty Dog's own internal abbreviation for something else, not Sony's `sceNpTus`. Whatever persists player stats/experience, it is not going through Sony's TUS API.

`sceNpScoreInit` being the *only* Score function imported (no `sceNpScoreRegisterScore`/`GetRanking`/etc.) suggests Score is barely used, if the game uses it for anything beyond a token initialization - not a strong lead for progression storage either.

## Working theory: progression/clan data goes through a custom Naughty Dog backend, not Sony NP storage

Given both plausible Sony storage mechanisms (TUS, and broad Score usage) are ruled out, and `cellHttp`/`cellSsl` are imported (6+3 functions - real, if small, HTTPS capability), the more likely picture: character customization, clan, and progression/experience data are persisted through Naughty Dog's **own backend**, reached via `cellHttp`/`cellSsl`, not through any Sony NP storage service. This is consistent with the internal build-infra hostnames found in the initial pass (`mysql-dog.naughtydog.com`, `postal-dog.naughtydog.com`) suggesting ND ran custom backend infrastructure, though those specific hostnames are almost certainly internal/build-only, not the production API host.

**Not yet confirmed** - this is the current best-supported theory, not a proven fact. The actual production API host/protocol is still unknown; worth specifically watching for during a live capture (DNS-redirect + logging relay, even without a real response, would reveal what host/port/handshake the client attempts).

## in-game-commerce.cpp corrected: this is the PSN Store, not a custom currency system

The single surviving debug-string reference to `in-game-commerce.cpp` is inside `FUN_00357964`, which is a heavy caller of `sceNpCommerce2*` functions (`GetProductInfoStart/CreateReq/GetResult`, `CreateSessionStart/Finish`, `GetGameProductInfo`, etc.). **Correction to the initial pass's framing:** this file is about real-money PSN Store purchases (DLC), not an in-game points/customization currency. Sony's own commerce service, not something this project needs to reimplement for core gameplay/customization - lower priority, likely out of scope entirely.

## Clan/booster/buff manager: function inventory recovered, bodies still opaque

`net-clan-manager.cpp` (10 functions), `net-booster-manager.cpp` (17 functions), `net-buff-manager.cpp` (1 function) - addresses catalogued in `research/ghidra/tus_clan_dig_report.txt`, all decompiled in `research/ghidra/clan_booster_decompile_report.txt`. None of them directly call any of the now-named `sceNp`/`sceNp2` functions - they're lower-level data manipulation, likely called *by* higher-level code that does the actual network I/O (not yet located). Their decompiled bodies are raw pointer arithmetic with no recovered struct/variable names (same opacity as `FUN_00ace694` in the initial pass) - meaningfully reading them needs either manual struct/type recovery in the Ghidra GUI (a human-in-the-loop task, not efficiently scriptable) or correlation against live capture data to anchor field meanings empirically. Deferred until capture data exists, per `docs/methodology.md`.
