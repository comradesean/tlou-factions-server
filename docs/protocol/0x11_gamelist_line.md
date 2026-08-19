# `gamelist-server` line protocol (opcode `0x11` family)

Companion doc for:
- `protos/0x11_gamelist_line.ksy`

Part of the `*-server` sibling family surveyed in
`docs/protocol/0x11_sibling_servers_family.md`.

**status: confirmed** — request grammar confirmed from the sender's own
`strcat` sequence and matched byte-for-byte against a live capture; reply
handling confirmed as *unparsed* from the same function.

**confidence: high** — the request is not inferred from the capture, it is read
off the instructions that build it, and the capture then matches the resulting
length exactly (50 bytes). The reply finding is a negative established by
reading every instruction between the `recv` call and the `close` that follows
it: there are two, and neither touches the result.

**build scope: 01.11 only.** Neither `gamelist-server` nor `game-add ` appears
anywhere in the 01.00 EBOOT. Every address here is an 01.11 VMA
(VMA = file offset + `0x10000`) in the ELF with sha256
`241e2b1bca43c97431a1aa7acd1b29a20d292bec7263ab8ca318b8a03538e592`.

## What this is

The client registering its live game with the backend: "this match-session id
exists and these accounts are in it." It is a write-only announcement, not a
discovery path — `game-add ` is the **only** `game-` verb in the whole binary.
There is no `game-remove` and no `game-list`, so nothing the backend stores can
ever be read back by the client. Game discovery remains `0x135`/`0x136` on the
session manager; this channel does not compete with it.

## How the sender was located

The service and verb strings are at fixed addresses, but PPC64 reaches them
through the `r2` → per-compilation-unit anchor → displacement idiom, so they do
not appear as address literals in a linear disassembly. Resolving that chain:

| string | VMA | pointer slot |
|---|---|---|
| `games/%s` | `0xeb2670` | `0x129cd70` |
| `game-add ` | `0xeb2680` | `0x129cd7c` |
| `gamelist-server` | `0xeb2690` | `0x129cd8c` |
| `" "` (separator) | `0xeac140` | `0x129cd80` |
| `"\n"` (terminator) | `0xf3efa0` | `0x129cd84` |
| `""` (buffer seed) | `0xeb2410` | `0x129cd78` |

`r2` for this build is `0x1338de0`, read from the entry-point function
descriptor at `0x12d5c08` (`{entry 0x10230, toc 0x1338de0}`). Scanning for
`lwz rN, -D(r2)` anchor loads followed by displacement accesses onto those slots
puts every one of them inside a single function beginning at **`0x004047f4`**
(`stdu r1,-816(r1)`) and ending at its `blr` at `0x00404a54`. Three independent
slots landing in the same function body is the address check: this is the
gamelist sender, not a neighbouring routine.

The corresponding chain for `report-server` resolves to `0x0036e1fc`, which is
exactly the address the already-documented report-server work names — an
independent confirmation that the `r2` value and the scan are correct before
anything here is concluded from them.

## Request

Assembled by literal `strcat`, which is where the field boundaries come from:

```
0x4048c0-0x4048e0   buf[0] = *""            (slot 0x129cd78 -> ""), so the
                    memset(buf+1, 0, 255)    buffer simply starts empty
0x4048ec            strcat(buf, "game-add ")           slot 0x129cd7c
0x4048fc / 0x40492c strcat(buf, <session-id>)          r25 = arg + 16222
0x404908-0x40494c   for i in 0 .. *(arg+16152) - 1:
0x404908                strcat(buf, " ")               slot 0x129cd80
0x40492c                strcat(buf, <player>)          arg + 17688 + i*212
0x404950            strcat(buf, "\n")                  slot 0x129cd84
```

Grammar:

```
game-add <session-id>[ <player>]...\n
```

Live capture (2026-08-19, one frame, decrypted plaintext):

```
game-add mgnomad2.1787116698 mgnomad2 comradesean\n
```

9 + 19 + 9 + 12 + 1 = **50 bytes**, exactly the observed length. There is no
trailing NUL inside the frame; the send length comes from the `strlen` at
`0x4049f0`.

`<session-id>` is the `<npid>.<unix-timestamp>` match-session id that
`0x143 SetRoomDataBlock` also carries (see
`protos/0x143_set_room_data_block.ksy`) — here `mgnomad2` hosting at unix
`1787116698`. The remaining tokens are the roster, host first.

## Connect

```
0x4049b0   r6 = "gamelist-server"                       slot 0x129cd8c
           r4/r5 = ip/port from *(0x15900b8) + 0x60
0x4049d4   bl 0xaf9bb4
0x4049dc   cmpwi cr7,r3,0 / bne -> 0x404a20             failure -> close only
```

`0xaf9bb4` is the family's shared hello function, verified by its own contents
rather than by name: `li r0,17` (opcode `0x11`) at `0xaf9c4c`, `li r5,88` for
the 88-byte hello at `0xaf9c94`, `li r5,8` for the 8-byte reply at `0xaf9d2c`,
and `cmpwi cr7,r0,34` — the `0x22` ack magic — at `0xaf9d60`. It is the same
function `report-server` calls at `0x36e220`, i.e. the 01.11 twin of 01.00's
`FUN_00acc424`. That is what makes `gamelist-server` a genuine member of this
family rather than a lookalike, and it means messages A and B are the family's
byte-identical pair with only the `service_name` field differing.

