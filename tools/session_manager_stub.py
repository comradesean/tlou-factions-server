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
import sys
import datetime
import threading
import struct
import os
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7314
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/tcp_catch.log"

CLIENT_HELLO_OPCODE = 0x12d
SERVER_HELLO_OPCODE = 0x12e
ROOM_CREATE_OPCODE = 0x12f
MEMBER_OPCODE = 0x131
ROOM_JOINED_OPCODE = 0x132
OWNER_CHANGED_OPCODE = 0x13f
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
# NetMatchmakingSetAttrFlags (0x140) / NetMatchmakingUpdatedAttrFlags (0x141).
# Live-captured 2026-08-15 for the first time ever this session - only
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
SET_ATTR_FLAGS_OPCODE = 0x140
UPDATED_ATTR_FLAGS_OPCODE = 0x141
# NetMatchmakingUpdatedRoomFlags (declared name, but client->server despite
# the name - see docs/protocol/session_manager_and_matchmaking.md row 22):
# 144 bytes, opcode + room_id(8) + a 128-byte verbatim copy of the client's
# own room_obj+0x18 region. Never handled by this stub before 2026-08-16 -
# confirmed via live Ghidra dispatch-case decompile that its counterpart,
# 0x144/HostRank (server->client, same 128 bytes written back into that same
# room_obj+0x18 region on receipt), is a message the real server would have
# sent and ours never has. Following this project's established "echo the
# client's own data back" pattern (RoomSearchResult/0x138 echoing
# RoomSearchInfo/0x137, UpdatedAttrFlags/0x141 echoing SetAttrFlags/0x140) -
# EXPERIMENTAL, not yet live-tested. See
# research/notes/2026-08-16-net-sm-server-lobby-dispatch.md and follow-ups.
UPDATED_ROOM_FLAGS_OPCODE = 0x143
HOST_RANK_OPCODE = 0x144
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

# Cross-connection find-match pairing state (2026-08-15). The stub is
# otherwise stateless per-connection - with two independent real RPCN
# accounts both sitting in "Find Match" simultaneously, neither could ever
# find the other since nothing tied their connections together. Single-slot
# waiting room: first searcher to arrive registers here and waits; the next
# *different* searcher pairs with whoever is waiting and both get pushed a
# real 2-member RoomJoined+Member pair. Guarded by waiting_lock since each
# connection runs in its own thread.
waiting_lock = threading.Lock()
waiting_player = None

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
active_rooms = {}

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
# SERIALIZED HOST/JOINER ELECTION (2026-08-17)
# ---------------------------------------------------------------------------
# See research/notes/2026-08-17-find-match-coordination-root-cause.md §4. Two
# clients pressing Find Match both self-elect host (each searches, gets an
# empty list, self-hosts) and neither is ever a plain joiner - with a ~12 s
# host window inside a ~23 s matchmaking cycle, unassisted rendezvous is a coin
# flip. The stub therefore SERIALIZES the two roles:
#
#   * the FIRST connection to search becomes HOST-ELECT (A). Every one of its
#     0x135s in the burst is answered with an EMPTY 0x136 so it exhausts its 5
#     searches (~9-11 s) and self-hosts.
#   * every OTHER searcher is PARKED: it gets NO 0x136 at all, so it blocks in
#     NET_SM_CLIENT_GAME_LIST_WAIT and stops sending 0x135s. Parking is free -
#     the client is happy to wait; its hard timeout is 60.0 s (float
#     0x01269c48, FUN_003b4bf4 @ 0x3b4d10) after which it shows an error
#     dialog, so we never hold longer than ELECTION_HOLD_CAP_SECONDS.
#   * the instant A's 0x12f RoomCreate lands, every parked joiner is RELEASED
#     with a ONE-entry 0x136 naming A's room (a stub-synthesized unique room id
#     - both clients literally send the same heap pointer 0x01383bd8, so the
#     registry must never be keyed on the raw client value) and A's real NpId.
#   * if the joiner's 0x130 RoomJoin does not arrive within
#     ELECTION_JOIN_WATCHDOG_SECONDS the election is abandoned (A tears its own
#     lobby down at t(0x12f) + 12.0 s anyway) and the next 0x135 starts a fresh
#     election - roles may swap, which is fine.
#
# Timings below are all from the disassembly table in §3 of that note.

# Client's GAME_LIST_WAIT hard timeout is 60.0 s -> error dialog + LEAVE_GAME.
# Never hold a 0x136 anywhere near that long.
ELECTION_HOLD_CAP_SECONDS = 40.0
# A's lobby teardown fires at t(0x12f) + 8.0 + lobbyWaitTable[1] = 12.0 s. The
# reference (working) PICK -> CONNECT_TO_HOST -> RESERVE -> 0x130 path took
# 0.17 s, so 9 s is a very generous budget that still leaves A alive.
ELECTION_JOIN_WATCHDOG_SECONDS = 9.0
# If the host-elect never reaches RoomCreate (backed out to the menu, crashed,
# ...) release the parked joiners rather than sitting on them.
ELECTION_CREATE_TIMEOUT_SECONDS = 35.0

