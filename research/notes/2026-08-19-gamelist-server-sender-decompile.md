# `gamelist-server`: locating the sender and settling the reply shape (01.11)

Raw evidence behind `protos/0x11_gamelist_line.ksy`,
`docs/protocol/0x11_gamelist_line.md` and `server/ticket_server.py`'s
`handle_gamelist`. Everything here is 01.11 only.

## Binary

```
/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/dev_hdd0/game/BCUS98174/USRDIR/EBOOT.elf
sha256 241e2b1bca43c97431a1aa7acd1b29a20d292bec7263ab8ca318b8a03538e592
size   20333528
```

ELF64, big-endian, PowerPC64, `OS/ABI <unknown: 66>` (= `ELFOSABI_CELL_LV2`),
entry `0x12d5c08`. VMA = file offset + `0x10000` for both LOAD segments, as in
`research/tools/eboot_analysis/README.md`.

## `r2` for this build

`research/tools/eboot_analysis/scan_anchor.py` hardcodes 01.00's TOC pointer
(`0x1305870`), so it cannot be pointed at 01.11 unchanged. The 01.11 value comes
from the entry-point function descriptor:

```
0x12d5c08: 00 01 02 30  01 33 8d e0   -> {entry 0x00010230, toc 0x01338de0}
```

so `r2 = 0x01338de0`. **Sanity check before anything was concluded from it:**
re-running the anchor scan with that `r2` against the `report-server` string
slot `0x129a3c8` resolves to `0x0036e1fc` — exactly the address the existing
report-server work names as the point where the service string is loaded. An
independently-derived constant landing on an independently-recorded address is
the check that the scan is not fabricating hits.

## String and slot resolution

```
0xeb2670 'games/%s'          slot 0x129cd70
0xeb2680 'game-add '         slot 0x129cd7c
0xeb2690 'gamelist-server'   slot 0x129cd8c
0xeac140 ' '                 slot 0x129cd80
0xf3efa0 '\n'                slot 0x129cd84
0xeb2410 ''                  slot 0x129cd78
                             slot 0x129cd74 -> 0x13ba678  (bss, HTTP host obj)
                             slot 0x129cd88 -> 0x15900b8  (bss, net singleton)
```

`game-add` and `gamelist-server` each occur exactly once in the whole file, and
each has exactly one pointer slot. Anchor scan on those slots:

```
0x0040486c (fn>=0x004047f4)  lwz r4, -32480(r30)  -> 0x0129cd70   "games/%s"
0x004048ec (fn>=0x004047f4)  lwz r4, -32468(r30)  -> 0x0129cd7c   "game-add "
0x004049b0 (fn>=0x004047f4)  lwz r6, -32452(r30)  -> 0x0129cd8c   "gamelist-server"
```

All three land in one function: `0x004047f4` (`stdu r1,-816(r1)`) through its
`blr` at `0x00404a54`. That is the address check — three separate slots inside
one body, not a single guessed address.

## The request, read off the strcat sequence

```
0x4048c0  lwz r9, slot 0x129cd78 ; lbz r0,0(r9) ; stb r0,496(r1)   buf[0] = '\0'
0x4048d4  memset(buf+1, 0, 255)                     (bl 0xe7b740)
0x4048ec  strcat(buf, "game-add ")                  (bl 0xe775ac)
0x4048fc  r4 = r25 = arg+16222  -> strcat(buf, <session-id>)  @0x40492c
0x404908  loop, trip count = *(arg+16152), i in r31/r27:
0x404908      strcat(buf, " ")                      slot 0x129cd80
0x40491c      r4 = i*212 + arg + 17688
0x40492c      strcat(buf, <player>)
0x404950  strcat(buf, "\n")                         slot 0x129cd84
```

Grammar: `game-add <session-id>[ <player>]...\n`.

Cross-check against the live capture
`game-add mgnomad2.1787116698 mgnomad2 comradesean\n`:
9 + 19 + 9 + 12 + 1 = 50 bytes, which is exactly the decrypted length observed.
No trailing NUL — the send length is `strlen` at `0x4049f0`.

## Connect: this is a real 0x11 sibling

```
0x4049b0  r6 = "gamelist-server"
0x4049bc  r9 = *(0x15900b8) ; lwz r9,96(r9) ; lwz r9,4(r9)
0x4049cc  r4 = ip = 0(r9) ; r5 = port = 4(r9)
0x4049d4  bl 0xaf9bb4
```

`0xaf9bb4` verified by contents, not by name:

```
0xaf9c4c  li r0,17         opcode 0x11
0xaf9c94  li r5,88         the 88-byte hello
0xaf9d2c  li r5,8          the 8-byte reply
0xaf9d60  cmpwi cr7,r0,34  the 0x22 ack magic
```

`report-server` calls the same function at `0x36e220`, so this is the 01.11
twin of 01.00's `FUN_00acc424` and messages A/B are the family's, unchanged
apart from the service-name field.

## The reply is never parsed

```
0x4049f0  bl 0xe72a00   strlen(buf)
0x404a04  bl 0xafad88   send
0x404a14  li r5,256
0x404a18  bl 0xafacf8   one bounded 256-byte recv, into the same buffer
0x404a1c  nop
0x404a20  mr r3,r31     r3 := connection pointer; the recv result is discarded
0x404a24  bl 0xaf9260   close
0x404a54  blr
```

Two instructions between recv and close, neither reading `r3`. No length field,
no accumulator loop, no `'+'` compare, no `strtok_r`. This is the heartbeat
single-bounded-recv shape, weaker even than report-server's, which does test the
byte count at `0x36e298` before parsing. Conclusion: the reply body is free, but
it must be one frame, it must exist, and the server must not close first.

## Adjacent HTTP-style upload (separate channel, unresolved)

`0x404820`-`0x4048b8`: buffer built via `0xa49efc` / `0xa49f14` / `0x403ca4`,
path formatted as `games/%s` with the same session id, handed to `0xaf39c0` with
a retry loop of up to 9 attempts (`cmpwi cr6,r31,8` @ `0x4048ac`). `0xaf39c0`
stores a method enum of 4 (`li r0,4` @ `0xaf39f8`; its sibling entry point
`0xaf3a30` stores 1) and takes its host from slot `0x129cd74` -> `0x13ba678`
(bss). Different backend, different transport; not handled by this server and
not characterised further here.

## Reproduction

The 01.11 anchor scan is `research/tools/eboot_analysis/scan_anchor.py` with
`R2 = 0x01338de0`, `TEXT_VA/TEXT_SZ = 0x00010000 / 0x121ef68` and `eb.py`'s
`EB`/`SEGS` pointed at the 01.11 ELF. Disassembly:

```sh
powerpc64-linux-gnu-objdump -D -b binary -m powerpc:common64 -EB \
  --adjust-vma=0x10000 --start-address=0x4047f4 --stop-address=0x404a58 "$EBOOT_0111"
```
