# Two Findings: 404 Fallback Regression, and Literal-IP Redirects Don't Work

## The catcher's 404 fallback broke NetInit entirely

After the `net1.bin.psarc.crypt` success, `tools/catch_http.py` was changed to default to `404 Not Found` for any request path we don't have a real file for (testing whether 404 lets the game skip an optional check gracefully - see `research/notes/first-http-capture.md`). This actively broke things: `patch.psarc.crypt` and `campaign.config.txt.crypt` (no real files available for either) started getting `404`, and the game failed to even reach a menu - a regression from the earlier state where an **empty `200 OK`** for those same two paths worked fine.

**Conclusion: an empty `200 OK` (`Content-Length: 0`) is what this game's content-delivery client actually tolerates gracefully for checks it doesn't strictly need - not a `404`.** Reverted the catcher's default back to `200 OK`. If a real file exists under `tools/served_content/` for the requested path, it's still served with real content/length; only the *fallback* (unknown path) behavior changed. Do not default back to 404 without deliberately re-testing - it's a live regression, not a theory.

## RPCS3's DNS-hook cannot redirect a literal IP address

Tried adding `50.18.104.153=192.168.1.100` to `IP swap list`, to redirect the dead fallback-server connection found in `net1.bin` (see `research/notes/net1bin-server-list.md`) to our own machine. **Confirmed via RPCS3 log this does not work**: `sys_net: [Native] Attempting to connect on 50.18.104.153:7320` still shows the real (dead) IP, unchanged.

**Why:** RPCS3's `dnshook` (`Emu/NP/np_dnshook.cpp`, see `docs/capture-howto.md`) only intercepts actual DNS *query packets* the guest sends over an emulated UDP socket - `analyze_dns_packet()` parses real DNS protocol bytes. The game reads `"50.18.104.153"` as a literal string out of `net1.bin` and converts it directly to a binary address in its own code (no hostname, no DNS query ever gets sent for a string that's already a dotted-decimal IP) - there's nothing for the DNS-hook to see or match against. **The `IP swap list` mechanism only works for hostnames that actually go through DNS resolution; it cannot intercept a connection built from a literal IP string.**

**Implication for the `net1.bin` hex-patch idea** (still not done): patching the local decrypted `net1.bin` file to replace the IP string itself (not adding a swap-list entry) remains the only viable way to redirect this specific connection, since the DNS-hook approach is a structural dead end for it. This raises the priority of that approach if reaching this connection is wanted.
