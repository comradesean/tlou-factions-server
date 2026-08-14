#!/usr/bin/env python3
"""Watches the live decrypted net1.bin and re-applies the same-length IP
string patch (dead fallback server -> our own address) every time the game
re-downloads/re-extracts it and overwrites our previous patch. Polling-based
(no inotify dependency) - checks mtime every 0.5s.

This is a stopgap: the real fix is a proper net1.bin.psarc.crypt round-trip
(decrypt -> patch -> re-encrypt) so the server-side file itself is correct
and no live-patching is needed at all - see research/notes/net1bin-server-list.md.
"""
import sys
import time
import os

PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/"
    "dev_hdd0/game/BCUS98174DATA2/USRDIR/net1.bin"
)
OLD = sys.argv[2].encode() if len(sys.argv) > 2 else b"50.18.104.153"
NEW = sys.argv[3].encode() if len(sys.argv) > 3 else b"192.168.1.100"

assert len(OLD) == len(NEW), "must be same length for a safe in-place patch"


def try_patch():
    if not os.path.isfile(PATH):
        return False
    data = bytearray(open(PATH, "rb").read())
    idx = data.find(OLD)
    if idx == -1:
        return False
    if idx + len(OLD) < len(data) and data[idx + len(OLD)] != 0:
        print(f"[skip] match at {hex(idx)} not null-terminated, refusing to patch")
        return False
    data[idx:idx + len(OLD)] = NEW
    open(PATH, "wb").write(data)
    print(f"[patched] {PATH} at {hex(idx)} ({time.strftime('%H:%M:%S')})", flush=True)
    return True


def main():
    print(f"Watching {PATH} for {OLD} -> {NEW}, polling every 0.5s", flush=True)
    last_mtime = None
    while True:
        try:
            mtime = os.path.getmtime(PATH)
        except FileNotFoundError:
            mtime = None
        if mtime != last_mtime:
            last_mtime = mtime
            if mtime is not None:
                try_patch()
        time.sleep(0.5)

if __name__ == "__main__":
    main()
