# `RoomCreate` wire offset `0xc` ("map_id"): the map-identity label is disputed, not confirmed

Correction to a claim treated as settled since `2026-08-15`. `tools/session_manager_stub.py`'s
`build_room_joined` docstring (and every doc/note citing it, including
`research/notes/2026-08-16-level1-psarc-version-check.md`) labeled `RoomCreate`'s wire
offset `0xc` (4 bytes) as a map/level identifier, based on 5 captures where it read
`0x9` for repeated "Checkpoint" selections and `0x13` for repeated "Lakeside"
selections. That original raw capture data was never saved to its own note - only
summarized as a conclusion - so it can't be rechecked now.

## Tonight's contradicting evidence

Live-testing `SetAttrFlags`/team-selection (see `docs/protocol/session_manager_and_matchmaking.md`
row 19 and `research/notes/2026-08-16-net-sm-server-lobby-dispatch.md` for that
thread), the user hosted three times in a row with **mode and map both held constant**
(Supply Raid, Checkpoint - confirmed explicitly by the user, not assumed) and only
**team** changing:

| Attempt | Team | `RoomCreate` offset `0xc` value |
|---|---|---|
| 1 | Red | `0x13` |
| 2 | Red | `0x13` |
| 3 | Blue | `0x9` |

These are the **exact same two numeric values** the `2026-08-15` finding attributed to
two different maps - now correlating perfectly with team instead, with map held
constant. Both explanations can't be literally true of the same field at the same time.

## Most likely reconciliation (not proven)

Solo-hosting may default to one team unless the player manually switches. If the
original `2026-08-15` test happened to test one map on the default team and the other
map after manually switching team (without treating team as a variable to control),
both the original finding ("changes with map, stable within a map") and tonight's
finding ("changes with team, stable within a team") could each look true in their own
limited sample, without either being the full picture. A genuine map+team-combined
index, or a per-map "default team" quirk, would also fit both datasets - not
distinguished by evidence in hand.

## What this does NOT affect

`tools/session_manager_stub.py`'s handling of this field is unchanged and still
correct regardless of what it actually means: `RoomCreate`'s offset `0xc` is read and
echoed straight back into `RoomJoined`'s own offset `4:8` unconditionally
(`build_room_joined(..., map_id=map_id)`), with no branching on its value. Whatever
this field encodes, blind-echoing it has never been shown to be wrong - this is a
documentation/understanding gap, not a known stub bug.

## What this DOES affect

`research/notes/2026-08-16-level1-psarc-version-check.md`'s "Lakeside content present,
Checkpoint content absent, matching map_id `0x13`/`0x9`" correlation - already flagged
SUPERSEDED for an unrelated reason (no second HTTP request ever observed) - loses
another leg to stand on: even the map_id labeling it leaned on for "which map is
which" is no longer trustworthy. The "why does Checkpoint load as an empty skybox"
question should be treated as fully open again, not partially explained by either the
content-pak theory or the map_id-correlation theory.

## Confidence

Medium that team is at least *part* of what this field encodes (tonight's test was
genuinely controlled for map/mode, unlike the original). Low on whether it's *purely*
team, purely map, or a combined index - would need a proper 2x2 test (both known maps
x both teams, 4 data points minimum) to fully disambiguate, which hasn't been run.

## How to apply

Before trusting this field for anything (in either a "map" or "team" interpretation),
run the missing 2x2: Checkpoint+Red, Checkpoint+Blue, Lakeside+Red, Lakeside+Blue,
diff all four `RoomCreate` captures. If the value is a clean function of team alone
(2 distinct values, same-team-same-value regardless of map), that confirms team. If
it's a clean function of map alone, that confirms the original finding. If it varies
with both, it's a combined index and needs its own encoding scheme worked out.
