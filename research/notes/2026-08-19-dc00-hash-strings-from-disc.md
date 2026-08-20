# DC00 hash strings recovered from the retail disc; `rank_tier`'s DC hash corrected

Follow-up to `research/notes/2026-08-19-dc00-container-format-solved.md`,
which solved the DC00 container format but left every individual hash's
*source symbol name* unrecovered (no on-disk string table maps a `key_hash`/
`type_hash` back to a name). This note closes that gap using a resource not
previously used in this project: the mounted retail PS3 disc.

## The disc is a new, previously-untapped source

`F:\rpcs3_testing\...\The Last of Us [BCUS98174]\PS3_GAME` (WSL path
`/mnt/f/rpcs3_testing/.../PS3_GAME`) is a full retail PS3 disc image mounted
for RPCS3. `PS3_GAME/USRDIR/build/main/*.psarc` are **unencrypted** PSARC
archives - a different, unrelated set of files from
`server/data/served_content/*.psarc.crypt` (which are Blowfish+HMAC-wrapped
network-delivered patch bundles). The disc archives are readable directly
with `server/lib/psarc_crypt.py`'s `parse_psarc()` function (skip
`decrypt_crypt_file` entirely - these are plain PSARC).

Two findings from walking `bin.psarc`:

1. It contains `dc1/net.bin` (283,615 bytes), which is **byte-identical in
   internal structure** to `net1.bin` from `served_content` - every hash
   checked (`0xC85E199D`, `0x1ad3445f`) lands at the exact same file offset
   in both (`0xed4`, `0x1850`). The disc's `dc1/` tree is very likely the
   direct build source of the `netN.bin` bundles served over the network.
2. Every `dc1/*.bin` has a sibling `dc1/*.dci` (1,878 of them found) - a
   small **plaintext** file, not DC00/binary, shaped like
   `(net (283615)\n  (import a b c ...)\n  (export *sym1* *sym2* ... plainsym) )`.
   This is the DC compiler's own import/export symbol list for that source
   module - i.e. exactly the string dictionary needed to reverse a
   `crc32_mpeg2` hash back to a name. Tokenizing every `.dci` in `bin.psarc`
   yields **43,674 unique symbol names**.

## Hash algorithm confirmed, naming scheme cracked

`crc32_mpeg2` (`server/lib/userdata_crypt.py`, already this project's
confirmed hash for `userdata.txt` config keys - poly `0x04C11DB7`, init 0,
no reflection/xorout) is the same hash used for DC00 directory keys.
Evidence: hashing every token from the 43,674-symbol corpus and checking
against every DC hash this project had cited turned up exact matches on the
first pass, including two on the same directory entry:

- `crc32_mpeg2("*net-money-info*") == 0xC85E199D` - previously cited (with a
  "rank/tier-bracket shaped" guess) as `member_data.rank_tier`'s backing
  hash.
- `crc32_mpeg2("net-money-info") == 0xced9d25f` - the exact `type_hash`
  documented as that same directory entry's sibling word in
  `docs/protocol/dc_table.md`.
- `crc32_mpeg2("hud") == 0x1ad3445f` - independent cross-check of
  `stat_line`'s table hash, already solved via a different method (EBOOT
  string trace) earlier the same day; this confirms the two methods agree.

