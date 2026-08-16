# TLOU Factions Protocol RE

Reverse-engineering the network protocol of *The Last of Us: Factions* (PS3 multiplayer, title ID `BCUS98174`) from a decrypted `EBOOT.elf`, with the eventual goal of building a modern, self-hosted server. Sony's original servers are gone; this project treats the client as the sole ground truth until a live server is available to test against.

This is a legitimate reverse-engineering / game-preservation effort: the analysis target is a binary the project owner legally owns and runs under [RPCS3](https://rpcs3.net/), a PS3 emulator.

## Status

Protocol RE is well advanced and live infrastructure is up and running — see `docs/protocol/README.md` for the current opcode/packet documentation index and `research/prior-art.md` for what's already known from outside sources.

- All 115 `NetEventType` gameplay opcodes have confirmed numeric IDs and a fully mapped dispatch mechanism (`protos/common/opcodes.ksy`); 41 have fully confirmed wire schemas, most of the rest have a known object size and/or constructor ready for the next pass.
- The ticket-server control channel's encrypt-then-MAC cipher is fully solved (`tools/ticket_cipher.py` decrypts a real captured message and recovers a genuine Sony NP ticket).
- All 28 `NetMatchmaking*` session-manager opcodes (auth handshake, room create/join/search) have confirmed numeric IDs and wire sizes.
- A self-hosted RPCN fork (`backend/`) plus custom stub servers (`tools/`) now get a real RPCS3 client all the way through auth → lobby → hosting/joining a room → loading into an actual map — this is live-tested, not just statically analyzed.
- Current live blocker: the client gets booted back to lobby a few seconds after loading into a map. Undiagnosed as of 2026-08-15 — see `research/notes/` for the latest dated entries.

## Layout

- `protos/` — [Kaitai Struct](https://kaitai.io/) `.ksy` files, one per confirmed/in-progress packet type. `protos/common/` holds shared types (opcode enum, packet envelope, primitives). `protos/pending/` holds catalogs of opcodes whose *names* are known (pulled from the binary) but whose numeric IDs/structure aren't confirmed yet.
- `docs/` — methodology, tooling setup, and per-packet semantic documentation (`docs/protocol/`) explaining *why* a field exists, not just its type.
- `research/` — raw and filtered static-analysis output (strings, disassembly, Ghidra project, working notes) and `prior-art.md`.
- `tools/` — helper scripts and external tooling references used for analysis.
- `captures/` — live packet captures and stub-server runtime logs from live testing (see `captures/README.md`).

The `EBOOT.elf` itself is never committed to this repo (copyrighted game data) — see `docs/tooling.md` for its fingerprint (SHA256/size) so any session can verify it's working from the same build.

See `CONVENTIONS.md` for naming, commit, and confidence-rating rules.
