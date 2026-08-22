# `server/data/served_content/` - inventory of every file this server hands to the client

This is a catalog, not a format spec - each row says what a file is, whether
it's actually served or just a research artifact sitting in the tree, and
where to find the real protocol/format documentation. Update this when a
served path's purpose or status changes; keep the deep format detail in the
linked doc, not duplicated here.

`http_gateway.py`'s routing rule (`build_response()`): a request matching a
Facebook-Graph host (`FB_HOSTS`) is answered dynamically by `fb_response()`
and never touches disk; everything else checks for a local file at the exact
request path first (`os.path.isfile`) and serves it verbatim if present,
falling back to a live upstream fetch (usually dead, since retail's servers
are gone) and then an empty `200 OK` if that also fails.

| path | served? | real internet URL (pre-redirect) | what it is | doc |
|---|---|---|---|---|
| `campaign.config.txt.crypt` | **yes, live** | `http://t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt` | this server's deployed replacement - real container, `queue-server-addr` pointed at this server | `docs/protocol/userdata_and_campaign_config_crypt.md` |
| `campaign.config.txt.crypt.orig` | no (wrong filename) | - | untouched captured original, kept for reference/diffing, not the name the client requests | same |
| `campaign3.config.txt.crypt` | **yes, live** | `http://t1.campaign.config.s3.amazonaws.com/campaign3.config.txt.crypt` | the later-version client requests this filename instead of `campaign.config.txt.crypt` - same container/key format plus two extra keys (`enable-dlc-facebook`, `enable-dlc-facebook-text`), confirmed served (`http_gateway.log`: `served 152 bytes for campaign3.config.txt.crypt`). The two extra keys are read only by the 01.11 EBOOT (absent from 01.00 entirely) as `"1"`-prefixed boolean toggles into two standalone global flag bytes - no reader of either flag found anywhere in 01.11 by static scan, a documented dead end | `research/notes/2026-08-17-userdata-txt-crypt-format.md`, `research/notes/2026-08-22-dlc-facebook-config-keys-trace.md` |
| `net1.bin.psarc.crypt` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/net1.bin.psarc.crypt` | the DC00 data-compiler bundle for build 01.00 - map/mode/rank tables etc. Container format fully solved, and the full directory (all 392 global names) cracks 100% (`research/tools/dc_dir.py`) - but only a handful of those 392 tables have their actual CONTENTS decoded field-by-field; most are name-only. See `docs/protocol/knowledge-inventory.md` for exactly which tables are actually decoded vs. just named. | `docs/protocol/dc_table.md` |
| `net10.bin.psarc.crypt` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/net10.bin.psarc.crypt` | same container/directory situation, for build 01.11 - directory crack rate not separately re-confirmed against 01.11's own symbol corpus, don't assume it matches 01.00's 392/392 without checking | `docs/protocol/dc_table.md` |
| `profiles/<id>/profile.21` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/profiles/<id>/profile.21` | player-progression record (0x5028-byte LZF container) - GET serves it, PUT stores an uploaded one | `protos/profile_21.ksy`, `docs/protocol/profile_21_record.md` |
| `t1/upgrades/upgrades.txt.crypt` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/t1/upgrades/upgrades.txt.crypt` | SCHEMA RESOLVED 2026-08-22 (decrypted and read directly, `userdata_crypt.py decode`): NOT the `key value` whitespace format the container doc's other examples use - this and its two siblings below are CSV entitlement manifests, one row per PSN product: `<owned flag 0/1>,Both,<PSN product code>,<title code>,0,`. This file has exactly 1 row - the base title itself (`UP9000-BCUS98174_00-THELASTOFUSONPAS`, flag `0`). `userdata_crypt.py`'s generic "parsed pairs" output is meaningless for this file shape (it assumes whitespace key/value pairs) - read the raw plaintext dump instead, not the pairs section. Consumer (what EBOOT code reads this / what the flag controls) NOT traced. | container format: `docs/protocol/userdata_and_campaign_config_crypt.md` |
| `t1/upgrades/extras.txt.crypt` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/t1/upgrades/extras.txt.crypt` | same CSV schema as `upgrades.txt.crypt` above. 3 rows, all **Uncharted 1/2/3** entitlements under DIFFERENT title codes (`UP9000-NPUA80697_00`, `UP9000-NPUA80698_00`, `UP9000-BCUS98233_00`) - reads as a cross-promotional bonus-content check against other Naughty Dog titles the account might own, not anything Factions-specific. Consumer not traced. | same |
| `t1/upgrades/upgrades7.txt.crypt` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/t1/upgrades/upgrades7.txt.crypt` | same CSV schema, MUCH larger: 156 rows, the full DLC/cosmetic entitlement manifest for this game - every DLC map pack, weapon skin, mask, helmet, gesture, taunt, and national flag hat ever released (`DLC5TCTLWEAPBUND`, `DLC1WELDINGHELME`, `FLAGHATUNITEDSTA`, etc.), all under the base title code. The `7` likely marks this as a LATER/more complete manifest revision than the 1-row `upgrades.txt.crypt`, not a build-01.11-specific file (that theory is now unconfirmed/unlikely given the content has nothing build-specific about it - both files coexist and are requested by the same client). Consumer not traced. | same |
| `build/main/pak23/level-1.psarc.crypt` | **yes, live** | `http://t1.final.prod.s3.amazonaws.com/build/main/pak23/level-1.psarc.crypt` | despite the "level" name, this is MULTIPLAYER map data (`coop-*-ingame12.pak` entries - real Factions map names), not campaign content - confirmed by decrypting and listing it (`server/lib/psarc_crypt.py list`) during the `task-%x` hash-crack investigation | `research/notes/2026-08-21-task-hash-variation-trace.md` |
| `games/<online_id>.<session_id>` | **yes, generated** | n/a - server-side only, never requested by the client | this server's OWN record of a completed/registered game (`ticket_server.py`'s `record_game`), not a file the retail client ever requests - server-side bookkeeping only | `server/ticket_server.py`'s `record_game`/`handle_gamelist` |
| `me/friends`, `me/picture` | **no - dead code** | n/a | static leftovers; the actual `/me/friends` and `/me/picture` requests are intercepted earlier by the Facebook-host routing rule and answered dynamically by `fb_response()`/`fb_load_people()` (reading `FB_FRIENDS_PATH`/`FB_PICS_DIR`, NOT this path) - these on-disk files are never reached | `server/http_gateway.py`'s `fb_response` |
| `SDK/webLanguage` | unconfirmed | unconfirmed | no server code references this path by name; likely servable generically if ever requested, purpose/trigger not investigated | - |
| `favicon.ico` | servable generically | n/a | no special-case code; only reachable if something requests `/favicon.ico` directly (a browser hitting this server manually, not game traffic) | - |

## Adding a new served file

1. If it's a `.crypt` container, check whether it's the same Blowfish+HMAC
   family as `docs/protocol/userdata_and_campaign_config_crypt.md` before
   reversing anything from scratch - most of this title's `.txt.crypt` files
   are.
2. Document the file's OWN key/value schema and purpose in whichever doc is
   the right home for it (a new section of the crypt-format doc if it's a
   sibling of `campaign.config`, a new file if it's a genuinely different
   format), then add a row here pointing at it.
3. Update this table's "served?" column once you've confirmed (via
   `http_gateway.log` or by testing) whether the client actually requests it
   under this exact path.
