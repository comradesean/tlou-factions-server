# Host migration: what exists, and at which layer

Question: when a room's host leaves or crashes, can the session be handed to
another player instead of ending?

Answer, from the EBOOT string layout: **the engine library supports host
migration; this game's matchmaking layer does not appear to use it.** Evidence
is string-adjacency plus a state-machine absence - strong, but not yet confirmed
by xrefs.

## The two layers

`ndlib/net/net-session-manager-nd.cpp` (0xec8048) - ND's reusable engine
library, the unit that speaks the port-7314 protocol:

    ec8080  Unhide
    ec8088  No Host Migrate
    ec8098  Host Migrate
    ec80a8  NetMatchmakingClientHello %i
    ec80c8  NetMatchmakingServerHello %i
    ...     (the whole NetMatchmaking opcode-name table follows)

`game/net/net-matchmaking.cpp` (0xe6d380) - THIS GAME's matchmaking state
machine, the layer that actually runs a match:

    e6d3e8  *********** Joining Room %s %i players
    e6d410  matchmaking room host left
    e6d430  matchmaking room destroyed
    e6d450  Kicked Out of Loading Screen because of timing out (or XMB invite)
    e6d498  NET_SM_CLIENT_LATE_JOIN_SCREEN_3
    e6d4c0  NET_SM_LOAD_LEVEL

`DebugMigrationStatus` (0xecef98) sits in the Debug* menu-item name table, so
migration also has a debug readout.

## Why the conclusion follows

1. `Host Migrate` / `No Host Migrate` is a PAIRED label - the shape of a toggle
   or a status readout, i.e. migration is conditional on some flag - and it
   lives in ndlib, not in the game's matchmaking unit.
2. The game's `NET_SM_*` state list is extensive (vote screen, game list pick,
   late join screens, load level, client start, game list wait, server lobby,
   round results, results, reset...) and contains **no migration state at all**.
   A feature the game layer drove would be expected to have one.
3. The game layer's entire host-loss vocabulary is `matchmaking room host left`
   and `matchmaking room destroyed`, both of which lead to teardown. The party
   layer is explicit about the same choice: `lost connection to party host %s,
   leaving party` - LEAVING, not migrating.

Live behaviour matches: when a find-match host crashed mid-game (2026-08-18),
both remaining players got "Lost connection to host" and the session ended.

## What this means for the server

No message we send can create a feature the game layer never implemented. The
stub cannot promote a survivor into a running match by sending `0x13d`.

What the stub CAN do, and now does, is make the ending clean rather than silent:
on owner departure every survivor gets `0x134 RoomLeave(owner)` + `0x139
RoomClosed` (commit 23db204), instead of being left holding a room the server
had forgotten. Ownership transfer via `0x13c`/`0x13d` IS live-verified, but only
in a PARTY, where the client requests it - see protos/0x13c_promote.ksy.

## Cheap verification available

`matchmaking room host left` and `matchmaking room destroyed` are adjacent in
the game layer and are plausibly the client's reactions to our owner-departure
`0x134` and our `0x139 RoomClosed`. Next time a host leaves a room with a
survivor present, grep the SURVIVOR's TTY (`sys_tty_write` in RPCS3.log) for
`matchmaking room destroyed`. If it prints, our `0x139` is being consumed
exactly as the game expects - direct confirmation of the teardown fix.

## To settle migration definitively

Xref `0xec8088` / `0xec8098` and `DebugMigrationStatus`, and check whether
anything in `net-matchmaking.cpp` calls into the ndlib migration path. That
distinguishes "the game never calls it" from "the game calls it but it is gated
off by a flag" - and if it is a flag, the next question is whether that flag is
a room attribute the server controls (`0x140 SetAttrFlags`' unresolved
`attr_selector`, or a bit in `room_flags_e8`).
