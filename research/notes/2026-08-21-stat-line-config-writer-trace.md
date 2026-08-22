# The `task-%x` line's throttle/ip/port fields: writer found, and it explains tonight's live zero-read directly

Date: 2026-08-21. Follow-up to
`research/notes/2026-08-21-stat-line-save-gate-investigation.md`, which
identified `FUN_007f1acc`'s GATE 1 (`param_1[0x4e1] > 0`, `param_1[0x4e3] !=
0`, `param_1[0x4e4] != 0`) and confirmed live, via a breakpoint at
`FUN_007f1acc`'s entry (`0x007f1acc`) during a real autosave, that the
save-manager singleton at `0x44148220` had `counter=0, modulus=0, ip=0,
port=0` at the moment of a genuine save event. This note traces WHERE those
three fields (throttle modulus `param_1[0x4e1]`/`+0x1384`, ip
`param_1[0x4e3]`/`+0x138c`, port `param_1[0x4e4]`/`+0x1390`) are ever
written, statically, and cross-checks the result against this server's own
live HTTP log from the same session. All addresses are **01.00** VMAs from
`research/disasm/full.asm`.

## The writer: `FUN_007f149c`, the save-manager's constructor

A raw grep for `stw rX,N(r31)` with `N` in `{4992, 4996, 5000, 5004, 5008}`
(decimal for `0x1380, 0x1384, 0x1388, 0x138c, 0x1390`) across the whole
144 MB disassembly returns exactly one function's worth of hits, all in
`r31`-relative stores (`r31 = mr r31,r3` at function entry, i.e. `this`):

```
7f1664: stw r0,5004(r31)   ; +0x138c = 0   (zero-init)
7f1668: stw r0,4992(r31)   ; +0x1380 = 0   (zero-init)
7f166c: stw r0,4996(r31)   ; +0x1384 = 0   (zero-init)
7f1670: stw r0,5008(r31)   ; +0x1390 = 0   (zero-init)
7f1674: stw r0,5000(r31)   ; +0x1388 = 0   (zero-init)
...
7f1744: stw r3,4996(r31)   ; +0x1384 = <parsed int>   (modulus write #1)
7f1774: stw r27,4996(r31)  ; +0x1384 = 0 (r27 is provably 0 here)  (modulus write #2, a reset)
7f1798: stw r3,5004(r31)   ; +0x138c = <parsed int>   (ip write)
7f17d0: stw r0,5008(r31)   ; +0x1390 = <parsed int or 0>  (port write)
```

This is `.opd.FUN_007f149c @ 007f149c`, in the same compilation unit as
`FUN_007f1acc` - both use the identical literal-pool anchor `0x012fe508`
(`FUN_007f1acc`'s own `puVar5 = PTR_DAT_012fe508`; `FUN_007f149c`'s `r30 =
lwz r30,-29548(r2)` resolves to the same slot). Reading the anchor's pointer
target and the string constants at the offsets this function loads
(`research/tools/eboot_analysis/eb.py`, anchor value `0x0128b390`):

| slot offset from anchor | contents |
|---|---|
| `-32504` | `"gamelib/save/saveworker.cpp"` |
| `-32496` | `"fileBufferSize == (m_file.m_bufferSize-sizeof(Header))"` |
| `-32484` | `"%s/%s/autosave"` |
| `-32480` | `"%s/campaign.config.txt.crypt"` |
| `-32476` | `"http://t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt"` |

`FUN_007f149c` is `gamelib/save/saveworker.cpp`'s constructor. It is the
save-manager object's own constructor, not a separate config-loader class.

## The gate: NP login, then a live download of `campaign.config.txt.crypt`

Reading `0x7f1660`-`0x7f17d4` in order:

1. `0x7f1664`-`0x7f1674`: unconditionally zero-init all five fields
   (`+0x1380`..`+0x1390`, i.e. counter/modulus/pad/ip/port).
2. `0x7f1678`: `bl 0xe5772c` = **`sceNpManagerGetNpId`** (confirmed by NID
   `0xFE37A7F4` in `research/ghidra/scenp_nid_table.txt:56`). `r27 = r3`
   (return code). `0x7f1680`-`0x7f1688`: `cmpwi cr7,r3,0; bne cr7,0x7f17d4` -
   **if NpId lookup fails, skip straight past the entire config block**,
   leaving all five fields at their zero-init values permanently (the
   constructor runs once - see "singleton" below - so there is no later
   retry inside this function).
3. `0x7f168c`-`0x7f16dc`: with NpId confirmed, build the request path
   `"<base>/campaign.config.txt.crypt"` (`_opd_FUN_00e46670`, the same
   formatter this function's sibling `FUN_007f1acc` uses for its own stat
   lines) and call `_opd_FUN_00ac5b40(auStack_1..., <formatted url>, ...)`.
   `FUN_00ac5b40` is the **shared HTTP-download function** used identically
   by the net1.bin/patch download paths (confirmed in
   `research/notes/2026-08-14-crypt-decrypt-investigation.md:10` -
   "download function ... handles the actual HTTP GET" - and
   `research/notes/2026-08-14-repack-rejection-investigation.md:152`, which
   traces its internals: `FUN_00ac59a0` does the actual streaming HTTP GET,
   `FUN_00ac3af8` is invoked on success). `research/ghidra/download_fn_decomp.txt`
   confirms the wrapper shape: `FUN_00ac5b40` calls `FUN_00ac59a0` into a
   21656-byte stack buffer, and only calls `FUN_00ac3af8` (parse/decrypt) if
   the download itself returned 0.
4. `0x7f16e4`-`0x7f16e8`: `cmpwi cr7,r3,0; ble cr7,0x7f17d4` - **if the
   download+decrypt result is `<= 0`, skip straight past the entire config
   block**, same destination as the NpId failure path. Fields stay zero.
5. `0x7f16ec`-`0x7f17d0`: only reached on a successful download. Three
   string-keyed lookups against the downloaded/decrypted buffer
   (`_opd_FUN_00ada358`, a key->value lookup over the parsed config,
   confirmed elsewhere in this project's notes as a generic
   config-key-lookup primitive) each feed `_opd_FUN_00e43e50` (a
   string-to-int parse, called with base 10) and the integer result is
   stored into `+0x1384` (modulus), `+0x138c` (ip), `+0x138c`/`+0x1390`
   (port) in turn. **The modulus write is itself double-gated**: if the
   first lookup key is absent (`beq cr7,0x7f1774`) OR present but its first
   character isn't `'1'` (`0x7f1768`-`0x7f1770`), the code falls through to
   `0x7f1774` and writes `r27` - which is provably `0` at this point (it was
   set from `sceNpManagerGetNpId`'s return code, and this whole block is
   only reached when that call returned `0`) - back into `+0x1384`. So even
   a **successful** download resets the modulus to `0` (permanently
   disabling the notify path) unless the downloaded config carries a
   specific `"1"`-valued boolean-style key.

**Verdict on the trigger condition:** ip/port/modulus are populated
exclusively by a genuine "connect to backend" step - a live HTTP GET+decrypt
of a per-title config file (`campaign.config.txt.crypt`) from an
Naughty-Dog/Sony S3 bucket, gated first on `sceNpManagerGetNpId` succeeding.
This is NOT the same mechanism the other sibling services
(`heartbeat-server`, `leaderboard-server`, etc.) use to resolve their own
`{ip,port}` - those are net1.bin/net10.bin hostname-table entries resolved
through this project's DNS-redirect + `FUN_00acc424` hello handshake
(`docs/protocol/0x11_ticket_server_hello.md`), a completely different code
path with no HTTP GET involved. `single-player-server`'s ip/port,
specifically, arrive as two of several **values inside the downloaded
config file itself**, not from a hostname table lookup at all - the earlier
gate-investigation note's inference that they "resolve through this
project's own net1.bin-driven hosts-redirect setup the same way
ticket-server does" is REVISED: that was true for *how the client reaches
`single-player-server` once GATE 1 passes* (via `FUN_00acc424`'s hello
handshake, same as every sibling), but it is wrong for *how ip/port get into
`param_1[0x4e3]`/`[0x4e4]` in the first place* - that is this separate S3
config-download path, wired up completely independently.

## Live corroboration: the download IS happening, and IS failing, tonight

`server/http_gateway.py` intercepts `t1.campaign.config.s3.amazonaws.com`
(it is on `UPSTREAM_ALLOWED_HOSTS`, `server/http_gateway.py:76`) and, per its
own documented behavior, attempts a live upstream fetch against the real S3
bucket before falling back to an **empty 200 OK body**
(`server/http_gateway.py:9-21`) if that live fetch fails - which it does,
because the real Naughty Dog/Sony content bucket for this specific hostname
is not one of the ones still alive.

`server/logs/http_gateway.log` shows this exact request happening
repeatedly across the whole log history (875 occurrences total), including
twice in the minutes immediately around tonight's live breakpoint session:

```
==== 2026-08-21T21:58:48.166057 from 192.168.1.100:64226 ====
GET /campaign.config.txt.crypt HTTP/1.1
Host: t1.campaign.config.s3.amazonaws.com
Connection: close
User-Agent: DNTG-HTTPC/1.1
---- responded: 200 OK (live fetch from t1.campaign.config.s3.amazonaws.com failed) ----

==== 2026-08-21T21:58:50.159190 from 192.168.1.100:64227 ====
GET /campaign.config.txt.crypt HTTP/1.1
Host: t1.campaign.config.s3.amazonaws.com
...
---- responded: 200 OK (live fetch from t1.campaign.config.s3.amazonaws.com failed) ----
```

An empty body cannot decrypt or parse successfully as a real
`campaign.config.txt.crypt` blob, so `FUN_00ac3af8` (the parse/decrypt step
inside `FUN_00ac5b40`) fails, `FUN_00ac5b40` returns `<= 0`, and
`FUN_007f149c` takes the `ble cr7,0x7f17d4` skip at step 4 above - **exactly
the state read live at `0x44148220` tonight** (counter/modulus/ip/port all
`0`). This is not a guess stacked on the decompile alone: the client's own
outbound request for this file, and this server's own failure to satisfy
it, are both directly logged in the same session the live memory read was
taken in.

Two requests ~2 seconds apart (`21:58:48` and `21:58:50`, and the same
pattern recurs earlier in the log at `20:53:35`/`20:53:37`,
`21:01:33`/`21:01:35`, `21:03:24`/`21:03:27`, `21:14:44`/`21:14:46`) suggests
either a retry-on-failure inside the client's download path or that
whatever calls into the constructor's containing function runs more than
once per session - this project's flag-gated single-call-site read (below)
doesn't fully explain the paired-request cadence and is noted as an open
detail, but it does not change the outcome: every attempt this log has ever
recorded ends in the same empty-body failure.

## Whether `single-player-server`'s ip/port could ever come from OUR server instead

Not by pointing DNS at this server the way `heartbeat-server`/
`leaderboard-server` do - those values never reach a hostname-resolve step
at all in this code path; they come from parsing the downloaded file's
content. The only way to make GATE 1 pass through this constructor is to
serve a `campaign.config.txt.crypt` body that:

1. Is byte-identical enough to what `FUN_00ac59a0`/`FUN_00ac3af8` expect to
   decrypt/parse successfully (format unknown - this pass did not reverse
   the `.crypt` container; `research/notes/2026-08-14-crypt-decrypt-investigation.md`
   and `research/notes/2026-08-14-repack-rejection-investigation.md` cover a
   DIFFERENT `.crypt` asset's format and note that downloads elsewhere in
   this same generic pipeline are HMAC-verified against a digest supplied
   by the caller before the constructor's download call - **whether
   `FUN_007f149c`'s specific call site supplies such a digest, and if so
   what it is, was not checked this pass** - if it does, no server-authored
   replacement content can pass verification without the real key/digest),
2. carries a config key resolving to a boolean-ish `"1"` string for the
   toggle checked at `0x7f1768`-`0x7f1774` (needed for the modulus to stick
   rather than reset to `0`), and
3. carries two more keys that parse (via `_opd_FUN_00e43e50`, base 10) to a
   nonzero ip and a nonzero port - values that would need to be an
   `{ip,port}` pair this server's own sibling-hello handler
   (`FUN_00acc424`'s target, same as every other sibling service) can
   actually answer, i.e. this server's own address.

This is a real, actionable path in principle, but is gated on reversing the
`.crypt` container format and, if it exists, the HMAC/digest-pinning step -
neither attempted this pass.

## Singleton confirmation (task item 4)

A whole-image search for `bl 0x7f149c` finds exactly **one** call site,
`0x7ef9dc`, inside a function starting at `0x7ef908`. That function:

```
7ef928: lwz  r9,-32768(r30)
7ef940: lwz  r9,0(r9)
7ef94c: lbz  r0,11691(r9)
7ef950: cmpwi cr7,r0,0
7ef954: bne  cr7,0x7efa6c          ; already-done flag set -> skip alloc+construct entirely
7ef9c4: li   r3,5024                ; sizeof(save-manager) = 0x13a0
7ef9c8: bl   0x914e60               ; allocator
7ef9dc: bl   0x7f149c               ; placement-construct into the fresh 5024-byte block
```

`5024` bytes (`0x13a0`) comfortably contains the highest offset this object
uses (`+0x1390`, 4 bytes = ends at `0x1394`), confirming this is the same
class. The `lbz r0,11691(r9)` guard before the allocate+construct pair is a
one-shot "already initialized" check - this IS a genuine lazy-constructed
singleton pattern, not a coincidental address reuse. Combined with the
live observation of the same address (`0x44148220`) across two separate
breakpoint hits tonight, the two lines of evidence agree: one construction,
one object, for the life of the process. **"Was it ever written even once
this boot" is exactly the right question, and per the HTTP log, the answer
for tonight's boot is no** - every recorded attempt at the required download
failed.

The paired ~2-second-apart request cadence noted above is not explained by
a single one-shot construction and is flagged as unresolved, but does not
change the singleton verdict for the *object itself* (still one instance,
one address) or the outcome (every attempt failed).

## Bottom line

- **Writer found and fully decompile-traced**: `FUN_007f149c`
  (`0x007f149c`), the save-manager's own constructor.
- **Trigger condition found**: `sceNpManagerGetNpId()` must succeed, THEN a
  live HTTP GET+decrypt of `campaign.config.txt.crypt` (default URL
  `http://t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt`)
  must succeed, THEN (for the modulus specifically) the downloaded config
  must carry a `"1"`-valued toggle key or the modulus is reset to `0` even
  on an otherwise-successful download.
- **Why it's still zero, live-confirmed**: this server's own
  `server/http_gateway.py` intercepts that exact request and, because the
  real S3 bucket for this path is dead, answers with an empty `200 OK` body
  (`server/logs/http_gateway.log`, entries at `2026-08-21T21:58:48` and
  `:50`, directly bracketing tonight's breakpoint session) - which cannot
  parse/decrypt successfully, so the whole field-population block is
  skipped and every field keeps its constructor-time zero-init value for
  the rest of the process's life (confirmed singleton, one construction).
- **Not resolved this pass**: the `.crypt` container's actual format, and
  whether this specific download call site is HMAC/digest-pinned against a
  value this project doesn't have (which would rule out ever serving a
  server-authored file the client accepts). Both would need to be reversed
  before attempting to author a working `campaign.config.txt.crypt`
  response; no live test is needed to make further static progress here -
  this is a static reverse-engineering task (decrypt algorithm +
  digest-pinning check), not a live-state question.
