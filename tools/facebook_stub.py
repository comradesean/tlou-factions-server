#!/usr/bin/env python3
"""Local stand-in for Facebook's Graph API, so The Last of Us Factions'
"CONNECT TO FACEBOOK" flow succeeds offline and names your camp's survivors
after a list of names YOU control (tools/facebook_friends.txt).

WHAT THE GAME ACTUALLY DOES (see research/notes/2026-08-17-facebook-connect-flow.md)
-----------------------------------------------------------------------------
The client does NOT do Facebook OAuth. When you click Connect, ndlib/net/
facebook.cpp spawns a worker (FUN_00ac2324) that, on a successful sign-in,
issues two plain Graph GETs with the access token it holds:

    GET https://graph.facebook.com/me?fields=name,id&access_token=<tok>
    GET https://graph.facebook.com/me/friends?fields=name,id&access_token=<tok>

and parses JSON keys "name" and "id". The friends' names overwrite your clan
survivors' procedural names. (Profile pictures are a separate, optional set of
/<id>/picture requests.)

Two things stop this offline, and this stub + its companions fix each:
  1. Sign-in fails: the token comes from Sony's sceNpSns library
     (sceNpSnsFbGetLongAccessToken), which RPCS3 stubs -> the worker skips the
     fetches. The faithful fix is an sceNpSns that returns a token (see the
     "authentic path" in the note; needs a real PS3 or an sceNpSns impl, out of
     scope for now). The shipped shortcut is the ONE code patch in
     tools/rpcs3/facebook_stub_patch.yml ("Facebook sign-in success"): it makes
     the game's own gate write the same token + far-future expiry the library
     would have produced and return success.
  2. The Graph URLs are https:// (the only https in the game; all its other
     content is plain http) and would need a TLS MITM. Fixed by the second
     entry in the same patch.yml ("Facebook Graph http scheme"): it rewrites the
     two URL format strings to http:// so they route through the game's normal
     plain-http path to THIS server.

SETUP
-----
1. RPCS3 -> Configuration -> Network -> set "IP/Hosts switches" to include
   (semicolon-separated), pointing at the machine running this stub:

       graph.facebook.com=<stub-ip>&&&api.facebook.com=<stub-ip>&&&graph-video.facebook.com=<stub-ip>

   (RPCS3's dnshook only rewrites HOSTNAMES that go through DNS - this works
   for graph.facebook.com; it can't rewrite a literal IP. See
   research/notes/2026-08-14-404-regression-and-ip-literal-limit.md.)
   Use 127.0.0.1 if the stub runs on the same box as RPCS3.

2. Install tools/rpcs3/facebook_stub_patch.yml and enable BOTH its entries
   (RPCS3 -> right-click game -> Manage Game Patches).

3. Run this stub on port 80 on <stub-ip>:

       sudo python3 tools/facebook_stub.py

   Port 80 collides with catch_http.py (the S3 content stub). RECOMMENDED when
   you also run S3/profiles: these routes are already folded into catch_http.py
   (its FB_HOSTS branch), so just point graph.facebook.com at that server and
   skip this standalone stub. Use this one only if you want Facebook on its own
   IP separate from catch_http.py.

4. Edit tools/facebook_friends.txt to taste, connect in-game, watch the camp.

Not a general HTTP server: matches on path only, no keep-alive, no TLS
(deliberately - the patch downgrades the game to http).
"""
import datetime
import json
import os
import re
import socket
import sys
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
FRIENDS_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "facebook_friends.txt")

# Base id the stub hands out when a friends.txt line pins no explicit id.
# 15-digit range mirrors real Facebook numeric ids (the game parses id as %lld).
BASE_ID = 1000000000000001


def _make_png(w=116, h=116, rgb=(84, 110, 122)):
    """A valid solid-colour PNG built in-memory (no deps), so /picture returns a
    real decodable image instead of empty bytes (empty = icon loader spins)."""
    import struct
    import zlib

    def chunk(typ, data):
        body = typ + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit truecolour RGB
    row = b"\x00" + bytes(rgb) * w                        # filter byte 0 + pixels
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(row * h, 9)) + chunk(b"IEND", b"")


def load_people():
    """Return (me, friends) as lists of {"name","id"} dicts, read fresh on each
    request so edits to facebook_friends.txt take effect without a restart."""
    people = []
    try:
        with open(FRIENDS_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    next_id = BASE_ID
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, _, id_str = line.partition("|")
            name = name.strip()
            id_str = id_str.strip()
            fid = id_str if id_str.isdigit() else str(next_id)
        else:
            name = line
            fid = str(next_id)
        people.append({"name": name, "id": fid})
        next_id += 1
    me = people[0] if people else {"name": "Survivor", "id": str(BASE_ID)}
    friends = people[1:] if len(people) > 1 else []
    return me, friends


def json_body(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def route(method, path):
    """Map a Graph API path to (content_type, body_bytes)."""
    me, friends = load_people()
    base = path.split("?", 1)[0].lstrip("/")

    # /me/friends?fields=name,id  -> the friend roster the clan is named from.
    if base == "me/friends":
        return "application/json", json_body({
            "data": friends,
            "paging": {},
        })

    # /me?fields=name,id  -> the account holder.
    if base == "me":
        return "application/json", json_body(me)

    # /me/picture, /<id>/picture -> avatar. Serve a valid image (an empty body
    # makes the game's icon loader retry forever -> spinner next to your name).
    if base == "me/picture" or re.fullmatch(r"\d+/picture", base):
        return "image/png", _make_png()

    # /<id>?fields=name  -> single-person name lookup.
    m = re.fullmatch(r"(\d+)", base)
    if m:
        fid = m.group(1)
        for p in [me] + friends:
            if p["id"] == fid:
                return "application/json", json_body(p)
        return "application/json", json_body({"name": "Survivor", "id": fid})

    # Anything else Facebook-shaped: empty JSON object, 200, so nothing hangs.
    return "application/json", b"{}"


def handle(conn, addr, log_lock):
    ts = datetime.datetime.now().isoformat()
    try:
        conn.settimeout(5)
        data = b""
        try:
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass

        request_line = data.split(b"\r\n", 1)[0].decode("latin1", "replace")
        parts = request_line.split()
        method = parts[0] if parts else ""
        path = parts[1] if len(parts) > 1 else "/"

        content_type, body = route(method, path)
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("ascii")
        with log_lock:
            print(f"==== {ts} {addr[0]}:{addr[1]} ====\n{request_line}\n"
                  f"---- responded {len(body)} bytes ({content_type}) ----",
                  flush=True)
        try:
            conn.sendall(header + body)
        except OSError:
            pass
    finally:
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(16)
    print(f"facebook_stub listening on 0.0.0.0:{PORT}, friends from {FRIENDS_PATH}",
          flush=True)
    log_lock = threading.Lock()
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr, log_lock),
                         daemon=True).start()


if __name__ == "__main__":
    main()
