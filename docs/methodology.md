# Methodology

## Goal

Every packet/opcode ends up as a `.ksy` file under `protos/` with a paired semantic doc under `docs/protocol/` that explains *why* a field exists — what decompiled game logic reads/writes it and what game behavior it corresponds to — not just its wire type. "Field 3 is a float" is not an acceptable end state; "field 3 is the player's aim pitch in radians, read by `FUN_00845000` (`game/net/net-event/net-event-player-move.cpp`) and fed into the camera-follow system" is.

## Workflow for documenting one opcode

1. **Identify the opcode exists.** Either from a static source (a name string, a dispatch table entry — see `protos/pending/` for the current catalog of known-but-unmapped names) or from an observed byte pattern in a live capture.
2. **Determine numeric ID and wire structure.** From the binary's dispatch/switch logic (via Ghidra decompilation — see `docs/ghidra-setup.md`) and/or from captured bytes once captures exist.
3. **Hypothesize field meanings.** Cross-reference: decompiled read/write sites for each field, the surrounding function's name/logic, and (once available) the specific in-game action that was being performed when a given capture was taken.
4. **Write the `.ksy`.** Structural spec under `protos/`, one-line `doc:` per field, `doc-ref:` pointing at the companion doc.
5. **Write the companion doc.** Evidence, confidence rating, and reasoning — see `CONVENTIONS.md` for the exact fields required (`status`, `confidence` + reason).
6. **Update the index.** `docs/protocol/README.md` gets a row for the new opcode.
7. **Validate.** Run `ksc` against the `.ksy` to make sure it compiles.

## Confidence discipline

Never write a numeric opcode ID or field offset into a `.ksy` file based on a guess. If it isn't confirmed by disassembly/decompilation or by direct byte-level evidence from a capture, it belongs in `protos/pending/` (a plain catalog, not a `.ksy`) with a note on what's missing to confirm it — not in `protos/` dressed up as settled fact.

## Current phase

Static-analysis-only (no live capture yet). String-table recon of the binary already surfaced a large amount of ground truth cheaply — see `research/prior-art.md` and `research/notes/static-recon-findings.md` — before any disassembly/decompilation was needed. The next unlock is Ghidra decompilation (blocked this session on a permission boundary around modifying the Ghidra install itself — see `docs/ghidra-setup.md` for the two manual steps needed and exactly what they unlock).
