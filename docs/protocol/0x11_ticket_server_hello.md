# `ticket-server` session-establishment handshake (opcode `0x11` family)

Companion doc for:
- `protos/0x11_ticket_server_hello.ksy`
- `protos/0x11_ticket_server_hello_response.ksy`
- `protos/0x11_ticket_server_ticket_submit.ksy`
- `protos/0x11_ticket_server_ticket_submit_response.ksy`

**status: partial** (message A confirmed high-confidence; message B confirmed
structurally with content semantics unconfirmed; messages C/D confirmed
structurally, D's content totally unconfirmed)

## What this is

After RPCN hands the game a valid NP ticket (`sceNpManagerRequestTicket2` /
`sceNpManagerGetTicket`, confirmed live: RPCS3 log shows
`SCE_NP_MANAGER_EVENT_GOT_TICKET, ticket size 248` and the game accepts it
without complaint), `NetInit` (`FUN_003557a8` @ `0x003557a8`) opens a raw TCP
connection to a backend the game's own strings call `"ticket-server"`
(reached on port 7320 via this build's patched `net1.bin` config) and runs a
four-message handshake on that single connection before considering the
connection usable. This doc nails down the wire format of all four messages
to the extent the client-side decompiled code proves it.

This supersedes the "loose read, unconfirmed" byte-0-is-opcode guess in
`research/notes/ticket-server-first-capture.md` - that note's raw capture is
now fully explained field-by-field below.

## The four messages, in order, on one TCP connection

| # | Direction | Name | Size | Status |
|---|---|---|---|---|
| A | client -> server | `ticket_server_hello` | 88 bytes (fixed) | **confirmed**, high confidence |
| B | server -> client | `ticket_server_hello_response` | 8 bytes (fixed) | confirmed structurally; content beyond 1 required byte unconfirmed |
| C | client -> server | `ticket_server_ticket_submit` | 2 + ticket_length bytes | confirmed structurally, high confidence |
| D | server -> client | `ticket_server_ticket_submit_response` | 16 bytes (fixed) | confirmed size only; content wholly unconfirmed |

The client only proceeds from A to C if B passes validation; it only closes
cleanly with a good NetInit result if D is received successfully. If B never
arrives, or arrives with the wrong first byte, the client aborts immediately
and never sends C at all - **this is exactly what happened in every prior
capture attempt** (see "Why prior captures never got past message A" below).

## Message A: `ticket_server_hello` (client -> server, 88 bytes)

### The code that builds and sends it

`FUN_00acc424` (`0x00acc424`), called from `FUN_003557a8` at call site
`0x00355f84`, immediately after a successful low-level TCP connect
(`FUN_00acbf90` @ `0x00acbf90`, already confirmed generic/reused elsewhere -
not re-analyzed here). Decompile:

```c
int _opd_FUN_00acc424(int param_1,undefined4 param_2,undefined4 param_3,undefined8 param_4)
{
  ...
  uVar1 = _opd_FUN_00e40ad8(param_4);           // strlen(service_name)
  if ((uVar1 < 0x40) &&                          // must be < 64 chars
     (iVar2 = _opd_FUN_00acbf90(param_1,param_2,param_3,1,0), -1 < iVar2)) {  // raw connect()
    uVar3 = _opd_FUN_00e408d8();                 // local PRNG -> uVar3
    *(undefined4 *)(param_1 + 0x4c) = uVar3;      // cache nonce in conn struct
    _opd_FUN_00e45b10(auStack_b0,param_4);        // strcpy(buf+0x18, service_name)
    iVar2 = _opd_FUN_00acb93c(param_1,local_c8,0x58,1);   // send(88 bytes)
    if ((iVar2 < 1) ||
       ((iVar2 = _opd_FUN_00acbd98(param_1,local_e0,8,1), iVar2 < 1 ||   // recv(8 bytes)
        (iVar2 = -1, local_e0[0] != '\"')))) {            // byte[0] must be 0x22
      _opd_FUN_00acbad0(param_1);                 // fail -> close
    } else {
      iVar2 = 0;
      *(undefined4 *)(param_1 + 0x50) = local_dc; // success -> store response[4..7]
    }
  }
  return iVar2;
}
```

`param_4` is the service-name string; at the one confirmed call site
(`0x00355f84`, inside `FUN_003557a8`) it's loaded from a config/TOC slot that
resolves to the literal string `"ticket-server"` (string address `0x00e7a2d0`
in this build, confirming `research/ghidra/ticket_server_handler_report.txt`'s
original finding - note that `strings -t x` reports raw *file offsets*, not
VMAs, for this ELF: this build's first LOAD segment maps file offset `0` to
VMA `0x10000`, so a `strings` hit at file offset `0xe6a2d0` is VMA
`0x00e7a2d0`; easy to get this wrong, flagging it here since it tripped this
pass up too).

### Byte-exact layout, from raw disassembly (not just the decompiler)

Raw PPC disassembly of `0xacc4bc`-`0xacc58c` (see
`research/ghidra/socket_wrapper_family_decomp.txt` and the raw `objdump`
excerpt captured this session) shows the actual stores, with `r1` = this
function's own stack pointer (frame allocated fresh via
`stdu r1,-336(r1)` at function entry) and the send buffer starting at `r1+136`:

```
li  r0,17        ; 0x11
stb r0,136(r1)    ; packet[0]  = opcode        = 0x11
li  r0,0
stb r0,137(r1)    ; packet[1]  = reserved0     = 0x00
li  r0,0
sth r0,138(r1)    ; packet[2:4]= reserved1     = 0x0000  (halfword store)

bl  0xe408d8      ; local PRNG call -> r9
stw r9,140(r1)    ; packet[4:8]= client_nonce  = PRNG output (masked to 30 bits)
stw r9,76(r18)    ; ALSO cached in conn struct at +0x4c

; --- packet[8:24] (16 bytes): byte-by-byte copy loop ---
addi r9,r1,120    ; SOURCE = r1+120  (16 bytes before the packet buffer start
                   ;   at r1+136 - i.e. INSIDE this function's own fresh
                   ;   336-byte frame, at an offset this function NEVER WRITES
                   ;   before this copy)
addi r11,r1,144   ; DEST   = packet[8:24]
; 16x { lbz rN, k(r9); stb rN, k(r11) }   for k = 0..15

; --- packet[24:88] (64 bytes): service name ---
addi r4,r1,136(+24)   ; addi r3,r1,160  => dest = packet+24 = offset 0x18
bl  0xe45b10           ; strcpy-equivalent(dest=packet+0x18, src=param_4)

; then: send(conn, packet_base=r1+136, len=88, flags=1)
```

`0x11` = opcode. `0x00acc424` is *not itself* named after this opcode in the
binary (no symbol survives) - `0x11` is simply the literal value stored, and
is unrelated to `net_event_type` opcode `17` (`kill_info`) in
`protos/common/opcodes.ksy`; that enum is for the in-game gameplay-event
protocol on a completely different connection/subsystem.

### The "leaked stack garbage" field - why it's confirmed garbage, not data

The 16-byte copy at packet offset 8 sources from `r1+120..135`. This address
range is **inside `FUN_00acc424`'s own stack frame** (the frame was just
allocated 60-ish instructions earlier via `stdu r1,-336(r1)`), and **no
instruction between function entry and this copy writes to `r1+120..135`** -
confirmed by reading every store instruction in the disassembly window
`0xacc424`-`0xacc590` (reproduced above in full; there is no `stb`/`sth`/`stw`
targeting that address range before the copy loop reads it). This means the
16 bytes are whatever was left on the CPU stack from a prior, deeper call at
that same stack depth - not initialized by this function, its arguments, or
anything the caller explicitly passed in for this purpose.

