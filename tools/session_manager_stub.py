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

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7314
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/tcp_catch.log"

CLIENT_HELLO_OPCODE = 0x12d
SERVER_HELLO_OPCODE = 0x12e
ROOM_CREATE_OPCODE = 0x12f
MEMBER_OPCODE = 0x131
ROOM_JOINED_OPCODE = 0x132
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
PING_OPCODE = 0x145
CLIENT_HELLO2_OPCODE = 0x146

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


def build_room_joined(npid, name, room_id, id_gate=0):
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
      specific 0x132 case in the traced decompile - left zero.
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


def build_member(members, room_id, max_players, owner_ref_id, local_ref_id):
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
              mapped - zero
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
    struct.pack_into(">I", header, 8, ROOM_PTR)
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
        if member_id != local_ref_id:
            npid_16 = npid[:16]
            entry[0:len(npid_16)] = npid_16
        struct.pack_into(">H", entry, 36, member_id)
        npid_field = npid[:64]
        entry[40:40 + len(npid_field)] = npid_field
        entries += entry

    return bytes(header) + bytes(entries)


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
    global waiting_player
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
                max_players = struct.unpack(">H", chunk[0x1e:0x20])[0] or 10
                # RoomCreate's own 8-byte transaction id (wire offset 4:12) -
                # a real, nonzero room identity is expected once past the
                # RoomJoined id-gate - see build_member's docstring.
                room_id = chunk[4:12]

                reply = build_room_joined(npid, name, room_id)
                member = build_member([(MEMBER_ID, npid)], room_id, max_players,
                                       owner_ref_id=MEMBER_ID, local_ref_id=MEMBER_ID)
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
                conn.sendall(reply + member)
                emit(f"   parsed opcode={opcode:#x} (RoomCreate), sent RoomJoined+Member "
                     f"as one write, RoomJoined first ({len(reply)}+{len(member)} bytes, "
                     f"room_ptr={ROOM_PTR:#x}, marking member_id={MEMBER_ID} as both "
                     f"local+owner)\n{hexdump(reply + member)}")
            elif opcode == FIND_MATCH_OPCODE and not matched:
                matched = True
                with waiting_lock:
                    peer = waiting_player
                    if peer is not None and peer["npid"] != own_npid:
                        waiting_player = None
                    else:
                        peer = None
                        waiting_player = {"npid": own_npid, "conn": conn, "emit": emit}
                if peer is None:
                    emit(f"   parsed opcode={opcode:#x} (find-match search broadcast) - "
                         f"no other player waiting, registered npid={own_npid!r} and waiting")
                else:
                    room_id = os.urandom(8)
                    max_players = 10
                    host_entry = (MEMBER_ID, peer["npid"])
                    joiner_entry = (JOINER_MEMBER_ID, own_npid)
                    room_name = peer["npid"] + b".matched"

                    # Roster order is per-recipient, own entry FIRST - live-
                    # confirmed 2026-08-15: with a shared host-first order for
                    # both recipients, the host (self at index 0) reached the
                    # lobby fine but the joiner (self at index 1, after the
                    # real remote entry) hit SCE_NP_SIGNALING_ERROR_OWN_NP_ID -
                    # a self-signaling attempt - despite both recipients using
                    # the exact same self-npid-skip logic in build_member.
                    # Since the field-content fix was identical for both but
                    # only position differed, the client evidently treats
                    # roster index 0 as "me" positionally, not by content -
                    # each recipient now gets their own entry first.
                    # Non-matching id_gate (all-ones sentinel, vs the default
                    # 0 the client's pending slot would actually have) - see
                    # build_room_joined's docstring: makes RoomJoined's own
                    # id-gate search fail to find a slot, skipping its
                    # internal self-signaling registration call. Member
                    # already fully registers this member on its own.
                    NO_MATCH_ID_GATE = 0xFFFFFFFFFFFFFFFF
                    peer_room_joined = build_room_joined(peer["npid"], room_name, room_id,
                                                          id_gate=NO_MATCH_ID_GATE)
                    peer_member = build_member([host_entry, joiner_entry], room_id, max_players,
                                                owner_ref_id=MEMBER_ID, local_ref_id=MEMBER_ID)
                    # Member sent BEFORE RoomJoined - see the matching comment
                    # in the RoomCreate branch above (capacity must be written
                    # by Member's processing before RoomJoined's own internal
                    # registration call reads it, or it traps regardless of
                    # Member's contents).
                    peer["conn"].sendall(peer_member + peer_room_joined)
                    peer["emit"](f"   MATCHED with {own_npid!r} (find-match pairing) - sent "
                                  f"Member+RoomJoined as one write, Member first, as host "
                                  f"(member_id={MEMBER_ID}) room_id={room_id.hex()}")

                    self_room_joined = build_room_joined(own_npid, room_name, room_id,
                                                          id_gate=NO_MATCH_ID_GATE)
                    self_member = build_member([joiner_entry, host_entry], room_id, max_players,
                                                owner_ref_id=MEMBER_ID, local_ref_id=JOINER_MEMBER_ID)
                    conn.sendall(self_member + self_room_joined)
                    emit(f"   parsed opcode={opcode:#x} (find-match search broadcast) - "
                         f"MATCHED with {peer['npid']!r} - sent Member+RoomJoined as one write, "
                         f"Member first, as joiner (member_id={JOINER_MEMBER_ID}) "
                         f"room_id={room_id.hex()}")
            elif opcode == ROOM_LEAVING_OPCODE and len(chunk) >= 16:
                # No reply - confirmed fire-and-forget, see the constant's
                # docstring. This firing means the client just gave up on
                # and abandoned this room on its own initiative.
                room_id_tail = chunk[8:16]
                emit(f"   parsed opcode={opcode:#x} (client abandoning room, "
                     f"room_id={room_id_tail.hex()}) - no reply (confirmed "
                     f"fire-and-forget)")
            elif opcode == ROOM_SEARCH_INFO_OPCODE and len(chunk) >= 16:
                # Echo the room_id straight back at the same wire offset (8),
                # matching the general "echo the client's own correlation
                # value" pattern used throughout this protocol.
                room_id_tail = chunk[8:16]
                reply = struct.pack(">I", ROOM_SEARCH_RESULT_OPCODE) + b"\x00\x00\x00\x00" + room_id_tail
                conn.sendall(reply)
                emit(f"   parsed opcode={opcode:#x} (RoomSearchInfo) - sent RoomSearchResult "
                     f"(16 bytes) echoing room_id={room_id_tail.hex()}\n{hexdump(reply)}")
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
        with waiting_lock:
            if waiting_player is not None and waiting_player["conn"] is conn:
                waiting_player = None
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
