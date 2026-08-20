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
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))
from rotating_log import RotatingLog, capped_appender
_LOGS = os.path.join(_HERE, "logs")
os.makedirs(_LOGS, exist_ok=True)
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "voice_server.log")

GUESSED_REPLY = b"+OK\n"

# Ceiling on the per-connection log block held in memory before it is written
# out at connection close. The real client sends one 6-byte `hello\n` and then
# goes quiet, so this never truncates legitimate traffic - but this port takes
# raw unauthenticated connections with no handshake, so `yes | nc host 7313`
# previously grew the block without bound until the process was OOM-killed
# (which takes the whole backend down through run_all's die-together
# supervision). Past the cap the block keeps only a count of what it dropped.
MAX_LOG_CHARS = int(os.environ.get("TLOU_VOICE_MAX_LOG_CHARS", str(64 * 1024)))

# Cap on concurrent handler threads, gating accept() rather than just the
# thread start: an unaccepted connection holds no file descriptor of ours and
# simply waits in the kernel's listen backlog, so a flood of idle connections
# cannot exhaust this process's fd limit. Same pattern and reasoning as
# http_gateway.py's MAX_CONCURRENT_HANDLERS. One real client opens a single
# connection here, so 64 is already far above any legitimate load.
MAX_CONCURRENT_HANDLERS = int(os.environ.get("TLOU_VOICE_MAX_HANDLERS", "64"))
_handler_slots = threading.Semaphore(MAX_CONCURRENT_HANDLERS)


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()
    append, finish = capped_appender(
        f"==== {ts} PORT-7313 connection from {addr[0]}:{addr[1]} ====\n",
        MAX_LOG_CHARS, "log characters")
    try:
        conn.settimeout(15)
        while True:
            data = conn.recv(4096)
            if not data:
                append("  (connection closed by peer)\n")
                break
            append(f"-- recv ({len(data)} bytes) --\n  {data!r}\n")
            conn.sendall(GUESSED_REPLY)
            append(f"-- sent guessed reply ({len(GUESSED_REPLY)} bytes) --\n  {GUESSED_REPLY!r}\n")
    except (socket.timeout, OSError) as e:
        append(f"  (idle/error: {e})\n")
    finally:
        # Release the accept slot first: a failure while closing or logging
        # must not permanently retire a slot.
        _handler_slots.release()
        conn.close()
        entry = finish()
        with log_lock:
            print(entry, flush=True)
            log.write(entry + "\n")
            log.flush()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Port-7313 stub listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}, "
          f"max {MAX_CONCURRENT_HANDLERS} concurrent handlers", flush=True)

    log_lock = threading.Lock()
    with RotatingLog(LOG_PATH) as log:
        while True:
            _handler_slots.acquire()
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
