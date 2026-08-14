# Captures

Live packet captures against the public RPCN service, taken with Wireshark on the Windows host running RPCS3 (see `docs/capture-howto.md` for the exact procedure). Analysis tooling: `tshark` (installed) and Python `scapy` in a local venv at `tools/.venv/` (gitignored, not committed — recreate with `python3 -m venv tools/.venv && tools/.venv/bin/pip install scapy`).

## Naming

`<date>_<short-description>.pcapng`, e.g. `2026-08-14_matchmaking-and-one-match.pcapng`.

## What to capture

1. RPCN handshake/auth (client connecting to the public RPCN service).
2. Matchmaking — room search/create/join. The interesting unknown here is the binary room-data blobs the game sets via `sceNpMatching2SetRoomDataInternal`/`SetRoomDataExternal` (see `research/notes/clan-tus-commerce-findings.md`) - RPCN relays these without understanding them, so their format is a real RE target.
3. P2P gameplay traffic once matched (the `NetEvent*` protocol - see `protos/common/opcodes.ksy`).
4. Any connection attempts outside RPCN/P2P (possible custom Naughty Dog backend for profile/clan/progression data - see the "working theory" in `research/notes/clan-tus-commerce-findings.md`). These may fail (server presumably dead) but the attempt itself - hostname, port, protocol handshake - is valuable.
