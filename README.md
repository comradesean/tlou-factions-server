# TLOU Factions — self-hosted revival server + protocol RE

A self-hosted backend that brings *The Last of Us: Factions* (PS3 multiplayer,
title ID `BCUS98174`) back online under [RPCS3](https://rpcs3.net/), plus the
reverse-engineering research it's built on. Sony's original servers are gone;
this project reconstructs the network backend from a decrypted `EBOOT.elf` and
serves it locally, getting a real client through auth → lobby → hosting/joining a
match → progression, leaderboards, and (in progress) the Facebook clan feature.

This is a legitimate reverse-engineering / game-preservation effort: the analysis
target is a binary the project owner legally owns and runs under RPCS3.

## What you need

- **A machine to run the backend** — Linux, macOS, or Windows (WSL2). Either
  [Docker](https://docs.docker.com/get-docker/), or Python 3.8+ (the servers use
  only the standard library — there is nothing to `pip install`).
- **RPCS3 and your own legal copy of the game** (`BCUS98174`), already set up and
  bootable in RPCS3.
- **The game's content files** (`net1.bin.psarc.crypt` and friends), supplied
  from your own copy — see step 2. These are copyrighted and are **not** shipped
  in this repo.

The backend and RPCS3 can be the same machine or two machines on the same LAN.
If two machines, note the backend's **LAN IP** — you'll point RPCS3 at it.

## 1. Start the backend

The whole backend is one command — no juggling five servers:

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
(:7313).

## 2. Supply the game content (one-time)

The backend serves the game's content-delivery files from
`server/data/served_content/` (gitignored — copyrighted). Place the files from
your own game copy there (`net1.bin.psarc.crypt`, `net10.bin.psarc.crypt`, the
campaign config, etc.); anything not present is fetched from the surviving
upstream S3 buckets automatically where they still respond. How to capture these
from your own client is described in
**[docs/capture-howto.md](docs/capture-howto.md)**.

## 3. Point RPCS3 at your backend

The game reaches its backends by hostname (and a few hardcoded IPs). Redirect
them to your backend machine in **RPCS3 → Configuration → Network → IP/Hosts
switches**. Paste this into that one field, **replacing `192.168.1.100` with
your backend's LAN IP** (use `127.0.0.1` if RPCS3 and the backend are the same
machine). Entries are `hostname=ip` joined by `&&`; `*` is a wildcard.

This is the minimal set — every entry here is confirmed in the server request
logs (five hostnames the game actually fetched, plus the one `net1.bin` server
IP it actually connected to):

```
t1.patch.s3.amazonaws.com=192.168.1.100&&t1.campaign.config.s3.amazonaws.com=192.168.1.100&&t1.final.*.s3.amazonaws.com=192.168.1.100&&s3.amazonaws.com=192.168.1.100&&graph.facebook.com=192.168.1.100&&50.18.104.153=192.168.1.100
```

- The four `*.s3.amazonaws.com` hosts — content-delivery files `http_gateway` serves.
- `graph.facebook.com` — the clan feature's Graph calls (local Facebook stand-in).
- `50.18.104.153` — the ticket/matchmaking server address hardcoded in `net1.bin`;
  redirecting it points those services at your backend without editing `net1.bin`.

### Optional extra entries

Append any of these (each as `&&hostname=192.168.1.100`) as belt-and-suspenders.
They are **not** seen in the current logs, so they're harmless catch-alls rather
than required — add them if a future capture or client build reaches them:

| Entry | Why you might add it |
|---|---|
| `*naughtydog.com` | The game assembles `t1.final.prod.naughtydog.com` at runtime as its "Content Delivery" host (`research/notes/dynamic-hostname-construction.md`); in testing it reached the S3 equivalents above instead. |
| `*naughty-dog.com` | Era-known ND domain (`*.tlou.ps3.naughty-dog.com`); resolves but is dead. |
| `50.18.47.114`, `174.129.210.135` | The other two `net1.bin` fallback server IPs; only `.153` was observed being tried. |
| `api.facebook.com`, `graph-video.facebook.com` | Referenced in the binary's social-sharing / video features; not observed in the Graph flow so far. |

## 4. RPCN and game patches

Two more RPCS3-side pieces — full details in
**[client/README.md](client/README.md)**:

- **RPCN** (NP authentication) — stock RPCN works unchanged, no fork needed;
  use the public service or self-host [RipleyTom/rpcn](https://github.com/RipleyTom/rpcn).
- **Patches** — copy the `patch.yml` files from
  **[client/patches/](client/patches/)** into RPCS3's `patches/` folder and
  enable them (one makes the Facebook connect flow succeed offline; one lowers
  the find-match minimum for 2-client testing).

Then boot the game and go to Factions online.

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
- **`ref/`** — reference material. (Superseded research lives under `research/`,
  e.g. `research/joinparty/`.)

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
