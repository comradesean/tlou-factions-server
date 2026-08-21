# Follow-up on four open items: the RoomCreate caller, 0x13e's encoding selector, 0x142's u16, capability bit 1

Date: 2026-08-20 (third pass, after the tier-2 follow-up and its audit)

Static only - no live RPCS3 session. Every address below is **01.00** unless
labelled otherwise, taken from `research/disasm/full.asm`
(`objdump -D -b binary -m powerpc:common64 -EB --adjust-vma=0x10000`) and
re-read at the instruction level before being cited. The 01.00 binary's TOC
(`r2`) is `0x01305870`; both LOAD segments map `file offset = VMA - 0x10000`.

Build-data bundles used:

| file | build | source |
|---|---|---|
| `dc1/net.bin` | 01.00 | `PS3_GAME/USRDIR/build/main/bin.psarc`, via `dc_dir.py --extract-from` |
| `net10.bin` | 01.11 | `server/data/served_content/net10.bin.psarc.crypt`, via `server/lib/psarc_crypt.py extract` |

## 0. A technique note: resolving `bctrl` dispatches without a call graph

Three of the four items below were blocked on the same thing - a `bctrl`
through a vtable slot, which `research/tools/eboot_analysis/scan_bl.py` cannot
see because it only finds direct `bl`. The method that unblocked all three, and
which is worth reusing:

1. **OPD first, not the function.** In this ABI a vtable slot holds the address
   of an 8-byte `.opd` descriptor `{func:u32, toc:u32}`, not the function. So
   searching the image for the function's own address finds the OPD entry, and
   searching for *that* address finds the vtable slot. `FUN_00ad5b78`'s
   address occurs exactly once in the image, at `0x012E9C40` (with
   `0x01305870` - the TOC - in the following word, confirming it is an OPD
   descriptor). `0x012E9C40` in turn occurs exactly once, at `0x01243B48`.
2. **Recover the vtable base from the slot.** `0x01243B48 - 0x10 = 0x01243B38`,
   and that base's other slots are the already-known Session Manager builders
   (`+0x20 = FUN_00ad6a34`, `+0x34 = FUN_00ad7024`, `+0x38 = FUN_00ad5ffc`), so
   the identification is self-checking.
3. **Literal-pool base tracking to resolve globals.** Functions in this binary
   load a per-translation-unit literal-pool base with `lwz r30,-N(r2)` and then
   address constants as `lwz rX,-M(r30)`. Walking the disassembly linearly
   while tracking the current `r30` value (read out of the image at
   `0x01305870 - N`) turns every `lwz rX,-M(r30)` into a concrete address. That
   is how each call site's arguments below were named. This is a small script,
   not a tool in `research/tools/` yet, but it is the single most useful
   primitive for this binary and should probably become one.

## 1. `FUN_00ad5b78`'s caller - RESOLVED

`FUN_00ad5b78` is the **0x12f RoomCreate** sender (opcode literal `li r0,303`
@`0xad5c38`), reached as **vtable `+0x10`** of the vtable at `0x01243B38`.

### The class and its two implementations

The vtable at `0x01243B38` is installed by the constructor `FUN_00ad84cc`
(`stw r0,0(r3)` @`0xad8500`, with `r0` loaded from the literal-pool slot
`0x012975FC`, whose contents are `0x01243B38`). That pool also holds the string
`ndlib/net/net-session-manager-nd.cpp`, so this is the **ND** Session Manager.
A sibling vtable at `0x01243AE8` (same pool, next to
`ndlib/net/net-session-manager-lan.cpp`) has the identical slot layout with LAN
implementations - `+0x10` there is `FUN_00ad512c`. Two implementations of one
abstract interface; only the ND one is used on the retail network path.

`FUN_00ad84cc` also fixes the object's shape: it zero-fills four slots of
stride `0x9000` starting at `this+0x50`, and the object's total size is
`0x25060` (`addis r3,r28,2; addi r3,r3,20576` @`0xad8548`). `FUN_00ad5b78`'s
own prologue walks exactly that array (`addi r11,r3,80`, `ori r4,r4,36864`
= `0x9000`, `mtctr` 4, `cmpw` against `param_2` @`0xad5be4`-`0xad5c14`), which
independently confirms `r3 = this` (the session manager) and `r4 = the room
object`.

### The singleton

The constructed instance is stored into the global **`0x014DB270`**:
`FUN_00356284` calls `bl 0xad84cc` @`0x3562ac` and then `stw r28,0(r9)`
@`0x3562cc` with `r9 = *(0x0126FE20 - 31532) = 0x014DB270`.

### The two call sites

An exhaustive scan for `bctrl` dispatches whose CTR is fed by
`lwz rS,16(rV); lwz r0,0(rS)` finds exactly two that target this object:

| call site | containing function | debug string it logs |
|---|---|---|
| `0x0035D440` | `FUN_0035D1FC` | `"Host"` (`0x00E7C3B0`) |
| `0x003B7FB0` | `FUN_003B7D70` | `"****************** GATHER ******************"` (`0x00E7D648`) |

Both take `r3 = *(0x014DB270)` and `r4 = 0x01383BD8` - the well-known **game
room** object. Neither passes the party object, so **the party's own
`0x12f` is not sent from either of these two sites**; where a party RoomCreate
originates is still open (see "still open" below).

