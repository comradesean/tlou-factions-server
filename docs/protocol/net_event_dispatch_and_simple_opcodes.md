# `net_event_type` dispatch mechanism + first confirmed payload schemas

Companion doc for the gameplay-event opcode space (`protos/common/opcodes.ksy`'s
`net_event_type` enum, values 0-114) - **not** the `0x11_ticket_server_*`
control-channel family another session is documenting in parallel (different,
unrelated opcode namespace/protocol entirely).

Covers two things:
1. **The dispatch/factory mechanism** - how the game goes from a raw opcode
   byte to a constructed, type-specific event object. This was the primary
   target of this session and is now solidly confirmed.
2. **16 individually confirmed opcode payload schemas** - the simplest,
   cleanest opcodes in the table, picked deliberately as the highest-confidence
   subset rather than trying to cover all 115 in one pass. See
   `research/notes/2026-08-14-gameplay-opcode-mapping.md` for the full
   opcode-by-opcode status ledger (confirmed / partially looked at / untouched).

## 1. The dispatch/factory table

### Finding it

Starting from the task's confirmed entry points `FUN_00ace694` (`0x00ace694`)
and `FUN_00acecd0` (`0x00acecd0`) - the two functions already known to read a
queued event's type via a 1-byte load `*(byte*)(node+4)` - decompiling
`FUN_00acecd0` shows it allocating a fresh event object via:

```c
piVar8 = (int *)_opd_FUN_0038ec00(0);   // opcode 0 in this specific call site
if (piVar8 == (int *)0x0) { return; }
*(undefined1 *)((int)piVar8 + 9) = 0;
(*(code *)**(undefined4 **)(*piVar8 + 8))(piVar8,param_2);   // -> Deserialize(this, reader)
```

`FUN_0038ec00` (`0x0038ec00`) turned out to be the dispatcher itself:

```c
undefined8 _opd_FUN_0038ec00(uint param_1)
{
  if (param_1 < 0x73) {                          // 0x73 = 115 - exactly kNumNetEvents
    T = *(int *)(PTR_DAT_012fdef4 + -0x7ee4);     // table base, read from a TOC slot
    return (*(code *)(*(int *)(T + param_1*4) + T))();  // relative-offset jump table, called with 0 args
  }
  // else: assert("Invalid net event type"), trap
}
```

