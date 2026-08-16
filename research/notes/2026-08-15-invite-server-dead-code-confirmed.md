# `invite-server` is confirmed dead code - not just the name string, the whole `net-invite.cpp` translation unit

Follow-up to `docs/protocol/0x11_sibling_servers_family.md`, which already
flagged `invite-server` as having "no live call site found - very likely
dead/unused" based on one check: the `"invite-server"` string constant
(`0x00e7d0b0`) has exactly one cross-reference in the whole binary, and it's
a data ref, not a code ref. That finding was correct but narrow - it only
checked one string. This pass checks the rest of that string's source file
and finds the same result across the board, which closes the "could be
fully-dynamic dispatch" hedge that was the stated reason for capping
confidence at medium.

## What was checked

`research/strings/strings_ascii.txt` (grep `-i invite`) turns up five
strings clustered within 0x50 bytes of each other, all clearly belonging to
one source file:

```
e6d0b0 invite-server                    (Ghidra VA 00e7d0b0)
e6d0c0 invite-list %s                   (Ghidra VA 00e7d0c0)
e6d0d0 m_thread == 0                    (Ghidra VA 00e7d0d0)
e6d0e0 game/net/net-invite.cpp          (Ghidra VA 00e7d0e0)
e6d0f8 invite-delete %s %s              (Ghidra VA 00e7d0f8)
```

(`strings_ascii.txt` addresses run a consistent `-0x10000` from Ghidra's
loaded VA throughout this binary - cross-checked against `facebook-server`,
`heartbeat-server`, `leaderboard-server`, whose `strings_ascii.txt`/Ghidra VA
pairs all differ by exactly `0x10000`.)

