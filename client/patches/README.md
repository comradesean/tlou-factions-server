# RPCS3 client patches

Custom RPCS3 patches for The Last of Us (BCUS98174, game ver 01.00, EBOOT hash
`PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6` — the only PPU hash this build
logs, and the same hash the community graphics patches already apply under).

These are **dev/test tooling**, not part of the final product: the shipped
experience keeps the game's real rules (e.g. 6-player find-match minimum);
patches here exist to let two-client testing exercise flows that normally need
a full lobby.

## Files

- `canary_patch.yml` — harmless pipeline test. Rewrites the matchmaking TTY
  string `Searching Game with Criteria %i` → `CANARY OK - Patch is Applied %i`.
  Use it to prove a machine's custom-patch plumbing works (right file location,
  right hash, patch enabled) before trusting any real patch on that machine.
- `minplayers_patch.yml` — TESTING ONLY. Lowers the find-match lobby start
  minimum from the shipped 6 to 2 (one `be32` at VMA `0x003b7ab8`: the sole
  `bl` to the playlist min-players getter becomes `li r3,2`). Install on BOTH
  test machines — either client can be elected host. Full derivation and
  alternative levers (live debugger poke at `0x01385D40`, the game's own
  "Force Matchmaking Min Players" dev setting): see
  `research/notes/2026-08-17-min-players-client-patch.md`.

## Installing on a machine (works for the remote client too)

1. Copy the `.yml` file into the RPCS3 `patches/` folder, next to the existing
   community `patch.yml`, e.g.:

   ```
   cp canary_patch.yml "<rpcs3 folder>/patches/BCUS98174_canary_patch.yml"
   ```

   (Any `.yml` name in that folder works. Alternative: RPCS3 GUI →
   Manage → Game Patches → Import, which appends into `imported_patch.yml`.)

2. In RPCS3: right-click The Last of Us → Manage Game Patches → find
   "TLOU Factions - Canary (custom patch pipeline test)" → tick the checkbox →
   Save.

3. Restart the game (patches apply at boot).

## Verifying the canary took

- **At boot** — RPCS3.log contains a line like:

  ```
  PAT: Applied patch (hash='PPU-9df60dc1…', description='TLOU Factions - Canary (custom patch pipeline test)', …)
  ```

- **In-game** — start Find Match; the TTY diagnostics (sys_tty_write lines in
  RPCS3.log) print `CANARY OK - Patch is Applied 0` instead of
  `Searching Game with Criteria 0`.

Untick the patch and restart to revert; the file writes nothing to disk.

## Address convention

RPCS3 PPU-hash patch addresses are **plain VMAs** — exactly the addresses the
RPCS3 debugger and this repo's research notes use (VMA = EBOOT file offset +
0x10000). No shifting. Verified live: an entry at the file-offset
interpretation reported "Applied" but changed nothing in-game; at the VMA it
works, and the community MLAA entries decode as coherent `lwz → li r0,0`
patches only under the VMA reading. When turning a research-note address into
a patch line, use it as-is.
