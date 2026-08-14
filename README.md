# TLOU Factions Protocol RE

Reverse-engineering the network protocol of *The Last of Us: Factions* (PS3 multiplayer, title ID `BCUS98174`) from a decrypted `EBOOT.elf`, with the eventual goal of building a modern, self-hosted server. Sony's original servers are gone; this project treats the client as the sole ground truth until a live server is available to test against.

This is a legitimate reverse-engineering / game-preservation effort: the analysis target is a binary the project owner legally owns and runs under [RPCS3](https://rpcs3.net/), a PS3 emulator.

## Status

Groundwork phase — see `docs/protocol/README.md` for the current opcode/packet documentation index and `research/prior-art.md` for what's already known from outside sources. No live capture has happened yet, but numeric IDs for 115 `NetEventType` gameplay opcodes are already confirmed via static analysis — see `protos/common/opcodes.ksy`.

## Layout

- `protos/` — [Kaitai Struct](https://kaitai.io/) `.ksy` files, one per confirmed/in-progress packet type. `protos/common/` holds shared types (opcode enum, packet envelope, primitives). `protos/pending/` holds catalogs of opcodes whose *names* are known (pulled from the binary) but whose numeric IDs/structure aren't confirmed yet.
- `docs/` — methodology, tooling setup, and per-packet semantic documentation (`docs/protocol/`) explaining *why* a field exists, not just its type.
- `research/` — raw and filtered static-analysis output (strings, disassembly, Ghidra project, working notes) and `prior-art.md`.
- `tools/` — helper scripts and external tooling references used for analysis.
- `captures/` — placeholder for future live packet captures. Empty until a capture session happens.

The `EBOOT.elf` itself is never committed to this repo (copyrighted game data) — see `docs/tooling.md` for its fingerprint (SHA256/size) so any session can verify it's working from the same build.

See `CONVENTIONS.md` for naming, commit, and confidence-rating rules.
