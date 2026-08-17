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
# CORRECTED 2026-08-17 (live PPU breakpoint + disasm): 0x137/0x138 are NOT
# search info/result - they are the party KICK mechanism, and 0x13c is PROMOTE:
#   0x137 Kickout   C->S "kick member X"   {u16 target@+4; u16 requester@+6; u64 room_id@+8}
#   0x138 Kickedout S->C recipient leaves the room named at wire+8 (handler @0x00ad7f28)
#   0x13c Promote   C->S "make member X party leader" {u16 target@+4; u64 room_id@+8}
KICKOUT_OPCODE = 0x137
KICKEDOUT_OPCODE = 0x138
PROMOTE_OPCODE = 0x13c
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
                if find_match_searching:
                    room_id = synth_public_room_id(room_ptr)
                elif room_ptr == PARTY_ROOM_PTR:
                    room_id = synth_party_room_id(room_ptr)
                    emit(f"   [party-id] minted unique party room_id "
                         f"{room_id.hex()} for {npid!r} (was shared static "
                         f"{PARTY_ROOM_PTR:#010x}; disambiguates the RoomJoin "
                         f"host lookup for direct Join Party)")
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
                                       populate_self_npid=True,
                                       blobs=create_blobs)
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
                         f"room {room_id.hex()} registered as PUBLIC/matchmade; "
                         f"now discoverable in the 0x136 list to other searchers)")
                    find_match_searching = False  # one-shot
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
                    # ---- HARVEST THIS JOINER'S 32-BYTE MEMBER BLOB ----
                    # RANK/LOADOUT FIX (2026-08-17): wire[0x0c] = length,
                    # wire[0x18:] = blob (FUN_00ad6718 0x00ad67a0/0x00ad67ac/
                    # 0x00ad67a8/0x00ad67c0). This is the ONLY place the joiner
                    # ever tells us its rank/faction/loadout on the find-match
                    # path - it sends no 0x13a there.
                    join_blob = extract_member_blob(chunk, ROOM_JOIN_BLOB_LEN_OFF,
                                                    ROOM_JOIN_BLOB_OFF)
                    if join_blob is not None:
                        with rooms_lock:
                            member_blobs[(target_room_id, JOINER_MEMBER_ID)] = join_blob
                        emit(f"   [blob] harvested {len(join_blob)}-byte member "
                             f"blob from {own_npid!r}'s RoomJoin (wire "
                             f"0x{ROOM_JOIN_BLOB_OFF:x}, len byte "
                             f"0x{ROOM_JOIN_BLOB_LEN_OFF:x}) -> cached for room "
                             f"{target_room_id.hex()} member_id={JOINER_MEMBER_ID}"
                             + ("" if len(join_blob) == 32 else
                                "  *** NOT 32 BYTES - FUN_00ad2650 will reject it ***"))
                    else:
                        emit(f"   [blob] no usable member blob in {own_npid!r}'s "
                             f"RoomJoin - the host's rank/loadout widgets for "
                             f"this player will stay blank")
                    with rooms_lock:
                        join_blobs = {mid: member_blobs[(target_room_id, mid)]
                                      for mid in (MEMBER_ID, JOINER_MEMBER_ID)
                                      if (target_room_id, mid) in member_blobs}
                    self_member = build_member([joiner_entry, host_entry],
                                               target_room_id, host["max_players"],
                                               owner_ref_id=MEMBER_ID,
                                               local_ref_id=JOINER_MEMBER_ID,
                                               room_ptr=join_room_ptr,
                                               populate_self_npid=True,
                                               blobs=join_blobs)
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
                                               populate_self_npid=True,
                                               blobs=join_blobs)
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
                    # The 2-member roster pushed to the host just above is what
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
                    hosted = active_rooms.get(conn_key)
                    live_host = (hosted is not None
                                 and hosted.get("room_ptr") == search_obj_ptr)
                    entries = [(info["room_id"], info)
                               for info in active_rooms.values()
                               if info.get("public") and info["conn"] is not conn
                               and len(info.get("members", []))
                               < info.get("max_players", 8)]
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
                        # Retire the room's cached member blobs with it, so a
                        # departed player's rank/faction/loadout can never be
                        # seeded into the NEXT room that reuses this id.
                        for k in [kk for kk in member_blobs
                                  if kk[0] == info["room_id"]]:
                            member_blobs.pop(k, None)
                stop_member_refresher(id(conn))
                if dropped_public:
                    emit(f"   (public host room {room_id_tail.hex()} abandoned - "
                         f"dropped from the find-match list IMMEDIATELY, no "
                         f"grace; this connection is no longer a host and will "
                         f"be answered normally if it searches again)")
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
                    # NOT a real kick. Live-decoded 2026-08-17: the friends-list
                    # "Join Party" flow emits its OWN 0x137 right after RoomJoin
                    # with requester(+6)=0 and target(+4)=the joiner. Acting on
                    # it kicked the joiner ("Unable to join party / You were
                    # kicked"). A user "Kick from Party" carries the kicking
                    # member's id at +6 (nonzero, e.g. 1 for the host). So gate
                    # the kick on requester!=0; otherwise log-only (this 0x137
                    # is a join-flow status message, fire-and-forget).
                    emit(f"   parsed opcode={opcode:#x} (0x137 requester=0, "
                         f"target={target_member_id}, room_id={room_id_tail.hex()}) "
                         f"- NOT a kick (join-flow status message), no action")
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
                    broadcast_member_departure(id(tconn), room_id=room_entry["room_id"])
            elif opcode == PROMOTE_OPCODE and len(chunk) >= 16:
                # PROMOTE TO PARTY LEADER - wired up 2026-08-17. Payload
                # (live-decoded): opcode(4) | new_owner member_id u16 @+4 |
                # (u16 @+6 uninitialised) | room_id(8) @+8. Make every client
                # agree on the new leader: OwnerMember (0x13d) sets
                # room_obj+0x19f0 (owner member id) everywhere; OwnerChanged
                # (0x13f) flips the "am I host" flag at room_obj+0x19f4 - 1 for
                # the new leader, 0 for everyone else. Both opcodes are already
                # used in the working join flow.
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
                else:
                    owner_msg = build_owner_member(room_entry["room_id"], new_owner_id)
                    sent = 0
                    for mid, c, em in conns:
                        try:
                            c.sendall(owner_msg)
                            c.sendall(build_owner_changed(
                                room_entry["room_id"], 1 if mid == new_owner_id else 0))
                            sent += 1
                        except OSError:
                            pass
                    emit(f"   parsed opcode={opcode:#x} (Promote) - new leader "
                         f"member_id={new_owner_id} in room "
                         f"{room_entry['room_id'].hex()}: OwnerMember(0x13d)+"
                         f"OwnerChanged(0x13f) to {sent} member(s)")
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
    print(f"{_ts()} Session Manager stub listening on 0.0.0.0:{PORT}, "
          f"logging to {LOG_PATH}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