Arguments, decoded (parameter numbering matches `protos/0x12f_room_create.ksy`):

**`0x0035D440`** (`FUN_0035D1FC`, the "Host" state):

    35d3f8  lwz  r9,-32400(r30)     ; -> 0x014DB270
    35d400  lwz  r28,0(r9)          ; r3 = the session manager
    35d404  lwz  r9,0(r28)          ; vtable
    35d408  lwz  r29,16(r9)         ; slot +0x10 -> FUN_00ad5b78
    35d40c  bl   0x3a3dc8           ; -> max_players
    35d414  extsw r5,r3
    35d418  mr   r4,r26             ; 0x01383BD8, the game room
    35d424  li   r6,0               ; param_4  -> flag_27 = 0
    35d430  li   r7,-1              ; param_5  -> caller_arg_1c = 0xffff
    35d434  li   r8,0               ; param_6  -> room_flags_e8 OR-gate off
    35d43c  li   r9,0               ; 7th arg (see below)
    35d440  bctrl

**`0x003B7FB0`** (`FUN_003B7D70`, the "GATHER" state):

    3b7f3c  lwz  r9,-32392(r30)     ; -> 0x01459260 (the caps/entitlement register)
    3b7f40  lwz  r11,140(r31)
    3b7f44  li   r31,1
    3b7f48  lwz  r0,12(r9)          ; *(0x01459260+0xC)
    3b7f4c  cmpw cr7,r0,r11
    3b7f50  beq  cr7,0x3b7f58
    3b7f54  li   r31,0
    3b7f58  lwz  r9,-32580(r30)     ; -> 0x014DB270
    3b7f5c  lwz  r3,-32712(r30)     ; 0x0137D700
    3b7f60  lwz  r27,0(r9)          ; r3 = the session manager
    3b7f64  lwz  r9,0(r27)
    3b7f68  lwz  r29,16(r9)         ; slot +0x10 -> FUN_00ad5b78
    3b7f6c  bl   0x39f218           ; -> max_players
    3b7f74  mr   r28,r3
    3b7f78  lwz  r3,-32684(r30)     ; 0x01387F58, the PARTY object
    3b7f7c  bl   0xad2b14           ; the capability AND-reduce over the party
    3b7f84  lwz  r4,-32756(r30)     ; 0x01383BD8, the game room
    3b7f90  extsw r9,r3             ; 7th arg = the common capability mask
    3b7fa0  extsw r5,r28            ; param_3 = max_players
    3b7fa4  extsw r7,r26            ; param_5 -> caller_arg_1c
    3b7fa8  clrldi r8,r31,63        ; param_6 -> room_flags_e8 OR-gate
    3b7fac  li   r6,0               ; param_4 -> flag_27 = 0
    3b7fb0  bctrl

This directly resolves several previously-open field questions:

* **`caller_arg_1c`.** The live `ff ff` comes from `li r7,-1` at the "Host"
  site; the live `00 00` comes from the GATHER site's `r26`. It is a
  caller-supplied token, constant per path, not a runtime quantity - which is
  consistent with the two observed values and nothing else.
* **`flag_27`.** Both call sites pass `li r6,0`, so `flag_27` is `0` on both
  known paths. The live `0x04` values must therefore come from a third,
  as-yet-unlocated call site (the same gap as the party's RoomCreate).
* **`max_players`.** At the GATHER site it is `FUN_0039f218()`, which is
  `FUN_00349360()->+0x18` - a field of the current game-mode descriptor, not a
  constant. That explains why it is live-constant 8 without being hardcoded.
* **`room_flags_e8`'s `0x40000000` OR-gate** (`param_6`). At the "Host" site it
  is hardcoded `0`; at the GATHER site it is `1` **iff** `FUN_003a1f5c() != 0`
  **and** `*(u32*)(0x01459260+0xC) == *(u32*)(r31+0x8C)`. `0x01459260+0xC` is
  exactly the caps/entitlement register that
  `protos/common/member_data.ksy` already names as `capability_flag`'s
  producer. So the OR fires only when the local entitlement word matches the
  candidate's - i.e. an "identical content" marker. Both live observations saw
  it false, which is consistent: it needs a specific candidate to compare
  against.
* **A seventh argument exists.** Both sites set `r9` before the `bctrl`, and at
  the GATHER site `r9` is the party-wide capability AND-reduce
  (`FUN_00ad2b14`). `FUN_00ad5b78` **ignores it** - `r9` is first written at
  `0xad5be4` (`clrldi r9,r11,32`) with no prior read - and so does the LAN
  sibling `FUN_00ad512c` (which also discards `r6`/`r7`/`r8`, clobbering `r8`
  at `0xad5134` before any read). So the interface is
  `f(this, room, max_players, p4, p5, p6, caps)` with the ND implementation
  using the first six. The same 7-argument shape appears on the sibling
  **RoomJoin** builder at vtable `+0x14` (`FUN_00ad6c70`, called at
  `0x003B6230`, also preceded by `bl 0xad2b14` on the party at `0x003B61F0`).

### Item 1 update: the party's `0x12f` caller - RESOLVED, live, 2026-08-20

The gap above was closed the same day with a live RPCS3 breakpoint at
`FUN_00ad5b78` (`0xad5b78`) hit during a real party join. Register state at
entry confirmed `r4 = 0x01387F58` (the party object) and `LR = 0x003CAC60`,
pinning the exact call site.

The call is at `0x003CAC5C`, inside **`FUN_003CA9D0`** - the same 9-state
room-state-machine function this project already cites elsewhere
(`protos/0x13f_host_flag_updated.ksy`, `docs/protocol/proto-map.md`) as
gating a block on `room_obj+0x19f4`. It dispatches through a `bctr` jump
table at `0x003CAA9C` (9 entries); the call sits in the block reached by
table entry 1 (offset `0xE4` -> `0x003CAB84`), specifically the branch taken
when `*(party_obj+0x1A50) == 0` (`ld r28,6736(r31); cmpdi cr7,r28,0;
beq -> 0x3cac00` @`0x3cabb0`-`0x3cabb4`) - i.e. the party has no room
created for it yet. That whole block is only reached when the already-
documented counted-match latch is clear (`bl 0x3abf68` @`0x3cab8c`, reading
`g_70[0x6C]`; `bne -> 0x3cb130` skips it otherwise - see
`research/notes/2026-08-17-match-counts-latch.md`).

This confirms the third-dispatch hypothesis over the alternative (the scan's
pattern was too narrow, not that the party takes some non-vtable path): it
IS the same `bctrl`-through-vtable-`+0x10` shape, just from a call site
outside the 40-instruction search window the original scan used, inside a
function with a much larger, jump-table-driven body than the two "Host"/
"GATHER" state functions.

Resolves both remaining field gaps from item 1: `flag_27`'s live `0x04`
(`r6=1` at this site; `flag_27 = 4 iff param_4 != 0`) and reconfirms
`caller_arg_1c`'s `0xffff` (`r7 = 0xFFFFFFFF` here too, matching both static
sites - apparently constant across every known call site rather than
path-specific). `room_flags_e8`'s gate is off here (`r8=0`), consistent with
both prior samples. All three known `0x12f` call sites are now fully
decoded. Full detail: `protos/0x12f_room_create.ksy`'s doc-level caller
note.

