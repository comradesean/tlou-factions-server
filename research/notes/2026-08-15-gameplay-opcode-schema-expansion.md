# Gameplay opcode (`net_event_type`) schema expansion, second pass

## Goal / starting point

`research/notes/2026-08-14-gameplay-opcode-mapping.md` left 16 of 115
`net_event_type` opcodes with fully confirmed `.ksy` + doc payload schemas -
deliberately the simplest subset (opcodes with **inline construction**,
reachable via a sequential-TOC-slot vtable trick). The other ~82 opcodes
have a dedicated **external constructor function** whose address was known
but whose vtable (and therefore Deserialize/Serialize/Execute) had not been
resolved. Goal of this pass: work through as many of those ~82 as could be
honestly confirmed in one pass, without rushing shallow schemas just to
inflate a count.

## Headline result: the vtable-resolution technique generalizes cleanly

Decompiling a handful of external constructors (`research/ghidra/
batch1_constructors_decomp.txt`) showed they set up the object header the
exact same way the inline trampolines do (base-class vtable pointer written
first, then overwritten by the derived class's own vtable pointer, both
loaded via a TOC-relative offset) - just off a per-compilation-unit named
anchor global (e.g. `PTR_DAT_012fdfa4`) instead of the shared `unaff_r30`
register value used by section 1's inline case. New tool
`tools/ghidra_scripts/ResolveExternalCtorVtables.java` reads the anchor's
own address as a memory cell (its value is the same TOC base pointer used
everywhere else in the binary), applies the constructor's derived-vtable
offset, and does the same PPC32 `.opd`-descriptor double-dereference as
`ResolveNetEventVtables.java` to resolve Deserialize (vtable+0x8), Serialize
(vtable+0xc), and Execute (vtable+0x10). Verified correct by cross-checking
the inherited/shared vtable slots (+0x14/+0x18/+0x1c/+0x20) against the
exact same function addresses confirmed in the first pass, for every one of
27 opcodes checked.

This unblocks the remaining ~57 external-constructor opcodes not covered
this pass (they just need their constructor decompiled to find the
anchor+offset pair, then one `ResolveExternalCtorVtables.java` run) - no
more rediscovery needed, same as the first pass's factory-table finding did
for construction itself.

## Full per-opcode status ledger (this pass)

25 opcodes newly confirmed, `.ksy`-written, `ksc`-validated. All are in
`docs/protocol/net_event_dispatch_and_simple_opcodes.md` section 5 with full
evidence; summarized here:

| Opcode (dec/hex) | Name | Fields | Semantics confidence |
|---|---|---|---|
| 9 / 0x09 | `kill_projectile_throwable` | 1 (u32) | high |
| 12 / 0x0c | `grenade_start_fuse` | 3 (u32, f32, b13) | medium (fuse_time type-only) |
| 21 / 0x15 | `request_interact` | 3 (b13, u32, u32) | medium |
| 25 / 0x19 | `end_interact` | 3 (b13, u32, u32) | medium (1 field unresolved) |
| 27 / 0x1b | `remove_interactable` | 1 (u32) | high |
| 28 / 0x1c | `set_interactable_ammo` | 2 (u32, u32) | high |
| 30 / 0x1e | `signal_respawn_player` | 3 (b13, b1, u32) | medium (1 field unresolved) |
| 32 / 0x20 | `secured_flag_score` | 2 (u32, b13) | high |
| 34 / 0x22 | `stop_pack_or_deploy` | 2 (b13, u32) | low-medium |
| 35 / 0x23 | `spawn_carry_object` | 2 (u32, u32) | low-medium |
| 39 / 0x27 | `npc_kill` | 2 (b32, u32) | low-medium |
| 47 / 0x2f | `revive` | 4 (b1, b13/b32 conditional, b13, b1) | medium |
| 61 / 0x3d | `abort_interact` | 3 (b13, u32, u32) | medium-high (cross-confirmed vs. opcode 21) |
| 76 / 0x4c | `swap_booster` | 4 (b13, b16, b8, b4) | medium |
| 81 / 0x51 | `reset_melee_history` | 2 (b1, b13/b32 conditional) | high |
| 83 / 0x53 | `melee_block` | 2 (b13, u32) | high |
| 95 / 0x5f | `npc_set_host` | 3 (b13, b32, b1) | medium-high |
| 100 / 0x64 | `item_received` | 3 (u32, u32, b1) | low |
| 102 / 0x66 | `increment_score` | 3 (b13, u32, u32) | medium |
| 103 / 0x67 | `set_player_exposed` | 3 (b13, u32, b1) | high (2 of 3 fields) |
| 104 / 0x68 | `add_net_marker` | 3 (b13, u32, u32) | medium |
| 105 / 0x69 | `player_left` | 1 (b13) | high |
| 107 / 0x6b | `kill_all_mines` | 0 (empty payload) | high |
| 109 / 0x6d | `sync_proxy_mine` | 3 (u32, b1, b1) | medium (2 fields unresolved) |
| 111 / 0x6f | `set_weapon_upgrade_level` | 3 (u32, b8, b8) | high |

