# Live Capture How-To

Target: public RPCN service, captured with Wireshark on the Windows host running RPCS3 (decided over WSL/localhost-relay alternatives - simplest, sees everything in one standard pcap).

## Steps

1. Open Wireshark on Windows (as Administrator if Npcap requires it for your setup).
2. Pick the network interface that carries your real internet traffic (the adapter your normal WiFi/Ethernet connection uses) - not a loopback/virtual adapter, since RPCS3 talks to the public RPCN service over the real network.
3. Start capturing with **no filter** - traffic volume for a short test session is small; filtering by port ahead of time risks missing the actual (unknown in advance) ports the game uses. Filter afterward in the Wireshark GUI instead.
4. Launch RPCS3, start The Last of Us, get into Factions online: sign in via RPCN, go to matchmaking, create/join a room, play briefly if you can get into an actual match, then back out to the menu.
5. Stop the capture.
6. **File -> Save As**, save directly into this repo so it's immediately available here too: `F:\ClaudeHole\tlou_factions\captures\<date>_<short-description>.pcapng` (see `captures/README.md` for the naming convention). Windows and WSL share this drive, so no transfer step is needed - it shows up at `/mnt/f/ClaudeHole/tlou_factions/captures/...` right away.

## What happens next

Once a `.pcapng` lands in `captures/`, analysis uses `tshark` (installed) and/or Python `scapy` (`tools/.venv/`, gitignored - recreate with `python3 -m venv tools/.venv && tools/.venv/bin/pip install scapy` if missing) to pull apart the UDP/TCP streams - starting with whatever's *not* already-understood generic RPCN/`sceNpMatching2` traffic: the room-data blobs, the P2P `NetEvent` stream, and any connection attempts to a possible custom Naughty Dog backend (see `research/notes/clan-tus-commerce-findings.md` and `captures/README.md` for what to look for).

## Superseded/complemented by: self-hosted RPCN + RPCS3's own DNS hook (session 3+)

Pure pcap capture against the public RPCN service turned out to be a poor primary method - see `research/notes/rpcn-connection-instability.md` and the empty-capture writeup in `research/notes/2026-08-13-capture1-and-nd-hostnames.md`. Current approach instead:

1. **Self-hosted RPCN fork** (`backend/rpcn/`, `Verbosity=Trace` in `rpcn.cfg`) gives full server-side protocol visibility for anything that goes through RPCN itself - no packet capture needed for that traffic at all. Point RPCS3 at it via `config/rpcn.yml`'s `Host` field (see `backend/README.md`).
2. **RPCS3's own DNS-hook / "IP swap list"** (`Emu/NP/np_dnshook.cpp` in RPCS3's source) redirects specific hostnames the *game itself* resolves (not RPCN traffic) to an IP of our choosing - this is how we catch the game's non-RPCN backend calls (e.g. the Naughty Dog "Content Delivery" server, `research/notes/dynamic-hostname-construction.md`). Set per-game in `config/custom_configs/config_<TITLEID>.yml`, `Net: IP swap list:`. **Syntax, confirmed from source** (not GUI-documented, verify against source if RPCS3 updates change this):
   - Entries are `hostname=ip`, joined by `&&` for multiple: `host1=127.0.0.1&&host2=127.0.0.1`.
   - The hostname side is a **regex** matched with `std::regex_match` (whole-string match) against the raw DNS-query hostname - `.` becomes a literal dot, `*` becomes `.*`. **Never include a URL scheme** (`http://`) - the actual DNS query is just the bare hostname, so a scheme prefix makes the match silently fail (this was a real bug hit and fixed in session 3 - the failure looked identical to a genuinely dead host, a ~20s TCP timeout, which is why it wasn't obvious).
   - A wildcard like `*naughtydog.com=127.0.0.1` catches every subdomain *and* the bare domain in one entry - prefer this over enumerating every known hostname individually.
3. **`tools/catch_http.py <port> <logfile>`** - a minimal raw-socket listener for observing what a redirected hostname actually sends once the DNS hook points it at us. Not a real HTTP server, just logs the raw request and replies with a generic 200 so the client's request cycle completes. Run it, then watch its log file (`Monitor`/`tail -f`) while retrying the connection in RPCS3.
