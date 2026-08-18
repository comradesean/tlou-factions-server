#!/usr/bin/env python3
"""Stub for a fourth, previously-unknown service on port 7313.

Found live: right after NAT-type detection ("Nat Type = 2" in the TTY log),
NetInit (FUN_003557a8) makes a ONE-SHOT, never-retried `connect() ` to this
port on the same redirected host as everything else - unlike ticket-server
(7320), Session Manager (7314), or the location service (7312), which all
retry on a steady cadence, this one fails once (`Connection refused` when
nothing listens) and the log goes completely silent afterward. That silent-
after-one-failure shape is a strong match for the "connecting..." bar filling
and then hanging forever with no error: whatever this is, the client isn't
built to tolerate it being unreachable.

KNOWN UNCERTAINTY - not fully decompiled, empirically probed instead:
- Ghidra: the connect() itself is `FUN_003d7890` (service-descriptor slot
  `+0x58`, same TOC-chain-resolved table as `+0x5c`=Session Manager/7314,
  `+0x54`=leaderboard-server, `+0x50`=facebook-server per
  docs/protocol/session_manager_and_matchmaking.md). `FUN_003d7890` itself
  only connects and, on success, spawns a background PPU thread to do the
  actual protocol work - the thread entry function was not resolved this
  pass. A structurally similar sibling, `FUN_0035363c` (different slot,
  `+0x4c`), does a plaintext send/recv where the response is validated by
  checking `response[0] == '+'` - suggests a simple line-based ack
  convention, same family as the confirmed-plaintext `heartbeat`/
  `get-location` commands, not a binary/framed protocol.
- Empirically confirmed via a live capture this pass: the client sends
  literal ASCII `hello\n` (6 bytes) after connecting. No prior art in this
  repo named this port or protocol before now.
- This stub's reply (`+OK\n`) is an EDUCATED GUESS based on the `'+'` prefix
  check above - not confirmed against a real observed success path. If the
  client still hangs after this, capture what it sends next (or whether it
  sends anything else at all) and adjust - see
  `research/notes/2026-08-14-voice-server-discovery.md` for the full method
  and where to pick this up.
"""
import socket
import sys
import datetime
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7313
import os
_LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOGS, exist_ok=True)
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "voice_server.log")

GUESSED_REPLY = b"+OK\n"


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()
    entry = f"==== {ts} PORT-7313 connection from {addr[0]}:{addr[1]} ====\n"
    try:
        conn.settimeout(15)
        while True:
            data = conn.recv(4096)
            if not data:
                entry += "  (connection closed by peer)\n"
                break
            entry += f"-- recv ({len(data)} bytes) --\n  {data!r}\n"
            conn.sendall(GUESSED_REPLY)
            entry += f"-- sent guessed reply ({len(GUESSED_REPLY)} bytes) --\n  {GUESSED_REPLY!r}\n"
    except (socket.timeout, OSError) as e:
        entry += f"  (idle/error: {e})\n"
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
    print(f"Port-7313 stub listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