Attempted and explicitly set aside (not written as `.ksy`, evidence recorded
in the companion doc's new "Set aside this pass" subsection):

- **`sync_stats` (65)** and **`sync_stats_player` (66)** - both real, both
  have their own 1-2 object fields confirmed, but their Deserialize/
  Serialize additionally read/write directly into a large *external*
  stats-manager singleton (a per-category array for `sync_stats`, a
  per-player sub-block for `sync_stats_player`) whose full width isn't
  mapped. Writing a `.ksy` covering only the object's own fields would
  silently truncate real wire bytes, so these were left out entirely rather
  than published as an incomplete parser - matches this project's
  confidence discipline (see `CONVENTIONS.md`). Good target for a dedicated
  "stats sync family" follow-up; likely shares its external structure with
  `increment_tally_stat` (opcode 101, same address neighborhood, not looked
  at this pass).

## New reusable findings (useful for the next pass)

1. **`ResolveExternalCtorVtables.java`** (`tools/ghidra_scripts/`) - see
   above. Args: `outPath name1 anchorAddrHex1 offsetHex1 ...`. The anchor
   address and derived-vtable offset for a given opcode come straight out of
   decompiling its constructor with the existing
   `DecompileByAddresses.java` (find the `puVar2 = PTR_DAT_0xxxxxxx; ...
   uVar1 = *(undefined4*)(puVar2 + -0xYYYY); *param_1 = uVar1;` pattern -
   the *second* assignment to `*param_1`/`*(undefined4*)param_1`, not the
   first, is the derived vtable).
2. **Two new BitStream helper pairs confirmed by direct decompilation**
   (`research/ghidra/batch1_helpers_decomp.txt`):
   - `FUN_00a1add0`/`FUN_00a1b81c` = `ReadFloat`/`WriteFloat` (32-bit IEEE
     single, confirmed by the Serialize side's explicit `(float)` cast
     before the write loop).
   - `FUN_00a1b488`/`FUN_00a1be18` = a 4th equivalent `Read32`/`Write32`
     call-site pair (byte-identical loop shape to the three already known).
     **This directly unblocks `request_ownership` (opcode 72)**, which the
     first pass left out specifically because this pair's width was
     unconfirmed - it's a plain 32-bit read, nothing novel. Not written up
     this pass (wasn't in this batch's opcode list) but ready for the next
     one.
   - Also confirmed: `FUN_00a1ab64` = a new `ReadU8` call-site (paired with
     the already-known `Write8`/`FUN_00a1b6d4` in `swap_booster`'s Serialize),
     and `FUN_00a1b190`/`FUN_00a1b548` = a 3rd equivalent `Read16`/`Write16`
     pair.
3. **A "full 32-bit npc id" pattern distinct from the common 13-bit
   player/entity-index scheme**: both `npc_kill` (39) and `npc_set_host`
   (95) read their npc-id field via the generic `ReadBits(32)` form (not one
   of the dedicated Read32 call sites), and both resolve it through the same
   `FUN_0039e0c8` npc-registry helper - NPCs appear to be consistently
   addressed with a wider id space than players/generic entities.
4. **The "optional compact id" idiom**: `revive` (47) and
   `reset_melee_history` (81) both read a bool immediately before an id
   field, then compute the id's bit-width at runtime from that bool via an
   identical branchless expression (13 bits vs. 32 bits), and both use the
   bool to select between two *different* object-lookup helpers for the
   resulting id - not just a width difference, a genuinely different
   resolution path. Modeled in Kaitai via a leading bool plus two
   mutually-exclusive `if:`-gated sibling fields. Gotcha for whoever writes
   the next one of these: comparing a `b1` field against a bare integer
   literal (`if: some_bool == 1`) fails to compile under `ksc` 0.11 with
   `error: can't compare BitsType1(BigBitEndian) and Int1Type(true)` - use
   `== true` / `== false` instead.
5. **Ghidra project-lock contention with concurrent work**: this
   pass ran alongside the parallel invite-server dead-code
   investigation, which also runs headless Ghidra scripts against the same
   `research/ghidra/tlou_factions.gpr` project. Two `analyzeHeadless`
   invocations against the same project directory can't run concurrently
   (`LockException: Unable to lock project!`) - the fix was just to poll for
   the other process to exit and retry, no corruption or lost work resulted.
   Worth remembering whenever parallel Ghidra work overlaps again.

## What's left as a clean worklist for the next pass

- **~57 external-constructor opcodes not yet touched**, all with known
  object size + constructor address (see
  `research/notes/2026-08-14-gameplay-opcode-mapping.md`'s ledger for the
  addresses) and now a proven, reusable resolution technique
  (`ResolveExternalCtorVtables.java`). No blockers.
- **`request_ownership` (72)** specifically unblocked by this pass's
  `FUN_00a1b488`/`FUN_00a1be18` width confirmation (see above) - should be
  one of the first picked up next.
- **`sync_stats` (65)`/`sync_stats_player` (66)`** need
  `FUN_003e6308`/`FUN_003e6590` (the per-category loop) and
  `FUN_003e628c`/`FUN_003e7a68`/`FUN_003e63f8` (the per-player sub-block)
  decompiled to map the external stats-manager singleton's structure before
  a `.ksy` can honestly cover their full wire payload.
- **`increment_tally_stat` (101)** wasn't looked at this pass but sits in
  the same address neighborhood as the sync_stats family (`0x004092dc`) -
  worth checking whether it shares the same external-structure complication
  before assuming it's a simple opcode.
- **`player_move` (13) / `npc_move` (14)** remain the highest-payoff, hardest
  targets (large objects, 0x370/0x140 bytes) - not attempted this pass
  either, consistent with the first pass's assessment that they deserve a
  dedicated pass of their own.
- The first pass's other leftovers (`message`/45, `event`/46,
  `assign_team`/18, `assign_team_desc`/19, `transfer_ownership`/73) are
  still open and untouched by this pass.

## Files touched in this pass

- New: `protos/0x09_kill_projectile_throwable.ksy`,
  `0x0c_grenade_start_fuse.ksy`, `0x15_request_interact.ksy`,
  `0x19_end_interact.ksy`, `0x1b_remove_interactable.ksy`,
  `0x1c_set_interactable_ammo.ksy`, `0x1e_signal_respawn_player.ksy`,
  `0x20_secured_flag_score.ksy`, `0x22_stop_pack_or_deploy.ksy`,
  `0x23_spawn_carry_object.ksy`, `0x27_npc_kill.ksy`, `0x2f_revive.ksy`,
  `0x3d_abort_interact.ksy`, `0x4c_swap_booster.ksy`,
  `0x51_reset_melee_history.ksy`, `0x53_melee_block.ksy`,
  `0x5f_npc_set_host.ksy`, `0x64_item_received.ksy`,
  `0x66_increment_score.ksy`, `0x67_set_player_exposed.ksy`,
  `0x68_add_net_marker.ksy`, `0x69_player_left.ksy`,
  `0x6b_kill_all_mines.ksy`, `0x6d_sync_proxy_mine.ksy`,
  `0x6f_set_weapon_upgrade_level.ksy` (all `ksc`-validated).
- New tool: `tools/ghidra_scripts/ResolveExternalCtorVtables.java`.
- Extended: `docs/protocol/net_event_dispatch_and_simple_opcodes.md` (new
  section 5 + updated `request_ownership` note in "Ruled out").
- Updated: `docs/protocol/README.md` (net_event_type table rows + summary
  line only - did not touch the sibling-server section, which another
  session was concurrently editing).
- Raw Ghidra evidence: `research/ghidra/batch1_constructors_decomp.txt`,
  `research/ghidra/batch1_vtables.txt` (vtable resolution + Deserialize/
  Serialize decompiles), `research/ghidra/batch1_helpers_decomp.txt`
  (BitStream helper widths), `research/ghidra/batch1_execute_decomp.txt`
  (Execute functions for semantic hypotheses).
