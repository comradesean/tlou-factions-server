#!/usr/bin/env python3
"""Supervisor: bring the whole TLOU Factions revival backend up with one command.

Starts every server as a subprocess and waits. Ctrl-C / SIGTERM stops them all.
Used directly (`python3 server/run_all.py`) and as the Docker container CMD.

Note: http_gateway binds port 80, which needs privilege - run with sudo, or use
the Docker setup (`docker compose up`), where the container runs as root.
"""
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# (script, default port). Ports the game connects to (net1.bin service table +
# hardcoded S3/graph hosts redirected here via RPCS3's IP/Hosts switches):
#   80    http_gateway     S3 content mirror + Facebook Graph API stand-in
#   7320  ticket_server    NP ticket handshake + leaderboard + facebook-server
#   7314  session_manager  matchmaking / room / party
#   7312  location_server
#   7313  voice_server
SERVERS = [
    ("http_gateway.py", "80"),
    ("ticket_server.py", "7320"),
    ("session_manager.py", "7314"),
    ("location_server.py", "7312"),
    ("voice_server.py", "7313"),
]

# Ceiling on how long any one child gets to exit cleanly after SIGTERM before
# being force-killed. session_manager.py's own room drain is itself bounded
# (2s per stale connection, see close_room_and_notify's notify_timeout), so a
# well-behaved shutdown should finish in well under this even with several
# rooms to drain; this is a backstop against a genuinely stuck child, not the
# expected common case.
SHUTDOWN_TIMEOUT = 15

_procs = []


def _shutdown(*_):
    """Stop every child, and - critically - WAIT for each to actually exit
    before this process does.

    BUG FIXED 2026-08-22, reported as "I have to clear things every time I
    run the server": the previous version called p.terminate() and then
    sys.exit(0) immediately, with no wait at all. Because run.sh execs this
    script directly (replacing the shell), the instant this process exited,
    the terminal/session it was attached to could go away while children
    were still mid-shutdown - session_manager.py in particular does real
    work on SIGTERM (draining active rooms, see drain_rooms_for_shutdown),
    and if a child's own shutdown code hit a write to a now-invalid stdout
    pipe uncaught, it would never reach ITS OWN sys.exit(0) and be left
    running forever, orphaned (re-parented, no controlling TTY) and still
    bound to its port - exactly the "Address already in use" on next start
    this bug report described, reliably reproducible on every run.

    Now: terminate() every child, wait up to SHUTDOWN_TIMEOUT seconds each
    for a clean exit, and kill() (SIGKILL) anything still alive after that -
    so this process never exits while a child might still be alive, and a
    child that's genuinely stuck (not just slow) gets forced down rather
    than orphaned.
    """
    for p in _procs:
        if p.poll() is None:
            p.terminate()
    for p in _procs:
        if p.poll() is None:
            try:
                p.wait(timeout=SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                print(f"[run_all] pid {p.pid} did not exit within "
                      f"{SHUTDOWN_TIMEOUT}s of SIGTERM - sending SIGKILL",
                      flush=True)
                p.kill()
                p.wait()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    for script, port in SERVERS:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, script), port])
        _procs.append(p)
        print(f"[run_all] started {script} on :{port} (pid {p.pid})", flush=True)
    print(f"[run_all] {len(_procs)} servers up. Ctrl-C to stop all.", flush=True)
    # Block until a server exits; if one dies, take the rest down so it's visible.
    while True:
        for p in _procs:
            if p.poll() is not None:
                print(f"[run_all] {p.args[-2] if len(p.args) > 1 else p.pid} exited "
                      f"(rc={p.returncode}); shutting the backend down.", flush=True)
                _shutdown()
        try:
            _procs[0].wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


if __name__ == "__main__":
    main()
