# Pak-numbering for map content: no code path found statically; PS4 comparison reinforces "pak23 is SP-only"

Follow-up to `research/notes/2026-08-16-level1-psarc-version-check.md`, which left open
whether `pak23/level-1.psarc.crypt` (all-SP-campaign-content, no "Checkpoint") is the
one shared pak the client always fetches regardless of map, or whether a per-map pak
number exists that the client should be requesting but currently isn't. Two lines of
investigation, both inconclusive-but-informative.

## 1. Static analysis: no resolvable code path builds the `pak%i` paths

Candidate format strings identified in `research/strings/strings_ascii.txt` (all in
the `.rodata`-like region around `0xeb35c0`-`0xeb6a08`):

- `0xeb35c0` `%s/build/%s/pak%i-coop.psarc`
- `0xeb3b48` `%s/build/%s/pak%i` (matches the captured `build/main/pak23/...` shape)
- `0xeb36f8` `%s/pak%i.psarc`
- `0xeb3af8` `%s/build/%s-sp` (plain "-sp" template - single-player-specific string, sits right next to the pak%i family)
- `0xeb3b60` `%s/build/%s/pakps%i-coop`
- `0xe898e0` `level-%d`, `0xe89660` `%s/pak%d.txt`, `0xe7c738`/`0xe7c758` `~DATABRANCH/pak%d/post[-%d]`

Ran `GetReferencesTo.java` (Ghidra's `ReferenceManager`, the same method that
successfully traced the invite-server and session-manager code previously) against
all of these. **Zero references found for every single one** except `0xe898e0`
(`level-%d`), which had 4 references, all into `FUN_00567578` - a function that on
inspection is unrelated to content-fetch (writes a `0xbadb100d` sentinel and looks
like a telemetry/assert-registration helper, not a path builder).

