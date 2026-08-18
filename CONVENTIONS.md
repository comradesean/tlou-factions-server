# Conventions

## Git commits

- Real commits per logical step, conventional-style subjects: `scaffold:`, `research:`, `protos:`, `docs:`, `tools:`.
- Imperative mood, under ~70 chars for the subject line, with a short body explaining *why* when it's not obvious.
- **No footers of any kind.** Specifically: never add `Co-Authored-By: Claude`, `Generated with Claude Code`, or any other tool-attribution/advertisement line to a commit message in this repo. This is a hard rule for every commit, not just ones made by an AI assistant.

## Naming

- Opcode files: `protos/0x<hex>_<snake_case_name>.ksy`, paired with `docs/protocol/0x<hex>_<snake_case_name>.md` (identical basename). Hex width is not fixed — use whatever width the dispatch field is actually confirmed to be; don't invent a width before it's known.
- Flat `protos/` directory — no premature movement/combat/chat subfolders. Only split into subdirectories once address clustering or an actual subsystem boundary is confirmed, via `git mv`.
- `protos/common/opcodes.ksy` is the single source of truth for opcode id → name. Changes to it (adding, renaming, correcting a value) should be their own commit with a message that distinguishes which kind of change it is.

## `.ksy` ↔ semantic doc pairing

Every `protos/*.ksy` file:
- Gets a one-line `doc:` on each field — terse, just enough for the file to be self-explanatory as a parser spec.
- Gets a `doc-ref:` at the `meta` level pointing at its companion doc under `docs/protocol/`.

The companion `docs/protocol/<name>.md` carries the actual evidence — this is where "why", not just "what", lives:
- The decompiled function address(es) that read/write the field.
- A pseudocode/asm excerpt or description of the surrounding logic.
- The specific observed game behavior the field was correlated to (once captures exist).
- `status`: `unconfirmed` / `partial` / `confirmed`.
- `confidence`: `low` / `medium` / `high`, **with the reason stated inline** (e.g. "high — offset matches store instruction at `0x00845120` inside `FUN_00845000`, called from the movement-tick function").

## Versioning across game builds

Don't multiply filenames speculatively (no `_v1`/`_v2` by default). Only introduce a version suffix once a *confirmed* wire-format divergence between builds is found, and state exactly which build/patch introduced it and how that was confirmed. Day-to-day evolution of understanding (partial → confirmed) is tracked via git history and the doc's status/confidence fields, not new files.
