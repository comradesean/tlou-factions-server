#!/usr/bin/env python3
"""Live leave-detection watcher, keyed strictly on the real leave opcodes.

Replaces an earlier ad-hoc watcher that inferred "someone left" from timing
heuristics (a burst of 0x142+0x13a, hold duration since room-join, join/leave
ordering). That heuristic had three distinct false-positive modes across one
session and zero real catches: phantom leaves on an unrelated periodic burst
exactly 79s after join, leaves mis-ordered against joins, and hold durations
measured across match boundaries.

This watcher instead tails server/logs/wire.jsonl and reports only the two
opcodes that ARE a leave, per the decompiled client and the server's own
sender (protos/0x133_room_leaving.ksy, server/session_manager.py
build_room_leave):

  0x133 RoomLeaving (in,  client -> server, 16 bytes): the client abandoning
      a room it was tracking. wire[8:16] = room_id. This is the client's own
      decision to leave - the ground-truth event.
  0x134 RoomLeave    (out, server -> client, 24 bytes): the server telling
      the REMAINING members that someone left. wire[8:16] = room_id,
      wire[16:18] = the departed member_id (u16).

No inference, no timing windows - just decode these two opcodes as they
appear on the wire.

Usage:
    watch_leaves.py [wire.jsonl]           # tail from end (live)
    watch_leaves.py --from-start [wire.jsonl]   # replay the whole file first
"""
import argparse
import json
import os
import sys
import time

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                             "server", "logs", "wire.jsonl")


def handle(rec):
    hexstr = rec.get("hex", "")
    if not hexstr:
        return
    try:
        b = bytes.fromhex(hexstr)
    except ValueError:
        return
    ts = rec.get("t", "?")
    conn = rec.get("conn", "?")
    direction = rec.get("dir", "?")

    if direction == "in" and hexstr.startswith("00000133") and len(b) >= 16:
        room_id = b[8:16].hex()
        print(f"{ts} conn{conn} LEAVE (0x133 RoomLeaving, client-initiated) "
              f"room={room_id}")
    elif direction == "out" and hexstr.startswith("00000134") and len(b) >= 18:
        room_id = b[8:16].hex()
        member_id = int.from_bytes(b[16:18], "big")
        print(f"{ts} conn{conn} LEAVE-NOTIFY (0x134 RoomLeave sent to "
              f"remaining members) room={room_id} departed_member={member_id}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=DEFAULT_PATH)
    ap.add_argument("--from-start", action="store_true",
                     help="replay the whole file before following new lines")
    args = ap.parse_args()

    f = open(args.path)
    if not args.from_start:
        f.seek(0, os.SEEK_END)

    print(f"watching {args.path} for 0x133/0x134 (Ctrl-C to stop)...",
          file=sys.stderr)
    try:
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            handle(rec)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
