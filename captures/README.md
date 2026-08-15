# Captures

Primary method (session 3+, in daily use): a **self-hosted RPCN fork** (`backend/rpcn/`, `Verbosity=Trace` in `rpcn.cfg`) plus custom stub servers (`tools/*_stub.py` — session manager, ticket, voice, location). Between them these give full server-side protocol visibility for anything that routes through RPCN or one of the stubs, without needing a packet capture at all — see `backend/README.md`'s "Self-hosting for local capture/testing" section for the run steps. Pure pcap capture against the public RPCN service was the original method but turned out unreliable as a primary source (see `research/notes/rpcn-connection-instability.md`); it's now secondary, for the traffic RPCN-side logging can't see.

This directory currently holds the stub servers' own stdout/log output (e.g. `session_manager_stub.stdout.log`, `http_catch.log`, `tcp_catch.log`), not `.pcapng` files — those are gitignored (`captures/*.log`), kept locally for reference during a session rather than committed. No `.pcapng` has been captured yet under this project's current phase.

## When a packet capture (Wireshark/pcap) is still useful

RPCN's own trace log covers `NetMatchmaking*`/session-manager traffic and RPCN-side auth — no capture needed for that. A capture is still the right tool for:

1. **The game's own non-RPCN backend calls** — caught via RPCS3's DNS-hook "IP swap list" redirecting to `tools/catch_http.py` or similar (see `docs/capture-howto.md`'s "Superseded/complemented by" section), not RPCN traffic at all.
2. **P2P gameplay traffic once matched** (the `NetEvent*` protocol — see `protos/common/opcodes.ksy`) — this never touches RPCN or the stubs, it's direct client-to-client UDP.
3. **The binary room-data blobs** the game sets via `sceNpMatching2SetRoomDataInternal`/`SetRoomDataExternal` (see `research/notes/clan-tus-commerce-findings.md`) — RPCN relays these without understanding them, so their format is still a real RE target even though the surrounding handshake is now visible via RPCN's trace log instead.
4. **Any connection attempt outside RPCN/P2P/DNS-hook coverage** (possible custom Naughty Dog backend for profile/clan/progression data — see the "working theory" in `research/notes/clan-tus-commerce-findings.md`).

See `docs/capture-howto.md` for the full Wireshark procedure if one of the above calls for an actual pcap.

## Naming

If a `.pcapng` capture is taken: `<date>_<short-description>.pcapng`, e.g. `2026-08-14_matchmaking-and-one-match.pcapng`. Analysis tooling: `tshark` (installed) and Python `scapy` in a local venv at `tools/.venv/` (gitignored, not committed — recreate with `python3 -m venv tools/.venv && tools/.venv/bin/pip install scapy`).
