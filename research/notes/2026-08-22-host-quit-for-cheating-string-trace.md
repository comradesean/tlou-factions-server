# "Host quit for cheating" - the never-before-attempted string trace, done

`docs/OPEN-QUESTIONS.md` has long tracked this as: reported once, rare,
NO static lead ever attempted - "search the EBOOT's string table for a
cheating/kick-for-cheating literal and trace its caller, the same method
used for every other client-side string in this project." That search was
never actually run. This note runs it. All addresses are **01.00** VMAs.

## The string, and its neighbors

`research/strings/strings_ascii.txt` has the literal at file offset
`e6fad0` (VMA `0xe7fad0`, confirmed by reading it back directly:
`eb.cstr(0xe7fad0) == "Host quit for cheating"`). It sits in a small
cluster of similarly-shaped debug/diagnostic strings, found by reading the
32-bit words immediately around its one and only pointer reference
(below):

    0x0126b118 -> "***** Windows Full *****"
    0x0126b11c -> "Cheating"
    0x0126b120 -> "Host quit for cheating"      <- this one
    0x0126b124 -> "Leaving Game %i %i %i"
    0x0126b128 -> "Leaving Game Normally"
    0x0126b12c -> "***** Connection Error *****"

These are NOT a simple flat `const char*[]` array - the words immediately
before and after this run (`0x0126b0e0`-`0x0126b114`, `0x0126b130`-`0x0126b16c`)
are a mix of object pointers, floats, and OTHER unrelated strings
(`NET_SM_UPDATE`, `NET_SM_LEAVE_GAME`, `NET_SM_START_MATCHMAKING`), so this
looks like inline literals scattered through one function's `.data`-pooled
constants, not a lookup table indexed by an enum.

## Locating the reference

A raw 4-byte big-endian scan of the whole EBOOT for the value `0xe7fad0`
(the string's own address) finds **exactly one hit**: file offset
`0x125b120` (VMA `0x126b120`) - i.e. a single pointer slot, not a jump
table with multiple entries pointing at it.

`scan_anchor.py`'s r2->anchor->displacement resolver finds exactly one
code site reaching that slot:

    0x003f1580   lwz r3, -32344(r30)   -> slot 0x0126b120 ("Host quit for cheating")

The same scan run against the neighboring slots shows this is one function
loading each of the five neighbor strings at different points along its own
body (`0x3f137c`, `0x3f13c8`, `0x3f1580`, `0x3f16a8`, `0x3f1758`) -
`fnstart.py` confirms all five sit inside the same function starting at
`0x003f10b8`.

## The gate condition reaching this specific line

Reading `0x3f14a0`-`0x3f1594` in order (raw objdump,
`--start-address=0x3f14a0 --stop-address=0x3f1598`):

```
3f14c0  clrlwi r0,r31,24
3f14c4  ...
3f14c8  cmpwi cr7,r0,0
3f14d0  beq cr7,0x3f1598          ; r31 (a byte-sized PARAMETER to this
                                  ; function) must be nonzero, or skip
                                  ; the ENTIRE diagnostic block
3f14d4  lwz r31,-32616(r30)       ; a different global object
3f14d8  lbz r0,11692(r31)
3f14dc  cmpwi cr7,r0,0
3f14e0  bne cr7,0x3f1518          ; if this flag byte is set, skip ahead
3f14e4  bl 0x3abe80               ; else call an unnamed predicate
3f14ec  clrlwi r3,r3,24
3f14f0  cmpwi cr7,r3,0
3f14f4  beq cr7,0x3f1598          ; predicate false -> skip everything
3f14f8  lbz r0,11692(r31)         ; re-read the same flag byte
3f14fc  cmpwi cr7,r0,0
3f1500  bne cr7,0x3f1518          ; nonzero -> skip the next block
3f1504  lwz r3,-32620(r30)
3f1508  bl 0x39935c               ; another unnamed helper
3f1510  cmpdi cr7,r3,3
3f1514  ble cr7,0x3f1598          ; result <= 3 -> skip everything

3f1518  lwz r3,-32636(r30)
3f151c  bl 0xad0eec                ; the SAME party predicate this project
                                  ; already names elsewhere (see
                                  ; research/notes on FUN_00ad0eec as a
                                  ; party-object test, e.g. the
                                  ; stat_line/task-%x investigation)
3f1524  clrlwi r3,r3,24
3f1528  cmpwi cr7,r3,0
3f152c  beq cr7,0x3f18fc          ; NOT a party -> skip this whole path
                                  ; entirely (jumps far past the message)
3f1530  lwz r9,-32484(r30)
3f1534  lbz r0,172(r9)
3f1538  cmpwi cr7,r0,0
3f153c  bne cr7,0x3f18fc          ; a flag byte at some_global+172 must
                                  ; be ZERO, or skip

... (builds and prints a separate formatted diagnostic first, via the
     same shared formatter this project already knows,
     _opd_FUN_00e46670-family at 0xe46460) ...

3f1580  lwz r3,-32344(r30)        ; "Host quit for cheating"
3f1584  bl 0xe3fb2c               ; print/log it
3f158c  lwz r9,-32628(r30)
3f1590  li r0,1
3f1594  stb r0,0(r9)              ; latch a flag - this message fires once
```

**Reading, stated at the confidence it deserves**: this function takes a
byte-sized "reason" parameter (`r31`) and only does ANY of this messaging
if that parameter is nonzero. Reaching the specific "Host quit for
cheating" line additionally requires an ALL of: an unnamed flag byte at
`some_object+11692` combined with an unnamed predicate (`0x3abe80`), a
count from an unnamed helper (`0x39935c`) being `> 3`, the SAME party
predicate this project already uses elsewhere (`0xad0eec`) being true, and
a second unnamed flag byte at `some_object+172` being zero. It then latches
a "already fired" flag after printing, consistent with a match-teardown
reason this fires once per session.

## What this closes, and what's still open

**Closed**: the string has exactly one code reference (not a table, not
dead code), the containing function and its entry point (`0x003f10b8`) are
now known, and the ordered condition chain reaching this specific line is
fully instruction-traced - this project's own stated partial-unblock bar
("search the string table, trace its caller") is met for the first time.

**Still open, and this matches the existing doc's own framing exactly**:
none of the individual predicates (`0x3abe80`, `0x39935c`, the two flag
bytes at `+11692`/`+172`, or the `r31` reason parameter's own caller/value
space) are named yet - resolving those would need either tracing each
helper function individually (a further static pass, not attempted this
session) or a live reproduction of the actual event (still the only way to
confirm WHICH real in-game action satisfies this whole chain, since a
five-way compound AND condition is not something to guess the meaning of
from addresses alone).