## 2. `0x13e` kind=3's vtable+0x18 selector - RESOLVED (mechanism), PARTIAL (semantics)

The call at `0xad6b8c` selects between the RAW (`param_3` verbatim, 0/1) and
ENCODED (3-or-0) encodings of the flag byte. Tracing the object:

    ad6b54  lwz  r9,-32748(r30)     ; pool 0x0129F5C0 - 32748 = 0x012975D4
                                    ; contents: 0x01441194
    ad6b68  lwz  r9,4(r9)           ; the object = *(u32*)0x01441198
    ad6b74  lwz  r9,0(r9)           ; vtable
    ad6b78  lwz  r9,24(r9)          ; slot +0x18
    ad6b8c  bctrl

`*(u32*)0x01441198` is the same object `FUN_00ad5b78` queries for
`value_20`/`value_22` (`lwz r22,-32748(r30)` @`0xad5c50`, `lwz r3,4(r22)`
@`0xad5c68`, `bl 0xacb6bc`, which is just
`out1 = this->f32@+0x48; out2 = this->f32@+0x4C`). Its class is constructed by
**`FUN_003ac2e8`**: that function calls the abstract base's constructor
`FUN_00acb6d0` (which installs the all-pure-virtual vtable `0x01243A18`), then
overwrites it with the derived vtable **`0x01224178`**
(`lwz r9,-32704(r30)` / `stw r9,0(r29)` @`0x3ac314`-`0x3ac31c`), and initialises
`+0x48`/`+0x4C` to 0 (`stw r11,72(r29)` / `stw r11,76(r29)` @`0x3ac38c`-`0x3ac390`)
- the very floats `FUN_00acb6bc` reads back. That cross-check makes the class
identification solid.

### What vtable+0x18 does

`0x01224178 + 0x18` is **`FUN_003abe4c`**, a nine-instruction pure getter:

    3abe4c  lwz   r0,856(r3)     ; r0 = *(u32*)(this + 0x358)
    3abe50  xori  r0,r0,2
    3abe54  srawi r9,r0,31
    3abe58  xor   r3,r9,r0
    3abe5c  subf  r3,r9,r3       ; r3 = abs(r0 ^ 2)
    3abe60  addi  r3,r3,-1
    3abe64  srwi  r3,r3,31       ; r3 = (r0 == 2)
    3abe68  extsw r3,r3
    3abe6c  blr

i.e. **it returns 1 iff `this->field_0x358 == 2`, else 0**. So the `0x13e`
kind=3 flag encoding is:

    field_0x358 == 2  ->  RAW      : flag = param_3 (0 or 1)
    field_0x358 != 2  ->  ENCODED  : flag = param_3 ? 3 : 0

That is the complete answer to "what selects between the two encodings", and it
explains the live distribution recorded in
`protos/0x13e_set_host_flag.ksy`: `(3,3) x35` and `(0,3) x35` are the ENCODED
path, `(1,3) x2` is the RAW path - the RAW path is rare because
`field_0x358 == 2` is a rare state.

### What `field_0x358` is - partially pinned

It is a small enum, written only with the literals 0, 1 and 2 (plus a few
copies of a stored value), always on instances of this class. Restricting a
literal-pool-tracked scan to stores/loads whose base register provably holds
the static instance `0x013835C0` gives:

