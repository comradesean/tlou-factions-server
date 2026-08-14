# Ghidra Setup Success + Opcode Recovery (session 1, continued)

Follow-up to `research/notes/static-recon-findings.md`, after the user manually applied the two outstanding Ghidra setup steps (cspec patch + extension install documented in `docs/ghidra-setup.md`).

## Setup validation

`analyzeHeadless` import + `AnalyzePs3Binary` + full auto-analysis + `DefinePS3Syscalls` completed successfully in ~6 minutes (not the "hours" worst case). Confirmed:
- 27 PS3 SDK libraries NID-resolved with real function names (`sceNp`: 56 funcs, `sceNp2`: 29 funcs, `sys_net`: 30 funcs, `cellNetCtl`: 7 funcs, etc. - full list in `research/ghidra/analyze.log`).
- TOC/`r2` set correctly to `0x01305870`.
- 190 syscall call sites resolved (1 unmapped: `syscall_988`).
- Ghidra's "Decompiler Switch Analysis" and "Data Reference" analyzers ran, which matters because they resolve PPC64 TOC-relative addressing that a flat `objdump` disassembly can't (see the negative result in `static-recon-findings.md` about why raw grep for the opcode-assert strings' addresses came up empty - this is exactly the gap Ghidra closes).

Custom scripts written this session (kept in `tools/ghidra_scripts/`, part of this repo - not vendored): `DumpOpcodeDispatchEvidence.java`, `ExploreNetEventStructure.java`, `FindNetEventTableRefs.java`, `FindCallersOf.java` (generic, takes a hex address + output path as script args). All run as `-postScript` against an already-imported project via `-process "EBOOT.elf" -noanalysis` (no need to re-import/re-analyze - seconds per run instead of minutes).

## Negative result: the "Opcode" assert strings are not the network dispatcher

Followed up on the top target flagged in `static-recon-findings.md` (`"Out of range Opcode type of 0x%X."` etc.) now that Ghidra can resolve the xrefs `objdump` couldn't. Found exactly one reference to each string (no hidden duplicate copies - string literals are pooled), decompiled the referencing functions:

- `"%s(%d) : Out of range Opcode type of 0x%X."` / `"...Unimplemented Opcode..."` -> both referenced from `FUN_00dd9284` @ `0x00dd9284`, which also references the string `src/common/grains.cpp`. This is Naughty Dog's audio **grain synthesis** engine's own opcode dispatcher (bounds check `bVar1 < 0x35`, i.e. a 54-entry table) - unrelated to networking.
- `"%p:%3u - UNKNOWN OPCODE"` -> referenced from `FUN_009f4c2c` @ `0x009f4c2c`, a 68-case (`bVar4 < 0x44`) indirect-jump dispatcher with `/* WARNING: Could not recover jumptable, too many branches */` - consistent with a general script/bytecode VM interpreter (matches the separate, distinct `"Eval: Unknown opcode"` / `"RunScript: Unknown opcode"` strings noted in the original strings pass), not networking either.

Conclusion: this engine reuses a generic "Out of range/Unimplemented Opcode" assert helper across multiple unrelated opcode-driven subsystems (audio, script VM, and presumably networking too) - finding one instance doesn't mean you've found the network one. Recorded here so a future session doesn't re-chase the same dead end.

## Positive result: NetEventType numeric IDs recovered directly from memory

Instead of chasing the dispatch function, went straight for the enum-to-name lookup table (a common compiler-emitted pattern for debug logging): searched for the string `"NetEventPlayerMove"`, found the single code location that references it (`0x01223914`), then scanned outward from that pointer slot in both directions in 4-byte (32-bit) steps, checking whether each slot's target address contains a printable string.

Result: **116 contiguous, ordered entries** recovered clean - 115 real `NetEventType` values (0-114) plus a `kNumNetEvents = 115` sentinel confirming the count, matching the compiler's own bounds. Table base: `0x012238e0`. Full raw output: `research/ghidra/netevent_structure_report.txt`.

Confirmed (not just inferred) by finding the accessor function that indexes this exact table: `FUN_00388b80(int id) { return table[id]; }` at `0x00388b80` - i.e. `GetNetEventName(NetEventType id)`. This is now encoded as the confirmed `net_event_type` enum in `protos/common/opcodes.ksy`.

One name from the original strings-only catalog (`protos/pending/netevent_catalog.md`) - `NetEventCharacterMove` - is *not* one of these 116 table entries. Not investigated further; likely a related class name rather than a distinct enum value.

## Corroborating (not confirmed) evidence for wire format: 1-byte opcode

Found callers of the `GetNetEventName` accessor: `FUN_00ace694` @ `0x00ace694` and `FUN_00acecd0` @ `0x00acecd0`, both of which read the event id from a queue-node structure via `*(undefined1 *)(*node + 4)` - an explicit single-byte load - before doing the name lookup (see decompiled code in `research/ghidra/callers_of_geteventname_report.txt`). These look like the network event send/receive queue processing loop (heavy use of C++ virtual dispatch through vtable offsets `+0xc`/`+0x10`/`+0x14`, consistent with polymorphic per-event-type handler objects).

This is evidence about the **in-process queue-node representation**, not a confirmed wire format - but since it comfortably fits the observed value range (max 114) and matches the existing `opcode: u1` hypothesis in `protos/common/packet_header.ksy`, it upgrades that field from "unconfirmed guess" to "medium confidence." Full wire-format confirmation still needs a live capture.

## What's next

`FUN_00ace694` / `FUN_00acecd0` are now the top target for a deeper dive (likely candidates for the actual network send/receive queue and/or per-event serialize/deserialize dispatch, given the vtable-based per-event-type handler pattern) - worth decompiling their full callers/callees graph in a future session, ideally cross-referenced against a live capture once one exists.