This is recognizably one full literal pool for `net-invite.cpp`: the service
name, two `sprintf`-style command formats (`invite-list %s` /
`invite-delete %s %s` - the same command-format shape used by every live
sibling, e.g. heartbeat-server's `FUN_00e46560` calls), an `ASSERT`
condition string (`m_thread == 0`), and the file's own `__FILE__` string
(used by every `ASSERT`/`assert` call site in that translation unit).

Ran `GetReferencesTo.java` (the existing repo script, reused unmodified -
`research/ghidra/invite_related_refs.txt`) against all four address-bearing
strings (`m_thread == 0` has no direct string-table entry check needed since
byte-dumping the region, below, already located it):

```
==== references to 00e7d0b0 (invite-server) ====
  ref from 01269950 in <none>

==== references to 00e7d0c0 (invite-list %s) ====
  ref from 01269954 in <none>

==== references to 00e7d0e0 (net-invite.cpp) ====
  ref from 01269974 in <none>

==== references to 00e7d0f8 (invite-delete %s %s) ====
  ref from 01269978 in <none>

==== DECOMPILED (0 functions) ====
```

**Zero code references to any of the four.** Every reference is a single
data-to-data ref from a TOC/literal-pointer table (`0x01269950`-`0x01269978`
region), `<none>` meaning it doesn't originate inside any function body.
Per `docs/ghidra-setup.md`, this project's full auto-analysis pass already
resolves TOC-relative (`r2`-based) loads into direct reference edges from
the *loading instruction* straight to the *target string* - this is exactly
the mechanism that correctly found all 10 real call sites for the other four
siblings in the original `acc424_all_callers.txt` pass. If any instruction
anywhere in the binary loaded one of these four addresses via TOC-relative
addressing, it would show up here as `ref from <code addr> in FUN_xxx`
(exactly the pattern seen for every live sibling). None do.

## Why the `m_thread == 0` assert string matters most

Raw byte-dump of the surrounding table (`research/ghidra/invite_struct_dump.txt`,
`DumpBytesAt.java 01269900 192`) confirms the fifth string
(`"m_thread == 0"` @ `00e7d0d0`) sits at table slot `0x01269970`, immediately
before the `net-invite.cpp` filename slot (`0x01269974`) - the classic
`ASSERT(cond, file, line)` macro pattern (condition-string-ptr immediately
followed by file-string-ptr). Checked its refs too
(`research/ghidra/invite_control_refs.txt`): also zero code refs.

This is the strongest single data point. An `ASSERT`/`assert()` macro's
file/line string-load instructions are compiled into the function
**unconditionally** - they exist in the binary as long as the *containing
function* was linked in, regardless of whether the assert condition is ever
false at runtime, and regardless of whether the function's "real" logic path
is ever exercised. Zero code refs to the assert filename string means not
just "the invite-list/invite-delete commands are never sent" but that **no
function from `net-invite.cpp` containing this assert was linked into the
executable's reachable code at all** - the entire translation unit's code
was dropped, while its `.rodata`/TOC string-literal entries were retained as
orphaned data.

## Control check: same table, same method, confirmed to find live refs when they exist

To rule out a systemic blind spot in this check (e.g. this whole TOC region
being somehow invisible to Ghidra's reference resolution), the same method
was run against neighboring literal-pool entries in the identical
`0x0126xxxx` table, belonging to different, definitely-alive source files:

- `"NetInteractableManager - too many interactables! total = %i"` /
  `"game/net/net-interactable-manager.cpp"` (`00e7d048`/`00e7d088`, table
  slots immediately *before* the invite-server cluster) - **2 code refs
  each**, both from `FUN_003acaf8 @ 003acaf8`.
- `"game/net/net-late-join.cpp"` / `"NET_SM_CLIENT_CUSTOM_LATE_JOIN_SCREEN_3"`
  (`00e7d110`/`00e7d130`, immediately *after*) - **13 and 2 code refs
  respectively**, spread across 7 distinct functions (`FUN_003ad09c`,
  `FUN_003ad444`, `FUN_003ad5dc`, `FUN_003ad6a4`, `FUN_003ad874`,
  `FUN_003ada80`, `FUN_003adf2c`, `FUN_003ae428`).

Same table, same reference-resolution mechanism, real call sites found on
both sides of the invite-server cluster and none inside it. The zero-refs
result for `net-invite.cpp` is a genuine negative, not a tooling gap.

## Corroborating context already in the repo

- `research/notes/2026-08-14-session-token-crypto-and-siblings-followup.md`
  independently reached the same "zero code call sites" result for
  `invite-server` in an earlier pass (consistent, not new).
- `research/notes/2026-08-15-createparty-trace.md` traced the actual
  in-game "invite to party" UI action live and found it does **not** go
  through `0x13a`/`FUN_00ad6148` or (by extension) anything in this
  `net-invite.cpp` cluster - the real trigger wasn't pinned down, but the
  note's own working theory is a separate Sony `sceNp`-native
  friends/invite mechanism, not custom backend traffic. That's consistent
  with this finding: the game's actual invite feature, whatever it is, does
  not appear to touch the dead `invite-server` code path at all.

## Confidence: high

Upgraded from the prior doc's "medium" / "medium-high". The original
caveat ("can't rule out a call reached only through fully dynamic dispatch")
is substantially weakened by the assert-filename result above: dynamic
dispatch by index into a function-pointer table could maybe explain away a
missing *direct* reference to one connect function, but it can't explain
away zero references to an `ASSERT` macro's file string, since that
load is unconditional within its containing function and has nothing to do
with how the function itself gets invoked. For all of that code to be
truly unreachable-but-present would require the entire translation unit to
be linked in with literally every function stripped of its body except
data - a scenario indistinguishable from "not linked" for any practical
purpose. Not upgraded to "certain" only because a fully stripped, no-symbol
20MB PS3 binary can't rule out esoteric indirect-call patterns with
absolute certainty from static analysis alone - but this is as close to
definitive as static analysis gets, and matches the same standard of
evidence (`getReferencesTo` + `acc424_all_callers.txt`) already treated as
conclusive for confirming the other four siblings are alive.

## How to apply

- `docs/protocol/0x11_sibling_servers_family.md` and `docs/protocol/README.md`
  should state `invite-server` as **confirmed dead code**, not "likely"
  dead/unused - both updated in this pass.
- If a future session revisits `net-invite.cpp`/the invite feature (e.g.
  because a live capture shows an invite-shaped payload somewhere), start
  from the possibility that it's implemented via Sony's native `sceNpBasic`
  invite/message API instead, per `2026-08-15-createparty-trace.md`'s
  working theory - not via this custom TCP service, which this note treats
  as closed.

## Files

- `research/ghidra/invite_related_refs.txt` - xref check on the 4
  address-bearing invite-server-cluster strings.
- `research/ghidra/invite_struct_dump.txt` - raw byte dump of the
  `0x01269900`-`0x012699c0` TOC/literal-pointer table region, used to locate
  the `m_thread == 0` assert-condition string's table slot.
- `research/ghidra/invite_control_refs.txt` - control-group xref check on
  neighboring, definitely-live table entries (`net-interactable-manager.cpp`,
  `net-late-join.cpp`), confirming the method finds real call sites when
  they exist.
