# Glossary

Terms encountered during analysis, defined as we learn them. Add to this as understanding grows — don't let terms go undefined once they're in use elsewhere in `docs/`/`protos/`.

- **LV2** — the PS3's hypervisor/OS kernel. `ELFOSABI_CELL_LV2` (`0x66`) marks an executable built for it.
- **PPU** — PowerPC Processor Unit, the Cell processor's general-purpose core (as opposed to the SPU/synergistic cores). `EBOOT.elf` is PPU code.
- **NID** — Numeric ID: a 32-bit hash PS3 SDK libraries use to identify imported/exported functions in place of a name, since PS3 binaries resolve imports by NID rather than by string. A NID database (name ↔ hash) is required to recover real function names in a stripped binary — see `docs/ghidra-setup.md`.
- **TOC** — Table of Contents: PPC64 ABI's per-module pointer table (held in register `r2`) used for position-independent addressing of globals/functions. Must be set correctly for a decompiler to resolve global/string references — this is why the Ghidra `r2`-unaffected cspec patch matters (see `docs/ghidra-setup.md`).
- **sceNpMatching2** — Sony's PSN "Matching2" API: room-based matchmaking/session service (create/join rooms, room data, in-room messaging). Confirmed (via strings in the binary) to be what Factions' matchmaking/lobby layer is built on top of. Publicly documented by Sony's PS3 SDK and reimplemented server-side by the RPCN project.
- **RPCN** — [RipleyTom/rpcn](https://github.com/RipleyTom/rpcn), a community reimplementation of PSN's online services (matching/rooms, friends, cloud storage) for RPCS3. Handles the generic PSN layer a game rides on; does not implement any given game's own custom gameplay protocol.
- **NetEvent** — the game's own (not Sony's) family of ~116 distinct network message types (`NetEventPlayerMove`, `NetEventEmitProjectileBullet`, etc.), named directly in the binary's string table. Very likely the actual gameplay-protocol opcode set — see `protos/pending/netevent_catalog.md`.
- **NET_SM_** — a ~38-entry family of state names (`NET_SM_SERVER_LOBBY`, `NET_SM_READY_UP`, etc.) — likely the client-side lobby/match state machine's states, not necessarily wire opcodes themselves, though transitions between them are probably synced over the network. Status unconfirmed.
