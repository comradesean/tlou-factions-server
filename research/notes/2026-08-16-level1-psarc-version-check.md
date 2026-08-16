**SUPERSEDED (2026-08-16, later same session)**: the "Lakeside" correlation below is
now considered coincidental, not a real finding - see the correction at the bottom of
`research/notes/2026-08-16-mp-pak-numbering.md`. Direct live observation (no second
HTTP request ever seen during a Checkpoint load, across many attempts) rules out the
"client should be fetching a different pak and isn't" theory this note was built
around. Left in place for the PSARC-decrypt/provenance evidence, which is still
correct - just not the map-content conclusion drawn from it.

# `pak23/level-1.psarc.crypt`: content doesn't match "Checkpoint", plausibly matches "Lakeside"

Follow-up to `research/notes/2026-08-15-*` map-selection findings (`RoomCreate`'s wire
offset `0xc` = map id: `0x9` = "Checkpoint", live-observed as an empty skybox with no
level geometry; `0x13` = "Lakeside", live-observed loading much further before being
kicked back to lobby - see commit `515178b`). Decrypted/extracted
`tools/served_content/build/main/pak23/level-1.psarc.crypt` to check whether its
content explains that split. **`HMAC OK`** - decrypts and unpacks cleanly with
`tools/psarc_crypt.py`, same as every other `.crypt` file solved so far.

## Provenance (not user-supplied - live CDN fetch)

Unlike `net1.bin.psarc.crypt` (user-supplied from their own game copy), this file was
never provided directly - it was **live-fetched by `tools/catch_http.py`'s
upstream-proxy fallback from `t1.final.prod.s3.amazonaws.com`** (Naughty Dog's real,
still-live production S3 bucket) and cached to `served_content/` on first request.
Confirmed via `captures/http_catch.log`, `2026-08-14T13:40:17`: `responded: served
8096488 bytes for build/main/pak23/level-1.psarc.crypt (live-fetched from
t1.final.prod.s3.amazonaws.com, cached)`. So this is genuine current Naughty Dog
production content for this exact path, not something pulled from an unrelated
release/build - a "wrong game version" explanation in the sense of "fetched from the
wrong source" is unlikely. No embedded version/date/build string was found anywhere
in the archive to confirm it matches `BCUS98174`'s expected asset revision more
precisely than that (see below).

## Container-level version check: matches `net1.bin.psarc.crypt`, no divergence found

Both files decrypt to the same PSARC container version: magic `PSAR`, version
`0x00010004` (1.4), compression `zlib`, identical header layout. No format-level
evidence of a build/version mismatch between this pak and the other already-solved
`.crypt` files.

## Contents: 49 entries, all single-player-campaign-location-named, `ingame12` tag

The manifest lists 49 inner `.pak` files (Naughty Dog's own proprietary binary pak
format - not zlib/PSARC, no readable strings beyond scattered asset-name fragments
like `vox-coop-bil-church-rgn-gen-building-1`, no version/date stamps found), all
named `coop-<location>[-pak|-sab-pak|-actor-pak]-ingame12.pak`. Locations present:
`bil-church`/`bil-high-school`/`bil-watertower` (Bill's Town), `capitol`, `docks`,
`hom-town`, `hun-bookstore`/`hun-street` (Pittsburgh/Hunters), `lak-mine`/`lak-street`
(Lakeside Resort), `objective`/`objective-crossbow`, `out-downtown`, `sub-street`,
`tom-river` (Tommy's Dam), `uni-campus` (University), `wil-bus-depot` (Winter). These
are single-player campaign chapter locations - the `coop-` prefix is a real internal
naming convention (also seen in unrelated EBOOT debug strings: `net-player-coop-id`,
`net-coop-host-script-id`), not evidence this is multiplayer-specific content on its
own.

**No entry name contains "checkpoint" anywhere** - map id `0x9` has no obvious content
bucket in this pak at all. **`lak-mine`/`lak-street` are present** - plausibly the
source geometry for the "Lakeside" Factions map (id `0x13`), since Naughty Dog is
known to build Factions maps from modified campaign geometry. This lines up with the
live symptom split: Lakeside (matching content present) gets further before failing;
Checkpoint (no matching content) never gets any geometry at all.

## Important caveat: this exact file is fetched identically regardless of map choice

`captures/http_catch.log` shows `GET /build/main/pak23/level-1.psarc.crypt` requested
with the **same static path** every session observed (2026-08-14 through 2026-08-15),
independent of which map was later selected in `RoomCreate` - it is not a
per-map-parameterized request. So two explanations remain open, not fully
distinguished by this pak alone:

1. This is genuinely the one shared content pak the client always pulls, and
   "Checkpoint" content lives in a *different* `pakNN/level-N.psarc.crypt` that the
   client should also be requesting but isn't (a stubbed-server response - matchmaking
   reply, patch manifest, or similar - may be failing to hand the client whatever
   determines the map-specific fetch, so it silently reuses/only-ever-fetches this
   one).
2. This pak really is the sole/master level-content archive, and "Checkpoint" simply
   isn't in this build's shipped-to-this-CDN-path set for an unrelated (ND-side,
   possibly DLC-gating or already-dead-content) reason.

## Confidence: medium

The naming correlation (Lakeside present, Checkpoint absent, matching the exact
observed pass/fail split) is a real, specific lead - not a coincidence given how
precisely it matches the two live symptoms. But it stops short of proof: the client's
actual internal asset-lookup key for "Checkpoint" was never confirmed to literally be
`"checkpoint"`, and it's unresolved whether other `pakNN` paths exist that the client
should be fetching per-map but isn't currently being prompted to (see caveat above).

## How to apply

Next step to close this out: check whether the client ever attempts a request for a
*different* `pakNN/level-N.psarc.crypt` path when Checkpoint is selected (re-run the
Checkpoint live test with `catch_http.py`'s log open, watching specifically for any
`GET` other than the always-present `pak23/level-1` one) - if it never asks for
anything else, the missing-content theory above needs another explanation; if it does
ask for something else and gets a 404/empty fallback, that's the concrete fix target.