This directly answers coordinator suggestion #1 from this session's brief
("check whether the pointer-looking request bytes are derived from the RPCN
ticket"): **no** - they cannot be, because they are proven-uninitialized
memory read before any ticket-related code in this call path has even run
(the ticket isn't fetched from RPCN until *after* this handshake succeeds -
see message C below). The `d0 0f xx xx`-shaped values seen in the one real
capture are self-consistent with genuine PS3/RPCS3 PPU stack addresses
sitting in that memory purely by coincidence of what the stack held at that
depth - not an intentional session-binding mechanism.

This also answers coordinator suggestion #2 (try the known Blowfish/HMAC-SHA1
keys from the `.crypt` investigation against these "opaque" bytes): **not
applicable / moot** - since the bytes are proven uninitialized stack garbage
rather than any kind of derived ciphertext or digest, there is nothing
meaningful for a key-based transform to have produced. Not tested, because
the premise (that these are encrypted/hashed data) is now ruled out.

### `client_nonce` field evidence

`FUN_00e408d8` (`0x00e408d8`) is a small custom PRNG: a 32-slot table seeded
once via a linear-congruential generator (multiplier `0x19660d`, increment
`0x3c6ef35f` - the classic Numerical-Recipes-style LCG constants), returning
`raw_output & 0x3fffffff` (masks off the top 2 bits, so the high byte of the
returned 32-bit value is always `<= 0x3f`). The one real capture's bytes
`27 ab 50 86` at packet offset 4 have high byte `0x27`, which is `<= 0x3f` -
consistent with this mask, corroborating the identification (not proof by
itself, but a real match rather than a coincidence check that could easily
have failed). This value is also cached into the connection object at
`conn+0x4c`; no code reading `conn+0x4c` again was located in this pass
(open item - see Next Steps).

### `service_name` field evidence

