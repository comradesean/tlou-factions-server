# Rejoin-party bug: the server marks party hosts as hosts, and that hides "Join Party"

**Status:** the friends-list predicate is fully decompiled and one server-caused
blocker in it is proven. A corrected fix is implemented in
`server/session_manager.py`. **Not yet live-tested.** An earlier hypothesis in
this same investigation was implemented and falsified by a live run; it is
recorded in section 5 so it is not re-tried.

**Symptom (reported 2026-08-19):** a player joins another player's party, then
leaves. Afterwards the "Join" affordance for that party's owner is absent from
the leaver's friends list - not failing when clicked, simply not offered.

Build: 01.00, `BCUS98174`, EBOOT `PPU-9df60dc1aa5005a0c80e9066e4951dc0471553e6`.
All addresses are 01.00 VMAs (`file offset = VMA - 0x10000`).

---

## 1. The menu item and where it is built

The label is StringId **`0xb1600ce3` = "Join Party"** (`text1.psarc`,
`2.common`; the neighbouring items resolve to "Invite To Party" `0x4a555973`
and "View Profile" `0x4040b706`, which is what identifies the block as the
friends-list context menu).

It is built at `0x0034bd60`-`0x0034bf3c`. Menu entries are 8-byte pairs
`{u32 label_string_id, u32 action_id}` written into the array at `r1+124`, with
the count at `r1+120` capped at 7, and the finished array handed to
`0x00337d88`. "Join Party" is written at `0x0034be5c`-`0x0034be88`.

## 2. The exact predicate

`r31` = the selected friend (a 760-byte `NetFriend`). Guards in order:

```
34bdb0  bl 0x00396b90        ; friend is already a member of MY party?
34bdc0  bne -> 34bed8        ;   yes -> neither "Join Party" nor "Invite"
34bdc4  lwz r3,-32616(r30)   ; 0x013835c0
34bdc8  bl 0x003abe80        ; -> *(0x013835c0+0x7c) != 0   (local busy flag)
34bdd8  bne -> 34bed8        ;   set -> neither item
34bde0  bl 0x00396a64        ; NetFriend::GetPresenceData(friend)
34bdec  beq -> 34be8c        ;   NULL -> no "Join Party"
34bdf0  lwz r0,608(r31)      ; friend->m_pres trailing state word
34bdf8  bne (!= 2) -> 34be8c ;   not 2 -> no "Join Party"
34be00  bl 0x00348e14        ; -> (no data) || (blob[7] != 0)
34be10  bne -> 34be8c        ;   true -> no "Join Party"
34be18  bl 0x00ad1024        ; member count of MY party (0x01387f58)
34be24  ble 3 -> 34be40      ; my party has room
34be34  lbz r0,4(r3)         ;   else: friend blob[4]
34be3c  beq 2 -> 34be8c      ;   my party full + friend in a session -> no
34be4c  lbz r0,4(r3)         ; friend blob[4]
34be54  bne 1 -> 34bf2c      ;   != 1 -> emit "Join Party" (via 0x34bf38)
34be58  b -> 34be8c          ;   == 1 -> no "Join Party"
```

Supporting functions:

* `0x00396b90(friend)` = `0x00ad1e64(0x01387f58, &friend->npid) != 0`, i.e.
  "is this friend already in my party object".
* `0x003abe80(obj)` = `*(obj+0x7c) != 0`. Written by `0x003abe9c` from
  `0x0035bd1c`, `0x0035bee4`, `0x0035d2c4`, `0x00395538` - all game-side party
  state, nothing this server touches.
* `0x00396a64` = `NetFriend::GetPresenceData`, and it is strict:

  ```
  396a74  lwz  r0,604(r3)     ; friend->m_pres.dataSize   (NetFriend+0x25c)
  396a78  addi r31,r3,476     ; friend->m_pres.data       (NetFriend+0x1dc)
  396a80  cmpwi r0,96         ; must be EXACTLY 96 bytes
  396a9c  r3 = 0x013835c0
  396aa0  r29 = *(data+0)     ; blob[0x00]
  396aa4  bl 0x003ac0fc       ; the same value the publisher puts in blob[0]
  396aac  cmpw r29,r3         ; must match the reader's own
  396ab0/b4  -> &data, else NULL
  ```
