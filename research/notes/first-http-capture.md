# First Real HTTP Capture (third pass)

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
- **`.psarc.crypt` / `.txt.crypt`** - Naughty Dog's own archive format (PSARC) and a plaintext config, both encrypted at rest. Matches `.crypt` extension already seen on `t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt` in the initial strings pass.
- These are **content-delivery/config fetches, not authentication** - separate from the `t1.final.prod.naughtydog.com` "Content Delivery" endpoint that's still failing (see below). The game apparently fetches multiple independent things labeled/routed differently even though the log only printed one "Content Delivery :" line - `t1.patch...` and `t1.campaign.config...` weren't announced the same way, or the announcement uses a different log line not yet grepped for.

## Open question: why does `t1.final.prod.naughtydog.com` still fail after the same fix worked for these two

Both `t1.patch.s3.amazonaws.com` and `t1.campaign.config.s3.amazonaws.com` redirected successfully. `t1.final.prod.naughtydog.com` has failed identically (~22s timeout) on every attempt so far, despite config edits that should match it.

**Actual root cause, found via RPCS3's `DnsHook: DNS query for %s` trace log** (not a caching/staleness issue after all): the game's real network-level DNS query for "Content Delivery" is **`t1.final.prod.s3.amazonaws.com`**, not `t1.final.prod.naughtydog.com`. The `sys_tty` "Content Delivery : http://t1.final.prod.naughtydog.com" line prints a *logical*/display name; the actual hostname resolved and connected to is an S3-hosted alias - the same `t1.final.prod.s3.amazonaws.com` seen as a real DNS query in the very first pcap capture back in the initial pass (`research/notes/2026-08-13-capture1-and-nd-hostnames.md` doesn't call this out explicitly - worth cross-referencing next time). This is why every `*naughtydog.com` wildcard silently never matched (the string "naughtydog.com" never appears in the real query at all), while `t1.patch.s3.amazonaws.com` / `t1.campaign.config.s3.amazonaws.com` worked immediately - those *are* queried as literal `s3.amazonaws.com` names from the start.

**Fix applied:** added `t1.final.*.s3.amazonaws.com=<ip>` to the swap list (wildcard covers both `t1.final.prod.s3.amazonaws.com` and the `t1.final.dev.s3.amazonaws.com` sibling from `research/notes/dynamic-hostname-construction.md`).

**General lesson:** a log line's printed URL/hostname is not reliable evidence of what's actually queried over the network - always verify against `DnsHook: DNS query for %s` (or a real capture) rather than trusting a human-readable log message, even one that looks like it's printing the literal request target.
