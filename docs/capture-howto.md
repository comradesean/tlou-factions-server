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

## 3. Targeted capture matrix for the remaining undefined fields

A handful of session-manager fields cannot be named from static analysis alone,
because the EBOOT never branches on them (their meaning lived in the retail
server) and the existing `server/logs/session_manager.log` is all solo-host.
Each is resolvable by a short, controlled hosting session while tailing
`server/logs/session_manager.log` (every received message is dumped as raw hex
with a parsed summary). Vary ONE condition at a time.

| # | Field | Message / offset | Capture procedure | Names it because |
|---|---|---|---|---|
| 4 | Party-vs-solo deltas | any session-manager message | Repeat a given action solo, then in a 2-player party; diff. | Isolates any field that only appears with a party. |
| 5 | Map ids | `member_data.recent_level` (card offset 10, two u16) | Play a KNOWN map and read slot 0 of the next card. Do NOT get booted in between - the boot-to-menu path clears the ring. | Slot 0 is the map just entered. |

RESOLVED - rows 1-3 were answered on 2026-08-18/19 and are kept here only as a
record of what the procedures were for:

- **`field_0c`** is the PLAYLIST ID (mode + party rules; nine of them on 01.11,
  two on 01.00, renumbered between builds). Resolved not by the 2x2 capture this
  table proposed but by walking every lobby style in 01.11 and reading the value
  off both the `0x135` search and the `0x12f` stamp. Full table in
  `protos/0x12f_room_create.ksy`.
- **`0x140` `attr_value`** is NOT a field - it is sender-side residue, the low
  half of a stale pointer in the reused send buffer. No capture will name it.
  See `research/notes/2026-08-18-wire-residue-and-field-corrections.md`.
- **Game mode** is not a separate wire field; it is folded into the playlist id
  above.

Known map ids (01.11): `0x1f` Checkpoint, `0x31` Lakeside. 01.00's observed ids
(`0x0e`-`0x17`) are unnamed, and it is not yet established whether map ids are
stable across builds - one match on a known map on 01.00 would settle it.

Practical notes:
- Tail the log live: `tail -f server/logs/session_manager.log`; each entry prints
  the 16-byte (or longer) hex dump plus a `parsed opcode=0x...` summary line.
- The stub already decodes RoomCreate `0x0c` as `map_id=` and `0x140` as
  `flags=` in its summary lines, so the varying value is visible without manual
  hex reading.
- `0x140` only fires once a room survives long enough to load toward a match
  (needs the RPCS3 "Stub PPU Traps" workaround and the min-players client patch);
  see `research/notes/2026-08-17-min-players-client-patch.md`.
