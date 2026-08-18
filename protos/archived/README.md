# Archived protos — pending deletion

These are the **peer-to-peer gameplay opcodes** (`NetEventType`, `0x00`–`0x6f`):
in-match state sync sent **client ↔ client**, relayed through the current host
peer over the game's P2P transport — **not** terminated by any server we run.
`netevent_catalog.md` indexes them.

This project's backend only implements the **client ↔ server** wire protocols
(the `0x11_*` sibling servers — ticket / leaderboard / facebook / heartbeat /
single-player — and the `0x12f`–`0x146` session-manager / matchmaking opcodes).
The P2P gameplay layer runs directly between clients via RPCN signaling; our
servers never see it, so these definitions aren't needed to run the server.

Kept here (rather than deleted outright) only as a temporary holding area — safe
to delete once we're sure nothing references them.
