# Session handoff — find-match, profiles, progression (2026-08-17)

Entry point for picking this up. Long live-testing session against two real
RPCS3 clients (`comradesean` + `mgnomad2`). Most items below have a dedicated
note with full evidence — read this first, then the referenced note.

## Live-confirmed WORKING

1. **Solo-host Custom Game** into a real match. Fix stack (all committed):
   parse `room_ptr` from RoomCreate wire offset 8 (per-client), `max_players`
   from 0x24, send `0x13f`/OwnerChanged after Member, DROP `RoomJoined` on the
   solo-host path, populate the local member's real NpId. See
   `2026-08-16-solo-host-fixed-live-confirmed.md`.
2. **Invite-to-Party 2-player matches** — comradesean invites, mgnomad2
   accepts, both load into and PLAY a real match. See
   `2026-08-16-two-player-party-and-match-working.md`. **BUT these are CUSTOM
   games and credit ZERO progression** (see the progression finding below).
3. **Party join** (`0x130` RoomJoin), joiner-leave (`0x134` RoomLeave), and the
   room-registry state hygiene.
4. **Remote-player rank cards** — the `0x13a`->`0x13b` 32-byte member-blob
   relay (getter gates on length==32). See
   `2026-08-17-member-data-blob-rank-and-0x142-hostrank.md`.
5. **Profile persistence** — the client PUTs its own signed `profile.21` to S3;
   `tools/catch_http.py` accepts the PUT and round-trips it; the user added the
   `s3.amazonaws.com` IP-swap in the RPCS3 GUI. Real profiles decrypt cleanly
   with `tools/psarc_crypt.py` (Blowfish+HMAC+LZF, same keys as the PSARC work).
   `tools/fetch_real_cdn.py` fetches real objects from the live CDN (SigV2,
   creds auto-extracted from the EBOOT). See
   `2026-08-16-profile-and-userdata-reverse-engineering.md`.

## THE central finding: progression requires COUNTED games, and only
## find-match produces them

`ClanManager::OnMatchEnd` (which credits supplies/rank/journeys/wins/population,
all of which then persist via the profile PUT) NEVER runs unless a "this match
counts" latch `g_70[0x6C]` (g_70 = 0x013835c0 NetInfo; set via FUN_003abf70) is
set. The match-end handler `FUN_003f208c` @ `0x3f2194` skips its ENTIRE body
otherwise. **CUSTOM/private/invite games never set the latch (shipped-game
design)** — a fully-completed 4-round custom Survivors match credited zero, and
the real decrypted `profile.21` shows the clan roster initialized (5 survivors)
but every match field at 0. The latch is set only on the COUNTED/matchmade path
(entered via `NET_SM_START_MATCHMAKING`), reaching a NORMAL end (win condition
met -> `NET_SM_RESULTS`). **So find-match is the ONLY path to any progression.**
See `2026-08-17-match-counts-latch.md` and `2026-08-17-supplies-and-survivor-state.md`.
(The user explicitly rejected patching custom games to count as an unacceptable
hack — the real find-match path is required.)

## find-match: implemented, works up to CONNECT, blocked on 2-client coordination

The correct flow (fully traced, `2026-08-17-find-match-flow.md`): the client's
`NET_SM_CLIENT_GAME_LIST_WAIT` blocks on a **`0x136` RoomSearch game list**
(server->client) the server must PUSH in reply to the `0x135` search. Empty
list -> the client self-hosts a public game; non-empty -> it PICKs an entry and
**P2P-connects to that entry's host BY NPID** (`CONNECT_TO_HOST`), NOT via a
`0x130` to us.

Implemented in `tools/session_manager_stub.py` (`build_room_search`, the
`FIND_MATCH_OPCODE` branch, a `public` flag on `active_rooms` entries fed by a
find-match-host `RoomCreate`, grace on host `0x133`). **Confirmed working live:**
search -> list -> pick -> CONNECT_TO_HOST, and the **host-NpId-in-the-0x136-entry
fix** (`entry[0x14:0x24]`) advanced the joiner past the old ~30s connect timeout
to `NET_SM_CLIENT_RESERVE`. The RequestSignalingInfos empty-npid crash is fixed
in RPCN (see below).

