# Observing Protocol Traffic

There are two complementary ways to see what the game sends and receives:

1. **Server-side logging** — the primary method. Because the project now runs
   the whole backend locally (`server/`), most traffic can be read directly from
   the servers that receive it, with no packet capture at all.
2. **Packet capture** — a fallback for traffic that does *not* terminate at our
   servers: the direct P2P `NetEvent` gameplay stream between clients, and any
   connection attempts to hosts we haven't redirected yet.

## 1. Server-side logging (primary)

Anything that goes through our own servers is logged where it arrives:

- **The custom backend** (`server/`, started with `docker compose up` or
  `./run.sh`) logs to `server/logs/`. The HTTP gateway, ticket/session/location/
  voice servers each record the requests and payloads they handle — this covers
  the `0x11` ticket-server family, the `NetMatchmaking*`/session-manager family,
  S3 content delivery, and the Facebook Graph flow.
- **RPCN** — the PSN reimplementation layer — is run self-hosted with
  `Verbosity=Trace`, which prints every `CommandType`/`NotificationType` packet
  it processes. Point RPCS3 at the local instance via its RPCN host setting.
  This gives full visibility into the fourth protocol family (see
  `docs/protocol/rpcn_psn_commands.md`) without capturing anything.

## 2. RPCS3 DNS-hook / "IP swap list"

To make the *game's own* backend calls (not RPCN traffic) arrive at our servers,
RPCS3's DNS hook (`Emu/NP/np_dnshook.cpp` in RPCS3's source) redirects specific
hostnames the game resolves to an IP of our choosing. This is how the game's
non-RPCN backend calls are caught and served (e.g. the Naughty Dog "Content
Delivery" server, `research/notes/dynamic-hostname-construction.md`). Set it
per-game in RPCS3's Network settings, `IP swap list`.

**Syntax, confirmed from source** (not GUI-documented; verify against source if
an RPCS3 update changes this):

- Entries are `hostname=ip`, joined by `&&` for multiple:
  `host1=127.0.0.1&&host2=127.0.0.1`.
- The hostname side is a **regex** matched with `std::regex_match` (whole-string
  match) against the raw DNS-query hostname — `.` becomes a literal dot, `*`
  becomes `.*`. **Never include a URL scheme** (`http://`) — the actual DNS query
  is just the bare hostname, so a scheme prefix makes the match silently fail
  (this was a real bug: the failure looked identical to a genuinely dead host, a
  ~20s TCP timeout, which is why it wasn't obvious).
- A wildcard like `*naughtydog.com=127.0.0.1` catches every subdomain *and* the
  bare domain in one entry — prefer this over enumerating every known hostname
  individually.

Once a hostname is redirected to us, `server/http_gateway.py` receives and logs
the raw request (and serves the real content back from `server/data/served_content/`),
so there is no separate raw-socket catcher to run.

## 3. Packet capture with Wireshark (fallback)

Use this for traffic that never reaches our servers — chiefly the direct P2P
`NetEvent` stream between two clients, and reconnaissance of unknown hosts/ports
before a DNS redirect exists for them.

1. Open Wireshark on the Windows host running RPCS3 (as Administrator if Npcap
   requires it).
2. Pick the network interface that carries real internet traffic (the adapter
   your normal WiFi/Ethernet uses) — not a loopback/virtual adapter.
3. Start capturing with **no filter** — traffic volume for a short test session
   is small, and filtering by port ahead of time risks missing the actual
   (unknown in advance) ports the game uses. Filter afterward in the GUI.
4. Launch RPCS3, get into Factions online, exercise the flow you're studying
   (matchmaking, room create/join, an actual match if reachable), then back out.
5. Stop the capture and **File → Save As** a `.pcapng` to any local path. Pcaps
   are gitignored (`*.pcapng`) — keep them local; they are not committed.

Analysis uses `tshark` and/or Python `scapy` (in a local venv at
`research/tools/.venv/`, gitignored — recreate with
`python3 -m venv research/tools/.venv && research/tools/.venv/bin/pip install scapy`)
to pull apart the UDP/TCP streams, starting with whatever is *not* already-
understood generic RPCN/`sceNpMatching2` traffic: the room-data blobs, the P2P
`NetEvent` stream, and connections to a possible custom Naughty Dog backend (see
`research/notes/clan-tus-commerce-findings.md`).

### A note on capturing against the public RPCN service

Pure pcap capture against the *public* RPCN service turned out to be a poor
primary method — the connection was unstable (`research/notes/rpcn-connection-instability.md`)
and early attempts produced empty captures
(`research/notes/2026-08-13-capture1-and-nd-hostnames.md`). Self-hosting the
backend (methods 1 and 2 above) replaced it.
