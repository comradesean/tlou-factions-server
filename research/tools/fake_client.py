#!/usr/bin/env python3
"""Synthetic Session Manager client - a third participant for soak testing.

Speaks enough of the port-7314 protocol to log in, search, join a room, sit in
it, and leave (or die abruptly, simulating a client crash). Its purpose is to
generate the roster churn a third player creates WITHOUT needing a third VM, so
we can see whether that churn destabilises the real clients or the stub.

WHAT IT DOES NOT DO: any P2P. The real clients will try to dial this member's
signaling handle and fail, exactly as they would for a hung or crashed peer.
That is realistic for the failure modes being chased, but it means a game will
not actually start with this client in it - use it to exercise LOBBY and ROSTER
paths, not to play a match.

Frame layouts are taken from live captures (server/logs/wire.jsonl) and the
schemas in protos/. See docs/protocol/session_manager_and_matchmaking.md.

Examples
    # log in, search, join whatever public room appears, hold 30 s, leave, repeat
    python3 research/tools/fake_client.py --host 192.168.1.100 --npid faker01

    # join one specific room over and over (roster churn against a known host)
    python3 research/tools/fake_client.py --room 5000000501383bd8 --cycles 20

    # join, then DROP THE SOCKET without leaving - simulates a crashed client,
    # which is what exercises the owner/member dead-socket teardown paths
    python3 research/tools/fake_client.py --hold 20 --crash --cycles 5
"""
import argparse
import binascii
import socket
import struct
import sys
import threading
import time

CLIENT_HELLO = 0x12D
SERVER_HELLO = 0x12E
ROOM_CREATE = 0x12F
ROOM_JOIN = 0x130
MEMBER = 0x131
ROOM_LEAVING = 0x133
ROOM_LEAVE = 0x134
FIND_MATCH = 0x135
ROOM_SEARCH = 0x136
KICKEDOUT = 0x138
ROOM_CLOSED = 0x139
MEMBER_UPD = 0x13B
PING = 0x145
CLIENT_HELLO2 = 0x146

# Fixed-size messages. 0x131 Member is variable (160 + roster_count * 104).
FIXED_LEN = {
    0x12E: 16, 0x134: 24, 0x138: 16, 0x139: 16, 0x13B: 80,
    0x13D: 16, 0x13F: 16, 0x141: 16, 0x144: 144, 0x145: 4,
}
MEMBER_HEADER = 160
MEMBER_ENTRY = 104

# Live-observed client constants (see protos/): the game object and party object
# pointers are static addresses in the retail EBOOT, identical on every client.
GAME_ROOM_PTR = 0x01383BD8
PARTY_ROOM_PTR = 0x01387F58

NAMES = {
    0x12E: "ServerHello", 0x131: "Member", 0x134: "RoomLeave",
    0x136: "RoomSearch", 0x138: "Kickedout", 0x139: "RoomClosed",
    0x13B: "MemberUpdatedData", 0x13D: "OwnerMemberChanged",
    0x13F: "HostFlagUpdated", 0x141: "UpdatedRoomFlags",
    0x144: "RoomDataBlockUpdated",
}


def member_card(team=1):
    """A plausible 32-byte member_data card (protos/common/member_data.ksy)."""
    b = bytearray(32)
    # party_id 0:8 = 0 (not in a party); capability_flag 8 = 0 (no DLC)
    b[9] = team & 0xFF                      # team / faction
    b[10:14] = b"\xff\xff\xff\xff"          # recent_level ring, 0xff = unset
    struct.pack_into(">H", b, 14, 0)        # rank_value (unranked)
    return bytes(b)


def f_hello(npid):
    b = bytearray(48)
    struct.pack_into(">I", b, 0, CLIENT_HELLO)
    name = npid.encode("ascii")[:16]
    b[8:8 + len(name)] = name
    return bytes(b)


def f_hello2():
    b = bytearray(8)
    struct.pack_into(">I", b, 0, CLIENT_HELLO2)
    struct.pack_into(">I", b, 4, 0x11223344)   # session checksum; unvalidated
    return bytes(b)


def f_ping():
    return struct.pack(">I", PING)


def f_find_match(marker, search_obj_ptr=GAME_ROOM_PTR, playlist_id=2):
    b = bytearray(36)
    struct.pack_into(">I", b, 0, FIND_MATCH)
    struct.pack_into(">I", b, 8, search_obj_ptr)
    struct.pack_into(">I", b, 12, playlist_id)
    struct.pack_into(">I", b, 16, 0x102C503F)   # room_flags, live-constant
    struct.pack_into(">HH", b, 20, 1000, 1000)  # value_pair_14
    struct.pack_into(">H", b, 24, marker)       # burst_marker
    b[32:36] = b"us\x00\x01"                    # locale
    return bytes(b)


def f_room_join(room_id, room_ptr, team=1):
    b = bytearray(88)
    struct.pack_into(">I", b, 0, ROOM_JOIN)
    struct.pack_into(">I", b, 8, room_ptr)
    b[12] = 32                                  # member_data_length
    b[16:24] = room_id
    b[24:56] = member_card(team)
    return bytes(b)


def f_room_leaving(room_id):
    b = bytearray(16)
    struct.pack_into(">I", b, 0, ROOM_LEAVING)
    b[8:16] = room_id
    return bytes(b)


