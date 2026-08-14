# Lesson: Some Hostnames Are Built at Runtime, Not Stored Whole

`http://t1.final.prod.naughtydog.com` (the "Content Delivery" server the game hangs trying to reach after a successful RPCN ticket exchange - see `research/notes/rpcn-connection-instability.md`/live testing) does **not** exist as a single string anywhere in `EBOOT.elf`. It's assembled at runtime from three separate pieces, all present in the strings dump (`research/strings/strings_ascii.txt`) but never connected by a pure string-table scan:

- `http://%s.naughtydog.com` (offset `0xe6a248`) - the format template. **This one actually was surfaced in the session-1 strings pass** (listed under "urls/schemes" in the original findings) - the miss was not recognizing what fills the `%s`, not failing to find the string at all.
- `t1.final.prod` / `t1.final.dev` (offsets `0xe69c20` / `0xe69c10`) - the substitution value, presumably environment-selected at build/runtime (retail build uses `prod`).
- `Content Delivery : %s` (offset `0xe6a268`) - the log line format that prints the fully-assembled URL, which is how this was actually confirmed (via RPCS3's `sys_tty_write` log output at runtime, not static analysis).

## Why this matters going forward

Static string/disassembly analysis cannot reliably find hostnames (or any data) built via string concatenation/formatting at runtime - the pieces exist separately in `.rodata` and nothing statically links them without decompiling the specific call site that does the `sprintf`/concatenation. **Live observation (RPCS3 logs, packet capture) catches what static analysis alone can miss** - this is a concrete case of it, not a hypothetical. Treat static analysis findings as a lower bound on what the game actually does, not a complete picture, and prioritize checking runtime logs/captures whenever something doesn't show up statically before concluding it doesn't exist.

## Other `%s` URL templates found (follow-up pass, same session)

- `http://%s.naughtydog.com` - confirmed substitution values: `t1.final.prod` (retail), `t1.final.dev` (likely internal/dev builds, not tested).
- `http://%s.s3.amazonaws.com` and `http://%s.s3.amazonaws.com/t1/upgrades/%s` - likely substitution values already known as *complete* literal strings from session 1 (not templated themselves): `t1.patch`, `t1.campaign.config` (full hostnames `t1.patch.s3.amazonaws.com` / `t1.campaign.config.s3.amazonaws.com` were already found whole in `research/notes/static-recon-findings.md`).
- `%s://%s%s` - fully generic (scheme+host+path all substituted), not actionable without more context on the call site.
- The Facebook/YouTube/Google template URLs are third-party social-sharing integrations, not the game's own backend - not relevant to this project's scope.
