#!/usr/bin/env python3
"""Stateful Session Manager stub for TLOU Factions' NetInit handshake (port 7314).

Implements the first exchange reversed via Ghidra decompilation - see
protos/netmatchmaking_client_hello.ksy, protos/netmatchmaking_server_hello.ksy,
and docs/protocol/session_manager_and_matchmaking.md for the full evidence
trail. This is a genuinely NEW connection g_pSessionManager::Init()
(FUN_00ad71a0) opens right after the ticket-server handshake completes - it
was failing because nothing listened on port 7314 at all (connect() silently
failing, then the client blindly using the dead socket - EBADF errors).

KNOWN UNCERTAINTY: both the client hello's opcode field and the required
server hello opcode (0x12e) pass through an unresolved byte-swap helper
(FUN_00a0e324 / FUN_00ad55d8) before use - the on-wire byte order is NOT
confirmed to be big-endian despite this project's usual convention. This
stub logs the raw client hello in both byte orders so the real convention
can be read directly off a live capture before trusting the server hello
response's byte order.
"""
import socket
import signal
import sys
import datetime
import threading
import struct
import os
import time
import json

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7314
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))
from rotating_log import RotatingLog
_LOGS = os.path.join(_HERE, "logs")
os.makedirs(_LOGS, exist_ok=True)

# Cap on concurrent handler threads, gating accept() rather than just the
# thread start: an unaccepted connection holds no file descriptor of ours and
# waits in the kernel's listen backlog instead, so a flood of idle connections
# cannot exhaust this process's fd limit (and, through run_all's die-together
# supervision, take the whole backend down). Same pattern and reasoning as
# http_gateway.py's MAX_CONCURRENT_HANDLERS. These are long-lived control
# connections - one per player for the whole session, with a 600 s idle
# timeout - so the cap is set generously above any realistic player count
# rather than at http_gateway's request-scoped 64.
MAX_CONCURRENT_HANDLERS = int(os.environ.get("TLOU_SESSION_MAX_HANDLERS", "128"))
_handler_slots = threading.Semaphore(MAX_CONCURRENT_HANDLERS)
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "session_manager.log")

# --- Raw wire tap (2026-08-18) --------------------------------------------
# A complete, machine-parseable record of EVERY packet in BOTH directions,
# separate from the human-readable session_manager.log. One JSON object per
# line: {"t": iso8601, "dir": "in"|"out", "conn": <int>, "hex": "<fullhex>"}.
# The client->server ("in") side is the one that matters for discovery - it is
# where the retail client might put meaning in a field we call padding. The
# stream may fragment/coalesce across recv() calls; the verifier reassembles
# per-connection per-direction and re-frames by opcode, so this just records
# raw recv/sendall events faithfully. Consumed by research/tools/verify_wire.py.
WIRE_PATH = os.path.join(_LOGS, "wire.jsonl")
_wire_lock = threading.Lock()
_wire_fp = RotatingLog(WIRE_PATH)
_conn_seq = 0
_conn_seq_lock = threading.Lock()


def _next_cid():
    global _conn_seq
    with _conn_seq_lock:
        _conn_seq += 1
        return _conn_seq


def _wire(cid, direction, data):
    if not data:
        return
    line = json.dumps(
        {"t": datetime.datetime.now().isoformat(), "dir": direction,
         "conn": cid, "hex": data.hex()},
        separators=(",", ":"))
    with _wire_lock:
        _wire_fp.write(line + "\n")


class _TapSock:
    """Transparent socket proxy: mirrors every recv/sendall to wire.jsonl.

    Wrapping the accepted socket once (in main) means every existing
    conn.recv / conn.sendall - including cross-connection sends via the room
    registry, which store this wrapped object - is tapped with no other code
    change. All other socket methods (settimeout, close, getpeername, ...) are
    transparently proxied.
    """

    def __init__(self, sock, cid):
        self._s = sock
        self._cid = cid

    def recv(self, n, *a, **k):
        data = self._s.recv(n, *a, **k)
        _wire(self._cid, "in", data)
        return data

    def sendall(self, data, *a, **k):
        _wire(self._cid, "out", data)
        return self._s.sendall(data, *a, **k)

    def send(self, data, *a, **k):
        _wire(self._cid, "out", data)
        return self._s.send(data, *a, **k)

    def __getattr__(self, name):
        return getattr(self._s, name)
# --------------------------------------------------------------------------

CLIENT_HELLO_OPCODE = 0x12d
SERVER_HELLO_OPCODE = 0x12e
ROOM_CREATE_OPCODE = 0x12f
MEMBER_OPCODE = 0x131
ROOM_JOINED_OPCODE = 0x132
HOST_FLAG_UPDATED_OPCODE = 0x13f
# The opcode/size table (docs/protocol/session_manager_and_matchmaking.md)
# labels 0x135 "NetMatchmakingRoomLeft", 24 bytes - but the same doc already
# flags that naive "0x12d + table index" naming as unconfirmed/wrong for
# tail entries (ClientHello2, Ping). Live capture 2026-08-15 of two real
# clients both sitting in "Find Match" shows each of them broadcasting this
# opcode unprompted every ~5s (same cadence as Ping), 36 bytes not 24,
# payload containing a locale field ("us"), a repeated 0x03e8 pair, and a
# small mode-shaped field - that's shaped like periodic search-criteria
# advertisement, not a one-off "I left a room" event. Treating it as the
# find-match heartbeat/broadcast until proven otherwise.
FIND_MATCH_OPCODE = 0x135
ROOM_SEARCH_OPCODE = 0x136  # server->client game LIST (reply to the 0x135 search)
# RESOLVED 2026-08-15 (see research/notes/2026-08-15-room-teardown-and-flag-
# chain.md and protos/0x133_room_leaving.ksy for the full decompiled trace):
# despite the declared table calling this NetMatchmakingMemberJoined, it is
# NOT a join event - full decompile of the sending function
# (_opd_FUN_00ad65e8) proves it fires when the client gives up on and
# abandons a room it's tracking: it zeroes its own local room-id copy right
# after sending this, then walks every member slot through the exact same
# per-member removal path the confirmed 0x134 (RoomLeave) case uses.
# Fire-and-forget - not one of the 11 opcodes the client's own receive-
# dispatch has a case for, and a same-opcode echo reply tried live had zero
# effect either way (expected, now that the real semantics are known) - left
# unhandled/log-only rather than echoed.
ROOM_LEAVING_OPCODE = 0x133
# NetMatchmakingRoomSearchInfo (declared 56 bytes, actual 16) - client sends
# this unprompted after Member/RoomJoined. Live capture 2026-08-15 of a real
# 2-player pairing: payload's tail 8 bytes exactly match the room_id we
# assigned via Member. 0x138 (NetMatchmakingRoomSearchResult) IS one of the
# 11 opcodes the client's own receive-dispatch already handles
# (sessmgr_vtable_dump.txt) - its handler searches a 4-slot local array by an
# 8-byte key at wire offset 8, matching this room_id shape. A room_id-echo
# reply was tried live and had zero effect on the "Searching for Optimal
# Game"/"Starting Game" hang - ROOM_LEAVING_OPCODE above (the client
# abandoning the room on its own, for a still-unknown reason) is the more
# likely actual cause of that hang, not a missing reply to this opcode.
ROOM_SEARCH_INFO_OPCODE = 0x137
ROOM_SEARCH_RESULT_OPCODE = 0x138
# CORRECTED 2026-08-17 (live PPU breakpoint + disasm): 0x137/0x138 are NOT
# search info/result - they are the party KICK mechanism, and 0x13c is PROMOTE:
#   0x137 Kickout   C->S "kick member X"   {u16 target@+4; u16 requester@+6; u64 room_id@+8}
#   0x138 Kickedout S->C recipient leaves the room named at wire+8 (handler @0x00ad7f28)
#   0x13c Promote   C->S "make member X party leader" {u16 target@+4; u64 room_id@+8}
KICKOUT_OPCODE = 0x137
KICKEDOUT_OPCODE = 0x138
PROMOTE_OPCODE = 0x13c
# SetRoomFlags (0x140) / UpdatedRoomFlags (0x141) - protos/0x140_set_room_
# flags.ksy, protos/0x141_updated_room_flags.ksy. The declared-table names
# for this pair are NetMatchmakingSetAttrFlags / NetMatchmakingUpdatedAttr
# Flags; the constants below were renamed off those on 2026-08-20 to match
# the protos.
# Live-captured 2026-08-15 for the first time - only
# reachable once a room survives long enough to actually load into a match
# (see research/notes/2026-08-15-room-teardown-and-flag-chain.md and the
# "Stub PPU Traps" RPCS3 workaround that finally got a client this far).
# 0x140 arrived as 16 bytes: opcode(4) + a 4-byte flags value + echoed
# room_id(8) - e.g. `00 01 2f 78` as the flags. 0x141 IS one of the 11
# opcodes the client's own receive-dispatch (FUN_00ad7604) already has a
# case for (unlike 0x140, 0x142, 0x143) - a classic "client sets X, server
# confirms updated X" pair. Untested: echoing the flags value straight back
# as 0x141, matching the room_id-echo pattern already proven for 0x137/
# 0x138.
SET_ROOM_FLAGS_OPCODE = 0x140
UPDATED_ROOM_FLAGS_OPCODE = 0x141
# SetRoomDataBlock (0x143) / RoomDataBlockUpdated (0x144) - protos/0x143_set_
# room_data_block.ksy, protos/0x144_room_data_block_updated.ksy. NAMES
# CORRECTED 2026-08-20: these constants were previously UPDATED_ROOM_FLAGS_
# OPCODE and HOST_RANK_OPCODE, both from the pre-2026-08-17 declared-table
# reading. HostRank is 0x142, NOT 0x144, so that old constant name collided
# with a genuinely different opcode. 0x143 is client->server despite its
# declared name (see docs/protocol/session_manager_and_matchmaking.md row
# 22): 144 bytes, opcode + room_id(8) + a 128-byte verbatim copy of the
# client's own room_obj+0x18 region. Never handled by this stub before
# 2026-08-16 - confirmed via live Ghidra dispatch-case decompile that its
# counterpart 0x144 (server->client, same 128 bytes written back into that
# same room_obj+0x18 region on receipt) is a message the real server would
# have sent and ours never has. Following this project's established "echo
# the client's own data back" pattern (Kickedout/0x138 echoing Kickout/
# 0x137, UpdatedRoomFlags/0x141 echoing SetRoomFlags/0x140) -
# EXPERIMENTAL, not yet live-tested. See
# research/notes/2026-08-16-net-sm-server-lobby-dispatch.md and follow-ups.
SET_ROOM_DATA_BLOCK_OPCODE = 0x143
ROOM_DATA_BLOCK_UPDATED_OPCODE = 0x144
PING_OPCODE = 0x145
CLIENT_HELLO2_OPCODE = 0x146
# NetMatchmakingKickedout (declared, 16 bytes) - confirmed WRONG both name
# and size, same "declared table lies" pattern as 0x133. Named "CreateParty"
# after first appearing right as the in-game "invite to party" action was
# used - but CORRECTED 2026-08-15 (later same day): a live-breakpoint trace
# of its actual sender (_opd_FUN_00ad6148, called from 0x003B17CC/
# 0x003B17E0) proved it fires on a periodic/UI-transition tick completely
# independent of party or room state - hits repeatedly from the main menu,
# through EULA acceptance, and every menu "continue" click, with the
# caller's own register context containing a literal Google Analytics
# beacon URL string ("GET /__utm.gif?..."). This is periodic telemetry, not
# party creation - the original invite correlation was timing coincidence.
# See research/notes/2026-08-15-createparty-trace.md for the full trace and
# correction. Real name/purpose still unknown; kept as a fire-and-forget
# log-only opcode (matches live evidence: not one of the client's own
# receive-dispatch cases, no reply behavior ever demonstrated to matter).
CREATE_PARTY_OPCODE = 0x13a

# Live-observed room-slot heap address (PS3 retail builds have no ASLR).
# Seen identically across 3 separate RPCS3 debugger breakpoints this session
# (once at FUN_00ad5ab0's r4, twice at the 0x00ad7b14 id-gate's r27) across
# multiple independent "back to menu, host again" attempts within the same
# RPCS3 process - not a guess, a repeated live observation. See
# docs/protocol/0x131_member.md "The room_ptr hazard" - if this is wrong the
# client dereferences it through an unchecked vtable call and will very
# likely crash the emulator outright (acceptable risk here - just restart
# RPCS3 and re-confirm via a fresh breakpoint if this value ever goes stale,
# e.g. after a full RPCS3 restart rather than just leaving/rejoining the
# multiplayer menu).
ROOM_PTR = 0x01383bd8
# The two statically-allocated room objects in this build (confirmed static
# globals, 2026-08-16/17): 0x01383bd8 = the GAME/session room, 0x01387f58 = the
# PARTY room. The refresher is only needed for a solo GAME host (keeping
# room_obj+0x10 alive before a match loads); re-broadcasting Member to the
# PARTY lobby churns party membership and spams "You were kicked from the party"
# on the host (10s cadence == the refresher interval). Never refresh the party
# room. See research/notes/2026-08-17-join-party-presence-discovery.md.
GAME_ROOM_PTR = 0x01383bd8
PARTY_ROOM_PTR = 0x01387f58

# ---------------------------------------------------------------------------
# MULTI-BUILD SUPPORT (2026-08-19). The client sends its OWN room-object pointer
# in 0x12f/0x130 wire offset 8, and those objects are statically allocated
# globals whose addresses differ PER GAME BUILD. Two behavioural decisions key
# on "is this the party object?" - the unique-party-id mint (the Join Party fix)
# and the solo-keepalive skip - so a build we do not know about silently loses
# both, resurfacing the Join Party host-lookup collision and the party
# re-broadcast churn with no error.
#
# Live-captured pairs. NOTE the inter-object delta CHANGED between builds
# (0x4380 -> 0x4490), so a new build's party pointer CANNOT be extrapolated from
# its game pointer - it has to be observed. 01.11's was captured from a real
# "Invite to Party" accept (2026-08-19 00:35:58) after the 01.00-only code let
# that join collide and bounce.
#
#   build   game object   party object
#   01.00   0x01383bd8    0x01387f58
#   01.11   0x013babd8    0x013bf068
#
# To add a build: create a game room and a party on it, read room_ptr off the
# wire (0x12f offset 8) for each, and add the pair. The canary in the 0x12f
# handler prints exactly what to add when it sees an unknown pointer.
# ---------------------------------------------------------------------------
CLIENT_BUILDS = {
    0x01383bd8: ("01.00", 0x01387f58),
    0x013babd8: ("01.11", 0x013bf068),
}
# field_0c is the PLAYLIST ID - a one-byte index into the playlist table that
# ships in netN.bin, bundling game mode WITH party rules. The binary asserts
# `(playlist & 0xFFFFFF00) == 0`. Numbering is PER BUILD, because the table is
# per-build DC data:
#
#   01.11                Parties Allowed   No Parties   DLC
#     Supply Raid                1              2         3
#     Survivors                  6              7         8
#   01.00  had only two playlists, one per mode: 2 and 3.
#          So id 3 = Survivors on 01.00 but Supply Raid/DLC on 01.11 - which is
#          why cross-build matchmaking has to be segregated by build.
#
# Ids 4 and 5 are unclaimed and sit exactly where a third mode's block would go
# (Interrogation is the obvious candidate); add them once observed.
# PER-BUILD playlist tables. The ids live in netN.bin, so the SAME number means
# different things on different builds - 3 is Survivors on 01.00 but
# Supply Raid/DLC on 01.11. Matchmaking is segregated by build (see
# CLIENT_BUILDS), so the two never mix; these tables exist so logs name the
# right playlist and so an id is only accepted as a playlist for a build that
# actually has it.
PLAYLIST_NAMES_BY_BUILD = {
    "01.00": {
        # 01.00 shipped one playlist per mode - no style variants.
        2: "Supply Raid",
        3: "Survivors",
    },
    "01.11": {
        1: "Supply Raid / Parties Allowed",
        2: "Supply Raid / No Parties",
        3: "Supply Raid / DLC",
        6: "Survivors / Parties Allowed",
        7: "Survivors / No Parties",
        8: "Survivors / DLC",
        11: "Interrogation / Parties Allowed",
        12: "Interrogation / No Parties",
        13: "Interrogation / DLC",
    },
}
# Union, used when the build is not yet known (the id alone is still a strong
# signal that a create is a matchmaking host rather than a private lobby).
MATCHMAKING_PLAYLISTS = set().union(*(set(t) for t in PLAYLIST_NAMES_BY_BUILD.values()))


def playlist_name(playlist, build=None):
    """Human-readable playlist name for logs, resolved for the client's build."""
    if build and build in PLAYLIST_NAMES_BY_BUILD:
        name = PLAYLIST_NAMES_BY_BUILD[build].get(playlist)
        if name:
            return f"{name} [{build}]"
        return f"unknown playlist for {build}"
    hits = {b: t[playlist] for b, t in PLAYLIST_NAMES_BY_BUILD.items() if playlist in t}
    if not hits:
        return "unknown playlist"
    if len(hits) == 1:
        b, n = next(iter(hits.items()))
        return f"{n} [{b}]"
    return "; ".join(f"{n} [{b}]" for b, n in sorted(hits.items()))

# Playlist ids used by lobbies that must NEVER be advertised in the find-match
# list, whatever the client was doing beforehand:
#   88 (0x58) party room (on the party object)
#   90 (0x5a) PRIVATE match - Interrogation (01:18:20)
#   99 (0x63) PRIVATE match - Supply Raid (00:55:23) and Survivors (01:01:29)
# The private value therefore varies by mode, though not in an obvious pattern
# (two modes share 99 while Interrogation uses 90). Unnamed on purpose - what
# matters here is only that none of them are ever advertised.
# This is checked FIRST because the search flag can still be set from a
# just-abandoned find-match queue; without it a private game created moments
# after searching inherits that flag and gets advertised to searchers. The
# equivalent bug was live-observed for the PARTY object at 01:00:50.
NON_MATCHMAKING_PLAYLISTS = {0x58, 0x5a, 0x63}

GAME_ROOM_PTRS = set(CLIENT_BUILDS)
PARTY_ROOM_PTRS = {party for _ver, party in CLIENT_BUILDS.values()}
KNOWN_ROOM_PTRS = GAME_ROOM_PTRS | PARTY_ROOM_PTRS


def is_party_ptr(room_ptr):
    """True if this is the PARTY room object of any known build."""
    return room_ptr in PARTY_ROOM_PTRS


def build_of(room_ptr):
    """Game-version label for a room pointer, or None if the build is unknown."""
    if room_ptr in CLIENT_BUILDS:
        return CLIENT_BUILDS[room_ptr][0]
    for ver, party in CLIENT_BUILDS.values():
        if room_ptr == party:
            return ver
    return None

