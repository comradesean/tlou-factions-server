#!/usr/bin/env python3
"""Minimal raw-socket HTTP catcher for observing what a redirected hostname
actually requests, and serving real files back when we have them.

Parses the request line for the path, strips the leading '/', and looks for
a matching file under SERVED_DIR (default tools/served_content/). If found,
serves it with a real Content-Length and application/octet-stream.

On a cache miss, before falling back, tries a live fetch against the ORIGINAL
hostname from the request's Host: header (reaching out over this machine's
own real internet connection, not the redirected/patched path the game uses) -
Naughty Dog's live game servers are dead, but as of this project's research
the static S3 content buckets (t1.final.prod.s3.amazonaws.com and friends)
turned out to still be up. A successful live fetch is cached to SERVED_DIR
so later requests for the same path hit the local-file branch instead. If the
live fetch fails (network error, 403/404/etc - some buckets/paths really are
gone), falls back to FALLBACK_STATUS (default 200 OK, empty body) so the
client's request cycle completes rather than hanging. NOTE: a 404 fallback
was tried and made the game fail *before* even reaching a menu (see
research/notes/net1bin-server-list.md / session 3) - an empty 200 is what
the game actually tolerates gracefully for content-delivery checks it
doesn't strictly need. Don't default this back to 404 without re-testing.

Not a real HTTP server - no range requests, no query-string handling
(matches on path only), no persistent connections.
"""
import base64
import socket
import sys
import datetime
import os
import threading
import urllib.request
import urllib.error

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_LOGS = os.path.join(_HERE, "logs")
os.makedirs(_LOGS, exist_ok=True)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "http_gateway.log")
FALLBACK_STATUS = sys.argv[3] if len(sys.argv) > 3 else "200 OK"
SERVED_DIR = sys.argv[4] if len(sys.argv) > 4 else os.path.join(_DATA, "served_content")

UPSTREAM_PROXY_ENABLED = os.environ.get("TLOU_HTTP_PROXY_UPSTREAM", "1") != "0"
UPSTREAM_TIMEOUT = 20


def get_header(text, name):
    prefix = name.lower() + ":"
    for line in text.split("\r\n")[1:]:
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def try_upstream_fetch(host, raw_path):
    """Best-effort live fetch of the real original file. Returns bytes or None."""
    url = f"http://{host}/{raw_path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DNTG-HTTPC/1.1"})
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def put_key_from_path(raw_path):
    """Map a path-style S3 PUT path to the same SERVED_DIR key a virtual-hosted
    GET uses. The game GETs `t1.final.prod.s3.amazonaws.com/profiles/<npid>/
    profile.21` (vhost, key = the path) but PUTs path-style to
    `s3.amazonaws.com/t1.final.prod/profiles/<npid>/profile.21` (key = path with
    the leading bucket segment stripped) - see
    research/notes/2026-08-16-profile-and-userdata-reverse-engineering.md. So for
    a path-style PUT, drop the first path segment (the bucket) to land on the
    same file the GET reads back."""
    stripped = raw_path.lstrip("/")
    segs = stripped.split("/", 1)
    # First segment is the S3 bucket in path-style requests (e.g.
    # "t1.final.prod"); strip it so the key matches the vhost GET.
    if len(segs) == 2:
        return segs[1]
    return stripped


def build_put_response(request_line, text, body):
    """Store an S3 PUT body under the GET key and 200 OK it, so the client's own
    correctly-signed profile.21 uploads round-trip and progression persists with
    zero format knowledge on our side. Requires RPCS3 to redirect
    s3.amazonaws.com to this host (config IP-swap) - otherwise the PUT never
    reaches us. See the profile-reverse-engineering note, section 4."""
    parts = request_line.split()
    raw_path = parts[1].split("?", 1)[0] if len(parts) >= 2 else ""
    key = put_key_from_path(raw_path)
    file_path = os.path.join(SERVED_DIR, key)
    stored = 0
    if key and body is not None:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(body)
        stored = len(body)
    header = (
        f"HTTP/1.1 200 OK\r\n"
        f"Content-Length: 0\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii")
    return header, key, stored, " (PUT stored)" if stored else " (PUT empty)"


