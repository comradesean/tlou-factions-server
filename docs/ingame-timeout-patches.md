# In-game timeout / kick patches

> **DO NOT APPLY. THESE PATCHES CRASH THE GAME.**
>
> Status corrected 2026-08-18. They were derived statically and never
> validated on a running client; applying them crashed the game. The
> referenced patch file `client/patches/ingame_timeouts_patch.yml` is
> deliberately NOT tracked in git for that reason, so this document describes
> an artifact you will not find in the repo.
>
> This file is kept only for the RESEARCH in it - the located timeout branches
> and their addresses are believed correct and are useful for understanding the
> shipped timeouts. The PATCHES built from them are not.
>
> Join-in-progress was solved on 2026-08-18 without any client timeout patch;
> see research/notes/2026-08-18-jip-handoff.md. There is no known reason to
> revive these.

Client-side (RPCS3) patches that disable the in-game and matchmaking-flow
timeouts which otherwise boot a player out of a session or a matchmaking wait.
Intended for multi-client join-in-progress development testing, where a session
must be held open longer than the shipped timeouts allow. Patch file:
`client/patches/ingame_timeouts_patch.yml`.

- **Status:** BROKEN, do not apply (see the warning above). The
  original claim was "testing-only", which understated it. Each patch neutralizes a single timeout branch and
  preserves genuine user / host / error / status leaves.
- **Address convention:** every address is the VMA, which equals the RPCS3
  effective address and the offset shown in `research/disasm/full.asm` (no
  `+0x10000` shift). Bytes were read directly off the disassembly.
- **No AFK/idle kick exists.** A full sweep of the leave guards found no
  controller-input / activity timer. The in-session timers below difference a
  real wall/frame-tick counter against a stored start-tick, so they fire on
  elapsed real time regardless of input.

## The patches

| Address | Mechanism | Original → new | Effect |
|---|---|---|---|
| `0x00352c60` | In-session **peer-heartbeat** timeout (per-frame session update `FUN_00351b0c`; tests peer last-response stamp at `obj+0xa4`). | `beq cr7,0x352cfc` (`41 9e 00 9c`) → `b 0x352cfc` (`48 00 00 9c`) | The "peer hasn't responded in N s → drop" arm no longer commits a leave. The bad-vtable-status leaves into the same block are preserved. |
| `0x0035dc04` | In-session **timer-state** timeout (`FUN_0035db20`; `IsTimerElapsed`, tick source `obj+0xf8`). | `bne cr7,0x35dc38` (`40 9e 00 34`) → `nop` (`60 00 00 00`) | Timeout no longer forces the leave; the normal state-flag path (`obj+1012`) still leaves when that flag is set. |
| `0x003cac90` | **P2P peer-drop → party leave.** Party state-machine state 2 (`FUN_003ca9d0`) reads a dead-connection code (3) derived from whether the NP-signaling handle `obj+0x10` exists; a dead handle routes to state 6 (leave). | `cmpwi r3,3` (`2f 83 00 03`) → `cmpwi r3,0` (`2f 83 00 00`) | The return is always 1/2/3, so `==0` is never true and the state-6 leave is never entered on a peer drop. A dead conn instead routes to state 8 (limbo, no forced leave). Does not resurrect a genuinely-dropped PSN/RPCN link. |
| `0x003b4d24` | **GAME_LIST_WAIT 60.0 s** (`FUN_003b4bf4`; float const `0x01269c48` = 60.0). Elapsed → error dialog → LEAVE_GAME. | `beq cr7,0x3b4dc8` (`41 9e 00 a4`) → `b 0x3b4dc8` (`48 00 00 a4`) | The "no game found in 60 s" boot is skipped; the wait polls again next frame. |
| `0x003b6620` | **CONNECT_TO_HOST 30.0 s** (`FUN_003b6584`, state 8; float const `0x01269c38` = 30.0). | `beq cr7,0x3b69dc` (`41 9e 03 bc`) → `b 0x3b69dc` (`48 00 03 bc`) | Keeps dialing the host instead of aborting. Only the still-connecting arm is affected. |
| `0x003b6514` | **RESERVE_SLOTS_WAIT 6.0 s** (`FUN_003b6404`, state 10; deadline `now + 6.0`, float const `0x01269cbc`). Elapsed → "Joining Request timed out" → state 7. | `blt cr7,0x3b6530` (`41 9c 00 1c`) → `nop` (`60 00 00 00`) | Falls through to the normal still-waiting path; the join-request timeout no longer fires. |

## Do NOT enable

| Address | Why not |
|---|---|
| `0x003caf50` | The 5.0 s watchdog here (`FUN_003ca9d0` state 6; float const `0x0126a320` = 5.0) only runs when the session is **already leaving** — it force-commits a stalled graceful teardown, it does not *initiate* a leave. NOPing it can hang an intended teardown, so it is left commented out in the patch file. |

## Notes and limits

- **No single choke point.** The timeout arms call `LEAVE_GAME` (`0xad0ca8`)
  directly as well as through `RequestLeave` (`0x3c9bdc`), and `LEAVE_GAME` has
  ~40 legitimate callers (user/host/error leaves), so it cannot be neutralized
  wholesale. The per-site branch patches are the surgical option.
- **Unresolved thresholds.** The exact second-values for `0x00352c60` and
  `0x0035dc04` load via SDA/TOC-relative addressing (`lfs -31264(r30)` /
  `lfs -32468(r30)`) and were not resolved from the text-only disassembly; they
  are confirmed timeout compares. The patches disable the branch and do not
  depend on the value. To read the numbers, resolve the TOC in a
  TOC-aware disassembler or break on `0x352c50` / `0x35dbf4` and read `f1`.
- **Not a JIP fix.** These stop a tester from being *timed out* while sitting in
  a session. They do not fix the separate join-in-progress teardown, whose root
  cause is a server-side roster bug — see
  `research/notes/2026-08-18-jip-roster-collision.md`.
- The pre-match SERVER_LOBBY minimum-count teardown (`FUN_003b7a78`,
  `count < min → LEAVE_GAME`) is a different mechanism, covered by
  `client/patches/minplayers_patch.yml`.

## Applying in RPCS3

Copy the patch under RPCS3's patch directory (or merge into `patch.yml`), then
enable "TLOU Factions - disable in-game timeouts" in the Patch Manager and reboot
the game so patches reload. RPCS3 keys patches by their title string under the
game's PPU hash; renaming a patch makes it a new entry that must be re-enabled.
