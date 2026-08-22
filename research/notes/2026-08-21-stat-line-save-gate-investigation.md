# `stat ... task-%x ...` line: why real campaign saves aren't reaching single-player-server

Date: 2026-08-21. Static analysis only (no live RPCS3 session this pass). All
addresses are **01.00** VMAs, taken from `research/ghidra/sibling_servers_report.txt`
(lines 1674-1889, the full decompile of `FUN_007f1acc`) and cross-checked
against `research/ghidra/acc424_all_callers.txt` (lines 2451-2560ish, the same
function reached via a `FindCallersOf(00acc424)` sweep - independent
extraction, same bytes, used here as a second source for the exact same
decompile).

## Trigger for this investigation

Two real, deliberate campaign-save events (an autosave and a manual pause-menu
save) during a live RPCS3 session with the server running produced **zero**
new connections in `server/logs/ticket_server.log`. The trophy line
(`stat %s trophy-%x\n`) has been observed live at least once; the campaign-save
line (`stat %s task-%x %s %s\n`) has never been observed live. This note
re-reads `FUN_007f1acc` specifically for gate conditions the 2026-08-19 pass
(focused on the format string/argument resolution) did not check.

## Verdict: a real gate was found - two, in fact, stacked

`FUN_007f1acc` is a dedicated PPU-thread event handler (ends in
`sys_ppu_thread_exit(0)`, matching the "runs as a dedicated thread"
pattern already documented for `heartbeat-server`). Its `param_1` is the
save-manager object this thread was spawned with. Reading the `iVar7==1`
(save-event), `uVar2 != 0xc` (non-special-slot) branch line by line
(`sibling_servers_report.txt:1714-1772`):

```c
if (*(char *)(param_1 + 0x1a) == '\0') {                    // GATE 0 (offset 0x68 byte)
    ...
    cVar9 = _opd_FUN_007f0f54(param_1,uVar2,piVar4,param_1[7]);
    if ((((0 < param_1[0x4e1]) && (-1 < param_1[3])) &&      // GATE 1 (config present)
         (param_1[0x4e3] != 0)) && (param_1[0x4e4] != 0)) {
      if ((param_1[0x4e0] == 0) &&                            // GATE 2 (throttle counter == 0)
          (iVar7 = sceNpManagerGetNpId(auStack_790), iVar7 == 0)) {   // GATE 3 (NP must be up)
        _opd_FUN_00acc668(auStack_744);
        iVar7 = _opd_FUN_00acc424(auStack_744,param_1[0x4e3],param_1[0x4e4],
                                  *(undefined4 *)(puVar5 + -0x7eb8));  // GATE 4 (connect+hello must succeed)
        if (iVar7 == 0) {
          /* ... build "stat %s task-%x %s %s\n" via FUN_00e46670, send, recv 0x40 ... */
        }
        else {
          _opd_FUN_007f0864(param_1,*(undefined4 *)(puVar5 + -0x7ea0),
                            param_1[0x4e3],param_1[0x4e4]);   // silent local-only fallback, NO network send
        }
      }
      param_1[0x4e0] =
           (param_1[0x4e0] + 1) - ((param_1[0x4e0] + 1) / param_1[0x4e1]) * param_1[0x4e1];
                                                               // counter always advances mod param_1[0x4e1]
    }
    ...
}
else {
    /* just cellSaveDataListAutoSave - no notify attempt of ANY kind */
}
```

Offsets, spelled out (`param_1` is `int *`, so index N = byte offset N*4,
except the one explicit `(char *)` cast):

| field | byte offset | role |
|---|---|---|
| `*(char*)(param_1+0x1a)` | `+0x68` | GATE 0 - outer byte flag; if nonzero, the ENTIRE notify branch (including the throttle/NP-check machinery) is skipped and only a bare `cellSaveDataListAutoSave` runs. Writer(s) not traced this pass. |
| `param_1[0x4e1]` | `+0x1384` | throttle modulus N - must be `> 0` or the notify block can never execute at all |
| `param_1[3]` | `+0x0c` | save-slot index - must be `>= 0` |
| `param_1[0x4e3]` / `param_1[0x4e4]` | `+0x138c` / `+0x1390` | single-player-server's resolved `{ip, port}` pair (matches `docs/protocol/0x11_sibling_servers_family.md`'s note that this call site "receives an already-resolved `{ip,port}` pair as a function argument") - both must be nonzero |
| `param_1[0x4e0]` | `+0x1380` | **throttle counter** - the actual network attempt (`sceNpManagerGetNpId` + `FUN_00acc424`) is only made when this equals exactly `0`; it is incremented mod `param_1[0x4e1]` on every qualifying save regardless of whether the attempt was made or whether it succeeded |