* `= 0` at `0x3ac368` (construction), `0x35ef90`, `0x33c37c`
* `= 1` at `0x3b5908`, `0x3b5b04`, `0x3bf3f4`
* `= 2` at `0x35bf88`, `0x35d5c0`, `0x35f174`
* copied from a local at `0x35bacc`, `0x35d9c4`, `0x35de98`

`FUN_0035D59C` - the tiny function immediately following `FUN_0035D1FC`, the
`"Host"`-state function that issues the RoomCreate in item 1 - is the clearest
of these: it sets the field to 2 and broadcasts the same value as net-event 272
(`li r3,272`, `bl 0x3c9d20` @`0x35d5dc`-`0x35d5e4`), gated on
`FUN_00ad0eec(0x01387F58)` (a party predicate).

Readers corroborate that it is a role/mode selector rather than a counter:
`0x0039F314` and `0x0039F398` take the "we have a game-mode descriptor" branch
only when it equals **1**; `0x003A41D0` **skips** the `*net-games*` lookup
entirely when it equals **2**; `0x003C05B4` uses it directly as an index into a
12-byte-stride runtime table (`mulli r9,r9,12`), which bounds the enum to a
handful of values.

Reading, stated at the confidence it deserves: `field_0x358` is a
three-valued net-session role/mode, `2` is the value the `"Host"` state
installs, and the `0x13e` kind=3 sender uses the raw 0/1 encoding in that state
and the 3-or-0 encoding otherwise.

### Value `1`, live-confirmed 2026-08-20 (breakpoint at the writer `0x3b5908`)

Two independent hits, both accounts, both in the same broad phase: on
`comradesean`, the write fired during the post-match results screen's
survivor-count update; on `mgnomad2`, it fired slightly later in the same
overall flow, after picking a new mission from the post-match menu (not
during the survivor-count update itself). Both are the results-screen ->
next-step handoff, not simultaneous frames of the same instant - consistent
with `field_0x358` marking a PHASE (a state the game is in for a stretch of
time) rather than a single-frame event, and consistent with the
already-documented reader corroboration: `0x0039F314`/`0x0039F398` only take
the "we have a game-mode descriptor" branch when this field equals `1`,
which is exactly what resolving "what mission comes next" needs. Reading:
**`field_0x358 == 1` marks the post-match results/mode-resolution phase** -
the stretch between a match ending and a new mode descriptor being resolved
for whatever comes next (menu, new mission, requeue). Not yet distinguished
from a possibly narrower reading (e.g. specifically "post-match", vs. more
generally "any mode-descriptor-pending state") - a hit during a NON-post-match
mode transition (e.g. entering matchmaking fresh from the main menu) would
settle that distinction, but the phase-level reading above is solid on
current evidence.

### Value `0`, live-confirmed 2026-08-20 (breakpoint at the writer `0x35ef90`)

Hit on `comradesean`'s client at the moment of confirming "Leave
Matchmaking" (clicked, then confirmed "Yes" on the follow-up prompt).
Matches the inference exactly: **`field_0x358 == 0` is the idle/no-active-
role state**, entered when leaving/cancelling matchmaking - the same value
construction (`0x3ac368`) sets, now confirmed as a real reset transition and
not just a static default.

### All three values closed

    0  idle / no active role       - live: "Leave Matchmaking" -> Yes
    1  post-match results / mode-resolution phase
                                    - live: survivor-count update; post-match
                                      mission selection
    2  "Host" (party-creation state)
                                    - static: FUN_0035D59C, immediately after
                                      the "Host" RoomCreate state, gated on a
                                      party predicate

Every value now has at least one live correlation. `kind=3`'s RAW-vs-ENCODED
selector (`field_0x358 == 2`) reads correctly in light of this: the RAW 0/1
encoding is used specifically in the "Host" state, and the ENCODED 3-or-0
form is used in both other states (idle and post-match) - i.e. RAW is
reserved for the one state where becoming/ceasing host is the actual
operation being performed, and ENCODED is the general-purpose form used
everywhere else.

### The runtime table, read live - structure confirmed, names still open

A live read of `0x013859A8` (RPCS3 memory viewer, 2026-08-20) gives:

    013859a8: bdb14168 b530fe7b 022b777d
    013859b4: 04333f76 b530fe7b 022b777d
    013859c0: 00d93d9d 7e2c2757 a7304dd3
    013859cc: 00000001 013885c0 01388740

This confirms the 12-byte stride `0x003C05B4` was already known to use, and
bounds the table to exactly **3 entries** - matching the enum's confirmed
0/1/2 range exactly, since word 0 of the fourth "entry" (`0x00000001`) is not
hash-shaped, and the two words after it (`0x013885c0`, `0x01388740`) are
plain heap pointers into this project's already-familiar `0x0138xxxx` object
region - i.e. a *different* structure (a count + two pointers) begins right
after the table, not a fourth table row. So the table is `0x013859A8`
through `0x013859CB`, no more.

Two of the three fields repeat verbatim between entry 0 and entry 1
(`b530fe7b`, `022b777d`) while only the first word differs (`bdb14168` vs
`04333f76`) - consistent with a `{name_hash, category_hash, icon_hash}`-
shaped record where states 0 and 1 share a category/icon and differ only by
name, the same general shape this project's other DC-backed catalogs use
(e.g. `*net-maps*`, `*net-stats*`).