* `0x00348e14(friend)` = `1` when `GetPresenceData` is NULL, else
  `blob[7] != 0`.

## 3. blob[7] is `party_obj+0x19f4`, and this server sets it to 1

The presence publisher is `0x00397d74` (throttle at `this+0xb0`: +3000 ms on
success, +9000 ms on failure; republished only when the 96-byte blob changes -
`memcmp` @`0x00398074` against the cached copy at `this+0x50`, then
`sceNpBasicSetPresenceDetails(details, 3)` @`0x0039815c`, with the blob copied
to `details+256` and `96` stored at `details+384`).

```
397dfc  lwz r9,-32756(r30)   ; r9 = 0x01387f58, the PARTY room object
397e08  lbz r0,6644(r9)      ; *(party_obj+0x19f4)
397e0c  ld  r9,16(r9)        ; *(party_obj+0x10)
397e10  stb r0,127(r1)       ; -> blob offset 7
397e14  std r9,160(r1)       ; -> blob offset 0x28
397e18  bl  0x00ad1024       ; party member count -> blob offset 5
```

Anchor resolution for that slot (done rather than assumed):
`r30 = *(r2-31096) = 0x012714e8`, `*(0x012694f4) = 0x01387f58`. The
friends-list CU reaches the same object through a different anchor -
`r30 = *(r2-31188) = 0x0126fe20`, `*(0x01267eb4) = 0x01387f58` - with
`*(0x01267eb8) = 0x013835c0` and `*(0x01267eb0) = 0x01383bd8` alongside it, so
the identification is unambiguous.

`room_obj+0x19f4` is the host flag. A full sweep for displacement 6644 gives
every writer:

| address | site | value |
|---|---|---|
| `0x00ad1f58` | room-object reset | 0 |
| `0x00ad5c98` | the `0x12f` RoomCreate **sender** (`li r27,0` @`0x00ad5c6c`) | 0 |
| `0x00ad6af0` | SetHostFlag promote, fn `0x00ad6a34` (vtable slot `0x012e9c80`); also emits the `0x13e` request | 1 |
| `0x00ad6c04` | SetHostFlag demote | 0 |
| `0x00ad82cc` | the **`0x13f` receive arm** (`stb r0,6644(r9)`, `r0 = wire[4] & 1`) | wire |

So a party host sits at **0** unless something explicitly promotes it, and the
only inbound way to change that is `0x13f`.

`server/session_manager.py` sent `build_owner_changed(room_id, is_owner=1)`
immediately after Member on **every** RoomCreate reply, party included. The
party host therefore advertised `blob[7] = 1`, and guard `0x00348e14` removed
"Join Party" from that host's row in every friend's list - independently of
whether anyone had joined or left. That is a server-caused, permanent blocker,
and it explains why a fix aimed at the leaver's own state changed nothing.

## 4. Fix applied

`build_owner_changed`'s parameter is renamed `joined_flag` (its docstring
previously described the byte correctly but did not know it was published), and
the RoomCreate reply now sends:

* **party object -> 0**, matching what the client's own RoomCreate sender
  wrote and what a friend's client needs to see;
* **game object -> 1**, unchanged. The 2026-08-16 audit added it to make a solo
  host "become the host", the find-match path is live-working with it, and the
  game object's copy of the byte is never published - the presence publisher
  reads the party object only.

`reseed_departed_party` (section 5) also sends 0 now.

Two sites are knowingly left inverted and commented in place:

* the `0x130` join reply already sends 0, which is the value the guard wants;
* the **Promote** path (`0x13c`) hands the new leader `0x19f4 = 1`, so a
  promoted party leader should re-acquire this bug. Not changed here because
  the Promote round trip is live-verified and the reported repro contains no
  promote - fix it in the same live run that confirms this one.