# The single in-flight election, or None. Guarded by election_lock (an RLock:
# the release path calls back into helpers that re-take it).
election_lock = threading.RLock()
election = None
_election_gen = [0]

# Stub-synthesized PUBLIC room ids. RoomCreate's own wire offset 4:12 is
# `00000000 01383bd8` on EVERY client (offset 4:8 is uninitialised stack,
# offset 8:12 is the statically-allocated game-room object) - so two hosts
# collide exactly. For find-match/public rooms we mint our own id instead:
# high word = a monotonic sequence tagged 0x5-, low word = the client's own
# room_ptr (keeps it nonzero and recognisable). The client stores whatever we
# put in Member's wire 16:24 into room_obj+0x10 and echoes it back to us in
# 0x133 / 0x137 / 0x140 / 0x13a (live-confirmed), and the P2P reserve reply
# carries it to the joiner, so the joiner's 0x130 names this same value.
_public_room_seq = [0]


def synth_public_room_id(room_ptr):
    """Mint a globally-unique 8-byte room id for a public (find-match) room."""
    with election_lock:
        _public_room_seq[0] += 1
        seq = _public_room_seq[0]
    return struct.pack(">II", 0x50000000 | (seq & 0x0fffffff), room_ptr & 0xffffffff)


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
              (PPU Trap at 0x00ad38b8, live-confirmed). Now sourced from
              RoomCreate's own wire offset 0x1e (2 bytes, captured live as
              `00 0a` = 10) - the room's own declared max-player count is
              the obvious source of truth for a "capacity" field.
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
              NOT change observed behavior - the user still hit the same
              3-attempt pattern (id-gate fail -> brief match then silent
              drop -> permanent NET_SM_SERVER_LOBBY stall) with this field
              populated. Reverted to zero. The real blocker is more likely
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


# ---------------------------------------------------------------------------
# Election state machine helpers
# ---------------------------------------------------------------------------
# States (election["state"]):
#   "electing" - A has searched, has NOT yet sent its 0x12f. A's 0x135s get an
#                EMPTY 0x136; everyone else parks (no reply at all).
#   "hosting"  - A's 0x12f landed, parked joiners were released with a 1-entry
#                0x136. Waiting for a joiner's 0x130 (watchdog armed).
#   "joined"   - a joiner's 0x130 landed and both sides hold the real 2-member
#                roster. New searchers get the ordinary public list.
# The election is torn down by: A's 0x133, A's socket close, the create
# timeout, or the join watchdog.


def _send_room_search(target, search_obj_ptr, entries, tag, why):
    """Send a 0x136 to one parked/searching connection. Never called for a live
    host - a 0x136 writes through the searcher's search object, which for a
    host IS its room object (0x01383bd8)."""
    try:
        target["conn"].sendall(build_room_search(search_obj_ptr, entries))
        target["emit"](f"   [{tag}] {target['npid']!r} <- 0x136 with "
                       f"{len(entries)} entry(s) ({why})")
        return True
    except OSError as e:
        target["emit"](f"   [{tag}] {target['npid']!r} send failed: {e}")
        return False


def election_abandon(reason, emit=None):
    """Tear the current election down and release anyone still parked with an
    EMPTY list (so they self-host and can win the NEXT election)."""
    global election
    with election_lock:
        e = election
        if e is None:
            return
        election = None
        for t in e.get("timers", []):
            t.cancel()
        e["timers"] = []
        stranded = [j for j in e["joiners"].values() if not j.get("released")]
        for j in stranded:
            j["released"] = True
            if j.get("cap_timer") is not None:
                j["cap_timer"].cancel()
    (emit or e["host_emit"])(
        f"   [watchdog] abandon election host={e['host_npid']!r} "
        f"state={e['state']}: {reason} "
        f"(releasing {len(stranded)} parked searcher(s) with an empty list)")
    for j in stranded:
        _send_room_search(j, j["search_obj_ptr"], [], "release",
                          f"election abandoned: {reason}")


def _election_create_timeout(gen):
    with election_lock:
        if election is None or election["gen"] != gen or election["state"] != "electing":
            return
    election_abandon(f"host-elect never reached RoomCreate within "
                     f"{ELECTION_CREATE_TIMEOUT_SECONDS:.0f}s")


def _election_join_watchdog(gen):
    with election_lock:
        if election is None or election["gen"] != gen or election["state"] != "hosting":
            return
    election_abandon(f"no 0x130 RoomJoin within "
                     f"{ELECTION_JOIN_WATCHDOG_SECONDS:.0f}s of the host's 0x12f "
                     f"(host tears its own lobby down at 12.0s)")


