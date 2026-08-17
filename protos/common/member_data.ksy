meta:
  id: member_data
  endian: be
  license: CC0-1.0
doc: |
  The 32-byte per-member data record that carries a player's lobby CARD
  (team/faction, host map-picker recent-level history, rank). NB: this record
  does NOT carry MP cosmetics or a gear loadout - the "loadout_slot" labels here
  were CORRECTED 2026-08-17 to recent_level_* (see that field). The same 32 bytes
  appear in four places, all cross-confirmed:

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
  - id: recent_level_0
    type: u1
    doc: |
      Offset 10. CORRECTED 2026-08-17 (was mislabeled "loadout_slot_0"): NOT
      loadout. This byte and recent_level_1..3 are the host map-picker's
      RECENT-LEVEL ring - the low bytes of `NetGameManager+0x4982` (global
      0x01382082), a ring of recently-played level/map indices. The blob
      producer FUN_003b15bc copies them here; the host's weighted-random map
      picker FUN_003a2310 reads them byte-wise (`lbz r0, 0xa(blob+k)`, k=0..3)
      and applies a DC penalty when a candidate map matches - i.e. "don't
      replay a map these players just played." 0xff = unset. They churn every
      match, and reset to 0xff on a fresh boot, because they are map history,
      not equipped gear. NB: MP cosmetics are NOT in this blob - they are built
      from the persisted profile (P+0x670..). See research/notes/
      2026-08-17-member-blob-vanity-semantics.md.
  - id: recent_level_1
    type: u1
    doc: "Offset 11. Recent-level ring entry 1. See recent_level_0."
  - id: recent_level_2
    type: u1
    doc: "Offset 12. Recent-level ring entry 2. See recent_level_0."
  - id: recent_level_3
    type: u1
    doc: "Offset 13. Recent-level ring entry 3. See recent_level_0."
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
