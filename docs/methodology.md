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

Ghidra decompilation (step 2) is fully unblocked and has been the main driver of progress for weeks — see `docs/ghidra-setup.md`. Combined with string-table recon (`research/prior-art.md`, `research/notes/static-recon-findings.md`), it's carried steps 1-4 a long way: all 115 `NetEventType` gameplay opcodes and all 28 `NetMatchmaking*` session-manager opcodes have confirmed numeric IDs (step 2 done for the whole opcode space), and a growing subset have fully confirmed wire schemas with `.ksy` files and companion docs (steps 4-6 done) — see `docs/protocol/README.md` for the current per-opcode ledger.

Live capture (step 1's "or from an observed byte pattern in a live capture" path, and step 3's "once available" capture cross-reference) is no longer a future unlock either — it's the active daily workflow. A self-hosted RPCN instance plus the custom `server/` backend get a real RPCS3 client through auth, lobby, room hosting, and into an actual loaded match, which is how most of the `NetMatchmaking*` family's live-tested behavior (step 3) got confirmed.

The current bottleneck is diagnosing why the client gets booted back to lobby a few seconds after loading into a map — undiagnosed as of 2026-08-15, with no research notes on it yet. Unblocking it needs a live capture spanning that ~10s window (step 1/3 applied to a specific, not-yet-reproduced-on-record failure), not more static analysis — the relevant opcodes in that path are already ID'd; what's missing is which one(s) actually fire, or fail to, right before the disconnect.
