# Protocol Documentation Index

No opcode has a confirmed numeric ID or wire structure yet — this project is still in the static-analysis-only groundwork phase (see `docs/methodology.md`).

What *is* known: a 116-entry catalog of likely gameplay opcode **names** (`NetEvent*`) and a 38-entry catalog of lobby/match state names (`NET_SM_*`), both pulled from the binary's string table. See `protos/pending/netevent_catalog.md` and `protos/pending/net_sm_states_catalog.md`. Neither has a confirmed numeric ID, dispatch width, or field layout yet — that requires either Ghidra decompilation of the dispatch logic (see `docs/ghidra-setup.md`) or a live capture to correlate against.

| Opcode (hex) | Name | Status | Confidence | `.ksy` | Doc |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

This table gets a row per opcode once its numeric ID is confirmed and a `protos/0x<hex>_<name>.ksy` file exists.
