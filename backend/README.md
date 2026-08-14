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

Not yet started: build/run instructions, what (if anything) needs patching for Factions specifically, self-hosting setup for local capture/testing.
