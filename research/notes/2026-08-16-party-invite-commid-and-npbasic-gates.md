# Party invites, part A: every gate on the sceNpBasic receive path, and where the commId actually comes from

> **VERDICT SUPERSEDED 2026-08-16 (later, by marathon-log evidence (assert-filtered extract: `research/logs/2026-08-16-marathon-tty-asserts.txt`)) — read
> `2026-08-16-party-invite-event2-inbox-and-roomsize-assert.md` first.**
> The gate analysis below is accurate and still worth having, but its two
> candidate causes are both now dead:
> 1. **commId mismatch: did not happen.** Every `sceNpBasicRegisterHandler` in
>    the 3.4 GB log registers `NPWR03073` (12+ boots, no exceptions) and the
>    received message carried `commId: NPWR03073`. Gates 1-6 *all* passed:
>    `rpcn: Received message from mgnomad2` -> `basic_event: event:2` ->
>    the game's own TTY `"Post Message 10b, size 16"` -> `"Get Message 10b,
>    size 16"` 17 ms later. **The invite is delivered and consumed correctly.**
>    The `NPWR03073`/`NPWR00795` runtime split found below is real, so the RPCN
>    normalization (submodule `1f272cd`) stays as a guard - but it is a **no-op
>    for this pair** and will not change anything.
> 2. **The `sceNpBasicGetMessageEntryCount` / `GetCustomInvitationEntryCount`
>    stub theory: irrelevant.** Those feed a custom-data *badge counter*, not
>    the invite list. **No RPCS3 patch is needed.**
>
> The real failure is 300 ms downstream of delivery:
> `*** ASSERTION: m_roomSize > 0`, `ndlib/net/net-session.cpp:227` - a room
> object our own server left without a `0x131` Member packet. It fires 15
> times across the marathon, on nearly every online session, invite or not.

Static follow-up to open item #3 in `2026-08-16-session-handoff.md` ("receiver's
Invites screen stays empty after a confirmed-delivered RPCN invite"). No live
testing in this block - everything below is from RPCS3's real source (shallow
clone, `2f3c0f0`, not vendored) plus Ghidra on the EBOOT. Cross-refs:
`2026-08-15-createparty-trace.md`, `2026-08-16-party-invite-sender-assert-corrected.md`.

## Loud correction: the handoff note's commId theory is *half* wrong

The handoff note says the mismatch may be "two independent client-side values
that happen to differ". The first half of that is wrong, and it matters:

**The game never supplies a communication_id on the send path at all.** RPCS3
fills it in itself, from the *sender's own* registered basic-handler context:

- `sceNpBasicSendMessageGui` (`Emu/Cell/Modules/sceNp.cpp:1389-1394`):
  `message_data msg_data = { .commId = nph.get_basic_handler_context(), ... }`
- `_sceNpBasicSendMessage` (same file, `:1194-1200`): identical.
- `rpcn_client::send_message` (`Emu/NP/rpcn_client.cpp:2186`):
  `pb_message.set_communicationid(np::communication_id_to_string(msg_data.commId))`

and the receiver compares it against *its own* registered context
(`Emu/NP/np_handler.cpp:1285`). So the two values are not "independent" - they
are the same expression evaluated on two machines. If both clients register the
same context (identical game, identical build), **a commId mismatch is
impossible** and the commId theory is dead.

The second half is where it gets interesting, and it is why this was worth
tracing one level further.

## The game has TWO communication ids and picks one at runtime (confidence: high)

`sceNpBasicRegisterHandler` (import stub `0x00e574ac`, NID `0xBCC09FE7`) has
exactly one caller: `_opd_FUN_003557a8` @ `0x3557a8`, at `0x00356264`:

```c
uVar23 = _opd_FUN_003ac074(iVar25);
iVar22 = sceNpBasicRegisterHandler(uVar23, /*handler*/, 0);
```

`sceNpBasicRegisterContextSensitiveHandler` is **not imported** at all, so
`basic_handler.context_sensitive == false` for this title. `_opd_FUN_003ac074`
@ `0x3ac074` is the whole context selector:

```c
undefined4 _opd_FUN_003ac074(void) {
  cVar3 = _opd_FUN_0003c048(*(u32*)(TOC - 0x7fec));   // TOC = 0x0127189c
  if (cVar3 == '\0') return *(u32*)(TOC - 0x7fdc);    // = *(0x012698c0)
  else                return *(u32*)(TOC - 0x7fe0);   // = *(0x012698bc)
}
```

