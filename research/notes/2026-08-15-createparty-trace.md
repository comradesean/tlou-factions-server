# CreateParty (0x13a) live trace: fire-and-forget sender, disconnect is a client-side assert on a second, unrelated call

**CORRECTION 2026-08-15 (later same day)**: everything below this point is an
accurate trace of `0x13a`/`_opd_FUN_00ad6148` - but it is NOT the party-invite
trigger. A follow-up live-breakpoint session on the two direct callers
(`0x003B17CC`/`0x003B17E0`) proved this call fires on a periodic/UI-transition
tick completely independent of party or room state: it hit repeatedly from the
main menu, through EULA acceptance, the faction-select cinematic, and every
"continue" click - long before hosting a room or touching the party UI, with
both argument pointers (`0x1383bd8`, `0x1387f58`) constant across all of it.
The caller's own register context at the time contains the literal string
`"GET /__utm.gif?utmwv=5.2.5&utmac"` (a Google Analytics beacon URL) - this
whole code path is periodic telemetry/analytics reporting, not party
creation. The correlation with the party invite in the original test was
timing coincidence, not causation. The real party-invite trigger (what causes
the "Creating Party" spinner and subsequent disconnect) is still unknown -
nothing distinctive appears on the session-manager wire (port 7314) between
the invite action and the eventual `0x133` abandon + connection reset, so it
may not be a session-manager feature at all - possibly a Sony system-level NP
feature (friends/invite messaging) instead. The trace below remains useful
background on the SessionManager vtable/OPD structure but should not be read
as party-invite-specific.


Live RPCS3 breakpoint at `0x00AD6148` (the `0x13a` sender), triggered by using the
in-game "invite to party" action with a real solo-hosted Private Match room open.
Two separate test runs, each producing two hits from the same breakpoint ~4s apart.

## The sender itself (`_opd_FUN_00ad6148`, SessionManager vtable slot `+0x50`)

Fully decompiled earlier (static). Confirmed live: `undefined4 _opd_FUN_00ad6148(int
param_1 /*SessionManager this*/, int param_2 /*room*/, undefined4 param_3 /*data
buf*/, uint param_4 /*len, max 0x40*/)`. Genuinely fire-and-forget - builds and
sends the 80-byte `0x13a` packet unconditionally on success, no reply-wait logic
inside it at all. If `param_4 > 0x40` it hits an assert (`trapWord(0x1f,...)`)
before even reaching the send - a real bounds check, not a bug we tripped (our
captures never exceeded 0x40).

Confirmed via live register reads: `param_1` (r3) = `0x337238a8`, identical across
every hit in both test runs - the SessionManager instance. `param_3`/r5 always
`0xd0040248`-ish (same stack slot reused per call), containing the SAME 32-byte
buffer across both hits within a test run: `ff ff ff ff` sentinel at buffer offset
10:14, and the room's own room_id (low 4 bytes) duplicated at buffer offset 28:32.
This buffer is genuinely meaningful "party data" the caller assembled, not stack
garbage (unlike the padding after it in the actual wire packet, which changes
between hits and IS garbage - see the `CREATE_PARTY_OPCODE` docstring in
`tools/session_manager_stub.py`).

## The caller (`_opd_FUN_00ad1fc0` @ entry `0xad1fc0`, both hits' `LR = 0xad2034`)

```c
int _opd_FUN_00ad1fc0(int param_1, undefined4 param_2, undefined4 param_3)
{
  piVar2 = *(int **)(param_1 + 4);           // SessionManager ptr, stored at +4 of THIS object
  if (piVar2 != NULL) {
    pcVar3 = (code *)**(undefined4 **)(*piVar2 + 0x30);  // vtable dispatch: *piVar2=vtable ptr, +0x30=slot
    iVar10 = (*pcVar3)(piVar2, param_1, param_2, param_3); // calls SetPartyData(SessMgr, room=param_1, buf=param_2, len=param_3)
    if (iVar10 == 0) { ... write into a member/party record on success ... }
    else {
      // error path: logs, then trapWord(0x1f, ...) - an assertion trap
    }
  }
  return iVar10;
}
```

Live-confirmed the vtable chain: `*(0x337238a8)` (SessionManager's own vtable
pointer) `= 0x01243b38`ish; `0x01243b38 + 0x30 = 0x01243b68` holds `0x012e9c50`
(dumped directly: `01243b68: 01 2e 9c 50`), which is the exact OPD-table slot for
`_opd_FUN_00ad6148` (confirmed earlier: `012e9c50: 00 ad 61 48 01 30 58 70`) - i.e.
`0x012e9c00` is the SessionManager's real method table (also contains the already-
known `Init` at slot 21/`0xad71a0` and the receive-dispatch loop at slot 22/
`0xad7604`, and the `0x133` room-abandon sender at slot 14/`0xad65e8`).

**Critically: `_opd_FUN_00ad1fc0`'s own `param_1` ("this") is passed straight
through as the room argument to SetPartyData.** This means the two hits per test
run are NOT retries of the same call - they're `_opd_FUN_00ad1fc0` being invoked
twice, from the same call site (a shared loop/ticker), with two DIFFERENT `this`
pointers:

- Hit 1 (both test runs): `param_1` = `0x1383bd8` = the real, live `ROOM_PTR`. Valid.
- Hit 2 (both test runs): `param_1` = a garbage-looking address (`0x1387f58` in
  test 1, a `0x...53b8`-tail value in test 2) that does NOT match this session's
  actual room_id, `ROOM_PTR`, or anything else recognizable. Fails
  `_opd_FUN_00ad6148`'s internal 4-slot room search (`param_1+0x50`, stride
  `0x9000`, matching the same room-slot-array pattern `_opd_FUN_00ad65e8`'s
  teardown search and `0x13b`'s member-removal search both use), which returns an
  error code (`0xffffffff`) without sending anything for this second hit.

`_opd_FUN_00ad1fc0` treats that nonzero return as fatal: logs, then `trapWord
(0x1f, ...)` - an assertion trap. This is exactly the class of trap RPCS3's "Stub
PPU Traps" setting downgrades from a hard emulator crash into graceful client-side
error recovery - matching the observed behavior (spinner clears, "You have been
disconnected from the game servers" instead of an emulator crash).

## Conclusion

The disconnect is very likely caused by this **second, bogus-`this` CreateParty
call tripping an assert**, not by anything our server did or didn't reply with to
the first (valid) call - `_opd_FUN_00ad6148` never waits on a reply at all. The
`CREATE_PARTY_OPCODE` handler in `session_manager_stub.py` was reverted back to
log-only after this was found (the earlier RoomJoined+Member reply experiment had
already been shown to have zero effect, consistent with this).

**Not yet determined**: where the bogus second `this` pointer comes from - whether
it's genuinely stale/corrupted per-slot state (e.g. left over from running many
back-to-back invite attempts within the same long-lived RPCS3 process rather than
a fresh boot each time), or a real client-side bug independent of anything we've
done. **Next step recommended**: retry the exact same live-breakpoint test
immediately after a full RPCS3 restart (clean process, single attempt) to see if
the bogus second hit still occurs on a clean slate.
