# The "connecting..." hang wasn't the room protocol - it's a 4th port, 7313

Follow-up to the Session Manager work. The live blocker after the level-content-sync
fix was the "connecting..." UI bar filling completely and then hanging forever with
no error. The working hypothesis coming in was the NetMatchmaking room protocol
(`RoomSearch`/`RoomCreate` - the 26 opcodes `session_manager_stub.py` doesn't
implement). That hypothesis is **wrong** - `session_manager_stub.py` needed no
changes. The real cause is a previously-undiscovered fourth service on **port 7313**.

## The one-line answer

Right after NAT-type detection (`Nat Type = 2` in the TTY log), NetInit
(`FUN_003557a8`) makes a **one-shot, never-retried** `connect()` to
`192.168.1.100:7313`. Unlike ticket-server (7320), Session Manager (7314), or the
location service (7312) - all of which retry on a steady ~5s cadence whether or not
anything answers - this one fails once (`Connection refused`) and goes silent. No
further log activity, ever, for that NetInit pass. That's exactly the shape of "fills
the bar, then hangs with no error": the client isn't built to tolerate this one being
unreachable, and isn't built to retry it either.

`tools/voice_server_stub.py` now listens there. Confirmed live this pass: the client
sends literal ASCII `hello\n` (6 bytes) once connected. Replied with a guessed
`+OK\n` - **not yet confirmed against a real success path**, see "What's still open."

## Why the room-protocol hypothesis was wrong (and what IS now confirmed there)

Decompiled the full SessionManager vtable this pass (`research/ghidra/sessmgr_vtable_dump.txt`,
regenerated from scratch - the file this doc's predecessor claimed existed didn't
actually exist on disk, see "Housekeeping" below) and traced `Init()` and the
receive/dispatch loop start to finish:

- **`Init()` does not wait for a response to `ClientHello2`.** The send
  (`_opd_FUN_00acb93c(iVar7,local_b0,8,1)`) is the last network call in `Init()` -
  the very next line just resets a buffer cursor and returns. `session_manager_stub.py`
  logging "further data" and then closing after a 10s idle timeout was already
  harmless; the client had already moved on by the time that timeout fires.
- **`ClientHello2`'s real on-wire opcode is `0x146`, not `0x148`.** Confirmed by two
  independent pieces of evidence agreeing exactly: the decompiled `Init()` literal
  (`_opd_FUN_00a0e324(0x146)` immediately before the 8-byte send) and the live capture
  in `captures/tcp_catch.log` (`further data (8 bytes): 00 00 01 46 18 ac 7a d2` -
  `00 00 01 46` = `0x146` BE). The second word (`18 ac 7a d2` in that capture) is a
  **checksum**, not free-form data: `local_98 + local_94 + local_8c + local_90`, four
  `int`s summed from the key-schedule digest output (`FUN_00db7f88`'s 0x24-byte
  result, reinterpreted as first-four-`int`s-summed) - so it varies per session/key,
  as observed.
- **The 28-opcode `name+size` table's `opcode = 0x12d + index` formula is confirmed
  wrong for at least two entries.** `ClientHello2`'s send literal is `0x146` (table
  says index 27 -> `0x148`), and the receive/dispatch loop's own periodic-ping send
  (see below) uses literal `0x145` (table says `Ping` is index 26 -> `0x147`). The 11
  receive-dispatch cases the prior pass verified (`0x131`-`0x144`) are still solid -
  those literals were read directly from the switch statement, not inferred from the
  debug-dump table order. Only the *tail* of the index-based formula (roughly
  `SetRoomName`/`UpdatedRoomName`/`Ping`/`ClientHello2`) is now suspect. Not fully
  re-derived this pass - flagged as open work below, not blocking.