### GATE 2/3 is the network/online-state gate (task item 1) - CONFIRMED

`sceNpManagerGetNpId(auStack_790)` must return `0` before the code even
constructs the connection object or calls `FUN_00acc424`. This is a direct,
unambiguous "is the NP manager currently initialized/logged in" check - the
exact category of gate item 1 asked about. If the client is mid-RPCN-outage
(the documented `recv failed: connection reset by server` cycle in
`research/notes/rpcn-connection-instability.md`) at the moment
`sceNpManagerGetNpId` is called, or simply hasn't completed an NP login this
boot, this call can fail and the entire notify attempt - including the
throttle-counter reset logic below it - is skipped for that save event
(though the counter itself still advances; see below).

This is not the same singleton as `0x013835c0`
(`research/notes/2026-08-20-followup-open-items.md` item 2) - that object is
the net-session-manager's mode/role field, unrelated to `sceNpManagerGetNpId`,
and `FUN_007f1acc`'s `param_1` is a save-manager object, not the session
manager. No cross-reference between the two was found or expected.

### GATE 4 is the "silent connect/handshake failure" gate (task item 2) - CONFIRMED

`FUN_00acc424` is the same shared hello/hello_response handshake function
documented in `docs/protocol/0x11_ticket_server_hello.md` for every sibling
service, and per that doc's own decompile excerpt it performs the raw
`connect()` **internally** (`_opd_FUN_00acbf90`, "raw connect()" per that
doc's own comment) as its first step, then the message-A/B exchange. Its
return value is a single pass/fail integer. `FUN_007f1acc` branches on it:
success (`==0`) builds and sends the real `"stat %s task-%x %s %s\n"` line;
failure takes `_opd_FUN_007f0864(param_1, ...(-0x7ea0 slot)..., ip, port)` -
an internal event/log call using the same call shape as every other
in-function state-transition log in this function (`FUN_007f0810`,
`FUN_007f0864` elsewhere in the same decompile), not a crash, not a retry,
not any other network attempt. So: **yes, a connect/handshake failure at this
call site is caught and absorbed with no visible error and no line reaching
the server**, exactly the failure mode item 2 hypothesized. This does NOT
implicate DNS specifically - single-player-server resolves through this
project's own net1.bin-driven hosts-redirect setup the same way ticket-server
does (see `research/notes/net1bin-server-list.md`), and that pipeline is
proven working (452+ ticket-server hellos logged) - but a *connect()* failure
(refused, wrong port, transient) downstream of a working DNS/redirect is still
fully possible and this code path would swallow it silently either way.

### GATE 2 is also a genuine one-shot-per-N throttle (task item 3) - CONFIRMED, and it's the most likely single explanation

`param_1[0x4e0]` only reaches the actual network attempt when it equals `0`,
and it is a rotating counter mod `param_1[0x4e1]` (some configured N,
plausibly net1.bin-sourced given the sibling family's general
net1.bin-driven config pattern, though this pass did not trace N's own
producer). **Concretely: only every Nth qualifying save event even attempts
to notify single-player-server; the rest silently just do the local
`cellSaveDataListAutoSave`/`ListSave2` with the counter incrementing and
nothing else happening.** If N is anything other than 1, two real deliberate
saves producing zero connections is unsurprising - it would take exactly N
qualifying saves to land on `param_1[0x4e0] == 0` again. And critically: the
counter advances **regardless of whether the attempt (if made) succeeded** -
so a save that DID hit `param_1[0x4e0]==0` during the RPCN-instability window
documented separately, and failed at GATE 3 or GATE 4, still consumed that
"slot" and pushed the next eligible attempt N saves further out. This means a
single unlucky failed attempt during a flaky-RPCN stretch can explain an
extended-looking silence even after RPCN recovers.

### GATE 0 (task item 4, partial) - the outer per-thread byte flag

`*(char*)(param_1+0x68)` gates the ENTIRE notify branch, not just the send.
When set, `FUN_007f1acc` takes a completely separate path
(`sibling_servers_report.txt:1764-1771`) that does nothing but
`cellSaveDataListAutoSave` - no `FUN_007f0f54` call, no throttle check, no NP
check, nothing. This pass did **not** trace where this byte is written (it
would require the same literal-pool/anchor tracking technique used for
`0x013835c0` in the 2026-08-20 followup note, applied to whatever object
`param_1` resolves to at each of `FUN_007f1acc`'s thread-spawn call sites -
see "what's still open" below). It's plausible this flag distinguishes
different save *reasons* (autosave vs. explicit/checkpoint save), which would
directly answer item 4's "different save types get different handling"
question - but that reading is a guess, not yet decompile-confirmed.

## What's still open / genuinely inconclusive statically

- **GATE 0's writer(s)** - not traced. If this flag is per-save-type (e.g.
  autosave sets it, explicit save doesn't, or vice versa), that alone could
  fully explain today's two failed attempts if both landed on the
  flag-set state.
- **The value of the throttle modulus `param_1[0x4e1]`** - not read from any
  live object or config bundle this pass. Whether it's 1 (fires every
  qualifying save) or something larger (fires rarely) is the single biggest
  open number for explaining today's silence. A live memory read of
  `param_1[0x4e1]`/`param_1[0x4e0]` (or a breakpoint at
  `FUN_007f1acc`'s entry, `0x007f1acc`, during a real save) would resolve
  this directly.
- **The actual thread-spawn call site(s) for `FUN_007f1acc`** were NOT
  located this pass - a full-image search for both the function's own VMA
  (`0x007f1acc`) and its `.opd` descriptor address (`0x012d7fc0`, confirmed
  by direct byte search to be the correct `.opd` slot: `func=0x007f1acc,
  toc=0x01305870` at that address, immediately adjacent to
  `.opd.FUN_007f149c`/`.opd.FUN_007f17fc`/etc. in the same OPD table region)
  found **zero** other references anywhere in the ~19MB image, via both the
  `scan_anchor.py`/`scan_imm.py` tools and a raw big-endian word search. That
  means the call is reached by some addressing idiom this project's existing
  tools don't cover (e.g. a computed/relative table the thread-creation
  wrapper builds another way), not that no caller exists - `FUN_007f1acc` is
  clearly live code (it's the function that builds the exact `task-%x`
  format string this project already confirmed). This blocks a full static
  answer to task item 4 ("is the call site itself conditional on save
  type/reason") - genuinely inconclusive, would need either a smarter static
  search or a live breakpoint at `0x007f1acc`'s entry to capture the caller's
  return address (`LR`) directly, the same technique that resolved the party
  RoomCreate caller in the 2026-08-20 followup note.

## Bottom line

Two gates are decompile-confirmed and directly explain "real saves happened,
nothing reached the server": (1) the whole notify attempt requires
`sceNpManagerGetNpId()` to succeed - a live NP/online-state precondition -
and a connect/handshake failure downstream of that is caught and silently
absorbed; and (2) even when NP is up and the handshake would succeed, the
actual send is throttled to once every N qualifying saves via a mod-N
counter, and a failed attempt still consumes a cycle. Either alone would
explain today's silence; both together make it close to expected rather than
surprising. What remains open and would need a live RPCS3 breakpoint at
`FUN_007f1acc`'s entry (`0x007f1acc`) during a real save: the concrete value
of `param_1[0x4e1]` (the throttle N) and `param_1[0x4e0]` (the current phase
of the counter) at the moment of a real save, whether `param_1+0x68`'s GATE 0
byte is set for autosave vs. explicit-save paths, and whether
`sceNpManagerGetNpId` is actually succeeding at that moment given the
account's ongoing RPCN instability.