All six distinct words look like `crc32_mpeg2` hashes (this project's
standard DC hash) but did NOT resolve against `research/tools/dc_hash_crack.py`,
tried twice with a widening corpus: first `bin.psarc` + `paks.txt` alone (no
match), then broadened to `bin.psarc` + `pak23.psarc` + `actor34.psarc` +
`paks.txt` + `pak23.txt` + `banks.txt` + both `*-audio-precache.txt` manifests
(50,676 unique candidate tokens) - still no match on any of the six values.
Either these hashes are keyed from a source string this project's known disc
archives don't contain as plaintext (the .dci corpus only covers DC-compiled
modules; a UI/debug-label string not compiled through DC would never appear
in it), or they hash something other than a plain symbol name. Naming the
three states therefore still needs a live breakpoint on one of `field_0x358`'s
three writer sites with the game in each state, or a wider hash-crack source
(the 01.11 disc's own `build/main`, if its `.dci`/manifest files are ever
found - the 01.11 install checked for this project so far only has the
patch's promo/DLC content, not a full `build/main`).

## 3. `0x142 HostRank`'s per-u16 encoding - FULLY RESOLVED, 2026-08-20 (live, later same day)

This is the item that changed the most. The existing documentation describes
the value as "that player's `vtable[0]` getter return... a per-player rank".
The getter has now been identified and read, and **it is not a rank; it is a
packed pair of small integers**.

### The player class and its vtable

`FUN_0039b720` emits `out_u16[i] = (u16)player->vtable[0](player)` (`bctrl`
@`0x39b920`, `sth r3,0(r9)` @`0x39b934`), with
`player = 0x0137D700 + i*0x920 + 0x40`.

The manager's constructor `FUN_0039BF10` installs the manager's own vtable and
then runs the eight player sub-object base constructors
(`bl 0x3d5518` @`0x39bf5c`, stepping `r31` by `0x920` from `r3+0x40`), which
install the **all-pure-virtual** base vtable `0x01224468`. The concrete vtable
is installed later, by `FUN_0039C464`:

    39c478  lwz r9,-32728(r30)   ; 0x0137D700
    39c47c  lwz r0,-32612(r30)   ; 0x01224148 (the manager's vtable)
    39c480  lwz r31,-32592(r30)  ; 0x01381720  (last player slot)
    39c484  stw r0,0(r9)
    ...
    39c48c  addi r31,r31,-2336   ; -0x920
    39c490  lwz r0,-32580(r30)   ; 0x0137CE20 (loop sentinel)
    ...
    39c4a0  lwz r0,-32576(r30)   ; 0x01224438  <-- the player vtable
    39c4ac  stw r0,0(r9)

`0x0137CE20 + 0x920 = 0x0137D740 = 0x0137D700 + 0x40`, exactly player slot 0,
and `0x01381720` is slot 7 - so all eight player sub-objects get vtable
**`0x01224438`**, whose slot 0 is **`FUN_003CD6C8`**.

### The getter, read instruction by instruction

    3cd6c8  lbz    r0,432(r3)    ; a = *(u8*) (this + 0x1B0)
    3cd6cc  lwz    r9,424(r3)    ; b = *(u32*)(this + 0x1A8)
    3cd6d0  cmpwi  cr7,r0,0
    3cd6d4  clrlwi r9,r9,20      ; b &= 0x0FFF
    3cd6d8  cmpwi  cr6,r9,0
    3cd6dc  beq    cr7,0x3cd6e8  ; a == 0 -> no marker
    3cd6e0  beq    cr6,0x3cd6e8  ; b == 0 -> no marker
    3cd6e4  addi   r9,r9,2048    ; b += 0x800
    3cd6e8  lwz    r3,428(r3)    ; c = *(u32*)(this + 0x1AC)
    3cd6ec  slwi   r3,r3,12      ; c <<= 12
    3cd6f0  add    r3,r9,r3
    3cd6f4  extsw  r3,r3
    3cd6f8  blr

So the wire u16 is:

    entry = ((b & 0x0FFF) + (0x800 if a != 0 and (b & 0x0FFF) != 0 else 0))
            + (c << 12)

**Low 12 bits** = a small per-player quantity, with **bit 11** used as a
conditional marker; **high 4 bits** = a second small tag. It is a bitfield, not
a scalar - which is why "the numeric encoding" never resolved as a number.

### Where the three inputs come from

All three are written by **`FUN_0039F75C`**
(`f(r3 = manager, r4 = room, r5 = member-slot pointer, r6, r7)`, prologue
`0x39f794`-`0x39f7a8`), which the callers run once per room member after
enumerating them with `FUN_00ad2768` (e.g. `0x003596F0`, `0x003B29E4`,
`0x003B79A8`, all with `r4 = 0x01383BD8`, the game room):

| player field | written at | value |
|---|---|---|
| `+0x1A8` (`b`) | `0x39fa34` (when `param_5 == 0`) | `*(u32*)(member_slot + 0xE8)` |
| `+0x1A8` (`b`) | `0x39fa90` (when `param_5 != 0`) | a global `u8` counter that post-increments by 2 (`lbz r9,0(r11); addi r0,r9,2; stw r9,424(r31); stb r0,0(r11)`) |
| `+0x1AC` (`c`) | `0x39fa64` | `param_4` (`r6`) verbatim |
| `+0x1B0` (`a`) | `0x39fa6c` | `param_5` (`r7`) verbatim, as a byte |

and `FUN_003D52E4` (the player slot reset) zeroes `+0x1A8`/`+0x1AC`
(`0x3d5340`/`0x3d5344`).

`member_slot + 0xE8` is itself wire-sourced. In the `0x131 Member` receive arm,
`lhz r0,0(r7)` @`0xad7854` (with `r7 = entry + 36`, the same register the
already-documented `lbz r0,2(r7)` @`0xad7858` and `lbz r9,3(r7)` @`0xad79b0`
use for entry offsets 38 and 39) stores the entry's **`member_id`** into the
80-byte local struct at `+0x38` (`sth r0,208(r1)`, local base
`addi r29,r1,152` @`0xad7814`), and `FUN_00ad33d8` copies that to the member
slot: `lhz r9,56(r29)` / `stw r9,232(r31)` @`0xad34e8`-`0xad34f0`, with
`r29 = param_2` (the local struct, `mr r29,r4` @`0xad3408`) and
`r31 = room + 0x668 + slot*0x180`.

So the traced chain is:

    0x131 entry.member_id (u16, entry+36)
      -> local_struct + 0x38            (0xad7854)
      -> member_slot  + 0xE8            (0xad34f0)
      -> player       + 0x1A8           (0x39fa34)
      -> low 12 bits of the 0x142 u16   (0x3cd6c8)

### Live corroboration, and the part that does NOT add up

Re-counting `server/logs/wire.jsonl` (187 `0x142` frames) refines the "always
`0x0002`" claim in two ways worth recording:

* One frame carries **`count=2` with entries `0x0002, 0x0003`** - consecutive.
  Raw frame: `0000014200020060012723d801383bd800020003`. So the value is not a
  global constant; with two qualifying players it is two adjacent small
  integers. That is the signature of a per-member sequential id, and is very
  hard to reconcile with "rank".
* Every single-entry frame reads `0x0002`, across **ten distinct connections**
  including solo-host sessions.

The unresolved part: this server assigns `MEMBER_ID = 1` to the host, and
`0x131` frames in the same log always contain an entry with `member_id == 1`,
yet no `0x142` frame ever reports `1`. If `b` were simply the local player's
`member_id`, a solo host should send `0x0001`. Candidate explanations not
distinguished here: one of `FUN_0039b720`'s seven filters
(`0x39b7d4`-`0x39b838`, notably `*(u32*)(player+0x1AC) != 1` @`0x39b818`)
systematically excludes member 1; or the `param_5 != 0` counter branch is the
live one and the `+0x800` marker is suppressed some other way; or `b` picks up
a different write. **Stated plainly: the arithmetic and the writers are proven,
the mapping from the live `0x0002` onto a specific input is not.**

### Live follow-up, 2026-08-20: the counter-branch candidate is ruled out

A breakpoint at `FUN_0039F75C`'s entry (`0x39f75c`) was hit five times across
a solo game, two find-match sessions, and post-loadout, on both
`comradesean`'s and `mgnomad2`'s clients independently. **`r7` (`param_5`)
was `0` in every single hit.** Re-reading the disassembly at `0x39fa28`-
`0x39fa70` confirms `r7`/`param_5` is exactly what selects the branch: `0`
takes the `member_slot+0xE8` path (`lwz r0,232(r26)` @`0x39fa28`,
`stw r0,424(r31)` @`0x39fa34`) and skips the counter block entirely
(`beq cr7,0x39fb24` @`0x39fa70`); the store is unconditional first and the
counter block, if reached, would overwrite it afterward. Since `param_5` was
never nonzero in any live sample, **the "counter branch is live" candidate
explanation is ruled out** - `member_slot+0xE8` is confirmed as the actual
source of `b` in every tested scenario (solo, find-match, and post-loadout
alike).

This also incidentally confirmed the per-member loop shape live: the
find-match session hit this breakpoint twice in a row from the same caller
(`LR=0x3b29e8`), once with `r5` pointing at `mgnomad2`'s member slot and once
at `comradesean`'s - one call per room member, as the note above already
inferred from the static enumeration call (`FUN_00ad2768`).

Remaining candidates: (1) one of `FUN_0039b720`'s filters at `0x39b818`
excludes member 1 from the `0x142` array entirely, or (3) `member_slot+0xE8`
does not actually hold `1` for the HOST's own slot the way it holds a real
member_id for a remote member's slot - e.g. if the local player's own roster
entry is populated through a different path than the `0x131`-receive-arm
chain traced above. Distinguishing these needs either confirming/refuting a
hit at `0x39b818`, or a direct memory read of `*(u32*)(member_slot+0xE8)` for
the host's own slot at the moment `FUN_0039F75C` runs for it (the slot
pointer is `r5`/`r26` at entry, and its first bytes are readably the
player's own NpId text - `r5` itself identifies which player is being
processed on any given hit).

One genuinely new constraint that IS proven and is useful to a server: the same
`vtable[0]` getter is called earlier in the same loop as a **boolean filter**
(`bctrl` @`0x39b7fc`, `cmpwi r3,0; beq skip` @`0x39b804`-`0x39b808`), so a
player whose getter returns 0 is never emitted. **A legitimate `0x142` entry can
never be zero.**

Also recovered while tracing (useful for `0x131`): the player slot mirrors the
member slot as `player+0x3C0 = slot+0xF0`, `player+0x3C4 = slot+0xE4`,
`player+0x3C8..0x3E7 = the 32-byte member_data card`; and `slot+0xE4` is a
per-room monotonic counter allocated at `0xad371c` from `room+0x19E8`.

### The full resolution: `0x142` reports OTHER members' ids, never the sender's own

Five live breakpoint hits at `FUN_0039F75C`'s entry (solo game, two
find-match sessions, post-loadout, both accounts) all showed `param_5=0`
(`r7`), which the disassembly confirms always takes the `member_slot+0xE8`
write path and never the counter path (see the "Live follow-up" subsection
above) - so `b = member_slot+0xE8` is proven correct in every tested case,
including two direct memory reads: a HOST's slot (as copied on the joiner's
own client) read `1`, and a player's own self-slot read its own `member_id`
(`2`) correctly. Both matched the expected `member_id` exactly.