- **Post-handshake `NetMatchmaking*` traffic on this connection is plain, unframed
  bytes - not wrapped in ticket-server's 20-byte encrypt-then-MAC frame.** The
  receive/dispatch loop (`FUN_00ad7604`) reads the opcode directly off the raw
  `recv()` buffer (`_opd_FUN_00a0e324(*puVar21)`, a byte-swap, not a decrypt call) -
  no cipher call appears anywhere in that function. This resolves open question #3
  from `docs/protocol/session_manager_and_matchmaking.md`: it's the simpler option.
  Each message is `[4-byte opcode][fixed-or-variable payload]` back to back, sized
  per the opcode (several, like `RoomSearch`/`0x136`, turned out to be
  variable-length - a count field followed by N fixed-size records - not the flat
  fixed size the debug-dump table implies for that entry; the debug-dump size looks
  like a *minimum/header* size for those, not the full wire size).
- **The dispatch loop is non-blocking and self-contained - it will not hang the
  client on its own.** It's a polled, per-tick function: if there's no data ready
  (`_opd_FUN_00acc634` returns 0), it just returns 0 immediately. It also owns its
  own periodic keepalive: if a timer expires, it sends a 4-byte `Ping` (opcode
  `0x145`, confirmed above) unprompted - no reply required from us for that either.
  **Conclusion: a client sitting on an idle Session Manager connection with nothing
  implemented past `ClientHello`/`ClientHello2` will not hang here.** This is why
  standing up the room protocol wouldn't have fixed the reported hang.

## How port 7313 was found

1. Correlated the user's live "connecting... bar filled, hanging, no errors" report
   against the RPCS3 TTY log (`/mnt/f/rpcs3_testing/.../log/TTY.log`, small and
   human-readable - much faster to work with than the multi-GB `RPCS3.log` for this).
   Right after `Nat Type = 2`, the log showed a `connect to 192.168.1.100:7313 ...`
   line with `Connection refused` immediately after, and then **nothing** - compare
   against 7312 (`get-location`), which retries every ~5s indefinitely regardless of
   success/failure. That contrast is what flagged 7313 as the real suspect over the
   room protocol.
2. Confirmed it's genuinely new: `grep -rn 7313` across `research/notes/`,
   `docs/known-keys.md`, and the decrypted `net1.bin` (`research/net1bin/net1.bin`,
   which only contains the three already-known dead ticket-server IPs, no fourth
   entry) - this port has never been documented in this project before.
3. `FindCallersOf.java` on the shared raw-connect wrapper (`00acbf90`, same helper
   ticket-server and Session Manager both use) surfaced `FUN_003d7890`, called
   directly from `FUN_003557a8` (NetInit) at `0x356edc` - matches the observed timing
   exactly. It reads its target host:port from service-descriptor slot `+0x58`
   (adjacent to the already-known `+0x54`=leaderboard-server, `+0x5c`=Session
   Manager slots) and does a `connect()` with flags `(1,1)` (vs. `(0,0)` for
   ticket-server/Session Manager - meaning unconfirmed, not chased further). Notably,
   `FUN_003d7890` **only connects** - no send/recv in that function itself; on
   success it spawns a background PPU thread (`sys_ppu_thread_create`) to do the
   actual protocol work, whose entry point was not resolved this pass.