`FUN_00e45b10` (`0x00e45b10`) is a hand-unrolled `strcpy`-equivalent (8-byte,
then 4-byte, then byte-at-a-time copy loop, stopping at a NUL) - confirmed by
its exact match to a standard SWAR (SIMD-within-a-register) zero-byte-scan
`strcpy` idiom. It's called as `FUN_00e45b10(dest=packet+0x18, src=param_4)`
with no length bound and no zero-fill of the destination buffer beforehand or
after - meaning bytes after the copied NUL terminator, up to the 64-byte
buffer boundary (packet offset `0x18` through `0x57`), are **also** leftover
stack garbage, same root cause as the offset-8 field. `FUN_00e40ad8`
(`0x00e40ad8`) - called once at function entry as
`strlen(param_4) < 0x40` - is a SWAR `strlen` (same zero-byte-scan idiom,
confirmed by its `LZCOUNT`/masking pattern), gating service names to 63 chars
+ NUL max.

### Why prior captures never got past message A

Our TCP catcher (`tools/catch_tcp.py`, not touched this session per the
"hands off" rule) never implemented this protocol - it either echoed the
request back or sent nothing. `FUN_00acc424`'s validation
(`local_e0[0] != '"' -> close`) means **any** response that isn't exactly
8 bytes starting with `0x22` causes an immediate `_opd_FUN_00acbad0` (close)
and a `-1` return, which the caller (`FUN_003557a8`) turns into the observed
`ERROR NET INIT ffffffff` / connection-reset symptom. This fully explains the
originally-reported failure mode without needing to guess further.

## Message B: `ticket_server_hello_response` (server -> client, 8 bytes)

Confirmed from the same `FUN_00acc424` disassembly (see `research/ghidra/`
raw objdump capture, addresses `0xacc594`-`0xacc5e8`):

```
addi r4,r1,112 ; recv dest
li   r5,8      ; recv length = 8
bl   0xacbd98  ; recv()
...
lbz  r0,112(r1)      ; response[0]
cmpwi cr7,r0,34      ; must equal 0x22 ('"')
beq  cr7,0xacc5e0     ; -> success path
                       ; else: close(), return -1
0xacc5e0:
lwz  r0,116(r1)       ; response[4:8], big-endian u32
li   r29,0             ; return 0 (success)
stw  r0,80(r18)        ; conn->+0x50 = response[4:8]
```

`ack_magic` (byte 0) is the only field the client actually branches on.
Bytes 1-3 are received but never read by any compare/branch in this function.
Bytes 4-7 are read as a big-endian `u32` and persisted into the connection
object at `+0x50` for later use - a real, meaningful field, but its
downstream consumer was not located in this pass (see Next Steps). **No real
response has ever been captured** (see above) - this schema describes what
the client's own code requires/reads, not a transcription of a live example.
A minimal, protocol-legal response for testing purposes would be
`22 00 00 00 xx xx xx xx` (any 4 bytes for the session token).

## Message C: `ticket_server_ticket_submit` (client -> server, variable length)

Confirmed from `FUN_003557a8`'s decompile, the block immediately following a
successful `FUN_00acc424` call (same connection object, no reconnect):

```c
iVar22 = _opd_FUN_00acc424(auStack_56c, *puVar29, puVar29[1], svc_name_ptr);
if (iVar22 != 0) { _opd_FUN_00acbad0(auStack_56c); goto LAB_00355fa4; }  // message A/B failure path

*puVar24 = (char)((uint)local_68c >> 8);   // ticket_length high byte
puVar24[1] = (char)local_68c;              // ticket_length low byte
iVar22 = _opd_FUN_00acd5f8(auStack_56c, puVar24, local_68c + 2);  // send(2 + ticket_length bytes)
if ((iVar22 == local_68c + 2) &&
   (iVar25 = _opd_FUN_00acd568(auStack_56c, auStack_500, 0x10), -1 < iVar25)) {
  _opd_FUN_00acbad0(auStack_56c);   // close after message D received
  ...
}
```

`local_68c` is the ticket size, obtained a few lines earlier via
`sceNpManagerGetTicket(0, &local_68c)` (size query) then
`sceNpManagerGetTicket(puVar24 + 2, &local_68c)` (actual ticket bytes,
written starting 2 bytes into the same allocated buffer - i.e. the buffer
was allocated as `ticket_size + 2` bytes specifically to leave room for this
length prefix). This is unambiguous: message C is
`[u16 BE ticket_length][raw ticket bytes]`, sent on the *same* socket right
after a passing message B, with no additional framing.

This directly answers coordinator suggestion #3 ("look for a fixed-size
receive buffer allocation right after the send, to learn the expected
response size before understanding field semantics") - the buffer is
`auStack_500`, and the length argument to the receive call
(`_opd_FUN_00acd568(auStack_56c, auStack_500, 0x10)`) is a literal `0x10`
(16) - see message D.

## Message D: `ticket_server_ticket_submit_response` (server -> client, size self-described, NOT a fixed 16 bytes)