And yet **no live `0x142` frame has ever reported `1`**, including several
sent in the same session as those confirmed-correct memory reads. The
resolution came from correlating `server/logs/wire.jsonl` (per-connection
wire capture) against `server/logs/session_manager.log` (which records the
server's own room-registry `member_id` for each connection) for two
independent, real matches with SWAPPED host/joiner roles:

* Room `5000000601383bd8`: server registry confirms connection 2
  (`mgnomad2`) is `member_id=1` (host) - a `0x13a` from the SAME connection,
  seconds after its `0x142`, is logged `"SetPartyData from member_id=1"`.
  That connection's own `0x142` (`...00010060...0002`) reports entry `2` -
  `comradesean`'s (the joiner's) id, not its own.
* Room `5000001b01383bd8`: server registry confirms `comradesean`'s
  RoomCreate got `member_id=1` (host) and `mgnomad2`'s later RoomJoin got
  `member_id=2`. `comradesean`'s own `0x142` from this room ALSO reports
  entry `2` - again the joiner's id, not the host's own `1`.
* The historical 3-member room `012723d801383bd8` (`comradesean` host,
  `member_id=1`, throughout its history in the log) produced the one
  `count=2` frame on record, entries `[2, 3]` - both OTHER members present at
  the time, again excluding the host's own `1`.

