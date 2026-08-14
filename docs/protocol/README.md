# Protocol Documentation Index

**Numeric opcode IDs are confirmed** for 115 `NetEventType` values (0-114) — recovered directly from an in-memory enum-to-name table via Ghidra, see `protos/common/opcodes.ksy` and `research/notes/ghidra-opcode-recovery.md`. **Per-opcode wire payload structure is still unconfirmed** — no individual `protos/0x<hex>_<name>.ksy` payload file exists yet, since that needs decompiled serialization code and/or a live capture to correlate against (see `docs/methodology.md`). The project is still in the static-analysis-only phase; no live capture has happened.

Also known: a 38-entry catalog of lobby/match state names (`NET_SM_*`) pulled from the binary's string table, status unconfirmed either way (state-machine states vs. actual wire opcodes) — see `protos/pending/net_sm_states_catalog.md`.

| Opcode (hex) | Name | Status | Confidence | `.ksy` | Doc |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

This table gets a row per opcode once its numeric ID is confirmed and a `protos/0x<hex>_<name>.ksy` file exists.