**CORRECTED (2026-08-14, second follow-up pass).** Two claims from the prior
pass are now withdrawn: "16 bytes fixed size" and "content/consumer
untraced but the buffer exists." Both were downstream of the same
mis-reading - see "Encrypted frame layer" below, which supersedes this
message's shape entirely. Message D uses the identical 20-byte-header +
encrypted-payload frame as message C, decoded by `FUN_00acbb90`
(`0x00acbb90`), keyed by `client_nonce` (`conn+0x4c`) rather than
`session_token`. The `0x10` literal at the `FUN_00acd568` call site
(previously read as "the expected response size") is not consumed anywhere
in `FUN_00acbb90`'s decompiled body - another parameter the decompiler
silently dropped, same failure mode documented below - so it does not
actually constrain the response to 16 bytes; the real size is whatever
`plaintext_len` the frame header says. See
`protos/0x11_ticket_server_ticket_submit_response.ksy` for the corrected
field-by-field schema.

## Encrypted frame layer: messages C and D are NOT sent/received raw

**Discovered and confirmed 2026-08-14, second follow-up pass this session**,
triggered by the first-ever live capture of a real message C (272 bytes,
`captures/tcp_catch.log`, connection at `2026-08-14T08:11:28`) that flatly
contradicted the original "2-byte length + raw ticket bytes" schema (first
two bytes read as a bogus 13058-byte length under that schema, which cannot
be reconciled with a 272-byte total message under any endianness).

### Where the original analysis went wrong

The original schema was built entirely from `FUN_003557a8`'s decompile of
the send/recv call sites (`_opd_FUN_00acd5f8(auStack_56c, puVar24,
local_68c + 2)` and `_opd_FUN_00acd568(auStack_56c, auStack_500, 0x10)`),
which show 3 arguments each. But decompiling `FUN_00acd5f8`
(`0x00acd5f8`) and `FUN_00acd568` (`0x00acd568`) **on their own** shows
each only using its *first* argument (the connection object) - the
buffer/length arguments never appear anywhere in their decompiled bodies:

```c
int _opd_FUN_00acd5f8(int param_1)   // decompiler shows only 1 param used!
{
  int iVar1 = _opd_FUN_00acb6fc(param_1);   // buffer/length args from the CALL SITE are NOT re-passed here...
  ...
}
```

Raw disassembly of `FUN_00acd5f8` (`0xacd5f8`-`0xacd67c`) confirms why: the
function never touches r4/r5 (the ABI registers holding buffer/length) at
all - it just calls `bl 0x00acb6fc` immediately. Since r4/r5 are never
clobbered, they pass through to `FUN_00acb6fc` **unchanged, by register
inertia**, not because `FUN_00acd5f8` explicitly forwards them. Ghidra's
per-function decompiler has no way to see this without inter-procedural
signature propagation (this project's Ghidra project is opened with
`-noanalysis`, relying on a prior analysis pass that evidently didn't
recover this), so it silently drops the parameters from
`FUN_00acd5f8`/`FUN_00acd568`'s own decompiled prototypes. The real work -
and the real wire format - lives one level deeper, in `FUN_00acb6fc`
(send) and `FUN_00acbb90` (receive), neither of which the original pass
decompiled individually.

### The real frame format

Fully decompiled this pass (`research/ghidra/base64_layer_decomp.txt`,
`research/ghidra/cipher_core_decomp.txt`, `research/ghidra/send_path_disasm.txt`).
`FUN_00acb6fc` (`0x00acb6fc`) builds every outbound frame after the hello
handshake as:

```
offset 0      u1   frame_magic   = 0x33 ('3', fixed literal - `li r0,0x33; stb`)
offset 1      u1   pad_count     = (-plaintext_len) & 3
offset 2      u2   plaintext_len = length of the real, unencrypted payload (BE)
offset 4      16B  auth_tag      = keyed digest over the plaintext
offset 20     N    ciphertext    = plaintext_len + pad_count bytes, XOR-keystream-encrypted in place
```

```c
// FUN_00acb6fc(conn, plaintext_buf, plaintext_len), decompiled:
if (*(int*)(conn+0x68) == 0) { /* lazy-alloc a 0x800-byte staging buffer at conn+0x68 */ }
key_table = *(u32*)(TOC_slot - 0x8000);           // static 16-byte key table, see below
pad = (-len) & 3;
FUN_00db5ec0(key_table, *(u32*)(conn+0x50), keystream_state);   // init, keyed by session_token
FUN_00db7f88(keystream_state, plaintext_buf, len + pad);         // digest the PLAINTEXT
FUN_00db5e50(keystream_state, tag_out /* 16 bytes */);            // finalize digest -> auth_tag
staging[cursor+0] = 0x33; staging[cursor+1] = pad;
staging[cursor+2] = len>>8; staging[cursor+3] = len;
memcpy(staging+cursor+4, tag_out, 16);
cursor += 20;
memcpy(staging+cursor, plaintext_buf, len+pad);      // raw copy first...
FUN_00db5ec0(key_table, *(u32*)(conn+0x50), keystream_state);   // re-key (same session_token value)
FUN_00db7cb0(keystream_state, staging+cursor, len+pad);           // ...then XOR-encrypt in place
*(u32*)(conn+0x50) += 1;                                          // rolling counter advances
```