## 5. The falsified hypothesis (do not re-try as-is)

The first pass concluded the bug was the **leaver's** zeroed party room id, and
the reseed built for it was live-tested and did not fix the symptom. The
underlying decompile is still correct and is kept, but it is not the cause of
the missing menu row:

* `_opd_FUN_00ad65e8`, the `0x133` sender, ends with `stb 1,184(r31)`
  (`*(room+0xb8) = 1`, still VALID) at `0x00ad6684`, then `std 0,16(r31)`
  (`*(room+0x10) = 0`) at `0x00ad66e0`, then wipes all 12 member slots via
  `0x00ad32c4`. The earlier `.ksy` wording called `+0xb8` an "inactive" flag,
  which had the polarity backwards.
* `room_obj+0x10` has exactly one writer, the `0x131` Member receive arm
  (`ld r9,16(r28)` / `std r9,16(r29)` @`0x00ad7804`-`0x00ad780c`), which takes
  the room object from the message's own wire offset 8 and is not gated on
  `+0xb8`. Only the server can restore it.
* The party **invite** state machine at `0x0034ee0` state 6 does gate on it
  (`ld r0,16(r9)` @`0x00354f50`, `beq` @`0x00354f58`, 3000 ms then abort)
  before calling the payload builder `0x00354c2c`, which packs
  `*(party+0x10)` and labels the message with `0x82c61354` "Party Invite" /
  `0xe2069b80` "Join my 'The Last of Us™' Multiplayer Party!".

So the reseed fixes a real hole on the **invite** path, not the friends-list
row. It is kept for that reason and because a leaver otherwise publishes room
id 0 at blob offset `0x28` forever. Note this also means the first successful
join in the reported repro most likely came through an invite, not through the
friends-list row - which may never have been drawn at all.

An earlier draft of this note claimed `0x19f4` was a "joined vs created" byte,
on the strength of `0x00ad6af0` writing 1. That was wrong: `0x00ad6af0` is
inside SetHostFlag (`0x00ad6a34`), not the RoomJoin sender. Corrected above.

## 6. What is still unknown

* **Guard 7** requires the friend's `blob[4] != 1`. blob[4] is `2` when
  `*(0x0137d700+18908) != 0`, else `1` when `*(0x013835c0+0x7c) != 0`, else 0
  (`0x00397fcc`-`0x00398054`). If a host sitting in a party lobby publishes
  `blob[4] == 1`, "Join Party" stays hidden even with `blob[7]` fixed. Nothing
  this server sends writes either global, so this would not be server-fixable
  in the same way. **This is the most likely reason for the fix to come up
  short again, and it is the first thing to check if it does.**
* **Guard 4** requires `friend->m_pres` trailing state word `== 2`. That word
  comes from `sceNpBasicGetFriendPresenceByNpId` (`NetFriend::UpdatePresence`,
  `0x00396be0`, `m_pres` at NetFriend+220, 392 bytes), i.e. from NP, not from
  this server.
* Whether the friends-list row was ever drawn on this stub at all. If it was
  not, this is a never-worked path rather than a regression, and the "after
  leaving" framing in the report is incidental.

## 7. How to test it decisively

Because two guards can independently hide the row, read the values rather than
just looking at the menu:

1. Host creates a party. In the RPCS3 debugger on the HOST, read
   `*(0x01387f58 + 0x19f4)` - it must now be **0** (it was 1 before this fix).
2. On the same console read `*(0x0137d700 + 18908)` and
   `*(0x013835c0 + 0x7c)`; they decide blob[4] and therefore guard 7.
3. On the OTHER console, open the friends list and check the row.
4. Only then repeat the join/leave/rejoin cycle.

Server-side, the log line to look for on a party create is the RoomCreate reply
emit; the reseed prints `[reseed] ... left a party` and its absence during a
leave would mean `is_party_ptr` never matched.
