# First Real HTTP Capture (session 3)

Via RPCS3's DNS-hook redirect (`config_BCUS98174.yml`, `Net: IP swap list`) + `tools/catch_http.py` listening on port 80. Full raw log: not committed (gitignored, `captures/http_catch.log` - live capture artifact); content below.

## Captured requests

```
GET /patch.psarc.crypt HTTP/1.1
Host: t1.patch.s3.amazonaws.com
Connection: close
User-Agent: DNTG-HTTPC/1.1

GET /campaign.config.txt.crypt HTTP/1.1
Host: t1.campaign.config.s3.amazonaws.com
Connection: close
User-Agent: DNTG-HTTPC/1.1
```

Each requested twice (~2s apart - one retry). No request path/query params beyond the bare GET - no auth headers, no cookies, no NP ticket attached to these specific requests (at least not in what our minimal catcher captured - it stops reading after the header block, see `tools/catch_http.py` limitations).

## What this confirms

- **`DNTG-HTTPC/1.1` user agent** - "DNTG" almost certainly = "Dog" (Naughty Dog's own custom HTTP client), confirming these go through the game's own bespoke HTTP layer, not a generic `cellHttp` default UA.
- **`.psarc.crypt` / `.txt.crypt`** - Naughty Dog's own archive format (PSARC) and a plaintext config, both encrypted at rest. Matches `.crypt` extension already seen on `t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt` in the session-1 strings pass.
- These are **content-delivery/config fetches, not authentication** - separate from the `t1.final.prod.naughtydog.com` "Content Delivery" endpoint that's still failing (see below). The game apparently fetches multiple independent things labeled/routed differently even though the log only printed one "Content Delivery :" line - `t1.patch...` and `t1.campaign.config...` weren't announced the same way, or the announcement uses a different log line not yet grepped for.

## Open question: why does `t1.final.prod.naughtydog.com` still fail after the same fix worked for these two

Both `t1.patch.s3.amazonaws.com` and `t1.campaign.config.s3.amazonaws.com` redirected successfully. `t1.final.prod.naughtydog.com` has failed identically (~22s timeout) on every attempt so far, despite config edits that should match it.

**Root mechanism, confirmed from RPCS3 source** (`Emu/NP/np_dnshook.cpp` + `Emu/Cell/lv2/sys_net/lv2_socket_native.cpp`): `dnshook` is a `g_fxo` singleton. Its constructor parses `g_cfg.net.swap_list` **once**, at construction, into `m_redirs` - there is no live-reload and no per-hostname IP cache in the hook itself (`analyze_dns_packet` just matches fresh against `m_redirs` on every query). So the actual rule is: **whatever `IP swap list` value was in the config at the moment that `dnshook` instance was constructed (i.e. at that boot) is what's active for the rest of that boot, no matter what the config file is edited to afterward.** Editing `config_BCUS98174.yml` while RPCS3/the game is already running, or even between quick in-emulator game restarts, may not get picked up unless a fresh `dnshook` is actually constructed - most reliably guaranteed by fully closing and reopening RPCS3, not just restarting the game. Given the captured patch/campaign.config requests happened successfully, *some* boot did pick up those two entries correctly - so this is a timing/ordering issue between "when was the config saved" and "when did the current boot's `dnshook` get constructed," not a fundamental block. **Next step: fully close and reopen RPCS3 after saving any `IP swap list` edit, before retrying.**