The receive side, `FUN_00acbb90` (`0x00acbb90`, invoked in a poll loop by
`FUN_00acd568`), is the exact mirror image: requires `frame_magic == 0x33`
or closes the connection (`_opd_FUN_00acbad0`) immediately; decrypts
`plaintext_len + pad_count` ciphertext bytes via `FUN_00db7e08` (same ARX
math, applied to already-received bytes); independently recomputes the tag
over the now-decrypted plaintext and **memcmp's it against the embedded
`auth_tag`** (`_opd_FUN_00e498f0(computed, embedded, 0x10)`); any mismatch
is fatal (connection closed). Critically, the receive side keys itself with
`*(conn+0x4c)` - **`client_nonce` from message A, not `session_token`** -
and increments *that* counter after each frame it decodes. This is a
sensible design: `client_nonce`'s starting value is chosen by the *client*
and sent to the server in cleartext in message A, so the server can derive
the correct receive-side key for its own outgoing frames (i.e. message D)
without any secret exchange - symmetric to how `session_token` (chosen by
the *server*, sent in message B) keys the client's sends.

### Byte-exact confirmation against the real capture

```
33 02 00 fa bb 75 ef e6 43 c7 25 d5 3a bf ca 68  02 a0 f7 a7 ...(252 more bytes of ciphertext)...
```

`frame_magic=0x33` (matches), `pad_count=0x02`, `plaintext_len=0x00fa=250`.
Predicted total frame length = `20 + plaintext_len + pad_count = 20 + 250 +
2 = 272` - **exactly** the captured length. Independently, `(-250) & 3 ==
2` matches the captured `pad_count` too. Two independent arithmetic checks,
both exact, against a real live capture - this is about as strong a
confirmation as this investigation gets without a working decrypt.
`250` is also a plausible NP ticket size (an unrelated earlier RPCS3 log
line observed `248` for a different ticket - sizes legitimately vary by a
few bytes run to run).

This also explains two things the coordinator's team had already ruled out
as red herrings, which turn out not to be red herrings after all:
Blowfish-with-the-known-`.crypt`-key producing garbage on the 272 bytes is
*expected*, since this is a completely different, unrelated cipher; and the
RPCN ticket "Version" magic (`0x21010000`) not appearing anywhere in the
272 bytes is *expected*, since those bytes are ciphertext, not the ticket
in the clear.

### The static key (found, not yet verified)

`FUN_00acb6fc`/`FUN_00acbb90` both key their ARX construction off a
16-byte table reached via a fixed two-level TOC/pointer indirection (no
per-call indexing - always the same address). Resolved this pass
(`research/ghidra/key_dump3.txt`) to address `0x00ed7a50`:

```
78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89
```

Flagged **medium confidence**: the resolution chain (TOC slot ->
`*(u32*)(0x01297378) = 0x00ed7a50` -> 16 bytes there) is mechanically sound
and was double-checked instruction-by-instruction, but the byte pattern
itself (`12345678`/`98765432`/`abcdef...` - all classic "placeholder-looking"
constants) is suspicious, and the bytes immediately following it in memory
are plain ASCII (`72 65 63 76 28 29 20 66 61 69 6c 65 64 20 28 65` =
`"recv() failed (e"`), meaning this 16-byte region sits directly against a
string literal in rodata with no obvious separator - plausible for a real
compile-time constant array butted up against a string table, but not
independently proven to be exactly 16 meaningful bytes rather than, say, a
differently-sized constant. **Not yet used in a working decrypt attempt** -
that is the real confirmation test and hasn't been run.

### The ARX construction itself - fully resolved via raw disassembly (2026-08-14, third pass)

**Update: the ambiguities flagged in the previous version of this section
(session_token's exact mixing mechanism, and whether decrypt is a mirror
image of encrypt) are now fully resolved**, by disassembling
`FUN_00db5ec0`, `FUN_00db7e08` (the decrypt round function - previously not
individually examined), and `FUN_00db5e50` (tag finalize) directly, rather
than trusting their decompiled C (which drops parameters here exactly like
everywhere else in this call chain - `FUN_00db5ec0`'s decompile doesn't
show its 2nd parameter used at all, same as before). Evidence in
`research/ghidra/cipher_final_disasm.txt` (`FUN_00db5ec0`),
`research/ghidra/round_funcs_disasm.txt` (`FUN_00db7f88`/`FUN_00db7cb0`/
`FUN_00db7e08`/`FUN_00db7c80`), `research/ghidra/finalize_disasm.txt`
(`FUN_00db5e50`), and `research/ghidra/acbb90_key_check.txt` (independent
re-confirmation from the decode side).

**The shared round** (`FUN_00db7f88`/`FUN_00db7cb0`/`FUN_00db7e08` all
execute byte-identical instructions up through computing a per-word
keystream value `K`; they differ only in how `K` combines with the data
word and what feeds forward into the next round):