Post-hello the payload goes through the same encrypt-then-MAC `0x33` frame as
every other sibling (`server/lib/ticket_cipher.py`); the grammar above is the
**plaintext**.

## Response — parsed at all? No.

This was the question that had to be settled before writing a handler, because
it decides whether the server may close first and how much it must send. The
answer is the **heartbeat single-bounded-recv shape**, in its weakest form:

```
0x4049f0   bl 0xe72a00     strlen(buf)
0x404a04   bl 0xafad88     send(conn, buf, len)
0x404a14   li r5,256
0x404a18   bl 0xafacf8     ONE bounded 256-byte recv, into the SAME buffer
0x404a1c   nop             (the call's linkage nop)
0x404a20   mr r3,r31       r3 := the connection pointer - the recv result is
                           overwritten here, unread
0x404a24   bl 0xaf9260     close
0x404a54   blr
```

There are exactly two instructions between the `recv` and the `close`, and
neither inspects `r3`. No length field is read, no accumulator loop runs, there
is no `'+'` test and no tokeniser call anywhere in `0x4047f4`-`0x404a54`.

Contrast the two shapes it could have been:

| service | after the recv |
|---|---|
| `leaderboard-server` | loops receiving into a 2048-byte buffer, splits on `\n`, parses `+` rows until satisfied |
| `report-server` | tests the byte count (`cmpwi cr7,r3,0` @ `0x36e298`), then `'+'`, then `strtok_r`/`strtol`/`strcmp` |
| `gamelist-server` | nothing — closes |

Consequences for the server:

- The whole reply must arrive in **one frame** (the client closes right after
  the single `recv`).
- The reply's **content is free** — any bytes satisfy this client.
- The server must still **send something**, or the client sits in `0xafacf8`'s
  own timeout instead of returning promptly.
- The server must still **never close first**. That rule is not derived from
  this function; it is the family-wide behaviour established live on
  `leaderboard-server` (a server-initiated EOF produces
  `recv() failed (errno=0)` → "Error 9 / You have been disconnected from the
  game servers") and it costs nothing to honour here.

## Proven vs. assumed

**Proven from the binary:** the verb; the session-id-then-roster token order;
the `" "` separators and the trailing `"\n"`; the absence of any other `game-`
verb; the single bounded 256-byte recv; and the fact that the reply is never
inspected.

**Proven from a live capture:** the 50-byte plaintext above — a two-player
roster with the host first.

**Assumed:** that a roster longer than two behaves identically. The loop at
`0x404908` is generic in the count at `*(arg+16152)`, so this is a strong
inference, but only a 2-player sample has been captured. Also assumed: that the
212-byte stride between roster entries is a per-player record — the stride is
proven, the struct at that stride is not mapped.

**A choice, not a requirement:** the reply body this server sends.

## Server behaviour

`server/ticket_server.py` `handle_gamelist` / `build_gamelist_response`
(2026-08-19). `gamelist-server` now has an entry in `LINE_SERVICE_HANDLERS` and
no longer falls through to the ticket path, which used to answer it with a
`ticket_submit_response` frame — the same request/response mismatch class that
produced the leaderboard "Error 9" boot and the Facebook retry spin before each
of those got a real handler.

The handler decodes the line, records the session id and roster in an in-memory
registry (`GAMES`, keyed by session id, with `first_seen` / `last_seen` /
`adds` / `roster`) — registration being the message's actual purpose — and
replies `+0\n` plus the family's NUL sentinel, then holds the socket until the
client closes. The registry is in-memory only, deliberately: the client can
never read it back (no `game-list` verb exists), so nothing depends on it
surviving a restart. It exists to make the log readable and to give future work
a real record to correlate against `0x143`'s data block.

The `+0\n` body is copied from `handle_heartbeat`, which answers an equally
unparsed reader, purely for family consistency. An unknown `game-` verb is
acked the same way and logged loudly, because such a line would be new evidence
— no verb other than `game-add ` exists in this build.

## Adjacent but separate channel

Earlier in the same function (`0x404820`-`0x4048b8`) the client builds a buffer
via `0xa49efc` / `0xa49f14` / `0x403ca4`, formats the path `games/%s`
(`0xeb2670`) with the same session id into a stack buffer, and hands it to
`0xaf39c0` in a retry loop of up to 9 attempts (`cmpwi cr6,r31,8` at
`0x4048ac`). `0xaf39c0` stores a method enum of `4` into its request object
(`li r0,4` at `0xaf39f8`; its sibling entry point `0xaf3a30` stores `1`), and
its host object comes from a different slot (`0x129cd74` → `0x13ba678`). So
that is an HTTP-style upload to a different backend, not this TCP line service.
It is recorded here only so the two are not confused; it is out of scope for
this spec and is not handled by this server. What it uploads, and to which
host, is not established.
