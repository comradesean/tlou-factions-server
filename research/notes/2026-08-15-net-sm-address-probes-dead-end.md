# NET_SM / party-orchestrator address probes (2026-08-15, 13:15-15:25): dead end, do not re-probe

A follow-up Ghidra session tried to locate the client's network state machine
("NET_SM") and a suspected "party orchestrator" function by guessing
addresses and decompiling/cross-referencing them directly, without first
re-deriving the addresses from a live breakpoint or a confirmed caller chain.
Every address probed in this pass was wrong:

- Addresses guessed for `net_sm_start`, `party_orchestrator`, and
  `choose_host_join` all decompiled to unrelated **Havok physics engine**
  constraint-setup code (`hkpConstraintAtom`, `hkcdStaticTree`, etc.) - not
  networking code at all.
- A later self-check (`sym_check`, `mem_blocks`, `net_sm_refs`,
  `net_sm_refs2`) confirmed the addresses being probed (`0x00e6a890`,
  `0x00e6def8`, `0x00e6ab78`, `0x00e6aa30`, `0x00e6a888`, `0x00e6a88c`,
  `0x00e6a894`, `0x00e6def0`, `0x00e6deec`) sit in `SECTION14`, a read-only
  data section, with **zero cross-references and no data of interest** -
  another confirmation these were the wrong addresses.

No usable finding came out of this thread. The raw dumps (`party_orchestrator.log`,
`ad0fd0.log`, `party_error_refs.log`, `choose_host_join.log`, `net_sm_start.log`,
`full_analysis.log`/`.stdout.log`, `net_sm_refs.log`, `net_sm_refs2.log`,
`sym_check.log`, `mem_blocks.log`, and their `tmp_out/` counterparts) have been
deleted rather than kept as "leads" - they would mislead a future session into
re-investigating addresses already proven wrong.

**How to apply:** if resuming the NET_SM / party-orchestrator investigation,
start over from a live RPCS3 breakpoint or a verified caller chain (the way
`2026-08-15-createparty-trace.md` and
`2026-08-15-room-teardown-and-flag-chain.md` did successfully), not from
guessed addresses. Static analysis on an unverified address guess in this
binary has now produced garbage results twice in one session - treat any
future address-guessing pass the same way: verify the function's actual
behavior (decompile sanity, known-good xrefs) before building any conclusion
on top of it.