# Cross-connection room registry (2026-08-16, party-join support). Every
# room a connection creates via RoomCreate is registered here so that a
# LATER 0x130 RoomJoin from a DIFFERENT connection can find it. Live
# evidence for 0x130 (party-invite accept flow, first capture 2026-08-16):
# 88 bytes; offset 8 = the JOINER's own local room-object pointer (the
# party room object 0x1387f58 - both clients share the same two static
# room globals, 0x1383bd8 game / 0x1387f58 party); offset 0x10:0x18 = the
# 8-byte room_id being joined (learned from the invite's tag-267 payload
# {be64 room_id; u8 flag} on the NP message bus); ffffffff party-data
# sentinel at 0x22. Ignoring 0x130 is what made "Joining Party" time out
# to "Unable to join party" while the invite itself delivered fine.
# Keyed by id(conn); each value keeps everything needed to push an updated
# roster to the host connection when someone joins. Guarded by rooms_lock.
rooms_lock = threading.Lock()
# KEYED BY (conn_key, room_id) since 2026-08-18 - it used to be keyed by
# conn_key alone, which meant a connection could own only ONE room. A client
# is routinely in TWO rooms at once (its party room 0x01387f58 AND its game
# room 0x01383bd8), so creating the game room OVERWROTE the party entry and
# the party ceased to exist server-side while the client was still in it.
# Live proof (2026-08-18 21:44-21:57): comradesean created a game room at
# 21:44:58, and mgnomad2's party join at 21:57:13 was answered "NO matching
# room found on another connection, no reply sent" - while the party host was
# still connected and still posting party data, which the stub then dropped as
# "sender not in any registered room". Both clients ended up restarting.
active_rooms = {}


def rooms_owned_by(conn_key):
    """Every room this connection is the OWNER of. Caller holds rooms_lock."""
    return [info for (ck, _rid), info in active_rooms.items() if ck == conn_key]


def room_keys_owned_by(conn_key):
    """Registry keys for every room this connection owns. Caller holds lock."""
    return [k for k in active_rooms if k[0] == conn_key]

# Per-member data blob cache (2026-08-17). Each client pushes its own 32-byte
# member blob via 0x13a (SetPartyData) - the blob carries the values the
# lobby UI reads for a REMOTE player: title/rank stats and the 4 loadout ids
# (getter FUN_00ad2650 hands member_slot+0xFC to the UI only if its length is
# exactly 32). We cache the latest per (room_id, member_id) so we can both
# relay live updates (0x13b) AND seed it into the Member roster for anyone
# who joins later (0x131 entry offset 39=len, 40..=blob). Guarded by
# rooms_lock. See research/notes/2026-08-17-member-data-blob-rank-and-0x142-
# hostrank.md.
member_blobs = {}   # (room_id_bytes, member_id) -> bytes (exactly 32)

# ---------------------------------------------------------------------------
# PER-CONNECTION INBOUND LIVENESS (2026-08-19)
# ---------------------------------------------------------------------------
# Monotonic timestamp of the last byte received from each session-manager
# connection, keyed by id(conn). Every client keeps this control connection
# busy: it sends a 0x145 keepalive ping every 30 s (PING_OPCODE, see the
# opcode table), plus 0x13a party-data pushes and whatever the UI generates.
# So "no inbound traffic for well over 30 s" is independent evidence that a
# connection is dead or hung, which is the confirmation the late-0x137
# dead-peer rule requires before it will remove anyone. Guarded by rooms_lock
# (the same lock the roster uses, so a removal decision reads one consistent
# snapshot). Entries are dropped when the connection closes.
last_inbound_ts = {}   # id(conn) -> time.monotonic()

# Gates for acting on a LATE 0x137 requester=0 (automatic dead-peer removal).
# See protos/0x137_kickout.ksy: requester=0 frames arrive in two regimes -
# 0.01-0.17 s after a RoomJoin (a join-flow artifact that must NEVER be acted
# on; acting on it is the bug that broke "Join Party"), and 29.7-642.6 s after
# any join (a host's P2P layer reporting an unreachable peer). 5 s sits ~30x
# above the largest observed join-flow delay (0.17 s) and ~6x below the
# earliest observed late frame (29.7 s), so neither regime can be mistaken for
# the other.
LATE_KICKOUT_MIN_SECONDS = 5.0
# A member must have been silent for this long before a late requester=0 frame
# is allowed to remove it. The client's own keepalive interval is 30 s
# (0x145), so this is 2.5 missed pings - comfortably past jitter, still fast
# enough to clear a zombie before the roster matters again.
DEAD_PEER_SILENCE_SECONDS = 75.0

# ---------------------------------------------------------------------------
# THE BLOB IS ALSO UPLOADED INSIDE RoomCreate AND RoomJoin (2026-08-17)
# ---------------------------------------------------------------------------
# 0x13a only ever fires when FUN_003b15bc rebuilds the blob while the room
# already has a room id: its sender FUN_00ad6148 writes the local mirror
# (memcpy(room+0x19FC, data, len); room+0x19F8 = len @0x00ad61d4/0x00ad61e4)
# and then, at 0x00ad6240, does `ld r9,16(r29)` / `beq -> return 0` - i.e. if
# room_obj+0x10 (the room id) is still 0 it silently sends NOTHING and leaves
# no deferred-retry marker. On the find-match path the blob is built before the
# matchmade room exists, so NO 0x13a is ever sent (live-confirmed: an exhaustive
# opcode tally over the whole 2026-08-17 find-match session found 0x13a x0).
#
# The client hands the server that same 32-byte blob a different way on that
# path: it embeds it in the two messages that CREATE its membership.
#
#   0x12f RoomCreate  (buffer base r1+144, FUN_00ad5b78)
#       0x00ad5d10  lwz r11,6648(r31)   ; r31 = room obj -> room+0x19F8 = LENGTH
#       0x00ad5d18  stb r11,182(r1)     ; -> wire offset 0x26
#       0x00ad5d20  addi r11,r1,312     ; -> wire offset 0xa8
#       0x00ad5d30  lbzu r7,6652(r9)    ; source = room+0x19FC, copied byte-wise
#
#   0x130 RoomJoin    (buffer base r1+112, FUN_00ad6718)
#       0x00ad67a0  lwz r9,6648(r28)    ; room+0x19F8 = LENGTH
#       0x00ad67ac  stb r9,124(r1)      ; -> wire offset 0x0c
#       0x00ad67a8  addi r11,r1,136     ; -> wire offset 0x18
#       0x00ad67c0  lbzu r0,6652(r9)    ; source = room+0x19FC, copied byte-wise
#
# Live confirmation (session_manager_stub-run.log, 2026-08-17 01:55:25):
#   0x12f: wire[0x26] = 0x20, wire[0xa8:0xc8] =
#          00*8 | 00 00 ff ff ff ff 00 00 | 00*8 | 56 7c 00 00 00 00 00 00
#   0x130: wire[0x0c] = 0x20, wire[0x18:0x38] = same shape, tail 56 9c ...
# blob[10..13] = ff ff ff ff (unset loadout) and blob[22..] = uninitialised
# stack exactly as FUN_003b15bc's layout predicts.
#
# So the server harvests each player's blob from its own 0x12f/0x130 and
# redistributes it: Member (0x131) entry[39]=len / entry[40..] seeds it into a
# member record at registration time, and 0x13b updates one that is already
# registered (FUN_00ad33d8 de-dupes by NpId and returns early, so Member can
# only ever SEED). Both are needed - see the harvest sites below.
ROOM_CREATE_BLOB_LEN_OFF = 0x26
ROOM_CREATE_BLOB_OFF = 0xa8
ROOM_JOIN_BLOB_LEN_OFF = 0x0c
ROOM_JOIN_BLOB_OFF = 0x18


def extract_member_blob(chunk, len_off, blob_off):
    """Pull a client's own per-member data blob out of a 0x12f/0x130 frame.

    Returns bytes or None. FUN_00ad33d8 asserts len <= 64 (net-session.cpp:218)
    and the UI getter FUN_00ad2650 hands the blob to the lobby ONLY when the
    length is exactly 32 (`cmpwi cr7,r0,32` @ 0x00ad2734), so anything else is
    worth logging but useless to relay.
    """
    if len(chunk) <= len_off:
        return None
    blob_len = chunk[len_off]
    if not (0 < blob_len <= 64) or len(chunk) < blob_off + blob_len:
        return None
    return bytes(chunk[blob_off:blob_off + blob_len])

# Stub-synthesized PUBLIC room ids. RoomCreate's own wire offset 4:12 is
# `00000000 01383bd8` on EVERY client (offset 4:8 is uninitialised stack,
# offset 8:12 is the statically-allocated game-room object) - so two hosts
# collide exactly. For find-match/public rooms we mint our own id instead:
# high word = a monotonic sequence tagged 0x5-, low word = the client's own
# room_ptr (keeps it nonzero and recognisable). The client stores whatever we
# put in Member's wire 16:24 into room_obj+0x10 and echoes it back to us in
# 0x133 / 0x137 / 0x140 / 0x13a (live-confirmed), and the P2P reserve reply
# carries it to the joiner, so the joiner's 0x130 names this same value.
_public_room_lock = threading.Lock()
_public_room_seq = [0]


def synth_public_room_id(room_ptr):
    """Mint a globally-unique 8-byte room id for a public (find-match) room."""
    with _public_room_lock:
        _public_room_seq[0] += 1
        seq = _public_room_seq[0]
    return struct.pack(">II", 0x50000000 | (seq & 0x0fffffff), room_ptr & 0xffffffff)


def synth_private_room_id(room_ptr):
    """Mint a globally-unique 8-byte room id for a room that is neither a party
    object nor a find-match host - i.e. a party-started or private match on the
    client's GAME room object (2026-08-19).

    ROOT CAUSE this addresses: this was the one create path with no mint. It
    fell through to `chunk[4:12]`, whose top word is RoomCreate wire offset 4:8
    - documented in protos/0x12f_room_create.ksy as NEVER WRITTEN by the sender,
    i.e. uninitialised client stack. The old comment claimed the value "only
    needs to be nonzero and session-consistent"; stack residue guarantees
    neither. Live 2026-08-19: comradesean's client sent pad_4=012a426c (room
    012a426c013babd8) while mgnomad2's sent pad_4=00000000 on the same build -
    so the same code path yields a unique id on one machine and the byte-
    identical-across-clients id 00000000<room_ptr> on the other. That collision
    is exactly the failure synth_party_room_id and synth_public_room_id were
    written to fix; this path simply was never covered.

    Distinct high-word tag (0x70000000) from the public (0x5) and party (0x6)
    mints so the three are told apart in logs; shares the same sequence/lock so
    uniqueness is global across all pools. Low word keeps the room_ptr so the
    value stays nonzero (the client asserts m_roomId != 0,
    net-event-player.cpp:560).
    """
    with _public_room_lock:
        _public_room_seq[0] += 1
        seq = _public_room_seq[0]
    return struct.pack(">II", 0x70000000 | (seq & 0x0fffffff), room_ptr & 0xffffffff)


def synth_party_room_id(room_ptr):
    """Mint a globally-unique 8-byte room id for a PARTY room (invite / direct
    Join Party), 2026-08-17.

    ROOT CAUSE this addresses: every party reuses the one static room-object
    pointer 0x01387f58, so its historical room_id (chunk[4:12] == 000000000
    1387f58) is byte-identical on ALL clients. The RoomJoin (0x130) host lookup
    then can only match on that shared id and has to guess "the most recent
    entry" among colliding parties - a stale entry from a just-abandoned or
    racing party (the failing direct-join lands 100-200ms after the target
    improvises its party) routes the join to the wrong/dead connection and the
    session collapses.

    Why a mint here propagates end-to-end (triple-verified in EBOOT.elf):
      - The client stores the 0x131 roster's wire[16:24] into room_obj+0x10
        (std @0x00ad780c).
      - The party state machine fills its NP 268 join-reply from that same
        m_roomId (room_obj+0x10) the instant its create completes, so the
        joiner learns the MINTED id over NP immediately - no presence-throttle
        dependency on the critical path.
      - Presence (sceNpBasicSetPresenceDetails path @0x00397d74) also re-reads
        *(room_obj+0x10) every tick while advertising, so the minted id reaches
        the friends list on the secondary channel too.

    Distinct high-word tag (0x60000000) from the public mint so the two are
    told apart in logs; shares the same sequence/lock so uniqueness is global
    across both pools. Low word keeps the room_ptr so the value stays nonzero
    (the client asserts m_roomId != 0, net-event-player.cpp:560).
    """
    with _public_room_lock:
        _public_room_seq[0] += 1
        seq = _public_room_seq[0]
    return struct.pack(">II", 0x60000000 | (seq & 0x0fffffff), room_ptr & 0xffffffff)


def build_room_joined(npid, name, room_id, id_gate=0, map_id=b"\x00\x00\x00\x00"):
    """Build a guessed NetMatchmakingRoomJoined (opcode 0x132) reply to a
    captured NetMatchmakingRoomCreate (opcode 0x12f).

    Field layout below is from decompiling FUN_00ad7604 (SessionManager's
    receive-dispatch loop, vtable+0x4 at base 0x01243b38), the `iVar8 == 0x132`
    case - see research/ghidra/sessmgr_vtable_dump.txt and
    docs/protocol/session_manager_and_matchmaking.md for the full trace.
    Wire offsets are relative to the message start (buffer base param_1+0x24058
    in the decompile, where the leading 4-byte opcode itself lives at +0).

    CONFIRMED mechanically (not guessed):
    - Total consumed size is 0x78 = 120 bytes, not the 160 bytes the opcode/
      size debug-log table claims - the dispatch code's own buffer-advance
      amount (`param_1 + 0x24054 = ... - 0x78`) is authoritative and
      contradicts the declared table size. Same class of correction as
      ClientHello2 (0x148->0x146) and Ping (0x147->0x145) found earlier this
      session - the size/opcode debug table is not reliable past the initial
      handshake opcodes.
    - Offset 8 (8 bytes) MUST match the corresponding room's 8-byte id field
      at `*(longlong*)(room_slot+0x10)` or the client's search for a matching
      pending room slot fails (comparison at 0x00ad7b14: `ld r0,0x10(r27)` /
      `cmpd cr7,r0,r3`). CONFIRMED LIVE via an RPCS3 debugger breakpoint at
      that exact instruction (2026-08-14): `r0` (the room slot's own stored
      id) was **0x0** for both of the client's populated room slots, while
      `r3` (our echoed id, loaded from this reply's own wire offset 8) was
      the nonzero value echoed from RoomCreate - CR7 EQ=0, confirmed
      mismatch. The client's local slot id is simply never set to anything
      nonzero (at least not before this point in the flow) - echoing
      RoomCreate's id back was the wrong approach entirely. Sending zero
      here instead is what the live memory state actually calls for.

    UNCONFIRMED / best-effort:
    - Offset 4:8 (4 bytes): referenced by other dispatch cases (e.g. 0x13b) as
      a generic u16 "room index"-shaped field but not read anywhere in this
      specific 0x132 case in the traced decompile - previously left zero.
      "map_id" LABEL NOW DISPUTED (2026-08-16) - see
      research/notes/2026-08-16-map-id-vs-team-confound.md. Originally
      labeled 2026-08-15 from 5 RoomCreate captures where this field read
      0x9 for repeated Checkpoint selections and 0x13 for repeated Lakeside
      selections - concluded "map identifier". NOT reconciled: a controlled
      test the following night held map AND mode constant (Checkpoint,
      Supply Raid, confirmed by the user) while only changing team, and got
      the SAME two values (0x13 for Red x2, 0x9 for Blue) now correlating
      with team instead. Both can't be literally true of the same field.
      The original 5-capture raw data was never saved to a dedicated note
      (only summarized here), so it can't be rechecked for whether team was
      itself uncontrolled in that original test (plausible: solo-hosting
      may default to one team unless manually switched, which would explain
      how "changed only by map" and "changed only by team" both looked true
      in their own limited samples). Not renaming the field or changing the
      stub's behavior over this - it's echoed straight back either way, so
      there's no known code-correctness question here, only a
      documentation/understanding one. Whatever this field actually
      encodes, treat the "Checkpoint loads as an empty skybox" explanation
      as unresolved again, not settled.
    - Offset 16:32 (first 16 bytes of the "18x u16 attribute" block): traced
      this pass to the likely root cause of the post-RoomJoined RPCS3 crash
      ("SIG: ... Unexpected error in reply to RequestSignalingInfos:
      Malformed", RPCN-side "Command Some(RequestSignalingInfos) was
      malformed!"). `_opd_FUN_00ad33d8` (member-slot registration, called
      right after this reply is processed) copies its `param_2+4:+0x28`
      (36 bytes) into a new member record, and *dedupes members by comparing
      `param_2+4` via `_opd_FUN_00e459bc`* - the same compare helper used
      elsewhere in the binary specifically for 16-byte SceNpId handles (e.g.
      in `FUN_00add510`'s local-vs-remote npid check). That strongly suggests
      `param_2+4:+0x14` (16 bytes) is this new member's NpId handle. Tracing
      the caller (`FUN_00ad7604`'s 0x132 case) shows `param_2` is built from
      this reply's own wire offset 0x24068 onward, i.e. wire offset 16 here -
      so wire offset 16:32 is hypothesized to need this room's member's
      SceNpId (== our own online ID for a solo/self-hosted room, "comradesean"
      null-padded to 16 bytes) rather than zero. Sending zero there produces
      an empty NpId, which downstream becomes the blank `%s` observed live in
      both `"NpId  connId 1"` and `"Activate Connection  4660 1"` (both
      %s slots empty) right before the crash - consistent circumstantial
      evidence, but NOT confirmed via a live debugger read of `param_2` at
      the `_opd_FUN_00ad33d8` call site itself. If this doesn't fix the
      crash, breakpoint at 0x00ad33d8 and inspect 16 bytes at (r4+4) (PPC64
      ABI: r4 = param_2) to see what's actually landing there.
    - Offset 32:52 (remaining 20 bytes of the attribute block): still
      unconfirmed - likely team/rank/slot-shaped member metadata (the rest of
      `_opd_FUN_00ad33d8`'s 36-byte copy, `param_2+0x14:+0x28`) - left zero.
    - Offset 52:56 (u16 + 2 flag bytes): same - left zero.
    - Offset 56:120 (64 bytes): a trailing buffer the client treats as a
      pointer/string region (`local_e4 = param_1+0x24090`) - filled here with
      the same "npid.timestamp" session-name string the client itself sent in
      RoomCreate (wire offset 0x28 there), on the theory that echoing the
      room's own name back is safe and plausibly expected; not confirmed this
      is actually a name field vs. something else.

    Only RoomJoined is sent here, not a follow-up Member (0x131) roster
    broadcast - RoomJoined's own handler already builds and registers a
    member-shaped local struct (`_opd_FUN_00ad33d8`), which reads as
    self-sufficient for "you are now in this room" without a separate
    Member message, but this is unconfirmed against live behavior.

    Takes explicit npid/name/room_id rather than parsing a raw RoomCreate
    blob directly, so the same builder can serve both the solo-host RoomCreate
    path and the cross-connection find-match pairing path (2026-08-15) - the
    latter has no RoomCreate message to parse at all, since neither paired
    client ever explicitly created a room the other could echo fields from.
    """
    body = bytearray(120)
    struct.pack_into(">I", body, 0, ROOM_JOINED_OPCODE)
    body[4:8] = map_id[:4]
    # offset 8:16 (id_gate) - zero by default, live-confirmed against the
    # client's own room-slot memory rather than echoed from RoomCreate (see
    # docstring). MUST stay zero for the solo-host RoomCreate path (matches
    # the client's pre-existing pending room slot's own id, or the client's
    # search at 0x00ad7b14 never finds it and the whole flow stalls). For the
    # find-match pairing path, a matching id-gate makes RoomJoined's own
    # handler independently call the SAME member-registration function
    # Member's handler uses (0x132 case's id-gate search, sessmgr_vtable_dump
    # .txt) - and since that internal call always embeds the RECIPIENT'S OWN
    # npid (needed to avoid the earlier malformed-npid bug), it triggers a
    # self-signaling attempt (`SCE_NP_SIGNALING_ERROR_OWN_NP_ID`, live-
    # confirmed 2026-08-15) that Member's own (already-sufficient) processing
    # doesn't need. Passing a non-matching id_gate here makes that search
    # fail to find a slot, skipping the internal call entirely.
    struct.pack_into(">Q", body, 8, id_gate)
    body[16:16 + len(npid[:16])] = npid[:16]
    name_field = name[:63]
    body[56:56 + len(name_field)] = name_field
    return bytes(body)


