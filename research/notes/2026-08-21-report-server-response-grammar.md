# `report-server`'s RESPONSE grammar: completing the documentation (01.11)

Low-stakes documentation task. The `is-banned` REQUEST side and the
`pReportArray` ban-name table were already fully resolved (see
`docs/OPEN-QUESTIONS.md`'s "Blocked on data-compiler" section and
`protos/0x11_report_line.ksy`, both dated 2026-08-19), and that prior work
already proves the check is FAIL-OPEN: this server's empty reply never
triggers a false ban, so there is no correctness risk in play here. What was
still open was purely documentation completeness - the RESPONSE grammar had
never been folded into a dedicated note, and two questions about it were
listed under "Genuinely unknown" in `docs/OPEN-QUESTIONS.md`:

1. What exactly does the client's response parser accept, token by token?
2. Does `report-server` handle any OTHER request kind besides `is-banned`
   (the family name suggests "report a player", not just "check ban
   status" - is that a real second grammar or a naming artifact)?

Both are now closed. Nothing here changes server behaviour or any existing
conclusion; it is a documentation pass over ground already traced on
2026-08-19, cross-checked against a fresh objdump of the 01.11 binary.

## Binary and method

```
01.11 EBOOT: /mnt/f/rpcs3_testing/TLOU-FACTIONS 1.11/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf
sha256: 241e2b1bca43c97431a1aa7acd1b29a20d292bec7263ab8ca318b8a03538e592
```

This is the same 01.11 build cited by the existing report-server and
gamelist-server writeups (`241e2b1b...`). Its previous location
(`.../rpcs3-v0.0.41.../dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf`, per
`research/tools/eboot_analysis/README.md`) no longer exists on disk - a
`backup/BCUS98174` copy under that same rpcs3 install has the identical
SHA256, and a second full copy lives under `TLOU-FACTIONS 1.11/`. Both are
byte-identical to the one prior notes used; anyone reproducing this should
verify the SHA256 before trusting an address.

`research/tools/eboot_analysis/eb.py`/`scan_bl.py`/`scan_anchor.py`/
`scan_imm.py` were pointed at this binary the way
`research/notes/2026-08-19-gamelist-server-sender-decompile.md` describes:
`eb.py`'s `EB` constant repointed at the path above; `scan_anchor.py`'s
`R2 = 0x01338de0` (from the entry-point function descriptor, same value the
gamelist note derived) and `TEXT_VA, TEXT_SZ = 0x00010000, 0x121ef68`. Sanity
check before trusting anything: `eb.cstr(0xeacdc0/0xeacdd0/0xeacde0, ...)`
returned `"report-server"` / `"is-banned %s\n"` / `"ban response: '%s'\n"`
exactly as the existing docs cite - the same check the gamelist note used to
validate its own `R2`.

## Re-verifying the existing trace

`objdump --start-address=0x36e100 --stop-address=0x36e400` (raw binary,
`--adjust-vma=0x10000`, per the tool README's uniform VMA mapping) reproduces
every address already cited in `protos/0x11_report_line.ksy` exactly:

- `0x36e1a8  stw r0,916(r9)` with `r0 = -1` (from `li r0,-1` @ 0x36e1a0) -
  the ban-index default.
- `0x36e1fc  lwz r6,-30712(r30)` - loads the "report-server" string pointer
  (confirmed: this offset resolves to slot `0x129a3c8`, which a full-file
  scan for the pointer value `0xeacdc0` shows holds exactly one entry, at
  exactly that slot).
- `0x36e220  bl 0xaf9bb4` - the connect+hello call.
- `0x36e298/0x36e29c  cmpwi cr7,r3,0 / ble 0x36e384` - the recv-length check.
- `0x36e2c8/0x36e2cc  lbz r0,904(r1) / cmpwi cr7,r0,43` - the `'+'` test.
- `0x36e2ec  bl 0xe72d80` (strtok_r) / `0x36e30c bl 0xe75d78` (strtol, base
  10 via `li r5,10` @ 0x36e300) / second `bl 0xe72d80` @ 0x36e324.
- `0x36e33c-0x36e384` - the `pReportArray` strcmp loop, entry stride
  `mulli r9,r9,12` @ 0x36e340 (12-byte entries), name at `+8`
  (`lwz r3,8(r9)` @ 0x36e34c), strcmp @ 0xe778e4.
- `0x36e360/0x36e364/0x36e368` - the match arm: `g_net+920 = ban_index_int`,
  `g_net+916 = loop_index`.

No address needed correction. This matches the project's "verify before
concluding" convention - every citation was re-derived from a live objdump
of the actual binary, not assumed from the prior note.

## Question 1: the exact response grammar

Already correctly stated in the existing `.ksy` prose. The one addition
worth making formal: the parser is **strictly single-pass**, not a
repeating "one row per reply" reader the way some other family members are.
Exactly one `strtok_r`/`strtol`/`strtok_r`/`strcmp`-loop sequence executes
per reply (no code path re-enters `0x36e2ec`), and any bytes in the 256-byte
recv buffer after the second token are read into memory but never inspected
again - there is no second `'+'`-line scan.

Grammar (EBNF-ish, matching what the parser actually branches on):

```
response  := "" | garbage | ban-row
ban-row   := "+" ban_index sep name (sep name)* junk? "\n"?
sep       := " " | "\n"
ban_index := [0-9]*              -- strtol(..., NULL, 10); non-digit content
                                     yields strtol's own 0, not a parse error
name      := any bytes not in {" ", "\n"}
junk      := anything (never read)
```

`ban_index` and `name` are modeled as `ban_reply_row` in
`protos/0x11_report_line.ksy` (new `types:` block). Every byte the client's
parser actually inspects is named; nothing is left as an opaque blob. The
"anything after `name`" tail is documented as ignored because that is
provably true of the parser (dead code past the second `strtok_r`), not
because a static answer wasn't attempted for it.

Two things are NOT in this grammar, both confirmed by this pass and matching
the existing "THERE IS NO 0/1 BOOLEAN" note:
- No length-prefixed or fixed-width fields anywhere in the response. It is a
  pure ASCII token stream, matching the sibling family's general "line
  protocol" convention (see `docs/protocol/0x11_sibling_servers_family.md`).
- No NUL-terminator requirement from the server - the client NUL-terminates
  the buffer itself at the recv length (`stb r28,904(r9)` @ 0x36e2ac, with
  `r28 = 0` from the connect-success check).

## Question 2: is there a second report-server request kind?

**No - confirmed by exhaustive search of the whole 01.11 text segment, not
by absence of a lead.**

`research/tools/eboot_analysis/scan_bl.py` against `0xaf9bb4` (the shared
connect+hello function every 0x11 sibling server uses - the same one
`docs/protocol/0x11_sibling_servers_family.md` and the gamelist-server note
already establish) finds exactly 12 call sites in the entire 01.11 EBOOT:

```
0x00084f9c  0x00369d94  0x0036ac8c  0x0036d1c4  0x0036e220  0x003c8cb0
0x003c95b0  0x003ca790  0x003cace4  0x004049d4  0x00816528  0x00aeeb80
```

Each site loads its service-name string pointer into `r6` immediately
before the call (this ABI's convention, confirmed at `0x36e220` itself,
where `r6` is set at `0x36e1fc`, far enough back that the intervening
tokenizing/logging code doesn't clobber it). Disassembling a window before
each of the other 11 call sites shows 11 *distinct* `r6` load displacements
off the per-function `r30` anchor - `-32676`, `-31140`, `-31036`, `-30820`,
`-32692` (four sites, almost certainly the ticket-server family sharing one
compilation unit), `-32452` (this is `0x4049d4`, already identified as
`gamelist-server`'s connect in the existing gamelist note), `-32356`,
`-32680`. **None of them is `-30712`** - the displacement that resolves to
the "report-server" string slot (`0x129a3c8`), and which only `0x36e220`
uses.

A second report-server request verb would necessarily need a second call to
`0xaf9bb4` passing the "report-server" string as its service name (or, in
principle, an entirely separate connect implementation reading the same
slot directly - checked and ruled out too: a raw-word scan of the full text
segment for the pointer value `0xeacdc0` finds exactly one slot,
`0x129a3c8`, and a raw-word scan for the load-instruction encoding
`lwz rX,-30712(r30)` finds 10 occurrences total, only one of which
(`0x36e1fc`) sits anywhere near the report-server code - the other 9 are in
unrelated functions scattered across the binary (`0x3d54c`, `0x760bc`,
`0xd640c`, `0x1749d8`, `0x522ca8`, `0x747aac`, `0x747b2c`, `0x7495f4`,
`0x838278`) where `r30` almost certainly resolves to a different
compilation-unit anchor value - i.e. coincidental displacement reuse, not
the same physical global; none of them is close enough in address or
purpose to the reporting code to be a plausible second use of this string).
There isn't one.

The string neighborhood around "report-server" (`0xeacc00`-`0xeacf00`,
scanned by hand) also has no second verb literal: sound/analytics strings
before it, `NetInit Done` / `!m_rBuffer` / `game/net/in-game-commerce.cpp` /
upgrade-DLC filenames after it. The only three strings that belong to this
service are the three already documented: `"report-server"` @0xeacdc0,
`"is-banned %s\n"` @0xeacdd0, `"ban response: '%s'\n"` @0xeacde0.

**Conclusion**: the "report" in `report-server` is a naming artifact of the
shared backend (per the existing doc, administratively the same service
that would receive player reports server-side), not a second client-side
grammar. This project's client never sends a report of any kind over this
connection - it only ever performs the `is-banned <own-online-id>`
self-check, and always for its own account (re-confirmed by the existing
"nine captured connections, always self" finding, unchanged by this pass).

## What remains genuinely unresolvable statically

Same two items the 2026-08-19 pass already flagged, unaffected by this
pass and not reopened by it:

- `pReportArray`'s entry NAMES - a data-compiler payload, not present in the
  EBOOT.
- The meaning of the integer stored at `g_net+920` - formatted into the ban
  message via a runtime (bss) format-string pointer, unreadable statically.

## Is a live capture worth doing, given the low correctness stakes?

**No, not on priority.** The fail-open conclusion needs no further evidence
- it was already correctness-verified on 2026-08-19 by decompile alone, and
this pass adds a second independent instruction-level confirmation on top
of that. A live capture of an actual `"+<n> <name>\n"` reply would only be
useful for two things, both already tracked as separately-scoped, lower
priority TODOs with no dependency on this task:

1. Recovering `pReportArray`'s literal entry names - but a capture can't do
   that either unless this project deliberately bans a test account first
   (there is no live source of a real ban row otherwise); a DC/.psarc dump
   is the more direct route and is already the tracked plan
   (`TODO(pReportArray)`).
2. Confirming the `g_net+920` integer's real-world meaning (duration? days?
   an ID?) - same caveat, needs a deliberately-triggered ban to observe, not
   passive capture.

Neither is motivated by anything found here; both were already known and
already correctly deferred.