# --- Facebook Graph stand-in (folded in from facebook_stub.py) ------------
# When graph.facebook.com is IP/Hosts-switched to this server, answer its /me,
# /me/friends and /<id>/picture calls from the editable friend list so the
# game's "Connect to Facebook" flow names the clan locally. See
# research/notes/2026-08-17-facebook-connect-flow.md and tools/facebook_stub.py.
FB_HOSTS = {"graph.facebook.com", "api.facebook.com", "graph-video.facebook.com"}
_FB_DIR = _DATA
FB_FRIENDS_PATH = os.path.join(_FB_DIR, "facebook_friends.txt")
# Optional real photos: drop <id>.png/.jpg or me.png/.jpg in tools/facebook_pics/.
FB_PICS_DIR = os.path.join(_FB_DIR, "facebook_pics")
FB_BASE_ID = 1000000000000001
# Max friends served to /me/friends. The game overflows a 2048-byte stack buffer
# at ~120+ friends (unbounded strcat in the Presence Thread) -> crash; keep low.
FB_MAX_FRIENDS = 32


# The game picks the image decoder from the URL's last 3 chars (facebook.cpp
# FUN_00ac719c @ 0xac7384: strcmp(url_end-3, "png") -> PNG loader, else JPEG).
# Our /me/picture URL ends in "...access_token=STUB", so the game always uses
# its JPEG decoder - therefore /picture MUST return JPEG bytes, not PNG (a PNG
# body silently fails to decode -> the icon spins and re-fetches every 5s).
# Solid-colour 116x116 placeholder JPEG, embedded so the stub stays stdlib-only.
_FB_PLACEHOLDER_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcU"
    "FhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgo"
    "KCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAB0AHQDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDn6KKK"
    "6zzwooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK"
    "KKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoooo"
    "AKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo"
    "ooAKKKKACiiigAooooAKKKKACiiigD/9k=")


def _fb_picture_bytes(base):
    """(content_type, body) for a /picture path - always JPEG (see note above).
    Serves a real override photo if tools/facebook_pics/<key>.{jpg,jpeg} exists,
    else the placeholder. key is the leading id, or 'me' for /me/picture."""
    key = "me" if base.startswith("me/") else base.split("/", 1)[0]
    for ext in (".jpg", ".jpeg"):
        path = os.path.join(FB_PICS_DIR, key + ext)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return "image/jpeg", f.read()
    return "image/jpeg", _FB_PLACEHOLDER_JPEG