MEMBER_ID = 1
JOINER_MEMBER_ID = 2

# Retail lobby ceiling: 8 players in every game mode, for the party staging
# room (0x01387f58) and the game room (0x01383bd8) alike - they are the same
# room object type on the wire and carry the same capacity field, RoomCreate
# offset 0x24, live-constant 8 in both cases.
RETAIL_MAX_PLAYERS = 8


def clamp_max_players(value):
    """Bound a wire-supplied room capacity to 1..RETAIL_MAX_PLAYERS.

    The capacity arrives verbatim from RoomCreate offset 0x24 and is both
    advertised to clients (Member wire offset 24 -> room_obj+0x1f8, where a
    zero trips a compiled-in assert) and used as the join gate. A malformed or
    hostile value therefore either crashes a client or creates a room the
    server admits an unbounded number of members into, so it is clamped on
    ingestion rather than trusted.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        return RETAIL_MAX_PLAYERS
    if value <= 0:
        return RETAIL_MAX_PLAYERS
    return min(value, RETAIL_MAX_PLAYERS)


def build_member(members, room_id, max_players, owner_ref_id, local_ref_id, team=None,
                 room_ptr=ROOM_PTR, populate_self_npid=False, blobs=None):
    """Build a NetMatchmakingMember (opcode 0x131) room-roster broadcast.

    Field layout from docs/protocol/0x131_member.md / protos/0x131_member.ksy
    (decompiled this session from FUN_00ad7604's `iVar8 == 0x131` case plus
    _opd_FUN_00ad6e34's byte-swap helper - see research/ghidra/member_decomp.txt
    and dispatch_raw2.txt for the raw evidence).

    This is what actually tells the client "you are both a member of this
    room AND its owner" - RoomJoined alone registers a member but always
    calls _opd_FUN_00ad33d8 with local/owner flag params hardcoded to 0,0 in
    the compiled dispatch code, so a RoomJoined-only flow leaves the client
    not knowing which member is itself or who owns the room. Member's header
    carries two reference ids (owner_ref_id, local_ref_id) that get
    XOR-compared against each roster entry's own member_id to set those
    flags per-entry - sending a single entry whose id matches both refs
    marks that one entry (the solo host) as both local and owner.

    Header (160 bytes / 0xa0), high confidence except where noted:
      0   4   opcode = 0x131
      4   4   unknown, swapped but unread - zero
      8   4   room_ptr - THE HAZARD FIELD. Dereferenced through an unchecked
              vtable call client-side with no null check. Must be the live
              address of the client's own room-slot object - see ROOM_PTR
              above for how this value was obtained.
      12  2   owner_ref_id
      14  2   local_ref_id
      16  8   overwrites room_obj+0x10 - the SAME id field RoomJoined's
              create_id gate (0x00ad7b14) checks against, but at a DIFFERENT
              point in time. RoomJoined's own wire offset 8 (the gate-compare
              value) must be zero to match the client's pre-existing local
              slot state (live-confirmed via the debugger). This field
              overwrites that same room_obj+0x10 AFTER the gate already
              passed - live-confirmed (2026-08-14) that leaving it zero here
              too causes a later named assertion failure once the client
              proceeds toward loading the match:
              `*** ASSERTION: m_roomId != 0 *** game/net/net-event/
              net-event-player.cpp:560`. Fixed by sending RoomCreate's own
              8-byte transaction id here instead - a real, nonzero room
              identity is expected once past the initial gate.
      24  2   capacity - CONFIRMED via a live crash (2026-08-14): _opd_FUN_00ad33d8
              (member registration, called from this message's own handler)
              contains `if (room_obj+0x1f8 == 0) { trapWord(0x1f,...); }` -
              an explicit compiled-in assert that this field is never zero.
              Sending zero here hit that trap and crashed RPCS3 outright
              (PPU Trap at 0x00ad38b8, live-confirmed). Sourced from
              RoomCreate's own wire offset 0x24 (2 bytes, live-constant
              `00 08` = 8) - the room's own declared max-player count is
              the obvious source of truth for a "capacity" field - and
              clamped to 1..RETAIL_MAX_PLAYERS on ingestion, since the same
              number is also the RoomJoin admission gate. CORRECTED
              2026-08-16: this used to read offset 0x1e, which RoomCreate's
              sender never writes (uninitialised stack, masked by an
              `or 10` fallback); see protos/0x12f_room_create.ksy's pad_1e
              and clamp_max_players above.
      26  2   roster_count
      28  2   unknown, swapped but unread - zero
      30  130 unread by the traced code - zero

    Per-entry (104 bytes / 0x68) x roster_count:
      0   16  FIXED 2026-08-15: live-confirmed via a real 2-real-player find-
              match pairing crash. Previously left zero along with the rest
              of the 36-byte attribute block below - inert for a solo host
              (nobody to open real NP signaling to), but with a genuine
              second npid in the roster, RPCN's own log showed the client
              sending it a malformed `RequestSignalingInfos` for the SAME
              npid-shaped-empty-string reason as the original RoomJoined bug
              (`research/notes/2026-08-14-signaling-crash-npid-trace.md`) -
              `sceNpSignalingGetConnectionFromNpId`/`ActivateConnection`
              needs a real per-member NpId that isn't the offset-40 trailing
              buffer this code always filled. Filled with this entry's own
              npid, mirroring RoomJoined's offset 16:32 fix - EXCEPT for
              whichever entry is the recipient's own (member_id ==
              local_ref_id): live-confirmed 2026-08-15 that populating a
              recipient's own entry here makes the client call
              sceNpSignalingGetConnectionFromNpId on itself, which Sony's API
              rejects outright (`SCE_NP_SIGNALING_ERROR_OWN_NP_ID`,
              0x8002a816) and which cascades into the same room-size/capacity
              trap. Left zero for the recipient's own entry, filled for every
              other (remote) entry.
      16  20  remainder of the 18x u16 "attributes" block - not independently
              mapped - zero. TRIED AND FALSIFIED (2026-08-16): a Ghidra dig
              for why solo-host permanently stalls in client state
              NET_SM_SERVER_LOBBY found its handler blocks popping an item
              off a bounded producer/consumer queue, with a translation
              helper (_opd_FUN_001953f8) that walks per-member-slot pointers
              checking fields at +0xc/+0x10 - a plausible per-member ready/
              team-assigned-flag shape, which lined up with this exact
              unmapped region. Live-tested team=0 (u16 @ entry offset 16) +
              ready=1 (u16 @ offset 18): confirmed present correctly on the
              wire (verified via captures/tcp_catch.log hex dump), but did
              NOT change observed behavior - the same 3-attempt pattern
              recurred with this field populated (id-gate fail -> brief
              match then silent drop -> permanent NET_SM_SERVER_LOBBY
              stall). Reverted to zero. The real blocker is more likely
              the `team >= 0 && team < NetInfo::kMaxNetTeams` assertion
              (game/net/net-game-manager.cpp:1358) firing during the 2nd
              attempt's match load - see research/notes/2026-08-16-net-sm-
              server-lobby-dispatch.md and follow-up notes for the current
              theory (that assert's abnormal-exit path is suspected of
              wedging whatever the 3rd attempt's queue depends on, medium-
              low confidence, not proven).

              TRYING AGAIN 2026-08-16 (later same night) with a real value
              instead of a guess: `RoomCreate`'s own wire offset 0xb0:0xb2 is
              now CONFIRMED (not guessed) to be the client's team selection -
              0=unset/spectator, 1=Blue, 2=Red - via ~24 live captures
              spanning every map and both teams with zero exceptions (see
              research/notes/2026-08-16-team-selection-field-confirmed.md).
              The earlier team=0 experiment failed to change anything, but
              it was ALWAYS zero regardless of what the player actually
              selected - indistinguishable from "spectator" every time, so
              it never actually tested "does echoing the real team value
              help." Writing the real captured value into entry offset 16
              (u16) now, offset 18 left zero (the earlier ready=1 guess is
              not re-added - no evidence for it, keep this experiment to one
              variable). EXPERIMENTAL - not yet live-tested.
      36  2   member_id - XOR-compared against owner_ref_id/local_ref_id
      38  1   unread - zero
      39  1   unread, flags-shaped - zero
      40  64  unread by the traced loop - by parallel with RoomJoined's own
              trailing region, likely a name/NpId buffer - filled with the
              room-creator's npid (same source as RoomJoined's own npid
              field) on the same "probably safe to echo" theory.

    `members` is a list of (member_id, npid_bytes) tuples, in roster order -
    same roster content goes to every recipient, only owner_ref_id/
    local_ref_id differ per-recipient (each recipient needs to see itself
    correctly flagged as local, but only the actual room owner's member_id
    is ever "owner" for anyone).
    """
    header = bytearray(160)
    struct.pack_into(">I", header, 0, MEMBER_OPCODE)
    # 2026-08-16 dispatch audit: RoomCreate wire offset 8 IS this pointer,
    # sent by the client itself (FUN_00ad5b78 writes its own room-object
    # address there) - so the solo-host path now echoes the sender's real
    # value instead of the debugger-recovered hardcode. The hardcoded default
    # remains for paths with no RoomCreate to parse it from (find-match).
    # See research/notes/2026-08-16-sessmgr-dispatch-audit-and-unsent-opcodes.md 4b.
    struct.pack_into(">I", header, 8, room_ptr)
    struct.pack_into(">H", header, 12, owner_ref_id)
    struct.pack_into(">H", header, 14, local_ref_id)
    header[16:24] = room_id
    struct.pack_into(">H", header, 24, max_players)  # capacity - must be nonzero, see docstring
    struct.pack_into(">H", header, 26, len(members))

    entries = bytearray()
    for member_id, npid in members:
        entry = bytearray(104)
        # Only tell the recipient to open NP signaling toward OTHER members -
        # live-confirmed 2026-08-15 via RPCS3's own log:
        # "'sceNpSignalingGetConnectionFromNpId' failed with 0x8002a816 :
        # SCE_NP_SIGNALING_ERROR_OWN_NP_ID" - Sony's API explicitly rejects
        # opening signaling to yourself. The previous fix populated this
        # attribute-block npid for every entry uniformly, including each
        # recipient's own local entry, which made the client try to signal
        # itself and crash. member_id == local_ref_id identifies "this
        # recipient's own entry" - skip it there.
        # 2026-08-16 UPDATE (live boot test + dispatch audit): zeroing the
        # self entry's NpId here made the client register its LOCAL member
        # with a blank identity - live TTY shows "Removing User '' failed"
        # and ' joined match' with an empty name, and downstream
        # find-player-by-npid lookups (team assignment feeding the
        # net-game-manager.cpp:1358 assert) come up empty. The audit shows
        # the OWN_NP_ID self-signaling this skip was added for actually came
        # from ROOMJOINED's registration (is_local hardcoded 0 - the
        # signaling resolve at 0xad34a4 only fires for is_local==0 slots),
        # not from Member's self entry (is_local=1, never signals). So on
        # paths that no longer send RoomJoined (solo-host), the real NpId is
        # restored via populate_self_npid=True. Find-match still sends
        # RoomJoined and keeps the old skip until it gets the same treatment.
        if member_id != local_ref_id or populate_self_npid:
            npid_16 = npid[:16]
            entry[0:len(npid_16)] = npid_16
        if team is not None:
            struct.pack_into(">H", entry, 16, team)
        struct.pack_into(">H", entry, 36, member_id)
        # CORRECTED 2026-08-17 (member-blob rank note): entry[39] is the
        # per-member DATA-BLOB length and entry[40:] is the blob - the Member
        # dispatch (0xad79b8/0xad79c8 -> FUN_00ad33d8) memcpys entry[40:40+len]
        # into member_slot+0xFC, which the rank/loadout UI getter FUN_00ad2650
        # returns ONLY if the length is exactly 32. It was never a name buffer
        # (the member's display name comes from the NpId at entry[0:16]).
        # Seeding the blob here makes a late-joiner see incumbents' ranks
        # immediately; live 0x13a->0x13b relays keep it current after.
        blob = (blobs or {}).get(member_id)
        if blob:
            entry[39] = len(blob) & 0xff
            entry[40:40 + len(blob)] = blob[:64]
        entries += entry

    return bytes(header) + bytes(entries)


def build_owner_member(room_id, owner_member_id=MEMBER_ID):
    """Build a NetMatchmakingOwnerMemberChanged (opcode 0x13d), 16 bytes.

    Dispatch audit 8.2 (2026-08-16): writes the u16 at wire offset 4 into
    room_obj+0x19f0 (the owner's member id) and then fires
    room->vtable[0x34]() - a client-side ownership-notification callback
    that Member does NOT fire (Member only sets +0x19f0 silently via the
    is_owner flag). First sent 2026-08-16 chasing the "Host Migrate Room"
    + "Host quit for cheating" match teardown seen ~3.5s into the first
    real 2-player party match.
    """
    body = bytearray(16)
    struct.pack_into(">I", body, 0, 0x13d)
    struct.pack_into(">H", body, 4, owner_member_id)
    body[8:16] = room_id
    return bytes(body)


def build_room_search(search_obj_ptr, entries):
    """Build a 0x136 RoomSearch reply - the server->client PUBLIC GAME LIST that
    NET_SM_CLIENT_GAME_LIST_WAIT is blocked on (research/notes/2026-08-17-find-
    match-flow.md). This is what find-match actually needs: the stub previously
    answered the 0x135 search with a party-style Member, the wrong layer, so the
    client parked forever.

    Header (16 bytes): opcode(4) | 0(4) | search_obj_ptr(4) | num_entries(4).
    The search_obj_ptr MUST echo the searcher's own object pointer from its
    0x135 wire offset 8 (0x01383bd8 live) - the 0x136 handler dereferences and
    writes through it. Then num_entries x 56-byte entries: room_id at [0:8]
    (the join key the client feeds into its subsequent 0x130 RoomJoin), two u16
    counts at [0xc]/[0x10] (current players / capacity - semantics unconfirmed),
    and a 36-byte attribute block at [0x14:0x38] (map/mode/name - byte layout
    unconfirmed, sent zero for the first cut per the note's recommendation).
    An empty list (num_entries=0, 16 bytes) is valid and lets a lone searcher
    fall through to hosting a public game itself.
    """
    header = bytearray(16)
    struct.pack_into(">I", header, 0, ROOM_SEARCH_OPCODE)
    struct.pack_into(">I", header, 8, search_obj_ptr & 0xffffffff)
    struct.pack_into(">I", header, 12, len(entries))
    body = bytearray()
    for room_id, info in entries:
        e = bytearray(56)
        e[0:8] = room_id
        struct.pack_into(">H", e, 0xc, len(info.get("members", [])) or 1)
        struct.pack_into(">H", e, 0x10, info.get("max_players", 8))
        # HOST IDENTITY (2026-08-17, find-match-flow.md Q3): the joiner's
        # CONNECT_TO_HOST handler (_opd_FUN_003b2a9c) copies this entry's
        # attribute block [0x14:0x38] and starts a P2P SIGNALING connect to the
        # host peer using the NpId carried here - NOT a 0x130 to us (the 0x130
        # already happened at GAME_LIST_PICK). With this left zero the joiner
        # resolves no peer and CONNECT_TO_HOST times out (~30s) -> force-leave.
        # entry[0x14:0x24] = the host's 16-byte NpId (best concrete guess).
        host_npid = info.get("npid", b"")[:16]
        e[0x14:0x14 + len(host_npid)] = host_npid
        body += bytes(e)
    return bytes(header) + bytes(body)


def build_room_leave(room_id, member_id):
    """Build a 0x134 RoomLeave (24 bytes) - "member X left the room".

    Dispatch audit 7 (2026-08-16): +8 room id (lookup), +16 member_id (u16,
    lhz @ 0xad7cc8) -> FUN_00ad0d4c member lookup -> FUN_00ad3190 removal.
    Audit 8.4 called it "the correct way to tell a client that another
    member left". First needed live 2026-08-16: a joiner leaving gave the
    HOST "You were kicked from the game/party" spammed at exactly the
    Member-refresher cadence - the stale joint roster kept re-adding the
    departed member every 10s and the client's party logic kicked on the
    conflict each time.
    """
    body = bytearray(24)
    struct.pack_into(">I", body, 0, 0x134)
    body[8:16] = room_id
    struct.pack_into(">H", body, 16, member_id)
    return bytes(body)


def build_room_closed(room_id):
    """Build a 0x139 RoomClosed (16 bytes) - "this room no longer exists".

    NEW 2026-08-18. Never sent before this date, which is exactly the bug:
    when the room OWNER left (0x133 or a dead socket) the stub deleted the
    room from its registry and told the remaining members NOTHING - no
    0x134, no 0x139. A survivor was left holding a room object the server
    had forgotten, with no keepalive (start_member_refresher skips
    multi-member rooms) and no surviving peer to maintain it, which is the
    documented road to room_obj+0x10 going zero and code that assumes a
    valid room id trapping (research/notes/2026-08-15-room-teardown-and-
    flag-chain.md, _opd_FUN_0040b210).

    Layout per protos/0x139_room_closed.ksy: opcode, 4 pad bytes, room_id.
    """
    body = bytearray(16)
    struct.pack_into(">I", body, 0, 0x139)
    body[8:16] = room_id
    return bytes(body)


def close_room_and_notify(entry, reason, exclude_key=None, notify_timeout=None):
    """Retire a room and TELL ITS SURVIVING MEMBERS, instead of silently
    dropping it. Caller must NOT hold rooms_lock.

    Sends, to every member except `exclude_key` (the departing connection):
      0x134 RoomLeave(owner_member_id)  - the owner is gone from the roster
      0x139 RoomClosed(room_id)         - and the room itself is finished
    then stops the refresher and purges the room's cached member blobs.

    notify_timeout: override each recipient socket's send timeout for just
    this notification (seconds). Left None for the live disconnect/Kickout
    paths, which keep the connection's normal 600s operational timeout - a
    live peer that's merely slow to ACK shouldn't have its notification cut
    short. Set to a small number by drain_rooms_for_shutdown: that path runs
    synchronously inside the SIGTERM/SIGINT handler on the main thread, and a
    stale/dead connection (this project has no client reconnect - see
    project_no_client_reconnect memory) would otherwise block sendall() for
    the full 600s PER dead connection, making the process visibly "refuse to
    die" until kill -9 (observed in production 2026-08-20).
    """
    room_id = entry["room_id"]
    leave = build_room_leave(room_id, MEMBER_ID)
    closed = build_room_closed(room_id)
    told = 0
    for key, (mid, mconn, memit) in list(entry.get("conns", {}).items()):
        if key == exclude_key:
            continue
        # NEVER send a member its OWN departure. 0x134's handler runs the
        # member lookup + removal path (FUN_00ad0d4c -> FUN_00ad3190), so
        # RoomLeave(member_id=N) delivered to member N tells that client it
        # left, and it acts on itself. That self-referential shape is the same
        # bug class as the 0x138 self-kick that broke Join Party and the 0x13d
        # re-announce that broke join-in-progress. The owner still gets 0x139,
        # which is the message that actually means "this room is finished".
        # Matters on the shutdown drain, where nobody is the departing party
        # and the owner IS one of the recipients.
        msg = closed if mid == MEMBER_ID else leave + closed
        try:
            if notify_timeout is not None:
                mconn.settimeout(notify_timeout)
            mconn.sendall(msg)
            memit(f"   [close] room {room_id.hex()} closed ({reason}) - sent "
                  + ("RoomClosed(0x139)" if mid == MEMBER_ID
                     else "RoomLeave(owner)+RoomClosed(0x139)")
                  + f" to member {mid}")
            told += 1
        except OSError as e:
            memit(f"   [close] could not notify member {mid} ({e})")
    if told == 0:
        # Log the no-survivor case too, so "the close path never ran" and "it
        # ran and had nobody to tell" are distinguishable in the log.
        entry["emit"](f"   [close] room {room_id.hex()} closed ({reason}) - "
                      f"no surviving members to notify")
    entry["stop_event"].set()
    with rooms_lock:
        for kk in [k for k in member_blobs if k[0] == room_id]:
            member_blobs.pop(kk, None)
    return told


def build_kickedout(room_id):
    """Build a 0x138 Kickedout (16 bytes) telling ONE recipient to leave a room.

    VERIFIED 2026-08-17: the client's dispatcher arm @0x00ad7f28 reads the
    8-byte room id at wire+8, finds the local room slot whose +0x10 matches,
    and calls that session's RequestLeave (-> m_leaveRequested=1 -> LeaveRoom).
    So this MUST be sent ONLY to the member being kicked - sending it to the
    room owner is the self-kick bug that collapsed every party.
    """
    body = bytearray(16)
    struct.pack_into(">I", body, 0, KICKEDOUT_OPCODE)
    body[8:16] = room_id
    return bytes(body)


def reseed_departed_party(conn, emit, npid, room_ptr, max_players):
    """Re-establish a solo PARTY room for a member that just left someone
    else's party, so its party object gets a fresh nonzero room id.

    ROOT CAUSE this addresses (rejoin-party bug, 2026-08-20). The client's
    own LeaveRoom sender (_opd_FUN_00ad65e8, the 0x133 builder) ends with:

        ad665c  ld   r9,16(r31)      ; room_id = *(room_obj+0x10)
        ad6664  cmpdi r9,0           ; nothing to leave -> just flag it
        ad667c  li   r0,1
        ad6680  li   r3,307          ; 0x133
        ad6684  stb  r0,184(r31)     ; *(room_obj+0xb8) = 1   (stays VALID)
        ...     build+send the 16-byte 0x133
        ad66e0  std  r0,16(r31)      ; *(room_obj+0x10) = 0   (id CLEARED)
        ad66e4  bl   0xad32c4        ; wipe all 12 member slots

    So a leaver is left holding a party object that still claims to be valid
    (+0xb8 == 1) but whose room id is zero, and NOTHING on the client puts an
    id back: `*(room_obj+0x10)` is written in exactly one place, the 0x131
    Member receive arm (`ld r9,16(r28)` / `std r9,16(r29)` @0x00ad7804-
    0x00ad780c), which takes its room object straight from the message's own
    wire offset 8 and is not gated on +0xb8. Only the server can restore it.

    Why that kills the next Join Party. The party-join/invite state machine
    (0x00354ee0, state 6) reads the LOCAL party object 0x01387f58 - resolved
    from this CU's anchor slot 0x01267eb4 - and refuses to proceed unless
    both fields are good:

        354f40  lwz  r9,-32620(r30)  ; r9 = 0x01387f58 (party room object)
        354f44  lbz  r0,184(r9)      ; *(party+0xb8)
        354f48  beq  -> 0x354f6c     ; invalid -> wait, then give up
        354f50  ld   r0,16(r9)       ; *(party+0x10)
        354f54  cmpdi r0,0
        354f58  beq  -> 0x354f6c     ; ZERO -> wait, then give up
        354f5c  bl   0x00354c2c      ; build the "Join" payload and send it

    0x00354c2c is the payload builder: it resolves the target friend through
    NetFriends::FindByNpId (0x003985dc) and packs `*(party+0x10)` at offset
    0x10 of the message. The 0x354f6c arm just re-checks until 3000 ms have
    passed and then aborts. The same field is what presence advertises -
    the 96-byte presence blob built at 0x00397d74 stores
    `*(0x01387f58+0x10)` at blob offset 0x28 (`ld r9,16(r9)` @0x00397e0c,
    `std r9,160(r1)` @0x00397e14) - so a leaver publishes room id 0 too.

    The fix is the same job start_member_refresher does for a solo GAME host
    ("keep room_obj+0x10 nonzero"), applied ONCE to the party object at the
    moment the client zeroes it. This is not a re-assertion into an
    established room - the client has just torn this room down itself - so it
    is not the 0x138/0x13d bug class; the bytes are identical in shape to the
    live-proven RoomCreate reply (Member + 0x13f + 0x13d, solo roster).
    """
    room_id = synth_party_room_id(room_ptr)
    member = build_member([(MEMBER_ID, npid)], room_id, max_players,
                          owner_ref_id=MEMBER_ID, local_ref_id=MEMBER_ID,
                          room_ptr=room_ptr, populate_self_npid=True)
    # joined_flag=0: a party host must advertise room_obj+0x19f4 == 0 or no
    # friend's client will draw "Join Party" on its row. See
    # build_owner_changed.
    msg = (member + build_owner_changed(room_id, joined_flag=0)
           + build_owner_member(room_id, MEMBER_ID))
    try:
        conn.sendall(msg)
    except OSError as e:
        emit(f"   [reseed] party re-seed for {npid!r} failed ({e}) - the "
             f"connection is gone, nothing to restore")
        return
    with rooms_lock:
        # A connection can only ever be in ONE party, and it just left the
        # previous one, so retire any other room it owns on the SAME party
        # object. Rooms on its GAME object are untouched (a client in a party
        # while hosting a game is normal - see active_rooms).
        for k in room_keys_owned_by(id(conn)):
            stale = active_rooms[k]
            if stale["room_id"] != room_id and is_party_ptr(stale.get("room_ptr", 0)):
                stale["stop_event"].set()
                del active_rooms[k]
                emit(f"   [reseed] retired this connection's previous party "
                     f"entry {stale['room_id'].hex()}")
        active_rooms[(id(conn), room_id)] = {
            "npid": npid, "conn": conn, "emit": emit,
            "room_id": room_id, "room_ptr": room_ptr,
            "max_players": max_players,
            "stop_event": threading.Event(),
            "conns": {id(conn): (MEMBER_ID, conn, emit)},
            "members": [(MEMBER_ID, npid)],
            # Authoritative party/room leader. See the other room-registration
            # site for why this is tracked.
            "owner_member_id": MEMBER_ID,
            "last_join_ts": time.monotonic(),
            "next_member_id": JOINER_MEMBER_ID,
            "room_ptrs": {MEMBER_ID: room_ptr},
            "public": False,
            "mode": None,
            "build": build_of(room_ptr),
        }
    emit(f"   [reseed] {npid!r} left a party - minted a fresh solo party "
         f"room_id {room_id.hex()} and sent Member+HostFlagUpdated+OwnerMember "
         f"({len(msg)} bytes, room_ptr={room_ptr:#010x}) so its party object "
         f"stops holding the zero its own 0x133 sender wrote to +0x10")


def broadcast_member_departure(departing_key, room_id=None, reseed_party=False):
    """A joined connection left (0x133 or socket close): remove it from any
    room it was a member of, tell the remaining members via 0x134, and
    restart the room owner's refresher with the shrunken roster so the
    departed member stops being re-registered every interval.

    reseed_party: the departure came from a LIVE connection's own 0x133 (not
    a dead socket), so the leaver is still there to be talked to. When the
    room it left was a party, give it a fresh solo party room id - see
    reseed_departed_party for the full mechanism. Never set on the socket-
    close path: that connection cannot receive anything."""
    affected = []
    reseed = []
    with rooms_lock:
        for other in active_rooms.values():
            if departing_key in other.get("conns", {}) and (
                    room_id is None or other["room_id"] == room_id):
                mid, dep_conn, dep_emit = other["conns"].pop(departing_key)
                if id(other["conn"]) == departing_key:
                    continue  # room owner leaving - entry teardown handles it
                dep_npid = next((n for m, n in other.get("members", [])
                                 if m == mid), b"")
                other["members"] = [m for m in other.get("members", [])
                                    if m[0] != mid]
                # Drop the departed member's cached blob so it is not replayed
                # to a future joiner of this (shared-id) room.
                member_blobs.pop((other["room_id"], mid), None)
                affected.append((other, mid))
                if reseed_party and is_party_ptr(other.get("room_ptr", 0)):
                    # The leaver's OWN party-object address, recorded when it
                    # joined (0x130 wire offset 8) - each client has its own.
                    reseed.append((dep_conn, dep_emit, dep_npid,
                                   other.get("room_ptrs", {}).get(
                                       mid, other["room_ptr"]),
                                   other["max_players"]))
    for other, mid in affected:
        leave = build_room_leave(other["room_id"], mid)
        for m2id, c2, em2 in list(other["conns"].values()):
            try:
                c2.sendall(leave)
                em2(f"   [leave] member_id={mid} left room "
                    f"{other['room_id'].hex()} - sent RoomLeave (0x134)")
            except OSError:
                pass
        other["stop_event"].set()
        ev = threading.Event()
        other["stop_event"] = ev
        start_member_refresher(other["conn"], other["emit"], other["members"],
                               other["room_id"], other["max_players"],
                               MEMBER_ID, MEMBER_ID, ev,
                               room_ptr=other["room_ptr"],
                               populate_self_npid=True)
    for dep_conn, dep_emit, dep_npid, dep_room_ptr, dep_max in reseed:
        reseed_departed_party(dep_conn, dep_emit, dep_npid, dep_room_ptr,
                              dep_max)


def evaluate_late_dead_peer_removal(sender_key, target_member_id, room_id_tail,
                                    now=None):
    """Decide whether a 0x137 carrying requester_member_id == 0 is a genuine
    LATE dead-peer removal that we should act on.

    Evidence (protos/0x137_kickout.ksy, live capture 2026-08-18): requester=0
    is an AUTOMATIC removal request with no requesting member, and it arrives
    in two clearly separated regimes:

      0.01s 0.02s 0.02s 0.17s          - emitted as a side effect of a RoomJoin
      29.7s ... 642.6s (8 frames)      - a host whose P2P layer has noticed an
                                         unreachable peer

    Acting on the FIRST kind kicks the joiner - that is the "Unable to join
    party / You were kicked" bug. Acting on the SECOND kind is what clears a
    zombie member whose client hung with its TCP socket still open (observed
    2026-08-18 22:43-22:46: last traffic 22:43:54, host asked for the drop at
    22:45:43, the roster only self-corrected a minute later when the socket
    finally closed).

    Because a control opcode misread as an action is the exact bug class that
    produced the 0x138 self-kick and the 0x13d re-announce regression, this
    NEVER trusts the frame alone. ALL of these must hold:

      1. the sender is a member of a room whose id matches the frame;
      2. the target is a different member of that same room;
      3. the target is not the room OWNER (owner departure is the
         close_room_and_notify path, not a member removal);
      4. the frame is LATE - at least LATE_KICKOUT_MIN_SECONDS since the
         roster last grew, i.e. far outside the join-flow window;
      5. the target's OWN connection is independently unresponsive - no
         inbound byte for DEAD_PEER_SILENCE_SECONDS, which is 2.5x its 30 s
         0x145 keepalive interval. If the target is still pinging, it is
         alive and we refuse, whatever the host believes.

    Returns ((target_key, member_id, conn, emit), room_id, note) when removal
    is warranted, or (None, None, note) with the reason it was refused. The
    caller performs the removal through the EXISTING departure path
    (broadcast_member_departure) so roster/refresher bookkeeping stays
    consistent.
    """
    now = time.monotonic() if now is None else now
    with rooms_lock:
        room_entry = None
        for info in active_rooms.values():
            if sender_key in info.get("conns", {}) and info["room_id"] == room_id_tail:
                room_entry = info
                break
        if room_entry is None:
            return None, None, "sender is not in a room with this room_id"
        target = None
        for key, (mid, c, em) in room_entry["conns"].items():
            if mid == target_member_id:
                target = (key, mid, c, em)
                break
        if target is None:
            return None, None, (f"target member_id={target_member_id} is not in room "
                                f"{room_entry['room_id'].hex()}")
        if target[0] == sender_key:
            return None, None, "target IS the sender (self-removal never acted on)"
        if id(room_entry["conn"]) == target[0]:
            return None, None, ("target is the room OWNER - owner departure is the "
                                "0x133/close path, not a member removal")
        since_join = now - room_entry.get("last_join_ts", now)
        if since_join < LATE_KICKOUT_MIN_SECONDS:
            return None, None, (f"only {since_join:.2f}s since the roster last grew - "
                                f"inside the join-flow window "
                                f"(<{LATE_KICKOUT_MIN_SECONDS:g}s), join-flow artifact")
        silence = now - last_inbound_ts.get(target[0], now)
        if silence < DEAD_PEER_SILENCE_SECONDS:
            return None, None, (f"target still ALIVE - last inbound {silence:.1f}s ago "
                                f"(<{DEAD_PEER_SILENCE_SECONDS:g}s, its ping interval "
                                f"is 30s); refusing to remove a live member")
        return (target, room_entry["room_id"],
                f"late by {since_join:.1f}s since last join, target silent for "
                f"{silence:.1f}s (>{DEAD_PEER_SILENCE_SECONDS:g}s)")


MEMBER_BLOB_OPCODE = 0x13b


def build_member_blob(member_id, room_id, blob):
    """Build a 0x13b per-member data blob, 80 bytes.

    Dispatch audit 7 (2026-08-16): handler looks up the member by the u16
    at wire offset 4 (FUN_00ad0d4c), writes the length byte at offset 6
    into member+0xF8 and memcpys that many payload bytes from offset 16
    into member+0xFC (cap 64). The audit called it "speculative - nothing
    principled to put in it" because no client->server supplier was known;
    the supplier is 0x13a (SetPartyData): same 80-byte size, same <=64
    payload cap, member-scoped, sent by every client about itself. The
    stub relays each client's own 0x13a payload to every room member as
    this message. Live theory (2026-08-16): member+0xFC is where the
    lobby's per-member rank display reads from (missing ranks were the
    first live symptom), and possibly what peer-consistency checks
    ("Host quit for cheating") compare.
    """
    body = bytearray(80)
    struct.pack_into(">I", body, 0, MEMBER_BLOB_OPCODE)
    struct.pack_into(">H", body, 4, member_id)
    payload = blob[:64]
    body[6] = len(payload)
    body[8:16] = room_id
    body[16:16 + len(payload)] = payload
    return bytes(body)


def build_owner_changed(room_id, joined_flag=1):
    """Build a NetMatchmakingHostFlagUpdated (opcode 0x13f), 16 bytes.

    NAME NOTE: this function's own name is legacy. `OwnerChanged` is 0x13d's
    name (built by build_owner_member below), not 0x13f's - see
    protos/0x13d_owner_changed.ksy vs protos/0x13f_host_flag_updated.ksy.
    The opcode constant was corrected to HOST_FLAG_UPDATED_OPCODE on
    2026-08-20; the function name is kept for now because dated research
    notes reference it by name.

    Layout: opcode(4) | joined_byte(1) | unused(3) | room_id(8).
    The handler (0x00ad825c-0x00ad82d0) searches the 4 room slots for
    room_obj+0x10 == wire[8:16] before writing `wire[4] & 1` into
    room_obj+0x19f4 - room_obj+0x10 is only set by Member's handler, so this
    MUST be sent after Member or it is silently swallowed.

    room_obj+0x19f4 is the host flag, as previously documented. What was NOT
    known before 2026-08-20 is that it LEAVES THE CONSOLE: the presence
    publisher copies the PARTY object's copy of it into the presence blob
    (`lbz r0,6644(r9)` @0x00397e08 with r9 = 0x01387f58, `stb r0,127(r1)`
    @0x00397e10 = blob offset 7), and a friend's client refuses to offer
    "Join Party" when that byte is nonzero:

      0x00348e14  returns 1 when the friend has no presence data, else
                  `blob[7] != 0`
      0x0034be10  `bne` on that result -> skips the "Join Party" menu item
                  (StringId 0xb1600ce3, text1.psarc 2.common)

    Writers of room_obj+0x19f4, full sweep for displacement 6644:
      0x00ad1f58  room-object reset                      -> 0
      0x00ad5c98  the 0x12f RoomCreate SENDER            -> 0
                  (`li r27,0` @0x00ad5c6c - unconditional)
      0x00ad6af0  SetHostFlag promote (fn 0x00ad6a34,    -> 1
                  a vtable method at slot 0x012e9c80;
                  it also emits the 0x13e request)
      0x00ad6c04  SetHostFlag demote                     -> 0
      0x00ad82cc  THIS message's handler                 -> wire[4] & 1

    So on a real server a PARTY host sits at 0 unless something explicitly
    promotes it, and 0 is what its friends need to see. Sending 1 on the
    party-create path removes "Join Party" from that host's row in every
    friend's list, permanently - the rejoin-party bug. See
    research/notes/2026-08-20-rejoin-party-bug.md.
    """
    body = bytearray(16)
    struct.pack_into(">I", body, 0, HOST_FLAG_UPDATED_OPCODE)
    body[4] = joined_flag & 1
    body[8:16] = room_id
    return bytes(body)


MEMBER_REFRESH_INTERVAL_SECONDS = 10

# THREAD-LEAK FIX (2026-08-17): the refresher used to be started from four
# different places (RoomCreate, RoomJoin x2, broadcast_member_departure) each
# with its own stop_event, and stopping a *previous* one relied on every one of
# those call sites remembering to set the right event. The last live run ended
# with SIX concurrent 10 s refreshers all re-pushing rosters at one client - and
# a roster push that omits a member tears that member's P2P connection down
# (FUN_00ad3190 -> mgr->vtable[0x1c]) while the next push redials it, exactly
# the churn that kills links. There is now at most ONE refresher per connection,
# enforced centrally: starting a new one cancels the old one, and each thread
# re-checks that it is still the registered generation on every tick so a
# cancelled thread cannot survive its interval.
refresher_lock = threading.Lock()
refreshers = {}      # id(conn) -> (generation, stop_event)
_refresher_gen = [0]


def stop_member_refresher(conn_key):
    """Cancel any refresher registered for this connection (idempotent)."""
    with refresher_lock:
        prev = refreshers.pop(conn_key, None)
    if prev is not None:
        prev[1].set()
    return prev is not None


def start_member_refresher(conn, emit, members, room_id, max_players,
                            owner_ref_id, local_ref_id, stop_event,
                            interval=MEMBER_REFRESH_INTERVAL_SECONDS,
                            room_ptr=ROOM_PTR, populate_self_npid=False):
    """EXPERIMENTAL (2026-08-15): live-confirmed via RPCS3 debugger memory
    read that ROOM_PTR+0x10 (room id) goes to zero shortly after Member is
    first processed - client-internal behavior (room "finalization"), not
    something we control - while ROOM_PTR+0xb8 (a "finalized" flag) stays
    set to 1. Code elsewhere that assumes a still-valid room id once that
    flag is set (_opd_FUN_0040b210, live-crash-confirmed) then traps. No
    evidence found (this session, extensive search) that any message exists
    to give the client a fresh/permanent id afterward - see
    research/notes/2026-08-15-room-teardown-and-flag-chain.md. Testing the
    pragmatic alternative: keep re-sending Member alone (not RoomJoined -
    that has its own internal registration/self-signal side effects we
    don't want to repeat) periodically, well under the ~55-70s window
    observed before the client gives up and abandons the room, so
    ROOM_PTR+0x10 never stays zero long enough for anything reading it to
    lose.
    """
    # *** VALIDATED 2026-08-17 (was: RE-REVIEW AFTER FULL 2-PLAYER FLOW WORKS) ***
    # The multi-member skip is now confirmed correct over a long session: a full
    # ~25-minute matchmade game (RPCS3.log 11:17:58 -> 11:42:36) held its
    # 2-member room via P2P alone with the refresher skipping it the whole time,
    # and ZERO party-churn events (no "kicked"/"You were"/PEER_DEACTIVATED) in
    # that window - the room did NOT go stale without our re-assertion. So the
    # open question below is answered: for >1 member the established P2P link
    # (MUTUAL_ACTIVATED on join) self-maintains room_obj+0x10; our periodic
    # re-broadcast is unnecessary there and was actively harmful (the churn bug
    # below). The refresher correctly serves ONLY the solo-host case.
    #
    # 2026-08-16 REGRESSION FIX: only refresh SOLO rooms. Live TTY showed the
    # host joining and LEAVING its own party every 10s - exactly this
    # interval - once a 2-member roster was being re-broadcast. Re-sending the
    # full roster to an already-established multi-member party makes the client
    # re-run its membership logic and churn ("You were kicked from the party"
    # spam on the host). A multi-member room is kept alive by the established
    # P2P link (SCE_NP_SIGNALING_EVENT_EXT_MUTUAL_ACTIVATED fires on join), so
    # our periodic re-assertion is unnecessary AND harmful there. The refresher
    # exists only for the solo-host case (keeping room_obj+0x10 nonzero before
    # anyone joins); for >1 member, send nothing and let the party stand.
    #
    # Whatever we decide below, FIRST cancel whatever this connection already
    # had running - the multi-member / party "skip" paths must still retire the
    # previous solo refresher, or it keeps pushing the now-stale 1-member roster
    # (which omits the member that just joined and thus drops its P2P link).
    conn_key = id(conn)
    stop_member_refresher(conn_key)
    if len(members) > 1:
        emit(f"   [refresh] SKIPPED periodic refresh for {len(members)}-member "
             f"room {room_id.hex()} (multi-member rooms are P2P-maintained; "
             f"re-broadcasting churns party membership)")
        return
    if is_party_ptr(room_ptr):
        # A solo occupant of the PARTY room (host who opened a party, or a host
        # left alone after the joiner departed) must NOT be refreshed - the
        # party lobby churns on Member re-broadcast and spams "kicked from
        # party" on the host. Only the GAME room needs solo keepalive.
        emit(f"   [refresh] SKIPPED periodic refresh for PARTY room "
             f"{room_id.hex()} (party lobby churns on re-broadcast; only the "
             f"game room needs solo keepalive)")
        return

    with refresher_lock:
        _refresher_gen[0] += 1
        gen = _refresher_gen[0]
        refreshers[conn_key] = (gen, stop_event)

    def run():
        try:
            while not stop_event.wait(interval):
                with refresher_lock:
                    cur = refreshers.get(conn_key)
                if cur is None or cur[0] != gen:
                    # Superseded/cancelled while we were sleeping - a stale
                    # thread must never push a stale roster.
                    return
                try:
                    member = build_member(members, room_id, max_players, owner_ref_id,
                                          local_ref_id, room_ptr=room_ptr,
                                          populate_self_npid=populate_self_npid)
                    conn.sendall(member)
                    emit(f"   [refresh] re-sent Member ({len(member)} bytes) to keep "
                         f"room_id={room_id.hex()} fresh (solo keepalive, gen={gen})")
                except OSError as e:
                    emit(f"   [refresh] stopping, send failed: {e}")
                    return
        finally:
            with refresher_lock:
                if refreshers.get(conn_key, (None, None))[0] == gen:
                    del refreshers[conn_key]
    t = threading.Thread(target=run, daemon=True,
                         name=f"refresh-{conn_key:x}-{gen}")
    t.start()


def _ts():
    """Wall-clock stamp for every log line: [HH:MM:SS.mmm].

    Added 2026-08-17. Find-match is a timing problem end to end (host lobby
    deadline = t(RoomCreate) + 8.0 + lobbyWaitTable[count]; 6.0 s P2P reserve
    timeout; 60.0 s GAME_LIST_WAIT cap), and this log had NO
    per-line timestamps at all - correlating it against RPCS3's TTY game clock
    was impossible and blocked a whole debugging round. Every physical line is
    stamped (hexdump rows included) so any grep/tail of a subset is still
    timeable.
    """
    return datetime.datetime.now().strftime("[%H:%M:%S.%f")[:-3] + "]"


def stamp(text):
    """Prefix every physical line of `text` with _ts()."""
    t = _ts()
    return "\n".join(f"{t} {line}" for line in text.split("\n"))


def hexdump(data):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:08x}  {hexpart:<48}  {asciipart}")
    return "\n".join(lines)


def recv_exact(conn, n, timeout=10):
    conn.settimeout(timeout)
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError(f"peer closed after {len(data)}/{n} bytes (wanted {n})")
        data += chunk
    return data


def sender_is_room_owner(room_entry, conn):
    """True if `conn` is the connection of the room's current owner/leader.

    Membership alone is NOT authorization: Kickout (0x137) and Promote (0x13c)
    used to act for any member of the room, so any player could kick or
    promote any other player - including themselves - by sending the opcode
    directly. The owner is tracked server-side as `owner_member_id` (the room
    creator, member 1, moved by a successful Promote), which is the same value
    0x13d OwnerMember publishes to every client as room_obj+0x19f0. Caller
    holds rooms_lock, or holds a reference taken under it.
    """
    slot = room_entry.get("conns", {}).get(id(conn))
    if slot is None:
        return False
    return slot[0] == room_entry.get("owner_member_id", MEMBER_ID)


def serve(conn, addr, log_lock, log):
    """Thread body: run handle() and always give the accept slot back.

    The release cannot live in handle()'s own `finally`: that block touches
    per-connection state (stop_event, the room registry) that is not yet bound
    if the connection dies during the initial handshake, so an exception there
    would skip the release and permanently retire a slot - the connection cap
    would then ratchet down to zero and stop accepting anyone.
    """
    try:
        handle(conn, addr, log_lock, log)
    finally:
        _handler_slots.release()


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()

    def emit(text):
        # Write immediately rather than batching until the connection closes -
        # this is a long-lived control connection now (see settimeout(600)
        # below), so waiting for close to log anything left us blind to
        # mid-connection activity while debugging "Lobby Server Error" live
        # on 2026-08-14.
        stamped = stamp(text)
        with log_lock:
            print(stamped, flush=True)
            log.write(stamped + "\n")
            log.flush()

    emit(f"==== {ts} SESSION MANAGER connection from {addr[0]}:{addr[1]} ====")
    try:
        # netmatchmaking_client_hello.ksy: fixed 48 bytes.
        hello = recv_exact(conn, 48)
        emit(f"-- recv client_hello (48 bytes) --\n{hexdump(hello)}")
        opcode_be = struct.unpack(">I", hello[0:4])[0]
        opcode_le = struct.unpack("<I", hello[0:4])[0]
        emit(f"   opcode as BE={opcode_be:#x} (expect {CLIENT_HELLO_OPCODE:#x} if BE) "
             f"LE={opcode_le:#x} (expect {CLIENT_HELLO_OPCODE:#x} if LE)")
        np_id = hello[8:44]
        emit(f"   np_id (36 bytes, likely SceNpId incl. online ID): {np_id!r}")
        own_npid = np_id.split(b"\x00", 1)[0]
        matched = False
        # Set when this connection sends a find-match search (0x135); its NEXT
        # RoomCreate is then a PUBLIC (matchmade) game that belongs in the
        # find-match pool. A RoomCreate WITHOUT a preceding 0x135 is a private/
        # custom game and must never be listed (one-shot: reset on create).
        find_match_searching = False
        find_match_mode = None
        find_match_build = None
        stop_event = threading.Event()
        # Per-room refresher lifecycle (2026-08-16): start_member_refresher's
        # background thread only stops on a socket error - nothing ever set
        # stop_event otherwise, and it was shared across every RoomCreate on
        # this connection. Since the session-manager connection stays open
        # across "back to menu, host again" cycles, an earlier room's
        # refresher kept re-sending Member (which overwrites ROOM_PTR+0x10)
        # forever, pinning it nonzero long after the room was abandoned - a
        # live debugger read confirmed ROOM_PTR+0x10 was still the FIRST
        # room's id going into a SECOND host attempt, causing the RoomJoined
        # id-gate (id_gate=0) to permanently mismatch and the client to give
        # up (0x133) without ever reaching a match again. Track the active
        # room's own stop_event separately so each new RoomCreate/abandon can
        # stop the previous room's refresher before it can pin stale state.
        active_room_stop = None

        # netmatchmaking_server_hello.ksy: fixed 16 bytes.
        # First guess: big-endian, matching this project's established convention -
        # if the client rejects/hangs, flip based on what opcode_be/opcode_le showed
        # for the client's own hello above.
        session_seed = 0
        resp = struct.pack(">IIII", SERVER_HELLO_OPCODE, 0, session_seed, 0)
        conn.sendall(resp)
        emit(f"-- sent server_hello (16 bytes, BE, session_seed={session_seed}) --\n{hexdump(resp)}")

        # Watch for anything further. This is the lobby control connection -
        # real usage means the player can sit in menus for minutes (choosing
        # host/join, picking a loadout, etc.) between the initial handshake
        # and the next actual message (RoomCreate/RoomSearch/...). An eager
        # idle timeout here silently kills the connection out from under the
        # client long before it tries to use it again, which then fails
        # locally with no visible network attempt at all - this is exactly
        # what "Lobby Server Error" live-diagnosed to on 2026-08-14 (no
        # timeout previously here was too short: 10s). Stay open until the
        # client itself closes or a very long idle period passes.
        conn.settimeout(600)
        while True:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                emit("  (600s idle after handshake, closing)")
                break
            if not chunk:
                emit("  (connection closed by peer after handshake)")
                break
            # Liveness record: ANY inbound byte proves this connection is
            # still being driven by a running client. Read by the late-0x137
            # dead-peer rule (see DEAD_PEER_SILENCE_SECONDS).
            with rooms_lock:
                last_inbound_ts[id(conn)] = time.monotonic()
            emit(f"-- further data ({len(chunk)} bytes) --\n{hexdump(chunk)}")

            opcode = struct.unpack(">I", chunk[0:4])[0] if len(chunk) >= 4 else None
            if opcode == ROOM_CREATE_OPCODE and len(chunk) >= 232:
                name_start = 0x28
                name_end = chunk.find(b"\x00", name_start)
                name = chunk[name_start:name_end] if name_end != -1 else b""
                # RoomCreate's room-name field is "<npid>.<timestamp>" - split
                # off the npid portion for the member-record fix (see
                # build_room_joined/build_member docstrings).
                npid = name.split(b".", 1)[0][:16]
                # 2026-08-16 dispatch audit (research/notes/2026-08-16-
                # sessmgr-dispatch-audit-and-unsent-opcodes.md 4b/4c):
                # RoomCreate's sender never writes offset 0x1e (the old
                # max_players read - uninitialized stack, masked by the
                # `or 10` fallback); the real field is at 0x24 (live-constant
                # 8, which the client also writes to room_obj+0x1f8 itself).
                # And offset 8 is the client's OWN room-object pointer -
                # echo that instead of the hardcoded debugger-recovered
                # ROOM_PTR, which only ever matched this one machine's boot.
                # Clamped to 1..8 (clamp_max_players): the retail ceiling is 8
                # for every mode, and this value is both advertised to clients
                # and used as the RoomJoin admission gate, so it cannot be
                # taken verbatim from the wire.
                max_players = clamp_max_players(
                    struct.unpack(">H", chunk[0x24:0x26])[0])
                room_ptr = struct.unpack(">I", chunk[8:12])[0]
                # 8-byte room identity echoed into Member wire 16:24 and the
                # RoomJoined id-gate. ALWAYS server-minted (2026-08-19) - see
                # the three synth_*_room_id functions. This used to default to
                # `chunk[4:12]`, but offset 4:8 is uninitialised client stack
                # (protos/0x12f_room_create.ksy pad_4), so the id was neither
                # guaranteed unique nor stable. Every branch below assigns it;
                # None here makes an unassigned path fail loudly instead of
                # silently shipping stack residue.
                room_id = None
                # UNIQUE PUBLIC ROOM ID (2026-08-17, coordination root-cause
                # note §4): chunk[4:12] is `00000000 01383bd8` on every client,
                # so two find-match hosts collide byte-for-byte and the
                # cross-connection registry cannot tell them apart (and the
                # 0x136 game list would advertise an ambiguous join key). Mint
                # our own for public rooms.
                #
                # UNIQUE PARTY ROOM ID (2026-08-17, Join Party fix): the party
                # object is the fixed global 0x01387f58 on EVERY client, so its
                # historical id (00000000 01387f58) collides byte-for-byte too -
                # exactly the ambiguity behind the failing direct Join Party
                # (the RoomJoin host lookup has to guess among colliding-id
                # entries and a stale/racing one wins). Mint a unique id for the
                # party room as well; it reaches the joiner over NP 268 (from
                # room_obj+0x10) and via presence, both triple-verified in the
                # EBOOT - see synth_party_room_id. The SOLO GAME host / custom
                # game path (GAME_ROOM_PTR, no find-match) still keeps the
                # historical static id: it is single-console with no cross-conn
                # join, so its collision is harmless and the live-confirmed
                # solo-host path stays byte-for-byte untouched.
                # BUILD CANARY (2026-08-18, made multi-build 2026-08-19). Two
                # BEHAVIOURAL decisions compare the client's room-object pointer
                # by equality: the unique-party-id mint just below, and the
                # solo-keepalive skip in start_member_refresher. Those objects
                # are per-build globals, so an unknown build silently loses both
                # - no error, just the Join Party host-lookup collision and the
                # "kicked from party" churn quietly returning. That is not
                # hypothetical: it happened live on 2026-08-19 when a 01.11
                # client's party join bounced against 01.00-only constants.
                # See CLIENT_BUILDS.
                if room_ptr not in KNOWN_ROOM_PTRS:
                    emit(f"   *** UNKNOWN room_ptr {room_ptr:#010x} - not a "
                         f"game or party object of any known build "
                         f"({', '.join(v for v, _ in CLIENT_BUILDS.values())}). "
                         f"Party detection and the unique-party-id mint are "
                         f"BOTH keyed on these addresses, so Join Party will "
                         f"collide and bounce for this client until its build "
                         f"is added. FIX: create a game room and a party on "
                         f"this build, read room_ptr (0x12f wire offset 8) for "
                         f"each, and add the pair to CLIENT_BUILDS. The party "
                         f"pointer CANNOT be extrapolated - the inter-object "
                         f"delta differs between builds. ***")
                elif build_of(room_ptr) is not None:
                    emit(f"   (client build {build_of(room_ptr)}, "
                         f"{'PARTY' if is_party_ptr(room_ptr) else 'GAME'} "
                         f"room object {room_ptr:#010x})")
                # PARTY OBJECT WINS (2026-08-19). This test used to come
                # SECOND, after find_match_searching, and that was a real bug: a
                # party created shortly after a find-match search inherited the
                # still-set search flag, so it was registered PUBLIC/matchmade,
                # skipped the unique-party-id mint entirely (it was the elif
                # branch), and got advertised to searchers as if it were a game.
                # Live at 01:00:50 - "room 50000008013bf068 registered as
                # PUBLIC/matchmade" for a create on the PARTY object - and the
                # invite-accept into it bounced immediately afterwards.
                # The room OBJECT is authoritative: a create on the party object
                # is a party, whatever the client was doing beforehand.
                if is_party_ptr(room_ptr):
                    room_id = synth_party_room_id(room_ptr)
                    emit(f"   [party-id] minted unique party room_id "
                         f"{room_id.hex()} for {npid!r} (party object "
                         f"{room_ptr:#010x}; disambiguates the RoomJoin host "
                         f"lookup for direct Join Party)")
                    if find_match_searching:
                        emit(f"   [party-id] NOTE: a find-match search preceded "
                             f"this party create; the search flag is being "
                             f"ignored because the party object takes priority")
                        find_match_searching = False
                    is_matchmaking_host = False
                elif find_match_searching:
                    room_id = synth_public_room_id(room_ptr)
                else:
                    # Party-started / private match on the GAME room object.
                    room_id = synth_private_room_id(room_ptr)
                    emit(f"   [private-id] minted unique private room_id "
                         f"{room_id.hex()} for {npid!r} (game object "
                         f"{room_ptr:#010x}, no find-match search; replaces the "
                         f"old uninitialised-stack chunk[4:12] fallthrough)")
                if room_id is None or len(room_id) != 8:
                    raise AssertionError(
                        f"room_id was not minted for room_ptr {room_ptr:#010x}")
                # RoomCreate's own wire offset 0xc:0x10 (4 bytes) - live-
                # evidenced 2026-08-15 as a likely map/level identifier, see
                # build_room_joined's docstring. Echo it straight back.
                map_id = chunk[0xc:0x10]
                # room_obj+0x0c. Used for exactly ONE decision - "is this a
                # matchmaking self-host?" - and nothing else; see
                # protos/0x12f_room_create.ksy for why the field is otherwise
                # untrusted. A matchmaking host carries the MODE here (0x02/
                # 0x03); private and party creates carry build-specific values.
                room_field_0c = struct.unpack(">I", chunk[0xc:0x10])[0]
                # A known private/party playlist is NEVER a matchmaking host,
                # even if a stale search flag is still set from a queue the
                # client just left. Otherwise: a preceding search, or a known
                # matchmaking playlist id (01.11 self-hosts BEFORE searching, so
                # there is no search to key on - see the "public" comment below).
                is_matchmaking_host = (
                    room_field_0c not in NON_MATCHMAKING_PLAYLISTS
                    and (find_match_searching
                         or room_field_0c in MATCHMAKING_PLAYLISTS))
                # RoomCreate's own wire offset 0xb0:0xb2 (2 bytes) - CONFIRMED
                # 2026-08-16 via ~24 live captures spanning every map and both
                # teams, zero exceptions: 0x0000=unset/spectator, 0x0001=Blue,
                # 0x0002=Red. See research/notes/2026-08-16-team-selection-
                # field-confirmed.md. Never echoed anywhere before now - the
                # slot this feeds (Member's per-entry offset 16, a u16 within
                # the "18x u16 attributes" block) has sat zeroed all along,
                # and a blind team=0 guess into that same slot was already
                # tried and falsified earlier tonight. Trying the REAL
                # captured value instead - EXPERIMENTAL, not yet live-tested.
                team = struct.unpack(">H", chunk[0xb0:0xb2])[0]

                # ---- HARVEST THIS HOST'S 32-BYTE MEMBER BLOB (2026-08-17) ----
                # RANK/LOADOUT FIX. wire[0x26] = length, wire[0xa8:] = blob
                # (0x00ad5d10/0x00ad5d18/0x00ad5d20/0x00ad5d30 - see
                # extract_member_blob). Without this the stub has NOTHING to put
                # in the roster's per-member blob field on the find-match path,
                # because no 0x13a is ever sent there (FUN_00ad6148 @0x00ad6240
                # returns silently while room_obj+0x10 == 0), so every remote
                # member's FUN_00ad2650 lookup returns NULL and the lobby's rank
                # / faction / loadout widgets render nothing.
                # NOTE the team read just above is really blob[8]<<8|blob[9] -
                # the same bytes - which is consistent with blob[9] being the
                # `value-1` string-table index FUN_0039c69c is called with.
                host_blob = extract_member_blob(chunk, ROOM_CREATE_BLOB_LEN_OFF,
                                                ROOM_CREATE_BLOB_OFF)
                # A fresh room reuses a shared static room_id on the private /
                # party paths (0000000001383bd8 / 0000000001387f58), so drop
                # anything a PREVIOUS occupant of that id left behind before
                # seeding this one - otherwise a dead player's rank/loadout gets
                # replayed to the next joiner.
                with rooms_lock:
                    for k in [kk for kk in member_blobs if kk[0] == room_id]:
                        member_blobs.pop(k, None)
                if host_blob is not None:
                    with rooms_lock:
                        member_blobs[(room_id, MEMBER_ID)] = host_blob
                    emit(f"   [blob] harvested {len(host_blob)}-byte member blob "
                         f"from {npid!r}'s RoomCreate (wire 0x{ROOM_CREATE_BLOB_OFF:x}, "
                         f"len byte 0x{ROOM_CREATE_BLOB_LEN_OFF:x}) -> cached for "
                         f"room {room_id.hex()} member_id={MEMBER_ID}"
                         + ("" if len(host_blob) == 32 else
                            "  *** NOT 32 BYTES - FUN_00ad2650 will reject it ***"))
                else:
                    emit(f"   [blob] no usable member blob in {npid!r}'s "
                         f"RoomCreate (len byte = "
                         f"{chunk[ROOM_CREATE_BLOB_LEN_OFF] if len(chunk) > ROOM_CREATE_BLOB_LEN_OFF else '??'}) "
                         f"- remote rank/loadout will stay blank for this room")
                create_blobs = {MEMBER_ID: host_blob} if host_blob else None

                # EXPERIMENTAL (2026-08-16, dispatch audit proposal #4, applied
                # after the HostFlagUpdated-alone test still hit the team assert):
                # RoomJoined is DROPPED from the solo-host reply. Audit
                # evidence: 0x132's handler registers a member with
                # is_local/is_owner hardcoded 0, which (a) creates a phantom
                # 2nd member slot for a 1-player room, (b) is the actual
                # source of the OWN_NP_ID self-signaling (the resolve at
                # 0xad34a4 only fires for is_local==0 slots), and (c) forced
                # the self-npid zeroing hack in build_member that left the
                # local player nameless ("Removing User ''..."). Member's own
                # handler carries the real room-create-completed latch
                # (0xad79ec) and takes the room pointer straight from wire
                # offset 8 - no id-gate, so the historical id-gate race that
                # motivated the 250ms delay shouldn't apply on this path
                # either (delay kept for now to change one thing at a time).
                # See research/notes/2026-08-16-sessmgr-dispatch-audit-and-
                # unsent-opcodes.md 3. With RoomJoined gone, the self entry's
                # real NpId is restored (populate_self_npid=True) so the
                # local member finally has an identity - the empty-name user
                # record is the live-evidenced feeder of the team-assignment
                # miss behind the net-game-manager.cpp:1358 boot.
                member = build_member([(MEMBER_ID, npid)], room_id, max_players,
                                       owner_ref_id=MEMBER_ID, local_ref_id=MEMBER_ID,
                                       team=team, room_ptr=room_ptr,
                                       populate_self_npid=True,
                                       blobs=create_blobs)
                # EXPERIMENTAL (2026-08-16, dispatch audit finding #1): the
                # client's RoomCreate sender clears its own "I am the host"
                # flag and only 0x13f can set it - without this a solo host
                # never becomes the host (see build_owner_changed's
                # docstring). Must come after Member in the write.
                # 0x13f writes room_obj+0x19f4 (the host flag) and nothing
                # else.
                #
                # PARTY ROOMS: send 0. ROOT CAUSE of the rejoin-party bug
                # (2026-08-20). The PARTY object's copy of this byte is
                # exported in presence (blob offset 7, `lbz r0,6644(r9)`
                # @0x00397e08), and a friend's client skips the "Join Party"
                # menu item entirely when the byte it sees is nonzero
                # (0x00348e14 -> `bne` @0x0034be10). The client's own
                # RoomCreate sender leaves it 0 (`li r27,0` @0x00ad5c6c,
                # `stb` @0x00ad5c98) and only an explicit SetHostFlag promote
                # (0x00ad6a34) ever sets it to 1, so 0 is what a party host is
                # supposed to advertise. Sending 1 here made every party this
                # server answered permanently unjoinable from the friends list,
                # whether or not anyone had ever joined and left it.
                #
                # GAME ROOMS: still 1, UNCHANGED and deliberately so. The
                # 2026-08-16 audit added it to make a solo host "become the
                # host", the find-match path is live-working with it, and the
                # GAME object's copy of the byte never reaches presence - the
                # publisher reads the party object only. Whether the game room
                # also wants 0 is a separate question needing its own live run.
                party_create = is_party_ptr(room_ptr)
                owner_changed = build_owner_changed(
                    room_id, joined_flag=0 if party_create else 1)
                # REVERTED to RoomJoined-first (2026-08-15): the Member-first
                # order was introduced to fix a capacity trap in the
                # find-match 2-real-player pairing path (see that branch's
                # comment for the full mechanism - RoomJoined's own internal
                # registration call needs capacity already set). Applying the
                # SAME reorder here regressed solo-host Custom Game, which had
                # worked crash-free for hours with RoomJoined sent first -
                # live-confirmed 2026-08-15 (started crashing with the exact
                # same SCE_NP_SIGNALING_ERROR_OWN_NP_ID/trap sequence only
                # after this reorder landed). Unlike find-match, solo-host's
                # RoomJoined id-gate MUST match the client's pending room slot
                # (the original "Lobby Server Error" fix, live-debugger-
                # confirmed at 0x00ad7b14) - it can't use find-match's
                # non-matching id_gate workaround either, so reverting the
                # order is the safe fix here specifically.
                #
                # EXPERIMENTAL (2026-08-16): research/notes/2026-08-14-room-
                # slot-gating.md flagged, and never resolved, whether the
                # client's local room-slot object genuinely exists yet by the
                # time this reply arrives, or whether it's registered by a
                # not-yet-run background/async step - i.e. a race, not just
                # the leftover-refresher staleness already fixed tonight.
                # Live evidence supports this: even a freshly-rebooted RPCS3's
                # very first RoomCreate this boot has still intermittently
                # failed the id-gate tonight, which the refresher fix alone
                # doesn't explain (nothing could have gone stale yet on a
                # true first attempt). Trying a small fixed delay before
                # replying, on the theory that giving the client's own local
                # slot-registration code a moment to run first reduces how
                # often our reply beats it there. NOT confirmed - a real
                # experiment, not a proven fix. If flakiness persists
                # unchanged, revert this and treat the race theory as
                # unconfirmed rather than assuming the delay itself is wrong.
                # NOT a stray-bytes bug: this write is Member (exactly
                # 0xa0+0x68*n) + 0x13f HostFlagUpdated (16) + 0x13d OwnerMember
                # (16) concatenated into one TCP write for efficiency. Each
                # carries its own opcode and fixed length, so the client
                # parses all three correctly off the stream; measuring the
                # combined write against the Member-only size formula makes
                # it look like +32 stray bytes when it's just two more
                # complete messages. The relayed Member path below (existing
                # members, not this connection) sends Member alone, which is
                # why it always measures exact.
                time.sleep(0.25)
                conn.sendall(member + owner_changed
                             + build_owner_member(room_id, MEMBER_ID))
                emit(f"   parsed opcode={opcode:#x} (RoomCreate, map_id={map_id.hex()}), sent "
                     f"Member+HostFlagUpdated+OwnerMember as one write, NO RoomJoined "
                     f"({len(member)}+{len(owner_changed)} bytes, "
                     f"room_ptr={room_ptr:#x} (parsed from wire offset 8), "
                     f"max_players={max_players} (parsed from wire offset 0x24), "
                     f"self npid populated, "
                     f"marking member_id={MEMBER_ID} as both local+owner+host)\n"
                     f"{hexdump(member + owner_changed)}")
                if active_room_stop is not None:
                    active_room_stop.set()
                active_room_stop = threading.Event()
                start_member_refresher(conn, emit, [(MEMBER_ID, npid)], room_id, max_players,
                                        MEMBER_ID, MEMBER_ID, active_room_stop,
                                        room_ptr=room_ptr, populate_self_npid=True)
                with rooms_lock:
                    # Replace only the entry for THIS SAME room_id. Rooms this
                    # connection owns under OTHER ids (its party room, when it
                    # is now creating a game room) must survive - overwriting
                    # them is what silently destroyed live parties before
                    # 2026-08-18. See active_rooms' comment.
                    old_entry = active_rooms.get((id(conn), room_id))
                    if old_entry is not None:
                        # A joint-roster refresher started by the 0x130 join
                        # handler holds a NEWER stop_event than this thread's
                        # local active_room_stop - stop it via the registry
                        # so it can't outlive its room.
                        old_entry["stop_event"].set()
                    active_rooms[(id(conn), room_id)] = {
                        "npid": npid, "conn": conn, "emit": emit,
                        "room_id": room_id, "room_ptr": room_ptr,
                        "max_players": max_players,
                        "stop_event": active_room_stop,
                        # member_id -> connection map for per-room broadcast
                        # (0x13a -> 0x13b relay); joiners get added by 0x130.
                        "conns": {id(conn): (MEMBER_ID, conn, emit)},
                        "members": [(MEMBER_ID, npid)],
                        # AUTHORITATIVE LEADER (2026-08-20). The room creator
                        # is member 1 and starts as owner; a Promote (0x13c)
                        # moves it, which is the same source of truth the
                        # 0x13d OwnerMember message publishes to every client
                        # (room_obj+0x19f0). Kickout and Promote are checked
                        # against this - without it any member could kick or
                        # promote anyone, since being in the room was the only
                        # test.
                        "owner_member_id": MEMBER_ID,
                        # When the roster last GREW. The late-0x137 dead-peer
                        # rule refuses to act inside the join-flow window
                        # measured from this instant (LATE_KICKOUT_MIN_SECONDS).
                        "last_join_ts": time.monotonic(),
                        # Monotonic member-id allocator (host=1, joiners 2,3,4...)
                        # + per-member room_ptr (the 0x131 hazard field - each
                        # client needs ITS OWN room-slot address). See
                        # research/notes/2026-08-18-jip-roster-collision.md.
                        "next_member_id": JOINER_MEMBER_ID,
                        "room_ptrs": {MEMBER_ID: room_ptr},
                        # PUBLIC iff the room DECLARES itself a matchmaking
                        # lobby - its playlist id says so.
                        #
                        # This was previously inferred from message ORDERING:
                        # "did a 0x135 search arrive on this connection first".
                        # That was a proxy, not the signal. It only ever worked
                        # because 01.00 happens to search before it self-hosts.
                        # A client that self-hosts FIRST and searches afterwards
                        # (01.11 does; live 2026-08-19, room created 00:40:03
                        # with no preceding search, first 0x135 at 00:40:47
                        # after that room was abandoned) had every matchmaking
                        # host registered PRIVATE and never advertised.
                        #
                        # The room carries the answer regardless of ordering: a
                        # matchmaking host stamps the PLAYLIST it is hosting in
                        # field_0c, which private and party creates never do.
                        # The preceding search is kept only as corroboration -
                        # it still covers a client that searched and then
                        # stamped a stale value (observed once, 2026-08-18
                        # 23:18:49).
                        "public": is_matchmaking_host,
                        # The playlist this room serves, taken from the SEARCH
                        # that preceded it (0x135 field_0c), not from this
                        # RoomCreate's own room_field_0c - the room field is not
                        # reliably reset and has been seen stale. None = unknown,
                        # which the 0x136 filter treats as "offer to anyone".
                        # Playlist this room serves. Prefer the SEARCH that
                        # preceded it (authoritative - see 0x135's schema); fall
                        # back to the room's own field only when there was no
                        # search at all, which on 01.11 is the normal case for a
                        # matchmaking self-host and is then the only signal.
                        "mode": (find_match_mode if find_match_searching
                                 else (room_field_0c if is_matchmaking_host else None)),
                        # Game build of the client that owns this room, from its
                        # own room-object pointer. None = unrecognised build,
                        # which the 0x136 filter treats as "offer to anyone".
                        "build": build_of(room_ptr),
                    }
                if find_match_searching:
                    emit(f"   (this RoomCreate follows a find-match search - "
                         f"room {room_id.hex()} registered as PUBLIC/matchmade; "
                         f"now discoverable in the 0x136 list to other searchers)")
                    find_match_searching = False  # one-shot
            elif opcode == 0x130 and len(chunk) >= 0x18:
                # RoomJoin - see active_rooms' comment for the wire evidence.
                join_room_ptr = struct.unpack(">I", chunk[8:12])[0]
                target_room_id = chunk[0x10:0x18]
                host = None
                # Set to (current_members, capacity) when the room is full.
                join_refused = None
                with rooms_lock:
                    # Take the MOST RECENT match on another connection, not
                    # the first. Party room_ids are minted unique per room
                    # since 2026-08-17 (synth_party_room_id, see the
                    # RoomCreate handler above), so an exact id collision
                    # between two LIVE parties no longer happens - but a
                    # stale registry entry for the SAME room can still
                    # outlive its connection and shadow the live one. Back
                    # when every client shared the static party room_id
                    # 0000000001387f58, matching the first (oldest) entry is
                    # what made a failed Join Party "corrupt" the next
                    # request by routing it to a dead connection. Keeping
                    # last-match wins is the cheap defence that still holds
                    # for the solo/custom game path, which deliberately
                    # retains its historical static id. dict preserves
                    # insertion order, so iterate and keep the last match.
                    for key, info in active_rooms.items():
                        if info["conn"] is not conn and info["room_id"] == target_room_id:
                            host = info
                if host is not None:
                    # CROSS-BUILD JOIN WATCH (2026-08-19). WARN ONLY - we do not
                    # refuse yet. A party invite crosses PSN, not our server, so
                    # a 1.00 client could in principle be invited into a 1.11
                    # party; the two cannot actually play together. Refusing
                    # outright risks false positives on a build we have not
                    # catalogued, and today already showed how a silent mismatch
                    # of these constants breaks Join Party - so observe first,
                    # enforce once there is evidence this fires in real use.
                    joiner_build = build_of(join_room_ptr)
                    host_build = host.get("build")
                    if (joiner_build is not None and host_build is not None
                            and joiner_build != host_build):
                        emit(f"   *** CROSS-BUILD JOIN: joiner is {joiner_build} "
                             f"(room_ptr {join_room_ptr:#010x}) but the room "
                             f"belongs to {host_build}. These builds cannot play "
                             f"together; the session will not work. Allowing it "
                             f"for now so the behaviour can be observed. ***")
                    # Always speak the room identity WE assigned (registry key).
                    # For the party/invite path this is identical to what the
                    # client sent; on the find-match path it is the synthesized
                    # unique public id, which both clients must agree on.
                    target_room_id = host["room_id"]
                    # CAPACITY GATE. The 0x136 search-result filter only hides
                    # a full room from searchers; it is advisory and does not
                    # cover the party-invite/direct-join path, nor two
                    # searchers who both saw one free slot. This is the
                    # authoritative check, taken with the member_id allocation
                    # under a single rooms_lock so concurrent joins cannot both
                    # pass it and overfill the room.
                    with rooms_lock:
                        capacity = clamp_max_players(
                            host.get("max_players", RETAIL_MAX_PLAYERS))
                        if len(host["members"]) >= capacity:
                            join_refused = (len(host["members"]), capacity)
                        else:
                            # Allocate a UNIQUE, never-reused member_id for this
                            # joiner (host=1, then 2, 3, 4, ...). A fixed
                            # JOINER_MEMBER_ID=2 collided on the 3rd participant
                            # and tore the whole session down - see
                            # research/notes/2026-08-18-jip-roster-collision.md.
                            new_mid = host.get("next_member_id", JOINER_MEMBER_ID)
                            host["next_member_id"] = new_mid + 1
                            host.setdefault(
                                "room_ptrs",
                                {MEMBER_ID: host["room_ptr"]})[new_mid] = join_room_ptr
                if host is None:
                    emit(f"   parsed opcode={opcode:#x} (RoomJoin, "
                         f"room_ptr={join_room_ptr:#x}, "
                         f"target room_id={target_room_id.hex()}) - NO matching "
                         f"room found on another connection, no reply sent")
                elif join_refused is not None:
                    # Declined, no reply - the same shape as the "no matching
                    # room" case above. The protocol has no server->client
                    # "room full" message (the 28-entry NetMatchmaking table
                    # carries no rejection opcode), and inventing one is not an
                    # option; a joiner that receives no Member for the room it
                    # asked to join falls back through its own join timeout,
                    # which is the same path a vanished room produces.
                    emit(f"   parsed opcode={opcode:#x} (RoomJoin, "
                         f"room_ptr={join_room_ptr:#x}, "
                         f"target room_id={target_room_id.hex()}) - room is FULL "
                         f"({join_refused[0]}/{join_refused[1]} members), join "
                         f"from {own_npid!r} DECLINED, no reply sent")
                else:
                    # Same roster discipline as everywhere else: per-recipient,
                    # own entry FIRST, self npid populated (the local member
                    # needs a real identity for team/user lookups), no
                    # RoomJoined anywhere, host flag set only for the actual
                    # host via 0x13f (explicit 0 for the joiner in case a
                    # stale 1 survives from an earlier hosted room - only
                    # RoomCreate's own sender clears it client-side).
                    # new_mid was allocated by the capacity gate above, under
                    # the same lock that admitted this joiner.
                    joiner_entry = (new_mid, own_npid)
                    # ---- HARVEST THIS JOINER'S 32-BYTE MEMBER BLOB (keyed by the
                    # newly-allocated member_id) ---- wire[0x0c]=len, wire[0x18:]=blob
                    # (FUN_00ad6718); the ONLY place the joiner tells us its
                    # rank/faction on the find-match path (it sends no 0x13a there).
                    join_blob = extract_member_blob(chunk, ROOM_JOIN_BLOB_LEN_OFF,
                                                    ROOM_JOIN_BLOB_OFF)
                    if join_blob is not None:
                        with rooms_lock:
                            member_blobs[(target_room_id, new_mid)] = join_blob
                        emit(f"   [blob] harvested {len(join_blob)}-byte member "
                             f"blob from {own_npid!r}'s RoomJoin -> cached for room "
                             f"{target_room_id.hex()} member_id={new_mid}"
                             + ("" if len(join_blob) == 32 else
                                "  *** NOT 32 BYTES - FUN_00ad2650 will reject it ***"))
                    else:
                        emit(f"   [blob] no usable member blob in {own_npid!r}'s "
                             f"RoomJoin - rank/loadout widgets for this player "
                             f"will stay blank")
                    # Full roster = every current member + the newcomer. Each
                    # recipient gets the SAME roster content with its OWN entry
                    # first and its own local_ref_id; owner is always the host (1).
                    with rooms_lock:
                        full_members = list(host["members"]) + [joiner_entry]
                        existing = list(host["conns"].values())   # (mid, conn, emit)
                        room_ptrs = dict(host.get("room_ptrs", {MEMBER_ID: host["room_ptr"]}))
                        blobs = {mid: b for (rid, mid), b in member_blobs.items()
                                 if rid == target_room_id}

                    def roster_for(mid):
                        own = [m for m in full_members if m[0] == mid]
                        return own + [m for m in full_members if m[0] != mid]

                    # REORDERED (2026-08-18): tell every EXISTING member about the
                    # newcomer FIRST - so the host starts dialing the joiner's P2P
                    # link BEFORE the joiner is admitted and enters JOIN_GAME_WAIT.
                    # Stick-vs-bounce is a timing race (byte-identical rosters both
                    # stick and bounce depending on host state); admitting the
                    # joiner before the host is told to dial it loses that race.
                    host_dead = False
                    for (mid, mconn, memit) in existing:
                        rp = room_ptrs.get(mid, host["room_ptr"])
                        m = build_member(roster_for(mid), target_room_id,
                                         host["max_players"], owner_ref_id=MEMBER_ID,
                                         local_ref_id=mid, room_ptr=rp,
                                         populate_self_npid=True, blobs=blobs)
                        try:
                            # NO 0x13d OwnerMemberChanged here (2026-08-18): the
                            # owner does not change on a join, but 0x13d's handler
                            # runs room->vtable[0x34], the ownership-notification
                            # callback - the source of the host's "New host : X"
                            # TTY print that fires on EVERY bounced JIP attempt.
                            # Re-announcing host ownership into an already-
                            # established (mid-match) room is the join-party bug
                            # class: a control opcode the client treats as
                            # disruptive while the stub assumes it's an ack. The
                            # joiner still gets 0x13f+0x13d below - for it this is
                            # the FIRST owner announcement, not a re-announcement.
                            mconn.sendall(m)
                            memit(f"   [join] {own_npid!r} joining room "
                                  f"{target_room_id.hex()} - pushed {len(full_members)}"
                                  f"-member roster to member {mid} (dial the joiner)")
                        except OSError as e:
                            memit(f"   [join] push to member {mid} failed ({e})")
                            if mconn is host["conn"]:
                                host_dead = True
                    if host_dead:
                        # The host connection is dead - purge its stale registry
                        # entry so it can't poison the NEXT join for this room, and
                        # do NOT admit the joiner into a dead room.
                        emit(f"   [join] host push failed - purging stale host "
                             f"entry for room {target_room_id.hex()}")
                        with rooms_lock:
                            stale = None
                            for k, v in active_rooms.items():
                                if v is host:
                                    stale = k
                                    break
                            if stale is not None:
                                host["stop_event"].set()
                                del active_rooms[stale]
                            for (rid, mid) in [kk for kk in member_blobs
                                               if kk[0] == target_room_id]:
                                del member_blobs[(rid, mid)]
                    else:
                        # NOW admit the newcomer (host already told to dial it).
                        self_member = build_member(roster_for(new_mid),
                                                   target_room_id, host["max_players"],
                                                   owner_ref_id=MEMBER_ID,
                                                   local_ref_id=new_mid,
                                                   room_ptr=join_room_ptr,
                                                   populate_self_npid=True, blobs=blobs)
                        # joined_flag=0 for the joiner is already the value the
                        # friends-list "Join Party" guard wants to see
                        # advertised (see build_owner_changed), so this path
                        # needs no change for the rejoin-party bug.
                        conn.sendall(self_member
                                     + build_owner_changed(target_room_id,
                                                           joined_flag=0)
                                     + build_owner_member(target_room_id, MEMBER_ID))
                        emit(f"   parsed opcode={opcode:#x} (RoomJoin) - JOINED "
                             f"{host['npid']!r}'s room {target_room_id.hex()} as "
                             f"member_id={new_mid}; room now has {len(full_members)} "
                             f"members (room_ptr={join_room_ptr:#x})")
                        # replay every member's cached blob to every OTHER member
                        # (0x13b must follow Member, same rule as 0x13f).
                        all_conns = existing + [(new_mid, conn, emit)]
                        for bmid, blob in blobs.items():
                            b = build_member_blob(bmid, target_room_id, blob)
                            for (mid, mconn, _me) in all_conns:
                                if mid == bmid:
                                    continue
                                try:
                                    mconn.sendall(b)
                                except OSError:
                                    pass
                        # register the newcomer; refresh the host keepalive with
                        # the full roster.
                        with rooms_lock:
                            host["conns"][id(conn)] = (new_mid, conn, emit)
                            host["members"] = full_members
                            # Roster grew: restart the join-flow quiet window
                            # for the late-0x137 dead-peer rule.
                            host["last_join_ts"] = time.monotonic()
                            last_inbound_ts[id(conn)] = time.monotonic()
                        host["stop_event"].set()
                        new_host_stop = threading.Event()
                        host["stop_event"] = new_host_stop
                        start_member_refresher(host["conn"], host["emit"],
                                               roster_for(MEMBER_ID),
                                               target_room_id, host["max_players"],
                                               MEMBER_ID, MEMBER_ID, new_host_stop,
                                               room_ptr=host["room_ptr"],
                                               populate_self_npid=True)
                        # the joiner's own keepalive refresher
                        if active_room_stop is not None:
                            active_room_stop.set()
                        active_room_stop = threading.Event()
                        start_member_refresher(conn, emit, roster_for(new_mid),
                                               target_room_id, host["max_players"],
                                               MEMBER_ID, new_mid,
                                               active_room_stop,
                                               room_ptr=join_room_ptr,
                                               populate_self_npid=True)
                    # The roster pushed to the host just above is what
                    # makes it dial this peer (FUN_00ad33d8 -> mgr->Connect); the
                    # link the joiner already established resolves to state 2, so
                    # FUN_003b19c4 counts 2 and the host's lobby deadline moves
                    # from 12.0 s to 16.0 s (lobbyWaitTable[2]).
            elif opcode == FIND_MATCH_OPCODE:
                # REAL-SERVER BEHAVIOR (root-cause note §7, validated in
                # disassembly). We do NOT park, elect, withhold, or fabricate
                # anything: we answer every 0x135 search with the ACTUAL list of
                # live public games (0x136) and let the client's own matchmaking
                # code decide whether to PICK one or self-host. Two symmetric
                # searchers that both self-host are not a deadlock to engineer
                # around - the client's search cadence uses a randomized
                # 1+2*rand() backoff (FUN_003b6c78 @0x3b6d64), so the two
                # rotations drift apart and one ends up hosting (in SERVER_LOBBY)
                # while the other is searching, at which point the searcher sees
                # the host in this list and joins. Convergence is w.p. 1 (§7 Q4).
                # A fabricated 2-member roster would NOT help: the SERVER_LOBBY
                # count is P2P-gated (FUN_003b19c4 counts a member only when its
                # connection handle at member+0xF0 reports state 2), so only a
                # real join produces a real, counted link.
                find_match_searching = True
                search_obj_ptr = (struct.unpack(">I", chunk[8:12])[0]
                                  if len(chunk) >= 12 else ROOM_PTR)
                # PLAYLIST / GAME MODE the client is queueing for, from
                # search_obj+0x0c (0x135 wire 12:16). Live: 0x02 = Supply Raid,
                # 0x03 = Survivors. This is the RELIABLE mode field - use it,
                # NOT the host's room_field_0c, which is not reliably reset and
                # has been observed stale (protos/0x12f_room_create.ksy).
                find_match_mode = (struct.unpack(">I", chunk[12:16])[0]
                                   if len(chunk) >= 16 else None)
                # GAME BUILD of the searcher. 0x135 wire offset 8 is the
                # client's search object, which is the SAME global as its game
                # room object (0x01383bd8 in 855/855 live 1.00 searches), so the
                # build fingerprint arrives with the search itself - no lazy
                # learning needed. build_of() returns None for an unrecognised
                # pointer, and None disables the filter rather than hiding
                # rooms, so an unknown build can never wedge matchmaking.
                find_match_build = build_of(search_obj_ptr)
                # Burst position marker: wire offset 0x18 u16 runs 5,10,10,0,0
                # across the five searches of one burst (live-captured), so 5
                # means "first search of a fresh burst" = criteria 0.
                marker = (struct.unpack(">H", chunk[0x18:0x1a])[0]
                          if len(chunk) >= 0x1a else 0)
                conn_key = id(conn)
                # NEVER-SEND rule: the ONLY thing we withhold is a 0x136 to a
                # connection that is ITSELF a live host. A 0x136 is written
                # through the searcher's search object, which for a host IS its
                # own room object (0x01383bd8), so answering would corrupt the
                # host's room. "Live host" is a registry membership test (between
                # its own 0x12f and 0x133), NEVER a timer - the old 10 s "abandon
                # grace" gated this on a clock and suppressed a 0x136 to a client
                # that was genuinely searching, hanging it for the full 60 s
                # GAME_LIST_WAIT timeout (root-cause note §5, divergence #2). A
                # live host is in SERVER_LOBBY and is not searching anyway; this
                # only guards the edge where a party host (room_ptr 0x01387f58)
                # searches on the game object (0x01383bd8).
                with rooms_lock:
                    # "Live host" = this connection owns a room whose room_ptr
                    # is the object it is searching on. Scans every room it
                    # owns now that a connection can own more than one.
                    live_host = any(h.get("room_ptr") == search_obj_ptr
                                    for h in rooms_owned_by(conn_key))
                    # MODE FILTER (2026-08-18). Without this the stub offered
                    # every public room to every searcher regardless of
                    # playlist - live-proven cross-match at 23:21:50: a
                    # Survivors searcher (mode 0x03) was handed a Supply Raid
                    # room (mode 0x02) and joined it. A room whose mode we never
                    # learned is still offered, so an unknown never makes a
                    # legitimate room unjoinable.
                    entries = [(info["room_id"], info)
                               for info in active_rooms.values()
                               if info.get("public") and info["conn"] is not conn
                               and len(info.get("members", []))
                               < info.get("max_players", 8)
                               # EXACT playlist match. No None tolerance here:
                               # a public room always carries a real playlist
                               # (see the "mode" tag at RoomCreate), so a None
                               # would be a bug, and offering it to everyone
                               # would leak one playlist into another - the
                               # thing this filter exists to prevent.
                               and (find_match_mode is None
                                    or info.get("mode") == find_match_mode)
                               and (find_match_build is None
                                    or info.get("build") in (None, find_match_build))]
                    filtered = [info for info in active_rooms.values()
                                if info.get("public") and info["conn"] is not conn
                                and find_match_mode is not None
                                and info.get("mode") != find_match_mode]
                    # CROSS-BUILD SEGREGATION (2026-08-19). Two game builds
                    # cannot play together - different code and content - so a
                    # 1.00 client must never be matched into a 1.11 room or
                    # vice versa. Nothing in the protocol carries a version
                    # (see research/notes/2026-08-18-version-segregation-via-
                    # netbin.md), but the client's own room-object pointer is a
                    # reliable build fingerprint, and unlike field_0c it is not
                    # stale-prone: it is the address the client is actually
                    # using this session.
                    wrong_build = [info for info in active_rooms.values()
                                   if info.get("public") and info["conn"] is not conn
                                   and info.get("build") is not None
                                   and find_match_build is not None
                                   and info["build"] != find_match_build]
                if live_host:
                    emit(f"   parsed opcode={opcode:#x} (find-match search, "
                         f"marker={marker}) - this connection is a LIVE HOST "
                         f"(between its own 0x12f and 0x133); NOT sending a "
                         f"0x136 (its search object is its room object)")
                else:
                    conn.sendall(build_room_search(search_obj_ptr, entries))
                    emit(f"   parsed opcode={opcode:#x} (find-match search, "
                         f"marker={marker}) - sent RoomSearch (0x136) listing "
                         f"{len(entries)} public game(s) "
                         f"[{', '.join(rid.hex() for rid, _ in entries) or 'none'}], "
                         f"search_obj_ptr={search_obj_ptr:#x}")
                    if wrong_build:
                        emit(f"   [build] withheld {len(wrong_build)} public "
                             f"room(s) from this searcher - wrong game build "
                             f"(searcher={find_match_build}, rooms="
                             f"{[i.get('build') for i in wrong_build]})")
                    if filtered:
                        emit(f"   [playlist] withheld {len(filtered)} public "
                             f"room(s) - wrong playlist. Searcher wants "
                             f"{find_match_mode} "
                             f"({playlist_name(find_match_mode, find_match_build)});"
                             f" rooms are "
                             f"{[(i.get('mode'), playlist_name(i.get('mode'), i.get('build'))) for i in filtered]}")
            elif opcode == ROOM_LEAVING_OPCODE and len(chunk) >= 16:
                # No reply - confirmed fire-and-forget, see the constant's
                # docstring. This firing means the client just gave up on
                # and abandoned this room on its own initiative.
                room_id_tail = chunk[8:16]
                emit(f"   parsed opcode={opcode:#x} (client abandoning room, "
                     f"room_id={room_id_tail.hex()}) - no reply (confirmed "
                     f"fire-and-forget)")
                # Stop this room's Member refresher now, not just at
                # connection-close - otherwise it keeps re-writing
                # ROOM_PTR+0x10 nonzero forever on this still-open
                # connection, pinning the RoomJoined id-gate mismatched for
                # every subsequent "host again" attempt (2026-08-16, see
                # active_room_stop's docstring above).
                if active_room_stop is not None:
                    active_room_stop.set()
                    active_room_stop = None
                # NO GRACE (2026-08-17, root-cause note §4 "Prerequisite
                # fixes"): the room and its `public` flag are dropped the
                # INSTANT the host abandons. The old 10 s abandon grace kept
                # the flag set, and the 0x135 branch read that same flag to
                # decide whether the sender was "already a public HOST" - so a
                # client that had abandoned its room 4.8 s earlier and was
                # genuinely searching got NO 0x136 and hung for the full 60 s
                # GAME_LIST_WAIT timeout, which is what destroyed the last run.
                # Host liveness is now strictly "between its 0x12f and its
                # 0x133", never a timer.
                dropped_public = False
                closing = None
                with rooms_lock:
                    # Only the room this 0x133 names - rooms this connection
                    # owns under other ids stay alive (a client leaving its
                    # GAME room is still in its PARTY room).
                    info = active_rooms.get((id(conn), room_id_tail))
                    if info is None:
                        # Tolerate an id mismatch on a public room: its id is
                        # stub-synthesized, so if the client's own local copy
                        # ever diverges we still must retire the room rather
                        # than leave a zombie host in the list.
                        for k in room_keys_owned_by(id(conn)):
                            if active_rooms[k].get("public"):
                                info = active_rooms[k]
                                emit(f"   (0x133 room_id {room_id_tail.hex()} != "
                                     f"registered {info['room_id'].hex()} - retiring "
                                     f"this connection's public room anyway)")
                                break
                    if info is not None:
                        dropped_public = bool(info.get("public"))
                        del active_rooms[(id(conn), info["room_id"])]
                        closing = info
                if closing is not None:
                    # THE OWNER IS LEAVING. Tell whoever is still in the room
                    # instead of dropping it silently - a survivor left holding
                    # a forgotten room gets no keepalive and no peer, which is
                    # the documented road to a null room id and a trap. See
                    # build_room_closed. (This also retires the cached blobs.)
                    close_room_and_notify(closing, "owner left (0x133)",
                                          exclude_key=id(conn))
                stop_member_refresher(id(conn))
                if dropped_public:
                    emit(f"   (public host room {room_id_tail.hex()} abandoned - "
                         f"dropped from the find-match list IMMEDIATELY, no "
                         f"grace; this connection is no longer a host and will "
                         f"be answered normally if it searches again)")
                # If this connection had JOINED someone else's room with this
                # id, notify the remaining members (0x134) and shrink their
                # refresher roster. reseed_party: this is a LIVE connection
                # leaving under its own steam, and its 0x133 sender has just
                # zeroed its party object's +0x10 (0x00ad66e0) while leaving
                # +0xb8 set - hand it a fresh party room id so the next Join
                # Party is not gated out at 0x00354f54. See
                # reseed_departed_party.
                broadcast_member_departure(id(conn), room_id=room_id_tail,
                                           reseed_party=True)
            elif opcode == CREATE_PARTY_OPCODE and len(chunk) >= 16:
                # RE-CORRECTED 2026-08-16: this is SetPartyData - the client
                # pushing its own <=64-byte per-member data blob for a room
                # (the 2026-08-15 "periodic telemetry" reading was about the
                # unrelated caller loop, not this message's content). It is
                # the natural client->server supplier for the 0x13b
                # per-member blob delivery (same 80-byte size, same 64-byte
                # payload cap, member-scoped - see build_member_blob's
                # docstring). Relay it to every member of the room it names
                # so all clients hold all members' data (rank display /
                # peer-consistency theory).
                room_id_tail = chunk[8:16]
                entry = None
                targets = []
                sender_member_id = None
                with rooms_lock:
                    for info in active_rooms.values():
                        if id(conn) in info.get("conns", {}) and info["room_id"] == room_id_tail:
                            entry = info
                            break
                    if entry is None:
                        for info in active_rooms.values():
                            if id(conn) in info.get("conns", {}):
                                entry = info
                                break
                    if entry is not None:
                        sender_member_id = entry["conns"][id(conn)][0]
                        targets = list(entry["conns"].values())
                if entry is None or len(chunk) < 80:
                    emit(f"   parsed opcode={opcode:#x} (SetPartyData, "
                         f"room_id={room_id_tail.hex()}) - sender not in any "
                         f"registered room (or short packet, {len(chunk)}b), "
                         f"no relay")
                else:
                    # CORRECTED 2026-08-17: the client's own declared blob
                    # length is the byte at wire offset 4 (live-constant 0x20
                    # = 32). Forwarding the old fixed chunk[16:80] (64 bytes)
                    # made every relay fail FUN_00ad2650's `length == 32` gate
                    # - the whole feature silently no-op'd. Use the real
                    # length so member_slot+0xF8 == 32 and the UI accepts it.
                    blob_len = chunk[4]
                    payload = chunk[16:16 + blob_len]
                    with rooms_lock:
                        member_blobs[(entry["room_id"], sender_member_id)] = payload
                    blob = build_member_blob(sender_member_id, entry["room_id"], payload)
                    sent = 0
                    for mid, c, em in targets:
                        # Don't echo a member's blob back to itself - the local
                        # read path uses room_obj+0x19FC, not the member slot.
                        if mid == sender_member_id:
                            continue
                        try:
                            c.sendall(blob)
                            sent += 1
                        except OSError:
                            pass
                    emit(f"   parsed opcode={opcode:#x} (SetPartyData from "
                         f"member_id={sender_member_id}, len={blob_len}) - "
                         f"cached + relayed as 0x13b blob to {sent} other "
                         f"member connection(s) of room {entry['room_id'].hex()}")
            elif opcode == KICKOUT_OPCODE and len(chunk) >= 16:
                # KICK FROM PARTY - wired up 2026-08-17 (was log-only after the
                # self-kick root-cause fix; see build_kickedout). The client
                # that clicks "Kick from Party" sends this Kickout. 0x138
                # (Kickedout) is what actually removes someone - route it to the
                # TARGET member's connection ONLY, NEVER echo to the sender
                # (that was the collapse bug). Payload: opcode(4) | target
                # member_id u16 @+4 | requester u16 @+6 | room_id(8) @+8.
                target_member_id = struct.unpack(">H", chunk[4:6])[0]
                requester_member_id = struct.unpack(">H", chunk[6:8])[0]
                room_id_tail = chunk[8:16]
                if requester_member_id == 0:
                    # NOT a user kick. requester=0 means there is NO requesting
                    # member - an AUTOMATIC removal request. Two sources
                    # (protos/0x137_kickout.ksy): the join flow (0.01-0.17 s
                    # after a RoomJoin - acting on it kicked the joiner,
                    # "Unable to join party / You were kicked") and a host
                    # whose P2P layer has noticed a dead peer (29.7-642.6 s
                    # after any join). We act ONLY on the second kind, and only
                    # when the target's own connection independently proves it
                    # is gone - see evaluate_late_dead_peer_removal.
                    target, dead_room_id, why = evaluate_late_dead_peer_removal(
                        id(conn), target_member_id, room_id_tail)
                    if target is None:
                        emit(f"   parsed opcode={opcode:#x} (0x137 requester=0, "
                             f"target={target_member_id}, "
                             f"room_id={room_id_tail.hex()}) - automatic removal "
                             f"request IGNORED: {why}")
                        continue
                    tkey, tmid, tconn, tem = target
                    emit(f"   parsed opcode={opcode:#x} (0x137 requester=0, "
                         f"target={target_member_id}, "
                         f"room_id={room_id_tail.hex()}) - *** ACTING ON LATE "
                         f"DEAD-PEER REMOVAL *** ({why}); removing member_id="
                         f"{tmid} from room {dead_room_id.hex()}")
                    try:
                        # Best effort only - the target is believed dead. If it
                        # is merely hung and later revives, this is the same
                        # 0x138 the genuine-kick path sends, so it leaves
                        # cleanly instead of resurrecting into a stale roster.
                        tconn.sendall(build_kickedout(dead_room_id))
                        tem(f"   [dead-peer] member_id={tmid} removed - sent "
                            f"Kickedout (0x138) to this member only "
                            f"(best effort; target believed dead)")
                    except OSError as e:
                        emit(f"   [dead-peer] 0x138 to member_id={tmid} failed "
                             f"({e}) - expected for a dead socket, continuing")
                    broadcast_member_departure(tkey, room_id=dead_room_id)
                    continue
                room_entry, target = None, None
                with rooms_lock:
                    for info in active_rooms.values():
                        if id(conn) in info.get("conns", {}) and info["room_id"] == room_id_tail:
                            room_entry = info
                            break
                    if room_entry is not None:
                        for mid, c, em in room_entry["conns"].values():
                            if mid == target_member_id:
                                target = (mid, c, em)
                                break
                if room_entry is None:
                    emit(f"   parsed opcode={opcode:#x} (Kickout target="
                         f"{target_member_id}, room_id={room_id_tail.hex()}) - "
                         f"sender not in a matching room, no action")
                elif not sender_is_room_owner(room_entry, conn):
                    # Only the party leader may kick. See sender_is_room_owner.
                    emit(f"   parsed opcode={opcode:#x} (Kickout target="
                         f"{target_member_id}, room_id={room_id_tail.hex()}) - "
                         f"REJECTED: sender member_id="
                         f"{room_entry['conns'][id(conn)][0]} is not the room "
                         f"owner (member_id="
                         f"{room_entry.get('owner_member_id', MEMBER_ID)}), "
                         f"no action")
                elif target is None:
                    emit(f"   parsed opcode={opcode:#x} (Kickout) - target "
                         f"member_id={target_member_id} not in room "
                         f"{room_entry['room_id'].hex()}, no action")
                else:
                    mid, tconn, tem = target
                    try:
                        tconn.sendall(build_kickedout(room_entry["room_id"]))
                        tem(f"   [kick] member_id={mid} kicked - sent Kickedout "
                            f"(0x138) to this member only")
                    except OSError:
                        pass
                    emit(f"   parsed opcode={opcode:#x} (Kickout) - removed "
                         f"member_id={target_member_id} from room "
                         f"{room_entry['room_id'].hex()}: 0x138 to target, 0x134 "
                         f"to the rest")
                    # reseed_party=True: a kicked member's own 0x138 handler
                    # (@0x00ad7f28) runs the same client-side LeaveRoom
                    # teardown as a voluntary 0x133 leave, so it ends up with
                    # the same zeroed party_obj+0x10 the rejoin-party fix
                    # addresses (see reseed_departed_party) - without this, a
                    # kicked party member would be stuck unable to rejoin
                    # anyone's party afterward, same symptom as the original
                    # bug report. UNLIKE the voluntary-leave case, this
                    # reseed is SERVER-INITIATED and races the target's own
                    # processing of the 0x138 we just sent it (a voluntary
                    # leaver has already finished its local teardown by the
                    # time its 0x133 reaches us; a kicked member has NOT yet
                    # processed our 0x138 at the moment we send this). Not
                    # live-tested - if kicked members report the same
                    # "Join" symptom as the original bug, or a NEW symptom
                    # (garbled party state right after being kicked),
                    # suspect this race first.
                    broadcast_member_departure(id(tconn), room_id=room_entry["room_id"],
                                               reseed_party=True)
            elif opcode == PROMOTE_OPCODE and len(chunk) >= 16:
                # PROMOTE TO PARTY LEADER - wired up 2026-08-17. Payload
                # (live-decoded): opcode(4) | new_owner member_id u16 @+4 |
                # (u16 @+6 uninitialised) | room_id(8) @+8. Make every client
                # agree on the new leader: OwnerMember (0x13d) sets
                # room_obj+0x19f0 (owner member id) everywhere; HostFlagUpdated
                # (0x13f) carries the "am I host" flag for room_obj+0x19f4,
                # whose value depends on the room type - see the flag rule
                # below, which is NOT simply "1 for the new leader". Both
                # opcodes are already used in the working join flow.
                new_owner_id = struct.unpack(">H", chunk[4:6])[0]
                room_id_tail = chunk[8:16]
                room_entry = None
                with rooms_lock:
                    for info in active_rooms.values():
                        if id(conn) in info.get("conns", {}) and info["room_id"] == room_id_tail:
                            room_entry = info
                            break
                    conns = list(room_entry["conns"].values()) if room_entry else []
                if room_entry is None:
                    emit(f"   parsed opcode={opcode:#x} (Promote target="
                         f"{new_owner_id}, room_id={room_id_tail.hex()}) - "
                         f"sender not in a matching room, no action")
                elif not sender_is_room_owner(room_entry, conn):
                    # Only the current leader may hand leadership on. See
                    # sender_is_room_owner.
                    emit(f"   parsed opcode={opcode:#x} (Promote target="
                         f"{new_owner_id}, room_id={room_id_tail.hex()}) - "
                         f"REJECTED: sender member_id="
                         f"{room_entry['conns'][id(conn)][0]} is not the room "
                         f"owner (member_id="
                         f"{room_entry.get('owner_member_id', MEMBER_ID)}), "
                         f"no action")
                else:
                    # Move the authoritative leader before announcing it, so a
                    # later Kickout/Promote is judged against the new owner -
                    # the same value 0x13d publishes as room_obj+0x19f0.
                    with rooms_lock:
                        room_entry["owner_member_id"] = new_owner_id
                    owner_msg = build_owner_member(room_entry["room_id"], new_owner_id)
                    # room_obj+0x19f4 ("host flag") is separate from the
                    # +0x19f0 owner id OwnerMember just set. On a PARTY room
                    # it is published verbatim into presence (blob offset 7)
                    # and hides "Join Party" on that host's friends-list row
                    # whenever it is nonzero - see build_owner_changed and
                    # research/notes/2026-08-20-rejoin-party-bug.md section 4.
                    # Promote only ever targets party rooms (it elects a new
                    # PARTY leader; leadership itself is +0x19f0, already
                    # handled by OwnerMember above), so every recipient keeps
                    # flag=0 there, new leader included - mirroring RoomCreate
                    # rather than reproducing the fixed bug for a fresh victim.
                    is_party = is_party_ptr(room_entry.get("room_ptr", 0))
                    sent = 0
                    for mid, c, em in conns:
                        try:
                            c.sendall(owner_msg)
                            flag = 0 if is_party else (1 if mid == new_owner_id else 0)
                            c.sendall(build_owner_changed(
                                room_entry["room_id"], joined_flag=flag))
                            sent += 1
                        except OSError:
                            pass
                    emit(f"   parsed opcode={opcode:#x} (Promote) - new leader "
                         f"member_id={new_owner_id} in room "
                         f"{room_entry['room_id'].hex()}: OwnerMember(0x13d)+"
                         f"HostFlagUpdated(0x13f) to {sent} member(s)")
            elif opcode == SET_ROOM_FLAGS_OPCODE and len(chunk) >= 16:
                flags_value = chunk[4:8]
                room_id_tail = chunk[8:16]
                reply = struct.pack(">I", UPDATED_ROOM_FLAGS_OPCODE) + flags_value + room_id_tail
                conn.sendall(reply)
                emit(f"   parsed opcode={opcode:#x} (SetRoomFlags, flags={flags_value.hex()}) - "
                     f"sent UpdatedRoomFlags (16 bytes) echoing flags+room_id="
                     f"{room_id_tail.hex()}\n{hexdump(reply)}")
            elif opcode == SET_ROOM_DATA_BLOCK_OPCODE and len(chunk) >= 144:
                room_id_tail = chunk[8:16]
                data_block = chunk[16:144]
                reply = (struct.pack(">I", ROOM_DATA_BLOCK_UPDATED_OPCODE) + chunk[4:8]
                          + room_id_tail + data_block)
                conn.sendall(reply)
                emit(f"   parsed opcode={opcode:#x} (SetRoomDataBlock, "
                     f"room_id={room_id_tail.hex()}) - sent RoomDataBlockUpdated "
                     f"(144 bytes) echoing the same 128-byte payload back"
                     f"\n{hexdump(reply)}")
            elif opcode == PING_OPCODE:
                emit(f"   parsed opcode={opcode:#x} (Ping keepalive) - "
                     f"no reply sent, appears fire-and-forget (client-side timer driven)")
            elif opcode == CLIENT_HELLO2_OPCODE:
                emit(f"   parsed opcode={opcode:#x} (ClientHello2) - no reply expected "
                     f"(Init() sends this and moves on without waiting)")
            elif opcode is not None:
                emit(f"   parsed opcode={opcode:#x} - unhandled, no reply sent")
    except (ConnectionError, socket.timeout, OSError) as e:
        emit(f"  (error/early close: {e})")
    finally:
        stop_event.set()
        if active_room_stop is not None:
            active_room_stop.set()
        stop_member_refresher(id(conn))
        with rooms_lock:
            # A connection can own SEVERAL rooms (party + game), so retire all
            # of them - and keep them so their survivors can be told. Blob
            # purging happens in close_room_and_notify.
            closing = []
            for k in room_keys_owned_by(id(conn)):
                closing.append(active_rooms.pop(k))
        for info in closing:
            # THE OWNER'S SOCKET DIED (client crash, VM death, network drop).
            # Previously this deleted the room and told the remaining members
            # NOTHING, orphaning them on a room the server had forgotten.
            close_room_and_notify(info, "owner connection closed",
                                  exclude_key=id(conn))
        broadcast_member_departure(id(conn))
        with rooms_lock:
            # Drop this connection's liveness record - id(conn) is only unique
            # while the object is alive, so a stale entry could otherwise be
            # inherited by a future connection at the same address.
            last_inbound_ts.pop(id(conn), None)
        conn.close()


def drain_rooms_for_shutdown(reason="server shutting down"):
    """Tell every client its rooms are gone, BEFORE the process exits.

    A client has NO reconnect path for the session-manager connection: it is
    opened once by SessionManager::Init (FUN_00ad71a0, connect @0x00ad728c) when
    the player enters the Multiplayer menu, and nothing re-drives it during a
    healthy session (research/notes/2026-08-18-session-manager-connect-and-
    reconnect.md). Worse, the death is SILENT client-side - recv()==0 returns
    with no log, no close, and the client keeps sending its 30 s 0x145 keepalive
    into the dead socket forever, only surfacing an error if it happens to hit
    one of the screen handlers that consume the network-error flag.

    Live consequence (2026-08-18): after a restart, one client was booted and
    recovered, while the other sat in the main menu looking fine for six
    minutes with a dead connection, and had to re-enter multiplayer by hand.

    We cannot make a client reconnect - that is proven, no server-reachable
    trigger exists. What we CAN do is not leave it holding a room we have
    forgotten: 0x134 RoomLeave + 0x139 RoomClosed drive the client's own
    teardown, so the room object is invalidated properly rather than rotting
    into a null room id. Best-effort and exception-guarded: shutdown must not
    hang or throw.
    """
    with rooms_lock:
        entries = list(active_rooms.values())
        active_rooms.clear()
    if not entries:
        return 0
    print(f"{_ts()} draining {len(entries)} room(s) before exit ({reason})",
          flush=True)
    for info in entries:
        try:
            # 2s, not the connection's normal 600s operational timeout - see
            # close_room_and_notify's notify_timeout doc. Bounds the whole
            # drain to a couple seconds per stale connection instead of
            # minutes, so the process actually exits on SIGTERM/SIGINT.
            close_room_and_notify(info, reason, notify_timeout=2.0)
        except Exception as e:      # never let shutdown die on a dead socket
            print(f"{_ts()}   drain of room "
                  f"{info.get('room_id', b'').hex()} failed: {e}", flush=True)
    return len(entries)


def _install_shutdown_handlers():
    def _bye(signum, _frame):
        drain_rooms_for_shutdown(f"server shutting down (signal {signum})")
        sys.exit(0)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _bye)
        except (ValueError, OSError):
            pass        # not on the main thread / unsupported platform


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    _install_shutdown_handlers()
    print(f"{_ts()} Session Manager stub listening on 0.0.0.0:{PORT}, "
          f"logging to {LOG_PATH}, max {MAX_CONCURRENT_HANDLERS} concurrent "
          f"handlers", flush=True)

    log_lock = threading.Lock()
    with RotatingLog(LOG_PATH) as log:
        while True:
            # Gate ACCEPT on the semaphore, not just the handler thread - see
            # MAX_CONCURRENT_HANDLERS.
            _handler_slots.acquire()
            conn, addr = srv.accept()
            conn = _TapSock(conn, _next_cid())   # raw wire tap (both directions)
            t = threading.Thread(target=serve, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
