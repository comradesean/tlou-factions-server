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
