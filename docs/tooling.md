# Tooling & Binary Fingerprint

## EBOOT.elf fingerprint

Path (Windows/RPCS3 install, referenced but never copied into this repo):
`F:\rpcs3_testing\rpcs3-v0.0.41-19598-357b7d44_win64_msvc\games\The Last of Us [BCUS98174]\PS3_GAME\USRDIR\EBOOT.elf`

- SHA256: `2e44426f00fbb13f192548efa27b7101fb71807d3772ee6e3807ff5053fa94ff`
- Size: `20120632` bytes
- `readelf -h`: ELF64, big-endian, `Machine: PowerPC64`, `OS/ABI: <unknown: 66>` (`0x66` = `ELFOSABI_CELL_LV2`, the standard PS3 PPU marker — readelf on this system doesn't know the name but the value confirms a normal PS3 executable), `Type: EXEC`, entry point `0x12a33c8`, 8 program headers, 34 section headers.
- `readelf -S`: all 34 section headers have **blank names** despite a non-empty string table at index 33 (`STRTAB`, 0x14f bytes) — consistent with a stripped retail PS3 build where section name resolution doesn't survive. Full raw output: `research/notes/eboot_fingerprint_raw.txt`.

Any future session should re-verify the SHA256 before assuming findings still apply to the binary in hand.

## Tool inventory (this environment, checked 2026-08-13)

| Tool | Status | Notes |
|---|---|---|
| `powerpc64-linux-gnu-objdump` (binutils 2.42) | present | Used for the full linear disassembly. ~0.3% of instructions (11,176 / 3.7M lines) come back as `.long`/unrecognized — consistent with Cell-specific Altivec instructions (e.g. `lvlx`) that this binutils build doesn't decode. |
| Python `capstone` 5.0.6 (`CS_ARCH_PPC`) | present | Not yet scripted against the binary this session; available for targeted disassembly once specific functions are identified via Ghidra. |
| Ghidra 12.0 (`/mnt/e/ghidra`) | present | Stock install only — no PS3-specific loader by default. See `docs/ghidra-setup.md` for the required setup (found via prior-art search, not yet fully applied — see that doc for what's outstanding and why). |
| `kaitai-struct-compiler` (`ksc`) | present | Used to validate every `.ksy` file in `protos/` compiles cleanly. |
| `git` 2.43.0 | present | Repo initialized this session. |
| `tshark` / `wireshark` / `mitmproxy` | **not installed, deliberately deferred** | No task in the groundwork phase needs live capture. Confirmed available via `apt` (universe component, no extra repo needed) for whenever the capture-session phase starts. |
| `scapy` / `pwntools` (pip) | **not installed, deliberately deferred** | Same reasoning — packet crafting/replay tools with no role until capture/testing exists. |

## Ghidra language/compiler-spec decision

This Ghidra 12.0 install has two ambiguous 64-bit big-endian PowerPC language IDs:
- `PowerPC:BE:64:default` (`ppc_64_be.cspec`) — plain 64-bit addressing.
- `PowerPC:BE:64:64-32addr` (`ppc_64_32.cspec`) — 64-bit registers, 32-bit addressing, Altivec. **This is the correct one** for Cell PPU / PS3 — it matches what the `Ps3GhidraScripts` project (see `docs/ghidra-setup.md`) explicitly documents as required (its README calls it by an older Ghidra alias, `PowerISA-Altivec-64-32addr`; confirmed via `ppc.ldefs` that this is the same `PowerPC:BE:64:64-32addr` entry in this Ghidra version).

Always pin this explicitly (`-processor "PowerPC:BE:64:64-32addr" -cspec default`) rather than relying on auto-detection.
