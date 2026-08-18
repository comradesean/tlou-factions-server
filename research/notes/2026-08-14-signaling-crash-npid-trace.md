# Post-RoomJoined RPCS3 crash traced to a likely-missing NpId in the attribute block

Follow-up to `2026-08-14-room-slot-gating.md`. That pass's fix (send `RoomJoined`
with a zeroed id field instead of echoing `RoomCreate`'s id) worked - live-confirmed
in this pass: the client now logs brand-new lines (`joined match`, `NpId  connId 1`,
`Activate Connection  4660 1`) it had never reached before. Immediately after,
RPCS3 itself crashes (100% reproducible, same stopping point every time):

```
{NP Handler Thread} SIG: Thread terminated due to fatal error: Unexpected error in
reply to RequestSignalingInfos: Malformed
(np_requests.cpp:849, np::np_handler::reply_req_sign_infos)
```

`backend/rpcn-run.log` shows the root cause is upstream of RPCS3's crash - RPCN's
own request parser rejects the request first:

```
Parsing command RequestSignalingInfos
WARN: Error while extracting data from RequestSignalingInfos command
WARN: Command Some(RequestSignalingInfos) was malformed!
```

`backend/rpcn/src/server/client/cmd_misc.rs`'s `req_signaling_infos` expects a
single length-prefixed string (the peer's NpID); `data.error()` being true means
the extraction failed structurally, not just semantically - i.e. RPCS3 is sending
RPCN a garbage/empty-length string field.

## What was traced this pass

Both `"NpId  connId 1"` and `"Activate Connection  4660 1"` have an **empty %s**
(format string confirmed: `"Activate Connection %s %i %i"` at VMA `0xec8af0`,
found via `sceNpSignalingActivateConnection() failed. 0x%x` sitting right next to
it in `research/strings/strings_ascii.txt`). Traced the caller chain via
`FindCallersOf.java` on the NID-resolved `sceNpSignalingActivateConnection` stub
(`0x00e5728c`, from `research/ghidra/scenp_nid_table.txt`):

- `FUN_00adcae0` (an NpId-keyed connection cache: linear-search 32 slots, insert
  new entry copying ~36 bytes from its own `param_2` if not found) calls
  `sceNpSignalingGetConnectionFromNpId(ctx, npid_ptr, ...)` then
  `sceNpSignalingActivateConnection(ctx, npid_ptr, ...)` using the SAME `npid_ptr`
  it just cached - i.e. whatever `param_2` this cache function was called with IS
  the npid used for both calls, and that npid clearly ends up empty.
- Static xref search for `FUN_00adcae0`'s own callers came back with only an
  indirect `DATA` reference (a function-pointer table entry) - same "indirect
  vtable call defeats plain xref search" wall hit repeatedly today. Did not
  resolve the ultimate caller.

Given that dead end, traced forward instead: `_opd_FUN_00ad33d8` (member-slot
registration, called right after our `RoomJoined` reply is processed - see the
prior note) copies `param_2+4 : param_2+0x28` (36 bytes) into a new room-member
record, and **dedupes existing members by comparing `param_2+4` via
`_opd_FUN_00e459bc`** - the same compare helper used elsewhere in this binary
specifically for 16-byte `SceNpId` handles (e.g. `FUN_00add510`'s local-vs-remote
npid check). That's a strong (not proven) signal that `param_2+4 : param_2+0x14`
(16 bytes) is this member's NpId handle.

Tracing back to the call site inside `FUN_00ad7604`'s `0x132` (RoomJoined) case
(field names from the earlier decompile: `local_d4` = wire `0x24068`, i.e. wire
offset 16 relative to the message start) puts this 16-byte span at **wire offset
16:32** - the first 16 bytes of what was previously called the "18x u16 attribute
block", sent all-zero. All-zero NpId -> empty string downstream -> matches the
observed blank `%s` in both logged lines -> RPCS3 forwards something RPCN can't
parse as a valid npid string -> crash.

## The fix applied (moderate confidence, NOT live-verified)

`session_manager_stub.py`'s `build_room_joined()` now writes the room-creator's
own npid (parsed back out of `RoomCreate`'s own `"<npid>.<timestamp>"` room-name
field, e.g. `"comradesean"`) into wire offset 16:32, null-padded to 16 bytes,
instead of leaving it zero. Verified against a real captured `RoomCreate` payload
that the function still produces a valid 120-byte reply with `comradesean\0...`
landing at the right offset - not yet tested against a live client.

## What's still open

- **Not confirmed live.** The offset-16 hypothesis rests on: (a) a compare-helper
  identity match (`_opd_FUN_00e459bc` used for both this and known npid compares
  elsewhere), (b) a caller-side wire-offset mapping done by matching decompiled
  local-variable names to their source addresses. Both are reasonable but not
  as ironclad as the `0x00ad7b14` id-gate fix from the prior pass (that one was a
  direct debugger register read). **If the crash persists, breakpoint at
  `0x00ad33d8` and read 16 bytes at `r4+4`** (PPC64 ABI: `r4` = this function's
  `param_2`) to see what's actually landing in the npid-shaped slot, and compare
  against what `session_manager_stub.py` is now sending at wire offset 16.
- The remaining 20 bytes of the attribute block (wire offset 32:52,
  `param_2+0x14:+0x28` in `_opd_FUN_00ad33d8`) are still unconfirmed and sent
  zero - likely team/rank/slot-shaped member metadata, not expected to crash
  anything but may affect whether the member "looks right" once past this bug.
- Two other pointer-indirect fields inside `_opd_FUN_00ad33d8` (reads guarded by
  `if (*(param_2+0x28) != 0)` and `if (*(param_2+0x2c) != 0)`, copying up to 0x80
  bytes each) were not fully traced back to their wire origin this pass - flagged
  as a residual risk if the npid fix alone doesn't clear the crash.
- `FUN_00adcae0`'s actual caller (who supplies the npid it caches) was not found
  via static analysis - if the offset-16 hypothesis is wrong, this would be the
  next thing to chase, likely also needing a debugger session given the indirect
  call.

## Raw evidence

Ghidra outputs from this pass (not previously saved, regenerated against the
existing `research/ghidra/tlou_factions.gpr` project, `-noanalysis` headless
re-run per `docs/ghidra-setup.md`) were written to `/tmp` and not copied into
this repo - re-run against addresses `00e5762c` (`FindCallersOf`),
`00adcae0` (`FindCallersOf`), `00e5728c` (`FindCallersOf`, the most useful one -
shows `FUN_00adc5f8`, `FUN_00adcae0`, `FUN_00add510` full decompiles), and
`00ad33d8` (`DecompileByAddresses`) if this needs re-deriving.
