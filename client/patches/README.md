# RPCS3 client patches

Custom RPCS3 patches for The Last of Us (BCUS98174). Both patch files carry
entries for TWO game versions; RPCS3 applies whichever matches the booted
build, so the same file can be installed everywhere.

| game ver | EBOOT hash |
|---|---|
| 01.00 | `PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6` |
| 01.11 | `PPU-120fb71f7352d62521c639b0e99f960018c10a56` |

The 01.11 addresses were ported by SIGNATURE, not by applying an offset delta -
1.11 is a recompile, and it even reorders the Facebook gate's prologue. Each
port was confirmed against a property that holds independently in both binaries
(the min-players getter having exactly one call site; the app-id construction
occurring exactly once; the object layout the Facebook patch writes into). The
1.11 hash was identified from `ppu_loader` log lines by matching all six logged
section addresses and sizes against the 1.11 ELF's own section table. Derivation
detail is in the comment blocks inside each `.yml`.

## Files

- `facebook_stub_patch.yml` — makes the in-game "Connect to Facebook" flow work
  against the local server. Entry 1 forces the `sceNpSns` sign-in to succeed with
  a stub token (skipping the dead Sony NP path); entries 2–3 rewrite the Facebook
  Graph URLs from `https://` to `http://` so they route to the local stand-in
  served by `http_gateway`. See
  `research/notes/2026-08-17-facebook-connect-flow.md`.
- `minplayers_patch.yml` — TESTING ONLY. Lowers the find-match lobby start
  minimum from the shipped 6 to 2 (one `be32`: the sole `bl` to the playlist
  min-players getter becomes `li r3,2` — VMA `0x003b7ab8` on 01.00,
  `0x003d1d18` on 01.11). Install on BOTH test
  machines — either client can be elected host. Full derivation and alternative
  levers (live debugger poke at `0x01385D40`, the game's own "Force Matchmaking
  Min Players" dev setting): see
  `research/notes/2026-08-17-min-players-client-patch.md`.

## Installing on a machine (works for the remote client too)

1. Copy the `.yml` file into the RPCS3 `patches/` folder, next to the existing
   community `patch.yml`, e.g.:

   ```
   cp facebook_stub_patch.yml "<rpcs3 folder>/patches/BCUS98174_facebook_stub_patch.yml"
   ```

   (Any `.yml` name in that folder works. Alternative: RPCS3 GUI →
   Manage → Game Patches → Import, which appends into `imported_patch.yml`.)

2. In RPCS3: right-click The Last of Us → Manage Game Patches → tick the patch's
   checkbox → Save.

3. Restart the game (patches apply at boot). Confirm at boot — RPCS3.log contains
   a line like:

   ```
   PAT: Applied patch (hash='PPU-9df60dc1…', description='…', …)
   ```

   Untick and restart to revert; the patches write nothing to disk.

## Address convention

RPCS3 PPU-hash patch addresses are **plain VMAs** — exactly the addresses the
RPCS3 debugger and this repo's research notes use (VMA = EBOOT file offset +
0x10000). No shifting. Verified live: an entry at the file-offset interpretation
reported "Applied" but changed nothing in-game; at the VMA it works, and the
community MLAA entries decode as coherent `lwz → li r0,0` patches only under the
VMA reading. When turning a research-note address into a patch line, use it as-is.