Three independent matches, two of them with the host role on opposite
accounts, all agree: **the host's own `0x142` lists every OTHER room
member's `member_id`, and structurally never its own.** This is not a
coincidence of a 2-player test pool - it explains every observed count too:
`count=0` in every custom/solo-host frame (no other members exist to list),
`count=1`/entry`=2` in every 2-player find-match frame (exactly one other
member, always the server's first-assigned joiner id), `count=2`/entries
`[2,3]` in the one 3-member capture. The exclusion must happen inside
`FUN_0039b720`'s own filter chain (the seven-filter loop this note already
partially traced), not in the write path this pass fully vindicated - which
filter specifically drops the local/self player was not pinned down this
pass, but its EFFECT is now proven beyond the reasonable doubt a live,
role-swapped, multi-match correlation provides.

Given this, the message's own name - `HostRank` - reads correctly at face
value for the first time: it is the host reporting the OTHER participants
present, not a self-report. Whatever the wire integer actually MEANS
(still an open, lower-priority question - `member_id` is what has been
proven to reach the wire, but whether the retail UI/backend then treats
that id as a literal "rank" of some kind is undetermined) is now a separate
question from "whose id is this", which is fully closed.

## 4. `capability_flag` bit 1 - RESOLVED as unused, by enumeration

### The reduce itself, re-read

`FUN_00ad2b14(room)` is exactly as documented:

    ad2b44  li   r28,-1                 ; identity = 0xFFFFFFFF
    ad2b54  bl   0xad2768               ; enumerate the room's members
    ad2b5c  lwz  r4,4(r9)               ; member pointer
    ad2b60  bl   0xad2650               ; -> the member's 32-byte card, or NULL
    ad2b68  beq  cr7,next               ; NULL -> skip
    ad2b6c  lbz  r0,8(r3)               ; card + 8 = capability_flag
    ad2b70  and  r28,r28,r0
    ad2b9c  clrldi r3,r28,32            ; return

Note the identity: a room with no members returns `0xFFFFFFFF`, not 0.

### Every consumer of the reduce

`FUN_00ad2b14` has exactly **five** call sites in the binary:

| site | what happens to the result |
|---|---|
| `0x0035AD78` | `lwz r0,20(r29); and r9,r3,r0; cmpwi r9,0` @`0x35ad80`-`0x35ad88` - a bit-AND gate against a descriptor's `+0x14` |
| `0x003A25A8` | `lwz r0,20(r29); and r3,r3,r0; cmpwi r3,0` @`0x3a25b0`-`0x3a25b8` - the same gate, in the map-list filter loop |
| `0x003B61F0` | passed as an argument to the **RoomJoin** builder (vtable `+0x14`, `FUN_00ad6c70`) at `0x003B6230` |
| `0x003B7F7C` | passed as the 7th argument to the **RoomCreate** builder (vtable `+0x10`, `FUN_00ad5b78`) at `0x003B7FB0` - **and dropped**, see item 1 |
| `0x003B6BFC` | `lwz r0,48(r29); cmpw cr7,r3,r0; bne -> reject` @`0x3b6c04`-`0x3b6c0c` - a whole-value **equality** test against a room-search candidate's own advertised mask at `+0x30` |

