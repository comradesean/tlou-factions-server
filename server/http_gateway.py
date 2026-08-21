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
gone), or the requested host is not on UPSTREAM_ALLOWED_HOSTS, falls back to
FALLBACK_STATUS (default 200 OK, empty body) so the client's request cycle
completes rather than hanging. NOTE: a 404 fallback
was tried and made the game fail *before* even reaching a menu (see
research/notes/net1bin-server-list.md / session 3) - an empty 200 is what
the game actually tolerates gracefully for content-delivery checks it
doesn't strictly need. Don't default this back to 404 without re-testing.

Not a real HTTP server - no range requests, no query-string handling
(matches on path only), no persistent connections.
"""
import base64
import re
import socket
import sys
import datetime
import os
import threading
import urllib.request
import urllib.error

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))
from rotating_log import RotatingLog
_DATA = os.path.join(_HERE, "data")
_LOGS = os.path.join(_HERE, "logs")
os.makedirs(_LOGS, exist_ok=True)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "http_gateway.log")
FALLBACK_STATUS = sys.argv[3] if len(sys.argv) > 3 else "200 OK"
SERVED_DIR = sys.argv[4] if len(sys.argv) > 4 else os.path.join(_DATA, "served_content")

UPSTREAM_PROXY_ENABLED = os.environ.get("TLOU_HTTP_PROXY_UPSTREAM", "1") != "0"
UPSTREAM_TIMEOUT = 20

# Hosts try_upstream_fetch() is allowed to contact. The upstream fetch exists
# only to mirror the handful of static content-delivery hosts this project's
# client redirects at this server (the S3 buckets in net1.bin's URL table and
# their naughtydog.com aliases); nothing else is ever a legitimate target.
#
# CRITICAL FIX 2026-08-20: the fetch target used to be the request's own Host:
# header verbatim, unvalidated and unauthenticated, so any request for a
# not-yet-cached path made this server fetch an ATTACKER-CHOSEN URL and cache
# the result into SERVED_DIR to be served back later. That is a plain SSRF
# (cloud metadata endpoints, loopback, anything else this host can reach) plus
# a cache-poisoning primitive for any not-yet-cached game asset path. It was
# also a self-amplifying DoS: pointing Host: at this server's own address made
# it fetch itself, miss again, and recurse - observed in production on
# 2026-08-20 as a burst of 1024 self-requests in ~5 s, the likely cause of the
# fd-exhaustion crash that MAX_CONCURRENT_HANDLERS also addresses. An
# allowlist closes both, because this server's own address can never be on it.
UPSTREAM_ALLOWED_HOSTS = frozenset({
    "s3.amazonaws.com",
    "s.s3.amazonaws.com",
    "t1.patch.s3.amazonaws.com",
    "t1.final.dev.s3.amazonaws.com",
    "t1.final.prod.s3.amazonaws.com",
    "t1ps4.final.prod.s3.amazonaws.com",
    "t1.campaign.config.s3.amazonaws.com",
    "s.naughtydog.com",
    "www.naughtydog.com",
    "t1.final.prod.naughtydog.com",
})

# Ceiling on a single upstream response held in memory / written to SERVED_DIR.
# The largest real asset this project mirrors is ~8 MB (level-1.psarc.crypt),
# so 32 MiB is generous; without a cap, an allowed host that misbehaves or is
# hijacked could stream unbounded bytes into memory and onto disk.
MAX_UPSTREAM_BYTES = int(os.environ.get("TLOU_HTTP_MAX_UPSTREAM_BYTES",
                                        str(32 * 1024 * 1024)))

# Cap on concurrent request-handler threads. Each thread holds its socket's
# file descriptor open for its whole lifetime, and a cache-miss request can
# block for up to UPSTREAM_TIMEOUT doing a live upstream fetch (see
# try_upstream_fetch / _UPSTREAM_FAIL_CACHE below) - without a cap, enough
# concurrent slow requests exhausts the process's fd limit and accept() dies
# with "Too many open files" (observed in production 2026-08-20, took the
# whole backend down via run_all's die-together supervision). Excess
# connections simply queue in the kernel's listen backlog instead of each
# grabbing an fd immediately.
MAX_CONCURRENT_HANDLERS = int(os.environ.get("TLOU_HTTP_MAX_HANDLERS", "64"))
_handler_slots = threading.Semaphore(MAX_CONCURRENT_HANDLERS)

# Negative cache for upstream fetch failures: (host, raw_path) -> fail time.
# A dead/unreachable upstream (e.g. a permanently-gone S3 bucket) previously
# got re-attempted, and re-blocked for the full UPSTREAM_TIMEOUT, on EVERY
# single request for that path - only a SUCCESSFUL fetch was ever cached to
# SERVED_DIR. That repeated-slow-block pattern is what starves
# MAX_CONCURRENT_HANDLERS/exhausts fds under real traffic. Remember failures
# for a TTL and skip straight to the fast FALLBACK_STATUS path instead.
UPSTREAM_FAIL_CACHE_TTL = int(os.environ.get("TLOU_HTTP_FAIL_CACHE_TTL", "300"))
_upstream_fail_cache = {}
_upstream_fail_cache_lock = threading.Lock()


def safe_join(base_dir, rel_path):
    """os.path.join(base_dir, rel_path), refusing anything that would land
    outside base_dir. rel_path comes straight off the wire (a URL path or a
    PUT key) with NO sanitization upstream - a request like
    `GET /../../../../etc/shadow` or `PUT /x/../../../../etc/cron.d/pwn`
    must not be allowed to read or write outside SERVED_DIR. Returns None if
    rejected. CRITICAL FIX 2026-08-20 (production server was internet-facing
    and running as root via `sudo ./run.sh` - this was an unauthenticated
    remote arbitrary file read (GET) and write (PUT, i.e. root RCE) with no
    exploitation evidence found in the log at fix time, but the server was
    live and exposed)."""
    base_real = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(base_dir, rel_path))
    if candidate != base_real and not candidate.startswith(base_real + os.sep):
        return None
    return candidate


def get_header(text, name):
    prefix = name.lower() + ":"
    for line in text.split("\r\n")[1:]:
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect that would leave UPSTREAM_ALLOWED_HOSTS.

    Allowlisting only the initial hostname would still permit an allowed host
    (or anything able to answer for it) to 302 the fetch at an internal
    address, reintroducing the SSRF one hop later. Every hop is re-checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        import urllib.parse
        target = urllib.parse.urlsplit(newurl)
        if target.scheme not in ("http", "https"):
            return None
        if (target.hostname or "").rstrip(".").lower() not in UPSTREAM_ALLOWED_HOSTS:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_upstream_opener = urllib.request.build_opener(_AllowlistRedirectHandler())


def try_upstream_fetch(host, raw_path):
    """Best-effort live fetch of the real original file. Returns bytes or None.

    `host` comes off the wire (the request's Host: header) and is only ever
    contacted if it is on UPSTREAM_ALLOWED_HOSTS - see that list for why.
    Anything else returns None with no network call at all. The URL is rebuilt
    from the matched allowlist entry rather than the raw header, so a header
    port or userinfo trick cannot redirect the fetch elsewhere.

    Recently-failed (host, raw_path) pairs are skipped for
    UPSTREAM_FAIL_CACHE_TTL seconds rather than re-attempted - see the
    _upstream_fail_cache comment above."""
    import time
    hostname = (host or "").split(":", 1)[0].strip().rstrip(".").lower()
    if hostname not in UPSTREAM_ALLOWED_HOSTS:
        return None
    host = hostname
    key = (host, raw_path)
    now = time.monotonic()
    with _upstream_fail_cache_lock:
        failed_at = _upstream_fail_cache.get(key)
    if failed_at is not None and now - failed_at < UPSTREAM_FAIL_CACHE_TTL:
        return None

    url = f"http://{host}/{raw_path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DNTG-HTTPC/1.1"})
        with _upstream_opener.open(req, timeout=UPSTREAM_TIMEOUT) as resp:
            # Read one byte past the ceiling so an over-large body is detected
            # and discarded instead of being buffered whole - see
            # MAX_UPSTREAM_BYTES.
            data = resp.read(MAX_UPSTREAM_BYTES + 1)
        if len(data) > MAX_UPSTREAM_BYTES:
            with _upstream_fail_cache_lock:
                _upstream_fail_cache[key] = now
            return None
        with _upstream_fail_cache_lock:
            _upstream_fail_cache.pop(key, None)
        return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        with _upstream_fail_cache_lock:
            _upstream_fail_cache[key] = now
        return None


# Keys build_put_response() is allowed to write. safe_join() only stops a PUT
# from escaping SERVED_DIR - it does nothing to stop a PUT from landing
# somewhere INSIDE SERVED_DIR the client has no legitimate reason to write to
# (e.g. overwriting a served game asset, or planting a new one at an
# arbitrary path to be served back to other players later). The two shapes
# below are the only PUTs this project's own client ever legitimately sends:
# a profile save (`profiles/<npid>/profile.21`) and a match-session upload
# (`games/<npid>.<unix-timestamp>`) - see put_key_from_path's doc and
# server/data/served_content/{profiles,games}/ for the real shapes on disk.
# Sony's online-ID rule (3-16 chars, letters/digits/hyphen/underscore)
# informs the id pattern, but the pattern below deliberately allows 1-16
# rather than enforcing the 3-char minimum: this is an allowlist whose job
# is to bound WHERE a PUT can land, not to validate account names, and
# being slightly more permissive than the real-world minimum keeps short
# local test ids working (`__selftest__`, this project's own smoke-test id,
# fits either way). The character class and the 16-char ceiling are what
# actually matter - neither admits a path separator or a `..` segment.
_NPID = r"[A-Za-z0-9_-]{1,16}"
PUT_KEY_ALLOWLIST = (
    re.compile(rf"^profiles/{_NPID}/profile\.21$"),
    re.compile(rf"^games/{_NPID}\.\d{{1,16}}$"),
)


def put_key_allowed(key):
    return any(pattern.match(key) for pattern in PUT_KEY_ALLOWLIST)


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
    allowed = bool(key) and put_key_allowed(key)
    file_path = safe_join(SERVED_DIR, key) if allowed else None
    stored = 0
    note = " (PUT empty)"
    if key and body is not None and not allowed:
        note = " (PUT rejected: key not on the allowlist)"
    elif key and body is not None and file_path is not None:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(body)
        stored = len(body)
        note = " (PUT stored)"
    elif key and body is not None:
        note = " (PUT rejected: path escapes SERVED_DIR)"
    header = (
        f"HTTP/1.1 200 OK\r\n"
        f"Content-Length: 0\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii")
    return header, key, stored, note


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
    file_path = safe_join(SERVED_DIR, path) if path else None

    upstream_note = ""
    if path and file_path is None:
        upstream_note = " (rejected: path escapes SERVED_DIR)"
    elif path and not os.path.isfile(file_path) and UPSTREAM_PROXY_ENABLED:
        host = get_header(text, "Host")
        if host and host.split(":", 1)[0].strip().rstrip(".").lower() not in UPSTREAM_ALLOWED_HOSTS:
            upstream_note = f" (upstream fetch refused: {host!r} not an allowed upstream host)"
        elif host:
            fetched = try_upstream_fetch(host, raw_path.lstrip("/"))
            if fetched is not None:
                os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(fetched)
                upstream_note = f" (live-fetched from {host}, cached)"
            else:
                upstream_note = f" (live fetch from {host} failed)"

    if path and file_path is not None and os.path.isfile(file_path):
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
        # Release the accept slot first: a failure while closing must not
        # permanently retire a slot.
        _handler_slots.release()
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}, serving from {SERVED_DIR}, "
          f"max {MAX_CONCURRENT_HANDLERS} concurrent handlers", flush=True)

    log_lock = threading.Lock()
    with RotatingLog(LOG_PATH) as log:
        while True:
            # Gate ACCEPT on the semaphore, not just the handler thread: a
            # connection we haven't accepted() yet holds no fd of ours and
            # simply waits in the kernel's listen backlog, so a burst of
            # slow (upstream-fetch-bound) requests queues there instead of
            # each grabbing an fd immediately - see MAX_CONCURRENT_HANDLERS.
            _handler_slots.acquire()
            conn, addr = srv.accept()
            threading.Thread(target=handle, args=(conn, addr, log, log_lock), daemon=True).start()

if __name__ == "__main__":
    main()
