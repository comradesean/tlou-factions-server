meta:
  id: kickout
  endian: be
  license: CC0-1.0
doc: |
  Direction: client-to-server

  NetMatchmakingKickout - "Kick from Party" request, client -> server, over
  the Session Manager connection (port 7314). Sender builder confirmed at
  0x00ad6570 (`li r9,311` / `li r3,311` @ 0x00ad6570-0x00ad6574, buffer base
  r1+112, 16-byte send at 0x00ad65bc).

  RENAMED from the earlier (wrong) `room_search_info` identity - the
  16-byte size and room_id-at-offset-8 shape were previously mistaken for a
  RoomSearchInfo message. Disassembly-verified opcode map corrects this:
  0x137 is the client's kick request, and its former "unknown offset 4:8"
  region decodes into two separate u16 member-id fields, not one opaque
  4-byte unknown.

  A `requester_member_id` of 0 is NOT a real user-initiated kick - it is an
  AUTOMATIC removal request with no requesting member (the join flow emits
  one as a side effect of joining; a host whose P2P layer has noticed a dead
  peer emits one too, long after any join - see the timing evidence below).
  Only treat this as a genuine kick request when requester_member_id is a
  real (nonzero) member id.

  DISCRIMINATOR LIVE-PROVEN 2026-08-18, then REFINED the same day. A deliberate
  "Kick from Party" was captured alongside the automatic frames, confirming that
  a nonzero requester_member_id means a real user-initiated kick (1 frame,
  target=2 requester=1, 36 s into a live party).

  CORRECTION to the "join flow" wording above: requester=0 is NOT specifically a
  join-flow artifact. Timing every captured 0x137 against the most recent join
  into the same room shows requester=0 firing in two clearly separated regimes:

    0.01s, 0.02s, 0.02s, 0.17s                      <- during a join flow (4)
    29.7s, 36.3s, 74.1s, 80.0s, 84.0s,
    130.2s, 132.7s, 642.6s                          <- nowhere near a join (8)

  Two thirds of them have nothing to do with joining. The accurate definition is
  therefore "a removal request with NO REQUESTING MEMBER" - a system/automatic
  removal - as opposed to requester=<member id>, a player pressing Kick in the
  UI. The join flow is merely one source of the automatic kind.

  WHAT THE LATE ONES MEAN (observed 2026-08-18 22:43-22:46): a member's client
  died silently; its last traffic was at 22:43:54, and at 22:45:43 the HOST sent
  0x137 target=3 requester=0 - i.e. the host's own P2P layer noticed an
  unreachable peer and asked the server to drop it. The stub took no action
  (correctly, under the current rule); the roster only corrected itself a minute
  later when the dead client's TCP socket finally closed. A HUNG client that
  keeps its socket open would leave a zombie member in the roster indefinitely
  with this rule. Acting on a late requester=0 is a plausible improvement but is
  NOT safe to adopt casually - misreading a control opcode as an action is the
  exact bug class that produced the Join Party 0x138 self-kick, so it needs the
  target's liveness independently confirmed before any removal.

  Server behaviour on the genuine kick, live-verified end to end: reply
  `0x138 Kickedout` to the TARGET's connection and `0x134 RoomLeave`
  (member_id = target) to each remaining member. The target left, the party
  survived, and the remaining member stayed - no host self-kick, which is the
  failure the 0x138 rule exists to prevent (see protos/0x138_kickedout.ksy).
  Taking NO action on a requester=0 frame is also live-verified: the four such
  frames were ignored and the parties they belonged to went on to promote and
  kick normally.
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x137 (311 decimal). `li r9,311` / `li r3,311` @ 0x00ad6570/0x00ad6574."
  - id: target_member_id
    type: u2
    doc: "Offset 4:6. The member id being kicked from the party/room."
  - id: requester_member_id
    type: u2
    doc: "Offset 6:8. The member id requesting the kick. A value of 0 means there is NO requesting member - an automatic removal request, NOT a genuine user-initiated kick. Two observed sources: the join flow (fires ~0.01-0.17 s after a RoomJoin) and a host whose P2P layer has noticed a dead peer (fires 30-640 s after any join). Only a nonzero value is a player pressing Kick in the UI - see doc-level note."
  - id: room_id
    type: u8
    doc: "Offset 8:16. The room the target/requester both belong to - same room_id-echo pattern used throughout this opcode family."
