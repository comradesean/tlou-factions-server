# Ghidra Setup for PS3 Analysis

This Ghidra 12.0 install (`/mnt/e/ghidra`) has no PS3-specific loader out of the box. A prior-art search found [`clienthax/Ps3GhidraScripts`](https://github.com/clienthax/Ps3GhidraScripts) (141 stars, actively describes exactly this use case), cloned locally at `research/tools/external/Ps3GhidraScripts` (gitignored — not vendored into this repo; pinned commit noted below for reproducibility).

Pinned commit: `d7cb6fd33da40e6547a23fa471292a58df54b89b` (2026-07-12).

## What it provides

- `ghidra_scripts/AnalyzePs3Binary.java` — run **before** auto-analysis. Parses PS3-specific ELF info sections, defines imports/exports, resolves import NIDs to real function names via `data/nids.txt` (9,100 entries), sets up the TOC.
- `ghidra_scripts/DefinePS3Syscalls.java` — run **after** auto-analysis. Maps raw syscall numbers to names via `data/syscall.txt` (798 entries) and defines proper function signatures for them.
- In `analyzeHeadless` terms, these map directly onto `-preScript` / `-postScript` — no manual Ghidra GUI step needed.

## Required language/cspec

`PowerPC:BE:64:64-32addr` (compiler spec `default` → `ppc_64_32.cspec`) — confirmed via `ppc.ldefs` to be the modern-Ghidra name for what the project's README calls `PowerISA-Altivec-64-32addr` (an older Ghidra alias). See `docs/tooling.md` for why this one and not `PowerPC:BE:64:default`.

## Two manual setup steps (DONE — applied manually)

Both require writing into the Ghidra install directory (`/mnt/e/ghidra/...`), which is outside this project's directory, so both were applied manually rather than scripted from the repo; verified in place before running analysis (see initial results below). Left here as a reference for setting up a fresh Ghidra install:

1. **Patch the compiler spec.** In `/mnt/e/ghidra/Ghidra/Processors/PowerPC/data/languages/ppc_64_32.cspec`, add `<register name="r2"/>` to the `<unaffected>` list (inside `<default_proto><prototype ...><unaffected>`). Without this, the decompiler doesn't know `r2` (the TOC pointer) survives function calls, which corrupts decompilation of anything that references globals/strings — i.e. most of the interesting code. Back up the original first.
2. **Install the extension** so `AnalyzePs3Binary.java`/`DefinePS3Syscalls.java` can find `data/nids.txt` and `data/syscall.txt` without an interactive file-picker prompt (which can't work in headless mode). Two ways:
   - Copy `research/tools/external/Ps3GhidraScripts/{ghidra_scripts,data,extension.properties}` into `/mnt/e/ghidra/Ghidra/Extensions/Ps3GhidraScripts/` (this repo's local clone already has `extension.properties` fixed — its `@extname@`/`@extversion@` template placeholders were unfilled in the raw clone since it's normally populated by a Gradle build; already patched here to `name=Ps3GhidraScripts` / `version=12.0` to match this install).
   - Or open Ghidra's GUI once and use *File → Install Extension* pointing at a zipped version of the same folder — slower but doesn't require writing into the install directory by hand.

## Headless invocation, once the above is done

```sh
/mnt/e/ghidra/support/analyzeHeadless \
  research/ghidra tlou_factions \
  -import "<path to EBOOT.elf>" \
  -processor "PowerPC:BE:64:64-32addr" \
  -cspec default \
  -preScript AnalyzePs3Binary.java \
  -postScript DefinePS3Syscalls.java \
  -scriptPath /mnt/e/ghidra/Ghidra/Extensions/Ps3GhidraScripts/ghidra_scripts \
  -analysisTimeoutPerFile 7200 \
  -log research/ghidra/analyze.log
```

Realistic runtime: tens of minutes to a few hours on this 20MB stripped binary. Run in the background; it doesn't block anything else.

## Known limitations (from the project's own README, worth remembering)

- Relocations are not processed.
- Some Cell-specific vector instructions (`lvlx` and similar) aren't supported by Ghidra's PowerPC support and may produce broken decompilation locally around their use. This matches what plain `objdump` also showed — 11,176 out of ~3.7M disassembled lines (~0.3%) came back unrecognized, consistent with this exact gap.

## Why this matters for opcode recovery

A raw-`objdump` attempt at cross-referencing the opcode-assert strings came up empty: PPC64/PS3 code loads string addresses via TOC-relative (`r2`-based) or `lis`+`ori` multi-instruction sequences that don't show up as flat address literals in a linear disassembly grep — this needs either Ghidra's decompiler or a scripted Capstone dataflow pass, not manual grepping.

## Initial analysis results (after the setup above was applied)

Setup verified working end-to-end: import + `AnalyzePs3Binary` + full auto-analysis + `DefinePS3Syscalls` completed in ~6 minutes, all 27 PS3 SDK library imports NID-resolved, TOC set correctly, 190/191 syscalls resolved. **NetEventType numeric opcode IDs (0-114) were recovered directly from an in-memory name table** — see `research/notes/ghidra-opcode-recovery.md` for the full method and `protos/common/opcodes.ksy` for the result. The "Opcode" assert strings flagged above as the "highest-value target" turned out to be a false lead (they belong to the audio grain-synthesis subsystem and a script VM, not networking) — the name-table approach is what actually worked. Both are documented in `research/notes/ghidra-opcode-recovery.md` so future work doesn't re-walk the same dead end.

Custom analysis scripts from this pass live in `research/tools/ghidra_scripts/` (this repo, not vendored) and can be rerun cheaply against the existing project without re-importing:

```sh
/mnt/e/ghidra/support/analyzeHeadless research/ghidra tlou_factions \
  -process "EBOOT.elf" -noanalysis \
  -scriptPath /mnt/f/ClaudeHole/tlou_factions/research/tools/ghidra_scripts \
  -postScript <ScriptName>.java [scriptArgs...] \
  -log research/ghidra/<name>.log
```