Both slots resolved and cross-verified two independent ways (raw bytes dumped
*and* Ghidra's own reference manager reporting the data reference):

| slot | value | string at that address |
|---|---|---|
| `0x012698c0` | `0x01303b58` | `NPWR03073` -> com_id `"NPWR03073_00"` |
| `0x012698bc` | `0x01303c84` | `NPWR00795` -> com_id `"NPWR00795_00"` |

(Both are the head of a 300-byte `{SceNpCommunicationId[12], passphrase[128],
signature[160]}` record - `0x01303b58 + 0x12c == 0x01303c84` exactly, and
`_opd_FUN_00080268` feeds `0x01303b58` and `0x01303b58+0x8c` to
`sceNpTrophyCreateContext` as com_id/sign, which confirms the record layout.
A third id, `NPWR00449` @ `0x00e625f9`, is referenced only by the trophy code
at `_opd_FUN_00080084` and by a pointer table at `0x012574d4` - not by the
basic handler.)

The selector `_opd_FUN_0003c048` is an obfuscated equality test:

```c
uint _opd_FUN_0003c048(int param_1) {
  uVar2 = *(uint*)(param_1 + 0x2e10) ^ 0xc0e2aff8;
  uVar1 = (int)uVar2 >> 0x1f;
  return ((uVar1 ^ uVar2) - uVar1) - 1 >> 0x1f;      // == 1 iff field == 0xc0e2aff8
}
```

i.e. **`context = NPWR00795_00` iff `*(g_config + 0x2e10) == 0xc0e2aff8`,
otherwise `NPWR03073_00`.** `g_config` is `*(0x012698b0)` = `0x0132c530`, a
BSS singleton (23 call sites for `_opd_FUN_0003c048` across the binary - it is
a general-purpose "is X" predicate, not invite-specific). **What sets that
field was NOT determined** - it is a register-computed write, which is the same
wall documented in `2026-08-16-net-sm-server-lobby-dispatch.md`. Confidence
that the bifurcation is real: high (verified addresses). Confidence about *what
it means* (region? SKU? disc-vs-PSN? online-pass?): none - untraced.

**This is the only mechanism by which two TLOU clients can end up with
different basic-handler contexts, and it is entirely plausible across two
differently-obtained copies of the game.** It is also trivially observable
live - see the checklist.

## Every other gate on the receive path (all verified in RPCS3 source)

Ordered as the event actually flows. Any one of these silently eats the invite.

1. **`rpcn_client::handle_message`** (`rpcn_client.cpp:3128-3147`) -
   `np::string_to_communication_id` rejects anything that is not exactly
   `<9 chars>_<2 digits>`; on failure logs `"Discarded invalid message!"` and
   drops it. Our RPCN forwards the sender's bytes verbatim, so this only fires
   if the sender's own com_id was malformed.
2. **Message-callback filter** (`rpcn_client.cpp:3175`) - `mainType` must equal
   a registered `type_filter`. Only relevant to the `RecvMessageCustom`/GUI
   dialog path, not to the basic-event path.
3. **`basic_handler_registered`** (`np_handler.cpp:1283`) - false if the game
   never registered, or if `sceNpBasicUnregisterHandler` ran
   (`_opd_FUN_0034f0fc` @ `0x34f0fc` does call it). Note RPCS3 returns
   `SCE_NP_BASIC_ERROR_EXCEEDS_MAX` from a *second* `RegisterHandler` while one
   is live - a failed re-register after an unregister/re-init cycle would leave
   the receiver deaf.
4. **`strncmp(msg.commId.data, basic_handler.context.data, 9)`**
   (`np_handler.cpp:1285`) - the gate this note is about.
5. **`mainType` switch** (`np_handler.cpp:1288-1306`) -
   `SCE_NP_BASIC_MESSAGE_MAIN_TYPE_ADD_FRIEND` and anything unknown `continue`
   (dropped). `INVITE`(3) maps to `SCE_NP_BASIC_EVENT_INCOMING_INVITATION`(5),
   or to `INCOMING_BOOTABLE_INVITATION`(23) if
   `msgFeatures & SCE_NP_BASIC_MESSAGE_FEATURES_BOOTABLE`. **Both 5 and 23 are
   inside the game's dispatch range** (its pump bounds-checks `event < 0x18`),
   so the BOOTABLE bit does not by itself break dispatch.
6. **The game's own pump**, `_opd_FUN_00355258` @ `0x355258`: it only calls
   `sceNpBasicGetEvent` when its handler callback has pushed onto a 12-byte-
   stride pending array (`*(TOC_0x012fde9c - 0x7948)`, count at
   `**(TOC - 0x7f8c)`), then indirect-jumps through a 24-entry table at
   `*(TOC - 0x793c)`. So the handler callback firing is load-bearing;
   `send_basic_event` is only reached inside gate 4.
7. **`get_basic_event` size clamp** (`np_handler.cpp`) - returns
   `SCE_NP_BASIC_ERROR_DATA_LOST` if the caller's `*size` is smaller than the
   invite payload. The game memsets a `0x200` buffer for this, so unlikely.

## A separate, definitely-broken thing worth knowing about

`_opd_FUN_0034923c` @ `0x34923c` (called from the pump's tail, gate 6) is the
game's unread-counter refresh:

```c
sceNpBasicGetCustomInvitationEntryCount(local_30);
iVar2 = sceNpBasicGetMessageEntryCount(4 /*CUSTOM_DATA_MESSAGE*/, local_30);
if (iVar2 == 0) { **(u32**)(TOC_0x012fde9c - 0x7ec4) = 0; }
```

Both of those RPCS3 HLE functions are hard stubs that unconditionally write
`*count = 0` (`sceNp.cpp`, both tagged `sceNp.todo`). So any game UI fed by
that global will read zero forever regardless of what our server does.
**Confidence this explains the live symptom: low** - it is the *custom data /
custom invitation* counter (type 4), not the `MAIN_TYPE_INVITE` basic-event
path, and the party-invite list is much more likely driven by gate 6's event
dispatch. Recorded so it is not rediscovered as a red herring - but if the
live checklist below shows the commIds matching *and* the basic event being
delivered, this becomes the next suspect and the fix would be an RPCS3-side
patch, not a server change.

## What was implemented (server-side)

`backend/rpcn/src/server/client/cmd_misc.rs`, `send_message`: the forwarded
`MessageDetails` now has its `communication_id` **rewritten per recipient** to
that recipient's own registered basic-handler context, so gate 4 can never
fail regardless of the `NPWR03073` / `NPWR00795` split.

This is possible because RPCS3 leaks the receiver's context to us for free:

```c++
// np_handler.cpp:921, inside register_basic_handler
presence_self.pr_com_id = *context;
```

and every `SetPresence` request is `forge_request_with_com_id(..., pr_com_id, ...)`
(`rpcn_client.cpp:2605`). RPCN already stores that in
`ClientSharedPresence::communication_id`. TLOU does call
`sceNpBasicSetPresenceDetails` (two call sites: `_opd_FUN_00396ad8`,
`_opd_FUN_00397d74`), and RPCS3 routes it to `nph.set_presence` -> `send_presence`,
so the value really does reach us in a normal session.

Behaviour:
- No-op when the ids already agree (the expected common case) - the original
  bytes are forwarded untouched.
- Rewrites only when the recipient's stored com_id passes a strict
  `[0-9A-Z]{9}_[0-9]{2}` validation (mirroring RPCS3's own
  `validate_communication_id` + `string_to_communication_id`), so we can never
  turn a deliverable message into one the receiver's parser discards.
- Logs `SendMessage: rewriting communication_id X => Y for recipient N` at
  `info` when it fires - that log line appearing at all is *proof* the two
  clients disagreed.
- The existing diagnostic `info!` from commit `04e4cff` is kept intact.
- Notifications are now built and sent per recipient rather than once for the
  whole set (required, since the payload can now differ per recipient).

Build: `cargo build --release` in `backend/rpcn` **succeeded** (incremental,
~15s - the "always a 7-minute clean rebuild" note in the handoff note did not hold
this time). Binary is fresh at `backend/rpcn/target/release/rpcn`.
**The running rpcn process was deliberately not touched.** To pick this up:
kill the running pid and relaunch from `backend/rpcn`.

## Live-test checklist (part A)

Two machines, `comradesean` + `mgnomad2`, both friends already.

1. **Restart rpcn** with the newly built binary (the old process is still
   running the pre-fix build).
2. On **both** machines, boot the game to the point where NP is up, then grep
   each RPCS3 log for:
   `sceNpBasicRegisterHandler(context=*0x...(NPWRxxxxx)` (logged at `warning`,
   so it is on by default).
   - **Both show the same NPWRxxxxx** -> the commId theory is dead for this
     pair; skip to step 5.
   - **They differ (one `NPWR03073`, one `NPWR00795`)** -> root cause confirmed,
     and the fix above should now paper over it. Record which machine reported
     which - that is the first real datapoint on what `*(g_config+0x2e10)`
     actually keys off.
3. Send a party invite from one to the other.
4. On the **server**, watch `catch_http`/rpcn's log for:
   - `SendMessage diagnostic: ... communication_id=...` (from `04e4cff`)
   - `SendMessage: rewriting communication_id ... => ...` (new). If this line
     appears, the two clients genuinely disagreed.
5. On the **receiving** machine's RPCS3 log, in order:
   - `rpcn: Received message from <sender>` -> RPCN delivery works.
   - `nph: basic_event: event:5, from:<sender>...` (or `event:23`) -> **gate 4
     passed and the game's pump consumed the event.** If you see `Received
     message` but no `basic_event`, gate 4 (or 3) is still eating it.
   - `sceNpBasicGetEvent` warnings -> the game is pumping at all.
6. Then check the in-game Invites screen.
   - Empty *despite* a logged `basic_event: event:5` -> the commId chain is
     fully exonerated; move to the `sceNpBasicGetMessageEntryCount`/
     `GetCustomInvitationEntryCount` stub theory above, which is an RPCS3 patch,
     not a server change.
   - Populated -> done.

Note that step 2 alone (30 seconds, no invite needed) settles the entire
root-cause question for part A, so do it first.
