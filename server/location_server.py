#!/usr/bin/env python3
"""Location service stub (port 7312) - plaintext get-location <npid> query.

Found live: the client opens a raw, unencrypted, unframed TCP connection here
independently of ticket-server (7320) and Session Manager (7314), sends a
single line `get-location <npid>\\n`, then closes. It retries on a steady
~5s cadence starting well before the level-content-sync/matchmaking flow -
including while it was getting Connection refused (nothing listened here
before this stub existed) - so this looks like a periodic background poll,
not something the "connecting..." UI is blocked on. Confirmed via eboot
strings (research/strings/strings_ascii.txt around VMA 0xe69df0): `location`,
`latitude = %f, longitude = %f` sit immediately above `heartbeat`/`heartbeat
%s` (the already-solved plaintext command sent over ticket-server's encrypted
channel) and `GetLocation`/`get-location %s` themselves - same plaintext
"<command> <arg>\\n" convention, just on its own raw port instead of wrapped
in ticket-server's ARX-encrypted frames.

KNOWN UNCERTAINTY: the response wire format has not been decompiled. The
`latitude = %f, longitude = %f` string is only confirmed to be how the
client logs whatever it parsed - not confirmed to be the literal reply
format. Current guess (a plain "<lat> <long>\\n" text line) was tried live
and did not stop the retry loop, but the loop didn't stop when unanswered
either, which is consistent with this just being a periodic poll rather than
a blocking wait - i.e. inconclusive either way. Revisit with a decompile of
the `GetLocation %s` call site if the real blocker turns out to be here
after all.
"""
import socket
import sys
import datetime
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7312
import os
_LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOGS, exist_ok=True)
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "location_server.log")

REPLY = b"0.000000 0.000000\n"


# How long to wait for the client's own FIN after replying, before giving up
# and closing from this side. The client polls every ~5 s and closes promptly,
# so this only bounds a misbehaving peer.
LINGER_SECONDS = 10.0


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()
    entry = f"==== {ts} LOCATION connection from {addr[0]}:{addr[1]} ====\n"
    try:
        conn.settimeout(5)
        data = conn.recv(4096)
        entry += f"-- recv ({len(data)} bytes) --\n  {data!r}\n"
        if data:
            conn.sendall(REPLY)
            entry += f"-- sent reply ({len(REPLY)} bytes) --\n  {REPLY!r}\n"
            # LET THE CLIENT CLOSE FIRST (2026-08-19). This stub used to
            # close() the moment it had replied, which the client sees as an
            # ECONNRESET on its next read - visible in its own log as
            # `sys_net: Socket error ECONNRESET` every ~5 s, once per poll,
            # from the first minute of every session. It is the same
            # server-initiated-close mistake that broke the leaderboard
            # channel, where an EOF from us drove the client's error path
            # ("Error 9 / disconnected from the game servers"); the location
            # poll happens to tolerate it, but there is no reason to keep
            # provoking it. The client's own contract is send-then-close, so
            # wait for its FIN and let the close be its idea.
            conn.settimeout(LINGER_SECONDS)
            try:
                while conn.recv(4096):
                    pass
                entry += "-- client closed (clean FIN)\n"
            except socket.timeout:
                entry += (f"-- client still open after {LINGER_SECONDS:g}s idle,"
                          f" closing from this side\n")
    except (socket.timeout, OSError) as e:
        entry += f"  (error/early close: {e})\n"
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
    print(f"Location stub listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
