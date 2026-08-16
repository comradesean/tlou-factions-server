meta:
  id: grenade_start_fuse
  endian: be
  bit-endian: be
  license: CC0-1.0
  imports:
    - common/opcodes
doc: |
  Direction: peer-to-peer (client<->client, relayed via the current host peer; not server-terminated - see docs/protocol/net_event_dispatch_and_simple_opcodes.md and research/notes/network-topology.md)

  net_event_type opcode 12. 3-field payload: entity handle, a float, and a
  13-bit team id.

  STATUS: confirmed structurally, high confidence on type/width; semantics
  medium confidence. Deserialize (FUN_00410f78, 0x00410f78) / Serialize
  (FUN_00410d40, 0x00410d40):
    Read32(&entity_id);       // offset 0x10, via FUN_00a1af50
    ReadFloat(&fuse_time);    // offset 0x14, via FUN_00a1add0 (Serialize
                               // confirms width: FUN_00a1b81c((double)
                               // *(float*)(this+0x14), stream) - 32-bit
                               // IEEE-754 float, first confirmed use of
                               // this Read/WriteFloat helper pair in this
                               // project; see companion doc section 5 for
                               // the widths of FUN_00a1add0/FUN_00a1b81c.
    ReadBits(&team_id, 13);   // offset 0x18
  Execute (FUN_00413824, 0x00413824) resolves entity_id via FUN_009ef28c
  (same dynamic-object registry as opcode 9), and - conditionally on a
  per-match flag - resolves team_id via FUN_0039f3d8 (the same team-lookup
  helper used by spawn_entity/coop_team_failed's confirmed team_id
  fields), confirming both those fields. fuse_time (offset 0x14) is not
  itself referenced in the traced portion of Execute (likely consumed by a
  called sub-function not decompiled this pass); its "fuse duration"
  semantics is inferred from the opcode name and its being the sole float
  field, not independently confirmed.
doc-ref: ../docs/protocol/net_event_dispatch_and_simple_opcodes.md
seq:
  - id: entity_id
    type: b32
    doc: "32-bit grenade entity handle (object offset 0x10). Confirmed: resolved via FUN_009ef28c on Execute, same registry-lookup helper as opcode 9's throwable_id."
  - id: fuse_time
    type: f4
    doc: "32-bit float (object offset 0x14), read/written via the newly-confirmed FUN_00a1add0/FUN_00a1b81c float helper pair. Width confirmed; 'fuse duration' semantics is an inference from the opcode name, not traced further in Execute."
  - id: team_id
    type: b13
    doc: "13-bit team id (object offset 0x18). Confirmed: resolved via FUN_0039f3d8 on Execute when a per-match flag is set, matching the established 13-bit team_id pattern from spawn_entity/coop_team_failed."
