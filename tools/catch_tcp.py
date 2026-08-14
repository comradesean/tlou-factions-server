#!/usr/bin/env python3
"""Minimal raw TCP listener for observing an unknown binary protocol.
Accepts connections, logs everything received (hex + best-effort ASCII) with
timestamps, and keeps the connection open (does not send anything back)
unless a reply is supplied via REPLY_HEX. Not a real server - no protocol
knowledge, just observation.
"""
import socket
import sys
import datetime
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7320
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/tcp_catch.log"


def hexdump(data):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:08x}  {hexpart:<48}  {asciipart}")
    return "\n".join(lines)


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()
    entry = f"==== {ts} connection from {addr[0]}:{addr[1]} ====\n"
    try:
        conn.settimeout(10)
        while True:
            try:
                data = conn.recv(65536)
            except socket.timeout:
                entry += "  (10s idle, closing)\n"
                break
            if not data:
                entry += "  (connection closed by peer)\n"
                break
            entry += f"-- {len(data)} bytes received --\n{hexdump(data)}\n"
    except OSError as e:
        entry += f"  (socket error: {e})\n"
    finally:
        conn.close()
        with log_lock:
            print(entry, flush=True)
            log.write(entry + "\n")
            log.flush()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()

if __name__ == "__main__":
    main()