```c
// state = (r16, r17, r18, r19), constants C1=0x5b3aa654, C2=0x75970a4d
r19 ^= C1;
r18 = rotl32(r18 + r16 + r19, 7);
r17 = rotl32(r17 + r19 + r18, 11);
r18 ^= C2;                                    // NOTE: applied AFTER r17 used the pre-xor r18
r16 = rotl32(r16 + r18 + r17, 17);
mux = (r16 & r17) | (r18 & ~r17);             // r17 here is PRE-negation
r17 = ~r17;  r16 = ~r16;                      // negated AFTER mux computed, persist into next round
K = r19 + mux;
```
This is a genuine 32-bit rotate (`rlwinm ...,SH,0,0x1f` - full mask, no
truncation; the decompiled C's `(x & 0x1ffffff) << 7 | ...` forms are just
Ghidra's verbose way of writing `rotl32(x,7)`, not evidence of a partial-
word operation - re-derived and confirmed this pass after initially
second-guessing it). The round constants and odd `and`/`nor`/`or` mux step
don't match any standard named cipher this pass could identify (not
TEA/XTEA/RC5/ChaCha/Salsa in their standard forms) - treat it as bespoke.

**Where `K` and the data word combine (the actual mode-specific step) -
this is the coordinator-flagged decrypt-vs-encrypt asymmetry, now resolved**:

```c
// FUN_00db7f88 (digest, read-only) and FUN_00db7cb0 (encrypt) - IDENTICAL:
out_word = K ^ data_word;
r19_next = out_word;              // feedback = the OUTPUT (ciphertext, for encrypt)
// FUN_00db7cb0 additionally writes out_word back to the buffer; db7f88 doesn't.

// FUN_00db7e08 (decrypt) - DIFFERENT, confirmed via its own disassembly
// (0xdb7edc-0xdb7ee4), NOT assumed symmetric with encrypt:
out_word = K ^ data_word;         // data_word = ciphertext; out_word = plaintext
write out_word (plaintext) to the buffer;
r19_next = data_word;             // feedback = the ORIGINAL CIPHERTEXT WORD, not the recovered plaintext
```
This is classic CFB (cipher feedback): both directions' keystream
generation must be driven by the same ciphertext stream, so decrypt's state
advances using the ciphertext word it just read (before overwriting it),
not the plaintext it just produced. Assuming symmetry here (i.e. having
decrypt's feedback use the recovered plaintext, matching encrypt's literal
instruction shape) would silently produce garbage after the first word -
exactly the failure mode the coordinator flagged, and confirmed as the real
behavior by disassembling `FUN_00db7e08` directly rather than inferring it.

**`FUN_00db5ec0`'s key-mixing mechanism (also fully resolved)**: seeds a
4-word state by byte-reversing the raw 16-byte static key
(`FUN_00db7c80`), runs ONE digest-round (`FUN_00db7f88`-style, 1 word) with
the session_token/client_nonce counter as the input word - the byte
shuffle instructions surrounding this (`rlwinm`s extracting/repositioning
individual bytes of the counter into a scratch buffer) algebraically net
out to simply using the counter's plain 32-bit value directly, confirmed by
a literal byte-level re-simulation matching the simplified version exactly
across 5 random trials - then runs a **finalization round**: takes a
byte-reversed snapshot of the current 4-word state and feeds it back
through an ENCRYPT-mode round (`FUN_00db7cb0`) against itself (4 words,
state evolving across all 4), and the resulting state is the actual
key-schedule output used for the real digest/encrypt/decrypt that follows.

**`FUN_00db5e50`'s tag finalization (also fully resolved)**: not a plain
byte-swap of the state as originally guessed - `X = state[0]^state[1]^
state[2]^state[3]`; `tag = concat(LE32(X^state[i]) for i in 0..3)`. A
final whitening XOR, not just an endian conversion.

**Reimplementation attempt (2026-08-14): algorithm verified correct,
decrypt of the real capture NOT yet successful.** A full Python
reimplementation (`tools/ticket_cipher.py`) was built from the above and
verified three independent ways: (1) self round-trip (encrypt then decrypt
recovers the original plaintext and passes tag verification, for arbitrary
keys/counters); (2) a from-scratch literal byte-level re-simulation of
`FUN_00db5ec0` cross-checked bit-exact against the simplified
implementation across 5 random trials; (3) manual instruction-by-
instruction re-derivation of the round function against raw disassembly
from BOTH `FUN_00acb6fc` (encode) and `FUN_00acbb90` (decode)
independently - confirmed both reach the key via the identical TOC offsets
(`-0x6bf0(r2)` then `-0x8000(r30)`), ruling out a per-function key-address
mismatch. Despite this, running `decrypt_frame()` against the real
272-byte capture with the candidate key from `research/ghidra/
key_dump3.txt` and `session_token=0` (confirmed correct - the stub sent
literal zero bytes) produces a high-entropy, non-ticket-looking
"plaintext" whose self-computed auth_tag does not match the frame's
embedded tag. A brute-force sweep of counters 0-19999 and several key
byte-order variants (full reverse, per-word reverse, word-order reverse)
found no match either. **Given the algorithm is now this thoroughly
verified, the remaining suspect is the candidate key value itself** -
despite the address-resolution mechanism being independently corroborated
(neighboring table entries at the same TOC-resolved base correctly resolve
to real, recognizable debug strings, including `"connect to %s:%i"`,
already known from earlier sessions of this investigation). Resolving this
needs a live RPCS3 debugger read of the actual runtime key bytes and/or a
breakpoint dump of `FUN_00db5ec0`'s register state for a real message,
compared step-by-step against `tools/ticket_cipher.py` - flagged as the
top next step.