`param_1 < 0x73` is the tell: 0x73 = 115 decimal, exactly `kNumNetEvents` from
the already-confirmed `net_event_type` enum recovery
(`protos/common/opcodes.ksy`). Table entries are **relative offsets from the
table's own base address** (standard PPC PIC switch-table idiom: `target =
table_base + *(i32*)(table_base + opcode*4)`), not raw pointers.

### Resolving it

`PTR_DAT_012fdef4` is read at file-scope as a plain 4-byte value (address
`0x012fdef4` holds `0x01271330` in this build - confirmed via
`tools/ghidra_scripts/DumpNetEventFactoryTable.java`, which also verified this
is the *same* TOC base value used by the per-opcode trampolines below, since
they're all in the same compiled unit / address neighborhood,
`0x38ec00`-`0x390bc4`). Table base slot = `0x1271330 + (-0x7ee4)` =
`0x0126944c`, which holds `0x0038ec40` - the table itself. Walking 115
consecutive 4-byte relative offsets from there and adding the table base
resolves cleanly to 115 distinct, monotonically increasing code addresses
(`0x0038ee0c` .. `0x00390b90`) - one "factory trampoline" per opcode, in
**exact enum-declaration order** (index == `net_event_type` value). Full dump:
`research/ghidra/netevent_factory_table.txt`.

### What each trampoline does

Each trampoline calls `operator new(size)` (`FUN_00915ae4`, confirmed generic
allocator via its `(size, stack_marker, align)` signature) with a **per-class,
per-opcode fixed size**, then either:

- **constructs inline** (writes the base+derived vtable pointers and a handful
  of fixed default fields directly in the trampoline body) - these are the
  opcodes with no extra data beyond the ~16-byte common `NetEvent` header, or
- **calls a dedicated constructor function** elsewhere in the binary (for
  opcodes whose object carries real extra fields).

Critically, **every inline-constructing trampoline writes the object's own
`net_event_type` value as a literal byte at object offset +4** - e.g. opcode 6
(`end_round`)'s trampoline does `*(byte*)(obj+4) = 6`. This is the exact same
offset (+4) that `FUN_00ace694`/`FUN_00acecd0` read via `*(byte*)(node+4)` -
this closes the loop and **confirms** (not just corroborates)
`packet_header.ksy`'s `opcode: u1` hypothesis: the wire opcode is genuinely a
single byte, and this is the field that carries it end-to-end from
construction through queuing through serialization. This should be upgraded to
high confidence in `packet_header.ksy` (see below).

Full per-opcode alloc-size + constructor-address table:
`research/ghidra/factory_trampolines_decomp.txt` (source) - all 115 entries
decompiled and tabulated (see the "Status ledger" table in
`research/notes/2026-08-14-gameplay-opcode-mapping.md`). This alone is enough
to bound every opcode's total object size even before decoding its fields,
and identifies at a glance which ~33 opcodes are "simple" (no dedicated
constructor - candidates for the next pass) vs. which ~82 have real payload
constructors.

### Resolving per-class virtual methods (Deserialize / Serialize / Execute)

Each opcode's class has its own vtable, reached via **another sequential TOC
slot table** - but only for opcodes using the *inline*-construction path
above (opcodes with a dedicated external constructor load their class vtable
pointer from a completely different, unrelated TOC region inside that
constructor function, which was not resolved this session for opcodes beyond
the ones below). For the inline-construction opcodes, the derived-class vtable
pointer TOC offset starts at `-0x7ee0` for opcode 0 and increments by exactly
4 bytes for **every subsequent inline-construction opcode in enum order**
(opcodes with an external constructor do *not* consume a slot in this
sequence - confirmed by cross-checking that the offset only advances once
between opcode 1 and opcode 3, skipping opcode 2/`load_level` which has an
external constructor). Formula and full derivation:
`tools/ghidra_scripts/ResolveNetEventVtables.java` +
`research/ghidra/vtables_final.txt`.

**Gotcha that cost real time**: a vtable slot does not hold a raw code
address - PPC32 ABI function pointers are pointers to 8-byte `.opd`
descriptors (`{code_addr, toc_addr}`). Reading a vtable slot gives you the
*address of* an opd descriptor; the real function entry is the first word
*at* that address. `ResolveNetEventVtables.java` does this double
dereference. Skipping it silently resolves to garbage-looking "no function"
addresses that are actually just descriptor data being misread as code.

Confirmed common vtable layout (from 26 cross-checked classes: 6 opcodes with
`-0x7ee0..-0x7ecc` + 20 more with `-0x7ec8..-0x7e7c`, all landing in the same
coherent `0x01223xxx-0x01224xxx` vtable address range with two of the slots
being byte-identical pointers across *every* class checked, confirming they're
inherited/non-overridden):

| vtable offset | Role | Evidence |
|---|---|---|
| `+0x0` | destructor (scalar?) | differs per class |
| `+0x4` | destructor (vector?) or related cleanup | differs per class |
| `+0x8` | **Deserialize(this, bitstream_reader)** | differs per class; called from `FUN_00acecd0`-style receive paths |
| `+0xc` | **Serialize(this, bitstream_writer)** | differs per class; called from `FUN_00ace694`'s send loop |
| `+0x10` | **Execute/Apply(this[, ctx])** | differs per class; this is where the decoded event actually mutates game state |
| `+0x14` | generic per-recipient send hook | **identical across every class checked** (`FUN_00acb460`) - inherited, not overridden by any of the 26 |
| `+0x18` | generic queue/dispatch hook | **identical across every class checked** (`FUN_00acb30c`) - inherited |
| `+0x1c` | bool, always returns 0 | **identical across every class checked** (`FUN_00388a1c`) - a default/inherited flag |
| `+0x20` | bool, always returns 1 | **identical across every class checked** (`FUN_00388a24`) - a default/inherited flag |

## 2. The common per-event wire envelope

`FUN_00ace694`'s send loop (already-confirmed entry point) writes, for each
queued event, in this exact order:

```c
_opd_FUN_00a1b758(param_2, 1);                      // WriteBool(true) - "another event follows"
_opd_FUN_00a1b6d4(param_2, *(byte*)(*piVar17 + 4));  // WriteU8(net_event_type) - confirms packet_header.ksy
(*Serialize_vtable_slot)(event_obj, param_2);        // per-opcode payload (see below)
// then, only if the event has non-default extra recipients:
uVar3 = *(ushort*)(node+3*4);              // count, from object offset 0xc
_opd_FUN_00a1b758(param_2, uVar3 != 0);    // WriteBool(has_extra_recipients)
if (uVar3 != 0) {
  _opd_FUN_00a1aad4(param_2, uVar3, 4, 1); // WriteBits(count, 4 bits, unsigned)
  // uVar3 x WriteU16(entry) - a per-recipient u16 list, from object offset 0x8
}
```

The receive side (`FUN_00acecd0`) mirrors the leading continuation bit:
`while (ReadBool(reader) != 0) { ...decode one event... }`. This is a strong,
direct confirmation that the "one or more net-events packed into a single
packet, each framed by a continuation bit + 1-byte opcode" model is correct,
and that `packet_header.ksy`'s `opcode: u1` field is real (see recommended
update below). The 4-bit-count + u16-list trailer is **not** part of the
opcode's own payload - it's a generic "extra recipients" list attached by the
base `NetEvent` class to every outgoing event, independent of opcode. Not
otherwise investigated this session (its exact purpose - e.g. targeted resend
to specific players who missed a broadcast - is a reasonable hypothesis, not
confirmed).

Caveat: `FUN_00acecd0`'s receive-side decompile calls `FUN_0038ec00(0)` with a
**literal 0**, not the just-read opcode byte - this looks like it could be
this specific queue's own hardcoded assumption (maybe this queue only ever
carries `start_connection` events pre-handshake) rather than a decompiler
error, but this was not resolved this session. The envelope conclusions above
rely on the **send-side** evidence (`FUN_00ace694`), which is unambiguous.

**Recommended follow-up (not done this session, flagged for whoever picks
this up next)**: update `protos/common/packet_header.ksy` to raise `opcode`
from medium to high confidence given this closes the loop end-to-end
(construction -> queue -> wire), and to document the leading continuation-bit
+ optional-trailer framing found here. Left undone this session to keep this
doc's scope to net-event payloads specifically; the packet_header.ksy file
itself was explicitly out of scope for individual opcode work per the task
brief, though this finding bears directly on it.

## 3. The BitStream field-level API

All per-opcode Serialize/Deserialize methods bottom out in a small set of
helper functions confirmed by direct decompilation
(`research/ghidra/bitstream_helpers_decomp.txt`). This is a genuine **bit**
stream, not a byte stream - fields are not necessarily byte-aligned (e.g.
`ready_to_start`'s ready flag is a single bit immediately following a 12-bit
integer, no padding).

| Function | Role | Evidence |
|---|---|---|
| `FUN_00a1a8dc` | `ReadBits(n) -> uint` | Assembles `n` bits a byte at a time via `FUN_00a1a7fc`; loop bound directly shows arbitrary bit-width reads (seen with n=1,3,4,0xc,0xd in this pass) |
| `FUN_00a1aad4` | `WriteBits(value, n, is_unsigned)` | Symmetric write, same bit-width parameter |
| `FUN_00a1abec` | `ReadBool() -> byte 0/1` | Effectively a 1-bit read, output normalized to a 0/1 byte |
| `FUN_00a1b758` | `WriteBool(value)` | 1-bit write |
| `FUN_00a1ae90`, `FUN_00a1b3c8`, `FUN_00a1af50` | `Read32() -> uint` | All three have byte-identical decompiled bodies (4-byte / 32-bit assembly loop) - three separate call-site names for what is almost certainly the same underlying 32-bit read, differing only in the C++-level type of the field being read into (plain uint vs. presumably int vs. float bit-pattern - cannot distinguish from the read call alone) |
| `FUN_00a1b8dc`, `FUN_00a1bd5c`, `FUN_00a1babc` | `Write32(value)` | Same situation as above, write side |
| `FUN_00a1b108` | `Read16() -> ushort` | 16-bit assembly loop |
| `FUN_00a1b5cc` | `Write16(value)` | 16-bit write |
| `FUN_00a1b6d4` | `Write8(value)` | 8-bit write (loop bound 8, not 0x10/0x18/0x20) |
| `FUN_00a1a7d8` | `GetBitPosition(stream) -> int` | Plain `*(stream+4)` read; used in `FUN_00ace694`'s loop guard (`pos < 0x2261` bits, i.e. a ~1100-byte packet-size cap) |
| `FUN_00a1a7f4`, `FUN_00a1a7f8` | no-ops | Empty function bodies - likely inlined-out begin/end hooks |

Several other Read/Write helpers were seen in the decompiled Serialize/
Deserialize bodies below (`FUN_00a1b488`/`FUN_00a1be18`,
`FUN_00a1ab64`/(unclear write pair), `FUN_00a1add0`/`FUN_00a1ca84`/
`FUN_00a1b81c` for floats) but were **not** individually decompiled this
session - their bit-widths are not confirmed, so fields depending on them are
marked `unconfirmed width` below rather than guessed.

Because these are bit-packed (not byte-aligned), the `.ksy` files below use
Kaitai's bit-sized integer types (`b1`, `b12`, `b13`, ...) with
`meta.bit-endian: be`, matching this project's existing `endian: be` byte
convention.

## 4. The 16 confirmed simple opcodes

All field offsets below are **object offsets** (i.e. offsets into the
in-memory `NetEvent`-derived C++ object, starting after the ~16-byte common
header at object offset 0x10) - not wire byte offsets. The wire order is
exactly the Serialize call order shown, immediately following the shared
2-byte(ish) envelope (continuation bit + opcode byte) from section 2 above;
there is no gap or padding between the envelope and the first payload field
since both are part of the same bitstream.

### 0x00 `start_connection` (opcode 0)

**Confirmed empty payload.** Trampoline `0x0038ee0c` constructs inline, size
0x10 (just the common header, no extra fields). Deserialize (`0x00388a2c`)
and Serialize (`0x00388a30`) are both literal `{ return; }` - zero bits
written beyond the shared envelope. Execute (`0x0038c58c`) calls
`FUN_0034b208`, a connection-init hook unrelated to wire content.

### 0x01 `connection_done` (opcode 1)

Deserialize `0x0038911c` / Serialize `0x00388fd0`:
```c
ReadBool(&this->success);       // offset 0x10, 1 bit
Read32(&this->bytes_or_val1);   // offset 0x14, 32 bits
Read32(&this->duration_or_val2);// offset 0x18, 32 bits
```
Execute (`0x0038c554`) calls `FUN_0035199c(success, val1, val2)`
(`0x0035199c`), which - among other things - formats `val1` divided by 1024
and `val2` divided by 1000 into what looks like a log/debug string call
(`FUN_00e46460`, a printf-style helper elsewhere in this binary). This is
suggestive but not proof of units: **hypothesis** `val1` = bytes transferred
(displayed as KB) and `val2` = elapsed milliseconds (displayed as seconds),
marked medium confidence - the divide-by-1024/1000 pattern is real and
directly observed, but no string/format-string content was traced to confirm
the label text.

### 0x03 `ready_to_start` (opcode 3)

Deserialize `0x00389a40` / Serialize `0x00389930`:
```c
player_id = ReadBits(12);   // offset 0x10, 12-bit unsigned
ready = ReadBool();          // offset 0x14, 1 bit
```
High confidence on both type *and* semantics: Execute (`0x0038c5b0`) loops
over 8 player slots, matches `player_id` against each slot's stored id
(`*(int*)(slot+0x1a8)`), then on match sets one of two adjacent flag bytes
(`slot+0x3fc` / `slot+0x3fd`) depending on whether `ready` is true or false -
textbook "this player toggled their ready-up state" handling, matching the
opcode name exactly.

### 0x06 `end_round` (opcode 6)

Deserialize `0x003890c0` / Serialize `0x00388f74`: two back-to-back `Read32`/
`Write32` calls, offsets 0x10 and 0x14. Execute (`0x0038cc2c`) routes into a
formatting/log helper (`FUN_00767434`) whose arguments weren't traced further
- fields are confirmed present and 32-bit, semantics unconfirmed (best guess:
round number and/or a result code, not verified).

### 0x14 `assign_team_done` (opcode 20)

**Confirmed empty payload** - same pattern as `start_connection`: Deserialize
(`0x00388a34`) and Serialize (`0x00388a38`) are both `{ return; }`. Execute
(`0x0038dcf4`) is a substantial match-flow-progression function (checks/sets
several match-state flags) consistent with "team assignment phase complete,
proceed" being a pure signal with no payload.

### 0x32 `play_vox` (opcode 50)

Deserialize `0x0038903c` / Serialize `0x00388ef4`:
```c
Read32(&this->vox_id);       // offset 0x10
speaking = ReadBool();        // offset 0x14, 1 bit
Read32(&this->field_18);      // offset 0x18
Read32(&this->speaker_id);    // offset 0x1c
```
Execute (`0x0038d138`) compares `speaker_id` (offset 0x1c) against a live
player object's field `+0x77` to decide between two different sound-event
hash constants passed to `FUN_003e82cc` - consistent with `speaker_id`
selecting a 3D-positional vs. non-positional (e.g. local/2D) playback variant
depending on whether the speaker is the local player. `vox_id` (offset 0x10)
and `field_18` (offset 0x18) are confirmed present and 32-bit; their specific
meaning (likely a vox line/bank ID and possibly a priority or category) is
not confirmed.

### 0x34 `simple_snapshot_phys_fx` (opcode 52)

Deserialize `0x00389a04` / Serialize `0x003898f8`: single field,
`ReadBits(13)` / `WriteBits(.., 13, 1)` at offset 0x10. Execute (`0x00392a3c`)
passes it into `FUN_00392908(value, 0xd9, 1)` and `FUN_00ad124c(...)` -
consistent with an entity/effect-index lookup, not otherwise confirmed.

### 0x37 `complete_task` (opcode 55)

Deserialize `0x0038a980` / Serialize `0x0038a6b0`: two `Read32`/`Write32`
calls at offsets 0x10 and 0x14. Execute (`0x00388b4c`) stores both directly
into a global task-tracking struct (`+0x4b50`, `+0x4b54`) and sets a
completion flag (`+0x4af8 = 1`) - confirms these are a task identifier pair
(likely task-type + task-instance-id), exact semantics of which is which not
disambiguated.

### 0x38 `start_net_task` (opcode 56)

Deserialize `0x0038a950` / Serialize `0x0038a680`: single `Read32`/`Write32`
at offset 0x10. Execute (`0x0038dbc8`) uses it as a lookup key into what
looks like a task/entity registry (`FUN_009ef28c`, `FUN_0078be94`) -
consistent with a task ID.

### 0x3c `coop_team_failed` (opcode 60)

Deserialize `0x0038a7f8` / Serialize `0x0038a538`: `Read32`(offset 0x10) +
`Read32`-variant `FUN_00a1af50`(offset 0x14). Execute (`0x00393c34`) resolves
offset 0x10 via `FUN_007b49dc` (an entity-handle-to-object lookup used
identically in `kill_entity` below) and offset 0x14 via `FUN_0039f3d8` (a
lookup keyed off a small per-match table, likely team index) - confirms
`entity_id` (0x10) + `team_id` (0x14), medium-high confidence on the labels
by analogy with `spawn_entity`/`kill_entity`'s confirmed `FUN_007b49dc` usage.

### 0x3e `spawn_entity` (opcode 62)

Deserialize `0x0038a884` / Serialize `0x0038a5bc`: identical shape to
`coop_team_failed` - `Read32`(0x10) + `FUN_00a1af50`-Read32(0x14). Execute
(`0x0038b71c`) resolves both the same way (`FUN_007b49dc` entity lookup +
`FUN_0039f3d8` team-table lookup) then calls `FUN_007b589c(entity, team)` -
strong confirmation of `entity_id` (0x10) + `team_id` (0x14).

### 0x3f `kill_entity` (opcode 63)

Deserialize `0x0038a854` / Serialize `0x0038a58c`: single `Read32`/`Write32`
at offset 0x10. Execute (`0x0038b6c4`) resolves it via `FUN_007b49dc` (the
same entity-handle lookup used above) then calls a virtual method at the
resolved object's vtable+0x210 - high confidence this is `entity_id`.

### 0x40 `animation_sync` (opcode 64)

Deserialize `0x0038998c` / Serialize `0x00389888`:
```c
anim_index = ReadBits(1);   // offset 0x10, 1 bit (!) - effectively a 2-valued selector, not a bool per se
Read32-variant(&this->field_14);  // offset 0x14, via FUN_00a1af50
Read32(&this->field_18);          // offset 0x18, via FUN_00a1ae90
```
Execute (`0x0038e610`) uses `anim_index` (offset 0x10) as a byte multiplied
into a per-entity animation-table stride (`*0xf158`), then combines offsets
0x14/0x18 into a packed value stored back into that table entry - confirmed
3-field shape, exact semantics of 0x14/0x18 not disambiguated (likely a frame
number and a timestamp/phase value, not confirmed).

### 0x4a `deny_ownership_request` (opcode 74)

Deserialize `0x0038958c` / Serialize `0x00389274`: single Read32-variant
(`FUN_00a1af50`)/Write32-variant (`FUN_00a1babc`) at offset 0x10. Execute
(`0x0038c740`) resolves it via `FUN_0039f3d8` (the same lookup used for
`team_id` above, so this may actually be a team or ownership-request-target
id rather than an entity id - not disambiguated) and sets a pending-deny flag
(`+0x401 = 1`).

### 0x4b `net_go` (opcode 75)

**Confirmed empty payload** - Deserialize (`0x00388b78`) and Serialize
(`0x00388b7c`) are both `{ return; }`. Execute (`0x003928bc`) triggers
`FUN_00392750` conditionally - consistent with `net_go` being a pure
"synchronized match start" signal, matching the name.

### 0x55 `debug` (opcode 85)

Deserialize `0x0038955c` / Serialize `0x00389244`: single Read32-variant
(`FUN_00a1af50`)/Write32-variant (`FUN_00a1babc`) at offset 0x10. Execute
(`0x0038b79c`) passes it straight to `FUN_0064b8dc(value, 0)` - a debug-output
helper, exact meaning of the value not traced further (likely a debug code or
category id, not confirmed).

## 5. Second pass (2026-08-15): opcodes with dedicated external constructors

The first pass above (section 4) deliberately covered only the ~33
inline-constructed opcodes reachable via the sequential-TOC-slot vtable trick.
This pass generalizes that technique to the ~82 opcodes with a **dedicated
external constructor function** (per-opcode alloc size + constructor address
already known from `research/ghidra/factory_trampolines_decomp.txt` - see
`research/notes/2026-08-14-gameplay-opcode-mapping.md`'s ledger) and works
through a first batch of 25.

### Generalizing vtable resolution to external-constructor opcodes

Each external constructor (e.g. `FUN_00412b70` for opcode 9) sets up the
object's header the same way the inline trampolines do - write the
**base**-class (`NetEvent`) vtable pointer first, then overwrite it with the
**derived** class's own vtable pointer, both loaded via a TOC-relative
offset. The difference from section 1's inline case is only *which* anchor
value the offset is relative to: instead of a single shared `unaff_r30`
register value, each constructor's compilation unit decompiles to a load off
a named global cell (e.g. `PTR_DAT_012fdfa4`, `PTR_PTR_012fdfa0`) - a
per-object-file "TOC anchor" slot that holds the exact same TOC base pointer
value as everywhere else in the binary (confirmed by checking multiple
constructors sharing an anchor symbol always resolve the same *base*-vtable
address off it). Concretely, for a derived vtable at decompiled offset
`puVar2 + -0x7ffc` where `puVar2 = PTR_DAT_012fdfa4`:

```
anchorVal = *(uint32*)0x012fdfa4        // the literal address in the symbol name
vtableAddr = *(uint32*)(anchorVal + (-0x7ffc))
```

then the same PPC32 `.opd`-descriptor double-dereference from section 1
resolves `vtableAddr+0x8` (Deserialize) and `vtableAddr+0xc` (Serialize) to
real function addresses. New tooling:
`tools/ghidra_scripts/ResolveExternalCtorVtables.java` (takes
`name anchorAddrHex offsetHex` triples, reusable for the remaining ~57
external-constructor opcodes not covered this pass). Verified correct by
cross-checking vtable+0x14/+0x18/+0x1c/+0x20 for every opcode in this batch
against the exact same inherited-function addresses (`FUN_00acb460`,
`FUN_00acb30c`, `FUN_00388a1c`, `FUN_00388a24`) confirmed in section 1 - a
strong structural sanity check that the resolution is landing on real
`NetEvent`-derived vtables, not garbage.

Full resolution dump: `research/ghidra/batch1_vtables.txt`. Constructor
decompiles (used to find each anchor/offset pair):
`research/ghidra/batch1_constructors_decomp.txt`. Deserialize/Serialize
decompiles: embedded in `batch1_vtables.txt`'s second half. Execute
decompiles: `research/ghidra/batch1_execute_decomp.txt`.

### New BitStream helper findings

This pass's fields exercised several helper functions not seen (or not
individually decompiled) in section 3's pass:

| Function | Role | Evidence |
|---|---|---|
| `FUN_00a1add0` | `ReadFloat() -> f32` | Decompiled this session (`research/ghidra/batch1_helpers_decomp.txt`): 4-byte assembly loop identical in shape to the confirmed `Read32` helpers, first used at `grenade_start_fuse`'s `fuse_time` field. |
| `FUN_00a1b81c` | `WriteFloat(value)` | Symmetric write; explicitly casts its `double` parameter to `float` before the 4-byte write loop - confirms 32-bit single-precision, not `double`. |
| `FUN_00a1b488` | `Read32() -> uint` (4th equivalent call site) | Decompiled this session: byte-identical 4-byte-loop shape to the other three confirmed Read32 helpers (`FUN_00a1ae90`/`FUN_00a1b3c8`/`FUN_00a1af50`). **This resolves the width that blocked `request_ownership` (opcode 72) in the first pass** - it's a plain 32-bit read, not a novel width; `request_ownership` is now unblocked for a future pass. |
| `FUN_00a1be18` | `Write32(value)` (4th equivalent call site) | Symmetric write, same finding. |
| `FUN_00a1ab64` | `ReadU8() -> byte` (new 8-bit call site) | Decompiled this session: loop bound produces exactly one byte (`*param_2 = (char)uVar3`), confirmed via `swap_booster`'s `flag_byte` field where the *Serialize* side pairs it with the already-known `Write8` (`FUN_00a1b6d4`). |
| `FUN_00a1b190` | `Read16() -> ushort` (3rd equivalent call site) | Decompiled this session; paired with `FUN_00a1b548` (`Write16`, symmetric) in `swap_booster`'s `old_slot_value` field. |

### The "optional compact id" idiom

Two opcodes this pass (`revive`, opcode 47, and `reset_melee_history`,
opcode 81) share a distinctive encoding: a bool field is read/written
*before* an id field, and the id field's bit-width is computed at runtime
from that bool via the exact same branchless expression in both opcodes'
Deserialize/Serialize:

```c
width = ((int)(*(byte*)&flag - 1) >> 0x1f & 0x13) + 0xd;   // flag=1 -> 13 bits, flag=0 -> 32 bits
```

In both opcodes, Execute uses the bool to choose between two *different*
object-lookup helpers for the id (`FUN_0039f3d8` when compact/13-bit,
`FUN_0039e0c8` when full/32-bit) - not just a cosmetic width difference, a
genuinely different resolution path. Hypothesis (not confirmed further):
13 bits covers the common in-range player/entity index, 32 bits is a
fallback for values outside that range or a sentinel (e.g. "no target").
Modeled in the `.ksy` files via a leading bool field plus two mutually
exclusive (`if:`-gated) sibling fields for the two widths - see
`protos/0x2f_revive.ksy` / `protos/0x51_reset_melee_history.ksy`. (Kaitai
note: comparing a `b1` field against an integer literal fails to compile
with ksc 0.11 - `error: can't compare BitsType1(BigBitEndian) and
Int1Type(true)` - use `== true`/`== false` instead.)

### The 25 confirmed opcodes

Field offsets are object offsets, same convention as section 4.

#### 0x09 `kill_projectile_throwable` (opcode 9)

Single field, `throwable_id` (u32, offset 0x10, via `FUN_00a1b3c8`).
Deserialize `0x00410b40` / Serialize `0x00410a78`. Execute (`0x00413514`)
resolves it via `FUN_009ef28c` (a dynamic-object registry lookup shared with
opcode 109 below) then conditionally calls `FUN_006ad9d4` (despawn/kill).
High confidence, type and semantics.

#### 0x0c `grenade_start_fuse` (opcode 12)

`entity_id` (u32, 0x10) + `fuse_time` (f32, 0x14, first confirmed use of the
float helper pair) + `team_id` (b13, 0x18). Deserialize `0x00410f78` /
Serialize `0x00410d40`. Execute (`0x00413824`) resolves `entity_id` via
`FUN_009ef28c` and, conditionally, `team_id` via `FUN_0039f3d8` (the same
team-lookup helper confirmed for `spawn_entity`/`coop_team_failed` in
section 4). `fuse_time` type confirmed; "fuse duration" semantics inferred
from the opcode name only.

#### 0x15 `request_interact` (opcode 21) / 0x3d `abort_interact` (opcode 61)

Structurally identical: `player_id` (b13, 0x10) + `interact_slot` (u32,
0x14) + `target_id` (u32, 0x18). `request_interact` Deserialize `0x00406070`
/ Serialize `0x00405d4c`, Execute `0x00407c68`. `abort_interact` Deserialize
`0x00405ff8` / Serialize `0x00405ce0`, Execute `0x00406688`. Both Execute
functions call the exact same validate/apply function pair
(`FUN_003acc74`/`FUN_003ace50`-or-`FUN_003aceb8`) with the identical argument
order `(target=0x18, player=0x10, extra=0x14)` - cross-opcode structural
confirmation of the field mapping. `player_id`/`target_id` high confidence;
`interact_slot`'s exact role (slot index vs. interact type) unconfirmed.

#### 0x19 `end_interact` (opcode 25)

`player_id` (b13, 0x10) + `interactable_id` (u32, 0x14) + `field_18` (u32,
0x18, unresolved). Deserialize `0x00405f80` / Serialize `0x00405c70`.
Execute (`0x00406a74`) resolves `player_id` via `FUN_0039f3d8` and
`interactable_id` via a distinct interactable-registry helper
(`FUN_003ac5b8`), clearing a pending-interact flag on it. `field_18` not
referenced in the traced Execute path.

#### 0x1b `remove_interactable` (opcode 27)

Single field, `interactable_id` (u32, 0x10). Deserialize `0x0040586c` /
Serialize `0x0040583c`. Execute (`0x0040664c`) passes it straight to a
one-call removal function (`FUN_003ac8a8`). High confidence.

#### 0x1c `set_interactable_ammo` (opcode 28)

`interactable_id` (u32, 0x10) + `ammo_count` (u32, 0x14). Deserialize
`0x004057e0` / Serialize `0x00405788`. Execute (`0x00406c80`) resolves the
interactable and either writes `ammo_count` directly into its `+0x390` field
or routes it through a weapon-rack setter (vtable+0x30c). High confidence.

#### 0x1e `signal_respawn_player` (opcode 30)

`player_id` (b13, 0x10) + `respawn_flag` (b1, 0x14) + `field_18` (u32, 0x18,
via `FUN_00a1b488`). Deserialize `0x00409eac` / Serialize `0x00409d08`.
Execute (`0x0040ec04`) resolves `player_id` and branches on `respawn_flag`
between a spawn-point-lookup path and a different call; `field_18`
unreferenced in the traced path.

#### 0x20 `secured_flag_score` (opcode 32)

`score_value` (u32, 0x10) + `team_id` (b13, 0x14). Deserialize `0x003f6b5c`
/ Serialize `0x003f6948`. Execute (`0x003f7020`) resolves `team_id` via
`FUN_0039f3d8` and passes `score_value` straight into a score-tracker call
(`FUN_003ea190`). High confidence, both fields.

#### 0x22 `stop_pack_or_deploy` (opcode 34) / 0x23 `spawn_carry_object` (opcode 35)

Both 2-field, both 32-bit-ish (`stop_pack_or_deploy`: `player_id` b13 +
`field_14` u32; `spawn_carry_object`: `field_10` u32 + `field_14` u32).
`stop_pack_or_deploy` Deserialize `0x003f6af8` / Serialize `0x003f68ec`,
Execute `0x003f70fc` (both fields used jointly as a single lookup key, so
individual roles aren't disambiguated). `spawn_carry_object` Deserialize
`0x003f6a9c` / Serialize `0x003f6898`, Execute `0x003f7c64` (branches on
each field but neither is independently resolved through a registry).
Type-confirmed high, semantics low-medium for both.

#### 0x27 `npc_kill` (opcode 39) / 0x5f `npc_set_host` (opcode 95)

Both use a **full 32-bit `ReadBits(32)`** for their npc-id field, distinct
from the common 13-bit player/entity-index scheme used everywhere else in
this opcode family - a new cross-opcode pattern this pass surfaced.
`npc_kill`: `npc_id` (b32 via `ReadBits(32)`, 0x10) + `field_14` (u32 via
`FUN_00a1b3c8`, 0x14); Deserialize `0x0040375c` / Serialize `0x00402c40`,
Execute `0x00403ca0` (unusually convoluted, includes an exception-trap path
- semantics left low-medium). `npc_set_host`: `requester_id` (b13, 0x10) +
`npc_id` (b32 via `ReadBits(32)`, 0x14) + `is_host` (b1, 0x18); Deserialize
`0x00402dcc` / Serialize `0x00402bcc`, Execute `0x00403df4` resolves
`npc_id` via the same `FUN_0039e0c8` npc-registry helper as `npc_kill`, and
`requester_id` by scanning **local player-table slots** rather than a
generic registry (used to check "is this local machine the requester") -
confirms `is_host` directly (passed to `FUN_00090074(npc, is_host)`).

#### 0x2f `revive` (opcode 47) / 0x51 `reset_melee_history` (opcode 81)

See "optional compact id" idiom above. `revive` additionally has a fixed
`reviver_id` (b13, 0x14) and a trailing `extra_flag` (b1, 0x19) that Execute
(`0x003d9ee4`) uses to select between two stat-increment codes (6 vs 7) -
suggestive of solo-revive vs. revive-assist, not confirmed. `reset_
melee_history`'s Execute (`0x00400ad4`) calls a "clear melee history"
virtual method (vtable+0x3b4) directly matching the opcode name - the
highest-confidence semantics of the pair.

#### 0x4c `swap_booster` (opcode 76)

`player_id` (b13, 0x10) + `old_slot_value` (b16, 0x14) + `flag_byte` (b8,
0x16) + `new_booster_id` (b4, 0x18). Deserialize `0x0040a330` / Serialize
`0x0040a2a8`. Execute (`0x0040ce9c`) resolves `player_id` and applies the
other three fields via a single setter (`FUN_003665c8`), wrapped in a
snapshot/verify/revert sequence when the target already exists. The 4-bit
width on `new_booster_id` is consistent with a small booster-type enum.

#### 0x53 `melee_block` (opcode 83)

`player_id` (b13, 0x10) + `block_value` (u32, 0x14, via `FUN_00a1b488`).
Deserialize `0x003fed68` / Serialize `0x003fec84`. Execute (`0x004002b0`)
writes `block_value` directly into the resolved player's `+0x58c` field.
High confidence, both fields.

#### 0x64 `item_received` (opcode 100)

`field_10` (u32) + `field_14` (u32) + `field_18` (b1). Deserialize
`0x003fdc94` / Serialize `0x003fdc30`. Execute (`0x003fe0f0`) is a large
item-pickup VFX/audio routine; both u32 fields are resolved via the player
registry (`FUN_0039f3d8`) but which is player vs. item is not disambiguated
- left unguessed per this project's confidence discipline.

#### 0x66 `increment_score` (opcode 102)

`id` (b13, 0x10) + `field_14` (u32, 0x14) + `score_delta` (u32, 0x18).
Deserialize `0x00409764` / Serialize `0x0040963c`. Execute (`0x0040c8bc`)
branches on `id == 0` (team-level increment, uses `field_14`) vs. nonzero
(player increment via `FUN_0039f3d8`, does *not* use `field_14`) - both
branches pass `score_delta` as the amount. `score_delta` high confidence;
`field_14` only meaningful in the team branch, not disambiguated further.

#### 0x67 `set_player_exposed` (opcode 103)

`player_id` (b13, 0x10) + `field_14` (u32, 0x14, via `FUN_00a1b488`) +
`is_exposed` (b1, 0x18). Deserialize `0x00409d80` / Serialize `0x00409bdc`.
Execute (`0x004094b8`) writes `is_exposed` directly into the resolved
player's `+0x90a` byte field - direct confirmation, matches the opcode name
exactly. `field_14` unreferenced in this Execute function.

#### 0x68 `add_net_marker` (opcode 104)

`owner_id` (b13, 0x10) + `marker_type` (u32, 0x14, via `FUN_00a1b3c8`) +
`field_18` (u32, 0x18, via `FUN_00a1b488`). Deserialize `0x00409ad8` /
Serialize `0x004099cc`. Execute (`0x00410188`) resolves `owner_id` and uses
`marker_type` as a key into a per-marker-type dictionary lookup
(`FUN_007a3878`). `field_18` unreferenced in the traced path.

#### 0x69 `player_left` (opcode 105)

Single field, `player_id` (b13, 0x10). Deserialize `0x004096b0` / Serialize
`0x00409590`. Execute (`0x0040c5b4`) resolves it twice - once directly, once
at `player_id + 0x1000` (a primary-slot/shadow-slot addressing scheme) -
running a cleanup call and invalidating a field (`+0x3c0 = -1`) for each.
High confidence, matches the opcode name (per-player disconnect cleanup).

#### 0x6b `kill_all_mines` (opcode 107)

**Confirmed empty payload**, same pattern as `start_connection`/`net_go`/
`assign_team_done`: Deserialize (`0x00410564`) and Serialize (`0x00410568`)
are both `{ return; }`. Execute (`0x00410c00`) calls a "clear all" function
on the mine registry itself, needing no per-object field.

#### 0x6d `sync_proxy_mine` (opcode 109)

`entity_id` (u32, 0x10) + `flag_a` (b1, 0x14) + `flag_b` (b1, 0x15).
Deserialize `0x004108b0` / Serialize `0x0041084c`. Execute (`0x0041374c`)
resolves `entity_id` via the same `FUN_009ef28c` registry as
`kill_projectile_throwable`; the two bools aren't visibly consumed in the
traced code.

#### 0x6f `set_weapon_upgrade_level` (opcode 111)

`entity_id` (u32, 0x10) + `upgrade_level_a` (b8, 0x14) + `upgrade_level_b`
(b8, 0x15). Deserialize `0x00410704` / Serialize `0x004106a0`. Execute
(`0x00410638`) resolves `entity_id` and passes both bytes straight into a
setter call (`FUN_003cd838`). High confidence, matches the opcode name well
(two weapon-part/upgrade levels).

### Set aside this pass: `sync_stats` (65) / `sync_stats_player` (66)

Both looked at (Deserialize/Serialize decompiled, in
`research/ghidra/batch1_vtables.txt`). Both are real and their *own* 1-2
object fields are confirmed (`sync_stats`: two u32 fields, offsets 0x10/
0x14; `sync_stats_player`: one u32 `player_id`-shaped field, offset 0x10),
but their Deserialize/Serialize additionally read/write a large *external*
stats-manager singleton directly from the bitstream - `sync_stats` loops
over a per-category array (stride 0x6e) via `FUN_003e6308`/`FUN_003e6590`;
`sync_stats_player` reads a per-player sub-block via `FUN_003e628c`/
`FUN_003e7a68` (partially decompiled: confirms at least a u32 at `+0x5e8`
and a u8 at `+0x5ef` relative to the player's stat-block base, with two more
sub-calls, `FUN_003e63f8`, not resolved). This means the *wire* payload for
both opcodes extends well beyond what the event object itself stores, so a
`.ksy` covering only the object's own fields would silently truncate real
wire data - written up here instead of as an incomplete parser. Good target
for a dedicated "stats sync family" follow-up (likely shared by
`increment_tally_stat`/opcode 101 and others in the same address
neighborhood).

## Ruled out / explicitly not attempted this session

- **`message` (opcode 45)** - looked at (Deserialize `0x0038d45c`, Serialize
  `0x0038ddc0`). This is a real, working opcode but its payload is a
  variable-shape tagged structure (a 4-bit type tag selecting between several
  different fixed-size argument shapes, resembling a localized
  string-with-substitution-parameters system) tangled together with unrelated
  lookup logic. Genuinely more complex than this pass's "simple opcodes"
  scope - flagged as a good target for a dedicated follow-up pass, not
  guessed at here.
- **`event` (opcode 46)** - looked at (Deserialize `0x0038b400`, Serialize
  `0x0038b360`). Mostly simple (13-bit id + three 32-bit fields + one float)
  but has one field (object offset 0x20, spanning to 0x30) read via
  `FUN_00a1c0a8` and written via a lone `FUN_00a1ca84(param_2)` call that
  takes no explicit value argument - shape/width not resolved this session,
  so the whole opcode was left out rather than half-documented.
- **`assign_team_desc` (opcode 19)** and **`assign_team` (opcode 18)** - both
  looked at; both are large (nested per-team-slot arrays, a 256-byte embedded
  buffer, likely a clan name or tag) and out of scope for a "simple opcodes"
  pass, but the dispatch/vtable resolution machinery documented in section 1
  makes them tractable for a focused follow-up.
- **`request_ownership`/`transfer_ownership` (opcodes 72/73)** - looked at
  in the first pass. `request_ownership` was blocked on the then-unconfirmed
  width of `FUN_00a1b488`/`FUN_00a1be18` - **section 5 (2026-08-15) now
  confirms this pair is a plain 32-bit Read32/Write32 equivalent**, so
  `request_ownership` is unblocked and a good target for the next pass (not
  done this session - out of the batch picked). `transfer_ownership` is a
  tagged union (a byte tag 0-3 selects between float/int32/two other 32-bit
  interpretations for its last field) - real and decodable, just needs the
  tag's exact meaning pinned down before it's worth writing a `.ksy` for it.

See `research/notes/2026-08-14-gameplay-opcode-mapping.md` for the complete
115-opcode status ledger (which of the ~33 "simple/inline-constructed"
opcodes are covered here vs. still open, and which of the ~82
"complex/dedicated-constructor" opcodes have at least had their object size
and constructor address identified for a future pass).
