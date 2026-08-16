# Session handoff — solo-host live-testing marathon (2026-08-16)

Long live-testing session against a real RPCS3 client (`comradesean`), later
joined by a second real account (`mgnomad2`) for genuine 2-player testing. This
note is the entry point for picking this up again — read it before re-deriving
anything below, most of which has its own dedicated note with full evidence.

## Confirmed and fixed this session

1. **Id-gate staleness from leftover refresher threads** — `session_manager_stub.py`'s
   `start_member_refresher()` background thread never stopped itself, so a prior
   room's refresher kept re-writing the client's room-slot id nonzero even after
   that room was abandoned, breaking the id-gate check (`0x00ad7b14`) for every
   subsequent "host again" attempt on the same connection. Fixed: each room now
   gets its own `stop_event`, explicitly stopped on the next `RoomCreate` or on
   `0x133` (room abandon). **Live-confirmed real** (via RPCS3 register/memory dumps),
   but did **not** fully eliminate the intermittent "Lobby Server Error" on a first
   attempt — a second, still-unconfirmed race (client-side room-slot registration
   timing) also contributes. A 250ms delay before replying to `RoomCreate` was
   added as an untested mitigation for that second race — no clear signal either
   way yet.

2. **`RoomCreate` wire offset `0xb0:0xb2` = team selection, CONFIRMED** —
   `0x0000`=unset, `0x0001`=Blue, `0x0002`=Red. ~24 live captures, zero
   exceptions, spanning every map and both teams. See
   `2026-08-16-team-selection-field-confirmed.md`. This was found by mistake
   while chasing a *different*, wrong field (`0xc`, previously mislabeled
   "map_id" — see below) — **`0xc` is NOT reliably map or team**, that whole
   theory from `2026-08-15` is now disputed, see `2026-08-16-map-id-vs-team-confound.md`.

3. **`0x144`/`HostRank` implemented** — a confirmed-real server→client message
   this project's stub had simply never sent, despite the client sending its
   `0x143` counterpart. Now echoes the client's own 128-byte payload back. Live
   correctness unconfirmed — the trigger condition for the client sending `0x143`
   at all has not fired once in ~30 solo-host attempts tonight, so this fix has
   never actually been exercised.

## Tested and falsified (don't re-try these without new evidence)

- Guessing `team=0`/`ready=1` into `Member`'s per-entry offset 16/18 — no effect.
- Echoing the *real* captured team value (finding #2 above) into that same slot
  instead of a guess — also no effect. The 10-15s post-load boot is not caused
  by this field. See `2026-08-16-team-selection-field-confirmed.md`'s update.
- Firewall/NAT theory for the 2-player find-match abandon — user applied inbound
  UDP allow rules on both machines, room still abandoned via the same `0x133`
  mechanism as every solo-host abandon. Not the (sole) cause.

## Still open, with concrete next steps

1. **The 10-15s post-load boot** (`net-game-manager.cpp:1358`'s
   `team >= 0 && team < NetInfo::kMaxNetTeams` assert). Ghidra tracing found the
   team[0]/team[1] array (`+0x4b1c`/`+0x4b20` on a NetGameManager/match-state
   object, NOT the SessionManager's room object) but only located a map-config
   *default-seed* write, not the real per-player assignment write. **Important
   correction, recorded loudly in `2026-08-16-team-selection-field-confirmed.md`**:
   an earlier framing of this as "outside server reach" was wrong and was called
   out directly by the user — this is shipped, working retail code, so if it
   fails under our server, something we're not sending/doing is the actual cause.
   Next step: live breakpoint/watchpoint on `param_1+0x4b1c`/`+0x4b20` writes
   during an actual solo-host session (static tracing hit a wall — needs live
   debugging now).

2. **`NET_SM_SERVER_LOBBY` permanent stall** (3rd+ host attempt on one
   connection, no timeout). Dispatcher found (`_opd_FUN_001594bc`), blocks
   popping an item off a bounded producer/consumer queue. Producer/writer of
   that queue never located. See `2026-08-16-net-sm-server-lobby-dispatch.md`
   (if present) and follow-up Ghidra passes referenced from
   `2026-08-16-team-selection-field-confirmed.md`.

3. **Party invite boots the sender fully offline.** Real mechanism (from a
   *prior* session, `2026-08-15-createparty-trace.md`): a client-side assertion
   trap, not anything we send. Tonight's live 2-player test with `mgnomad2`
   surfaced a much more promising, DIFFERENT angle though: RPCN's own
   `SendMessage`/`MessageReceived` path (real Sony `sceNpBasic` messaging, not
   the custom `NetMatchmaking` family) — a real invite was sent and delivered
   (confirmed via RPCN's own log and RPCS3's real source, cloned to `/tmp` this
   session, not vendored), but the receiving client's Invites screen stayed
   empty. Root cause per RPCS3's actual source
   (`Emu/NP/np_handler.cpp:1283-1285`): event delivery is gated on
   `strncmp(msg.commId, basic_handler.context)` matching, where `commId` comes
   from the network message and `context` is the receiving client's own locally
   registered value. **Diagnostic logging just added** to
   `backend/rpcn/src/server/client/cmd_misc.rs`'s `send_message` (prints the
   sender's actual `communication_id`/`main_type`/`msg_features` on every send) -
   rebuild in progress as of this note, not yet live-tested. Next real party
   invite attempt will show directly what the sender's client submits, which
   settles whether the mismatch is something we control or purely two
   independent client-side values that happen to differ for an unrelated reason.
   **Do not conclude "client-internal, unfixable" again without new evidence** -
   that framing was wrong multiple times tonight, called out directly twice.

4. **Checkpoint's empty-skybox symptom** — both leading theories from tonight
   (missing content pak, map_id-based content-lookup gap) are now ruled out by
   direct evidence, not just deprioritized. See the "Correction" sections in
   `2026-08-16-mp-pak-numbering.md` and `2026-08-16-level1-psarc-version-check.md`.
   Genuinely unexplained again - no live lead currently.

## Process/infra notes

- `tools/session_manager_stub.py` needs a restart after every edit (kill the pid,
  relaunch `cd tools && nohup python3 session_manager_stub.py 7314 >
  session_manager_stub-run.log 2>&1 < /dev/null &`).
- `backend/rpcn` is a git submodule with its own commit history - changes there
  need committing inside the submodule AND a pointer-bump commit in the parent
  repo. Rebuilding it (`cargo run --release`) after any source change appears to
  trigger a full clean rebuild (~7 minutes), not an incremental one - budget for
  that when testing a Rust-side change live.
- Root-cause discipline lesson from tonight, worth internalizing for next
  session: this is shipped, working retail code. "It's client-internal / the
  emulator / outside our reach" is very rarely the right stopping point - it was
  wrong on the team-assert bug, wrong (initially) on the party-invite crash
  framing, and almost wrong on the RPCN message-delivery investigation. Trace
  one level further before concluding something can't be fixed server-side.