### What this means for the sibling services (see companion doc)

`FUN_00acb6fc`/`FUN_00acbb90` are the SAME shared helpers `FUN_00acd5f8`/
`FUN_00acd568` call for every one of the sibling *-server connections
mapped in `docs/protocol/0x11_sibling_servers_family.md` - meaning their
post-hello payloads (previously described in this session's first pass as
"plain ASCII text commands") are actually the PLAINTEXT *input* to this
same encrypted frame, not what actually goes out on the wire. The
service-specific payload-construction logic (sprintf-style command
strings, base64-ish "+"-line parsing, etc.) still stands as a correct
description of the plaintext; it is additionally wrapped in this frame
before transmission. See that doc for details.

## Ruled out this session

- **Message A's "pointer-looking" bytes are session tokens derived from the
  RPCN ticket** - ruled out. Proven uninitialized stack memory, read before
  any ticket-fetch code in this call path executes. See Message A section.
- **Applying the known Blowfish/HMAC-SHA1 `.crypt` keys to the opaque
  bytes** - not applicable; premise (that the bytes are derived/encrypted
  data) doesn't hold once they're shown to be uninitialized memory.
- **RPCN already implements an equivalent to this protocol** - ruled out.
  `backend/rpcn/` was grepped for `ticket-server`, `7320`,
  `heartbeat-server`, `leaderboard-server`, `invite-server` (case-insensitive,
  across all `.rs` files) - zero matches. RPCN's `req_ticket`
  (`src/server/client/cmd_misc.rs:88`) only covers issuing the NP ticket
  itself (the Sony/NP layer), not this Naughty-Dog-specific control-channel
  protocol layered on top of it. This really is new protocol surface that
  needs a from-scratch server implementation - RPCN is not a shortcut here.
