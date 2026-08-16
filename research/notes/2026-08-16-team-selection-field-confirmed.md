# `RoomCreate` wire offset `0xb0:0xb2`: team selection, confirmed via live capture diffing

**Status: confirmed, high confidence.** Found by brute-force diffing ~24 real
`RoomCreate` captures across a deliberate sweep (the user hosted every available
Supply Raid map with both Red and Blue explicitly selected, plus several
default/spectator attempts), after the `map_id` field investigation
(`research/notes/2026-08-16-map-id-vs-team-confound.md`) turned up a genuine
confound and needed disentangling with a controlled dataset.

## The field

`RoomCreate` (opcode `0x12f`, client→server, 232 bytes) wire offset `0xb0:0xb2` (2
bytes, big-endian) is a small integer:

| Value | Meaning |
|---|---|
| `0x0000` | No team selected (spectator/random/default) |
| `0x0001` | Blue team |
| `0x0002` | Red team |

## Evidence

Full sweep, one row per live host attempt (map × team), collected over one session:

| Map | Team | `0xb0:0xb2` |
|---|---|---|
| Checkpoint | Blue | `0001` |
| Checkpoint | (unset) | `0000` |
| Checkpoint | Red | `0002` |
| Checkpoint | Blue (2nd) | `0001` |
| Lakeside | (unset) | `0000` |
| Lakeside | Red | `0002` |
| Lakeside | Blue | `0001` |
| Bill's Town | (unset, ×2) | `0000`, `0000` |
| Bill's Town | Red | `0002` |
| University | (unset) | `0000` |
| University | Red | `0002` |
| University | Blue (×2, retry) | `0001`, `0001` |
| High School | (unset) | `0000` |
| High School | Red | `0002` |
| High School | Blue | `0001` |
| Downtown | (unset) | `0000` |
| Downtown | Blue | `0001` |
| Downtown | Red (accidental unset first attempt) | `0000`, then `0002` on the real attempt |
| The Dam | (unset) | `0000` |
| Downtown | (unset, "Red" intended but too early) | `0000` |
| The Dam | Blue | `0001` |
| The Dam | Red | `0002` |

**Zero exceptions across the whole dataset.** Every single sample matches the
0/1/2 = unset/Blue/Red scheme regardless of map, including two cases where a
*different* field (wire offset `0xc`, previously mislabeled "map_id" - see the
superseding note above) gave an unexpected value on the same capture - this field
was unaffected both times and read correctly.

## Why this was missed for so long

Offset `0xc` (the original "map_id" candidate) happened to correlate with team in
several early samples purely by chance/confound, which is what sent this whole
investigation down the wrong path for a while (see `2026-08-16-map-id-vs-team-
confound.md`). `0xb0:0xb2` was sitting a few bytes further into the same message,
never diffed on its own until a fully controlled map×team sweep forced it into view.

## What this is NOT confirmed to explain

This is a **client→server** field - it's what the host told us they selected, not
proof of what fixes anything on the receiving end. Two live-tested speculative
fixes this session (`build_member`'s entry offset 16 first with a blind `team=0`
guess, `docs`/code has the full history) did not resolve the `NET_SM_SERVER_LOBBY`
stall or the `net-game-manager.cpp:1358` team-assert boot. Whether echoing the
*real* captured value into that same slot (now implemented, see
`tools/session_manager_stub.py`'s `build_member`) changes either of those symptoms
is untested as of this note - a real experiment, not a proven fix.

## How to apply

- This field can now be read confidently for any future capture work without
  re-deriving it.
- The still-open question is whether/where the server needs to *echo* this value
  back for the client's own host-side team-assignment logic to resolve correctly -
  not yet confirmed either way.

## Update (2026-08-16, later same night): echoing the real value tested, no effect

Live-tested the real captured team value written into `Member`'s entry offset 16
(the fix described above, implemented in `tools/session_manager_stub.py`). Result:
**no observable difference** - same pattern as before (first attempt stalls, second
attempt loads into the match and gets booted out after ~10-15s exactly as before).

This closes out the "maybe the server just needed to echo the real value instead of
a guess" theory for THIS SPECIFIC SLOT (`Member` entry offset 16) - falsified with
the actual correct data, not just a wrong guess.

**Correction, same night**: this was initially over-read as evidence the whole
10-15s boot is unfixable client-internal logic "outside server reach." That's wrong
and was called out directly - this is shipped, working retail code; if it asserts
under our server in a way it didn't under Sony's, something we're not sending or
doing is the actual cause, full stop. The earlier Ghidra trace only showed that 8
specific functions checking a team-index bound don't read wire data *directly* -
it never traced what populates the array those functions read from, which is a
completely open question and the real next target. A confirmed, never-implemented
lead already sitting in this project's own docs: `docs/protocol/README.md` row 23,
opcode `0x144`/`HostRank` (server→client, decompiled, paired with `0x143` which the
client DOES send) - our stub has never sent this message at all. Worth tracing
whether it (or something else server-side) is what's supposed to feed the array the
assert checks, before concluding anything is out of reach.