4. Rather than keep chasing the spawned thread's entry point through Ghidra, stood up
   `tools/catch_tcp.py 7313` (passive/log-only, this project's existing "probe one
   guess at a time" tool) and waited for a live retry. Caught one: the client sent
   literal `hello\n` - the same plaintext-line convention as `heartbeat`/
   `get-location`, just with no prior art documenting this one at all.
5. A structurally similar sibling function, `FUN_0035363c` (different service slot,
   `+0x4c`, connects/sends/receives inside a single self-contained PPU thread,
   ends with `sys_ppu_thread_exit`) does a send/recv where the response is validated
   as `response[0] == '+'`. Used this as the basis for the reply this stub now
   sends. **Important nuance: `FUN_0035363c` uses a DIFFERENT service slot (`+0x4c`)
   than the confirmed 7313 caller (`FUN_003d7890`, `+0x58`)** - they are two separate
   services, not the same one. The `'+'`-prefix convention is borrowed by inference
   (same plaintext-ack family, `cellVoiceGetPortAttr` appears nearby in a sibling
   caller path suggesting this general area is voice-chat-related), not confirmed
   for 7313 specifically. Treat `voice_server_stub.py`'s reply as an educated guess.

## Housekeeping: the raw-evidence-files gap

`docs/protocol/session_manager_and_matchmaking.md`'s "Raw evidence files from this
pass" section names six files (`sessmgr_vtable_dump.txt`, `sessmgr_ctor_decomp.txt`,
`sessmgr_init_raw_disasm.txt`, `netinit_raw_disasm.txt`, `sessmgr_vtable_resolve.txt`,
`sessmgr_cipherkey_resolve.txt`) that **did not actually exist in `research/ghidra/`**
when this pass started - confirmed via `grep -rl "0x01243b38" research/ghidra/*.txt`
finding nothing before today. Either they were never written to disk or got lost
before commit `20bad57`. Regenerated `sessmgr_vtable_dump.txt` from scratch this pass
(`tools/ghidra_scripts/DumpVtableAt.java` against vtable base `01243b38`, 8 slots -
note the script wants a bare hex string, not `0x`-prefixed, or `Long.parseLong`
throws) and verified it landed on disk before relying on it. Didn't chase down
whether the other five ever existed; if a future pass needs them, regenerate rather
than assume.

## What's still open (prioritized)

1. **Confirm the port-7313 reply format for real.** `+OK\n` is a guess. If the
   client hangs again at the same point, capture what (if anything) it sends after
   our reply, or whether it disconnects/retries differently - `tools/voice_server_stub.py`
   already logs every exchange to `captures/tcp_catch.log`.
2. **Resolve `FUN_003d7890`'s spawned-thread entry point** (the `uVar3` argument to
   `sys_ppu_thread_create`, loaded from `*(puVar4 + -0x7fd8)` relative to
   `PTR_PTR_012fdf50`) - this is the function that would actually define the real
   protocol on this connection, if the one-shot `hello\n`/`+OK\n` exchange isn't the
   whole story.
3. **Re-derive the tail of the 28-opcode table properly** (`SetRoomName`/
   `UpdatedRoomName`/`Ping`/`ClientHello2` region) now that two of its entries are
   confirmed wrong by the naive index formula - the receive-dispatch switch literals
   are trustworthy where decompiled; the debug-dump table's *declared order* is not,
   past index ~24.
4. Room-protocol field layouts (`RoomCreate`/`RoomJoin`/etc.) remain unmapped, same
   as before this pass - just no longer believed to be the active blocker.

## Raw evidence files from this pass

- `research/ghidra/sessmgr_vtable_dump.txt` - full decompile of all 8 SessionManager
  vtable slots (`Init()`, the receive/dispatch loop, and 6 more), regenerated and
  verified on disk.
- `research/ghidra/callers_of_connect_wrapper.txt` - pre-existing, reused as-is; has
  decompiles of every caller of the shared raw-connect helper including
  `FUN_003d7890` and `FUN_0035363c`.
- `research/ghidra/callers_of_003d7890.txt` - new, callers of the port-7313 connect
  function; confirms the `FUN_003557a8`/NetInit call site and a second, unrelated
  periodic-tick caller (`FUN_00355550`, voice-port-attribute-gated).
- `research/ghidra/netinit_full_decomp.txt` - pre-existing full NetInit decompile;
  line 654 is the confirmed `FUN_003d7890` call site.
- Live capture: `captures/tcp_catch.log` (the `hello\n` exchange, logged by
  `voice_server_stub.py`) and the RPCS3 TTY log (`.../log/TTY.log`, small enough to
  read directly - much faster than grepping the multi-GB full `RPCS3.log` for this
  kind of correlation work).