**THE UNSOLVED BLOCKER — two-client host/joiner coordination.** Both clients
self-elect host (each searches, gets an empty list, self-hosts), so neither is
ever a plain joiner, and they never resolve into one-host + one-joiner. The
host leaves `SERVER_LOBBY` (`net-matchmaking.cpp:1039`) at ~12s because its SM
member count (from our Member roster) stays 1 < the mode min. Roster-push
band-aids (pushing both clients a 2-member Member roster) got them to briefly
SEE each other in a shared lobby, but it "keeps rotating through searches and
booting" — because the roster is a display illusion without a real P2P join.
**Next session: solve the deterministic host/joiner designation.** The real
mechanism is P2P (no `0x130`), so the stub must make exactly ONE client host
and steer the OTHER to PICK it from the list (become a joiner via
CONNECT_TO_HOST) BEFORE it self-hosts — a timing/coordination problem the
passive stub currently loses. Do NOT re-try the band-aid roster pushes (last
commits) as the solution; they are papering over the missing real join.

- **Mode-min is NOT a hard wall** (`2026-08-17-mode-min-players.md`): the
  min-to-start is runtime DC data (`modeCfg+0x14`), read live via a breakpoint
  at `0x003b7ac0` (`r3`=min, `r29`=count). It's ≤2, or bypassable via the
  `[0x01385cdc+0x64]` runtime floor, or a 1-instruction client patch
  (`FUN_0039f1e0` -> `li r3,2; blr`). So 2-player is viable ONCE they connect.

## Other root-caused items (server-adjacent, mostly P2P)

- **Join Party (friends-list): UNRELIABLE, OPEN — QUARANTINED.** This session's
  investigation and all its conclusions are archived at `archive/joinparty/` and
  deliberately kept out of a fresh attempt. Do NOT read them before forming your own
  read. Invite-to-Party works; friends-list Join is the unreliable direction.
- **Remote faction-model mismatch** (`2026-08-17-team-assignment-consistency.md`):
  team is host-authoritative, NpId-keyed at `player+0x1dc` (default -1),
  broadcast to the joiner ONLY over P2P `assign_team`. If the remote NpId isn't
  resolvable when it arrives, that player stays -1 = wrong faction. Same P2P
  layer; roster-index ordering was falsified as the cause.
- **RequestSignalingInfos empty-npid crash — FIXED** (RPCN `0a8b369`): the game
  signals empty match slots with a blank npid; RPCN was returning `Malformed`
  (connection-closing) which crashed the joiner. Now soft-fails as `NotFound`.

## Convergence

The game-end party drop, the remote faction model, AND the
find-match join all sit on the same **P2P signaling/rendezvous** layer. The
matchmaking-server (our stub) side is largely correct; the remaining frontier
is getting two consoles to establish and hold a real P2P link — and, upstream
of that, the two-client host/joiner coordination for find-match.

## Naming shift RESOLVED

The SessionManager declared opcode table is shifted +2 from 0x13a (idx 13/14
phantom). All 11 `.ksy` (0x13a-0x144) renamed to correct names, meta.ids fixed,
docs reconciled. Documentation-only — the stub keys off wire opcodes/behavior,
always correct. See `2026-08-17-opcode-naming-shift-resolved.md`.

## Process / infra

- Stub restart after every edit: `pkill -f "session_manager_stub.py 7314";
  sleep 1; cd tools && setsid python3 session_manager_stub.py 7314 >>
  session_manager_stub-run.log 2>&1 < /dev/null &`. **Use `setsid`** — plain
  `nohup &` from an interactive shell has not been persisting. Always verify a
  SINGLE listener on 7314 after (stale instances / leftover refresher threads
  spam the client).
- RPCN: `backend/rpcn` is a submodule; changes need a commit inside it AND a
  parent pointer-bump. Rebuild `cargo build --release` (incremental ~15-25s,
  not the "7 min" old lore). Restart: `pkill -f target/release/rpcn; setsid
  ./target/release/rpcn ...`. Running RPCN carries the empty-npid soft-fail.
- Concurrent-commit hazard: committing while a background agent also commits can
  orphan a commit (the working tree is the source of truth; re-commit the file).
  Avoid `git add -A`; stage specific paths.
- EBOOT (decrypted): `/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf`.
  Live RPCS3 log (multi-GB, `grep -a`; game diagnostics via `sys_tty_write`):
  `/mnt/f/rpcs3_testing/.../log/RPCS3.log`. Wire captures:
  `captures/tcp_catch.log`. HTTP: `captures/http_catch.log`.

## Research notes produced this session

`2026-08-17-{find-match-flow, match-counts-latch, supplies-and-survivor-state,
mode-min-players, member-data-blob-rank-and-0x142-hostrank, opcode-naming-shift-
resolved, team-assignment-consistency, character-customization-sync, join-party-
p2p-collapse-signaling-deactivation, join-party-presence-discovery}.md`, plus
the 2026-08-16 solo-host / two-player / profile / party-invite / metagame notes.
