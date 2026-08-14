# Session Manager init failure: root-caused, plus the NetMatchmaking opcode table

Follow-up session to the ticket-server work. The live blocker hit right after
ticket-server started succeeding: `g_pSessionManager->Init()() failed. ret =
0xffffffff` / `ERROR NET INIT ffffffff`, preceded by a `recv() failed
(errno=9)` and a 28-line dump of `NetMatchmaking*` name+size debug strings.
Full write-up: `docs/protocol/session_manager_and_matchmaking.md`. This note
is the condensed version + pointers to the raw evidence files.

## The one-line answer

`g_pSessionManager::Init()` opens a brand-new TCP connection to
**`192.168.1.100:7314`** (same redirected host as ticket-server, different
port) that currently has nothing listening on it. `Init()` never checks
whether that connect() succeeded before blindly sending/receiving on the
resulting dead connection object (socket fd `-1`), which is exactly what
produces the observed `errno=9`/`EBADF` cascade. **Nothing here depends on
ticket-server's message D** - ruled out definitively, not just deprioritized.

## How it was found (method notes for next time)

1. The two log strings from the brief (`"g_pSessionManager->Init()() failed..."`
   at VMA `0xe7a320`, `"ERROR NET INIT %x"` at `0xe7a4f8`) both resolve, via
   `FindCallersOf.java`, to exactly one code cross-reference each - and it's
   the *same* function, the already-known `FUN_003557a8` NetInit orchestrator.
   This immediately told us Session Manager init isn't off in some unexplored
   corner of the binary - it's inline in code we'd already partially mapped.
2. Raw disassembly (`DumpRawDisasm.java`) around the string-load site found a
   `bctrl` virtual call (`this->vtable[0](this)`) whose negative return value
   triggers the log - i.e. `Init()` really is a C++ virtual method, matching
   the brief's `->Init()()`-with-double-parens naming (a strong tell it's a
   macro-wrapped virtual dispatch in the original source).
3. New reusable tool: `tools/ghidra_scripts/DumpVtableAt.java` - given a raw
   vtable address, dumps+decompiles N slots (does the PPC32 ABI double-
   dereference through the `.opd` descriptor automatically, same gotcha
   `ResolveNetEventVtables.java` already documented for the gameplay-opcode
   vtables). Used it on the resolved vtable base `0x01243b38` and got 8 clean
   decompiled methods immediately - `Init()`, a receive/dispatch loop, and 6
   more room-management methods.
4. The receive/dispatch loop (vtable `+0x4`, `FUN_00ad7604`) turned out to be
   the real gold: an `if (opcode == 0x131) {...} else if (opcode == 0x132)
   {...}` chain whose literal values, when compared against the 28-entry
   `NetMatchmaking*` name+size table `Init()` logs right before its own
   send/recv, landed EXACTLY on `0x12d + table_index` for all 11 cases decoded
   this pass. That's a mechanically verified opcode table, not a guessed
   pattern - see the doc for the full cross-check.
5. **The single most useful move this pass**: grepping the *live* RPCS3 log
   directly (`/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/log/RPCS3.log`,
   1.5GB, actively growing) for `SessionManager`/`NetMatchmaking`/`connect to`
   instead of only doing static analysis. This surfaced the actual
   `sys_net_bnet_setsockopt(s=-1, ...)` / `-SYS_NET_EBADF` syscall trace
   around the failure - which is what actually nails the root cause (dead
   connection, not a logic bug in Init() itself) rather than leaving it as a
   plausible-but-unconfirmed static hypothesis. Worth remembering as a general
   technique: when a long-running live-test log exists, grep it before
   assuming a question needs a fresh live capture.

## What's genuinely new vs. what's still open

New and solid:
- Root cause of the Init() failure (dead connection to port 7314, unchecked
  connect() return value).
- All 28 `NetMatchmaking*` opcode IDs (`0x12d`-`0x148`) and wire sizes.
- `NetMatchmakingClientHello`/`ServerHello` field layouts (partial - opcode +
  identity-copy fields confirmed, a few bytes each still unconfirmed).
- Confirmed the ticket-server ARX key is reused verbatim (different rodata
  address) for this connection's own handshake.
- Ruled out both "depends on message D" and "RPCN already has this".

Still open, prioritized for whoever picks this up next:
1. Stand up an actual stub listener on port 7314 (this session left the
   "hands off" live-testing files untouched per the task brief).
2. Full field-level `.ksy` schemas for the other 26 `NetMatchmaking*` opcodes -
   11 already have their handler decompiled in
   `research/ghidra/sessmgr_vtable_dump.txt`, ready for a focused pass.
   `RoomCreate`/`RoomJoin`/`RoomJoined`/`Member` are the highest-value targets
   (actual room-formation opcodes).
3. Confirm whether post-handshake `NetMatchmaking*` traffic uses the same
   20-byte encrypt-then-MAC frame header as ticket-server's messages C/D, or
   something simpler.
4. `FUN_00ad55d8` (ServerHello's byte-order fixup) not decompiled - would
   resolve the open endianness question on the opcode fields.

## Raw evidence files from this pass

- `research/ghidra/sessmgr_ctor_decomp.txt` / `sessmgr_ctor_disasm.txt` - the
  SessionManager object's constructor (`FUN_00ad84cc`), showing the 4 embedded
  room-slot sub-objects + 1 control connection.
- `research/ghidra/sessmgr_vtable_dump.txt` - all 8 decompiled vtable methods
  (`Init`, receive/dispatch loop with 11 opcode cases, 6 more room-management
  methods).
- `research/ghidra/sessmgr_init_raw_disasm.txt` - full raw disassembly of
  `Init()` (`FUN_00ad71a0`), used to derive `ClientHello`'s field layout.
- `research/ghidra/netinit_raw_disasm.txt` - raw disassembly of the relevant
  slice of `FUN_003557a8` around the `Init()` call site.
- `research/ghidra/sessmgr_vtable_resolve.txt`, `sessmgr_cipherkey_resolve.txt` -
  TOC-chain resolutions for the vtable base and the reused static key.
- `tools/ghidra_scripts/DumpVtableAt.java` - new reusable script (raw-vtable-
  address version of `ResolveNetEventVtables.java`).
- Live capture: `/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/log/RPCS3.log`,
  around timestamp `5:02:05` in the most recent run in that log (grep for
  `NetMatchmakingClientHello2` to jump straight to the relevant slice - the
  file is 1.5GB and actively written by the live-testing process, so avoid
  `tail`-ing the whole thing).