class Fake:
    def __init__(self, args):
        self.a = args
        self.sock = None
        self.buf = b""
        self.stop = threading.Event()
        self.rooms = []          # room_ids seen in the last 0x136
        self.lock = threading.Lock()
        self.counts = {}

    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {self.a.npid}: {msg}", flush=True)

    # ---- framing -------------------------------------------------------
    def frame_len(self, b):
        if len(b) < 4:
            return None
        op = struct.unpack(">I", b[:4])[0]
        if op in FIXED_LEN:
            return FIXED_LEN[op]
        if op == MEMBER:
            if len(b) < 28:
                return None
            return MEMBER_HEADER + struct.unpack(">H", b[26:28])[0] * MEMBER_ENTRY
        if op == ROOM_SEARCH:
            if len(b) < 16:
                return None
            return 16 + struct.unpack(">I", b[12:16])[0] * 56
        return -1     # unknown opcode: cannot frame

    def reader(self):
        while not self.stop.is_set():
            try:
                data = self.sock.recv(65536)
            except OSError:
                break
            if not data:
                self.log("server closed the connection")
                break
            self.buf += data
            while self.buf:
                n = self.frame_len(self.buf)
                if n is None or (n > 0 and len(self.buf) < n):
                    break
                if n < 0:
                    op = struct.unpack(">I", self.buf[:4])[0]
                    self.log(f"!! unframeable opcode {op:#x}, dropping {len(self.buf)}B")
                    self.buf = b""
                    break
                self.on_frame(self.buf[:n])
                self.buf = self.buf[n:]

    def on_frame(self, f):
        op = struct.unpack(">I", f[:4])[0]
        self.counts[op] = self.counts.get(op, 0) + 1
        if op == ROOM_SEARCH:
            cnt = struct.unpack(">I", f[12:16])[0]
            with self.lock:
                self.rooms = [f[16 + i * 56: 24 + i * 56] for i in range(cnt)]
            self.log(f"<- RoomSearch: {cnt} room(s) "
                     f"{[r.hex() for r in self.rooms]}")
        elif op == MEMBER:
            cnt = struct.unpack(">H", f[26:28])[0]
            self.log(f"<- Member: roster={cnt} room={f[16:24].hex()} "
                     f"local_ref={struct.unpack('>H', f[14:16])[0]}")
        elif op in (KICKEDOUT, ROOM_CLOSED, ROOM_LEAVE):
            self.log(f"<- *** {NAMES.get(op, hex(op))} *** room={f[8:16].hex()}")
        elif op not in (0x13B, 0x13D, 0x13F, 0x141, 0x12E):
            self.log(f"<- {NAMES.get(op, hex(op))}")

    # ---- lifecycle -----------------------------------------------------
    def send(self, b):
        self.sock.sendall(b)

    def pinger(self):
        while not self.stop.wait(30):
            try:
                self.send(f_ping())
            except OSError:
                return

    def connect(self):
        self.sock = socket.create_connection((self.a.host, self.a.port), timeout=10)
        self.sock.settimeout(None)
        threading.Thread(target=self.reader, daemon=True).start()
        threading.Thread(target=self.pinger, daemon=True).start()
        self.send(f_hello(self.a.npid))
        time.sleep(0.2)
        self.send(f_hello2())
        self.log(f"connected to {self.a.host}:{self.a.port}")

    def search(self):
        """One find-match burst, mimicking the real client's marker sequence."""
        for marker in (5, 10, 10, 0, 0):
            self.send(f_find_match(marker))
            time.sleep(self.a.search_gap)
        with self.lock:
            return list(self.rooms)

    def run(self):
        self.connect()
        time.sleep(1.0)
        for i in range(1, self.a.cycles + 1):
            if self.a.room:
                room = binascii.unhexlify(self.a.room)
            else:
                found = self.search()
                if not found:
                    self.log(f"cycle {i}: no rooms advertised, waiting")
                    time.sleep(self.a.gap)
                    continue
                room = found[-1]
            ptr = PARTY_ROOM_PTR if room.endswith(b"\x01\x38\x7f\x58") else GAME_ROOM_PTR
            self.log(f"cycle {i}/{self.a.cycles}: JOIN {room.hex()}")
            self.send(f_room_join(room, ptr, team=self.a.team))
            time.sleep(self.a.hold)
            if self.a.crash:
                self.log(f"cycle {i}: *** DROPPING SOCKET without leaving "
                         f"(simulated crash) ***")
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.stop.set()
                time.sleep(self.a.gap)
                if i < self.a.cycles:
                    self.stop = threading.Event()
                    self.buf = b""
                    self.connect()
                    time.sleep(1.0)
            else:
                self.log(f"cycle {i}: LEAVE {room.hex()}")
                self.send(f_room_leaving(room))
                time.sleep(self.a.gap)
        self.log(f"done. received: " + ", ".join(
            f"{NAMES.get(o, hex(o))}={n}" for o, n in sorted(self.counts.items())))
        self.stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7314)
    p.add_argument("--npid", default="faker01", help="<=16 ASCII chars")
    p.add_argument("--room", help="join this room_id hex (16 chars) instead of searching")
    p.add_argument("--cycles", type=int, default=10)
    p.add_argument("--hold", type=float, default=30.0, help="seconds to stay in the room")
    p.add_argument("--gap", type=float, default=5.0, help="seconds between cycles")
    p.add_argument("--search-gap", type=float, default=1.5)
    p.add_argument("--team", type=int, default=1)
    p.add_argument("--crash", action="store_true",
                   help="drop the socket instead of leaving cleanly")
    a = p.parse_args()
    try:
        Fake(a).run()
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
