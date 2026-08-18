#!/usr/bin/env python3
"""Watches the live decrypted net10.bin and re-applies same-length IP string
patches every time the game re-downloads/re-extracts it and overwrites our
previous patch (confirmed 2026-08-14: a chmod/attrib read-only flag does NOT
survive this - the game deletes and recreates the file rather than writing
in place, so file-permission protection alone is not enough). Polling-based
(no inotify dependency) - checks mtime every 5ms.

This is the same stopgap technique as watch_and_patch_net1bin.py, generalized
to patch multiple same-length IP strings in one pass (net10.bin has 3 distinct
dead server IPs, not 1).
"""
import sys
import time
import os

PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/"
    "dev_hdd0/game/BCUS98174DATA2/USRDIR/net10.bin"
)
NEW = (sys.argv[2] if len(sys.argv) > 2 else "51.75.22.125").encode()

OLD_IPS = [b"50.18.104.153", b"174.129.210.135", b"50.18.47.114"]
for old in OLD_IPS:
    assert len(old) >= len(NEW), f"{old} shorter than {NEW}, can't null-pad safely"


def try_patch():
    if not os.path.isfile(PATH):
        return False
    data = bytearray(open(PATH, "rb").read())
    patched_any = False
    for old in OLD_IPS:
        idx = data.find(old)
        if idx == -1:
            continue
        if idx + len(old) < len(data) and data[idx + len(old)] != 0:
            print(f"[skip] match for {old} at {hex(idx)} not null-terminated, refusing", flush=True)
            continue
        replacement = NEW.ljust(len(old), b"\x00")
        data[idx:idx + len(old)] = replacement
        print(f"[patched] {old.decode()} -> {NEW.decode()} at {hex(idx)} ({time.strftime('%H:%M:%S')})", flush=True)
        patched_any = True
    if patched_any:
        # Atomic replace, not an in-place write - an in-place open(...,"wb")
        # truncates the file before the new bytes land, so a reader landing
        # in that window gets a short/inconsistent read (live-confirmed
        # 2026-08-14: "ReadSync file (req/read: 409093/262048) Permission
        # denied" crash). os.replace() on the same filesystem is a single
        # atomic rename - any reader sees either the fully-old or fully-new
        # file, never a partial one.
        tmp = PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, PATH)
    return patched_any


def main():
    print(f"Watching {PATH} for {[o.decode() for o in OLD_IPS]} -> {NEW.decode()}, polling every 5ms", flush=True)
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
        time.sleep(0.005)


if __name__ == "__main__":
    main()