Two independent exact matches (`key_hash` AND `type_hash`) landing on the
same concept, out of a 32-bit hash space searched against ~44K candidates,
rules out coincidence. This also reveals the general naming convention:
`key_hash = crc32_mpeg2(global-variable-name)` including the source
language's `*star*` global-decoration syntax, `type_hash =
crc32_mpeg2(bare-name)` with the stars stripped - a global and its
type/struct name, hashed as a matched pair, for every top-level directory
entry in a DC00 file.

## Correction this forces: `rank_tier` is not a rank/tier concept

This project's docs described `0xC85E199D` as "rank/tier-bracket shaped"
purely from context (it backs the wire field named `rank_tier`, and the
consuming function `FUN_003c8e30` visibly does a linear bracket-scan). That
description is now known to be **wrong at the source-symbol level**: the DC
table is named `net-money-info` in the shipping source, not any rank/tier
concept - almost certainly a currency/scrap-economy table (unlock costs,
weekly earnings, etc.). This retroactively explains why the table's
193-entry array never read cleanly as flat rank thresholds under the
consumer's literal stride (see `member_data.ksy`'s `rank_tier` doc) - it was
never a thresholds array to begin with.

**What is deliberately left open, not resolved by this note:** whether the
*wire field* at member_data offset 16:18 (kept as `rank_tier` for its own,
separate behavioral justification - the lobby reads it for a remote
player's rank/title display, per `docs/protocol/0x131_member.md`) is
actually money-derived data being misread as rank, or whether
`FUN_003c8e30` genuinely produces a rank/tier value by consulting a
money-table (e.g. "which reward tier has this player's earned currency
crossed"). Both remain plausible. The field was NOT renamed off the
strength of this finding alone - see `member_data.ksy` for the full
reasoning and what would resolve it (a live memory read of the resolved
`net-money-info` table correlated against known scrap/currency totals).

## Log cross-check against the leaderboard (inconclusive)

Board 405 (`leaderboard-server`, "overall/clan-supplies") is submitted on
every match end and is already fully decoded
(`protos/0x11_leaderboard_line.ksy`) - a real numeric supplies score per
account, sitting in `server/logs/ticket_server.log` for the project's own
test accounts. Cross-referencing those against every captured `0x13a` frame
(`rank_tier` at byte offset 32:34 of that packet) in `server/logs/wire.jsonl`
by npid+timestamp: `rank_tier` reads a constant `0x0000` across all 852
captured frames for all three test accounts, while `mgnomad2`'s board-405
score climbed `35 -> 53+` and `comradesean`'s plateaued at `81` over the
same period. No variation to correlate against - inconclusive, not
confirming either the money-table or the old rank-tier reading (both
predict a constant 0 for accounts this low/unranked). Recorded in
`protos/common/member_data.ksy`'s `rank_tier` field doc.

## What didn't crack

`0xFFAC56F2` / `0xF99A36AA` (`pReportArray`'s key_hash/type_hash) and the
DC00 payload's other recurring `type_hash` constants (`0x2a8027cf`,
`0x290349e3`, `0x13c5fb80`, `0x3331e70d`) were all searched against the
full 43,674-token corpus and found no match. `pReportArray` is confirmed
01.11-only content (only appears in `net10.bin`, not `net1.bin`), and this
disc is the 01.00 base build - if its source symbol was introduced in a
later patch, it plausibly just isn't present in this disc's `.dci` set. A
matching 01.11-era disc/patch source (not currently available) would be
needed to try these against a comparable symbol corpus.

## Reusable method, going forward

**Tool: `research/tools/dc_hash_crack.py`.** Any future DC hash this
project cites should be run through it before being declared unrecoverable
- it's a cheap, mechanical search (hash ~50K candidate strings pulled fresh
from the disc, check set membership), not a fresh RE investigation each
time. Reproduces every match in this note from a clean checkout:

```sh
BASE="/mnt/f/rpcs3_testing/.../PS3_GAME/USRDIR/build/main"
python3 research/tools/dc_hash_crack.py \
    -p "$BASE/bin.psarc" -w "$BASE/paks.txt" -w "$BASE/pak23.txt" \
    0xC85E199D 0xced9d25f 0x1ad3445f
```

See `docs/protocol/dc_table.md`'s "Recovering hash strings from the retail
disc" section, or the script's own `--help`, for the full explanation of
where each candidate source comes from and why.

The script also fixed a real bug it exposed in `server/lib/psarc_crypt.py`:
the CLI's `unpack`/`extract` actions did not create subdirectories for
entries with nested paths (e.g. `dc1/net.dci`), so they crashed on
`bin.psarc` (which is full of `dc1/...` entries) before this session. Fixed
by creating each entry's parent directory before writing it.

## Files changed by this note's work

- `protos/common/member_data.ksy` - `rank_tier` field doc corrected.
- `docs/protocol/dc_table.md` - key_hash/type_hash naming scheme documented,
  disc-extraction method documented, points at the checked-in tool.
- `docs/protocol/proto-map.md`, `docs/protocol/knowledge-inventory.md`,
  `docs/OPEN-QUESTIONS.md` - `rank_tier` row/entries corrected.
- `research/tools/dc_hash_crack.py` (new) - the checked-in, runnable
  hash-cracking tool; verified to reproduce every match above from a clean
  invocation, including the negative results (`pReportArray`).
- `server/lib/psarc_crypt.py` - `unpack`/`extract` nested-directory bug fix
  (see above), needed to make the disc's `bin.psarc` actually unpackable.
