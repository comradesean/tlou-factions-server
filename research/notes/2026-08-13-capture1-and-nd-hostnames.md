# Capture #1 Analysis + Naughty Dog Hostname Check

## Capture: `captures/2026-08-13_auth-server-connect-fail.pcapng`

23,324 packets, 27-second window, unfiltered on the Windows host's main interface. The client showed "Error connecting to authentication server" in RPCS3 during the capture window.

**Finding: zero network activity related to RPCN or Naughty Dog at all.** Checked:
- DNS queries for `np.rpcs3.net` (the configured RPCN host, per `.../config/rpcn.yml`) - none. Only 3 DNS queries total in the whole capture (`t1.final.prod.s3.amazonaws.com`, `spade.twitch.tv`, `p2p-ord1.discovery.steamserver.net` - unrelated background apps).
- Traffic to either configured RPCN address (`np.rpcs3.net` or the `Reloaded` fallback `51.75.22.125`) - none.
- Raw byte search for the string `"rpcs3"` or `"naughty-dog"` anywhere in any of the 23k packets - none.

**Conclusion: this isn't a real network-level finding yet** - RPCS3 never attempted the connection during the capture window (or the capture missed it entirely). Most likely a timing issue: capture started after the attempt already failed, or DNS was cached from an earlier try so no fresh query fired (though absence of *any* traffic to the target IP argues against pure DNS caching - a real connection attempt would still generate packets regardless of whether DNS was cached).

**For the retry:** start the Wireshark capture *before* opening RPCS3, keep it running through the entire sign-in attempt until the error appears on screen, then stop - bracket the whole attempt inside the capture window. Also worth an `ipconfig /flushdns` beforehand to guarantee a fresh DNS query shows up.

## Naughty Dog backend hostnames

Two specific candidate hostnames known from the game's original era: `prod.usa.tlou.ps3.naughty-dog.com` and `auth.usa.tlou.ps3.naughty-dog.com`. Checked against everything available:

- **Not present** in `EBOOT.elf`'s strings, full disassembly, or as template fragments (checked for `%s`-style patterns that could construct the hostname at runtime) - see `research/strings/strings_ascii.txt`, `research/disasm/full.asm`.
- **No other executable modules exist** in the game install to check - `PS3_GAME/USRDIR/` contains only `EBOOT.BIN` (encrypted original) and `EBOOT.elf` (decrypted, what we've been analyzing). No separate `.sprx`/`.self` network modules.
- **Not checked yet:** `PS3_GAME/PKGDIR/PKG00/INSTALL.PKG` (16MB, dated 2013-05-10, presumably an early day-one patch) - could in principle contain a different/updated EBOOT with different hardcoded hosts, not yet extracted/examined.
- `PARAM.SFO` has no hostnames, just standard metadata (title, version `04.4100`, NP communication ID `NPWR03073_00` which is actually the trophy set ID).

**DNS check (2026-08-14):** both hostnames **do still resolve** - `prod.usa.tlou.ps3.naughty-dog.com` and `auth.usa.tlou.ps3.naughty-dog.com` both -> `76.223.67.189` / `13.248.213.45`. But an HTTP request to either returns a generic `200 OK` / 114-byte page, and HTTPS fails the TLS handshake with "unrecognized name" (SNI rejection) - both signs of a domain-parking/registrar placeholder, not a live backend. Both hostnames resolving to the *identical* pair of IPs also suggests a domain-level catch-all rather than per-service DNS records. **Dead end for live connectivity today**, even if genuine.

Still valuable: confirms Naughty Dog used a `<service>.<region>.tlou.ps3.naughty-dog.com` naming convention for their backend (service names seen so far: `prod`, `auth` - `region` seen: `usa`) - consistent with the "custom ND backend" theory from `research/notes/clan-tus-commerce-findings.md`. Worth keeping on the DNS-redirect/stub-server target list for future capture sessions in case other `<service>.<region>` combinations are still alive, or in case the client falls back to them in a way worth observing even against a dead/parked endpoint.