def _election_park_cap(gen, conn_key):
    """HARD CAP: a parked joiner has been holding a 0x136 for
    ELECTION_HOLD_CAP_SECONDS. The client's own hard timeout is 60.0 s and ends
    in an error dialog, so let it go with an empty list well before that."""
    with election_lock:
        if election is None or election["gen"] != gen:
            return
        j = election["joiners"].get(conn_key)
        if j is None or j.get("released"):
            return
        j["released"] = True
        j["capped"] = True
    _send_room_search(j, j["search_obj_ptr"], [], "release",
                      f"{ELECTION_HOLD_CAP_SECONDS:.0f}s hold cap expired - "
                      f"letting it self-host")


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


def broadcast_member_departure(departing_key, room_id=None):
    """A joined connection left (0x133 or socket close): remove it from any
    room it was a member of, tell the remaining members via 0x134, and
    restart the room owner's refresher with the shrunken roster so the
    departed member stops being re-registered every interval."""
    affected = []
    with rooms_lock:
        for other in active_rooms.values():
            if departing_key in other.get("conns", {}) and (
                    room_id is None or other["room_id"] == room_id):
                mid = other["conns"].pop(departing_key)[0]
                if id(other["conn"]) == departing_key:
                    continue  # room owner leaving - entry teardown handles it
                other["members"] = [m for m in other.get("members", [])
                                    if m[0] != mid]
                # Drop the departed member's cached blob so it is not replayed
                # to a future joiner of this (shared-id) room.
                member_blobs.pop((other["room_id"], mid), None)
                affected.append((other, mid))
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


def build_owner_changed(room_id, is_owner=1):
    """Build a NetMatchmakingOwnerChanged (opcode 0x13f), 16 bytes.

    2026-08-16 dispatch audit finding #1 (see research/notes/2026-08-16-
    sessmgr-dispatch-audit-and-unsent-opcodes.md 2): RoomCreate's own sender
    unconditionally CLEARS the client's "I am the host" flag
    (room_obj+0x19f4), and this message's handler (0xad8264-0xad82d0) is the
    only inbound writer of that flag - so a solo host that never receives
    this never becomes the host, and three game-layer readers (including the
    9-state room state machine at _opd_FUN_003ca9d0) gate on it.

    Layout: opcode(4) | is_owner_byte(1) | unused(3) | room_id(8).
    The handler searches the 4 room slots for room_obj+0x10 == wire[8:16]
    before writing wire[4] & 1 - room_obj+0x10 is only set by Member's
    handler, so this MUST be sent after Member or it is silently swallowed.
    """
    body = bytearray(16)
    struct.pack_into(">I", body, 0, OWNER_CHANGED_OPCODE)
    body[4] = is_owner & 1
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
    # *** RE-REVIEW AFTER FULL 2-PLAYER FLOW WORKS (flagged 2026-08-16) ***
    # This multi-member skip fixed a CONFIRMED live bug (see below) but rests on
    # a single live observation. Open question: does a multi-member room's
    # room_obj+0x10 stay alive without our periodic re-assertion, or will it go
    # stale (the original reason the refresher existed for solo)? P2P
    # MUTUAL_ACTIVATED suggests the party self-maintains, but that was not
    # verified over a long-lived multi-member session. Re-validate once the full
    # flow is stable; if multi-member rooms DO go stale, the right fix is a
    # much longer interval or a room_obj+0x10-only keepalive, not full-roster
    # re-broadcast. Do not treat this skip as settled.
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
    if room_ptr == PARTY_ROOM_PTR:
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


