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
import socket
import sys
import datetime
import os
import urllib.request
import urllib.error

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/http_catch.log"
FALLBACK_STATUS = sys.argv[3] if len(sys.argv) > 3 else "200 OK"
SERVED_DIR = sys.argv[4] if len(sys.argv) > 4 else "/mnt/f/ClaudeHole/tlou_factions/tools/served_content"

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


def build_response(request_line, text):
    parts = request_line.split()
    if len(parts) < 2 or parts[0] != "GET":
        return (f"HTTP/1.1 {FALLBACK_STATUS}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").encode("ascii"), "", 0, ""

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


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}, serving from {SERVED_DIR}", flush=True)

    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
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

                text = data.decode("latin1", errors="replace")
                request_line = text.split("\r\n", 1)[0] if text else ""

                entry = f"==== {ts} from {addr[0]}:{addr[1]} ====\n{text}\n"
                response, matched_path, served_len, upstream_note = build_response(request_line, text)
                entry += f"---- responded: {'served ' + str(served_len) + ' bytes for ' + matched_path if served_len else FALLBACK_STATUS}{upstream_note} ----\n"
                print(entry, flush=True)
                log.write(entry + "\n")

                try:
                    conn.sendall(response)
                except OSError:
                    pass
            finally:
                conn.close()

if __name__ == "__main__":
    main()
