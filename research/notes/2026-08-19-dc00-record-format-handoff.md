# net1.bin/net10.bin's DC00 record format: accessible, hash-matched, not yet decoded

Handoff for a dedicated follow-up session. This is a genuinely new lead, not a continuation of anything already tracked as "in progress" - it surfaced from questioning whether "DC-blocked" (this project's long-standing catch-all for content that lives in `.pak`/`netN.bin` rather than the EBOOT) was as hard a wall as documented.

## The core finding

`net1.bin`/`net10.bin` are **not opaque** - they're already decrypted, on disk, and readable:

```
server/data/served_content/net1.bin.psarc.crypt   (01.00's file)
server/data/served_content/net10.bin.psarc.crypt  (01.11's file)
```

Extract either with the tool this project already has:

```sh
python3 server/lib/psarc_crypt.py extract server/data/served_content/net1.bin.psarc.crypt <outdir>
# -> <outdir>/net1.bin (283,870 bytes, HMAC-verified), <outdir>/_manifest.txt
```

(Note: I extracted into this session's scratchpad, which does NOT persist. Re-extract at the start of the next session - the source `.crypt` files themselves are already committed/present in `server/data/served_content/`, nothing needs re-downloading.)

Both files open with a `DC00` magic header and a genuine hash-keyed record structure - not the "mostly non-text blob, no readable pattern" verdict from the prior 2026-08-14 pass (`research/notes/net1bin-server-list.md`). That earlier note was searching for readable ASCII strings (IP addresses) and correctly found none in a structured sense - it never looked for *binary hash tables*, which is a completely different search and is what this note found.

## Confirmed: known DC hashes appear literally as bytes in these files

Every DC hash this project has ever cited in code/docs (only three exist, found via `grep -rn "hash 0x" protos/ docs/ server/`) is present, as raw big-endian 4-byte values, in one or both files:

| Hash | Cited for | net1.bin (01.00) | net10.bin (01.11) |
|---|---|---|---|
| `0xC85E199D` | `member_data.rank_tier` threshold table (`protos/common/member_data.ksy`) | 1 occurrence @ `0xed4` | 1 occurrence @ `0x1084` |
| `0x1ad3445f` | `stat_line`'s task-definitions table base (`protos/0x11_stat_line.ksy`, traced to `FUN_0032241c` this session) | 39 occurrences, first @ `0x1850` | 76 occurrences, first @ `0x1b10` |
| `0xFFAC56F2` | `pReportArray` ban-list entries (`server/ticket_server.py`, `TODO(pReportArray)`) | 0 occurrences | 1 occurrence @ `0x148c` |

`pReportArray` only appearing in net10.bin is expected and corroborating: `report-server` is already established as 01.11-only (see `docs/protocol/proto-map.md`'s Tier C entry for it), and net10.bin is 01.11's data file.

Every single-occurrence hit (`rank_tier`, `pReportArray`) is a clean, unambiguous match - not the kind of thing that happens by chance in a 280-400KB file. The 39/76-occurrence hit for the task-table hash is consistent with it being a shared TABLE TYPE tag referenced by many individual task/objective records, matching what the EBOOT-side trace already established (`FUN_0032241c` resolves several sibling fields - `0x19`, `0x1b`, `0x1d`-`0x20`, `0x2e` - from the same base table).

## What is NOT yet solved: the exact record layout

Raw bytes around the `rank_tier` hit (net1.bin, offset `0xed4`, HMAC-verified extraction):

```
00000e94: 00 00 52 00 c4 bc 9e 8b 2a 80 27 cf 00 00 52 d0  ..R.....*.'...R.
00000ea4: c5 1a 27 a2 fd 85 45 de 00 02 7e 34 c5 70 86 fd  ..'...E...~4.p..
00000eb4: 2a 80 27 cf 00 00 52 dc c5 7c af 6b 2a 80 27 cf  *.'...R..|.k*.'.
00000ec4: 00 00 52 e8 c7 f8 56 7c ed 6b 8e 26 00 02 7d a8  ..R...V|.k.&..}.
00000ed4: c8 5e 19 9d ce d9 d2 5f 00 00 52 f4 c9 70 68 1f  .^....._..R..ph.
00000ee4: 29 03 49 e3 00 00 53 00 c9 80 c0 53 2a 80 27 cf  ).I...S....S*.'.
```

Pattern visible: a sequence of 4-byte values that strictly increase (`0x5200`, `0x52d0`, `0x52dc`, `0x52e8`, `0x52f4`, `0x5300`, ...) - almost certainly record ids or byte offsets into a second data region - interleaved with pairs of hash-looking 4-byte values, one of which (`0x2a8027cf`) repeats often enough to be a shared type tag, not the individual key.

**A naive fixed-12-byte-stride reading breaks down**: after the id at `0xe94` and its two following 4-byte values, the next id-looking value doesn't land cleanly 12 bytes later every time (see `0x00027e34`, `0x00027da8`, `0x00027d90`-shaped values interrupting the pattern at `0xeac`/`0xed0`-ish) - meaning either (a) records are variable-length, or (b) there are two interleaved tables/sections and the naive scan is reading across a boundary, or (c) the true stride is larger than 12 and what looks like noise is actually a third field per record that I mis-split. Not resolved this pass.

**Header fields, first 24 bytes of net1.bin vs net10.bin (not yet interpreted, offered as a starting point):**

```
net1.bin:  44 43 30 30 00 00 00 01 00 04 33 40 00 00 00 00 00 00 00 01 00 00 01 88
net10.bin: 44 43 30 30 00 00 00 01 00 06 0d 94 00 00 00 00 00 00 00 01 00 00 01 b5
           DC00        ver?=1      ????        pad?        ????=1      count?=392/437
```

Both files' first table entry is IDENTICAL (`00 73 a3 83  2a 80 27 cf`, right at offset `0x1c` in both) - strong evidence the table format itself (not just the magic) is shared between builds, only the content differs. The `0x00000188`/`0x000001b5` field (392 / 437 decimal) is a plausible record-count guess given it roughly tracks the size difference between the two files, but this is NOT confirmed - do not build further work on it without checking against the actual parser.

## Recommended next step: find the EBOOT's own parser, don't keep guessing from bytes alone

The client MUST correctly parse this exact format to use `net1.bin`/`net10.bin` at all - its parser is a ground-truth answer sitting in the EBOOT, and is almost certainly far more reliable and faster to find than continuing to guess from a hexdump. Concretely:

1. Search the EBOOT for the 4-byte literal `0x44433030` (`"DC00"` as a big-endian word) via `research/tools/eboot_analysis` (the existing `scan_imm.py`/raw byte search techniques used all session for other constants) - this should find the magic-number check that gates loading these files, and the function containing it is the parser.
2. Alternatively, search for known DC hash-resolver function names already identified this session: `_opd_FUN_0078b5a0` (resolves a base table from a hash - used for `stat_line`'s task table) and `_opd_FUN_00ab685c` (per-key lookup within a resolved table) are STRONG candidates for being (part of) this exact file's reader, since they were traced doing hash-keyed lookups this session without yet connecting them to `net1.bin` specifically. Decompiling `FUN_0078b5a0` fully (not just its call-site behavior, which is all that was traced this session) would very likely reveal the header layout and record stride directly, since it has to walk this table to resolve a hash to a value.
3. Once the record format is confirmed, decode the three known hits directly (`rank_tier`'s actual threshold values, `pReportArray`'s ban-list entry structure, and as many of the 39-76 task entries as are useful) and fold the results into their respective `.ksy`/doc files, removing the "DC-blocked" status from each.
4. This format is shared infrastructure - once cracked, ANY future DC hash this project ever cites (capability_flag bit-to-DLC mapping, cosmetic/character id maps, etc., none of which have a known hash cited yet but plausibly use the same table) becomes checkable the same way. Worth documenting the format itself as its own `.ksy`/doc (e.g. `protos/common/dc_table.ksy`) once solved, not just patching individual fields.

## Why this matters

This project's docs currently describe an entire category ("DC-blocked") as needing something this project doesn't have access to - "extract the net1.bin/net10.bin registries. Not reachable by decompiling the EBOOT" (`docs/protocol/proto-map.md`). That framing is now out of date: the registries ARE extracted, sitting on disk, and at least three of this project's own already-traced hash lookups match bytes inside them exactly. What remains is a genuine but bounded reverse-engineering task (one binary record format, likely shared across both files), not a resource-access wall like the PS4-retail-server or ranked-account blockers elsewhere in this project.
