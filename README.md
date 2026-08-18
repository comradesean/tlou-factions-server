# TLOU Factions — self-hosted revival server + protocol RE

A self-hosted backend that brings *The Last of Us: Factions* (PS3 multiplayer,
title ID `BCUS98174`) back online under [RPCS3](https://rpcs3.net/), plus the
reverse-engineering research it's built on. Sony's original servers are gone;
this project reconstructs the network backend from a decrypted `EBOOT.elf` and
serves it locally, getting a real client through auth → lobby → hosting/joining a
match → progression, leaderboards, and (in progress) the Facebook clan feature.

This is a legitimate reverse-engineering / game-preservation effort: the analysis
target is a binary the project owner legally owns and runs under RPCS3.

## Quick start (run the backend)

The whole backend is one command — no more juggling five servers:

```sh
# Docker (recommended):
docker compose up

# — or, without Docker (identical behavior):
sudo ./run.sh            # foreground, Ctrl-C stops all  (sudo: http_gateway binds :80)
./run.sh -d              # background; logs in server/logs/
./run.sh stop            # stop background servers
```

This starts all five servers: `http_gateway` (:80, S3 content + Facebook Graph),
`ticket_server` (:7320, NP ticket + leaderboard + facebook-server),
`session_manager` (:7314, matchmaking), `location_server` (:7312), `voice_server`
(:7313). Then point RPCS3 at them — see **[client/README.md](client/README.md)**
for the IP/Hosts switches, RPCN, and game-patch setup.

## Layout

- **`server/`** — the revival server (the product). `*.py` servers, `lib/` shared
  modules (ticket cipher, profile/psarc crypto), `data/` runtime data (S3 mirror,
  player profiles, leaderboard DB, Facebook assets). `run_all.py` supervises all.
- **`client/`** — player-side RPCS3 setup: `patches/` (game `patch.yml` files) and
  the setup guide.
- **`research/`** — the reverse-engineering work: `notes/` (dated findings),
  `strings/`, `ghidra/`, and `tools/` (the raw-EBOOT analysis toolkit, Ghidra
  scripts, capture/patch utilities).
- **`protos/`** — [Kaitai Struct](https://kaitai.io/) `.ksy` files, one per packet
  type. `docs/` — methodology + per-packet semantic docs (`docs/protocol/`).
- **`ref/`**, **`archive/`**, **`captures/`** — reference material, quarantined old
  investigations, and live logs.

The `EBOOT.elf` itself is never committed (copyrighted game data) — see
`docs/tooling.md` for its fingerprint. RPCN is **not** vendored here: stock
[RPCN](https://github.com/RipleyTom/rpcn) works unchanged (see client setup).

## Status

Live infrastructure is up: auth → lobby → hosting/joining a matchmade game →
played to the win condition → **progression credited** (supplies/rank increment
on screen, profile persisted); leaderboards render and update; profile
round-trips to the S3 mirror. Facebook clan-naming is the current work in
progress. See `docs/protocol/README.md` for the opcode/packet index and
`research/notes/` for the latest dated entries.

See `CONVENTIONS.md` for naming, commit, and confidence-rating rules.
