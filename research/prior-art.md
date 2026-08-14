# Prior Art

Checked 2026-08-13, via web search. Should be re-checked periodically — PS3 homebrew/RE communities are active.

## TLOU Factions protocol RE specifically

**Nothing found.** No GitHub repo, forum thread, or published packet dump specifically documenting TLOU Factions' game protocol turned up in general search, `site:github.com` search, or a title-ID-specific search (`BCUS98174`). This matches the user's own experience — they describe this as consistent with their prior similar projects: prior art on the *specific game protocol* is essentially never available, and the actual working method is pulling client↔server packet mappings directly out of the EBOOT via RE. This is exactly the approach this project is taking.

## The "Nomad" fan reimplementation

No public repo/docs found under that name for a TLOU-specific PS3 online reimplementation. Per the user, it exists but is currently access-gated (~12 days out as of 2026-08-13). Not actionable right now; revisit once access opens.

## RPCN — the underlying PSN reimplementation layer

[RipleyTom/rpcn](https://github.com/RipleyTom/rpcn) — a community reimplementation of PSN's online services (rooms/matchmaking, friends, title user storage) for RPCS3, actively maintained, with public source and a compatibility list (`wiki.rpcs3.net/index.php?title=RPCN_Compatibility_List`). This matters because static string recon this session (see `research/notes/static-recon-findings.md`) confirmed Factions' matchmaking/lobby layer is built on Sony's `sceNpMatching2` API — the exact layer RPCN reimplements. This means:
- The matchmaking/room/session layer is likely *not* a Factions-specific custom protocol at all — it's the well-documented, publicly-known `sceNpMatching2` API, which RPCN already serves.
- The actual reverse-engineering target is narrower than "the whole online layer" — it's specifically the game's own payload data carried through that layer (room messages / binary attributes) plus whatever separate direct-connection protocol carries real-time gameplay traffic (movement, combat, etc. — the `NetEvent*` family, see `protos/pending/netevent_catalog.md`).
- Per the user: RPCN has never been a blocker on their past similar projects, and if it ever is, the source is available to patch directly. Not treated as a risk for this project.

## Ghidra PS3 support

[`clienthax/Ps3GhidraScripts`](https://github.com/clienthax/Ps3GhidraScripts) — directly fills the "no PS3 loader in stock Ghidra" gap identified during recon. NID resolution (9,100-entry database), syscall naming (798-entry database), TOC setup, PS3 ELF info-section parsing. Cloned locally (gitignored, not vendored — see `docs/ghidra-setup.md` for the pinned commit and setup steps, two of which are still outstanding pending a permission grant to modify the Ghidra install itself).

Other PS3 Ghidra projects surfaced but not investigated further (Ps3GhidraScripts looked like the most complete/relevant match): `zecoxao/ps3_ghidra`, `aerosoul94/GhidraSPU`, `bevanweiss/GhidraSPU` (SPU-focused, not relevant to PPU analysis).

## What this changes about the plan

Static string recon alone (no disassembly/decompilation needed) already answered several of the open questions the groundwork plan expected to need Ghidra for — see `research/notes/static-recon-findings.md`. The next real unlock is still Ghidra decompilation (for numeric opcode IDs and field layout), but the *shape* of the protocol (matchmaking via sceNpMatching2/RPCN, ~116 named gameplay events, a sequenced/acked custom transport layer) is already reasonably well understood before writing a single line of capture code.
