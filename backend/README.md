# Backend

`rpcn/` - our fork of [RipleyTom/rpcn](https://github.com/RipleyTom/rpcn) at `github.com/comradesean/rpcn`, vendored as a git submodule. `origin` points at the fork (push target); `upstream` points at the original repo, fetch-only (push disabled), for pulling in upstream fixes.

## Why forked (not used unmodified)

Originally scoped to use RPCN as-is (see `research/notes/network-topology.md`). Reversed 2026-08-14 after observing the public RPCN service (`np.rpcs3.net`) reset a client's connection **77 times in one session**, at irregular intervals (~1s to ~37min) - see `research/notes/rpcn-connection-instability.md`. Forking gives us: a stable self-hosted instance for development/testing/capture work, and the ability to add whatever Factions-specific extensions turn out to be needed (see `research/notes/clan-tus-commerce-findings.md` for what's still outside RPCN's scope - character customization, progression, clan data).

## Working on the fork

```sh
cd backend/rpcn
git fetch upstream        # pull in updates from RipleyTom/rpcn
git log --oneline -5      # current HEAD
```

Cloning this repo fresh: `git submodule update --init backend/rpcn`.

## What's actually changed vs. upstream

As of `5ff5c6f` (`config: enable trace logging, add comradesean as admin for local dev`), the fork's only divergence from `RipleyTom/rpcn` is local-dev config, not code: `rpcn.cfg`'s `Verbosity` bumped from `Info` to `Trace` (full server-side protocol visibility, used heavily for debugging the initial connection wiring) and `AdminsList` set to `comradesean`. No Factions-specific server-side logic has been added to the fork itself yet — everything Factions-specific so far lives in the standalone stub servers under `tools/` (session manager, ticket, voice, location), which sit alongside RPCN rather than inside it.

## Self-hosting for local capture/testing (working, in daily use)

1. Build and run the fork:
   ```sh
   cd backend/rpcn
   cargo run --release        # reads rpcn.cfg in this directory; listens on Host=0.0.0.0, Port=31313 by default
   ```
2. Point RPCS3 at it instead of the public `np.rpcs3.net` service: in RPCS3's own config (not this repo), set `config/rpcn.yml`'s `Host` field to this machine's address. See `docs/capture-howto.md` for how this fits into the full local-testing setup (RPCN fork + RPCS3's DNS-hook "IP swap list" + `tools/catch_http.py` + the `tools/*_stub.py` servers), and `docs/ghidra-setup.md` for the companion static-analysis environment.
3. With `Verbosity=Trace` in `rpcn.cfg`, the fork's own stdout/log is often sufficient for protocol visibility on anything that goes through RPCN — no packet capture needed for that traffic.

This is what's been running for the live-testing sessions referenced throughout `research/notes/` (auth → lobby → room hosting → loading into a map) — it is not aspirational.
