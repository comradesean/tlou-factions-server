#!/usr/bin/env python3
"""Raw TCP listener/responder for observing an unknown binary protocol.
Accepts connections, logs everything received (hex + best-effort ASCII) with
timestamps. By default sends nothing back (pure observation). Pass --echo to
mirror each received chunk back verbatim, or --reply-hex <hex> to send a
fixed byte string back after the first chunk received per connection - both
are for empirically probing an unknown response format one guess at a time,
not real protocol knowledge.
"""
import argparse
import socket
import sys
import datetime
import threading


def hexdump(data):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:08x}  {hexpart:<48}  {asciipart}")
    return "\n".join(lines)


def handle(conn, addr, log_lock, log, args):
    ts = datetime.datetime.now().isoformat()
    entry = f"==== {ts} connection from {addr[0]}:{addr[1]} ====\n"
    replied = False
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

            if args.echo:
                conn.sendall(data)
                entry += f"-- echoed {len(data)} bytes back --\n"
            elif args.reply_hex is not None and not replied:
                reply = bytes.fromhex(args.reply_hex)
                conn.sendall(reply)
                entry += f"-- sent {len(reply)}-byte reply --\n{hexdump(reply)}\n"
                replied = True
    except OSError as e:
        entry += f"  (socket error: {e})\n"
    finally:
        conn.close()
        with log_lock:
            print(entry, flush=True)
            log.write(entry + "\n")
            log.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", type=int, default=7320)
    ap.add_argument("logfile", nargs="?",
                     default="/mnt/f/ClaudeHole/tlou_factions/captures/tcp_catch.log")
    ap.add_argument("--echo", action="store_true",
                     help="mirror every received chunk back verbatim")
    ap.add_argument("--reply-hex", default=None,
                     help="send this fixed hex-decoded byte string back once, "
                          "after the first chunk received on each connection")
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(5)
    mode = "echo" if args.echo else (f"reply-hex ({len(args.reply_hex)//2} bytes)" if args.reply_hex else "passive/log-only")
    print(f"Listening on 0.0.0.0:{args.port} [{mode}], logging to {args.logfile}", flush=True)

    log_lock = threading.Lock()
    with open(args.logfile, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log, args), daemon=True)
            t.start()

if __name__ == "__main__":
    main()