def fb_load_people():
    """(me, friends) from facebook_friends.txt, re-read each request so edits
    take effect live. First non-comment line = you (/me); rest = friends."""
    try:
        with open(FB_FRIENDS_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    people, next_id = [], FB_BASE_ID
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, _, id_str = line.partition("|")
            name, id_str = name.strip(), id_str.strip()
            fid = id_str if id_str.isdigit() else str(next_id)
        else:
            name, fid = line, str(next_id)
        people.append({"name": name, "id": fid})
        next_id += 1
    me = people[0] if people else {"name": "Survivor", "id": str(FB_BASE_ID)}
    return me, people[1:]


def fb_response(raw_path):
    """(header+body, matched_label, served_len) for a Facebook Graph path."""
    import json
    import re as _re
    me, friends = fb_load_people()
    base = raw_path.split("?", 1)[0].lstrip("/")
    if base == "me/friends":
        # Cap the served friends: the game's Presence Thread builds its outbound
        # "friends <id> <id> ..." request via unbounded strcat into a 2048-byte
        # stack buffer (128 friends/line), so a large list smashes its own saved
        # return address and crashes (jump to 0x30303030 = the '0'-run fbid bytes).
        # ~120 16-digit ids overflow one batch; 32 keeps us far under, and a clan
        # is only a few dozen survivors anyway. See the crash root-cause note.
        ctype, obj = "application/json", {"data": friends[:FB_MAX_FRIENDS], "paging": {}}
    elif base == "me":
        ctype, obj = "application/json", me
    elif base == "me/picture" or _re.fullmatch(r"\d+/picture", base):
        ctype, body = _fb_picture_bytes(base)
        header = (f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\n"
                  f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii")
        return header + body, f"fb:{base}", len(body)
    else:
        m = _re.fullmatch(r"(\d+)", base)
        obj = next((p for p in [me] + friends if p["id"] == m.group(1)),
                   {"name": "Survivor", "id": m.group(1)}) if m else {}
        ctype = "application/json"
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    header = (f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\n"
              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii")
    return header + body, f"fb:{base}", len(body)
# --------------------------------------------------------------------------


def build_response(request_line, text, body=None):
    parts = request_line.split()
    if len(parts) >= 1 and parts[0] == "PUT":
        return build_put_response(request_line, text, body)
    if len(parts) < 2 or parts[0] != "GET":
        return (f"HTTP/1.1 {FALLBACK_STATUS}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").encode("ascii"), "", 0, ""

    # Facebook Graph hosts get the friend-list stand-in, not the file/S3 path.
    host = get_header(text, "Host")
    if host and host.split(":", 1)[0] in FB_HOSTS:
        response, label, served_len = fb_response(parts[1])
        return response, label, served_len, ""

    raw_path = parts[1].split("?", 1)[0]
    path = raw_path.lstrip("/")
    file_path = os.path.join(SERVED_DIR, path)

    upstream_note = ""
    if path and not os.path.isfile(file_path) and UPSTREAM_PROXY_ENABLED:
        host = get_header(text, "Host")
        if host:
            fetched = try_upstream_fetch(host, raw_path.lstrip("/"))
            if fetched is not None:
                os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(fetched)
                upstream_note = f" (live-fetched from {host}, cached)"
            else:
                upstream_note = f" (live fetch from {host} failed)"

    if path and os.path.isfile(file_path):
        with open(file_path, "rb") as f:
            body = f.read()
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/octet-stream\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("ascii")
        return header + body, path, len(body), upstream_note

    header = (
        f"HTTP/1.1 {FALLBACK_STATUS}\r\n"
        f"Content-Length: 0\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii")
    return header, path, 0, upstream_note


def handle(conn, addr, log, log_lock):
    ts = datetime.datetime.now().isoformat()
    try:
        conn.settimeout(5)
        data = b""
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\r\n\r\n" in data:
                    break
        except socket.timeout:
            pass

        # Split headers from any body already read; for PUT/POST keep reading
        # until the full Content-Length body arrives (the client uploads its
        # signed profile.21 as a PUT body). GET has no body, so this is a no-op
        # for the common case.
        head, sep, body = data.partition(b"\r\n\r\n")
        headers_text = head.decode("latin1", errors="replace")
        request_line = headers_text.split("\r\n", 1)[0] if headers_text else ""
        method = request_line.split(" ", 1)[0] if request_line else ""
        if sep and method in ("PUT", "POST"):
            content_length = get_header(headers_text + "\r\n", "Content-Length")
            try:
                want = int(content_length) if content_length else 0
            except ValueError:
                want = 0
            try:
                while len(body) < want:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    body += chunk
            except socket.timeout:
                pass
        text = headers_text

        entry = f"==== {ts} from {addr[0]}:{addr[1]} ====\n{text}\n"
        # build_response() can block for up to UPSTREAM_TIMEOUT seconds on a
        # live upstream fetch (e.g. patch.psarc.crypt's bucket is permanently
        # dead and re-attempts on every single request, never caching) - this
        # runs per-connection in its own thread specifically so a slow fetch
        # for one request can't starve other concurrent requests (this was a
        # real bug: a second, concurrent net1.bin.psarc.crypt connection
        # arriving while a patch.psarc.crypt fetch was still in flight got no
        # response at all until the client's own 10s connect timeout gave up
        # and closed it - not a network/firewall/DNS issue, confirmed via a
        # live RPCS3 log trace of the hung connect() call).
        response, matched_path, served_len, upstream_note = build_response(request_line, text, body)
        entry += f"---- responded: {'served ' + str(served_len) + ' bytes for ' + matched_path if served_len else FALLBACK_STATUS}{upstream_note} ----\n"
        with log_lock:
            print(entry, flush=True)
            log.write(entry + "\n")

        try:
            conn.sendall(response)
        except OSError:
            pass
    finally:
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}, serving from {SERVED_DIR}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle, args=(conn, addr, log, log_lock), daemon=True).start()

if __name__ == "__main__":
    main()
