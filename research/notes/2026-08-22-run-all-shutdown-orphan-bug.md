# `run_all.py` leaving `session_manager.py` orphaned on every shutdown - root-caused and fixed

Reported symptom: every time the backend was stopped (`Ctrl-C` on
`./run.sh`, no `-d`) and restarted, `session_manager.py` specifically failed
to bind port 7314 (`OSError: [Errno 98] Address already in use`). Not
intermittent - reproduced on every single restart across the session this
was diagnosed in.

## Root cause

`server/run_all.py`'s `_shutdown()`:

```python
def _shutdown(*_):
    for p in _procs:
        if p.poll() is None:
            p.terminate()
    sys.exit(0)
```

Sends `SIGTERM` to every child, then exits **immediately** - no wait for any
child to actually finish. `run.sh`'s default (non-`-d`) path uses
`exec "$PY" "$HERE/server/run_all.py"`, replacing the shell with
`run_all.py` directly, so `run_all.py` IS the terminal's foreground process.
The instant it exits via that immediate `sys.exit(0)`, the terminal/session
it was attached to can go away while children are still mid-shutdown -
`session_manager.py` does real work on `SIGTERM`
(`drain_rooms_for_shutdown`: walks every still-tracked room and notifies
surviving members before exiting, see that function's own docstring for why
the drain exists at all). If a child's shutdown code hits a write to a
stdout pipe that's already gone, uncaught, it can be left alive, orphaned
(re-parented, no controlling TTY - confirmed live via `ps aux` showing `?`
in the TTY column for the stuck process), still bound to its port,
indefinitely.

This was diagnosed live: an orphaned `session_manager.py` (PID confirmed via
`ps aux`, TTY `?`) sat bound to port 7314 for 45+ minutes with zero new log
activity - not slow, not still draining, genuinely never signaled in a way
it could act on, or signaled and then stuck.

## Fix

Two changes, `server/run_all.py` and `server/session_manager.py`:

1. **`run_all.py`'s `_shutdown()` now waits.** `terminate()` every child,
   then `wait(timeout=SHUTDOWN_TIMEOUT)` (15s) for each in turn, escalating
   to `kill()` (`SIGKILL`) + a blocking `wait()` for anything still alive
   past that. The parent process can no longer exit while a child might
   still be running, and a genuinely stuck child gets forced down
   automatically instead of orphaned forever.
2. **`session_manager.py`'s own shutdown handler hardened**, defense in
   depth in case something upstream ever bypasses `run_all.py`'s wait (e.g.
   a direct `kill` by PID):
   - A `_shutting_down` guard so a second overlapping signal exits
     immediately (`os._exit`) instead of re-entering
     `drain_rooms_for_shutdown` reentrantly mid-drain.
   - The drain call is wrapped so ANY exception during shutdown can't
     prevent `sys.exit(0)` from being reached.
   - `drain_rooms_for_shutdown`'s own `_both()` logging helper (added
     earlier the same session for room-count/timing visibility - see
     `research/notes/2026-08-21` era work) now guards its `print()` call
     against `OSError` the same way its log-file write already did, so a
     broken stdout pipe can't derail the drain.

## Verification

Restarted the backend after the fix (`sudo ./run.sh`, `Ctrl-C`, `sudo
./run.sh` again) - clean bind on the first try, no orphan, all 5 processes
attached to the new terminal (confirmed via `ps aux` TTY column showing the
real pts, not `?`).

## Note on the exact failure mechanism

The precise reason a stuck child's shutdown code hung rather than crashing
loudly (which would have still freed the port, just noisily) was not
pinned down to certainty - plausible candidates include a broken-pipe
exception being silently absorbed somewhere in the call chain, or signal
re-entrancy from an overlapping SIGINT/SIGTERM pair. The fix in `run_all.py`
makes this moot regardless of the exact mechanism: children can no longer
be exited-past by their parent, and a stuck one is force-killed within a
bounded time either way.
