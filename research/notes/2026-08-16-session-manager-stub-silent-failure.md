# `session_manager_stub.py` went silent mid-handshake for one client attempt: cause unconfirmed, fix was a blind restart

**Status: NOT root-caused.** This note records a real, reproduced-once failure and
the evidence trail around it, but the actual triggering bug is unknown and the
evidence needed to identify it is gone. Written up so a future session doesn't
have to re-derive the same dead end, and so "it just started working again" isn't
mistaken for "it's fixed."

## Symptom (live, in-game)

RPCS3 TTY log showed the client successfully connecting to our session-manager
stub, then failing:

```
connect to 192.168.1.100:7314 ...
connect ok
recv() failed (errno=35)
Error 9
g_pSessionManager->Init()() failed. ret = 0xffffffff
```

`errno=35` is `EAGAIN` - the client's `recv()` timed out waiting for a reply that
never came, not a dead/refused connection (that would be the already-documented
`s=-1` failure mode from `docs/protocol/session_manager_and_matchmaking.md`).
This is a different failure than the one that doc already covers.

## What the stub's own log showed

`captures/tcp_catch.log` confirmed the stub *did* receive and correctly parse the
client's hello (opcode `0x12d`, `np_id` decoded as `comradesean`) - but the log
just stops there. No `-- sent server_hello --` line, no exception, no error of
any kind. The handler goes silent between logging the parsed hello and the
`conn.sendall(resp)` call immediately after it in `session_manager_stub.py`
(`handle()`, around line 458-469) - a span of code with no obvious way to fail
(`threading.Event()`, a `struct.pack`, a `sendall`).

## Why there's no traceback to look at

`handle()`'s exception handler (`session_manager_stub.py:655`) only catches
`(ConnectionError, socket.timeout, OSError)` - not a bare `except Exception`. If
something else threw, Python prints the traceback to stderr by default.

That process had been started earlier that day as
`python3 session_manager_stub.py 7314 2>&1 | head -5 &` - `head -5` exits after
its first 5 lines and closes its read end. By the time (if) a later exception
fired, that pipe was long broken, so any traceback aimed at stderr would have
been silently discarded rather than ever appearing anywhere. This is a plausible
mechanism for "no error, anywhere, at all" - not confirmed, since the actual
exception is unrecoverable at this point.

## The "fix"

Killed the stub process and restarted it identically, only with stdout/stderr
redirected to a real file instead of piped through `head`. The very next client
attempt succeeded normally (hello received, `server_hello` sent, `ClientHello2`
and `Ping` both logged correctly afterward - a clean, complete exchange).

**This is not a confirmed fix for a known bug.** It's equally consistent with:
a genuine bug in the handler that a clean process happened to not hit again, or
long-lived process/thread state (across everything else run through that same
process tonight - repacking `net1.bin`, other stub restarts, etc.) that a fresh
process simply didn't inherit. No way to distinguish these from what's logged.

## How to apply

If this recurs: this time it should actually be visible, since no currently-running
stub's output is piped through anything that can eat a traceback silently. If a
repeat happens with a clean log and still shows no error, that itself is a
finding (points at something worse than an uncaught exception - e.g. a deadlock
on `log_lock`, since `emit()`'s `with log_lock:` would block forever if some
other code path acquired it without the `with` pattern - not currently checked).
Worth widening `handle()`'s except clause to a bare `except Exception` regardless,
purely so any future occurrence self-reports instead of depending on how the
process happened to be launched.
