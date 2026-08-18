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

_procs = []


def _shutdown(*_):
    for p in _procs:
        if p.poll() is None:
            p.terminate()
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
