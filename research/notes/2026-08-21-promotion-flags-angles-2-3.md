# `promotion_flags_1e74`: chasing the two angles left open by the DLC hypothesis pass

Date: 2026-08-21. Static only, no live RPCS3 session. Follows
`research/notes/2026-08-21-profile21-zero-region-walk.md` (found the six
BE u32 words at `P+0x1E74..0x1E8B`, no EBOOT writer in 01.00) and
`research/notes/2026-08-21-promotion-flags-dlc-hypothesis.md` (re-checked
01.11, still no writer, flagged two angles as not fully chased: relocating
the `0x01459260` entitlement/capability register to 01.11, and
name-cracking `net10.bin`'s 46 new hash-only globals). This note chases
both, plus a third lead that turned up along the way (the 01.11 install's
own `promo1/` PSN entitlement files).

## Angle 1: the entitlement register, relocated to 01.11

### Method

`research/notes/2026-08-20-followup-open-items.md` §1 established that
01.00's register lives at fixed address `0x01459260`, reached in
`FUN_003B7D70` (the "GATHER" RoomCreate state) via
`lwz r9,-32392(r30)` where `r30` is that function's own per-TU literal-pool
anchor. Re-derived and confirmed in this pass: `r30 = *(0x01305870-31056) =
0x01271B1C` (`0x3B7D7C`'s `lwz r30,-31056(r2)`), slot
`0x01271B1C-32392 = 0x01269C94`, `*(0x01269C94) = 0x01459260`. Matches the
prior note exactly.

Relocating this to 01.11 needed the register's actual *consumer*, not the
constant itself (a raw data-segment pointer constant can't be found by
signature the way code can). The path:

1. Found the 01.11 counterpart of `FUN_003B7D70` by the same string-anchor
   technique the DLC-hypothesis note used for the profile accessor: the
   debug string `"****************** GATHER ******************"` sits at
   `0x00EB0138` in the 01.11 executable segment (found by raw byte search,
   `/`), its pointer is stored at data slot `0x0129BB38` (found by
   searching both LOAD segments for the 4-byte BE value `0x00EB0138`), and
   `scan_anchor`-style tracing (a new `eb111.py`/anchor-scan pair written
   for this pass, same technique as `research/tools/eboot_analysis/
   scan_anchor.py`, pointed at 01.11's segments and R2 `0x01338de0`) finds
   exactly one instruction reaching that slot: `0x003D1FF4` (`lwz
   r3,-32244(r30)`), inside the function starting at `0x003D1FD4`. This is
   01.11's "GATHER" state function.
2. Read `0x003D1FD4` in full (`0x3D1FD4..0x3D25B8`). It has the same shape
   as 01.00's `FUN_003B7D70`: profile-accessor calls (`bl 0x3E6ADC`,
   01.11's confirmed universal accessor per the DLC-hypothesis note),
   `bl 0x3B84E4` for max_players, a vtable `+0x10` `bctrl` RoomCreate call
   at `0x3D2400` with the same 7-argument shape (`r3`=session manager,
   `r4`=game room, `r5`=max_players, `r6=0`=`flag_27`, `r7`=`caller_arg_1c`,
   `r8`=`room_flags_e8` OR-gate boolean, `r9`/`r10`=capability mask) as
   both 01.00 call sites.
3. The `room_flags_e8` OR-gate boolean (`r8 = clrldi(r25,63)` at
   `0x3D23F4`) is set via `r25=1; bl 0x0037C85C; ...; beq -> keep 1, else
   r25=0` (`0x3D2340-0x3D235C`) instead of 01.00's inline compare. Reading
   `FUN_0037C85C` (`0x37C85C..0x37C900`) shows it is **both** of 01.00's
   two mechanisms fused into one helper: it iterates the party's members
   building an 8-bit capability-mask reduction (`ld r0,144(r7)` per member,
   `slw`/`or` accumulate - the 01.11 refactor of `FUN_00ad2b14`, the party
   capability AND-reduce), **then ANDs it against `*(reg+0xC)`** where `reg
   = *(anchor-32764)` (`lwz r9,-32764(r30); lwz r5,12(r9)` at
   `0x37C878-0x37C87C`) - the exact same `+0xC` displacement 01.00 used on
   `0x01459260`.
4. Resolving that slot: `FUN_0037C85C`'s own anchor is `r30 =
   *(0x01338DE0-31160) = 0x012A27DC` (`0x37C860`'s `lwz r30,-31160(r2)`),
   slot `0x012A27DC-32764 = 0x0129A7E0`, `*(0x0129A7E0) = 0x01502808`.

### Result: **`0x01502808` is the 01.11 relocation of the entitlement/capability register**

Confirmed by a second, independent consumer sharing the same anchor and
slot: `FUN_0037C95C` (`0x37C95C..0x37CBD4`, immediately adjacent to
`FUN_0037C85C` in the same translation unit) also does `lwz
r4,-32764(r30)` (`0x37CA60`) against the identical resolved anchor, reads
16 bytes from the pointed-at struct (`ld r0,8(r9); ld r9,0(r9)`, copied
byte-by-byte into a local buffer), and passes them into `bl 0x9EC964`
together with a per-party-member loop index, writing a bit into
`party_obj+144` (`r10 = r27+144`, `stdx` at `0x37CB8C`) - i.e. this is the
per-member capability/entitlement bit-setter for the party roster, the
same functional role `capability_flag` (`protos/common/member_data.ksy`)
already documents, just refactored across two helper functions instead of
inlined in the RoomCreate-state function directly.

`scan_anchor`-equivalent search for the slot `0x0129A7E0` binary-wide in
01.11 (i.e. "who else loads this register pointer") returns **exactly
these two sites** (`0x0037C878`, `0x0037CA60`) - matching 01.00's
finding that the register has a narrow, specific consumer set, not a
broadly-shared global.

### Angle 1 verdict: relocated and traced - still no connection to `promotion_flags_1e74`

Neither of `0x01502808`'s two 01.11 consumers touches the profile record at
all - `FUN_0037C85C` only reads the register (`+0xC`) and a live party
member field (`+0x90`), no profile-record accessor call anywhere in it;
`FUN_0037C95C` writes into the **party object** (`party+144`), not the
profile record. This independently confirms, via full relocation rather
than assumption, that the entitlement/capability register genuinely has
nothing to do with `P+0x1E74..0x1E8B` in either build. Angle 1 is now
**closed** (register relocated, both consumers read, neither reaches the
target field) rather than merely "not yet chased".

### A minor side-finding, out of primary scope

While reading `0x003D1FD4` end-to-end, four more profile-accessor touches
turned up in the already-flagged "genuinely unmapped middle" gap
(`P+0x1BB8..0x1E73`, out of this task's scope per the zero-region-walk
note's §6): `stw r29,7740(r3)` (`P+0x1E3C`) and `stw r29,7768(r3)`
(`P+0x1E58`) at `0x3D2120`/`0x3D2130`, both via the confirmed accessor
(`bl 0x3E6ADC`). Both offsets are safely below `0x1E74` (the target
field's start) and outside this note's scope - logged here only so a
future pass on that gap doesn't have to rediscover them.

## Angle 2: name-cracking `net10.bin`'s 46 new globals, plus a fresh lead (`promo1/`)

### The 01.11 install now has more than "just the patch's promo/DLC content" - but only a subset

The DLC-hypothesis note's exact words: "the 01.11 disc's own `build/main`
... has so far only the patch's promo/DLC content, not a full
`build/main`." Re-checked this pass: still true for the *disc corpus*
(`bin.psarc`, `.dci` files, `paks.txt`, etc. - none present under the
01.11 install's `build/main`), but the `build/main/promo1/` directory
itself turns out to be exactly the promotional/pre-order entitlement pack,
worth reading directly rather than only grepping for its filenames in
strings:

    /mnt/f/rpcs3_testing/TLOU-FACTIONS 1.11/dev_hdd0/game/BCUS98174/USRDIR/
      build/main/promo1/*.edat   (142 files)

Seven of them are the genuine "PROMO" pre-order bonus content pack (PS3
`.edat` NPD-wrapped entitlement files, content ID format confirmed by
reading each file's own NPD header, `UP9000-BCUS98174_00-<NAME>`):

    PROMOEARLYBRAWLR.edat   UP9000-BCUS98174_00-PROMOEARLYBR...
    PROMOELLIESKIN01.edat   UP9000-BCUS98174_00-PROMOELLIESK...
    PROMOEXTRASUPPLY.edat   UP9000-BCUS98174_00-PROMOEXTRASU...
    PROMOHATSHELMETS.edat   UP9000-BCUS98174_00-PROMOHATSHEL...
    PROMOJOELSKIN001.edat   UP9000-BCUS98174_00-PROMOJOELSKI...
    PROMOLOADOUTPOIN.edat   UP9000-BCUS98174_00-PROMOLOADOUT...
    PROMOSPUPGRADESF.edat   UP9000-BCUS98174_00-PROMOSPUPGRA...

`PROMOEXTRASUPPLY` is, by name, unmistakably the same promotional grant
`milestone_latch_1e2c`'s doc entry already names ("Added Extra Supplies
from Promotion!"). That leaves **exactly six** sibling PROMO items -
matching `promotion_flags_1e74`'s six-word count exactly. This is a real,
freshly-found structural coincidence and the most concrete new lead this
pass produced - **but see the verdict below: it did not resolve further.**

A scan of the 01.11 EBOOT's executable segment for the literal strings
`PROMO`, `EARLYBR`, `ELLIESK`, `EXTRASU`, `HATSHEL`, `JOELSKI`, `LOADOUT`,
`SPUPGRA` found no hardcoded content-ID string matching any of the seven
(the only `promo1` hits are a **generic** path-format string,
`"/%s/promo1/%s"` at `0x00E9460C`, and two unrelated Free2Play-edition
content names baked into the same format-string neighborhood,
`FREE2PLAYMPUNLC2`/`FREE2PLAYARENA00`/`FREE2PLAYADVENTU`, none of which
exist as files in this install). So entitlement names are **data-driven**
(populated from `net10.bin` at runtime, substituted into `%s`), not
compiled string literals - consistent with needing DC hash-cracking to
identify them, which is exactly the angle the DLC-hypothesis note left
open.

### Re-deriving the 46 new keys (reproduced, unchanged)

Re-extracted both bundles fresh this pass
(`server/lib/psarc_crypt.py extract`, HMAC OK both) and re-ran the
directory diff: `net1.bin` 392 entries, `net10.bin` 437 entries, same
**46** new `key_hash` values as the prior pass (independently
reproduced, not just re-cited).

### Widened hash-crack corpus - 3 of 46 cracked, none promotion-related

`dc_hash_crack.py` was run against all 46 new keys with the corpus grown
to `bin.psarc` + `paks.txt` + `pak23.txt` + `banks.txt` +
`rulebook-audio-precache.txt` + `ss-audio-precache.txt` (50,676 unique
candidate tokens - the same widened corpus the `field_0x358` runtime-table
work tried and failed against, described in
`research/notes/2026-08-20-followup-open-items.md` §2). This pass's two
largest available archives, `pak23.psarc` (10.8 GB) and `actor34.psarc`
(1.9 GB), were attempted too but the parse hung on disk I/O for over ten
minutes with no completion and were dropped from this run as impractical
within the pass's time budget - a different practical obstacle than the
prior pass's "not available", but the same net effect: those two archives'
`.dci` symbols remain unchecked.

**3 of the 46 new keys cracked:**

    0x4ba861b8  *net-smoke-bomb-upgrades*
    0xb58cdd92  *net-proximity-bomb-radius-upgrades*
    0xde531ac2  *net-molotov-radius-upgrades*

These are new DLC5 "Survival Skills" weapon-upgrade tables - matching the
`DLC5SURVSKIL*.edat` (`DLC5SURVSKIL2NDC`, `DLC5SURVSKILJACK`,
`DLC5SURVSKILLTHL`, `DLC5SURVSKILLUCK`, `DLC5SURVSKILWOLF`) content also
found in `promo1/`. This is useful, real confirmation that the crack
pipeline and widened corpus genuinely work against 01.11-only content (not
just a repeat of the prior pass's null result) - but it also demonstrates
that the 46 new globals are predominantly ordinary DLC5 gameplay-upgrade
data, not promotion/entitlement flags. The other 43/46 did not crack
(their source strings are not in this corpus - most plausibly inside the
two un-parsed giant archives, or a text bank this project doesn't have a
01.11 copy of, see below).

### The `*unlock-list*` table grew 284 -> 453 rows - also checked, also no clean 6-row match

Beyond the top-level 46 new keys, `net1.bin`'s `*unlock-list*` global
(`key=0xe2e8998e`, 28-byte-stride `{unlock_id, category, item_hash, 0,
sub_index, string_id, flags}` rows, per `research/tools/dc_dir.py`'s
established layout) grew from 284 rows (01.00) to **453 rows** (01.11) -
169 new rows, a strictly bigger diff surface than the top-level 46 keys
and not checked by either prior pass. Dumped in full
(`dc_dir.py --array 0x1960c 453 28 --as hash+hash` against the freshly
extracted `net10.bin`) and compared row-for-row against `net1.bin`'s 284:

* The `category` column gained a new value: `{1..6}` in `net1.bin` becomes
  `{1..7}` in `net10.bin`.
* The five rows that were `category=6` in `net1.bin` (`unlock_id` 1-5, all
  sharing `item_hash=0x497e034d`, at array rows 0-4) are present
  **byte-for-byte identical** in `net10.bin`, at the **same array rows**
  (0-4) - just relabeled `category=7`. This is a DC source-enum
  renumbering artifact (something got inserted into the category enum
  ahead of this value), not new content - this specific 5-row group is
  not a new-in-01.11 addition despite the category number changing.
* The genuinely new content is `net10.bin`'s new `category=6`: **9** rows
  with distinct `item_hash` values (`unlock_id` `0x1C3..0x1CB`), inserted
  mid-table at array rows 112-120.

Neither the old 5-row group nor the new 9-row group is a 6-row match.
Their `item_hash` values (`0x497e034d`, `0x69f47fc2`, `0x4d91c1b5`,
`0x82ab8c48`, `0x0cee1539`, `0xa7394951`, `0xbb93399f`, `0x4350588c`,
`0xaddb2a82`, `0xfbbcfde5`) were run through the same widened crack corpus
above - **none cracked**. Their `string_id` column (`0x000433xx`-
`0x000434xx` for the new 01.11 rows) looks like a `text1.psarc` StringId
(matching the `--as hash+strid` convention `dc_dir.py` already documents
for `*net-stats*`), but resolving it needs 01.11's own `text1.psarc` -
this project's only copy is the 01.00 disc's (`build/main/text1.psarc`,
`2.networking` entry), tried directly and returned nothing for either
build's IDs (01.00 IDs are `0x0002cccc`-`0x0002d0xx`, well below 01.11's
`0x000433xx` range, confirming they're from different text-bank
generations). No 01.11 `text1.psarc` is available locally.

### Angle 2 verdict: substantial new leads, no proof

* The `PROMOEXTRASUPPLY` + six sibling `PROMO*.edat` correlation (six
  items excluding the one with its own dedicated latch field) is a real,
  freshly-discovered structural coincidence that fits
  `promotion_flags_1e74`'s six-word shape exactly - the strongest
  candidate explanation either pass has produced. But it remains
  circumstantial: no EBOOT string reference, no cracked DC hash, and no
  `*unlock-list*` row set of the right size connects these six specific
  content IDs to the six-word block.
* The `net10.bin` diff surface was expanded (46 top-level keys, now also
  the `*unlock-list*` table's 169 new rows) and re-cracked against a wider
  corpus than either prior pass tried, confirming the pipeline works (3
  real names recovered) while still finding **no** clean 6-row DC table
  anywhere in either diff that maps to promotion content.
* Two concrete gaps remain, both purely a matter of unavailable/too-large
  source material rather than a wrong method: `pak23.psarc`
  (10.8 GB)/`actor34.psarc` (1.9 GB) were not successfully parsed this
  pass (I/O too slow, not attempted-and-empty), and 01.11's own
  `text1.psarc` (for resolving `*unlock-list*`'s `string_id` column) was
  not found anywhere in either local install.

## Combined verdict

Neither angle produced a real writer, reader, or proven semantic
explanation for `promotion_flags_1e74`. Angle 1 is now genuinely closed
(register relocated and fully traced in 01.11, confirmed uninvolved).
Angle 2 turned up a strong new circumstantial candidate (the six sibling
`PROMO*.edat` items) and meaningfully widened the hash-crack corpus and
diff surface, but static analysis still cannot connect any of it to the
six-word block with proof. **Static analysis is exhausted for this field**
- what's left needs either the live RPCS3 breakpoint test already planned
in the zero-region-walk note's §5, or non-static artifacts this project
doesn't have locally (`pak23.psarc`/`actor34.psarc` parsed to completion,
or 01.11's own `text1.psarc`).

### What the live test should specifically check now, given this pass's findings

In addition to the zero-region-walk note's original plan (arm a memory
write breakpoint on `P+0x1E74..0x1E8B` on a fresh/low-progress account,
trigger the Promotion event, check `CIA`/`LR`):

* If the breakpoint fires, check whether the call stack passes through
  `FUN_0037C85C`/`FUN_0037C95C` (01.11) or their 01.00 analogs
  (`0x01459260`'s two consumers) - this pass's finding is that it should
  **not**, since neither function ever resolves the profile-record
  accessor. A hit inside either would overturn this pass's conclusion and
  is worth flagging immediately if seen.
* If a live account's inventory/entitlement screen can be correlated with
  which of the six words are set, check specifically against the six
  named `PROMO*.edat` items (`EARLYBRAWLR`, `ELLIESKIN01`, `HATSHELMETS`,
  `JOELSKIN001`, `LOADOUTPOIN`, `SPUPGRADESF`) - if the live account owns
  a strict subset of these six and the word pattern matches, that would
  independently confirm this pass's leading hypothesis without needing
  the EBOOT write site at all.
