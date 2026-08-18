# Facebook Connect: what the button does, why it fails, and where a stub plugs in

Static RE pass on the "CONNECT TO FACEBOOK" flow (`ndlib/net/facebook.cpp`),
driven by the ask "I get *Failed to get Facebook data*; I want a local
stub/replacement — it just puts your friends' names into your camp."

Method: `tools/eboot_analysis` (raw-EBOOT, no Ghidra). VMA = file offset +
0x10000. All function/string addresses below read off
`powerpc64-linux-gnu-objdump` disassembly of the decrypted EBOOT.

## TL;DR

- The feature is **additive/cosmetic**: it overwrites your already-populated
  clan survivors' procedural names with your Facebook friends' real names
  (and, separately, downloads their profile pictures). Per
  `docs/factions-metagame-reference.md` it also grants a one-off **3
  One-Use Boosters** — the only non-cosmetic effect.
- The client does **not** do Facebook OAuth itself. There is **no** login /
  webview / `dialog/oauth` / `sceNpFacebook` string anywhere — the only
  `facebook.com` strings are Graph API **data** endpoints. The client expects
  to already hold an **`access_token`**, acquired asynchronously by ND's net
  layer (tagged `"Facebook SignIn"`), brokered through ND's dead backend
  (Sony-account-linked FB token). **That token fetch is what fails**, so the
  Graph calls never even fire → "Failed to get Facebook data".
- Clan survivor names live in **`profile.21`** (`NetPlayerData::m_tusData`,
  the 0x5028-byte record this project already round-trips), sourced normally
  from the `pFirstNames`/`pLastNames` tables in `net-player-data.cpp`. So
  there are two independent ways to get friend names into the camp: feed the
  Facebook code path, or write the names straight into the profile record.

## The code (all confirmed from disassembly)

Module cluster: `ndlib/net/facebook.cpp` string at VMA `0x00ed6f18`; code at
`0x00ac1670`–`0x00ac2100`.

### Token / sign-in gate — `FUN_00ac1ce8`

Returns the cached `access_token` pointer (`obj+12` region). Logic:
- `lbz r0, 296(r3)` — a "have valid token" flag at `obj+0x128`. If set, return
  cached token immediately.
- Else `bl 0x347414` (precondition check) then a time-vs-expiry compare
  (`obj+268` is the expiry, `bl 0xa235f0` = now). If expired, sets a
  "refreshing" flag (`obj+464 = 1`), logs with tag `"Facebook SignIn"`
  (`0x00ed6f30`, level 0x4000, code 1001, via logger `0x729ef4`), and kicks
  off the async token fetch (`bl 0xa10110`, handle stored at `obj+448/456`).
- **Returns 0 (null) while there is no valid token.**

This async fetch (`0xa10110`) is ND's net/NP path to obtain the FB token. With
the backend dead, it never completes → the flag never sets → the getter keeps
returning null.

### "Get my name/id" — `FUN_00ac1e4c`

```
r3 = FUN_00ac1ce8()            ; token
if (r3 == 0) goto fail         ; <-- "Failed to get Facebook data" originates here
...
token = FUN_00ac1ce8()
sprintf(buf, 512,
        "https://graph.facebook.com/me?fields=name,id&access_token=%s",  ; 0x00ed7120
        token)
ok = FUN_00ac57c8(buf, 0, parse_cb=0x00ac084c, ctx)   ; HTTPS GET + parse
; retries up to 10x on failure (r29 loop 0..9)
```

### "Get my friends" — `FUN_00ac1f94`

Same shape, URL `"https://graph.facebook.com/me/friends?fields=name,id&access_token=%s"`
(`0x00ed7160`), parser callback `0x00ac0a24`. After the fetch it calls
`FUN_00ac17b0` (the `facebook-server` sibling backend, below) to resolve which
friends are also players.

### Response parsers — JSON

- `me` parser `FUN_00ac084c` and friends parser `FUN_00ac0a24` extract JSON
  keys **`name`** (`0x00e98630`), `id` (numeric), and for the picture variants
  **`source` / `width` / `height`** (`0x00ed6f10` / `0x00ed6f08` / `0x00ed0010`).
- Expected shapes (old Graph API v1):
  - `/me`  → `{"name":"...","id":"<digits>"}`
  - `/me/friends` → `{"data":[{"name":"...","id":"<digits>"}, ...]}`

