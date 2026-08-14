#!/usr/bin/env python3
"""Minimal raw-socket HTTP catcher for observing what a redirected hostname
actually requests, and serving real files back when we have them.

Parses the request line for the path, strips the leading '/', and looks for
a matching file under SERVED_DIR (default tools/served_content/). If found,
serves it with a real Content-Length and application/octet-stream. If not
found, replies with FALLBACK_STATUS (default 404 Not Found, empty body) so
the client's request cycle completes rather than hanging.

Not a real HTTP server - no range requests, no query-string handling
(matches on path only), no persistent connections.
"""
import socket
import sys
import datetime
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/http_catch.log"
FALLBACK_STATUS = sys.argv[3] if len(sys.argv) > 3 else "404 Not Found"
SERVED_DIR = sys.argv[4] if len(sys.argv) > 4 else "/mnt/f/ClaudeHole/tlou_factions/tools/served_content"


def build_response(request_line):
    parts = request_line.split()
    if len(parts) < 2 or parts[0] != "GET":
        return (f"HTTP/1.1 {FALLBACK_STATUS}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").encode("ascii")

    path = parts[1].split("?", 1)[0].lstrip("/")
    file_path = os.path.join(SERVED_DIR, path)

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
        return header + body, path, len(body)

    header = (
        f"HTTP/1.1 {FALLBACK_STATUS}\r\n"
        f"Content-Length: 0\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii")
    return header, path, 0


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
                response, matched_path, served_len = build_response(request_line)
                entry += f"---- responded: {'served ' + str(served_len) + ' bytes for ' + matched_path if served_len else FALLBACK_STATUS} ----\n"
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