### Is `0x35AD84` a different table? No.

This was the specific hypothesis to test, and it is **disproved**. At
`0x0035AD78` the descriptor `r29` comes from `bl 0x3a3e94` @`0x35aafc`, and
`FUN_003A3E94` reads:

    3a3ea4  lis r3,15258 / ori r3,r3,1661   ; 0x3B9A067D
    3a3eb4  bl  0x9fa9b8                    ; DC global lookup by hash
    3a3ec8  lhz r0,18816(r31)               ; index = *(s16*)(gamemgr + 0x4980)
    3a3ee8  mulli r9,r3,112                 ; stride 112
    3a3f04  lwz r31,4(r9)                   ; entry + 0x04 = a map-name hash
    3a3efc  lis r3,3564 / ori r3,r3,38820   ; 0x0DEC97A4
    3a3f08  bl  0x9fa9f4                    ; DC global lookup by hash
    3a3f40  mulli r0,r11,76                 ; stride 76
    3a3f50  lwz r0,0(r9) / cmpw r0,r31      ; find the matching map entry

`crc32_mpeg2("*net-maps*") = 0x0DEC97A4` and
`crc32_mpeg2("*net-games*") = 0x3B9A067D`, both confirmed against the decoded
DC directory (`*net-games*`: 28 entries x 112 on 01.00, 65 on 01.11). So
`0x35AD84` resolves a `*net-games*` row to a `*net-maps*` row and then tests
**the same `*net-maps*` `+0x14` column** as `0x3A25B4`. There is no second
capability table.

(Worth recording from the same function: `0x0035AB24` performs an additional
AND against that identical `+0x14` column using
`*(u32*)(0x01459260 + 0xC)` - the raw local entitlement register - instead of
the party-wide reduce. Same column again.)

### The column's contents, both bundles

Decoded straight out of the bundles (`*net-maps*` `+0x14`, stride 76):

* `dc1/net.bin` (01.00): 8 entries, **every mask is `0x00000000`**.
* `net10.bin` (01.11): 19 entries; masks `0x01` (x4), `0x04` (x4), `0x08` (x2),
  `0x00` (x9). **`0x02` appears nowhere.**

The all-zero 01.00 table is not a contradiction: both gate sites explicitly
short-circuit a zero mask (`lwz r0,20(r29); cmpwi cr7,r0,0; beq skip`
@`0x3a2598`-`0x3a25a0`), i.e. a candidate that requires nothing is always
eligible, so on 01.00 the capability gate never fires at all.

### Is bit 1 read anywhere else?

The byte itself (`card + 8`) has essentially one consumer. Of the 13 call sites
of the card getter `FUN_00ad2650`, only one reads offset 8 from the returned
pointer - `0xad2b6c`, the reduce. The player object's mirror of the card
(`player + 0x3C8`, so `capability_flag` at `player + 0x3D0` = 976) has no
reader in the player translation unit either.

**Conclusion.** Bit 1 (`0x02`) is required by no map descriptor in either
bundle, and there is no second gate that could require it: the reduce's result
reaches exactly two bit-AND tests (both the same `*net-maps*` column), one
whole-mask equality test, and two wire arguments. The only way bit 1 can affect
behaviour at all is through the whole-mask equality at `0x003B6C08`, which
compares the entire value rather than any bit. So the existing guidance stands
and is now stronger than "no map uses it": **nothing uses it.** The live 01.11
value `0x0d` (= bits 0, 2, 3) is exactly the set of bits that are meaningful.

Caveat on the sweep, stated for the same reason the `attr_tail` note states
its own: the `FUN_00ad2650` scan follows the returned pointer only through
direct `mr`/`clrldi` renames within 120 bytes and stops at the next `bl`, so a
consumer that stashes the card pointer and reads `+8` much later, or reads it
through a runtime-computed index, would evade it.

## Summary of status changes

| item | before | after |
|---|---|---|
| `FUN_00ad5b78`'s caller | untraced (`bctrl` through vtable `+0x10`) | **all three call sites resolved** with all arguments named - two static ("Host"/"GATHER" game-room states), one live (the party path, `FUN_003CA9D0`'s 9-state machine, closing the `flag_27`/`caller_arg_1c` gaps too) |
| `0x13e` kind=3's encoding selector | "not yet traced" | **resolved**: `*(u32*)(netsession + 0x358) == 2` selects RAW over ENCODED; the enum's value names are partial |
| `0x142`'s per-u16 encoding | "needs a ranked account" | **structure resolved**: a 12+4 bitfield with a conditional bit-11 marker, all three inputs and their writers located; it is **not a rank**. Which input produces the live `0x0002` is unreconciled |
| `capability_flag` bit 1 | "required by no map descriptor" | **closed**: no consumer of any kind exists; the second gate site reads the same table, not a different one |
