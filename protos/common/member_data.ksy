meta:
  id: member_data
  endian: be
  license: CC0-1.0
doc: |
  The 32-byte per-member data record that carries a player's lobby CARD
  (team/faction, loadout, rank). The same 32 bytes appear in four places, all
  cross-confirmed:

  - `0x12f` RoomCreate wire 0xa8:0xc8 (the host's own card), length at wire 0x26
  - `0x130` RoomJoin  wire 0x18:0x38 (the joiner's own card), length at wire 0x0c
  - `0x131` Member    each roster entry offset 40:72, length at entry offset 39
  - `0x13a`/`0x13b`   SetMemberData / MemberUpdatedData payload

  The rank/loadout UI getter `_opd_FUN_00ad2650` hands this record to the lobby
  card ONLY when its length is exactly 32 (`cmpwi 32; beq` @ 0x00ad2734); any
  other length renders the remote player's card as absent. See
  research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md.

  FIELD LAYOUT — decoded from 47 distinct live RoomCreate cards across both test
  accounts (comradesean, mgnomad2) in captures/tcp_catch.log, cross-checked
  against the earlier independent team-selection finding. Both test accounts are
  UNRANKED, so the rank/stat fields read 0 or uninitialised here; those fields
  are named from the getter's usage but their populated form is unconfirmed
  (needs a ranked-account capture) and is flagged per-field below.
seq:
  - id: reserved_0
    type: u4
    doc: "Offset 0:4. Zero in all 47 captures. Reserved / unused."
  - id: uninit_4
    size: 4
    doc: |
      Offset 4:8. Uninitialised stack: zero in most captures but observed
      leaking a stale room-object pointer (`01 38 7f 58` = mgnomad2's
      0x01387f58) in several. Not a meaningful field - do not read it.
  - id: team
    type: u2
    doc: |
      Offset 8:10. Team / faction selection. Live values 0, 1, 2 only. This is
      the same field previously located as "the u16 at wire 0xb0" (0=unset,
      1/2 = the two factions) in
      research/notes/2026-08-16-team-selection-field-confirmed.md - wire 0xb0
      of RoomCreate == offset 8 of this record. High confidence.
  - id: loadout_slot_0
    type: u2
    doc: |
      Offset 10:12. First loadout item-id. 0xffff = empty slot; live non-empty
      values 0x000e, 0x000f, 0x0011, 0x0012, 0x0013, 0x0015 (small item ids).
      Varies as the player changes loadout between captures. High confidence
      it is a loadout slot; the id->item mapping is not yet decoded.
  - id: loadout_slot_1
    type: u2
    doc: |
      Offset 12:14. Second loadout item-id, same encoding as loadout_slot_0
      (0xffff = empty; live 0x000e etc.). The two slots vary independently
      (e.g. `000f 000e`, `0011 000e`, `0013 ffff`).
  - id: rank_value
    type: u2
    doc: |
      Offset 14:16. Candidate rank / progression value read by the card UI.
      ZERO in every capture (both test accounts are rank 0 / unranked), so its
      populated encoding is UNCONFIRMED - named from the getter's usage, not
      from observed non-zero data. Confirm with a ranked-account capture.
  - id: reserved_10
    size: 6
    doc: "Offset 16:22. Zero in all 47 captures. Reserved, or additional stat fields that stay 0 for unranked accounts."
  - id: uninit_tail
    size: 10
    doc: |
      Offset 22:32. Uninitialised / stale stack for these unranked accounts -
      the bytes vary randomly across captures and include recognisable stale
      pointers (`01 45 cd 40`, `d0 03 fa b0`) and timestamp-shaped values, i.e.
      leftover stack rather than a real field. This is the one region that is
      genuinely opaque here; on a ranked account it MAY hold stats, but there
      is no ground truth for that yet. Send zero.
