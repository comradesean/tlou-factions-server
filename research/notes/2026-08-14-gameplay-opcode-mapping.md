# Gameplay opcode (`net_event_type`) dispatch + payload mapping

## Goal / starting point

Trace how individual `net_event_type` payloads (protos/common/opcodes.ksy,
115 confirmed opcode IDs, no payloads reversed yet at the start of this pass) get
parsed/dispatched, starting from the confirmed entry points
`FUN_00ace694` (`0x00ace694`) and `FUN_00acecd0` (`0x00acecd0`) - the
event-queue-processing functions already known to read a queued event's type
via a 1-byte load. Goal: find the dispatch mechanism (likely a jump table
given 115 distinct types), then use it to systematically decompile and
document as many individual opcode payloads as can be genuinely confirmed.

## Headline result: the dispatch mechanism is found and fully mapped

`FUN_0038ec00` (`0x0038ec00`) is a 115-entry (`0x73`, exactly matching
`kNumNetEvents`) relative-offset jump table, keyed directly by
`net_event_type` value, that allocates and default-constructs a blank
event object for a given opcode. Table base `0x0038ec40`, resolved via the
same TOC-relative addressing scheme used elsewhere in this project
(`PTR_DAT_012fdef4` = `0x01271330`, table pointer at TOC slot `-0x7ee4`).
Full walkthrough, evidence, and the confirmed common wire envelope (a
continuation bit + 1-byte opcode preceding every event's own payload, which
also closes out `packet_header.ksy`'s previously-medium-confidence `opcode:
u1` field to effectively proven) is in
**`docs/protocol/net_event_dispatch_and_simple_opcodes.md`** - that doc is
the primary evidence record for everything in this pass; this note is the
status ledger and pointer to next steps.

Tooling built this pass (all under `tools/ghidra_scripts/`, reusable for
future passes):
- `DumpNetEventFactoryTable.java` - resolves and dumps the 115-entry
  dispatch table (opcode -> allocator trampoline address).
- `DecompileFactoryTrampolines.java` - decompiles all 115 trampolines in one
  pass, revealing each opcode's object alloc size and (if non-trivial) its
  dedicated constructor function address. Output:
  `research/ghidra/factory_trampolines_decomp.txt`.
- `ResolveNetEventVtables.java` - given a class's derived-vtable TOC slot
  offset, resolves the vtable address and decompiles its virtual function
  slots (destructor / Deserialize / Serialize / Execute / shared-inherited
  slots), correctly handling the PPC32 double-indirection through `.opd`
  descriptors (a real gotcha this pass hit and had to debug - see the
  companion doc's "Gotcha" callout). Output: `research/ghidra/vtables_final.txt`
  (+ a couple of earlier, partially-wrong-offset runs kept for the record:
  `vtables_base_and_simple.txt`, `vtables_base_and_simple2.txt`,
  `vtables_inline_all.txt`).
- `ProbeVtableSlot.java` - single-address debug probe used to diagnose the
  `.opd` double-indirection issue.

## What's confirmed vs. not, per opcode

Every one of the 115 opcodes now has at least its **object allocation size**
known, and for the ~82 opcodes with a dedicated constructor function, that
**constructor's address** is known too (a concrete, addressable starting
point for a follow-up pass - no more "where do I even start"
for any opcode). 16 opcodes have a **fully confirmed payload schema**
(`.ksy` file + evidence in the companion doc) - deliberately the simplest,
highest-confidence subset rather than a scattershot attempt at breadth over
all 115, following the explicit prioritization guidance.

| Opcode (dec/hex) | Name | Alloc size | Constructor (if not inline) | Status |
|---|---|---|---|---|
| 0 / 0x00 | `start_connection` | 0x10 | (inline) | **confirmed (this pass)** |
| 1 / 0x01 | `connection_done` | 0x1c | (inline) | **confirmed (this pass)** |
| 2 / 0x02 | `load_level` | 0x58 | FUN_0038918c | not attempted - size + constructor addr known only |
| 3 / 0x03 | `ready_to_start` | 0x18 | (inline) | **confirmed (this pass)** |
| 4 / 0x04 | `start_game` | 0x18 | (inline) | inline/simple - size known, fields not decoded |
| 5 / 0x05 | `end_game` | 0x1c | (inline) | inline/simple - size known, fields not decoded |
| 6 / 0x06 | `end_round` | 0x18 | (inline) | **confirmed (this pass)** |
| 7 / 0x07 | `emit_projectile_bullet` | 0xf0 | FUN_00412bbc | not attempted - size + constructor addr known only |
| 8 / 0x08 | `spawn_projectile_throwable` | 0x60 | FUN_00413448 | not attempted - size + constructor addr known only |
| 9 / 0x09 | `kill_projectile_throwable` | 0x14 | FUN_00412b70 | not attempted - size + constructor addr known only |
| 10 / 0x0a | `emit_grenade` | 0x50 | FUN_00413240 | not attempted - size + constructor addr known only |
| 11 / 0x0b | `spawn_explosion` | 0x130 | FUN_004132fc | not attempted - size + constructor addr known only |
| 12 / 0x0c | `grenade_start_fuse` | 0x1c | FUN_00412b18 | not attempted - size + constructor addr known only |
| 13 / 0x0d | `player_move` | 0x370 | FUN_003fd680 | not attempted - size + constructor addr known only (large - likely the highest-value remaining target) |
| 14 / 0x0e | `npc_move` | 0x140 | FUN_003fd5cc | not attempted - size + constructor addr known only |
| 15 / 0x0f | `attack_projectile` | 0x90 | FUN_00413e2c | not attempted - size + constructor addr known only |
| 16 / 0x10 | `attack_explosion` | 0x50 | FUN_00413284 | not attempted - size + constructor addr known only |
| 17 / 0x11 | `kill_info` | 0x70 | FUN_0041143c | not attempted - size + constructor addr known only |
| 18 / 0x12 | `assign_team` | 400 | FUN_00388c94 | not attempted - size + constructor addr known only |
| 19 / 0x13 | `assign_team_desc` | 0xa8 | (inline) | looked at (Deserialize 0x0038a1d4 / Serialize 0x0038a044) - large nested-array + 256-byte string field, out of "simple" scope this pass |
| 20 / 0x14 | `assign_team_done` | 0x10 | (inline) | **confirmed (this pass)** |
| 21 / 0x15 | `request_interact` | 0x1c | FUN_004069a8 | not attempted - size + constructor addr known only |
| 22 / 0x16 | `approved_interact` | 0x20 | FUN_00406a30 | not attempted - size + constructor addr known only |
| 23 / 0x17 | `denied_interact` | 0x30 | FUN_004069ec | not attempted - size + constructor addr known only |
| 24 / 0x18 | `on_interact` | 0x24 | FUN_00405588 | not attempted - size + constructor addr known only |
| 25 / 0x19 | `end_interact` | 0x1c | FUN_004055cc | not attempted - size + constructor addr known only |
| 26 / 0x1a | `add_dropped_interactable` | 0x60 | FUN_00405bc8 | not attempted - size + constructor addr known only |
| 27 / 0x1b | `remove_interactable` | 0x14 | FUN_00405610 | not attempted - size + constructor addr known only |
| 28 / 0x1c | `set_interactable_ammo` | 0x18 | FUN_00406914 | not attempted - size + constructor addr known only |
| 29 / 0x1d | `respawn_player` | 0xa0 | FUN_0040c324 | not attempted - size + constructor addr known only |
| 30 / 0x1e | `signal_respawn_player` | 0x1c | FUN_0040cd78 | not attempted - size + constructor addr known only |
| 31 / 0x1f | `secure_carry_object` | 0x28 | FUN_003f7284 | not attempted - size + constructor addr known only |
| 32 / 0x20 | `secured_flag_score` | 0x18 | FUN_003f7234 | not attempted - size + constructor addr known only |
| 33 / 0x21 | `start_pack_or_deploy` | 0x24 | FUN_003f7dd0 | not attempted - size + constructor addr known only |
| 34 / 0x22 | `stop_pack_or_deploy` | 0x18 | FUN_003f71f0 | not attempted - size + constructor addr known only |
| 35 / 0x23 | `spawn_carry_object` | 0x18 | FUN_003f71ac | not attempted - size + constructor addr known only |
| 36 / 0x24 | `carry_object_drop` | 0x80 | FUN_003f713c | not attempted - size + constructor addr known only |
| 37 / 0x25 | `carry_object_stop_move` | 0x70 | FUN_003f67cc | not attempted - size + constructor addr known only |
| 38 / 0x26 | `npc_spawn` | 0x50 | FUN_0040358c | not attempted - size + constructor addr known only |
| 39 / 0x27 | `npc_kill` | 0x18 | FUN_00403548 | not attempted - size + constructor addr known only |
| 40 / 0x28 | `breakable_attack_projectile` | 0x50 | FUN_003f4dc8 | not attempted - size + constructor addr known only |
| 41 / 0x29 | `breakable_attack_projectile_with_results` | 0x90 | FUN_003f5d58 | not attempted - size + constructor addr known only |
| 42 / 0x2a | `breakable_attack_explosion` | 0x60 | FUN_003f4eec | not attempted - size + constructor addr known only |
| 43 / 0x2b | `breakable_attack_explosion_with_results` | 0xa0 | FUN_003f4e80 | not attempted - size + constructor addr known only |
| 44 / 0x2c | `player_info` | 200 | FUN_004090dc | not attempted - size + constructor addr known only |
| 45 / 0x2d | `message` | 0x1c | (inline) | looked at (Deserialize 0x0038d45c / Serialize 0x0038ddc0) - variable-shape tagged payload (localized string + substitution args), too complex for this pass, flagged for follow-up |
| 46 / 0x2e | `event` | 0x20 | (inline) | looked at (Deserialize 0x0038b400 / Serialize 0x0038b360) - mostly simple but one field's width unresolved (FUN_00a1c0a8/FUN_00a1ca84 pair not decompiled), left out rather than guessed |
| 47 / 0x2f | `revive` | 0x1c | FUN_003d8e40 | not attempted - size + constructor addr known only |
| 48 / 0x30 | `revive_finished` | 0x20 | FUN_003d8514 | not attempted - size + constructor addr known only |
| 49 / 0x31 | `revive_credit` | 0x20 | FUN_003d8e98 | not attempted - size + constructor addr known only |
| 50 / 0x32 | `play_vox` | 0x2c | (inline) | **confirmed (this pass)** |
| 51 / 0x33 | `simple_snapshot` | 0x70 | (inline) | inline/simple - size known, fields not decoded |
| 52 / 0x34 | `simple_snapshot_phys_fx` | 0x40 | (inline) | **confirmed (this pass)** |
| 53 / 0x35 | `npc_piecewise_health_depleted` | 0x18 | FUN_00402610 | not attempted - size + constructor addr known only |
| 54 / 0x36 | `player_death_cleanup` | 0x50 | FUN_00409120 | not attempted - size + constructor addr known only |
| 55 / 0x37 | `complete_task` | 0x20 | (inline) | **confirmed (this pass)** |
| 56 / 0x38 | `start_net_task` | 0x48 | (inline) | **confirmed (this pass)** |
| 57 / 0x39 | `player_health` | 0x30 | FUN_0040d26c | not attempted - size + constructor addr known only |
| 58 / 0x3a | `heal` | 0x20 | FUN_0040c524 | not attempted - size + constructor addr known only |
| 59 / 0x3b | `kick_griefer` | 0x14 | (inline) | inline/simple - size known, fields not decoded (Deserialize/Serialize seen in passing: 3 fields, u32+u32+unconfirmed-width) |
| 60 / 0x3c | `coop_team_failed` | 0x18 | (inline) | **confirmed (this pass)** |
| 61 / 0x3d | `abort_interact` | 0x1c | FUN_00406964 | not attempted - size + constructor addr known only |
| 62 / 0x3e | `spawn_entity` | 0x80 | (inline) | **confirmed (this pass)** |
| 63 / 0x3f | `kill_entity` | 0x14 | (inline) | **confirmed (this pass)** |
| 64 / 0x40 | `animation_sync` | 0x1c | (inline) | **confirmed (this pass)** |
| 65 / 0x41 | `sync_stats` | 0x18 | FUN_0040c4e0 | not attempted - size + constructor addr known only |
| 66 / 0x42 | `sync_stats_player` | 0x14 | FUN_0040c49c | not attempted - size + constructor addr known only |
| 67 / 0x43 | `sync_carry_objects` | 0x720 | FUN_003f671c | not attempted - size + constructor addr known only (largest object in the table) |
| 68 / 0x44 | `sync_carry_object_stands` | 0x94 | FUN_003f6258 | not attempted - size + constructor addr known only |
| 69 / 0x45 | `sync_weapon_pickups` | 0x414 | FUN_0041056c | not attempted - size + constructor addr known only |
| 70 / 0x46 | `sync_breakable` | 0x58 | FUN_003f3c68 | not attempted - size + constructor addr known only |
| 71 / 0x47 | `sync_players` | 0x330 | FUN_0040a840 | not attempted - size + constructor addr known only |
| 72 / 0x48 | `request_ownership` | 0x18 | (inline) | looked at (Deserialize 0x003895bc / Serialize 0x003892a4) - 3 fields, 2 confirmed u32-width, 1 unconfirmed-width (FUN_00a1b488/FUN_00a1be18 pair) |
| 73 / 0x49 | `transfer_ownership` | 0x18 | (inline) | looked at (Deserialize 0x0038ac88 / Serialize 0x0038aaf4) - tagged union, a byte tag (0-3) selects float/int32 interpretation of the last field; real and decodable but needs the tag's meaning pinned down |
| 74 / 0x4a | `deny_ownership_request` | 0x14 | (inline) | **confirmed (this pass)** |
| 75 / 0x4b | `net_go` | 0x80 | (inline) | **confirmed (this pass)** |
| 76 / 0x4c | `swap_booster` | 0x1c | FUN_0040c458 | not attempted - size + constructor addr known only |
| 77 / 0x4d | `start_melee` | 0xf0 | FUN_003ffb04 | not attempted - size + constructor addr known only |
| 78 / 0x4e | `abort_melee` | 0x20 | FUN_003ff348 | not attempted - size + constructor addr known only |
| 79 / 0x4f | `attack_melee_damage` | 0x3c | FUN_004003dc | not attempted - size + constructor addr known only |
| 80 / 0x50 | `set_melee_history` | 0x20 | FUN_00400304 | not attempted - size + constructor addr known only |
| 81 / 0x51 | `reset_melee_history` | 0x18 | FUN_0040021c | not attempted - size + constructor addr known only |
| 82 / 0x52 | `melee_assist` | 0x1c | FUN_00400388 | not attempted - size + constructor addr known only |
| 83 / 0x53 | `melee_block` | 0x18 | FUN_003fec1c | not attempted - size + constructor addr known only |
| 84 / 0x54 | `npd_stat` | 0x1c | (inline) | inline/simple - size known, fields not decoded (Deserialize/Serialize seen in passing: several fields incl. a string, more involved than the "simple" set) |
| 85 / 0x55 | `debug` | 0x1c | (inline) | **confirmed (this pass)** |
| 86 / 0x56 | `net_set` | 0x20 | (inline) | inline/simple - size known, fields not decoded (the sequential-TOC-slot pattern broke down starting here - see companion doc section 1; needs a fresh offset derivation, not guessed) |
| 87 / 0x57 | `client_net_go` | 0x24 | (inline) | inline/simple - size known, fields not decoded |
| 88 / 0x58 | `late_join_sync_done` | 0x14 | (inline) | inline/simple - size known, fields not decoded |
| 89 / 0x59 | `late_join_sync_done_host` | 0x10 | (inline) | inline/simple - size known, fields not decoded |
| 90 / 0x5a | `phase_snapshot` | 0x90 | (inline) | inline/simple - size known, fields not decoded |
| 91 / 0x5b | `sync_odd_lives` | 0x38 | FUN_00409298 | not attempted - size + constructor addr known only |
| 92 / 0x5c | `debug_caption` | 0x3c | (inline) | inline/simple - size known, fields not decoded |
| 93 / 0x5d | `npc_hit_reaction` | 0x50 | FUN_004040ec | not attempted - size + constructor addr known only |
| 94 / 0x5e | `npc_death_reaction` | 0x50 | FUN_004032a8 | not attempted - size + constructor addr known only |
| 95 / 0x5f | `npc_set_host` | 0x1c | FUN_004034f4 | not attempted - size + constructor addr known only |
| 96 / 0x60 | `npc_on_screen` | 0x58 | FUN_00402948 | not attempted - size + constructor addr known only |
| 97 / 0x61 | `set_tension` | 0x14 | (inline) | inline/simple - size known, fields not decoded |
| 98 / 0x62 | `audio_gameplay_event` | 0x30 | FUN_00403fac | not attempted - size + constructor addr known only |
| 99 / 0x63 | `give_item` | 0x20 | FUN_003fdb90 | not attempted - size + constructor addr known only |
| 100 / 0x64 | `item_received` | 0x1c | FUN_003fdbd4 | not attempted - size + constructor addr known only |
| 101 / 0x65 | `increment_tally_stat` | 0x28 | FUN_004092dc | not attempted - size + constructor addr known only |
| 102 / 0x66 | `increment_score` | 0x1c | FUN_0040933c | not attempted - size + constructor addr known only |
| 103 / 0x67 | `set_player_exposed` | 0x1c | FUN_00409394 | not attempted - size + constructor addr known only |
| 104 / 0x68 | `add_net_marker` | 0x1c | FUN_004093e8 | not attempted - size + constructor addr known only |
| 105 / 0x69 | `player_left` | 0x14 | FUN_0040c40c | not attempted - size + constructor addr known only |
| 106 / 0x6a | `dismember` | 0x60 | FUN_004028c4 | not attempted - size + constructor addr known only |
| 107 / 0x6b | `kill_all_mines` | 0x10 | FUN_004105b8 | not attempted - size + constructor addr known only |
| 108 / 0x6c | `spawn_visibility_blocker` | 0x70 | FUN_00410b70 | not attempted - size + constructor addr known only |
| 109 / 0x6d | `sync_proxy_mine` | 0x18 | FUN_00412ac4 | not attempted - size + constructor addr known only |
| 110 / 0x6e | `explode` | 0x30 | FUN_00412c48 | not attempted - size + constructor addr known only |
| 111 / 0x6f | `set_weapon_upgrade_level` | 0x18 | FUN_00412a80 | not attempted - size + constructor addr known only |
| 112 / 0x70 | `debug_swap_part` | 0x40 | FUN_0040994c | not attempted - size + constructor addr known only |
| 113 / 0x71 | `emit_arrow` | 0x50 | FUN_004134d0 | not attempted - size + constructor addr known only |
| 114 / 0x72 | `spawn_armor_destruction` | 0x40 | FUN_0040943c | not attempted - size + constructor addr known only |

## Summary

- **Confirmed, `.ksy` written, `ksc`-validated**: 16 opcodes (0, 1, 3, 6, 20,
  50, 52, 55, 56, 60, 62, 63, 64, 74, 75, 85). 3 of these (0 `start_connection`,
  20 `assign_team_done`, 75 `net_go`) are confirmed-empty payloads (pure
  signal events, zero bits beyond the shared envelope); the rest have 1-4
  confirmed fields each.
- **Looked at, explicitly not finished** (evidence recorded in the companion
  doc's "Ruled out" section so the next pass doesn't redo the work):
  `message` (45), `event` (46), `assign_team_desc` (19),
  `request_ownership` (72), `transfer_ownership` (73).
- **Inline/simple but genuinely untouched this pass**: 4, 5, 51, 59, 84, 86,
  87, 88, 89, 90, 92, 97 (12 opcodes) - no dedicated constructor, so likely
  tractable with the same technique used for the 16 confirmed ones; just ran
  out of session time.
- **Not attempted at all**: the remaining ~82 opcodes with dedicated
  constructors - every one of them has a known object size and constructor
  address (table above) ready for the next pass to decompile directly, no
  rediscovery needed.

## Key infrastructure findings reusable for future passes

1. **The dispatch table exists and is fully mapped** (`0x0038ec40`, 115
   entries) - opcode -> allocator trampoline -> (inline construction | named
   constructor function). This alone answers "where do I start for opcode
   N" for all 115 opcodes instantly.
2. **The BitStream field API is identified** (`research/ghidra/
   bitstream_helpers_decomp.txt`): `ReadBits(n)`/`WriteBits(v,n,unsigned)`,
   `ReadBool`/`WriteBool`, `Read32`/`Write32` (three equivalent read
   call-sites, three equivalent write call-sites - can't distinguish
   int/uint/float from the call alone), `Read16`/`Write16`, `Write8`. Fields
   are **not byte-aligned** - plan accordingly when writing `.ksy` files
   (use Kaitai's `bN` bit-sized types + `meta.bit-endian: be`, as done in
   this pass's 16 files).
3. **The common per-event wire envelope is confirmed**: a 1-bit "more events
   follow" continuation flag + 1-byte opcode, immediately followed by the
   opcode's own Serialize output, optionally followed by a 1-bit "has extra
   recipients" flag + 4-bit count + N x u16 recipient-list trailer (generic,
   not opcode-specific). This closes the loop on `packet_header.ksy`'s
   previously-medium-confidence `opcode: u1` field - **recommend upgrading
   that file's confidence rating and adding the continuation-bit framing in
   a follow-up pass** (deliberately left untouched in this pass since
   `packet_header.ksy` itself was out of scope here, but the
   evidence now exists in `docs/protocol/net_event_dispatch_and_simple_opcodes.md`
   section 2).
4. **The vtable-resolution technique and its gotcha are documented** so the
   next pass doesn't lose time rediscovering the PPC32 `.opd` double-
   indirection issue (see companion doc section 1's "Gotcha" callout) or the
   TOC-slot-sequencing subtlety (slots are assigned per *inline-construction*
   opcode in enum order, skipping opcodes that have their own dedicated
   constructor - naive linear extrapolation across a skipped opcode produces
   plausible-looking but wrong vtable addresses, which is exactly what
   happened on the first attempt in this pass before it was caught and
   corrected).

## Prioritized next steps

1. **`player_move` (13) and `npc_move` (14)** - the explicitly
   flagged highest-payoff, hardest targets. Both have dedicated constructors
   now at known addresses (`FUN_003fd680`, `FUN_003fd5cc`) and are large
   objects (0x370, 0x140 bytes) - likely vectors/quaternions/animation
   state. Worth a dedicated pass once the vtable-resolution offset for
   opcodes with external constructors is worked out (their derived vtable
   pointer is *not* in the same sequential TOC-slot table used for the 16
   confirmed inline opcodes - it's loaded inside the constructor function
   itself, from an as-yet-unmapped TOC region).
2. **Finish the 12 remaining inline/simple opcodes** (4, 5, 51, 59, 84, 86,
   87, 88, 89, 90, 92, 97) - same technique as this pass's 16, just needs
   the vtable resolution re-run with corrected sequential offsets past the
   `net_set` (86) break point (see companion doc).
3. **Session-flow completion**: `assign_team` (18) and `assign_team_desc`
   (19) are the two remaining opcodes in the 0-20 "basic session flow" range
   flagged for the 0-20 range - both have known constructors/sizes now,
   `assign_team_desc`'s Deserialize/Serialize were even already decompiled
   in this pass (just not written up - see companion doc's "Ruled out"
   section) and would be a fast follow-up.
4. **`message` (45)** - real opcode, tagged-union-shaped payload
   (4-bit type tag selecting between argument shapes), likely a chat/
   notification system with localized-string + substitution-param
   semantics. Worth a dedicated pass; partially decompiled already.
5. Update `protos/common/packet_header.ksy` per finding #3 above (not done
   in this pass - out of scope here, but the evidence is
   ready).