To rule out non-instruction references (e.g. a data table of string pointers indexed
by an enum, which wouldn't show as an `Reference` even after full analysis), wrote a
new script `tools/ghidra_scripts/ScanForPointers.java` that raw-scans every loaded,
initialized memory block for 4-byte-aligned words matching each target address as a
literal pointer value. Same result: **no hits** for any of the `pak%i`/`pakps%i`
family, and the one `level-%d` hit found this way (`0x01273e04`, in `SECTION23`, no
containing function) is the same telemetry-adjacent one already ruled out above.

**Control check**: also ran both methods against `0xe6d310`
(`build/%s/text1/%i.networking`) and `0xe6d2f8` (`build/%s/actor%i`) - the former is a
template we have **live, confirmed proof of use** for (`captures/http_catch.log` shows
a real `GET /build/main/text1/2.networking.crypt` request, an exact match with
`%s`=`main`, `%i`=`2`). Both came back with **zero references too**, by both methods.
This is the important result: it's not that the `pak%i` strings are specifically dead
- the entire path-template string family, including one we know for certain the
client executes at runtime, is invisible to both static-reference techniques in this
Ghidra project.

**Likely explanation**: `docs/ghidra-setup.md` already documents "relocations are not
processed" as a known limitation of this project's PS3 loader setup. These templates
plausibly live in a relocatable pointer table (populated by the PS3 dynamic
loader/relocator at process load time) rather than being referenced by literal
`lis`/`addi` immediates in code - if so, the `.data` bytes as loaded into Ghidra at
those table slots are pre-relocation placeholders, not the real string addresses,
which would explain a clean zero across every string in the family including a
confirmed-live one, rather than partial/spotty results. Not proven (no relocation
table located to check byte-for-byte), but it fits the evidence better than "this
whole string family is coincidentally dead code" - one of them is provably live.

**Conclusion for part 1**: inconclusive by design of this attempt. No static evidence
either confirming or ruling out a map_id -> pak-number mapping; the code that
constructs these paths was not located. This needs either a live RPCS3 debugger
break-on-string-address session (watch for a read/execute touching `0xeb3b48` during
an actual content-fetch, sidestepping Ghidra's reference resolution entirely) or
locating/processing the relocation table, not more reference-graph search of the
current static Ghidra project.

## 2. PS4 remaster comparison: `pak32/level-1` parallels PS3's `pak23/level-1` exactly

Fetched `https://t1ps4.final.prod.s3.amazonaws.com/build/ps4/main/pak32/level-1.psarc.crypt`
(HTTP 200, 5,853,184 bytes - confirmed live, genuinely different content than the PS3
file's 8,096,488 bytes). This is *The Last of Us Remastered* (PS4, 2014), a different
platform/build than this project's PS3 target - treated as directional evidence only.

**It decrypts cleanly with this project's existing PS3 keys** - `tools/psarc_crypt.py`
reports `HMAC OK` with no changes, same `SECRET_KEY`/`HMAC_KEY` as
`docs/known-keys.md`. Notable on its own: Naughty Dog reused the same Blowfish/HMAC
content-delivery keys across the PS3 original and the PS4 remaster three years later,
not just across the save-game-tool/content-delivery boundary already documented.

Contents: 47 entries (vs. PS3's 48), same naming scheme
`coop-<location>[-pak|-sab-pak]-ingame14.pak` (PS3 uses `ingame12` - consistent with a
later, remastered asset revision), same location set: Bill's Town
(`bil-church`/`bil-high-school`/`bil-watertower`), `capitol`, `docks`, `hom-town`,
Pittsburgh/Hunters (`hun-bookstore`/`hun-street`), Lakeside
(`lak-mine`/`lak-street`), `objective`/`objective-crossbow`, `out-downtown`,
`sewer-camp` (new vs. PS3's list), `sub-street`, `tom-river`, `uni-campus`,
`wil-bus-depot`. **No Factions multiplayer map names anywhere.** This is the same
single-player-campaign-location content as PS3's pak23, just a later asset revision.

## Answer to the direct question

**No evidence found, in either direction, of Factions maps using a genuinely
different/separate pak-numbering scheme reachable via a confirmed map_id -> pak-number
formula.** What we have:

- Both platforms' "master" numbered level pak (`pak23` on PS3, `pak32` on PS4) contain
  exclusively single-player campaign geography, under both asset revisions checked
  (`ingame12` PS3, `ingame14` PS4). This is now **two independent data points**
  agreeing that this specific pak slot is SP-only - the PS4 comparison meaningfully
  strengthens (doesn't just replicate) the earlier PS3-only finding, since it shows the
  same "SP-only master pak, arbitrary platform-specific number" pattern recurring
  across a build with an unrelated pak-number assignment (23 vs 32) and no reason to
  coincidentally agree on content type if the numbering were map/mode-driven.
- The static analysis needed to find an actual map_id -> pak-number code path
  (confirm/deny a separate MP mechanism) dead-ended - not because the strings are
  proven dead code, but because Ghidra's reference resolution doesn't reach this
  string family at all, live-confirmed template included. This is a tooling gap, not
  a "there is no such code" finding.

**Confidence**: medium-high that pak23/pak32 specifically are SP-only (two platforms
agree, zero MP names across 95 combined entries). Low/unresolved on whether a
separate, different-numbered pak exists for Factions maps and what would compute its
number for a given map_id - open question, needs live debugger or relocation-table
work, not further static reference search.

## How to apply next

1. A live RPCS3 debugger session with a read/execute breakpoint at one of the
   `pak%i`-family string addresses (`0xeb3b48` first - closest wire-shape match) during
   an actual `RoomCreate` + map-load sequence would settle both the "is this code
   live" and "what computes `%i`" questions in one session, sidestepping the
   relocation-table gap entirely.
2. If that's not available soon, worth checking whether the PS3 EBOOT's relocation
   section can be located and processed (even partially/manually) to fix up whatever
   pointer table backs this string family, then re-running
   `tools/ghidra_scripts/ScanForPointers.java` (added in this pass, reusable) against
   the same address list.

## Correction (2026-08-16, later the same day): live observation contradicts the "missing MP pak" theory entirely

Direct watching of `catch_http.py`'s live traffic across many Checkpoint
load attempts on 2026-08-16 **never showed any HTTP request beyond the always-present
`pak23/level-1.psarc.crypt`** - no second/different pak, no 404, nothing. That's
stronger and more direct than anything in this note or `2026-08-16-level1-psarc-
version-check.md`: it rules out "the client asks for a different pak and we're
failing to serve it," which was the leading theory both notes were built around.

Given standard PS3-era game architecture, this makes sense in retrospect: base
multiplayer map geometry for a retail disc game is almost certainly shipped **on the
disc itself** (`PS3_GAME`/`dev_bdvd`), not streamed from a CDN - CDN paks like the
ones decrypted in this pass are far more likely post-launch SP-campaign-content
patches/DLC delivery, unrelated to which maps are already on-disc. This reframes
"Checkpoint loads as an empty skybox" as **probably not a content-delivery problem at
all** - more likely a local asset/disc-image issue (an incomplete or non-matching
`PS3_GAME` dump missing that specific map's on-disc data) or something else entirely
in the load path, not something `catch_http.py`/this project's server stack can fix
by serving a different pak.

**Downgrading this whole investigation thread (this note and the version-check note
before it) to a dead end for the "is there a missing MP pak" question specifically.**
The static "how does pak-number get computed" tooling gap (relocations unprocessed)
may still be worth fixing for other reasons someday, but not on the theory that it
unblocks Checkpoint - that theory is now considered ruled out by direct live
observation, not just deprioritized.