### The `facebook-server` sibling backend (separate from Graph)

`FUN_00ac17b0` (call site `0x00ac1828`) and `FUN_003538c0` speak the opcode-0x11
sibling protocol (see `docs/protocol/0x11_sibling_servers_family.md`):
`facebook-set %s %llu` (`0x00ed6f40`), `facebook-get-npid ` (`0x00ed6f58`),
`facebook-get-fid` (`0x00e7a0d0`). This maps FB-id ↔ NpId (which friends play
the game, for presence) — **not needed** just to name the clan.

### Profile-picture downloads (separate)

`https://graph.facebook.com/%lld/picture?...` at `FUN_00379428`,
`FUN_003974ac`, `FUN_00398674`, `FUN_003c203c` — avatar loading, optional.

## The connect flow, end to end (confirmed)

- Camp/clan menu "CONNECT TO FACEBOOK" button → `FUN_00ac1670` (callers
  `0x0034c580`, `0x00350170`). It spawns the sign-in **worker thread**
  `FUN_00ac2324` (via `sys_ppu_thread_create` wrapper `0xa10110`), gated by
  `0xa10258` (don't respawn if already running).
- Worker `FUN_00ac2324`: clears `obj+296`, calls the **sign-in gate**
  `FUN_00ac20f4` (`bl` @ `0x00ac237c`). If it returns 0 → runs `/me` fetch
  (`FUN_00ac1e4c`) then `/me/friends` fetch (`FUN_00ac1f94`); else skips them
  → "Failed to get Facebook data".
- **The gate `FUN_00ac20f4` gets the token from Sony's `sceNpSns` library**
  (NP Social Networking Service — the official PS3 Facebook API), NOT from an
  ND backend or a raw HTTP call. Confirmed by resolving the NID import stubs it
  calls (lib.stub descriptor @ `0xe59c54`, library name string `sceNpSns` @
  `0xe58fd4`):
  - `sceNpSnsFbInit` (NID `0x2c0f3548`)
  - `sceNpSnsFbCreateHandle` (`0x8fd1d549`, trampoline `0xe5878c`) → returns a
    handle; `< 0` aborts (`blt 0xac2280`).
  - `sceNpSnsFbGetLongAccessToken` (`0xba8c569e`, trampoline `0xe587ac`) →
    fills a result struct with the long-lived FB **access token**; returns 0 on
    success (checked against sceNpSns error `0x8002451c`). The gate then
    `strncpy`s 256 bytes from `result+8` into the token buffer `obj+12` and
    stores an expiry in `obj+268` (f32).
  - `sceNpSnsFbDestroyHandle` (`0x6e42c0dd`, `0xe5876c`) / `sceNpSnsFbTerm`
    (`0xc05545fd`) to clean up.
  - The request param the gate builds (272 B @ `r1+112`) embeds the game's
    Facebook **app id** as a u64: `0x0001b6a7824b8012` = **482305538490386**
    (The Last of Us's registered FB app). Result buffer is 4112 B.
  - On real hardware `sceNpSnsFbGetLongAccessToken` reaches out to Sony's NP
    servers, which return the FB token Sony stored when the account linked
    Facebook in system settings. **RPCS3 stubs `sceNpSns`**, so the call fails
    → gate returns non-zero → fetches skipped. This is the single point that
    breaks offline, and it is emulator-level, not game-level.
- The token getter `FUN_00ac1ce8` returns `obj+12` (token buffer) only when
  `obj+296==0`, precondition `FUN_00347414` (reads a global at `+0x1df8` —
  looks like "NP available", true in a working NP setup) passes, `now <=`
  expiry `obj+268` (f32), and `obj[12] != 0`. It is *also* the game-wide
  "am I connected to FB?" oracle (~15 menu/HUD call sites), which is why we do
  **not** force it non-null (that would hide the connect button); instead the
  gate patch populates the token so the getter returns valid *naturally*.

## The authentic path (skeleton — for a real PS3 or a future sceNpSns impl)

This is what a faithful, un-faked emulation would do; recorded so it can be
exercised later (e.g. on real hardware). Not testable on stock RPCS3 today
because `sceNpSns` is stubbed, and forking RPCS3 to implement it is out of
scope for now.

The ONLY thing that has to change vs. a real successful sign-in is that
`sceNpSnsFbGetLongAccessToken` must return success + a token. Everything after
it (the Graph GETs, the clan-populate) is the game's own real code and works
unmodified once redirected. So the authentic setup is:

1. **`sceNpSnsFbGetLongAccessToken` returns a token.** On real hardware this is
   automatic if the account's Facebook link is live on Sony's NP side (likely
   dead in 2026, so this is the piece to verify on a real PS3). In an emulator
   the faithful version is an `sceNpSns` module that fills the result struct and
   returns `CELL_OK`:

   ```
   // rpcs3 Emu/Cell/Modules/sceNpSns.cpp — skeleton, NOT built (forking out of scope)
   error_code sceNpSnsFbGetLongAccessToken(s32 handle,
           vm::cptr<SceNpSnsFbAccessTokenParam> param,
           vm::ptr<SceNpSnsFbAccessTokenResult> result) {
       // param->fbAppId == 0x0001b6a7824b8012 (482305538490386), TLOU's app id
       // result layout (from the game's use): token string at result+8, ≤256 B
       std::strcpy(result->accessToken /* +8 */, "<any-non-empty-token>");
       result->expiration = /* far future */;
       return CELL_OK;   // game copies token to obj+12, sets expiry, proceeds
   }
   // sceNpSnsFbInit / FbCreateHandle / FbDestroyHandle / FbTerm: return >= 0.
   ```

   The token *value* is irrelevant to us — our Graph stub ignores it — so even a
   dummy string is faithful enough; the point is the success return.

2. **The `/me` + `/me/friends` Graph GETs go to the local stub** exactly as in
   the shipped solution below (IP/Hosts switch + the http-scheme handling).
   On a real PS3 these would hit real Facebook over TLS; locally they hit
   `facebook_stub.py`.

The **patch route below is a faithful shortcut of step 1**: instead of a
success-returning `sceNpSns`, the patch has the game's own gate write the same
result the library would have produced (token into `obj+12`, expiry into
`obj+268`) and return success. Same end state, no emulator changes.

## Solution shipped (patch route — the "for now")

Everything below is in the repo. No EBOOT binary editing — a toggleable
`patch.yml` + an RPCS3 config switch + a text-file-driven stub.

- **`tools/facebook_stub.py`** + **`tools/facebook_friends.txt`** — plain-HTTP
  stand-in for graph.facebook.com. Serves `/me`, `/me/friends` (Graph JSON
  from the editable friends file), and empty images for `/…/picture`. First
  line of the txt = you (`/me`), the rest = friends. Verified locally.
- **`tools/rpcs3/facebook_stub_patch.yml`** — two required entries + one
  optional:
  1. *Facebook sign-in success* — overwrites the gate `FUN_00ac20f4` prologue
     (9 instrs, 36 B, verified via objdump) to write token `"STUB\0"` to
     `obj+12`, set expiry `obj+268 = 0x7F000000` (f32 ≈ 1.7e38, far future),
     and `return 0`. This is exactly what a real successful sign-in does, so
     the token getter then returns valid on its own.
  2. *Graph http scheme, names* — rewrites the `/me` (`0x00ed7120`) and
     `/me/friends` (`0x00ed7160`) URL format strings `https://`→`http://`
     (+ NUL re-terminator), so they route through the game's plain-http path
     to the stub. Required because the Graph URLs are the game's only
     `https://` (all other content is plain `http://` — hence why
     `catch_http.py` already works on :80; confirmed from the EBOOT URL
     strings: `http://t1.patch.s3.amazonaws.com`, `http://%s.s3.amazonaws.com`,
     etc.). Avoids any TLS MITM.
  3. *Graph http scheme, pictures* (optional) — same rewrite for the three
     `/…/picture` URLs, if you want avatar loads to resolve locally.
- **RPCS3 config** — Network → IP/Hosts switches (append to existing S3
  entries with `&&&`): `graph.facebook.com=<stub-ip>` (optionally
  `api.facebook.com`, `graph-video.facebook.com`). dnshook rewrites hostnames
  only (not literal IPs) — fine here. **This is the step most easily missed:
  without it graph.facebook.com resolves to the real Facebook IP
  (157.240.14.x), which the emulator can't reach → endless 5s retry spin.**
- **Serving** — the Facebook routes are folded into `catch_http.py`
  (`FB_HOSTS` branch), so the single :80 server you already run for S3/profiles
  answers `/me`, `/me/friends`, `/…/picture` too (from `facebook_friends.txt`).
  `facebook_stub.py` remains as a standalone equivalent if you'd rather run it
  on its own IP.

## Live test — 2026-08-17 (first attempt)

Confirmed from `RPCS3.log`: all three patches applied at boot; the game issued
`http://graph.facebook.com/me?fields=name,id&access_token=STUB`,
`/me/friends…&access_token=STUB`, and `/me/picture…` — proving the gate patch
(sign-in success), the token injection (`STUB`), and the http-scheme patch all
work, and the precondition `FUN_00347414` is a non-issue (the fetches ran).
`sceNpSnsFbInit` shows as an RPCS3 `TODO` stub (harmless — it's the module
init, not the gate's token call, which the patch skips). The ONLY failure was
`graph.facebook.com` missing from the IP/Hosts switches → it resolved to
`157.240.14.15` (real Facebook) and connect failed/retried every 5s. Fix =
add the host switch above + restart the merged `catch_http.py`.

## Live test — 2026-08-17 (working)

With `graph.facebook.com=<stub-ip>` added to the IP/Hosts switches and the
merged `catch_http.py` running, the flow works: `/me` and `/me/friends` are
served once each and parsed (the game then sends all 11 friend fbids to
`facebook-get-npid`), and the player's own name shows as the `/me` name
(first line of `facebook_friends.txt`). Two follow-on issues, both resolved:

- **facebook-server backend Error 9.** After a successful connect the game
  opens `facebook-server` connections (`facebook-set` / `facebook-get-fid` /
  `facebook-get-npid`) on 7320. The stub fell through to the ticket path
  (generic reply + server-close), which the client reads as `recv() failed
  (errno=0)` → `Error 9`. Fixed by a dedicated `facebook-server` handler in
  `ticket_server_stub.py` (proper `+`-line replies + NUL sentinel + hold for
  client close, mirroring leaderboard). See that file's `handle_facebook`.
- **The lobby avatar spinner was a JPEG-vs-PNG format bug, NOT a
  connection/RPCS3 limit.** The picture *was* downloading fine (17 KB served
  on a 5s loop). The image loader `FUN_00ac719c` (@ `0x00ac7384`) picks its
  decoder from the URL's last 3 chars: `strcmp(url_end-3, "png"` @ `0x00ed7490`)
  → PNG decoder if equal, else JPEG. Our `/me/picture?...access_token=STUB` URL
  ends in `STUB`, so the game always uses the **JPEG** decoder; we were serving
  PNG → silent decode failure → spin + re-fetch. Fixed by serving JPEG
  (`tools/facebook_pics/me.jpg` override + embedded placeholder JPEG); the icon
  then renders. Lesson: `/picture` MUST be JPEG unless the URL ends in `png`.

## Open / still to confirm

- Clan survivor renaming: `/me/friends` is parsed (all 11 friends reach
  `facebook-get-npid`), but whether the survivor names visibly change was not
  confirmed. The feature *overwrites an already-populated clan* (metagame note)
  and shows on the Clan Roster / camp screen, not the MP lobby — so it needs an
  existing clan of survivors to be visible. `facebook-get-npid` currently
  returns fake NpIds per friend (a resolution test); the code
  (`FUN_00ac1f94` → `FUN_00ac12c0`, called unconditionally after resolution)
  suggests naming doesn't depend on resolution.
- Observed side effect (kept): returning fake NpIds for `facebook-get-npid`
  makes all the FB friends appear in the in-game **friends list** with those
  fake PSN ids (the "which FB friends are on PSN" resolution succeeding on stub
  data). Harmless as cosmetic population; do NOT act on them (party invite /
  join / presence against non-existent NpIds may error or hang).

## Alternative not taken — edit `profile.21` directly

Clan survivor name seeds live in `NetPlayerData::m_tusData` (0x5028 B), which
this project already round-trips (Blowfish+HMAC-SHA1+LZF, keys solved). Writing
names straight in bypasses Facebook entirely (no patch, no network) but does
not exercise the real feature or grant the 3 boosters, and needs the roster
offsets mapped. Kept as a fallback if the code-path approach stalls.
