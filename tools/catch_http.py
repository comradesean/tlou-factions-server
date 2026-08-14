#!/usr/bin/env python3
"""Minimal raw-socket HTTP catcher for observing what a redirected hostname
actually requests. Logs the full raw request to stdout and to a log file,
then replies with a generic 200 so the client's request cycle completes
rather than hanging. Not a real HTTP server - just enough to see what's sent.
"""
import socket
import sys
import datetime

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/http_catch.log"

RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}", flush=True)

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
                            # crude: stop after headers unless Content-Length says more
                            break
                except socket.timeout:
                    pass

                entry = f"==== {ts} from {addr[0]}:{addr[1]} ====\n{data.decode('latin1', errors='replace')}\n"
                print(entry, flush=True)
                log.write(entry + "\n")

                try:
                    conn.sendall(RESPONSE)
                except OSError:
                    pass
            finally:
                conn.close()

if __name__ == "__main__":
    main()