- **Matchmaking rides this same "X-server" family** - ruled out as a
  hypothesis for THIS handshake specifically. In-game matchmaking goes
  through Sony's own `sceNpMatching2`/`sceNpSignaling` APIs (confirmed by
  the many `sceNpMatching2*`/`sceNpSignaling*` string refs found this
  session, e.g. `sceNpMatching2CreateJoinRoom`, `sceNpSignalingActivateConnection`),
  which is a separate NP subsystem RPCN would need to implement on its own
  terms - not part of this raw-TCP "X-server" family at all. Not
  investigated further (out of this task's scope per the brief).

## Other service names found (family survey, low-effort pass per coordinator ask)

Found via a single `strings`/grep pass over the EBOOT for `*-server`
patterns near `ticket-server` (`0x00e7a2d0`); VMAs below already converted
from `strings`' raw file offsets (+`0x10000`, see note above):
`single-player-server` (`0x00e62aa8`), `facebook-server` (`0x00e7a0c0`),
`heartbeat-server` (`0x00e7a0e8`), `ticket-server` (`0x00e7a2d0`),
`invite-server` (`0x00e7d0b0`), `leaderboard-server` (`0x00e7d268`). None of
these were individually decompiled
this session - listed here only to map the shape of the broader backend
surface for future prioritization, per the coordinator's ask. Given the
generic `FUN_00acc424` handshake this doc reverse-engineered is a shared
helper (it takes the service name as a plain string argument, not something
`ticket-server`-specific), **the strong hypothesis is that every one of these
services uses the exact same 4-message handshake** (messages A/B at least;
C/D are ticket-specific and probably don't apply to the others) - worth
confirming against one more service's call site before assuming it
generalizes.

## Ruled out / corrected this follow-up pass

- **"`session_token` is a dead, write-only field"** - this session's own
  first-draft conclusion, reached by tracing only `FUN_003557a8` (which
  indeed never reads `conn+0x50` directly) without also checking the leaf
  send helper `FUN_00acb6fc`, which does. **Withdrawn** - see "Encrypted
  frame layer" above. `session_token` is the live key/counter for every
  frame the client sends after the handshake.
- **"Message D is a fixed 16 bytes"** - traced to a `0x10` literal argument
  that, per the same decompiler parameter-drop issue documented above, is
  never actually consumed by the function it's passed to. **Withdrawn** -
  message D's size is self-described by its own frame header, like message
  C.
- **"Message C is `[u16 BE length][raw ticket bytes]`, no further
  wrapping"** - the original message-C schema from this session's first
  pass. **Disproven** by the first real live capture (272 bytes, first two
  bytes read as a nonsensical 13058-byte length under that schema). See
  "Encrypted frame layer" above for the corrected format.
- Applying the known `.crypt` Blowfish key to the 272-byte capture producing
  garbage, and the RPCN ticket version magic not appearing in it - both
  already correctly ruled out as informative by the coordinator's team
  before this pass started, and now positively *explained* (different
  cipher entirely; the captured bytes are ciphertext, not a ticket in the
  clear) rather than just ruled out.

## Confidence summary

| Field | Confidence | Reason |
|---|---|---|
| Message A: opcode, reserved0, reserved1, client_nonce | high | Explicit store instructions read directly from disassembly; nonce further corroborated by PRNG masking matching the one real capture |
| Message A: leaked_stack_garbage | high (on *cause*), unconfirmed (on *content*, by design) | Absence of any write to that address range is directly verifiable in the disassembly; content is genuinely non-deterministic by definition |
| Message A: service_name | high | strcpy call target/source directly visible in disassembly; matches captured "ticket-server" placement exactly (offset 0x18) |
| Message B: ack_magic | high | Direct `cmpwi`/`beq` on the exact byte, unambiguous |
| Message B: unknown1 | medium | Byte range confirmed unread by the validating function; whether truly inert elsewhere is not proven |
| Message B: session_token | high (as key material), unconfirmed (its exact starting-value requirements) | Confirmed via disassembly of the actual consumer (`FUN_00acb6fc`) that it's read/used/incremented as frame-encryption key material, and byte-exact-matched against a real capture's frame math; NOT confirmed whether the client requires anything specific about its *value* beyond internal self-consistency (a server picks it, so this may be moot) |
| Message C: frame_magic, pad_count, plaintext_len, auth_tag(existence)/ciphertext(existence) | high | Byte-exact match (two independent arithmetic checks) against a real 272-byte live capture, plus full disassembly of both the encode and decode paths |
| Message C: auth_tag/ciphertext algorithm (round function, CFB feedback, key schedule, tag finalize) | high (as an algorithm), unconfirmed (that it reproduces the real hardware's exact output) | Every operation independently re-derived from raw disassembly (not decompiled C) of both the encode path (`FUN_00acb6fc`) and decode path (`FUN_00acbb90`), cross-checked 3 independent ways (self round-trip, literal byte-level re-simulation, manual instruction-by-instruction re-derivation); reimplemented in `tools/ticket_cipher.py`; does NOT yet successfully decrypt the one real capture with the candidate key - see "Reimplementation attempt" above |
| Message C: static key bytes | low-medium (unchanged from prior pass) | Resolution chain independently re-confirmed from BOTH `FUN_00acb6fc` and `FUN_00acbb90` (same TOC offsets); neighboring table entries correctly resolve to real debug strings (including a string already known from earlier sessions); despite this, does not currently produce a successful decrypt - remains unconfirmed pending a live debugger check |
| Message D: frame format | high (structural, by analogy) | Confirmed to share the same decoder (`FUN_00acbb90`) and header format as message C via decompile; no independent live capture of an actual message D exists yet (never captured - no server has sent one) |
| Message D: content | unconfirmed | Never observed; no other code path explains it |

## Next steps (prioritized)

1. **Live RPCS3 debugger session to resolve the static key** - the single
   remaining blocker. `tools/ticket_cipher.py` is a verified-correct
   (against raw disassembly, 3 independent cross-checks) implementation of
   the frame cipher; it does not currently decrypt the one real capture
   with the candidate key found via static analysis
   (`research/ghidra/key_dump3.txt`, address `0x00ed7a50`). Set a
   breakpoint at `FUN_00db5ec0`'s entry (`0x00db5ec0`) or at
   `FUN_00acb6fc`'s call into it (`0x00acb788`), dump the actual 16 bytes
   at whatever address is really in `r3` at that point, and/or step through
   the round function comparing register values against
   `tools/ticket_cipher.py`'s `arx_round()` step-by-step for a real
   message. The same live-debugger technique already worked for the
   `.crypt` HMAC key (`research/notes/2026-08-14-repack-rejection-investigation.md`)
   and would be decisive here in a single session, unlike further static
   analysis.
2. **Once the key is confirmed, update `tools/ticket_server_stub.py`** to
   build protocol-legal encrypted frames using `tools/ticket_cipher.py` -
   the current stub's all-zero 16-byte message-D reply is almost certainly
   not valid (wrong magic byte, wrong/missing tag), and a real decrypt of
   message C's ticket bytes would let the stub actually read what RPCN
   issued instead of ignoring it.
3. **Confirm the "shared handshake AND shared frame layer" hypothesis** for
   the sibling services - now separately tracked in
   `docs/protocol/0x11_sibling_servers_family.md` (messages A/B confirmed
   identical via the literal shared function `FUN_00acc424`; the encrypted
   frame layer for their post-hello payloads is confirmed shared by
   construction, since they call the same `FUN_00acd5f8`/`FUN_00acb6fc`, but
   not independently live-tested for any sibling).
4. **Confirm whether the client enforces anything about `session_token`'s
   *value*** beyond what's needed for its own internal frame math to be
   self-consistent (it never compares it against anything external as far
   as this pass found) - low priority, since the server chooses this value
   anyway.