def handle(conn, addr, log_lock, log):
    global waiting_player, election
    ts = datetime.datetime.now().isoformat()

    def emit(text):
        # Write immediately rather than batching until the connection closes -
        # this is a long-lived control connection now (see settimeout(600)
        # below), so waiting for close to log anything left us blind to
        # mid-connection activity while debugging "Lobby Server Error" live
        # on 2026-08-14.
        with log_lock:
            print(text, flush=True)
            log.write(text + "\n")
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
                max_players = struct.unpack(">H", chunk[0x24:0x26])[0] or 8
                room_ptr = struct.unpack(">I", chunk[8:12])[0]
                # 8-byte room identity echoed into Member wire 16:24 and the
                # RoomJoined id-gate - kept as chunk[4:12] for continuity even
                # though the audit shows offset 4:8 is never client-written
                # (the value only needs to be nonzero and session-consistent;
                # its low half is the room_ptr, guaranteeing nonzero).
                room_id = chunk[4:12]
                # UNIQUE PUBLIC ROOM ID (2026-08-17, coordination root-cause
                # note §4): chunk[4:12] is `00000000 01383bd8` on every client,
                # so two find-match hosts collide byte-for-byte and the
                # cross-connection registry cannot tell them apart (and the
                # 0x136 game list would advertise an ambiguous join key). Mint
                # our own for public rooms only - private/custom and party
                # rooms keep the historical value so the live-confirmed
                # solo-host and invite-to-party paths are untouched.
                if find_match_searching:
                    room_id = synth_public_room_id(room_ptr)
                # RoomCreate's own wire offset 0xc:0x10 (4 bytes) - live-
                # evidenced 2026-08-15 as a likely map/level identifier, see
                # build_room_joined's docstring. Echo it straight back.
                map_id = chunk[0xc:0x10]
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

                # EXPERIMENTAL (2026-08-16, dispatch audit proposal #4, applied
                # after the OwnerChanged-alone test still hit the team assert):
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
                                       populate_self_npid=True)
                # EXPERIMENTAL (2026-08-16, dispatch audit finding #1): the
                # client's RoomCreate sender clears its own "I am the host"
                # flag and only 0x13f can set it - without this a solo host
                # never becomes the host (see build_owner_changed's
                # docstring). Must come after Member in the write.
                owner_changed = build_owner_changed(room_id, is_owner=1)
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
                time.sleep(0.25)
                conn.sendall(member + owner_changed
                             + build_owner_member(room_id, MEMBER_ID))
                emit(f"   parsed opcode={opcode:#x} (RoomCreate, map_id={map_id.hex()}), sent "
                     f"Member+OwnerChanged+OwnerMember as one write, NO RoomJoined "
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
                    old_entry = active_rooms.get(id(conn))
                    if old_entry is not None:
                        # A joint-roster refresher started by the 0x130 join
                        # handler holds a NEWER stop_event than this thread's
                        # local active_room_stop - stop it via the registry
                        # so it can't outlive its room.
                        old_entry["stop_event"].set()
                    active_rooms[id(conn)] = {
                        "npid": npid, "conn": conn, "emit": emit,
                        "room_id": room_id, "room_ptr": room_ptr,
                        "max_players": max_players,
                        "stop_event": active_room_stop,
                        # member_id -> connection map for per-room broadcast
                        # (0x13a -> 0x13b relay); joiners get added by 0x130.
                        "conns": {id(conn): (MEMBER_ID, conn, emit)},
                        "members": [(MEMBER_ID, npid)],
                        # PUBLIC iff this client reached RoomCreate via find-match
                        # (0x135 preceded it). Only public rooms enter the
                        # find-match list; private/custom games never do.
                        "public": find_match_searching,
                    }
                if find_match_searching:
                    emit(f"   (this RoomCreate follows a find-match search - "
                         f"room {room_id.hex()} registered as PUBLIC/matchmade)")
                    find_match_searching = False  # one-shot
                    # ---- ELECTION: the host-elect just became a real host ----
                    # Release every parked joiner NOW with a one-entry 0x136
                    # naming this room. A's lobby deadline is t(now) + 12.0 s;
                    # the reference PICK -> CONNECT_TO_HOST -> RESERVE -> 0x130
                    # path takes ~0.2 s, so the joiner has an enormous margin.
                    to_release = []
                    with election_lock:
                        e = election
                        if (e is not None and e["host_key"] == id(conn)
                                and e["state"] == "electing"):
                            e["state"] = "hosting"
                            e["create_ts"] = time.time()
                            e["room_id"] = room_id
                            e["max_players"] = max_players
                            for t in e["timers"]:
                                t.cancel()
                            wd = threading.Timer(ELECTION_JOIN_WATCHDOG_SECONDS,
                                                 _election_join_watchdog,
                                                 args=(e["gen"],))
                            wd.daemon = True
                            e["timers"] = [wd]
                            wd.start()
                            for j in e["joiners"].values():
                                if not j.get("released"):
                                    j["released"] = True
                                    if j.get("cap_timer") is not None:
                                        j["cap_timer"].cancel()
                                    to_release.append(j)
                            emit(f"   [elect] host={npid!r} is LIVE "
                                 f"(0x12f room_id={room_id.hex()}) - releasing "
                                 f"{len(to_release)} parked searcher(s); join "
                                 f"watchdog armed for "
                                 f"{ELECTION_JOIN_WATCHDOG_SECONDS:.0f}s")
                    entry_info = {"members": [(MEMBER_ID, npid)],
                                  "max_players": max_players, "npid": npid}
                    for j in to_release:
                        _send_room_search(
                            j, j["search_obj_ptr"], [(room_id, entry_info)],
                            "release",
                            f"host {npid!r} room {room_id.hex()} - PICK this")
            elif opcode == 0x130 and len(chunk) >= 0x18:
                # RoomJoin - see active_rooms' comment for the wire evidence.
                join_room_ptr = struct.unpack(">I", chunk[8:12])[0]
                target_room_id = chunk[0x10:0x18]
                host = None
                with rooms_lock:
                    # The party room_id is a shared static value
                    # (0000000001387f58) across ALL clients, so several entries
                    # can carry it. Take the MOST RECENT match on another
                    # connection: a live host is the freshly-created party,
                    # while a stale entry left by a failed prior Join Party is
                    # older. Matching the first (oldest) entry is exactly what
                    # made a failed attempt "corrupt" the next request (it
                    # routed the join to a dead connection) - dict preserves
                    # insertion order, so iterate and keep the last match.
                    for key, info in active_rooms.items():
                        if info["conn"] is not conn and info["room_id"] == target_room_id:
                            host = info
                if host is None:
                    # ELECTION FALLBACK: this connection was released with a
                    # one-entry 0x136 naming the elected host's room. The room
                    # id that comes back on the 0x130 is relayed through the
                    # P2P reserve handshake (FUN_003ca178 -> host ->
                    # FUN_003b6404 -> FUN_00ad6718), so if anything reshapes it
                    # on the way we still know exactly which room this join is
                    # for - the per-connection mapping is authoritative.
                    with election_lock:
                        e = election
                        if (e is not None and e["state"] in ("hosting", "joined")
                                and e["joiners"].get(id(conn), {}).get("released")):
                            host_key = e["host_key"]
                        else:
                            host_key = None
                    if host_key is not None:
                        with rooms_lock:
                            host = active_rooms.get(host_key)
                        if host is not None:
                            emit(f"   [release] 0x130 carried room_id="
                                 f"{target_room_id.hex()} which is not registered "
                                 f"- resolved to elected host {host['npid']!r} "
                                 f"room {host['room_id'].hex()} via the election "
                                 f"mapping")
                if host is not None:
                    # Always speak the room identity WE assigned (registry key).
                    # For the party/invite path this is identical to what the
                    # client sent; on the find-match path it is the synthesized
                    # unique public id, which both clients must agree on.
                    target_room_id = host["room_id"]
                if host is None:
                    emit(f"   parsed opcode={opcode:#x} (RoomJoin, "
                         f"room_ptr={join_room_ptr:#x}, "
                         f"target room_id={target_room_id.hex()}) - NO matching "
                         f"room found on another connection, no reply sent")
                else:
                    # Same roster discipline as everywhere else: per-recipient,
                    # own entry FIRST, self npid populated (the local member
                    # needs a real identity for team/user lookups), no
                    # RoomJoined anywhere, host flag set only for the actual
                    # host via 0x13f (explicit 0 for the joiner in case a
                    # stale 1 survives from an earlier hosted room - only
                    # RoomCreate's own sender clears it client-side).
                    host_entry = (MEMBER_ID, host["npid"])
                    joiner_entry = (JOINER_MEMBER_ID, own_npid)
                    self_member = build_member([joiner_entry, host_entry],
                                               target_room_id, host["max_players"],
                                               owner_ref_id=MEMBER_ID,
                                               local_ref_id=JOINER_MEMBER_ID,
                                               room_ptr=join_room_ptr,
                                               populate_self_npid=True)
                    conn.sendall(self_member + build_owner_changed(target_room_id, 0)
                                 + build_owner_member(target_room_id, MEMBER_ID))
                    emit(f"   parsed opcode={opcode:#x} (RoomJoin) - JOINED "
                         f"{host['npid']!r}'s room {target_room_id.hex()} as "
                         f"member_id={JOINER_MEMBER_ID}, sent Member+OwnerChanged(0) "
                         f"(room_ptr={join_room_ptr:#x})")
                    host_member = build_member([host_entry, joiner_entry],
                                               target_room_id, host["max_players"],
                                               owner_ref_id=MEMBER_ID,
                                               local_ref_id=MEMBER_ID,
                                               room_ptr=host["room_ptr"],
                                               populate_self_npid=True)
                    try:
                        host["conn"].sendall(host_member
                                             + build_owner_member(target_room_id, MEMBER_ID))
                        host["emit"](f"   [join] {own_npid!r} joined room "
                                     f"{target_room_id.hex()} - pushed updated "
                                     f"2-member roster + OwnerMember(1)")
                    except OSError as e:
                        # The matched host connection is dead. Purge its stale
                        # registry entry so it can't poison the NEXT join/invite
                        # for this shared party room_id (the "failed attempt
                        # corrupts the next request" cascade).
                        emit(f"   [join] host push failed ({e}) - purging stale "
                             f"host entry for room {target_room_id.hex()}")
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
                    # Replay any already-cached member blobs both ways so the
                    # late joiner sees incumbents' rank/loadout immediately and
                    # vice versa (0x13b must follow Member - same rule as 0x13f).
                    with rooms_lock:
                        cached = {mid: blob for (rid, mid), blob
                                  in member_blobs.items() if rid == target_room_id}
                    for mid, blob in cached.items():
                        b = build_member_blob(mid, target_room_id, blob)
                        try:
                            if mid != JOINER_MEMBER_ID:
                                conn.sendall(b)          # incumbent -> newcomer
                            if mid != MEMBER_ID:
                                host["conn"].sendall(b)  # newcomer -> incumbent
                        except OSError:
                            pass
                    with rooms_lock:
                        host["conns"][id(conn)] = (JOINER_MEMBER_ID, conn, emit)
                        host["members"] = [host_entry, joiner_entry]
                    # Restart both refreshers with the joint roster.
                    host["stop_event"].set()
                    new_host_stop = threading.Event()
                    host["stop_event"] = new_host_stop
                    start_member_refresher(host["conn"], host["emit"],
                                           [host_entry, joiner_entry],
                                           target_room_id, host["max_players"],
                                           MEMBER_ID, MEMBER_ID, new_host_stop,
                                           room_ptr=host["room_ptr"],
                                           populate_self_npid=True)
                    if active_room_stop is not None:
                        active_room_stop.set()
                    active_room_stop = threading.Event()
                    start_member_refresher(conn, emit, [joiner_entry, host_entry],
                                           target_room_id, host["max_players"],
                                           MEMBER_ID, JOINER_MEMBER_ID,
                                           active_room_stop,
                                           room_ptr=join_room_ptr,
                                           populate_self_npid=True)
                    # ---- ELECTION: a REAL join landed. Disarm the watchdog.
                    # The 2-member roster pushed just above is what makes the
                    # host dial this peer (FUN_00ad33d8 -> mgr->Connect); the
                    # link the joiner already established resolves to state 2,
                    # so FUN_003b19c4 counts 2 and the host's lobby deadline
                    # moves from 12.0 s to 16.0 s (lobbyWaitTable[2]).
                    with election_lock:
                        e = election
                        if (e is not None
                                and e["host_key"] == id(host["conn"])
                                and e["state"] == "hosting"):
                            e["state"] = "joined"
                            for t in e["timers"]:
                                t.cancel()
                            e["timers"] = []
                            emit(f"   [elect] JOINED - {own_npid!r} joined elected "
                                 f"host {host['npid']!r} room "
                                 f"{target_room_id.hex()}; watchdog disarmed, "
                                 f"real 2-member roster pushed to both sides")
            elif opcode == FIND_MATCH_OPCODE:
                # SERIALIZED HOST/JOINER ELECTION (2026-08-17). Replaces the
                # purely reactive "answer every 0x135 with whatever public
                # rooms exist" logic AND the `[pair]` synthetic roster push,
                # both of which are explicitly rejected by
                # research/notes/2026-08-17-find-match-coordination-root-cause.md:
                # the roster is server-controlled but the COUNT is P2P-gated
                # (FUN_003b19c4 only counts a member whose connection handle at
                # member+0xF0 reports state 2), so a fabricated roster is a
                # display illusion whose link dies in ~16 s. Only a real join
                # produces a real link. See the module-level election block.
                find_match_searching = True
                search_obj_ptr = (struct.unpack(">I", chunk[8:12])[0]
                                  if len(chunk) >= 12 else ROOM_PTR)
                # Burst position marker: wire offset 0x18 u16 runs 5,10,10,0,0
                # across the five searches of one burst (live-captured), so 5
                # means "first search of a fresh burst" = criteria 0.
                marker = (struct.unpack(">H", chunk[0x18:0x1a])[0]
                          if len(chunk) >= 0x1a else 0)
                conn_key = id(conn)
                me = {"conn": conn, "emit": emit, "npid": own_npid,
                      "search_obj_ptr": search_obj_ptr}
                # SAFETY (never-send rule): a live host's search object IS its
                # room object (0x01383bd8) and a 0x136 writes +0xa4/+0x200/
                # +0x208 through it. "Live host" = strictly between its own
                # 0x12f and its 0x133 - a registry membership test, NEVER a
                # timer. The old 10 s "abandon grace" gated this on a clock and
                # suppressed a 0x136 to a client that was genuinely searching,
                # hanging it for the full 60 s GAME_LIST_WAIT timeout and
                # killing the run (root-cause note §5, divergence #2).
                # Scoped precisely: the hazard is that the object this 0x136
                # would be written through is the very object this connection
                # is hosting a room on. A PARTY host (room_ptr 0x01387f58)
                # searching on the GAME object (0x01383bd8) is not affected and
                # must still get an answer.
                with rooms_lock:
                    hosted = active_rooms.get(conn_key)
                    live_host = (hosted is not None
                                 and hosted.get("room_ptr") == search_obj_ptr)
                action = None
                elected_host_npid = None
                with election_lock:
                    e = election
                    if live_host:
                        action = "livehost"
                    elif e is None:
                        _election_gen[0] += 1
                        gen = _election_gen[0]
                        to = threading.Timer(ELECTION_CREATE_TIMEOUT_SECONDS,
                                             _election_create_timeout, args=(gen,))
                        to.daemon = True
                        election = {
                            "gen": gen, "state": "electing",
                            "host_key": conn_key, "host_conn": conn,
                            "host_emit": emit, "host_npid": own_npid,
                            "start_ts": time.time(), "joiners": {},
                            "timers": [to],
                        }
                        to.start()
                        action = "elect"
                    elif e["host_key"] == conn_key:
                        action = "hostelect"
                    elif e["state"] == "joined":
                        # The elected pair is already together; a third searcher
                        # gets the ordinary public list (their room, if it has
                        # room left) rather than being parked.
                        action = "list"
                    else:
                        j = e["joiners"].get(conn_key)
                        if j is not None and j.get("released"):
                            # Already released once (it got its one-entry list
                            # and came back, e.g. the connect failed). Answer
                            # normally instead of re-parking it.
                            action = "list"
                        elif j is not None:
                            j["search_obj_ptr"] = search_obj_ptr
                            action = "reparked"
                        else:
                            cap = threading.Timer(ELECTION_HOLD_CAP_SECONDS,
                                                  _election_park_cap,
                                                  args=(e["gen"], conn_key))
                            cap.daemon = True
                            me["released"] = False
                            me["park_ts"] = time.time()
                            me["cap_timer"] = cap
                            e["joiners"][conn_key] = me
                            cap.start()
                            action = "park"
                        elected_host_npid = e["host_npid"]
                        if action in ("park", "reparked") and e["state"] == "hosting":
                            # Race: the host created its room in the window
                            # between our two lock acquisitions. Release now.
                            action = "late-release"

                if action == "livehost":
                    emit(f"   parsed opcode={opcode:#x} (find-match search, "
                         f"marker={marker}) - this connection is a LIVE HOST "
                         f"(between its own 0x12f and 0x133); NOT sending a "
                         f"0x136 (its search object is its room object)")
                elif action in ("elect", "hostelect"):
                    if action == "elect":
                        emit(f"   [elect] host={own_npid!r} (marker={marker}) - "
                             f"HOST-ELECT: answering every search in this burst "
                             f"with an EMPTY 0x136 so it exhausts its 5 searches "
                             f"and self-hosts (~10s)")
                    conn.sendall(build_room_search(search_obj_ptr, []))
                    emit(f"   parsed opcode={opcode:#x} (find-match search, "
                         f"marker={marker}) - HOST-ELECT {own_npid!r} <- EMPTY "
                         f"0x136 (search_obj_ptr={search_obj_ptr:#x})")
                elif action in ("park", "reparked"):
                    emit(f"   [park] {own_npid!r} (marker={marker}) - election "
                         f"pending for host {elected_host_npid!r}; sending "
                         f"NOTHING. Client blocks in GAME_LIST_WAIT and stops "
                         f"searching; hard cap "
                         f"{ELECTION_HOLD_CAP_SECONDS:.0f}s (client timeout is "
                         f"60s)" + ("" if action == "park" else " [re-park]"))
                elif action == "late-release":
                    hinfo = None
                    with election_lock:
                        e = election
                        if e is not None and e["state"] in ("hosting", "joined"):
                            with rooms_lock:
                                hinfo = active_rooms.get(e["host_key"])
                            jj = e["joiners"].get(conn_key)
                            if jj is not None and not jj.get("released"):
                                jj["released"] = True
                                if jj.get("cap_timer") is not None:
                                    jj["cap_timer"].cancel()
                    if hinfo is not None:
                        _send_room_search(
                            me, search_obj_ptr,
                            [(hinfo["room_id"], hinfo)], "release",
                            f"host {hinfo['npid']!r} already live - PICK this")
                    else:
                        conn.sendall(build_room_search(search_obj_ptr, []))
                        emit(f"   [release] {own_npid!r} <- EMPTY 0x136 (elected "
                             f"host vanished between locks)")
                else:  # "list"
                    with rooms_lock:
                        entries = [(info["room_id"], info)
                                   for info in active_rooms.values()
                                   if info.get("public") and info["conn"] is not conn
                                   and len(info.get("members", []))
                                   < info.get("max_players", 8)]
                    conn.sendall(build_room_search(search_obj_ptr, entries))
                    emit(f"   parsed opcode={opcode:#x} (find-match search, "
                         f"marker={marker}) - sent RoomSearch (0x136) listing "
                         f"{len(entries)} public game(s) "
                         f"[{', '.join(rid.hex() for rid, _ in entries) or 'none'}], "
                         f"search_obj_ptr={search_obj_ptr:#x}")
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
                with rooms_lock:
                    info = active_rooms.get(id(conn))
                    # Tolerate an id mismatch on a public room: its id is
                    # stub-synthesized, so if the client's own local copy ever
                    # diverges we still must retire the room rather than leave
                    # a zombie host in the list.
                    if info is not None and (info["room_id"] == room_id_tail
                                             or info.get("public")):
                        if info["room_id"] != room_id_tail:
                            emit(f"   (0x133 room_id {room_id_tail.hex()} != "
                                 f"registered {info['room_id'].hex()} - retiring "
                                 f"this connection's public room anyway)")
                        info["stop_event"].set()
                        dropped_public = bool(info.get("public"))
                        del active_rooms[id(conn)]
                stop_member_refresher(id(conn))
                if dropped_public:
                    emit(f"   (public host room {room_id_tail.hex()} abandoned - "
                         f"dropped from the find-match list IMMEDIATELY, no "
                         f"grace; this connection is no longer a host and will "
                         f"be answered normally if it searches again)")
                # The elected host gave up (or the joined pair broke up): tear
                # the election down so the next 0x135 starts a fresh one. Roles
                # may swap - that is fine and intended.
                with election_lock:
                    e = election
                    is_host = e is not None and e["host_key"] == id(conn)
                    if e is not None and not is_host:
                        j = e["joiners"].pop(id(conn), None)
                        if j is not None and j.get("cap_timer") is not None:
                            j["cap_timer"].cancel()
                if is_host:
                    election_abandon("elected host sent 0x133 (left its lobby)",
                                     emit=emit)
                # If this connection had JOINED someone else's room with this
                # id, notify the remaining members (0x134) and shrink their
                # refresher roster.
                broadcast_member_departure(id(conn), room_id=room_id_tail)
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
            elif opcode == ROOM_SEARCH_INFO_OPCODE and len(chunk) >= 16:
                # Echo the room_id straight back at the same wire offset (8),
                # matching the general "echo the client's own correlation
                # value" pattern used throughout this protocol.
                room_id_tail = chunk[8:16]
                reply = struct.pack(">I", ROOM_SEARCH_RESULT_OPCODE) + b"\x00\x00\x00\x00" + room_id_tail
                conn.sendall(reply)
                emit(f"   parsed opcode={opcode:#x} (RoomSearchInfo) - sent RoomSearchResult "
                     f"(16 bytes) echoing room_id={room_id_tail.hex()}\n{hexdump(reply)}")
            elif opcode == SET_ATTR_FLAGS_OPCODE and len(chunk) >= 16:
                flags_value = chunk[4:8]
                room_id_tail = chunk[8:16]
                reply = struct.pack(">I", UPDATED_ATTR_FLAGS_OPCODE) + flags_value + room_id_tail
                conn.sendall(reply)
                emit(f"   parsed opcode={opcode:#x} (SetAttrFlags, flags={flags_value.hex()}) - "
                     f"sent UpdatedAttrFlags (16 bytes) echoing flags+room_id="
                     f"{room_id_tail.hex()}\n{hexdump(reply)}")
            elif opcode == UPDATED_ROOM_FLAGS_OPCODE and len(chunk) >= 144:
                room_id_tail = chunk[8:16]
                rank_payload = chunk[16:144]
                reply = (struct.pack(">I", HOST_RANK_OPCODE) + chunk[4:8]
                          + room_id_tail + rank_payload)
                conn.sendall(reply)
                emit(f"   parsed opcode={opcode:#x} (UpdatedRoomFlags/rank-table submit, "
                     f"room_id={room_id_tail.hex()}) - sent HostRank (144 bytes) echoing "
                     f"the same 128-byte payload back\n{hexdump(reply)}")
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
        # Election hygiene on socket close - never leave a dead connection as
        # the host-elect (that would park every future searcher until the cap).
        with election_lock:
            e = election
            closing_host = e is not None and e["host_key"] == id(conn)
            if e is not None and not closing_host:
                j = e["joiners"].pop(id(conn), None)
                if j is not None and j.get("cap_timer") is not None:
                    j["cap_timer"].cancel()
        if closing_host:
            election_abandon("elected host's connection closed", emit=emit)
        with waiting_lock:
            if waiting_player is not None and waiting_player["conn"] is conn:
                waiting_player = None
        with rooms_lock:
            info = active_rooms.pop(id(conn), None)
            if info is not None:
                info["stop_event"].set()
                # Purge this room's cached blobs so a dead host's stale rank/
                # loadout data can't be replayed into the next party that
                # reuses the same shared room_id.
                for (rid, mid) in [kk for kk in member_blobs
                                   if kk[0] == info["room_id"]]:
                    member_blobs.pop((rid, mid), None)
        broadcast_member_departure(id(conn))
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Session Manager stub listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
